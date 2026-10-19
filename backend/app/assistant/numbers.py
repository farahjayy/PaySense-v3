"""The number check (ADR D-47): every figure in the model's narration must come from this turn's
tool results, the server's own step summaries, or the user's current message. Otherwise the
narration is replaced by a template. Earlier turns are not a source: they come from the client.
"""

import re
from collections.abc import Iterable
from decimal import Decimal
from typing import Any

# Any run of digits not continuing another number: "RM450" and "x2" are read as 450 and 2, so a
# figure glued to a currency or a word cannot slip past the check. ".75" is read as 0.75.
NUMBER = re.compile(r"(?<![\d.,])(?:\d[\d,]*(?:\.\d+)?|(?<![A-Za-z])\.\d+)")
# A figure with a scale word is checked at its full value: "5k" is 5000, never a free small count.
SCALE = re.compile(r"\s*(k|thousand|ribu|mil|million|juta|bn|billion)\b", re.IGNORECASE)
MULTIPLIER = {"k": 10**3, "thousand": 10**3, "ribu": 10**3, "mil": 10**6, "million": 10**6,
              "juta": 10**6, "bn": 10**9, "billion": 10**9}  # fmt: skip
DATE = re.compile(r"(\d{4})-(\d{2})(?:-(\d{2}))?")
# ASSUMED 28 (WP4c): whole numbers up to 12 need no source — counts such as "3 instalments" or
# "2 plans", which the model may say in words or digits.
FREE_UP_TO = 12


def normalise(token: str) -> str:
    """'1,234.50' -> '1234.5'; '12.00' -> '12'; '007' -> '7'."""
    text = token.replace(",", "")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    text = text.lstrip("0") or "0"
    return "0" + text if text.startswith(".") else text


def _number_forms(value: float, key: str) -> set[str]:
    # A sen field is only ever written in ringgit: its raw value would let a 100x error pass.
    if key.endswith("_sen"):
        ringgit = abs(value) / 100
        return {normalise(f"{ringgit:.2f}"), normalise(str(round(ringgit)))}
    forms = {normalise(f"{value:.6f}"), normalise(str(round(value)))}
    for digits in (1, 2):
        forms.add(normalise(f"{value:.{digits}f}"))
    if 0 <= abs(value) <= 1 and isinstance(value, float):
        percent = abs(value) * 100
        forms |= {normalise(str(round(percent))), normalise(f"{percent:.1f}")}
    if value < 0:
        forms |= _number_forms(-value, key)
    return forms


def figures_of(value: Any, key: str = "") -> set[str]:
    """Every way a figure in a tool result may legitimately be written in a sentence."""
    found: set[str] = set()
    if isinstance(value, bool) or value is None:
        return found
    if isinstance(value, int | float):
        return _number_forms(float(value) if isinstance(value, float) else value, key)
    if isinstance(value, str):
        match = DATE.match(value)
        if match:
            found |= {normalise(g) for g in match.groups() if g}
        found |= {normalise(t) for t in NUMBER.findall(value)}
        return found
    if isinstance(value, dict):
        for k, v in value.items():
            found |= figures_of(v, str(k))
        return found
    if isinstance(value, list | tuple):
        for v in value:
            found |= figures_of(v, key)
    return found


def written_figures(text: str) -> list[tuple[str, str, bool]]:
    """(as written, normalised value, scaled?) for every figure in a sentence."""
    found = []
    for match in NUMBER.finditer(text or ""):
        figure = normalise(match.group())
        scale = SCALE.match(text, match.end())
        if scale:
            value = Decimal(figure) * MULTIPLIER[scale.group(1).lower()]
            found.append((match.group() + scale.group(), normalise(f"{value:f}"), True))
        else:
            found.append((match.group(), figure, False))
    return found


def argument_figures(value: Any, key: str = "") -> set[str]:
    """Figures the model itself wrote into its tool arguments. Dates are left out: a date passed
    to a tool is validated by it and the results' dates are computed from it."""
    if isinstance(value, str) and DATE.fullmatch(value):
        return set()
    found: set[str] = set()
    if isinstance(value, dict):
        for k, v in value.items():
            found |= argument_figures(v, str(k))
    elif isinstance(value, list | tuple):
        for v in value:
            found |= argument_figures(v, key)
    else:
        found = figures_of(value, key)
    return found


def allowed_figures(
    results: Iterable[Any],
    texts: Iterable[str],
    *,
    echoed: set[str] | None = None,
    trusted: Iterable[str] = (),
) -> set[str]:
    """Figures in the results and texts, minus those that only echo the model's own arguments
    (`echoed`) unless the person wrote them (`trusted`: their message and paste)."""
    allowed: set[str] = set()
    for result in results:
        allowed |= figures_of(result)
    for text in texts:
        allowed |= {figure for _, figure, _ in written_figures(text)}
    allowed -= echoed or set()
    for text in trusted:
        allowed |= {figure for _, figure, _ in written_figures(text)}
    return allowed


def unsupported(narration: str, allowed: set[str]) -> list[str]:
    """Figures in the narration that no source supports."""
    bad = []
    for written, figure, scaled in written_figures(narration):
        if not scaled and figure.isdigit() and int(figure) <= FREE_UP_TO:
            continue
        if figure not in allowed:
            bad.append(written)
    return bad
