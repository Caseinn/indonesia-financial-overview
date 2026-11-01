"""Gold build: pandas views, revision folding, and quarantine handling."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pandas as pd
import pytest

from pipeline.config import load_config
from pipeline.gold import (
    VIEWS,
    build_bundle,
    build_facts,
    build_snapshot,
    eligible_frame,
    source_rows,
)
from pipeline.ops import SourceRunRecord
from pipeline.storage.silver import COLUMNS

TS = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)
CONFIG = load_config()


def silver_row(
    *,
    indicator_code: str = "POLICY_RATE",
    period_start: date = date(2024, 1, 1),
    frequency: str = "monthly",
    geography_code: str = "IDN",
    dimension_code: str = "",
    value: float = 3.5,
    sha: str = "a" * 64,
    source_id: str = "BI_SEKI",
    is_current: bool = True,
    retrieved_at: datetime = TS,
    superseded_at: datetime | None = None,
) -> dict[str, object]:
    return {
        "source_id": source_id,
        "source_table": "TABEL",
        "indicator_code": indicator_code,
        "period_start": period_start,
        "frequency": frequency,
        "geography_code": geography_code,
        "dimension_code": dimension_code,
        "normalized_value": value,
        "normalized_unit": "percent",
        "source_file_sha256": sha,
        "retrieved_at": pd.Timestamp(retrieved_at),
        "is_current": is_current,
        "superseded_at": pd.Timestamp(superseded_at) if superseded_at else pd.NaT,
    }


def frame(*rows: dict[str, object]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def ok_run(source_id: str = "BI_SEKI", **kwargs: object) -> SourceRunRecord:
    return SourceRunRecord(
        run_id="run-1",
        source_id=source_id,
        status="ok",
        finished_at=datetime.now(UTC),
        rows_published=10,
        **kwargs,
    )


def healthy_latest() -> dict[str, SourceRunRecord]:
    return {source_id: ok_run(source_id) for source_id in CONFIG.sources}


def test_build_facts_folds_revision_history() -> None:
    data = frame(
        silver_row(value=3.5, is_current=False, superseded_at=TS),
        silver_row(value=3.75, is_current=True, retrieved_at=TS),
    )

    macro, daily = build_facts(data)

    assert daily == []
    assert len(macro) == 1
    fact = macro[0]
    assert fact.indicator_code == "POLICY_RATE"
    assert fact.value == 3.75
    assert fact.first_published_value == 3.5
    assert fact.revision_count == 1
    assert fact.last_revised_at == TS
    assert fact.sector_code == "ALL"


def test_build_facts_maps_daily_and_sector() -> None:
    data = frame(
        silver_row(indicator_code="USDIRR_JISDOR", frequency="daily", value=15500.0),
        silver_row(indicator_code="CREDIT_BY_SECTOR", dimension_code="SECTOR_A", value=1e12),
    )

    macro, daily = build_facts(data)

    assert len(daily) == 1
    assert daily[0].obs_date == date(2024, 1, 1)
    assert daily[0].revision_count == 0
    assert daily[0].last_revised_at is None
    assert len(macro) == 1
    assert macro[0].sector_code == "SECTOR_A"


def test_build_facts_ignores_keys_without_a_current_row() -> None:
    macro, daily = build_facts(frame(silver_row(is_current=False, superseded_at=TS)))

    assert macro == []
    assert daily == []


def test_eligible_frame_restores_the_previous_revision() -> None:
    data = frame(
        silver_row(value=4.0, sha="a" * 64, is_current=False, superseded_at=TS),
        silver_row(value=9.0, sha="b" * 64, is_current=True, retrieved_at=TS + timedelta(days=1)),
    )
    latest = {
        "BI_SEKI": SourceRunRecord(
            run_id="run-2",
            source_id="BI_SEKI",
            status="failed",
            finished_at=TS,
            publication_checksums=("b" * 64,),
            message="quarantined: drift",
        )
    }

    eligible = eligible_frame(data, latest)

    assert len(eligible) == 1
    assert eligible.iloc[0]["normalized_value"] == 4.0
    assert bool(eligible.iloc[0]["is_current"]) is True


def test_eligible_frame_honors_a_durable_quarantine() -> None:
    data = frame(
        silver_row(value=4.0, sha="a" * 64, is_current=False, superseded_at=TS),
        silver_row(value=9.0, sha="b" * 64, is_current=True, retrieved_at=TS + timedelta(days=1)),
    )
    latest = {
        "BI_SEKI": SourceRunRecord(
            run_id="run-3",
            source_id="BI_SEKI",
            status="failed",
            finished_at=TS,
            publication_checksums=(),
            message="fetch failed",
        )
    }

    eligible = eligible_frame(data, latest, quarantined={"BI_SEKI": ("b" * 64,)})

    assert len(eligible) == 1
    assert eligible.iloc[0]["normalized_value"] == 4.0
    assert bool(eligible.iloc[0]["is_current"]) is True


def test_build_snapshot_publishes_every_view() -> None:
    data = frame(
        silver_row(indicator_code="POLICY_RATE", value=4.75),
        silver_row(indicator_code="BI7DR", value=5.0),
        silver_row(indicator_code="INFLASI_MOM", value=0.2),
        silver_row(indicator_code="INFLASI_MOM", period_start=date(2024, 3, 1), value=0.3),
        silver_row(indicator_code="MONEY_SUPPLY_M2", value=8000.0),
        silver_row(indicator_code="SBN_OUTSTANDING", value=5000.0),
        silver_row(indicator_code="USDIRR_SEKI", value=15510.0),
        silver_row(indicator_code="CREDIT_BY_SECTOR", dimension_code="SECTOR_A", value=100.0),
        silver_row(
            indicator_code="APBN_REVENUE",
            period_start=date(2023, 1, 1),
            frequency="annual",
            value=3000.0,
        ),
        silver_row(
            indicator_code="USDIRR_JISDOR",
            period_start=date(2024, 1, 2),
            frequency="daily",
            value=15500.0,
        ),
        silver_row(
            indicator_code="USDIRR_JISDOR",
            period_start=date(2024, 1, 31),
            frequency="daily",
            value=15400.0,
        ),
        silver_row(
            indicator_code="PHL_GDP_GROWTH",
            period_start=date(2024, 1, 1),
            frequency="quarterly",
            geography_code="PHL",
            value=5.0,
        ),
        silver_row(
            indicator_code="IDN_GDP_GROWTH",
            period_start=date(2024, 1, 1),
            frequency="quarterly",
            value=5.1,
        ),
    )

    snapshot = build_snapshot(config=CONFIG, frame=data, latest=healthy_latest())

    assert set(snapshot) == set(VIEWS)
    monthly = snapshot["financial_overview_monthly"]
    assert monthly[0]["month_start"] == date(2024, 1, 1)
    assert monthly[0]["policy_rate"] == 4.75
    assert monthly[0]["usd_idr_jisdor"] == 15400.0
    assert snapshot["fiscal_annual"][0]["revenue"] == 3000.0
    assert snapshot["rupiah"][0]["jisdor_eop"] == 15400.0
    assert snapshot["rupiah"][0]["seki_rate"] == 15510.0
    assert snapshot["credit_sector"][0]["dimension_code"] == "SECTOR_A"
    assert {row["geography_code"] for row in snapshot["regional"]} >= {"IDN", "PHL"}
    idn = next(row for row in snapshot["regional"] if row["geography_code"] == "IDN")
    assert idn["gdp_growth"] == 5.1
    assert idn["inflation"] is not None
    assert snapshot["gold_revisions"] == []
    assert snapshot["dashboard_freshness"][0]["global_healthy"] is True


def test_build_bundle_returns_the_gold_tables() -> None:
    data = frame(
        silver_row(indicator_code="POLICY_RATE", value=4.75),
        silver_row(
            indicator_code="USDIRR_JISDOR",
            period_start=date(2024, 1, 2),
            frequency="daily",
            value=15500.0,
        ),
    )

    bundle = build_bundle(config=CONFIG, frame=data, latest=healthy_latest())

    assert set(bundle.tables) == {
        "dim_source",
        "dim_events",
        "fact_macro_periodic",
        "fact_market_daily",
    }
    assert bundle.tables["fact_macro_periodic"]["indicator_code"].tolist() == ["POLICY_RATE"]
    assert bundle.tables["fact_market_daily"]["indicator_code"].tolist() == ["USDIRR_JISDOR"]
    assert len(bundle.tables["dim_source"]) == len(CONFIG.sources)
    assert set(bundle.snapshot) == set(VIEWS)


def test_build_snapshot_hides_a_quarantined_publication() -> None:
    data = frame(
        silver_row(value=4.0, sha="a" * 64, is_current=False, superseded_at=TS),
        silver_row(value=9.0, sha="b" * 64, is_current=True, retrieved_at=TS + timedelta(days=1)),
    )
    latest = {
        **healthy_latest(),
        "BI_SEKI": SourceRunRecord(
            run_id="run-2",
            source_id="BI_SEKI",
            status="failed",
            finished_at=datetime.now(UTC),
            publication_checksums=("b" * 64,),
            message="quarantined: drift",
        ),
    }

    snapshot = build_snapshot(config=CONFIG, frame=data, latest=latest)

    assert snapshot["financial_overview_monthly"][0]["policy_rate"] == 4.0
    freshness = {row["source_id"]: row for row in snapshot["dashboard_freshness"]}
    assert freshness["BI_SEKI"]["status"] == "failed"
    assert freshness["BI_SEKI"]["global_healthy"] is False


def test_build_snapshot_on_empty_silver_still_publishes_views() -> None:
    snapshot = build_snapshot(config=CONFIG, frame=pd.DataFrame(columns=COLUMNS), latest={})

    assert set(snapshot) == set(VIEWS)
    assert snapshot["financial_overview_monthly"] == []
    assert len(snapshot["dashboard_freshness"]) == len(CONFIG.sources)
    assert snapshot["dashboard_freshness"][0]["global_healthy"] is False


def test_source_rows_project_the_config() -> None:
    sources = {row[0]: row for row in source_rows(CONFIG)}

    assert sources["BI_JISDOR"][4] == "weekday"
    assert sources["BI_JISDOR"][5] == 4
    assert sources["BI_SEKI"][5] == 35


def test_freshness_tolerates_the_gap_between_monthly_runs() -> None:
    latest = {
        "BI_SEKI": SourceRunRecord(
            run_id="run-1",
            source_id="BI_SEKI",
            status="ok",
            finished_at=datetime.now(UTC) - timedelta(days=20),
            rows_published=1,
        )
    }

    snapshot = build_snapshot(config=CONFIG, frame=pd.DataFrame(columns=COLUMNS), latest=latest)
    freshness = {row["source_id"]: row for row in snapshot["dashboard_freshness"]}

    assert freshness["BI_SEKI"]["is_fresh"] is True


def test_freshness_flags_a_source_past_its_refresh_window() -> None:
    latest = {
        "BI_SEKI": SourceRunRecord(
            run_id="run-1",
            source_id="BI_SEKI",
            status="ok",
            finished_at=datetime.now(UTC) - timedelta(days=40),
            rows_published=1,
        )
    }

    snapshot = build_snapshot(config=CONFIG, frame=pd.DataFrame(columns=COLUMNS), latest=latest)
    freshness = {row["source_id"]: row for row in snapshot["dashboard_freshness"]}

    assert freshness["BI_SEKI"]["is_fresh"] is False


@pytest.mark.parametrize("source_id", ["BI_JISDOR", "BI_SEKI", "BPS", "OJK_SPI"])
def test_freshness_covers_every_configured_source(source_id: str) -> None:
    snapshot = build_snapshot(config=CONFIG, frame=pd.DataFrame(columns=COLUMNS), latest={})

    assert source_id in {row["source_id"] for row in snapshot["dashboard_freshness"]}
