"""Saved-search dispatch — the one saved-search operation the engine does not cover.

CRUD goes through the generic engine, which `test_resource_factory.py` proves
once for every spec. Dispatch is hand-written: it posts to a `/dispatch` suffix
and returns the search job id the caller polls.

Dispatch also carries the one write gate that is conditional rather than
absolute, so both sides of that condition are pinned here.
"""

from __future__ import annotations

import httpx
import pytest
from click.testing import CliRunner

from vct_splunk.cli import cli
from vct_splunk.core import saved_searches as ss

ARGV = ["saved-search", "run", "nightly", "--app", "my_app"]


def test_dispatch_returns_sid(client_for):
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"sid": "sid99"})

    result = ss.dispatch_saved_search(client_for(handler), "nightly", owner="-", app="-")
    assert result["sid"] == "sid99"
    assert result["dispatched"] is True


@pytest.fixture
def dispatching(monkeypatch: pytest.MonkeyPatch, client_for):
    """Record every request a dispatch sends, with a resolvable audit target."""
    requests: list[httpx.Request] = []
    monkeypatch.setenv("SPLUNK_URL", "https://sh.corp:8089")
    monkeypatch.setenv("SPLUNK_TOKEN", "T")

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"sid": "sid1"})

    monkeypatch.setattr("vct_splunk.commands.context.Ctx.client", lambda self: client_for(handler))
    return requests


def test_triggering_alert_actions_is_a_gated_write(dispatching) -> None:
    """Alert actions can email or run a script, so they need the write gate.

    Non-interactively the gate must stop the dispatch before it is sent, and
    `--yes` must let exactly one request through.
    """
    argv = [*ARGV, "--trigger-actions", "--output", "json"]

    refused = CliRunner().invoke(cli, argv)
    assert refused.exit_code == 2, refused.output
    assert dispatching == []

    allowed = CliRunner().invoke(cli, [*argv, "--yes"])
    assert allowed.exit_code == 0, allowed.output
    assert len(dispatching) == 1


def test_a_plain_dispatch_is_not_gated(dispatching) -> None:
    """Without alert actions a dispatch only creates a job, like `search run`."""
    result = CliRunner().invoke(cli, [*ARGV, "--output", "json"])

    assert result.exit_code == 0, result.output
    assert len(dispatching) == 1
