"""CLI-level behavior of the `index` group worth pinning by name.

The generic write gate is covered once in test_write.py; these are the
representative CLI cases (one dry-run, one refusal) plus index-specific rules.
"""

from __future__ import annotations

from click.testing import CliRunner

from vct_splunk.cli import cli


def test_create_refuses_without_yes_noninteractive(cli_env):
    # The one CLI-level pin of the non-interactive refusal (canonical gate test
    # lives in test_write.py).
    result = CliRunner().invoke(cli, ["index", "create", "myidx", "--output", "json"])
    assert result.exit_code == 2
    assert "usage_error" in result.output


def test_create_dry_run_previews(cli_env):
    result = CliRunner().invoke(
        cli, ["index", "create", "myidx", "--max-gb", "2", "--dry-run", "--output", "json"]
    )
    assert result.exit_code == 0
    assert '"dry_run": true' in result.output
    assert '"maxTotalDataSizeMB": 2048' in result.output  # --max-gb scaled GB -> MB


def test_update_requires_a_field(cli_env):
    result = CliRunner().invoke(cli, ["index", "update", "main", "--yes", "--output", "json"])
    assert result.exit_code == 2
    assert "usage_error" in result.output


def test_add_alias_resolves_to_create(cli_env):
    # Splunk-CLI familiarity: `index add` resolves to `index create`.
    result = CliRunner().invoke(cli, ["index", "add", "myidx", "--dry-run", "--output", "json"])
    assert result.exit_code == 0
    assert '"dry_run": true' in result.output
