"""Run bookkeeping in object storage instead of a database.

Gold is rebuilt from Silver on every Run, so the audit trail and per-source
freshness must live somewhere durable. Each Source Run writes its own JSON
record under ``ops/runs`` and refreshes a small ``ops/latest`` pointer: a crash
keeps the outcomes already recorded, and freshness never depends on replaying
Silver. Rejected publication checksums live in a separate ``ops/quarantine``
ledger so a later failed fetch cannot forget a quarantine and let the rejected
revision back into Gold.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from botocore.exceptions import ClientError

from pipeline.storage.s3 import ObjectStore, client_from_env, is_missing

_logger = logging.getLogger(__name__)

ROOT = "ops"
QUARANTINE_ROOT = "quarantine"
CONTENT_TYPE = "application/json; charset=utf-8"


@dataclass(frozen=True, slots=True)
class PipelineRunRecord:
    """One Run's overall outcome, written when it starts and when it ends."""

    run_id: str
    status: str
    trigger: str | None
    started_at: datetime
    finished_at: datetime | None = None
    message: str | None = None

    def payload(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "trigger": self.trigger,
            "started_at": self.started_at.isoformat(),
            "finished_at": None if self.finished_at is None else self.finished_at.isoformat(),
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class SourceRunRecord:
    """One Source's outcome within a Run; the unit freshness and quarantine read."""

    run_id: str
    source_id: str
    status: str
    finished_at: datetime
    rows_published: int = 0
    revisions: int = 0
    publication_checksums: tuple[str, ...] = ()
    message: str | None = None

    def payload(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "source_id": self.source_id,
            "status": self.status,
            "finished_at": self.finished_at.isoformat(),
            "rows_published": self.rows_published,
            "revisions": self.revisions,
            "publication_checksums": list(self.publication_checksums),
            "message": self.message,
        }

    @classmethod
    def from_payload(cls, payload: dict[str, object]) -> SourceRunRecord:
        """Rebuild a record from the JSON object written by :meth:`payload`."""
        checksums = payload.get("publication_checksums") or ()
        return cls(
            run_id=str(payload["run_id"]),
            source_id=str(payload["source_id"]),
            status=str(payload["status"]),
            finished_at=datetime.fromisoformat(str(payload["finished_at"])),
            rows_published=int(payload.get("rows_published") or 0),
            revisions=int(payload.get("revisions") or 0),
            publication_checksums=tuple(str(item) for item in checksums),
            message=_optional_str(payload.get("message")),
        )


class OpsStore:
    """Append-only run records plus a latest-pointer index under ``ops/``."""

    def __init__(self, client: ObjectStore, bucket: str, *, root: str = ROOT) -> None:
        self._client = client
        self._bucket = bucket
        self._root = root.strip("/")

    def write_run(self, record: PipelineRunRecord) -> None:
        """Persist one Run's outcome; reruns rewrite the same key."""
        self._put(f"{self._root}/runs/{record.run_id}/pipeline.json", record.payload())

    def write_source(self, record: SourceRunRecord) -> None:
        """Persist a Source Run and refresh its latest pointer.

        Both OJK adapters record under one logical Source, so a second write in
        the same Run merges counts and keeps the strictest status instead of
        overwriting the first adapter's outcome.
        """
        key = f"{self._root}/runs/{record.run_id}/sources/{record.source_id}.json"
        previous = self._get_json(key)
        merged = (
            record
            if previous is None
            else _merge_source(record, SourceRunRecord.from_payload(previous))
        )
        payload = merged.payload()
        self._put(key, payload)
        self._put(f"{self._root}/latest/{record.source_id}.json", payload)

    def latest_source_runs(self, source_ids: Iterable[str]) -> dict[str, SourceRunRecord]:
        """Read the newest record for each configured Source, skipping absent ones."""
        latest: dict[str, SourceRunRecord] = {}
        for source_id in source_ids:
            payload = self._get_json(f"{self._root}/latest/{source_id}.json")
            if payload is not None:
                latest[str(source_id)] = SourceRunRecord.from_payload(payload)
        return latest

    def record_quarantine(
        self,
        source_id: str,
        checksums: Iterable[str],
        *,
        at: datetime | None = None,
    ) -> tuple[str, ...]:
        """Add rejected publication checksums to a Source's durable block list.

        Quarantine is cumulative because a rejected Publication must stay out of
        Gold even after intervening Runs that published nothing; a same-bytes
        re-publication is still the rejected data.
        """
        key = f"{self._root}/{QUARANTINE_ROOT}/{source_id}.json"
        existing = self._get_json(key) or {}
        merged = tuple(
            sorted({str(item) for item in existing.get("checksums") or ()} | set(checksums))
        )
        payload = {
            "source_id": source_id,
            "checksums": list(merged),
            "updated_at": (at or datetime.now(UTC)).isoformat(),
        }
        self._put(key, payload)
        return merged

    def quarantined_checksums(self, source_ids: Iterable[str]) -> dict[str, tuple[str, ...]]:
        """Read the durable rejected-publication block list per Source."""
        quarantined: dict[str, tuple[str, ...]] = {}
        for source_id in source_ids:
            payload = self._get_json(f"{self._root}/{QUARANTINE_ROOT}/{source_id}.json")
            if payload is None:
                continue
            checksums = tuple(str(item) for item in payload.get("checksums") or ())
            if checksums:
                quarantined[str(source_id)] = checksums
        return quarantined

    def _put(self, key: str, payload: dict[str, object]) -> None:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self._client.put_object(Bucket=self._bucket, Key=key, Body=body, ContentType=CONTENT_TYPE)

    def _get_json(self, key: str) -> dict[str, object] | None:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            if is_missing(exc):
                return None
            raise
        return json.loads(response["Body"].read())


def store_from_env(*, root: str = ROOT) -> OpsStore:
    """Build an OpsStore from the R2 environment variables, or fail loudly."""
    client, bucket = client_from_env()
    return OpsStore(client, bucket, root=root)


def _merge_source(new: SourceRunRecord, previous: SourceRunRecord) -> SourceRunRecord:
    """Fold two adapter outcomes for the same logical Source into one record."""
    checksums = tuple(sorted(set(previous.publication_checksums) | set(new.publication_checksums)))
    messages = [text for text in (previous.message, new.message) if text]
    return SourceRunRecord(
        run_id=new.run_id,
        source_id=new.source_id,
        status="ok" if previous.status == "ok" and new.status == "ok" else "failed",
        finished_at=max(previous.finished_at, new.finished_at),
        rows_published=previous.rows_published + new.rows_published,
        revisions=previous.revisions + new.revisions,
        publication_checksums=checksums,
        message="; ".join(messages) or None,
    )


def _optional_str(value: object) -> str | None:
    return None if value is None else str(value)
