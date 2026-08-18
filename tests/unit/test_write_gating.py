"""Writes are refused by default, on every backend, until explicitly opted in.

Two independent env-only gates (never a CLI flag, so a saved command line can
never turn one on by itself):

- `SPLUNK_ENABLE_WRITES=true` -- required for any real (non-dry-run) mutation,
  on every backend. `--dry-run` sends nothing and needs no opt-in.
- `SPLUNK_CLOUD_WRITE=true` -- required *additionally* on a Cloud target, and
  only unlocks create/update/delete for `index`, `role`, and `hec-token` (the
  three ACS mutation routes). This one is enforced even for a `--dry-run`
  preview, since it also proves the object is one of those three -- see
  `vct_splunk.commands.write.refuse_cloud_write`.

The property that makes each refusal safe is not "writes usually fail" -- it is
that the write stops at the gate, with a typed error, having sent nothing. A
refusal that happened only because a credential was missing, or one that fired
after a request went out, would both look like success in a weaker test. So
every refusal case here installs a transport that fails the test if any real
request leaves the process.

`tests/unit/test_acs_loopback.py` covers the Cloud read contract; this and
that both run credential-free on every change, needing no live target.
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
from vct_splunk.utils.errors import UnsupportedBackendError, UsageError

WRITE_CASES = tuple(case for case in CATALOG if case.kind == "write")
CLOUD_WRITABLE_CASES = tuple(
    case for case in WRITE_CASES if has_cloud_write(case.path[0], case.path[-1])
)
CLOUD_UNWRITABLE_CASES = tuple(
    case for case in WRITE_CASES if not has_cloud_write(case.path[0], case.path[-1])
)
#: `saved-search run` (no `--trigger-actions`) dispatches a job -- it changes no
#: configuration, so it deliberately does not go through `do_write` at all (see
#: its docstring). It is cataloged as "write" for other purposes, but does not
#: belong in a suite proving `SPLUNK_ENABLE_WRITES` refuses every gated write.
_GATED_WRITE_CASES = tuple(case for case in WRITE_CASES if case.path != ("saved-search", "run"))

#: CLI resource name -> the ACS collection path it writes to.
_ACS_PATH = {"index": acs.INDEXES, "role": acs.ROLES, "hec-token": acs.HEC_TOKENS}


def _argv(case: Case, *extra: str) -> list[str]:
    """Build one invocation of *case*, replacing any `--dry-run` with *extra*."""
    args = [arg for arg in case.argvs[0] if arg != "--dry-run"]
    return [*case.path, *args, *extra, "--output", "json"]


def _refuse_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: object, **kwargs: object) -> object:
        raise AssertionError("a refused write reached the network")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)


# --- Enterprise: SPLUNK_ENABLE_WRITES gates every real write ------------------


@pytest.fixture
def enterprise_env_no_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the CLI at Enterprise with the top-level gate off; refuse the network.

    A namespaced write needs an explicit app regardless of this gate (that
    check runs before `do_write`), so `SPLUNK_APP` is set, not cleared, here --
    this suite is testing the write-enable gate, not namespace resolution.
    """
    for name in ("SPLUNK_OWNER", "SPLUNK_PROFILE", "SPLUNK_ENABLE_WRITES"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SPLUNK_URL", "https://sh.corp:8089")
    monkeypatch.setenv("SPLUNK_TOKEN", "T")
    monkeypatch.setenv("SPLUNK_APP", "my_app")
    _refuse_network(monkeypatch)


@pytest.mark.parametrize("case", _GATED_WRITE_CASES, ids=lambda case: " ".join(case.path))
def test_every_write_is_refused_without_enable_writes(
    case: Case, enterprise_env_no_opt_in: None
) -> None:
    """Every write leaf refuses before touching the network when the gate is off."""
    result = CliRunner().invoke(cli, _argv(case, "--yes"))

    assert result.exit_code == UsageError.exit_code, (
        f"{' '.join(case.path)} exited {result.exit_code}: {result.output}"
    )
    payload = json.loads(result.output)
    assert set(payload) == {"error"}
    assert payload["error"]["code"] == UsageError.code
    assert "SPLUNK_ENABLE_WRITES" in payload["error"]["message"]


def test_enterprise_dry_run_needs_no_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    """A preview sends nothing, so it works with SPLUNK_ENABLE_WRITES unset."""
    monkeypatch.delenv("SPLUNK_ENABLE_WRITES", raising=False)
    monkeypatch.setenv("SPLUNK_URL", "https://sh.corp:8089")
    monkeypatch.setenv("SPLUNK_TOKEN", "T")

    result = CliRunner().invoke(
        cli, ["index", "create", "example", "--dry-run", "--output", "json"]
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["data"]["dry_run"] is True


# --- Cloud: SPLUNK_CLOUD_WRITE additionally gates the three ACS routes --------


@pytest.fixture
def cloud_env_no_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the CLI at a Cloud stack with neither opt-in set; refuse the network."""
    for name in (
        "SPLUNK_APP",
        "SPLUNK_OWNER",
        "SPLUNK_PROFILE",
        "SPLUNK_ACS_BASE_URL",
        "SPLUNK_CLOUD_WRITE",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SPLUNK_URL", "https://acme.splunkcloud.com")
    monkeypatch.setenv("SPLUNK_ACS_TOKEN", "unused")
    monkeypatch.setenv("SPLUNK_TOKEN", "unused")
    _refuse_network(monkeypatch)


@pytest.mark.parametrize("case", WRITE_CASES, ids=lambda case: " ".join(case.path))
def test_every_write_is_refused_on_cloud_by_default(case: Case, cloud_env_no_opt_in: None) -> None:
    """The gate stops the write, names the backend, and sends nothing."""
    result = CliRunner().invoke(cli, _argv(case, "--yes"))

    assert result.exit_code == UnsupportedBackendError.exit_code, (
        f"{' '.join(case.path)} exited {result.exit_code}: {result.output}"
    )
    payload = json.loads(result.output)
    assert set(payload) == {"error"}
    assert payload["error"]["code"] == UnsupportedBackendError.code
    assert "Splunk Cloud" in payload["error"]["message"]


@pytest.fixture
def cloud_write_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the CLI at a Cloud stack with the write opt-in set."""
    for name in ("SPLUNK_APP", "SPLUNK_OWNER", "SPLUNK_PROFILE", "SPLUNK_ACS_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SPLUNK_URL", "https://acme.splunkcloud.com")
    monkeypatch.setenv("SPLUNK_ACS_TOKEN", "T")
    monkeypatch.setenv("SPLUNK_CLOUD_WRITE", "true")


def _patch_acs_write(monkeypatch: pytest.MonkeyPatch, handler) -> None:
    """Back the ACS write client `do_write` opens with an `httpx.MockTransport`."""

    def _make(config):
        return RealAcsClient(config, transport=httpx.MockTransport(handler))

    monkeypatch.setattr("vct_splunk.commands.write.AcsClient", _make)


@pytest.mark.parametrize("case", CLOUD_UNWRITABLE_CASES, ids=lambda case: " ".join(case.path))
def test_non_acs_writes_still_refused_when_opted_in(
    case: Case, cloud_write_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The opt-in unlocks only the nine ACS routes -- everything else still refuses."""
    _refuse_network(monkeypatch)
    result = CliRunner().invoke(cli, _argv(case, "--yes"))

    assert result.exit_code == UnsupportedBackendError.exit_code, (
        f"{' '.join(case.path)} exited {result.exit_code}: {result.output}"
    )
    payload = json.loads(result.output)
    assert set(payload) == {"error"}
    assert payload["error"]["code"] == UnsupportedBackendError.code


@pytest.mark.parametrize("case", CLOUD_WRITABLE_CASES, ids=lambda case: " ".join(case.path))
def test_acs_write_dry_run_sends_nothing(
    case: Case, cloud_write_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """--dry-run previews an ACS write and sends no request, even when opted in."""
    _refuse_network(monkeypatch)
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
