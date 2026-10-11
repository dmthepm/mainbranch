"""``mb connect`` provider and credential foundation."""

from __future__ import annotations

import email.message
import hashlib
import io
import json
import os
import random
import shutil
import stat
import string
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest
import typer
import yaml
from typer.testing import CliRunner

from mb import codex as codex_mod
from mb import connect as connect_mod
from mb import credential_store as credential_store_mod
from mb import http_safe as http_safe_mod
from mb.cli import app

runner = CliRunner()


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _local_secret_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "local-file")
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "home"))
    for provider in connect_mod.PROVIDERS:
        for env_var in provider.env_vars:
            monkeypatch.delenv(env_var, raising=False)


def _connect_meta_ready_prereqs(monkeypatch) -> None:
    monkeypatch.setattr(connect_mod, "_meta_prerequisite_state", lambda **kwargs: "")


def _fake_meta_which(name: str) -> str | None:
    if name in {"meta", "python3.12"}:
        return f"/usr/bin/{name}"
    return None


def test_provider_registry_includes_initial_foundation() -> None:
    providers = {provider["id"]: provider for provider in connect_mod.provider_registry()}

    assert {
        "google",
        "meta",
        "cloudflare",
        "stripe",
        "resend",
        "postiz",
        "apify",
        "hledger",
        "transcription",
    }.issubset(providers)
    assert "beancount" not in providers
    assert providers["stripe"]["required_secrets"] == ["api_key"]
    assert "STRIPE_SECRET_KEY" in providers["stripe"]["env_vars"]
    assert "mode" in providers["stripe"]["metadata_fields"]
    assert providers["resend"]["required_secrets"] == ["api_key"]
    assert "RESEND_API_KEY" in providers["resend"]["env_vars"]
    assert "sender_domain" in providers["resend"]["metadata_fields"]
    assert providers["cloudflare"]["required_secrets"] == ["api_token"]
    assert providers["meta"]["auth"] == "meta_ads_cli_read_only"
    assert providers["meta"]["required_secrets"] == ["access_token"]
    assert "ACCESS_TOKEN" in providers["meta"]["env_vars"]
    assert providers["hledger"]["required_secrets"] == []
    assert providers["hledger"]["metadata_fields"] == [
        "journal_path",
        "vault_path",
    ]


def test_connect_list_json_does_not_create_repo_metadata(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(connect_mod, "_meta_prerequisite_state", lambda **kwargs: "missing_cli")
    repo = tmp_path / "biz"
    repo.mkdir()

    result = runner.invoke(app, ["connect", "list", "--repo", str(repo), "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert any(provider["id"] == "cloudflare" for provider in payload["providers"])
    meta = next(provider for provider in payload["providers"] if provider["id"] == "meta")
    assert meta["auth"] == "meta_ads_cli_read_only"
    cloudflare = next(
        provider for provider in payload["providers"] if provider["id"] == "cloudflare"
    )
    assert "low-lock-in rail" in cloudflare["why"]
    assert cloudflare["status_command"] == "mb connect doctor --json"
    assert not (repo / ".mb" / "connect.yaml").exists()


def test_connect_plan_returns_numbered_provider_choices(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "biz"
    repo.mkdir()
    github_context = {
        "ok": False,
        "state": "unauthenticated",
        "summary": "GitHub CLI is installed but not authenticated.",
        "repair": "Run `gh auth login`.",
        "repair_command": "gh auth login",
        "safe_to_share": True,
    }
    monkeypatch.setattr(connect_mod, "github_context", lambda repo: github_context)
    monkeypatch.setattr(connect_mod, "_meta_prerequisite_state", lambda **kwargs: "missing_cli")

    result = runner.invoke(app, ["connect", "plan", "--repo", str(repo), "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    steps = {step["id"]: step for step in payload["steps"]}
    assert list(steps) == ["github", "cloudflare", "google", "meta", "apify"]
    assert steps["github"]["next_command"] == "gh auth login"
    assert steps["github"]["safe_to_share"] is True
    assert steps["meta"]["state"] == "missing_cli"
    assert steps["meta"]["next_command"] == "pipx install --python <python3.12-or-newer> meta-ads"
    assert payload["summary"]["total"] == 5
    assert not (repo / ".mb" / "connect.yaml").exists()


def test_connect_meta_token_stdin_stores_secret_outside_repo(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    monkeypatch.setattr(connect_mod, "_meta_prerequisite_state", lambda **kwargs: "")
    repo = tmp_path / "biz"
    repo.mkdir()

    result = runner.invoke(
        app,
        [
            "connect",
            "meta",
            "--repo",
            str(repo),
            "--token-stdin",
            "--metadata",
            "ad_account_id=act_test",
            "--account",
            "Meta Test",
            "--json",
        ],
        input="meta-secret-token\n",
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["status"]["state"] == "unvalidated"
    assert payload["credential_source"]["type"] == "stdin"
    assert "Meta Business Portfolio" in payload["setup"]["requirements"][0]
    assert "Business portfolio ID" in payload["setup"]["requirements"][2]
    assert "act_" in payload["setup"]["safe_metadata"][0]
    assert "Business portfolio ID" in payload["setup"]["safe_metadata"][1]

    config_text = (repo / ".mb" / "connect.yaml").read_text(encoding="utf-8")
    assert "meta-secret-token" not in config_text
    config = yaml.safe_load(config_text)
    meta = config["providers"]["meta"]
    assert meta["metadata"] == {"ad_account_id": "act_test"}
    assert meta["account_label"] == "Meta Test"
    assert meta["secrets"]["access_token"]["backend"] == "local-file"

    secret_file = tmp_path / "home" / "secrets" / "connect.json"
    assert "meta-secret-token" in secret_file.read_text(encoding="utf-8")


def test_meta_status_preserves_stale_metadata_but_reports_missing_secret(
    tmp_path: Path, monkeypatch
) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    monkeypatch.setattr(connect_mod, "_meta_prerequisite_state", lambda **kwargs: "")
    repo = tmp_path / "biz"
    repo.mkdir()
    config_path = repo / ".mb" / "connect.yaml"
    config_path.parent.mkdir()
    config_path.write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "repo_id": "repo",
                "providers": {
                    "meta": {
                        "provider": "meta",
                        "connected": True,
                        "account_label": "Old Meta",
                        "metadata": {"ad_account_id": "act_123"},
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    status = connect_mod.status_provider("meta", repo)

    assert status["state"] == "missing_secret"
    assert status["connected"] is True
    assert status["repair_command"] == (
        "mb connect meta --token-stdin --metadata ad_account_id=<act_id>"
    )
    assert status["metadata"] == {"ad_account_id": "act_123"}

    aggregate = connect_mod.status_all(repo)
    assert aggregate["ok"] is False
    assert aggregate["summary"]["configured"] == 1
    assert aggregate["summary"]["needs_repair"] == 1
    assert aggregate["providers"][0]["state"] == "missing_secret"

    check = connect_mod.doctor_check(repo, status=aggregate)
    assert check["ok"] is False
    assert "meta" in check["detail"]


def test_connect_test_meta_reports_missing_metadata(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    _connect_meta_ready_prereqs(monkeypatch)
    repo = tmp_path / "biz"
    repo.mkdir()
    runner.invoke(
        app,
        ["connect", "meta", "--repo", str(repo), "--token", "meta-secret-token"],
    )

    result = runner.invoke(app, ["connect", "test", "meta", "--repo", str(repo), "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["status"]["state"] == "missing_metadata"
    assert (
        payload["status"]["repair_command"] == "mb connect meta --metadata ad_account_id=<act_id>"
    )
    assert "meta-secret-token" not in result.stdout


def test_connect_test_meta_missing_cli_has_python312_repair(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    connect_mod.connect_provider(
        "meta",
        repo=repo,
        token="meta-secret-token",
        metadata_pairs=["ad_account_id=act_test"],
    )

    result = connect_mod.test_provider(
        "meta",
        repo,
        which_func=lambda name: "/usr/bin/python3.12" if name == "python3.12" else None,
        command_runner=lambda args, cwd=None, timeout=5.0: {
            "ok": True,
            "returncode": 0,
            "stdout": "3.12\n",
            "stderr": "",
        },
    )

    assert result["ok"] is False
    assert result["status"]["state"] == "missing_cli"
    assert result["status"]["repair_command"] == (
        "pipx install --python <python3.12-or-newer> meta-ads"
    )


def test_connect_test_meta_uses_installed_cli_before_python_repair(
    tmp_path: Path, monkeypatch
) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    monkeypatch.setattr(sys, "version_info", (3, 11))
    repo = tmp_path / "biz"
    repo.mkdir()
    connect_mod.connect_provider(
        "meta",
        repo=repo,
        token="meta-secret-token",
        metadata_pairs=["ad_account_id=act_test"],
    )
    calls: list[list[str]] = []

    def fake_run(
        args: list[str],
        cwd: Path | None = None,
        timeout: float = 5.0,
        *,
        env: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        calls.append(args)
        if args == ["meta", "--version"]:
            return {"ok": True, "returncode": 0, "stdout": "meta 1.0.1\n", "stderr": ""}
        return {"ok": True, "returncode": 0, "stdout": "{}\n", "stderr": ""}

    result = connect_mod.test_provider(
        "meta",
        repo,
        which_func=lambda name: "/opt/pipx/bin/meta" if name == "meta" else None,
        command_runner=fake_run,
    )

    assert result["ok"] is True
    assert result["status"]["state"] == "ready"
    assert calls[0] == ["meta", "--version"]
    assert all("python" not in call[0] for call in calls)


def test_connect_test_meta_read_only_smoke_passes_with_sanitized_env(
    tmp_path: Path, monkeypatch
) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    connect_mod.connect_provider(
        "meta",
        repo=repo,
        token="meta-secret-token",
        metadata_pairs=["ad_account_id=act_test", "business_id=biz_test"],
    )
    calls: list[tuple[list[str], dict[str, str]]] = []

    def fake_run(
        args: list[str],
        cwd: Path | None = None,
        timeout: float = 5.0,
        *,
        env: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if args == ["meta", "--version"]:
            return {"ok": True, "returncode": 0, "stdout": "meta 1.0.1\n", "stderr": ""}
        calls.append((args, env or {}))
        return {"ok": True, "returncode": 0, "stdout": "{}\n", "stderr": ""}

    result = connect_mod.test_provider(
        "meta",
        repo,
        which_func=_fake_meta_which,
        command_runner=fake_run,
    )

    assert result["ok"] is True
    assert result["status"]["state"] == "ready"
    assert [call[0] for call in calls] == [
        ["meta", "auth", "status"],
        ["meta", "-o", "json", "ads", "adaccount", "list"],
        ["meta", "-o", "json", "ads", "campaign", "list"],
        [
            "meta",
            "-o",
            "json",
            "ads",
            "insights",
            "get",
            "--fields",
            "spend,impressions,clicks,ctr,cpc",
        ],
        ["meta", "-o", "json", "ads", "dataset", "list"],
    ]
    assert calls[0][1]["ACCESS_TOKEN"] == "meta-secret-token"
    assert calls[0][1]["AD_ACCOUNT_ID"] == "act_test"
    assert calls[0][1]["BUSINESS_ID"] == "biz_test"
    assert "meta-secret-token" not in json.dumps(result)


def test_connect_test_meta_admin_approval_state(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    connect_mod.connect_provider(
        "meta",
        repo=repo,
        token="meta-secret-token",
        metadata_pairs=["ad_account_id=act_test"],
    )

    def fake_run(
        args: list[str],
        cwd: Path | None = None,
        timeout: float = 5.0,
        *,
        env: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if args == ["meta", "--version"]:
            return {"ok": True, "returncode": 0, "stdout": "meta 1.0.1\n", "stderr": ""}
        return {
            "ok": False,
            "returncode": 1,
            "stdout": "",
            "stderr": "Waiting for another business admin approval.",
        }

    result = connect_mod.test_provider(
        "meta",
        repo,
        which_func=_fake_meta_which,
        command_runner=fake_run,
    )

    assert result["ok"] is False
    assert result["status"]["state"] == "waiting_for_admin_approval"
    assert result["status"]["summary"] == (
        "Meta needs another business admin to approve this connection."
    )
    assert result["status"]["repair"] == (
        "Meta needs another business admin to approve this connection. Nothing is broken locally."
    )


def test_connect_test_meta_read_smoke_failure_state(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    connect_mod.connect_provider(
        "meta",
        repo=repo,
        token="meta-secret-token",
        metadata_pairs=["ad_account_id=act_test"],
    )
    calls: list[list[str]] = []

    def fake_run(
        args: list[str],
        cwd: Path | None = None,
        timeout: float = 5.0,
        *,
        env: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        if args == ["meta", "--version"]:
            return {"ok": True, "returncode": 0, "stdout": "meta 1.0.1\n", "stderr": ""}
        calls.append(args)
        ok = args == ["meta", "auth", "status"]
        return {
            "ok": ok,
            "returncode": 0 if ok else 1,
            "stdout": "{}\n" if ok else "",
            "stderr": "" if ok else "permission denied",
        }

    result = connect_mod.test_provider(
        "meta",
        repo,
        which_func=_fake_meta_which,
        command_runner=fake_run,
    )

    assert result["ok"] is False
    assert result["status"]["state"] == "read_smoke_failed"
    assert calls == [
        ["meta", "auth", "status"],
        ["meta", "-o", "json", "ads", "adaccount", "list"],
    ]


def test_status_peek_exposes_meta_integration_state(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    monkeypatch.setattr(connect_mod, "_meta_prerequisite_state", lambda **kwargs: "")
    repo = tmp_path / "biz"
    repo.mkdir()
    connect_mod.connect_provider(
        "meta",
        repo=repo,
        token="meta-secret-token",
        metadata_pairs=["ad_account_id=act_test"],
    )

    result = runner.invoke(app, ["status", str(repo), "--json", "--peek"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    meta = payload["integrations"]["providers"][0]
    assert meta["provider"] == "meta"
    assert meta["state"] == "unvalidated"
    assert meta["repair_command"] == "mb connect test meta"
    assert "meta-secret-token" not in result.stdout


def test_connect_plan_human_output_uses_numbered_choices(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "biz"
    repo.mkdir()
    github_context = {
        "ok": True,
        "state": "ready",
        "summary": "GitHub CLI auth and repo remote are ready.",
        "repair": "",
        "repair_command": "",
        "safe_to_share": True,
    }
    monkeypatch.setattr(connect_mod, "github_context", lambda repo: github_context)
    monkeypatch.setattr(connect_mod, "_meta_prerequisite_state", lambda **kwargs: "missing_cli")

    result = runner.invoke(app, ["connect", "plan", "--repo", str(repo)])

    assert result.exit_code == 0
    assert "1. GitHub (ready)" in result.stdout
    assert "2. Cloudflare (not_connected)" in result.stdout
    assert "next: mb connect cloudflare --token-stdin" in result.stdout
    assert not (repo / ".mb" / "connect.yaml").exists()


def test_connect_provider_stores_secret_outside_repo(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()

    result = runner.invoke(
        app,
        [
            "connect",
            "cloudflare",
            "--repo",
            str(repo),
            "--account",
            "Acme CF",
            "--token",
            "cf-test-token",
            "--metadata",
            "account_id=acct_123",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["ready"] is False
    assert payload["credential_backend"] == "local-file"
    assert payload["status"]["state"] == "unvalidated"
    assert payload["status"]["repair_command"] == "mb connect test cloudflare"

    config_path = repo / ".mb" / "connect.yaml"
    config_text = config_path.read_text(encoding="utf-8")
    assert "cf-test-token" not in config_text
    config = yaml.safe_load(config_text)
    cloudflare = config["providers"]["cloudflare"]
    assert cloudflare["metadata"] == {"account_id": "acct_123"}
    assert cloudflare["account_label"] == "Acme CF"
    assert config["repo_identity"]["source"] in {"git_common_dir", "path"}

    secret_file = tmp_path / "home" / "secrets" / "connect.json"
    assert "cf-test-token" in secret_file.read_text(encoding="utf-8")
    assert stat.S_IMODE(secret_file.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(secret_file.stat().st_mode) == 0o600


def test_connect_status_filters_hand_edited_secret_like_metadata(
    tmp_path: Path, monkeypatch
) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    connect_mod.connect_provider(
        "cloudflare",
        repo=repo,
        token="cf-test-token",
        account_label="Acme CF",
        metadata_pairs=["account_id=acct_123"],
    )
    config_path = repo / ".mb" / "connect.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["providers"]["cloudflare"]["account_label"] = "sk-live-label-secret"
    config["providers"]["cloudflare"]["metadata"]["api_key"] = "sk-live-metadata-secret"
    config["providers"]["cloudflare"]["metadata"]["zone_id"] = "zone_456"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

    status = connect_mod.status_provider("cloudflare", repo=repo)

    assert status["safe_to_share"] is True
    assert status["account_label"] == connect_mod.SECRET_REPLACEMENT
    assert status["metadata"] == {"account_id": "acct_123", "zone_id": "zone_456"}
    assert "sk-live" not in json.dumps(status)
    assert "api_key" not in status["metadata"]


def test_connect_repo_identity_is_stable_across_worktrees(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    first = tmp_path / "biz-one"
    second = tmp_path / "biz-two"
    first.mkdir()
    second.mkdir()

    def fake_git(repo: Path, args: list[str]) -> str:
        if args == ["config", "--get", "remote.origin.url"]:
            return "git@github.com:acme/business.git"
        return ""

    monkeypatch.setattr(connect_mod, "_git_output", fake_git)

    connect_mod.connect_provider("cloudflare", repo=first, token="first-token")
    connect_mod.connect_provider("cloudflare", repo=second, token="second-token")

    first_config = yaml.safe_load((first / ".mb" / "connect.yaml").read_text(encoding="utf-8"))
    second_config = yaml.safe_load((second / ".mb" / "connect.yaml").read_text(encoding="utf-8"))
    assert first_config["repo_id"] == second_config["repo_id"]
    assert first_config["repo_identity"]["source"] == "git_remote"
    assert (
        first_config["providers"]["cloudflare"]["secrets"]["api_token"]["ref"]
        == second_config["providers"]["cloudflare"]["secrets"]["api_token"]["ref"]
    )


def test_connect_user_scope_hydrates_disposable_checkout(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    canonical = tmp_path / "canonical"
    disposable = tmp_path / "workspace"
    canonical.mkdir()
    disposable.mkdir()

    def fake_git(repo: Path, args: list[str]) -> str:
        if args == ["config", "--get", "remote.origin.url"]:
            return "git@github.com:acme/business.git"
        return ""

    monkeypatch.setattr(connect_mod, "_git_output", fake_git)

    result = connect_mod.connect_provider(
        "cloudflare",
        repo=canonical,
        token="cf-test-token",
        account_label="Acme Cloudflare",
        metadata_pairs=["account_id=acct_123", "zone_id=zone_456"],
        scope="user",
    )

    assert result["ok"] is True
    assert result["scope"] == "user"
    assert result["hydrated"] is True
    assert Path(result["user_scope_path"]).exists()
    assert "cf-test-token" not in Path(result["user_scope_path"]).read_text(encoding="utf-8")

    monkeypatch.chdir(disposable)  # inside the workspace the command stays bare
    before = connect_mod.status_provider("cloudflare", disposable)
    assert before["state"] == "needs_hydration"
    assert before["user_scope_available"] is True
    assert before["hydrated"] is False
    assert before["repair_command"] == "mb connect hydrate --repo ."
    assert not (disposable / ".mb" / "connect.yaml").exists()

    aggregate = connect_mod.status_all(disposable)
    assert aggregate["summary"]["configured"] == 1
    assert aggregate["summary"]["needs_repair"] == 1
    assert aggregate["providers"][0]["state"] == "needs_hydration"

    doctor = connect_mod.doctor(disposable)
    cloudflare = next(check for check in doctor["checks"] if check["name"] == "provider:cloudflare")
    assert cloudflare["state"] == "needs_hydration"
    assert cloudflare["repair_command"] == "mb connect hydrate --repo ."

    hydrated = connect_mod.hydrate(disposable)

    assert hydrated["ok"] is True
    assert hydrated["hydrated"] == ["cloudflare"]
    config = yaml.safe_load((disposable / ".mb" / "connect.yaml").read_text(encoding="utf-8"))
    assert config["providers"]["cloudflare"]["account_label"] == "Acme Cloudflare"
    assert config["providers"]["cloudflare"]["metadata"] == {
        "account_id": "acct_123",
        "zone_id": "zone_456",
    }
    assert "cf-test-token" not in (disposable / ".mb" / "connect.yaml").read_text(encoding="utf-8")

    after = connect_mod.status_provider("cloudflare", disposable)
    assert after["state"] == "unvalidated"
    assert after["scope"] == "user"
    assert after["hydrated"] is True
    assert after["secrets"]["api_token"]["present"] is True


def test_connect_user_scope_keeps_different_repos_isolated(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()

    def fake_git(repo: Path, args: list[str]) -> str:
        if args == ["config", "--get", "remote.origin.url"]:
            slug = "first" if repo == first else "second"
            return f"git@github.com:acme/{slug}.git"
        return ""

    monkeypatch.setattr(connect_mod, "_git_output", fake_git)

    connect_mod.connect_provider(
        "cloudflare",
        repo=first,
        token="first-token",
        metadata_pairs=["account_id=acct_first"],
        scope="user",
    )

    second_status = connect_mod.status_provider("cloudflare", second)
    second_all = connect_mod.status_all(second)
    hydrated = connect_mod.hydrate(second)

    assert second_status["state"] == "not_connected"
    assert second_status["user_scope_available"] is False
    assert second_all["providers"] == []
    assert hydrated["ok"] is False
    assert hydrated["hydrated"] == []
    assert not (second / ".mb" / "connect.yaml").exists()


def test_connect_user_scope_validation_updates_hydration_source(
    tmp_path: Path, monkeypatch
) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    canonical = tmp_path / "canonical"
    disposable = tmp_path / "workspace"
    canonical.mkdir()
    disposable.mkdir()

    def fake_git(repo: Path, args: list[str]) -> str:
        if args == ["config", "--get", "remote.origin.url"]:
            return "git@github.com:acme/business.git"
        return ""

    monkeypatch.setattr(connect_mod, "_git_output", fake_git)
    connect_mod.connect_provider(
        "postiz",
        repo=canonical,
        token="postiz-token",
        metadata_pairs=["workspace=acme"],
        scope="user",
    )

    tested = connect_mod.test_provider("postiz", canonical)
    hydrated = connect_mod.hydrate(disposable, provider_id="postiz")
    after = connect_mod.status_provider("postiz", disposable)

    assert tested["ok"] is False
    assert hydrated["ok"] is True
    assert after["state"] == connect_mod.UNVERIFIED_STATE
    assert after["stored"] is True
    assert after["provider_verified"] is False
    assert (
        after["validation"]["summary"]
        == "Postiz has a stored credential, but Main Branch has no automated way to "
        "confirm it works with the provider."
    )


def test_connect_hydrate_cli_materializes_user_scope_metadata(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    canonical = tmp_path / "canonical"
    disposable = tmp_path / "workspace"
    canonical.mkdir()
    disposable.mkdir()

    def fake_git(repo: Path, args: list[str]) -> str:
        if args == ["config", "--get", "remote.origin.url"]:
            return "git@github.com:acme/business.git"
        if args == ["rev-parse", "--is-inside-work-tree"]:
            return "true"
        return ""

    monkeypatch.setattr(connect_mod, "_git_output", fake_git)

    connected = runner.invoke(
        app,
        [
            "connect",
            "cloudflare",
            "--repo",
            str(canonical),
            "--scope",
            "user",
            "--token",
            "cf-token",
            "--metadata",
            "account_id=acct_123",
            "--json",
        ],
    )
    hydrated = runner.invoke(
        app,
        ["connect", "hydrate", "--repo", str(disposable), "--json"],
    )

    assert connected.exit_code == 0
    connected_payload = json.loads(connected.stdout)
    assert connected_payload["scope"] == "user"
    assert connected_payload["hydrated"] is True
    assert hydrated.exit_code == 0
    hydrated_payload = json.loads(hydrated.stdout)
    assert hydrated_payload["hydrated"] == ["cloudflare"]
    assert (disposable / ".mb" / "connect.yaml").exists()


def test_connect_normalizes_common_remote_protocol_variants() -> None:
    assert connect_mod._normalized_remote("git@gitlab.com:team/business.git") == (
        "https://gitlab.com/team/business"
    )
    assert connect_mod._normalized_remote("ssh://git@gitlab.com/team/business.git") == (
        "https://gitlab.com/team/business"
    )
    assert connect_mod._normalized_remote("https://gitlab.com/team/business.git") == (
        "https://gitlab.com/team/business"
    )


def test_connect_preserves_existing_repo_id_to_avoid_orphaned_secrets(
    tmp_path: Path, monkeypatch
) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    (repo / ".mb").mkdir(parents=True)
    (repo / ".mb" / "connect.yaml").write_text(
        yaml.safe_dump({"version": 1, "repo_id": "legacy-random-id", "providers": {}}),
        encoding="utf-8",
    )

    connect_mod.connect_provider("cloudflare", repo=repo, token="cf-secret-token")

    config = yaml.safe_load((repo / ".mb" / "connect.yaml").read_text(encoding="utf-8"))
    assert config["repo_id"] == "legacy-random-id"
    assert config["repo_identity"]["repo_id_source"] == "existing_config"
    assert config["providers"]["cloudflare"]["secrets"]["api_token"]["ref"] == (
        connect_mod._secret_ref("legacy-random-id", "cloudflare", "api_token")
    )


def test_connect_provider_only_reads_env_when_explicit(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    monkeypatch.setenv("APIFY_TOKEN", "apify-test-token")
    repo = tmp_path / "biz"
    repo.mkdir()

    implicit = runner.invoke(app, ["connect", "apify", "--repo", str(repo), "--json"])

    assert implicit.exit_code == 1
    implicit_payload = json.loads(implicit.stdout)
    assert implicit_payload["status"]["state"] == "missing_secret"

    explicit = runner.invoke(
        app,
        ["connect", "apify", "--repo", str(repo), "--from-env", "--json"],
    )

    assert explicit.exit_code == 0
    explicit_payload = json.loads(explicit.stdout)
    assert explicit_payload["credential_source"] == {
        "type": "env",
        "env_var": "APIFY_TOKEN",
    }
    assert explicit_payload["status"]["state"] == "unvalidated"
    assert "apify-test-token" not in (repo / ".mb" / "connect.yaml").read_text(encoding="utf-8")


def test_connect_status_reports_missing_secret_as_repair_not_hard_crash(
    tmp_path: Path, monkeypatch
) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()

    result = runner.invoke(app, ["connect", "cloudflare", "--repo", str(repo), "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["status"]["state"] == "missing_secret"

    status = runner.invoke(app, ["connect", "status", "--repo", str(repo), "--json"])
    assert status.exit_code == 1
    status_payload = json.loads(status.stdout)
    assert status_payload["summary"]["needs_repair"] == 1
    assert status_payload["providers"][0]["secrets"]["api_token"]["present"] is False
    assert status_payload["providers"][0]["state"] == "missing_secret"
    assert status_payload["providers"][0]["repair_command"] == "mb connect cloudflare --token-stdin"
    assert status_payload["providers"][0]["safe_to_share"] is True


def test_connect_status_reports_unvalidated_secret_without_claiming_health(
    tmp_path: Path, monkeypatch
) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()

    result = runner.invoke(
        app,
        ["connect", "cloudflare", "--repo", str(repo), "--token", "cf-test-token", "--json"],
    )

    assert result.exit_code == 0
    status = runner.invoke(app, ["connect", "status", "--repo", str(repo), "--json"])
    assert status.exit_code == 1
    payload = json.loads(status.stdout)
    provider = payload["providers"][0]
    assert payload["summary"]["configured"] == 1
    assert payload["summary"]["healthy"] == 0
    assert payload["summary"]["unvalidated"] == 1
    assert provider["state"] == "unvalidated"
    assert provider["summary"]
    assert provider["repair"] == "Run `mb connect test cloudflare`."
    assert provider["repair_command"] == "mb connect test cloudflare"
    assert provider["safe_to_share"] is True
    assert "cf-test-token" not in status.stdout


def test_connect_test_marks_metadata_only_provider_ready(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    connect_mod.connect_provider(
        "hledger",
        repo=repo,
        metadata_pairs=[
            "journal_path=.mb/private/books/main.journal",
            "vault_path=.mb/private/books/",
        ],
    )

    result = runner.invoke(app, ["connect", "test", "hledger", "--repo", str(repo), "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["status"]["state"] == "ready"
    assert payload["status"]["repair_command"] == ""


def test_connect_test_records_invalid_provider_without_leaking_secret(
    tmp_path: Path, monkeypatch
) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    runner.invoke(
        app,
        ["connect", "cloudflare", "--repo", str(repo), "--token", "cf-secret-token", "--json"],
    )
    monkeypatch.setattr(
        connect_mod,
        "_http_get_json",
        lambda url, headers=None, **kwargs: {
            "ok": False,
            "state": "invalid",
            "summary": "Cloudflare rejected the credential. Create a fresh token and reconnect it.",
            "safe_to_share": True,
            "upstream": {
                "endpoint_family": kwargs["endpoint_family"],
                "http_status": 403,
                "response_received": True,
                "error_codes": ["9109"],
                "error_messages": ["Invalid access token <redacted>"],
                "safe_to_share": True,
            },
        },
    )

    result = runner.invoke(app, ["connect", "test", "cloudflare", "--repo", str(repo), "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["status"]["state"] == "invalid"
    assert payload["status"]["repair_command"] == "mb connect cloudflare --token-stdin"
    assert "rejected the credential" in payload["status"]["validation"]["summary"]
    assert payload["validation"]["upstream"]["endpoint_family"] == "cloudflare_user_token_verify"
    assert payload["validation"]["upstream"]["http_status"] == 403
    assert payload["validation"]["upstream"]["error_codes"] == ["9109"]
    assert payload["validation"]["upstream"]["error_messages"] == [
        "Invalid access token <redacted>"
    ]
    assert "cf-secret-token" not in result.stdout


def test_connect_redacts_secret_material_from_provider_errors() -> None:
    codes, messages = connect_mod._extract_upstream_errors(
        {
            "errors": [
                {
                    "code": "bad_auth",
                    "message": "Invalid access token cf-secret-token for request",
                },
                {"message": "Authorization: Bearer sk-live-secret"},
                {"message": "api_key=plain-secret-value"},
            ]
        },
        secret_values=("cf-secret-token", "sk-live-secret", "plain-secret-value"),
    )

    serialized = json.dumps({"codes": codes, "messages": messages})
    assert "cf-secret-token" not in serialized
    assert "sk-live-secret" not in serialized
    assert "plain-secret-value" not in serialized
    assert messages == [
        "Invalid access token <redacted> for request",
        "Authorization: Bearer <redacted>",
        "api_key=<redacted>",
    ]


def test_connect_test_routes_cloudflare_account_tokens_to_account_endpoint(
    tmp_path: Path, monkeypatch
) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    runner.invoke(
        app,
        [
            "connect",
            "cloudflare",
            "--repo",
            str(repo),
            "--token",
            "cf-secret-token",
            "--metadata",
            "token_type=account",
            "--metadata",
            "account_id=0123456789abcdef0123456789abcdef",
        ],
    )
    calls: list[str] = []

    def fake_http(url: str, headers=None, **kwargs) -> dict[str, Any]:
        calls.append(url)
        return {
            "ok": True,
            "state": "ready",
            "summary": "Cloudflare credential validated with provider.",
            "safe_to_share": True,
            "upstream": {
                "endpoint_family": kwargs["endpoint_family"],
                "http_status": 200,
                "response_received": True,
                "error_codes": [],
                "error_messages": [],
                "safe_to_share": True,
            },
        }

    monkeypatch.setattr(connect_mod, "_http_get_json", fake_http)

    result = runner.invoke(app, ["connect", "test", "cloudflare", "--repo", str(repo), "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["validation"]["upstream"]["endpoint_family"] == "cloudflare_account_token_verify"
    assert calls == [
        "https://api.cloudflare.com/client/v4/accounts/0123456789abcdef0123456789abcdef/tokens/verify"
    ]


def test_connect_test_detects_cloudflare_account_token_prefix(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    runner.invoke(
        app,
        [
            "connect",
            "cloudflare",
            "--repo",
            str(repo),
            "--token",
            "cfat_secret-token",
            "--metadata",
            "account_id=0123456789abcdef0123456789abcdef",
        ],
    )
    calls: list[str] = []

    def fake_http(url: str, headers=None, **kwargs) -> dict[str, Any]:
        calls.append(url)
        return {
            "ok": True,
            "state": "ready",
            "summary": "Cloudflare credential validated with provider.",
            "safe_to_share": True,
            "upstream": {
                "endpoint_family": kwargs["endpoint_family"],
                "http_status": 200,
                "response_received": True,
                "error_codes": [],
                "error_messages": [],
                "safe_to_share": True,
            },
        }

    monkeypatch.setattr(connect_mod, "_http_get_json", fake_http)

    result = runner.invoke(app, ["connect", "test", "cloudflare", "--repo", str(repo), "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["validation"]["upstream"]["endpoint_family"] == (
        "cloudflare_account_token_verify"
    )
    assert calls == [
        "https://api.cloudflare.com/client/v4/accounts/0123456789abcdef0123456789abcdef/tokens/verify"
    ]


def test_connect_test_routes_cloudflare_user_tokens_to_user_endpoint(
    tmp_path: Path, monkeypatch
) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    runner.invoke(
        app,
        ["connect", "cloudflare", "--repo", str(repo), "--token", "cf-secret-token"],
    )
    calls: list[str] = []

    def fake_http(url: str, headers=None, **kwargs) -> dict[str, Any]:
        calls.append(url)
        return {
            "ok": True,
            "state": "ready",
            "summary": "Cloudflare credential validated with provider.",
            "safe_to_share": True,
            "upstream": {
                "endpoint_family": kwargs["endpoint_family"],
                "http_status": 200,
                "response_received": True,
                "error_codes": [],
                "error_messages": [],
                "safe_to_share": True,
            },
        }

    monkeypatch.setattr(connect_mod, "_http_get_json", fake_http)

    result = runner.invoke(app, ["connect", "test", "cloudflare", "--repo", str(repo), "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["validation"]["upstream"]["endpoint_family"] == "cloudflare_user_token_verify"
    assert calls == ["https://api.cloudflare.com/client/v4/user/tokens/verify"]


def test_connect_test_account_token_uses_account_read_fallback_on_verify_404(
    tmp_path: Path, monkeypatch
) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    runner.invoke(
        app,
        [
            "connect",
            "cloudflare",
            "--repo",
            str(repo),
            "--token",
            "cf-secret-token",
            "--metadata",
            "token_type=account",
            "--metadata",
            "account_id=0123456789abcdef0123456789abcdef",
        ],
    )
    calls: list[tuple[str, str]] = []

    def fake_http(url: str, headers=None, **kwargs) -> dict[str, Any]:
        endpoint = kwargs["endpoint_family"]
        calls.append((endpoint, url))
        if endpoint == "cloudflare_account_token_verify":
            return {
                "ok": False,
                "state": "invalid",
                "summary": "Cloudflare could not find the requested account/token resource.",
                "safe_to_share": True,
                "upstream": {
                    "endpoint_family": endpoint,
                    "http_status": 404,
                    "response_received": True,
                    "error_codes": ["1003"],
                    "error_messages": ["Not found"],
                    "safe_to_share": True,
                },
            }
        return {
            "ok": True,
            "state": "ready",
            "summary": "Cloudflare credential validated with provider.",
            "safe_to_share": True,
            "upstream": {
                "endpoint_family": endpoint,
                "http_status": 200,
                "response_received": True,
                "error_codes": [],
                "error_messages": [],
                "safe_to_share": True,
            },
        }

    monkeypatch.setattr(connect_mod, "_http_get_json", fake_http)

    result = runner.invoke(app, ["connect", "test", "cloudflare", "--repo", str(repo), "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["validation"]["upstream"]["endpoint_family"] == "cloudflare_account_read"
    assert payload["validation"]["upstream"]["fallback_from"] == "cloudflare_account_token_verify"
    assert "fallback" in payload["validation"]["summary"]
    assert calls == [
        (
            "cloudflare_account_token_verify",
            "https://api.cloudflare.com/client/v4/accounts/0123456789abcdef0123456789abcdef/tokens/verify",
        ),
        (
            "cloudflare_account_read",
            "https://api.cloudflare.com/client/v4/accounts/0123456789abcdef0123456789abcdef",
        ),
    ]


def test_connect_test_account_token_requires_account_id(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    runner.invoke(
        app,
        [
            "connect",
            "cloudflare",
            "--repo",
            str(repo),
            "--token",
            "cf-secret-token",
            "--metadata",
            "token_type=account",
        ],
    )

    result = runner.invoke(app, ["connect", "test", "cloudflare", "--repo", str(repo), "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["status"]["state"] == "unvalidated"
    assert payload["status"]["repair_command"] == (
        "mb connect cloudflare --metadata token_type=account --metadata account_id=<account-id>"
    )
    assert "account_id" in payload["validation"]["summary"]
    assert payload["validation"]["repair_command"] == (
        "mb connect cloudflare --metadata token_type=account --metadata account_id=<account-id>"
    )
    assert payload["validation"]["upstream"]["response_received"] is False


def test_connect_test_no_probe_provider_reports_stored_unverified_without_loop(
    tmp_path: Path, monkeypatch
) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    runner.invoke(app, ["connect", "google", "--repo", str(repo), "--token", "google-token"])

    result = runner.invoke(app, ["connect", "test", "google", "--repo", str(repo), "--json"])

    # Exit 0: Google has no probe, so there is nothing the operator can run.
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["stored"] is True
    assert payload["provider_verified"] is False
    assert payload["verified_at"] == ""
    assert payload["status"]["state"] == connect_mod.UNVERIFIED_STATE
    # No repair command: rerunning `mb connect test` would record the same
    # unverified answer, so pointing back at it would be a loop.
    assert payload["status"]["repair_command"] == ""
    assert "no automated way to confirm it works" in payload["validation"]["summary"]
    assert "google-token" not in result.stdout

    status = runner.invoke(app, ["connect", "status", "--repo", str(repo), "--json"])
    assert status.exit_code == 0
    status_payload = json.loads(status.stdout)
    assert status_payload["summary"]["healthy"] == 0
    assert status_payload["summary"]["needs_repair"] == 0
    assert status_payload["summary"]["unverified"] == 1
    assert status_payload["providers"][0]["state"] == connect_mod.UNVERIFIED_STATE


def test_connect_test_transient_provider_failure_stays_unvalidated(
    tmp_path: Path, monkeypatch
) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    runner.invoke(app, ["connect", "cloudflare", "--repo", str(repo), "--token", "cf-secret-token"])
    monkeypatch.setattr(
        connect_mod,
        "_http_get_json",
        lambda url, headers=None, **kwargs: {
            "ok": False,
            "state": "unvalidated",
            "summary": (
                "Cloudflare validation returned HTTP 503. Retry after the provider recovers."
            ),
            "safe_to_share": True,
            "upstream": {
                "endpoint_family": kwargs["endpoint_family"],
                "http_status": 503,
                "response_received": True,
                "error_codes": [],
                "error_messages": [],
                "safe_to_share": True,
            },
        },
    )

    result = runner.invoke(app, ["connect", "test", "cloudflare", "--repo", str(repo), "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["status"]["state"] == "unvalidated"
    assert payload["status"]["repair_command"] == "mb connect test cloudflare"
    assert "HTTP 503" in payload["status"]["validation"]["summary"]
    assert "cf-secret-token" not in result.stdout


def test_token_stdin_prints_interactive_eof_prompt(monkeypatch, capsys) -> None:
    class FakeStdin:
        def isatty(self) -> bool:
            return True

        def read(self) -> str:
            return "secret-token\n"

    monkeypatch.setattr(sys, "stdin", FakeStdin())

    token = connect_mod.read_stdin_token()

    assert token == "secret-token"
    assert "Ctrl-D" in capsys.readouterr().err


def test_connect_doctor_includes_github_context_and_provider_repairs(
    tmp_path: Path, monkeypatch
) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    runner.invoke(app, ["connect", "cloudflare", "--repo", str(repo), "--json"])
    monkeypatch.setattr(connect_mod.shutil, "which", lambda name: "")  # type: ignore[attr-defined]

    result = runner.invoke(app, ["connect", "doctor", "--repo", str(repo), "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    checks = {check["name"]: check for check in payload["checks"]}
    assert checks["github-context"]["state"] == "missing_cli"
    assert checks["provider:cloudflare"]["state"] == "missing_secret"
    assert checks["provider:cloudflare"]["repair_command"] == "mb connect cloudflare --token-stdin"
    assert payload["safe_to_share"] is True


def test_github_context_distinguishes_missing_remote(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        connect_mod.shutil,  # type: ignore[attr-defined]
        "which",
        lambda name: "/usr/bin/gh" if name == "gh" else "",
    )

    def fake_run(args: list[str], cwd: Path | None = None, timeout: float = 5.0) -> dict[str, Any]:
        if args[:3] == ["gh", "auth", "status"]:
            return {"ok": True, "returncode": 0, "stdout": "", "stderr": ""}
        if args[:3] == ["git", "rev-parse", "--is-inside-work-tree"]:
            return {"ok": True, "returncode": 0, "stdout": "true\n", "stderr": ""}
        if args[:4] == ["git", "config", "--get", "remote.origin.url"]:
            return {"ok": False, "returncode": 1, "stdout": "", "stderr": ""}
        raise AssertionError(args)

    monkeypatch.setattr(connect_mod, "_run_command", fake_run)

    context = connect_mod.github_context(tmp_path)

    assert context["ok"] is False
    assert context["state"] == "missing_github_remote"
    assert context["repair_command"] == "gh repo create --source . --remote origin --push"


def test_github_context_trusts_repo_view_when_auth_status_is_stale(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        connect_mod.shutil,  # type: ignore[attr-defined]
        "which",
        lambda name: "/usr/bin/gh" if name == "gh" else "/usr/bin/git",
    )

    def fake_run(args: list[str], cwd: Path | None = None, timeout: float = 5.0) -> dict[str, Any]:
        if args[:3] == ["git", "rev-parse", "--is-inside-work-tree"]:
            return {"ok": True, "returncode": 0, "stdout": "true\n", "stderr": ""}
        if args[:4] == ["git", "config", "--get", "remote.origin.url"]:
            return {
                "ok": True,
                "returncode": 0,
                "stdout": "https://github.com/dmthepm/acme.git\n",
                "stderr": "",
            }
        if args[:3] == ["gh", "auth", "status"]:
            return {"ok": False, "returncode": 1, "stdout": "", "stderr": "stale token"}
        if args[:3] == ["gh", "repo", "view"]:
            return {
                "ok": True,
                "returncode": 0,
                "stdout": '{"nameWithOwner":"dmthepm/acme"}\n',
                "stderr": "",
            }
        raise AssertionError(args)

    monkeypatch.setattr(connect_mod, "_run_command", fake_run)

    context = connect_mod.github_context(tmp_path)

    assert context["ok"] is True
    assert context["state"] == "ready_reachable"
    assert context["repo"] == "dmthepm/acme"
    assert context["auth_status_ok"] is False
    assert context["repo_view_ok"] is True


def test_status_all_reuses_supplied_github_context(monkeypatch, tmp_path: Path) -> None:
    context = {
        "ok": True,
        "state": "ready",
        "summary": "cached GitHub context",
        "repair": "",
        "repair_command": "",
        "safe_to_share": True,
    }

    def fail_context(repo: Path) -> dict[str, Any]:
        raise AssertionError("github_context should not be recomputed")

    monkeypatch.setattr(connect_mod, "github_context", fail_context)

    status = connect_mod.status_all(tmp_path, github=context)

    assert status["github"] == context


def test_connect_status_tolerates_malformed_config_version(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    (repo / ".mb").mkdir()
    (repo / ".mb" / "connect.yaml").write_text(
        "version: not-a-number\nproviders: []\n",
        encoding="utf-8",
    )

    status = runner.invoke(app, ["connect", "status", "--repo", str(repo), "--json"])

    assert status.exit_code == 0
    status_payload = json.loads(status.stdout)
    assert status_payload["summary"]["configured"] == 0


def test_connect_refuses_to_clobber_invalid_yaml_config(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    (repo / ".mb").mkdir()
    config_path = repo / ".mb" / "connect.yaml"
    config_path.write_text("version: 1\nproviders: [\n", encoding="utf-8")

    result = runner.invoke(
        app,
        ["connect", "cloudflare", "--repo", str(repo), "--token", "cf-test-token", "--json"],
    )

    assert result.exit_code == 2
    assert "invalid YAML" in result.stderr
    assert config_path.read_text(encoding="utf-8") == "version: 1\nproviders: [\n"
    assert not (tmp_path / "secrets" / "connect.json").exists()


def test_connect_status_missing_config_still_reports_empty_state(
    tmp_path: Path, monkeypatch
) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()

    status = runner.invoke(app, ["connect", "status", "--repo", str(repo), "--json"])

    assert status.exit_code == 0
    payload = json.loads(status.stdout)
    assert payload["summary"]["configured"] == 0
    assert not (repo / ".mb" / "connect.yaml").exists()


def test_connect_refuses_symlinked_mb_directory_without_leaking_path(
    tmp_path: Path, monkeypatch
) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    outside = tmp_path / "outside"
    repo.mkdir()
    outside.mkdir()
    (repo / ".mb").symlink_to(outside, target_is_directory=True)

    result = runner.invoke(
        app,
        [
            "connect",
            "hledger",
            "--repo",
            str(repo),
            "--metadata",
            "vault_path=.mb/private/books",
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "local state path is a symlink" in result.stderr
    assert str(tmp_path) not in result.stderr
    assert not (outside / "connect.yaml").exists()


def test_connect_refuses_symlinked_connect_yaml_without_leaking_path(
    tmp_path: Path, monkeypatch
) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    outside = tmp_path / "outside"
    repo.mkdir()
    outside.mkdir()
    (repo / ".mb").mkdir()
    (repo / ".mb" / "connect.yaml").symlink_to(outside / "connect.yaml")

    result = runner.invoke(
        app,
        [
            "connect",
            "hledger",
            "--repo",
            str(repo),
            "--metadata",
            "vault_path=.mb/private/books",
            "--json",
        ],
    )

    assert result.exit_code == 2
    assert "local state path is a symlink" in result.stderr
    assert str(tmp_path) not in result.stderr
    assert not (outside / "connect.yaml").exists()


def test_connect_status_refuses_config_that_resolves_outside_repo(
    tmp_path: Path, monkeypatch
) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    outside = tmp_path / "outside"
    repo.mkdir()
    outside.mkdir()
    (outside / "connect.yaml").write_text(
        yaml.safe_dump({"version": 1, "providers": {"hledger": {"connected": True}}}),
        encoding="utf-8",
    )
    (repo / ".mb").symlink_to(outside, target_is_directory=True)

    status = runner.invoke(app, ["connect", "status", "--repo", str(repo), "--json"])

    assert status.exit_code == 2
    assert "local state path is a symlink" in status.stderr
    assert str(tmp_path) not in status.stderr


def test_checked_connect_config_path_rejects_outside_boundary(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "biz"
    outside = tmp_path / "outside" / "connect.yaml"
    repo.mkdir()
    outside.parent.mkdir()
    monkeypatch.setattr(connect_mod, "_config_path", lambda repo: outside)

    with pytest.raises(connect_mod.ConfigBoundaryError) as exc_info:
        connect_mod.status_all(repo)

    assert str(exc_info.value) == (
        "Refusing to use .mb/connect.yaml because it is outside the selected repo boundary."
    )
    assert str(tmp_path) not in str(exc_info.value)


def test_checked_connect_config_path_rejects_invalid_local_state_directory(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "biz"
    repo.mkdir()
    (repo / ".mb").write_text("not a directory", encoding="utf-8")

    with pytest.raises(connect_mod.ConfigBoundaryError, match="local state directory is invalid"):
        connect_mod.status_all(repo)


def test_doctor_and_status_include_integration_state(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    connect_mod.connect_provider(
        "hledger",
        repo=repo,
        metadata_pairs=[
            "journal_path=.mb/private/books/main.journal",
            "vault_path=.mb/private/books/",
        ],
    )

    doctor_report = runner.invoke(app, ["doctor", str(repo), "--json"])
    doctor_payload = json.loads(doctor_report.stdout)
    assert doctor_payload["integrations"]["summary"]["configured"] == 1
    assert "integration-credentials" in {check["name"] for check in doctor_payload["checks"]}

    status_report = runner.invoke(app, ["status", str(repo), "--json"])
    assert status_report.exit_code == 0
    status_payload = json.loads(status_report.stdout)
    assert status_payload["integrations"]["summary"]["healthy"] == 1


def _fake_native_store(monkeypatch, state: str) -> None:
    monkeypatch.setattr(credential_store_mod.platform, "system", lambda: "Darwin")  # type: ignore[attr-defined]
    monkeypatch.setattr(
        credential_store_mod,
        "_run_helper",
        lambda backend, action, **kwargs: {"state": state},
    )


def test_macos_keychain_write_failure_reports_sanitized_auth_classification(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "macos-keychain")
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "home"))
    _fake_native_store(monkeypatch, "auth-failed")
    repo = tmp_path / "biz"
    repo.mkdir()

    with pytest.raises(connect_mod.KeychainError) as excinfo:
        connect_mod.connect_provider("resend", repo=repo, token="re_secret_token")

    message = str(excinfo.value)
    assert excinfo.value.reason == "keychain_auth_failed"
    assert "rejected credential access" in message
    assert "Nothing was stored" in message
    assert "Do not reset or delete the login keychain" in message
    assert "re_secret_token" not in message
    assert "auth-failed" not in message


def test_macos_keychain_write_failure_leaves_no_partial_metadata(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "macos-keychain")
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "home"))
    _fake_native_store(monkeypatch, "auth-failed")
    repo = tmp_path / "biz"
    repo.mkdir()

    result = runner.invoke(
        app,
        ["connect", "resend", "--repo", str(repo), "--token-stdin"],
        input="re_secret_token\n",
    )

    assert result.exit_code == 1
    assert "keychain" in result.stderr.lower()
    assert "re_secret_token" not in result.stderr
    assert not (repo / ".mb" / "connect.yaml").exists()


def test_locked_keychain_status_distinguishes_backend_failure_from_missing_secret(
    tmp_path: Path, monkeypatch
) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    connect_mod.connect_provider("resend", repo=repo, token="re_secret_token")
    config_path = repo / ".mb" / "connect.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["providers"]["resend"]["secrets"]["api_key"]["backend"] = "macos-keychain"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    _fake_native_store(monkeypatch, "auth-failed")

    status = connect_mod.status_provider("resend", repo)

    assert status["state"] == "backend_unavailable"
    assert status["ok"] is False
    assert status["secrets"]["api_key"]["backend_ok"] is False
    assert status["secrets"]["api_key"]["backend_state"] == "keychain_auth_failed"
    assert "Do not reset or delete the login keychain" in status["repair"]
    # The old advice — rerun the same connect command — cannot work here.
    assert "--token-stdin" not in status["repair_command"]


def test_missing_keychain_item_still_reports_missing_secret(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    connect_mod.connect_provider("resend", repo=repo, token="re_secret_token")
    config_path = repo / ".mb" / "connect.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["providers"]["resend"]["secrets"]["api_key"]["backend"] = "macos-keychain"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    _fake_native_store(monkeypatch, "missing")

    status = connect_mod.status_provider("resend", repo)

    assert status["state"] == "missing_secret"
    assert status["secrets"]["api_key"]["backend_ok"] is True


def test_doctor_checks_keychain_health_before_provider_reconnect(
    tmp_path: Path, monkeypatch
) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    connect_mod.connect_provider("resend", repo=repo, token="re_secret_token")
    config_path = repo / ".mb" / "connect.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["providers"]["resend"]["secrets"]["api_key"]["backend"] = "macos-keychain"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "macos-keychain")
    _fake_native_store(monkeypatch, "auth-failed")

    report = connect_mod.doctor(repo)

    checks = {check["name"]: check for check in report["checks"]}
    assert checks["credential-backend"]["ok"] is False
    assert checks["credential-backend"]["state"] == "keychain_auth_failed"
    assert checks["provider:resend"]["state"] == "backend_unavailable"
    assert report["ok"] is False
    payload = json.dumps(report)
    assert "re_secret_token" not in payload
    assert "auth-failed" not in payload


def test_doctor_skips_backend_check_when_no_provider_connected(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "macos-keychain")
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "home"))
    repo = tmp_path / "biz"
    repo.mkdir()
    # An unhealthy Keychain must not warn when nothing depends on it yet.
    _fake_native_store(monkeypatch, "auth-failed")

    report = connect_mod.doctor(repo)

    names = {check["name"] for check in report["checks"]}
    assert "credential-backend" not in names


def test_status_briefing_leads_with_backend_failure(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    connect_mod.connect_provider("resend", repo=repo, token="re_secret_token")
    config_path = repo / ".mb" / "connect.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["providers"]["resend"]["secrets"]["api_key"]["backend"] = "macos-keychain"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    _fake_native_store(monkeypatch, "auth-failed")

    check = connect_mod.doctor_check(repo)

    assert check["ok"] is False
    assert "credential backend is unhealthy" in check["detail"]
    assert "Do not reset or delete the login keychain" in check["repair"]


def test_keychain_health_reports_locked_without_raw_output(monkeypatch) -> None:
    _fake_native_store(monkeypatch, "locked")

    health = connect_mod.credential_backend_health("macos-keychain")

    assert health["ok"] is False
    assert health["state"] == "keychain_locked"
    assert health["repair_command"].startswith("security unlock-keychain")
    assert "remote session" in health["repair"]


def test_auto_secret_backend_selects_native_macos_adapter(monkeypatch) -> None:
    monkeypatch.delenv("MB_CONNECT_SECRET_BACKEND", raising=False)
    monkeypatch.setattr(credential_store_mod.platform, "system", lambda: "Darwin")  # type: ignore[attr-defined]

    assert connect_mod._select_secret_backend() == "macos-keychain"


def test_connect_token_prints_secret_to_stdout(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    connect_mod.connect_provider("cloudflare", repo=repo, token="cf-test-token")

    result = runner.invoke(app, ["connect", "token", "cloudflare", "--print", "--repo", str(repo)])

    assert result.exit_code == 0
    assert result.stdout == "cf-test-token"


def test_connect_token_falls_back_to_user_scope(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    connect_mod.connect_provider("cloudflare", repo=repo, token="cf-user-token", scope="user")
    (repo / ".mb" / "connect.yaml").unlink()

    result = runner.invoke(app, ["connect", "token", "cloudflare", "--print", "--repo", str(repo)])

    assert result.exit_code == 0
    assert result.stdout == "cf-user-token"


def test_connect_token_not_connected_fails(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()

    result = runner.invoke(app, ["connect", "token", "cloudflare", "--print", "--repo", str(repo)])

    assert result.exit_code == 1
    assert result.stdout == ""
    assert "not connected" in result.stderr
    assert "mb connect cloudflare --token-stdin" in result.stderr


def test_connect_token_missing_stored_secret_fails(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    connect_mod.connect_provider("cloudflare", repo=repo)

    result = runner.invoke(app, ["connect", "token", "cloudflare", "--print", "--repo", str(repo)])

    assert result.exit_code == 1
    assert result.stdout == ""
    assert "credential is missing from the secret store" in result.stderr


def test_connect_token_requires_provider(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)

    result = runner.invoke(app, ["connect", "token"])

    assert result.exit_code == 2
    assert "provider required" in result.stderr


def test_connect_token_rejects_json(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    connect_mod.connect_provider("cloudflare", repo=repo, token="cf-test-token")

    result = runner.invoke(
        app, ["connect", "token", "cloudflare", "--print", "--repo", str(repo), "--json"]
    )

    assert result.exit_code == 2
    # A JSON error envelope only (#973); the token never reaches JSON.
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["state"] == "json_not_supported"
    assert "cf-test-token" not in result.output
    assert "--json is not supported" in result.stderr


def test_connect_token_rejects_secretless_provider(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()

    result = runner.invoke(app, ["connect", "token", "hledger", "--print", "--repo", str(repo)])

    assert result.exit_code == 2
    assert "stores no secrets" in result.stderr


def test_connect_token_refuses_terminal_or_pipe_without_print(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    connect_mod.connect_provider("cloudflare", repo=repo, token="cf-test-token")

    result = runner.invoke(app, ["connect", "token", "cloudflare", "--repo", str(repo)])

    assert result.exit_code == connect_mod.TOKEN_REFUSED_EXIT_CODE
    assert result.stdout == ""
    assert "cf-test-token" not in result.output
    assert "mb connect exec cloudflare -- <command>" in result.stderr
    assert "mb connect token cloudflare > file" in result.stderr
    assert "--print" in result.stderr


def test_token_refusal_exit_code_is_pinned_and_distinct() -> None:
    """Scripts match on this number (#1011); changing it is a breaking change."""

    assert connect_mod.TOKEN_REFUSED_EXIT_CODE == 3
    # 1: credential missing, unreadable or store failure; 2: usage and other refusals.
    assert connect_mod.TOKEN_REFUSED_EXIT_CODE not in {0, 1, 2}


def _token_subprocess_env(tmp_path: Path) -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if not any(key in provider.env_vars for provider in connect_mod.PROVIDERS)
    }
    env["MB_CONNECT_SECRET_BACKEND"] = "local-file"
    env["MAINBRANCH_HOME"] = str(tmp_path / "home")
    env["MB_FEEDBACK_LOG"] = "0"
    return env


@pytest.mark.parametrize("stdout_kind", ["pipe", "terminal"])
def test_connect_token_refusal_exit_code_for_a_real_pipe_and_terminal(
    tmp_path: Path, monkeypatch, stdout_kind: str
) -> None:
    if stdout_kind == "terminal" and sys.platform == "win32":
        pytest.skip("needs a pty")
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    connect_mod.connect_provider("cloudflare", repo=repo, token="cf-test-token")
    argv = [sys.executable, "-m", "mb", "connect", "token", "cloudflare", "--repo", str(repo)]
    env = _token_subprocess_env(tmp_path)

    if stdout_kind == "pipe":
        completed = subprocess.run(
            argv, capture_output=True, text=True, env=env, timeout=60, check=False
        )
        returncode, stdout, stderr = completed.returncode, completed.stdout, completed.stderr
    else:
        import pty

        leader, follower = pty.openpty()
        try:
            completed = subprocess.run(
                argv,
                stdout=follower,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                timeout=60,
                check=False,
            )
            os.close(follower)
            follower = -1
            chunks: list[bytes] = []
            while True:
                try:
                    chunk = os.read(leader, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                chunks.append(chunk)
        finally:
            if follower != -1:
                os.close(follower)
            os.close(leader)
        returncode, stdout, stderr = (
            completed.returncode,
            b"".join(chunks).decode(),
            completed.stderr,
        )

    assert returncode == connect_mod.TOKEN_REFUSED_EXIT_CODE == 3
    assert stdout == ""
    assert "cf-test-token" not in stdout + stderr
    assert "mb connect exec cloudflare -- <command>" in stderr


def test_connect_token_print_still_writes_to_a_real_pipe(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    connect_mod.connect_provider("cloudflare", repo=repo, token="cf-test-token")

    completed = subprocess.run(
        [sys.executable, "-m", "mb", "connect", "token", "cloudflare", "--print"]
        + ["--repo", str(repo)],
        capture_output=True,
        text=True,
        env=_token_subprocess_env(tmp_path),
        timeout=60,
        check=False,
    )

    assert completed.returncode == 0
    assert completed.stdout == "cf-test-token"


def test_connect_token_plain_file_redirect_needs_no_print_flag(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    connect_mod.connect_provider("cloudflare", repo=repo, token="cf-test-token")
    out = tmp_path / "token-file"

    with out.open("w") as handle:
        completed = subprocess.run(
            [sys.executable, "-m", "mb", "connect", "token", "cloudflare", "--repo", str(repo)],
            stdout=handle,
            stderr=subprocess.PIPE,
            text=True,
            env=_token_subprocess_env(tmp_path),
            timeout=60,
            check=False,
        )

    assert completed.returncode == 0
    assert out.read_text() == "cf-test-token"


def test_connect_token_refusal_comes_before_the_provider_lookup(
    tmp_path: Path, monkeypatch
) -> None:
    """Exit 1 needs the stdout gate passed: not connected, through a pipe, is still 3."""

    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()

    for provider in ("cloudflare", "no-such-provider"):
        result = runner.invoke(app, ["connect", "token", provider, "--repo", str(repo)])
        assert result.exit_code == connect_mod.TOKEN_REFUSED_EXIT_CODE, provider
        assert "not connected" not in result.stderr


def test_connect_token_missing_credential_keeps_exit_1(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()

    result = runner.invoke(app, ["connect", "token", "cloudflare", "--print", "--repo", str(repo)])

    assert result.exit_code == 1
    assert "not connected" in result.stderr


def test_stdout_exposes_secret_for_tty_pipe_and_unknown(tmp_path: Path) -> None:
    class Tty:
        def isatty(self) -> bool:
            return True

    read_fd, write_fd = os.pipe()
    try:
        with os.fdopen(write_fd, "w") as pipe:
            assert connect_mod.stdout_exposes_secret(pipe) is True
    finally:
        os.close(read_fd)
    assert connect_mod.stdout_exposes_secret(Tty()) is True
    assert connect_mod.stdout_exposes_secret(object()) is True
    with (tmp_path / "out.txt").open("w") as regular:
        assert connect_mod.stdout_exposes_secret(regular) is False


def test_refuse_raises_named_rule() -> None:
    with pytest.raises(connect_mod.ConnectRefusal) as caught:
        connect_mod._refuse("example_rule", "do the other thing")

    assert caught.value.rule == "example_rule"
    assert str(caught.value) == "do the other thing"
    assert isinstance(caught.value, ValueError)


def _env_probe(name: str, expected: str) -> list[str]:
    """A child that exits 0 only when ``name`` holds ``expected``, printing nothing."""
    return [
        sys.executable,
        "-c",
        f"import os, sys; sys.exit(0 if os.environ.get({name!r}) == {expected!r} else 3)",
    ]


def test_connect_exec_puts_secret_in_child_env_only(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    connect_mod.connect_provider("cloudflare", repo=repo, token="cf-test-token")

    result = runner.invoke(
        app,
        [
            "connect",
            "exec",
            "cloudflare",
            "--repo",
            str(repo),
            "--",
            *_env_probe("CLOUDFLARE_API_TOKEN", "cf-test-token"),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "cf-test-token" not in result.output


def test_connect_exec_returns_child_exit_code(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    connect_mod.connect_provider("cloudflare", repo=repo, token="cf-test-token")

    result = runner.invoke(
        app,
        [
            "connect",
            "exec",
            "cloudflare",
            "--repo",
            str(repo),
            "--",
            sys.executable,
            "-c",
            "import sys; sys.exit(7)",
        ],
    )

    assert result.exit_code == 7


def test_connect_exec_env_override_and_custom_default(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    connect_mod.connect_provider("stripe", repo=repo, token="sk_test_fixture")
    connect_mod.connect_provider("mercury", repo=repo, token="mercury-fixture", custom=True)

    stripe_default = runner.invoke(
        app,
        ["connect", "exec", "stripe", "--repo", str(repo), "--"]
        + _env_probe("STRIPE_API_KEY", "sk_test_fixture"),
    )
    stripe_override = runner.invoke(
        app,
        ["connect", "exec", "stripe", "--env", "MY_KEY", "--repo", str(repo), "--"]
        + _env_probe("MY_KEY", "sk_test_fixture"),
    )
    custom_default = runner.invoke(
        app,
        ["connect", "exec", "mercury", "--repo", str(repo), "--"]
        + _env_probe("MB_SECRET", "mercury-fixture"),
    )

    assert stripe_default.exit_code == 0, stripe_default.output
    assert stripe_override.exit_code == 0, stripe_override.output
    assert custom_default.exit_code == 0, custom_default.output


def test_connect_exec_uses_no_shell(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    connect_mod.connect_provider("cloudflare", repo=repo, token="cf-fixture-0000")
    seen: dict[str, Any] = {}

    def fake_run(args, **kwargs):
        seen["args"] = args
        seen["kwargs"] = kwargs
        return subprocess.CompletedProcess(args, 0)

    outcome = connect_mod.exec_with_secret(
        "cloudflare", ["wrangler", "whoami"], repo, runner=fake_run
    )

    assert outcome == {
        "ok": True,
        "provider": "cloudflare",
        "env_name": "CLOUDFLARE_API_TOKEN",
        "returncode": 0,
        "error": "",
        "repair_command": "",
    }
    assert seen["args"] == ["wrangler", "whoami"]
    # Read only names and the checked key: `seen["kwargs"]` holds the whole
    # environment, so a failing assert on it would print every value.
    kwarg_names = sorted(seen["kwargs"])
    token = seen["kwargs"]["env"].get("CLOUDFLARE_API_TOKEN")
    assert "shell" not in kwarg_names
    assert token == "cf-fixture-0000"
    assert "cf-fixture-0000" not in json.dumps(outcome)


def test_connect_exec_signal_exit_maps_to_shell_convention(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    connect_mod.connect_provider("cloudflare", repo=repo, token="cf-test-token")

    outcome = connect_mod.exec_with_secret(
        "cloudflare",
        ["child"],
        repo,
        runner=lambda args, **kwargs: subprocess.CompletedProcess(args, -15),
    )

    assert outcome["returncode"] == 143


@pytest.mark.skipif(sys.platform == "win32", reason="ENOEXEC needs a POSIX exec")
def test_connect_exec_launch_failure_never_prints_secret(tmp_path: Path, monkeypatch) -> None:
    """A real `mb` process launching an executable text file with no shebang.

    exec fails with ENOEXEC. The fake credential must not reach stdout or
    stderr, whatever Typer, Click and Rich versions are installed.
    """
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    fake_secret = "cf-fixture-enoexec-0000"
    connect_mod.connect_provider("cloudflare", repo=repo, token=fake_secret)
    script = tmp_path / "no-shebang"
    script.write_text("echo this file has no interpreter line\n")
    script.chmod(0o755)

    completed = subprocess.run(
        [sys.executable, "-m", "mb", "connect", "exec", "cloudflare", "--repo", str(repo)]
        + ["--", str(script)],
        capture_output=True,
        text=True,
        env=dict(os.environ),
        check=False,
        timeout=120,
    )

    assert completed.returncode == 126, completed.stderr
    assert fake_secret not in completed.stdout
    assert fake_secret not in completed.stderr
    assert "Traceback" not in completed.stderr
    assert "could not be started (ENOEXEC)" in completed.stderr


def test_connect_exec_other_launch_oserror_is_sanitized(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    connect_mod.connect_provider("cloudflare", repo=repo, token="cf-fixture-oserror-0000")

    def fake_run(args, **kwargs):
        raise OSError(7, f"Argument list too long: {kwargs['env']['CLOUDFLARE_API_TOKEN']}")

    outcome = connect_mod.exec_with_secret("cloudflare", ["child"], repo, runner=fake_run)

    assert outcome["returncode"] == 126
    assert outcome["error"] == "command could not be started (E2BIG): child"
    assert "cf-fixture-oserror-0000" not in json.dumps(outcome)


def test_connect_unexpected_error_hides_details(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()

    def explode(*args, **kwargs):
        raise KeyError("cf-fixture-crash-0000")

    monkeypatch.setattr(connect_mod, "exec_with_secret", explode)

    result = runner.invoke(
        app, ["connect", "exec", "cloudflare", "--repo", str(repo), "--", "true"]
    )

    assert result.exit_code == 1
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert "unexpected error (KeyError)" in result.output
    assert "cf-fixture-crash-0000" not in result.output
    assert app.pretty_exceptions_show_locals is False


def test_connect_exec_refusals_and_failures(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()

    not_connected = runner.invoke(
        app, ["connect", "exec", "cloudflare", "--repo", str(repo), "--", "true"]
    )
    assert not_connected.exit_code == 1
    assert "not connected" in not_connected.stderr
    assert "mb connect cloudflare --token-stdin" in not_connected.stderr

    connect_mod.connect_provider("cloudflare", repo=repo, token="cf-test-token")
    no_command = runner.invoke(app, ["connect", "exec", "cloudflare", "--repo", str(repo)])
    assert no_command.exit_code == 2
    assert "needs a command after `--`" in no_command.stderr

    bad_env = runner.invoke(
        app,
        ["connect", "exec", "cloudflare", "--env", "1BAD", "--repo", str(repo), "--", "true"],
    )
    assert bad_env.exit_code == 2
    assert "shell variable name" in bad_env.stderr

    as_json = runner.invoke(
        app, ["connect", "exec", "cloudflare", "--json", "--repo", str(repo), "--", "true"]
    )
    assert as_json.exit_code == 2

    missing = runner.invoke(
        app,
        ["connect", "exec", "cloudflare", "--repo", str(repo), "--", "mb-no-such-command-985"],
    )
    assert missing.exit_code == 127
    assert "command not found" in missing.stderr
    for result in (not_connected, no_command, bad_env, as_json, missing):
        assert "cf-test-token" not in result.output


def test_connect_extra_arguments_outside_exec_are_rejected(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)

    result = runner.invoke(app, ["connect", "test", "cloudflare", "surplus"])

    assert result.exit_code == 2
    assert "unexpected extra argument" in result.stderr


def test_connect_stripe_and_resend_store_and_read_back(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()

    connect_mod.connect_provider(
        "stripe",
        repo=repo,
        token="sk_test_fixture_not_real",
        metadata_pairs=["mode=test", "account_id=acct_fixture"],
    )
    connect_mod.connect_provider(
        "resend",
        repo=repo,
        token="re_fixture_not_real",
        metadata_pairs=["sender_domain=example.com"],
    )

    config_text = (repo / ".mb" / "connect.yaml").read_text(encoding="utf-8")
    assert "sk_test_fixture_not_real" not in config_text
    assert "re_fixture_not_real" not in config_text

    stripe_token = runner.invoke(
        app, ["connect", "token", "stripe", "--print", "--repo", str(repo)]
    )
    assert stripe_token.exit_code == 0
    assert stripe_token.stdout == "sk_test_fixture_not_real"

    resend_token = runner.invoke(
        app, ["connect", "token", "resend", "--print", "--repo", str(repo)]
    )
    assert resend_token.exit_code == 0
    assert resend_token.stdout == "re_fixture_not_real"

    status = connect_mod.status_provider("stripe", repo)
    assert status["metadata"]["mode"] == "test"


def test_connect_stripe_refuses_malformed_key_shape(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()

    result = runner.invoke(
        app,
        ["connect", "stripe", "--repo", str(repo), "--token", "not-a-stripe-key"],
    )

    assert result.exit_code == 2
    assert "expected key shape" in result.stderr
    assert "not-a-stripe-key" not in result.stderr
    secret_file = tmp_path / "home" / "secrets" / "connect.json"
    assert not secret_file.exists() or "not-a-stripe-key" not in secret_file.read_text(
        encoding="utf-8"
    )


def test_connect_stripe_refuses_mode_key_mismatch(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()

    live_mode_test_key = runner.invoke(
        app,
        [
            "connect",
            "stripe",
            "--repo",
            str(repo),
            "--token",
            "sk_test_fixture_not_real",
            "--metadata",
            "mode=live",
        ],
    )
    assert live_mode_test_key.exit_code == 2
    assert "metadata says mode=live) and this is a Stripe TEST key" in live_mode_test_key.stderr
    assert "sk_test_fixture_not_real" not in live_mode_test_key.stderr

    test_mode_live_key = runner.invoke(
        app,
        [
            "connect",
            "stripe",
            "--repo",
            str(repo),
            "--token",
            "sk_live_fixture_not_real",
            "--metadata",
            "mode=test",
        ],
    )
    assert test_mode_live_key.exit_code == 2
    assert "metadata says mode=test) and this is a Stripe LIVE key" in test_mode_live_key.stderr


def test_connect_resend_refuses_malformed_key_shape(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()

    result = runner.invoke(
        app,
        ["connect", "resend", "--repo", str(repo), "--token", "sk_wrong_provider"],
    )

    assert result.exit_code == 2
    assert "expected key shape" in result.stderr
    assert "re_…" in result.stderr


def test_connect_metadata_only_skips_key_shape_check(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()

    result = connect_mod.connect_provider(
        "stripe", repo=repo, metadata_pairs=["account_id=acct_fixture"]
    )

    assert result["ok"] is False or result["status"]["state"] == "missing_secret"


def test_connect_custom_provider_roundtrip(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    secret = "custom-fixture-token"

    result = runner.invoke(
        app,
        [
            "connect",
            "dataforseo",
            "--custom",
            "--repo",
            str(repo),
            "--token",
            secret,
        ],
    )
    assert result.exit_code == 0

    config_text = (repo / ".mb" / "connect.yaml").read_text(encoding="utf-8")
    assert secret not in config_text
    assert "dataforseo" in config_text

    token = runner.invoke(app, ["connect", "token", "dataforseo", "--print", "--repo", str(repo)])
    assert token.exit_code == 0
    assert _sha256(token.stdout.strip()) == _sha256(secret)

    status = connect_mod.status_provider("dataforseo", repo)
    assert status["provider"] == "dataforseo"
    assert status["connected"] is True
    assert status["state"] == "unvalidated"

    tested = connect_mod.test_provider("dataforseo", repo)
    assert tested["ok"] is False
    assert tested["status"]["state"] == connect_mod.UNVERIFIED_STATE

    single_status = runner.invoke(
        app, ["connect", "status", "dataforseo", "--repo", str(repo), "--json"]
    )
    assert single_status.exit_code == 0
    single_status_payload = json.loads(single_status.stdout)
    assert single_status_payload["provider"] == "dataforseo"
    assert single_status_payload["state"] == connect_mod.UNVERIFIED_STATE

    aggregate = connect_mod.status_all(repo, include_all=True)
    aggregate_by_id = {item["provider"]: item for item in aggregate["providers"]}
    assert aggregate_by_id["dataforseo"]["state"] == connect_mod.UNVERIFIED_STATE
    assert aggregate["summary"]["configured"] == 1
    assert aggregate["summary"]["healthy"] == 0
    assert aggregate["summary"]["unverified"] == 1

    doctor = connect_mod.doctor(repo)
    checks = {check["name"]: check for check in doctor["checks"]}
    assert checks["provider:dataforseo"]["state"] == connect_mod.UNVERIFIED_STATE

    listed = connect_mod.list_providers(repo)
    listed_by_id = {provider["id"]: provider for provider in listed["providers"]}
    assert listed_by_id["cloudflare"]["custom"] is False
    assert listed_by_id["dataforseo"]["custom"] is True
    assert listed_by_id["dataforseo"]["category"] == "custom"
    assert listed_by_id["dataforseo"]["state"] == connect_mod.UNVERIFIED_STATE
    assert listed["custom_providers"][0]["id"] == "dataforseo"

    reconnect = runner.invoke(
        app,
        ["connect", "dataforseo", "--repo", str(repo), "--token", "rotated-fixture-token"],
    )
    assert reconnect.exit_code == 0
    rotated = runner.invoke(app, ["connect", "token", "dataforseo", "--print", "--repo", str(repo)])
    assert _sha256(rotated.stdout.strip()) == _sha256("rotated-fixture-token")


def test_connect_custom_provider_missing_secret_surfaces_repair(
    tmp_path: Path, monkeypatch
) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    (repo / ".mb").mkdir()
    (repo / ".mb" / "connect.yaml").write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "repo_id": "repo",
                "providers": {
                    "mercury": {
                        "provider": "mercury",
                        "connected": True,
                        "scope": "repo",
                        "auth": "api_key",
                        "secrets": {
                            "api_key": {
                                "ref": connect_mod._secret_ref("repo", "mercury", "api_key"),
                                "backend": "local-file",
                            }
                        },
                        "metadata": {"role": "operating_cash_source"},
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    status = runner.invoke(app, ["connect", "status", "--all", "--repo", str(repo), "--json"])
    assert status.exit_code == 1
    status_payload = json.loads(status.stdout)
    mercury = next(item for item in status_payload["providers"] if item["provider"] == "mercury")
    assert mercury["state"] == "missing_secret"
    assert mercury["repair_command"] == "mb connect mercury --custom --token-stdin"
    assert mercury["secrets"]["api_key"]["present"] is False
    assert status_payload["summary"]["configured"] == 1
    assert status_payload["summary"]["needs_repair"] == 1

    single_status = runner.invoke(
        app, ["connect", "status", "mercury", "--repo", str(repo), "--json"]
    )
    assert single_status.exit_code == 1
    single_status_payload = json.loads(single_status.stdout)
    assert single_status_payload["provider"] == "mercury"
    assert single_status_payload["state"] == "missing_secret"
    assert single_status_payload["repair_command"] == ("mb connect mercury --custom --token-stdin")

    token = runner.invoke(app, ["connect", "token", "mercury", "--print", "--repo", str(repo)])
    assert token.exit_code == 1
    assert token.stdout == ""
    assert "credential is missing from the secret store" in token.stderr
    assert "repair: mb connect mercury --custom --token-stdin" in token.stderr

    doctor = runner.invoke(app, ["connect", "doctor", "--repo", str(repo), "--json"])
    assert doctor.exit_code == 1
    doctor_payload = json.loads(doctor.stdout)
    checks = {check["name"]: check for check in doctor_payload["checks"]}
    assert checks["provider:mercury"]["state"] == "missing_secret"
    assert checks["provider:mercury"]["repair_command"] == (
        "mb connect mercury --custom --token-stdin"
    )

    listed = runner.invoke(app, ["connect", "list", "--repo", str(repo), "--json"])
    assert listed.exit_code == 0
    listed_payload = json.loads(listed.stdout)
    listed_mercury = next(
        provider for provider in listed_payload["providers"] if provider["id"] == "mercury"
    )
    assert listed_mercury["state"] == "missing_secret"
    assert listed_mercury["custom"] is True


def test_connect_user_scope_custom_provider_hydrates_and_reads(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    canonical = tmp_path / "canonical"
    disposable = tmp_path / "workspace"
    canonical.mkdir()
    disposable.mkdir()
    secret = "mercury-fixture-token"

    def fake_git(repo: Path, args: list[str]) -> str:
        if args == ["config", "--get", "remote.origin.url"]:
            return "git@github.com:acme/business.git"
        return ""

    monkeypatch.setattr(connect_mod, "_git_output", fake_git)

    connected = connect_mod.connect_provider(
        "mercury",
        repo=canonical,
        token=secret,
        account_label="Mercury Fixture",
        metadata_pairs=["role=operating_cash_source"],
        scope="user",
        custom=True,
    )
    assert connected["scope"] == "user"
    assert Path(connected["user_scope_path"]).exists()
    assert secret not in Path(connected["user_scope_path"]).read_text(encoding="utf-8")

    before = connect_mod.status_all(disposable)
    assert before["summary"]["configured"] == 1
    assert before["providers"][0]["provider"] == "mercury"
    assert before["providers"][0]["state"] == "needs_hydration"
    assert before["providers"][0]["repair_command"] == "mb connect hydrate --repo ."

    token = runner.invoke(
        app, ["connect", "token", "mercury", "--print", "--repo", str(disposable)]
    )
    assert token.exit_code == 0
    assert _sha256(token.stdout.strip()) == _sha256(secret)

    hydrated = connect_mod.hydrate(disposable, provider_id="mercury")
    assert hydrated["ok"] is True
    assert hydrated["hydrated"] == ["mercury"]
    assert secret not in (disposable / ".mb" / "connect.yaml").read_text(encoding="utf-8")

    tested = connect_mod.test_provider("mercury", disposable)
    assert tested["ok"] is False
    assert tested["status"]["state"] == connect_mod.UNVERIFIED_STATE
    assert tested["stored"] is True
    assert tested["provider_verified"] is False


def test_connect_unknown_provider_hints_custom(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()

    result = runner.invoke(app, ["connect", "dataforseo", "--repo", str(repo), "--token", "x"])

    assert result.exit_code == 2
    assert "rerun with --custom" in result.stderr


def test_connect_custom_rejects_bad_slug(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()

    result = runner.invoke(
        app,
        ["connect", "Bad_Slug!", "--custom", "--repo", str(repo), "--token", "x"],
    )

    assert result.exit_code == 2
    assert "lowercase letters, digits, and hyphens" in result.stderr


def test_rotation_never_rewrites_same_provider_in_another_repo(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo_a = tmp_path / "biz-a"
    repo_b = tmp_path / "biz-b"
    repo_a.mkdir()
    repo_b.mkdir()

    connect_mod.connect_provider("cloudflare", repo=repo_a, token="cf-old-token", scope="user")
    connect_mod.connect_provider("cloudflare", repo=repo_b, token="cf-old-token", scope="user")

    result = connect_mod.connect_provider(
        "cloudflare", repo=repo_a, token="cf-new-token", scope="user"
    )

    assert result["rotated_sibling_refs"] == []
    assert result["stale_sibling_refs"] == []
    token_b = runner.invoke(
        app, ["connect", "token", "cloudflare", "--print", "--repo", str(repo_b)]
    )
    assert token_b.exit_code == 0
    assert token_b.stdout == "cf-old-token"


def test_rotation_does_not_touch_other_providers(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo_a = tmp_path / "biz-a"
    repo_b = tmp_path / "biz-b"
    repo_a.mkdir()
    repo_b.mkdir()

    connect_mod.connect_provider("cloudflare", repo=repo_a, token="cf-token", scope="user")
    connect_mod.connect_provider("apify", repo=repo_b, token="apify-token", scope="user")

    result = connect_mod.connect_provider(
        "cloudflare", repo=repo_a, token="cf-rotated", scope="user"
    )

    assert result["rotated_sibling_refs"] == []
    token_b = runner.invoke(app, ["connect", "token", "apify", "--print", "--repo", str(repo_b)])
    assert token_b.stdout == "apify-token"


# --- credential hygiene (mb connect hygiene) -------------------------------

# A sentinel that must NEVER appear in any hygiene output (value redaction).
_SECRET_SENTINEL = "fal-SUPERSECRETVALUE0123456789abcdef"


def _write_claude_config(home: Path) -> Path:
    home.mkdir(parents=True, exist_ok=True)
    config = {
        "mcpServers": {
            "google-ads-mcp": {
                "env": {
                    # plaintext, secret-named key -> flagged
                    "GOOGLE_ADS_DEVELOPER_TOKEN": "abc123DEVTOKENplaintext",
                    # correctly externalized -> NOT flagged
                    "GOOGLE_ADS_CLIENT_ID": "${GOOGLE_ADS_CLIENT_ID}",
                },
            },
            "fal-ai": {
                # plaintext by value-prefix, even though key isn't "secret" named
                "env": {"FAL_KEY": _SECRET_SENTINEL},
            },
            "safe-server": {
                "command": "node",
                "args": ["server.js"],
                "env": {"PORT": "8080", "API_KEY": "${MY_API_KEY}"},
            },
        }
    }
    path = home / ".claude.json"
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    return path


def test_hygiene_flags_plaintext_and_spares_env_refs(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _write_claude_config(home)
    repo = tmp_path / "biz"
    repo.mkdir()

    result = connect_mod.scan_credential_hygiene(repo, home=home)

    assert result["ok"] is False
    locations = {f["location"] for f in result["findings"]}
    assert "mcpServers.google-ads-mcp.env.GOOGLE_ADS_DEVELOPER_TOKEN" in locations
    assert "mcpServers.fal-ai.env.FAL_KEY" in locations
    # env-referenced and placeholder-shaped values are correctly externalized
    assert all("CLIENT_ID" not in loc for loc in locations)
    assert all(not loc.endswith("API_KEY") for loc in locations)
    assert all(not loc.endswith(".PORT") for loc in locations)


def test_hygiene_never_emits_the_secret_value(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _write_claude_config(home)
    repo = tmp_path / "biz"
    repo.mkdir()

    result = connect_mod.scan_credential_hygiene(repo, home=home)
    blob = json.dumps(result)
    assert _SECRET_SENTINEL not in blob
    assert "abc123DEVTOKENplaintext" not in blob
    # mask reports length only
    fal = next(f for f in result["findings"] if f["location"].endswith("FAL_KEY"))
    assert fal["mask"] == f"••• ({len(_SECRET_SENTINEL)} chars)"
    assert "remediation" in fal


def test_hygiene_clean_when_all_externalized(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir(parents=True)
    (home / ".claude.json").write_text(
        json.dumps({"mcpServers": {"x": {"env": {"TOKEN": "${X_TOKEN}"}}}}),
        encoding="utf-8",
    )
    repo = tmp_path / "biz"
    repo.mkdir()

    result = connect_mod.scan_credential_hygiene(repo, home=home)
    assert result["ok"] is True
    assert result["findings"] == []
    assert "~/.claude.json" in result["surfaces_scanned"]


def test_hygiene_ignores_iso_date_housekeeping_fields(tmp_path: Path) -> None:
    # A secret-named key holding an ISO date (e.g. claudeCodeFirstTokenDate)
    # is not a credential — it must not inflate the count.
    home = tmp_path / "home"
    home.mkdir(parents=True)
    (home / ".claude.json").write_text(
        json.dumps(
            {
                "claudeCodeFirstTokenDate": "2026-01-15T12:34:56.789Z",
                "lastTokenRefreshDate": "2026-06-14",
                "mcpServers": {"real": {"env": {"API_KEY": "sk-live-abc123def456"}}},
            }
        ),
        encoding="utf-8",
    )
    repo = tmp_path / "biz"
    repo.mkdir()

    result = connect_mod.scan_credential_hygiene(repo, home=home)
    locations = {f["location"] for f in result["findings"]}
    # The real secret is still caught; the two date fields are not.
    assert "mcpServers.real.env.API_KEY" in locations
    assert not any("Date" in loc for loc in locations)
    assert len(result["findings"]) == 1


def test_hygiene_cli_exit_code_and_redaction(tmp_path: Path) -> None:
    home = tmp_path / "home"
    _write_claude_config(home)
    repo = tmp_path / "biz"
    repo.mkdir()
    # point _home() at our fake home via the documented env override
    import os

    env = {**os.environ, "HOME": str(home)}
    result = runner.invoke(app, ["connect", "hygiene", "--repo", str(repo), "--json"], env=env)
    assert result.exit_code == 1
    assert _SECRET_SENTINEL not in result.stdout


def test_hygiene_scans_repo_mcp_surface(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir(parents=True)
    repo = tmp_path / "biz"
    repo.mkdir()
    (repo / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"y": {"env": {"SECRET": "re_live_plaintextkey123"}}}}),
        encoding="utf-8",
    )
    result = connect_mod.scan_credential_hygiene(repo, home=home)
    assert result["ok"] is False
    assert any(f["surface"] == ".mcp.json" for f in result["findings"])


def test_hygiene_unparseable_surface_is_not_a_clean_verdict(tmp_path: Path) -> None:
    # A surface that could not be scanned must NOT return a clean machine
    # verdict — gates/automation read ok + the exit code (#911 Codex review).
    home = tmp_path / "home"
    home.mkdir(parents=True)
    (home / ".claude.json").write_text("{ not valid json", encoding="utf-8")
    repo = tmp_path / "biz"
    repo.mkdir()
    result = connect_mod.scan_credential_hygiene(repo, home=home)
    assert result["ok"] is False
    assert any(s["reason"] == "not valid JSON" for s in result["surfaces_skipped"])

    import os as _os

    cli = runner.invoke(
        app,
        ["connect", "hygiene", "--repo", str(repo), "--json"],
        env={**_os.environ, "HOME": str(home)},
    )
    assert cli.exit_code == 1


# --- canonical business identity (mb connect identity) ---------------------


def test_identity_aggregates_recorded_metadata(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    connect_mod.connect_provider(
        "meta",
        repo=repo,
        token="meta-secret-token",
        metadata_pairs=["ad_account_id=act_test", "page_id=12345", "business_id=biz_1"],
    )

    result = connect_mod.business_identity(repo)

    assert result["ok"] is True
    assert result["safe_to_share"] is False  # carries business identifiers
    meta = next(p for p in result["providers"] if p["provider"] == "meta")
    assert meta["identity"]["ad_account_id"] == "act_test"
    assert meta["identity"]["page_id"] == "12345"
    # pixel_id is a registry identity field that was not recorded
    assert meta["identity"]["pixel_id"] == ""
    assert "pixel_id" in meta["missing_fields"]
    assert meta["complete"] is False


def test_identity_marks_complete_when_all_fields_recorded(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    connect_mod.connect_provider(
        "resend",
        repo=repo,
        token="re_live_key_abc",
        metadata_pairs=["sender_domain=mail.example.com", "audience_id=aud_1"],
    )

    result = connect_mod.business_identity(repo)
    resend = next(p for p in result["providers"] if p["provider"] == "resend")
    assert resend["complete"] is True
    assert resend["missing_fields"] == []


def test_identity_empty_when_no_providers(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    result = connect_mod.business_identity(repo)
    assert result["providers"] == []
    assert "no connected providers" in result["summary"]


def test_identity_never_emits_secret_material(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    connect_mod.connect_provider(
        "resend",
        repo=repo,
        token="re_live_SECRETTOKEN999",
        metadata_pairs=["sender_domain=mail.example.com"],
    )
    result = connect_mod.business_identity(repo)
    assert "re_live_SECRETTOKEN999" not in json.dumps(result)


def test_identity_cli_json(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    connect_mod.connect_provider(
        "meta",
        repo=repo,
        token="meta-secret-token",
        metadata_pairs=["ad_account_id=act_test"],
    )
    result = runner.invoke(app, ["connect", "identity", "--repo", str(repo), "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["safe_to_share"] is False
    assert any(p["provider"] == "meta" for p in payload["providers"])


def test_identity_includes_custom_provider_safe_metadata(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    connect_mod.connect_provider(
        "mercury",
        repo=repo,
        token="mercury-fixture-token",
        account_label="Mercury Fixture",
        metadata_pairs=[
            "role=operating_cash_source",
            "access_level=read_only",
            "data_domain=banking",
            "auth_state=api_token",
        ],
        custom=True,
    )

    result = connect_mod.business_identity(repo)

    mercury = next(p for p in result["providers"] if p["provider"] == "mercury")
    assert mercury["custom"] is True
    assert mercury["identity_schema"] == "custom_metadata"
    assert mercury["identity"] == {
        "role": "operating_cash_source",
        "access_level": "read_only",
        "data_domain": "banking",
        "auth_state": "api_token",
    }
    assert mercury["missing_fields"] == []
    assert mercury["complete"] is True
    assert "mercury-fixture-token" not in json.dumps(result)


def test_identity_suppresses_secret_like_custom_metadata(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    connect_mod.connect_provider(
        "mercury",
        repo=repo,
        token="mercury-fixture-token",
        metadata_pairs=["role=operating_cash_source"],
        custom=True,
    )
    config_path = repo / ".mb" / "connect.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["providers"]["mercury"]["metadata"]["api_key"] = "badly-committed-secret"
    config["providers"]["mercury"]["metadata"]["account_ref"] = "operating-cash"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

    result = connect_mod.business_identity(repo)

    mercury = next(p for p in result["providers"] if p["provider"] == "mercury")
    assert mercury["identity"] == {
        "role": "operating_cash_source",
        "account_ref": "operating-cash",
    }
    assert "badly-committed-secret" not in json.dumps(result)
    assert "api_key" not in mercury["identity"]


def test_hygiene_flags_literal_secret_mixed_with_env_ref(tmp_path: Path) -> None:
    # "${ENV}sk-realsecret" must NOT pass as externalized (false-negative fix).
    home = tmp_path / "home"
    home.mkdir(parents=True)
    (home / ".claude.json").write_text(
        json.dumps({"mcpServers": {"m": {"env": {"API_KEY": "${BASE}sk-live-realsecret999"}}}}),
        encoding="utf-8",
    )
    repo = tmp_path / "biz"
    repo.mkdir()
    result = connect_mod.scan_credential_hygiene(repo, home=home)
    assert result["ok"] is False
    assert any(f["location"].endswith("API_KEY") for f in result["findings"])


def test_hygiene_surfaces_unscannable_files_loudly(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir(parents=True)
    (home / ".claude.json").write_text("{ not valid json", encoding="utf-8")
    repo = tmp_path / "biz"
    repo.mkdir()
    result = connect_mod.scan_credential_hygiene(repo, home=home)
    # Skipped surface must be called out, not silently treated as clean.
    assert "could not be scanned" in result["summary"]
    assert result["surfaces_skipped"]


# --- stored vs verified (issue 962) ----------------------------------------
#
# `stored`, `provider_verified`, and `verified_at` are three separate facts.
# Every simulated provider response below is a local stub; no test in this
# block makes a real network call or reads a real credential.


def _simulated_passing_probe(monkeypatch) -> list[str]:
    """Stub a successful provider probe. Simulated: never calls the network."""
    calls: list[str] = []

    def fake_http(url: str, headers=None, **kwargs) -> dict[str, Any]:
        calls.append(url)
        return {
            "ok": True,
            "state": "ready",
            "summary": "Cloudflare credential validated with provider (simulated).",
            "safe_to_share": True,
            "upstream": {
                "endpoint_family": kwargs["endpoint_family"],
                "http_status": 200,
                "response_received": True,
                "error_codes": [],
                "error_messages": [],
                "safe_to_share": True,
            },
        }

    monkeypatch.setattr(connect_mod, "_http_get_json", fake_http)
    return calls


def _simulated_failing_probe(monkeypatch) -> None:
    """Stub a rejected provider probe. Simulated: never calls the network."""

    def fake_http(url: str, headers=None, **kwargs) -> dict[str, Any]:
        return {
            "ok": False,
            "state": "invalid",
            "summary": "Cloudflare rejected the credential (simulated).",
            "repair": "Replace the credential.",
            "repair_command": "mb connect cloudflare --token-stdin",
            "safe_to_share": True,
            "upstream": {
                "endpoint_family": kwargs["endpoint_family"],
                "http_status": 401,
                "response_received": True,
                "error_codes": [1000],
                "error_messages": [],
                "safe_to_share": True,
            },
        }

    monkeypatch.setattr(connect_mod, "_http_get_json", fake_http)


def test_connect_test_probe_provider_reaches_ready_and_records_verified_at(
    tmp_path: Path, monkeypatch
) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    runner.invoke(app, ["connect", "cloudflare", "--repo", str(repo), "--token", "cf-test-token"])
    calls = _simulated_passing_probe(monkeypatch)

    tested = connect_mod.test_provider("cloudflare", repo)

    assert calls, "the probe provider must actually call the provider"
    assert tested["ok"] is True
    assert tested["stored"] is True
    assert tested["provider_verified"] is True
    assert tested["verified_at"] == tested["validation"]["checked_at"]
    assert tested["status"]["state"] == "ready"
    assert tested["status"]["provider_verified"] is True
    assert tested["status"]["verified_at"] == tested["verified_at"]

    status = connect_mod.status_all(repo)
    assert status["ok"] is True
    assert status["summary"]["healthy"] == 1
    assert status["summary"]["unverified"] == 0


def test_connect_test_failed_probe_keeps_the_earlier_verified_at(
    tmp_path: Path, monkeypatch
) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    runner.invoke(app, ["connect", "cloudflare", "--repo", str(repo), "--token", "cf-test-token"])
    _simulated_passing_probe(monkeypatch)
    first = connect_mod.test_provider("cloudflare", repo)
    assert first["provider_verified"] is True

    _simulated_failing_probe(monkeypatch)
    second = connect_mod.test_provider("cloudflare", repo)

    # `verified_at` records when the credential last worked, which stays true
    # after a later rejection; `provider_verified` is about right now.
    assert second["ok"] is False
    assert second["provider_verified"] is False
    assert second["verified_at"] == first["verified_at"]
    assert second["status"]["state"] == "invalid"


def test_connect_status_json_exposes_stored_verified_and_verified_at(
    tmp_path: Path, monkeypatch
) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    runner.invoke(app, ["connect", "resend", "--repo", str(repo), "--token", "re_fixture_key"])
    runner.invoke(app, ["connect", "test", "resend", "--repo", str(repo)])

    status = runner.invoke(app, ["connect", "status", "--repo", str(repo), "--json"])

    assert status.exit_code == 0
    provider = json.loads(status.stdout)["providers"][0]
    assert provider["stored"] is True
    assert provider["provider_verified"] is False
    assert provider["verified_at"] == ""
    assert provider["ok"] is False
    assert provider["state"] == connect_mod.UNVERIFIED_STATE
    assert "re_fixture_key" not in status.stdout


def test_connect_status_not_connected_provider_reports_nothing_stored(
    tmp_path: Path, monkeypatch
) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()

    status = connect_mod.status_provider("resend", repo)

    assert status["state"] == "not_connected"
    assert status["stored"] is False
    assert status["provider_verified"] is False
    assert status["verified_at"] == ""


def test_connect_doctor_grades_stored_unverified_as_warning_not_pass(
    tmp_path: Path, monkeypatch
) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    runner.invoke(app, ["connect", "resend", "--repo", str(repo), "--token", "re_fixture_key"])
    runner.invoke(app, ["connect", "test", "resend", "--repo", str(repo)])

    doctor = connect_mod.doctor(repo)
    checks = {check["name"]: check for check in doctor["checks"]}
    assert checks["provider:resend"]["ok"] is False
    assert checks["provider:resend"]["state"] == connect_mod.UNVERIFIED_STATE

    # `mb status` consumes this check; it must not read as a pass either.
    check = connect_mod.doctor_check(repo)
    assert check["ok"] is False
    assert check["severity"] == "warn"
    assert "cannot verify" in check["detail"]
    assert "resend" in check["detail"]

    rendered = runner.invoke(app, ["connect", "doctor", "--repo", str(repo)])
    # The grade stays `warn`; only the process exit softens, and here the exit
    # is 1 only because this fixture is not a git repo (github-context).
    assert "provider:resend: stored, unverified" in rendered.stdout
    assert "ready" not in rendered.stdout.split("provider:resend")[1]


def test_connect_status_all_counts_unverified_apart_from_needs_repair(
    tmp_path: Path, monkeypatch
) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    runner.invoke(app, ["connect", "resend", "--repo", str(repo), "--token", "re_fixture_key"])
    runner.invoke(app, ["connect", "test", "resend", "--repo", str(repo)])
    runner.invoke(app, ["connect", "postiz", "--repo", str(repo), "--token", "postiz-token"])

    status = connect_mod.status_all(repo)
    summary = status["summary"]

    # An unverified credential is not "broken": nothing is known to be wrong
    # with it, and no repair command would change that. `unvalidated` keeps its
    # old meaning ("`mb connect test` has not been run") and still counts as
    # something to repair, because running the test does change it.
    assert summary["configured"] == 2
    assert summary["healthy"] == 0
    assert summary["unverified"] == 1
    assert summary["unvalidated"] == 1
    assert summary["needs_repair"] == 1
    assert [item["provider"] for item in status["providers"] if not item["ok"]] == [
        "resend",
        "postiz",
    ]
    assert status["ok"] is False


def test_connect_custom_provider_reports_stored_unverified(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    runner.invoke(
        app,
        ["connect", "mercury", "--custom", "--repo", str(repo), "--token", "custom-fixture-token"],
    )

    tested = connect_mod.test_provider("mercury", repo)

    # Custom providers ride the same no-probe branch as built-ins.
    assert tested["ok"] is False
    assert tested["stored"] is True
    assert tested["provider_verified"] is False
    assert tested["verified_at"] == ""
    assert tested["status"]["state"] == connect_mod.UNVERIFIED_STATE
    assert tested["status"]["repair_command"] == ""
    assert "custom-fixture-token" not in json.dumps(tested)

    doctor = connect_mod.doctor(repo)
    checks = {check["name"]: check for check in doctor["checks"]}
    assert checks["provider:mercury"]["ok"] is False


def test_connect_metadata_only_provider_stays_ready_without_provider_verified(
    tmp_path: Path, monkeypatch
) -> None:
    """Pin the shape of a provider with no `required_secrets`.

    The readiness invariant is scoped: for a provider WITH required secrets,
    `ready` requires `provider_verified`. hledger has none, sends nothing to a
    provider, and therefore has no credential to confirm. It keeps reporting
    `ready` from repo-local metadata with `stored` and `provider_verified`
    false, rather than faking a provider call it never made.
    """
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    assert connect_mod.provider_map()["hledger"].required_secrets == ()
    connect_mod.connect_provider(
        "hledger",
        repo=repo,
        metadata_pairs=["journal_path=.mb/private/books/main.journal"],
    )

    tested = connect_mod.test_provider("hledger", repo)

    assert tested["ok"] is True
    assert tested["status"]["state"] == "ready"
    assert tested["stored"] is False
    assert tested["provider_verified"] is False
    assert tested["verified_at"] == ""

    # The same shape on the status surface, not just the test result.
    status = connect_mod.status_provider("hledger", repo)
    assert status["state"] == "ready"
    assert status["ok"] is True
    assert status["stored"] is False
    assert status["provider_verified"] is False
    assert status["verified_at"] == ""
    assert status["repair_command"] == ""

    # It counts as healthy, not as unverified, and doctor passes it.
    aggregate = connect_mod.status_all(repo)
    assert aggregate["ok"] is True
    assert aggregate["summary"]["healthy"] == 1
    assert aggregate["summary"]["unverified"] == 0
    assert connect_mod.doctor_check(repo)["ok"] is True

    checks = {check["name"]: check for check in connect_mod.doctor(repo)["checks"]}
    assert checks["provider:hledger"]["ok"] is True
    assert checks["provider:hledger"]["state"] == "ready"


def _legacy_ready_entry(repo: Path, provider_id: str) -> None:
    """Write a 0.5.2-shaped entry: `validation.state: ready`, no verified facts."""
    config = yaml.safe_load((repo / ".mb" / "connect.yaml").read_text(encoding="utf-8"))
    config["providers"][provider_id]["validation"] = {
        "state": "ready",
        "checked_at": "2026-09-01T00:00:00+00:00",
        "summary": "legacy 0.5.2 validation entry",
        "safe_to_share": True,
    }
    config["providers"][provider_id]["last_checked_at"] = "2026-09-01T00:00:00+00:00"
    (repo / ".mb" / "connect.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")


def test_connect_status_reads_legacy_ready_metadata_as_unverified(
    tmp_path: Path, monkeypatch
) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    runner.invoke(app, ["connect", "cloudflare", "--repo", str(repo), "--token", "cf-test-token"])
    _legacy_ready_entry(repo, "cloudflare")

    status = connect_mod.status_provider("cloudflare", repo)

    # 0.5.2 wrote `ready` for probed and unprobed providers alike, so the word
    # alone is not evidence of a provider call. Absent `provider_verified`
    # fails closed: the entry keeps working, it just stops claiming verified.
    assert status["state"] == connect_mod.UNVERIFIED_STATE
    assert status["ok"] is False
    assert status["stored"] is True
    assert status["provider_verified"] is False
    assert status["verified_at"] == ""
    # Cloudflare has a probe, so the legacy entry is actionable: run the test.
    assert status["repair_command"] == "mb connect test cloudflare"
    assert connect_mod.provider_needs_action(status) is True


def test_connect_test_reverifies_legacy_ready_metadata(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    runner.invoke(app, ["connect", "cloudflare", "--repo", str(repo), "--token", "cf-test-token"])
    _legacy_ready_entry(repo, "cloudflare")
    _simulated_passing_probe(monkeypatch)

    tested = connect_mod.test_provider("cloudflare", repo)

    # One re-test is the whole upgrade cost for a provider that has a probe.
    assert tested["ok"] is True
    assert tested["provider_verified"] is True
    assert tested["verified_at"] == tested["validation"]["checked_at"]
    assert tested["status"]["state"] == "ready"


def test_connect_meta_legacy_ready_metadata_reads_as_unverified(
    tmp_path: Path, monkeypatch
) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    _connect_meta_ready_prereqs(monkeypatch)
    repo = tmp_path / "biz"
    repo.mkdir()
    runner.invoke(
        app,
        [
            "connect",
            "meta",
            "--repo",
            str(repo),
            "--token",
            "meta-fixture-token",
            "--metadata",
            "ad_account_id=act_123",
        ],
    )
    _legacy_ready_entry(repo, "meta")

    status = connect_mod.status_provider("meta", repo)

    assert status["state"] == connect_mod.UNVERIFIED_STATE
    assert status["ok"] is False
    assert status["provider_verified"] is False


# --- exit-code contract -----------------------------------------------------
#
# An exit code means "there is something you can act on". A red nobody can
# clear gets ignored, and a probe-less provider can never turn green until a
# probe exists upstream.


def _simulate_ready_github(monkeypatch) -> None:
    """Stub GitHub context so doctor exit codes isolate the provider rule."""
    monkeypatch.setattr(
        connect_mod,
        "github_context",
        lambda repo, **kwargs: {
            "ok": True,
            "state": "ready",
            "summary": "simulated GitHub context",
            "repair": "",
            "repair_command": "",
            "safe_to_share": True,
        },
    )


def test_probe_provider_set_matches_validate_with_provider(tmp_path: Path, monkeypatch) -> None:
    """`PROBE_PROVIDERS` must match what `_validate_with_provider` really probes.

    The exit-code contract turns on this set. Drift either hides a provider
    behind a permanent exit 0 or raises a red nobody can clear.
    """
    monkeypatch.setattr(
        connect_mod,
        "_http_get_json",
        lambda url, headers=None, **kwargs: {
            "ok": True,
            "state": "ready",
            "summary": "simulated provider response",
            "safe_to_share": True,
            "upstream": {
                "endpoint_family": kwargs["endpoint_family"],
                "safe_to_share": True,
            },
        },
    )
    monkeypatch.setattr(connect_mod, "_meta_prerequisite_state", lambda **kwargs: "")

    def fake_run(args, cwd=None, timeout=5.0, *, env=None):
        return {"ok": True, "returncode": 0, "stdout": "{}\n", "stderr": ""}

    for provider in connect_mod.PROVIDERS:
        if not provider.required_secrets:
            continue
        result = connect_mod._validate_with_provider(
            provider,
            "simulated-token",
            {"ad_account_id": "act_test", "account_id": "0" * 32},
            repo=tmp_path,
            which_func=_fake_meta_which,
            command_runner=fake_run,
        )
        probed = result["state"] != connect_mod.UNVERIFIED_STATE
        assert probed is connect_mod.has_provider_probe(provider.id), provider.id

    # Every id in the set is a real registered provider.
    assert connect_mod.PROBE_PROVIDERS.issubset({p.id for p in connect_mod.PROVIDERS})

    # Custom providers are never in the set.
    assert connect_mod.has_provider_probe("mercury") is False

    # The conditional set: `google` is probed only when its entry records an
    # OAuth grant (`mb/google_probe.py` runs then, not `_validate_with_provider`,
    # which the loop above shows stays probe-less for it).
    assert frozenset({"google"}) == connect_mod.CONDITIONAL_PROBE_PROVIDERS
    assert not connect_mod.CONDITIONAL_PROBE_PROVIDERS & connect_mod.PROBE_PROVIDERS
    assert connect_mod.CONDITIONAL_PROBE_PROVIDERS.issubset({p.id for p in connect_mod.PROVIDERS})
    legacy = {"secrets": {"access_token": {"ref": "ref-1", "backend": "local-file"}}}
    oauth = {
        "secrets": {
            "access_token": {"ref": "ref-1", "backend": "local-file"},
            "oauth_grant": {"ref": "ref-2", "backend": "local-file"},
        }
    }
    unrecorded = {"secrets": {**legacy["secrets"], "oauth_grant": {"ref": ""}}}
    for provider_id in connect_mod.CONDITIONAL_PROBE_PROVIDERS:
        assert connect_mod.has_provider_probe(provider_id) is False
        assert connect_mod.has_provider_probe(provider_id, legacy) is False
        assert connect_mod.has_provider_probe(provider_id, unrecorded) is False
        assert connect_mod.has_provider_probe(provider_id, oauth) is True
    for provider_id in connect_mod.PROBE_PROVIDERS:
        assert connect_mod.has_provider_probe(provider_id, legacy) is True
    # Recording the slot gives a probe only to the provider that has one.
    assert connect_mod.has_provider_probe("resend", oauth) is False
    assert connect_mod.has_provider_probe("mercury", oauth) is False


def test_provider_needs_action_splits_on_whether_a_probe_exists() -> None:
    unverified = {"ok": False, "state": connect_mod.UNVERIFIED_STATE}

    # Actionable: a probe exists, so `mb connect test` is a real next step.
    assert connect_mod.provider_needs_action({**unverified, "provider": "cloudflare"}) is True
    assert connect_mod.provider_needs_action({**unverified, "provider": "apify"}) is True
    assert connect_mod.provider_needs_action({**unverified, "provider": "meta"}) is True

    # Not actionable: nothing the operator runs can verify these.
    assert connect_mod.provider_needs_action({**unverified, "provider": "resend"}) is False
    assert connect_mod.provider_needs_action({**unverified, "provider": "mercury"}) is False

    # Every other unhealthy state stays actionable.
    for state in ("unvalidated", "invalid", "missing_secret", connect_mod.BACKEND_FAILURE_STATE):
        assert (
            connect_mod.provider_needs_action({"ok": False, "state": state, "provider": "resend"})
            is True
        ), state

    assert connect_mod.provider_needs_action({"ok": True, "state": "ready"}) is False

    # A status item's own `has_probe` wins: that is how a conditional probe
    # (an OAuth-mode `google`) reaches the exit code.
    google = {**unverified, "provider": "google"}
    assert connect_mod.provider_needs_action(google) is False
    assert connect_mod.provider_needs_action({**google, "has_probe": False}) is False
    assert connect_mod.provider_needs_action({**google, "has_probe": True}) is True


def test_connect_probeless_unverified_exits_zero_on_all_three_surfaces(
    tmp_path: Path, monkeypatch
) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    _simulate_ready_github(monkeypatch)
    repo = tmp_path / "biz"
    repo.mkdir()
    runner.invoke(app, ["connect", "resend", "--repo", str(repo), "--token", "re_fixture_key"])

    tested = runner.invoke(app, ["connect", "test", "resend", "--repo", str(repo)])
    aggregate = runner.invoke(app, ["connect", "status", "--repo", str(repo)])
    every = runner.invoke(app, ["connect", "status", "--all", "--repo", str(repo)])
    single = runner.invoke(app, ["connect", "status", "resend", "--repo", str(repo)])
    doctor = runner.invoke(app, ["connect", "doctor", "--repo", str(repo)])

    assert tested.exit_code == 0
    assert aggregate.exit_code == 0
    assert every.exit_code == 0
    assert single.exit_code == 0
    assert doctor.exit_code == 0

    # The exit softens; the grade and the facts do not.
    payload = json.loads(
        runner.invoke(app, ["connect", "status", "--repo", str(repo), "--json"]).stdout
    )
    provider = payload["providers"][0]
    assert provider["ok"] is False
    assert provider["state"] == connect_mod.UNVERIFIED_STATE
    assert provider["has_probe"] is False
    assert provider["provider_verified"] is False
    assert payload["ok"] is False
    assert payload["summary"]["actionable"] == 0
    assert "stored, unverified" in doctor.stdout


def test_connect_probe_capable_unverified_exits_one_on_all_three_surfaces(
    tmp_path: Path, monkeypatch
) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    _simulate_ready_github(monkeypatch)
    repo = tmp_path / "biz"
    repo.mkdir()
    runner.invoke(app, ["connect", "cloudflare", "--repo", str(repo), "--token", "cf-test-token"])
    _legacy_ready_entry(repo, "cloudflare")

    aggregate = runner.invoke(app, ["connect", "status", "--repo", str(repo)])
    single = runner.invoke(app, ["connect", "status", "cloudflare", "--repo", str(repo)])
    doctor = runner.invoke(app, ["connect", "doctor", "--repo", str(repo)])

    assert aggregate.exit_code == 1
    assert single.exit_code == 1
    assert doctor.exit_code == 1

    payload = json.loads(
        runner.invoke(app, ["connect", "status", "--repo", str(repo), "--json"]).stdout
    )
    assert payload["providers"][0]["has_probe"] is True
    assert payload["summary"]["actionable"] == 1
    # Exit 1 always names something to run; the probe-less case never does.
    assert payload["providers"][0]["repair_command"] == "mb connect test cloudflare"

    # Running the probe is the action, and it resolves the exit either way.
    _simulated_failing_probe(monkeypatch)
    rejected = runner.invoke(app, ["connect", "test", "cloudflare", "--repo", str(repo)])
    assert rejected.exit_code == 1

    _simulated_passing_probe(monkeypatch)
    accepted = runner.invoke(app, ["connect", "test", "cloudflare", "--repo", str(repo)])
    assert accepted.exit_code == 0
    assert runner.invoke(app, ["connect", "doctor", "--repo", str(repo)]).exit_code == 0


def test_connect_doctor_hint_names_providers_without_a_probe(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    _simulate_ready_github(monkeypatch)
    repo = tmp_path / "biz"
    repo.mkdir()
    runner.invoke(app, ["connect", "resend", "--repo", str(repo), "--token", "re_fixture_key"])
    runner.invoke(app, ["connect", "postiz", "--repo", str(repo), "--token", "postiz-token"])
    runner.invoke(app, ["connect", "cloudflare", "--repo", str(repo), "--token", "cf-test-token"])
    connect_mod.connect_provider(
        "hledger", repo=repo, metadata_pairs=["journal_path=.mb/private/books/main.journal"]
    )

    report = connect_mod.doctor(repo)

    # Named so the gap is fixable upstream instead of silently permanent.
    assert report["probe_gap"]["providers"] == ["postiz", "resend"]
    assert "no automated probe" in report["probe_gap"]["summary"]
    # cloudflare has a probe; hledger stores no credential to probe.
    assert "cloudflare" not in report["probe_gap"]["providers"]
    assert "hledger" not in report["probe_gap"]["providers"]

    rendered = runner.invoke(app, ["connect", "doctor", "--repo", str(repo)])
    assert "no provider probe: postiz, resend" in rendered.stdout


def test_connect_status_all_exits_zero_when_nothing_is_connected(
    tmp_path: Path, monkeypatch
) -> None:
    """`--all` lists providers nobody asked for; those are not problems.

    `--all` enumerates every built-in provider, so a brand-new repo shows nine
    `not_connected` entries. Letting those drive the exit made the surface most
    likely to be scripted return 1 on a healthy repo.
    """
    _local_secret_env(monkeypatch, tmp_path)
    _simulate_ready_github(monkeypatch)
    repo = tmp_path / "biz"
    repo.mkdir()

    every = runner.invoke(app, ["connect", "status", "--all", "--repo", str(repo)])
    aggregate = runner.invoke(app, ["connect", "status", "--repo", str(repo)])

    assert every.exit_code == 0
    assert aggregate.exit_code == 0

    payload = json.loads(
        runner.invoke(app, ["connect", "status", "--all", "--repo", str(repo), "--json"]).stdout
    )
    assert payload["summary"]["configured"] == 0
    assert payload["summary"]["actionable"] == 0
    assert any(item["state"] == "not_connected" for item in payload["providers"])


def test_connect_status_all_still_exits_one_for_a_connected_actionable_provider(
    tmp_path: Path, monkeypatch
) -> None:
    """Scoping to connected providers must not mute a real problem under `--all`."""
    _local_secret_env(monkeypatch, tmp_path)
    _simulate_ready_github(monkeypatch)
    repo = tmp_path / "biz"
    repo.mkdir()
    runner.invoke(app, ["connect", "postiz", "--repo", str(repo), "--token", "postiz-token"])

    every = runner.invoke(app, ["connect", "status", "--all", "--repo", str(repo)])

    assert every.exit_code == 1


def test_connect_doctor_check_detail_matches_its_repair_line(tmp_path: Path, monkeypatch) -> None:
    """The detail must not say "cannot verify" about a provider with a probe."""
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    runner.invoke(app, ["connect", "cloudflare", "--repo", str(repo), "--token", "cf-test-token"])
    _legacy_ready_entry(repo, "cloudflare")

    check = connect_mod.doctor_check(repo)

    assert check["ok"] is False
    assert check["severity"] == "warn"
    assert check["repair_command"] == "mb connect test cloudflare"
    assert "never confirmed with the provider (cloudflare)" in check["detail"]
    assert "cannot verify" not in check["detail"]


def test_connect_doctor_check_detail_separates_testable_from_unverifiable(
    tmp_path: Path, monkeypatch
) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    runner.invoke(app, ["connect", "cloudflare", "--repo", str(repo), "--token", "cf-test-token"])
    _legacy_ready_entry(repo, "cloudflare")
    runner.invoke(app, ["connect", "resend", "--repo", str(repo), "--token", "re_fixture_key"])
    runner.invoke(app, ["connect", "test", "resend", "--repo", str(repo)])

    check = connect_mod.doctor_check(repo)

    # Both halves named, and the actionable one leads with the command to run.
    assert "never confirmed with the provider (cloudflare)" in check["detail"]
    assert "Main Branch cannot verify (resend)" in check["detail"]
    assert check["repair_command"] == "mb connect test cloudflare"


# Fake values in the shape of each rule. None of these is a real credential.
FAKE_SECRET_VALUES = {
    "credential_prefix:sk_": "sk_test_" + "F4k3v4lu3F4k3",
    "credential_prefix:rk_": "rk_live_" + "F4k3v4lu3F4k3",
    "credential_prefix:pk_live_": "pk_live_" + "F4k3v4lu3F4k3",
    "credential_prefix:ghp_": "ghp_" + "F4k3" * 9,
    "credential_prefix:github_pat_": "github_pat_" + "11F4K3_f4k3v4lu3",
    "credential_prefix:xox": "xoxb-" + "1111-2222-f4k3",
    "credential_prefix:AKIA": "AKIA" + "F4K3F4K3F4K3F4K3",
    "jwt_shape": "eyJhbGciOiJub25lIn0.eyJzdWIiOiJmYWtlIn0.",
    "high_entropy": "Q2hhbmdlTWVQbGVhc2U4ZjNrMjlYcVdlUnR5VWlPcA",
    "bearer_credential": "Bearer f4k3",
}


@pytest.mark.parametrize(("rule", "value"), sorted(FAKE_SECRET_VALUES.items()))
def test_metadata_refuses_secret_values_and_never_echoes_them(
    rule: str, value: str, tmp_path: Path, monkeypatch
) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()

    result = runner.invoke(
        app,
        ["connect", "cloudflare", "--metadata", f"zone_label={value}", "--repo", str(repo)],
    )

    assert result.exit_code == 2
    assert f"rule: {rule}" in result.stderr
    assert "'zone_label'" in result.stderr
    assert value not in result.output
    assert not (repo / ".mb" / "connect.yaml").exists()
    with pytest.raises(connect_mod.ConnectRefusal) as caught:
        connect_mod._parse_metadata([f"zone_label={value}"])
    assert caught.value.rule == "metadata_secret_value"


@pytest.mark.parametrize(
    "value",
    [
        "0" * 32,
        "3f2a9c1e7b4d4e0f9a8b7c6d5e4f3a2b",
        "123e4567-e89b-12d3-a456-426614174000",
        "act_1234567890",
        "123456789",
        "op://Business/Stripe restricted/credential",
        "https://example.com/Path/To/Thing123",
        "owner@example.com",
        "Main Stripe restricted key",
        "core/finance/books.journal",
        "re_engagement",
        "AcmeCorpProductionWorkspace01",
        "pk_test_publishable",
        "${STRIPE_API_KEY}",
        "2026-10-03",
        "AcmeProductionWorkspace2026",
        "UsEuUkCaAuNzApiKeyName2026",
        "UsCaMxBrArClPeCoLatamRegionKey",
        "HTTPSRedirectCheckerProdV2",
        "SpringLaunchCampaign2026Q2EU",
        "AbTestVariantBHeadlineShortV2",
        "MyAPIKeyForStagingEnvironment",
        "owner@example.invalid",
        "https://example.invalid/Path/To/Thing123",
        "op://ReviewVault/ExampleItem/credential",
        "2026-10-03T12:00:00Z",
        "Main restricted key",
        "Main bearer token reader",
        "note: renewed after the October audit",
        "re_engagement_campaign_2026",
        "CloudflareR2StorageBucket",
        "B2BMarketingCampaignOctober2026",
        "S3ProductionBucketUsWest2",
        "https://example.invalid/?campaign=CloudflareR2StorageBucket",
        "https://example.invalid/?campaign=SpringLaunch&region=us-west-2#top",
        "note: https://example.invalid/?campaign=CloudflareR2StorageBucket",
    ],
)
def test_metadata_accepts_ids_labels_and_references(value: str) -> None:
    assert connect_mod.metadata_value_rule(value) == ""


# Fake values only. Each was missed before the provider grammars, the word
# split and the segment heuristic.
@pytest.mark.parametrize(
    ("value", "rule"),
    [
        ("ghp_" + "f4k3" * 9, "credential_prefix:ghp_"),
        ("ghp_" + "a" * 36, "credential_prefix:ghp_"),
        ("note: " + "sk_live_" + "F4k3v4lu3F4k3", "credential_prefix:sk_"),
        ("note:" + "ghp_" + "f4k3" * 9, "credential_prefix:ghp_"),
        ("key for ci " + "Qx7Lm2Pz9Rt4Vb8Nc1Kd6Hs3", "high_entropy"),
        ("old key, " + "Bearer " + "F4k3T0k3nV4lu3F4k3T0k3n", "bearer_credential"),
        ("QwErTyUiOpAsDfGhJkLzXcVbNmQwErTyUiOpAsDf", "high_entropy"),
        ("re_" + "F4k3ab12" + "_" + "F4k3v4lu3F4k3v4lu3", "credential_prefix:re_"),
    ],
)
def test_metadata_refuses_previous_blind_spots(value: str, rule: str) -> None:
    assert connect_mod.metadata_value_rule(value) == rule


# A fake 40-character token. Inside a URL it is judged on its own, wherever
# the URL puts it.
_URL_FAKE_TOKEN = "Qx7Lm2Pz9Rt4Vb8Nc1Kd6Hs3Wy5Jf0Gt8Rn2Ls4M"
_URL_PERCENT_TOKEN = "".join(f"%{ord(char):02X}" for char in _URL_FAKE_TOKEN)


@pytest.mark.parametrize(
    "value",
    [
        f"https://example.invalid/?token={_URL_FAKE_TOKEN}",
        f"https://example.invalid/?campaign=SpringLaunch&token={_URL_FAKE_TOKEN}",
        f"note: https://example.invalid/?token={_URL_FAKE_TOKEN}",
        f"https://example.invalid/callback#access_token={_URL_FAKE_TOKEN}",
        f"https://reader:{_URL_FAKE_TOKEN}@example.invalid/",
        f"https://example.invalid/{_URL_FAKE_TOKEN}",
        f"https://example.invalid/token={_URL_FAKE_TOKEN}",
        f"https://example.invalid/{_URL_PERCENT_TOKEN}",
        f"https://example.invalid/#token:{_URL_FAKE_TOKEN}",
        f"https://example.invalid/#{_URL_FAKE_TOKEN}",
        f"https://example.invalid/#{_URL_PERCENT_TOKEN}",
        f"https://example.invalid/#/access/{_URL_FAKE_TOKEN}",
        f"https://{_URL_FAKE_TOKEN}@example.invalid/",
        f"https://{_URL_PERCENT_TOKEN}@example.invalid/",
        f"https://{_URL_FAKE_TOKEN}:ordinary@example.invalid/",
        f"https://example.invalid/?{_URL_FAKE_TOKEN}=ordinary",
        f"https://example.invalid/?token={_URL_PERCENT_TOKEN}",
        f"https://example.invalid/?token=ordinary&token={_URL_FAKE_TOKEN}",
    ],
)
def test_metadata_refuses_token_inside_url(value: str) -> None:
    assert connect_mod.metadata_value_rule(value) == "high_entropy"
    with pytest.raises(connect_mod.ConnectRefusal) as caught:
        connect_mod._parse_metadata([f"note={value}"])
    assert caught.value.rule == "metadata_secret_value"
    assert connect_mod._safe_status_metadata({"note": value}) == {}


@pytest.mark.parametrize(
    "value",
    [
        "https://example.invalid/" + "ghp_" + "a" * 36,
        "https://" + "ghp_" + "a" * 36 + "@example.invalid/",
        "https://example.invalid/#" + "ghp_" + "a" * 36,
    ],
)
def test_metadata_refuses_provider_token_inside_url(value: str) -> None:
    assert connect_mod.metadata_value_rule(value) == "credential_prefix:ghp_"
    assert connect_mod._safe_status_metadata({"note": value}) == {}


def _percent(text: str) -> str:
    """Percent-encode every character, separators included."""
    return "".join(f"%{ord(char):02X}" for char in text)


_URL_GHP_TOKEN = "ghp_" + "a" * 36


# Each shape passed intake and stayed visible in status before URL parts
# were fully decoded before splitting, nested URLs and host labels judged.
@pytest.mark.parametrize(
    ("value", "rule"),
    [
        (
            "https://example.invalid/" + _percent("access/" + _URL_GHP_TOKEN),
            "credential_prefix:ghp_",
        ),
        (
            "https://example.invalid/?next=" + _percent("https://inner.invalid/" + _URL_GHP_TOKEN),
            "credential_prefix:ghp_",
        ),
        ("https://example.invalid/" + _percent(_URL_PERCENT_TOKEN), "high_entropy"),
        ("https://" + _percent(_URL_PERCENT_TOKEN) + "@example.invalid/", "high_entropy"),
        (f"https://{_URL_FAKE_TOKEN}.example.invalid/", "high_entropy"),
        (f"https://{_URL_FAKE_TOKEN}.example.invalid:bad/", "high_entropy"),
    ],
)
def test_metadata_refuses_encoded_nested_and_host_tokens(value: str, rule: str) -> None:
    assert connect_mod.metadata_value_rule(value) == rule
    with pytest.raises(connect_mod.ConnectRefusal) as caught:
        connect_mod._parse_metadata([f"note={value}"])
    assert caught.value.rule == "metadata_secret_value"
    assert connect_mod._safe_status_metadata({"note": value}) == {}


def test_metadata_url_with_bad_port_is_judged_from_raw_pieces() -> None:
    assert connect_mod._url_parts("https://example.invalid:bad/docs") == [
        "https:",
        "example.invalid:bad",
        "docs",
    ]
    value = "https://example.invalid:bad/docs/getting-started"
    assert connect_mod._parse_metadata([f"note={value}"]) == {"note": value}
    assert connect_mod._safe_status_metadata({"note": value}) == {"note": value}


@pytest.mark.parametrize(
    "value",
    [
        "https://example.invalid/docs/getting-started",
        "https://example.invalid/2026/10/launch",
        "https://owner@example.invalid/",
        "https://example.invalid/#section-two",
        "https://example.invalid/?campaign=CloudflareR2StorageBucket",
        "https://example.invalid/" + _percent("blog/how-we-cut-our-onboarding-time-in-half"),
        "https://example.invalid/?next=" + _percent("https://inner.invalid/docs/getting-started"),
        "https://[2001:db8::1]:8443/docs/getting-started",
        "https://192.0.2.10:8080/status",
        "https://xn--bcher-kva.example.invalid/docs",
        "https://a1b2.example.invalid/",
        "https://shop-eu-west-2.storefront.example.invalid/",
    ],
)
def test_metadata_url_labels_pass_intake_and_status(value: str) -> None:
    assert connect_mod._parse_metadata([f"note={value}"]) == {"note": value}
    assert connect_mod._safe_status_metadata({"note": value}) == {"note": value}


# Constructed pronounceable runs around a short code with a generated tail.
# A code counts as a word only when the rest of the value reads as words.
# Metadata detection is a heuristic: a value built only from invented
# pronounceable words still passes (see docs/connect.md).
@pytest.mark.parametrize("code", ["R2", "B2B", "S3"])
@pytest.mark.parametrize(
    ("left", "right"), [("Amoriavena", "Ulenavopira"), ("Evolinaroa", "Pavirelona")]
)
def test_metadata_refuses_code_between_words_with_generated_tail(
    code: str, left: str, right: str
) -> None:
    value = left + code + right + "Qe7Lo"
    assert connect_mod.metadata_value_rule(value) == "high_entropy"
    assert connect_mod._safe_status_metadata({"note": value}) == {}


def test_metadata_invented_words_around_a_code_are_a_known_pass() -> None:
    """Documented limit: invented pronounceable words read as a label."""
    assert connect_mod.metadata_value_rule("AmoriavenaR2UlenavopiraPavirelona") == ""


def _random_values(alphabet: str, length: int, count: int = 10_000) -> list[str]:
    rng = random.Random(987)
    return ["".join(rng.choice(alphabet) for _ in range(length)) for _ in range(count)]


def test_metadata_high_entropy_miss_rates_match_docs() -> None:
    """The miss rates published in docs/connect.md, measured with a fixed seed."""
    alnum = string.ascii_letters + string.digits
    measured = {
        "alnum24": _random_values(alnum, 24),
        "base64_24": _random_values(alnum + "+/", 24),
        "letters40": _random_values(string.ascii_letters, 40),
    }
    missed = {
        name: sum(1 for value in values if not connect_mod.metadata_value_rule(value))
        for name, values in measured.items()
    }

    assert missed == {"alnum24": 33, "base64_24": 37, "letters40": 168}
    docs = (Path(__file__).resolve().parents[2] / "docs" / "connect.md").read_text()
    assert "33 of 10,000" in docs
    assert "37 of 10,000" in docs
    assert "168 of 10,000" in docs


def test_metadata_key_names_alone_never_refuse(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()

    result = connect_mod.connect_provider(
        "stripe",
        repo=repo,
        token="sk_test_fixture",
        metadata_pairs=[
            "key_name=Main restricted key",
            "onepassword_item=Stripe restricted",
            "source=op://Business/Stripe/credential",
            "api_key_label=checkout",
            "mode=test",
        ],
    )

    stored = result["status"]["metadata"]
    assert stored["key_name"] == "Main restricted key"
    assert stored["onepassword_item"] == "Stripe restricted"
    assert stored["source"] == "op://Business/Stripe/credential"
    assert "source" in connect_mod.SAFE_METADATA_KEYS


def test_metadata_without_equals_does_not_echo_the_argument() -> None:
    bare = "sk_live_" + "F4k3v4lu3F4k3"

    with pytest.raises(connect_mod.ConnectRefusal) as caught:
        connect_mod._parse_metadata([bare])

    assert caught.value.rule == "metadata_format"
    assert bare not in str(caught.value)


def test_status_hides_hand_edited_secret_values(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    connect_mod.connect_provider("cloudflare", repo=repo, token="cf-test-token")
    config_path = repo / ".mb" / "connect.yaml"
    config = yaml.safe_load(config_path.read_text())
    leaked = FAKE_SECRET_VALUES["credential_prefix:sk_"]
    config["providers"]["cloudflare"]["metadata"] = {"zone_label": leaked, "zone_id": "abc123"}
    config_path.write_text(yaml.safe_dump(config))

    status = connect_mod.status_provider("cloudflare", repo)

    assert "zone_label" not in status["metadata"]
    assert status["metadata"]["zone_id"] == "abc123"
    assert leaked not in json.dumps(status)


def _fake_op(value: str = "cf-rotated-token", *, ok: bool = True, stderr: str = ""):
    calls: list[list[str]] = []

    def run(args, cwd=None, timeout=5.0, *, env=None):
        calls.append(list(args))
        return {
            "ok": ok,
            "returncode": 0 if ok else 1,
            "stdout": value if ok else "",
            "stderr": stderr,
        }

    return run, calls


def _ok_http(monkeypatch) -> None:
    monkeypatch.setattr(
        connect_mod,
        "_http_get_json",
        lambda url, headers=None, **kwargs: {
            "ok": True,
            "state": "ready",
            "summary": "simulated provider response",
            "safe_to_share": True,
            "upstream": {"endpoint_family": kwargs["endpoint_family"], "safe_to_share": True},
        },
    )


def test_connect_source_is_stored_and_merges_existing_metadata(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    connect_mod.connect_provider(
        "cloudflare", repo=repo, token="cf-test-token", metadata_pairs=["zone_id=abc123"]
    )

    result = runner.invoke(
        app,
        [
            "connect",
            "cloudflare",
            "--source",
            "op://Business/Cloudflare/credential",
            "--repo",
            str(repo),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    metadata = json.loads(result.stdout)["status"]["metadata"]
    assert metadata == {"zone_id": "abc123", "source": "op://Business/Cloudflare/credential"}
    assert connect_mod.read_token("cloudflare", repo)["token"] == "cf-test-token"


def test_connect_source_refuses_a_secret_value(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    leaked = FAKE_SECRET_VALUES["credential_prefix:sk_"]

    result = runner.invoke(
        app, ["connect", "stripe", "--source", leaked, "--repo", str(repo)], input=""
    )

    assert result.exit_code == 2
    assert "--source looks like a secret" in result.stderr
    assert leaked not in result.output


def test_rotate_reads_op_ref_stores_and_probes(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    _ok_http(monkeypatch)
    repo = tmp_path / "biz"
    repo.mkdir()
    connect_mod.connect_provider(
        "cloudflare",
        repo=repo,
        token="cf-old-token",
        account_label="Main",
        metadata_pairs=["zone_id=abc123"],
        source="op://Business/Cloudflare/credential",
    )
    run, calls = _fake_op("cf-rotated-token\n")

    result = connect_mod.rotate_provider(
        "cloudflare", repo, which_func=lambda name: f"/usr/bin/{name}", command_runner=run
    )

    assert calls == [["op", "read", "--no-newline", "op://Business/Cloudflare/credential"]]
    assert result["ok"] is True
    assert result["provider_verified"] is True
    assert connect_mod.read_token("cloudflare", repo)["token"] == "cf-rotated-token"
    status = connect_mod.status_provider("cloudflare", repo)
    assert status["account_label"] == "Main"
    assert status["metadata"]["zone_id"] == "abc123"
    assert "cf-rotated-token" not in json.dumps(result)
    assert "cf-old-token" not in json.dumps(result)


def test_rotate_cli_json_never_carries_the_secret(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    _ok_http(monkeypatch)
    repo = tmp_path / "biz"
    repo.mkdir()
    connect_mod.connect_provider(
        "cloudflare",
        repo=repo,
        token="cf-old-token",
        source="op://Business/Cloudflare/credential",
    )
    run, _calls = _fake_op("cf-rotated-token")
    monkeypatch.setattr(connect_mod, "_run_command", run)
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")

    result = runner.invoke(app, ["connect", "rotate", "cloudflare", "--repo", str(repo), "--json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["provider_verified"] is True
    assert "cf-rotated-token" not in result.output


def test_rotate_without_source_explains(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    connect_mod.connect_provider("cloudflare", repo=repo, token="cf-test-token")

    result = runner.invoke(app, ["connect", "rotate", "cloudflare", "--repo", str(repo)])

    assert result.exit_code == 2
    assert "no recorded source" in result.stderr
    assert "--source op://vault/item/field" in result.stderr


@pytest.mark.parametrize(
    ("source", "which", "ok", "stderr", "rule"),
    [
        ("vault://elsewhere/item", "/usr/bin/op", True, "", "rotate_unsupported_source"),
        ("op://Business/Item/field", None, True, "", "rotate_op_missing"),
        (
            "op://Business/Item/field",
            "/usr/bin/op",
            False,
            "[ERROR] You are not currently signed in.",
            "rotate_op_signed_out",
        ),
        (
            "op://Business/Item/field",
            "/usr/bin/op",
            False,
            "item not found",
            "rotate_op_read_failed",
        ),
    ],
)
def test_rotate_refusals(
    source: str,
    which: str | None,
    ok: bool,
    stderr: str,
    rule: str,
    tmp_path: Path,
    monkeypatch,
) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    connect_mod.connect_provider("cloudflare", repo=repo, token="cf-test-token", source=source)
    run, _calls = _fake_op(ok=ok, stderr=stderr)

    with pytest.raises(connect_mod.ConnectRefusal) as caught:
        connect_mod.rotate_provider(
            "cloudflare", repo, which_func=lambda name: which, command_runner=run
        )

    assert caught.value.rule == rule
    assert connect_mod.read_token("cloudflare", repo)["token"] == "cf-test-token"


def test_rotate_not_connected(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()

    with pytest.raises(connect_mod.ConnectRefusal) as caught:
        connect_mod.rotate_provider("cloudflare", repo)

    assert caught.value.rule == "rotate_not_connected"


def _fake_http(
    responses: dict[str, tuple[int | None, dict[str, str]]], calls: list[dict[str, Any]]
):
    """Answer `_http_get_json` by endpoint family: (http_status or None, headers)."""

    def fake(url, headers=None, **kwargs):
        family = kwargs["endpoint_family"]
        calls.append({"url": url, "family": family, "headers": dict(headers or {})})
        status, response_headers = responses.get(family, (None, {}))
        ok = status is not None and 200 <= status < 300
        if status is None:
            state = "unvalidated"
        elif ok:
            state = "ready"
        else:
            state = "invalid" if status in {400, 401, 403, 404} else "unvalidated"
        return {
            "ok": ok,
            "state": state,
            "summary": f"simulated {family}",
            "safe_to_share": True,
            "upstream": {
                "endpoint_family": family,
                "http_status": status,
                "response_received": status is not None,
                "error_codes": [],
                "error_messages": [],
                "safe_to_share": True,
            },
            "headers": response_headers,
        }

    return fake


def test_registry_includes_github_and_ga4_with_probes() -> None:
    providers = {provider["id"]: provider for provider in connect_mod.provider_registry()}

    assert providers["github"]["required_secrets"] == ["api_key"]
    assert "GITHUB_TOKEN" in providers["github"]["env_vars"]
    assert providers["ga4"]["metadata_fields"] == ["property_id"]
    assert {"stripe", "github", "ga4"} <= connect_mod.PROBE_PROVIDERS
    assert connect_mod.exec_env_name("github") == "GITHUB_TOKEN"
    assert connect_mod.exec_env_name("ga4") == "MB_SECRET"


@pytest.mark.parametrize(
    ("provider_id", "expected"),
    [
        ("cloudflare", "CLOUDFLARE_API_TOKEN"),
        ("stripe", "STRIPE_API_KEY"),
        ("github", "GITHUB_TOKEN"),
        ("resend", "RESEND_API_KEY"),
        ("apify", "APIFY_TOKEN"),
        ("meta", "ACCESS_TOKEN"),
        ("postiz", "POSTIZ_API_KEY"),
        ("transcription", "OPENAI_API_KEY"),
        ("google", "GOOGLE_OAUTH_TOKEN"),
        ("ga4", "MB_SECRET"),
        ("mercury", "MB_SECRET"),
    ],
)
def test_exec_default_env_is_the_providers_own_variable(provider_id: str, expected: str) -> None:
    assert connect_mod.exec_env_name(provider_id) == expected
    assert connect_mod.exec_env_name(provider_id, "OVERRIDE") == "OVERRIDE"


def test_stripe_probe_reports_restricted_key_scopes(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        connect_mod,
        "_http_get_json",
        _fake_http(
            {
                "stripe_products_read": (200, {}),
                "stripe_prices_read": (200, {}),
                "stripe_customers_read": (403, {}),
                "stripe_charges_read": (403, {}),
                "stripe_balance_read": (200, {}),
            },
            calls,
        ),
    )
    repo = tmp_path / "biz"
    repo.mkdir()
    secret = "rk_test_" + "F4k3v4lu3F4k3"
    connect_mod.connect_provider("stripe", repo=repo, token=secret)

    result = runner.invoke(app, ["connect", "test", "stripe", "--repo", str(repo), "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["provider_verified"] is True
    assert payload["validation"]["scopes"] == {
        "products": "allowed",
        "prices": "allowed",
        "customers": "refused",
        "charges": "refused",
        "balance": "allowed",
    }
    assert "refused: customers, charges" in payload["validation"]["summary"]
    assert [call["family"] for call in calls] == [
        f"stripe_{name}_read" for name, _url in connect_mod.STRIPE_SCOPE_PROBES
    ]
    assert all(call["url"].startswith("https://api.stripe.com/v1/") for call in calls)
    assert secret not in result.output
    status = connect_mod.status_provider("stripe", repo)
    assert status["validation"]["scopes"]["customers"] == "refused"

    human = runner.invoke(app, ["connect", "test", "stripe", "--repo", str(repo)])
    assert "reads: products=allowed" in human.stdout


def test_stripe_probe_stops_on_rejected_key(tmp_path: Path, monkeypatch) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        connect_mod,
        "_http_get_json",
        _fake_http({"stripe_products_read": (401, {})}, calls),
    )
    provider = connect_mod.normalize_provider("stripe")

    result = connect_mod._validate_with_provider(provider, "sk_test_fake")

    assert result["ok"] is False
    assert result["state"] == "invalid"
    assert result["provider_verified"] is False
    assert len(calls) == 1


def test_stripe_probe_unreachable_is_unvalidated(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(connect_mod, "_http_get_json", _fake_http({}, calls))

    result = connect_mod._validate_with_provider(
        connect_mod.normalize_provider("stripe"), "sk_test_fake"
    )

    assert result["state"] == "unvalidated"
    assert set(result["scopes"].values()) == {"unknown"}


def test_github_probe_reports_classic_scopes(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        connect_mod,
        "_http_get_json",
        _fake_http(
            {"github_authenticated_user": (200, {"X-OAuth-Scopes": "repo, read:org"})}, calls
        ),
    )
    repo = tmp_path / "biz"
    repo.mkdir()
    secret = "ghp_" + "F4k3" * 9
    connect_mod.connect_provider("github", repo=repo, token=secret)

    result = connect_mod.test_provider("github", repo)

    assert result["ok"] is True
    assert result["validation"]["token_kind"] == "classic"
    assert result["validation"]["token_scopes"] == ["repo", "read:org"]
    assert "scopes: repo, read:org" in result["validation"]["summary"]
    assert calls[0]["url"] == "https://api.github.com/user"
    assert calls[0]["headers"]["Authorization"] == f"Bearer {secret}"
    assert secret not in json.dumps(result)


def test_github_probe_fine_grained_explains_permissions(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        connect_mod,
        "_http_get_json",
        _fake_http({"github_authenticated_user": (200, {})}, calls),
    )

    result = connect_mod._validate_with_provider(
        connect_mod.normalize_provider("github"), "github_pat_" + "11F4K3_f4k3"
    )

    assert result["ok"] is True
    assert result["token_kind"] == "fine_grained"
    assert result["token_scopes"] == []
    assert "token's settings" in result["summary"]


def test_github_custom_connection_keeps_resolving_as_builtin(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    connect_mod.connect_provider("github", repo=repo, token="ghp_" + "F4k3" * 9, custom=False)

    assert connect_mod.read_token("github", repo)["field"] == "api_key"
    assert connect_mod.read_token("github", repo)["ok"] is True


@pytest.mark.parametrize("property_id", ["", "G-ABC123", "123; drop"])
def test_ga4_probe_needs_numeric_property_id(property_id: str, monkeypatch) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(connect_mod, "_http_get_json", _fake_http({}, calls))

    result = connect_mod._validate_with_provider(
        connect_mod.normalize_provider("ga4"), "ya29.fake", {"property_id": property_id}
    )

    assert result["state"] == "unvalidated"
    assert result["repair_command"] == "mb connect ga4 --metadata property_id=<property-id>"
    assert calls == []


def test_ga4_probe_reads_the_configured_property(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        connect_mod,
        "_http_get_json",
        _fake_http({"ga4_property_read": (200, {})}, calls),
    )

    result = connect_mod._validate_with_provider(
        connect_mod.normalize_provider("ga4"), "ya29.fake", {"property_id": "properties/123456"}
    )

    assert result["ok"] is True
    assert calls[0]["url"] == "https://analyticsadmin.googleapis.com/v1beta/properties/123456"


def test_http_get_json_returns_only_named_headers(monkeypatch) -> None:
    class FakeResponse:
        status = 200
        headers = {"X-OAuth-Scopes": "repo", "Set-Cookie": "session=f4k3"}

        def read(self, size: int) -> bytes:
            return b'{"login": "someone"}'

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

    seen: dict[str, Any] = {}

    def fake_urlopen(request, timeout):
        seen["method"] = request.get_method()
        return FakeResponse()

    monkeypatch.setattr(http_safe_mod, "open_no_redirect", fake_urlopen)

    result = connect_mod._http_get_json(
        "https://api.example.test/user",
        {"Authorization": "Bearer f4k3"},
        endpoint_family="example",
        response_headers=("X-OAuth-Scopes",),
    )

    assert seen["method"] == "GET"
    assert result["ok"] is True
    assert result["headers"] == {"X-OAuth-Scopes": "repo"}
    assert "someone" not in json.dumps(result)


def _hostile_headers(secret: str) -> email.message.Message:
    headers = email.message.Message()
    headers["X-OAuth-Scopes"] = f"repo, {secret}, read:org, Bearer {secret}"
    return headers


@pytest.mark.parametrize("status", [200, 401])
def test_github_probe_redacts_secret_reflected_in_scope_header(monkeypatch, status: int) -> None:
    """A hostile response echoing the request token never reaches output."""
    secret = "ghp_" + "F4k3" * 9

    class FakeResponse:
        def __init__(self) -> None:
            self.status = status
            self.headers = _hostile_headers(secret)

        def read(self, size: int) -> bytes:
            return b"{}"

        def __enter__(self):
            return self

        def __exit__(self, *args) -> None:
            return None

    def fake_urlopen(request, timeout):
        if status >= 400:
            raise urllib.error.HTTPError(
                request.full_url,
                status,
                "Unauthorized",
                _hostile_headers(secret),
                io.BytesIO(b"{}"),
            )
        return FakeResponse()

    monkeypatch.setattr(http_safe_mod, "open_no_redirect", fake_urlopen)

    result = connect_mod._validate_with_provider(connect_mod.normalize_provider("github"), secret)

    assert secret not in json.dumps(result)
    assert result["token_scopes"] == ["repo", "read:org"]
    assert result["token_scopes_withheld"] == 2
    if status == 200:
        assert result["ok"] is True
        assert "scopes: repo, read:org (2 unrecognized value(s) withheld)" in result["summary"]
    else:
        assert result["ok"] is False
        assert result["state"] == "invalid"


def test_http_get_json_redacts_and_caps_returned_headers(monkeypatch) -> None:
    secret = "f4k3-request-secret-0000"

    def fake_urlopen(request, timeout):
        headers = email.message.Message()
        headers["X-OAuth-Scopes"] = f"repo,{secret}," + "x" * 2000
        raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", headers, io.BytesIO(b""))

    monkeypatch.setattr(http_safe_mod, "open_no_redirect", fake_urlopen)

    result = connect_mod._http_get_json(
        "https://api.example.test/user",
        {"Authorization": f"Bearer {secret}"},
        endpoint_family="example",
        response_headers=("X-OAuth-Scopes",),
    )

    returned = result["headers"]["X-OAuth-Scopes"]
    assert secret not in returned
    assert "<redacted>" in returned
    assert len(returned) <= connect_mod.RESPONSE_HEADER_MAX_CHARS


def test_generated_agents_guidance_routes_credentials_to_exec(tmp_path: Path) -> None:
    """Generated AGENTS.md sends agents to `exec`, never to `token` output."""
    rendered = codex_mod.render_agents_md(tmp_path, name="Example Co")

    text = " ".join(rendered.split())
    assert "need a credential -> `mb connect exec <provider> -- <command>`" in text
    assert "token to stdout" not in text
    assert "credentials -> `mb connect token`" not in text
    assert text.count("mb connect token") == text.count("`mb connect token` refuses")


# --- #991: a tokenless first connect records no secret it never stored ---------


def _stored_entry(repo: Path, provider_id: str) -> dict[str, Any]:
    config = yaml.safe_load((repo / ".mb" / "connect.yaml").read_text(encoding="utf-8"))
    entry: dict[str, Any] = config["providers"][provider_id]
    return entry


def test_tokenless_first_connect_with_metadata_records_no_secret_ref(
    tmp_path: Path, monkeypatch
) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()

    result = connect_mod.connect_provider("cloudflare", repo=repo, metadata_pairs=["zone_id=abc"])

    entry = _stored_entry(repo, "cloudflare")
    assert entry["connected"] is False
    assert entry["secrets"] == {}
    assert entry["metadata"] == {"zone_id": "abc"}
    assert result["ok"] is False
    status = result["status"]
    assert status["state"] == "missing_secret"
    assert status["repair_command"] == "mb connect cloudflare --token-stdin"
    assert status["connected"] is False
    assert status["configured"] is True
    assert status["secrets"]["api_token"]["ref"] == ""
    assert status["secrets"]["api_token"]["backend"] == "local-file"

    cli = runner.invoke(app, ["connect", "status", "--repo", str(repo), "--json"])

    # Still counted and still actionable, so status keeps exiting 1.
    assert cli.exit_code == 1, cli.output
    payload = json.loads(cli.stdout)
    assert payload["summary"]["configured"] == 1
    assert payload["summary"]["needs_repair"] == 1
    assert payload["providers"][0]["state"] == "missing_secret"


def test_tokenless_first_connect_with_source_then_rotate_connects(
    tmp_path: Path, monkeypatch
) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    _ok_http(monkeypatch)
    repo = tmp_path / "biz"
    repo.mkdir()
    source = "op://Business/Cloudflare/credential"

    first = runner.invoke(
        app,
        ["connect", "cloudflare", "--source", source, "--repo", str(repo), "--json"],
        input="",
    )

    assert first.exit_code == 1, first.output
    assert json.loads(first.stdout)["status"]["state"] == "missing_secret"
    entry = _stored_entry(repo, "cloudflare")
    assert entry["connected"] is False
    assert entry["secrets"] == {}
    assert entry["metadata"] == {"source": source}

    run, calls = _fake_op("cf-rotated-token")
    rotated = connect_mod.rotate_provider(
        "cloudflare", repo, which_func=lambda name: f"/usr/bin/{name}", command_runner=run
    )

    assert calls == [["op", "read", "--no-newline", source]]
    assert rotated["stored"] is True
    entry = _stored_entry(repo, "cloudflare")
    assert entry["connected"] is True
    assert entry["secrets"]["api_token"]["ref"]
    assert connect_mod.read_token("cloudflare", repo)["token"] == "cf-rotated-token"


def test_tokenless_reconnect_keeps_existing_connected_entry(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    connect_mod.connect_provider("cloudflare", repo=repo, token="cf-test-token")
    before = _stored_entry(repo, "cloudflare")["secrets"]

    connect_mod.connect_provider("cloudflare", repo=repo, metadata_pairs=["zone_id=abc"])

    entry = _stored_entry(repo, "cloudflare")
    assert entry["connected"] is True
    assert entry["secrets"] == before
    assert entry["metadata"] == {"zone_id": "abc"}
    assert connect_mod.read_token("cloudflare", repo)["token"] == "cf-test-token"


def test_entry_written_with_a_dangling_ref_still_reads_missing_secret(
    tmp_path: Path, monkeypatch
) -> None:
    # The shape releases before #991 wrote for a tokenless first connect.
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    (repo / ".mb").mkdir(parents=True)
    (repo / ".mb" / "connect.yaml").write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "providers": {
                    "cloudflare": {
                        "provider": "cloudflare",
                        "connected": True,
                        "scope": "repo",
                        "secrets": {
                            "api_token": {
                                "ref": "mainbranch:connect:demo:cloudflare:api_token",
                                "backend": "local-file",
                            }
                        },
                        "metadata": {"zone_id": "abc"},
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    status = connect_mod.status_provider("cloudflare", repo)

    assert status["state"] == "missing_secret"
    assert status["connected"] is True
    assert status["configured"] is True
    assert status["secrets"]["api_token"]["present"] is False
    assert status["secrets"]["api_token"]["presence"] == "absent"
    assert status["repair_command"] == "mb connect cloudflare --token-stdin"


# --- #973: every --json failure prints one envelope on stdout --------------------


def _assert_json_failure(result: Any, *, exit_code: int, state: str) -> dict[str, Any]:
    assert result.exit_code == exit_code, (result.stdout, result.stderr)
    payload: dict[str, Any] = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["state"] == state
    assert payload["result_status"] == "error"
    assert payload["errors"][0]["code"] == state
    assert payload["exit_code"] == exit_code
    assert payload["mb_command"].startswith("mb connect")
    assert payload["safe_to_share"] is True
    # The human text is unchanged and stays on stderr.
    assert result.stderr.startswith(payload["mb_command"] + ": ")
    return payload


@pytest.mark.parametrize(
    ("argv", "exit_code", "state"),
    [
        (["status", "no-such-provider"], 2, "invalid_request"),
        (["test"], 2, "usage_error"),
        (["rotate"], 2, "usage_error"),
        (["token", "cloudflare"], 2, "json_not_supported"),
        (["exec", "cloudflare", "--", "true"], 2, "json_not_supported"),
        (["repair"], 2, "usage_error"),
        (["repair", "--keychain"], 2, "needs_terminal"),
        (["status", "cloudflare", "extra-arg"], 2, "usage_error"),
        (["stripe", "--from-env"], 1, "missing_env_credential"),
    ],
)
def test_connect_json_failure_paths_print_an_envelope(
    tmp_path: Path, monkeypatch, argv: list[str], exit_code: int, state: str
) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()

    # Options first, so the exec case's `--` keeps them out of its command.
    with_json = runner.invoke(app, ["connect", "--repo", str(repo), "--json", *argv], input="")
    plain = runner.invoke(app, ["connect", "--repo", str(repo), *argv], input="")

    _assert_json_failure(with_json, exit_code=exit_code, state=state)
    if state == "json_not_supported":
        return  # Only --json itself fails here; the plain run is another command.
    # Without --json nothing changes: stdout stays empty, same exit, same text.
    assert plain.exit_code == exit_code
    assert plain.stdout == ""
    assert plain.stderr == with_json.stderr


def test_connect_json_refusal_names_its_rule_without_the_value(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    leaked = FAKE_SECRET_VALUES["credential_prefix:sk_"]

    result = runner.invoke(
        app, ["connect", "stripe", "--source", leaked, "--repo", str(repo), "--json"], input=""
    )

    payload = _assert_json_failure(result, exit_code=2, state="refused")
    assert payload["rule"] == "source_secret_value"
    assert leaked not in result.output


# Credential-shaped dummy for the stderr tests; built here, never printed.
STDERR_DUMMY_CREDENTIAL = "sk_live_" + "Q" * 32


@pytest.mark.parametrize("json_flag", [["--json"], []])
def test_connect_failure_keeps_a_credential_off_both_streams(
    tmp_path: Path, monkeypatch, json_flag: list[str]
) -> None:
    """The 0.6.3 release-gate scenario: the stdin credential reused as a metadata key."""
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    dummy = STDERR_DUMMY_CREDENTIAL

    result = runner.invoke(
        app,
        [
            "connect",
            "stripe",
            "--token-stdin",
            "--metadata",
            f"{dummy}={dummy}",
            "--repo",
            str(repo),
            *json_flag,
        ],
        input=dummy,
    )

    assert result.exit_code == 2
    assert dummy not in result.stdout
    assert dummy not in result.stderr
    assert "--metadata argument 1" in result.stderr
    if json_flag:
        payload = _assert_json_failure(result, exit_code=2, state="refused")
        assert payload["rule"] == "metadata_secret_value"
    else:
        assert result.stdout == ""


@pytest.mark.parametrize(
    "argv",
    [
        # A secret-shaped metadata key with a refused value, no stdin credential.
        ["connect", "cloudflare", "--metadata", "{dummy}=" + FAKE_SECRET_VALUES["high_entropy"]],
        ["connect", "{dummy}"],
        ["connect", "--custom", "{dummy}"],
        ["connect", "stripe", "{dummy}"],
        ["connect", "repair", "{dummy}"],
    ],
)
def test_connect_failure_messages_never_quote_secret_shaped_input(
    tmp_path: Path, monkeypatch, argv: list[str]
) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    dummy = STDERR_DUMMY_CREDENTIAL
    args = [arg.replace("{dummy}", dummy) for arg in argv]

    for json_flag in (["--json"], []):
        result = runner.invoke(app, [*args, "--repo", str(repo), *json_flag], input="")

        assert result.exit_code == 2, result.stderr
        assert dummy not in result.stdout
        assert dummy not in result.stderr
        assert FAKE_SECRET_VALUES["high_entropy"] not in result.output
        assert connect_mod.HIDDEN_INPUT in result.stderr


def test_connect_token_refusal_never_quotes_a_secret_shaped_provider(
    tmp_path: Path, monkeypatch
) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    monkeypatch.setattr(connect_mod, "stdout_exposes_secret", lambda: True)
    dummy = STDERR_DUMMY_CREDENTIAL

    result = runner.invoke(app, ["connect", "token", dummy, "--repo", str(tmp_path)])

    assert result.exit_code == connect_mod.TOKEN_REFUSED_EXIT_CODE
    assert dummy not in result.output
    assert "mb connect exec <provider> -- <command>" in result.stderr


def test_connect_exec_never_quotes_a_secret_shaped_command(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    connect_mod.connect_provider("cloudflare", repo=repo, token="cf-fixture-notfound-0000")
    dummy = STDERR_DUMMY_CREDENTIAL

    def fake_run(args, **kwargs):
        raise FileNotFoundError(2, "No such file or directory", args[0])

    outcome = connect_mod.exec_with_secret("cloudflare", [dummy], repo, runner=fake_run)

    assert outcome["returncode"] == 127
    assert outcome["error"] == f"command not found: {connect_mod.HIDDEN_INPUT}"
    assert dummy not in json.dumps(outcome)


def test_connect_failure_redacts_stderr_like_the_json_copy(capsys) -> None:
    """The reporter redacts the human line too, not only the JSON envelope."""
    from mb import cli as cli_mod

    dummy = STDERR_DUMMY_CREDENTIAL
    for json_out in (True, False):
        with pytest.raises(typer.Exit):
            cli_mod._connect_failure(
                "mb connect",
                f"upstream said {dummy}; Authorization: Bearer {dummy}",
                json_out=json_out,
                exit_code=1,
                state="connect_failed",
                secrets=(dummy,),
            )
        captured = capsys.readouterr()
        assert dummy not in captured.out
        assert dummy not in captured.err
        assert connect_mod.SECRET_REPLACEMENT in captured.err


@pytest.mark.parametrize(
    ("value", "shown"),
    [
        ("cloudflare", True),
        ("my-custom-provider", True),
        ("/usr/local/bin/stripe", True),
        (STDERR_DUMMY_CREDENTIAL, False),
        (FAKE_SECRET_VALUES["high_entropy"], False),
        (FAKE_SECRET_VALUES["jwt_shape"], False),
        ("x" * 65, False),
        ("two words", False),
    ],
)
def test_echoable_input_only_shows_plain_short_names(value: str, shown: bool) -> None:
    assert (connect_mod.echoable_input(value) == value) is shown
    assert (value in connect_mod.quoted_input(value)) is shown


@pytest.mark.parametrize(
    ("native_state", "backend_state"),
    [("locked", "keychain_locked"), ("unavailable", "keychain_unavailable")],
)
def test_connect_json_backend_failure_carries_sanitized_state(
    tmp_path: Path, monkeypatch, native_state: str, backend_state: str
) -> None:
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "macos-keychain")
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "home"))
    _fake_native_store(monkeypatch, native_state)
    repo = tmp_path / "biz"
    repo.mkdir()

    result = runner.invoke(
        app,
        ["connect", "resend", "--token-stdin", "--repo", str(repo), "--json"],
        input="re_secret_token\n",
    )

    payload = _assert_json_failure(result, exit_code=1, state="backend_unavailable")
    assert payload["backend_state"] == backend_state
    assert payload["repair_command"] == connect_mod._backend_repair(backend_state)["repair_command"]
    assert "Nothing was stored" in payload["summary"]
    assert "re_secret_token" not in result.output
    assert not (repo / ".mb" / "connect.yaml").exists()


def test_connect_json_unexpected_error_prints_an_envelope(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()

    def boom(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise KeyError("sk_live_should_never_print")

    monkeypatch.setattr(connect_mod, "status_all", boom)

    result = runner.invoke(app, ["connect", "status", "--repo", str(repo), "--json"])

    payload = _assert_json_failure(result, exit_code=1, state="unexpected_error")
    assert "KeyError" in payload["summary"]
    assert "sk_live_should_never_print" not in result.output


# --- #976: backend health without providers; unknown is not absent -------------


def test_status_reports_backend_health_with_no_providers(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()

    result = runner.invoke(app, ["connect", "status", "--repo", str(repo), "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["providers"] == []
    backend = payload["credential_backend"]
    assert backend["backend"] == "local-file"
    assert backend["ok"] is True
    assert backend["state"] == "ready"


def test_status_reports_locked_backend_with_no_providers(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "macos-keychain")
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "home"))
    _fake_native_store(monkeypatch, "locked")
    repo = tmp_path / "biz"
    repo.mkdir()

    status = connect_mod.status_all(repo)

    assert status["providers"] == []
    backend = status["credential_backend"]
    assert backend["backend"] == "macos-keychain"
    assert backend["ok"] is False
    assert backend["state"] == "keychain_locked"
    assert backend["repair_command"].startswith("security unlock-keychain")
    assert '"locked"' not in json.dumps(backend)


def test_locked_backend_reports_presence_unknown_not_absent(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    connect_mod.connect_provider("resend", repo=repo, token="re_secret_token")
    config_path = repo / ".mb" / "connect.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["providers"]["resend"]["secrets"]["api_key"]["backend"] = "macos-keychain"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    _fake_native_store(monkeypatch, "locked")

    status = connect_mod.status_all(repo)

    secret = status["providers"][0]["secrets"]["api_key"]
    assert secret["present"] is None
    assert secret["presence"] == "unknown"
    assert secret["backend_ok"] is False
    assert secret["backend_state"] == "keychain_locked"
    assert status["providers"][0]["state"] == "backend_unavailable"
    assert status["credential_backend"]["ok"] is False
    assert status["credential_backend"]["state"] == "keychain_locked"
    assert "re_secret_token" not in json.dumps(status)


def test_ready_and_missing_secrets_report_known_presence(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    connect_mod.connect_provider("resend", repo=repo, token="re_secret_token")
    connect_mod.connect_provider("cloudflare", repo=repo, metadata_pairs=["zone_id=abc"])

    status = connect_mod.status_all(repo)

    by_id = {item["provider"]: item for item in status["providers"]}
    stored = by_id["resend"]["secrets"]["api_key"]
    assert (stored["present"], stored["presence"]) == (True, "present")
    missing = by_id["cloudflare"]["secrets"]["api_token"]
    assert (missing["present"], missing["presence"]) == (False, "absent")
    assert status["credential_backend"] == {
        "backend": "local-file",
        "ok": True,
        "state": "ready",
        "summary": "Configured credential backend(s) are ready: local-file.",
        "repair": "",
        "repair_command": "",
        "safe_to_share": True,
    }


def test_metadata_only_first_connect_still_appears_in_identity(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    connect_mod.connect_provider(
        "meta", repo=repo, metadata_pairs=["pixel_id=111", "ad_account_id=act_222"]
    )
    connect_mod.connect_provider("cloudflare", repo=repo, metadata_pairs=["zone_id=demo-zone"])

    cli = runner.invoke(app, ["connect", "identity", "--repo", str(repo), "--json"])
    human = runner.invoke(app, ["connect", "identity", "--repo", str(repo)])

    assert cli.exit_code == 0, cli.output
    by_id = {item["provider"]: item for item in json.loads(cli.stdout)["providers"]}
    assert set(by_id) == {"meta", "cloudflare"}
    assert by_id["meta"]["identity"]["pixel_id"] == "111"
    assert by_id["meta"]["identity"]["ad_account_id"] == "act_222"
    assert by_id["cloudflare"]["identity"]["zone_id"] == "demo-zone"
    assert human.exit_code == 0, human.output
    assert "meta" in human.stdout.lower()
    assert "cloudflare" in human.stdout.lower()
    assert "no connected providers" not in human.stdout


def test_tokenless_slot_does_not_vouch_for_backend_health(tmp_path: Path, monkeypatch) -> None:
    # The tokenless entry reports backend local-file, as before, but asked no
    # backend anything; health still comes from the backend a connect would use.
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "macos-keychain")
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "home"))
    repo = tmp_path / "biz"
    repo.mkdir()
    connect_mod.connect_provider(
        "cloudflare", repo=repo, metadata_pairs=["zone_id=abc"], secret_backend="local-file"
    )
    _fake_native_store(monkeypatch, "locked")

    status = connect_mod.status_all(repo)

    assert status["providers"][0]["secrets"]["api_token"]["backend"] == "local-file"
    assert status["credential_backend"]["backend"] == "macos-keychain"
    assert status["credential_backend"]["state"] == "keychain_locked"


def test_tokenless_first_connect_still_counts_in_probe_gap(tmp_path: Path, monkeypatch) -> None:
    # The probe gap is about the provider, not the stored secret: resend has no
    # probe whether or not its key is stored yet, as on releases before #991.
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    connect_mod.connect_provider("resend", repo=repo, metadata_pairs=["sender_domain=example.com"])

    report = connect_mod.doctor(repo)

    assert report["probe_gap"]["providers"] == ["resend"]


def _record_google_oauth_grant(repo: Path, *, user_scope: bool = False) -> str:
    """Store a fake, well-formed grant in the local-file backend and record its ref."""

    config = connect_mod._read_config(repo.resolve())
    repo_id = str(config["repo_id"])
    ref = connect_mod._secret_ref(repo_id, "google", connect_mod.GOOGLE_OAUTH_GRANT_SLOT)
    grant = {
        "client_id": "fake-client.apps.example.com",
        "client_secret": "fake-oauth-grant-json",
        "refresh_token": "fake-oauth-grant-json",
    }
    credential_store_mod.SecretStore("local-file").set(ref, json.dumps(grant))
    slot = {"ref": ref, "backend": "local-file"}
    if user_scope:
        data = connect_mod._read_user_scope()
        entry = data["repos"][repo_id]["providers"]["google"]
        entry["secrets"][connect_mod.GOOGLE_OAUTH_GRANT_SLOT] = slot
        connect_mod._write_user_scope(data)
    else:
        config["providers"]["google"]["secrets"][connect_mod.GOOGLE_OAUTH_GRANT_SLOT] = slot
        connect_mod._write_config(repo.resolve(), config)
    return ref


def test_google_access_token_entry_status_keeps_one_slot(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    connect_mod.connect_provider("google", repo=repo, token="google-token")
    connect_mod.connect_provider("resend", repo=repo, token="re_live_key_abc")

    result = runner.invoke(app, ["connect", "status", "--repo", str(repo), "--json"])

    items = {item["provider"]: item for item in json.loads(result.stdout)["providers"]}
    google = items["google"]
    assert sorted(google["secrets"]) == ["access_token"]
    assert "optional" not in google["secrets"]["access_token"]
    assert google["credential_mode"] == "access_token"
    assert google["stored"] is True
    assert google["state"] == "unvalidated"
    # Providers without optional slots carry no credential_mode key at all.
    assert "credential_mode" not in items["resend"]


def test_google_recorded_oauth_grant_is_optional_and_oauth_mode(
    tmp_path: Path, monkeypatch
) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    connect_mod.connect_provider("google", repo=repo, token="google-token")
    ref = _record_google_oauth_grant(repo)

    result = runner.invoke(app, ["connect", "status", "google", "--repo", str(repo), "--json"])

    assert "fake-oauth-grant-json" not in result.stdout
    item = json.loads(result.stdout)
    grant = item["secrets"][connect_mod.GOOGLE_OAUTH_GRANT_SLOT]
    assert grant["optional"] is True
    assert grant["presence"] == "present"
    assert grant["ref"] == ref
    assert item["credential_mode"] == "oauth"
    assert item["stored"] is True
    assert item["state"] == "unvalidated"


def test_google_missing_oauth_grant_is_missing_secret(tmp_path: Path, monkeypatch) -> None:
    """A recorded sign-in grant that is gone is never `ready` (#1073)."""

    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    connect_mod.connect_provider("google", repo=repo, token="google-token")
    ref = _record_google_oauth_grant(repo)
    # The entry records the grant but the item is gone from the store.
    credential_store_mod.SecretStore("local-file").delete(ref)

    item = connect_mod.status_provider("google", repo)

    grant = item["secrets"][connect_mod.GOOGLE_OAUTH_GRANT_SLOT]
    assert grant["optional"] is True
    assert grant["presence"] == "absent"
    assert item["state"] == "missing_secret"
    assert item["stored"] is False
    assert item["repair_command"] == (
        "mb connect google --oauth --reauth --client-file <Desktop client JSON>"
    )


def test_google_user_scope_oauth_grant_survives_hydrate(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    connect_mod.connect_provider("google", repo=repo, token="google-token", scope="user")
    _record_google_oauth_grant(repo, user_scope=True)
    config = connect_mod._read_config(repo.resolve())
    config["providers"].pop("google", None)
    connect_mod._write_config(repo.resolve(), config)

    unhydrated = connect_mod.status_provider("google", repo)
    assert unhydrated["state"] == "needs_hydration"
    assert unhydrated["credential_mode"] == "oauth"
    assert unhydrated["secrets"][connect_mod.GOOGLE_OAUTH_GRANT_SLOT]["optional"] is True

    hydrated = connect_mod.hydrate(repo, provider_id="google")

    assert hydrated["hydrated"] == ["google"]
    item = hydrated["statuses"][0]
    assert item["credential_mode"] == "oauth"
    assert item["secrets"][connect_mod.GOOGLE_OAUTH_GRANT_SLOT]["presence"] == "present"


def _tree_snapshot(root: Path) -> dict[str, bytes]:
    if not root.exists():
        return {}
    return {str(path): path.read_bytes() for path in sorted(root.rglob("*")) if path.is_file()}


@pytest.mark.parametrize("json_flag", [["--json"], []])
@pytest.mark.parametrize("with_token", [False, True], ids=["tokenless", "token"])
def test_connect_refuses_a_credential_shaped_metadata_key(
    tmp_path: Path, monkeypatch, with_token: bool, json_flag: list[str]
) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    connect_mod.connect_provider("cloudflare", repo=repo, metadata_pairs=["zone_id=demo-zone"])
    before = (_tree_snapshot(repo / ".mb"), _tree_snapshot(tmp_path / "home"))
    dummy = STDERR_DUMMY_CREDENTIAL
    token_args = ["--token-stdin"] if with_token else []

    result = runner.invoke(
        app,
        [
            "connect",
            "cloudflare",
            *token_args,
            "--metadata",
            f"{dummy}=a-label",
            "--repo",
            str(repo),
            *json_flag,
        ],
        input="cf-fixture-token-0000" if with_token else "",
    )

    # Booleans only, so a failure never prints the dummy or the output.
    after = (_tree_snapshot(repo / ".mb"), _tree_snapshot(tmp_path / "home"))
    refused = result.exit_code == 2
    on_stdout = dummy in result.stdout
    on_stderr = dummy in result.stderr
    marked = connect_mod.HIDDEN_INPUT in result.stderr
    unchanged = before == after
    assert (refused, on_stdout, on_stderr, marked, unchanged) == (True, False, False, True, True)
    if json_flag:
        payload = _assert_json_failure(result, exit_code=2, state="refused")
        assert payload["rule"] == "metadata_secret_key"


def test_connect_metadata_keys_like_zone_id_still_work(tmp_path: Path, monkeypatch) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()

    result = runner.invoke(
        app,
        [
            "connect",
            "cloudflare",
            "--metadata",
            "zone_id=demo-zone",
            "--metadata",
            "account_id=demo-account",
            "--repo",
            str(repo),
            "--json",
        ],
    )

    assert result.exit_code in {0, 1}, result.output
    assert connect_mod.read_metadata("cloudflare", repo) == {
        "zone_id": "demo-zone",
        "account_id": "demo-account",
    }


def test_status_and_identity_hide_a_stored_credential_shaped_metadata_key(
    tmp_path: Path, monkeypatch
) -> None:
    _local_secret_env(monkeypatch, tmp_path)
    repo = tmp_path / "biz"
    repo.mkdir()
    connect_mod.connect_provider("cloudflare", repo=repo, metadata_pairs=["zone_id=demo-zone"])
    connect_mod.connect_provider(
        "mercury",
        repo=repo,
        token="mercury-fixture-token",
        metadata_pairs=["role=operating_cash_source"],
        custom=True,
    )
    dummy = STDERR_DUMMY_CREDENTIAL
    # Stored by hand (or by an older mb that accepted it).
    config_path = repo / ".mb" / "connect.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["providers"]["cloudflare"]["metadata"][dummy] = "a-label"
    config["providers"]["mercury"]["metadata"][dummy] = "a-label"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

    status = runner.invoke(app, ["connect", "status", "--repo", str(repo), "--json"])
    identity = runner.invoke(app, ["connect", "identity", "--repo", str(repo), "--json"])

    # Booleans only, so a failure never prints the dummy or the output.
    in_status = dummy in status.output
    in_identity = dummy in identity.output
    assert (in_status, in_identity) == (False, False)
    by_id = {item["provider"]: item for item in json.loads(status.stdout)["providers"]}
    assert by_id["cloudflare"]["metadata"]["zone_id"] == "demo-zone"
    assert by_id["cloudflare"]["safe_to_share"] is True
    identities = {item["provider"]: item for item in json.loads(identity.stdout)["providers"]}
    assert identities["mercury"]["identity"]["role"] == "operating_cash_source"
