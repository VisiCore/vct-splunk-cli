"""Typed errors raised by the core layer. Click-free so the core stays a plain library.

`exit_code` maps to the process exit status; the CLI shell renders these to stderr.
Exit 5 is not an error class: `health check` exits 5 when the check succeeded but
some finding is warn/fail, so scripts can tell a sick Splunk from a failed request.
"""

from __future__ import annotations


class SplunkError(Exception):
    exit_code = 1
    code = "error"

    def __init__(self, message: str, *, details: object | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class UsageError(SplunkError):
    exit_code = 2
    code = "usage_error"


class AuthError(SplunkError):
    exit_code = 3
    code = "auth_error"


class NotFoundError(SplunkError):
    exit_code = 4
    code = "not_found"


class UnsupportedBackendError(SplunkError):
    """The requested operation does not exist on the deduced backend.

    Exit code 4 (the "not found" family): from the user's view the endpoint simply
    isn't there for this target (Cloud vs Enterprise), so the CLI stops cleanly
    rather than falling through to an unofficial endpoint.
    """

    exit_code = 4
    code = "unsupported_backend"

    def __init__(self, resource: str, verb: str, backend: str) -> None:
        nice = {"enterprise": "Splunk Enterprise", "cloud": "Splunk Cloud"}.get(backend, backend)
        super().__init__(f"`{resource} {verb}` is not available on {nice}.")
        self.resource = resource
        self.verb = verb
        self.backend = backend


class APIError(SplunkError):
    exit_code = 1
    code = "api_error"


class TransportError(SplunkError):
    exit_code = 1
    code = "transport_error"
