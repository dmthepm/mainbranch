---
type: decision
date: 2026-10-31
status: accepted
topic: Warn on the old plugin address and pin each release to an exact commit
linked_issues:
  - https://github.com/dmthepm/mainbranch/issues/1271
linked_decisions:
  - decisions/2026-06-10-skills-distribution-plugin-vs-engine-router.md
linked_docs:
  - docs/migrating.md
participants: [Devon, Claude]
tags: [plugin, release, supply-chain]
---

# Plugin source and release pinning

## Decision

1. A repo or plugin registration that still names `noontide-co/mainbranch` keeps
   counting as wired. `mb` adds a separate warning. `wired` keeps its meaning.
2. Each release pins plugin content to one exact commit. Owners update on purpose.
   The marketplace uses an HTTPS `url` source with a `sha`.

## Why

The old address works only through a GitHub redirect, which ends if a new
repository takes that name. Changing what `wired` means would break tools that
read it, while a separate warning tells the owner what to do.

Today the marketplace source is `./`, so an install takes whatever is on main.
One version label can cover different skills, and skills can need a newer `mb`
than the owner has. A rolling release branch would be easier to update, but it
can move and can't prove exact content.

## Evidence

Tested on 31 Oct 2026 with Claude Code 2.1.309 on Linux, CLI only, in a
throwaway profile. Both source shapes installed the exact commit. Moving the pin
from the 0.6.16 commit to the 0.6.17 commit behaved differently:

| Source | `claude plugin update` |
| --- | --- |
| `github` with `sha` | Failed: it cloned over SSH, and the host had no key for github.com. |
| `url` (HTTPS) with `sha` | Updated from 0.6.16 to 0.6.17 at the exact commit. |

Not tested: Claude Desktop, and machines with SSH set up.

## Consequences

The pin has to name the release commit, so it lands after that commit exists.
Release steps must handle that order and check the pinned commit holds the
declared version. Installs between releases no longer follow main.
