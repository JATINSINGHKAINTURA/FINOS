"""End-to-end: seed -> 3 cases -> investigate -> approve -> execute -> audit."""
import os
import tempfile

_fd, _DB = tempfile.mkstemp(suffix=".db")
os.environ["FINOS_DB"] = _DB

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def test_full_flow():
    with TestClient(app) as c:
        assert c.get("/health").json()["ok"] is True
        nos = sorted(x["case_no"] for x in c.get("/api/cases").json())
        assert nos == [1042, 1043, 1044]

        # --- Case 1042: ambiguous -> no_action ---
        d = c.post("/api/cases/1042/investigate").json()
        assert d["decision"]["recommended_action"] == "no_action"
        assert "P-456" in d["decision"]["evidence"][0]
        assert c.post("/api/cases/1042/approve", json={"actor": "judge"}).json()["ok"] is True
        e = c.post("/api/cases/1042/execute", json={"actor": "judge"}).json()
        assert e["ok"] is True
        assert e["case"]["status"] == "resolved"

        # --- Case 1043: duplicate -> refund (dry-run), idempotent replay ---
        d = c.post("/api/cases/1043/investigate").json()
        assert d["decision"]["recommended_action"] == "refund"
        assert c.post("/api/cases/1043/approve", json={"actor": "judge"}).json()["ok"] is True
        e1 = c.post("/api/cases/1043/execute", json={"actor": "judge"}).json()
        assert e1["ok"] is True and e1["idempotent_replay"] is False
        e2 = c.post("/api/cases/1043/execute", json={"actor": "judge"}).json()
        assert e2["ok"] is True and e2["idempotent_replay"] is True
        assert e2["result"] == e1["result"]

        # --- Case 1044: settlement -> flag_review ---
        d = c.post("/api/cases/1044/investigate").json()
        assert d["decision"]["recommended_action"] == "flag_review"
        assert c.post("/api/cases/1044/approve", json={"actor": "judge"}).json()["ok"] is True
        assert c.post("/api/cases/1044/execute", json={"actor": "judge"}).json()["ok"] is True

        # --- Webhook: unverified sender still ingested, flagged ---
        w = c.post("/webhooks/razorpay",
                   json={"id": "evt_test_1", "event": "payment.failed", "entity": "event",
                         "payload": {"payment": {"entity": {"id": "P-999", "order_id": "O-123"}}}}).json()
        assert w["ok"] is True and w["signature_ok"] is False

        audit = c.get("/api/audit").json()
        events = {a["event"] for a in audit}
        assert {"case.opened", "decision.recorded", "action.proposed",
                "action.approved", "action.executed"} <= events
