"""``mb init`` scaffolds the canonical business folders + CLAUDE.md."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mb import codex as codex_mod
from mb import init as init_mod
from mb.init import _DEFAULT_CLAUDE, DATA_FOLDERS, _read_template, run


def _section(text: str, start: str, end: str) -> str:
    start_index = text.index(start)
    end_index = text.index(end, start_index)
    return text[start_index:end_index]


def _normalize(text: str) -> str:
    return " ".join(text.split())


def _assert_claude_md_cli_first_contract(text: str) -> None:
    normalized = _normalize(text)
    assert "## Claude operating contract" in text
    assert "Main Branch CLI facts are the source of truth" in text
    assert "run `claude`" in text
    assert "`/mb-start` inside Claude Code" in text
    # Hybrid plugin rail (Stage 3 / #924): the plugin is durable across Claude
    # Desktop + terminal, while the project-local bridge preserves the friendly
    # `/mb-start` user command.
    assert "claude plugin marketplace add noontide-co/mainbranch" in text
    assert "normal user command stays `/mb-start`" in text
    assert "/mainbranch:mb-start" in text
    assert "plugin smoke/diagnostic command" in text
    assert "Claude Desktop" in text
    assert "mb start --launch" in text
    assert "mb --version" in text
    assert "mb status --json --peek" in text
    assert "MoneyPath" in text
    assert "mb start --json" in text
    assert "mb doctor repair --plan" in text
    assert "Do not replace those facts with ad hoc shell" in text
    assert "inspection unless `mb` says a section is unavailable" in text
    assert "Read-only commands can be run without asking first" in text
    assert "require explicit operator approval before applying" in text
    assert "mb skill repair --repo ." in text
    assert "mb skill link --repo .          # writes project-local Claude skill wiring" in text
    assert "mb skill repair --repo . --apply" in text
    assert "mb doctor repair --apply" in text
    assert "## First-run setup intent" in text
    assert "setup intent, not as a document to save" in normalized
    assert "pipx install mainbranch" in normalized
    assert "gh auth status" in normalized
    assert "gh api user --jq .login" in normalized
    assert "GitHub is strongly recommended" in normalized
    assert "connector-friendly copy of the business brain" in normalized
    assert "business brain" in normalized
    assert "If `/mb-start` is not discoverable" in text
    assert "restart Claude Code from this repo and try" in text
    assert "business-owner language" in text
    assert "bets, goals, offers, pushes" in text
    assert "playbooks, outcomes" in text
    assert "`working tree: clean`" in text
    assert "nothing unsaved locally" in text
    assert "`branch: main`" in text
    assert "current business" in text
    assert "`No origin remote`" in text
    assert "no connected GitHub backup" in text
    assert "`PR and issue facts`" in text
    assert "GitHub task and proposal context" in text
    # CLAUDE.md is the Claude-runtime contract; Codex has its own AGENTS.md,
    # and other runtimes remain roadmap — keep them out of this file.
    for unsupported_runtime in ("Codex", "Cursor", "OpenClaw", "Hermes"):
        assert unsupported_runtime not in text


def _assert_claude_md_primitive_routing_contract(text: str) -> None:
    assert "## Business primitive routing" in text
    assert "Offer: what the business sells or may sell repeatedly" in text
    assert "Bet: a time-boxed wager" in text
    assert "Push: coordinated work" in text
    assert "Reusable playbook: an engine recipe" in text
    assert "Push playbook: this push's approval" in text
    assert "Proof: evidence that a claim is true" in text
    assert "Use MoneyPath from" in text
    assert "`mb status --json --peek` for routing" in text
    assert "legible," in text
    assert "supported, connected, and instrumented" in text
    assert "single-offer repo, `core/offer.md` is the durable offer truth" in text
    assert "multi-offer repo, `core/offer.md` is the portfolio thesis" in text
    assert "`core/offers/<slug>/offer.md` holds per-offer truth" in text
    assert "Company-wide proof belongs" in text
    assert "`core/proof/`" in text
    assert "offer-specific proof belongs in `core/offers/<slug>/proof/`" in text
    assert "Use standard proof files such as `testimonials.md`" in text
    assert "`permissioned_public: false`" in text
    assert "`money_path.objects.proof.quality.public_marketing.status` is `blocked`" in text
    assert "`typicality.md`" in text
    assert "`angles/`" in text
    assert "Content strategy starts at `core/content-strategy.md`" in text
    assert "`core/marketing/channels/<channel>.md`" in text
    assert "`core/marketing/accounts/<platform>-<account>.md`" in text
    assert "`core/people/<person>.md`" in text
    assert "A live idea can be both a bet and an offer candidate" in text
    assert "Do not rename, delete, merge, split, or move offer folders" in text
    assert "domain rubric" not in text.lower()


def _assert_agents_md_codex_start_contract(text: str) -> None:
    normalized = _normalize(text)
    assert "## Codex Operating Contract" in text
    assert "<!-- mainbranch:codex-guidance " in text
    assert "template_hash=" in text
    assert "min_mb=" in text
    assert "This file is managed by Main Branch" in text
    assert "This guidance was generated by Main Branch" not in text
    assert "Do not pretend Claude" in text
    assert "global Main Branch skill route" in text
    assert "## Codex Lifecycle Workflow Index" in text
    assert "repo-level Codex bootstrap" in text
    assert "skill bundle is installed globally once per user" in text
    assert "repo-local plugin or skill" in text
    assert "copies" in text
    assert "Use the global Main Branch skills" in text
    assert "`runtime.codex_cli.status` is `runtime_mismatch`" in text
    assert "`codex_runtime_mb_mismatch`" in text
    assert "Start the day / what next / get oriented" in text
    assert "routes `mb-*`" in text
    assert "Inspect status / what changed / what is stale" in text
    assert "Think / research / decide / codify" in text
    assert "route to the matching global" in text
    assert "Do not claim full Codex workflow parity" in text
    assert "## Codex Start Workflow" in text
    assert "This is the Codex-native start workflow" in text
    assert "## Codex Status Workflow" in text
    assert "This is the Codex-native status workflow" in text
    assert "since_last_check" in text
    assert "## Codex Think Route" in text
    assert "existing `mb-think` shared workflow" in text
    assert "smallest honest research depth" in text
    assert "mb checkpoint --plan --json" in text
    assert "mb status --json --peek" in text
    assert "mb start --json" in text
    assert "mb doctor repair --plan" in text
    assert "explicit operator approval" in text
    assert "## First-run setup intent" in text
    assert "setup intent, not as a document to save" in normalized
    assert "pipx install mainbranch" in normalized
    assert "gh auth status" in normalized
    assert "gh api user --jq .login" in normalized
    assert "GitHub is strongly recommended" in normalized
    assert "connector-friendly copy of the business brain" in normalized
    assert "business brain" in normalized
    assert "business-owner language" in text
    assert "bets, goals, offers, pushes" in text
    assert "`working tree: clean`" in text
    assert "nothing unsaved locally" in text
    assert "`branch: main`" in text
    assert "current business" in text
    assert "`No origin remote`" in text
    assert "no connected GitHub backup" in text
    assert "`PR and issue facts`" in text
    assert "GitHub task and proposal context" in text
    assert "created, saved, synced to GitHub when requested" in text
    assert "short technical receipt" in text
    assert "`vocabulary` block from `mb status --json --peek`" in text
    assert "MoneyPath" in text
    assert "Use `money_path` when the next move depends on customer progress" in text
    assert "`permissioned_public: false`" in text
    assert "current paths, frontmatter, JSON keys" in text
    assert "If `ranked_actions` has entries" in text
    assert "Do not pretend" in text


def test_default_claude_operating_contract_matches_template() -> None:
    template = _read_template("CLAUDE.md.tmpl")
    template_contract = _section(template, "## Claude operating contract", "## Folders")
    fallback_contract = _section(_DEFAULT_CLAUDE, "## Claude operating contract", "## Folders")

    assert fallback_contract == template_contract
    _assert_claude_md_cli_first_contract(_DEFAULT_CLAUDE)
    _assert_claude_md_primitive_routing_contract(_DEFAULT_CLAUDE)


def test_business_repo_templates_load_entry_rules_once() -> None:
    agents = _read_template("AGENTS.md.tmpl")
    claude = _read_template("CLAUDE.md.tmpl")
    heading = "## Trials and readouts"
    for template in (agents, claude):
        assert template.count(heading) == 1
        assert "check existing bets first and reuse the matching bet" in template
        assert "summarized numbers, source, timeframe" in template
        assert "linked_decisions` and `linked_research" in template
        assert "For a status-only question, answer it" in template
        assert "Ask for approval before any write" in template
        assert "account IDs, or exported tables" in template
    assert "<!-- mainbranch:entry-rules:begin -->" in claude
    assert "<!-- mainbranch:entry-rules:end -->" in claude


def test_init_scaffolds_folders(tmp_path: Path) -> None:
    target = tmp_path / "acme"
    result = run(path=str(target), name="Acme Brewing")
    assert result["status"] == "ok"
    for folder in DATA_FOLDERS:
        assert (target / folder).is_dir(), f"missing {folder}"
    assert not (target / "reference").exists()
    assert (target / "core" / "proof").is_dir()
    assert (target / "core" / "brand").is_dir()
    assert (target / "core" / "marketing").is_dir()
    assert (target / "core" / "marketing" / "channels").is_dir()
    assert (target / "core" / "marketing" / "accounts").is_dir()
    assert (target / "core" / "team").is_dir()
    team_files = list((target / "core" / "team").glob("*.md"))
    assert len(team_files) == 1
    assert "type: team_member" in team_files[0].read_text(encoding="utf-8")
    assert (target / "core" / "people").is_dir()
    assert (target / "core" / "strategy").is_dir()
    assert (target / "core" / "operations").is_dir()
    assert (target / "bets").is_dir()
    # Canonical primitive is `pushes/`; legacy `campaigns/` is not scaffolded.
    assert (target / "pushes").is_dir()
    assert not (target / "campaigns").exists()
    # Operator vocabulary is an optional file scaffolded by init.
    assert (target / "core" / "vocabulary.md").exists()
    vocab = (target / "core" / "vocabulary.md").read_text(encoding="utf-8")
    assert "type: vocabulary" in vocab
    assert "terms:" in vocab
    assert "singular: push" in vocab
    assert (target / "CLAUDE.md").exists()
    assert (target / "README.md").exists()
    assert (target / "AGENTS.md").exists()
    assert not (target / ".agents" / "plugins").exists()
    assert not (target / ".agents" / "skills" / "main-branch-owner-loop").exists()
    assert (target / ".github" / "CODEOWNERS").exists()
    assert (target / ".gitignore").exists()
    assert (target / ".mb" / "schema_version").read_text(encoding="utf-8") == "0.2\n"
    assert (target / ".claude" / "settings.local.json").exists()
    assert (target / ".claude" / "skills" / "mb-start" / "SKILL.md").exists()
    assert (target / ".git" / "hooks" / "commit-msg").exists()
    hook = (target / ".git" / "hooks" / "commit-msg").read_text(encoding="utf-8")
    assert "MB_BIN=" in hook
    assert '"$MB_CHECKPOINT" checkpoint --validate -' in hook
    assert result["checkpoint_hook"]["state"] == "installed"

    settings = json.loads((target / ".claude" / "settings.local.json").read_text())
    dirs = settings["permissions"]["additionalDirectories"]
    assert dirs
    assert (Path(dirs[0]) / ".claude" / "skills" / "mb-start" / "SKILL.md").exists()

    gitignore = (target / ".gitignore").read_text()
    assert ".claude/settings.local.json" in gitignore
    assert ".claude/worktrees/" in gitignore
    assert ".claude/skills/mb-start" in gitignore
    assert ".mb/private/" in gitignore
    assert ".mb/backups/" in gitignore
    assert ".mb/connect.yaml" in gitignore
    assert ".mb/onboarding.json" in gitignore
    assert ".mb/issue-drafts/" in gitignore
    assert "*.journal" in gitignore
    assert "*.hledger" in gitignore
    assert "*.ledger" in gitignore
    assert "*.beancount" in gitignore
    assert ".vip/local.yaml" in gitignore
    claude_md = (target / "CLAUDE.md").read_text()
    agents_md = (target / "AGENTS.md").read_text()
    readme_md = (target / "README.md").read_text()
    assert "Acme Brewing" in claude_md
    assert "Acme Brewing" in agents_md
    assert "Acme Brewing" in readme_md
    assert "/mb-start" in readme_md
    assert "Codex CLI" in readme_md
    assert "mb doctor repair --apply --only codex" in readme_md
    codex_readme = readme_md.split("Or, in Codex CLI:", 1)[1]
    assert "global `mb-start` skill" in codex_readme
    assert "/mb-start" not in codex_readme
    assert "## Save, Checkpoint, Backup" in readme_md
    assert "A checkpoint is an approved saved point" in readme_md
    assert "GitHub backup/sync is strongly recommended" in readme_md
    assert ".mb/onboarding.json" in readme_md
    assert "## Connected accounts" in claude_md
    assert "Stripe account IDs" in claude_md
    assert "Google Ads customer IDs" in claude_md
    assert "MCP server names" in claude_md
    assert "MCP tokens" in claude_md
    assert "Never commit API keys" in claude_md
    assert "`bets/`" in claude_md
    # CLAUDE.md teaches the canonical push primitive and the optional
    # vocabulary file without carrying retired folder vocabulary into every
    # fresh repo.
    assert "`pushes/`" in claude_md
    assert "core/vocabulary.md" in claude_md
    retired_generated_terms = (
        "reference/core",
        "reference/offers",
        "reference/domain",
        "campaigns/",
        "outputs/",
        "ship-bet",
        "weekly-review",
    )
    for term in retired_generated_terms:
        assert term not in claude_md
        assert term not in agents_md
    _assert_claude_md_cli_first_contract(claude_md)
    _assert_claude_md_primitive_routing_contract(claude_md)
    _assert_agents_md_codex_start_contract(agents_md)
    assert codex_mod.instructions_status(target)["ok"] is True


def test_init_preserves_existing_gitignore_and_codeowners(tmp_path: Path) -> None:
    target = tmp_path / "existing"
    (target / ".github").mkdir(parents=True)
    (target / ".gitignore").write_text("custom-ignore\n", encoding="utf-8")
    (target / ".github" / "CODEOWNERS").write_text("* @existing\n", encoding="utf-8")

    result = run(path=str(target), name="Existing Business")

    assert result["status"] == "ok"
    gitignore = (target / ".gitignore").read_text(encoding="utf-8")
    assert gitignore.startswith("custom-ignore\n")
    assert "# Main Branch local Claude wiring" in gitignore
    assert (target / ".github" / "CODEOWNERS").read_text(encoding="utf-8") == "* @existing\n"
    assert ".github/CODEOWNERS" not in result["created"]


def test_codex_agents_repair_preserves_operator_content(tmp_path: Path) -> None:
    target = tmp_path / "biz"
    target.mkdir()
    (target / "AGENTS.md").write_text(
        "# Operator Notes\n\nKeep this local note.\n", encoding="utf-8"
    )

    result = codex_mod.write_agents_md(target, name="Acme")

    text = (target / "AGENTS.md").read_text(encoding="utf-8")
    assert result["changed"] is True
    assert text.startswith(codex_mod.AGENTS_MANAGED_BEGIN)
    assert codex_mod.AGENTS_MANAGED_END in text
    assert "# Operator Notes\n\nKeep this local note.\n" in text
    assert "<!-- mainbranch:codex-guidance " in text
    assert codex_mod.instructions_status(target)["ok"] is True


def test_init_defaults_owner_name_without_local_git_identity(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("MB_OWNER_NAME", "")
    monkeypatch.setattr(init_mod, "_gh_username", lambda: "MixedCaseUser")
    target = tmp_path / "acme"

    result = run(path=str(target), name="Acme Brewing")

    assert result["status"] == "ok"
    owner_file = target / "core" / "team" / "mixedcaseuser.md"
    assert owner_file.exists()
    text = owner_file.read_text(encoding="utf-8")
    assert "name: Business Owner" in text
    assert "preferred_name: Business Owner" in text
    assert "  - mixedcaseuser" in text


def test_init_uses_explicit_owner_name_env_override(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MB_OWNER_NAME", "Env Owner")
    monkeypatch.setattr(init_mod, "_gh_username", lambda: "")
    target = tmp_path / "acme"

    result = run(path=str(target), name="Acme Brewing")

    assert result["status"] == "ok"
    # No real handle anywhere → the file slugs from the owner's name, not
    # from the your-gh-username placeholder.
    owner_file = target / "core" / "team" / "env-owner.md"
    assert owner_file.exists()
    assert "name: Env Owner" in owner_file.read_text(encoding="utf-8")


def test_init_without_github_identity_never_probes_gh(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MB_OWNER_NAME", "")

    def _explode() -> str:
        raise AssertionError("gh login probed despite infer_github_identity=False")

    monkeypatch.setattr(init_mod, "_gh_username", _explode)
    target = tmp_path / "acme"

    result = run(
        path=str(target),
        name="Acme Brewing",
        owner_name="Riley Quinn",
        infer_github_identity=False,
    )

    assert result["status"] == "ok"
    owner_file = target / "core" / "team" / "riley-quinn.md"
    assert owner_file.exists()
    text = owner_file.read_text(encoding="utf-8")
    assert "name: Riley Quinn" in text
    assert "your-gh-username" in text
    codeowners = (target / ".github" / "CODEOWNERS").read_text(encoding="utf-8")
    assert "@your-gh-username" in codeowners


def test_init_explicit_owner_github_skips_probe_even_when_inference_off(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(
        init_mod,
        "_gh_username",
        lambda: (_ for _ in ()).throw(AssertionError("probe must not run")),
    )
    target = tmp_path / "acme"

    result = run(
        path=str(target),
        name="Acme Brewing",
        owner_github="riley-gh",
        infer_github_identity=False,
    )

    assert result["status"] == "ok"
    assert (target / "core" / "team" / "riley-gh.md").exists()


def test_init_idempotent(tmp_path: Path) -> None:
    target = tmp_path / "acme"
    first = run(path=str(target), name="Acme")
    second = run(path=str(target), name="Acme")
    assert first["status"] == "ok"
    assert second["status"] == "already-initialized"
    assert second["checkpoint_hook"]["state"] == "installed"


def test_init_requires_name(tmp_path: Path, monkeypatch) -> None:
    # Force input() to raise EOFError, simulating no TTY.
    monkeypatch.setattr("builtins.input", lambda _: (_ for _ in ()).throw(EOFError()))
    target = tmp_path / "noname"
    result = run(path=str(target), name="")
    assert result["status"] == "error"


def test_init_wires_plugin_by_default(tmp_path: Path) -> None:
    # Stage 3 (decision 2026-06-10): plugin is the primary cross-surface rail;
    # a fresh repo must be wired by default, not symlink-only.
    from mb import engine as engine_mod

    target = tmp_path / "acme"
    result = run(path=str(target), name="Acme")
    assert result["status"] == "ok"
    assert result["plugin_wiring"]["ok"] is True
    status = engine_mod.plugin_wiring_status(target)
    assert status["wired"] is True
    assert status["marketplace_known"] is True
    assert status["plugin_enabled"] is True
    # Tracked settings (committed), not the gitignored local file.
    assert (target / ".claude" / "settings.json").exists()
    assert ".claude/settings.json" in result["created"]


def test_init_already_initialized_backfills_plugin_wiring(tmp_path: Path) -> None:
    from mb import engine as engine_mod

    target = tmp_path / "acme"
    run(path=str(target), name="Acme")
    # Simulate a symlink-era repo: drop the plugin wiring, keep CLAUDE.md.
    (target / ".claude" / "settings.json").unlink()
    second = run(path=str(target), name="Acme")
    assert second["status"] == "already-initialized"
    assert engine_mod.plugin_wiring_status(target)["wired"] is True
    assert ".claude/settings.json" in second["created"]


def _status_lines(claude_md: str) -> dict[str, set[str]]:
    """The `status:` sets the CLAUDE.md conventions name, keyed by file type."""
    conventions = _section(claude_md, "## Conventions", "\n## ")
    found: dict[str, set[str]] = {}
    for line in conventions.splitlines():
        label, sep, rest = line.strip().removeprefix("- ").partition(": `")
        if sep and rest.endswith("`"):
            found[label] = {value.strip() for value in rest[:-1].split("|")}
    return found


@pytest.mark.parametrize("source", ["template", "fallback"])
def test_init_claude_md_status_values_match_mb_validate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source: str
) -> None:
    # #1119: one status set for every file type taught agents that `running`
    # is a bet status; `mb validate` rejects it. Each type's set comes from
    # the schema `mb validate` checks.
    from mb.validate import SCHEMAS

    if source == "fallback":
        real = init_mod._read_template
        monkeypatch.setattr(
            init_mod,
            "_read_template",
            lambda name: "" if name == "CLAUDE.md.tmpl" else real(name),
        )
    target = tmp_path / "acme"
    assert run(path=str(target), name="Acme Brewing")["status"] == "ok"
    text = (target / "CLAUDE.md").read_text(encoding="utf-8")

    assert "{{" not in text
    assert "Status field" not in text
    assert _status_lines(text) == {
        "Bets": set(SCHEMAS["bets"]["enums"]["status"]),
        "Decisions": set(SCHEMAS["decisions"]["enums"]["status"]),
        "Offers": set(SCHEMAS["core/offers"]["enums"]["status"]),
        "Pushes": set(SCHEMAS["pushes"]["enums"]["status"]),
        "Push playbooks": set(SCHEMAS["push-playbooks"]["enums"]["status"]),
    }
    assert "`mb validate` names the" in text
    # #1122: the lead-in names exactly the types it lists, not "each file type".
    assert "Each file type" not in text
    conventions = _section(text, "## Conventions", "\n## ")
    before_names = conventions.split("`mb validate` names")[0]
    lead_in = " ".join(before_names[before_names.rindex("\n- ") :].split())
    listed = {
        part.strip(" -")
        for part in lead_in.lower().replace(" and ", ", ").split("each")[0].split(",")
    }
    assert listed == {label.lower() for label in _status_lines(text)}
    assert lead_in.endswith("each have their own `status:` values;")


def test_every_status_enum_schema_is_listed_or_excluded() -> None:
    # #1133: the drift test above compares the lead-in with the list, and both come
    # from STATUS_CONVENTION_SCHEMAS, so a new constrained type would go unseen.
    from mb.validate import SCHEMAS

    listed = {schema for _, schema in init_mod.STATUS_CONVENTION_SCHEMAS}
    excluded = set(init_mod.STATUS_CONVENTION_EXCLUDED)
    assert not listed & excluded
    constrained = {name for name, spec in SCHEMAS.items() if "status" in spec["enums"]}
    assert constrained == listed | excluded
    assert all(init_mod.STATUS_CONVENTION_EXCLUDED.values())


def test_a_new_status_enum_schema_fails_the_coverage_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from mb import validate

    monkeypatch.setitem(
        validate.SCHEMAS,
        "brand-new",
        {"glob": "x/*.md", "required": [], "enums": {"status": {"a"}}},
    )
    with pytest.raises(AssertionError):
        test_every_status_enum_schema_is_listed_or_excluded()
