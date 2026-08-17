"""The one shared write path for every mutation. Shell layer.

Every gated write -- hand-written or factory-generated -- runs through
:func:`do_write`, so target resolution, the confirmation gate, and audit logging
live in exactly one place.

This function is also the seam for the larger write-safety framework (#12):
deferred pieces such as plan tokens, optimistic concurrency, and a freeze-writes
kill switch would all belong *inside* it. Add each only when a real second
writer needs it; today the call sites need exactly the gate + audit below.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from ..api.acs.client import AcsClient, acs_config_from_env
from ..config.loader import _resolve_target, load_config
from ..output import formatter as out
from ..utils import audit
from ..utils.backends import cloud_stack_from_url
from ..utils.errors import UnsupportedBackendError
from ..utils.redact import public_target, safe_target
from .dispatch import has_cloud_write

#: Opt-in for Splunk Cloud writes. Never a CLI flag -- see `refuse_cloud_write`.
CLOUD_WRITE_ENV = "SPLUNK_CLOUD_WRITE"


def do_write(
    ctx: Any,
    *,
    action: str,
    audit_event: dict[str, Any],
    run: Callable[[Any], dict[str, Any]],
    target: str | None = None,
) -> dict[str, Any]:
    """Run one gated mutation: confirm it, execute it, and audit it.

    Resolves the target up front (so a missing ``SPLUNK_URL`` / credential
    fails before we prompt), gates the write via :func:`output.confirm_write`
    (dry-run / ``--yes`` / non-interactive fail-fast), runs ``run(client)``, and
    appends an audit record for any real (non-dry-run) write.

    Args:
        ctx: The command :class:`~vct_splunk.commands.context.Ctx`.
        action: A human phrase for the prompt, e.g. ``"create index 'web'"``.
        audit_event: Fields to record on a real write; ``target`` is added here.
        run: Callable given an open client (a ``SplunkClient`` on Enterprise, an
            ``AcsClient`` for an opted-in Cloud write), returning the result.
        target: The Splunk URL; resolved from the environment when omitted.

    Returns:
        The operation result, ready for :func:`output.emit`.
    """
    # audit_event["action"] is "<resource>.<verb>", e.g. "index.create".
    resource, _, verb = str(audit_event.get("action", "")).partition(".")
    refuse_cloud_write(ctx, resource, verb)
    backend = getattr(ctx, "backend", "enterprise")
    if target is None:
        if backend == "cloud":
            # A Cloud write authenticates to ACS, not splunkd, so resolving the
            # target must not go through `load_config` -- that function demands
            # a splunkd credential (SPLUNK_TOKEN et al.) this path never needs.
            target = _resolve_target(ctx.base_url, getattr(ctx, "profile", None))[0].base_url
        else:
            target = load_config(ctx.base_url, profile=getattr(ctx, "profile", None)).base_url
    out.confirm_write(ctx, action, public_target(target))
    if backend == "cloud":
        stack = cloud_stack_from_url(ctx.base_url)
        config = acs_config_from_env(stack, write=True)
        config.dry_run = ctx.dry_run
        with AcsClient(config) as c:
            result = run(c)
    else:
        with ctx.client() as c:
            result = run(c)
    if not (isinstance(result, dict) and result.get("dry_run")):
        audit.record({**audit_event, "target": safe_target(target)})
    return result


def refuse_cloud_write(ctx: Any, resource: str, verb: str) -> None:
    """Stop a mutation aimed at a Splunk Cloud stack, unless explicitly opted in.

    Cloud writes are opt-in and narrow: only create/update/delete for index,
    role, and hec-token (the ACS mutation routes declared in
    :mod:`vct_splunk.commands.dispatch`) are ever allowed, and only when
    ``SPLUNK_CLOUD_WRITE=true`` is set in the environment -- there is no CLI
    flag for it, so a script cannot flip it on by accident. Every other Cloud
    mutation -- including enable/disable on those same three resources, and
    every verb on every other resource -- always raises before any network is
    touched, opt-in or not. The env var alone never bypasses confirmation:
    :func:`do_write` still runs `output.confirm_write` (``--yes``/TTY) after
    this check passes.

    :func:`do_write` calls this, which is enough for a command that reaches the
    gate directly. A command that first resolves a namespace calls it earlier
    as well, so a Cloud target is told writes are unsupported rather than being
    asked for an ``--app`` that would not have helped.
    """
    if getattr(ctx, "backend", "enterprise") != "cloud":
        return
    if os.environ.get(CLOUD_WRITE_ENV) == "true" and has_cloud_write(resource, verb):
        return
    raise UnsupportedBackendError(resource or "this resource", verb or "write", "cloud")
