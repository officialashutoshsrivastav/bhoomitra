from __future__ import annotations

import contextvars
import json
import logging
import sys
import time
from typing import Any, Dict

from app.core.config import settings

request_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
user_id_ctx: contextvars.ContextVar[str] = contextvars.ContextVar("user_id", default="-")

_REDACT_KEYS = {"password", "password_hash", "token", "access_token", "refresh_token", "secret", "authorization", "api_key"}


def redact(data: Any) -> Any:
    if isinstance(data, dict):
        return {k: ("***" if k.lower() in _REDACT_KEYS else redact(v)) for k, v in data.items()}
    if isinstance(data, list):
        return [redact(v) for v in data]
    return data


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": request_id_ctx.get(),
            "user_id": user_id_ctx.get(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        extra = getattr(record, "extra_data", None)
        if extra:
            payload["data"] = redact(extra)
        return json.dumps(payload, default=str)


class PlainFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = f"{self.formatTime(record)} {record.levelname:<7} [{request_id_ctx.get()}] {record.name}: {record.getMessage()}"
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


def configure_logging() -> None:
    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if settings.log_json else PlainFormatter())
    root.addHandler(handler)
    root.setLevel(settings.log_level.upper())
    for noisy in ("uvicorn.access", "botocore", "urllib3", "opensearch"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_event(logger: logging.Logger, msg: str, **data: Any) -> None:
    logger.info(msg, extra={"extra_data": data})
