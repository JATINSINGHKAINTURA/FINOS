"""Payment-state reconstruction: facts come from verified events/data only.

The LLM never invents financial truth — it only explains this state.
"""
from .models import Event, Order, Payment, Refund, Settlement


def _iso(dt):
    return dt.isoformat() if dt else None


def timeline_for_order(db, order_id: str) -> list:
    items = []
    for p in db.query(Payment).filter_by(order_id=order_id).all():
        items.append((p.created_at, f"Payment {p.payment_id}", f"status={p.status} amount={p.amount}"))
    for e in db.query(Event).all():
        pl = e.payload or {}
        blob = str(pl)
        if order_id in blob:
            items.append((e.received_at, e.type, f"entity={e.entity} verified={bool(e.signature_ok)}"))
    items.sort(key=lambda x: x[0] or "")
    return [{"at": _iso(t), "label": label, "detail": detail} for t, label, detail in items]


def reconstruct(db, order_id: str) -> dict:
    order = db.query(Order).filter_by(order_id=order_id).first()
    payments = db.query(Payment).filter_by(order_id=order_id).all()
    captured = [p for p in payments if p.status == "captured" or p.captured]
    refunds = []
    for p in payments:
        refunds += db.query(Refund).filter_by(payment_id=p.payment_id).all()
    state = {
        "order_id": order_id,
        "order_status": order.status if order else "unknown",
        "amount_due": order.amount if order else 0,
        "payments_total": len(payments),
        "captured_count": len(captured),
        "captured_total": sum(p.amount for p in captured),
        "captured_ids": [p.payment_id for p in captured],
        "refunded_total": sum(r.amount for r in refunds),
        "duplicate": len(captured) >= 2,
    }
    return {
        "state": state,
        "order": {"order_id": order.order_id, "amount": order.amount, "status": order.status} if order else None,
        "payments": [
            {"payment_id": p.payment_id, "amount": p.amount, "status": p.status, "method": p.method}
            for p in payments
        ],
        "refunds": [{"refund_id": r.refund_id, "amount": r.amount, "status": r.status} for r in refunds],
        "timeline": timeline_for_order(db, order_id),
    }


def settlement_math(db, settlement_id: str) -> dict:
    s = db.query(Settlement).filter_by(settlement_id=settlement_id).first()
    if not s:
        return {}
    unexplained = s.amount_expected - s.amount_actual - s.fees - s.tax
    return {
        "settlement_id": s.settlement_id,
        "expected": s.amount_expected,
        "actual": s.amount_actual,
        "fees": s.fees,
        "tax": s.tax,
        "reference": s.reference,
        "unexplained": unexplained,
    }
