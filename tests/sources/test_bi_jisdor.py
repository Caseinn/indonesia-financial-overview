"""Tests for the BI JISDOR adapter, against a real trimmed export fixture."""

from __future__ import annotations

import hashlib
from datetime import date, datetime
from io import BytesIO
from pathlib import Path

import openpyxl
import pytest

from pipeline.models import IngestionEnvelope
from pipeline.parsing import ParseError
from pipeline.sources.bi_jisdor import (
    EXPECTED_SHEET,
    INDICATOR_CODE,
    SOURCE_ID,
    FormState,
    build_envelope,
    build_export_body,
    extract_form_state,
    fetch_export,
    parse_export,
    run,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "bi_jisdor"
FIXTURE = FIXTURES / "jisdor_export_2026-10-15.xlsx"
PAGE = FIXTURES / "jisdor_page_2026-10-15.html"
PREFIX = "ctl00$ctl54$g_f51e6b6d_47c5_4ff4_8105_27cbd1a2f52d$ctl00"
POSTBACK_HTML = """
<html><body><form>
<input type="hidden" name="__VIEWSTATE" value="VS" />
<input type="hidden" name="__EVENTTARGET" value="" />
<input type="hidden" name="__EVENTARGUMENT" value="" />
<input name="ctl00$ctl51$g_abc$ctl00$TextBoxFrom" type="text" />
<input name="ctl00$ctl51$g_abc$ctl00$TextBoxDateTo" type="text" />
<input type="hidden" name="ctl00$ctl51$g_abc$ctl00$HiddenFieldDateFrom" />
<input type="hidden" name="ctl00$ctl51$g_abc$ctl00$HiddenFieldDateTo" />
<a id="ctl00_ctl51_g_abc_ctl00_ButtonExport"
 href="javascript:__doPostBack(&#39;ctl00$ctl51$g_abc$ctl00$ButtonExport&#39;,&#39;&#39;)">Unduh</a>
</form></body></html>
"""
POSTBACK_PREFIX = "ctl00$ctl51$g_abc$ctl00"


class _Response:
    def __init__(self, *, text: str = "", content: bytes = b"") -> None:
        self.text = text
        self.content = content

    def raise_for_status(self) -> None:
        return None


class _Session:
    """Stands in for requests.Session so fetch tests stay off the network."""

    def __init__(self, page_html: str, export: bytes) -> None:
        self.headers: dict[str, str] = {}
        self.posted: list[dict[str, str]] = []
        self._page = _Response(text=page_html)
        self._export = _Response(content=export)

    def get(self, *args: object, **kwargs: object) -> _Response:
        return self._page

    def post(self, url: str, data: dict[str, str], **kwargs: object) -> _Response:
        self.posted.append(data)
        return self._export


def _slept() -> tuple[list[float], object]:
    calls: list[float] = []

    def sleep(seconds: float) -> None:
        calls.append(seconds)

    return calls, sleep


def _envelope() -> IngestionEnvelope:
    return IngestionEnvelope(
        source_id=SOURCE_ID,
        source_url="https://www.bi.go.id/id/statistik/informasi-kurs/jisdor/Default.aspx",
        retrieved_at=datetime(2026, 10, 15, 12, 0, 0),
        period_start=date(2026, 9, 28),
        period_end=date(2026, 10, 15),
        source_file_sha256="0" * 64,
        ingestion_run_id="run-1",
        source_version=1,
    )


def _build_xlsx(rows: list[list[object]], sheet_name: str = EXPECTED_SHEET) -> bytes:
    workbook = openpyxl.Workbook()
    workbook.active.title = sheet_name
    for row in rows:
        workbook.active.append(row)
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_parses_real_fixture() -> None:
    observations = parse_export(FIXTURE.read_bytes(), _envelope())

    assert len(observations) == 14
    assert observations[0].period_start == date(2026, 10, 15)
    assert observations[0].original_value == 17948
    assert observations[-1].period_start == date(2026, 9, 28)
    assert observations[-1].original_value == 17965

    first = observations[0]
    assert first.indicator_code == INDICATOR_CODE
    assert first.frequency == "daily"
    assert first.geography_code == "IDN"
    assert first.normalized_unit == "idr_per_usd"
    assert first.original_value == first.normalized_value
    assert first.source_file_sha256 == "0" * 64

    keys = {obs.business_key for obs in observations}
    assert len(keys) == len(observations)


def test_wrong_header_fails_loudly() -> None:
    blob = _build_xlsx(
        [
            [None, None, None],
            ["Informasi Kurs Jisdor", None, None],
            ["NO", "Date", "Rate"],
            [1, "10/15/2026 12:00:00 AM", 17948],
        ]
    )
    with pytest.raises(ParseError, match="header"):
        parse_export(blob, _envelope())


def test_wrong_sheet_fails_loudly() -> None:
    blob = _build_xlsx([["NO", "Tanggal", "Kurs"]], sheet_name="Sheet1")
    with pytest.raises(ParseError, match="expected sheet"):
        parse_export(blob, _envelope())


def test_non_xlsx_payload_fails_loudly() -> None:
    with pytest.raises(ParseError, match="expected an .xlsx"):
        parse_export(b"<html><table><tr></tr></table></html>", _envelope())


def test_header_only_sheet_fails_loudly() -> None:
    blob = _build_xlsx([["Informasi Kurs Jisdor", None, None], ["NO", "Tanggal", "Kurs"]])
    with pytest.raises(ParseError, match="no data rows"):
        parse_export(blob, _envelope())


def _state() -> FormState:
    return extract_form_state(PAGE.read_text(encoding="utf-8"))


def test_extract_form_state_reads_real_page() -> None:
    state = _state()

    assert state.prefix == PREFIX
    assert state.uses_postback is False
    assert state.fields["__VIEWSTATEGENERATOR"] == "D5F26F22"
    assert state.fields["__VIEWSTATE"]
    assert state.fields["__REQUESTDIGEST"]
    assert state.fields[f"{PREFIX}$TextBoxFrom"] == ""
    assert state.fields[f"{PREFIX}$HiddenFieldDateTo"] == ""
    assert f"{PREFIX}$ButtonExport" not in state.fields
    assert f"{PREFIX}$ButtonCari" not in state.fields
    assert f"{PREFIX}$DataPagerData$ctl00$ctl00" not in state.fields


def test_extract_form_state_reads_postback_link() -> None:
    state = extract_form_state(POSTBACK_HTML)

    assert state.prefix == POSTBACK_PREFIX
    assert state.uses_postback is True
    assert state.fields[f"{POSTBACK_PREFIX}$TextBoxFrom"] == ""
    assert state.fields["__VIEWSTATE"] == "VS"


def test_extract_form_state_fails_without_export_button() -> None:
    with pytest.raises(ParseError, match="export button"):
        extract_form_state("<html><body><form></form></body></html>")


def test_build_export_body_sets_range_and_buttons() -> None:
    state = _state()
    body = build_export_body(state, date(2020, 1, 1), date(2020, 3, 31))

    assert body[f"{PREFIX}$TextBoxFrom"] == "01/01/2020"
    assert body[f"{PREFIX}$TextBoxDateTo"] == "31/03/2020"
    assert body[f"{PREFIX}$HiddenFieldDateFrom"] == ""
    assert body[f"{PREFIX}$ButtonExport"] == "Unduh"
    assert f"{PREFIX}$ButtonCari" not in body
    assert body["__VIEWSTATE"] == state.fields["__VIEWSTATE"]


def test_build_export_body_posts_event_target_for_link() -> None:
    state = extract_form_state(POSTBACK_HTML)
    body = build_export_body(state, date(2020, 1, 1), date(2020, 3, 31))

    assert body[f"{POSTBACK_PREFIX}$TextBoxFrom"] == "01/01/2020"
    assert body[f"{POSTBACK_PREFIX}$TextBoxDateTo"] == "31/03/2020"
    assert body["__EVENTTARGET"] == f"{POSTBACK_PREFIX}$ButtonExport"
    assert body["__EVENTARGUMENT"] == ""
    assert f"{POSTBACK_PREFIX}$ButtonExport" not in body
    assert body["__VIEWSTATE"] == "VS"


def test_fetch_export_posts_range_and_returns_workbook() -> None:
    sleeps, sleep = _slept()
    session = _Session(PAGE.read_text(encoding="utf-8"), FIXTURE.read_bytes())

    blob = fetch_export(date(2020, 1, 1), date(2020, 1, 31), session=session, sleep=sleep)

    assert blob == FIXTURE.read_bytes()
    assert len(session.posted) == 1
    posted = session.posted[0]
    assert posted[f"{PREFIX}$TextBoxFrom"] == "01/01/2020"
    assert posted[f"{PREFIX}$ButtonExport"] == "Unduh"
    assert sleeps


def test_fetch_export_retries_non_workbook_then_fails() -> None:
    _, sleep = _slept()
    session = _Session(PAGE.read_text(encoding="utf-8"), b"<html>throttled</html>")

    with pytest.raises(ParseError, match="export failed after"):
        fetch_export(date(2020, 1, 1), date(2020, 1, 31), session=session, sleep=sleep)

    assert len(session.posted) == 3


def test_build_envelope_hashes_the_artifact() -> None:
    blob = FIXTURE.read_bytes()
    envelope = build_envelope(
        blob,
        period_start=date(2020, 1, 1),
        period_end=date(2020, 1, 31),
        ingestion_run_id="run-1",
        retrieved_at=datetime(2026, 10, 15, 12, 0, 0),
    )

    assert envelope.source_id == SOURCE_ID
    assert envelope.source_file_sha256 == hashlib.sha256(blob).hexdigest()
    assert envelope.period_start == date(2020, 1, 1)
    assert envelope.period_end == date(2020, 1, 31)


def test_run_composes_fetch_parse_and_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    blob = FIXTURE.read_bytes()
    monkeypatch.setattr(
        "pipeline.sources.bi_jisdor.fetch_export",
        lambda start, end, **kwargs: blob,
    )

    result = run(date(2020, 1, 1), date(2020, 1, 31), ingestion_run_id="run-1")

    assert result.envelope.source_file_sha256 == hashlib.sha256(blob).hexdigest()
    assert len(result.observations) == 14
    assert len(result.artifacts) == 1
    assert result.artifacts[0].content == blob
    assert result.artifacts[0].name == "jisdor_2020-01-01_2020-01-31.xlsx"
