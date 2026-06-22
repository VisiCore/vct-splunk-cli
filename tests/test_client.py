from __future__ import annotations

import httpx
import pytest

from vct_splunk.errors import AuthError, NotFoundError


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

    result = client_for(handler, dry_run=True).write("POST", "/services/data/indexes", {"name": "x"})
    assert result["dry_run"] is True
    assert calls["n"] == 0


def test_404_raises_not_found(client_for):
    with pytest.raises(NotFoundError):
        client_for(lambda req: httpx.Response(404, json={})).get("/services/data/indexes/nope")


def test_401_raises_auth(client_for):
    with pytest.raises(AuthError):
        client_for(lambda req: httpx.Response(401, json={})).get("/services/server/info")


def test_get_collection_paginates(client_for):
    items = [{"name": n} for n in "abc"]

    def handler(req: httpx.Request) -> httpx.Response:
        count = int(req.url.params.get("count", "200"))
        offset = int(req.url.params.get("offset", "0"))
        chunk = items[offset : offset + count]
        return httpx.Response(200, json={"entry": chunk, "paging": {"total": len(items)}})

    entries = client_for(handler).get_collection("/services/data/indexes", page=2)
    assert [e["name"] for e in entries] == ["a", "b", "c"]
