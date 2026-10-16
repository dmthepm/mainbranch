"""``mb init`` — non-interactive scaffold for a Main Branch business repo.

Per master decision, v0.1 asks ONE question (business name). Path-config
flexibility is locked; folder names are canonical. Re-running on
an existing repo returns ``status=already-initialized`` (idempotent).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from importlib import resources
from pathlib import Path
from typing import Any

from mb import checkpoint as checkpoint_mod
from mb import codex as codex_mod
from mb import team as team_mod
from mb import validate as validate_mod
from mb.durable import atomic_write_text
from mb.engine import link_skills, write_plugin_wiring
from mb.migrate import LATEST_SCHEMA_VERSION, SCHEMA_MARKER

# The canonical business folders. Keep these stable unless a schema migration lands.
DATA_FOLDERS = [
    "core",
    "core/offers",
    "core/proof",
    "core/brand",
    "core/marketing",
    "core/marketing/channels",
    "core/marketing/accounts",
    "core/team",
    "core/people",
    "core/strategy",
    "core/operations",
    "core/finance",
    "research",
    "decisions",
    "bets",
    "log",
    "pushes",
    "documents",
]

DEFAULT_GITIGNORE = """\
# Main Branch defaults
.env
.env.*
*.journal
*.hledger
*.ledger
*.beancount
.DS_Store
__pycache__/
.mypy_cache/
.ruff_cache/
.pytest_cache/
node_modules/
.venv/
.claude/worktrees/
.mb/private/
.mb/backups/
.mb/connect.yaml
.mb/media/
.mb/onboarding.json
.mb/last-status-seen.json
.mb/issue-drafts/
"""


def _gh_username() -> str:
    """Best-effort gh-cli username probe. Returns empty string on miss."""
    try:
        out = subprocess.run(
            ["gh", "api", "user", "--jq", ".login"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if out.returncode == 0:
            return out.stdout.strip()
    except (FileNotFoundError, subprocess.SubprocessError):
        pass
    return ""


def _owner_display_name(owner_name: str) -> str:
    """Return an explicit owner name without reading local machine identity."""
    explicit_name = owner_name.strip()
    if explicit_name:
        return explicit_name
    env_name = os.environ.get("MB_OWNER_NAME", "").strip()
    if env_name:
        return env_name
    return "Business Owner"


def _read_template(name: str) -> str:
    """Read a bundled template by relative path under ``_data/templates/``."""
    try:
        ref = resources.files("mb").joinpath("_data").joinpath("templates").joinpath(name)
        return ref.read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError, AttributeError):
        # Fallback to repo-relative path during dev (-e install).
        here = Path(__file__).resolve().parent / "_data" / "templates" / name
        if here.exists():
            return here.read_text(encoding="utf-8")
        return ""


# Each file type `mb validate` checks a `status:` for, and the schema it checks
# against. The CLAUDE.md conventions list these values from the same sets, so
# the scaffold cannot teach a status `mb validate` rejects (#1119).
STATUS_CONVENTION_SCHEMAS = (
    ("Bets", "bets"),
    ("Decisions", "decisions"),
    ("Offers", "core/offers"),
    ("Pushes", "pushes"),
    ("Push playbooks", "push-playbooks"),
)

# Every other schema with a `status:` enum, and why the conventions do not list
# it. A new constrained type is in neither set, which fails
# `test_every_status_enum_schema_is_listed_or_excluded` until someone decides.
# Topology status lives in `validate.TOPOLOGY_STATUS`, outside `SCHEMAS[...]["enums"]`.
STATUS_CONVENTION_EXCLUDED = {
    "campaigns": "legacy: `pushes/` replaced it and shares the push status values",
}


def _join_labels(labels: list[str]) -> str:
    return ", ".join(labels[:-1]) + f" and {labels[-1]}" if len(labels) > 1 else labels[0]


def status_conventions() -> str:
    """The CLAUDE.md conventions lines for `status:` values, one set per file type."""
    labels = [label.lower() for label, _ in STATUS_CONVENTION_SCHEMAS]
    lines = [
        f"- {_join_labels(labels).capitalize()} each have their own `status:` values;",
        "  `mb validate` names the allowed values when one is wrong:",
    ]
    for label, schema in STATUS_CONVENTION_SCHEMAS:
        allowed = validate_mod.SCHEMAS[schema]["enums"]["status"]
        lines.append(f"  - {label}: `{' | '.join(sorted(allowed))}`")
    return "\n".join(lines)


def _render(text: str, mapping: dict[str, str]) -> str:
    out = text
    for key, val in mapping.items():
        out = out.replace("{{" + key + "}}", val)
    return out


def _owner_slug(owner_name: str, github_handle: str) -> str:
    handle = team_mod.normalize_github_handle(github_handle)
    if handle:
        return handle
    slug = re.sub(r"[^a-z0-9]+", "-", owner_name.lower()).strip("-")
    return slug or "owner"


def run(
    path: str,
    name: str,
    *,
    owner_name: str = "",
    owner_github: str = "",
    infer_github_identity: bool = True,
) -> dict[str, Any]:
    """Scaffold ``path`` as a Main Branch business repo.

    ``infer_github_identity`` controls whether the machine's gh login may be
    probed when no explicit ``owner_github`` is given. Callers that let the
    operator decline GitHub (onboard) must pass False on decline so a shared
    machine's logged-in account never lands in the scaffold.

    Returns a dict with ``status`` ∈ {ok, already-initialized, error},
    ``path`` (absolute), and ``created`` (list of relative paths created).
    """
    target = Path(path).resolve()
    target.mkdir(parents=True, exist_ok=True)

    if (target / "CLAUDE.md").exists():
        link_result = link_skills(target)
        # Plugin is the primary, worktree-durable, cross-surface rail (works in
        # Claude Desktop + the CLI + IDEs); symlinks remain the fallback. Wire
        # it by default (decision 2026-06-10, Stage 3). Idempotent.
        plugin_wiring = write_plugin_wiring(target)
        already_created = list(link_result["created"])
        if plugin_wiring.get("changed"):
            already_created.append(".claude/settings.json")
        return {
            "status": "already-initialized",
            "path": str(target),
            "created": already_created,
            "skill_link": link_result,
            "plugin_wiring": plugin_wiring,
            "checkpoint_hook": checkpoint_mod.hook_status(target),
        }

    business_name = name.strip() or os.environ.get("MB_BUSINESS_NAME", "").strip()
    if not business_name:
        try:
            business_name = input("business name: ").strip()
        except (EOFError, KeyboardInterrupt):
            return {"status": "error", "path": str(target), "error": "no business name"}
    if not business_name:
        return {"status": "error", "path": str(target), "error": "empty business name"}

    explicit_handle = team_mod.normalize_github_handle(owner_github)
    inferred_handle = (
        team_mod.normalize_github_handle(_gh_username())
        if not explicit_handle and infer_github_identity
        else ""
    )
    gh_handle = explicit_handle or inferred_handle
    gh_user = gh_handle or "your-gh-username"
    owner_display_name = _owner_display_name(owner_name)
    # No real handle → slug from the owner's name, never from the placeholder.
    owner_slug = _owner_slug(owner_display_name, gh_handle)

    created: list[str] = []
    for sub in DATA_FOLDERS:
        d = target / sub
        d.mkdir(parents=True, exist_ok=True)
        # .gitkeep so empty folders survive git
        keep = d / ".gitkeep"
        if not keep.exists():
            atomic_write_text(keep, "")
            created.append(f"{sub}/.gitkeep")

    marker = target / SCHEMA_MARKER
    marker.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(marker, LATEST_SCHEMA_VERSION + "\n")
    created.append(SCHEMA_MARKER)

    mapping = {
        "BUSINESS_NAME": business_name,
        "GH_USERNAME": gh_user,
        "OWNER_NAME": owner_display_name,
        "OWNER_SLUG": owner_slug,
        "STATUS_CONVENTIONS": status_conventions(),
    }

    claude_tmpl = _read_template("CLAUDE.md.tmpl") or _DEFAULT_CLAUDE
    atomic_write_text(target / "CLAUDE.md", _render(claude_tmpl, mapping))
    created.append("CLAUDE.md")

    readme_tmpl = _read_template("README.md.tmpl")
    if readme_tmpl:
        atomic_write_text(target / "README.md", _render(readme_tmpl, mapping))
        created.append("README.md")

    agents_result = codex_mod.write_agents_md(
        target,
        name=business_name,
        gh_username=gh_user,
    )
    for created_path in agents_result.get("changed_paths", []):
        if created_path not in created:
            created.append(str(created_path))
    # #1056: a refused or partial AGENTS.md write is reported the way doctor and
    # update report it: a warning, plus the operator step with the same reason.
    warnings: list[str] = []
    operator_actions: list[dict[str, Any]] = []
    if agents_result.get("refused"):
        agents_action = codex_mod.agents_md_operator_action(
            {"refused": agents_result["refused"], "kept": [], "operations": []},
            repo=target,
        )
        if agents_action is not None:
            warnings.append(str(agents_action["note"]))
            operator_actions.append(agents_action)
    elif agents_result.get("kept"):
        warnings.append(
            "Kept files not proven to be Main Branch's in old repo-local Codex folders: "
            + ", ".join(str(item) for item in agents_result["kept"])
            + ". Move or delete them yourself when you no longer need them."
        )

    vocabulary_tmpl = _read_template("core_vocabulary.md.tmpl")
    if vocabulary_tmpl:
        vocabulary_path = target / "core" / "vocabulary.md"
        vocabulary_path.parent.mkdir(parents=True, exist_ok=True)
        if not vocabulary_path.exists():
            atomic_write_text(vocabulary_path, _render(vocabulary_tmpl, mapping))
            created.append("core/vocabulary.md")

    team_tmpl = _read_template("core_team_member.md.tmpl")
    if team_tmpl:
        owner_path = target / "core" / "team" / f"{owner_slug}.md"
        owner_path.parent.mkdir(parents=True, exist_ok=True)
        if not owner_path.exists():
            atomic_write_text(owner_path, _render(team_tmpl, mapping))
            created.append(f"core/team/{owner_slug}.md")

    codeowners_tmpl = _read_template("CODEOWNERS.tmpl") or f"* @{gh_user}\n"
    github_dir = target / ".github"
    github_dir.mkdir(exist_ok=True)
    codeowners_path = github_dir / "CODEOWNERS"
    if not codeowners_path.exists():
        atomic_write_text(codeowners_path, _render(codeowners_tmpl, mapping))
        created.append(".github/CODEOWNERS")

    gitignore_tmpl = _read_template(".gitignore.tmpl") or DEFAULT_GITIGNORE
    gitignore_path = target / ".gitignore"
    if not gitignore_path.exists():
        atomic_write_text(gitignore_path, _render(gitignore_tmpl, mapping))
        created.append(".gitignore")

    link_result = link_skills(target)
    created.extend(path for path in link_result["created"] if path not in created)

    # Plugin is the primary, worktree-durable, cross-surface rail (Claude
    # Desktop + CLI + IDEs); symlinks are the fallback. Wire by default
    # (decision 2026-06-10, Stage 3). Idempotent; lands in tracked settings.
    plugin_wiring = write_plugin_wiring(target)
    if plugin_wiring.get("changed") and ".claude/settings.json" not in created:
        created.append(".claude/settings.json")

    if shutil.which("git") and not (target / ".git").exists():
        try:
            subprocess.run(
                ["git", "init", "-q", "-b", "main"],
                cwd=target,
                check=True,
                timeout=10,
            )
            created.append(".git/")
        except subprocess.SubprocessError:
            # git init failure is not fatal for scaffolding
            pass

    checkpoint_hook = (
        checkpoint_mod.install_commit_hook(target)
        if (target / ".git").exists()
        else checkpoint_mod.hook_status(target)
    )
    if checkpoint_hook.get("changed"):
        created.append(".git/hooks/commit-msg")

    return {
        "status": "ok",
        "path": str(target),
        "created": created,
        "business_name": business_name,
        "skill_link": link_result,
        "plugin_wiring": plugin_wiring,
        "checkpoint_hook": checkpoint_hook,
        "codex_agents_md": {
            "ok": bool(agents_result.get("ok")),
            "refused": agents_result.get("refused", []),
            "kept": agents_result.get("kept", []),
        },
        "warnings": warnings,
        "operator_actions": operator_actions,
    }


# Embedded fallback CLAUDE.md so ``mb init`` works even without bundled
# templates resolving (early dev installs, source checkouts).
_DEFAULT_CLAUDE = """\
# {{BUSINESS_NAME}}

Your business as files. Claude reads these; you edit them; git remembers them.

## Claude operating contract

Main Branch CLI facts are the source of truth for repo health, setup, runtime
wiring, updates, graph/status signals, provider readiness, and repair paths.
Main Branch installs as a Claude Code plugin
(`claude plugin marketplace add noontide-co/mainbranch`, then enable it). The
plugin is the durable cross-surface rail, and `mb init` / `mb onboard` also
keep the project-local bridge so the normal user command stays `/mb-start`.
Plugin-native skills are namespaced, so `/mainbranch:mb-start` is the direct
plugin smoke/diagnostic command. The normal runtime path is: open this repo in
Claude Code — the Claude Desktop app, or run `claude` in a terminal — then type
`/mb-start` inside Claude Code. From the terminal, `mb start --json` checks the
handoff and `mb start --launch` can open Claude Code when available.
Before giving setup, routing, migration, update, or repair advice, run the
read-only checks that fit the situation from this business repo:

```bash
mb --version
mb status --json --peek
mb start --json
mb doctor repair --plan
```

Use `mb status --json --peek` as the default daily briefing before routing the
operator. It names readiness, drift, onboarding progress, update state, GitHub
activity, provider signals, recent work, content strategy health, MoneyPath,
ranked actions, bets, pushes, and checkpoint state.
Do not replace those facts with ad hoc shell inspection unless `mb` says a section is unavailable.

Read-only commands can be run without asking first. Commands that write files,
refresh local runtime wiring, move personal skill shadows, update packages,
migrate business files, create checkpoints, publish, spend money, email, or
mutate provider accounts require explicit operator approval before applying.
Plan first, then apply only after approval:

```bash
mb doctor repair --plan
mb skill repair --repo .
mb skill link --repo .          # writes project-local Claude skill wiring
mb skill repair --repo . --apply
mb doctor repair --apply
mb update
```

<!-- mainbranch:entry-rules:begin -->
## Trials and readouts

For a current experiment with a measurable target and a review or cut point,
check existing bets first and reuse the matching bet. If none covers the work,
offer to open one with `mb-bet` before doing the work.
For an observation or readout, such as "the numbers show" or "this week's read",
offer a short `research/` readout with summarized numbers, source, timeframe,
caveat, and next question. Do not file the readout in `log/`.
If the observation changes the plan, also offer a `decisions/` record. Link the
readout and decision both ways with `linked_decisions` and `linked_research`,
and link the bet or push that changes. For a status-only question, answer it
without proposing records. Ask for approval before any write. Never copy raw
provider rows, account IDs, or exported tables into the repo. See `/mb-start`,
`/mb-bet`, and `/mb-think` for the full routes.
<!-- mainbranch:entry-rules:end -->

## First-run setup intent

When the operator pastes a setup guide, bootstrap prompt, or business/folder
description into an empty or uninitialized folder, treat it as setup intent,
not as a document to save. Do not ask what file format to save the prompt in. First
check `mb --version`. If `mb` is missing, stop and give the exact install step:
`pipx install mainbranch`. If `mb` is available, inspect the setup path with
`mb onboard --help`, then explain which folder will become the business brain
and ask before running any command that writes files.

If the operator asks for GitHub backup, sync, collaboration, or
`mb onboard --github <owner/repo> --push`, check GitHub CLI before any setup write:
`gh auth status` and `gh api user --jq .login`. Confirm the signed-in account
matches the operator's expected account. GitHub is strongly recommended because
it gives Main Branch a free cloud backup, shared history, task/proposal layer,
and connector-friendly copy of the business brain. Main Branch can start
locally without GitHub; GitHub is needed for sync, collaboration, and the
GitHub-backed onboarding path.

After setup, run `mb status --json --peek` and `mb start --json`. Summarize the
outcome in business language first: folder created, business brain ready,
baseline saved, GitHub backup connected when requested, checkpoint state, and
next safe action. Put commands and git/GitHub details second.

If `/mb-start` is not discoverable or Claude Code reports `Unknown command:
/mb-start`, do not improvise from memory. The most common cause is that the
Main Branch plugin is not installed or enabled — install it with
`claude plugin marketplace add noontide-co/mainbranch` and enable it (this
works in the Claude Desktop app and the terminal). If you need to prove the
plugin itself loaded, use the namespaced `/mainbranch:mb-start` command. If you
are in a cloud/web session, plugins are unavailable there — use the Claude
Desktop app or the `claude` CLI. From this business repo, check `mb --version`,
run `mb start --json` and `mb status --json --peek`, inspect repair options
with `mb doctor repair --plan`, then ask before running any write/apply command
such as `mb skill link --repo .`, `mb skill repair --repo . --apply`,
`mb doctor repair --apply`, or `mb update`. After repairing skill wiring, tell
the operator: "I repaired missing Main Branch start wiring in this business
folder; restart Claude Code from this repo and try `/mb-start` again."

If `mb status --json --peek` reports `update.severity` as `recommended` or
`required`, make that the only recommendation before business routing. Name the
installed/latest versions when present. Use `update.release_notes_url` or
`update.update_check_command` when present to answer what changed. If release
context is unavailable, say the update brings recent routing, repair, and skill
improvements, then ask whether to update now. Do not show ranked actions until
after the operator updates or explicitly chooses to continue. For required
updates, route to the cited `mb update` command before business work. After an
approved update, rerun the status briefing.

Do the technical work in technical commands, then translate the result back into
business-owner language. Speak first in terms of bets, goals, offers, pushes,
playbooks, outcomes, decisions, next actions, and saved checkpoints. Treat git,
branches, pull requests, provider refs, and local wiring as the hidden memory
layer unless the operator asks for the plumbing.

Default translations for normal owner answers:
- `git is clean`, `repo is clean`, `working tree clean`, or `working tree: clean`
  -> nothing unsaved locally;
- `branch main`, `branch: main`, or `current branch: main` -> current business
  folder or workspace;
- `No GitHub origin remote`, `No origin remote`, or `Connected GitHub backup:
  none surfaced` -> no connected GitHub backup or shared task source;
- `PR/issue facts` or `PR and issue facts` -> GitHub task and proposal context.
Use raw git/GitHub terms only in exact commands or a separate "Technical
detail:" line after the owner meaning.

## Folders

- `core/` — the business brain: offer, audience, voice, soul, proof, brand,
  strategy, operations, finance
- `core/offers/` — per-offer specifics when this is a multi-offer repo
- `core/proof/` — testimonials, typicality, and reusable proof
- `core/brand/` — visual identity, voice guardrails, and brand systems
- `core/marketing/` — optional content distribution, channel, and account strategy
- `core/team/` — public-safe team member files for names, roles, GitHub
  handles, and ownership context
- `core/people/` — optional founder/person voice source material, beliefs, stories, and proof
- `core/strategy/` — strategic context that should remain evergreen
- `core/operations/` — operating context such as fulfillment, classroom, funnel, or membership notes
- `core/finance/` — approved finance summaries, policies, and safe provider refs
- `research/` — dated notes from when you went looking
- `decisions/` — dated choices, with rationale
- `bets/` — operating bets with appetite, metric, target, and outcome
- `log/` — running activity log
- `pushes/` — coordinated pushes (launches, drops, challenges, promos, etc.)
- `documents/` — anything that doesn't belong above

If your repo was created before the push primitive decision, you may also have
a legacy `campaigns/` folder. `mb` continues to read it; new coordinated work
should land in `pushes/`. Run `mb doctor` to see whether your repo is on the
canonical shape and `mb migrate campaigns --plan` to preview a safe move.

## Hub and child repos

This repo is the hub for business strategy, bets, decisions, offers, pushes,
logs, approved summaries, and routing. Child repos hold role-specific execution
work when a site, offer, product, client, finance, legal, ops, integration
sidecar, experiment, or archive surface needs its own lifecycle or access
boundary.

Use the hub for strategy, durable business truth, and checkpoint context. Switch
to a child repo when editing that child repo's code, site, product files, client
deliverables, sidecar code, or ops files. When you are in a child repo, read
`.mainbranch/repo.json` if it exists; existing site repos may still use
`.mainbranch/source.json` as a compatibility link. Return to this hub for
business routing, decisions, and cross-repo topology questions.

The hub topology registry, when present, lives at
`core/operations/repo-topology.md`. It should use safe handles such as display
names, roles, lifecycle, GitHub owner/repo, linked offers/pushes/bets/decisions,
and private-boundary notes. Do not commit local absolute paths, secrets, raw
provider caches, raw finance/legal/customer data, or permission claims in hub
or child repo descriptors.

## Business primitive routing

When deciding where an idea belongs, use business meaning first:

- Offer: what the business sells or may sell repeatedly.
- Bet: a time-boxed wager with appetite, target, evidence, and verdict.
- Push: coordinated work that ships something to an audience.
- Reusable playbook: an engine recipe for running a repeatable operating
  workflow. Treat its defaults as attributed method, not universal law.
- Push playbook: this push's approval, provider-boundary, check, manual-step,
  evidence, fork, and outcome record.
- Proof: evidence that a claim is true.
- Decision: rationale for changing durable truth.

Reusable playbooks can encode official platform rules, Main Branch guidance,
and author opinion. Push playbooks record which defaults were used or forked
for this run and why. See `docs/playbooks.md` in the Main Branch engine for
the full model.

In a single-offer repo, `core/offer.md` is the durable offer truth. In a
multi-offer repo, `core/offer.md` is the portfolio thesis and
`core/offers/<slug>/offer.md` holds per-offer truth. Company-wide proof belongs
in `core/proof/`; offer-specific proof belongs in `core/offers/<slug>/proof/`.
Use standard proof files such as `testimonials.md`, `typicality.md`, and
`angles/` inside those proof folders. Make proof status-detectable with
structured testimonial fields such as `public`, `permissioned_public`,
`approved_for_public`, `safe_to_share`, `offer`, `linked_offer`, and
`linked_offers`. Use `permissioned_public: false` for specific internal proof
that is not approved for public marketing yet. Use `typicality.md` for
average-case outcomes, caveats, common failure context, and time-to-outcome
when available.
Content strategy starts at `core/content-strategy.md`. Keep it as the simple
business-level strategy and index: what the business wants to be known for, who
the content is for, pillars, content jobs, non-publishing rules, and links to
the rest of the model. When the operator needs more detail, use
`core/marketing/distribution-strategy.md`,
`core/marketing/channels/<channel>.md`,
`core/marketing/accounts/<platform>-<account>.md`, and
`core/people/<person>.md`. Weekly content planning should read those files by
reference, then write concrete execution to `pushes/` and results to `log/`.
`mb validate` checks their frontmatter shape and relationships;
`mb status --json --peek` exposes normalized `content_strategy` health for
agents and future read-only dashboard views.
`mb status --json --peek` also emits `money_path`, a read-only map of whether
customer progress, offer, proof, CTA, channel, push, playbook, page readiness,
and outcome feedback are legible and connected. Use MoneyPath from
`mb status --json --peek` for routing when the path needs to be legible,
supported, connected, and instrumented. Treat proof-quality fields as factual
signals for badges or gaps, not persuasion scores; do not claim proof or offers
are good, bad, high-converting, or likely to convert. If
`money_path.objects.proof.quality.public_marketing.status` is `blocked`,
collect permission before using that proof in public ads, pages, or claims.
A live idea can be both a bet and an offer candidate: open the bet first, then
create or update the offer only when the operator wants durable sellable truth.

Team context lives in `core/team/<slug>.md`. Use it for public-safe business
identity: name, preferred name, role, relationship, owned areas, and GitHub
handles without `@`. Do not put payroll, legal ownership percentages, home
contact details, private customer/member data, or credentials there. Keep
external collaborators in the same folder with
`relationship: external_collaborator` only when they are useful business
context. Unknown GitHub handles should stay as handles until the operator
chooses to add a team file.

Do not rename, delete, merge, split, or move offer folders until an accepted
decision, approved migration plan, or explicit operator instruction exists.
Paused, dead, superseded, or graduated offers should remain inspectable until
the operator decides what happens to them.

## Optional: operator vocabulary

`core/vocabulary.md` is an optional file where the business names what it
calls coordinated pushes. A coach might call them *drops*; a creator might
call them *launches*; a community might call them *challenges*. The file
shape:

    ---
    type: vocabulary
    status: active
    terms:
      push:
        singular: drop
        plural: drops
      statuses:
        active: live
        completed: shipped
    ---

    Optional prose explanation goes here.

Vocabulary changes how skills and `mb status` speak in conversation. It does
not rename folders, frontmatter types, link fields, JSON keys, validator
rules, or commands. Engine internals stay canonical.

## Conventions

- Decisions, research, bets, and offers carry a small block of metadata at the top
  (frontmatter). Run `mb validate` to check it.
{{STATUS_CONVENTIONS}}
- One owner per file (CODEOWNERS pattern).

## Connected accounts

Treat this repo as the boundary for connected business tools. When you switch
business repos, switch the accounts, tokens, and MCP servers that can act on
that business.

Keep non-secret IDs in repo files when they help agents choose the right
account: Stripe account/product/price IDs in `core/offers/<offer>/stripe.md`,
Google Ads customer and campaign IDs (provider's term for their object) in
`pushes/<push>/push.md` `provider_refs:`, ad pixel IDs beside the site or
push files they belong to, and MCP server names/scopes in local setup notes.

Never commit API keys, OAuth refresh tokens, service-account JSON, webhook
secrets, MCP tokens, or bearer tokens. Put secrets in a runtime local config,
OS keychain, 1Password, `.env`, or `.claude/settings.local.json`; those files
should stay gitignored. If a tool can spend money, publish, email, or mutate a
customer account, verify it is tethered to this repo before using it.

## Helpful commands

```
mb doctor                  # see if anything is off in this repo
mb validate                # check the metadata on your files
mb graph --open            # see what links to what
```

Visit https://mainbranch.io for the full system docs.

Owner: @{{GH_USERNAME}}
"""
