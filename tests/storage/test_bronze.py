"""Bronze store behaviour: write-once objects, manifest, and supersedes chains."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

import pytest

from pipeline.models import Artifact, IngestionEnvelope
from pipeline.parsing import sha256_hex
from pipeline.storage.bronze import (
    BronzeError,
    BronzeStore,
    edition_label,
    store_from_env,
)
from pipeline.storage.s3 import S3Error
from tests.storage.fakes import FakeS3


def make_envelope(
    *,
    sha: str = "a" * 64,
    source_id: str = "BI_JISDOR",
    period_start: date = date(2020, 1, 1),
    period_end: date = date(2020, 3, 31),
) -> IngestionEnvelope:
    return IngestionEnvelope(
        source_id=source_id,
        source_url="https://example.test/source",
        retrieved_at=datetime(2026, 10, 16, 8, 0, tzinfo=UTC),
        period_start=period_start,
        period_end=period_end,
        source_file_sha256=sha,
        ingestion_run_id="run-1",
        source_version=1,
    )


def artifact(name: str = "export.xlsx", content: bytes = b"raw-bytes") -> Artifact:
    return Artifact(name=name, content_type="application/vnd.ms-excel", content=content)


def test_write_stores_files_and_manifest() -> None:
    client = FakeS3()
    store = BronzeStore(client, "bucket")

    publication = store.write(make_envelope(), (artifact(),))

    prefix = (
        "bronze/source=BI_JISDOR/edition_period=2020-01-01_2020-03-31"
        "/publication_checksum=" + "a" * 64
    )
    assert publication.key_prefix == prefix
    assert f"{prefix}/export.xlsx" in client.objects
    stored, content_type = client.objects[f"{prefix}/export.xlsx"]
    assert stored == b"raw-bytes"
    assert content_type == "application/vnd.ms-excel"

    manifest = json.loads(client.objects[f"{prefix}/manifest.json"][0])
    assert manifest["publication_checksum"] == "a" * 64
    assert manifest["edition_period"] == "2020-01-01_2020-03-31"
    assert manifest["files"] == [
        {
            "name": "export.xlsx",
            "sha256": sha256_hex(b"raw-bytes"),
            "size": len(b"raw-bytes"),
            "content_type": "application/vnd.ms-excel",
        }
    ]


def test_write_is_write_once() -> None:
    client = FakeS3()
    store = BronzeStore(client, "bucket")
    envelope = make_envelope()

    first = store.write(envelope, (artifact(),))
    calls_after_first = list(client.put_calls)
    second = store.write(envelope, (artifact(),))

    assert second == first
    assert client.put_calls == calls_after_first


def test_republished_edition_records_supersedes() -> None:
    client = FakeS3()
    store = BronzeStore(client, "bucket")

    store.write(make_envelope(sha="a" * 64), (artifact(content=b"old"),))
    republished = store.write(make_envelope(sha="b" * 64), (artifact(content=b"new"),))

    assert republished.supersedes == ("a" * 64,)
    assert any("publication_checksum=" + "a" * 64 in key for key in client.objects)
    assert any("publication_checksum=" + "b" * 64 in key for key in client.objects)


def test_write_requires_artifacts() -> None:
    store = BronzeStore(FakeS3(), "bucket")
    with pytest.raises(BronzeError):
        store.write(make_envelope(), ())


def test_write_respects_explicit_edition_period() -> None:
    client = FakeS3()
    store = BronzeStore(client, "bucket")

    store.write(make_envelope(), (artifact(),), edition_period="2020-Q1")

    assert any("edition_period=2020-Q1" in key for key in client.objects)


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        (date(2020, 5, 4), date(2020, 5, 4), "2020-05-04"),
        (date(2020, 5, 1), date(2020, 5, 31), "2020-05-01_2020-05-31"),
        (date(2020, 1, 1), date(2020, 12, 31), "2020-01-01_2020-12-31"),
        (date(2019, 6, 1), date(2020, 6, 30), "2019-06-01_2020-06-30"),
    ],
)
def test_edition_label(start: date, end: date, expected: str) -> None:
    assert edition_label(start, end) == expected


def test_store_from_env_reports_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET"):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(S3Error):
        store_from_env()
