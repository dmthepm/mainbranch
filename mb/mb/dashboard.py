"""Local read-only dashboard rendering for Main Branch business repos."""

# ruff: noqa: E501

from __future__ import annotations

import html
import json
import re
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

import yaml

from mb import __version__
from mb import connect as connect_mod
from mb import status as status_mod
from mb.durable import atomic_write_text
from mb.gitignore import gitignore_problem

DASHBOARD_SCHEMA_VERSION = "0.1"
DEFAULT_OUTPUT_PATH = Path(".mb") / "dashboard" / "index.html"


class DashboardOutputError(ValueError):
    """Raised when the dashboard output path is not safe to write."""


SECRET_VALUE_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{12,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{12,}\b"),
    re.compile(r"\bEAAB[A-Za-z0-9]{12,}\b"),
)
ABSOLUTE_PATH_PATTERN = re.compile(
    r"(?<![\w.:-])(?:/(?:Users|private|var|tmp|home|Volumes|opt|usr)/[^\s'\"<>)]+)"
)
SENSITIVE_KEY_PARTS = (
    "token",
    "secret",
    "password",
    "api_key",
    "apikey",
    "account_id",
    "business_id",
    "repo_id",
    "path_absolute",
)
SENSITIVE_EXACT_KEYS = {"credential", "credentials", "credential_ref"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_text(value: Any) -> str:
    text = str(value or "")
    for pattern in SECRET_VALUE_PATTERNS:
        text = pattern.sub("[redacted secret]", text)
    return ABSOLUTE_PATH_PATTERN.sub("[local path]", text)


def _safe_value(value: Any) -> Any:
    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            lowered = key_text.lower()
            if lowered in SENSITIVE_EXACT_KEYS or any(
                part in lowered for part in SENSITIVE_KEY_PARTS
            ):
                safe[key_text] = "[redacted]"
            else:
                safe[key_text] = _safe_value(item)
        return safe
    if isinstance(value, list):
        return [_safe_value(item) for item in value]
    if isinstance(value, str):
        return _safe_text(value)
    return value


def _repo_relative(path: Path, repo: Path) -> str:
    try:
        return path.resolve().relative_to(repo.resolve()).as_posix()
    except ValueError:
        return path.name


def _first_string(value: Any, fallback: str = "") -> str:
    return value if isinstance(value, str) and value.strip() else fallback


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_safe_text(item) for item in value if isinstance(item, str) and item.strip()]
    if isinstance(value, str) and value.strip():
        return [_safe_text(value)]
    return []


def _int_value(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return default
    return default


def _bool_or_none(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _component_state(component: dict[str, Any]) -> str:
    level = _int_value(component.get("level"))
    missing = component.get("missing") if isinstance(component.get("missing"), list) else []
    status = _safe_text(component.get("status"))
    if status in {"ready", "ok", "field_tested", "instrumented"} or (level >= 3 and not missing):
        return "ready"
    if level > 0:
        return "partial"
    return "blocked"


def _component_card(component_id: str, title: str, component: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": component_id,
        "title": title,
        "state": _component_state(component),
        "level": _int_value(component.get("level")),
        "label": _safe_text(component.get("label")),
        "summary": _safe_text(component.get("summary")),
        "missing": _string_list(component.get("missing")),
        "evidence": _string_list(component.get("evidence"))[:5],
        "paths": _string_list(component.get("paths"))[:5],
        "next_route": _safe_text(component.get("recommended_route")),
    }


def _file_exists_card(repo: Path, card_id: str, title: str, paths: list[str]) -> dict[str, Any]:
    existing = [path for path in paths if (repo / path).exists()]
    return {
        "id": card_id,
        "title": title,
        "state": "ready" if existing else "blocked",
        "summary": f"{title} source found." if existing else f"No {title.lower()} source found.",
        "paths": existing or paths,
        "missing": [] if existing else [card_id],
        "evidence": existing[:5],
    }


def _business_readiness(repo: Path, report: dict[str, Any]) -> dict[str, Any]:
    objects = (report.get("money_path") or {}).get("objects") or {}
    checks = [
        _component_card("offer", "Offer", _dict(objects.get("offer"))),
        _component_card("audience", "Audience", _dict(objects.get("audience"))),
        _component_card("proof", "Proof", _dict(objects.get("proof"))),
        _component_card(
            "customer_language",
            "Customer Language",
            _dict(objects.get("customer_progress")),
        ),
        _file_exists_card(
            repo,
            "brand_visual_style",
            "Brand Visual Style",
            [
                "core/brand/visual-style.md",
                "core/brand/style.md",
                "core/brand.md",
            ],
        ),
        _current_push_card(report),
        _checkpoint_card(report),
    ]
    ready = len([item for item in checks if item["state"] == "ready"])
    partial = len([item for item in checks if item["state"] == "partial"])
    blocked = len([item for item in checks if item["state"] == "blocked"])
    if blocked:
        state = "blocked"
    elif partial:
        state = "partial"
    else:
        state = "ready"
    return {
        "state": state,
        "summary": {
            "ready": ready,
            "partial": partial,
            "blocked": blocked,
            "total": len(checks),
        },
        "checks": checks,
    }


def _current_push_card(report: dict[str, Any]) -> dict[str, Any]:
    pushes = [item for item in report.get("active_pushes") or [] if isinstance(item, dict)]
    if not pushes:
        pushes = [
            item
            for item in report.get("pushes") or []
            if isinstance(item, dict)
            and str(item.get("status") or "").lower() in {"planned", "active", "paused"}
        ][:3]
    first = pushes[0] if pushes else {}
    title = _safe_text(first.get("title")) if first else ""
    status = _safe_text(first.get("status")) if first else ""
    return {
        "id": "current_push",
        "title": "Current Push",
        "state": "ready" if pushes else "blocked",
        "summary": f"{title} is {status}." if pushes else "No active or planned push found.",
        "paths": [_safe_text(item.get("path")) for item in pushes[:3] if item.get("path")],
        "missing": [] if pushes else ["active_or_planned_push"],
        "evidence": [title] if title else [],
        "records": [_push_summary(item) for item in pushes[:3]],
    }


def _checkpoint_card(report: dict[str, Any]) -> dict[str, Any]:
    journal = _dict(report.get("journal"))
    summary = _dict(journal.get("summary"))
    events = _int_value(summary.get("events"))
    groups = [item for item in journal.get("groups") or [] if isinstance(item, dict)]
    return {
        "id": "checkpoints",
        "title": "Saved Checkpoints",
        "state": "ready" if events else "partial",
        "summary": (
            f"{events} recent journal event(s) available."
            if events
            else "No recent checkpoint journal events available."
        ),
        "paths": [],
        "missing": [] if events else ["recent_checkpoint_history"],
        "evidence": [_safe_text(item.get("label")) for item in groups[:3] if item.get("label")],
        "events": events,
    }


def _push_summary(push: dict[str, Any]) -> dict[str, Any]:
    goal = _dict(push.get("goal"))
    return {
        "path": _safe_text(push.get("path")),
        "title": _safe_text(push.get("title")),
        "slug": _safe_text(push.get("slug")),
        "kind": _safe_text(push.get("kind")),
        "status": _safe_text(push.get("status")),
        "health": _safe_text(push.get("health")),
        "channels": _string_list(push.get("channels")),
        "goal": _safe_value(goal),
        "review_on": _safe_text(push.get("review_on")),
    }


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _image_index_records(repo: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(repo.glob("pushes/*/image-index.md"), key=lambda item: item.stat().st_mtime):
        parsed = _parse_image_index(path)
        if not parsed:
            continue
        records.append(_image_index_summary(repo, path, parsed))
    return list(reversed(records))


def _parse_image_index(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {}
    if "```yaml" in text:
        try:
            yaml_text = text.split("```yaml", 1)[1].split("```", 1)[0]
            loaded = yaml.safe_load(yaml_text) or {}
        except (IndexError, yaml.YAMLError):
            return {}
        return loaded if isinstance(loaded, dict) else {}
    if text.startswith("---"):
        try:
            yaml_text = text.split("---", 2)[1]
            loaded = yaml.safe_load(yaml_text) or {}
        except (IndexError, yaml.YAMLError):
            return {}
        return loaded if isinstance(loaded, dict) else {}
    return {}


def _image_index_summary(repo: Path, path: Path, record: dict[str, Any]) -> dict[str, Any]:
    concepts = [item for item in record.get("concepts") or [] if isinstance(item, dict)]
    assets = [item for item in record.get("assets") or [] if isinstance(item, dict)]
    calibration = _dict(record.get("visual_calibration_result"))
    gate = _dict(record.get("ad_readiness_gate"))
    dashboard_readiness = _dict(record.get("dashboard_readiness"))
    return {
        "path": _repo_relative(path, repo),
        "push_slug": path.parent.name,
        "state": _safe_text(calibration.get("state") or record.get("state") or "recorded"),
        "candidate_count": _int_value(
            _dict(record.get("batch_plan")).get("candidate_count"),
            default=len(concepts) or len(assets),
        ),
        "generated_count": _int_value(
            calibration.get("generated_count") or record.get("generated_count")
        ),
        "best_candidate": _safe_text(
            calibration.get("best_candidate") or record.get("best_candidate")
        ),
        "best_playbook": _safe_text(
            calibration.get("best_playbook") or record.get("best_playbook")
        ),
        "all_rejected": _bool_or_none(
            calibration.get("all_rejected") or record.get("all_rejected")
        ),
        "overlay_tested": bool(calibration.get("overlay_tested") or record.get("overlay_tested")),
        "main_failure_modes": _string_list(
            calibration.get("main_failure_modes") or record.get("main_failure_modes")
        ),
        "ad_readiness_gate": _ad_gate_summary(gate),
        "dashboard_next_actions": _string_list(dashboard_readiness.get("next_actions"))[:6],
        "source_bites": _source_bites(record.get("selected_source_bites")),
        "playbooks": _creative_playbook_summaries(concepts),
        "candidates": _candidate_summaries(concepts, assets),
        "provider_readiness": _image_provider_readiness(record, assets, dashboard_readiness),
    }


def _ad_gate_summary(gate: dict[str, Any]) -> dict[str, Any]:
    return {
        "state": _safe_text(gate.get("state") or "not_recorded"),
        "status": _safe_text(gate.get("status")),
        "required_fields": _string_list(gate.get("required_fields")),
        "hard_stop_missing_fields": _string_list(
            gate.get("hard_stop_missing_fields") or gate.get("hard_stop_missing")
        ),
        "soft_warning_missing_fields": _string_list(
            gate.get("soft_warning_missing_fields") or gate.get("soft_warning_missing")
        ),
        "allowed_actions": _string_list(gate.get("allowed_actions")),
        "blocked_actions": _string_list(gate.get("blocked_actions")),
        "rule": _safe_text(gate.get("rule")),
    }


def _source_bites(value: Any) -> list[dict[str, Any]]:
    bites = [item for item in value or [] if isinstance(item, dict)]
    return [
        {
            "concept_id": _safe_text(item.get("concept_id")),
            "source_type": _safe_text(item.get("source_type")),
            "source_file": _safe_text(item.get("source_file")),
            "extracted_phrase": _safe_text(item.get("extracted_phrase")),
            "visual_translation": _safe_text(item.get("visual_translation")),
        }
        for item in bites[:9]
    ]


def _creative_playbook_summaries(concepts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for concept in concepts:
        playbook = _dict(concept.get("creative_playbook"))
        playbook_id = _safe_text(
            concept.get("creative_playbook_id") or playbook.get("id") or concept.get("concept_id")
        )
        if playbook_id in seen:
            continue
        seen.add(playbook_id)
        summaries.append(
            {
                "id": playbook_id,
                "status": _safe_text(playbook.get("status") or concept.get("status")),
                "concept_id": _safe_text(concept.get("concept_id")),
                "router_reason": _safe_text(concept.get("router_reason")),
                "playbook_fit": _safe_value(_dict(concept.get("playbook_fit"))),
                "likely_click_reason": _safe_text(
                    _dict(concept.get("ad_quality")).get("likely_click_reason")
                    or concept.get("likely_click_reason")
                ),
            }
        )
    return summaries[:8]


def _candidate_summaries(
    concepts: list[dict[str, Any]], assets: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    assets_by_concept: dict[str, dict[str, Any]] = {}
    for asset in assets:
        concept_id = _safe_text(asset.get("concept_id"))
        if concept_id and concept_id not in assets_by_concept:
            assets_by_concept[concept_id] = asset
    summaries: list[dict[str, Any]] = []
    for concept in concepts[:12]:
        concept_id = _safe_text(concept.get("concept_id"))
        review = _dict(concept.get("review"))
        asset = assets_by_concept.get(concept_id, {})
        summaries.append(
            {
                "concept_id": concept_id,
                "asset_id": _safe_text(asset.get("asset_id")),
                "state": _safe_text(asset.get("state") or concept.get("status")),
                "creative_playbook_id": _safe_text(
                    concept.get("creative_playbook_id")
                    or _dict(concept.get("creative_playbook")).get("id")
                ),
                "source_phrase": _safe_text(
                    _dict(concept.get("source_bite")).get("extracted_phrase")
                ),
                "review_status": _safe_text(review.get("status") or asset.get("review_status")),
                "decision": _safe_text(review.get("decision")),
                "visual_quality": _safe_value(_dict(review.get("visual_quality"))),
                "ad_quality": _safe_value(_dict(review.get("ad_quality"))),
                "risk": _safe_value(_dict(review.get("risk"))),
                "scores": _safe_value(_dict(review.get("scores"))),
                "output_reference": _safe_text(asset.get("output_reference")),
                "blocker_code": _safe_text(asset.get("blocker_code")),
            }
        )
    if summaries:
        return summaries
    return [
        {
            "concept_id": _safe_text(asset.get("concept_id")),
            "asset_id": _safe_text(asset.get("asset_id")),
            "state": _safe_text(asset.get("state")),
            "review_status": _safe_text(asset.get("review_status")),
            "output_reference": _safe_text(asset.get("output_reference")),
            "blocker_code": _safe_text(asset.get("blocker_code")),
        }
        for asset in assets[:12]
    ]


def _image_provider_readiness(
    record: dict[str, Any], assets: list[dict[str, Any]], dashboard_readiness: dict[str, Any]
) -> dict[str, Any]:
    readiness = _dict(dashboard_readiness.get("provider_readiness"))
    provider = _safe_text(readiness.get("provider") or record.get("provider") or "openai")
    model = _safe_text(readiness.get("model") or record.get("model"))
    states = sorted(
        {
            _safe_text(item.get("credential_state"))
            for item in assets
            if isinstance(item, dict) and item.get("credential_state")
        }
    )
    blockers = sorted(
        {
            _safe_text(item.get("blocker_code"))
            for item in assets
            if isinstance(item, dict) and item.get("blocker_code")
        }
    )
    return {
        "provider": provider,
        "model": model,
        "state": "ready" if states and not blockers else "blocked" if blockers else "not_checked",
        "credential_states": states[:5],
        "blocker_codes": blockers[:5],
        "required_before_generation": _string_list(readiness.get("required_before_generation")),
    }


def _ad_readiness(report: dict[str, Any], image_indexes: list[dict[str, Any]]) -> dict[str, Any]:
    if image_indexes:
        gate = _dict(image_indexes[0].get("ad_readiness_gate"))
        hard = _string_list(gate.get("hard_stop_missing_fields"))
        soft = _string_list(gate.get("soft_warning_missing_fields"))
        state = _safe_text(
            gate.get("state") or ("blocked" if hard else "partial" if soft else "ready")
        )
        return {
            "state": state,
            "source": image_indexes[0]["path"],
            "hard_stop_missing_fields": hard,
            "soft_warning_missing_fields": soft,
            "allowed_actions": _string_list(gate.get("allowed_actions")),
            "blocked_actions": _string_list(gate.get("blocked_actions")),
            "rule": _safe_text(gate.get("rule")),
        }

    objects = (report.get("money_path") or {}).get("objects") or {}
    missing: list[str] = []
    if _component_state(_dict(objects.get("offer"))) == "blocked":
        missing.append("offer")
    if _component_state(_dict(objects.get("audience"))) == "blocked":
        missing.append("audience")
    if not (report.get("active_pushes") or []):
        missing.append("campaign_goal")
    proof_state = _component_state(_dict(objects.get("proof")))
    hard = missing
    soft = []
    if proof_state != "ready":
        soft.append("claim_proof_boundary")
    soft.extend(["source_bites", "image_index", "brand_visual_style"])
    return {
        "state": "blocked" if hard else "partial",
        "source": "mb status --json --peek",
        "hard_stop_missing_fields": hard,
        "soft_warning_missing_fields": soft,
        "allowed_actions": [
            "intake",
            "repo_source_audit",
            "ad_strategy_outline",
            "missing_info_checklist",
            "prompt_only_concepts",
        ],
        "blocked_actions": [
            "final_ad_package_when_hard_stop_missing",
            "provider_image_generation_without_image_index",
            "meta_informed_recommendations_without_approved_summary",
        ],
        "rule": "Record hard-stop ad inputs and source bites before final ads or provider generation.",
    }


def _provider_readiness(repo: Path, image_indexes: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        status = connect_mod.status_all(repo, include_all=True)
    except (ValueError, OSError):
        status = {"providers": [], "summary": {"configured": 0, "healthy": 0, "needs_repair": 0}}
    providers = {
        str(item.get("provider")): item
        for item in status.get("providers") or []
        if isinstance(item, dict)
    }
    meta = _dict(providers.get("meta"))
    openai = _dict(image_indexes[0].get("provider_readiness")) if image_indexes else {}
    media_root = repo / ".mb" / "media"
    return {
        "summary": _safe_value(_dict(status.get("summary"))),
        "providers": [
            _provider_card("meta_ads", "Meta Ads", meta),
            {
                "id": "openai_image_rail",
                "name": "OpenAI image rail",
                "state": _safe_text(openai.get("state") or "not_checked"),
                "ok": openai.get("state") == "ready",
                "summary": _openai_summary(openai, bool(image_indexes)),
                "repair": "Run `mb image smoke-openai --json` after operator approval.",
            },
            {
                "id": "media_storage",
                "name": "Media storage",
                "state": "present" if media_root.exists() else "not_created",
                "ok": media_root.exists(),
                "summary": (
                    "Local media storage exists under `.mb/media`."
                    if media_root.exists()
                    else "No local media storage folder has been created yet."
                ),
                "repair": "Run an approved image rail smoke or configure media storage.",
            },
        ],
    }


def _provider_card(provider_id: str, name: str, provider: dict[str, Any]) -> dict[str, Any]:
    if not provider:
        return {
            "id": provider_id,
            "name": name,
            "state": "not_connected",
            "ok": False,
            "summary": f"{name} is not connected.",
            "repair": "Run `mb connect plan` before wiring provider access.",
        }
    return {
        "id": provider_id,
        "name": name,
        "state": _safe_text(connect_mod.state_label(str(provider.get("state") or ""))),
        "ok": bool(provider.get("ok")),
        "summary": _safe_text(provider.get("summary")),
        "repair": _safe_text(provider.get("repair_command") or provider.get("repair")),
    }


def _openai_summary(openai: dict[str, Any], has_index: bool) -> str:
    if not has_index:
        return "No image-index provider evidence found."
    blockers = _string_list(openai.get("blocker_codes"))
    if blockers:
        return f"Image rail evidence exists, blocked by {', '.join(blockers[:3])}."
    if openai.get("state") == "ready":
        return "Image rail evidence is ready from the latest image index."
    return "Image rail evidence is recorded but not ready."


def _creative_state(image_indexes: list[dict[str, Any]]) -> dict[str, Any]:
    if not image_indexes:
        return {
            "state": "empty",
            "summary": "No push-local image-index.md files found.",
            "image_indexes": [],
            "source_bites": [],
            "playbooks": [],
            "candidates": [],
            "winner": {"best_candidate": "", "best_playbook": "", "all_rejected": None},
        }
    latest = image_indexes[0]
    all_rejected = latest.get("all_rejected")
    state = (
        "winner_selected"
        if latest.get("best_candidate")
        else "all_rejected"
        if all_rejected
        else "review"
    )
    return {
        "state": state,
        "summary": (
            f"{latest.get('candidate_count', 0)} candidate(s), "
            f"{latest.get('generated_count', 0)} generated."
        ),
        "image_indexes": [
            {
                "path": item["path"],
                "push_slug": item["push_slug"],
                "state": item["state"],
                "candidate_count": item["candidate_count"],
                "generated_count": item["generated_count"],
            }
            for item in image_indexes[:5]
        ],
        "source_bites": latest.get("source_bites") or [],
        "playbooks": latest.get("playbooks") or [],
        "candidates": latest.get("candidates") or [],
        "winner": {
            "best_candidate": _safe_text(latest.get("best_candidate")),
            "best_playbook": _safe_text(latest.get("best_playbook")),
            "all_rejected": all_rejected,
            "failure_modes": _string_list(latest.get("main_failure_modes")),
            "overlay_tested": bool(latest.get("overlay_tested")),
        },
    }


def _next_actions(
    report: dict[str, Any], ad_readiness: dict[str, Any], image_indexes: list[dict[str, Any]]
) -> list[dict[str, str]]:
    actions: list[dict[str, str]] = []
    for item in report.get("ranked_actions") or []:
        if not isinstance(item, dict) or item.get("safe_to_share") is False:
            continue
        command = _safe_text(item.get("command"))
        if not command:
            continue
        actions.append(
            {
                "title": _safe_text(item.get("title") or item.get("id")),
                "reason": _safe_text(item.get("operator_summary") or item.get("reason")),
                "command": command,
                "severity": _safe_text(item.get("severity") or "info"),
            }
        )
    for field in _string_list(ad_readiness.get("hard_stop_missing_fields")):
        actions.append(
            {
                "title": f"Fill ad input: {field}",
                "reason": "Ad readiness has a hard stop.",
                "command": "Use `/mb-ads` to collect the missing input before final ads.",
                "severity": "warn",
            }
        )
    if image_indexes:
        for action_text in _string_list(image_indexes[0].get("dashboard_next_actions")):
            actions.append(
                {
                    "title": action_text.replace("_", " ").title(),
                    "reason": "Latest image index marked this as a next action.",
                    "command": action_text,
                    "severity": "info",
                }
            )
    else:
        actions.append(
            {
                "title": "Record image candidate state",
                "reason": "No push-local image-index.md exists yet.",
                "command": "Run `/mb-ads` or `mb image smoke-openai --json` for a safe image-index record.",
                "severity": "info",
            }
        )

    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for action in actions:
        key = action["title"] + action["command"]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(action)
    return deduped[:8]


def collect(repo: str | Path = ".") -> dict[str, Any]:
    """Collect privacy-bounded dashboard facts without mutating the business repo."""

    root = Path(repo).resolve()
    report = status_mod.run(
        str(root),
        update_marker=False,
        validation_cross_refs=False,
    )
    image_indexes = _image_index_records(root)
    business = _business_readiness(root, report)
    ad = _ad_readiness(report, image_indexes)
    providers = _provider_readiness(root, image_indexes)
    creative = _creative_state(image_indexes)
    data = {
        "schema_version": DASHBOARD_SCHEMA_VERSION,
        "generated_at": _utc_now(),
        "generator": {"name": "mainbranch", "version": __version__},
        "safe_to_share": True,
        "read_only": True,
        "source_boundary": {
            "cli": "facts_and_safe_checks",
            "skills": "workflow_and_judgment",
            "repo_files": "memory",
            "dashboard": "visual_map",
        },
        "safe_sources": [
            "mb start --json",
            "mb status --json --peek",
            "mb connect doctor --json",
            "mb ads meta summary --json when approved/ready",
            "push files",
            "image-index.md",
            "local review-board metadata when present",
        ],
        "repo": {
            "name": root.name,
            "looks_like_mainbranch_repo": bool(
                _dict(report.get("repo")).get("looks_like_mainbranch_repo")
            ),
            "git_branch": _safe_text(_dict(report.get("git")).get("branch")),
            "git_dirty": bool(_dict(report.get("git")).get("dirty")),
            "dirty_count": _int_value(_dict(report.get("git")).get("dirty_count")),
            "readiness": _safe_value(_dict(report.get("readiness"))),
        },
        "business_readiness": business,
        "ad_readiness": ad,
        "provider_readiness": providers,
        "creative_state": creative,
        "system_map": _system_map(report, image_indexes),
        "next_actions": _next_actions(report, ad, image_indexes),
        "boundaries": [
            "read_only",
            "no_secrets",
            "no_raw_provider_payloads",
            "no_account_ids",
            "no_private_absolute_paths",
            "no_committed_image_binaries",
        ],
    }
    return cast(dict[str, Any], _safe_value(data))


def _system_map(
    report: dict[str, Any], image_indexes: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    brain = _dict(report.get("brain"))
    counts = _dict(brain.get("counts"))
    playbook_summary = _dict(_dict(report.get("playbook_health")).get("summary"))
    return [
        {
            "section": "Business",
            "items": [
                {"label": "Offer", "count": _int_value(counts.get("core"))},
                {"label": "Audience", "count": 1 if counts.get("core") else 0},
                {"label": "Proof", "count": _int_value(counts.get("core"))},
                {"label": "Brand", "count": _int_value(counts.get("core"))},
                {"label": "Content Strategy", "count": _int_value(counts.get("core"))},
            ],
        },
        {
            "section": "Work",
            "items": [
                {"label": "Bets", "count": _int_value(counts.get("bets"))},
                {"label": "Pushes", "count": _int_value(counts.get("pushes"))},
                {"label": "Decisions", "count": _int_value(counts.get("decisions"))},
                {"label": "Logs", "count": _int_value(counts.get("log"))},
            ],
        },
        {
            "section": "Growth",
            "items": [
                {"label": "Ads", "count": _int_value(counts.get("pushes"))},
                {"label": "Creative", "count": len(image_indexes)},
                {
                    "label": "Image Review Boards",
                    "count": len([item for item in image_indexes if item.get("generated_count")]),
                },
                {"label": "Outcomes", "count": _int_value(counts.get("log"))},
            ],
        },
        {
            "section": "Playbooks",
            "items": [
                {
                    "label": "Push Run Records",
                    "count": _int_value(playbook_summary.get("playbooks")),
                },
                {
                    "label": "Creative Playbooks",
                    "count": len(_creative_state(image_indexes).get("playbooks") or []),
                },
            ],
        },
        {
            "section": "Providers",
            "items": [
                {"label": "Meta", "count": 1},
                {"label": "OpenAI", "count": 1 if image_indexes else 0},
                {"label": "Media Storage", "count": 1},
            ],
        },
        {
            "section": "History",
            "items": [
                {
                    "label": "Checkpoints",
                    "count": _int_value(
                        _dict(_dict(report.get("journal")).get("summary")).get("events")
                    ),
                },
                {
                    "label": "File Timeline",
                    "count": len(report.get("git_activity", {}).get("items") or []),
                },
                {"label": "Decisions", "count": _int_value(counts.get("decisions"))},
            ],
        },
    ]


def build(repo: str | Path = ".", output: str | Path | None = None) -> dict[str, Any]:
    """Write the dashboard HTML and return command output facts."""

    root = Path(repo).resolve()
    output_path = _resolve_output(root, output)
    _refuse_symlinked_output(root, output_path)
    data = collect(root)
    html_text = render_html(data)
    atomic_write_text(output_path, html_text)
    # Self-ignoring output dir: the rendered dashboard is local-only state,
    # and "committed_by_default: False" must be enforced by git, not prose.
    if _is_relative_to(output_path, root):
        ignore_path = output_path.parent / ".gitignore"
        if not gitignore_problem(output_path.parent) and not ignore_path.exists():
            ignore_path.write_text("*\n", encoding="utf-8")
    return {
        "ok": True,
        "schema_version": DASHBOARD_SCHEMA_VERSION,
        "repo": data["repo"],
        "output": {
            "path": _repo_relative(output_path, root)
            if _is_relative_to(output_path, root)
            else str(output_path),
            "inside_repo": _is_relative_to(output_path, root),
            "generated_file": True,
            "committed_by_default": False,
        },
        "dashboard": data,
        "safe_to_share": False,
    }


def open_dashboard(repo: str | Path = ".", output: str | Path | None = None) -> dict[str, Any]:
    """Build the dashboard and open it in the local default browser."""

    result = build(repo=repo, output=output)
    root = Path(repo).resolve()
    output_path = _resolve_output(root, output)
    opened = _open_browser(output_path.resolve().as_uri())
    result["opened"] = bool(opened)
    return result


def _open_browser(uri: str) -> bool:
    return webbrowser.open(uri)


def _resolve_output(repo: Path, output: str | Path | None) -> Path:
    if output is None or str(output).strip() == "":
        return repo / DEFAULT_OUTPUT_PATH
    path = Path(output).expanduser()
    return path if path.is_absolute() else repo / path


def _refuse_symlinked_output(repo: Path, output_path: Path) -> None:
    """Refuse an output path that passes through a symlink stored inside the repo."""
    for candidate in (output_path, *output_path.parents):
        if candidate.is_symlink() and _is_relative_to(candidate.parent, repo):
            link = (candidate.parent.resolve() / candidate.name).relative_to(repo).as_posix()
            raise DashboardOutputError(
                f"{link} is a symlink; Main Branch will not write the dashboard through it. "
                "Replace it with a regular file or folder, or pass --output outside the repo, "
                "then rerun."
            )


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def render_html(data: dict[str, Any]) -> str:
    """Render a self-contained static dashboard."""

    json_blob = html.escape(json.dumps(data, indent=2), quote=False)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Main Branch Dashboard - {html.escape(_safe_text(_dict(data.get("repo")).get("name")))}</title>
  <style>{_css()}</style>
</head>
<body>
  <div class="shell">
    <aside class="sidebar">
      <div class="brand">
        <span class="mark">mb</span>
        <div>
          <p>Main Branch</p>
          <small>Local repo cockpit</small>
        </div>
      </div>
      {_render_system_nav(data)}
    </aside>
    <main class="main">
      {_render_header(data)}
      {_render_state_grid(data)}
      {_render_business(data)}
      {_render_ad(data)}
      {_render_creative(data)}
      {_render_actions(data)}
      <section class="panel compact">
        <div>
          <p class="eyebrow">Source Boundary</p>
          <h2>Read-only visual map</h2>
        </div>
        <pre>{json_blob}</pre>
      </section>
    </main>
  </div>
</body>
</html>
"""


def _render_header(data: dict[str, Any]) -> str:
    repo = _dict(data.get("repo"))
    branch = _safe_text(repo.get("git_branch")) or "unknown branch"
    dirty = "Changed files pending review" if repo.get("git_dirty") else "Clean working tree"
    return f"""
      <header class="hero">
        <div>
          <p class="eyebrow">Generated {html.escape(_safe_text(data.get("generated_at")))}</p>
          <h1>{html.escape(_safe_text(repo.get("name")))} cockpit</h1>
          <p class="lede">A local, read-only map over Main Branch facts, repo memory, provider readiness, and ad creative state.</p>
        </div>
        <div class="hero-card">
          <span class="pill">read-only</span>
          <strong>{html.escape(branch)}</strong>
          <small>{html.escape(dirty)}</small>
        </div>
      </header>
    """


def _render_state_grid(data: dict[str, Any]) -> str:
    cards = [
        ("Business", _dict(data.get("business_readiness")).get("state"), "Core repo readiness"),
        ("Ads", _dict(data.get("ad_readiness")).get("state"), "Hard stops and warnings"),
        ("Providers", _provider_state(data), "Meta, OpenAI, media storage"),
        ("Creative", _dict(data.get("creative_state")).get("state"), "Candidates and review"),
    ]
    items = "\n".join(
        f"""
        <article class="stat">
          <span class="dot {html.escape(_state_class(state))}"></span>
          <p>{html.escape(title)}</p>
          <strong>{html.escape(_safe_text(state) or "unknown")}</strong>
          <small>{html.escape(subtitle)}</small>
        </article>
        """
        for title, state, subtitle in cards
    )
    return f'<section class="stats">{items}</section>'


def _provider_state(data: dict[str, Any]) -> str:
    providers = _dict(data.get("provider_readiness")).get("providers") or []
    if any(isinstance(item, dict) and item.get("ok") for item in providers):
        return "partial"
    return "blocked"


def _render_business(data: dict[str, Any]) -> str:
    business = _dict(data.get("business_readiness"))
    checks = [item for item in business.get("checks") or [] if isinstance(item, dict)]
    rows = "\n".join(_render_check_row(item) for item in checks)
    return f"""
      <section class="panel" id="business">
        <div class="section-head">
          <div>
            <p class="eyebrow">Business</p>
            <h2>Repo readiness</h2>
          </div>
          <span class="pill {_state_class(business.get("state"))}">{html.escape(_safe_text(business.get("state")))}</span>
        </div>
        <div class="check-list">{rows}</div>
      </section>
    """


def _render_ad(data: dict[str, Any]) -> str:
    ad = _dict(data.get("ad_readiness"))
    providers = [
        item
        for item in _dict(data.get("provider_readiness")).get("providers") or []
        if isinstance(item, dict)
    ]
    provider_cards = "\n".join(_render_provider(item) for item in providers)
    hard = _chips(_string_list(ad.get("hard_stop_missing_fields")), "danger")
    soft = _chips(_string_list(ad.get("soft_warning_missing_fields")), "warn")
    return f"""
      <section class="panel" id="ads">
        <div class="section-head">
          <div>
            <p class="eyebrow">Ads</p>
            <h2>Readiness and providers</h2>
          </div>
          <span class="pill {_state_class(ad.get("state"))}">{html.escape(_safe_text(ad.get("state")))}</span>
        </div>
        <div class="two-col">
          <div>
            <h3>Hard stops</h3>
            {hard or '<p class="muted">No hard-stop inputs missing.</p>'}
            <h3>Soft warnings</h3>
            {soft or '<p class="muted">No soft warnings recorded.</p>'}
          </div>
          <div class="provider-grid">{provider_cards}</div>
        </div>
      </section>
    """


def _render_creative(data: dict[str, Any]) -> str:
    creative = _dict(data.get("creative_state"))
    source_bites = "\n".join(
        f"""
        <li>
          <strong>{html.escape(_safe_text(item.get("extracted_phrase")))}</strong>
          <span>{html.escape(_safe_text(item.get("source_type")))} - {html.escape(_safe_text(item.get("source_file")))}</span>
        </li>
        """
        for item in creative.get("source_bites") or []
        if isinstance(item, dict)
    )
    candidates = "\n".join(
        f"""
        <article class="candidate">
          <div>
            <span class="pill {_state_class(item.get("review_status") or item.get("state"))}">{html.escape(_safe_text(item.get("review_status") or item.get("state")))}</span>
            <h3>{html.escape(_safe_text(item.get("concept_id")))}</h3>
            <p>{html.escape(_safe_text(item.get("source_phrase")))}</p>
          </div>
          <small>{html.escape(_safe_text(item.get("creative_playbook_id")))}</small>
        </article>
        """
        for item in creative.get("candidates") or []
        if isinstance(item, dict)
    )
    winner = _dict(creative.get("winner"))
    return f"""
      <section class="panel" id="creative">
        <div class="section-head">
          <div>
            <p class="eyebrow">Creative</p>
            <h2>Image candidate state</h2>
          </div>
          <span class="pill {_state_class(creative.get("state"))}">{html.escape(_safe_text(creative.get("state")))}</span>
        </div>
        <div class="two-col">
          <div>
            <h3>Source bites</h3>
            <ul class="bite-list">{source_bites or "<li><span>No source bites recorded.</span></li>"}</ul>
          </div>
          <div class="winner">
            <h3>Winner / rejection</h3>
            <p>Best candidate: <strong>{html.escape(_safe_text(winner.get("best_candidate")) or "none")}</strong></p>
            <p>Best playbook: <strong>{html.escape(_safe_text(winner.get("best_playbook")) or "none")}</strong></p>
            <p>All rejected: <strong>{html.escape(str(winner.get("all_rejected")))}</strong></p>
          </div>
        </div>
        <div class="candidate-grid">{candidates or '<p class="muted">No candidates recorded.</p>'}</div>
      </section>
    """


def _render_actions(data: dict[str, Any]) -> str:
    actions = [item for item in data.get("next_actions") or [] if isinstance(item, dict)]
    rendered = "\n".join(
        f"""
        <li>
          <span class="dot {_state_class(item.get("severity"))}"></span>
          <div>
            <strong>{html.escape(_safe_text(item.get("title")))}</strong>
            <p>{html.escape(_safe_text(item.get("reason")))}</p>
            <code>{html.escape(_safe_text(item.get("command")))}</code>
          </div>
        </li>
        """
        for item in actions
    )
    return f"""
      <section class="panel" id="actions">
        <div class="section-head">
          <div>
            <p class="eyebrow">Next</p>
            <h2>Recommended actions</h2>
          </div>
        </div>
        <ul class="action-list">{rendered}</ul>
      </section>
    """


def _render_system_nav(data: dict[str, Any]) -> str:
    sections = [item for item in data.get("system_map") or [] if isinstance(item, dict)]
    rendered_sections = []
    for section in sections:
        items = "\n".join(
            f"<li><span>{html.escape(_safe_text(item.get('label')))}</span><b>{html.escape(str(item.get('count', 0)))}</b></li>"
            for item in section.get("items") or []
            if isinstance(item, dict)
        )
        rendered_sections.append(
            f"""
            <div class="nav-group">
              <h2>{html.escape(_safe_text(section.get("section")))}</h2>
              <ul>{items}</ul>
            </div>
            """
        )
    return "\n".join(rendered_sections)


def _render_check_row(item: dict[str, Any]) -> str:
    missing = _string_list(item.get("missing"))
    return f"""
      <article class="check-row">
        <span class="dot {_state_class(item.get("state"))}"></span>
        <div>
          <strong>{html.escape(_safe_text(item.get("title")))}</strong>
          <p>{html.escape(_safe_text(item.get("summary")))}</p>
          {_chips(missing, "warn") if missing else ""}
        </div>
      </article>
    """


def _render_provider(item: dict[str, Any]) -> str:
    return f"""
      <article class="provider">
        <span class="pill {_state_class(item.get("state"))}">{html.escape(_safe_text(item.get("state")))}</span>
        <h3>{html.escape(_safe_text(item.get("name")))}</h3>
        <p>{html.escape(_safe_text(item.get("summary")))}</p>
      </article>
    """


def _chips(items: list[str], class_name: str) -> str:
    return " ".join(
        f'<span class="chip {html.escape(class_name)}">{html.escape(_safe_text(item))}</span>'
        for item in items
    )


def _state_class(value: Any) -> str:
    state = _safe_text(value).lower()
    if state in {"ready", "ok", "accepted", "winner_selected", "present", "pass", "clean"}:
        return "good"
    if state in {
        "partial",
        "needs_attention",
        "needs_revision",
        "review",
        "warn",
        "warning",
        "info",
    }:
        return "warn"
    return "danger"


def _css() -> str:
    return """
:root {
  color-scheme: light;
  --bg: #f5f7fb;
  --panel: #ffffff;
  --text: #101828;
  --muted: #667085;
  --line: #e4e7ec;
  --blue: #3758f9;
  --green: #12b76a;
  --amber: #f79009;
  --red: #f04438;
  --shadow: 0 14px 40px rgba(16, 24, 40, 0.08);
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font: 14px/1.5 Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
.shell { display: grid; grid-template-columns: 280px 1fr; min-height: 100vh; }
.sidebar {
  position: sticky;
  top: 0;
  height: 100vh;
  overflow: auto;
  padding: 24px;
  background: #0f172a;
  color: white;
}
.brand { display: flex; gap: 12px; align-items: center; margin-bottom: 28px; }
.brand p { margin: 0; font-weight: 700; }
.brand small { color: #cbd5e1; }
.mark {
  width: 40px;
  height: 40px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  background: var(--blue);
  font-weight: 800;
}
.nav-group { margin: 0 0 22px; }
.nav-group h2 { margin: 0 0 8px; font-size: 12px; color: #94a3b8; text-transform: uppercase; letter-spacing: 0; }
.nav-group ul { list-style: none; padding: 0; margin: 0; display: grid; gap: 6px; }
.nav-group li { display: flex; justify-content: space-between; gap: 12px; color: #e2e8f0; }
.nav-group b { color: white; font-weight: 600; }
.main { padding: 28px; display: grid; gap: 20px; max-width: 1380px; width: 100%; }
.hero {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
  padding: 28px;
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  box-shadow: var(--shadow);
}
.hero h1 { margin: 4px 0 8px; font-size: 34px; line-height: 1.1; letter-spacing: 0; }
.lede { margin: 0; color: var(--muted); max-width: 720px; }
.hero-card {
  min-width: 240px;
  display: grid;
  gap: 8px;
  padding: 16px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #f8fafc;
}
.hero-card strong { overflow-wrap: anywhere; }
.eyebrow { margin: 0; color: var(--blue); font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0; }
.stats { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; }
.stat, .panel {
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 8px;
  box-shadow: var(--shadow);
}
.stat { padding: 18px; display: grid; gap: 6px; min-height: 132px; }
.stat p, .stat small, .panel p { margin: 0; }
.stat p { color: var(--muted); }
.stat strong { font-size: 22px; letter-spacing: 0; }
.stat small, .muted { color: var(--muted); }
.panel { padding: 22px; display: grid; gap: 18px; }
.section-head { display: flex; justify-content: space-between; align-items: start; gap: 16px; }
.section-head h2 { margin: 2px 0 0; font-size: 22px; letter-spacing: 0; }
.check-list { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.check-row {
  display: grid;
  grid-template-columns: 12px 1fr;
  gap: 12px;
  padding: 14px;
  border: 1px solid var(--line);
  border-radius: 8px;
}
.check-row p { color: var(--muted); }
.dot { width: 10px; height: 10px; border-radius: 999px; margin-top: 7px; background: var(--red); display: inline-block; flex: 0 0 auto; }
.good { background-color: var(--green); }
.warn { background-color: var(--amber); }
.danger { background-color: var(--red); }
.pill, .chip {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  width: max-content;
  max-width: 100%;
  padding: 4px 9px;
  border-radius: 999px;
  color: white;
  font-size: 12px;
  font-weight: 700;
  overflow-wrap: anywhere;
}
.chip { margin: 8px 6px 0 0; color: #344054; background: #f2f4f7; border: 1px solid var(--line); }
.chip.warn { color: #93370d; background: #fffaeb; border-color: #fedf89; }
.chip.danger { color: #b42318; background: #fef3f2; border-color: #fecdca; }
.two-col { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 16px; }
h3 { margin: 0 0 8px; font-size: 15px; letter-spacing: 0; }
.provider-grid { display: grid; gap: 12px; }
.provider, .winner, .candidate {
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 14px;
  background: #fcfcfd;
}
.provider h3, .candidate h3 { margin-top: 10px; }
.bite-list, .action-list { list-style: none; padding: 0; margin: 0; display: grid; gap: 10px; }
.bite-list li { border-bottom: 1px solid var(--line); padding-bottom: 10px; }
.bite-list span { display: block; color: var(--muted); }
.candidate-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.candidate { min-height: 150px; display: flex; flex-direction: column; justify-content: space-between; }
.candidate p, .candidate small { color: var(--muted); overflow-wrap: anywhere; }
.action-list li { display: grid; grid-template-columns: 14px 1fr; gap: 12px; padding: 12px; border: 1px solid var(--line); border-radius: 8px; }
code {
  display: inline-block;
  max-width: 100%;
  margin-top: 6px;
  padding: 4px 6px;
  border-radius: 6px;
  background: #f2f4f7;
  color: #344054;
  overflow-wrap: anywhere;
}
pre {
  max-height: 320px;
  overflow: auto;
  margin: 0;
  padding: 16px;
  background: #101828;
  color: #e4e7ec;
  border-radius: 8px;
  font-size: 12px;
}
@media (max-width: 980px) {
  .shell { grid-template-columns: 1fr; }
  .sidebar { position: static; height: auto; }
  .stats, .check-list, .two-col, .candidate-grid { grid-template-columns: 1fr; }
  .hero { align-items: stretch; flex-direction: column; }
}
"""
