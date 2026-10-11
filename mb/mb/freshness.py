"""Shared package freshness metadata and beginner-safe update copy."""

from __future__ import annotations

import json
import re
import shlex
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mb import __version__, topology
from mb.engine import install_mode, repo_flag

MINIMUM_SUPPORTED_VERSION = "0.2.0"
# `mb update` first shipped in the same release as the current support floor.
MB_UPDATE_AVAILABLE_VERSION = "0.2.0"
PYPI_PACKAGE_URL = "https://pypi.org/pypi/mainbranch/json"
GITHUB_RELEASE_URL_TEMPLATE = "https://github.com/noontide-co/mainbranch/releases/tag/oe-v{version}"
_LATEST_AUTO = object()
# Required-update command per install mode (#965). `mb update` reuses these, so
# both surfaces name the same command. `@latest` with `--refresh-package` is the
# uv form `mb update` runs (#963, #1008).
PIPX_UPDATE_COMMAND_TEXT = "pipx upgrade mainbranch"
UV_UPDATE_COMMAND_TEXT = "uv tool install --refresh-package mainbranch mainbranch@latest"
PIP_UPDATE_COMMAND_TEXT = "pip install --upgrade mainbranch"
REQUIRED_UPDATE_COMMANDS = {
    "pipx": PIPX_UPDATE_COMMAND_TEXT,
    "uv": UV_UPDATE_COMMAND_TEXT,
    "wheel": PIP_UPDATE_COMMAND_TEXT,
}
MODE_NEUTRAL_UPDATE_TEXT = (
    "Upgrade the mainbranch package with the tool that installed it (pipx, uv or pip)."
)
_PEP440_RE = re.compile(
    r"""^\s*v?
    (?:(?P<epoch>[0-9]+)!)?
    (?P<release>[0-9]+(?:\.[0-9]+)*)
    (?:[-_.]?(?P<pre_l>a|alpha|b|beta|c|rc|pre|preview)[-_.]?(?P<pre_n>[0-9]+)?)?
    (?P<post>-(?P<post_n1>[0-9]+)|[-_.]?(?:post|rev|r)[-_.]?(?P<post_n2>[0-9]+)?)?
    (?P<dev>[-_.]?dev[-_.]?(?P<dev_n>[0-9]+)?)?
    (?:\+(?P<local>[a-z0-9]+(?:[-_.][a-z0-9]+)*))?
    \s*$""",
    re.VERBOSE | re.IGNORECASE,
)
_PRE_RANK = {"a": 0, "alpha": 0, "b": 1, "beta": 1, "c": 2, "rc": 2, "pre": 2, "preview": 2}
# A release version as PyPI publishes it: 0.6.3, 0.6.3rc1, 0.6.3.post1, 0.7.0.dev2.
_RELEASE_VERSION_RE = re.compile(r"^\d+(\.\d+)*((a|b|rc)\d+)?(\.post\d+)?(\.dev\d+)?$")


def version_key(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for piece in version.split("."):
        digits = ""
        for char in piece:
            if not char.isdigit():
                break
            digits += char
        parts.append(int(digits or "0"))
    return tuple(parts)


def _pep440_key(version: str) -> tuple[Any, ...]:
    """Sort key following PEP 440 ordering for the forms Main Branch publishes.

    `version_key` drops pre-release and dev markers, so `0.6.3rc1` and `0.6.3`
    compare equal. This one orders dev < pre-release < final < post, the way
    pip and uv do, without adding `packaging` as a runtime dependency.
    """
    match = _PEP440_RE.match(version)
    if match is None:
        return (0, version_key(version), (3, 0), -1, float("inf"), 0)
    release = [int(part) for part in match.group("release").split(".")]
    while len(release) > 1 and release[-1] == 0:
        release.pop()
    pre_l = match.group("pre_l")
    post = match.group("post_n1") or match.group("post_n2")
    has_post = match.group("post") is not None
    has_dev = match.group("dev") is not None
    if pre_l:
        pre: tuple[int, int] = (_PRE_RANK[pre_l.lower()], int(match.group("pre_n") or 0))
    elif has_dev and not has_post:
        pre = (-1, 0)
    else:
        pre = (3, 0)
    return (
        int(match.group("epoch") or 0),
        tuple(release),
        pre,
        int(post or 0) if has_post else -1,
        int(match.group("dev_n") or 0) if has_dev else float("inf"),
        1 if match.group("local") else 0,
    )


def checked_release_version(version: Any) -> str | None:
    """``version`` stripped when it reads as a published release version, else None.

    `compare_versions` cannot order text it does not recognise, so callers pass
    PyPI's answer through this first and treat None as "latest unknown" (#1028).
    """
    text = version.strip() if isinstance(version, str) else ""
    return text if _RELEASE_VERSION_RE.fullmatch(text) else None


def compare_versions(left: str, right: str) -> int:
    """Return -1, 0 or 1 as ``left`` is older than, equal to or newer than ``right``.

    Both sides should be release versions (see `checked_release_version`); an
    unparseable one sorts below every release, which is not a meaningful answer.
    """
    left_key = _pep440_key(left)
    right_key = _pep440_key(right)
    return (left_key > right_key) - (left_key < right_key)


def latest_pypi_version(timeout: float = 3.0) -> str | None:
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(PYPI_PACKAGE_URL, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        # Valid JSON that is not an object (a list, null, a number or a string)
        # carries no version; treat it as unknown, never as a traceback (#1039).
        return None
    info = data.get("info", {})
    version = info.get("version") if isinstance(info, dict) else None
    return version if isinstance(version, str) and version else None


def release_notes_url(version: str) -> str:
    version = version.strip()
    return GITHUB_RELEASE_URL_TEMPLATE.format(version=version) if version else ""


def looks_like_business_repo(repo: Path) -> bool:
    """True when ``repo`` is a hub business repo (see ``topology.classify_repo``)."""
    return topology.classify_repo(repo)["kind"] == "hub"


def _post_update_commands(repo: str | Path | None) -> list[str]:
    flag = repo_flag(repo)
    path = f" {shlex.quote(str(Path(repo).expanduser().resolve()))}" if flag and repo else ""
    return [f"mb skill link{flag or ' --repo .'}", f"mb doctor{path}"]


def package_update_status(
    repo: str | Path | None = None,
    *,
    installed_version: str = __version__,
    latest_version: Any = _LATEST_AUTO,
    minimum_supported: str = MINIMUM_SUPPORTED_VERSION,
    mode: str | None = None,
) -> dict[str, Any]:
    """Return stable update metadata for CLI JSON and skill consumers."""
    mode = install_mode() if mode is None else mode
    latest = (
        latest_pypi_version()
        if latest_version is _LATEST_AUTO and mode not in {"clone", "source"}
        else latest_version
    )
    checked_at = (
        datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    )
    latest_source = "not_applicable" if mode in {"clone", "source"} else "provided"
    if latest_version is _LATEST_AUTO and mode not in {"clone", "source"}:
        latest_source = "pypi_json" if latest else "unavailable"
    if latest is _LATEST_AUTO:
        latest = None
    # An answer that is not a release version cannot be ordered, so it counts
    # as unknown rather than as older or newer than the install (#1028).
    latest_text = checked_release_version(latest) or ""
    latest_unreadable = isinstance(latest, str) and bool(latest.strip()) and not latest_text
    if latest_unreadable and latest_source == "pypi_json":
        latest_source = "unavailable"

    installed_key = version_key(installed_version)
    minimum_key = version_key(minimum_supported)

    severity = "current"
    command = ""
    reason = "Installed version is supported."

    if mode in {"clone", "source"}:
        reason = f"Package freshness does not apply in {mode} mode."
    elif installed_key < minimum_key:
        severity = "required"
        command = REQUIRED_UPDATE_COMMANDS.get(mode, "")
        if installed_key < version_key(MB_UPDATE_AVAILABLE_VERSION):
            reason = "Installed version predates mb update and the current skill-link repair flow."
        else:
            reason = "Installed version is below the minimum supported Main Branch version."
    elif latest_text and compare_versions(latest_text, installed_version) > 0:
        severity = "recommended"
        command = "mb update"
        reason = "A newer compatible Main Branch package is available."
    elif latest_unreadable or (latest_version is _LATEST_AUTO and not latest_text):
        severity = "unknown"
        reason = "Could not check PyPI for the latest Main Branch version."
    elif latest_text:
        reason = "Installed version is current."

    return {
        "installed": installed_version,
        "install_mode": mode,
        "latest": latest_text,
        "minimum_supported": minimum_supported,
        "severity": severity,
        "command": command,
        "update_check_command": "mb update --check --json"
        if mode not in {"clone", "source"}
        else "",
        "post_update_commands": _post_update_commands(repo),
        "reason": reason,
        "latest_source": latest_source,
        "checked_at": checked_at,
        "release_notes_url": release_notes_url(latest_text) if latest_text else "",
    }


def format_update_alert(update: dict[str, Any]) -> str:
    """Render the shared update object as direct beginner-safe terminal copy."""
    severity = str(update.get("severity", ""))
    if severity not in {"required", "recommended"}:
        return ""

    command = str(update.get("command") or "")
    post_update = [str(cmd) for cmd in update.get("post_update_commands", [])]
    installed = str(update.get("installed") or "")
    minimum_supported = str(update.get("minimum_supported") or "")

    if severity == "required":
        lines = [
            "Update required.",
            "",
            "Your Main Branch install is old enough that setup and skills may not work correctly.",
            "",
        ]
        lines.extend(["Run this first:", f"  {command}"] if command else [MODE_NEUTRAL_UPDATE_TEXT])
        if installed and version_key(installed) < version_key(MB_UPDATE_AVAILABLE_VERSION):
            first_update = (
                "this first update must use pipx"
                if command == PIPX_UPDATE_COMMAND_TEXT
                else "this first update must use the command above"
                if command
                else "this first update must use your installer"
            )
            lines.extend(["", f"mb update is not available in {installed}; {first_update}."])
    else:
        lines = [
            "Update recommended.",
            "",
            "A newer Main Branch version is available. Your install is still supported.",
            "",
            "Run:",
            f"  {command}",
        ]

    if post_update:
        lines.extend(["", "Then, from your business repo:"])
        lines.extend(f"  {cmd}" for cmd in post_update)
    elif severity == "required" and minimum_supported:
        lines.extend(["", f"Minimum supported version: {minimum_supported}."])

    return "\n".join(lines)
