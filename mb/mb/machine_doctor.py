"""Read-only machine checks. Registry entries own every probe and output field."""

from __future__ import annotations

import configparser
import getpass
import json
import os
import platform
import re
import shlex
import stat
import time
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, get_args

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
    # Allowed-Origins uses origin:archive. Origins-Pattern uses named selectors.
    if "=" not in origin:
        parts = origin.split(":")
        return len(parts) == 2 and bool(parts[0]) and parts[1].endswith("-security")
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
    return pocket.endswith("-security") and not any(char in pocket for char in "*?[]")


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
                _verdict(
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


def credential_store(deadline: float) -> list[ReadResult]:
    from mb.credential_store import SecretStore

    store = SecretStore()
    # Local-file health reads stored values. Do not call it from doctor.
    if store.backend == "local-file":
        return [_unknown("store_available", "probe_missing")]
    health = store.health(deadline=deadline)
    ready = health.get("ok") is True
    if ready and any(os.environ.get(key) for key in ("DISPLAY", "WAYLAND_DISPLAY")):
        return [_unknown("store_available", "ambiguous_config")]
    return [_verdict("store_available", ready, available=ready)]


def registry(os_id: str) -> tuple[CheckSpec, ...]:
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
    return tuple(spec for spec in specs if os_id in spec.platforms)


REGISTRY: tuple[CheckSpec, ...] = ()


def doctor() -> dict[str, Any]:
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
        check_result(spec, spec.run(deadline)) for spec in (*registry(detected["id"]), *REGISTRY)
    )
    code = exit_code(checks)
    # No manifest handling in this release. Missing policy prevents assurance.
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
        "run_as": {"account": getpass.getuser(), "role": "unknown"},
        "scope": "self",
        "manifest": {"source": "none", "reason": "no_manifest"},
        "summary": {state: counts[state] for state in STATES},
        "checks": checks,
    }


def human_report(report: dict[str, Any]) -> str:
    lines = ["Machine doctor: scope self, current account only."]
    for check in report["checks"]:
        lines.extend([check["section"], f"  {check['id']}: {check['state']}"])
        if check["does_not_prove"]:
            lines.append(f"  Does not prove: {check['does_not_prove']}")
    lines.append("No manifest: baseline verification is incomplete.")
    return "\n".join(lines)
