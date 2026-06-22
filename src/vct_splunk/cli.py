"""`splunk` CLI root. Shell layer (imports Click)."""

from __future__ import annotations

import click

from . import __version__
from .cmd_api import api
from .cmd_health import health
from .cmd_index import index
from .cmd_search import search
from .cmd_server import server


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, "--version", prog_name="splunk")
def cli() -> None:
    """Read, search, health-check, and safely administer Splunk Enterprise over its REST API."""


for _group in (server, api, index, search, health):
    cli.add_command(_group)


def main() -> None:
    cli()
