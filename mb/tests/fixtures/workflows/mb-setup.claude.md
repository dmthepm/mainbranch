# Generated Claude Shell: Repo Setup

Source workflow: `workflows/mb-setup/workflow.md`
Runtime support: `claude_code: supported_shell`
Approval gates: `updates_repairs_migrations`, `file_writes`, `checkpoint`, `provider_mutation`, `publishing_or_spend`, `customer_contact`, `private_data`, `destructive_operations`, `github_repo_create`
Public/private boundaries: `no_secrets`, `no_raw_provider_exports`, `no_customer_member_data`, `no_private_runtime_settings`, `no_raw_finance_legal_records`

Use from `/mb-setup` when the operator wants to create or connect a business repo. Treat pasted setup prompts as setup intent, confirm the target folder, and ask before running a write command.

This snapshot does not replace shipped `.claude/skills` prose.

## Required mb Commands

- `mb --version`
- `mb onboard --help`
- `mb status --json --peek`
- `mb start --json`
- `mb doctor repair --plan`

## Required JSON Fact Paths

- `money_path`
- `money_path.objects.proof.quality`
- `content_strategy`
- `ranked_actions`
- `update`
- `readiness`
- `drift.items`
- `runtime.codex_cli`
- `runtime.claude_code`
- `onboarding`
- `onboarding.repo_boundary`
- `topology.repo_boundary`
- `checkpoint`
- `vocabulary`

## Routing

1. Treat setup prompts as setup intent and onboarding intent, not as documents to save.
2. Confirm the target folder and inspect setup capability before writes.
3. If `mb` is missing, stop and give the install command. If GitHub backup is requested, check GitHub CLI auth before any GitHub write.
4. Ask before running a write command such as onboarding, repo creation, file scaffolding, GitHub remote/push, repair apply, migration apply, or checkpoint save.
5. After approved setup, rerun status/start facts and report the owner outcome before command receipts.

## Handoff Shape

```text
Setup state: <not started, target confirmed, created, connected, ready,
or blocked>.
Target folder: <business folder or needs confirmation>.
Facts read: <version/help/status/start/repair facts used>.
Created or planned: <folders, guidance, GitHub backup, checkpoint, or none>.
Owner outcome: <business record ready, needs approval, or blocked reason>.
Next safe action: <one command or route>.
Approval needed before writes: <yes/no and what action>.
```

Use business language first. Technical commands, runtime wiring, provider refs,
and file paths are receipts after the owner-facing state unless the operator asks
for plumbing.
