"""BPS adapter: inflation from the BPS WebAPI.

The BPS WebAPI is a generic dynamic-table service, not a per-indicator endpoint:
data is requested per Variable over a reporting year and returned as a
``datacontent`` map whose keys are the concatenated ``vervar`` / ``var`` / ``th``
/ ``turth`` identifiers. This adapter resolves the Variable and Vertical
Variable from ``indicators.yml``, walks the requested years, and turns the
national series into monthly Observations. Every response is kept as its own
lineage unit (its checksum is the Observation's ``source_file_sha256``), and the
run envelope checksums the concatenation of the raw responses.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import UTC, date, datetime

import requests

from pipeline.config import IndicatorConfig, IndicatorsConfig, load_config
from pipeline.http import browser_headers, new_session, request_with_retry
from pipeline.models import Artifact, IngestionEnvelope, Observation, SourceRunResult
from pipeline.parsing import ParseError, month_end, month_number, sha256_hex

SOURCE_ID = "BPS"
API_BASE = "https://webapi.bps.go.id/v1/api"
API_KEY_ENV = "BPS_API_KEY"
CONTENT_TYPE = "application/json"
DEFAULT_DOMAIN = "0000"
NATIONAL_VERVAR = 9999
_QUARTERS = {"triwulan i": 1, "triwulan ii": 2, "triwulan iii": 3, "triwulan iv": 4}
_BROWSER_HEADERS = browser_headers(accept="application/json, text/plain, */*")
_REQUEST_TIMEOUT = 60.0
_PACE_SECONDS = 3.0
_ATTEMPTS = 3
_BACKOFF_SECONDS = 20.0

_logger = logging.getLogger(__name__)


def api_key_from_env() -> str:
    """Return the BPS API key from the environment, or fail loudly."""
    key = os.environ.get(API_KEY_ENV)
    if not key:
        raise ParseError(f"{SOURCE_ID}: {API_KEY_ENV} is not set")
    return key


def list_periods(
    var: int,
    *,
    domain: str,
    api_key: str,
    session: requests.Session,
) -> list[tuple[int, int]]:
    """Return every ``(th_id, year)`` the Variable publishes, across all pages."""
    periods: list[tuple[int, int]] = []
    page = 1
    while True:
        payload = _get_json(
            f"/list/model/th/domain/{domain}/var/{var}/page/{page}/key/{api_key}/", session
        )
        meta, rows = _split(payload)
        for row in rows:
            try:
                periods.append((int(row["th_id"]), int(row["th"])))
            except (KeyError, TypeError, ValueError) as exc:
                raise ParseError(f"{SOURCE_ID}: malformed period row {row!r}") from exc
        if not rows or page >= int(meta.get("pages", 1)):
            break
        page += 1
    if not periods:
        raise ParseError(f"{SOURCE_ID}: variable {var} publishes no periods")
    return periods


def fetch_payload(
    var: int,
    th_id: int,
    *,
    domain: str,
    api_key: str,
    session: requests.Session,
) -> tuple[dict, bytes]:
    """Fetch one Variable-year response, returning the parsed and raw bytes."""
    response = session.get(
        f"{API_BASE}/list/model/data/domain/{domain}/var/{var}/th/{th_id}/key/{api_key}/",
        timeout=_REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    raw = response.content
    payload = _decode(raw)
    if "datacontent" not in payload:
        raise ParseError(f"{SOURCE_ID}: variable {var} th {th_id} returned no data")
    return payload, raw


def parse_payload(
    payload: dict,
    indicator: IndicatorConfig,
    envelope: IngestionEnvelope,
    source_file_sha256: str,
) -> tuple[Observation, ...]:
    """Turn one Variable-year response into Observations for the bound series.

    The ``datacontent`` key is the concatenation ``vervar`` + ``var`` + ``turvar``
    + ``th`` + ``turth`` as raw digits, so the first five are reconstructed from
    config and the trailing ``turth`` selects the Reporting Period.
    """
    var = _require_var(indicator)
    vervar = indicator.source_vervar if indicator.source_vervar is not None else NATIONAL_VERVAR
    turvar = indicator.source_turvar or 0
    meta = _first(payload.get("var"), indicator.code, "var")
    tahun = _first(payload.get("tahun"), indicator.code, "tahun")
    year = int(tahun["label"])
    th_id = int(tahun["val"])

    periods = _periods(payload.get("turtahun"), year, indicator.frequency)
    prefix = f"{vervar}{var}{turvar}{th_id}"

    datacontent = payload.get("datacontent") or {}
    observations: list[Observation] = []
    for key, value in datacontent.items():
        if value is None or not key.startswith(prefix):
            continue
        period = periods.get(int(key[len(prefix) :]))
        if period is None:
            continue
        observations.append(
            _observation(float(value), *period, meta, indicator, envelope, source_file_sha256)
        )
    if not observations:
        raise ParseError(f"{SOURCE_ID}: no values for {indicator.code} in th {th_id}")
    observations.sort(key=lambda observation: observation.period_start)
    return tuple(observations)


def run(
    period_start: date,
    period_end: date,
    *,
    ingestion_run_id: str,
    config: IndicatorsConfig | None = None,
    api_key: str | None = None,
    session: requests.Session | None = None,
    retrieved_at: datetime | None = None,
    sleep=time.sleep,
) -> SourceRunResult:
    """Fetch and parse every BPS Indicator for the requested year range."""
    config = config or load_config()
    indicators = [
        indicator for indicator in config.indicators.values() if indicator.source == SOURCE_ID
    ]
    if not indicators:
        raise ParseError(f"{SOURCE_ID}: no Indicators are configured for this source")

    key = api_key or api_key_from_env()
    http = new_session(_BROWSER_HEADERS, session)

    fetched: list[tuple[IndicatorConfig, dict, bytes]] = []
    artifacts: list[Artifact] = []
    for indicator in indicators:
        var = _require_var(indicator)
        domain = indicator.source_domain or DEFAULT_DOMAIN
        periods = request_with_retry(
            lambda var=var, domain=domain: list_periods(
                var, domain=domain, api_key=key, session=http
            ),
            source_id=SOURCE_ID,
            label=f"{indicator.code} periods",
            attempts=_ATTEMPTS,
            backoff=_BACKOFF_SECONDS,
            sleep=sleep,
        )
        by_year = {year: th_id for th_id, year in periods}
        for year in range(period_start.year, period_end.year + 1):
            th_id = by_year.get(year)
            if th_id is None:
                _logger.info("%s: %s has no period for %d", SOURCE_ID, indicator.code, year)
                continue
            sleep(_PACE_SECONDS)
            payload = request_with_retry(
                lambda var=var, th_id=th_id, domain=domain: fetch_payload(
                    var, th_id, domain=domain, api_key=key, session=http
                ),
                source_id=SOURCE_ID,
                label=f"{indicator.code} th {th_id}",
                attempts=_ATTEMPTS,
                backoff=_BACKOFF_SECONDS,
                sleep=sleep,
            )
            fetched.append((indicator, *payload))
            artifacts.append(
                Artifact(
                    name=f"bps_var{var}_th{th_id}.json",
                    content_type=CONTENT_TYPE,
                    content=payload[1],
                )
            )

    if not fetched:
        raise ParseError(f"{SOURCE_ID}: no data returned for {period_start}..{period_end}")

    blob = b"\n".join(raw for _, _, raw in fetched)
    envelope = IngestionEnvelope(
        source_id=SOURCE_ID,
        source_url=API_BASE,
        retrieved_at=retrieved_at or datetime.now(UTC),
        period_start=period_start,
        period_end=period_end,
        source_file_sha256=sha256_hex(blob),
        ingestion_run_id=ingestion_run_id,
        source_version=1,
    )

    observations: list[Observation] = []
    for indicator, payload, raw in fetched:
        observations.extend(parse_payload(payload, indicator, envelope, sha256_hex(raw)))
    return SourceRunResult(
        envelope=envelope,
        observations=tuple(observations),
        artifacts=tuple(artifacts),
    )


def _observation(
    value: float,
    period_start: date,
    period_end: date,
    meta: dict,
    indicator: IndicatorConfig,
    envelope: IngestionEnvelope,
    source_file_sha256: str,
) -> Observation:
    return Observation.from_source(
        envelope,
        source_table=str(indicator.source_var),
        indicator_code=indicator.code,
        period_start=period_start,
        period_end=period_end,
        frequency=indicator.frequency,
        value=value,
        unit=indicator.unit,
        source_raw_label=str(meta.get("label", indicator.name)),
        source_file_sha256=source_file_sha256,
    )


def _get_json(path: str, session: requests.Session) -> dict:
    response = session.get(f"{API_BASE}{path}", timeout=_REQUEST_TIMEOUT)
    response.raise_for_status()
    return _decode(response.content)


def _decode(raw: bytes) -> dict:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ParseError(f"{SOURCE_ID}: response is not valid JSON") from exc
    if payload.get("status") not in (None, "OK"):
        raise ParseError(f"{SOURCE_ID}: API returned status {payload.get('status')!r}")
    return payload


def _split(payload: dict) -> tuple[dict, list]:
    data = payload.get("data")
    if isinstance(data, list) and len(data) == 2 and isinstance(data[1], list):
        return data[0], data[1]
    return {}, []


def _first(items: object, code: str, field: str) -> dict:
    if not isinstance(items, list) or not items:
        raise ParseError(f"{SOURCE_ID}: missing {field} for {code}")
    return items[0]


def _periods(turtahun: object, year: int, frequency: str) -> dict[int, tuple[date, date]]:
    periods: dict[int, tuple[date, date]] = {}
    for entry in turtahun or []:
        label = str(entry.get("label", "")).strip().lower()
        if frequency == "quarterly":
            quarter = _QUARTERS.get(label)
            if quarter is None:
                continue
            start_month = 3 * (quarter - 1) + 1
            periods[int(entry["val"])] = (
                date(year, start_month, 1),
                month_end(year, start_month + 2),
            )
        else:
            month = month_number(label)
            if month is not None:
                periods[int(entry["val"])] = (date(year, month, 1), month_end(year, month))
    return periods


def _require_var(indicator: IndicatorConfig) -> int:
    if indicator.source_var is None:
        raise ParseError(f"{SOURCE_ID}: Indicator {indicator.code} has no source_var")
    return indicator.source_var
