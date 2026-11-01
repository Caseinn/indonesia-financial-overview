"""Tests for the BI SEKI adapter, against a real trimmed table fixture."""

from __future__ import annotations

import io
import zipfile
from datetime import date, datetime
from pathlib import Path

import pytest

from pipeline.config import load_config
from pipeline.models import IngestionEnvelope
from pipeline.parsing import ParseError
from pipeline.sources.bi_seki import (
    DEFAULT_TABLE,
    INDEX_URL,
    SOURCE_ID,
    EditionArtifact,
    build_envelope,
    extract_member,
    fetch_edition,
    find_latest_edition,
    find_zip_url,
    parse_edition,
    parse_table,
    run,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "bi_seki" / "TABEL1_25_1.xls"
MONEY = FIXTURE.parent / "TABEL1_1.xls"
MID_RATE = FIXTURE.parent / "TABEL5_40.xls"
REGIONAL_GDP = FIXTURE.parent / "TABEL9_1.xls"
REGIONAL_INFLATION = FIXTURE.parent / "TABEL9_2.xls"
FISCAL_REVENUE = FIXTURE.parent / "TABEL4_1.xls"
FISCAL_EXPENDITURE = FIXTURE.parent / "TABEL4_2.xls"
FISCAL_FINANCING = FIXTURE.parent / "TABEL4_3.xls"
FISCAL_SBN = FIXTURE.parent / "TABEL4_4.xls"
INDEX_PAGE = FIXTURE.parent / "edition_index_2026-10-15.html"
EDITION_PAGE = FIXTURE.parent / "edition_2026-09.html"


class _Response:
    def __init__(self, *, text: str = "", content: bytes = b"") -> None:
        self.text = text
        self.content = content

    def raise_for_status(self) -> None:
        return None


class _Session:
    """Stands in for requests.Session so fetch tests stay off the network."""

    def __init__(self, index_html: str, edition_html: str, zip_bytes: bytes) -> None:
        self.headers: dict[str, str] = {}
        self.calls: list[str] = []
        self._index = index_html
        self._edition = edition_html
        self._zip = zip_bytes

    def get(self, url: str, **kwargs: object) -> _Response:
        self.calls.append(url)
        if url == INDEX_URL:
            return _Response(text=self._index)
        if url.endswith(".aspx"):
            return _Response(text=self._edition)
        if url.endswith(".zip"):
            return _Response(content=self._zip)
        raise AssertionError(f"unexpected URL: {url}")


def _zip_bytes() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(f"{DEFAULT_TABLE}.xls", FIXTURE.read_bytes())
        archive.writestr("TABEL1_1.xls", MONEY.read_bytes())
        archive.writestr("TABEL5_40.xls", MID_RATE.read_bytes())
        archive.writestr("TABEL9_1.xls", REGIONAL_GDP.read_bytes())
        archive.writestr("TABEL9_2.xls", REGIONAL_INFLATION.read_bytes())
        archive.writestr("TABEL4_1.xls", FISCAL_REVENUE.read_bytes())
        archive.writestr("TABEL4_2.xls", FISCAL_EXPENDITURE.read_bytes())
        archive.writestr("TABEL4_3.xls", FISCAL_FINANCING.read_bytes())
        archive.writestr("TABEL4_4.xls", FISCAL_SBN.read_bytes())
    return buffer.getvalue()


def _slept() -> tuple[list[float], object]:
    calls: list[float] = []

    def sleep(seconds: float) -> None:
        calls.append(seconds)

    return calls, sleep


def _envelope() -> IngestionEnvelope:
    return IngestionEnvelope(
        source_id=SOURCE_ID,
        source_url="https://www.bi.go.id/id/statistik/ekonomi-keuangan/seki/",
        retrieved_at=datetime(2026, 10, 15, 12, 0, 0),
        period_start=date(2017, 1, 1),
        period_end=date(2026, 9, 30),
        source_file_sha256="a" * 64,
        ingestion_run_id="run-1",
        source_version=1,
    )


def _by_code(observations):
    grouped: dict[str, list] = {}
    for observation in observations:
        grouped.setdefault(observation.indicator_code, []).append(observation)
    return grouped


def _value_at(observations, period: date) -> float:
    for observation in observations:
        if observation.period_start == period:
            return observation.original_value
    raise AssertionError(f"no observation at {period}")


@pytest.fixture(scope="module")
def observations():
    return parse_table(FIXTURE.read_bytes(), DEFAULT_TABLE, load_config(), _envelope())


def test_policy_rate_series(observations) -> None:
    policy = _by_code(observations)["POLICY_RATE"]

    assert len(policy) == 201
    assert policy[0].period_start == date(2010, 1, 1)
    assert policy[-1].period_start == date(2026, 9, 1)
    assert _value_at(policy, date(2010, 1, 1)) == 6.5
    assert _value_at(policy, date(2017, 1, 1)) == 4.75
    assert _value_at(policy, date(2024, 4, 1)) == 6.25
    assert _value_at(policy, date(2026, 9, 1)) == 5.75

    assert policy[0].frequency == "monthly"
    assert policy[0].original_unit == "percent_per_annum"
    assert policy[0].source_raw_label == "Policy Rate"
    assert policy[0].period_end == date(2010, 1, 31)
    assert policy[0].source_file_sha256 == "a" * 64


def test_bi7dr_resolves_child_row_and_validity(observations) -> None:
    bi7dr = _by_code(observations)["BI7DR"]

    assert bi7dr[0].period_start == date(2022, 7, 1)
    assert _value_at(bi7dr, date(2022, 7, 1)) == 3.5
    assert all(observation.period_start >= date(2022, 7, 1) for observation in bi7dr)


def test_lending_facility_resolves_by_prefix(observations) -> None:
    lf = _by_code(observations)["LF_RATE"]

    assert _value_at(lf, date(2017, 1, 1)) == 5.5
    assert _value_at(lf, date(2026, 9, 1)) == 6.5
    assert lf[0].source_raw_label == "Lending Facility dan Financing Facility"


def test_money_supply_from_second_table() -> None:
    observations = parse_table(MONEY.read_bytes(), "TABEL1_1", load_config(), _envelope())
    money = _by_code(observations)

    assert money["MONEY_SUPPLY_M2"][0].period_start == date(2010, 1, 1)
    assert money["MONEY_SUPPLY_M2"][0].original_value == 2073859.77
    assert money["MONEY_SUPPLY_M1"][0].original_value == 496526.84
    assert money["MONEY_SUPPLY_M2"][0].normalized_unit == "miliar_idr"
    assert len(money["MONEY_SUPPLY_M2"]) == len(money["MONEY_SUPPLY_M1"])


def test_usd_middle_rate_from_v40_table() -> None:
    observations = parse_table(MID_RATE.read_bytes(), "TABEL5_40", load_config(), _envelope())
    usd = _by_code(observations)["USDIRR_SEKI"]

    assert len(usd) == 201
    assert usd[0].period_start == date(2010, 1, 1)
    assert usd[0].original_value == 9365.0
    assert usd[-1].period_start == date(2026, 9, 1)
    assert usd[-1].original_value == 17998.0
    assert usd[0].frequency == "monthly"


def test_regional_quarterly_from_section_ix() -> None:
    gdp = _by_code(parse_table(REGIONAL_GDP.read_bytes(), "TABEL9_1", load_config(), _envelope()))

    assert set(gdp) == {
        "CHN_GDP_GROWTH",
        "MYS_GDP_GROWTH",
        "PHL_GDP_GROWTH",
        "SGP_GDP_GROWTH",
        "THA_GDP_GROWTH",
    }
    china = gdp["CHN_GDP_GROWTH"]
    assert china[0].period_start == date(2010, 1, 1)
    assert china[0].period_end == date(2010, 3, 31)
    assert china[0].original_value == 12.2
    assert china[0].geography_code == "CHN"
    assert china[0].frequency == "quarterly"
    assert china[-1].period_start == date(2024, 10, 1)


def test_regional_inflation_from_section_ix() -> None:
    inflation = _by_code(
        parse_table(REGIONAL_INFLATION.read_bytes(), "TABEL9_2", load_config(), _envelope())
    )

    malaysia = inflation["MYS_INFLATION"]
    assert malaysia[0].original_value == 1.4
    assert malaysia[0].geography_code == "MYS"


def test_revenue_annual_from_section_iv() -> None:
    revenue = _by_code(
        parse_table(FISCAL_REVENUE.read_bytes(), "TABEL4_1", load_config(), _envelope())
    )

    series = revenue["APBN_REVENUE"]
    assert series[0].period_start == date(1990, 1, 1)
    assert series[0].period_end == date(1990, 12, 31)
    assert series[0].original_value == 31584.0
    assert series[0].frequency == "annual"
    assert series[0].original_unit == "miliar_idr"
    assert _value_at(series, date(2007, 1, 1)) == 694088.0
    assert _value_at(series, date(2008, 1, 1)) == 894990.6
    assert series[-1].period_start == date(2025, 1, 1)
    assert series[-1].original_value == 3005127.683257


def test_expenditure_balance_and_financing_annual() -> None:
    expenditure = _by_code(
        parse_table(FISCAL_EXPENDITURE.read_bytes(), "TABEL4_2", load_config(), _envelope())
    )
    spending = expenditure["APBN_EXPENDITURE"]
    assert spending[0].period_start == date(1990, 1, 1)
    assert spending[0].original_value == 36143.0
    assert spending[-1].original_value == 3621313.7435

    fiscal = _by_code(
        parse_table(FISCAL_FINANCING.read_bytes(), "TABEL4_3", load_config(), _envelope())
    )
    balance = fiscal["APBN_BALANCE"]
    assert balance[0].original_value == -4559.0
    assert balance[-1].original_value == -616186.060243
    financing = fiscal["APBN_FINANCING"]
    assert _value_at(financing, date(1990, 1, 1)) == 4559.0
    assert _value_at(financing, date(2008, 1, 1)) == 94503.3
    assert len(balance) == len(financing)


def test_annual_year_columns_stay_unique() -> None:
    revenue = _by_code(
        parse_table(FISCAL_REVENUE.read_bytes(), "TABEL4_1", load_config(), _envelope())
    )

    starts = [observation.period_start for observation in revenue["APBN_REVENUE"]]
    assert len(starts) == len(set(starts))


def test_sbn_outstanding_from_section_iv4() -> None:
    observations = parse_table(FISCAL_SBN.read_bytes(), "TABEL4_4", load_config(), _envelope())
    series = _by_code(observations)["SBN_OUTSTANDING"]

    assert len(series) == 203
    assert series[0].period_start == date(2008, 12, 1)
    assert series[0].original_value == 520995.0
    assert _value_at(series, date(2009, 12, 1)) == 570215.0
    assert _value_at(series, date(2010, 1, 1)) == 577665.0
    assert series[-1].period_start == date(2026, 9, 1)
    assert series[-1].original_value == 5704995.483
    assert series[0].frequency == "monthly"
    assert series[0].original_unit == "miliar_idr"

    starts = [observation.period_start for observation in series]
    assert len(starts) == len(set(starts))


def test_deposit_facility_resolves_child_row(observations) -> None:
    df = _by_code(observations)["DF_RATE"]

    assert _value_at(df, date(2017, 1, 1)) == 4.0
    assert _value_at(df, date(2026, 9, 1)) == 4.75
    assert df[0].source_raw_label == "1 Hari Sore"


def test_bi_rate_from_era_sheet(observations) -> None:
    bi_rate = _by_code(observations)["BI_RATE"]

    assert len(bi_rate) == 51
    assert bi_rate[0].period_start == date(2005, 10, 1)
    assert bi_rate[0].original_value == 11.0
    assert bi_rate[-1].period_start == date(2009, 12, 1)
    assert bi_rate[-1].original_value == 6.5


def test_extract_member_round_trips() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(f"{DEFAULT_TABLE}.xls", FIXTURE.read_bytes())

    assert extract_member(buffer.getvalue(), DEFAULT_TABLE) == FIXTURE.read_bytes()

    with pytest.raises(ParseError, match="not found in the Edition ZIP"):
        extract_member(buffer.getvalue(), "TABEL9_9")


def test_parse_edition_reads_the_zip() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(f"{DEFAULT_TABLE}.xls", FIXTURE.read_bytes())

    observations = parse_edition(buffer.getvalue(), load_config(), _envelope())

    assert _value_at(_by_code(observations)["POLICY_RATE"], date(2026, 9, 1)) == 5.75


def test_non_xls_payload_fails_loudly() -> None:
    with pytest.raises(ParseError, match="expected legacy .xls"):
        parse_table(b"<html></html>", DEFAULT_TABLE, load_config(), _envelope())


def test_missing_row_fails_loudly(tmp_path: Path) -> None:
    config_file = tmp_path / "indicators.yml"
    config_file.write_text(
        "sources:\n"
        "  BI_SEKI:\n"
        "    name: Bank Indonesia SEKI\n"
        "indicators:\n"
        "  POLICY_RATE:\n"
        "    name: Policy Rate\n"
        "    unit: percent_per_annum\n"
        "    frequency: monthly\n"
        "    source: BI_SEKI\n"
        "    source_table: TABEL1_25_1\n"
        "    source_sheets:\n"
        "      - 1.25A_1\n"
        "    source_row: Nope Rate\n",
        encoding="utf-8",
    )
    with pytest.raises(ParseError, match="not found"):
        parse_table(FIXTURE.read_bytes(), DEFAULT_TABLE, load_config(config_file), _envelope())


def test_find_latest_edition() -> None:
    period, url = find_latest_edition(INDEX_PAGE.read_text(encoding="utf-8"))

    assert period == date(2026, 9, 1)
    assert url.endswith("/Pages/SEKI-SEPTEMBER-2026.aspx")


def test_find_latest_edition_fails_without_links() -> None:
    with pytest.raises(ParseError, match="no Edition links"):
        find_latest_edition("<html><body>nothing</body></html>")


def test_find_zip_url() -> None:
    page_url = (
        "https://www.bi.go.id/id/statistik/ekonomi-keuangan/seki/Pages/SEKI-SEPTEMBER-2026.aspx"
    )
    url = find_zip_url(EDITION_PAGE.read_text(encoding="utf-8"), page_url)

    assert url.endswith("/Documents/SEKI_SEPTEMBER_2026.zip")


def test_find_zip_url_fails_loudly() -> None:
    with pytest.raises(ParseError, match="no ZIP link"):
        find_zip_url("<html></html>", INDEX_URL)


def test_fetch_edition_walks_the_pages() -> None:
    zip_bytes = _zip_bytes()
    session = _Session(
        INDEX_PAGE.read_text(encoding="utf-8"),
        EDITION_PAGE.read_text(encoding="utf-8"),
        zip_bytes,
    )
    _, sleep = _slept()

    artifact = fetch_edition(session=session, sleep=sleep)

    assert artifact.period == date(2026, 9, 1)
    assert artifact.content == zip_bytes
    assert artifact.zip_url.endswith("/Documents/SEKI_SEPTEMBER_2026.zip")
    assert [call for call in session.calls if call == INDEX_URL] == [INDEX_URL]
    assert len(session.calls) == 3


def test_run_composes_fetch_and_parse(monkeypatch: pytest.MonkeyPatch) -> None:
    zip_bytes = _zip_bytes()
    monkeypatch.setattr(
        "pipeline.sources.bi_seki.fetch_edition",
        lambda **kwargs: EditionArtifact(
            content=zip_bytes,
            edition_url="https://www.bi.go.id/edition",
            zip_url="https://www.bi.go.id/edition.zip",
            period=date(2026, 9, 1),
        ),
    )

    result = run(ingestion_run_id="run-1")

    assert result.envelope.period_start == date(2026, 9, 1)
    assert result.envelope.period_end == date(2026, 9, 30)
    assert result.envelope.source_id == SOURCE_ID
    policy = _by_code(result.observations)["POLICY_RATE"]
    assert _value_at(policy, date(2026, 9, 1)) == 5.75
    assert "MONEY_SUPPLY_M2" in _by_code(result.observations)
    assert len(result.artifacts) == 1
    assert result.artifacts[0].name == "edition.zip"
    assert result.artifacts[0].content == zip_bytes


def test_build_envelope_covers_the_edition_month() -> None:
    artifact = EditionArtifact(
        content=_zip_bytes(),
        edition_url="https://www.bi.go.id/edition",
        zip_url="https://www.bi.go.id/edition.zip",
        period=date(2026, 9, 1),
    )

    envelope = build_envelope(artifact, ingestion_run_id="run-1")

    assert envelope.period_start == date(2026, 9, 1)
    assert envelope.period_end == date(2026, 9, 30)
    assert envelope.source_url == "https://www.bi.go.id/edition"
