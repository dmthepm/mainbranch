"""`mb feedback` — local friction log, rollup and self-logged refusals (#986)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from mb import connect as connect_mod
from mb import feedback as feedback_mod
from mb.cli import app

runner = CliRunner()
NOW = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def state_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    state = tmp_path / "state"
    monkeypatch.setenv("XDG_STATE_HOME", str(state))
    monkeypatch.delenv("MB_FEEDBACK_LOG", raising=False)
    return state


def _log(state: Path) -> Path:
    return state / "mainbranch" / "feedback.jsonl"


def _lines(state: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in _log(state).read_text(encoding="utf-8").splitlines()]


def test_feedback_appends_one_line_under_xdg_state_home(state_home: Path, tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["feedback", "status said ready", "but", "test failed", "--command", "mb connect test"],
    )
    assert result.exit_code == 0, result.output
    assert "nothing was sent" in result.stdout
    [entry] = _lines(state_home)
    assert entry["kind"] == "feedback"
    assert entry["command"] == "mb connect test"
    assert entry["text"] == "status said ready but test failed"
    assert entry["repo_kind"] in {"hub", "child", "engine", "none"}
    assert isinstance(entry["mb_version"], str) and entry["mb_version"]
    assert str(entry["time"]).endswith("Z")
    assert set(entry) == {"schema", "kind", "time", "mb_version", "command", "repo_kind", "text"}


def test_feedback_default_state_dir_is_local_state(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert (
        feedback_mod.feedback_path()
        == tmp_path / ".local" / "state" / "mainbranch" / "feedback.jsonl"
    )


def test_feedback_json_envelope(state_home: Path) -> None:
    result = runner.invoke(app, ["feedback", "confusing message", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["mb_command"] == "mb feedback"
    assert payload["result_schema"]["name"] == "mainbranch.feedback.v1"
    assert payload["sent"] is False
    assert payload["entry"]["command"] is None
    assert payload["path"] == "$XDG_STATE_HOME/mainbranch/feedback.jsonl"
    assert str(state_home) not in result.stdout


def test_feedback_empty_text_exits_two(state_home: Path) -> None:
    assert runner.invoke(app, ["feedback"]).exit_code == 2
    assert runner.invoke(app, ["feedback", "   "]).exit_code == 2
    assert not _log(state_home).exists()


@pytest.mark.parametrize(
    "secret_text",
    [
        "token=abcd1234efgh5678ijkl",
        "Authorization: Bearer abcd1234efgh5678ijkl",
        "api_key: abcd1234efgh5678ijkl",
        "pasted ghp_abcd1234efgh5678ijkl by mistake",
        "the access token abcd1234efgh5678ijkl was refused",
    ],
)
def test_feedback_scrubs_secret_values(state_home: Path, secret_text: str) -> None:
    result = runner.invoke(app, ["feedback", secret_text, "--command", f"mb connect {secret_text}"])
    assert result.exit_code == 0
    raw = _log(state_home).read_text(encoding="utf-8")
    assert "abcd1234efgh5678ijkl" not in raw
    assert "<redacted>" in raw


def test_feedback_replaces_home_paths(
    state_home: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = tmp_path / "home" / "someone"
    monkeypatch.setenv("HOME", str(home))
    text = f"mb status crashed in {home}/Work/biz and /Users/other/biz and /home/third/biz"
    result = runner.invoke(app, ["feedback", text])
    assert result.exit_code == 0
    [entry] = _lines(state_home)
    assert entry["text"] == "mb status crashed in ~/Work/biz and ~/biz and ~/biz"
    assert str(home) not in _log(state_home).read_text(encoding="utf-8")
    assert "/Users/other" not in entry["text"]


def test_feedback_file_is_private(state_home: Path) -> None:
    runner.invoke(app, ["feedback", "hello"])
    assert _log(state_home).stat().st_mode & 0o777 == 0o600


def test_record_refusal_logs_rule_and_command_only(state_home: Path) -> None:
    assert feedback_mod.record_refusal("connect.metadata_sensitive", "mb connect meta")
    [entry] = _lines(state_home)
    assert entry["kind"] == "refusal"
    assert entry["rule"] == "connect.metadata_sensitive"
    assert entry["command"] == "mb connect meta"
    assert "text" not in entry


def test_record_refusal_opt_out(state_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MB_FEEDBACK_LOG", "0")
    assert feedback_mod.record_refusal("connect.config_boundary", "mb connect") is False
    assert not _log(state_home).exists()


def test_record_refusal_never_raises(state_home: Path) -> None:
    state_home.mkdir(parents=True)
    (state_home / "mainbranch").write_text("not a directory", encoding="utf-8")
    assert feedback_mod.record_refusal("connect.config_boundary", "mb connect") is False


def test_connect_boundary_exit_logs_refusal_without_message(
    state_home: Path, tmp_path: Path
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "elsewhere").mkdir()
    (repo / ".mb").symlink_to(repo / "elsewhere")
    result = runner.invoke(app, ["connect", "list", "--repo", str(repo)])
    assert result.exit_code == 2
    [entry] = _lines(state_home)
    assert entry == {
        "schema": 1,
        "kind": "refusal",
        "time": entry["time"],
        "mb_version": entry["mb_version"],
        "command": "mb connect list",
        "rule": "connect.config_boundary",
        "repo_kind": entry["repo_kind"],
    }


def test_connect_boundary_exit_respects_opt_out(
    state_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MB_FEEDBACK_LOG", "0")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "elsewhere").mkdir()
    (repo / ".mb").symlink_to(repo / "elsewhere")
    assert runner.invoke(app, ["connect", "list", "--repo", str(repo)]).exit_code == 2
    assert not _log(state_home).exists()


def _seed(state: Path) -> Path:
    path = _log(state)
    feedback_mod.record(
        "old note", command="mb status", path=path, now=datetime(2026, 9, 1, tzinfo=timezone.utc)
    )
    feedback_mod.record(
        "first",
        command="mb connect test",
        path=path,
        now=datetime(2026, 9, 30, tzinfo=timezone.utc),
    )
    feedback_mod.record(
        "second",
        command="mb connect test",
        path=path,
        now=datetime(2026, 10, 2, tzinfo=timezone.utc),
    )
    feedback_mod.record("loose", path=path, now=datetime(2026, 10, 1, tzinfo=timezone.utc))
    with path.open("a", encoding="utf-8") as handle:
        for day in (29, 30):
            handle.write(
                json.dumps(
                    {
                        "schema": 1,
                        "kind": "refusal",
                        "time": f"2026-09-{day}T10:00:00Z",
                        "mb_version": "0.5.3",
                        "command": "mb connect",
                        "rule": "connect.config_boundary",
                        "repo_kind": "hub",
                    }
                )
                + "\n"
            )
        handle.write("{not json\n")
    return path


def test_rollup_groups_by_command_and_rule(state_home: Path) -> None:
    path = _seed(state_home)
    result = feedback_mod.rollup(since="7d", path=path, now=NOW)
    assert result["total"] == 5
    assert result["skipped_lines"] == 1
    groups = {(g["kind"], g["command"], g["rule"]): g for g in result["groups"]}
    refusal = groups[("refusal", "mb connect", "connect.config_boundary")]
    assert refusal["count"] == 2
    assert refusal["oldest"] == "2026-09-29T10:00:00Z"
    assert refusal["newest"] == "2026-09-30T10:00:00Z"
    connect = groups[("feedback", "mb connect test", None)]
    assert connect["count"] == 2 and connect["texts"] == ["first", "second"]
    assert ("feedback", "mb status", None) not in groups
    assert result["groups"][0]["kind"] == "refusal"
    markdown = result["markdown"]
    assert markdown.startswith("# mb feedback rollup")
    assert "| `connect.config_boundary` | `mb connect` | 2 |" in markdown
    assert "### `mb connect test`: 2 entries" in markdown
    assert "### No command given: 1 entry" in markdown
    assert "- second" in markdown


def test_rollup_cli_markdown_and_json(state_home: Path) -> None:
    _seed(state_home)
    result = runner.invoke(app, ["feedback", "rollup", "--since", "2026-09-01"])
    assert result.exit_code == 0
    assert "## Refusals" in result.stdout and "`mb status`" in result.stdout
    payload = json.loads(
        runner.invoke(app, ["feedback", "rollup", "--since", "60d", "--json"]).stdout
    )
    assert payload["mb_command"] == "mb feedback rollup"
    assert payload["total"] >= 5
    assert payload["markdown"].startswith("# mb feedback rollup")


def test_rollup_empty_and_bad_since(state_home: Path) -> None:
    result = runner.invoke(app, ["feedback", "rollup"])
    assert result.exit_code == 0
    assert "No feedback or refusals in this window." in result.stdout
    bad = runner.invoke(app, ["feedback", "rollup", "--since", "lately", "--json"])
    assert bad.exit_code == 2
    assert json.loads(bad.stdout)["errors"][0]["code"] == "invalid_since"


def test_list_newest_with_filters(state_home: Path) -> None:
    path = _seed(state_home)
    result = feedback_mod.list_entries(limit=2, path=path)
    assert result["total"] == 6 and result["shown"] == 2
    assert [item["time"] for item in result["entries"]] == [
        "2026-10-01T00:00:00Z",
        "2026-10-02T00:00:00Z",
    ]
    refusals = feedback_mod.list_entries(kind="refusal", limit=0, path=path)
    assert refusals["total"] == 2
    cli = runner.invoke(app, ["feedback", "list", "--kind", "refusal"])
    assert cli.exit_code == 0
    assert "rule=connect.config_boundary" in cli.stdout
    assert runner.invoke(app, ["feedback", "list", "--kind", "other"]).exit_code == 2


def test_clear_before_date(state_home: Path) -> None:
    path = _seed(state_home)
    assert runner.invoke(app, ["feedback", "clear"]).exit_code == 2
    result = runner.invoke(app, ["feedback", "clear", "--before", "2026-09-30", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["removed"] == 2
    assert payload["removed_unreadable"] == 1
    assert payload["kept"] == 4
    times = [entry["time"] for entry in _lines(state_home)]
    assert min(times) >= "2026-09-30"
    assert path.stat().st_mode & 0o777 == 0o600


def test_clear_missing_file_is_ok(state_home: Path) -> None:
    result = runner.invoke(app, ["feedback", "clear", "--before", "2026-10-01"])
    assert result.exit_code == 0
    assert "Removed 0 entries" in result.stdout


def test_subcommand_rejects_extra_words(state_home: Path) -> None:
    assert runner.invoke(app, ["feedback", "list", "extra"]).exit_code == 2


def test_write_failure_exits_one(state_home: Path) -> None:
    state_home.mkdir(parents=True)
    (state_home / "mainbranch").write_text("not a directory", encoding="utf-8")
    result = runner.invoke(app, ["feedback", "hello", "--json"])
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["errors"][0]["code"] == "feedback_write_failed"


def test_feedback_scrubs_other_absolute_paths_and_url_secrets(state_home: Path) -> None:
    text = "log at /private/tmp/run/x.log and C:\\work\\biz, url https://x.test/?token=abcd1234efgh"
    assert runner.invoke(app, ["feedback", text]).exit_code == 0
    [entry] = _lines(state_home)
    assert "/private/tmp" not in entry["text"]
    assert "C:\\work" not in entry["text"]
    assert "abcd1234efgh" not in entry["text"]
    assert entry["text"].count("<local-path>") == 2


# Synthetic canary only; never a real credential.
CANARY = "Zq7canary" + "0123456789abcdef"

SECRET_SHAPES = {
    "assignment": f"token={CANARY}",
    "bearer": f"Authorization: Bearer {CANARY}",
    "json_double_quoted": f'{{"token": "{CANARY}"}}',
    "json_single_quoted": f"{{'api_key': '{CANARY}'}}",
    "json_client_secret": f'{{"client_secret":"{CANARY}"}}',
    "env_assignment": f"GITHUB_TOKEN={CANARY}",
    "env_export_quoted": f'export AWS_SECRET_ACCESS_KEY="{CANARY}"',
    "env_prefixed_key": f"STRIPE_API_KEY={CANARY}",
    "ghp": f"ghp_{CANARY}",
    "ghs": f"ghs_{CANARY}",
    "gho": f"gho_{CANARY}",
    "ghu": f"ghu_{CANARY}",
    "ghr": f"ghr_{CANARY}",
    "github_pat": f"github_pat_{CANARY}",
    "openai_project": f"sk-proj-{CANARY}",
    "slack": f"xoxb-{CANARY}",
    "aws_key_id": "AKIA" + "Z7Q" * 5 + "Z",
    "url_token": f"https://x.test/cb?token={CANARY}",
    "url_access_token": f"https://x.test/cb?access_token={CANARY}",
    "url_api_key": f"https://x.test/cb?api_key={CANARY}",
    "url_client_secret": f"https://x.test/cb?client_id=abc&client_secret={CANARY}",
    "url_signature": f"https://x.test/f?X-Amz-Signature={CANARY}",
    "url_userinfo": f"https://someone:{CANARY}@x.test/repo.git",
    "dsn_userinfo": f"postgres://app:{CANARY}@db.internal:5432/main",
    "basic_auth": f"Authorization: Basic {CANARY}",
    "json_apostrophe": f'{{"token": "it\'s-{CANARY}"}}',
    "json_escaped_quote": f'{{"token": "a\\"{CANARY}"}}',
    "env_quoted_space_semicolon": f'export X_TOKEN="abc def;{CANARY}"',
    "env_single_with_double": f"X_SECRET='a \"b\" {CANARY}'",
    "env_unterminated_quote": f'X_TOKEN="abc {CANARY}',
}


def _secret_leaks(value: str) -> bool:
    return CANARY in value or "Z7QZ7QZ7Q" in value


@pytest.mark.parametrize("shape", sorted(SECRET_SHAPES))
def test_every_secret_shape_is_scrubbed_in_every_field(state_home: Path, shape: str) -> None:
    hostile = f"mb connect said {SECRET_SHAPES[shape]} then stopped"
    feedback_mod.record(hostile, command=f"mb connect {SECRET_SHAPES[shape]}")
    assert feedback_mod.record_refusal(hostile, hostile)
    raw = _log(state_home).read_text(encoding="utf-8")
    assert not _secret_leaks(raw), shape
    for entry in _lines(state_home):
        for field in ("text", "command", "rule"):
            assert not _secret_leaks(str(entry.get(field) or "")), (shape, field)


def test_scrub_keeps_ordinary_urls_and_words() -> None:
    text = (
        "see https://github.com/noontide-co/mainbranch/issues/986?tab=comments and the token flow"
    )
    assert feedback_mod.scrub(text) == text


# shape -> (path, text that must not survive)
PATH_SHAPES = {
    "users": ("/Users/someone/biz/notes.md", "/Users/someone"),
    "home": ("/home/someone/biz/notes.md", "/home/someone"),
    "tmp": ("/tmp/run-42/out.log", "run-42"),
    "etc": ("/etc/acme/config.yaml", "acme"),
    "srv": ("/srv/acme-repo/core/offer.md", "acme"),
    "root": ("/root/acme/core/offer.md", "acme"),
    "mnt": ("/mnt/data/acme/core.md", "acme"),
    "workspace": ("/workspace/acme/core/offer.md", "acme"),
    "opt": ("/opt/acme/run.sh", "acme"),
    "windows_backslash": ("C:\\Users\\someone\\biz\\notes.md", "someone"),
    "windows_forward": ("C:/Users/someone/biz/notes.md", "someone"),
    "windows_other_drive": ("D:/work/acme/notes.md", "acme"),
    "unc": ("\\\\fileserver\\share\\biz\\notes.md", "fileserver"),
    "colon_prose": ("failed:/srv/private-project/config.yaml", "private-project"),
    "unc_forward": ("//fileserver/private-project/config.yaml", "fileserver"),
    "quoted_with_space": ('"/srv/private project/config.yaml"', "project/config"),
    "quoted_windows_space": ("'C:\\Program Files\\private-project\\x.cfg'", "private-project"),
}


@pytest.mark.parametrize("shape", sorted(PATH_SHAPES))
def test_every_absolute_path_shape_is_scrubbed_in_every_field(state_home: Path, shape: str) -> None:
    path, marker = PATH_SHAPES[shape]
    hostile = f"mb status failed reading {path} today"
    feedback_mod.record(hostile, command=f"mb status --repo {path}")
    assert feedback_mod.record_refusal(f"rule {path}", f"mb connect {path}")
    for entry in _lines(state_home):
        for field in ("text", "command", "rule"):
            value = str(entry.get(field) or "")
            assert marker not in value, (shape, field, value)
            if field == "text" and entry["kind"] == "feedback":
                assert "~" in value or "<local-path>" in value, (shape, field, value)


def test_path_scrub_keeps_urls_slash_commands_and_home_tilde(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = tmp_path / "someone"
    monkeypatch.setenv("HOME", str(home))
    text = (
        "run /mb-start, see https://github.com/noontide-co/mainbranch/blob/main/docs/feedback.md "
        f"and file://x.test/a/b, and {home}/biz/x.md, and/or 1/2"
    )
    assert feedback_mod.scrub(text) == (
        "run /mb-start, see https://github.com/noontide-co/mainbranch/blob/main/docs/feedback.md "
        "and file://x.test/a/b, and ~/biz/x.md, and/or 1/2"
    )


def _good(time: str, text: str) -> bytes:
    entry = {
        "schema": 1,
        "kind": "feedback",
        "time": time,
        "mb_version": "0.5.3",
        "command": "mb status",
        "repo_kind": "hub",
        "text": text,
    }
    return (json.dumps(entry) + "\n").encode()


CORRUPT_LINES = [
    b"\xff\xfe not utf-8 \x80\n",
    b'{"time": "2026-10-02T00:00:00Z", "kind": "feedback", "text": 42}\n',
    b'{"time": "2026-10-02T00:00:00Z", "kind": "feedback", "text": "x", "repo_kind": ["hub"]}\n',
    b'{"time": "2026-10-02T00:00:00Z", "kind": "feedback", "text": "x", "command": {"a": 1}}\n',
    b'{"time": "2026-10-02T00:00:00Z", "kind": "telemetry", "text": "x"}\n',
    b'{"time": 1696000000, "kind": "feedback", "text": "x"}\n',
    b'{"time": "yesterday", "kind": "feedback", "text": "x"}\n',
    b'{"time": "2026-10-02T00:00:00Z", "kind": "refusal", "rule": 7}\n',
    b"[1, 2, 3]\n",
    b"{not json\n",
]


def test_corrupt_records_are_skipped_and_neighbors_kept(state_home: Path) -> None:
    path = _log(state_home)
    path.parent.mkdir(parents=True)
    path.write_bytes(
        _good("2026-10-01T00:00:00Z", "before")
        + b"".join(CORRUPT_LINES)
        + _good("2026-10-02T00:00:00Z", "after")
    )
    listed = runner.invoke(app, ["feedback", "list", "--json"])
    assert listed.exit_code == 0, listed.output
    payload = json.loads(listed.stdout)
    assert [entry["text"] for entry in payload["entries"]] == ["before", "after"]
    assert payload["skipped_lines"] == len(CORRUPT_LINES)
    rolled = runner.invoke(app, ["feedback", "rollup", "--since", "2026-09-01", "--json"])
    assert rolled.exit_code == 0, rolled.output
    assert json.loads(rolled.stdout)["total"] == 2
    human = runner.invoke(app, ["feedback", "rollup", "--since", "2026-09-01"])
    assert human.exit_code == 0 and "- after" in human.stdout
    cleared = runner.invoke(app, ["feedback", "clear", "--before", "2026-01-01", "--json"])
    assert cleared.exit_code == 0
    assert json.loads(cleared.stdout)["removed_unreadable"] == len(CORRUPT_LINES)
    assert [entry["text"] for entry in _lines(state_home)] == ["before", "after"]


def test_record_after_partial_tail_is_still_readable(state_home: Path) -> None:
    path = _log(state_home)
    path.parent.mkdir(parents=True)
    path.write_bytes(_good("2026-10-01T00:00:00Z", "before") + b'{"time": "2026-10-0')
    result = feedback_mod.record("after the crash")
    assert result["ok"] is True
    entries, skipped = feedback_mod.read_entries()
    assert [entry["text"] for entry in entries] == ["before", "after the crash"]
    assert skipped == 1
    assert path.read_bytes().endswith(b"\n")


@pytest.mark.parametrize("since", ["1000000000d", "99999999999h", "9999999w", "36501d"])
def test_oversized_since_is_a_structured_error(state_home: Path, since: str) -> None:
    for sub in ("rollup", "list"):
        result = runner.invoke(app, ["feedback", sub, "--since", since, "--json"])
        assert result.exit_code == 2, result.output
        payload = json.loads(result.stdout)
        assert payload["mb_command"] == f"mb feedback {sub}"
        assert payload["errors"][0]["code"] == "invalid_since"


@pytest.mark.parametrize("sub", [["list"], ["rollup"], ["clear", "--before", "2026-10-01"]])
def test_unreadable_log_is_a_structured_scrubbed_error(state_home: Path, sub: list[str]) -> None:
    _log(state_home).mkdir(parents=True)  # a directory where the file should be
    result = runner.invoke(app, ["feedback", *sub, "--json"])
    assert result.exit_code == 1, result.output
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["errors"][0]["code"] in {"feedback_read_failed", "feedback_clear_failed"}
    assert str(state_home) not in result.stdout
    human = runner.invoke(app, ["feedback", *sub])
    assert human.exit_code == 1
    assert "Traceback" not in human.output and str(state_home) not in human.output


def test_clear_disk_full_is_a_structured_scrubbed_error(
    state_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    feedback_mod.record("keep me")
    target = _log(state_home)

    def disk_full(path: Path, text: str, **_: object) -> None:
        raise OSError(28, "No space left on device", str(path))

    monkeypatch.setattr(feedback_mod, "atomic_write_text", disk_full)
    result = runner.invoke(app, ["feedback", "clear", "--before", "2026-10-01", "--json"])
    assert result.exit_code == 1, result.output
    payload = json.loads(result.stdout)
    assert payload["errors"][0]["code"] == "feedback_clear_failed"
    assert "No space left on device" in payload["errors"][0]["message"]
    assert str(target) not in result.stdout
    assert [entry["text"] for entry in _lines(state_home)] == ["keep me"]


def test_suite_never_writes_the_real_feedback_file(
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    # No state_home fixture here: conftest must already isolate every test,
    # including connect tests that reach the refusal hook.
    assert feedback_mod.feedback_path().is_relative_to(tmp_path_factory.getbasetemp())
    assert feedback_mod.record_refusal("test.isolation", "mb connect")
    assert feedback_mod.feedback_path().is_file()


def _make_repo(root: Path, kind: str) -> Path:
    repo = root / kind
    repo.mkdir()
    if kind == "hub":
        (repo / "core").mkdir()
        (repo / "CLAUDE.md").write_text("# Hub\n", encoding="utf-8")
    elif kind == "child":
        (repo / "research").mkdir()
        (repo / "CLAUDE.md").write_text("# App\n", encoding="utf-8")
        (repo / ".mainbranch").mkdir()
        (repo / ".mainbranch" / "repo.json").write_text(
            json.dumps(
                {
                    "schema": "mb.child_repo.v0",
                    "role": "product",
                    "github_owner": "example-co",
                    "repo_name": "app",
                    "parent": {"github_owner": "example-co", "repo_name": "example"},
                }
            ),
            encoding="utf-8",
        )
    elif kind == "engine":
        (repo / "mb" / "mb").mkdir(parents=True)
        (repo / "mb" / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
        (repo / "mb" / "mb" / "cli.py").write_text("", encoding="utf-8")
    return repo


@pytest.mark.parametrize("kind", ["hub", "child", "engine", "none"])
def test_repo_kind_comes_from_the_shared_classifier(
    state_home: Path, tmp_path: Path, kind: str
) -> None:
    repo = _make_repo(tmp_path, kind)
    result = runner.invoke(app, ["feedback", "noted", "--repo", str(repo), "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["entry"]["repo_kind"] == kind
    assert feedback_mod.record_refusal("test.kind", "mb connect", repo=repo)
    assert _lines(state_home)[-1]["repo_kind"] == kind


def test_repo_kind_is_unknown_when_the_classifier_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from mb import topology

    def broken(repo: object) -> dict[str, str]:
        raise RuntimeError("boom")

    monkeypatch.setattr(topology, "classify_repo", broken)
    assert feedback_mod.repo_kind(tmp_path) == "unknown"


@pytest.mark.parametrize(
    "text",
    [
        "https://example.test/?token_count=25",
        "https://example.test/search?q=token&page=2&sort=desc",
        "set max_tokens=100 and tokenizer=bpe",
        "author=Ana design=x signed=yes",
        "see ./docs/feedback.md and core/offer.md, and/or run /mb-start",
        "file://x.test/a/b and https://github.com/noontide-co/mainbranch/pull/989",
    ],
)
def test_scrub_keeps_ordinary_metadata(text: str) -> None:
    assert feedback_mod.scrub(text) == text


@pytest.mark.parametrize(
    ("given", "stored"),
    [
        ("mb connect test", "mb connect test"),
        ("connect test", "mb connect test"),
        ("mb connect meta --token abc", "mb connect meta"),
        ("mb status --repo /srv/x/y", "mb status"),
        ("mb issue draft bug extra words", "mb issue draft bug"),
        ("mb connect 'quoted'", "mb connect"),
        ("mb", None),
        ("--json", None),
        ("MB STATUS", None),
        ("", None),
    ],
)
def test_command_is_stored_as_the_command_path_only(
    state_home: Path, given: str, stored: str | None
) -> None:
    result = feedback_mod.record("noted", command=given)
    assert result["entry"]["command"] == stored
    assert feedback_mod.record_refusal("connect.config_boundary", given)
    assert _lines(state_home)[-1]["command"] == stored


@pytest.mark.parametrize(
    ("given", "stored"),
    [
        ("connect.config_boundary", "connect.config_boundary"),
        ("connect:metadata-sensitive_2", "connect:metadata-sensitive_2"),
        ("Connect.Boundary", "other"),
        ("rule with spaces", "other"),
        ("token=abc", "other"),
        ("x" * 65, "other"),
        ("", "other"),
    ],
)
def test_rule_is_a_slug_or_other(state_home: Path, given: str, stored: str) -> None:
    assert feedback_mod.record_refusal(given, "mb connect")
    assert _lines(state_home)[-1]["rule"] == stored


# --- Connect refusals through the CLI (phase 2b) -------------------------------

_SYNTHETIC_METADATA_SECRET = "ghp_" + "F4k3" * 9
_SYNTHETIC_BAD_KEY = "not-a-stripe-key-F4k3"
_REFUSAL_FIELDS = {"schema", "kind", "time", "mb_version", "command", "rule", "repo_kind"}


@pytest.fixture
def connect_env(state_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A synthetic business repo with a local-file secret store under ``tmp_path``."""
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "local-file")
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "home"))
    for provider in connect_mod.PROVIDERS:
        for env_var in provider.env_vars:
            monkeypatch.delenv(env_var, raising=False)
    repo = tmp_path / "biz"
    repo.mkdir()
    return repo


def _refusal_exit(rule: str) -> int:
    """The token refusal has its own exit code (#1011); every other refusal exits 2."""
    return connect_mod.TOKEN_REFUSED_EXIT_CODE if rule == "connect.token_print" else 2


def _symlinked_state(repo: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "connect.yaml").write_text("version: 1\nproviders: {}\n", encoding="utf-8")
    (repo / ".mb").symlink_to(outside, target_is_directory=True)


# (argv after `--repo <repo>` is appended, stored command, stored rule, a value that must not leak)
CONNECT_REFUSALS = [
    pytest.param(
        ["connect", "token", "cloudflare"],
        "mb connect token",
        "connect.token_print",
        None,
        id="token_print",
    ),
    pytest.param(
        ["connect", "cloudflare", "--metadata", f"zone_label={_SYNTHETIC_METADATA_SECRET}"],
        "mb connect",
        "connect.metadata_secret_value",
        _SYNTHETIC_METADATA_SECRET,
        id="metadata_secret_value",
    ),
    pytest.param(
        ["connect", "stripe", "--token", _SYNTHETIC_BAD_KEY],
        "mb connect",
        "connect.key_shape",
        _SYNTHETIC_BAD_KEY,
        id="key_shape",
    ),
    pytest.param(
        ["connect", "exec", "cloudflare"],
        "mb connect exec",
        "connect.exec_no_command",
        None,
        id="exec_no_command",
    ),
]


@pytest.mark.parametrize(("argv", "command", "rule", "value"), CONNECT_REFUSALS)
def test_connect_refusal_through_cli_logs_one_rule_line(
    connect_env: Path,
    state_home: Path,
    tmp_path: Path,
    argv: list[str],
    command: str,
    rule: str,
    value: str | None,
) -> None:
    result = runner.invoke(app, [*argv, "--repo", str(connect_env)])

    assert result.exit_code == _refusal_exit(rule), result.output
    [entry] = _lines(state_home)
    assert set(entry) == _REFUSAL_FIELDS
    assert entry["kind"] == "refusal"
    assert entry["command"] == command
    assert entry["rule"] == rule
    raw = _log(state_home).read_text(encoding="utf-8")
    assert str(tmp_path) not in raw
    assert result.stderr.strip().split(": ", 1)[1] not in raw
    if value is not None:
        assert value not in raw
        assert value not in result.output


def test_config_boundary_refusal_logs_exactly_one_line(
    connect_env: Path, state_home: Path, tmp_path: Path
) -> None:
    _symlinked_state(connect_env, tmp_path)

    for argv in (["connect", "status"], ["connect", "list"]):
        result = runner.invoke(app, [*argv, "--repo", str(connect_env)])
        assert result.exit_code == 2, result.output

    entries = _lines(state_home)
    assert [(e["command"], e["rule"]) for e in entries] == [
        ("mb connect status", "connect.config_boundary"),
        ("mb connect list", "connect.config_boundary"),
    ]


def test_plain_connect_value_error_logs_nothing(connect_env: Path, state_home: Path) -> None:
    result = runner.invoke(app, ["connect", "no-such-provider", "--repo", str(connect_env)])

    assert result.exit_code == 2
    assert not _log(state_home).exists()


@pytest.mark.parametrize(("argv", "command", "rule", "value"), CONNECT_REFUSALS)
def test_connect_refusal_logging_opt_out(
    connect_env: Path,
    state_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
    command: str,
    rule: str,
    value: str | None,
) -> None:
    monkeypatch.setenv("MB_FEEDBACK_LOG", "0")

    result = runner.invoke(app, [*argv, "--repo", str(connect_env)])

    assert result.exit_code == _refusal_exit(rule)
    assert not _log(state_home).exists()


@pytest.mark.parametrize(("argv", "command", "rule", "value"), CONNECT_REFUSALS)
def test_unwritable_log_never_changes_the_refusal(
    connect_env: Path,
    state_home: Path,
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
    command: str,
    rule: str,
    value: str | None,
) -> None:
    monkeypatch.setenv("MB_FEEDBACK_LOG", "0")
    baseline = runner.invoke(app, [*argv, "--repo", str(connect_env)])
    monkeypatch.delenv("MB_FEEDBACK_LOG")
    locked = state_home / "mainbranch"
    locked.mkdir(parents=True, exist_ok=True)
    locked.chmod(0o500)
    try:
        result = runner.invoke(app, [*argv, "--repo", str(connect_env)])
    finally:
        locked.chmod(0o700)

    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert result.exit_code == baseline.exit_code == _refusal_exit(rule)
    assert result.stderr == baseline.stderr
    assert result.stdout == baseline.stdout
    assert not _log(state_home).exists()
