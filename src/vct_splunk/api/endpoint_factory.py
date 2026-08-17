"""Generic CRUD endpoint factory for Splunk REST resources. Click-free.

Mirrors the cribl-cli ``api/endpoint_factory`` design: most admin resources are
plain REST collections — list / get / create / update / delete under a path,
with form-encoded settings and an ``entry[].content`` response body. Rather
than hand-write a near-identical module per resource, each one is described as
data (:class:`EndpointConfig`) and bound to a single generic :class:`Endpoints`
class. The command layer turns the same config into a Click group (see
:mod:`vct_splunk.commands.command_factory`).

Two URL scopes exist (the Splunk analogue of cribl's group/global scopes):

============  =========================================================
Scope         URL pattern
============  =========================================================
``global``    ``/services/{path}``  (path is given absolute)
``namespaced``  ``/servicesNS/{owner}/{app}/{path}``
============  =========================================================

Resources that do NOT fit this shape (document stores, secret-returning
creates, action-only endpoints) stay hand-written in
:mod:`vct_splunk.api.endpoints`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from ..utils.errors import NotFoundError
from ..utils.namespace import ns_path
from ..utils.path import absolute_path_segment, path_segment
from ..utils.redact import redact_secrets
from .client import SplunkClient

Scope = Literal["global", "namespaced"]
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
class EndpointConfig:
    """A declarative description of one CRUD-shaped Splunk resource.

    Attributes:
        name: The singular noun / command group, e.g. ``user``.
        path: The REST path. For a ``global`` resource this is the full
            ``/services/...`` path; for a ``namespaced`` resource it is the
            suffix under ``/servicesNS/<owner>/<app>/`` (e.g.
            ``configs/conf-macros``).
        help: Group help text.
        verbs: The verbs to expose; a read-only resource passes ``("list",)``.
        fields: The create/update settings.
        out_map: Splunk-content-key -> output-key. Empty means pass content through.
        scope: ``"global"`` or ``"namespaced"`` (see the module docstring).
        absolute_name: True when Splunk identifies the resource by an absolute
            server path, as monitor inputs do.
        mints_secret: True when ``create`` produces a credential the caller cannot
            get any other way, so its response may show it. Off for everything
            else, including resources that *accept* a secret (a user password),
            whose create response must not echo it back.
    """

    name: str
    path: str
    help: str
    verbs: tuple[Verb, ...] = ("list", "get", "create", "update", "delete")
    fields: tuple[Field, ...] = ()
    out_map: dict[str, str] = field(default_factory=dict)
    scope: Scope = "global"
    absolute_name: bool = False
    mints_secret: bool = False


class Endpoints:
    """The generic CRUD operations for one :class:`EndpointConfig`.

    Namespaced resources take an ``owner`` and ``app`` (resolved by the command
    layer); global resources ignore them.
    """

    def __init__(self, config: EndpointConfig) -> None:
        self.config = config

    def list(
        self, client: SplunkClient, *, owner: str | None = None, app: str | None = None
    ) -> list[dict[str, Any]]:
        return [self._out(e) for e in client.get_collection(self._base(owner, app))]

    def get(
        self, client: SplunkClient, name: str, *, owner: str | None = None, app: str | None = None
    ) -> dict[str, Any]:
        encoded = self.validate_name(name)
        entries = client.get(f"{self._base(owner, app)}/{encoded}").get("entry") or []
        if not entries:
            raise NotFoundError(f"{self.config.name.capitalize()} {name!r} not found.")
        return self._out(entries[0])

    def create(
        self,
        client: SplunkClient,
        name: str,
        *,
        fields: dict[str, Any],
        sets: dict[str, str] | None = None,
        owner: str | None = None,
        app: str | None = None,
    ) -> dict[str, Any]:
        data = self._body(fields, sets)
        self.validate_name(name)
        data["name"] = name
        # Only a config that mints a credential may show one, and only here: the
        # value exists nowhere else afterwards. A config that merely accepts a
        # secret, as `user` does with a password, must not have it echoed back.
        return self._unwrap(
            client.write("POST", self._base(owner, app), data),
            reveal_secrets=self.config.mints_secret,
        )

    def update(
        self,
        client: SplunkClient,
        name: str,
        *,
        fields: dict[str, Any],
        sets: dict[str, str] | None = None,
        owner: str | None = None,
        app: str | None = None,
    ) -> dict[str, Any]:
        # Splunk's POST to the named object merges server-side, so only the
        # provided settings are sent (no read-modify-write).
        encoded = self.validate_name(name)
        return self._unwrap(
            client.write("POST", f"{self._base(owner, app)}/{encoded}", self._body(fields, sets))
        )

    def delete(
        self, client: SplunkClient, name: str, *, owner: str | None = None, app: str | None = None
    ) -> dict[str, Any]:
        encoded = self.validate_name(name)
        return client.write("DELETE", f"{self._base(owner, app)}/{encoded}", {})

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
        encoded = self.validate_name(name)
        return self._unwrap(
            client.write("POST", f"{self._base(owner, app)}/{encoded}/{action}", {})
        )

    def _base(self, owner: str | None, app: str | None) -> str:
        if self.config.scope == "namespaced":
            # The command layer always resolves owner/app for namespaced configs.
            return ns_path(self.config.path, owner=owner or "-", app=app or "-")
        return self.config.path

    def validate_name(self, name: str) -> str:
        """Validate and encode the config's supported identifier shape."""
        if self.config.absolute_name:
            return absolute_path_segment(name, label=f"{self.config.name} name")
        return path_segment(name, label=f"{self.config.name} name")

    def _body(self, fields: dict[str, Any], sets: dict[str, str] | None) -> dict[str, Any]:
        """Map provided options to Splunk form keys, then merge raw --set pairs."""
        by_opt = {f.opt: f for f in self.config.fields}
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
        data.update(sets or {})
        return data

    def _unwrap(self, result: dict[str, Any], *, reveal_secrets: bool = False) -> dict[str, Any]:
        if result.get("dry_run"):
            return result
        entries = result.get("entry") or []
        return self._out(entries[0], reveal_secrets=reveal_secrets) if entries else result

    def _out(self, entry: dict[str, Any], *, reveal_secrets: bool = False) -> dict[str, Any]:
        content = entry.get("content") or {}
        if not reveal_secrets:
            # Splunk returns secrets in ordinary reads -- an HTTP Event Collector
            # input carries its own token -- so browsing a resource would print
            # every credential it holds. Only a command whose purpose is to mint
            # one passes reveal_secrets.
            content = redact_secrets(content)
        acl = entry.get("acl") or {}
        # The name leads (first table column / JSON key); reassigning it after
        # the content merge keeps the entry name authoritative over any content
        # key of the same name.
        out: dict[str, Any] = {"name": entry.get("name")}
        if self.config.out_map:
            for splunk_key, out_key in self.config.out_map.items():
                out[out_key] = content.get(splunk_key)
        else:
            out.update(content)
        out["name"] = entry.get("name")
        if self.config.scope == "namespaced":
            out["app"] = acl.get("app")
            out["owner"] = acl.get("owner")
            out["sharing"] = acl.get("sharing")
        return out


def create_endpoints(config: EndpointConfig) -> Endpoints:
    """Bind one :class:`EndpointConfig` to the generic CRUD engine."""
    return Endpoints(config)
