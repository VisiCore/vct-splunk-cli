"""End-to-end smoke test against a live Splunk Enterprise.

Gated: set SPLUNK_INTEGRATION_TEST=true plus SPLUNK_URL / SPLUNK_TOKEN. Runs
against any reachable Splunk Enterprise instance — an ephemeral Dockerized
`splunk/splunk`, or an existing instance whose REST management port is reachable.
"""

from __future__ import annotations

import os
import uuid

import pytest
from click.testing import CliRunner

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _gate():
    if os.environ.get("SPLUNK_INTEGRATION_TEST") != "true":
        pytest.skip("set SPLUNK_INTEGRATION_TEST=true (+ SPLUNK_URL/SPLUNK_TOKEN) to run")


def test_end_to_end():
    from vct_splunk import indexes
    from vct_splunk.cli import cli
    from vct_splunk.client import SplunkClient, config_from_env

    runner = CliRunner()
    assert runner.invoke(cli, ["server", "info", "--output", "json"]).exit_code == 0
    assert runner.invoke(cli, ["index", "list", "--output", "json"]).exit_code == 0
    assert runner.invoke(cli, ["api", "get", "/services/server/info", "--output", "json"]).exit_code == 0

    name = f"vctmvp_{uuid.uuid4().hex[:8]}"
    # The common flags (--dry-run, -y, --output) are defined on the *leaf* command
    # (here `index create`), not on the root group. Click parses each group's own
    # options before descending into the subcommand, so a flag placed *before* the
    # subcommand name (e.g. `--dry-run index create`) is rejected as an unknown
    # group option and exits 2. Always place these flags after the final subcommand.
    assert runner.invoke(cli, ["index", "create", name, "--dry-run", "--output", "json"]).exit_code == 0
    assert runner.invoke(cli, ["index", "create", name, "-y", "--max-gb", "1", "--output", "json"]).exit_code == 0
    try:
        assert runner.invoke(cli, ["index", "get", name, "--output", "json"]).exit_code == 0
    finally:
        with SplunkClient(config_from_env()) as client:
            indexes.delete_index(client, name)
