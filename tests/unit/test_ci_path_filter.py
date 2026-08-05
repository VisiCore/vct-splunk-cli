"""Pin the CI cost filter that decides whether the live Enterprise suite runs.

The filter lives in `.github/scripts/detect-code-changes.sh`. A silent mistake
there is expensive in both directions: too narrow and a real code change merges
without ever touching a live Splunk, too broad and every documentation typo
boots a container. The regex is read from the script itself, so there is one
source of truth and this test fails if the two ever drift apart.
"""

from __future__ import annotations

import re
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / ".github/scripts/detect-code-changes.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("bash") is None or shutil.which("grep") is None,
    reason="bash and grep are needed to run the filter the way CI runs it",
)


def test_script_is_valid_bash() -> None:
    """The script must parse.

    A syntax error here only shows up as a failed CI job, and the reported line
    can be far from the real mistake — an apostrophe inside `${VAR:?...}` opens
    a quote that bash never closes, and it blames a later line.
    """
    result = subprocess.run(
        ["bash", "-n", str(_SCRIPT)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"detect-code-changes.sh has a syntax error:\n{result.stderr}"


def _expression(name: str) -> str:
    """Extract one `readonly <name>='<regex>'` literal from the shell script."""
    match = re.search(rf"^readonly {name}='(?P<expr>.+)'$", _SCRIPT.read_text(), re.MULTILINE)
    assert match, f"detect-code-changes.sh must define `readonly {name}='<regex>'`"
    return match.group("expr")


def _covers(path: str) -> bool:
    """Run *path* through the script's own filter and report whether it matches.

    This shells out to the same `grep -vE DOCS | grep -qE COVERED` pipeline the
    script runs, with both patterns read from the script. The engine has to be
    the real one: POSIX extended regular expressions and Python's `re` disagree
    on enough syntax that a pattern can pass here and behave differently in the
    job this test exists to protect.
    """
    docs = shlex.quote(_expression("DOCS"))
    covered = shlex.quote(_expression("COVERED"))
    pipeline = f"grep -vE {docs} | grep -qE {covered}"
    result = subprocess.run(
        ["bash", "-c", pipeline],
        input=path,
        capture_output=True,
        text=True,
    )
    assert result.returncode in (0, 1), f"filter failed on {path!r}: {result.stderr}"
    return result.returncode == 0


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
    assert _covers(path), f"{path} should trigger the Enterprise suite"


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
        "tests/TESTING.md",  # markdown under tests/ is still documentation
        ".github/workflows/cloud-read.yml",  # credential-gated, not this gate
    ],
)
def test_docs_only_paths_skip_the_live_suite(path: str) -> None:
    """Documentation and unrelated workflows must not boot a Splunk container."""
    assert not _covers(path), f"{path} should not trigger the Enterprise suite"
