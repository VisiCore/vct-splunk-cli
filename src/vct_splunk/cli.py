"""`splunk` CLI root. Shell layer (imports Click)."""

from __future__ import annotations

import click

from . import __version__
from .commands.api import api
from .commands.apps import app_install
from .commands.auth import auth
from .commands.cluster import cluster
from .commands.datamodel import datamodel_accelerate
from .commands.deploy import deploy
from .commands.factory import build_group
from .commands.health import health
from .commands.hec import hec
from .commands.inspect import inspect
from .commands.kvstore import kvstore
from .commands.license import license
from .commands.lookup import lookup
from .commands.registry import INDEX, REGISTRY
from .commands.saved_search import saved_search
from .commands.search import search
from .commands.server import server
from .commands.shcluster import shcluster


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, "--version", prog_name="splunk")
def cli() -> None:
    """Read, search, health-check, and safely administer Splunk Enterprise over its REST API."""


for _group in (
    server,
    api,
    build_group(INDEX),
    search,
    saved_search,
    health,
    auth,
    kvstore,
    cluster,
    shcluster,
    license,
    deploy,
    hec,
    lookup,
):
    cli.add_command(_group)

cli.add_command(inspect)

# Factory-generated CRUD resources (users, roles, ...): each spec becomes a group.
# The 'app' group's install-from-file/URL command does not fit the CRUD shape, so
# it is hand-written and attached to the generated group here.
for _spec in REGISTRY:
    _grp = build_group(_spec)
    if _spec.name == "app":
        _grp.add_command(app_install)
    elif _spec.name == "datamodel":
        _grp.add_command(datamodel_accelerate)
    cli.add_command(_grp)


def main() -> None:
    cli()
