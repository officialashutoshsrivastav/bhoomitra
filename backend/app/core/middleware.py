from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque
from typing import Deque, Dict, Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings
from app.core.exceptions import error_body
from app.core.logging import get_logger, request_id_ctx

logger = get_logger("bhoomitra.http")


def client_ip(request: Request) -> str:
    if settings.trusted_proxies:
        peer = request.client.host if request.client else ""
        if peer in settings.trusted_proxies:
            xff = request.headers.get("x-forwarded-for")
            if xff:
                return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        token = request_id_ctx.set(rid)
        request.state.request_id = rid
        start = time.perf_counter()
        try:
            response: Response = await call_next(request)
        finally:
            request_id_ctx.reset(token)
        duration_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Request-ID"] = rid
        if not request.url.path.startswith("/health"):
            logger.info("request", extra={"extra_data": {"method": request.method, "path": request.url.path, "status": response.status_code, "ms": round(duration_ms, 1), "ip": client_ip(request)}})
        return response


class SecureHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "geolocation=(self), camera=(), microphone=()")
        response.headers.setdefault("Cache-Control", "no-store")
        if settings.is_production or settings.cookie_secure:
            response.headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
        if not request.url.path.startswith(("/docs", "/redoc", "/openapi.json")):
            response.headers.setdefault("Content-Security-Policy", "default-src 'self'; frame-ancestors 'none'")
        return response


class _MemoryLimiter:
    def __init__(self):
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)

    def allow(self, key: str, limit: int, window: int = 60) -> bool:
        now = time.time()
        q = self._hits[key]
        while q and q[0] < now - window:
            q.popleft()
        if len(q) >= limit:
            return False
        q.append(now)
        if len(self._hits) > 50000:
            for k in list(self._hits.keys())[:1000]:
                self._hits.pop(k, None)
        return True


class _RedisLimiter:
    def __init__(self, url: str):
        import redis  # type: ignore

        self._r = redis.Redis.from_url(url, socket_timeout=0.5)

    def allow(self, key: str, limit: int, window: int = 60) -> bool:
        try:
            bucket = f"rl:{key}:{int(time.time() // window)}"
            pipe = self._r.pipeline()
            pipe.incr(bucket)
            pipe.expire(bucket, window)
            count, _ = pipe.execute()
            return int(count) <= limit
        except Exception:
            return True


_limiter: Optional[object] = None


def get_limiter():
    global _limiter
    if _limiter is None:
        if settings.redis_url and not settings.is_test:
            try:
                _limiter = _RedisLimiter(settings.redis_url)
            except Exception:
                _limiter = _MemoryLimiter()
        else:
            _limiter = _MemoryLimiter()
    return _limiter


AUTH_PATHS = ("/auth/login", "/auth/register", "/auth/refresh", "/auth/password/forgot", "/auth/password/reset")


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not settings.rate_limit_enabled or request.url.path.startswith("/health"):
            return await call_next(request)
        path = request.url.path
        is_auth = any(path.endswith(p) for p in AUTH_PATHS)
        limit = settings.rate_limit_auth_per_minute if is_auth else settings.rate_limit_default_per_minute
        key = f"{'auth' if is_auth else 'api'}:{client_ip(request)}"
        if not get_limiter().allow(key, limit):
            return JSONResponse(status_code=429, content=error_body("rate_limited", "Too many requests, please slow down"), headers={"Retry-After": "60"})
        return await call_next(request)
