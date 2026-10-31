"""Best-effort webhook alerts for pipeline findings.

Alerts must never fail a run: a broken webhook is logged and swallowed so the
pipeline still finishes and records its outcome in ``ops``.
"""

from __future__ import annotations

import logging

import requests

_logger = logging.getLogger(__name__)


def send(
    webhook_url: str | None,
    payload: dict[str, object],
    *,
    session: requests.Session | None = None,
    timeout: float = 10.0,
) -> bool:
    """Post an alert to the webhook, returning whether it was delivered."""
    if not webhook_url:
        return False
    http = session or requests.Session()
    try:
        response = http.post(webhook_url, json=payload, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        detail = f"HTTP {status}" if status is not None else type(exc).__name__
        _logger.warning("alert webhook failed (%s)", detail)
        return False
    return True
