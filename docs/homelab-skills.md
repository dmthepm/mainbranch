# Read-only homelab skills

Use these Claude Code skills to inspect the machines that run your agents.
They work outside a business repo and do not touch business data. They are
Claude-only, excluded from Codex global skills, workflow inventory and daily
start routing. The two tailnet skills remain draft pending runtime dogfood and
security review.

With the Main Branch plugin enabled, invoke the skill by name in Claude Code.
See the [invocation contract](claude-code-invocation-contract.md) for plugin
namespaces and project-local fallback. Python 3.10+ is required.

| Skill | Input | Checks |
| --- | --- | --- |
| `/mb-homelab-machine` | An always-on agent machine you are setting up, maintaining or extending | Read-only setup, maintenance, extension and hardening checks that report NOT VERIFIED instead of guessing; the owner runs root steps |
| `/mb-homelab-tailnet-audit` | Current machine, with Tailscale available | Version and current-track release; Tailscale SSH; Serve/Funnel forwards; tailnet lock; auto-update preference; OpenSSH listeners on Linux; macOS build metadata |
| `/mb-homelab-tailnet-policy-review` | Policy file already on disk and lists of agent/admin tags | SSH section; accept versus check; wildcard sources/destinations; member-to-all rules; missing tag ownership; direct agent-tag reach to admin tags or all destinations |

Each returns one redacted table and a short list of things to inspect. Unknown
fields say "not checked" with a reason. Command availability, permissions and
platform differences can limit coverage. No check uses sudo.

## Run the bundled scripts directly

From the chosen skill directory, run the applicable pipeline:

```bash
python3 scripts/collect.py | python3 scripts/redact.py
```

For a local policy, use its path and repeat the tag flags for each supplied tag:

```bash
python3 scripts/review.py "$POLICY_FILE" --agent-tag tag:agent --admin-tag tag:admin | python3 scripts/redact.py
```

These tag names are examples. HuJSON comments and trailing commas are accepted.
Review results exit 0, including an explicit incomplete result for invalid
HuJSON. An unreadable file exits nonzero; when using a pipeline, inspect both
process exit statuses. No policy is downloaded, exported or written.

## Privacy and limits

Keep raw JSON local. The report omits raw nested Serve/Funnel configuration and
replaces IPs, Tailscale key values, tailnet DNS names, identified hostnames and
emails with placeholders. Placeholders remain stable within one invocation.
Unlabelled names in arbitrary prose need a local human check before sharing.
Redaction is verified against synthetic fixtures and one real machine check run
by a user that can reach `tailscaled`: the report held none of that machine's
tailnet DNS names, node names, logins, peer names, IPs or hostname. One machine
proves no other setup, and no real policy has been reviewed. Inspect the entire
response locally before sharing, including model explanations and permission
errors; these do not pass through the redactor.
The skills never publish a report, change settings, retrieve credentials,
call an admin API, install software or connect to other machines.

The machine check compares the local CLI version to the public package
server's current-track release. It does not establish patch safety or that the
running daemon has the same version. Admin-port detection uses a conservative
list of common ports; other services need local interpretation. Serve status
can omit Services configuration. Linux procfs listener attribution depends on
process permissions and reports only confirmed OpenSSH sockets; otherwise it
is not checked. Other platforms have no confirmed listener probe yet.
macOS identification requires explicit version metadata; ambiguous builds are
not checked. Auto-update is the daemon preference, not App Store or operating
system package-manager scheduling.

Run the machine check as a user that can reach `tailscaled`. Otherwise
daemon-backed checks say "not checked"; version and local listener checks may
still work. A scripted `claude -p` turn stops at a permission prompt unless you grant the skill directory and its
`python3` command.

Policy review checks literal selectors in `acls`, `grants` and `ssh`; it does
not compute effective permissions through groups, host aliases, CIDRs, posture,
application capabilities or other policy sections. Missing tag lists leave
agent/admin checks incomplete. Agent-to-admin rows cover `acls` and `grants`; an
`ssh` rule between those tags appears only as the general `ssh-accept` row. A
clean table cannot prove isolation. Keep
policy tests and effective-access validation as a separate operator task.

The [official policy reference](https://tailscale.com/docs/reference/syntax/policy-file)
and [Tailscale CLI reference](https://tailscale.com/docs/reference/tailscale-cli)
explain the underlying controls. For current details, use Tailscale's
[docs index for agents](https://tailscale.com/docs/llms.txt),
[security bulletins](https://tailscale.com/security-bulletins) and
[changelog](https://tailscale.com/changelog). Its
[official skill](https://github.com/tailscale/tailscale-skill) is a public alpha
and separate from these skills. Each skill carries its own command evidence
and read-only safety contract. Other mesh adapters require their own probes
and tests before support can be claimed.
