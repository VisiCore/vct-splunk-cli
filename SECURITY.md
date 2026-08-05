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
- **Secret-bearing response fields are removed before data leaves an
  operation.** HTTP Event Collector tokens in a listing, for example, are
  stripped inside the ACS operation, so no listing can print one.
- **Two commands return a secret on purpose,** because minting one is what they
  do: `auth login` prints the session key it created, and `hec rotate` prints
  the token it minted. Both values go to standard output only — never to the
  audit log, which records the action and the object name.
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
- Third-party GitHub Actions are pinned to full commit SHAs.
- Workflows declare least-privilege `permissions:` blocks.
- Every pull request runs CodeQL, `zizmor` workflow-security analysis, and
  dependency review that fails on moderate or higher severity.
- [OpenSSF Scorecard](https://github.com/VisiCore/vct-splunk-cli/actions/workflows/scorecard.yml)
  audits these practices weekly and publishes the result.
