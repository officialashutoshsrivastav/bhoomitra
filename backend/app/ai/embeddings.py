from __future__ import annotations

import hashlib
import math
import re
from abc import ABC, abstractmethod
from typing import List, Optional

import numpy as np

from app.core.config import settings
from app.core.exceptions import DependencyUnavailable

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOP = {"the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is", "are", "was", "were", "be", "by", "with", "as", "at", "that", "this", "it", "from", "which", "these", "those", "their", "its", "has", "have", "had", "not", "but", "also", "than", "into", "such", "may", "can", "will", "shall", "been", "being", "we", "our", "they", "them", "there", "where", "when", "who", "what", "how"}


def tokenize(text: str) -> List[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOP and len(t) > 1]


class EmbeddingProvider(ABC):
    name: str = "abstract"
    model_name: str = ""

    @property
    def dim(self) -> int:
        return settings.embedding_dim

    @abstractmethod
    def embed(self, texts: List[str]) -> List[List[float]]: ...

    def embed_one(self, text: str) -> List[float]:
        return self.embed([text])[0]


class HashingEmbeddings(EmbeddingProvider):
    """Deterministic feature-hashed unigram+bigram embedding (sub-linear TF, L2
    normalised). It needs no external service or model download, gives useful
    lexical-semantic similarity for retrieval and is fully reproducible. It is
    the documented fallback when OPENAI_API_KEY is not configured; production
    deployments should switch EMBEDDING_PROVIDER=openai (or another dense model)
    and re-index."""

    name = "hashing"

    def __init__(self, dim: Optional[int] = None):
        self._dim = dim or settings.embedding_dim
        self.model_name = f"hashing-v1-{self._dim}"

    @property
    def dim(self) -> int:
        return self._dim

    def _features(self, text: str) -> List[str]:
        toks = tokenize(text)
        feats = list(toks)
        feats.extend(f"{a}_{b}" for a, b in zip(toks, toks[1:]))
        return feats

    def _vector(self, text: str) -> np.ndarray:
        vec = np.zeros(self._dim, dtype=np.float32)
        feats = self._features(text)
        if not feats:
            return vec
        counts: dict = {}
        for f in feats:
            counts[f] = counts.get(f, 0) + 1
        for f, c in counts.items():
            h = hashlib.blake2b(f.encode("utf-8"), digest_size=8).digest()
            idx = int.from_bytes(h[:4], "little") % self._dim
            sign = 1.0 if (h[4] & 1) else -1.0
            vec[idx] += sign * (1.0 + math.log(c))
        norm = float(np.linalg.norm(vec))
        if norm > 0:
            vec /= norm
        return vec

    def embed(self, texts: List[str]) -> List[List[float]]:
        return [self._vector(t).tolist() for t in texts]


class OpenAIEmbeddings(EmbeddingProvider):
    name = "openai"

    def __init__(self):
        if not settings.openai_api_key:
            raise DependencyUnavailable("OPENAI_API_KEY is not configured")
        self.model_name = settings.openai_embedding_model

    def embed(self, texts: List[str]) -> List[List[float]]:
        import httpx

        out: List[List[float]] = []
        for i in range(0, len(texts), 64):
            batch = [t[:8000] for t in texts[i : i + 64]]
            resp = httpx.post(
                f"{settings.openai_base_url}/embeddings",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json={"model": self.model_name, "input": batch, "dimensions": settings.embedding_dim},
                timeout=60,
            )
            if resp.status_code >= 400:
                raise DependencyUnavailable(f"Embedding API error {resp.status_code}: {resp.text[:200]}")
            data = resp.json()["data"]
            out.extend([d["embedding"] for d in sorted(data, key=lambda d: d["index"])])
        return out


_provider: Optional[EmbeddingProvider] = None


def get_embedding_provider() -> EmbeddingProvider:
    global _provider
    if _provider is None:
        _provider = OpenAIEmbeddings() if settings.embedding_provider == "openai" else HashingEmbeddings()
    return _provider


def cosine(a: List[float], b: List[float]) -> float:
    va, vb = np.asarray(a, dtype=np.float32), np.asarray(b, dtype=np.float32)
    na, nb = np.linalg.norm(va), np.linalg.norm(vb)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(va, vb) / (na * nb))
