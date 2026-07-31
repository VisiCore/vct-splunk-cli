"""Apply every canonical Enterprise mutation against a disposable Splunk."""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass

import pytest

from cli_catalog import CATALOG, Case
from vct_splunk.commands.registry import INDEX, REGISTRY, SAVED_SEARCH

pytestmark = [pytest.mark.integration, pytest.mark.enterprise, pytest.mark.write]

WRITE_CASES = tuple(
    case for case in CATALOG if case.kind == "write" and case.path != ("server", "restart")
)
RESTART_CASE = next(case for case in CATALOG if case.path == ("server", "restart"))
GENERATED_WRITES = {
    (spec.name, verb)
    for spec in (INDEX, SAVED_SEARCH, *REGISTRY)
    for verb in spec.verbs
    if verb not in {"list", "get"} and spec.name != "app"
}


@dataclass(frozen=True)
class ResourcePlan:
    """Valid creation and update arguments for one generated resource."""

    name: str
    create: tuple[str, ...] = ()
    update: tuple[str, ...] = ("--set", "disabled=false")
    namespaced: bool = False
    owner: str = "nobody"


def _name(prefix: str) -> str:
    return f"vct_ci_{prefix}_{uuid.uuid4().hex[:8]}"


def _server_fixture(name: str) -> str:
    root = os.environ.get("SPLUNK_TEST_SERVER_FIXTURE_DIR")
    assert root, "SPLUNK_TEST_SERVER_FIXTURE_DIR is required for write tests"
    return f"{root.rstrip('/')}/{name}"


def _plan(resource: str) -> ResourcePlan:
    unique = _name(resource.replace("-", "_"))
    root_object = {
        "objectName": "Root",
        "displayName": "Root",
        "parentName": "BaseEvent",
        "fields": [],
        "calculations": [],
        "constraints": [{"search": "index=_internal", "owner": "Root"}],
    }
    model = json.dumps({"modelName": unique, "displayName": unique, "objects": [root_object]})
    updated_model = json.dumps(
        {
            "modelName": unique,
            "displayName": f"{unique} updated",
            "objects": [root_object],
        }
    )
    plans = {
        "index": ResourcePlan(unique, ("--max-gb", "1"), ("--frozen-secs", "604800")),
        "saved-search": ResourcePlan(
            unique,
            ("--search", "index=_internal | head 1"),
            ("--description", "updated by vct-splunk-cli"),
            True,
        ),
        "user": ResourcePlan(unique, ("--set", "roles=user"), ("--set", "realname=VCT CI")),
        "role": ResourcePlan(
            unique,
            ("--set", "imported_roles=user"),
            ("--set", "imported_roles=power"),
        ),
        "monitor-input": ResourcePlan(
            _server_fixture("input.txt"),
            ("--set", "index=_internal"),
            ("--set", "sourcetype=vct_ci"),
        ),
        "tcp-input": ResourcePlan(
            str(20000 + int(uuid.uuid4().hex[:4], 16) % 20000),
            (),
            ("--set", "connection_host=ip"),
        ),
        "udp-input": ResourcePlan(
            str(40000 + int(uuid.uuid4().hex[:4], 16) % 20000),
            (),
            ("--set", "connection_host=ip"),
        ),
        "script-input": ResourcePlan(
            "/opt/splunk/etc/apps/search/bin/vct_test_input.sh",
            ("--set", "interval=300", "--set", "index=_internal"),
            ("--set", "sourcetype=vct_ci"),
        ),
        "hec-token": ResourcePlan(unique, (), ("--set", "description=updated by CI")),
        "output-server": ResourcePlan(
            f"127.0.0.1:{20000 + int(uuid.uuid4().hex[:4], 16) % 20000}",
            (),
            ("--set", "compressed=true"),
        ),
        "output-group": ResourcePlan(
            unique,
            ("--set", "servers=127.0.0.1:9997"),
            ("--set", "servers=127.0.0.1:9998"),
        ),
        "macro": ResourcePlan(
            unique,
            ("--set", "definition=search index=_internal"),
            ("--set", "definition=search index=_internal | head 1"),
            True,
        ),
        "eventtype": ResourcePlan(
            unique,
            ("--set", "search=index=_internal"),
            ("--set", "search=index=_internal sourcetype=splunkd"),
            True,
        ),
        "extraction": ResourcePlan(
            unique,
            ("--set", "REGEX=(?<vct_ci>.*)", "--set", "FORMAT=vct_ci::$1"),
            ("--set", "REGEX=(?<vct_ci>.*)", "--set", "FORMAT=vct_ci_updated::$1"),
            True,
        ),
        "lookup-definition": ResourcePlan(
            unique,
            ("--set", "filename=vct_ci_lookup.csv"),
            ("--set", "filename=vct_ci_lookup.csv", "--set", "case_sensitive_match=false"),
            True,
            "admin",
        ),
        "tag": ResourcePlan(
            f"host={unique}",
            ("--set", "tag.vct_ci=enabled"),
            ("--set", "tag.vct_ci=disabled"),
            True,
        ),
        "datamodel": ResourcePlan(
            unique,
            ("--set", f"description={model}"),
            ("--set", f"description={updated_model}"),
            True,
        ),
        "kvstore-collection": ResourcePlan(
            unique,
            ("--set", "field.value=string"),
            ("--set", "field.count=number"),
            True,
        ),
        "message": ResourcePlan(unique, ("--set", "value=vct-splunk-cli CI message")),
    }
    return plans[resource]


def _namespace(plan: ResourcePlan) -> tuple[str, ...]:
    return ("--app", "search", "--owner", plan.owner) if plan.namespaced else ()


def _create(harness, resource: str, plan: ResourcePlan) -> None:
    harness.write(resource, "create", plan.name, *plan.create, *_namespace(plan))


def _generated(case: Case, harness) -> None:
    resource, verb = case.path
    plan = _plan(resource)
    if verb != "create":
        _create(harness, resource, plan)
    if verb not in {"create", "delete"}:
        harness.cleanup(
            f"delete {resource} {plan.name}",
            resource,
            "delete",
            plan.name,
            *_namespace(plan),
        )
    args = plan.create if verb == "create" else plan.update if verb == "update" else ()
    harness.write(resource, verb, plan.name, *args, *_namespace(plan))
    if verb == "disable":
        harness.cleanup(
            f"re-enable {resource} {plan.name}",
            resource,
            "enable",
            plan.name,
            *_namespace(plan),
        )
    if verb == "create":
        harness.cleanup(
            f"delete {resource} {plan.name}",
            resource,
            "delete",
            plan.name,
            *_namespace(plan),
        )


def _install_app(harness, *, cleanup: bool = True) -> str:
    archive = _server_fixture("vct_ci_app.spl")
    data = harness.write("app", "install", "--server-file", archive)
    app_name = str(data.get("name") or "vct_ci_app")
    if cleanup:
        harness.cleanup(f"delete app {app_name}", "app", "delete", app_name)
    return app_name


def _app(case: Case, harness) -> None:
    verb = case.path[-1]
    if verb == "install":
        _install_app(harness)
        return
    name = _install_app(harness, cleanup=verb != "delete")
    harness.write("app", verb, name)


def _special(case: Case, harness) -> None:
    path = case.path
    if path[0] == "app":
        _app(case, harness)
    elif path == ("datamodel", "accelerate"):
        plan = _plan("datamodel")
        _create(harness, "datamodel", plan)
        harness.cleanup(
            f"delete datamodel {plan.name}",
            "datamodel",
            "delete",
            plan.name,
            *_namespace(plan),
        )
        harness.write(*path, plan.name, "--app", "search")
    elif path == ("deploy-server", "reload"):
        harness.write(*path)
    elif path[:2] == ("deploy-server", "serverclass"):
        name = _name("serverclass")
        if path[-1] == "update":
            harness.write(
                "deploy-server",
                "serverclass",
                "create",
                name,
                "--set",
                "whitelist.0=*",
            )
        harness.write(*path, name, "--set", "whitelist.0=*")
    elif path in {("hec", "global-disable"), ("hec", "global-enable")}:
        current = harness.run("api", "get", "/services/data/inputs/http/http")
        disabled = str(current.get("disabled", "0")).lower() in {"1", "true"}
        restore = ("hec", "global-disable") if disabled else ("hec", "global-enable")
        harness.cleanup("restore HEC global state", *restore)
        harness.write(*path)
    elif path == ("hec", "rotate"):
        plan = _plan("hec-token")
        _create(harness, "hec-token", plan)
        harness.cleanup(f"delete HEC token {plan.name}", "hec-token", "delete", plan.name)
        rotated = harness.write(*path, plan.name)
        assert rotated["token"]
    elif path[0] == "kvstore":
        plan = _plan("kvstore-collection")
        _create(harness, "kvstore-collection", plan)
        harness.cleanup(
            f"delete KV collection {plan.name}",
            "kvstore-collection",
            "delete",
            plan.name,
            *_namespace(plan),
        )
        inserted = harness.write(
            "kvstore",
            "insert",
            plan.name,
            "--data",
            '{"value":"before"}',
            "--app",
            "search",
        )
        key = str(inserted.get("_key") or inserted.get("key"))
        if path[-1] == "insert":
            return
        if path[-1] == "update":
            harness.write(*path, plan.name, key, "--data", '{"value":"after"}', "--app", "search")
        elif path[-1] == "delete":
            harness.write(*path, plan.name, key, "--app", "search")
        else:
            harness.write(*path, plan.name, "--app", "search")
    elif path == ("lookup", "upload"):
        app_name = _install_app(harness)
        harness.write(
            *path,
            "--server-file",
            _server_fixture("vct_ci_lookup.csv"),
            "--app",
            app_name,
        )
    elif path == ("saved-search", "run"):
        plan = _plan("saved-search")
        _create(harness, "saved-search", plan)
        harness.cleanup(
            f"delete saved search {plan.name}",
            "saved-search",
            "delete",
            plan.name,
            *_namespace(plan),
        )
        harness.write(*path, plan.name, "--app", "search", "--earliest", "-15m")
    elif path == ("search", "cancel"):
        plan = _plan("saved-search")
        _create(harness, "saved-search", plan)
        harness.cleanup(
            f"delete saved search {plan.name}",
            "saved-search",
            "delete",
            plan.name,
            *_namespace(plan),
        )
        job = harness.write("saved-search", "run", plan.name, "--app", "search")
        harness.write(*path, str(job["sid"]))
    elif path == ("server", "settings", "set"):
        current = harness.run("server", "settings", "get")
        old_name = str(current.get("serverName") or current.get("server_name"))
        assert old_name
        harness.cleanup("restore server name", *path, "--set", f"serverName={old_name}")
        harness.write(*path, "--set", f"serverName={_name('server')}")
    elif path == ("server", "restart"):
        harness.write(*path)
        saw_disconnect = False
        for _ in range(90):
            time.sleep(2)
            result = harness.runner.invoke(
                __import__("vct_splunk.cli", fromlist=["cli"]).cli,
                ["server", "info", "--output", "json"],
            )
            if result.exit_code != 0:
                saw_disconnect = True
            elif saw_disconnect:
                return
        if not saw_disconnect:
            pytest.fail("splunkd did not disconnect after restart", pytrace=False)
        pytest.fail("splunkd did not reconnect within 180 seconds", pytrace=False)
    else:
        raise AssertionError(f"missing live write handler for {' '.join(path)}")


@pytest.mark.parametrize("case", WRITE_CASES, ids=lambda case: " ".join(case.path))
def test_write_leaf(case: Case, enterprise_cli, monkeypatch) -> None:
    """Apply one catalogued mutation and restore its state through the CLI."""
    monkeypatch.setenv("SPLUNK_USER_PASSWORD", "Vct-CI-User-Pass-123!")
    if case.path in GENERATED_WRITES:
        _generated(case, enterprise_cli)
    else:
        _special(case, enterprise_cli)


def test_restart_reconnect(enterprise_cli, monkeypatch) -> None:
    """Restart only after ordinary mutations have completed and cleaned up."""
    monkeypatch.setenv("SPLUNK_USER_PASSWORD", "Vct-CI-User-Pass-123!")
    _special(RESTART_CASE, enterprise_cli)
