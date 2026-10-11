#!/usr/bin/env bash
# Run one Cloud pytest suite, tee its output, and publish a JUnit report.
# Shared by the read and write canary workflows so the pipefail/tee/exit
# dance lives in one place instead of being copy-pasted per step.
#
# Usage: run-cloud-suite.sh <label> <pytest-target> [pytest-marker]
#   label          used for <label>.log / <label>.xml
#   pytest-target  path pytest should collect
#   pytest-marker  -m expression (default: "integration and cloud")
#
# Requires: a project already installed into .venv (the workflow's "Install
# project" step).
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

exit "$pytest_status"
