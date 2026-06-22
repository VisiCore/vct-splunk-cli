"""`splunk` CLI root. Shell layer (imports Click)."""

from __future__ import annotations

import click

from . import __version__
from .commands.api import api
from .commands.health import health
from .commands.index import index
from .commands.search import search
from .commands.server import server


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, "--version", prog_name="splunk")
def cli() -> None:
    """Read, search, health-check, and safely administer Splunk Enterprise over its REST API."""


for _group in (server, api, index, search, health):
    cli.add_command(_group)


def main() -> None:
    cli()
