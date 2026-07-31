"""Exhaustive execution and completeness checks for the canonical CLI catalog."""

from __future__ import annotations

import json
from collections import Counter

import httpx
import pytest
from click.testing import CliRunner

from cli_catalog import CATALOG, help_invocations, iter_leaves
from vct_splunk.cli import cli


def _handler(req: httpx.Request) -> httpx.Response:
    """One request recorder response set that satisfies every read leaf."""
    path = req.url.path
    if path.endswith("/dispatch"):
        return httpx.Response(201, json={"sid": "sid1"})
    if "/search/jobs" in path and req.method == "POST":
        return httpx.Response(200, json={"results": [{"error_count": "0"}]})
    content = {"version": "9.4", "health": "green", "features": {}}
    if path.endswith("/resource-usage/hostwide"):
        content.update(
            {"cpu_system_pct": "5", "cpu_user_pct": "10", "mem": "100", "mem_used": "20"}
        )
    if path.endswith("/partitions-space"):
        content.update({"mount_point": "/", "capacity": "100", "free": "80"})
    return httpx.Response(
        200,
        json={
            "entry": [
                {
                    "name": "example",
                    "content": content,
                    "acl": {"app": "a", "owner": "o", "sharing": "app"},
                }
            ],
            "paging": {"total": 1},
        },
    )


@pytest.mark.parametrize("argv", help_invocations(cli), ids=" ".join)
def test_every_help_screen_renders(argv):
    result = CliRunner().invoke(cli, argv)
    assert result.exit_code == 0, f"{argv}: {result.output}"
    assert "Usage:" in result.output


def test_catalog_is_exactly_complete_and_unique():
    live = {path for path, _ in iter_leaves(cli)}
    counts = Counter(case.path for case in CATALOG)
    duplicates = sorted(" ".join(path) for path, count in counts.items() if count != 1)
    catalogued = set(counts)

    assert duplicates == [], f"duplicate catalog commands: {duplicates}"
    assert sorted(" ".join(path) for path in live - catalogued) == [], "missing catalog commands"
    assert sorted(" ".join(path) for path in catalogued - live) == [], "stale catalog commands"
    assert len(CATALOG) == 154
    assert sum(case.kind == "read" for case in CATALOG) == 61
    assert sum(case.kind == "write" for case in CATALOG) == 93
    assert all(1 <= len(case.argvs) <= 2 for case in CATALOG)


@pytest.mark.parametrize("case", CATALOG, ids=lambda case: " ".join(case.path))
def test_every_leaf_executes(case, cli_env, patch_client, monkeypatch, tmp_path):
    monkeypatch.setenv("SPLUNK_APP", "my_app")
    monkeypatch.setenv("SPLUNK_PASSWORD", "secret")
    monkeypatch.setenv("VCT_SPLUNK_AUDIT", str(tmp_path / "audit.log"))
    requests: list[httpx.Request] = []

    def record(req: httpx.Request) -> httpx.Response:
        requests.append(req)
        return _handler(req)

    patch_client(record)
    if case.path == ("auth", "login"):
        monkeypatch.setattr("vct_splunk.commands.auth.core.login", lambda *args, **kwargs: "SK")

    for args in case.argvs:
        argv = [*case.path, *args, "--output", "json"]
        result = CliRunner().invoke(cli, argv)
        assert result.exit_code == 0, f"{argv}: {result.output}"
        assert "secret" not in result.output
        payload = json.loads(result.output)
        assert set(payload) == {"data", "meta"}
        if case.kind == "write":
            preview = payload["data"]
            assert preview["dry_run"] is True
            assert preview["request"]["method"] in {"POST", "DELETE"}
            assert preview["request"]["path"].startswith("/")
            assert "body" in preview["request"]
        else:
            assert isinstance(payload["data"], (dict, list))

    offline = {("auth", "login"), ("auth", "status"), ("inspect",)}
    if case.kind == "read" and case.path not in offline:
        assert requests, f"{' '.join(case.path)} did not exercise its transport"


@pytest.mark.parametrize(
    "case",
    [case for case in CATALOG if case.kind == "write"],
    ids=lambda case: " ".join(case.path),
)
def test_every_write_refuses_cloud_before_client_creation(case, cli_env, monkeypatch, tmp_path):
    monkeypatch.setenv("SPLUNK_URL", "https://acme.splunkcloud.com")
    monkeypatch.setenv("SPLUNK_APP", "my_app")
    monkeypatch.setenv("SPLUNK_PASSWORD", "secret")
    monkeypatch.setenv("VCT_SPLUNK_AUDIT", str(tmp_path / "audit.log"))

    def unexpected_client(*args, **kwargs):
        raise AssertionError("Cloud write must not construct an ACS or splunkd client")

    monkeypatch.setattr("vct_splunk.commands.context.Ctx.client", unexpected_client)
    monkeypatch.setattr("vct_splunk.commands.context.Ctx.acs_client", unexpected_client)
    for args in case.argvs:
        result = CliRunner().invoke(cli, [*case.path, *args, "--output", "json"])
        assert result.exit_code == 4, f"{' '.join(case.path)}: {result.output}"
        assert "unsupported_backend" in result.output
