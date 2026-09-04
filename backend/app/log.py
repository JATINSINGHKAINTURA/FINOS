"""One-line structured-ish logging for every request + key events."""
import logging
import sys
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("finos")
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
logger.addHandler(handler)
logger.setLevel(logging.INFO)
logger.propagate = False


def event(msg: str, **fields):
    parts = " ".join(f"{k}={v}" for k, v in fields.items())
    logger.info("%s %s", msg, parts)


class RequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        rid = uuid.uuid4().hex[:8]
        t0 = time.time()
        try:
            resp = await call_next(request)
            event("http", id=rid, method=request.method, path=request.url.path,
                  status=resp.status_code, ms=int((time.time() - t0) * 1000))
            return resp
        except Exception as e:  # logged by the unhandled handler too; keep id correlation
            event("http_error", id=rid, err=type(e).__name__)
            raise
