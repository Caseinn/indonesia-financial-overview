"""Silver store behaviour: partitioned inserts, idempotent reruns, revisions."""

from __future__ import annotations

from datetime import UTC, date, datetime
from io import BytesIO

import pandas as pd
import pyarrow.parquet as pq
import pytest

from pipeline.models import Observation
from pipeline.storage.s3 import S3Error
from pipeline.storage.silver import SCHEMA, SilverStore, store_from_env
from tests.storage.fakes import FakeS3

AT = datetime(2026, 10, 16, 8, 0, tzinfo=UTC)


def observation(
    *,
    period_start: date = date(2020, 1, 1),
    value: float = 14000.0,
    indicator: str = "USDIRR_JISDOR",
    dimension: str = "",
    sha: str = "a" * 64,
) -> Observation:
    return Observation(
        source_id="BI_JISDOR",
        source_table="JISDOR",
        indicator_code=indicator,
        period_start=period_start,
        period_end=period_start,
        frequency="daily",
        geography_code="IDN",
        original_value=value,
        original_unit="idr_per_usd",
        normalized_value=value,
        normalized_unit="idr_per_usd",
        source_raw_label="Kurs",
        retrieved_at=AT,
        source_file_sha256=sha,
        ingestion_run_id="run-1",
        dimension_code=dimension,
    )


def part_key(source_id: str = "BI_JISDOR", year: int = 2020) -> str:
    return f"silver/macro_observations/source={source_id}/year={year}/part-000.parquet"


def read_frame(client: FakeS3, source_id: str = "BI_JISDOR", year: int = 2020) -> pd.DataFrame:
    return pq.read_table(BytesIO(client.objects[part_key(source_id, year)][0])).to_pandas()


def test_upsert_partitions_by_source_and_year() -> None:
    client = FakeS3()
    store = SilverStore(client, "bucket")

    result = store.upsert(
        (observation(period_start=date(2020, 1, 1)), observation(period_start=date(2021, 1, 1)))
    )

    assert result.written == 2
    assert result.unchanged == 0
    assert result.partitions == (part_key(year=2020), part_key(year=2021))
    frame = read_frame(client, year=2020)
    assert list(frame.columns) == list(SCHEMA.names)
    assert frame.loc[0, "is_current"]
    assert frame.loc[0, "indicator_code"] == "USDIRR_JISDOR"


def test_rerun_with_same_values_is_unchanged() -> None:
    client = FakeS3()
    store = SilverStore(client, "bucket")

    store.upsert((observation(),))
    result = store.upsert((observation(),))

    assert result.written == 0
    assert result.unchanged == 1
    assert result.revisions == ()
    assert len(read_frame(client)) == 1


def test_changed_value_supersedes_and_appends() -> None:
    client = FakeS3()
    store = SilverStore(client, "bucket")

    store.upsert((observation(value=14000.0, sha="a" * 64),))
    result = store.upsert((observation(value=14500.0, sha="b" * 64),), at=AT)

    assert result.written == 1
    assert result.unchanged == 0
    assert len(result.revisions) == 1
    revision = result.revisions[0]
    assert revision.old_value == 14000.0
    assert revision.new_value == 14500.0
    assert revision.old_sha256 == "a" * 64
    assert revision.new_sha256 == "b" * 64

    frame = read_frame(client)
    assert len(frame) == 2
    superseded = frame[~frame["is_current"]]
    assert len(superseded) == 1
    assert superseded.iloc[0]["normalized_value"] == 14000.0
    assert superseded.iloc[0]["superseded_at"] == pd.Timestamp(AT)
    current = frame[frame["is_current"]]
    assert current.iloc[0]["normalized_value"] == 14500.0


def test_dimension_code_is_part_of_the_key() -> None:
    client = FakeS3()
    store = SilverStore(client, "bucket")

    store.upsert((observation(dimension="SECTOR_A"),))
    result = store.upsert((observation(dimension="SECTOR_B", value=99.0),))

    assert result.written == 1
    assert result.revisions == ()
    frame = read_frame(client)
    assert set(frame["dimension_code"]) == {"SECTOR_A", "SECTOR_B"}
    assert frame["is_current"].all()


def test_empty_observations_is_a_noop() -> None:
    client = FakeS3()
    store = SilverStore(client, "bucket")

    result = store.upsert(())

    assert result.written == 0
    assert result.partitions == ()
    assert client.put_calls == []


def test_current_values_returns_the_published_snapshot() -> None:
    client = FakeS3()
    store = SilverStore(client, "bucket")
    store.upsert((observation(value=14000.0),))

    values = store.current_values((observation(),))

    assert values == {observation().business_key: 14000.0}


def test_current_values_falls_back_to_the_previous_revision_when_excluded() -> None:
    client = FakeS3()
    store = SilverStore(client, "bucket")
    store.upsert((observation(value=14000.0, sha="a" * 64),))
    store.upsert((observation(value=20000.0, sha="b" * 64),), at=AT)

    values = store.current_values((observation(),), excluded_checksums=("b" * 64,))

    assert values == {observation().business_key: 14000.0}


def test_frame_for_concatenates_written_partitions() -> None:
    client = FakeS3()
    store = SilverStore(client, "bucket")
    write = store.upsert((observation(), observation(period_start=date(2021, 1, 1))))

    frame = store.frame_for(write.partitions)

    assert len(frame) == 2
    assert list(frame.columns) == list(SCHEMA.names)


def test_read_all_concatenates_every_partition() -> None:
    client = FakeS3()
    store = SilverStore(client, "bucket")
    store.upsert(
        (
            observation(period_start=date(2020, 1, 1)),
            observation(period_start=date(2021, 1, 1), value=14500.0),
        )
    )

    frame = store.read_all()

    assert len(frame) == 2
    assert list(frame.columns) == list(SCHEMA.names)
    assert set(frame["normalized_value"]) == {14000.0, 14500.0}


def test_read_all_on_empty_store_returns_an_empty_frame() -> None:
    store = SilverStore(FakeS3(), "bucket")

    frame = store.read_all()

    assert frame.empty
    assert list(frame.columns) == list(SCHEMA.names)


def test_store_from_env_reports_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET"):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(S3Error):
        store_from_env()
