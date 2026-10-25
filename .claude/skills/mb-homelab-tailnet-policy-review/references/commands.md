# Command evidence

Checked 2026-10-25. This skill runs no external commands from Python, makes no
network requests and reads only the supplied policy file. There is no shell
command allowlist because there are no subprocess calls.

| Local entrypoint | Reads | Official policy reference | Checked |
| --- | --- | --- | --- |
| `python3 scripts/review.py "$POLICY_FILE" --agent-tag tag:agent --admin-tag tag:admin` | Supplied local HuJSON policy and operator-provided tag lists | https://tailscale.com/docs/reference/syntax/policy-file | 2026-10-25 |
| `python3 scripts/redact.py` | Review JSON from stdin | https://tailscale.com/docs/reference/syntax/policy-file | 2026-10-25 |

These are bundled Python entrypoints, not commands supplied by Tailscale.
Repeat either tag flag for multiple tags. No fetching or exporting command is
used. SSH guidance: https://tailscale.com/docs/features/tailscale-ssh, checked
2026-10-25. Prefer check for interactive human sessions; unattended access
needs an explicit operator decision about identity and access scope.

## Not used, unconfirmed

None. Admin API, credential and admin-console commands are outside this skill.
