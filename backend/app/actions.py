"""Guarded action layer: propose -> approve (policy) -> execute (idempotent)."""
from . import policy as pol
from . import razorpay as rz
from .models import ActionItem, AuditLog, Case, Refund


def log_audit(db, actor: str, event: str, details: dict) -> AuditLog:
    n = db.query(AuditLog).count() + 1
    row = AuditLog(audit_id=f"AUD-{n:06d}", actor=actor, event=event, details=details)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def propose(db, case: Case, decision) -> ActionItem:
    kind = decision.recommended_action
    ctx = pol.context_for_case(db, case)
    if kind == "refund":
        target = ctx.get("refund_payment_id", case.payment_id)
        params = {"payment_id": target, "amount": ctx.get("amount", 0)}
        key = f"{case.case_no}:refund:{target}:{params['amount']}"
    elif kind == "flag_review":
        params = {"case_no": case.case_no}
        key = f"{case.case_no}:flag_review"
    else:
        kind = "no_action"
        params = {}
        key = f"{case.case_no}:no_action"
    existing = db.query(ActionItem).filter_by(idempotency_key=key).first()
    if existing:
        return existing
    action = ActionItem(action_id=f"ACT-{case.case_no}", case_id=case.id, kind=kind,
                        status="proposed", idempotency_key=key, params=params, result={})
    db.add(action)
    case.status = "awaiting_approval"
    db.commit()
    db.refresh(action)
    log_audit(db, "system", "action.proposed",
              {"action_id": action.action_id, "kind": kind, "params": params})
    return action


def approve(db, action: ActionItem, actor: str = "reviewer") -> dict:
    case = db.query(Case).filter_by(id=action.case_id).first()
    verdict = pol.check(db, action.kind, pol.context_for_case(db, case))
    if not verdict["allowed"]:
        action.status = "blocked"
        db.commit()
        log_audit(db, actor, "action.blocked",
                  {"action_id": action.action_id, "reasons": verdict["reasons"]})
        return {"ok": False, "verdict": verdict}
    action.status = "approved"
    case.status = "approved"
    db.commit()
    log_audit(db, actor, "action.approved",
              {"action_id": action.action_id, "reasons": verdict["reasons"]})
    return {"ok": True, "verdict": verdict}


def execute(db, action: ActionItem, actor: str = "reviewer") -> dict:
    if action.status == "executed":
        return {"ok": True, "idempotent_replay": True, "result": action.result}
    if action.status != "approved":
        return {"ok": False, "error": "Action must be approved before execution."}
    case = db.query(Case).filter_by(id=action.case_id).first()
    if action.kind == "no_action":
        result = {"outcome": "Resolved without financial movement."}
    elif action.kind == "flag_review":
        result = {"outcome": "Flagged for finance review. No money moved."}
    elif action.kind == "refund":
        p = action.params
        r = rz.create_refund(p["payment_id"], p["amount"],
                             notes={"case": str(case.case_no), "reason": "duplicate_payment"})
        db.add(Refund(refund_id=r["id"], payment_id=p["payment_id"], amount=p["amount"],
                      status=r.get("status", "processed"), reason="duplicate_payment",
                      dry_run=1 if r.get("dry_run") else 0))
        result = {"outcome": f"Refund {r['id']} {r.get('status')}.", "refund": r,
                  "dry_run": bool(r.get("dry_run"))}
    else:
        return {"ok": False, "error": f"Unknown action kind {action.kind}"}
    action.result = result
    action.status = "executed"
    case.status = "resolved"
    db.commit()
    log_audit(db, actor, "action.executed", {"action_id": action.action_id, **result})
    return {"ok": True, "idempotent_replay": False, "result": result}
