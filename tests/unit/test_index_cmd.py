from __future__ import annotations

from click.testing import CliRunner

from vct_splunk.cli import cli


def _env(monkeypatch):
    monkeypatch.setenv("SPLUNK_URL", "https://splunk.test:8089")
    monkeypatch.setenv("SPLUNK_TOKEN", "T")


def test_create_refuses_without_yes_noninteractive(monkeypatch):
    _env(monkeypatch)
    result = CliRunner().invoke(cli, ["index", "create", "myidx", "--output", "json"])
    assert result.exit_code == 2
    assert "usage_error" in result.output


class _FakeClient:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def write(self, method, path, data):
        return {"dry_run": True, "request": {"method": method, "path": path, "body": data}}


def test_create_dry_run_previews(monkeypatch):
    _env(monkeypatch)
    monkeypatch.setattr("vct_splunk.commands.context.Ctx.client", lambda self: _FakeClient())
    result = CliRunner().invoke(cli, ["index", "create", "myidx", "--dry-run", "--output", "json"])
    assert result.exit_code == 0
    assert '"dry_run": true' in result.output


def test_update_requires_a_field(monkeypatch):
    _env(monkeypatch)
    result = CliRunner().invoke(cli, ["index", "update", "main", "--yes", "--output", "json"])
    assert result.exit_code == 2
    assert "usage_error" in result.output


def test_delete_refuses_without_yes_noninteractive(monkeypatch):
    _env(monkeypatch)
    result = CliRunner().invoke(cli, ["index", "delete", "main", "--output", "json"])
    assert result.exit_code == 2
    assert "usage_error" in result.output


def test_disable_dry_run_previews(monkeypatch):
    _env(monkeypatch)
    monkeypatch.setattr("vct_splunk.commands.context.Ctx.client", lambda self: _FakeClient())
    result = CliRunner().invoke(cli, ["index", "disable", "main", "--dry-run", "--output", "json"])
    assert result.exit_code == 0
    assert '"dry_run": true' in result.output


def test_add_alias_resolves_to_create(monkeypatch):
    # Splunk-CLI familiarity: `index add` resolves to `index create`.
    _env(monkeypatch)
    monkeypatch.setattr("vct_splunk.commands.context.Ctx.client", lambda self: _FakeClient())
    result = CliRunner().invoke(cli, ["index", "add", "myidx", "--dry-run", "--output", "json"])
    assert result.exit_code == 0
    assert '"dry_run": true' in result.output
