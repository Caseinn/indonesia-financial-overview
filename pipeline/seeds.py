"""Load the curated events Seed into Gold, idempotently.

Events annotate the dashboard with dated context (crises, policy turns) that no
official API serves. The file is the source of truth; its checksum is recorded
in ``ops.source_runs`` so an unchanged Seed is skipped and an edited one
republishes the whole table (ADR-0005: config-like data is projected, not
hand-edited in SQL).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from pipeline.parsing import sha256_hex

DEFAULT_SEED_PATH = Path(__file__).resolve().parents[1] / "seeds" / "events.yml"
SOURCE_ID = "SEED_EVENTS"


class SeedError(ValueError):
    """Raised when the events Seed is malformed."""


@dataclass(frozen=True, slots=True)
class Event:
    """One dated, curated event for dashboard annotation."""

    event_date: date
    code: str
    category: str
    title: str
    description: str = ""
    source_url: str = ""

    def params(self) -> tuple[object, ...]:
        return (
            self.event_date,
            self.code,
            self.category,
            self.title,
            self.description,
            self.source_url,
        )


def seed_checksum(path: Path | str = DEFAULT_SEED_PATH) -> str:
    """Return the Seed file's checksum, the idempotency key for the loader."""
    return sha256_hex(Path(path).read_bytes())


def load_events(path: Path | str = DEFAULT_SEED_PATH) -> tuple[Event, ...]:
    """Parse the events Seed, failing loudly on a malformed entry."""
    try:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    except FileNotFoundError as exc:
        raise SeedError(f"seed file not found: {path}") from exc
    if not isinstance(raw, Mapping):
        raise SeedError(f"seed root must be a mapping: {path}")

    events: list[Event] = []
    for node in raw.get("events") or []:
        if not isinstance(node, Mapping):
            raise SeedError(f"event entry must be a mapping: {node!r}")
        events.append(
            Event(
                event_date=_date(node, "date"),
                code=str(_require(node, "code")),
                category=str(node.get("category", "")),
                title=str(_require(node, "title")),
                description=str(node.get("description", "")),
                source_url=str(node.get("source_url", "")),
            )
        )
    return tuple(events)


def _date(node: Mapping[str, Any], key: str) -> date:
    value = _require(node, key)
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise SeedError(f"invalid date {value!r}") from exc


def _require(node: Mapping[str, Any], key: str) -> Any:
    if key not in node or node[key] in (None, ""):
        raise SeedError(f"event entry missing required field {key!r}")
    return node[key]
