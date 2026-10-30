"""Read-only shape and declared-doctor checks for a private books repository."""

from __future__ import annotations

import ast
import csv
import json
import os
import re
import shlex
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from mb.books import _has_fixture_marker, _read_frontmatter

YEAR_ENTRYPOINT = re.compile(r"^[0-9]{4}\.journal$")
SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
COMMIT = re.compile(r"^[0-9a-fA-F]{40}$")
ROOT_TYPES = {"assets": "A", "liabilities": "L", "equity": "E", "income": "R", "expenses": "X"}
RULE_STATUSES = {"active recurring", "migration generator", "template/fallback"}
EVIDENCE_EXTENSIONS = {".pdf", ".ofx", ".qfx", ".qbo", ".qif", ".csv"}
CSV_ALLOWED_DIRS = {"imports", "reports", "manifests", "workpapers"}
RECEIPT_KEYS = {"commit", "finished_at", "exit_code", "hledger_version", "controls"}


def _finding(rule: str, path: str, summary: str, level: str = "error") -> dict[str, str]:
    return {"rule": rule, "level": level, "operator_summary": summary, "path": path}


def _git(repo: Path, *args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def _shape(repo: Path, tracked: list[str]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    if not any(Path(rel).suffix == ".journal" for rel in tracked):
        findings.append(
            _finding(
                "workspace_repo",
                ".",
                "No journals here; treated as a books workspace, not a ledger repo.",
                level="info",
            )
        )
    else:
        entrypoints = sorted(
            p for p in repo.iterdir() if p.is_file() and YEAR_ENTRYPOINT.fullmatch(p.name)
        )
        if not entrypoints:
            findings.append(
                _finding("entrypoint_missing", ".", "Add a year journal at the books repo root.")
            )

        accounts = sorted(p for p in repo.glob("*-accounts.journal") if p.is_file())
        typed: dict[str, str] = {}
        commodities = 0
        multi_currency = False
        for path in accounts:
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeError):
                lines = []
            for line in lines:
                match = re.match(
                    r"^\s*account\s+(assets|liabilities|equity|income|expenses)\s*;\s*type:\s*([A-Za-z])\b",
                    line,
                )
                if match:
                    typed[match.group(1)] = match.group(2).upper()
                if re.match(r"^\s*commodity\s+\S", line):
                    commodities += 1
                    if commodities == 1 and "; mb-books: multi-currency" in line:
                        multi_currency = True
        if not accounts or any(typed.get(root) != kind for root, kind in ROOT_TYPES.items()):
            findings.append(
                _finding(
                    "accounts_untyped",
                    accounts[0].relative_to(repo).as_posix() if accounts else ".",
                    "Declare type directives on all five root accounts.",
                )
            )
        if commodities > 1 and not multi_currency:
            findings.append(
                _finding(
                    "commodity_extra",
                    accounts[0].relative_to(repo).as_posix() if accounts else ".",
                    "Declare multi-currency on the first commodity or use one commodity.",
                )
            )

    for path in sorted((repo / "rules").glob("*.rules")):
        if not path.is_file():
            continue
        rel = path.relative_to(repo).as_posix()
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError):
            lines = []
        values = [
            match.group(1).strip()
            for line in lines
            if (match := re.search(r"\bStatus:\s*(.*)$", line))
        ]
        if not values:
            findings.append(
                _finding("rules_status_missing", rel, "Add a Status header to the rules file.")
            )
        elif len(values) != 1 or not any(
            values[0] == status
            or any(
                values[0].startswith(status + delimiter)
                for delimiter in (".", ";", ",", " -", " (")
            )
            for status in RULE_STATUSES
        ):
            findings.append(
                _finding("rules_status_invalid", rel, "Use an allowed rules Status value.")
            )

    for rel in tracked:
        path = repo / rel
        suffix = path.suffix.lower()
        if suffix not in EVIDENCE_EXTENSIONS:
            continue
        if suffix == ".csv" and path.parts[len(repo.parts)] in CSV_ALLOWED_DIRS:
            continue
        if path.is_file() and not _has_fixture_marker(path):
            findings.append(
                _finding("evidence_tracked", rel, "Move evidence bytes out of tracked books files.")
            )

    for path in sorted((repo / "manifests").glob("*.csv")):
        rel = path.relative_to(repo).as_posix()
        try:
            with path.open(newline="", encoding="utf-8") as handle:
                rows = csv.DictReader(line for line in handle if not line.lstrip().startswith("#"))
                invalid = not rows.fieldnames or "sha256" not in rows.fieldnames
                if not invalid:
                    invalid = any(
                        not SHA256.fullmatch((row.get("sha256") or "").strip()) for row in rows
                    )
        except (OSError, UnicodeError, csv.Error):
            invalid = True
        if invalid:
            findings.append(
                _finding("manifest_sha_missing", rel, "Add a SHA-256 to every manifest row.")
            )
    return findings


def _receipt(repo: Path, head: str | None) -> tuple[dict[str, Any] | None, bool]:
    path = repo / "reports/doctor-receipt.json"
    if not path.is_file():
        return None, False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or set(data) != RECEIPT_KEYS:
            return None, True
        if not isinstance(data["commit"], str) or not COMMIT.fullmatch(data["commit"]):
            return None, True
        if (
            not isinstance(data["finished_at"], str)
            or not datetime.fromisoformat(data["finished_at"].replace("Z", "+00:00")).tzinfo
        ):
            return None, True
        if (
            type(data["exit_code"]) is not int
            or type(data["controls"]) is not int
            or data["controls"] < 0
        ):
            return None, True
        if (
            not isinstance(data["hledger_version"], str)
            or not data["hledger_version"]
            or len(data["hledger_version"]) > 120
        ):
            return None, True
        return {**data, "stale": data["commit"] != head}, False
    except (OSError, UnicodeError, ValueError, TypeError):
        return None, True


def _blockers(repo: Path) -> dict[str, int]:
    counts = {"open": 0, "resolved": 0}
    try:
        lines = (repo / "docs/blockers.md").read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return counts
    for line in lines:
        if not line.startswith("|"):
            continue
        cells = [part.strip().lower() for part in line.strip().strip("|").split("|")]
        if (
            len(cells) < 4
            or cells[0] in {"id", "---"}
            or all(set(c) <= {"-", ":", " "} for c in cells)
        ):
            continue
        if cells[3] == "resolved":
            counts["resolved"] += 1
        elif cells[3] in {"open", "blocked", "pending"}:
            counts["open"] += 1
    return counts


def _doctor(repo: Path, timeout: int) -> tuple[dict[str, Any], list[dict[str, str]]]:
    if not shutil.which("hledger"):
        return {
            "ran": False,
            "status": "not_run",
            "level": "info",
            "reason": "hledger unavailable here",
            "exit_code": None,
            "duration_s": 0.0,
            "timed_out": False,
        }, []
    command = "bin/books doctor"
    config = repo / "books.toml"
    if config.is_file():
        try:
            section = ""
            declared = command
            for line in config.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped.startswith("[") and stripped.endswith("]"):
                    section = stripped[1:-1]
                elif section == "mb" and stripped.startswith("doctor_command"):
                    key, sep, value = stripped.partition("=")
                    if sep and key.strip() == "doctor_command":
                        parsed = ast.literal_eval(value.strip())
                        if isinstance(parsed, str):
                            declared = parsed
            command = declared
        except (OSError, UnicodeError, ValueError, SyntaxError):
            return {
                "ran": False,
                "reason": "invalid books.toml",
                "exit_code": None,
                "duration_s": 0.0,
                "timed_out": False,
            }, [
                _finding(
                    "doctor_command_invalid", "books.toml", "Set a valid declared doctor command."
                )
            ]
    try:
        argv = shlex.split(command)
    except ValueError:
        argv = []
    if not argv or not (repo / argv[0]).is_file() or not os.access(repo / argv[0], os.X_OK):
        return {
            "ran": False,
            "reason": "doctor command unavailable",
            "exit_code": None,
            "duration_s": 0.0,
            "timed_out": False,
        }, [
            _finding(
                "doctor_command_invalid",
                "books.toml" if config.exists() else "bin/books",
                "Set an executable declared doctor command.",
            )
        ]
    started = time.monotonic()
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    try:
        result = subprocess.run(
            argv,
            cwd=repo,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            check=False,
        )
        record: dict[str, Any] = {
            "ran": True,
            "exit_code": result.returncode,
            "duration_s": round(time.monotonic() - started, 3),
            "timed_out": False,
        }
    except subprocess.TimeoutExpired:
        record = {
            "ran": True,
            "exit_code": None,
            "duration_s": round(time.monotonic() - started, 3),
            "timed_out": True,
        }
    except OSError:
        record = {
            "ran": False,
            "reason": "doctor command unavailable",
            "exit_code": None,
            "duration_s": round(time.monotonic() - started, 3),
            "timed_out": False,
        }
    findings = (
        [_finding("doctor_failed", ".", "The declared books doctor did not pass.")]
        if record["timed_out"] or record["exit_code"] != 0
        else []
    )
    return record, findings


def inspect(repo: Path, timeout: int = 600) -> dict[str, Any]:
    """Inspect one books repo without retaining private command output."""
    policy = repo / "core/finance/books.md"
    if policy.is_file():
        fm, _ = _read_frontmatter(policy)
        configured = str(fm.get("books_repo") or "").strip()
        if configured:
            candidate = Path(configured).expanduser()
            target = candidate if candidate.is_absolute() else repo / candidate
            if target.resolve() != repo.resolve():
                return {
                    "ok": False,
                    "state": "warn",
                    "safe_to_share": True,
                    "summary": "This is the business repo; check the configured books repo.",
                    "findings": [
                        _finding(
                            "business_repo_not_books_repo",
                            "core/finance/books.md",
                            "This is the business repo; the books repo is configured as "
                            f"{configured}. "
                            f"Run mb books doctor --repo {shlex.quote(configured)}.",
                            level="warn",
                        )
                    ],
                    "doctor": {
                        "ran": False,
                        "status": "not_run",
                        "level": "warn",
                        "reason": "business repo selected",
                        "exit_code": None,
                        "duration_s": 0.0,
                        "timed_out": False,
                    },
                    "receipt": None,
                    "blockers": {"open": 0, "resolved": 0},
                    "repo": "business repo",
                }
    tracked_text = _git(repo, "ls-files")
    head = _git(repo, "rev-parse", "HEAD")
    findings = _shape(repo, tracked_text.splitlines() if tracked_text is not None else [])
    if tracked_text is None or head is None:
        findings.append(
            _finding("git_unavailable", ".", "Open a git books repo for tracked evidence checks.")
        )
    receipt, invalid = _receipt(repo, head)
    if invalid:
        findings.append(
            _finding(
                "receipt_invalid",
                "reports/doctor-receipt.json",
                "Replace the invalid doctor receipt with the documented shape.",
            )
        )
    if any(item["rule"] == "workspace_repo" for item in findings):
        # A workspace holds no journals, so there is no ledger doctor to run.
        doctor: dict[str, Any] = {
            "ran": False,
            "status": "not_run",
            "level": "info",
            "reason": "no journals here",
            "exit_code": None,
            "duration_s": 0.0,
            "timed_out": False,
        }
    else:
        doctor, doctor_findings = _doctor(repo, timeout)
        findings.extend(doctor_findings)
    ok = not any(item["level"] == "error" for item in findings)
    return {
        "ok": ok,
        "state": "ok" if ok else "error",
        "safe_to_share": True,
        "summary": "Books repo checks passed." if ok else "Books repo checks need attention.",
        "findings": findings,
        "doctor": doctor,
        "receipt": receipt,
        "blockers": _blockers(repo),
        "repo": "books repo",
    }


def render(report: dict[str, Any]) -> None:
    import typer

    typer.echo(report["summary"])
    for finding in report["findings"]:
        summary = finding["operator_summary"]
        path = finding["path"]
        typer.echo(f"[{finding['level']}] {finding['rule']}: {summary} ({path})")
    doctor = report["doctor"]
    if doctor["ran"]:
        typer.echo(
            f"Declared doctor: exit {doctor['exit_code']}, timed out: {doctor['timed_out']}."
        )
    else:
        level = doctor.get("level")
        prefix = f"[{level}] " if level else ""
        typer.echo(f"{prefix}Declared doctor: not run ({doctor['reason']}).")
    if report["receipt"]:
        receipt = report["receipt"]
        typer.echo(f"Doctor receipt: stale: {receipt['stale']}; exit {receipt['exit_code']}.")
    typer.echo(
        f"Blockers: {report['blockers']['open']} open, {report['blockers']['resolved']} resolved."
    )
