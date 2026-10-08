"""Money helpers. Money is integer sen everywhere (ADR D-16); ringgit text is parsed exactly.

Nothing here (or anywhere in `app/domain/`) multiplies a float by 100: amounts are read from the
*text* a person typed, so 19.99 is 1999 sen and not 1998.9999999999998.
"""

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

SEN_PER_RM = 100
_HUNDREDTH = Decimal("0.01")
# Optional "RM", then 1,234 / 1234, then an optional .5 or .50 — nothing else (no sign, no
# parentheses, no third decimal), because a silently guessed amount is worse than a rejected one.
_RM_TEXT = re.compile(r"^(?:RM\s*)?(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{1,2}))?$", re.IGNORECASE)


def parse_rm(text: str) -> int:
    """Ringgit text -> integer sen. Raises ValueError for anything ambiguous."""
    match = _RM_TEXT.match(text.strip()) if isinstance(text, str) else None
    if match is None:
        raise ValueError(f"not a valid amount: {text!r} (use e.g. 12.50 or RM 1,234.50)")
    whole = int(match.group(1).replace(",", ""))
    cents = int((match.group(2) or "0").ljust(2, "0"))
    return whole * SEN_PER_RM + cents


def format_rm(sen: int) -> str:
    """Integer sen -> 'RM 1,234.56' (negative: '-RM 2.50')."""
    whole, cents = divmod(abs(sen), SEN_PER_RM)
    sign = "-" if sen < 0 else ""
    return f"{sign}RM {whole:,}.{cents:02d}"


def percent_to_hundredths(rate: str | int | float | Decimal) -> int:
    """A percentage (1.5 = 1.5%) -> hundredths of a percent (150), rounded half up."""
    try:
        value = Decimal(str(rate)).quantize(_HUNDREDTH, ROUND_HALF_UP)
    except InvalidOperation as err:
        raise ValueError(f"not a valid rate: {rate!r}") from err
    if value < 0:
        raise ValueError(f"rate cannot be negative: {rate!r}")
    return int(value * 100)
