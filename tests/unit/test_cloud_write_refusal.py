"""Every mutation must refuse a Splunk Cloud target before touching the network.

Cloud support is read-only. The property that makes that safe is not "writes
usually fail" — it is that a write against a Cloud stack stops at the gate, with
a typed error, having sent nothing. A refusal that happened only because a
credential was missing, or one that fired after a request went out, would both
look like success in a weaker test.

So this suite runs every write leaf in the catalog with `--yes`, the form that
would otherwise execute, and installs a transport that fails the test if any
request leaves the process.

Its read counterpart is `test_acs_loopback.py`. Both run credential-free on
every change; neither needs a Cloud stack.
"""

from __future__ import annotations

import json

import httpx
import pytest
from click.testing import CliRunner

from cli_catalog import CATALOG, Case
from vct_splunk.cli import cli
from vct_splunk.core.errors import UnsupportedBackendError

WRITE_CASES = tuple(case for case in CATALOG if case.kind == "write")


@pytest.fixture(autouse=True)
def cloud_target_with_no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the CLI at a Cloud stack and make any real request an error.

    Patching the transport rather than the client covers both clients at once,
    including a future one, and cannot be satisfied by a command that simply
    fails earlier for an unrelated reason.
    """
    # Clear the ambient settings a developer may have exported, so the suite
    # tests the tool rather than the machine it runs on.
    for name in ("SPLUNK_APP", "SPLUNK_OWNER", "SPLUNK_PROFILE", "SPLUNK_ACS_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SPLUNK_URL", "https://acme.splunkcloud.com")
    monkeypatch.setenv("SPLUNK_ACS_TOKEN", "unused")
    monkeypatch.setenv("SPLUNK_TOKEN", "unused")

    def refuse(*args: object, **kwargs: object) -> object:
        raise AssertionError("a write against a Cloud target reached the network")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)


def _argv(case: Case) -> list[str]:
    """Build the executing form of a write: no preview, no prompt."""
    args = [arg for arg in case.argvs[0] if arg != "--dry-run"]
    return [*case.path, *args, "--yes", "--output", "json"]


@pytest.mark.parametrize("case", WRITE_CASES, ids=lambda case: " ".join(case.path))
def test_every_write_is_refused_on_cloud(case: Case) -> None:
    """The gate stops the write, names the backend, and sends nothing."""
    result = CliRunner().invoke(cli, _argv(case))

    assert result.exit_code == UnsupportedBackendError.exit_code, (
        f"{' '.join(case.path)} exited {result.exit_code}: {result.output}"
    )
    payload = json.loads(result.output)
    assert set(payload) == {"error"}
    assert payload["error"]["code"] == UnsupportedBackendError.code
    assert "Splunk Cloud" in payload["error"]["message"]
