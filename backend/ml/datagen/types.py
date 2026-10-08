"""Plain data the generator passes around. Money is integer sen; dates are `datetime.date`."""

from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True)
class Txn:
    """One transaction in the app's own vocabulary (`app.db.transactions` / the CSV importer)."""

    date: date
    amount_sen: int  # always positive; `type` carries the direction
    type: str  # income | expense | savings
    category: str
    description: str
    bnpl_plan_key: str | None = None  # set on payments that settle a generated BNPL plan

    def as_row(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "amount_sen": self.amount_sen,
            "type": self.type,
            "category": self.category,
            "description": self.description,
        }


@dataclass(frozen=True)
class RecurringTruth:
    """The generator's own record of a recurring item: the answer key for recurring detection."""

    name: str
    kind: str  # income | bill
    amount_sen: int
    cadence: str  # weekly | biweekly | monthly | semester | custom
    anchor_date: date
