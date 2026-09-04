"""Optional API-key guard. Unset FINOS_API_KEY = open demo mode.

When set, all mutating endpoints (except the HMAC-signed Razorpay webhook)
require header X-API-Key. Read-only GETs stay public.
"""
import os

from fastapi import Request

from .errors import AppError

API_KEY = os.environ.get("FINOS_API_KEY", "")


def require_key(request: Request):
    if not API_KEY:
        return
    if request.headers.get("x-api-key", "") != API_KEY:
        raise AppError("Missing or invalid API key.", code="unauthorized", status=401)
