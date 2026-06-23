"""The flat registry of factory-generated CRUD resources.

Each entry is data -- a :class:`~vct_splunk.core.resource.Spec` describing a
CRUD-shaped Splunk resource. ``cli.py`` loops over :data:`REGISTRY` and builds a
command group per spec via :func:`vct_splunk.commands.factory.build_group`.
Resources that do not fit the CRUD shape stay hand-written and are not listed here.

Field ``key`` values are the official Splunk REST form-field names, so the surface
stays familiar to a Splunk admin. Any field not given a typed option is still
reachable through the generic ``--set KEY=VALUE`` escape hatch.
"""

from __future__ import annotations

from ..core.resource import Field, Spec

# Verb set for inputs/outputs that also support enable/disable control endpoints.
# (Plain CRUD is the Spec default, so it does not need a named constant.)
_CRUD_TOGGLE = ("list", "get", "create", "update", "delete", "enable", "disable")

# Fields shared by most data inputs.
_INDEX_SOURCETYPE = (
    Field("index", key="index", help="Target index."),
    Field("sourcetype", key="sourcetype", help="Source type."),
)

# --- Access (#4) -------------------------------------------------------------

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

# --- Inputs / outputs (#6) ---------------------------------------------------
# Global, under /services/data/inputs|outputs. The HEC token's value is returned
# in the create response (the caller needs it); token rotation stays hand-written.

MONITOR_INPUT = Spec(
    name="monitor-input",
    path="/services/data/inputs/monitor",
    help="File and directory monitor inputs.",
    verbs=_CRUD_TOGGLE,
    fields=(
        *_INDEX_SOURCETYPE,
        Field("host", key="host", help="Host value for events."),
        Field("recursive", key="recursive", type="bool", help="Recurse into subdirectories."),
        Field("whitelist", key="whitelist", help="Allowlist regex."),
        Field("blacklist", key="blacklist", help="Denylist regex."),
    ),
)

TCP_INPUT = Spec(
    name="tcp-input",
    path="/services/data/inputs/tcp/raw",
    help="Raw TCP inputs.",
    verbs=_CRUD_TOGGLE,
    fields=(
        *_INDEX_SOURCETYPE,
        Field("connection_host", key="connection_host", help="Host from: ip|dns|none."),
    ),
)

UDP_INPUT = Spec(
    name="udp-input",
    path="/services/data/inputs/udp",
    help="UDP inputs.",
    verbs=_CRUD_TOGGLE,
    fields=(
        *_INDEX_SOURCETYPE,
        Field("connection_host", key="connection_host", help="Host from: ip|dns|none."),
    ),
)

SCRIPT_INPUT = Spec(
    name="script-input",
    path="/services/data/inputs/script",
    help="Scripted inputs.",
    verbs=_CRUD_TOGGLE,
    fields=(
        *_INDEX_SOURCETYPE,
        Field("interval", key="interval", help="Run interval (seconds or cron)."),
    ),
)

HEC_TOKEN = Spec(
    name="hec-token",
    path="/services/data/inputs/http",
    help="HTTP Event Collector tokens.",
    verbs=_CRUD_TOGGLE,
    fields=(
        *_INDEX_SOURCETYPE,
        Field("allowed_index", key="indexes", multi=True, help="Allowed index (repeatable)."),
        Field("source", key="source", help="Default source."),
    ),
)

OUTPUT_SERVER = Spec(
    name="output-server",
    path="/services/data/outputs/tcp/server",
    help="Forwarder output servers (forwarding destinations).",
    verbs=_CRUD_TOGGLE,
    fields=(Field("method", key="method", help="Routing: clone|balance|autobalance."),),
)

OUTPUT_GROUP = Spec(
    name="output-group",
    path="/services/data/outputs/tcp/group",
    help="Forwarder output groups.",
    verbs=_CRUD_TOGGLE,
    fields=(
        Field("server", key="servers", multi=True, help="Member server host:port (repeatable)."),
        Field("method", key="method", help="Routing: clone|balance|autobalance."),
    ),
)

# --- Knowledge objects (#8) --------------------------------------------------
# Namespaced. Tags, data models, and lookup-file upload stay hand-written.

MACRO = Spec(
    name="macro",
    path="configs/conf-macros",
    help="Search macros.",
    namespaced=True,
    fields=(
        Field("definition", key="definition", help="The macro expansion."),
        Field("args", key="args", help="Comma-separated argument names."),
        Field("iseval", key="iseval", type="bool", help="Definition is an eval expression."),
    ),
)

EVENTTYPE = Spec(
    name="eventtype",
    path="saved/eventtypes",
    help="Event types.",
    namespaced=True,
    fields=(
        Field("search", key="search", help="The search that defines the event type."),
        Field("description", key="description", help="Description."),
        Field("priority", key="priority", type="int", help="Priority (1-10)."),
    ),
)

EXTRACTION = Spec(
    name="extraction",
    path="data/transforms/extractions",
    help="Field extractions (transforms).",
    namespaced=True,
    fields=(
        Field("regex", key="REGEX", help="Extraction regular expression."),
        Field("format", key="FORMAT", help="Output format."),
    ),
)

LOOKUP_DEFINITION = Spec(
    name="lookup-definition",
    path="data/transforms/lookups",
    help="Lookup definitions (transforms).",
    namespaced=True,
    fields=(Field("filename", key="filename", help="Lookup table file name."),),
)

TAG = Spec(
    name="tag",
    path="saved/fvtags",
    help="Field-value tags (use --set to tie field=value to tag names).",
    namespaced=True,
    verbs=("list", "get", "create", "update", "delete"),
    # A tag entry ties a field=value pair to one or more tag names. The exact
    # keys vary by Splunk version, so only the obvious one is modeled and the
    # rest go through --set (validate-in-CI against a live instance).
    fields=(Field("tag", key="tag", multi=True, help="Tag name (repeatable)."),),
)

DATAMODEL = Spec(
    name="datamodel",
    path="datamodel/model",
    help="Data models (large JSON; use --set description/acceleration). Accelerate is separate.",
    namespaced=True,
    fields=(Field("description", key="description", help="Human description."),),
)

# --- KV Store (#9) -----------------------------------------------------------
# Only the collection schema is CRUD-shaped. Schema fields are dynamic
# (field.<name>=<type>), so they go through --set. Data records are a document
# store and stay hand-written.

KVSTORE_COLLECTION = Spec(
    name="kvstore-collection",
    path="storage/collections/config",
    help="KV Store collection schemas (use --set field.<name>=<type> for fields).",
    namespaced=True,
)

# --- Platform (#10) ----------------------------------------------------------
# Cluster control, restart, and peers are action/read endpoints and stay
# hand-written.

MESSAGE = Spec(
    name="message",
    path="/services/messages",
    help="System bulletin messages.",
    verbs=("list", "get", "create", "delete"),
    fields=(Field("value", key="value", help="Message text."),),
)

# --- Apps (#5) ---------------------------------------------------------------
# Lifecycle only. Install-from-file/URL (the appinstall endpoint) does not fit
# the CRUD shape and stays hand-written (see commands/apps.py).

APP = Spec(
    name="app",
    path="/services/apps/local",
    help="Installed apps (install from file/URL is separate).",
    verbs=("list", "get", "delete", "enable", "disable"),
)

REGISTRY: list[Spec] = [
    USER,
    ROLE,
    CAPABILITY,
    MONITOR_INPUT,
    TCP_INPUT,
    UDP_INPUT,
    SCRIPT_INPUT,
    HEC_TOKEN,
    OUTPUT_SERVER,
    OUTPUT_GROUP,
    MACRO,
    EVENTTYPE,
    EXTRACTION,
    LOOKUP_DEFINITION,
    TAG,
    DATAMODEL,
    KVSTORE_COLLECTION,
    MESSAGE,
    APP,
]
