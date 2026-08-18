"""The Splunk REST API layer: client, endpoint factory, and endpoint modules.

Mirrors the cribl-cli ``api/`` package. Nothing here imports Click — this is
the reusable library surface a downstream application (e.g. a web backend)
embeds directly:

* :mod:`vct_splunk.api.client` — the httpx transport stack (auth, retries) and
  the envelope-aware :class:`~vct_splunk.api.client.SplunkClient`.
* :mod:`vct_splunk.api.endpoint_factory` — the generic CRUD engine driven by
  declarative :class:`~vct_splunk.api.endpoint_factory.EndpointConfig` entries.
* :mod:`vct_splunk.api.endpoints` — hand-written endpoint modules for
  resources that do not fit the CRUD shape.
* :mod:`vct_splunk.api.acs` — the Splunk Cloud ACS management-plane client.
"""
