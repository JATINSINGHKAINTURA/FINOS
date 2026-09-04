"""Guidebot tools: every tool performs a REAL operation and reports honestly.

State-changing tools (approve/execute) additionally require a recorded user
confirmation (see engine.user_confirmed) — the policy gate still applies.
"""
from .. import ai as investigator
from .. import rules, state as st
from ..actions import approve as act_approve
from ..actions import execute as act_execute
from ..actions import log_audit, propose
from ..errors import AppError
from ..models import ActionItem, Case, Event


def _case(db, case_no: int) -> Case:
    c = db.query(Case).filter_by(case_no=int(case_no)).first()
    if not c:
        raise AppError(f"Case {case_no} not found.", code="not_found", status=404)
    return c


def tool_get_cases(db, args: dict) -> dict:
    return {"cases": [{"case_no": c.case_no, "kind": c.kind, "title": c.title, "status": c.status}
                      for c in db.query(Case).order_by(Case.case_no).all()]}


def tool_get_case(db, args: dict) -> dict:
    c = _case(db, args.get("case_no", 0))
    out = {"case_no": c.case_no, "kind": c.kind, "title": c.title,
           "summary": c.summary, "status": c.status}
    if c.order_id:
        s = st.reconstruct(db, c.order_id)["state"]
        out["facts"] = {k: s[k] for k in
                        ("order_status", "amount_due", "captured_count",
                         "captured_total", "captured_ids", "duplicate") if k in s}
    return out


def tool_investigate(db, args: dict) -> dict:
    c = _case(db, args.get("case_no", 0))
    d = investigator.investigate(db, c)
    action = propose(db, c, d)
    from .. import policy as pol
    verdict = pol.check(db, action.kind, pol.context_for_case(db, c))
    log_audit(db, "guidebot", "decision.recorded",
              {"case_no": c.case_no, "recommended_action": d.recommended_action})
    return {"diagnosis": d.diagnosis, "evidence": d.evidence, "confidence": d.confidence,
            "recommended_action": d.recommended_action, "rationale": d.rationale,
            "action_id": action.action_id, "action_kind": action.kind,
            "policy": verdict["reasons"]}


def tool_approve(db, args: dict, actor: str) -> dict:
    c = _case(db, args.get("case_no", 0))
    action = db.query(ActionItem).filter_by(case_id=c.id).first()
    if not action:
        raise AppError("Investigate the case before approving.", code="conflict", status=409)
    out = act_approve(db, action, actor)
    return {"ok": out["ok"], "action_id": action.action_id, "status": action.status,
            "reasons": out["verdict"]["reasons"]}


def tool_execute(db, args: dict, actor: str) -> dict:
    c = _case(db, args.get("case_no", 0))
    action = db.query(ActionItem).filter_by(case_id=c.id).first()
    if not action:
        raise AppError("Nothing to execute.", code="conflict", status=409)
    out = act_execute(db, action, actor)
    if not out.get("ok"):
        raise AppError(out.get("error", "Execution failed."), code="conflict", status=409)
    return {"action_id": action.action_id, "status": action.status,
            "result": action.result, "replayed": out.get("idempotent_replay", False)}


def tool_test_webhook(db, args: dict) -> dict:
    kind = str(args.get("event", "payment.captured"))
    if kind not in ("payment.captured", "payment.failed", "refund.processed"):
        raise AppError("Test event must be payment.captured, payment.failed, or refund.processed.",
                       code="validation", status=422)
    eid = f"evt-test-{db.query(Event).count() + 1}"
    db.add(Event(event_id=eid, type=kind, entity="test",
                 payload={"test": True, "note": "Fired by Webhook Helper guidebot."},
                 signature_ok=0, processed=1))
    db.commit()
    opened = rules.detect(db)
    log_audit(db, "guidebot", "webhook.test", {"event_id": eid, "type": kind, "cases_opened": opened})
    return {"event_id": eid, "type": kind, "signature_ok": False,
            "note": "Test events are ingested but never signature-verified.",
            "cases_opened": opened}


TOOLS = {
    "get_cases": tool_get_cases,
    "get_case": tool_get_case,
    "investigate": tool_investigate,
    "approve": tool_approve,
    "execute": tool_execute,
    "test_webhook": tool_test_webhook,
}
STATE_CHANGING = {"approve", "execute"}
