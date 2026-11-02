"""Markdown records and playbook health for the status briefing."""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

from mb import pushes as pushes_mod
from mb import relationships

IMPORTANT_DIRS = (
    "core",
    "reference/core",
    "research",
    "decisions",
    "bets",
    "pushes",
    "campaigns",
    "log",
    "documents",
)
STALE_DECISION_DAYS = 14
UNCODIFIED_DECISION_DAYS = 7
STALE_RESEARCH_DAYS = 45
ACTIVE_BET_STATUSES = {"open", "paused"}
BET_APPETITE_TIERS = {"trivial", "small", "material", "strategic"}
BET_SIGNAL_COMPARATORS = {"<", "<=", "==", ">=", ">", "!="}
ACTIVE_PUSH_STATUSES = {"planned", "active", "paused"}
COMPLETED_PUSH_STATUSES = {"completed"}
LIVE_OFFER_STATUSES = {"accepted", "graduated", "running", "scaling"}
PUSH_STATUSES_EXPECTING_PLAYBOOK = {"planned", "active"}
PLAYBOOK_STATUSES_NEEDING_ATTENTION = {"draft", "planned"}
PLAYBOOK_APPROVAL_STATUSES_NEEDING_ATTENTION = {"needed", "rejected", ""}
PLAYBOOK_PROVIDER_BOUNDARIES_NEEDING_ATTENTION = {
    "plan-only",
    "external-manual",
    "manual-provider",
}


def _read_frontmatter(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            first = handle.readline()
            if first.strip() != "---":
                return {}
            lines: list[str] = []
            for line in handle:
                if line.strip() == "---":
                    break
                lines.append(line)
            else:
                return {}
    except OSError:
        return {}
    raw = "".join(lines).strip()
    try:
        parsed = yaml.safe_load(raw) or {}
    except yaml.YAMLError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _read_markdown_text(path: Path, *, limit: int = 80_000) -> str:
    try:
        return path.read_text(encoding="utf-8")[:limit]
    except OSError:
        return ""


def _relative_existing_paths(repo: Path, candidates: list[str]) -> list[str]:
    return [rel for rel in candidates if (repo / rel).is_file()]


def _frontmatter_status(repo: Path, rel_path: str) -> str:
    return str(_read_frontmatter(repo / rel_path).get("status") or "").lower()


def _is_stub_content(repo: Path, rel_path: str) -> bool:
    status = _frontmatter_status(repo, rel_path)
    text = _read_markdown_text(repo / rel_path).lower()
    return status == "stub" or "public stub" in text or "[from state]" in text


def _parse_date(value: Any, fallback_path: Path) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            pass
    match = re.match(r"(\d{4}-\d{2}-\d{2})", fallback_path.name)
    if match:
        try:
            return date.fromisoformat(match.group(1))
        except ValueError:
            return None
    return None


def _parse_explicit_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError:
            return None
    return None


def _relative_markdown_files(repo: Path, folder: str) -> list[Path]:
    root = repo / folder
    if not root.exists():
        return []
    return sorted(
        (path for path in root.rglob("*.md") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )


def _file_summary(
    repo: Path, path: Path, frontmatter: dict[str, Any] | None = None
) -> dict[str, Any]:
    meta = frontmatter if frontmatter is not None else _read_frontmatter(path)
    item_date = _parse_date(meta.get("date"), path)
    try:
        rel = path.relative_to(repo).as_posix()
    except ValueError:
        rel = str(path)
    return {
        "path": rel,
        "title": _title_from_markdown(path),
        "date": item_date.isoformat() if item_date else "",
        "status": str(meta.get("status", "") or ""),
        "updated_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
    }


def _title_from_markdown(path: Path) -> str:
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if stripped.startswith("# "):
                    return stripped[2:].strip()
    except OSError:
        pass
    return path.stem.replace("-", " ")


def _brain(repo: Path) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for folder in IMPORTANT_DIRS:
        root = repo / folder
        counts[folder] = (
            sum(1 for path in root.rglob("*.md") if path.is_file()) if root.exists() else 0
        )

    decision_files = _relative_markdown_files(repo, "decisions")
    decisions: list[dict[str, Any]] = []
    stale: list[dict[str, Any]] = []
    uncodified: list[dict[str, Any]] = []
    today = date.today()

    for path in decision_files:
        meta = _read_frontmatter(path)
        item = _file_summary(repo, path, meta)
        decisions.append(item)
        status = item["status"].lower()
        decision_date = _parse_date(meta.get("date"), path)
        if status in {"proposed", "running"} and decision_date is not None:
            age_days = (today - decision_date).days
            if age_days > STALE_DECISION_DAYS:
                stale_item = dict(item)
                stale_item["age_days"] = age_days
                stale.append(stale_item)
        # Accepted but never codified: the decision happened, the reference
        # files it should change did not — decision-vs-implementation drift.
        if status == "accepted" and decision_date is not None:
            age_days = (today - decision_date).days
            if age_days > UNCODIFIED_DECISION_DAYS:
                uncodified_item = dict(item)
                uncodified_item["age_days"] = age_days
                uncodified.append(uncodified_item)

    research_files = _relative_markdown_files(repo, "research")
    research: list[dict[str, Any]] = []
    stale_research: list[dict[str, Any]] = []
    for path in research_files:
        meta = _read_frontmatter(path)
        item = _file_summary(repo, path, meta)
        research.append(item)
        research_date = _parse_date(meta.get("date"), path)
        if research_date is not None:
            age_days = (today - research_date).days
            if age_days > STALE_RESEARCH_DAYS:
                stale_item = dict(item)
                stale_item["age_days"] = age_days
                stale_research.append(stale_item)
    bets = _bets(repo)
    push_facts = pushes_mod.facts(repo)

    return {
        "counts": counts,
        "recent_decisions": decisions[:5],
        "recent_decisions_total": len(decisions),
        "stale_decisions": stale[:5],
        "stale_decisions_total": len(stale),
        "uncodified_decisions": uncodified[:5],
        "uncodified_decisions_total": len(uncodified),
        "recent_research": research[:5],
        "recent_research_total": len(research),
        "stale_research": stale_research[:5],
        "stale_research_total": len(stale_research),
        "bets": bets,
        "pushes": push_facts,
    }


def _bet_summary(repo: Path, path: Path) -> dict[str, Any]:
    meta = _read_frontmatter(path)
    opened = _parse_date(meta.get("opened"), path)
    deadline = _parse_explicit_date(meta.get("deadline"))
    try:
        rel = path.relative_to(repo).as_posix()
    except ValueError:
        rel = str(path)
    channels = meta.get("channels")
    if not isinstance(channels, list):
        channels = []
    money_path = _bet_money_path_summary(meta, path)
    exit_criteria = _bet_exit_criteria(meta, today=date.today())
    return {
        "path": rel,
        "title": _title_from_markdown(path),
        "status": str(meta.get("status", "") or ""),
        "stage": str(meta.get("stage", "") or ""),
        "commitment": _bet_commitment_summary(meta),
        "opened": opened.isoformat() if opened else "",
        "deadline": deadline.isoformat() if deadline else "",
        "appetite": str(meta.get("appetite", "") or ""),
        "appetite_tier": _bet_appetite_tier(meta),
        "hypothesis": str(meta.get("hypothesis", "") or ""),
        "metric": str(meta.get("metric", "") or ""),
        "target": str(meta.get("target", "") or ""),
        "result": str(meta.get("result", "") or ""),
        "money_path": money_path,
        "exit_criteria": exit_criteria,
        "public": bool(meta.get("public", False)),
        "channels": [str(channel) for channel in channels if isinstance(channel, str)],
        "updated_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
    }


def _bet_commitment_summary(meta: dict[str, Any]) -> dict[str, str] | None:
    raw = meta.get("commitment")
    if not isinstance(raw, dict):
        return None
    return {
        key: str(raw.get(key) or "").strip() for key in ("action", "cadence", "owner", "evidence")
    }


def _bet_appetite_tier(meta: dict[str, Any]) -> str:
    tier = meta.get("appetite_tier")
    if isinstance(tier, str) and tier.strip().lower() in BET_APPETITE_TIERS:
        return tier.strip().lower()
    appetite = meta.get("appetite")
    if isinstance(appetite, str) and appetite.strip().lower() in BET_APPETITE_TIERS:
        return appetite.strip().lower()
    return ""


def _bet_money_path_summary(meta: dict[str, Any], path: Path) -> dict[str, Any]:
    raw = meta.get("money_path")
    if not isinstance(raw, dict):
        return {
            "declared": False,
            "required": False,
            "bet_id": "",
            "expected_bet_id": path.stem,
            "anchor_required_before": "",
            "exposure_cap": None,
        }
    exposure_cap = raw.get("exposure_cap")
    cap: dict[str, Any] | None = None
    if isinstance(exposure_cap, dict):
        amount = exposure_cap.get("amount")
        currency = exposure_cap.get("currency")
        cap = {
            "amount": amount
            if isinstance(amount, int | float) and not isinstance(amount, bool)
            else None,
            "currency": str(currency or "").strip(),
        }
    return {
        "declared": True,
        "required": bool(raw.get("required")),
        "bet_id": str(raw.get("bet_id") or "").strip(),
        "expected_bet_id": path.stem,
        "anchor_required_before": str(raw.get("anchor_required_before") or "").strip(),
        "exposure_cap": cap,
    }


def _bet_metric_values(meta: dict[str, Any]) -> dict[str, Any]:
    for key in ("metrics", "metric_values"):
        value = meta.get(key)
        if isinstance(value, dict):
            return {str(metric): current for metric, current in value.items()}
    return {}


def _coerce_signal_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "")
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _compare_signal(current: Any, comparator: str, threshold: Any) -> bool | None:
    current_number = _coerce_signal_number(current)
    threshold_number = _coerce_signal_number(threshold)
    if current_number is not None and threshold_number is not None:
        if comparator == "<":
            return current_number < threshold_number
        if comparator == "<=":
            return current_number <= threshold_number
        if comparator == "==":
            return current_number == threshold_number
        if comparator == ">=":
            return current_number >= threshold_number
        if comparator == ">":
            return current_number > threshold_number
        if comparator == "!=":
            return current_number != threshold_number
    if comparator == "==":
        return str(current) == str(threshold)
    if comparator == "!=":
        return str(current) != str(threshold)
    return None


def _evaluate_bet_signal(
    signal: dict[str, Any],
    *,
    metrics: dict[str, Any],
    today: date,
) -> dict[str, Any]:
    metric = str(signal.get("metric") or "").strip()
    comparator = str(signal.get("comparator") or "").strip()
    threshold = signal.get("threshold")
    by_date = _parse_explicit_date(signal.get("by"))
    current_value = metrics.get(metric) if metric else None
    base = {
        "id": str(signal.get("id") or metric or "unnamed-signal"),
        "metric": metric,
        "comparator": comparator,
        "threshold": threshold,
        "current_value": current_value,
        "by": by_date.isoformat() if by_date else str(signal.get("by") or ""),
        "action": str(signal.get("action") or ""),
        "triggered": False,
        "status": "not_triggered",
    }
    if not metric or comparator not in BET_SIGNAL_COMPARATORS:
        base["status"] = "invalid"
        return base
    if metric not in metrics:
        base["status"] = "missing_metric"
        return base
    matched = _compare_signal(current_value, comparator, threshold)
    if matched is None:
        base["status"] = "invalid"
        return base
    if by_date is not None and by_date > today:
        base["status"] = "pending"
        return base
    base["triggered"] = bool(matched)
    base["status"] = "triggered" if matched else "not_triggered"
    return base


def _bet_exit_criteria(meta: dict[str, Any], *, today: date) -> dict[str, Any]:
    rubric = meta.get("kill_rubric")
    if not isinstance(rubric, dict):
        return {
            "declared": False,
            "missing": True,
            "failure_signals": [],
            "double_down_signals": [],
            "triggered_failure_signals": [],
            "triggered_double_down_signals": [],
            "metrics_source": "",
        }
    metrics = _bet_metric_values(meta)
    failure_signals = [
        _evaluate_bet_signal(signal, metrics=metrics, today=today)
        for signal in rubric.get("failure_signals") or []
        if isinstance(signal, dict)
    ]
    double_down_signals = [
        _evaluate_bet_signal(signal, metrics=metrics, today=today)
        for signal in rubric.get("double_down_signals") or []
        if isinstance(signal, dict)
    ]
    return {
        "declared": True,
        "missing": False,
        "failure_signals": failure_signals,
        "double_down_signals": double_down_signals,
        "triggered_failure_signals": [
            signal for signal in failure_signals if signal.get("triggered")
        ],
        "triggered_double_down_signals": [
            signal for signal in double_down_signals if signal.get("triggered")
        ],
        "metrics_source": "frontmatter.metrics"
        if "metrics" in meta
        else "frontmatter.metric_values"
        if "metric_values" in meta
        else "",
    }


def _bet_sort_key(item: dict[str, Any]) -> tuple[str, str]:
    deadline = str(item.get("deadline") or "9999-12-31")
    return (deadline, str(item.get("path") or ""))


def _bets(repo: Path) -> dict[str, Any]:
    bet_items = [_bet_summary(repo, path) for path in _relative_markdown_files(repo, "bets")]
    active = [
        item for item in bet_items if str(item.get("status", "")).lower() in ACTIVE_BET_STATUSES
    ]
    active.sort(key=_bet_sort_key)
    today = date.today()
    due_soon: list[dict[str, Any]] = []
    overdue: list[dict[str, Any]] = []
    for item in active:
        deadline = _parse_explicit_date(item.get("deadline"))
        if deadline is None:
            continue
        days_until = (deadline - today).days
        if days_until < 0:
            overdue_item = dict(item)
            overdue_item["days_overdue"] = abs(days_until)
            overdue.append(overdue_item)
        elif days_until <= 7:
            due_item = dict(item)
            due_item["days_until_deadline"] = days_until
            due_soon.append(due_item)
    missing_exit_criteria = [
        item for item in active if (item.get("exit_criteria") or {}).get("missing")
    ]
    triggered_failure_signals = [
        {
            "path": item.get("path"),
            "title": item.get("title"),
            "signal": signal,
        }
        for item in active
        for signal in (item.get("exit_criteria") or {}).get("triggered_failure_signals", [])
    ]
    triggered_double_down_signals = [
        {
            "path": item.get("path"),
            "title": item.get("title"),
            "signal": signal,
        }
        for item in active
        for signal in (item.get("exit_criteria") or {}).get("triggered_double_down_signals", [])
    ]
    return {
        "active": active[:5],
        "due_soon": due_soon[:5],
        "overdue": overdue[:5],
        "recent": bet_items[:5],
        "exit_criteria": {
            "missing": missing_exit_criteria[:5],
            "triggered_failure_signals": triggered_failure_signals[:10],
            "triggered_double_down_signals": triggered_double_down_signals[:10],
        },
    }


def _file_path_from_graph_id(value: Any) -> str:
    if not isinstance(value, str) or not value.startswith("file:"):
        return ""
    return value[len("file:") :]


def _relationship_adjacency(edges: list[dict[str, Any]]) -> dict[str, dict[str, set[str]]]:
    adjacency: dict[str, dict[str, set[str]]] = {}
    for edge in edges:
        rel_type = str(edge.get("rel_type") or edge.get("type") or "")
        source = _file_path_from_graph_id(edge.get("source"))
        target = _file_path_from_graph_id(edge.get("target"))
        if not rel_type or not source or not target:
            continue
        adjacency.setdefault(source, {}).setdefault(rel_type, set()).add(target)
        adjacency.setdefault(target, {}).setdefault(rel_type, set()).add(source)
    return adjacency


def _linked_push_paths_for_bet(
    adjacency: dict[str, dict[str, set[str]]],
    bet_path: str,
    push_paths: set[str],
) -> set[str]:
    direct_pushes = _linked_paths(adjacency, bet_path, "push")
    reverse_bet_links = _linked_paths(adjacency, bet_path, "bet") & push_paths
    return direct_pushes | reverse_bet_links


def _relationship_slug(value: str) -> str:
    lowered = value.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return slug or "unknown"


def _coerce_relationship_refs(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def _is_hidden_or_generated(path: Path, repo: Path) -> bool:
    try:
        rel_parts = path.relative_to(repo).parts
    except ValueError:
        return True
    is_bundled_data = rel_parts[:2] == ("mb", "_data") or rel_parts[:1] == ("_data",)
    return (
        any(
            part.startswith(".") or part in {"__pycache__", "node_modules", ".venv", "venv"}
            for part in rel_parts
        )
        or is_bundled_data
    )


def _relationship_markdown_files(repo: Path) -> list[Path]:
    return [
        path
        for path in sorted(repo.rglob("*.md"))
        if path.is_file() and not _is_hidden_or_generated(path, repo)
    ]


def _resolve_relationship_ref(repo: Path, ref: str) -> Path | None:
    clean_ref = relationships.clean_ref(ref)
    if not clean_ref:
        return None
    target = (repo / clean_ref).resolve()
    try:
        target.relative_to(repo)
    except ValueError:
        return None
    return target


def _relationship_reference_edges(repo: Path) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    seen_edges: set[tuple[str, str, str, tuple[tuple[str, str], ...]]] = set()
    if not repo.exists():
        return edges

    for file_path in _relationship_markdown_files(repo):
        frontmatter = _read_frontmatter(file_path)
        if not frontmatter:
            continue
        source_rel = file_path.relative_to(repo).as_posix()
        source_id = f"file:{source_rel}"
        for field in relationships.relationship_fields_for_source(source_rel):
            rel_type = relationships.normalize_relationship(
                field,
                source_path=source_rel,
                fallback=field,
            )
            for ref in _coerce_relationship_refs(frontmatter.get(field)):
                clean_ref = relationships.clean_ref(ref)
                if not clean_ref and not relationships.is_external_ref(ref):
                    continue
                target = _resolve_relationship_ref(repo, ref)
                if target is not None and target.exists():
                    target_id = f"file:{target.relative_to(repo).as_posix()}"
                elif relationships.is_external_ref(ref):
                    target_id = f"external:{_relationship_slug(ref)}"
                else:
                    target_id = f"missing:{_relationship_slug(ref)}"
                evidence = {"kind": "frontmatter", "field": field, "path": source_rel}
                key = (source_id, target_id, rel_type, tuple(sorted(evidence.items())))
                if key in seen_edges:
                    continue
                seen_edges.add(key)
                edges.append(
                    {
                        "source": source_id,
                        "target": target_id,
                        "type": field,
                        "rel_type": rel_type,
                        "original_field": field,
                        "evidence": evidence,
                        "target_ref": ref,
                    }
                )
    return edges


def _linked_paths(
    adjacency: dict[str, dict[str, set[str]]],
    path: str,
    rel_type: str,
) -> set[str]:
    return adjacency.get(path, {}).get(rel_type, set())


def _offer_summaries(repo: Path) -> list[dict[str, Any]]:
    paths: list[Path] = []
    for folder in ("core/offers", "reference/core/offers"):
        paths.extend(
            path for path in _relative_markdown_files(repo, folder) if path.name == "offer.md"
        )
    for rel in ("core/offer.md", "reference/core/offer.md"):
        path = repo / rel
        if path.is_file():
            paths.append(path)
    unique_paths = sorted(set(paths), key=lambda path: path.stat().st_mtime, reverse=True)
    return [_file_summary(repo, path, _read_frontmatter(path)) for path in unique_paths]


def _coerce_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str) and item.strip()]
    return []


def _playbook_summary(repo: Path, path: Path) -> dict[str, Any]:
    meta = _read_frontmatter(path)
    try:
        rel = path.relative_to(repo).as_posix()
    except ValueError:
        rel = str(path)
    push_path = ""
    if path.parent.name == "playbooks" and path.parent.parent.name:
        push_path = f"pushes/{path.parent.parent.name}/push.md"
    approval_raw = meta.get("approval")
    approval: dict[str, Any] = approval_raw if isinstance(approval_raw, dict) else {}
    state_raw = meta.get("state")
    state: dict[str, Any] = state_raw if isinstance(state_raw, dict) else {}
    return {
        "path": rel,
        "title": _title_from_markdown(path),
        "status": str(meta.get("status", "") or ""),
        "push": str(meta.get("push", "") or ""),
        "resolved_push": push_path,
        "platform": str(meta.get("platform", "") or ""),
        "provider": str(meta.get("provider", "") or ""),
        "provider_boundary": str(meta.get("provider_boundary", "") or ""),
        "approval": {
            "required": bool(approval.get("required")),
            "status": str(approval.get("status", "") or ""),
            "approved_by": str(approval.get("approved_by", "") or ""),
            "approved_at": str(approval.get("approved_at", "") or ""),
        },
        "linked_outcomes": _coerce_string_list(meta.get("linked_outcomes")),
        "provider_refs_recorded": bool(state.get("provider_refs")),
        "updated_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"),
    }


def _playbook_summaries(repo: Path) -> list[dict[str, Any]]:
    return [
        _playbook_summary(repo, path)
        for path in sorted(repo.glob("pushes/*/playbooks/*.md"))
        if path.is_file()
    ]


def _gap(
    *,
    gap_id: str,
    severity: str,
    summary: str,
    records: list[dict[str, Any]],
    repair: str,
) -> dict[str, Any]:
    return {
        "id": gap_id,
        "severity": severity,
        "summary": summary,
        "count": len(records),
        "evidence": [str(item.get("path") or item.get("source") or "") for item in records[:5]],
        "records": records[:5],
        "repair": repair,
        "safe_to_share": True,
    }


def _playbook_health(
    repo: Path,
    *,
    brain: dict[str, Any],
) -> dict[str, Any]:
    push_report = brain.get("pushes") or {}
    pushes = [
        item
        for item in push_report.get("records", [])
        if isinstance(item, dict) and item.get("source") == "canonical"
    ]
    playbooks = _playbook_summaries(repo)
    playbooks_by_push: dict[str, list[dict[str, Any]]] = {}
    for playbook in playbooks:
        push_path = str(playbook.get("resolved_push") or "")
        if push_path:
            playbooks_by_push.setdefault(push_path, []).append(playbook)

    pushes_without_playbook = [
        item
        for item in pushes
        if str(item.get("status") or "").lower() in PUSH_STATUSES_EXPECTING_PLAYBOOK
        and not playbooks_by_push.get(str(item.get("path") or ""))
    ]
    pending_status = [
        item
        for item in playbooks
        if str(item.get("status") or "").lower() in PLAYBOOK_STATUSES_NEEDING_ATTENTION
    ]
    approval_needed = [
        item
        for item in playbooks
        if bool((item.get("approval") or {}).get("required"))
        and str(item.get("status") or "").lower() not in {"canceled", "retired"}
        and str((item.get("approval") or {}).get("status") or "").lower()
        in PLAYBOOK_APPROVAL_STATUSES_NEEDING_ATTENTION
    ]
    completed_without_outcome: list[dict[str, Any]] = []
    for push in pushes:
        if str(push.get("status") or "").lower() not in COMPLETED_PUSH_STATUSES:
            continue
        for playbook in playbooks_by_push.get(str(push.get("path") or ""), []):
            if not playbook.get("linked_outcomes"):
                item = dict(playbook)
                item["push_status"] = str(push.get("status") or "")
                completed_without_outcome.append(item)
    provider_boundary_attention = [
        item
        for item in playbooks
        if str(item.get("provider_boundary") or "").lower()
        in PLAYBOOK_PROVIDER_BOUNDARIES_NEEDING_ATTENTION
        and str(item.get("status") or "").lower() not in {"canceled", "retired"}
    ]

    gaps = [
        _gap(
            gap_id="pushes_without_playbook",
            severity="warn",
            summary=(
                f"{len(pushes_without_playbook)} active/planned push(es) need a playbook run."
            ),
            records=pushes_without_playbook,
            repair="Add a run record under `pushes/<push>/playbooks/` for each active push.",
        )
        if pushes_without_playbook
        else None,
        _gap(
            gap_id="pending_playbook_statuses",
            severity="warn",
            summary=f"{len(pending_status)} playbook run(s) are still draft/planned.",
            records=pending_status,
            repair="Review each playbook run and move it toward approved, active, or completed.",
        )
        if pending_status
        else None,
        _gap(
            gap_id="playbook_approval_needed",
            severity="warn",
            summary=f"{len(approval_needed)} playbook run(s) still need approval.",
            records=approval_needed,
            repair="Record approval status before publishing, spending, or mutating providers.",
        )
        if approval_needed
        else None,
        _gap(
            gap_id="completed_playbooks_without_outcome",
            severity="warn",
            summary=(
                f"{len(completed_without_outcome)} completed-push playbook run(s) "
                "need an outcome link."
            ),
            records=completed_without_outcome,
            repair="Add `linked_outcomes` to the playbook after the push is reviewed.",
        )
        if completed_without_outcome
        else None,
        _gap(
            gap_id="manual_provider_boundaries",
            severity="info",
            summary=(
                f"{len(provider_boundary_attention)} playbook run(s) are still "
                "plan/manual provider work."
            ),
            records=provider_boundary_attention,
            repair=(
                "Confirm the operator expects manual provider steps before treating this "
                "as automation."
            ),
        )
        if provider_boundary_attention
        else None,
    ]
    active_gaps = [gap_item for gap_item in gaps if gap_item is not None]
    return {
        "ok": not active_gaps,
        "source": "mb status playbook scan",
        "summary": {
            "gaps": len(active_gaps),
            "warnings": len([item for item in active_gaps if item["severity"] == "warn"]),
            "info": len([item for item in active_gaps if item["severity"] == "info"]),
            "playbooks": len(playbooks),
            "pushes_without_playbook": len(pushes_without_playbook),
            "pending_playbook_statuses": len(pending_status),
            "playbook_approval_needed": len(approval_needed),
            "completed_playbooks_without_outcome": len(completed_without_outcome),
            "manual_provider_boundaries": len(provider_boundary_attention),
        },
        "gaps": active_gaps,
        "sections": {
            "pushes": {
                "records": len(pushes),
                "expecting_playbook": len(
                    [
                        item
                        for item in pushes
                        if str(item.get("status") or "").lower() in PUSH_STATUSES_EXPECTING_PLAYBOOK
                    ]
                ),
                "without_playbook": pushes_without_playbook[:5],
            },
            "playbooks": {
                "records": playbooks[:5],
                "pending_status": pending_status[:5],
                "approval_needed": approval_needed[:5],
                "completed_without_outcome": completed_without_outcome[:5],
                "provider_boundary_attention": provider_boundary_attention[:5],
            },
        },
        "safe_to_share": True,
    }


def _money_amount(
    *, commodity: str = "USD", decimal_mantissa: int = 0, decimal_places: int = 2
) -> dict[str, Any]:
    scale = 10**decimal_places
    whole = abs(decimal_mantissa) // scale
    fraction = abs(decimal_mantissa) % scale
    sign = "-" if decimal_mantissa < 0 else ""
    if commodity == "USD" and decimal_places == 2:
        display = f"{sign}${whole:,}.{fraction:02d}"
    elif decimal_places > 0:
        display = f"{sign}{whole:,}.{fraction:0{decimal_places}d} {commodity}".strip()
    else:
        display = f"{sign}{whole:,} {commodity}".strip()
    return {
        "commodity": commodity,
        "decimal_mantissa": decimal_mantissa,
        "decimal_places": decimal_places,
        "display": display,
    }
