"""Click command groups — the ``splunk`` CLI surface.

Each hand-written module wires one command group (``server``, ``api``,
``index``, ``search``, ``saved_search``, ``health``, ``inspect``) to the
matching functions in :mod:`vct_splunk.core`; ``registry`` + ``factory``
generate the remaining CRUD groups (``user``, ``role``, ``macro``, the data
inputs/outputs, and friends) from declarative specs. These modules are thin
adapters: argument parsing, output formatting, and write-gating only. The real
work lives in the core.
"""
