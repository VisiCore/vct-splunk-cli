"""The one shared write path for every mutation. Shell layer.

Every gated write -- hand-written or factory-generated -- runs through
:func:`do_write`, so target resolution, both write-enable gates, backend
routing, the confirmation gate, and audit logging all live in exactly one
place.

This function is also the seam for the larger write-safety framework (#12):
deferred pieces such as plan tokens, optimistic concurrency, and a freeze-writes
kill switch would all belong *inside* it. Add each only when a real second
writer needs it; today the call sites need exactly the gates + audit below.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

import click

from ..api.acs.client import AcsClient, acs_config_from_env
from ..api.acs.operations import cloud_write
from ..config.loader import load_config, resolve_target
from ..output import formatter as out
from ..utils import audit
from ..utils.backends import cloud_stack_from_url
from ..utils.errors import UnsupportedBackendError, UsageError
from ..utils.redact import safe_target
from .dispatch import has_cloud_write

#: Opt-in required for every real mutation.
ENABLE_WRITES_ENV = "SPLUNK_ENABLE_WRITES"

#: Additional opt-in for supported Cloud writes and previews.
CLOUD_WRITE_ENV = "SPLUNK_CLOUD_WRITE"


def do_write(
    ctx: Any,
    *,
    action: str,
    audit_event: dict[str, Any],
    run: Callable[[Any], dict[str, Any]],
    target: str | None = None,
    name: str | None = None,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Confirm, dispatch, and audit a mutation after its backend gates."""
    resource, _, verb = str(audit_event.get("action", "")).partition(".")
    refuse_cloud_write(ctx, resource, verb)
    if not ctx.dry_run:
        _require_writes_enabled(resource, verb)
    backend = getattr(ctx, "backend", "enterprise")
    if target is None:
        if backend == "cloud":
            # A Cloud write authenticates to ACS, not splunkd, so resolving the
            # target must not go through `load_config` -- that function demands
            # a splunkd credential (SPLUNK_TOKEN et al.) this path never needs.
            target = resolve_target(ctx.base_url, getattr(ctx, "profile", None))[0].base_url
        else:
            target = load_config(ctx.base_url, profile=getattr(ctx, "profile", None)).base_url
    out.confirm_write(ctx, action, safe_target(target))
    audit_target = safe_target(target)
    if backend == "cloud":
        stack = cloud_stack_from_url(ctx.base_url)
        config = acs_config_from_env(stack, write=True)
        audit_target = safe_target(f"{config.base_url}/{config.stack}")
        config.dry_run = ctx.dry_run
        with AcsClient(config) as c:
            result = cloud_write(c, resource, verb, name or "", body)
    else:
        with ctx.client() as c:
            result = run(c)
    if not (isinstance(result, dict) and result.get("dry_run")):
        try:
            audit.record({**audit_event, "target": audit_target})
        except OSError:
            click.echo(
                "Warning: the write succeeded, but its audit record could not be saved; "
                "check VCT_SPLUNK_AUDIT and the default audit path.",
                err=True,
            )
    return result


def refuse_cloud_write(ctx: Any, resource: str, verb: str) -> None:
    """Reject unsupported Cloud mutations or a missing Cloud opt-in.

    The opt-in also applies to previews because it proves the resource has an ACS route.
    """
    if getattr(ctx, "backend", "enterprise") != "cloud":
        return
    if not has_cloud_write(resource, verb):
        raise UnsupportedBackendError(resource or "this resource", verb or "write", "cloud")
    if os.environ.get(CLOUD_WRITE_ENV) != "true":
        raise UsageError(
            f"Splunk Cloud writes are disabled by default. Set {CLOUD_WRITE_ENV}=true "
            f"to allow `{resource} {verb}` (there is no CLI flag for this)."
        )


def _require_writes_enabled(resource: str, verb: str) -> None:
    """Require the shared opt-in before a real write."""
    if os.environ.get(ENABLE_WRITES_ENV) == "true":
        return
    raise UsageError(
        f"Writes are disabled by default. Set {ENABLE_WRITES_ENV}=true to allow "
        f"`{resource} {verb}` (there is no CLI flag for this)."
    )
