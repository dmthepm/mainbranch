# Provider mutation contract: preview, approve, apply, verify

Reading a provider's state and **mutating** a provider's account are different
surfaces with different trust. A read is recoverable; a write to a CRM, an
email list, an ad platform, or an account's metadata changes the outside world
and often cannot be cleanly undone. Main Branch agents move fast from connector
setup into real external-account writes — updating CRM contacts, smoke-testing
sends, creating ad drafts — and "be careful" as prose is not a contract.

This page is the engine-side doctrine for any surface that writes to an
external provider on a business's behalf. It graduated from a live business we
built, where real CRM records were updated, outbound email was smoke-tested
through a freshly wired provider, and the operator asked whether the agent
could build directly in an ad platform — all handled by conversational
approval, with no deterministic gate underneath.

## The pattern

Every provider mutation runs the same five steps. Never collapse them.

1. **Read-only discovery first.** Establish current provider state with a read
   before proposing any change. A write you cannot preview, you do not make.
2. **Build a sanitized mutation plan.** Name the affected provider, the object
   type, the **count** of objects, and a risk level (`low` / `material` /
   `irreversible`). The plan describes the change in business terms — "update
   42 CRM contacts' lifecycle stage", "send 1 smoke email to an owned inbox",
   "create 1 paused ad draft" — and never embeds private rows, account IDs,
   customer names, payloads, or tokens. The plan is safe to show and safe to
   record; the raw data is not.
3. **Require explicit operator approval.** The operator approves the named
   plan, not a vague "go ahead." Spend, sends, customer contact, and account
   changes each need their own approval — one approval does not blanket the
   next surface. Default to the most conservative form (a paused draft, a
   dry-run, an owned-inbox smoke test) before anything live.
4. **Apply with minimal scope.** Use the narrowest credential and the smallest
   change that satisfies the approved plan. Never widen scope mid-apply; if the
   apply needs more than the plan named, stop and re-plan.
5. **Verify and record a private-safe summary.** Confirm the change took
   (re-read the provider), then write a business-readable record — counts,
   provider, risk, outcome — with the same sanitization as the plan. When the
   mutation changes business state, point the operator at a checkpoint or the
   relevant lane (bet, push, decision). Raw payloads stay out of git.

## Plan / apply example

A CRM lifecycle-stage update, in the contract's language:

```
mb <provider> plan      # read-only: what would change
  provider: crm
  object: contact
  count: 42
  change: lifecycle_stage "lead" -> "member" for contacts on the reconciled export
  risk: material (customer-visible segmentation)
  scope: contacts.write (no delete, no email)
  preview: 42 matched, 0 ambiguous, 0 outside the export

# operator reviews the sanitized plan and approves THIS plan

mb <provider> apply --approve   # minimal scope, named change only
  applied: 42 contacts updated
  verify: re-read shows 42 at "member", 0 drift
  record: pushes/<date>/crm-reconcile.md (counts + outcome, no rows)
  next: mb checkpoint --plan
```

The same shape holds for an email smoke test (`count: 1`, an owned inbox,
`risk: low`), an ad draft (`risk: material`, created **paused**, never
launched without separate spend approval), or a provider metadata update.

## What never enters a public or git artifact

- Tokens or credentials of any kind.
- Customer rows, contact names, email addresses, or account identifiers.
- Raw provider payloads or exported member lists.

The plan and the record carry **counts and shapes**, not data. If a number
can't be reported without a private row attached, report the number and leave
the row in the provider.

## Read vs write, always separate

`mb connect` read paths (`status`, `doctor`, `identity`, `token`, `test`,
`rotate`) never mutate a provider. `mb connect exec` runs whatever command it
is given, so a write command run through it is a write surface like any other:
the credential reaching the command is not approval to write. Write surfaces
are the ones this contract governs. An agent
that can read a provider has not been granted permission to write it — the
write needs its own plan and its own approval, every time.

A worked provider instance lives in
[google-ads-gtm-conversion-rubric.md](google-ads-gtm-conversion-rubric.md):
publishing a GTM container, creating a Google Ads conversion action, uploading
offline conversions, and launching/budget changes are each mutations that run
this contract, with the live-API automation operator-gated until smoke
evidence exists. For agent access to Google Ads (a Read only reader user, why
the OAuth scope and a read-only tool are not the boundary, and a reviewed
Google Ads Script as the default agent write route), see
[google-ads-agent-access.md](../.claude/skills/mb-ads/references/google-ads-agent-access.md).
