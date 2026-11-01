#!/usr/bin/env bash
# Release-file preflight (release-agent-contract.md Rule 0, issue #826).
#
# Asserts the version-bearing release files agree — and agree with the
# release tag when one is passed — then runs the cheapest targeted guard for
# the plugin manifest. Run this before scripts/check.sh on a release-prep
# branch; do not spend a 10-minute gate discovering a version mismatch.
#
# Usage:
#   scripts/release-preflight.sh              # files must agree with each other
#   scripts/release-preflight.sh 0.3.43       # ...and with this version
#   scripts/release-preflight.sh oe-v0.3.43   # tag form accepted
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

expected="${1:-}"
expected="${expected#oe-v}"

pyproject_version="$(sed -n 's/^version = "\(.*\)"$/\1/p' "$ROOT/mb/pyproject.toml" | head -n1)"
init_version="$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' "$ROOT/mb/mb/__init__.py" | head -n1)"
plugin_version="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["version"])' "$ROOT/.claude-plugin/plugin.json")"
marketplace_version="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["metadata"]["version"])' "$ROOT/.claude-plugin/marketplace.json")"

fail=0
echo "mb/pyproject.toml        version    = $pyproject_version"
echo "mb/mb/__init__.py        __version__ = $init_version"
echo ".claude-plugin/plugin.json version  = $plugin_version"
echo ".claude-plugin/marketplace.json    = $marketplace_version"

if [ -z "$pyproject_version" ] || [ -z "$init_version" ] || [ -z "$plugin_version" ] || [ -z "$marketplace_version" ]; then
  echo "release-preflight: could not read all version strings." >&2
  fail=1
fi
if [ "$pyproject_version" != "$init_version" ] || [ "$pyproject_version" != "$plugin_version" ] || [ "$pyproject_version" != "$marketplace_version" ]; then
  echo "release-preflight: version files disagree." >&2
  fail=1
fi
if [ -n "$expected" ] && [ "$pyproject_version" != "$expected" ]; then
  echo "release-preflight: files say $pyproject_version but the release is $expected." >&2
  fail=1
fi

if grep -n "## \[$pyproject_version\]" "$ROOT/CHANGELOG.md" > /dev/null; then
  echo "CHANGELOG.md             has a [$pyproject_version] section"
else
  echo "release-preflight: CHANGELOG.md has no [$pyproject_version] section." >&2
  fail=1
fi

if [ "$fail" -ne 0 ]; then
  echo "release-preflight: FAILED — fix release files before running scripts/check.sh." >&2
  exit 1
fi

# A pinned marketplace must name the first-party release tag's commit, on
# first-party main, and not newer than this tree. This needs the network; the
# check fetches first-party main itself.
python3 "$ROOT/scripts/plugin_pin.py" --root "$ROOT" check || {
  echo "release-preflight: plugin pin check failed." >&2
  exit 1
}

cd "$ROOT/mb"
python3 -m pytest tests/test_smoke_coverage.py::test_claude_plugin_manifest_points_at_prefixed_skills -q

echo "release-preflight: OK ($pyproject_version)"
