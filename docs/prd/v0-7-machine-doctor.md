---
title: "PRD: mb machine doctor (manifest, check registry, JSON and exit codes)"
status: draft
date: 2026-10-28
release: planned (target v0.7.x, not decided)
linked_issue: none yet
---

# PRD: `mb machine doctor`

## Decision asked of reviewers

Approve this shape before any code lands:

1. a **machine manifest** that only selects check ids and typed parameters;
2. a **fixed check registry** in `mb` code, where every check maps to a section
   of [`docs/machine-setup.md`](../machine-setup.md);
3. a **doctor JSON payload and exit codes**, including `not_verified` as its
   own exit code.

Design only. No code ships with this PRD.

Out of scope: `mb machine setup` (only after a first real machine passes
doctor, and only with the maintainer's yes), any fix that runs, any
isolation control (per-user firewall rules, Landlock policies, a local API),
cross-account aggregation, Windows.

Platforms: Ubuntu LTS and Omarchy are first-class. macOS gets read-only checks
where a probe is cheap and needs no admin rights; everything else reports
`not_verified` on macOS.

## Standing rules

These come from the security review for `mb machine` and are not open for
change in this PRD:

- **No shell, no eval.** Doctor never runs a string that came from a
  manifest. Probes are fixed argv lists in check code, run with
  `shell=False`. No templated commands.
- **Fixes are display-only.** Doctor prints the command for the owner to run
  and never runs it.
- **Unverifiable means `not_verified`.** A check that could not be verified on
  this machine never reports `pass`.

What follows from them:

- Doctor never calls `sudo`, `pkexec`, `doas` or `su`, and never prompts. A
  probe that needs root reports `not_verified` with reason `needs_root`.
- Doctor writes nothing: no files, caches, receipts or logs. It makes no
  network calls. Local sockets owned by an installed tool (for example
  `tailscale status`) are reads, not network calls.
- A manifest parameter may reach a probe's argv only as one whole element,
  and only after it passes that check's typed validator (for example a POSIX
  account name pattern). It never becomes `argv[0]`, a flag, or part of a
  path outside a fixed, check-owned prefix.
- Probes run with `LC_ALL=C`, a per-probe timeout (5 s default) and an
  overall timeout. A timed-out probe reports `not_verified`, reason
  `probe_timeout`.
- Displayed fix commands are rendered from argv with shell quoting, so a
  parameter can't turn a copied command into something else.

## Platform detection

Detection runs first and decides which probes apply. It reads files and
runs fixed commands only.

| Platform id | Signals (all required) | If signals disagree |
|---|---|---|
| `ubuntu` | `/etc/os-release` `ID=ubuntu`; `VERSION` contains `LTS` | `ID=ubuntu` without `LTS`: platform `ubuntu`, check `os.supported` fails (interim releases are not supported) |
| `omarchy` | `/etc/os-release` `ID=omarchy`; `pacman -Q omarchy` exits 0 | Either signal alone: platform `unsupported`, reason `ambiguous_platform` |
| `macos` | `platform.system() == "Darwin"`; `sw_vers -productVersion` readable | n/a |
| `unsupported` | anything else | Every check reports `not_verified`, reason `platform_unsupported` |

Do not detect Omarchy by `~/.local/share/omarchy`. On Omarchy 4 it is a
system package under `/usr/share/omarchy`, so the home-folder check gives a
false "no".

## Manifest

### Where it lives

- `--manifest PATH` wins.
- Otherwise `/etc/mainbranch/machine.yaml` on Linux and macOS.
- No manifest: doctor runs the platform's default check set with default
  parameters. Checks that need account names report `not_applicable`, reason
  `no_manifest`.

The manifest belongs to the admin account. Agent accounts read it and must
not be able to change it, so an agent can't weaken its own checks. Check
`manifest.integrity` fails when the running account can write the file or
its directory.

### Parsing

- YAML `safe_load` only, 64 KB cap, UTF-8.
- Strict schema: an unknown key, an unknown check id, or a parameter that
  fails its validator is a manifest error (exit `2`, no checks run).
- The manifest carries no commands, scripts, globs, URLs or templates. It
  carries account names, unit names, numbers, booleans, enums and dates.

### Shape (v1)

The example is synthetic. Account names are placeholders.

```yaml
schema: mb.machine.manifest
schema_version: 1

machine:
  role: always_on            # always_on | workstation
  platforms: [ubuntu, omarchy]   # platforms this manifest was written for

accounts:
  admin: boxadmin
  agents:
    - name: acme-agent
      multiplexer_unit: tmux-agent.service
    - name: northwind-agent
      multiplexer_unit: herdr.service

checks:
  set: default               # default | none (none = only the ids listed in `add`)
  add: []                    # opt-in ids not in the default set
  params:
    hardware.memory_min: {min_gb: 32}
    updates.omarchy_recent: {max_age_days: 14}
  skip:
    - id: remote.tailscale_up
      reason: "Reached through a site VPN instead"
  attest:
    - id: power.on_after_outage
      date: 2026-10-28
      note: "BIOS: After Power Loss set to Power On"
```

Field rules:

- `machine.role` changes severity, not which checks run. On `always_on`,
  sleep and auto-login without a lock are `fail`; on `workstation` they are
  `warn`.
- `machine.platforms` that doesn't include the detected platform is a
  `warn` on `manifest.integrity`, not an error.
- `accounts.*.name`: `^[a-z_][a-z0-9_-]{0,31}$`.
- `multiplexer_unit`: `^[A-Za-z0-9@._-]{1,128}\.service$`.
- `skip` needs a non-empty `reason`. Skipped checks appear in the output with
  state `skipped` and the reason. They are never counted as passing.
- `attest` is accepted only for checks the registry marks `manual_only`
  (nothing on the machine can read them, such as BIOS settings). An attested
  check reports state `attested`, never `pass`. Attesting any other check is
  a manifest error.
- No severity overrides in v1. Severity is part of the reviewed registry.

PENDING (homelab pack): homelab's manifest schema and synthetic examples
haven't arrived. This shape is the engine's proposal. Reconcile the two before
code lands, and replace the example above with homelab's synthetic one if it
fits.

## Check registry

Each check is `mb` code with a stable id, registered once. A registry entry
holds:

- `id`, `title`;
- `section`: an anchor in `docs/machine-setup.md` (a test asserts every
  anchor exists);
- `platforms`: which of `ubuntu`, `omarchy`, `macos` have a probe;
- `scope`: `machine` (readable from any account, may report one result per
  declared account) or `self` (verifiable only for the account running
  doctor);
- `severity`: what a failure means (`fail` or `warn`, by role where noted);
- `manual_only`: true when no probe can read it;
- `default`: whether it is in the default set;
- `params`: a typed schema with defaults;
- `fix`: a display-only argv per platform, and who runs it (`admin`,
  `this_account`, or `owner_at_machine` for BIOS and hardware).

`self` checks run only for the account running doctor. With
`--scope all`, doctor also lists them for every other declared account as
`not_verified`, reason `other_account`, so nothing is silently missing. The
default scope leaves them out. A full machine picture means running doctor
in each account. Aggregating those runs is a follow-up and goes through the
gate (PENDING).

Platform column: **U** Ubuntu LTS, **O** Omarchy, **M** macOS (read-only).
A dash means the check reports `not_applicable` on that platform. `nv` means
it always reports `not_verified` there.

### Platform and manifest

| id | Section | U | O | M | Scope | What it reads; when it fails |
|---|---|---|---|---|---|---|
| `os.supported` | [mac-or-linux-for-the-box](../machine-setup.md#mac-or-linux-for-the-box) | ✓ | ✓ | ✓ | machine | Platform detection above. Fails on an Ubuntu interim release; `not_verified` on `unsupported`. |
| `manifest.integrity` | [admin-account-and-agent-accounts](../machine-setup.md#admin-account-and-agent-accounts) | ✓ | ✓ | ✓ | self | `stat` of the manifest and its directory. Fails if the running account can write either. |

### Accounts

| id | Section | U | O | M | Scope | What it reads; when it fails |
|---|---|---|---|---|---|---|
| `accounts.agents_exist` | [one-user-account-per-business](../machine-setup.md#one-user-account-per-business) | ✓ | ✓ | ✓ | machine | `pwd.getpwnam` per declared agent. Fails if one is missing. |
| `accounts.home_private` | [one-user-account-per-business](../machine-setup.md#one-user-account-per-business) | ✓ | ✓ | ✓ | machine | `stat` of each agent's home. Fails on any world bit, or group bits for a group with other members. |
| `accounts.no_cross_home_read` | [accounts-talk-through-a-gate-not-shared-folders](../machine-setup.md#accounts-talk-through-a-gate-not-shared-folders) | ✓ | ✓ | ✓ | self | `os.access` from the running agent account to every other agent home. Fails if any is listable. |
| `accounts.agent_no_sudo` | [admin-account-and-agent-accounts](../machine-setup.md#admin-account-and-agent-accounts) | ✓ | ✓ | ✓ | machine | Group membership: `sudo`/`admin` (U), `wheel` (O), `admin` (M). Fails if an agent is in one. If not in one, `not_verified` (reason `needs_root`), because sudoers drop-ins are unreadable without root. |
| `accounts.admin_present` | [admin-account-and-agent-accounts](../machine-setup.md#admin-account-and-agent-accounts) | ✓ | ✓ | ✓ | machine | Declared admin exists and is in the platform's admin group. `warn` if not. |

### Sessions

| id | Section | U | O | M | Scope | What it reads; when it fails |
|---|---|---|---|---|---|---|
| `sessions.linger` | [sessions-that-survive-a-reboot](../machine-setup.md#sessions-that-survive-a-reboot) | ✓ | ✓ | nv | machine | Existence of `/var/lib/systemd/linger/<name>` per agent. Fails if missing. |
| `sessions.multiplexer_service` | [sessions-that-survive-a-reboot](../machine-setup.md#sessions-that-survive-a-reboot) | ✓ | ✓ | nv | self | `systemctl --user is-enabled` and `is-active` for the declared unit. Fails unless enabled and active. |
| `sessions.started_without_login` | [part-4-first-week](../machine-setup.md#part-4-first-week) | ✓ | ✓ | nv | self | The unit is active and its `ActiveEnterTimestamp` falls before the account's first login session since boot (`loginctl`). `warn` if it started after a login: the reboot test hasn't been passed. |
| `sessions.own_slice` | [sessions-that-survive-a-reboot](../machine-setup.md#sessions-that-survive-a-reboot) | PENDING | PENDING | — | self | PENDING (homelab generic controls): the exact slice rule. Not in the default set until specified. |

### Shared tools

| id | Section | U | O | M | Scope | What it reads; when it fails |
|---|---|---|---|---|---|---|
| `tools.present` | [shared-tools-private-data](../machine-setup.md#shared-tools-private-data) | ✓ | ✓ | ✓ | self | `shutil.which` for names from a fixed enum (`git`, `gh`, `uv`, `python3`, `hledger`, `tmux`, `herdr`). The manifest picks from the enum. `warn` per missing tool. |
| `tools.shared_readonly` | [shared-tools-private-data](../machine-setup.md#shared-tools-private-data) | PENDING | PENDING | — | self | PENDING (homelab paradigms): where shared tools live and how write protection is judged. Not in the default set. |

### Heavy jobs and the gate

| id | Section | U | O | M | Scope | What it reads; when it fails |
|---|---|---|---|---|---|---|
| `heavy.single_lock` | [one-heavy-job-at-a-time](../machine-setup.md#one-heavy-job-at-a-time) | PENDING | PENDING | — | — | PENDING (homelab generic controls). Id reserved, not in the default set. |
| `gate.present` | [accounts-talk-through-a-gate-not-shared-folders](../machine-setup.md#accounts-talk-through-a-gate-not-shared-folders) | PENDING | PENDING | — | — | PENDING (homelab generic controls), then a security read before any code. Id reserved, not in the default set. |

### Credentials

| id | Section | U | O | M | Scope | What it reads; when it fails |
|---|---|---|---|---|---|---|
| `credentials.store_available` | [credentials](../machine-setup.md#credentials) | ✓ | ✓ | ✓ | self | Reuses the existing credential-store probe from [`connect.md`](../connect.md), not a new one. Fails if no store is usable without a desktop session. This matters on a headless box. |

### Power and hardware

| id | Section | U | O | M | Scope | What it reads; when it fails |
|---|---|---|---|---|---|---|
| `power.on_after_outage` | [part-2-picking-a-machine](../machine-setup.md#part-2-picking-a-machine) | nv | nv | ✓ | machine | Linux: `manual_only`, BIOS isn't readable. It can be attested. macOS: `pmset -g` `autorestart 1`. |
| `power.no_sleep` | [the-box-works-the-laptop-is-a-remote-control](../machine-setup.md#the-box-works-the-laptop-is-a-remote-control) | ✓ | ✓ | ✓ | machine | Linux: `systemctl is-enabled` for `sleep.target`, `suspend.target` and `hibernate.target` (pass only if masked). macOS: `pmset -g` `sleep 0`. Severity follows `machine.role`. |
| `hardware.memory_min` | [part-2-picking-a-machine](../machine-setup.md#part-2-picking-a-machine) | ✓ | ✓ | ✓ | machine | `/proc/meminfo` or `sysctl -n hw.memsize`. `warn` below `min_gb` (default 16). |

### Operating system

| id | Section | U | O | M | Scope | What it reads; when it fails |
|---|---|---|---|---|---|---|
| `disk.encrypted` | [part-4-first-week](../machine-setup.md#part-4-first-week) | ✓ | ✓ | ✓ | machine | Linux: `lsblk -J -o NAME,TYPE,MOUNTPOINTS`, with a `crypt` device in the ancestry of `/`. macOS: `fdesetup status`. Fails if not encrypted. |
| `login.autologin_locked` | [omarchy-arch-based](../machine-setup.md#omarchy-arch-based) | ✓ | ✓ | ✓ | machine | Auto-login: GDM `/etc/gdm3/custom.conf` (U), SDDM `/etc/sddm.conf.d/*.conf` `[Autologin]` (O), `com.apple.loginwindow autoLoginUser` (M). If auto-login is on, look for an idle lock. Severity follows `machine.role`. Omarchy idle-lock location: needs verification (see open questions), so `not_verified` until confirmed. |
| `security.apparmor` | [ubuntu-lts-recommended-default](../machine-setup.md#ubuntu-lts-recommended-default) | ✓ | — | — | machine | `/sys/module/apparmor/parameters/enabled` is `Y`. `aa-status` needs root and is not used. |
| `security.landlock` | [omarchy-arch-based](../machine-setup.md#omarchy-arch-based) | ✓ | ✓ | — | machine | `landlock` listed in `/sys/kernel/security/lsm`. Info only; `not_verified` if unreadable. It reports availability, not a policy. |

### Updates and backups

| id | Section | U | O | M | Scope | What it reads; when it fails |
|---|---|---|---|---|---|---|
| `updates.security_auto` | [backups-and-updates](../machine-setup.md#backups-and-updates) | ✓ | — | ✓ | machine | U: `dpkg-query -W unattended-upgrades`, `APT::Periodic::Unattended-Upgrade "1"` under `/etc/apt/apt.conf.d/`, `apt-daily-upgrade.timer` enabled. M: `com.apple.SoftwareUpdate` `CriticalUpdateInstall`. |
| `updates.omarchy_recent` | [omarchy-arch-based](../machine-setup.md#omarchy-arch-based) | — | ✓ | — | machine | Last full upgrade in `/var/log/pacman.log`. `warn` if older than `max_age_days` (default 14). The fix shown is `omarchy update`, never `pacman -Syu`. |
| `updates.reboot_pending` | [backups-and-updates](../machine-setup.md#backups-and-updates) | ✓ | ✓ | — | machine | U: `/var/run/reboot-required`. O: no `/usr/lib/modules/$(uname -r)`, meaning the running kernel was replaced. `warn`. |
| `updates.mainbranch_current` | [backups-and-updates](../machine-setup.md#backups-and-updates) | ✓ | ✓ | ✓ | self | Reuses `mb doctor`'s version check. `warn` when behind. |
| `backups.home_backup` | [backups-and-updates](../machine-setup.md#backups-and-updates) | nv | nv | nv | self | `manual_only` until homelab's paradigms say what is checkable. It can be attested. PENDING. |

### Remote access

| id | Section | U | O | M | Scope | What it reads; when it fails |
|---|---|---|---|---|---|---|
| `remote.ssh_keys_only` | [managing-it-from-a-mac](../machine-setup.md#managing-it-from-a-mac) | ✓ | ✓ | ✓ | machine | Parse `/etc/ssh/sshd_config` and `sshd_config.d/*.conf` for `PasswordAuthentication` and `KbdInteractiveAuthentication`. `sshd -T` needs root and isn't used. `Match` blocks, or `Include` outside `sshd_config.d`, give `not_verified` (reason `ambiguous_config`). No sshd gives `not_applicable`. |
| `remote.tailscale_up` | [managing-it-from-a-mac](../machine-setup.md#managing-it-from-a-mac) | ✓ | ✓ | ✓ | machine | `tailscale status --json`, field `BackendState == "Running"`. Missing CLI or denied socket gives `not_verified`. |

Not checks: the lid-closed test and the key-roll drill in
[Part 4](../machine-setup.md#part-4-first-week) are things the owner does. They
stay in the guide as manual steps.

Follow-up candidates, not in v1: SSH listening on a public interface, per-user
firewall rules, Landlock policies (isolation controls, which need a security
read first).

## Doctor output

### Command

```bash
mb machine doctor [--manifest PATH] [--scope self|all] [--json]
```

Human output groups by section and prints each fix's argv quoted, with who
runs it. `--json` prints the payload below and nothing else on stdout.

### JSON

The payload uses the shared envelope from
[`json-output-contract.md`](../json-output-contract.md):
`result_schema.name = "mainbranch.machine.doctor.result"`,
`mb_command = "mb machine doctor"`. The domain schema is
`schema: "mb.machine.doctor"`, `schema_version: 1`.

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
  "platform": {
    "id": "omarchy",
    "version": "4.0.6",
    "signals": {"os_release_id": "omarchy", "pacman_package": true}
  },
  "run_as": {"account": "acme-agent", "role": "agent"},
  "scope": "self",
  "manifest": {
    "source": "default_path",
    "sha256": "<hex>",
    "schema_version": 1
  },
  "summary": {
    "pass": 14, "fail": 0, "warn": 1, "not_verified": 2,
    "attested": 1, "skipped": 1, "not_applicable": 4
  },
  "checks": [
    {
      "id": "sessions.linger",
      "title": "Agent sessions start at boot",
      "section": "docs/machine-setup.md#sessions-that-survive-a-reboot",
      "scope": "machine",
      "subject": "acme-agent",
      "state": "pass",
      "severity": "fail",
      "observed": {"linger": true},
      "reason": null,
      "fix": null
    },
    {
      "id": "accounts.agent_no_sudo",
      "title": "Agent accounts have no sudo",
      "section": "docs/machine-setup.md#admin-account-and-agent-accounts",
      "scope": "machine",
      "subject": "acme-agent",
      "state": "not_verified",
      "severity": "fail",
      "observed": {"in_admin_group": false},
      "reason": "needs_root",
      "fix": null
    },
    {
      "id": "power.on_after_outage",
      "state": "attested",
      "attested": {"date": "2026-10-28", "note": "BIOS: After Power Loss set to Power On"},
      "reason": "manual_only",
      "fix": {
        "display_only": true,
        "run_as": "owner_at_machine",
        "argv": null,
        "text": "In the BIOS power menu, set the after-power-loss option to Power On."
      }
    }
  ]
}
```

The third check is trimmed to the fields that differ.

Field rules:

- `state` is one of `pass`, `fail`, `warn`, `not_verified`, `attested`,
  `skipped`, `not_applicable`. `severity` is what a failure would be;
  `state` is what happened.
- `reason` is set for every state except `pass` and `fail`, from a fixed
  enum: `needs_root`, `platform_unsupported`, `platform_partial`,
  `ambiguous_platform`, `ambiguous_config`, `probe_missing`, `probe_timeout`,
  `probe_error`, `manual_only`, `other_account`, `no_manifest`,
  `pending_spec`, `skipped_by_manifest`. No free-text reasons, so no stray
  paths or output leak.
- `observed` holds the parsed facts the verdict used (booleans, numbers,
  enum strings). Never raw command output, file contents or absolute paths
  outside the fixed system paths named in the registry.
- `fix.display_only` is always `true`. `fix.argv` is a list or `null` (BIOS
  and other manual steps). Doctor never runs it.
- `safe_to_share` is `false` because account names appear. A scrubbed share
  mode is a follow-up.
- A manifest error returns the same envelope with `ok: false`,
  `result_status: "error"`, `exit_code: 2`, an empty `checks`, and
  `errors` entries like
  `{"code": "manifest.unknown_check_id", "id": "power.nap"}`. No
  traceback, no file contents.

### Exit codes

| Code | Meaning | `ok` |
|---|---|---|
| `0` | Healthy: no `fail` and no `not_verified`. `warn`, `attested`, `skipped` and `not_applicable` are allowed. | `true` |
| `1` | At least one `fail`. | `false` |
| `2` | Usage error, invalid or unreadable manifest, or internal error. No verdict. | `false` |
| `3` | No `fail`, but at least one `not_verified`. | `false` |

`3` is new for `mb`, which elsewhere uses `0`/`1`/`2`. It exists because the
rule says unverified is never a pass. With only `0`/`1`, a script that
checks for `0` would read "couldn't check" as "healthy".

## Validation plan for the code batch

- A registry test: every id is unique, every `section` anchor exists in
  `docs/machine-setup.md`, every `manual_only` check has a fix with `text`,
  and every PENDING id is out of the default set.
- A static test: no `shell=True` in machine-doctor code, and no `sudo`,
  `pkexec`, `doas` or `su` anywhere in a probe argv.
- Manifest tests: unknown key, unknown id, bad account name, bad unit name,
  and `attest` on a non-manual check all exit `2`.
- Fixture tests per platform from captured, synthetic `os-release`, `lsblk`,
  `pmset` and `sshd_config` samples.
- One real run each on an Ubuntu LTS box and an Omarchy box, as an agent
  account and as the admin account, with JSON and exit codes recorded in the
  PR. macOS gets one run if a Mac is available; otherwise its probes stay
  labeled unverified in the PR.

## Open questions

1. Exit code `3` for `not_verified`: accept it, or fold it into `1`?
2. `attested` as a separate state for `manual_only` checks: accept it? (It
   needs a security read. It is never `pass`, but it does keep exit `0`
   reachable on Linux, where BIOS power-on can never be read.)
3. Default manifest path `/etc/mainbranch/machine.yaml`, admin-owned: accept
   it?
4. Omarchy idle lock: the setting lives in Omarchy's shell config
   (`idle.lock`), but the file location isn't recorded yet. Confirm it on
   an Omarchy box before `login.autologin_locked` can pass there.
5. A tracking issue doesn't exist yet. Open one before the code batch?

## PENDING

- Homelab's sanitized pack: manifest schema, synthetic examples, generic
  controls (`heavy.single_lock`, `gate.present`, `sessions.own_slice`) and
  paradigms (`tools.shared_readonly`, `backups.home_backup`).
- The security review of that pack.

Next: the reviewers answer the open questions; reconcile with homelab's pack
when it lands; then the code batch.
