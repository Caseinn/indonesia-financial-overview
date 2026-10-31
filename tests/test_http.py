"""HTTP retry logging never echoes a credential from the URL."""

from __future__ import annotations

import logging

import pytest
import requests

from pipeline.http import request_with_retry
from pipeline.parsing import ParseError


def test_retry_redacts_url_credentials(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING)

    def boom() -> None:
        raise requests.ConnectionError(
            "failed https://webapi.bps.go.id/v1/api/list/model/data/domain/0000/"
            "var/1/th/1/key/SECRET123/"
        )

    with pytest.raises(ParseError):
        request_with_retry(
            boom,
            source_id="BPS",
            label="payload",
            attempts=2,
            backoff=0,
            sleep=lambda _: None,
        )

    assert "SECRET123" not in caplog.text
    assert "key/***/" in caplog.text
