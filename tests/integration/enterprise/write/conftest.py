"""Shared safety gate for destructive Enterprise tests. Harness lives in write_test_cli."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from write_test_cli import WriteTestCli


@pytest.fixture(autouse=True)
def _require_write_opt_in() -> None:
    if os.environ.get("SPLUNK_WRITE_TEST") == "true":
        return
    message = "set SPLUNK_WRITE_TEST=true to run destructive Enterprise tests"
    if os.environ.get("CI") == "true":
        pytest.fail(message, pytrace=False)
    pytest.skip(message)


@pytest.fixture
def enterprise_cli() -> Iterator[WriteTestCli]:
    harness = WriteTestCli()
    try:
        yield harness
    finally:
        harness.finish()
