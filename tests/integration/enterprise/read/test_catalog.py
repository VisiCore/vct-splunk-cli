"""Execute every catalogued read against live Splunk Enterprise."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from cli_catalog import CATALOG, Case
from vct_splunk.cli import cli

pytestmark = [pytest.mark.integration, pytest.mark.enterprise, pytest.mark.read]

READ_CASES = tuple(case for case in CATALOG if case.kind == "read")


@pytest.mark.parametrize("case", READ_CASES, ids=lambda case: " ".join(case.path))
def test_every_enterprise_read_leaf(case: Case) -> None:
    """Run one canonical read and verify its typed JSON contract."""
    args = case.live_argv if case.live_argv is not None else case.argvs[0]
    result = CliRunner().invoke(cli, [*case.path, *args, "--output", "json"])

    assert result.exit_code in case.live_exit_codes, (
        f"{' '.join(case.path)} exited {result.exit_code}: {result.output}"
    )
    payload = json.loads(result.output)
    if result.exit_code == 4:
        assert payload["error"]["code"] == "not_found"
        return

    assert set(payload) == {"data", "meta"}
    assert payload["meta"]["target"]
