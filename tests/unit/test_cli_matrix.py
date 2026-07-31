"""Exhaustive wiring test: every command in the tree works with common inputs.

Two guarantees, kept automatically as commands are added:

1. ``--help`` succeeds for the root, every group, every leaf command, and every
   registered alias — a broken decorator, bad option declaration, or import slip
   anywhere in the tree fails here.
2. Every leaf command runs once with representative arguments against the mocked
   transport: reads must exit 0 with the ``{data, meta}`` envelope; writes run
   under ``--dry-run`` and must preview. A new command that this table cannot
   infer arguments for fails the completeness check until it gets an entry.
"""

from __future__ import annotations

import json

import click
import httpx
import pytest
from click.testing import CliRunner

from vct_splunk.cli import cli
from vct_splunk.commands.context import AliasedGroup

# Non-CRUD leaves the generic verb rules below cannot infer. Writes include
# --dry-run; reads run for real against the mock.
_SPECIAL: dict[tuple[str, ...], list[str]] = {
    ("auth", "login"): ["--username", "admin"],
    ("auth", "status"): [],
    ("server", "info"): [],
    ("api", "get"): ["/services/server/info", "-q", "count=1"],
    ("search", "run"): ["--query", "index=_internal", "--earliest", "-1h", "--max-rows", "5"],
    ("search", "list"): [],
    ("search", "get"): ["sid1"],
    ("search", "cancel"): ["sid1", "--dry-run"],
    ("saved-search", "run"): ["nightly", "--app", "my_app", "--earliest", "-1h"],
    ("health", "check"): [],
    ("inspect",): [],
}

# Generic argument rules by CRUD verb (factory-generated and factory-shaped groups).
_BY_VERB: dict[str, list[str]] = {
    "list": [],
    "get": ["x"],
    "create": ["x", "--dry-run"],
    "update": ["x", "--set", "k=v", "--dry-run"],
    "delete": ["x", "--dry-run"],
    "enable": ["x", "--dry-run"],
    "disable": ["x", "--dry-run"],
}

# Required create options the verb rule must add, per group.
_REQUIRED_CREATE: dict[str, list[str]] = {
    "saved-search": ["--search", "index=x"],
}


def _iter_leaves(group: click.Group, path: tuple[str, ...] = ()):
    for name, cmd in sorted(group.commands.items()):
        if isinstance(cmd, click.Group):
            yield from _iter_leaves(cmd, (*path, name))
        else:
            yield (*path, name), cmd


def _iter_groups(group: click.Group, path: tuple[str, ...] = ()):
    yield path, group
    for name, cmd in sorted(group.commands.items()):
        if isinstance(cmd, click.Group):
            yield from _iter_groups(cmd, (*path, name))


def _args_for(path: tuple[str, ...]) -> list[str] | None:
    if path in _SPECIAL:
        return list(_SPECIAL[path])
    if len(path) == 2 and path[1] in _BY_VERB:
        args = list(_BY_VERB[path[1]])
        extra = _REQUIRED_CREATE.get(path[0])
        if path[1] == "create" and extra:
            args += extra
        return args
    return None


def _handler(req: httpx.Request) -> httpx.Response:
    """One canned Splunk that satisfies every read the tree performs."""
    path = req.url.path
    if path.endswith("/dispatch"):
        return httpx.Response(201, json={"sid": "sid1"})
    if "/search/jobs" in path and req.method == "POST":
        return httpx.Response(200, json={"results": [{"error_count": "0"}]})
    content = {"version": "9.4", "health": "green", "features": {}}
    if path.endswith("/resource-usage/hostwide"):
        content.update(
            {"cpu_system_pct": "5", "cpu_user_pct": "10", "mem": "100", "mem_used": "20"}
        )
    if path.endswith("/partitions-space"):
        content.update({"mount_point": "/", "capacity": "100", "free": "80"})
    return httpx.Response(
        200,
        json={
            "entry": [
                {
                    "name": "x",
                    "content": content,
                    "acl": {"app": "a", "owner": "o", "sharing": "app"},
                }
            ],
            "paging": {"total": 1},
        },
    )


def _all_help_invocations() -> list[list[str]]:
    argvs: list[list[str]] = [["--help"]]
    for path, group in _iter_groups(cli):
        if path:
            argvs.append([*path, "--help"])
        # Aliases resolve through AliasedGroup.get_command; --help must work there too.
        if isinstance(group, AliasedGroup):
            argvs.extend([*path, alias, "--help"] for alias in group._aliases)
    argvs.extend([*path, "--help"] for path, _ in _iter_leaves(cli))
    return argvs


@pytest.mark.parametrize("argv", _all_help_invocations(), ids=" ".join)
def test_every_help_screen_renders(argv):
    result = CliRunner().invoke(cli, argv)
    assert result.exit_code == 0, f"{argv}: {result.output}"
    assert "Usage:" in result.output


def test_every_leaf_has_representative_args():
    # Completeness gate: a newly added command must be covered by a verb rule or
    # get a _SPECIAL entry — otherwise this test names it and fails.
    uncovered = [" ".join(path) for path, _ in _iter_leaves(cli) if _args_for(path) is None]
    assert not uncovered, f"add matrix args for: {uncovered}"


@pytest.mark.parametrize("path", [p for p, _ in _iter_leaves(cli)], ids=lambda p: " ".join(p))
def test_every_leaf_runs_with_common_inputs(path, cli_env, patch_client, monkeypatch, tmp_path):
    monkeypatch.setenv("SPLUNK_APP", "my_app")  # satisfies namespaced writes
    monkeypatch.setenv("SPLUNK_PASSWORD", "secret")
    monkeypatch.setenv("VCT_SPLUNK_AUDIT", str(tmp_path / "audit.log"))
    if path == ("auth", "login"):
        monkeypatch.setattr("vct_splunk.commands.auth.core.login", lambda *a, **k: "SK")
    patch_client(_handler)
    argv = [*path, *(_args_for(path) or []), "--output", "json"]
    result = CliRunner().invoke(cli, argv)
    assert result.exit_code == 0, f"{argv}: {result.output}"
    payload = json.loads(result.output)
    assert "data" in payload  # the success envelope, for reads and previews alike
    if "--dry-run" in argv:
        assert payload["data"]["dry_run"] is True  # writes never hit the wire here
