from __future__ import annotations

import httpx
import pytest

from vct_splunk.core.client import SplunkClient, config_from_env
from vct_splunk.core.errors import APIError, AuthError, TransportError, UsageError


@pytest.fixture
def _clean_env(monkeypatch):
    """Strip every auth-related variable so each test states exactly what it sets."""
    for var in (
        "SPLUNK_URL",
        "SPLUNK_TOKEN",
        "SPLUNK_SESSION_KEY",
        "SPLUNK_USERNAME",
        "SPLUNK_PASSWORD",
        "SPLUNK_CA_BUNDLE",
        "SPLUNK_VERIFY",
    ):
        monkeypatch.delenv(var, raising=False)


def test_session_key_scheme_and_header(monkeypatch):
    # Only SPLUNK_SESSION_KEY set: config picks the "Splunk <key>" scheme and the
    # client sends `Authorization: Splunk <key>` (vs the default Bearer/JWT path).
    monkeypatch.delenv("SPLUNK_TOKEN", raising=False)
    monkeypatch.setenv("SPLUNK_URL", "https://splunk.test:8089")
    monkeypatch.setenv("SPLUNK_SESSION_KEY", "SESSIONKEY")

    cfg = config_from_env()
    assert cfg.auth_scheme == "Splunk"
    assert cfg.token == "SESSIONKEY"

    seen: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["auth"] = req.headers.get("authorization", "")
        return httpx.Response(200, json={"entry": []})

    SplunkClient(cfg, transport=httpx.MockTransport(handler)).get("/services/server/info")
    assert seen["auth"] == "Splunk SESSIONKEY"


def test_username_password_login(monkeypatch):
    # No token or session key: the client logs in with SPLUNK_USERNAME/SPLUNK_PASSWORD
    # via /services/auth/login and uses the returned session key (the CI fallback; not
    # an encouraged path, so it is intentionally undocumented).
    monkeypatch.delenv("SPLUNK_TOKEN", raising=False)
    monkeypatch.delenv("SPLUNK_SESSION_KEY", raising=False)
    monkeypatch.setenv("SPLUNK_URL", "https://splunk.test:8089")
    monkeypatch.setenv("SPLUNK_USERNAME", "admin")
    monkeypatch.setenv("SPLUNK_PASSWORD", "secret")

    seen: dict[str, object] = {}

    def fake_post(url, *, data, verify, timeout):
        seen["url"] = url
        seen["data"] = data
        return httpx.Response(200, json={"sessionKey": "LOGGEDIN"})

    monkeypatch.setattr("vct_splunk.core.client.httpx.post", fake_post)

    cfg = config_from_env()
    assert cfg.auth_scheme == "Splunk"
    assert cfg.token == "LOGGEDIN"
    assert str(seen["url"]).endswith("/services/auth/login")
    assert seen["data"]["username"] == "admin"  # type: ignore[index]


def _login_env(monkeypatch):
    monkeypatch.setenv("SPLUNK_URL", "https://splunk.test:8089")
    monkeypatch.setenv("SPLUNK_USERNAME", "admin")
    monkeypatch.setenv("SPLUNK_PASSWORD", "secret")


@pytest.mark.parametrize(
    "response,expected",
    [
        (httpx.Response(401, json={}), AuthError),
        (httpx.Response(403, json={}), AuthError),
        (httpx.Response(500, json={"messages": ["boom"]}), APIError),
        (httpx.Response(200, json={}), AuthError),  # 200 but no sessionKey in the body
    ],
)
def test_login_error_responses_map_typed(_clean_env, monkeypatch, response, expected):
    _login_env(monkeypatch)
    monkeypatch.setattr("vct_splunk.core.client.httpx.post", lambda *a, **k: response)
    with pytest.raises(expected):
        config_from_env()


def test_login_unreachable_raises_transport_error(_clean_env, monkeypatch):
    _login_env(monkeypatch)

    def raise_connect(*a, **k):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr("vct_splunk.core.client.httpx.post", raise_connect)
    with pytest.raises(TransportError):
        config_from_env()


def test_config_requires_a_url(_clean_env):
    with pytest.raises(UsageError, match="SPLUNK_URL"):
        config_from_env()


def test_config_requires_some_auth(_clean_env, monkeypatch):
    monkeypatch.setenv("SPLUNK_URL", "https://splunk.test:8089")
    with pytest.raises(UsageError, match="SPLUNK_TOKEN"):
        config_from_env()


def test_ca_bundle_becomes_verify_path(_clean_env, monkeypatch):
    monkeypatch.setenv("SPLUNK_URL", "https://splunk.test:8089")
    monkeypatch.setenv("SPLUNK_TOKEN", "T")
    monkeypatch.setenv("SPLUNK_CA_BUNDLE", "/path/ca.pem")
    monkeypatch.setenv("SPLUNK_VERIFY", "false")  # CA bundle takes precedence
    assert config_from_env().verify == "/path/ca.pem"


def test_verify_flag_parsing(_clean_env, monkeypatch):
    monkeypatch.setenv("SPLUNK_URL", "https://splunk.test:8089")
    monkeypatch.setenv("SPLUNK_TOKEN", "T")
    assert config_from_env().verify is True  # default: verify
    monkeypatch.setenv("SPLUNK_VERIFY", "false")
    assert config_from_env().verify is False
