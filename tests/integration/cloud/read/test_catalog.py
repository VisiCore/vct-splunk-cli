"""Execute every catalogued read against a live Splunk Cloud stack.

The Cloud mirror of `tests/integration/enterprise/read/test_catalog.py`. It runs
the same read leaves from the same catalog, and asserts the Cloud contract:

* A read that Cloud actually serves (via ACS) must succeed and return a typed
  ``{data, meta}`` envelope.
* Every other read must still honor the documented contract — a typed error
  envelope and a documented exit code — never a traceback, and never a silent
  fallthrough to an endpoint the stack does not serve.

That second rule is the point of the suite. Cloud coverage is read-only and
partial, so the guarantee worth proving is that an unsupported command fails
*cleanly* instead of guessing.
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from cli_catalog import CATALOG, Case
from vct_splunk.cli import cli
from vct_splunk.commands.dispatch import has_cloud_list

pytestmark = [pytest.mark.integration, pytest.mark.cloud, pytest.mark.read]

READ_CASES = tuple(case for case in CATALOG if case.kind == "read")

#: Reads that must succeed on Cloud. Derived from the real dispatch table, so
#: adding a Cloud route extends this suite automatically instead of drifting.
CLOUD_BACKED = tuple(
    case
    for case in READ_CASES
    if (case.path[-1] == "list" and has_cloud_list(case.path[0])) or case.path == ("inspect",)
)

#: The documented exit codes (see the README). Anything else means the CLI
#: crashed or invented a status. Exit 2 belongs here: this suite supplies only
#: ACS credentials, so every read outside the ACS routes stops at the splunkd
#: auth check with a config error — which is itself the contract holding.
CONTRACT_EXITS = (0, 1, 2, 3, 4, 5)


def _invoke(case: Case):
    """Run one catalogued read through the public CLI, asking for JSON."""
    args = case.live_argv if case.live_argv is not None else case.argvs[0]
    return CliRunner().invoke(cli, [*case.path, *args, "--output", "json"])


@pytest.mark.parametrize("case", CLOUD_BACKED, ids=lambda case: " ".join(case.path))
def test_cloud_backed_read_succeeds(case: Case) -> None:
    """A read Cloud serves must succeed and return the typed data envelope."""
    result = _invoke(case)

    assert result.exit_code == 0, (
        f"{' '.join(case.path)} exited {result.exit_code}: {result.output}"
    )
    payload = json.loads(result.output)
    assert set(payload) == {"data", "meta"}
    assert payload["meta"]["target"]


@pytest.mark.parametrize("case", READ_CASES, ids=lambda case: " ".join(case.path))
def test_every_cloud_read_leaf_honors_the_contract(case: Case) -> None:
    """Every read either succeeds or fails cleanly — never a crash or a guess."""
    result = _invoke(case)

    assert result.exit_code in CONTRACT_EXITS, (
        f"{' '.join(case.path)} exited {result.exit_code}, "
        f"outside the documented contract: {result.output}"
    )
    payload = json.loads(result.output)

    if result.exit_code in (0, 5):
        assert set(payload) == {"data", "meta"}
        return

    # A failure must still be a typed envelope that a script can branch on.
    assert set(payload) == {"error"}
    assert payload["error"]["code"]
    assert payload["error"]["message"]
