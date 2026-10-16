"""Reusable parsing primitives shared by every adapter.

Government portals serve data in inconsistent shapes, so the format sniffing,
Indonesian-locale number cleaning, date parsing, and checksum hashing live here
once instead of being copy-pasted. Primitives return ``None`` for an explicit
missing marker and raise ``ParseError`` for genuinely malformed input, so drift
is never imported silently.
"""

from __future__ import annotations

import calendar
import hashlib
import re
from datetime import date
from enum import StrEnum


class ParseError(ValueError):
    """Raised when a value cannot be parsed as the expected type."""


class WorkbookFormat(StrEnum):
    """Physical format of a downloaded workbook, decided by magic bytes."""

    XLS = "xls"
    XLSX = "xlsx"
    HTML = "html"
    XML = "xml"
    UNKNOWN = "unknown"


_MISSING_MARKERS = frozenset(
    {"", "-", "--", "–", "—", "n/a", "na", "null", "none", "n.a.", "tidak ada"}
)

_XLS_MAGIC = b"\xd0\xcf\x11\xe0"
_XLSX_MAGIC = b"PK\x03\x04"

_MONTHS = {
    "januari": 1,
    "jan": 1,
    "january": 1,
    "februari": 2,
    "feb": 2,
    "february": 2,
    "maret": 3,
    "mar": 3,
    "march": 3,
    "april": 4,
    "apr": 4,
    "mei": 5,
    "may": 5,
    "juni": 6,
    "jun": 6,
    "june": 6,
    "juli": 7,
    "jul": 7,
    "july": 7,
    "agustus": 8,
    "agu": 8,
    "aug": 8,
    "august": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "oktober": 10,
    "okt": 10,
    "oct": 10,
    "october": 10,
    "november": 11,
    "nov": 11,
    "desember": 12,
    "des": 12,
    "dec": 12,
    "december": 12,
}


def sha256_hex(blob: bytes) -> str:
    """Return the hex SHA-256 of raw bytes, the pipeline's lineage key."""
    return hashlib.sha256(blob).hexdigest()


def detect_workbook_format(blob: bytes) -> WorkbookFormat:
    """Identify a payload by magic bytes, never by file extension.

    Returns ``XLS`` for OLE2 (BIFF), ``XLSX`` for ZIP, ``HTML`` or ``XML`` for
    markup a portal served with a spreadsheet filename, else ``UNKNOWN``.
    """
    if blob.startswith(_XLS_MAGIC):
        return WorkbookFormat.XLS
    if blob.startswith(_XLSX_MAGIC):
        return WorkbookFormat.XLSX
    head = blob[:4096].lstrip(b"\xef\xbb\xbf").lstrip().lower()
    if head.startswith(b"<html") or b"<!doctype html" in head or b"<table" in head:
        return WorkbookFormat.HTML
    if head.startswith(b"<?xml") or b"<workbook" in head:
        return WorkbookFormat.XML
    return WorkbookFormat.UNKNOWN


def clean_number(raw: str | None) -> float | None:
    """Parse a numeric cell into a float, tolerating Indonesian conventions.

    Handles thousands/decimal separators in either order, footnote dots for
    missing values, parenthesised negatives, and currency or percent suffixes.
    Returns ``None`` for an explicit missing marker and raises ``ParseError``
    when non-numeric text remains.
    """
    if raw is None:
        return None
    text = raw.replace("\u00a0", " ").strip()
    if text.lower() in _MISSING_MARKERS:
        return None
    text = text.replace(" ", "")

    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1].strip()
    for token in ("Rp", "IDR", "%", "percent", "persen"):
        text = text.replace(token, "")
    text = text.strip()
    if text.lower() in _MISSING_MARKERS:
        return None

    text = text.removeprefix("+")
    if text.startswith(("-", "\u2212")):
        negative = not negative
        text = text.lstrip("-\u2212")
    if not text:
        return None

    text = _normalize_separators(text)
    try:
        value = float(text)
    except ValueError as exc:
        raise ParseError(f"not a number: {raw!r}") from exc
    return -value if negative else value


def _normalize_separators(text: str) -> str:
    """Collapse grouping separators and leave the last one as the decimal point.

    Both ``1.234,56`` and ``1,234.56`` reduce to ``1234.56``. A lone comma is a
    decimal point, and a lone dot of the form ``1.000`` is Indonesian grouping,
    matching government tables.
    """
    has_dot = "." in text
    has_comma = "," in text
    if has_dot and has_comma:
        if text.rfind(",") > text.rfind("."):
            return text.replace(".", "").replace(",", ".")
        return text.replace(",", "")
    if text.count(",") > 1:
        return text.replace(",", "")
    if text.count(".") > 1:
        return text.replace(".", "")
    if "." in text:
        before, _, after = text.partition(".")
        if before.isdigit() and 1 <= len(before) <= 3 and len(after) == 3:
            return before + after
        return text
    return text.replace(",", ".")


def parse_date(raw: str | None, *, day_first: bool = True) -> date | None:
    """Parse an ISO, numeric, or month-name date, tolerating Indonesian names.

    ``day_first`` resolves ambiguous numeric dates: Indonesian sources use
    day-first (``15/10/2026``) while the JISDOR export is month-first
    (``10/15/2026``). Returns ``None`` for a missing marker.
    """
    if raw is None:
        return None
    text = raw.strip()
    if text.lower() in _MISSING_MARKERS:
        return None
    text = re.sub(r"\s\d{1,2}:\d{2}(?::\d{2})?\s*(?:[AaPp][Mm])?$", "", text).strip()

    iso = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", text)
    if iso:
        year, month, day = (int(part) for part in iso.groups())
        return _make_date(year, month, day, raw)

    named = re.fullmatch(r"(\d{1,2})[\s-]*([A-Za-z]+)[\s,-]*(\d{4})", text)
    if named:
        month = _lookup_month(named.group(2), raw)
        return _make_date(int(named.group(3)), month, int(named.group(1)), raw)

    named_us = re.fullmatch(r"([A-Za-z]+)[\s-]*(\d{1,2}),?[\s-]*(\d{4})", text)
    if named_us:
        month = _lookup_month(named_us.group(1), raw)
        return _make_date(int(named_us.group(3)), month, int(named_us.group(2)), raw)

    parts = re.split(r"[/.\-]", text)
    if len(parts) == 3 and all(part.isdigit() for part in parts):
        first, second, third = (int(part) for part in parts)
        if len(parts[0]) == 4:
            return _make_date(first, second, third, raw)
        day, month = (first, second) if day_first else (second, first)
        return _make_date(third, month, day, raw)

    raise ParseError(f"not a date: {raw!r}")


def _make_date(year: int, month: int, day: int, raw: str | None) -> date:
    try:
        return date(year, month, day)
    except ValueError as exc:
        raise ParseError(f"not a date: {raw!r}") from exc


def _lookup_month(name: str, raw: str | None) -> int:
    try:
        return _MONTHS[name.lower()]
    except KeyError as exc:
        raise ParseError(f"unknown month name in {raw!r}") from exc


def month_number(name: str | None) -> int | None:
    """Return the 1-12 month for an English or Indonesian name or abbreviation.

    Shared so adapters reading month headers (``Jan``/``Januari``) or BPS labels
    (``Januari``) do not each carry their own table. Returns ``None`` when the
    text is not a month name.
    """
    if name is None:
        return None
    return _MONTHS.get(name.strip().lower())


def month_end(year: int, month: int) -> date:
    """Return the last calendar day of ``month`` in ``year``."""
    return date(year, month, calendar.monthrange(year, month)[1])
