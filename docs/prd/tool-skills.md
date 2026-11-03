---
title: "PRD: tool skills (a pinned registry, a doctor section, a usage count)"
status: draft
date: 2026-11-03
release: planned (after the design is approved)
---

# PRD: tool skills

## Decision

When a good tool ships its own skills, Main Branch points to them at a pinned
version and adds the business layer around them. The tool does the work. Main
Branch decides whether the work is wanted, stays inside the owner's limits, and
keeps the result.

Three pieces, built in this order:

1. **A tools registry**: one reviewed data file in the engine that says, per
   tool, what we point to and which version we last tested.
2. **A "Tool skills" section in `mb doctor`**: read-only facts about whether
   the tool's skills are present, wired to the right place, and current.
3. **A usage count** (later, opt-in): how often the owner's agents used those
   skills, from the owner's own transcripts.

Rules that hold throughout:

- `mb` never installs, updates, pulls or rewrites a tool's skills. It prints
  the install command and the release notes link for the owner. Devon's
  direction: do not help them update; make sure they know.
- Nothing leaves the machine. No upload, no counter inside a skill.
- Optional tools never turn a healthy business red. Info by default; warn only
  when the business's own record says it uses the tool.
- A fact that could not be read is `not_verified`, never a pass. Same rule as
  [`mb machine doctor`](v0-7-machine-doctor.md).
- Text inside an installed tool skill is instructions an agent will obey. It
  never overrides the owner's limits or Main Branch's hard rules. Wrappers say
  so.
- The pin lives in the host's own config, not only in a Main Branch file.
  Doctor verifies the host setting; it never writes it.
- Spend and publish limits are enforced by a hook, not by wrapper prose.
- Proof comes from live businesses, never from throwaway copies (see
  [Bumping a pin](#5-bumping-a-pin)).

Out of scope: running any installer, a combined "update everything", vendoring
a tool's files into the engine, MCP calls from `mb` (it cannot make them), and
claims of Codex support before a smoke run on the exact surface.

## Why

Today facts about third-party tools live in skill prose, so they drift:

- `mb-seo` names OpenSEO but none of its skills, and tells the agent not to
  install the upstream plugin because the plugin's MCP entry points at the
  hosted service. It also re-explains flows the tool's own skills already
  teach, so two sets of steps will disagree.
- `mb-books` never names hledger's manual or a tested version.
- `mb doctor` checks Main Branch's own plugin (`plugin_wiring_status`,
  `plugin_registry_status` in `mb/mb/engine.py`) and Codex global skills
  (`mb/mb/codex.py`). Nothing checks a third-party skill, plugin or MCP entry.
- A business can have the tool's skills installed and never use them, or use
  the tool's MCP with an improvised workflow, and nobody can tell.

## Verified against primary sources (3 Nov 2026)

A third-party research brief (Grok INT-01) suggested the changes folded in
below. Its claims were checked before use. Marked V (verified) or U (not
verified, treated as open).

- V, Claude docs (marketplace reference): `github`, `url` and `git-subdir`
  sources take `ref` and a full 40-character `sha`; with both, Claude Code
  checks out `sha`.
- V, Claude docs (host a marketplace): background auto-update is off by
  default for a user-added marketplace; `marketplace.json` has no field to
  turn it on. The per-marketplace `autoUpdate` flag is set in `/plugin` or in
  managed settings. On the box checked, `known_marketplaces.json` entries
  hold only `source`, `installLocation`, `lastUpdated`, so an absent
  `autoUpdate` means the default (off). Doctor reads absent as off, `true` as
  on.
- V, Claude docs (hooks): `PreToolUse` fires for MCP tools, named
  `mcp__<server>__<tool>` (a bare `mcp__<server>` matches nothing; use
  `mcp__<server>__.*`), and exit 2 or `permissionDecision: "deny"` blocks the
  call.
- V (docs), U (field list): `UserPromptExpansion` exists, can block, and is
  what fires when the owner types `/skill-name`; `PreToolUse` on the `Skill`
  tool does not. The exact input fields (`command_name`, `command_source`)
  came from a summary and are confirmed on a real run before code.
- V, this box: `claude plugin list --json` and `codex plugin list --json`
  exist (Codex 0.164) and report id, version, scope, enabled, install path;
  Claude's output also lists a plugin's `mcpServers`.
- V (docs): plugin `dependencies` accept semver ranges, resolved from git tags
  named `<plugin>--v<version>`. U: OpenSEO and Impeccable publishing such
  tags is from the brief and is rechecked at bump time. Until they do, ranges
  cannot resolve, so the lock file (not `dependencies`) is the contract.
- U: Codex git marketplaces auto-upgrade at each start unless added with
  `--ref`; the brief cites source at a Codex tag. Not re-read here. Treat as
  true for the design (it only makes the pin check stricter) and confirm on a
  Codex smoke run.
- U: `npx skills check` / `npx impeccable check` as check-only precedents.
  Neither is run by `mb`. They are named in the owner's printed guidance only
  after a person confirms their behaviour.

## 1. The tools registry

### Where and what

One packaged data file: `mb/mb/_data/tools.json`. One entry per recommended
tool. Wrapper skills and docs read it, so a skill says "use the tool's
`keyword-research` skill" and the link, the name and the pin come from one
place. This is what `.claude-plugin/marketplace.json` and
`scripts/plugin_pin.py` already do for Main Branch's own plugin, pointed
outward.

JSON, not YAML, so the validator and the doctor load it with the standard
library. It is data only: no command in it is ever executed (see
`install.print`).

### Shape

```json
{
  "schema": "mb.tools",
  "schema_version": 1,
  "tools": [
    {
      "id": "openseo",
      "title": "OpenSEO",
      "kind": "app+skills",
      "source": {
        "repo": "https://github.com/every-app/open-seo",
        "docs": ["https://openseo.so/docs/skills/setup"],
        "release_notes": "https://github.com/every-app/open-seo/releases"
      },
      "app": {
        "ref": "<40-char sha>",
        "version": "0.1.21",
        "tested_on": "2026-11-03",
        "tool_names_file": "mb/mb/_data/tools/openseo.app-tools.json"
      },
      "skills": {
        "ref": "<40-char sha>",
        "version": "1.0.25",
        "tested_on": "2026-11-03",
        "names": ["keyword-research", "seo-audit", "seo-report"],
        "points_to": ["keyword-research", "seo-audit"],
        "calls_tools": {
          "keyword-research": ["research_keywords", "get_keyword_metrics"],
          "seo-audit": ["run_site_audit", "get_audit_issues"]
        },
        "must_not_install": [".mcp.json"]
      },
      "mcp": {
        "name_pattern": "openseo-<business>",
        "must_match": "recorded_host",
        "hosted_default_host": "app.openseo.so",
        "paid_tools": ["research_keywords", "get_keyword_metrics", "run_site_audit"]
      },
      "jobs": {
        "keyword research": "keyword-research",
        "site audit": "seo-audit"
      },
      "runtimes": [
        {"runtime": "claude", "tested": true, "tested_with": "claude-code 2.x"},
        {"runtime": "codex", "tested": false}
      ],
      "install": {
        "print": [
          "npx skills add every-app/open-seo --skill '<name>' --agent claude-code"
        ],
        "note": "Printed for the owner. mb never runs it."
      },
      "business_record": {
        "path_glob": "decisions/*-seo-openseo-setup.md",
        "front_matter_key": "tool"
      },
      "wrapper_skills": ["mb-seo"]
    }
  ]
}
```

Field notes:

- `kind`: `skills`, `plugin`, `cli`, `app+skills`. hledger is `cli` with an
  empty `skills` block; it still gets docs links and a tested version, so
  `mb books doctor` can say what it has already said about the binary.
- `app.ref` and `skills.ref` are separate on purpose. For OpenSEO the app is a
  deploy the owner chose; the skills are a documentation choice. One bump must
  not silently force the other. `app` is absent for tools with no app.
- `skills.names` is every skill the pinned ref ships. `points_to` is the
  subset our wrappers name. `calls_tools` is what those skills call; it is
  extracted at bump time and reviewed by a person (see
  [Bumping a pin](#5-bumping-a-pin)).
- `app.tool_names_file` holds the tool names the pinned app exposes. The
  validator checks `calls_tools` against it, which enforces the rule that
  **skills must not call tools the pinned app lacks**.
- `must_not_install` lists upstream files our install path leaves out. For
  OpenSEO the plugin's own `.mcp.json` points at the hosted service, so the
  documented route installs skills without it and wires MCP to the owner's
  own copy. The skills installer route (`npx skills add`, or copying
  `SKILL.md` files) already separates the two.
- `runtimes[].tested` is the claim we are allowed to make. Doctor and docs may
  not say "works in Codex" unless it is `true` with a version.
- `install.print` is display-only strings. Doctor prints them. Nothing parses
  or runs them, so there is no template, no shell and no interpolation
  (security ruling for `mb machine`, applied here).
- `business_record` says how a business records that it uses the tool. That is
  what flips doctor from info to warn.
- Generic only: examples in the engine use synthetic business names. No
  machine paths, accounts, hosts or project ids appear in the file.

### The host holds the pin; the lock records it

A warning after the host has already moved is too late: Claude Code and Codex
can pull a newer release on their own. So the pin must exist in the host's
config, and `mb` checks it.

- **Claude Code:** the marketplace source carries `ref` and a 40-character
  `sha`, and the marketplace's auto-update is off.
- **Codex:** the marketplace was added with `--ref`, so startup cannot
  upgrade it.
- **Loose skills** (the skills installer route): the pin is the lock's tree
  hash, since no host tracks a ref.

`mb` records what the owner should have, in a **business-side lock** at
`.mainbranch/tools.lock` (JSON), written by the owner or an agent at install
time, never by a background job. Per tool: `source`, `ref`, `sha`, the skill
names relied on, a tree hash of those skill folders, `installed_on`, `route`
(`plugin`, `skills_installer`, `copied`) and `runtime`. The engine registry
says what we tested; the lock says what this business installed. Doctor
compares three things: registry, lock and host.

Drift reports, all display-only:

| Finding | Meaning |
|---|---|
| `host_unpinned` | marketplace has no `sha`/`ref`, or auto-update is on (Codex: no `--ref`) |
| `lock_missing` | tool in use, no lock entry |
| `lock_host_mismatch` | the host's sha differs from the lock's |
| `tree_changed` | installed skill folders differ from the lock's tree hash |
| `releases_behind: N` | tags newer than the pin, read from upstream tags |

`releases_behind` needs the network, so it is opt-in (`mb doctor tools
--online`), uses a fixed `git ls-remote --tags` against the registry's own
`source.repo` only, and is `not_verified` otherwise. Plain `mb doctor` stays
offline. The tree hash covers file paths and bytes of the named skill
folders, sorted, so a local edit shows as `tree_changed`.

### Validator

`scripts/check_tools.py`, run from `scripts/check.sh` and release preflight,
the same way `plugin_pin.py check` runs. Offline by default; `--online`
reads upstream and is used only when bumping.

It fails when:

- the file does not match the schema, an id repeats, or a ref is not a full
  40-character sha;
- a wrapper skill (`wrapper_skills`) names a tool skill that is not in
  `skills.names`. It finds names by scanning the wrapper for the marker
  `` `tool:<id>/<skill>` ``; the marker is the only syntax it reads, so prose
  is free;
- `calls_tools` names a tool absent from the pinned app's tool list;
- `tested_on` is later than the file's commit date, or `runtimes[].tested` is
  true with no `tested_with`;
- an `install.print` string contains a shell metacharacter the doctor would
  have to interpret, or any `@` marker for a host other than the documented
  upstream. (Strings are displayed as-is; the check keeps them boring.)
- a skill in `points_to` appears in two registry entries (name clash), or
  collides with a bundled `mb-*` skill.

A maintainer-only warning, not shown to owners: a pin older than 90 days while
upstream has newer releases. It prints in release preflight.

## 2. `mb doctor`: the "Tool skills" section

### What it reads

For each registry tool, per runtime, three facts, reported separately. Mixing
them hides the real problem, as `mb-seo` already insists for the guard, the
app and the data.

1. **Skills present.** Names only, plus a hash of each `SKILL.md`.
   - Claude plugin registry: `$CLAUDE_CONFIG_DIR/plugins/installed_plugins.json`
     (default `~/.claude`). Shape checked on a live box on 3 Nov 2026:
     `version: 2`, `plugins` keyed `<plugin>@<marketplace>`, each a list of
     entries with `scope`, `installPath`, `version`, `gitCommitSha`. The
     reader copies `plugin_registry_status`: open with `O_NONBLOCK`, regular
     file only, 1 MiB cap, no raw content or exception text returned. A
     different `version` value means `not_verified` (reason `format_changed`).
   - Loose skill folders: `~/.claude/skills`, the repo's `.claude/skills`,
     `~/.agents/skills`, and the Codex skills root that `codex.py` already
     resolves (`MAINBRANCH_CODEX_SKILLS_ROOT`, default `~/.codex/skills`).
     Symlinks are followed once, to a regular directory owned by the current
     user; the resolved path is not reported.
2. **Tool wired.** An MCP entry with the registry's `name_pattern` exists and
   its URL host equals the host the business recorded. Sources, read-only:
   - Claude: the user config (`~/.claude.json`, `mcpServers` at user scope and
     under `projects.<repo>` for local scope) and the repo's `.mcp.json`.
     Key names above the `projects` map were checked on 3 Nov 2026. The
     `mcpServers` key inside a project entry was **not** seen on that box; it
     must be verified before code is written.
   - Codex: `~/.codex/config.toml` MCP tables, with the `enabled` flag read
     (an entry can be present and disabled).
   - Output keeps the host only, never the full URL, a token, a project id or
     a header. An entry whose host differs from the recorded one is the
     hosted-service trap and is reported as such (`host_mismatch`).
3. **Version against the pin.** Compare what is installed with
   `skills.ref` / `skills.version` (plugin registry version and
   `gitCommitSha`; for loose folders, the hash). Results:

   | Result | Meaning |
   |---|---|
   | `current` | matches the pin |
   | `older` | installed is older than the pin |
   | `newer` | installed is newer than the pin; not tested, nothing wrong |
   | `locally_changed` | hash differs from every known hash for this tool |
   | `unknown` | no version evidence (loose copy of unknown origin) |

   Known hashes ship in the registry as `skills.hashes[<name>]`, a list that
   includes the pinned hash. Doctor never says "downgrade".

"Works" (a free read such as `whoami`) is a fact the skill checks in a
session. `mb` cannot call MCP and does not try.

### Severity

- **info** by default. A tool nobody here uses stays quiet or one line.
- **warn** only when the business's own record says it uses the tool: a file
  matching `business_record.path_glob` whose front matter `tool` key names the
  registry id. That is the only trigger. Installed skills alone do not make a
  business "a user of the tool".
- One exception to "never an error": the tool is in use and its MCP entry
  points at the tool's **hosted default** instead of the host the business
  recorded (`host_mismatch`). That sends project data and spend to someone
  else's server, so it is severity **error** for that check only. It still
  changes no files and does not alter other checks.
- Otherwise never an error. Never changes `ok` or exit codes. Same treatment as the
  plugin source warnings in
  [`docs/json-output-contract.md`](../json-output-contract.md#plugin-source-warnings).

### JSON

Added to `mb doctor --json` as a check named `tool-skills`, with warning
severity at most, plus a structured payload that
[`docs/json-output-contract.md`](../json-output-contract.md) gets in the same
PR that ships the code. Shape:

```json
{
  "name": "tool-skills",
  "severity": "info",
  "ok": true,
  "detail": "OpenSEO: skills present in Claude, not checked in Codex.",
  "tools": [
    {
      "id": "openseo",
      "in_use": true,
      "pin": {"skills_version": "1.0.25", "tested_on": "2026-11-03"},
      "runtimes": [
        {
          "runtime": "claude",
          "tested": true,
          "skills": {
            "state": "present",
            "found": ["keyword-research", "seo-audit"],
            "missing": ["seo-report"],
            "where": ["plugin_registry"]
          },
          "mcp": {
            "state": "wired",
            "name": "openseo-example",
            "host_matches_record": true
          },
          "version": {"state": "older", "installed": "1.0.20"},
          "host_pin": {"state": "pinned", "auto_update": false},
          "lock": {"state": "matches"},
          "spend_hook": {"state": "installed"}
        },
        {
          "runtime": "codex",
          "tested": false,
          "skills": {"state": "not_verified", "reason": "runtime_untested"},
          "mcp": {"state": "not_verified", "reason": "runtime_untested"},
          "version": {"state": "unknown"}
        }
      ],
      "next_actions": [
        {
          "kind": "owner_command",
          "display_only": true,
          "text": "npx skills add every-app/open-seo --skill 'seo-report' --agent claude-code",
          "read_first": "https://github.com/every-app/open-seo/releases"
        }
      ]
    }
  ],
  "summary": {"tools": 1, "in_use": 1, "needs_attention": 1}
}
```

State values:

- `skills.state`: `present`, `partial`, `absent`, `not_verified`.
- `mcp.state`: `wired`, `disabled`, `host_mismatch`, `absent`, `not_verified`.
- `host_pin.state`: `pinned`, `host_unpinned`, `not_verified`.
- `lock.state`: `matches`, `missing`, `host_mismatch`, `tree_changed`.
- `spend_hook.state`: `installed`, `absent`, `stale`, `not_enforced`.
- `version.state`: `current`, `older`, `newer`, `locally_changed`, `unknown`.
- `reason` for `not_verified`: `runtime_untested`, `format_changed`,
  `unreadable`, `too_large`, `no_config`.

`next_actions[].display_only` is always true. The command string comes from
the registry's `install.print` and is never built from detected values.

### Human lines

Business language first. One line per tool and runtime, only when there is
something to say:

```
Tool skills
  OpenSEO is set up for this business, but its keyword and audit skills are
  not installed in Codex. Codex is not tested with them yet, so this is
  informational. (info)
  OpenSEO is connected to a different server than this business recorded.
  Check the connection before using it. (warn)
  Newer tested OpenSEO skills are available. Read what changed, then update
  with the tool's own installer when it suits you. Release notes: <link> (info)
  Your OpenSEO skills have local edits. Nothing is wrong; results may differ
  from what we tested. (info)
```

`mb update` prints this section after its own update and stops. It never
offers "update everything".

### Per-runtime honesty

Claude Code is the tested runtime. Codex checks run only where the registry
sets `tested: true` with a version; otherwise the Codex rows are
`not_verified` with `runtime_untested`. Doctor prints "not checked" rather
than guess, the way `mb books doctor` handles `not_run`.

### Name clashes

Doctor reports two installed skills with the same name from different
sources (for example a plugin-namespaced `seo-audit` and a loose one). Our
wrappers refer to namespaced names, and bundled `mb-*` skills must not be
shadowed.

## 3. Enforcement: hooks, not prose

Wrapper text is an instruction the model may skip. A tool's own skills do not
know the owner's cap, and a "read-only" hint is not "free". Where Claude Code
offers a hook, the limit is a hook.

- **Spend gate.** A `PreToolUse` hook matched on the tool's paid MCP tools
  (`mcp__<server>__<tool>`, from the registry's `paid_tools`) blocks the call
  unless the business has an approval record naming the estimated cost and
  not yet used up. The approval is a small file in the business repo written
  when the owner says yes. The hook reads local files only, exits 2 with a
  business-language reason when there is no approval, and never prompts.
- **Where it comes from.** The hook script ships with the engine as data; the
  registry lists the paid tool names (extracted at bump time and reviewed).
  Doctor reports `hook: installed | absent | stale` per tool in use. Adding
  the hook to the owner's settings is an owner action: doctor prints it and
  never edits settings. Same rule as every fix here.
- **Free versus paid is Main Branch's knowledge.** The registry's
  `paid_tools` list is the one place it lives; wrapper prose points to it
  rather than restating a table.
- **Cannot enforce:** the provider's own balance, calls made outside Claude
  Code, or a runtime with no hook. Codex has no tool hook of this kind in the
  brief's reading, so on Codex the rows say `not_enforced` and the wrapper
  asks first. The limit is stated, not implied.
- **Fail closed for spend, quiet for everything else.** If the approval file
  is unreadable, the paid call is blocked. A broken usage logger never blocks
  anything.

Hooks run commands, so they get the same security read as any isolation
control before they ship.

## 4. Usage count (later, opt-in)

A read-only command, `mb doctor tools --usage` (or a field in `mb status
--json`). Built after section 2 ships, because "installed" has to be solid
before "used" means anything.

- **Collected two ways, both local.** (a) A `PreToolUse` hook on the `Skill`
  tool and a `UserPromptExpansion` hook, which together cover skills Claude
  calls and skills the owner types as `/name`. Each appends one line (skill
  name, timestamp, runtime) to a private file in the business's local state,
  gitignored. (b) Transcript reading, for sessions before the hooks existed.
  Hooks alone undercount (hooks off, other machines); transcripts alone miss
  nothing but depend on a format we do not own. Use hooks going forward and
  transcripts as backfill, and say which source a number came from.
- **Codex:** no skill hook is known. A rollout reader (Codex sessions
  directory) can show reads of `SKILL.md`, which is inference, not proof of
  use. Its own skill tracking goes to the vendor's analytics, which is not
  ours to read. Until a smoke run proves a reader, Codex usage is `unknown`.
- **Reads:** the owner's own Claude transcripts
  (`$CLAUDE_CONFIG_DIR/projects/*/*.jsonl`) for `tool_use` events with
  `name: "Skill"` and `input.skill`, and the matching Codex session logs where
  the format is known.
- **Counts only:** per skill name, uses in the last 30 and 90 days and the
  last-used date. Skill names are limited to the registry plus bundled `mb-*`
  names. No prompts, paths, project names or business text are read into
  memory beyond the single field, and none are printed.
- **Flags:** installed and never used in 30 days; used but not installed (a
  stale or wrong name, or a plugin-namespaced one); the tool's MCP called with
  no matching skill used that session (the agent improvised the workflow).
  Advice to the owner ("you installed 12 SEO skills and used 2"), not a
  metric for us.
- **Fails quiet:** if the event shape is not recognized, print "usage
  unknown" and exit 0. The transcript format belongs to Anthropic. The
  `tool_use` shape above is **not yet verified against a transcript** and is
  the first thing to confirm; the sample read on 3 Nov 2026 did not settle it.
- **Opt-in:** the hooks are installed by the owner on request, and the
  command is run by the owner. Bounded: file size cap, line
  length cap, newest N files, no following symlinks out of the config dir.
- **Never:** upload, add counters to skills, or write the result anywhere
  except stdout.

What it cannot see, said plainly in the output:

- Skills the agent read as a file instead of invoking.
- Other users' transcripts. Each account sees only its own.
- Transcripts the owner deleted or a runtime does not keep.
- Whether the skill's advice was followed or was any good.
- Runtimes without a known log format.
- Time spent. It counts invocations, not value.

## 5. Bumping a pin

Mirrors the plugin pin (`scripts/plugin_pin.py`,
`scripts/release-pin-plugin.sh`): a human-reviewed PR with evidence. No bot
changes a pin.

1. **Read upstream.** Release notes between the pin and the candidate. Diff
   the skills in `points_to`: names, tools they call, anything that spends,
   any `.mcp.json` or hook change, new network destinations, new install
   steps.
2. **Run `scripts/check_tools.py --candidate <id>@<ref> --online`.** It
   extracts the tool names each skill calls from the candidate and prints a
   proposed `calls_tools` block, plus the candidate app's tool list. A person
   reviews the extraction; the script proposes, a human commits.
3. **Check compatibility.** Every tool a skill calls must exist in the app
   version the registry pins (`app.tool_names_file`). A skills bump that needs
   a newer app is blocked until the app pin moves, and the app pin is a
   deploy decision needing the owner's yes, not a documentation edit.
4. **Prove it on a live business.** Run the wrapper with the candidate on a
   business that really uses the tool, with that owner's agreement and inside
   their cap. Throwaway copies do not count: they miss the real context,
   limits and quirks. The PR carries a short evidence block: which business
   (by role, not by name, if the PR is public), runtime and version, the
   skills run, what was spent against what was estimated, what the wrapper
   saved, and what surprised us.
5. **One PR.** It changes `tools.json`, the wrapper if its seam changed, and
   `CHANGELOG.md`. `check_tools.py` and `scripts/check.sh` pass. A security
   read is required when the diff touches `install`, `must_not_install`, MCP
   handling, or spend rules.
6. **Release.** Pins are read from the packaged data, so a bump ships in the
   next release. Owners learn about it through doctor's "newer tested
   version" line and the release notes; nobody is updated.

Security or spend issue in a pinned ref: a hotfix PR that changes `tested_on`,
sets `advisory` on the entry (text and link), and makes doctor warn for
in-use businesses with the action named.

## 6. Build order

1. Registry, schema, validator, and `mb-seo` / `mb-books` rewritten to read it
   (markers only, no copied steps). No doctor yet.
2. Doctor section: present, wired, version, host pin and lock. Claude only. Codex rows are
   `not_verified` until a smoke run exists.
3. Codex readers, once smoke evidence for the exact surface exists.
4. Spend-gate hook (security read first), then the usage hooks and
   `mb doctor tools --usage`, opt-in.
5. Next tool (for example a design-critique tool) follows the same entry
   shape with no engine change. If it needs one, the shape was wrong.

Each step adds the fixture/package/runtime smoke evidence that `AGENTS.md`
asks for when skill discovery or doctor changes.

## 7. Open questions and recommended answers

1. **Where does the skills install route get documented, and which is the
   default?** The skills installer (`npx skills add ... --agent`) installs
   without the plugin's hosted MCP entry. *Recommend:* make it the one
   documented route, recorded from how the live businesses already did it
   (route, scope, version), and keep "copy `SKILL.md` files" as the fallback.
2. **One registry file or one per tool?** *Recommend* one file with a
   per-tool side file for large lists (the app tool names). Review stays in
   one place; diffs stay small.
3. **Does a business-record front-matter key exist yet?** Setup decisions are
   `decisions/YYYY-MM-DD-seo-openseo-setup.md` today with no `tool` key.
   *Recommend:* add `tool: openseo` to what the setup flow writes, and for
   existing businesses fall back to the filename glob alone for one release.
4. **Should doctor read MCP config at all, given it holds URLs?** *Recommend
   yes, host only.* The wrong-host trap is the highest-impact failure; URLs,
   headers and tokens never leave the reader.
5. **Is info-only too quiet?** *Recommend* keep info by default, and promote
   to warn only on the business's own record. Revisit after a month of real
   output.
6. **Do hashes make "locally changed" noisy?** Owners may legitimately edit.
   *Recommend* report it as info with "nothing is wrong", and drop it if it
   produces complaints.
7. **Usage across Claude and Codex.** *Recommend* ship Claude first and say
   "unknown" for Codex until the log format is verified.
8. **Who owns a tool's `PRODUCT.md`-style files (design tools)?** *Recommend*
   the business repo stays the record: Main Branch drafts from offer,
   audience and voice for the owner to approve; the tool's files live in the
   site repo; the engine never vendors them.
9. **Plugin-namespaced versus loose skill names.** The registry stores both
   forms. *Recommend* wrappers use the namespaced name when installed as a
   plugin and doctor reports which form it found.
10. **Where does the lock live and who writes it?** *Recommend*
    `.mainbranch/tools.lock` in the business repo, written by the install
    step the owner approves, committed like any other record. Doctor never
    writes it.
11. **Does `mb` ship hooks at all?** It is a new surface that runs code on
    every tool call. *Recommend* yes for the spend gate only, owner-installed,
    reviewed by security, with usage hooks as a separate later opt-in.
12. **Route by job, with a test.** *Recommend* a small table in the registry
    mapping each Main Branch job to a tool skill or command name, and a CI
    check that fails if the pinned tree lacks that name. Impeccable is one
    skill with many commands, so its entry names commands under one skill,
    not 24 skills.
13. **hledger writes.** *Recommend* the wrapper states: reads through
    hledger's own reports (`-O json`), writes only through `import --dry`,
    `hledger check`, then a commit the owner approves; any hledger MCP only
    in read-only mode. Unverified (from the brief); confirm in the hledger
    docs before the wrapper says it.
14. **Facts not yet verified.** The Claude local-scope `mcpServers` location,
    the Codex MCP table layout, the `UserPromptExpansion` input fields, and the
    transcript `Skill` event shape need a check on a live box before the code that reads them. Until then the
    corresponding rows are `not_verified`.

Next action: approve the shape (sections 1 and 2), then step 1 of the build
order.
