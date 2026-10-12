"""``mb validate`` — frontmatter and optional cross-reference checks.

Hard-coded schema per the master decision. Cross-reference validation is
opt-in because local authoring should warn by default and CI can opt into
strict mode. Per-file frontmatter errors always fail.

The schemas tolerate extras; only listed required keys are checked.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from mb import (
    content_strategy,
    file_contracts,
    github_activity,
    migration_lint,
    related_links,
    relationships,
    team,
    topology,
)
from mb import pushes as pushes_mod
from mb.engine import repo_flag

DECISION_STATUS = {"proposed", "accepted", "rejected", "superseded", "running"}
OFFER_STATUS = {
    "proposed",
    "running",
    "scaling",
    "killed",
    "graduated",
    "died",
    "accepted",
    "rejected",
}
RESEARCH_STATUS = {"complete", "in-progress", "stale"}
BET_STATUS = {"open", "paused", "closed", "canceled"}
CAMPAIGN_STATUS = pushes_mod.PUSH_STATUS
PUSH_KIND = pushes_mod.PUSH_KIND
PUSH_HEALTH = pushes_mod.PUSH_HEALTH
PLAYBOOK_STATUS = {
    "draft",
    "planned",
    "approved",
    "active",
    "paused",
    "completed",
    "canceled",
    "retired",
}
PLAYBOOK_PROVIDER_BOUNDARY = {
    "plan-only",
    "external-manual",
    "candidate-adapter",
    "accepted-adapter",
}
PLAYBOOK_APPROVAL_STATUS = {"not-required", "needed", "approved", "rejected"}
PLAYBOOK_RESOURCE_KIND = {"url", "file", "repo", "document", "manual", "none"}
PLAYBOOK_ACCEPTED_MUTATION_PROVIDERS: set[str] = set()
PLAYBOOK_PROVIDER_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
DATA_SOURCE_TYPE = "data_source"
DATA_SOURCE_PRIVACY = {"public", "team_private", "restricted", "local_only"}
DATA_SOURCE_CADENCE = {
    "realtime",
    "hourly",
    "daily",
    "weekly",
    "monthly",
    "quarterly",
    "ad_hoc",
    "manual",
}
DATA_SOURCE_PROVIDER_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
DATA_SOURCE_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TEAM_MEMBER_TYPE = "team_member"

TOPOLOGY_SCHEMA = {"mb.repo_topology.v0"}
TOPOLOGY_STATUS = {"proposed", "active", "paused", "superseded", "archived"}
# Single source of truth: the topology reader owns these vocabularies and the
# unsafe-key/secret matchers. Aliased here so validate and topology never drift.
TOPOLOGY_ROLE = topology.TOPOLOGY_ROLES
TOPOLOGY_VISIBILITY = topology.TOPOLOGY_VISIBILITIES
TOPOLOGY_RELATIONSHIP = {
    "hub_for",
    "child_of",
    "execution_vehicle_for",
    "graduated_from",
    "supersedes",
    "archived_from",
    "source_for",
    "reports_to",
    "uses_provider",
}
TOPOLOGY_LOCAL_LINK_FIELDS = {
    "linked_bets",
    "linked_decisions",
    "linked_documents",
    "linked_docs",
    "linked_logs",
    "linked_offers",
    "linked_outcomes",
    "linked_playbook_runs",
    "linked_pushes",
    "linked_research",
}
TOPOLOGY_LINK_PREFIXES = {
    "linked_bets": ("bets/",),
    "linked_decisions": ("decisions/",),
    "linked_documents": ("documents/",),
    "linked_docs": ("documents/",),
    "linked_logs": ("log/",),
    "linked_offers": ("core/offers/",),
    "linked_playbook_runs": ("pushes/",),
    "linked_pushes": ("pushes/",),
    "linked_research": ("research/",),
}
TOPOLOGY_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
GITHUB_OWNER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
GITHUB_REPO_RE = re.compile(r"^[A-Za-z0-9._-]+$")
DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,}$"
)
LOCAL_ABSOLUTE_PATH_RE = re.compile(r"^(?:/|~[/\\]|[A-Za-z]:[/\\])")
TOPOLOGY_UNSAFE_KEY_RE = topology.UNSAFE_KEY_RE
SECRET_KEY_RE = topology.SECRET_KEY_RE
SECRET_VALUE_RE = re.compile(
    r"(-----BEGIN [A-Z ]*PRIVATE KEY-----|bearer\s+[A-Za-z0-9._~+/=-]{10,}|"
    r"gh[pousr]_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{10,}|"
    r"xox[baprs]-[A-Za-z0-9-]{10,}|api[_-]?key\s*[:=])",
    re.IGNORECASE,
)

LINK_FIELDS = relationships.RELATIONSHIP_FIELDS

VALIDATION_CATEGORY_REPAIR: dict[str, str] = {
    "missing_slug": "Add stable kebab-case `slug:` values that name the thing sold or worked on.",
    "missing_required_key": "Add the missing required frontmatter keys for this record type.",
    "status_enum_mismatch": "Change `status:` to one of the allowed lifecycle values.",
    "enum_mismatch": "Change the value to one of the allowed schema values.",
    "no_frontmatter": "Add YAML frontmatter bounded by `---` at the top of the file.",
    "yaml_error": "Fix malformed YAML before repairing schema fields.",
    "schema_shape_error": "Fix nested mappings and field shapes before rerunning validation.",
    "missing_cross_ref_target": "Repair, remove, or intentionally archive broken local links.",
    related_links.MISSING_RELATED_LINK_MIRROR_CATEGORY: (
        "Run `mb doctor repair --plan`, review the Related links mirror action, "
        "then `mb doctor repair --apply` after approval."
    ),
    "missing_reverse_link": "Add the suggested reverse relationship field after operator approval.",
    "migration_drift": "Run `mb doctor repair --plan --json` and review stale layout guidance.",
    "file_contract_missing_section": (
        "Use the recommended Main Branch route to fill the missing business shape."
    ),
    "file_contract_empty_section": (
        "Add enough detail for this section to guide the next business workflow."
    ),
    "other_error": "Review the validation message and repair the affected record.",
    "other_warning": (
        "Review the warning and decide whether the relationship or file shape is intentional."
    ),
    "duplicate_github_handle": "Use each GitHub handle in only one core/team/<slug>.md file.",
    "unnormalized_github_handle": "Store GitHub handles without @, URLs, or uppercase letters.",
}

# Audience routing per category. See decision
# decisions/2026-05-11-operator-facing-gitops-and-migration-planning.md.
# Categories absent from this map default to "operator_decision".
VALIDATION_CATEGORY_AUDIENCE: dict[str, str] = {
    related_links.MISSING_RELATED_LINK_MIRROR_CATEGORY: "mechanical",
    "migration_drift": "mechanical",
}

# Operator-facing summaries. Default to the existing repair string when no
# separate plain-language framing exists.
VALIDATION_CATEGORY_OPERATOR_SUMMARY: dict[str, str] = {
    "missing_slug": "Name the thing this file is about so other notes can link to it.",
    "missing_required_key": "Fill in the few required fields this kind of file expects.",
    "status_enum_mismatch": "Pick a status this kind of file allows.",
    "enum_mismatch": "Pick one of the allowed values for this field.",
    "no_frontmatter": "Add the YAML header at the top of the file.",
    "yaml_error": "Fix the YAML formatting at the top before anything else can be checked.",
    "schema_shape_error": "Reshape the YAML fields so they match the expected layout.",
    "missing_cross_ref_target": (
        "Fix the broken link, remove it, or mark it as intentionally archived."
    ),
    related_links.MISSING_RELATED_LINK_MIRROR_CATEGORY: (
        "Main Branch can repair this automatically — run `mb doctor repair --plan` then `--apply`."
    ),
    "missing_reverse_link": "Decide whether to add the reverse link the suggestion proposes.",
    "migration_drift": (
        "Main Branch can repair this automatically — run `mb doctor repair --plan` then `--apply`."
    ),
    "file_contract_missing_section": (
        "A business file is missing context needed for the next workflow."
    ),
    "file_contract_empty_section": (
        "A business file has the right section name, but not enough useful detail."
    ),
    "other_error": "Read the validation message and decide how to fix the file.",
    "other_warning": "Decide whether the relationship or shape is intentional, or change it.",
    "duplicate_github_handle": "One GitHub handle points to more than one team member.",
    "unnormalized_github_handle": "Normalize the GitHub handle before agents rely on it.",
}

VALIDATION_CATEGORY_ROUTE: dict[str, str] = {
    "file_contract_missing_section": "mb-think",
    "file_contract_empty_section": "mb-think",
}

DECISION_STATUS_ORDER = {
    "proposed": 0,
    "running": 1,
    "accepted": 2,
    "rejected": 2,
    "superseded": 2,
}
OFFER_STATUS_ORDER = {
    "proposed": 0,
    "running": 1,
    "accepted": 1,
    "rejected": 1,
    "scaling": 2,
    "killed": 3,
    "graduated": 3,
    "died": 3,
}
CAMPAIGN_STATUS_ORDER = {
    "draft": 0,
    "planned": 1,
    "active": 2,
    "paused": 2,
    "completed": 3,
    "canceled": 3,
    "archived": 4,
}

SCHEMAS: dict[str, dict[str, Any]] = {
    "decisions": {
        "glob": "decisions/*.md",
        "required": ["date", "status"],
        "enums": {"status": DECISION_STATUS},
    },
    "core/offers": {
        "glob": "core/offers/*/offer.md",
        "required": ["slug", "status"],
        "enums": {"status": OFFER_STATUS},
    },
    "research": {
        "glob": "research/*.md",
        "required": ["date", "topic", "source"],
        "enums": {},
    },
    "bets": {
        "glob": "bets/*.md",
        # Current bets use `linked_pushes`; legacy bets may still have only
        # `linked_campaigns`. _check_bet_frontmatter enforces that at least one
        # campaign/push link field exists without requiring the legacy field.
        "required": [
            "status",
            "opened",
            "deadline",
            "appetite",
            "hypothesis",
            "metric",
            "target",
            "result",
            "linked_decisions",
            "linked_research",
            "linked_outcomes",
            "public",
            "channels",
            "tags",
        ],
        "enums": {"status": BET_STATUS},
        "primitive": "bet",
    },
    "log": {
        "glob": "log/*.md",
        "required": ["date"],
        "enums": {},
    },
    "campaigns": {
        "glob": "campaigns/*/campaign.md",
        "required": ["slug", "status"],
        "enums": {"status": CAMPAIGN_STATUS},
        "primitive": "legacy-campaign",
    },
    "pushes": {
        "glob": "pushes/*/push.md",
        "required": [
            "type",
            "slug",
            "kind",
            "status",
            "health",
            "goal",
            "owner",
            "audience",
            "offer",
            "promise",
        ],
        "enums": {"kind": PUSH_KIND, "status": CAMPAIGN_STATUS, "health": PUSH_HEALTH},
        "primitive": "push",
    },
    "push-playbooks": {
        "glob": "pushes/*/playbooks/*.md",
        "required": [
            "type",
            "status",
            "push",
            "platform",
            "provider",
            "provider_boundary",
            "trigger",
            "resource",
            "approval",
            "state",
            "validation",
            "linked_outcomes",
        ],
        "enums": {
            "status": PLAYBOOK_STATUS,
            "provider_boundary": PLAYBOOK_PROVIDER_BOUNDARY,
        },
        "primitive": "playbook",
    },
    "repo-topology": {
        "glob": "core/operations/repo-topology.md",
        "required": ["type", "schema", "business_display_name", "repos"],
        "enums": {"type": {"repo_topology"}, "schema": TOPOLOGY_SCHEMA},
        "primitive": "repo-topology",
    },
    "documents": {
        "glob": "documents/*.md",
        "required": ["title"],
        "enums": {},
    },
    "data-sources": {
        "glob": "data/*/source.md",
        "required": ["type", "provider", "owner", "privacy"],
        "enums": {"type": {DATA_SOURCE_TYPE}, "privacy": DATA_SOURCE_PRIVACY},
        "primitive": "data-source",
    },
    "team-members": {
        "glob": "core/team/*.md",
        "required": ["type", "slug", "name", "relationship"],
        "enums": {"type": {TEAM_MEMBER_TYPE}, "relationship": team.RELATIONSHIPS},
        "primitive": "team-member",
    },
}


def _read_frontmatter(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    """Return (frontmatter dict, error). Either may be None."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"unreadable: {exc}"
    if not text.startswith("---"):
        return None, "no frontmatter"
    try:
        end = text.index("\n---", 3)
    except ValueError:
        return None, "unterminated frontmatter"
    body = text[3:end].lstrip("\n")
    try:
        data = yaml.safe_load(body) or {}
    except yaml.YAMLError as exc:
        return None, f"yaml error: {exc}"
    if not isinstance(data, dict):
        return None, "frontmatter not a mapping"
    return data, None


def _check_one(path: Path, schema: dict[str, Any]) -> dict[str, Any]:
    fm, err = _read_frontmatter(path)
    if err is not None:
        return {"path": str(path), "ok": False, "errors": [err], "warnings": []}
    assert fm is not None
    errors: list[str] = []
    warnings: list[str] = []
    for k in schema["required"]:
        if k not in fm:
            errors.append(f"missing key: {k}")
    for k, allowed in schema.get("enums", {}).items():
        if k in fm and fm[k] not in allowed:
            errors.append(f"{k}={fm[k]!r} not in {sorted(allowed)}")
    primitive = schema.get("primitive")
    if primitive == "push":
        _check_push_frontmatter(path, fm, errors)
    elif primitive == "bet":
        _check_bet_frontmatter(path, fm, errors, warnings)
    elif primitive == "playbook":
        _check_playbook_frontmatter(path, fm, errors)
    elif primitive == "legacy-campaign":
        _check_legacy_campaign_frontmatter(fm, errors)
    elif primitive == "repo-topology":
        _check_repo_topology_frontmatter(path, fm, errors, warnings)
    elif primitive == "data-source":
        _check_data_source_frontmatter(path, fm, errors, warnings)
    elif primitive == "team-member":
        _check_team_member_frontmatter(path, fm, errors, warnings)
    _check_provider_refs_shape(fm, errors)
    return {"path": str(path), "ok": not errors, "errors": errors, "warnings": warnings}


BET_APPETITE_TIERS = {"trivial", "small", "material", "strategic"}
BET_ANCHOR_REQUIRED_BEFORE = {"planning", "execution", "spend", "launch", "none"}
BET_SIGNAL_COMPARATORS = {"<", "<=", "==", ">=", ">", "!="}
BET_SIGNAL_ACTIONS = {"kill", "double_down", "review"}
BET_OWNER_REF_RE = re.compile(r"^core/team/[a-z0-9][a-z0-9-]*\.md$")
BET_STAGE = {"tuning", "working", "ongoing", "done", "cut"}
BET_STAGE_ENDED = {"done", "cut"}
BET_ACTIVE_STATUS = {"open", "paused"}
BET_ENDED_STATUS = {"closed", "canceled"}
BET_COMMITMENT_CADENCE = {"daily", "weekdays", "weekly"}
BET_COMMITMENT_EVIDENCE = {"url", "commit", "send_id", "file", "other"}


def _check_bet_frontmatter(
    path: Path,
    fm: dict[str, Any],
    errors: list[str],
    warnings: list[str],
) -> None:
    if "linked_pushes" not in fm and "linked_campaigns" not in fm:
        errors.append("missing key: linked_pushes or linked_campaigns")
    appetite_tier = fm.get("appetite_tier")
    if appetite_tier is not None and appetite_tier not in BET_APPETITE_TIERS:
        warnings.append(
            f"appetite_tier={appetite_tier!r} is not one of {sorted(BET_APPETITE_TIERS)}"
        )
    _check_bet_owner(fm, warnings)
    _check_bet_stage(fm, errors, warnings)
    _check_bet_commitment(fm, errors)
    _check_bet_money_path(path, fm, warnings)
    _check_bet_kill_rubric(fm, warnings)


def _check_bet_stage(fm: dict[str, Any], errors: list[str], warnings: list[str]) -> None:
    if "stage" not in fm:
        return
    stage = fm["stage"]
    if not isinstance(stage, str) or stage not in BET_STAGE:
        errors.append(f"stage={stage!r} not in {sorted(BET_STAGE)}")
        return
    status = fm.get("status")
    if stage in BET_STAGE_ENDED and status in BET_ACTIVE_STATUS:
        warnings.append(f"stage={stage!r} but status={status!r}; close or cancel the bet to match")
    elif stage not in BET_STAGE_ENDED and status in BET_ENDED_STATUS:
        warnings.append(f"stage={stage!r} but status={status!r}; set stage to done or cut")


def _check_bet_commitment(fm: dict[str, Any], errors: list[str]) -> None:
    if "commitment" not in fm:
        return
    commitment = fm["commitment"]
    if not isinstance(commitment, dict):
        errors.append("commitment must be a mapping with action, cadence and evidence")
        return
    action = commitment.get("action")
    if not isinstance(action, str) or not action.strip():
        errors.append("commitment.action must be a non-empty string")
    if "owner" in commitment and (
        not isinstance(commitment["owner"], str) or not commitment["owner"].strip()
    ):
        errors.append("commitment.owner must be a non-empty string when present")
    for key, allowed in (
        ("cadence", BET_COMMITMENT_CADENCE),
        ("evidence", BET_COMMITMENT_EVIDENCE),
    ):
        value = commitment.get(key)
        if value is None:
            errors.append(f"missing key: commitment.{key} (one of {sorted(allowed)})")
        elif not isinstance(value, str) or value not in allowed:
            errors.append(f"commitment.{key}={value!r} not in {sorted(allowed)}")


def _check_bet_owner(fm: dict[str, Any], warnings: list[str]) -> None:
    owner = fm.get("owner")
    if owner is None:
        return
    if not isinstance(owner, str) or not owner.strip():
        warnings.append("owner should be a team member slug matching core/team/<slug>.md")
        return
    owner_ref = owner.strip()
    if "/" in owner_ref and not BET_OWNER_REF_RE.fullmatch(owner_ref):
        warnings.append("owner path references should use core/team/<slug>.md")


def _check_bet_money_path(path: Path, fm: dict[str, Any], warnings: list[str]) -> None:
    money_path = fm.get("money_path")
    if money_path is None:
        return
    if not isinstance(money_path, dict):
        warnings.append("money_path must be a mapping when declared")
        return
    required = money_path.get("required")
    if required is not None and not isinstance(required, bool):
        warnings.append("money_path.required should be true or false")
    bet_id = money_path.get("bet_id")
    if bet_id is not None:
        if not isinstance(bet_id, str) or not bet_id.strip():
            warnings.append("money_path.bet_id must be a non-empty string")
        elif bet_id.strip() != path.stem:
            warnings.append("money_path.bet_id should match the bet filename stem")
    elif required is True:
        warnings.append("money_path.required is true but money_path.bet_id is missing")
    anchor_required_before = money_path.get("anchor_required_before")
    if (
        anchor_required_before is not None
        and anchor_required_before not in BET_ANCHOR_REQUIRED_BEFORE
    ):
        warnings.append(
            "money_path.anchor_required_before should be one of "
            f"{sorted(BET_ANCHOR_REQUIRED_BEFORE)}"
        )
    exposure_cap = money_path.get("exposure_cap")
    if exposure_cap is None:
        return
    if not isinstance(exposure_cap, dict):
        warnings.append("money_path.exposure_cap must be a mapping with amount and currency")
        return
    amount = exposure_cap.get("amount")
    if not isinstance(amount, int | float) or isinstance(amount, bool) or amount < 0:
        warnings.append("money_path.exposure_cap.amount must be a non-negative number")
    currency = exposure_cap.get("currency")
    if not isinstance(currency, str) or not currency.strip():
        warnings.append("money_path.exposure_cap.currency must be a non-empty string")


def _check_bet_kill_rubric(fm: dict[str, Any], warnings: list[str]) -> None:
    rubric = fm.get("kill_rubric")
    if rubric is None:
        return
    if not isinstance(rubric, dict):
        warnings.append("kill_rubric must be a mapping when declared")
        return
    for key, expected_action in (
        ("failure_signals", "kill"),
        ("double_down_signals", "double_down"),
    ):
        signals = rubric.get(key)
        if signals is None:
            continue
        if not isinstance(signals, list):
            warnings.append(f"kill_rubric.{key} must be a list")
            continue
        for index, signal in enumerate(signals):
            prefix = f"kill_rubric.{key}[{index}]"
            if not isinstance(signal, dict):
                warnings.append(f"{prefix} must be a mapping")
                continue
            for field in ("id", "metric", "comparator", "threshold", "action"):
                if field not in signal:
                    warnings.append(f"{prefix}.{field} is missing")
            comparator = signal.get("comparator")
            if comparator is not None and comparator not in BET_SIGNAL_COMPARATORS:
                warnings.append(
                    f"{prefix}.comparator={comparator!r} is not one of "
                    f"{sorted(BET_SIGNAL_COMPARATORS)}"
                )
            action = signal.get("action")
            if action is not None and action not in BET_SIGNAL_ACTIONS:
                warnings.append(
                    f"{prefix}.action={action!r} is not one of {sorted(BET_SIGNAL_ACTIONS)}"
                )
            elif action is not None and action != expected_action:
                warnings.append(f"{prefix}.action is usually {expected_action!r}")
            threshold = signal.get("threshold")
            if threshold is not None and not isinstance(threshold, int | float | str):
                warnings.append(f"{prefix}.threshold should be a number or string")


def _require_non_empty_string(fm: dict[str, Any], key: str, errors: list[str]) -> None:
    if key not in fm:
        return
    value = fm.get(key)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{key} must be a non-empty string")


def _scalar_as_string(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    iso_method = getattr(value, "isoformat", None)
    if callable(iso_method):
        iso = iso_method()
        return iso.strip() if isinstance(iso, str) else ""
    if isinstance(value, int | float):
        return str(value)
    return ""


def _check_push_frontmatter(path: Path, fm: dict[str, Any], errors: list[str]) -> None:
    if not pushes_mod.PUSH_FOLDER_RE.fullmatch(path.parent.name):
        errors.append("push folder must match YYYY-MM-DD-slug")
    if fm.get("type") != "push":
        errors.append("type must be 'push'")
    for key in ("slug", "kind", "status", "health", "owner", "audience", "offer", "promise"):
        _require_non_empty_string(fm, key, errors)
    promise = fm.get("promise")
    if isinstance(promise, str) and len(promise.strip()) > 140:
        errors.append("promise must be 140 characters or fewer")
    media_location = fm.get("media_location")
    if "media_location" in fm and not (isinstance(media_location, str) and media_location.strip()):
        errors.append("media_location must be a non-empty string when present")
    if "media_backend" in fm:
        media_backend = fm.get("media_backend")
        if not (isinstance(media_backend, str) and media_backend.strip()):
            errors.append("media_backend must be a non-empty string when present")
        elif not (isinstance(media_location, str) and media_location.strip()):
            errors.append(
                "media_backend is set but media_location is missing — "
                "record where the finished creative lives"
            )
    goal = fm.get("goal")
    if "goal" not in fm:
        return
    if not isinstance(goal, dict):
        errors.append("goal must be a mapping with metric, target, and by")
        return
    for key in ("metric", "target", "by"):
        value = _scalar_as_string(goal.get(key))
        if not value:
            errors.append(f"goal.{key} must be a non-empty string")
    by = _scalar_as_string(goal.get("by"))
    if by and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", by):
        errors.append("goal.by must be YYYY-MM-DD")


def _require_mapping(fm: dict[str, Any], key: str, errors: list[str]) -> dict[str, Any] | None:
    if key not in fm:
        return None
    value = fm.get(key)
    if not isinstance(value, dict):
        errors.append(f"{key} must be a mapping")
        return None
    return value


def _mapping_value_as_string(mapping: dict[str, Any], key: str) -> str:
    value = mapping.get(key)
    return value.strip() if isinstance(value, str) else ""


def _require_mapping_string(
    mapping: dict[str, Any],
    key: str,
    errors: list[str],
    *,
    prefix: str,
) -> str:
    value = _mapping_value_as_string(mapping, key)
    if not value:
        errors.append(f"{prefix}.{key} must be a non-empty string")
    return value


def _check_playbook_push_link(path: Path, fm: dict[str, Any], errors: list[str]) -> None:
    push_folder = path.parent.parent
    if path.parent.name != "playbooks" or push_folder.parent.name != "pushes":
        errors.append("playbook files must live under pushes/<YYYY-MM-DD-slug>/playbooks/")
        return
    if not pushes_mod.PUSH_FOLDER_RE.fullmatch(push_folder.name):
        errors.append("playbook push folder must match YYYY-MM-DD-slug")
    raw_push = fm.get("push")
    if not isinstance(raw_push, str) or not raw_push.strip():
        if "push" in fm:
            errors.append("push must link to the containing push.md")
        return
    clean_push = relationships.clean_ref(raw_push)
    if not clean_push:
        errors.append("push must link to the containing push.md")
        return
    repo = push_folder.parent.parent
    if clean_push.startswith("pushes/"):
        target = (repo / clean_push).resolve()
    else:
        target = (path.parent / clean_push).resolve()
    expected = (push_folder / "push.md").resolve()
    if target != expected:
        errors.append("push must link to the containing push.md")
    if not expected.exists():
        errors.append("push target does not exist")


def _iter_secret_paths(value: Any, prefix: str = "") -> list[str]:
    findings: list[str] = []
    if isinstance(value, dict):
        for key, nested in value.items():
            key_text = str(key)
            path = f"{prefix}.{key_text}" if prefix else key_text
            if SECRET_KEY_RE.search(key_text):
                findings.append(path)
            findings.extend(_iter_secret_paths(nested, path))
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            path = f"{prefix}[{index}]" if prefix else f"[{index}]"
            findings.extend(_iter_secret_paths(nested, path))
    elif isinstance(value, str) and SECRET_VALUE_RE.search(value):
        findings.append(prefix or "<value>")
    return findings


def _check_playbook_frontmatter(path: Path, fm: dict[str, Any], errors: list[str]) -> None:
    _check_playbook_push_link(path, fm, errors)
    if fm.get("type") != "playbook":
        errors.append("type must be 'playbook'")
    for key in ("platform", "provider", "provider_boundary"):
        _require_non_empty_string(fm, key, errors)

    provider = fm.get("provider")
    if isinstance(provider, str) and provider.strip():
        provider_id = provider.strip()
        if not PLAYBOOK_PROVIDER_RE.fullmatch(provider_id):
            errors.append("provider must be a lowercase hyphenated provider id")
        if (
            fm.get("provider_boundary") == "accepted-adapter"
            and provider_id not in PLAYBOOK_ACCEPTED_MUTATION_PROVIDERS
        ):
            errors.append(
                "provider_boundary=accepted-adapter requires a tested Main Branch provider adapter"
            )

    trigger = _require_mapping(fm, "trigger", errors)
    if trigger is not None:
        trigger_kind = _require_mapping_string(trigger, "kind", errors, prefix="trigger")
        if trigger_kind in {"comment_keyword", "dm_keyword"}:
            _require_mapping_string(trigger, "keyword", errors, prefix="trigger")

    resource = _require_mapping(fm, "resource", errors)
    if resource is not None:
        resource_kind = _require_mapping_string(resource, "kind", errors, prefix="resource")
        if resource_kind and resource_kind not in PLAYBOOK_RESOURCE_KIND:
            errors.append(
                f"resource.kind={resource_kind!r} not in {sorted(PLAYBOOK_RESOURCE_KIND)}"
            )
        if resource_kind != "none":
            _require_mapping_string(resource, "value", errors, prefix="resource")

    approval = _require_mapping(fm, "approval", errors)
    if approval is not None:
        if not isinstance(approval.get("required"), bool):
            errors.append("approval.required must be true or false")
        status = _require_mapping_string(approval, "status", errors, prefix="approval")
        if status and status not in PLAYBOOK_APPROVAL_STATUS:
            errors.append(f"approval.status={status!r} not in {sorted(PLAYBOOK_APPROVAL_STATUS)}")

    state = _require_mapping(fm, "state", errors)
    if state is not None and "provider_refs" in state:
        provider_refs = state.get("provider_refs")
        if not isinstance(provider_refs, dict | list) and provider_refs is not None:
            errors.append("state.provider_refs must be a mapping, list, or null")

    validation = _require_mapping(fm, "validation", errors)
    if validation is not None:
        if "dry_run" not in validation:
            errors.append("validation.dry_run must be recorded")
        if "smoke_evidence" not in validation:
            errors.append("validation.smoke_evidence must be recorded")

    refs, valid_refs = _coerce_refs(fm.get("linked_outcomes"))
    if "linked_outcomes" in fm and not valid_refs:
        errors.append("linked_outcomes must be a string or list of strings")
    if any(ref.strip().lower().startswith(("http://", "https://")) for ref in refs):
        errors.append("linked_outcomes should point to repo outcome/log files, not external URLs")

    secret_paths = sorted(set(_iter_secret_paths(fm)))
    if secret_paths:
        errors.append("playbook frontmatter must not contain secrets: " + ", ".join(secret_paths))


def _check_legacy_campaign_frontmatter(fm: dict[str, Any], errors: list[str]) -> None:
    record_type = fm.get("type")
    if record_type is not None and record_type not in {"campaign", "push"}:
        errors.append("type must be 'campaign' or 'push' for legacy campaign records")


def _check_data_source_frontmatter(
    path: Path,
    fm: dict[str, Any],
    errors: list[str],
    warnings: list[str],
) -> None:
    if fm.get("type") != DATA_SOURCE_TYPE:
        errors.append(f"type must be {DATA_SOURCE_TYPE!r}")

    _require_non_empty_string(fm, "provider", errors)
    provider = fm.get("provider")
    if isinstance(provider, str) and provider.strip():
        provider_id = provider.strip()
        if not DATA_SOURCE_PROVIDER_RE.fullmatch(provider_id):
            errors.append("provider must be a lowercase id using letters, digits, '-' or '_'")
        else:
            folder = path.parent.name
            if folder != provider_id:
                warnings.append(
                    f"provider {provider_id!r} does not match the parent folder {folder!r}; "
                    "data records are usually data/<provider>/source.md"
                )

    _require_non_empty_string(fm, "owner", errors)

    cadence = fm.get("cadence")
    if isinstance(cadence, str) and cadence.strip() and cadence.strip() not in DATA_SOURCE_CADENCE:
        warnings.append(
            f"cadence={cadence!r} is not one of the conventional values "
            f"{sorted(DATA_SOURCE_CADENCE)}; agents may not interpret it consistently"
        )

    freshness = _scalar_as_string(fm.get("freshness"))
    if "freshness" in fm and freshness and not DATA_SOURCE_DATE_RE.fullmatch(freshness):
        errors.append("freshness must be a YYYY-MM-DD date")

    if "storage" in fm:
        storage = fm.get("storage")
        if not isinstance(storage, dict):
            errors.append("storage must be a mapping with 'primary' and optional 'snapshots'")
        else:
            primary = storage.get("primary")
            if primary is not None and (not isinstance(primary, str) or not primary.strip()):
                errors.append("storage.primary must be a non-empty path string when present")
            elif isinstance(primary, str) and LOCAL_ABSOLUTE_PATH_RE.search(primary.strip()):
                errors.append(
                    "storage.primary must be a repo-relative path; "
                    "machine-specific absolute paths are not portable"
                )
            snapshots = storage.get("snapshots")
            if snapshots is not None and (
                not isinstance(snapshots, list)
                or not all(isinstance(item, str) and item.strip() for item in snapshots)
            ):
                errors.append("storage.snapshots must be a list of non-empty path strings")
            elif isinstance(snapshots, list):
                for index, snapshot in enumerate(snapshots):
                    if isinstance(snapshot, str) and LOCAL_ABSOLUTE_PATH_RE.search(
                        snapshot.strip()
                    ):
                        errors.append(
                            f"storage.snapshots[{index}] must be a repo-relative path; "
                            "machine-specific absolute paths are not portable"
                        )

    for ref_field in ("reports", "useful_queries"):
        if ref_field not in fm:
            continue
        value = fm.get(ref_field)
        if ref_field == "reports":
            if not isinstance(value, list) or not all(
                isinstance(item, str) and item.strip() for item in value
            ):
                errors.append("reports must be a list of non-empty path strings")
            else:
                for index, report in enumerate(value):
                    if LOCAL_ABSOLUTE_PATH_RE.search(report.strip()):
                        errors.append(
                            f"reports[{index}] must be a repo-relative path; "
                            "machine-specific absolute paths are not portable"
                        )
        else:
            if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
                errors.append("useful_queries must be a list of mappings")
                continue
            for index, item in enumerate(value):
                if not isinstance(item.get("name"), str) or not item.get("name").strip():
                    errors.append(f"useful_queries[{index}].name must be a non-empty string")
                if not isinstance(item.get("query"), str) or not item.get("query").strip():
                    errors.append(f"useful_queries[{index}].query must be a non-empty string")

    secret_paths = sorted(set(_iter_secret_paths(fm)))
    if secret_paths:
        errors.append(
            "data-source frontmatter must not contain secrets: " + ", ".join(secret_paths)
        )


def _check_team_member_frontmatter(
    path: Path,
    fm: dict[str, Any],
    errors: list[str],
    warnings: list[str],
) -> None:
    if fm.get("type") != TEAM_MEMBER_TYPE:
        errors.append(f"type must be {TEAM_MEMBER_TYPE!r}")
    if not team.SLUG_RE.fullmatch(path.stem):
        errors.append("team member filename must be a lowercase slug")
    slug = fm.get("slug")
    if isinstance(slug, str) and slug.strip() and slug.strip() != path.stem:
        errors.append("slug must match the core/team/<slug>.md filename")
    _require_non_empty_string(fm, "name", errors)

    github = fm.get("github")
    raw_handles: list[str] = []
    if github is None:
        raw_handles = []
    elif isinstance(github, str):
        raw_handles = [github]
    elif isinstance(github, list) and all(isinstance(item, str) for item in github):
        raw_handles = [str(item) for item in github]
    else:
        errors.append("github must be a string or list of strings")

    seen_handles: set[str] = set()
    for raw_handle in raw_handles:
        normalized = team.normalize_github_handle(raw_handle)
        if not normalized:
            errors.append(f"github handle {raw_handle!r} is not valid")
            continue
        if raw_handle.strip() != normalized:
            errors.append(f"github handle {raw_handle!r} must be normalized as {normalized!r}")
        if normalized in seen_handles:
            errors.append(f"duplicate github handle {normalized!r} in this team member")
        seen_handles.add(normalized)

    areas = fm.get("areas")
    if areas is not None and (
        not isinstance(areas, list)
        or not all(isinstance(item, str) and item.strip() for item in areas)
    ):
        errors.append("areas must be a list of non-empty strings")

    secret_paths = sorted(set(_iter_secret_paths(fm)))
    if secret_paths:
        errors.append(
            "team member frontmatter must not contain secrets: " + ", ".join(secret_paths)
        )

    sensitive_keys = sorted(
        key
        for key in fm
        if isinstance(key, str)
        and re.search(r"(home|birthday|birthdate|ssn|compensation|payroll)", key, re.IGNORECASE)
    )
    if sensitive_keys:
        warnings.append(
            "team member frontmatter should avoid sensitive personal fields: "
            + ", ".join(sensitive_keys)
        )


def _check_provider_refs_shape(fm: dict[str, Any], errors: list[str]) -> None:
    if "provider_refs" not in fm:
        return
    provider_refs = fm.get("provider_refs")
    if not isinstance(provider_refs, dict):
        errors.append("provider_refs must be a mapping of provider names to non-secret refs")
        return
    for provider, refs in provider_refs.items():
        if not isinstance(provider, str) or not provider.strip():
            errors.append("provider_refs provider names must be non-empty strings")
            continue
        if refs is None:
            continue
        if isinstance(refs, dict):
            if not all(isinstance(key, str) and key.strip() for key in refs):
                errors.append(f"provider_refs.{provider} ref names must be non-empty strings")
            continue
        if isinstance(refs, list):
            if not all(isinstance(item, dict) for item in refs):
                errors.append(f"provider_refs.{provider} must be a mapping or list of mappings")
                continue
            invalid_keys = [
                key for item in refs for key in item if not isinstance(key, str) or not key.strip()
            ]
            if invalid_keys:
                errors.append(f"provider_refs.{provider} ref names must be non-empty strings")
            continue
        errors.append(f"provider_refs.{provider} must be a mapping or list of mappings")


def _topology_repo_root(path: Path) -> Path:
    # core/operations/repo-topology.md -> repo root
    return path.parent.parent.parent


def _github_ref_full_name(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    ref = value.strip()
    if ref.startswith("github:"):
        full_name = ref.removeprefix("github:").strip()
        return full_name if _valid_github_full_name(full_name) else ""
    return github_activity.repo_full_name(ref)


def _valid_github_full_name(value: str) -> bool:
    parts = value.split("/", 1)
    if len(parts) != 2:
        return False
    owner, repo = parts
    return bool(GITHUB_OWNER_RE.fullmatch(owner) and GITHUB_REPO_RE.fullmatch(repo))


def _require_topology_repo_string(
    repo_entry: dict[str, Any],
    key: str,
    errors: list[str],
    *,
    prefix: str,
) -> str:
    value = repo_entry.get(key)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{prefix}.{key} must be a non-empty string")
        return ""
    return value.strip()


def _topology_refs(value: Any, errors: list[str], *, field: str, prefix: str) -> list[str]:
    refs, valid_type = _coerce_refs(value)
    if not valid_type:
        errors.append(f"{prefix}.{field} must be a string or list of strings")
        return []
    return [ref.strip() for ref in refs if ref.strip()]


def _warn_topology_unsafe_paths(value: Any, warnings: list[str], prefix: str = "") -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            key_text = str(key)
            path = f"{prefix}.{key_text}" if prefix else key_text
            if SECRET_KEY_RE.search(key_text) or TOPOLOGY_UNSAFE_KEY_RE.search(key_text):
                warnings.append(
                    f"{path} looks like sensitive or local-only metadata; keep raw finance, "
                    "legal, customer, provider-cache, credential, and local-path details out "
                    "of repo topology"
                )
            _warn_topology_unsafe_paths(nested, warnings, path)
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            path = f"{prefix}[{index}]" if prefix else f"[{index}]"
            _warn_topology_unsafe_paths(nested, warnings, path)
    elif isinstance(value, str) and LOCAL_ABSOLUTE_PATH_RE.search(value.strip()):
        warnings.append(
            f"{prefix or '<value>'} looks like a local absolute path; keep durable topology "
            "on GitHub handles and business relationships, not machine-specific paths"
        )


def _check_topology_local_link(
    *,
    repo: Path,
    source: Path,
    field: str,
    ref: str,
    errors: list[str],
    warnings: list[str],
    prefix: str,
) -> None:
    if relationships.is_external_ref(ref):
        return
    clean_ref = relationships.clean_ref(ref)
    if not clean_ref:
        return
    if field == "linked_playbook_runs" and not re.fullmatch(
        r"pushes/[^/]+/playbooks/[^/]+\.md", clean_ref
    ):
        errors.append(f"{prefix}.{field} must point to pushes/<push>/playbooks/<playbook>.md")
    allowed_prefixes = TOPOLOGY_LINK_PREFIXES.get(field)
    if allowed_prefixes and not clean_ref.startswith(allowed_prefixes):
        errors.append(f"{prefix}.{field} target {ref!r} must live under {allowed_prefixes}")
        return
    if not relationships.is_local_markdown_ref(clean_ref):
        warnings.append(
            f"{prefix}.{field} target {ref!r} is not a local markdown file Main Branch can check"
        )
        return
    target = relationships.resolve_markdown_link(repo, source, clean_ref)
    if target is None:
        warnings.append(f"{prefix}.{field} target {ref!r} does not resolve to a markdown file")


def _check_repo_topology_frontmatter(
    path: Path,
    fm: dict[str, Any],
    errors: list[str],
    warnings: list[str],
) -> None:
    if fm.get("type") != "repo_topology":
        errors.append("type must be 'repo_topology'")
    _require_non_empty_string(fm, "business_display_name", errors)

    if "status" in fm and fm.get("status") not in TOPOLOGY_STATUS:
        errors.append(f"topology status={fm.get('status')!r} not in {sorted(TOPOLOGY_STATUS)}")

    home = fm.get("home")
    if home is not None and (not isinstance(home, str) or not _github_ref_full_name(home)):
        errors.append("home must be a GitHub handle such as github:owner/repo")

    repos = fm.get("repos")
    if not isinstance(repos, list) or not repos:
        errors.append("repos must be a non-empty list of repo mappings")
        return
    if not all(isinstance(repo_entry, dict) for repo_entry in repos):
        errors.append("repos must contain only mappings")
        return

    slugs: set[str] = {
        str(repo_entry.get("slug")).strip()
        for repo_entry in repos
        if isinstance(repo_entry.get("slug"), str) and repo_entry.get("slug").strip()
    }
    if len(slugs) != sum(
        1
        for repo_entry in repos
        if isinstance(repo_entry.get("slug"), str) and repo_entry.get("slug").strip()
    ):
        errors.append("repos.slug values must be unique")

    repo_root = _topology_repo_root(path)
    for index, repo_entry in enumerate(repos):
        prefix = f"repos[{index}]"
        slug = _require_topology_repo_string(repo_entry, "slug", errors, prefix=prefix)
        if slug and not TOPOLOGY_SLUG_RE.fullmatch(slug):
            errors.append(f"{prefix}.slug must be lowercase hyphenated")
        _require_topology_repo_string(repo_entry, "display_name", errors, prefix=prefix)

        role = _require_topology_repo_string(repo_entry, "role", errors, prefix=prefix)
        if role and role not in TOPOLOGY_ROLE:
            errors.append(f"{prefix}.role={role!r} not in {sorted(TOPOLOGY_ROLE)}")

        lifecycle = _require_topology_repo_string(repo_entry, "lifecycle", errors, prefix=prefix)
        if lifecycle == "graduated":
            errors.append(f"{prefix}.lifecycle must not be 'graduated'; use a relationship instead")
        elif lifecycle and lifecycle not in TOPOLOGY_STATUS:
            errors.append(f"{prefix}.lifecycle={lifecycle!r} not in {sorted(TOPOLOGY_STATUS)}")

        visibility = _require_topology_repo_string(repo_entry, "visibility", errors, prefix=prefix)
        if visibility and visibility not in TOPOLOGY_VISIBILITY:
            errors.append(
                f"{prefix}.visibility={visibility!r} not in {sorted(TOPOLOGY_VISIBILITY)}"
            )

        relationship_value = repo_entry.get("relationship")
        for relationship in _topology_refs(
            relationship_value, errors, field="relationship", prefix=prefix
        ):
            if relationship not in TOPOLOGY_RELATIONSHIP:
                errors.append(
                    f"{prefix}.relationship={relationship!r} not in {sorted(TOPOLOGY_RELATIONSHIP)}"
                )

        parent = repo_entry.get("parent")
        if parent is not None:
            if not isinstance(parent, str) or not parent.strip():
                errors.append(f"{prefix}.parent must be a non-empty repo topology slug")
            elif parent.strip() not in slugs:
                warnings.append(f"{prefix}.parent={parent!r} does not match a repo slug in repos")

        github_owner = repo_entry.get("github_owner")
        repo_name = repo_entry.get("repo_name")
        if github_owner is not None and (
            not isinstance(github_owner, str) or not GITHUB_OWNER_RE.fullmatch(github_owner)
        ):
            errors.append(f"{prefix}.github_owner must be a GitHub owner/org slug")
        if repo_name is not None and (
            not isinstance(repo_name, str) or not GITHUB_REPO_RE.fullmatch(repo_name)
        ):
            errors.append(f"{prefix}.repo_name must be a GitHub repo name")
        if (github_owner is None) != (repo_name is None):
            errors.append(f"{prefix}.github_owner and {prefix}.repo_name must be recorded together")

        remote_full_name = _github_ref_full_name(repo_entry.get("remote"))
        if repo_entry.get("remote") is not None and not remote_full_name:
            errors.append(f"{prefix}.remote must be a GitHub handle or github.com URL when present")
        if (
            remote_full_name
            and isinstance(github_owner, str)
            and isinstance(repo_name, str)
            and remote_full_name != f"{github_owner}/{repo_name}"
        ):
            if lifecycle == "proposed":
                warnings.append(
                    f"{prefix}.remote points to {remote_full_name!r} while "
                    f"github_owner/repo_name is {github_owner}/{repo_name}; allowed for "
                    "lifecycle 'proposed' rename planning, but accepted/live entries must match"
                )
            else:
                errors.append(
                    f"{prefix}.remote must match github_owner/repo_name "
                    f"({github_owner}/{repo_name})"
                )

        domain = repo_entry.get("domain")
        if domain is not None and (
            not isinstance(domain, str) or not DOMAIN_RE.fullmatch(domain.strip())
        ):
            errors.append(f"{prefix}.domain must be a bare domain such as example.com")

        if role in {"finance", "legal"} and visibility not in {"restricted", "local_only"}:
            warnings.append(
                f"{prefix} has role {role!r}; finance/legal topology should usually use "
                "restricted or local_only visibility and link only approved summaries"
            )
        if role == "archive" and lifecycle not in {"archived", "superseded"}:
            warnings.append(f"{prefix} uses role 'archive' but lifecycle is {lifecycle!r}")

        for field in sorted(TOPOLOGY_LOCAL_LINK_FIELDS):
            if field not in repo_entry:
                continue
            for ref in _topology_refs(repo_entry.get(field), errors, field=field, prefix=prefix):
                _check_topology_local_link(
                    repo=repo_root,
                    source=path,
                    field=field,
                    ref=ref,
                    errors=errors,
                    warnings=warnings,
                    prefix=prefix,
                )

        if "linked_playbooks" in repo_entry:
            warnings.append(
                f"{prefix}.linked_playbooks looks like a reusable playbook reference; "
                "topology should link business repo run records with linked_playbook_runs"
            )

    secret_paths = sorted(set(_iter_secret_paths(fm)))
    if secret_paths:
        errors.append(
            "repo topology frontmatter must not contain secrets: " + ", ".join(secret_paths)
        )
    _warn_topology_unsafe_paths(fm, warnings)


def _is_hidden_or_generated(path: Path, repo: Path) -> bool:
    rel_parts = path.relative_to(repo).parts
    is_bundled_data = rel_parts[:2] == ("mb", "_data") or rel_parts[:1] == ("_data",)
    return (
        any(
            part.startswith(".") or part in {"__pycache__", "node_modules", ".venv", "venv"}
            for part in rel_parts
        )
        or is_bundled_data
    )


def _iter_frontmatter_files(repo: Path) -> list[Path]:
    return [
        f
        for f in sorted(repo.rglob("*.md"))
        if f.is_file() and not _is_hidden_or_generated(f, repo)
    ]


def _coerce_refs(value: Any) -> tuple[list[str], bool]:
    if value is None:
        return [], True
    if isinstance(value, str):
        return [value], True
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)], all(
            isinstance(item, str) for item in value
        )
    return [], False


def _read_markdown_body(path: Path) -> str | None:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if not text.startswith("---"):
        return text
    try:
        end = text.index("\n---", 3)
    except ValueError:
        return text
    return text[end + len("\n---") :]


def _resolve_wikilink(
    *,
    repo: Path,
    target: str,
    files_by_stem: dict[str, list[Path]],
    files_by_rel: dict[str, Path],
) -> tuple[Path | None, bool]:
    clean = relationships.wikilink_target(target)
    if not clean:
        return None, False
    is_bare_wikilink = len(Path(clean).parts) == 1
    candidates = [clean]
    if not clean.endswith(".md"):
        candidates.append(f"{clean}.md")
    for candidate in candidates:
        direct = files_by_rel.get(candidate)
        if direct is not None:
            return direct, False
        repo_direct = (repo / candidate).resolve()
        try:
            repo_direct.relative_to(repo)
        except ValueError:
            continue
        if repo_direct.is_file() and repo_direct.suffix == ".md":
            return repo_direct, False
    if not is_bare_wikilink:
        return None, False
    matches = files_by_stem.get(Path(clean).stem, [])
    if len(matches) == 1:
        return matches[0], False
    return None, len(matches) > 1


def _status_order_for(path: Path) -> dict[str, int] | None:
    parts = path.parts
    if "decisions" in parts:
        return DECISION_STATUS_ORDER
    if "pushes" in parts or "campaigns" in parts:
        return CAMPAIGN_STATUS_ORDER
    if "offers" in parts:
        return OFFER_STATUS_ORDER
    return None


def _finding(
    *,
    code: str,
    source: Path,
    repo: Path,
    field: str,
    target: str,
    message: str,
) -> dict[str, str]:
    return {
        "code": code,
        "path": str(source.relative_to(repo)),
        "field": field,
        "target": target,
        "message": message,
    }


def _add_file_warning(
    files_by_path: dict[str, dict[str, Any]],
    *,
    repo: Path,
    source: Path,
    message: str,
) -> None:
    rel = str(source.relative_to(repo))
    if rel not in files_by_path:
        files_by_path[rel] = {
            "path": rel,
            "ok": True,
            "errors": [],
            "warnings": [],
            "schema": "cross-refs",
        }
    files_by_path[rel].setdefault("warnings", []).append(message)


def _add_migration_lint_warnings(
    files_by_path: dict[str, dict[str, Any]],
    report: dict[str, Any],
) -> None:
    for finding in report.get("findings", []):
        raw_path = str(finding.get("path") or "migration-drift")
        rel = raw_path.rstrip("/") or raw_path
        message = str(finding.get("message") or "")
        if not message:
            continue
        files_by_path.setdefault(
            rel,
            {
                "path": rel,
                "ok": True,
                "errors": [],
                "warnings": [],
                "schema": "migration-drift",
            },
        )
        files_by_path[rel].setdefault("warnings", []).append(message)


def _add_team_handle_duplicate_errors(repo: Path, files_by_path: dict[str, dict[str, Any]]) -> None:
    handles: dict[str, list[str]] = {}
    for path in sorted((repo / team.TEAM_DIR).glob("*.md")):
        if path.name == "README.md":
            continue
        fm, err = _read_frontmatter(path)
        if err is not None or fm is None:
            continue
        github = fm.get("github")
        raw_handles = (
            [github] if isinstance(github, str) else github if isinstance(github, list) else []
        )
        if not isinstance(raw_handles, list):
            continue
        rel = path.relative_to(repo).as_posix()
        for raw_handle in raw_handles:
            normalized = team.normalize_github_handle(raw_handle)
            if normalized:
                handles.setdefault(normalized, []).append(rel)

    for handle, paths in handles.items():
        unique_paths = sorted(set(paths))
        if len(unique_paths) < 2:
            continue
        message = f"duplicate github handle {handle!r} appears in {', '.join(unique_paths)}"
        for rel in unique_paths:
            files_by_path.setdefault(
                rel,
                {
                    "path": rel,
                    "ok": True,
                    "errors": [],
                    "warnings": [],
                    "schema": "team-members",
                },
            )
            files_by_path[rel].setdefault("errors", []).append(message)
            files_by_path[rel]["ok"] = False


def _validation_category(message: str, *, severity: str, schema: str) -> str:
    lowered = message.lower()
    if schema == "file-contracts" and "empty" in lowered:
        return "file_contract_empty_section"
    if schema == "file-contracts":
        return "file_contract_missing_section"
    if lowered.startswith("your offer") and "empty" in lowered:
        return "file_contract_empty_section"
    if lowered.startswith("your offer"):
        return "file_contract_missing_section"
    if schema == "team-members" and "duplicate github handle" in lowered:
        return "duplicate_github_handle"
    if schema == "team-members" and "must be normalized as" in lowered:
        return "unnormalized_github_handle"
    if message == "missing key: slug":
        return "missing_slug"
    if message.startswith("missing key:"):
        return "missing_required_key"
    if lowered in {"no frontmatter", "unterminated frontmatter", "frontmatter not a mapping"}:
        return "no_frontmatter"
    if lowered.startswith("yaml error:"):
        return "yaml_error"
    enum_match = re.search(r"(?:^|[.\s\]])([a-z_]+)=", message)
    if enum_match and " not in " in message:
        if enum_match.group(1) == "status":
            return "status_enum_mismatch"
        return "enum_mismatch"
    if (
        " must be a mapping" in message
        or " must be a non-empty string" in message
        or " must be true or false" in message
        or " must be recorded" in message
        or " must point to " in message
        or " must live under " in message
        or " must match " in message
        or " must contain " in message
        or " must not contain " in message
        or "frontmatter must" in message
    ):
        return "schema_shape_error"
    if " target " in message and ("does not exist" in message or "does not resolve" in message):
        return "missing_cross_ref_target"
    if " is not mirrored in ## Related links" in message:
        return related_links.MISSING_RELATED_LINK_MIRROR_CATEGORY
    if " should include linked_" in message:
        return "missing_reverse_link"
    if schema == "migration-drift":
        return "migration_drift"
    return "other_error" if severity == "error" else "other_warning"


def _name_allowed_status_values(entry: dict[str, Any] | None, schemas: list[str]) -> None:
    """Name the allowed `status:` values per file type in the rollup an agent reads.

    The per-file message already lists them; the rollup (`mb validate`, `mb status
    --json` and `mb doctor repair --plan --json` print `repair`) used to say only
    "one of the allowed lifecycle values", and its example named a status no file
    type accepts (#1122).
    """
    if entry is None or not schemas:
        return
    allowed = {
        schema: sorted(SCHEMAS[schema]["enums"]["status"]) for schema in sorted(set(schemas))
    }
    named = "; ".join(
        f"{schema.rsplit('/', 1)[-1]}: {' | '.join(values)}" for schema, values in allowed.items()
    )
    entry["allowed_status"] = allowed
    entry["repair"] = f"Change `status:` to an allowed value ({named})."
    entry["operator_summary"] = f"Pick a status this kind of file allows ({named})."


def _validation_categories(files: list[dict[str, Any]]) -> dict[str, Any]:
    categories: dict[str, dict[str, Any]] = {}
    status_schemas: list[str] = []
    for file_result in files:
        path = str(file_result.get("path") or "")
        schema = str(file_result.get("schema") or "")
        for severity, messages in (
            ("error", file_result.get("errors") or []),
            ("warning", file_result.get("warnings") or []),
        ):
            for raw_message in messages:
                message = str(raw_message)
                category = _validation_category(message, severity=severity, schema=schema)
                repair_text = VALIDATION_CATEGORY_REPAIR.get(
                    category, VALIDATION_CATEGORY_REPAIR["other_error"]
                )
                entry = categories.setdefault(
                    category,
                    {
                        "count": 0,
                        "errors": 0,
                        "warnings": 0,
                        "examples": [],
                        "repair": repair_text,
                        "audience": VALIDATION_CATEGORY_AUDIENCE.get(category, "operator_decision"),
                        "operator_summary": VALIDATION_CATEGORY_OPERATOR_SUMMARY.get(
                            category, repair_text
                        ),
                        "recommended_route": VALIDATION_CATEGORY_ROUTE.get(category, ""),
                    },
                )
                if (
                    category == "status_enum_mismatch"
                    and message.startswith("status=")
                    and "status" in SCHEMAS.get(schema, {}).get("enums", {})
                ):
                    status_schemas.append(schema)
                entry["count"] += 1
                entry["errors" if severity == "error" else "warnings"] += 1
                examples = entry["examples"]
                if len(examples) < 5:
                    examples.append({"path": path, "message": message})
    _name_allowed_status_values(categories.get("status_enum_mismatch"), status_schemas)
    ordered = dict(
        sorted(
            categories.items(),
            key=lambda item: (
                -int(item[1].get("errors", 0)),
                -int(item[1]["count"]),
                item[0],
            ),
        )
    )
    top_category = next(iter(ordered), "")
    top_entry = ordered.get(top_category, {})
    blocker_count = sum(int(item.get("errors", 0)) for item in ordered.values())
    mechanical_warning_count = sum(
        int(item.get("warnings", 0))
        for item in ordered.values()
        if item.get("audience") == "mechanical"
    )
    operator_warning_count = sum(
        int(item.get("warnings", 0))
        for item in ordered.values()
        if item.get("audience") != "mechanical"
    )
    return {
        "schema_version": "1.1",
        "total_categories": len(ordered),
        "top_category": top_category,
        "top_repair": top_entry.get("repair", ""),
        "top_audience": top_entry.get("audience", ""),
        "top_operator_summary": top_entry.get("operator_summary", ""),
        "blocker_count": blocker_count,
        "mechanical_warning_count": mechanical_warning_count,
        "operator_warning_count": operator_warning_count,
        "owner_summary": _owner_summary(
            blocker_count, mechanical_warning_count, operator_warning_count
        ),
        "by_category": ordered,
        "safe_to_share": True,
    }


def _owner_summary(
    blocker_count: int,
    mechanical_warning_count: int,
    operator_warning_count: int,
) -> str:
    """One-line owner framing that separates blockers from bulk-repairable noise.

    Mechanical warnings cover both related-link mirrors and migration drift, so
    the rollup label stays generic; per-category ``operator_summary`` carries the
    specific mirror vs migration repair guidance.
    """
    parts: list[str] = []
    if blocker_count:
        parts.append(f"{blocker_count} blocker(s) to fix")
    if mechanical_warning_count:
        parts.append(f"{mechanical_warning_count} bulk-repairable warning(s)")
    if operator_warning_count:
        parts.append(f"{operator_warning_count} warning(s) to review")
    if not parts:
        return "No validation issues."
    return ", ".join(parts) + "."


def _check_status_transition(
    *,
    source: Path,
    target: Path,
    repo: Path,
    field: str,
    ref: str,
    source_fm: dict[str, Any],
    findings: list[dict[str, str]],
) -> None:
    if field != "supersedes":
        return
    source_order = _status_order_for(source.relative_to(repo))
    target_order = _status_order_for(target.relative_to(repo))
    if source_order is None or target_order is None or source_order is not target_order:
        return
    source_status = source_fm.get("status")
    target_fm, target_err = _read_frontmatter(target)
    if target_err is not None or target_fm is None:
        return
    target_status = target_fm.get("status")
    if not isinstance(source_status, str) or not isinstance(target_status, str):
        return
    if source_status not in source_order or target_status not in source_order:
        return
    if source_order[source_status] < source_order[target_status]:
        findings.append(
            _finding(
                code="status-transition",
                source=source,
                repo=repo,
                field=field,
                target=ref,
                message=(
                    f"{field} target {ref!r} is status {target_status!r}; "
                    f"source status {source_status!r} would move backward"
                ),
            )
        )


def _relative_ref(path: Path, repo: Path) -> str:
    return path.relative_to(repo).as_posix()


def _ref_list_contains(value: Any, expected: str) -> bool:
    refs, valid_type = _coerce_refs(value)
    return valid_type and expected in {relationships.clean_ref(ref) for ref in refs}


def _reverse_bet_field(source: Path, repo: Path) -> str:
    parts = source.relative_to(repo).parts
    if not parts:
        return ""
    section = parts[0]
    if section == "decisions":
        return "linked_decisions"
    if section == "research":
        return "linked_research"
    if section == "pushes":
        return "linked_pushes"
    if section == "campaigns":
        return "linked_campaigns"
    if section in {"log", "documents"}:
        return "linked_outcomes"
    return ""


def _check_bet_backlink(
    *,
    source: Path,
    target: Path,
    repo: Path,
    field: str,
    ref: str,
    target_fm: dict[str, Any],
    findings: list[dict[str, str]],
) -> None:
    source_rel = _relative_ref(source, repo)
    target_rel = _relative_ref(target, repo)
    source_is_bet = source_rel.startswith("bets/")
    target_is_bet = target_rel.startswith("bets/")

    if (
        source_is_bet
        and not target_is_bet
        and field
        in {
            "linked_decisions",
            "linked_research",
            "linked_pushes",
            "linked_campaigns",
            "linked_outcomes",
        }
    ):
        if not _ref_list_contains(target_fm.get("linked_bets"), source_rel):
            findings.append(
                _finding(
                    code="missing-bet-backlink",
                    source=source,
                    repo=repo,
                    field=field,
                    target=ref,
                    message=(f"{field} target {ref!r} should include linked_bets: {source_rel}"),
                )
            )
        return

    if field == "linked_bets" and target_is_bet and not source_is_bet:
        reverse_field = _reverse_bet_field(source, repo)
        if reverse_field and not _ref_list_contains(target_fm.get(reverse_field), source_rel):
            findings.append(
                _finding(
                    code="missing-bet-backlink",
                    source=source,
                    repo=repo,
                    field=field,
                    target=ref,
                    message=(
                        f"{field} target {ref!r} should include {reverse_field}: {source_rel}"
                    ),
                )
            )


def _check_cross_refs(
    repo: Path,
    files_by_path: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    findings: list[dict[str, str]] = []
    orphan_offers: list[dict[str, str]] = []
    markdown_files = _iter_frontmatter_files(repo)
    files_by_stem: dict[str, list[Path]] = {}
    files_by_rel: dict[str, Path] = {}

    for file_path in markdown_files:
        rel = file_path.relative_to(repo).as_posix()
        files_by_rel[rel] = file_path
        files_by_stem.setdefault(file_path.stem, []).append(file_path)

    related_index = related_links.markdown_index(repo, markdown_files)
    for source in markdown_files:
        fm, err = _read_frontmatter(source)
        if err is not None or fm is None:
            continue
        source_rel = source.relative_to(repo).as_posix()
        body = _read_markdown_body(source) or ""
        for mirror_ref in related_links.missing_mirror_refs(
            repo, source, fm, body, index=related_index
        ):
            findings.append(
                _finding(
                    code="missing-related-link-mirror",
                    source=source,
                    repo=repo,
                    field=mirror_ref.field,
                    target=mirror_ref.key,
                    message=(
                        f"{mirror_ref.field} target {mirror_ref.key!r} "
                        "is not mirrored in ## Related links"
                    ),
                )
            )
        for field in relationships.relationship_fields_for_source(source_rel):
            if field not in fm:
                continue
            refs, valid_type = _coerce_refs(fm.get(field))
            if not valid_type:
                findings.append(
                    _finding(
                        code="invalid-link-field",
                        source=source,
                        repo=repo,
                        field=field,
                        target="",
                        message=f"{field} must be a string or list of strings",
                    )
                )
                continue
            for ref in refs:
                if relationships.is_external_ref(ref):
                    continue
                clean_ref = relationships.clean_ref(ref)
                if not clean_ref:
                    continue
                target = (repo / clean_ref).resolve()
                try:
                    target.relative_to(repo)
                except ValueError:
                    findings.append(
                        _finding(
                            code="target-outside-repo",
                            source=source,
                            repo=repo,
                            field=field,
                            target=ref,
                            message=f"{field} target {ref!r} resolves outside the repo",
                        )
                    )
                    continue
                if not target.exists():
                    findings.append(
                        _finding(
                            code="missing-target",
                            source=source,
                            repo=repo,
                            field=field,
                            target=ref,
                            message=f"{field} target {ref!r} does not exist",
                        )
                    )
                    continue
                _check_status_transition(
                    source=source,
                    target=target,
                    repo=repo,
                    field=field,
                    ref=ref,
                    source_fm=fm,
                    findings=findings,
                )
                target_fm, target_err = _read_frontmatter(target)
                if target_err is None and target_fm is not None:
                    _check_bet_backlink(
                        source=source,
                        target=target,
                        repo=repo,
                        field=field,
                        ref=ref,
                        target_fm=target_fm,
                        findings=findings,
                    )

    for source in markdown_files:
        markdown_body = _read_markdown_body(source)
        if markdown_body is None:
            continue
        body_without_code = relationships.strip_markdown_code(markdown_body)
        for match in relationships.WIKILINK_RE.finditer(body_without_code):
            raw_target = match.group(1)
            clean_target = relationships.wikilink_target(raw_target)
            if not clean_target:
                continue
            resolved, ambiguous = _resolve_wikilink(
                repo=repo,
                target=raw_target,
                files_by_stem=files_by_stem,
                files_by_rel=files_by_rel,
            )
            if resolved is not None:
                continue
            code = "ambiguous-wikilink" if ambiguous else "missing-wikilink-target"
            message = (
                f"wikilink target {raw_target!r} matches multiple markdown files"
                if ambiguous
                else f"wikilink target {raw_target!r} does not resolve to a markdown file"
            )
            findings.append(
                _finding(
                    code=code,
                    source=source,
                    repo=repo,
                    field="wikilink",
                    target=raw_target,
                    message=message,
                )
            )
        for _, raw_target in relationships.iter_markdown_links(body_without_code):
            clean_target = relationships.markdown_link_target(raw_target)
            if not clean_target or relationships.is_external_ref(clean_target):
                continue
            if not relationships.is_local_markdown_ref(clean_target):
                continue
            if relationships.resolve_markdown_link(repo, source, clean_target) is not None:
                continue
            findings.append(
                _finding(
                    code="missing-markdown-link-target",
                    source=source,
                    repo=repo,
                    field="markdown_link",
                    target=clean_target,
                    message=(
                        f"markdown link target {clean_target!r} does not resolve to a markdown file"
                    ),
                )
            )

    offers_root = repo / "core" / "offers"
    if offers_root.exists():
        for offer_dir in sorted(p for p in offers_root.iterdir() if p.is_dir()):
            if (offer_dir / "offer.md").exists():
                continue
            rel = str(offer_dir.relative_to(repo))
            orphan_offers.append(
                {
                    "code": "orphan-offer",
                    "path": rel,
                    "field": "core/offers",
                    "target": "offer.md",
                    "message": f"{rel}/ is missing offer.md",
                }
            )

    for finding in findings:
        _add_file_warning(
            files_by_path,
            repo=repo,
            source=repo / finding["path"],
            message=finding["message"],
        )
    for finding in orphan_offers:
        rel = finding["path"]
        files_by_path.setdefault(
            rel,
            {
                "path": rel,
                "ok": True,
                "errors": [],
                "warnings": [],
                "schema": "core/offers",
            },
        )
        files_by_path[rel].setdefault("warnings", []).append(finding["message"])

    return {
        "enabled": True,
        "checked_fields": list(LINK_FIELDS),
        "registry": relationships.registry_payload(),
        "warnings": findings + orphan_offers,
        "orphan_offers": orphan_offers,
    }


def _legacy_frontmatter_repair(repo: Path, error_count: int) -> dict[str, Any] | None:
    if error_count == 0:
        return None
    migrated_markers = [
        repo / ".mb" / "schema_version",
        repo / "decisions" / "2026-05-02-mainbranch-v02-path-migration.md",
    ]
    has_compat_links = (repo / "reference" / "core").is_symlink() or (
        repo / "reference" / "offers"
    ).is_symlink()
    if not has_compat_links and not any(path.exists() for path in migrated_markers):
        return None
    return {
        "code": "legacy-frontmatter-schema-debt",
        "message": (
            "Layout migration can succeed while old markdown files still fail the "
            "current frontmatter schema. Treat these as legacy content repairs, "
            "not as evidence that the path migration failed."
        ),
        "next_steps": [
            "Run `mb validate --json` and group failures by missing key or status enum.",
            "Repair frontmatter in small batches on the migration branch.",
            "Use `mb validate --cross-refs` after schema errors are down to zero.",
        ],
    }


def _is_folder_doc(path: Path, schema_name: str) -> bool:
    return schema_name in {
        "research",
        "decisions",
        "bets",
        "log",
        "documents",
        "push-playbooks",
        "team-members",
    } and (path.name == "README.md")


def _normalize_scope_paths(repo: Path, paths: list[str]) -> list[str]:
    """Normalize --paths entries to repo-relative posix prefixes."""
    prefixes: list[str] = []
    for raw in paths:
        candidate = Path(raw)
        if candidate.is_absolute():
            try:
                rel = candidate.resolve().relative_to(repo)
            except ValueError:
                raise ValueError(f"--paths entry {raw!r} is outside the repo") from None
        else:
            rel = Path(raw.replace("\\", "/"))
        text = rel.as_posix().strip("/")
        if text in {"", "."}:
            # Whole-repo scope: treat as unscoped.
            return []
        if ".." in rel.parts:
            raise ValueError(f"--paths entry {raw!r} escapes the repo")
        prefixes.append(text)
    return prefixes


def _path_in_scope(rel: str, prefixes: list[str]) -> bool:
    return any(rel == prefix or rel.startswith(prefix + "/") for prefix in prefixes)


def run(
    path: str,
    verbose: bool = False,
    cross_refs: bool = False,
    strict: bool = False,
    migration_drift_report: dict[str, Any] | None = None,
    paths: list[str] | None = None,
) -> dict[str, Any]:
    """Run validation across all known schemas. Verbose adds key dumps.

    ``paths`` scopes the report to files under the given repo-relative
    prefixes — so an agent can validate only what it touched instead of
    hand-rolling filters against a repo's legacy debt.
    """
    repo = Path(path).resolve()
    scope_prefixes = _normalize_scope_paths(repo, paths or [])
    files_by_path: dict[str, dict[str, Any]] = {}
    for schema_name, schema in SCHEMAS.items():
        glob = schema["glob"]
        for f in sorted(repo.glob(glob)):
            if _is_folder_doc(f, schema_name):
                continue
            r = _check_one(f, schema)
            r["schema"] = schema_name
            r["path"] = str(f.relative_to(repo))
            files_by_path[r["path"]] = r
    files_by_path.update(content_strategy.validation_results(repo))
    _add_team_handle_duplicate_errors(repo, files_by_path)
    file_contract_report = file_contracts.evaluate(repo)
    for finding in file_contract_report.get("findings", []):
        rel = str(finding.get("path") or "")
        if not rel:
            continue
        severity = str(finding.get("severity") or "warn")
        message = str(finding.get("owner_message") or finding.get("message") or "")
        if not message:
            continue
        file_entry = files_by_path.setdefault(
            rel,
            {
                "path": rel,
                "ok": True,
                "errors": [],
                "warnings": [],
                "schema": "file-contracts",
            },
        )
        if file_entry.get("errors"):
            continue
        if severity == "error":
            file_entry.setdefault("errors", []).append(message)
            file_entry["ok"] = False
        else:
            file_entry.setdefault("warnings", []).append(message)

    if migration_drift_report is None:
        migration_drift_report = migration_lint.run(repo)
    _add_migration_lint_warnings(files_by_path, migration_drift_report)

    cross_ref_report = {"enabled": False, "checked_fields": [], "warnings": [], "orphan_offers": []}
    if cross_refs:
        cross_ref_report = _check_cross_refs(repo, files_by_path)

    if scope_prefixes:
        files_by_path = {
            rel: entry
            for rel, entry in files_by_path.items()
            if _path_in_scope(rel, scope_prefixes)
        }
        for key in ("warnings", "orphan_offers"):
            raw_findings = cross_ref_report.get(key)
            findings_list: list[dict[str, Any]] = (
                raw_findings if isinstance(raw_findings, list) else []
            )
            cross_ref_report[key] = [
                finding
                for finding in findings_list
                if _path_in_scope(str(finding.get("path") or ""), scope_prefixes)
            ]

    files = list(files_by_path.values())
    warning_count = sum(len(f.get("warnings", [])) for f in files)
    error_count = sum(len(f.get("errors", [])) for f in files)
    categories = _validation_categories(files)
    ok = error_count == 0 and (warning_count == 0 or not strict)
    if strict:
        for file_result in files:
            if file_result.get("warnings"):
                file_result["ok"] = False
    return {
        "ok": ok,
        "files": files,
        "repo": str(repo),
        "scoped_paths": scope_prefixes,
        "strict": strict,
        "cross_refs": cross_ref_report,
        "legacy_repair": _legacy_frontmatter_repair(repo, error_count),
        "migration_drift": migration_drift_report,
        "file_contracts": file_contract_report,
        "validation_categories": categories,
        "by_category": categories["by_category"],
        "summary": {"errors": error_count, "warnings": warning_count},
    }


def render_human(report: dict[str, Any], verbose: bool = False, repo: Path | None = None) -> None:
    """Print results to stdout; `repo` names the business repo in the commands it suggests."""
    from rich.console import Console
    from rich.markup import escape

    console = Console()
    if not report["files"]:
        console.print("[yellow]nothing to check yet.[/yellow]")
        return
    by_schema: dict[str, list[dict[str, Any]]] = {}
    for f in report["files"]:
        by_schema.setdefault(f["schema"], []).append(f)
    for schema, items in by_schema.items():
        ok_n = sum(1 for f in items if not f["errors"] and not f.get("warnings"))
        warn_n = sum(1 for f in items if not f["errors"] and f.get("warnings"))
        fail_n = sum(1 for f in items if f["errors"])
        console.print(f"\n[bold]{schema}[/bold]  {ok_n} ok, {warn_n} warn, {fail_n} fail")
        for f in items:
            if not verbose and not f["errors"]:
                # Collapse warning-only and ok files by default; the grouped
                # summary below carries compact examples and repair guidance so
                # a few thousand cross-ref/mirror warnings never flood the loop.
                continue
            if f["errors"]:
                mark = "[red]fail[/red]"
            elif f.get("warnings"):
                mark = "[yellow]warn[/yellow]"
            else:
                mark = "[green]ok[/green]"
            console.print(f"  {mark}  {f['path']}")
            for e in f["errors"]:
                console.print(f"        - {e}")
            if verbose:
                for warning in f.get("warnings", []):
                    console.print(f"        - {warning}")
    legacy_repair = report.get("legacy_repair")
    categories = report.get("validation_categories") or {}
    by_category = categories.get("by_category") or {}
    if by_category:
        console.print("\n[bold yellow]Validation summary[/bold yellow]")
        owner_summary = categories.get("owner_summary")
        if owner_summary:
            console.print(f"  {owner_summary}")
        blockers = [(n, i) for n, i in by_category.items() if i.get("errors")]
        mechanical = [
            (n, i)
            for n, i in by_category.items()
            if not i.get("errors") and i.get("warnings") and i.get("audience") == "mechanical"
        ]
        other = [
            (n, i)
            for n, i in by_category.items()
            if not i.get("errors") and i.get("warnings") and i.get("audience") != "mechanical"
        ]
        if blockers:
            console.print("  [red]Blockers (fix these)[/red]:")
            for name, item in blockers[:5]:
                console.print(
                    f"    - {name}: {item.get('errors', 0)} error(s)"
                    f" — {escape(str(item.get('operator_summary', '')))}"
                )
        if mechanical:
            console.print("  [yellow]Bulk-repairable (mechanical)[/yellow]:")
            for name, item in mechanical[:3]:
                console.print(
                    f"    - {name}: {item.get('warnings', 0)} warning(s)"
                    f" — {escape(str(item.get('operator_summary', '')))}"
                )
        if other:
            console.print("  Other warnings:")
            for name, item in other[:5]:
                console.print(
                    f"    - {name}: {item.get('warnings', 0)} warning(s)"
                    f" — {escape(str(item.get('operator_summary', '')))}"
                )
        top_repair = categories.get("top_repair")
        if top_repair:
            console.print(f"  next: {escape(top_repair)}")
        if not verbose and (mechanical or other):
            validate_command = f"mb validate{repo_flag(repo)} --cross-refs -v"
            console.print(
                f"  Run `{escape(validate_command)}` or `--json` for the full per-file list."
            )
    if legacy_repair:
        console.print("\n[bold yellow]Legacy frontmatter repair[/bold yellow]")
        console.print(f"  {legacy_repair['message']}")
        for step in legacy_repair.get("next_steps", []):
            console.print(f"  - {escape(step)}")
    console.print()
    if report["ok"]:
        if report["summary"]["warnings"]:
            console.print(
                f"[yellow]{report['summary']['warnings']} warning(s) found; "
                "use --strict to fail on warnings.[/yellow]"
            )
        else:
            console.print("[green]all metadata looks right.[/green]")
    else:
        if report["summary"]["errors"]:
            bad = sum(1 for f in report["files"] if f["errors"])
            console.print(f"[red]{bad} file(s) need fixing — see above.[/red]")
        else:
            console.print(
                f"[red]{report['summary']['warnings']} warning(s) fail in strict mode.[/red]"
            )
