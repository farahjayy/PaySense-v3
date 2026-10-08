"""The synthetic-population parameter file, with provenance enforced by the loader.

Every parameter in `params.yaml` is a leaf `{value, unit, ...}` and must carry EITHER
`source: <key>` (a heading in `sources.md`, which records what the source states and what it does
not) OR `assumed: true` with a `why`. A parameter with neither, with both, or citing something
that is not in `sources.md` is an error — so an assumption can never be mistaken for a citation
(supervisor's top methodology concern; ADR D-08).
"""

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

HERE = Path(__file__).parent
DEFAULT_PARAMS_PATH = HERE / "params.yaml"
DEFAULT_SOURCES_PATH = HERE / "sources.md"
NOT_CITABLE = frozenset({"not_available"})  # a heading in sources.md that lists what is missing

_SOURCE_HEADING = re.compile(r"^##\s+([a-z0-9_]+)\s*$", re.MULTILINE)


class ParamError(ValueError):
    """The parameter file breaks the provenance rule."""


@dataclass(frozen=True)
class Param:
    path: str
    value: Any
    unit: str
    source: str | None
    assumed: bool
    why: str | None


def source_keys(path: Path = DEFAULT_SOURCES_PATH) -> set[str]:
    return set(_SOURCE_HEADING.findall(path.read_text(encoding="utf-8")))


def _is_leaf(node: Any) -> bool:
    return isinstance(node, dict) and "value" in node


def _leaf(path: str, node: dict[str, Any], keys: set[str]) -> Param:
    unknown = set(node) - {"value", "unit", "source", "assumed", "why"}
    if unknown:
        raise ParamError(f"{path}: unknown field(s) {sorted(unknown)}")
    if not isinstance(node.get("unit"), str) or not node["unit"].strip():
        raise ParamError(f"{path}: a unit is required (use 'ratio', 'count', 'sen', ...)")
    source = node.get("source")
    assumed = node.get("assumed", False)
    why = node.get("why")
    if source is not None and assumed:
        raise ParamError(f"{path}: has both a source and assumed: true; pick one")
    if source is None and not assumed:
        raise ParamError(f"{path}: needs either a source or assumed: true with a why")
    if source is not None:
        if source in NOT_CITABLE or source not in keys:
            raise ParamError(f"{path}: source {source!r} is not a citable entry in sources.md")
    elif not isinstance(why, str) or not why.strip():
        raise ParamError(f"{path}: an assumed parameter needs a non-empty 'why'")
    return Param(
        path=path,
        value=node["value"],
        unit=node["unit"],
        source=source,
        assumed=bool(assumed),
        why=why.strip() if isinstance(why, str) else None,
    )


def _walk(prefix: str, node: Any, keys: set[str], out: dict[str, Param]) -> None:
    if _is_leaf(node):
        out[prefix] = _leaf(prefix, node, keys)
    elif isinstance(node, dict):
        for name, child in node.items():
            _walk(f"{prefix}.{name}" if prefix else str(name), child, keys, out)
    else:
        raise ParamError(f"{prefix}: expected a section or a {{value, unit, ...}} leaf")


class Params:
    def __init__(self, params: dict[str, Param]) -> None:
        self._params = params

    def __getitem__(self, path: str) -> Any:
        value = self.param(path).value
        return tuple(value) if isinstance(value, list) else value  # callers cannot mutate it

    def param(self, path: str) -> Param:
        try:
            return self._params[path]
        except KeyError:
            raise KeyError(f"no such parameter: {path}") from None

    def all(self) -> list[Param]:
        return list(self._params.values())

    def assumed(self) -> list[Param]:
        return [p for p in self._params.values() if p.assumed]

    def cited(self) -> list[Param]:
        return [p for p in self._params.values() if not p.assumed]

    def hash(self) -> str:
        """Stable fingerprint of every value and its provenance (key order does not matter)."""
        canonical = {
            p.path: [p.value, p.unit, p.source, p.assumed, p.why] for p in self._params.values()
        }
        blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]

    def describe_assumptions(self) -> str:
        return "\n".join(f"- {p.path} = {p.value!r} {p.unit}: {p.why}" for p in self.assumed())


class _UniqueKeyLoader(yaml.SafeLoader):
    """SafeLoader that refuses a repeated key instead of silently keeping the last one."""

    def construct_mapping(self, node, deep=False):
        seen: set[Any] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in seen:
                raise ParamError(f"duplicate key in parameter file: {key!r}")
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


def parse_params(data: dict[str, Any], keys: set[str]) -> Params:
    out: dict[str, Param] = {}
    _walk("", data, keys, out)
    return Params(out)


def load_params(
    params_path: Path = DEFAULT_PARAMS_PATH, sources_path: Path = DEFAULT_SOURCES_PATH
) -> Params:
    data = yaml.load(params_path.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)  # noqa: S506 - SafeLoader subclass
    return parse_params(data, source_keys(sources_path))
