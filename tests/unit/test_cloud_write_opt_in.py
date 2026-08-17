"""Splunk Cloud writes are opt-in and narrow.

``SPLUNK_CLOUD_WRITE=true`` unlocks exactly nine leaves: create/update/delete for
`index`, `role`, and `hec-token` -- the three ACS mutation routes. Every other
Cloud mutation, including enable/disable on those same three resources, stays
refused before any network is touched even with the opt-in set; there is no CLI
flag for the opt-in, only the environment variable.

This is the counterpart to `test_cloud_write_refusal.py`, which proves the
*default* (no opt-in) behavior. Neither needs a Cloud stack.
"""

from __future__ import annotations

import json

import httpx
import pytest
from click.testing import CliRunner

from cli_catalog import CATALOG, Case
from vct_splunk.api.acs import operations as acs
from vct_splunk.api.acs.client import AcsClient as RealAcsClient
from vct_splunk.cli import cli
from vct_splunk.commands.dispatch import has_cloud_write
from vct_splunk.utils.errors import UnsupportedBackendError

#: CLI resource name -> the ACS collection path it writes to.
_ACS_PATH = {"index": acs.INDEXES, "role": acs.ROLES, "hec-token": acs.HEC_TOKENS}

WRITE_CASES = tuple(case for case in CATALOG if case.kind == "write")
CLOUD_WRITABLE_CASES = tuple(
    case for case in WRITE_CASES if has_cloud_write(case.path[0], case.path[-1])
)
STILL_REFUSED_CASES = tuple(
    case for case in WRITE_CASES if not has_cloud_write(case.path[0], case.path[-1])
)


@pytest.fixture
def cloud_write_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the CLI at a Cloud stack with the write opt-in set."""
    for name in ("SPLUNK_APP", "SPLUNK_OWNER", "SPLUNK_PROFILE", "SPLUNK_ACS_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SPLUNK_URL", "https://acme.splunkcloud.com")
    monkeypatch.setenv("SPLUNK_ACS_TOKEN", "T")
    monkeypatch.setenv("SPLUNK_CLOUD_WRITE", "true")


@pytest.fixture
def refuse_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make any real request an error, so a passing test proves nothing left the process."""

    def refuse(*args: object, **kwargs: object) -> object:
        raise AssertionError("a write reached the network")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)


def _patch_acs_write(monkeypatch: pytest.MonkeyPatch, handler) -> None:
    """Back the ACS write client `do_write` opens with a `httpx.MockTransport`."""

    def _make(config):
        return RealAcsClient(config, transport=httpx.MockTransport(handler))

    monkeypatch.setattr("vct_splunk.commands.write.AcsClient", _make)


def _argv(case: Case, *extra: str) -> list[str]:
    """Build one invocation of *case*, replacing any `--dry-run` with *extra*."""
    args = [arg for arg in case.argvs[0] if arg != "--dry-run"]
    return [*case.path, *args, *extra, "--output", "json"]


@pytest.mark.parametrize("case", STILL_REFUSED_CASES, ids=lambda case: " ".join(case.path))
def test_non_acs_writes_still_refused_when_opted_in(
    case: Case, cloud_write_env: None, refuse_network: None
) -> None:
    """The opt-in unlocks only the nine ACS routes -- everything else still refuses."""
    result = CliRunner().invoke(cli, _argv(case, "--yes"))

    assert result.exit_code == UnsupportedBackendError.exit_code, (
        f"{' '.join(case.path)} exited {result.exit_code}: {result.output}"
    )
    payload = json.loads(result.output)
    assert set(payload) == {"error"}
    assert payload["error"]["code"] == UnsupportedBackendError.code


@pytest.mark.parametrize("case", CLOUD_WRITABLE_CASES, ids=lambda case: " ".join(case.path))
def test_acs_write_dry_run_sends_nothing(
    case: Case, cloud_write_env: None, refuse_network: None
) -> None:
    """--dry-run previews an ACS write and sends no request, even when opted in."""
    result = CliRunner().invoke(cli, _argv(case, "--dry-run"))

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["data"]["dry_run"] is True
    assert payload["data"]["request"]["method"] in {"POST", "PATCH", "DELETE"}


@pytest.mark.parametrize("case", CLOUD_WRITABLE_CASES, ids=lambda case: " ".join(case.path))
def test_acs_write_succeeds_when_opted_in_and_confirmed(
    case: Case, cloud_write_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the opt-in and --yes, a mocked ACS create/update/delete succeeds."""
    seen: dict[str, str] = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["method"] = req.method
        seen["path"] = req.url.path
        return httpx.Response(202, json={"name": "example"})

    _patch_acs_write(monkeypatch, handler)
    result = CliRunner().invoke(cli, _argv(case, "--yes"))

    assert result.exit_code == 0, result.output
    resource, verb = case.path
    expected_method = {"create": "POST", "update": "PATCH", "delete": "DELETE"}[verb]
    assert seen["method"] == expected_method
    assert seen["path"].startswith(f"/acme/adminconfig/v2/{_ACS_PATH[resource]}")


def test_hec_token_create_redacts_token_in_output(
    cloud_write_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ACS mints the token on create; Cloud CI output must never show it."""

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            202, json={"http-event-collector": {"name": "example", "token": "SECRET-DO-NOT-LEAK"}}
        )

    _patch_acs_write(monkeypatch, handler)
    result = CliRunner().invoke(
        cli, ["hec-token", "create", "example", "--yes", "--output", "json"]
    )

    assert result.exit_code == 0, result.output
    assert "SECRET-DO-NOT-LEAK" not in result.output
    assert "<redacted>" in result.output
