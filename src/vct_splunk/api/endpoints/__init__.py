"""Hand-written endpoint modules for resources the CRUD factory cannot express.

Each module is plain functions taking a
:class:`~vct_splunk.api.client.SplunkClient` first, mirroring the cribl-cli
``api/endpoints/`` layout: search/jobs (dispatch + lifecycle), server info and
settings, health checks, the KV Store document store, HEC token rotation, app
install, cluster/license/deployment reads, lookup upload, data model
acceleration, and the raw read-only escape hatch.
"""
