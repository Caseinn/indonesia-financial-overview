"""BI JISDOR adapter: the daily USD/IDR reference rate.

The JISDOR page is an ASP.NET form whose ``Unduh`` button returns an ``.xlsx``
for the whole requested date range (verified: a three-month range yields one
file with every business day, no pagination scraping). Getting there needs the
page's own form state: a GET to harvest the dynamic web-part prefix and hidden
fields, then a POST of ``TextBoxFrom`` / ``TextBoxDateTo`` plus ``ButtonExport``.
The export is month-first and carries three junk title rows, so parsing validates
the sheet and header and fails loudly on drift instead of importing misaligned
columns.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime
from html import unescape
from io import BytesIO

import openpyxl
import requests

from pipeline.http import browser_headers, new_session, request_with_retry
from pipeline.models import (
    Artifact,
    IngestionEnvelope,
    Observation,
    SourceRunResult,
)
from pipeline.parsing import (
    ParseError,
    WorkbookFormat,
    clean_number,
    detect_workbook_format,
    parse_date,
    sha256_hex,
)

SOURCE_ID = "BI_JISDOR"
INDICATOR_CODE = "USDIRR_JISDOR"
SOURCE_TABLE = "JISDOR"
UNIT = "idr_per_usd"
FREQUENCY = "daily"
GEOGRAPHY = "IDN"
PAGE_URL = "https://www.bi.go.id/id/statistik/informasi-kurs/jisdor/Default.aspx"
EXPECTED_SHEET = "Informasi Kurs Jisdor"
EXPECTED_HEADER = ("NO", "Tanggal", "Kurs")
CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_HEADER_SEARCH_ROWS = 10
_DATE_FORMAT = "%d/%m/%Y"
_BROWSER_HEADERS = browser_headers(
    accept="text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    origin="https://www.bi.go.id",
    referer=PAGE_URL,
)
_REQUEST_TIMEOUT = 60.0
_PACE_SECONDS = 20.0
_ATTEMPTS = 3
_BACKOFF_SECONDS = 20.0
_UNPOSTED_TYPES = frozenset({"image", "button", "submit", "reset", "file"})

_INPUT_TAG = re.compile(r"(?is)<input\b[^>]*>")
_ATTR = re.compile(r'(?is)(name|type|value)="([^"]*)"')
_POSTBACK_TARGET = re.compile(r"__doPostBack\(\s*['\"]([^'\"]+)\$ButtonExport['\"]", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class FormState:
    """The page's replayable form: dynamic web-part prefix plus posted fields."""

    prefix: str
    fields: dict[str, str]
    uses_postback: bool = False


def extract_form_state(html: str) -> FormState:
    """Read the web-part prefix and postable fields out of the JISDOR page.

    The ASP.NET control prefix embeds a per-render GUID, so it is discovered
    from the export control rather than hardcoded. The portal has shipped the
    control both as a submit input and as a ``__doPostBack`` link, so the
    replay strategy follows whichever shape the page serves. Non-posted controls
    (image and button inputs) are skipped, matching a real browser postback.
    """
    prefix, uses_postback = _discover_target(html)
    fields: dict[str, str] = {}
    for tag in _INPUT_TAG.findall(html):
        attributes = {name.lower(): value for name, value in _ATTR.findall(tag)}
        name = unescape(attributes.get("name", ""))
        if not name or attributes.get("type", "text").lower() in _UNPOSTED_TYPES:
            continue
        fields[name] = unescape(attributes.get("value", ""))
    if f"{prefix}$TextBoxFrom" not in fields:
        raise ParseError(f"{SOURCE_ID}: date inputs missing from the page")
    return FormState(prefix=prefix, fields=fields, uses_postback=uses_postback)


def build_export_body(state: FormState, period_start: date, period_end: date) -> dict[str, str]:
    """Build the export postback for a date range, as a real browser sends it.

    The visible ``TextBoxFrom`` / ``TextBoxDateTo`` carry the range; the paired
    hidden date fields stay empty. A submit input posts its name and value,
    while a ``__doPostBack`` link posts ``__EVENTTARGET`` instead.
    """
    body = dict(state.fields)
    body[f"{state.prefix}$TextBoxFrom"] = period_start.strftime(_DATE_FORMAT)
    body[f"{state.prefix}$TextBoxDateTo"] = period_end.strftime(_DATE_FORMAT)
    body[f"{state.prefix}$HiddenFieldDateFrom"] = ""
    body[f"{state.prefix}$HiddenFieldDateTo"] = ""
    if state.uses_postback:
        body["__EVENTTARGET"] = f"{state.prefix}$ButtonExport"
        body["__EVENTARGUMENT"] = ""
    else:
        body[f"{state.prefix}$ButtonExport"] = "Unduh"
    return body


def fetch_export(
    period_start: date,
    period_end: date,
    *,
    session: requests.Session | None = None,
    sleep=time.sleep,
) -> bytes:
    """Download the JISDOR export for a date range, with pacing and backoff.

    Each attempt re-reads the page so the postback uses a fresh viewstate; BI's
    WAF drops bursts, so a failed attempt backs off before trying again.
    """
    http = new_session(_BROWSER_HEADERS, session)
    return request_with_retry(
        lambda: _export_once(http, period_start, period_end, sleep),
        source_id=SOURCE_ID,
        label="export",
        attempts=_ATTEMPTS,
        backoff=_BACKOFF_SECONDS,
        sleep=sleep,
    )


def build_envelope(
    artifact: bytes,
    *,
    period_start: date,
    period_end: date,
    ingestion_run_id: str,
    retrieved_at: datetime | None = None,
) -> IngestionEnvelope:
    """Wrap a downloaded export in provenance, keyed by its checksum."""
    return IngestionEnvelope(
        source_id=SOURCE_ID,
        source_url=PAGE_URL,
        retrieved_at=retrieved_at or datetime.now(UTC),
        period_start=period_start,
        period_end=period_end,
        source_file_sha256=sha256_hex(artifact),
        ingestion_run_id=ingestion_run_id,
        source_version=1,
    )


def run(
    period_start: date,
    period_end: date,
    *,
    ingestion_run_id: str,
    session: requests.Session | None = None,
) -> SourceRunResult:
    """Fetch and parse one JISDOR range, the adapter's single entrypoint."""
    artifact = fetch_export(period_start, period_end, session=session)
    envelope = build_envelope(
        artifact,
        period_start=period_start,
        period_end=period_end,
        ingestion_run_id=ingestion_run_id,
    )
    raw = Artifact(
        name=f"jisdor_{period_start.isoformat()}_{period_end.isoformat()}.xlsx",
        content_type=CONTENT_TYPE,
        content=artifact,
    )
    return SourceRunResult(
        envelope=envelope,
        observations=parse_export(artifact, envelope),
        artifacts=(raw,),
    )


def parse_export(blob: bytes, envelope: IngestionEnvelope) -> tuple[Observation, ...]:
    """Turn one JISDOR export into daily Observations, or fail loudly on drift."""
    sniffed = detect_workbook_format(blob)
    if sniffed is not WorkbookFormat.XLSX:
        raise ParseError(f"{SOURCE_ID}: expected an .xlsx export, sniffed {sniffed}")

    workbook = openpyxl.load_workbook(BytesIO(blob), read_only=True, data_only=True)
    if EXPECTED_SHEET not in workbook.sheetnames:
        raise ParseError(
            f"{SOURCE_ID}: expected sheet {EXPECTED_SHEET!r}, got {workbook.sheetnames!r}"
        )
    rows = list(workbook[EXPECTED_SHEET].iter_rows(values_only=True))

    header_index = _find_header(rows)
    observations = tuple(
        _row_to_observation(row, envelope) for row in rows[header_index + 1 :] if _is_data_row(row)
    )
    if not observations:
        raise ParseError(f"{SOURCE_ID}: no data rows found beneath the header")
    return observations


def _discover_target(html: str) -> tuple[str, bool]:
    match = re.search(r'name="([^"]+)\$ButtonExport"', html)
    if match is not None:
        return unescape(match.group(1)), False
    match = _POSTBACK_TARGET.search(unescape(html))
    if match is not None:
        return match.group(1), True
    raise ParseError(f"{SOURCE_ID}: export button not found on the page")


def _export_once(http: requests.Session, period_start: date, period_end: date, sleep) -> bytes:
    page = http.get(PAGE_URL, timeout=_REQUEST_TIMEOUT)
    page.raise_for_status()
    state = extract_form_state(page.text)
    sleep(_PACE_SECONDS)
    response = http.post(
        PAGE_URL,
        data=build_export_body(state, period_start, period_end),
        timeout=_REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    if detect_workbook_format(response.content) is not WorkbookFormat.XLSX:
        raise ParseError(f"{SOURCE_ID}: expected an .xlsx export, got a non-workbook response")
    return response.content


def _find_header(rows: list[tuple[object, ...]]) -> int:
    for index, row in enumerate(rows[:_HEADER_SEARCH_ROWS]):
        if tuple(_clean_cell(cell) for cell in row[: len(EXPECTED_HEADER)]) == EXPECTED_HEADER:
            return index
    raise ParseError(
        f"{SOURCE_ID}: header {EXPECTED_HEADER} not found in first {_HEADER_SEARCH_ROWS} rows"
    )


def _is_data_row(row: tuple[object, ...]) -> bool:
    return len(row) >= 3 and _clean_cell(row[1]) != ""


def _row_to_observation(row: tuple[object, ...], envelope: IngestionEnvelope) -> Observation:
    obs_date = _parse_cell_date(row[1])
    value = _parse_cell_number(row[2])
    return Observation.from_source(
        envelope,
        source_table=SOURCE_TABLE,
        indicator_code=INDICATOR_CODE,
        period_start=obs_date,
        period_end=obs_date,
        frequency=FREQUENCY,
        value=value,
        unit=UNIT,
        source_raw_label="Kurs",
        geography_code=GEOGRAPHY,
    )


def _clean_cell(value: object) -> str:
    return "" if value is None else str(value).strip()


def _parse_cell_date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    parsed = parse_date(str(value), day_first=False)
    if parsed is None:
        raise ParseError(f"{SOURCE_ID}: unparseable date {value!r}")
    return parsed


def _parse_cell_number(value: object) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    number = clean_number(str(value))
    if number is None:
        raise ParseError(f"{SOURCE_ID}: unparseable value {value!r}")
    return number
