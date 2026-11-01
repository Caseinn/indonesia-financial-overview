"""Normalize Observations into Silver and keep their full revision history.

Silver is long-form ``macro_observations`` Parquet partitioned by source and
year. Observations are upserted on their business key (ADR-0001): a rerun with
identical values is a no-op, a changed value flips ``is_current`` on the old row
and appends the new one, so Gold can read current rows while the revision view
still exposes superseded ones. The value shift is handed back as a ``Revision``
so the drift gate can flag it (ADR-0002).
"""

from __future__ import annotations

import logging
from collections.abc import Collection, Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from io import BytesIO

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from botocore.exceptions import ClientError

from pipeline.models import Observation
from pipeline.storage.s3 import ObjectStore, client_from_env, is_missing

_logger = logging.getLogger(__name__)

ROOT = "silver"
DATASET = "macro_observations"
PART_FILE = "part-000.parquet"
CONTENT_TYPE = "application/vnd.apache.parquet"

SCHEMA = pa.schema(
    [
        ("source_id", pa.string()),
        ("source_table", pa.string()),
        ("indicator_code", pa.string()),
        ("period_start", pa.date32()),
        ("period_end", pa.date32()),
        ("frequency", pa.string()),
        ("geography_code", pa.string()),
        ("dimension_code", pa.string()),
        ("original_value", pa.float64()),
        ("original_unit", pa.string()),
        ("normalized_value", pa.float64()),
        ("normalized_unit", pa.string()),
        ("source_raw_label", pa.string()),
        ("retrieved_at", pa.timestamp("us", tz="UTC")),
        ("source_file_sha256", pa.string()),
        ("ingestion_run_id", pa.string()),
        ("is_current", pa.bool_()),
        ("superseded_at", pa.timestamp("us", tz="UTC")),
    ]
)
COLUMNS = tuple(field.name for field in SCHEMA)
KEY_COLUMNS = (
    "source_id",
    "source_table",
    "indicator_code",
    "period_start",
    "geography_code",
    "dimension_code",
)
VALUE_COLUMNS = (
    "original_value",
    "normalized_value",
    "original_unit",
    "normalized_unit",
    "source_raw_label",
)


class SilverError(RuntimeError):
    """Raised when a Silver write cannot be applied."""


@dataclass(frozen=True, slots=True)
class Revision:
    """One Observation whose value changed between Publications."""

    indicator_code: str
    period_start: date
    geography_code: str
    dimension_code: str
    old_value: float
    new_value: float
    old_sha256: str
    new_sha256: str


@dataclass(frozen=True, slots=True)
class SilverWriteResult:
    """What one upsert changed: rows written, rows untouched, and revisions."""

    written: int
    unchanged: int
    revisions: tuple[Revision, ...]
    partitions: tuple[str, ...]


def observation_row(observation: Observation) -> dict[str, object]:
    """Flatten one Observation into a Silver row keyed by the schema columns."""
    return {
        "source_id": observation.source_id,
        "source_table": observation.source_table,
        "indicator_code": observation.indicator_code,
        "period_start": observation.period_start,
        "period_end": observation.period_end,
        "frequency": observation.frequency,
        "geography_code": observation.geography_code,
        "dimension_code": observation.dimension_code,
        "original_value": float(observation.original_value),
        "original_unit": observation.original_unit,
        "normalized_value": float(observation.normalized_value),
        "normalized_unit": observation.normalized_unit,
        "source_raw_label": observation.source_raw_label,
        "retrieved_at": observation.retrieved_at,
        "source_file_sha256": observation.source_file_sha256,
        "ingestion_run_id": observation.ingestion_run_id,
        "is_current": observation.is_current,
        "superseded_at": observation.superseded_at,
    }


class SilverStore:
    """Upserts Observations into partitioned Parquet with revision history."""

    def __init__(
        self,
        client: ObjectStore,
        bucket: str,
        *,
        dataset: str = DATASET,
        root: str = ROOT,
    ) -> None:
        self._client = client
        self._bucket = bucket
        self._dataset = dataset
        self._root = root.strip("/")

    def upsert(
        self,
        observations: tuple[Observation, ...],
        *,
        at: datetime | None = None,
    ) -> SilverWriteResult:
        """Merge Observations into their partitions, superseding changed rows."""
        records = [observation_row(observation) for observation in observations]
        if not records:
            return SilverWriteResult(written=0, unchanged=0, revisions=(), partitions=())

        transition_time = at or datetime.now(UTC)
        grouped: dict[tuple[str, int], list[dict[str, object]]] = {}
        for record in records:
            grouped.setdefault((str(record["source_id"]), record["period_start"].year), []).append(
                record
            )

        revisions: list[Revision] = []
        partitions: list[str] = []
        unchanged = 0
        for (source_id, year), rows in sorted(grouped.items()):
            key = self._path(source_id, year)
            frame, part_revisions, part_unchanged = _merge(self.read(key), rows, transition_time)
            self._write(key, frame)
            revisions.extend(part_revisions)
            unchanged += part_unchanged
            partitions.append(key)

        return SilverWriteResult(
            written=len(records) - unchanged,
            unchanged=unchanged,
            revisions=tuple(revisions),
            partitions=tuple(partitions),
        )

    def current_values(
        self,
        observations: Sequence[Observation],
        *,
        excluded_checksums: Collection[str] = (),
    ) -> dict[tuple[object, ...], float]:
        """Return the currently published value per business key for these Observations.

        Drift is measured against what Gold already shows, so the gate reads the
        pre-upsert snapshot rather than the freshly merged rows. Rejected
        publications are excluded and the previous revision is re-folded, because
        Silver still stores a quarantined row as ``is_current`` after a breaker.
        """
        blocked = frozenset(excluded_checksums)
        values: dict[tuple[object, ...], float] = {}
        partitions = {
            (observation.source_id, observation.period_start.year) for observation in observations
        }
        for source_id, year in sorted(partitions):
            frame = self.read(self._path(source_id, year))
            if frame is None:
                continue
            current = _fold_publishable(frame, blocked) if blocked else frame[frame["is_current"]]
            for _, row in current.iterrows():
                values[_key(row)] = float(row["normalized_value"])
        return values

    def frame_for(self, partitions: Sequence[str]) -> pd.DataFrame:
        """Load and concatenate the Silver partitions a write touched."""
        frames = [frame for key in partitions if (frame := self.read(key)) is not None]
        if not frames:
            return pd.DataFrame(columns=COLUMNS)
        return pd.concat(frames, ignore_index=True)

    def read_all(self) -> pd.DataFrame:
        """Load every Silver partition, because Gold is rebuilt from scratch.

        A full read is the only way to keep the rebuilt Gold consistent: it sees
        Sources that did not run this time as well as the full revision history.
        """
        prefix = f"{self._root}/{self._dataset}/"
        frames = [frame for key in self._keys(prefix) if (frame := self.read(key)) is not None]
        if not frames:
            return pd.DataFrame(columns=COLUMNS)
        return pd.concat(frames, ignore_index=True)

    def _path(self, source_id: str, year: int) -> str:
        return f"{self._root}/{self._dataset}/source={source_id}/year={year}/{PART_FILE}"

    def _keys(self, prefix: str) -> Iterator[str]:
        token: str | None = None
        while True:
            kwargs: dict[str, object] = {"Bucket": self._bucket, "Prefix": prefix}
            if token is not None:
                kwargs["ContinuationToken"] = token
            response = self._client.list_objects_v2(**kwargs)
            for item in response.get("Contents") or ():
                yield str(item["Key"])
            if not response.get("IsTruncated"):
                return
            token = response.get("NextContinuationToken")

    def read(self, key: str) -> pd.DataFrame | None:
        """Read one Silver partition, or return ``None`` when it does not exist."""
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            if is_missing(exc):
                return None
            raise
        return pq.read_table(BytesIO(response["Body"].read())).to_pandas()

    def _write(self, key: str, frame: pd.DataFrame) -> None:
        table = pa.Table.from_pandas(frame, schema=SCHEMA, preserve_index=False)
        buffer = BytesIO()
        pq.write_table(table, buffer, compression="snappy")
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=buffer.getvalue(),
            ContentType=CONTENT_TYPE,
        )


def _merge(
    existing: pd.DataFrame | None,
    incoming: list[dict[str, object]],
    at: datetime,
) -> tuple[pd.DataFrame, list[Revision], int]:
    frame = pd.DataFrame(columns=COLUMNS) if existing is None else existing.reset_index(drop=True)
    current = (
        {_key(row): index for index, row in frame[frame["is_current"]].iterrows()}
        if len(frame)
        else {}
    )

    revisions: list[Revision] = []
    appended: list[dict[str, object]] = []
    unchanged = 0
    for row in incoming:
        index = current.pop(_key(row), None)
        if index is None:
            appended.append(row)
            continue
        previous = frame.loc[index]
        if _signature(previous) == _signature(row):
            unchanged += 1
            continue
        frame.at[index, "is_current"] = False
        frame.at[index, "superseded_at"] = at
        revisions.append(
            Revision(
                indicator_code=str(row["indicator_code"]),
                period_start=row["period_start"],
                geography_code=str(row["geography_code"]),
                dimension_code=str(row["dimension_code"]),
                old_value=float(previous["normalized_value"]),
                new_value=float(row["normalized_value"]),
                old_sha256=str(previous["source_file_sha256"]),
                new_sha256=str(row["source_file_sha256"]),
            )
        )
        appended.append(row)

    if appended:
        frame = pd.concat([frame, pd.DataFrame(appended)], ignore_index=True)
    frame = frame.sort_values(list(KEY_COLUMNS) + ["retrieved_at"]).reset_index(drop=True)
    return frame, revisions, unchanged


def _key(record: object) -> tuple[object, ...]:
    return tuple(record[column] for column in KEY_COLUMNS)


def _signature(record: object) -> tuple[object, ...]:
    return tuple(record[column] for column in VALUE_COLUMNS)


def _fold_publishable(frame: pd.DataFrame, excluded: frozenset[str]) -> pd.DataFrame:
    """Re-derive the current row per key after dropping rejected publications."""
    kept = frame[~frame["source_file_sha256"].isin(excluded)]
    if kept.empty:
        return kept
    ordered = kept.sort_values(list(KEY_COLUMNS) + ["retrieved_at"], kind="stable")
    current = ordered.groupby(list(KEY_COLUMNS), dropna=False, sort=False).tail(1).index
    return kept[kept.index.isin(current)]


def store_from_env(*, dataset: str = DATASET, root: str = ROOT) -> SilverStore:
    """Build a SilverStore from the R2 environment variables, or fail loudly."""
    client, bucket = client_from_env()
    return SilverStore(client, bucket, dataset=dataset, root=root)
