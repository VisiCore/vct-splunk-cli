"""One definition of "this value is a secret", and how to hide it.

Splunk returns secrets inside ordinary response bodies: a server setting holds
``pass4SymmKey``, an HTTP Event Collector input holds its ``token``. Whether a
field is secret is a property of the field, not of the endpoint that returned
it, so the rule lives here and every read applies it — rather than each
operation remembering which of its own fields to hide.

Deciding by key name, not by an allowlist per resource, is deliberate: a field
Splunk adds to an endpoint later is covered the day it appears, with no spec to
update. Commands whose purpose is to mint a credential (``auth login``,
``hec rotate``, ``hec-token create``) opt out explicitly.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit, urlunsplit

#: What a hidden value is replaced with. The key stays, so a caller can still
#: see that the field exists.
REDACTED = "<redacted>"

_SECRET_MARKERS = ("pass4symmkey", "password", "passwd", "secret", "token")


def is_secret_key(key: object) -> bool:
    """True if a field with this name carries a secret.

    Matching ignores case, underscores, and hyphens, so ``pass4SymmKey``,
    ``hec_token``, and ``client-secret`` are all recognized.
    """
    normalized = str(key).casefold().replace("_", "").replace("-", "")
    return any(marker in normalized for marker in _SECRET_MARKERS)


def redact_secrets(value: Any) -> Any:
    """Return *value* with every secret-named field replaced, at any depth."""
    if isinstance(value, dict):
        return {
            key: REDACTED if is_secret_key(key) else redact_secrets(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    return value


def safe_target(target: str) -> str:
    """Return *target* with URL credentials and query components removed.

    A Splunk URL may carry `user:password@`, and the target is printed in
    prompts, JSON metadata, and the audit log. Only the scheme, host, port, and
    path identify an instance, so everything else is dropped.
    """
    parsed = urlsplit(target)
    if not parsed.hostname:
        return target
    host = parsed.hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    try:
        if parsed.port is not None:
            host = f"{host}:{parsed.port}"
    except ValueError:
        # A malformed port cannot be read; the credential-free host still stands.
        pass
    return urlunsplit((parsed.scheme, host, parsed.path, "", ""))
