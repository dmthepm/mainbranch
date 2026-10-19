"""Acceptance checks for books routing and the close simulation fixture."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from typer.testing import CliRunner

from mb import __version__, codex, dogfood_harness, init, release_simulation, skill_validate
from mb.cli import app

ROOT = Path(__file__).resolve().parents[2]
BASE_CLAUDE_SHA256 = "e8cdcbd134956f9538d56eb3240444a143810ea82a932abd234246bbf83b5ad5"
BASE_AGENTS_SHA256 = "e7ec06820c3aee359759bef6b91493747e666e235a73996763004875c88389ea"
BASE_MANIFEST_SHA256 = "c61fd488de25e59e4326aea0dbb93bb181924d601a2279437d6518c79dc798d5"


def _base_template(path: str, digest: str) -> str:
    current = (ROOT / path).read_text()
    added = [line for line in current.splitlines(keepends=True) if "mb-books" in line]
    assert len(added) == 1
    base = current.replace(added[0], "", 1)
    assert hashlib.sha256(base.encode()).hexdigest() == digest
    return base


def _simulation() -> release_simulation.Simulation:
    return next(sim for sim in release_simulation.simulations() if sim.id == "books-close")


def _materialize(tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "source-business"
    result = init.run(str(source), "Fixture Business", infer_github_identity=False)
    assert result["status"] == "ok"
    subprocess.run(["git", "init", "-q", str(source)], check=True)
    subprocess.run(["git", "add", "-A"], cwd=source, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Fixture Author",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-q",
            "-m",
            "Fixture baseline",
        ],
        cwd=source,
        check=True,
    )
    state = dogfood_harness.HarnessState(
        engine_repo=ROOT,
        root=tmp_path,
        evidence_dir=tmp_path / "evidence",
        fixture_repo=source,
        mb_path=Path(sys.executable).parent / "mb",
    )
    state.evidence_dir.mkdir()
    record = dogfood_harness.materialize_fixture_profile(state, _simulation())
    assert record["mutations"]
    return Path(record["repo"]), tmp_path / "books"


def test_e1_router_names_mb_books_for_books_intents() -> None:
    body = (ROOT / ".claude/skills/mb-start/SKILL.md").read_text()
    paragraph = body.split("**Books/finance routing:**", 1)[1].split("**Slug/", 1)[0]
    for token in ("/mb-books", "mb books check", "restricted", "local_only", "storage_mode"):
        assert token in paragraph
    assert "/mb-books" in body.split("## Intent Keywords", 1)[1].split("---", 1)[0]
    router = (ROOT / ".claude/skills/mb-start/references/router-and-language.md").read_text()
    section = router.split("### Bookkeeping, books, finance, accounting", 1)[1].split(
        "### Provider and tool setup", 1
    )[0]
    for token in ("/mb-books", "monthly close", "reconcil", "CPA handoff"):
        assert token in section


def test_e2_mb_books_description_triggers_on_close() -> None:
    body = (ROOT / ".claude/skills/mb-books/SKILL.md").read_text()
    description = re.search(r"^description: (.+)$", body, re.M)
    assert description is not None
    assert len(description.group(1)) <= 400
    for token in ("close", "reconcil", "cpa", "setup", "mb books check", "mb books doctor"):
        assert token in description.group(1).lower()
    report = skill_validate.run("mb-books")
    assert report is not None and report["ok"]
    assert len(body.splitlines()) <= 300
    assert len((ROOT / ".claude/skills/mb-start/SKILL.md").read_text().splitlines()) <= 500


def test_e3_generated_guidance_names_mb_books(tmp_path: Path) -> None:
    repo = tmp_path / "business"
    assert init.run(str(repo), "Fixture Business", infer_github_identity=False)["status"] == "ok"
    claude = (repo / "CLAUDE.md").read_text()
    agents = (repo / "AGENTS.md").read_text()
    assert "/mb-books" in claude
    assert "mb-books" in agents
    mapping = {
        "BUSINESS_NAME": "Fixture Business",
        "GH_USERNAME": "your-gh-username",
        "OWNER_NAME": "Business Owner",
        "OWNER_SLUG": "business-owner",
        "STATUS_CONVENTIONS": init.status_conventions(),
    }
    base_claude = init._render(
        _base_template("mb/mb/_data/templates/CLAUDE.md.tmpl", BASE_CLAUDE_SHA256), mapping
    )
    base_agents = codex._render(
        _base_template("mb/mb/_data/templates/AGENTS.md.tmpl", BASE_AGENTS_SHA256),
        {
            "BUSINESS_NAME": "Fixture Business",
            "GH_USERNAME": "your-gh-username",
            "MAINBRANCH_VERSION": __version__,
            "CODEX_GUIDANCE_METADATA": codex.guidance_metadata_comment(),
        },
    )
    for current, base in ((claude, base_claude), (agents, base_agents)):
        current = current.replace(codex.AGENTS_MANAGED_BEGIN + "\n", "").replace(
            codex.AGENTS_MANAGED_END + "\n", ""
        )
        added = [line for line in current.splitlines() if line not in base.splitlines()]
        removed = [line for line in base.splitlines() if line not in current.splitlines()]
        assert added and all("mb-books" in line for line in added)
        assert not removed


def test_e4_books_repo_fixture_materializes(tmp_path: Path) -> None:
    business, books = _materialize(tmp_path)
    assert "books_repo: ../books" in (business / "core/finance/books.md").read_text()
    assert books.is_dir() and books.parent == tmp_path
    assert business.resolve().is_relative_to(tmp_path.resolve())
    assert books.resolve().is_relative_to(tmp_path.resolve())
    assert (
        subprocess.check_output(["git", "rev-list", "--count", "HEAD"], cwd=books).strip() != b"0"
    )
    for name in ("README.md", "AGENTS.md", "2026.journal", "books.toml"):
        assert "MB-FIXTURE" in (books / name).read_text()[:1024]
    runner = CliRunner()
    explicit = runner.invoke(app, ["books", "doctor", "--repo", str(books), "--json"])
    previous = Path.cwd()
    try:
        os.chdir(business)
        configured = runner.invoke(app, ["books", "doctor", "--json"])
    finally:
        os.chdir(previous)
    assert explicit.exit_code in (0, 1)
    assert configured.exit_code in (0, 1)
    explicit_report = json.loads(explicit.output)
    configured_report = json.loads(configured.output)
    for report in (explicit_report, configured_report):
        assert not {"entrypoint_missing", "accounts_untyped", "evidence_tracked"} & {
            finding["rule"] for finding in report["findings"]
        }
    assert explicit_report["findings"] == configured_report["findings"]


def test_e5_books_close_uses_books_repo_fixture(tmp_path: Path) -> None:
    path = "mb/mb/_data/release_simulations/manifest.json"
    current_text = (ROOT / path).read_text()
    assert current_text.count('"fixture_profile": "books_repo_fixture"') == 1
    base_text = current_text.replace(
        '"fixture_profile": "books_repo_fixture"',
        '"fixture_profile": "fresh_sanitized_business_repo"',
        1,
    )
    assert hashlib.sha256(base_text.encode()).hexdigest() == BASE_MANIFEST_SHA256
    current = json.loads(current_text)
    base = json.loads(base_text)
    current_by_id = {sim["id"]: sim for sim in current["simulations"]}
    base_by_id = {sim["id"]: sim for sim in base["simulations"]}
    assert current_by_id.keys() == base_by_id.keys()
    assert current_by_id["books-close"]["fixture_profile"] == "books_repo_fixture"
    for sim_id, original in base_by_id.items():
        actual = current_by_id[sim_id].copy()
        if sim_id == "books-close":
            actual["fixture_profile"] = original["fixture_profile"]
        assert actual == original
    business, books = _materialize(tmp_path)
    assert business.is_dir() and books.is_dir()
