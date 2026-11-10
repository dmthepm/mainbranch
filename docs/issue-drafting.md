# Privacy-Safe Issue Drafting

Main Branch improves through public friction reports, but business repos can
contain private context. Use `mb issue` when an error, confusing step, missing
workflow, or question should become a GitHub issue.

When the source is a full customer call, webinar transcript, chat export, or
agent session log, first use [`session-excavation.md`](session-excavation.md)
to classify findings by priority and keep private evidence out of public
GitHub.

## Commands

```bash
mb issue draft bug --command "mb status" --what-happened "..." --expected "..."
mb issue draft feature --problem "..." --proposal "..."
mb issue draft question --question "..." --context "..." --tried "..."
```

Drafts are written under `.mb/issue-drafts/` in the active business repo. That
directory is local operational state and should stay gitignored.

Bug drafts include scrubbed `mb doctor --json` output by default. Use
`--no-doctor` when you only want the fields you supplied.

After reviewing the draft:

```bash
mb issue open .mb/issue-drafts/<draft>.md --yes
```

`mb issue open` uses `gh issue create` when GitHub CLI is installed and
authenticated. If `gh` is missing, unauthenticated, or `--yes` is omitted, it
prints a browser/manual fallback instead of submitting.

## Privacy Defaults

The scrubber redacts common hazards:

- local absolute paths such as home, temp, volume, and Windows drive paths;
- token-shaped values and bearer tokens;
- sensitive environment lines such as `API_TOKEN=...`;
- URL query secrets such as `?token=...`;
- email addresses.

The scrubber is a guardrail, not a guarantee. Before submitting, review the
draft and remove private business data, customer/member data, account details,
raw files, screenshots with private information, and secrets.

This rule is for public GitHub issues. Your own team's private tracker can hold
real recordings and examples under
[where data lives](../.claude/skills/mb-setup/references/where-data-lives.md);
a public issue never does. Describe the case with invented values in the same
shape.

## Skill Convention

Skills should suggest `mb issue draft` only when the operator hits reproducible
friction that would help future users:

- command or setup errors that persist after the documented repair command;
- missing Main Branch workflow surfaces;
- confusing docs or runtime handoff steps;
- questions whose answer belongs in public docs or the issue tracker.

Skills should not file or open issues on their own. They should summarize the
public-safe problem, recommend the matching shape (`bug`, `feature`, or
`question`), and let the operator run `mb issue open ... --yes` after reviewing
the draft.

For larger transcript/export reviews, skills should also leave behind the
reusable artifact that would make the same review easier next time: a doc,
decision, fixture, test, template, or skill reference.
