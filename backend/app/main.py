"""FINOS API: webhook ingest -> state -> investigate -> approve -> execute -> audit."""
import json
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import ai as investigator
from . import policy as pol
from . import razorpay as rz
from . import rules
from . import state as st
from .actions import approve as approve_action
from .actions import execute as execute_action
from .actions import log_audit, propose
from .db import Base, SessionLocal, engine
from .models import ActionItem, AuditLog, Case, Decision, Event, Order, Payment, Refund, Settlement
from .seed import seed


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        seed(db)
    finally:
        db.close()
    yield


app = FastAPI(title="FINOS", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


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
    actor: str = "judge"


@app.get("/health")
def health():
    return {"ok": True, "dry_run": rz.DRY_RUN}


@app.post("/webhooks/razorpay")
async def razorpay_webhook(request: Request):
    body = await request.body()
    try:
        payload = json.loads(body or b"{}")
    except Exception:
        return JSONResponse({"ok": False, "error": "Invalid JSON"}, status_code=400)
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
        c = db.query(Case).filter_by(case_no=no).first()
        if not c:
            return JSONResponse({"error": "Case not found"}, status_code=404)
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
def investigate_case(no: int):
    db = SessionLocal()
    try:
        c = db.query(Case).filter_by(case_no=no).first()
        if not c:
            return JSONResponse({"error": "Case not found"}, status_code=404)
        d = investigator.investigate(db, c)
        action = propose(db, c, d)
        verdict = pol.check(db, action.kind, pol.context_for_case(db, c))
        log_audit(db, "system", "decision.recorded",
                  {"case_no": no, "diagnosis": d.diagnosis, "recommended_action": d.recommended_action})
        return {"decision": ser_decision(d), "action": ser_action(action), "policy": verdict}
    finally:
        db.close()


@app.post("/api/cases/{no}/approve")
def approve_case(no: int, body: ApproveBody):
    db = SessionLocal()
    try:
        c = db.query(Case).filter_by(case_no=no).first()
        if not c:
            return JSONResponse({"error": "Case not found"}, status_code=404)
        action = db.query(ActionItem).filter_by(case_id=c.id).first()
        if not action:
            return JSONResponse({"error": "Investigate the case first."}, status_code=409)
        return approve_action(db, action, body.actor) | {"action": ser_action(action)}
    finally:
        db.close()


@app.post("/api/cases/{no}/execute")
def execute_case(no: int, body: ApproveBody):
    db = SessionLocal()
    try:
        c = db.query(Case).filter_by(case_no=no).first()
        if not c:
            return JSONResponse({"error": "Case not found"}, status_code=404)
        action = db.query(ActionItem).filter_by(case_id=c.id).first()
        if not action:
            return JSONResponse({"error": "Nothing to execute."}, status_code=409)
        out = execute_action(db, action, body.actor)
        if not out.get("ok"):
            return JSONResponse(out, status_code=409)
        out["action"] = ser_action(action)
        out["case"] = ser_case(c)
        return out
    finally:
        db.close()


@app.get("/api/audit")
def audit_list(limit: int = 100):
    db = SessionLocal()
    try:
        rows = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(limit).all()
        return [{"audit_id": a.audit_id, "actor": a.actor, "event": a.event,
                 "details": a.details, "created_at": _iso(a.created_at)} for a in rows]
    finally:
        db.close()


@app.post("/api/seed/reset")
def seed_reset():
    """Demo-only: wipe all data and reseed the three cases."""
    db = SessionLocal()
    try:
        for m in (AuditLog, ActionItem, Decision, Case, Refund, Settlement, Payment, Order, Event):
            db.query(m).delete()
        db.commit()
        opened = seed(db)
        return {"ok": True, "cases_opened": opened}
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
            return JSONResponse({"error": "Not found"}, status_code=404)
        fp = os.path.join(DIST, path)
        if path and os.path.isfile(fp):
            return FileResponse(fp)
        return FileResponse(os.path.join(DIST, "index.html"))
