"""The pre/post decision-switch table: who changed their choice, and in which direction.

Direction is measured against the risk ranking written in `uat/vignettes.yaml`: a lower rank after
seeing the risk check is "safer". Counts only; with a handful of testers a p-value would overstate.
"""

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from ml.uat.load import Choice, UatDataError, Vignette


@dataclass(frozen=True)
class SwitchRow:
    vignette: str
    title: str
    n: int  # testers with both a before and an after answer
    same: int
    safer: int
    riskier: int
    transitions: tuple[tuple[str, str, int], ...]  # (before option, after option, testers)
    confidence_before: float | None
    confidence_after: float | None

    @property
    def switched(self) -> int:
        return self.safer + self.riskier


def switch_table(choices: Iterable[Choice], vignettes: Mapping[str, Vignette]) -> list[SwitchRow]:
    by_key: dict[tuple[str, str], dict[str, Choice]] = {}
    for c in choices:
        by_key.setdefault((c.vignette, c.participant), {})[c.phase] = c

    rows: list[SwitchRow] = []
    for vid, vignette in vignettes.items():
        pairs = [
            (phases["pre"], phases["post"])
            for (v, _), phases in by_key.items()
            if v == vid and "pre" in phases and "post" in phases
        ]
        transitions: Counter[tuple[str, str]] = Counter((a.option, b.option) for a, b in pairs)
        safer = same = riskier = 0
        for a, b in pairs:
            before = vignette.option(a.option)
            after = vignette.option(b.option)
            if before is None or after is None:
                raise UatDataError(f"{vid}: answer is not one of the vignette's options")
            if after.risk_rank < before.risk_rank:
                safer += 1
            elif after.risk_rank > before.risk_rank:
                riskier += 1
            else:
                same += 1
        rows.append(
            SwitchRow(
                vignette=vid,
                title=vignette.title,
                n=len(pairs),
                same=same,
                safer=safer,
                riskier=riskier,
                transitions=tuple((a, b, n) for (a, b), n in sorted(transitions.items())),
                confidence_before=_mean([a.confidence for a, _ in pairs]),
                confidence_after=_mean([b.confidence for _, b in pairs]),
            )
        )
    return rows


def _mean(values: list[int]) -> float | None:
    return sum(values) / len(values) if values else None
