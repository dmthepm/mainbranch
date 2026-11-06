"""A record, a deal or the config with a field the library does not know is refused by name.

Every writer reads before it writes and writes back only the fields it knows, so a
field added by hand would be deleted without a word. The read refuses instead, and
the file stays byte for byte as it was. Everything here is invented.
"""

from __future__ import annotations

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
CLIP = b"clip bytes"
ASSET = sha(CLIP)
FIELD = "source_shoot"
runner = CliRunner()


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


class Shop:
    """A business folder with one scanned clip and one proposed deal."""

    def __init__(self, biz: Path, source: Path) -> None:
        self.biz = biz
        self.lib = store.Library(biz, now=lambda: NOW, init=True)
        self.lib.add_source("studio", source)
        self.lib.scan()
        deal = self.lib.propose_deal(
            ASSET,
            uses=("website",),
            platforms=(),
            from_date=date(2026, 12, 1),
            to_date=date(2026, 12, 31),
            perpetual=False,
            music="none",
            said_by="Rowan Vale, email 2026-10-02",
            subject="none-shown",
        )
        self.deal_id = deal.id
        self.record = biz / "library" / "records" / f"{ASSET}.yaml"
        self.config = biz / ".mb/private/library/config.yaml"

    def edit(self, path: Path, change: Callable[[dict[str, Any]], None]) -> bytes:
        data = yaml.safe_load(path.read_text())
        change(data)
        path.write_text(yaml.safe_dump(data, sort_keys=False))
        path.chmod(0o600)
        return path.read_bytes()

    def stray_in_record(self) -> bytes:
        return self.edit(self.record, lambda d: d.__setitem__(FIELD, "2026-10-14-founder-shoot"))

    def stray_in_deal(self) -> bytes:
        return self.edit(self.record, lambda d: d["deals"][0].__setitem__(FIELD, "x"))

    def stray_in_config(self) -> bytes:
        return self.edit(self.config, lambda d: d.__setitem__(FIELD, "x"))


@pytest.fixture()
def shop(biz: Path, tree: Callable[[dict[str, bytes]], Path]) -> Shop:
    return Shop(biz, tree({"clip.jpg": CLIP}))


def lib_run(*args: str) -> Any:
    return runner.invoke(app, ["library", *args])


PROPOSE = [
    "deal", "propose", ASSET, "--use", "website", "--from", "2026-12-01", "--to", "2026-12-31",
    "--music", "none", "--said-by", "Rowan Vale, email 2026-10-03", "--subject", "none-shown",
]  # fmt: skip

READERS = {
    "find": ["find", "clip"],
    "find-for": ["find", "--for", "website"],
    "show": ["show", ASSET],
    "check": ["check", ASSET, "--use", "website"],
    "propose": PROPOSE,
}


@needs_nonroot
@pytest.mark.parametrize("where", ["stray_in_record", "stray_in_deal"])
@pytest.mark.parametrize("verb", sorted(READERS))
def test_every_cli_verb_that_reads_a_record_refuses_a_stray_field(
    shop: Shop, where: str, verb: str
) -> None:
    before = getattr(shop, where)()
    out = lib_run(*READERS[verb])
    assert out.exit_code == 2, out.output
    assert FIELD in out.output
    assert "tags" in out.output
    assert shop.record.read_bytes() == before


@needs_nonroot
@pytest.mark.parametrize("where", ["stray_in_record", "stray_in_deal"])
def test_revoke_refuses_a_stray_field_and_leaves_the_file_alone(shop: Shop, where: str) -> None:
    before = getattr(shop, where)()
    out = lib_run("deal", "revoke", shop.deal_id, "--reason", "creator withdrew")
    assert out.exit_code == 2, out.output
    assert FIELD in out.output
    assert shop.record.read_bytes() == before


@needs_nonroot
@pytest.mark.parametrize("where", ["stray_in_record", "stray_in_deal"])
def test_approve_refuses_a_stray_field_and_leaves_the_file_alone(shop: Shop, where: str) -> None:
    before = getattr(shop, where)()
    with pytest.raises(files.LibraryError, match=FIELD):
        shop.lib.approve_deal(shop.deal_id, shop.deal_id, has_terminal=True, approver="rowan")
    assert shop.record.read_bytes() == before


@needs_nonroot
def test_source_add_refuses_a_stray_config_key_and_leaves_the_file_alone(
    shop: Shop, tree: Callable[[dict[str, bytes]], Path]
) -> None:
    before = shop.stray_in_config()
    out = lib_run("source", "add", "second", str(tree({"other.jpg": b"other bytes"})))
    assert out.exit_code == 2, out.output
    assert FIELD in out.output
    assert shop.config.read_bytes() == before


@needs_nonroot
def test_a_config_with_a_stray_key_stops_queries_too(shop: Shop) -> None:
    shop.stray_in_config()
    out = lib_run("find", "clip")
    assert out.exit_code == 2, out.output
    assert FIELD in out.output


@needs_nonroot
def test_the_message_names_the_record_and_the_way_out(shop: Shop) -> None:
    shop.stray_in_record()
    out = lib_run("show", ASSET)
    assert f"record {ASSET[:12]}" in out.output
    assert "put business-only facts in tags" in out.output


@needs_nonroot
def test_the_known_fields_still_read_and_write(shop: Shop) -> None:
    out = lib_run("show", ASSET)
    assert out.exit_code == 0, out.output
    assert lib_run("deal", "revoke", shop.deal_id, "--reason", "creator withdrew").exit_code == 0


def test_the_known_deal_fields_are_exactly_the_ones_a_deal_writes() -> None:
    deal = rights.Deal(
        id="d7aa11bb",
        uses=("website",),
        platforms=(),
        from_date=date(2026, 12, 1),
        to_date=None,
        perpetual=True,
        music="none",
        platform_code=None,
        said_by="Rowan Vale",
        evidence_hash="",
        sightings=("studio:clip.jpg",),
        subject="agreed",
        subject_proof="signed release, Releases folder",
    )
    assert set(deal.to_mapping()) == rights.DEAL_KEYS


@needs_nonroot
def test_an_alias_still_wins_over_the_stray_field_check(shop: Shop) -> None:
    shop.record.write_text(f"asset: {ASSET}\ntags: &t [a]\nextra: *t\n")
    shop.record.chmod(0o600)
    out = lib_run("show", ASSET)
    assert out.exit_code == 2, out.output
    assert "alias" in out.output or "merge" in out.output
