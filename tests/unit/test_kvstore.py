"""Isolated unit tests for the `kvstore` command adapters (#9).

These drive the real command + core + client stack through ``CliRunner`` while
mocking only the HTTP transport, mirroring ``test_commands.py``. ``Ctx.client``
is patched to return a real ``SplunkClient`` backed by ``httpx.MockTransport``.
"""

from __future__ import annotations

import httpx
import pytest
from click.testing import CliRunner

from vct_splunk.cli import cli
from vct_splunk.core.client import ClientConfig, SplunkClient
from vct_splunk.core.errors import UsageError
from vct_splunk.core.kvstore import (
    delete_all,
    delete_record,
    get_record,
    insert_record,
    list_records,
    update_record,
)


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


def test_records_requires_app(monkeypatch):
    _env(monkeypatch)
    result = CliRunner().invoke(cli, ["kvstore", "records", "things", "--output", "json"])
    assert result.exit_code == 2
    assert "usage_error" in result.output


def test_records_uses_shared_owner_and_explicit_app(monkeypatch):
    _env(monkeypatch)
    seen: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["path"] = req.url.path
        return httpx.Response(200, json=[{"_key": "a", "x": 1}])

    _patch_client(monkeypatch, handler)
    result = CliRunner().invoke(
        cli, ["kvstore", "records", "things", "--app", "my_app", "--output", "json"]
    )
    assert result.exit_code == 0
    assert '"_key": "a"' in result.output
    assert seen["path"] == "/servicesNS/nobody/my_app/storage/collections/data/things"


def test_get_returns_one_record(monkeypatch):
    _env(monkeypatch)
    _patch_client(monkeypatch, lambda req: httpx.Response(200, json={"_key": "a", "x": 1}))
    result = CliRunner().invoke(
        cli, ["kvstore", "get", "things", "a", "--app", "my_app", "--output", "json"]
    )
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


@pytest.mark.parametrize("value", [".", "..", "a/b", "a\\b", "%2fetc", "%25252e%25252e", "a\nb"])
def test_rejected_collection_sends_no_request(monkeypatch, value):
    _env(monkeypatch)
    requests: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        requests.append(req)
        return httpx.Response(200, json=[])

    _patch_client(monkeypatch, handler)
    result = CliRunner().invoke(
        cli, ["kvstore", "records", value, "--app", "my_app", "--output", "json"]
    )
    assert result.exit_code == 2
    assert requests == []


def test_kvstore_exact_wire_contracts_and_encoding(client_for):
    seen: list[tuple[str, str, dict[str, str], bytes]] = []

    def handler(req: httpx.Request) -> httpx.Response:
        raw_path = req.url.raw_path.split(b"?", 1)[0].decode()
        seen.append((req.method, raw_path, dict(req.url.params), req.content))
        if req.method == "GET":
            record = {"_key": "a b"} if req.url.path.endswith("a b") else []
            return httpx.Response(200, json=record)
        return httpx.Response(200, json={"ok": True})

    client = client_for(handler)
    assert (
        list_records(client, "my things", owner="nobody", app="my app", query='{"x":1}', limit=3)
        == []
    )
    assert get_record(client, "my things", "a b", owner="nobody", app="my app") == {"_key": "a b"}
    assert insert_record(client, "my things", {"x": 1}, owner="nobody", app="my app") == {
        "ok": True
    }
    assert update_record(client, "my things", "a b", {"x": 2}, owner="nobody", app="my app") == {
        "ok": True
    }
    assert delete_record(client, "my things", "a b", owner="nobody", app="my app") == {"ok": True}
    assert delete_all(client, "my things", owner="nobody", app="my app") == {"ok": True}

    base = "/servicesNS/nobody/my%20app/storage/collections/data/my%20things"
    assert seen == [
        ("GET", base, {"query": '{"x":1}', "limit": "3", "output_mode": "json"}, b""),
        ("GET", f"{base}/a%20b", {"output_mode": "json"}, b""),
        ("POST", base, {}, b'{"x":1}'),
        ("POST", f"{base}/a%20b", {}, b'{"x":2}'),
        ("DELETE", f"{base}/a%20b", {"output_mode": "json"}, b""),
        ("DELETE", base, {"output_mode": "json"}, b""),
    ]


@pytest.mark.parametrize("value", ["..", "a/b", "a\\b", "%2e%2e", "%25252fetc", "\x00"])
def test_core_rejects_traversal_before_request(client_for, value):
    requests: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        requests.append(req)
        return httpx.Response(200, json=[])

    client = client_for(handler)
    with pytest.raises(UsageError):
        list_records(client, value, owner="nobody", app="my_app")
    with pytest.raises(UsageError):
        get_record(client, "things", value, owner="nobody", app="my_app")
    assert requests == []
