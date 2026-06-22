from __future__ import annotations

from typing import Callable

import httpx
import pytest

from vct_splunk.client import ClientConfig, SplunkClient


def make_client(handler: Callable, *, dry_run: bool = False) -> SplunkClient:
    cfg = ClientConfig(base_url="https://splunk.test:8089", token="TESTTOKEN", dry_run=dry_run)
    return SplunkClient(cfg, transport=httpx.MockTransport(handler))


@pytest.fixture
def client_for() -> Callable:
    """Return a factory: client_for(handler, dry_run=...) -> SplunkClient backed by a mock transport."""
    return make_client
