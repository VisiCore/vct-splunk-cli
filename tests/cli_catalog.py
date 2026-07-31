"""Canonical CLI leaf catalog shared by exhaustive tests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import click

from vct_splunk.commands.context import AliasedGroup
from vct_splunk.commands.registry import INDEX, REGISTRY, SAVED_SEARCH

Kind = Literal["read", "write"]


@dataclass(frozen=True)
class Case:
    """One canonical leaf with its semantic kind and representative invocations."""

    path: tuple[str, ...]
    kind: Kind
    argvs: tuple[tuple[str, ...], ...]


_VERB_ARGS: dict[str, tuple[str, ...]] = {
    "list": (),
    "get": ("example",),
    "create": ("example", "--dry-run"),
    "update": ("example", "--set", "key=value", "--dry-run"),
    "delete": ("example", "--dry-run"),
    "enable": ("example", "--dry-run"),
    "disable": ("example", "--dry-run"),
}

_SPECIAL: tuple[Case, ...] = (
    Case(("api", "get"), "read", (("/services/server/info", "-q", "count=1"),)),
    Case(("app", "install"), "write", (("--server-file", "/tmp/app.spl", "--dry-run"),)),
    Case(("auth", "login"), "read", (("--username", "admin"),)),
    Case(("auth", "status"), "read", ((),)),
    Case(("cluster", "status"), "read", ((),)),
    Case(("datamodel", "accelerate"), "write", (("model", "--app", "my_app", "--dry-run"),)),
    Case(("deploy-client", "list"), "read", ((),)),
    Case(("deploy-server", "reload"), "write", (("--dry-run",),)),
    Case(("deploy-server", "serverclass", "list"), "read", ((),)),
    Case(("deploy-server", "serverclass", "get"), "read", (("class",),)),
    Case(
        ("deploy-server", "serverclass", "create"),
        "write",
        (("class", "--set", "whitelist.0=*", "--dry-run"),),
    ),
    Case(
        ("deploy-server", "serverclass", "update"),
        "write",
        (("class", "--set", "whitelist.0=*", "--dry-run"),),
    ),
    Case(("health", "check"), "read", ((),)),
    Case(("hec", "global-disable"), "write", (("--dry-run",),)),
    Case(("hec", "global-enable"), "write", (("--dry-run",),)),
    Case(("hec", "rotate"), "write", (("token", "--dry-run"),)),
    Case(("inspect",), "read", ((),)),
    Case(("kvstore", "records"), "read", (("records",),)),
    Case(("kvstore", "get"), "read", (("records", "key"),)),
    Case(
        ("kvstore", "insert"),
        "write",
        (("records", "--data", '{"value":"x"}', "--dry-run"),),
    ),
    Case(
        ("kvstore", "update"),
        "write",
        (("records", "key", "--data", '{"value":"x"}', "--dry-run"),),
    ),
    Case(("kvstore", "delete"), "write", (("records", "key", "--dry-run"),)),
    Case(("kvstore", "purge"), "write", (("records", "--dry-run"),)),
    Case(("license", "usage"), "read", ((),)),
    Case(("license", "get"), "read", (("license",),)),
    Case(("license", "list"), "read", ((),)),
    Case(
        ("lookup", "upload"),
        "write",
        (("--server-file", "/var/tmp/table.csv", "--app", "my_app", "--dry-run"),),
    ),
    Case(
        ("saved-search", "run"),
        "write",
        (("nightly", "--app", "my_app", "--earliest", "-1h", "--dry-run"),),
    ),
    Case(("search", "cancel"), "write", (("sid1", "--dry-run"),)),
    Case(("search", "get"), "read", (("sid1",),)),
    Case(("search", "list"), "read", ((),)),
    Case(
        ("search", "run"),
        "read",
        (("--query", "index=_internal", "--earliest", "-1h", "--max-rows", "5"),),
    ),
    Case(("server", "info"), "read", ((),)),
    Case(("server", "restart"), "write", (("--dry-run",),)),
    Case(("server", "settings", "get"), "read", ((),)),
    Case(("server", "settings", "set"), "write", (("--set", "host=x", "--dry-run"),)),
    Case(("shcluster", "status"), "read", ((),)),
)


def _generated_cases() -> tuple[Case, ...]:
    cases: list[Case] = []
    for spec in (INDEX, SAVED_SEARCH, *REGISTRY):
        for verb in spec.verbs:
            args = _VERB_ARGS[verb]
            if spec is SAVED_SEARCH and verb == "create":
                args = (*args, "--search", "index=x")
            cases.append(
                Case(
                    (spec.name, verb),
                    "read" if verb in {"list", "get"} else "write",
                    (args,),
                )
            )
    return tuple(cases)


CATALOG: tuple[Case, ...] = (*_generated_cases(), *_SPECIAL)


def iter_leaves(group: click.Group, path: tuple[str, ...] = ()):
    """Yield canonical Click leaves, excluding aliases."""
    for name, command in sorted(group.commands.items()):
        if isinstance(command, click.Group):
            yield from iter_leaves(command, (*path, name))
        else:
            yield (*path, name), command


def iter_groups(group: click.Group, path: tuple[str, ...] = ()):
    """Yield canonical Click groups."""
    yield path, group
    for name, command in sorted(group.commands.items()):
        if isinstance(command, click.Group):
            yield from iter_groups(command, (*path, name))


def help_invocations(root: click.Group) -> list[list[str]]:
    """Return canonical and alias help invocations without cataloguing aliases."""
    argvs: list[list[str]] = [["--help"]]
    for path, group in iter_groups(root):
        if path:
            argvs.append([*path, "--help"])
        if isinstance(group, AliasedGroup):
            argvs.extend([*path, alias, "--help"] for alias in group._aliases)
    argvs.extend([*path, "--help"] for path, _ in iter_leaves(root))
    return argvs
