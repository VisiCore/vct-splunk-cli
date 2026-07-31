"""Shared gates for live Splunk Enterprise tests."""

from __future__ import annotations

import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def _require_enterprise_target() -> None:
    """Skip local opt-out runs, but fail a misconfigured CI job."""
    if os.environ.get("SPLUNK_INTEGRATION_TEST") != "true":
        pytest.skip("set SPLUNK_INTEGRATION_TEST=true to run Enterprise integration tests")

    if not os.environ.get("SPLUNK_URL"):
        pytest.fail("SPLUNK_URL is required for Enterprise integration tests", pytrace=False)

    has_token = bool(os.environ.get("SPLUNK_TOKEN") or os.environ.get("SPLUNK_SESSION_KEY"))
    has_password = bool(os.environ.get("SPLUNK_USERNAME") and os.environ.get("SPLUNK_PASSWORD"))
    if not (has_token or has_password):
        pytest.fail(
            "set SPLUNK_TOKEN, SPLUNK_SESSION_KEY, or SPLUNK_USERNAME plus SPLUNK_PASSWORD",
            pytrace=False,
        )
