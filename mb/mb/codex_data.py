"""Static Codex adapter definitions and fallback guidance."""

from __future__ import annotations

from typing import Any

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
    "mb-seo",
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
    "mb-seo",
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
    "mb-seo": "Explain SEO support status for Main Branch.",
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
    "mb-seo": ("mb workflow list --runtime codex --json",),
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
    "mb-seo": "intentionally_unsupported",
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
        "id": "seo",
        "label": "SEO review and OpenSEO research",
        "surface_type": "skill",
        "claude_surface": "/mb-seo",
        "claude_skill_sources": ("mb-seo",),
        "codex_status": "intentionally_unsupported",
        "source_status": "intentionally_unsupported",
        "codex_surface": "Boundary explainer only; no Codex execution route",
        "codex_entrypoints": ("main-branch mb-seo",),
        "commands": (),
        "status_reason": "Experimental Claude Code skill with no Codex runtime proof.",
        "notes": "Claude Code only until a Codex run proves setup and spend approval.",
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
