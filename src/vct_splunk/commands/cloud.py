"""`splunk cloud` -- read-only Splunk Cloud (ACS) commands.

These target the ACS adminconfig/v2 API (a separate client and credentials,
``SPLUNK_ACS_STACK`` / ``SPLUNK_ACS_TOKEN``), not splunkd. Read-only this release;
cloud coverage is not yet certified against a live stack.
"""

from __future__ import annotations

import click

from ..core.acs import operations
from ..core.acs.client import AcsClient, AcsConfig, acs_config_from_env
from . import output as out
from .context import command


@click.group()
def cloud() -> None:
    """Splunk Cloud (ACS) -- read-only this release."""


def _meta(config: AcsConfig) -> dict[str, str]:
    return {"backend": "cloud", "stack": config.stack}


@cloud.command("indexes")
@command
def indexes(ctx) -> None:
    """List Cloud indexes (ACS, read-only)."""
    config = acs_config_from_env()
    with AcsClient(config) as c:
        out.emit(operations.list_cloud_indexes(c), ctx.output_mode, _meta(config))


@cloud.command("hec-tokens")
@command
def hec_tokens(ctx) -> None:
    """List Cloud HEC tokens (ACS, read-only)."""
    config = acs_config_from_env()
    with AcsClient(config) as c:
        out.emit(operations.list_hec_tokens(c), ctx.output_mode, _meta(config))


@cloud.command("roles")
@command
def roles(ctx) -> None:
    """List Cloud roles (ACS, read-only)."""
    config = acs_config_from_env()
    with AcsClient(config) as c:
        out.emit(operations.list_cloud_roles(c), ctx.output_mode, _meta(config))
