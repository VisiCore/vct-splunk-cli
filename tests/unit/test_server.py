from __future__ import annotations

import httpx
import pytest

from vct_splunk.core.errors import UsageError
from vct_splunk.core.server import get_server_info


def test_get_server_info_normalizes(client_for):
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"entry": [{"content": {"serverName": "sh1", "version": "9.4.1"}}]}
        )

    info = get_server_info(client_for(handler))
    assert info["server_name"] == "sh1"
    assert info["version"] == "9.4.1"


def test_get_server_info_non_rest_body_raises(client_for):
    # A non-REST 200 (e.g. the web UI) decodes to {"raw": ...} with no "entry".
    # That must surface as a clear error, not an all-null "success".
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>not splunkd</html>")

    with pytest.raises(UsageError):
        get_server_info(client_for(handler))
