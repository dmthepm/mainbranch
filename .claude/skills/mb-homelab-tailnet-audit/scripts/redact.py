#!/usr/bin/env python3
"""Read private JSON on stdin and emit a selected, redacted Markdown table."""

from __future__ import annotations

import ipaddress
import json
import re
import sys

KEY = re.compile(
    r"(?:(?:nodekey|mkey|discokey|nlpub|tlpub):[^\s\"'<>|,}]+|tskey-[\w-]+)",
    re.IGNORECASE,
)
EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}")
DNS = re.compile(r"(?:[\w-]+\.)*ts\.net\.?", re.IGNORECASE)
URL = re.compile(r"https?://[^\s\"'<>|]+", re.IGNORECASE)
IPV4 = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
IPV6 = re.compile(
    r"(?<![0-9a-fA-F:])(?:[0-9a-fA-F]{0,4}:){2,}"
    r"[0-9a-fA-F:.]*(?:%[\w.-]+)?(?![0-9a-fA-F:])"
)
IDENTITY_CLASSES = {
    "displayname": "user",
    "loginname": "user",
    "email": "user",
    "profilepicurl": "url",
    "id": "id",
    "stableid": "id",
    "nodeid": "id",
    "publickey": "id",
    "hostname": "node",
    "dnsname": "node",
    "certdomains": "node",
    "magicdnssuffix": "tailnet",
    "tailnetname": "tailnet",
    "currenttailnet": "tailnet",
    "tailnet": "tailnet",
    "machine": "node",
    "host": "node",
    "name": "node",
}
TABLE_FIELDS = ("check", "location", "result", "safer", "docs")
MACHINE_CHECKS = {
    "Version and track",
    "Tailscale SSH",
    "Auto-update",
    "Tailnet lock",
    "OpenSSH listeners",
    "Serve",
    "Funnel",
    "macOS build",
}
POLICY_CHECKS = {
    "ssh-section",
    "ssh-accept",
    "wildcard",
    "member-to-all",
    "agent-to-admin",
    "tag-without-owner",
    "not checked",
}
DOCS = {
    "https://tailscale.com/docs/reference/syntax/policy-file",
    "https://tailscale.com/docs/features/tailscale-ssh",
}


class Redactor:
    def __init__(self, payload: object):
        self.values: dict[str, str] = {}
        self.counts: dict[str, int] = {}
        self.discover(payload)
        self.identities = sorted(self.values, key=len, reverse=True)

    def placeholder(self, value: str, kind: str = "node") -> str:
        normalized = value.lower()
        if normalized not in self.values:
            self.counts[kind] = self.counts.get(kind, 0) + 1
            self.values[normalized] = f"{kind}-{self.counts[kind]}"
        return self.values[normalized]

    def discover(self, value: object, context: str | None = None) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                field = str(key).lower()
                kind = IDENTITY_CLASSES.get(field)
                if field in {"user", "userprofiles"}:
                    kind = "user"
                    if isinstance(child, dict):
                        for identity in child:
                            self.placeholder(str(identity), "id")
                if field == "name" and context in {"tailnet", "user"}:
                    kind = context
                self.discover(child, kind or context)
        elif isinstance(value, list):
            for child in value:
                self.discover(child, context)
        elif (
            isinstance(value, (str, int))
            and not isinstance(value, bool)
            and context
            and str(value)
        ):
            self.placeholder(str(value), context)

    def scrub(self, value: object) -> str:
        text = str(value)
        # One substitution prevents replacements from modifying earlier placeholders.
        if self.identities:
            pattern = "|".join(re.escape(value) for value in self.identities)
            text = re.sub(
                pattern, lambda m: self.values[m[0].lower()], text, flags=re.IGNORECASE
            )
        text = URL.sub(lambda m: self.placeholder(m[0], "url"), text)
        text = KEY.sub(lambda m: self.placeholder(m[0], "id"), text)
        text = EMAIL.sub(lambda m: self.placeholder(m[0], "user"), text)
        text = DNS.sub(lambda m: self.placeholder(m[0]), text)

        def address(match: re.Match) -> str:
            candidate = match[0]
            try:
                ipaddress.ip_address(candidate.split("%", 1)[0])
            except ValueError:
                return candidate
            return self.placeholder(candidate)

        text = IPV6.sub(address, text)
        text = IPV4.sub(address, text)
        return (
            text.replace("|", "\\|")
            .replace("\n", " ")
            .replace("\r", " ")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )


def machine_result(check: str, value: object) -> str:
    if check in {"Serve", "Funnel"} and isinstance(value, (dict, list)):
        return (
            "Configuration present; review forwarding warnings locally"
            if value
            else "No configuration returned"
        )
    if not isinstance(value, str):
        return "not checked: unexpected field value"
    if value.startswith("not checked:"):
        return value
    if check in {"Tailscale SSH", "Auto-update", "Tailnet lock"} and value in {
        "on",
        "off",
    }:
        return value
    if check == "macOS build" and value in {
        "standalone",
        "App Store",
        "open-source tailscaled",
    }:
        return value
    if check == "Version and track" and re.fullmatch(
        r"\d+\.\d+\.\d+(?:[-+][a-zA-Z0-9.-]+)?; (?:current for track|"
        r"differs from current track release|track currency not checked: upstream version unavailable)",
        value,
    ):
        return value
    if check == "OpenSSH listeners" and value.startswith("OpenSSH listening: "):
        interfaces = set()
        for listener in value.removeprefix("OpenSSH listening: ").split("; "):
            try:
                host, port = listener.split(", TCP ")
                address = ipaddress.ip_address(host)
                if not port.isdigit() or not 0 < int(port) < 65536:
                    raise ValueError
            except ValueError:
                return "not checked: unexpected listener value"
            interfaces.add(
                "loopback"
                if address.is_loopback
                else "all interfaces"
                if address.is_unspecified
                else "specific interface"
            )
        return "OpenSSH listening: " + "; ".join(sorted(interfaces))
    return "not checked: unexpected field value"


def render(payload: dict) -> str:
    redactor = Redactor(payload)
    lines = [
        "Read-only report. No machine, tailnet or policy settings changed.",
        "",
        "| Check | Location | Result | Safer shape | Docs |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in payload.get("rows", []):
        if not isinstance(row, dict):
            continue
        check = row.get("check")
        if not isinstance(check, str) or check not in MACHINE_CHECKS | POLICY_CHECKS:
            continue
        selected = {"check": check}
        if check in MACHINE_CHECKS:
            selected["result"] = machine_result(check, row.get("result"))
        else:
            for field in ("result", "safer"):
                if isinstance(row.get(field), str):
                    selected[field] = row[field]
            location = row.get("location", "")
            if isinstance(location, str) and re.fullmatch(
                r"(?:policy|ssh|(?:ssh|acls|grants)\[\d+\](?:\.(?:src|dst)\[\d+\])?)",
                location,
            ):
                selected["location"] = location
            if isinstance(row.get("docs"), str) and row["docs"] in DOCS:
                selected["docs"] = row["docs"]
        cells = [
            selected.get(field, "")
            if field == "docs"
            else redactor.scrub(selected.get(field, ""))
            for field in TABLE_FIELDS
        ]
        lines.append("| " + " | ".join(cells) + " |")
    lines.extend(["", "What to look at:", ""])
    lines.extend(
        "- " + redactor.scrub(note)
        for note in payload.get("notes", [])
        if isinstance(note, str)
    )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    try:
        print(render(json.load(sys.stdin)), end="")
    except (ValueError, TypeError, AttributeError):
        print(
            "Cannot render report: expected collector or policy-review JSON.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
