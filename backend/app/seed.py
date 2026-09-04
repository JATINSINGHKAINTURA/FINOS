"""Demo seed: the three judge cases. Idempotent — safe to run repeatedly."""
from .actions import log_audit
from .models import Case, Event, Order, Payment, Settlement
from . import rules


def _ev(db, eid, typ, payload, verified=True):
    if db.query(Event).filter_by(event_id=eid).first():
        return
    db.add(Event(event_id=eid, type=typ, entity="internal",
                 payload=payload, signature_ok=1 if verified else 0, processed=1))
    db.commit()


def seed(db):
    if db.query(Case).count():
        return []
    # ---- Case 1042: ambiguous payment (O-123 / P-456) ----
    db.add(Order(order_id="O-123", amount=499900, currency="INR", receipt="rcpt-123",
                 status="created", customer_email="customer@example.com"))
    db.add(Payment(payment_id="P-456", order_id="O-123", amount=499900,
                   currency="INR", method="upi", status="captured", captured=1))
    db.commit()
    _ev(db, "evt_1042_1", "order.created", {"order": {"id": "O-123", "amount": 499900}})
    _ev(db, "evt_1042_2", "payment.created", {"payment": {"id": "P-456", "order_id": "O-123"}})
    _ev(db, "evt_1042_3", "payment.authorized", {"payment": {"id": "P-456", "order_id": "O-123"}})
    _ev(db, "evt_1042_4", "payment.captured",
        {"payment": {"id": "P-456", "order_id": "O-123", "amount": 499900, "status": "captured"}})
    _ev(db, "evt_1042_5", "checkout.timeout",
        {"order_id": "O-123", "note": "Customer/browser did not receive the final response."}, verified=False)
    # ---- Case 1043: duplicate payment (O-124 / P-457 + P-458) ----
    db.add(Order(order_id="O-124", amount=249900, currency="INR", receipt="rcpt-124",
                 status="paid", customer_email="customer@example.com"))
    db.add(Payment(payment_id="P-457", order_id="O-124", amount=249900,
                   currency="INR", method="card", status="captured", captured=1))
    db.add(Payment(payment_id="P-458", order_id="O-124", amount=249900,
                   currency="INR", method="card", status="captured", captured=1))
    db.commit()
    _ev(db, "evt_1043_1", "payment.captured",
        {"payment": {"id": "P-457", "order_id": "O-124", "amount": 249900, "status": "captured"}})
    _ev(db, "evt_1043_2", "payment.captured",
        {"payment": {"id": "P-458", "order_id": "O-124", "amount": 249900, "status": "captured"}})
    _ev(db, "evt_1043_3", "order.paid", {"order": {"id": "O-124"}})
    # ---- Case 1044: settlement anomaly (S-789) ----
    db.add(Settlement(settlement_id="S-789", amount_expected=749700, amount_actual=744900,
                      fees=4100, tax=400, reference="STL-789-HDFC", status="settled"))
    db.commit()
    _ev(db, "evt_1044_1", "settlement.processed",
        {"settlement": {"id": "S-789", "amount_expected": 749700, "amount_actual": 744900,
                        "fees": 4100, "tax": 400, "reference": "STL-789-HDFC"}}, verified=False)
    opened = rules.detect(db)
    log_audit(db, "system", "seed.completed", {"cases_opened": opened})
    return opened
