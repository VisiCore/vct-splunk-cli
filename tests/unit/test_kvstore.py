"""Isolated unit tests for the `kvstore` command adapters (#9).

These drive the real command + core + client stack through ``CliRunner`` while
mocking only the HTTP transport, mirroring ``test_commands.py``. ``Ctx.client``
is patched to return a real ``SplunkClient`` backed by ``httpx.MockTransport``.
"""

from __future__ import annotations

import httpx
from click.testing import CliRunner

from vct_splunk.cli import cli
from vct_splunk.core.client import ClientConfig, SplunkClient


def _env(monkeypatch):
    monkeypatch.setenv("SPLUNK_URL", "https://splunk.test:8089")
    monkeypatch.setenv("SPLUNK_TOKEN", "T")
    # Keep namespace resolution deterministic regardless of the host environment.
    monkeypatch.delenv("SPLUNK_APP", raising=False)
    monkeypatch.delenv("SPLUNK_OWNER", raising=False)


def _patch_client(monkeypatch, handler):
    def make(self):
        cfg = ClientConfig(base_url="https://splunk.test:8089", token="T", dry_run=self.dry_run)
        return SplunkClient(cfg, transport=httpx.MockTransport(handler))

    monkeypatch.setattr("vct_splunk.commands.context.Ctx.client", make)


def test_records_lists_with_read_wildcard_namespace(monkeypatch):
    _env(monkeypatch)
    seen: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["path"] = req.url.path
        return httpx.Response(200, json=[{"_key": "a", "x": 1}])

    _patch_client(monkeypatch, handler)
    result = CliRunner().invoke(cli, ["kvstore", "records", "things", "--output", "json"])
    assert result.exit_code == 0
    assert '"_key": "a"' in result.output
    assert seen["path"] == "/servicesNS/-/-/storage/collections/data/things"


def test_get_returns_one_record(monkeypatch):
    _env(monkeypatch)
    _patch_client(monkeypatch, lambda req: httpx.Response(200, json={"_key": "a", "x": 1}))
    result = CliRunner().invoke(cli, ["kvstore", "get", "things", "a", "--output", "json"])
    assert result.exit_code == 0
    assert '"_key": "a"' in result.output


def test_insert_requires_app(monkeypatch):
    _env(monkeypatch)
    # No --app and no SPLUNK_APP -> the write must refuse (exit 2) before any
    # network call, so no client patch is needed; it must never target 'search'.
    result = CliRunner().invoke(
        cli, ["kvstore", "insert", "things", "--data", '{"x":1}', "--output", "json"]
    )
    assert result.exit_code == 2
    assert "usage_error" in result.output


def test_insert_dry_run_previews_app_namespace(monkeypatch):
    _env(monkeypatch)
    result = CliRunner().invoke(
        cli,
        [
            "kvstore",
            "insert",
            "things",
            "--data",
            '{"x":1}',
            "--app",
            "my_app",
            "--dry-run",
            "--output",
            "json",
        ],
    )
    assert result.exit_code == 0
    assert '"dry_run": true' in result.output
    assert "/servicesNS/nobody/my_app/storage/collections/data/things" in result.output


def test_insert_rejects_bad_json(monkeypatch):
    _env(monkeypatch)
    result = CliRunner().invoke(
        cli,
        [
            "kvstore",
            "insert",
            "things",
            "--data",
            "not json",
            "--app",
            "my_app",
            "--output",
            "json",
        ],
    )
    assert result.exit_code == 2
    assert "usage_error" in result.output
