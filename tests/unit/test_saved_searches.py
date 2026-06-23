from __future__ import annotations

import httpx
import pytest

from vct_splunk.core import saved_searches as ss
from vct_splunk.core.errors import NotFoundError


def test_list_uses_namespaced_path(client_for):
    seen: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["path"] = req.url.path
        return httpx.Response(
            200,
            json={
                "entry": [
                    {
                        "name": "nightly",
                        "content": {"search": "index=main"},
                        "acl": {"app": "my_app", "owner": "nobody", "sharing": "app"},
                    }
                ],
                "paging": {"total": 1},
            },
        )

    rows = ss.list_saved_searches(client_for(handler), owner="-", app="-")
    assert seen["path"] == "/servicesNS/-/-/saved/searches"
    assert rows[0]["name"] == "nightly"
    assert rows[0]["app"] == "my_app"  # app/owner/sharing surfaced from the acl block
    assert rows[0]["sharing"] == "app"


def test_get_missing_raises(client_for):
    with pytest.raises(NotFoundError):
        ss.get_saved_search(
            client_for(lambda req: httpx.Response(200, json={"entry": []})),
            "x",
            owner="-",
            app="-",
        )


def test_create_posts_to_app_namespace(client_for):
    seen: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["path"] = req.url.path
        seen["body"] = req.content.decode()
        return httpx.Response(
            201,
            json={"entry": [{"name": "nightly", "content": {"search": "index=main"}, "acl": {}}]},
        )

    result = ss.create_saved_search(
        client_for(handler),
        "nightly",
        owner="nobody",
        app="my_app",
        search="index=main",
        cron="0 2 * * *",
    )
    assert seen["path"] == "/servicesNS/nobody/my_app/saved/searches"
    assert "name=nightly" in seen["body"]
    assert "cron_schedule=" in seen["body"]
    assert result["name"] == "nightly"


def test_update_omits_name_from_body(client_for):
    seen: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["path"] = req.url.path
        seen["body"] = req.content.decode()
        return httpx.Response(200, json={"entry": [{"name": "nightly", "content": {}, "acl": {}}]})

    ss.update_saved_search(
        client_for(handler), "nightly", owner="nobody", app="my_app", search="index=other"
    )
    assert seen["path"] == "/servicesNS/nobody/my_app/saved/searches/nightly"
    assert "name=" not in seen["body"]  # no rename: name stays in the URL only
    assert "search=" in seen["body"]


def test_delete_issues_delete(client_for):
    seen: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["method"] = req.method
        return httpx.Response(200, json={})

    ss.delete_saved_search(client_for(handler), "nightly", owner="nobody", app="my_app")
    assert seen["method"] == "DELETE"


def test_dispatch_returns_sid(client_for):
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"sid": "sid99"})

    result = ss.dispatch_saved_search(client_for(handler), "nightly", owner="-", app="-")
    assert result["sid"] == "sid99"
    assert result["dispatched"] is True
