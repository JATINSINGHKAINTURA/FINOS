"""Chat, guidebots, validation, auth guard, rate limiting."""
import os
import tempfile

_fd, _DB = tempfile.mkstemp(suffix=".db")
os.environ["FINOS_DB"] = _DB

from fastapi.testclient import TestClient  # noqa: E402

import app.auth as authmod  # noqa: E402
import app.ratelimit as rlmod  # noqa: E402
from app.main import app  # noqa: E402


def fresh():
    c = TestClient(app)
    c.__enter__()
    c.post("/api/seed/reset")
    return c


def test_chat_and_validation():
    with fresh() as c:
        r = c.post("/api/chat", json={"message": "list cases"}).json()
        assert "1042" in r["reply"] and r["session_id"]
        sid = r["session_id"]
        r2 = c.post("/api/chat", json={"session_id": sid, "message": "explain case 1042"}).json()
        assert r2["session_id"] == sid and "P-456" in r2["reply"]
        hist = c.get(f"/api/chat/{sid}").json()
        assert len(hist["messages"]) == 4
        assert c.post("/api/chat", json={"message": ""}).status_code == 422
        assert c.post("/api/chat", json={"message": "x" * 2001}).status_code == 422
        assert c.get("/api/chat/nope").status_code == 404


def test_case_pilot_full_flow():
    with fresh() as c:
        assert len(c.get("/api/guidebots").json()) == 2
        assert c.post("/api/guidebots/nope/chat", json={"message": "hi"}).status_code == 404
        s = c.post("/api/guidebots/case-pilot/chat", json={"message": "hi"}).json()
        sid = s["session_id"]
        assert s["step"] == 0
        # confirmation cannot be skipped: EXECUTE at step 0 must not execute anything
        early = c.post("/api/guidebots/case-pilot/chat",
                       json={"session_id": sid, "message": "EXECUTE"}).json()
        assert early["step"] == 0 and not early["tool_results"]
        g = lambda m: c.post("/api/guidebots/case-pilot/chat",
                             json={"session_id": sid, "message": m}).json()
        assert "1042" in g("1042")["reply"]
        inv = g("YES")
        assert any(t["tool"] == "investigate" and t["ok"] for t in inv["tool_results"])
        appr = g("APPROVE")
        assert any(t["tool"] == "approve" and t["data"]["ok"] for t in appr["tool_results"])
        ex = g("EXECUTE")
        assert any(t["tool"] == "execute" and t["data"]["status"] == "executed"
                   for t in ex["tool_results"])
        assert ex["done"] is True
        hist = c.get(f"/api/guidebots/case-pilot/chat/{sid}").json()
        assert len(hist["messages"]) >= 10
        # executed actions are immutable: re-approve refused, re-execute replays
        again_a = c.post("/api/cases/1042/approve", json={"actor": "judge"}).json()
        assert again_a["ok"] is False
        again_e = c.post("/api/cases/1042/execute", json={"actor": "judge"}).json()
        assert again_e["ok"] is True and again_e["idempotent_replay"] is True


def test_webhook_helper():
    with fresh() as c:
        s = c.post("/api/guidebots/webhook-helper/chat",
                   json={"message": "fire payment.captured"}).json()
        assert any(t["tool"] == "test_webhook" and t["ok"] for t in s["tool_results"])
        assert "signature_ok=false" in s["reply"] or "signature" in s["reply"]


def test_auth_guard_and_rate_limit():
    with fresh() as c:
        authmod.API_KEY = "s3cret"
        try:
            r = c.post("/api/cases/1042/investigate")
            assert r.status_code == 401 and r.json()["code"] == "unauthorized"
            ok = c.post("/api/cases/1042/investigate", headers={"x-api-key": "s3cret"})
            assert ok.status_code == 200
        finally:
            authmod.API_KEY = ""
        rlmod.CHAT_PER_MIN = 2
        try:
            c.post("/api/chat", json={"message": "hi"})
            c.post("/api/chat", json={"message": "hi"})
            r = c.post("/api/chat", json={"message": "hi"})
            assert r.status_code == 429 and r.json()["code"] == "rate_limited"
        finally:
            rlmod.CHAT_PER_MIN = 30
