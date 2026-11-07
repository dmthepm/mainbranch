"""A directory-sync failure after the credential file was replaced is reported as it happened."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from mb import connect as c
from mb.credential_store import CredentialStoreError, SecretStore

OLD = "fake-key-old-0000000000000000"
NEW = "fake-key-new-1111111111111111"


@pytest.fixture()
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "local-file")
    target = tmp_path / "acme-candles"
    target.mkdir()
    return target


def _fail_secret_directory_sync(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    secrets_dir = tmp_path / "home" / "secrets"
    real_fsync = os.fsync

    def fsync(fd: int) -> None:
        info = os.fstat(fd)
        if stat.S_ISDIR(info.st_mode) and info.st_ino == secrets_dir.stat().st_ino:
            raise OSError(5, "directory fsync failed")
        real_fsync(fd)

    monkeypatch.setattr(os, "fsync", fsync)


def _stored_values(tmp_path: Path) -> str:
    return (tmp_path / "home" / "secrets" / "connect.json").read_text(encoding="utf-8")


def test_existing_credential_failure_does_not_claim_nothing_was_stored(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c.connect_provider("cloudflare", repo=repo, token=OLD)
    config = (repo / ".mb" / "connect.yaml").read_bytes()
    _fail_secret_directory_sync(monkeypatch, tmp_path)

    with pytest.raises(CredentialStoreError) as exc_info:
        c.connect_provider("cloudflare", repo=repo, token=NEW)

    assert NEW in _stored_values(tmp_path)  # the file really was replaced
    assert exc_info.value.reason == "local_file_unconfirmed"
    message = str(exc_info.value)
    assert "Nothing was stored" not in message
    assert "was written" in message and "rerun" in message.lower()
    assert (repo / ".mb" / "connect.yaml").read_bytes() == config
    assert NEW not in message and OLD not in message


def test_new_credential_failure_does_not_claim_nothing_was_stored(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "home" / "secrets").mkdir(parents=True)
    _fail_secret_directory_sync(monkeypatch, tmp_path)

    with pytest.raises(CredentialStoreError) as exc_info:
        c.connect_provider("cloudflare", repo=repo, token=NEW)

    assert NEW in _stored_values(tmp_path)
    assert exc_info.value.reason == "local_file_unconfirmed"
    assert "Nothing was stored" not in str(exc_info.value)
    config = repo / ".mb" / "connect.yaml"
    assert not config.exists() or "cloudflare" not in config.read_text(encoding="utf-8")


def test_store_set_reports_the_unconfirmed_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "home"))
    (tmp_path / "home" / "secrets").mkdir(parents=True)
    _fail_secret_directory_sync(monkeypatch, tmp_path)

    with pytest.raises(CredentialStoreError) as exc_info:
        SecretStore("local-file").set("fake-ref", NEW)

    assert exc_info.value.reason == "local_file_unconfirmed"
