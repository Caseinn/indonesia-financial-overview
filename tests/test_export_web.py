"""Web export: JSON shaping, manifest checksums, and R2 object keys."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from pipeline import export_web
from pipeline.storage.s3 import S3Error
from tests.storage.fakes import FakeS3

MOMENT = datetime(2026, 10, 30, 9, 0, tzinfo=UTC)


def snapshot() -> dict[str, list[dict[str, object]]]:
    return {
        "financial_overview_monthly": [
            {
                "month_start": date(2026, 9, 1),
                "policy_rate": Decimal("5.75"),
                "usd_idr_jisdor": None,
            }
        ]
    }


def test_dumps_serializes_decimal_and_dates() -> None:
    payload = json.loads(
        export_web.dumps({"value": Decimal("5.75"), "day": date(2026, 9, 1), "ts": MOMENT})
    )

    assert payload == {"value": 5.75, "day": "2026-09-01", "ts": "2026-10-30T09:00:00+00:00"}


def test_dumps_is_deterministic() -> None:
    assert export_web.dumps({"b": 1, "a": 2}) == export_web.dumps({"a": 2, "b": 1})


def test_build_objects_writes_manifest_with_checksums() -> None:
    objects = export_web.build_objects(
        snapshot(), prefix="/web/data/", run_id="run-1", generated_at=MOMENT
    )

    assert set(objects) == {
        "web/data/financial_overview_monthly.json",
        "web/data/manifest.json",
    }
    manifest = json.loads(objects["web/data/manifest.json"])
    assert manifest["run_id"] == "run-1"
    assert manifest["generated_at"] == "2026-10-30T09:00:00+00:00"
    assert manifest["views"]["financial_overview_monthly"]["rows"] == 1
    assert len(manifest["views"]["financial_overview_monthly"]["sha256"]) == 64


def test_export_snapshot_uploads_every_object() -> None:
    store = FakeS3()

    keys = export_web.export_snapshot(
        snapshot(),
        store,
        "bucket",
        run_id="run-1",
        prefix="web/data",
        generated_at=MOMENT,
    )

    assert sorted(keys) == [
        "web/data/financial_overview_monthly.json",
        "web/data/manifest.json",
    ]
    assert all(
        content_type == export_web.CONTENT_TYPE for _, content_type in store.objects.values()
    )


def test_normalize_prefix_trims_slashes_and_defaults() -> None:
    assert export_web.normalize_prefix("/web/data/") == "web/data"
    assert export_web.normalize_prefix("") == export_web.DEFAULT_PREFIX


def test_export_from_env_requires_public_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("R2_PUBLIC_BUCKET", raising=False)

    with pytest.raises(S3Error):
        export_web.export_from_env(snapshot(), run_id="run-1")


def test_write_gold_swallows_storage_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("r2 down")

    monkeypatch.setattr("pipeline.export_web.gold_from_env", boom)

    export_web._write_gold({}, "run-1")


def test_export_to_directory_writes_flat_json(tmp_path: Path) -> None:
    written = export_web.export_to_directory(
        snapshot(), tmp_path, run_id="run-1", generated_at=MOMENT
    )

    assert sorted(path.name for path in written) == [
        "financial_overview_monthly.json",
        "manifest.json",
    ]
    assert json.loads((tmp_path / "manifest.json").read_text())["run_id"] == "run-1"
