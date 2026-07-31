"""Tests for the transparent Cloud/Enterprise backend + the read-only ACS slice.

The backend is deduced from SPLUNK_URL (a ``*.splunkcloud.com`` host is Cloud);
the user sees one flat command surface. Cloud certification is deferred (no live
canary), so these use a mocked transport rather than recorded cassettes. The
public-spec test verifies the operation declarations against Splunk's OpenAPI.
"""

from __future__ import annotations

import json

import httpx
import pytest
from click.testing import CliRunner

from vct_splunk.cli import cli
from vct_splunk.core import backends
from vct_splunk.core.acs import operations
from vct_splunk.core.acs.client import AcsClient, AcsConfig, acs_config_from_env
from vct_splunk.core.client import ClientConfig, SplunkClient
from vct_splunk.core.errors import (
    APIError,
    AuthError,
    NotFoundError,
    TransportError,
    UsageError,
)

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


def test_acs_read_paths_match_list_declarations():
    assert tuple(operations.LIST_ENVELOPES) == operations.READ_PATHS


def test_list_cloud_indexes_hits_indexes_path():
    seen: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["path"] = req.url.path
        return httpx.Response(200, json={"indexes": [{"name": "main"}, {"name": "audit"}]})

    result = operations.list_cloud_indexes(_acs(handler))
    assert seen["path"].endswith("/adminconfig/v2/indexes")
    assert [i["name"] for i in result] == ["main", "audit"]


def test_acs_list_paginates_with_count_and_offset():
    offsets: list[int] = []

    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.params["count"] == "100"
        offset = int(req.url.params["offset"])
        offsets.append(offset)
        size = 100 if offset == 0 else 2
        return httpx.Response(
            200, json={"roles": [{"name": f"role-{offset + i}"} for i in range(size)]}
        )

    result = operations.list_cloud_roles(_acs(handler))

    assert offsets == [0, 100]
    assert len(result) == 102


@pytest.mark.parametrize("body", [{}, {"roles": {}}, {"roles": ["bad"]}])
def test_acs_rejects_missing_or_malformed_envelope(body):
    with pytest.raises(APIError):
        operations.list_cloud_roles(_acs(lambda req: httpx.Response(200, json=body)))


def test_acs_hec_tokens_are_removed_at_operation_boundary():
    result = operations.list_hec_tokens(
        _acs(
            lambda req: httpx.Response(
                200,
                json={
                    "http_event_collectors": [
                        {"spec": {"name": "one"}, "token": "secret"},
                        {"spec": {"name": "two", "token": "nested-secret"}},
                    ]
                },
            )
        )
    )

    assert result == [{"spec": {"name": "one"}}, {"spec": {"name": "two"}}]
    assert "secret" not in json.dumps(result)


@pytest.mark.parametrize("status", [401, 403])
def test_acs_auth_error_maps_typed(status):
    with pytest.raises(AuthError):
        operations.list_cloud_roles(_acs(lambda req: httpx.Response(status, json={})))


def test_acs_404_maps_not_found():
    with pytest.raises(NotFoundError):
        operations.list_cloud_roles(_acs(lambda req: httpx.Response(404, json={})))


def test_acs_5xx_maps_api_error(monkeypatch):
    monkeypatch.setattr("vct_splunk.core.acs.client.time.sleep", lambda delay: None)
    with pytest.raises(APIError):
        operations.list_cloud_roles(_acs(lambda req: httpx.Response(500, json={})))


def test_acs_malformed_json_maps_api_error():
    with pytest.raises(APIError, match="malformed JSON"):
        operations.list_cloud_roles(_acs(lambda req: httpx.Response(200, content=b"{not-json")))


@pytest.mark.parametrize("status", [429, 500, 501, 502, 503, 504])
def test_acs_retries_bounded_statuses(monkeypatch, status):
    calls = 0
    sleeps: list[float] = []

    def handler(req: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls < 3:
            return httpx.Response(status, headers={"Retry-After": "7"}, json={})
        return httpx.Response(200, json={"roles": []})

    monkeypatch.setattr("vct_splunk.core.acs.client.time.sleep", sleeps.append)
    assert operations.list_cloud_roles(_acs(handler)) == []
    assert calls == 3
    assert sleeps == [7.0, 7.0]


def test_acs_unreachable_maps_transport_error():
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    with pytest.raises(TransportError):
        operations.list_cloud_roles(_acs(handler))


def test_acs_config_requires_stack(monkeypatch):
    monkeypatch.delenv("SPLUNK_ACS_STACK", raising=False)
    monkeypatch.delenv("SPLUNK_ACS_TOKEN", raising=False)
    with pytest.raises(UsageError, match="stack"):
        acs_config_from_env()


def test_acs_config_requires_token(monkeypatch):
    # Stack resolved but no token: the error must name SPLUNK_ACS_TOKEN.
    monkeypatch.delenv("SPLUNK_ACS_TOKEN", raising=False)
    with pytest.raises(UsageError, match="SPLUNK_ACS_TOKEN"):
        acs_config_from_env("acme")


@pytest.mark.parametrize("stack", ["../other", "a/b", ".hidden", "two words", ""])
def test_acs_config_rejects_invalid_stack(monkeypatch, stack):
    monkeypatch.setenv("SPLUNK_ACS_TOKEN", "T")
    monkeypatch.setenv("SPLUNK_ACS_STACK", stack)
    with pytest.raises(UsageError, match="stack"):
        acs_config_from_env()


def test_acs_config_supports_base_url_override(monkeypatch):
    monkeypatch.setenv("SPLUNK_ACS_TOKEN", "T")
    monkeypatch.setenv("SPLUNK_ACS_BASE_URL", "https://admin.splunkcloudgc.com/")

    config = acs_config_from_env("fed-stack")

    assert config.base_url == "https://admin.splunkcloudgc.com"


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
        envelope = {
            "indexes": "indexes",
            "roles": "roles",
            "http-event-collectors": "http_event_collectors",
        }[req.url.path.rsplit("/", 1)[-1]]
        return httpx.Response(200, json={envelope: [{"name": "main"}]})

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


def test_factory_write_on_cloud_stops_too(monkeypatch):
    # The Cloud write guard sits in the shared write path, so every generated
    # group refuses as well — not just index.
    monkeypatch.setenv("SPLUNK_URL", CLOUD_URL)
    monkeypatch.setenv("SPLUNK_APP", "my_app")
    result = CliRunner().invoke(
        cli, ["macro", "create", "m1", "--set", "definition=x", "--yes", "--output", "json"]
    )
    assert result.exit_code == 4
    assert "unsupported_backend" in result.output


# --- `inspect` reports the deduced backend (no --backend selector) -----------


def test_inspect_reports_deduced_cloud(monkeypatch):
    monkeypatch.setenv("SPLUNK_URL", CLOUD_URL)
    result = CliRunner().invoke(cli, ["inspect", "--output", "json"])
    assert result.exit_code == 0
    assert '"backend": "cloud"' in result.output
    assert '"stack": "acme"' in result.output
    assert "not yet certified" in result.output


def test_inspect_reports_enterprise_capabilities(monkeypatch):
    monkeypatch.setenv("SPLUNK_URL", ENTERPRISE_URL)
    result = CliRunner().invoke(cli, ["inspect", "--output", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)["data"]
    assert data["backend"] == "enterprise"
    assert data["capabilities"]["search"] is True  # full support, no caveat string
