"""Isolated unit tests for the Click command adapters (#20).

These drive the real command + core + client stack through ``CliRunner`` while
mocking only the HTTP transport (the shared ``cli_env`` / ``patch_client``
fixtures), so each adapter is exercised without a live Splunk instance. Generic
per-command wiring lives in ``test_cli_matrix.py``; this file keeps the cases
with command-specific behavior worth pinning.
"""

from __future__ import annotations

import httpx
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


def test_search_run_executes(cli_env, patch_client):
    patch_client(lambda req: httpx.Response(200, json={"results": [{"x": "1"}]}))
    result = CliRunner().invoke(
        cli, ["search", "run", "--query", "index=_internal", "--output", "json"]
    )
    assert result.exit_code == 0
    assert '"count": 1' in result.output


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


def test_search_list_renders(cli_env, patch_client):
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "entry": [{"name": "sid1", "content": {"dispatchState": "DONE"}, "acl": {}}],
                "paging": {"total": 1},
            },
        )

    patch_client(handler)
    result = CliRunner().invoke(cli, ["search", "list", "--output", "json"])
    assert result.exit_code == 0
    assert '"sid": "sid1"' in result.output


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
    assert seen["path"].endswith("/saved/searches/nightly/dispatch")
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
