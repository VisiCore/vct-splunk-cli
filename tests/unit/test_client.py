from __future__ import annotations

import httpx
import pytest

from vct_splunk.core.errors import APIError, AuthError, NotFoundError, TransportError


def test_auth_header_and_json_mode(client_for):
    seen: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["auth"] = req.headers.get("authorization", "")
        seen["url"] = str(req.url)
        return httpx.Response(200, json={"entry": [{"content": {"version": "9.4"}}]})

    client_for(handler).get("/services/server/info")
    assert seen["auth"] == "Bearer TESTTOKEN"
    assert "output_mode=json" in seen["url"]


def test_dry_run_write_sends_nothing(client_for):
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(201, json={})

    result = client_for(handler, dry_run=True).write(
        "POST", "/services/data/indexes", {"name": "x"}
    )
    assert result["dry_run"] is True
    assert calls["n"] == 0


def test_404_raises_not_found(client_for):
    with pytest.raises(NotFoundError):
        client_for(lambda req: httpx.Response(404, json={})).get("/services/data/indexes/nope")


def test_401_raises_auth(client_for):
    with pytest.raises(AuthError):
        client_for(lambda req: httpx.Response(401, json={})).get("/services/server/info")


def test_403_raises_auth(client_for):
    with pytest.raises(AuthError):
        client_for(lambda req: httpx.Response(403, json={})).get("/services/server/info")


def test_5xx_raises_api_error_with_safe_body(client_for):
    with pytest.raises(APIError) as exc_info:
        client_for(lambda req: httpx.Response(500, json={"messages": ["boom"]})).get("/services/x")
    assert exc_info.value.exit_code == 1
    assert exc_info.value.details == {"messages": ["boom"]}  # JSON body carried as details


def test_400_non_json_body_is_truncated_text(client_for):
    with pytest.raises(APIError) as exc_info:
        client_for(lambda req: httpx.Response(400, text="x" * 1000)).get("/services/x")
    assert exc_info.value.details == "x" * 500  # _safe_body caps raw text


def test_unreachable_raises_transport_error(client_for):
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with pytest.raises(TransportError):
        client_for(handler).get("/services/server/info")


def test_non_json_200_returns_raw_text(client_for):
    client = client_for(lambda req: httpx.Response(200, text="<html>web ui</html>"))
    assert client.get("/services/x") == {"raw": "<html>web ui</html>"}


def test_retries_429_then_succeeds(client_for, monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr("vct_splunk.core.client.time.sleep", sleeps.append)
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={}, headers={"Retry-After": "7"})
        return httpx.Response(200, json={"ok": True})

    body = client_for(handler).get("/services/server/info")
    assert body == {"ok": True}
    assert calls["n"] == 2
    assert sleeps == [7.0]  # the server's Retry-After wins over the backoff curve


def test_retries_503_with_backoff_then_gives_up(client_for, monkeypatch):
    sleeps: list[float] = []
    monkeypatch.setattr("vct_splunk.core.client.time.sleep", sleeps.append)
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(503, json={})

    # After exhausting retries the final 503 surfaces as a plain APIError.
    with pytest.raises(APIError):
        client_for(handler).get("/services/server/info")
    assert calls["n"] == 4  # first try + 3 retries
    # The exact curve is an implementation detail; pin only that it backs off.
    assert len(sleeps) == 3 and sleeps == sorted(sleeps)


def test_400_is_not_retried(client_for, monkeypatch):
    monkeypatch.setattr(
        "vct_splunk.core.client.time.sleep",
        lambda s: pytest.fail("must not sleep on a non-retryable status"),
    )
    calls = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(400, json={})

    with pytest.raises(APIError):
        client_for(handler).get("/services/x")
    assert calls["n"] == 1


def test_get_collection_paginates(client_for):
    items = [{"name": n} for n in "abc"]

    def handler(req: httpx.Request) -> httpx.Response:
        count = int(req.url.params.get("count", "200"))
        offset = int(req.url.params.get("offset", "0"))
        chunk = items[offset : offset + count]
        return httpx.Response(200, json={"entry": chunk, "paging": {"total": len(items)}})

    entries = client_for(handler).get_collection("/services/data/indexes", page=2)
    assert [e["name"] for e in entries] == ["a", "b", "c"]


def test_request_passes_explicit_timeout_else_config(client_for, monkeypatch):
    # _request must forward an explicit timeout verbatim (including 0, which is a
    # real value, not "unset") and fall back to config.timeout only when None.
    client = client_for(lambda req: httpx.Response(200, json={}))
    seen: list[object] = []
    real = client._http.request

    def spy(method, url, **kwargs):
        seen.append(kwargs.get("timeout"))
        return real(method, url, **kwargs)

    monkeypatch.setattr(client._http, "request", spy)
    client.post("/services/search/jobs", {"q": "1"}, timeout=0)
    client.get("/services/server/info")
    assert seen == [0, 30.0]  # explicit 0 honored; None -> ClientConfig default
