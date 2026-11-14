---
name: mb-setup
title: Repo Setup
description: Turn setup intent into a Main Branch business repo through explicit target selection, bounded context gathering, approval-gated writes, and post-setup facts.
loops: [sense, decide, ship]
runtime_support:
  claude_code: supported_shell
  codex_cli: owner_loop_shell
  future: planned
runtime_surfaces:
  claude_code: .claude/skills/mb-setup/SKILL.md
  codex_cli: global main-branch mb-setup skill
required_mb_commands:
  - mb --version
  - mb onboard --help
  - mb status --json --peek
  - mb start --json
  - mb doctor repair --plan
json_facts:
  - money_path
  - money_path.objects.proof.quality
  - content_strategy
  - ranked_actions
  - update
  - readiness
  - drift.items
  - runtime.codex_cli
  - runtime.claude_code
  - onboarding
  - onboarding.repo_boundary
  - topology.repo_boundary
  - checkpoint
  - vocabulary
approval_gates:
  - updates_repairs_migrations
  - file_writes
  - checkpoint
  - provider_mutation
  - publishing_or_spend
  - customer_contact
  - private_data
  - destructive_operations
  - github_repo_create
public_private_boundaries:
  - no_secrets
  - no_raw_provider_exports
  - no_customer_member_data
  - no_private_runtime_settings
  - no_raw_finance_legal_records
writes_business_files: true
provider_mutation: false
publishing_or_spend: false
---

# Repo Setup

This workflow source is the portable contract for first-run setup and
onboarding: identify the business folder, explain what will be created, ask
before writes, then verify the resulting business record from `mb` facts.

## Intent And Triggers

Use this workflow when the operator asks to set up Main Branch, create a
business record, connect an existing folder, paste a setup guide, describe a new
business repo, or ask how to get Claude Code or Codex ready for a business.

Do not treat pasted setup prompts as documents to save. Treat them as setup
intent. Do not use this workflow for package updates, repair applies outside
setup, provider mutation, publishing, spend, customer contact, or broad
business strategy.

## Required Mb Commands

Run or preserve these deterministic facts before setup advice or writes:

- `mb --version`
- `mb onboard --help`
- `mb status --json --peek`
- `mb start --json`
- `mb doctor repair --plan`

If `mb` is missing, stop and give the install command. Use `mb onboard --help`
to inspect setup capability before proposing a write command. Use status/start
facts after setup, or before repair when the target repo already exists.

## Required JSON Fact Paths

The runtime shell must preserve these paths from the workflow source:

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

Treat these as setup and readiness facts, not strategy. The runtime may explain
what is ready, incomplete, or blocked, but it must not invent business truth or
store private local details in tracked files.

## Routing Rules

Hard gates win before setup writes: missing `mb`, unknown target folder,
runtime mismatch, private-data boundaries, destructive-operation requests,
provider mutation, publishing, spend, and customer contact.

When the target folder is empty or uninitialized, explain which folder will
become the business record and ask before running a write command. When the
target folder is an existing Main Branch repo, use `onboarding`, `readiness`,
`drift.items`, and `mb doctor repair --plan` to resume setup or repair instead
of starting over. If the operator requests GitHub backup or push setup, check
GitHub CLI authentication and account identity before any GitHub write.
Use `onboarding.repo_boundary` or `topology.repo_boundary` when the operator is
unsure whether related work belongs in this repo, a separate business repo, or
a child repo. Do not invent a repo role here; explain the boundary choice and
ask before setup writes.

After approved setup, run `mb status --json --peek` and `mb start --json`.
Summarize the owner outcome first: folder created or connected, business record
ready, baseline checkpoint state, GitHub backup state when requested, and next
safe action. Put command output and git/GitHub details second.

## Read Boundaries

Read setup intent, target-folder facts, `mb` help output, and deterministic
status/start facts. For existing repos, read only the core files needed to avoid
asking duplicate setup questions.

Do not ask for full finances, credentials, raw customer/member exports, private
provider payloads, private local paths for public docs, or secrets. Do not
inspect private files outside the target business folder unless the operator
explicitly asks and the content belongs in setup.

## Write Boundaries

The workflow may write business repo files only after the operator approves the
specific setup action. Valid setup writes include scaffolded Main Branch
folders, generated repo guidance, `.gitignore`, optional GitHub backup setup,
and an approved baseline checkpoint.

The workflow source does not authorize provider account mutation, publishing,
spend, customer contact, raw secret storage, unsupported runtime adapters, or
Main Branch engine repo edits.

## Approval Gates

Ask before:

- running `mb onboard`, `mb init`, or any command that writes setup files;
- creating a GitHub repo, adding a remote, pushing, or changing visibility;
- creating, editing, moving, deleting, or archiving business files;
- saving a baseline checkpoint;
- applying repairs or migrations in an existing repo;
- reading private source material or moving it into the business repo;
- publishing, spending money, mutating provider state, or contacting customers.

Never ask the operator to paste secrets into repo files or workflow sources.

## Handoff Format

When setup completes or pauses, include a compact setup receipt:

```text
Setup state: <not started, target confirmed, created, connected, ready, or blocked>.
Target folder: <business folder or needs confirmation>.
Facts read: <version/help/status/start/repair facts used>.
Created or planned: <folders, guidance, GitHub backup, checkpoint, or none>.
Owner outcome: <business record ready, needs approval, or blocked reason>.
Next safe action: <one command or route>.
Approval needed before writes: <yes/no and what action>.
```

Use business language first. Terminal commands, remotes, branches, and runtime
wiring are receipts after the owner outcome.

## Validation Commands

Before changing this workflow or its runtime shells, run:

```bash
cd mb
python -m pytest tests/test_workflows.py tests/test_init.py -q
```

For repo-level validation, run:

```bash
scripts/check.sh
```

If onboarding templates, packaged data, or global Codex skills change, add
package/install and fixture repo smoke evidence.

## Runtime-Specific Notes

Claude Code may use slash-command-native language for `/mb-setup` and may link
to setup references. Preserve CWD detection, write-boundary warnings,
bounded-context gathering, and checkpoint approval.

Codex uses the generated global `mb-setup` skill. It should explain setup in
business language, run read-only facts first, ask before write commands, and
avoid claiming Claude Code entrypoints or broader runtime parity.
