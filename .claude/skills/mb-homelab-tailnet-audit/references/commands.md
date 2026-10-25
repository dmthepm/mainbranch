# Command evidence

Checked 2026-10-25 against official Tailscale docs. Every external command uses
one fixed argv tuple. No shell expansion, arbitrary arguments or sudo.

| Exact argv | Reads | Official docs | Checked |
| --- | --- | --- | --- |
| `tailscale version --json --upstream` | Local version and latest release for the current track; contacts the public package server | https://tailscale.com/docs/reference/tailscale-cli#version | 2026-10-25 |
| `tailscale status --json` | Local daemon status and identity fields for redaction | https://tailscale.com/docs/reference/tailscale-cli#status | 2026-10-25 |
| `tailscale debug prefs` | Local daemon preferences; RunSSH and AutoUpdate.Apply when present | https://tailscale.com/docs/reference/route-injection#troubleshooting | 2026-10-25 |
| `tailscale serve status --json` | Local Serve configuration | https://tailscale.com/docs/reference/tailscale-cli/serve#get-the-status | 2026-10-25 |
| `tailscale funnel status --json` | Local Funnel configuration | https://tailscale.com/docs/reference/tailscale-cli/funnel#get-the-status | 2026-10-25 |
| `tailscale lock status --json` | Local tailnet lock status | https://tailscale.com/docs/reference/tailscale-cli/lock#lock-status | 2026-10-25 |

Local Python entrypoints, checked 2026-10-25: `python3 scripts/collect.py` and
`python3 scripts/redact.py` implement this contract; they are not Tailscale
commands. Their upstream command reference is
https://tailscale.com/docs/reference/tailscale-cli.

The collector also reads Linux procfs process names, socket links and TCP
listener tables with Python file reads. If permissions prevent process
attribution, OpenSSH is "not checked". Listener addresses become stable placeholders in the shared report. On other platforms it is
not checked. No connection attempt is made.

macOS build identification uses explicit macapp/macsys/-oss version metadata
when available, otherwise "not checked". These are build hints, not proof of
which of several installations is running. Variant background:
https://tailscale.com/docs/concepts/macos-variants, checked 2026-10-25.
Preference and version JSON fields can vary by build; absent fields remain
unknown. AutoUpdate.Apply describes the daemon preference, not App Store or
system package-manager scheduling. Serve status may omit Services.

## Not used, unconfirmed

Exact listener invocations of ss and lsof, and macOS service-manager probes,
were not confirmed in official Tailscale docs. They are not allowlisted or
invoked. This limits OpenSSH coverage on non-Linux platforms. No speculative
fallback command is run.
