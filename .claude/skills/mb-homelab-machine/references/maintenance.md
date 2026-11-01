# Maintenance: daily, weekly, monthly

Guide sections this follows:
[Backups and updates](https://github.com/dmthepm/mainbranch/blob/main/docs/machine-setup.md#backups-and-updates),
[Backup storage](https://github.com/dmthepm/mainbranch/blob/main/docs/machine-setup.md#backup-storage),
[Sessions that survive a reboot](https://github.com/dmthepm/mainbranch/blob/main/docs/machine-setup.md#sessions-that-survive-a-reboot),
[One heavy job at a time](https://github.com/dmthepm/mainbranch/blob/main/docs/machine-setup.md#one-heavy-job-at-a-time).

When the operator asks "what should I check?", run the rows for the window
they name (default: today's daily rows, plus any weekly or monthly row whose
last date is outside its window). Every row is read-only. Report in the table
from SKILL.md. A reading without a time is NOT VERIFIED.

## Principles and their checks

**Updates go through one version manager.** Shared tools move through one
version manager with a minimum release age by default, so a new release
waits before it lands. A confirmed security advisory may skip the wait through
one audited override, which records the advisory, the tool, the version and
who approved it. The exact command and rules are pending the owner's security
review; until they arrive, treat this as a requirement and don't invent a
command.
*Done-check:* every pin in the tool index names an exact version (never
`latest`), and every version newer than the release-age window has a matching
override entry. Anything else is FAIL.

**Every listed tool exists and runs.** Tools that never got installed on a new
host are a known failure.
*Done-check (daily):* for each tool in the index, `command -v <tool>` finds it
and `<tool> --help` exits 0. List misses by name. A miss is FAIL even if no
one has used the tool yet.

**Quota readings carry their age.** Keep a snapshot per account: percent used,
the window's reset time, and when the reading was taken.
*Done-check (daily):* each reading is younger than the window you agreed with
the owner (for example two hours). Stale means unknown, never available:
report a stale or missing reading as NOT VERIFIED, not as headroom. Banked
resets and credits are shown for information only; never redeem or spend one,
and bring them up with the owner only when the window shows 100% used.

**Every agent can restart from its checkpoint.** The machine record has a
restart table: agent, Unix user, session, checkpoint file, last checkpoint
time.
*Done-check (daily):* each checkpoint file exists, is readable by its own
account, and is newer than that agent's last working session. Run the check
as the agent's account; you can't read another account's files.

**Backups count only after a restore drill.**
*Done-check:* see the backup rows below. A backup job that "succeeded" with no
drill inside its window is NOT VERIFIED.

**One business per Unix user.**
A same-user hook is advisory, not a boundary.
*Done-check (weekly):* the restart table shows no two businesses
sharing an account.

## Daily

| Check | Done when |
| --- | --- |
| Sessions | as each agent account, `systemctl --user is-active <unit>` shows `active` |
| Tools | every tool in the index is found and `--help` exits 0 |
| Quota | every reading has a reset time and is fresh; stale is NOT VERIFIED |
| Checkpoints | every row of the restart table has a fresh checkpoint file |
| Nightly backup | the local backup log's last run finished today and wrote to `<backup mount>`, and `findmnt <backup mount>` shows the drive mounted. A run that reports the drive missing is FAIL |
| Disk space | `df -h /` and `df -h <backup mount>` each have the headroom the owner set (for example 15% free) |
| Source health | every collector's source-health record shows a success newer than its expected interval (see extension.md) |

## Weekly

| Check | Done when |
| --- | --- |
| OS updates | Ubuntu: unattended upgrades ran in the last 7 days (`/var/log/unattended-upgrades/` has a dated entry; NOT VERIFIED if the log isn't readable without root) and `/run/reboot-required` is reported if present. Omarchy: the last full update is under about 7 days old; the owner runs it, never a single-package upgrade |
| Services after update | after any update or reboot, every `<unit>` is `active` again |
| Off-site backup | the off-site tool's last snapshot is under 7 days old (read its snapshot list or log, never its password) |
| Disk health | SMART overall health is PASSED for the system disk and the backup drive. `smartctl` usually needs root: prepare `smartctl -H <device>` for the owner and report NOT VERIFIED until they share the result |
| Accounts | one business per Unix user; no agent account in an admin group |
| Listeners | `ss -Htln` lists no dev server or debug port on a non-loopback address |

## Monthly

| Check | Done when |
| --- | --- |
| Restore drill | a real folder restored from each backup layer this month, the restored hashes match, and the drill is dated in the machine record. The off-site drill runs from another machine, without the box |
| CVE inventory | the inventory of installed tool and package versions was refreshed this month, one row per key (tool and version); a duplicate key is an import error to fix, not a row to add |
| Tool pins | each pin was reviewed against its advisories; overrides used this month are listed with their approvals |
| Reboot test | after a reboot in the owner's window, every account's sessions came back with nobody logged in |
| Firmware | firmware and BIOS updates happen only with the owner at the machine; record the date, NOT VERIFIED (owner attested) |
| Hardening | if the box claims Checkpoint 1, the dated run is under a month old (see hardening.md) |
