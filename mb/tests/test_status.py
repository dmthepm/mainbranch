"""``mb status`` daily briefing."""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from mb import codex as codex_mod
from mb import connect as connect_mod
from mb import graph as graph_mod
from mb import status as status_mod
from mb import validate as validate_mod
from mb.cli import app
from mb.freshness import MODE_NEUTRAL_UPDATE_TEXT
from mb.init import run as init_run

runner = CliRunner()
FIXTURES = Path(__file__).parent / "fixtures"


def _without_github_or_claude(name: str) -> str:
    if name in {"gh", "claude"}:
        return ""
    return shutil.which(name) or ""


def _with_codex(name: str) -> str:
    if name == "codex":
        return "/usr/local/bin/codex"
    return shutil.which(name) or ""


def _without_codex(name: str) -> str:
    if name == "codex":
        return ""
    return shutil.which(name) or ""


def _codex_plugin_list_result(repo: Path, *, installed: bool = True) -> dict[str, Any]:
    marketplace = codex_mod.marketplace_path(repo)
    plugin = codex_mod.plugin_manifest_path(repo).parent
    status = "installed, enabled" if installed else "not installed"
    return {
        "ok": True,
        "returncode": 0,
        "stdout": (
            f"Marketplace `{codex_mod.CODEX_MARKETPLACE_NAME}`\n"
            f"{marketplace}\n\n"
            "PLUGIN                                    STATUS              VERSION  PATH\n"
            f"{codex_mod.CODEX_PLUGIN_SELECTOR}  {status}  0.1.0  {plugin}\n"
        ),
        "stderr": "",
        "command": f"codex plugin list --marketplace {codex_mod.CODEX_MARKETPLACE_NAME}",
    }


def _prepare_codex_global_plugin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAINBRANCH_CODEX_PLUGIN_ROOT", str(tmp_path / "codex-global"))
    codex_mod.write_global_plugin_source()


def _prepare_codex_global_skills(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAINBRANCH_CODEX_PLUGIN_ROOT", str(tmp_path / "codex-global"))
    monkeypatch.setenv("MAINBRANCH_CODEX_SKILLS_ROOT", str(tmp_path / "codex-skills"))
    codex_mod.write_global_skill_source()


def _codex_runtime_ok() -> dict[str, Any]:
    return {
        "checked": True,
        "ok": True,
        "state": "ok",
        "shell": "/bin/zsh",
        "command": "command -v mb && mb --version",
        "path": "/usr/local/bin/mb",
        "version": "0.3.31",
        "active_path": "/usr/local/bin/mb",
        "active_version": "0.3.31",
        "path_mismatch": False,
        "version_mismatch": False,
        "mismatch": False,
        "error": "",
        "summary": "Login-shell runtime resolves the active mb.",
        "repair": "",
        "safe_to_share": True,
    }


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )


def _configure_git_user(repo: Path) -> None:
    assert _git(repo, "config", "user.email", "test@example.com").returncode == 0
    assert _git(repo, "config", "user.name", "Test User").returncode == 0


def _commit(repo: Path, relative_path: str, content: str, subject: str, body: str = "") -> None:
    target = repo / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    assert _git(repo, "add", relative_path).returncode == 0
    args = ["commit", "--no-verify", "-m", subject]
    if body:
        args.extend(["-m", body])
    result = _git(repo, *args)
    assert result.returncode == 0, result.stderr


def _write_push(
    repo: Path,
    slug: str,
    *,
    status: str = "active",
    offer: str = "core/offers/coaching/offer.md",
) -> Path:
    push = repo / "pushes" / slug
    push.mkdir(parents=True, exist_ok=True)
    (push / "push.md").write_text(
        (
            "---\n"
            "type: push\n"
            f"slug: {slug[11:]}\n"
            "kind: launch\n"
            f"status: {status}\n"
            "health: on-track\n"
            "goal:\n"
            "  metric: booked calls\n"
            "  target: 5 booked calls\n"
            "  by: 2026-05-20\n"
            "owner: Operator\n"
            "audience: founders\n"
            f"offer: {offer}\n"
            "promise: Ship a sanitized launch.\n"
            "channels: [email]\n"
            "started: 2026-05-06\n"
            "review_on: 2026-05-20\n"
            "---\n\n"
            "# Launch push\n"
        ),
        encoding="utf-8",
    )
    return push


def _write_playbook(
    push: Path,
    *,
    status: str = "active",
    provider_boundary: str = "candidate-adapter",
    approval_status: str = "approved",
    linked_outcomes: str = "[]",
) -> None:
    playbooks = push / "playbooks"
    playbooks.mkdir(parents=True, exist_ok=True)
    (playbooks / "launch.md").write_text(
        (
            "---\n"
            "type: playbook\n"
            f"status: {status}\n"
            "push: ../push.md\n"
            "platform: email\n"
            "provider: manual\n"
            f"provider_boundary: {provider_boundary}\n"
            "trigger:\n"
            "  kind: operator_launch_request\n"
            "resource:\n"
            "  kind: document\n"
            "  value: documents/launch.md\n"
            "approval:\n"
            "  required: true\n"
            f"  status: {approval_status}\n"
            "  approved_by: Operator\n"
            "  approved_at: 2026-05-06\n"
            "state:\n"
            "  provider_refs: []\n"
            "  activated_at:\n"
            "  retired_at:\n"
            "validation:\n"
            "  dry_run: passed\n"
            "  smoke_evidence: []\n"
            f"linked_outcomes: {linked_outcomes}\n"
            "---\n\n"
            "# Launch playbook\n"
        ),
        encoding="utf-8",
    )


def _write_money_path_core(repo: Path) -> None:
    (repo / "core" / "offer.md").write_text(
        (
            "---\n"
            "type: offer\n"
            "status: active\n"
            "---\n\n"
            "# Offer\n\n"
            "## Audience\n"
            "Solo founders who keep losing launch context.\n\n"
            "## Transformation\n"
            "Scattered launch work becomes durable operating memory.\n\n"
            "## Mechanism\n"
            "A repo-backed workflow connects research, offer, proof, and pushes.\n\n"
            "## Pricing\n"
            "$500 setup sprint.\n\n"
            "## Next step\n"
            "Book a fit call for the setup sprint.\n"
        ),
        encoding="utf-8",
    )
    (repo / "core" / "audience.md").write_text(
        (
            "---\n"
            "type: audience\n"
            "status: active\n"
            "---\n\n"
            "# Audience\n\n"
            "## Customer progress\n"
            "They are trying to turn AI-assisted launch work into repeatable progress.\n\n"
            "## Pain\n"
            "They are stuck rebuilding context every session.\n\n"
            "## What they say\n"
            '"I know we learned something, but I cannot find where it went."\n\n'
            "## Common objections\n"
            "Time, trust, and switching cost.\n"
        ),
        encoding="utf-8",
    )


def _write_money_path_proof(repo: Path) -> None:
    proof = repo / "core" / "proof"
    proof.mkdir(parents=True, exist_ok=True)
    (proof / "testimonials.md").write_text(
        "# Testimonials\n\nA founder shipped faster.\n", encoding="utf-8"
    )
    (proof / "typicality.md").write_text(
        "# Typicality\n\nMost users need setup help first.\n", encoding="utf-8"
    )


def test_status_json_degrades_without_github(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    (repo / "core" / "vocabulary.md").write_text(
        "---\n"
        "type: vocabulary\n"
        "status: active\n"
        "terms:\n"
        "  push:\n"
        "    singular: drop\n"
        "    plural: drops\n"
        "  statuses:\n"
        "    active: live\n"
        "  channels:\n"
        "    paid: paid traffic\n"
        "  kinds:\n"
        "    launch: launch\n"
        "---\n"
        "# Vocabulary\n",
        encoding="utf-8",
    )
    (repo / "decisions" / "2026-05-01-pricing.md").write_text(
        "---\ndate: 2026-05-01\nstatus: accepted\n---\n\n# Pricing\n",
        encoding="utf-8",
    )
    (repo / "research" / "2026-05-01-market.md").write_text(
        "---\ndate: 2026-05-01\nsource: desk\n---\n\n# Market\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["status", str(repo), "--json"])

    assert result.exit_code == 0
    report = json.loads(result.stdout)
    assert report["schema_version"] == "1.0"
    assert report["schema"]["name"] == "mainbranch.status"
    assert report["generated_at"]
    assert report["repo"]["looks_like_mainbranch_repo"] is True
    assert report["runtime"]["skill_wiring"]["ok"] is True
    assert report["github"]["authenticated"] is False
    assert report["github"]["source"] == "gh"
    assert "assigned_tasks" in report["github"]["sections"]
    assert report["brain"]["counts"]["decisions"] == 1
    assert report["brain"]["counts"]["bets"] == 0
    assert report["brain"]["recent_research"][0]["title"] == "Market"
    assert report["vocabulary"]["ok"] is True
    assert report["vocabulary"]["path"] == "core/vocabulary.md"
    assert report["vocabulary"]["terms"]["push"] == {"singular": "drop", "plural": "drops"}
    assert report["vocabulary"]["terms"]["statuses"]["active"] == "live"
    assert report["vocabulary"]["terms"]["channels"]["paid"] == "paid traffic"
    assert report["vocabulary"]["terms"]["kinds"]["launch"] == "launch"
    assert report["books"]["schema_version"] == "1.0"
    assert report["books"]["safe_to_share"] is True
    assert report["since_last_check"]["first_run"] is True
    assert report["marker_update"]["ok"] is True
    assert (repo / ".mb" / "last-status-seen.json").is_file()
    assert "readiness" in report
    assert "update" in report
    assert report["ranked_actions"]
    assert report["ranked_actions"][0]["signals"]
    assert "safe_to_share" in report["ranked_actions"][0]


def test_status_schema_v1_matches_golden_fixture(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")

    payload = status_mod.run(
        path=str(repo),
        now=datetime(2026, 5, 4, 12, 0, tzinfo=timezone.utc),
        update_marker=False,
    )
    actual = {
        "schema_version": payload["schema_version"],
        "schema_name": payload["schema"]["name"],
        "top_level_keys": sorted(payload.keys()),
        "section_keys": {
            key: sorted(payload[key].keys())
            for key in [
                "repo",
                "install",
                "update",
                "runtime",
                "git",
                "git_activity",
                "journal",
                "brain",
                "books",
                "vocabulary",
                "team",
                "onboarding",
                "integrations",
                "measurement",
                "github",
                "content_strategy",
                "money_path",
                "since_last_check",
                "drift",
                "readiness",
                "relationship_health",
                "playbook_health",
                "validation",
                "ranked_actions",
                "marker_update",
            ]
            if isinstance(payload[key], dict)
        },
    }
    expected = json.loads(
        (FIXTURES / "status" / "schema-v1-basic.json").read_text(encoding="utf-8")
    )

    assert actual == expected


def test_status_money_path_default_repo_stays_low(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    _prepare_codex_global_plugin(tmp_path, monkeypatch)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    monkeypatch.setattr(
        codex_mod,
        "_codex_plugin_list",
        lambda plugin_repo: _codex_plugin_list_result(Path(plugin_repo)),
    )

    report = status_mod.run(path=str(repo), update_marker=False)

    money_path = report["money_path"]
    assert money_path["schema_version"] == "1.0"
    assert money_path["overall_level"] <= 1
    assert "customer_progress" in money_path["objects"]
    assert money_path["ranked_actions"]


def test_status_books_readiness_fresh_repo_is_compact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    monkeypatch.setattr("mb.books.shutil.which", lambda name: "")
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")

    report = status_mod.run(path=str(repo), update_marker=False)

    books = report["books"]
    assert books["state"] == "not_configured"
    assert books["configured"] is False
    assert books["mention"] is False
    assert books["hledger"]["available"] is False
    assert books["policy"]["present"] is False
    assert books["next_command"] == "mb books status --json"
    assert books["recommended_route"] == {
        "tool": "mb books status",
        "reason": "inspect bookkeeping setup",
    }
    assert books["safe_to_share"] is True


def test_status_books_readiness_redacts_private_paths_and_contents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    monkeypatch.setattr("mb.books.shutil.which", lambda name: "/private/bin/hledger")
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    private_vault = tmp_path / "private-books"
    books_path = repo / "core" / "finance" / "books.md"
    books_path.parent.mkdir(parents=True, exist_ok=True)
    books_path.write_text(
        (
            "---\n"
            "type: books\n"
            "ledger: hledger\n"
            "storage_mode: solo-local\n"
            f'vault_location: "{private_vault}"\n'
            "---\n\n"
            "# Books\n"
        ),
        encoding="utf-8",
    )
    (repo / "core" / "finance" / "chart-of-accounts.md").write_text(
        "---\ntype: chart-of-accounts\nledger: hledger\n---\n\n# Chart\n",
        encoding="utf-8",
    )
    (repo / ".gitignore").write_text(
        ".mb/private/\n*.journal\n*.hledger\n*.ledger\n*.beancount\n",
        encoding="utf-8",
    )
    private_vault.mkdir(parents=True)
    (private_vault / "main.journal").write_text("; PRIVATE_LEDGER_CONTENT\n", encoding="utf-8")

    report = status_mod.run(path=str(repo), update_marker=False)
    payload = json.dumps(report["books"])

    books = report["books"]
    assert books["hledger"]["available"] is True
    assert books["vault"]["location_kind"] == "external"
    assert books["vault"]["exists"] is None
    assert books["ignore"]["ok"] is True
    assert books["chart_of_accounts"]["present"] is True
    assert str(private_vault) not in payload
    assert "/private/bin/hledger" not in payload
    assert "PRIVATE_LEDGER_CONTENT" not in payload


def test_status_money_path_reports_active_bet_exposure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    (repo / "core/finance/books.md").write_text(
        """---
type: books
ledger: hledger
storage_mode: solo-local
vault_location: ".mb/private/books/"
money_path:
  appetite_thresholds:
    small:
      max_amount: 100
      approval: operator
      ledger_required: true
---

# Books
""",
        encoding="utf-8",
    )
    (repo / ".mb/private/books").mkdir(parents=True)
    (repo / ".mb/private/books/main.journal").write_text("; PRIVATE\n", encoding="utf-8")
    (repo / ".gitignore").write_text(".mb/private/\n", encoding="utf-8")
    deadline = date.today()
    (repo / "bets").mkdir(exist_ok=True)
    (repo / "bets/2026-05-16-offer-test.md").write_text(
        (
            "---\n"
            "status: open\n"
            "opened: 2026-05-16\n"
            f"deadline: {deadline.isoformat()}\n"
            "appetite_tier: small\n"
            "money_path:\n"
            "  required: true\n"
            "  bet_id: 2026-05-16-offer-test\n"
            "linked_decisions: []\n"
            "linked_research: []\n"
            "linked_pushes: []\n"
            "linked_outcomes: []\n"
            "public: false\n"
            "channels: []\n"
            "tags: []\n"
            "---\n\n# Offer test\n"
        ),
        encoding="utf-8",
    )

    class _FakeCompleted:
        def __init__(self, stdout: str = "", returncode: int = 0) -> None:
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = ""

    real_run = subprocess.run

    def _fake_hledger(args: Any, *rest: Any, **kwargs: Any) -> Any:
        argv = list(args) if isinstance(args, (list, tuple)) else [args]
        if argv and Path(str(argv[0])).name == "hledger":
            if "check" in argv:
                return _FakeCompleted()
            if "print" in argv:
                return _FakeCompleted(
                    json.dumps(
                        [
                            {
                                "tpostings": [
                                    {
                                        "paccount": "Expenses:Marketing",
                                        "pamount": [
                                            {
                                                "acommodity": "USD",
                                                "aquantity": {
                                                    "decimalMantissa": 12500,
                                                    "decimalPlaces": 2,
                                                },
                                            }
                                        ],
                                    }
                                ]
                            }
                        ]
                    )
                )
        return real_run(args, *rest, **kwargs)

    monkeypatch.setattr("mb.books.shutil.which", lambda name: "/fake/hledger")
    monkeypatch.setattr("mb.books.subprocess.run", _fake_hledger)

    report = status_mod.run(path=str(repo), update_marker=False)

    money_path = report["money_path"]
    assert money_path["policy"]["thresholds_declared"] is True
    assert money_path["active_bets"]["count"] == 1
    assert money_path["active_bets"]["anchored"] == 1
    assert money_path["active_bets"]["gross_exposure"]["display"] == "$125.00"
    assert money_path["active_bets"]["this_week_at_risk"]["display"] == "$125.00"
    assert money_path["active_bets"]["over_cap"][0]["path"] == "bets/2026-05-16-offer-test.md"
    assert money_path["ranked_actions"][0]["id"] == "review-over-cap-bets"


def test_status_money_path_single_offer_structured_caps_without_proof(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    _write_money_path_core(repo)

    report = status_mod.run(path=str(repo), update_marker=False)

    money_path = report["money_path"]
    assert money_path["objects"]["offer"]["level"] == 2
    assert money_path["objects"]["proof"]["level"] == 0
    assert money_path["overall_level"] == 2
    assert money_path["ranked_actions"][0]["component"] == "proof"


def test_status_money_path_reads_layered_channel_strategy(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    channel = repo / "core" / "marketing" / "channels" / "reddit.md"
    channel.write_text(
        (
            "---\n"
            "type: channel_strategy\n"
            "status: draft\n"
            "channel: reddit\n"
            "---\n\n"
            "# Reddit Channel Strategy\n\n"
            "Useful answers, community norms, timing notes, and no spam.\n"
        ),
        encoding="utf-8",
    )

    report = status_mod.run(path=str(repo), update_marker=False)

    channel_strategy = report["money_path"]["objects"]["channel_strategy"]
    assert channel_strategy["level"] == 1
    assert channel_strategy["paths"] == ["core/marketing/channels/reddit.md"]
    assert "docs/content-strategy.md" in channel_strategy["references"]


def test_status_money_path_reads_distribution_strategy_only(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    distribution = repo / "core" / "marketing" / "distribution-strategy.md"
    distribution.write_text(
        (
            "---\n"
            "type: distribution_strategy\n"
            "status: draft\n"
            "---\n\n"
            "# Distribution Strategy\n\n"
            "Blog, email, wiki, social, community, and partner channels work together.\n"
        ),
        encoding="utf-8",
    )

    report = status_mod.run(path=str(repo), update_marker=False)

    channel_strategy = report["money_path"]["objects"]["channel_strategy"]
    assert channel_strategy["level"] == 1
    assert channel_strategy["paths"] == ["core/marketing/distribution-strategy.md"]


def test_status_content_strategy_simple_entry_point_is_healthy(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    (repo / "core" / "content-strategy.md").write_text(
        (
            "---\n"
            "type: content_strategy\n"
            "status: active\n"
            "---\n\n"
            "# Content Strategy\n\n"
            "## Known-for target\n"
            "Be known for durable business memory that agents can read.\n\n"
            "## Pillars\n"
            "Repo truth, operator loops, practical AI-assisted shipping, and proof.\n"
        ),
        encoding="utf-8",
    )

    report = status_mod.run(path=str(repo), update_marker=False)

    content = report["content_strategy"]
    assert content["overall_state"] == "healthy"
    assert content["simple_entry_point"]["exists"] is True
    assert content["simple_entry_point"]["health_state"] == "healthy"
    assert content["counts"]["layers"] == 0


def test_status_content_strategy_reports_disconnected_account_layers(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    (repo / "core" / "content-strategy.md").write_text(
        (
            "---\n"
            "type: content_strategy\n"
            "status: active\n"
            "linked_strategy_layers:\n"
            "  - core/marketing/accounts/x-founder.md\n"
            "---\n\n"
            "# Content Strategy\n\n"
            "The account layer should resolve its channel and person references.\n"
        ),
        encoding="utf-8",
    )
    account = repo / "core" / "marketing" / "accounts" / "x-founder.md"
    account.parent.mkdir(parents=True, exist_ok=True)
    account.write_text(
        (
            "---\n"
            "type: account_strategy\n"
            "status: active\n"
            "platform: x\n"
            "account: founder\n"
            "channel_strategy: core/marketing/channels/x.md\n"
            "voice_source: core/people/founder.md\n"
            "owner: Operator\n"
            "last_reviewed: 2026-05-12\n"
            "update_trigger: Platform norms changed.\n"
            "source_links: []\n"
            "---\n\n"
            "# X Founder Account\n\n"
            "Audience, allowed topics, voice, cadence, content mix, and CTA path.\n"
        ),
        encoding="utf-8",
    )

    report = status_mod.run(path=str(repo), update_marker=False)

    content = report["content_strategy"]
    account_facts = content["layers"]["accounts"][0]
    assert content["overall_state"] == "disconnected"
    assert account_facts["health_state"] == "disconnected"
    assert account_facts["channel_connected"] is False
    assert account_facts["person_connected"] is False


def test_status_content_strategy_reports_stale_indexed_channel(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    (repo / "core" / "content-strategy.md").write_text(
        (
            "---\n"
            "type: content_strategy\n"
            "status: active\n"
            "linked_strategy_layers:\n"
            "  - core/marketing/channels/reddit.md\n"
            "---\n\n"
            "# Content Strategy\n\n"
            "Reddit is the current community channel for durable public answers.\n"
        ),
        encoding="utf-8",
    )
    channel = repo / "core" / "marketing" / "channels" / "reddit.md"
    channel.parent.mkdir(parents=True, exist_ok=True)
    channel.write_text(
        (
            "---\n"
            "type: channel_strategy\n"
            "status: active\n"
            "channel: reddit\n"
            "owner: Operator\n"
            "last_reviewed: 2025-01-01\n"
            "update_trigger: Platform norms changed.\n"
            "source_links: []\n"
            "---\n\n"
            "# Reddit Channel Strategy\n\n"
            "Community norms, timing, content types, anti-spam rules, and review triggers.\n"
        ),
        encoding="utf-8",
    )

    report = status_mod.run(
        path=str(repo),
        update_marker=False,
        now=datetime(2026, 5, 12, tzinfo=timezone.utc),
    )

    content = report["content_strategy"]
    channel_facts = content["layers"]["channels"][0]
    assert content["overall_state"] == "stale"
    assert channel_facts["health_state"] == "stale"
    assert channel_facts["indexed_from_content_strategy"] is True
    assert channel_facts["stale"] is True


def test_status_content_strategy_reports_unindexed_layer_code(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    (repo / "core" / "content-strategy.md").write_text(
        (
            "---\n"
            "type: content_strategy\n"
            "status: active\n"
            "---\n\n"
            "# Content Strategy\n\n"
            "The solo strategy still works, but the channel layer is not indexed yet.\n"
        ),
        encoding="utf-8",
    )
    channel = repo / "core" / "marketing" / "channels" / "reddit.md"
    channel.parent.mkdir(parents=True, exist_ok=True)
    channel.write_text(
        (
            "---\n"
            "type: channel_strategy\n"
            "status: active\n"
            "channel: reddit\n"
            "owner: Operator\n"
            "last_reviewed: 2026-05-12\n"
            "update_trigger: Platform norms changed.\n"
            "source_links: []\n"
            "---\n\n"
            "# Reddit Channel Strategy\n\n"
            "Community norms, timing, content types, anti-spam rules, and review triggers.\n"
        ),
        encoding="utf-8",
    )

    report = status_mod.run(path=str(repo), update_marker=False)

    content = report["content_strategy"]
    finding = next(
        item for item in content["findings"] if item["code"] == "content_strategy_unindexed_layer"
    )
    assert content["overall_state"] == "disconnected"
    assert finding["path"] == "core/marketing/channels/reddit.md"
    assert finding["state"] == "disconnected"
    assert finding["message"] == "layer exists but is not indexed from core/content-strategy.md"


def test_status_money_path_offer_exposes_guardrail_detail(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    _write_money_path_core(repo)

    report = status_mod.run(path=str(repo), update_marker=False)

    offer = report["money_path"]["objects"]["offer"]
    guardrails = offer["guardrails"]
    assert guardrails["checks"]["audience"]["present"] is True
    assert guardrails["checks"]["audience"]["paths"] == ["core/offer.md"]
    assert guardrails["checks"]["risk_reversal"]["present"] is False
    assert "risk_reversal" in guardrails["missing"]
    assert guardrails["proof_boundary_warnings"] == ["proof_claim_without_proof_file"]


def test_status_money_path_generic_proof_quality_stays_structured(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    _write_money_path_core(repo)
    proof = repo / "core" / "proof"
    proof.mkdir(parents=True, exist_ok=True)
    (proof / "testimonials.md").write_text(
        "# Testimonials\n\nGreat work from a happy customer.\n",
        encoding="utf-8",
    )

    report = status_mod.run(path=str(repo), update_marker=False)

    proof_object = report["money_path"]["objects"]["proof"]
    quality = proof_object["quality"]
    assert proof_object["level"] == 2
    assert proof_object["status"] == "structured"
    assert quality["testimonials"]["total"] == 1
    assert quality["testimonials"]["generic"] == 1
    assert quality["testimonials"]["specific"] == 0
    assert quality["claim_links"]["unsupported_offer_claims"] == [
        "core/offer.md: no offer-linked proof detected"
    ]
    assert report["money_path"]["ranked_actions"][0]["id"] == "strengthen-proof-quality"
    assert report["money_path"]["ranked_actions"][0]["missing"] == [
        "specific_testimonials",
        "offer_linked_proof",
        "typicality",
        "supported_offer_claims",
        "outcome_feedback",
    ]


def test_status_money_path_frontmatter_public_true_counts_as_permission(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    _write_money_path_core(repo)
    proof = repo / "core" / "proof"
    proof.mkdir(parents=True, exist_ok=True)
    (proof / "testimonials.md").write_text(
        (
            "---\n"
            "testimonials:\n"
            "  - public: true\n"
            "    before: stuck rebuilding context\n"
            "    outcome: booked 3 calls\n"
            "    timeframe: within 2 weeks\n"
            "---\n\n"
            "# Testimonials\n"
        ),
        encoding="utf-8",
    )

    report = status_mod.run(path=str(repo), update_marker=False)

    testimonials = report["money_path"]["objects"]["proof"]["quality"]["testimonials"]
    assert testimonials["total"] == 1
    assert testimonials["permissioned_public"] == 1
    assert testimonials["specific"] == 1


def test_status_json_peek_handles_date_valued_testimonial_frontmatter(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    _write_money_path_core(repo)
    proof = repo / "core" / "proof"
    proof.mkdir(parents=True, exist_ok=True)
    (proof / "testimonials.md").write_text(
        (
            "---\n"
            "testimonials:\n"
            "  - public: true\n"
            "    received_on: 2026-05-16\n"
            "    before: stuck rebuilding context\n"
            "    outcome: booked 3 calls\n"
            "    timeframe: within 2 weeks\n"
            "---\n\n"
            "# Testimonials\n"
        ),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["status", str(repo), "--json", "--peek"])

    assert result.exit_code == 0
    assert "Traceback" not in result.stdout
    assert "Traceback" not in result.stderr
    report = json.loads(result.stdout)
    testimonials = report["money_path"]["objects"]["proof"]["quality"]["testimonials"]
    assert testimonials["total"] == 1
    assert testimonials["permissioned_public"] == 1


def test_status_money_path_specific_unpermissioned_proof_blocks_public_marketing(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    _write_money_path_core(repo)
    proof = repo / "core" / "proof"
    proof.mkdir(parents=True, exist_ok=True)
    (proof / "testimonials.md").write_text(
        (FIXTURES / "proof" / "specific-unpermissioned-testimonials.md").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    (proof / "typicality.md").write_text(
        (
            "# Typicality\n\n"
            "Average case: most users need one setup week. Caveat: outcomes vary. "
            "Common failure context: no clear offer. Time to outcome is usually 2 weeks.\n"
        ),
        encoding="utf-8",
    )

    report = status_mod.run(path=str(repo), update_marker=False)

    proof_object = report["money_path"]["objects"]["proof"]
    quality = proof_object["quality"]
    testimonials = quality["testimonials"]
    assert testimonials["specific"] == 2
    assert testimonials["permissioned_public"] == 0
    assert testimonials["specific_permissioned_public"] == 0
    assert quality["public_marketing"] == {
        "ready": False,
        "status": "blocked",
        "summary": (
            "Specific proof exists for internal strategy, but no specific "
            "testimonial is permissioned for public marketing."
        ),
        "missing": ["permissioned_public_testimonials"],
        "next_action": "collect_public_permission",
    }
    assert report["money_path"]["ranked_actions"][0]["id"] == "collect-proof-permission"
    assert report["money_path"]["ranked_actions"][0]["source"] == (
        "money_path.objects.proof.quality.public_marketing"
    )


def test_status_money_path_proof_cannot_reach_field_tested_without_level_three(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    _write_money_path_core(repo)
    proof = repo / "core" / "proof"
    proof.mkdir(parents=True, exist_ok=True)
    (proof / "testimonials.md").write_text(
        (
            "# Testimonials\n\n"
            "## Founder A\n"
            "Permissioned public source: sales call. Before: stuck. "
            "Outcome: booked 3 calls within 2 weeks.\n\n"
            "## Founder B\n"
            "Approved for public source: interview. Previously scattered. "
            "Result: saved 5 hours in 10 days.\n"
        ),
        encoding="utf-8",
    )

    report = status_mod.run(path=str(repo), update_marker=False)

    proof_object = report["money_path"]["objects"]["proof"]
    quality = proof_object["quality"]
    assert quality["testimonials"]["specific"] == 2
    assert quality["testimonials"]["permissioned_public"] == 2
    assert quality["testimonials"]["linked_to_offer"] == 0
    assert quality["typicality"]["exists"] is False
    assert proof_object["level"] == 2
    assert proof_object["status"] == "structured"


def test_status_money_path_common_offer_slug_in_prose_does_not_link_offer(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    _write_money_path_core(repo)
    offer = repo / "core" / "offers" / "coaching"
    offer.mkdir(parents=True, exist_ok=True)
    (offer / "offer.md").write_text(
        "---\nslug: coaching\nstatus: running\n---\n\n# Coaching\n\nAudience and proof.\n",
        encoding="utf-8",
    )
    proof = repo / "core" / "proof"
    proof.mkdir(parents=True, exist_ok=True)
    (proof / "testimonials.md").write_text(
        (
            "# Testimonials\n\n"
            "## Founder A\n"
            "Before: stuck rebuilding context. Outcome: booked 3 calls within 2 weeks "
            "after coaching helped clarify the workflow.\n"
        ),
        encoding="utf-8",
    )

    report = status_mod.run(path=str(repo), update_marker=False)

    quality = report["money_path"]["objects"]["proof"]["quality"]
    assert quality["testimonials"]["specific"] == 1
    assert quality["testimonials"]["linked_to_offer"] == 0
    assert quality["claim_links"]["linked_offers"] == []
    assert (
        "core/offers/coaching/offer.md: no offer-linked proof detected"
        in quality["claim_links"]["unsupported_offer_claims"]
    )


def test_status_money_path_permission_warning_only_applies_to_testimonials(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    typicality_repo = tmp_path / "typicality"
    init_run(path=str(typicality_repo), name="Typicality")
    _write_money_path_core(typicality_repo)
    typicality_proof = typicality_repo / "core" / "proof"
    typicality_proof.mkdir(parents=True, exist_ok=True)
    (typicality_proof / "typicality.md").write_text(
        "# Typicality\n\nMost users need setup help first.\n",
        encoding="utf-8",
    )

    typicality_report = status_mod.run(path=str(typicality_repo), update_marker=False)

    typicality_warnings = typicality_report["money_path"]["objects"]["offer"]["guardrails"][
        "proof_boundary_warnings"
    ]
    assert "testimonials_without_permissioned_public_signal" not in typicality_warnings

    testimonial_repo = tmp_path / "testimonial"
    init_run(path=str(testimonial_repo), name="Testimonial")
    _write_money_path_core(testimonial_repo)
    testimonial_proof = testimonial_repo / "core" / "proof"
    testimonial_proof.mkdir(parents=True, exist_ok=True)
    (testimonial_proof / "testimonials.md").write_text(
        "# Testimonials\n\nGreat work from a happy customer.\n",
        encoding="utf-8",
    )

    testimonial_report = status_mod.run(path=str(testimonial_repo), update_marker=False)

    testimonial_warnings = testimonial_report["money_path"]["objects"]["offer"]["guardrails"][
        "proof_boundary_warnings"
    ]
    assert "testimonials_without_permissioned_public_signal" in testimonial_warnings


def test_status_money_path_specific_typicality_without_offer_link_reaches_evidence_backed(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    _write_money_path_core(repo)
    proof = repo / "core" / "proof"
    proof.mkdir(parents=True, exist_ok=True)
    (proof / "testimonials.md").write_text(
        (
            "# Testimonials\n\n"
            "## Founder A\n"
            "Before: stuck rebuilding context. Outcome: booked 3 calls within 2 weeks.\n"
        ),
        encoding="utf-8",
    )
    (proof / "typicality.md").write_text(
        (
            "# Typicality\n\n"
            "Average case: most users need one setup week. Caveat: outcomes vary. "
            "Common failure context: poor fit. Time to outcome is usually 2 weeks.\n"
        ),
        encoding="utf-8",
    )

    report = status_mod.run(path=str(repo), update_marker=False)

    proof_object = report["money_path"]["objects"]["proof"]
    quality = proof_object["quality"]
    assert proof_object["level"] == 3
    assert proof_object["status"] == "evidence_backed"
    assert quality["testimonials"]["specific"] == 1
    assert quality["testimonials"]["linked_to_offer"] == 0
    assert quality["claim_links"]["unsupported_offer_claims"] == [
        "core/offer.md: no offer-linked proof detected"
    ]


def test_status_money_path_offer_linked_proof_without_outcome_feedback_is_not_instrumented(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    offer = repo / "core" / "offers" / "coaching"
    offer.mkdir(parents=True, exist_ok=True)
    (offer / "offer.md").write_text(
        (
            "---\nslug: coaching\nstatus: running\n---\n\n"
            "# Coaching\n\n"
            "Audience, transformation, mechanism, pricing, proof, objections, "
            "reason to act, and next step.\n"
        ),
        encoding="utf-8",
    )
    proof = offer / "proof"
    proof.mkdir(parents=True, exist_ok=True)
    (proof / "testimonials.md").write_text(
        (
            "# Testimonials\n\n"
            "## Founder A\n"
            "Permissioned public source: sales call. Before: stuck rebuilding context. "
            "Outcome: booked 3 calls within 2 weeks using the workflow. "
            "Objection: worried about time.\n\n"
            "## Founder B\n"
            "Approved for public source: interview. Previously scattered launches. "
            "Result: saved 5 hours in 10 days through the process.\n"
        ),
        encoding="utf-8",
    )
    (proof / "typicality.md").write_text(
        (
            "# Typicality\n\n"
            "Average case: most users need one setup week before speed improves. "
            "Caveat: outcomes vary. Common failure context: poor fit when no offer "
            "exists. Time to outcome is usually 2 weeks.\n"
        ),
        encoding="utf-8",
    )
    push = _write_push(repo, "2026-05-06-launch", offer="core/offers/coaching/offer.md")
    _write_playbook(push, status="active", approval_status="approved")

    report = status_mod.run(path=str(repo), update_marker=False)

    proof_object = report["money_path"]["objects"]["proof"]
    quality = proof_object["quality"]
    assert proof_object["level"] == 4
    assert proof_object["status"] == "field_tested"
    assert quality["testimonials"]["total"] == 2
    assert quality["testimonials"]["specific"] == 2
    assert quality["testimonials"]["permissioned_public"] == 2
    assert quality["testimonials"]["linked_to_offer"] == 2
    assert quality["testimonials"]["with_timeframe"] == 2
    assert quality["testimonials"]["with_metric"] == 2
    assert quality["typicality"] == {
        "exists": True,
        "has_average_case": True,
        "has_caveats": True,
        "has_common_failure_context": True,
        "has_time_to_outcome": True,
    }
    assert quality["claim_links"]["linked_offers"] == ["core/offers/coaching/offer.md"]
    assert quality["claim_links"]["unsupported_offer_claims"] == []
    assert quality["instrumentation"]["active_push"] is True
    assert quality["instrumentation"]["playbook"] is True
    assert quality["instrumentation"]["outcome_feedback"] is False
    assert any(
        action["id"] == "strengthen-proof-quality" and "outcome_feedback" in action["missing"]
        for action in report["money_path"]["ranked_actions"]
    )


def test_status_money_path_level_five_proof_requires_outcome_feedback(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    offer = repo / "core" / "offers" / "coaching"
    offer.mkdir(parents=True, exist_ok=True)
    (offer / "offer.md").write_text(
        (
            "---\nslug: coaching\nstatus: running\n---\n\n"
            "# Coaching\n\n"
            "Audience, transformation, mechanism, pricing, proof, objections, "
            "reason to act, and next step.\n"
        ),
        encoding="utf-8",
    )
    proof = offer / "proof"
    proof.mkdir(parents=True, exist_ok=True)
    (proof / "testimonials.md").write_text(
        (
            "# Testimonials\n\n"
            "## Founder A\n"
            "Permissioned public source: sales call. Before: stuck rebuilding context. "
            "Outcome: booked 3 calls within 2 weeks using the workflow. "
            "Objection: worried about time.\n\n"
            "## Founder B\n"
            "Approved for public source: interview. Previously scattered launches. "
            "Result: saved 5 hours in 10 days through the process.\n"
        ),
        encoding="utf-8",
    )
    (proof / "typicality.md").write_text(
        (
            "# Typicality\n\n"
            "Average case: most users need one setup week before speed improves. "
            "Caveat: outcomes vary. Common failure context: poor fit when no offer "
            "exists. Time to outcome is usually 2 weeks.\n"
        ),
        encoding="utf-8",
    )
    push = _write_push(repo, "2026-05-06-launch", offer="core/offers/coaching/offer.md")
    _write_playbook(
        push,
        status="active",
        approval_status="approved",
        linked_outcomes='["log/2026-05-20-launch-outcome.md"]',
    )

    report = status_mod.run(path=str(repo), update_marker=False)

    proof_object = report["money_path"]["objects"]["proof"]
    quality = proof_object["quality"]
    assert proof_object["level"] == 5
    assert proof_object["status"] == "instrumented"
    assert quality["instrumentation"]["active_push"] is True
    assert quality["instrumentation"]["playbook"] is True
    assert quality["instrumentation"]["outcome_feedback"] is True
    assert all(
        action["id"] != "strengthen-proof-quality"
        for action in report["money_path"]["ranked_actions"]
    )


def test_status_money_path_strong_proof_ranks_below_channel(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    # Shaped offer/audience/customer-progress, field-tested proof, but no channel
    # or active push yet -- the agency archetype shape from the dogfood.
    _write_money_path_core(repo)
    proof = repo / "core" / "proof"
    proof.mkdir(parents=True, exist_ok=True)
    (proof / "testimonials.md").write_text(
        (
            "# Testimonials\n\n"
            "## Founder A\n"
            "Permissioned public source: sales call. Before: stuck rebuilding context. "
            "Outcome: booked 3 calls within 2 weeks using the workflow. "
            "Objection: worried about time.\n\n"
            "## Founder B\n"
            "Approved for public source: interview. Previously scattered launches. "
            "Result: saved 5 hours in 10 days through the process.\n"
        ),
        encoding="utf-8",
    )
    (proof / "typicality.md").write_text(
        (
            "# Typicality\n\n"
            "Average case: most users need one setup week before speed improves. "
            "Caveat: outcomes vary. Common failure context: poor fit when no offer "
            "exists. Time to outcome is usually 2 weeks.\n"
        ),
        encoding="utf-8",
    )

    report = status_mod.run(path=str(repo), update_marker=False)

    assert report["money_path"]["objects"]["proof"]["level"] == 4
    ids = [action["id"] for action in report["money_path"]["ranked_actions"]]
    # Field-tested proof should not bury packaging/channel moves. Channel gap ranks
    # ahead of polishing already-strong proof.
    assert "connect-channel-strategy" in ids
    assert "strengthen-proof-quality" in ids
    assert ids.index("connect-channel-strategy") < ids.index("strengthen-proof-quality")


def _write_active_bet(repo: Path, slug: str, *, committed: bool) -> None:
    money_path_block = "money_path:\n  required: true\n  bet_id: launch\n" if committed else ""
    (repo / "bets" / f"{slug}.md").write_text(
        (
            "---\n"
            "status: open\n"
            "opened: 2026-05-16\n"
            "deadline: 2026-12-01\n"
            "appetite: 2 weeks\n"
            f"{money_path_block}"
            "hypothesis: A pricing test creates calls.\n"
            "metric: calls\n"
            "target: 3 calls\n"
            "result: ''\n"
            "public: false\n"
            "channels: []\n"
            "tags: []\n"
            "exit_criteria:\n"
            "  kill: drop if under 1 call\n"
            "  double_down: scale past 5 calls\n"
            "---\n\n"
            "# Active bet\n"
        ),
        encoding="utf-8",
    )


def _raise_exposure(**_kwargs: object) -> dict[str, object]:
    raise RuntimeError("ledger unavailable")


def test_status_money_path_books_repair_skips_exploratory_bets(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    monkeypatch.setattr(
        status_mod.books_mod,  # type: ignore[attr-defined]
        "exposure",
        _raise_exposure,
    )
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    _write_active_bet(repo, "2026-05-16-explore", committed=False)

    report = status_mod.run(path=str(repo), update_marker=False)

    active_bets = report["money_path"]["active_bets"]
    assert active_bets["ledger_unavailable"] is True
    assert active_bets["requires_anchor"] is False
    ids = {action["id"] for action in report["money_path"]["ranked_actions"]}
    # An exploratory bet that has not committed spend should not trigger an eager
    # ledger-repair nudge.
    assert "repair-books-exposure" not in ids


def test_status_money_path_books_repair_fires_for_committed_bet(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    monkeypatch.setattr(
        status_mod.books_mod,  # type: ignore[attr-defined]
        "exposure",
        _raise_exposure,
    )
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    _write_active_bet(repo, "2026-05-16-committed", committed=True)

    report = status_mod.run(path=str(repo), update_marker=False)

    active_bets = report["money_path"]["active_bets"]
    assert active_bets["ledger_unavailable"] is True
    assert active_bets["requires_anchor"] is True
    repair = next(
        action
        for action in report["money_path"]["ranked_actions"]
        if action["id"] == "repair-books-exposure"
    )
    # Owner-facing reason names the committed-anchor trigger; no private amounts.
    assert "requires MoneyPath anchoring" in repair["reason"]
    assert repair["safe_to_share"] is True


def test_status_money_path_detects_multi_offer_product_ladder(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    _write_money_path_core(repo)
    offer = repo / "core" / "offers" / "community"
    offer.mkdir(parents=True, exist_ok=True)
    (offer / "offer.md").write_text(
        (
            "---\nslug: community\nstatus: running\n---\n\n"
            "# Community\n\n"
            "Audience, transformation, mechanism, pricing, next step.\n"
        ),
        encoding="utf-8",
    )
    (repo / "core" / "product-ladder.md").write_text(
        (
            "# Product ladder\n\n"
            "Entry offer feeds into the paid community. Ascension moves into "
            "retention and upgrade offers.\n"
        ),
        encoding="utf-8",
    )

    report = status_mod.run(path=str(repo), update_marker=False)

    ladder = report["money_path"]["objects"]["product_ladder"]
    assert ladder["level"] >= 2
    assert ladder["paths"] == ["core/product-ladder.md"]
    assert ladder["missing"] == []


def test_status_money_path_product_ladder_names_missing_requirements(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    _write_money_path_core(repo)
    offer = repo / "core" / "offers" / "community"
    offer.mkdir(parents=True, exist_ok=True)
    (offer / "offer.md").write_text(
        (
            "---\nslug: community\nstatus: running\n---\n\n"
            "# Community\n\n"
            "Audience, transformation, mechanism, pricing, next step.\n"
        ),
        encoding="utf-8",
    )
    (repo / "core" / "product-ladder.md").write_text(
        "# Product ladder\n\nEntry offer only.\n",
        encoding="utf-8",
    )

    report = status_mod.run(path=str(repo), update_marker=False)

    ladder = report["money_path"]["objects"]["product_ladder"]
    assert ladder["level"] == 1
    assert ladder["missing"] == ["ascension_path", "retention_offer"]


def test_status_money_path_flags_ambiguous_live_multi_offer(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    _write_money_path_core(repo)
    for slug in ("community", "workshop"):
        offer = repo / "core" / "offers" / slug
        offer.mkdir(parents=True, exist_ok=True)
        (offer / "offer.md").write_text(
            (
                f"---\nslug: {slug}\nstatus: running\n---\n\n"
                f"# {slug}\n\nAudience, transformation, mechanism, pricing, next step.\n"
            ),
            encoding="utf-8",
        )

    report = status_mod.run(path=str(repo), update_marker=False)

    offer = report["money_path"]["objects"]["offer"]
    assert offer["status"] == "ambiguous_multi_offer"
    assert "active_offer_selection" in offer["missing"]
    assert report["money_path"]["overall_level"] <= 1


def test_status_money_path_push_playbook_without_outcome_cannot_reach_instrumented(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    _write_money_path_core(repo)
    _write_money_path_proof(repo)
    push = _write_push(repo, "2026-05-06-launch", offer="core/offer.md")
    _write_playbook(push, status="active", approval_status="approved")

    report = status_mod.run(path=str(repo), update_marker=False)

    money_path = report["money_path"]
    assert money_path["objects"]["playbook"]["level"] >= 2
    assert money_path["objects"]["outcome_feedback_loop"]["level"] == 0
    assert money_path["overall_level"] == 4


def test_status_money_path_fully_connected_path_can_reach_instrumented(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    _write_money_path_core(repo)
    _write_money_path_proof(repo)
    push = _write_push(repo, "2026-05-06-launch", offer="core/offer.md")
    _write_playbook(
        push,
        status="active",
        approval_status="approved",
        linked_outcomes='["log/2026-05-20-launch-outcome.md"]',
    )

    def ready_measurement(_repo: Path) -> dict[str, Any]:
        return {
            "available": True,
            "state": "ready",
            "ok": True,
            "summary": "Local readiness checks passed.",
            "repair": "",
            "repair_command": "mb site check",
            "site_repo": "",
            "business_repo": str(repo),
            "facts": {"conversion_kind": "lead_form"},
            "blocked_count": 0,
            "manual_count": 0,
            "safe_to_share": True,
        }

    monkeypatch.setattr(status_mod, "_measurement", ready_measurement)

    report = status_mod.run(path=str(repo), update_marker=False)

    assert report["money_path"]["objects"]["page_readiness"]["level"] == 5
    assert report["money_path"]["objects"]["outcome_feedback_loop"]["level"] >= 3
    assert report["money_path"]["overall_level"] == 5
    assert all(
        action["id"] != "close-outcome-loop" for action in report["money_path"]["ranked_actions"]
    )


def test_status_vocabulary_falls_back_with_warnings_for_unknown_terms(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    (repo / "core" / "vocabulary.md").write_text(
        "---\n"
        "type: vocabulary\n"
        "terms:\n"
        "  push:\n"
        "    singular: challenge\n"
        "    plural: challenges\n"
        "    folder: challenges\n"
        "  paths:\n"
        "    pushes: challenges\n"
        "  statuses:\n"
        "    active: running\n"
        "    completed: wrapped\n"
        "---\n"
        "# Vocabulary\n",
        encoding="utf-8",
    )

    report = status_mod.run(path=str(repo), update_marker=False)

    vocabulary = report["vocabulary"]
    assert vocabulary["ok"] is True
    assert vocabulary["terms"]["push"] == {"singular": "challenge", "plural": "challenges"}
    assert vocabulary["terms"]["statuses"] == {"active": "running", "completed": "wrapped"}
    assert "paths" not in vocabulary["terms"]
    assert any("terms.paths is not recognized" in warning for warning in vocabulary["warnings"])
    assert any(
        "terms.push.folder is not recognized" in warning for warning in vocabulary["warnings"]
    )


def test_status_vocabulary_reports_malformed_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    (repo / "core" / "vocabulary.md").write_text("# Vocabulary\n", encoding="utf-8")

    report = status_mod.run(path=str(repo), update_marker=False)

    assert report["vocabulary"]["ok"] is False
    assert report["vocabulary"]["exists"] is True
    assert report["vocabulary"]["terms"]["push"] == {"singular": "push", "plural": "pushes"}
    assert report["vocabulary"]["errors"] == ["missing YAML frontmatter"]


def test_status_vocabulary_returns_defaults_when_file_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    (repo / "core" / "vocabulary.md").unlink()

    report = status_mod.run(path=str(repo), update_marker=False)

    vocabulary = report["vocabulary"]
    assert vocabulary["exists"] is False
    assert vocabulary["ok"] is True
    assert vocabulary["source"] == "defaults"
    assert vocabulary["terms"]["push"] == {"singular": "push", "plural": "pushes"}
    assert vocabulary["summary"] == "Using default vocabulary: push/pushes."


def test_status_vocabulary_summary_reflects_non_push_customizations(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    (repo / "core" / "vocabulary.md").write_text(
        "---\ntype: vocabulary\nterms:\n  statuses:\n    active: live\n---\n# Vocabulary\n",
        encoding="utf-8",
    )

    report = status_mod.run(path=str(repo), update_marker=False)

    vocabulary = report["vocabulary"]
    assert vocabulary["ok"] is True
    assert vocabulary["terms"]["push"] == {"singular": "push", "plural": "pushes"}
    assert vocabulary["summary"] == "Using operator vocabulary: push/pushes."


def test_status_drift_does_not_warn_for_codex_instructions_until_codex_is_present(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    monkeypatch.setattr(codex_mod, "_which", _without_codex)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    (repo / "AGENTS.md").unlink()

    report = status_mod.run(path=str(repo), update_marker=False)

    assert not any(
        item["id"] == "codex_instructions_not_ready" for item in report["drift"]["items"]
    )

    monkeypatch.setattr(codex_mod, "_which", _with_codex)
    report = status_mod.run(path=str(repo), update_marker=False)

    assert any(item["id"] == "codex_instructions_not_ready" for item in report["drift"]["items"])


def test_status_warns_when_codex_runtime_uses_stale_mb(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    monkeypatch.setattr(codex_mod, "_which", _with_codex)
    monkeypatch.setattr(
        codex_mod,
        "_login_shell_mb_diagnostics",
        lambda: {
            "checked": True,
            "ok": False,
            "state": "warn",
            "shell": "/bin/zsh",
            "command": "command -v mb && mb --version",
            "path": "/old/bin/mb",
            "version": "0.3.18",
            "active_path": "/new/bin/mb",
            "active_version": "0.3.29",
            "path_mismatch": True,
            "version_mismatch": True,
            "mismatch": True,
            "error": "",
            "summary": "Login-shell runtime resolves a different mb than this process.",
            "repair": "Put the current Main Branch install earlier on the login-shell PATH.",
            "safe_to_share": True,
        },
    )
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")

    report = status_mod.run(path=str(repo), update_marker=False)

    codex = report["runtime"]["codex_cli"]
    assert codex["ok"] is False
    assert codex["status"] == "runtime_mismatch"
    assert codex["static_ok"] is True
    finding = next(
        item for item in report["drift"]["items"] if item["id"] == "codex_runtime_mb_mismatch"
    )
    assert "different mb" in finding["summary"]
    assert "login-shell PATH" in finding["repair"]


def test_status_does_not_treat_non_mismatch_codex_runtime_context_as_mismatch(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    monkeypatch.setattr(codex_mod, "_which", _with_codex)
    monkeypatch.setattr(
        codex_mod,
        "_login_shell_mb_diagnostics",
        lambda: {
            "checked": True,
            "ok": False,
            "state": "info",
            "shell": "/bin/zsh",
            "command": "command -v mb && mb --version",
            "path": "/inactive/old/mb",
            "version": "0.3.18",
            "active_path": "/current/bin/mb",
            "active_version": "0.3.41",
            "path_mismatch": False,
            "version_mismatch": False,
            "mismatch": False,
            "error": "",
            "summary": (
                "An inactive old mb install was observed, but active/runtime mismatch "
                "flags are false."
            ),
            "repair": "",
            "safe_to_share": True,
        },
    )
    _prepare_codex_global_skills(tmp_path, monkeypatch)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")

    report = status_mod.run(path=str(repo), update_marker=False)

    codex = report["runtime"]["codex_cli"]
    assert codex["runtime"]["mismatch"] is False
    assert codex["status"] == "runtime_unverified"
    assert not any(item["id"] == "codex_runtime_mb_mismatch" for item in report["drift"]["items"])


def test_status_marks_codex_not_ready_when_global_skills_are_missing(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    monkeypatch.setattr(codex_mod, "_which", _with_codex)
    monkeypatch.setattr(codex_mod, "_login_shell_mb_diagnostics", _codex_runtime_ok)
    monkeypatch.setenv("MAINBRANCH_CODEX_PLUGIN_ROOT", str(tmp_path / "codex-global"))
    monkeypatch.setenv("MAINBRANCH_CODEX_SKILLS_ROOT", str(tmp_path / "codex-skills"))
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")

    report = status_mod.run(path=str(repo), update_marker=False)

    codex = report["runtime"]["codex_cli"]
    assert codex["ok"] is False
    assert codex["status"] == "global_skill_missing_or_stale"
    assert codex["static_ok"] is True
    assert codex["runtime_ok"] is True
    assert codex["global_skill_ok"] is False
    assert "mb-start/SKILL.md" in codex["global_skill"]["missing"]
    finding = next(
        item for item in report["drift"]["items"] if item["id"] == "codex_global_skills_not_ready"
    )
    assert codex_mod.repair_command(repo) in finding["repair"]


def test_status_marks_codex_ready_when_global_skills_are_installed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    monkeypatch.setattr(codex_mod, "_which", _with_codex)
    monkeypatch.setattr(codex_mod, "_login_shell_mb_diagnostics", _codex_runtime_ok)
    _prepare_codex_global_skills(tmp_path, monkeypatch)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")

    report = status_mod.run(path=str(repo), update_marker=False)

    codex = report["runtime"]["codex_cli"]
    assert codex["ok"] is True
    assert codex["status"] == "ready"
    assert codex["global_skill_ok"] is True
    assert codex["generated_guidance_ready"] is True
    assert codex["command_surface_ok"] is True
    assert codex["slash_commands_ready"] is False
    assert set(codex["global_skill"]["required_skills"]) == set(codex_mod.CODEX_GLOBAL_SKILL_NAMES)
    assert codex["global_skill"]["skills"]["mb-start"]["ok"] is True
    assert codex["global_skill"]["skills"]["mb-ads"]["ok"] is True


def test_status_readiness_separates_repo_runtime_from_business_memory(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")

    report = status_mod.run(path=str(repo), update_marker=False)

    dimensions = report["readiness"]["dimensions"]
    assert dimensions["repo_runtime"]["level"] == report["readiness"]["level"]
    assert dimensions["business_memory"]["state"] in {
        "needs_input",
        "needs_attention",
        "ready",
    }
    assert "Business memory is" in report["readiness"]["summary"]


def test_status_json_exposes_push_and_legacy_campaign_facts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    push = repo / "pushes" / "2026-05-06-workshop"
    push.mkdir(parents=True)
    (push / "push.md").write_text(
        "---\n"
        "type: push\n"
        "slug: workshop\n"
        "kind: launch\n"
        "status: active\n"
        "health: on-track\n"
        "goal:\n"
        "  metric: qualified calls\n"
        "  target: 10 qualified calls\n"
        "  by: 2026-05-20\n"
        "owner: Devon\n"
        "audience: founders\n"
        "offer: core/offers/workshop/offer.md\n"
        "promise: Own the launch memory in git.\n"
        "---\n"
        "# Workshop\n",
        encoding="utf-8",
    )
    campaign = repo / "campaigns" / "2026-05-legacy"
    campaign.mkdir(parents=True)
    (campaign / "campaign.md").write_text(
        "---\ntype: campaign\nslug: legacy\nstatus: active\n---\n# Legacy\n",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["status", str(repo), "--json", "--peek"])

    assert result.exit_code == 0
    report = json.loads(result.stdout)
    assert report["push_count"] == 2
    assert report["canonical_push_count"] == 1
    assert report["campaign_count"] == 1
    assert report["deprecated_campaign_keys"] is True
    assert report["push_compatibility"]["legacy_campaign_keys_deprecated"] is True
    assert report["pushes"][0]["path"] == "pushes/2026-05-06-workshop/push.md"
    assert report["pushes"][0]["date"] == "2026-05-06"
    assert report["campaigns"][0]["path"] == "campaigns/2026-05-legacy/campaign.md"
    assert {item["path"] for item in report["active_pushes"]} == {
        "pushes/2026-05-06-workshop/push.md",
        "campaigns/2026-05-legacy/campaign.md",
    }


def test_status_playbook_health_accepts_healthy_active_push_playbook(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    offer = repo / "core" / "offers" / "coaching"
    offer.mkdir(parents=True)
    (offer / "offer.md").write_text(
        "---\nslug: coaching\nstatus: running\n---\n\n# Coaching\n",
        encoding="utf-8",
    )
    push = _write_push(repo, "2026-05-06-launch")
    _write_playbook(push, status="active", approval_status="approved")

    report = status_mod.run(path=str(repo), update_marker=False)

    health = report["playbook_health"]
    assert health["ok"] is True
    assert health["summary"]["playbooks"] == 1
    assert health["summary"]["pushes_without_playbook"] == 0
    assert health["summary"]["pending_playbook_statuses"] == 0
    assert health["summary"]["playbook_approval_needed"] == 0
    assert health["gaps"] == []

    human = runner.invoke(app, ["status", str(repo), "--no-color", "--peek"])
    assert human.exit_code == 0
    assert "Playbook health" not in human.stdout


def test_status_playbook_health_flags_active_push_without_playbook(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    push = _write_push(repo, "2026-05-06-launch")

    result = runner.invoke(app, ["status", str(repo), "--json", "--peek"])

    assert result.exit_code == 0
    report = json.loads(result.stdout)
    health = report["playbook_health"]
    assert health["ok"] is False
    assert health["summary"]["pushes_without_playbook"] == 1
    assert health["sections"]["pushes"]["without_playbook"][0]["path"] == (
        "pushes/2026-05-06-launch/push.md"
    )
    assert any(item["id"] == "playbook_health_gaps" for item in report["drift"]["items"])
    assert any(action["id"] == "review_playbook_health" for action in report["ranked_actions"])

    human = runner.invoke(app, ["status", str(repo), "--no-color", "--peek"])

    assert human.exit_code == 0
    assert "Playbook health" in human.stdout
    assert "active/planned push(es) need a playbook run" in human.stdout
    assert push.is_dir()


def test_status_playbook_health_flags_pending_and_completed_without_outcome(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    planned = _write_push(repo, "2026-05-06-planned", status="planned")
    _write_playbook(
        planned,
        status="draft",
        provider_boundary="plan-only",
        approval_status="needed",
    )
    completed = _write_push(repo, "2026-05-07-completed", status="completed")
    _write_playbook(completed, status="completed", approval_status="approved")

    report = status_mod.run(path=str(repo), update_marker=False)

    health = report["playbook_health"]
    assert health["summary"]["pending_playbook_statuses"] == 1
    assert health["summary"]["playbook_approval_needed"] == 1
    assert health["summary"]["completed_playbooks_without_outcome"] == 1
    assert health["summary"]["manual_provider_boundaries"] == 1
    assert health["sections"]["playbooks"]["pending_status"][0]["path"] == (
        "pushes/2026-05-06-planned/playbooks/launch.md"
    )
    assert health["sections"]["playbooks"]["completed_without_outcome"][0]["path"] == (
        "pushes/2026-05-07-completed/playbooks/launch.md"
    )


def test_status_playbook_health_ignores_retired_playbook_approval(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    push = _write_push(repo, "2026-05-06-launch")
    _write_playbook(
        push,
        status="retired",
        provider_boundary="plan-only",
        approval_status="",
    )

    report = status_mod.run(path=str(repo), update_marker=False)

    health = report["playbook_health"]
    assert health["summary"]["playbook_approval_needed"] == 0
    assert health["summary"]["manual_provider_boundaries"] == 0
    assert health["gaps"] == []


def test_status_relationship_health_flags_active_bet_and_offer_gaps(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    offer = repo / "core" / "offers" / "coaching"
    offer.mkdir(parents=True)
    (offer / "offer.md").write_text(
        "---\nslug: coaching\nstatus: running\n---\n\n# Coaching\n",
        encoding="utf-8",
    )
    # Time-stable deadline (same convention as the brain-payload test below): the
    # hardcoded 2026-05-31 deadline made this bet OVERDUE once real time passed it,
    # and the overdue-bet action then outranked review_relationship_health out of
    # the MAX_ACTIONS=3 cap — failing the ranked_actions assertion on every PR
    # after that date. The bet must stay active-but-not-overdue forever.
    deadline = date.today().replace(year=date.today().year + 1)
    (repo / "bets" / "2026-05-01-launch.md").write_text(
        (
            "---\n"
            "status: open\n"
            "opened: 2026-05-01\n"
            f"deadline: {deadline.isoformat()}\n"
            "appetite: 2 weeks\n"
            "hypothesis: A launch push will create calls.\n"
            "metric: calls\n"
            "target: 5 calls\n"
            "result: ''\n"
            "linked_decisions: []\n"
            "linked_research: []\n"
            "linked_pushes: []\n"
            "linked_campaigns: []\n"
            "linked_outcomes: []\n"
            "public: true\n"
            "channels: []\n"
            "tags: []\n"
            "---\n\n"
            "# Launch bet\n"
        ),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["status", str(repo), "--json", "--peek"])

    assert result.exit_code == 0
    report = json.loads(result.stdout)
    health = report["relationship_health"]
    assert health["ok"] is False
    assert health["summary"]["active_bets_without_push"] == 1
    assert health["summary"]["offers_without_current_push_or_playbook"] == 1
    assert health["sections"]["bets"]["active_without_push"][0]["path"] == (
        "bets/2026-05-01-launch.md"
    )
    assert any(item["id"] == "relationship_health_gaps" for item in report["drift"]["items"])
    assert any(action["id"] == "review_relationship_health" for action in report["ranked_actions"])

    human = runner.invoke(app, ["status", str(repo), "--no-color", "--peek"])

    assert human.exit_code == 0
    assert "Relationship health" in human.stdout
    assert "active bet(s) need a linked push" in human.stdout


def test_relationship_health_notes_unlinked_decisions_and_older_research(tmp_path: Path) -> None:
    repo = tmp_path / "business"
    for folder in ("bets", "decisions", "research"):
        (repo / folder).mkdir(parents=True)

    def write(path: str, frontmatter: str) -> None:
        (repo / path).write_text(f"---\n{frontmatter}---\n# Record\n", encoding="utf-8")

    write("decisions/accepted.md", "status: accepted\n")
    write("decisions/codified.md", "status: codified\n")
    write("decisions/reverse-linked.md", "status: accepted\n")
    write(
        "decisions/research-linked.md",
        "status: accepted\nlinked_research:\n  - research/linked.md\n",
    )
    write("decisions/proposed.md", "status: proposed\n")
    write("decisions/superseded.md", "status: superseded\n")
    write("bets/bet.md", "linked_decisions:\n  - decisions/reverse-linked.md\n")
    for number in range(6):
        write(f"research/old-{number}.md", "date: 2026-09-05\n")
    write("research/recent.md", "date: 2026-10-05\n")
    write("research/undated.md", "status: complete\n")
    write("research/linked.md", "date: 2026-09-05\n")

    health = status_mod._relationship_health(
        repo, brain={"pushes": {"records": []}}, today=date(2026, 10, 15)
    )
    gaps = {item["id"]: item for item in health["gaps"]}
    decisions = gaps["accepted_decisions_without_links"]
    research = gaps["research_without_links"]
    assert decisions["severity"] == research["severity"] == "info"
    assert decisions["count"] == health["summary"]["accepted_decisions_without_links"] == 2
    assert set(decisions["evidence"]) == {"decisions/accepted.md", "decisions/codified.md"}
    assert research["count"] == health["summary"]["research_without_links"] == 6
    assert len(research["records"]) == len(research["evidence"]) == 5
    assert health["sections"]["research"]["without_links_total"] == 6
    assert health["summary"]["warnings"] == 0
    assert health["summary"]["info"] == 2


def test_status_relationship_health_accepts_push_side_bet_links(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    (repo / "bets" / "2026-05-01-launch.md").write_text(
        (
            "---\n"
            "status: open\n"
            "opened: 2026-05-01\n"
            "deadline: 2026-05-31\n"
            "appetite: 2 weeks\n"
            "hypothesis: A launch push will create calls.\n"
            "metric: calls\n"
            "target: 5 calls\n"
            "result: ''\n"
            "linked_decisions: []\n"
            "linked_research: []\n"
            "linked_pushes: []\n"
            "linked_campaigns: []\n"
            "linked_outcomes: []\n"
            "public: true\n"
            "channels: []\n"
            "tags: []\n"
            "---\n\n"
            "# Launch bet\n"
        ),
        encoding="utf-8",
    )
    push = _write_push(repo, "2026-05-06-launch")
    push_record = push / "push.md"
    push_record.write_text(
        push_record.read_text(encoding="utf-8").replace(
            "---\n\n# Launch push\n",
            "linked_bets:\n  - bets/2026-05-01-launch.md\n---\n\n# Launch push\n",
        ),
        encoding="utf-8",
    )

    report = status_mod.run(path=str(repo), update_marker=False)

    assert report["relationship_health"]["summary"]["active_bets_without_push"] == 0


def test_status_flags_only_live_pushes_without_a_bet(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "business"
    init_run(path=str(repo), name="Test Business")
    bet_path = "bets/2026-05-01-launch.md"
    bet_linked_push = "pushes/2026-05-06-bet-linked/push.md"
    (repo / bet_path).write_text(
        f"---\nstatus: open\nlinked_pushes:\n  - {bet_linked_push}\n---\n# Launch bet\n",
        encoding="utf-8",
    )
    for slug, status, extra in (
        ("unlinked", "planned", ""),
        ("push-linked", "active", f"linked_bets:\n  - {bet_path}\n"),
        ("bet-linked", "paused", ""),
        ("completed", "completed", ""),
        ("one-off", "active", "linked_bets: []\nno_bet_reason: One-time notice\n"),
        ("empty-reason", "active", "linked_bets: []\nno_bet_reason: '  '\n"),
    ):
        push = _write_push(repo, f"2026-05-06-{slug}", status=status) / "push.md"
        push.write_text(
            push.read_text(encoding="utf-8").replace(
                "---\n\n# Launch push", extra + "---\n\n# Launch push"
            ),
            encoding="utf-8",
        )

    result = runner.invoke(app, ["status", str(repo), "--json", "--peek"])
    assert result.exit_code == 0
    health = json.loads(result.stdout)["relationship_health"]
    assert health["summary"]["active_pushes_without_bet"] == 2
    assert health["summary"]["active_bets_without_push"] == 0
    assert {item["path"] for item in health["sections"]["pushes"]["active_without_bet"]} == {
        "pushes/2026-05-06-unlinked/push.md",
        "pushes/2026-05-06-empty-reason/push.md",
    }
    assert any(
        gap["id"] == "active_pushes_without_bet" and gap["count"] == 2 for gap in health["gaps"]
    )
    assert "active_pushes_without_offer" in health["summary"]

    human = runner.invoke(app, ["status", str(repo), "--no-color", "--peek"])
    assert human.exit_code == 0
    assert "2 live push(es) do not say which bet they serve" in human.stdout


def test_status_dates_undated_push_from_slug(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "business"
    init_run(path=str(repo), name="Test Business")
    for slug, frontmatter_slug, started in (
        ("old", "2026-04-01-old", ""),
        ("recent", "2026-05-01-recent", ""),
        ("explicit", "2026-04-01-explicit", "started: 2026-05-01\n"),
        ("undated", "undated", ""),
    ):
        push = _write_push(repo, f"2026-05-06-{slug}") / "push.md"
        content = push.read_text(encoding="utf-8")
        content = content.replace(f"slug: {slug}\n", f"slug: {frontmatter_slug}\n")
        content = content.replace("started: 2026-05-06\n", started)
        content = content.replace("review_on: 2026-05-20\n", "")
        push.write_text(content, encoding="utf-8")

    report = status_mod.run(
        path=str(repo),
        now=datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc),
        update_marker=False,
    )
    stale = report["relationship_health"]["sections"]["pushes"]["stale_without_outcome"]
    assert [(item["path"], item["age_days"]) for item in stale] == [
        ("pushes/2026-05-06-old/push.md", 37)
    ]


def test_push_stale_date_fallback_rejects_invalid_or_missing_slug() -> None:
    today = date(2026, 5, 8)
    assert status_mod._is_push_stale({"slug": "2026-04-01-old"}, today) == (True, 37)
    assert status_mod._is_push_stale({"slug": "2026-05-01-recent"}, today) == (False, 7)
    assert status_mod._is_push_stale(
        {"slug": "2026-04-01-old", "started": "2026-05-01"}, today
    ) == (False, 7)
    assert status_mod._is_push_stale({"slug": "2026-04-99-invalid"}, today) == (False, 0)
    assert status_mod._is_push_stale({"slug": "undated"}, today) == (False, 0)


def test_status_surfaces_validation_category_counts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    for slug in ("one", "two"):
        offer = repo / "core" / "offers" / slug / "offer.md"
        offer.parent.mkdir(parents=True)
        offer.write_text("---\nstatus: running\n---\n# Offer\n", encoding="utf-8")

    report = status_mod.run(path=str(repo), update_marker=False)

    assert report["validation"]["validation_categories"]["top_category"] == "missing_slug"
    assert (
        report["validation"]["validation_categories"]["by_category"]["missing_slug"]["count"] == 2
    )
    validation_drift = next(
        item for item in report["drift"]["items"] if item["id"] == "validation_debt"
    )
    assert "top category: missing_slug" in validation_drift["summary"]
    assert any(action["id"] == "repair_validation_debt" for action in report["ranked_actions"])


def test_status_peek_skips_validation_cross_refs(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    calls: list[bool] = []

    def fake_validate(
        path: str,
        verbose: bool = False,
        cross_refs: bool = False,
        strict: bool = False,
        migration_drift_report: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        calls.append(cross_refs)
        return {
            "ok": True,
            "summary": {"errors": 0, "warnings": 0},
            "cross_refs": {
                "enabled": cross_refs,
                "warnings": [],
                "orphan_offers": [],
            },
            "files": [],
            "legacy_repair": None,
            "migration_drift": {"summary": {}},
            "validation_categories": {
                "schema_version": "1.0",
                "total_categories": 0,
                "top_category": "",
                "top_repair": "",
                "by_category": {},
                "safe_to_share": True,
            },
        }

    monkeypatch.setattr(validate_mod, "run", fake_validate)

    result = runner.invoke(app, ["status", str(repo), "--json", "--peek"])

    assert result.exit_code == 0, result.stdout
    assert calls == [False]


def test_status_validation_exception_scrubs_local_paths(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    private_path = tmp_path / "private" / "proof.md"

    def fail_validate(
        path: str,
        verbose: bool = False,
        cross_refs: bool = False,
        strict: bool = False,
        migration_drift_report: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        raise RuntimeError(f"failed while reading {private_path}")

    monkeypatch.setattr(validate_mod, "run", fail_validate)

    report = status_mod.run(path=str(repo), update_marker=False)

    validation = report["validation"]
    message = validation["validation_categories"]["by_category"]["validation_unavailable"][
        "examples"
    ][0]["message"]
    assert str(private_path) not in message
    assert "<local-path>" in message
    assert validation["safe_to_share"] is True


def test_status_relationship_health_flags_completed_and_stale_pushes(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    offer = repo / "core" / "offers" / "coaching"
    offer.mkdir(parents=True)
    (offer / "offer.md").write_text(
        "---\nslug: coaching\nstatus: running\n---\n\n# Coaching\n",
        encoding="utf-8",
    )
    completed = repo / "pushes" / "2026-05-01-completed"
    completed.mkdir(parents=True)
    (completed / "push.md").write_text(
        (
            "---\n"
            "type: push\n"
            "slug: completed\n"
            "kind: launch\n"
            "status: completed\n"
            "health: on-track\n"
            "goal: booked calls\n"
            "owner: Devon\n"
            "audience: founders\n"
            "offer: core/offers/coaching/offer.md\n"
            "started: 2026-05-01\n"
            "review_on: 2026-05-07\n"
            "---\n\n"
            "# Completed push\n"
        ),
        encoding="utf-8",
    )
    stale = repo / "pushes" / "2026-04-01-stale"
    stale.mkdir(parents=True)
    (stale / "push.md").write_text(
        (
            "---\n"
            "type: push\n"
            "slug: stale\n"
            "kind: launch\n"
            "status: active\n"
            "health: at-risk\n"
            "goal: booked calls\n"
            "owner: Devon\n"
            "audience: founders\n"
            "offer: core/offers/coaching/offer.md\n"
            "started: 2026-04-01\n"
            "review_on: 2026-04-15\n"
            "---\n\n"
            "# Stale push\n"
        ),
        encoding="utf-8",
    )

    report = status_mod.run(
        path=str(repo),
        now=datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc),
        update_marker=False,
    )

    summary = report["relationship_health"]["summary"]
    assert summary["completed_pushes_without_outcome"] == 1
    assert summary["stale_pushes_without_outcome"] == 1
    assert summary["offers_without_current_push_or_playbook"] == 0
    assert (
        report["relationship_health"]["sections"]["pushes"]["stale_without_outcome"][0]["path"]
        == "pushes/2026-04-01-stale/push.md"
    )


def test_status_relationship_health_accepts_offer_side_push_links(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    offer = repo / "core" / "offers" / "coaching"
    offer.mkdir(parents=True)
    (offer / "offer.md").write_text(
        (
            "---\n"
            "slug: coaching\n"
            "status: running\n"
            "linked_pushes:\n"
            "  - pushes/2026-05-01-launch/push.md\n"
            "---\n\n"
            "# Coaching\n"
        ),
        encoding="utf-8",
    )
    push = repo / "pushes" / "2026-05-01-launch"
    push.mkdir(parents=True)
    (push / "push.md").write_text(
        (
            "---\n"
            "type: push\n"
            "slug: launch\n"
            "kind: launch\n"
            "status: active\n"
            "health: on-track\n"
            "goal: booked calls\n"
            "owner: Devon\n"
            "audience: founders\n"
            "offer: ''\n"
            "started: 2026-05-01\n"
            "review_on: 2026-05-20\n"
            "---\n\n"
            "# Launch\n"
        ),
        encoding="utf-8",
    )

    report = status_mod.run(
        path=str(repo),
        now=datetime(2026, 5, 8, 12, 0, tzinfo=timezone.utc),
        update_marker=False,
    )

    assert report["relationship_health"]["summary"]["offers_without_current_push_or_playbook"] == 0


def test_status_relationship_health_ignores_non_live_offer_stubs(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    (repo / "core" / "offer.md").write_text(
        "---\ntype: offer\nstatus: stub\n---\n\n# Offer stub\n",
        encoding="utf-8",
    )

    report = status_mod.run(path=str(repo), update_marker=False)

    assert report["relationship_health"]["summary"]["offers_without_current_push_or_playbook"] == 0


def test_status_relationship_health_flags_closed_bet_without_outcome(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    (repo / "bets" / "2026-05-01-closed.md").write_text(
        (
            "---\n"
            "status: closed\n"
            "opened: 2026-05-01\n"
            "deadline: 2026-05-07\n"
            "appetite: 1 week\n"
            "hypothesis: A follow-up push will create calls.\n"
            "metric: calls\n"
            "target: 5 calls\n"
            "result: win\n"
            "linked_decisions: []\n"
            "linked_research: []\n"
            "linked_pushes: []\n"
            "linked_campaigns: []\n"
            "linked_outcomes: []\n"
            "public: false\n"
            "channels: []\n"
            "tags: []\n"
            "---\n\n"
            "# Closed bet\n"
        ),
        encoding="utf-8",
    )

    report = status_mod.run(path=str(repo), update_marker=False)

    assert report["relationship_health"]["summary"]["closed_bets_without_outcome"] == 1
    assert (
        report["relationship_health"]["sections"]["bets"]["closed_without_outcome"][0]["path"]
        == "bets/2026-05-01-closed.md"
    )


def test_status_relationship_health_uses_lightweight_scan_on_large_repos(
    tmp_path: Path, monkeypatch
) -> None:
    def fail_if_graph_builds(_path: str) -> None:
        raise AssertionError("status built the full graph")

    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    monkeypatch.setattr(graph_mod, "build_index", fail_if_graph_builds)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    documents = repo / "documents"
    documents.mkdir(exist_ok=True)
    large_body = "# Notes\n\n" + ("Relationship-free working note.\n" * 100)
    for index in range(300):
        (documents / f"2026-05-01-note-{index:03d}.md").write_text(
            large_body,
            encoding="utf-8",
        )
    (repo / "bets" / "2026-05-01-launch.md").write_text(
        (
            "---\n"
            "status: open\n"
            "opened: 2026-05-01\n"
            "deadline: 2026-05-31\n"
            "appetite: 2 weeks\n"
            "hypothesis: A launch push will create calls.\n"
            "metric: calls\n"
            "target: 5 calls\n"
            "linked_pushes:\n"
            "  - pushes/missing-launch/push.md\n"
            "---\n\n"
            "# Launch bet\n"
        ),
        encoding="utf-8",
    )

    report = status_mod.run(path=str(repo), update_marker=False)

    health = report["relationship_health"]
    assert report["brain"]["counts"]["documents"] == 300
    assert health["summary"]["active_bets_without_push"] == 1
    assert health["summary"]["missing_relationship_targets"] == 1
    assert health["sections"]["outcomes"]["missing_targets"][0] == {
        "source": "bets/2026-05-01-launch.md",
        "relationship": "push",
        "field": "linked_pushes",
        "target": "pushes/missing-launch/push.md",
    }


def test_status_human_output_mentions_core_sections(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")

    result = runner.invoke(app, ["status", str(repo)])

    assert result.exit_code == 0
    assert "mb status" in result.stdout
    assert "Repo" in result.stdout
    assert "Since last check" in result.stdout
    assert "Drift" in result.stdout
    assert "Runtime" in result.stdout
    assert "GitHub" in result.stdout
    assert "Next" in result.stdout
    assert "why:" in result.stdout
    assert "next:" in result.stdout


def test_status_human_labels_missing_codex_without_experimental_copy(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    monkeypatch.setattr(codex_mod, "_which", _without_codex)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")

    result = runner.invoke(app, ["status", str(repo), "--no-color", "--peek"])

    assert result.exit_code == 0
    assert "Codex: missing global skills" in result.stdout
    assert "experimental" not in result.stdout


def test_status_since_last_check_uses_repo_marker(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")

    first = runner.invoke(app, ["status", str(repo), "--json"])
    assert first.exit_code == 0
    first_payload = json.loads(first.stdout)
    assert first_payload["since_last_check"]["first_run"] is True

    (repo / "research" / "2026-05-02-market.md").write_text("# Market\n", encoding="utf-8")
    second = runner.invoke(app, ["status", str(repo), "--json"])

    assert second.exit_code == 0
    second_payload = json.loads(second.stdout)
    assert second_payload["since_last_check"]["first_run"] is False
    assert second_payload["since_last_check"]["previous_seen_at"] == first_payload["generated_at"]
    assert {
        "folder": "research",
        "before": 0,
        "after": 1,
        "delta": 1,
    } in second_payload["since_last_check"]["brain_count_changes"]


def test_status_since_last_check_includes_grouped_journal(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    _configure_git_user(repo)
    assert _git(repo, "add", ".").returncode == 0
    result = _git(repo, "commit", "--no-verify", "-m", "[added] business scaffold")
    assert result.returncode == 0, result.stderr

    first = runner.invoke(app, ["status", str(repo), "--json"])
    assert first.exit_code == 0

    _commit(
        repo,
        "pushes/workshop/push.md",
        "# Workshop\n",
        "[shipped] workshop lander",
        "Refs:\n- pushes/workshop/push.md\n- https://github.com/noontide-co/mainbranch/issues/303",
    )
    second = runner.invoke(app, ["status", str(repo), "--json", "--peek"])

    assert second.exit_code == 0
    payload = json.loads(second.stdout)
    journal = payload["since_last_check"]["journal"]
    assert payload["since_last_check"]["summary"]["journal_events"] == 1
    assert journal["schema_version"] == "0.current"
    assert journal["events"][0]["verb"] == "shipped"
    assert journal["events"][0]["loop"] == "ship"
    assert journal["events"][0]["refs"][0]["kind"] == "push"
    assert journal["events"][0]["refs"][1]["kind"] == "github_issue"
    assert journal["groups"][0]["label"] == "Shipped work"


def test_status_human_output_summarizes_since_last_journal(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    _configure_git_user(repo)
    assert _git(repo, "add", ".").returncode == 0
    result = _git(repo, "commit", "--no-verify", "-m", "[added] business scaffold")
    assert result.returncode == 0, result.stderr
    first = runner.invoke(app, ["status", str(repo), "--json"])
    assert first.exit_code == 0
    _commit(repo, "bets/workshop.md", "# Bet\n", "[opened] bet workshop")

    human = runner.invoke(app, ["status", str(repo), "--verbose", "--no-color", "--peek"])

    assert human.exit_code == 0
    assert "journal:" in human.stdout
    assert "Made decisions: 1 event(s)" in human.stdout
    assert "Opened bet workshop" in human.stdout


def test_status_peek_does_not_update_seen_marker(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")

    first = runner.invoke(app, ["status", str(repo), "--json"])
    marker_before = (repo / ".mb" / "last-status-seen.json").read_text(encoding="utf-8")
    peek = runner.invoke(app, ["status", str(repo), "--json", "--peek"])
    marker_after = (repo / ".mb" / "last-status-seen.json").read_text(encoding="utf-8")

    assert first.exit_code == 0
    assert peek.exit_code == 0
    payload = json.loads(peek.stdout)
    assert payload["marker_update"]["reason"] == "disabled"
    assert marker_after == marker_before


def test_marker_gitignore_state_honors_broader_gitignore_patterns(
    tmp_path: Path, monkeypatch
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    runner.invoke(app, ["init", str(repo), "--name", "Acme"])
    (repo / ".gitignore").write_text(".mb/\n", encoding="utf-8")

    state = status_mod._marker_gitignore_state(repo)

    assert state["ok"] is True
    assert state["repair"] == ""


def test_status_no_color_and_verbose_output(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    (repo / "decisions" / "2026-05-01-pricing.md").write_text(
        "---\ndate: 2026-05-01\nstatus: accepted\n---\n\n# Pricing\n",
        encoding="utf-8",
    )

    terse = runner.invoke(app, ["status", str(repo), "--no-color"])
    verbose = runner.invoke(app, ["status", str(repo), "--verbose", "--no-color"])

    assert terse.exit_code == 0
    assert "\x1b[" not in terse.stdout
    assert "Recent decisions" not in terse.stdout
    assert verbose.exit_code == 0
    assert "Recent decisions" in verbose.stdout


def test_status_required_update_json_and_human_copy(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    monkeypatch.setattr(
        status_mod,
        "package_update_status",
        lambda repo: {
            "installed": "0.1.0",
            "latest": "0.2.1",
            "minimum_supported": "0.2.0",
            "severity": "required",
            "command": "pipx upgrade mainbranch",
            "post_update_commands": ["mb skill link --repo .", "mb doctor"],
            "reason": (
                "Installed version predates mb update and the current skill-link repair flow."
            ),
        },
    )
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")

    json_result = runner.invoke(app, ["status", str(repo), "--json"])

    assert json_result.exit_code == 0
    payload = json.loads(json_result.stdout)
    assert payload["update"]["severity"] == "required"
    assert payload["update"]["command"] == "pipx upgrade mainbranch"
    assert any(
        "pipx upgrade mainbranch" in action for action in payload["readiness"]["next_actions"]
    )
    assert payload["ranked_actions"][0]["id"] == "mainbranch_update_required"

    human_result = runner.invoke(app, ["status", str(repo), "--verbose"])

    assert human_result.exit_code == 0
    assert "Update required." in human_result.stdout
    assert "pipx upgrade mainbranch" in human_result.stdout
    assert "mb skill link --repo ." in human_result.stdout


def test_status_names_integration_repairs(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "local-file")
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "home"))
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    connect_mod.connect_provider("cloudflare", repo=repo)

    json_result = runner.invoke(app, ["status", str(repo), "--json"])

    assert json_result.exit_code == 0
    payload = json.loads(json_result.stdout)
    assert payload["integrations"]["providers"][0]["state"] == "missing_secret"
    assert any(item["id"] == "unhealthy_integrations" for item in payload["drift"]["items"])
    assert any(
        "mb connect cloudflare --token-stdin" in action
        for action in payload["readiness"]["next_actions"]
    )
    assert any(
        action["id"] == "repair_unhealthy_integrations" for action in payload["ranked_actions"]
    )

    human_result = runner.invoke(app, ["status", str(repo), "--verbose"])

    assert human_result.exit_code == 0
    assert "cloudflare: missing_secret" in human_result.stdout
    assert "mb connect cloudflare --token-stdin" in human_result.stdout


def test_status_drift_aligns_unhealthy_integrations_with_readiness(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    provider = {
        "provider": "cloudflare",
        "ok": False,
        "connected": True,
        "state": "unvalidated",
        "repair_command": "mb connect test cloudflare",
    }
    report = status_mod.run(path=str(repo), update_marker=False)
    report["integrations"]["providers"] = [provider]
    report["integrations"]["summary"] = {
        "configured": 1,
        "healthy": 0,
        "needs_repair": 1,
        "unvalidated": 1,
    }

    drift = status_mod._drift(report)
    readiness = status_mod._readiness(report)

    assert any(item["id"] == "unhealthy_integrations" for item in drift["items"])
    assert any("mb connect test cloudflare" in action for action in readiness["next_actions"])


def test_status_reports_stored_unverified_integration_without_calling_it_ready(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    provider = {
        "provider": "resend",
        "name": "Resend",
        "ok": False,
        "connected": True,
        "state": connect_mod.UNVERIFIED_STATE,
        "stored": True,
        "provider_verified": False,
        "verified_at": "",
        "repair": "Confirm the Resend credential in the provider's own dashboard.",
        "repair_command": "",
    }
    report = status_mod.run(path=str(repo), update_marker=False)
    report["integrations"]["providers"] = [provider]
    report["integrations"]["summary"] = {
        "configured": 1,
        "healthy": 0,
        "needs_repair": 0,
        "unvalidated": 0,
        "unverified": 1,
    }

    drift = status_mod._drift(report)
    readiness = status_mod._readiness(report)

    # Its own signal, not a repair item: there is no command that fixes it.
    assert any(item["id"] == "unverified_integrations" for item in drift["items"])
    assert not any(item["id"] == "unhealthy_integrations" for item in drift["items"])
    assert not any("Repair resend integration" in action for action in readiness["next_actions"])


def test_status_detects_non_business_repo(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    report = status_mod.run(path=str(tmp_path))

    assert report["repo"]["looks_like_mainbranch_repo"] is False
    assert report["readiness"]["level"] == "not_ready"
    assert any("mb init" in action for action in report["readiness"]["next_actions"])


def test_status_brain_includes_active_bets(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "decisions").mkdir(parents=True)
    old_date = date.today().replace(year=date.today().year - 1)
    (repo / "decisions" / f"{old_date.isoformat()}-old.md").write_text(
        f"---\ndate: {old_date.isoformat()}\nstatus: proposed\n---\n\n# Old proposal\n",
        encoding="utf-8",
    )
    (repo / "research").mkdir()
    (repo / "research" / "2026-05-01-market.md").write_text("# Market\n", encoding="utf-8")
    deadline = date.today().replace(year=date.today().year + 1)
    (repo / "bets").mkdir()
    (repo / "bets" / "2026-05-01-launch.md").write_text(
        (
            "---\n"
            "status: open\n"
            "opened: 2026-05-01\n"
            f"deadline: {deadline.isoformat()}\n"
            "appetite: 2 weeks\n"
            "hypothesis: Launching a demo will create calls.\n"
            "metric: calls\n"
            "target: 5 calls\n"
            "result: ''\n"
            "linked_decisions: []\n"
            "linked_research: []\n"
            "linked_campaigns: []\n"
            "linked_outcomes: []\n"
            "public: true\n"
            "channels:\n"
            "  - site\n"
            "tags: []\n"
            "---\n\n"
            "# Launch bet\n"
        ),
        encoding="utf-8",
    )

    brain = status_mod._brain(repo)

    assert brain["recent_decisions"][0]["title"] == "Old proposal"
    assert brain["stale_decisions"][0]["age_days"] > status_mod.STALE_DECISION_DAYS
    assert brain["recent_research"][0]["title"] == "Market"
    assert brain["bets"]["active"][0]["title"] == "Launch bet"
    assert brain["bets"]["active"][0]["deadline"] == deadline.isoformat()


def test_status_brain_reports_bet_stage_and_commitment(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "bets").mkdir(parents=True)
    base = (
        "status: open\n"
        "opened: 2026-05-16\n"
        "deadline: 2026-05-30\n"
        "appetite: 2 weeks\n"
        "hypothesis: h\n"
        "metric: m\n"
        "target: t\n"
        "result: ''\n"
    )
    (repo / "bets" / "2026-05-16-daily.md").write_text(
        "---\n"
        + base
        + "stage: working\n"
        + "commitment:\n"
        + "  action: Send one outreach message\n"
        + "  cadence: weekdays\n"
        + "  evidence: send_id\n"
        + "---\n\n# Daily bet\n",
        encoding="utf-8",
    )
    (repo / "bets" / "2026-05-17-plain.md").write_text(
        "---\n" + base + "---\n\n# Plain bet\n", encoding="utf-8"
    )

    bets = {b["path"]: b for b in status_mod._brain(repo)["bets"]["recent"]}

    daily = bets["bets/2026-05-16-daily.md"]
    assert daily["stage"] == "working"
    assert daily["commitment"] == {
        "action": "Send one outreach message",
        "cadence": "weekdays",
        "owner": "",
        "evidence": "send_id",
    }
    plain = bets["bets/2026-05-17-plain.md"]
    assert plain["stage"] == ""
    assert plain["commitment"] is None


def test_status_brain_evaluates_declared_bet_exit_signals(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "bets").mkdir(parents=True)
    (repo / "bets" / "2026-05-16-offer-test.md").write_text(
        (
            "---\n"
            "status: open\n"
            "opened: 2026-05-16\n"
            "deadline: 2026-05-30\n"
            "appetite: 2 weeks\n"
            "appetite_tier: small\n"
            "hypothesis: Offer sharpening creates qualified calls.\n"
            "metric: qualified_calls\n"
            "target: 3 qualified calls\n"
            "result: ''\n"
            "metrics:\n"
            "  qualified_calls: 2\n"
            "  cost_per_qualified_call: 120\n"
            "money_path:\n"
            "  required: true\n"
            "  bet_id: 2026-05-16-offer-test\n"
            "  exposure_cap:\n"
            "    amount: 500\n"
            "    currency: USD\n"
            "  anchor_required_before: execution\n"
            "kill_rubric:\n"
            "  failure_signals:\n"
            "    - id: no-qualified-calls\n"
            "      metric: qualified_calls\n"
            "      comparator: <\n"
            "      threshold: 3\n"
            "      by: 2026-05-01\n"
            "      action: kill\n"
            "  double_down_signals:\n"
            "    - id: profitable-signal\n"
            "      metric: cost_per_qualified_call\n"
            "      comparator: <=\n"
            "      threshold: 150\n"
            "      action: double_down\n"
            "linked_decisions: []\n"
            "linked_research: []\n"
            "linked_pushes: []\n"
            "linked_outcomes: []\n"
            "public: false\n"
            "channels: []\n"
            "tags: []\n"
            "---\n\n"
            "# Offer test\n"
        ),
        encoding="utf-8",
    )

    brain = status_mod._brain(repo)

    bet = brain["bets"]["active"][0]
    assert bet["appetite_tier"] == "small"
    assert bet["money_path"]["required"] is True
    assert bet["exit_criteria"]["declared"] is True
    assert bet["exit_criteria"]["triggered_failure_signals"][0]["id"] == "no-qualified-calls"
    assert bet["exit_criteria"]["triggered_double_down_signals"][0]["id"] == "profitable-signal"
    assert brain["bets"]["exit_criteria"]["triggered_failure_signals"][0]["path"] == (
        "bets/2026-05-16-offer-test.md"
    )


def test_status_brain_flags_active_bets_without_predeclared_exit_criteria(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    (repo / "bets").mkdir(parents=True)
    (repo / "bets" / "2026-05-16-open.md").write_text(
        (
            "---\n"
            "status: open\n"
            "opened: 2026-05-16\n"
            "deadline: 2026-05-30\n"
            "appetite: 2 weeks\n"
            "hypothesis: A test creates calls.\n"
            "metric: calls\n"
            "target: 3 calls\n"
            "result: ''\n"
            "linked_decisions: []\n"
            "linked_research: []\n"
            "linked_pushes: []\n"
            "linked_outcomes: []\n"
            "public: false\n"
            "channels: []\n"
            "tags: []\n"
            "---\n\n"
            "# Open bet\n"
        ),
        encoding="utf-8",
    )

    brain = status_mod._brain(repo)

    assert brain["bets"]["active"][0]["exit_criteria"]["missing"] is True
    assert brain["bets"]["exit_criteria"]["missing"][0]["path"] == "bets/2026-05-16-open.md"


def test_status_ranks_active_bets_missing_exit_criteria(tmp_path: Path, monkeypatch) -> None:
    """Active bets without a kill/double-down rubric should surface as a ranked
    action that routes to /mb-bet, not stay buried in raw brain.bets facts."""
    monkeypatch.setattr(status_mod, "_which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        status_mod,
        "_git_info",
        lambda repo: {
            "available": True,
            "inside_work_tree": True,
            "branch": "main",
            "commit": "abc123",
            "dirty": False,
            "dirty_count": 0,
            "dirty_files": [],
            "remote": "https://github.com/example/acme.git",
            "error": "",
        },
    )
    monkeypatch.setattr(
        status_mod,
        "_git_recent_activity",
        lambda repo, git: {"available": True, "items": [], "error": ""},
    )
    monkeypatch.setattr(
        status_mod,
        "_github",
        lambda repo, git, **kwargs: {
            "available": True,
            "authenticated": True,
            "degraded": False,
            "source": "gh",
            "repo": "example/acme",
            "summary": {
                "assigned_tasks": 0,
                "attention_requests": 0,
                "open_proposals": 0,
                "shipped_this_week": 0,
                "recently_closed_tasks": 0,
                "blocked_or_stale_tasks": 0,
            },
            "sections": {
                "assigned_tasks": [],
                "attention_requests": [],
                "open_proposals": [],
                "shipped_this_week": [],
                "recently_closed_tasks": [],
                "blocked_or_stale_tasks": [],
            },
            "errors": [],
            "assigned_issues": [],
            "review_requests": [],
            "recent_merged_prs": [],
            "context": {"ok": True, "state": "ready"},
        },
    )
    monkeypatch.setattr(
        status_mod.onboard_mod,  # type: ignore[attr-defined]
        "onboarding_status",
        lambda repo: {"summary": {"status": "ready"}, "checklist": []},
    )
    repo = tmp_path / "repo"
    init_run(path=str(repo), name="Acme")
    # Future deadline so only the missing-exit-criteria signal fires (not due/overdue).
    (repo / "bets" / "2026-05-16-open.md").write_text(
        (
            "---\n"
            "status: open\n"
            "opened: 2026-05-16\n"
            "deadline: 2026-12-01\n"
            "appetite: 2 weeks\n"
            "hypothesis: A test creates calls.\n"
            "metric: calls\n"
            "target: 3 calls\n"
            "result: ''\n"
            "public: false\n"
            "channels: []\n"
            "tags: []\n"
            "---\n\n"
            "# Open bet\n"
        ),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["status", str(repo), "--json", "--peek"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    actions = {action["id"]: action for action in payload["ranked_actions"]}
    assert "tighten_bet_exit_criteria" in actions
    action = actions["tighten_bet_exit_criteria"]
    assert action["command"] == "/mb-bet update"
    assert action["audience"] == "operator_decision"
    assert action["operator_summary"]
    # Private bet, so the action must not be marked safe to share publicly.
    assert action["safe_to_share"] is False


def test_status_frontmatter_reader_accepts_delimiter_whitespace(tmp_path: Path) -> None:
    path = tmp_path / "note.md"
    path.write_text("--- \nstatus: open\n--- \n# Note\n", encoding="utf-8")

    assert status_mod._read_frontmatter(path)["status"] == "open"


def test_status_readiness_mentions_due_bets(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "bets").mkdir(parents=True)
    today = date.today()
    (repo / "bets" / f"{today.isoformat()}-due.md").write_text(
        (
            "---\n"
            "status: open\n"
            f"opened: {today.isoformat()}\n"
            f"deadline: {today.isoformat()}\n"
            "appetite: 1 day\n"
            "hypothesis: Fast follow-up increases replies.\n"
            "metric: replies\n"
            "target: 3 replies\n"
            "result: ''\n"
            "linked_decisions: []\n"
            "linked_research: []\n"
            "linked_campaigns: []\n"
            "linked_outcomes: []\n"
            "public: false\n"
            "channels: []\n"
            "tags: []\n"
            "---\n\n"
            "# Due bet\n"
        ),
        encoding="utf-8",
    )
    report = {
        "repo": {"looks_like_mainbranch_repo": True},
        "git": {"inside_work_tree": True, "dirty": False},
        "install": {"ok": True},
        "update": {"severity": "current", "command": ""},
        "runtime": {
            "skill_wiring": {"ok": True, "repair": ""},
            "claude_code": {"found": True, "repair": ""},
        },
        "brain": status_mod._brain(repo),
        "onboarding": {"summary": {"status": "ready"}},
        "integrations": {"providers": []},
        "github": {"authenticated": True, "context": {"ok": True}},
    }

    readiness = status_mod._readiness(report)

    assert any("active bets" in action for action in readiness["next_actions"])


@pytest.mark.parametrize(
    ("mode", "repair"),
    [
        ("pipx", "Run `pipx upgrade mainbranch`."),
        ("uv", "Run `uv tool install --refresh-package mainbranch mainbranch@latest`."),
        ("wheel", "Run `pip install --upgrade mainbranch`."),
        ("unknown", MODE_NEUTRAL_UPDATE_TEXT),
    ],
)
def test_status_readiness_install_repair_names_the_install_mode(
    tmp_path: Path, mode: str, repair: str
) -> None:
    # The non-required install repair follows the detected mode, not always pipx (#1028).
    report = {
        "repo": {"looks_like_mainbranch_repo": True},
        "git": {"inside_work_tree": True, "dirty": False},
        "install": {"ok": False, "mode": mode},
        "update": {"severity": "current", "command": ""},
        "runtime": {
            "skill_wiring": {"ok": True, "repair": ""},
            "claude_code": {"found": True, "repair": ""},
        },
        "brain": status_mod._brain(tmp_path),
        "onboarding": {"summary": {"status": "ready"}},
        "integrations": {"providers": []},
        "github": {"authenticated": True, "context": {"ok": True}},
    }

    readiness = status_mod._readiness(report)

    assert repair in readiness["next_actions"]
    assert not any("pipx install mainbranch" in action for action in readiness["next_actions"])


def test_readiness_keeps_existing_offer_repair_and_ignores_only_new_gaps(tmp_path: Path) -> None:
    offer = {
        "id": "offers_without_current_push_or_playbook",
        "severity": "info",
        "repair": "Link the offer to an active push.",
    }
    missing = {
        "id": "missing_relationship_targets",
        "severity": "warn",
        "repair": "Fix the missing linked file.",
    }
    new_gaps = [
        {
            "id": "accepted_decisions_without_links",
            "severity": "info",
            "repair": "Link each decision to the bet or push it informs.",
        },
        {
            "id": "research_without_links",
            "severity": "info",
            "repair": "Link each research note to the bet or push it informs.",
        },
    ]
    report = {
        "repo": {"looks_like_mainbranch_repo": True},
        "git": {"inside_work_tree": True, "dirty": False},
        "install": {"ok": True},
        "update": {"severity": "current", "command": ""},
        "runtime": {
            "skill_wiring": {"ok": True, "repair": ""},
            "claude_code": {"found": True, "repair": ""},
        },
        "brain": status_mod._brain(tmp_path),
        "onboarding": {"summary": {"status": "ready"}},
        "integrations": {"providers": []},
        "github": {"authenticated": True, "context": {"ok": True}},
    }
    for gaps, expected in (
        ([offer], ["Link the offer to an active push."]),
        ([offer, missing], ["Link the offer to an active push."]),
        (new_gaps, ["Run `claude` in this repo, then `/mb-start`."]),
    ):
        report["relationship_health"] = {"gaps": gaps}
        assert status_mod._readiness(report)["next_actions"] == expected


def test_status_ranker_mentions_due_bets(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(status_mod, "_which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        status_mod,
        "_git_info",
        lambda repo: {
            "available": True,
            "inside_work_tree": True,
            "branch": "main",
            "commit": "abc123",
            "dirty": False,
            "dirty_count": 0,
            "dirty_files": [],
            "remote": "https://github.com/example/acme.git",
            "error": "",
        },
    )
    monkeypatch.setattr(
        status_mod,
        "_git_recent_activity",
        lambda repo, git: {"available": True, "items": [], "error": ""},
    )
    monkeypatch.setattr(
        status_mod,
        "_github",
        lambda repo, git, **kwargs: {
            "available": True,
            "authenticated": True,
            "degraded": False,
            "source": "gh",
            "repo": "example/acme",
            "summary": {
                "assigned_tasks": 0,
                "attention_requests": 0,
                "open_proposals": 0,
                "shipped_this_week": 0,
                "recently_closed_tasks": 0,
                "blocked_or_stale_tasks": 0,
            },
            "sections": {
                "assigned_tasks": [],
                "attention_requests": [],
                "open_proposals": [],
                "shipped_this_week": [],
                "recently_closed_tasks": [],
                "blocked_or_stale_tasks": [],
            },
            "errors": [],
            "assigned_issues": [],
            "review_requests": [],
            "recent_merged_prs": [],
            "context": {"ok": True, "state": "ready"},
        },
    )
    monkeypatch.setattr(
        status_mod.onboard_mod,  # type: ignore[attr-defined]
        "onboarding_status",
        lambda repo: {"summary": {"status": "ready"}, "checklist": []},
    )
    repo = tmp_path / "repo"
    init_run(path=str(repo), name="Acme")
    today = date.today()
    (repo / "bets" / f"{today.isoformat()}-due.md").write_text(
        (
            "---\n"
            "status: open\n"
            f"opened: {today.isoformat()}\n"
            f"deadline: {today.isoformat()}\n"
            "appetite: 1 day\n"
            "hypothesis: Fast follow-up increases replies.\n"
            "metric: replies\n"
            "target: 3 replies\n"
            "result: ''\n"
            "kill_rubric:\n"
            "  failure_signals:\n"
            "    - metric: replies\n"
            "      comparator: '<'\n"
            "      threshold: 1\n"
            "  double_down_signals:\n"
            "    - metric: replies\n"
            "      comparator: '>='\n"
            "      threshold: 5\n"
            "linked_decisions: []\n"
            "linked_research: []\n"
            "linked_campaigns: []\n"
            "linked_outcomes: []\n"
            "public: false\n"
            "channels: []\n"
            "tags: []\n"
            "---\n\n"
            "# Due bet\n"
        ),
        encoding="utf-8",
    )

    result = runner.invoke(app, ["status", str(repo), "--json", "--peek"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert any(action["id"] == "review_due_bets" for action in payload["ranked_actions"])


def test_status_empty_bet_deadline_does_not_fall_back_to_opened_filename(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "bets").mkdir(parents=True)
    (repo / "bets" / "2020-01-01-no-deadline.md").write_text(
        (
            "---\n"
            "status: open\n"
            "opened: 2020-01-01\n"
            "deadline: ''\n"
            "appetite: 1 week\n"
            "hypothesis: A no-deadline bet should stay active but not due.\n"
            "metric: replies\n"
            "target: 3 replies\n"
            "result: ''\n"
            "linked_decisions: []\n"
            "linked_research: []\n"
            "linked_campaigns: []\n"
            "linked_outcomes: []\n"
            "public: false\n"
            "channels: []\n"
            "tags: []\n"
            "---\n\n"
            "# No deadline\n"
        ),
        encoding="utf-8",
    )

    bets = status_mod._brain(repo)["bets"]

    assert bets["active"][0]["title"] == "No deadline"
    assert bets["active"][0]["deadline"] == ""
    assert bets["due_soon"] == []
    assert bets["overdue"] == []


def test_status_low_level_helpers_handle_edge_cases(tmp_path: Path, monkeypatch) -> None:
    assert status_mod._repo_full_name("git@github.com:noontide-co/mainbranch.git") == (
        "noontide-co/mainbranch"
    )
    assert status_mod._repo_full_name("https://github.com/noontide-co/mainbranch.git") == (
        "noontide-co/mainbranch"
    )
    assert status_mod._repo_full_name("https://github.com/noontide-co/some.io.git") == (
        "noontide-co/some.io"
    )
    assert status_mod._repo_full_name("") == ""

    missing = tmp_path / "missing.md"
    plain = tmp_path / "plain.md"
    plain.write_text("# Plain\n", encoding="utf-8")
    unclosed = tmp_path / "unclosed.md"
    unclosed.write_text("---\nstatus: proposed\n", encoding="utf-8")
    bad_yaml = tmp_path / "bad.md"
    bad_yaml.write_text("---\n:\n---\n", encoding="utf-8")

    assert status_mod._read_frontmatter(missing) == {}
    assert status_mod._read_frontmatter(plain) == {}
    assert status_mod._read_frontmatter(unclosed) == {}
    assert status_mod._read_frontmatter(bad_yaml) == {}

    assert status_mod._parse_date(datetime(2026, 5, 2, 8, 30), plain) == date(2026, 5, 2)
    assert status_mod._parse_date(date(2026, 5, 2), plain) == date(2026, 5, 2)
    assert status_mod._parse_date("not-a-date", tmp_path / "2026-05-01-note.md") == date(2026, 5, 1)
    assert status_mod._parse_date("not-a-date", tmp_path / "note.md") is None

    external = tmp_path / "external.md"
    external.write_text("no heading\n", encoding="utf-8")
    summary = status_mod._file_summary(tmp_path / "repo", external)
    assert summary["path"] == str(external)
    assert summary["title"] == "external"

    def raise_missing(*args: object, **kwargs: object) -> object:
        raise FileNotFoundError

    monkeypatch.setattr(subprocess, "run", raise_missing)
    assert status_mod._run_command(["missing-bin"])["returncode"] == 127

    def raise_timeout(*args: object, **kwargs: object) -> object:
        raise subprocess.TimeoutExpired(cmd="slow", timeout=1)

    monkeypatch.setattr(subprocess, "run", raise_timeout)
    assert status_mod._run_command(["slow"])["returncode"] == 124

    def raise_subprocess(*args: object, **kwargs: object) -> object:
        raise subprocess.SubprocessError("boom")

    monkeypatch.setattr(subprocess, "run", raise_subprocess)
    assert status_mod._run_command(["boom"])["stderr"] == "boom"


def test_status_git_activity_parser_and_failure(tmp_path: Path, monkeypatch) -> None:
    def fake_run_command(
        args: list[str], cwd: Path | None = None, timeout: float = 3.0
    ) -> dict[str, Any]:
        assert args[1] == "log"
        return {
            "ok": True,
            "stdout": (
                "abc123\t2026-05-02\tUpdate offer\n"
                "core/offer.md\n"
                "research/2026-05-01-market.md\n\n"
                "def456\t2026-05-01\tAdd decision\n"
                "decisions/2026-05-01-pricing.md\n"
            ),
            "stderr": "",
        }

    monkeypatch.setattr(status_mod, "_run_command", fake_run_command)
    activity = status_mod._git_recent_activity(tmp_path, {"inside_work_tree": True})

    assert activity["available"] is True
    assert activity["items"][0]["commit"] == "abc123"
    assert activity["items"][0]["files"] == [
        "core/offer.md",
        "research/2026-05-01-market.md",
    ]
    assert activity["items"][1]["subject"] == "Add decision"
    assert (
        status_mod._git_recent_activity(tmp_path, {"inside_work_tree": False, "error": "no git"})[
            "error"
        ]
        == "no git"
    )

    monkeypatch.setattr(
        status_mod,
        "_run_command",
        lambda args, cwd=None, timeout=3.0: {"ok": False, "stdout": "", "stderr": "bad log"},
    )
    assert (
        status_mod._git_recent_activity(tmp_path, {"inside_work_tree": True})["error"] == "bad log"
    )


def test_status_git_activity_includes_bet_and_playbook_only_commits(tmp_path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "Fixture"], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "fixture@example.test"],
        check=True,
    )
    for folder, name in (("bets", "Bet"), ("playbooks", "Playbook")):
        path = tmp_path / folder / "item.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {name}\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(tmp_path), "add", str(path)], check=True)
        subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", f"Add {name}"], check=True)

    activity = status_mod._git_recent_activity(tmp_path, {"inside_work_tree": True})
    assert activity["available"] is True
    assert [item["files"] for item in activity["items"]] == [
        ["playbooks/item.md"],
        ["bets/item.md"],
    ]


def test_status_brain_marks_stale_decisions(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "repo"
    decisions = repo / "decisions"
    decisions.mkdir(parents=True)
    old_date = date.today().replace(year=date.today().year - 1)
    (decisions / f"{old_date.isoformat()}-old.md").write_text(
        f"---\ndate: {old_date.isoformat()}\nstatus: proposed\n---\n\n# Old proposal\n",
        encoding="utf-8",
    )
    (repo / "research").mkdir()
    old_research_date = date.today().replace(year=date.today().year - 1)
    (repo / "research" / f"{old_research_date.isoformat()}-market.md").write_text(
        f"---\ndate: {old_research_date.isoformat()}\n---\n\n# Market\n",
        encoding="utf-8",
    )

    brain = status_mod._brain(repo)

    assert brain["recent_decisions"][0]["title"] == "Old proposal"
    assert brain["stale_decisions"][0]["age_days"] > status_mod.STALE_DECISION_DAYS
    assert brain["recent_research"][0]["title"] == "Market"
    assert brain["stale_research"][0]["age_days"] > status_mod.STALE_RESEARCH_DAYS


def test_status_github_authenticated_branches(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        connect_mod,
        "github_context",
        lambda repo, **kwargs: {
            "ok": True,
            "state": "ready",
            "summary": "GitHub ready",
            "repair": "",
            "repair_command": "",
            "safe_to_share": True,
        },
    )
    monkeypatch.setattr(status_mod, "_which", lambda name: "/usr/bin/gh" if name == "gh" else "")
    monkeypatch.setattr(
        status_mod,
        "_run_command",
        lambda args, cwd=None, timeout=3.0: {"ok": True, "stdout": "", "stderr": ""},
    )

    def fake_gh_json(args: list[str], repo: Path) -> tuple[bool, Any, str]:
        if args[1:3] == ["issue", "list"] and "--assignee" in args:
            return True, [{"number": 173, "title": "Status", "url": "u"}], ""
        if args[1:3] == ["pr", "list"] and "review-requested:@me" in args:
            return False, None, "search failed"
        if args[1:3] == ["issue", "list"]:
            return True, [], ""
        if args[1:3] == ["pr", "list"] and "--state" in args and "open" in args:
            return True, [], ""
        return (
            True,
            [
                {
                    "number": 190,
                    "title": "Older",
                    "body": "older",
                    "mergedAt": "2026-05-01T10:00:00Z",
                },
                {
                    "number": 192,
                    "title": "Briefing",
                    "body": "## Scope\n- Shipped status",
                    "mergedAt": "2026-05-02T10:00:00Z",
                },
            ],
            "",
        )

    monkeypatch.setattr(status_mod, "_gh_json", fake_gh_json)
    github = status_mod._github(
        tmp_path,
        {"remote": "https://github.com/noontide-co/mainbranch.git"},
    )

    assert github["authenticated"] is True
    assert github["repo"] == "noontide-co/mainbranch"
    assert github["assigned_issues"][0]["number"] == 173
    assert github["sections"]["assigned_tasks"][0]["type"] == "task"
    assert github["summary"]["assigned_tasks"] == 1
    assert github["recent_merged_prs"][0]["number"] == 192
    assert github["recent_merged_prs"][0]["what_shipped"] == "Shipped status"
    assert github["errors"] == ["review requests: search failed"]

    assert (
        status_mod._summarize_pr({"title": "Fallback title", "body": "# Heading"})["what_shipped"]
        == "Fallback title"
    )
    assert [
        pr["number"]
        for pr in status_mod._recent_merged_prs(
            [
                {"number": index, "title": str(index), "mergedAt": f"2026-05-{index:02d}T00:00:00Z"}
                for index in range(1, 8)
            ]
        )
    ] == [7, 6, 5, 4, 3]

    monkeypatch.setattr(
        status_mod,
        "_run_command",
        lambda args, cwd=None, timeout=3.0: {"ok": False, "stdout": "", "stderr": "no auth"},
    )
    assert status_mod._github(tmp_path, {"remote": ""})["authenticated"] is False


def test_status_github_activity_business_sections(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        connect_mod,
        "github_context",
        lambda repo, **kwargs: {
            "ok": True,
            "state": "ready",
            "summary": "GitHub ready",
            "repair": "",
            "repair_command": "",
            "safe_to_share": True,
        },
    )
    monkeypatch.setattr(status_mod, "_which", lambda name: "/usr/bin/gh" if name == "gh" else "")
    monkeypatch.setattr(
        status_mod,
        "_run_command",
        lambda args, cwd=None, timeout=3.0: {"ok": True, "stdout": "", "stderr": ""},
    )

    def value_after(args: list[str], flag: str) -> str:
        if flag not in args:
            return ""
        return args[args.index(flag) + 1]

    def fake_gh_json(args: list[str], repo: Path) -> tuple[bool, Any, str]:
        state = value_after(args, "--state")
        search = value_after(args, "--search")
        if args[1:3] == ["issue", "list"]:
            if "--assignee" in args:
                return True, [{"number": 1, "title": "Assigned", "labels": []}], ""
            if state == "closed":
                return True, [{"number": 2, "title": "Closed", "closedAt": "2026-05-02"}], ""
            if search == "mentions:@me":
                return True, [{"number": 3, "title": "Mentioned task"}], ""
            if search == "label:blocked":
                return (
                    True,
                    [{"number": 4, "title": "Blocked", "labels": [{"name": "blocked"}]}],
                    "",
                )
            if search == "label:stale":
                return True, [{"number": 5, "title": "Stale", "labels": [{"name": "stale"}]}], ""
        if args[1:3] == ["pr", "list"]:
            if search == "review-requested:@me":
                return True, [{"number": 6, "title": "Review me", "author": {"login": "devon"}}], ""
            if search == "mentions:@me":
                return True, [{"number": 7, "title": "Mentioned proposal"}], ""
            if "--author" in args:
                return True, [{"number": 8, "title": "Open proposal"}], ""
            if state == "merged":
                return (
                    True,
                    [
                        {
                            "number": index,
                            "title": f"Merged {index}",
                            "body": f"- Launched {index}",
                            "mergedAt": f"2026-05-0{index}T00:00:00Z",
                        }
                        for index in range(1, 8)
                    ],
                    "",
                )
        return True, [], ""

    monkeypatch.setattr(status_mod, "_gh_json", fake_gh_json)
    github = status_mod._github(
        tmp_path,
        {"remote": "https://github.com/noontide-co/mainbranch.git"},
    )

    sections = github["sections"]
    assert github["summary"] == {
        "assigned_tasks": 1,
        "attention_requests": 3,
        "open_proposals": 1,
        "shipped_this_week": 7,
        "recently_closed_tasks": 1,
        "blocked_or_stale_tasks": 2,
    }
    assert sections["assigned_tasks"][0]["business_status"] == "assigned"
    assert sections["attention_requests"][0]["type"] == "proposal"
    assert sections["open_proposals"][0]["business_status"] == "open_proposal"
    assert len(sections["shipped_this_week"]) == 5
    assert sections["shipped_this_week"][0]["number"] == 7
    assert sections["shipped_this_week"][0]["what_shipped"] == "Launched 7"
    assert sections["recently_closed_tasks"][0]["business_status"] == "closed"
    assert sections["blocked_or_stale_tasks"][0]["labels"] == ["blocked"]


def test_status_github_activity_resolves_team_handles(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "core" / "team").mkdir(parents=True)
    (tmp_path / "core" / "team" / "maya.md").write_text(
        (
            "---\n"
            "type: team_member\n"
            "slug: maya\n"
            "name: Maya Chen\n"
            "preferred_name: Maya\n"
            "relationship: member\n"
            "github:\n"
            "  - mayachen\n"
            "---\n\n"
            "# Maya\n"
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        connect_mod,
        "github_context",
        lambda repo, **kwargs: {
            "ok": True,
            "state": "ready",
            "summary": "GitHub ready",
            "repair": "",
            "repair_command": "",
            "safe_to_share": True,
        },
    )
    monkeypatch.setattr(status_mod, "_which", lambda name: "/usr/bin/gh" if name == "gh" else "")
    monkeypatch.setattr(
        status_mod,
        "_run_command",
        lambda args, cwd=None, timeout=3.0: {"ok": True, "stdout": "", "stderr": ""},
    )

    def fake_gh_json(args: list[str], repo: Path) -> tuple[bool, Any, str]:
        if args[1:3] == ["pr", "list"] and "review-requested:@me" in args:
            return True, [{"number": 6, "title": "Review me", "author": {"login": "mayachen"}}], ""
        if args[1:3] == ["pr", "list"] and "--state" in args and "merged" in args:
            return True, [{"number": 7, "title": "Merged", "author": {"login": "unknown-dev"}}], ""
        return True, [], ""

    monkeypatch.setattr(status_mod, "_gh_json", fake_gh_json)

    report = status_mod.run(path=str(tmp_path), update_marker=False)
    attention = report["github"]["sections"]["attention_requests"][0]
    shipped = report["github"]["sections"]["shipped_this_week"][0]

    assert report["team"]["summary"]["members"] == 1
    assert attention["author"] == "mayachen"
    assert attention["author_display"] == "Maya"
    assert attention["author_known"] is True
    assert attention["author_team_slug"] == "maya"
    assert shipped["author_display"] == "unknown contributor (@unknown-dev)"
    assert shipped["author_known"] is False


def test_status_github_context_stops_before_low_level_remote_errors(
    tmp_path: Path, monkeypatch
) -> None:
    context = {
        "ok": False,
        "state": "missing_github_remote",
        "summary": "This repo does not have a GitHub origin remote.",
        "repair": "Add a GitHub origin remote before relying on GitHub tasks or proposals.",
        "repair_command": "gh repo create --source . --remote origin --push",
        "safe_to_share": True,
    }
    monkeypatch.setattr(connect_mod, "github_context", lambda repo, **kwargs: context)

    def fail_gh_json(args: list[str], repo: Path) -> tuple[bool, Any, str]:
        raise AssertionError(args)

    monkeypatch.setattr(status_mod, "_gh_json", fail_gh_json)

    github = status_mod._github(tmp_path, {"remote": ""})

    assert github["authenticated"] is True
    assert github["context"]["state"] == "missing_github_remote"
    assert github["errors"] == ["This repo does not have a GitHub origin remote."]
    assert "no git remotes found" not in json.dumps(github)


def test_status_reuses_github_context_for_integrations(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    calls = 0

    def fake_context(repo: Path, **kwargs: Any) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {
            "ok": False,
            "state": "missing_cli",
            "summary": "GitHub CLI is not installed.",
            "repair": "Install GitHub CLI, then run `gh auth login`.",
            "repair_command": "gh auth login",
            "safe_to_share": True,
        }

    monkeypatch.setattr(connect_mod, "github_context", fake_context)

    report = status_mod.run(path=str(repo))

    assert calls == 1
    assert report["integrations"]["github"] == report["github"]["context"]


def test_status_renderer_prints_optional_sections(capsys) -> None:
    report: dict[str, Any] = {
        "repo": {"path": "/tmp/biz", "looks_like_mainbranch_repo": True},
        "install": {"detail": "mb 0.1.2 (wheel mode)"},
        "runtime": {
            "claude_code": {"found": True},
            "skill_wiring": {"ok": True},
        },
        "git": {"inside_work_tree": False, "dirty": False, "error": "not a git work tree"},
        "brain": {
            "counts": {
                "core": 1,
                "reference/core": 1,
                "research": 1,
                "decisions": 1,
                "bets": 1,
                "campaigns": 1,
                "log": 1,
                "documents": 1,
            },
            "recent_decisions": [
                {"date": "2026-05-01", "updated_at": "", "title": "Pricing", "status": "accepted"}
            ],
            "stale_decisions": [
                {"path": "decisions/old.md", "age_days": 30},
            ],
            "recent_research": [
                {"date": "2026-05-01", "updated_at": "", "title": "Market"},
            ],
            "bets": {
                "active": [
                    {
                        "deadline": "2026-05-08",
                        "title": "Launch bet",
                        "status": "open",
                    }
                ],
                "due_soon": [],
                "overdue": [],
                "recent": [],
            },
        },
        "git_activity": {
            "items": [
                {
                    "date": "2026-05-02",
                    "commit": "abc123",
                    "subject": "Update brain",
                    "files": ["core/offer.md", "research/a.md", "decisions/b.md"],
                }
            ]
        },
        "github": {
            "available": True,
            "authenticated": True,
            "assigned_issues": [{"number": 173, "title": "Status"}],
            "review_requests": [],
            "recent_merged_prs": [{"number": 192, "what_shipped": "Daily briefing"}],
            "errors": ["merged PRs: degraded"],
        },
        "readiness": {"level": "ready", "score": 100, "next_actions": ["Run `claude`."]},
        "ranked_actions": [
            {
                "id": "review_due_bets",
                "title": "Review bets due this week",
                "command": "/mb-bet update",
                "reason": "1 active bet has a deadline soon.",
            }
        ],
    }

    status_mod.render_human(report, verbose=True, no_color=True)

    output = capsys.readouterr().out
    assert "Recent decisions" in output
    assert "Stale proposed/running decisions" in output
    assert "Recent research" in output
    assert "Active bets" in output
    assert "Recent git activity" in output
    assert "tasks assigned: 1" in output
    assert "shipped this week: 1" in output
    assert "task #173" in output
    assert "shipped #192" in output
    assert "Review bets due this week" in output


def test_status_renderer_falls_back_to_readiness_actions_for_legacy_reports(capsys) -> None:
    report: dict[str, Any] = {
        "repo": {"path": "/tmp/biz", "looks_like_mainbranch_repo": True},
        "install": {"detail": "mb 0.2.6 (wheel mode)"},
        "runtime": {
            "claude_code": {"found": True},
            "skill_wiring": {"ok": True},
        },
        "git": {"inside_work_tree": True, "branch": "main", "dirty": False},
        "brain": {
            "counts": {
                "core": 0,
                "reference/core": 0,
                "research": 0,
                "decisions": 0,
                "bets": 0,
                "campaigns": 0,
                "log": 0,
                "documents": 0,
            },
            "recent_decisions": [],
            "stale_decisions": [],
            "stale_research": [],
            "recent_research": [],
            "bets": {"active": [], "due_soon": [], "overdue": [], "recent": []},
        },
        "git_activity": {"items": []},
        "github": {
            "available": False,
            "authenticated": False,
            "errors": [],
        },
        "readiness": {
            "level": "ready",
            "score": 100,
            "next_actions": ["Run `claude` in this repo, then `/mb-start`."],
        },
    }

    status_mod.render_human(report, no_color=True)

    output = capsys.readouterr().out
    assert "Run `claude` in this repo, then `/mb-start`." in output


_VALID_TOPOLOGY_REGISTRY = """\
---
type: repo_topology
status: active
schema: mb.repo_topology.v0
home: github:example-co/example
business_display_name: Example Business
repos:
  - slug: example
    display_name: Example Business
    role: business
    lifecycle: active
    github_owner: example-co
    repo_name: example
    remote: github:example-co/example
    visibility: team_private
    relationship: hub_for
    purpose: Hub repo for company strategy and decisions.
  - slug: workshop-site
    display_name: Workshop site
    role: site
    lifecycle: active
    relationship: execution_vehicle_for
    parent: example
    github_owner: example-co
    repo_name: workshop-site
    remote: github:example-co/workshop-site
    visibility: public
---
# Topology
"""


def test_status_exposes_topology_section_when_registry_missing(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    # Ensure no topology registry exists.
    registry_path = repo / "core" / "operations" / "repo-topology.md"
    if registry_path.exists():
        registry_path.unlink()

    report = status_mod.run(path=str(repo), update_marker=False)
    topology = report["topology"]

    assert topology["schema"] == "mb.topology.view.v0"
    assert topology["safe_to_share"] is True
    assert topology["summary"]["registry_found"] is False
    assert topology["summary"]["warnings"] == 0
    assert topology["current_repo"]["matched"] is False
    assert topology["repo_boundary"]["state"] == "single_business_repo"
    assert topology["repo_boundary"]["recommended_choice"] == "same_business_repo"
    assert topology["registry"]["found"] is False
    assert topology["registry"]["ok"] is False
    assert topology["local"]["repo_path"] == str(repo.resolve())
    assert topology["local"]["safe_to_share"] is False


def test_status_flags_missing_role_for_child_checkout(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    # Drop the hub registry and add a site signal with no declared role so the
    # checkout looks like an un-roled child.
    registry_path = repo / "core" / "operations" / "repo-topology.md"
    if registry_path.exists():
        registry_path.unlink()
    (repo / ".mainbranch").mkdir(exist_ok=True)
    (repo / ".mainbranch" / "conversion.json").write_text("{}", encoding="utf-8")

    report = status_mod.run(path=str(repo), update_marker=False)
    topology = report["topology"]

    assert topology["summary"]["current_repo_role"] == ""
    assert topology["summary"]["current_repo_role_suggestion"] == "site"
    codes = {f["code"] for f in topology["findings"]}
    assert "topology_role_not_identified" in codes


def test_status_exposes_topology_section_with_valid_registry(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    registry_path = repo / "core" / "operations" / "repo-topology.md"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(_VALID_TOPOLOGY_REGISTRY, encoding="utf-8")

    report = status_mod.run(path=str(repo), update_marker=False)
    topology = report["topology"]

    assert topology["summary"]["registry_ok"] is True
    assert topology["summary"]["child_repo_count"] >= 1
    assert topology["repo_boundary"]["schema"] == "mb.repo_boundary_helper.v0"
    assert topology["repo_boundary"]["recommended_choice"] == "same_business_repo"
    # The hub itself should match by github_owner/repo_name fall-through (no
    # remote configured in tmp git), or fall through to descriptor. Either way
    # the registry recorded the hub role for this owner/repo pair.
    registry_repos = topology["registry"]["repos"]
    business_entries = [entry for entry in registry_repos if entry.get("role") == "business"]
    assert business_entries, "expected at least one business role entry"

    public_payload = json.dumps({key: topology[key] for key in topology if key != "local"})
    assert "/Users/" not in public_payload
    assert str(repo.resolve()) not in public_payload


def test_status_human_output_mentions_business_map(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")

    quiet = runner.invoke(app, ["status", str(repo)])
    assert quiet.exit_code == 0
    assert "Business map" in quiet.stdout

    loud = runner.invoke(app, ["status", str(repo), "--verbose"])
    assert loud.exit_code == 0
    assert "Business map" in loud.stdout


def test_classify_workflow_covers_known_states() -> None:
    assert (
        status_mod._classify_workflow(
            branch="",
            is_linked_worktree=False,
            default_branch="main",
        )
        == "detached"
    )
    assert (
        status_mod._classify_workflow(
            branch="main",
            is_linked_worktree=False,
            default_branch="main",
        )
        == "solo-on-main"
    )
    assert (
        status_mod._classify_workflow(
            branch="feature/x",
            is_linked_worktree=False,
            default_branch="main",
        )
        == "branch"
    )
    assert (
        status_mod._classify_workflow(
            branch="feature/x",
            is_linked_worktree=True,
            default_branch="main",
        )
        == "worktree"
    )


def test_build_git_summary_reads_in_business_language() -> None:
    on_main = status_mod._build_git_summary(
        workflow_mode="solo-on-main",
        branch="main",
        default_branch="main",
        dirty_count=0,
        ahead=None,
        behind=None,
    )
    assert "main workspace" in on_main
    assert "no unsaved local changes" in on_main

    on_branch = status_mod._build_git_summary(
        workflow_mode="branch",
        branch="feature/x",
        default_branch="main",
        dirty_count=3,
        ahead=2,
        behind=1,
    )
    assert "separate workspace" in on_branch
    assert "3 unsaved local files" in on_branch
    assert "local and shared saved work need reconciliation" in on_branch

    detached = status_mod._build_git_summary(
        workflow_mode="detached",
        branch="",
        default_branch="main",
        dirty_count=0,
        ahead=None,
        behind=None,
    )
    assert "detached" in detached.lower()
    assert "Switch back to a named workspace" in detached


def test_git_info_solo_on_main_without_remote(tmp_path: Path) -> None:
    """Local repo on the default branch with no `origin` remote should still
    classify as solo-on-main, leave ahead/behind null, and produce a clear
    summary. Locks the contract for the most common existing-repo state."""
    repo = tmp_path / "solo"
    repo.mkdir()
    assert _git(repo, "init", "-b", "main").returncode == 0
    _configure_git_user(repo)
    _commit(repo, "README.md", "hello\n", "[add] readme")

    info = status_mod._git_info(repo)
    assert info["inside_work_tree"] is True
    assert info["branch"] == "main"
    assert info["workflow_mode"] == "solo-on-main"
    assert info["default_branch"] == "main"
    assert info["dirty"] is False
    assert info["remote"] == ""
    assert info["upstream"] == ""
    assert info["ahead"] is None
    assert info["behind"] is None
    assert info["summary"]
    assert "main" in info["summary"]
    assert "unsaved local" in info["summary"]


def test_git_info_branch_without_upstream(tmp_path: Path) -> None:
    """Feature branch with no upstream should classify as branch, leave
    ahead/behind null, and use business-owner workspace language in the summary.
    Common state when an operator starts work but hasn't pushed yet."""
    repo = tmp_path / "branched"
    repo.mkdir()
    assert _git(repo, "init", "-b", "main").returncode == 0
    _configure_git_user(repo)
    _commit(repo, "README.md", "hello\n", "[add] readme")
    assert _git(repo, "checkout", "-b", "feature/x").returncode == 0

    info = status_mod._git_info(repo)
    assert info["branch"] == "feature/x"
    assert info["workflow_mode"] == "branch"
    assert info["default_branch"] == "main"
    assert info["upstream"] == ""
    assert info["ahead"] is None
    assert info["behind"] is None
    assert "separate workspace" in info["summary"]
    assert "feature/x" not in info["summary"]


def test_git_info_handles_non_git_directory(tmp_path: Path) -> None:
    info = status_mod._git_info(tmp_path)
    # Either git is missing or this is not a work tree; either way no workflow.
    assert info.get("inside_work_tree") in (False, None)
    assert "workflow_mode" not in info or info.get("workflow_mode") in ("", None)


def test_status_ranked_actions_always_carry_audience_and_summary(
    tmp_path: Path, monkeypatch
) -> None:
    """Every ranked action emitted by `mb status` must have a valid audience
    and a non-empty operator_summary, so skills can route on the field
    without re-deriving from schema language."""
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "fresh"
    init_run(path=str(repo), name="Fresh")

    payload = status_mod.run(
        path=str(repo),
        now=datetime(2026, 5, 4, 12, 0, tzinfo=timezone.utc),
        update_marker=False,
    )

    actions = payload["ranked_actions"]
    assert actions, "expected at least one ranked action on a fresh repo"
    valid_audiences = {"mechanical", "operator_decision", "informational"}
    for action in actions:
        assert action["audience"] in valid_audiences, (
            f"action {action['id']} has invalid audience: {action['audience']!r}"
        )
        assert action["operator_summary"], f"action {action['id']} has empty operator_summary"


def test_git_info_detects_linked_worktree(tmp_path: Path) -> None:
    """Conductor workspaces and `git worktree add` checkouts should report
    workflow_mode='worktree' internally and use operator-facing workspace copy."""
    main_repo = tmp_path / "main"
    main_repo.mkdir()
    assert _git(main_repo, "init", "-b", "main").returncode == 0
    _configure_git_user(main_repo)
    _commit(main_repo, "README.md", "hello\n", "[add] readme")

    worktree_path = tmp_path / "wt-feature"
    add = _git(main_repo, "worktree", "add", "-b", "feature/x", str(worktree_path))
    assert add.returncode == 0, add.stderr

    info = status_mod._git_info(worktree_path)
    assert info["inside_work_tree"] is True
    assert info["workflow_mode"] == "worktree"
    assert info["branch"] == "feature/x"
    assert info["default_branch"] == "main"
    assert info["worktree_root"] == str(worktree_path.resolve())
    assert "linked workspace" in info["summary"]


def test_core_propagation_drift_flags_identity_newer_than_active_push(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess as sp

    from mb import status as status_pkg

    repo = tmp_path / "biz"
    (repo / "core").mkdir(parents=True)
    (repo / "core" / "offer.md").write_text("# offer v2\n", encoding="utf-8")
    push_dir = repo / "pushes" / "2026-06-01-launch"
    push_dir.mkdir(parents=True)
    (push_dir / "push.md").write_text(
        (
            "---\ntype: push\nslug: launch\nkind: launch\nstatus: active\n"
            "health: on-track\nowner: o\naudience: a\noffer: core/offer.md\n"
            "promise: p\n---\n# launch\n"
        ),
        encoding="utf-8",
    )

    import os

    def git(*args: str, when: str = "") -> None:
        env = dict(os.environ)
        if when:
            env["GIT_COMMITTER_DATE"] = when
            env["GIT_AUTHOR_DATE"] = when
        sp.run(["git", *args], cwd=repo, check=True, capture_output=True, env=env)

    git("init")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "T")
    git("add", "pushes")
    git("commit", "-m", "push first", when="2026-06-01T00:00:00")
    git("add", "core")
    git("commit", "-m", "identity later", when="2026-06-10T00:00:00")

    report = {
        "repo": str(repo),
        "brain": {
            "pushes": {
                "records": [
                    {
                        "path": "pushes/2026-06-01-launch/push.md",
                        "status": "active",
                        "legacy": False,
                    }
                ]
            }
        },
    }
    item = status_pkg._core_propagation_drift(repo, report)

    assert item is not None
    assert item["id"] == "core_propagation"
    assert "core/offer.md" in item["evidence"]

    # Touch the push AFTER the identity change: drift clears.
    (push_dir / "push.md").write_text(
        (push_dir / "push.md").read_text(encoding="utf-8") + "\nupdated.\n", encoding="utf-8"
    )
    git("add", "pushes")
    git("commit", "-m", "push refreshed", when="2026-06-11T00:00:00")
    assert status_pkg._core_propagation_drift(repo, report) is None


def test_core_propagation_drift_silent_without_active_pushes(tmp_path: Path) -> None:
    from mb import status as status_pkg

    repo = tmp_path / "biz"
    (repo / "core").mkdir(parents=True)
    (repo / "core" / "offer.md").write_text("# offer\n", encoding="utf-8")

    report = {"repo": str(repo), "brain": {"pushes": {"records": []}}}

    assert status_pkg._core_propagation_drift(repo, report) is None


def test_uncodified_decisions_drift(tmp_path: Path) -> None:
    from mb import status as status_pkg

    repo = tmp_path / "biz"
    decisions = repo / "decisions"
    decisions.mkdir(parents=True)
    (decisions / "2026-05-01-old-accepted.md").write_text(
        "---\ndate: 2026-05-01\nstatus: accepted\n---\n# old accepted\n",
        encoding="utf-8",
    )
    (decisions / "2026-05-01-applied.md").write_text(
        "---\ndate: 2026-05-01\nstatus: codified\n---\n# applied\n",
        encoding="utf-8",
    )

    brain = status_pkg._brain(repo)
    uncodified = brain["uncodified_decisions"]

    assert len(uncodified) == 1
    assert brain["uncodified_decisions_total"] == 1
    assert uncodified[0]["path"].endswith("2026-05-01-old-accepted.md")

    report = {
        "brain": brain,
        "repo": str(repo),
        "runtime": {},
        "validation": {},
        "relationship_health": {},
        "playbook_health": {},
        "integrations": {},
        "measurement": {},
        "books": {},
        "topology": {},
        "since_last_check": {"marker_gitignore": {"ok": True}},
    }
    drift = status_pkg._drift(report)
    by_id = {item["id"]: item for item in drift["items"]}

    assert "uncodified_decisions" in by_id
    assert "never" in by_id["uncodified_decisions"]["summary"]
    assert "codify" in by_id["uncodified_decisions"]["repair"]


@pytest.mark.parametrize("count", [3, 9])
def test_uncodified_decision_total_and_shown_count(tmp_path: Path, count: int) -> None:
    repo = tmp_path / "biz"
    decisions = repo / "decisions"
    decisions.mkdir(parents=True)
    for index in range(count):
        (decisions / f"2025-01-01-choice-{index}.md").write_text(
            "---\ndate: 2025-01-01\nstatus: accepted\n---\n# Choice\n",
            encoding="utf-8",
        )
    brain = status_mod._brain(repo)
    assert brain["uncodified_decisions_total"] == count
    assert len(brain["uncodified_decisions"]) == min(count, 5)
    report = {
        "repo": str(repo),
        "brain": brain,
        "runtime": {},
        "since_last_check": {"marker_gitignore": {"ok": True}},
    }
    gap = next(
        item for item in status_mod._drift(report)["items"] if item["id"] == "uncodified_decisions"
    )
    assert len(gap["evidence"]) == min(count, 5)
    assert gap["summary"].startswith(f"{count} accepted decision")
    assert ("(5 shown)" in gap["summary"]) is (count > 5)


def test_status_runtime_claude_repair_is_plugin_first_when_missing(
    tmp_path: Path, monkeypatch
) -> None:
    # #924: with no `claude` CLI on PATH the repair must point at the plugin
    # (Desktop + terminal), not assume the only fix is installing the CLI.
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")

    report = status_mod.run(path=str(repo), update_marker=False)

    claude_code = report["runtime"]["claude_code"]
    assert claude_code["found"] is False
    assert "noontide-co/mainbranch" in claude_code["repair"]
    assert "Claude Desktop" in claude_code["repair"]


def test_status_runtime_claude_repair_empty_when_present(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        status_mod,
        "_which",
        lambda name: "/usr/local/bin/claude" if name == "claude" else (shutil.which(name) or ""),
    )
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")

    report = status_mod.run(path=str(repo), update_marker=False)

    claude_code = report["runtime"]["claude_code"]
    assert claude_code["found"] is True
    assert claude_code["repair"] == ""


def _measured_repo(tmp_path: Path, *, customer_id: str = "") -> Path:
    repo = tmp_path / "acme"
    init_run(path=str(repo), name="Acme")
    customer_line = f"google_ads_customer_id: '{customer_id}'\n" if customer_id else ""
    (repo / "core" / "offer.md").write_text(
        f"---\ngtm_container_id: GTM-ABC1234\n{customer_line}---\n\n# Offer\n",
        encoding="utf-8",
    )
    (repo / ".mainbranch").mkdir(exist_ok=True)
    (repo / ".mainbranch" / "conversion.json").write_text(
        json.dumps(
            {
                "kind": "lead_form",
                "url": "https://tally.so/r/example",
                "primary_conversions": ["mb_lead_submit"],
            }
        ),
        encoding="utf-8",
    )
    return repo


def test_status_measurement_names_the_google_ads_statuses(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "local-file")
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "home"))
    repo = _measured_repo(tmp_path, customer_id="5550100000")

    measurement = status_mod.run(path=str(repo), update_marker=False)["measurement"]

    assert measurement["google_ads"] == {
        "google_ads_plan": "declared",
        "google_ads_connection": "not_checked",
        "google_ads_conversion_evidence": "no_evidence_recorded",
    }
    assert measurement["manual_count"] >= 2

    result = runner.invoke(app, ["status", str(repo)])

    assert result.exit_code == 0
    assert (
        "Google Ads: customer and conversion plan declared; account connection not "
        "checked; no conversion evidence recorded"
    ) in " ".join(result.stdout.split())


def test_status_measurement_names_a_placeholder_google_ads_customer(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "local-file")
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "home"))
    repo = _measured_repo(tmp_path, customer_id="000-000-0000")

    measurement = status_mod.run(path=str(repo), update_marker=False)["measurement"]

    assert measurement["google_ads"] == {"google_ads_plan": "placeholder"}
    result = runner.invoke(app, ["status", str(repo)])
    assert "Google Ads: customer ID is a placeholder" in result.stdout


def test_status_measurement_placeholder_customer_names_a_missing_conversion_plan(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "local-file")
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "home"))
    repo = _measured_repo(tmp_path, customer_id="TODO: add id")
    (repo / ".mainbranch" / "conversion.json").write_text(
        json.dumps({"kind": "lead_form", "url": "https://tally.so/r/example"}),
        encoding="utf-8",
    )

    measurement = status_mod.run(path=str(repo), update_marker=False)["measurement"]

    assert measurement["google_ads"] == {"google_ads_plan": "placeholder"}
    result = runner.invoke(app, ["status", str(repo)])
    assert "Google Ads: customer ID is a placeholder; conversion plan missing" in " ".join(
        result.stdout.split()
    )


def test_status_measurement_without_google_ads_customer_has_no_google_ads_field(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(status_mod, "_which", _without_github_or_claude)
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "local-file")
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "home"))
    repo = _measured_repo(tmp_path)

    measurement = status_mod.run(path=str(repo), update_marker=False)["measurement"]

    assert measurement["available"] is True
    assert "google_ads" not in measurement
    result = runner.invoke(app, ["status", str(repo)])
    assert "Google Ads:" not in result.stdout
