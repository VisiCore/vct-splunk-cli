"""`splunk` CLI root. Shell layer (imports Click)."""

from __future__ import annotations

import click

from . import __version__
from .commands.api import api
from .commands.factory import build_group
from .commands.health import health
from .commands.index import index
from .commands.inspect import inspect
from .commands.registry import REGISTRY
from .commands.saved_search import saved_search
from .commands.search import search
from .commands.server import server


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, "--version", prog_name="splunk")
def cli() -> None:
    """Read, search, health-check, and safely administer Splunk Enterprise over its REST API."""


for _group in (server, api, index, search, saved_search, health):
    cli.add_command(_group)

cli.add_command(inspect)

# Factory-generated CRUD resources (users, roles, ...): each spec becomes a group.
for _spec in REGISTRY:
    cli.add_command(build_group(_spec))


def main() -> None:
    cli()
