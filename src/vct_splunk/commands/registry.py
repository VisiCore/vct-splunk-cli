"""The flat registry of factory-generated CRUD resources.

Each entry is data -- a :class:`~vct_splunk.core.resource.Spec` describing a
CRUD-shaped Splunk resource. ``cli.py`` loops over :data:`REGISTRY` and builds a
command group per spec via :func:`vct_splunk.commands.factory.build_group`.
Resources that do not fit the CRUD shape stay hand-written and are not listed here.

Specs are intentionally thin: a path, help text, and the verbs/flags that shape
the command surface. Settings flow through the generic ``--set KEY=VALUE`` escape
hatch, where ``KEY`` is the official Splunk REST form-field name, and Splunk
validates them server-side. The lone exception is the ``user`` password, which
stays a typed secret field so it is read from the environment, never a flag.
"""

from __future__ import annotations

from ..core.resource import Field, Spec

# Verb set for inputs/outputs that also support enable/disable control endpoints.
# (Plain CRUD is the Spec default, so it does not need a named constant.)
_CRUD_TOGGLE = ("list", "get", "create", "update", "delete", "enable", "disable")

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
    ),
)

ROLE = Spec(
    name="role",
    path="/services/authorization/roles",
    help="Splunk roles (authorization).",
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
)

TCP_INPUT = Spec(
    name="tcp-input",
    path="/services/data/inputs/tcp/raw",
    help="Raw TCP inputs.",
    verbs=_CRUD_TOGGLE,
)

UDP_INPUT = Spec(
    name="udp-input",
    path="/services/data/inputs/udp",
    help="UDP inputs.",
    verbs=_CRUD_TOGGLE,
)

SCRIPT_INPUT = Spec(
    name="script-input",
    path="/services/data/inputs/script",
    help="Scripted inputs.",
    verbs=_CRUD_TOGGLE,
)

HEC_TOKEN = Spec(
    name="hec-token",
    path="/services/data/inputs/http",
    help="HTTP Event Collector tokens.",
    verbs=_CRUD_TOGGLE,
)

OUTPUT_SERVER = Spec(
    name="output-server",
    path="/services/data/outputs/tcp/server",
    help="Forwarder output servers (forwarding destinations).",
    verbs=_CRUD_TOGGLE,
)

OUTPUT_GROUP = Spec(
    name="output-group",
    path="/services/data/outputs/tcp/group",
    help="Forwarder output groups.",
    verbs=_CRUD_TOGGLE,
)

# --- Knowledge objects (#8) --------------------------------------------------
# Namespaced. Tags, data models, and lookup-file upload stay hand-written.

MACRO = Spec(
    name="macro",
    path="configs/conf-macros",
    help="Search macros.",
    namespaced=True,
)

EVENTTYPE = Spec(
    name="eventtype",
    path="saved/eventtypes",
    help="Event types.",
    namespaced=True,
)

EXTRACTION = Spec(
    name="extraction",
    path="data/transforms/extractions",
    help="Field extractions (transforms).",
    namespaced=True,
)

LOOKUP_DEFINITION = Spec(
    name="lookup-definition",
    path="data/transforms/lookups",
    help="Lookup definitions (transforms).",
    namespaced=True,
)

TAG = Spec(
    name="tag",
    path="saved/fvtags",
    help="Field-value tags (settings via --set).",
    namespaced=True,
    verbs=("list", "get", "create", "update", "delete"),
)

DATAMODEL = Spec(
    name="datamodel",
    path="datamodel/model",
    help="Data models (settings via --set). Acceleration is a separate command.",
    namespaced=True,
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
)

# --- Apps (#5) ---------------------------------------------------------------
# Lifecycle only. Install-from-file/URL is a multipart upload and stays
# hand-written.

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
