"""Deterministic next-action ranker."""

from __future__ import annotations

from mb import ranker


def _base_report() -> dict[str, object]:
    return {
        "repo": {"looks_like_mainbranch_repo": True, "missing_markers": []},
        "git": {"inside_work_tree": True, "dirty": False, "dirty_count": 0, "dirty_files": []},
        "update": {
            "severity": "current",
            "command": "",
            "reason": "",
            "installed": "0.2.6",
            "latest": "0.2.6",
        },
        "runtime": {
            "skill_wiring": {"ok": True, "repair": "", "missing": []},
            "claude_code": {"found": True, "repair": ""},
        },
        "onboarding": {"summary": {"status": "ready"}},
        "integrations": {"providers": []},
        "github": {
            "authenticated": True,
            "context": {"ok": True},
            "sections": {
                "attention_requests": [],
                "assigned_tasks": [],
                "blocked_or_stale_tasks": [],
            },
        },
        "brain": {
            "bets": {"overdue": [], "due_soon": []},
        },
        "drift": {"items": []},
        "since_last_check": {
            "first_run": False,
            "summary": {"commits": 0, "files_changed": 0, "brain_count_changes": 0},
        },
        "readiness": {"level": "ready"},
    }


def test_ranker_prioritizes_repair_before_business_work() -> None:
    report = _base_report()
    report["update"] = {
        "severity": "required",
        "command": "pipx upgrade mainbranch",
        "reason": "Installed version is below the supported floor.",
        "installed": "0.1.0",
        "latest": "0.2.6",
    }
    report["brain"] = {
        "bets": {
            "overdue": [
                {
                    "title": "Launch test",
                    "deadline": "2026-05-01",
                    "days_overdue": 3,
                }
            ],
            "due_soon": [],
        }
    }

    actions = ranker.rank_status_report(report)

    assert actions[0]["id"] == "mainbranch_update_required"
    assert actions[0]["priority"] == "urgent"
    assert actions[0]["command"] == "pipx upgrade mainbranch"
    assert actions[0]["signals"][0]["id"] == "update.severity"
    assert actions[1]["id"] == "update_overdue_bets"
    assert actions[1]["safe_to_share"] is False


def test_ranker_surfaces_low_confidence_floor_when_no_signals() -> None:
    actions = ranker.rank_status_report(_base_report())

    assert len(actions) == 1
    action = actions[0]
    assert action["id"] == "not_enough_signal"
    assert action["confidence"] == "low"
    assert action["safe_to_share"] is True
    assert action["signals"][0]["id"] == "ranker.low_signal_floor"
    assert action["signals"][0]["evidence"] == ["readiness=ready"]


def test_ranker_uses_github_status_sections() -> None:
    report = _base_report()
    report["github"] = {
        "authenticated": True,
        "context": {"ok": True},
        "sections": {
            "attention_requests": [{"number": 12, "title": "Review proposal"}],
            "assigned_tasks": [{"number": 13, "title": "Write docs"}],
            "blocked_or_stale_tasks": [],
        },
    }

    actions = ranker.rank_status_report(report)

    assert actions[0]["id"] == "review_github_attention"
    assert actions[0]["signals"][0]["evidence"] == ["#12: Review proposal"]
    assert actions[0]["safe_to_share"] is False


def test_ranker_surfaces_playbook_health() -> None:
    report = _base_report()
    report["playbook_health"] = {
        "gaps": [
            {
                "id": "pushes_without_playbook",
                "severity": "warn",
                "summary": "1 active/planned push(es) need a playbook run.",
                "safe_to_share": True,
            }
        ]
    }

    actions = ranker.rank_status_report(report)

    assert actions[0]["id"] == "review_playbook_health"
    assert actions[0]["signals"][0]["id"] == "playbook_health.gaps"
    assert actions[0]["signals"][0]["evidence"] == ["pushes_without_playbook"]


def test_ranker_suppresses_file_contract_route_until_validation_blockers_clear() -> None:
    report = _base_report()
    report["drift"] = {
        "items": [
            {
                "id": "validation_debt",
                "severity": "error",
                "summary": "Validation findings need repair.",
                "evidence": ["core/offer.md: missing required frontmatter"],
            }
        ]
    }
    report["validation"] = {
        "file_contracts": {
            "findings": [
                {
                    "contract_id": "offer",
                    "contract_label": "offer",
                    "severity": "warn",
                    "recommended_route": "mb-think",
                    "owner_message": "Your offer needs more buyer context.",
                    "route_reason": "Offer shape gaps route through mb-think.",
                    "path": "core/offer.md",
                    "section": "Proof",
                    "safe_to_share": True,
                }
                for _ in range(6)
            ]
        }
    }

    actions = ranker.rank_status_report(report)

    assert actions[0]["id"] == "repair_validation_debt"
    assert "review_file_contract_offer" not in {action["id"] for action in actions}


def test_ranker_surfaces_money_path_below_repair_blockers() -> None:
    report = _base_report()
    report["update"] = {
        "severity": "required",
        "command": "pipx upgrade mainbranch",
        "reason": "Installed version is below the supported floor.",
        "installed": "0.1.0",
        "latest": "0.2.6",
    }
    report["money_path"] = {
        "ranked_actions": [
            {
                "id": "define-cta-path",
                "title": "Define the CTA path",
                "reason": "Offer and audience facts need a next step.",
                "route": "/mb-think",
                "component": "cta_path",
                "confidence": "high",
                "missing": ["conversion_endpoint"],
                "safe_to_share": True,
            }
        ]
    }

    actions = ranker.rank_status_report(report)

    assert actions[0]["id"] == "mainbranch_update_required"
    money_path = next(action for action in actions if action["id"] == "review_money_path_cta_path")
    assert money_path["command"] == "/mb-think"
    assert money_path["signals"][0]["id"] == "money_path.objects.cta_path"
    assert money_path["score"] < actions[0]["score"]


def test_ranker_preserves_money_path_action_source() -> None:
    report = _base_report()
    report["money_path"] = {
        "ranked_actions": [
            {
                "id": "declare-appetite-thresholds",
                "title": "Declare MoneyPath appetite thresholds",
                "reason": "Thresholds are missing.",
                "route": "/mb-think",
                "component": "financial_exposure",
                "source": "money_path.policy.thresholds_declared",
                "confidence": "medium",
                "missing": ["core/finance/books.md money_path.appetite_thresholds"],
                "safe_to_share": True,
            }
        ]
    }

    actions = ranker.rank_status_report(report)

    money_path = next(
        action for action in actions if action["id"] == "review_money_path_financial_exposure"
    )
    assert money_path["signals"][0]["id"] == "money_path.policy.thresholds_declared"


def test_ranker_action_carries_audience_and_operator_summary() -> None:
    action = ranker._action(
        action_id="any.id",
        title="Do the thing",
        command="mb something",
        severity="warn",
        score=60,
        reason="Three pushes need attention.",
        signals=[],
    )
    assert action["audience"] == "operator_decision"
    assert action["operator_summary"] == "Three pushes need attention."

    overridden = ranker._action(
        action_id="any.id",
        title="Do the thing",
        command="mb something",
        severity="info",
        score=10,
        reason="Heads up.",
        signals=[],
        audience="informational",
        operator_summary="Just a status note.",
    )
    assert overridden["audience"] == "informational"
    assert overridden["operator_summary"] == "Just a status note."


def test_ranker_surfaces_active_bets_missing_exit_criteria() -> None:
    report = _base_report()
    report["brain"] = {
        "bets": {
            "overdue": [],
            "due_soon": [],
            "exit_criteria": {
                "missing": [
                    {
                        "path": "bets/2026-05-16-launch.md",
                        "title": "Launch the cohort",
                        "deadline": "2026-06-30",
                        "public": False,
                    },
                    {
                        "path": "bets/2026-05-18-ads.md",
                        "title": "Paid acquisition test",
                        "deadline": "",
                        "public": False,
                    },
                ]
            },
        }
    }

    actions = ranker.rank_status_report(report)
    action = next(action for action in actions if action["id"] == "tighten_bet_exit_criteria")

    assert action["command"] == "/mb-bet update"
    assert action["priority"] == "high"
    assert action["audience"] == "operator_decision"
    assert action["operator_summary"]
    assert action["signals"][0]["id"] == "brain.bets.exit_criteria.missing"
    assert action["signals"][0]["evidence"] == [
        "Launch the cohort (2026-06-30)",
        "Paid acquisition test (no deadline)",
    ]
    # Private bet names must not be marked shareable.
    assert action["safe_to_share"] is False


def test_ranker_bet_exit_criteria_shareable_only_when_all_public() -> None:
    report = _base_report()
    report["brain"] = {
        "bets": {
            "overdue": [],
            "due_soon": [],
            "exit_criteria": {
                "missing": [
                    {
                        "path": "bets/2026-05-16-launch.md",
                        "title": "Launch the cohort",
                        "deadline": "2026-06-30",
                        "public": True,
                    }
                ]
            },
        }
    }

    actions = ranker.rank_status_report(report)
    action = next(action for action in actions if action["id"] == "tighten_bet_exit_criteria")

    assert action["safe_to_share"] is True


def test_ranker_bet_exit_criteria_stays_below_repair_blockers() -> None:
    report = _base_report()
    report["update"] = {
        "severity": "required",
        "command": "pipx upgrade mainbranch",
        "reason": "Installed version is below the supported floor.",
        "installed": "0.1.0",
        "latest": "0.2.6",
    }
    report["brain"] = {
        "bets": {
            "overdue": [],
            "due_soon": [],
            "exit_criteria": {
                "missing": [
                    {
                        "path": "bets/2026-05-16-launch.md",
                        "title": "Launch the cohort",
                        "deadline": "2026-06-30",
                        "public": False,
                    }
                ]
            },
        }
    }

    actions = ranker.rank_status_report(report)

    assert actions[0]["id"] == "mainbranch_update_required"
    tighten = next(action for action in actions if action["id"] == "tighten_bet_exit_criteria")
    assert tighten["score"] < actions[0]["score"]


def _onboarding_in_progress() -> dict[str, object]:
    return {
        "summary": {
            "status": "in_progress",
            "missing_inputs": ["offer"],
            "completed_required": 1,
            "total_required": 3,
            "next_recommended_action": "mb onboard status",
        }
    }


def _money_path_cta_action() -> dict[str, object]:
    return {
        "ranked_actions": [
            {
                "id": "define-cta-path",
                "title": "Define the CTA path",
                "reason": "Offer and audience facts need a next step.",
                "route": "/mb-think",
                "component": "cta_path",
                "confidence": "high",
                "missing": ["conversion_endpoint"],
                "safe_to_share": True,
            }
        ]
    }


def test_ranker_demotes_onboarding_below_money_path_when_operational() -> None:
    report = _base_report()
    report["onboarding"] = _onboarding_in_progress()
    report["money_path"] = _money_path_cta_action()

    actions = ranker.rank_status_report(report)
    ids = [action["id"] for action in actions]

    assert "review_money_path_cta_path" in ids
    assert "resume_onboarding" in ids
    money_path = next(a for a in actions if a["id"] == "review_money_path_cta_path")
    onboarding = next(a for a in actions if a["id"] == "resume_onboarding")
    # On an operational repo, finishing onboarding inputs must not outrank the
    # path-to-money bottleneck.
    assert money_path["score"] > onboarding["score"]
    assert ids.index("review_money_path_cta_path") < ids.index("resume_onboarding")


def test_ranker_keeps_onboarding_leading_when_repo_not_operational() -> None:
    report = _base_report()
    report["repo"] = {"looks_like_mainbranch_repo": False, "missing_markers": ["core/"]}
    report["onboarding"] = _onboarding_in_progress()

    actions = ranker.rank_status_report(report)
    onboarding = next(a for a in actions if a["id"] == "resume_onboarding")

    # Not operational: onboarding keeps its full weight band (>= 95) so a fresh or
    # unshaped repo still leads with finishing setup.
    assert onboarding["score"] >= ranker.WEIGHTS["onboarding_incomplete"]


def test_ranker_surfaces_money_path_over_hygiene_but_keeps_blocker() -> None:
    report = _base_report()
    report["drift"] = {
        "items": [
            {
                "id": "validation_debt",
                "severity": "error",
                "summary": "Validation findings need repair.",
                "evidence": ["core/offer.md: missing required frontmatter"],
            }
        ]
    }
    report["playbook_health"] = {
        "gaps": [
            {
                "id": "pushes_without_playbook",
                "severity": "warn",
                "summary": "1 active push needs a playbook run.",
                "safe_to_share": True,
            }
        ]
    }
    report["relationship_health"] = {
        "gaps": [
            {
                "id": "bet_without_push",
                "severity": "warn",
                "summary": "An active bet has no linked push.",
                "safe_to_share": True,
            }
        ]
    }
    report["money_path"] = _money_path_cta_action()

    actions = ranker.rank_status_report(report)
    ids = {action["id"] for action in actions}

    # The validation error blocker is preserved; the path-to-money bottleneck
    # surfaces by displacing the weakest hygiene action, not the blocker.
    assert "repair_validation_debt" in ids
    assert "review_money_path_cta_path" in ids
    assert "review_relationship_health" not in ids


def test_info_only_relationship_gaps_do_not_become_daily_action() -> None:
    report = _base_report()
    report["relationship_health"] = {
        "gaps": [
            {
                "id": "research_without_links",
                "severity": "info",
                "summary": "Older research has no business links.",
            }
        ]
    }
    assert "review_relationship_health" not in {
        action["id"] for action in ranker.rank_status_report(report)
    }


def test_ranker_never_displaces_business_pressure_for_money_path() -> None:
    report = _base_report()
    report["drift"] = {
        "items": [
            {
                "id": "validation_debt",
                "severity": "error",
                "summary": "Validation findings need repair.",
                "evidence": ["core/offer.md: missing required frontmatter"],
            }
        ]
    }
    report["brain"] = {
        "bets": {
            "overdue": [{"title": "Stale bet", "deadline": "2026-05-01", "days_overdue": 5}],
            "due_soon": [],
            "exit_criteria": {
                "missing": [
                    {
                        "path": "bets/2026-05-16-launch.md",
                        "title": "Launch the cohort",
                        "deadline": "2026-06-30",
                        "public": False,
                    }
                ]
            },
        }
    }
    report["money_path"] = _money_path_cta_action()

    actions = ranker.rank_status_report(report)
    ids = {action["id"] for action in actions}

    # Operational repo, but the top band is a validation blocker plus two bet
    # signals with no hygiene action to yield. Money path must not displace any of
    # them; blockers and business pressure keep their slots.
    assert "repair_validation_debt" in ids
    assert "tighten_bet_exit_criteria" in ids
    assert "update_overdue_bets" in ids
    assert "review_money_path_cta_path" not in ids


def test_ranker_surfaces_missing_exit_criteria_even_with_overdue_bets() -> None:
    report = _base_report()
    report["brain"] = {
        "bets": {
            "overdue": [{"title": "Stale bet", "deadline": "2026-05-01", "days_overdue": 5}],
            "due_soon": [],
            "exit_criteria": {
                "missing": [
                    {
                        "path": "bets/2026-05-16-launch.md",
                        "title": "Launch the cohort",
                        "deadline": "2026-06-30",
                        "public": False,
                    }
                ]
            },
        }
    }

    actions = ranker.rank_status_report(report)
    ids = {action["id"] for action in actions}

    # The overdue early-return must not suppress the missing-criteria action.
    assert "tighten_bet_exit_criteria" in ids
    assert "update_overdue_bets" in ids
