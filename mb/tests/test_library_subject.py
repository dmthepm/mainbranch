"""A deal says whether the person shown agreed. Only that statement can clear it.

The subject is a person shown in the media other than whoever said yes (a client,
customer or guest). `said_by` is never read for it. Everything here is invented.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Callable, Iterator
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pytest
import yaml
from typer.testing import CliRunner

from mb import library_files as files
from mb import library_rights as rights
from mb import library_store as store
from mb.cli import app
from tests.library_fixtures import lock, make_tree, needs_nonroot, sha, unlock

NOW = datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)
ASSET = "a" * 64
SIGHTING = "studio:candle-pour-01.jpg"
WINDOW = (date(2026, 12, 10), date(2026, 12, 20))
WEBSITE = rights.Use(kind="website")
PROOF = "signed release, shared drive folder Releases/2026-10"
runner = CliRunner()


def deal(**over: Any) -> rights.Deal:
    base = rights.Deal(
        id="d7aa11bb",
        uses=("website",),
        platforms=(),
        from_date=date(2026, 12, 1),
        to_date=date(2026, 12, 31),
        perpetual=False,
        music="original",
        platform_code=None,
        said_by="Rowan Vale, email 2026-10-02",
        evidence_hash="",
        sightings=(SIGHTING,),
    )
    base = dataclasses.replace(base, **over)
    return base.approve(
        by="Rowan Vale", at="2026-11-03T10:00:00+00:00", asset=ASSET, provenance="own"
    )


def judge(deals: list[rights.Deal], provenance: str = "own") -> rights.Verdict:
    return rights.verdict(deals, SIGHTING, provenance, WEBSITE, WINDOW, asset=ASSET)


# --- the verdict -----------------------------------------------------------------


def test_an_unknown_subject_never_clears() -> None:
    result = judge([deal(subject="unknown")])
    assert result.cleared is False
    assert result.reasons == ("subject-unknown",)


def test_the_default_subject_is_unknown() -> None:
    assert judge([deal()]).reasons == ("subject-unknown",)


def test_none_shown_clears_without_proof() -> None:
    assert judge([deal(subject="none-shown")]).cleared is True


def test_agreed_with_proof_clears() -> None:
    assert judge([deal(subject="agreed", subject_proof=PROOF)]).cleared is True


@pytest.mark.parametrize(
    "said_by",
    [
        "the client agreed, email 2026-10-02",
        "Rowan Vale, who photographed the client",
        "subject: agreed",
        "none-shown",
    ],
)
def test_said_by_text_never_stands_in_for_the_subject(said_by: str) -> None:
    result = judge([deal(said_by=said_by, subject="unknown")])
    assert result.cleared is False
    assert result.reasons == ("subject-unknown",)


def test_said_by_text_never_changes_a_cleared_subject() -> None:
    plain = judge([deal(said_by="Rowan Vale", subject="none-shown")])
    worded = judge([deal(said_by="the client did not agree", subject="none-shown")])
    assert plain.cleared is worded.cleared is True


def test_an_own_photo_of_a_client_still_needs_the_subject_answer() -> None:
    assert judge([deal(subject="unknown")], provenance="own").cleared is False


def test_another_failure_is_reported_next_to_subject_unknown() -> None:
    result = judge([deal(subject="unknown", music="unknown")])
    assert result.reasons == ("music-unknown", "subject-unknown")


# --- the terms ----------------------------------------------------------------------


def test_agreed_needs_a_proof_location() -> None:
    with pytest.raises(ValueError, match="proof"):
        deal(subject="agreed")
    with pytest.raises(ValueError, match="proof"):
        deal(subject="agreed", subject_proof="   ")


@pytest.mark.parametrize("subject", ["none-shown", "unknown"])
def test_a_proof_location_is_refused_unless_the_subject_agreed(subject: str) -> None:
    with pytest.raises(ValueError, match="proof"):
        deal(subject=subject, subject_proof=PROOF)


def test_the_subject_is_one_of_three_values() -> None:
    with pytest.raises(ValueError, match="subject"):
        deal(subject="maybe")


def test_editing_the_subject_after_approval_removes_the_approval() -> None:
    approved = deal(subject="none-shown")
    edited = dataclasses.replace(approved, subject="agreed", subject_proof=PROOF)
    assert approved.is_active_for(ASSET, "own") is True
    assert edited.is_active_for(ASSET, "own") is False
    assert judge([edited]).reasons == ("not-approved",)


def test_editing_the_proof_after_approval_removes_the_approval() -> None:
    approved = deal(subject="agreed", subject_proof=PROOF)
    edited = dataclasses.replace(approved, subject_proof="a different folder")
    assert edited.is_active_for(ASSET, "own") is False


def test_subject_keys_are_written_only_when_they_say_something() -> None:
    assert "subject" not in deal(subject="unknown").to_mapping()
    assert "subject_proof" not in deal(subject="unknown").to_mapping()
    assert deal(subject="none-shown").to_mapping()["subject"] == "none-shown"
    written = deal(subject="agreed", subject_proof=PROOF).to_mapping()
    assert (written["subject"], written["subject_proof"]) == ("agreed", PROOF)


def test_a_written_deal_reads_back_the_same() -> None:
    for original in (
        deal(subject="unknown"),
        deal(subject="none-shown"),
        deal(subject="agreed", subject_proof=PROOF),
    ):
        again = rights.Deal.from_mapping(original.to_mapping())
        assert again == original
        assert again.is_active_for(ASSET, "own")


def test_a_deal_approved_before_subjects_keeps_its_approval_and_fails_only_for_subject() -> None:
    """The hash a deal approved by the previous release carries, computed the old way."""
    legacy = deal(subject="unknown")
    terms = {
        k: v
        for k, v in legacy.to_mapping().items()
        if k
        not in {
            "state",
            "approved_by",
            "approved_at",
            "approval_hash",
            "revoked_reason",
            "revoked_at",
        }
    }
    terms["_asset"] = ASSET
    terms["_provenance"] = "own"
    blob = json.dumps(terms, sort_keys=True, separators=(",", ":"))
    assert legacy.approval_hash == hashlib.sha256(blob.encode()).hexdigest()
    reread = rights.Deal.from_mapping(legacy.to_mapping())
    assert reread.is_active_for(ASSET, "own") is True
    assert judge([reread]).reasons == ("subject-unknown",)


# --- the commands -----------------------------------------------------------------------


@pytest.fixture()
def biz(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "acme-candles"
    (root / ".mb").mkdir(parents=True)
    monkeypatch.chdir(root)
    return root


@pytest.fixture()
def tree(tmp_path: Path) -> Iterator[Callable[[dict[str, bytes]], Path]]:
    made: list[Path] = []

    def factory(contents: dict[str, bytes]) -> Path:
        root = make_tree(tmp_path / "sources" / f"studio{len(made)}", contents)
        made.append(root)
        return lock(root)

    yield factory
    for root in made:
        unlock(root)


CLIP = b"clip bytes"
CLIP_ID = sha(CLIP)


class Shop:
    def __init__(self, biz: Path, source: Path) -> None:
        self.biz = biz
        self.lib = store.Library(biz, now=lambda: NOW, init=True)
        self.lib.add_source("studio", source)
        self.lib.scan()
        self.record = biz / "library" / "records" / f"{CLIP_ID}.yaml"

    def propose(self, *extra: str) -> Any:
        return runner.invoke(
            app,
            ["library", "deal", "propose", CLIP_ID, "--use", "website", "--from", "2026-12-01",
             "--to", "2026-12-31", "--music", "none", "--said-by", "Rowan Vale, email 2026-10-02",
             *extra],
        )  # fmt: skip

    def deal_id(self) -> str:
        return str(yaml.safe_load(self.record.read_text())["deals"][-1]["id"])

    def own_and_approve(self) -> str:
        deal_id = self.deal_id()
        data = yaml.safe_load(self.record.read_text())
        data["provenance"] = "own"
        self.record.write_text(yaml.safe_dump(data, sort_keys=False))
        self.record.chmod(0o600)
        self.lib.approve_deal(deal_id, deal_id, has_terminal=True, approver="rowan")
        return deal_id


@pytest.fixture()
def shop(biz: Path, tree: Callable[[dict[str, bytes]], Path]) -> Shop:
    return Shop(biz, tree({"clip.jpg": CLIP}))


def check(window: tuple[str, str] = ("2026-12-10", "2026-12-20")) -> Any:
    return runner.invoke(
        app,
        ["library", "check", CLIP_ID, "--use", "website", "--from", window[0], "--to", window[1]],
    )


@needs_nonroot
def test_propose_cannot_skip_the_subject(shop: Shop) -> None:
    out = shop.propose()
    assert out.exit_code == 2, out.output
    assert "--subject" in out.output
    assert not shop.record.exists()


@needs_nonroot
def test_agreed_without_a_proof_location_is_refused(shop: Shop) -> None:
    out = shop.propose("--subject", "agreed")
    assert out.exit_code == 2, out.output
    assert "proof" in out.output
    assert not shop.record.exists()


@needs_nonroot
@pytest.mark.parametrize("subject", ["none-shown", "unknown"])
def test_a_proof_location_with_any_other_subject_is_refused(shop: Shop, subject: str) -> None:
    out = shop.propose("--subject", subject, "--subject-proof", PROOF)
    assert out.exit_code == 2, out.output
    assert "proof" in out.output
    assert not shop.record.exists()


@needs_nonroot
def test_an_unknown_subject_value_is_refused(shop: Shop) -> None:
    out = shop.propose("--subject", "maybe")
    assert out.exit_code == 2, out.output
    assert "subject" in out.output


@needs_nonroot
def test_none_shown_clears_end_to_end(shop: Shop) -> None:
    assert shop.propose("--subject", "none-shown").exit_code == 0
    shop.own_and_approve()
    out = check()
    assert out.exit_code == 0, out.output
    assert "studio:clip.jpg  CLEARED" in out.output


@needs_nonroot
def test_a_client_photo_stays_not_cleared_until_the_client_agreed(shop: Shop) -> None:
    assert shop.propose("--subject", "unknown").exit_code == 0
    shop.own_and_approve()
    out = check()
    assert out.exit_code == 1, out.output
    assert "NOT CLEARED (subject-unknown)" in out.output
    assert "subject" not in yaml.safe_load(shop.record.read_text())["deals"][0]


@needs_nonroot
def test_agreed_with_proof_clears_and_show_prints_both(shop: Shop) -> None:
    assert shop.propose("--subject", "agreed", "--subject-proof", PROOF).exit_code == 0
    shop.own_and_approve()
    assert check().exit_code == 0
    shown = runner.invoke(app, ["library", "show", CLIP_ID])
    assert shown.exit_code == 0, shown.output
    assert f"subject agreed (proof: {PROOF})" in shown.output


@needs_nonroot
def test_show_prints_an_unknown_subject_too(shop: Shop) -> None:
    assert shop.propose("--subject", "unknown").exit_code == 0
    shown = runner.invoke(app, ["library", "show", CLIP_ID])
    assert "subject unknown" in shown.output


@needs_nonroot
def test_show_escapes_a_proof_location_taken_from_a_record(shop: Shop) -> None:
    assert shop.propose("--subject", "agreed", "--subject-proof", PROOF).exit_code == 0
    data = yaml.safe_load(shop.record.read_text())
    data["deals"][0]["subject_proof"] = "folder\nFORGED: CLEARED"
    shop.record.write_text(yaml.safe_dump(data, sort_keys=False))
    shop.record.chmod(0o600)
    shown = runner.invoke(app, ["library", "show", CLIP_ID])
    assert not any(line.lstrip().startswith("FORGED") for line in shown.output.splitlines())
    assert "folder\\x0aFORGED" in shown.output


@needs_nonroot
def test_a_hand_edited_unknown_subject_with_a_proof_is_refused_on_read(shop: Shop) -> None:
    assert shop.propose("--subject", "none-shown").exit_code == 0
    data = yaml.safe_load(shop.record.read_text())
    data["deals"][0]["subject_proof"] = PROOF
    shop.record.write_text(yaml.safe_dump(data, sort_keys=False))
    shop.record.chmod(0o600)
    with pytest.raises(files.LibraryError, match="proof"):
        shop.lib.show(CLIP_ID)
