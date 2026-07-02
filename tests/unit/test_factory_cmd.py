"""CLI smoke through factory-generated groups, proving the wiring the engine
tests can't see: field options, secret-from-env, verb subsetting, --set
passthrough, and the enable/disable control path.
"""

from __future__ import annotations

import httpx
from click.testing import CliRunner

from vct_splunk.cli import cli


def test_generated_user_create_previews_set_fields(cli_env):
    result = CliRunner().invoke(
        cli,
        [
            "user",
            "create",
            "alice",
            "--set",
            "roles=admin",
            "--set",
            "email=a@x.com",
            "--dry-run",
            "--output",
            "json",
        ],
    )
    assert result.exit_code == 0
    assert "/services/authentication/users" in result.output
    assert '"roles": "admin"' in result.output  # --set pairs land in the preview body
    assert "alice" in result.output


def test_capability_is_read_only(cli_env):
    # Verb subsetting: a read-only spec exposes no create subcommand.
    result = CliRunner().invoke(cli, ["capability", "create", "x"])
    assert result.exit_code == 2  # Click: no such command


def test_password_is_never_a_flag(cli_env):
    result = CliRunner().invoke(
        cli, ["user", "create", "alice", "--password", "hunter2", "--dry-run", "--output", "json"]
    )
    # The secret field must not exist as an option (Click rejects it as unknown).
    assert result.exit_code == 2
    assert "--password" not in CliRunner().invoke(cli, ["user", "create", "--help"]).output


def test_password_read_from_env_not_flag(cli_env, patch_client, monkeypatch, tmp_path):
    monkeypatch.setenv("SPLUNK_USER_PASSWORD", "hunter2")
    monkeypatch.setenv("VCT_SPLUNK_AUDIT", str(tmp_path / "audit.log"))
    seen: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["body"] = req.content.decode()
        return httpx.Response(201, json={"entry": [{"name": "alice", "content": {}}]})

    patch_client(handler)
    result = CliRunner().invoke(
        cli, ["user", "create", "alice", "--set", "roles=admin", "--yes", "--output", "json"]
    )
    assert result.exit_code == 0
    assert "password=hunter2" in seen["body"]  # secret pulled from env, sent on the wire


def test_namespaced_generated_group_requires_app(cli_env):
    # macro is namespaced -> a write without --app must refuse (never target 'search').
    result = CliRunner().invoke(
        cli, ["macro", "create", "m1", "--set", "definition=x", "--dry-run", "--output", "json"]
    )
    assert result.exit_code == 2
    assert "usage_error" in result.output


def test_namespaced_generated_group_previews_app_namespace(cli_env):
    result = CliRunner().invoke(
        cli,
        [
            "macro",
            "create",
            "m1",
            "--set",
            "definition=x",
            "--app",
            "my_app",
            "--dry-run",
            "--output",
            "json",
        ],
    )
    assert result.exit_code == 0
    assert "/servicesNS/nobody/my_app/configs/conf-macros" in result.output


def test_namespaced_write_audits_app_and_owner(cli_env, patch_client, monkeypatch, tmp_path):
    audit_file = tmp_path / "audit.log"
    monkeypatch.setenv("VCT_SPLUNK_AUDIT", str(audit_file))
    patch_client(lambda req: httpx.Response(201, json={"entry": [{"name": "m1", "content": {}}]}))
    result = CliRunner().invoke(
        cli,
        ["macro", "create", "m1", "--set", "definition=x", "--app", "my_app", "--yes"],
    )
    assert result.exit_code == 0, result.output
    contents = audit_file.read_text()
    assert '"app": "my_app"' in contents
    assert '"owner": "nobody"' in contents


def test_control_verb_posts_control_endpoint(cli_env, patch_client, monkeypatch, tmp_path):
    monkeypatch.setenv("VCT_SPLUNK_AUDIT", str(tmp_path / "audit.log"))
    seen: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["method"] = req.method
        seen["path"] = req.url.path
        return httpx.Response(200, json={})

    patch_client(handler)
    result = CliRunner().invoke(cli, ["monitor-input", "disable", "mon1", "--yes"])
    assert result.exit_code == 0, result.output
    assert seen["method"] == "POST"
    assert seen["path"] == "/services/data/inputs/monitor/mon1/disable"


def test_global_input_group_lists(cli_env, patch_client):
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "entry": [{"name": "/var/log", "content": {"index": "main"}}],
                "paging": {"total": 1},
            },
        )

    patch_client(handler)
    result = CliRunner().invoke(cli, ["monitor-input", "list", "--output", "json"])
    assert result.exit_code == 0
    assert "/var/log" in result.output
