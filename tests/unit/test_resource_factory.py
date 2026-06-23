"""Engine tests for the CRUD factory.

These test the generic CrudResource once over two contrived specs (a global one
and a namespaced one), which covers every registry resource forever -- adding a
Spec adds no test burden.
"""

from __future__ import annotations

import httpx
import pytest

from vct_splunk.core.errors import NotFoundError
from vct_splunk.core.resource import CrudResource, Field, Spec

GLOBAL_SPEC = Spec(
    name="widget",
    path="/services/data/widgets",
    help="Widgets.",
    fields=(
        Field("size_gb", key="sizeMB", type="float", scale=1024),
        Field("tag", key="tags", multi=True),
        Field("color", key="color"),
    ),
    out_map={"sizeMB": "size_mb", "color": "color"},
)

NS_SPEC = Spec(
    name="gadget",
    path="configs/conf-gadgets",
    help="Gadgets.",
    namespaced=True,
    verbs=("list", "get"),
)


def test_create_maps_keys_scale_multi_and_set(client_for):
    seen: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["method"] = req.method
        seen["path"] = req.url.path
        seen["body"] = req.content.decode()
        return httpx.Response(201, json={"entry": [{"name": "w1", "content": {}}]})

    CrudResource(GLOBAL_SPEC).create(
        client_for(handler),
        "w1",
        fields={"size_gb": 2, "tag": ("a", "b"), "color": "red"},
        sets=("extra=1",),
    )
    body = seen["body"]
    assert seen["method"] == "POST"
    assert seen["path"] == "/services/data/widgets"
    assert "name=w1" in body
    assert "sizeMB=2048" in body  # scale: GB -> MB
    assert "tags=a" in body and "tags=b" in body  # multi -> repeated key
    assert "color=red" in body
    assert "extra=1" in body  # --set passthrough


def test_out_map_renames_and_drops_unmapped(client_for):
    body = {
        "entry": [{"name": "w1", "content": {"sizeMB": 1024, "color": "blue", "junk": "x"}}],
        "paging": {"total": 1},
    }
    rows = CrudResource(GLOBAL_SPEC).list(client_for(lambda req: httpx.Response(200, json=body)))
    assert rows[0] == {"size_mb": 1024, "color": "blue", "name": "w1"}  # 'junk' dropped


def test_namespaced_base_builds_servicesns(client_for):
    seen: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["path"] = req.url.path
        return httpx.Response(200, json={"entry": [], "paging": {"total": 0}})

    CrudResource(NS_SPEC).list(client_for(handler), owner="nobody", app="my_app")
    assert seen["path"] == "/servicesNS/nobody/my_app/configs/conf-gadgets"


def test_get_missing_raises_notfound(client_for):
    with pytest.raises(NotFoundError):
        CrudResource(GLOBAL_SPEC).get(
            client_for(lambda req: httpx.Response(200, json={"entry": []})), "nope"
        )
