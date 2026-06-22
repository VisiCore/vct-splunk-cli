"""splunk — a small, scriptable CLI over the Splunk Enterprise REST API.

The public ``__version__`` is read from the installed package metadata so there
is a single source of truth: the top-level ``VERSION`` file, which the build
copies into that metadata.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("vct-splunk-cli")
except PackageNotFoundError:  # pragma: no cover - running from a source tree without an install
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
