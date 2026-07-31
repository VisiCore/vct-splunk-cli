"""Pin the CI cost filter that decides whether the live Enterprise suite runs.

The filter lives in `.github/scripts/detect-code-changes.sh`. A silent mistake
there is expensive in both directions: too narrow and a real code change merges
without ever touching a live Splunk, too broad and every documentation typo
boots a container. The regex is read from the script itself, so there is one
source of truth and this test fails if the two ever drift apart.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / ".github/scripts/detect-code-changes.sh"


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is not installed")
def test_script_is_valid_bash() -> None:
    """The script must parse.

    A syntax error here only shows up as a failed CI job, and the reported line
    can be far from the real mistake — an apostrophe inside `${VAR:?...}` opens
    a quote that bash never closes, and it blames a later line.
    """
    result = subprocess.run(  # noqa: S603
        ["bash", "-n", str(_SCRIPT)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"detect-code-changes.sh has a syntax error:\n{result.stderr}"


def _covered_pattern() -> re.Pattern[str]:
    """Extract the COVERED extended-regex literal from the shell script."""
    match = re.search(r"^readonly COVERED='(?P<expr>.+)'$", _SCRIPT.read_text(), re.MULTILINE)
    assert match, "detect-code-changes.sh must define `readonly COVERED='<regex>'`"
    return re.compile(match.group("expr"))


@pytest.mark.parametrize(
    "path",
    [
        "src/vct_splunk/cli.py",
        "src/vct_splunk/core/client.py",
        "tests/unit/test_client.py",
        "tests/integration/enterprise/read/test_catalog.py",
        "pyproject.toml",
        ".github/workflows/ci.yml",
        ".github/scripts/detect-code-changes.sh",
    ],
)
def test_code_paths_trigger_the_live_suite(path: str) -> None:
    """Anything that can change CLI behavior must run the live suite."""
    assert _covered_pattern().search(path), f"{path} should trigger the Enterprise suite"


@pytest.mark.parametrize(
    "path",
    [
        "README.md",
        "CHANGELOG.md",
        "CONTRIBUTING.md",
        "AGENTS.md",
        "LICENSE",
        "docs/pyproject.toml",  # only a root-level pyproject.toml counts
        "notes/src/scratch.py",  # only a root-level src/ counts
        ".github/workflows/cloud-read.yml",  # credential-gated, not this gate
    ],
)
def test_docs_only_paths_skip_the_live_suite(path: str) -> None:
    """Documentation and unrelated workflows must not boot a Splunk container."""
    assert not _covered_pattern().search(path), f"{path} should not trigger the Enterprise suite"
