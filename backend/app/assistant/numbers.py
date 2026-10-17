"""The number check (ADR D-47): every figure in the model's narration must come from this turn's
tool results, the server's own step summaries, or the user's current message. Otherwise the
narration is replaced by a template. Earlier turns are not a source: they come from the client.
"""

import re
from collections.abc import Iterable
from typing import Any

# Any run of digits not continuing another number: "RM450" and "x2" are read as 450 and 2, so a
# figure glued to a currency or a word cannot slip past the check.
NUMBER = re.compile(r"(?<![\d.,])\d[\d,]*(?:\.\d+)?")
DATE = re.compile(r"^(\d{4})-(\d{2})(?:-(\d{2}))?")
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
    forms = {normalise(f"{value:.6f}"), normalise(str(round(value)))}
    for digits in (1, 2):
        forms.add(normalise(f"{value:.{digits}f}"))
    if key.endswith("_sen"):
        ringgit = abs(value) / 100
        forms |= {normalise(f"{ringgit:.2f}"), normalise(str(round(ringgit)))}
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


def allowed_figures(results: Iterable[Any], texts: Iterable[str]) -> set[str]:
    allowed: set[str] = set()
    for result in results:
        allowed |= figures_of(result)
    for text in texts:
        allowed |= {normalise(t) for t in NUMBER.findall(text or "")}
    return allowed


def unsupported(narration: str, allowed: set[str]) -> list[str]:
    """Figures in the narration that no source supports."""
    bad = []
    for token in NUMBER.findall(narration):
        figure = normalise(token)
        if figure.isdigit() and int(figure) <= FREE_UP_TO:
            continue
        if figure not in allowed:
            bad.append(token)
    return bad
