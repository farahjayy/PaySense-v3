"""Runs one tool call for the model or for guided mode: refuse what policy forbids, validate the
arguments with the tool's own model, run the handler, and describe what happened as a step.

A failure never escapes as an exception: a refused call, invalid arguments or an error from the
shared function become a step with that status and a plain sentence, which is also what the
model is told.
"""

import logging
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException
from pydantic import ValidationError

from app.api.assistant import StepOut
from app.assistant import policy
from app.assistant.context import ToolContext
from app.assistant.tools import MODEL_TOOLS

logger = logging.getLogger("paysense")
MAX_ARGUMENT_CHARS = 20_000  # a tool call this large is not a real request


@dataclass(frozen=True)
class StepRecord:
    step: StepOut
    card: Any | None = None
    data: Any = None  # what the model is shown as the tool result
    pending_action: Any | None = None


def _refused(name: str, tier: int, args: Any, why: str) -> StepRecord:
    shown = args if isinstance(args, dict) else {}
    return StepRecord(StepOut(tool=name, tier=tier, status="refused", inputs=shown, summary=why))


def _validation_text(err: ValidationError) -> str:
    first = err.errors()[0]
    where = ".".join(str(p) for p in first["loc"]) or "arguments"
    return f"The arguments were not valid ({where}: {first['msg']})."


def run_tool(ctx: ToolContext, name: str, args: Any, *, caller: policy.Caller) -> StepRecord:
    tool = MODEL_TOOLS.get(name)
    if tool is None:
        return _refused(name, 2, args, f"There is no tool called {name!r} that I may use.")
    if not policy.allowed(tool.tier, caller):
        return _refused(name, tool.tier, args, "That tool changes data; only you can do that.")
    if not isinstance(args, dict):
        return _refused(name, tool.tier, {}, "Tool arguments must be an object.")
    if len(repr(args)) > MAX_ARGUMENT_CHARS:
        return _refused(name, tool.tier, {}, "Those arguments are too large.")
    if policy.names_a_user(args):
        return _refused(
            name, tool.tier, args, "Tool arguments cannot name a user; I only see your own data."
        )
    try:
        parsed = tool.input_model.model_validate(args)
    except ValidationError as err:
        return StepRecord(
            StepOut(tool=name, tier=tool.tier, status="error", inputs=args,
                    summary=_validation_text(err))
        )  # fmt: skip
    inputs = parsed.model_dump(mode="json", exclude_none=True)
    try:
        out = tool.handler(ctx, parsed)
    except HTTPException as err:
        detail = err.detail if isinstance(err.detail, dict) else {"message": str(err.detail)}
        return StepRecord(
            StepOut(tool=name, tier=tool.tier, status="error", inputs=inputs,
                    summary=str(detail.get("message", "That did not work.")))
        )  # fmt: skip
    except Exception:
        logger.exception("assistant tool %s failed", name)
        return StepRecord(
            StepOut(tool=name, tier=tool.tier, status="error", inputs=inputs,
                    summary="That did not work on our side.")
        )  # fmt: skip
    return StepRecord(
        step=StepOut(tool=name, tier=tool.tier, status="ok", inputs=inputs, summary=out.summary),
        card=out.card,
        data=out.data,
        pending_action=out.pending_action,
    )
