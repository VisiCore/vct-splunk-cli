from __future__ import annotations

import httpx
import pytest

from vct_splunk.api.client import SplunkClient
from vct_splunk.auth import session
from vct_splunk.config.loader import load_config
from vct_splunk.utils.errors import APIError, AuthError, TransportError, UsageError


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
        "SPLUNK_PROFILE",
        "VCT_SPLUNK_CONFIG",
    ):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture(autouse=True)
def _clear_session_cache():
    session.clear_session_cache()
    yield
    session.clear_session_cache()


def test_session_key_scheme_and_header(_clean_env, monkeypatch):
    # Only SPLUNK_SESSION_KEY set: the auth transport sends
    # `Authorization: Splunk <key>` (vs the default Bearer/JWT path).
    monkeypatch.setenv("SPLUNK_URL", "https://splunk.test:8089")
    monkeypatch.setenv("SPLUNK_SESSION_KEY", "SESSIONKEY")

    cfg = load_config()
    assert cfg.session_key == "SESSIONKEY"
    assert cfg.token is None

    seen: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["auth"] = req.headers.get("authorization", "")
        return httpx.Response(200, json={"entry": []})

    SplunkClient(cfg, transport=httpx.MockTransport(handler)).get("/services/server/info")
    assert seen["auth"] == "Splunk SESSIONKEY"


def test_username_password_login_is_lazy(_clean_env, monkeypatch):
    # No token or session key: the auth transport logs in with
    # SPLUNK_USERNAME/SPLUNK_PASSWORD via /services/auth/login on the *first
    # request* (not at config time) and sends the returned session key.
    monkeypatch.setenv("SPLUNK_URL", "https://splunk.test:8089")
    monkeypatch.setenv("SPLUNK_USERNAME", "admin")
    monkeypatch.setenv("SPLUNK_PASSWORD", "secret")

    seen: dict[str, object] = {}

    def fake_login(url, username, password, *, verify, timeout):
        seen.update({"url": url, "username": username, "password": password, "verify": verify})
        return "LOGGEDIN"

    monkeypatch.setattr("vct_splunk.auth.session.login", fake_login)

    cfg = load_config()
    assert cfg.username == "admin"
    assert not seen  # config loading performed no login

    headers: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        headers["auth"] = req.headers.get("authorization", "")
        return httpx.Response(200, json={"entry": []})

    SplunkClient(cfg, transport=httpx.MockTransport(handler)).get("/services/server/info")
    assert headers["auth"] == "Splunk LOGGEDIN"
    assert seen["url"] == "https://splunk.test:8089"
    assert seen["username"] == "admin"


def test_login_session_is_cached_across_requests(_clean_env, monkeypatch):
    monkeypatch.setenv("SPLUNK_URL", "https://splunk.test:8089")
    monkeypatch.setenv("SPLUNK_USERNAME", "admin")
    monkeypatch.setenv("SPLUNK_PASSWORD", "secret")

    calls = {"n": 0}

    def fake_login(url, username, password, *, verify, timeout):
        calls["n"] += 1
        return "LOGGEDIN"

    monkeypatch.setattr("vct_splunk.auth.session.login", fake_login)

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"entry": []})

    client = SplunkClient(load_config(), transport=httpx.MockTransport(handler))
    client.get("/services/server/info")
    client.get("/services/server/info")
    assert calls["n"] == 1  # the minted session key is reused


@pytest.mark.parametrize(
    "expected",
    [AuthError, APIError, TransportError],
)
def test_login_errors_surface_on_first_request(_clean_env, monkeypatch, expected):
    monkeypatch.setenv("SPLUNK_URL", "https://splunk.test:8089")
    monkeypatch.setenv("SPLUNK_USERNAME", "admin")
    monkeypatch.setenv("SPLUNK_PASSWORD", "secret")

    def fail_login(*args, **kwargs):
        raise expected("login failed")

    monkeypatch.setattr("vct_splunk.auth.session.login", fail_login)

    def handler(req: httpx.Request) -> httpx.Response:  # pragma: no cover - never reached
        return httpx.Response(200, json={"entry": []})

    client = SplunkClient(load_config(), transport=httpx.MockTransport(handler))
    with pytest.raises(expected):
        client.get("/services/server/info")


def test_config_requires_a_url(_clean_env):
    with pytest.raises(UsageError, match="SPLUNK_URL"):
        load_config()


def test_config_requires_some_auth(_clean_env, monkeypatch):
    monkeypatch.setenv("SPLUNK_URL", "https://splunk.test:8089")
    with pytest.raises(UsageError, match="SPLUNK_TOKEN"):
        load_config()


def test_ca_bundle_becomes_verify_path(_clean_env, monkeypatch):
    monkeypatch.setenv("SPLUNK_URL", "https://splunk.test:8089")
    monkeypatch.setenv("SPLUNK_TOKEN", "T")
    monkeypatch.setenv("SPLUNK_CA_BUNDLE", "/path/ca.pem")
    monkeypatch.setenv("SPLUNK_VERIFY", "false")  # CA bundle takes precedence
    assert load_config().verify == "/path/ca.pem"


def test_verify_flag_parsing(_clean_env, monkeypatch):
    monkeypatch.setenv("SPLUNK_URL", "https://splunk.test:8089")
    monkeypatch.setenv("SPLUNK_TOKEN", "T")
    assert load_config().verify is True  # default: verify
    monkeypatch.setenv("SPLUNK_VERIFY", "false")
    assert load_config().verify is False
