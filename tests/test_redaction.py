"""Credential redaction for log lines and failure alerts."""

from __future__ import annotations

from pipeline.redaction import redact, redact_traceback


def test_redacts_bps_key_in_path() -> None:
    text = (
        "GET https://webapi.bps.go.id/v1/api/list/model/data/domain/0000/var/1/th/1/key/SECRET123/"
    )
    assert redact(text) == (
        "GET https://webapi.bps.go.id/v1/api/list/model/data/domain/0000/var/1/th/1/key/***/"
    )


def test_redacts_key_without_trailing_slash() -> None:
    assert redact("https://example.test/key/SECRET123") == "https://example.test/key/***"


def test_redacts_query_credentials() -> None:
    redacted = redact("https://example.test/data?token=SECRET&page=1")

    assert "SECRET" not in redacted
    assert "token=***" in redacted


def test_redacts_authorization_headers() -> None:
    redacted = redact("Authorization: Bearer abc.def.ghi\nX-Api-Key: SECRET")

    assert "abc.def.ghi" not in redacted
    assert "SECRET" not in redacted


def test_redacts_traceback() -> None:
    try:
        raise RuntimeError("https://example.test/key/SECRET123/")
    except RuntimeError as exc:
        text = redact_traceback(exc)

    assert "SECRET123" not in text
    assert "RuntimeError" in text


def test_leaves_ordinary_urls_alone() -> None:
    text = "https://www.bi.go.id/id/statistik/informasi-kurs/jisdor/"

    assert redact(text) == text
