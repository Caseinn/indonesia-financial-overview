"""Tests for the BPS adapter, against real trimmed API responses."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest

from pipeline.config import load_config
from pipeline.models import IngestionEnvelope
from pipeline.parsing import ParseError
from pipeline.sources.bps import (
    SOURCE_ID,
    api_key_from_env,
    list_periods,
    parse_payload,
    run,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "bps"
TH124 = FIXTURES / "bps_inflasi_mom_th124.json"
TH125 = FIXTURES / "bps_inflasi_mom_th125.json"
GDP124 = FIXTURES / "bps_gdp_yoy_th124.json"
GDP125 = FIXTURES / "bps_gdp_yoy_th125.json"


def _envelope() -> IngestionEnvelope:
    return IngestionEnvelope(
        source_id=SOURCE_ID,
        source_url="https://webapi.bps.go.id/v1/api",
        retrieved_at=datetime(2026, 10, 15, 12, 0, 0),
        period_start=date(2024, 1, 1),
        period_end=date(2025, 12, 31),
        source_file_sha256="b" * 64,
        ingestion_run_id="run-1",
        source_version=1,
    )


class _Response:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def raise_for_status(self) -> None:
        return None


class _Session:
    def __init__(self, routes: dict[str, bytes]) -> None:
        self.headers: dict[str, str] = {}
        self.routes = routes
        self.calls: list[str] = []

    def get(self, url: str, **kwargs: object) -> _Response:
        self.calls.append(url)
        for token, content in self.routes.items():
            if token in url:
                return _Response(content)
        raise AssertionError(f"unexpected URL: {url}")


def _load(path: Path) -> dict:
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def _indicator():
    return load_config().indicator("INFLASI_MOM")


def _value_at(observations, period: date) -> float:
    for observation in observations:
        if observation.period_start == period:
            return observation.original_value
    raise AssertionError(f"no observation at {period}")


def test_parse_payload_2024() -> None:
    observations = parse_payload(_load(TH124), _indicator(), _envelope(), "c" * 64)

    assert len(observations) == 12
    assert observations[0].period_start == date(2024, 1, 1)
    assert observations[-1].period_end == date(2024, 12, 31)
    assert _value_at(observations, date(2024, 1, 1)) == 0.04
    assert _value_at(observations, date(2024, 3, 1)) == 0.52
    assert observations[0].frequency == "monthly"
    assert observations[0].original_unit == "percent"
    assert observations[0].source_raw_label == "Inflasi Bulanan (M-to-M)"
    assert observations[0].source_file_sha256 == "c" * 64


def test_parse_payload_2025() -> None:
    observations = parse_payload(_load(TH125), _indicator(), _envelope(), "c" * 64)

    assert len(observations) == 12
    assert _value_at(observations, date(2025, 1, 1)) == -0.76
    assert _value_at(observations, date(2025, 3, 1)) == 1.65
    assert _value_at(observations, date(2025, 12, 1)) == 0.64


def test_parse_payload_fails_on_empty() -> None:
    with pytest.raises(ParseError, match="no values"):
        parse_payload(
            {
                "var": _load(TH125)["var"],
                "tahun": _load(TH125)["tahun"],
                "turtahun": [],
                "datacontent": {},
            },
            _indicator(),
            _envelope(),
            "c" * 64,
        )


def test_parse_payload_gdp_quarterly() -> None:
    indicator = load_config().indicator("GDP_GROWTH_YOY")
    observations = parse_payload(_load(GDP124), indicator, _envelope(), "d" * 64)

    assert len(observations) == 4
    assert observations[0].period_start == date(2024, 1, 1)
    assert observations[0].period_end == date(2024, 3, 31)
    assert observations[-1].period_start == date(2024, 10, 1)
    assert observations[-1].period_end == date(2024, 12, 31)
    assert _value_at(observations, date(2024, 1, 1)) == 5.11
    assert _value_at(observations, date(2024, 10, 1)) == 5.02
    assert observations[0].frequency == "quarterly"
    assert (
        observations[0].source_raw_label
        == "[Seri 2010] 4. Laju Pertumbuhan PDB menurut Pengeluaran"
    )


def test_list_periods_paginates() -> None:
    payload = '{"status":"OK","data":[{"page":1,"pages":1,"total":2},[{"th_id":124,"th":2024},{"th_id":125,"th":2025}]]}'
    session = _Session({"/model/th/": payload.encode()})

    assert list_periods(1, domain="0000", api_key="k", session=session) == [
        (124, 2024),
        (125, 2025),
    ]


def test_run_walks_years() -> None:
    periods = '{"status":"OK","data":[{"page":1,"pages":1,"total":2},[{"th_id":124,"th":2024},{"th_id":125,"th":2025}]]}'
    session = _Session(
        {
            "model/th/domain/0000/var/1/": periods.encode(),
            "model/th/domain/0000/var/108/": periods.encode(),
            "var/1/th/124/": TH124.read_bytes(),
            "var/1/th/125/": TH125.read_bytes(),
            "var/108/th/124/": GDP124.read_bytes(),
            "var/108/th/125/": GDP125.read_bytes(),
        }
    )

    result = run(
        date(2024, 1, 1),
        date(2025, 12, 31),
        ingestion_run_id="run-1",
        api_key="k",
        session=session,
        sleep=lambda _seconds: None,
    )

    assert result.envelope.source_id == SOURCE_ID
    assert len(result.observations) == 32
    codes = {observation.indicator_code for observation in result.observations}
    assert codes == {"INFLASI_MOM", "GDP_GROWTH_YOY"}
    assert _value_at(result.observations, date(2025, 12, 1)) == 0.64
    gdp = [o for o in result.observations if o.indicator_code == "GDP_GROWTH_YOY"]
    assert _value_at(gdp, date(2024, 1, 1)) == 5.11
    assert {artifact.name for artifact in result.artifacts} == {
        "bps_var1_th124.json",
        "bps_var1_th125.json",
        "bps_var108_th124.json",
        "bps_var108_th125.json",
    }


def test_api_key_missing_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BPS_API_KEY", raising=False)

    with pytest.raises(ParseError, match="BPS_API_KEY is not set"):
        api_key_from_env()
