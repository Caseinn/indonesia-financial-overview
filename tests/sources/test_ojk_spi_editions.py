"""Tests for the OJK SPI edition-page backfill, against a trimmed real workbook."""

from __future__ import annotations

import io
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Self

import pytest

from pipeline.config import load_config
from pipeline.models import IngestionEnvelope
from pipeline.parsing import ParseError
from pipeline.sources import ojk_spi_editions
from pipeline.sources.ojk_spi_editions import (
    SOURCE_ID,
    find_artifact_url,
    find_editions,
    list_editions,
    parse_annual_ratios,
    run,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "ojk" / "kinerja_bank_umum.xlsx"
INDEX_URL = ojk_spi_editions.INDEX_URL

EDITION_HREF = (
    "/id/kanal/perbankan/data-dan-statistik/statistik-perbankan-indonesia/Pages/"
    "Statistik-Perbankan-Indonesia---Desember-2024.aspx"
)
ARTIFACT_HREF = (
    "/id/kanal/perbankan/data-dan-statistik/statistik-perbankan-indonesia/Documents/Pages/"
    "Statistik-Perbankan-Indonesia---Desember-2024/STATISTIK%20PERBANKAN%20INDONESIA%20-%20DESEMBER%202024.xlsx"
)
INDEX_HTML = f'<html><body><a href="{EDITION_HREF}">Desember 2024</a></body></html>'
EDITION_HTML = f'<html><body><a href="{ARTIFACT_HREF}">unduh</a></body></html>'


def _envelope() -> IngestionEnvelope:
    return IngestionEnvelope(
        source_id=SOURCE_ID,
        source_url="https://www.ojk.go.id/edition",
        retrieved_at=datetime(2026, 10, 16, tzinfo=UTC),
        period_start=date(2021, 1, 1),
        period_end=date(2021, 12, 31),
        source_file_sha256="a" * 64,
        ingestion_run_id="run-1",
        source_version=1,
    )


def _indicators():
    config = load_config()
    return [
        indicator
        for indicator in config.indicators.values()
        if indicator.source == SOURCE_ID and indicator.source_sheet and indicator.source_row
    ]


def _by_code(observations):
    grouped: dict[str, list] = {}
    for observation in observations:
        grouped.setdefault(observation.indicator_code, []).append(observation)
    return grouped


class _Response:
    def __init__(self, *, text: str = "", content: bytes = b"") -> None:
        self.text = text
        self.content = content
        self.status_code = 200

    def raise_for_status(self) -> None:
        return None

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def iter_content(self, chunk_size: int) -> list[bytes]:
        return [self.content]


class _Session:
    """Serves the index, one edition page, and the workbook, off the network."""

    def __init__(self, workbook: bytes) -> None:
        self.headers: dict[str, str] = {}
        self.calls: list[str] = []
        self._workbook = workbook

    def get(self, url: str, **kwargs: object) -> _Response:
        self.calls.append(url)
        if url == INDEX_URL:
            return _Response(text=INDEX_HTML)
        if url.endswith(".aspx"):
            return _Response(text=EDITION_HTML)
        if url.endswith(".xlsx"):
            return _Response(content=self._workbook)
        raise AssertionError(f"unexpected URL: {url}")

    def post(self, url: str, **kwargs: object) -> _Response:
        raise AssertionError("the index has no pager; no POST expected")


def test_parse_annual_ratios_pre_portal() -> None:
    observations = parse_annual_ratios(FIXTURE.read_bytes(), _indicators(), _envelope())
    grouped = _by_code(observations)

    assert set(grouped) == {"CAR_ANNUAL", "ROA_ANNUAL", "LDR_ANNUAL"}
    car = grouped["CAR_ANNUAL"]
    assert [observation.period_start.year for observation in car] == [2021, 2022]
    assert car[0].original_value == pytest.approx(25.66529191921533)
    assert car[0].period_end == date(2021, 12, 31)
    assert car[0].frequency == "annual"
    assert car[0].original_unit == "percent"
    assert car[0].source_raw_label.startswith("Rasio Pemenuhan Kecukupan Modal Minimum (%)")


def test_cutover_includes_2023_when_later() -> None:
    observations = parse_annual_ratios(
        FIXTURE.read_bytes(), _indicators(), _envelope(), cutover=date(2024, 1, 1)
    )
    car_years = [o.period_start.year for o in _by_code(observations)["CAR_ANNUAL"]]

    assert car_years == [2021, 2022, 2023]


def test_zip_wrapped_workbook_is_unwrapped() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("STATISTIK PERBANKAN INDONESIA - DESEMBER 2024.xlsx", FIXTURE.read_bytes())

    observations = parse_annual_ratios(buffer.getvalue(), _indicators(), _envelope())

    assert {o.indicator_code for o in observations} == {"CAR_ANNUAL", "ROA_ANNUAL", "LDR_ANNUAL"}


def test_non_workbook_payload_fails_loudly() -> None:
    with pytest.raises(ParseError, match="expected an .xlsx or .zip"):
        parse_annual_ratios(b"<html></html>", _indicators(), _envelope())


def test_find_editions_parses_period_and_url() -> None:
    editions = find_editions(INDEX_HTML)

    assert editions == [(date(2024, 12, 1), "https://www.ojk.go.id" + EDITION_HREF)]


def test_find_artifact_url() -> None:
    url = find_artifact_url(EDITION_HTML, "https://www.ojk.go.id/edition.aspx")

    assert url.endswith(".xlsx")
    with pytest.raises(ParseError, match="no Workbook link"):
        find_artifact_url("<html></html>", "https://www.ojk.go.id/x.aspx")


def test_list_editions_walks_without_pager() -> None:
    editions = list_editions(_Session(FIXTURE.read_bytes()), sleep=lambda _seconds: None)

    assert editions == [(date(2024, 12, 1), "https://www.ojk.go.id" + EDITION_HREF)]


def test_run_emits_pre_portal_annual_ratios() -> None:
    result = run(
        ingestion_run_id="run-1",
        edition_years=(2024,),
        session=_Session(FIXTURE.read_bytes()),
        sleep=lambda _seconds: None,
    )

    assert result.envelope.source_id == SOURCE_ID
    assert result.envelope.period_start == date(2021, 1, 1)
    assert result.envelope.period_end == date(2022, 12, 31)
    assert {o.indicator_code for o in result.observations} == {
        "CAR_ANNUAL",
        "ROA_ANNUAL",
        "LDR_ANNUAL",
    }
    assert all(o.frequency == "annual" for o in result.observations)
    assert len(result.artifacts) == 1
    assert result.artifacts[0].content == FIXTURE.read_bytes()
