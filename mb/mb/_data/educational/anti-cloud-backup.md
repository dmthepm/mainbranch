---
type: educational
topic: anti-cloud-backup
status: draft
last-updated: 2026-05-08
---

# Why sensitive business records should not live in consumer cloud sync

Main Branch is local-first because some business records should not be treated
like casual synced documents.

Consumer cloud sync tools are convenient. They are also the wrong default for
raw finance, legal, customer, credential, and account-export material.

## The beginner version

Use this rule:

- the durable business record can live in the business repo;
- raw sensitive records need stricter boundaries;
- secrets never belong in committed markdown;
- cloud sync is not the same thing as a deliberate backup plan.

The business repo is for durable, safe operating truth: offers, audience notes,
research, decisions, pushes, logs, documents, and summaries. Sensitive source
material should either stay out of the repo or live in a separate private repo
with explicit access rules.

## Why not iCloud Drive, Google Drive, Dropbox, or OneDrive?

**Sync is not review.** A synced folder copies whatever lands in it. That is
dangerous for ledgers, exports, customer lists, legal docs, and tokens because
one accidental file can spread to every device and vendor copy before anyone
reviews it.

**Conflict handling is not audit handling.** Cloud sync tools try to keep files
available. They are not designed to preserve a clean accounting or legal audit
story. A conflicted copy may be survivable for a draft, but it is unacceptable
for records you must reconcile later.

**Provider access is not the same as owner custody.** Even when a provider is
reputable, the business has less control over account access, legal process,
retention, and recovery than it does over a repo plus a tested backup plan.

**Agents can accidentally read what you put nearby.** If a runtime has access
to a folder, assume it can inspect files in that folder. Keep private raw data
outside the normal business repo unless a workflow explicitly needs a safe
summary.

## What Main Branch recommends

For the everyday business record, use the normal repo created by:

```bash
mb onboard --name "My Business" --path my-business
```

For raw sensitive material, choose a stricter home:

1. Keep secrets in the OS keychain, a password manager, runtime local config,
   or environment variables.
2. Keep raw finance or legal files in a separate private repo or system with
   explicit access boundaries.
3. Put only durable summaries, provider-safe IDs, and decisions in the shared
   business repo.
4. Test restore before you trust any backup.

## Where hledger fits

hledger plain-text journals are useful because they are inspectable and
versionable. That does not mean every journal belongs in the shared business
repo. A safe pattern is:

- real journals and statements in a private books vault or restricted books repo;
- business-readable summaries in `core/finance/` or `log/`;
- no account numbers, credentials, or customer-private rows in shared docs.

See:

```bash
mb educational hledger
```

## What Main Branch does not claim

Main Branch does not provide legal, accounting, tax, or security advice. It
provides a repo-backed operating model and guardrails that keep sensitive raw
data from becoming casual context.

If you are unsure whether a file is safe to commit, do not commit it. Ask
Claude to summarize it without copying private details, or keep it outside the
business repo.
