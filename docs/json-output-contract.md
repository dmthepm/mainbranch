# JSON Output Contract

Main Branch CLI JSON is for skills, runtime harnesses, dashboards, and scripts
that need deterministic facts without parsing human terminal output.

The v1 result envelope is additive. Commands keep their existing domain payload
keys at the top level, and high-value `--json` surfaces also expose shared
metadata:

```json
{
  "result_envelope_version": "1.0",
  "result_schema": {"name": "mainbranch.status", "version": "1.0"},
  "mb_command": "mb status",
  "ok": true,
  "result_status": "ok",
  "errors": [],
  "warnings": [],
  "actions": []
}
```

JSON surfaces normalize Python `date` and `datetime` values to ISO strings
before writing output. If `mb status --json` cannot produce its normal payload,
it returns the same envelope with `ok: false`, `result_status: "error"`, and a
safe error action instead of leaking a Python traceback or local filesystem
path.

## Shared Fields

- `result_envelope_version`: shared result-envelope version. This is separate
  from any command-specific `schema_version` field.
- `result_schema`: shared result-envelope schema identifier for the command
  surface. This is separate from any command-specific `schema` field.
- `mb_command`: the `mb` command surface that emitted the JSON. The field is
  prefixed so commands can keep existing domain keys such as `command`.
- `ok`: boolean success flag suitable for automation. It answers "is this
  healthy", which is not always the same question as the process exit code,
  which answers "is there something you can act on". `mb connect` deliberately
  reports `ok: false` while exiting 0 for a stored-but-unverified provider that
  has no validation probe, because nothing the operator can run would change it;
  see [connect.md](connect.md#what-the-exit-code-means).
  A provider with `state: credential_not_checked` is the same kind of case:
  `mb connect status`, `list` and `mb doctor` ran out of their shared credential
  read time before reaching it, so `ok` is `false`, nothing is reported broken,
  and the exit code does not fail. `summary.not_checked` appears in
  `mb connect status --json` only when at least one provider was not checked;
  see [connect.md](connect.md#credential-not-checked).
- `result_status`: concise machine-readable envelope state, currently `ok` or
  `error`. Commands may still expose their own domain `status` field with
  command-specific values such as `ready`, `valid`, `committed`, or structured
  provider state.
- `errors`: top-level list of failure messages or objects. Empty when there are
  no shared top-level errors.
- `warnings`: top-level list of warnings. Empty when there are no shared
  top-level warnings.
- `actions`: top-level list of recommended or repair actions when the command
  already exposes them. Empty for commands whose actions live in
  command-specific sections such as `ranked_actions` or `next_actions`.

## Command-Specific Fields

Existing command payload keys remain top-level and keep their command-specific
meaning. In particular, `schema`, `schema_version`, `status`, and `command`
are not shared envelope fields in v1. For example, `mb status --json` keeps its
status schema object, `mb doctor repair --json` keeps
`schema: "mb.doctor.repair"` and `schema_version: 1`, and `mb checkpoint --json`
can keep a domain `status` such as `ready` while the envelope reports
`result_status: "ok"`.

`mb status --json` includes a `money_path` section for read-only business-path
readiness. It reports gated component objects for customer progress, offer,
audience, proof, product ladder, CTA path, channel strategy, active push,
playbook, page readiness, and outcome feedback. These facts describe whether
the path is legible, supported, connected, and instrumented; they do not infer
conversion quality, market strength, or strategic correctness.

`mb checkpoint --validate <message> --json` includes a `contract` object for
the checkpoint subject format. In v1 this contract is a bracketed finite
business verb, a required object, and an optional result segment:

```json
{
  "contract": {
    "format": "[verb] object [-- result]",
    "format_id": "bracket_verb",
    "accepted_prefixes": ["[added]", "[updated]"],
    "legacy_prefixes": ["[checkpoint]"]
  }
}
```

`accepted_prefixes` contains the full packaged verb registry in command output;
the shortened example above is illustrative. `legacy_prefixes` are readable in
history but are not accepted for new checkpoint subjects.

### Operator Actions

`mb update --json` and `mb doctor repair --json` include an `operator_actions`
list: steps that change tracked files in the business repo, so a person runs
them at a terminal. An agent shows each entry to the person and never runs it,
even when it runs `next_actions` or applies doctor repairs. Each entry has:

- `command`: the command for the person to run.
- `changes`: the tracked files the command writes.
- `note`: a short explanation for the person.

Entries today:

- the plugin-rail switch for a repo still on symlink-only skill wiring
  (`mb update` and `mb doctor repair`);
- from `mb update`, each surface-refresh apply command it declined to run
  without a person (no terminal, `--json`, or a "no" at the prompt): the
  skill-link refresh (`mb skill link --repo <path>`, usually `.gitignore`) and
  the Codex refresh (`mb doctor repair --repo <path> --apply --only codex`,
  which writes or creates `AGENTS.md` and can delete tracked transitional
  plugin copies). Each entry's `changes` comes from that surface's tracked
  writes, plus a missing `AGENTS.md` the Codex refresh would create (#1053)
  or a missing `.gitignore` the skill-link refresh would create (#1087; listed
  in `surface_refresh.planned.tracked_changes` with `op: "create"`). A
  `.gitignore` that is an untracked or dangling link is held the same way and
  listed with `op: "replace_link"`; the terminal prompt names it
  `.gitignore (replace link)`. The
  same commands stay in `surface_refresh.planned.apply_commands`; they are not
  in `next_actions`. The read-only
  `mb doctor repair --repo <path> --plan --only codex` stays in `next_actions`,
  once, so an agent can show the plan first. `mb update --check` writes
  nothing and lists no apply command here, but its `surface_refresh.planned`
  (`consent`, `tracked_files`, `tracked_changes`, `apply_commands`) predicts,
  with the installed version's templates, what a run without a terminal would
  report (#1100). When a newer release is available, that release may also
  stop for `AGENTS.md`. If a file the plan reads cannot be read (not UTF-8, no
  permission, a folder, a link that loops), `--check` predicts nothing and
  names it in `warnings`; the run stops there with an error. The same holds
  for the Codex readiness read (an `AGENTS.md` that is not UTF-8, a repo
  `.claude` folder or `CODEX_HOME` you cannot open, #1106). The path is
  relative to the repo, or `~/...` under the home folder; a path outside both
  (for example `CODEX_HOME=/opt/codex`) is shown absolute. A folder on the way
  that cannot be entered, or a link on the way that loops, is named instead of
  the path below it (#1109). The sentence ends with that file's own fix. When
  a file that is not UTF-8 cannot be told apart, no file is guessed: the
  message says "a file it needs". `mb doctor --json`,
  `mb doctor repair --plan --json` and `mb skill link --plan --json` stop with
  exit 1 and one error `{"code": "unreadable_file", "message": ...}` naming
  the same path;
- from `mb update`, including `--check` and `--no-refresh-surfaces`, the Codex
  `AGENTS.md` repair when Codex guidance is still not ready after the refresh
  (or the refresh did not run): the same
  `mb doctor repair --repo <path> --apply --only codex`, with `changes` from
  the `AGENTS.md` plan. It is not listed twice when the refresh already listed
  it;
- the Codex `AGENTS.md` repair while it needs a person first
  (`mb doctor repair` and `mb update`, #1052). This entry also has
  `id: "codex-agents-md"`, `reason` and `manual_step` (also folded into
  `note`). It appears when the repair would refuse to touch `AGENTS.md`
  (managed markers missing or out of order, or older generated guidance that
  no longer matches the template its metadata names), or when old repo-local
  Codex paths hold files Main Branch cannot prove it wrote. A file is proven
  only when its content equals a version a released `mb` wrote there (or what
  this `mb` renders), allowing only for the embedded `mb` version number (a
  plain X.Y.Z) and line endings, with JSON files compared as data (whitespace
  and key order); names and wording are not proof. A JSON file that repeats a
  key, at any depth, and a file that cannot be read (not UTF-8, or an OS error)
  are not proven. The repair removes only proven
  files and never touches anything else, including a generated file a person
  added to (#1062). Each file is proven again right before it is removed, so a
  file changed after the plan, or reached through a folder that became a link
  after the plan, stays and is listed in the apply's `kept`. A
  linked folder above a Codex path (`.agents/`, or a folder under it) is not
  walked: the link is listed in `kept`, the `reason` says it is a link, and
  nothing under it is touched (#1067). While
  this entry is present, doctor's `codex-agents-md` action has
  `safe_to_apply: false` with the additive `refused` and `kept` lists, and
  `mb update` makes no Codex write (`surface_refresh.codex.blocked: true` and
  a `reason`) and asks no consent for it. The action and this entry both carry
  `on_apply` (`writes`, `removes`, `keeps`): exactly what an explicit
  `mb doctor repair --apply --only codex` or `--all-agents` does. A refusal
  writes and removes nothing; otherwise it rewrites `AGENTS.md` when listed,
  deletes only the listed Main Branch files and keeps the rest (#1056).
  `mb init` returns the same entry, plus a `warnings` line, when it refuses to
  change an existing `AGENTS.md`; `codex_agents_md` has its `ok`, `refused`
  and `kept`.
- files in the global Codex folders that are not proven to be Main
  Branch's (`mb doctor repair`, #1062; `mb update`, #1067): any such file in
  the global plugin source or the legacy `main-branch-owner-loop` skill folder,
  and in a retired playbook skill folder only when that folder also held a
  Main Branch file (a same-named folder with nothing of Main Branch's in it is
  left alone and not listed). A global `mb-*` skill file that cannot be read
  is listed too, and is not overwritten. A link at the global plugin root, at
  its `mainbranch` folder, or at a folder under the root is listed instead of
  what it leads to; nothing under it is walked (#1067). This entry has
  `id: "codex-global-kept"`, `reason`, `manual_step`, `changes` (the kept
  files) and `on_apply`, with the same meaning as above. While it is present,
  doctor's `codex-global-skill` action has `safe_to_apply: false` and the same
  `on_apply`; an explicit apply, or `mb update`, deletes only the proven files
  and leaves these. `mb update`, including `--check` and
  `--no-refresh-surfaces`, lists the same entry once, with doctor's fields and
  its `note` also in `warnings`, so an operator who runs only `mb update` is
  told. A linked global skill folder (`<skills root>/<name>` is a link) is
  listed here only while the skill file it leads to is not the current one.
  When it already holds the current skill file there is nothing for a person
  to do, so it is not in `kept` and gets no `codex-global-kept` entry (#1087).
  Instead the global skill status (`codex_cli.global_skill` in `mb status`,
  `codex_adapter.global_skill` in `mb update`, the `codex-global-skill` check
  in `mb doctor` and `mb doctor repair`) and the result of the global skill
  apply carry two additive keys, `linked` (those folders) and `note` (an
  informational sentence, also appended to the status `summary`); `mb update`
  prints it as a `note:` line, not a warning. Neither key is present when no
  such folder exists. Nothing is ever written through the link.

```json
{
  "operator_actions": [
    {
      "command": "mb skill link --repo /Users/me/my-business",
      "changes": [".gitignore"],
      "note": "For a person to run at a terminal, not an agent: ..."
    },
    {
      "command": "mb skill link --repo /Users/me/my-business --plugin",
      "changes": [".claude/settings.json"],
      "note": "For a person to run at a terminal, not an agent: ..."
    },
    {
      "command": "mb doctor repair --repo /Users/me/my-business --apply --only codex",
      "changes": ["AGENTS.md"],
      "note": "For a person to run at a terminal, not an agent: ..."
    }
  ]
}
```

In `mb update` entries, `<path>` is the business repo's absolute path,
shell-quoted, so the command runs from any directory; the `--repo` flag is
left out only when that repo is the current directory. The same rule applies
to the Codex `operator_actions` entries of `mb doctor repair` and `mb init`
(`codex-agents-md`, `codex-global-kept`, including their `manual_step`), and
to the `repair` and `repair_command` strings in the Codex status blocks
(`codex_cli` in `mb status` and `mb start`, the Codex checks in `mb doctor`)
(#1072). The command fields below follow the same rule, and JSON keys are
unchanged; only the command values gain the flag: `next_actions` (`mb update`, `mb update --check`, the plan
command), the plugin-rail switch (`mb skill link --repo <path> --plugin`),
the retry and package-upgrade prose in `warnings`, and doctor's
`actions[].command`, `sections[].actions[].command`,
`sections[].checks[].repair_command` (the legacy `campaigns/` migration is
`mb migrate --repo <path> campaigns --plan`),
`agent_surfaces.surfaces[].repair_command`, `agent_surfaces.scope_choices`,
`agent_surfaces.apply_choices` and `post_apply`. Each command in a `&&` chain
names the repo exactly once, and a path that looks like a command is quoted,
not split. `mb status`, `mb graph` and `mb doctor` take the path as an argument, so their
suggestions end with it (`mb status --json --peek <path>`). Only the `mb`
segment of a line is edited (#1083): a pipe, `;`, redirect, `$VAR`, glob or `~`
elsewhere in the line keeps every byte, and a `--repo` with no value is left
alone. Lines with command or parameter substitution, heredocs, herestrings,
process substitution, comments or a backslash line continuation are left exactly
as written. The same rule
names the repo in `plan_interpretation.summary`, in the
`mb spine declare` and `mb onboard status` commands in section summaries and
check details, in the manual step "review .git/hooks/commit-msg, then run
`mb checkpoint --install-hook`", in the repair text of the validation section
(`sections[validation].checks[].report.validation_categories`, a copy), and in what
`mb doctor` itself emits:
`checks[].repair_command` (the checkpoint hook), `checks[migration-drift].findings[].repair_command`
and `update.command` / `update.update_check_command`. It also covers the
backticked commands in `checks[mainbranch-version].detail` (matching
`update.command`) and `checks[legacy-campaigns].detail`, and their repair-plan
section summaries; the explicitly labelled commands in `receipt.skipped_surfaces`;
the shared skill-wiring `fallback_commands` (including the repair section);
and, in `mb doctor repair --plan --json`, the backticked commands in
`sections[validation].checks[].report.legacy_repair.next_steps[]` (`mb validate
--repo <path> --json`; `raw.validation.legacy_repair` keeps the source text).
`onboarding.checklist[].next_action` names the repo for skill linking, starting,
and checkpoint-hook repair in doctor, status and onboarding output. The shared
freshness object's `post_update_commands` names the repo too. For compatibility,
inside-repo output retains its existing spelling, including `--repo .` in the
post-update and onboarding skill-link suggestions; with no known repo, the
post-update instructions still say to run from the business folder. `raw.*`,
`actions[].result` (including the plan) and `applied_actions[].result` are
diagnostic copies and are never rewritten; the
same finding is offered named under `sections[]` and `actions[]`. The workflow inventory's `install_hint` describes no repo and
stays bare. The list is empty when there is nothing for a person to run.

`mb status` names the repo in the same way (#1083), from another folder, for
exactly these fields: `update.command` and `update.update_check_command`;
`command` and `repair_command` anywhere in the report (including
`runtime.skill_wiring`, its `mb_installs` and `shadow_report`,
`ranked_actions[].command` and the connect providers); the `repair` text
anywhere in the report (`drift.items[]`, `readiness.checks[]`,
`runtime.skill_wiring`); `operator_summary`, `top_repair` and
`top_operator_summary` in `validation.validation_categories`; and
`validation.legacy_repair.next_steps[]`; `readiness.next_actions[]` (the only
`next_actions` list `mb status` rewrites: `ads`, `launch`, `update` and Codex
guidance keep theirs); `books.next_command` (`mb books status` and `mb books
doctor` take the repo as a trailing path: `mb books status --json <path>`); and
`measurement.repair_command` when it names a site repo (`mb site check "<site>"
--business-repo .` becomes `--business-repo <path>`; a site path with shell
characters is shell-quoted). A bare `mb site check` is left as written, in both
places it appears: `measurement.repair_command` when the business repo holds its
own `.mainbranch/conversion.json`, and when no site conversion plan is found.
From another folder it checks that folder, so run it from the business repo.
`mb spine show` and `mb spine init`
name it in their `summary` (`mb spine declare --repo <path> --store <provider>`).
Inside the repo these keep their existing spelling, including `--repo .`.
Left as written: `mb_command` (the command that ran), the Codex guidance
(`workflow_inventory`, `fact_commands`, `missing_markers`, `smoke_command`),
placeholder commands such as `mb onboard --path <repo>`, and `raw.*` and
`result` copies. `mb status` and `mb graph` take no `--repo` flag; their
path argument is the supported form.

`mb start --json` (and the human output) rewrites its command fields the same
way, from another folder, once the report is built: the fields above wherever
`mb start` carries them (`update`, `runtime.skill_wiring`, `books.next_command`,
`ranked_actions[].command`, `readiness`) and its own top-level `next_actions[]`.
A launch has already run when this happens, so what ran is never rewritten.

`mb doctor --json` adds a `claude-status-line` entry to `checks[]` only when the
business repo's `CLAUDE.md` still has the pre-#1121 list item "Status field:"
(or the older "Status enum:") followed by "proposed | running | scaling |
killed | graduated | died" (#1122); the same text quoted inside a sentence, or
inside a fenced code block (``` or ~~~), is not flagged. It is a warning (`ok: false`, `severity: warn`; the report's
overall `ok` and the exit code are unchanged) with `path`, `repair` and `detail` text and `suggested_text`,
the replacement conventions. Nothing is written. Repos without the line see no
new entry. `mb doctor repair --plan --json` lists it as a manual action and
section named `claude-status-line` (never applied). `mb doctor repair --plan
--only claude`, `--only codex` and `--all-agents` leave it out: the finding is
about business conventions, not agent wiring, and those scopes keep only
agent-wiring sections. The `status_enum_mismatch`
entry of `validation_categories.by_category` (and the top-level `by_category`
copy in `mb validate --json`) gains `allowed_status`, a map from file type to its
allowed `status:` values, whenever a file's `status:` was rejected, and its
`repair` and `operator_summary` text names those values; every other key is as
before.

An `AGENTS.md` that is a folder is reported as a `codex-agents-md` entry whose
`reason` says it is a folder and whose `manual_step` says to move or rename it
(`mb update` and `mb doctor repair --plan/--apply --only codex`, #1072);
nothing is written and the rest of the run completes. A symlinked `AGENTS.md`,
tracked or not, dangling or not, is listed like a tracked file: `mb update`
without a terminal leaves the link and lists the Codex apply command, with
`AGENTS.md` in `changes` and `consent: no_terminal`; an interactive yes may
replace it, and the prompt lists an untracked or dangling link as `AGENTS.md (replace link)`
and a tracked one as plain `AGENTS.md`.
`mb doctor repair --apply` never performs an operator action, and
`mb doctor repair --only codex` lists only the Codex entries (it leaves the
plugin switch out).

`mb doctor repair --plan` is read-only. Its exit code is 1 when any check in
its scope is an error (`ok: false`), including `--all-agents` when the repo's
Claude wiring is missing, and 0 when it only lists actions or warnings. A
non-zero exit means "something needs repair", not that the plan failed to run;
read the envelope's `summary` and `actions`.

### MoneyPath Proof Quality

`money_path.objects.proof` has two layers:

- Component-level `level`, `status`, `summary`, `paths`, and `missing` describe
  the proof component in the same gated MoneyPath scale as other components.
- Nested `quality` describes factual proof signals that skills, dashboards, and
  scripts can cite without inventing a persuasion score.

`proof.status: structured` means standard proof files, parseable entries, or
frontmatter exist. It does not mean each testimonial has outcome structure.
Nested `proof.quality.structured_entries` means status found structured
testimonial entries or frontmatter inside `testimonials.md`.

When no proof files exist, `quality` contains the baseline empty shape:

```json
{
  "testimonials": {
    "total": 0,
    "generic": 0,
    "specific": 0,
    "permissioned_public": 0,
    "specific_permissioned_public": 0,
    "linked_to_offer": 0,
    "with_before_state": 0,
    "with_outcome": 0,
    "with_timeframe": 0,
    "with_metric": 0,
    "with_mechanism": 0,
    "with_objection": 0
  },
  "typicality": {
    "exists": false,
    "has_average_case": false,
    "has_caveats": false,
    "has_common_failure_context": false,
    "has_time_to_outcome": false
  },
  "claim_links": {
    "linked_offers": [],
    "unsupported_offer_claims": []
  },
  "public_marketing": {
    "ready": false,
    "status": "missing",
    "summary": "No testimonial proof is available for public marketing.",
    "missing": ["testimonials"],
    "next_action": "collect_testimonials"
  }
}
```

When proof files exist and status can inspect them, `quality` also includes:

```json
{
  "structured_entries": false,
  "source_backed": false,
  "instrumentation": {
    "active_push": false,
    "playbook": false,
    "page_readiness": false,
    "outcome_feedback": false
  }
}
```

Generic testimonials are real proof material, but they are not treated as
specific, offer-linked, typicality-aware, or outcome-backed unless the relevant
fields say so. Skills and dashboards should cite facts such as
`permissioned_public`, `specific_permissioned_public`, `linked_to_offer`,
`with_outcome`, `with_timeframe`, `with_metric`, `typicality.exists`, and, when present,
`instrumentation.outcome_feedback`; those are factual signals, not persuasion
scores.

`quality.public_marketing` distinguishes internal proof from proof that can be
used in public campaigns. If testimonials have specific outcomes but none are
permissioned for public use, `public_marketing.status` is `blocked` and
`ready` is `false`; skills should route to permission collection before
drafting proof-backed public ads, pages, or claims.

Dashboard-safe proof categories can be derived from these facts:

- Missing proof: component `status` is `missing`.
- Generic proof: testimonials exist, but `specific` is `0`.
- Specific proof: `testimonials.specific` is greater than `0`.
- Public marketing proof: `public_marketing.ready` is `true`.
- Permission-blocked public proof: `public_marketing.status` is `blocked`.
- Offer-linked proof: `testimonials.linked_to_offer` is greater than `0`.
- Typicality-aware proof: `typicality.exists` is `true`.
- Outcome-backed proof: `instrumentation.outcome_feedback` is present and
  `true`.

Use factual copy such as "Proof exists, but it is generic", "Proof includes
specific outcomes", "Proof is linked to an offer", "Proof has typicality
context", or "Proof is connected to outcome feedback." Avoid claims such as
"good proof", "bad proof", "high-converting proof", "ready to win", or
"persuasive proof."

`mb status --json` also includes a `content_strategy` section for layered
content-strategy health. It reports whether the simple
`core/content-strategy.md` entry point exists, which optional distribution,
channel, account, and person layers exist, whether layers are indexed from the
business strategy, whether account layers resolve their channel and voice
source, and whether fast-changing channel/account layers are stale. Dashboard
and runtime callers should read these normalized facts instead of parsing raw
markdown. Use `overall_state` as summary health and `findings[].code` for
repair cards, such as `content_strategy_unindexed_layer` when a layer exists
but is not indexed from `core/content-strategy.md`.

### `mb site check --json`

`schema: mainbranch.site_readiness` keeps its `state` values (`missing`,
`blocked`, `ready_for_preview`, `ready_for_operator_review`, `ready`) and its
`evidence[]` items of `kind`, `state` and `summary`. Items whose `state` is
`manual` or `missing` are also listed in `manual`.

Google Ads is reported as three separate checks, never one implied from
another:

| `kind` | `status` | Meaning |
|--------|----------|---------|
| `google_ads_plan` | `declared` or `partly_declared` | The repo declares a Google Ads customer and primary conversion plan. Declared only. |
| `google_ads_plan` | `placeholder` | The customer ID is not exactly 10 digits once dashes and spaces are removed (all zeros, all `X`, `TODO`, `TBD`, `N/A`, `none`, `123`, letters), so no customer is declared. `state: manual`, `next` asks for the real 10-digit ID, and the other two items are absent. |
| `google_ads_connection` | `not_checked` | Main Branch has no Google Ads read, so the account is not checked. `next` names the read paths. A connected `google` provider (Analytics, Search Console) is not a Google Ads connection. |
| `google_ads_conversion_evidence` | `no_evidence_recorded` | No evidence that the tag fires (`tag_fired`) or that Google Ads attributes a conversion (`attributed_conversion`). `next` names the step. |

`status`, `next`, `tag_fired` and `attributed_conversion` are additive and
appear only once a Google Ads customer is declared; without one,
`google_ads_plan` keeps its earlier shape and the other two items are absent.
The two new items have `state: manual` and do not change `state` or `ok`.

`mb status --json` carries the same statuses in `measurement.google_ads`, a map
from each Google Ads `kind` to its `status`, for example
`{"google_ads_plan": "declared", "google_ads_connection": "not_checked",
"google_ads_conversion_evidence": "no_evidence_recorded"}`. The items whose
status is `not_checked`, `no_evidence_recorded`, `partly_declared` or
`placeholder` are manual and are counted in `measurement.manual_count`. The key
is additive and absent when no Google Ads customer value is recorded. When the customer ID is a placeholder and `measurement.facts.primary_conversions` is empty, the human `Google Ads:` line also says the conversion plan is missing.

### `mb google ... --out --json`

The summary (`schema: mb.google.out`) carries `out`, the path of the private
file, shown as `~/...` when it is under the home folder, so the summary has no
home folder name and `safe_to_share: true` is accurate. There is no absolute-path field:
an agent opens the file by the path it passed to `--out` (expanding `~` to the
home folder). If the read worked but the file could not be written, stdout
carries the usual failure envelope (`ok: false`, `rule: out_write_failed`,
`exit_code: 1`), the same shape as the read failures, and the process exits 1.
The message names at most the temporary file's name (`.<name>.mb-out.tmp`),
never a full path. If the file was written but that temporary copy could not be
removed, the summary is still `ok: true` (exit 0) and `warnings` holds one
message naming it. A refusal (exit 2, `rule: out_*`) shows an `--out` that
leads under the home folder (absolute or relative, with links followed and
then `.` and `..` collapsed) as `~/...` in `summary` and `errors`, and any
other `--out` as typed (`~name/...` for another user stays `~name/...`, in the
summary's `out` too; `~you/...` for your own user name is `~/...`; a `~/...`
or `~name/...` path that leaves that home, including through a link, and does
not come back into yours, is shown as typed). If a part that contains the home
folder's name would still be printed, only `…/` and the file name are shown (a
home name of four letters or fewer counts only where no letter touches it, so
`samples.json` still shows); a temporary file's name that contains it is shown
as `.….mb-out.tmp`, so neither a refusal nor the summary has the home folder's
name under `safe_to_share: true`. See
[google.md](google.md#--out-keep-a-large-pull-in-a-private-file).

### `mb connect test --json`

The payload is the provider check: `ok`, `provider`, `validation`, `status`,
`recorded` and, when a check was not recorded, `not_recorded_reason`
(`connect_yaml_tracked`, `user_scope_read_only` or `user_scope_write_failed`)
with a sanitized `not_recorded_detail`. Two further keys are additive and absent
otherwise:

- `needs_action` is the check's own result, `true` when it should exit 1. It
  is set when `.mb/connect.yaml` is tracked by git, for a Google check, and in
  the case below.
- `exit_follows_check` is `true` only when the user-scope file could not be
  read or parsed (invalid YAML, not a mapping, not valid UTF-8). The check ran,
  nothing was recorded and `.mb/connect.yaml` was put back, so the stored status
  is stale and the exit code follows `needs_action` (a failed check exits 1; a
  passing check exits 0 with `recorded: false`). Consumers can ignore the key;
  `mb doctor` uses it to say the file is "unreadable or invalid" rather than
  "could not be written".

## First Migrated Surfaces

The v1 envelope is present on:

- `mb status --json`
- `mb start --json`
- `mb checkpoint --json`
- `mb issue draft --json`
- `mb issue open --json`
- `mb doctor --json`
- `mb doctor repair --json`
- `mb onboard --json`
- `mb onboard status --json`
- `mb onboard plan --json`
- `mb fleet refresh --json`
- `mb fleet status --json`
- `mb fleet hubs list --json`

Future commands should use the same shared metadata when they add or revise
`--json` output. Avoid moving existing payloads under a new `data` key unless a
future schema version explicitly deprecates the top-level domain keys.
