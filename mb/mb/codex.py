"""Codex global-skill helpers.

Codex support starts with repo instructions, global Main Branch skills, and
deterministic ``mb`` facts. This module intentionally does not invoke Codex or
manage model conversation.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
from collections.abc import Callable
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

from mb import __version__
from mb import engine as engine_mod
from mb.codex_known_files import KNOWN_FILE_DIGESTS
from mb.durable import atomic_write_text
from mb.workflows import WorkflowSource, load_workflow, render_codex_shell

AGENTS_TEMPLATE = "AGENTS.md.tmpl"
AGENTS_RELATIVE_PATH = "AGENTS.md"
AGENTS_MANAGED_BEGIN = "<!-- mainbranch:codex-guidance:begin -->"
AGENTS_MANAGED_END = "<!-- mainbranch:codex-guidance:end -->"
CODEX_GUIDANCE_SCHEMA = 1
CODEX_GUIDANCE_MIN_MB = "0.3.43"
CODEX_SKILL_DIR_RELATIVE_PATH = ".agents/skills/main-branch-owner-loop"
CODEX_SKILL_RELATIVE_PATH = f"{CODEX_SKILL_DIR_RELATIVE_PATH}/SKILL.md"
CODEX_WORKFLOW_INVENTORY_RELATIVE_PATH = AGENTS_RELATIVE_PATH
CODEX_GLOBAL_SKILL_NAME = "main-branch"
CODEX_LEGACY_GLOBAL_SKILL_NAME = "main-branch-owner-loop"
CODEX_GLOBAL_SKILL_RELATIVE_PATH = f"{CODEX_GLOBAL_SKILL_NAME}/SKILL.md"
CODEX_MARKETPLACE_RELATIVE_PATH = ".agents/plugins/marketplace.json"
CODEX_MARKETPLACE_NAME = "main-branch"
CODEX_LEGACY_PLUGIN_NAME = "main-branch-owner-loop"
CODEX_PLUGIN_NAME = "main-branch"
CODEX_PLUGIN_SELECTOR = f"{CODEX_PLUGIN_NAME}@{CODEX_MARKETPLACE_NAME}"
CODEX_LEGACY_PLUGIN_SELECTOR = f"{CODEX_LEGACY_PLUGIN_NAME}@{CODEX_MARKETPLACE_NAME}"
CODEX_PLUGIN_INSTALL_COMMAND = f"codex plugin add {CODEX_PLUGIN_SELECTOR}"
CODEX_PLUGIN_DIR_RELATIVE_PATH = f".agents/plugins/{CODEX_PLUGIN_NAME}"
CODEX_LEGACY_PLUGIN_DIR_RELATIVE_PATH = f".agents/plugins/{CODEX_LEGACY_PLUGIN_NAME}"
CODEX_PLUGIN_COMMANDS_RELATIVE_PATH = f"{CODEX_PLUGIN_DIR_RELATIVE_PATH}/commands"
CODEX_PLUGIN_LEGACY_COMMANDS_RELATIVE_PATH = f"{CODEX_LEGACY_PLUGIN_DIR_RELATIVE_PATH}/commands"
CODEX_PLUGIN_MANIFEST_RELATIVE_PATH = f"{CODEX_PLUGIN_DIR_RELATIVE_PATH}/.codex-plugin/plugin.json"
CODEX_PLUGIN_SKILL_RELATIVE_PATH = (
    f"{CODEX_LEGACY_PLUGIN_DIR_RELATIVE_PATH}/skills/main-branch-owner-loop/SKILL.md"
)
CODEX_SUPPORT_LEVEL = "supported_global_main_branch_skill"
# The bare forms, for text with no business repo in view (#1072). Wherever the
# repo is known, `repair_command(repo)` and `repair_text(repo)` name it.
CODEX_REPAIR_COMMAND = "mb doctor repair --apply --only codex"
CODEX_REPAIR_TEXT = (
    "Run `mb doctor repair --plan --only codex`, review, then "
    "`mb doctor repair --apply --only codex`."
)
CODEX_RUNTIME_MISMATCH_STOP_TEXT = (
    "After `mb status --json --peek` or `mb start --json`, stop if "
    "`runtime.codex_cli.status` is `runtime_mismatch` or any `drift.items[].id` "
    "equals `codex_runtime_mb_mismatch`. Treat that as a runtime `mb` mismatch: "
    "tell the operator to fix the runtime/login-shell PATH and rerun read-only "
    "checks before Main Branch advice, repair planning, or writes."
)
REQUIRED_FACT_COMMANDS = (
    "mb status --json --peek",
    "mb start --json",
    "mb doctor repair --plan",
)
CODEX_SLASH_COMMAND_NAMES = (
    "mb-start",
    "mb-status",
    "mb-setup",
    "mb-update",
    "mb-doctor",
    "mb-think",
    "mb-end",
    "mb-help",
)
CLAUDE_SKILL_SOURCE_NAMES = (
    "mb-start",
    "mb-status",
    "mb-setup",
    "mb-update",
    "mb-think",
    "mb-end",
    "mb-help",
    "mb-bet",
    "mb-ads",
    "mb-organic",
    "mb-site",
    "mb-books",
    "mb-wiki",
    "mb-skill-concept",
    "mb-skill-brief-draft",
    "mb-skill-review",
)
CLAUDE_PLAYBOOK_SOURCE_NAMES = ("google-ads-search-launch",)
CODEX_RETIRED_GLOBAL_SKILL_NAMES = (
    "google-ads-search-launch",
    "ship-bet",
    "weekly-review",
)
CODEX_GLOBAL_SKILL_NAMES = (
    CODEX_GLOBAL_SKILL_NAME,
    "mb-doctor",
    "mb-start",
    "mb-status",
    "mb-setup",
    "mb-update",
    "mb-think",
    "mb-end",
    "mb-help",
    "mb-bet",
    "mb-ads",
    "mb-organic",
    "mb-site",
    "mb-books",
    "mb-wiki",
    "mb-skill-concept",
    "mb-skill-brief-draft",
    "mb-skill-review",
)
CODEX_SLASH_COMMAND_RELATIVE_PATHS = tuple(
    f"{CODEX_PLUGIN_COMMANDS_RELATIVE_PATH}/{name}.md" for name in CODEX_SLASH_COMMAND_NAMES
)
CODEX_SLASH_COMMAND_FACTS: dict[str, tuple[str, ...]] = {
    "mb-start": ("mb status --json --peek", "mb start --json"),
    "mb-status": ("mb status --json --peek",),
    "mb-setup": ("mb --version", "mb onboard --help", "mb status --json --peek"),
    "mb-update": ("mb update --check --json", "mb status --json --peek"),
    "mb-doctor": ("mb doctor repair --plan --json", "mb status --json --peek"),
    "mb-think": (
        "mb status --json --peek",
        "mb start --json",
        "mb doctor repair --plan",
        "mb connect doctor --json",
        "mb checkpoint --plan --json",
    ),
    "mb-end": (
        "mb status --json --peek",
        "mb start --json",
        "mb doctor repair --plan",
        "mb checkpoint --plan --json",
        "mb validate --json",
    ),
    "mb-help": ("mb workflow list --runtime codex --json", "mb status --json --peek"),
}
CODEX_SLASH_COMMAND_DESCRIPTIONS = {
    "mb-start": "Start Main Branch.",
    "mb-status": "Show Main Branch status.",
    "mb-setup": "Set up Main Branch.",
    "mb-update": "Update Main Branch.",
    "mb-doctor": "Repair Main Branch setup.",
    "mb-think": "Think through a Main Branch decision.",
    "mb-end": "End and checkpoint work.",
    "mb-help": "Show Main Branch commands.",
}
CODEX_GLOBAL_SKILL_DESCRIPTIONS = {
    **CODEX_SLASH_COMMAND_DESCRIPTIONS,
    "main-branch": "Route Main Branch work to the right mb-* skill.",
    "mb-bet": "Plan and review Main Branch bets.",
    "mb-ads": "Plan ads and paid creative from Main Branch facts.",
    "mb-organic": "Plan organic content from Main Branch facts.",
    "mb-site": "Plan pages and site readiness from Main Branch facts.",
    "mb-books": "Review private books readiness from safe Main Branch facts.",
    "mb-wiki": "Explain wiki support status for Main Branch.",
    "mb-skill-concept": "Plan a Main Branch skill concept.",
    "mb-skill-brief-draft": "Draft a Main Branch skill brief.",
    "mb-skill-review": "Review a Main Branch skill proposal.",
}
CODEX_GLOBAL_SKILL_FACTS: dict[str, tuple[str, ...]] = {
    **CODEX_SLASH_COMMAND_FACTS,
    "main-branch": REQUIRED_FACT_COMMANDS,
    "mb-bet": (
        "mb status --json --peek",
        "mb start --json",
        "mb validate --cross-refs --json",
        "mb checkpoint --plan --json",
    ),
    "mb-ads": (
        "mb status --json --peek",
        "mb start --json",
        "mb doctor repair --plan",
        "mb connect doctor --json",
        "mb connect plan",
        'mb launch check "$SITE_REPO" --business-repo "$BUSINESS_REPO" --json',
        'mb site check "$SITE_REPO" --business-repo "$BUSINESS_REPO" --json',
        "mb validate --cross-refs --json",
        "mb checkpoint --plan --json",
    ),
    "mb-organic": ("mb status --json --peek",),
    "mb-site": (
        "mb status --json --peek",
        "mb start --json",
        "mb doctor repair --plan",
        "mb connect doctor --json",
        'mb launch check "$SITE_REPO" --business-repo "$BUSINESS_REPO" --json',
        'mb site check "$SITE_REPO" --business-repo "$BUSINESS_REPO" --json',
        "mb validate --cross-refs --json",
        "mb checkpoint --plan --json",
    ),
    "mb-wiki": ("mb workflow list --runtime codex --json",),
    "mb-books": ("mb books check . --json", 'mb books doctor --repo "$BOOKS_REPO" --json'),
    "mb-skill-concept": ("mb workflow list --runtime codex --json",),
    "mb-skill-brief-draft": ("mb workflow list --runtime codex --json",),
    "mb-skill-review": ("mb workflow list --runtime codex --json",),
}
CODEX_GLOBAL_SKILL_SUPPORT: dict[str, str] = {
    "main-branch": "supported",
    "mb-start": "supported",
    "mb-status": "supported",
    "mb-setup": "supported",
    "mb-update": "supported",
    "mb-doctor": "supported",
    "mb-think": "supported",
    "mb-end": "supported",
    "mb-help": "supported",
    "mb-bet": "read_only_planning",
    "mb-ads": "read_only_planning",
    "mb-organic": "read_only_planning",
    "mb-site": "read_only_planning",
    "mb-books": "read_only_planning",
    "mb-wiki": "intentionally_unsupported",
    "mb-skill-concept": "intentionally_unsupported",
    "mb-skill-brief-draft": "intentionally_unsupported",
    "mb-skill-review": "intentionally_unsupported",
}
CODEX_THINK_SOURCE_WORKFLOW = "workflows/mb-think/workflow.md"
CODEX_START_STATUS_SOURCE_WORKFLOW = "workflows/mb-start-status/workflow.md"
CODEX_SETUP_SOURCE_WORKFLOW = "workflows/mb-setup/workflow.md"
CODEX_MAINTENANCE_REPAIR_SOURCE_WORKFLOW = "workflows/mb-maintenance-repair/workflow.md"
CODEX_BET_SOURCE_WORKFLOW = "workflows/mb-bet/workflow.md"
CODEX_ADS_SOURCE_WORKFLOW = "workflows/mb-ads/workflow.md"
CODEX_ORGANIC_SOURCE_WORKFLOW = "workflows/mb-organic/workflow.md"
CODEX_SITE_SOURCE_WORKFLOW = "workflows/mb-site/workflow.md"
CODEX_THINK_REQUIRED_MB_COMMANDS = (
    "mb status --json --peek",
    "mb start --json",
    "mb doctor repair --plan",
    "mb connect doctor --json",
    "mb checkpoint --plan --json",
)
CODEX_THINK_REQUIRED_JSON_FACTS = (
    "money_path",
    "money_path.objects.offer",
    "money_path.objects.proof",
    "money_path.objects.proof.quality",
    "money_path.objects.product_ladder",
    "money_path.objects.cta_path",
    "money_path.objects.channel_strategy",
    "money_path.objects.active_push",
    "money_path.objects.outcome_feedback_loop",
    "money_path.ranked_actions",
    "validation.file_contracts",
    "content_strategy",
    "ranked_actions",
    "update",
    "readiness",
    "drift.items",
    "books",
    "runtime.codex_cli",
    "runtime.claude_code",
)
CODEX_THINK_APPROVAL_GATES = (
    "updates_repairs_migrations",
    "file_writes",
    "checkpoint",
    "provider_mutation",
    "publishing_or_spend",
    "customer_contact",
    "private_data",
    "destructive_operations",
    "structured_collection",
    "public_issue_or_proposal",
)
CODEX_THINK_PUBLIC_PRIVATE_BOUNDARIES = (
    "no_secrets",
    "no_raw_provider_exports",
    "no_raw_transcripts",
    "no_customer_member_data",
    "no_private_runtime_settings",
    "no_private_dms_or_gated_communities",
    "no_raw_finance_legal_records",
)
CODEX_END_SOURCE_WORKFLOW = "workflows/mb-end/workflow.md"
CODEX_END_REQUIRED_MB_COMMANDS = (
    "mb status --json --peek",
    "mb start --json",
    "mb doctor repair --plan",
    "mb checkpoint --plan --json",
    "mb validate --json",
)
CODEX_END_REQUIRED_JSON_FACTS = (
    "money_path",
    "money_path.objects.proof.quality",
    "validation.file_contracts",
    "content_strategy",
    "ranked_actions",
    "relationship_health.gaps",
    "update",
    "readiness",
    "drift.items",
    "runtime.codex_cli",
    "runtime.claude_code",
    "journal",
    "since_last_check",
    "checkpoint.pending",
    "checkpoint.pending.changed_files",
    "checkpoint.pending.blockers",
    "checkpoint.pending.proposed_subject",
    "summary.changed_files",
    "safety.blocks",
    "proposal.message",
    "validation",
)
CODEX_END_APPROVAL_GATES = (
    "updates_repairs_migrations",
    "file_writes",
    "checkpoint",
    "provider_mutation",
    "publishing_or_spend",
    "customer_contact",
    "private_data",
    "destructive_operations",
    "public_issue_or_proposal",
)
CODEX_END_PUBLIC_PRIVATE_BOUNDARIES = (
    "no_secrets",
    "no_raw_provider_exports",
    "no_raw_transcripts",
    "no_customer_member_data",
    "no_private_runtime_settings",
    "no_raw_finance_legal_records",
)
CODEX_BET_REQUIRED_MB_COMMANDS = (
    "mb status --json --peek",
    "mb start --json",
    "mb doctor repair --plan",
    "mb validate --cross-refs --json",
    "mb checkpoint --plan --json",
    'mb similar-bets "<thesis>" --repo . --json',
    "mb books exposure --repo . --bet bets/YYYY-MM-DD-slug.md --json",
    "mb books exposure --repo . --active --json",
)
CODEX_BET_REQUIRED_JSON_FACTS = (
    "money_path",
    "money_path.objects.proof.quality",
    "validation.file_contracts",
    "content_strategy",
    "ranked_actions",
    "update",
    "readiness",
    "drift.items",
    "brain.bets",
    "brain.bets.active",
    "brain.bets.due_soon",
    "brain.bets.overdue",
    "brain.bets.exit_criteria",
    "relationship_health.sections.bets",
    "relationship_health.gaps",
    "checkpoint.pending",
    "checkpoint.pending.blockers",
    "books",
    "runtime.codex_cli",
    "runtime.claude_code",
)
CODEX_BET_APPROVAL_GATES = (
    "updates_repairs_migrations",
    "file_writes",
    "checkpoint",
    "provider_mutation",
    "publishing_or_spend",
    "customer_contact",
    "private_data",
    "destructive_operations",
    "structured_collection",
    "public_issue_or_proposal",
)
CODEX_BET_PUBLIC_PRIVATE_BOUNDARIES = (
    "no_secrets",
    "no_raw_provider_exports",
    "no_raw_transcripts",
    "no_customer_member_data",
    "no_private_runtime_settings",
    "no_private_dms_or_gated_communities",
    "no_raw_finance_legal_records",
    "no_raw_ledger_rows",
)
CODEX_ADS_REQUIRED_MB_COMMANDS = (
    "mb status --json --peek",
    "mb start --json",
    "mb doctor repair --plan",
    "mb connect doctor --json",
    "mb connect plan",
    'mb launch check "$SITE_REPO" --business-repo "$BUSINESS_REPO" --json',
    'mb site check "$SITE_REPO" --business-repo "$BUSINESS_REPO" --json',
    "mb validate --cross-refs --json",
    "mb checkpoint --plan --json",
)
CODEX_ADS_REQUIRED_JSON_FACTS = (
    "money_path",
    "money_path.objects.proof.quality",
    "money_path.objects.cta_path",
    "money_path.objects.channel_strategy",
    "money_path.objects.active_push",
    "validation.file_contracts",
    "content_strategy",
    "content_strategy.overall_state",
    "content_strategy.simple_entry_point",
    "content_strategy.layers",
    "ranked_actions",
    "update",
    "readiness",
    "drift.items",
    "integrations",
    "measurement",
    "measurement.available",
    "measurement.state",
    "measurement.facts.expected_events",
    "measurement.facts.instrumentation",
    "measurement.blocked_count",
    "measurement.manual_count",
    "relationship_health.gaps",
    "checkpoint.pending",
    "checkpoint.pending.blockers",
    "runtime.codex_cli",
    "runtime.claude_code",
    "state",
    "blocked",
    "manual",
    "evidence",
    "facts.expected_events",
    "facts.instrumentation",
    "facts.provider_state",
    "facts.app_stack",
    "facts.deploy",
    "facts.commerce",
    "facts.email",
    "facts.measurement",
    "recommended_action",
    "source",
    "child_descriptor",
)
CODEX_ADS_APPROVAL_GATES = (
    "updates_repairs_migrations",
    "file_writes",
    "checkpoint",
    "provider_mutation",
    "publishing_or_spend",
    "customer_contact",
    "private_data",
    "destructive_operations",
    "structured_collection",
    "public_issue_or_proposal",
    "account_change",
    "upload_assets",
    "budget_change",
    "campaign_publish",
    "conversion_upload",
    "gtm_publish",
)
CODEX_ADS_PUBLIC_PRIVATE_BOUNDARIES = (
    "no_secrets",
    "no_raw_provider_exports",
    "no_raw_transcripts",
    "no_customer_member_data",
    "no_private_runtime_settings",
    "no_private_dms_or_gated_communities",
    "no_raw_finance_legal_records",
    "no_oauth_tokens",
    "no_conversion_uploads",
    "no_account_identifiers_in_public_examples",
)
CODEX_ORGANIC_REQUIRED_MB_COMMANDS = (
    "mb status --json --peek",
    "mb start --json",
    "mb doctor repair --plan",
    "mb validate --cross-refs --json",
    "mb checkpoint --plan --json",
)
CODEX_ORGANIC_REQUIRED_JSON_FACTS = (
    "money_path",
    "money_path.objects.proof.quality",
    "money_path.objects.channel_strategy",
    "money_path.objects.active_push",
    "validation.file_contracts",
    "content_strategy",
    "content_strategy.overall_state",
    "content_strategy.simple_entry_point",
    "content_strategy.layers",
    "content_strategy.layers.distribution",
    "content_strategy.layers.channels",
    "content_strategy.layers.accounts",
    "content_strategy.layers.people",
    "content_strategy.findings",
    "ranked_actions",
    "update",
    "readiness",
    "drift.items",
    "relationship_health.gaps",
    "checkpoint.pending",
    "checkpoint.pending.blockers",
    "runtime.codex_cli",
    "runtime.claude_code",
)
CODEX_ORGANIC_APPROVAL_GATES = (
    "updates_repairs_migrations",
    "file_writes",
    "checkpoint",
    "provider_mutation",
    "publishing_or_spend",
    "customer_contact",
    "private_data",
    "destructive_operations",
    "structured_collection",
    "public_issue_or_proposal",
)
CODEX_ORGANIC_PUBLIC_PRIVATE_BOUNDARIES = (
    "no_secrets",
    "no_raw_provider_exports",
    "no_raw_transcripts",
    "no_customer_member_data",
    "no_private_runtime_settings",
    "no_private_dms_or_gated_communities",
    "no_raw_finance_legal_records",
)
CODEX_SITE_REQUIRED_MB_COMMANDS = (
    "mb status --json --peek",
    "mb start --json",
    "mb doctor repair --plan",
    "mb connect doctor --json",
    'mb launch check "$SITE_REPO" --business-repo "$BUSINESS_REPO" --json',
    'mb site check "$SITE_REPO" --business-repo "$BUSINESS_REPO" --json',
    "mb validate --cross-refs --json",
    "mb checkpoint --plan --json",
)
CODEX_SITE_REQUIRED_JSON_FACTS = (
    "money_path",
    "money_path.objects.proof.quality",
    "money_path.objects.cta_path",
    "money_path.objects.channel_strategy",
    "money_path.objects.active_push",
    "validation.file_contracts",
    "content_strategy",
    "content_strategy.overall_state",
    "content_strategy.simple_entry_point",
    "content_strategy.layers",
    "ranked_actions",
    "update",
    "readiness",
    "drift.items",
    "integrations",
    "measurement",
    "measurement.available",
    "measurement.state",
    "measurement.facts.expected_events",
    "measurement.facts.instrumentation",
    "measurement.blocked_count",
    "measurement.manual_count",
    "relationship_health.gaps",
    "checkpoint.pending",
    "checkpoint.pending.blockers",
    "runtime.codex_cli",
    "runtime.claude_code",
    "state",
    "blocked",
    "manual",
    "evidence",
    "facts.expected_events",
    "facts.instrumentation",
    "facts.provider_state",
    "facts.app_stack",
    "facts.deploy",
    "facts.commerce",
    "facts.email",
    "facts.measurement",
    "recommended_action",
    "source",
    "child_descriptor",
)
CODEX_SITE_APPROVAL_GATES = (
    "updates_repairs_migrations",
    "file_writes",
    "checkpoint",
    "provider_mutation",
    "publishing_or_spend",
    "customer_contact",
    "private_data",
    "destructive_operations",
    "structured_collection",
    "public_issue_or_proposal",
    "domain_purchase",
    "dns_change",
    "pages_project",
    "custom_domain_attach",
    "deploy_or_push",
    "account_change",
)
CODEX_SITE_PUBLIC_PRIVATE_BOUNDARIES = (
    "no_secrets",
    "no_raw_provider_exports",
    "no_raw_transcripts",
    "no_customer_member_data",
    "no_private_runtime_settings",
    "no_private_dms_or_gated_communities",
    "no_raw_finance_legal_records",
    "no_absolute_local_paths_in_committed_descriptors",
)
CODEX_SHARED_WORKFLOW_SKILLS = {
    "mb-start": CODEX_START_STATUS_SOURCE_WORKFLOW,
    "mb-status": CODEX_START_STATUS_SOURCE_WORKFLOW,
    "mb-setup": CODEX_SETUP_SOURCE_WORKFLOW,
    "mb-update": CODEX_MAINTENANCE_REPAIR_SOURCE_WORKFLOW,
    "mb-doctor": CODEX_MAINTENANCE_REPAIR_SOURCE_WORKFLOW,
    "mb-think": CODEX_THINK_SOURCE_WORKFLOW,
    "mb-end": CODEX_END_SOURCE_WORKFLOW,
    "mb-bet": CODEX_BET_SOURCE_WORKFLOW,
    "mb-ads": CODEX_ADS_SOURCE_WORKFLOW,
    "mb-organic": CODEX_ORGANIC_SOURCE_WORKFLOW,
    "mb-site": CODEX_SITE_SOURCE_WORKFLOW,
}
REQUIRED_LIFECYCLE_GUIDANCE = (
    "## Codex Lifecycle Workflow Index",
    "## Codex Status Workflow",
    "## Codex Think Route",
    "## Codex End Route",
    f"Engine source workflow: `{CODEX_THINK_SOURCE_WORKFLOW}`",
    f"Engine source workflow: `{CODEX_END_SOURCE_WORKFLOW}`",
    "does not need to contain that engine source file",
    "Shared source required `mb` commands",
    "runtime/login-shell PATH",
    "`runtime.codex_cli.status` is `runtime_mismatch`",
    "`codex_runtime_mb_mismatch`",
    "Shared source required JSON fact paths",
    "Shared source gates",
    "Shared public/private boundaries",
    "Use the global Main Branch skill",
    "route to the matching global",
    "global skill",
    "main-branch",
)
REQUIRED_LIFECYCLE_GUIDANCE_MARKERS = (*REQUIRED_LIFECYCLE_GUIDANCE,)
REQUIRED_LIFECYCLE_SECTION_MARKERS = (
    (
        "## Codex Think Route",
        (
            *(f"- `{command}`" for command in CODEX_THINK_REQUIRED_MB_COMMANDS),
            *(f"- `{fact}`" for fact in CODEX_THINK_REQUIRED_JSON_FACTS),
            *(f"`{gate}`" for gate in CODEX_THINK_APPROVAL_GATES),
            *(f"`{boundary}`" for boundary in CODEX_THINK_PUBLIC_PRIVATE_BOUNDARIES),
        ),
    ),
    (
        "## Codex End Route",
        (
            *(f"- `{command}`" for command in CODEX_END_REQUIRED_MB_COMMANDS),
            *(f"- `{fact}`" for fact in CODEX_END_REQUIRED_JSON_FACTS),
            *(f"`{gate}`" for gate in CODEX_END_APPROVAL_GATES),
            *(f"`{boundary}`" for boundary in CODEX_END_PUBLIC_PRIVATE_BOUNDARIES),
        ),
    ),
)
CODEX_PLUGIN_REQUIRED_MARKERS = (
    "Main Branch",
    "commands",
    "mb-*",
    "business repos",
)
CODEX_WORKFLOW_STATUS_VOCABULARY = (
    "supported",
    "read_only_planning",
    "pending_shared_source_migration",
    "blocked_by_provider_gates",
    "internal_composable",
    "generated_shell_pending",
    "intentionally_unsupported",
)
CODEX_SURFACE_KIND_VOCABULARY = (
    "shared_source",
    "claude_skill",
    "playbook",
    "codex_global_skill",
    "read_only_planning",
    "pending_shared_source_migration",
    "blocked_by_provider_gates",
    "internal_composable",
    "intentionally_unsupported",
)
CODEX_SURFACE_KIND_DESCRIPTIONS = {
    "shared_source": "canonical workflow source under workflows/<workflow>/workflow.md",
    "claude_skill": "Claude Code runtime shell under .claude/skills/<name>/SKILL.md",
    "playbook": "reusable business recipe under .claude/playbooks/<name>/SKILL.md",
    "codex_global_skill": "generated Codex global skill shell under the Codex skills root",
    "read_only_planning": (
        "Codex may inspect facts and plan, but must not claim full workflow parity"
    ),
    "pending_shared_source_migration": "workflow substance still needs a shared source migration",
    "blocked_by_provider_gates": (
        "full execution waits for provider, publishing, spend, or account-mutation gates"
    ),
    "internal_composable": "internal or provisional surface hidden from default user-facing routes",
    "intentionally_unsupported": "outside the current Codex daily-loop support target",
}
CODEX_SOURCE_STATUS_VOCABULARY = (
    "shared_workflow_source",
    "temporary_source_skill_mirror",
    "pending_shared_source_migration",
    "blocked_by_provider_gates",
    "internal_composable",
    "intentionally_unsupported",
)
CODEX_SOURCE_STATUS_DESCRIPTIONS = {
    "shared_workflow_source": (
        "portable workflow semantics live in workflows/<name>/workflow.md and "
        "the checked Claude/Codex shells must preserve that contract"
    ),
    "temporary_source_skill_mirror": (
        "Codex mirrors existing Claude skill or CLI guidance until a shared "
        "workflow source owns both runtime shells"
    ),
    "pending_shared_source_migration": (
        "Codex may use read-only facts or planning guidance, but runtime shells "
        "must wait for a shared source migration"
    ),
    "blocked_by_provider_gates": (
        "planning or review may be useful, but execution waits for explicit provider, "
        "publishing, spend, customer-contact, or account-mutation gates"
    ),
    "internal_composable": (
        "internal or provisional surface that may compose other workflows but is not "
        "a default user-facing route"
    ),
    "intentionally_unsupported": "outside the current Codex daily-loop target",
}

CODEX_WORKFLOW_INVENTORY: tuple[dict[str, Any], ...] = (
    {
        "id": "daily-start-status",
        "label": "Start, status, and what changed",
        "claude_surface": "/mb-start, /mb-status",
        "claude_skill_sources": ("mb-start", "mb-status"),
        "codex_status": "supported",
        "source_status": "shared_workflow_source",
        "codex_surface": "main-branch skill routes: mb-start, mb-status",
        "codex_entrypoints": ("main-branch mb-start", "main-branch mb-status"),
        "shared_source": CODEX_START_STATUS_SOURCE_WORKFLOW,
        "commands": ("mb status --json --peek", "mb start --json", "mb doctor repair --plan"),
        "contract_checks": (
            "intent",
            "required_mb_commands",
            "required_json_facts",
            "approval_gates",
            "read_boundaries",
            "write_boundaries",
            "runtime_mismatch_gate",
            "read_before_write_boundary",
            "one_next_route_core_flow",
            "status_marker_approval",
            "core_flow",
            "public_private_boundaries",
        ),
        "notes": (
            "Codex starts from deterministic status/start facts, translates them "
            "into business language, and routes one next Main Branch move."
        ),
    },
    {
        "id": "daily-setup",
        "label": "Setup and onboarding",
        "claude_surface": "/mb-setup",
        "claude_skill_sources": ("mb-setup",),
        "codex_status": "supported",
        "source_status": "shared_workflow_source",
        "codex_surface": "main-branch skill route: mb-setup",
        "codex_entrypoints": ("main-branch mb-setup",),
        "shared_source": CODEX_SETUP_SOURCE_WORKFLOW,
        "commands": (
            "mb --version",
            "mb onboard --help",
            "mb status --json --peek",
            "mb start --json",
            "mb doctor repair --plan",
        ),
        "contract_checks": (
            "intent",
            "required_mb_commands",
            "required_json_facts",
            "approval_gates",
            "read_boundaries",
            "write_boundaries",
            "target_folder_confirmation",
            "setup_intent_boundary",
            "core_flow",
            "public_private_boundaries",
        ),
        "notes": (
            "Codex treats setup prompts as onboarding intent, confirms the target "
            "folder, and asks before setup writes, GitHub creation, or checkpoints."
        ),
    },
    {
        "id": "daily-maintenance-repair",
        "label": "Update, doctor, and repair planning",
        "claude_surface": "/mb-update, /mb-start repair routing",
        "claude_skill_sources": ("mb-update",),
        "codex_status": "supported",
        "source_status": "shared_workflow_source",
        "codex_surface": "main-branch skill routes: mb-update, mb-doctor",
        "codex_entrypoints": (
            "main-branch mb-update",
            "main-branch mb-doctor",
        ),
        "shared_source": CODEX_MAINTENANCE_REPAIR_SOURCE_WORKFLOW,
        "commands": (
            "mb --version",
            "mb status --json --peek",
            "mb start --json",
            "mb doctor repair --plan",
            "mb doctor repair --plan --json",
            "mb update --check --json",
        ),
        "contract_checks": (
            "intent",
            "required_mb_commands",
            "required_json_facts",
            "approval_gates",
            "read_boundaries",
            "write_boundaries",
            "read_before_write_boundary",
            "repair_plan_core_flow",
            "safe_to_apply_state",
            "runtime_mismatch_gate",
            "core_flow",
            "public_private_boundaries",
        ),
        "notes": (
            "Codex may inspect plans and explain next steps. Applying updates, "
            "repairs, migrations, or setup writes requires explicit approval."
        ),
    },
    {
        "id": "think-codify",
        "label": "Think, research, decide, and codify",
        "claude_surface": "/mb-think",
        "claude_skill_sources": ("mb-think",),
        "codex_status": "supported",
        "source_status": "shared_workflow_source",
        "codex_surface": "main-branch skill route: mb-think plus AGENTS.md#codex-think-route",
        "codex_entrypoints": ("main-branch mb-think",),
        "shared_source": CODEX_THINK_SOURCE_WORKFLOW,
        "commands": CODEX_THINK_REQUIRED_MB_COMMANDS,
        "contract_checks": (
            "intent",
            "required_mb_commands",
            "required_json_facts",
            "approval_gates",
            "read_boundaries",
            "write_boundaries",
            "core_flow",
            "public_private_boundaries",
        ),
        "notes": (
            "Codex uses the shared mb-think contract for research depth, source "
            "privacy, decision routing, codification, and approval gates."
        ),
    },
    {
        "id": "end-checkpoint-save",
        "label": "End, checkpoint, and save business memory",
        "claude_surface": "/mb-end, mb checkpoint",
        "claude_skill_sources": ("mb-end",),
        "codex_status": "supported",
        "source_status": "shared_workflow_source",
        "codex_surface": "main-branch skill route: mb-end",
        "codex_entrypoints": ("main-branch mb-end",),
        "shared_source": CODEX_END_SOURCE_WORKFLOW,
        "commands": CODEX_END_REQUIRED_MB_COMMANDS,
        "contract_checks": (
            "intent",
            "required_mb_commands",
            "required_json_facts",
            "approval_gates",
            "read_boundaries",
            "write_boundaries",
            "core_flow",
            "public_private_boundaries",
            "save_state_language",
        ),
        "notes": (
            "Codex uses the shared mb-end contract for status scan, checkpoint "
            "plan, final thought capture, crystallize-lite/deep when available, "
            "owner-facing save states, approval-gated save, and warm close."
        ),
    },
    {
        "id": "workflow-discovery",
        "label": "Workflow discovery and support inventory",
        "claude_surface": "/mb-help and docs",
        "claude_skill_sources": ("mb-help",),
        "codex_status": "supported",
        "source_status": "temporary_source_skill_mirror",
        "codex_surface": "main-branch skill route: mb-help",
        "codex_entrypoints": ("main-branch mb-help",),
        "commands": ("mb workflow list --runtime codex --json",),
        "contract_checks": ("inventory_json_schema", "support_boundary_copy"),
        "notes": "Codex users can inspect supported, pending, and unsupported workflow surfaces.",
    },
    {
        "id": "bets",
        "label": "Bet lifecycle",
        "surface_type": "skill",
        "claude_surface": "/mb-bet",
        "claude_skill_sources": ("mb-bet",),
        "codex_status": "read_only_planning",
        "source_status": "shared_workflow_source",
        "codex_surface": "Read-only planning and file guidance through global mb-bet skill",
        "codex_entrypoints": ("main-branch mb-bet",),
        "shared_source": CODEX_BET_SOURCE_WORKFLOW,
        "commands": CODEX_BET_REQUIRED_MB_COMMANDS,
        "contract_checks": (
            "intent",
            "required_mb_commands",
            "required_json_facts",
            "approval_gates",
            "read_boundaries",
            "write_boundaries",
            "bet_lifecycle_modes",
            "bet_file_contract",
            "typed_links_and_reverse_links",
            "cross_ref_validation",
            "aggregate_exposure_privacy",
            "public_narration_boundary",
            "codex_read_only_planning_boundary",
            "core_flow",
            "public_private_boundaries",
        ),
        "status_reason": (
            "Bet lifecycle substance has a shared source, but Codex remains "
            "read-only planning and file guidance until runtime smoke proves "
            "lifecycle writes."
        ),
        "notes": "Codex may inspect bet facts, explain contract gaps, and propose guarded edits.",
    },
    {
        "id": "ads",
        "label": "Ads and paid creative",
        "surface_type": "skill",
        "claude_surface": "/mb-ads",
        "claude_skill_sources": ("mb-ads",),
        "codex_status": "read_only_planning",
        "source_status": "shared_workflow_source",
        "codex_surface": "Read-only planning and file guidance through global mb-ads skill",
        "codex_entrypoints": ("main-branch mb-ads",),
        "shared_source": CODEX_ADS_SOURCE_WORKFLOW,
        "commands": CODEX_ADS_REQUIRED_MB_COMMANDS,
        "contract_checks": (
            "intent",
            "required_mb_commands",
            "required_json_facts",
            "approval_gates",
            "read_boundaries",
            "write_boundaries",
            "ads_modes",
            "research_handoff",
            "site_readiness_handoff",
            "proof_quality_boundary",
            "artifact_routing",
            "google_ads_playbook",
            "provider_gates",
            "upload_spend_publish_boundary",
            "gtm_conversion_boundary",
            "codex_read_only_planning_boundary",
            "core_flow",
            "public_private_boundaries",
        ),
        "status_reason": (
            "Ads workflow substance has a shared source, but Codex remains read-only "
            "planning and file guidance until runtime smoke proves paid creative writes, "
            "provider mutation, uploads, publishing, spend, account changes, GTM publishes, "
            "conversion uploads, and customer contact."
        ),
        "notes": (
            "Codex may inspect ads, provider, measurement, and proof facts, propose "
            "guarded drafts and launch plans, and name exact file targets. No provider "
            "mutation, spend, upload, publishing, account change, GTM publish, conversion "
            "upload, or customer contact is supported."
        ),
    },
    {
        "id": "organic-content",
        "label": "Organic content and newsletter planning",
        "surface_type": "skill",
        "claude_surface": "/mb-organic and related playbooks",
        "claude_skill_sources": ("mb-organic",),
        "codex_status": "read_only_planning",
        "source_status": "shared_workflow_source",
        "codex_surface": "Read-only planning and file guidance through global mb-organic skill",
        "codex_entrypoints": ("main-branch mb-organic",),
        "shared_source": CODEX_ORGANIC_SOURCE_WORKFLOW,
        "commands": CODEX_ORGANIC_REQUIRED_MB_COMMANDS,
        "contract_checks": (
            "intent",
            "required_mb_commands",
            "required_json_facts",
            "approval_gates",
            "read_boundaries",
            "write_boundaries",
            "organic_modes",
            "content_strategy_json_paths",
            "mining_handoff",
            "source_privacy_boundaries",
            "artifact_routing",
            "proof_quality_boundary",
            "publishing_boundary",
            "account_mutation_boundary",
            "codex_read_only_planning_boundary",
            "core_flow",
            "public_private_boundaries",
        ),
        "status_reason": (
            "Organic workflow substance has a shared source, but Codex remains "
            "read-only planning and file guidance until runtime smoke proves "
            "organic drafting writes."
        ),
        "notes": (
            "Codex may inspect content strategy and proof facts, propose guarded "
            "drafts, review existing drafts, and name exact file targets. No "
            "publishing, scheduling, upload, account mutation, spend, or customer "
            "contact is supported."
        ),
    },
    {
        "id": "site",
        "label": "Site and page production",
        "surface_type": "skill",
        "claude_surface": "/mb-site",
        "claude_skill_sources": ("mb-site",),
        "codex_status": "read_only_planning",
        "source_status": "shared_workflow_source",
        "codex_surface": "Read-only planning and file guidance through global mb-site skill",
        "codex_entrypoints": ("main-branch mb-site",),
        "shared_source": CODEX_SITE_SOURCE_WORKFLOW,
        "commands": CODEX_SITE_REQUIRED_MB_COMMANDS,
        "contract_checks": (
            "intent",
            "required_mb_commands",
            "required_json_facts",
            "approval_gates",
            "read_boundaries",
            "write_boundaries",
            "site_modes",
            "site_shapes",
            "site_readiness_json_shape",
            "repo_descriptor_boundary",
            "provider_gates",
            "domain_dns_deploy_boundary",
            "publishing_boundary",
            "account_mutation_boundary",
            "codex_read_only_planning_boundary",
            "core_flow",
            "public_private_boundaries",
        ),
        "status_reason": (
            "Site workflow substance has a shared source, but Codex remains read-only "
            "planning and file guidance until runtime smoke proves site writes, builds, "
            "deploys, and publishing."
        ),
        "notes": (
            "Codex may inspect site readiness, descriptors, and business facts, then "
            "propose guarded file targets. No site writes, build, deploy, DNS, domain, "
            "publishing, provider mutation, account changes, spend, or customer contact "
            "is supported."
        ),
    },
    {
        "id": "books",
        "label": "Private books review",
        "surface_type": "skill",
        "claude_surface": "/mb-books",
        "claude_skill_sources": ("mb-books",),
        "codex_status": "read_only_planning",
        "source_status": "temporary_source_skill_mirror",
        "codex_surface": "Read-only books review through global mb-books skill",
        "codex_entrypoints": ("main-branch mb-books",),
        "commands": ("mb books check . --json", 'mb books doctor --repo "$BOOKS_REPO" --json'),
        "status_reason": (
            "Codex has a safe read-only route but no shared workflow source or "
            "runtime proof for books repo setup and close execution."
        ),
        "notes": (
            "Use safe aggregate CLI facts. Do not read evidence bytes, quote doctor "
            "output or financial details, post entries, or edit journals."
        ),
    },
    {
        "id": "wiki",
        "label": "Wiki and personal atomic notes",
        "surface_type": "skill",
        "claude_surface": "/mb-wiki",
        "claude_skill_sources": ("mb-wiki",),
        "codex_status": "intentionally_unsupported",
        "source_status": "intentionally_unsupported",
        "codex_surface": "Boundary explainer only; no Codex execution route",
        "codex_entrypoints": ("main-branch mb-wiki",),
        "commands": (),
        "status_reason": "Specialty personal-wiki workflow outside the current Codex target.",
        "notes": "Specialty workflow outside the current Codex command target.",
    },
    {
        "id": "google-ads-search-launch-playbook",
        "label": "Google Ads search launch playbook",
        "surface_type": "playbook",
        "playbook_status": "draft_manual",
        "claude_surface": "google-ads-search-launch playbook",
        "claude_skill_sources": (),
        "claude_playbook_sources": ("google-ads-search-launch",),
        "codex_status": "blocked_by_provider_gates",
        "source_status": "blocked_by_provider_gates",
        "codex_surface": "Draft/manual playbook behind mb-ads; no direct Codex global skill",
        "playbook_source": "playbooks/google-ads-search-launch/playbook.md",
        "commands": ("mb status --json --peek", "mb connect doctor --json"),
        "status_reason": (
            "This is a reusable launch recipe, not a first-class skill. It stays "
            "manual behind mb-ads until provider/spend/publish gates and runtime "
            "smoke support more than planning."
        ),
        "notes": (
            "No Google Ads account mutation, spend, upload, or publishing is supported in Codex."
        ),
    },
    {
        "id": "skill-authoring",
        "label": "Skill concept, draft, and review",
        "surface_type": "skill",
        "claude_surface": "/mb-skill-concept, /mb-skill-brief-draft, /mb-skill-review",
        "claude_skill_sources": (
            "mb-skill-concept",
            "mb-skill-brief-draft",
            "mb-skill-review",
        ),
        "codex_status": "intentionally_unsupported",
        "source_status": "intentionally_unsupported",
        "codex_surface": "Boundary explainer only; no Codex execution route",
        "codex_entrypoints": (
            "main-branch mb-skill-concept",
            "main-branch mb-skill-brief-draft",
            "main-branch mb-skill-review",
        ),
        "commands": (),
        "status_reason": "Engine-contributor workflow, not a business runtime surface.",
        "notes": "Engine-contributor workflow, not a business runtime surface.",
    },
)


def _repo_flag(repo: str | Path | None) -> str:
    """The shared `--repo` rule (#1072); see `engine.repo_flag`."""

    return engine_mod.repo_flag(repo)


def repair_command(repo: str | Path | None = None) -> str:
    """The Codex apply command, naming the business repo when one is known (#1072)."""

    return f"mb doctor repair{_repo_flag(repo)} --apply --only codex"


def repair_text(repo: str | Path | None = None) -> str:
    """The Codex plan-then-apply sentence, naming the business repo when known (#1072)."""

    flag = _repo_flag(repo)
    return (
        f"Run `mb doctor repair{flag} --plan --only codex`, review, then "
        f"`mb doctor repair{flag} --apply --only codex`."
    )


def _global_plugin_root_unresolved() -> tuple[Path, bool]:
    """The global plugin root as configured, before links are resolved, and
    whether it came from `MAINBRANCH_CODEX_PLUGIN_ROOT`."""

    override = os.environ.get("MAINBRANCH_CODEX_PLUGIN_ROOT", "").strip()
    if override:
        return Path(override).expanduser(), True
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", "") or Path.home() / "AppData" / "Local")
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", "") or Path.home() / ".local" / "share")
    return (base / "mainbranch" / "codex").expanduser(), False


def global_plugin_source_root() -> Path:
    """Return the user-local source directory for the global Codex plugin."""

    return _global_plugin_root_unresolved()[0].resolve()


def global_plugin_root_link() -> Path | None:
    """A link at the global plugin root, or at its `mainbranch` folder (#1067).

    Main Branch names those folders; a link there leads somewhere a person
    chose, so the cleanup does not walk through it. None when neither is a link.
    """

    root, overridden = _global_plugin_root_unresolved()
    for candidate in (root,) if overridden else (root.parent, root):
        if candidate.is_symlink():
            return candidate
    return None


def _symlinked_ancestor(base: Path, path: Path) -> Path | None:
    """The first folder strictly between `base` and `path` that is a link (#1067)."""

    current = base
    for part in path.relative_to(base).parts[:-1]:
        current = current / part
        if current.is_symlink():
            return current
    return None


def _read_text_or_none(path: Path) -> str | None:
    """The file's UTF-8 text, "" when it is absent, None when it cannot be read.

    Unreadable means an OS error on read or bytes that are not UTF-8 (#1067).
    """

    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def global_skill_source_root() -> Path:
    """Return the user-local directory where Codex global skills are installed."""

    override = os.environ.get("MAINBRANCH_CODEX_SKILLS_ROOT", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return (Path.home() / ".codex" / "skills").expanduser().resolve()


def global_skill_path() -> Path:
    return global_skill_source_root() / CODEX_GLOBAL_SKILL_RELATIVE_PATH


def global_skill_file_path(name: str) -> Path:
    return global_skill_source_root() / name / "SKILL.md"


def _is_retired_mainbranch_global_skill(path: Path, name: str) -> bool:
    """Whether the retired skill at `path` (a link is read through) is one `mb` wrote.

    Proven by content: a known generated version of `<name>/SKILL.md`. A
    person's edited copy, or their own skill at that name, is not.
    """

    skill_file = path / "SKILL.md" if path.is_dir() else path
    return skill_file.parent.name == name and _is_known_generated_content(skill_file)


def codex_marketplace_add_command() -> str:
    return f"codex plugin marketplace add {shlex.quote(str(global_plugin_source_root()))}"


_DEFAULT_AGENTS = """\
{{CODEX_GUIDANCE_METADATA}}

# {{BUSINESS_NAME}}

Main Branch business repo instructions for Codex.

## Codex Operating Contract

Main Branch CLI facts are the source of truth for repo health, setup, runtime
wiring, updates, graph/status signals, provider readiness, and repair paths.
When the operator asks to start, begin, get oriented, triage the day, or decide
what to do next, use the global Main Branch skill route (`mb-start`,
`mb-status`, or the closest `mb-*` route) or the read-only `mb` fact commands
below. Do not pretend Claude Code slash skills work in Codex.

Start in this repo. Before setup, routing, migration, update, or repair advice,
run the runtime preflight and read-only checks that fit the situation:

```bash
command -v mb
mb --version
mb status --json --peek
mb start --json
mb doctor repair --plan
```

This file is managed by Main Branch. Run
`mb doctor repair --plan --only codex` if setup or runtime guidance looks
stale. If `mb --version` reports an older or different version, stop before
status or repair commands and tell the operator to put the current Main Branch
install earlier on the runtime/login-shell PATH.

After `mb status --json --peek` or `mb start --json`, stop if
`runtime.codex_cli.status` is `runtime_mismatch` or any `drift.items[].id`
equals `codex_runtime_mb_mismatch`. Treat that as a runtime `mb` mismatch: tell
the operator to fix the runtime/login-shell PATH and rerun read-only checks
before Main Branch advice, repair planning, or writes.

Use `mb status --json --peek` as the default daily briefing before routing the
operator. It names readiness, drift, onboarding progress, update state, GitHub
activity, provider signals, recent work, MoneyPath, ranked actions, bets,
pushes, and checkpoint state. Do not replace those facts with ad hoc shell
inspection unless `mb` says a section is unavailable or the command itself is
missing.

Read-only commands can be run without asking first. Commands that write files,
refresh local runtime wiring, update packages, migrate business files, create
checkpoints, publish, spend money, contact customers, email, or mutate provider
accounts require explicit operator approval before applying.

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
- `No GitHub origin remote` or `No origin remote` -> no connected GitHub backup
  or shared task source;
- `PR/issue facts` or `PR and issue facts` -> GitHub task and proposal context.

When finishing first-run setup, lead with the owner outcome before the receipt:
created, saved, synced to GitHub when requested, and ready to open in Claude
Code. Put commands, remotes, branches, validation checks, and local wiring in a
short technical receipt after that outcome.

Use the `vocabulary` block from `mb status --json --peek` when present. If
`core/vocabulary.md` says this business calls pushes drops, launches,
challenges, or promos, use that word in operator-facing prose while preserving
canonical paths, frontmatter, JSON keys, validator rules, and command names.

## Codex Lifecycle Workflow Index

This tracked `AGENTS.md` file is the repo-level Codex bootstrap. The Main
Branch Codex skill bundle is installed globally once per user and routes `mb-*`
workflow names over deterministic `mb` facts. Business repos keep this
lightweight `AGENTS.md` guidance instead of tracked repo-local plugin or skill
copies. `mb doctor repair --only codex` refreshes this file and installs or
repairs the global skills.

Use the global Main Branch skills for Main Branch daily routes only. Do not
create repo-local Codex plugin manifests, copied Claude skill trees, or
symlinked Claude skills unless a future `mb` command or issue says that surface
is supported for this repo.
The global `main-branch` skill is an index; named global skills such as
`mb-start`, `mb-status`, `mb-think`, `mb-bet`, `mb-ads`, `mb-organic`, and
`mb-site` carry the workflow routes.

Use this index to map natural Codex requests:

- **Start the day / what next / get oriented:** use the Codex Start Workflow
  below. Run `mb status --json --peek` first, then `mb start --json` when
  runtime handoff or adapter-readiness facts matter.
- **Inspect status / what changed / what is stale:** use the Codex Status
  Workflow below.
  Answer from `ranked_actions`, `since_last_check`, `journal`, `money_path`,
  `validation.file_contracts`, `content_strategy`, `integrations`,
  `readiness`, and `drift.items`.
- **Think / research / decide / codify:** use the Codex Think Route below. Start
  from `mb` facts, choose a research depth, and ask before writing durable
  business files.
- **Bets, ads, organic, or site work:** route to the matching global
  `mb-bet`, `mb-ads`, `mb-organic`, or `mb-site` skill for read-only planning
  and file guidance. Do not claim full Codex workflow parity. Do not perform
  lifecycle writes, site writes/builds/deploys, provider mutations,
  publishing, spend, domain/DNS changes, uploads, account changes, or
  customer contact unless `mb workflow list --runtime codex --json` reports a
  support level and runtime smoke evidence that explicitly allows the action.

Use `mb doctor repair --plan --only codex` to inspect global skill wiring.

## Codex Start Workflow

This is the Codex-native start workflow.

1. Run `mb status --json --peek` from the current working directory. Use the
   repo markers in that JSON to confirm this is the business repo. If the
   status report says this is not a Main Branch repo or the command is missing,
   ask for the business repo path instead of guessing.
2. Use the status JSON as the source of truth for
   readiness, drift, onboarding, update severity, GitHub facts, provider
   readiness, recent work, MoneyPath, ranked actions, bets, pushes,
   vocabulary, and checkpoint state.
3. Run `mb start --json` when you need runtime handoff, repo-boundary, or
   adapter-readiness facts.
4. Stop before more checks if either status or start reports
   `runtime.codex_cli.status` as `runtime_mismatch`, or if `drift.items`
   includes `codex_runtime_mb_mismatch`. Tell the operator to fix the
   runtime/login-shell PATH first.
5. Run `mb doctor repair --plan` before recommending setup or repair. Quote the
   exact repair command from the plan. Ask before any write/apply command.
6. If status says an update is required, route to the cited `mb update` command
   and ask before running it. After an approved update, rerun
   `mb status --json --peek`.
7. Resume onboarding from status facts. In rich repos, read existing `core/`
   files before asking bounded missing-profile questions.
8. Present one clear business route: frame a bet, think through a decision,
   advance a push, draft a playbook, repair the repo, review provider
   readiness, save a checkpoint, or inspect a specific offer.

Use numbered lists for operator choices, with one active choice namespace per
turn. If the operator replies with an ambiguous number, ask what they meant
before acting.

## Codex Status Workflow

This is the Codex-native status workflow.

1. Run `mb status --json --peek`.
2. Treat the JSON as the source of truth for setup, update, drift, GitHub,
   onboarding, integrations, bets, recent work, since-last-check,
   `content_strategy`, `money_path`, `validation.file_contracts`, vocabulary,
   checkpoint state, and `ranked_actions`.
3. Stop before business routing if `runtime.codex_cli.status` is
   `runtime_mismatch` or `drift.items` includes `codex_runtime_mb_mismatch`.
   Tell the operator to fix the runtime/login-shell PATH and rerun the
   read-only checks first.
4. Lead with the top `ranked_actions` entry when the operator asks what to do
   next. Include the reason and cited signal summaries. After it, name the
   first warn-level `relationship_health.gaps` item once with its repair.
5. For "what changed?" answer from `since_last_check.journal` first, then
   top-level `journal` for recent context.
6. For provider questions, read `integrations` first. Run `mb connect plan` or
   `mb connect doctor --json` only when the operator needs choices or repair
   commands.
7. Use `money_path` for customer progress, offer, proof, CTA, channel, push,
   playbook, page readiness, and outcome feedback questions. Keep language
   evidence-based: legible, supported, connected, instrumented.
8. Use `validation.file_contracts` when a business file exists but is missing
   the shape needed for the next workflow. Route offer-shape gaps to
   `mb-think`; ask before editing files.
9. Use `content_strategy` for content strategy health, layered channel/account
   files, stale platform rules, or disconnected content layers.

Do not mutate the last-check marker unless the operator explicitly says this is
the daily check-in and wants it recorded.

## Codex Think Route

This is Codex-native guidance for the existing `mb-think` shared workflow
source. Treat this section as the natural-language Codex route. It does not
mean all Main Branch skills work in Codex.

Engine source workflow: `workflows/mb-think/workflow.md`. This business repo
does not need to contain that engine source file. Treat this generated
`AGENTS.md` section as the Codex shell for that source unless you are explicitly
working inside the Main Branch engine repo.

Shared source required `mb` commands:

- `mb status --json --peek`
- `mb start --json`
- `mb doctor repair --plan`
- `mb connect doctor --json`
- `mb checkpoint --plan --json`

Shared source required JSON fact paths:

- `money_path`
- `money_path.objects.offer`
- `money_path.objects.proof`
- `money_path.objects.proof.quality`
- `money_path.objects.product_ladder`
- `money_path.objects.cta_path`
- `money_path.objects.channel_strategy`
- `money_path.objects.active_push`
- `money_path.objects.outcome_feedback_loop`
- `money_path.ranked_actions`
- `validation.file_contracts`
- `content_strategy`
- `ranked_actions`
- `update`
- `readiness`
- `drift.items`
- `books`
- `runtime.codex_cli`
- `runtime.claude_code`

Shared source gates: `updates_repairs_migrations`, `file_writes`,
`checkpoint`, `provider_mutation`, `publishing_or_spend`, `customer_contact`,
`private_data`, `destructive_operations`, `structured_collection`,
`public_issue_or_proposal`.

Shared public/private boundaries: `no_secrets`, `no_raw_provider_exports`,
`no_raw_transcripts`, `no_customer_member_data`,
`no_private_runtime_settings`, `no_private_dms_or_gated_communities`,
`no_raw_finance_legal_records`.

Use it when the operator asks to think through an offer, research a market,
compare providers, make a decision, or codify what was learned.

Before advice, run the read-only facts that fit the situation:

```bash
mb status --json --peek
mb start --json
mb doctor repair --plan
```

If the task touches provider readiness, run `mb connect doctor --json`. Before
recommending a saved checkpoint, run `mb checkpoint --plan --json`. These
commands provide facts and plans; they do not authorize writes.

Choose the smallest honest research depth:

- Level 0: operator memory is enough for a low-risk move.
- Level 1: existing repo context and `mb` facts are enough.
- Level 2: lightweight public or operator-provided research is needed.
- Level 3: multi-source synthesis is needed.
- Level 4: structured approved-source collection is justified.
- Level 5: high-resolution market analysis or field evidence is needed.

Read only the business files needed for the question: `core/`, `research/`,
`decisions/`, `bets/`, `pushes/`, `log/`, and `documents/`. Do not inspect
secrets, raw provider exports, raw transcripts, raw finance/legal records,
customer/member records, private DMs, gated communities, local runtime
settings, or credentials unless the operator gives explicit permission and the
source belongs in the business repo. For transcripts, authenticated community
content, provider recordings, cloud-drive files, exported chats, or mixed
private/business sources, inventory sources and apply manifest-first
allow/skip filters before reading content; commit synthesized findings, not raw
payloads.

Ask before creating, editing, moving, deleting, archiving, codifying, or
checkpointing business files. Ask before publishing, opening a public issue,
submitting a proposal, spending money, mutating provider state, or contacting
customers.

## Codex End Route

This is Codex-native guidance for the existing `mb-end` shared workflow source.
Treat this section as the natural-language Codex route. It does not mean all
Main Branch skills work in Codex.

Engine source workflow: `workflows/mb-end/workflow.md`. This business repo does
not need to contain that engine source file. Treat this generated `AGENTS.md`
section as the Codex shell for that source unless you are explicitly working
inside the Main Branch engine repo.

Shared source required `mb` commands:

- `mb status --json --peek`
- `mb start --json`
- `mb doctor repair --plan`
- `mb checkpoint --plan --json`
- `mb validate --json`

Shared source required JSON fact paths:

- `money_path`
- `money_path.objects.proof.quality`
- `content_strategy`
- `ranked_actions`
- `relationship_health.gaps`
- `update`
- `readiness`
- `drift.items`
- `runtime.codex_cli`
- `runtime.claude_code`
- `journal`
- `since_last_check`
- `checkpoint.pending`
- `checkpoint.pending.changed_files`
- `checkpoint.pending.blockers`
- `checkpoint.pending.proposed_subject`
- `summary.changed_files`
- `safety.blocks`
- `proposal.message`
- `validation`

Shared source gates: `updates_repairs_migrations`, `file_writes`,
`checkpoint`, `provider_mutation`, `publishing_or_spend`, `customer_contact`,
`private_data`, `destructive_operations`, `public_issue_or_proposal`.

Shared public/private boundaries: `no_secrets`, `no_raw_provider_exports`,
`no_raw_transcripts`, `no_customer_member_data`,
`no_private_runtime_settings`, `no_raw_finance_legal_records`.

Use it when the operator is done, pausing, saving progress, checkpointing, or
asking whether the work is saved. Run a status scan first, build the checkpoint
plan, summarize the session, ask once for a final thought, run crystallize-lite
in-thread or use available subagent tooling, name the owner-facing save state,
and ask before saving.

Owner-facing save states are `drafted`, `saved locally`, `ready to send up`,
`sent for review`, `landed in main`, and `blocked by unrelated cleanup`.
Technical branch, proposal, merge, and working-tree details come second unless
the operator asks for plumbing.

Before the checkpoint, compare changed bets, pushes, decisions, and research
files with `relationship_health.gaps` evidence or records. If a gap names one,
offer one link fix with the field and file; ask at most one question. Otherwise skip.

## Routing Rules

- If `ranked_actions` has entries, lead with the first action, its reason, and
  the cited signal summaries.
- Use `money_path` when the next move depends on customer progress, offer,
  proof, CTA, channel, push, playbook, page readiness, or outcome feedback.
  Keep the language evidence-based: legible, supported, connected,
  instrumented.
- If readiness is blocked or drift has errors, handle repair before output
  work.
- If onboarding is incomplete, use the `onboarding.summary` and checklist from
  status instead of inventing a setup interview.
- Use current Main Branch paths for new work. If status or doctor facts report
  old structural paths, treat them as migration input and follow the repair
  plan before creating new coordinated work.
- If the operator asks for publishing, spend, provider mutation, customer
  contact, migration, checkpoint creation, or file writes, plan first and ask
  for explicit approval.
- If the operator brings a live idea and it is unclear where it belongs, route
  by business meaning: offers are what the business may keep selling; bets are
  time-boxed wagers; pushes are coordinated execution; proof is evidence; and
  decisions explain durable changes.

## Business Folders

- `core/` - the business brain: offer, audience, voice, soul, proof, brand,
  strategy, operations, finance.
- `core/offers/` - per-offer specifics when this is a multi-offer repo.
- `core/proof/` - testimonials, typicality, and reusable proof. Use
  structured permission and offer-link fields when proof should be detectable
  by `mb status`.
- `core/content-strategy.md` - business-level content strategy and index.
- `core/marketing/` - optional distribution, channel, and account strategy.
- `core/people/` - optional founder/person voice source material, beliefs,
  stories, and proof.
- `research/` - dated notes from when you went looking.
- `decisions/` - dated choices, with rationale.
- `bets/` - operating bets with appetite, metric, target, and outcome.
- `pushes/` - coordinated pushes such as launches, drops, challenges, promos.
- `log/` - running activity log.
- `documents/` - anything that does not belong above.

Use `core/content-strategy.md` as the default solo-operator content strategy.
When the business needs more layers, read or write
`core/marketing/distribution-strategy.md`,
`core/marketing/channels/<channel>.md`,
`core/marketing/accounts/<platform>-<account>.md`, and
`core/people/<person>.md`. Weekly content planning should reference those files,
then put specific execution in `pushes/` and results in `log/`.

## Connected Accounts

Never commit API keys, OAuth refresh tokens, service-account JSON, webhook
secrets, MCP tokens, or bearer tokens. Keep secrets in the runtime's local
config, an OS keychain, 1Password, `.env`, or another gitignored local file. If
a tool can spend money, publish, email, or mutate a customer account, verify it
is tethered to this repo and ask for approval before using it.

## Repo Owner

`@{{GH_USERNAME}}`
"""


def _read_template(name: str) -> str:
    try:
        ref = resources.files("mb").joinpath("_data").joinpath("templates").joinpath(name)
        return ref.read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError, AttributeError):
        here = Path(__file__).resolve().parent / "_data" / "templates" / name
        if here.exists():
            return here.read_text(encoding="utf-8")
        return ""


def _render(text: str, mapping: dict[str, str]) -> str:
    out = text
    for key, val in mapping.items():
        out = out.replace("{{" + key + "}}", val)
    return out


def _which(name: str) -> str:
    return shutil.which(name) or ""


def _markdown_h1(path: Path) -> str:
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("# "):
                return stripped[2:].strip()
    except OSError:
        return ""
    return ""


def _repo_owner(repo: Path) -> str:
    codeowners = repo / ".github" / "CODEOWNERS"
    try:
        for raw_line in codeowners.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            for part in parts[1:]:
                if part.startswith("@"):
                    return part.removeprefix("@")
    except OSError:
        pass
    agents = repo / AGENTS_RELATIVE_PATH
    try:
        lines = agents.read_text(encoding="utf-8").splitlines()
    except OSError:
        return "your-gh-username"
    for line in lines:
        stripped = line.strip().strip("`")
        if stripped.startswith("@") and " " not in stripped:
            return stripped.removeprefix("@")
    return "your-gh-username"


def business_name(repo: str | Path) -> str:
    target = Path(repo).expanduser().resolve()
    for relative in ("CLAUDE.md", "AGENTS.md"):
        name = _markdown_h1(target / relative)
        if name and "instructions" not in name.lower():
            return name
    return target.name or "Business"


def render_agents_md(repo: str | Path, *, name: str = "", gh_username: str = "") -> str:
    target = Path(repo).expanduser().resolve()
    template = _read_template(AGENTS_TEMPLATE) or _DEFAULT_AGENTS
    template_hash = guidance_template_hash(template)
    mapping = {
        "BUSINESS_NAME": name.strip() or business_name(target),
        "GH_USERNAME": gh_username.strip() or _repo_owner(target),
        "MAINBRANCH_VERSION": __version__,
        "CODEX_GUIDANCE_METADATA": guidance_metadata_comment(template_hash=template_hash),
    }
    return _render(template, mapping)


def _metadata_free_template(template: str) -> str:
    return template.replace("{{CODEX_GUIDANCE_METADATA}}\n\n", "").replace(
        "{{CODEX_GUIDANCE_METADATA}}\n", ""
    )


def guidance_template_hash(template: str | None = None) -> str:
    source = (
        template if template is not None else (_read_template(AGENTS_TEMPLATE) or _DEFAULT_AGENTS)
    )
    normalized = _metadata_free_template(source).replace("\r\n", "\n").strip() + "\n"
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def guidance_metadata_comment(*, template_hash: str | None = None) -> str:
    digest = template_hash or guidance_template_hash()
    return (
        "<!-- mainbranch:codex-guidance "
        f"schema={CODEX_GUIDANCE_SCHEMA} "
        f"template_hash={digest} "
        f"min_mb={CODEX_GUIDANCE_MIN_MB} -->"
    )


def parse_guidance_metadata(text: str) -> dict[str, str]:
    match = re.search(r"<!--\s*mainbranch:codex-guidance\s+([^>]*)-->", text)
    if not match:
        return {}
    pairs: dict[str, str] = {}
    for item in match.group(1).split():
        if "=" not in item:
            continue
        key, value = item.split("=", 1)
        pairs[key.strip()] = value.strip().strip('"')
    return pairs


def _managed_agents_block(rendered: str) -> str:
    return f"{AGENTS_MANAGED_BEGIN}\n{rendered.rstrip()}\n{AGENTS_MANAGED_END}\n"


def _managed_agents_content(text: str) -> str:
    start = text.find(AGENTS_MANAGED_BEGIN)
    if start == -1:
        return ""
    body_start = text.find("\n", start)
    if body_start == -1:
        return ""
    end = text.find(AGENTS_MANAGED_END, body_start)
    if end == -1:
        return ""
    return text[body_start + 1 : end].strip() + "\n"


_GUIDANCE_METADATA_RE = re.compile(r"<!--\s*mainbranch:codex-guidance\s+[^>]*-->")
_OWNER_LINE_RE = re.compile(r"^`@[^`\s]*`$")
AGENTS_RERUN_STEP = "then run `mb doctor repair --plan --only codex` again."


def _agents_rerun_step(repo: str | Path | None = None) -> str:
    """The closing step of a refusal's manual step, naming the repo when known (#1072)."""

    return f"then run `mb doctor repair{_repo_flag(repo)} --plan --only codex` again."


def _agents_refusal(code: str, reason: str, manual_step: str) -> dict[str, str]:
    return {
        "path": AGENTS_RELATIVE_PATH,
        "code": code,
        "reason": reason,
        "manual_step": manual_step,
    }


def _marker_refusal(existing: str, rerun_step: str = AGENTS_RERUN_STEP) -> dict[str, str] | None:
    """Refuse any managed-marker layout other than one begin before one end (#1052).

    Without both markers in order, Main Branch cannot tell where its guidance
    ends and a person's notes begin, so it writes nothing.
    """

    begins = existing.count(AGENTS_MANAGED_BEGIN)
    ends = existing.count(AGENTS_MANAGED_END)
    if begins == 0 and ends == 0:
        return None
    if (
        begins == 1
        and ends == 1
        and existing.find(AGENTS_MANAGED_BEGIN) < existing.find(AGENTS_MANAGED_END)
    ):
        return None
    if begins == 1 and ends == 0:
        return _agents_refusal(
            "missing_end_marker",
            "AGENTS.md has the Main Branch begin marker but no end marker, so Main "
            "Branch cannot tell where its guidance ends and your own notes begin. "
            "It left the file unchanged.",
            f"Put `{AGENTS_MANAGED_END}` on its own line right after the Main Branch "
            f"guidance (above any notes of your own), {rerun_step}",
        )
    if begins == 0 and ends == 1:
        return _agents_refusal(
            "missing_begin_marker",
            "AGENTS.md has the Main Branch end marker but no begin marker, so Main "
            "Branch cannot tell where its guidance starts. It left the file unchanged.",
            f"Put `{AGENTS_MANAGED_BEGIN}` on its own line right before the Main "
            f"Branch guidance (below any notes of your own), {rerun_step}",
        )
    return _agents_refusal(
        "marker_mismatch",
        f"AGENTS.md has {begins} Main Branch begin marker(s) and {ends} end "
        "marker(s), not one of each in order, so Main Branch cannot tell which text "
        "is its guidance. It left the file unchanged.",
        f"Keep exactly one `{AGENTS_MANAGED_BEGIN}` above the Main Branch guidance "
        f"and one `{AGENTS_MANAGED_END}` below it, {rerun_step}",
    )


def _unrendered_template_hash(body: str) -> str:
    """The template hash of rendered guidance text, with its two fields put back.

    Every template that carried the metadata comment had one `# {{BUSINESS_NAME}}`
    heading as its first line and one `` `@{{GH_USERNAME}}` `` line as its last.
    """

    lines = body.replace("\r\n", "\n").strip().split("\n")
    if len(lines) < 2 or not lines[0].startswith("# ") or not _OWNER_LINE_RE.match(lines[-1]):
        return ""
    lines[0] = "# {{BUSINESS_NAME}}"
    lines[-1] = "`@{{GH_USERNAME}}`"
    return hashlib.sha256(("\n".join(lines) + "\n").encode("utf-8")).hexdigest()[:16]


def _old_generated_span(existing: str) -> tuple[int, int] | None:
    """Where an older generated AGENTS.md sits inside `existing`, or None (#1052).

    Before the managed markers, `mb` wrote the whole file from the template
    with the metadata comment on top. A span counts only when the text from
    that comment to an owner line, with the business name and owner put back,
    hashes to the `template_hash` the comment names: exactly the generated
    text, unedited. Anything before or after it was written by a person.
    """

    match = _GUIDANCE_METADATA_RE.search(existing)
    digest = parse_guidance_metadata(existing).get("template_hash", "")
    if not match or not digest:
        return None
    offset = match.end()
    for line in existing[match.end() :].splitlines(keepends=True):
        offset += len(line)
        if not _OWNER_LINE_RE.match(line.strip()):
            continue
        if _unrendered_template_hash(existing[match.end() : offset]) == digest:
            return match.start(), offset
    return None


def _merge_agents_md(
    existing: str, rendered: str, rerun_step: str = AGENTS_RERUN_STEP
) -> tuple[str, dict[str, str] | None]:
    """The new AGENTS.md text, or the unchanged text and why it was refused.

    Only Main Branch's own guidance is replaced: the text between the managed
    markers, or an older generated file recognised by its template hash.
    Everything else in the file is kept. When the guidance cannot be told apart
    from a person's notes, nothing is written (#1052).
    """

    block = _managed_agents_block(rendered)
    refusal = _marker_refusal(existing, rerun_step)
    if refusal is not None:
        return existing, refusal
    start = existing.find(AGENTS_MANAGED_BEGIN)
    if start != -1:
        end = existing.find(AGENTS_MANAGED_END, start)
        tail_start = end + len(AGENTS_MANAGED_END)
        return existing[:start] + block.rstrip("\n") + existing[tail_start:], None
    if not existing.strip():
        return block, None
    if not parse_guidance_metadata(existing):
        return block + "\n" + existing, None
    span = _old_generated_span(existing)
    if span is None:
        return existing, _agents_refusal(
            "unrecognised_generated_text",
            "AGENTS.md was written by an older Main Branch (it has the guidance "
            "metadata comment but no begin and end markers), and its text no longer "
            "matches the template that comment names, so Main Branch cannot separate "
            "its guidance from text you wrote. It left the file unchanged.",
            f"Put `{AGENTS_MANAGED_BEGIN}` on its own line above the Main Branch "
            f"guidance and `{AGENTS_MANAGED_END}` below it, keeping your own notes "
            f"outside the markers, {rerun_step}",
        )
    kept = (existing[: span[0]] + existing[span[1] :]).strip("\n")
    if not kept.strip():
        return block, None
    return block + "\n" + kept + "\n", None


def _markdown_section(text: str, heading: str) -> str:
    start = text.find(heading)
    if start == -1:
        return ""
    next_heading = text.find("\n## ", start + len(heading))
    if next_heading == -1:
        return text[start:]
    return text[start:next_heading]


def _commands_for_inventory_item(item: dict[str, Any]) -> tuple[str, ...]:
    commands = item.get("commands") or ()
    if not isinstance(commands, tuple):
        return tuple(str(command) for command in commands)
    return tuple(str(command) for command in commands)


def _workflow_source_path(relative_path: str) -> Path:
    root = engine_mod.engine_root()
    if root is not None:
        candidate = root / relative_path
        if candidate.is_file():
            return candidate
    return Path(__file__).resolve().parents[2] / relative_path


def _load_shared_workflow_for_skill(name: str) -> WorkflowSource | None:
    relative_path = CODEX_SHARED_WORKFLOW_SKILLS.get(name)
    if relative_path is None:
        return None
    return load_workflow(_workflow_source_path(relative_path))


def _claude_skill_sources_for_inventory_item(item: dict[str, Any]) -> tuple[str, ...]:
    sources = item.get("claude_skill_sources") or ()
    names = sources if isinstance(sources, tuple) else tuple(str(source) for source in sources)
    return tuple(f".claude/skills/{name}/SKILL.md" for name in names)


def _claude_playbook_sources_for_inventory_item(item: dict[str, Any]) -> tuple[str, ...]:
    sources = item.get("claude_playbook_sources") or ()
    names = sources if isinstance(sources, tuple) else tuple(str(source) for source in sources)
    return tuple(f".claude/playbooks/{name}/SKILL.md" for name in names)


def _source_of_truth_for_inventory_item(item: dict[str, Any]) -> dict[str, Any]:
    status = str(item["source_status"])
    surface_kinds = _surface_kinds_for_inventory_item(item)
    return {
        "status": status,
        "description": CODEX_SOURCE_STATUS_DESCRIPTIONS[status],
        "surface_type": item.get("surface_type", "workflow"),
        "playbook_status": item.get("playbook_status"),
        "status_reason": item.get("status_reason"),
        "shared_source": item.get("shared_source"),
        "playbook_source": item.get("playbook_source"),
        "surface_kinds": surface_kinds,
        "claude_sources": list(
            _claude_skill_sources_for_inventory_item(item)
            + _claude_playbook_sources_for_inventory_item(item)
        ),
        "codex_sources": [str(entrypoint) for entrypoint in item.get("codex_entrypoints", ())],
        "contract_checks": [str(check) for check in item.get("contract_checks", ())],
        "next_required_issue": item.get("next_required_issue"),
        "follow_up_issue": item.get("follow_up_issue"),
    }


def _surface_kinds_for_inventory_item(item: dict[str, Any]) -> list[str]:
    kinds: list[str] = []
    if item.get("shared_source"):
        kinds.append("shared_source")
    if item.get("claude_skill_sources"):
        kinds.append("claude_skill")
    if item.get("claude_playbook_sources"):
        kinds.append("playbook")
    if item.get("codex_entrypoints"):
        kinds.append("codex_global_skill")
    codex_status = str(item.get("codex_status", ""))
    source_status = str(item.get("source_status", ""))
    if codex_status == "read_only_planning":
        kinds.append("read_only_planning")
    if source_status == "pending_shared_source_migration":
        kinds.append("pending_shared_source_migration")
    if codex_status == "blocked_by_provider_gates" or source_status == "blocked_by_provider_gates":
        kinds.append("blocked_by_provider_gates")
    if codex_status == "internal_composable" or source_status == "internal_composable":
        kinds.append("internal_composable")
    if codex_status == "intentionally_unsupported":
        kinds.append("intentionally_unsupported")
    return kinds


def workflow_inventory(*, runtime: str = "codex") -> dict[str, Any]:
    """Return the public-safe Main Branch workflow support inventory."""

    items = []
    for item in CODEX_WORKFLOW_INVENTORY:
        copied = dict(item)
        copied["surface_type"] = str(item.get("surface_type", "workflow"))
        if item.get("playbook_status"):
            copied["playbook_status"] = str(item["playbook_status"])
        if item.get("playbook_source"):
            copied["playbook_source"] = str(item["playbook_source"])
        copied["commands"] = list(_commands_for_inventory_item(item))
        copied["claude_skill_sources"] = list(_claude_skill_sources_for_inventory_item(item))
        copied["claude_playbook_sources"] = list(_claude_playbook_sources_for_inventory_item(item))
        copied["codex_entrypoints"] = [
            str(entrypoint) for entrypoint in item.get("codex_entrypoints", ())
        ]
        copied["surface_kinds"] = _surface_kinds_for_inventory_item(item)
        copied["source_of_truth"] = _source_of_truth_for_inventory_item(item)
        items.append(copied)
    statuses = sorted(
        {*CODEX_WORKFLOW_STATUS_VOCABULARY}
        | {str(item["codex_status"]) for item in CODEX_WORKFLOW_INVENTORY}
    )
    source_statuses = sorted(
        {*CODEX_SOURCE_STATUS_VOCABULARY}
        | {str(item["source_status"]) for item in CODEX_WORKFLOW_INVENTORY}
    )
    counts = {
        "items": len(items),
        "workflows": len(items),
        "codex_global_skill_routes": len(CODEX_GLOBAL_SKILL_NAMES),
        "shared_source": sum(1 for item in items if "shared_source" in item["surface_kinds"]),
        "read_only_planning": sum(
            1 for item in items if "read_only_planning" in item["surface_kinds"]
        ),
        "intentionally_unsupported": sum(
            1 for item in items if "intentionally_unsupported" in item["surface_kinds"]
        ),
    }
    return {
        "ok": True,
        "runtime": runtime,
        "support_level": CODEX_SUPPORT_LEVEL,
        "entrypoint": "main-branch mb-start",
        "repo_guidance": AGENTS_RELATIVE_PATH,
        "inventory_path": CODEX_WORKFLOW_INVENTORY_RELATIVE_PATH,
        "architecture": {
            "canonical_flow": (
                "shared workflow source -> Claude Code shell -> Codex shell -> inventory/tests"
            ),
            "shared_source_root": "workflows/<workflow>/workflow.md",
            "runtime_shells": {
                "claude_code": ".claude/skills/<name>/SKILL.md",
                "codex_cli": "global main-branch skills plus AGENTS.md guidance",
            },
            "status_field": "items[].source_of_truth.status",
        },
        "claude_skill_sources": [
            f".claude/skills/{name}/SKILL.md" for name in CLAUDE_SKILL_SOURCE_NAMES
        ],
        "claude_playbook_sources": [
            f".claude/playbooks/{name}/SKILL.md" for name in CLAUDE_PLAYBOOK_SOURCE_NAMES
        ],
        "playbook_sources": sorted(
            str(item["playbook_source"])
            for item in CODEX_WORKFLOW_INVENTORY
            if item.get("playbook_source")
        ),
        "global_skill": {
            "name": CODEX_GLOBAL_SKILL_NAME,
            "display_name": "Main Branch",
            "path": CODEX_GLOBAL_SKILL_RELATIVE_PATH,
            "routes": list(CODEX_GLOBAL_SKILL_NAMES),
            "support": {
                name: CODEX_GLOBAL_SKILL_SUPPORT[name] for name in CODEX_GLOBAL_SKILL_NAMES
            },
            "install_hint": CODEX_REPAIR_COMMAND,
        },
        "statuses": statuses,
        "source_statuses": source_statuses,
        "source_status_descriptions": CODEX_SOURCE_STATUS_DESCRIPTIONS,
        "surface_kinds": list(CODEX_SURFACE_KIND_VOCABULARY),
        "surface_kind_descriptions": CODEX_SURFACE_KIND_DESCRIPTIONS,
        "json_shape": {
            "canonical_items": "items",
            "compatibility_alias": "workflows",
            "summary_count": "counts.items",
            "note": (
                "`items` is canonical; `workflows` is an alias for agents that "
                "expect workflow inventories under that key."
            ),
        },
        "counts": counts,
        "items": items,
        "workflows": items,
        "safe_to_share": True,
    }


def render_workflow_inventory_md() -> str:
    """Render the project-local Codex workflow inventory reference."""

    rows = []
    for item in CODEX_WORKFLOW_INVENTORY:
        commands = ", ".join(f"`{command}`" for command in _commands_for_inventory_item(item))
        entrypoints = ", ".join(f"`{entry}`" for entry in item.get("codex_entrypoints", ()))
        next_issue = item.get("next_required_issue") or item.get("follow_up_issue") or "None"
        claude_sources = ", ".join(
            f"`{source}`"
            for source in (
                _claude_skill_sources_for_inventory_item(item)
                + _claude_playbook_sources_for_inventory_item(item)
            )
        )
        row_template = (
            "| {label} | `{surface_type}` | `{status}` | `{source_status}` | {reason} | "
            "{next_issue} | {claude} | {sources} | {codex} | {entrypoints} | {commands} |"
        )
        rows.append(
            row_template.format(
                label=item["label"],
                surface_type=item.get("surface_type", "workflow"),
                status=item["codex_status"],
                source_status=item["source_status"],
                reason=item.get("status_reason", item["notes"]),
                next_issue=next_issue,
                claude=item["claude_surface"],
                sources=claude_sources or "None",
                codex=item["codex_surface"],
                entrypoints=entrypoints or "None",
                commands=commands or "None",
            )
        )
    return (
        "# Main Branch Codex Workflow Inventory\n\n"
        "Generated by `mb`. Do not edit by hand in business repos. This file maps "
        "Main Branch workflow surfaces to the Codex global-skill support boundary.\n\n"
        "Status meanings:\n\n"
        "- `supported`: Codex can use this surface through global Main Branch skills "
        "grounded in deterministic `mb` facts.\n"
        "- `read_only_planning`: Codex can inspect facts and help plan, but must "
        "not claim full workflow parity until a shared source migration lands.\n"
        "- `pending_shared_source_migration`: Codex may plan from read-only facts, "
        "but a runtime shell should wait for a shared workflow source.\n"
        "- `blocked_by_provider_gates`: Codex may plan or review, but provider "
        "mutation, publishing, spend, customer contact, or account changes wait "
        "for explicit gates and runtime evidence.\n"
        "- `internal_composable`: internal or provisional route hidden from "
        "default user-facing Codex global skills.\n"
        "- `generated_shell_pending`: a shared source exists, but a generated Codex "
        "shell still needs implementation and smoke evidence.\n"
        "- `intentionally_unsupported`: outside the current Codex daily-loop target.\n\n"
        "Source-of-truth meanings:\n\n"
        "- `shared_workflow_source`: `workflows/<workflow>/workflow.md` owns "
        "the portable workflow contract and tests check runtime shells against it.\n"
        "- `temporary_source_skill_mirror`: Codex mirrors existing Claude skill "
        "or CLI guidance until a shared source owns both runtime shells.\n"
        "- `pending_shared_source_migration`: Codex may use read-only facts or "
        "planning guidance, but runtime shells wait for a shared source migration.\n"
        "- `blocked_by_provider_gates`: planning or review may be useful, but "
        "execution waits for provider, publishing, spend, customer-contact, or "
        "account-mutation gates.\n"
        "- `internal_composable`: provisional surface that may compose other "
        "workflows but is not a default user-facing route.\n"
        "- `intentionally_unsupported`: outside the current Codex daily-loop target.\n\n"
        "Canonical architecture: shared workflow source -> Claude Code shell -> "
        "Codex shell -> inventory/tests. Temporary mirrors are explicit so "
        "reviewers can see which routes still need migration.\n\n"
        "`mb workflow list --runtime codex --json` returns workflow inventory "
        "under canonical `items`, with `workflows` as a compatibility alias and "
        "`counts.items` as the top-level count.\n\n"
        "Surface kinds in `mb workflow list --json`: `shared_source`, "
        "`claude_skill`, `playbook`, `codex_global_skill`, `read_only_planning`, "
        "`pending_shared_source_migration`, `blocked_by_provider_gates`, "
        "`internal_composable`, and `intentionally_unsupported`.\n\n"
        "The global Main Branch skill bundle is installed by "
        "`mb doctor repair --only codex`; business repos keep only lightweight "
        "`AGENTS.md` guidance. After repair, open a fresh Codex thread in the "
        "business repo and ask Main Branch to run one of the `mb-*` routes. "
        "Each row names its bundled Claude skill "
        "source(s); every bundled Claude `mb-*` skill must be accounted for here "
        "until the shared workflow generator owns both runtime shells.\n\n"
        "| Workflow | Type | Codex status | Source of truth | Reason | Next issue | "
        "Claude Code surface | Claude source | Codex surface | Codex route | Fact commands |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|\n" + "\n".join(rows) + "\n\n"
        "Codex must ask before durable writes, checkpoints, repairs, updates, "
        "migrations, provider mutation, publishing, spend, customer contact, or "
        "public issue/proposal submission.\n"
    )


def render_codex_plugin_manifest() -> str:
    """Render the global Codex plugin manifest."""

    payload = {
        "name": CODEX_PLUGIN_NAME,
        "version": "0.1.0",
        "description": (
            "Main Branch /mb commands for Codex. Uses deterministic mb facts "
            "and business-repo guidance."
        ),
        "author": {"name": "Noontide"},
        "homepage": "https://github.com/dmthepm/mainbranch",
        "repository": "https://github.com/dmthepm/mainbranch",
        "license": "MIT",
        "keywords": ["main-branch", "mainbranch", "business-memory"],
        "interface": {
            "displayName": "Main Branch",
            "shortDescription": "Main Branch /mb commands for business repos",
            "longDescription": (
                "Adds Codex `/mb-*` commands for Main Branch business repos. Commands "
                "route through deterministic mb facts and repo guidance; "
                "they do not add provider mutation, publishing, spend, customer "
                "contact, ads/site production, or all-skill parity."
            ),
            "developerName": "Noontide",
            "category": "Productivity",
            "capabilities": ["Interactive", "Read", "Write"],
            "websiteURL": "https://github.com/dmthepm/mainbranch",
            "defaultPrompt": [
                "Use /mb-start to start this Main Branch business day",
                "Use /mb-help to show supported Main Branch Codex commands",
                "Use /mb-end to plan a checkpoint before saving work",
            ],
            "brandColor": "#0F766E",
            "screenshots": [],
        },
    }
    return json.dumps(payload, indent=2) + "\n"


def render_codex_marketplace_json() -> str:
    """Render the global Codex plugin marketplace metadata."""

    payload = {
        "name": CODEX_MARKETPLACE_NAME,
        "interface": {"displayName": "Main Branch"},
        "plugins": [
            {
                "name": CODEX_PLUGIN_NAME,
                "source": {
                    "source": "local",
                    "path": f"./{CODEX_PLUGIN_DIR_RELATIVE_PATH}",
                },
                "policy": {
                    "installation": "AVAILABLE",
                    "authentication": "ON_INSTALL",
                },
                "category": "Productivity",
            }
        ],
    }
    return json.dumps(payload, indent=2) + "\n"


def _slash_command_label(name: str) -> str:
    return f"/{name}"


def render_codex_slash_command_md(name: str) -> str:
    """Render one thin Codex slash-command file for the global plugin."""

    if name not in CODEX_SLASH_COMMAND_NAMES:
        raise ValueError(f"unknown Codex slash command: {name}")
    description = CODEX_SLASH_COMMAND_DESCRIPTIONS[name]
    facts = CODEX_SLASH_COMMAND_FACTS[name]
    fact_lines = "\n".join(f"- `{command}`" for command in facts)
    command = _slash_command_label(name)
    specific = {
        "mb-start": (
            "Summarize the business state, readiness, ranked actions, and one "
            "clear next route. Use `mb start --json` when runtime handoff or "
            "Codex readiness matters."
        ),
        "mb-status": (
            "Answer from status facts: readiness, drift, recent work, "
            "since-last-check, MoneyPath, content strategy, provider signals, "
            "and ranked actions."
        ),
        "mb-setup": (
            "Treat setup prompts as onboarding intent. Explain the target folder "
            "and ask before running any command that writes files."
        ),
        "mb-update": (
            "Report whether an update is required or recommended. Ask before "
            "running update, repair, migration, or package-changing commands."
        ),
        "mb-doctor": (
            "Explain the repair plan in business language first. Quote exact "
            "safe commands and ask before applying any write action."
        ),
        "mb-think": (
            "Use the Codex Think Route in `AGENTS.md`. Choose the smallest honest "
            "research depth, read only needed business files, and ask before "
            "codifying or checkpointing."
        ),
        "mb-end": (
            "Use the shared closeout workflow. Run the status scan and checkpoint "
            "plan, summarize the session, capture a final thought, do "
            "crystallize-lite or an available subagent pass, name the owner-facing "
            "save state, and ask before saving."
        ),
        "mb-help": (
            "Show the supported, pending, and unsupported Codex workflow surfaces. "
            "Do not claim parity for surfaces the inventory does not mark supported."
        ),
    }[name]
    return f"""---
description: {description}
---

# {command}

Use Main Branch from the current repo. This command is a thin Codex route over
deterministic `mb` facts and the repo `AGENTS.md` guidance. Do not duplicate
workflow logic here.

## Preflight

Run first:

- `command -v mb`
- `mb --version`

If `mb` is missing or reports an unexpected version, stop and tell the operator
to fix the runtime/login-shell PATH before continuing.

## Facts

Run the read-only facts that fit this command:

{fact_lines}

Stop before business routing if `runtime.codex_cli.status` is
`runtime_mismatch` or if any drift item is `codex_runtime_mb_mismatch`.

## Route

{specific}

Ask before durable writes, checkpoints, updates, repairs, migrations, provider
mutation, publishing, spend, customer contact, destructive operations, or public
issue/proposal submission.
"""


def render_codex_slash_commands() -> dict[str, str]:
    """Render all generated Codex slash-command files by relative path."""

    return {
        f"{CODEX_PLUGIN_COMMANDS_RELATIVE_PATH}/{name}.md": render_codex_slash_command_md(name)
        for name in CODEX_SLASH_COMMAND_NAMES
    }


def _render_shared_workflow_global_skill_adapter(workflow: WorkflowSource) -> str:
    rendered_shell = render_codex_shell(workflow).strip()
    return (
        "Follow the generated Codex shell below. It is rendered from the canonical "
        "shared workflow source, so workflow substance belongs in that source and "
        "Codex differences stay in this adapter layer.\n\n"
        f"{rendered_shell}"
    )


def render_codex_global_skill_md(name: str = CODEX_GLOBAL_SKILL_NAME) -> str:
    """Render one global Main Branch Codex skill."""

    route_lines = "\n".join(
        f"- `{skill}`: {CODEX_GLOBAL_SKILL_DESCRIPTIONS[skill]} "
        f"({CODEX_GLOBAL_SKILL_SUPPORT[skill]})"
        for skill in CODEX_GLOBAL_SKILL_NAMES
        if skill != CODEX_GLOBAL_SKILL_NAME
    )
    if name not in CODEX_GLOBAL_SKILL_NAMES:
        raise ValueError(f"unknown Codex global skill: {name}")
    description = CODEX_GLOBAL_SKILL_DESCRIPTIONS[name]
    support_level = CODEX_GLOBAL_SKILL_SUPPORT[name]
    workflow = _load_shared_workflow_for_skill(name)
    facts = tuple(workflow.required_mb_commands) if workflow else CODEX_GLOBAL_SKILL_FACTS[name]
    if name == CODEX_GLOBAL_SKILL_NAME:
        argument_hint = (
            "[mb-start|mb-status|mb-setup|mb-update|mb-doctor|mb-think|mb-end|mb-help|other-route]"
        )
        title = "Main Branch"
        route_guidance = (
            "Choose the closest route below, then follow that route's facts and approval boundary."
        )
    else:
        argument_hint = "[target]"
        title = name
        if workflow is not None:
            route_guidance = _render_shared_workflow_global_skill_adapter(workflow)
        else:
            supported_guidance = {
                "mb-start": (
                    "Summarize the business state, readiness, ranked actions, and one "
                    "clear next route. Use `mb start --json` when runtime handoff or "
                    "Codex readiness matters."
                ),
                "mb-status": (
                    "Answer from status facts: readiness, drift, recent work, "
                    "since-last-check, MoneyPath, content strategy, provider signals, "
                    "and ranked actions."
                ),
                "mb-setup": (
                    "Treat setup prompts as onboarding intent. Explain the target folder "
                    "and ask before running any command that writes files."
                ),
                "mb-update": (
                    "Report whether an update is required or recommended. Ask before "
                    "running update, repair, migration, or package-changing commands."
                ),
                "mb-doctor": (
                    "Explain the repair plan in business language first. Quote exact "
                    "safe commands and ask before applying any write action."
                ),
                "mb-think": (
                    "Use the Codex Think Route in `AGENTS.md`. Choose the smallest honest "
                    "research depth, read only needed business files, and ask before "
                    "codifying or checkpointing."
                ),
                "mb-end": (
                    "Use the shared closeout workflow. Run the status scan and checkpoint "
                    "plan, summarize the session, capture a final thought, do "
                    "crystallize-lite or an available subagent pass, name the owner-facing "
                    "save state, and ask before saving."
                ),
                "mb-help": (
                    "Show the supported, pending, and unsupported Codex workflow surfaces. "
                    "Do not claim parity for surfaces the inventory does not mark supported."
                ),
                "mb-books": (
                    "From the business repo run `mb books check . --json`. Discover "
                    "books_repo in core/finance/books.md or ask for its location, then "
                    "run `mb books doctor --repo $BOOKS_REPO --json`. Review only "
                    "aggregate close state and process docs. Never open evidence "
                    "bytes, quote doctor output or financial details, post or edit "
                    "journal entries, or run hledger import/add. Propose rules edits "
                    "for operator approval in the private books repo."
                ),
            }
            if name in supported_guidance:
                route_guidance = supported_guidance[name]
            elif support_level == "read_only_planning":
                route_guidance = (
                    "Use this as a read-only planning route in Codex. Ground the answer "
                    "in the facts below, name what Claude Code can do more fully when "
                    "relevant, and ask before writing files or touching providers. This "
                    "route is pending shared source migration and is not full workflow "
                    "parity."
                )
            else:
                route_guidance = (
                    "This workflow is inventoried for completeness but is not a supported "
                    "Codex execution route yet. Explain the support boundary and route "
                    "the operator to Claude Code or another supported Main Branch path."
                )
    fact_lines = "\n".join(f"- `{command}`" for command in facts)
    return f"""---
name: {name}
description: "{description}"
argument-hint: "{argument_hint}"
user-invocable: true
---

# {title}

Support level: `{support_level}`.

Use this skill when the operator is in a Main Branch business repo and asks to
start the day, inspect status, set up, update, repair, think through a decision,
close a session, get help, or use one of the inventoried Main Branch workflows.

## Routes

{route_lines}

{route_guidance}

Use the route names above as product-facing workflow names. Do not introduce
legacy adapter names, installation internals, or command-surface vocabulary in
operator-facing answers.

## Grounding

Start in the current repo. Run the read-only facts that fit the route before
advice:

{fact_lines}

Run `command -v mb` and `mb --version` first when setup, update, repair, or
runtime readiness is uncertain. If `mb` is missing or reports an unexpected
version, stop and tell the operator to fix the runtime/login-shell PATH before
continuing.

Use `mb status --json --peek` as the default daily briefing source. It names
readiness, drift, onboarding progress, update state, GitHub activity, provider
signals, recent work, MoneyPath, ranked actions, bets, pushes, and checkpoint
state. Use `mb start --json` when runtime handoff or repo-boundary facts matter.

Stop before business routing if `runtime.codex_cli.status` is `runtime_mismatch`
or if any drift item is `codex_runtime_mb_mismatch`.

## Approval

Read-only fact commands can run without asking. Ask before durable writes,
checkpoints, updates, repairs, migrations, provider mutation, publishing, spend,
customer contact, destructive operations, or public issue/proposal submission.

## Boundaries

Codex supports the daily Main Branch routes listed here. Do not claim all Claude
Code skills, provider mutation, ads/site production, publishing, spend, customer
contact, or Claude Code command surfaces are available unless `mb workflow list
--runtime codex --json` and current runtime evidence say so.
Read workflow inventory from canonical `items`; `workflows` is a compatibility
alias and `counts.items` is the top-level count.
"""


def agents_path(repo: str | Path) -> Path:
    return Path(repo).expanduser().resolve() / AGENTS_RELATIVE_PATH


def codex_skill_path(repo: str | Path) -> Path:
    return Path(repo).expanduser().resolve() / CODEX_SKILL_RELATIVE_PATH


def workflow_inventory_path(repo: str | Path) -> Path:
    return Path(repo).expanduser().resolve() / CODEX_WORKFLOW_INVENTORY_RELATIVE_PATH


def marketplace_path(repo: str | Path) -> Path:
    return global_plugin_source_root() / CODEX_MARKETPLACE_RELATIVE_PATH


def plugin_manifest_path(repo: str | Path) -> Path:
    return global_plugin_source_root() / CODEX_PLUGIN_MANIFEST_RELATIVE_PATH


def plugin_skill_path(repo: str | Path) -> Path:
    return global_plugin_source_root() / CODEX_PLUGIN_SKILL_RELATIVE_PATH


def plugin_commands_dir(repo: str | Path) -> Path:
    return global_plugin_source_root() / CODEX_PLUGIN_COMMANDS_RELATIVE_PATH


def plugin_command_path(repo: str | Path, name: str) -> Path:
    return plugin_commands_dir(repo) / f"{name}.md"


def executable_status() -> dict[str, Any]:
    path = _which("codex")
    return {
        "found": bool(path),
        "path": path,
        "executable": "codex",
        "repair": "" if path else "Install Codex CLI before using Main Branch in Codex.",
    }


def _run_codex_plugin_command(repo: Path, args: list[str]) -> dict[str, Any]:
    codex_path = _which("codex")
    command = [codex_path or "codex", *args]
    if not codex_path:
        return {
            "ok": False,
            "returncode": 127,
            "stdout": "",
            "stderr": "codex not on PATH",
            "command": " ".join(["codex", *args]),
        }
    try:
        proc = subprocess.run(
            command,
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "returncode": 124,
            "stdout": "",
            "stderr": "codex plugin command timed out",
            "command": " ".join(["codex", *args]),
        }
    except (FileNotFoundError, subprocess.SubprocessError) as exc:
        return {
            "ok": False,
            "returncode": 1,
            "stdout": "",
            "stderr": str(exc),
            "command": " ".join(["codex", *args]),
        }
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "command": " ".join(["codex", *args]),
    }


def _codex_plugin_list(repo: Path) -> dict[str, Any]:
    return _run_codex_plugin_command(
        repo,
        ["plugin", "list", "--marketplace", CODEX_MARKETPLACE_NAME],
    )


def _parse_plugin_install_status(output: str, expected_marketplace_path: Path) -> dict[str, Any]:
    lines = output.splitlines()
    actual_marketplace_path = ""
    for index, line in enumerate(lines):
        if line.strip() == f"Marketplace `{CODEX_MARKETPLACE_NAME}`":
            if index + 1 < len(lines):
                actual_marketplace_path = lines[index + 1].strip()
            break

    marketplace_registered = bool(
        actual_marketplace_path
        and Path(actual_marketplace_path).expanduser().resolve()
        == expected_marketplace_path.expanduser().resolve()
    )
    marketplace_stale = bool(actual_marketplace_path and not marketplace_registered)
    plugin_line = next((line.strip() for line in lines if CODEX_PLUGIN_SELECTOR in line), "")
    plugin_available = bool(plugin_line and marketplace_registered)
    status_text = plugin_line.split(CODEX_PLUGIN_SELECTOR, 1)[1].strip() if plugin_line else ""
    plugin_installed = bool(
        plugin_available and "installed" in status_text and "not installed" not in status_text
    )
    plugin_enabled = bool(plugin_installed and "enabled" in status_text)
    return {
        "marketplace_registered": marketplace_registered,
        "marketplace_stale": marketplace_stale,
        "marketplace_path": str(expected_marketplace_path),
        "registered_marketplace_path": actual_marketplace_path,
        "global_plugin_installed": plugin_installed,
        "plugin_available": plugin_available,
        "plugin_installed": plugin_installed,
        "plugin_enabled": plugin_enabled,
        "skill_available": False,
        "skill_ready": False,
        "slash_commands_ready": False,
        "plugin_line": plugin_line,
    }


def plugin_install_status(repo: str | Path, *, adapter_files_ok: bool = True) -> dict[str, Any]:
    target = Path(repo).expanduser().resolve()
    expected_marketplace_path = marketplace_path(target)
    install_command = CODEX_PLUGIN_INSTALL_COMMAND
    register_command = codex_marketplace_add_command()
    source_status = plugin_status(target)
    source_ok = source_status["ok"]
    if not _which("codex"):
        return {
            "checked": False,
            "ok": False,
            "state": "codex_missing",
            "summary": "Codex CLI is not installed, so plugin install state was not checked.",
            "marketplace_name": CODEX_MARKETPLACE_NAME,
            "plugin_selector": CODEX_PLUGIN_SELECTOR,
            "marketplace_registered": False,
            "marketplace_stale": False,
            "global_source_path": str(global_plugin_source_root()),
            "global_source_ok": source_ok,
            "plugin_available": False,
            "global_plugin_installed": False,
            "plugin_installed": False,
            "plugin_enabled": False,
            "command_files_current": bool(source_status.get("command_files_current", False)),
            "command_surface_ok": False,
            "slash_commands_likely_loaded": False,
            "slash_commands_restart_required": False,
            "skill_ready": False,
            "slash_commands_ready": False,
            "install_command": install_command,
            "register_command": register_command,
            "repair": "Install Codex CLI before using Main Branch Codex commands.",
            "safe_to_share": True,
        }
    if not adapter_files_ok:
        return {
            "checked": False,
            "ok": False,
            "state": "waiting_for_adapter_files",
            "summary": (
                "Codex plugin install check waits until repo AGENTS.md guidance is current."
            ),
            "marketplace_name": CODEX_MARKETPLACE_NAME,
            "plugin_selector": CODEX_PLUGIN_SELECTOR,
            "marketplace_registered": False,
            "marketplace_stale": False,
            "global_source_path": str(global_plugin_source_root()),
            "global_source_ok": source_ok,
            "plugin_available": False,
            "global_plugin_installed": False,
            "plugin_installed": False,
            "plugin_enabled": False,
            "command_files_current": bool(source_status.get("command_files_current", False)),
            "command_surface_ok": False,
            "slash_commands_likely_loaded": False,
            "slash_commands_restart_required": False,
            "skill_ready": False,
            "slash_commands_ready": False,
            "install_command": install_command,
            "register_command": register_command,
            "repair": repair_text(target),
            "safe_to_share": True,
        }

    if not source_ok:
        return {
            "checked": True,
            "ok": False,
            "state": "global_plugin_source_missing",
            "summary": ("The global Main Branch Codex plugin source is missing or stale."),
            "marketplace_name": CODEX_MARKETPLACE_NAME,
            "plugin_selector": CODEX_PLUGIN_SELECTOR,
            "marketplace_registered": False,
            "marketplace_stale": False,
            "marketplace_path": str(expected_marketplace_path),
            "registered_marketplace_path": "",
            "global_source_path": str(global_plugin_source_root()),
            "global_source_ok": False,
            "plugin_available": False,
            "global_plugin_installed": False,
            "plugin_installed": False,
            "plugin_enabled": False,
            "slash_commands_ready": False,
            "command_files_current": bool(source_status.get("command_files_current", False)),
            "command_surface_ok": False,
            "slash_commands_likely_loaded": False,
            "slash_commands_restart_required": False,
            "skill_ready": False,
            "plugin_line": "",
            "install_command": install_command,
            "register_command": register_command,
            "repair": f"Run `{repair_command(target)}` to install the global plugin.",
            "safe_to_share": True,
        }

    result = _codex_plugin_list(target)
    parsed = _parse_plugin_install_status(
        str(result.get("stdout") or ""), expected_marketplace_path
    )
    command_files_current = bool(source_status.get("command_files_current"))
    state = "ok"
    summary = "Main Branch Codex commands are installed and ready after restarting Codex."
    repair = ""
    if not result["ok"]:
        state = "plugin_state_unverified"
        summary = "Codex plugin install state could not be checked."
        repair = f"Run `{register_command}`, then `{install_command}`."
    elif not parsed["marketplace_registered"]:
        state = "marketplace_not_registered"
        summary = (
            "The global Main Branch Codex plugin source is ready, but its Codex "
            "marketplace is not registered."
        )
        if parsed["marketplace_stale"]:
            summary = (
                "A `main-branch` Codex marketplace is registered, but it "
                "points at a different Main Branch plugin source."
            )
        repair = f"Run `{register_command}`, then `{install_command}`."
    elif not parsed["plugin_available"]:
        state = "plugin_not_available"
        summary = (
            "The global Main Branch Codex marketplace is registered, but the plugin is missing."
        )
        repair = f"Run `{register_command}`, then `{install_command}`."
    elif not parsed["plugin_installed"]:
        state = "plugin_not_installed"
        summary = (
            "The global Main Branch Codex plugin source is ready, but the plugin "
            "is not installed in Codex yet."
        )
        repair = f"Run `{install_command}`."
    elif not parsed["plugin_enabled"]:
        state = "plugin_disabled"
        summary = "The Main Branch Codex plugin is installed but not enabled."
        repair = f"Enable `{CODEX_PLUGIN_SELECTOR}` in Codex plugins."
    elif not command_files_current:
        state = "slash_commands_stale"
        summary = "Main Branch Codex command files are missing or stale."
        repair = repair_text(target)

    installed_enabled_current = bool(
        state == "ok"
        and command_files_current
        and parsed["plugin_installed"]
        and parsed["plugin_enabled"]
    )
    return {
        "checked": True,
        "ok": state == "ok",
        "state": state,
        "summary": summary,
        "marketplace_name": CODEX_MARKETPLACE_NAME,
        "plugin_selector": CODEX_PLUGIN_SELECTOR,
        **parsed,
        "global_source_path": str(global_plugin_source_root()),
        "global_source_ok": source_ok,
        "command_files": list(CODEX_SLASH_COMMAND_RELATIVE_PATHS),
        "command_files_current": command_files_current,
        "slash_commands_generated": command_files_current,
        "command_surface_ok": installed_enabled_current,
        "slash_commands_ready": installed_enabled_current,
        "slash_commands_likely_loaded": False,
        "slash_commands_restart_required": installed_enabled_current,
        "install_command": install_command,
        "register_command": register_command,
        "repair": repair,
        "command": result.get("command", ""),
        "returncode": result.get("returncode"),
        "error": str(result.get("stderr") or "").strip(),
        "safe_to_share": True,
    }


def install_plugin(repo: str | Path) -> dict[str, Any]:
    target = Path(repo).expanduser().resolve()
    source = write_global_plugin_source()
    steps = [
        _run_codex_plugin_command(target, ["plugin", "remove", CODEX_LEGACY_PLUGIN_SELECTOR]),
        _run_codex_plugin_command(
            target,
            ["plugin", "marketplace", "add", str(global_plugin_source_root())],
        ),
        _run_codex_plugin_command(target, ["plugin", "add", CODEX_PLUGIN_SELECTOR]),
    ]
    final = plugin_install_status(target)
    return {
        "ok": bool(final.get("ok")),
        "source": source,
        "steps": steps,
        "status": final,
        "safe_to_share": True,
    }


def global_skill_status(repo: str | Path) -> dict[str, Any]:
    """Return status for the global Main Branch Codex skill bundle."""

    expected_by_name = {
        name: render_codex_global_skill_md(name) for name in CODEX_GLOBAL_SKILL_NAMES
    }
    path_by_name = {name: global_skill_file_path(name) for name in CODEX_GLOBAL_SKILL_NAMES}
    missing = [f"{name}/SKILL.md" for name, path in path_by_name.items() if not path.is_file()]
    read_error = ""
    stale: list[str] = []
    missing_markers: list[str] = []
    skill_reports: dict[str, dict[str, Any]] = {}
    unreadable: list[str] = []
    for skill_name, path in path_by_name.items():
        exists = path.is_file()
        text = ""
        skill_read_error = ""
        try:
            text = path.read_text(encoding="utf-8") if exists else ""
        except (OSError, UnicodeDecodeError) as exc:
            # #1067: unreadable (an OS error, or bytes that are not UTF-8) is
            # reported, kept and never overwritten; see `global_skill_operations`.
            skill_read_error = str(exc)
            read_error = skill_read_error
            unreadable.append(str(path))
        markers = (
            f"name: {skill_name}",
            "user-invocable: true",
            "mb status --json --peek",
        )
        route_missing = [marker for marker in markers if marker not in text]
        if route_missing:
            missing_markers.extend(f"{skill_name}: {marker}" for marker in route_missing)
        if exists and not skill_read_error and text != expected_by_name[skill_name]:
            stale.append(f"{skill_name}/SKILL.md")
        skill_reports[skill_name] = {
            "ok": bool(
                exists
                and not route_missing
                and not skill_read_error
                and text == expected_by_name[skill_name]
            ),
            "exists": exists,
            "current": bool(exists and text == expected_by_name[skill_name]),
            "path": f"{skill_name}/SKILL.md",
            "absolute_path": str(path),
            "missing_markers": route_missing,
            "read_error": skill_read_error,
        }
    # #1056: an old surface is stale while it holds a Main Branch file; a
    # person's files left in it are reported as kept, never removed.
    cleanup = global_skill_cleanup()
    stale.extend(cleanup["removals"])
    ok = bool(not missing and not stale and not read_error and not missing_markers)
    linked = [str(path) for path in _linked_current_skill_folders()]
    summary = (
        "The global Main Branch Codex skill bundle is installed and current."
        if ok
        else (
            "The global Main Branch Codex skill bundle is missing, stale, "
            "or has old plugin artifacts."
        )
    )
    # #1087 item 6: informational, not an action; present only when it applies.
    extra: dict[str, Any] = (
        {"linked": linked, "note": _linked_current_note(linked)} if linked else {}
    )
    return {
        "checked": True,
        "ok": ok,
        "state": "ok" if ok else "global_skill_missing_or_stale",
        "summary": f"{summary} {extra['note']}" if extra else summary,
        "name": CODEX_GLOBAL_SKILL_NAME,
        "display_name": "Main Branch",
        "path": CODEX_GLOBAL_SKILL_RELATIVE_PATH,
        "absolute_path": str(global_skill_path()),
        "skills_root": str(global_skill_source_root()),
        "exists": not missing,
        "current": bool(not stale and not missing_markers),
        "skills": skill_reports,
        "required_skills": list(CODEX_GLOBAL_SKILL_NAMES),
        "stale": stale,
        "kept": [*unreadable, *cleanup["kept"]],
        "missing": missing,
        "missing_markers": missing_markers,
        "read_error": read_error,
        "routes": list(CODEX_SLASH_COMMAND_NAMES),
        "repair": "" if ok else repair_text(repo),
        "repair_command": repair_command(repo),
        **extra,
        "safe_to_share": True,
    }


def _owned_tree_cleanup(
    path: Path,
    is_owned: Callable[[Path], bool],
    *,
    remove_link: bool = True,
    base: Path | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Per-file removals under one Main Branch path, and the entries it keeps (#1056).

    Only files `is_owned` recognises are removed, one by one, and a folder
    goes only once it is empty. A symlink at `path` itself is removed as a
    link when `remove_link`, never followed. Symlinks inside and every other
    file stay, and are returned as kept. When a folder between `base` and
    `path` is a link, nothing under it is walked; the link is kept (#1067).
    """

    link = _symlinked_ancestor(base, path) if base is not None else None
    if link is not None:
        return [], [str(link)] if path.exists() or path.is_symlink() else []
    if path.is_symlink():
        if remove_link:
            return [{"op": "delete", "path": str(path), "root": str(path)}], []
        return [], [str(path)]
    if path.is_file():
        if is_owned(path):
            return [{"op": "delete", "path": str(path), "root": str(path)}], []
        return [], [str(path)]
    if not path.is_dir():
        return [], []
    operations: list[dict[str, Any]] = []
    kept: list[str] = []
    for root, dirs, files in os.walk(path):
        base = Path(root)
        for entry in sorted([*files, *(name for name in dirs if (base / name).is_symlink())]):
            item = base / entry
            if is_owned(item):
                operations.append({"op": "delete", "path": str(item), "root": str(path)})
            else:
                kept.append(str(item))
    return operations, kept


def _plugin_link_above(path: Path) -> Path | None:
    """The link at the plugin root or its `mainbranch` folder, if it exists right now,
    for a planned plugin `path` (#1078). Checked again just before each removal.

    A path under the skills root is not a plugin path. The plan's own paths cannot be
    compared with the plugin root here: once the link exists, the root resolves
    through it.
    """

    link = global_plugin_root_link()
    if link is None:
        return None
    skills_root = global_skill_source_root()
    return None if path == skills_root or skills_root in path.parents else link


def _link_on_the_way(base: Path, path: Path) -> bool:
    """Whether `base`, or a folder between it and `path`, is now a link (#1067)."""

    return path != base and (base.is_symlink() or _symlinked_ancestor(base, path) is not None)


def _unlink_if_proven(path: Path, base: Path | None = None) -> bool:
    """Remove `path` only if its content is proven to be Main Branch's right now.

    Both applies, repo-local and global, prove each file again just before
    removing it, so a file changed after the plan stays (#1067). With `base`
    (where the plan's walk started) it also stays when `base` or a folder
    between them is now a link: the plan walked through none, so a link there
    appeared after it, and the file is no longer where the plan saw it.
    """

    if base is not None and _link_on_the_way(base, path):
        return False
    if not _is_mainbranch_transitional_file(path):
        return False
    path.unlink()
    return True


def _remove_owned_entry(item: dict[str, Any]) -> bool:
    """Remove one planned file or link, then any folders it leaves empty up to its root.

    A link is removed, as a link, only where the plan removes the path itself.
    A file is proven again first; one changed since the plan stays (#1067).
    """

    path = Path(item["path"])
    root = Path(item.get("root") or item["path"])
    if path.is_symlink():
        if path != root:
            return False
        path.unlink()  # a link is removed as a link, never followed
    elif not _unlink_if_proven(path, root):
        return False
    parent = path.parent
    while parent == root or root in parent.parents:
        try:
            parent.rmdir()  # only an empty folder; a non-empty one stays
        except OSError:
            break
        parent = parent.parent
    return True


def _is_retired_skill_file(name: str) -> Callable[[Path], bool]:
    def owned(path: Path) -> bool:
        return (
            path.name == "SKILL.md"
            and path.parent.name == name
            and not path.is_symlink()
            and _is_retired_mainbranch_global_skill(path, name)
        )

    return owned


def _held_global_skill_entry(path: Path) -> Path | None:
    """Keep a linked skill folder, a folder at SKILL.md, or a broken SKILL.md link."""

    if path.parent.is_symlink():
        return path.parent
    if path.is_dir() or (path.is_symlink() and not path.exists()):
        return path
    return None


def _linked_current_skill_folders() -> list[Path]:
    """Linked skill folders that already hold the current skill file (#1087 item 6).

    Nothing is written through them, as for any linked folder, but there is
    nothing for a person to do either, so they are not listed as kept.
    """

    found: list[Path] = []
    for name in CODEX_GLOBAL_SKILL_NAMES:
        path = global_skill_file_path(name)
        if (
            path.parent.is_symlink()
            and not path.is_symlink()
            and path.is_file()
            and _read_text_or_none(path) == render_codex_global_skill_md(name)
        ):
            found.append(path.parent)
    return found


def _linked_current_note(linked: list[str]) -> str:
    """The informational note for linked skill folders that are current (#1087 item 6)."""

    return (
        ", ".join(linked)
        + (" is a link" if len(linked) == 1 else " are links")
        + " to a folder that already holds the current Main Branch skill file. "
        "Nothing to do: Main Branch does not write through links, and if a later "
        "release changes the skill, `mb doctor` will say so."
    )


def global_skill_cleanup() -> dict[str, Any]:
    """Old global Codex surfaces to remove, per file, and what stays (#1056).

    `removals` maps each old surface (the label `global_skill_status` reports
    as stale) to its delete operations. `kept` lists files Main Branch did not
    write; they stay where they are.
    """

    skills_root = global_skill_source_root()
    plugin_root = global_plugin_source_root()
    # #1067: a link at the plugin root or its `mainbranch` folder is not walked.
    plugin_link = global_plugin_root_link()
    # (label, path, owned-file test, Main Branch-named, remove a link at path)
    surfaces: list[tuple[str, Path, Callable[[Path], bool], bool, bool]] = [
        (
            CODEX_LEGACY_GLOBAL_SKILL_NAME,
            skills_root / CODEX_LEGACY_GLOBAL_SKILL_NAME,
            _is_mainbranch_transitional_file,
            True,
            True,
        ),
        *(
            (
                name,
                skills_root / name,
                _is_retired_skill_file(name),
                False,
                # As before: a link here goes only when it leads to Main Branch's skill.
                _is_retired_mainbranch_global_skill(skills_root / name, name),
            )
            for name in CODEX_RETIRED_GLOBAL_SKILL_NAMES
        ),
        *(
            [(str(plugin_root), plugin_root, _is_mainbranch_transitional_file, True, True)]
            if plugin_link is None
            else []
        ),
    ]
    removals: dict[str, list[dict[str, Any]]] = {}
    kept: list[str] = [str(plugin_link)] if plugin_link and plugin_root.exists() else []
    linked = _linked_current_skill_folders()
    kept.extend(
        str(held)
        for name in CODEX_GLOBAL_SKILL_NAMES
        if (held := _held_global_skill_entry(global_skill_file_path(name))) is not None
        and held not in linked
    )
    for label, path, is_owned, main_branch_named, remove_link in surfaces:
        operations, others = _owned_tree_cleanup(path, is_owned, remove_link=remove_link)
        if operations:
            removals[label] = operations
        # A same-name folder with nothing of Main Branch's in it is not ours to report.
        if operations or main_branch_named:
            kept.extend(others)
    return {"removals": removals, "kept": kept}


def _link_note(paths: list[Path]) -> str:
    """A sentence naming the kept entries that are links, or "" (#1067)."""

    links = [str(path) for path in paths if path.is_symlink()]
    if not links:
        return ""
    return (
        " "
        + ", ".join(links)
        + (" is a link" if len(links) == 1 else " are links")
        + "; Main Branch does not follow links, so nothing a link leads to is touched."
    )


def _directory_note(paths: list[Path]) -> str:
    """A sentence naming the kept entries that are folders where a skill file belongs (#1078)."""

    folders = [str(path) for path in paths if path.name == "SKILL.md" and path.is_dir()]
    if not folders:
        return ""
    return (
        " "
        + ", ".join(folders)
        + (" is a folder" if len(folders) == 1 else " are folders")
        + " where a skill file belongs; Main Branch does not write there."
    )


def global_skill_operator_action(
    status: dict[str, Any], *, repo: str | Path | None = None
) -> dict[str, Any] | None:
    """The `operator_actions` entry while old global Codex folders hold unproven files.

    None when every file there is proven to be Main Branch's. Otherwise it
    names each kept file and what a person does with it; the apply removes
    only the proven files (#1062). `repo` names the business repo in the
    command (#1072).
    """

    kept = [str(item) for item in status.get("kept") or []]
    if not kept:
        return None
    effect = global_skill_apply_effect(status)
    command = repair_command(repo)
    reason = (
        "Global Codex folders hold files Main Branch cannot prove it wrote "
        "(your own files, Main Branch files that were changed, or files it cannot read): "
        + ", ".join(kept)
        + ". The repair leaves them where they are."
        + _link_note([Path(item) for item in kept])
        + _directory_note([Path(item) for item in kept])
    )
    manual_step = (
        "Open each file. Move anything you want to keep somewhere of your own, "
        "then delete the rest yourself. "
        f"`{command}` "
        + (
            "deletes only these unchanged Main Branch files: " + ", ".join(effect["removes"])
            if effect["removes"]
            else "deletes no files there"
        )
        + ("; writes these skill files: " + ", ".join(effect["writes"]) if effect["writes"] else "")
        + "; it keeps the files above."
    )
    action = engine_mod.operator_action(command, kept, f"{reason} {manual_step}")
    action.update(
        {
            "id": "codex-global-kept",
            "reason": reason,
            "manual_step": manual_step,
            "on_apply": effect,
        }
    )
    return action


def global_skill_apply_effect(status: dict[str, Any]) -> dict[str, list[str]]:
    """What `--apply --only codex` does to the global Codex folders (#1056)."""

    operations = global_skill_operations()
    return {
        "writes": [str(item["path"]) for item in operations if item["op"] == "write"],
        "removes": [str(item["path"]) for item in operations if item["op"] != "write"],
        "keeps": [str(item) for item in status.get("kept") or []],
    }


def global_skill_operations() -> list[dict[str, Any]]:
    """Every destination `write_global_skill_source` touches, in order (#1012)."""

    operations: list[dict[str, Any]] = []
    for name in CODEX_GLOBAL_SKILL_NAMES:
        path = global_skill_file_path(name)
        if _held_global_skill_entry(path) is not None:
            continue
        expected = render_codex_global_skill_md(name)
        existing = _read_text_or_none(path)
        # #1067: an unreadable file is not proven to be Main Branch's; it stays.
        if existing is not None and existing != expected:
            operations.append({"op": "write", "path": str(path), "content": expected})
    for removals in global_skill_cleanup()["removals"].values():
        operations.extend(removals)
    return operations


def write_global_skill_source() -> dict[str, Any]:
    """Write the global Main Branch Codex skill bundle and remove old surfaces."""

    changed_paths: list[str] = []
    kept = [
        str(path)
        for path in map(global_skill_file_path, CODEX_GLOBAL_SKILL_NAMES)
        if _read_text_or_none(path) is None
    ]
    kept.extend(global_skill_cleanup()["kept"])
    for item in global_skill_operations():
        path = Path(item["path"])
        if item["op"] == "write":
            if (held := _held_global_skill_entry(path)) is not None:
                kept.append(str(held))
                continue
            # Replace the directory entry: a hard-linked file keeps its content.
            atomic_write_text(path, item["content"])
            changed_paths.append(str(path))
        elif (link := _plugin_link_above(path)) is not None:
            kept.append(str(link))  # #1078: a link appeared above the plugin root
        elif _remove_owned_entry(item):
            changed_paths.append(str(path))
        elif path.exists() or path.is_symlink():
            kept.append(str(path))  # #1067: changed since the plan, so it stays
    kept = list(dict.fromkeys(kept))
    status = global_skill_status(Path.cwd())

    return {
        "ok": True,
        "path": str(global_skill_source_root()),
        "skills_root": str(global_skill_source_root()),
        "changed": bool(changed_paths),
        "changed_paths": changed_paths,
        "kept": kept,
        "relative_paths": [f"{name}/SKILL.md" for name in CODEX_GLOBAL_SKILL_NAMES],
        "status": status,
        # #1087 item 6: a current linked folder is reported, not kept.
        **{key: status[key] for key in ("linked", "note") if key in status},
        "safe_to_share": True,
    }


def install_global_skill(repo: str | Path) -> dict[str, Any]:
    """Install or refresh the primary global Codex skill."""

    source = write_global_skill_source()
    final = global_skill_status(repo)
    return {
        "ok": bool(final.get("ok")),
        "source": source,
        "steps": [],
        "status": final,
        "safe_to_share": True,
    }


def plugin_status(repo: str | Path) -> dict[str, Any]:
    target = Path(repo).expanduser().resolve()
    marketplace = marketplace_path(target)
    manifest = plugin_manifest_path(target)
    expected_marketplace = render_codex_marketplace_json()
    expected_manifest = render_codex_plugin_manifest()
    expected_commands = render_codex_slash_commands()

    paths = {
        CODEX_MARKETPLACE_RELATIVE_PATH: marketplace,
        CODEX_PLUGIN_MANIFEST_RELATIVE_PATH: manifest,
        **{
            relative: global_plugin_source_root() / relative
            for relative in CODEX_SLASH_COMMAND_RELATIVE_PATHS
        },
    }
    missing = [relative for relative, path in paths.items() if not path.is_file()]
    stale: list[str] = []
    read_errors: list[str] = []

    expected_by_path = {
        CODEX_MARKETPLACE_RELATIVE_PATH: expected_marketplace,
        CODEX_PLUGIN_MANIFEST_RELATIVE_PATH: expected_manifest,
        **expected_commands,
    }
    missing_markers: list[str] = []
    for relative, path in paths.items():
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            # #1067: not UTF-8, or not readable: reported, and the cleanup keeps it.
            read_errors.append(f"{relative}: {exc}")
            continue
        if text != expected_by_path[relative]:
            stale.append(relative)
        if relative == CODEX_PLUGIN_MANIFEST_RELATIVE_PATH:
            missing_markers.extend(
                marker for marker in CODEX_PLUGIN_REQUIRED_MARKERS if marker not in text
            )
    legacy_plugin = global_plugin_source_root() / CODEX_LEGACY_PLUGIN_DIR_RELATIVE_PATH
    if legacy_plugin.exists():
        stale.append(CODEX_LEGACY_PLUGIN_DIR_RELATIVE_PATH)
    visible_skill_dir = global_plugin_source_root() / CODEX_PLUGIN_DIR_RELATIVE_PATH / "skills"
    if visible_skill_dir.exists():
        stale.append(f"{CODEX_PLUGIN_DIR_RELATIVE_PATH}/skills")
    command_files_current = not any(
        relative in missing or relative in stale for relative in CODEX_SLASH_COMMAND_RELATIVE_PATHS
    )

    ok = not missing and not stale and not read_errors and not missing_markers
    return {
        "ok": ok,
        "exists": not missing,
        "current": not stale and not missing_markers,
        "marketplace_path": CODEX_MARKETPLACE_RELATIVE_PATH,
        "manifest_path": CODEX_PLUGIN_MANIFEST_RELATIVE_PATH,
        "skill_path": "",
        "commands_path": CODEX_PLUGIN_COMMANDS_RELATIVE_PATH,
        "command_files": list(CODEX_SLASH_COMMAND_RELATIVE_PATHS),
        "command_files_current": command_files_current,
        "slash_commands_generated": command_files_current,
        "command_surface_ok": command_files_current,
        "slash_commands_ready": False,
        "missing": missing,
        "stale": stale,
        "missing_markers": missing_markers,
        "read_errors": read_errors,
        "repair": "" if ok else repair_text(target),
        "repair_command": repair_command(target),
        "safe_to_share": True,
    }


def write_global_plugin_source() -> dict[str, Any]:
    """Write the global Main Branch Codex plugin source outside business repos."""

    root = global_plugin_source_root()
    link = global_plugin_root_link()
    if link is not None:
        # #1067: the root, or its `mainbranch` folder, is a person's link.
        return {
            "ok": True,
            "path": str(root),
            "changed": False,
            "changed_paths": [],
            "kept": [str(link)],
            "relative_paths": [],
            "safe_to_share": True,
        }
    marketplace = marketplace_path(root)
    manifest = plugin_manifest_path(root)
    expected_marketplace = render_codex_marketplace_json()
    expected_manifest = render_codex_plugin_manifest()
    expected_commands = render_codex_slash_commands()
    writes = {
        CODEX_MARKETPLACE_RELATIVE_PATH: (marketplace, expected_marketplace),
        CODEX_PLUGIN_MANIFEST_RELATIVE_PATH: (manifest, expected_manifest),
        **{relative: (root / relative, text) for relative, text in expected_commands.items()},
    }
    commands_dir = root / CODEX_PLUGIN_COMMANDS_RELATIVE_PATH
    changed_paths: list[str] = []
    kept: list[str] = []
    for _relative, (path, text) in writes.items():
        # #1062: a symlinked commands/ is a person's; never write or walk through it.
        if path.parent == commands_dir and commands_dir.is_symlink():
            continue
        # #1087: a link that appeared above the plugin root mid-run is not written through.
        if (above := _plugin_link_above(path)) is not None:
            kept.append(str(above))
            continue
        # #1067: never write or walk through a link inside the plugin root.
        link = _symlinked_ancestor(root, path)
        if link is not None:
            kept.append(str(link))
            continue
        existing = _read_text_or_none(path)
        if existing is None:
            kept.append(str(path))  # #1067: unreadable, so not proven; it stays
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        if existing != text:
            atomic_write_text(path, text)
            changed_paths.append(str(path))
    # #1056: old plugin folders and unknown command files go only when Main
    # Branch wrote them; anything else stays and is reported as kept.
    for old in (
        root / CODEX_PLUGIN_DIR_RELATIVE_PATH / "skills",
        root / CODEX_LEGACY_PLUGIN_DIR_RELATIVE_PATH,
    ):
        # #1078: a link at `old` stays, as the plan says; keeping is the safe way.
        operations, others = _owned_tree_cleanup(
            old, _is_mainbranch_transitional_file, remove_link=False, base=root
        )
        kept.extend(others)
        for item in operations:
            if (above := _plugin_link_above(Path(item["path"]))) is not None:
                kept.append(str(above))  # #1078: a link appeared above the plugin root
            elif _remove_owned_entry(item):
                changed_paths.append(item["path"])
            elif Path(item["path"]).exists():
                kept.append(item["path"])  # #1067: changed since the plan
    expected_names = {f"{name}.md" for name in CODEX_SLASH_COMMAND_NAMES}
    if commands_dir.is_symlink():
        kept.append(str(commands_dir))
    elif commands_dir.is_dir() and _symlinked_ancestor(root, commands_dir) is None:
        for path in sorted(commands_dir.iterdir()):
            if path.name in expected_names:
                continue
            if (above := _plugin_link_above(path)) is not None:
                kept.append(str(above))
            elif _unlink_if_proven(path, root):
                changed_paths.append(str(path))
            else:
                kept.append(str(path))
    kept = list(dict.fromkeys(kept))  # a link many paths lead through, once
    return {
        "ok": True,
        "path": str(root),
        "changed": bool(changed_paths),
        "changed_paths": changed_paths,
        "kept": kept,
        "relative_paths": list(writes),
        "safe_to_share": True,
    }


def _remove_generated_tree(path: Path, target: Path) -> bool:
    """Remove a transitional path the plan found to hold only `mb` files.

    A link is removed as a link. A folder is never removed whole: each file is
    checked again and removed only when proven, then folders that are left
    empty go; anything else stays with its folders. Nothing is removed when a
    folder between the repo and `path` has become a link since the plan (#1067).
    """

    if _symlinked_ancestor(target, path) is not None:
        return False
    if path.is_symlink():
        path.unlink()  # the link only, never the tree it points into
        return True
    if path.is_dir():
        for root, dirs, files in os.walk(path, topdown=False):
            base = Path(root)
            for name in files:
                _unlink_if_proven(base / name, target)
            for name in dirs:
                folder = base / name
                if not folder.is_symlink():
                    with contextlib.suppress(OSError):
                        folder.rmdir()  # only an empty folder
        try:
            path.rmdir()
        except OSError:
            return False
        return True
    return path.is_file() and _unlink_if_proven(path, target)


def _transitional_repo_paths() -> tuple[str, ...]:
    return (
        CODEX_PLUGIN_DIR_RELATIVE_PATH,
        CODEX_LEGACY_PLUGIN_DIR_RELATIVE_PATH,
        CODEX_MARKETPLACE_RELATIVE_PATH,
        CODEX_SKILL_DIR_RELATIVE_PATH,
        ".agents/skills/main-branch",
    )


def _remove_empty_transitional_dirs(target: Path) -> None:
    for maybe_empty in (
        target / ".agents" / "plugins",
        target / ".agents" / "skills",
        target / ".agents",
    ):
        # #1067: a linked folder, or one under a link, is a person's; left alone.
        if maybe_empty.is_symlink() or _symlinked_ancestor(target, maybe_empty) is not None:
            continue
        try:
            if maybe_empty.is_dir() and not any(maybe_empty.iterdir()):
                maybe_empty.rmdir()
        except OSError:
            pass


# The `mb` version a release embedded in its Codex command and skill text, in
# the two sentences that carried it: "by Main Branch `0.3.30`. If runtime ..."
# and "`0.3.30`. If the runtime reports ...". Every release wrote a plain
# X.Y.Z there; anything else in that slot is a person's text and is compared.
_EMBEDDED_VERSION_RE = re.compile(r"`\d+\.\d+\.\d+`(?=\. If (?:the )?runtime )")
_EMBEDDED_VERSION_PLACEHOLDER = "`<mb-version>`"


def generated_file_key(path: Path) -> str:
    """The key a generated Codex file is proven under: its folder and file name."""

    return f"{path.parent.name}/{path.name}"


def normalised_generated_digest(name: str, data: bytes) -> str | None:
    """sha256 of a Codex file's content with what varies per install normalised.

    What varies: the embedded `mb` version (each release wrote its own) and
    line endings (git may check a repo-local copy out with CRLF). JSON
    manifests are compared as parsed data, re-serialised with sorted keys, so
    a formatter's whitespace or key order does not matter while any added,
    removed or changed key or value does. None when the bytes are not UTF-8
    text, or not valid JSON for a `.json` name, or JSON that repeats a key in
    any object (#1067: a JSON reader keeps the last value, which hides the first).
    """

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    text = text.replace("\r\n", "\n")
    if name.endswith(".json"):
        try:
            payload = json.loads(text, object_pairs_hook=_unique_keys)
        except ValueError:  # invalid JSON, or a repeated key
            return None
        text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    else:
        text = _EMBEDDED_VERSION_RE.sub(_EMBEDDED_VERSION_PLACEHOLDER, text)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """A JSON object's pairs as a dict; a key that appears twice is refused (#1067)."""

    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


@lru_cache(maxsize=1)
def _current_generated_digests() -> dict[str, frozenset[str]]:
    """Digests of what this `mb` writes that an old Codex path may hold a copy of.

    The global plugin source files, and the `main-branch` skill (the
    repo-local `.agents/skills/main-branch` path held a copy of it).
    """

    rendered = {
        CODEX_MARKETPLACE_RELATIVE_PATH: render_codex_marketplace_json(),
        CODEX_PLUGIN_MANIFEST_RELATIVE_PATH: render_codex_plugin_manifest(),
        **render_codex_slash_commands(),
        CODEX_GLOBAL_SKILL_RELATIVE_PATH: render_codex_global_skill_md(CODEX_GLOBAL_SKILL_NAME),
    }
    digests: dict[str, set[str]] = {}
    for relative, text in rendered.items():
        path = Path(relative)
        digest = normalised_generated_digest(path.name, text.encode("utf-8"))
        if digest is not None:
            digests.setdefault(generated_file_key(path), set()).add(digest)
    return {key: frozenset(values) for key, values in digests.items()}


def _is_known_generated_content(path: Path) -> bool:
    """Whether the file at `path` (a link is read through) is a known generated version."""

    try:
        data = path.read_bytes()
    except OSError:
        return False
    digest = normalised_generated_digest(path.name, data)
    if digest is None:
        return False
    key = generated_file_key(path)
    if digest in KNOWN_FILE_DIGESTS.get(key, frozenset()):
        return True
    return digest in _current_generated_digests().get(key, frozenset())


def _is_mainbranch_transitional_file(path: Path) -> bool:
    """Whether this file at an old Codex path is proven to be one `mb` wrote.

    Proof is content, not name: the file must equal, after normalising what
    varies per install, a version a released `mb` wrote at that path (the
    frozen digests in `mb.codex_known_files`) or what this `mb` renders. A
    person's look-alike, a renamed file or a generated file with additions is
    not proven and stays. A symlink is never proven.
    """

    if path.is_symlink() or not path.is_file():
        return False
    return _is_known_generated_content(path)


def _transitional_cleanup(target: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Removals for the transitional repo-local Codex paths, and the files kept.

    A path is removed whole only when every file in it is one `mb` wrote. When
    a person's file sits inside, only the `mb` files are removed one by one and
    the person's files (and their folders) stay (#1052). A symlink at a
    transitional path is removed as a link, never followed.
    """

    operations: list[dict[str, Any]] = []
    kept: list[str] = []
    for relative in _transitional_repo_paths():
        candidate = target / relative
        # #1067: a linked folder above the path (`.agents/` or one under it) is
        # a person's; nothing under it is walked or removed, and the link is kept.
        link = _symlinked_ancestor(target, candidate)
        if link is not None:
            if candidate.exists() or candidate.is_symlink():
                kept.append(link.relative_to(target).as_posix())
            continue
        # #1056: a symlink, live or dangling, is removed as a link, never followed.
        if candidate.is_symlink() or (
            candidate.is_file() and _is_mainbranch_transitional_file(candidate)
        ):
            operations.append({"op": "delete_tree", "path": str(candidate), "rel": relative})
            continue
        if candidate.is_file():
            kept.append(relative)
            continue
        if not candidate.is_dir():
            continue
        owned: list[Path] = []
        person: list[Path] = []
        for root, dirs, files in os.walk(candidate):
            base = Path(root)
            for entry in [*files, *(name for name in dirs if (base / name).is_symlink())]:
                path = base / entry
                (owned if _is_mainbranch_transitional_file(path) else person).append(path)
        if not person:
            operations.append({"op": "delete_tree", "path": str(candidate), "rel": relative})
            continue
        kept.extend(sorted(path.relative_to(target).as_posix() for path in person))
        operations.extend(
            {"op": "delete", "path": str(path), "rel": path.relative_to(target).as_posix()}
            for path in sorted(owned)
        )
    return operations, list(dict.fromkeys(kept))


def _remove_transitional_file(path: Path, target: Path) -> bool:
    """Remove one `mb` file, then any folders it leaves empty, up to the repo."""

    if not _unlink_if_proven(path, target):
        return False
    parent = path.parent
    while parent != target and target in parent.parents:
        try:
            parent.rmdir()
        except OSError:
            break
        parent = parent.parent
    return True


def _apply_transitional_operation(item: dict[str, Any], target: Path) -> bool:
    path = Path(item["path"])
    if item["op"] == "delete":
        return _remove_transitional_file(path, target)
    return _remove_generated_tree(path, target)


def remove_repo_local_codex_plugin_files(repo: str | Path) -> list[str]:
    """Remove generated repo-local Codex plugin files from the transitional model.

    Only files `mb` wrote are removed; a person's files stay (#1052).
    """

    target = Path(repo).expanduser().resolve()
    removed: list[str] = []
    operations, _kept = _transitional_cleanup(target)
    for item in operations:
        if _apply_transitional_operation(item, target):
            removed.append(str(item["rel"]))
    _remove_empty_transitional_dirs(target)
    return removed


def skill_status(repo: str | Path) -> dict[str, Any]:
    skill = global_skill_status(repo)
    return {
        "ok": bool(skill["ok"]),
        "exists": bool(skill["exists"]),
        "current": bool(skill["current"]),
        "path": skill["path"],
        "absolute_path": skill["absolute_path"],
        "inventory_path": CODEX_WORKFLOW_INVENTORY_RELATIVE_PATH,
        "missing_markers": skill["missing_markers"],
        "global_skill": skill,
        "plugin": plugin_status(repo),
        "read_error": skill["read_error"],
        "repair": skill["repair"],
        "repair_command": repair_command(repo),
        "deprecated": False,
        "summary": ("The global Main Branch Codex skill is the supported Codex surface."),
        "safe_to_share": True,
    }


def instructions_status(repo: str | Path) -> dict[str, Any]:
    target = Path(repo).expanduser().resolve()
    path = agents_path(target)
    expected = render_agents_md(target)
    exists = path.is_file()
    try:
        text = path.read_text(encoding="utf-8") if exists else ""
    except OSError as exc:
        text = ""
        read_error = str(exc)
    else:
        read_error = ""
    managed_text = _managed_agents_content(text)
    status_text = managed_text or text
    missing_commands = [command for command in REQUIRED_FACT_COMMANDS if command not in status_text]
    approval_ok = "explicit operator approval" in status_text
    slash_ok = "Do not pretend Claude Code slash skills work in Codex." in status_text
    missing_lifecycle_guidance = [
        marker for marker in REQUIRED_LIFECYCLE_GUIDANCE_MARKERS if marker not in status_text
    ]
    for heading, markers in REQUIRED_LIFECYCLE_SECTION_MARKERS:
        section = _markdown_section(status_text, heading)
        missing_lifecycle_guidance.extend(marker for marker in markers if marker not in section)
    missing_lifecycle_guidance = list(dict.fromkeys(missing_lifecycle_guidance))
    lifecycle_discovery_ok = bool(exists and not missing_lifecycle_guidance)
    guidance_metadata = parse_guidance_metadata(status_text) if exists else {}
    expected_template_hash = guidance_template_hash()
    expected_guidance_metadata = guidance_metadata_comment(template_hash=expected_template_hash)
    guidance_schema_ok = guidance_metadata.get("schema") == str(CODEX_GUIDANCE_SCHEMA)
    guidance_template_hash_ok = guidance_metadata.get("template_hash") == expected_template_hash
    guidance_min_mb_ok = guidance_metadata.get("min_mb") == CODEX_GUIDANCE_MIN_MB
    guidance_metadata_ok = bool(
        exists and guidance_schema_ok and guidance_template_hash_ok and guidance_min_mb_ok
    )
    fact_grounding_ok = bool(
        exists and not missing_commands and approval_ok and slash_ok and lifecycle_discovery_ok
    )
    skill = skill_status(target)
    repo_local_plugin_paths = [
        relative
        for relative in (
            CODEX_SKILL_DIR_RELATIVE_PATH,
            ".agents/skills/main-branch",
            CODEX_MARKETPLACE_RELATIVE_PATH,
            CODEX_PLUGIN_DIR_RELATIVE_PATH,
            CODEX_LEGACY_PLUGIN_DIR_RELATIVE_PATH,
        )
        if (target / relative).exists() or (target / relative).is_symlink()
    ]
    template_match = bool(exists and status_text == expected)
    current = bool(fact_grounding_ok and guidance_metadata_ok and not repo_local_plugin_paths)
    return {
        "ok": current,
        "exists": exists,
        "current": current,
        "template_match": template_match,
        "fact_grounding_ok": fact_grounding_ok,
        "guidance_metadata_ok": guidance_metadata_ok,
        "guidance_schema_ok": guidance_schema_ok,
        "guidance_template_hash_ok": guidance_template_hash_ok,
        "guidance_min_mb_ok": guidance_min_mb_ok,
        "guidance_metadata": guidance_metadata,
        "expected_guidance_metadata": expected_guidance_metadata,
        "expected_template_hash": expected_template_hash,
        "guidance_min_mb": CODEX_GUIDANCE_MIN_MB,
        "generated_version_ok": guidance_metadata_ok,
        "expected_version_marker": "",
        "path": AGENTS_RELATIVE_PATH,
        "absolute_path": str(path),
        "missing_fact_commands": missing_commands,
        "missing_lifecycle_guidance": missing_lifecycle_guidance,
        "repo_local_plugin_paths": repo_local_plugin_paths,
        "lifecycle_discovery_ok": lifecycle_discovery_ok,
        "skill": skill,
        "workflow_inventory": workflow_inventory(),
        "approval_boundary_ok": approval_ok,
        "codex_native_ok": slash_ok,
        "repair": "" if current else repair_text(target),
        "repair_command": repair_command(target),
        "read_error": read_error,
        "safe_to_share": True,
    }


def _login_shell_mb_diagnostics() -> dict[str, Any]:
    return engine_mod.login_shell_mb_diagnostics()


def readiness(repo: str | Path) -> dict[str, Any]:
    executable = executable_status()
    instructions = instructions_status(repo)
    static_ok = bool(executable["found"] and instructions["ok"])
    runtime = _login_shell_mb_diagnostics()
    runtime_ok = bool(runtime.get("ok"))
    global_skill = global_skill_status(repo)
    global_skill_ok = bool(global_skill.get("ok"))
    plugin_install = {
        "checked": False,
        "ok": False,
        "state": "legacy_plugin_not_checked",
        "summary": "Codex plugin commands are legacy/experimental and not part of readiness.",
        "plugin_installed": False,
        "plugin_enabled": False,
        "command_files_current": False,
        "command_surface_ok": False,
        "slash_commands_ready": False,
        "slash_commands_likely_loaded": False,
        "slash_commands_restart_required": False,
        "repair": "",
        "safe_to_share": True,
    }
    plugin_ok = False
    slash_commands_ready = False
    command_surface_ok = global_skill_ok
    generated_guidance_ready = bool(instructions["ok"] and global_skill_ok)
    ok = bool(static_ok and runtime_ok and global_skill_ok)
    if ok:
        status = "ready"
    elif not executable["found"] or not instructions["ok"]:
        status = "needs_setup"
    elif runtime.get("mismatch"):
        status = "runtime_mismatch"
    elif runtime_ok and not global_skill_ok:
        status = str(global_skill.get("state") or "global_skill_missing_or_stale")
    else:
        status = "runtime_unverified"
    return {
        "ok": ok,
        "status": status,
        "support_level": CODEX_SUPPORT_LEVEL,
        "static_ok": static_ok,
        "runtime_ok": runtime_ok,
        "plugin_ok": plugin_ok,
        "global_skill_ok": global_skill_ok,
        "generated_guidance_ready": generated_guidance_ready,
        "command_surface_ok": command_surface_ok,
        "slash_commands_ready": slash_commands_ready,
        "global_skill": global_skill,
        "plugin_install": plugin_install,
        "runtime": runtime,
        "executable": executable,
        "instructions": instructions,
        "skill": instructions["skill"],
        "plugin": instructions["skill"]["plugin"],
        "workflow_inventory": workflow_inventory(),
        "fact_commands": list(REQUIRED_FACT_COMMANDS),
        "repair": ""
        if ok
        else (
            str(runtime.get("repair") or "")
            if static_ok and not runtime_ok
            else str(global_skill.get("repair") or "")
            if static_ok and runtime_ok and not global_skill_ok
            else instructions["repair"] or executable["repair"]
        ),
        "start_command": f"codex -C {shlex.quote(str(Path(repo).expanduser().resolve()))}",
        "smoke_command": (
            "codex exec --json --ephemeral --sandbox read-only "
            "-c 'approval_policy=\"never\"' "
            f"-C {shlex.quote(str(Path(repo).expanduser().resolve()))} "
            "'Start this Main Branch business day. Run only read-only mb checks "
            "and do not edit files.'"
        ),
        "safe_to_share": True,
    }


def human_readiness_label(readiness_report: dict[str, Any]) -> str:
    """Return a short user-facing Codex readiness label."""

    if readiness_report.get("ok"):
        return "ready"
    executable = readiness_report.get("executable") or {}
    if not executable.get("found"):
        return "missing"
    instructions = readiness_report.get("instructions") or {}
    if not instructions.get("ok"):
        return "needs setup"
    runtime = readiness_report.get("runtime") or {}
    if runtime.get("mismatch"):
        return "runtime mismatch"
    if not runtime.get("ok"):
        return "runtime unverified"
    global_skill = readiness_report.get("global_skill") or {}
    if not global_skill.get("ok"):
        return "skill not ready"
    plugin_install = readiness_report.get("plugin_install") or {}
    if not plugin_install.get("ok"):
        return "plugin optional"
    return "not ready"


def agents_md_plan(
    repo: str | Path,
    *,
    name: str = "",
    gh_username: str = "",
) -> dict[str, Any]:
    """What `write_agents_md` would do, what it refuses, and what it leaves (#1052).

    `operations` lists every destination it touches, in order (#1012): the
    AGENTS.md write, then each transitional repo-local Codex path or file it
    removes. `refused` names an AGENTS.md it will not touch, with the reason
    and the manual step; then nothing is written at all. `kept` lists the
    person's files left in transitional paths.
    """

    target = Path(repo).expanduser().resolve()
    path = agents_path(target)
    if path.is_dir():
        # #1072: a folder where the file belongs is not ours to read or replace.
        return {
            "operations": [],
            "refused": [
                _agents_refusal(
                    "is_directory",
                    "AGENTS.md is a folder, not a file, so Main Branch cannot read or "
                    "write the Codex guidance there. It left everything unchanged.",
                    "Move or rename the AGENTS.md folder (or merge what it holds into a "
                    f"file of your own), {_agents_rerun_step(target)}",
                )
            ],
            "kept": [],
        }
    rendered = render_agents_md(target, name=name, gh_username=gh_username)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    updated, refusal = _merge_agents_md(existing, rendered, _agents_rerun_step(target))
    if refusal is not None:
        return {"operations": [], "refused": [refusal], "kept": []}
    operations: list[dict[str, Any]] = []
    if existing != updated:
        operations.append(
            {"op": "write", "path": str(path), "rel": AGENTS_RELATIVE_PATH, "content": updated}
        )
    removals, kept = _transitional_cleanup(target)
    operations.extend(removals)
    return {"operations": operations, "refused": [], "kept": kept}


def agents_md_operations(
    repo: str | Path,
    *,
    name: str = "",
    gh_username: str = "",
) -> list[dict[str, Any]]:
    """Every destination `write_agents_md` touches, in order (#1012)."""

    return list(agents_md_plan(repo, name=name, gh_username=gh_username)["operations"])


def agents_md_operator_action(
    plan: dict[str, Any], *, repo: str | Path | None = None
) -> dict[str, Any] | None:
    """The `operator_actions` entry while the Codex AGENTS.md repair needs a person.

    None when the plan only replaces Main Branch's own guidance. Otherwise it
    names the reason and the manual step (#1052). `repo` names the business
    repo in the command (#1072).
    """

    refused = plan.get("refused") or []
    kept = plan.get("kept") or []
    effect = agents_md_apply_effect(plan)
    command = repair_command(repo)
    base = Path(repo).expanduser().resolve() if repo is not None else None
    if refused:
        reason = str(refused[0]["reason"])
        manual_step = str(refused[0]["manual_step"])
        changes = [AGENTS_RELATIVE_PATH]
    elif kept:
        reason = (
            "Old repo-local Codex folders hold files Main Branch cannot prove it wrote "
            "(your own files, or Main Branch files that were changed): "
            + ", ".join(kept)
            + ". The repair removes only unchanged Main Branch files and leaves these."
            + (_link_note([base / item for item in kept]) if base is not None else "")
        )
        # #1056: name exactly what an apply does, so the plan and the apply agree.
        removes = effect["removes"]
        manual_step = (
            "Open each file. Move anything you want to keep somewhere of your own, "
            "then delete the rest yourself. "
            f"`{command}` (or `--all-agents`) "
            + ("rewrites AGENTS.md, " if effect["writes"] else "")
            + (
                "deletes only these Main Branch files: " + ", ".join(removes)
                if removes
                else "deletes no files"
            )
            + "; it keeps the files above."
        )
        changes = [str(item["rel"]) for item in plan.get("operations", [])]
    else:
        return None
    action = engine_mod.operator_action(command, changes, f"{reason} {manual_step}")
    action.update(
        {
            "id": "codex-agents-md",
            "reason": reason,
            "manual_step": manual_step,
            "on_apply": effect,
        }
    )
    return action


def agents_md_apply_effect(plan: dict[str, Any]) -> dict[str, list[str]]:
    """What `--apply --only codex` or `--all-agents` does with this plan (#1056).

    The apply runs `write_agents_md`, which follows the same plan: a refusal
    writes and deletes nothing; otherwise it rewrites AGENTS.md when the plan
    says so, deletes exactly the planned Main Branch paths and keeps the rest.
    """

    if plan.get("refused"):
        return {"writes": [], "removes": [], "keeps": []}
    operations = plan.get("operations") or []
    return {
        "writes": [str(item["rel"]) for item in operations if item["op"] == "write"],
        "removes": [str(item["rel"]) for item in operations if item["op"] != "write"],
        "keeps": [str(item) for item in plan.get("kept") or []],
    }


def write_agents_md(
    repo: str | Path,
    *,
    name: str = "",
    gh_username: str = "",
) -> dict[str, Any]:
    target = Path(repo).expanduser().resolve()
    plan = agents_md_plan(target, name=name, gh_username=gh_username)
    changed_paths: list[str] = []
    kept = list(plan["kept"])
    for item in plan["operations"]:
        if item["op"] == "write":
            atomic_write_text(Path(item["path"]), item["content"])
            changed_paths.append(AGENTS_RELATIVE_PATH)
        elif _apply_transitional_operation(item, target):
            changed_paths.append(f"removed:{item['rel']}")
        elif Path(item["path"]).exists():
            kept.append(str(item["rel"]))  # #1067: changed since the plan, so it stays
    if not plan["refused"]:
        _remove_empty_transitional_dirs(target)
    return {
        "ok": not plan["refused"],
        "path": AGENTS_RELATIVE_PATH,
        "changed": bool(changed_paths),
        "changed_paths": changed_paths,
        "refused": plan["refused"],
        "kept": kept,
        "status": instructions_status(target),
    }
