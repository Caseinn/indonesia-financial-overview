"""Shared ingestion contracts.

Adapters return these shapes and never invent ad-hoc dicts, so Silver, Gold,
and the quality gates all read one vocabulary. Envelopes and run results are
frozen; ``Observation`` stays mutable so ``is_current`` and ``superseded_at``
can carry revision state.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum


class SourceRunStatus(StrEnum):
    """Outcome of one adapter run for one Source within a Run."""

    OK = "ok"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class IngestionEnvelope:
    """Provenance for one adapter run against one Publication.

    Business identity excludes ``source_file_sha256``: the checksum is lineage,
    not identity, so a re-publication of the same Edition still differs here.
    """

    source_id: str
    source_url: str
    retrieved_at: datetime
    period_start: date
    period_end: date
    source_file_sha256: str
    ingestion_run_id: str
    source_version: int


@dataclass(slots=True)
class Observation:
    """One Indicator value for one Reporting Period and geography.

    ``original_*`` preserves the source's own figure and label; ``normalized_*``
    is the pipeline's canonical form. Both are kept so a Revision stays
    traceable back to exactly what the Source published.
    """

    source_id: str
    source_table: str
    indicator_code: str
    period_start: date
    period_end: date
    frequency: str
    geography_code: str
    original_value: float
    original_unit: str
    normalized_value: float
    normalized_unit: str
    source_raw_label: str
    retrieved_at: datetime
    source_file_sha256: str
    ingestion_run_id: str
    dimension_code: str = ""
    is_current: bool = True
    superseded_at: datetime | None = None

    @property
    def business_key(self) -> tuple[str, str, str, date, str, str]:
        """Identity of an Observation, excluding checksum and revision flags.

        ``dimension_code`` is the optional second axis (a sector, bank group, or
        credit quality); single-series Observations leave it empty.
        """
        return (
            self.source_id,
            self.source_table,
            self.indicator_code,
            self.period_start,
            self.geography_code,
            self.dimension_code,
        )

    @classmethod
    def from_source(
        cls,
        envelope: IngestionEnvelope,
        *,
        source_table: str,
        indicator_code: str,
        period_start: date,
        period_end: date,
        frequency: str,
        value: float,
        unit: str,
        source_raw_label: str,
        geography_code: str = "IDN",
        dimension_code: str = "",
        source_file_sha256: str | None = None,
    ) -> Observation:
        """Build an Observation from an envelope plus the source's own figure.

        ``original_*`` and ``normalized_*`` start identical; an adapter that must
        normalize differently can set those fields itself. ``source_file_sha256``
        defaults to the envelope's checksum but may be overridden per response.
        """
        return cls(
            source_id=envelope.source_id,
            source_table=source_table,
            indicator_code=indicator_code,
            period_start=period_start,
            period_end=period_end,
            frequency=frequency,
            geography_code=geography_code,
            original_value=value,
            original_unit=unit,
            normalized_value=value,
            normalized_unit=unit,
            source_raw_label=source_raw_label,
            retrieved_at=envelope.retrieved_at,
            source_file_sha256=source_file_sha256 or envelope.source_file_sha256,
            ingestion_run_id=envelope.ingestion_run_id,
            dimension_code=dimension_code,
        )


@dataclass(frozen=True, slots=True)
class Artifact:
    """One raw source file handed to Bronze, exactly as the Source served it.

    Adapters attach the bytes they downloaded so Bronze can persist them
    write-once; the checksum and size are derived at write time, never supplied.
    """

    name: str
    content_type: str
    content: bytes


@dataclass(frozen=True, slots=True)
class SourceRunResult:
    """What one adapter hands back to the pipeline for a Source."""

    envelope: IngestionEnvelope
    observations: tuple[Observation, ...] = ()
    artifacts: tuple[Artifact, ...] = ()
    status: SourceRunStatus = SourceRunStatus.OK
