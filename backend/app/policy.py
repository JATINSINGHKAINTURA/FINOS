"""Policy gate: sensitive actions pass checks before approval/execution."""
from . import state as st


def check(db, kind: str, ctx: dict) -> dict:
    """Pure check. Returns {allowed, requires_approval, reasons[]}."""
    if kind == "no_action":
        return {"allowed": True, "requires_approval": True,
                "reasons": ["No money moves. Approval only records the decision."]}
    if kind == "refund":
        reasons = []
        if not ctx.get("duplicate_confirmed"):
            reasons.append("Refund blocked: duplicate not confirmed from captured payments.")
            return {"allowed": False, "requires_approval": True, "reasons": reasons}
        if ctx.get("amount", 0) > ctx.get("excess", 0):
            reasons.append("Refund blocked: amount exceeds the excess captured.")
            return {"allowed": False, "requires_approval": True, "reasons": reasons}
        reasons.append(f"Duplicate confirmed ({ctx.get('captured_count')} captured). "
                       f"Refund {ctx.get('amount')} <= excess {ctx.get('excess')}.")
        if ctx.get("dry_run", True):
            reasons.append("Dry-run mode: no real money will move.")
        return {"allowed": True, "requires_approval": True, "reasons": reasons}
    if kind == "flag_review":
        return {"allowed": True, "requires_approval": True,
                "reasons": ["Read-only flag for finance review. No money moves."]}
    return {"allowed": False, "requires_approval": True, "reasons": [f"Unknown action kind: {kind}"]}


def context_for_case(db, case) -> dict:
    from . import razorpay as rz
    ctx = {"dry_run": rz.DRY_RUN}
    if case.order_id:
        s = st.reconstruct(db, case.order_id)["state"]
        ctx.update({
            "duplicate_confirmed": s["duplicate"],
            "captured_count": s["captured_count"],
            "excess": max(0, s["captured_total"] - s["amount_due"]),
        })
        if s["duplicate"]:
            from .models import Payment
            caps = [p for p in db.query(Payment).filter_by(order_id=case.order_id).all()
                    if p.status == "captured" or p.captured]
            caps.sort(key=lambda p: p.created_at or "")
            if len(caps) >= 2:
                ctx["refund_payment_id"] = caps[-1].payment_id
                ctx["amount"] = caps[-1].amount
    return ctx
