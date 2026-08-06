from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from click.testing import CliRunner

from vct_splunk.core.client import ClientConfig, SplunkClient

_TEST_URL = "https://splunk.test:8089"


def cli_runner() -> CliRunner:
    """Return a ``CliRunner`` that captures stderr separately on every Click.

    Click below 8.2 folds stderr into stdout unless asked not to, so reading
    ``result.stderr`` raises. Click 8.2 removed the parameter and always
    separates. Ask for separation only when the installed Click still takes
    the parameter. Only tests that assert on stderr need this.
    """
    kwargs: dict[str, Any] = {}
    if "mix_stderr" in inspect.signature(CliRunner.__init__).parameters:
        kwargs["mix_stderr"] = False
    return CliRunner(**kwargs)


def make_client(handler: Callable, *, dry_run: bool = False) -> SplunkClient:
    cfg = ClientConfig(base_url=_TEST_URL, token="TESTTOKEN", dry_run=dry_run)
    return SplunkClient(cfg, transport=httpx.MockTransport(handler))


@pytest.fixture
def client_for() -> Callable:
    """Return a factory ``client_for(handler, dry_run=...)`` that builds a
    SplunkClient backed by a mocked HTTP transport."""
    return make_client


@pytest.fixture
def cli_env(monkeypatch):
    """Point the CLI at a test Splunk and clear ambient vars that change behavior."""
    monkeypatch.setenv("SPLUNK_URL", _TEST_URL)
    monkeypatch.setenv("SPLUNK_TOKEN", "T")
    for var in (
        "SPLUNK_APP",
        "SPLUNK_OWNER",
        "SPLUNK_USER_PASSWORD",
        "SPLUNK_SESSION_KEY",
        "SPLUNK_USERNAME",
        "SPLUNK_PASSWORD",
        "SPLUNK_PROFILE",
        "VCT_SPLUNK_CONFIG",
    ):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def patch_client(monkeypatch) -> Callable:
    """Return ``patch_client(handler)``: route the CLI's HTTP through a mock.

    Patches ``Ctx.client`` so commands driven by ``CliRunner`` build a real
    ``SplunkClient`` (dry-run flag intact) over ``httpx.MockTransport``.
    """

    def _patch(handler: Callable) -> None:
        def make(self):
            cfg = ClientConfig(base_url=_TEST_URL, token="T", dry_run=self.dry_run)
            return SplunkClient(cfg, transport=httpx.MockTransport(handler))

        monkeypatch.setattr("vct_splunk.commands.context.Ctx.client", make)

    return _patch
