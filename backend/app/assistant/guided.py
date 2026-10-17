"""Guided mode (ADR D-47): the same tools, run from buttons and small forms, with no model. The
reply is the step's own sentence, so guided mode can never say a number a tool did not give."""

from typing import Any

from app.api.assistant import ChatOut
from app.assistant import executor
from app.assistant.context import ToolContext


def chat_out_from(records: list[executor.StepRecord], reply: str, **extra: Any) -> ChatOut:
    return ChatOut(
        reply=reply,
        mode=extra.get("mode", "guided"),
        provider=extra.get("provider"),
        model=extra.get("model"),
        steps=[r.step for r in records],
        cards=[r.card for r in records if r.card is not None],
        pending_actions=[r.pending_action for r in records if r.pending_action is not None],
        narration_replaced=extra.get("narration_replaced", False),
        refused=extra.get("refused", any(r.step.status == "refused" for r in records)),
    )


def run_guided(ctx: ToolContext, tool: str, arguments: dict[str, Any]) -> ChatOut:
    record = executor.run_tool(ctx, tool, arguments, caller="guided")
    return chat_out_from([record], record.step.summary)
