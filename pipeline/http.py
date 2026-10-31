"""Shared HTTP plumbing for source adapters.

Every source sits behind a WAF that rejects default clients and drops request
bursts, so the browser identity, session setup, and retry-with-backoff live here
once instead of being copy-pasted into each adapter.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

import requests

from pipeline.parsing import ParseError
from pipeline.redaction import redact

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
ACCEPT_LANGUAGE = "en-US,en;q=0.9"

_logger = logging.getLogger(__name__)


def browser_headers(
    *,
    accept: str | None = None,
    origin: str | None = None,
    referer: str | None = None,
    content_type: str | None = None,
    soap_action: str | None = None,
) -> dict[str, str]:
    """Build browser-like request headers so a WAF treats us as a real client."""
    headers = {"User-Agent": USER_AGENT, "Accept-Language": ACCEPT_LANGUAGE}
    for name, value in (
        ("Accept", accept),
        ("Origin", origin),
        ("Referer", referer),
        ("Content-Type", content_type),
        ("SOAPAction", soap_action),
    ):
        if value is not None:
            headers[name] = value
    return headers


def new_session(
    headers: dict[str, str], session: requests.Session | None = None
) -> requests.Session:
    """Return a session with ``headers`` applied, reusing one when provided."""
    http = session if session is not None else requests.Session()
    http.headers.update(headers)
    return http


def request_with_retry[T](
    operation: Callable[[], T],
    *,
    source_id: str,
    label: str,
    attempts: int,
    backoff: float,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Run ``operation``, retrying transport and parse failures with backoff.

    A WAF that drops a burst clears after a quiet pause, so a failed attempt
    waits ``backoff`` seconds before trying again, up to ``attempts`` times.
    """
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except (requests.RequestException, ParseError) as exc:
            last_error = exc
            _logger.warning(
                "%s: %s attempt %d/%d failed: %s",
                source_id,
                label,
                attempt,
                attempts,
                redact(str(exc)),
            )
            if attempt < attempts:
                sleep(backoff)
    raise ParseError(f"{source_id}: {label} failed after {attempts} attempts") from last_error
