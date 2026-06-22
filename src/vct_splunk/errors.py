"""Typed errors raised by the core layer. Click-free so the core stays a plain library.

`exit_code` maps to the process exit status; the CLI shell renders these to stderr.
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


class APIError(SplunkError):
    exit_code = 1
    code = "api_error"


class TransportError(SplunkError):
    exit_code = 1
    code = "transport_error"
