#!/usr/bin/env bash
# Run one Cloud pytest suite, tee its output, and fail if a leak scan finds a
# target or credential in the resulting artifacts. Shared by the read and
# write canary workflows so the pipefail/tee/scan/exit dance lives in one
# place instead of being copy-pasted per step.
#
# Usage: run-cloud-suite.sh <label> <pytest-target> [pytest-marker]
#   label          used for <label>.log / <label>.xml
#   pytest-target  path pytest should collect
#   pytest-marker  -m expression (default: "integration and cloud")
#
# The calling workflow is expected to set VCT_SPLUNK_REDACT_TARGET=1, so this
# scan is checking real defense-in-depth rather than re-catching what
# redaction already hid.
#
# Requires: a project already installed into .venv (the workflow's "Install
# project" step). Reads GITHUB_STEP_SUMMARY when set (Actions).
set -euo pipefail

label="${1:?usage: run-cloud-suite.sh <label> <pytest-target> [pytest-marker]}"
target="${2:?usage: run-cloud-suite.sh <label> <pytest-target> [pytest-marker]}"
marker="${3:-integration and cloud}"

log="${label}.log"
xml="${label}.xml"

set +e
.venv/bin/pytest "$target" \
  -m "$marker" \
  -q --tb=line -r N \
  -o addopts='--strict-markers --import-mode=importlib' \
  --junitxml="$xml" \
  | tee "$log"
pytest_status=${PIPESTATUS[0]}
set -e

scan_files=("$log" "$xml")
if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
  scan_files+=("$GITHUB_STEP_SUMMARY")
fi
python .github/scripts/scan-cloud-ci-leaks.py "${scan_files[@]}"

exit "$pytest_status"
