"""Bounded, profile-local Codex rollout metadata. Discovery is a hint, never adoption."""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from mb.agent_store import Refusal

META_BYTES = 65_536


@dataclass(frozen=True)
class Rollout:
    sid: str
    cwd: str
    stamp: datetime
    path: str
    mtime: float


def timestamp(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp needs a string")
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        raise ValueError("timestamp needs a timezone")
    return stamp


def rollouts(profile: str, expect: tuple[int, int] | None, cap: int) -> list[Rollout]:
    """Scan at most cap entries, without following directory links or opening special files."""
    try:
        info = os.lstat(profile)
    except FileNotFoundError:
        if expect is None:
            return []
        raise Refusal(4, "search-incomplete", "recorded Codex profile is missing") from None
    except OSError:
        raise Refusal(4, "search-incomplete", "cannot read Codex profile") from None
    if not stat.S_ISDIR(info.st_mode) or (expect and expect != (info.st_dev, info.st_ino)):
        raise Refusal(4, "search-incomplete", "Codex profile changed")
    result: list[Rollout] = []
    count = 0
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC

    def walk(parent: int, name: str, path: str, depth: int = 0) -> None:
        nonlocal count
        if depth > 40:
            raise Refusal(4, "inconsistent", "Codex rollout directory depth exceeded")
        fd = os.open(name, flags | os.O_DIRECTORY, dir_fd=parent)
        try:
            with os.scandir(fd) as entries:
                for entry in entries:
                    count += 1
                    if count > cap:
                        raise Refusal(4, "inconsistent", "Codex rollout entry cap exceeded")
                    child = f"{path}/{entry.name}"
                    kind = entry.stat(follow_symlinks=False).st_mode
                    if stat.S_ISLNK(kind):
                        raise Refusal(4, "unsupported-format", "Codex rollout tree has a link")
                    if stat.S_ISDIR(kind):
                        walk(fd, entry.name, child, depth + 1)
                    elif entry.name.endswith(".jsonl"):
                        if not stat.S_ISREG(kind):
                            raise Refusal(4, "unsupported-format", "not a regular Codex rollout")
                        result.append(meta(fd, entry.name, child))
        finally:
            os.close(fd)

    def meta(parent: int, name: str, path: str) -> Rollout:
        fd = os.open(name, flags | os.O_NONBLOCK, dir_fd=parent)
        try:
            before = os.fstat(fd)
            if not stat.S_ISREG(before.st_mode):
                raise ValueError("not a regular rollout")
            with os.fdopen(fd, "rb", closefd=False) as handle:
                first = handle.readline(META_BYTES + 1)
            if len(first) > META_BYTES:
                raise ValueError("metadata too large")
            record = json.loads(first)
            payload = record["payload"]
            sid = payload["id"]
            if record["type"] != "session_meta" or not isinstance(sid, str):
                raise ValueError("not session metadata")
            if sid != payload["session_id"]:
                raise Refusal(4, "inconsistent", "Codex metadata id and session_id differ")
            # Local import keeps the UUID rule shared with the launcher's explicit-session parser.
            from mb.agent_up import UUID_RE

            if not UUID_RE.fullmatch(sid) or not isinstance(payload["cwd"], str):
                raise ValueError("invalid session metadata")
            stamp = timestamp(payload["timestamp"])
            after = os.fstat(fd)
            named = os.stat(name, dir_fd=parent, follow_symlinks=False)
            fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns")
            if any(getattr(before, k) != getattr(after, k) for k in fields) or any(
                getattr(before, k) != getattr(named, k) for k in fields
            ):
                raise Refusal(4, "transcript-changed", "Codex rollout changed while read")
            return Rollout(sid, payload["cwd"], stamp, path, before.st_mtime)
        except (ValueError, KeyError, TypeError):
            raise Refusal(4, "unsupported-format", "unsupported Codex session metadata") from None
        finally:
            os.close(fd)

    try:
        root = os.open(profile, flags | os.O_DIRECTORY)
        try:
            pinned = os.fstat(root)
            if (pinned.st_dev, pinned.st_ino) != (info.st_dev, info.st_ino):
                raise Refusal(4, "search-incomplete", "Codex profile changed while opening")
            try:
                os.stat("sessions", dir_fd=root, follow_symlinks=False)
            except FileNotFoundError:
                return []
            walk(root, "sessions", str(Path(profile) / "sessions"))
        finally:
            os.close(root)
    except OSError:
        raise Refusal(4, "search-incomplete", "cannot read Codex rollout tree") from None
    return result


def discover(last: dict[str, Any], cap: int) -> list[Rollout]:
    expected = last.get("profile_id")
    expect = tuple(expected) if isinstance(expected, list) else None
    rows = rollouts(str(last["profile_real"]), expect, cap)
    since = timestamp(str(last["utc"]))
    return [r for r in rows if r.cwd == last["cwd_real"] and r.stamp >= since]


def hints(rows: list[Rollout]) -> str:
    ids = sorted({r.sid for r in rows})
    return "discovered (not adopted): " + ", ".join(ids) if ids else ""
