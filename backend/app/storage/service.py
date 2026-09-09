from __future__ import annotations

import hashlib
import os
import re
import uuid
from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO, Iterator, Optional, Tuple

from app.core.config import settings
from app.core.exceptions import DependencyUnavailable, ValidationFailed


class StorageBackend(ABC):
    @abstractmethod
    def put(self, key: str, data: bytes, content_type: str) -> None: ...

    @abstractmethod
    def get(self, key: str) -> bytes: ...

    @abstractmethod
    def stream(self, key: str) -> Iterator[bytes]: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def health(self) -> Tuple[bool, str]: ...


class LocalStorage(StorageBackend):
    def __init__(self, root: str):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        p = (self.root / key).resolve()
        if self.root not in p.parents and p != self.root:
            raise ValidationFailed("Invalid storage key")
        return p

    def put(self, key: str, data: bytes, content_type: str) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, p)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def stream(self, key: str, chunk: int = 1024 * 512) -> Iterator[bytes]:
        with open(self._path(key), "rb") as fh:
            while True:
                buf = fh.read(chunk)
                if not buf:
                    break
                yield buf

    def delete(self, key: str) -> None:
        p = self._path(key)
        if p.exists():
            p.unlink()

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def health(self) -> Tuple[bool, str]:
        try:
            probe = self.root / ".healthcheck"
            probe.write_text("ok")
            probe.unlink()
            return True, f"local:{self.root}"
        except Exception as exc:  # pragma: no cover
            return False, str(exc)


class S3Storage(StorageBackend):
    def __init__(self):
        import boto3
        from botocore.config import Config

        self.bucket = settings.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
            use_ssl=settings.s3_use_ssl,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except Exception:
            try:
                self.client.create_bucket(Bucket=self.bucket)
            except Exception as exc:
                raise DependencyUnavailable(f"Object storage bucket unavailable: {exc}")

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)

    def get(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def stream(self, key: str) -> Iterator[bytes]:
        body = self.client.get_object(Bucket=self.bucket, Key=key)["Body"]
        for chunk in body.iter_chunks(chunk_size=1024 * 512):
            yield chunk

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False

    def health(self) -> Tuple[bool, str]:
        try:
            self.client.head_bucket(Bucket=self.bucket)
            return True, f"s3:{self.bucket}"
        except Exception as exc:
            return False, str(exc)


_backend: Optional[StorageBackend] = None


def get_storage() -> StorageBackend:
    global _backend
    if _backend is None:
        _backend = S3Storage() if settings.storage_backend == "s3" else LocalStorage(settings.storage_local_path)
    return _backend


def reset_storage() -> None:
    global _backend
    _backend = None


_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


def safe_filename(name: str) -> str:
    base = os.path.basename(name or "file")
    base = _SAFE_NAME.sub("_", base).strip("._") or "file"
    return base[:200]


def build_key(prefix: str, filename: str) -> str:
    return f"{prefix}/{uuid.uuid4().hex}/{safe_filename(filename)}"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_upload(fileobj: BinaryIO, max_mb: int) -> bytes:
    limit = max_mb * 1024 * 1024
    data = fileobj.read(limit + 1)
    if len(data) > limit:
        raise ValidationFailed(f"File exceeds the maximum upload size of {max_mb} MB")
    if not data:
        raise ValidationFailed("Uploaded file is empty")
    return data
