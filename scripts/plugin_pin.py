#!/usr/bin/env python3
"""Pin the Claude Code plugin marketplace to one exact release commit.

Subcommands:
  pin TAG        write the marketplace source as an HTTPS url plus the full
                 sha of TAG's commit, after checking that commit declares
                 TAG's version
  check          fail when the marketplace is pinned wrongly (no-op for "./")
  candidate DEST export HEAD into DEST with the source reset to "./", so a
                 release smoke installs the candidate and not the old pin

Ordering rule for `check`: the pinned commit must declare one version in
plugin.json and marketplace metadata, and that version may equal the version in
this tree or be older. It may never be newer. A release commit bumps the
versions while the pin still names the previous release, so "older" must pass.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

PIN_URL = "https://github.com/dmthepm/mainbranch.git"
MARKETPLACE = ".claude-plugin/marketplace.json"
PLUGIN = ".claude-plugin/plugin.json"
SHA_RE = re.compile(r"[0-9a-f]{40}")
VERSION_RE = re.compile(r"\d+(\.\d+)*")


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise ValueError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def _declared_versions(root: Path, commit: str) -> tuple[str, str]:
    """Return (plugin.json version, marketplace metadata version) at a commit."""
    plugin = json.loads(_git(root, "show", f"{commit}:{PLUGIN}"))
    marketplace = json.loads(_git(root, "show", f"{commit}:{MARKETPLACE}"))
    return str(plugin.get("version")), str(marketplace.get("metadata", {}).get("version"))


def _plugin_entry(manifest: dict[str, Any]) -> dict[str, Any]:
    plugins = manifest.get("plugins")
    if not isinstance(plugins, list) or len(plugins) != 1 or not isinstance(plugins[0], dict):
        raise ValueError("marketplace.json must list exactly one plugin")
    return plugins[0]


def pin(root: Path, tag: str) -> str:
    """Write the pin for TAG; return the commit sha."""
    version = tag.removeprefix("oe-v").removeprefix("v")
    if not VERSION_RE.fullmatch(version):
        raise ValueError(f"cannot read a version from tag {tag!r}")
    commit = _git(root, "rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}").strip()
    if not SHA_RE.fullmatch(commit):
        raise ValueError(f"tag {tag} did not resolve to a full commit sha")
    plugin_version, marketplace_version = _declared_versions(root, commit)
    if plugin_version != version or marketplace_version != version:
        raise ValueError(
            f"commit {commit[:12]} declares plugin.json {plugin_version} and marketplace "
            f"{marketplace_version}, not {version}; refusing to pin"
        )
    path = root / MARKETPLACE
    manifest = json.loads(path.read_text(encoding="utf-8"))
    _plugin_entry(manifest)["source"] = {"source": "url", "url": PIN_URL, "sha": commit}
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return commit


def check(root: Path, *, offline: bool = False) -> list[str]:
    """Return problems with the marketplace pin; an empty list means fine."""
    manifest = json.loads((root / MARKETPLACE).read_text(encoding="utf-8"))
    source = _plugin_entry(manifest).get("source")
    if source == "./":
        return []
    if not isinstance(source, dict) or source.get("source") != "url":
        return [f"plugin source must be './' or a url pin, got {source!r}"]
    problems = []
    if source.get("url") != PIN_URL:
        problems.append(f"pin url must be {PIN_URL}, got {source.get('url')!r}")
    sha = source.get("sha")
    if not isinstance(sha, str) or not SHA_RE.fullmatch(sha):
        problems.append(f"pin sha must be a full 40-character lowercase sha, got {sha!r}")
    if problems or offline:
        return problems
    try:
        assert isinstance(sha, str)
        pinned = _declared_versions(root, sha)
    except ValueError as exc:
        return [f"cannot read the pinned commit {sha[:12]} here (fetch it or use --offline): {exc}"]
    if pinned[0] != pinned[1]:
        problems.append(
            f"pinned commit declares plugin.json {pinned[0]} but marketplace {pinned[1]}"
        )
    here = str(manifest.get("metadata", {}).get("version"))
    try:
        if _version_key(pinned[0]) > _version_key(here):
            problems.append(f"pinned commit declares {pinned[0]}, newer than this tree's {here}")
    except ValueError:
        problems.append(f"versions are not numeric: pinned {pinned[0]!r}, tree {here!r}")
    return problems


def candidate(root: Path, dest: Path) -> None:
    """Export HEAD into DEST with the plugin source reset to './'."""
    dest.mkdir(parents=True, exist_ok=True)
    if any(dest.iterdir()):
        raise ValueError(f"{dest} is not empty")
    with tempfile.NamedTemporaryFile(suffix=".tar") as archive:
        _git(root, "archive", "--format=tar", "-o", archive.name, "HEAD")
        subprocess.run(["tar", "-xf", archive.name, "-C", str(dest)], check=True)
    path = dest / MARKETPLACE
    manifest = json.loads(path.read_text(encoding="utf-8"))
    _plugin_entry(manifest)["source"] = "./"
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("pin").add_argument("tag")
    check_parser = sub.add_parser("check")
    check_parser.add_argument("--offline", action="store_true")
    sub.add_parser("candidate").add_argument("dest", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "pin":
            commit = pin(args.root, args.tag)
            print(f"pinned {MARKETPLACE} to {commit} ({args.tag})")
        elif args.command == "check":
            problems = check(args.root, offline=args.offline)
            for problem in problems:
                print(f"plugin-pin: {problem}", file=sys.stderr)
            if problems:
                return 1
            print("plugin-pin: OK")
        else:
            candidate(args.root, args.dest)
            print(f"candidate export with source './' written to {args.dest}")
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"plugin-pin: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
