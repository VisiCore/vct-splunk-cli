"""No read prints a credential, on either backend.

Splunk returns secrets inside ordinary read responses: an HTTP Event Collector
input carries its own token, a server setting carries `pass4SymmKey`. A resource
that simply passes content through therefore publishes every credential it
holds, and the CLI matrix cannot notice — its fixture content has no secret in
it to leak.

So these tests feed a secret through the real command path and assert it does
not come back. The one deliberate exception is a command whose purpose is to
mint a credential; those are named here so adding another is a visible decision
rather than a quiet regression.
"""

from __future__ import annotations

import json

import httpx
import pytest
from click.testing import CliRunner

from vct_splunk.cli import cli
from vct_splunk.commands import context
from vct_splunk.core import redact
from vct_splunk.core.client import ClientConfig, SplunkClient

SECRET = "s3cret-token-value"
URL_PASSWORD = "url-password-must-not-appear"


@pytest.fixture
def splunk(monkeypatch: pytest.MonkeyPatch):
    """Answer every request with an entry whose content carries a secret."""
    seen: list[httpx.Request] = []
    # A gated write resolves its audit target from the environment, separately
    # from the client this fixture patches.
    monkeypatch.setenv("SPLUNK_URL", "https://sh.corp:8089")
    monkeypatch.setenv("SPLUNK_TOKEN", "T")

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "entry": [
                    {
                        "name": "ci_hec",
                        "content": {
                            "token": SECRET,
                            "pass4SymmKey": SECRET,
                            "index": "main",
                            "disabled": 0,
                        },
                        "acl": {"app": "search", "owner": "nobody", "sharing": "app"},
                    }
                ],
                "paging": {"total": 1},
            },
        )

    monkeypatch.setattr(
        context.Ctx,
        "client",
        lambda self: SplunkClient(
            ClientConfig(base_url="https://sh.corp:8089", token="T"),
            transport=httpx.MockTransport(handler),
        ),
    )
    return seen


def _run(*argv: str):
    return CliRunner().invoke(cli, [*argv, "--output", "json"])


@pytest.mark.parametrize(
    "argv",
    [
        ("hec-token", "list"),
        ("hec-token", "get", "ci_hec"),
        ("hec-token", "update", "ci_hec", "--set", "index=main", "--yes"),
    ],
    ids=lambda argv: " ".join(argv[:2]),
)
def test_reading_a_credential_bearing_resource_never_prints_the_secret(splunk, argv) -> None:
    """Browsing a resource shows that a secret field exists, never its value."""
    result = _run(*argv)

    assert result.exit_code == 0, result.output
    assert SECRET not in result.output
    assert redact.REDACTED in result.output


def test_creating_a_credential_returns_it_once(splunk) -> None:
    """The documented exception: a create mints the value and must hand it back.

    If this ever starts redacting, `hec-token create` becomes unusable without a
    follow-up rotate — so the exception is pinned rather than left to a comment.
    """
    result = _run("hec-token", "create", "ci_hec", "--yes")

    assert result.exit_code == 0, result.output
    assert SECRET in result.output


def test_server_settings_redact_the_symmetric_key(splunk) -> None:
    """The same rule covers server settings, which carry `pass4SymmKey`."""
    payload = json.loads(_run("server", "settings", "get").output)

    assert payload["data"]["pass4SymmKey"] == redact.REDACTED
    assert SECRET not in json.dumps(payload)


@pytest.mark.parametrize(
    "key",
    ["token", "hec_token", "Token", "pass4SymmKey", "password", "clientSecret", "client-secret"],
)
def test_secret_key_names_are_recognized(key: str) -> None:
    """Matching ignores case, underscores, and hyphens."""
    assert redact.is_secret_key(key)


@pytest.mark.parametrize("key", ["index", "name", "disabled", "sourcetype", "maxTotalDataSizeMB"])
def test_ordinary_key_names_are_left_alone(key: str) -> None:
    assert not redact.is_secret_key(key)


def test_no_command_prints_url_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """A credentialed SPLUNK_URL never reaches output, from any command.

    The target is echoed in response metadata, dry-run previews, `auth status`,
    and transport error messages. Sweeping the whole catalog is how a new echo
    site gets caught, rather than each one being remembered separately.
    """
    from cli_catalog import CATALOG

    monkeypatch.setenv("SPLUNK_URL", f"https://admin:{URL_PASSWORD}@sh.corp:8089")
    monkeypatch.setenv("SPLUNK_TOKEN", "T")
    monkeypatch.setenv("SPLUNK_APP", "my_app")

    leaking = []
    for case in CATALOG:
        argv = [*case.path, *case.argvs[0]]
        if "--dry-run" not in argv:
            argv.append("--dry-run")
        result = CliRunner().invoke(cli, [*argv, "--yes", "--output", "json"])
        if URL_PASSWORD in (result.output or ""):
            leaking.append(" ".join(case.path))

    assert leaking == []
