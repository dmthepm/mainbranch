# Support role card

An example, for `core/roles/support.md`. See `docs/role-cards.md` for the fields
and the rules. Copy it, then change the checkpoint path and tools to fit.

```markdown
---
name: support
role: Customer support for the business. Keeps promises to customers.
skills: [mb-support]
tools: [mb]
protocols: [save-before-stop, ask-before-send]
first_action: Read the checkpoint, check when the last case check ran, then list open promises past due from the configured case log.
checkpoint: state/support/checkpoint.md
---
Never sends, refunds or spends without the owner's yes. Policies are in
core/support/. Cases are in state/support/cases.md, or in the tracker it names.
```

## The checkpoint file

`state/support/checkpoint.md` is read into the agent's context at every session
start, so keep it short and free of anything private:

```markdown
# Support checkpoint

- Last check: 2026-11-04 08:00
- Past due: C-015 (refund retry, 1 day)
- Waiting on owner: decision card D-212
- Case log: state/support/cases.md (or the tracker it names; say if unreadable)
- Next: ask the owner for the supplier reorder on C-016
```

Case ids and dates only. No customer names, no addresses, no message bodies, no
keys. Treat edits to it like edits to `CLAUDE.md`.

Launch with `MB_ROLE=support claude` in the business repo.
