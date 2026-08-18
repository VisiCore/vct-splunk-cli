"""Configuration endpoint and CLI coverage."""

from __future__ import annotations

import json

import httpx
import pytest
from click.testing import CliRunner

from vct_splunk.api.endpoints import config
from vct_splunk.cli import cli
from vct_splunk.utils.errors import UsageError


def _entry(name: str, content: object | None = None) -> dict[str, object]:
    return {"name": name, "content": {} if content is None else content}


def test_list_files_paginates_without_returning_unknown_content(client_for) -> None:
    seen: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.url.params))
        if request.url.params["offset"] == "0":
            entries = [_entry("props", {"token": "never-print"})] + [
                _entry(f"other-{index}") for index in range(199)
            ]
        else:
            entries = [_entry("transforms")]
        return httpx.Response(200, json={"entry": entries, "paging": {"total": 201}})

    files = config.list_files(client_for(handler), owner="-", app="-")

    assert files[0] == {"name": "props"}
    assert files[-1] == {"name": "transforms"}
    assert len(files) == 201
    assert seen == [
        {"count": "200", "offset": "0", "output_mode": "json"},
        {"count": "200", "offset": "200", "output_mode": "json"},
    ]


def test_stanza_paths_normalize_file_and_encode_dynamic_segments(client_for) -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.raw_path.decode().partition("?")[0])
        return httpx.Response(
            200,
            json={"entry": [_entry("TRANSFORMS-routing", "main")], "paging": {"total": 1}},
        )

    stanza = config.get_stanza(
        client_for(handler), "props file.conf", "host::web one", owner="nobody", app="search"
    )

    assert stanza == {"name": "host::web one", "properties": {"TRANSFORMS-routing": "main"}}
    assert seen == ["/servicesNS/nobody/search/properties/props%20file/host%3A%3Aweb%20one"]


def test_config_get_paginates_and_redacts_scalar_secret_keys(client_for) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params["offset"] == "0":
            entries = [_entry("password", "hidden")] + [
                _entry(f"other-{index}", index) for index in range(199)
            ]
        else:
            entries = [_entry("nested", {"token": "also-hidden"})]
        return httpx.Response(200, json={"entry": entries, "paging": {"total": 201}})

    result = config.get_stanza(client_for(handler), "props", "actual", owner="-", app="-")

    assert result["name"] == "actual"
    assert result["properties"]["password"] == "<redacted>"
    assert result["properties"]["nested"] == {"token": "<redacted>"}
    assert len(result["properties"]) == 201


def test_config_lists_use_the_authoritative_entry_name(client_for) -> None:
    body = {"entry": [_entry("actual", {"name": "forged", "nested": {"token": "hidden"}})]}
    result = config.list_stanzas(
        client_for(lambda request: httpx.Response(200, json=body)),
        "props",
        owner="-",
        app="-",
    )

    assert result == [{"name": "actual"}]


@pytest.mark.parametrize("file", ["", ".conf", "../props", "props/other", "%252fetc"])
def test_config_file_rejects_unsafe_paths_before_request(client_for, file: str) -> None:
    requests: list[httpx.Request] = []
    client = client_for(lambda request: requests.append(request) or httpx.Response(200, json={}))

    with pytest.raises(UsageError):
        config.list_stanzas(client, file, owner="-", app="-")

    assert requests == []


@pytest.mark.parametrize("stanza", ["", "../default", "a/b", "%252fetc"])
def test_config_stanza_rejects_unsafe_paths_before_request(client_for, stanza: str) -> None:
    requests: list[httpx.Request] = []
    client = client_for(lambda request: requests.append(request) or httpx.Response(200, json={}))

    with pytest.raises(UsageError):
        config.get_stanza(client, "props", stanza, owner="-", app="-")

    assert requests == []


def test_get_stanza_empty_response_is_an_empty_stanza(client_for) -> None:
    result = config.get_stanza(
        client_for(lambda request: httpx.Response(200, json={"entry": []})),
        "props",
        "default",
        owner="-",
        app="-",
    )

    assert result == {"name": "default", "properties": {}}


def test_config_cli_uses_read_namespace_envelope_and_redaction(cli_env, patch_client) -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        return httpx.Response(
            200,
            json={"entry": [_entry("password", "hidden")], "paging": {"total": 1}},
        )

    patch_client(handler)
    result = CliRunner().invoke(
        cli,
        [
            "config",
            "get",
            "props.conf",
            "default",
            "--owner",
            "alice",
            "--app",
            "search",
            "--output",
            "json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert seen["path"] == "/servicesNS/alice/search/properties/props/default"
    payload = json.loads(result.output)
    assert set(payload) == {"data", "meta"}
    assert payload["data"] == {"name": "default", "properties": {"password": "<redacted>"}}
    assert "hidden" not in result.output


def test_config_cli_not_found_is_a_typed_error(cli_env, patch_client) -> None:
    patch_client(lambda request: httpx.Response(404, json={"messages": []}))

    result = CliRunner().invoke(cli, ["config", "get", "props", "default", "--output", "json"])

    assert result.exit_code == 4
    payload = json.loads(result.output)
    assert payload["error"]["code"] == "not_found"
