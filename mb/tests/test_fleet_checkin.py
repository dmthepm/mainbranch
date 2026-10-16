"""``mb fleet checkin``: one read-only card per business (#1177).

Hub lists, checkouts and the fleet cache are synthetic temp files. ``gh`` and
every other fleet network surface are replaced with stubs that fail the test.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import textwrap
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from mb import fleet, fleet_checkin
from mb import status as status_mod
from mb.cli import app
from mb.init import run as init_run

runner = CliRunner()
needs_tomllib = pytest.mark.skipif(sys.version_info < (3, 11), reason="tomllib is 3.11+")
MB_PACKAGE_ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_AMOUNT_KEYS = ("gross_exposure", "this_week_at_risk", "decimal_mantissa", "threshold")


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "home"
    root.mkdir()
    monkeypatch.setenv("HOME", str(root))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(root / "config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(root / "state"))
    monkeypatch.setenv("SHELL", "/bin/sh")

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("fleet checkin must not reach gh or the network")

    monkeypatch.setattr(fleet, "_run_gh", forbidden)
    monkeypatch.setattr(fleet, "_http_get", forbidden)
    monkeypatch.setattr(fleet, "GitHub", forbidden)
    monkeypatch.setattr(fleet, "Cloudflare", forbidden)
    monkeypatch.setattr(fleet, "refresh", forbidden)
    return root


def _hub_list(home: Path, body: str) -> Path:
    path = home / "config" / "mainbranch" / "fleet.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


def _fixture_hubs(home: Path) -> dict[str, Path]:
    healthy = home / "src" / "healthy"
    missing = home / "src" / "gone"
    _hub_list(
        home,
        f"""\
        [[hubs]]
        name = "healthy"
        remote = "github:example-co/healthy"
        checkout = "{healthy}"

        [[hubs]]
        name = "gone"
        remote = "github:example-co/gone"
        checkout = "{missing}"

        [[hubs]]
        name = "elsewhere"
        remote = "github:example-co/elsewhere"
        """,
    )
    return {"healthy": healthy, "gone": missing}


def _status_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "generated_at": "2026-10-12T09:00:00Z",
        "repo": {"looks_like_mainbranch_repo": True},
        "readiness": {"level": "ready"},
        "ranked_actions": [{"title": "Pick the next bet", "severity": "info"}],
        "git": {
            "branch": "main",
            "default_branch": "main",
            "commit": "abc1234",
            "dirty_count": 0,
            "ahead": 0,
            "behind": 0,
        },
        "journal": {
            "events": [
                {
                    "date": "2026-10-10",
                    "summary": "Saved the offer rewrite",
                    "recognized_as": "business_verb",
                }
            ]
        },
        "brain": {
            "bets": {
                "active": [
                    {
                        "title": "Webinar test",
                        "status": "active",
                        "deadline": "2026-11-01",
                        "stage": "working",
                        "commitment": {
                            "action": "Send one outreach message",
                            "cadence": "weekdays",
                            "owner": "",
                            "evidence": "send_id",
                        },
                    }
                ],
                "due_soon": [],
                "overdue": [],
                "exit_criteria": {"triggered_failure_signals": []},
            }
        },
        "money_path": {
            "active_bets": {
                "count": 1,
                "checked": True,
                "ledger_unavailable": False,
                "anchored": 1,
                "unanchored": 0,
                "over_cap": [],
                "gross_exposure": {"decimal_mantissa": 12345},
                "this_week_at_risk": {"decimal_mantissa": 999},
            }
        },
        "github": {
            "available": True,
            "degraded": False,
            "summary": {
                "open_proposals": 1,
                "attention_requests": 0,
                "assigned_tasks": 0,
                "blocked_or_stale_tasks": 0,
            },
        },
        "integrations": {"summary": {"configured": 2, "healthy": 2, "needs_repair": 0}},
    }
    payload.update(overrides)
    return payload


def _write_cache(home: Path, *, refreshed: str | None = None) -> Path:
    cache = home / "state" / "mainbranch" / "fleet.db"
    snapshot = {
        "schema": fleet.FLEET_SCHEMA,
        "refreshed_at": refreshed or datetime.now(timezone.utc).isoformat(),
        "hubs": [],
        "repos": [
            {
                "hub": "healthy",
                "repo": "example-co/healthy",
                "main_sha": "abc1234" + "0" * 33,
                "dependabot_alerts": {"state": "ok", "open": 2},
            },
        ],
        "sites": [
            {"hub": "healthy", "repo": "example-co/healthy", "flags": ["ci_failing"]},
            {"hub": "elsewhere", "repo": "example-co/elsewhere", "flags": []},
        ],
        "refresh_errors": [],
    }
    fleet._store(cache, snapshot)
    return cache


def _runner_for(outcomes: dict[str, tuple[dict[str, Any] | None, str]]):
    def run(checkout: Path, timeout: int) -> tuple[dict[str, Any] | None, str]:
        return outcomes[checkout.name]

    return run


def _tree(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


@needs_tomllib
def test_cards_json_shape_and_exit_one_when_a_checkout_is_missing(home: Path) -> None:
    hubs = _fixture_hubs(home)
    hubs["healthy"].mkdir(parents=True)
    _write_cache(home)
    doc, code = fleet_checkin.checkin(
        status_runner=_runner_for({"healthy": (_status_payload(), "")})
    )

    assert code == 1
    assert doc["ok"] is False
    assert doc["schema"] == "mb.fleet.checkin"
    assert doc["schema_version"] == 1
    assert doc["safe_to_share"] is False
    assert doc["hub_list"] == {"state": "ok", "hubs": 3, "shown": 3}
    assert doc["fleet_snapshot"]["state"] == "ok"
    cards = {card["hub"]: card for card in doc["cards"]}
    assert cards["healthy"]["checkout_state"] == "ok"
    assert cards["gone"]["checkout_state"] == "missing"
    assert cards["gone"]["state"] == "unavailable"
    assert cards["elsewhere"]["checkout_state"] == "not_on_this_machine"
    assert cards["elsewhere"]["state"] == "remote_only"
    healthy = cards["healthy"]
    assert healthy["sections"]["loop"]["top_gap"] is None
    assert set(healthy["sections"]) == set(fleet_checkin.SECTION_NAMES)
    for section in healthy["sections"].values():
        assert {"state", "as_of", "source", "text"} <= set(section)
    bet = healthy["sections"]["bets"]["items"][0]
    assert bet["stage"] == "working"
    assert bet["commitment"] == {
        "action": "Send one outreach message",
        "cadence": "weekdays",
        "owner": "",
        "evidence": "send_id",
    }
    assert healthy["freshness"]["local_matches_remote"] is True
    overview = doc["overview"]
    assert overview["needs_you"] + overview["on_track"] + overview["cannot_see"] == len(
        doc["cards"]
    )
    assert healthy["sections"]["sites"]["flags"] == {"ci_failing": 1}
    assert healthy["verdict"] == "on_track"  # loop is ready; a failing site is a note
    assert cards["gone"]["sections"]["loop"]["state"] == "unavailable"
    assert cards["gone"]["sections"]["loop"]["top_gap"] is None
    assert cards["elsewhere"]["sections"]["loop"]["state"] == "not_applicable"
    assert cards["gone"]["verdict"] == "cannot_see"
    assert cards["elsewhere"]["verdict"] == "on_track"


@needs_tomllib
def test_real_status_gap_reaches_card_text_and_json(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = home / "src" / "healthy"
    init_run(path=str(repo), name="Test Business")
    (repo / "bets" / "2026-10-13-test.md").write_text(
        "---\nstatus: open\nopened: 2026-10-13\n"
        "hypothesis: Outreach will lead to calls.\nmetric: calls\n"
        "target: 5 calls\nlinked_pushes: []\n---\n# Test bet\n",
        encoding="utf-8",
    )
    _hub_list(
        home,
        f'[[hubs]]\nname = "healthy"\nremote = "github:example-co/healthy"\ncheckout = "{repo}"\n',
    )
    monkeypatch.setattr(
        status_mod,
        "_which",
        lambda name: "" if name in {"gh", "claude"} else shutil.which(name) or "",
    )
    report = status_mod.run(path=str(repo), update_marker=False)
    gap = next(
        item
        for item in report["relationship_health"]["gaps"]
        if item["id"] == "active_bets_without_push"
    )
    report["ranked_actions"] = [{"title": "Review today's work", "severity": "info"}]
    monkeypatch.setattr(fleet_checkin, "run_status_child", lambda checkout, timeout: (report, ""))

    result = runner.invoke(app, ["fleet", "checkin", "--json"])
    assert result.exit_code == 0
    card = json.loads(result.stdout)["cards"][0]
    assert card["sections"]["loop"]["top_gap"] == {
        key: gap[key] for key in ("id", "severity", "count", "summary")
    }
    assert card["sections"]["loop"]["top_action"]["title"] == "Review today's work"
    assert "Links: 1 active bet needs a linked push." in card["text"]

    human = runner.invoke(app, ["fleet", "checkin"])
    assert human.exit_code == 0
    assert "Links: 1 active bet needs a linked push." in human.stdout


@needs_tomllib
def test_gap_already_named_by_top_action_is_not_repeated(home: Path) -> None:
    hubs = _fixture_hubs(home)
    hubs["healthy"].mkdir(parents=True)
    summary = "1 active bet(s) need a linked push."
    payload = _status_payload(
        readiness={"level": "needs_attention"},
        ranked_actions=[{"title": summary.rstrip("."), "reason": summary}],
        relationship_health={
            "gaps": [
                {
                    "id": "active_bets_without_push",
                    "severity": "warn",
                    "count": 1,
                    "summary": summary,
                }
            ]
        },
    )
    doc, _ = fleet_checkin.checkin(status_runner=_runner_for({"healthy": (payload, "")}))
    loop = doc["cards"][0]["sections"]["loop"]
    assert loop["top_gap"]["id"] == "active_bets_without_push"
    assert "Next: 1 active bet(s) need a linked push." in loop["text"]
    assert "Links:" not in loop["text"]


def test_generic_relationship_action_still_names_the_specific_gap() -> None:
    summary = "1 active bet(s) need a linked push."
    payload = _status_payload(
        ranked_actions=[{"title": "Review business relationship gaps", "reason": summary}],
        relationship_health={
            "gaps": [
                {
                    "id": "active_bets_without_push",
                    "severity": "warn",
                    "count": 1,
                    "summary": summary,
                }
            ]
        },
    )
    loop = fleet_checkin._loop_section(payload, "2026-10-13")
    assert "Links: 1 active bet needs a linked push." in loop["text"]


@needs_tomllib
def test_no_relationship_gap_has_no_line_and_null_key(home: Path) -> None:
    hubs = _fixture_hubs(home)
    hubs["healthy"].mkdir(parents=True)
    payload = _status_payload(relationship_health={"gaps": []})
    doc, _ = fleet_checkin.checkin(status_runner=_runner_for({"healthy": (payload, "")}))
    loop = doc["cards"][0]["sections"]["loop"]
    assert loop["top_gap"] is None
    assert "Links:" not in loop["text"]


def test_info_only_relationship_gap_does_not_change_fleet_loop() -> None:
    payload = _status_payload(
        readiness={"level": "ready"},
        relationship_health={
            "gaps": [
                {
                    "id": "research_without_links",
                    "severity": "info",
                    "count": 1,
                    "summary": "Older research has no business links.",
                }
            ]
        },
    )
    loop = fleet_checkin._loop_section(payload, "2026-10-15")
    assert loop["state"] == "ok"
    assert loop["top_gap"] is None
    assert "Links:" not in loop["text"]


def test_existing_offer_gap_keeps_fleet_headline() -> None:
    payload = _status_payload(
        readiness={"level": "ready"},
        relationship_health={
            "gaps": [
                {
                    "id": "offers_without_current_push_or_playbook",
                    "severity": "info",
                    "count": 1,
                    "summary": "1 offer(s) have no current push or playbook.",
                }
            ]
        },
    )
    loop = fleet_checkin._loop_section(payload, "2026-10-15")
    assert loop["top_gap"] == {
        "id": "offers_without_current_push_or_playbook",
        "severity": "info",
        "count": 1,
        "summary": "1 offer(s) have no current push or playbook.",
    }
    assert loop["text"] == "Ready to work. Links: 1 offer has no current push or playbook."


def test_both_new_relationship_gaps_have_no_fleet_headline() -> None:
    payload = _status_payload(
        relationship_health={
            "gaps": [
                {
                    "id": "accepted_decisions_without_links",
                    "severity": "info",
                    "summary": "Decision.",
                },
                {"id": "research_without_links", "severity": "info", "summary": "Research."},
            ]
        }
    )
    loop = fleet_checkin._loop_section(payload, "2026-10-15")
    assert loop["top_gap"] is None
    assert "Links:" not in loop["text"]


def test_top_gap_prefers_warning_and_preserves_status_order_for_ties() -> None:
    payload = _status_payload(
        relationship_health={
            "gaps": [
                {"id": "offer", "severity": "info", "count": 1, "summary": "One offer gap."},
                {
                    "id": "first_warning",
                    "severity": "warn",
                    "count": 2,
                    "summary": "Two missing links.",
                },
                {
                    "id": "second_warning",
                    "severity": "warn",
                    "count": 1,
                    "summary": "One missing link.",
                },
            ]
        }
    )
    loop = fleet_checkin._loop_section(payload, "2026-10-13")
    assert loop["top_gap"]["id"] == "first_warning"
    assert "Links: Two missing links." in loop["text"]


@needs_tomllib
def test_exposure_is_counts_and_cap_state_only(home: Path) -> None:
    hubs = _fixture_hubs(home)
    hubs["healthy"].mkdir(parents=True)
    over = {"path": "bets/a.md", "gross_exposure": {"decimal_mantissa": 5}, "threshold": 100}
    payload = _status_payload()
    payload["money_path"]["active_bets"]["over_cap"] = [over]
    doc, _ = fleet_checkin.checkin(status_runner=_runner_for({"healthy": (payload, "")}))
    exposure = doc["cards"][0]["sections"]["exposure"]
    assert exposure["over_cap"] == 1
    assert exposure["state"] == "attention"
    dump = json.dumps(doc)
    for key in FORBIDDEN_AMOUNT_KEYS:
        assert key not in dump


@needs_tomllib
def test_all_cards_exit_zero_without_the_missing_hub(home: Path) -> None:
    healthy = home / "src" / "healthy"
    healthy.mkdir(parents=True)
    _hub_list(
        home,
        f"""\
        [[hubs]]
        name = "healthy"
        remote = "github:example-co/healthy"
        checkout = "{healthy}"

        [[hubs]]
        name = "elsewhere"
        remote = "github:example-co/elsewhere"
        """,
    )
    doc, code = fleet_checkin.checkin(
        status_runner=_runner_for({"healthy": (_status_payload(), "")})
    )
    assert code == 0
    assert doc["ok"] is True
    assert doc["fleet_snapshot"]["state"] == "missing"
    assert doc["cards"][0]["sections"]["sites"]["state"] == "not_checked"


@needs_tomllib
def test_a_broken_hub_is_unavailable_and_does_not_block_the_others(home: Path) -> None:
    first = home / "src" / "first"
    second = home / "src" / "second"
    first.mkdir(parents=True)
    second.mkdir(parents=True)
    _hub_list(
        home,
        f"""\
        [[hubs]]
        name = "first"
        remote = "github:example-co/first"
        checkout = "{first}"

        [[hubs]]
        name = "second"
        remote = "github:example-co/second"
        checkout = "{second}"
        """,
    )
    runner_ = _runner_for(
        {
            "first": (None, "mb status did not finish within 5 seconds"),
            "second": (_status_payload(), ""),
        }
    )
    doc, code = fleet_checkin.checkin(status_runner=runner_, timeout=5)
    assert code == 1
    first_card, second_card = doc["cards"]
    assert first_card["state"] == "unavailable"
    assert "did not finish" in first_card["reason"]
    assert second_card["state"] == "ok"
    assert doc["errors"] and "first" in doc["errors"][0]


@needs_tomllib
def test_not_a_business_repo_is_unavailable(home: Path) -> None:
    hubs = _fixture_hubs(home)
    hubs["healthy"].mkdir(parents=True)
    plain = _status_payload(repo={"looks_like_mainbranch_repo": False})
    doc, code = fleet_checkin.checkin(status_runner=_runner_for({"healthy": (plain, "")}))
    assert code == 1
    assert doc["cards"][0]["checkout_state"] == "not_a_business_repo"
    assert doc["cards"][0]["state"] == "unavailable"


@needs_tomllib
def test_local_checkout_behind_remote_is_called_out_without_fetching(home: Path) -> None:
    hubs = _fixture_hubs(home)
    hubs["healthy"].mkdir(parents=True)
    _write_cache(home)
    behind = _status_payload()
    behind["git"]["commit"] = "fffffff"
    doc, _ = fleet_checkin.checkin(status_runner=_runner_for({"healthy": (behind, "")}))
    card = doc["cards"][0]
    assert card["freshness"]["local_matches_remote"] is False
    assert "May miss work saved elsewhere" in card["sections"]["loop"]["text"]


@needs_tomllib
def test_stale_snapshot_warns(home: Path) -> None:
    hubs = _fixture_hubs(home)
    hubs["healthy"].mkdir(parents=True)
    _write_cache(home, refreshed="2026-10-01T08:00:00Z")
    doc, _ = fleet_checkin.checkin(status_runner=_runner_for({"healthy": (_status_payload(), "")}))
    assert doc["fleet_snapshot"]["state"] == "stale"
    assert any("over a day old" in w for w in doc["warnings"])


@needs_tomllib
@pytest.mark.parametrize(
    "hub_list",
    [None, "this is = not [valid", 'name = "no hubs"\n'],
    ids=["missing", "invalid-toml", "no-hubs"],
)
@pytest.mark.parametrize("json_out", [False, True], ids=["text", "json"])
def test_invalid_hub_list_exits_two_without_home_path(
    home: Path, hub_list: str | None, json_out: bool
) -> None:
    if hub_list is not None:
        _hub_list(home, hub_list)
    result = runner.invoke(app, ["fleet", "checkin", *(["--json"] if json_out else [])])
    assert result.exit_code == 2
    assert str(home) not in result.output
    assert "~/config/mainbranch/fleet.toml" in result.output
    if json_out:
        payload = json.loads(result.stdout)
        assert payload["ok"] is False
        assert "cards" not in payload
    else:
        assert "card" not in result.output


@needs_tomllib
def test_bad_usage_exits_two_with_no_cards(home: Path) -> None:
    _fixture_hubs(home)
    unknown = runner.invoke(app, ["fleet", "checkin", "--json", "--hub", "nope"])
    assert unknown.exit_code == 2
    assert "cards" not in json.loads(unknown.stdout)
    assert runner.invoke(app, ["fleet", "checkin", "--timeout", "0"]).exit_code == 2


@needs_tomllib
def test_plain_text_is_an_overview_then_one_card_per_business(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hubs = _fixture_hubs(home)
    hubs["healthy"].mkdir(parents=True)
    _write_cache(home)
    monkeypatch.setattr(
        fleet_checkin, "run_status_child", lambda checkout, timeout: (_status_payload(), "")
    )
    result = runner.invoke(app, ["fleet", "checkin"])
    assert result.exit_code == 1
    lines = result.stdout.splitlines()
    assert lines[0].startswith("3 businesses:")
    for name in ("healthy", "gone", "elsewhere"):
        assert any(line.startswith(f"{name}:") for line in lines)
    assert str(home) not in result.stdout


@needs_tomllib
def test_output_has_no_absolute_home_paths(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    hubs = _fixture_hubs(home)
    hubs["healthy"].mkdir(parents=True)
    payload = _status_payload()
    payload["ranked_actions"] = [{"title": f"Open {hubs['healthy']}/core", "severity": "info"}]
    monkeypatch.setattr(fleet_checkin, "run_status_child", lambda checkout, timeout: (payload, ""))
    result = runner.invoke(app, ["fleet", "checkin", "--json"])
    assert str(home) not in result.stdout
    document = json.loads(result.stdout)
    assert document["cards"][0]["checkout"] == "~/src/healthy"
    assert document["safe_to_share"] is False
    assert document["result_schema"]["name"] == "mainbranch.fleet_checkin"


@needs_tomllib
def test_hub_flag_limits_cards(home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fixture_hubs(home)
    result = runner.invoke(app, ["fleet", "checkin", "--json", "--hub", "elsewhere"])
    assert result.exit_code == 0
    document = json.loads(result.stdout)
    assert [card["hub"] for card in document["cards"]] == ["elsewhere"]
    assert document["hub_list"]["hubs"] == 3


@needs_tomllib
def test_cache_read_creates_nothing(home: Path) -> None:
    _fixture_hubs(home)
    doc, _ = fleet_checkin.checkin()
    assert doc["fleet_snapshot"]["state"] == "missing"
    assert not (home / "state").exists()


def _git(repo: Path, *args: str) -> None:
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@example.com",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@example.com",
    }
    subprocess.run(["git", *args], cwd=repo, env=env, check=True, capture_output=True)


@needs_tomllib
def test_real_status_child_is_peek_only_and_writes_nothing(
    home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = home / "src" / "healthy"
    init_run(path=str(repo), name="Healthy")
    if not (repo / ".git").exists():
        _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "[setup] Start the business repo")
    _hub_list(
        home,
        f"""\
        [[hubs]]
        name = "healthy"
        remote = "github:example-co/healthy"
        checkout = "{repo}"
        """,
    )
    # Only git on the child's PATH: the real gh must not be reachable.
    tools = home / "tools"
    tools.mkdir()
    (tools / "git").symlink_to(shutil.which("git") or "/usr/bin/git")
    monkeypatch.setenv("PATH", str(tools))
    gh_path = shutil.which("gh", path=os.environ["PATH"])
    assert gh_path is None
    monkeypatch.setenv("PYTHONPATH", str(MB_PACKAGE_ROOT))
    for proxy in ("HTTPS_PROXY", "HTTP_PROXY", "https_proxy", "http_proxy"):
        monkeypatch.setenv(proxy, "http://127.0.0.1:9")
    before = _tree(repo)

    started = time.monotonic()
    doc, code = fleet_checkin.checkin(timeout=120)

    assert time.monotonic() - started < 120
    assert code == 0, json.dumps(doc["cards"][0], indent=2)[:2000]
    assert _tree(repo) == before
    assert not (repo / ".mb" / "last-status-seen.json").exists()
    card = doc["cards"][0]
    assert card["state"] == "ok"
    assert card["sections"]["github"]["state"] == "not_checked"
    assert str(home) not in json.dumps(doc)


def test_timeout_kills_the_child_group(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    slow = tmp_path / "slow"
    slow.mkdir()
    real_popen = subprocess.Popen

    def sleeper(args: list[str], **kwargs: Any) -> Any:
        return real_popen([sys.executable, "-c", "import time; time.sleep(60)"], **kwargs)

    monkeypatch.setattr(subprocess, "Popen", sleeper)
    started = time.monotonic()
    payload, error = fleet_checkin.run_status_child(slow, 1)
    assert payload is None
    assert "did not finish within 1 seconds" in error
    assert time.monotonic() - started < 15


@needs_tomllib
def test_needs_you_follows_the_loop_level(home: Path) -> None:
    hubs = _fixture_hubs(home)
    hubs["healthy"].mkdir(parents=True)
    payload = _status_payload(readiness={"level": "needs_attention"})
    doc, _ = fleet_checkin.checkin(status_runner=_runner_for({"healthy": (payload, "")}))
    assert doc["cards"][0]["verdict"] == "needs_you"
    assert doc["overview"]["needs_you"] == 1


@needs_tomllib
def test_unreadable_snapshot_keeps_cards_but_exits_one(home: Path) -> None:
    hubs = _fixture_hubs(home)
    hubs["healthy"].mkdir(parents=True)
    cache = _write_cache(home)
    cache.write_bytes(b"not a sqlite database")
    doc, code = fleet_checkin.checkin(
        hub="healthy", status_runner=_runner_for({"healthy": (_status_payload(), "")})
    )
    assert code == 1
    assert doc["ok"] is False
    assert doc["cards"][0]["state"] == "ok"
    assert doc["fleet_snapshot"]["state"] == "unreadable"
    assert doc["errors"] == ["the fleet snapshot could not be read"]
    assert cache.read_bytes() == b"not a sqlite database"


@needs_tomllib
def test_snapshot_refresh_failures_warn_in_text(home: Path, capsys: Any) -> None:
    _fixture_hubs(home)
    cache = _write_cache(home)
    snapshot, _ = fleet_checkin.read_snapshot(cache)
    assert snapshot is not None
    snapshot["refresh_errors"] = ["a provider read failed"]
    fleet._store(cache, snapshot)
    doc, code = fleet_checkin.checkin(hub="elsewhere")
    assert code == 0
    assert doc["fleet_snapshot"]["refresh_errors"] == 1
    fleet_checkin.render_text(doc)
    assert "snapshot has read failures" in capsys.readouterr().out


@needs_tomllib
def test_cache_path_with_uri_punctuation_is_read_only(home: Path) -> None:
    cache = _write_cache(home)
    special = cache.with_name("fleet?#.db")
    cache.rename(special)
    before = _tree(special.parent)
    snapshot, state = fleet_checkin.read_snapshot(special)
    assert state == "ok"
    assert snapshot is not None
    assert _tree(special.parent) == before


@needs_tomllib
@pytest.mark.parametrize("declared", [True, False])
def test_card_preserves_real_status_bet_fields(home: Path, declared: bool) -> None:
    hubs = _fixture_hubs(home)
    repo = hubs["healthy"]
    (repo / "bets").mkdir(parents=True)
    optional = (
        "stage: working\ncommitment:\n"
        "  action: Send one outreach message\n"
        "  cadence: weekdays\n  evidence: send_id\n"
        if declared
        else ""
    )
    (repo / "bets" / "daily.md").write_text(
        "---\nstatus: open\n" + optional + "---\n\n# Daily bet\n", encoding="utf-8"
    )
    brain = status_mod._brain(repo)
    payload = _status_payload(brain=brain)
    doc, code = fleet_checkin.checkin(
        hub="healthy", status_runner=_runner_for({"healthy": (payload, "")})
    )
    assert code == 0
    bet = doc["cards"][0]["sections"]["bets"]["items"][0]
    assert bet["stage"] == ("working" if declared else "")
    assert bet["commitment"] == (
        {
            "action": "Send one outreach message",
            "cadence": "weekdays",
            "owner": "",
            "evidence": "send_id",
        }
        if declared
        else None
    )
