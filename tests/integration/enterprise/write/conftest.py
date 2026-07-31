"""Shared safety gate and CLI harness for destructive Enterprise tests."""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

import pytest
from click.testing import CliRunner, Result

from vct_splunk.cli import cli


@pytest.fixture(autouse=True)
def _require_write_opt_in() -> None:
    if os.environ.get("SPLUNK_WRITE_TEST") == "true":
        return
    message = "set SPLUNK_WRITE_TEST=true to run destructive Enterprise tests"
    if os.environ.get("CI") == "true":
        pytest.fail(message, pytrace=False)
    pytest.skip(message)


@dataclass
class EnterpriseCli:
    """Invoke the public CLI and fail explicitly if reverse cleanup leaks state."""

    runner: CliRunner = field(default_factory=CliRunner)
    cleanups: list[tuple[str, Callable[[], Result]]] = field(default_factory=list)

    def run(
        self,
        *argv: str,
        exit_codes: tuple[int, ...] = (0,),
    ) -> dict[str, Any]:
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
            (
                label,
                lambda: self.runner.invoke(cli, [*argv, "--yes", "--output", "json"]),
            )
        )

    def finish(self) -> None:
        failures: list[str] = []
        for label, cleanup in reversed(self.cleanups):
            result = cleanup()
            if result.exit_code != 0:
                failures.append(f"{label}: exit {result.exit_code}: {result.output}")
        assert not failures, "cleanup failures:\n" + "\n".join(failures)


@pytest.fixture
def enterprise_cli() -> Iterator[EnterpriseCli]:
    harness = EnterpriseCli()
    try:
        yield harness
    finally:
        harness.finish()
