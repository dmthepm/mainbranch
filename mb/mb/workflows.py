"""Shared workflow source validation and snapshot rendering."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

VALID_LOOP_SLUGS = {"sense", "decide", "ship", "reflect"}
REQUIRED_FRONTMATTER_FIELDS = {
    "name",
    "title",
    "description",
    "loops",
    "runtime_support",
    "runtime_surfaces",
    "required_mb_commands",
    "json_facts",
    "approval_gates",
    "public_private_boundaries",
    "writes_business_files",
    "provider_mutation",
    "publishing_or_spend",
}
REQUIRED_SECTIONS = {
    "Intent And Triggers",
    "Required Mb Commands",
    "Required JSON Fact Paths",
    "Routing Rules",
    "Read Boundaries",
    "Write Boundaries",
    "Approval Gates",
    "Handoff Format",
    "Validation Commands",
    "Runtime-Specific Notes",
}
REQUIRED_RUNTIME_SUPPORT = {
    "claude_code": "supported_shell",
    "codex_cli": "owner_loop_shell",
}
ALLOWED_RUNTIME_SUPPORT_VALUES = {
    "claude_code": {"supported_shell"},
    "codex_cli": {"owner_loop_shell", "read_only_planning"},
}
MINIMUM_MB_COMMANDS = {
    "mb status --json --peek",
    "mb start --json",
    "mb doctor repair --plan",
}
MINIMUM_JSON_FACTS = {
    "money_path",
    "money_path.objects.proof.quality",
    "content_strategy",
    "ranked_actions",
    "update",
    "readiness",
    "drift.items",
}
MINIMUM_APPROVAL_GATES = {
    "file_writes",
    "checkpoint",
    "provider_mutation",
    "publishing_or_spend",
    "customer_contact",
    "private_data",
}
MINIMUM_PUBLIC_PRIVATE_BOUNDARIES = {
    "no_secrets",
    "no_raw_provider_exports",
    "no_customer_member_data",
    "no_private_runtime_settings",
}
REQUIRED_SHELL_PHRASES_BY_WORKFLOW: dict[str, dict[str, str]] = {
    "mb-think": {
        "research-depth ladder": "research depth recommendation",
        "parallel research file pattern": "parallel research files",
        "decision writing": "decision",
        "codification": "codify",
        "stale-source cleanup": "stale source",
        "public/private boundary": "public/private",
        "approval gates": "approval",
        "checkpoint approval": "checkpoint",
        "Codex runtime-entrypoint boundary": (
            "Do not tell Codex users to run Claude Code entrypoints."
        ),
    },
    "mb-end": {
        "status scan": "status scan",
        "checkpoint plan": "checkpoint plan",
        "session summary": "session summary",
        "final thought capture": "final thought",
        "crystallize": "crystallize",
        "approval-gated save": "approval-gated save",
        "save states": "drafted",
        "warm close": "warm close",
    },
    "mb-start-status": {
        "ranked next route": "ranked_actions",
        "runtime mismatch gate": "runtime mismatch",
        "status marker approval": "status marker",
        "owner-facing state": "business language first",
        "bet trigger facts": "brain.bets",
        "bet lifecycle routing": "double-down",
    },
    "mb-setup": {
        "setup intent": "setup intent",
        "target folder confirmation": "target folder",
        "approval-gated writes": "ask before running a write command",
        "owner outcome": "owner outcome",
    },
    "mb-maintenance-repair": {
        "repair plan": "repair plan",
        "package update approval": "package updates are explicit operator actions",
        "safe-to-apply state": "safe-to-apply",
        "post-repair status": "rerun `mb status --json --peek`",
    },
    "mb-bet": {
        "bet lifecycle modes": "new, update, close, list, and narrate",
        "bet file contract": "bets/YYYY-MM-DD-slug.md",
        "bet not offer or push": "Bet is a time-boxed wager",
        "strict bet contract": "strict contract",
        "reverse links": "linked_bets",
        "cross-ref validation": "mb validate --cross-refs",
        "exposure privacy": "aggregate exposure",
        "public narration": "public-safe narration",
        "checkpoint boundary": "checkpoint plan",
        "Codex support boundary": "read-only planning",
    },
    "mb-organic": {
        "organic modes": "plan, video, carousel, static, sales-video-repurpose, or review",
        "mining handoff": "route to `mb-think`",
        "content strategy paths": "content_strategy.overall_state",
        "artifact routing": "pushes/<YYYY-MM-DD-slug>/organic-batch-001.md",
        "proof quality boundary": "money_path.objects.proof.quality",
        "source privacy boundary": "source/privacy",
        "publishing boundary": "Do not publish",
        "account mutation boundary": "mutate provider accounts",
        "Codex support boundary": "read-only planning",
    },
    "mb-ads": {
        "ads modes": "account-context modes",
        "research handoff": "route to `mb-think`",
        "site readiness handoff": "route to `mb-site`",
        "proof quality boundary": "money_path.objects.proof.quality",
        "artifact routing": "pushes/<YYYY-MM-DD-slug>/ads-batch-001.md",
        "Google Ads playbook": "google-ads-search-launch",
        "provider boundary": "provider mutation",
        "upload boundary": "upload assets",
        "spend boundary": "spend",
        "GTM boundary": "GTM",
        "Codex support boundary": "read-only planning",
    },
    "mb-site": {
        "site modes": "plan, brief, build, preview, check, publish, iterate, graduate, or recover",
        "site shapes": "lander, minisite, website",
        "sales-video surfaces": "sales-video surface",
        "site readiness facts": "facts.expected_events",
        "readiness states": "ready_for_operator_review",
        "site check command": "mb site check",
        "repo descriptor": ".mainbranch/repo.json",
        "legacy source descriptor": ".mainbranch/source.json",
        "Cloudflare gate": "Cloudflare Pages",
        "provider boundary": "provider mutation",
        "DNS boundary": "DNS",
        "deploy boundary": "deploy",
        "Codex support boundary": "read-only planning",
    },
}
CODEX_FORBIDDEN_PHRASES_BY_WORKFLOW: dict[str, tuple[str, ...]] = {
    "mb-think": (
        "Run `/mb-think`",
        "Claude Code skills work in Codex",
        "Claude Code slash commands work inside Codex",
        "Claude slash commands",
        "slash-command parity",
    ),
    "mb-end": (
        "Run `/mb-end`",
        "Claude Code skills work in Codex",
        "Claude Code slash commands work inside Codex",
        "Claude slash commands",
        "slash-command parity",
        "skip crystallize",
    ),
    "mb-start-status": (
        "Run `/mb-start`",
        "Run `/mb-status`",
        "Claude Code skills work in Codex",
        "Claude Code slash commands work inside Codex",
        "Claude slash commands",
        "slash-command parity",
    ),
    "mb-setup": (
        "Run `/mb-setup`",
        "Claude Code skills work in Codex",
        "Claude Code slash commands work inside Codex",
        "Claude slash commands",
        "slash-command parity",
    ),
    "mb-maintenance-repair": (
        "Run `/mb-update`",
        "Run `/mb-doctor`",
        "Claude Code skills work in Codex",
        "Claude Code slash commands work inside Codex",
        "Claude slash commands",
        "slash-command parity",
    ),
    "mb-bet": (
        "Run `/mb-bet`",
        "Claude Code skills work in Codex",
        "Claude Code slash commands work inside Codex",
        "Claude slash commands",
        "slash-command parity",
        "Codex can create bets",
        "Codex can close bets",
    ),
    "mb-organic": (
        "Run `/mb-organic`",
        "Claude Code skills work in Codex",
        "Claude Code slash commands work inside Codex",
        "Claude slash commands",
        "slash-command parity",
        "Codex can publish",
        "Codex can schedule",
        "Codex can mutate provider accounts",
        "Codex can contact customers",
    ),
    "mb-ads": (
        "Run `/mb-ads`",
        "Claude Code skills work in Codex",
        "Claude Code slash commands work inside Codex",
        "Claude slash commands",
        "slash-command parity",
        "Codex can publish ads",
        "Codex can upload assets",
        "Codex can mutate ad accounts",
        "Codex can change budgets",
        "Codex can start spend",
        "Codex can contact customers",
    ),
    "mb-site": (
        "Run `/mb-site`",
        "Claude Code skills work in Codex",
        "Claude Code slash commands work inside Codex",
        "Claude slash commands",
        "slash-command parity",
        "Codex can build sites",
        "Codex can deploy",
        "Codex can publish",
        "Codex can mutate provider accounts",
        "Codex can change DNS",
        "Codex can contact customers",
    ),
}
PUBLIC_PRIVATE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("local user path", re.compile(r"/Users/[^\s`)]+")),
    ("private maintainer handle", re.compile(r"devonmeadows", re.I)),
    ("GitHub token", re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}")),
    ("AWS access key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("Stripe key", re.compile(r"sk_(?:live|test)_[A-Za-z0-9]{12,}")),
    (
        "inline secret assignment",
        re.compile(r"(?i)\b(?:api[_-]?key|password|secret|token)\s*[:=]\s*\S+"),
    ),
)


@dataclass(frozen=True)
class WorkflowSource:
    """Parsed workflow source file."""

    path: Path
    frontmatter: dict[str, Any]
    body: str

    @property
    def name(self) -> str:
        return str(self.frontmatter["name"])

    @property
    def title(self) -> str:
        return str(self.frontmatter["title"])

    @property
    def required_mb_commands(self) -> list[str]:
        return [str(item) for item in self.frontmatter["required_mb_commands"]]

    @property
    def json_facts(self) -> list[str]:
        return [str(item) for item in self.frontmatter["json_facts"]]

    @property
    def approval_gates(self) -> list[str]:
        return [str(item) for item in self.frontmatter["approval_gates"]]

    @property
    def public_private_boundaries(self) -> list[str]:
        return [str(item) for item in self.frontmatter["public_private_boundaries"]]

    @property
    def runtime_support(self) -> dict[str, str]:
        raw = self.frontmatter["runtime_support"]
        if not isinstance(raw, dict):
            return {}
        return {str(key): str(value) for key, value in raw.items()}


class WorkflowValidationError(ValueError):
    """Raised when a workflow source cannot be rendered safely."""


def _split_frontmatter(text: str) -> tuple[dict[str, Any] | None, str, str | None]:
    if not text.startswith("---\n"):
        return None, text, "missing YAML frontmatter"
    end = text.find("\n---", 4)
    if end == -1:
        return None, text, "unterminated YAML frontmatter"
    try:
        parsed = yaml.safe_load(text[4:end]) or {}
    except yaml.YAMLError as exc:
        return None, text, f"frontmatter does not parse as YAML: {exc}"
    if not isinstance(parsed, dict):
        return None, text, "frontmatter must be a mapping"
    return parsed, text[end + len("\n---") :].lstrip("\n"), None


def _coerce_string_list(value: Any) -> list[str] | None:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        return None
    return [str(item) for item in value]


def _section_titles(body: str) -> set[str]:
    return {
        match.group("title").strip()
        for match in re.finditer(r"^## (?P<title>.+?)\s*$", body, flags=re.MULTILINE)
    }


def read_workflow(path: Path) -> WorkflowSource:
    """Read a workflow source without validating every contract rule."""

    text = path.read_text(encoding="utf-8")
    frontmatter, body, error = _split_frontmatter(text)
    if error is not None or frontmatter is None:
        raise WorkflowValidationError(error or "invalid workflow frontmatter")
    return WorkflowSource(path=path, frontmatter=frontmatter, body=body)


def validate_workflow(path: Path) -> list[str]:
    """Return workflow source validation errors."""

    errors: list[str] = []
    if not path.is_file():
        return [f"{path}: workflow source does not exist"]

    text = path.read_text(encoding="utf-8")
    frontmatter, body, frontmatter_error = _split_frontmatter(text)
    if frontmatter_error is not None or frontmatter is None:
        return [frontmatter_error or "invalid workflow frontmatter"]

    for field in sorted(REQUIRED_FRONTMATTER_FIELDS):
        if field not in frontmatter:
            errors.append(f"missing frontmatter field: {field}")

    loops = _coerce_string_list(frontmatter.get("loops"))
    if loops is None:
        errors.append("frontmatter field loops must be a list of strings")
    else:
        invalid_loops = sorted(set(loops) - VALID_LOOP_SLUGS)
        if invalid_loops:
            errors.append(f"frontmatter field loops has invalid slugs: {invalid_loops}")
        if len(set(loops)) != len(loops):
            errors.append("frontmatter field loops must not contain duplicate slugs")

    runtime_support = frontmatter.get("runtime_support")
    if not isinstance(runtime_support, dict):
        errors.append("frontmatter field runtime_support must be a mapping")
    else:
        for runtime, expected in REQUIRED_RUNTIME_SUPPORT.items():
            actual = runtime_support.get(runtime)
            allowed = ALLOWED_RUNTIME_SUPPORT_VALUES.get(runtime, {expected})
            if actual not in allowed:
                if len(allowed) == 1:
                    errors.append(f"runtime_support.{runtime} must be {expected!r}, got {actual!r}")
                else:
                    errors.append(
                        f"runtime_support.{runtime} must be one of "
                        f"{sorted(allowed)!r}, got {actual!r}"
                    )

    runtime_surfaces = frontmatter.get("runtime_surfaces")
    if not isinstance(runtime_surfaces, dict):
        errors.append("frontmatter field runtime_surfaces must be a mapping")
    else:
        for runtime in REQUIRED_RUNTIME_SUPPORT:
            actual = runtime_surfaces.get(runtime)
            if not isinstance(actual, str) or not actual.strip():
                errors.append(f"runtime_surfaces.{runtime} must name the checked shell path")

    commands = _coerce_string_list(frontmatter.get("required_mb_commands"))
    if commands is None:
        errors.append("frontmatter field required_mb_commands must be a list of strings")
    else:
        missing_commands = sorted(MINIMUM_MB_COMMANDS - set(commands))
        if missing_commands:
            errors.append(f"required_mb_commands missing minimum commands: {missing_commands}")

    facts = _coerce_string_list(frontmatter.get("json_facts"))
    if facts is None:
        errors.append("frontmatter field json_facts must be a list of strings")
    else:
        missing_facts = sorted(MINIMUM_JSON_FACTS - set(facts))
        if missing_facts:
            errors.append(f"json_facts missing minimum paths: {missing_facts}")

    approval_gates = _coerce_string_list(frontmatter.get("approval_gates"))
    if approval_gates is None:
        errors.append("frontmatter field approval_gates must be a list of strings")
    else:
        missing_gates = sorted(MINIMUM_APPROVAL_GATES - set(approval_gates))
        if missing_gates:
            errors.append(f"approval_gates missing minimum gates: {missing_gates}")

    boundaries = _coerce_string_list(frontmatter.get("public_private_boundaries"))
    if boundaries is None:
        errors.append("frontmatter field public_private_boundaries must be a list of strings")
    else:
        missing_boundaries = sorted(MINIMUM_PUBLIC_PRIVATE_BOUNDARIES - set(boundaries))
        if missing_boundaries:
            errors.append(
                f"public_private_boundaries missing minimum boundaries: {missing_boundaries}"
            )

    for field in ("writes_business_files", "provider_mutation", "publishing_or_spend"):
        if field in frontmatter and not isinstance(frontmatter[field], bool):
            errors.append(f"frontmatter field {field} must be true or false")

    missing_sections = sorted(REQUIRED_SECTIONS - _section_titles(body))
    for section in missing_sections:
        errors.append(f"missing workflow section: {section}")

    errors.extend(public_private_boundary_errors(text))
    return errors


def load_workflow(path: Path) -> WorkflowSource:
    """Validate and read a workflow source."""

    errors = validate_workflow(path)
    if errors:
        raise WorkflowValidationError("; ".join(errors))
    return read_workflow(path)


def shell_drift_errors(workflow: WorkflowSource, shell_text: str) -> list[str]:
    """Return missing required commands or JSON facts for a rendered shell."""

    errors: list[str] = []
    for command in workflow.required_mb_commands:
        if not _has_exact_bullet_item(shell_text, command):
            errors.append(f"shell missing required mb command: {command}")
    for fact in workflow.json_facts:
        if not _has_exact_bullet_item(shell_text, fact):
            errors.append(f"shell missing required JSON fact path: {fact}")
    for gate in workflow.approval_gates:
        if f"`{gate}`" not in shell_text:
            errors.append(f"shell missing required approval gate: {gate}")
    for boundary in workflow.public_private_boundaries:
        if f"`{boundary}`" not in shell_text:
            errors.append(f"shell missing required public/private boundary: {boundary}")
    for label, phrase in REQUIRED_SHELL_PHRASES_BY_WORKFLOW.get(workflow.name, {}).items():
        if phrase.lower() not in shell_text.lower():
            errors.append(f"shell missing required workflow rule: {label}")
    return errors


def codex_shell_policy_errors(workflow: WorkflowSource, shell_text: str) -> list[str]:
    """Return Codex guidance phrases that would overclaim support."""

    errors: list[str] = []
    for phrase in CODEX_FORBIDDEN_PHRASES_BY_WORKFLOW.get(workflow.name, ()):
        if phrase.lower() in shell_text.lower():
            errors.append(f"Codex shell contains forbidden support phrase: {phrase}")
    return errors


def _has_exact_bullet_item(text: str, item: str) -> bool:
    expected = f"- `{item}`"
    return any(line.strip() == expected for line in text.splitlines())


def public_private_boundary_errors(text: str) -> list[str]:
    """Flag obvious private paths, tokens, or inline secret assignments."""

    errors: list[str] = []
    for label, pattern in PUBLIC_PRIVATE_PATTERNS:
        if pattern.search(text):
            errors.append(f"public/private boundary violation: {label}")
    return errors


def _bullet_list(items: list[str]) -> str:
    return "\n".join(f"- `{item}`" for item in items)


def _inline_code_list(items: list[str]) -> str:
    return ", ".join(f"`{item}`" for item in items)


def _display_path(path: Path) -> str:
    parts = path.parts
    if "workflows" in parts:
        index = parts.index("workflows")
        return Path(*parts[index:]).as_posix()
    return path.as_posix()


_PUSH_LINK_STEP = """When creating or first writing a push, ask once:
"Which bet does this push serve, and which existing decision or research supports it?"
Offer active bets and recent decisions and research by name from status facts or files already read.
Accept "none yet" and continue. For a deliberate one-off with no bet, write
`linked_bets: []` and a one-line `no_bet_reason`. On an approved write, put the
chosen repo-relative paths in `linked_bets`, `linked_decisions`, and
`linked_research` on the push; add its path to `linked_pushes` on each named
bet, decision, and research file. Leave unanswered links empty; do not invent
a reason. Mirror typed links in `## Related links` as relative Markdown links.
Use docs/business-connections.md; never infer links from body-only references."""


def render_claude_shell(workflow: WorkflowSource) -> str:
    """Render a Claude Code shell snapshot for a workflow source."""

    if workflow.name == "mb-think":
        return _render_think_claude_shell(workflow)
    if workflow.name == "mb-end":
        return _render_end_claude_shell(workflow)
    if workflow.name == "mb-bet":
        return _render_bet_claude_shell(workflow)
    if workflow.name == "mb-organic":
        return _render_organic_claude_shell(workflow)
    if workflow.name == "mb-ads":
        return _render_ads_claude_shell(workflow)
    if workflow.name == "mb-site":
        return _render_site_claude_shell(workflow)
    if workflow.name in {"mb-start-status", "mb-setup", "mb-maintenance-repair"}:
        return _render_daily_claude_shell(workflow)
    return _render_start_money_path_claude_shell(workflow)


def _daily_claude_use_text(workflow: WorkflowSource) -> str:
    if workflow.name == "mb-start-status":
        return (
            "Use from `/mb-start` or `/mb-status` when the operator starts the day, "
            "returns to a repo, asks what changed, or asks what to do next. Preserve "
            "fact-first routing, update/repair gates, one clear next route, and "
            "business language first."
        )
    if workflow.name == "mb-setup":
        return (
            "Use from `/mb-setup` when the operator wants to create or connect a "
            "business repo. Treat pasted setup prompts as setup intent, confirm the "
            "target folder, and ask before running a write command."
        )
    return (
        "Use from `/mb-update`, `/mb-start` repair routing, or doctor guidance when "
        "the operator needs update, repair, migration, or runtime wiring help. Explain "
        "the repair plan in business language first and ask before apply commands."
    )


def _daily_codex_route_text(workflow: WorkflowSource) -> str:
    if workflow.name == "mb-start-status":
        return (
            "1. Use the business repo `AGENTS.md` bootstrap posture: read facts first, "
            "keep writes approval-gated, and translate git/provider details into business "
            "language.\n"
            "2. Run hard gates before routing: required updates, runtime mismatch, repair "
            "blockers, readiness blockers, private-data boundaries, unsafe provider "
            "operations, and destructive-operation requests.\n"
            "3. Use `ranked_actions`, `since_last_check`, `git_activity`, `journal`, `money_path`, "
            "`content_strategy`, `validation.file_contracts`, `onboarding`, "
            "`readiness`, `update`, `drift.items`, and `brain.bets` as cited facts. "
            "Recent activity and `since_last_check` answer what changed without a "
            "separate latest or changelog index.\n"
            "4. Route offer-shape gaps from `validation.file_contracts` to `mb-think` "
            "after hard gates, and ask before durable writes.\n"
            "5. Use due-soon and overdue bet deadlines, missing-exit criteria, triggered "
            "failure signals, and triggered double-down signals for update, kill, close, "
            "double-down, or narrate routing.\n"
            "6. Present one clear business route and the signal behind it. Mutate the "
            "status marker only when the operator explicitly approves recording the "
            "daily check-in.\n"
            "7. Ask before business-file writes, checkpoints, repairs, updates, migrations, "
            "provider mutation, publishing, spend, customer contact, destructive operations, "
            "or public issue/proposal submission."
        )
    if workflow.name == "mb-setup":
        return (
            "1. Treat setup prompts as setup intent and onboarding intent, not as documents "
            "to save.\n"
            "2. Confirm the target folder and inspect setup capability before writes.\n"
            "3. If `mb` is missing, stop and give the install command. If GitHub backup "
            "is requested, check GitHub CLI auth before any GitHub write.\n"
            "4. Ask before running a write command such as onboarding, repo creation, "
            "file scaffolding, GitHub remote/push, repair apply, migration apply, or "
            "checkpoint save.\n"
            "5. After approved setup, rerun status/start facts and report the owner "
            "outcome before command receipts."
        )
    return (
        "1. Inspect update and repair state before advice: version, status, start, "
        "update check, and repair plan facts.\n"
        "2. Stop on runtime mismatch or missing `mb` before business routing.\n"
        "3. Explain what is stale, why it matters, affected surface, write set, and "
        "safe-to-apply state before exact commands.\n"
        "4. Package updates are explicit operator actions. Repair applies, migrations, "
        "global skill writes, skill links, gitignore changes, and untracking require "
        "approval.\n"
        "5. After an approved update or repair, rerun `mb status --json --peek` before "
        "routing back into business work."
    )


def _daily_claude_route_text(workflow: WorkflowSource) -> str:
    if workflow.name == "mb-start-status":
        return (
            "1. Start from status facts before raw markdown: readiness, drift, "
            "runtime wiring, update state, ranked actions, and since-last-check context.\n"
            "2. Run hard gates before routing: required updates, runtime mismatch, repair "
            "blockers, readiness blockers, private-data boundaries, unsafe provider "
            "operations, and destructive-operation requests.\n"
            "3. Use `ranked_actions`, `since_last_check`, `git_activity`, `journal`, `money_path`, "
            "`content_strategy`, `validation.file_contracts`, `onboarding`, "
            "`readiness`, `update`, `drift.items`, and `brain.bets` as cited facts. "
            "Recent activity and `since_last_check` answer what changed without a "
            "separate latest or changelog index.\n"
            "4. Route offer-shape gaps from `validation.file_contracts` to `/mb-think` "
            "after hard gates, and ask before durable writes.\n"
            "5. Use due-soon and overdue bet deadlines, missing-exit criteria, triggered "
            "failure signals, and triggered double-down signals for update, kill, close, "
            "double-down, or narrate routing.\n"
            "6. Present one clear business route and the signal behind it. Mutate the "
            "status marker only when the operator explicitly approves recording the "
            "daily check-in.\n"
            "7. Ask before business-file writes, checkpoints, repairs, updates, migrations, "
            "provider mutation, publishing, spend, customer contact, destructive operations, "
            "or public issue/proposal submission."
        )
    if workflow.name == "mb-setup":
        return (
            "1. Treat setup prompts as setup intent and onboarding intent, not as documents "
            "to save.\n"
            "2. Confirm the target folder and inspect setup capability before writes.\n"
            "3. If `mb` is missing, stop and give the install command. If GitHub backup "
            "is requested, check GitHub CLI auth before any GitHub write.\n"
            "4. Ask before running a write command such as onboarding, repo creation, "
            "file scaffolding, GitHub remote/push, repair apply, migration apply, or "
            "checkpoint save.\n"
            "5. After approved setup, rerun status/start facts and report the owner "
            "outcome before command receipts."
        )
    return (
        "1. Inspect update and repair state before advice: version, status, start, "
        "update check, and repair plan facts.\n"
        "2. Stop on runtime mismatch or missing `mb` before business routing.\n"
        "3. Explain what is stale, why it matters, affected surface, write set, and "
        "safe-to-apply state before exact commands.\n"
        "4. Package updates are explicit operator actions. Repair applies, migrations, "
        "skill links, gitignore changes, and untracking require approval.\n"
        "5. After an approved update or repair, rerun `mb status --json --peek` before "
        "routing back into business work."
    )


def _daily_handoff_template(workflow: WorkflowSource) -> str:
    if workflow.name == "mb-start-status":
        return """Daily state: <ready, needs attention, blocked, or not a Main Branch repo>.
Facts read: <status/start/repair facts used>.
What changed: <since-last-check or journal summary>.
Main signal: <ranked action, readiness, drift, MoneyPath, content strategy, or onboarding fact>.
Recommended route: <one business route and why>.
Approval needed before writes: <yes/no and what action>."""
    if workflow.name == "mb-setup":
        return """Setup state: <not started, target confirmed, created, connected, ready,
or blocked>.
Target folder: <business folder or needs confirmation>.
Facts read: <version/help/status/start/repair facts used>.
Created or planned: <folders, guidance, GitHub backup, checkpoint, or none>.
Owner outcome: <business brain ready, needs approval, or blocked reason>.
Next safe action: <one command or route>.
Approval needed before writes: <yes/no and what action>."""
    return """Maintenance state: <current, update available, repair needed, blocked, or applied>.
Facts read: <version/status/start/update/repair facts used>.
Affected surface: <install, Claude wiring, Codex guidance, migration,
validation, gitignore, or checkpoint hook>.
Plan: <read-only command, write command, files touched, and safe-to-apply state>.
Owner impact: <why this matters in business language>.
Next safe action: <one command or route>.
Approval needed before writes: <yes/no and what action>."""


def _render_daily_claude_shell(workflow: WorkflowSource) -> str:
    """Render a Claude Code shell snapshot for daily operating workflows."""

    output = f"""# Generated Claude Shell: {workflow.title}

Source workflow: `{_display_path(workflow.path)}`
Runtime support: `claude_code: supported_shell`
Approval gates: {_inline_code_list(workflow.approval_gates)}
Public/private boundaries: {_inline_code_list(workflow.public_private_boundaries)}

{_daily_claude_use_text(workflow)}

This snapshot does not replace shipped `.claude/skills` prose.

## Required mb Commands

{_bullet_list(workflow.required_mb_commands)}

## Required JSON Fact Paths

{_bullet_list(workflow.json_facts)}

## Routing

{_daily_claude_route_text(workflow)}

## Handoff Shape

```text
{_daily_handoff_template(workflow)}
```

Use business language first. Technical commands, runtime wiring, provider refs,
and file paths are receipts after the owner-facing state unless the operator asks
for plumbing.
"""
    return output


def _render_start_money_path_claude_shell(workflow: WorkflowSource) -> str:
    """Render the start-to-MoneyPath Claude shell snapshot."""

    output = f"""# Generated Claude Shell: {workflow.title}

Source workflow: `{_display_path(workflow.path)}`
Runtime support: `claude_code: supported_shell`
Approval gates: {_inline_code_list(workflow.approval_gates)}
Public/private boundaries: {_inline_code_list(workflow.public_private_boundaries)}

Use from `/mb-start` when the operator asks about revenue, offer readiness, the
next dollar, or the path to money. Preserve slash-command-native language and
handoff to `/mb-think` only when the next useful move is to clarify, decide,
research, or codify durable business truth.

This snapshot does not replace shipped `.claude/skills` prose.

## Required mb Commands

{_bullet_list(workflow.required_mb_commands)}

## Required JSON Fact Paths

{_bullet_list(workflow.json_facts)}

## Routing

1. Run hard gates first: required updates, broken repo wiring, repair blockers,
   validation blockers, relationship-health blockers, unsafe provider
   operations, private-data boundaries, and destructive-operation requests.
2. Start MoneyPath interpretation from `money_path.overall_level`,
   `money_path.overall_label`, the required `money_path.objects.*` paths, and
   `money_path.ranked_actions`.
3. Compare top-level `ranked_actions` with the MoneyPath bottleneck. If they
   disagree, name the gate or route taking priority.
4. Read supporting markdown only after deterministic facts identify the
   bottleneck.
5. Hand off to `/mb-think` with the MoneyPath snapshot when the next move is a
   decision, research pass, or codify write.

## Handoff Shape

```text
MoneyPath snapshot: overall <level> / <label>.
Bottleneck: <object or gate>.
Proof: <generic/specific/offer-linked/typicality/outcome-feedback facts>.
Offer and ladder: <structured facts and missing fields>.
CTA/channel/push: <connection facts>.
Outcome feedback: <instrumentation facts>.
Ranked actions: <agreement or disagreement with MoneyPath bottleneck>.
Recommended route: use /mb-think to <decision or write target>.
Approval needed before writes: yes.
```

Avoid subjective conversion judgment. Do not say an offer is bad, will convert,
or will not convert.
"""
    return output


def render_codex_shell(workflow: WorkflowSource) -> str:
    """Render a Codex CLI guidance snapshot for a workflow source."""

    if workflow.name == "mb-think":
        return _render_think_codex_shell(workflow)
    if workflow.name == "mb-end":
        return _render_end_codex_shell(workflow)
    if workflow.name == "mb-bet":
        return _render_bet_codex_shell(workflow)
    if workflow.name == "mb-organic":
        return _render_organic_codex_shell(workflow)
    if workflow.name == "mb-ads":
        return _render_ads_codex_shell(workflow)
    if workflow.name == "mb-site":
        return _render_site_codex_shell(workflow)
    if workflow.name in {"mb-start-status", "mb-setup", "mb-maintenance-repair"}:
        return _render_daily_codex_shell(workflow)
    return _render_start_money_path_codex_shell(workflow)


def _render_daily_codex_shell(workflow: WorkflowSource) -> str:
    """Render Codex CLI guidance for daily operating workflows."""

    output = f"""# Generated Codex Workflow Guidance: {workflow.title}

Source workflow: `{_display_path(workflow.path)}`
Runtime support: `codex_cli: {workflow.runtime_support.get("codex_cli", "")}`
Approval gates: {_inline_code_list(workflow.approval_gates)}
Public/private boundaries: {_inline_code_list(workflow.public_private_boundaries)}

Codex is first-class for the proven owner loop only. This guidance is generated
from the engine workflow source for business-repo `AGENTS.md`; the business repo
does not need to contain `{_display_path(workflow.path)}`. Treat this rendered
route as the Codex shell for natural-language daily operating tasks. It does not
claim Claude Code runtime entrypoints work inside Codex or that all Main Branch
workflows are available in Codex.

## Required mb Commands

{_bullet_list(workflow.required_mb_commands)}

## Required JSON Fact Paths

{_bullet_list(workflow.json_facts)}

## Codex Route

{_daily_codex_route_text(workflow)}

## Handoff Shape

```text
{_daily_handoff_template(workflow)}
```

Use business language first. Technical commands, runtime wiring, provider refs,
and file paths are receipts after the owner-facing state unless the operator asks
for plumbing. Do not tell Codex users to run Claude Code entrypoints. Runtime
smoke is required before docs say this selected workflow is supported in Codex.
"""
    return output


def _render_start_money_path_codex_shell(workflow: WorkflowSource) -> str:
    """Render the start-to-MoneyPath Codex shell snapshot."""

    output = f"""# Generated Codex Workflow Guidance: {workflow.title}

Source workflow: `{_display_path(workflow.path)}`
Runtime support: `codex_cli: {workflow.runtime_support.get("codex_cli", "")}`
Approval gates: {_inline_code_list(workflow.approval_gates)}
Public/private boundaries: {_inline_code_list(workflow.public_private_boundaries)}

Codex is first-class for the proven owner loop only. This guidance is a
generated owner-loop shell; it does not mean Claude Code runtime entrypoints
work inside Codex and it does not claim all Main Branch workflow support.

Start from deterministic `mb` facts before reading business markdown or giving
path-to-money advice.

## Required mb Commands

{_bullet_list(workflow.required_mb_commands)}

## Required JSON Fact Paths

{_bullet_list(workflow.json_facts)}

## Codex Route

1. Use the business repo `AGENTS.md` bootstrap posture: read facts first, keep
   writes approval-gated, and translate git/provider details into business
   language.
2. Run hard gates before MoneyPath interpretation: required updates, repair
   blockers, readiness blockers, unsafe provider operations, private-data
   boundaries, and destructive-operation requests.
3. Use `money_path`, `money_path.objects.proof.quality`, `content_strategy`,
   `ranked_actions`, `update`, `readiness`, and `drift.items` as cited facts.
4. If a thinking/codification step is needed, propose the route in Codex-native
   language instead of pretending Claude Code runtime entrypoints are available.
5. Ask before writing business files, saving checkpoints, opening public
   issues, publishing, mutating providers, spending money, or contacting
   customers.

## Handoff Shape

```text
MoneyPath snapshot: overall <level> / <label>.
Bottleneck: <object or gate>.
Proof: <generic/specific/offer-linked/typicality/outcome-feedback facts>.
Offer and ladder: <structured facts and missing fields>.
CTA/channel/push: <connection facts>.
Outcome feedback: <instrumentation facts>.
Ranked actions: <agreement or disagreement with MoneyPath bottleneck>.
Recommended route: clarify or codify <decision or write target> after approval.
Approval needed before writes: yes.
```

Runtime smoke is required before docs say this selected workflow is supported
or available in Codex.
"""
    return output


def _render_think_claude_shell(workflow: WorkflowSource) -> str:
    """Render a Claude Code shell snapshot for the thinking workflow."""

    output = f"""# Generated Claude Shell: {workflow.title}

Source workflow: `{_display_path(workflow.path)}`
Runtime support: `claude_code: supported_shell`
Approval gates: {_inline_code_list(workflow.approval_gates)}
Public/private boundaries: {_inline_code_list(workflow.public_private_boundaries)}

Use from `/mb-think` when the operator asks to research, decide, figure out,
compare, codify, sharpen an offer, or turn learning into durable business
truth. Preserve slash-command-native language for Claude Code only.

This snapshot does not replace shipped `.claude/skills/mb-think/SKILL.md`.

## Required mb Commands

{_bullet_list(workflow.required_mb_commands)}

## Required JSON Fact Paths

{_bullet_list(workflow.json_facts)}

## Routing

1. Run hard gates first: required updates, broken repo wiring, repair blockers,
   validation blockers, unsafe provider operations, private-data boundaries,
   and destructive-operation requests.
2. Read deterministic `mb` facts before raw markdown. Then read only relevant
   `core/`, `research/`, `decisions/`, `bets/`, `pushes/`, `log/`, and `docs/`
   files.
3. Give a Research Depth Recommendation from 0-5 before outside research:
   memory, repo context, lightweight public/manual research, multi-source
   synthesis, structured approved-source collection, or high-resolution market
   analysis.
4. Use parallel research files for multiple sources, then synthesize in the
   main thread. Each source file records source quality, access/permission,
   caveats, promotion limits, and public/private handling.
5. Write a decision when durable business truth changes. Codify only after the
   operator accepts the direction.
6. For transcripts, authenticated community content, provider recordings, or
   mixed private/business sources, use manifest-first allow/skip filters before
   reading content. Route synthesized output, not raw payloads.
7. For stale source, claim, proof, or angle cleanup, identify the stale item,
   find downstream usage, keep history auditable with a stale note, reconcile
   current truth after approval, record and codify the decision, then
   checkpoint only after approval.
8. Ask for approval before creating or editing business files, promoting
   research into core truth, using structured collection, or saving a
   checkpoint.

## Handoff Shape

```text
Thinking task: <research, decision, codify, or full flow>.
Repo facts read: <status/start/connect/repair/checkpoint facts used>.
Current bottleneck: <MoneyPath, content strategy, readiness, drift, or user question>.
Research depth recommendation: <0-5>, because <reason>.
Useful sources: <repo files, public/manual sources, approved providers, or operator input>.
Stop condition: <what is enough signal>.
Durable targets: <research/, decisions/, core/, bets/, pushes/, log/, or documents/>.
Approval needed before writes: yes.
```

Use business language. Do not say an offer is bad, will convert, or will not
convert. Do not tell Codex users to run Claude Code entrypoints.
"""
    return output


def _render_think_codex_shell(workflow: WorkflowSource) -> str:
    """Render Codex CLI guidance for the thinking workflow."""

    output = f"""# Generated Codex Workflow Guidance: {workflow.title}

Source workflow: `{_display_path(workflow.path)}`
Runtime support: `codex_cli: {workflow.runtime_support.get("codex_cli", "")}`
Approval gates: {_inline_code_list(workflow.approval_gates)}
Public/private boundaries: {_inline_code_list(workflow.public_private_boundaries)}

Codex is first-class for the proven owner loop only. This guidance is generated
from the engine workflow source for business-repo `AGENTS.md`; the business repo
does not need to contain `{_display_path(workflow.path)}`. Treat this rendered
route as the Codex shell for natural-language thinking tasks. It does not claim
Claude Code runtime entrypoints work inside Codex or that all Main Branch
workflows are available in Codex.

## Required mb Commands

{_bullet_list(workflow.required_mb_commands)}

## Required JSON Fact Paths

{_bullet_list(workflow.json_facts)}

## Codex Route

1. Use the business repo `AGENTS.md` bootstrap posture: read facts first, keep
   writes approval-gated, and translate git/provider details into business
   language.
2. Run hard gates first: required updates, repair blockers, readiness
   blockers, unsafe provider operations, private-data boundaries, and
   destructive-operation requests.
3. Read deterministic `mb` facts before raw markdown. Then read only relevant
   `core/`, `research/`, `decisions/`, `bets/`, `pushes/`, `log/`, and `docs/`
   files.
4. Give a Research Depth Recommendation from 0-5 before outside research:
   memory, repo context, lightweight public/manual research, multi-source
   synthesis, structured approved-source collection, or high-resolution market
   analysis.
5. Use parallel research files for multiple sources, then synthesize in the
   main thread. Each source file records source quality, access/permission,
   caveats, promotion limits, and public/private handling.
6. Write a decision when durable business truth changes. Codify only after the
   operator accepts the direction.
7. For transcripts, authenticated community content, provider recordings, or
   mixed private/business sources, use manifest-first allow/skip filters before
   reading content. Route synthesized output, not raw payloads.
8. For stale source, claim, proof, or angle cleanup, identify the stale item,
   find downstream usage, keep history auditable with a stale note, reconcile
   current truth after approval, record and codify the decision, then
   checkpoint only after approval.
9. Ask for approval before creating or editing business files, promoting
   research into core truth, using structured collection, opening public
   issues, publishing, provider mutation, spend, customer contact, or checkpoint.

## Handoff Shape

```text
Thinking task: <research, decision, codify, or full flow>.
Repo facts read: <status/start/connect/repair/checkpoint facts used>.
Current bottleneck: <MoneyPath, content strategy, readiness, drift, or user question>.
Research depth recommendation: <0-5>, because <reason>.
Useful sources: <repo files, public/manual sources, approved providers, or operator input>.
Stop condition: <what is enough signal>.
Durable targets: <research/, decisions/, core/, bets/, pushes/, log/, or documents/>.
Approval needed before writes: yes.
```
Do not tell Codex users to run Claude Code entrypoints. Runtime smoke is
required before docs say this selected workflow is supported in Codex.
"""
    return output


def _render_bet_claude_shell(workflow: WorkflowSource) -> str:
    """Render a Claude Code shell snapshot for the bet lifecycle workflow."""

    output = f"""# Generated Claude Shell: {workflow.title}

Source workflow: `{_display_path(workflow.path)}`
Runtime support: `claude_code: supported_shell`
Approval gates: {_inline_code_list(workflow.approval_gates)}
Public/private boundaries: {_inline_code_list(workflow.public_private_boundaries)}

Use from `/mb-bet` when the operator wants to create, update, close, list, or
narrate bets. Preserve the existing Claude skill's mode language, approval
gates, artifact routing, and finance/privacy boundaries.

This snapshot does not replace shipped `.claude/skills/mb-bet/SKILL.md`.

## Required mb Commands

{_bullet_list(workflow.required_mb_commands)}

## Required JSON Fact Paths

{_bullet_list(workflow.json_facts)}

## Routing

1. Read deterministic facts first: status, start when runtime facts matter,
   repair plan when blockers appear, validation, relationship health,
   checkpoint plan, similar-bets for repeated material theses, and aggregate
   exposure for financially material bets.
2. Bet is a time-boxed wager, not an offer or push. Offers are durable things
   sold; pushes coordinate execution. Bets carry hypothesis, appetite, target,
   deadline, evidence, kill or double-down logic, and verdict.
3. Support new, update, close, list, and narrate modes. Create or edit
   `bets/YYYY-MM-DD-slug.md` only after approval, and keep the strict contract:
   frontmatter fields, body sections, typed links, reverse `linked_bets`, and
   `## Related links`.
4. For updates, append dated evidence and links without filling `result` unless
   there is a measured result. For close, record verdict, learning, outcomes,
   and graduation route without rewriting failed bets as success.
5. Use `mb validate --cross-refs --json` after bet or link edits. Use the
   checkpoint plan before offering an approval-gated save.
6. For financially material bets, use aggregate exposure only. Never paste raw
   ledger rows, payees, account names, vault paths, transaction memos, provider
   exports, customer/member records, or secrets.
7. Public-safe narration must come from accepted repo truth. Do not invent
   metrics, results, testimonials, channels, or proof. If `public: false`, ask
   before drafting public copy.
8. Do not publish, spend, contact customers, mutate providers, create dashboard
   work, or promote bet learning into offer truth without accepted evidence,
   an accepted decision, and explicit approval.

## Handoff Shape

```text
Bet mode: <new, update, close, list, or narrate>.
Facts read: <status/start/validate/relationship/exposure/similar-bets facts>.
Bet: <path, status, deadline, appetite, metric, target>.
Evidence: <new evidence, missing evidence, or measured result>.
Exit posture: <kill, double-down, continue, close, or unclear>.
Connections: <decisions, research, pushes, outcomes, offers, or none>.
Public posture: <public-safe, private, needs approval, or not narration>.
Write plan: <files to create/edit or none>.
Approval needed before writes: <yes/no and exact action>.
Next business action: <one clear owner-facing step>.
```

Use business language first. Keep legacy campaign links compatibility-only;
new execution routes through pushes. Codex support stays read-only planning
until runtime smoke proves bet lifecycle writes.
"""
    return output


def _render_bet_codex_shell(workflow: WorkflowSource) -> str:
    """Render Codex CLI guidance for the bet lifecycle workflow."""

    output = f"""# Generated Codex Workflow Guidance: {workflow.title}

Source workflow: `{_display_path(workflow.path)}`
Runtime support: `codex_cli: {workflow.runtime_support.get("codex_cli", "")}`
Approval gates: {_inline_code_list(workflow.approval_gates)}
Public/private boundaries: {_inline_code_list(workflow.public_private_boundaries)}

Codex uses the global Main Branch `mb-bet` skill as a read-only planning and
file-guidance route. This guidance is generated from the engine workflow source
and does not claim supported lifecycle writes or Claude Code entrypoints in
Codex.

## Required mb Commands

{_bullet_list(workflow.required_mb_commands)}

## Required JSON Fact Paths

{_bullet_list(workflow.json_facts)}

## Codex Route

1. Use the business repo `AGENTS.md` bootstrap posture: read facts first, keep
   writes approval-gated, and translate git/provider details into business
   language.
2. Read deterministic facts before raw markdown: status, start when runtime
   facts matter, repair plan when blockers appear, validation, relationship
   health, checkpoint plan, similar-bets for repeated material theses, and
   aggregate exposure for financially material bets.
3. Bet is a time-boxed wager, not an offer or push. Offers are durable things
   sold; pushes coordinate execution. Bets carry hypothesis, appetite, target,
   deadline, evidence, kill or double-down logic, and verdict.
4. Guide new, update, close, list, and narrate modes from the shared contract.
   Codex may draft patch-shaped recommendations and exact file targets, then
   stop before changing files.
5. Keep the strict contract for `bets/YYYY-MM-DD-slug.md`: frontmatter fields,
   body sections, typed links, reverse `linked_bets`, and `## Related links`.
6. If the operator wants the proposed changes applied, route them to Claude
   Code `/mb-bet` or another supported write surface until Codex lifecycle-write
   smoke proves this route. Do not run checkpoint commands or post-change
   validation as if Codex edited files.
7. For financially material bets, use aggregate exposure only. Never paste raw
   ledger rows, payees, account names, vault paths, transaction memos, provider
   exports, customer/member records, or secrets.
8. Public-safe narration must come from accepted repo truth. Do not invent
   metrics, results, testimonials, channels, or proof. If `public: false`, ask
   before drafting public copy.
9. Do not publish, spend, contact customers, mutate providers, create dashboard
   work, or promote bet learning into offer truth without accepted evidence,
   an accepted decision, and explicit approval.

## Handoff Shape

```text
Bet mode: <new, update, close, list, or narrate>.
Facts read: <status/start/validate/relationship/exposure/similar-bets facts>.
Bet: <path, status, deadline, appetite, metric, target>.
Evidence: <new evidence, missing evidence, or measured result>.
Exit posture: <kill, double-down, continue, close, or unclear>.
Connections: <decisions, research, pushes, outcomes, offers, or none>.
Public posture: <public-safe, private, needs approval, or not narration>.
Write plan: <files to create/edit or none>.
Approval needed before writes: <yes/no and exact action>.
Next business action: <one clear owner-facing step>.
```

Use business language first. Keep legacy campaign links compatibility-only;
new execution routes through pushes. Runtime smoke is required before docs say
this lifecycle is supported for Codex writes.
"""
    return output


def _render_organic_claude_shell(workflow: WorkflowSource) -> str:
    """Render a Claude Code shell snapshot for the organic content workflow."""

    output = f"""# Generated Claude Shell: {workflow.title}

Source workflow: `{_display_path(workflow.path)}`
Runtime support: `claude_code: supported_shell`
Approval gates: {_inline_code_list(workflow.approval_gates)}
Public/private boundaries: {_inline_code_list(workflow.public_private_boundaries)}

Use from `/mb-organic` when the operator wants organic content planning,
scripts, carousels, static posts, sales-video repurposing, or content review.
Preserve the existing Claude skill's mode language, mining handoff, voice
adaptation, content strategy integration, artifact routing, and source/privacy
boundaries.

This snapshot does not replace shipped `.claude/skills/mb-organic/SKILL.md`.

## Required mb Commands

{_bullet_list(workflow.required_mb_commands)}

## Required JSON Fact Paths

{_bullet_list(workflow.json_facts)}

## Routing

1. Read deterministic facts first: status, start when runtime facts matter,
   repair plan when blockers appear, content strategy health, proof quality,
   relationship gaps, validation, and checkpoint plan.
2. For mining handoff, route to `mb-think` for mining, scraping, competitor
   research, transcript extraction, and outside source collection. Organic drafts from accepted
   `research/` handoffs, operator excerpts, approved transcripts, and current
   business truth.
3. Support plan, video, carousel, static, sales-video-repurpose, or review
   modes. Use content_strategy.overall_state, content_strategy.simple_entry_point,
   content_strategy.layers, and content_strategy.findings before parsing raw
   strategy files.
4. Draft from active offer, audience, voice, content strategy, relevant
   channel/account/person layers, research, sales-video notes, active pushes,
   and money_path.objects.proof.quality. Do not call proof good, bad,
   persuasive, high-converting, or ready to win.
5. Route coordinated content to `pushes/<YYYY-MM-DD-slug>/push.md`, draft
   batches to `pushes/<YYYY-MM-DD-slug>/organic-batch-001.md`, and provider
   mechanics to `pushes/<YYYY-MM-DD-slug>/playbooks/<playbook>.md` as plans.
6. Use `mb validate --cross-refs --json` after approved push, draft, playbook,
   typed-link, or related-link edits. Use the checkpoint plan before offering
   an approval-gated save.
7. Keep source/privacy boundaries explicit. Never paste raw provider exports,
   private DMs, gated community threads, raw customer/member records, raw
   transcripts, account details, session cookies, finance/legal records, or
   secrets.
8. Do not publish, schedule, upload to accounts, mutate provider accounts,
   spend, auto-DM, auto-reply, contact customers, or execute provider setup.

## Push Links

{_PUSH_LINK_STEP}

## Handoff Shape

```text
Organic mode: <plan, video, carousel, static, sales-video-repurpose, or review>.
Facts read: <status/start/content-strategy/proof/checkpoint facts>.
Source base: <offer, audience, voice, research, sales video, push, account, or missing>.
Channel/account: <platform/account/person layer or not selected>.
Content strategy: <healthy, thin, stale, disconnected, or missing>.
Proof/privacy posture: <public-safe, internal-only, missing permission, or needs summary>.
Artifact route: <push path, batch path, playbook path, or none>.
Write plan: <files to create/edit or planning only>.
Approval needed before writes: <yes/no and exact action>.
Next business action: <one clear owner-facing step>.
```

Use business language first. New coordinated work uses pushes. Legacy content
structures are migration input only. Codex support stays read-only planning
until runtime smoke proves organic drafting writes.
"""
    return output


def _render_organic_codex_shell(workflow: WorkflowSource) -> str:
    """Render Codex CLI guidance for the organic content workflow."""

    output = f"""# Generated Codex Workflow Guidance: {workflow.title}

Source workflow: `{_display_path(workflow.path)}`
Runtime support: `codex_cli: {workflow.runtime_support.get("codex_cli", "")}`
Approval gates: {_inline_code_list(workflow.approval_gates)}
Public/private boundaries: {_inline_code_list(workflow.public_private_boundaries)}

Codex uses the global Main Branch `mb-organic` skill as a read-only planning
and file-guidance route. This guidance is generated from the engine workflow
source and does not claim supported organic drafting writes, publishing,
account mutation, customer contact, or Claude Code entrypoints in Codex.

## Required mb Commands

{_bullet_list(workflow.required_mb_commands)}

## Required JSON Fact Paths

{_bullet_list(workflow.json_facts)}

## Codex Route

1. Use the business repo `AGENTS.md` bootstrap posture: read facts first, keep
   writes approval-gated, and translate git/provider details into business
   language.
2. Read deterministic facts before raw markdown: status, start when runtime
   facts matter, repair plan when blockers appear, content strategy health,
   proof quality, relationship gaps, validation, and checkpoint plan.
3. For mining handoff, route to `mb-think` in Codex-native language for mining,
   scraping, competitor research, transcript extraction, and outside source
   collection. Organic may plan from accepted `research/` handoffs, operator
   excerpts, approved transcripts, and current business truth.
4. Guide plan, video, carousel, static, sales-video-repurpose, or review modes
   from the shared contract. Use content_strategy.overall_state,
   content_strategy.simple_entry_point, content_strategy.layers, and
   content_strategy.findings before parsing raw strategy files.
5. Codex may draft patch-shaped recommendations, sample copy, review notes,
   and exact file targets, then stop before changing files.
6. Name artifact routes as plans only: `pushes/<YYYY-MM-DD-slug>/push.md`,
   `pushes/<YYYY-MM-DD-slug>/organic-batch-001.md`, and
   `pushes/<YYYY-MM-DD-slug>/playbooks/<playbook>.md`.
7. If the operator wants the proposed content applied, route them to Claude
   Code `/mb-organic` or another supported write surface until Codex
   organic-write smoke proves this route. Do not run checkpoint commands or
   post-change validation as if Codex edited files.
8. Keep source/privacy boundaries explicit. Never paste raw provider exports,
   private DMs, gated community threads, raw customer/member records, raw
   transcripts, account details, session cookies, finance/legal records, or
   secrets.
9. Do not publish, schedule, upload to accounts, mutate provider accounts,
   spend, auto-DM, auto-reply, contact customers, or execute provider setup.

## Push Links

{_PUSH_LINK_STEP}

For Codex, include these as proposed file edits and stop before applying.

## Handoff Shape

```text
Organic mode: <plan, video, carousel, static, sales-video-repurpose, or review>.
Facts read: <status/start/content-strategy/proof/checkpoint facts>.
Source base: <offer, audience, voice, research, sales video, push, account, or missing>.
Channel/account: <platform/account/person layer or not selected>.
Content strategy: <healthy, thin, stale, disconnected, or missing>.
Proof/privacy posture: <public-safe, internal-only, missing permission, or needs summary>.
Artifact route: <push path, batch path, playbook path, or none>.
Write plan: <files to create/edit or planning only>.
Approval needed before writes: <yes/no and exact action>.
Next business action: <one clear owner-facing step>.
```

Use business language first. New coordinated work uses pushes. Legacy content
structures are migration input only. Runtime smoke is required before docs say
this workflow is supported for Codex writes.
"""
    return output


def _render_ads_claude_shell(workflow: WorkflowSource) -> str:
    """Render a Claude Code shell snapshot for the ads workflow."""

    output = f"""# Generated Claude Shell: {workflow.title}

Source workflow: `{_display_path(workflow.path)}`
Runtime support: `claude_code: supported_shell`
Approval gates: {_inline_code_list(workflow.approval_gates)}
Public/private boundaries: {_inline_code_list(workflow.public_private_boundaries)}

Use from `/mb-ads` when the operator wants paid creative planning, ad copy,
image prompts, video scripts, long-form paid creative, compliance review,
launch plans, launch instrumentation checks, launch checks, optional read-only
account context, or Google Ads Search planning. Preserve the existing Claude
skill's mode language, proof discipline, review workflow, paid-search
launch-plan path, and provider gates.

This snapshot does not replace shipped `.claude/skills/mb-ads/SKILL.md`.

## Required mb Commands

{_bullet_list(workflow.required_mb_commands)}

## Required JSON Fact Paths

{_bullet_list(workflow.json_facts)}

## Routing

1. Read deterministic facts first: status, start when runtime facts matter,
   repair plan when blockers appear, provider readiness, measurement readiness,
   site-check readiness, relationship gaps, validation, and checkpoint plan.
2. For mining, scraping, competitor research, transcript extraction, outside
   source collection, thin offers, or unsupported claims, route to `mb-think`
   before drafting paid creative.
3. For landing-page, conversion endpoint, GA4, GTM/dataLayer, Meta pixel,
   booking links, HubSpot/forms, consent, form-submit smoke, or paid
   measurement readiness, route to `mb-site` and use `mb site check` before
   describing traffic as locally ready for operator review.
4. Support static, copy-only, image-only, hook-library, video-scripts,
   long-form-video, review, launch-plan, check, or account-context modes.
   Treat instrumentation as the launch-readiness sub-mode for GA4/GTM/pixels,
   booking links, HubSpot/forms, and submit/booking smoke.
5. Draft from active offer, audience, voice, content strategy, proof facts,
   relevant research, decisions, active pushes, playbooks, and
   money_path.objects.proof.quality. Do not turn unapproved proof into public
   ad claims.
6. Route coordinated paid work to `pushes/<YYYY-MM-DD-slug>/push.md`, draft
   batches to `pushes/<YYYY-MM-DD-slug>/ads-batch-001.md`, provider or launch
   plans to `pushes/<YYYY-MM-DD-slug>/playbooks/<playbook>.md`, research to
   `research/`, and accepted tradeoffs to `decisions/`.
7. For Google Ads Search, use the google-ads-search-launch playbook source and
   official Google Ads docs for load-bearing limits, policy, targeting, and
   feature mechanics. The playbook is a manual recipe, not provider authority.
8. Keep provider gates explicit. Do not publish ads, schedule ads, upload assets,
   perform provider mutation, mutate provider accounts, change budgets, start
   spend, publish GTM, upload conversions, change billing, or contact customers.
   Execution needs explicit approval and runtime evidence for that exact surface.

## Push Links

{_PUSH_LINK_STEP}

## Handoff Shape

```text
Ads mode: <static, copy-only, image-only, hook-library, video-scripts,
long-form-video, review, launch-plan, instrumentation, check, or account-context>.
Facts read: <status/start/connect/site-check/validation/checkpoint facts>.
Source base: <offer, audience, voice, proof, research, push, playbook, account summary, or missing>.
Provider posture: <not needed, read-only, connected, blocked, unsupported, or approval needed>.
Measurement posture: <missing, blocked, ready_for_preview,
ready_for_operator_review, ready, or not checked>.
Proof/privacy posture: <public-safe, internal-only, missing permission,
unsupported claim, or needs summary>.
Artifact route: <push path, ads batch path, playbook run path, research path,
decision path, or none>.
Write plan: <files to create/edit or planning only>.
Approval needed before writes/provider action: <yes/no and exact action>.
Next business action: <one clear owner-facing step>.
```

Use business language first. New coordinated work uses pushes. Provider
mutation, publishing, spend, uploads, account changes, GTM publishes,
conversion uploads, and customer contact stay approval-gated and manual unless
the exact adapter surface has shipped evidence. Codex support: read-only planning.
Runtime smoke must prove ads writes or provider execution.
"""
    return output


def _render_ads_codex_shell(workflow: WorkflowSource) -> str:
    """Render Codex CLI guidance for the ads workflow."""

    output = f"""# Generated Codex Workflow Guidance: {workflow.title}

Source workflow: `{_display_path(workflow.path)}`
Runtime support: `codex_cli: {workflow.runtime_support.get("codex_cli", "")}`
Approval gates: {_inline_code_list(workflow.approval_gates)}
Public/private boundaries: {_inline_code_list(workflow.public_private_boundaries)}

Codex uses the global Main Branch `mb-ads` skill as a read-only planning and
file-guidance route. This guidance is generated from the engine workflow source
and does not claim supported paid creative writes, provider mutation, asset
uploads, publishing, spend, account changes, GTM publishes, conversion uploads,
customer contact, or Claude Code entrypoints in Codex.

## Required mb Commands

{_bullet_list(workflow.required_mb_commands)}

## Required JSON Fact Paths

{_bullet_list(workflow.json_facts)}

## Codex Route

1. Use the business repo `AGENTS.md` bootstrap posture: read facts first, keep
   writes approval-gated, and translate provider details into business language.
2. Read deterministic facts before raw markdown: status, start when runtime
   facts matter, repair plan when blockers appear, provider readiness,
   measurement readiness, site-check readiness, relationship gaps, validation,
   and checkpoint plan.
3. For mining, scraping, competitor research, transcript extraction, outside
   source collection, thin offers, or unsupported claims, route to `mb-think`
   in Codex-native language before drafting paid creative.
4. For landing-page, conversion endpoint, GA4, GTM/dataLayer, Meta pixel,
   booking links, HubSpot/forms, consent, form-submit smoke, or paid
   measurement readiness, route to `mb-site` in Codex-native language and use
   `mb site check` before describing traffic as locally ready for operator
   review.
5. Guide static, copy-only, image-only, hook-library, video-scripts,
   long-form-video, review, launch-plan, check, or account-context modes from
   the shared contract. Treat instrumentation as the launch-readiness sub-mode.
   Codex may draft patch-shaped recommendations, sample copy, review notes, and
   launch-plan specs. Name exact file targets, then stop before changing files
   or running provider tools.
6. Name artifact routes as plans only: `pushes/<YYYY-MM-DD-slug>/push.md`,
   `pushes/<YYYY-MM-DD-slug>/ads-batch-001.md`,
   `pushes/<YYYY-MM-DD-slug>/playbooks/<playbook>.md`, `research/`, and
   `decisions/`.
7. For Google Ads Search, use the google-ads-search-launch playbook source and
   official Google Ads docs for load-bearing limits, policy, targeting, and
   feature mechanics. The playbook remains draft/manual and blocked from direct
   Codex execution by provider gates.
8. If the operator wants proposed ad or launch-plan files applied, route them
   to Claude Code `/mb-ads` or another supported write surface until Codex
   ads-write smoke proves this route. Do not run checkpoint commands,
   post-change validation, provider tools, upload steps, campaign actions, GTM
   actions, budget changes, or customer contact as if Codex edited or executed
   the work.
9. Keep provider gates explicit. Do not publish ads, schedule ads, upload assets,
   mutate provider accounts, change budgets, start spend, publish GTM, upload
   conversions, change billing, or contact customers.

## Push Links

{_PUSH_LINK_STEP}

For Codex, include these as proposed file edits and stop before applying.

## Handoff Shape

```text
Ads mode: <static, copy-only, image-only, hook-library, video-scripts,
long-form-video, review, launch-plan, instrumentation, check, or account-context>.
Facts read: <status/start/connect/site-check/validation/checkpoint facts>.
Source base: <offer, audience, voice, proof, research, push, playbook, account summary, or missing>.
Provider posture: <not needed, read-only, connected, blocked, unsupported, or approval needed>.
Measurement posture: <missing, blocked, ready_for_preview,
ready_for_operator_review, ready, or not checked>.
Proof/privacy posture: <public-safe, internal-only, missing permission,
unsupported claim, or needs summary>.
Artifact route: <push path, ads batch path, playbook run path, research path,
decision path, or none>.
Write plan: <files to create/edit or planning only>.
Approval needed before writes/provider action: <yes/no and exact action>.
Next business action: <one clear owner-facing step>.
```

Use business language first. Runtime smoke is required before docs say this
workflow is supported for Codex paid creative writes, provider mutation,
uploads, publishing, spend, account changes, GTM publishes, conversion uploads,
or customer contact.
"""
    return output


def _render_site_claude_shell(workflow: WorkflowSource) -> str:
    """Render a Claude Code shell snapshot for the site workflow."""

    output = f"""# Generated Claude Shell: {workflow.title}

Source workflow: `{_display_path(workflow.path)}`
Runtime support: `claude_code: supported_shell`
Approval gates: {_inline_code_list(workflow.approval_gates)}
Public/private boundaries: {_inline_code_list(workflow.public_private_boundaries)}

Use from `/mb-site` when the operator wants to plan, brief, build, preview,
check, publish, iterate, graduate, or recover an owned conversion surface,
including analytics/instrumentation checks.
Modes: plan, brief, build, preview, check, publish, iterate, graduate, or recover.
Preserve the existing Claude skill's lander, minisite, website, sales-video
surface, business-repo mode, site-repo mode, Cloudflare gate, and checkpoint
contract.

This snapshot does not replace shipped `.claude/skills/mb-site/SKILL.md`.

## Required mb Commands

{_bullet_list(workflow.required_mb_commands)}

## Required JSON Fact Paths

{_bullet_list(workflow.json_facts)}

## Routing

1. Read deterministic facts first: status, start when runtime facts matter,
   repair plan when blockers appear, Cloudflare/provider readiness, site-check
   readiness, relationship gaps, validation, and checkpoint plan.
2. Detect business repo mode or site repo mode. Use `.mainbranch/repo.json` as
   the preferred site descriptor and legacy `.mainbranch/source.json` only as
   compatibility.
3. Support plan, brief, build, preview, check, publish, iterate, graduate, or
   recover modes across lander, minisite, website, and sales-video surface
   shapes. Treat instrumentation as the check mode for analytics, tags,
   booking/form widgets, and event mapping.
4. For business-repo site readiness, use `measurement.*` facts from status. For
   site-repo readiness, use top-level `state`, `blocked`, `manual`, `evidence`,
   `facts.expected_events`, `facts.instrumentation`, `facts.provider_state`,
   `source`, and `child_descriptor` from `mb site check`. Use exact readiness
   states such as ready_for_operator_review; do not invent ready_for_launch.
5. Draft from active offer, audience, voice, content strategy, proof facts,
   relevant research, decisions, active pushes, and MoneyPath facts. Route thin
   offers or unsupported claims to `mb-think` before page copy.
6. Route coordinated site work to `pushes/<YYYY-MM-DD-slug>/push.md`, site
   records to `pushes/<YYYY-MM-DD-slug>/site.md` or the relevant offer note,
   research to `research/`, locked briefs to `decisions/`, and descriptors to
   `.mainbranch/repo.json` in the site repo after approval.
7. Use `mb validate --cross-refs --json` after approved business-repo link,
   push, site, brief, or related-link edits. Use `mb site check` for site repo
   readiness and the checkpoint plan before offering an approval-gated save.
8. Keep provider gates explicit. Do not buy domains, change DNS, create
   Cloudflare Pages projects, attach custom domains, deploy, git push, publish,
   spend, perform provider mutation, mutate provider accounts, or contact
   customers. Do not contact customers or execute account changes without
   explicit approval and runtime evidence for that surface.

## Push Links

{_PUSH_LINK_STEP}

## Handoff Shape

```text
Site mode: <plan, brief, build, preview, check, publish, iterate, graduate,
or recover; instrumentation is a check sub-mode>.
Repo mode: <business repo, site repo, both linked, or unclear>.
Facts read: <status/start/connect/site-check/validation/checkpoint facts>.
Shape: <lander, minisite, website, sales-video surface, or unknown>.
Offer/CTA: <resolved, thin, blocked, or needs decision>.
Readiness: <missing, blocked, ready_for_preview, ready_for_operator_review, ready, or not checked>.
Provider posture: <read-only, connected, blocked, approval needed, or unsupported>.
Artifact route: <business push/site/decision/research path, site repo target, or none>.
Write plan: <files to create/edit or planning only>.
Approval needed before writes/provider action: <yes/no and exact action>.
Next business action: <one clear owner-facing step>.
```

Use business language first. Site code commits still use the site repo's normal
git flow; business-repo saves use `mb checkpoint`. Codex support stays
read-only planning until runtime smoke proves site writes, builds, deploys, and
publishing.
"""
    return output


def _render_site_codex_shell(workflow: WorkflowSource) -> str:
    """Render Codex CLI guidance for the site workflow."""

    output = f"""# Generated Codex Workflow Guidance: {workflow.title}

Source workflow: `{_display_path(workflow.path)}`
Runtime support: `codex_cli: {workflow.runtime_support.get("codex_cli", "")}`
Approval gates: {_inline_code_list(workflow.approval_gates)}
Public/private boundaries: {_inline_code_list(workflow.public_private_boundaries)}

Codex uses the global Main Branch `mb-site` skill as a read-only planning and
site-readiness route. This guidance is generated from the engine workflow
source and does not claim supported site writes, builds, deploys, publishing,
provider mutation, account changes, customer contact, or Claude Code
entrypoints in Codex.
Modes: plan, brief, build, preview, check, publish, iterate, graduate, or recover.

## Required mb Commands

{_bullet_list(workflow.required_mb_commands)}

## Required JSON Fact Paths

{_bullet_list(workflow.json_facts)}

## Codex Route

1. Use the business repo `AGENTS.md` bootstrap posture: read facts first, keep
   writes approval-gated, and translate git/provider details into business
   language.
2. Read deterministic facts before raw markdown: status, start when runtime
   facts matter, repair plan when blockers appear, provider readiness,
   site-check readiness, relationship gaps, validation, and checkpoint plan.
3. Detect business repo mode or site repo mode. Use `.mainbranch/repo.json` as
   the preferred site descriptor and legacy `.mainbranch/source.json` only as
   compatibility.
4. Guide plan, brief, build, preview, check, publish, iterate, graduate, or
   recover modes across lander, minisite, website, and sales-video surface
   shapes from the shared contract. Treat instrumentation as the check mode for
   analytics, tags, booking/form widgets, and event mapping.
5. For business-repo site readiness, use `measurement.*` facts from status. For
   site-repo readiness, use top-level `state`, `blocked`, `manual`, `evidence`,
   `facts.expected_events`, `facts.instrumentation`, `facts.provider_state`,
   `source`, and `child_descriptor` from `mb site check`. Use exact readiness
   states such as ready_for_operator_review; do not invent ready_for_launch.
6. Codex may draft patch-shaped recommendations, sample copy, review notes,
   readiness summaries, and exact file targets, then stop before changing files
   or running build/deploy actions.
7. Name artifact routes as plans only: `pushes/<YYYY-MM-DD-slug>/push.md`,
   `pushes/<YYYY-MM-DD-slug>/site.md`, `research/`, `decisions/`, and
   `.mainbranch/repo.json`.
8. If the operator wants proposed site changes applied, route them to Claude
   Code `/mb-site` or another supported write surface until Codex site-write
   and build/deploy smoke proves this route. Do not run post-change validation,
   checkpoint commands, git pushes, deploys, or provider tools as if Codex
   edited files.
9. Keep provider gates explicit. Do not buy domains, change DNS, create
   Cloudflare Pages projects, attach custom domains, deploy, git push, publish,
   spend, mutate provider accounts, contact customers, or execute account
   changes.

## Push Links

{_PUSH_LINK_STEP}

For Codex, include these as proposed file edits and stop before applying.

## Handoff Shape

```text
Site mode: <plan, brief, build, preview, check, publish, iterate, graduate,
or recover; instrumentation is a check sub-mode>.
Repo mode: <business repo, site repo, both linked, or unclear>.
Facts read: <status/start/connect/site-check/validation/checkpoint facts>.
Shape: <lander, minisite, website, sales-video surface, or unknown>.
Offer/CTA: <resolved, thin, blocked, or needs decision>.
Readiness: <missing, blocked, ready_for_preview, ready_for_operator_review, ready, or not checked>.
Provider posture: <read-only, connected, blocked, approval needed, or unsupported>.
Artifact route: <business push/site/decision/research path, site repo target, or none>.
Write plan: <files to create/edit or planning only>.
Approval needed before writes/provider action: <yes/no and exact action>.
Next business action: <one clear owner-facing step>.
```

Use business language first. Runtime smoke is required before docs say this
workflow is supported for Codex site writes, builds, deploys, or publishing.
"""
    return output


def _render_end_claude_shell(workflow: WorkflowSource) -> str:
    """Render a Claude Code shell snapshot for the closeout workflow."""

    output = f"""# Generated Claude Shell: {workflow.title}

Source workflow: `{_display_path(workflow.path)}`
Runtime support: `claude_code: supported_shell`
Approval gates: {_inline_code_list(workflow.approval_gates)}
Public/private boundaries: {_inline_code_list(workflow.public_private_boundaries)}

Use from `/mb-end` when the operator is done, pausing, closing a work block, or
asking whether the work is saved. Preserve slash-command-native language for
Claude Code only.

This snapshot does not replace shipped `.claude/skills/mb-end/SKILL.md`.

## Required mb Commands

{_bullet_list(workflow.required_mb_commands)}

## Required JSON Fact Paths

{_bullet_list(workflow.json_facts)}

## Routing

Mid-session save vs close: if the operator only wants to save progress and keep
working — "save", "checkpoint this", "yes save" mid-flow — this is a save, not a
close. Run `mb checkpoint --plan`, save on approval through `mb checkpoint`, and
return them to work. Never save with raw git. Use the full closeout below only
when the session is actually ending or pausing.

1. Run a status scan first. Use deterministic status, checkpoint, validation,
   readiness, drift, recent-work, and runtime facts before reading raw git
   details.
2. Build the checkpoint plan from `mb checkpoint --plan --json`; use
   `mb validate --json` for blockers and cite `mb doctor repair --plan` when
   repairs are needed.
3. Give a short session summary in business language: decisions, research,
   offers, pushes, outcomes, changed core truth, and unsaved work.
4. Ask once for final thought capture before closeout. Offer to save a brief
   research note only after operator approval.
5. Run crystallize when meaningful activity happened. Claude may use a Task
   subagent for deep crystallize; light sessions may use crystallize-lite.
6. Present save state before plumbing: drafted, saved locally, ready to send
   up, sent for review, landed in main, or blocked by unrelated cleanup.
7. Make checkpointing an approval-gated save. Validate the subject, ask before
   saving, and use `mb checkpoint`, not raw git commands.
8. End with a warm close: one sentence naming the most important saved or
   drafted business outcome, without tomorrow planning.

## Handoff Shape

```text
Closeout state: <one owner-facing save state>.
Status scan: <status/checkpoint/validate facts read>.
Session summary: <3-6 bullets or one compact paragraph>.
Final thought: <none, captured, or approved research note target>.
Crystallize: <deep, lite, skipped with reason>.
Checkpoint plan: <subject, changed surfaces, blockers, approval needed>.
Warm close: <one sentence>.
```

Use business language first. Git, branch, pull request, merge, and working-tree
details are secondary unless the operator asks for plumbing.
"""
    return output


def _render_end_codex_shell(workflow: WorkflowSource) -> str:
    """Render Codex CLI guidance for the closeout workflow."""

    output = f"""# Generated Codex Workflow Guidance: {workflow.title}

Source workflow: `{_display_path(workflow.path)}`
Runtime support: `codex_cli: {workflow.runtime_support.get("codex_cli", "")}`
Approval gates: {_inline_code_list(workflow.approval_gates)}
Public/private boundaries: {_inline_code_list(workflow.public_private_boundaries)}

Codex is first-class for the proven owner loop only. This guidance is generated
from the engine workflow source for business-repo `AGENTS.md`; the business repo
does not need to contain `{_display_path(workflow.path)}`. Treat this rendered
route as the Codex shell for natural-language closeout tasks. It does not claim
Claude Code runtime entrypoints work inside Codex or that all Main Branch
workflows are available in Codex.

## Required mb Commands

{_bullet_list(workflow.required_mb_commands)}

## Required JSON Fact Paths

{_bullet_list(workflow.json_facts)}

## Codex Route

Mid-session save vs close: if the operator only wants to save progress and keep
working — "save", "checkpoint this", "yes save" mid-flow — this is a save, not a
close. Run `mb checkpoint --plan`, save on approval through `mb checkpoint`, and
return them to work. Never save with raw git. Use the full closeout below only
when the session is actually ending or pausing.

1. Run a status scan first. Use deterministic status, checkpoint, validation,
   readiness, drift, recent-work, and runtime facts before reading raw git
   details.
2. Build the checkpoint plan from `mb checkpoint --plan --json`; use
   `mb validate --json` for blockers and cite `mb doctor repair --plan` when
   repairs are needed.
3. Give a short session summary in business language: decisions, research,
   offers, pushes, outcomes, changed core truth, and unsaved work.
4. Ask once for final thought capture before closeout. Offer to save a brief
   research note only after operator approval.
5. Run crystallize-lite in-thread when meaningful activity happened, or use
   available subagent tooling when the current Codex session supports it. If
   neither is available, name the limitation and still ask one specific
   crystallize question from the day's facts.
6. Present save state before plumbing: drafted, saved locally, ready to send
   up, sent for review, landed in main, or blocked by unrelated cleanup.
7. Make checkpointing an approval-gated save. Validate the subject, ask before
   saving, and use `mb checkpoint`, not raw git commands.
8. End with a warm close: one sentence naming the most important saved or
   drafted business outcome, without tomorrow planning.

## Handoff Shape

```text
Closeout state: <one owner-facing save state>.
Status scan: <status/checkpoint/validate facts read>.
Session summary: <3-6 bullets or one compact paragraph>.
Final thought: <none, captured, or approved research note target>.
Crystallize: <lite, subagent, or limitation named>.
Checkpoint plan: <subject, changed surfaces, blockers, approval needed>.
Warm close: <one sentence>.
```

Use business language first. Git, branch, pull request, merge, and working-tree
details are secondary unless the operator asks for plumbing. Do not tell Codex
users to run Claude Code entrypoints. Runtime smoke is required before docs say
this selected workflow is supported or available in Codex.
"""
    return output
