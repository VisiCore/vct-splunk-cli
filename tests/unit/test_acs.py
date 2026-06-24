"""Tests for the transparent Cloud/Enterprise backend + the read-only ACS slice.

The backend is deduced from SPLUNK_URL (a ``*.splunkcloud.com`` host is Cloud);
the user sees one flat command surface. Cloud certification is deferred (no live
canary), so these use a mocked transport rather than recorded cassettes. The
spec-pinned test ensures the client never calls an ACS path the vendored OpenAPI
subset does not declare.
"""

from __future__ import annotations

import httpx
import pytest
from click.testing import CliRunner

from vct_splunk.cli import cli
from vct_splunk.core import backends
from vct_splunk.core.acs import operations, pinned_spec
from vct_splunk.core.acs.client import AcsClient, AcsConfig, acs_config_from_env
from vct_splunk.core.client import ClientConfig, SplunkClient
from vct_splunk.core.errors import AuthError, UsageError

CLOUD_URL = "https://acme.splunkcloud.com:8089"
ENTERPRISE_URL = "https://sh.corp:8089"


def _acs(handler) -> AcsClient:
    return AcsClient(AcsConfig(stack="s", token="T"), transport=httpx.MockTransport(handler))


def _patch_acs(monkeypatch, handler) -> None:
    """Patch Ctx.acs_client to an AcsClient backed by the given MockTransport handler."""
    monkeypatch.setattr(
        "vct_splunk.commands.context.Ctx.acs_client",
        lambda self: AcsClient(
            AcsConfig(stack="acme", token="T"), transport=httpx.MockTransport(handler)
        ),
    )


def _patch_rest(monkeypatch, handler) -> None:
    monkeypatch.setattr(
        "vct_splunk.commands.context.Ctx.client",
        lambda self: SplunkClient(
            ClientConfig(base_url=ENTERPRISE_URL, token="T"), transport=httpx.MockTransport(handler)
        ),
    )


# --- ACS client + operations (unchanged behaviour) ---------------------------


def test_acs_read_paths_are_pinned_to_the_spec():
    declared = set(pinned_spec()["paths"])
    for path in operations.READ_PATHS:
        assert f"/{path}" in declared  # never call a path the spec does not pin


def test_list_cloud_indexes_hits_indexes_path():
    seen: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["path"] = req.url.path
        return httpx.Response(200, json=[{"name": "main"}, {"name": "audit"}])

    result = operations.list_cloud_indexes(_acs(handler))
    assert seen["path"].endswith("/adminconfig/v2/indexes")
    assert [i["name"] for i in result] == ["main", "audit"]


def test_acs_auth_error_maps_typed():
    with pytest.raises(AuthError):
        operations.list_cloud_roles(_acs(lambda req: httpx.Response(401, json={})))


def test_acs_config_requires_stack_and_token(monkeypatch):
    monkeypatch.delenv("SPLUNK_ACS_STACK", raising=False)
    monkeypatch.delenv("SPLUNK_ACS_TOKEN", raising=False)
    with pytest.raises(UsageError):
        acs_config_from_env()


# --- Backend deduction from the URL ------------------------------------------


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://acme.splunkcloud.com:8089", "cloud"),
        ("https://acme.splunkcloud.com", "cloud"),
        ("acme.splunkcloud.com:8089", "cloud"),  # missing scheme still parses
        ("https://sh.internal.corp:8089", "enterprise"),
        ("https://localhost:8089", "enterprise"),
        (None, "enterprise"),
        ("", "enterprise"),
    ],
)
def test_deduce_backend(url, expected, monkeypatch):
    monkeypatch.delenv("SPLUNK_URL", raising=False)
    assert backends.deduce_backend(url) == expected


def test_cloud_stack_from_url():
    assert backends.cloud_stack_from_url("https://acme.splunkcloud.com:8089") == "acme"
    assert backends.cloud_stack_from_url("https://es-acme.splunkcloud.com") == "es-acme"
    assert backends.cloud_stack_from_url("https://sh.corp:8089") is None


# --- Flat commands route by the deduced backend ------------------------------


@pytest.mark.parametrize(
    "argv,acs_path",
    [
        (["index", "list"], "/adminconfig/v2/indexes"),
        (["role", "list"], "/adminconfig/v2/roles"),
        (["hec-token", "list"], "/adminconfig/v2/inputs/http-event-collectors"),
    ],
)
def test_flat_list_routes_to_acs_on_cloud(monkeypatch, argv, acs_path):
    monkeypatch.setenv("SPLUNK_URL", CLOUD_URL)
    monkeypatch.setenv("SPLUNK_ACS_TOKEN", "T")
    seen: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["path"] = req.url.path
        return httpx.Response(200, json=[{"name": "main"}])

    _patch_acs(monkeypatch, handler)
    result = CliRunner().invoke(cli, [*argv, "--output", "json"])
    assert result.exit_code == 0, result.output
    assert seen["path"].endswith(acs_path)
    assert "main" in result.output


def test_index_list_routes_to_rest_on_enterprise(monkeypatch):
    monkeypatch.setenv("SPLUNK_URL", ENTERPRISE_URL)
    monkeypatch.setenv("SPLUNK_TOKEN", "T")
    seen: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["path"] = req.url.path
        return httpx.Response(200, json={"entry": [{"content": {"name": "main"}}]})

    _patch_rest(monkeypatch, handler)
    result = CliRunner().invoke(cli, ["index", "list", "--output", "json"])
    assert result.exit_code == 0, result.output
    assert "/services/data/indexes" in seen["path"]


# --- Unsupported operations stop cleanly -------------------------------------


def test_write_on_cloud_stops_with_unsupported_backend(monkeypatch):
    monkeypatch.setenv("SPLUNK_URL", CLOUD_URL)
    monkeypatch.setenv("SPLUNK_ACS_TOKEN", "T")
    result = CliRunner().invoke(cli, ["index", "create", "x", "--yes", "--output", "json"])
    assert result.exit_code == 4
    assert "unsupported_backend" in result.output
    assert "Splunk Cloud" in result.output


# --- `inspect` reports the deduced backend (no --backend selector) -----------


def test_inspect_reports_deduced_cloud(monkeypatch):
    monkeypatch.setenv("SPLUNK_URL", CLOUD_URL)
    result = CliRunner().invoke(cli, ["inspect", "--output", "json"])
    assert result.exit_code == 0
    assert '"backend": "cloud"' in result.output
    assert '"stack": "acme"' in result.output
    assert "not yet certified" in result.output


def test_inspect_reports_deduced_enterprise(monkeypatch):
    monkeypatch.setenv("SPLUNK_URL", ENTERPRISE_URL)
    result = CliRunner().invoke(cli, ["inspect", "--output", "json"])
    assert result.exit_code == 0
    assert '"backend": "enterprise"' in result.output


def test_inspect_has_no_backend_selector(monkeypatch):
    monkeypatch.setenv("SPLUNK_URL", ENTERPRISE_URL)
    # The old --backend selector is gone; passing it is now an error.
    result = CliRunner().invoke(cli, ["inspect", "--backend", "cloud"])
    assert result.exit_code != 0
