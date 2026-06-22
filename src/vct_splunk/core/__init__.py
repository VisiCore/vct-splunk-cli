"""Click-free core: the Splunk REST client and pure operation functions.

Nothing in this package imports Click. Modules here are plain, importable
functions plus typed errors, so the logic can be reused and unit-tested without
the CLI. The Click adapters that call into this package live in
:mod:`vct_splunk.commands`.
"""
