"""Engine tests for the CRUD factory.

These test the generic CrudResource once over two contrived specs (a global one
and a namespaced one), which covers every registry resource forever -- adding a
Spec adds no test burden.
"""

from __future__ import annotations

import httpx
import pytest

from vct_splunk.commands.registry import INDEX, REGISTRY, SAVED_SEARCH
from vct_splunk.core.errors import NotFoundError, UsageError
from vct_splunk.core.resource import CrudResource, Field, Spec

GLOBAL_SPEC = Spec(
    name="widget",
    path="/services/data/widgets",
    help="Widgets.",
    fields=(
        Field("size_gb", key="sizeMB", type="float", scale=1024),
        Field("color", key="color"),
    ),
    out_map={"sizeMB": "size_mb", "color": "color"},
)

# A namespaced spec sharing GLOBAL_SPEC's `color` field, so one parametrized
# test can assert a property against both a global and a namespaced resource.
NS_SPEC = Spec(
    name="gadget",
    path="configs/conf-gadgets",
    help="Gadgets.",
    namespaced=True,
    fields=(Field("color", key="color"),),
)

PATH_SPEC = Spec(
    name="monitor",
    path="/services/data/inputs/monitor",
    help="Monitor inputs.",
    absolute_name=True,
)


def test_create_maps_keys_scale_and_set(client_for):
    seen: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["method"] = req.method
        seen["path"] = req.url.path
        seen["body"] = req.content.decode()
        return httpx.Response(201, json={"entry": [{"name": "w1", "content": {}}]})

    CrudResource(GLOBAL_SPEC).create(
        client_for(handler),
        "w1",
        fields={"size_gb": 2, "color": "red"},
        sets={"extra": "1"},
    )
    body = seen["body"]
    assert seen["method"] == "POST"
    assert seen["path"] == "/services/data/widgets"
    assert "name=w1" in body
    assert "sizeMB=2048" in body  # scale: GB -> MB
    assert "color=red" in body
    assert "extra=1" in body  # --set passthrough


def test_out_map_renames_and_drops_unmapped(client_for):
    body = {
        "entry": [{"name": "w1", "content": {"sizeMB": 1024, "color": "blue", "junk": "x"}}],
        "paging": {"total": 1},
    }
    rows = CrudResource(GLOBAL_SPEC).list(client_for(lambda req: httpx.Response(200, json=body)))
    assert rows[0] == {"size_mb": 1024, "color": "blue", "name": "w1"}  # 'junk' dropped


@pytest.mark.parametrize("spec", [GLOBAL_SPEC, NS_SPEC], ids=lambda spec: spec.name)
def test_update_never_sends_a_name(spec, client_for):
    """An update sends only changed settings; the name stays in the URL.

    Splunk merges an update server-side, and a `name` in the body would read as
    a rename. This holds for every spec, so the engine is the place to pin it.
    """
    seen: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["method"] = req.method
        seen["body"] = req.content.decode()
        return httpx.Response(200, json={"entry": [{"name": "thing", "content": {}}]})

    owner = "nobody" if spec.namespaced else None
    app = "my_app" if spec.namespaced else None
    CrudResource(spec).update(
        client_for(handler), "thing", fields={"color": "blue"}, owner=owner, app=app
    )

    assert seen["method"] == "POST"
    assert "name=" not in seen["body"]


def test_namespaced_list_surfaces_the_acl_block(client_for):
    """A namespaced row carries its app, owner, and sharing from the acl block."""
    body = {
        "entry": [
            {
                "name": "g1",
                "content": {},
                "acl": {"app": "my_app", "owner": "nobody", "sharing": "app"},
            }
        ],
        "paging": {"total": 1},
    }
    rows = CrudResource(NS_SPEC).list(
        client_for(lambda req: httpx.Response(200, json=body)), owner="-", app="-"
    )

    assert rows[0]["app"] == "my_app"
    assert rows[0]["owner"] == "nobody"
    assert rows[0]["sharing"] == "app"


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


@pytest.mark.parametrize("spec", [INDEX, SAVED_SEARCH, *REGISTRY], ids=lambda spec: spec.name)
def test_every_registry_spec_uses_the_generic_read_engine(spec, client_for):
    seen: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["method"] = req.method
        seen["path"] = req.url.path
        return httpx.Response(200, json={"entry": [], "paging": {"total": 0}})

    owner = "nobody" if spec.namespaced else None
    app = "my_app" if spec.namespaced else None
    assert CrudResource(spec).list(client_for(handler), owner=owner, app=app) == []
    expected = (
        f"/servicesNS/nobody/my_app/{spec.path.lstrip('/')}" if spec.namespaced else spec.path
    )
    assert seen == {"method": "GET", "path": expected}


@pytest.mark.parametrize("operation", ["get", "update", "delete", "control"])
def test_dynamic_name_paths_are_encoded(client_for, operation):
    seen: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["path"] = req.url.raw_path.decode().partition("?")[0]
        return httpx.Response(200, json={"entry": [{"name": "east west", "content": {}}]})

    resource = CrudResource(GLOBAL_SPEC)
    client = client_for(handler)
    if operation == "get":
        resource.get(client, "east west")
        suffix = ""
    elif operation == "update":
        resource.update(client, "east west", fields={"color": "blue"})
        suffix = ""
    elif operation == "delete":
        resource.delete(client, "east west")
        suffix = ""
    else:
        resource.control(client, "east west", "enable")
        suffix = "/enable"

    assert seen["path"] == f"/services/data/widgets/east%20west{suffix}"


def test_absolute_path_identifiers_are_validated_and_encoded(client_for):
    seen: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["path"] = req.url.raw_path.decode().partition("?")[0]
        return httpx.Response(200, json={})

    CrudResource(PATH_SPEC).delete(client_for(handler), "/var/tmp/input.log")

    assert seen["path"] == "/services/data/inputs/monitor/%2Fvar%2Ftmp%2Finput.log"


@pytest.mark.parametrize(
    ("spec", "name"),
    [
        (PATH_SPEC, "relative.log"),
        (PATH_SPEC, "/var/../etc/passwd"),
        (PATH_SPEC, "/var/%252e%252e/etc/passwd"),
    ],
)
def test_path_identifiers_refuse_wrong_shape_and_traversal(client_for, spec, name):
    requests: list[httpx.Request] = []
    resource = CrudResource(spec)
    client = client_for(lambda req: requests.append(req) or httpx.Response(200, json={}))

    with pytest.raises(UsageError):
        resource.delete(client, name)

    assert requests == []


@pytest.mark.parametrize("operation", ["get", "update", "delete", "control"])
@pytest.mark.parametrize("name", ["..", "a/b", "a\\b", "%252fetc", "a\nb"])
def test_dynamic_name_traversal_sends_no_request(client_for, operation, name):
    requests: list[httpx.Request] = []
    resource = CrudResource(GLOBAL_SPEC)
    client = client_for(lambda req: requests.append(req) or httpx.Response(200, json={"entry": []}))

    with pytest.raises(UsageError):
        if operation == "get":
            resource.get(client, name)
        elif operation == "update":
            resource.update(client, name, fields={"color": "blue"})
        elif operation == "delete":
            resource.delete(client, name)
        else:
            resource.control(client, name, "enable")

    assert requests == []
