"""Load and validate ``config/indicators.yml``.

Indicator codes, units, frequencies, normalization rules, drift thresholds, and
Regimes live in one YAML file, so adapters and quality gates read this module
instead of hardcoding strings. Loading fails loudly on malformed or
self-inconsistent config, catching drift at startup rather than mid-run.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from types import MappingProxyType
from typing import Any

import yaml

from pipeline.parsing import ParseError, parse_date

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "indicators.yml"


class ConfigError(ValueError):
    """Raised when ``indicators.yml`` is malformed or self-inconsistent."""


@dataclass(frozen=True, slots=True)
class DriftThreshold:
    """One drift bound, interpreted by ``type`` (relative or absolute)."""

    type: str
    value: float


@dataclass(frozen=True, slots=True)
class DriftRule:
    """The WARN and Circuit Breaker bounds for one Indicator."""

    warn: DriftThreshold
    circuit_breaker: DriftThreshold


@dataclass(frozen=True, slots=True)
class Regime:
    """A named date range over which an Indicator's definition stayed constant."""

    label: str
    source_code: str
    valid_from: date
    valid_to: date | None


@dataclass(frozen=True, slots=True)
class Cadence:
    """Expected publication timing for a Source."""

    frequency: str | None = None
    release_lag_days: int | None = None
    probe_start_day: int | None = None
    probe_end_day: int | None = None


@dataclass(frozen=True, slots=True)
class SourceConfig:
    """A Source's channel, artifact kind, and cadence."""

    source_id: str
    name: str
    artifact: str
    url: str
    cadence: Cadence


@dataclass(frozen=True, slots=True)
class GeographyConfig:
    """One geography Gold can attribute an Indicator to."""

    code: str
    name: str
    is_national: bool = False


@dataclass(frozen=True, slots=True)
class IndicatorConfig:
    """Everything the pipeline knows about one Indicator."""

    code: str
    name: str
    unit: str
    frequency: str
    source: str
    geography: str = "IDN"
    source_table: str | None = None
    source_sheets: tuple[str, ...] = ()
    source_sheet: str | None = None
    source_parent: str | None = None
    source_row: str | None = None
    source_domain: str | None = None
    source_var: int | None = None
    source_vervar: int | None = None
    source_turvar: int | None = None
    source_catalog: str | None = None
    source_cube: str | None = None
    source_measure: str | None = None
    source_member: str | None = None
    source_dimension: str | None = None
    source_mdx: str | None = None
    role: str | None = None
    valid_from: date | None = None
    valid_to: date | None = None
    drift: DriftRule | None = None
    regimes: tuple[Regime, ...] = ()


@dataclass(frozen=True, slots=True)
class IndicatorsConfig:
    """The parsed ``indicators.yml``, with frozen lookups by code and id."""

    sources: Mapping[str, SourceConfig]
    indicators: Mapping[str, IndicatorConfig]
    geographies: Mapping[str, GeographyConfig]

    def indicator(self, code: str) -> IndicatorConfig:
        """Return the Indicator config, raising ``ConfigError`` if unknown."""
        try:
            return self.indicators[code]
        except KeyError as exc:
            raise ConfigError(f"unknown indicator code: {code}") from exc

    def source(self, source_id: str) -> SourceConfig:
        """Return the Source config, raising ``ConfigError`` if unknown."""
        try:
            return self.sources[source_id]
        except KeyError as exc:
            raise ConfigError(f"unknown source_id: {source_id}") from exc


def load_config(path: Path | str = DEFAULT_CONFIG_PATH) -> IndicatorsConfig:
    """Read, parse, and validate the indicators config file."""
    path = Path(path)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"config file not found: {path}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"config root must be a mapping: {path}")

    sources = _parse_sources(raw.get("sources") or {})
    indicators = _parse_indicators(raw.get("indicators") or {})
    geographies = _parse_geographies(raw.get("geography") or {})
    for code, indicator in indicators.items():
        if indicator.source not in sources:
            raise ConfigError(f"indicator {code} references unknown source {indicator.source!r}")
        if indicator.geography not in geographies:
            raise ConfigError(
                f"indicator {code} references unknown geography {indicator.geography!r}"
            )
        _validate_binding(code, indicator)

    return IndicatorsConfig(
        sources=MappingProxyType(sources),
        indicators=MappingProxyType(indicators),
        geographies=MappingProxyType(geographies),
    )


_OJK_PORTAL_FIELDS = ("source_measure", "source_cube")


def _validate_binding(code: str, indicator: IndicatorConfig) -> None:
    """Fail when an Indicator lacks the fields its Source adapter reads.

    Each adapter binds differently, so an absent field would otherwise surface
    only mid-run; for BI SEKI a missing ``source_table`` would be silently
    skipped. Adapters pull indicator codes from config, so the binding rules
    live here beside the shape they guard.
    """
    missing: list[str] = []
    if indicator.source == "BI_SEKI":
        missing = [
            name
            for name in ("source_table", "source_sheets", "source_row")
            if not getattr(indicator, name)
        ]
    elif indicator.source == "BPS":
        if indicator.source_var is None:
            missing = ["source_var"]
    elif indicator.source == "OJK_SPI":
        portal = bool(indicator.source_mdx) or all(
            getattr(indicator, name) for name in _OJK_PORTAL_FIELDS
        )
        edition = bool(indicator.source_sheet and indicator.source_row)
        if not (portal or edition):
            missing = ["source_mdx or source_measure/source_cube or source_sheet/source_row"]
    if missing:
        raise ConfigError(
            f"indicator {code} (source {indicator.source}) lacks binding fields: "
            f"{', '.join(missing)}"
        )


def _parse_geographies(raw: Mapping[str, Any]) -> dict[str, GeographyConfig]:
    if not raw:
        return {"IDN": GeographyConfig(code="IDN", name="Indonesia", is_national=True)}
    geographies: dict[str, GeographyConfig] = {}
    for code, node in raw.items():
        if not isinstance(node, Mapping):
            raise ConfigError(f"geography {code!r} must be a mapping")
        geographies[code] = GeographyConfig(
            code=code,
            name=str(node.get("name", code)),
            is_national=bool(node.get("is_national", False)),
        )
    if "IDN" not in geographies:
        raise ConfigError("geography must define IDN")
    return geographies


def _parse_sources(raw: Mapping[str, Any]) -> dict[str, SourceConfig]:
    sources: dict[str, SourceConfig] = {}
    for source_id, node in raw.items():
        if not isinstance(node, Mapping):
            raise ConfigError(f"source {source_id!r} must be a mapping")
        cadence_raw = node.get("cadence") or {}
        window = cadence_raw.get("probe_window") or {}
        sources[source_id] = SourceConfig(
            source_id=source_id,
            name=str(node.get("name", source_id)),
            artifact=str(node.get("artifact", "")),
            url=str(node.get("url", "")),
            cadence=Cadence(
                frequency=cadence_raw.get("frequency"),
                release_lag_days=cadence_raw.get("release_lag_days"),
                probe_start_day=window.get("start_day"),
                probe_end_day=window.get("end_day"),
            ),
        )
    return sources


def _parse_indicators(raw: Mapping[str, Any]) -> dict[str, IndicatorConfig]:
    indicators: dict[str, IndicatorConfig] = {}
    for code, node in raw.items():
        if not isinstance(node, Mapping):
            raise ConfigError(f"indicator {code!r} must be a mapping")
        regimes = tuple(_parse_regime(code, item) for item in node.get("regimes") or [])
        indicators[code] = IndicatorConfig(
            code=code,
            name=str(_require(node, "name", code)),
            unit=str(_require(node, "unit", code)),
            frequency=str(_require(node, "frequency", code)),
            source=str(_require(node, "source", code)),
            geography=str(node.get("geography", "IDN")),
            source_table=_opt_str(node.get("source_table")),
            source_sheets=_parse_sheets(node, code),
            source_sheet=_opt_str(node.get("source_sheet")),
            source_parent=_opt_str(node.get("source_parent")),
            source_row=_opt_str(node.get("source_row")),
            source_domain=_opt_str(node.get("source_domain")),
            source_var=_opt_int(node.get("source_var"), f"{code}.source_var"),
            source_vervar=_opt_int(node.get("source_vervar"), f"{code}.source_vervar"),
            source_turvar=_opt_int(node.get("source_turvar"), f"{code}.source_turvar"),
            source_catalog=_opt_str(node.get("source_catalog")),
            source_cube=_opt_str(node.get("source_cube")),
            source_measure=_opt_str(node.get("source_measure")),
            source_member=_opt_str(node.get("source_member")),
            source_dimension=_opt_str(node.get("source_dimension")),
            source_mdx=_opt_str(node.get("source_mdx")),
            role=_opt_str(node.get("role")),
            valid_from=_opt_date(node.get("valid_from"), f"{code}.valid_from"),
            valid_to=_opt_date(node.get("valid_to"), f"{code}.valid_to"),
            drift=_parse_drift(code, node.get("drift")),
            regimes=regimes,
        )
    return indicators


def _parse_regime(code: str, node: Mapping[str, Any]) -> Regime:
    valid_from = _opt_date(node.get("valid_from"), f"{code}.regime.valid_from")
    if valid_from is None:
        raise ConfigError(f"indicator {code}: regime requires valid_from")
    return Regime(
        label=str(_require(node, "label", code)),
        source_code=str(_require(node, "source_code", code)),
        valid_from=valid_from,
        valid_to=_opt_date(node.get("valid_to"), f"{code}.regime.valid_to"),
    )


def _parse_drift(code: str, raw: Mapping[str, Any] | None) -> DriftRule | None:
    if raw is None:
        return None

    def threshold(kind: str) -> DriftThreshold:
        node = raw.get(kind)
        if not isinstance(node, dict) or "type" not in node or "value" not in node:
            raise ConfigError(f"indicator {code}: drift.{kind} must set type and value")
        return DriftThreshold(type=str(node["type"]), value=float(node["value"]))

    return DriftRule(warn=threshold("warn"), circuit_breaker=threshold("circuit_breaker"))


def _require(node: Mapping[str, Any], key: str, code: str) -> Any:
    if key not in node:
        raise ConfigError(f"indicator {code}: missing required field {key!r}")
    return node[key]


def _parse_sheets(node: Mapping[str, Any], code: str) -> tuple[str, ...]:
    value = node.get("source_sheets", node.get("source_sheet"))
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list):
        return tuple(str(item) for item in value)
    raise ConfigError(f"indicator {code}: source_sheets must be a string or list")


def _opt_str(value: Any) -> str | None:
    return None if value is None else str(value)


def _opt_int(value: Any, field_name: str) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"invalid integer for {field_name}: {value!r}") from exc


def _opt_date(value: Any, field_name: str) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        parsed = parse_date(str(value))
    except ParseError as exc:
        raise ConfigError(f"invalid date for {field_name}: {value!r}") from exc
    if parsed is None:
        raise ConfigError(f"invalid date for {field_name}: {value!r}")
    return parsed
