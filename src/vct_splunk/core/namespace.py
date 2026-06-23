"""Splunk namespace (owner + app) helpers. Click-free core.

Most knowledge and search objects live under a namespace path::

    /servicesNS/<owner>/<app>/<suffix>

The non-namespaced ``/services/<suffix>`` form silently resolves to the caller's
*default app* — usually ``search`` — which is rarely what an admin wants and is
easy to write to by accident. These helpers build explicit namespaced paths and
apply a safe default policy so a write never lands in ``search`` by mistake.

Splunk's official field names are **owner** and **app**. ``-`` is the wildcard
(all owners / all apps). ``nobody`` owns app-level (shared) objects;
``splunk-system-user`` is an internal system owner that is set explicitly, never
by default.
"""

from __future__ import annotations

from .errors import UsageError

#: Splunk wildcard for owner or app — matches across every namespace.
WILDCARD = "-"
#: Owner for an app-level (shared) object, i.e. not private to one user.
SHARED_OWNER = "nobody"


def ns_path(suffix: str, *, owner: str, app: str) -> str:
    """Build a namespaced REST path: ``/servicesNS/<owner>/<app>/<suffix>``.

    Args:
        suffix: The endpoint under the namespace, e.g. ``saved/searches`` or
            ``saved/searches/My Alert``. A leading slash is ignored.
        owner: The owner segment (a username, ``nobody``, or the ``-`` wildcard).
        app: The app segment (an app name or the ``-`` wildcard).

    Returns:
        The full namespaced path, ready for the client.

    Raises:
        UsageError: If owner or app is empty.
    """
    if not owner or not app:
        raise UsageError("A namespace needs both an owner and an app.")
    return f"/servicesNS/{owner}/{app}/{suffix.lstrip('/')}"


def resolve_ns(owner: str | None, app: str | None, *, for_write: bool) -> tuple[str, str]:
    """Resolve ``(owner, app)`` for a namespaced request, applying the safe policy.

    Reads (``for_write=False``) default to the ``-`` wildcard for both, so a
    ``list``/``get`` sees objects across every namespace unless the caller
    narrows it.

    Writes (``for_write=True``) **require an explicit app** so an object is never
    created in the default ``search`` app by accident; the owner defaults to
    ``nobody`` (an app-level shared object) unless one is given.

    Args:
        owner: The owner from ``--owner`` / ``$SPLUNK_OWNER``, or None.
        app: The app from ``--app`` / ``$SPLUNK_APP``, or None.
        for_write: True for a mutating request (stricter policy).

    Returns:
        The resolved ``(owner, app)`` pair.

    Raises:
        UsageError: For a write with no app.
    """
    if for_write:
        if not app:
            raise UsageError(
                "This write needs an app. Pass --app NAME (or set SPLUNK_APP) so the "
                "object is created in a real app instead of defaulting to 'search'."
            )
        return (owner or SHARED_OWNER, app)
    return (owner or WILDCARD, app or WILDCARD)
