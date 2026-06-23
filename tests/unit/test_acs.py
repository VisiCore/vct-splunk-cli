"""Tests for the minimal read-only ACS slice.

Cloud certification is deferred (no live canary), so these use a mocked transport
rather than recorded cassettes; confidence is capped accordingly. The spec-pinned
test ensures the client never calls an ACS path the vendored OpenAPI subset does
not declare.
"""

from __future__ import annotations

import httpx
import pytest
from click.testing import CliRunner

from vct_splunk.cli import cli
from vct_splunk.core import backends
from vct_splunk.core.acs import operations, pinned_spec
from vct_splunk.core.acs.client import AcsClient, AcsConfig, acs_config_from_env
from vct_splunk.core.errors import AuthError, UsageError


def _acs(handler) -> AcsClient:
    return AcsClient(AcsConfig(stack="s", token="T"), transport=httpx.MockTransport(handler))


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


def test_active_backend_defaults_to_enterprise(monkeypatch):
    monkeypatch.delenv("SPLUNK_BACKEND", raising=False)
    assert backends.active_backend() == "enterprise"
    assert backends.active_backend("cloud") == "cloud"
    assert backends.active_backend("bogus") == "enterprise"  # unknown falls back safely


def test_inspect_command_reports_backend(monkeypatch):
    monkeypatch.delenv("SPLUNK_BACKEND", raising=False)
    result = CliRunner().invoke(cli, ["inspect", "--backend", "cloud", "--output", "json"])
    assert result.exit_code == 0
    assert '"backend": "cloud"' in result.output
    assert "not yet certified" in result.output  # capped-confidence note


def test_cloud_indexes_command_lists(monkeypatch):
    monkeypatch.setenv("SPLUNK_ACS_STACK", "mystack")
    monkeypatch.setenv("SPLUNK_ACS_TOKEN", "T")

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"name": "main"}])

    monkeypatch.setattr(
        "vct_splunk.commands.cloud.AcsClient",
        lambda config: AcsClient(config, transport=httpx.MockTransport(handler)),
    )
    result = CliRunner().invoke(cli, ["cloud", "indexes", "--output", "json"])
    assert result.exit_code == 0
    assert "main" in result.output


def test_cloud_command_requires_acs_creds(monkeypatch):
    monkeypatch.delenv("SPLUNK_ACS_STACK", raising=False)
    monkeypatch.delenv("SPLUNK_ACS_TOKEN", raising=False)
    result = CliRunner().invoke(cli, ["cloud", "roles", "--output", "json"])
    assert result.exit_code == 2  # UsageError: no stack/token
    assert "usage_error" in result.output
