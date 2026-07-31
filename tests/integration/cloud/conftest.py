"""Shared gates for live Splunk Cloud tests.

Mirrors `tests/integration/enterprise/conftest.py`: skip a local run that did
not opt in, but fail loudly when a run opts in and is misconfigured, so a broken
canary can never pass by silently skipping every test.
"""

from __future__ import annotations

import os

import pytest

from vct_splunk.core.backends import deduce_backend


@pytest.fixture(scope="session", autouse=True)
def _require_cloud_target() -> None:
    """Require the opt-in, a real Cloud URL, and an ACS token."""
    if os.environ.get("SPLUNK_ACS_LIVE_TEST") != "true":
        pytest.skip("set SPLUNK_ACS_LIVE_TEST=true to run Splunk Cloud integration tests")

    url = os.environ.get("SPLUNK_URL")
    if not url:
        pytest.fail("SPLUNK_URL is required for Splunk Cloud integration tests", pytrace=False)

    # The backend is deduced from the URL, never chosen, so a non-Cloud URL here
    # would quietly test Enterprise instead of what this suite claims to cover.
    if deduce_backend(url) != "cloud":
        pytest.fail(
            f"SPLUNK_URL={url!r} is not a Splunk Cloud host; "
            "expected something like https://<stack>.splunkcloud.com",
            pytrace=False,
        )

    if not os.environ.get("SPLUNK_ACS_TOKEN"):
        pytest.fail(
            "SPLUNK_ACS_TOKEN is required for Splunk Cloud integration tests",
            pytrace=False,
        )
