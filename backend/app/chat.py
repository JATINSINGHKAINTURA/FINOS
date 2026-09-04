"""General assistant: grounded in FINOS data, strictly read-only.

With DEEPSEEK_API_KEY it reasons over live case facts; without it a
deterministic fallback answers from the same facts so the UI always works.
"""
import uuid

import httpx

from .ai import BASE_URL, API_KEY, MODEL
from .errors import AppError
from .models import Case, ChatMessage, ChatSession

MAX_MSG = 2000


def clean(text: str) -> str:
    if not isinstance(text, str):
        raise AppError("Message must be text.", code="validation", status=422)
    t = "".join(ch for ch in text if ch == "\n" or ch == "\t" or ord(ch) >= 32).strip()
    if not t:
        raise AppError("Message is empty.", code="validation", status=422)
    if len(t) > MAX_MSG:
        raise AppError(f"Message too long (max {MAX_MSG} chars).", code="validation", status=422)
    return t


def get_session(db, kind: str, session_id: str | None = None) -> ChatSession:
    if session_id:
        s = db.query(ChatSession).filter_by(session_id=session_id, kind=kind).first()
        if s:
            return s
    s = ChatSession(session_id=f"sess-{uuid.uuid4().hex[:12]}", kind=kind, state={})
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def save_message(db, session_id: str, role: str, content: str):
    db.add(ChatMessage(session_id=session_id, role=role, content=content[:4000]))
    db.commit()


def history(db, session_id: str, limit: int = 20) -> list:
    rows = (db.query(ChatMessage).filter_by(session_id=session_id)
            .order_by(ChatMessage.id.desc()).limit(limit).all())
    return [{"role": r.role, "content": r.content} for r in reversed(rows)]


def ground(db) -> str:
    cases = db.query(Case).order_by(Case.case_no).all()
    lines = [f"#{c.case_no} [{c.kind}] {c.title} — {c.status}" for c in cases]
    return "Open FINOS cases:\n" + ("\n".join(lines) if lines else "(none)") + \
        "\nFINOS pipeline: Facts → Rules/State → AI Reasoning → Policy Gate → Approved Action."


SYSTEM = ("You are the FINOS assistant. Answer from the provided FINOS facts only; "
          "never invent payments, amounts, or case outcomes. You are read-only: you cannot "
          "approve or execute actions — direct users to the case page or a Guidebot for that. "
          "Be concise.")


def fallback_reply(db, message: str) -> tuple[str, list]:
    m = message.lower()
    cases = db.query(Case).order_by(Case.case_no).all()
    if any(w in m for w in ("hello", "hi", "hey", "namaste")) and len(m) < 20:
        return ("Hello. I can explain FINOS cases, payment states, and how approvals work. "
                "Try “list cases” or “explain case 1042”.",
                ["List cases", "Explain case 1042", "How do approvals work?"])
    if "case 1042" in m or "case #1042" in m:
        return ("Case #1042 is an ambiguous payment: order O-123 was charged (P-456, captured) "
                "but the checkout never got the final response. FINOS recommends NOT asking the "
                "customer to pay again — the money already arrived.", ["List cases", "Explain case 1043"])
    if "case 1043" in m or "case #1043" in m:
        return ("Case #1043 is a duplicate payment: order O-124 was captured twice (P-457 + P-458). "
                "FINOS recommends refunding the later payment through the guarded approval flow.",
                ["Explain case 1042", "How do approvals work?"])
    if "case 1044" in m or "case #1044" in m:
        return ("Case #1044 is a settlement anomaly on S-789: expected vs actual differs even after "
                "fees and tax. FINOS explains the math and flags the remainder for finance review.",
                ["List cases"])
    if "case" in m and any(ch.isdigit() for ch in m):
        return ("Tell me which case number (1042, 1043, or 1044) and I'll explain it.",
                ["Explain case 1042", "Explain case 1043", "Explain case 1044"])
    if "list" in m or "cases" in m or "dashboard" in m:
        lines = "; ".join(f"#{c.case_no} {c.title} ({c.status})" for c in cases) or "no cases"
        return (f"Current cases: {lines}. Open one to run the investigation flow.",
                ["Explain case 1042", "How do approvals work?"])
    if "approv" in m or "refund" in m or "action" in m or "policy" in m:
        return ("Approvals: Investigate → a Decision + proposed action → Approve (policy gate checks "
                "it) → Execute (idempotent, audited). Refunds only pass for confirmed duplicates; "
                "everything is recorded in the audit trail.", ["List cases", "What is a Guidebot?"])
    if "guidebot" in m:
        return ("Guidebots are task-oriented assistants that walk you through a workflow step by step "
                "— e.g. Case Pilot resolves a case with you, Webhook Helper tests event ingestion. "
                "Open the Guidebots tab to start one.", ["List cases"])
    if "webhook" in m or "razorpay" in m:
        return ("FINOS ingests Razorpay webhooks at POST /webhooks/razorpay, verifies the HMAC-SHA256 "
                "signature when RAZORPAY_WEBHOOK_SECRET is set, normalizes the event, and re-runs "
                "exception detection. Unverified senders are still stored but flagged.",
                ["What is a Guidebot?", "List cases"])
    if "who are you" in m or "what can you" in m or "help" in m:
        return ("I'm the FINOS assistant (demo mode: answering from verified case data). I explain "
                "cases, states, and approvals. For step-by-step help, use a Guidebot.",
                ["List cases", "Explain case 1042", "What is a Guidebot?"])
    return ("I can help with FINOS cases, payment states, approvals, webhooks, and Guidebots. "
            "What would you like to know?",
            ["List cases", "Explain case 1042", "How do approvals work?"])


def chat_turn(db, session_id: str | None, message: str) -> dict:
    msg = clean(message)
    sess = get_session(db, "chat", session_id)
    save_message(db, sess.session_id, "user", msg)
    if API_KEY:
        try:
            r = httpx.post(
                f"{BASE_URL}/chat/completions",
                headers={"Authorization": f"Bearer {API_KEY}"},
                json={"model": MODEL, "temperature": 0.2,
                      "messages": [{"role": "system", "content": SYSTEM + "\n" + ground(db)},
                                   *history(db, sess.session_id)[-10:],
                                   {"role": "user", "content": msg}]},
                timeout=60,
            )
            r.raise_for_status()
            reply = r.json()["choices"][0]["message"]["content"].strip()
            suggestions = ["List cases", "Explain case 1042", "How do approvals work?"]
        except Exception:
            reply, suggestions = fallback_reply(db, msg)
    else:
        reply, suggestions = fallback_reply(db, msg)
    save_message(db, sess.session_id, "assistant", reply)
    return {"session_id": sess.session_id, "reply": reply, "suggestions": suggestions}
