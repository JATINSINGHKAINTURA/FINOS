"""Consistent API errors. Every failure is {ok:false, error:str, code:str}."""
from fastapi import Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(self, message: str, code: str = "bad_request", status: int = 400):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status


async def app_error_handler(_: Request, exc: AppError):
    return JSONResponse({"ok": False, "error": exc.message, "code": exc.code},
                        status_code=exc.status)


async def unhandled_handler(_: Request, exc: Exception):
    # Never leak internals to clients; details go to server logs.
    import logging
    logging.getLogger("finos").exception("unhandled error: %s", exc)
    return JSONResponse({"ok": False, "error": "Internal error.", "code": "internal"},
                        status_code=500)
