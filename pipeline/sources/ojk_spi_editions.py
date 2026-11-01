"""OJK SPI edition-page backfill: annual banking ratios from before the portal.

From the July 2025 period OJK publishes Statistik Perbankan Indonesia only
through the SJKPublic portal (ADR-0007); earlier periods survive as frozen
edition pages, each linking one Workbook (an ``.xlsx``, or a single-member
``.zip`` holding one). This module resolves a bounded set of editions, reads the
aggregate "Kinerja Bank Umum" table, and emits its *annual* columns as
Observations for the pre-portal years only, so its coverage stays disjoint from
the portal adapter's. Only headline ratios bound in ``indicators.yml`` with
``source_sheet`` and ``source_row`` are read; layout drift fails loudly.
"""

from __future__ import annotations

import html as htmlmod
import logging
import re
import time
import zipfile
from datetime import UTC, date, datetime
from io import BytesIO
from urllib.parse import urljoin

import openpyxl
import requests

from pipeline.config import IndicatorConfig, IndicatorsConfig, load_config
from pipeline.http import browser_headers, new_session, request_with_retry
from pipeline.models import Artifact, IngestionEnvelope, Observation, SourceRunResult
from pipeline.parsing import ParseError, month_end, month_number, sha256_hex

SOURCE_ID = "OJK_SPI"
SITE = "https://www.ojk.go.id"
INDEX_URL = (
    f"{SITE}/id/kanal/perbankan/data-dan-statistik/statistik-perbankan-indonesia/Default.aspx"
)
CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PORTAL_START = date(2023, 1, 1)
DEFAULT_EDITION_YEARS = (2021, 2022, 2023, 2024)
DEFAULT_MAX_EDITIONS = 6

_EDITION_HREF = re.compile(
    r'href="(/id/[^"]*Statistik-Perbankan-Indonesia-+([A-Za-z]+)-(\d{4})\.aspx)"',
    re.IGNORECASE,
)
_ARTIFACT_HREF = re.compile(r'href="([^"]+\.(?:xlsx|zip))"', re.IGNORECASE)
_PAGER = re.compile(r"__doPostBack\(&#39;([^&]+)&#39;,&#39;&#39;\)")
_HIDDEN = re.compile(r'name="(__[A-Z]+)"[^>]*value="([^"]*)"')
_HEADER_SEARCH_ROWS = 6
_MAX_TABLE_ROWS = 40
_BROWSER_HEADERS = browser_headers(accept="text/html,application/xhtml+xml,*/*")
_RETRY_HEADERS = browser_headers(accept="*/*")
_REQUEST_TIMEOUT = 180.0
_PACE_SECONDS = 3.0
_ATTEMPTS = 3
_BACKOFF_SECONDS = 20.0

_logger = logging.getLogger(__name__)

Rows = list[tuple[object, ...]]


def find_editions(html: str) -> list[tuple[date, str]]:
    """Return every Edition page on a listing page as (period, url), in page order."""
    editions: list[tuple[date, str]] = []
    for href, month_name, year in _EDITION_HREF.findall(html):
        month = month_number(month_name[:3])
        if month is not None:
            editions.append((date(int(year), month, 1), urljoin(SITE, href)))
    return editions


def list_editions(
    session: requests.Session,
    *,
    max_pages: int = 12,
    sleep=time.sleep,
) -> list[tuple[date, str]]:
    """Walk the ASP.NET pager and return every Edition newest first, deduplicated."""
    page = session.get(INDEX_URL, timeout=_REQUEST_TIMEOUT)
    page.raise_for_status()
    ordered: list[tuple[date, str]] = []
    seen: set[str] = set()
    used_targets: set[str] = set()
    html = page.text
    for _ in range(max_pages):
        for period, url in find_editions(html):
            if url not in seen:
                seen.add(url)
                ordered.append((period, url))
        target = next(
            (
                candidate
                for candidate in _PAGER.findall(html)
                if "DataPagerArticles" in candidate and candidate not in used_targets
            ),
            None,
        )
        if target is None:
            break
        used_targets.add(target)
        data = {name: htmlmod.unescape(value) for name, value in _HIDDEN.findall(html)}
        data["__EVENTTARGET"] = htmlmod.unescape(target)
        data["__EVENTARGUMENT"] = ""
        sleep(_PACE_SECONDS)
        response = session.post(INDEX_URL, data=data, timeout=_REQUEST_TIMEOUT)
        response.raise_for_status()
        html = response.text
    if not ordered:
        raise ParseError(f"{SOURCE_ID}: no Edition links found on {INDEX_URL}")
    return ordered


def find_artifact_url(html: str, page_url: str) -> str:
    """Return the Edition's Workbook link (``.xlsx`` or ``.zip``), or fail loudly."""
    match = _ARTIFACT_HREF.search(html)
    if match is None:
        raise ParseError(f"{SOURCE_ID}: no Workbook link found on {page_url}")
    return urljoin(page_url, match.group(1))


def fetch_artifact(session: requests.Session, url: str, *, referer: str, sleep=time.sleep) -> bytes:
    """Download one Edition Workbook, retrying OJK's flaky streams with backoff."""
    return request_with_retry(
        lambda: _download(session, url, referer),
        source_id=SOURCE_ID,
        label="edition workbook",
        attempts=_ATTEMPTS,
        backoff=_BACKOFF_SECONDS,
        sleep=sleep,
    )


def parse_annual_ratios(
    blob: bytes,
    indicators: list[IndicatorConfig],
    envelope: IngestionEnvelope,
    *,
    cutover: date = PORTAL_START,
) -> tuple[Observation, ...]:
    """Read the annual columns of every bound ratio row, before ``cutover``."""
    by_sheet: dict[str, list[IndicatorConfig]] = {}
    for indicator in indicators:
        if indicator.source_sheet:
            by_sheet.setdefault(indicator.source_sheet, []).append(indicator)

    observations: list[Observation] = []
    for sheet_name, sheet_indicators in by_sheet.items():
        rows = _load_rows(blob, sheet_name)
        year_row, month_row = _header_rows(rows, sheet_name)
        periods = _column_periods(rows[year_row], rows[month_row])
        table_end = _table_end(rows, month_row + 1)
        for indicator in sheet_indicators:
            row_index = _find_label_row(rows, indicator.source_row, month_row + 1, table_end)
            raw_label = _norm(rows[row_index][0])
            for column, (year, month) in periods.items():
                if month is not None or column >= len(rows[row_index]):
                    continue
                if date(year, 1, 1) >= cutover:
                    continue
                value = rows[row_index][column]
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    continue
                observations.append(
                    _observation(float(value), year, raw_label, indicator, envelope)
                )
    return tuple(observations)


def run(
    *,
    ingestion_run_id: str,
    config: IndicatorsConfig | None = None,
    edition_years: tuple[int, ...] | None = None,
    max_editions: int = DEFAULT_MAX_EDITIONS,
    session: requests.Session | None = None,
    retrieved_at: datetime | None = None,
    sleep=time.sleep,
) -> SourceRunResult:
    """Fetch the bound edition years and emit their pre-portal annual ratios."""
    config = config or load_config()
    indicators = [
        indicator
        for indicator in config.indicators.values()
        if indicator.source == SOURCE_ID and indicator.source_sheet and indicator.source_row
    ]
    if not indicators:
        raise ParseError(f"{SOURCE_ID}: no Edition Indicators are bound")

    http = new_session(_BROWSER_HEADERS, session)
    editions = _select_editions(
        list_editions(http, sleep=sleep),
        DEFAULT_EDITION_YEARS if edition_years is None else edition_years,
        max_editions,
    )
    if not editions:
        raise ParseError(f"{SOURCE_ID}: no Edition matched the requested years")

    retrieved = retrieved_at or datetime.now(UTC)
    collected: dict[tuple[str, int], Observation] = {}
    blobs: list[bytes] = []
    artifacts: list[Artifact] = []
    for period, url in editions:
        try:
            page = http.get(url, timeout=_REQUEST_TIMEOUT)
            page.raise_for_status()
            artifact_url = find_artifact_url(page.text, url)
            blob = fetch_artifact(http, artifact_url, referer=url, sleep=sleep)
        except (requests.HTTPError, ParseError) as exc:
            _logger.warning("%s: skipping edition %s: %s", SOURCE_ID, url, exc)
            continue
        envelope = IngestionEnvelope(
            source_id=SOURCE_ID,
            source_url=url,
            retrieved_at=retrieved,
            period_start=period,
            period_end=month_end(period.year, period.month),
            source_file_sha256=sha256_hex(blob),
            ingestion_run_id=ingestion_run_id,
            source_version=1,
        )
        try:
            observations = parse_annual_ratios(blob, indicators, envelope)
        except ParseError as exc:
            _logger.warning("%s: skipping edition %s: %s", SOURCE_ID, url, exc)
            continue
        blobs.append(blob)
        for observation in observations:
            collected.setdefault(
                (observation.indicator_code, observation.period_start.year), observation
            )
        artifacts.append(
            Artifact(
                name=artifact_url.rsplit("/", 1)[-1],
                content_type=CONTENT_TYPE,
                content=blob,
            )
        )
        sleep(_PACE_SECONDS)

    if not collected:
        raise ParseError(f"{SOURCE_ID}: no annual pre-portal values parsed from the editions")
    observations = tuple(
        sorted(collected.values(), key=lambda item: (item.period_start, item.indicator_code))
    )
    envelope = IngestionEnvelope(
        source_id=SOURCE_ID,
        source_url=INDEX_URL,
        retrieved_at=retrieved,
        period_start=min(observation.period_start for observation in observations),
        period_end=max(observation.period_end for observation in observations),
        source_file_sha256=sha256_hex(b"\n".join(blobs)),
        ingestion_run_id=ingestion_run_id,
        source_version=1,
    )
    return SourceRunResult(envelope=envelope, observations=observations, artifacts=tuple(artifacts))


def _select_editions(
    editions: list[tuple[date, str]], years: tuple[int, ...], max_editions: int
) -> list[tuple[date, str]]:
    """Pick the December Edition of each requested year, newest year first."""
    wanted = set(years)
    selected = [
        (period, url) for period, url in editions if period.year in wanted and period.month == 12
    ]
    return selected[:max_editions]


def _download(session: requests.Session, url: str, referer: str) -> bytes:
    with session.get(
        url, headers={"Referer": referer}, timeout=_REQUEST_TIMEOUT, stream=True
    ) as response:
        response.raise_for_status()
        return b"".join(response.iter_content(chunk_size=65536))


def _load_rows(blob: bytes, sheet_name: str) -> Rows:
    workbook = _open_workbook(blob)
    if sheet_name not in workbook.sheetnames:
        raise ParseError(f"{SOURCE_ID}: sheet {sheet_name!r} not in the Edition workbook")
    sheet = workbook[sheet_name]
    rows: Rows = []
    for row in sheet.iter_rows(values_only=True):
        rows.append(row)
        if len(rows) >= _MAX_TABLE_ROWS:
            break
    return rows


def _open_workbook(blob: bytes) -> openpyxl.Workbook:
    """Open an Edition Workbook directly, or unwrap the single ``.xlsx`` in a zip.

    Both an ``.xlsx`` and a ``.zip`` start with the PK signature, so the container
    is told apart by the presence of ``[Content_Types].xml`` at the archive root.
    """
    if not blob.startswith(b"PK"):
        raise ParseError(f"{SOURCE_ID}: expected an .xlsx or .zip Workbook")
    with zipfile.ZipFile(BytesIO(blob)) as archive:
        names = archive.namelist()
        if "[Content_Types].xml" in names:
            return openpyxl.load_workbook(BytesIO(blob), read_only=True, data_only=True)
        workbooks = [name for name in names if name.lower().endswith(".xlsx")]
        if len(workbooks) != 1:
            raise ParseError(
                f"{SOURCE_ID}: expected one .xlsx in the archive, found {len(workbooks)}"
            )
        return openpyxl.load_workbook(
            BytesIO(archive.read(workbooks[0])), read_only=True, data_only=True
        )


def _header_rows(rows: Rows, sheet_name: str) -> tuple[int, int]:
    for index in range(min(_HEADER_SEARCH_ROWS, len(rows))):
        if sum(1 for cell in rows[index] if _is_year(cell)) >= 1:
            if index + 1 >= len(rows):
                break
            return index, index + 1
    raise ParseError(f"{SOURCE_ID}: no year header found in sheet {sheet_name!r}")


def _column_periods(
    year_cells: tuple[object, ...], month_cells: tuple[object, ...]
) -> dict[int, tuple[int, int | None]]:
    periods: dict[int, tuple[int, int | None]] = {}
    year: int | None = None
    for column in range(max(len(year_cells), len(month_cells))):
        cell = year_cells[column] if column < len(year_cells) else None
        if _is_year(cell):
            year = int(cell)  # type: ignore[arg-type]
        caption = _norm(month_cells[column]) if column < len(month_cells) else ""
        if year is None:
            continue
        periods[column] = (year, _month(caption))
    return periods


def _table_end(rows: Rows, start: int) -> int:
    for index in range(start, len(rows)):
        if _norm(rows[index][0] if rows[index] else "").startswith("Tabel"):
            return index
    return len(rows)


def _find_label_row(rows: Rows, label: str, start: int, end: int) -> int:
    for index in range(start, end):
        if rows[index] and _norm(rows[index][0]).startswith(label):
            return index
    raise ParseError(f"{SOURCE_ID}: row {label!r} not found before the next table")


def _observation(
    value: float,
    year: int,
    raw_label: str,
    indicator: IndicatorConfig,
    envelope: IngestionEnvelope,
) -> Observation:
    return Observation.from_source(
        envelope,
        source_table=indicator.source_sheet or "",
        indicator_code=indicator.code,
        period_start=date(year, 1, 1),
        period_end=date(year, 12, 31),
        frequency=indicator.frequency,
        value=value,
        unit=indicator.unit,
        source_raw_label=raw_label,
        geography_code=indicator.geography,
    )


def _is_year(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and 1900 <= value <= 2100


def _month(caption: str) -> int | None:
    return month_number(caption[:3]) if caption else None


def _norm(value: object) -> str:
    return " ".join(str(value).split()) if value is not None else ""
