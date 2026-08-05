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
    scheme = ("https", "http", fdp.ConsumeUnicodeNoSurrogates(12))[shape]
    user = fdp.ConsumeUnicodeNoSurrogates(12)
    host = "sh.corp:8089" if shape == 0 else fdp.ConsumeUnicodeNoSurrogates(24)
    tail = fdp.ConsumeUnicodeNoSurrogates(24)
    # A credential does not only appear as userinfo. `?token=` and `#token=`
    # carry one too, and these two shapes omit `//` and `@` on purpose: without
    # an authority there is no host to rebuild from, which is the branch that
    # returns the target as it stands. Keeping the `@` here would send every
    # input down the userinfo rule instead and never reach it.
    place = fdp.ConsumeIntInRange(0, 2)
    if place == 1:
        return f"{host}{tail}?token={SENTINEL}"
    if place == 2:
        return f"{host}{tail}#token={SENTINEL}"
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
