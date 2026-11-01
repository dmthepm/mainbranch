#!/usr/bin/env python3
"""Review a local HuJSON policy without network or process calls."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

DOC = "https://tailscale.com/docs/reference/syntax/policy-file"
SSH_DOC = "https://tailscale.com/docs/features/tailscale-ssh"


def parse(text: str) -> dict:
    # Tokenize strings before comments so URLs and escaped quotes stay intact.
    tokens = re.findall(r'"(?:\\.|[^"\\])*"|//[^\n]*|/\*[\s\S]*?\*/|[^"/]+|/', text)
    stripped = "".join(" " if t.startswith(("//", "/*")) else t for t in tokens)
    stripped = re.sub(r'"(?:\\.|[^"\\])*"|,(\s*[}\]])', lambda m: m[1] if m[1] else m[0], stripped)
    value = json.loads(stripped)
    if not isinstance(value, dict):
        raise ValueError("policy must be an object")
    return value


def selectors(rule: dict, field: str) -> list[str]:
    value = rule.get(field, [])
    return [x for x in value if isinstance(x, str)] if isinstance(value, list) else []


def destination(value: str) -> str:
    # ACL destinations add a port suffix; grant and SSH destinations do not.
    return re.sub(r":(?:\*|[0-9][0-9,\-]*)$", "", value)


def review(policy: dict, agent_tags: list[str], admin_tags: list[str]) -> dict:
    rows = []

    def flag(code: str, location: str, why: str, safer: str, docs: str = DOC) -> None:
        rows.append(
            {
                "check": code,
                "location": location,
                "result": why,
                "safer": safer,
                "docs": docs,
            }
        )

    if "ssh" in policy:
        flag(
            "ssh-section",
            "ssh",
            "Tailscale SSH policy is present; review intended access.",
            "Keep only necessary SSH rules and use check for interactive access.",
            SSH_DOC,
        )
    used_tags = {}
    for section in ("ssh", "acls", "grants"):
        rules = policy.get(section, [])
        if not isinstance(rules, list):
            continue
        for i, rule in enumerate(rules):
            if not isinstance(rule, dict):
                continue
            location = f"{section}[{i}]"
            src = selectors(rule, "src")
            dst = [destination(v) if section == "acls" else v for v in selectors(rule, "dst")]
            for field, values in (("src", src), ("dst", dst)):
                for index, selector in enumerate(values):
                    if selector.startswith("tag:"):
                        used_tags.setdefault(selector, f"{location}.{field}[{index}]")
            if section == "ssh" and rule.get("action") == "accept":
                flag(
                    "ssh-accept",
                    location,
                    "accept skips periodic identity confirmation.",
                    "Use check with a suitable checkPeriod for human sessions.",
                    SSH_DOC,
                )
            if "*" in src or "*" in dst:
                flag(
                    "wildcard",
                    location,
                    "A wildcard permits a broad set of machines or users.",
                    "Name the smallest required source and destination selectors.",
                )
            if "autogroup:member" in src and "*" in dst:
                flag(
                    "member-to-all",
                    location,
                    "Every member can reach the wildcard destination.",
                    "Limit member access to explicitly required destinations.",
                )
            permits = section == "grants" or rule.get("action") == "accept"
            if (
                section in {"acls", "grants"}
                and permits
                and set(src) & set(agent_tags)
                and (set(dst) & set(admin_tags) or "*" in dst)
            ):
                flag(
                    "agent-to-admin",
                    location,
                    "An agent tag can reach an admin tag or every destination.",
                    "Separate agent and admin destinations; permit only required service ports.",
                )
    owners = policy.get("tagOwners", {})
    for tag in sorted(used_tags):
        if not isinstance(owners, dict) or tag not in owners:
            flag(
                "tag-without-owner",
                used_tags[tag],
                "A referenced tag has no tagOwners entry.",
                "Declare a narrowly scoped owner for the referenced tag.",
            )
    return {
        "kind": "policy",
        "rows": rows,
        "notes": [
            "Static selector review only; groups, hosts, CIDRs, posture and "
            "application capabilities are not resolved.",
            "Zero rows does not prove isolation. Validate effective access separately.",
            "Agent/admin reach checks require both tag lists; "
            "omitted lists leave that check incomplete.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("policy", type=Path)
    parser.add_argument("--agent-tag", action="append", default=[])
    parser.add_argument("--admin-tag", action="append", default=[])
    args = parser.parse_args()
    try:
        policy = parse(args.policy.read_text(encoding="utf-8"))
    except OSError:
        print(
            "Cannot read policy input; check the local path and permissions.",
            file=sys.stderr,
        )
        return 1
    except (ValueError, UnicodeError):
        # Invalid input is a review result, not a clean policy or an unreadable file.
        json.dump(
            {
                "kind": "policy",
                "rows": [
                    {
                        "check": "not checked",
                        "location": "policy",
                        "result": "Invalid HuJSON; correct the local policy syntax before review.",
                    }
                ],
                "notes": ["Policy review incomplete."],
            },
            sys.stdout,
        )
        print()
        return 0
    json.dump(review(policy, args.agent_tag, args.admin_tag), sys.stdout)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
