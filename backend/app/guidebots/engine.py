"""Guidebot engine: Registry → Config → AI/script → Tools → Context → Response.

Two drivers share one tool dispatcher and one confirmation rule:
- script_turn: deterministic step machine (no API key needed, demo always works)
- llm_turn: DeepSeek with a strict JSON contract (richer conversation)

Server-side rule: approve/execute tools run ONLY after the user explicitly
confirmed the specific proposed action (state['proposed'] + yes-pattern).
The model cannot bypass this — the engine checks, not the prompt.
"""
import json

import httpx

from .. import chat as chatmod
from ..ai import BASE_URL, API_KEY, MODEL
from ..errors import AppError
from .registry import get_config
from .tools import STATE_CHANGING, TOOLS

YES = {"yes", "y", "yeah", "yep", "confirm", "confirmed", "approve", "approved",
       "do it", "go ahead", "proceed", "ok", "okay", "execute", "run it", "sure"}


def user_says_yes(text: str) -> bool:
    return text.strip().lower() in YES


def user_confirmed(state: dict, tool_name: str, args: dict, user_text: str) -> bool:
    """True only if the same action was proposed before AND the user said yes."""
    prop = (state or {}).get("proposed") or {}
    if tool_name not in STATE_CHANGING:
        return True
    return (user_says_yes(user_text)
            and prop.get("kind") == tool_name
            and str(prop.get("case_no")) == str(args.get("case_no", "")))


def run_tool(db, cfg, name: str, args: dict, actor: str, state: dict, user_text: str) -> dict:
    if name not in TOOLS or name not in cfg.tools:
        raise AppError(f"Tool '{name}' is not available to this guidebot.", code="validation", status=422)
    if name in STATE_CHANGING and not user_confirmed(state, name, args, user_text):
        return {"blocked": True,
                "message": f"I need your explicit confirmation first — reply YES to {name} "
                           f"case {args.get('case_no')}."}
    fn = TOOLS[name]
    try:
        if name in STATE_CHANGING or name == "investigate":
            return {"ok": True, "data": fn(db, args, actor) if name in STATE_CHANGING else fn(db, args)}
        return {"ok": True, "data": fn(db, args)}
    except AppError as e:
        return {"ok": False, "error": e.message}


def _save_state(db, sess, state: dict):
    sess.state = state
    db.commit()


# ---------------- scripted driver (no key) ----------------

def _case_no_in(text: str):
    for n in ("1042", "1043", "1044"):
        if n in text:
            return int(n)
    return None


def script_turn(db, cfg, sess, msg: str, actor: str) -> dict:
    state = dict(sess.state or {})
    step = state.get("step", 0)
    suggestions: list[str] = []
    tool_results: list[dict] = []

    if cfg.id == "case-pilot":
        if step == 0:
            n = _case_no_in(msg)
            if n:
                state.update({"case_no": n, "step": 1})
                r = run_tool(db, cfg, "get_case", {"case_no": n}, actor, state, msg)
                facts = r.get("data", {})
                reply = (f"Case #{n}: {facts.get('title')}. Facts: {facts.get('facts', {})}. "
                         f"Shall I run the AI investigation? Reply YES.")
                suggestions = ["YES", "Show all cases"]
            else:
                r = run_tool(db, cfg, "get_cases", {}, actor, state, msg)
                cases = "; ".join(f"#{c['case_no']} {c['title']} ({c['status']})"
                                  for c in r["data"]["cases"])
                reply = (f"I'm Case Pilot. We'll go: facts → investigate → approve → execute. "
                         f"Which case? {cases}")
                suggestions = ["1042", "1043", "1044"]
        elif step == 1:
            if user_says_yes(msg):
                r = run_tool(db, cfg, "investigate", {"case_no": state["case_no"]}, actor, state, msg)
                tool_results.append({"tool": "investigate", **r})
                d = r["data"]
                state.update({"step": 2, "proposed": {"kind": "approve",
                                                      "case_no": state["case_no"]}})
                reply = (f"Diagnosis: {d['diagnosis']} Evidence: {' | '.join(d['evidence'])} "
                         f"Recommended: {d['recommended_action']} ({d['action_id']}). "
                         f"Reply APPROVE to approve it.")
                suggestions = ["APPROVE", "Show evidence"]
            else:
                reply = "Reply YES and I'll run the investigation, or pick another case number."
                suggestions = ["YES", "1042", "1043", "1044"]
        elif step == 2:
            if "approv" in msg.lower() or user_says_yes(msg):
                r = run_tool(db, cfg, "approve", {"case_no": state["case_no"]}, actor, state, msg)
                if r.get("blocked"):
                    reply = r["message"]
                    suggestions = ["APPROVE"]
                elif not r.get("data", {}).get("ok", False):
                    reply = ("Approval refused: "
                             + " | ".join(r["data"].get("reasons", ["not allowed"])))
                    suggestions = ["Show all cases"]
                else:
                    tool_results.append({"tool": "approve", **r})
                    state.update({"step": 3, "proposed": {"kind": "execute",
                                                          "case_no": state["case_no"]}})
                    reply = (f"Approved ({r['data']['action_id']}). Policy: "
                             f"{' | '.join(r['data']['reasons'])} Reply EXECUTE to run it.")
                    suggestions = ["EXECUTE"]
            else:
                reply = "Reply APPROVE when you're ready — nothing has been approved yet."
                suggestions = ["APPROVE"]
        elif step == 3:
            if "execut" in msg.lower() or user_says_yes(msg):
                r = run_tool(db, cfg, "execute", {"case_no": state["case_no"]}, actor, state, msg)
                if r.get("blocked"):
                    reply = r["message"]
                    suggestions = ["EXECUTE"]
                elif not r.get("ok", False):
                    reply = f"Execution failed: {r.get('error', 'not allowed')}"
                    suggestions = ["Show all cases"]
                else:
                    tool_results.append({"tool": "execute", **r})
                    state.update({"step": 4, "proposed": {}, "done": True})
                    res = r["data"]["result"]
                    reply = (f"Done. Case #{state['case_no']} resolved — "
                             f"{res.get('outcome', '')} Audit: {r['data']['action_id']}.")
                    suggestions = ["Show all cases"]
            else:
                reply = "Reply EXECUTE to run the approved action, or stop here — nothing has moved."
                suggestions = ["EXECUTE"]
        else:
            reply = "This case is resolved. Pick another case number to guide again."
            suggestions = ["1042", "1043", "1044"]
            state = {"step": 0}

    elif cfg.id == "webhook-helper":
        if step == 0:
            if any(k in msg.lower() for k in ("captured", "failed", "refund", "test", "yes", "fire")):
                kind = "payment.failed" if "failed" in msg.lower() else \
                    "refund.processed" if "refund" in msg.lower() else "payment.captured"
                r = run_tool(db, cfg, "test_webhook", {"event": kind}, actor, state, msg)
                tool_results.append({"tool": "test_webhook", **r})
                d = r["data"]
                state.update({"step": 1})
                reply = (f"Fired {d['event_id']} ({d['type']}). Ingested with signature_ok=false — "
                         f"test events are never trusted. Cases opened: {d['cases_opened'] or 'none'}. "
                         f"For production: set RAZORPAY_WEBHOOK_SECRET and point your Razorpay "
                         f"webhook URL at POST /webhooks/razorpay (HMAC-SHA256, header "
                         f"x-razorpay-signature).")
                suggestions = ["Fire another test", "Show all cases"]
            else:
                reply = ("FINOS ingests Razorpay events at POST /webhooks/razorpay, verifies HMAC-SHA256 "
                         "when a secret is configured, and re-runs exception detection. Want me to "
                         "fire a real test event? Say “fire payment.captured”.")
                suggestions = ["Fire payment.captured", "Fire payment.failed"]
        else:
            if "fire" in msg.lower() or "another" in msg.lower() or "test" in msg.lower():
                state = {"step": 0}
                return script_turn(db, cfg, sess, "fire " + msg, actor)
            reply = "Done here. Ask me anything else about webhooks, or try Case Pilot."
            suggestions = ["Fire payment.captured"]
    else:
        reply = "This guidebot has no scripted flow yet."
    _save_state(db, sess, state)
    done = bool(state.get("done", False))
    return {"reply": reply, "suggestions": suggestions, "tool_results": tool_results,
            "step": state.get("step", 0), "done": done}


# ---------------- LLM driver ----------------

LLM_SYSTEM = """You guide the user through a workflow step by step as a FINOS guidebot.
Rules:
1. NEVER claim an action (investigate/approve/execute/test event) completed unless the turn's tool result proves it.
2. Propose approve/execute only after showing the user what will happen; the engine enforces explicit YES confirmation.
3. Reply with JSON ONLY: {"reply": str, "suggestions": [str], "tool": {"name": str, "args": {}} | null, "set_state": {}}.
4. Use tools instead of guessing data. Keep replies short."""


def llm_turn(db, cfg, sess, hist: list, msg: str, actor: str) -> dict:
    state = dict(sess.state or {})
    try:
        r = httpx.post(
            f"{BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {API_KEY}"},
            json={"model": MODEL, "temperature": 0.2, "response_format": {"type": "json_object"},
                  "messages": [
                      {"role": "system",
                       "content": LLM_SYSTEM + f"\nGuidebot: {cfg.name}. {cfg.system_extra}\n"
                                              f"Steps: {cfg.steps}\nTools: {cfg.tools}\n"
                                              f"Current state: {json.dumps(state)}"},
                      *hist[-10:],
                      {"role": "user", "content": msg}]},
            timeout=60,
        )
        r.raise_for_status()
        data = json.loads(r.json()["choices"][0]["message"]["content"])
    except Exception:
        return script_turn(db, cfg, sess, msg, actor)
    tool_results = []
    tool = data.get("tool")
    if isinstance(tool, dict) and tool.get("name"):
        res = run_tool(db, cfg, tool["name"], tool.get("args", {}), actor, state, msg)
        tool_results.append({"tool": tool["name"], **res})
        if res.get("blocked"):
            data["reply"] = res["message"]
    if isinstance(data.get("set_state"), dict):
        state.update(data["set_state"])
    _save_state(db, sess, state)
    return {"reply": str(data.get("reply", "…")),
            "suggestions": list(data.get("suggestions", []))[:4],
            "tool_results": tool_results,
            "step": state.get("step", 0), "done": bool(data.get("done", False))}


def guide_turn(db, bot_id: str, session_id: str | None, message: str, actor: str = "user") -> dict:
    cfg = get_config(bot_id)
    msg = chatmod.clean(message)
    sess = chatmod.get_session(db, f"guidebot:{bot_id}", session_id)
    hist = chatmod.history(db, sess.session_id)
    chatmod.save_message(db, sess.session_id, "user", msg)
    if API_KEY:
        out = llm_turn(db, cfg, sess, hist, msg, actor)
    else:
        out = script_turn(db, cfg, sess, msg, actor)
    chatmod.save_message(db, sess.session_id, "assistant", out["reply"])
    return {"session_id": sess.session_id, "bot": {"id": cfg.id, "name": cfg.name,
                                                  "steps": cfg.steps}, **out}
