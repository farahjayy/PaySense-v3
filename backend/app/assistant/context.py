"""Who a tool runs for, and when. `user_id` comes from the session only (ADR D-48): it is never a
tool argument, and the executor refuses any argument that tries to name a user."""

from dataclasses import dataclass
from datetime import date
from typing import Any

from app.core.settings import Settings


@dataclass(frozen=True)
class ToolContext:
    db: Any
    user_id: str
    today: date
    settings: Settings
    predictor: Any = None  # the risk model; None when no artefact is loaded
    # this turn's pasted text, from the server's own copy of the request (import by chat, WP4d);
    # tools ground what the model read against it, never against the model's arguments
    pasted_text: str | None = None

    @property
    def forecaster(self) -> Any:
        from app.engines.forecasting.serving import served_forecaster

        return served_forecaster()
