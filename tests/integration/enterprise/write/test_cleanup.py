"""Verify that ordinary Enterprise write tests did not leave test-named objects."""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from cli_catalog import CATALOG, Case
from vct_splunk.cli import cli

pytestmark = [pytest.mark.integration, pytest.mark.enterprise, pytest.mark.read]

_WRITE_AREAS = {case.path[0] for case in CATALOG if case.kind == "write"}
_CLEANUP_LISTS = tuple(
    case
    for case in CATALOG
    if case.kind == "read"
    and case.path[-1] == "list"
    and case.path[0] in _WRITE_AREAS
    and case.path[:2] != ("deploy-server", "serverclass")
)


@pytest.mark.parametrize("case", _CLEANUP_LISTS, ids=lambda case: " ".join(case.path))
def test_no_vct_ci_objects_remain(case: Case) -> None:
    """Inspect catalogued mutable-resource collections through the public CLI."""
    result = CliRunner().invoke(cli, [*case.path, "--output", "json"])
    assert result.exit_code == 0, f"{' '.join(case.path)} exited {result.exit_code}"
    assert "vct_ci_" not in result.stdout, f"{' '.join(case.path)} still has a test object"
