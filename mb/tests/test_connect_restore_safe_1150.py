"""A user-scope connect rollback never removes a credential it cannot prove it created (#1150).

Temporary stores, no network, no real keychain.
"""

# ruff: noqa: F811
from __future__ import annotations

import errno
from pathlib import Path
from typing import Any

import pytest

from mb import connect as connect_mod
from mb.credential_store import SecretProbe, SecretStore, _read_local_secrets
from tests.test_connect_followups_1076 import _store_snapshot
from tests.test_google_connect import (  # noqa: F401 (fixtures are used by name)
    google_env,
    loopback_only_network,
    repo,
)

OLD = "sk_live_" + "O" * 28
NEW = "sk_live_" + "N" * 28
OTHER = "sk_live_" + "W" * 28


def _fail_record(monkeypatch: pytest.MonkeyPatch, before: Any = None) -> None:
    def write(*args: Any, **kwargs: Any) -> Path:
        if before is not None:
            before()
        raise OSError(errno.ENOSPC, "synthetic")

    monkeypatch.setattr(connect_mod, "_write_user_scope_provider", write)


def _items() -> dict[str, str]:
    return dict(_read_local_secrets())


def _connect(repo: Path, token: str = NEW) -> Any:
    return connect_mod.connect_provider("stripe", repo=repo, token=token, scope="user")


@pytest.mark.parametrize("kind", ["not_checked", "refused"])
def test_an_inconclusive_snapshot_refuses_before_anything_is_written(
    repo: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    connect_mod.connect_provider("stripe", repo=repo, token=OLD, scope="user")
    before = _store_snapshot()
    items = _items()
    if kind == "not_checked":
        probe = SecretProbe("", False, True, "", not_checked=True)
    else:
        probe = SecretProbe("", False, False, "keychain_prompt_pending")
    monkeypatch.setattr(SecretStore, "probe", lambda self, ref, **kw: probe)
    writes: list[str] = []
    monkeypatch.setattr(SecretStore, "set", lambda self, ref, value, **kw: writes.append(ref))

    with pytest.raises(connect_mod.KeychainError) as excinfo:
        _connect(repo)

    message = str(excinfo.value)
    assert "Nothing was stored" in message
    assert NEW not in message and OLD not in message
    assert writes == []
    assert bool(_items() == items)
    assert bool(_store_snapshot() == before)


def test_a_definitely_absent_snapshot_is_deleted_when_the_record_fails(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _fail_record(monkeypatch)

    with pytest.raises(connect_mod.MetadataWriteError) as excinfo:
        _connect(repo)

    assert "The new credential was removed" in str(excinfo.value)
    assert NEW not in str(excinfo.value)
    assert _items() == {}


def test_another_writers_item_is_kept_and_listed_as_stayed_changed(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def other_writer() -> None:
        (ref,) = _items()
        SecretStore("local-file").set(ref, OTHER)

    _fail_record(monkeypatch, other_writer)

    with pytest.raises(connect_mod.MetadataWriteError) as excinfo:
        _connect(repo)

    message = str(excinfo.value)
    assert "stayed changed" in message
    assert "the Stripe credential" in message
    assert NEW not in message and OTHER not in message
    assert list(_items().values()) == [OTHER]


def test_an_item_deleted_by_another_writer_leaves_nothing_to_restore(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def other_writer() -> None:
        (ref,) = _items()
        SecretStore("local-file").delete(ref)

    _fail_record(monkeypatch, other_writer)

    with pytest.raises(connect_mod.MetadataWriteError) as excinfo:
        _connect(repo)

    assert "stayed changed" not in str(excinfo.value)
    assert _items() == {}


def test_a_present_snapshot_is_restored_as_before(
    repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    connect_mod.connect_provider("stripe", repo=repo, token=OLD, scope="user")
    items = _items()
    _fail_record(monkeypatch)

    with pytest.raises(connect_mod.MetadataWriteError) as excinfo:
        _connect(repo)

    assert "The previous credential was restored" in str(excinfo.value)
    assert bool(_items() == items)
