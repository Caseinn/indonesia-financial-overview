"""Persist raw Publications to Bronze as write-once objects.

Bronze is the audit trail: every Source file lands under
``source=<>/edition_period=<>/publication_checksum=<>/`` and is never
overwritten or deleted. Re-published editions become new Publications whose
manifest records the checksum they supersede (ADR-0002), and the manifest is
written last so its presence marks a Publication complete.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from botocore.exceptions import ClientError

from pipeline.models import Artifact, IngestionEnvelope
from pipeline.parsing import sha256_hex
from pipeline.storage.s3 import ObjectStore, client_from_env, is_missing

_logger = logging.getLogger(__name__)

ROOT = "bronze"
MANIFEST_NAME = "manifest.json"


class BronzeError(RuntimeError):
    """Raised when Bronze configuration or transport is unusable."""


@dataclass(frozen=True, slots=True)
class BronzeFile:
    """One stored artifact, identified by its checksum."""

    name: str
    sha256: str
    size: int
    content_type: str

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "sha256": self.sha256,
            "size": self.size,
            "content_type": self.content_type,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> BronzeFile:
        return cls(
            name=str(raw["name"]),
            sha256=str(raw["sha256"]),
            size=int(raw["size"]),
            content_type=str(raw["content_type"]),
        )


@dataclass(frozen=True, slots=True)
class Publication:
    """A stored Edition: the envelope's provenance plus where it now lives."""

    source_id: str
    edition_period: str
    publication_checksum: str
    source_url: str
    period_start: date
    period_end: date
    retrieved_at: datetime
    ingestion_run_id: str
    source_version: int
    files: tuple[BronzeFile, ...]
    supersedes: tuple[str, ...] = ()

    @property
    def key_prefix(self) -> str:
        return (
            f"{ROOT}/source={self.source_id}"
            f"/edition_period={self.edition_period}"
            f"/publication_checksum={self.publication_checksum}"
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "edition_period": self.edition_period,
            "publication_checksum": self.publication_checksum,
            "source_url": self.source_url,
            "period_start": self.period_start.isoformat(),
            "period_end": self.period_end.isoformat(),
            "retrieved_at": self.retrieved_at.isoformat(),
            "ingestion_run_id": self.ingestion_run_id,
            "source_version": self.source_version,
            "supersedes": list(self.supersedes),
            "files": [entry.to_dict() for entry in self.files],
        }

    def to_json_bytes(self) -> bytes:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2).encode("utf-8")

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Publication:
        return cls(
            source_id=str(raw["source_id"]),
            edition_period=str(raw["edition_period"]),
            publication_checksum=str(raw["publication_checksum"]),
            source_url=str(raw["source_url"]),
            period_start=date.fromisoformat(raw["period_start"]),
            period_end=date.fromisoformat(raw["period_end"]),
            retrieved_at=datetime.fromisoformat(raw["retrieved_at"]),
            ingestion_run_id=str(raw["ingestion_run_id"]),
            source_version=int(raw["source_version"]),
            files=tuple(BronzeFile.from_dict(entry) for entry in raw["files"]),
            supersedes=tuple(str(item) for item in raw.get("supersedes", ())),
        )


def edition_label(period_start: date, period_end: date) -> str:
    """Derive a human-readable Edition label from a Publication's period.

    The label identifies the Edition, so it only collapses a single-day range;
    any wider range keeps both endpoints, because a coarser name (a month or a
    year) would let two distinct ranges share a partition and wrongly chain one
    as superseding the other. A source whose Edition is genuinely one month or
    one year passes that label explicitly.
    """
    if period_start == period_end:
        return period_start.strftime("%Y-%m-%d")
    return f"{period_start:%Y-%m-%d}_{period_end:%Y-%m-%d}"


class BronzeStore:
    """Writes Publications to an S3-compatible bucket, once and only once."""

    def __init__(self, client: ObjectStore, bucket: str, root: str = ROOT) -> None:
        self._client = client
        self._bucket = bucket
        self._root = root.strip("/")

    def write(
        self,
        envelope: IngestionEnvelope,
        artifacts: tuple[Artifact, ...],
        *,
        edition_period: str | None = None,
    ) -> Publication:
        """Store one Publication's files and manifest, or return the existing one.

        The (source, edition, checksum) triple is the identity, so a rerun with
        the same bytes is a no-op; a changed checksum is a new Publication that
        records the checksum it supersedes.
        """
        if not artifacts:
            raise BronzeError(f"{envelope.source_id}: no artifacts to store")

        label = edition_period or edition_label(envelope.period_start, envelope.period_end)
        prefix = (
            f"{self._root}/source={envelope.source_id}"
            f"/edition_period={label}"
            f"/publication_checksum={envelope.source_file_sha256}"
        )
        existing = self._read(prefix)
        if existing is not None:
            _logger.info("bronze: %s already stored, keeping it", prefix)
            return existing

        supersedes = tuple(
            checksum
            for checksum in self._publications(envelope.source_id, label)
            if checksum != envelope.source_file_sha256
        )
        files = tuple(self._put_file(prefix, artifact) for artifact in artifacts)
        publication = Publication(
            source_id=envelope.source_id,
            edition_period=label,
            publication_checksum=envelope.source_file_sha256,
            source_url=envelope.source_url,
            period_start=envelope.period_start,
            period_end=envelope.period_end,
            retrieved_at=envelope.retrieved_at,
            ingestion_run_id=envelope.ingestion_run_id,
            source_version=envelope.source_version,
            files=files,
            supersedes=supersedes,
        )
        self._put_object(
            f"{prefix}/{MANIFEST_NAME}", publication.to_json_bytes(), "application/json"
        )
        return publication

    def _put_file(self, prefix: str, artifact: Artifact) -> BronzeFile:
        self._put_object(f"{prefix}/{artifact.name}", artifact.content, artifact.content_type)
        return BronzeFile(
            name=artifact.name,
            sha256=sha256_hex(artifact.content),
            size=len(artifact.content),
            content_type=artifact.content_type,
        )

    def _put_object(self, key: str, body: bytes, content_type: str) -> None:
        if self._exists(key):
            _logger.info("bronze: %s already present, kept", key)
            return
        self._client.put_object(Bucket=self._bucket, Key=key, Body=body, ContentType=content_type)

    def _exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
            return True
        except ClientError as exc:
            if is_missing(exc):
                return False
            raise

    def _read(self, prefix: str) -> Publication | None:
        key = f"{prefix}/{MANIFEST_NAME}"
        if not self._exists(key):
            return None
        response = self._client.get_object(Bucket=self._bucket, Key=key)
        return Publication.from_dict(json.loads(response["Body"].read()))

    def _publications(self, source_id: str, label: str) -> list[str]:
        prefix = f"{self._root}/source={source_id}/edition_period={label}/"
        response = self._client.list_objects_v2(Bucket=self._bucket, Prefix=prefix, Delimiter="/")
        checksums = [
            entry["Prefix"].rstrip("/").rsplit("=", 1)[-1]
            for entry in response.get("CommonPrefixes", [])
        ]
        return sorted(checksums)


def store_from_env(root: str = ROOT) -> BronzeStore:
    """Build a BronzeStore from the R2 environment variables, or fail loudly."""
    client, bucket = client_from_env()
    return BronzeStore(client, bucket, root=root)
