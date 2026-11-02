"""Orchestrator behaviour: per-source isolation, quarantine, and run status."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime, timedelta

import pytest

from pipeline.config import IndicatorsConfig, load_config
from pipeline.models import Artifact, IngestionEnvelope, Observation, SourceRunResult
from pipeline.ops import PipelineRunRecord, SourceRunRecord
from pipeline.run_monthly import (
    DEFAULT_SOURCES,
    SOURCES,
    _export_web,
    _overall,
    _parse_args,
    _period,
    _run_source,
    _write_gold,
)
from pipeline.storage.bronze import BronzeStore
from pipeline.storage.silver import SilverStore
from tests.storage.fakes import FakeS3

TS = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)
CONFIG: IndicatorsConfig = load_config()


@pytest.fixture(autouse=True)
def _clear_alert_webhook(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ALERT_WEBHOOK_URL", raising=False)


class StubOps:
    """Captures run records without touching object storage."""

    def __init__(self) -> None:
        self.sources: list[SourceRunRecord] = []
        self.runs: list[PipelineRunRecord] = []
        self.quarantine: dict[str, tuple[str, ...]] = {}

    def write_source(self, record: SourceRunRecord) -> None:
        self.sources.append(record)

    def write_run(self, record: PipelineRunRecord) -> None:
        self.runs.append(record)

    def latest_source_runs(self, source_ids: Iterable[str]) -> dict[str, SourceRunRecord]:
        return {}

    def quarantined_checksums(self, source_ids: Iterable[str]) -> dict[str, tuple[str, ...]]:
        return {
            source_id: self.quarantine[source_id]
            for source_id in source_ids
            if source_id in self.quarantine
        }

    def record_quarantine(self, source_id: str, checksums: Iterable[str]) -> tuple[str, ...]:
        merged = tuple(sorted(set(self.quarantine.get(source_id, ())) | set(checksums)))
        self.quarantine[source_id] = merged
        return merged


def envelope() -> IngestionEnvelope:
    return IngestionEnvelope(
        source_id="BI_JISDOR",
        source_url="https://example.test",
        retrieved_at=TS,
        period_start=date(2020, 1, 1),
        period_end=date(2020, 1, 2),
        source_file_sha256="a" * 64,
        ingestion_run_id="run-1",
        source_version=1,
    )


def observation(*, code: str = "USDIRR_JISDOR", value: float = 14000.0) -> Observation:
    return Observation(
        source_id="BI_JISDOR",
        source_table="JISDOR",
        indicator_code=code,
        period_start=date(2020, 1, 2),
        period_end=date(2020, 1, 2),
        frequency="daily",
        geography_code="IDN",
        original_value=value,
        original_unit="idr_per_usd",
        normalized_value=value,
        normalized_unit="idr_per_usd",
        source_raw_label="Kurs",
        retrieved_at=TS,
        source_file_sha256="a" * 64,
        ingestion_run_id="run-1",
    )


def seki_envelope(sha: str) -> IngestionEnvelope:
    return IngestionEnvelope(
        source_id="BI_SEKI",
        source_url="https://example.test/seki",
        retrieved_at=TS,
        period_start=date(2020, 1, 1),
        period_end=date(2020, 1, 31),
        source_file_sha256=sha,
        ingestion_run_id="run-1",
        source_version=1,
    )


def policy_rate(*, value: float, sha: str) -> Observation:
    return Observation(
        source_id="BI_SEKI",
        source_table="TABEL1_25_1",
        indicator_code="POLICY_RATE",
        period_start=date(2020, 1, 1),
        period_end=date(2020, 1, 31),
        frequency="monthly",
        geography_code="IDN",
        original_value=value,
        original_unit="percent_per_annum",
        normalized_value=value,
        normalized_unit="percent_per_annum",
        source_raw_label="Policy Rate",
        retrieved_at=TS,
        source_file_sha256=sha,
        ingestion_run_id="run-1",
    )


def stores() -> tuple[BronzeStore, SilverStore]:
    return BronzeStore(FakeS3(), "bucket"), SilverStore(FakeS3(), "bucket")


def test_run_source_records_success() -> None:
    bronze, silver = stores()
    ops = StubOps()
    result = SourceRunResult(
        envelope=envelope(),
        observations=(observation(),),
        artifacts=(Artifact("jisdor.xlsx", "application/vnd.ms-excel", b"data"),),
    )

    status, _ = _run_source(
        "BI_JISDOR",
        lambda *args: result,
        CONFIG,
        "run-1",
        date(2020, 1, 1),
        date(2020, 1, 2),
        bronze,
        silver,
        ops,
    )

    assert status == "ok"
    record = ops.sources[0]
    assert record.status == "ok"
    assert record.rows_published == 1
    assert record.publication_checksums == ("a" * 64,)


def test_run_source_records_failure_without_raising() -> None:
    bronze, silver = stores()
    ops = StubOps()

    def boom(*args: object) -> None:
        raise RuntimeError("boom")

    status, _ = _run_source(
        "BPS",
        boom,
        CONFIG,
        "run-1",
        date(2020, 1, 1),
        date(2020, 1, 2),
        bronze,
        silver,
        ops,
    )

    assert status == "failed"
    assert ops.sources[0].status == "failed"
    assert ops.sources[0].message == "boom"


def test_run_source_quarantines_on_breaker() -> None:
    bronze, silver = stores()
    ops = StubOps()
    result = SourceRunResult(
        envelope=envelope(),
        observations=(observation(code="NOPE"),),
        artifacts=(Artifact("jisdor.xlsx", "application/vnd.ms-excel", b"data"),),
    )

    status, _ = _run_source(
        "BI_JISDOR",
        lambda *args: result,
        CONFIG,
        "run-1",
        date(2020, 1, 1),
        date(2020, 1, 2),
        bronze,
        silver,
        ops,
    )

    assert status == "failed"
    record = ops.sources[0]
    assert record.status == "failed"
    assert record.message and record.message.startswith("quarantined:")
    assert record.publication_checksums == ("a" * 64,)
    assert ops.quarantine == {"BI_JISDOR": ("a" * 64,)}


def test_gate_baseline_ignores_a_quarantined_publication() -> None:
    bronze, silver = stores()
    ops = StubOps()
    artifact = Artifact("seki.zip", "application/zip", b"zip")

    def ingest(run_id: str, value: float, sha: str) -> str:
        result = SourceRunResult(
            envelope=seki_envelope(sha),
            observations=(policy_rate(value=value, sha=sha),),
            artifacts=(artifact,),
        )
        status, _ = _run_source(
            "BI_SEKI",
            lambda *args: result,
            CONFIG,
            run_id,
            date(2020, 1, 1),
            date(2020, 1, 31),
            bronze,
            silver,
            ops,
        )
        return status

    assert ingest("run-1", 4.0, "a" * 64) == "ok"
    assert ingest("run-2", 10.0, "b" * 64) == "failed"
    assert ops.quarantine == {"BI_SEKI": ("b" * 64,)}
    assert ingest("run-3", 4.1, "c" * 64) == "ok"


def test_run_source_swallows_a_storage_failure() -> None:
    class BoomBronze:
        def write(self, *args: object, **kwargs: object) -> None:
            raise RuntimeError("r2 down")

    _, silver = stores()
    ops = StubOps()
    result = SourceRunResult(
        envelope=envelope(),
        observations=(observation(),),
        artifacts=(Artifact("jisdor.xlsx", "application/vnd.ms-excel", b"data"),),
    )

    status, _ = _run_source(
        "BI_JISDOR",
        lambda *args: result,
        CONFIG,
        "run-1",
        date(2020, 1, 1),
        date(2020, 1, 2),
        BoomBronze(),
        silver,
        ops,
    )

    assert status == "failed"
    assert ops.sources[0].status == "failed"


def test_edition_runner_records_under_the_portal_source() -> None:
    assert SOURCES["OJK_SPI_EDITION"][0] == "OJK_SPI"
    assert SOURCES["OJK_SPI"][0] == "OJK_SPI"


def test_overall_status() -> None:
    assert _overall(["ok", "ok"]) == "ok"
    assert _overall(["ok", "failed"]) == "partial"
    assert _overall(["failed", "failed"]) == "failed"


def test_period_defaults_to_lookback() -> None:
    args = _parse_args([])
    start, end = _period(args)

    assert end == date.today()
    assert end - start == timedelta(days=40)


def test_period_respects_explicit_range() -> None:
    args = _parse_args(["--start", "2019-01-01", "--end", "2020-12-31"])
    start, end = _period(args)

    assert (start, end) == (date(2019, 1, 1), date(2020, 12, 31))


def test_sources_registry_matches_config() -> None:
    assert set(DEFAULT_SOURCES) == set(CONFIG.sources)
    assert set(SOURCES) >= set(DEFAULT_SOURCES)


def test_sources_filter_defaults_to_all() -> None:
    assert _parse_args([]).sources is None


def test_sources_filter_selects_subset() -> None:
    assert _parse_args(["--sources", "BI_JISDOR", "BPS"]).sources == ["BI_JISDOR", "BPS"]


def test_sources_filter_rejects_unknown_source() -> None:
    with pytest.raises(SystemExit):
        _parse_args(["--sources", "NOPE"])


def test_export_web_swallows_storage_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("r2 down")

    monkeypatch.setattr("pipeline.run_monthly.export_web.export_from_env", boom)

    _export_web({}, "run-1")


def test_write_gold_swallows_storage_failure() -> None:
    class BoomStore:
        def write(self, *args: object, **kwargs: object) -> None:
            raise RuntimeError("r2 down")

    _write_gold(BoomStore(), {}, "run-1")


def test_run_source_alerts_on_failure_without_leaking_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bronze, silver = stores()
    ops = StubOps()
    sent: list[tuple[str | None, dict[str, object]]] = []
    monkeypatch.setenv("ALERT_WEBHOOK_URL", "https://hooks.test/SECRET")
    monkeypatch.setattr(
        "pipeline.run_monthly.notify.send",
        lambda url, payload: sent.append((url, payload)) or True,
    )

    def boom(*args: object) -> None:
        raise RuntimeError(
            "https://webapi.bps.go.id/v1/api/list/model/data/domain/0000/var/1/th/1/key/SECRET123/"
        )

    status, _ = _run_source(
        "BPS",
        boom,
        CONFIG,
        "run-1",
        date(2020, 1, 1),
        date(2020, 1, 2),
        bronze,
        silver,
        ops,
    )

    assert status == "failed"
    assert "SECRET123" not in str(ops.sources[0].message)
    assert sent
    assert sent[0][0] == "https://hooks.test/SECRET"
    assert sent[0][1]["check"] == "source_run"
    assert sent[0][1]["source_id"] == "BPS"
    assert sent[0][1]["status"] == "failed"
    assert "SECRET123" not in str(sent[0][1]["error"])


def test_export_web_alerts_on_storage_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[tuple[str | None, dict[str, object]]] = []
    monkeypatch.setenv("ALERT_WEBHOOK_URL", "https://hooks.test/SECRET")
    monkeypatch.setattr(
        "pipeline.run_monthly.notify.send",
        lambda url, payload: sent.append((url, payload)) or True,
    )

    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("r2 down")

    monkeypatch.setattr("pipeline.run_monthly.export_web.export_from_env", boom)

    _export_web({}, "run-1")

    assert sent
    assert sent[0][1]["check"] == "web_export"
    assert sent[0][1]["status"] == "failed"
