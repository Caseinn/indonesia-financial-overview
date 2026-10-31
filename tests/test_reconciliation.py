"""Cross-source reconciliation between JISDOR daily and SEKI V.40 monthly."""

from __future__ import annotations

from datetime import UTC, date, datetime

from pipeline.models import Observation
from pipeline.reconciliation import monthly_averages, reconcile_usd_idr

TS = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)


def obs(code: str, period_start: date, value: float, *, frequency: str = "monthly") -> Observation:
    return Observation(
        source_id="BI_SEKI",
        source_table="TABEL5_40",
        indicator_code=code,
        period_start=period_start,
        period_end=period_start,
        frequency=frequency,
        geography_code="IDN",
        original_value=value,
        original_unit="idr_per_usd",
        normalized_value=value,
        normalized_unit="idr_per_usd",
        source_raw_label="USD",
        retrieved_at=TS,
        source_file_sha256="a" * 64,
        ingestion_run_id="run-1",
    )


def jisdor_month(year: int, month: int, value: float, days: int = 20) -> list[Observation]:
    return [
        obs("USDIRR_JISDOR", date(year, month, day), value, frequency="daily")
        for day in range(1, days + 1)
    ]


def test_matching_months_have_no_findings() -> None:
    primary = jisdor_month(2026, 8, 17800.0)
    reference = [obs("USDIRR_SEKI", date(2026, 8, 1), 17850.0)]

    assert reconcile_usd_idr(primary, reference) == ()


def test_divergent_month_is_flagged() -> None:
    primary = jisdor_month(2026, 8, 17800.0)
    reference = [obs("USDIRR_SEKI", date(2026, 8, 1), 19000.0)]

    findings = reconcile_usd_idr(primary, reference)

    assert len(findings) == 1
    assert findings[0].period_start == date(2026, 8, 1)
    assert findings[0].primary == 17800.0
    assert findings[0].reference == 19000.0
    assert findings[0].relative_diff > 0.02


def test_partial_primary_month_is_skipped() -> None:
    primary = jisdor_month(2026, 8, 17000.0, days=5)
    reference = [obs("USDIRR_SEKI", date(2026, 8, 1), 19000.0)]

    assert reconcile_usd_idr(primary, reference) == ()


def test_monthly_averages_requires_min_days() -> None:
    observations = jisdor_month(2026, 8, 15000.0, days=3)

    assert monthly_averages(observations, "USDIRR_JISDOR", min_days=15) == {}
    assert monthly_averages(observations, "USDIRR_JISDOR", min_days=1) == {(2026, 8): 15000.0}
