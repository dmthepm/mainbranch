# Extension: a business, a role, a collector, storage

Guide sections this follows:
[One user account per business](https://github.com/dmthepm/mainbranch/blob/main/docs/machine-setup.md#one-user-account-per-business),
[Admin account and agent accounts](https://github.com/dmthepm/mainbranch/blob/main/docs/machine-setup.md#admin-account-and-agent-accounts),
[Shared tools, private data](https://github.com/dmthepm/mainbranch/blob/main/docs/machine-setup.md#shared-tools-private-data),
[Accounts talk through a gate](https://github.com/dmthepm/mainbranch/blob/main/docs/machine-setup.md#accounts-talk-through-a-gate-not-shared-folders),
[Credentials](https://github.com/dmthepm/mainbranch/blob/main/docs/machine-setup.md#credentials).

Every addition ends with its own row in the machine record and a done-check
table. You prepare the steps; the owner runs root steps and sign-ins.

## Add a business

A new business gets its own Unix user. Never add it to an existing account,
even for a trial: one business per Unix user, and a same-user
hook is advisory, not a boundary. Several standing roles can share one business's
account, because they share its trust.

Requirements:

- New agent account, no `sudo`, in no admin group (`sudo`, `adm`, `docker`,
  `lxd`, `incus-admin`).
- Private home and private temporary folder.
- Its own keys and sign-ins, each key doing one job, with an expiry where the
  vendor offers one. The owner completes every sign-in.
- Linger on and its multiplexer as a user service, inside its own memory and
  process limits.
- Main Branch installed for that account and the business repo set up there.
- Added to the backup set and to the next restore drill.
- If the box claims Checkpoint 1, the cross-tenant lines in hardening.md are
  rerun with the new account included.

**Done-check:** the setup.md rows for Accounts, Private homes and Sessions are
PASS for the new account; the account appears in the restart table and the
backup set; a reboot test passed with it.

## Add a standing role

A standing role is an agent that keeps running across days (for example a
bookkeeper or a support triager for one business). Roles go stale unless a
file that a restart loads holds what they are doing.

Requirements:

- It runs in the account of the business it serves, never in a shared one.
- It has a role card (purpose, limits, model, cadence) and a checkpoint file
  it writes as it works and reads when it starts.
- It has a row in the restart table: agent, Unix user, session, checkpoint
  file, last checkpoint time.
- Heavy work goes through the shared heavy-job lock with its own memory cap
  and time limit.

**Done-check:** restart the role's session; it resumes from its checkpoint
file without being re-briefed, and the restart table's time updates.

## Add a data collector

A collector pulls data from an outside source on a schedule (mail, a payments
provider, an ad account). A reader that holds no state of its own needs the
collector's record to say what happened and since when.

Requirements:

- Read-only credentials for the source when reading is enough.
- A source-health record per source, updated on every run, with at least:
  source, last attempt, last success, status, failing since (empty when
  healthy), items read, and the expected interval.
- Timers and scheduled jobs don't send messages to other accounts or people.
  If a collector's result needs to go somewhere, an agent session picks it up
  and sends it.
- Identifiers and counters have no fixed width that can run out.

**Done-check:** the source-health record exists, its last success is newer
than the expected interval, and "failing since" is empty. A record without a
last-success time is NOT VERIFIED.

## Add storage

Follow [Backup storage](https://github.com/dmthepm/mainbranch/blob/main/docs/machine-setup.md#backup-storage)
for picking the drive.

Requirements:

- Mounted by filesystem UUID, never by device name.
- SMART health readable through the actual enclosure; return it if not.
- The nightly copy fails loudly when the drive is missing or not mounted, so
  it never fills the box's own disk.
- Added to the restore drill.

**Done-check:** `/etc/fstab` mounts it by `UUID=`; `findmnt <backup mount>`
shows it mounted; the owner shared a SMART health result (else NOT VERIFIED);
a restore from it is dated in the machine record.

## What goes to the platform owner

Prepare these and hand them over; don't do them or write their recipes:

- Anything that needs root: users, groups, services, mounts, packages,
  firmware.
- Isolation controls: firewall and network rules, process hiding, sandboxes,
  the gate between accounts. These go to the owner's security reviewer as
  requirements.
- Moving a shared tool's pin, and any override of the release-age wait.
- Anything one business needs from another: the owner carries it across.
- A recorded graduation trigger (see hardening.md).
