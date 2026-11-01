"""BI SEKI adapter: policy rate and the interest-rate corridor.

One Edition is a ZIP reached from the edition page, which is reached from the
landing page; artifact links are resolved from the pages, never guessed. Each
ZIP member is a per-table legacy ``.xls`` workbook whose rate tables present a
month grid: an instrument-label column, a year row, a month row, then one row
per instrument with months advancing left to right. Section IV fiscal tables
instead present an annual grid (one column per year, no month row); the same
table reader resolves both layouts. This module resolves the Edition, extracts a
table, and reads that grid for every Indicator bound to it in ``indicators.yml``,
failing loudly when a page, sheet, row, or header drifts. Only the current-era
sheets are parsed here; the pre-2017 era sheets, which use older layouts, are
handled separately.
"""

from __future__ import annotations

import re
import time
import zipfile
from dataclasses import dataclass
from datetime import UTC, date, datetime
from io import BytesIO
from urllib.parse import urljoin

import requests
import xlrd

from pipeline.config import IndicatorConfig, IndicatorsConfig, load_config
from pipeline.http import browser_headers, new_session, request_with_retry
from pipeline.models import Artifact, IngestionEnvelope, Observation, SourceRunResult
from pipeline.parsing import (
    ParseError,
    WorkbookFormat,
    clean_number,
    detect_workbook_format,
    month_end,
    month_number,
    sha256_hex,
)

SOURCE_ID = "BI_SEKI"
DEFAULT_TABLE = "TABEL1_25_1"
CONTENT_TYPE = "application/zip"
INDEX_URL = "https://www.bi.go.id/id/statistik/ekonomi-keuangan/seki/"
_SITE_ROOT = "https://www.bi.go.id"
_EDITION_HREF = re.compile(r'href="([^"]*/seki/Pages/SEKI-([A-Z]+)-(\d{4})\.aspx)"', re.IGNORECASE)
_ZIP_HREF = re.compile(r'href="([^"]+\.zip)"', re.IGNORECASE)
_BROWSER_HEADERS = browser_headers(
    accept="text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    referer=INDEX_URL,
)
_REQUEST_TIMEOUT = 120.0
_PACE_SECONDS = 20.0
_ATTEMPTS = 3
_BACKOFF_SECONDS = 20.0
_ZIP_MAGIC = b"PK\x03\x04"
_MEMBER_SUFFIX = ".xls"
_HEADER_SEARCH_ROWS = 12
_LABEL_HEADERS = ("JENIS", "GOLONGAN", "KETERANGAN", "KELOMPOK", "PENGELUARAN")
_HEADER_LABELS = frozenset(_LABEL_HEADERS)
_MISSING_MARKERS = frozenset({"", "-", "--", "\u2013", "\u2014"})
_QUARTER = re.compile(r"^Q([1-4])$", re.IGNORECASE)

Grid = tuple[tuple[object, ...], ...]


def extract_member(zip_bytes: bytes, table_code: str) -> bytes:
    """Return one table's workbook bytes out of an Edition ZIP, or fail loudly."""
    wanted = f"{table_code}{_MEMBER_SUFFIX}".lower()
    with zipfile.ZipFile(BytesIO(zip_bytes)) as archive:
        for name in archive.namelist():
            if name.lower() == wanted:
                return archive.read(name)
    raise ParseError(f"{SOURCE_ID}: {table_code}{_MEMBER_SUFFIX} not found in the Edition ZIP")


def parse_edition(
    zip_bytes: bytes,
    config: IndicatorsConfig,
    envelope: IngestionEnvelope,
    table_code: str = DEFAULT_TABLE,
) -> tuple[Observation, ...]:
    """Extract and parse one table from an Edition ZIP into Observations."""
    return parse_table(extract_member(zip_bytes, table_code), table_code, config, envelope)


@dataclass(frozen=True, slots=True)
class EditionArtifact:
    """A downloaded Edition ZIP plus the pages it was resolved from."""

    content: bytes
    edition_url: str
    zip_url: str
    period: date


def find_latest_edition(html: str) -> tuple[date, str]:
    """Return the newest Edition's reporting period and page URL from the index.

    The landing page lists editions newest first, but the period is parsed from
    each link (never assumed from order) so a re-ordering cannot silently pick a
    stale Edition.
    """
    editions: list[tuple[date, str]] = []
    for href, month_name, year in _EDITION_HREF.findall(html):
        month = month_number(month_name)
        if month is not None:
            editions.append((date(int(year), month, 1), urljoin(_SITE_ROOT, href)))
    if not editions:
        raise ParseError(f"{SOURCE_ID}: no Edition links found on the landing page")
    return max(editions, key=lambda entry: entry[0])


def find_zip_url(html: str, page_url: str) -> str:
    """Return the Edition ZIP link from an edition page, or fail loudly."""
    match = _ZIP_HREF.search(html)
    if match is None:
        raise ParseError(f"{SOURCE_ID}: no ZIP link found on {page_url}")
    return urljoin(page_url, match.group(1))


def fetch_edition(
    *,
    session: requests.Session | None = None,
    sleep=time.sleep,
) -> EditionArtifact:
    """Resolve and download the newest Edition, with pacing and backoff.

    BI's WAF drops request bursts, so a failed attempt backs off before retrying
    the whole landing -> edition -> ZIP walk.
    """
    http = new_session(_BROWSER_HEADERS, session)
    return request_with_retry(
        lambda: _fetch_edition_once(http, sleep),
        source_id=SOURCE_ID,
        label="edition fetch",
        attempts=_ATTEMPTS,
        backoff=_BACKOFF_SECONDS,
        sleep=sleep,
    )


def build_envelope(
    artifact: EditionArtifact,
    *,
    ingestion_run_id: str,
    retrieved_at: datetime | None = None,
) -> IngestionEnvelope:
    """Wrap a downloaded Edition ZIP in provenance, keyed by its checksum.

    The Edition's reporting period is the month it is named for; the ZIP is the
    canonical Publication, so its checksum identifies every table inside it.
    """
    return IngestionEnvelope(
        source_id=SOURCE_ID,
        source_url=artifact.edition_url,
        retrieved_at=retrieved_at or datetime.now(UTC),
        period_start=artifact.period,
        period_end=month_end(artifact.period.year, artifact.period.month),
        source_file_sha256=sha256_hex(artifact.content),
        ingestion_run_id=ingestion_run_id,
        source_version=1,
    )


def run(
    *,
    ingestion_run_id: str,
    config: IndicatorsConfig | None = None,
    session: requests.Session | None = None,
) -> SourceRunResult:
    """Fetch the newest Edition and parse every table bound in the config."""
    config = config or load_config()
    tables = _bound_tables(config)
    if not tables:
        raise ParseError(f"{SOURCE_ID}: no tables are bound in the config")
    artifact = fetch_edition(session=session)
    envelope = build_envelope(artifact, ingestion_run_id=ingestion_run_id)
    observations: list[Observation] = []
    for table in tables:
        observations.extend(parse_edition(artifact.content, config, envelope, table))
    raw = Artifact(
        name=artifact.zip_url.rsplit("/", 1)[-1],
        content_type=CONTENT_TYPE,
        content=artifact.content,
    )
    return SourceRunResult(envelope=envelope, observations=tuple(observations), artifacts=(raw,))


def _bound_tables(config: IndicatorsConfig) -> list[str]:
    return sorted(
        {
            indicator.source_table
            for indicator in config.indicators.values()
            if indicator.source == SOURCE_ID
            and indicator.source_table
            and indicator.source_sheets
            and indicator.source_row
        }
    )


def _fetch_edition_once(http: requests.Session, sleep) -> EditionArtifact:
    index = http.get(INDEX_URL, timeout=_REQUEST_TIMEOUT)
    index.raise_for_status()
    period, edition_url = find_latest_edition(index.text)

    sleep(_PACE_SECONDS)
    page = http.get(edition_url, timeout=_REQUEST_TIMEOUT)
    page.raise_for_status()
    zip_url = find_zip_url(page.text, edition_url)

    sleep(_PACE_SECONDS)
    download = http.get(zip_url, headers={"Referer": edition_url}, timeout=_REQUEST_TIMEOUT)
    download.raise_for_status()
    if not download.content.startswith(_ZIP_MAGIC):
        raise ParseError(f"{SOURCE_ID}: expected a ZIP archive from {zip_url}")
    return EditionArtifact(
        content=download.content,
        edition_url=edition_url,
        zip_url=zip_url,
        period=period,
    )


def parse_table(
    blob: bytes,
    table_code: str,
    config: IndicatorsConfig,
    envelope: IngestionEnvelope,
) -> tuple[Observation, ...]:
    """Parse one SEKI table workbook for every bound Indicator, or fail loudly."""
    grids = _read_grids(blob)
    bound = [
        indicator
        for indicator in config.indicators.values()
        if indicator.source == SOURCE_ID and indicator.source_table == table_code
    ]
    if not bound:
        raise ParseError(f"{SOURCE_ID}: no Indicators are bound to table {table_code}")

    observations: list[Observation] = []
    for indicator in bound:
        if not indicator.source_sheets or not indicator.source_row:
            raise ParseError(
                f"{SOURCE_ID}: Indicator {indicator.code} is bound to {table_code} "
                "without source_sheets and source_row"
            )
        for sheet in indicator.source_sheets:
            if sheet not in grids:
                raise ParseError(
                    f"{SOURCE_ID}: sheet {sheet!r} for {indicator.code} "
                    f"not in workbook (have {sorted(grids)})"
                )
            observations.extend(_parse_indicator(grids[sheet], sheet, indicator, envelope))
    return tuple(observations)


def _read_grids(blob: bytes) -> dict[str, Grid]:
    sniffed = detect_workbook_format(blob)
    if sniffed is not WorkbookFormat.XLS:
        raise ParseError(f"{SOURCE_ID}: expected legacy .xls, sniffed {sniffed}")
    book = xlrd.open_workbook(file_contents=blob)
    grids: dict[str, Grid] = {}
    for name in book.sheet_names():
        sheet = book.sheet_by_name(name)
        grids[name] = tuple(tuple(sheet.row_values(row)) for row in range(sheet.nrows))
    return grids


def _parse_indicator(
    grid: Grid, sheet: str, indicator: IndicatorConfig, envelope: IngestionEnvelope
) -> list[Observation]:
    label_column = _label_column(grid, indicator)
    periods = _column_periods(grid, indicator, sheet, label_column)
    row_index = _find_row(grid, label_column, indicator, sheet)
    raw_label = str(grid[row_index][label_column]).strip()

    observations: list[Observation] = []
    for column, (period_start, period_end) in periods.items():
        if column >= len(grid[row_index]):
            continue
        value = _cell_number(grid[row_index][column])
        if value is None:
            continue
        if not _in_validity(period_start, indicator):
            continue
        observations.append(
            _observation(value, period_start, period_end, raw_label, indicator, envelope)
        )
    if not observations:
        raise ParseError(f"{SOURCE_ID}: no values for {indicator.code} in sheet {sheet!r}")
    return observations


def _observation(
    value: float,
    period_start: date,
    period_end: date,
    raw_label: str,
    indicator: IndicatorConfig,
    envelope: IngestionEnvelope,
) -> Observation:
    return Observation.from_source(
        envelope,
        source_table=indicator.source_table or DEFAULT_TABLE,
        indicator_code=indicator.code,
        period_start=period_start,
        period_end=period_end,
        frequency=indicator.frequency,
        value=value,
        unit=indicator.unit,
        source_raw_label=raw_label,
        geography_code=indicator.geography,
    )


def _label_column(grid: Grid, indicator: IndicatorConfig) -> int:
    for row in grid[:_HEADER_SEARCH_ROWS]:
        for column, cell in enumerate(row):
            if isinstance(cell, str) and any(keyword in cell.upper() for keyword in _LABEL_HEADERS):
                return column
    raise ParseError(f"{SOURCE_ID}: label column not found for {indicator.code}")


def _column_periods(
    grid: Grid, indicator: IndicatorConfig, sheet: str, label_column: int
) -> dict[int, tuple[date, date]]:
    month_row = _find_period_row(grid, _is_month_name, label_column)
    if month_row is not None:
        return {
            column: _month_bounds(year, month)
            for column, (year, month) in _grid_periods(grid, month_row).items()
        }
    quarter_row = _find_period_row(grid, _is_quarter, label_column)
    if quarter_row is not None:
        return _quarter_bounds(grid, quarter_row)
    serial_row = _find_period_row(grid, _is_serial, label_column)
    if serial_row is not None:
        return {
            column: _month_bounds(year, month)
            for column, (year, month) in _serial_periods(grid[serial_row]).items()
        }
    year_row = _find_period_row(grid, _is_year, label_column)
    if year_row is not None:
        return _year_periods(grid[year_row])
    raise ParseError(f"{SOURCE_ID}: no period header in sheet {sheet!r} for {indicator.code}")


def _month_bounds(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), month_end(year, month)


def _quarter_bounds(grid: Grid, quarter_row: int) -> dict[int, tuple[date, date]]:
    year_row = grid[quarter_row - 1] if quarter_row > 0 else ()
    start_year = next(
        (int(cell) for cell in year_row if isinstance(cell, float) and 1900 <= cell <= 2100),
        None,
    )
    if start_year is None:
        raise ParseError(f"{SOURCE_ID}: no year found above the quarter header")

    periods: dict[int, tuple[date, date]] = {}
    year = start_year
    seen_quarter = False
    for column, cell in enumerate(grid[quarter_row]):
        match = _QUARTER.match(str(cell).strip())
        if match is None:
            continue
        quarter = int(match.group(1))
        if quarter == 1 and seen_quarter:
            year += 1
        seen_quarter = True
        start_month = (quarter - 1) * 3 + 1
        periods[column] = (date(year, start_month, 1), month_end(year, start_month + 2))
    return periods


def _find_period_row(grid: Grid, predicate, label_column: int) -> int | None:
    for index, row in enumerate(grid[:_HEADER_SEARCH_ROWS]):
        cell = row[label_column] if label_column < len(row) else None
        if not _is_header_label(cell):
            continue
        if sum(1 for cell in row if predicate(cell)) >= 3:
            return index
    return None


def _is_header_label(value: object) -> bool:
    """A period-header row has a blank label cell or an exact label-header token.

    Distinguishes the true period row from data rows whose label or values merely
    resemble one (a data label like "Pengeluaran Rutin" contains a header
    keyword, and annual IDR totals fall inside the Excel-serial range).
    """
    text = _normalize(value).upper()
    return text == "" or text in _HEADER_LABELS


def _is_month_name(value: object) -> bool:
    return _month(value) is not None


def _is_serial(value: object) -> bool:
    return isinstance(value, float) and 20000.0 <= value <= 60000.0


def _is_year(value: object) -> bool:
    return isinstance(value, float) and 1900.0 <= value <= 2100.0


def _is_quarter(value: object) -> bool:
    return _QUARTER.match(str(value).strip()) is not None


def _grid_periods(grid: Grid, month_row: int) -> dict[int, tuple[int, int]]:
    year_row = grid[month_row - 1] if month_row > 0 else ()
    labeled = [(column, int(cell)) for column, cell in enumerate(year_row) if _is_year(cell)]
    if len({year for _, year in labeled}) >= 2:
        return _labeled_grid_periods(grid, month_row, year_row)
    start_year = next((year for _, year in labeled), None)
    if start_year is None:
        raise ParseError(f"{SOURCE_ID}: no year found above the month header")

    periods: dict[int, tuple[int, int]] = {}
    year = start_year
    seen_month = False
    for column, cell in enumerate(grid[month_row]):
        month = _month(cell)
        if month is None:
            continue
        if month == 1 and seen_month:
            year += 1
        seen_month = True
        periods[column] = (year, month)
    return periods


def _labeled_grid_periods(
    grid: Grid, month_row: int, year_row: tuple[object, ...]
) -> dict[int, tuple[int, int]]:
    """Map month columns to periods using year labels and Dec-to-Jan rollover.

    An explicit year label wins where present; otherwise the year rolls over on a
    December-to-January step. Modern tables label every year, but section IV.4
    shifts its late-year labels, so the rollover keeps the series continuous and
    free of duplicate (year, month) pairs.
    """
    periods: dict[int, tuple[int, int]] = {}
    year: int | None = None
    previous: int | None = None
    for column, cell in enumerate(grid[month_row]):
        month = _month(cell)
        if month is None:
            continue
        label = year_row[column] if column < len(year_row) else None
        if _is_year(label):
            year = int(label)
        elif previous == 12 and month == 1 and year is not None:
            year += 1
        if year is None:
            previous = month
            continue
        periods[column] = (year, month)
        previous = month
    return periods


def _serial_periods(serial_row: tuple[object, ...]) -> dict[int, tuple[int, int]]:
    periods: dict[int, tuple[int, int]] = {}
    for column, cell in enumerate(serial_row):
        if not _is_serial(cell):
            continue
        moment = xlrd.xldate_as_datetime(float(cell), 0)
        periods[column] = (moment.year, moment.month)
    return periods


def _year_periods(year_row: tuple[object, ...]) -> dict[int, tuple[date, date]]:
    """Map each year column to its full-year Reporting Period, first column wins.

    Section IV fiscal tables label columns with a calendar year and carry a
    trailing duplicate-year block for later line items; a repeated year is bound
    to its first (canonical) column so the business key stays unique.
    """
    periods: dict[int, tuple[date, date]] = {}
    seen: set[int] = set()
    for column, cell in enumerate(year_row):
        if not _is_year(cell):
            continue
        year = int(cell)
        if year in seen:
            continue
        seen.add(year)
        periods[column] = (date(year, 1, 1), date(year, 12, 31))
    return periods


def _find_row(grid: Grid, label_column: int, indicator: IndicatorConfig, sheet: str) -> int:
    target = _normalize(indicator.source_row)
    parent = _normalize(indicator.source_parent) if indicator.source_parent else None
    start = 0
    if parent is not None:
        parent_row = _scan_label(grid, label_column, parent, start, exact=False)
        if parent_row is None:
            raise ParseError(
                f"{SOURCE_ID}: parent row {indicator.source_parent!r} for {indicator.code} not found"
            )
        start = parent_row + 1

    row = _scan_label(grid, label_column, target, start, exact=parent is not None)
    if row is None:
        raise ParseError(
            f"{SOURCE_ID}: row {indicator.source_row!r} for {indicator.code} not found "
            f"in sheet {sheet!r}"
        )
    return row


def _scan_label(
    grid: Grid, label_column: int, target: str, start: int, *, exact: bool
) -> int | None:
    for index in range(start, len(grid)):
        if label_column >= len(grid[index]):
            continue
        label = _normalize(grid[index][label_column])
        if exact:
            if label == target:
                return index
        elif label == target or label.startswith((target + " ", target + "(")):
            return index
    return None


def _in_validity(period_start: date, indicator: IndicatorConfig) -> bool:
    return not (
        (indicator.valid_from is not None and period_start < indicator.valid_from)
        or (indicator.valid_to is not None and period_start > indicator.valid_to)
    )


def _month(value: object) -> int | None:
    if not isinstance(value, str):
        return None
    return month_number(value)


def _normalize(value: object) -> str:
    return " ".join(str(value).split())


def _cell_number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if text.lower() in _MISSING_MARKERS:
        return None
    return clean_number(text)
