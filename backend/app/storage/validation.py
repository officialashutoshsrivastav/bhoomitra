from __future__ import annotations

import zipfile
from abc import ABC, abstractmethod
from io import BytesIO
from typing import Optional, Tuple

from app.core.config import settings
from app.core.exceptions import ValidationFailed

_MAGIC = [
    (b"%PDF-", "application/pdf"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"II*\x00", "image/tiff"),
    (b"MM\x00*", "image/tiff"),
]

_EXT_MIME = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".csv": "text/csv",
    ".json": "application/json",
    ".geojson": "application/geo+json",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".zip": "application/zip",
}


def sniff_mime(data: bytes, filename: str, declared: Optional[str]) -> str:
    head = data[:16]
    for magic, mime in _MAGIC:
        if head.startswith(magic):
            return mime
    if head.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(BytesIO(data)) as zf:
                names = set(zf.namelist())
                if "word/document.xml" in names:
                    return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                if "xl/workbook.xml" in names:
                    return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        except zipfile.BadZipFile:
            raise ValidationFailed("Corrupted archive upload")
        return "application/zip"
    ext = ("." + filename.rsplit(".", 1)[-1].lower()) if "." in filename else ""
    if ext in {".txt", ".md", ".csv", ".json", ".geojson"}:
        try:
            data[:4096].decode("utf-8")
        except UnicodeDecodeError:
            raise ValidationFailed("Text upload is not valid UTF-8")
        return _EXT_MIME[ext]
    if declared and declared in settings.allowed_upload_mime:
        return declared
    raise ValidationFailed("Unsupported or unrecognised file type")


class MalwareScanner(ABC):
    name = "none"

    @abstractmethod
    def scan(self, data: bytes, filename: str) -> Tuple[bool, str]: ...


class NoopScanner(MalwareScanner):
    """Placeholder scanner. Wire ClamAV (clamd) here in production; the
    interface is intentionally tiny so the swap is a config change."""

    name = "noop"

    def scan(self, data: bytes, filename: str) -> Tuple[bool, str]:
        if b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*" in data:
            return False, "EICAR test signature detected"
        return True, "scanner not configured (noop)"


_scanner: MalwareScanner = NoopScanner()


def get_scanner() -> MalwareScanner:
    return _scanner


def validate_upload(data: bytes, filename: str, declared_mime: Optional[str]) -> str:
    mime = sniff_mime(data, filename, declared_mime)
    if mime not in settings.allowed_upload_mime:
        raise ValidationFailed(f"File type {mime} is not allowed")
    ok, msg = get_scanner().scan(data, filename)
    if not ok:
        raise ValidationFailed(f"Upload rejected by malware scanner: {msg}")
    return mime
