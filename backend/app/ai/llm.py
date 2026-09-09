from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional

from app.ai.embeddings import tokenize
from app.core.config import settings
from app.core.exceptions import DependencyUnavailable

SYSTEM_PROMPT = """You are the Bhoomitra research assistant for India's Department of Land Resources.
Answer ONLY from the numbered evidence passages provided. Every factual sentence must end with
citation markers like [1] or [2][4] that refer to the passages. If the passages do not contain
enough information, say so explicitly and do not guess. Never invent sources, statistics,
policies, datasets or citations. Distinguish clearly between what the evidence states (facts)
and any inference you draw. Keep answers concise, neutral and policy-relevant."""


@dataclass
class Passage:
    marker: int
    text: str
    title: str
    locator: str


@dataclass
class Generation:
    answer: str
    provider: str
    model_name: str
    used_markers: List[int]
    inference_note: Optional[str] = None


class LLMProvider(ABC):
    name = "abstract"
    model_name = ""

    @abstractmethod
    def answer(self, question: str, passages: List[Passage], history: Optional[List[Dict[str, str]]] = None) -> Generation: ...


_MARKER_RE = re.compile(r"\[(\d{1,2})\]")


def markers_in(text: str) -> List[int]:
    return sorted({int(m) for m in _MARKER_RE.findall(text)})


class OpenAIChat(LLMProvider):
    name = "openai"

    def __init__(self):
        if not settings.openai_api_key:
            raise DependencyUnavailable("OPENAI_API_KEY is not configured")
        self.model_name = settings.openai_chat_model

    def answer(self, question: str, passages: List[Passage], history: Optional[List[Dict[str, str]]] = None) -> Generation:
        import httpx

        evidence = "\n\n".join(f"[{p.marker}] ({p.title}, {p.locator})\n{p.text}" for p in passages)
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for h in (history or [])[-6:]:
            messages.append({"role": h["role"], "content": h["content"][:2000]})
        messages.append({"role": "user", "content": f"Evidence passages:\n\n{evidence}\n\nQuestion: {question}"})
        resp = httpx.post(f"{settings.openai_base_url}/chat/completions", headers={"Authorization": f"Bearer {settings.openai_api_key}"}, json={"model": self.model_name, "messages": messages, "temperature": 0.1, "max_tokens": 900}, timeout=90)
        if resp.status_code >= 400:
            raise DependencyUnavailable(f"LLM API error {resp.status_code}: {resp.text[:200]}")
        content = resp.json()["choices"][0]["message"]["content"].strip()
        valid = {p.marker for p in passages}
        used = [m for m in markers_in(content) if m in valid]
        return Generation(answer=content, provider=self.name, model_name=self.model_name, used_markers=used)


class ExtractiveAnswerer(LLMProvider):
    """Citation-only answerer used when no external LLM is configured.

    It selects the most query-relevant sentences from the retrieved passages and
    presents them verbatim with markers, so nothing in the answer can be
    fabricated. It is deliberately conservative and labelled as such."""

    name = "local-extractive"
    model_name = "extractive-v1"

    _SENT = re.compile(r"(?<=[.!?])\s+")

    def answer(self, question: str, passages: List[Passage], history: Optional[List[Dict[str, str]]] = None) -> Generation:
        q_terms = set(tokenize(question))
        scored = []
        for p in passages:
            for sent in self._SENT.split(p.text):
                sent = sent.strip()
                if len(sent) < 30 or len(sent) > 600:
                    continue
                terms = set(tokenize(sent))
                if not terms:
                    continue
                overlap = len(q_terms & terms)
                if overlap == 0:
                    continue
                score = overlap / (len(q_terms) or 1) + 0.15 * (overlap / len(terms))
                scored.append((score, p.marker, sent))
        scored.sort(key=lambda t: -t[0])
        chosen, used_markers, seen = [], [], set()
        for score, marker, sent in scored:
            key = sent[:80].lower()
            if key in seen:
                continue
            seen.add(key)
            chosen.append(f"{sent} [{marker}]")
            if marker not in used_markers:
                used_markers.append(marker)
            if len(chosen) >= 6:
                break
        if not chosen:
            return Generation(answer="The retrieved evidence does not contain passages that directly address this question. Try rephrasing, narrowing the geography, or uploading the relevant documents.", provider=self.name, model_name=self.model_name, used_markers=[], inference_note="No sentence in the retrieved evidence overlapped with the question terms.")
        answer = "Based on the retrieved evidence:\n\n" + "\n\n".join(f"• {c}" for c in chosen)
        answer += "\n\nThese statements are quoted from the cited sources; no inference beyond the evidence has been made. Configure an LLM provider for synthesised answers."
        return Generation(answer=answer, provider=self.name, model_name=self.model_name, used_markers=sorted(used_markers), inference_note="Extractive mode: answer sentences are verbatim excerpts.")


_provider: Optional[LLMProvider] = None


def get_llm_provider() -> LLMProvider:
    global _provider
    if _provider is None:
        _provider = OpenAIChat() if settings.ai_provider == "openai" else ExtractiveAnswerer()
    return _provider
