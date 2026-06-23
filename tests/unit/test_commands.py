"""Isolated unit tests for the Click command adapters (#20).

These drive the real command + core + client stack through ``CliRunner`` while
mocking only the HTTP transport, so each adapter is exercised without a live
Splunk instance. ``Ctx.client`` is patched to return a real ``SplunkClient``
backed by ``httpx.MockTransport``.
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


def test_server_info_renders(monkeypatch):
    _env(monkeypatch)
    _patch_client(
        monkeypatch,
        lambda req: httpx.Response(
            200, json={"entry": [{"content": {"serverName": "sh1", "version": "9.4.1"}}]}
        ),
    )
    result = CliRunner().invoke(cli, ["server", "info", "--output", "json"])
    assert result.exit_code == 0
    assert '"version": "9.4.1"' in result.output


def test_index_list_renders(monkeypatch):
    _env(monkeypatch)
    _patch_client(
        monkeypatch,
        lambda req: httpx.Response(
            200,
            json={
                "entry": [{"name": "main", "content": {"totalEventCount": "5"}}],
                "paging": {"total": 1},
            },
        ),
    )
    result = CliRunner().invoke(cli, ["index", "list", "--output", "json"])
    assert result.exit_code == 0
    assert '"name": "main"' in result.output


def test_index_get_renders(monkeypatch):
    _env(monkeypatch)
    _patch_client(
        monkeypatch,
        lambda req: httpx.Response(200, json={"entry": [{"name": "main", "content": {}}]}),
    )
    result = CliRunner().invoke(cli, ["index", "get", "main", "--output", "json"])
    assert result.exit_code == 0
    assert '"name": "main"' in result.output


def test_api_get_accepts_namespaced_path(monkeypatch):
    _env(monkeypatch)
    seen: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["path"] = req.url.path
        return httpx.Response(200, json={"entry": []})

    _patch_client(monkeypatch, handler)
    result = CliRunner().invoke(
        cli, ["api", "get", "/servicesNS/nobody/search/saved/searches", "--output", "json"]
    )
    assert result.exit_code == 0
    assert seen["path"] == "/servicesNS/nobody/search/saved/searches"


def test_search_run_executes(monkeypatch):
    _env(monkeypatch)
    _patch_client(monkeypatch, lambda req: httpx.Response(200, json={"results": [{"x": "1"}]}))
    result = CliRunner().invoke(
        cli, ["search", "run", "--query", "index=_internal", "--output", "json"]
    )
    assert result.exit_code == 0
    assert '"count": 1' in result.output


def test_health_check_exits_nonzero_on_fail(monkeypatch):
    _env(monkeypatch)

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/services/server/info":
            return httpx.Response(
                200, json={"entry": [{"content": {"version": "9.4", "serverName": "sh"}}]}
            )
        return httpx.Response(200, json={"entry": [{"content": {"health": "red", "features": {}}}]})

    _patch_client(monkeypatch, handler)
    result = CliRunner().invoke(cli, ["health", "check", "--output", "json"])
    assert result.exit_code == 1
    assert '"finding": "fail"' in result.output


def test_command_maps_auth_error_to_exit_3(monkeypatch):
    _env(monkeypatch)
    _patch_client(monkeypatch, lambda req: httpx.Response(401, json={}))
    result = CliRunner().invoke(cli, ["server", "info", "--output", "json"])
    assert result.exit_code == 3
    assert "auth_error" in result.output


def test_search_list_renders(monkeypatch):
    _env(monkeypatch)

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "entry": [{"name": "sid1", "content": {"dispatchState": "DONE"}, "acl": {}}],
                "paging": {"total": 1},
            },
        )

    _patch_client(monkeypatch, handler)
    result = CliRunner().invoke(cli, ["search", "list", "--output", "json"])
    assert result.exit_code == 0
    assert '"sid": "sid1"' in result.output


def test_search_cancel_refuses_without_yes_noninteractive(monkeypatch):
    _env(monkeypatch)
    # Must refuse before any network call, so no client patch is needed.
    result = CliRunner().invoke(cli, ["search", "cancel", "sid1", "--output", "json"])
    assert result.exit_code == 2
    assert "usage_error" in result.output


def test_saved_search_create_requires_app(monkeypatch):
    _env(monkeypatch)
    # No --app and no SPLUNK_APP -> the write must refuse (exit 2), not target 'search'.
    result = CliRunner().invoke(
        cli,
        [
            "saved-search",
            "create",
            "nightly",
            "--search",
            "index=main",
            "--dry-run",
            "--output",
            "json",
        ],
    )
    assert result.exit_code == 2
    assert "usage_error" in result.output


def test_saved_search_create_dry_run_previews_app_namespace(monkeypatch):
    _env(monkeypatch)
    result = CliRunner().invoke(
        cli,
        [
            "saved-search",
            "create",
            "nightly",
            "--search",
            "index=main",
            "--app",
            "my_app",
            "--dry-run",
            "--output",
            "json",
        ],
    )
    assert result.exit_code == 0
    assert '"dry_run": true' in result.output
    assert "/servicesNS/nobody/my_app/saved/searches" in result.output


def test_cluster_status_renders(monkeypatch):
    _env(monkeypatch)

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/services/cluster/config":
            return httpx.Response(200, json={"entry": [{"content": {"mode": "manager"}}]})
        return httpx.Response(200, json={"entry": [{"content": {"indexing_ready_flag": True}}]})

    _patch_client(monkeypatch, handler)
    result = CliRunner().invoke(cli, ["cluster", "status", "--output", "json"])
    assert result.exit_code == 0
    assert '"mode": "manager"' in result.output


def test_license_list_renders(monkeypatch):
    _env(monkeypatch)
    _patch_client(
        monkeypatch,
        lambda req: httpx.Response(
            200,
            json={
                "entry": [{"name": "lic1", "content": {"label": "Enterprise"}}],
                "paging": {"total": 1},
            },
        ),
    )
    result = CliRunner().invoke(cli, ["license", "list", "--output", "json"])
    assert result.exit_code == 0
    assert '"name": "lic1"' in result.output


def test_message_list_renders(monkeypatch):
    _env(monkeypatch)
    _patch_client(
        monkeypatch,
        lambda req: httpx.Response(
            200,
            json={
                "entry": [{"name": "restart_required", "content": {"value": "Restart needed"}}],
                "paging": {"total": 1},
            },
        ),
    )
    result = CliRunner().invoke(cli, ["message", "list", "--output", "json"])
    assert result.exit_code == 0
    assert '"name": "restart_required"' in result.output


def test_server_settings_get_renders(monkeypatch):
    _env(monkeypatch)
    _patch_client(
        monkeypatch,
        lambda req: httpx.Response(
            200, json={"entry": [{"content": {"serverName": "sh1", "host": "sh1"}}]}
        ),
    )
    result = CliRunner().invoke(cli, ["server", "settings", "get", "--output", "json"])
    assert result.exit_code == 0
    assert '"serverName": "sh1"' in result.output


def test_server_restart_refuses_without_yes_noninteractive(monkeypatch):
    _env(monkeypatch)
    # Must refuse before any network call, so no client patch is needed.
    result = CliRunner().invoke(cli, ["server", "restart", "--output", "json"])
    assert result.exit_code == 2
    assert "usage_error" in result.output


def test_server_restart_dry_run_previews(monkeypatch):
    _env(monkeypatch)

    def handler(req: httpx.Request) -> httpx.Response:
        raise AssertionError("dry-run must not send a request")

    _patch_client(monkeypatch, handler)
    result = CliRunner().invoke(cli, ["server", "restart", "--dry-run", "--output", "json"])
    assert result.exit_code == 0
    assert '"dry_run": true' in result.output


def test_server_settings_set_dry_run_previews(monkeypatch):
    _env(monkeypatch)

    def handler(req: httpx.Request) -> httpx.Response:
        raise AssertionError("dry-run must not send a request")

    _patch_client(monkeypatch, handler)
    result = CliRunner().invoke(
        cli,
        ["server", "settings", "set", "--set", "host=sh1", "--dry-run", "--output", "json"],
    )
    assert result.exit_code == 0
    assert '"dry_run": true' in result.output


def test_app_install_requires_one_source(monkeypatch):
    _env(monkeypatch)
    # Neither --file nor --url: usage error before any network call.
    result = CliRunner().invoke(cli, ["app", "install", "--output", "json"])
    assert result.exit_code == 2
    assert "usage_error" in result.output


def test_app_install_url_dry_run_previews(monkeypatch):
    _env(monkeypatch)

    def handler(req: httpx.Request) -> httpx.Response:
        raise AssertionError("dry-run must not send a request")

    _patch_client(monkeypatch, handler)
    result = CliRunner().invoke(
        cli, ["app", "install", "--url", "https://x/app.spl", "--dry-run", "--output", "json"]
    )
    assert result.exit_code == 0
    assert '"dry_run": true' in result.output


def test_deploy_client_list_renders(monkeypatch):
    _env(monkeypatch)
    _patch_client(
        monkeypatch,
        lambda req: httpx.Response(
            200,
            json={
                "entry": [{"name": "client1", "content": {"hostname": "fwd1"}}],
                "paging": {"total": 1},
            },
        ),
    )
    result = CliRunner().invoke(cli, ["deploy", "client", "list", "--output", "json"])
    assert result.exit_code == 0
    assert '"name": "client1"' in result.output


def test_deploy_serverclass_list_renders(monkeypatch):
    _env(monkeypatch)
    _patch_client(
        monkeypatch,
        lambda req: httpx.Response(
            200,
            json={
                "entry": [{"name": "sc1", "content": {"whitelist.0": "*"}}],
                "paging": {"total": 1},
            },
        ),
    )
    result = CliRunner().invoke(cli, ["deploy", "serverclass", "list", "--output", "json"])
    assert result.exit_code == 0
    assert '"name": "sc1"' in result.output


def test_deploy_reload_refuses_without_yes_noninteractive(monkeypatch):
    _env(monkeypatch)
    # Must refuse before any network call, so no client patch is needed.
    result = CliRunner().invoke(cli, ["deploy", "reload", "--output", "json"])
    assert result.exit_code == 2
    assert "usage_error" in result.output


def test_deploy_reload_dry_run_previews(monkeypatch):
    _env(monkeypatch)

    def handler(req: httpx.Request) -> httpx.Response:
        raise AssertionError("dry-run must not send a request")

    _patch_client(monkeypatch, handler)
    result = CliRunner().invoke(cli, ["deploy", "reload", "--dry-run", "--output", "json"])
    assert result.exit_code == 0
    assert '"dry_run": true' in result.output


def test_deploy_serverclass_create_dry_run_previews(monkeypatch):
    _env(monkeypatch)

    def handler(req: httpx.Request) -> httpx.Response:
        raise AssertionError("dry-run must not send a request")

    _patch_client(monkeypatch, handler)
    result = CliRunner().invoke(
        cli,
        ["deploy", "serverclass", "create", "foo", "--set", "x=1", "--dry-run", "--output", "json"],
    )
    assert result.exit_code == 0
    assert '"dry_run": true' in result.output


def test_hec_global_enable_refuses_without_yes_noninteractive(monkeypatch):
    _env(monkeypatch)
    # Must refuse before any network call, so no client patch is needed.
    result = CliRunner().invoke(cli, ["hec", "global-enable", "--output", "json"])
    assert result.exit_code == 2
    assert "usage_error" in result.output


def test_hec_global_enable_dry_run_previews(monkeypatch):
    _env(monkeypatch)

    def handler(req: httpx.Request) -> httpx.Response:
        raise AssertionError("dry-run must not send a request")

    _patch_client(monkeypatch, handler)
    result = CliRunner().invoke(cli, ["hec", "global-enable", "--dry-run", "--output", "json"])
    assert result.exit_code == 0
    assert '"dry_run": true' in result.output


def test_hec_rotate_dry_run_previews(monkeypatch):
    _env(monkeypatch)

    def handler(req: httpx.Request) -> httpx.Response:
        raise AssertionError("dry-run must not send a request")

    _patch_client(monkeypatch, handler)
    result = CliRunner().invoke(cli, ["hec", "rotate", "tok1", "--dry-run", "--output", "json"])
    assert result.exit_code == 0
    assert '"dry_run": true' in result.output


def test_datamodel_list_renders(monkeypatch):
    _env(monkeypatch)
    _patch_client(
        monkeypatch,
        lambda req: httpx.Response(
            200,
            json={
                "entry": [{"name": "Authentication", "content": {}, "acl": {}}],
                "paging": {"total": 1},
            },
        ),
    )
    result = CliRunner().invoke(cli, ["datamodel", "list", "--output", "json"])
    assert result.exit_code == 0
    assert '"name": "Authentication"' in result.output


def test_tag_list_renders(monkeypatch):
    _env(monkeypatch)
    _patch_client(
        monkeypatch,
        lambda req: httpx.Response(
            200,
            json={
                "entry": [{"name": "important", "content": {}, "acl": {}}],
                "paging": {"total": 1},
            },
        ),
    )
    result = CliRunner().invoke(cli, ["tag", "list", "--output", "json"])
    assert result.exit_code == 0
    assert '"name": "important"' in result.output


def test_datamodel_accelerate_dry_run_previews(monkeypatch):
    _env(monkeypatch)

    def handler(req: httpx.Request) -> httpx.Response:
        raise AssertionError("dry-run must not send a request")

    _patch_client(monkeypatch, handler)
    result = CliRunner().invoke(
        cli,
        [
            "datamodel",
            "accelerate",
            "Authentication",
            "--enable",
            "--app",
            "a",
            "--dry-run",
            "--output",
            "json",
        ],
    )
    assert result.exit_code == 0
    assert '"dry_run": true' in result.output


def test_lookup_upload_requires_app(monkeypatch, tmp_path):
    _env(monkeypatch)
    csv = tmp_path / "t.csv"
    csv.write_text("a,b\n1,2\n", encoding="utf-8")
    # No --app and no SPLUNK_APP -> the namespaced write must refuse (exit 2).
    result = CliRunner().invoke(cli, ["lookup", "upload", "--file", str(csv), "--output", "json"])
    assert result.exit_code == 2
    assert "usage_error" in result.output


def test_lookup_upload_dry_run_previews_namespace(monkeypatch, tmp_path):
    _env(monkeypatch)
    csv = tmp_path / "t.csv"
    csv.write_text("a,b\n1,2\n", encoding="utf-8")

    def handler(req: httpx.Request) -> httpx.Response:
        raise AssertionError("dry-run must not send a request")

    _patch_client(monkeypatch, handler)
    result = CliRunner().invoke(
        cli,
        ["lookup", "upload", "--file", str(csv), "--app", "a", "--dry-run", "--output", "json"],
    )
    assert result.exit_code == 0
    assert '"dry_run": true' in result.output
    assert "/servicesNS/nobody/a/data/lookup-table-files" in result.output
