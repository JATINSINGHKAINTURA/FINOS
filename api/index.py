"""Vercel serverless entry: re-export the same FastAPI app.

Ephemeral filesystem: FINOS_DB defaults to /tmp (reseeded per cold start).
Set real env (DEEPSEEK_API_KEY, RAZORPAY_*, FINOS_API_KEY) in the Vercel dashboard.
"""
import os
import sys

os.environ.setdefault("FINOS_DB", "/tmp/finos.db")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.main import app  # noqa: E402  (Vercel looks for `app`)
