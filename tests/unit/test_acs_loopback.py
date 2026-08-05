"""Drive the Cloud read path over a real socket, with no Cloud stack.

`test_acs.py` covers the ACS client against `httpx.MockTransport`, and its
CLI-level tests replace `Ctx.acs_client` outright. That leaves one span
untested: the wiring between them — environment to `acs_config_from_env`, to
the joined base URL, to the `Authorization` header, to a request that actually
leaves the process.

These tests close it with a loopback HTTP server from the standard library. The
CLI runs unmodified against `SPLUNK_ACS_BASE_URL=http://127.0.0.1:<port>`, so
every layer is the real one and the server can assert on what it received.

The fake serves the paths declared in `operations.READ_PATHS` and the envelope
names in `operations.LIST_ENVELOPES`. Those are the same declarations the
weekly public-spec canary checks against Splunk's published OpenAPI, so the
fake cannot drift from the contract without that canary failing.

Deliberately not retested here: pagination, the status-code-to-error mapping,
and retries. `test_acs.py` owns those against a mock transport, which is faster
and more precise. This file proves the wiring, once.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import pytest
from click.testing import CliRunner

from vct_splunk.cli import cli
from vct_splunk.core.acs import operations

STACK = "acme"
TOKEN = "acs-test-token"

#: One item per ACS path, each carrying a `token` field. Every response goes
#: through the CLI, so a leaked secret shows up as a failed assertion.
_ITEM = {"name": "example", "token": "SECRET-MUST-NOT-APPEAR"}

#: The CLI command whose list routes to each ACS path.
_COMMAND_FOR_PATH = {
    operations.INDEXES: "index",
    operations.ROLES: "role",
    operations.HEC_TOKENS: "hec-token",
}


class _Recorder(BaseHTTPRequestHandler):
    """Serve the ACS read paths and record what each request looked like."""

    requests: list[tuple[str, str, str | None]]
    status = 200

    def do_GET(self) -> None:  # noqa: N802 — BaseHTTPRequestHandler's required name
        path = urlsplit(self.path).path
        self.requests.append((self.command, path, self.headers.get("Authorization")))

        if self.status != 200:
            self._respond(self.status, {"code": "forbidden", "message": "no"})
            return

        prefix = f"/{STACK}/adminconfig/v2/"
        envelope = operations.LIST_ENVELOPES.get(path.removeprefix(prefix))
        if envelope is None:
            self._respond(404, {"code": "404", "message": "unknown path"})
            return
        self._respond(200, {envelope: [_ITEM]})

    def _respond(self, status: int, body: dict[str, object]) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args: object) -> None:
        """Keep the server silent; pytest reports what matters."""


@pytest.fixture
def acs_server(monkeypatch: pytest.MonkeyPatch) -> Iterator[type[_Recorder]]:
    """Run the fake ACS on a loopback port and point the CLI's Cloud path at it."""
    handler = type("_Handler", (_Recorder,), {"requests": []})
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    monkeypatch.setenv("SPLUNK_URL", f"https://{STACK}.splunkcloud.com")
    monkeypatch.setenv("SPLUNK_ACS_TOKEN", TOKEN)
    monkeypatch.setenv("SPLUNK_ACS_BASE_URL", f"http://127.0.0.1:{server.server_port}")
    try:
        yield handler
    finally:
        server.shutdown()
        server.server_close()


def _run(*argv: str):
    """Invoke the real CLI, asking for JSON so the assertions read the contract."""
    return CliRunner().invoke(cli, [*argv, "--output", "json"])


@pytest.mark.parametrize("acs_path", operations.READ_PATHS)
def test_every_acs_read_reaches_its_endpoint_with_a_bearer_token(acs_server, acs_path: str) -> None:
    """Each ACS read builds the right URL, authenticates, and returns the envelope.

    Parametrized over the runtime declaration rather than a copied list, so a
    new ACS route is covered the moment it is registered.
    """
    result = _run(_COMMAND_FOR_PATH[acs_path], "list")

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert set(payload) == {"data", "meta"}

    method, path, authorization = acs_server.requests[0]
    assert method == "GET"
    assert path == f"/{STACK}/adminconfig/v2/{acs_path}"
    assert authorization == f"Bearer {TOKEN}"


@pytest.mark.parametrize("acs_path", operations.READ_PATHS)
def test_no_acs_read_prints_a_token(acs_server, acs_path: str) -> None:
    """A secret the stack returns must never reach the caller's output."""
    result = _run(_COMMAND_FOR_PATH[acs_path], "list")

    assert result.exit_code == 0, result.output
    assert _ITEM["token"] not in result.output


def test_a_rejected_acs_read_exits_3_with_a_typed_error(acs_server) -> None:
    """A 403 from the stack maps to the documented auth exit code and envelope."""
    acs_server.status = 403

    result = _run("index", "list")

    assert result.exit_code == 3, result.output
    payload = json.loads(result.output)
    assert set(payload) == {"error"}
    assert payload["error"]["code"]
    assert payload["error"]["message"]
