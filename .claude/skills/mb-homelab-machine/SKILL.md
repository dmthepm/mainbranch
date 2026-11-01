---
name: mb-homelab-machine
description: "Set up, maintain, harden or extend an always-on machine that runs your agents (a mini PC, Mac mini or homelab box). Use whenever the operator asks about picking hardware, installing Ubuntu or Omarchy for agents, the first week on a new box, what to check daily, weekly or monthly, backups and restore drills, disk health, quota or tool checks, adding a business account, a standing agent role, a data collector or a backup drive, Checkpoint 1 hardening, or whether to move to containers, VMs or a second machine. Read-only checks; the owner runs root steps."
loops: [sense, decide, ship]
---

# Always-on agent machine

Say first: "I'll check this machine read-only and prepare any change for you to
run. I won't use sudo, change settings or print secret values."

This skill turns the Main Branch machine guide into jobs an agent can run and
check. The guide is the human document; the references below point to its
sections instead of copying them:
[Machine Setup](https://github.com/dmthepm/mainbranch/blob/main/docs/machine-setup.md#part-1-concepts).
No business repo is needed.

Run `mb machine doctor` first for the current account's read-only baseline.
Use `mb machine doctor --json` when structured results are needed. Exit 3 means
incomplete verification, not failed verification. Exit 1 means a failed check;
exit 2 means no verdict. Report NOT VERIFIED rows and their reasons. This first
release has no manifest support, so a run cannot establish full machine health.
The maintenance rows below still cover checks outside doctor's current scope.

## Pick the job

| The operator wants to | Read |
| --- | --- |
| Pick hardware, install the OS, finish the first week, move to a new host | [references/setup.md](references/setup.md) |
| Know what to check today, this week or this month | [references/maintenance.md](references/maintenance.md) |
| Add a business, a standing role, a data collector or storage | [references/extension.md](references/extension.md) |
| Harden the box, or decide on containers, VMs or a second machine | [references/hardening.md](references/hardening.md) |

Read only the reference for the job. If the request spans two, finish one job
and its done-checks before starting the next.

## Principles

1. **The owner steers.** You prepare each command and explain it; the owner
   reads it and runs anything that needs root, a sign-in or a payment. Never
   run `sudo`, never complete a sign-in, never change the machine yourself.
2. **One box for the agents.** Agent sessions start on the always-on box. The
   laptop and phone only view and steer. If closing the laptop stops work, the
   setup isn't finished.
3. **Isolation by Unix user.** One business per Unix user. Several
   roles may share one business's account. A hook or rule inside the same user is advisory, not a security
   boundary. Accounts reach each other only through the owner until a
   reviewed gate exists.
4. **Backups you've restored.** A backup counts only after a restore drill
   from it passed. Until then, report backups as NOT VERIFIED.
5. **Requirements, not commands, for isolation controls.** Firewalls, network
   fences, process hiding, sandboxes and gates are written as requirements and
   expected results. Their commands come from the owner's security reviewer,
   never from this skill.
6. **Start at Checkpoint 1; graduate only on a recorded trigger.** One Linux
   user per business is the first checkpoint. Containers, VMs or a second
   machine come only when a trigger in the hardening reference is recorded
   with its evidence.
7. **Unknown is never a pass.** A check you can't run, a reading that is stale
   and an owner's word are all NOT VERIFIED. Say which, and why.

## Done-checks

Every job ends with a report, one row per check:

| Check | Result | Evidence | Next step |
| --- | --- | --- | --- |
| Agent account has no admin group | PASS | `id` lists only its own group | none |
| Restore drill this month | NOT VERIFIED | no dated drill in the machine record | owner runs a drill |

- **Result** is PASS, FAIL or NOT VERIFIED. Write "NOT VERIFIED (owner
  attested)" when only the owner's word supports it.
- **Evidence** is what you read, summarized: a status word, a mode, a date.
  Never paste tokens, keys, passwords, recovery codes or full config files.
- Done for each job means:
  - **Setup:** every first-week step in setup.md is PASS, including the reboot
    and lid-closed tests, and the restore test passed before business data
    went on the box.
  - **Maintenance:** the daily rows are fresh (read today), weekly and monthly
    rows carry dates inside their window, and every FAIL has a next step.
  - **Extension:** the new account, role, collector or drive has its own row in
    the machine record and its checks are PASS.
  - **Hardening:** all 14 Checkpoint 1 lines are PASS after a reboot, with the
    run dated, or each failing line names its owner and next step.

Run checks as the account they describe: operator-level checks from the
owner's admin session without `sudo`, and per-account checks as that account.
If a check needs root, prepare it for the owner and report NOT VERIFIED until
they share the result.

## The machine record

Keep one record per machine, owned by the admin account and outside every
business repo: the tool index, the restart table, backup layers and drill
dates, collectors, Checkpoint 1 run dates and any recorded graduation trigger.
If it doesn't exist yet, offer to draft it; the owner decides where it lives.

## What this skill never does

- Run `sudo`, change settings, install software or reboot the machine.
- Write firewall, network-fence, process-hiding, sandbox or gate recipes.
- Read or print secret values, key files, browser profiles or clipboard
  history files.
- Read another account's home folder or business data.
- Treat a missing, failed, stale or attested check as a pass.
- Publish the report or send it anywhere. The owner shares it if they want.
