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
