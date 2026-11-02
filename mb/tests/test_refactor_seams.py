"""Compatibility checks for the original module bindings."""

from typing import Any

import pytest

from mb import connect


@pytest.mark.parametrize(
    ("provider_id", "probe_name"),
    [
        ("github", "_probe_github"),
        ("stripe", "_probe_stripe"),
        ("ga4", "_probe_ga4"),
        ("meta", "_validate_meta_with_cli"),
    ],
)
def test_provider_dispatch_uses_connect_binding(
    monkeypatch: pytest.MonkeyPatch, provider_id: str, probe_name: str
) -> None:
    def fake_probe(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("old probe reached")

    def forbidden_http(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("HTTP reached instead")

    monkeypatch.setattr(connect, probe_name, fake_probe)
    monkeypatch.setattr(connect, "_http_get_json", forbidden_http)
    with pytest.raises(RuntimeError, match="^old probe reached$"):
        connect._validate_with_provider(
            connect.provider_map()[provider_id], "synthetic-placeholder"
        )


def test_metadata_grammar_uses_connect_binding(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(connect, "METADATA_SECRET_GRAMMARS", ())
    assert connect._word_secret_rule("sk_test_" + "0" * 8) == ""


def test_original_imports_remain_available() -> None:
    from mb import migrate, validate
    from mb.doctor import (
        LATEST_SCHEMA_VERSION,
        pending_migrations,
        read_schema_version,
        schema_write_blocker,
        validate_mod,
    )
    from mb.json_result import json_default as original_json_default
    from mb.status import json_default

    assert LATEST_SCHEMA_VERSION == migrate.LATEST_SCHEMA_VERSION
    assert pending_migrations is migrate.pending_migrations
    assert read_schema_version is migrate.read_schema_version
    assert schema_write_blocker is migrate.schema_write_blocker
    assert validate_mod is validate
    assert json_default is original_json_default
