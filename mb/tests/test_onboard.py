"""``mb onboard`` adaptive setup flow."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mb import graph as graph_mod
from mb import onboard as onboard_mod
from mb import status as status_mod
from mb import validate as validate_mod
from mb.cli import app

runner = CliRunner()


def _tool_path(name: str) -> str:
    if name == "git":
        return shutil.which("git") or ""
    return ""


def _tool_path_with_codex(name: str) -> str:
    if name == "codex":
        return "/usr/local/bin/codex"
    return _tool_path(name)


def _normalize(text: str) -> str:
    return " ".join(text.split())


def _assert_onboard_claude_md_cli_first_contract(text: str) -> None:
    normalized = _normalize(text)
    assert "## Claude operating contract" in text
    assert "Main Branch CLI facts are the source of truth" in text
    assert "mb status --json --peek" in text
    assert "mb start --json" in text
    assert "mb doctor repair --plan" in text
    assert "Read-only commands can be run without asking first" in text
    assert "require explicit operator approval before applying" in text
    assert "If `/mb-start` is not discoverable" in text
    assert "business-owner language" in text
    assert "## First-run setup intent" in text
    assert "setup intent, not as a document to save" in normalized
    assert "gh auth status" in normalized
    assert "business record" in normalized
    assert "## Business primitive routing" in text
    assert "multi-offer repo, `core/offer.md` is the portfolio thesis" in text
    assert "offer-specific proof belongs in `core/offers/<slug>/proof/`" in text
    assert "Use standard proof files such as `testimonials.md`" in text
    assert "Do not rename, delete, merge, split, or move offer folders" in text


def test_onboard_yes_creates_repo_and_reports_next_steps(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(onboard_mod, "_which", _tool_path)
    repo = tmp_path / "acme"

    result = onboard_mod.run(
        path=str(repo),
        name="Acme Brewing",
        mode="new",
        level="beginner",
    )

    assert result["ok"] is True
    assert result["action"] == "created"
    assert result["level"] == "beginner"
    assert (repo / "CLAUDE.md").exists()
    claude_md = (repo / "CLAUDE.md").read_text(encoding="utf-8")
    _assert_onboard_claude_md_cli_first_contract(claude_md)
    assert (repo / ".claude" / "skills" / "mb-start" / "SKILL.md").exists()
    assert (repo / ".git" / "hooks" / "commit-msg").exists()
    assert result["checkpoint_hook"]["state"] == "installed"
    assert result["skill_wiring"]["ok"] is True
    assert result["setup_complete"]["scaffolded"] is True
    assert result["setup_complete"]["initialized_on_main"] is True
    assert result["setup_complete"]["checkpoint_hook_ready"] is True
    assert result["setup_complete"]["claude_code_handoff_ready"] is True
    assert result["setup_complete"]["codex_instructions_present"] is True
    assert result["next_steps"] == [
        f"cd {repo.resolve()}",
        "claude",
        "/mb-start",
        "Save your first checkpoint once you've made changes: mb checkpoint --plan",
    ]
    assert any("Claude Code" in warning for warning in result["warnings"])
    assert any(
        "gh auth login" in warning or "GitHub CLI" in warning for warning in result["warnings"]
    )


def test_onboard_next_steps_offer_global_codex_repair_when_available(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(onboard_mod, "_which", _tool_path_with_codex)
    repo = tmp_path / "acme"

    result = onboard_mod.run(
        path=str(repo),
        name="Acme Brewing",
        mode="new",
        level="beginner",
    )

    assert result["next_steps"] == [
        f"cd {repo.resolve()}",
        "claude",
        "/mb-start",
        "mb doctor repair --plan --only codex",
        "mb doctor repair --apply --only codex",
        f"codex -C {repo.resolve()}",
        "Ask Codex to start this Main Branch business day from read-only mb facts.",
        "Save your first checkpoint once you've made changes: mb checkpoint --plan",
    ]


def test_onboard_without_github_never_scrapes_machine_login(tmp_path: Path, monkeypatch) -> None:
    from mb import init as init_mod

    monkeypatch.setattr(onboard_mod, "_which", _tool_path)
    monkeypatch.setattr(init_mod, "_gh_username", lambda: "machine-login")
    repo = tmp_path / "acme"

    result = onboard_mod.run(
        path=str(repo),
        name="Acme Brewing",
        mode="new",
        owner_name="Riley Quinn",
    )

    assert result["ok"] is True
    # The operator declined GitHub (no --github): the machine's gh login
    # must not appear anywhere in the scaffold (#880, cold-eyes finding).
    assert not (repo / "core" / "team" / "machine-login.md").exists()
    assert (repo / "core" / "team" / "riley-quinn.md").exists()
    for rel in ("CLAUDE.md", "AGENTS.md", ".github/CODEOWNERS", "core/team/riley-quinn.md"):
        text = (repo / rel).read_text(encoding="utf-8")
        assert "machine-login" not in text, rel


def test_onboard_rerun_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(onboard_mod, "_which", _tool_path)
    repo = tmp_path / "acme"

    first = onboard_mod.run(path=str(repo), name="Acme", mode="new", level="auto")
    second = onboard_mod.run(path=str(repo), name="Acme", mode="auto", level="auto")

    assert first["action"] == "created"
    assert second["action"] == "repaired"
    assert second["ok"] is True
    assert second["repo"]["before"]["claude_md"] is True
    assert (repo / "CLAUDE.md").exists()


def test_onboard_connect_repairs_existing_initialized_repo(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(onboard_mod, "_which", _tool_path)
    repo = tmp_path / "acme"
    onboard_mod.run(
        path=str(repo),
        name="Acme",
        mode="new",
        level="power",
        team_size="solo",
        business_type="coaching",
        success_stage="working",
        desired_outcome="usable core files",
    )
    settings = repo / ".claude" / "settings.local.json"
    settings.unlink()

    result = onboard_mod.run(path=str(repo), name="", mode="connect", level="power")

    assert result["ok"] is True
    assert result["action"] == "repaired"
    assert result["business_name"] == ""
    assert settings.exists()
    assert result["skill_wiring"]["ok"] is True


def test_onboard_connect_backfills_plugin_wiring(tmp_path: Path, monkeypatch) -> None:
    # The connect path is how a symlink-era repo gets migrated when the operator
    # runs `mb onboard` rather than `mb doctor`. Lock that it wires the plugin.
    from mb import engine as engine_mod

    monkeypatch.setattr(onboard_mod, "_which", _tool_path)
    repo = tmp_path / "acme"
    onboard_mod.run(
        path=str(repo),
        name="Acme",
        mode="new",
        level="power",
        team_size="solo",
        business_type="coaching",
        success_stage="working",
        desired_outcome="usable core files",
    )
    # Simulate symlink-era: drop the tracked plugin wiring.
    (repo / ".claude" / "settings.json").unlink()
    assert engine_mod.plugin_wiring_status(repo)["wired"] is False

    result = onboard_mod.run(path=str(repo), name="", mode="connect", level="power")

    assert result["ok"] is True
    assert engine_mod.plugin_wiring_status(repo)["wired"] is True
    assert ".claude/settings.json" in result["created"]


def test_onboard_connect_missing_repo_routes_to_doctor(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(onboard_mod, "_which", _tool_path)
    repo = tmp_path / "missing"

    result = onboard_mod.run(path=str(repo), name="", mode="connect", level="power")

    assert result["ok"] is False
    assert "cannot connect missing repo" in result["errors"][0]
    assert result["doctor_command"].startswith("mb doctor ")


def test_onboard_connect_uninitialized_repo_explains_repair(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(onboard_mod, "_which", _tool_path)
    repo = tmp_path / "plain"
    repo.mkdir()

    result = onboard_mod.run(path=str(repo), name="", mode="connect", level="power")

    assert result["ok"] is False
    assert any("does not look like a Main Branch repo" in error for error in result["errors"])
    assert result["doctor_command"].startswith("mb doctor ")
    assert result["created"] == []
    assert not (repo / ".claude").exists()
    assert not (repo / ".gitignore").exists()


def test_onboard_cli_noninteractive_requires_yes(monkeypatch) -> None:
    monkeypatch.setattr(onboard_mod, "is_interactive", lambda: False)

    result = runner.invoke(app, ["onboard"])

    assert result.exit_code == 2
    assert "Use `mb onboard --yes`" in result.stderr


def test_onboard_cli_yes_json_smoke(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(onboard_mod, "_which", _tool_path)
    monkeypatch.setattr(onboard_mod, "is_interactive", lambda: False)
    repo = tmp_path / "acme"

    result = runner.invoke(
        app,
        [
            "onboard",
            "--yes",
            "--name",
            "Acme Brewing",
            "--path",
            str(repo),
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["path"] == str(repo.resolve())
    assert "/mb-start" in payload["next_steps"]
    assert payload["next_steps"][-1] == (
        "Save your first checkpoint once you've made changes: mb checkpoint --plan"
    )
    assert payload["setup_complete"]["scaffolded"] is True
    assert payload["setup_complete"]["github_requested"] is False
    assert (repo / ".mb" / "onboarding.json").exists()
    assert payload["onboarding"]["summary"]["status"] == "in_progress"
    assert payload["onboarding"]["repo_boundary"]["schema"] == "mb.repo_boundary_helper.v0"
    assert payload["onboarding"]["repo_boundary"]["recommended_choice"] == "same_business_repo"
    assert ".mb/onboarding.json" in (repo / ".gitignore").read_text(encoding="utf-8")
    assert ".vip/local.yaml" in (repo / ".gitignore").read_text(encoding="utf-8")

    graph = graph_mod.build_index(str(repo))
    validate = validate_mod.run(str(repo), cross_refs=True)
    assert graph["registry"]["version"] == "0.1"
    assert validate["cross_refs"]["registry"]["version"] == "0.1"


def test_onboard_status_reports_partial_small_team_progress(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(onboard_mod, "_which", _tool_path)
    repo = tmp_path / "acme"
    onboard_mod.run(
        path=str(repo),
        name="Acme",
        mode="new",
        level="power",
        team_size="small-team",
        business_type="agency",
        success_stage="working",
        desired_outcome="usable core files",
    )
    (repo / "core" / "offer.md").write_text("# Offer\n", encoding="utf-8")

    result = runner.invoke(app, ["onboard", "status", "--repo", str(repo), "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["state_exists"] is True
    assert payload["profile"]["team_size"] == "small_team"
    assert payload["summary"]["status"] == "in_progress"
    assert payload["summary"]["next_step"] == "core_reference"
    assert "audience" in payload["summary"]["missing_inputs"]
    team_step = next(step for step in payload["checklist"] if step["id"] == "team_layer")
    assert team_step["title"] == "Small-team GitHub loop"
    assert team_step["required"] is True


def test_onboard_status_accepts_canonical_core_proof_directory(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(onboard_mod, "_which", _tool_path)
    repo = tmp_path / "proof"
    onboard_mod.run(
        path=str(repo),
        name="Proof Co",
        mode="new",
        level="power",
        team_size="solo",
        business_type="coaching",
        success_stage="working",
        desired_outcome="usable core files",
    )
    (repo / "core" / "offer.md").write_text("# Offer\n", encoding="utf-8")
    (repo / "core" / "audience.md").write_text("# Audience\n", encoding="utf-8")
    (repo / "core" / "voice.md").write_text("# Voice\n", encoding="utf-8")
    (repo / "core" / "soul.md").write_text("# Soul\n", encoding="utf-8")
    if (repo / "core" / "proof").is_file():
        (repo / "core" / "proof").unlink()
    proof = repo / "core" / "proof" / "testimonials.md"
    proof.parent.mkdir(parents=True, exist_ok=True)
    proof.write_text("# Testimonials\n", encoding="utf-8")

    payload = onboard_mod.onboarding_status(repo)

    core_step = next(step for step in payload["checklist"] if step["id"] == "core_reference")
    assert core_step["status"] == "complete"
    assert "proof" not in payload["summary"]["missing_inputs"]


def test_onboard_status_unknown_team_size_is_not_larger_team(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(onboard_mod, "_which", _tool_path)
    repo = tmp_path / "unknown-team"
    onboard_mod.run(
        path=str(repo),
        name="Unknown Team",
        mode="new",
        level="power",
        business_type="agency",
        success_stage="working",
        desired_outcome="usable core files",
    )

    payload = onboard_mod.onboarding_status(repo)

    team_step = next(step for step in payload["checklist"] if step["id"] == "team_layer")
    assert team_step["title"] == "Team operating loop"
    assert team_step["required"] is False
    assert team_step["missing_inputs"] == ["team_size"]


def test_onboard_plan_updates_profile_without_raw_business_state(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(onboard_mod, "_which", _tool_path)
    repo = tmp_path / "solo"
    onboard_mod.run(path=str(repo), name="Solo Co", mode="new", level="power")

    result = runner.invoke(
        app,
        [
            "onboard",
            "plan",
            "--repo",
            str(repo),
            "--team-size",
            "solo",
            "--business-type",
            "coaching",
            "--success-stage",
            "successful",
            "--desired-outcome",
            "document the core files",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["profile"]["success_stage"] == "successful"
    state = json.loads((repo / ".mb" / "onboarding.json").read_text(encoding="utf-8"))
    assert "never_store_here" in state["contract"]
    assert "chat transcripts" in " ".join(state["contract"]["never_store_here"])


def test_onboard_plan_stores_safe_moneypath_threshold_context_without_books_write(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(onboard_mod, "_which", _tool_path)
    repo = tmp_path / "solo"
    onboard_mod.run(path=str(repo), name="Solo Co", mode="new", level="power")

    result = runner.invoke(
        app,
        [
            "onboard",
            "plan",
            "--repo",
            str(repo),
            "--operating-currency",
            "usd",
            "--books-storage-mode",
            "solo-local",
            "--monthly-experiment-budget-band",
            "500-2k",
            "--trivial-max-amount",
            "100",
            "--small-max-amount",
            "1000",
            "--threshold-privacy",
            "declared",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["money_path"]["operating_currency"] == "USD"
    assert payload["money_path"]["monthly_experiment_budget_band"] == "500-2k"
    assert payload["money_path"]["trivial_max_amount"] == 100
    assert not (repo / "core" / "finance" / "books.md").exists()
    state_text = (repo / ".mb" / "onboarding.json").read_text(encoding="utf-8")
    assert "revenue" not in state_text
    assert "balance" not in state_text
    assert ".mb/onboarding.json" in (repo / ".gitignore").read_text(encoding="utf-8")


def test_onboard_yes_writes_confirmed_safe_moneypath_thresholds_to_books_policy(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(onboard_mod, "_which", _tool_path)
    repo = tmp_path / "acme"

    result = onboard_mod.run(
        path=str(repo),
        name="Acme",
        mode="new",
        level="power",
        operating_currency="usd",
        books_storage_mode="solo-local",
        trivial_max_amount="100",
        small_max_amount="1000",
        material_max_amount="5000",
        strategic_min_amount="5000",
        approval_required_for_material="yes",
        ledger_anchor_default="yes",
    )

    assert result["ok"] is True
    assert "core/finance/books.md" in result["created"]
    books_text = (repo / "core" / "finance" / "books.md").read_text(encoding="utf-8")
    assert "operating_currency: USD" in books_text
    assert "appetite_thresholds:" in books_text
    assert "material:" in books_text
    assert "approval: accepted_decision" in books_text
    assert "requires_exit_rubric: true" in books_text
    assert "payee" not in books_text
    assert "balance" not in books_text

    report = status_mod.run(path=str(repo), update_marker=False)
    assert report["money_path"]["policy"]["thresholds_declared"] is True


def test_onboard_private_threshold_choice_keeps_thresholds_optional(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(onboard_mod, "_which", _tool_path)
    repo = tmp_path / "private"
    onboard_mod.run(
        path=str(repo),
        name="Private Co",
        mode="new",
        level="power",
        threshold_privacy="private",
    )

    payload = onboard_mod.onboarding_status(repo)
    threshold_step = next(
        step for step in payload["checklist"] if step["id"] == "money_path_thresholds"
    )
    assert threshold_step["status"] == "complete"
    assert threshold_step["required"] is False
    assert not (repo / "core" / "finance" / "books.md").exists()


def test_onboard_private_threshold_choice_does_not_commit_amounts(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(onboard_mod, "_which", _tool_path)
    repo = tmp_path / "private-amount"

    onboard_mod.run(
        path=str(repo),
        name="Private Amount Co",
        mode="new",
        level="power",
        threshold_privacy="private",
        trivial_max_amount="100",
    )

    assert not (repo / "core" / "finance" / "books.md").exists()
    state_text = (repo / ".mb" / "onboarding.json").read_text(encoding="utf-8")
    assert '"threshold_privacy": "private"' in state_text
    assert '"trivial_max_amount": 100' in state_text


def test_onboard_non_local_books_storage_does_not_fake_local_vault(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(onboard_mod, "_which", _tool_path)
    repo = tmp_path / "team-books"

    onboard_mod.run(
        path=str(repo),
        name="Team Books Co",
        mode="new",
        level="power",
        books_storage_mode="team-private-repo",
        trivial_max_amount="100",
    )

    books_text = (repo / "core" / "finance" / "books.md").read_text(encoding="utf-8")
    assert "storage_mode: team-private-repo" in books_text
    assert "vault_location: ''" in books_text
    assert ".mb/private/books/" not in books_text


def test_onboard_non_local_storage_switch_clears_generated_local_vault(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(onboard_mod, "_which", _tool_path)
    repo = tmp_path / "storage-switch"

    onboard_mod.run(
        path=str(repo),
        name="Storage Switch Co",
        mode="new",
        level="power",
        books_storage_mode="solo-local",
        trivial_max_amount="100",
    )
    onboard_mod.run(
        path=str(repo),
        name="Storage Switch Co",
        mode="connect",
        level="power",
        books_storage_mode="team-private-repo",
        small_max_amount="1000",
    )

    books_text = (repo / "core" / "finance" / "books.md").read_text(encoding="utf-8")
    assert "storage_mode: team-private-repo" in books_text
    assert "vault_location: ''" in books_text
    assert ".mb/private/books/" not in books_text


def test_onboard_partial_threshold_rerun_preserves_existing_tiers(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(onboard_mod, "_which", _tool_path)
    repo = tmp_path / "tier-merge"

    onboard_mod.run(
        path=str(repo),
        name="Tier Merge Co",
        mode="new",
        level="power",
        trivial_max_amount="100",
        small_max_amount="1000",
        material_max_amount="5000",
        strategic_min_amount="5000",
    )
    onboard_mod.run(
        path=str(repo),
        name="Tier Merge Co",
        mode="connect",
        level="power",
        trivial_max_amount="200",
    )

    books_text = (repo / "core" / "finance" / "books.md").read_text(encoding="utf-8")
    assert "trivial:" in books_text
    assert "max_amount: 200" in books_text
    assert "small:" in books_text
    assert "max_amount: 1000" in books_text
    assert "material:" in books_text
    assert "strategic:" in books_text


def test_onboard_yes_does_not_overwrite_existing_team_size(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(onboard_mod, "_which", _tool_path)
    monkeypatch.setattr(onboard_mod, "is_interactive", lambda: False)
    repo = tmp_path / "team"
    onboard_mod.run(path=str(repo), name="Team Co", mode="new", level="power")
    plan = runner.invoke(
        app,
        [
            "onboard",
            "plan",
            "--repo",
            str(repo),
            "--team-size",
            "small-team",
            "--json",
        ],
    )
    assert plan.exit_code == 0

    rerun = runner.invoke(
        app,
        ["onboard", "--yes", "--mode", "connect", "--path", str(repo), "--json"],
    )

    assert rerun.exit_code == 0
    payload = json.loads(rerun.stdout)
    assert payload["onboarding"]["profile"]["team_size"] == "small_team"


def test_status_includes_onboarding_progress(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(onboard_mod, "_which", _tool_path)
    monkeypatch.setattr(status_mod, "_which", _tool_path)
    repo = tmp_path / "acme"
    onboard_mod.run(
        path=str(repo),
        name="Acme",
        mode="new",
        level="power",
        team_size="solo",
        business_type="coaching",
        success_stage="working",
        desired_outcome="usable core files",
    )

    report = status_mod.run(path=str(repo))

    assert report["onboarding"]["summary"]["status"] == "in_progress"
    assert any("Collect just enough" in action for action in report["readiness"]["next_actions"])


def test_onboard_cli_interactive_path_renders_clear_labels(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(onboard_mod, "_which", _tool_path)
    monkeypatch.setattr(onboard_mod, "is_interactive", lambda: True)
    repo = tmp_path / "interactive"

    result = runner.invoke(
        app,
        ["onboard"],
        input=f"beginner\nnew\nInteractive Business\n{repo}\nTaylor Owner\ntaylor-owner\n",
    )

    assert result.exit_code == 0
    assert "Main Branch works because the business lives somewhere durable" in result.stdout
    assert "new/connect/auto" in result.stdout
    assert "repo:" in result.stdout
    assert "interactive" in result.stdout
    assert "level / action: beginner / created" in result.stdout
    assert "path: beginner / created" not in result.stdout
    assert "Connected accounts" in result.stdout
    assert "Outcome" in result.stdout
    assert "CLAUDE.md -> Connected accounts" in result.stdout
    assert "Show the short why" not in result.stdout


def test_onboard_github_create_push_commits_and_sets_tracking(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(onboard_mod, "_which", lambda name: f"/usr/bin/{name}")
    repo = tmp_path / "acme"
    state = {"commit": False, "remote": "", "tracking": "", "staged": False, "dirty": False}
    commands: list[list[str]] = []

    def fake_run(
        args: list[str], cwd: Path | None = None, timeout: float = 5.0
    ) -> dict[str, object]:
        commands.append(args)
        if args[:2] == ["git", "init"]:
            return {"ok": True, "stdout": "", "stderr": "", "returncode": 0}
        if args[:3] == ["git", "rev-parse", "--is-inside-work-tree"]:
            return {"ok": True, "stdout": "true\n", "stderr": "", "returncode": 0}
        if args[:3] == ["git", "branch", "--show-current"]:
            return {"ok": True, "stdout": "main\n", "stderr": "", "returncode": 0}
        if args[:4] == ["git", "config", "--get", "remote.origin.url"]:
            ok = bool(state["remote"])
            return {"ok": ok, "stdout": state["remote"], "stderr": "", "returncode": 0 if ok else 1}
        if args[:5] == ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"]:
            ok = bool(state["tracking"])
            return {
                "ok": ok,
                "stdout": state["tracking"],
                "stderr": "",
                "returncode": 0 if ok else 1,
            }
        if args[:3] == ["git", "rev-parse", "--verify"]:
            return {
                "ok": state["commit"],
                "stdout": "abc123\n" if state["commit"] else "",
                "stderr": "",
                "returncode": 0 if state["commit"] else 1,
            }
        if args[:2] == ["git", "status"]:
            stdout = "?? private.txt\n" if state["dirty"] else ""
            return {"ok": True, "stdout": stdout, "stderr": "", "returncode": 0}
        if args[:2] == ["git", "add"]:
            state["staged"] = True
            return {"ok": True, "stdout": "", "stderr": "", "returncode": 0}
        if args[:3] == ["git", "diff", "--cached"]:
            return {
                "ok": not state["staged"],
                "stdout": "",
                "stderr": "",
                "returncode": 1 if state["staged"] else 0,
            }
        if args[:2] == ["git", "commit"]:
            state["commit"] = True
            state["staged"] = False
            return {"ok": True, "stdout": "", "stderr": "", "returncode": 0}
        if args[:3] == ["gh", "auth", "status"]:
            return {"ok": True, "stdout": "", "stderr": "", "returncode": 0}
        if args[:4] == ["gh", "api", "user", "--jq"]:
            return {"ok": True, "stdout": "dmthepm\n", "stderr": "", "returncode": 0}
        if args[:3] == ["gh", "repo", "create"]:
            state["remote"] = "https://github.com/dmthepm/acme.git\n"
            state["tracking"] = "origin/main\n"
            return {"ok": True, "stdout": "", "stderr": "", "returncode": 0}
        raise AssertionError(args)

    monkeypatch.setattr(onboard_mod, "_run_command", fake_run)

    result = onboard_mod.run(
        path=str(repo),
        name="Acme",
        mode="new",
        level="power",
        github_repo="dmthepm/acme",
        github_visibility="private",
        github_push=True,
    )

    assert result["ok"] is True
    assert result["github"]["ok"] is True
    assert result["github"]["committed"] is True
    assert ["git", "commit", "-m", "[opened] Main Branch scaffold for Acme"] in commands
    add_command = next(cmd for cmd in commands if cmd[:3] == ["git", "add", "--"])
    assert "." not in add_command
    assert "CLAUDE.md" in add_command
    assert ".gitignore" in add_command
    assert ".mb/schema_version" in add_command
    assert result["github"]["pushed"] is True
    assert result["github"]["preflight"]["authenticated_account"] == "dmthepm"
    assert result["github"]["preflight"]["owner_matches_authenticated_account"] is True
    assert result["setup_complete"]["github_requested"] is True
    assert result["setup_complete"]["github_remote_connected"] is True
    assert result["setup_complete"]["pushed_tracking_remote"] is True
    assert "created, saved, synced to GitHub" in result["setup_complete"]["owner_outcome"]
    assert any(cmd[:3] == ["gh", "repo", "create"] and "--private" in cmd for cmd in commands)


def test_onboard_github_push_commits_generated_scaffold_in_repo_with_head(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(onboard_mod, "_which", lambda name: f"/usr/bin/{name}")
    repo = tmp_path / "existing"
    state = {"commit": True, "remote": "", "tracking": "", "staged": False, "dirty": False}
    commands: list[list[str]] = []

    def fake_run(
        args: list[str], cwd: Path | None = None, timeout: float = 5.0
    ) -> dict[str, object]:
        commands.append(args)
        if args[:3] == ["git", "rev-parse", "--is-inside-work-tree"]:
            return {"ok": True, "stdout": "true\n", "stderr": "", "returncode": 0}
        if args[:3] == ["git", "branch", "--show-current"]:
            return {"ok": True, "stdout": "main\n", "stderr": "", "returncode": 0}
        if args[:4] == ["git", "config", "--get", "remote.origin.url"]:
            ok = bool(state["remote"])
            return {"ok": ok, "stdout": state["remote"], "stderr": "", "returncode": 0 if ok else 1}
        if args[:5] == ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"]:
            ok = bool(state["tracking"])
            return {
                "ok": ok,
                "stdout": state["tracking"],
                "stderr": "",
                "returncode": 0 if ok else 1,
            }
        if args[:3] == ["git", "rev-parse", "--verify"]:
            return {"ok": True, "stdout": "abc123\n", "stderr": "", "returncode": 0}
        if args[:2] == ["git", "status"]:
            return {"ok": True, "stdout": "", "stderr": "", "returncode": 0}
        if args[:2] == ["git", "add"]:
            state["staged"] = True
            return {"ok": True, "stdout": "", "stderr": "", "returncode": 0}
        if args[:3] == ["git", "diff", "--cached"]:
            return {
                "ok": not state["staged"],
                "stdout": "",
                "stderr": "",
                "returncode": 1 if state["staged"] else 0,
            }
        if args[:2] == ["git", "commit"]:
            state["staged"] = False
            return {"ok": True, "stdout": "", "stderr": "", "returncode": 0}
        if args[:3] == ["gh", "auth", "status"]:
            return {"ok": True, "stdout": "", "stderr": "", "returncode": 0}
        if args[:4] == ["gh", "api", "user", "--jq"]:
            return {"ok": True, "stdout": "dmthepm\n", "stderr": "", "returncode": 0}
        if args[:3] == ["gh", "repo", "create"]:
            state["remote"] = "https://github.com/dmthepm/existing.git\n"
            state["tracking"] = "origin/main\n"
            return {"ok": True, "stdout": "", "stderr": "", "returncode": 0}
        raise AssertionError(args)

    monkeypatch.setattr(onboard_mod, "_run_command", fake_run)

    result = onboard_mod.run(
        path=str(repo),
        name="Existing",
        mode="new",
        level="power",
        github_repo="dmthepm/existing",
        github_visibility="private",
        github_push=True,
    )

    assert result["ok"] is True
    assert result["github"]["ok"] is True
    assert result["github"]["committed"] is True
    assert any(cmd[:2] == ["git", "commit"] for cmd in commands)
    assert any(cmd[:3] == ["gh", "repo", "create"] for cmd in commands)


def test_onboard_github_push_does_not_sweep_preexisting_untracked_files(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(onboard_mod, "_which", lambda name: f"/usr/bin/{name}")
    repo = tmp_path / "private-folder"
    repo.mkdir()
    (repo / "private-notes.txt").write_text("do not publish\n", encoding="utf-8")
    state = {"commit": False, "remote": "", "tracking": "", "staged": False, "dirty": True}
    commands: list[list[str]] = []

    def fake_run(
        args: list[str], cwd: Path | None = None, timeout: float = 5.0
    ) -> dict[str, object]:
        commands.append(args)
        if args[:3] == ["git", "rev-parse", "--is-inside-work-tree"]:
            return {"ok": True, "stdout": "true\n", "stderr": "", "returncode": 0}
        if args[:3] == ["git", "branch", "--show-current"]:
            return {"ok": True, "stdout": "main\n", "stderr": "", "returncode": 0}
        if args[:4] == ["git", "config", "--get", "remote.origin.url"]:
            return {"ok": False, "stdout": "", "stderr": "", "returncode": 1}
        if args[:5] == ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"]:
            return {"ok": False, "stdout": "", "stderr": "", "returncode": 1}
        if args[:3] == ["git", "rev-parse", "--verify"]:
            return {
                "ok": state["commit"],
                "stdout": "abc123\n" if state["commit"] else "",
                "stderr": "",
                "returncode": 0 if state["commit"] else 1,
            }
        if args[:2] == ["git", "status"]:
            return {"ok": True, "stdout": "?? private-notes.txt\n", "stderr": "", "returncode": 0}
        if args[:2] == ["git", "add"]:
            assert "private-notes.txt" not in args
            assert "." not in args
            state["staged"] = True
            return {"ok": True, "stdout": "", "stderr": "", "returncode": 0}
        if args[:3] == ["git", "diff", "--cached"]:
            return {
                "ok": not state["staged"],
                "stdout": "",
                "stderr": "",
                "returncode": 1 if state["staged"] else 0,
            }
        if args[:2] == ["git", "commit"]:
            state["commit"] = True
            state["staged"] = False
            return {"ok": True, "stdout": "", "stderr": "", "returncode": 0}
        if args[:3] == ["gh", "auth", "status"]:
            return {"ok": True, "stdout": "", "stderr": "", "returncode": 0}
        if args[:4] == ["gh", "api", "user", "--jq"]:
            return {"ok": True, "stdout": "dmthepm\n", "stderr": "", "returncode": 0}
        raise AssertionError(args)

    monkeypatch.setattr(onboard_mod, "_run_command", fake_run)

    result = onboard_mod.run(
        path=str(repo),
        name="Private Folder",
        mode="new",
        level="power",
        github_repo="dmthepm/private-folder",
        github_visibility="private",
        github_push=True,
    )

    assert result["ok"] is False
    assert result["github"]["ok"] is False
    assert any("files Main Branch did not create" in error for error in result["github"]["errors"])
    assert not any(cmd[:3] == ["gh", "repo", "create"] for cmd in commands)


def test_onboard_github_success_uses_reachability_over_stale_auth_status(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(onboard_mod, "_which", lambda name: f"/usr/bin/{name}")
    repo = tmp_path / "reachable"
    state = {"commit": False, "remote": "", "tracking": "", "staged": False}

    def fake_run(
        args: list[str], cwd: Path | None = None, timeout: float = 5.0
    ) -> dict[str, object]:
        if args[:3] == ["git", "rev-parse", "--is-inside-work-tree"]:
            return {"ok": True, "stdout": "true\n", "stderr": "", "returncode": 0}
        if args[:3] == ["git", "branch", "--show-current"]:
            return {"ok": True, "stdout": "main\n", "stderr": "", "returncode": 0}
        if args[:4] == ["git", "config", "--get", "remote.origin.url"]:
            ok = bool(state["remote"])
            return {"ok": ok, "stdout": state["remote"], "stderr": "", "returncode": 0 if ok else 1}
        if args[:5] == ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"]:
            ok = bool(state["tracking"])
            return {
                "ok": ok,
                "stdout": state["tracking"],
                "stderr": "",
                "returncode": 0 if ok else 1,
            }
        if args[:3] == ["git", "rev-parse", "--verify"]:
            return {
                "ok": state["commit"],
                "stdout": "abc123\n" if state["commit"] else "",
                "stderr": "",
                "returncode": 0 if state["commit"] else 1,
            }
        if args[:2] == ["git", "status"]:
            return {"ok": True, "stdout": "", "stderr": "", "returncode": 0}
        if args[:2] == ["git", "add"]:
            state["staged"] = True
            return {"ok": True, "stdout": "", "stderr": "", "returncode": 0}
        if args[:3] == ["git", "diff", "--cached"]:
            return {
                "ok": not state["staged"],
                "stdout": "",
                "stderr": "",
                "returncode": 1 if state["staged"] else 0,
            }
        if args[:2] == ["git", "commit"]:
            state["commit"] = True
            state["staged"] = False
            return {"ok": True, "stdout": "", "stderr": "", "returncode": 0}
        if args[:3] == ["gh", "auth", "status"]:
            return {"ok": False, "stdout": "", "stderr": "stale auth", "returncode": 1}
        if args[:4] == ["gh", "api", "user", "--jq"]:
            return {"ok": True, "stdout": "dmthepm\n", "stderr": "", "returncode": 0}
        if args[:3] == ["gh", "repo", "create"]:
            state["remote"] = "https://github.com/dmthepm/reachable.git\n"
            state["tracking"] = "origin/main\n"
            return {"ok": True, "stdout": "", "stderr": "", "returncode": 0}
        if args[:3] == ["gh", "repo", "view"]:
            return {
                "ok": True,
                "stdout": '{"nameWithOwner":"dmthepm/reachable"}\n',
                "stderr": "",
                "returncode": 0,
            }
        raise AssertionError(args)

    monkeypatch.setattr(onboard_mod, "_run_command", fake_run)

    result = onboard_mod.run(
        path=str(repo),
        name="Reachable",
        mode="new",
        level="auto",
        github_repo="dmthepm/reachable",
        github_visibility="private",
        github_push=True,
    )

    assert result["ok"] is True
    assert result["tools"]["github_cli"]["authenticated"] is True
    assert result["tools"]["github_cli"]["state"] == "ready_reachable"
    assert not any("gh auth login" in warning for warning in result["warnings"])


def test_onboard_cli_github_push_fixture_leaves_generated_mb_state_clean(
    tmp_path: Path, monkeypatch
) -> None:
    if not shutil.which("git"):
        pytest.skip("git is required for the fixture push smoke")

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_gh = fake_bin / "gh"
    remote = tmp_path / "remote.git"
    fake_gh.write_text(
        """#!/usr/bin/env python3
import json
import os
import subprocess
import sys

args = sys.argv[1:]
remote = os.environ["MB_TEST_REMOTE"]

if args[:2] == ["auth", "status"]:
    sys.exit(0)
if args[:4] == ["api", "user", "--jq", ".login"]:
    print("fixture-owner")
    sys.exit(0)
if args[:2] == ["repo", "view"]:
    print(json.dumps({{"nameWithOwner": args[2]}}))
    sys.exit(0)
if args[:2] == ["repo", "create"]:
    full_name = args[2]
    if not os.path.exists(remote):
        subprocess.run(["git", "init", "--bare", remote], check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["git", "remote", "remove", "origin"], stderr=subprocess.DEVNULL)
    subprocess.run(["git", "remote", "add", "origin", remote], check=True)
    if "--push" in args:
        subprocess.run(["git", "push", "-u", "origin", "main"], check=True)
    subprocess.run(
        ["git", "remote", "set-url", "origin", "https://github.com/" + full_name + ".git"],
        check=True,
    )
    sys.exit(0)

print("unexpected gh command: " + " ".join(args), file=sys.stderr)
sys.exit(2)
""",
        encoding="utf-8",
    )
    fake_gh.chmod(0o755)
    monkeypatch.setenv("PATH", str(fake_bin) + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setenv("MB_TEST_REMOTE", str(remote))
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Main Branch Test")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "test@example.com")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Main Branch Test")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "test@example.com")
    monkeypatch.setattr(onboard_mod, "is_interactive", lambda: False)
    repo = tmp_path / "acme"

    result = runner.invoke(
        app,
        [
            "onboard",
            "--yes",
            "--name",
            "Acme",
            "--path",
            str(repo),
            "--github",
            "fixture-owner/acme",
            "--push",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["github"]["ok"] is True
    assert payload["github"]["committed"] is True
    assert payload["github"]["pushed"] is True
    assert payload["github"]["preflight"]["authenticated_account"] == "fixture-owner"
    assert payload["setup_complete"]["committed_with_durable_files"] is True
    assert payload["setup_complete"]["pushed_tracking_remote"] is True
    assert ".mb/schema_version" in " ".join(payload["github"]["commands"])

    status = subprocess.run(
        ["git", "status", "--short"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    assert status.stdout == ""
    schema_history = subprocess.run(
        ["git", "log", "--oneline", "--", ".mb/schema_version"],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    assert schema_history.stdout.strip()


def test_onboard_budget_band_without_thresholds_warns(tmp_path: Path, monkeypatch) -> None:
    # #880 item 2: a recorded budget band with no thresholds and no private
    # choice must say what's still missing, not stay silently todo.
    monkeypatch.setattr(onboard_mod, "_which", _tool_path)
    repo = tmp_path / "acme"

    result = onboard_mod.run(
        path=str(repo),
        name="Acme Brewing",
        mode="new",
        monthly_experiment_budget_band="500-2k",
    )

    assert any(
        "MoneyPath thresholds are still" in w and "trivial/small/material" in w
        for w in result["warnings"]
    )


def test_onboard_budget_band_with_private_choice_is_quiet(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(onboard_mod, "_which", _tool_path)
    repo = tmp_path / "acme"

    result = onboard_mod.run(
        path=str(repo),
        name="Acme Brewing",
        mode="new",
        monthly_experiment_budget_band="500-2k",
        threshold_privacy="private",
    )

    assert not any("MoneyPath thresholds are still" in w for w in result["warnings"])


def test_onboard_budget_band_with_amounts_is_quiet(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(onboard_mod, "_which", _tool_path)
    repo = tmp_path / "acme"

    result = onboard_mod.run(
        path=str(repo),
        name="Acme Brewing",
        mode="new",
        monthly_experiment_budget_band="500-2k",
        trivial_max_amount="50",
        small_max_amount="200",
        material_max_amount="1000",
    )

    assert not any("MoneyPath thresholds are still" in w for w in result["warnings"])
