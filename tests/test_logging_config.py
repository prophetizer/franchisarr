"""Logging must be leveled, timestamped, on stdout -- and must never emit a secret."""

from __future__ import annotations

import logging

import pytest

from app.logging_config import (
    REDACTED,
    clear_secrets,
    configure_logging,
    mask_secret,
    redact,
    register_secret,
)


@pytest.fixture(autouse=True)
def _clean_secret_registry():
    clear_secrets()
    yield
    clear_secrets()


def _capture(capsys) -> str:
    return capsys.readouterr().out


def test_logs_go_to_stdout_with_level_and_timestamp(capsys) -> None:
    configure_logging("INFO")
    logging.getLogger("app.test").info("scan finished")

    out = _capture(capsys)
    assert "INFO" in out
    assert "app.test" in out
    assert "scan finished" in out
    # ISO-8601 UTC, e.g. 2026-08-29T17:00:00.000Z
    assert out.split(" ", 1)[0].endswith("Z")


def test_log_level_is_honoured(capsys) -> None:
    configure_logging("WARNING")
    logging.getLogger("app.test").info("should not appear")
    logging.getLogger("app.test").warning("should appear")

    out = _capture(capsys)
    assert "should not appear" not in out
    assert "should appear" in out


def test_unknown_log_level_falls_back_to_info(capsys) -> None:
    configure_logging("NONSENSE")
    logging.getLogger("app.test").info("still logged")

    assert "still logged" in _capture(capsys)


def test_configure_logging_is_idempotent(capsys) -> None:
    configure_logging("INFO")
    configure_logging("INFO")
    logging.getLogger("app.test").info("once only")

    assert _capture(capsys).count("once only") == 1


def test_registered_secret_is_redacted_in_message(capsys) -> None:
    configure_logging("INFO")
    register_secret("super-secret-api-key")

    logging.getLogger("app.test").info("calling radarr with super-secret-api-key")

    out = _capture(capsys)
    assert "super-secret-api-key" not in out
    assert REDACTED in out


def test_registered_secret_is_redacted_in_args(capsys) -> None:
    configure_logging("INFO")
    register_secret("super-secret-api-key")

    logging.getLogger("app.test").info("url=%s", "http://radarr/api?apikey=super-secret-api-key")

    out = _capture(capsys)
    assert "super-secret-api-key" not in out


def test_registered_secret_is_redacted_in_tracebacks(capsys) -> None:
    """The case our own code can't prevent: a library putting the token in an exception."""
    configure_logging("INFO")
    register_secret("super-secret-api-key")

    try:
        raise ValueError("bad token: super-secret-api-key")
    except ValueError:
        logging.getLogger("app.test").exception("request failed")

    out = _capture(capsys)
    assert "super-secret-api-key" not in out


def test_very_short_values_are_not_registered(capsys) -> None:
    """A two-character 'secret' would match everywhere and destroy the logs."""
    configure_logging("INFO")
    register_secret("ab")

    logging.getLogger("app.test").info("about to scan")

    assert "about to scan" in _capture(capsys)


def test_register_secret_ignores_empty_values() -> None:
    register_secret(None)
    register_secret("")
    assert redact("nothing to do here") == "nothing to do here"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("abcdef123456", "••••••••3456"),
        ("abcd", "••••"),
        ("", ""),
        (None, ""),
    ],
)
def test_mask_secret(value: str | None, expected: str) -> None:
    assert mask_secret(value) == expected
