#!/usr/bin/env python3
"""Read private JSON on stdin and emit a selected, redacted Markdown table."""

from __future__ import annotations

import ipaddress
import json
import re
import sys

KEY = re.compile(
    r'\b(?:(?:nodekey|mkey|discokey|nlpub|tlpub):[^\s"\'<>|,}]+|tskey-[\w-]+)', re.IGNORECASE
)
EMAIL = re.compile(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}")
DNS = re.compile(r"(?<![\w-])(?:[\w-]+\.)+ts\.net\.?", re.IGNORECASE)
IP = re.compile(r"(?<![\w])(?:[0-9a-fA-F]*:[0-9a-fA-F:.%]+|(?:\d{1,3}\.){3}\d{1,3})(?:/\d+)?")
IDENTITY_FIELDS = {
    "hostname",
    "dnsname",
    "name",
    "machine",
    "host",
    "loginname",
    "email",
}


class Redactor:
    def __init__(self, payload: object):
        self.nodes: dict[str, str] = {}
        self.users: dict[str, str] = {}
        self.hosts: set[str] = set()
        self.discover(payload)

    def placeholder(self, value: str, user: bool = False) -> str:
        mapping = self.users if user else self.nodes
        normalized = value.rstrip(".").lower()
        if normalized not in mapping:
            mapping[normalized] = f"{'user' if user else 'node'}-{len(mapping) + 1}"
        return mapping[normalized]

    def discover(self, value: object) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if str(key).lower() in IDENTITY_FIELDS and isinstance(child, str) and child:
                    self.hosts.add(child)
                self.discover(child)
        elif isinstance(value, list):
            for child in value:
                self.discover(child)

    def scrub(self, value: object) -> str:
        text = str(value)
        text = KEY.sub("[key]", text)
        text = EMAIL.sub(lambda m: self.placeholder(m[0], True), text)
        text = DNS.sub(lambda m: self.placeholder(m[0]), text)

        def address(match: re.Match) -> str:
            candidate = match[0]
            try:
                ipaddress.ip_interface(candidate.split("%", 1)[0])
            except ValueError:
                return candidate
            return self.placeholder(candidate)

        text = IP.sub(address, text)
        for host in sorted(self.hosts, key=len, reverse=True):
            text = re.sub(
                r"(?<![\w-])" + re.escape(host) + r"(?![\w-])",
                lambda m, host=host: self.placeholder(host, "@" in host),
                text,
                flags=re.IGNORECASE,
            )
        return (
            text.replace("|", "\\|")
            .replace("\n", " ")
            .replace("\r", " ")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )


def render(payload: dict) -> str:
    redactor = Redactor(payload)
    lines = [
        "Read-only report. No machine, tailnet or policy settings changed.",
        "",
        "| Check | Location | Result | Safer shape | Docs |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in payload.get("rows", []):
        cells = []
        for field in ("check", "location", "result", "safer", "docs"):
            value = row.get(field, "")
            # Serve/Funnel are arbitrary nested private configuration. Share counts only.
            if isinstance(value, (dict, list)):
                value = (
                    "Configuration present; review forwarding warnings locally"
                    if value
                    else "No configuration returned"
                )
            cells.append(redactor.scrub(value))
        lines.append("| " + " | ".join(cells) + " |")
    lines.extend(["", "What to look at:", ""])
    lines.extend("- " + redactor.scrub(note) for note in payload.get("notes", []))
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
