"""Click command groups — the ``splunk`` CLI surface.

Each module wires one command group (``server``, ``api``, ``index``, ``search``,
``health``) to the matching functions in :mod:`vct_splunk.core`. These modules
are thin adapters: argument parsing, output formatting, and write-gating only.
The real work lives in the core.
"""
