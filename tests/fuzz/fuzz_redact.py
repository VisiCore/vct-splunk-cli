"""Fuzz `core.redact.safe_target`, the one function standing between a
credentialed URL and the audit log.

`SPLUNK_URL` may carry `user:password@`, and the target it names is printed in
prompts, JSON metadata, transport errors, and the audit log — all before
anything validates that the URL parses. So the interesting inputs are the
malformed ones: a missing scheme, a truncated authority, an unterminated IPv6
literal. Those are exactly what an example-based test does not think to write
down, and what a fuzzer produces immediately.

The oracle is one property, checked on every input:

    a credential handed to `safe_target` never comes back out of it,
    and `safe_target` never raises.

Raising counts as a failure because a traceback prints the offending value,
which puts the credential in the log by a different door.

This file is deliberately not named `test_*.py`: pytest must not collect it.
atheris ships manylinux x86_64 wheels only, so it cannot be installed on macOS
or arm64, and the local suite has to keep running there. Run it in CI, or on a
Linux box with:

    python -m pip install --require-hashes -r requirements-fuzz.txt
    python -m pip install -e . --no-deps
    python tests/fuzz/fuzz_redact.py -atheris_runs=200000
"""

import sys

import atheris

with atheris.instrument_imports():
    from vct_splunk.core.redact import safe_target

#: Spliced in as the password of every generated target. A fixed marker is what
#: makes the leak check decidable — the fuzzer shapes the URL around it, and any
#: appearance of this string in the output is a leak regardless of how it got
#: there.
SENTINEL = "fuzz-password-must-not-survive"


def _fuzzed(fdp: "atheris.FuzzedDataProvider", n: int) -> str:
    """Consume up to *n* fuzzed characters, scrubbed of the sentinel itself.

    libFuzzer's coverage-guided mutator extracts the sentinel as a useful byte
    string (it shows up as a `DE:` dictionary entry in the corpus) and splices
    it wherever bytes are consumed — including here, not only where the
    credential is deliberately placed below. Left unscrubbed, that plants the
    sentinel in a field like the host, which `safe_target` correctly leaves
    visible, and the oracle then reports a leak that never happened: the
    credential slot was never touched.
    """
    return fdp.ConsumeUnicodeNoSurrogates(n).replace(SENTINEL, "")


def build_target(data: bytes) -> str:
    """Shape one candidate URL around the sentinel password.

    Assembled rather than consumed whole so that every input is shaped like a
    URL carrying userinfo. A purely random string almost never grows a `@`, and
    would spend the whole budget on targets with no credential to leak.
    """
    fdp = atheris.FuzzedDataProvider(data)
    # Two thirds of inputs keep a real scheme, and a third of those a real
    # authority, so the port and IPv6-bracket branches are actually reached.
    # The rest are free-form — the shape that broke this function.
    shape = fdp.ConsumeIntInRange(0, 2)
    # A credential does not only appear as userinfo. `?token=` and `#token=`
    # carry one too, and these two shapes omit `//` and `@` on purpose: without
    # an authority there is no host to rebuild from, which is the branch that
    # returns the target as it stands. Keeping the `@` here would send every
    # input down the userinfo rule instead and never reach it.
    #
    # Half the budget stays on the userinfo shape. These two reach the fallback
    # quickly and so explore fewer branches; splitting evenly measurably cost
    # coverage of the parse-and-rebuild path that the other half exercises.
    #
    # Drawn before scheme/user, which the query/fragment shapes never use —
    # consuming them anyway would waste fuzzer budget on two of every four runs.
    place = fdp.ConsumeIntInRange(0, 3)
    host = "sh.corp:8089" if shape == 0 else _fuzzed(fdp, 24)
    tail = _fuzzed(fdp, 24)
    if place == 2:
        return f"{host}{tail}?token={SENTINEL}"
    if place == 3:
        return f"{host}{tail}#token={SENTINEL}"
    scheme = ("https", "http", _fuzzed(fdp, 12))[shape]
    user = _fuzzed(fdp, 12)
    return f"{scheme}://{user}:{SENTINEL}@{host}{tail}"


# CamelCase because libFuzzer's Python binding looks the entry point up by name.
def TestOneInput(data: bytes) -> None:
    """Assert the credential does not survive, however malformed the target."""
    target = build_target(data)
    try:
        result = safe_target(target)
    # Deliberately broad: any exception escaping is itself the finding.
    except Exception as exc:
        raise AssertionError(f"safe_target raised {type(exc).__name__} on {target!r}") from exc
    if SENTINEL in result:
        raise AssertionError(f"credential survived: {target!r} -> {result!r}")


def main() -> None:
    """Hand control to libFuzzer."""
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
