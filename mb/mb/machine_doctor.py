"""Read-only machine checks. Registry entries own every probe and output field."""

from __future__ import annotations

import getpass
import platform
import shlex
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
        "fix": None,
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


# D3 adds checks here. Platform detection is shared once per run.
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
    checks.extend(check_result(spec, spec.run(deadline)) for spec in REGISTRY)
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
