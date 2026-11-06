"""Overlapping deal changes must not lose one another.

A deal change reads a whole record, changes one deal and writes the record back.
Two overlapping changes used to lose one, so a revocation could vanish and check
would clear a withdrawn use. These tests run real processes and force the overlap
by events, not by sleeping.
"""

from __future__ import annotations

import multiprocessing
import os
import signal
import time
from collections.abc import Iterator
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pytest
import yaml

from mb import library_files as files
from mb import library_store as store
from tests.library_fixtures import lock, make_tree, needs_nonroot, sha, unlock

NOW = datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)
FORK = multiprocessing.get_context("fork")
PATIENCE = 30  # seconds a child waits for the other side before giving up


def library(biz: Path, *, init: bool = False) -> store.Library:
    return store.Library(biz, now=lambda: NOW, init=init)


def propose(lib: store.Library, asset: str) -> str:
    return lib.propose_deal(
        asset,
        uses=("paid-ad",),
        platforms=("meta",),
        from_date=date(2026, 12, 1),
        to_date=date(2026, 12, 31),
        perpetual=False,
        music="original",
        said_by="Rowan Vale, email 2026-10-02",
        subject="none-shown",
    ).id


def deal_states(biz: Path, asset: str) -> dict[str, str]:
    data = yaml.safe_load((biz / "library" / "records" / f"{asset}.yaml").read_text())
    return {d["id"]: d["state"] for d in data["deals"]}


@pytest.fixture()
def shelf(tmp_path: Path) -> Iterator[tuple[Path, str, list[str]]]:
    """A business folder with one asset and two proposed deals on it."""
    biz = tmp_path / "acme-candles"
    (biz / ".mb").mkdir(parents=True)
    data = b"clip bytes"
    src = lock(make_tree(tmp_path / "studio", {"clip.jpg": data}))
    lib = library(biz, init=True)
    lib.add_source("studio", src)
    lib.scan()
    asset = sha(data)
    yield biz, asset, [propose(lib, asset), propose(lib, asset)]
    unlock(src)


def _revoke(biz: Path, deal: str, role: str, events: dict[str, Any], out: Any) -> None:
    """Child process. `first` stops after it has read; `second` starts once that happened."""
    if role == "first":
        real = store.Library._locate

        def locate_then_wait(self: store.Library, deal_id: str) -> Any:
            found = real(self, deal_id)
            events["read"].set()
            stop = time.monotonic() + PATIENCE
            while not (events["done"].is_set() or events["blocked"].is_set()):
                if time.monotonic() > stop:
                    break
                events["done"].wait(0.01)
            return found

        store.Library._locate = locate_then_wait  # type: ignore[method-assign]
    else:
        events["read"].wait(PATIENCE)

        def pause(seconds: float) -> None:
            events["blocked"].set()
            time.sleep(seconds)

        files._pause = pause  # type: ignore[attr-defined]
    try:
        library(biz).revoke_deal(deal, "withdrawn")
        out.put((role, "ok"))
    except files.LibraryError as exc:
        out.put((role, str(exc)))
    finally:
        if role == "second":
            events["done"].set()


@needs_nonroot
def test_two_processes_revoking_different_deals_both_stay_revoked(
    shelf: tuple[Path, str, list[str]],
) -> None:
    biz, asset, (one, two) = shelf
    events = {name: FORK.Event() for name in ("read", "blocked", "done")}
    out = FORK.Queue()
    first = FORK.Process(target=_revoke, args=(biz, one, "first", events, out))
    second = FORK.Process(target=_revoke, args=(biz, two, "second", events, out))
    first.start()
    second.start()
    first.join(PATIENCE * 2)
    second.join(PATIENCE * 2)
    results = dict(out.get(timeout=5) for _ in range(2))
    assert results == {"first": "ok", "second": "ok"}
    assert deal_states(biz, asset) == {one: "revoked", two: "revoked"}


@needs_nonroot
def test_a_busy_deal_lock_is_refused_as_deals_and_writes_nothing(
    shelf: tuple[Path, str, list[str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    biz, asset, (one, two) = shelf
    monkeypatch.setattr(store, "DEAL_LOCK_WAIT", 0.1)
    before = (biz / "library" / "records" / f"{asset}.yaml").read_bytes()
    with library(biz)._deals_locked():
        for attempt in (
            lambda: library(biz).revoke_deal(one, "withdrawn"),
            lambda: library(biz).approve_deal(one, one, has_terminal=True, approver="Rowan"),
            lambda: propose(library(biz), asset),
        ):
            with pytest.raises(files.LibraryError, match="deal") as caught:
                attempt()
            assert "scan" not in str(caught.value)
    assert (biz / "library" / "records" / f"{asset}.yaml").read_bytes() == before


@needs_nonroot
def test_a_lock_held_by_a_killed_process_is_free_again(
    shelf: tuple[Path, str, list[str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    biz, _, (one, _two) = shelf
    held = FORK.Event()

    def hold() -> None:
        with library(biz)._deals_locked():
            held.set()
            time.sleep(PATIENCE * 4)

    child = FORK.Process(target=hold)
    child.start()
    assert held.wait(PATIENCE)
    monkeypatch.setattr(store, "DEAL_LOCK_WAIT", 0.1)
    with pytest.raises(files.LibraryError, match="deal"):
        library(biz).revoke_deal(one, "withdrawn")
    assert child.pid is not None
    os.kill(child.pid, signal.SIGKILL)
    child.join(PATIENCE)
    assert library(biz).revoke_deal(one, "withdrawn").state == "revoked"


@needs_nonroot
def test_deal_changes_do_not_wait_on_a_running_scan(shelf: tuple[Path, str, list[str]]) -> None:
    biz, asset, (one, _two) = shelf
    lib = library(biz)
    fd = files.open_dir(biz, store.CONFIG_REL, create=False)
    try:
        with files.exclusive(fd, store.LOCK_NAME):
            assert lib.revoke_deal(one, "withdrawn").state == "revoked"
    finally:
        os.close(fd)
    assert deal_states(biz, asset)[one] == "revoked"


def test_a_record_cannot_be_written_without_the_deal_lock(
    shelf: tuple[Path, str, list[str]],
) -> None:
    biz, asset, _ = shelf
    lib = library(biz)
    record = lib._record_or_default(asset)
    with lib._records_fd(create=False) as fd, pytest.raises(RuntimeError, match="deal lock"):
        lib._write_record(fd, record)
