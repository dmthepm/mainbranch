#!/usr/bin/env bash
# Pin the plugin marketplace to a release tag's exact commit, after the release
# exists (docs/release-agent-contract.md Rule 8).
#
# Usage:
#   scripts/release-pin-plugin.sh oe-v0.6.18      # write url + sha pin
#   scripts/release-pin-plugin.sh --check         # verify an existing pin
#   scripts/release-pin-plugin.sh --candidate DIR # export HEAD with source "./" for smoke
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
case "${1:-}" in
  --check) shift; exec python3 "$HERE/plugin_pin.py" check "$@" ;;
  --candidate) shift; exec python3 "$HERE/plugin_pin.py" candidate "$@" ;;
  "" | -*) sed -n '2,8p' "${BASH_SOURCE[0]}" >&2; exit 2 ;;
  *) exec python3 "$HERE/plugin_pin.py" pin "$@" ;;
esac
