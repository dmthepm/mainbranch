#!/usr/bin/env python3
"""Pin the Claude Code plugin marketplace to one exact release commit.

Subcommands:
  pin TAG        write the marketplace source as an HTTPS url plus the full
                 sha of TAG's commit, after checking that commit declares
                 TAG's version and is the commit the first-party remote's tag
                 names
  check          fail when the marketplace is pinned wrongly (no-op for "./")
  candidate DEST export a clean HEAD into DEST with the source reset to "./",
                 so a release smoke installs the candidate and not the old pin

Ordering rule for `check`: the pinned commit must declare one version in
plugin.json and marketplace metadata, and that version may equal the version in
this tree or be older. It may never be newer. A release commit bumps the
versions while the pin still names the previous release, so "older" must pass.

Provenance rule, in `pin` and in a full `check`: the pinned commit must be the
commit of the first-party tag oe-v<version>, read from the first-party remote
(never a local ref), and an ancestor of first-party main. These reads run in an
empty temporary repo with Git's environment and user config dropped, so nothing
in the working repo or on this machine's Git setup changes them. Versions are exactly
three numeric components. `--offline` skips the network and the pinned-commit
reads; it exists for the manifest unit tests only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

PIN_URL = "https://github.com/dmthepm/mainbranch.git"
MARKETPLACE = ".claude-plugin/marketplace.json"
PLUGIN = ".claude-plugin/plugin.json"
SHA_RE = re.compile(r"[0-9a-f]{40}")
VERSION_RE = re.compile(r"\d+\.\d+\.\d+")


def _git_env() -> dict[str, str]:
    """Drop Git's environment and user config, which could redirect the first-party URL."""
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull})
    return env


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=False,
        env=_git_env(),
    )
    if result.returncode != 0:
        raise ValueError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def _object(value: Any, what: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{what} must be a JSON object")  # noqa: TRY004
    return value


def _version_of(plugin_json: Any, marketplace_json: Any, where: str) -> tuple[str, str]:
    """Validate manifest shapes and return (plugin.json, marketplace metadata) versions."""
    plugin = _object(plugin_json, f"{PLUGIN} ({where})")
    marketplace = _object(marketplace_json, f"{MARKETPLACE} ({where})")
    metadata = _object(marketplace.get("metadata"), f"{MARKETPLACE} metadata ({where})")
    versions = (plugin.get("version"), metadata.get("version"))
    for label, value in zip((PLUGIN, f"{MARKETPLACE} metadata"), versions):
        if not isinstance(value, str) or not VERSION_RE.fullmatch(value):
            raise ValueError(
                f"{label} version ({where}) must be three numeric parts like 1.2.3, got {value!r}"
            )
    return versions  # type: ignore[return-value]


def _declared_versions(root: Path, commit: str) -> tuple[str, str]:
    """Return (plugin.json version, marketplace metadata version) at a commit."""
    return _version_of(
        json.loads(_git(root, "show", f"{commit}:{PLUGIN}")),
        json.loads(_git(root, "show", f"{commit}:{MARKETPLACE}")),
        f"commit {commit[:12]}",
    )


def _plugin_entry(manifest: Any) -> dict[str, Any]:
    plugins = _object(manifest, MARKETPLACE).get("plugins")
    if (
        not isinstance(plugins, list)
        or len(plugins) != 1
        or not isinstance(plugins[0], dict)
    ):
        raise ValueError("marketplace.json must list exactly one plugin")
    return plugins[0]


@contextmanager
def _first_party(remote: str) -> Iterator[Path]:
    """Yield an empty temp repo holding only first-party main.

    Nothing in the working repo is consulted, so its config, refs and tags
    can't change the answer.
    """
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)
        _git(repo, "init", "--quiet", "--bare")
        try:
            _git(repo, "fetch", "--quiet", "--no-tags", remote, "refs/heads/main")
        except ValueError as exc:
            raise ValueError(f"cannot fetch first-party main: {exc}") from exc
        yield repo


def _remote_tag_commit(repo: Path, tag: str, remote: str) -> str:
    """Return the commit the first-party remote's tag names (peeling annotated tags)."""
    ref = f"refs/tags/{tag}"
    try:
        out = _git(repo, "ls-remote", remote, ref, f"{ref}^{{}}")
    except ValueError as exc:
        raise ValueError(
            f"cannot reach the first-party remote to verify tag {tag}: {exc}"
        ) from exc
    refs = {}
    for line in out.splitlines():
        sha, _, name = line.partition("\t")
        refs[name] = sha
    commit = refs.get(f"{ref}^{{}}") or refs.get(ref)
    if not commit or not SHA_RE.fullmatch(commit):
        raise ValueError(f"tag {tag} does not exist on the first-party remote")
    return commit


def _verify_provenance(repo: Path, commit: str, version: str, remote: str) -> None:
    """Require COMMIT to be the first-party tag oe-v<version>'s commit and on main."""
    tag = f"oe-v{version}"
    tagged = _remote_tag_commit(repo, tag, remote)
    if tagged != commit:
        raise ValueError(
            f"commit {commit[:12]} is not the commit of first-party tag {tag} ({tagged[:12]})"
        )
    result = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", commit, "FETCH_HEAD"],
        capture_output=True,
        text=True,
        check=False,
        env=_git_env(),
    )
    if result.returncode != 0:
        raise ValueError(
            f"commit {commit[:12]} ({tag}) is not an ancestor of first-party main"
        )


def pin(root: Path, tag: str, *, remote: str = PIN_URL) -> str:
    """Write the pin for TAG; return the commit sha."""
    version = tag.removeprefix("oe-v").removeprefix("v")
    if not VERSION_RE.fullmatch(version):
        raise ValueError(f"cannot read a three-part version from tag {tag!r}")
    with _first_party(remote) as repo:
        # Provenance first: the first-party remote names the commit, not a local ref.
        commit = _remote_tag_commit(repo, f"oe-v{version}", remote)
        _verify_provenance(repo, commit, version, remote)
        plugin_version, marketplace_version = _declared_versions(repo, commit)
    if plugin_version != version or marketplace_version != version:
        raise ValueError(
            f"commit {commit[:12]} declares plugin.json {plugin_version} and marketplace "
            f"{marketplace_version}, not {version}; refusing to pin"
        )
    path = root / MARKETPLACE
    manifest = json.loads(path.read_text(encoding="utf-8"))
    _plugin_entry(manifest)["source"] = {"source": "url", "url": PIN_URL, "sha": commit}
    path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return commit


def check(root: Path, *, offline: bool = False, remote: str = PIN_URL) -> list[str]:
    """Return problems with the marketplace pin; an empty list means fine.

    Malformed manifests raise ValueError. REMOTE is a test seam: the CLI never
    exposes it, so a real check always verifies against the first-party URL.
    """
    manifest = json.loads((root / MARKETPLACE).read_text(encoding="utf-8"))
    source = _plugin_entry(manifest).get("source")
    here = _object(manifest.get("metadata"), f"{MARKETPLACE} metadata").get("version")
    if not isinstance(here, str) or not VERSION_RE.fullmatch(here):
        raise ValueError(
            f"{MARKETPLACE} metadata version must be three numeric parts like 1.2.3, got {here!r}"
        )
    if source == "./":
        return []
    if not isinstance(source, dict) or source.get("source") != "url":
        return [f"plugin source must be './' or a url pin, got {source!r}"]
    problems = []
    if source.get("url") != PIN_URL:
        problems.append(f"pin url must be {PIN_URL}, got {source.get('url')!r}")
    sha = source.get("sha")
    if not isinstance(sha, str) or not SHA_RE.fullmatch(sha):
        problems.append(
            f"pin sha must be a full 40-character lowercase sha, got {sha!r}"
        )
    if problems or offline:
        return problems
    assert isinstance(sha, str)
    try:
        with _first_party(remote) as repo:
            return _check_pinned(repo, sha, here, remote)
    except ValueError as exc:
        return [str(exc)]


def _check_pinned(repo: Path, sha: str, here: str, remote: str) -> list[str]:
    """Check a pinned commit against first-party history and this tree's version."""
    try:
        pinned = _declared_versions(repo, sha)
    except ValueError as exc:
        return [f"cannot read the pinned commit {sha[:12]} from first-party main: {exc}"]
    if pinned[0] != pinned[1]:
        return [f"pinned commit declares plugin.json {pinned[0]} but marketplace {pinned[1]}"]
    problems = []
    if _version_key(pinned[0]) > _version_key(here):
        problems.append(f"pinned commit declares {pinned[0]}, newer than this tree's {here}")
    try:
        _verify_provenance(repo, sha, pinned[0], remote)
    except ValueError as exc:
        problems.append(str(exc))
    return problems


def candidate(root: Path, dest: Path) -> str:
    """Export HEAD into DEST with the plugin source reset to './'; return HEAD's sha."""
    if _git(root, "status", "--porcelain", "--untracked-files=all").strip():
        raise ValueError(
            "working tree has uncommitted or untracked changes; commit them first "
            "(the export is HEAD, so a dirty tree would silently test older content)"
        )
    head = _git(root, "rev-parse", "HEAD").strip()
    dest.mkdir(parents=True, exist_ok=True)
    if any(dest.iterdir()):
        raise ValueError(f"{dest} is not empty")
    with tempfile.NamedTemporaryFile(suffix=".tar") as archive:
        _git(root, "archive", "--format=tar", "-o", archive.name, "HEAD")
        subprocess.run(["tar", "-xf", archive.name, "-C", str(dest)], check=True)
    path = dest / MARKETPLACE
    manifest = json.loads(path.read_text(encoding="utf-8"))
    _plugin_entry(manifest)["source"] = "./"
    path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return head


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
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
            head = candidate(args.root, args.dest)
            print(
                f"candidate export of HEAD {head} with source './' written to {args.dest}"
            )
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"plugin-pin: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
