"""Credential-free drift check against Splunk's public ACS OpenAPI."""

from __future__ import annotations

import os

import httpx
import pytest

from vct_splunk.core.acs import pinned_spec

pytestmark = pytest.mark.integration

_SOURCE = "https://admin.splunk.com/service/info/specs/v2/openapi.json"


def test_implemented_acs_contract_matches_public_spec():
    if os.environ.get("SPLUNK_ACS_SPEC_TEST") != "true":
        pytest.skip("set SPLUNK_ACS_SPEC_TEST=true to check the public ACS OpenAPI")

    public = httpx.get(_SOURCE, timeout=30).raise_for_status().json()
    snapshot = pinned_spec()
    assert snapshot["x-source-url"] == _SOURCE

    for path, item in snapshot["paths"].items():
        operation = public["paths"][path]["get"]
        expected = item["get"]
        assert operation["operationId"] == expected["operationId"]
        assert [parameter["$ref"].rsplit("/", 1)[-1] for parameter in operation["parameters"]] == (
            expected["parameters"]
        )
        schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
        envelope = next(iter(expected["response"]))
        assert schema["properties"][envelope]["type"] == "array"
        assert (
            schema["properties"][envelope]["items"]["$ref"].rsplit("/", 1)[-1]
            == expected["response"][envelope]["items"]
        )
