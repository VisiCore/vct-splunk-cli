"""Click command groups — the ``splunk`` CLI surface.

Each hand-written module wires one command group (``server``, ``api``,
``search``, ``health``, ``inspect``, plus ``saved_search``'s ``run``) to the
matching functions in :mod:`vct_splunk.core`; ``registry`` + ``factory``
generate the CRUD groups (``index``, ``saved-search``, ``user``, ``role``,
``macro``, the data inputs/outputs, and friends) from declarative specs. These modules are thin
adapters: argument parsing, output formatting, and write-gating only. The real
work lives in the core.
"""
