"""Deterministic next-action ranking over ``mb status`` reports."""

from __future__ import annotations

from typing import Any

from mb.relationships import INFO_GAPS_WITHOUT_DAILY_ACTIONS

RANKER_SCHEMA_VERSION = "1.0"
MAX_ACTIONS = 3

WEIGHTS: dict[str, int] = {
    "update_required": 120,
    "not_mainbranch_repo": 115,
    "skill_wiring_broken": 110,
    "git_repo_missing": 105,
    "onboarding_incomplete": 95,
    "onboarding_incomplete_operational": 56,
    "overdue_bets": 90,
    "unhealthy_integrations": 85,
    "github_context_repair": 80,
    "validation_debt": 88,
    "dirty_git": 75,
    "attention_requests": 70,
    "assigned_tasks": 65,
    "blocked_or_stale_tasks": 60,
    "playbook_health_gaps": 84,
    "file_contract_gaps": 86,
    "relationship_health_gaps": 82,
    "bets_missing_exit_criteria": 80,
    "money_path_gaps": 72,
    "due_bets": 58,
    "stale_decisions": 50,
    "stale_research": 35,
    "since_last_check": 25,
    "low_signal": 1,
}

SEVERITY_PRIORITY: dict[str, str] = {
    "error": "urgent",
    "warn": "high",
    "info": "medium",
}


def rank_status_report(
    report: dict[str, Any],
    *,
    limit: int = MAX_ACTIONS,
) -> list[dict[str, Any]]:
    """Return ranked next actions from a status v1 report.

    This function is intentionally deterministic and local: it only inspects
    the report passed in, uses static weights, and never calls a model or
    external service.
    """

    actions: list[dict[str, Any]] = []
    _add_readiness_actions(actions, report)
    _add_drift_actions(actions, report)
    _add_file_contract_actions(actions, report)
    _add_playbook_actions(actions, report)
    _add_relationship_actions(actions, report)
    _add_money_path_actions(actions, report)
    _add_bet_actions(actions, report)
    _add_github_actions(actions, report)
    _add_since_last_check_action(actions, report)

    ranked = sorted(actions, key=_action_sort_key)
    if not ranked:
        ranked = [_low_signal_action(report)]
    ranked = _ensure_money_path_visible(ranked, report, limit)
    return ranked[:limit]


def _repo_operational(report: dict[str, Any]) -> bool:
    """True when the repo is already a working Main Branch business repo.

    Operational means the safe-blocker preconditions are met: the folder has the
    business-repo markers, git is initialized, skill wiring (if present) is
    healthy, and no update is required. In that state onboarding completion is a
    polish item, not a gate, and path-to-money guidance should be visible.
    """

    repo = _dict(report.get("repo"))
    git = _dict(report.get("git"))
    runtime = _dict(report.get("runtime"))
    skill_wiring = _dict(runtime.get("skill_wiring"))
    update = _dict(report.get("update"))
    return (
        bool(repo.get("looks_like_mainbranch_repo"))
        and bool(git.get("inside_work_tree"))
        and (not skill_wiring or bool(skill_wiring.get("ok")))
        and str(update.get("severity") or "") != "required"
    )


# Soft onboarding / repo-operation / hygiene actions that may yield a top slot to
# the leading MoneyPath bottleneck on an operational repo. Required safe blockers
# and business-pressure signals (bets, overdue/due bets, money finance) are not
# here, so they are never displaced.
_MONEY_PATH_DISPLACEABLE_IDS = frozenset(
    {
        "resume_onboarding",
        "review_playbook_health",
        "review_relationship_health",
        "review_local_git_changes",
        "review_since_last_check",
        "review_stale_decisions",
        "refresh_stale_research",
        "review_github_attention",
        "work_assigned_github_tasks",
        "unstick_blocked_or_stale_tasks",
    }
)


def _ensure_money_path_visible(
    ranked: list[dict[str, Any]],
    report: dict[str, Any],
    limit: int,
) -> list[dict[str, Any]]:
    """Reserve a top slot for the leading MoneyPath action on operational repos.

    When the repo is operational and the top MoneyPath bottleneck would otherwise
    fall below ``limit``, it takes the slot of the weakest soft onboarding /
    repo-operation / hygiene action in the top band so a path-to-money question
    surfaces it alongside, not underneath, those actions. Required safe blockers
    and business-pressure signals (bets, money finance) keep their slots.
    """

    if limit <= 0 or not _repo_operational(report):
        return ranked
    money = next(
        (
            action
            for action in ranked
            if str(action.get("id") or "").startswith("review_money_path")
        ),
        None,
    )
    if money is None or money in ranked[:limit]:
        return ranked
    top = ranked[:limit]
    displaceable = [
        action for action in top if str(action.get("id") or "") in _MONEY_PATH_DISPLACEABLE_IDS
    ]
    if not displaceable:
        # Top band is all blockers/business signals. Leave them; money path is not
        # buried under hygiene, it simply ranks below higher-pressure work.
        return ranked
    victim = min(displaceable, key=lambda action: _as_int(action.get("score")))
    new_top = [action for action in top if action is not victim] + [money]
    new_top_ids = {id(action) for action in new_top}
    rest = [action for action in ranked if id(action) not in new_top_ids]
    return sorted(new_top, key=_action_sort_key) + sorted(rest, key=_action_sort_key)


def _add_readiness_actions(actions: list[dict[str, Any]], report: dict[str, Any]) -> None:
    update = _dict(report.get("update"))
    update_severity = str(update.get("severity") or "")
    if update_severity in {"required", "recommended"}:
        severity = "error" if update_severity == "required" else "warn"
        score = WEIGHTS["update_required"] if update_severity == "required" else 78
        actions.append(
            _action(
                action_id=f"mainbranch_update_{update_severity}",
                title="Update Main Branch",
                command=str(update.get("command") or "mb update"),
                severity=severity,
                score=score,
                reason=str(update.get("reason") or "The installed Main Branch package is stale."),
                signals=[
                    _signal(
                        "update.severity",
                        severity=severity,
                        summary=f"update severity is {update_severity}",
                        evidence=[
                            str(update.get("installed") or ""),
                            str(update.get("latest") or ""),
                        ],
                        weight=score,
                    )
                ],
            )
        )

    repo = _dict(report.get("repo"))
    if not bool(repo.get("looks_like_mainbranch_repo")):
        missing = [str(item) for item in _list(repo.get("missing_markers"))]
        actions.append(
            _action(
                action_id="initialize_or_switch_business_repo",
                title="Open or initialize a Main Branch business repo",
                command="mb init",
                severity="error",
                score=WEIGHTS["not_mainbranch_repo"],
                reason="This folder does not have the required Main Branch repo markers.",
                signals=[
                    _signal(
                        "repo.looks_like_mainbranch_repo",
                        severity="error",
                        summary="business repo shape is missing",
                        evidence=missing[:5],
                        weight=WEIGHTS["not_mainbranch_repo"],
                    )
                ],
            )
        )

    git = _dict(report.get("git"))
    if not bool(git.get("inside_work_tree")):
        actions.append(
            _action(
                action_id="initialize_git_work_tree",
                title="Repair git setup",
                command="git init",
                severity="error",
                score=WEIGHTS["git_repo_missing"],
                reason=str(git.get("error") or "This folder is not a git work tree."),
                signals=[
                    _signal(
                        "git.inside_work_tree",
                        severity="error",
                        summary="git work tree is missing",
                        evidence=[str(git.get("error") or "")],
                        weight=WEIGHTS["git_repo_missing"],
                    )
                ],
            )
        )
    elif bool(git.get("dirty")):
        dirty_count = _as_int(git.get("dirty_count"))
        dirty_files = [str(item) for item in _list(git.get("dirty_files"))]
        actions.append(
            _action(
                action_id="review_local_git_changes",
                title="Review local git changes",
                command="git status --short",
                severity="warn",
                score=WEIGHTS["dirty_git"] + min(dirty_count, 10),
                reason=f"{dirty_count} local file(s) changed since the last clean handoff.",
                signals=[
                    _signal(
                        "git.dirty",
                        severity="warn",
                        summary=f"{dirty_count} dirty file(s)",
                        evidence=dirty_files[:5],
                        weight=WEIGHTS["dirty_git"],
                        safe_to_share=False,
                    )
                ],
            )
        )

    runtime = _dict(report.get("runtime"))
    skill_wiring = _dict(runtime.get("skill_wiring"))
    if skill_wiring and not bool(skill_wiring.get("ok")):
        actions.append(
            _action(
                action_id="repair_skill_wiring",
                title="Repair Claude Code skill wiring",
                command=str(
                    skill_wiring.get("repair")
                    or "mb skill repair --repo . && mb skill link --repo ."
                ),
                severity="error",
                score=WEIGHTS["skill_wiring_broken"],
                reason="Claude Code cannot reliably discover the bundled Main Branch skills.",
                signals=[
                    _signal(
                        "runtime.skill_wiring.ok",
                        severity="error",
                        summary="skill wiring is not healthy",
                        evidence=[str(item) for item in _list(skill_wiring.get("missing"))[:5]],
                        weight=WEIGHTS["skill_wiring_broken"],
                    )
                ],
            )
        )

    onboarding = _dict(report.get("onboarding"))
    onboarding_summary = _dict(onboarding.get("summary"))
    if onboarding_summary.get("status") == "in_progress":
        missing_inputs = [str(item) for item in _list(onboarding_summary.get("missing_inputs"))]
        # Onboarding is a soft warn. Once the repo is already operational, finishing
        # remaining onboarding inputs should not automatically bury path-to-money,
        # validation, bet, or active-push signals, so demote it below the
        # business-pressure band while keeping it leading on fresh/unshaped repos.
        onboarding_weight = (
            WEIGHTS["onboarding_incomplete_operational"]
            if _repo_operational(report)
            else WEIGHTS["onboarding_incomplete"]
        )
        actions.append(
            _action(
                action_id="resume_onboarding",
                title="Finish required onboarding inputs",
                command=str(
                    onboarding_summary.get("next_recommended_action") or "mb onboard status"
                ),
                severity="warn",
                score=onboarding_weight + min(len(missing_inputs), 10),
                reason=(
                    f"{_as_int(onboarding_summary.get('completed_required'))}/"
                    f"{_as_int(onboarding_summary.get('total_required'))} required onboarding "
                    "steps are complete."
                ),
                signals=[
                    _signal(
                        "onboarding.summary.status",
                        severity="warn",
                        summary="onboarding is still in progress",
                        evidence=missing_inputs[:5],
                        weight=WEIGHTS["onboarding_incomplete"],
                    )
                ],
            )
        )


def _add_drift_actions(actions: list[dict[str, Any]], report: dict[str, Any]) -> None:
    drift = _dict(report.get("drift"))
    for item in _list(drift.get("items")):
        drift_item = _dict(item)
        drift_id = str(drift_item.get("id") or "")
        if drift_id == "unhealthy_integrations":
            score = WEIGHTS["unhealthy_integrations"]
            actions.append(
                _action(
                    action_id="repair_unhealthy_integrations",
                    title="Repair unhealthy integrations",
                    command=str(drift_item.get("repair") or "mb connect doctor"),
                    severity="warn",
                    score=score,
                    reason=str(drift_item.get("summary") or "A declared integration needs repair."),
                    signals=[_drift_signal(drift_item, weight=score)],
                )
            )
        elif drift_id == "validation_debt":
            severity = str(drift_item.get("severity") or "warn")
            if severity != "error":
                continue
            score = WEIGHTS["validation_debt"]
            actions.append(
                _action(
                    action_id="repair_validation_debt",
                    title="Repair validation debt",
                    command="mb validate --cross-refs --json",
                    severity=severity,
                    score=score + len(_list(drift_item.get("evidence"))),
                    reason=str(
                        drift_item.get("summary")
                        or "Validation findings need to be grouped and repaired."
                    ),
                    signals=[_drift_signal(drift_item, weight=score)],
                )
            )
        elif drift_id == "stale_decisions":
            score = WEIGHTS["stale_decisions"]
            actions.append(
                _action(
                    action_id="review_stale_decisions",
                    title="Review stale decisions",
                    command="/mb-think",
                    severity="warn",
                    score=score + len(_list(drift_item.get("evidence"))),
                    reason=str(
                        drift_item.get("summary")
                        or "Proposed or running decisions have gone stale."
                    ),
                    signals=[_drift_signal(drift_item, weight=score, safe_to_share=False)],
                )
            )
        elif drift_id == "stale_research":
            score = WEIGHTS["stale_research"]
            actions.append(
                _action(
                    action_id="refresh_stale_research",
                    title="Refresh stale research",
                    command="/mb-think",
                    severity="info",
                    score=score + len(_list(drift_item.get("evidence"))),
                    reason=str(
                        drift_item.get("summary") or "Research is older than freshness rules."
                    ),
                    signals=[_drift_signal(drift_item, weight=score, safe_to_share=False)],
                )
            )

    github_context = _dict(_dict(report.get("github")).get("context"))
    if github_context and not bool(github_context.get("ok")):
        severity = "warn" if github_context.get("state") != "missing_cli" else "info"
        score = WEIGHTS["github_context_repair"]
        actions.append(
            _action(
                action_id="repair_github_context",
                title="Repair GitHub task context",
                command=str(github_context.get("repair_command") or "gh auth login"),
                severity=severity,
                score=score,
                reason=str(
                    github_context.get("summary")
                    or "GitHub task and proposal facts are unavailable."
                ),
                signals=[
                    _signal(
                        "github.context.ok",
                        severity=severity,
                        summary=str(github_context.get("state") or "not_ready"),
                        evidence=[str(github_context.get("summary") or "")],
                        weight=score,
                    )
                ],
            )
        )


def _add_bet_actions(actions: list[dict[str, Any]], report: dict[str, Any]) -> None:
    bets = _dict(_dict(report.get("brain")).get("bets"))

    missing_exit = [_dict(item) for item in _list(_dict(bets.get("exit_criteria")).get("missing"))]
    if missing_exit:
        score = WEIGHTS["bets_missing_exit_criteria"] + min(len(missing_exit) * 3, 12)
        safe_to_share = all(bool(item.get("public")) for item in missing_exit)
        actions.append(
            _action(
                action_id="tighten_bet_exit_criteria",
                title="Tighten active bet exit criteria",
                command="/mb-bet update",
                severity="warn",
                score=score,
                reason=(
                    f"{len(missing_exit)} active bet(s) have no kill or double-down criteria. "
                    "Tighten the bet before launching more work."
                ),
                operator_summary=(
                    f"{len(missing_exit)} active bet(s) are running without a predeclared exit "
                    "rubric. Add kill and double-down criteria so the bet can be cut or scaled on "
                    "evidence instead of gut feel."
                ),
                signals=[
                    _signal(
                        "brain.bets.exit_criteria.missing",
                        severity="warn",
                        summary="active bets are missing predeclared exit criteria",
                        evidence=[_bet_evidence(item) for item in missing_exit[:5]],
                        weight=WEIGHTS["bets_missing_exit_criteria"],
                        safe_to_share=safe_to_share,
                    )
                ],
            )
        )

    overdue = [_dict(item) for item in _list(bets.get("overdue"))]
    if overdue:
        score = WEIGHTS["overdue_bets"] + min(len(overdue) * 3, 15)
        actions.append(
            _action(
                action_id="update_overdue_bets",
                title="Close or update overdue bets",
                command="/mb-bet update",
                severity="warn",
                score=score,
                reason=f"{len(overdue)} active bet(s) are past their deadline.",
                signals=[
                    _signal(
                        "brain.bets.overdue",
                        severity="warn",
                        summary="active bet deadlines are overdue",
                        evidence=[_bet_evidence(item) for item in overdue[:5]],
                        weight=WEIGHTS["overdue_bets"],
                        safe_to_share=False,
                    )
                ],
            )
        )
        return

    due_soon = [_dict(item) for item in _list(bets.get("due_soon"))]
    if due_soon:
        score = WEIGHTS["due_bets"] + min(len(due_soon) * 3, 15)
        actions.append(
            _action(
                action_id="review_due_bets",
                title="Review bets due this week",
                command="/mb-bet update",
                severity="info",
                score=score,
                reason=f"{len(due_soon)} active bet(s) have deadlines in the next 7 days.",
                signals=[
                    _signal(
                        "brain.bets.due_soon",
                        severity="info",
                        summary="active bet deadlines are approaching",
                        evidence=[_bet_evidence(item) for item in due_soon[:5]],
                        weight=WEIGHTS["due_bets"],
                        safe_to_share=False,
                    )
                ],
            )
        )


def _add_relationship_actions(actions: list[dict[str, Any]], report: dict[str, Any]) -> None:
    relationship_health = _dict(report.get("relationship_health"))
    gaps = [_dict(item) for item in _list(relationship_health.get("gaps"))]
    gaps = [item for item in gaps if item.get("id") not in INFO_GAPS_WITHOUT_DAILY_ACTIONS]
    if not gaps:
        return
    warnings = [item for item in gaps if item.get("severity") == "warn"]
    first_gap = gaps[0]
    score = WEIGHTS["relationship_health_gaps"] + min(len(gaps) * 3, 18)
    actions.append(
        _action(
            action_id="review_relationship_health",
            title="Review business relationship gaps",
            command="mb status --verbose --peek",
            severity="warn" if warnings else "info",
            score=score,
            reason=str(
                first_gap.get("summary") or f"{len(gaps)} business relationship gap(s) need review."
            ),
            signals=[
                _signal(
                    "relationship_health.gaps",
                    severity="warn" if warnings else "info",
                    summary="business graph has actionable relationship gaps",
                    evidence=[str(item.get("id") or "") for item in gaps[:5]],
                    weight=WEIGHTS["relationship_health_gaps"],
                    safe_to_share=all(bool(item.get("safe_to_share", True)) for item in gaps),
                )
            ],
        )
    )


def _add_playbook_actions(actions: list[dict[str, Any]], report: dict[str, Any]) -> None:
    playbook_health = _dict(report.get("playbook_health"))
    gaps = [_dict(item) for item in _list(playbook_health.get("gaps"))]
    if not gaps:
        return
    warnings = [item for item in gaps if item.get("severity") == "warn"]
    first_gap = gaps[0]
    score = WEIGHTS["playbook_health_gaps"] + min(len(gaps) * 3, 18)
    actions.append(
        _action(
            action_id="review_playbook_health",
            title="Review push playbook health",
            command="mb status --verbose --peek",
            severity="warn" if warnings else "info",
            score=score,
            reason=str(
                first_gap.get("summary") or f"{len(gaps)} push playbook signal(s) need review."
            ),
            signals=[
                _signal(
                    "playbook_health.gaps",
                    severity="warn" if warnings else "info",
                    summary="push playbook run records have actionable health signals",
                    evidence=[str(item.get("id") or "") for item in gaps[:5]],
                    weight=WEIGHTS["playbook_health_gaps"],
                    safe_to_share=all(bool(item.get("safe_to_share", True)) for item in gaps),
                )
            ],
        )
    )


def _add_file_contract_actions(actions: list[dict[str, Any]], report: dict[str, Any]) -> None:
    if _has_validation_blocker(report):
        return
    validation = _dict(report.get("validation"))
    file_contracts = _dict(validation.get("file_contracts"))
    findings = [_dict(item) for item in _list(file_contracts.get("findings"))]
    if not findings:
        return
    first = findings[0]
    contract_id = str(first.get("contract_id") or "business_file")
    route = str(first.get("recommended_route") or "mb-think")
    severity = str(first.get("severity") or "warn")
    score = WEIGHTS["file_contract_gaps"] + min(len(findings) * 2, 16)
    actions.append(
        _action(
            action_id=f"review_file_contract_{contract_id}",
            title=f"Clarify {str(first.get('contract_label') or 'business file')} shape",
            command=route,
            severity="error" if severity == "error" else "warn",
            score=score,
            confidence="high",
            reason=str(
                first.get("owner_message")
                or first.get("message")
                or "A business file is missing context needed for the next workflow."
            ),
            signals=[
                _signal(
                    "validation.file_contracts.findings",
                    severity="error" if severity == "error" else "warn",
                    summary=str(first.get("route_reason") or "business file contract gap"),
                    evidence=[
                        str(item.get("path") or "")
                        + (f":{item.get('section')}" if item.get("section") else "")
                        for item in findings[:5]
                    ],
                    weight=WEIGHTS["file_contract_gaps"],
                    safe_to_share=all(bool(item.get("safe_to_share", True)) for item in findings),
                )
            ],
            audience="operator_decision",
            operator_summary=str(
                first.get("owner_message")
                or "A business file is missing context needed for the next workflow."
            ),
        )
    )


def _has_validation_blocker(report: dict[str, Any]) -> bool:
    drift = _dict(report.get("drift"))
    for item in _list(drift.get("items")):
        drift_item = _dict(item)
        if (
            str(drift_item.get("id") or "") == "validation_debt"
            and str(drift_item.get("severity") or "") == "error"
        ):
            return True
    return False


def _add_money_path_actions(actions: list[dict[str, Any]], report: dict[str, Any]) -> None:
    money_path = _dict(report.get("money_path"))
    money_actions = [_dict(item) for item in _list(money_path.get("ranked_actions"))]
    if not money_actions:
        return
    first = money_actions[0]
    score = WEIGHTS["money_path_gaps"]
    component = str(first.get("component") or "money_path")
    signal_id = str(first.get("source") or f"money_path.objects.{component}")
    missing = [str(item) for item in _list(first.get("missing"))]
    actions.append(
        _action(
            action_id=f"review_money_path_{component}",
            title=str(first.get("title") or "Review MoneyPath gap"),
            command=str(first.get("route") or "/mb-think"),
            severity="info",
            score=score,
            confidence=str(first.get("confidence") or "medium"),
            reason=str(first.get("reason") or "MoneyPath found a business-path gap."),
            signals=[
                _signal(
                    signal_id,
                    severity="info",
                    summary=str(first.get("reason") or "MoneyPath component needs review."),
                    evidence=missing,
                    weight=score,
                    safe_to_share=bool(first.get("safe_to_share", True)),
                )
            ],
            audience="operator_decision",
            operator_summary=str(first.get("reason") or "MoneyPath found a business-path gap."),
        )
    )


def _add_github_actions(actions: list[dict[str, Any]], report: dict[str, Any]) -> None:
    github = _dict(report.get("github"))
    if not bool(github.get("authenticated")):
        return
    sections = _dict(github.get("sections"))
    candidates = [
        (
            "review_github_attention",
            "Review GitHub attention requests",
            "gh pr list --search review-requested:@me",
            "attention_requests",
            "proposal or task needs review/response",
            WEIGHTS["attention_requests"],
        ),
        (
            "work_assigned_github_tasks",
            "Work assigned GitHub tasks",
            "gh issue list --assignee @me",
            "assigned_tasks",
            "task is assigned to you",
            WEIGHTS["assigned_tasks"],
        ),
        (
            "unstick_blocked_or_stale_tasks",
            "Unstick blocked or stale tasks",
            "gh issue list --search 'label:blocked label:stale'",
            "blocked_or_stale_tasks",
            "task is blocked or stale",
            WEIGHTS["blocked_or_stale_tasks"],
        ),
    ]
    for action_id, title, command, section, summary, weight in candidates:
        items = [_dict(item) for item in _list(sections.get(section))]
        if not items:
            continue
        actions.append(
            _action(
                action_id=action_id,
                title=title,
                command=command,
                severity="info",
                score=weight + min(len(items) * 2, 12),
                reason=f"{len(items)} GitHub {section.replace('_', ' ')} item(s) surfaced.",
                signals=[
                    _signal(
                        f"github.sections.{section}",
                        severity="info",
                        summary=summary,
                        evidence=[_github_evidence(item) for item in items[:5]],
                        weight=weight,
                        safe_to_share=False,
                    )
                ],
            )
        )


def _add_since_last_check_action(actions: list[dict[str, Any]], report: dict[str, Any]) -> None:
    since = _dict(report.get("since_last_check"))
    summary = _dict(since.get("summary"))
    changed = (
        _as_int(summary.get("commits"))
        + _as_int(summary.get("files_changed"))
        + _as_int(summary.get("brain_count_changes"))
    )
    if since.get("first_run") or changed <= 0:
        return
    actions.append(
        _action(
            action_id="review_since_last_check",
            title="Review what changed since the last check",
            command="mb status --verbose --peek",
            severity="info",
            score=WEIGHTS["since_last_check"] + min(changed, 20),
            reason=(
                f"{summary.get('commits', 0)} commit(s), "
                f"{summary.get('files_changed', 0)} file change(s), and "
                f"{summary.get('brain_count_changes', 0)} brain count change(s) since the "
                "last recorded check."
            ),
            signals=[
                _signal(
                    "since_last_check.summary",
                    severity="info",
                    summary="repo changed since the last status check",
                    evidence=[str(summary)],
                    weight=WEIGHTS["since_last_check"],
                    safe_to_share=False,
                )
            ],
        )
    )


def _low_signal_action(report: dict[str, Any]) -> dict[str, Any]:
    readiness = _dict(report.get("readiness"))
    level = str(readiness.get("level") or "unknown")
    return _action(
        action_id="not_enough_signal",
        title="Choose the next workflow manually",
        command="claude",
        severity="info",
        score=WEIGHTS["low_signal"],
        confidence="low",
        reason=(
            "Status did not find enough repair, deadline, GitHub, drift, or recent-change "
            f"signal to rank work confidently. Readiness is {level}."
        ),
        signals=[
            _signal(
                "ranker.low_signal_floor",
                severity="info",
                summary="not enough deterministic signal to rank work",
                evidence=[f"readiness={level}"],
                weight=WEIGHTS["low_signal"],
            )
        ],
    )


def _action(
    *,
    action_id: str,
    title: str,
    command: str,
    severity: str,
    score: int,
    reason: str,
    signals: list[dict[str, Any]],
    confidence: str | None = None,
    audience: str = "operator_decision",
    operator_summary: str = "",
) -> dict[str, Any]:
    action_confidence = confidence or _confidence(score, signals)
    safe_to_share = all(bool(signal.get("safe_to_share")) for signal in signals)
    return {
        "id": action_id,
        "title": title,
        "command": command,
        "priority": SEVERITY_PRIORITY.get(severity, "low"),
        "severity": severity,
        "score": score,
        "confidence": action_confidence,
        "reason": reason,
        "audience": audience,
        "operator_summary": operator_summary or reason or title,
        "signals": signals,
        "safe_to_share": safe_to_share,
    }


def _signal(
    signal_id: str,
    *,
    severity: str,
    summary: str,
    evidence: list[str],
    weight: int,
    safe_to_share: bool = True,
) -> dict[str, Any]:
    return {
        "id": signal_id,
        "severity": severity,
        "summary": summary,
        "evidence": [item for item in evidence if item][:5],
        "weight": weight,
        "safe_to_share": safe_to_share,
    }


def _drift_signal(
    item: dict[str, Any],
    *,
    weight: int,
    safe_to_share: bool = True,
) -> dict[str, Any]:
    severity = str(item.get("severity") or "info")
    return _signal(
        f"drift.{item.get('id') or 'item'}",
        severity=severity,
        summary=str(item.get("summary") or ""),
        evidence=[str(value) for value in _list(item.get("evidence"))],
        weight=weight,
        safe_to_share=safe_to_share and bool(item.get("safe_to_share", True)),
    )


def _confidence(score: int, signals: list[dict[str, Any]]) -> str:
    if score >= 80 and signals:
        return "high"
    if score >= 35 and signals:
        return "medium"
    return "low"


def _action_sort_key(action: dict[str, Any]) -> tuple[int, str]:
    return (-_as_int(action.get("score")), str(action.get("id") or ""))


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _bet_evidence(item: dict[str, Any]) -> str:
    title = str(item.get("title") or item.get("path") or "untitled bet")
    deadline = str(item.get("deadline") or "no deadline")
    return f"{title} ({deadline})"


def _github_evidence(item: dict[str, Any]) -> str:
    number = item.get("number")
    title = str(item.get("title") or "untitled")
    return f"#{number}: {title}" if number else title
