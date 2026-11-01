"""Tests for the OJK SJKPublic adapter, against real trimmed XMLA responses."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import ClassVar

import pytest

from pipeline.config import load_config
from pipeline.models import IngestionEnvelope
from pipeline.parsing import ParseError
from pipeline.sources.ojk_sjk import (
    SOURCE_ID,
    build_mdx,
    execute_mdx,
    parse_dataset,
    parse_metric,
    run,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "ojk"
CAR = FIXTURES / "rasio_car.xml"
ROA = FIXTURES / "rasio_roa.xml"
LDR = FIXTURES / "rasio_ldr.xml"
NPL = FIXTURES / "npl_ratio.xml"
SECTOR = FIXTURES / "credit_sector.xml"


def _envelope() -> IngestionEnvelope:
    return IngestionEnvelope(
        source_id=SOURCE_ID,
        source_url="https://data.ojk.go.id/SJKPublic/datasource/",
        retrieved_at=datetime(2026, 10, 15, 12, 0, 0),
        period_start=date(2025, 7, 1),
        period_end=date(2026, 7, 31),
        source_file_sha256="f" * 64,
        ingestion_run_id="run-1",
        source_version=1,
    )


class _Response:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def raise_for_status(self) -> None:
        return None


class _Session:
    """Serves a fixture per metric by matching the MDX member in the request."""

    _ROUTES: ClassVar[dict[str, Path]] = {
        "001.Rasio Pemenuhan": CAR,
        "003.Return On Assets": ROA,
        "006.Loan to Deposits": LDR,
        "NPL Ratio": NPL,
        "[Sektor Ekonomi].[Sektor Ekonomi].members": SECTOR,
    }

    def __init__(self) -> None:
        self.headers: dict[str, str] = {}
        self.calls: list[bytes] = []

    def post(self, url: str, data: bytes, **kwargs: object) -> _Response:
        self.calls.append(data)
        text = data.decode("utf-8")
        for token, path in self._ROUTES.items():
            if token in text:
                return _Response(path.read_bytes())
        raise AssertionError("unexpected MDX request")


class _CaptureSession:
    """Records request bodies and returns a trivial response."""

    def __init__(self) -> None:
        self.headers: dict[str, str] = {}
        self.calls: list[bytes] = []

    def post(self, url: str, data: bytes, **kwargs: object) -> _Response:
        self.calls.append(data)
        return _Response(b"<ok/>")


def test_parse_dataset_rows() -> None:
    rows = parse_dataset(CAR.read_bytes())

    assert len(rows) == 14
    assert rows[0][0].get("[Bulan].[Bulan]") == "All"
    assert rows[1][0].get("[Bulan].[Bulan]") == "2025-07"
    assert rows[1][1] == pytest.approx(25.877, abs=0.01)


def test_parse_metric_car() -> None:
    observations = parse_metric(CAR.read_bytes(), load_config().indicator("CAR"), _envelope())

    assert len(observations) == 13
    assert observations[0].period_start == date(2025, 7, 1)
    assert observations[0].period_end == date(2025, 7, 31)
    assert observations[-1].period_start == date(2026, 7, 1)
    assert observations[0].original_value == pytest.approx(25.877, abs=0.01)
    assert observations[0].frequency == "monthly"
    assert observations[0].normalized_unit == "percent"
    assert observations[0].source_raw_label.startswith("[Akun].[Akun].&[001.")


def test_parse_metric_ldr() -> None:
    observations = parse_metric(LDR.read_bytes(), load_config().indicator("LDR"), _envelope())

    assert len(observations) == 13
    assert observations[0].original_value == pytest.approx(86.549, abs=0.01)


def test_parse_metric_npl_ratio() -> None:
    observations = parse_metric(NPL.read_bytes(), load_config().indicator("NPL"), _envelope())

    assert len(observations) == 43
    assert observations[0].period_start == date(2023, 1, 1)
    assert observations[0].original_value == pytest.approx(2.566, abs=0.01)
    assert observations[-1].original_value == pytest.approx(2.074, abs=0.01)


def test_credit_by_sector_uses_dimension_code() -> None:
    indicator = load_config().indicator("CREDIT_BY_SECTOR")
    observations = parse_metric(SECTOR.read_bytes(), indicator, _envelope())

    assert len(observations) == 84
    assert {o.dimension_code for o in observations} == {f"{i:03d}" for i in range(1, 29)}
    assert len({o.business_key for o in observations}) == 84
    first = observations[0]
    assert first.period_start == date(2026, 5, 1)
    assert first.dimension_code == "001"
    assert first.original_unit == "idr"


def test_build_mdx_has_measure_and_member() -> None:
    mdx = build_mdx(load_config().indicator("ROA"))

    assert "[Measures].[Rasio Keuangan]" in mdx
    assert "003.Return On Assets Ratio (%)" in mdx
    assert "FROM [BU_RasioKeuangan]" in mdx


def test_execute_mdx_escapes_ampersand() -> None:
    session = _CaptureSession()

    execute_mdx("SELECT [Akun].[Akun].&[006.x]", catalog="PORTALSJKCUBE_BU", session=session)

    assert b"&amp;[006.x]" in session.calls[0]
    assert b"&[006.x]" not in session.calls[0]


def test_run_parses_every_indicator() -> None:
    result = run(ingestion_run_id="run-1", session=_Session())

    codes = {observation.indicator_code for observation in result.observations}
    assert codes == {"CAR", "ROA", "LDR", "NPL", "CREDIT_BY_SECTOR"}
    assert len(result.observations) == 166
    assert result.envelope.period_start == date(2023, 1, 1)
    assert result.envelope.period_end == date(2026, 7, 31)
    assert {artifact.name for artifact in result.artifacts} == {
        "ojk_car.xml",
        "ojk_roa.xml",
        "ojk_ldr.xml",
        "ojk_npl.xml",
        "ojk_credit_by_sector.xml",
    }


def test_soap_fault_fails_loudly() -> None:
    fault = (
        b'<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
        b"<soap:Body><soap:Fault><faultstring>boom</faultstring></soap:Fault></soap:Body>"
        b"</soap:Envelope>"
    )
    with pytest.raises(ParseError, match="SOAP fault"):
        parse_dataset(fault)
