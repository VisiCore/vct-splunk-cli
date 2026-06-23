from __future__ import annotations

import httpx

from vct_splunk.core.client import SplunkClient, config_from_env


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
