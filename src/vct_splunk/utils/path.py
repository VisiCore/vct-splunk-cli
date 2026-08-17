"""Validation and encoding for values inserted into REST path segments."""

from __future__ import annotations

from urllib.parse import quote, unquote

from .errors import UsageError


def path_segment(value: str, *, label: str = "path segment") -> str:
    """Validate and percent-encode one dynamic REST path segment.

    Encoded traversal forms are rejected as well as literal separators so a
    caller cannot smuggle a second segment through URL decoding.
    """
    if not value:
        raise UsageError(f"{label.capitalize()} cannot be empty.")

    candidate = value
    while True:
        _reject_unsafe(candidate, label)
        decoded = unquote(candidate)
        if decoded == candidate:
            break
        candidate = decoded

    return quote(value, safe="")


def absolute_path_segment(value: str, *, label: str) -> str:
    """Encode an absolute-path stanza name after strict traversal validation."""
    candidate = value
    while True:
        if any(ord(char) < 32 or ord(char) == 127 for char in candidate):
            raise UsageError(f"{label.capitalize()} cannot contain control characters.")
        if "\\" in candidate:
            raise UsageError(f"{label.capitalize()} cannot contain backslashes.")
        decoded = unquote(candidate)
        if decoded == candidate:
            break
        candidate = decoded

    if not candidate.startswith("/"):
        raise UsageError(f"{label.capitalize()} must contain an absolute path.")
    if any(part in {".", ".."} for part in candidate.split("/")):
        raise UsageError(f"{label.capitalize()} cannot contain dot segments.")
    return quote(value, safe="")


def _reject_unsafe(value: str, label: str) -> None:
    if value in {".", ".."}:
        raise UsageError(f"{label.capitalize()} cannot be a dot segment.")
    if "/" in value or "\\" in value:
        raise UsageError(f"{label.capitalize()} cannot contain a path separator.")
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise UsageError(f"{label.capitalize()} cannot contain control characters.")
