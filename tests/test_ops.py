"""Ops store: append-only run records and the latest-per-source pointer."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from pipeline.ops import OpsStore, PipelineRunRecord, SourceRunRecord
from tests.storage.fakes import FakeS3

AT = datetime(2026, 10, 30, 9, 0, tzinfo=UTC)


def source_record(*, source_id: str = "BI_SEKI", status: str = "ok") -> SourceRunRecord:
    return SourceRunRecord(
        run_id="run-1",
        source_id=source_id,
        status=status,
        finished_at=AT,
        rows_published=12,
        revisions=1,
        publication_checksums=("a" * 64,),
        message=None,
    )


def test_write_source_records_the_run_and_the_pointer() -> None:
    client = FakeS3()
    store = OpsStore(client, "bucket")

    store.write_source(source_record())

    keys = set(client.objects)
    assert keys == {
        "ops/runs/run-1/sources/BI_SEKI.json",
        "ops/latest/BI_SEKI.json",
    }
    payload = json.loads(client.objects["ops/latest/BI_SEKI.json"][0])
    assert payload["rows_published"] == 12
    assert payload["finished_at"] == "2026-10-30T09:00:00+00:00"


def test_latest_source_runs_round_trips_and_skips_absent_sources() -> None:
    store = OpsStore(FakeS3(), "bucket")
    store.write_source(source_record(source_id="BI_SEKI", status="failed"))

    latest = store.latest_source_runs(["BI_SEKI", "BPS"])

    assert set(latest) == {"BI_SEKI"}
    assert latest["BI_SEKI"].status == "failed"
    assert latest["BI_SEKI"].publication_checksums == ("a" * 64,)


def test_two_adapter_runs_for_one_source_merge() -> None:
    store = OpsStore(FakeS3(), "bucket")
    store.write_source(source_record(source_id="OJK_SPI", status="ok"))
    store.write_source(
        SourceRunRecord(
            run_id="run-1",
            source_id="OJK_SPI",
            status="failed",
            finished_at=AT,
            rows_published=3,
            revisions=2,
            publication_checksums=("b" * 64,),
            message="boom",
        )
    )

    latest = store.latest_source_runs(["OJK_SPI"])["OJK_SPI"]

    assert latest.status == "failed"
    assert latest.rows_published == 15
    assert latest.revisions == 3
    assert latest.publication_checksums == ("a" * 64, "b" * 64)
    assert latest.message == "boom"


def test_write_run_is_idempotent_on_the_same_key() -> None:
    client = FakeS3()
    store = OpsStore(client, "bucket")
    store.write_run(PipelineRunRecord("run-1", "running", "schedule", AT))
    store.write_run(
        PipelineRunRecord("run-1", "ok", "schedule", AT, finished_at=AT, message="BI_SEKI=ok")
    )

    payload = json.loads(client.objects["ops/runs/run-1/pipeline.json"][0])
    assert payload["status"] == "ok"
    assert payload["finished_at"] == "2026-10-30T09:00:00+00:00"
    assert len(client.objects) == 1


def test_quarantine_ledger_unions_and_skips_absent_sources() -> None:
    client = FakeS3()
    store = OpsStore(client, "bucket")

    store.record_quarantine("BI_SEKI", ("a" * 64,), at=AT)
    merged = store.record_quarantine("BI_SEKI", ("b" * 64,), at=AT)

    assert merged == ("a" * 64, "b" * 64)
    assert store.quarantined_checksums(["BI_SEKI", "BPS"]) == {"BI_SEKI": ("a" * 64, "b" * 64)}
    payload = json.loads(client.objects["ops/quarantine/BI_SEKI.json"][0])
    assert payload["source_id"] == "BI_SEKI"
    assert payload["checksums"] == ["a" * 64, "b" * 64]
    assert payload["updated_at"] == "2026-10-30T09:00:00+00:00"
