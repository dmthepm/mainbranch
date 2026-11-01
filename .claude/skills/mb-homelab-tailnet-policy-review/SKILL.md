---
name: mb-homelab-tailnet-policy-review
description: Review a local Tailscale policy for broad access, SSH rules, tag ownership, and agent-to-admin reach without credentials or changes.
loops: [sense, decide]
---

# Tailnet policy review

Draft: tested on synthetic data and one host. Real tailnet DNS, node, login and
peer names have not been tested. Inspect the whole response before sharing it.

Say first: "This is read-only. I will read the policy file you provide and show
a redacted report without changing your policy, tailnet or business data."

1. Read [references/safety-contract.md](references/safety-contract.md) and
   [references/commands.md](references/commands.md).
2. Get the local policy path and the operator's agent-tag and admin-tag lists.
   Accept a file already exported or checked out from their policy repo.
   Never fetch a policy or ask for credentials. If tags are unknown, say that
   agent-to-admin reach remains incomplete.
3. Resolve scripts from the runtime-supplied skill directory. From that
   directory, run the following with the provided path and repeated tag flags:

   ```bash
   python3 scripts/review.py "$POLICY_FILE" --agent-tag tag:agent --admin-tag tag:admin | python3 scripts/redact.py
   ```

   The tag names above are examples. Substitute only operator-provided tags,
   quoting arguments as data. Python 3.10+ is required; never install it.
4. Show the redacted table. Each row names the rule location, why to inspect it,
   a safer shape, and official docs. Explain that static selectors do not
   resolve groups, hosts, CIDRs, posture, or application capabilities. Zero
   rows cannot prove isolation. Invalid HuJSON means the review is incomplete.
   Tailscale's policy reference says to prefer grants; `acls` still work.
5. Stop after a short "What to look at" list. Offer shapes for the operator to
   consider, without editing, applying or publishing a policy.

## What this skill never does

- Change files, network access, tags, ownership, or SSH rules.
- Call an API, retrieve credentials, or open an admin console.
- Read business data, print policy text, save raw output or publish the report.
- Claim to calculate effective access or replace policy tests.
