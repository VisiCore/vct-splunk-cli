# Security Policy

## Reporting a vulnerability

Report suspected vulnerabilities privately through GitHub Security Advisories:
[**Report a vulnerability**](https://github.com/VisiCore/vct-splunk-cli/security/advisories/new).

Please do not open a public issue or pull request for a security problem.

Include the command you ran, the version (`splunk --version`), and what you
observed. You will get an acknowledgement within 7 days and a status update at
least every 14 days until the report is resolved.

## Supported versions

The latest release on `main` receives security fixes. Older versions do not.

## How this tool handles your credentials

- **Secret credentials come from the environment or a configuration profile,
  never from a command-line flag.** Flags are recorded in shell history and are
  visible to any other user in the process list, so no option accepts a
  password, token, or session key. `auth login` accepts `--username`, which is
  not a secret; it reads the password from `$SPLUNK_PASSWORD` or a no-echo
  prompt.
- **Credentials are never written to disk by this tool.** It reads them, uses
  them for the current invocation, and forgets them.
- **Secret-bearing response fields are replaced before data leaves an
  operation.** Splunk returns secrets inside ordinary reads — an HTTP Event
  Collector input carries its own token, a server setting carries
  `pass4SymmKey`. Whether a field is secret is decided by its name, in one
  place (`core/redact.py`), and applied to every named read command on both
  backends. The key survives as `<redacted>` so you can still see the field
  exists, and a field Splunk adds later is covered the day it appears.
- **`api get` is the one exception, by design.** It is a raw escape hatch that
  returns the endpoint's body verbatim, so it can show a stored secret. It
  stays verbatim on purpose: redacting it would corrupt the round-trip that
  makes an escape hatch useful. Prefer the named command when one exists.
- **Three commands return a secret on purpose,** because minting one is what
  they do: `auth login` prints the session key it created, `hec rotate` prints
  the token it regenerated, and `hec-token create` prints the token it just
  created — you cannot configure a sender without it. Those values go to
  standard output only, never to the audit log, which records the action and
  the object name. Every other named command redacts.
- **TLS verification is on by default.** `SPLUNK_CA_BUNDLE` points at your own
  certificate authority. `SPLUNK_VERIFY=false` disables verification entirely
  and exists only for laboratory use.

## How changes to your server are controlled

Reads cannot modify a server. Every write passes through one gate:

- `--dry-run` prints the exact request and sends nothing.
- On a terminal, the write asks for confirmation.
- Without a terminal, the write requires `--yes` and otherwise stops. It never
  waits on a prompt nobody can see.
- Every applied write is appended to a local audit log.

An operation the target does not support fails with a typed error. The tool
never falls back to guessing an endpoint.

## How this project protects its supply chain

- **Two runtime dependencies:** `click` and `httpx`. Every added package is
  both maintenance burden and attack surface, so the list does not grow without
  a written case that the standard library cannot do the job.
- Every GitHub Actions reference is pinned to a full commit SHA — third-party
  actions and reusable workflows alike. A branch or tag can be repointed at new
  code after review; a commit cannot.
- Workflows declare least-privilege `permissions:` blocks.
- Every pull request runs CodeQL (GitHub code scanning default setup, so there
  is no workflow file for it), `zizmor` workflow-security analysis, and
  dependency review that fails on moderate or higher severity.
- [OpenSSF Scorecard](https://github.com/VisiCore/vct-splunk-cli/actions/workflows/scorecard.yml)
  audits these practices weekly and publishes the result.
