"""Gold storage: Parquet encoding, manifest shape, and R2 writes."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from io import BytesIO

import pandas as pd
import pyarrow.parquet as pq
import pytest

from pipeline.storage.gold import SCHEMAS, GoldStore, build_objects, to_parquet
from tests.storage.fakes import FakeS3

MOMENT = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)


def macro_table(*, value: float = 4.75) -> dict[str, pd.DataFrame]:
    columns = [field.name for field in SCHEMAS["fact_macro_periodic"]]
    rows = [
        {
            "indicator_code": "POLICY_RATE",
            "period_start": date(2024, 1, 1),
            "frequency": "monthly",
            "entity_code": "IDN",
            "sector_code": "ALL",
            "value": value,
            "unit": "percent",
            "source_id": "BI_SEKI",
            "source_table": "TABEL1_25_1",
            "geography_code": "IDN",
            "dimension_code": "",
            "first_published_value": value,
            "revision_count": 0,
            "last_revised_at": None,
            "retrieved_at": MOMENT,
        }
    ]
    return {"fact_macro_periodic": pd.DataFrame(rows, columns=columns)}


def test_build_objects_encodes_parquet_and_manifest() -> None:
    objects = build_objects(macro_table(), run_id="run-1", generated_at=MOMENT)

    assert set(objects) == {"gold/fact_macro_periodic.parquet", "gold/manifest.json"}
    frame = pq.read_table(BytesIO(objects["gold/fact_macro_periodic.parquet"])).to_pandas()
    assert frame["indicator_code"].tolist() == ["POLICY_RATE"]
    assert frame["period_start"].tolist() == [date(2024, 1, 1)]
    assert frame["value"].tolist() == [4.75]

    manifest = json.loads(objects["gold/manifest.json"])
    assert manifest["run_id"] == "run-1"
    assert manifest["generated_at"] == MOMENT.isoformat()
    assert manifest["tables"]["fact_macro_periodic"]["rows"] == 1
    assert len(manifest["tables"]["fact_macro_periodic"]["sha256"]) == 64


def test_to_parquet_keeps_the_declared_schema_for_an_empty_table() -> None:
    schema = SCHEMAS["fact_market_daily"]
    body = to_parquet(pd.DataFrame(columns=[field.name for field in schema]), schema)

    assert pq.read_table(BytesIO(body)).schema.remove_metadata() == schema


def test_build_objects_rejects_an_unknown_table() -> None:
    with pytest.raises(ValueError, match="unknown Gold table"):
        build_objects({"nope": pd.DataFrame()}, run_id="run-1", generated_at=MOMENT)


def test_gold_store_writes_every_object() -> None:
    store = FakeS3()
    gold = GoldStore(store, "bucket")

    keys = gold.write(macro_table(), run_id="run-1", generated_at=MOMENT)

    assert set(keys) == set(store.objects)
    assert store.objects["gold/fact_macro_periodic.parquet"][1] == (
        "application/vnd.apache.parquet"
    )
    assert store.objects["gold/manifest.json"][1] == "application/json; charset=utf-8"
