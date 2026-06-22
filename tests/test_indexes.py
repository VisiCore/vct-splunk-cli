from __future__ import annotations

import httpx

from vct_splunk import indexes


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
