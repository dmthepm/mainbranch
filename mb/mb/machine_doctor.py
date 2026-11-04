"""Read-only machine checks. Registry entries own every probe and output field."""

from __future__ import annotations

import configparser
import json
import os
import platform
import pwd
import re
import shlex
import stat
import time
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal, get_args

from mb import machine_manifest as manifest_loader
from mb import machine_probe as probe

State = Literal["pass", "fail", "warn", "not_verified", "attested", "skipped", "not_applicable"]
Reason = Literal[
    "needs_root",
    "platform_unsupported",
    "platform_partial",
    "ambiguous_platform",
    "ambiguous_config",
    "probe_missing",
    "probe_timeout",
    "probe_error",
    "untrusted_executable",
    "owner_attested",
    "attestation_missing",
    "attestation_stale",
    "other_account",
    "no_manifest",
    "caller_selected_policy",
    "skipped_by_manifest",
    "advanced_pending",
    "no_section",
    "reboot_pending",
    "desktop_absent",
    "location_unknown",
    "not_checked",
]
REASONS = frozenset(get_args(Reason))
STATES: tuple[State, ...] = (
    "pass",
    "fail",
    "warn",
    "not_verified",
    "attested",
    "skipped",
    "not_applicable",
)
WORST = {
    state: rank
    for rank, state in enumerate(
        ("not_applicable", "pass", "warn", "skipped", "attested", "not_verified", "fail")
    )
}


@dataclass(frozen=True)
class ReadResult:
    name: str
    state: State
    observed: dict[str, bool | int | str]
    reason: Reason | None = None

    def __post_init__(self) -> None:
        if self.state not in STATES or self.reason not in REASONS | {None}:
            raise ValueError("Unknown result state or reason")
        if (self.reason is None) != (self.state in {"pass", "fail"}):
            raise ValueError("Non-verdict states require a coded reason")


@dataclass(frozen=True)
class CheckSpec:
    id: str
    section: str
    run: Callable[[float], list[ReadResult]]
    does_not_prove: str | None = None
    source: str = "pack"
    tier: Literal["baseline", "advanced"] = "baseline"
    run_as: str = "any"
    severity: str = "fail"
    platforms: tuple[str, ...] = ("ubuntu", "omarchy")
    fix_text: str | None = None


def check_result(spec: CheckSpec, reads: list[ReadResult]) -> dict[str, Any]:
    if not reads:
        raise ValueError("A running check must report its reads")
    worst = max(reads, key=lambda read: WORST[read.state])
    return {
        "id": spec.id,
        "source": spec.source,
        "tier": spec.tier,
        "as": spec.run_as,
        "section": spec.section,
        "subject": "self",
        "state": worst.state,
        "severity": spec.severity,
        "reads": [asdict(read) for read in reads],
        "reason": worst.reason,
        "does_not_prove": spec.does_not_prove,
        "fix": (
            {"display_only": True, "run_as": "owner", "argv": None, "text": spec.fix_text}
            if spec.fix_text
            else None
        ),
    }


def exit_code(checks: Sequence[dict[str, Any]], *, error: bool = False) -> int:
    if error:
        return 2
    if any(check["state"] == "fail" for check in checks):
        return 1
    if any(
        check["tier"] == "baseline" and check["state"] in {"not_verified", "attested", "skipped"}
        for check in checks
    ):
        return 3
    return 0


def detect_platform(deadline: float) -> tuple[dict[str, Any], list[ReadResult]]:
    if platform.system() == "Darwin":
        version = probe.run_probe(
            "macos", ("/usr/bin/sw_vers", "-productVersion"), deadline=deadline
        )
        if version.reason or version.returncode != 0 or not version.data.strip():
            reason: Reason = version.reason or "probe_error"
            return {"id": "unsupported", "family": None, "signals": {}}, [
                ReadResult("sw_vers", "not_verified", {}, reason)
            ]
        return {"id": "macos", "family": "darwin", "signals": {}}, [
            ReadResult("os_release", "not_verified", {}, "platform_partial")
        ]
    if platform.system() != "Linux":
        return {"id": "unsupported", "family": None, "signals": {}}, [
            ReadResult("os_release", "not_verified", {}, "platform_unsupported")
        ]
    result = probe.read_file(Path("/etc/os-release"), prefix=Path("/etc"))
    if result.reason == "ambiguous_config":
        result = probe.read_file(Path("/usr/lib/os-release"), prefix=Path("/usr/lib"))
    if result.reason:
        return {"id": "unsupported", "family": None, "signals": {}}, [
            ReadResult("os_release", "not_verified", {}, result.reason)
        ]
    try:
        fields = {}
        for line in result.data.decode("utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                key, value = line.split("=", 1)
                tokens = shlex.split(value, comments=False)
                if len(tokens) != 1 or key in fields:
                    raise ValueError
                fields[key] = tokens[0]
    except (UnicodeError, ValueError):
        return {"id": "unsupported", "family": None, "signals": {}}, [
            ReadResult("os_release", "not_verified", {}, "ambiguous_config")
        ]
    if fields.get("ID") == "ubuntu":
        lts = "LTS" in fields.get("VERSION", "")
        return {"id": "ubuntu", "family": "ubuntu", "signals": {"os_release_id": "ubuntu"}}, [
            ReadResult("os_release", "pass" if lts else "fail", {"lts": lts})
        ]
    package = probe.run_probe("omarchy", ("/usr/bin/pacman", "-Q", "omarchy"), deadline=deadline)
    identified = fields.get("ID") == "omarchy"
    installed = package.reason is None and package.returncode == 0
    signals = {"os_release_id": "omarchy" if identified else "other", "pacman_package": installed}
    if identified and installed:
        return {"id": "omarchy", "family": "arch", "distribution": "omarchy", "signals": signals}, [
            ReadResult("os_release", "pass", {"id_matches": True}),
            ReadResult("pacman_package", "pass", {"installed": True}),
        ]
    reason = "ambiguous_platform" if identified or installed else "platform_unsupported"
    return {"id": "unsupported", "family": None, "signals": signals}, [
        ReadResult("os_release", "not_verified", {"id_matches": identified}, reason),
        ReadResult(
            "pacman_package", "not_verified", {"installed": installed}, package.reason or reason
        ),
    ]


def _current_account() -> str | None:
    """Name of the effective-uid account; never from LOGNAME, USER or any caller-set variable."""
    try:
        return pwd.getpwuid(os.geteuid()).pw_name
    except (KeyError, OSError):
        return None


def _unknown(name: str, reason: Reason = "ambiguous_config") -> ReadResult:
    return ReadResult(name, "not_verified", {}, reason)


def _verdict(name: str, good: bool, **observed: bool | int | str) -> ReadResult:
    return ReadResult(name, "pass" if good else "fail", observed)


def _text(path: Path, prefix: Path) -> tuple[str, Reason | None]:
    result = probe.read_file(path, prefix=prefix)
    if result.reason:
        return "", result.reason
    try:
        return result.data.decode("utf-8"), None
    except UnicodeError:
        return "", "ambiguous_config"


def no_sleep(os_id: probe.Platform, deadline: float) -> list[ReadResult]:
    reads = []
    for target in ("sleep", "suspend", "hibernate"):
        result = probe.run_probe(
            os_id, ("/usr/bin/systemctl", "is-enabled", target + ".target"), deadline=deadline
        )
        name = target + "_masked"
        if result.reason:
            reads.append(_unknown(name, result.reason))
        elif result.data.strip() in {
            b"masked",
            b"enabled",
            b"disabled",
            b"static",
            b"indirect",
            b"alias",
        }:
            reads.append(
                _verdict(
                    name, result.data.strip() == b"masked", masked=result.data.strip() == b"masked"
                )
            )
        else:
            reads.append(_unknown(name))
    return reads


def desktop_ubuntu(deadline: float) -> list[ReadResult]:
    text, reason = _text(Path("/etc/gdm3/custom.conf"), Path("/etc/gdm3"))
    if reason == "probe_missing":
        package = probe.run_probe(
            "ubuntu", ("/usr/bin/dpkg-query", "-W", "-f=${Status}", "gdm3"), deadline=deadline
        )
        if package.reason:
            return [_unknown("automatic_login", package.reason)]
        absent = (package.returncode == 1 and not package.data.strip()) or (
            package.returncode == 0
            and package.data.strip() in {b"deinstall ok config-files", b"unknown ok not-installed"}
        )
        if absent:
            return [
                ReadResult(
                    "automatic_login", "not_applicable", {"gdm_installed": False}, "desktop_absent"
                )
            ]
    if reason:
        return [_unknown("automatic_login", reason)]
    config = configparser.ConfigParser(interpolation=None)
    try:
        config.read_string(text)
        if not config.has_section("daemon"):
            return [_unknown("automatic_login")]
        value = config.get("daemon", "AutomaticLoginEnable", fallback="false").lower()
    except (configparser.Error, KeyError):
        return [_unknown("automatic_login")]
    if value not in {"true", "false"}:
        return [_unknown("automatic_login")]
    enabled = value == "true"
    return [_verdict("automatic_login", not enabled, enabled=enabled)]


def _config_files(pattern: str) -> tuple[list[Path], Reason | None]:
    try:
        if pattern == "ssh/sshd_config.d/*.conf":
            directory = Path("/etc/ssh/sshd_config.d")
            if not stat.S_ISDIR(directory.lstat().st_mode):
                return [], "ambiguous_config"
            with os.scandir(directory) as entries:
                return sorted(
                    directory / entry.name for entry in entries if entry.name.endswith(".conf")
                ), None
        return sorted(Path("/etc").glob(pattern)), None
    except OSError:
        return [], "probe_error"


def desktop_arch(_: float) -> list[ReadResult]:
    reads = []
    for name, pattern in (
        ("sddm_autologin", "sddm.conf.d/*.conf"),
        ("getty_autologin", "systemd/system/getty@*.service.d/*.conf"),
    ):
        paths, reason = _config_files(pattern)
        if reason or not paths:
            reads.append(_unknown(name, reason or "probe_missing"))
            continue
        enabled = False
        for path in paths:
            text, reason = _text(path, Path("/etc"))
            if reason:
                break
            section = ""
            for line in text.splitlines():
                line = line.strip()
                if line.startswith(("#", ";")):
                    continue
                if line.startswith("["):
                    section = line.lower()
                if (
                    name == "sddm_autologin"
                    and section == "[autologin]"
                    and re.match(r"User\s*=\s*[^\s#;]", line)
                ):
                    enabled = True
                if name == "getty_autologin" and "--autologin" in line:
                    enabled = True
        reads.append(
            _unknown(name, reason) if reason else _verdict(name, not enabled, enabled=enabled)
        )
    return reads


def sshd_keys(_: float) -> list[ReadResult]:
    values: dict[str, str] = {}

    def parse(path: Path, *, included: bool = False) -> Reason | None:
        text, reason = _text(path, Path("/etc/ssh"))
        if reason:
            return reason
        for line in text.splitlines():
            try:
                tokens = shlex.split(line, comments=True)
            except ValueError:
                return "ambiguous_config"
            if not tokens:
                continue
            key = tokens[0].lower()
            if key == "match":
                return "ambiguous_config"
            if key == "include":
                if included or tokens[1:] != ["/etc/ssh/sshd_config.d/*.conf"]:
                    return "ambiguous_config"
                paths, reason = _config_files("ssh/sshd_config.d/*.conf")
                if reason:
                    return reason
                for child in sorted(paths):
                    reason = parse(child, included=True)
                    if reason:
                        return reason
            if key in {
                "passwordauthentication",
                "kbdinteractiveauthentication",
                "pubkeyauthentication",
                "challengeresponseauthentication",
            }:
                if len(tokens) != 2 or tokens[1].lower() not in {"yes", "no"}:
                    return "ambiguous_config"
                # ChallengeResponseAuthentication is an alias for the same setting.
                if key == "challengeresponseauthentication":
                    key = "kbdinteractiveauthentication"
                values.setdefault(key, tokens[1].lower())
        return None

    reason = parse(Path("/etc/ssh/sshd_config"))
    if reason:
        return [_unknown("sshd_authentication", reason)]
    good = (
        values.get("passwordauthentication") == "no"
        and values.get(
            "kbdinteractiveauthentication", values.get("challengeresponseauthentication")
        )
        == "no"
        and values.get("pubkeyauthentication") == "yes"
    )
    return [
        _verdict(
            "sshd_authentication",
            good,
            password_off=values.get("passwordauthentication") == "no",
            keyboard_interactive_off=values.get(
                "kbdinteractiveauthentication", values.get("challengeresponseauthentication")
            )
            == "no",
            pubkey_on=values.get("pubkeyauthentication") == "yes",
        )
    ]


def tailscale_no_ssh(os_id: probe.Platform, deadline: float) -> list[ReadResult]:
    result = probe.run_probe(os_id, ("/usr/bin/tailscale", "debug", "prefs"), deadline=deadline)
    if result.reason or result.returncode != 0:
        return [_unknown("run_ssh", result.reason or "probe_error")]
    try:
        value = json.loads(result.data)["RunSSH"]
        if not isinstance(value, bool):
            raise ValueError
    except (ValueError, KeyError, TypeError):
        return [_unknown("run_ssh")]
    return [_verdict("run_ssh", not value, enabled=value)]


def reboot_pending(arch: bool) -> list[ReadResult]:
    path = Path("/usr/lib/modules") / platform.release() if arch else Path("/run/reboot-required")
    try:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode):
            return [_unknown("reboot_pending")]
        if arch and not stat.S_ISDIR(info.st_mode):
            return [_unknown("reboot_pending")]
        if not arch and not stat.S_ISREG(info.st_mode):
            return [_unknown("reboot_pending")]
        pending = not arch
    except FileNotFoundError:
        pending = arch
    except OSError:
        return [_unknown("reboot_pending", "probe_error")]
    return [
        ReadResult("reboot_pending", "warn", {"pending": True}, "reboot_pending")
        if pending
        else _verdict("reboot_pending", True, pending=False)
    ]


def _security_origin(origin: str) -> bool:
    def supported(identity: str, pocket: str) -> bool:
        suffixes = {
            "Ubuntu": "-security",
            "UbuntuESM": "-infra-security",
            "UbuntuESMApps": "-apps-security",
            "${distro_id}": "-security",
            "${distro_id}ESM": "-infra-security",
            "${distro_id}ESMApps": "-apps-security",
        }
        suffix = suffixes.get(identity)
        if suffix is None:
            return False
        release = pocket.removesuffix(suffix)
        return pocket.endswith(suffix) and (
            release == "${distro_codename}" or bool(re.fullmatch(r"[a-z]+", release))
        )

    # Allowed-Origins uses origin:archive. Origins-Pattern uses named selectors.
    if "=" not in origin:
        parts = origin.split(":")
        return len(parts) == 2 and supported(parts[0], parts[1])
    selectors: dict[str, str] = {}
    aliases = {
        "o": "origin",
        "a": "archive",
        "suite": "archive",
        "n": "codename",
        "l": "label",
        "c": "component",
        "site": "site",
    }
    for item in origin.split(","):
        pair = item.strip().split("=", 1)
        if len(pair) != 2 or not pair[1]:
            return False
        key = aliases.get(pair[0], pair[0])
        if (
            key not in {"origin", "archive", "codename", "label", "component", "site"}
            or key in selectors
        ):
            return False
        selectors[key] = pair[1]
    # A codename alone identifies a release, not its update pocket.
    pocket = selectors.get("archive", "")
    return supported(selectors.get("origin", ""), pocket)


def unattended(deadline: float) -> list[ReadResult]:
    reads = []
    package = probe.run_probe(
        "ubuntu",
        ("/usr/bin/dpkg-query", "-W", "-f=${Status}", "unattended-upgrades"),
        deadline=deadline,
    )
    reads.append(
        _unknown("package_installed", package.reason)
        if package.reason
        else _verdict(
            "package_installed",
            package.returncode == 0 and package.data.strip() == b"install ok installed",
            installed=package.returncode == 0 and package.data.strip() == b"install ok installed",
        )
    )
    # apt-config applies all apt fragment ordering and overrides without changing it.
    config = probe.run_probe("ubuntu", ("/usr/bin/apt-config", "dump"), deadline=deadline)
    if config.reason or config.returncode != 0:
        reads.append(_unknown("security_only_config", config.reason or "probe_error"))
    else:
        try:
            text = config.data.decode("utf-8")
            enabled = 'APT::Periodic::Unattended-Upgrade "1";' in text
            reboot_off = 'Unattended-Upgrade::Automatic-Reboot "false";' in text
            origins = re.findall(
                r'^Unattended-Upgrade::(?:Allowed-Origins|Origins-Pattern):: "([^"\n]+)";',
                text,
                re.M,
            )
            security_only = bool(origins) and all(_security_origin(origin) for origin in origins)
            reads.append(
                _unknown("security_only_config", "ambiguous_config")
                if origins and not security_only
                else _verdict(
                    "security_only_config",
                    enabled and reboot_off and security_only,
                    enabled=enabled,
                    automatic_reboot_off=reboot_off,
                    security_only=security_only,
                )
            )
        except UnicodeError:
            reads.append(_unknown("security_only_config"))
    timer = probe.run_probe(
        "ubuntu", ("/usr/bin/systemctl", "is-enabled", "apt-daily-upgrade.timer"), deadline=deadline
    )
    reads.append(
        _unknown("upgrade_timer", timer.reason or "probe_error")
        if timer.reason or timer.returncode not in {0, 1}
        else _verdict(
            "upgrade_timer",
            timer.data.strip() == b"enabled",
            enabled=timer.data.strip() == b"enabled",
        )
    )
    return reads


def credential_store(_: float) -> list[ReadResult]:
    # Existing backend health adapters require a child process or read stored
    # values. Neither is a bounded, in-process metadata read for doctor.
    return [_unknown("store_available", "probe_missing")]


def registry(os_id: str, *, include_policy: bool = False) -> tuple[CheckSpec, ...]:
    if os_id not in {"ubuntu", "omarchy"}:
        return ()
    linux: probe.Platform = "ubuntu" if os_id == "ubuntu" else "omarchy"
    specs = (
        CheckSpec(
            "host.no-sleep",
            "docs/machine-setup.md#the-box-works-the-laptop-is-a-remote-control",
            lambda deadline: no_sleep(linux, deadline),
        ),
        CheckSpec(
            "host.desktop-no-autologin",
            "docs/machine-setup.md#omarchy-arch-based",
            desktop_ubuntu,
            platforms=("ubuntu",),
        ),
        CheckSpec(
            "host.desktop-no-autologin-arch",
            "docs/machine-setup.md#omarchy-arch-based",
            desktop_arch,
            platforms=("omarchy",),
        ),
        CheckSpec(
            "remote_access.sshd-keys-only",
            "docs/machine-setup.md#managing-it-from-a-mac",
            sshd_keys,
        ),
        CheckSpec(
            "remote_access.tailscale-no-ssh",
            "docs/machine-setup.md#managing-it-from-a-mac",
            lambda deadline: tailscale_no_ssh(linux, deadline),
        ),
        CheckSpec(
            "hardening.reboot-pending",
            "docs/machine-setup.md#backups-and-updates",
            lambda _: reboot_pending(False),
            platforms=("ubuntu",),
            severity="warn",
        ),
        CheckSpec(
            "hardening.reboot-pending-arch",
            "docs/machine-setup.md#omarchy-arch-based",
            lambda _: reboot_pending(True),
            "A systemd or glibc update since boot.",
            platforms=("omarchy",),
            severity="warn",
        ),
        CheckSpec(
            "hardening.unattended-security-only",
            "docs/machine-setup.md#backups-and-updates",
            unattended,
            platforms=("ubuntu",),
        ),
        CheckSpec(
            "credentials.store-available",
            "docs/machine-setup.md#credentials",
            credential_store,
            "Availability without a desktop session unless this run is headless.",
            source="engine",
            run_as="each-business",
        ),
        CheckSpec(
            "manifest.integrity",
            "docs/machine-setup.md#admin-account-and-agent-accounts",
            lambda _: [_unknown("manifest", "no_manifest")],
            source="engine",
        ),
    )
    return tuple(spec for spec in specs if os_id in spec.platforms) + (
        (*ACCOUNT_SPECS, *TOOL_SPECS, *LINUX_SPECS) if include_policy else ()
    )


ACCOUNT_SPECS = tuple(
    CheckSpec(
        check_id,
        "docs/machine-setup.md#" + anchor,
        lambda _: [_unknown("manifest", "no_manifest")],
        limitation,
        run_as=role,
        source=source,
        fix_text="Review password-required sudo and business run-as rules as the owner."
        if role == "owner-attests"
        else None,
    )
    for check_id, anchor, role, source, limitation in (
        ("owner.sudo-needs-password", "admin-account-and-agent-accounts", "owner", "pack", None),
        (
            "owner.no-sudo-into-business",
            "admin-account-and-agent-accounts",
            "owner-attests",
            "pack",
            "Root can still become any user; the admin stays trusted.",
        ),
        ("businesses.users-and-homes", "one-user-account-per-business", "any", "pack", None),
        (
            "businesses.no-privileged-groups",
            "admin-account-and-agent-accounts",
            "any",
            "pack",
            "A sudoers user rule, which requires root to read.",
        ),
        ("businesses.private-tmpdir", "shared-tools-private-data", "each-business", "pack", None),
        ("businesses.slice-limits", "sessions-that-survive-a-reboot", "any", "pack", None),
        ("sessions.linger", "sessions-that-survive-a-reboot", "any", "engine", None),
        ("runtime.herdr-per-user", "sessions-that-survive-a-reboot", "each-business", "pack", None),
        (
            "sessions.started-without-login",
            "part-4-first-week",
            "each-business",
            "engine",
            "The first login this boot is not retained by this bounded probe; "
            "complete the reboot test.",
        ),
        ("runtime.claude-autoupdate-off", "backups-and-updates", "each-business", "pack", None),
    )
)


TOOL_SPECS = tuple(
    CheckSpec(
        check_id,
        "docs/machine-setup.md#" + anchor,
        lambda _: [_unknown("manifest", "no_manifest")],
        limitation,
        run_as=role,
        fix_text=fix,
    )
    for check_id, anchor, role, limitation, fix in (
        ("shared_tools.root-owned-readonly", "shared-tools-private-data", "any", None, None),
        (
            "shared_tools.pins-match",
            "shared-tools-private-data",
            "any",
            "Tarball checksums are not recomputed. "
            "Install directories do not prove binary contents.",
            None,
        ),
        (
            "shared_tools.path-order",
            "shared-tools-private-data",
            "each-business",
            "The PATH of services not started from this shell.",
            None,
        ),
        (
            "heavy_work.lock",
            "one-heavy-job-at-a-time",
            "any + each-business",
            "That every heavy job actually takes the lock.",
            None,
        ),
        (
            "heavy_work.capped-run",
            "one-heavy-job-at-a-time",
            "any",
            "Whether the wrapper refuses an uncapped job; doctor never executes it.",
            None,
        ),
        (
            "backups.fresh",
            "backups-and-updates",
            "owner-attests",
            "Snapshot contents and restorability on the off-box backup host.",
            "Check the backup host and record the last successful backup date.",
        ),
        (
            "backups.restore-tested",
            "backups-and-updates",
            "owner",
            None,
            "Restore a home into a scratch account and record the date and result.",
        ),
    )
)


def _metadata(path: Path, prefix: Path) -> tuple[os.stat_result | None, Reason | None]:
    """Inspect metadata through pinned parents, rejecting every symlink."""
    if not path.is_absolute() or ".." in path.parts or not path.is_relative_to(prefix):
        return None, "ambiguous_config"
    descriptor = None
    try:
        descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
        for component in path.parts[1:-1]:
            child = os.open(
                component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor
            )
            os.close(descriptor)
            descriptor = child
        info = os.stat(path.name, dir_fd=descriptor, follow_symlinks=False)
        if stat.S_ISLNK(info.st_mode):
            return None, "ambiguous_config"
        return info, None
    except FileNotFoundError:
        return None, "probe_missing"
    except OSError:
        return None, "probe_error"
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _tool_metadata(name: str, path: Path, root: Path, directory: bool = False) -> ReadResult:
    info, error = _metadata(path, root)
    if error or info is None:
        return _unknown(name, error or "probe_error")
    correct_type = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    good = correct_type and info.st_uid == 0 and info.st_gid == 0 and not info.st_mode & 0o022
    return _verdict(
        name,
        good,
        root_owned=info.st_uid == 0 and info.st_gid == 0,
        readonly=not bool(info.st_mode & 0o022),
        correct_type=correct_type,
    )


def _install_base(root: Path, policy: dict[str, Any]) -> Path:
    """Where pinned versions live: mise keeps them in its data folder, ``<tool_root>/mise``."""
    if policy["shared_tools"].get("version_manager") == "mise":
        return root / "mise" / "installs"
    return root / "installs"


def _tool_bin(
    name: str, path: Path, root: Path, tool: dict[str, Any], installs: Path | None = None
) -> ReadResult:
    info, error = _metadata(path, root)
    if info is not None or error != "ambiguous_config":
        return _tool_metadata(name, path, root)
    # A bin link is the sole exception to the no-symlink metadata rule.
    descriptor = None
    try:
        descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
        for component in path.parts[1:-1]:
            parent = os.fstat(descriptor)
            if parent.st_uid != 0 or parent.st_mode & 0o022:
                return _unknown(name)
            child = os.open(
                component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor
            )
            os.close(descriptor)
            descriptor = child
        parent = os.fstat(descriptor)
        link = os.stat(path.name, dir_fd=descriptor, follow_symlinks=False)
        if (
            parent.st_uid != 0
            or parent.st_mode & 0o022
            or not stat.S_ISLNK(link.st_mode)
            or link.st_uid != 0
            or link.st_gid != 0
        ):
            return _unknown(name)
        target = Path(os.readlink(path.name, dir_fd=descriptor))
    except OSError:
        return _unknown(name, "probe_error")
    finally:
        if descriptor is not None:
            os.close(descriptor)
    version = tool["version"]
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]*", version) or version.lower() in {
        "latest",
        "lts",
    }:
        return _unknown(name)
    install = (installs or root / "installs") / tool["name"] / version
    if not target.is_absolute() or ".." in target.parts or not target.is_relative_to(install):
        return _unknown(name)
    descriptor = None
    try:
        descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
        for component in target.parts[1:-1]:
            parent = os.fstat(descriptor)
            if parent.st_uid != 0 or parent.st_mode & 0o022:
                return _unknown(name)
            child = os.open(
                component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor
            )
            os.close(descriptor)
            descriptor = child
        parent = os.fstat(descriptor)
        final = os.stat(target.name, dir_fd=descriptor, follow_symlinks=False)
        good = (
            parent.st_uid == 0
            and not parent.st_mode & 0o022
            and final.st_uid == 0
            and final.st_gid == 0
            and not final.st_mode & 0o022
            and stat.S_ISREG(final.st_mode)
        )
        return _verdict(name, good, trusted_target=good)
    except OSError:
        return _unknown(name, "probe_error")
    finally:
        if descriptor is not None:
            os.close(descriptor)


def tool_checks(policy: dict[str, Any], os_id: str, scope: str = "self") -> list[dict[str, Any]]:
    if os_id not in {"ubuntu", "omarchy"}:
        return []
    root = Path(policy["labels"]["tool_root"])
    installs = _install_base(root, policy)
    tools = policy["shared_tools"]["tools"]
    heavy = policy["heavy_work"]
    lock = Path(policy["labels"]["run_dir"]) / heavy["lock_name"]
    now = datetime.now(timezone.utc)
    skips = {entry["id"]: entry["reason"] for entry in policy["checks"].get("skip", [])}

    def ownership() -> list[ReadResult]:
        reads = [
            _tool_metadata("tool_root", root, root, True),
            _tool_metadata("tool_bin", root / "bin", root, True),
        ]
        for index, tool in enumerate(tools):
            for number, binary in enumerate(tool.get("bins", [tool["name"]])):
                name = f"tool_{index}_bin_{number}"
                if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", binary):
                    reads.append(_unknown(name))
                else:
                    reads.append(_tool_bin(name, root / "bin" / binary, root, tool, installs))
        return reads

    def pins() -> list[ReadResult]:
        reads = []
        for index, tool in enumerate(tools):
            name = f"tool_{index}_pin"
            version = tool["version"]
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]*", version):
                reads.append(_unknown(name))
            elif version.lower() in {"latest", "lts"}:
                reads.append(_verdict(name, False, pinned=False))
            else:
                reads.append(_tool_metadata(name, installs / tool["name"] / version, root, True))
        return reads

    def lock_reads() -> list[ReadResult]:
        info, error = _metadata(lock, Path(policy["labels"]["run_dir"]))
        if error or info is None:
            reads = [_unknown("lock_mode_and_group", error or "probe_error")]
        else:
            _, groups, group_error = _accounts()
            if group_error:
                reads = [_unknown("lock_mode_and_group", group_error)]
            else:
                group = groups.get(policy["labels"]["shared_group"])
                matches = group is not None and info.st_gid == group[0]
                good = (
                    stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o660 and matches
                )
                reads = [
                    _verdict(
                        "lock_mode_and_group",
                        good,
                        group_matches=matches,
                        mode_matches=stat.S_IMODE(info.st_mode) == 0o660,
                    )
                ]
        reads.extend(environment("env_var_names_lock", heavy["env_var"], str(lock)))
        return reads

    def environment(name: str, variable: str, expected: str) -> list[ReadResult]:
        current = next((u for u in policy["businesses"]["users"] if u["uid"] == os.getuid()), None)
        if current is None:
            return [_unknown(name, "other_account")]
        value = os.environ.get(variable, "")
        matches = value == expected if variable != "PATH" else value.split(":")[0] == expected
        reads = [_verdict(name, matches, set=bool(value), matches=matches)]
        if scope == "all" and any(u["uid"] != os.getuid() for u in policy["businesses"]["users"]):
            reads.append(_unknown(name + "_other_accounts", "other_account"))
        return reads

    def wrapper() -> list[ReadResult]:
        return [
            _tool_metadata("wrapper_metadata", root / "bin" / heavy["wrapper"], root),
            _unknown("refuses_uncapped_job", "not_checked"),
        ]

    def restore() -> list[ReadResult]:
        setting = policy["backups"]["restore_test"]
        if "record" not in setting:
            return attestation_reads(policy, "backups.restore-tested", now)
        result = probe.read_file(
            Path(setting["record"]), prefix=Path("/var/lib"), byte_cap=4096, root_owned=True
        )
        if result.reason:
            return [
                _unknown("restore_test_record", result.reason),
                *attestation_reads(policy, "backups.restore-tested", now),
            ]
        try:
            data = json.loads(result.data, object_pairs_hook=manifest_loader._pairs)
            if not isinstance(data, dict) or not isinstance(data.get("date"), str):
                raise ValueError
            date = data["date"]
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)?", date):
                raise ValueError
            at = datetime.fromisoformat(date.replace("Z", "+00:00"))
            if at.tzinfo is None:
                at = at.replace(tzinfo=timezone.utc)
            outcome = data.get("result")
            if outcome not in ("pass", "fail"):
                raise ValueError
            if at > now:
                return [_unknown("restore_test_record")]
            good = outcome == "pass" and now - at <= timedelta(days=setting["max_age_days"])
            return [_verdict("restore_test_record", good, date=date, result=outcome)]
        except (ValueError, TypeError, UnicodeError):
            return [_unknown("restore_test_record")]

    runners = {
        "shared_tools.root-owned-readonly": ownership,
        "shared_tools.pins-match": pins,
        "shared_tools.path-order": lambda: environment("path_order", "PATH", str(root / "bin")),
        "heavy_work.lock": lock_reads,
        "heavy_work.capped-run": wrapper,
        "backups.fresh": lambda: (
            attestation_reads(policy, "backups.fresh", now)
            if "max_age_hours" in policy["backups"]
            else [_unknown("last_backup")]
        ),
        "backups.restore-tested": restore,
    }
    return [
        check_result(
            spec,
            [
                ReadResult(
                    "manifest_skip", "skipped", {"reason": skips[spec.id]}, "skipped_by_manifest"
                )
            ]
            if spec.id in skips
            else runners[spec.id](),
        )
        for spec in TOOL_SPECS
    ]


REGISTRY: tuple[CheckSpec, ...] = ()


def attestation_reads(policy: dict[str, Any], check_id: str, now: datetime) -> list[ReadResult]:
    entries = {(e["id"], e["read"]): e for e in policy["checks"].get("attest", [])}
    reads = []
    for identity, days in manifest_loader.ATTESTABLE.items():
        if identity[0] != check_id:
            continue
        name = identity[1]
        entry = entries.get(identity)
        if entry is None:
            reads.append(_unknown(name, "attestation_missing"))
            continue
        at = manifest_loader.attestation_time(entry["at"])
        age = now - at
        limit = (
            timedelta(days=days)
            if days is not None
            else timedelta(hours=policy["backups"]["max_age_hours"])
            if check_id == "backups.fresh"
            else timedelta(days=policy["backups"]["restore_test"]["max_age_days"])
        )
        observed = {"at": entry["at"]}
        if at > now:
            reads.append(ReadResult(name, "not_verified", observed, "attestation_stale"))
        elif entry["answer"] == "no" or (age > limit and days is None):
            reads.append(ReadResult(name, "fail", observed))
        elif age > limit:
            reads.append(ReadResult(name, "not_verified", observed, "attestation_stale"))
        else:
            reads.append(ReadResult(name, "attested", observed, "owner_attested"))
    return reads


def _accounts() -> tuple[
    dict[str, tuple[int, int, Path]], dict[str, tuple[int, set[str]]], Reason | None
]:
    """Read bounded local account databases, never a credential database."""
    accounts: dict[str, tuple[int, int, Path]] = {}
    groups: dict[str, tuple[int, set[str]]] = {}
    for filename in ("passwd", "group"):
        text, reason = _text(Path("/etc") / filename, Path("/etc"))
        if reason:
            return {}, {}, reason
        try:
            for line in text.splitlines():
                fields = line.split(":")
                if filename == "passwd":
                    name, _, uid, gid, _, home, _ = fields
                    if name in accounts or not Path(home).is_absolute():
                        raise ValueError
                    accounts[name] = (int(uid), int(gid), Path(home))
                else:
                    name, _, gid, members = fields
                    if name in groups:
                        raise ValueError
                    groups[name] = (int(gid), set(members.split(",")))
        except ValueError:
            return {}, {}, "ambiguous_config"
    return accounts, groups, None


def _directory(name: str, path: Path, uid: int) -> ReadResult:
    try:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode):
            return _unknown(name)
        good = (
            stat.S_ISDIR(info.st_mode)
            and info.st_uid == uid
            and stat.S_IMODE(info.st_mode) == 0o700
        )
        return _verdict(name, good, private=good)
    except OSError:
        return _unknown(name, "probe_error")


def account_checks(
    policy: dict[str, Any], os_id: str, deadline: float, scope: str = "self"
) -> list[dict[str, Any]]:
    if os_id not in {"ubuntu", "omarchy"}:
        return []
    linux: probe.Platform = "ubuntu" if os_id == "ubuntu" else "omarchy"
    accounts: dict[str, tuple[int, int, Path]] = {}
    groups: dict[str, tuple[int, set[str]]] = {}
    reason: Reason | None = None
    loaded = False

    def load_accounts() -> None:
        nonlocal accounts, groups, reason, loaded
        if not loaded:
            accounts, groups, reason = _accounts()
            loaded = True

    users = policy["businesses"]["users"]
    owner = policy["owner"]["user"]
    current_uid = os.getuid()
    skips = {entry["id"]: entry["reason"] for entry in policy["checks"].get("skip", [])}
    results = []

    def emit(
        check_id: str,
        anchor: str,
        role: str,
        subject: str,
        run: Callable[[], list[ReadResult]],
        *,
        limitation: str | None = None,
        source: str = "pack",
    ) -> None:
        # Scope selection uses validated declared identities, not a database read.
        declared_uid = next((u["uid"] for u in users if u["user"] == subject), None)
        local = role in {"any", "owner-attests"} or declared_uid == current_uid
        if role == "owner":
            if check_id not in skips:
                load_accounts()
            local = check_id in skips or (
                subject in accounts and accounts[subject][0] == current_uid
            )
        if not local and scope == "self":
            return
        spec = next(spec for spec in ACCOUNT_SPECS if spec.id == check_id)
        if check_id in skips:
            reads = [
                ReadResult(
                    "manifest_skip", "skipped", {"reason": skips[check_id]}, "skipped_by_manifest"
                )
            ]
        elif not local:
            reads = [_unknown("account", "other_account")]
        else:
            if check_id in {
                "owner.sudo-needs-password",
                "businesses.users-and-homes",
                "businesses.no-privileged-groups",
            }:
                load_accounts()
                reads = [_unknown("account_database", reason)] if reason else run()
            else:
                reads = run()
        result = check_result(spec, reads)
        result["subject"] = subject
        results.append(result)

    def membership(user: str, group: str) -> bool:
        return (
            user in accounts
            and group in groups
            and (accounts[user][1] == groups[group][0] or user in groups[group][1])
        )

    admin_group = "sudo" if os_id == "ubuntu" else "wheel"
    emit(
        "owner.sudo-needs-password",
        "admin-account-and-agent-accounts",
        "owner",
        owner,
        lambda: [
            _verdict(
                "owner_in_admin_group",
                membership(owner, admin_group),
                member=membership(owner, admin_group),
            ),
            *attestation_reads(policy, "owner.sudo-needs-password", datetime.now(timezone.utc)),
        ],
    )
    emit(
        "owner.no-sudo-into-business",
        "admin-account-and-agent-accounts",
        "owner-attests",
        owner,
        lambda: attestation_reads(
            policy, "owner.no-sudo-into-business", datetime.now(timezone.utc)
        ),
        limitation="Root can still become any user; the admin stays trusted.",
    )

    for user in users:
        name, uid = user["user"], user["uid"]

        def homes(
            user: dict[str, Any] = user, name: str = name, uid: int = uid
        ) -> list[ReadResult]:
            found = accounts.get(name)
            bounds = policy["businesses"]["uid_range"]
            reads = [
                _verdict(
                    "declared_uid",
                    found is not None and found[0] == uid and bounds["min"] <= uid <= bounds["max"],
                    matches=found is not None and found[0] == uid,
                )
            ]
            reads.append(
                _directory("home_private", found[2], uid)
                if found
                else _verdict("home_private", False, exists=False)
            )
            if current_uid == uid:
                # /proc exposes the current mask without changing process state.
                status, error = _text(Path(f"/proc/{os.getpid()}/status"), Path("/proc"))
                mask = re.search(r"^Umask:\s+([0-7]{4})$", status, re.M)
                reads.append(
                    _unknown("umask", error or "ambiguous_config")
                    if error or not mask
                    else _verdict("umask", mask[1] == "0077", private=mask[1] == "0077")
                )
                for other in users:
                    if other["user"] == name:
                        continue
                    account = accounts.get(other["user"])
                    if not account:
                        reads.append(_unknown("other_home_unlistable"))
                        continue
                    try:
                        with os.scandir(account[2]):
                            pass
                        reads.append(_verdict("other_home_unlistable", False, listable=True))
                    except PermissionError:
                        reads.append(_verdict("other_home_unlistable", True, listable=False))
                    except OSError:
                        reads.append(_unknown("other_home_unlistable", "probe_error"))
            elif scope == "all":
                reads.append(_unknown("business_home_access", "other_account"))
            return reads

        emit("businesses.users-and-homes", "one-user-account-per-business", "any", name, homes)
        forbidden = {"sudo", "adm", "wheel", "docker", "lxd", owner}

        # The owner's primary group can have a different name.
        def unprivileged(name: str = name, forbidden: set[str] = forbidden) -> list[ReadResult]:
            forbidden = forbidden | {
                group
                for group, (gid, _) in groups.items()
                if owner in accounts and gid == accounts[owner][1]
            }
            good = name in accounts and not any(membership(name, group) for group in forbidden)
            return [_verdict("unprivileged_groups", good, unprivileged=good)]

        emit(
            "businesses.no-privileged-groups",
            "admin-account-and-agent-accounts",
            "any",
            name,
            unprivileged,
            limitation="A sudoers user rule, which requires root to read.",
        )

        def tmpdir(uid: int = uid) -> list[ReadResult]:
            value = os.environ.get("TMPDIR")
            if not value:
                return [_verdict("private_tmpdir", False, set=False)]
            if not Path(value).is_absolute() or ".." in Path(value).parts:
                return [_unknown("private_tmpdir")]
            # Reject symlink ancestors as well as the final directory.
            try:
                if any(stat.S_ISLNK(p.lstat().st_mode) for p in Path(value).parents):
                    return [_unknown("private_tmpdir")]
            except OSError:
                return [_unknown("private_tmpdir", "probe_error")]
            return [_directory("private_tmpdir", Path(value), uid)]

        emit(
            "businesses.private-tmpdir", "shared-tools-private-data", "each-business", name, tmpdir
        )

        def slice_limits(user: dict[str, Any] = user, uid: int = uid) -> list[ReadResult]:
            result = probe.run_probe(
                linux,
                (
                    "/usr/bin/systemctl",
                    "show",
                    f"user-{uid}.slice",
                    "--property=MemoryHigh",
                    "--property=MemoryMax",
                    "--property=TasksMax",
                ),
                deadline=deadline,
            )
            reads: list[ReadResult] = []
            if result.reason or result.returncode != 0:
                reads.append(_unknown("slice_limits", result.reason or "probe_error"))
            else:
                try:
                    pairs = [line.split("=", 1) for line in result.data.decode().splitlines()]
                    fields = dict(pairs)
                    if len(pairs) != len(fields) or set(fields) != {
                        "MemoryHigh",
                        "MemoryMax",
                        "TasksMax",
                    }:
                        raise ValueError
                    limits = policy["businesses"]["size_classes"][user["size_class"]]
                    for key, prop in (
                        ("memory_high", "MemoryHigh"),
                        ("memory_max", "MemoryMax"),
                        ("tasks_max", "TasksMax"),
                    ):
                        value = fields[prop]
                        if value != "infinity" and not value.isdecimal():
                            raise ValueError
                        if key not in limits:
                            continue
                        wanted = limits[key]
                        expected = (
                            wanted
                            if isinstance(wanted, int)
                            else int(wanted[:-1]) * 1024 ** (3 if wanted[-1] == "G" else 2)
                        )
                        matches = value != "infinity" and int(value) == expected
                        reads.append(_verdict(key, matches, matches=matches))
                except (ValueError, UnicodeError):
                    reads = [_unknown("slice_limits")]
            text, error = _text(Path("/proc/meminfo"), Path("/proc"))
            values = re.findall(r"^MemTotal:\s+([0-9]+) kB$", text, re.M)
            if error or len(values) != 1:
                reads.append(_unknown("host_ram", error or "ambiguous_config"))
            else:
                expected_ram = policy["businesses"]["sizing_basis"]["host_ram_gb"] * 1024**3
                matches = abs(int(values[0]) * 1024 - expected_ram) <= expected_ram * 0.1
                reads.append(
                    ReadResult(
                        "host_ram",
                        "pass" if matches else "warn",
                        {"within_ten_percent": matches},
                        None if matches else "not_checked",
                    )
                )
            return reads

        emit("businesses.slice-limits", "sessions-that-survive-a-reboot", "any", name, slice_limits)

        def linger(name: str = name) -> list[ReadResult]:
            result = probe.read_file(
                Path("/var/lib/systemd/linger") / name, prefix=Path("/var/lib/systemd/linger")
            )
            if result.reason == "probe_missing":
                return [_verdict("linger", False, enabled=False)]
            return (
                [_unknown("linger", result.reason)]
                if result.reason
                else [_verdict("linger", True, enabled=True)]
            )

        emit(
            "sessions.linger",
            "sessions-that-survive-a-reboot",
            "any",
            name,
            linger,
            source="engine",
        )

        def unit_fields(properties: tuple[str, ...]) -> tuple[dict[str, str], Reason | None]:
            result = probe.run_probe(
                linux,
                (
                    "/usr/bin/systemctl",
                    "--user",
                    "show",
                    policy["runtime"].get("session_unit", "herdr.service"),
                    *(f"--property={key}" for key in properties),
                ),
                deadline=deadline,
            )
            if result.reason or result.returncode != 0:
                return {}, result.reason or "probe_error"
            try:
                pairs = [line.split("=", 1) for line in result.data.decode().splitlines()]
                fields = dict(pairs)
                if len(pairs) != len(fields) or set(fields) != set(properties):
                    return {}, "ambiguous_config"
                return fields, None
            except (ValueError, UnicodeError):
                return {}, "ambiguous_config"

        def runtime() -> list[ReadResult]:
            fields, error = unit_fields(("UnitFileState", "ActiveState", "Slice"))
            if error:
                return [_unknown("session_unit", error)]
            return [
                _verdict(
                    "unit_enabled",
                    fields["UnitFileState"] == "enabled",
                    enabled=fields["UnitFileState"] == "enabled",
                ),
                _verdict(
                    "unit_active",
                    fields["ActiveState"] == "active",
                    active=fields["ActiveState"] == "active",
                ),
                _verdict(
                    "unit_slice",
                    bool(fields["Slice"]) and fields["Slice"] != "app.slice",
                    outside_app_slice=bool(fields["Slice"]) and fields["Slice"] != "app.slice",
                ),
            ]

        emit(
            "runtime.herdr-per-user",
            "sessions-that-survive-a-reboot",
            "each-business",
            name,
            runtime,
        )

        def started() -> list[ReadResult]:
            fields, error = unit_fields(("ActiveEnterTimestampMonotonic",))
            if error:
                return [_unknown("startup_before_login", error)]
            value = fields["ActiveEnterTimestampMonotonic"]
            if not value.isdecimal():
                return [_unknown("startup_before_login")]
            # Active state alone cannot establish the first login this boot.
            # Closed logind sessions disappear from /run, so do not infer a pass.
            return [
                ReadResult(
                    "startup_before_login", "warn", {"unit_started": int(value) > 0}, "not_checked"
                )
            ]

        emit(
            "sessions.started-without-login",
            "part-4-first-week",
            "each-business",
            name,
            started,
            source="engine",
            limitation=(
                "The first login this boot is not retained by this bounded probe; "
                "complete the reboot test."
            ),
        )

        def updater() -> list[ReadResult]:
            fields, error = unit_fields(("Environment",))
            if error:
                return [_unknown("autoupdater_disabled", error)]
            try:
                values = [
                    item.split("=", 1)[1]
                    for item in shlex.split(fields["Environment"])
                    if item.startswith("DISABLE_AUTOUPDATER=")
                ]
            except ValueError:
                return [_unknown("autoupdater_disabled")]
            disabled = values == ["1"]
            return [_verdict("autoupdater_disabled", disabled, disabled=disabled)]

        emit("runtime.claude-autoupdate-off", "backups-and-updates", "each-business", name, updater)
    return results


LINUX_SPECS: tuple[CheckSpec, ...] = (
    CheckSpec(
        "host.power-on-after-loss",
        "docs/machine-setup.md#part-2-picking-a-machine",
        lambda _: [],
        source="engine",
        run_as="owner-attests",
        fix_text="Check the BIOS power-on setting and record dated evidence.",
    ),
    CheckSpec(
        "host.disk-luks2-tpm",
        "docs/machine-setup.md#ubuntu-lts-recommended-default",
        lambda _: [],
        "TPM binding to verified boot, Secure Boot and PCR policy need root.",
        platforms=("ubuntu",),
    ),
    CheckSpec(
        "host.disk-luks2-tpm-arch",
        "docs/machine-setup.md#omarchy-arch-based",
        lambda _: [],
        "TPM binding to verified boot, Secure Boot and PCR policy need root.",
        platforms=("omarchy",),
    ),
    CheckSpec(
        "hardening.firewall-default-deny",
        "docs/machine-setup.md#managing-it-from-a-mac",
        lambda _: [],
        "The live ruleset and SSH source list require root.",
    ),
    CheckSpec(
        "hardening.aur-reviewed",
        "docs/machine-setup.md#omarchy-arch-based",
        lambda _: [],
        platforms=("omarchy",),
    ),
    CheckSpec(
        "hardening.firmware-manual",
        "docs/machine-setup.md#backups-and-updates",
        lambda _: [],
        run_as="owner-attests",
        fix_text="Check firmware does not auto-apply and record dated evidence.",
    ),
)


LINUX_SPECS += tuple(
    CheckSpec(
        check_id,
        "docs/machine-setup.md#" + section,
        lambda _: [],
        limitation,
        platforms=platforms,
        run_as=run_as,
        fix_text=fix,
    )
    for check_id, section, limitation, platforms, run_as, fix in (
        (
            "host.screen-lock",
            "omarchy-arch-based",
            "Omarchy idle configuration needs a second-install proof.",
            ("ubuntu", "omarchy"),
            "owner",
            None,
        ),
        (
            "remote_access.tailscale-version",
            "managing-it-from-a-mac",
            None,
            ("ubuntu", "omarchy"),
            "any",
            None,
        ),
        (
            "remote_access.tailscale-serve-named",
            "managing-it-from-a-mac",
            None,
            ("ubuntu", "omarchy"),
            "any",
            None,
        ),
        (
            "remote_access.offbox-listeners",
            "managing-it-from-a-mac",
            "Process identity is not established by a listener uid or port.",
            ("ubuntu", "omarchy"),
            "any",
            None,
        ),
        (
            "hardening.update-snapshot",
            "omarchy-arch-based",
            "Snapshot presence requires root.",
            ("omarchy",),
            "any",
            "Run omarchy update after taking a snapshot.",
        ),
    )
)


def _serve_allowed(data: bytes, ports: list[int]) -> bool | None:
    try:
        config = json.loads(data)
        if not isinstance(config, dict) or set(config) - {"TCP", "Web", "AllowFunnel"}:
            return None
        tcp = config.get("TCP", {})
        web = config.get("Web", {})
        funnel = config.get("AllowFunnel", {})
        if not all(isinstance(value, dict) for value in (tcp, web, funnel)):
            return None
        if any(type(value) is not bool for value in funnel.values()):
            return None
        declared = set()
        for port, handler in tcp.items():
            if not port.isdecimal() or not isinstance(handler, dict):
                return None
            declared.add(int(port))
        for address, handler in web.items():
            port = address.rsplit(":", 1)[-1]
            if ":" not in address or not port.isdecimal() or not isinstance(handler, dict):
                return None
            declared.add(int(port))
        return declared <= set(ports) and not any(funnel.values())
    except (ValueError, TypeError, AttributeError):
        return None


def _listeners_loopback(text: str, ipv6: bool) -> bool | None:
    rows = text.splitlines()
    if not rows or "local_address" not in rows[0] or "uid" not in rows[0]:
        return None
    try:
        offbox = False
        for row in rows[1:]:
            fields = row.split()
            if len(fields) < 10 or not fields[7].isdecimal():
                return None
            address, port = fields[1].split(":")
            if len(address) != (32 if ipv6 else 8):
                return None
            int(address, 16)
            int(port, 16)
            if fields[3] != "0A":
                continue
            loopback = (
                address == "00000000000000000000000001000000" if ipv6 else address.endswith("7F")
            )
            offbox |= not loopback
        return not offbox
    except (ValueError, IndexError):
        return None


def _root_tpm(data: bytes, rows: list[list[str]]) -> bool | None:
    try:
        if any(len(row) != 4 for row in rows):
            return None
        sources = [row[1] for row in rows]
        if len(set(sources)) != len(sources):
            return None
        roots: list[str | None] = []

        def visit(node: Any, backing: str | None, encrypted: str | None, depth: int) -> None:
            if depth > 64 or not isinstance(node, dict):
                raise ValueError
            if node.get("type") == "crypt":
                encrypted = backing
            mounts = node["mountpoints"]
            if not isinstance(mounts, list):
                raise ValueError
            if "/" in mounts:
                roots.append(encrypted)
            children = node.get("children", [])
            if not isinstance(children, list):
                raise ValueError
            uuid = node.get("uuid")
            if uuid is not None and not isinstance(uuid, str):
                raise ValueError
            for child in children:
                visit(child, uuid, encrypted, depth + 1)

        for device in json.loads(data)["blockdevices"]:
            visit(device, None, None, 0)
        if not roots or any(not value for value in roots):
            return None
        for uuid in roots:
            matching = [row for row in rows if row[1] == "UUID=" + str(uuid)]
            if not matching:
                # Other crypttab source formats need device resolution.
                return None
            options = matching[0][3].split(",")
            tpm = [value for value in options if value.startswith("tpm2-device=")]
            if len(tpm) > 1:
                return None
            if not tpm or tpm[0] != "tpm2-device=auto":
                return False
        return True
    except (ValueError, KeyError, TypeError, RecursionError):
        return None


def _root_encrypted(data: bytes) -> bool | None:
    """Follow only paths ending at the root mount; unrelated crypt nodes do not count."""
    try:
        document = json.loads(data)
        roots: list[bool] = []

        def visit(node: Any, encrypted: bool, depth: int) -> None:
            if depth > 64 or not isinstance(node, dict) or not isinstance(node.get("type"), str):
                raise ValueError
            mounts = node.get("mountpoints")
            if not isinstance(mounts, list) or any(
                m is not None and not isinstance(m, str) for m in mounts
            ):
                raise ValueError
            encrypted = encrypted or node["type"] == "crypt"
            if "/" in mounts:
                roots.append(encrypted)
            children = node.get("children", [])
            if not isinstance(children, list):
                raise ValueError
            for child in children:
                visit(child, encrypted, depth + 1)

        devices = document["blockdevices"]
        if not isinstance(devices, list):
            raise ValueError
        for device in devices:
            visit(device, False, 0)
        return all(roots) if roots else None
    except (ValueError, KeyError, TypeError, RecursionError):
        return None


def linux_checks(policy: dict[str, Any], os_id: str, deadline: float) -> list[dict[str, Any]]:
    if os_id not in {"ubuntu", "omarchy"}:
        return []
    linux: probe.Platform = "ubuntu" if os_id == "ubuntu" else "omarchy"
    skips = {entry["id"]: entry["reason"] for entry in policy["checks"].get("skip", [])}

    def disk() -> list[ReadResult]:
        result = probe.run_probe(
            linux, ("/usr/bin/lsblk", "--json", "--output", "TYPE,MOUNTPOINTS"), deadline=deadline
        )
        if result.reason or result.returncode != 0:
            reads = [_unknown("root_encrypted", result.reason or "probe_error")]
        else:
            encrypted = _root_encrypted(result.data)
            reads = (
                [_unknown("root_encrypted")]
                if encrypted is None
                else [_verdict("root_encrypted", encrypted, encrypted=encrypted)]
            )
        wanted = policy["host"]["disk"]["encryption"]
        if linux == "omarchy" and wanted == "luks2-passphrase":
            reads.append(
                _verdict("passphrase_boot", policy["host"]["disk"].get("unattended_boot") is False)
            )
        elif wanted == "luks2-tpm2":
            path = Path("/etc/crypttab" if linux == "ubuntu" else "/etc/crypttab.initramfs")
            text, error = _text(path, Path("/etc"))
            if error:
                reads.append(_unknown("tpm_option", error))
            else:
                rows = [
                    line.split()
                    for line in text.splitlines()
                    if line.strip() and not line.lstrip().startswith("#")
                ]
                identity = probe.run_probe(
                    linux,
                    ("/usr/bin/lsblk", "--json", "--output", "TYPE,MOUNTPOINTS,UUID"),
                    deadline=deadline,
                )
                if identity.reason or identity.returncode != 0:
                    reads.append(_unknown("tpm_option", identity.reason or "probe_error"))
                else:
                    matched = _root_tpm(identity.data, rows)
                    reads.append(
                        _unknown("tpm_option")
                        if matched is None
                        else _verdict("tpm_option", matched, configured=matched)
                    )
        else:
            reads.append(_verdict("encryption_policy", False))
        reads.append(_unknown("luks2_header", "needs_root"))
        return reads

    def firewall() -> list[ReadResult]:
        if policy["hardening"]["firewall"]["tool"] != "ufw":
            return [_unknown("firewall_config", "not_checked")]
        reads = []
        for name, path, key, expected in (
            ("ufw_enabled", "/etc/ufw/ufw.conf", "ENABLED", "yes"),
            ("input_policy", "/etc/default/ufw", "DEFAULT_INPUT_POLICY", "DROP"),
        ):
            text, error = _text(Path(path), Path("/etc"))
            if error:
                reads.append(_unknown(name, error))
                continue
            values = re.findall(r"^\s*" + key + r"\s*=\s*([^#\n]+)", text, re.M)
            if len(values) != 1:
                reads.append(_unknown(name))
            else:
                try:
                    tokens = shlex.split(values[0])
                except ValueError:
                    tokens = []
                if len(tokens) != 1:
                    reads.append(_unknown(name))
                    continue
                value = tokens[0]
                reads.append(_verdict(name, value == expected, matches=value == expected))
        return reads

    def tailscale_version() -> list[ReadResult]:
        argv = (
            ("/usr/bin/dpkg-query", "-W", "-f=${Version}", "tailscale")
            if linux == "ubuntu"
            else ("/usr/bin/pacman", "-Q", "tailscale")
        )
        package = probe.run_probe(linux, argv, deadline=deadline)
        status = probe.run_probe(
            linux, ("/usr/bin/tailscale", "status", "--json"), deadline=deadline
        )
        reads = []
        if package.reason or package.returncode != 0:
            reads.append(_unknown("package_version", package.reason or "probe_missing"))
        else:
            try:
                value = package.data.decode().strip()
                if linux == "omarchy":
                    name, value = value.split()
                    if name != "tailscale":
                        raise ValueError
                match = re.fullmatch(
                    r"(?:[0-9]+:)?([0-9]+)\.([0-9]+)\.([0-9]+)(?:-[A-Za-z0-9.+~]+)?", value
                )
                minimum = policy["remote_access"]["tailscale"]["min_version"]
                if not match:
                    raise ValueError
                good = tuple(map(int, match.groups())) >= tuple(map(int, minimum.split(".")))
                reads.append(_verdict("package_version", good, meets_minimum=good))
            except (ValueError, UnicodeError):
                reads.append(_unknown("package_version"))
        if status.reason or status.returncode != 0:
            reads.append(_unknown("backend_running", status.reason or "probe_error"))
        else:
            try:
                value = json.loads(status.data)["BackendState"]
                if not isinstance(value, str):
                    raise ValueError
                reads.append(_verdict("backend_running", value == "Running"))
            except (ValueError, TypeError, KeyError):
                reads.append(_unknown("backend_running"))
        return reads

    def serve() -> list[ReadResult]:
        result = probe.run_probe(
            linux, ("/usr/bin/tailscale", "serve", "status", "--json"), deadline=deadline
        )
        if result.reason or result.returncode != 0:
            return [_unknown("serve_policy", result.reason or "probe_error")]
        allowed = _serve_allowed(result.data, policy["remote_access"]["tailscale"]["serve_ports"])
        return [_unknown("serve_policy") if allowed is None else _verdict("serve_policy", allowed)]

    def listeners() -> list[ReadResult]:
        reads = []
        for name in ("tcp", "tcp6"):
            text, error = _text(Path("/proc/net") / name, Path("/proc/net"))
            value = None if error else _listeners_loopback(text, name == "tcp6")
            # Off-box listeners cannot be exempted using a uid or a port alone.
            reads.append(
                _verdict(name, True)
                if value is True
                else _unknown(name, error or "ambiguous_config")
            )
        return reads

    def screen() -> list[ReadResult]:
        if _current_account() != policy["owner"]["user"]:
            return [_unknown("screen_lock", "other_account")]
        if linux == "omarchy":
            return [_unknown("screen_lock", "not_checked")]
        reads = []
        for key, schema in (
            ("lock-enabled", "org.gnome.desktop.screensaver"),
            ("idle-delay", "org.gnome.desktop.session"),
        ):
            result = probe.run_probe(
                linux, ("/usr/bin/gsettings", "get", schema, key), deadline=deadline
            )
            if result.reason or result.returncode != 0:
                reads.append(_unknown(key, result.reason or "probe_error"))
                continue
            try:
                value = result.data.decode().strip()
                if key == "lock-enabled":
                    if value not in {"true", "false"}:
                        raise ValueError
                    good = value == "true"
                else:
                    match = re.fullmatch(r"uint32 ([0-9]+)", value)
                    if not match:
                        raise ValueError
                    good = (
                        0 < int(match[1]) <= policy["host"]["desktop"]["screen_lock_minutes"] * 60
                    )
                reads.append(_verdict(key, good))
            except (ValueError, UnicodeError):
                reads.append(_unknown(key))
        return reads

    def update() -> list[ReadResult]:
        text, error = _text(Path("/var/log/pacman.log"), Path("/var/log"))
        reads = []
        if error:
            reads.append(_unknown("upgrade_age", error))
        else:
            dates = []
            pending = False
            for line in text.splitlines():
                if re.fullmatch(r"\[[^]]+\] \[PACMAN\] starting full system upgrade", line):
                    pending = True
                elif "[PACMAN] Running " in line:
                    pending = False
                elif pending:
                    match = re.fullmatch(r"\[([^]]+)\] \[ALPM\] transaction completed", line)
                    if match:
                        dates.append(match[1])
                        pending = False
            try:
                if not dates:
                    raise ValueError
                date = datetime.fromisoformat(dates[-1])
                if date.tzinfo is None:
                    raise ValueError
                age = datetime.now(timezone.utc) - date
                reads.append(
                    _verdict(
                        "upgrade_age",
                        timedelta(0)
                        <= age
                        <= timedelta(days=policy["hardening"]["updates"]["cadence_days"]),
                    )
                )
            except ValueError:
                reads.append(_unknown("upgrade_age"))
        return reads + [_unknown("snapshot_presence", "needs_root")]

    def aur() -> list[ReadResult]:
        result = probe.run_probe(linux, ("/usr/bin/pacman", "-Qm"), deadline=deadline)
        if result.reason or result.returncode != 0:
            return [_unknown("foreign_packages", result.reason or "probe_error")]
        try:
            rows = [line.split() for line in result.data.decode().splitlines()]
            if any(len(row) != 2 or not re.fullmatch(r"[a-z0-9@._+-]+", row[0]) for row in rows):
                return [_unknown("foreign_packages")]
            packages = {row[0] for row in rows}
            reviewed = set(policy["hardening"]["updates"].get("aur_packages_reviewed", []))
            return [
                _verdict(
                    "foreign_packages", packages <= reviewed, all_reviewed=packages <= reviewed
                )
            ]
        except UnicodeError:
            return [_unknown("foreign_packages")]

    results = []
    now = datetime.now(timezone.utc)
    for spec in LINUX_SPECS:
        if os_id not in spec.platforms:
            continue
        if spec.id in skips:
            reads = [
                ReadResult(
                    "manifest_skip", "skipped", {"reason": skips[spec.id]}, "skipped_by_manifest"
                )
            ]
        else:
            callbacks = {
                "host.disk-luks2-tpm": disk,
                "host.disk-luks2-tpm-arch": disk,
                "host.screen-lock": screen,
                "hardening.firewall-default-deny": firewall,
                "hardening.aur-reviewed": aur,
                "hardening.update-snapshot": update,
                "remote_access.tailscale-version": tailscale_version,
                "remote_access.tailscale-serve-named": serve,
                "remote_access.offbox-listeners": listeners,
            }
            reads = callbacks.get(spec.id, lambda: [])()
            reads += attestation_reads(policy, spec.id, now)
        results.append(check_result(spec, reads))
    return results


def policy_checks(
    policy: dict[str, Any], os_id: str, deadline: float, scope: str = "self"
) -> list[dict[str, Any]]:
    specs = {spec.id: spec for spec in (*registry(os_id), *REGISTRY)}
    skips = {entry["id"]: entry["reason"] for entry in policy["checks"].get("skip", [])}
    for check_id in skips:
        if check_id in {s.id for s in LINUX_SPECS}:
            continue
        if check_id.startswith(
            (
                "owner.",
                "businesses.",
                "sessions.",
                "runtime.",
                "shared_tools.",
                "heavy_work.",
                "backups.",
            )
        ):
            continue
        if check_id in {"host.os-release", "manifest.integrity"}:
            continue
        if os_id not in {"ubuntu", "omarchy"}:
            continue
        if check_id == "host.disk-filevault":
            continue
        if check_id.endswith("-arch") and os_id != "omarchy":
            continue
        if os_id == "omarchy" and check_id in {
            "host.disk-luks2-tpm",
            "host.desktop-no-autologin",
            "hardening.reboot-pending",
            "hardening.unattended-security-only",
        }:
            continue
        specs.setdefault(
            check_id,
            CheckSpec(
                check_id,
                "docs/machine-setup.md#admin-account-and-agent-accounts",
                lambda _: [],
            ),
        )
    now = datetime.now(timezone.utc)
    results = []
    for spec in specs.values():
        if spec.id in skips:
            reads = [
                ReadResult(
                    "manifest_skip", "skipped", {"reason": skips[spec.id]}, "skipped_by_manifest"
                )
            ]
        else:
            reads = spec.run(deadline) + attestation_reads(policy, spec.id, now)
        results.append(check_result(spec, reads))
    return (
        results
        + account_checks(policy, os_id, deadline, scope)
        + tool_checks(policy, os_id, scope)
        + linux_checks(policy, os_id, deadline)
    )


def doctor(manifest: Path | None = None, scope: str = "self") -> dict[str, Any]:
    if scope not in {"self", "all"}:
        raise ValueError("Invalid scope")
    policy = None
    failure = None
    metadata: dict[str, Any] = {"source": "default_path" if manifest is None else "caller_selected"}
    try:
        policy, metadata = manifest_loader.load(manifest)
    except manifest_loader.IntegrityError:
        failure = 1
    except manifest_loader.ManifestError:
        failure = 2
    if failure is not None:
        checks = []
        if failure == 1:
            checks.append(
                check_result(
                    CheckSpec(
                        "manifest.integrity",
                        "docs/machine-setup.md#admin-account-and-agent-accounts",
                        lambda _: [],
                    ),
                    [ReadResult("manifest", "fail", {})],
                )
            )
        counts = Counter(check["state"] for check in checks)
        return {
            "schema": "mb.machine.doctor",
            "schema_version": 1,
            "safe_to_share": False,
            "ok": False,
            "exit_code": failure,
            "scope": scope,
            "manifest": metadata,
            "platform": {"id": "not_checked"},
            "run_as": {"account": _current_account() or "unknown", "role": "unknown"},
            "summary": {state: counts[state] for state in STATES},
            "checks": checks,
            "errors": [{"code": "manifest.invalid"}] if failure == 2 else [],
        }
    deadline = time.monotonic() + 60
    detected, reads = detect_platform(deadline)
    checks = [
        check_result(
            CheckSpec(
                "host.os-release",
                "docs/machine-setup.md#part-3-the-operating-system",
                lambda _: reads,
                "Install-media verification and other machine controls.",
            ),
            reads,
        )
    ]
    checks.extend(
        policy_checks(policy, detected["id"], deadline, scope)
        if policy is not None
        else [
            check_result(spec, spec.run(deadline))
            for spec in (*registry(detected["id"]), *REGISTRY)
        ]
    )
    if policy is not None:
        integrity = CheckSpec(
            "manifest.integrity",
            "docs/machine-setup.md#admin-account-and-agent-accounts",
            lambda _: [],
        )
        checks = [check for check in checks if check["id"] != "manifest.integrity"]
        checks.append(
            check_result(
                integrity,
                [
                    _unknown("manifest", "caller_selected_policy")
                    if manifest is not None
                    else _verdict("manifest", True)
                ],
            )
        )
        checks.append(
            check_result(
                CheckSpec(
                    "manifest.coverage",
                    "docs/machine-setup.md#admin-account-and-agent-accounts",
                    lambda _: [],
                ),
                [
                    ReadResult(section, "not_verified", {}, "not_checked")
                    for section in policy
                    if section
                    not in (
                        {
                            "manifest_version",
                            "checks",
                            "owner",
                            "runtime",
                            "shared_tools",
                            "heavy_work",
                            "backups",
                        }
                        if detected["id"] in {"ubuntu", "omarchy"}
                        else {"manifest_version", "checks"}
                    )
                ],
            )
        )
        if (
            detected["id"] in {"ubuntu", "omarchy"}
            and policy["host"]["os"]["family"] != detected["family"]
        ):
            checks[0] = check_result(
                CheckSpec(
                    "host.os-release",
                    "docs/machine-setup.md#part-3-the-operating-system",
                    lambda _: [],
                ),
                [*reads, _verdict("manifest_os_matches", False)],
            )
    if policy is not None:
        for entry in policy["checks"].get("skip", []):
            if entry["id"] in {"host.os-release", "manifest.integrity"}:
                for index, check in enumerate(checks):
                    if check["id"] == entry["id"]:
                        checks[index] = check_result(
                            CheckSpec(check["id"], check["section"], lambda _: []),
                            [
                                ReadResult(
                                    "manifest_skip",
                                    "skipped",
                                    {"reason": entry["reason"]},
                                    "skipped_by_manifest",
                                )
                            ],
                        )
    code = exit_code(checks)
    # Deferred manifest checks keep the baseline incomplete.
    if code == 0:
        code = 3
    counts = Counter(check["state"] for check in checks)
    return {
        "schema": "mb.machine.doctor",
        "schema_version": 1,
        "safe_to_share": False,
        "ok": code == 0,
        "exit_code": code,
        "platform": detected,
        "run_as": {"account": _current_account() or "unknown", "role": "unknown"},
        "scope": scope,
        "manifest": metadata,
        "summary": {state: counts[state] for state in STATES},
        "checks": checks,
    }


def human_report(report: dict[str, Any]) -> str:
    lines = [
        "Machine doctor: scope self, current account only."
        if report.get("scope", "self") == "self"
        else "Machine doctor: scope all, other accounts are not verified."
    ]
    for check in report["checks"]:
        lines.extend([check["section"], f"  {check['id']}: {check['state']}"])
        for read in check["reads"]:
            if read["state"] == "attested":
                lines.append(f"  NOT VERIFIED (owner attested): {read['observed']['at']}")
            if read["state"] == "skipped":
                lines.append(f"  Skipped: {read['observed']['reason']}")
        if check["id"] == "manifest.coverage":
            for read in check["reads"]:
                lines.append(f"  {read['name']}: not checked")
        if check["reason"] == "caller_selected_policy":
            lines.append("  Caller-selected policy: trust is not verified.")
        if check["does_not_prove"]:
            lines.append(f"  Does not prove: {check['does_not_prove']}")
    lines.append(
        "No manifest: baseline verification is incomplete."
        if report["manifest"]["source"] == "none"
        else "Manifest verification failed; no other checks ran."
        if report["exit_code"] == 1 and len(report["checks"]) == 1
        else "Manifest policy loaded; baseline verification is incomplete."
    )
    return "\n".join(lines)
