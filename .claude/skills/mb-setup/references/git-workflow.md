# Save And Review Workflow

Use this reference when `/mb-setup` needs to explain how business-repo work is
saved, synced, or shared for review.

Main Branch uses git underneath, but the operator should hear business language
first:

| Technical layer | Operator language |
| --- | --- |
| tracked history | saved checkpoints |
| changed files | unsaved local work |
| remote update | shared repo update |
| pull request | proposal / review conversation |
| branch or worktree | workspace |

---

## Setup Saves

During setup, use `mb checkpoint` for business-repo saves. Do not ask the
operator to stage files or write raw save commands.

After the operator approves the created or changed files:

```bash
mb checkpoint --plan --json
mb checkpoint --validate "[added] initial business repo foundation" --json
mb checkpoint --message "[added] initial business repo foundation" --yes
```

Use the subject proposed by `mb checkpoint --plan` when it is good. If you need
to choose, use lower-case, past-tense business verbs:

- `[added]` for new durable context or setup files;
- `[updated]` for changed business context;
- `[decided]` for accepted setup decisions;
- `[connected]` for provider readiness that is now usable;
- `[ran]` for setup maintenance, migrations, imports, or checks;
- `[fixed]` for repaired wiring, links, or setup state.

Avoid engine-contributor subjects such as `[add]`, `[update]`, `[fix]`, or
`[refactor]` in business repos. Those are for this Main Branch repository, not the
operator's business history.

Do not add AI attribution trailers by default. Add an `Agent:` trailer only when
it changes how future readers should interpret generated copy, generated site
code, synthetic research, or compliance review.

---

## Common Setup Moments

Initial setup:

```bash
mb checkpoint --plan --json
mb checkpoint --validate "[added] initial business repo foundation" --json
mb checkpoint --message "[added] initial business repo foundation" --yes
```

Other common subjects follow the same plan, validate, save sequence: `[updated] core business context` after a context batch, `[connected] GitHub` after a provider becomes usable, `[updated] offer structure` after a multi-offer restructure.

If `mb checkpoint --plan` reports blockers, stop and explain the blocker in
plain language before trying to save.

---

## Sync And Review

If the operator asks to sync saved work, first read the current facts:

```bash
mb status --json --peek
```

Use the `git.summary`, `git.workflow_mode`, `git.ahead`, and `git.behind` facts
to explain whether work is:

- saved locally but not synced;
- waiting to catch up with the shared repo;
- waiting for local and shared saved work to be reconciled;
- ready to share as a proposal/review conversation.

The planned `mb publish --plan` command and packaged publish skill are not
shipped yet. Do not promise them. If the operator needs a proposal today, use
the available GitHub tooling only after explaining the path and getting
approval.

---

## GitHub Setup

GitHub is optional but recommended for shared backup, tasks, and proposals.
Check readiness from the business repo:

```bash
mb connect doctor --json
```

For a brand-new business repo, prefer `mb onboard` to create, save, push, and
report the setup receipt in one flow:

```bash
mb onboard --yes --name "[Business Name]" --path "[repo-path]" --github "[owner/repo]" --github-visibility private --push
```

Creating a private GitHub repo is a setup/provider step, not a substitute for
checkpointing approved business changes. Prefer private visibility unless the
repo is intentionally public. If an older installed `mb` does not expose the
GitHub onboarding option yet, use the raw GitHub CLI fallback only after
approval:

```bash
gh repo create [business-name] --private --source=. --push
```

Use `/mb-help` for beginner GitHub questions.
