"""Exception/rule engine: verified facts -> cases. No LLM involved here."""
from .actions import log_audit
from .models import Case, Event, Order, Payment, Settlement


def _open_case(db, kind, title, summary, order_id="", payment_id=""):
    q = db.query(Case).filter_by(kind=kind, order_id=order_id, status="open").first()
    if q:
        return None
    no = 1042 + db.query(Case).count()
    case = Case(case_no=no, kind=kind, title=title, summary=summary,
               order_id=order_id, payment_id=payment_id)
    db.add(case)
    db.commit()
    db.refresh(case)
    log_audit(db, "system", "case.opened",
              {"case_no": no, "kind": kind, "title": title})
    return case


def detect(db) -> list:
    """Scan facts, open cases for the three MVP exception types."""
    opened = []
    # 1. Ambiguous: checkout timed out but a payment got captured, no order.paid
    timeout_orders = set()
    paid_orders = set()
    for e in db.query(Event).all():
        blob = str(e.payload or {})
        for o in db.query(Order).all():
            if o.order_id in blob:
                if e.type == "checkout.timeout":
                    timeout_orders.add(o.order_id)
                if e.type == "order.paid":
                    paid_orders.add(o.order_id)
    for oid in timeout_orders - paid_orders:
        caps = [p for p in db.query(Payment).filter_by(order_id=oid).all()
                if p.status == "captured" or p.captured]
        if caps:
            c = _open_case(db, "ambiguous",
                           f"Ambiguous payment on {oid}",
                           "Checkout response was not delivered, but a payment was captured.",
                           order_id=oid, payment_id=caps[0].payment_id)
            if c:
                opened.append(c.case_no)
    # 2. Duplicate: 2+ captured payments on one order
    for o in db.query(Order).all():
        caps = [p for p in db.query(Payment).filter_by(order_id=o.order_id).all()
                if p.status == "captured" or p.captured]
        if len(caps) >= 2:
            c = _open_case(db, "duplicate",
                           f"Possible duplicate payment on {o.order_id}",
                           f"{len(caps)} captured payments on one order.",
                           order_id=o.order_id, payment_id=caps[-1].payment_id)
            if c:
                opened.append(c.case_no)
    # 3. Settlement anomaly: expected != actual + fees + tax (tolerance ₹1)
    for s in db.query(Settlement).all():
        unexplained = s.amount_expected - s.amount_actual - s.fees - s.tax
        if abs(unexplained) >= 100:
            dup = db.query(Case).filter(Case.kind == "settlement",
                                        Case.title.like(f"%{s.settlement_id}%")).first()
            if not dup:
                c = _open_case(db, "settlement",
                               f"Settlement anomaly {s.settlement_id}",
                               f"Unexplained difference of {unexplained} paise.",
                               order_id="", payment_id="")
                if c:
                    opened.append(c.case_no)
    return opened
