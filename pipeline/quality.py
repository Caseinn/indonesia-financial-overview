"""Quality gates that decide whether a Source may be promoted to Gold.

Checks run on a batch before promotion and classify each breach as a WARN
(record it, alert, let data flow) or a Circuit Breaker (quarantine the Source and
halt Gold). Thresholds come from ``indicators.yml``; the gates never edit a
value, they only flag it, because real economic shocks exist.
(ADR-0006)
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from enum import StrEnum

from pipeline.config import IndicatorsConfig
from pipeline.models import Observation
from pipeline.ops import SourceRunRecord

VANISH_RATIO = 0.30


class Severity(StrEnum):
    """How severe a quality breach is."""

    WARN = "warn"
    BREAKER = "breaker"


@dataclass(frozen=True, slots=True)
class Finding:
    """One quality breach for one Indicator (or the batch as a whole)."""

    severity: Severity
    code: str
    message: str
    indicator_code: str = ""
    period_start: date | None = None


@dataclass(frozen=True, slots=True)
class QualityReport:
    """The findings of one gate run and whether promotion must halt."""

    findings: tuple[Finding, ...]

    @property
    def warns(self) -> tuple[Finding, ...]:
        return tuple(item for item in self.findings if item.severity is Severity.WARN)

    @property
    def breakers(self) -> tuple[Finding, ...]:
        return tuple(item for item in self.findings if item.severity is Severity.BREAKER)

    @property
    def has_breaker(self) -> bool:
        return any(item.severity is Severity.BREAKER for item in self.findings)


def evaluate(
    observations: tuple[Observation, ...],
    config: IndicatorsConfig,
    previous_values: Mapping[tuple[object, ...], float] | None = None,
) -> QualityReport:
    """Run every quality check over one Source batch and collect the findings.

    ``previous_values`` maps a business key to its currently published value, so
    drift is measured against what Gold already shows rather than against a
    neighbouring row.
    """
    findings: list[Finding] = []
    findings.extend(_check_identity(observations, config))
    findings.extend(_check_duplicates(observations))
    findings.extend(_check_drift(observations, config, previous_values or {}))
    findings.extend(_check_vanishing(observations, previous_values or {}, config))
    return QualityReport(findings=tuple(findings))


def evaluate_freshness(
    config: IndicatorsConfig,
    latest: Mapping[str, SourceRunRecord],
    *,
    now: datetime | None = None,
    source_ids: Iterable[str] | None = None,
) -> QualityReport:
    """Flag Sources whose last Source Run failed or fell behind their cadence.

    Freshness is advisory: a late or unhealthy Source keeps showing its last good
    value in Gold, so a breach never quarantines the batch or empties the dashboard.
    Sources without a recorded run yet are skipped, because a first deploy has no
    history to judge.
    """
    moment = _as_utc(now) if now is not None else datetime.now(UTC)
    findings: list[Finding] = []
    for source_id in source_ids if source_ids is not None else config.sources:
        source = config.sources.get(source_id)
        if source is None or source.cadence.refresh_days is None:
            continue
        record = latest.get(source_id)
        if record is None:
            continue
        if record.status != "ok":
            findings.append(_freshness(source_id, "source_unhealthy", f"last run {record.status}"))
            continue
        age = moment - _as_utc(record.finished_at)
        if age > timedelta(days=source.cadence.refresh_days):
            findings.append(
                _freshness(
                    source_id,
                    "stale_source",
                    f"last success {age.days} days ago, cadence {source.cadence.refresh_days} days",
                )
            )
    return QualityReport(findings=tuple(findings))


def _check_identity(
    observations: tuple[Observation, ...], config: IndicatorsConfig
) -> list[Finding]:
    findings: list[Finding] = []
    for observation in observations:
        if observation.indicator_code not in config.indicators:
            findings.append(
                _finding(
                    Severity.BREAKER,
                    observation,
                    "unknown_indicator",
                    f"{observation.indicator_code} is not in the indicator config",
                )
            )
            continue
        expected = config.indicators[observation.indicator_code]
        if observation.normalized_unit != expected.unit:
            findings.append(
                _finding(
                    Severity.BREAKER,
                    observation,
                    "unit_drift",
                    f"{observation.indicator_code} unit {observation.normalized_unit!r} "
                    f"!= config {expected.unit!r}",
                )
            )
        if observation.frequency != expected.frequency:
            findings.append(
                _finding(
                    Severity.BREAKER,
                    observation,
                    "frequency_drift",
                    f"{observation.indicator_code} frequency {observation.frequency!r} "
                    f"!= config {expected.frequency!r}",
                )
            )
        if observation.normalized_value is None or math.isnan(observation.normalized_value):
            findings.append(
                _finding(
                    Severity.BREAKER,
                    observation,
                    "null_value",
                    f"{observation.indicator_code} has a null value",
                )
            )
    return findings


def _check_duplicates(observations: tuple[Observation, ...]) -> list[Finding]:
    seen: set[tuple[object, ...]] = set()
    duplicates: set[tuple[object, ...]] = set()
    for observation in observations:
        if observation.business_key in seen:
            duplicates.add(observation.business_key)
        seen.add(observation.business_key)
    return [
        Finding(
            severity=Severity.BREAKER,
            code="duplicate_grain",
            message=f"business key {key} appears more than once in one batch",
        )
        for key in sorted(duplicates, key=repr)
    ]


def _check_drift(
    observations: tuple[Observation, ...],
    config: IndicatorsConfig,
    previous_values: Mapping[tuple[object, ...], float],
) -> list[Finding]:
    findings: list[Finding] = []
    for observation in observations:
        previous = previous_values.get(observation.business_key)
        if previous is None or observation.indicator_code not in config.indicators:
            continue
        rule = config.indicators[observation.indicator_code].drift
        if rule is None:
            continue
        measure = _measure(rule.warn.type, previous, observation.normalized_value)
        if measure > rule.circuit_breaker.value:
            severity = Severity.BREAKER
        elif measure > rule.warn.value:
            severity = Severity.WARN
        else:
            continue
        findings.append(
            _finding(
                severity,
                observation,
                "value_drift",
                f"{observation.indicator_code} moved {previous} -> "
                f"{observation.normalized_value} ({measure:.2f} {rule.warn.type})",
            )
        )
    return findings


def _check_vanishing(
    observations: tuple[Observation, ...],
    previous_values: Mapping[tuple[object, ...], float],
    config: IndicatorsConfig,
) -> list[Finding]:
    """Flag a batch that drops most rows the Source already published.

    Only rows for Indicators this Source still publishes count: a series retired
    from ``indicators.yml`` is expected to stop appearing, while a configured
    series disappearing from the batch is real data loss.
    """
    if not observations or not previous_values:
        return []
    source_id = observations[0].source_id
    configured = {
        code for code, indicator in config.indicators.items() if indicator.source == source_id
    }
    new_keys = {observation.business_key for observation in observations}
    span_start = min(observation.period_start for observation in observations)
    span_end = max(observation.period_start for observation in observations)
    prior = {
        key
        for key in previous_values
        if key[0] == source_id and key[2] in configured and span_start <= key[3] <= span_end
    }
    if not prior:
        return []
    missing = prior - new_keys
    if len(missing) / len(prior) <= VANISH_RATIO:
        return []
    return [
        Finding(
            severity=Severity.BREAKER,
            code="vanishing_rows",
            message=f"{len(missing)} of {len(prior)} previously published rows vanished",
        )
    ]


def _measure(kind: str, old: float, new: float) -> float:
    delta = abs(new - old)
    if kind == "relative":
        return float("inf") if old == 0 else delta / abs(old)
    if kind == "absolute_bp":
        return delta * 100
    return delta


def _finding(severity: Severity, observation: Observation, code: str, message: str) -> Finding:
    return Finding(
        severity=severity,
        code=code,
        message=message,
        indicator_code=observation.indicator_code,
        period_start=observation.period_start,
    )


def _freshness(source_id: str, code: str, detail: str) -> Finding:
    return Finding(severity=Severity.WARN, code=code, message=f"{source_id} {detail}")


def _as_utc(moment: datetime) -> datetime:
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)
