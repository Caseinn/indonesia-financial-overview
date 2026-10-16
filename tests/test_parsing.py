"""Tests for pipeline.parsing primitives."""

from __future__ import annotations

from datetime import date

import pytest

from pipeline.parsing import (
    ParseError,
    WorkbookFormat,
    clean_number,
    detect_workbook_format,
    parse_date,
    sha256_hex,
)


@pytest.mark.parametrize(
    ("blob", "expected"),
    [
        (b"\xd0\xcf\x11\xe0\xa1\xb1" + b"\x00" * 16, WorkbookFormat.XLS),
        (b"PK\x03\x04" + b"\x00" * 16, WorkbookFormat.XLSX),
        (b"<html><body><table></table></body></html>", WorkbookFormat.HTML),
        (b"  \xef\xbb\xbf<!DOCTYPE html><html></html>", WorkbookFormat.HTML),
        (b'<?xml version="1.0"?><Workbook></Workbook>', WorkbookFormat.XML),
        (b"\x89PNG\r\n", WorkbookFormat.UNKNOWN),
    ],
)
def test_detect_workbook_format(blob: bytes, expected: WorkbookFormat) -> None:
    assert detect_workbook_format(blob) is expected


def test_sha256_hex_matches_known_vector() -> None:
    assert sha256_hex(b"") == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1.234,56", 1234.56),
        ("1,234.56", 1234.56),
        ("1234.56", 1234.56),
        ("5,25", 5.25),
        ("1,234,567", 1234567.0),
        ("1.234.567", 1234567.0),
        ("  12,5  %", 12.5),
        ("Rp 1.000", 1000.0),
        ("(250)", -250.0),
        ("-3,5", -3.5),
    ],
)
def test_clean_number_valid(raw: str, expected: float) -> None:
    assert clean_number(raw) == pytest.approx(expected)


@pytest.mark.parametrize("raw", ["", "-", "--", "n/a", "–", None, "tidak ada"])
def test_clean_number_missing(raw: str | None) -> None:
    assert clean_number(raw) is None


@pytest.mark.parametrize("raw", ["abc", "12x3", "1,2,3.4.5"])
def test_clean_number_invalid_raises(raw: str) -> None:
    with pytest.raises(ParseError):
        clean_number(raw)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2022-07-01", date(2022, 7, 1)),
        ("15/10/2026", date(2026, 10, 15)),
        ("15-10-2026", date(2026, 10, 15)),
        ("1 Oktober 2022", date(2022, 10, 1)),
        ("October 1, 2022", date(2022, 10, 1)),
        ("10/15/2026", date(2026, 10, 15)),
    ],
)
def test_parse_date_valid(raw: str, expected: date) -> None:
    day_first = raw != "10/15/2026"
    assert parse_date(raw, day_first=day_first) == expected


def test_parse_date_with_time_suffix() -> None:
    assert parse_date("10/15/2026 12:00:00 AM", day_first=False) == date(2026, 10, 15)


@pytest.mark.parametrize("raw", ["", "-", None, "n/a"])
def test_parse_date_missing(raw: str | None) -> None:
    assert parse_date(raw) is None


@pytest.mark.parametrize("raw", ["31/13/2020", "not a date", "Oktober 2020"])
def test_parse_date_invalid_raises(raw: str) -> None:
    with pytest.raises(ParseError):
        parse_date(raw, day_first=False)
