"""Razorpay integration: real webhook-signature verification + minimal REST client.

No invented capabilities: we only read payments/orders and create refunds.
There is no "retry payment" API — FINOS never re-charges a customer.
Default is DRY_RUN (no real money moves) unless RAZORPAY_LIVE=1 with keys set.
"""
import hashlib
import hmac
import os

import httpx

WEBHOOK_SECRET = os.environ.get("RAZORPAY_WEBHOOK_SECRET", "")
KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "")
KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "")
BASE_URL = os.environ.get("RAZORPAY_BASE_URL", "https://api.razorpay.com/v1")
DRY_RUN = os.environ.get("RAZORPAY_LIVE", "") != "1"


def verify_signature(body: bytes, signature: str) -> bool:
    """Real Razorpay scheme: HMAC-SHA256 of the raw body, hex digest."""
    if not WEBHOOK_SECRET or not signature:
        return False
    expected = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def fetch_payment(payment_id: str):
    """Read a payment from Razorpay. Returns None in dry-run / without keys."""
    if DRY_RUN or not KEY_ID or not KEY_SECRET:
        return None
    r = httpx.get(f"{BASE_URL}/payments/{payment_id}", auth=(KEY_ID, KEY_SECRET), timeout=20)
    r.raise_for_status()
    return r.json()


def create_refund(payment_id: str, amount: int, notes: dict | None = None) -> dict:
    """Create a refund. Dry-run returns a simulated processed refund."""
    if DRY_RUN or not KEY_ID or not KEY_SECRET:
        return {
            "id": f"RFND-DRY-{payment_id[-6:]}",
            "payment_id": payment_id,
            "amount": amount,
            "status": "processed",
            "dry_run": True,
        }
    r = httpx.post(
        f"{BASE_URL}/refunds",
        auth=(KEY_ID, KEY_SECRET),
        json={"payment_id": payment_id, "amount": amount, "notes": notes or {}},
        timeout=20,
    )
    r.raise_for_status()
    data = r.json()
    data["dry_run"] = False
    return data
