---
title: "PRD: mb machine doctor (manifest, check registry, JSON and exit codes)"
status: draft
date: 2026-10-28
release: planned (target v0.7.x, tentative)
linked_issue: https://github.com/dmthepm/mainbranch/issues/1248
---

# PRD: `mb machine doctor`

## Decision asked of reviewers

Approve this shape before any code lands:

1. a **machine manifest** that holds desired-state values only. It follows
   the machine reference pack's schema, minus the parts that would carry
   logic;
2. a **fixed check registry** in `mb` code that uses the pack's check ids,
   where every default check maps to a section of
   [`docs/machine-setup.md`](../machine-setup.md);
3. a **doctor JSON payload and exit codes**: exit precedence `2` > `1` > `3`
   > `0`, where `3` means incomplete, and `attested` is owner evidence that
   never counts as a pass.

Design only. No code ships with this PRD.

Out of scope: `mb machine setup` (only after a first real machine passes
doctor, and only with the maintainer's yes), any fix that runs, isolation
controls (the pack's advanced checks), cross-account IPC and the gate,
cross-account aggregation, Windows.

Platforms: Ubuntu LTS and Omarchy are first-class. macOS gets a small
read-only subset with no manifest.

## Standing rules

From the security rulings for `mb machine`; not open for change here:

- **No shell, no eval.** Doctor never runs a string that came from a
  manifest. Probes are fixed argv lists in check code, run with
  `shell=False`. No templated commands.
- **Fixes are display-only.** Doctor prints the command for the owner to run
  and never runs it.
- **Unverifiable means `not_verified`.** Never `pass`.
- **The admin stays trusted.** Checks don't defend the box against its owner.
  An admin with root can always become any user.
- **Advanced IPC isolation is deferred.** No gate or IPC check in v1.
- **The pack is a design reference.** It is not an executable doctor, and its
  check reads and fix strings are illustrative data. The registry below
  defines the reads. Nothing is copied from the pack's `checks[]` as code.
- **Isolation controls get a homelab-security read** before they ship.

What follows from them:

- Doctor never calls `sudo`, `pkexec`, `doas` or `su`, and never prompts or
  asks for pasted output. A read that needs root is an owner attestation or
  `not_verified` (reason `needs_root`).
- Doctor writes nothing and makes no network calls. Local sockets owned by an
  installed tool (`tailscale`) are reads.
- **Trusted executables only.**
  - Doctor runs only system binaries from a fixed, per-OS allowlist of
    absolute paths (for example `/usr/bin/systemctl`, `/usr/bin/lsblk`,
    `/usr/bin/pacman`, `/usr/bin/pmset`). It never looks a name up on `PATH`.
  - Before running one, doctor resolves symlinks and requires the real file
    and every ancestor directory to be owned by root and not writable by
    group or others. Otherwise the read is `not_verified`, reason
    `untrusted_executable`.
  - It never runs anything from the shared tool tree or from a path that
    comes from a manifest, and never runs a tool to ask its version. Versions
    come from install metadata or the package database.
- **Bounded, confined file reads.**
  - A read resolves the path, then requires the resolved path to stay inside
    the registry's fixed prefix for that read (manifest-supplied paths
    included).
  - Reads open regular files only (no FIFOs, devices or sockets), with
    `O_NOFOLLOW` on the last component, under a byte cap.
  - Permission checks use `lstat`. A symlink where a directory or file is
    expected is `not_verified`, reason `ambiguous_config`.
- **Minimal environment.** Probes get a fixed environment: `LC_ALL=C`,
  `PATH=/usr/bin:/bin`, and for `systemctl --user` only the running user's
  own `XDG_RUNTIME_DIR`. Each probe has a 5 s timeout, and the run has an
  overall timeout. A timed-out probe gives `not_verified`, reason
  `probe_timeout`.
- Each read keeps only named fields under a byte cap. No read needs a secret
  value, and none returns raw command output.
- A manifest value reaches a probe's argv only as one whole element, and only
  after schema validation. It never becomes `argv[0]` or a flag.
- **Escaped display.** Text that came from a manifest (account names, skip
  reasons, attestation notes) is limited to printable characters and 200
  characters, and has control and escape sequences stripped before it
  reaches a terminal. JSON output escapes it as usual.

## Platform detection

| Platform | Signals (all required) | If they disagree |
|---|---|---|
| `ubuntu` | `/etc/os-release` `ID=ubuntu`, `VERSION` contains `LTS` | No `LTS`: `host.os-release` fails |
| `omarchy` | `ID=omarchy` and `pacman -Q omarchy` exits 0 | One signal alone: `unsupported`, reason `ambiguous_platform` |
| `macos` | `platform.system() == "Darwin"`, `sw_vers -productVersion` readable | n/a |
| `unsupported` | anything else | Every check `not_verified`, reason `platform_unsupported` |

On Linux the detected platform must match the manifest's `host.os`. Ubuntu
is `family: ubuntu`. Omarchy is `family: arch, distribution: omarchy`. Do not
detect Omarchy by `~/.local/share/omarchy`: on Omarchy 4 it's a system
package and that folder check gives a false "no".

## Manifest

### Format and schema

JSON, validated against the machine reference pack's schema (JSON Schema
draft 2020-12, `manifest_version: 1`), with the engine deltas below. The pack
names no file location, so this one is a proposal:
`/etc/mainbranch/machine.json`, owned by root, readable by all, writable only
through the admin's `sudo`. Agent accounts read it and can't change it, so an
agent can't weaken its own checks.

- **Default path, trusted.**
  - The file must be a regular file, not a symlink, owned by root and not
    writable by group or others.
  - Every ancestor directory up to `/` must be owned by root and not
    writable by group or others.
  - If any of that fails, `manifest.integrity` fails, no other checks run,
    and the exit code is `1`.
- **`--manifest PATH`, caller-selected.** The manifest is reported as
  `"source": "caller_selected"`. Results are against a policy the caller
  chose, not the machine's. `manifest.integrity` is `not_verified`, reason
  `caller_selected_policy`, so such a run never exits `0`. Use it for
  drafts and fixtures, not as an assurance.

The pack's sections stay as they are: `labels`, `host`, `owner`,
`businesses`, `shared_tools`, `runtime`, `remote_access`, `heavy_work`,
`backups` and `hardening`. They describe the desired state: users, uid
range, home mode, slice sizes, pinned tools, SSH and Tailscale settings, the
heavy-work lock, backup age limits, update model. The pack's two synthetic
examples (Ubuntu, and Omarchy administered from a Mac) are the reference
fixtures, once the deltas are applied.

Parsing: strict, a 256 KB cap, and every `additionalProperties: false` kept.
An unknown key, an invalid value, an unknown check id, or a `size_class` that
names no `size_classes` key is a manifest error (exit `2`, no checks run).

### Engine deltas from the pack schema

| Pack field | Engine rule | Why |
|---|---|---|
| `checks[]` (reads, `selects`, `pass`, `fix`, `title`, `does_not_prove`) | Removed. Replaced by `checks: {skip, attest}` below. | Checks are reviewed code. A manifest supplies values, never logic. |
| `hardening.updates.command` (rolling) | Removed. The registry knows the update command for each distribution (`omarchy update` on Omarchy). | A command in data is one copy-paste from being run. |
| `heavy_work.wrapper` | Narrowed to a bare name, `^[a-z0-9-]+$`, looked up under `<labels.tool_root>/bin`. Doctor checks it with `stat` and never runs it. | It was a free string interpolated into a read. |
| `backups.restore_test.record` | Narrowed to `^/var/lib/[a-z0-9-]+/[a-z0-9._-]+\.json$`. Doctor reads only the date and result fields. | Was a free path. |
| `backups.paths[]`, `backups.schedule`, `shared_tools.tools[].bins[]` | Data only. Compared and displayed, never expanded into a command or glob. | Free strings. |
| `businesses.users[].size_class` | Must name a key in `businesses.size_classes`. | The schema didn't tie them together. |
| `runtime.session_unit` (new, optional) | The user unit that runs each business's multiplexer, `^[A-Za-z0-9@._-]{1,128}\.service$`. Default `herdr.service`. | The schema says one Herdr server per user unit but doesn't name the unit; the guide also allows `tmux`. |

Engine-only `checks` section:

```json
"checks": {
  "skip": [
    {"id": "remote_access.tailscale-serve-named", "reason": "No Serve or Funnel on this box"}
  ],
  "attest": [
    {"id": "host.power-on-after-loss", "read": "bios_power_on", "answer": "yes", "at": "2026-10-28T18:30:00Z"},
    {"id": "backups.restore-tested", "read": "restore_test_attested", "answer": "yes", "at": "2026-10-20T09:00:00Z"}
  ]
}
```

- **`skip`** needs a reason.
  - A skipped check is reported as `skipped` and never counts as passing.
  - Skipping a baseline check that applies to this platform keeps the run
    incomplete (exit `3`).
  - Advanced checks can't be listed: a manifest can never accept or reject
    them.
- **`attest`** is keyed by check id and read name.
  - The registry marks individual reads `attestable`, each with its own
    expiry rule. Attesting a read that isn't attestable is a manifest error
    (exit `2`).
  - `at` is an RFC 3339 UTC timestamp. One in the future is a manifest error.
- **Outcome of an attestable read:**

  | Manifest says | Read outcome |
  |---|---|
  | Nothing for this read | `not_verified`, reason `attestation_missing` |
  | `answer: "no"` | `fail` |
  | `answer: "yes"`, within its expiry | `attested`: recorded owner evidence, shown as NOT VERIFIED (owner attested). Never `pass`. |
  | `answer: "yes"`, past its expiry | `not_verified`, reason `attestation_stale` |
  | `answer: "yes"`, past its expiry, where the attested fact is itself an age (`backups.fresh`, `backups.restore-tested`) | `fail` |

- **Expiry rules**, compared at the precision of `at`:

  | Read | Expires after |
  |---|---|
  | `backups.fresh` | `backups.max_age_hours`, in hours |
  | `backups.restore-tested` | `restore_test.max_age_days` |
  | BIOS power-on | 180 days |
  | Firmware not auto-applied | 180 days |
  | Sudoers reads | 90 days |
  | Off-box LUKS header copy | 365 days |

  No attestation lasts forever.

Nothing from our own machine is in the engine's manifest or fixtures. The
examples use the pack's synthetic names (`box-01`, `admin`, `biz-a-agent`)
and documentation-only addresses.

## Check registry

Each check is `mb` code with a stable id and a registry entry:

- `id`: the pack's id where the pack defines the control; an engine id in the
  same style otherwise;
- `source`: `pack` or `engine`;
- `tier`: `baseline` or `advanced`. Advanced checks are listed, never read,
  and never offer a fix until the registry (not a manifest) accepts them;
- `section`: an anchor in `docs/machine-setup.md`. A check with no section is
  out of the default set;
- `os`: `ubuntu`, `arch` (Omarchy), `macos`;
- `as`: `owner` (run in the admin account), `each-business` (run in each
  agent account, about itself), `owner-attests` (a root-only fact the owner
  confirms in the manifest), or `any` (readable from any account; an engine
  addition);
- `reads`: one or more fixed reads, each with its own outcome. A failed read
  is never hidden by another read that passed;
- `does_not_prove`: what the check can't see, printed with every result;
- `severity`: `fail` or `warn` when a read fails;
- `fix`: display-only argv per OS, with who runs it.

**Scope.** Doctor runs the checks for whoever is running it: `any` checks
plus `owner` checks in the admin account, or `any` plus `each-business`
checks in an agent account. With `--scope all` it also lists the other
role's checks as `not_verified`, reason `other_account`, so nothing silently
disappears. A full picture means running doctor in the admin account and
in each agent account. Combining those runs is a follow-up.

A result always names its scope. Exit `0` means "every applicable baseline
check visible to this account passed", never "the machine is healthy". The
JSON carries `scope` and `run_as`. Human output says, for example, "All
checks visible to `biz-a-agent` passed (scope: self; owner checks not
run)".

Columns: **U** Ubuntu LTS, **O** Omarchy, **M** macOS. `—` means not
applicable on that OS. `att` means an owner attestation. `NV` means always
`not_verified` there.

### Host

| id | Src | Section | U | O | M | As | Reads; verdict |
|---|---|---|---|---|---|---|---|
| `host.os-release` | pack | [part-3-the-operating-system](../machine-setup.md#part-3-the-operating-system) | ✓ | ✓ | NV | any | Platform detection matches `host.os`. Fails on an interim Ubuntu release or a mismatch. On macOS it is `not_verified` (`platform_partial`), because the Linux controls don't apply there. Install-media verification is an install-time step, not a doctor read. |
| `host.no-sleep` | pack | [the-box-works-the-laptop-is-a-remote-control](../machine-setup.md#the-box-works-the-laptop-is-a-remote-control) | ✓ | ✓ | ✓ | any | `systemctl is-enabled` of the sleep, suspend and hibernate targets: pass only if all are `masked`. macOS: `pmset -g` `sleep 0`. |
| `host.power-on-after-loss` | engine | [part-2-picking-a-machine](../machine-setup.md#part-2-picking-a-machine) | att | att | ✓ | owner-attests | Attestable read `bios_power_on` (180 days): BIOS isn't readable from Linux. macOS: `pmset -g` `autorestart 1`, no attestation. Pack: `host.power.after_power_loss`. |
| `host.disk-luks2-tpm` | pack | [ubuntu-lts-recommended-default](../machine-setup.md#ubuntu-lts-recommended-default) | ✓ | — | — | any | `lsblk -J`: a `crypt` device in `/`'s ancestry. `/etc/crypttab`: a `tpm2-device` option matches `host.disk.encryption`. LUKS2 header version: `not_verified` (`needs_root`). Attestable read `header_offbox` (365 days). `does_not_prove`: that the TPM binding covers a verified boot chain (Secure Boot state and PCR policy need root). |
| `host.disk-luks2-tpm-arch` | pack | [omarchy-arch-based](../machine-setup.md#omarchy-arch-based) | — | ✓ | — | any | `lsblk -J` as above, plus `/etc/crypttab.initramfs` or `/proc/cmdline` against `host.disk.encryption`. `luks2-passphrase` with `unattended_boot: false` passes (the pack's Omarchy example). |
| `host.disk-filevault` | engine | [mac-or-linux-for-the-box](../machine-setup.md#mac-or-linux-for-the-box) | — | — | ✓ | any | `fdesetup status` says FileVault is on. |
| `host.desktop-no-autologin` | pack | [omarchy-arch-based](../machine-setup.md#omarchy-arch-based) | ✓ | — | ✓ | any | U: `/etc/gdm3/custom.conf` `AutomaticLoginEnable`. M: `com.apple.loginwindow autoLoginUser` absent. `not_applicable` when `host.desktop.session` is `none` and no display manager is installed. |
| `host.desktop-no-autologin-arch` | pack | [omarchy-arch-based](../machine-setup.md#omarchy-arch-based) | — | ✓ | — | any | `/etc/sddm.conf.d/*.conf` `[Autologin] User=`; `getty@*.service.d/*.conf` with `--autologin`. Fails if any is present. |
| `host.screen-lock` | pack | [omarchy-arch-based](../machine-setup.md#omarchy-arch-based) | ✓ | NV | ✓ | owner | U: the owner's GNOME `lock-enabled` and `idle-delay` are within `host.desktop.screen_lock_minutes`. O: **NOT VERIFIED**: where Omarchy 4 stores its idle-lock setting is unknown. M: the owner's `askForPassword`. |

### Owner and business users

| id | Src | Section | U | O | M | As | Reads; verdict |
|---|---|---|---|---|---|---|---|
| `owner.sudo-needs-password` | pack | [admin-account-and-agent-accounts](../machine-setup.md#admin-account-and-agent-accounts) | ✓+att | ✓+att | — | owner | Read `owner_in_admin_group`: `owner.user` exists and is in `sudo` (U) or `wheel` (O). Attestable read `no_nopasswd` (90 days): sudoers is root-only. |
| `owner.no-sudo-into-business` | pack | [admin-account-and-agent-accounts](../machine-setup.md#admin-account-and-agent-accounts) | att | att | — | owner-attests | Attestable read `no_runas_business` (90 days): sudoers is root-only. `does_not_prove`: root can still become any user (the admin stays trusted). |
| `businesses.users-and-homes` | pack | [one-user-account-per-business](../machine-setup.md#one-user-account-per-business) | ✓ | ✓ | — | any + each-business | any: each user exists with its declared uid, inside `uid_range`; its home `stat` is `0700` and owned by it. each-business: umask `077`; no other business's home is listable. |
| `businesses.no-privileged-groups` | pack | [admin-account-and-agent-accounts](../machine-setup.md#admin-account-and-agent-accounts) | ✓ | ✓ | — | any | Group lists: no business user in `sudo`, `adm`, `wheel`, `docker`, `lxd` or the owner's group. `does_not_prove`: a sudoers user rule (root-only). |
| `businesses.private-tmpdir` | pack | [shared-tools-private-data](../machine-setup.md#shared-tools-private-data) | ✓ | ✓ | — | each-business | `$TMPDIR` is set, owned by the user, mode `0700`. |
| `businesses.slice-limits` | pack | [sessions-that-survive-a-reboot](../machine-setup.md#sessions-that-survive-a-reboot) | ✓ | ✓ | — | any | `systemctl show user-<uid>.slice` `MemoryHigh`, `MemoryMax`, `TasksMax` against the user's size class. `warn` if `/proc/meminfo` total differs from `sizing_basis.host_ram_gb` by more than 10%. |

### Sessions and runtime

| id | Src | Section | U | O | M | As | Reads; verdict |
|---|---|---|---|---|---|---|---|
| `sessions.linger` | engine | [sessions-that-survive-a-reboot](../machine-setup.md#sessions-that-survive-a-reboot) | ✓ | ✓ | — | any | `/var/lib/systemd/linger/<user>` exists for each business user. |
| `runtime.herdr-per-user` | pack | [sessions-that-survive-a-reboot](../machine-setup.md#sessions-that-survive-a-reboot) | ✓ | ✓ | — | each-business | `systemctl --user` `is-enabled` and `is-active` for `runtime.session_unit`. Its `Slice` is not `app.slice`. |
| `sessions.started-without-login` | engine | [part-4-first-week](../machine-setup.md#part-4-first-week) | ✓ | ✓ | — | each-business | The unit's `ActiveEnterTimestamp` is before the user's first login session this boot. `warn` otherwise: the reboot test hasn't been passed. |
| `runtime.claude-autoupdate-off` | pack | [backups-and-updates](../machine-setup.md#backups-and-updates) | ✓ | ✓ | — | each-business | The session unit's `Environment` has `DISABLE_AUTOUPDATER=1`. Only that key is kept from the read. |
| `credentials.store-available` | engine | [credentials](../machine-setup.md#credentials) | ✓ | ✓ | ✓ | each-business | Reuses `mb connect`'s existing credential-store probe ([`connect.md`](../connect.md)). Fails if no store works without a desktop session. |

### Shared tools and heavy work

| id | Src | Section | U | O | M | As | Reads; verdict |
|---|---|---|---|---|---|---|---|
| `shared_tools.root-owned-readonly` | pack | [shared-tools-private-data](../machine-setup.md#shared-tools-private-data) | ✓ | ✓ | — | any | `stat` of `labels.tool_root`, its `bin`, and each declared bin: owner `root:root`, no group or other write. |
| `shared_tools.pins-match` | pack | [shared-tools-private-data](../machine-setup.md#shared-tools-private-data) | ✓ | ✓ | — | any | The pinned version's install directory exists under `tool_root`, and no `latest` alias is in use. `does_not_prove`: tarball checksums (not recomputed). |
| `shared_tools.path-order` | pack | [shared-tools-private-data](../machine-setup.md#shared-tools-private-data) | ✓ | ✓ | — | each-business | The first `PATH` entry is under `tool_root`. `does_not_prove`: the PATH of services that weren't started from this shell. |
| `heavy_work.lock` | pack | [one-heavy-job-at-a-time](../machine-setup.md#one-heavy-job-at-a-time) | ✓ | ✓ | — | any + each-business | any: `stat` of `<run_dir>/<lock_name>` is `0660`, group `shared_group`. each-business: `$<env_var>` names that path. |
| `heavy_work.capped-run` | pack | [one-heavy-job-at-a-time](../machine-setup.md#one-heavy-job-at-a-time) | ✓ | ✓ | — | any | The wrapper exists under `tool_root/bin` and is root-owned and read-only. Whether it refuses an uncapped job: `not_verified`, because doctor never runs it. |

### Backups

| id | Src | Section | U | O | M | As | Reads; verdict |
|---|---|---|---|---|---|---|---|
| `backups.fresh` | pack | [backups-and-updates](../machine-setup.md#backups-and-updates) | att | att | — | owner-attests | Attestable read `last_backup` (`max_age_hours`): the backup host is off the box. Stale means `fail`. |
| `backups.restore-tested` | pack | [backups-and-updates](../machine-setup.md#backups-and-updates) | ✓/att | ✓/att | — | owner | Read `restore_test_record`: `restore_test.record` (date and result only) if readable. Otherwise attestable read `restore_test_attested` (`max_age_days`). Stale means `fail`. |

### Remote access

| id | Src | Section | U | O | M | As | Reads; verdict |
|---|---|---|---|---|---|---|---|
| `remote_access.sshd-keys-only` | pack | [managing-it-from-a-mac](../machine-setup.md#managing-it-from-a-mac) | ✓ | ✓ | ✓ | any | `sshd_config` and `sshd_config.d/*.conf`: password and keyboard-interactive off, pubkey on. `Match` blocks or an outside `Include`: `not_verified` (`ambiguous_config`). `sshd -T` needs root and isn't used. |
| `remote_access.tailscale-version` | pack | [managing-it-from-a-mac](../machine-setup.md#managing-it-from-a-mac) | ✓ | ✓ | NV | any | Version from the package database, not by running Tailscale (`dpkg-query -W tailscale` on U, `pacman -Q tailscale` on O), at least `min_version`. `tailscale status --json` (allowlisted system binary) `BackendState` is `Running`. A missing package or denied socket: `not_verified`. |
| `remote_access.tailscale-no-ssh` | pack | [managing-it-from-a-mac](../machine-setup.md#managing-it-from-a-mac) | ✓ | ✓ | — | any | Tailscale prefs `RunSSH` is false. Denied: `not_verified`. |
| `remote_access.tailscale-serve-named` | pack | [managing-it-from-a-mac](../machine-setup.md#managing-it-from-a-mac) | ✓ | ✓ | — | any | `tailscale serve status --json` ports are within `serve_ports`, and Funnel is off. Denied: `not_verified`. |
| `remote_access.offbox-listeners` | pack | [managing-it-from-a-mac](../machine-setup.md#managing-it-from-a-mac) | ✓ | ✓ | — | any | `/proc/net/tcp` and `tcp6` (uid column, no root): no listener off loopback except sshd's port and tailscaled. |

### Hardening and updates

| id | Src | Section | U | O | M | As | Reads; verdict |
|---|---|---|---|---|---|---|---|
| `hardening.firewall-default-deny` | pack | [managing-it-from-a-mac](../machine-setup.md#managing-it-from-a-mac) | ✓ | ✓ | — | any | ufw: `/etc/ufw/ufw.conf` `ENABLED=yes`, and `/etc/default/ufw` input policy `DROP`. `does_not_prove`: the live ruleset and the SSH source list (root-only). Other `firewall.tool` values: `not_verified`. |
| `hardening.unattended-security-only` | pack | [backups-and-updates](../machine-setup.md#backups-and-updates) | ✓ | — | ✓ | any | U: the package is installed, `Unattended-Upgrade "1"`, the origins are security only, `Automatic-Reboot "false"`, and `apt-daily-upgrade.timer` is enabled. M: `CriticalUpdateInstall`. |
| `hardening.update-snapshot` | pack | [omarchy-arch-based](../machine-setup.md#omarchy-arch-based) | — | ✓ | — | any | The last full upgrade in `/var/log/pacman.log` is within `cadence_days`. Snapshot presence: `not_verified` if `snapper` needs root. The fix shown is `omarchy update`. |
| `hardening.aur-reviewed` | pack | [omarchy-arch-based](../machine-setup.md#omarchy-arch-based) | — | ✓ | — | any | `pacman -Qm` (foreign packages) is a subset of `aur_packages_reviewed`. |
| `hardening.reboot-pending` | pack | [backups-and-updates](../machine-setup.md#backups-and-updates) | ✓ | — | — | any | `/var/run/reboot-required`. `warn`. |
| `hardening.reboot-pending-arch` | pack | [omarchy-arch-based](../machine-setup.md#omarchy-arch-based) | — | ✓ | — | any | `/usr/lib/modules/$(uname -r)` is missing. `warn`. `does_not_prove`: a systemd or glibc update since boot. |
| `hardening.firmware-manual` | pack | [backups-and-updates](../machine-setup.md#backups-and-updates) | att | att | — | owner-attests | Attestable read `no_auto_firmware` (180 days). |
| `manifest.integrity` | engine | [admin-account-and-agent-accounts](../machine-setup.md#admin-account-and-agent-accounts) | ✓ | ✓ | — | any | Default path: a regular file, not a symlink, root-owned, with every ancestor root-owned and not writable by group or others; it fails otherwise. `--manifest`: `not_verified`, reason `caller_selected_policy`. No manifest: `not_verified`, reason `no_manifest`, and only checks that need no manifest values run. |

### Not in the default set

- **Pack checks with no guide section yet:** `host.disk-free` and
  `hardening.no-failed-units`. They're accepted designs, and they join the
  default set once `docs/machine-setup.md` covers them (follow-up).
- **Advanced, listed but never run:** `hardening.landlock-agent-shell`,
  `hardening.nft-egress-fence`, `hardening.proc-hidepid`,
  `hardening.apparmor-bwrap`. These are isolation controls: a
  homelab-security read comes before any of them is accepted.
- **No check:** the gate and cross-account IPC (`hardening.ipc_isolation:
  separate-platform-review`). This is deferred by the rulings.

### Reconciled from the first draft

The first draft reserved five ids. Four map to the pack:

- `heavy.single_lock` became `heavy_work.lock` and `heavy_work.capped-run`.
- `sessions.own_slice` became `businesses.slice-limits` and the slice read in
  `runtime.herdr-per-user`.
- `tools.shared_readonly` became `shared_tools.root-owned-readonly`,
  `shared_tools.pins-match` and `shared_tools.path-order`.
- `backups.home_backup` became `backups.fresh` and `backups.restore-tested`.

The fifth, `gate.present`, stays out: the pack defines no gate check, and
the rulings defer it.

Other first-draft ids now use the pack's names or were folded in:

- `os.supported` → `host.os-release`
- `disk.encrypted` → `host.disk-luks2-tpm*`
- `login.autologin_locked` → `host.desktop-no-autologin*` and
  `host.screen-lock`
- `accounts.*` → `owner.*` and `businesses.*`
- `remote.*` → `remote_access.*`
- `updates.*` → `hardening.*`
- `tools.present` and `updates.mainbranch_current` → `shared_tools.pins-match`
- `hardware.memory_min` → `businesses.slice-limits`

`security.apparmor` and `security.landlock` were dropped: the pack treats
AppArmor and Landlock only as advanced controls.

## Doctor output

### Command

```bash
mb machine doctor [--manifest PATH] [--scope self|all] [--json]
```

Human output groups results by guide section. For each result it prints the
check, then `does_not_prove` when the check can't see everything, then the
quoted fix and who runs it. `--json` prints only the payload below.

### JSON

The payload uses the shared envelope from
[`json-output-contract.md`](../json-output-contract.md), with
`result_schema.name = "mainbranch.machine.doctor.result"` and
`mb_command = "mb machine doctor"`. The domain fields are
`schema: "mb.machine.doctor"` and `schema_version: 1`.

```json
{
  "result_envelope_version": "1.0",
  "result_schema": {"name": "mainbranch.machine.doctor.result", "version": "1.0"},
  "mb_command": "mb machine doctor",
  "ok": false,
  "result_status": "ok",
  "errors": [],
  "warnings": [],
  "actions": [],

  "schema": "mb.machine.doctor",
  "schema_version": 1,
  "safe_to_share": false,
  "exit_code": 3,
  "platform": {"id": "omarchy", "family": "arch", "signals": {"os_release_id": "omarchy", "pacman_package": true}},
  "run_as": {"account": "biz-a-agent", "role": "each-business"},
  "scope": "self",
  "manifest": {"source": "default_path", "sha256": "<hex>", "manifest_version": 1},
  "summary": {"pass": 12, "fail": 0, "warn": 1, "not_verified": 2, "attested": 0, "skipped": 4, "not_applicable": 0},
  "checks": [
    {
      "id": "heavy_work.lock",
      "source": "pack",
      "tier": "baseline",
      "as": "each-business",
      "section": "docs/machine-setup.md#one-heavy-job-at-a-time",
      "subject": "biz-a-agent",
      "state": "pass",
      "severity": "fail",
      "reads": [
        {"name": "lock_mode_and_group", "state": "pass", "observed": {"mode": "0660", "group_matches": true}},
        {"name": "env_var_names_lock", "state": "pass", "observed": {"set": true, "matches": true}}
      ],
      "reason": null,
      "does_not_prove": "That every heavy job actually takes the lock.",
      "fix": null
    },
    {
      "id": "host.screen-lock",
      "source": "pack",
      "tier": "baseline",
      "as": "owner",
      "section": "docs/machine-setup.md#omarchy-arch-based",
      "subject": "admin",
      "state": "not_verified",
      "severity": "fail",
      "reads": [{"name": "idle_lock_setting", "state": "not_verified", "observed": {}}],
      "reason": "location_unknown",
      "does_not_prove": "Omarchy 4's idle-lock setting location is not yet confirmed.",
      "fix": {"display_only": true, "run_as": "owner", "argv": null, "text": "Turn on the idle lock in Omarchy's settings."}
    },
    {
      "id": "hardening.nft-egress-fence",
      "source": "pack",
      "tier": "advanced",
      "state": "skipped",
      "reason": "advanced_pending",
      "reads": [],
      "fix": null
    }
  ]
}
```

The third result is trimmed to the fields that differ. The second shows the
`host.screen-lock` result as it would look in an owner run.

Field rules:

- `state` is one of `pass`, `fail`, `warn`, `not_verified`, `attested`,
  `skipped`, `not_applicable`. `severity` is what a failure would be.
- A check with several reads takes the worst read, in this order: `fail`,
  `not_verified`, `attested`, `warn`, `pass`. Every read keeps its own
  outcome in `reads`, so an attested read never turns into a pass, and a
  passing read never hides a failed one.
- `attested` is displayed as "NOT VERIFIED (owner attested)" with the
  attestation time. In JSON and in `summary` it stays separate from both
  `pass` and `not_verified`.
- `reason` is set for every state except `pass` and `fail`, from a fixed
  enum: `needs_root`, `platform_unsupported`, `platform_partial`,
  `ambiguous_platform`, `ambiguous_config`, `probe_missing`,
  `probe_timeout`, `probe_error`, `untrusted_executable`, `owner_attested`,
  `attestation_missing`, `attestation_stale`, `other_account`, `no_manifest`,
  `caller_selected_policy`, `skipped_by_manifest`, `advanced_pending`,
  `no_section`, `location_unknown`. Reasons are never free text, so no stray paths or
  output leak.
- `observed` holds only the parsed fields that a read selects: booleans,
  numbers, enums, modes. Never raw output, file contents, environment values
  other than the one named key, or paths outside the registry's fixed
  prefixes.
- Every result includes the registry's `does_not_prove` text when it has one.
- `fix.display_only` is always `true`. `fix.argv` is a list, or `null` for
  manual steps. Root steps are shown as the owner would type them. Doctor
  never runs them.
- `safe_to_share` is `false` because account names appear. A scrubbed share
  mode is a follow-up.
- A manifest error returns the same envelope with `ok: false`,
  `result_status: "error"`, `exit_code: 2`, empty `checks`, and coded
  `errors` such as `{"code": "manifest.schema", "pointer": "/businesses/users/0/user"}`.
  No traceback and no file contents.

### Exit codes

Exit codes follow a fixed precedence: `2`, then `1`, then `3`, then `0`.
The first that applies wins.

| Code | Meaning | `ok` |
|---|---|---|
| `2` | Error: usage error, invalid or unreadable manifest, or internal error. No verdict. | `false` |
| `1` | Failure: at least one `fail`. | `false` |
| `3` | Incomplete: no `fail`, but at least one applicable baseline check is `not_verified`, `attested` or `skipped`. | `false` |
| `0` | Every applicable baseline check in this run's scope passed. `warn` is allowed. | `true` |

Exit meanings are specific to each command. Here, `3` means the run was
incomplete, the difference between "failed" and "couldn't fully verify".
Security approved it on 28 Oct 2026.

These don't block exit `0`:

- `not_applicable` checks (another OS, or a desktop check when there is no
  desktop);
- advanced checks, which are outside the accepted baseline and never run.

`attested` is recorded owner evidence, never a pass. It is shown as NOT
VERIFIED (owner attested), counted on its own, and keeps the run at exit `3`.
It follows the pack's `owner-attests` checks, with one difference: the
answer lives in the root-owned manifest, because doctor writes nothing.

So in practice, a Linux box with any owner-attested baseline fact (BIOS
power-on, sudoers, an off-box backup) exits `3`, never `0`. That's
deliberate: the owner sees which facts rest on their word. A consumer
that wants "nothing failed" checks for exit codes `0` and `3`.

Expected today: every Linux box exits `3` because of its attested reads.
Omarchy boxes also have `host.screen-lock` NOT VERIFIED. macOS always exits
`3` (`host.os-release` is `platform_partial`).

## Validation plan for the code batch

- Registry test:
  - every id is unique;
  - every default check's `section` anchor exists in
    `docs/machine-setup.md`;
  - every `owner-attests` check has fix text;
  - advanced checks have no reads and no fix;
  - every pack id used appears in the pack's `generic-controls.md`.
- Schema test: the engine schema is the pack schema with the listed deltas.
  Both synthetic examples, with deltas applied, validate. Each delta has a
  rejecting case: a command field, a wrapper path, a record path outside its
  prefix, an unknown `size_class`.
- Static test:
  - no `shell=True` in machine-doctor code;
  - no `sudo`, `pkexec`, `doas` or `su` in any probe argv;
  - no probe runs a path that comes from a manifest;
  - every executable is an absolute path on the per-OS allowlist.
- Trust tests:
  - a user-writable binary placed earlier on `PATH` is never run;
  - an allowlisted path whose real file, or an ancestor directory, is
    group- or other-writable gives `untrusted_executable`;
  - a `restore_test.record` symlinked outside its prefix is refused;
  - a FIFO is never opened;
  - a manifest account name or note containing escape sequences prints
    inert.
- Exit and attestation tests:
  - precedence `2` > `1` > `3` > `0`;
  - an attested, skipped or `not_verified` applicable baseline check never
    gives `0`;
  - an attestation that is missing, in the future, stale or "no" gives the
    outcome in the attestation table;
  - attesting a read that isn't attestable is a manifest error;
  - `--manifest` never gives `0`;
  - an untrusted default manifest fails with no other checks run.
- Fixture tests per platform, from synthetic `os-release`, `lsblk`,
  `/proc/net/tcp`, `sshd_config`, `pacman.log` and `pmset` samples.
- Real runs:
  - Ubuntu LTS and Omarchy boxes, in the admin account and in one agent
    account each;
  - macOS once, if a Mac is available;
  - JSON and exit codes recorded in the PR.

## Open questions

1. Exit `3` (approved) and `attested` (accepted only as non-passing
   evidence): applied as ruled in the security review of 28 Oct 2026.
2. `/etc/mainbranch/machine.json` as the default location: a proposal. The
   pack names none.
3. Where does Omarchy 4 keep its idle-lock setting? `host.screen-lock` is
   NOT VERIFIED on Omarchy until it's confirmed.
4. The v0-7 target in this file name is tentative.

Next: security re-reviews this revision; then the code batch on #1248.
