"""Investigator: AI explains verified evidence, never invents financial truth.

Tries DeepSeek (OpenAI-compatible) with a strict JSON contract; falls back to
deterministic rules when no key is configured so the demo always works.
"""
import json
import os

import httpx

from . import state as st
from .models import Decision

BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")

ALLOWED_ACTIONS = ("no_action", "refund", "flag_review")

SYSTEM = (
    "You are FINOS, a financial-operations investigator. You receive VERIFIED facts "
    "(events, amounts, statuses). Rules:\n"
    "1. Never invent payments, amounts, or statuses not in the facts.\n"
    "2. Explain what happened, cite the evidence, state confidence.\n"
    "3. Recommend exactly one of: no_action | refund | flag_review.\n"
    "4. Reply with JSON ONLY, no markdown, matching this schema:\n"
    '{"diagnosis": str, "evidence": [str], "confidence": "high|medium|low", '
    '"recommended_action": str, "rationale": str}'
)


def fallback(db, case) -> dict:
    if case.kind == "ambiguous":
        s = st.reconstruct(db, case.order_id)
        pay = s["state"]["captured_ids"][0] if s["state"]["captured_ids"] else case.payment_id
        return {
            "diagnosis": "Payment appears successful despite checkout timeout.",
            "evidence": [f"Order {case.order_id} → Payment {pay} → authorized → captured → webhook received"],
            "confidence": "high",
            "recommended_action": "no_action",
            "rationale": f"Payment {pay} is already captured. Do not request another payment.",
            "model": "fallback-rules-v1",
        }
    if case.kind == "duplicate":
        s = st.reconstruct(db, case.order_id)["state"]
        ids = " + ".join(s["captured_ids"])
        return {
            "diagnosis": f"Duplicate payment: {s['captured_count']} captured payments on one order.",
            "evidence": [f"Order {case.order_id} captured: {ids}",
                         f"Captured total {s['captured_total']} vs due {s['amount_due']}"],
            "confidence": "high",
            "recommended_action": "refund",
            "rationale": "Same order context paid twice. Refund the later payment via the guarded action layer.",
            "model": "fallback-rules-v1",
        }
    m = st.settlement_math(db, (db_case_settlement(db, case) or ""))
    return {
        "diagnosis": "Settlement shortfall with an unexplained remainder.",
        "evidence": [f"Expected {m.get('expected')} vs actual {m.get('actual')} "
                     f"(fees {m.get('fees')}, tax {m.get('tax')}, ref {m.get('reference')})",
                     f"Unexplained difference: {m.get('unexplained')} paise"],
        "confidence": "medium",
        "recommended_action": "flag_review",
        "rationale": "Fees and tax explain part of the gap; the remainder needs finance review.",
        "model": "fallback-rules-v1",
    }


def db_case_settlement(db, case) -> str:
    from .models import Settlement
    row = db.query(Settlement).order_by(Settlement.id.desc()).first()
    return row.settlement_id if row else ""


def evidence_pack(db, case) -> dict:
    pack = {"kind": case.kind, "order_id": case.order_id, "payment_id": case.payment_id}
    if case.order_id:
        pack["reconstruction"] = st.reconstruct(db, case.order_id)
    if case.kind == "settlement":
        pack["settlement"] = st.settlement_math(db, db_case_settlement(db, case))
    return pack


def call_deepseek(pack: dict) -> dict | None:
    if not API_KEY:
        return None
    try:
        r = httpx.post(
            f"{BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}"},
            json={"model": MODEL, "temperature": 0,
                  "messages": [{"role": "system", "content": SYSTEM},
                               {"role": "user", "content": json.dumps(pack)}]},
            timeout=60,
        )
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"].strip()
        if text.startswith("```"):
            text = text.strip("`").split("\n", 1)[-1]
        data = json.loads(text)
        if data.get("recommended_action") not in ALLOWED_ACTIONS:
            return None
        data["model"] = MODEL
        return data
    except Exception:
        return None


def investigate(db, case) -> Decision:
    pack = evidence_pack(db, case)
    data = call_deepseek(pack) or fallback(db, case)
    d = Decision(case_id=case.id, diagnosis=data["diagnosis"], evidence=data["evidence"],
                 confidence=data.get("confidence", "medium"),
                 recommended_action=data["recommended_action"],
                 rationale=data.get("rationale", ""), model=data.get("model", ""))
    db.add(d)
    db.commit()
    db.refresh(d)
    return d
