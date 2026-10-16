"""Curated events Seed loading and its idempotency checksum."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from pipeline.seeds import SeedError, load_events, seed_checksum


def test_loads_committed_seed() -> None:
    events = load_events()
    codes = {event.code for event in events}

    assert "COVID_FIRST_CASES" in codes
    covid = next(event for event in events if event.code == "COVID_FIRST_CASES")
    assert covid.event_date == date(2020, 3, 2)
    assert covid.category == "pandemic"


def test_checksum_reflects_content(tmp_path: Path) -> None:
    first = tmp_path / "a.yml"
    second = tmp_path / "b.yml"
    first.write_text("events: []\n", encoding="utf-8")
    second.write_text("events:\n  - date: 2020-01-01\n    code: X\n    title: X\n")

    assert seed_checksum(first) == seed_checksum(first)
    assert seed_checksum(first) != seed_checksum(second)


def test_missing_field_raises(tmp_path: Path) -> None:
    bad = tmp_path / "events.yml"
    bad.write_text("events:\n  - date: 2020-01-01\n    code: X\n", encoding="utf-8")

    with pytest.raises(SeedError, match="title"):
        load_events(bad)


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(SeedError, match="not found"):
        load_events(tmp_path / "absent.yml")
