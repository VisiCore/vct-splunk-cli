"""One CLI smoke through a factory-generated group (user), proving the wiring:
field options, secret-from-env, do_write gating, verb subsetting, and aliases.
"""

from __future__ import annotations

import httpx
from click.testing import CliRunner

from vct_splunk.cli import cli
from vct_splunk.core.client import ClientConfig, SplunkClient


def _env(monkeypatch):
    monkeypatch.setenv("SPLUNK_URL", "https://splunk.test:8089")
    monkeypatch.setenv("SPLUNK_TOKEN", "T")
    monkeypatch.delenv("SPLUNK_USER_PASSWORD", raising=False)


def _patch_client(monkeypatch, handler):
    def make(self):
        cfg = ClientConfig(base_url="https://splunk.test:8089", token="T", dry_run=self.dry_run)
        return SplunkClient(cfg, transport=httpx.MockTransport(handler))

    monkeypatch.setattr("vct_splunk.commands.context.Ctx.client", make)


def test_generated_user_create_dry_run_previews(monkeypatch):
    _env(monkeypatch)
    result = CliRunner().invoke(
        cli,
        [
            "user",
            "create",
            "alice",
            "--role",
            "admin",
            "--email",
            "a@x.com",
            "--dry-run",
            "--output",
            "json",
        ],
    )
    assert result.exit_code == 0
    assert '"dry_run": true' in result.output
    assert "/services/authentication/users" in result.output
    assert "alice" in result.output


def test_generated_user_create_refuses_without_yes(monkeypatch):
    _env(monkeypatch)
    result = CliRunner().invoke(
        cli, ["user", "create", "alice", "--role", "admin", "--output", "json"]
    )
    assert result.exit_code == 2
    assert "usage_error" in result.output


def test_capability_is_read_only(monkeypatch):
    _env(monkeypatch)
    # Verb subsetting: a read-only spec exposes no create subcommand.
    result = CliRunner().invoke(cli, ["capability", "create", "x"])
    assert result.exit_code == 2  # Click: no such command


def test_password_is_never_a_flag(monkeypatch):
    _env(monkeypatch)
    result = CliRunner().invoke(
        cli, ["user", "create", "alice", "--password", "hunter2", "--dry-run", "--output", "json"]
    )
    assert result.exit_code == 2  # no such option
    assert "no such option" in result.output.lower()


def test_password_read_from_env_not_flag(monkeypatch, tmp_path):
    _env(monkeypatch)
    monkeypatch.setenv("SPLUNK_USER_PASSWORD", "hunter2")
    monkeypatch.setenv("VCT_SPLUNK_AUDIT", str(tmp_path / "audit.log"))
    seen: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["body"] = req.content.decode()
        return httpx.Response(201, json={"entry": [{"name": "alice", "content": {}}]})

    _patch_client(monkeypatch, handler)
    result = CliRunner().invoke(
        cli, ["user", "create", "alice", "--role", "admin", "--yes", "--output", "json"]
    )
    assert result.exit_code == 0
    assert "password=hunter2" in seen["body"]  # secret pulled from env, sent on the wire


def test_add_alias_on_generated_group(monkeypatch):
    _env(monkeypatch)
    result = CliRunner().invoke(
        cli, ["user", "add", "alice", "--role", "admin", "--dry-run", "--output", "json"]
    )
    assert result.exit_code == 0
    assert '"dry_run": true' in result.output
