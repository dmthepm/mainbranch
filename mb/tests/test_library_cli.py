"""`mb library` as typed at a terminal, from inside one business folder."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, cast

import pytest
import yaml
from typer.main import get_command
from typer.testing import CliRunner

from mb import cli_library
from mb.cli import app
from tests.library_fixtures import blob, needs_nonroot, sha

runner = CliRunner()
POUR = blob("pour")
POUR_ID = sha(POUR)
SIGHTING = "studio:candle-pour-01.jpg"


@pytest.fixture()
def shop(tmp_path, monkeypatch, read_only_source):
    """Inside Acme Candles' business folder, with one read-only source."""
    biz = tmp_path / "acme-candles"
    (biz / ".mb").mkdir(parents=True)
    src = read_only_source({"candle-pour-01.jpg": POUR, "reels/wick-trim.mp4": blob("wick")})
    monkeypatch.chdir(biz)
    return biz, src


def run(*args: str, input: str | None = None) -> Any:
    return runner.invoke(app, ["library", *args], input=input)


def commands(group: Any, prefix: tuple[str, ...] = ()) -> Iterator[tuple[tuple[str, ...], Any]]:
    for name, cmd in sorted(group.commands.items()):
        if hasattr(cmd, "commands"):
            yield from commands(cmd, (*prefix, name))
        else:
            yield (*prefix, name), cmd


def test_the_eight_verbs_and_nothing_else():
    library = cast(Any, get_command(app)).commands["library"]
    assert sorted(" ".join(path) for path, _ in commands(library)) == [
        "check",
        "deal approve",
        "deal propose",
        "deal revoke",
        "find",
        "scan",
        "show",
        "source add",
    ]


def test_no_verb_takes_a_business_folder_or_repo_option():
    library = cast(Any, get_command(app)).commands["library"]
    for path, cmd in commands(library):
        flags = {opt for p in cmd.params for opt in getattr(p, "opts", [])}
        assert not flags & {"--repo", "--root", "--dir", "--path", "--folder", "--records"}, path
    # The one folder a verb accepts is the media source being registered.
    folders = [
        (" ".join(path), p.name)
        for path, cmd in commands(library)
        for p in cmd.params
        if p.param_type_name == "argument" and p.name in {"folder", "path", "repo"}
    ]
    assert folders == [("source add", "folder")]


def test_the_help_states_the_limits_honestly():
    result = run("--help")
    assert result.exit_code == 0
    text = " ".join(result.output.split())
    assert "same OS user" in text
    assert "does not enforce" in text
    assert "tamper" not in text.lower()


@needs_nonroot
def test_a_whole_session_from_source_to_cleared(shop):
    biz, src = shop
    out = run("source", "add", "studio", str(src))
    assert out.exit_code == 0, out.output
    assert "studio" in out.output

    out = run("scan")
    assert out.exit_code == 0, out.output
    assert "indexed 2" in out.output

    out = run("find", "candle pour")
    assert POUR_ID in out.output and SIGHTING in out.output
    assert "wick" not in out.output

    out = run("show", POUR_ID)
    assert "provenance: unknown" in out.output and SIGHTING in out.output

    window = [
        "--use",
        "paid-ad",
        "--platform",
        "meta",
        "--from",
        "2026-12-10",
        "--to",
        "2026-12-20",
    ]
    out = run("check", POUR_ID, *window)
    assert out.exit_code == 1
    assert f"{SIGHTING}  NOT CLEARED (provenance-not-clearable)" in out.output

    out = run(
        "deal", "propose", POUR_ID, "--use", "paid-ad", "--platform", "meta",
        "--from", "2026-12-01", "--to", "2026-12-31", "--music", "original",
        "--said-by", "Rowan Vale, email 2026-10-02",
    )  # fmt: skip
    assert out.exit_code == 0, out.output
    deal_id = out.output.split("deal ")[1].split()[0]
    assert len(deal_id) == 8

    record = biz / "library/records" / f"{POUR_ID}.yaml"
    data = yaml.safe_load(record.read_text())
    data["provenance"] = "own"
    record.write_text(yaml.safe_dump(data, sort_keys=False))

    out = run("check", POUR_ID, *window)
    assert f"{SIGHTING}  NOT CLEARED (not-approved)" in out.output

    # No terminal under the test runner: approving is refused even with the id typed.
    out = run("deal", "approve", deal_id, input=f"{deal_id}\n")
    assert out.exit_code == 2
    assert "terminal" in out.output

    out = run("check", POUR_ID, *window)
    assert out.exit_code == 1

    monkey = pytest.MonkeyPatch()
    monkey.setattr(cli_library, "_has_terminal", lambda: True)
    try:
        out = run("deal", "approve", deal_id, input="wrong\n")
        assert out.exit_code == 2 and "type the deal id" in out.output
        out = run("deal", "approve", deal_id, input=f"{deal_id}\n")
        assert out.exit_code == 0, out.output
    finally:
        monkey.undo()

    out = run("check", POUR_ID, *window)
    assert out.exit_code == 0
    assert f"{SIGHTING}  CLEARED (deal {deal_id}, approved " in out.output

    out = run("find", "--for", "paid-ad", "--platform", "meta", "--from", "2026-12-10",
              "--to", "2026-12-20")  # fmt: skip
    assert POUR_ID in out.output and f"usable at: {SIGHTING}" in out.output
    assert "wick" not in out.output
    assert "1 more match but are not cleared." in out.output

    out = run("find", "candle")  # no --for: nothing to be cleared for, so no count
    assert "not cleared" not in out.output

    out = run("deal", "revoke", deal_id, "--reason", "creator withdrew")
    assert out.exit_code == 0
    out = run("check", POUR_ID, *window)
    assert f"{SIGHTING}  NOT CLEARED (revoked)" in out.output


@needs_nonroot
def test_scan_prints_skipped_files_with_reasons(shop, tmp_path):
    biz, src = shop
    # a second source with a file that must be listed, not hidden
    from tests.library_fixtures import lock, make_tree, unlock

    other = make_tree(tmp_path / "sources" / "site-repo", {"img/pour.jpg": POUR})
    (other / "img" / "loose.jpg").write_bytes(blob("loose"))
    lock(other)
    (other / "img" / "loose.jpg").chmod(0o644)
    try:
        run("source", "add", "studio", str(src))
        run("source", "add", "site-repo", str(other))
        out = run("scan")
        assert "Skipped (1)" in out.output
        assert "site-repo:img/loose.jpg  writable" in out.output
        assert "Duplicates (1)" in out.output
        assert POUR_ID[:12] in out.output
    finally:
        unlock(other)


def test_a_writable_source_is_refused_with_a_clear_message(shop, tmp_path):
    import os

    if os.geteuid() == 0:
        pytest.skip("running as root: every folder looks writable; the refusal path is unproven")
    from tests.library_fixtures import make_tree

    open_folder = make_tree(tmp_path / "open", {"a.jpg": blob("a")})
    out = run("source", "add", "open", str(open_folder))
    assert out.exit_code == 2
    assert "writable by this user" in out.output


def test_outside_a_business_folder_it_refuses(tmp_path, monkeypatch):
    bare = tmp_path / "bare"
    bare.mkdir()
    monkeypatch.chdir(bare)
    out = run("scan")
    assert out.exit_code == 2
    assert "not a business folder" in out.output
    assert list(bare.iterdir()) == []


def test_a_half_given_window_is_refused(shop):
    out = run("find", "--for", "paid-ad", "--platform", "meta", "--from", "2026-12-10")
    assert out.exit_code == 2
    assert "--from and --to" in out.output


@needs_nonroot
def test_a_bad_date_and_a_bad_asset_id_are_named(shop):
    biz, src = shop
    run("source", "add", "studio", str(src))
    assert "YYYY-MM-DD" in run("find", "--from", "tomorrow", "--to", "2026-12-20").output
    out = run("show", "a1f3")
    assert out.exit_code == 2 and "full 64-character" in out.output
