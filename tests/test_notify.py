"""Webhook alerts stay best-effort and never log the secret URL."""

from __future__ import annotations

import logging

import pytest
import requests

from pipeline import notify


class FailingSession:
    """Raise a connection error without touching the network."""

    def post(self, url: str, json: dict[str, object], timeout: float) -> None:
        raise requests.ConnectionError(f"failed to connect to {url}")


class OkResponse:
    """Minimal successful response returned by :class:`OkSession`."""

    status_code = 204

    def raise_for_status(self) -> None:
        return None


class OkSession:
    """Return a successful response without touching the network."""

    def post(self, url: str, json: dict[str, object], timeout: float) -> OkResponse:
        return OkResponse()


def test_send_without_a_url_is_a_noop() -> None:
    assert notify.send(None, {}) is False


def test_send_returns_true_on_success() -> None:
    assert notify.send("https://example.test/hook", {}, session=OkSession()) is True


def test_failure_does_not_log_the_webhook_url(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING)
    secret = "https://hooks.slack.com/services/SECRET/TOKEN"

    assert notify.send(secret, {}, session=FailingSession()) is False

    assert "SECRET" not in caplog.text
    assert "ConnectionError" in caplog.text
