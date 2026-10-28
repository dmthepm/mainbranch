"""Privacy-safe GitHub issue drafting for Main Branch friction."""

from __future__ import annotations

import json
import platform
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from mb import __version__
from mb import doctor as doctor_mod
from mb.engine import install_mode
from mb.gitignore import gitignore_problem

PUBLIC_REPO = "dmthepm/mainbranch"
ISSUE_DRAFTS_RELATIVE_PATH = Path(".mb") / "issue-drafts"
ISSUE_DRAFTS_GITIGNORE_ENTRY = ".mb/issue-drafts/"
ISSUE_KINDS = {"bug", "feature", "question"}

SENSITIVE_ENV_RE = re.compile(
    r"(?im)^([A-Z0-9_]*(?:TOKEN|KEY|SECRET|PASSWORD|PASS|PWD|"
    r"CREDENTIAL|AUTH|BEARER)[A-Z0-9_]*\s*=\s*).+$"
)
INLINE_SECRET_RE = re.compile(
    r"(?i)(?<![?&])\b([A-Z0-9_]*(?:TOKEN|KEY|SECRET|PASSWORD|PASS|PWD|"
    r"CREDENTIAL|AUTH|BEARER)[A-Z0-9_]*\s*=\s*)(?!\[REDACTED\])[^\s`'\",;]+"
)
BEARER_RE = re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/=-]{10,}")
TOKEN_RE = re.compile(
    r"\b(?:ghp|gho|ghu|ghs|ghr|github_pat|sk|xoxb|xoxp|xapp)-[A-Za-z0-9_./=-]{8,}\b"
)
QUERY_SECRET_RE = re.compile(r"(?i)([?&](?:token|key|secret|auth|password)=)[^&\s]+")
ABSOLUTE_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9:])(?:"
    r"/(?:Users|home|private|tmp|var|Volumes|opt|usr/local)/[^\s\"'`<>),;]+"
    r"|[A-Za-z]:\\[^\s\"'`<>),;]+"
    r")"
)
HOME_PATH_RE = re.compile(r"(?<![\w])~/[^\s\"'`<>),;]+")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


@dataclass(frozen=True)
class ScrubbedText:
    text: str
    redactions: dict[str, int]


def _bump(redactions: dict[str, int], key: str) -> None:
    redactions[key] = redactions.get(key, 0) + 1


def _replace_pattern(
    text: str,
    pattern: re.Pattern[str],
    replacement: str | Callable[[re.Match[str]], str],
    redactions: dict[str, int],
    key: str,
) -> str:
    def repl(match: re.Match[str]) -> str:
        _bump(redactions, key)
        if callable(replacement):
            return replacement(match)
        return replacement

    return pattern.sub(repl, text)


def merge_redactions(*items: dict[str, int]) -> dict[str, int]:
    merged: dict[str, int] = {}
    for item in items:
        for key, value in item.items():
            merged[key] = merged.get(key, 0) + value
    return merged


def scrub_text(text: str) -> ScrubbedText:
    """Redact common public-issue hazards while preserving useful shape."""
    redactions: dict[str, int] = {}
    scrubbed = text
    scrubbed = _replace_pattern(
        scrubbed,
        SENSITIVE_ENV_RE,
        lambda match: f"{match.group(1)}[REDACTED]",
        redactions,
        "sensitive_env",
    )
    scrubbed = _replace_pattern(
        scrubbed,
        INLINE_SECRET_RE,
        lambda match: f"{match.group(1)}[REDACTED]",
        redactions,
        "sensitive_env",
    )
    scrubbed = _replace_pattern(
        scrubbed,
        BEARER_RE,
        lambda match: f"{match.group(1)}[REDACTED]",
        redactions,
        "token",
    )
    scrubbed = _replace_pattern(scrubbed, TOKEN_RE, "[REDACTED_TOKEN]", redactions, "token")
    scrubbed = _replace_pattern(
        scrubbed,
        QUERY_SECRET_RE,
        lambda match: f"{match.group(1)}[REDACTED]",
        redactions,
        "url_secret",
    )
    scrubbed = _replace_pattern(
        scrubbed, ABSOLUTE_PATH_RE, "<local-path>", redactions, "local_path"
    )
    scrubbed = _replace_pattern(scrubbed, HOME_PATH_RE, "<home-path>", redactions, "local_path")
    scrubbed = _replace_pattern(scrubbed, EMAIL_RE, "<email>", redactions, "email")
    return ScrubbedText(text=scrubbed, redactions=redactions)


def scrub_value(value: Any) -> tuple[Any, dict[str, int]]:
    """Recursively scrub strings inside JSON-like structures."""
    if isinstance(value, str):
        scrubbed = scrub_text(value)
        return scrubbed.text, scrubbed.redactions
    if isinstance(value, list):
        redactions: list[dict[str, int]] = []
        scrubbed_items = []
        for item in value:
            scrubbed, item_redactions = scrub_value(item)
            scrubbed_items.append(scrubbed)
            redactions.append(item_redactions)
        return scrubbed_items, merge_redactions(*redactions)
    if isinstance(value, dict):
        redactions = []
        scrubbed_dict: dict[str, Any] = {}
        for key, item in value.items():
            scrubbed, item_redactions = scrub_value(item)
            scrubbed_dict[str(key)] = scrubbed
            redactions.append(item_redactions)
        return scrubbed_dict, merge_redactions(*redactions)
    return value, {}


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:48].strip("-") or "issue"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _default_title(kind: str, fields: dict[str, str]) -> str:
    if kind == "bug":
        command = fields.get("command", "").strip()
        suffix = command or "Main Branch friction"
        return f"bug: {suffix}"
    if kind == "feature":
        problem = fields.get("problem", "").strip()
        suffix = problem.splitlines()[0][:80] if problem else "Main Branch workflow gap"
        return f"feat: {suffix}"
    question = fields.get("question", "").strip()
    suffix = question.splitlines()[0][:80] if question else "Main Branch question"
    return f"question: {suffix}"


def _labels_for_kind(kind: str) -> list[str]:
    if kind == "bug":
        return ["bug", "triage"]
    if kind == "feature":
        return ["enhancement", "triage"]
    return ["question", "triage"]


def _scrub_field(value: str) -> tuple[str, dict[str, int]]:
    scrubbed = scrub_text(value.strip() or "_Not provided yet._")
    return scrubbed.text, scrubbed.redactions


def _safe_doctor_json(repo: Path) -> tuple[str, dict[str, int]]:
    try:
        report = doctor_mod.run(path=str(repo), qualify=False)
    except Exception as exc:
        scrubbed = scrub_text(str(exc))
        return (
            json.dumps(
                {
                    "ok": False,
                    "error": "mb doctor --json could not run while drafting this issue.",
                    "detail": scrubbed.text,
                    "fallback": "Re-run with `mb issue draft bug --no-doctor` if needed.",
                },
                indent=2,
            ),
            scrubbed.redactions,
        )
    scrubbed, redactions = scrub_value(report)
    return json.dumps(scrubbed, indent=2), redactions


def _bug_body(
    repo: Path,
    fields: dict[str, str],
    include_doctor: bool,
) -> tuple[str, dict[str, int]]:
    redactions: list[dict[str, int]] = []
    command, item_redactions = _scrub_field(fields.get("command", ""))
    redactions.append(item_redactions)
    happened, item_redactions = _scrub_field(fields.get("happened", ""))
    redactions.append(item_redactions)
    expected, item_redactions = _scrub_field(fields.get("expected", ""))
    redactions.append(item_redactions)
    diagnostics, item_redactions = _scrub_field(fields.get("diagnostics", ""))
    redactions.append(item_redactions)
    doctor_json = ""
    if include_doctor:
        doctor_json, item_redactions = _safe_doctor_json(repo)
        redactions.append(item_redactions)
    doctor_block = (
        "\n## `mb doctor --json` output\n\n"
        "<details>\n<summary>mb doctor --json</summary>\n\n"
        "```json\n"
        f"{doctor_json}\n"
        "```\n\n"
        "</details>\n"
        if doctor_json
        else ""
    )
    body = f"""## `mb --version` output

```text
mb {__version__}
```

## Operating system

{platform.system() or "Unknown"}

## Install mode

{install_mode()}

## Command or skill that failed

```text
{command}
```

## What happened

{happened}

## What you expected

{expected}

## Extra diagnostics

```text
{diagnostics}
```
{doctor_block}
## Privacy review

- [ ] I reviewed this draft and removed private business data, customer data, secrets,
      account details, and local-only paths.
"""
    return body, merge_redactions(*redactions)


def _feature_body(fields: dict[str, str]) -> tuple[str, dict[str, int]]:
    redactions: list[dict[str, int]] = []
    problem, item_redactions = _scrub_field(fields.get("problem", ""))
    redactions.append(item_redactions)
    surface, item_redactions = _scrub_field(fields.get("surface", "Other / not sure"))
    redactions.append(item_redactions)
    proposal, item_redactions = _scrub_field(fields.get("proposal", ""))
    redactions.append(item_redactions)
    alternatives, item_redactions = _scrub_field(fields.get("alternatives", ""))
    redactions.append(item_redactions)
    related, item_redactions = _scrub_field(fields.get("related", ""))
    redactions.append(item_redactions)
    body = f"""## Problem statement

{problem}

## Proposed surface

{surface}

## Proposed change

{proposal}

## Alternatives considered

{alternatives}

## Related issues or PRs

{related}

## Privacy review

- [ ] I reviewed this draft and removed private business data, customer data, secrets,
      account details, and local-only paths.
"""
    return body, merge_redactions(*redactions)


def _question_body(fields: dict[str, str]) -> tuple[str, dict[str, int]]:
    redactions: list[dict[str, int]] = []
    question, item_redactions = _scrub_field(fields.get("question", ""))
    redactions.append(item_redactions)
    context, item_redactions = _scrub_field(fields.get("context", ""))
    redactions.append(item_redactions)
    tried, item_redactions = _scrub_field(fields.get("tried", ""))
    redactions.append(item_redactions)
    body = f"""## Question

{question}

## Context

{context}

## What you've tried

{tried}

## Privacy review

- [ ] I reviewed this draft and removed private business data, customer data, secrets,
      account details, and local-only paths.
"""
    return body, merge_redactions(*redactions)


def ensure_issue_gitignore(repo: Path) -> bool:
    if gitignore_problem(repo):
        return False
    gitignore = repo / ".gitignore"
    existing = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    entries = {line.strip() for line in existing.splitlines()}
    if ISSUE_DRAFTS_GITIGNORE_ENTRY in entries or ".mb/" in entries:
        return False
    prefix = "" if not existing or existing.endswith("\n") else "\n"
    gitignore.write_text(existing + prefix + ISSUE_DRAFTS_GITIGNORE_ENTRY + "\n", encoding="utf-8")
    return True


def create_draft(
    *,
    repo: str,
    kind: str,
    title: str,
    fields: dict[str, str],
    include_doctor: bool = True,
) -> dict[str, Any]:
    normalized_kind = kind.strip().lower()
    if normalized_kind not in ISSUE_KINDS:
        supported = ", ".join(sorted(ISSUE_KINDS))
        raise ValueError(f"unknown issue kind {kind!r}; expected one of: {supported}")

    repo_path = Path(repo).resolve()
    if not repo_path.exists():
        raise ValueError(f"repo not found: {repo}")
    draft_dir = repo_path / ISSUE_DRAFTS_RELATIVE_PATH
    draft_dir.mkdir(parents=True, exist_ok=True)
    gitignore_updated = ensure_issue_gitignore(repo_path)

    raw_title = title.strip() or _default_title(normalized_kind, fields)
    scrubbed_title = scrub_text(raw_title)
    if normalized_kind == "bug":
        body, body_redactions = _bug_body(repo_path, fields, include_doctor=include_doctor)
    elif normalized_kind == "feature":
        body, body_redactions = _feature_body(fields)
    else:
        body, body_redactions = _question_body(fields)
    redactions = merge_redactions(scrubbed_title.redactions, body_redactions)
    labels = _labels_for_kind(normalized_kind)
    created_at = _now().isoformat(timespec="seconds")
    slug = _slug(scrubbed_title.text)
    filename = f"{created_at.replace(':', '').replace('+0000', 'Z')}-{normalized_kind}-{slug}.md"
    path = draft_dir / filename
    counter = 2
    while path.exists():
        path = draft_dir / f"{path.stem}-{counter}{path.suffix}"
        counter += 1

    label_lines = "\n".join(f"  - {label}" for label in labels)
    content = f"""---
mb_issue_draft: 1
kind: {normalized_kind}
title: {json.dumps(scrubbed_title.text)}
labels:
{label_lines}
created_at: {created_at}
privacy_review: required
---

<!-- mb:internal
Review before opening. Main Branch scrubbed common secrets, local paths, email
addresses, and token-shaped values, but the operator is still responsible for
removing private business context before submitting a public issue.
-->

{body}
"""
    relative_path = str(path.relative_to(repo_path))
    path.write_text(content, encoding="utf-8")
    return {
        "ok": True,
        "kind": normalized_kind,
        "title": scrubbed_title.text,
        "labels": labels,
        "path": str(path),
        "relative_path": relative_path,
        "repo": str(repo_path),
        "gitignore_updated": gitignore_updated,
        "redactions": redactions,
        "privacy": {
            "safe_by_default": True,
            "requires_operator_review": True,
            "submitted": False,
        },
        "next_command": f"mb issue open {relative_path}",
    }


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---\n", 4)
    if end == -1:
        return {}, text
    metadata_text = text[4:end]
    body = text[end + 5 :].lstrip()
    metadata: dict[str, Any] = {}
    labels: list[str] = []
    in_labels = False
    for line in metadata_text.splitlines():
        if line.startswith("labels:"):
            in_labels = True
            continue
        if in_labels and line.startswith("  - "):
            labels.append(line[4:].strip())
            continue
        in_labels = False
        if ": " not in line:
            continue
        key, value = line.split(": ", 1)
        if key == "title":
            try:
                metadata[key] = json.loads(value)
            except json.JSONDecodeError:
                metadata[key] = value.strip('"')
        else:
            metadata[key] = value
    if labels:
        metadata["labels"] = labels
    return metadata, body


def _public_body(body: str) -> str:
    return re.sub(r"<!-- mb:internal.*?-->\n\n?", "", body, flags=re.DOTALL).strip() + "\n"


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, timeout=30, check=False)


def _fallback(title: str, reason: str, draft_path: Path) -> dict[str, Any]:
    title_query = quote(title)
    return {
        "ok": True,
        "submitted": False,
        "fallback": True,
        "reason": reason,
        "draft_path": str(draft_path),
        "manual_url": f"https://github.com/{PUBLIC_REPO}/issues/new?title={title_query}",
        "manual_steps": [
            f"Open https://github.com/{PUBLIC_REPO}/issues/new/choose",
            f"Use the draft body from {draft_path}",
            "Review the privacy checklist before submitting.",
        ],
    }


def open_draft(
    draft: str,
    *,
    yes: bool = False,
    runner: Callable[[list[str]], subprocess.CompletedProcess[str]] = _run,
) -> dict[str, Any]:
    draft_path = Path(draft).resolve()
    if not draft_path.exists():
        raise ValueError(f"issue draft not found: {draft}")
    metadata, body = _parse_frontmatter(draft_path.read_text(encoding="utf-8"))
    title = str(metadata.get("title") or draft_path.stem)
    labels = [str(label) for label in metadata.get("labels", [])]
    public_body = _public_body(body)

    if not yes:
        return _fallback(
            title,
            "pass --yes after reviewing the draft to submit with gh",
            draft_path,
        )
    if not shutil.which("gh"):
        return _fallback(title, "GitHub CLI `gh` is not on PATH", draft_path)

    auth = runner(["gh", "auth", "status"])
    if auth.returncode != 0:
        return _fallback(title, "GitHub CLI is not authenticated", draft_path)

    args = ["gh", "issue", "create", "--repo", PUBLIC_REPO, "--title", title, "--body", public_body]
    for label in labels:
        args.extend(["--label", label])
    result = runner(args)
    if result.returncode != 0:
        fallback = _fallback(
            title,
            result.stderr.strip() or result.stdout.strip() or "gh issue create failed",
            draft_path,
        )
        fallback["ok"] = False
        return fallback
    return {
        "ok": True,
        "submitted": True,
        "fallback": False,
        "url": result.stdout.strip(),
        "draft_path": str(draft_path),
        "title": title,
        "labels": labels,
    }
