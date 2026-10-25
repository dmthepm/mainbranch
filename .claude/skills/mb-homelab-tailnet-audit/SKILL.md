---
name: mb-homelab-tailnet-audit
description: Audit local Tailscale machine settings when asked about tailnet security, SSH, Serve, Funnel, updates, or tailnet lock. Produce a redacted read-only report.
loops: [sense, decide]
---

# Tailnet machine check

Say first: "This is read-only. I will inspect local settings and show a redacted
report without changing your machine, tailnet or business data."

1. Read [references/safety-contract.md](references/safety-contract.md) and
   [references/commands.md](references/commands.md). Use the skill directory
   supplied by the runtime to resolve the script paths. No business repo needed.
2. Run on each machine the operator wants to inspect, from this skill directory:

   ```bash
   python3 scripts/collect.py | python3 scripts/redact.py
   ```

   Run only locally. Ask the operator to invoke this skill separately on other
   machines. Never SSH into them. If Python 3.10+ or Tailscale is absent, report
   the missing prerequisite. Never install or elevate privileges.
3. Show the redacted table and a short "What to look at" list. Prioritize
   forwarding warnings and unknown checks. Explain that admin ports are a
   heuristic, and a matching version is current for its track, not a security
   guarantee. Serve status may omit Services configuration.
4. Stop after the report. Suggest an operator review using the linked docs;
   leave any change to a separate workflow.

## What this skill never does

- Change settings, update software, enable SSH, Serve, Funnel or tailnet lock.
- Read credentials, call an admin API, or access the admin console.
- Read or write business data, save raw output, or publish the report.
- Treat missing or unsupported checks as proof of safety.
