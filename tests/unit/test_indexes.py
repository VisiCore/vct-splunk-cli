from __future__ import annotations

import httpx

from vct_splunk.core import indexes


def test_list_indexes_parses(client_for):
    body = {
        "entry": [{"name": "main", "content": {"totalEventCount": 5, "currentDBSizeMB": 10}}],
        "paging": {"total": 1},
    }
    rows = indexes.list_indexes(client_for(lambda req: httpx.Response(200, json=body)))
    assert rows[0]["name"] == "main"
    assert rows[0]["total_event_count"] == 5


def test_create_index_posts_form(client_for):
    seen: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["method"] = req.method
        seen["body"] = req.content.decode()
        return httpx.Response(201, json={"entry": [{"name": "new", "content": {}}]})

    result = indexes.create_index(client_for(handler), "new", max_gb=1)
    assert seen["method"] == "POST"
    assert "name=new" in seen["body"]
    assert "maxTotalDataSizeMB=1024" in seen["body"]
    assert result["name"] == "new"


def test_update_index_sends_only_changed_settings(client_for):
    seen: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["method"] = req.method
        seen["path"] = req.url.path
        seen["body"] = req.content.decode()
        return httpx.Response(200, json={"entry": [{"name": "main", "content": {}}]})

    indexes.update_index(client_for(handler), "main", frozen_secs=86400)
    assert seen["method"] == "POST"
    assert seen["path"] == "/services/data/indexes/main"
    assert "frozenTimePeriodInSecs=86400" in seen["body"]
    assert "name=" not in seen["body"]  # server-side merge: name stays in the URL only


def test_enable_index_posts_control_endpoint(client_for):
    seen: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["method"] = req.method
        seen["path"] = req.url.path
        return httpx.Response(200, json={})

    indexes.enable_index(client_for(handler), "main")
    assert seen["method"] == "POST"
    assert seen["path"] == "/services/data/indexes/main/enable"


def test_disable_index_posts_control_endpoint(client_for):
    seen: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["path"] = req.url.path
        return httpx.Response(200, json={})

    indexes.disable_index(client_for(handler), "main")
    assert seen["path"] == "/services/data/indexes/main/disable"
