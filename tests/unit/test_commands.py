"""Isolated unit tests for the Click command adapters (#20).

These drive the real command + core + client stack through ``CliRunner`` while
mocking only the HTTP transport (the shared ``cli_env`` / ``patch_client``
fixtures), so each adapter is exercised without a live Splunk instance. Generic
per-command wiring lives in ``test_cli_matrix.py``; this file keeps the cases
with command-specific behavior worth pinning.
"""

from __future__ import annotations

import httpx
import pytest
from click.testing import CliRunner

from vct_splunk.cli import cli


def test_api_get_accepts_namespaced_path(cli_env, patch_client):
    seen: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["path"] = req.url.path
        return httpx.Response(200, json={"entry": []})

    patch_client(handler)
    result = CliRunner().invoke(
        cli, ["api", "get", "/servicesNS/nobody/search/saved/searches", "--output", "json"]
    )
    assert result.exit_code == 0
    assert seen["path"] == "/servicesNS/nobody/search/saved/searches"


def test_api_get_rejects_non_services_path(cli_env, patch_client):
    # The escape hatch is read-only AND path-restricted: anything outside
    # /services or /servicesNS is refused before any request is made.
    patch_client(lambda req: httpx.Response(200, json={}))
    result = CliRunner().invoke(cli, ["api", "get", "/etc/passwd", "--output", "json"])
    assert result.exit_code == 2
    assert "usage_error" in result.output


def test_api_get_query_requires_key_value(cli_env, patch_client):
    patch_client(lambda req: httpx.Response(200, json={}))
    result = CliRunner().invoke(
        cli, ["api", "get", "/services/x", "-q", "brokenpair", "--output", "json"]
    )
    assert result.exit_code == 2
    assert "usage_error" in result.output


def test_api_get_forwards_query_params(cli_env, patch_client):
    seen: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["query"] = str(req.url.query.decode())
        return httpx.Response(200, json={"entry": []})

    patch_client(handler)
    result = CliRunner().invoke(
        cli, ["api", "get", "/services/x", "-q", "search=foo", "--output", "json"]
    )
    assert result.exit_code == 0
    assert "search=foo" in seen["query"]


def test_search_run_reads_query_from_file(cli_env, patch_client, tmp_path):
    seen: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["body"] = req.content.decode()
        return httpx.Response(200, json={"results": []})

    patch_client(handler)
    spl = tmp_path / "q.spl"
    spl.write_text("index=fromfile")
    result = CliRunner().invoke(cli, ["search", "run", "--file", str(spl), "--output", "json"])
    assert result.exit_code == 0
    assert "index%3Dfromfile" in seen["body"] or "index=fromfile" in seen["body"]


def test_search_run_reads_query_from_stdin(cli_env, patch_client):
    seen: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["body"] = req.content.decode()
        return httpx.Response(200, json={"results": []})

    patch_client(handler)
    result = CliRunner().invoke(
        cli, ["search", "run", "-", "--output", "json"], input="index=fromstdin"
    )
    assert result.exit_code == 0
    assert "fromstdin" in seen["body"]


def test_search_run_requires_exactly_one_query_source(cli_env, patch_client):
    patch_client(lambda req: httpx.Response(200, json={"results": []}))
    result = CliRunner().invoke(cli, ["search", "run", "--output", "json"])
    assert result.exit_code == 2
    assert "usage_error" in result.output


def test_health_check_exits_5_on_fail(cli_env, patch_client):
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/services/server/info":
            return httpx.Response(
                200, json={"entry": [{"content": {"version": "9.4", "serverName": "sh"}}]}
            )
        return httpx.Response(200, json={"entry": [{"content": {"health": "red", "features": {}}}]})

    patch_client(handler)
    result = CliRunner().invoke(cli, ["health", "check", "--output", "json"])
    # Exit 5 is the dedicated "health findings" code, distinct from exit 1
    # (API/transport error).
    assert result.exit_code == 5
    assert '"finding": "fail"' in result.output


@pytest.mark.parametrize("status", [403, 404])
def test_health_optional_checks_unavailable_exit_zero(cli_env, patch_client, status):
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/services/server/info":
            return httpx.Response(
                200,
                json={"entry": [{"content": {"version": "9.4", "serverName": "sh"}}]},
            )
        return httpx.Response(status, json={"messages": []})

    patch_client(handler)
    result = CliRunner().invoke(cli, ["health", "check", "--output", "json"])

    assert result.exit_code == 0
    assert '"finding": "na"' in result.output
    expected = "permission_denied" if status == 403 else "not_applicable"
    assert f'"{expected}"' in result.output
    assert '"health_checks_version": "1"' in result.output
    assert '"check": "checks_version"' not in result.output


def test_saved_search_create_requires_app(cli_env):
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


def test_saved_search_create_dry_run_previews_app_namespace(cli_env):
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


def test_cluster_status_renders(cli_env, patch_client):
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/services/cluster/manager/info"
        return httpx.Response(
            200,
            json={"entry": [{"content": {"label": "cluster-one", "indexing_ready_flag": True}}]},
        )

    patch_client(handler)
    result = CliRunner().invoke(cli, ["cluster", "status", "--output", "json"])
    assert result.exit_code == 0
    assert '"label": "cluster-one"' in result.output


def test_license_list_renders(cli_env, patch_client):
    patch_client(
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


def test_message_list_renders(cli_env, patch_client):
    patch_client(
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


def test_server_settings_get_renders(cli_env, patch_client):
    patch_client(
        lambda req: httpx.Response(
            200, json={"entry": [{"content": {"serverName": "sh1", "host": "sh1"}}]}
        ),
    )
    result = CliRunner().invoke(cli, ["server", "settings", "get", "--output", "json"])
    assert result.exit_code == 0
    assert '"serverName": "sh1"' in result.output


def test_server_restart_refuses_without_yes_noninteractive(cli_env):
    # Must refuse before any network call, so no client patch is needed.
    result = CliRunner().invoke(cli, ["server", "restart", "--output", "json"])
    assert result.exit_code == 2
    assert "usage_error" in result.output


def test_server_restart_dry_run_previews(cli_env, patch_client):
    def handler(req: httpx.Request) -> httpx.Response:
        raise AssertionError("dry-run must not send a request")

    patch_client(handler)
    result = CliRunner().invoke(cli, ["server", "restart", "--dry-run", "--output", "json"])
    assert result.exit_code == 0
    assert '"dry_run": true' in result.output


def test_server_settings_set_dry_run_previews(cli_env, patch_client):
    def handler(req: httpx.Request) -> httpx.Response:
        raise AssertionError("dry-run must not send a request")

    patch_client(handler)
    result = CliRunner().invoke(
        cli,
        ["server", "settings", "set", "--set", "host=sh1", "--dry-run", "--output", "json"],
    )
    assert result.exit_code == 0
    assert '"dry_run": true' in result.output


def test_app_install_requires_one_source(cli_env):
    # Neither --server-file nor --url: usage error before any network call.
    result = CliRunner().invoke(cli, ["app", "install", "--output", "json"])
    assert result.exit_code == 2
    assert "usage_error" in result.output


def test_app_install_url_dry_run_previews(cli_env, patch_client):
    def handler(req: httpx.Request) -> httpx.Response:
        raise AssertionError("dry-run must not send a request")

    patch_client(handler)
    result = CliRunner().invoke(
        cli, ["app", "install", "--url", "https://x/app.spl", "--dry-run", "--output", "json"]
    )
    assert result.exit_code == 0
    assert '"dry_run": true' in result.output


def test_deploy_client_list_renders(cli_env, patch_client):
    patch_client(
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


def test_deploy_serverclass_list_renders(cli_env, patch_client):
    patch_client(
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


def test_deploy_reload_refuses_without_yes_noninteractive(cli_env):
    # Must refuse before any network call, so no client patch is needed.
    result = CliRunner().invoke(cli, ["deploy", "reload", "--output", "json"])
    assert result.exit_code == 2
    assert "usage_error" in result.output


def test_deploy_reload_dry_run_previews(cli_env, patch_client):
    def handler(req: httpx.Request) -> httpx.Response:
        raise AssertionError("dry-run must not send a request")

    patch_client(handler)
    result = CliRunner().invoke(cli, ["deploy", "reload", "--dry-run", "--output", "json"])
    assert result.exit_code == 0
    assert '"dry_run": true' in result.output


def test_deploy_serverclass_create_dry_run_previews(cli_env, patch_client):
    def handler(req: httpx.Request) -> httpx.Response:
        raise AssertionError("dry-run must not send a request")

    patch_client(handler)
    result = CliRunner().invoke(
        cli,
        ["deploy", "serverclass", "create", "foo", "--set", "x=1", "--dry-run", "--output", "json"],
    )
    assert result.exit_code == 0
    assert '"dry_run": true' in result.output


def test_hec_global_enable_refuses_without_yes_noninteractive(cli_env):
    # Must refuse before any network call, so no client patch is needed.
    result = CliRunner().invoke(cli, ["hec", "global-enable", "--output", "json"])
    assert result.exit_code == 2
    assert "usage_error" in result.output


def test_hec_global_enable_dry_run_previews(cli_env, patch_client):
    def handler(req: httpx.Request) -> httpx.Response:
        raise AssertionError("dry-run must not send a request")

    patch_client(handler)
    result = CliRunner().invoke(cli, ["hec", "global-enable", "--dry-run", "--output", "json"])
    assert result.exit_code == 0
    assert '"dry_run": true' in result.output


def test_hec_rotate_dry_run_previews(cli_env, patch_client):
    def handler(req: httpx.Request) -> httpx.Response:
        raise AssertionError("dry-run must not send a request")

    patch_client(handler)
    result = CliRunner().invoke(cli, ["hec", "rotate", "tok1", "--dry-run", "--output", "json"])
    assert result.exit_code == 0
    assert '"dry_run": true' in result.output


def test_datamodel_list_renders(cli_env, patch_client):
    patch_client(
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


def test_tag_list_renders(cli_env, patch_client):
    patch_client(
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


def test_datamodel_accelerate_dry_run_previews(cli_env, patch_client):
    def handler(req: httpx.Request) -> httpx.Response:
        raise AssertionError("dry-run must not send a request")

    patch_client(handler)
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


def test_lookup_upload_requires_app(cli_env, monkeypatch):
    monkeypatch.delenv("SPLUNK_APP", raising=False)
    # No --app and no SPLUNK_APP -> the namespaced write must refuse (exit 2).
    result = CliRunner().invoke(
        cli, ["lookup", "upload", "--server-file", "/var/tmp/t.csv", "--output", "json"]
    )
    assert result.exit_code == 2
    assert "usage_error" in result.output


def test_lookup_upload_dry_run_previews_namespace(cli_env, patch_client):
    def handler(req: httpx.Request) -> httpx.Response:
        raise AssertionError("dry-run must not send a request")

    patch_client(handler)
    result = CliRunner().invoke(
        cli,
        [
            "lookup",
            "upload",
            "--server-file",
            "/var/tmp/t.csv",
            "--app",
            "a",
            "--dry-run",
            "--output",
            "json",
        ],
    )
    assert result.exit_code == 0
    assert '"dry_run": true' in result.output
    assert "/servicesNS/nobody/a/data/lookup-table-files" in result.output


def test_saved_search_scheduled_flag_coerces_to_int(cli_env):
    # The bool Field must reach the wire as is_scheduled=0/1, not False/True.
    result = CliRunner().invoke(
        cli,
        [
            "saved-search",
            "update",
            "nightly",
            "--no-scheduled",
            "--app",
            "my_app",
            "--dry-run",
            "--output",
            "json",
        ],
    )
    assert result.exit_code == 0
    assert '"is_scheduled": 0' in result.output


def test_base_url_flag_overrides_env(cli_env, patch_client):
    patch_client(lambda req: httpx.Response(200, json={"entry": [{"content": {}}]}))
    result = CliRunner().invoke(
        cli, ["server", "info", "--base-url", "https://other.test:8089", "--output", "json"]
    )
    assert result.exit_code == 0
    assert '"target": "https://other.test:8089"' in result.output  # flag wins over SPLUNK_URL


def test_owner_flag_narrows_the_namespace(cli_env, patch_client):
    seen: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["path"] = req.url.path
        return httpx.Response(200, json={"entry": [], "paging": {"total": 0}})

    patch_client(handler)
    result = CliRunner().invoke(
        cli, ["saved-search", "list", "--owner", "alice", "--output", "json"]
    )
    assert result.exit_code == 0
    assert seen["path"] == "/servicesNS/alice/-/saved/searches"


def test_saved_search_run_dispatches_with_times(cli_env, patch_client):
    seen: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["path"] = req.url.path
        seen["body"] = req.content.decode()
        return httpx.Response(201, json={"sid": "sid42"})

    patch_client(handler)
    result = CliRunner().invoke(
        cli,
        [
            "saved-search",
            "run",
            "nightly",
            "--trigger-actions",
            "--earliest",
            "-1h",
            "--app",
            "my_app",
            "--output",
            "json",
        ],
    )
    assert result.exit_code == 0
    assert '"sid": "sid42"' in result.output
    # Never a wildcard: Splunk 400s a dispatch to /servicesNS/-/... (found live).
    assert seen["path"] == "/servicesNS/nobody/my_app/saved/searches/nightly/dispatch"
    assert "trigger_actions=1" in seen["body"]
    assert "dispatch.earliest_time" in seen["body"]


def test_saved_search_run_dry_run_matches_real_payload(cli_env):
    # The preview body must carry everything the real request would send.
    result = CliRunner().invoke(
        cli,
        [
            "saved-search",
            "run",
            "nightly",
            "--earliest",
            "-1h",
            "--latest",
            "now",
            "--app",
            "my_app",
            "--dry-run",
            "--output",
            "json",
        ],
    )
    assert result.exit_code == 0
    assert '"dispatch.earliest_time": "-1h"' in result.output
    assert '"dispatch.latest_time": "now"' in result.output
