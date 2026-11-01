"""Persist the Gold tables as Parquet in R2.

Gold's tabular layer is persisted as Parquet in R2: facts and dimensions are
written under ``gold/`` on every Run, with a manifest recording the Run, row
counts, and per-table checksums. The tables are derived from Silver and are
never read back as a pipeline input; Silver remains the source of truth
(ADR-0008, ADR-0012).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from datetime import UTC, datetime
from io import BytesIO

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from pipeline.parsing import sha256_hex
from pipeline.storage.s3 import ObjectStore, client_from_env

_logger = logging.getLogger(__name__)

DEFAULT_PREFIX = "gold"
MANIFEST_NAME = "manifest.json"
SCHEMA_VERSION = 1
PARQUET_CONTENT_TYPE = "application/vnd.apache.parquet"
JSON_CONTENT_TYPE = "application/json; charset=utf-8"

SCHEMAS: dict[str, pa.Schema] = {
    "dim_source": pa.schema(
        [
            ("source_id", pa.string()),
            ("name", pa.string()),
            ("artifact", pa.string()),
            ("url", pa.string()),
            ("cadence_frequency", pa.string()),
            ("refresh_days", pa.int32()),
            ("probe_start_day", pa.int32()),
            ("probe_end_day", pa.int32()),
        ]
    ),
    "dim_events": pa.schema(
        [
            ("event_date", pa.date32()),
            ("code", pa.string()),
            ("category", pa.string()),
            ("title", pa.string()),
            ("description", pa.string()),
            ("source_url", pa.string()),
        ]
    ),
    "fact_macro_periodic": pa.schema(
        [
            ("indicator_code", pa.string()),
            ("period_start", pa.date32()),
            ("frequency", pa.string()),
            ("entity_code", pa.string()),
            ("sector_code", pa.string()),
            ("value", pa.float64()),
            ("unit", pa.string()),
            ("source_id", pa.string()),
            ("source_table", pa.string()),
            ("geography_code", pa.string()),
            ("dimension_code", pa.string()),
            ("first_published_value", pa.float64()),
            ("revision_count", pa.int32()),
            ("last_revised_at", pa.timestamp("us", tz="UTC")),
            ("retrieved_at", pa.timestamp("us", tz="UTC")),
        ]
    ),
    "fact_market_daily": pa.schema(
        [
            ("indicator_code", pa.string()),
            ("obs_date", pa.date32()),
            ("entity_code", pa.string()),
            ("value", pa.float64()),
            ("unit", pa.string()),
            ("source_id", pa.string()),
            ("geography_code", pa.string()),
            ("dimension_code", pa.string()),
            ("first_published_value", pa.float64()),
            ("revision_count", pa.int32()),
            ("last_revised_at", pa.timestamp("us", tz="UTC")),
            ("retrieved_at", pa.timestamp("us", tz="UTC")),
        ]
    ),
}


def normalize_prefix(prefix: str) -> str:
    """Trim surrounding slashes so keys are composed predictably."""
    return prefix.strip("/") or DEFAULT_PREFIX


def to_parquet(frame: pd.DataFrame, schema: pa.Schema) -> bytes:
    """Encode one Gold table with its fixed schema and snappy compression."""
    table = pa.Table.from_pandas(frame, schema=schema, preserve_index=False)
    buffer = BytesIO()
    pq.write_table(table, buffer, compression="snappy")
    return buffer.getvalue()


def build_objects(
    tables: Mapping[str, pd.DataFrame],
    *,
    prefix: str = DEFAULT_PREFIX,
    run_id: str,
    generated_at: datetime,
) -> dict[str, bytes]:
    """Render every table as Parquet plus a manifest of rows and checksums."""
    base = normalize_prefix(prefix)
    objects: dict[str, bytes] = {}
    manifest_tables: dict[str, dict[str, object]] = {}
    for name, frame in tables.items():
        schema = SCHEMAS.get(name)
        if schema is None:
            raise ValueError(f"unknown Gold table: {name}")
        body = to_parquet(frame, schema)
        objects[f"{base}/{name}.parquet"] = body
        manifest_tables[name] = {"rows": len(frame), "sha256": sha256_hex(body)}
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "generated_at": generated_at.astimezone(UTC).isoformat(),
        "tables": manifest_tables,
    }
    objects[f"{base}/{MANIFEST_NAME}"] = json.dumps(
        manifest,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return objects


class GoldStore:
    """Writes the derived Gold tables to R2 as Parquet objects."""

    def __init__(
        self,
        client: ObjectStore,
        bucket: str,
        *,
        prefix: str = DEFAULT_PREFIX,
    ) -> None:
        self._client = client
        self._bucket = bucket
        self._prefix = normalize_prefix(prefix)

    def write(
        self,
        tables: Mapping[str, pd.DataFrame],
        *,
        run_id: str,
        generated_at: datetime | None = None,
    ) -> list[str]:
        """Write every table and the manifest, returning the keys written."""
        moment = generated_at or datetime.now(UTC)
        objects = build_objects(
            tables,
            prefix=self._prefix,
            run_id=run_id,
            generated_at=moment,
        )
        for key, body in objects.items():
            content_type = (
                JSON_CONTENT_TYPE if key.endswith(MANIFEST_NAME) else PARQUET_CONTENT_TYPE
            )
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=body,
                ContentType=content_type,
            )
        _logger.info("gold: wrote %d objects under %s/", len(objects), self._prefix)
        return list(objects)


def store_from_env(*, prefix: str = DEFAULT_PREFIX) -> GoldStore:
    """Build a GoldStore from the private R2 environment, or fail loudly."""
    client, bucket = client_from_env()
    return GoldStore(client, bucket, prefix=prefix)
