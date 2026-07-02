"""Build a Click command group from a declarative resource :class:`Spec`.

One :func:`build_group` turns a spec into a ``list`` / ``get`` / ``create`` /
``update`` / ``delete`` (and optional ``enable`` / ``disable``) group, wired to
the same shared helpers the hand-written commands use: ``@command`` for the shared
options and error mapping, :func:`do_write` for gated writes, namespace resolution
for namespaced resources, and a generic ``--set KEY=VALUE`` escape hatch so a spec
rarely needs more than a path.
"""

from __future__ import annotations

import os
import sys
from typing import Any

import click

from ..core.errors import UsageError
from ..core.namespace import resolve_ns
from ..core.resource import CrudResource, Field, Spec
from . import output as out
from .context import AliasedGroup, command
from .dispatch import dispatch_list, has_cloud_list
from .write import do_write

_VERB_ALIASES = {"add": "create", "edit": "update", "remove": "delete"}


def _help_for(spec: Spec, verb: str) -> str:
    """One-line help for a generated command, in the hand-written commands' style."""
    noun = spec.name.replace("-", " ")
    gated = " Gated write (--dry-run previews; --yes when non-interactive)."
    ns = " Requires an app (--app or $SPLUNK_APP)." if spec.namespaced else ""
    texts = {
        "list": f"List every {noun}.",
        "get": f"Show one {noun}.",
        "create": f"Create a {noun}.{gated}{ns}",
        "update": f"Update a {noun} (only the fields you pass).{gated}{ns}",
        "delete": f"Delete a {noun}.{gated}{ns}",
        "enable": f"Enable a {noun}.{gated}",
        "disable": f"Disable a {noun}.{gated}",
    }
    return texts[verb]


def build_group(spec: Spec) -> click.Group:
    """Return the Click group for *spec*, exposing only the verbs it declares."""
    res = CrudResource(spec)
    aliases = {a: t for a, t in _VERB_ALIASES.items() if t in spec.verbs}

    @click.group(name=spec.name, cls=AliasedGroup, aliases=aliases, help=spec.help)
    def grp() -> None:
        pass

    if "list" in spec.verbs:

        @grp.command("list", help=_help_for(spec, "list"))
        @command
        def _list(ctx) -> None:
            # Resources both backends serve (index/role/hec-token) route by the
            # deduced backend: ACS on Cloud, REST otherwise. These specs are not
            # namespaced, so there is no owner/app to resolve for the Cloud path.
            if has_cloud_list(spec.name):
                out.emit(
                    dispatch_list(ctx, spec.name, lambda c: res.list(c, owner=None, app=None)),
                    ctx.output_mode,
                    ctx.meta(),
                )
                return
            owner, app = _ns(ctx, spec, for_write=False)
            with ctx.client() as c:
                out.emit(res.list(c, owner=owner, app=app), ctx.output_mode, ctx.meta())

    if "get" in spec.verbs:

        @grp.command("get", help=_help_for(spec, "get"))
        @click.argument("name")
        @command
        def _get(ctx, name) -> None:
            owner, app = _ns(ctx, spec, for_write=False)
            with ctx.client() as c:
                out.emit(res.get(c, name, owner=owner, app=app), ctx.output_mode, ctx.meta())

    if "create" in spec.verbs:

        @grp.command("create", help=_help_for(spec, "create"))
        @click.argument("name")
        @_field_options(spec)
        @command
        def _create(ctx, name, **opts) -> None:
            owner, app = _ns(ctx, spec, for_write=True)
            fields, sets = _collect_fields(spec, opts)
            result = do_write(
                ctx,
                action=f"create {spec.name} '{name}'",
                audit_event={"action": f"{spec.name}.create", "name": name},
                run=lambda c: res.create(c, name, fields=fields, sets=sets, owner=owner, app=app),
            )
            out.emit(result, ctx.output_mode, ctx.meta())

    if "update" in spec.verbs:

        @grp.command("update", help=_help_for(spec, "update"))
        @click.argument("name")
        @_field_options(spec)
        @command
        def _update(ctx, name, **opts) -> None:
            owner, app = _ns(ctx, spec, for_write=True)
            fields, sets = _collect_fields(spec, opts)
            if not sets and all(v in (None, ()) for v in fields.values()):
                raise UsageError("Nothing to update. Pass a field option or --set KEY=VALUE.")
            result = do_write(
                ctx,
                action=f"update {spec.name} '{name}'",
                audit_event={"action": f"{spec.name}.update", "name": name},
                run=lambda c: res.update(c, name, fields=fields, sets=sets, owner=owner, app=app),
            )
            out.emit(result, ctx.output_mode, ctx.meta())

    if "delete" in spec.verbs:

        @grp.command("delete", help=_help_for(spec, "delete"))
        @click.argument("name")
        @command
        def _delete(ctx, name) -> None:
            owner, app = _ns(ctx, spec, for_write=True)
            result = do_write(
                ctx,
                action=f"delete {spec.name} '{name}'",
                audit_event={"action": f"{spec.name}.delete", "name": name},
                run=lambda c: res.delete(c, name, owner=owner, app=app),
            )
            out.emit(result, ctx.output_mode, ctx.meta())

    for _verb in ("enable", "disable"):
        if _verb in spec.verbs:
            _add_control(grp, spec, res, _verb)

    return grp


def _add_control(grp: click.Group, spec: Spec, res: CrudResource, verb: str) -> None:
    """Register an enable/disable control command (kept in a helper to bind *verb*)."""

    @grp.command(verb, help=_help_for(spec, verb))
    @click.argument("name")
    @command
    def _control(ctx, name) -> None:
        owner, app = _ns(ctx, spec, for_write=True)
        result = do_write(
            ctx,
            action=f"{verb} {spec.name} '{name}'",
            audit_event={"action": f"{spec.name}.{verb}", "name": name},
            run=lambda c: res.control(c, name, verb, owner=owner, app=app),
        )
        out.emit(result, ctx.output_mode, ctx.meta())


def _field_options(spec: Spec):
    """A decorator that adds one Click option per (non-secret) field, plus --set."""
    options = []
    for f in spec.fields:
        if f.secret:
            continue  # secrets are read from env / prompt, never a flag
        options.append(_option_for(f))
    options.append(
        click.option(
            "--set",
            "_set",
            multiple=True,
            metavar="KEY=VALUE",
            help="Raw Splunk field (repeatable).",
        )
    )

    def decorate(fn):
        for option in reversed(options):
            fn = option(fn)
        return fn

    return decorate


def _option_for(f: Field):
    dashed = f.opt.replace("_", "-")
    if f.type == "bool":
        return click.option(f"--{dashed}/--no-{dashed}", f.opt, default=None, help=f.help)
    kwargs: dict[str, Any] = {"default": None, "help": f.help}
    if f.multi:
        kwargs["multiple"] = True
    if f.type == "int":
        kwargs["type"] = int
    elif f.type == "float":
        kwargs["type"] = float
    return click.option(f"--{dashed}", f.opt, **kwargs)


def _collect_fields(spec: Spec, opts: dict[str, Any]) -> tuple[dict[str, Any], tuple[str, ...]]:
    """Split Click options into (field values, --set pairs), resolving secrets."""
    values = dict(opts)
    sets: tuple[str, ...] = tuple(values.pop("_set", ()))
    for f in spec.fields:
        if not f.secret:
            continue
        env = f"SPLUNK_{spec.name.upper().replace('-', '_')}_{f.opt.upper()}"
        secret = os.environ.get(env)
        if secret is None and sys.stdin.isatty() and sys.stderr.isatty():
            secret = click.prompt(f.opt.replace("_", " "), hide_input=True, err=True)
        if secret is not None:
            values[f.opt] = secret
    return values, sets


def _ns(ctx: Any, spec: Spec, *, for_write: bool) -> tuple[str | None, str | None]:
    """Resolve (owner, app) for a namespaced spec; global specs ignore them."""
    if not spec.namespaced:
        return (None, None)
    return resolve_ns(ctx.owner, ctx.app, for_write=for_write)
