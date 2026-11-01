# Setup: hardware, operating system, first week

Guide sections this follows (read them for the reasoning; don't restate them
to the owner at length):
[Concepts](https://github.com/dmthepm/mainbranch/blob/main/docs/machine-setup.md#part-1-concepts),
[Picking a machine](https://github.com/dmthepm/mainbranch/blob/main/docs/machine-setup.md#part-2-picking-a-machine),
[The operating system](https://github.com/dmthepm/mainbranch/blob/main/docs/machine-setup.md#part-3-the-operating-system),
[First week](https://github.com/dmthepm/mainbranch/blob/main/docs/machine-setup.md#part-4-first-week).

Placeholders: `<agent-user>` is one business's agent account, `<unit>` is its
multiplexer's user service, `<backup mount>` is the local backup drive's mount
point. Every done-check is read-only. Where a check needs root or physical
access, the result is NOT VERIFIED until the owner reports it.

## 1. Pick the hardware

Ask how many businesses will run, whether the owner already lives on Apple,
and the budget. Then use the guide's table in
[Picking a machine](https://github.com/dmthepm/mainbranch/blob/main/docs/machine-setup.md#part-2-picking-a-machine)
and its
[Mac or Linux](https://github.com/dmthepm/mainbranch/blob/main/docs/machine-setup.md#mac-or-linux-for-the-box)
comparison. Prices there are dated: tell the owner to check before buying.

- RAM first (32 GB is comfortable for several businesses), a fast SSD, and a
  BIOS setting that powers on after an outage.
- For backups, plan the three layers in
  [Backup storage](https://github.com/dmthepm/mainbranch/blob/main/docs/machine-setup.md#backup-storage)
  before buying a drive.

**Done-check:** the owner has a written pick with RAM, disk and backup drive.
Power-on after outage is NOT VERIFIED (owner attested) until the owner confirms
the BIOS setting; you can't read it.

## 2. Pick the operating system

| Choice | When | Read |
| --- | --- | --- |
| Ubuntu LTS (default) | Most owners; automatic security updates | [Ubuntu LTS](https://github.com/dmthepm/mainbranch/blob/main/docs/machine-setup.md#ubuntu-lts-recommended-default) |
| Omarchy | The owner wants Arch and will run weekly updates | [Omarchy](https://github.com/dmthepm/mainbranch/blob/main/docs/machine-setup.md#omarchy-arch-based) |
| macOS (Mac mini) | One business, owner already on Apple | [Mac or Linux](https://github.com/dmthepm/mainbranch/blob/main/docs/machine-setup.md#mac-or-linux-for-the-box) |

Requirements on every OS:

- Full-disk encryption, with the unlock trade-off chosen on purpose
  (passphrase, or TPM unlock only with a verified boot chain). The recovery
  key is in the owner's password manager and was read back from a second
  device.
- Ubuntu: security updates install automatically; the box never reboots
  itself.
- Omarchy: auto-login off and the idle lock on. Updates go through Omarchy's
  own updater, about weekly.
- Omarchy, and any desktop where a password, token or key is ever copied:
  clipboard history is off completely. Keep it only on a machine that never
  handles secrets.

**Done-checks:**

- OS identified: `/etc/os-release` shows `ID=ubuntu` or `ID=omarchy` (on
  Omarchy, `pacman -Q omarchy` also lists the package).
- Ubuntu automatic reboot is off: `apt-config dump` shows
  `Unattended-Upgrade::Automatic-Reboot "false"` or no such line (the default
  is off).
- Disk encryption: `findmnt -no SOURCE /` names root's device, and
  `lsblk -s -o NAME,TYPE <device>` shows a `crypt` entry in that device's chain. A
  crypt device elsewhere does not count. Unlock method and recovery-key readback are NOT VERIFIED (owner
  attested).
- Clipboard history: no clipboard-history service or process runs for the
  desktop user, and the desktop's autostart config doesn't start one. Read
  service and process names only. Never open, list or copy the history store
  (on Omarchy, anything under `~/.local/state/omarchy/clipboard*`). If you
  can't tell without opening it, report NOT VERIFIED and ask the owner to
  check the setting.

## 3. First week

Walk the guide's
[First week](https://github.com/dmthepm/mainbranch/blob/main/docs/machine-setup.md#part-4-first-week)
in order. Prepare each command in a terminal pane; the owner reads it and
presses Enter. Root steps run from the admin account. Don't skip ahead: the
reboot test proves the earlier steps.

| Step | Requirement | Done-check (read-only) |
| --- | --- | --- |
| Accounts | One admin account with `sudo`; one agent account per business, none with `sudo` | `id <agent-user>` lists no `sudo`, `adm`, `docker`, `lxd` or `incus-admin` group |
| Private homes | Only the owner of each home and temporary folder can open it | `stat -c '%a %U' /home/<agent-user>` shows `700`, or `750` with a group only that user is in, and the right owner. That proves the mode only: also check ACLs with `getfacl`, the group's members, and that no parent folder is writable by others. Anything unchecked is NOT VERIFIED |
| Remote access | SSH by key only, over a private network; inbound connections denied by default | `ss -Htln` lists no dev server or debug port on a non-loopback address. The inbound rule set is NOT VERIFIED (owner attested): its commands are the owner's, not this skill's |
| Shared tools | Installed once, root-owned, pinned to exact versions, first on PATH | `stat -c '%U %a'` on the tool tree shows `root` and no group or other write bit, with ACLs and parent folders also checked, or it is NOT VERIFIED; each tool in the index runs (see step 4) |
| Sessions | Linger on, multiplexer as a user service | `loginctl show-user <agent-user> -p Linger` shows `Linger=yes`; as that account, `systemctl --user is-active <unit>` shows `active` |
| Reboot test | Every account's multiplexer is back with nobody logged in | the owner reboots; then `uptime -s` is newer than the reboot request and every `<unit>` is `active` |
| Lid-closed test | Work keeps running with the laptop closed for 30 minutes | the capped test run's log ends with its finish line, timestamped after the laptop closed |
| Key roll | One practice roll with a fake key | NOT VERIFIED (owner attested) with the date |
| Backups | Three layers set up; one restore test passed before business data | the machine record has a dated restore drill for each layer; `findmnt <backup mount>` shows the drive mounted, and `/etc/fstab` mounts it by `UUID=` |

## 4. New host or cutover

Moving to a new box fails most often through tools and configs that never got
installed. Before calling a new host done:

- Copy the tool index from the old machine record. Every listed tool exists
  on the new host and `<tool> --help` exits 0 for every account that uses it.
- Every agent in the restart table has its checkpoint file on the new host
  and resumed its session from it.
- Collectors and scheduled jobs from the old host are either running on the
  new host (their source-health record shows a success since cutover) or
  listed as retired.

**Done-check:** a table of every tool, agent and collector with PASS, FAIL or
NOT VERIFIED. A tool you couldn't run is a FAIL, not a skip.
