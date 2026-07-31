#!/usr/bin/env bash
# Decide whether a pull request touches code that the live Enterprise suite
# covers. Writes `code=true` or `code=false` to $GITHUB_OUTPUT.
#
# Plain git on purpose: no third-party action and no Node runtime, so the cost
# filter keeps the same "standard tools only" property as the rest of the
# project. tests/unit/test_ci_path_filter.py pins the pattern below.
#
# Requires: BASE_REF (the pull request's target branch), GITHUB_OUTPUT (Actions).
set -euo pipefail

: "${BASE_REF:?BASE_REF must be set to the pull request's base branch}"
: "${GITHUB_OUTPUT:?GITHUB_OUTPUT must be set by GitHub Actions}"

# Paths whose change requires a live Splunk run, anchored at the repo root.
readonly COVERED='^(src/|tests/|\.github/scripts/|pyproject\.toml$|\.github/workflows/ci\.yml$)'

# Fetch into an explicit remote-tracking ref. `git fetch origin <branch>` only
# updates FETCH_HEAD unless the checkout happens to configure a matching
# refspec, and `origin/<branch>` would then not resolve below.
git fetch --no-tags origin "+refs/heads/${BASE_REF}:refs/remotes/origin/${BASE_REF}"

if git diff --name-only "origin/${BASE_REF}...HEAD" | grep -qE "$COVERED"; then
  echo "code=true" >>"$GITHUB_OUTPUT"
  echo "Code paths changed: the Enterprise suite will run."
else
  echo "code=false" >>"$GITHUB_OUTPUT"
  echo "No code paths changed: skipping the Enterprise suite."
fi
