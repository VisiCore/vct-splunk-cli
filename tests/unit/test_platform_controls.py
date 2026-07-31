"""Exact platform-control contracts and normalization."""

from __future__ import annotations

import json

import httpx
import pytest
from click.testing import CliRunner

from vct_splunk.cli import cli
from vct_splunk.core.errors import UsageError
from vct_splunk.core.parsing import parse_key_value_pairs


def test_cluster_status_uses_manager_info(cli_env, patch_client):
    seen: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req.url.path)
        return httpx.Response(
            200,
            json={
                "entry": [
                    {
                        "content": {
                            "label": "cluster-one",
                            "replication_factor": 3,
                            "search_factor": 2,
                            "indexing_ready_flag": True,
                            "maintenance_mode": False,
                        }
                    }
                ]
            },
        )

    patch_client(handler)
    result = CliRunner().invoke(cli, ["cluster", "status", "--output", "json"])

    assert result.exit_code == 0
    assert seen == ["/services/cluster/manager/info"]
    assert json.loads(result.output)["data"] == {
        "configured": True,
        "label": "cluster-one",
        "replication_factor": 3,
        "search_factor": 2,
        "indexing_ready": True,
        "maintenance_mode": False,
    }


@pytest.mark.parametrize("status", [200, 404, 503])
def test_cluster_status_normalizes_standalone(cli_env, patch_client, status):
    patch_client(
        lambda req: (
            httpx.Response(status, json={"entry": []})
            if status == 200
            else httpx.Response(
                status,
                json={
                    "messages": [
                        {"type": "ERROR", "text": "Cluster manager is not enabled on this node"}
                    ]
                },
            )
        )
    )
    result = CliRunner().invoke(cli, ["cluster", "status", "--output", "json"])

    assert result.exit_code == 0
    assert json.loads(result.output)["data"] == {"configured": False}


def test_cluster_status_reraises_non_503_errors(cli_env, patch_client):
    """A "not enabled" phrase in a non-503 body is not proof of a standalone node."""
    patch_client(
        lambda req: httpx.Response(
            500,
            json={"messages": [{"type": "ERROR", "text": "Cluster manager is not enabled"}]},
        )
    )
    result = CliRunner().invoke(cli, ["cluster", "status", "--output", "json"])

    assert result.exit_code == 1


def test_shcluster_status_uses_status_endpoint(cli_env, patch_client):
    seen: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req.url.path)
        return httpx.Response(
            200,
            json={
                "entry": [
                    {
                        "content": {
                            "captain": {"label": "sh1"},
                            "members": {"guid-1": {"status": "Up"}},
                        }
                    }
                ]
            },
        )

    patch_client(handler)
    result = CliRunner().invoke(cli, ["shcluster", "status", "--output", "json"])

    assert result.exit_code == 0
    assert seen == ["/services/shcluster/status"]
    assert json.loads(result.output)["data"] == {
        "configured": True,
        "captain": {"label": "sh1"},
        "members": {"guid-1": {"status": "Up"}},
    }


@pytest.mark.parametrize("status", [200, 404, 503])
def test_shcluster_status_normalizes_standalone(cli_env, patch_client, status):
    patch_client(
        lambda req: (
            httpx.Response(status, json={"entry": []})
            if status == 200
            else httpx.Response(
                status,
                json={
                    "messages": [
                        {
                            "type": "ERROR",
                            "text": "Search Head Clustering is not enabled on this node.",
                        }
                    ]
                },
            )
        )
    )
    result = CliRunner().invoke(cli, ["shcluster", "status", "--output", "json"])

    assert result.exit_code == 0
    assert json.loads(result.output)["data"] == {"configured": False}


def test_license_usage_uses_documented_fields(cli_env, patch_client):
    patch_client(
        lambda req: httpx.Response(
            200,
            json={
                "entry": [
                    {
                        "name": "pool-one",
                        "content": {
                            "stack_id": "enterprise",
                            "effective_quota": 1000,
                            "quota": 9999,
                            "used_bytes": 250,
                        },
                    },
                    {"name": "pool-two", "content": {}},
                ]
            },
        )
    )
    result = CliRunner().invoke(cli, ["license", "usage", "--output", "json"])

    assert result.exit_code == 0
    assert json.loads(result.output)["data"] == [
        {
            "name": "pool-one",
            "stack_id": "enterprise",
            "quota_bytes": 1000,
            "used_bytes": 250,
        },
        {
            "name": "pool-two",
            "stack_id": None,
            "quota_bytes": None,
            "used_bytes": None,
        },
    ]


@pytest.mark.parametrize(
    ("pairs", "message"),
    [
        (["broken"], "Expected KEY=VALUE"),
        (["=value"], "non-empty key"),
        (["host=one", "host=two"], "Duplicate key"),
    ],
)
def test_key_value_parser_rejects_invalid_pairs(pairs, message):
    with pytest.raises(UsageError, match=message):
        parse_key_value_pairs(pairs)


def test_key_value_parser_preserves_explicit_empty_value():
    assert parse_key_value_pairs(["host="]) == {"host": ""}


def test_server_settings_set_rejects_invalid_pairs_before_request(cli_env, patch_client):
    def handler(req: httpx.Request) -> httpx.Response:
        raise AssertionError("invalid settings must not send a request")

    patch_client(handler)
    result = CliRunner().invoke(
        cli,
        [
            "server",
            "settings",
            "set",
            "--set",
            "host=one",
            "--set",
            "host=two",
            "--yes",
            "--output",
            "json",
        ],
    )

    assert result.exit_code == 2
    assert "Duplicate key" in result.output


def test_server_settings_get_redacts_secrets(cli_env, patch_client):
    patch_client(
        lambda req: httpx.Response(
            200,
            json={
                "entry": [
                    {
                        "content": {
                            "host": "sh1",
                            "pass4SymmKey": "top-secret",
                            "sslKeysfilePassword": "also-secret",
                        }
                    }
                ]
            },
        )
    )
    result = CliRunner().invoke(cli, ["server", "settings", "get", "--output", "json"])

    assert result.exit_code == 0
    assert "top-secret" not in result.output
    assert "also-secret" not in result.output
    assert json.loads(result.output)["data"] == {
        "host": "sh1",
        "pass4SymmKey": "<redacted>",
        "sslKeysfilePassword": "<redacted>",
    }


def test_server_settings_dry_run_redacts_secret_values(cli_env):
    result = CliRunner().invoke(
        cli,
        [
            "server",
            "settings",
            "set",
            "--set",
            "pass4SymmKey=top-secret",
            "--dry-run",
            "--output",
            "json",
        ],
    )

    assert result.exit_code == 0
    assert "top-secret" not in result.output
    assert json.loads(result.output)["data"]["request"]["body"]["pass4SymmKey"] == "<redacted>"


def test_server_settings_set_redacts_success_response(cli_env, patch_client):
    def handler(req: httpx.Request) -> httpx.Response:
        assert req.method == "POST"
        assert req.url.path == "/services/server/settings/settings"
        assert req.content.decode() == "host=sh1"
        return httpx.Response(
            200,
            json={"entry": [{"content": {"host": "sh1", "pass4SymmKey": "top-secret"}}]},
        )

    patch_client(handler)
    result = CliRunner().invoke(
        cli,
        [
            "server",
            "settings",
            "set",
            "--set",
            "host=sh1",
            "--yes",
            "--output",
            "json",
        ],
    )

    assert result.exit_code == 0
    assert "top-secret" not in result.output
    assert json.loads(result.output)["data"]["pass4SymmKey"] == "<redacted>"


def test_server_settings_set_redacts_api_error_details(cli_env, patch_client):
    patch_client(
        lambda req: httpx.Response(
            500,
            json={
                "messages": [{"type": "ERROR", "text": "rejected"}],
                "pass4SymmKey": "top-secret",
            },
        )
    )
    result = CliRunner().invoke(
        cli,
        [
            "server",
            "settings",
            "set",
            "--set",
            "host=sh1",
            "--yes",
            "--output",
            "json",
        ],
    )

    assert result.exit_code == 1
    assert "top-secret" not in result.output
    assert "<redacted>" in result.output
