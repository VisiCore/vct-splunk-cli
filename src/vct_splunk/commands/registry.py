"""The flat registry of factory-generated CRUD resources.

Each entry is data -- a :class:`~vct_splunk.core.resource.Spec` describing a
CRUD-shaped Splunk resource. ``cli.py`` loops over :data:`REGISTRY` and builds a
command group per spec via :func:`vct_splunk.commands.factory.build_group`.
Resources that do not fit the CRUD shape stay hand-written and are not listed here.

Field ``key`` values are the official Splunk REST form-field names, so the surface
stays familiar to a Splunk admin.
"""

from __future__ import annotations

from ..core.resource import Field, Spec

USER = Spec(
    name="user",
    path="/services/authentication/users",
    help="Splunk users (local authentication).",
    fields=(
        Field(
            "password",
            key="password",
            secret=True,
            help="Initial password (from $SPLUNK_USER_PASSWORD or a prompt; never a flag).",
        ),
        Field("role", key="roles", multi=True, help="Role to assign (repeatable)."),
        Field("email", key="email", help="Email address."),
        Field("realname", key="realname", help="Full name."),
        Field("default_app", key="defaultApp", help="Default app on login."),
    ),
    out_map={
        "realname": "real_name",
        "email": "email",
        "roles": "roles",
        "defaultApp": "default_app",
        "type": "auth_type",
    },
)

ROLE = Spec(
    name="role",
    path="/services/authorization/roles",
    help="Splunk roles (authorization).",
    fields=(
        Field(
            "capability", key="capabilities", multi=True, help="Capability to grant (repeatable)."
        ),
        Field(
            "imported_role", key="imported_roles", multi=True, help="Role to inherit (repeatable)."
        ),
        Field(
            "search_index",
            key="srchIndexesAllowed",
            multi=True,
            help="Allowed search index (repeatable).",
        ),
        Field(
            "default_index",
            key="srchIndexesDefault",
            multi=True,
            help="Default search index (repeatable).",
        ),
        Field(
            "search_quota",
            key="srchJobsQuota",
            type="int",
            help="Concurrent historical search quota.",
        ),
    ),
    out_map={
        "imported_roles": "imported_roles",
        "srchIndexesAllowed": "search_indexes",
        "srchJobsQuota": "search_quota",
    },
)

CAPABILITY = Spec(
    name="capability",
    path="/services/authorization/capabilities",
    help="Authorization capabilities (read-only).",
    verbs=("list",),
)

REGISTRY: list[Spec] = [USER, ROLE, CAPABILITY]
