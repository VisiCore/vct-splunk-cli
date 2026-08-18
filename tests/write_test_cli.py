"""Shared CLI harness for destructive integration suites (Enterprise + Cloud).

Both suites need the same three operations: invoke the CLI and assert on its
JSON envelope, invoke it as a real write (``--yes``), and register a
reverse-cleanup command that runs (in reverse order) when the test finishes,
failing loudly if any of those cleanups itself errors. Only the *opt-in* gate
differs per suite (``SPLUNK_WRITE_TEST`` vs ``SPLUNK_CLOUD_WRITE``), so each
keeps its own autouse fixture in its own ``conftest.py``; this module holds
only what is identical between them.

A flat top-level module rather than a nested ``tests/integration/conftest.py``:
this test suite has no ``__init__.py`` packages (see ``pythonpath = ["tests"]``
in ``pyproject.toml``), so a shared helper is imported the same way
``cli_catalog.py`` already is -- ``from write_test_cli import WriteTestCli``.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from click.testing import CliRunner, Result

from vct_splunk.cli import cli


@dataclass
class WriteTestCli:
    """Invoke the public CLI and fail explicitly if reverse cleanup leaks state."""

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
