"""The last suggested commands that named no business repo (#1083).

Each case runs from a folder that is not the business repo, so a bare
`--repo .` or a command with no repo would act on the wrong folder. The
from-inside cases pin the bare text byte for byte.
"""

from __future__ import annotations

import json
import shlex
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mb import connect, onboard
from mb.cli import app
from mb.init import run as init_run

runner = CliRunner()


@pytest.fixture
def business(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("MAINBRANCH_HOME", str(home / "mb"))
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "local-file")
    monkeypatch.setenv("COLUMNS", "2000")
    repo = tmp_path / "Acme's studio"
    init_run(path=str(repo), name="Acme")
    hook = repo / ".git" / "hooks" / "commit-msg"
    hook.unlink(missing_ok=True)
    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.chdir(other)
    return repo.resolve()


def _flag(business: Path) -> str:
    return f"--repo {shlex.quote(str(business))}"


def _hook_status_command(business: Path) -> dict:
    result = runner.invoke(app, ["checkpoint", "--repo", str(business), "--hook-status", "--json"])
    payload: dict = json.loads(result.stdout)
    return payload


def _hook_repair(business: Path) -> str:
    return str(_hook_status_command(business)["repair_command"])


def test_hook_status_repair_command_names_the_business(business: Path) -> None:
    assert _hook_status_command(business)["state"] == "missing"
    assert _hook_repair(business) == f"mb checkpoint {_flag(business)} --install-hook"


def test_blocked_hook_repair_command_names_the_business(business: Path) -> None:
    hook = business / ".git" / "hooks" / "commit-msg"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    assert _hook_status_command(business)["state"] == "blocked_existing_hook"
    assert _hook_repair(business) == (
        f"review .git/hooks/commit-msg, then run mb checkpoint {_flag(business)} --install-hook"
    )


def test_hook_status_inside_the_repo_keeps_its_bare_commands(
    business: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(business)
    assert _hook_repair(business) == "mb checkpoint --install-hook"
    hook = business / ".git" / "hooks" / "commit-msg"
    hook.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    assert _hook_repair(business) == (
        "review .git/hooks/commit-msg, then run mb checkpoint --install-hook"
    )


def test_setup_complete_hook_repair_names_the_business(
    business: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected = f"mb checkpoint {_flag(business)} --install-hook"
    assert onboard._setup_complete(business)["checkpoint_hook_repair"] == expected
    monkeypatch.chdir(business)
    assert (
        onboard._setup_complete(business)["checkpoint_hook_repair"]
        == "mb checkpoint --install-hook"
    )


def test_onboard_status_human_names_the_business_in_its_plan_hint(business: Path) -> None:
    result = runner.invoke(app, ["onboard", "status", "--repo", str(business)])
    assert f"Run `mb onboard plan {_flag(business)}`." in result.output


def test_onboard_status_human_inside_the_repo_keeps_the_bare_hint(
    business: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(business)
    result = runner.invoke(app, ["onboard", "status", "--repo", str(business)])
    assert "Run `mb onboard plan`." in result.output


def _store_user_scope_provider(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    canonical = tmp_path / "canonical"
    disposable = tmp_path / "workspace"
    canonical.mkdir()
    disposable.mkdir()

    def fake_git(repo: Path, args: list[str]) -> str:
        if args == ["config", "--get", "remote.origin.url"]:
            return "git@github.com:acme/business.git"
        return ""

    monkeypatch.setattr(connect, "_git_output", fake_git)
    result = connect.connect_provider(
        "cloudflare",
        repo=canonical,
        token="cf-test-token",
        account_label="Acme Cloudflare",
        metadata_pairs=["account_id=acct_123", "zone_id=zone_456"],
        scope="user",
    )
    assert result["ok"] is True
    return disposable


def test_connect_hydrate_hint_names_the_workspace(
    tmp_path: Path, business: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = _store_user_scope_provider(tmp_path, monkeypatch).resolve()
    before = connect.status_provider("cloudflare", workspace)
    assert before["state"] == "needs_hydration"
    command = f"mb connect hydrate --repo {shlex.quote(str(workspace))}"
    assert before["repair_command"] == command
    assert before["repair"] == f"Run `{command}` from this workspace."
    doctor = connect.doctor(workspace)
    check = next(item for item in doctor["checks"] if item["name"] == "provider:cloudflare")
    assert check["repair_command"] == command
    cli = runner.invoke(app, ["connect", "status", "cloudflare", "--repo", str(workspace), "--json"])
    assert command in json.dumps(json.loads(cli.stdout))


def test_connect_hydrate_hint_inside_the_workspace_keeps_the_bare_command(
    tmp_path: Path, business: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = _store_user_scope_provider(tmp_path, monkeypatch)
    monkeypatch.chdir(workspace)
    before = connect.status_provider("cloudflare", workspace)
    assert before["repair_command"] == "mb connect hydrate --repo ."
    assert before["repair"] == "Run `mb connect hydrate --repo .` from this workspace."


def _start(business: Path) -> dict:
    result = runner.invoke(app, ["start", "--repo", str(business), "--json"])
    assert result.exit_code in {0, 1}, result.output
    payload: dict = json.loads(result.stdout)
    return payload


def _broken_wiring(business: Path) -> None:
    subprocess.run(["rm", "-rf", str(business / ".claude" / "skills")], check=True)


def test_start_wiring_repair_names_the_business_without_a_redundant_clause(
    business: Path,
) -> None:
    _broken_wiring(business)
    report = _start(business)
    repair = next(c["repair"] for c in report["checks"] if c["name"] == "skill_wiring")
    flag = _flag(business)
    assert repair == (
        f"Run `mb doctor repair {flag} --plan`, review it, then run "
        f"`mb doctor repair {flag} --apply`."
    )
    assert not any("from the business repo" in action for action in report["next_actions"])


def test_start_wiring_repair_inside_the_repo_keeps_its_clause(
    business: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _broken_wiring(business)
    monkeypatch.chdir(business)
    result = runner.invoke(app, ["start", "--json"])
    report = json.loads(result.stdout)
    repair = next(c["repair"] for c in report["checks"] if c["name"] == "skill_wiring")
    assert repair == (
        "Run `mb doctor repair --plan`, review it, then run "
        "`mb doctor repair --apply` from the business repo."
    )
