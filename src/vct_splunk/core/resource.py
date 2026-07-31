"""A declarative CRUD engine for the many Splunk resources that share one shape.

Most Splunk admin resources are plain REST collections: list / get / create /
update / delete under a path, with form-encoded settings and an
``entry[].content`` body. Rather than hand-write a near-identical module per
resource, we describe each one as data (:class:`Spec`) and bind it to a single
generic :class:`CrudResource`. The command layer turns the same spec into a Click
group (see :mod:`vct_splunk.commands.factory`).

This is Click-free core. Resources that do NOT fit this shape (document stores,
secret-returning creates, action-only endpoints) stay hand-written.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .client import SplunkClient
from .errors import NotFoundError
from .namespace import ns_path

Verb = Literal["list", "get", "create", "update", "delete", "enable", "disable"]
FieldType = Literal["str", "int", "float", "bool"]


@dataclass(frozen=True)
class Field:
    """One create/update setting, mapping a friendly CLI option to a Splunk key.

    Attributes:
        opt: The CLI option / parameter stem, e.g. ``max_gb`` -> ``--max-gb``.
        key: The Splunk form field name to send, e.g. ``maxTotalDataSizeMB``.
        type: The value type (drives the Click option type).
        secret: True for a value never accepted as a flag (read from env/prompt).
        required: True when ``create`` cannot proceed without it (``update``
            never requires a field — it sends only what you pass).
        scale: Optional numeric multiplier, e.g. ``1024`` for GB -> MB.
        help: Help text for the generated option.
    """

    opt: str
    key: str
    type: FieldType = "str"
    secret: bool = False
    required: bool = False
    scale: float | None = None
    help: str = ""


@dataclass(frozen=True)
class Spec:
    """A declarative description of one CRUD-shaped Splunk resource.

    Attributes:
        name: The singular noun / command group, e.g. ``user``.
        path: The REST path. For a global resource this is the full
            ``/services/...`` path; for a ``namespaced`` resource it is the suffix
            under ``/servicesNS/<owner>/<app>/`` (e.g. ``configs/conf-macros``).
        help: Group help text.
        verbs: The verbs to expose; a read-only resource passes ``("list",)``.
        fields: The create/update settings.
        out_map: Splunk-content-key -> output-key. Empty means pass content through.
        namespaced: True for objects under ``/servicesNS/<owner>/<app>/``.
    """

    name: str
    path: str
    help: str
    verbs: tuple[Verb, ...] = ("list", "get", "create", "update", "delete")
    fields: tuple[Field, ...] = ()
    out_map: dict[str, str] = field(default_factory=dict)
    namespaced: bool = False


class CrudResource:
    """The generic CRUD operations for one :class:`Spec`, bound at construction.

    Namespaced resources take an ``owner`` and ``app`` (resolved by the command
    layer); global resources ignore them.
    """

    def __init__(self, spec: Spec) -> None:
        self.spec = spec

    def list(
        self, client: SplunkClient, *, owner: str | None = None, app: str | None = None
    ) -> list[dict[str, Any]]:
        return [self._out(e) for e in client.get_collection(self._base(owner, app))]

    def get(
        self, client: SplunkClient, name: str, *, owner: str | None = None, app: str | None = None
    ) -> dict[str, Any]:
        entries = client.get(f"{self._base(owner, app)}/{name}").get("entry") or []
        if not entries:
            raise NotFoundError(f"{self.spec.name.capitalize()} {name!r} not found.")
        return self._out(entries[0])

    def create(
        self,
        client: SplunkClient,
        name: str,
        *,
        fields: dict[str, Any],
        sets: tuple[str, ...] = (),
        owner: str | None = None,
        app: str | None = None,
    ) -> dict[str, Any]:
        data = self._body(fields, sets)
        data["name"] = name
        return self._unwrap(client.write("POST", self._base(owner, app), data))

    def update(
        self,
        client: SplunkClient,
        name: str,
        *,
        fields: dict[str, Any],
        sets: tuple[str, ...] = (),
        owner: str | None = None,
        app: str | None = None,
    ) -> dict[str, Any]:
        # Splunk's POST to the named object merges server-side, so only the
        # provided settings are sent (no read-modify-write).
        return self._unwrap(
            client.write("POST", f"{self._base(owner, app)}/{name}", self._body(fields, sets))
        )

    def delete(
        self, client: SplunkClient, name: str, *, owner: str | None = None, app: str | None = None
    ) -> dict[str, Any]:
        return client.write("DELETE", f"{self._base(owner, app)}/{name}", {})

    def control(
        self,
        client: SplunkClient,
        name: str,
        action: str,
        *,
        owner: str | None = None,
        app: str | None = None,
    ) -> dict[str, Any]:
        """Run a control action (``enable`` / ``disable``) on one object."""
        return self._unwrap(client.write("POST", f"{self._base(owner, app)}/{name}/{action}", {}))

    def _base(self, owner: str | None, app: str | None) -> str:
        if self.spec.namespaced:
            # The command layer always resolves owner/app for namespaced specs.
            return ns_path(self.spec.path, owner=owner or "-", app=app or "-")
        return self.spec.path

    def _body(self, fields: dict[str, Any], sets: tuple[str, ...]) -> dict[str, Any]:
        """Map provided options to Splunk form keys, then merge raw --set pairs."""
        by_opt = {f.opt: f for f in self.spec.fields}
        data: dict[str, Any] = {}
        for opt, value in fields.items():
            if value is None or value == ():
                continue
            f = by_opt[opt]
            if f.scale is not None:
                data[f.key] = int(float(value) * f.scale)
            elif f.type == "bool":
                data[f.key] = int(bool(value))
            else:
                data[f.key] = value
        for pair in sets:
            key, _, val = pair.partition("=")
            data[key] = val
        return data

    def _unwrap(self, result: dict[str, Any]) -> dict[str, Any]:
        if result.get("dry_run"):
            return result
        entries = result.get("entry") or []
        return self._out(entries[0]) if entries else result

    def _out(self, entry: dict[str, Any]) -> dict[str, Any]:
        content = entry.get("content") or {}
        acl = entry.get("acl") or {}
        # The name leads (first table column / JSON key); reassigning it after
        # the content merge keeps the entry name authoritative over any content
        # key of the same name.
        out: dict[str, Any] = {"name": entry.get("name")}
        if self.spec.out_map:
            for splunk_key, out_key in self.spec.out_map.items():
                out[out_key] = content.get(splunk_key)
        else:
            out.update(content)
        out["name"] = entry.get("name")
        if self.spec.namespaced:
            out["app"] = acl.get("app")
            out["owner"] = acl.get("owner")
            out["sharing"] = acl.get("sharing")
        return out
