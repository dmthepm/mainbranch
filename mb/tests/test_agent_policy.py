"""mb agent check, slice 1: agents.json policy and filesystem validation. Invented paths only."""

import json
import os
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from mb import agent_policy as ap
from mb.cli import app

CARD = (
    "---\n"
    "name: {role}\n"
    "role: Invented role\n"
    "skills: [a]\n"
    "tools: [b]\n"
    "protocols: [c]\n"
    "first_action: Read the checkpoint.\n"
    "checkpoint: state/checkpoint.md\n"
    "---\n"
    "Body.\n"
)


class World:
    """A disposable HOME under a private floor, so the real /tmp ancestors are not judged."""

    def __init__(self, tmp_path: Path) -> None:
        self.floor = tmp_path / "w"
        self.floor.mkdir(mode=0o700)
        self.home = self.floor / "home"
        self.home.mkdir(mode=0o700)
        self.biz = self.mkdir(self.home / "biz")
        self.mkdir(self.biz / "core" / "roles")
        self.store = self.mkdir(self.home / ".local" / "state" / "mainbranch" / "agents")
        self.cards = self.mkdir(self.home / ".local" / "share" / "agent-role-cards")
        self.bin = self.mkdir(self.floor / "bin")
        self.card("planner", self.biz / "core" / "roles")
        self.host = ap.Host(
            home=str(self.home),
            uid=os.getuid(),
            floor=str(self.floor),
            default_path=(str(self.bin),),
        )

    @staticmethod
    def mkdir(path: Path) -> Path:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        for part in (path, *path.parents):
            if part.name == "w":
                break
            part.chmod(0o700)
        return path

    def card(self, role: str, where: Path) -> Path:
        path = where / f"{role}.md"
        path.write_text(CARD.format(role=role))
        path.chmod(0o600)
        return path

    def row(self, **over: Any) -> dict[str, Any]:
        row: dict[str, Any] = {
            "name": "planner",
            "runtime": "claude",
            "cwd": str(self.biz),
            "role": "planner",
            "profile": "default",
            "model": "claude-test-1",
        }
        row.update(over)
        return row

    def write(self, policy: Any = None, **top: Any) -> Path:
        if policy is None:
            policy = {"version": 1, "agents": [self.row()], **top}
        path = self.store / "agents.json"
        path.write_text(policy if isinstance(policy, str) else json.dumps(policy))
        path.chmod(0o600)
        return path

    def check(self, name: str | None = None, host: ap.Host | None = None) -> ap.Report:
        return ap.check(host or self.host, name)

    def codes(self, **kw: Any) -> list[str]:
        return [p.code for p in self.check(**kw).problems]


@pytest.fixture
def w(tmp_path: Path) -> World:
    world = World(tmp_path)
    world.write()
    return world


def test_valid_policy(w: World) -> None:
    report = w.check()
    assert report.problems == []
    assert report.ok
    assert report.agents == 1


def test_missing_policy_file(w: World) -> None:
    (w.store / "agents.json").unlink()
    assert w.codes() == ["policy-missing"]


def test_root_is_refused(w: World) -> None:
    host = ap.Host(**{**w.host.__dict__, "uid": 0})
    assert [p.code for p in w.check(host=host).problems] == ["root"]


def test_check_changes_nothing(w: World) -> None:
    def snapshot() -> list[tuple[str, int, int]]:
        return sorted((str(p), p.stat().st_mtime_ns, p.stat().st_mode) for p in w.floor.rglob("*"))

    before = snapshot()
    w.check()
    assert snapshot() == before


# --- file and directory trust -------------------------------------------------------


@pytest.mark.parametrize("mode", [0o620, 0o602, 0o660, 0o666])
def test_group_or_world_writable_policy_file(w: World, mode: int) -> None:
    (w.store / "agents.json").chmod(mode)
    assert "unsafe-path" in w.codes()


@pytest.mark.parametrize("mode", [0o770, 0o707, 0o777, 0o1777])
def test_group_or_world_writable_store_dir(w: World, mode: int) -> None:
    w.store.chmod(mode)
    assert "unsafe-path" in w.codes()


def test_writable_ancestor_of_store(w: World) -> None:
    (w.home / ".local").chmod(0o770)
    assert "unsafe-path" in w.codes()


def test_sticky_does_not_excuse_world_write(w: World) -> None:
    w.biz.chmod(0o1777)
    assert "unsafe-path" in w.codes()


def test_policy_owned_by_someone_else(w: World) -> None:
    host = ap.Host(**{**w.host.__dict__, "uid": os.getuid() + 1})
    assert "unsafe-path" in [p.code for p in w.check(host=host).problems]


def test_policy_file_symlink_refused(w: World, tmp_path: Path) -> None:
    real = tmp_path / "elsewhere.json"
    real.write_text((w.store / "agents.json").read_text())
    real.chmod(0o600)
    (w.store / "agents.json").unlink()
    (w.store / "agents.json").symlink_to(real)
    assert "unsafe-path" in w.codes()


def test_store_dir_symlink_refused(w: World, tmp_path: Path) -> None:
    moved = tmp_path / "moved"
    w.store.rename(moved)
    w.store.symlink_to(moved)
    assert "unsafe-path" in w.codes()


def test_policy_fifo_is_refused_without_hanging(w: World) -> None:
    path = w.store / "agents.json"
    path.unlink()
    os.mkfifo(path, 0o600)
    assert "unsafe-path" in w.codes()


def test_symlinked_home_is_followed_through_checked_dirs(w: World, tmp_path: Path) -> None:
    alias = w.floor / "home-alias"
    alias.symlink_to(w.home)
    host = ap.Host(**{**w.host.__dict__, "home": str(alias)})
    assert w.check(host=host).problems == []


# --- schema -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    ["", "{", "[]", '"x"', "null", '{"version": 1, "version": 1, "agents": []}', "NaN"],
)
def test_unparsable_policy(w: World, text: str) -> None:
    w.write(text)
    assert w.codes() == ["schema"]


def test_policy_too_large(w: World) -> None:
    w.write({"version": 1, "agents": [], "pad": "x" * 70_000})
    assert w.codes() == ["schema"]


@pytest.mark.parametrize("version", [0, 2, "1", True, None])
def test_bad_version(w: World, version: Any) -> None:
    w.write({"version": version, "agents": [w.row()]})
    assert "schema" in w.codes()


def test_unknown_top_level_key(w: World) -> None:
    w.write({"version": 1, "agents": [w.row()], "env": {}})
    assert "schema" in w.codes()


@pytest.mark.parametrize(
    "field", ["owner", "kind", "argv", "env", "workspace", "pane", "first_prompt", "session"]
)
def test_dropped_fields_are_rejected(w: World, field: str) -> None:
    w.write({"version": 1, "agents": [w.row(**{field: "x"})]})
    assert "schema" in w.codes()


@pytest.mark.parametrize("field", ["name", "runtime", "cwd", "role", "profile", "model"])
def test_missing_required_row_field(w: World, field: str) -> None:
    row = w.row()
    del row[field]
    w.write({"version": 1, "agents": [row]})
    assert "schema" in w.codes()


@pytest.mark.parametrize(
    "over",
    [
        {"name": "Planner"},
        {"name": ""},
        {"name": "a" * 41},
        {"name": "has space"},
        {"role": "../x"},
        {"role": "A"},
        {"runtime": "gemini"},
        {"model": "bad model"},
        {"model": "m" * 65},
        {"model": ""},
        {"effort": "extreme"},
        {"runtime": "codex", "effort": "max"},
        {"profile": 3},
        {"model": "x\x1b[2J"},
        {"role": "x" * 201},
    ],
)
def test_bad_field_values(w: World, over: dict[str, Any]) -> None:
    w.write({"version": 1, "agents": [w.row(**over)]})
    assert not w.check().ok


@pytest.mark.parametrize("effort", ["low", "medium", "high", "xhigh", "max"])
def test_claude_effort_enum(w: World, effort: str) -> None:
    w.write({"version": 1, "agents": [w.row(effort=effort)]})
    assert w.check().ok


def test_duplicate_names(w: World) -> None:
    w.write({"version": 1, "agents": [w.row(), w.row()]})
    assert "schema" in w.codes()


def test_row_limit(w: World) -> None:
    rows = [w.row(name=f"a{i}") for i in range(51)]
    w.write({"version": 1, "agents": rows})
    assert "schema" in w.codes()
    w.write({"version": 1, "agents": rows[:50]})
    assert "schema" not in w.codes()


def test_agents_must_be_a_list(w: World) -> None:
    w.write({"version": 1, "agents": {}})
    assert "schema" in w.codes()


@pytest.mark.parametrize(
    "options, ok",
    [
        (["--permission-mode plan"], True),
        (["--permission-mode default", "--permission-mode plan"], False),
        (["--permission-mode nonsense"], False),
        (["--resume abc"], False),
        (["--model other"], False),
        (["--session-id abc"], False),
        (["--append-system-prompt-file /etc/passwd"], False),
        (["--settings x.json"], False),
        (["--permission-mode"], False),
        (["--permission-mode plan extra"], False),
        ("--permission-mode plan", False),
        ([3], False),
    ],
)
def test_claude_options_allowlist(w: World, options: Any, ok: bool) -> None:
    w.write({"version": 1, "agents": [w.row(options=options)]})
    assert w.check().ok is ok


def test_codex_options_allowlist(w: World) -> None:
    w.card("worker", w.biz / "core" / "roles")
    good = w.row(runtime="codex", role="worker", name="worker", options=["--sandbox read-only"])
    w.write({"version": 1, "agents": [good]})
    assert w.check().ok
    bad = w.row(runtime="codex", role="worker", name="worker", options=["--permission-mode plan"])
    w.write({"version": 1, "agents": [bad]})
    assert not w.check().ok


def test_declared_work_shape(w: World) -> None:
    ok = [{"name": "nightly", "kind": "cron", "schedule": "0 3 * * *", "prompt_file": "a.md"}]
    w.write({"version": 1, "agents": [w.row(declared_work=ok)]})
    assert w.check().ok
    for bad in (
        [{"name": "n", "kind": "daemon"}],
        [{"name": "N", "kind": "cron"}],
        [{"name": "n", "kind": "cron", "extra": 1}],
        [{"kind": "cron"}],
        {"name": "n", "kind": "cron"},
        [{"name": "n", "kind": "cron", "prompt_file": "../x"}],
    ):
        w.write({"version": 1, "agents": [w.row(declared_work=bad)]})
        assert not w.check().ok, bad


def test_named_agent_must_exist(w: World) -> None:
    assert w.check("planner").ok
    assert w.codes(name="nobody") == ["unknown-agent"]


# --- cwd ----------------------------------------------------------------------------


def test_cwd_must_be_absolute_and_normal(w: World) -> None:
    for cwd in ("biz", "~/biz", f"{w.biz}/", f"{w.biz}/../biz", f"{w.biz}/./"):
        w.write({"version": 1, "agents": [w.row(cwd=cwd)]})
        assert "cwd" in w.codes(), cwd


def test_cwd_must_be_under_home(w: World) -> None:
    outside = w.mkdir(w.floor / "outside")
    w.write({"version": 1, "agents": [w.row(cwd=str(outside))]})
    assert "cwd" in w.codes()
    w.write({"version": 1, "agents": [w.row(cwd=str(w.home))]})
    assert "cwd" in w.codes()


def test_cwd_missing(w: World) -> None:
    w.write({"version": 1, "agents": [w.row(cwd=str(w.home / "nope"))]})
    assert "cwd" in w.codes()


def test_cwd_symlink_refused(w: World) -> None:
    link = w.home / "link"
    link.symlink_to(w.biz)
    w.write({"version": 1, "agents": [w.row(cwd=str(link))]})
    assert "unsafe-path" in w.codes()


def test_cwd_group_writable(w: World) -> None:
    w.biz.chmod(0o770)
    assert "unsafe-path" in w.codes()


def test_cwd_need_not_be_a_business_repo(w: World) -> None:
    plain = w.mkdir(w.home / "plain")
    w.card("planner", w.cards)
    w.write({"version": 1, "agents": [w.row(cwd=str(plain))]})
    assert w.check().ok


# --- cards: fixed locations ---------------------------------------------------------


def test_card_in_roles_dir_of_cwd(w: World) -> None:
    assert w.check().ok


def test_card_missing_for_claude(w: World) -> None:
    (w.biz / "core" / "roles" / "planner.md").unlink()
    assert w.codes() == ["card"]


def test_shared_card_is_never_a_fallback_for_a_roles_dir(w: World) -> None:
    (w.biz / "core" / "roles" / "planner.md").unlink()
    w.card("planner", w.cards)
    assert w.codes() == ["card"]


def test_shared_card_when_cwd_has_no_roles_dir(w: World) -> None:
    plain = w.mkdir(w.home / "plain")
    w.write({"version": 1, "agents": [w.row(cwd=str(plain))]})
    assert w.codes() == ["card"]
    w.card("planner", w.cards)
    assert w.check().ok


def test_codex_without_card_is_not_an_error(w: World) -> None:
    (w.biz / "core" / "roles" / "planner.md").unlink()
    w.write({"version": 1, "agents": [w.row(runtime="codex")]})
    report = w.check()
    assert report.ok
    assert any("no-adapter" in n for n in report.notes)


def test_codex_card_that_exists_is_still_validated(w: World) -> None:
    (w.biz / "core" / "roles" / "planner.md").write_text("not a card")
    w.write({"version": 1, "agents": [w.row(runtime="codex")]})
    assert w.codes() == ["card"]


def test_card_name_must_equal_role(w: World) -> None:
    path = w.biz / "core" / "roles" / "planner.md"
    path.write_text(CARD.format(role="someone-else"))
    assert w.codes() == ["card"]


def test_card_bad_frontmatter(w: World) -> None:
    (w.biz / "core" / "roles" / "planner.md").write_text("---\nname: planner\n---\n")
    assert set(w.codes()) == {"card"}


def test_card_too_large(w: World) -> None:
    path = w.biz / "core" / "roles" / "planner.md"
    path.write_text(CARD.format(role="planner") + "x" * 70_000)
    assert w.codes() == ["card"]


@pytest.mark.parametrize("mode", [0o660, 0o606, 0o666])
def test_card_writable_by_others(w: World, mode: int) -> None:
    (w.biz / "core" / "roles" / "planner.md").chmod(mode)
    assert "unsafe-path" in w.codes()


def test_card_symlink_refused(w: World) -> None:
    path = w.biz / "core" / "roles" / "planner.md"
    real = w.home / "real-card.md"
    real.write_text(path.read_text())
    real.chmod(0o600)
    path.unlink()
    path.symlink_to(real)
    assert "unsafe-path" in w.codes()


def test_card_dir_symlink_refused(w: World) -> None:
    roles = w.biz / "core" / "roles"
    moved = w.home / "moved-roles"
    roles.rename(moved)
    roles.symlink_to(moved)
    assert "unsafe-path" in w.codes()


def test_card_must_be_a_regular_file(w: World) -> None:
    path = w.biz / "core" / "roles" / "planner.md"
    path.unlink()
    path.mkdir()
    assert "card" in w.codes() or "unsafe-path" in w.codes()
    path.rmdir()
    os.mkfifo(path, 0o600)
    assert not w.check().ok


def test_card_writable_ancestor(w: World) -> None:
    (w.biz / "core").chmod(0o770)
    assert "unsafe-path" in w.codes()


# --- profiles -----------------------------------------------------------------------


def profile_dir(w: World, name: str = "p1") -> Path:
    return w.mkdir(w.home / "profiles" / name)


def test_named_profile_ok(w: World) -> None:
    claude = profile_dir(w)
    w.write(
        {
            "version": 1,
            "profiles": {"alt": {"claude": str(claude)}},
            "agents": [w.row(profile="alt")],
        }
    )
    assert w.check().ok


def test_unknown_profile(w: World) -> None:
    w.write({"version": 1, "agents": [w.row(profile="ghost")]})
    assert "profile" in w.codes()


def test_profile_without_the_rows_runtime(w: World) -> None:
    codex = profile_dir(w)
    w.write(
        {
            "version": 1,
            "profiles": {"alt": {"codex": str(codex)}},
            "agents": [w.row(profile="alt")],
        }
    )
    assert "profile" in w.codes()


def test_default_cannot_be_redefined(w: World) -> None:
    claude = profile_dir(w)
    w.write({"version": 1, "profiles": {"default": {"claude": str(claude)}}, "agents": []})
    assert "profile" in w.codes()


@pytest.mark.parametrize("bad", ["rel/dir", "~/x", "", 3, ["a"]])
def test_profile_path_shape(w: World, bad: Any) -> None:
    w.write({"version": 1, "profiles": {"alt": {"claude": bad}}, "agents": []})
    assert not w.check().ok


def test_profile_unknown_runtime_key(w: World) -> None:
    claude = profile_dir(w)
    w.write({"version": 1, "profiles": {"alt": {"claude": str(claude), "x": "/a"}}, "agents": []})
    assert not w.check().ok


def test_profile_missing_dir(w: World) -> None:
    w.write({"version": 1, "profiles": {"alt": {"claude": str(w.home / "nope")}}, "agents": []})
    assert "profile" in w.codes()


def test_profile_must_be_its_own_realpath(w: World) -> None:
    claude = profile_dir(w)
    link = w.home / "profile-link"
    link.symlink_to(claude)
    w.write({"version": 1, "profiles": {"alt": {"claude": str(link)}}, "agents": []})
    assert not w.check().ok


@pytest.mark.parametrize("mode", [0o770, 0o707, 0o777])
def test_profile_writable_dir(w: World, mode: int) -> None:
    claude = profile_dir(w)
    claude.chmod(mode)
    w.write({"version": 1, "profiles": {"alt": {"claude": str(claude)}}, "agents": []})
    assert "unsafe-path" in w.codes()


def test_default_profile_dirs_checked_when_present(w: World) -> None:
    claude = w.mkdir(w.home / ".claude")
    assert w.check().ok
    claude.chmod(0o770)
    assert "unsafe-path" in w.codes()
    claude.chmod(0o700)
    (w.home / ".claude.json").write_text("{}")
    (w.home / ".claude.json").chmod(0o666)
    assert "unsafe-path" in w.codes()


def test_default_profile_dir_absent_is_reported_not_failed(w: World) -> None:
    report = w.check()
    assert report.ok
    assert any("absent" in n for n in report.notes)


def test_default_profile_symlink_refused(w: World) -> None:
    real = w.mkdir(w.home / "real-claude")
    (w.home / ".claude").symlink_to(real)
    assert "unsafe-path" in w.codes()


def test_codex_default_dir_checked_for_codex_rows(w: World) -> None:
    codex = w.mkdir(w.home / ".codex")
    codex.chmod(0o770)
    assert w.check().ok  # the only row is Claude
    w.write({"version": 1, "agents": [w.row(runtime="codex")]})
    assert "unsafe-path" in w.codes()


# --- path list ----------------------------------------------------------------------


def test_default_path_is_used_and_checked(w: World) -> None:
    report = w.check()
    assert report.path == [str(w.bin)]
    w.bin.chmod(0o770)
    assert "unsafe-path" in w.codes()


def test_listed_path_ok_and_reported_in_order(w: World) -> None:
    other = w.mkdir(w.floor / "other")
    w.write({"version": 1, "path": [str(other), str(w.bin)], "agents": [w.row()]})
    assert w.check().path == [str(other), str(w.bin)]


def test_unsafe_listed_dir_is_named(w: World) -> None:
    other = w.mkdir(w.floor / "other")
    other.chmod(0o777)
    w.write({"version": 1, "path": [str(w.bin), str(other)], "agents": [w.row()]})
    problems = w.check().problems
    assert [p.code for p in problems] == ["unsafe-path"]
    assert str(other) in problems[0].where


def test_missing_listed_dir_is_skipped_and_not_executed(w: World) -> None:
    ghost = w.floor / "ghost"
    w.write({"version": 1, "path": [str(ghost), str(w.bin)], "agents": [w.row()]})
    report = w.check()
    assert report.ok
    assert report.path == [str(w.bin)]
    assert report.skipped == [str(ghost)]


def test_missing_dir_under_unsafe_ancestor_is_refused(w: World) -> None:
    open_dir = w.mkdir(w.floor / "open")
    open_dir.chmod(0o777)
    w.write({"version": 1, "path": [str(open_dir / "bin")], "agents": [w.row()]})
    assert "unsafe-path" in w.codes()


@pytest.mark.parametrize("bad", ["bin", "~/bin", "", "/a:/b", "/a/../b", "/a//b", 3])
def test_path_entry_shape(w: World, bad: Any) -> None:
    w.write({"version": 1, "path": [bad], "agents": [w.row()]})
    assert not w.check().ok


def test_path_must_not_be_empty(w: World) -> None:
    w.write({"version": 1, "path": [], "agents": [w.row()]})
    assert "schema" in w.codes()


def test_path_entry_must_be_a_directory(w: World) -> None:
    file = w.floor / "file"
    file.write_text("x")
    file.chmod(0o600)
    w.write({"version": 1, "path": [str(file)], "agents": [w.row()]})
    assert "unsafe-path" in w.codes()


def test_symlinked_path_dir_through_checked_dirs_is_allowed(w: World) -> None:
    link = w.floor / "bin-link"
    link.symlink_to(w.bin)
    w.write({"version": 1, "path": [str(link)], "agents": [w.row()]})
    assert w.check().ok


def test_symlink_into_unsafe_dir_is_refused(w: World) -> None:
    bad = w.mkdir(w.floor / "bad")
    bad.chmod(0o777)
    link = w.floor / "bin-link"
    link.symlink_to(bad)
    w.write({"version": 1, "path": [str(link)], "agents": [w.row()]})
    assert "unsafe-path" in w.codes()


def test_symlink_loop_is_refused(w: World) -> None:
    loop = w.floor / "loop"
    loop.symlink_to(loop)
    w.write({"version": 1, "path": [str(loop)], "agents": [w.row()]})
    assert "unsafe-path" in w.codes()


# --- start_file ---------------------------------------------------------------------


def test_start_file_ok(w: World) -> None:
    (w.biz / "START.md").write_text("go")
    (w.biz / "START.md").chmod(0o600)
    w.write({"version": 1, "agents": [w.row(start_file="START.md")]})
    assert w.check().ok


@pytest.mark.parametrize("bad", ["/etc/passwd", "../x", "a/../../x", "~/x", "", "x\ny"])
def test_start_file_shape(w: World, bad: str) -> None:
    w.write({"version": 1, "agents": [w.row(start_file=bad)]})
    assert not w.check().ok


def test_start_file_missing(w: World) -> None:
    w.write({"version": 1, "agents": [w.row(start_file="START.md")]})
    assert "start_file" in w.codes()


def test_start_file_symlink_refused(w: World) -> None:
    target = w.home / "secret.md"
    target.write_text("x")
    (w.biz / "START.md").symlink_to(target)
    w.write({"version": 1, "agents": [w.row(start_file="START.md")]})
    assert "unsafe-path" in w.codes()


def test_start_file_writable_by_group(w: World) -> None:
    (w.biz / "START.md").write_text("go")
    (w.biz / "START.md").chmod(0o660)
    w.write({"version": 1, "agents": [w.row(start_file="START.md")]})
    assert "unsafe-path" in w.codes()


# --- command ------------------------------------------------------------------------


@pytest.fixture
def local(w: World, monkeypatch: pytest.MonkeyPatch) -> World:
    monkeypatch.setattr(ap.Host, "local", classmethod(lambda cls: w.host))
    return w


def test_cli_valid_says_policy_valid_only(local: World) -> None:
    result = CliRunner().invoke(app, ["agent", "check"])
    assert result.exit_code == 0
    first, *rest = result.output.splitlines()
    assert first == "Policy valid."
    assert all(line.startswith("  note: ") for line in rest)


@pytest.mark.parametrize(
    ("runtime", "option"),
    [
        ("claude", "--permission-mode bypassPermissions"),
        ("codex", "--sandbox danger-full-access"),
    ],
)
def test_most_permissive_mode_is_allowed_but_noted(local: World, runtime: str, option: str) -> None:
    local.write({"version": 1, "agents": [local.row(runtime=runtime, options=[option])]})
    assert local.check().ok
    result = CliRunner().invoke(app, ["agent", "check"])
    assert result.exit_code == 0
    first, *rest = result.output.splitlines()
    assert first == "Policy valid."
    assert rest[0] == f"  note: planner: {option} is the most permissive mode; allowed, not safe"
    assert all(line.startswith("  note: ") for line in rest)


@pytest.mark.parametrize(
    ("runtime", "option"),
    [("claude", "--permission-mode acceptEdits"), ("codex", "--sandbox workspace-write")],
)
def test_other_modes_carry_no_note(local: World, runtime: str, option: str) -> None:
    local.write({"version": 1, "agents": [local.row(runtime=runtime, options=[option])]})
    assert local.check().warnings == []


def test_note_is_kept_when_the_policy_is_not_valid(local: World) -> None:
    local.write(
        {
            "version": 1,
            "agents": [
                local.row(options=["--permission-mode bypassPermissions"]),
                local.row(name="second", role="nobody"),
            ],
        }
    )
    result = CliRunner().invoke(app, ["agent", "check"])
    assert result.exit_code == 2
    assert "Policy not valid." in result.output
    assert "most permissive mode" in result.output


def test_cli_invalid_exits_2_and_names_the_problem(local: World) -> None:
    local.biz.chmod(0o777)
    result = CliRunner().invoke(app, ["agent", "check"])
    assert result.exit_code == 2
    assert "unsafe-path" in result.output
    assert str(local.biz) in result.output
    assert "policy valid" not in result.output.lower()


def test_cli_named_agent(local: World) -> None:
    assert CliRunner().invoke(app, ["agent", "check", "planner"]).exit_code == 0
    result = CliRunner().invoke(app, ["agent", "check", "nobody"])
    assert result.exit_code == 2
    assert "unknown-agent" in result.output


def test_cli_missing_policy(local: World) -> None:
    (local.store / "agents.json").unlink()
    result = CliRunner().invoke(app, ["agent", "check"])
    assert result.exit_code == 2
    assert "policy-missing" in result.output


def test_cli_hostile_text_is_not_echoed_raw(local: World) -> None:
    local.write({"version": 1, "agents": [local.row(model="\x1b[2Jevil")]})
    result = CliRunner().invoke(app, ["agent", "check"])
    assert result.exit_code == 2
    assert "\x1b" not in result.output


def test_agent_module_never_signals_or_launches() -> None:
    source = Path(ap.__file__).read_text()
    for banned in ("os.kill", "killpg", "subprocess", "os.exec", "os.fork", "fcntl"):
        assert banned not in source, banned


@pytest.mark.parametrize("bad", [{"model": "bad model"}, {"effort": "extreme"}])
def test_note_is_kept_for_a_row_with_an_unrelated_schema_error(
    local: World, bad: dict[str, Any]
) -> None:
    row = local.row(options=["--permission-mode bypassPermissions"], **bad)
    local.write({"version": 1, "agents": [row]})
    report = local.check()
    assert "schema" in [p.code for p in report.problems]
    assert report.warnings == [
        "planner: --permission-mode bypassPermissions is the most permissive mode; "
        "allowed, not safe"
    ]


def test_note_survives_a_row_with_odd_name_and_options(local: World) -> None:
    local.write(
        {
            "version": 1,
            "agents": [
                {"name": 3, "options": ["--sandbox danger-full-access", 7]},
                {"options": "--sandbox danger-full-access"},
                "not a row",
            ],
        }
    )
    assert local.check().warnings == [
        "agents[0]: --sandbox danger-full-access is the most permissive mode; allowed, not safe"
    ]


@pytest.mark.parametrize("control", ["\u202e", "\u202a", "\u2066", "\u200b", "\u200f", "\ufeff"])
def test_note_label_carries_no_unicode_format_control(local: World, control: str) -> None:
    row = local.row(name=f"spoof{control}abc", options=["--permission-mode bypassPermissions"])
    local.write({"version": 1, "agents": [row]})
    report = local.check()
    assert not report.ok
    rendered = ap.human_report(report)
    assert "most permissive mode" in rendered
    assert control not in rendered
    assert "spoofabc: --permission-mode bypassPermissions" in rendered


def test_cli_prints_the_notes_a_valid_codex_row_carries(local: World) -> None:
    (local.biz / "core" / "roles" / "planner.md").unlink()
    local.write({"version": 1, "agents": [local.row(runtime="codex")]})
    result = CliRunner().invoke(app, ["agent", "check"])
    assert result.exit_code == 0
    assert "  note: planner: card: unverified(no-adapter)" in result.output
    assert "  note: default codex profile:" in result.output
