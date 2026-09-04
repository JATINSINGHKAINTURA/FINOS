"""FINOS API: webhook ingest -> state -> investigate -> approve -> execute -> audit,
plus assistant chat + guidebots. Same response shapes as before; errors are now
consistent {ok:false, error, code}."""
import json
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import ai as investigator
from . import chat as assistant
from . import policy as pol
from . import razorpay as rz
from . import rules
from . import state as st
from .actions import approve as approve_action
from .actions import execute as execute_action
from .actions import log_audit, propose
from .auth import require_key
from .db import Base, SessionLocal, engine
from .errors import AppError, app_error_handler, unhandled_handler
from .guidebots import engine as guides
from .guidebots.registry import get_config, list_configs
from .log import RequestLogMiddleware, event
from .models import ActionItem, AuditLog, Case, Decision, Event, Order, Payment, Refund, Settlement
from .ratelimit import RateLimitMiddleware
from .seed import seed


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()
    event("startup", dry_run=rz.DRY_RUN)
    yield


app = FastAPI(title="FINOS", version="0.2.0", lifespan=lifespan)
app.add_exception_handler(AppError, app_error_handler)
app.add_exception_handler(Exception, unhandled_handler)


@app.exception_handler(RequestValidationError)
async def validation_handler(_: Request, exc: RequestValidationError):
    return JSONResponse({"ok": False, "error": "Invalid request.", "code": "validation"},
                        status_code=422)


app.add_middleware(RequestLogMiddleware)
app.add_middleware(RateLimitMiddleware)
origins = [o.strip() for o in os.environ.get("FINOS_CORS_ORIGINS", "*").split(",")]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])


def _iso(dt):
    return dt.isoformat() if dt else None


def ser_case(c: Case) -> dict:
    return {"case_no": c.case_no, "kind": c.kind, "title": c.title, "summary": c.summary,
            "status": c.status, "order_id": c.order_id, "payment_id": c.payment_id,
            "created_at": _iso(c.created_at)}


def ser_decision(d: Decision) -> dict:
    return {"id": d.id, "diagnosis": d.diagnosis, "evidence": d.evidence,
            "confidence": d.confidence, "recommended_action": d.recommended_action,
            "rationale": d.rationale, "model": d.model, "created_at": _iso(d.created_at)}


def ser_action(a: ActionItem | None) -> dict | None:
    if not a:
        return None
    return {"action_id": a.action_id, "kind": a.kind, "status": a.status,
            "params": a.params, "result": a.result, "created_at": _iso(a.created_at)}


class ApproveBody(BaseModel):
    actor: str = Field(default="judge", max_length=64)


class ChatBody(BaseModel):
    session_id: str | None = Field(default=None, max_length=64)
    message: str = Field(max_length=2000)


class GuideChatBody(BaseModel):
    session_id: str | None = Field(default=None, max_length=64)
    message: str = Field(max_length=2000)
    actor: str = Field(default="judge", max_length=64)


def need_case(db, no: int) -> Case:
    c = db.query(Case).filter_by(case_no=no).first()
    if not c:
        raise AppError("Case not found.", code="not_found", status=404)
    return c


@app.get("/health")
def health():
    return {"ok": True, "dry_run": rz.DRY_RUN}


@app.post("/webhooks/razorpay")
async def razorpay_webhook(request: Request):
    body = await request.body()
    try:
        payload = json.loads(body or b"{}")
    except Exception:
        raise AppError("Invalid JSON.", code="validation", status=400)
    if not isinstance(payload, dict):
        raise AppError("Invalid JSON.", code="validation", status=400)
    sig = request.headers.get("x-razorpay-signature", "")
    ok = rz.verify_signature(body, sig)
    db = SessionLocal()
    try:
        eid = str(payload.get("id") or f"evt-{db.query(Event).count() + 1}")
        if db.query(Event).filter_by(event_id=eid).first():
            return {"ok": True, "duplicate": True}
        inner = payload.get("payload", {})
        db.add(Event(event_id=eid, type=str(payload.get("event", "unknown")),
                     entity=str(payload.get("entity", "")), payload=payload,
                     signature_ok=1 if ok else 0, processed=1))
        pay = (inner.get("payment") or {}).get("entity", {})
        if pay.get("id"):
            row = db.query(Payment).filter_by(payment_id=pay["id"]).first()
            if not row and pay.get("order_id"):
                db.add(Payment(payment_id=pay["id"], order_id=pay["order_id"],
                               amount=int(pay.get("amount", 0)),
                               currency=pay.get("currency", "INR"),
                               method=pay.get("method", ""),
                               status=pay.get("status", "created"),
                               captured=1 if pay.get("status") == "captured" else 0))
            elif row and pay.get("status"):
                row.status = pay["status"]
                row.captured = 1 if pay["status"] == "captured" else row.captured
        order = (inner.get("order") or {}).get("entity", {})
        if order.get("id"):
            row = db.query(Order).filter_by(order_id=order["id"]).first()
            if row and str(payload.get("event")) == "order.paid":
                row.status = "paid"
        ref = (inner.get("refund") or {}).get("entity", {})
        if ref.get("id"):
            db.add(Refund(refund_id=ref["id"], payment_id=str(ref.get("payment_id", "")),
                          amount=int(ref.get("amount", 0)),
                          status=str(ref.get("status", "processed")), dry_run=0))
        db.commit()
        opened = rules.detect(db)
        event("webhook", type=payload.get("event"), signature_ok=ok, cases_opened=opened)
        return {"ok": True, "signature_ok": ok, "cases_opened": opened}
    finally:
        db.close()


@app.get("/api/cases")
def list_cases():
    db = SessionLocal()
    try:
        return [ser_case(c) for c in db.query(Case).order_by(Case.case_no).all()]
    finally:
        db.close()


@app.get("/api/cases/{no}")
def case_detail(no: int):
    db = SessionLocal()
    try:
        c = need_case(db, no)
        out = {"case": ser_case(c)}
        if c.order_id:
            out["reconstruction"] = st.reconstruct(db, c.order_id)
        if c.kind == "settlement":
            out["settlement"] = st.settlement_math(db, investigator.db_case_settlement(db, c))
        out["decisions"] = [ser_decision(d) for d in
                            db.query(Decision).filter_by(case_id=c.id).order_by(Decision.id).all()]
        action = db.query(ActionItem).filter_by(case_id=c.id).first()
        out["action"] = ser_action(action)
        out["policy"] = pol.check(db, action.kind, pol.context_for_case(db, c)) if action else None
        audits = []
        for a in db.query(AuditLog).order_by(AuditLog.id).all():
            det = a.details or {}
            if det.get("case_no") == no or det.get("action_id") == f"ACT-{no}":
                audits.append({"audit_id": a.audit_id, "actor": a.actor, "event": a.event,
                               "details": det, "created_at": _iso(a.created_at)})
        out["audit"] = audits
        return out
    finally:
        db.close()


@app.post("/api/cases/{no}/investigate")
def investigate_case(no: int, request: Request):
    require_key(request)
    db = SessionLocal()
    try:
        c = need_case(db, no)
        d = investigator.investigate(db, c)
        action = propose(db, c, d)
        verdict = pol.check(db, action.kind, pol.context_for_case(db, c))
        log_audit(db, "system", "decision.recorded",
                  {"case_no": no, "diagnosis": d.diagnosis, "recommended_action": d.recommended_action})
        return {"decision": ser_decision(d), "action": ser_action(action), "policy": verdict}
    finally:
        db.close()


@app.post("/api/cases/{no}/approve")
def approve_case(no: int, body: ApproveBody, request: Request):
    require_key(request)
    db = SessionLocal()
    try:
        c = need_case(db, no)
        action = db.query(ActionItem).filter_by(case_id=c.id).first()
        if not action:
            raise AppError("Investigate the case first.", code="conflict", status=409)
        return approve_action(db, action, body.actor) | {"action": ser_action(action)}
    finally:
        db.close()


@app.post("/api/cases/{no}/execute")
def execute_case(no: int, body: ApproveBody, request: Request):
    require_key(request)
    db = SessionLocal()
    try:
        c = need_case(db, no)
        action = db.query(ActionItem).filter_by(case_id=c.id).first()
        if not action:
            raise AppError("Nothing to execute.", code="conflict", status=409)
        out = execute_action(db, action, body.actor)
        if not out.get("ok"):
            raise AppError(out.get("error", "Execution failed."), code="conflict", status=409)
        out["action"] = ser_action(action)
        out["case"] = ser_case(c)
        return out
    finally:
        db.close()


@app.get("/api/audit")
def audit_list(limit: int = 100):
    db = SessionLocal()
    try:
        rows = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(min(limit, 500)).all()
        return [{"audit_id": a.audit_id, "actor": a.actor, "event": a.event,
                 "details": a.details, "created_at": _iso(a.created_at)} for a in rows]
    finally:
        db.close()


@app.post("/api/seed/reset")
def seed_reset(request: Request):
    """Demo-only: wipe all data and reseed the three cases."""
    require_key(request)
    db = SessionLocal()
    try:
        for m in (AuditLog, ActionItem, Decision, Case, Refund, Settlement, Payment, Order, Event):
            db.query(m).delete()
        try:
            from .models import ChatMessage, ChatSession
            db.query(ChatMessage).delete()
            db.query(ChatSession).delete()
        except Exception:
            pass
        db.commit()
        opened = seed(db)
        return {"ok": True, "cases_opened": opened}
    finally:
        db.close()


# ---- assistant chat (read-only, grounded) ----

@app.post("/api/chat")
def chat_turn(body: ChatBody, request: Request):
    require_key(request)
    db = SessionLocal()
    try:
        return assistant.chat_turn(db, body.session_id, body.message)
    finally:
        db.close()


@app.get("/api/chat/{session_id}")
def chat_history(session_id: str):
    db = SessionLocal()
    try:
        s = db.query(assistant.ChatSession).filter_by(session_id=session_id).first()
        if not s:
            raise AppError("Session not found.", code="not_found", status=404)
        return {"session_id": session_id,
                "messages": [{"role": m.role, "content": m.content}
                             for m in db.query(assistant.ChatMessage)
                             .filter_by(session_id=session_id).order_by(assistant.ChatMessage.id).all()]}
    finally:
        db.close()


# ---- guidebots ----

@app.get("/api/guidebots")
def guidebot_list():
    return list_configs()


@app.post("/api/guidebots/{bot_id}/chat")
def guidebot_chat(bot_id: str, body: GuideChatBody, request: Request):
    require_key(request)
    get_config(bot_id)  # 404 early on unknown bot
    db = SessionLocal()
    try:
        return guides.guide_turn(db, bot_id, body.session_id, body.message, body.actor)
    finally:
        db.close()


@app.get("/api/guidebots/{bot_id}/chat/{session_id}")
def guidebot_history(bot_id: str, session_id: str):
    get_config(bot_id)
    db = SessionLocal()
    try:
        s = db.query(assistant.ChatSession).filter_by(
            session_id=session_id, kind=f"guidebot:{bot_id}").first()
        if not s:
            raise AppError("Session not found.", code="not_found", status=404)
        return {"session_id": session_id, "step": (s.state or {}).get("step", 0),
                "messages": [{"role": m.role, "content": m.content}
                             for m in db.query(assistant.ChatMessage)
                             .filter_by(session_id=session_id).order_by(assistant.ChatMessage.id).all()]}
    finally:
        db.close()


# ---- Serve the built frontend (single-URL demo) ----
DIST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "frontend", "dist")
DIST = os.path.abspath(DIST)
if os.path.isdir(DIST):
    assets = os.path.join(DIST, "assets")
    if os.path.isdir(assets):
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        if path.startswith(("api/", "webhooks/", "health")):
            return JSONResponse({"ok": False, "error": "Not found.", "code": "not_found"},
                                status_code=404)
        fp = os.path.join(DIST, path)
        if path and os.path.isfile(fp):
            return FileResponse(fp)
        return FileResponse(os.path.join(DIST, "index.html"))
