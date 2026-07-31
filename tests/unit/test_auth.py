"""Unit tests for session login + the `splunk auth` commands (#13)."""

from __future__ import annotations

import httpx
import pytest
from click.testing import CliRunner

from vct_splunk.cli import cli
from vct_splunk.core import auth as core
from vct_splunk.core.errors import APIError, AuthError


def _clear_auth_env(monkeypatch):
    for var in (
        "SPLUNK_URL",
        "SPLUNK_TOKEN",
        "SPLUNK_SESSION_KEY",
        "SPLUNK_USERNAME",
        "SPLUNK_PASSWORD",
        "SPLUNK_PROFILE",
        "VCT_SPLUNK_CONFIG",
    ):
        monkeypatch.delenv(var, raising=False)


# --- core.auth.login (mocked transport, no network) -------------------------


def test_login_returns_session_key():
    seen_path = ""
    seen_auth: str | None = "sentinel"
    seen_body = ""

    def handler(req: httpx.Request) -> httpx.Response:
        nonlocal seen_path, seen_auth, seen_body
        seen_path = req.url.path
        seen_auth = req.headers.get("authorization")
        seen_body = req.content.decode()
        return httpx.Response(200, json={"sessionKey": "SK123"})

    key = core.login(
        "https://splunk.test:8089/",
        "admin",
        "secret",
        transport=httpx.MockTransport(handler),
    )
    assert key == "SK123"
    assert seen_path == "/services/auth/login"
    # This call authenticates via the body, so it must carry no bearer header.
    assert seen_auth is None
    assert "username=admin" in seen_body


def test_login_401_raises_auth():
    with pytest.raises(AuthError):
        core.login(
            "https://splunk.test:8089",
            "admin",
            "bad",
            transport=httpx.MockTransport(lambda req: httpx.Response(401, json={})),
        )


def test_login_403_raises_auth():
    with pytest.raises(AuthError):
        core.login(
            "https://splunk.test:8089",
            "admin",
            "forbidden",
            transport=httpx.MockTransport(lambda req: httpx.Response(403, json={})),
        )


def test_login_missing_session_key_raises_auth():
    with pytest.raises(AuthError):
        core.login(
            "https://splunk.test:8089",
            "admin",
            "secret",
            transport=httpx.MockTransport(lambda req: httpx.Response(200, json={})),
        )


def test_login_500_raises_api():
    with pytest.raises(APIError):
        core.login(
            "https://splunk.test:8089",
            "admin",
            "secret",
            transport=httpx.MockTransport(lambda req: httpx.Response(500, text="boom")),
        )


# --- splunk auth login / status (CliRunner) ---------------------------------


def test_auth_login_echoes_session_key(monkeypatch):
    _clear_auth_env(monkeypatch)
    monkeypatch.setenv("SPLUNK_URL", "https://splunk.test:8089")
    monkeypatch.setenv("SPLUNK_USERNAME", "admin")
    monkeypatch.setenv("SPLUNK_PASSWORD", "secret")
    monkeypatch.setattr("vct_splunk.commands.auth.core.login", lambda *a, **k: "SK-FROM-LOGIN")
    result = CliRunner().invoke(cli, ["auth", "login", "--output", "json"])
    assert result.exit_code == 0
    assert '"session_key": "SK-FROM-LOGIN"' in result.output
    assert "export SPLUNK_SESSION_KEY" not in result.stderr


def test_auth_login_refuses_without_password_noninteractive(monkeypatch):
    _clear_auth_env(monkeypatch)
    monkeypatch.setenv("SPLUNK_URL", "https://splunk.test:8089")
    monkeypatch.setenv("SPLUNK_USERNAME", "admin")
    # No SPLUNK_PASSWORD and CliRunner stdin is not a TTY -> clean refusal.
    result = CliRunner().invoke(cli, ["auth", "login", "--output", "json"])
    assert result.exit_code == 2
    assert "usage_error" in result.output


def test_auth_status_reports_bearer(monkeypatch):
    _clear_auth_env(monkeypatch)
    monkeypatch.setenv("SPLUNK_URL", "https://splunk.test:8089")
    monkeypatch.setenv("SPLUNK_TOKEN", "T")
    result = CliRunner().invoke(cli, ["auth", "status", "--output", "json"])
    assert result.exit_code == 0
    assert '"auth_scheme": "Bearer"' in result.output
    assert '"target": "https://splunk.test:8089"' in result.output


def test_auth_status_reports_session_key_scheme(monkeypatch):
    _clear_auth_env(monkeypatch)
    monkeypatch.setenv("SPLUNK_URL", "https://splunk.test:8089")
    monkeypatch.setenv("SPLUNK_SESSION_KEY", "SK")
    result = CliRunner().invoke(cli, ["auth", "status", "--output", "json"])
    assert result.exit_code == 0
    assert '"auth_scheme": "Splunk"' in result.output


def test_auth_status_reports_none_when_unset(monkeypatch):
    _clear_auth_env(monkeypatch)
    monkeypatch.setenv("SPLUNK_URL", "https://splunk.test:8089")
    result = CliRunner().invoke(cli, ["auth", "status", "--output", "json"])
    assert result.exit_code == 0
    assert '"auth_scheme": "none"' in result.output
