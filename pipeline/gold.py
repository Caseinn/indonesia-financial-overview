"""Build Gold in pandas and expose it as Parquet tables plus a JSON snapshot.

Gold is a projection of the current Silver revisions: every Run folds the full
history into facts, projects the published views, and builds the facts and
dimensions that the storage stage writes as Parquet. The JSON snapshot is the
denormalized copy the dashboard reads; Silver remains the only source of truth
(ADR-0008, ADR-0012).
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

import numpy as np
import pandas as pd

from pipeline import seeds
from pipeline.config import IndicatorsConfig, load_config
from pipeline.ops import SourceRunRecord
from pipeline.ops import store_from_env as ops_from_env
from pipeline.storage.silver import KEY_COLUMNS
from pipeline.storage.silver import store_from_env as silver_from_env

_logger = logging.getLogger(__name__)

SOURCE_COLUMNS = (
    "source_id",
    "name",
    "artifact",
    "url",
    "cadence_frequency",
    "refresh_days",
    "probe_start_day",
    "probe_end_day",
)

EVENT_COLUMNS = (
    "event_date",
    "code",
    "category",
    "title",
    "description",
    "source_url",
)

MACRO_COLUMNS = (
    "indicator_code",
    "period_start",
    "frequency",
    "entity_code",
    "sector_code",
    "value",
    "unit",
    "source_id",
    "source_table",
    "geography_code",
    "dimension_code",
    "first_published_value",
    "revision_count",
    "last_revised_at",
    "retrieved_at",
)

DAILY_COLUMNS = (
    "indicator_code",
    "obs_date",
    "entity_code",
    "value",
    "unit",
    "source_id",
    "geography_code",
    "dimension_code",
    "first_published_value",
    "revision_count",
    "last_revised_at",
    "retrieved_at",
)


@dataclass(frozen=True, slots=True)
class MacroFact:
    """One current periodic fact with its revision summary."""

    indicator_code: str
    period_start: date
    frequency: str
    entity_code: str
    sector_code: str
    value: float
    unit: str
    source_id: str
    source_table: str
    geography_code: str
    dimension_code: str
    first_published_value: float
    revision_count: int
    last_revised_at: datetime | None
    retrieved_at: datetime | None

    def params(self) -> tuple[object, ...]:
        return (
            self.indicator_code,
            self.period_start,
            self.frequency,
            self.entity_code,
            self.sector_code,
            self.value,
            self.unit,
            self.source_id,
            self.source_table,
            self.geography_code,
            self.dimension_code,
            self.first_published_value,
            self.revision_count,
            self.last_revised_at,
            self.retrieved_at,
        )


@dataclass(frozen=True, slots=True)
class DailyFact:
    """One current daily fact with its revision summary."""

    indicator_code: str
    obs_date: date
    entity_code: str
    value: float
    unit: str
    source_id: str
    geography_code: str
    dimension_code: str
    first_published_value: float
    revision_count: int
    last_revised_at: datetime | None
    retrieved_at: datetime | None

    def params(self) -> tuple[object, ...]:
        return (
            self.indicator_code,
            self.obs_date,
            self.entity_code,
            self.value,
            self.unit,
            self.source_id,
            self.geography_code,
            self.dimension_code,
            self.first_published_value,
            self.revision_count,
            self.last_revised_at,
            self.retrieved_at,
        )


@dataclass(frozen=True, slots=True)
class GoldBundle:
    """The Gold tables and the snapshot derived from them."""

    tables: dict[str, pd.DataFrame]
    snapshot: dict[str, list[dict[str, object]]]


@dataclass(frozen=True, slots=True)
class ViewContext:
    """Everything a Gold view needs to render one snapshot table."""

    now: pd.Timestamp
    sources: pd.DataFrame
    macro: pd.DataFrame
    daily: pd.DataFrame
    latest: Mapping[str, SourceRunRecord]


def build_bundle(
    *,
    config: IndicatorsConfig,
    frame: pd.DataFrame,
    latest: Mapping[str, SourceRunRecord],
    quarantined: Mapping[str, Iterable[str]] | None = None,
) -> GoldBundle:
    """Rebuild Gold once, returning its tables and the derived snapshot."""
    eligible = eligible_frame(frame, latest, quarantined=quarantined)
    macro, daily = build_facts(eligible)
    tables = build_tables(config, macro, daily)
    return GoldBundle(tables=tables, snapshot=render_snapshot(tables, latest))


def build_snapshot(
    *,
    config: IndicatorsConfig,
    frame: pd.DataFrame,
    latest: Mapping[str, SourceRunRecord],
    quarantined: Mapping[str, Iterable[str]] | None = None,
) -> dict[str, list[dict[str, object]]]:
    """Rebuild Gold from Silver and return every published view as row objects."""
    return build_bundle(
        config=config,
        frame=frame,
        latest=latest,
        quarantined=quarantined,
    ).snapshot


def build_bundle_from_env() -> GoldBundle:
    """Rebuild Gold from the configured Silver and ops stores."""
    config = load_config()
    ops = ops_from_env()
    return build_bundle(
        config=config,
        frame=silver_from_env().read_all(),
        latest=ops.latest_source_runs(config.sources),
        quarantined=ops.quarantined_checksums(config.sources),
    )


def build_from_env() -> dict[str, list[dict[str, object]]]:
    """Rebuild Gold and return only the published snapshot."""
    return build_bundle_from_env().snapshot


def build_tables(
    config: IndicatorsConfig,
    macro: Sequence[MacroFact],
    daily: Sequence[DailyFact],
    *,
    events: Sequence[seeds.Event] | None = None,
) -> dict[str, pd.DataFrame]:
    """Project facts, sources, and events into the Gold table shapes."""
    loaded_events = seeds.load_events() if events is None else events
    return {
        "dim_source": pd.DataFrame(source_rows(config), columns=list(SOURCE_COLUMNS)),
        "dim_events": pd.DataFrame(
            [event.params() for event in loaded_events], columns=list(EVENT_COLUMNS)
        ),
        "fact_macro_periodic": _macro_frame(macro),
        "fact_market_daily": _daily_frame(daily),
    }


def _macro_frame(macro: Sequence[MacroFact]) -> pd.DataFrame:
    frame = pd.DataFrame([fact.params() for fact in macro], columns=list(MACRO_COLUMNS))
    frame["period_start"] = pd.to_datetime(frame["period_start"])
    frame["last_revised_at"] = pd.to_datetime(frame["last_revised_at"], utc=True)
    frame["retrieved_at"] = pd.to_datetime(frame["retrieved_at"], utc=True)
    return frame


def _daily_frame(daily: Sequence[DailyFact]) -> pd.DataFrame:
    frame = pd.DataFrame([fact.params() for fact in daily], columns=list(DAILY_COLUMNS))
    frame["obs_date"] = pd.to_datetime(frame["obs_date"])
    frame["last_revised_at"] = pd.to_datetime(frame["last_revised_at"], utc=True)
    frame["retrieved_at"] = pd.to_datetime(frame["retrieved_at"], utc=True)
    return frame


def render_snapshot(
    tables: Mapping[str, pd.DataFrame],
    latest: Mapping[str, SourceRunRecord],
    *,
    now: pd.Timestamp | None = None,
) -> dict[str, list[dict[str, object]]]:
    """Run every published view over the Gold tables and serialize its rows."""
    context = ViewContext(
        now=now or pd.Timestamp.now(tz="UTC"),
        sources=tables["dim_source"],
        macro=tables["fact_macro_periodic"],
        daily=tables["fact_market_daily"],
        latest=latest,
    )
    return {name: records(view(context)) for name, view in VIEWS.items()}


def eligible_frame(
    frame: pd.DataFrame,
    latest: Mapping[str, SourceRunRecord],
    *,
    quarantined: Mapping[str, Iterable[str]] | None = None,
) -> pd.DataFrame:
    """Drop unpublished publications and re-derive which row is current.

    A failed or quarantined Source Run leaves its rows in Silver (ADR-0006), so
    the rebuild excludes that publication by checksum and lets the previous
    revision become current again. The durable quarantine ledger is applied as
    well, because the latest Run may have failed before publishing anything and
    would otherwise forget which checksums were rejected earlier.
    """
    if frame.empty:
        return frame
    blocked = {
        (record.source_id, checksum)
        for record in latest.values()
        if record.status != "ok"
        for checksum in record.publication_checksums
    }
    for source_id, checksums in (quarantined or {}).items():
        blocked.update((source_id, checksum) for checksum in checksums)
    if blocked:
        keep = [
            (str(source_id), str(checksum)) not in blocked
            for source_id, checksum in zip(
                frame["source_id"], frame["source_file_sha256"], strict=True
            )
        ]
        frame = frame[keep]
    return _refold_current(frame)


def _refold_current(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    frame = frame.copy()
    ordered = frame.sort_values(list(KEY_COLUMNS) + ["retrieved_at"], kind="stable")
    current = ordered.groupby(list(KEY_COLUMNS), dropna=False, sort=False).tail(1).index
    frame["is_current"] = frame.index.isin(current)
    return frame


def build_facts(frame: pd.DataFrame) -> tuple[list[MacroFact], list[DailyFact]]:
    """Turn a Silver frame into current Gold facts with revision summaries.

    Silver keeps every revision; Gold keeps only the current row per business
    key and folds the history into ``first_published_value``, ``revision_count``,
    and ``last_revised_at``.
    """
    macro: list[MacroFact] = []
    daily: list[DailyFact] = []
    if frame.empty:
        return macro, daily

    for _, rows in frame.groupby(list(KEY_COLUMNS), dropna=False, sort=False):
        current = rows[rows["is_current"]]
        if current.empty:
            continue
        row = current.iloc[0]
        revision_count = int((~rows["is_current"]).sum())
        first_published_value = float(rows.sort_values("retrieved_at").iloc[0]["normalized_value"])
        last_revised_at = _as_datetime(rows["superseded_at"].max()) if revision_count else None
        retrieved_at = _as_datetime(row["retrieved_at"])
        geography_code = str(row["geography_code"])
        dimension_code = str(row["dimension_code"])

        if str(row["frequency"]) == "daily":
            daily.append(
                DailyFact(
                    indicator_code=str(row["indicator_code"]),
                    obs_date=row["period_start"],
                    entity_code=geography_code,
                    value=float(row["normalized_value"]),
                    unit=str(row["normalized_unit"]),
                    source_id=str(row["source_id"]),
                    geography_code=geography_code,
                    dimension_code=dimension_code,
                    first_published_value=first_published_value,
                    revision_count=revision_count,
                    last_revised_at=last_revised_at,
                    retrieved_at=retrieved_at,
                )
            )
            continue

        macro.append(
            MacroFact(
                indicator_code=str(row["indicator_code"]),
                period_start=row["period_start"],
                frequency=str(row["frequency"]),
                entity_code=geography_code,
                sector_code=dimension_code or "ALL",
                value=float(row["normalized_value"]),
                unit=str(row["normalized_unit"]),
                source_id=str(row["source_id"]),
                source_table=str(row["source_table"]),
                geography_code=geography_code,
                dimension_code=dimension_code,
                first_published_value=first_published_value,
                revision_count=revision_count,
                last_revised_at=last_revised_at,
                retrieved_at=retrieved_at,
            )
        )
    return macro, daily


def source_rows(config: IndicatorsConfig) -> list[tuple[object, ...]]:
    """Project the Source configuration into dimension rows."""
    return [
        (
            source.source_id,
            source.name,
            source.artifact,
            source.url,
            source.cadence.frequency,
            source.cadence.refresh_days,
            source.cadence.probe_start_day,
            source.cadence.probe_end_day,
        )
        for source in config.sources.values()
    ]


def _pivot(
    frame: pd.DataFrame,
    *,
    frequency: str,
    codes: Sequence[str],
    renames: Mapping[str, str],
    period_name: str,
) -> pd.DataFrame:
    columns = [period_name, *renames.values()]
    selected = frame[(frame["frequency"] == frequency) & (frame["sector_code"] == "ALL")]
    if selected.empty:
        return pd.DataFrame(columns=columns)
    pivoted = selected.pivot_table(
        index="period_start",
        columns="indicator_code",
        values="value",
        aggfunc="max",
    )
    pivoted = pivoted.reindex(columns=list(codes)).rename(columns=renames)
    result = pivoted.reset_index().rename(columns={"period_start": period_name})
    result[period_name] = pd.to_datetime(result[period_name]).dt.date
    result = result.sort_values(period_name, kind="stable").reset_index(drop=True)
    return result[columns]


def _fx_monthly(context: ViewContext) -> pd.DataFrame:
    columns = [
        "month_start",
        "first_trading_day",
        "eop_date",
        "eop_rate",
        "average_rate",
        "trading_days",
        "is_complete_month",
    ]
    daily = context.daily[context.daily["indicator_code"] == "USDIRR_JISDOR"].copy()
    if daily.empty:
        return pd.DataFrame(columns=columns)

    daily["obs_date"] = pd.to_datetime(daily["obs_date"])
    daily["month_start"] = daily["obs_date"].dt.to_period("M").dt.start_time
    grouped = daily.groupby("month_start", sort=True)
    result = pd.DataFrame(
        {
            "first_trading_day": grouped["obs_date"].min().dt.date,
            "eop_date": grouped["obs_date"].max().dt.date,
            "average_rate": grouped["value"].mean(),
            "trading_days": grouped.size(),
        }
    ).reset_index()

    ordered = daily.sort_values(["month_start", "obs_date", "entity_code", "value"], kind="stable")
    eop = (
        ordered.groupby("month_start", sort=True)
        .tail(1)[["month_start", "value"]]
        .rename(columns={"value": "eop_rate"})
    )
    result = result.merge(eop, on="month_start", how="left")
    current_month = pd.Timestamp(context.now.date().replace(day=1))
    result["month_start"] = result["month_start"].dt.date
    result["is_complete_month"] = result["month_start"] < current_month.date()
    result = result.sort_values("month_start", kind="stable").reset_index(drop=True)
    return result[columns]


def _financial_overview_monthly(context: ViewContext) -> pd.DataFrame:
    columns = [
        "month_start",
        "policy_rate",
        "bi7drr",
        "inflation_mom",
        "money_supply_m2",
        "car",
        "roa",
        "ldr",
        "npl",
        "usd_idr_jisdor",
        "usd_idr_jisdor_avg",
    ]
    periodic = _pivot(
        context.macro,
        frequency="monthly",
        codes=[
            "POLICY_RATE",
            "BI7DR",
            "INFLASI_MOM",
            "MONEY_SUPPLY_M2",
            "CAR",
            "ROA",
            "LDR",
            "NPL",
        ],
        renames={
            "POLICY_RATE": "policy_rate",
            "BI7DR": "bi7drr",
            "INFLASI_MOM": "inflation_mom",
            "MONEY_SUPPLY_M2": "money_supply_m2",
            "CAR": "car",
            "ROA": "roa",
            "LDR": "ldr",
            "NPL": "npl",
        },
        period_name="month_start",
    )
    fx = _fx_monthly(context)[["month_start", "eop_rate", "average_rate"]].rename(
        columns={"eop_rate": "usd_idr_jisdor", "average_rate": "usd_idr_jisdor_avg"}
    )
    result = periodic.merge(fx, on="month_start", how="outer")
    result = result.sort_values("month_start", kind="stable").reset_index(drop=True)
    return result[columns]


def _financial_overview_annual(context: ViewContext) -> pd.DataFrame:
    columns = [
        "year_start",
        "year",
        "apbn_revenue",
        "apbn_expenditure",
        "apbn_balance",
        "apbn_financing",
        "car",
        "roa",
        "ldr",
    ]
    result = _pivot(
        context.macro,
        frequency="annual",
        codes=[
            "APBN_REVENUE",
            "APBN_EXPENDITURE",
            "APBN_BALANCE",
            "APBN_FINANCING",
            "CAR_ANNUAL",
            "ROA_ANNUAL",
            "LDR_ANNUAL",
        ],
        renames={
            "APBN_REVENUE": "apbn_revenue",
            "APBN_EXPENDITURE": "apbn_expenditure",
            "APBN_BALANCE": "apbn_balance",
            "APBN_FINANCING": "apbn_financing",
            "CAR_ANNUAL": "car",
            "ROA_ANNUAL": "roa",
            "LDR_ANNUAL": "ldr",
        },
        period_name="year_start",
    )
    result.insert(1, "year", pd.to_datetime(result["year_start"]).dt.year.astype("int64"))
    return result[columns]


def _dashboard_freshness(context: ViewContext) -> pd.DataFrame:
    columns = [
        "source_id",
        "name",
        "status",
        "last_published_at",
        "lag_days",
        "refresh_days",
        "is_fresh",
        "rows_published",
        "revisions",
        "global_healthy",
    ]
    sources = context.sources[["source_id", "name", "refresh_days"]].copy()
    runs = pd.DataFrame(
        [
            {
                "source_id": record.source_id,
                "status": record.status,
                "finished_at": record.finished_at,
                "rows_published": record.rows_published,
                "revisions": record.revisions,
            }
            for record in context.latest.values()
        ],
        columns=["source_id", "status", "finished_at", "rows_published", "revisions"],
    )
    if not runs.empty:
        runs["finished_at"] = pd.to_datetime(runs["finished_at"], utc=True)
        runs = runs.sort_values(
            "finished_at", ascending=False, na_position="last", kind="stable"
        ).drop_duplicates("source_id", keep="first")
    result = sources.merge(runs, on="source_id", how="left").rename(
        columns={"finished_at": "last_published_at"}
    )
    finished = pd.to_datetime(result["last_published_at"], utc=True)
    now = context.now.tz_convert("UTC")
    result["lag_days"] = ((now.normalize() - finished.dt.normalize()).dt.days).astype("Int64")
    refresh = result["refresh_days"].fillna(0)
    result["is_fresh"] = (
        (result["status"] == "ok")
        & finished.notna()
        & (finished >= now - pd.to_timedelta(refresh, unit="D"))
    )
    result["rows_published"] = result["rows_published"].astype("Int64")
    result["revisions"] = result["revisions"].astype("Int64")
    result["global_healthy"] = bool((result["status"].fillna("failed") == "ok").all())
    result = result.sort_values("source_id", kind="stable").reset_index(drop=True)
    return result[columns]


def _gold_revisions(context: ViewContext) -> pd.DataFrame:
    columns = [
        "indicator_code",
        "period_start",
        "frequency",
        "entity_code",
        "sector_code",
        "first_published_value",
        "current_value",
        "change",
        "revision_count",
        "last_revised_at",
    ]
    macro = context.macro[context.macro["revision_count"] > 0]
    daily = context.daily[context.daily["revision_count"] > 0]
    macro_rows = pd.DataFrame(
        {
            "indicator_code": macro["indicator_code"],
            "period_start": macro["period_start"],
            "frequency": macro["frequency"],
            "entity_code": macro["entity_code"],
            "sector_code": macro["sector_code"],
            "first_published_value": macro["first_published_value"],
            "current_value": macro["value"],
            "change": macro["value"] - macro["first_published_value"],
            "revision_count": macro["revision_count"],
            "last_revised_at": macro["last_revised_at"],
        }
    )
    daily_rows = pd.DataFrame(
        {
            "indicator_code": daily["indicator_code"],
            "period_start": daily["obs_date"],
            "frequency": "daily",
            "entity_code": daily["entity_code"],
            "sector_code": "ALL",
            "first_published_value": daily["first_published_value"],
            "current_value": daily["value"],
            "change": daily["value"] - daily["first_published_value"],
            "revision_count": daily["revision_count"],
            "last_revised_at": daily["last_revised_at"],
        }
    )
    result = pd.concat([macro_rows, daily_rows], ignore_index=True)
    if result.empty:
        return pd.DataFrame(columns=columns)
    result["period_start"] = pd.to_datetime(result["period_start"]).dt.date
    result = result.sort_values(["indicator_code", "period_start"], kind="stable").reset_index(
        drop=True
    )
    return result[columns]


def _monetary_policy(context: ViewContext) -> pd.DataFrame:
    return _pivot(
        context.macro,
        frequency="monthly",
        codes=["POLICY_RATE", "BI7DR", "DF_RATE", "LF_RATE"],
        renames={
            "POLICY_RATE": "policy_rate",
            "BI7DR": "bi7drr",
            "DF_RATE": "deposit_facility",
            "LF_RATE": "lending_facility",
        },
        period_name="period_start",
    )


def _liquidity(context: ViewContext) -> pd.DataFrame:
    return _pivot(
        context.macro,
        frequency="monthly",
        codes=["MONEY_SUPPLY_M1", "MONEY_SUPPLY_M2"],
        renames={"MONEY_SUPPLY_M1": "m1", "MONEY_SUPPLY_M2": "m2"},
        period_name="period_start",
    )


def _fiscal_annual(context: ViewContext) -> pd.DataFrame:
    columns = ["year_start", "year", "revenue", "expenditure", "balance"]
    result = _pivot(
        context.macro,
        frequency="annual",
        codes=["APBN_REVENUE", "APBN_EXPENDITURE", "APBN_BALANCE"],
        renames={
            "APBN_REVENUE": "revenue",
            "APBN_EXPENDITURE": "expenditure",
            "APBN_BALANCE": "balance",
        },
        period_name="year_start",
    )
    result.insert(1, "year", pd.to_datetime(result["year_start"]).dt.year.astype("int64"))
    return result[columns]


def _sbn_monthly(context: ViewContext) -> pd.DataFrame:
    columns = ["period_start", "outstanding"]
    selected = context.macro[
        (context.macro["indicator_code"] == "SBN_OUTSTANDING")
        & (context.macro["frequency"] == "monthly")
        & (context.macro["sector_code"] == "ALL")
    ]
    if selected.empty:
        return pd.DataFrame(columns=columns)
    result = (
        selected.groupby("period_start", as_index=False)["value"]
        .max()
        .rename(columns={"value": "outstanding"})
    )
    result["period_start"] = pd.to_datetime(result["period_start"]).dt.date
    result = result.sort_values("period_start", kind="stable").reset_index(drop=True)
    return result[columns]


def _rupiah(context: ViewContext) -> pd.DataFrame:
    columns = ["month_start", "jisdor_eop", "jisdor_avg", "seki_rate"]
    fx = _fx_monthly(context)[["month_start", "eop_rate", "average_rate"]].rename(
        columns={"eop_rate": "jisdor_eop", "average_rate": "jisdor_avg"}
    )
    selected = context.macro[
        (context.macro["indicator_code"] == "USDIRR_SEKI")
        & (context.macro["frequency"] == "monthly")
        & (context.macro["sector_code"] == "ALL")
    ]
    if selected.empty:
        seki = pd.DataFrame(columns=["month_start", "seki_rate"])
    else:
        seki = selected.copy()
        seki["month_start"] = (
            pd.to_datetime(seki["period_start"]).dt.to_period("M").dt.start_time.dt.date
        )
        seki = (
            seki.groupby("month_start", as_index=False)["value"]
            .max()
            .rename(columns={"value": "seki_rate"})
        )
    result = fx.merge(seki, on="month_start", how="outer")
    result = result.sort_values("month_start", kind="stable").reset_index(drop=True)
    return result[columns]


def _credit_sector(context: ViewContext) -> pd.DataFrame:
    columns = ["period_start", "dimension_code", "value"]
    selected = context.macro[context.macro["indicator_code"] == "CREDIT_BY_SECTOR"]
    if selected.empty:
        return pd.DataFrame(columns=columns)
    latest = selected["period_start"].max()
    result = selected[selected["period_start"] == latest][columns].copy()
    result["period_start"] = pd.to_datetime(result["period_start"]).dt.date
    result = result.sort_values(
        ["value", "dimension_code"], ascending=[False, True], kind="stable"
    ).reset_index(drop=True)
    return result


def _regional(context: ViewContext) -> pd.DataFrame:
    columns = ["period_start", "geography_code", "gdp_growth", "inflation"]
    geographies = ("IDN", "PHL", "MYS", "CHN", "THA", "SGP")
    macro = context.macro
    regional = macro[
        (macro["frequency"] == "quarterly") & macro["geography_code"].isin(geographies)
    ].copy()
    if regional.empty:
        return pd.DataFrame(columns=columns)

    regional["gdp_growth"] = regional["value"].where(
        regional["indicator_code"].str.contains("GDP_GROWTH", regex=False)
    )
    regional["inflation"] = regional["value"].where(
        regional["indicator_code"].str.contains("INFLATION", regex=False)
    )
    grouped = regional.groupby(["period_start", "geography_code"], as_index=False).agg(
        gdp_growth=("gdp_growth", "max"),
        inflation=("inflation", "max"),
    )

    monthly = (
        macro[
            (macro["indicator_code"] == "INFLASI_MOM")
            & (macro["frequency"] == "monthly")
            & (macro["sector_code"] == "ALL")
        ]
        .sort_values("period_start", kind="stable")
        .copy()
    )
    if monthly.empty:
        result = grouped
    else:
        monthly["inflation"] = (
            np.expm1(np.log1p(monthly["value"] / 100).rolling(12, min_periods=1).sum()) * 100
        )
        monthly["period_start"] = pd.to_datetime(monthly["period_start"])
        quarterly = monthly[monthly["period_start"].dt.month.isin([3, 6, 9, 12])].copy()
        quarterly["period_start"] = quarterly["period_start"].dt.to_period("Q").dt.start_time
        idn = quarterly.groupby("period_start", as_index=False)["inflation"].max()
        idn["geography_code"] = "IDN"
        result = grouped.merge(
            idn,
            on=["period_start", "geography_code"],
            how="left",
            suffixes=("", "_monthly"),
        )
        result["inflation"] = result["inflation"].fillna(result["inflation_monthly"])
        result = result.drop(columns=["inflation_monthly"])

    result["period_start"] = pd.to_datetime(result["period_start"]).dt.date
    result = result.sort_values(["period_start", "geography_code"], kind="stable").reset_index(
        drop=True
    )
    return result[columns]


VIEWS: dict[str, Callable[[ViewContext], pd.DataFrame]] = {
    "financial_overview_monthly": _financial_overview_monthly,
    "financial_overview_annual": _financial_overview_annual,
    "fx_monthly": _fx_monthly,
    "dashboard_freshness": _dashboard_freshness,
    "gold_revisions": _gold_revisions,
    "monetary_policy": _monetary_policy,
    "liquidity": _liquidity,
    "fiscal_annual": _fiscal_annual,
    "sbn_monthly": _sbn_monthly,
    "rupiah": _rupiah,
    "credit_sector": _credit_sector,
    "regional": _regional,
}


def records(frame: pd.DataFrame) -> list[dict[str, object]]:
    """Convert a view into JSON-safe row objects, preserving column order."""
    columns = [str(column) for column in frame.columns]
    return [
        {column: _json_value(value) for column, value in zip(columns, values, strict=True)}
        for values in frame.itertuples(index=False, name=None)
    ]


def _json_value(value: object) -> object:
    if value is None or value is pd.NaT or value is pd.NA:
        return None
    if isinstance(value, pd.Timestamp):
        return None if pd.isna(value) else value.to_pydatetime()
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return value
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return None if np.isnan(value) else float(value)
    if isinstance(value, float):
        return None if math.isnan(value) else value
    if isinstance(value, np.datetime64):
        return pd.Timestamp(value).to_pydatetime()
    return value


def _as_datetime(value: Any) -> datetime | None:
    if value is None or pd.isna(value):
        return None
    return value.to_pydatetime() if hasattr(value, "to_pydatetime") else value
