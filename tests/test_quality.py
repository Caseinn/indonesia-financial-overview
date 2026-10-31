"""Quality gate behaviour: identity, duplicates, drift tiers, and vanishing."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from pipeline.config import load_config
from pipeline.models import Observation
from pipeline.ops import SourceRunRecord
from pipeline.quality import Severity, evaluate, evaluate_freshness

TS = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)
CONFIG = load_config()


def obs(
    *,
    code: str = "POLICY_RATE",
    period_start: date = date(2022, 6, 1),
    value: float = 3.5,
    unit: str = "percent_per_annum",
    frequency: str = "monthly",
    dimension_code: str = "",
) -> Observation:
    return Observation(
        source_id="BI_SEKI",
        source_table="TABEL1_25_1",
        indicator_code=code,
        period_start=period_start,
        period_end=period_start,
        frequency=frequency,
        geography_code="IDN",
        original_value=value,
        original_unit=unit,
        normalized_value=value,
        normalized_unit=unit,
        source_raw_label="x",
        retrieved_at=TS,
        source_file_sha256="a" * 64,
        ingestion_run_id="run-1",
        dimension_code=dimension_code,
    )


def codes(report) -> set[str]:
    return {finding.code for finding in report.findings}


def test_clean_batch_has_no_findings() -> None:
    report = evaluate((obs(value=3.5),), CONFIG)

    assert report.findings == ()
    assert report.has_breaker is False


def test_unknown_indicator_is_a_breaker() -> None:
    report = evaluate((obs(code="NOPE"),), CONFIG)

    assert report.has_breaker is True
    assert "unknown_indicator" in codes(report)


def test_unit_drift_is_a_breaker() -> None:
    report = evaluate((obs(unit="wrong_unit"),), CONFIG)

    assert "unit_drift" in codes(report)


def test_frequency_drift_is_a_breaker() -> None:
    report = evaluate((obs(frequency="daily"),), CONFIG)

    assert "frequency_drift" in codes(report)
    assert report.has_breaker is True


def test_duplicate_grain_is_a_breaker() -> None:
    report = evaluate((obs(), obs()), CONFIG)

    assert "duplicate_grain" in codes(report)


def test_rate_drift_tiers_by_basis_points() -> None:
    base = obs(value=4.0)
    previous = {base.business_key: 4.0}

    assert evaluate((obs(value=4.20),), CONFIG, previous).findings == ()

    warned = evaluate((obs(value=4.30),), CONFIG, previous)
    assert [finding.severity for finding in warned.findings] == [Severity.WARN]

    broken = evaluate((obs(value=9.01),), CONFIG, previous)
    assert broken.has_breaker is True


def test_relative_drift_uses_config_ratio() -> None:
    base = obs(code="USDIRR_JISDOR", value=14000.0, unit="idr_per_usd", frequency="daily")
    previous = {base.business_key: 14000.0}

    warned = evaluate(
        (obs(code="USDIRR_JISDOR", value=14900.0, unit="idr_per_usd", frequency="daily"),),
        CONFIG,
        previous,
    )
    assert [finding.severity for finding in warned.findings] == [Severity.WARN]


def test_vanishing_rows_beyond_threshold_is_a_breaker() -> None:
    batch = [obs(period_start=date(2022, 6, day)) for day in range(1, 11)]
    previous = {observation.business_key: 3.5 for observation in batch}
    survivors = tuple(batch[index] for index in (0, 1, 2, 3, 4, 9))

    report = evaluate(survivors, CONFIG, previous)

    assert "vanishing_rows" in codes(report)
    assert report.has_breaker is True


def test_vanishing_within_threshold_is_allowed() -> None:
    batch = [obs(period_start=date(2022, 6, day)) for day in range(1, 11)]
    previous = {observation.business_key: 3.5 for observation in batch}
    survivors = tuple(item for item in batch if item not in batch[4:6])

    report = evaluate(survivors, CONFIG, previous)

    assert "vanishing_rows" not in codes(report)


def test_vanishing_ignores_rows_for_retired_indicators() -> None:
    batch = [obs(period_start=date(2022, 6, day)) for day in range(1, 6)]
    retired = [obs(code="INFLASI_YOY", period_start=date(2022, 6, day)) for day in range(1, 10)]
    previous = {observation.business_key: 3.5 for observation in batch}
    previous.update({observation.business_key: 1.0 for observation in retired})

    report = evaluate(batch, CONFIG, previous)

    assert "vanishing_rows" not in codes(report)


def source_run(
    source_id: str = "BI_JISDOR", *, status: str = "ok", finished_at: datetime = TS
) -> SourceRunRecord:
    return SourceRunRecord(
        run_id="run-1",
        source_id=source_id,
        status=status,
        finished_at=finished_at,
    )


def test_fresh_source_has_no_freshness_findings() -> None:
    latest = {"BI_JISDOR": source_run(finished_at=TS - timedelta(days=1))}

    report = evaluate_freshness(CONFIG, latest, now=TS)

    assert report.findings == ()


def test_source_beyond_cadence_is_a_warn() -> None:
    latest = {"BI_JISDOR": source_run(finished_at=TS - timedelta(days=10))}

    report = evaluate_freshness(CONFIG, latest, now=TS)

    assert codes(report) == {"stale_source"}
    assert [finding.severity for finding in report.findings] == [Severity.WARN]
    assert report.has_breaker is False


def test_unhealthy_source_is_a_warn() -> None:
    latest = {"BI_JISDOR": source_run(status="failed", finished_at=TS)}

    report = evaluate_freshness(CONFIG, latest, now=TS)

    assert codes(report) == {"source_unhealthy"}
    assert report.has_breaker is False


def test_source_without_a_record_is_skipped() -> None:
    report = evaluate_freshness(CONFIG, {}, now=TS)

    assert report.findings == ()
