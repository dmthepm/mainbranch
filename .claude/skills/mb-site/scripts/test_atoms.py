"""Atom envelope round-trip + invariant tests.

Run with: `python3 -m pytest .claude/skills/mb-site/scripts/test_atoms.py -v`
or directly:  `python3 .claude/skills/mb-site/scripts/test_atoms.py`

These tests exercise the schema contract — not network calls. Live integration
tests for `domain.py check` are run manually (see issue #93). Live `domain.py
buy` is deferred to the first real-project domain.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _envelope import SCHEMA_VERSION, ProviderRunMetadata, validate_status_consistency
from unittest.mock import patch

import dns as dns_module
import pages as pages_module
from dns import (
    CfResult,
    DnsEnsureData,
    DnsEnsureEnvelope,
    DnsEnsureError,
    PORKBUN_API_BASE,
    _cf_classify_error,
    _detect_registrar,
    _porkbun_update_ns,
)
from domain import (
    DomainBuyData,
    DomainBuyEnvelope,
    DomainBuyError,
    DomainCheckData,
    DomainCheckEnvelope,
    DomainCheckError,
    DomainCheckResult,
)
from pages import (
    PagesCreateProjectData,
    PagesCreateProjectEnvelope,
    PagesCreateProjectError,
    PagesSetDomainData,
    PagesSetDomainEnvelope,
    PagesSetDomainError,
    _domain_payload_to_data,
    _existing_project_source_matches,
    _map_cf_create_error,
    _map_cf_error,
    _wait_for_domain_active,
)


# ---------------------------------------------------------------------------
# DomainCheckEnvelope
# ---------------------------------------------------------------------------


def test_domain_check_ok_round_trip() -> None:
    env = DomainCheckEnvelope(
        status="ok",
        data=DomainCheckData(
            name="example",
            tlds_checked=["com", "co"],
            results=[
                DomainCheckResult(domain="example.com", available=False, method_used="bootstrap"),
                DomainCheckResult(domain="example.co", available=True, method_used="whois"),
            ],
            available=["example.co"],
        ),
        provenance={
            "domain_check": ProviderRunMetadata(
                status="ok",
                latency_ms=412,
                provider_version="domain-check",
            )
        },
    )
    payload = env.model_dump_json()
    parsed = DomainCheckEnvelope.model_validate_json(payload)
    assert parsed.status == "ok"
    assert parsed.error is None
    assert parsed.data.available == ["example.co"]
    assert parsed.schema_version == SCHEMA_VERSION


def test_domain_check_degraded_requires_error() -> None:
    with pytest.raises(ValidationError, match="status!=.ok. requires a structured error"):
        DomainCheckEnvelope(
            status="degraded",
            data=DomainCheckData(name="x", tlds_checked=[], results=[]),
        )


def test_domain_check_ok_rejects_error() -> None:
    with pytest.raises(ValidationError, match='status="ok" must not include an error'):
        DomainCheckEnvelope(
            status="ok",
            data=DomainCheckData(name="x", tlds_checked=[], results=[]),
            error=DomainCheckError(code="invalid_name", message="x"),
        )


def test_domain_check_error_code_is_closed() -> None:
    """Closed enum: only listed codes accepted."""
    with pytest.raises(ValidationError):
        DomainCheckError(code="not_a_real_code", message="x")  # type: ignore[arg-type]


def test_domain_check_extra_fields_rejected() -> None:
    """extra='forbid' on every model — schema drift is loud."""
    payload = {
        "schema_version": SCHEMA_VERSION,
        "status": "ok",
        "data": {
            "name": "x",
            "tlds_checked": [],
            "results": [],
            "available": [],
            "surprise_field": "drift",
        },
        "provenance": {},
        "error": None,
    }
    with pytest.raises(ValidationError):
        DomainCheckEnvelope.model_validate(payload)


# ---------------------------------------------------------------------------
# DomainBuyEnvelope
# ---------------------------------------------------------------------------


def test_domain_buy_ok_round_trip() -> None:
    env = DomainBuyEnvelope(
        status="ok",
        data=DomainBuyData(
            domain="example.com",
            registrar="cloudflare",
            price_usd=10.45,
            purchased=True,
            already_owned=False,
            expiry="2027-04-27",
            years=1,
        ),
        provenance={
            "cloudflare_registrar": ProviderRunMetadata(
                status="ok",
                latency_ms=1845,
                provider_version="cf-registrar-beta-2026-04-15",
                cost_incurred=1045,
            )
        },
    )
    parsed = DomainBuyEnvelope.model_validate_json(env.model_dump_json())
    assert parsed.data.purchased is True
    assert parsed.data.registrar == "cloudflare"
    assert parsed.provenance["cloudflare_registrar"].cost_incurred == 1045


def test_domain_buy_already_owned_is_ok_status() -> None:
    """already_owned is a *data field*, not an error — atom is idempotent."""
    env = DomainBuyEnvelope(
        status="ok",
        data=DomainBuyData(
            domain="example.com",
            registrar="cloudflare",
            already_owned=True,
            purchased=False,
            expiry="2027-04-27",
            years=1,
        ),
    )
    assert env.error is None
    assert env.data.already_owned is True


def test_domain_buy_user_declined_is_degraded() -> None:
    env = DomainBuyEnvelope(
        status="degraded",
        data=DomainBuyData(domain="example.com", years=1),
        error=DomainBuyError(
            code="user_declined",
            message="Registration requires --yes confirmation.",
            suggestion="Re-run with --yes",
        ),
    )
    assert env.error is not None
    assert env.error.code == "user_declined"


def test_domain_buy_error_code_is_closed() -> None:
    with pytest.raises(ValidationError):
        DomainBuyError(code="something_not_in_the_enum", message="x")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# validate_status_consistency (shared)
# ---------------------------------------------------------------------------


def test_validate_status_consistency_partial_requires_error() -> None:
    with pytest.raises(ValidationError, match="status!=.ok. requires a structured error"):
        DomainCheckEnvelope(
            status="partial",
            data=DomainCheckData(name="x", tlds_checked=[], results=[]),
        )


def test_provider_run_metadata_is_frozen() -> None:
    """Provenance rows are immutable — no after-the-fact mutation."""
    pr = ProviderRunMetadata(status="ok", latency_ms=100, provider_version="v1")
    with pytest.raises(ValidationError):
        pr.latency_ms = 200  # type: ignore[misc]


# ---------------------------------------------------------------------------
# DnsEnsureEnvelope
# ---------------------------------------------------------------------------


def test_dns_ensure_ok_round_trip() -> None:
    env = DnsEnsureEnvelope(
        status="ok",
        data=DnsEnsureData(
            domain="example.com",
            zone_id="abc123",
            ns_pair=["walt.ns.cloudflare.com", "sara.ns.cloudflare.com"],
            zone_created_now=True,
            registrar="porkbun",
            ns_swap_performed=True,
            propagated=True,
            propagation_seconds=143,
        ),
        provenance={
            "cf_zone_create": ProviderRunMetadata(
                status="ok", latency_ms=512, provider_version="cloudflare-api-v4"
            ),
            "porkbun_update_ns": ProviderRunMetadata(
                status="ok", latency_ms=812, provider_version="porkbun-api-v3"
            ),
            "dns_propagation_poll": ProviderRunMetadata(
                status="ok", latency_ms=143000, provider_version="dig+1.1.1.1"
            ),
        },
    )
    parsed = DnsEnsureEnvelope.model_validate_json(env.model_dump_json())
    assert parsed.data.zone_created_now is True
    assert parsed.data.ns_swap_performed is True
    assert len(parsed.data.ns_pair) == 2
    assert parsed.data.propagation_seconds == 143


def test_dns_ensure_idempotent_no_swap() -> None:
    """Idempotent path: zone already existed, NS already correct, no work performed."""
    env = DnsEnsureEnvelope(
        status="ok",
        data=DnsEnsureData(
            domain="example.com",
            zone_id="abc123",
            ns_pair=["walt.ns.cloudflare.com", "sara.ns.cloudflare.com"],
            zone_created_now=False,
            registrar="cloudflare",
            ns_swap_performed=False,
            propagated=True,
            propagation_seconds=2,
        ),
    )
    assert env.data.zone_created_now is False
    assert env.data.ns_swap_performed is False


def test_dns_ensure_error_codes_closed() -> None:
    with pytest.raises(ValidationError):
        DnsEnsureError(code="not_a_real_dns_code", message="x")  # type: ignore[arg-type]


def test_dns_ensure_invalid_domain_envelope() -> None:
    env = DnsEnsureEnvelope(
        status="degraded",
        data=DnsEnsureData(domain="not a valid domain"),
        error=DnsEnsureError(
            code="invalid_domain",
            message="Domain doesn't look valid.",
            suggestion="Pass a registrable apex.",
        ),
    )
    assert env.error is not None
    assert env.error.code == "invalid_domain"


def test_cf_classify_zone_already_exists() -> None:
    """Code 1097 → zone_already_exists with manual-cleanup suggestion."""
    result = CfResult(ok=False, latency_ms=100, status_code=400, error_code=1097, error_message="zone exists")
    code, suggestion = _cf_classify_error(result)
    assert code == "zone_already_exists"
    assert "another Cloudflare account" in suggestion


def test_cf_classify_unauthenticated_401() -> None:
    result = CfResult(ok=False, latency_ms=50, status_code=401, error_message="bad auth")
    code, suggestion = _cf_classify_error(result)
    assert code == "cf_unauthenticated"
    assert "CLOUDFLARE_API_TOKEN" in suggestion


def test_cf_classify_unauthenticated_by_code() -> None:
    """Code 10000 (auth) → cf_unauthenticated even on http 200."""
    result = CfResult(ok=False, latency_ms=50, status_code=200, error_code=10000, error_message="invalid")
    code, _ = _cf_classify_error(result)
    assert code == "cf_unauthenticated"


def test_cf_classify_rate_limited_429() -> None:
    result = CfResult(ok=False, latency_ms=50, status_code=429, error_message="too many")
    code, suggestion = _cf_classify_error(result)
    assert code == "cf_rate_limited"
    assert "back off" in suggestion.lower()


def test_cf_classify_timeout() -> None:
    result = CfResult(ok=False, latency_ms=30000, status_code=0, error_message="timeout")
    code, _ = _cf_classify_error(result)
    assert code == "network_timeout"


def test_cf_classify_generic_failure() -> None:
    """Unrecognized failure shape → cf_request_failed (not silent ok)."""
    result = CfResult(ok=False, latency_ms=50, status_code=500, error_code=9999, error_message="boom")
    code, suggestion = _cf_classify_error(result)
    assert code == "cf_request_failed"
    assert "9999" in suggestion or "500" in suggestion


# CF auth-error code coverage — all five flavors map to cf_unauthenticated.
# (Verified against Cloudflare's published error codes: 9106/9107 legacy,
# 9109 invalid/revoked, 6003/6111 malformed Authorization header.)
@pytest.mark.parametrize(
    "http_status,cf_code",
    [
        (403, 9109),  # token format OK but invalid/revoked
        (403, 9106),  # missing X-Auth-Email (legacy auth)
        (403, 9107),  # missing X-Auth-Key (legacy auth)
        (400, 6003),  # malformed Authorization header
        (400, 6111),  # malformed Authorization header variant
    ],
)
def test_cf_classify_auth_error_codes(http_status: int, cf_code: int) -> None:
    """All five auth-error code paths map to cf_unauthenticated."""
    result = CfResult(
        ok=False,
        latency_ms=80,
        status_code=http_status,
        error_code=cf_code,
        error_message="auth_problem",
    )
    code, suggestion = _cf_classify_error(result)
    assert code == "cf_unauthenticated", f"http {http_status} + code {cf_code} → {code}"
    assert "CLOUDFLARE_API_TOKEN" in suggestion
    assert "scopes" in suggestion.lower() or "scope" in suggestion.lower()


# ---------------------------------------------------------------------------
# Porkbun host pinned (regression test for the audit-caught bug)
# ---------------------------------------------------------------------------


def test_porkbun_api_base_pinned_to_correct_host() -> None:
    """Regression: Porkbun's documented API host is api.porkbun.com (not porkbun.com).

    porkbun.com/api/json/v3/* returns HTTP 403; api.porkbun.com/api/json/v3/* works.
    Audited live before this test was written.
    """
    assert PORKBUN_API_BASE == "https://api.porkbun.com/api/json/v3"


def test_porkbun_update_ns_url_construction() -> None:
    """The actual HTTP call hits api.porkbun.com, not porkbun.com.

    Mocks `requests.post` at the dns module level and asserts the URL passed.
    Catches a future regression where someone shortens the base back to porkbun.com.
    """
    fake_response = type(
        "FakeResp",
        (),
        {
            "status_code": 200,
            "json": lambda self: {"status": "SUCCESS"},
        },
    )()

    with patch.object(dns_module.requests, "post", return_value=fake_response) as mock_post:
        ok, _, err = _porkbun_update_ns(
            "example.com",
            ["walt.ns.cloudflare.com", "sara.ns.cloudflare.com"],
            "fake_key",
            "fake_secret",
        )
        assert ok is True
        assert err is None
        called_url = mock_post.call_args.args[0] if mock_post.call_args.args else mock_post.call_args.kwargs["url"]
        assert called_url.startswith("https://api.porkbun.com/api/json/v3/"), (
            f"Porkbun URL must start with api.porkbun.com — got {called_url}"
        )
        assert "example.com" in called_url
        assert "domain/updateNs" in called_url


def test_porkbun_update_ns_failure_returns_message() -> None:
    """Porkbun status != SUCCESS surfaces the message verbatim for diagnosis."""
    fake_response = type(
        "FakeResp",
        (),
        {
            "status_code": 200,
            "json": lambda self: {"status": "ERROR", "message": "invalid api key"},
        },
    )()

    with patch.object(dns_module.requests, "post", return_value=fake_response):
        ok, _, err = _porkbun_update_ns("example.com", ["a", "b"], "k", "s")
        assert ok is False
        assert err == "invalid api key"


def test_detect_registrar_explicit_wins() -> None:
    reg, err = _detect_registrar("porkbun")
    assert reg == "porkbun"
    assert err is None


def test_detect_registrar_cf_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN_REGISTRAR", "fake")
    monkeypatch.delenv("PORKBUN_API_KEY", raising=False)
    monkeypatch.delenv("PORKBUN_SECRET_KEY", raising=False)
    reg, err = _detect_registrar(None)
    assert reg == "cloudflare"
    assert err is None


def test_detect_registrar_porkbun_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN_REGISTRAR", raising=False)
    monkeypatch.setenv("PORKBUN_API_KEY", "k")
    monkeypatch.setenv("PORKBUN_SECRET_KEY", "s")
    reg, err = _detect_registrar(None)
    assert reg == "porkbun"
    assert err is None


def test_detect_registrar_neither_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN_REGISTRAR", raising=False)
    monkeypatch.delenv("PORKBUN_API_KEY", raising=False)
    monkeypatch.delenv("PORKBUN_SECRET_KEY", raising=False)
    reg, err = _detect_registrar(None)
    assert reg is None
    assert err is not None
    assert err.code == "registrar_required"


# ---------------------------------------------------------------------------
# PagesSetDomainEnvelope
# ---------------------------------------------------------------------------


def test_pages_set_domain_ok_round_trip() -> None:
    env = PagesSetDomainEnvelope(
        status="ok",
        data=PagesSetDomainData(
            project_name="thelastbill",
            domain="thelastbill.com",
            domain_id="dom_123",
            status="active",
            certificate_authority="google",
            already_attached=False,
            attached_now=True,
            ssl_active=True,
            poll_seconds=42,
            validation_status="active",
            verification_status="active",
            zone_tag="zone_123",
        ),
        provenance={
            "cf_pages_domain_add": ProviderRunMetadata(
                status="ok", latency_ms=321, provider_version="cloudflare-api-v4"
            ),
            "cf_pages_domain_poll": ProviderRunMetadata(
                status="ok", latency_ms=42000, provider_version="cloudflare-api-v4"
            ),
        },
    )
    parsed = PagesSetDomainEnvelope.model_validate_json(env.model_dump_json())
    assert parsed.status == "ok"
    assert parsed.error is None
    assert parsed.data.attached_now is True
    assert parsed.data.ssl_active is True
    assert parsed.schema_version == SCHEMA_VERSION


def test_pages_set_domain_already_attached_is_ok() -> None:
    env = PagesSetDomainEnvelope(
        status="ok",
        data=PagesSetDomainData(
            project_name="thelastbill",
            domain="thelastbill.com",
            status="active",
            already_attached=True,
            attached_now=False,
            ssl_active=True,
        ),
    )
    assert env.error is None
    assert env.data.already_attached is True
    assert env.data.attached_now is False


def test_pages_set_domain_error_codes_closed() -> None:
    with pytest.raises(ValidationError):
        PagesSetDomainError(code="not_a_real_pages_code", message="x")  # type: ignore[arg-type]


def test_pages_set_domain_degraded_requires_error() -> None:
    with pytest.raises(ValidationError, match="status!=.ok. requires a structured error"):
        PagesSetDomainEnvelope(
            status="degraded",
            data=PagesSetDomainData(project_name="x", domain="example.com"),
        )


def test_pages_set_domain_payload_to_data_extracts_statuses() -> None:
    data = _domain_payload_to_data(
        "thelastbill",
        "thelastbill.com",
        {
            "id": "dom_123",
            "name": "thelastbill.com",
            "status": "active",
            "certificate_authority": "lets_encrypt",
            "validation_data": {"status": "active"},
            "verification_data": {"status": "active"},
            "zone_tag": "zone_123",
        },
        already_attached=True,
        attached_now=False,
        poll_seconds=0,
    )
    assert data.domain_id == "dom_123"
    assert data.certificate_authority == "lets_encrypt"
    assert data.ssl_active is True
    assert data.validation_status == "active"
    assert data.verification_status == "active"


def test_pages_map_cf_error_project_not_found() -> None:
    err = _map_cf_error(
        CfResult(ok=False, latency_ms=10, status_code=404, error_message="not found"),
        project_checked=False,
    )
    assert err.code == "project_not_found"


def test_pages_map_cf_error_auth_reuses_cf_classifier() -> None:
    err = _map_cf_error(
        CfResult(ok=False, latency_ms=10, status_code=403, error_code=9109, error_message="invalid token"),
        project_checked=True,
    )
    assert err.code == "cf_unauthenticated"
    assert "CLOUDFLARE_API_TOKEN" in (err.suggestion or "")


def test_pages_map_cf_error_rate_limit_reuses_cf_classifier() -> None:
    err = _map_cf_error(
        CfResult(ok=False, latency_ms=10, status_code=429, error_message="too many"),
        project_checked=True,
    )
    assert err.code == "cf_rate_limited"


def test_pages_map_cf_error_dns_hint() -> None:
    err = _map_cf_error(
        CfResult(ok=False, latency_ms=10, status_code=400, error_message="DNS validation failed"),
        project_checked=True,
    )
    assert err.code == "dns_misconfigured"


def test_pages_wait_for_domain_active_success(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = [
        CfResult(
            ok=True,
            latency_ms=10,
            status_code=200,
            payload={
                "id": "dom_123",
                "status": "pending",
                "validation_data": {"status": "pending"},
                "verification_data": {"status": "pending"},
            },
        ),
        CfResult(
            ok=True,
            latency_ms=10,
            status_code=200,
            payload={
                "id": "dom_123",
                "status": "active",
                "validation_data": {"status": "active"},
                "verification_data": {"status": "active"},
            },
        ),
    ]

    def fake_cf_call(*args: object, **kwargs: object) -> CfResult:
        return calls.pop(0)

    monkeypatch.setattr(pages_module, "_cf_call", fake_cf_call)
    monkeypatch.setattr(pages_module.time, "sleep", lambda _seconds: None)
    provenance: dict[str, ProviderRunMetadata] = {}
    payload, elapsed, err = _wait_for_domain_active("acct", "proj", "example.com", "tok", 10, provenance)
    assert err is None
    assert payload is not None
    assert payload["status"] == "active"
    assert elapsed >= 0
    assert "cf_pages_domain_poll" in provenance


def test_pages_wait_for_domain_active_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    result = CfResult(
        ok=True,
        latency_ms=10,
        status_code=200,
        payload={
            "id": "dom_123",
            "status": "pending",
            "validation_data": {"status": "pending"},
            "verification_data": {"status": "pending"},
        },
    )
    monkeypatch.setattr(pages_module, "_cf_call", lambda *args, **kwargs: result)
    monkeypatch.setattr(pages_module.time, "sleep", lambda _seconds: None)

    ticks = iter([0, 2, 5])
    monkeypatch.setattr(pages_module.time, "monotonic", lambda: next(ticks))
    payload, elapsed, err = _wait_for_domain_active("acct", "proj", "example.com", "tok", 3, {})
    assert payload is not None
    assert elapsed == 5
    assert err is not None
    assert err.code == "ssl_provisioning_timeout"


def test_pages_wait_for_domain_active_error_status(monkeypatch: pytest.MonkeyPatch) -> None:
    result = CfResult(
        ok=True,
        latency_ms=10,
        status_code=200,
        payload={
            "id": "dom_123",
            "status": "error",
            "validation_data": {"status": "error", "error_message": "CNAME missing"},
            "verification_data": {"status": "pending"},
        },
    )
    monkeypatch.setattr(pages_module, "_cf_call", lambda *args, **kwargs: result)
    payload, _elapsed, err = _wait_for_domain_active("acct", "proj", "example.com", "tok", 10, {})
    assert payload is None
    assert err is not None
    assert err.code == "dns_misconfigured"
    assert "CNAME missing" in err.message


# ---------------------------------------------------------------------------
# PagesCreateProjectEnvelope (#98 — git-source-by-default)
# ---------------------------------------------------------------------------


def test_pages_create_project_ok_round_trip() -> None:
    env = PagesCreateProjectEnvelope(
        status="ok",
        data=PagesCreateProjectData(
            project_name="mb-git-test",
            source_type="github",
            repo_owner="example-co",
            repo_name="thelastbill-test",
            production_branch="main",
            project_id="b6dacee6-fa1e-497f-b81b-369927a475a7",
            pages_subdomain="mb-git-test.pages.dev",
            already_existed=False,
            created_now=True,
        ),
        provenance={
            "cf_pages_project_create": ProviderRunMetadata(
                status="ok", latency_ms=3992, provider_version="cloudflare-api-v4"
            )
        },
    )
    parsed = PagesCreateProjectEnvelope.model_validate_json(env.model_dump_json())
    assert parsed.data.created_now is True
    assert parsed.data.source_type == "github"
    assert parsed.data.repo_owner == "example-co"


def test_pages_create_project_idempotent_already_existed() -> None:
    """Idempotent path: project already exists with matching source."""
    env = PagesCreateProjectEnvelope(
        status="ok",
        data=PagesCreateProjectData(
            project_name="mb-git-test",
            source_type="github",
            repo_owner="example-co",
            repo_name="thelastbill-test",
            production_branch="main",
            project_id="b6dacee6-fa1e-497f-b81b-369927a475a7",
            pages_subdomain="mb-git-test.pages.dev",
            already_existed=True,
            created_now=False,
        ),
    )
    assert env.error is None
    assert env.data.already_existed is True
    assert env.data.created_now is False


def test_pages_create_project_error_codes_closed() -> None:
    with pytest.raises(ValidationError):
        PagesCreateProjectError(code="not_a_real_create_code", message="x")  # type: ignore[arg-type]


def test_pages_create_project_source_type_closed() -> None:
    with pytest.raises(ValidationError):
        PagesCreateProjectData(project_name="x", source_type="bitbucket")  # type: ignore[arg-type]


def test_existing_project_source_matches_github_match() -> None:
    payload = {
        "source": {
            "type": "github",
            "config": {
                "owner": "example-co",
                "repo_name": "thelastbill-test",
                "production_branch": "main",
            },
        }
    }
    assert _existing_project_source_matches(
        payload, "github", "example-co", "thelastbill-test", "main"
    ) is True


def test_existing_project_source_matches_owner_mismatch() -> None:
    payload = {
        "source": {
            "type": "github",
            "config": {
                "owner": "dmthepm",
                "repo_name": "thelastbill-test",
                "production_branch": "main",
            },
        }
    }
    assert _existing_project_source_matches(
        payload, "github", "example-co", "thelastbill-test", "main"
    ) is False


def test_existing_project_source_matches_type_mismatch() -> None:
    """direct-upload project (source: null) should not match github request."""
    assert _existing_project_source_matches(
        {"source": None}, "github", "example-co", "thelastbill-test", "main"
    ) is False


def test_map_cf_create_error_8000011_github_app() -> None:
    """Code 8000011 → github_app_not_installed with install URL in suggestion."""
    result = CfResult(
        ok=False,
        latency_ms=300,
        status_code=400,
        error_code=8000011,
        error_message="There is an internal issue with your Cloudflare Pages Git installation.",
    )
    err = _map_cf_create_error(result)
    assert err.code == "github_app_not_installed"
    assert "github.com/apps/cloudflare-workers-and-pages" in (err.suggestion or "")


def test_map_cf_create_error_409_already_exists() -> None:
    result = CfResult(
        ok=False,
        latency_ms=80,
        status_code=409,
        error_message="A project with this name already exists.",
    )
    err = _map_cf_create_error(result)
    assert err.code == "project_already_exists"


def test_map_cf_create_error_repo_not_found() -> None:
    result = CfResult(
        ok=False,
        latency_ms=120,
        status_code=400,
        error_message="The repository was not found.",
    )
    err = _map_cf_create_error(result)
    assert err.code == "repo_not_found"


def test_map_cf_create_error_passes_through_auth() -> None:
    """Generic auth failure (no specific create-project code) routes to cf_unauthenticated."""
    result = CfResult(
        ok=False,
        latency_ms=50,
        status_code=401,
        error_message="invalid token",
    )
    err = _map_cf_create_error(result)
    assert err.code == "cf_unauthenticated"


def test_map_cf_create_error_generic_fallback() -> None:
    """Unrecognized failure → cf_request_failed (closed-enum, no silent ok)."""
    result = CfResult(
        ok=False,
        latency_ms=50,
        status_code=500,
        error_code=9999,
        error_message="boom",
    )
    err = _map_cf_create_error(result)
    assert err.code == "cf_request_failed"


# ---------------------------------------------------------------------------
# OgRenderEnvelope (atom 5)
# ---------------------------------------------------------------------------

import og_render as og_render_module
from og_render import (
    OG_HEIGHT,
    OG_MAX_BYTES,
    OG_WIDTH,
    OgRenderData,
    OgRenderEnvelope,
    OgRenderError,
    _png_dimensions,
)


# A 23-byte minimal SVG that rsvg-convert can rasterize without external assets.
_TINY_SVG = (
    b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 630">'
    b'<rect width="1200" height="630" fill="#0a0a0a"/>'
    b'<text x="600" y="320" font-family="sans-serif" font-size="96" '
    b'font-weight="700" text-anchor="middle" fill="#fafafa">test</text>'
    b"</svg>"
)


def test_og_render_ok_round_trip() -> None:
    env = OgRenderEnvelope(
        status="ok",
        data=OgRenderData(
            input_svg="/tmp/og.svg",
            output_png="/tmp/og.png",
            renderer="rsvg-convert",
            width=OG_WIDTH,
            height=OG_HEIGHT,
            output_bytes=540_000,
        ),
        provenance={
            "rsvg_convert": ProviderRunMetadata(
                status="ok", latency_ms=512, provider_version="rsvg-convert"
            )
        },
    )
    parsed = OgRenderEnvelope.model_validate_json(env.model_dump_json())
    assert parsed.data.renderer == "rsvg-convert"
    assert parsed.data.width == OG_WIDTH and parsed.data.height == OG_HEIGHT


def test_og_render_degraded_requires_error() -> None:
    with pytest.raises(ValidationError, match="status!=.ok. requires a structured error"):
        OgRenderEnvelope(
            status="degraded",
            data=OgRenderData(input_svg="/x.svg", output_png="/x.png"),
        )


def test_og_render_error_codes_closed() -> None:
    with pytest.raises(ValidationError):
        OgRenderError(code="not_a_real_render_error", message="x")  # type: ignore[arg-type]


def test_og_render_renderer_field_closed() -> None:
    with pytest.raises(ValidationError):
        OgRenderData(input_svg="/x.svg", output_png="/x.png", renderer="imagemagick")  # type: ignore[arg-type]


def test_png_dimensions_reads_real_png(tmp_path: Path) -> None:
    """Sanity check the dependency-free PNG header parser used for validation."""
    import zlib

    png_path = tmp_path / "1x1.png"
    width, height = 1, 1
    ihdr_data = struct_pack_uint32(width) + struct_pack_uint32(height) + bytes([8, 2, 0, 0, 0])
    ihdr_chunk = _png_chunk(b"IHDR", ihdr_data)
    raw = b"\x00" + bytes([0, 0, 0])
    idat = zlib.compress(raw)
    idat_chunk = _png_chunk(b"IDAT", idat)
    iend_chunk = _png_chunk(b"IEND", b"")
    png_path.write_bytes(b"\x89PNG\r\n\x1a\n" + ihdr_chunk + idat_chunk + iend_chunk)

    assert _png_dimensions(png_path) == (1, 1)


def test_png_dimensions_returns_none_on_non_png(tmp_path: Path) -> None:
    not_png = tmp_path / "not.png"
    not_png.write_bytes(b"<svg></svg>")
    assert _png_dimensions(not_png) is None


def test_og_render_live_against_tiny_svg(tmp_path: Path) -> None:
    """End-to-end: the atom renders a hand-written SVG via the real rsvg-convert binary.

    This is the live integration test for #100. Howdy's og.svg works too, but
    using a tiny inline SVG keeps the test self-contained and fast.
    """
    if shutil.which("rsvg-convert") is None:
        pytest.skip("rsvg-convert not installed locally")

    svg_path = tmp_path / "og.svg"
    png_path = tmp_path / "og.png"
    svg_path.write_bytes(_TINY_SVG)

    from click.testing import CliRunner

    runner = CliRunner()
    result = runner.invoke(
        og_render_module.cli, ["render", str(svg_path), str(png_path)]
    )
    assert result.exit_code == 0, f"stdout: {result.stdout}\nstderr: {result.stderr}"
    payload = json.loads(result.stdout)
    assert payload["status"] == "ok"
    assert payload["data"]["renderer"] == "rsvg-convert"
    assert payload["data"]["width"] == OG_WIDTH
    assert payload["data"]["height"] == OG_HEIGHT
    assert png_path.exists() and png_path.stat().st_size > 0


def test_og_render_missing_input_envelope(tmp_path: Path) -> None:
    """Read-only error path: nonexistent SVG returns a structured envelope."""
    from click.testing import CliRunner

    runner = CliRunner()
    result = runner.invoke(
        og_render_module.cli,
        ["render", str(tmp_path / "does-not-exist.svg"), str(tmp_path / "out.png")],
    )
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "degraded"
    assert payload["error"]["code"] == "svg_input_missing"


def test_og_render_no_renderer_available(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When neither renderer is installed, atom fails loud with no_renderer_available."""
    svg_path = tmp_path / "og.svg"
    svg_path.write_bytes(_TINY_SVG)

    monkeypatch.setattr(og_render_module.shutil, "which", lambda _name: None)

    def _raise_import(*_a: object, **_k: object) -> tuple[bool, int, str | None]:
        return False, 0, "module_missing"

    monkeypatch.setattr(og_render_module, "_render_cairosvg", _raise_import)

    from click.testing import CliRunner

    runner = CliRunner()
    result = runner.invoke(
        og_render_module.cli, ["render", str(svg_path), str(tmp_path / "out.png")]
    )
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["error"]["code"] == "no_renderer_available"
    assert "librsvg" in payload["error"]["suggestion"]


# Tiny PNG-construction helpers used by test_png_dimensions_reads_real_png.

def struct_pack_uint32(n: int) -> bytes:
    import struct as _struct
    return _struct.pack(">I", n)


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    import struct as _struct
    import zlib as _zlib
    crc = _zlib.crc32(chunk_type + data) & 0xFFFFFFFF
    return _struct.pack(">I", len(data)) + chunk_type + data + _struct.pack(">I", crc)


# ---------------------------------------------------------------------------
# StripeEnvelope (atom 6)
# ---------------------------------------------------------------------------

# The atom file is named `stripe.py` to match the /mb-site atom convention. The
# `sys.path.insert` at the top of this test file puts the scripts directory
# first, so `import stripe` resolves to the local atom rather than the
# (unrelated, not installed) Stripe Python SDK.
import stripe as stripe_module
from stripe import (
    CreatePaymentLinkData,
    CreatePaymentLinkEnvelope,
    ListProductsData,
    ListProductsEnvelope,
    StripeError,
    StripeResult,
)


def test_stripe_create_payment_link_ok_round_trip() -> None:
    env = CreatePaymentLinkEnvelope(
        status="ok",
        data=CreatePaymentLinkData(
            offer_slug="thelastbill",
            payment_link_url="https://buy.stripe.com/abc123",
            payment_link_id="plink_123",
            product_id="prod_123",
            price_id="price_123",
            amount_cents=10000,
            currency="usd",
            statement_descriptor="EXAMPLE LASTBILL",
            success_url="https://thelastbill.com/start/thanks/",
            created_now=True,
        ),
        provenance={
            "stripe_product_create": ProviderRunMetadata(
                status="ok",
                latency_ms=420,
                provider_version="stripe-2024-06-20",
            ),
        },
    )
    blob = env.model_dump_json()
    rehydrated = CreatePaymentLinkEnvelope.model_validate_json(blob)
    assert rehydrated.status == "ok"
    assert rehydrated.data.payment_link_url == "https://buy.stripe.com/abc123"
    assert rehydrated.error is None


def test_stripe_envelope_degraded_requires_error() -> None:
    with pytest.raises(ValidationError):
        CreatePaymentLinkEnvelope(
            status="degraded",
            data=CreatePaymentLinkData(offer_slug="x"),
            error=None,
        )


def test_stripe_envelope_ok_forbids_error() -> None:
    with pytest.raises(ValidationError):
        CreatePaymentLinkEnvelope(
            status="ok",
            data=CreatePaymentLinkData(offer_slug="x"),
            error=StripeError(code="stripe_request_failed", message="x"),
        )


def test_stripe_error_codes_closed() -> None:
    with pytest.raises(ValidationError):
        StripeError(code="not_a_real_code", message="x")  # type: ignore[arg-type]


def test_stripe_form_encode_nested_dict() -> None:
    encoded = dict(stripe_module._form_encode({
        "default_price_data": {"currency": "usd", "unit_amount": 10000},
    }))
    assert encoded["default_price_data[currency]"] == "usd"
    assert encoded["default_price_data[unit_amount]"] == "10000"


def test_stripe_form_encode_list_of_dicts() -> None:
    encoded = dict(stripe_module._form_encode({
        "line_items": [{"price": "price_1", "quantity": 1}],
    }))
    assert encoded["line_items[0][price]"] == "price_1"
    assert encoded["line_items[0][quantity]"] == "1"


def test_stripe_form_encode_metadata() -> None:
    encoded = dict(stripe_module._form_encode({
        "metadata": {"mb_offer": "thelastbill", "mb_kind": "deposit"},
    }))
    assert encoded["metadata[mb_offer]"] == "thelastbill"
    assert encoded["metadata[mb_kind]"] == "deposit"


def test_stripe_form_encode_booleans() -> None:
    encoded = dict(stripe_module._form_encode({"active": True}))
    assert encoded["active"] == "true"


def test_stripe_truncate_descriptor() -> None:
    assert stripe_module._truncate_descriptor("  EXAMPLE  ") == "EXAMPLE"
    assert stripe_module._truncate_descriptor("EXAMPLE CO THE LAST BILL EXTRA") == "EXAMPLE CO THE LAST BI"
    assert len(stripe_module._truncate_descriptor("EXAMPLE CO THE LAST BILL EXTRA")) == 22


def test_stripe_validate_offer_slug_ok() -> None:
    assert stripe_module._validate_offer_slug("thelastbill") is None
    assert stripe_module._validate_offer_slug("the-last-bill") is None
    assert stripe_module._validate_offer_slug("offer_1") is None


def test_stripe_validate_offer_slug_rejects_uppercase() -> None:
    err = stripe_module._validate_offer_slug("TheLastBill")
    assert err is not None and "invalid" in err.lower()


def test_stripe_validate_offer_slug_rejects_leading_hyphen() -> None:
    err = stripe_module._validate_offer_slug("-thelastbill")
    assert err is not None


def test_stripe_validate_statement_descriptor_ok() -> None:
    assert stripe_module._validate_statement_descriptor("EXAMPLE") is None
    assert stripe_module._validate_statement_descriptor("EXAMPLE LAST BILL") is None


def test_stripe_validate_statement_descriptor_rejects_special_chars() -> None:
    assert stripe_module._validate_statement_descriptor("EXAM<>PLE") is not None


def test_stripe_classify_error_unauthenticated() -> None:
    code, suggestion = stripe_module._classify_error(StripeResult(
        ok=False,
        latency_ms=100,
        status_code=401,
        error_message="Invalid API Key",
    ))
    assert code == "stripe_unauthenticated"
    assert "STRIPE_API_KEY" in suggestion


def test_stripe_classify_error_rate_limited() -> None:
    code, _ = stripe_module._classify_error(StripeResult(
        ok=False,
        latency_ms=100,
        status_code=429,
        error_message="rate limit",
    ))
    assert code == "stripe_rate_limited"


def test_stripe_classify_error_timeout() -> None:
    code, _ = stripe_module._classify_error(StripeResult(
        ok=False,
        latency_ms=30000,
        status_code=0,
        error_message="timeout",
    ))
    assert code == "network_timeout"


def test_stripe_classify_error_generic_fallback() -> None:
    code, _ = stripe_module._classify_error(StripeResult(
        ok=False,
        latency_ms=100,
        status_code=500,
        error_message="server error",
    ))
    assert code == "stripe_request_failed"


# ---------------------------------------------------------------------------
# stripe.py CLI: validation paths (no network)
# ---------------------------------------------------------------------------

from click.testing import CliRunner as _StripeCliRunner


def _run_stripe(args: list[str], env: dict[str, str] | None = None) -> dict:
    runner = _StripeCliRunner()
    result = runner.invoke(stripe_module.cli, args, env=env or {})
    return json.loads(result.stdout)


def test_stripe_cli_missing_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("STRIPE_API_KEY", raising=False)
    payload = _run_stripe([
        "create-payment-link", "thelastbill",
        "--amount", "10000",
        "--success-url", "https://thelastbill.com/start/thanks/",
        "--statement-descriptor", "EXAMPLE CO",
    ])
    assert payload["status"] == "degraded"
    assert payload["error"]["code"] == "missing_api_key"


def test_stripe_cli_invalid_amount(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STRIPE_API_KEY", "sk_test_dummy")
    payload = _run_stripe([
        "create-payment-link", "thelastbill",
        "--amount", "10",
        "--success-url", "https://thelastbill.com/start/thanks/",
    ])
    assert payload["status"] == "degraded"
    assert payload["error"]["code"] == "invalid_amount"


def test_stripe_cli_invalid_currency(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STRIPE_API_KEY", "sk_test_dummy")
    payload = _run_stripe([
        "create-payment-link", "thelastbill",
        "--amount", "10000",
        "--currency", "US",
        "--success-url", "https://thelastbill.com/start/thanks/",
    ])
    assert payload["status"] == "degraded"
    assert payload["error"]["code"] == "invalid_currency"


def test_stripe_cli_invalid_success_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STRIPE_API_KEY", "sk_test_dummy")
    payload = _run_stripe([
        "create-payment-link", "thelastbill",
        "--amount", "10000",
        "--success-url", "http://thelastbill.com/start/thanks/",
    ])
    assert payload["status"] == "degraded"
    assert payload["error"]["code"] == "invalid_success_url"


def test_stripe_cli_invalid_statement_descriptor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STRIPE_API_KEY", "sk_test_dummy")
    payload = _run_stripe([
        "create-payment-link", "thelastbill",
        "--amount", "10000",
        "--success-url", "https://thelastbill.com/start/thanks/",
        "--statement-descriptor", "NO<>NE",
    ])
    assert payload["status"] == "degraded"
    assert payload["error"]["code"] == "invalid_statement_descriptor"


def test_stripe_cli_refuses_missing_statement_descriptor_before_any_stripe_call(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STRIPE_API_KEY", "sk_test_dummy")

    def fake_call(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("Stripe must not be called without a statement descriptor")

    monkeypatch.setattr(stripe_module, "_stripe_call", fake_call)
    payload = _run_stripe([
        "create-payment-link", "thelastbill",
        "--amount", "10000",
        "--success-url", "https://thelastbill.com/start/thanks/",
    ])
    assert payload["status"] == "degraded"
    assert payload["error"]["code"] == "missing_statement_descriptor"


def test_stripe_cli_invalid_offer_slug(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STRIPE_API_KEY", "sk_test_dummy")
    payload = _run_stripe([
        "create-payment-link", "TheLastBill",
        "--amount", "10000",
        "--success-url", "https://thelastbill.com/start/thanks/",
    ])
    assert payload["status"] == "degraded"
    assert payload["error"]["code"] == "invalid_offer_slug"


def test_stripe_cli_idempotent_returns_existing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Search returns an existing product with stashed payment-link URL → idempotent ok."""
    monkeypatch.setenv("STRIPE_API_KEY", "sk_test_dummy")

    existing_product = {
        "id": "prod_existing",
        "default_price": "price_existing",
        "metadata": {
            "mb_offer": "thelastbill",
            "mb_kind": "deposit",
            "mb_payment_link_url": "https://buy.stripe.com/EXISTING",
        },
    }

    def fake_search(api_key, slug, prov):  # type: ignore[no-untyped-def]
        prov["stripe_products_search"] = ProviderRunMetadata(
            status="ok", latency_ms=50, provider_version="stripe-2024-06-20"
        )
        return existing_product, StripeResult(ok=True, latency_ms=50, status_code=200)

    monkeypatch.setattr(stripe_module, "_search_existing_product", fake_search)

    payload = _run_stripe([
        "create-payment-link", "thelastbill",
        "--amount", "10000",
        "--success-url", "https://thelastbill.com/start/thanks/",
        "--statement-descriptor", "EXAMPLE CO",
    ])
    assert payload["status"] == "ok"
    assert payload["data"]["payment_link_url"] == "https://buy.stripe.com/EXISTING"
    assert payload["data"]["created_now"] is False
    assert payload["data"]["product_id"] == "prod_existing"


def test_stripe_cli_creates_when_no_existing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Search returns nothing; product + payment link get created in sequence."""
    monkeypatch.setenv("STRIPE_API_KEY", "sk_test_dummy")

    calls: list[tuple[str, str]] = []

    def fake_call(method, path, api_key, body=None, idempotency_key=None, query=None):  # type: ignore[no-untyped-def]
        calls.append((method, path))
        if path == "/products/search":
            return StripeResult(ok=True, latency_ms=10, status_code=200, payload={"data": []})
        if path == "/products" and method == "POST":
            return StripeResult(
                ok=True, latency_ms=20, status_code=200,
                payload={
                    "id": "prod_new",
                    "default_price": "price_new",
                    "metadata": {"mb_offer": "thelastbill"},
                },
            )
        if path == "/payment_links" and method == "POST":
            return StripeResult(
                ok=True, latency_ms=15, status_code=200,
                payload={"id": "plink_new", "url": "https://buy.stripe.com/NEW"},
            )
        if path.startswith("/products/prod_new") and method == "POST":
            return StripeResult(ok=True, latency_ms=10, status_code=200, payload={"id": "prod_new"})
        raise AssertionError(f"unexpected call: {method} {path}")

    monkeypatch.setattr(stripe_module, "_stripe_call", fake_call)

    payload = _run_stripe([
        "create-payment-link", "thelastbill",
        "--amount", "10000",
        "--success-url", "https://thelastbill.com/start/thanks/",
        "--statement-descriptor", "EXAMPLE CO",
    ])
    assert payload["status"] == "ok"
    assert payload["data"]["payment_link_url"] == "https://buy.stripe.com/NEW"
    assert payload["data"]["created_now"] is True
    assert payload["data"]["product_id"] == "prod_new"
    assert payload["data"]["price_id"] == "price_new"
    # Confirm the call sequence: search → create product → create link → update metadata
    assert ("GET", "/products/search") in calls
    assert ("POST", "/products") in calls
    assert ("POST", "/payment_links") in calls


def test_stripe_cli_unauthenticated_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    """A 401 from Stripe surfaces as `stripe_unauthenticated`."""
    monkeypatch.setenv("STRIPE_API_KEY", "sk_test_bad")

    def fake_call(method, path, api_key, body=None, idempotency_key=None, query=None):  # type: ignore[no-untyped-def]
        return StripeResult(
            ok=False, latency_ms=20, status_code=401,
            error_message="Invalid API Key provided",
            error_type="invalid_request_error",
        )

    monkeypatch.setattr(stripe_module, "_stripe_call", fake_call)

    payload = _run_stripe([
        "create-payment-link", "thelastbill",
        "--amount", "10000",
        "--success-url", "https://thelastbill.com/start/thanks/",
        "--statement-descriptor", "EXAMPLE CO",
    ])
    assert payload["status"] == "degraded"
    assert payload["error"]["code"] == "stripe_unauthenticated"


# ---------------------------------------------------------------------------

import shutil  # placed at the bottom so prior tests don't shadow it


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
