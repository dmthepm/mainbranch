# Hardening: Checkpoint 1 and when to graduate

Guide sections this follows:
[One user account per business](https://github.com/dmthepm/mainbranch/blob/main/docs/machine-setup.md#one-user-account-per-business),
[Admin account and agent accounts](https://github.com/dmthepm/mainbranch/blob/main/docs/machine-setup.md#admin-account-and-agent-accounts),
[Managing it from a Mac](https://github.com/dmthepm/mainbranch/blob/main/docs/machine-setup.md#managing-it-from-a-mac).

Hardening works like a site ladder: reach the first checkpoint, use it for a
while, and move up only when a specific wall is hit and recorded. Each tier
costs operating complexity. Graduate when the *current* tier is failing, not
because a future tier sounds safer.

This file lists requirements and what "pass" means. It carries no install or
configuration commands: those come from the owner's security reviewer. Fixed
read-only commands may check a named fact, and each proves only that fact. Report each line PASS only from evidence the owner or their
reviewer produced; otherwise NOT VERIFIED.

## Checkpoint 1: one Linux user per business

A machine reaches Checkpoint 1 when every line passes on the live host
**after a reboot**, with the run dated in the machine record. `A` and `B` are
two business accounts (tenants).

| # | Requirement | Pass means |
| --- | --- | --- |
| 1 | Other users' processes and their arguments are hidden | the process table is mounted so each user sees only their own processes, with one observer group (the owner only) allowed to see all; the setting is also in the boot config |
| 2 | A tenant sees only itself | as A, the process list shows only A's user, and PID 1's command line is not readable |
| 3 | A tenant still sees its own service manager | as A, the user service manager reports `running` or `degraded`, never a connection failure |
| 4 | The system service manager won't list other processes to a tenant | as A, asking the system manager over D-Bus for a service's processes is denied, on every interface that offers the method |
| 5 | No unexpected abstract sockets | the owner's inventory of abstract-socket listeners finishes clean; only the display manager's greeter is allowed |
| 6 | Tenants can't reach each other's network or the mesh daemon's local API | the owner's isolation suite reports 0 failures and no foreign UDP or TCP traffic for every tenant; the mesh daemon's local socket is open only to root and the owner |
| 7 | Login keys are root-owned and source-pinned | each tenant's authorized keys are a root-owned copy, every key line is limited to allowed source addresses, and the SSH server reports agent forwarding, password login and user rc files off for tenants |
| 8 | No path to sudo | each tenant is only in its own group and the tenant group; no tenant is in `sudo`, `adm`, `lxd`, `docker` or `incus-admin`; the owner isn't in `lxd`, `docker` or `incus-admin`; sudo reports tenants not allowed. On Ubuntu, `lxd` means passwordless root once LXD or Incus is installed |
| 9 | Patch floor | the mesh client is at or above the current security bulletin floor, its CLI and daemon versions match, and the kernel has no open security issue of top priority |
| 10 | The message broker is the pinned build | the broker binary's hash matches the pin in the machine record, with one active unit per tenant |
| 11 | Cross-tenant probe fails | as A, for every other tenant B: B's home, runtime folder and keyring are denied, B's processes are invisible, B's browser debug port and session bus can't be reached |
| 12 | It survives a reboot | lines 1 to 11 pass again after a reboot and the boot id changed. If the owner chose a passphrase, report "needs an operator after reboot"; removing it is not the repair |
| 13 | It survives updates | a post-update check runs after every automatic update and every boot; its status says OK and is newer than the last package change |
| 14 | A tenant can be restored | one tenant's newest backup restores into a scratch user with hashes and permissions matching the manifest, and the elapsed time is recorded |

Lines 13 and 14 need tooling the owner may not have yet. Until it exists,
report them NOT VERIFIED and say what is missing.

## Graduation triggers

The next tiers are an unprivileged container per tenant, then a VM per
tenant, then a separate machine. **No recorded trigger, no graduation.** Each
trigger is unlocked only by the evidence in its row, written into the machine
record.

| Observed wall | Evidence to record | Unlocks |
| --- | --- | --- |
| A Checkpoint 1 line can't pass with users alone, and its fix would break a needed service | the failed run plus the security reviewer's ruling | Container per tenant |
| A second cross-tenant leak, through a new class of host-wide path, after Checkpoint 1 | an incident record and a reproduced probe | Container per tenant |
| The post-update check stops on isolation twice in 30 days after vendor updates | the two status records | Container per tenant |
| A tenant needs root, its own system services, Docker, or packages that need root at runtime, a system service or a kernel module | the tenant's written requirement | Container per tenant |
| A tenant runs code nobody reviewed: customer-supplied code, public input that reaches a shell, or a hostile or third-party tenant | the requirement or an incident | VM for that tenant |
| A kernel privilege-escalation issue stays unpatched for more than 7 days | the open issue and the vendor's status | VM for exposed tenants until patched |
| Capacity: available memory stays under 4 GiB at peak on 3 days in a week, a weekly cap or out-of-memory kill, or more tenants than the box was sized for | health-check and usage records | Separate machine (more boxes, not more isolation) |
| A tenant is owned or run by someone other than the machine's owner, or a contract requires segregation | the person or the contract | Separate machine. Neither a container nor a VM protects a tenant from the host's root admin |

When the operator asks "should we move to containers?", look for a recorded
row first. If there is none, the answer is no for now: name the closest
trigger and the evidence that would unlock it.
