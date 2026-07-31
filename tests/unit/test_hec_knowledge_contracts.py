"""Exact wire contracts for HEC and hand-written knowledge-object operations."""

from __future__ import annotations

from urllib.parse import parse_qs

import httpx
import pytest
from click.testing import CliRunner

from vct_splunk.cli import cli
from vct_splunk.core.errors import APIError
from vct_splunk.core.hec import rotate_token


def test_hec_rotate_exact_contract_and_official_response(cli_env, patch_client):
    seen: dict[str, object] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen.update(
            method=req.method,
            path=req.url.raw_path.decode().partition("?")[0],
            form=parse_qs(req.content.decode()),
        )
        return httpx.Response(
            200, json={"entry": [{"name": "east west", "content": {"token": "new-secret"}}]}
        )

    patch_client(handler)
    result = CliRunner().invoke(cli, ["hec", "rotate", "east west", "--yes", "--output", "json"])

    assert result.exit_code == 0
    assert '"token": "new-secret"' in result.output
    assert seen == {
        "method": "POST",
        "path": "/services/data/inputs/http/east%20west/rotate",
        "form": {},
    }


def test_hec_rotate_requires_token_in_response(client_for):
    client = client_for(lambda req: httpx.Response(200, json={"entry": [{"content": {}}]}))

    with pytest.raises(APIError, match="did not contain a new token"):
        rotate_token(client, "token")


@pytest.mark.parametrize("name", ["..", "a/b", "a\\b", "%252fetc", "a\nb"])
@pytest.mark.parametrize("command", ["hec", "datamodel"])
def test_dynamic_names_refuse_traversal_before_request(cli_env, patch_client, name, command):
    requests: list[httpx.Request] = []
    patch_client(lambda req: requests.append(req) or httpx.Response(200, json={}))
    argv = (
        ["hec", "rotate", name, "--yes", "--output", "json"]
        if command == "hec"
        else [
            "datamodel",
            "accelerate",
            name,
            "--app",
            "a",
            "--yes",
            "--output",
            "json",
        ]
    )

    result = CliRunner().invoke(cli, argv)

    assert result.exit_code == 2
    assert requests == []


def test_datamodel_accelerate_encodes_name_and_sends_exact_body(cli_env, patch_client):
    seen: list[dict[str, object]] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(
            {
                "method": req.method,
                "path": req.url.raw_path.decode().partition("?")[0],
                "form": parse_qs(req.content.decode()),
            }
        )
        if req.method == "GET":
            return httpx.Response(
                200,
                json={
                    "entry": [
                        {
                            "name": "Auth Model",
                            "content": {
                                "acceleration": (
                                    '{"enabled":false,"earliest_time":"-30d",'
                                    '"cron_schedule":"15 * * * *"}'
                                )
                            },
                        }
                    ]
                },
            )
        return httpx.Response(200, json={"entry": []})

    patch_client(handler)
    result = CliRunner().invoke(
        cli,
        [
            "datamodel",
            "accelerate",
            "Auth Model",
            "--app",
            "search",
            "--yes",
            "--output",
            "json",
        ],
    )

    assert result.exit_code == 0
    assert seen == [
        {
            "method": "GET",
            "path": "/servicesNS/nobody/search/datamodel/model/Auth%20Model",
            "form": {},
        },
        {
            "method": "POST",
            "path": "/servicesNS/nobody/search/datamodel/model/Auth%20Model",
            "form": {
                "acceleration": [
                    '{"enabled":true,"earliest_time":"-30d","cron_schedule":"15 * * * *"}'
                ]
            },
        },
    ]


def test_datamodel_accelerate_refuses_malformed_current_settings(cli_env, patch_client):
    requests: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        requests.append(req)
        return httpx.Response(
            200,
            json={"entry": [{"name": "model", "content": {"acceleration": "not-json"}}]},
        )

    patch_client(handler)
    result = CliRunner().invoke(
        cli,
        ["datamodel", "accelerate", "model", "--app", "search", "--yes", "--output", "json"],
    )

    assert result.exit_code == 1
    assert [request.method for request in requests] == ["GET"]
    assert "malformed acceleration settings" in result.output


def test_lookup_upload_sends_server_staging_path(cli_env, patch_client):
    seen: dict[str, object] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen.update(
            method=req.method,
            path=req.url.path,
            form=parse_qs(req.content.decode()),
        )
        return httpx.Response(201, json={"entry": [{"name": "table.csv", "content": {}}]})

    patch_client(handler)
    result = CliRunner().invoke(
        cli,
        [
            "lookup",
            "upload",
            "--server-file",
            "/var/tmp/staged/table.csv",
            "--app",
            "search",
            "--yes",
            "--output",
            "json",
        ],
    )

    assert result.exit_code == 0
    assert seen == {
        "method": "POST",
        "path": "/servicesNS/nobody/search/data/lookup-table-files",
        "form": {"name": ["table.csv"], "eai:data": ["/var/tmp/staged/table.csv"]},
    }


def test_lookup_help_exposes_only_server_file():
    result = CliRunner().invoke(cli, ["lookup", "upload", "--help"])

    assert result.exit_code == 0
    assert "--server-file" in result.output
    assert "--file " not in result.output
    assert "readable by splunkd" in result.output
