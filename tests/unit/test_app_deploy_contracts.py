"""Exact app-install and deployment-server contracts."""

from __future__ import annotations

import json
from urllib.parse import parse_qs

import httpx
import pytest
from click.testing import CliRunner

from vct_splunk.cli import cli


@pytest.mark.parametrize(
    ("option", "source"),
    [
        ("--server-file", "/var/tmp/apps/example.spl"),
        ("--url", "https://downloads.example.test/apps/example.spl"),
    ],
)
def test_app_install_uses_apps_local_contract(cli_env, patch_client, option, source):
    seen: dict[str, object] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen.update(method=req.method, path=req.url.path, form=parse_qs(req.content.decode()))
        return httpx.Response(201, json={"entry": [{"name": "example", "content": {}}]})

    patch_client(handler)
    result = CliRunner().invoke(
        cli,
        ["app", "install", option, source, "--update", "--yes", "--output", "json"],
    )

    assert result.exit_code == 0
    assert seen == {
        "method": "POST",
        "path": "/services/apps/local",
        "form": {"name": [source], "update": ["true"]},
    }


def test_app_install_audit_uses_sanitized_url(cli_env, patch_client, monkeypatch, tmp_path):
    audit = tmp_path / "audit.log"
    monkeypatch.setenv("VCT_SPLUNK_AUDIT", str(audit))
    source = "https://user:password@example.test:8443/apps/example.spl?token=secret#fragment"
    seen: dict[str, list[str]] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen.update(parse_qs(req.content.decode()))
        return httpx.Response(201, json={"entry": []})

    patch_client(handler)

    result = CliRunner().invoke(
        cli, ["app", "install", "--url", source, "--yes", "--output", "json"]
    )

    assert result.exit_code == 0
    assert seen == {"name": [source]}
    record = json.loads(audit.read_text())
    assert record["source"] == "https://example.test:8443/apps/example.spl"
    assert "user" not in audit.read_text()
    assert "password" not in audit.read_text()
    assert "token" not in audit.read_text()
    assert "secret" not in audit.read_text()
    assert "fragment" not in audit.read_text()


def test_app_install_dry_run_uses_sanitized_url(cli_env, patch_client):
    source = "https://user:password@example.test:8443/apps/example.spl?token=secret#fragment"
    patch_client(
        lambda req: (_ for _ in ()).throw(AssertionError("dry-run must not send a request"))
    )

    result = CliRunner().invoke(
        cli,
        ["app", "install", "--url", source, "--dry-run", "--output", "json"],
    )

    assert result.exit_code == 0
    body = json.loads(result.output)
    assert body["data"]["request"]["body"] == {"name": "https://example.test:8443/apps/example.spl"}
    for secret in ("user", "password", "token", "secret", "fragment"):
        assert secret not in result.output


def test_app_install_help_has_no_caller_local_file_option():
    result = CliRunner().invoke(cli, ["app", "install", "--help"])

    assert result.exit_code == 0
    assert "--server-file" in result.output
    assert "--file " not in result.output
    assert "readable by splunkd" in result.output


@pytest.mark.parametrize("source", ["ftp://example.test/app.spl", "https:///app.spl"])
def test_app_install_rejects_invalid_url(cli_env, patch_client, source):
    patch_client(
        lambda req: (_ for _ in ()).throw(AssertionError("invalid URL must not send a request"))
    )
    result = CliRunner().invoke(
        cli, ["app", "install", "--url", source, "--yes", "--output", "json"]
    )

    assert result.exit_code == 2


def test_deploy_serverclass_get_encodes_name(cli_env, patch_client):
    seen: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["method"] = req.method
        seen["path"] = req.url.raw_path.decode().partition("?")[0]
        return httpx.Response(200, json={"entry": [{"name": "east west", "content": {}}]})

    patch_client(handler)
    result = CliRunner().invoke(
        cli, ["deploy", "serverclass", "get", "east west", "--output", "json"]
    )

    assert result.exit_code == 0
    assert seen == {
        "method": "GET",
        "path": "/services/deployment/server/serverclasses/east%20west",
    }


@pytest.mark.parametrize("verb", ["create", "update"])
def test_deploy_serverclass_write_exact_contract(cli_env, patch_client, verb):
    seen: dict[str, object] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen.update(
            method=req.method,
            path=req.url.raw_path.decode().partition("?")[0],
            form=parse_qs(req.content.decode()),
        )
        return httpx.Response(200, json={"entry": [{"name": "east west", "content": {}}]})

    patch_client(handler)
    result = CliRunner().invoke(
        cli,
        [
            "deploy",
            "serverclass",
            verb,
            "east west",
            "--set",
            "whitelist.0=*",
            "--yes",
            "--output",
            "json",
        ],
    )

    assert result.exit_code == 0
    expected_path = "/services/deployment/server/serverclasses"
    expected_form = {"whitelist.0": ["*"]}
    if verb == "create":
        expected_form["name"] = ["east west"]
    else:
        expected_path += "/east%20west"
    assert seen == {"method": "POST", "path": expected_path, "form": expected_form}


@pytest.mark.parametrize("verb", ["create", "update"])
@pytest.mark.parametrize("setting", ["broken", "=value", "x=1"])
def test_deploy_serverclass_rejects_malformed_settings(cli_env, patch_client, verb, setting):
    def handler(req: httpx.Request) -> httpx.Response:
        raise AssertionError("malformed settings must not send a request")

    patch_client(handler)
    args = ["deploy", "serverclass", verb, "example", "--set", setting]
    if setting == "x=1":
        args.extend(["--set", "x=2"])
    result = CliRunner().invoke(cli, [*args, "--yes", "--output", "json"])

    assert result.exit_code == 2


@pytest.mark.parametrize("verb", ["get", "create", "update"])
@pytest.mark.parametrize("name", ["..", "../other", r"..\\other", "%2e%2e%2fother"])
def test_deploy_serverclass_rejects_traversal_before_request(cli_env, patch_client, verb, name):
    def handler(req: httpx.Request) -> httpx.Response:
        raise AssertionError("unsafe names must not send a request")

    patch_client(handler)
    args = ["deploy", "serverclass", verb, name]
    if verb != "get":
        args.extend(["--set", "x=1", "--yes"])
    result = CliRunner().invoke(cli, [*args, "--output", "json"])

    assert result.exit_code == 2
