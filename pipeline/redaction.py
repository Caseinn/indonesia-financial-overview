"""Redact credentials from log-bound error text.

Source APIs sometimes carry secrets in the request URL (the BPS key is a path
segment), and transport exceptions echo that URL back. Error text bound for a
log line or failure alert passes through these helpers so the pipeline never
prints a credential.
"""

from __future__ import annotations

import re
import traceback

_API_KEY_PATH = re.compile(r"(?i)(/key/)[^/\s?#]+")
_SECRET_QUERY = re.compile(r"(?i)([?&](?:api_?key|key|token|access_token|secret)=)[^&\s#]+")
_AUTH_HEADER = re.compile(r"(?i)((?:bearer|basic)\s+)[A-Za-z0-9._~+/=-]+")
_API_HEADER = re.compile(r"(?i)((?:x-api-key|api-key)\s*:\s*)[^\s,]+")


def redact(text: str) -> str:
    """Mask credentials that appear in URLs or headers inside ``text``."""
    redacted = _API_KEY_PATH.sub(r"\1***", text)
    redacted = _SECRET_QUERY.sub(r"\1***", redacted)
    redacted = _AUTH_HEADER.sub(r"\1***", redacted)
    return _API_HEADER.sub(r"\1***", redacted)


def redact_traceback(exc: BaseException) -> str:
    """Render an exception and its traceback with credentials masked."""
    return redact("".join(traceback.format_exception(exc)))
