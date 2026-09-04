"""In-memory sliding-window rate limiter (per IP). Zero dependencies.

Per-instance state: correct for single-process demo; for multi-instance
deployments put a shared store here (documented limitation, not silent).
"""
import os
import time
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

WRITE_PER_MIN = int(os.environ.get("FINOS_RL_WRITE_PER_MIN", "60"))
CHAT_PER_MIN = int(os.environ.get("FINOS_RL_CHAT_PER_MIN", "30"))


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.hits: dict[str, deque] = defaultdict(deque)

    async def dispatch(self, request, call_next):
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            path = request.url.path
            limit = CHAT_PER_MIN if ("/api/chat" in path or "/api/guidebots" in path) else WRITE_PER_MIN
            ip = request.client.host if request.client else "unknown"
            key = f"{ip}:{ 'chat' if limit == CHAT_PER_MIN else 'write'}"
            now = time.time()
            window = self.hits[key]
            while window and window[0] <= now - 60:
                window.popleft()
            if len(window) >= limit:
                return JSONResponse({"ok": False, "error": "Rate limit exceeded. Slow down.",
                                     "code": "rate_limited"}, status_code=429)
            window.append(now)
        return await call_next(request)
