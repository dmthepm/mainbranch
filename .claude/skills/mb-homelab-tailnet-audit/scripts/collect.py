#!/usr/bin/env python3
"""Collect local facts with fixed read-only argv; stdout is PRIVATE JSON."""

from __future__ import annotations

import json
import platform
import socket
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

ALLOWLIST = (
    ("tailscale", "version", "--json", "--upstream"),
    ("tailscale", "status", "--json"),
    ("tailscale", "debug", "prefs"),
    ("tailscale", "serve", "status", "--json"),
    ("tailscale", "funnel", "status", "--json"),
    ("tailscale", "lock", "status", "--json"),
)
ADMIN_PORTS = {22, 2375, 2376, 3389, 5432, 5900, 6379, 8006, 8080, 8443, 9000}


def run(argv: tuple[str, ...]) -> dict:
    if argv not in ALLOWLIST:
        raise ValueError("command refused: not in read-only allowlist")
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=20, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return {
            "status": "not checked",
            "reason": "command missing, unavailable or timed out",
        }
    if result.returncode:
        return {
            "status": "not checked",
            "reason": "command unsupported or permission denied",
        }
    try:
        return {"status": "checked", "data": json.loads(result.stdout)}
    except ValueError:
        return {"status": "not checked", "reason": "expected JSON was unavailable"}


def forwards(value: object) -> list[str]:
    warnings = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"Proxy", "TCPForward"} and isinstance(child, str):
                if "tailscaled" in child.lower() or child.startswith("unix:"):
                    warnings.append("Review a forward to a local daemon socket")
                    continue
                try:
                    target = urlsplit(child if "://" in child else "tcp://" + child)
                    if target.port in ADMIN_PORTS:
                        warnings.append("Review a forward to a possible admin port")
                except ValueError:
                    warnings.append("Review an unrecognized forwarding target")
            warnings.extend(forwards(child))
    elif isinstance(value, list):
        for child in value:
            warnings.extend(forwards(child))
    return sorted(set(warnings))


def openssh(proc: Path = Path("/proc")) -> str:
    """Read Linux procfs only; process visibility can prevent attribution."""
    try:
        inodes = set()
        for process in proc.iterdir():
            if not process.name.isdigit():
                continue
            try:
                if process.joinpath("comm").read_text().strip() != "sshd":
                    continue
                for fd in process.joinpath("fd").iterdir():
                    link = fd.readlink().as_posix()
                    if link.startswith("socket:["):
                        inodes.add(link[8:-1])
            except OSError:
                continue
        listeners = []
        for filename in ("tcp", "tcp6"):
            for line in proc.joinpath("net", filename).read_text().splitlines()[1:]:
                fields = line.split()
                if fields[3] == "0A" and fields[9] in inodes:
                    address, port = fields[1].split(":")
                    raw = bytes.fromhex(address)
                    raw = b"".join(raw[i : i + 4][::-1] for i in range(0, len(raw), 4))
                    interface = socket.inet_ntop(
                        socket.AF_INET if filename == "tcp" else socket.AF_INET6, raw
                    )
                    listeners.append(f"{interface}, TCP {int(port, 16)}")
        if listeners:
            return "OpenSSH listening: " + "; ".join(sorted(set(listeners)))
    except OSError:
        pass
    return "not checked: procfs cannot prove OpenSSH listener attribution with current permissions"


def collect() -> dict:
    results = {" ".join(argv[1:]): run(argv) for argv in ALLOWLIST}

    def data(key: str) -> dict:
        value = results[key].get("data")
        return value if isinstance(value, dict) else {}

    def reason(key: str) -> str:
        return "not checked: " + results[key].get("reason", "field unavailable on this build")

    def toggle(value: object, key: str) -> str:
        return ("on" if value else "off") if isinstance(value, bool) else reason(key)

    prefs = data("debug prefs")
    version = data("version --json --upstream")
    current = version.get("short", version.get("Short"))
    upstream = version.get("upstream")
    version_text = str(current) if isinstance(current, str) else reason("version --json --upstream")
    if isinstance(current, str) and isinstance(upstream, str):
        version_text += (
            "; current for track" if current == upstream else "; differs from current track release"
        )
    else:
        version_text += "; track currency not checked: upstream version unavailable"
    rows = [
        {"check": "Version and track", "result": version_text},
        {
            "check": "Tailscale SSH",
            "result": toggle(prefs.get("RunSSH"), "debug prefs"),
        },
        {
            "check": "Auto-update",
            "result": toggle(
                prefs.get("AutoUpdate", {}).get("Apply")
                if isinstance(prefs.get("AutoUpdate"), dict)
                else None,
                "debug prefs",
            ),
        },
        {
            "check": "Tailnet lock",
            "result": toggle(data("lock status --json").get("Enabled"), "lock status --json"),
        },
        {
            "check": "OpenSSH listeners",
            "result": openssh()
            if platform.system() == "Linux"
            else "not checked: no confirmed read-only listener command for this platform",
        },
    ]
    notes = []
    for feature in ("serve", "funnel"):
        key = f"{feature} status --json"
        value = results[key].get("data")
        rows.append(
            {
                "check": feature.title(),
                "result": value if value is not None else reason(key),
            }
        )
        notes.extend(forwards(value))
    if platform.system() == "Darwin":
        # Version metadata is a hint only. Never infer the running variant from PATH.
        long_version = str(version.get("long", version.get("Long", ""))).lower()
        variant = next(
            (
                label
                for token, label in (
                    ("macsys", "standalone"),
                    ("macapp", "App Store"),
                    ("-oss", "open-source tailscaled"),
                )
                if token in long_version
            ),
            None,
        )
        rows.append(
            {
                "check": "macOS build",
                "result": variant
                or "not checked: build metadata does not identify the installed variant",
            }
        )
    return {
        "kind": "machine",
        "identities": data("status --json"),
        "rows": rows,
        "notes": sorted(set(notes))
        + ["Review every not checked row locally; unknown does not mean off."],
    }


if __name__ == "__main__":
    json.dump(collect(), sys.stdout)
    print()
