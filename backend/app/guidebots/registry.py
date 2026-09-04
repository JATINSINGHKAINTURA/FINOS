"""Guidebot registry: task-oriented assistants. Add new ones here —
no other file changes needed (engine + tools are generic)."""
from dataclasses import dataclass

from ..errors import AppError


@dataclass(frozen=True)
class GuidebotConfig:
    id: str
    name: str
    tagline: str
    description: str
    steps: list
    tools: list
    system_extra: str


GUIDE_BOTS: dict[str, GuidebotConfig] = {
    "case-pilot": GuidebotConfig(
        id="case-pilot",
        name="Case Pilot",
        tagline="Resolve a payment case with me, step by step",
        description=("Picks a case, reviews verified facts, runs the AI investigation, "
                     "walks through approval, and executes — with your confirmation at each gate."),
        steps=["Choose case", "Review facts", "Investigate", "Review diagnosis",
               "Approve", "Execute", "Done"],
        tools=["get_cases", "get_case", "investigate", "approve", "execute"],
        system_extra=("Guide the user through resolving ONE case. Never claim an action "
                      "was done unless a tool just reported it. Require explicit user "
                      "confirmation before approve/execute tools."),
    ),
    "webhook-helper": GuidebotConfig(
        id="webhook-helper",
        name="Webhook Helper",
        tagline="Understand and test Razorpay event ingestion",
        description=("Explains how FINOS ingests and verifies Razorpay webhooks, fires a real "
                     "test event on request, and shows how to configure a production webhook."),
        steps=["Explain ingestion", "Fire test event", "Show result", "Production setup", "Done"],
        tools=["test_webhook", "get_cases"],
        system_extra=("Teach webhook ingestion. You may fire a test event only when the user "
                      "asks. Always report the tool's real result, including signature status."),
    ),
}


def list_configs() -> list:
    return [{"id": c.id, "name": c.name, "tagline": c.tagline,
             "description": c.description, "steps": c.steps} for c in GUIDE_BOTS.values()]


def get_config(bot_id: str) -> GuidebotConfig:
    if bot_id not in GUIDE_BOTS:
        raise AppError("Unknown guidebot.", code="not_found", status=404)
    return GUIDE_BOTS[bot_id]
