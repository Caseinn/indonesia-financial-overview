"""OJK SJKPublic adapter: banking ratios from the portal's XMLA cube.

The portal exposes metadata over a DevExtreme JSON cascade, but it serves the
measure *values* from a DevExpress ``XmlaStore`` — MDX over SOAP to
``/SJKPublic/datasource/``. This adapter posts one MDX query per Indicator (its
catalog, cube, measure, and ``[Akun]`` member come from ``indicators.yml``) and
parses the returned ``MDDATASET`` XML into monthly Observations, mapping the
``[Bulan]`` member's ``YYYY-MM`` caption to a Reporting Period and failing loudly
when the cube or the period axis drifts.
"""

from __future__ import annotations

import re
import time
from datetime import UTC, date, datetime
from xml.etree import ElementTree

import requests

from pipeline.config import IndicatorConfig, IndicatorsConfig, load_config
from pipeline.http import browser_headers, new_session, request_with_retry
from pipeline.models import Artifact, IngestionEnvelope, Observation, SourceRunResult
from pipeline.parsing import ParseError, month_end, sha256_hex

SOURCE_ID = "OJK_SPI"
DATASOURCE_URL = "https://data.ojk.go.id/SJKPublic/datasource/"
DEFAULT_CATALOG = "PORTALSJKCUBE_BU"
CONTENT_TYPE = "application/xml"
MONTH_HIERARCHY = "[Bulan].[Bulan]"
_BROWSER_HEADERS = browser_headers(
    content_type="text/xml; charset=utf-8",
    origin="https://data.ojk.go.id",
    soap_action='"urn:schemas-microsoft-com:xml-analysis:Execute"',
)
_REQUEST_TIMEOUT = 120.0
_ATTEMPTS = 3
_BACKOFF_SECONDS = 20.0
_ENVELOPE = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
    '<soap:Body><Execute xmlns="urn:schemas-microsoft-com:xml-analysis">'
    "<Command><Statement>{statement}</Statement></Command>"
    "<Properties><PropertyList><Catalog>{catalog}</Catalog></PropertyList></Properties>"
    "</Execute></soap:Body></soap:Envelope>"
)

MonthRows = list[tuple[dict[str, str], float | None]]


def build_mdx(indicator: IndicatorConfig) -> str:
    """Build the MDX for one Indicator, or return its explicit ``source_mdx``."""
    if indicator.source_mdx:
        return indicator.source_mdx
    measure = _require(indicator, "source_measure")
    cube = _require(indicator, "source_cube")
    if indicator.source_member:
        rows = f"{{{indicator.source_member}}}"
    elif indicator.source_dimension:
        rows = f"{{{indicator.source_dimension}.members}}"
    else:
        raise ParseError(f"{SOURCE_ID}: Indicator {indicator.code} has no member or dimension")
    return (
        f"SELECT [Measures].[{measure}] ON 0, "
        f"NON EMPTY {rows} * {{{MONTH_HIERARCHY}.members}} ON 1 "
        f"FROM [{cube}]"
    )


def execute_mdx(
    mdx: str,
    *,
    catalog: str,
    session: requests.Session | None = None,
) -> bytes:
    """POST one MDX statement to the portal's XMLA endpoint."""
    http = new_session(_BROWSER_HEADERS, session)
    body = _ENVELOPE.format(statement=_xml_escape(mdx), catalog=catalog).encode("utf-8")
    response = http.post(DATASOURCE_URL, data=body, timeout=_REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.content


def parse_dataset(xml_bytes: bytes) -> MonthRows:
    """Parse the ``MDDATASET`` XML into (member map, value) rows for Axis1.

    Each row keeps a ``hierarchy -> caption`` map so the caller can read the
    ``[Bulan]`` period; the cell value is read by ordinal (one measure per axis).
    """
    try:
        root = ElementTree.fromstring(xml_bytes)
    except ElementTree.ParseError as exc:
        raise ParseError(f"{SOURCE_ID}: response is not well-formed XML") from exc
    if any(_local(element.tag) == "Fault" for element in root.iter()):
        raise ParseError(f"{SOURCE_ID}: XMLA returned a SOAP fault")

    axes: dict[str, list[dict[str, str]]] = {}
    for element in root.iter():
        if _local(element.tag) != "Axis":
            continue
        name = element.get("name")
        if name:
            axes[name] = _axis_tuples(element)

    rows = axes.get("Axis1", [])
    columns = max(len(axes.get("Axis0", ())), 1)
    cells = _cells(root)

    parsed: MonthRows = []
    for index, members in enumerate(rows):
        parsed.append((members, cells.get(index * columns)))
    return parsed


def parse_metric(
    xml_bytes: bytes,
    indicator: IndicatorConfig,
    envelope: IngestionEnvelope,
) -> tuple[Observation, ...]:
    """Turn one XMLA response into monthly Observations for one Indicator."""
    observations: list[Observation] = []
    for members, value in parse_dataset(xml_bytes):
        caption = members.get(MONTH_HIERARCHY)
        if value is None or caption is None:
            continue
        period = _period(caption)
        if period is None:
            continue
        dimension = _dimension_code(members, indicator)
        if indicator.source_dimension and not dimension:
            continue
        period_start, period_end = period
        observations.append(
            _observation(
                value,
                period_start,
                period_end,
                caption,
                dimension,
                indicator,
                envelope,
            )
        )
    if not observations:
        raise ParseError(f"{SOURCE_ID}: no values for {indicator.code}")
    observations.sort(
        key=lambda observation: (observation.period_start, observation.dimension_code)
    )
    return tuple(observations)


def run(
    *,
    ingestion_run_id: str,
    config: IndicatorsConfig | None = None,
    session: requests.Session | None = None,
    retrieved_at: datetime | None = None,
    sleep=time.sleep,
) -> SourceRunResult:
    """Fetch and parse every OJK Indicator from the XMLA cube."""
    config = config or load_config()
    indicators = [
        indicator
        for indicator in config.indicators.values()
        if indicator.source == SOURCE_ID and (indicator.source_measure or indicator.source_mdx)
    ]
    if not indicators:
        raise ParseError(f"{SOURCE_ID}: no portal Indicators are configured for this source")

    http = new_session(_BROWSER_HEADERS, session)

    blobs: list[bytes] = []
    responses: list[tuple[IndicatorConfig, bytes]] = []
    for indicator in indicators:
        xml_bytes = request_with_retry(
            lambda indicator=indicator: execute_mdx(
                build_mdx(indicator),
                catalog=indicator.source_catalog or DEFAULT_CATALOG,
                session=http,
            ),
            source_id=SOURCE_ID,
            label=indicator.code,
            attempts=_ATTEMPTS,
            backoff=_BACKOFF_SECONDS,
            sleep=sleep,
        )
        blobs.append(xml_bytes)
        responses.append((indicator, xml_bytes))

    envelope = IngestionEnvelope(
        source_id=SOURCE_ID,
        source_url=DATASOURCE_URL,
        retrieved_at=retrieved_at or datetime.now(UTC),
        period_start=date.min,
        period_end=date.min,
        source_file_sha256=sha256_hex(b"\n".join(blobs)),
        ingestion_run_id=ingestion_run_id,
        source_version=1,
    )

    observations: list[Observation] = []
    artifacts: list[Artifact] = []
    for indicator, xml_bytes in responses:
        observations.extend(parse_metric(xml_bytes, indicator, envelope))
        artifacts.append(
            Artifact(
                name=f"ojk_{indicator.code.lower()}.xml",
                content_type=CONTENT_TYPE,
                content=xml_bytes,
            )
        )

    period_start = min(observation.period_start for observation in observations)
    period_end = max(observation.period_end for observation in observations)
    envelope = IngestionEnvelope(
        source_id=SOURCE_ID,
        source_url=DATASOURCE_URL,
        retrieved_at=envelope.retrieved_at,
        period_start=period_start,
        period_end=period_end,
        source_file_sha256=envelope.source_file_sha256,
        ingestion_run_id=ingestion_run_id,
        source_version=1,
    )
    return SourceRunResult(
        envelope=envelope,
        observations=tuple(observations),
        artifacts=tuple(artifacts),
    )


def _observation(
    value: float,
    period_start: date,
    period_end: date,
    caption: str,
    dimension_code: str,
    indicator: IndicatorConfig,
    envelope: IngestionEnvelope,
) -> Observation:
    return Observation.from_source(
        envelope,
        source_table=indicator.source_cube or "",
        indicator_code=indicator.code,
        period_start=period_start,
        period_end=period_end,
        frequency=indicator.frequency,
        value=value,
        unit=indicator.unit,
        source_raw_label=indicator.source_member or caption,
        dimension_code=dimension_code,
    )


def _dimension_code(members: dict[str, str], indicator: IndicatorConfig) -> str:
    if not indicator.source_dimension:
        return ""
    text = members.get(indicator.source_dimension, "")
    match = re.match(r"\s*(\d+)", text)
    return match.group(1) if match else ""


def _axis_tuples(axis: ElementTree.Element) -> list[dict[str, str]]:
    tuples: list[dict[str, str]] = []
    for element in axis.iter():
        if _local(element.tag) != "Tuple":
            continue
        members: dict[str, str] = {}
        for member in element:
            if _local(member.tag) != "Member":
                continue
            hierarchy = member.get("Hierarchy", "")
            members[hierarchy] = _child_text(member, "Caption")
        tuples.append(members)
    return tuples


def _cells(root: ElementTree.Element) -> dict[int, float]:
    cells: dict[int, float] = {}
    for element in root.iter():
        if _local(element.tag) != "Cell":
            continue
        ordinal = element.get("CellOrdinal")
        text = _child_text(element, "Value")
        if ordinal is None or text in (None, ""):
            continue
        cells[int(ordinal)] = float(text)
    return cells


def _period(caption: str) -> tuple[date, date] | None:
    match = re.fullmatch(r"(\d{4})-(\d{2})", caption.strip())
    if match is None:
        return None
    year, month = int(match.group(1)), int(match.group(2))
    return date(year, month, 1), month_end(year, month)


def _child_text(element: ElementTree.Element, name: str) -> str | None:
    for child in element:
        if _local(child.tag) == name:
            return child.text
    return None


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _xml_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _require(indicator: IndicatorConfig, field: str) -> str:
    value = getattr(indicator, field)
    if not value:
        raise ParseError(f"{SOURCE_ID}: Indicator {indicator.code} is missing {field}")
    return value
