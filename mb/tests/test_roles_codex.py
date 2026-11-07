"""Role cards in Codex: the user-level hook install, its command, and doctor wiring."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from mb import roles, roles_codex
from mb.cli import app
from mb.doctor import run as doctor_run

runner = CliRunner()
MB_PACKAGE_ROOT = Path(__file__).resolve().parents[1]

CARD = """---
name: scout
role: Research scout for the business
skills: [mb-think]
tools: [mb]
protocols: [save-before-stop]
first_action: Read the checkpoint, then say which role you are.
checkpoint: state/scout-checkpoint.md
---
Notes.
"""
FOUND = {"found": True, "path": "/x/codex", "repair": ""}
MISSING = {"found": False, "path": "", "repair": ""}
OTHER_GROUP = {
    "matcher": "startup",
    "hooks": [{"type": "command", "command": "echo other-guard", "timeout": 5}],
}


@pytest.fixture()
def codex_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "codex-home"
    home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(home))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.delenv(roles.ROLE_ENV, raising=False)
    return home


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "biz"
    (root / "core" / "roles").mkdir(parents=True)
    (root / "state").mkdir()
    (root / "core" / "roles" / "scout.md").write_text(CARD, encoding="utf-8")
    (root / "state" / "scout-checkpoint.md").write_text("ZEBRA-42 open\n", encoding="utf-8")
    (root / ".git").mkdir()
    return root


def _write(home: Path, doc: object) -> Path:
    path = home / "hooks.json"
    path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return path


def _groups(home: Path) -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = json.loads((home / "hooks.json").read_text())["hooks"][
        "SessionStart"
    ]
    return groups


# --- install: plan, apply, merge -------------------------------------------


def test_plan_writes_nothing(codex_home: Path) -> None:
    report = roles_codex.plan()
    assert report["action"] == "add" and "+++" in report["diff"]
    assert not (codex_home / "hooks.json").exists()


def test_apply_creates_the_hook_with_limits_and_no_other_files(codex_home: Path) -> None:
    result = roles_codex.apply()
    assert result["written"]
    (group,) = _groups(codex_home)
    assert group["matcher"] == "startup|resume|clear|compact|fork"
    (hook,) = group["hooks"]
    assert hook["command"] == roles_codex.CODEX_HOOK_COMMAND
    assert hook["timeout"] == roles_codex.HOOK_TIMEOUT_SECONDS
    assert hook["additionalContextLimit"] == roles_codex.CONTEXT_LIMIT
    # No trust state and no config tables are ever written.
    assert [p.name for p in codex_home.iterdir()] == ["hooks.json"]


def test_apply_twice_is_idempotent(codex_home: Path) -> None:
    roles_codex.apply()
    first = (codex_home / "hooks.json").read_bytes()
    again = roles_codex.apply()
    assert again["action"] == "unchanged" and not again["written"]
    assert (codex_home / "hooks.json").read_bytes() == first


def test_other_hooks_and_keys_are_preserved(codex_home: Path) -> None:
    doc: dict[str, Any] = {
        "description": "mine",
        "hooks": {
            "SessionStart": [OTHER_GROUP],
            "Stop": [{"hooks": [{"type": "command", "command": "echo bye"}]}],
        },
    }
    _write(codex_home, doc)
    roles_codex.apply()
    after = json.loads((codex_home / "hooks.json").read_text())
    assert after["description"] == "mine" and after["hooks"]["Stop"] == doc["hooks"]["Stop"]
    assert after["hooks"]["SessionStart"][0] == OTHER_GROUP
    assert len(after["hooks"]["SessionStart"]) == 2


def test_stale_copy_of_our_hook_is_replaced_not_duplicated(codex_home: Path) -> None:
    stale = {
        "matcher": "startup",
        "hooks": [{"type": "command", "command": roles_codex.CODEX_HOOK_COMMAND, "timeout": 5}],
    }
    _write(codex_home, {"hooks": {"SessionStart": [OTHER_GROUP, stale]}})
    assert roles_codex.plan()["action"] == "replace"
    roles_codex.apply()
    groups = _groups(codex_home)
    assert groups[0] == OTHER_GROUP and len(groups) == 2
    assert groups[1] == roles_codex.hook_group()


@pytest.mark.parametrize(
    "command",
    [
        'printf "%s\\n" "mb role hook --runtime codex"',
        "mb role hook --runtime codex",
        "guard.sh && mb role hook --runtime codex",
    ],
)
def test_a_hook_that_only_mentions_ours_is_never_touched(codex_home: Path, command: str) -> None:
    theirs = {"matcher": "startup", "hooks": [{"type": "command", "command": command}]}
    _write(codex_home, {"hooks": {"SessionStart": [theirs]}})
    assert roles_codex.plan(remove=True)["action"] == "unchanged"
    assert roles_codex.plan(remove=True)["note"]
    roles_codex.apply()
    assert _groups(codex_home) == [theirs, roles_codex.hook_group()]
    roles_codex.apply(remove=True)
    assert _groups(codex_home) == [theirs]


@pytest.mark.parametrize(
    "raw",
    [
        "{not json",
        "[]",
        '{"hooks": []}',
        '{"hooks": null}',
        '{"hooks": {"SessionStart": null}}',
        '{"hooks": {"SessionStart": {}}}',
        '{"hooks": {"SessionStart": ["x"]}}',
        '{"hooks": {"SessionStart": [{"hooks": "x"}]}}',
        "\xff",
    ],
)
def test_malformed_file_fails_closed_with_no_change(codex_home: Path, raw: str) -> None:
    path = codex_home / "hooks.json"
    path.write_bytes(raw.encode("latin-1"))
    for remove in (False, True):
        result = roles_codex.apply(remove=remove)
        assert result["action"] == "refused" and not result["written"] and result["problem"]
    assert path.read_bytes() == raw.encode("latin-1")
    assert [p.name for p in codex_home.iterdir()] == ["hooks.json"]


def test_symlinked_hooks_file_is_refused_and_left_alone(codex_home: Path, tmp_path: Path) -> None:
    real = tmp_path / "dotfiles-hooks.json"
    real.write_text('{"hooks": {}}', encoding="utf-8")
    (codex_home / "hooks.json").symlink_to(real)
    result = roles_codex.apply()
    assert result["action"] == "refused" and "link" in result["problem"]
    assert (codex_home / "hooks.json").is_symlink()
    assert real.read_text() == '{"hooks": {}}'


def test_dangling_symlink_is_refused(codex_home: Path, tmp_path: Path) -> None:
    (codex_home / "hooks.json").symlink_to(tmp_path / "nowhere.json")
    assert roles_codex.apply()["action"] == "refused"
    assert not (tmp_path / "nowhere.json").exists()


def test_missing_codex_home_is_refused_not_created(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "absent"))
    assert roles_codex.apply()["action"] == "refused"
    assert not (tmp_path / "absent").exists()


# --- uninstall ---------------------------------------------------------------


def test_uninstall_removes_only_ours_and_keeps_the_rest(codex_home: Path) -> None:
    _write(codex_home, {"hooks": {"SessionStart": [OTHER_GROUP]}})
    roles_codex.apply()
    roles_codex.apply(remove=True)
    assert json.loads((codex_home / "hooks.json").read_text()) == {
        "hooks": {"SessionStart": [OTHER_GROUP]}
    }


def test_uninstall_of_our_only_hook_removes_the_file(codex_home: Path) -> None:
    roles_codex.apply()
    assert roles_codex.apply(remove=True)["written"]
    assert not (codex_home / "hooks.json").exists()


def test_uninstall_when_not_installed_changes_nothing(codex_home: Path) -> None:
    _write(codex_home, {"hooks": {"SessionStart": [OTHER_GROUP]}})
    before = (codex_home / "hooks.json").read_bytes()
    assert roles_codex.apply(remove=True)["action"] == "unchanged"
    assert (codex_home / "hooks.json").read_bytes() == before


def test_uninstall_splits_a_group_it_shares_with_another_hook(codex_home: Path) -> None:
    shared = {
        "matcher": "startup",
        "hooks": [
            OTHER_GROUP["hooks"][0],
            {"type": "command", "command": roles_codex.CODEX_HOOK_COMMAND},
        ],
    }
    _write(codex_home, {"hooks": {"SessionStart": [shared]}})
    roles_codex.apply(remove=True)
    assert _groups(codex_home) == [{"matcher": "startup", "hooks": OTHER_GROUP["hooks"]}]


# --- CLI ---------------------------------------------------------------------


def test_cli_previews_by_default_and_applies_on_request(codex_home: Path) -> None:
    preview = runner.invoke(app, ["role", "codex-hook"])
    assert preview.exit_code == 0 and "Preview only" in preview.output
    assert not (codex_home / "hooks.json").exists()
    done = runner.invoke(app, ["role", "codex-hook", "--apply"])
    assert done.exit_code == 0 and "/hooks" in done.output
    assert (codex_home / "hooks.json").exists()
    gone = runner.invoke(app, ["role", "codex-hook", "--apply", "--remove", "--json"])
    payload = json.loads(gone.output)
    assert gone.exit_code == 0 and payload["written"] is True and payload["ok"] is True
    assert payload["result_schema"]["name"] == "mainbranch.role.codex_hook"
    assert not (codex_home / "hooks.json").exists()


def test_cli_exits_one_on_a_refused_file(codex_home: Path) -> None:
    (codex_home / "hooks.json").write_text("{", encoding="utf-8")
    result = runner.invoke(app, ["role", "codex-hook", "--apply"])
    assert result.exit_code == 1 and "Refused" in result.output


# --- the hook command and stdin ------------------------------------------------


def _shim(directory: Path, marker: Path) -> Path:
    directory.mkdir()
    shim = directory / "mb"
    shim.write_text(
        f'#!/bin/sh\necho ran >> "{marker}"\n'
        f'PYTHONPATH="{MB_PACKAGE_ROOT}" exec "{sys.executable}" -m mb "$@"\n',
        encoding="utf-8",
    )
    shim.chmod(0o755)
    return directory


def _run(
    cwd: Path,
    path_dir: Path,
    payload: object | None,
    role: str | None = "scout",
    cwd_in_payload: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    env = {"PATH": f"{path_dir}:/usr/bin:/bin", "HOME": str(cwd)}
    if role:
        env[roles.ROLE_ENV] = role
    stdin = "" if payload is None else json.dumps(payload)
    if isinstance(payload, dict) and cwd_in_payload is not None:
        stdin = json.dumps({**payload, "cwd": str(cwd_in_payload)})
    return subprocess.run(
        ["/bin/sh", "-c", roles_codex.CODEX_HOOK_COMMAND],
        cwd=cwd,
        env=env,
        input=stdin,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


@pytest.mark.parametrize("source", ["startup", "resume", "clear", "compact", "fork"])
def test_hook_loads_card_for_every_codex_source(repo: Path, tmp_path: Path, source: str) -> None:
    sub = repo / "state"
    path_dir = _shim(tmp_path / "bin", tmp_path / "ran")
    result = _run(sub, path_dir, {"source": source, "cwd": str(sub)})
    assert result.returncode == 0 and result.stderr == ""
    assert f"(session {source})" in result.stdout
    assert "running as role: scout" in result.stdout and "ZEBRA-42" in result.stdout


def test_hook_finds_the_repo_from_a_deep_subfolder_by_payload_cwd(
    repo: Path, tmp_path: Path
) -> None:
    deep = repo / "a" / "b"
    deep.mkdir(parents=True)
    path_dir = _shim(tmp_path / "bin", tmp_path / "ran")
    result = _run(deep, path_dir, {"source": "startup"}, cwd_in_payload=deep)
    assert "running as role: scout" in result.stdout


def test_hook_works_in_a_git_worktree_where_dot_git_is_a_file(repo: Path, tmp_path: Path) -> None:
    (repo / ".git").rmdir()
    (repo / ".git").write_text("gitdir: /nowhere\n", encoding="utf-8")
    sub = repo / "state"
    path_dir = _shim(tmp_path / "bin", tmp_path / "ran")
    assert "running as role: scout" in _run(sub, path_dir, {"source": "resume"}).stdout


def test_hook_refuses_with_cards_and_no_mb_role(repo: Path, tmp_path: Path) -> None:
    path_dir = _shim(tmp_path / "bin", tmp_path / "ran")
    result = _run(repo, path_dir, {"source": "startup"}, role=None)
    assert result.returncode == 0
    assert "ROLE CHECK FAILED" in result.stdout and "MB_ROLE is not set" in result.stdout


def test_hook_is_silent_and_never_starts_mb_with_no_cards(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / ".git").mkdir()
    marker = tmp_path / "ran"
    path_dir = _shim(tmp_path / "bin", marker)
    result = _run(plain, path_dir, {"source": "startup"})
    assert result.returncode == 0 and result.stdout == "" and result.stderr == ""
    assert not marker.exists()


def test_hook_does_not_climb_past_a_git_root_into_a_parent_repo(repo: Path, tmp_path: Path) -> None:
    inner = repo / "vendor" / "other"
    (inner / ".git").mkdir(parents=True)
    marker = tmp_path / "ran"
    path_dir = _shim(tmp_path / "bin", marker)
    result = _run(inner, path_dir, {"source": "startup"})
    assert result.stdout == "" and not marker.exists()


@pytest.mark.parametrize("source", ["startup", "resume", "clear", "compact", "fork"])
def test_hook_when_mb_is_missing_and_a_card_exists(repo: Path, tmp_path: Path, source: str) -> None:
    empty = tmp_path / "empty-bin"
    empty.mkdir()
    result = _run(repo / "state", empty, {"source": source}, role=None)
    assert result.returncode == 0
    if source == "startup":
        assert "ROLE CHECK FAILED" in result.stdout and "STOP" in result.stdout
    else:
        assert result.stdout.startswith("MAIN BRANCH ROLE WARNING")
        assert "Restart it with MB_ROLE set to the role you meant." in result.stdout
        assert "mb agent" not in result.stdout
        assert "STOP" not in result.stdout and "ROLE CHECK FAILED" not in result.stdout


@pytest.mark.parametrize("payload", [None, {}, {"source": "weird"}, {"cwd": "x"}])
def test_hook_when_mb_is_missing_and_source_is_unknown_keeps_stop(
    repo: Path, tmp_path: Path, payload: object
) -> None:
    empty = tmp_path / "empty-bin"
    empty.mkdir()
    result = _run(repo / "state", empty, payload, role=None)
    assert "STOP" in result.stdout


def _failing_mb(directory: Path) -> Path:
    directory.mkdir()
    shim = directory / "mb"
    shim.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    shim.chmod(0o755)
    return directory


@pytest.mark.parametrize("source", ["startup", "resume", "clear", "compact", "fork"])
@pytest.mark.parametrize("role", ["scout", "ghost", "Bad Name"])
@pytest.mark.parametrize("binary", ["missing", "failing"])
def test_hook_with_a_selected_role_never_downgrades_to_a_warning(
    repo: Path, tmp_path: Path, source: str, role: str, binary: str
) -> None:
    if binary == "missing":
        path_dir = tmp_path / "empty-bin"
        path_dir.mkdir()
    else:
        path_dir = _failing_mb(tmp_path / "fail-bin")
    result = _run(repo / "state", path_dir, {"source": source}, role=role)
    assert "ROLE CHECK FAILED" in result.stdout and "STOP" in result.stdout
    assert "ROLE WARNING" not in result.stdout


@pytest.mark.parametrize(
    "raw",
    [
        '{"source":"startup","metadata":{"source":"resume"}}',
        '{"metadata":{"source":"resume"}}',
        '{"source":"resume","source":"startup"}',
        '{"source":"startup","source":"resume"}',
        '{"source":"resume"',
        'not json "source":"resume"',
        '"source":"resume"}',
        '{"source":"startup","note":"x' + "a" * 70000 + '","tail":"\\"source\\":\\"resume\\""}',
    ],
)
def test_hook_fallback_reads_only_the_top_level_source(
    repo: Path, tmp_path: Path, raw: str
) -> None:
    empty = tmp_path / "empty-bin"
    empty.mkdir()
    env = {"PATH": f"{empty}:/usr/bin:/bin", "HOME": str(repo)}
    result = subprocess.run(
        ["/bin/sh", "-c", roles_codex.CODEX_HOOK_COMMAND],
        cwd=repo / "state",
        env=env,
        input=raw,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert "STOP" in result.stdout and "ROLE WARNING" not in result.stdout


def test_hook_fallback_warns_for_a_real_flat_payload(repo: Path, tmp_path: Path) -> None:
    empty = tmp_path / "empty-bin"
    empty.mkdir()
    payload = {"session_id": "s", "cwd": str(repo), "source": "resume"}
    result = _run(repo / "state", empty, payload, role=None)
    assert result.stdout.startswith("MAIN BRANCH ROLE WARNING") and "STOP" not in result.stdout


# The exact command `mb role codex-hook --apply` wrote before the source split.
PREVIOUS_COMMAND = (
    'sh -c \'d=$PWD; while :; do [ -d "$d/core/roles" ] && break; '
    '{ [ -e "$d/.git" ] || [ "$d" = / ]; } && exit 0; p=${d%/*}; d=${p:-/}; done; '
    "if command -v mb >/dev/null 2>&1 && out=$(mb role hook --runtime codex 2>/dev/null); "
    'then [ -z "$out" ] || printf "%s\\n" "$out"; '
    'else set -- "$d"/core/roles/*.md; '
    'if [ -e "$1" ] || [ -L "$1" ]; then printf "%s\\n" "MAIN BRANCH ROLE CHECK FAILED: '
    "this repo has role cards (core/roles) but the role could not be loaded. STOP. "
    "Do not start work and do not pick a role yourself. Tell the owner this message and ask "
    "them to fix the role setup. This session has no role.\"; fi; fi; exit 0'"
)


def test_previously_generated_command_is_replaced_on_apply(codex_home: Path) -> None:
    old = {
        "matcher": roles_codex.CODEX_MATCHER,
        "hooks": [{"type": "command", "command": PREVIOUS_COMMAND, "timeout": 20}],
    }
    _write(codex_home, {"hooks": {"SessionStart": [OTHER_GROUP, old]}})
    assert roles_codex.plan()["action"] == "replace"
    roles_codex.apply()
    groups = _groups(codex_home)
    assert groups[0] == OTHER_GROUP and groups[1:] == [roles_codex.hook_group()]


def test_previously_generated_command_is_removed_on_remove(codex_home: Path) -> None:
    old = {"matcher": "startup", "hooks": [{"type": "command", "command": PREVIOUS_COMMAND}]}
    _write(codex_home, {"hooks": {"SessionStart": [OTHER_GROUP, old]}})
    assert roles_codex.plan(remove=True)["action"] != "unchanged"
    roles_codex.apply(remove=True)
    assert _groups(codex_home) == [OTHER_GROUP]


@pytest.mark.parametrize("source", ["startup", "resume", "clear", "compact", "fork"])
def test_hook_with_mb_present_and_no_role_splits_by_source(
    repo: Path, tmp_path: Path, source: str
) -> None:
    path_dir = _shim(tmp_path / "bin", tmp_path / "ran")
    result = _run(repo / "state", path_dir, {"source": source, "cwd": str(repo)}, role=None)
    assert result.returncode == 0
    if source == "startup":
        assert "STOP" in result.stdout
    else:
        assert result.stdout.startswith("MAIN BRANCH ROLE WARNING") and "STOP" not in result.stdout


def test_codex_hook_declares_a_timeout_and_a_hang_prints_nothing(
    repo: Path, tmp_path: Path
) -> None:
    assert 0 < roles_codex.HOOK_TIMEOUT_SECONDS <= 30
    shim = tmp_path / "hang-bin"
    shim.mkdir()
    (shim / "mb").write_text("#!/bin/sh\nexec sleep 30\n", encoding="utf-8")
    (shim / "mb").chmod(0o755)
    env = {"PATH": f"{shim}:/usr/bin:/bin", "HOME": str(repo)}
    with pytest.raises(subprocess.TimeoutExpired) as caught:
        subprocess.run(
            ["/bin/sh", "-c", roles_codex.CODEX_HOOK_COMMAND],
            cwd=repo / "state",
            env=env,
            input=json.dumps({"source": "resume"}),
            capture_output=True,
            text=True,
            timeout=1,
        )
    assert not caught.value.stdout or "running as role" not in str(caught.value.stdout)


def test_hook_is_silent_when_mb_is_missing_and_the_roles_folder_is_empty(
    repo: Path, tmp_path: Path
) -> None:
    (repo / "core" / "roles" / "scout.md").unlink()
    empty = tmp_path / "empty-bin"
    empty.mkdir()
    result = _run(repo, empty, {"source": "startup"})
    assert result.returncode == 0 and result.stdout == ""


def test_hook_ignores_garbage_and_missing_stdin(repo: Path, tmp_path: Path) -> None:
    path_dir = _shim(tmp_path / "bin", tmp_path / "ran")
    for payload in (None, ["x"], "not an object"):
        result = _run(repo / "state", path_dir, payload)
        assert result.returncode == 0
        assert "(session unknown)" in result.stdout and "running as role: scout" in result.stdout


def test_hook_ignores_claude_project_dir_under_codex(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    decoy = tmp_path / "decoy"
    (decoy / "core" / "roles").mkdir(parents=True)
    (decoy / "core" / "roles" / "scout.md").write_text(
        CARD.replace("Research scout", "DECOY"), encoding="utf-8"
    )
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(decoy))
    monkeypatch.setenv(roles.ROLE_ENV, "scout")
    payload = json.dumps({"source": "startup", "cwd": str(repo)})
    result = runner.invoke(app, ["role", "hook", "--runtime", "codex"], input=payload)
    assert "Research scout" in result.output and "DECOY" not in result.output


def test_claude_runtime_output_is_unchanged_and_ignores_stdin(
    repo: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(repo))
    monkeypatch.setenv(roles.ROLE_ENV, "scout")
    expected = roles.hook_text(repo, "compact", env={roles.ROLE_ENV: "scout"}) + "\n"
    payload = json.dumps({"source": "startup", "cwd": str(tmp_path)})
    default = runner.invoke(app, ["role", "hook", "--source", "compact"], input=payload)
    assert default.output == expected
    explicit = runner.invoke(app, ["role", "hook", "--runtime", "claude", "--source", "compact"])
    assert explicit.output == expected


def test_codex_and_claude_print_the_same_card(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(roles.ROLE_ENV, "scout")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(repo))
    claude = runner.invoke(app, ["role", "hook", "--source", "resume"]).output
    monkeypatch.delenv("CLAUDE_PROJECT_DIR")
    payload = json.dumps({"source": "resume", "cwd": str(repo / "state")})
    assert (
        runner.invoke(app, ["role", "hook", "--runtime", "codex"], input=payload).output == claude
    )


def test_card_with_a_full_checkpoint_fits_the_context_limit(repo: Path) -> None:
    (repo / "state" / "scout-checkpoint.md").write_text("word " * 4000, encoding="utf-8")
    text = roles.hook_text(repo, "startup", env={roles.ROLE_ENV: "scout"})
    assert "(checkpoint truncated)" in text
    assert len(text) / 3 < roles_codex.CONTEXT_LIMIT


# --- doctor ----------------------------------------------------------------------


def _codex_check(repo: Path) -> dict[str, Any]:
    return next(c for c in doctor_run(path=str(repo))["checks"] if c["name"] == "role-cards-codex")


def test_doctor_has_no_codex_role_check_without_cards(codex_home: Path, tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    names = [c["name"] for c in doctor_run(path=str(plain))["checks"]]
    assert "role-cards-codex" not in names


def test_doctor_warns_when_codex_is_present_but_not_wired(
    codex_home: Path, repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("mb.doctor.codex_mod.executable_status", lambda: FOUND)
    check = _codex_check(repo)
    assert not check["ok"] and check["severity"] == "warn"
    assert "mb role codex-hook" in check["detail"]


def test_doctor_wired_hook_is_never_reported_as_trusted(
    codex_home: Path, repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("mb.doctor.codex_mod.executable_status", lambda: FOUND)
    roles_codex.apply()
    check = _codex_check(repo)
    assert check["ok"] and check["severity"] == "info"
    assert "Trust not verified" in check["detail"] and check["codex"]["trust"] == "not verified"


@pytest.mark.parametrize(
    "command",
    [
        "mb role hook --runtime codex",
        roles_codex.CODEX_HOOK_COMMAND + " ; echo extra",
        roles_codex.CODEX_HOOK_COMMAND.replace("2>/dev/null", ""),
    ],
)
def test_doctor_requires_the_exact_command(
    codex_home: Path, command: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    group = roles_codex.hook_group()
    group["hooks"][0]["command"] = command
    _write(codex_home, {"hooks": {"SessionStart": [group]}})
    assert roles_codex.wiring()["wired"] is False


def test_doctor_requires_every_source_matcher(codex_home: Path) -> None:
    group = roles_codex.hook_group()
    group["matcher"] = "startup"
    _write(codex_home, {"hooks": {"SessionStart": [group]}})
    assert roles_codex.wiring()["wired"] is False


def test_doctor_does_not_call_a_malformed_or_linked_file_wired(
    codex_home: Path, tmp_path: Path
) -> None:
    (codex_home / "hooks.json").write_text("{", encoding="utf-8")
    state = roles_codex.wiring()
    assert not state["wired"] and state["problem"]
    (codex_home / "hooks.json").unlink()
    real = tmp_path / "real.json"
    real.write_text(json.dumps({"hooks": {"SessionStart": [roles_codex.hook_group()]}}))
    (codex_home / "hooks.json").symlink_to(real)
    assert roles_codex.wiring()["wired"] is False


def test_doctor_says_codex_not_checked_when_codex_is_missing(
    codex_home: Path, repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("mb.doctor.codex_mod.executable_status", lambda: MISSING)
    check = _codex_check(repo)
    assert check["ok"] and "not checked" in check["detail"]


def test_install_path_never_follows_claude_named_variables(
    codex_home: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude"))
    assert Path(roles_codex.hooks_path()).parent == codex_home
    assert os.fspath(roles_codex.hooks_path()).startswith(str(codex_home))


def test_find_repo_stops_at_a_git_root(repo: Path) -> None:
    inner = repo / "vendor" / "other"
    (inner / ".git").mkdir(parents=True)
    deep = repo / "a" / "b"
    deep.mkdir(parents=True)
    assert roles.find_repo(deep) == repo.resolve()
    assert roles.find_repo(inner) is None
