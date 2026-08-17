"""Shared safety gate and CLI harness for destructive Splunk Cloud tests.

Nested under `tests/integration/cloud/`, so `_require_cloud_target` (that
package's `conftest.py`) already gates `SPLUNK_ACS_LIVE_TEST`, a Cloud
`SPLUNK_URL`, and `SPLUNK_ACS_TOKEN` before any test here runs. This file adds
the write-specific opt-in on top, mirroring
`tests/integration/enterprise/write/conftest.py`.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

import pytest
from click.testing import CliRunner, Result

from vct_splunk.cli import cli

#: Groups every name this test run creates, so a stale object from another run
#: (or one still mid-async-delete) is never mistaken for one of this run's own.
RUN_ID = os.environ.get("GITHUB_RUN_ID") or uuid.uuid4().hex[:8]


def unique_name(prefix: str) -> str:
    """A `vct_ci_<run>_<prefix>_<random>` name unique to this test run."""
    return f"vct_ci_{RUN_ID}_{prefix}_{uuid.uuid4().hex[:8]}"


@pytest.fixture(autouse=True)
def _require_cloud_write_opt_in() -> None:
    if os.environ.get("SPLUNK_CLOUD_WRITE") == "true":
        return
    message = "set SPLUNK_CLOUD_WRITE=true to run destructive Splunk Cloud tests"
    if os.environ.get("CI") == "true":
        pytest.fail(message, pytrace=False)
    pytest.skip(message)


@pytest.fixture(scope="session", autouse=True)
def _preflight_leftover_report() -> None:
    """List existing `vct_ci_*` objects before this run starts, without failing.

    ACS index and HEC-token deletes complete asynchronously, so an object from
    a run that finished (and whose own cleanup succeeded) moments ago can still
    be listed here. Asserting on that would be a false failure, so this is a
    report only. The enforceable guarantee is narrower and per-test: each test
    below polls its own delete to completion before returning, and
    `CloudCli.finish()` fails loudly if any registered reverse-cleanup command
    itself errors.
    """
    runner = CliRunner()
    for resource in ("index", "role", "hec-token"):
        result = runner.invoke(cli, [resource, "list", "--output", "json"])
        if result.exit_code != 0:
            continue
        payload = json.loads(result.stdout)
        leftover = [
            item.get("name")
            for item in payload.get("data", [])
            if isinstance(item, dict) and str(item.get("name", "")).startswith("vct_ci_")
        ]
        if leftover:
            print(f"[cloud write preflight] leftover {resource} objects: {leftover}")


@dataclass
class CloudCli:
    """Invoke the public CLI against Splunk Cloud and fail if reverse cleanup leaks state."""

    runner: CliRunner = field(default_factory=CliRunner)
    cleanups: list[tuple[str, Callable[[], Result]]] = field(default_factory=list)

    def run(self, *argv: str, exit_codes: tuple[int, ...] = (0,)) -> Any:
        result = self.runner.invoke(cli, [*argv, "--output", "json"])
        assert result.exit_code in exit_codes, (
            f"{' '.join(argv)} exited {result.exit_code}\n{result.output}"
        )
        payload = json.loads(result.stdout)
        if result.exit_code == 0:
            assert set(payload) == {"data", "meta"}
            return payload["data"]
        return payload["error"]

    def write(self, *argv: str) -> dict[str, Any]:
        return self.run(*argv, "--yes")

    def cleanup(self, label: str, *argv: str) -> None:
        self.cleanups.append(
            (label, lambda: self.runner.invoke(cli, [*argv, "--yes", "--output", "json"]))
        )

    def drop_cleanup(self, label: str) -> None:
        """Remove a previously registered cleanup, e.g. once a test's own delete succeeds."""
        self.cleanups = [c for c in self.cleanups if c[0] != label]

    def finish(self) -> None:
        failures: list[str] = []
        for label, cleanup in reversed(self.cleanups):
            result = cleanup()
            if result.exit_code != 0:
                failures.append(f"{label}: exit {result.exit_code}: {result.output}")
        assert not failures, "cleanup failures:\n" + "\n".join(failures)


@pytest.fixture
def cloud_cli() -> Iterator[CloudCli]:
    harness = CloudCli()
    try:
        yield harness
    finally:
        harness.finish()
