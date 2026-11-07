"""Daily business pulse scaffold (`mb pulse init`).

Graduates the pulse shape proven on a live business's daily operator brief:
deterministic no-LLM collectors (date in -> one JSON object out, honest
``{"unavailable": true}`` + non-zero exit on failure), and a repo-local
pulse skill that does the judgment over the JSON — per-channel scorecard,
anomalies, exactly ONE recommended action, a sub-60-line log entry. The
agent is the editor; code never writes the paper.

Division of labor with the surfaces that already exist: ``mb status`` owns
repo-fact triage (drift, overdue bets) and the pulse CONSUMES it as one
source; ``mb canary`` owns invariant pass/fail and its JSON can be wired in
as another collector. The pulse never re-ranks what those already rank.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

COLLECTOR_README_TEMPLATE = """# Pulse collectors — the deterministic layer

One script per source, named `collect-<source>.sh`. The pulse skill runs
them and does the judgment; collectors only fetch numbers.

## The collector contract

- **Date in, JSON out.** `bash collect-<source>.sh [YYYY-MM-DD]` (defaults
  to today UTC) prints exactly ONE JSON object on stdout.
- **Honest absence beats invented numbers.** On ANY failure print
  `{"unavailable": true, "source": "<source>", "error": "<token>"}` and
  exit non-zero. The pulse reports the gap; it never guesses.
- **Deterministic and judgment-free.** No LLM calls, no thresholds, no
  recommendations — numbers only. Judgment lives in the pulse skill.
- **Read-only against every provider.** No sends, no spend, no writes.
- **Never print credentials.** Source tokens from your env file; emit only
  derived numbers.
- **One command, no compound wrappers.** Keep each collector runnable as a
  single `bash collect-<source>.sh <date>` so agent permission systems can
  allow it once instead of prompting per tick.

## Adding a collector

Copy `collect-example.sh`, rename the SOURCE, replace the TODO block with
one read-only API pull shaped (via jq) into the numbers your pulse needs.
The comment at the top must say what the source answers for the business.
"""

EXAMPLE_COLLECTOR_TEMPLATE = """#!/usr/bin/env bash
# collect-example.sh — pulse collector template (copy + rename per source).
# Contract (see README.md): date in -> ONE JSON object on stdout; on any
# failure emit {"unavailable": true, ...} and exit non-zero. Deterministic,
# no LLM, read-only, never prints credentials.
set -u
set -o pipefail

SOURCE="example"
fail() { printf '{"unavailable": true, "source": "%s", "error": "%s"}\\n' "$SOURCE" "$1"; exit 1; }

DATE="${1:-$(date -u +%F)}"
case "$DATE" in
  [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]) ;;
  *) fail "bad_date_arg" ;;
esac
command -v jq >/dev/null 2>&1 || fail "jq_missing"

# TODO: store the API token with `mb connect` and run this script through
# `mb connect exec <provider> --env YOUR_API_TOKEN -- <this script>` (never echo
# the token), then check it arrived:
#   [ -n "${YOUR_API_TOKEN:-}" ] || fail "your_api_token_missing_from_env"

# TODO: ONE read-only API pull for $DATE, shaped by jq into the numbers the
# pulse needs, e.g.
#   curl -fsS "https://api.example.com/stats?date=$DATE" \\
#     -H "Authorization: Bearer $YOUR_API_TOKEN" \\
#     | jq --arg date "$DATE" '{source: "example", date: $date, visits: .visits}' \\
#     || fail "api_error"

TODO_MSG="replace with one read-only API pull"
printf '{"source": "%s", "date": "%s", "todo": "%s"}\\n' "$SOURCE" "$DATE" "$TODO_MSG"
"""

SKILL_TEMPLATE = """---
name: mb-pulse
description: Daily business pulse — run collectors, judge the JSON, name ONE action. Read-only.
---

# mb-pulse — the daily business pulse

You are the editor of a one-page daily paper about this business. The
collectors fetch the numbers; you do the judgment. Nothing in this skill
sends, spends, or fixes anything.

## Steps

1. **Date.** Default to today UTC; accept an explicit `YYYY-MM-DD`.
2. **Collect.** For each script in `core/operations/pulse/collectors/`,
   run `bash core/operations/pulse/collectors/collect-<source>.sh <date>`
   and parse the JSON. An `{"unavailable": true}` result is an honest gap:
   report it as "<source>: unavailable (<error>)" — never substitute a
   guess or yesterday's number.
3. **Repo facts.** Run `mb status --json` and take its ranked actions and
   drift items as one more source. Do NOT re-rank repo facts — status owns
   that triage; the pulse only decides whether today's top repo fact beats
   today's top provider fact.
4. **Judge.** Compose, in order:
   - **Scorecard** — one line per channel/source with the day's numbers
     against the trailing norm.
   - **Anomalies** — only deltas that change what the operator does next.
   - **ONE recommended action** — exactly one, the single highest-leverage
     move for today, with the evidence line that justifies it.
5. **Write the paper.** Save to `log/<date>-{{SLUG}}-pulse.md`, under 60
   lines. If the file exists, append nothing — rerun overwrites it.
6. **Stay read-only.** Route every fix into the business's normal lanes
   (issues, bets, decisions) — the pulse names the move, the operator (or
   their session) makes it.

## Doctrine

- Honest absence beats invented numbers.
- Every anomaly named must be actionable; skip trivia.
- One action. A pulse that recommends three things recommends nothing.
"""


RUN_WRAPPER_TEMPLATE = """#!/usr/bin/env bash
# run-pulse.sh — operator-owned daily pulse collector run (mb pulse install).
# Runs every collect-*.sh for a date and assembles ONE JSON bundle so the
# numbers are ready when you open the session and run /mb-pulse. Deterministic,
# no LLM, read-only against providers. Individual collector failures are
# recorded as unavailable, never fatal to the bundle (collector contract).
#
# Usage: bash run-pulse.sh [YYYY-MM-DD]   (defaults to today UTC)
set -u
set -o pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
COLLECTORS="$HERE/collectors"
DATA="$HERE/data"
DATE="${1:-$(date -u +%F)}"
case "$DATE" in
  [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]) ;;
  *) echo "run-pulse: bad date arg: $DATE" >&2; exit 2 ;;
esac
command -v jq >/dev/null 2>&1 || { echo "run-pulse: jq not found" >&2; exit 2; }

shopt -s nullglob
scripts=("$COLLECTORS"/collect-*.sh)
if [ ${#scripts[@]} -eq 0 ]; then
  echo "run-pulse: no collectors in $COLLECTORS (run mb pulse init)" >&2
  exit 1
fi

mkdir -p "$DATA"
bundle="{}"
count=0
unavailable=0
for script in "${scripts[@]}"; do
  name="$(basename "$script" .sh)"; name="${name#collect-}"
  out="$(bash "$script" "$DATE" 2>/dev/null)" || true
  if ! printf '%s' "$out" | jq -e . >/dev/null 2>&1; then
    out="{\\"unavailable\\": true, \\"source\\": \\"$name\\", \\"error\\": \\"no_json\\"}"
  fi
  if printf '%s' "$out" | jq -e '.unavailable == true' >/dev/null 2>&1; then
    unavailable=$((unavailable+1))
  fi
  bundle="$(printf '%s' "$bundle" | jq --arg k "$name" --argjson v "$out" '.[$k] = $v')"
  count=$((count+1))
done

printf '%s' "$bundle" | jq --arg date "$DATE" \\
  '{date: $date, collectors: .}' > "$DATA/$DATE.json"
echo "run-pulse: $DATE — $count collector(s), $unavailable unavailable -> $DATA/$DATE.json" >&2
"""


def _slug_for(repo: Path, slug: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", (slug or repo.name).lower()).strip("-")
    return cleaned or "business"


def _normalize_time(value: str) -> tuple[int, int]:
    """Parse HH:MM (24h) into (hour, minute); raise ValueError on bad input."""
    raw = value.strip() or "08:00"
    if ":" not in raw:
        raise ValueError("time must be HH:MM (24-hour), e.g. 08:00")
    hh, mm = raw.split(":", 1)
    try:
        hour, minute = int(hh), int(mm)
    except ValueError as exc:
        raise ValueError("time must be HH:MM (24-hour), e.g. 08:00") from exc
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("time out of range; use HH:MM (00:00–23:59)")
    return hour, minute


def install(repo: str | Path = ".", *, at: str = "08:00", force: bool = False) -> dict[str, Any]:
    """Emit an operator-owned daily pulse wrapper + activation instructions.

    Writes ``core/operations/pulse/run-pulse.sh`` (assembles the collector
    JSON bundle for a date) and returns the exact cron line to activate it.
    Never installs or enables anything — activation is the operator's, by
    design (no spend, no background process started here).
    """
    root = Path(repo).resolve()
    pulse_dir = root / "core" / "operations" / "pulse"
    collectors_dir = pulse_dir / "collectors"
    wrapper_path = pulse_dir / "run-pulse.sh"
    if not collectors_dir.exists():
        return {
            "ok": False,
            "repo": str(root),
            "written": [],
            "summary": "no pulse collectors yet — run `mb pulse init` first",
        }
    if wrapper_path.exists() and not force:
        return {
            "ok": False,
            "repo": str(root),
            "written": [],
            "skipped": [str(wrapper_path.relative_to(root))],
            "summary": "run-pulse.sh already exists; rerun with --force to overwrite",
        }
    try:
        hour, minute = _normalize_time(at)
    except ValueError as exc:
        return {"ok": False, "repo": str(root), "written": [], "summary": str(exc)}

    wrapper_path.write_text(RUN_WRAPPER_TEMPLATE, encoding="utf-8")
    wrapper_path.chmod(0o755)
    rel_wrapper = wrapper_path.relative_to(root)
    cron_line = f"{minute} {hour} * * * cd {root} && bash {rel_wrapper}"
    activation = [
        "Activation is yours to enable — mb does not start any background job.",
        f"cron: add this line with `crontab -e`:\n    {cron_line}",
        (
            "Claude Code scheduled task: point a daily task at "
            f"`cd {root} && bash {rel_wrapper}`, then open /mb-pulse to read the day."
        ),
        "The wrapper only runs collectors and writes a local JSON bundle; the "
        "agent still writes the paper via /mb-pulse.",
    ]
    return {
        "ok": True,
        "repo": str(root),
        "written": [str(rel_wrapper)],
        "cron_line": cron_line,
        "run_at": f"{hour:02d}:{minute:02d}",
        "activation": activation,
        "summary": (
            f"pulse wrapper written to {rel_wrapper}; activate it yourself with the "
            "cron line below (mb never enables a schedule for you)"
        ),
        "safe_to_share": True,
    }


def init(repo: str | Path = ".", *, slug: str = "", force: bool = False) -> dict[str, Any]:
    """Scaffold pulse collectors + the repo-local mb-pulse skill."""
    root = Path(repo).resolve()
    collectors_dir = root / "core" / "operations" / "pulse" / "collectors"
    readme_path = collectors_dir / "README.md"
    example_path = collectors_dir / "collect-example.sh"
    skill_path = root / ".claude" / "skills" / "mb-pulse" / "SKILL.md"
    targets = (readme_path, example_path, skill_path)
    existing = [str(p.relative_to(root)) for p in targets if p.exists()]
    if existing and not force:
        return {
            "ok": False,
            "repo": str(root),
            "written": [],
            "skipped": existing,
            "summary": (
                "pulse files already exist; rerun with --force to overwrite "
                "(your collectors keep their own names, so collect-example.sh "
                "is the only collector at risk)"
            ),
            "safe_to_share": True,
        }
    collectors_dir.mkdir(parents=True, exist_ok=True)
    skill_path.parent.mkdir(parents=True, exist_ok=True)
    readme_path.write_text(COLLECTOR_README_TEMPLATE, encoding="utf-8")
    example_path.write_text(EXAMPLE_COLLECTOR_TEMPLATE, encoding="utf-8")
    example_path.chmod(0o755)
    skill_path.write_text(
        SKILL_TEMPLATE.replace("{{SLUG}}", _slug_for(root, slug)), encoding="utf-8"
    )
    return {
        "ok": True,
        "repo": str(root),
        "written": [str(p.relative_to(root)) for p in targets],
        "skipped": [],
        "summary": (
            "pulse scaffold written — copy collect-example.sh once per source "
            "(see the collectors README for the contract), then run /mb-pulse "
            "for the first paper; `mb pulse install` emits a daily run wrapper"
        ),
        "safe_to_share": True,
    }
