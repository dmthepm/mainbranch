#!/usr/bin/env python3
"""pages.py — Cloudflare Pages operations atom.

Credential entry happens in the owner's own terminal, because the hidden prompt needs a real terminal; the agent hands off, then resumes its readiness check.

Subcommands:
    create-project  Create a Pages project, default source.type=github so
                    `git push` auto-deploys. Idempotent on re-run with
                    matching source config; returns dns_misconfigured
                    behavior if config drifts.

    set-domain      Idempotent: attach a custom domain to an existing
                    Cloudflare Pages project, ensure the verification
                    DNS record exists, then poll until the custom-domain
                    status is active.

Invocation: `python3 pages.py <subcommand> <args>`
Output: companyctx-shape envelope JSON on stdout, logs on stderr.
Exit code: 0 on ok|partial, 1 on degraded.

Per `decisions/2026-04-27-git-auto-deploy-non-negotiable.md`: every
Pages project this atom creates must default to git source. The
`--source=direct-upload` flag exists as opt-out for CI environments
that can't install the Cloudflare GitHub App.
"""

from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path
from typing import Literal
from urllib.parse import urlencode

import click
from pydantic import BaseModel, ConfigDict, Field, model_validator

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _envelope import (  # noqa: E402
    OWNER_HANDOFF,
    SCHEMA_VERSION,
    EnvelopeStatus,
    ProviderRunMetadata,
    emit,
    log,
    validate_status_consistency,
)
from dns import CfResult, _cf_call, _cf_classify_error  # noqa: E402

_PROJECT_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,57}[a-z0-9]$")
_DOMAIN_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$")
# GitHub owner / repo names: alphanumerics + dash + underscore + dot.
# Length capped to 100 (org max is 39, repo max is 100).
_GH_OWNER_RE = re.compile(r"^[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,38})$")
_GH_REPO_RE = re.compile(r"^[a-zA-Z0-9._-]{1,100}$")

# CF Pages GitHub App install URL — surfaced in suggestions when CF reports
# code 8000011 (Pages Git installation broken). Verified live 2026-04-27.
_CF_GITHUB_APP_INSTALL_URL = "https://github.com/apps/cloudflare-workers-and-pages"


PagesSetDomainErrorCode = Literal[
    "invalid_project_name",
    "invalid_domain",
    "cf_account_id_missing",
    "cf_unauthenticated",
    "cf_rate_limited",
    "project_not_found",
    "domain_already_attached",
    "ssl_provisioning_timeout",
    "cf_request_failed",
    "dns_misconfigured",
    "network_timeout",
]


class PagesSetDomainError(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: PagesSetDomainErrorCode
    message: str
    suggestion: str | None = None


class PagesSetDomainData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_name: str
    domain: str
    domain_id: str | None = None
    status: str | None = None
    certificate_authority: Literal["google", "lets_encrypt"] | None = None
    already_attached: bool = False
    attached_now: bool = False
    ssl_active: bool = False
    poll_seconds: int | None = None
    validation_status: str | None = None
    validation_error: str | None = None
    verification_status: str | None = None
    verification_error: str | None = None
    zone_tag: str | None = None
    pages_subdomain: str | None = None
    dns_record_id: str | None = None
    dns_record_content: str | None = None
    dns_record_created_now: bool = False


class PagesSetDomainEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["0.1.0"] = SCHEMA_VERSION
    status: EnvelopeStatus
    data: PagesSetDomainData
    provenance: dict[str, ProviderRunMetadata] = Field(default_factory=dict)
    error: PagesSetDomainError | None = None

    @model_validator(mode="after")
    def _v(self) -> PagesSetDomainEnvelope:
        return validate_status_consistency(self)  # type: ignore[return-value]


def _provider_row(result: CfResult) -> ProviderRunMetadata:
    return ProviderRunMetadata(
        status="ok" if result.ok else "failed",
        latency_ms=result.latency_ms,
        error=None if result.ok else (result.error_message or "unknown"),
        provider_version="cloudflare-api-v4",
    )


def _map_cf_error(result: CfResult, *, project_checked: bool = False) -> PagesSetDomainError:
    if result.status_code == 404 and not project_checked:
        return PagesSetDomainError(
            code="project_not_found",
            message=result.error_message or "Cloudflare Pages project not found.",
            suggestion="Create the Pages project in Cloudflare first, then re-run this atom.",
        )

    dns_hint = result.error_message or ""
    if any(term in dns_hint.lower() for term in ("dns", "cname", "zone", "validation")):
        return PagesSetDomainError(
            code="dns_misconfigured",
            message=result.error_message or "Cloudflare could not validate the custom domain.",
            suggestion="Run dns.py ensure for this apex and confirm the zone lives in the same Cloudflare account.",
        )

    code, suggestion = _cf_classify_error(result)
    if code in ("cf_unauthenticated", "cf_rate_limited", "network_timeout"):
        return PagesSetDomainError(
            code=code,  # type: ignore[arg-type]
            message=result.error_message or code,
            suggestion=suggestion,
        )
    return PagesSetDomainError(
        code="cf_request_failed",
        message=result.error_message or "Cloudflare Pages request failed.",
        suggestion=suggestion,
    )


def _domain_payload_to_data(
    project_name: str,
    domain: str,
    payload: dict,
    *,
    already_attached: bool,
    attached_now: bool,
    poll_seconds: int | None,
    pages_subdomain: str | None = None,
    dns_record_id: str | None = None,
    dns_record_content: str | None = None,
    dns_record_created_now: bool = False,
) -> PagesSetDomainData:
    validation = payload.get("validation_data") or {}
    verification = payload.get("verification_data") or {}
    status = payload.get("status")
    return PagesSetDomainData(
        project_name=project_name,
        domain=domain,
        domain_id=payload.get("id") or payload.get("domain_id"),
        status=status,
        certificate_authority=payload.get("certificate_authority"),
        already_attached=already_attached,
        attached_now=attached_now,
        ssl_active=status == "active",
        poll_seconds=poll_seconds,
        validation_status=validation.get("status"),
        validation_error=validation.get("error_message"),
        verification_status=verification.get("status"),
        verification_error=verification.get("error_message"),
        zone_tag=payload.get("zone_tag"),
        pages_subdomain=pages_subdomain,
        dns_record_id=dns_record_id,
        dns_record_content=dns_record_content,
        dns_record_created_now=dns_record_created_now,
    )


def _domain_error_message(payload: dict) -> str | None:
    validation = payload.get("validation_data") or {}
    verification = payload.get("verification_data") or {}
    return (
        validation.get("error_message")
        or verification.get("error_message")
        or payload.get("error_message")
    )


def _is_missing_domain(result: CfResult) -> bool:
    if result.status_code == 404:
        return True
    msg = (result.error_message or "").lower()
    return "not found" in msg and "domain" in msg


def _candidate_zone_names(domain: str) -> list[str]:
    labels = domain.strip(".").split(".")
    return [".".join(labels[idx:]) for idx in range(0, max(0, len(labels) - 1))]


def _lookup_zone_id(
    account_id: str,
    domain: str,
    token: str,
    provenance: dict[str, ProviderRunMetadata],
) -> tuple[str | None, PagesSetDomainError | None]:
    for zone_name in _candidate_zone_names(domain):
        query = urlencode({"name": zone_name, "account.id": account_id})
        result = _cf_call("GET", f"/zones?{query}", token)
        provenance["cf_pages_zone_lookup"] = _provider_row(result)
        if not result.ok:
            return None, _map_cf_error(result, project_checked=True)
        zones = result.payload if isinstance(result.payload, list) else []
        if zones:
            zone_id = zones[0].get("id")
            if isinstance(zone_id, str) and zone_id:
                return zone_id, None
    return None, PagesSetDomainError(
        code="dns_misconfigured",
        message=f"No Cloudflare zone found for {domain!r} in this account.",
        suggestion="Run dns.py ensure for this domain, then retry pages.py set-domain.",
    )


def _record_matches_pages(record: dict, domain: str, pages_subdomain: str) -> bool:
    return (
        record.get("type") == "CNAME"
        and str(record.get("name", "")).rstrip(".").lower() == domain
        and str(record.get("content", "")).rstrip(".").lower() == pages_subdomain
    )


def _ensure_pages_dns_record(
    account_id: str,
    domain: str,
    pages_subdomain: str,
    token: str,
    provenance: dict[str, ProviderRunMetadata],
    *,
    zone_tag: str | None,
) -> tuple[str | None, bool, PagesSetDomainError | None]:
    zone_id = zone_tag
    if not zone_id:
        zone_id, zone_err = _lookup_zone_id(account_id, domain, token, provenance)
        if zone_err is not None:
            return None, False, zone_err

    query = urlencode({"name": domain})
    lookup = _cf_call("GET", f"/zones/{zone_id}/dns_records?{query}", token)
    provenance["cf_pages_dns_record_lookup"] = _provider_row(lookup)
    if not lookup.ok:
        return None, False, _map_cf_error(lookup, project_checked=True)

    records = lookup.payload if isinstance(lookup.payload, list) else []
    for record in records:
        if _record_matches_pages(record, domain, pages_subdomain):
            record_id = record.get("id")
            return (record_id if isinstance(record_id, str) else None), False, None

    if records:
        existing = records[0]
        message = (
            f"DNS record already exists for {domain}: "
            f"{existing.get('type')} {existing.get('content')}"
        )
        return None, False, PagesSetDomainError(
            code="dns_misconfigured",
            message=message,
            suggestion=(
                f"Point {domain} at {pages_subdomain} with a proxied CNAME record, "
                "or remove the conflicting DNS record and retry."
            ),
        )

    create = _cf_call(
        "POST",
        f"/zones/{zone_id}/dns_records",
        token,
        json_body={
            "type": "CNAME",
            "name": domain,
            "content": pages_subdomain,
            "ttl": 1,
            "proxied": True,
            "comment": "Managed by Main Branch pages.py set-domain",
        },
    )
    provenance["cf_pages_dns_record_create"] = _provider_row(create)
    if not create.ok:
        return None, False, _map_cf_error(create, project_checked=True)

    payload = create.payload if isinstance(create.payload, dict) else {}
    record_id = payload.get("id")
    return (record_id if isinstance(record_id, str) else None), True, None


def _wait_for_domain_active(
    account_id: str,
    project_name: str,
    domain: str,
    token: str,
    timeout_seconds: int,
    provenance: dict[str, ProviderRunMetadata],
) -> tuple[dict | None, int, PagesSetDomainError | None]:
    start = time.monotonic()
    attempt = 0
    while True:
        attempt += 1
        result = _cf_call(
            "GET",
            f"/accounts/{account_id}/pages/projects/{project_name}/domains/{domain}",
            token,
        )
        provenance["cf_pages_domain_poll"] = _provider_row(result)
        elapsed = int(time.monotonic() - start)

        if not result.ok:
            return None, elapsed, _map_cf_error(result, project_checked=True)

        payload = result.payload if isinstance(result.payload, dict) else {}
        status = payload.get("status")
        validation_status = (payload.get("validation_data") or {}).get("status")
        verification_status = (payload.get("verification_data") or {}).get("status")

        if status == "active":
            return payload, elapsed, None

        if status in ("blocked", "error", "deactivated") or validation_status == "error" or verification_status == "error":
            message = _domain_error_message(payload) or f"Pages custom domain status is {status!r}."
            return None, elapsed, PagesSetDomainError(
                code="dns_misconfigured",
                message=message,
                suggestion="Confirm the domain is an active Cloudflare zone in this account and retry.",
            )

        if elapsed >= timeout_seconds:
            return payload, elapsed, PagesSetDomainError(
                code="ssl_provisioning_timeout",
                message=f"Pages custom domain did not become active within {timeout_seconds}s.",
                suggestion="Wait a few minutes and re-run; Cloudflare may still be provisioning the certificate.",
            )

        log(
            f"  [{elapsed:>3}s] domain status={status}, "
            f"validation={validation_status}, verification={verification_status}; waiting"
        )
        time.sleep(min(10, max(2, timeout_seconds // 30)))


# ---------------------------------------------------------------------------
# create-project — atom subcommand for git-connected Pages project creation
# ---------------------------------------------------------------------------

PagesCreateProjectErrorCode = Literal[
    "invalid_project_name",
    "invalid_repo_owner",
    "invalid_repo_name",
    "cf_account_id_missing",
    "cf_unauthenticated",
    "cf_rate_limited",
    "github_app_not_installed",
    "repo_not_found",
    "project_already_exists",
    "project_source_mismatch",
    "cf_request_failed",
    "network_timeout",
]


class PagesCreateProjectError(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: PagesCreateProjectErrorCode
    message: str
    suggestion: str | None = None


class PagesCreateProjectData(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_name: str
    source_type: Literal["github", "direct-upload"]
    repo_owner: str | None = None
    repo_name: str | None = None
    production_branch: str = "main"
    project_id: str | None = None
    pages_subdomain: str | None = None
    already_existed: bool = False
    created_now: bool = False


class PagesCreateProjectEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["0.1.0"] = SCHEMA_VERSION
    status: EnvelopeStatus
    data: PagesCreateProjectData
    provenance: dict[str, ProviderRunMetadata] = Field(default_factory=dict)
    error: PagesCreateProjectError | None = None

    @model_validator(mode="after")
    def _v(self) -> PagesCreateProjectEnvelope:
        return validate_status_consistency(self)  # type: ignore[return-value]


def _map_cf_create_error(result: CfResult) -> PagesCreateProjectError:
    """Map CF-side failures during create-project to closed-enum codes.

    Three codes worth surfacing distinctly from the generic _cf_classify_error
    pipeline because they have specific operator-actionable suggestions:
      8000011  CF Pages Git installation broken — surface install URL
      8000007  Project not found (used as a not-yet-created signal elsewhere,
                 but here means CF couldn't find the GitHub repo)
      409 / "already exists" → project_already_exists
    """
    if result.error_code == 8000011:
        return PagesCreateProjectError(
            code="github_app_not_installed",
            message=result.error_message or "Cloudflare Pages Git installation has an internal issue.",
            suggestion=(
                "The Cloudflare Pages GitHub App needs to be installed AND OAuth-bound to your CF account. "
                "Install alone is not enough — the dashboard OAuth handshake is the load-bearing step. "
                "Quickest path (verified): dash.cloudflare.com → Compute → Workers & Pages → Create application "
                "→ Continue with GitHub → connect any repo, then close the tab without finishing the create. "
                "Full walkthrough in .claude/skills/mb-site/references/cloudflare-pages-link.md. "
                f"Direct App install URL (use after the first handshake): {_CF_GITHUB_APP_INSTALL_URL}."
            ),
        )

    err_msg = (result.error_message or "").lower()
    if result.status_code == 409 or "already exists" in err_msg:
        return PagesCreateProjectError(
            code="project_already_exists",
            message=result.error_message or "A Pages project with this name already exists in the account.",
            suggestion="Pick a different project name, or query the existing project with GET /pages/projects/{name}.",
        )

    if "not found" in err_msg and ("repo" in err_msg or "repository" in err_msg):
        return PagesCreateProjectError(
            code="repo_not_found",
            message=result.error_message or "Cloudflare could not access the named GitHub repo.",
            suggestion=(
                "Verify the owner and repo_name; confirm the Cloudflare Pages GitHub App has access to "
                "this repo (it may be installed on the account but with 'Only select repositories' "
                "configured to exclude it)."
            ),
        )

    code, suggestion = _cf_classify_error(result)
    if code in ("cf_unauthenticated", "cf_rate_limited", "network_timeout"):
        return PagesCreateProjectError(
            code=code,  # type: ignore[arg-type]
            message=result.error_message or code,
            suggestion=suggestion,
        )
    return PagesCreateProjectError(
        code="cf_request_failed",
        message=result.error_message or "Cloudflare Pages create-project request failed.",
        suggestion=suggestion,
    )


def _existing_project_source_matches(
    payload: dict, source_type: str, repo_owner: str | None, repo_name: str | None, branch: str
) -> bool:
    """Return True if an existing project's source config matches what we'd create."""
    src = payload.get("source") or {}
    if not isinstance(src, dict):
        return source_type == "direct-upload" and src is None
    if src.get("type") != source_type:
        return False
    if source_type == "direct-upload":
        return True
    cfg = src.get("config") or {}
    return (
        cfg.get("owner") == repo_owner
        and cfg.get("repo_name") == repo_name
        and cfg.get("production_branch") == branch
    )


@click.group()
def cli() -> None:
    """pages.py — Cloudflare Pages operations atom."""


@cli.command("create-project")
@click.argument("project_name")
@click.option(
    "--repo-owner",
    default=None,
    help="GitHub owner (user or org) for source.type=github. Required unless --source=direct-upload.",
)
@click.option(
    "--repo-name",
    default=None,
    help="GitHub repo name for source.type=github. Required unless --source=direct-upload.",
)
@click.option(
    "--branch",
    default="main",
    show_default=True,
    help="Production branch.",
)
@click.option(
    "--source",
    "source_type",
    type=click.Choice(["github", "direct-upload"]),
    default="github",
    show_default=True,
    help="Source binding. Default github = git auto-deploy. Use direct-upload only for CI/restricted environments.",
)
@click.option(
    "--account-id",
    default=None,
    help="Cloudflare account ID. Defaults to CF_ACCOUNT_ID from the environment.",
)
def create_project(
    project_name: str,
    repo_owner: str | None,
    repo_name: str | None,
    branch: str,
    source_type: str,
    account_id: str | None,
) -> None:
    """Create a Cloudflare Pages project. Default source.type=github so git push auto-deploys.

    Idempotent: if a project with this name already exists with matching source config,
    returns ok with `already_existed: true`. Mismatched source returns project_source_mismatch.
    """
    project_name = project_name.strip().lower()
    branch = branch.strip()
    repo_owner = (repo_owner or "").strip() or None
    repo_name = (repo_name or "").strip() or None
    provenance: dict[str, ProviderRunMetadata] = {}

    if not _PROJECT_RE.match(project_name):
        env = PagesCreateProjectEnvelope(
            status="degraded",
            data=PagesCreateProjectData(project_name=project_name, source_type=source_type),  # type: ignore[arg-type]
            error=PagesCreateProjectError(
                code="invalid_project_name",
                message=f"Project name {project_name!r} is not a valid Cloudflare Pages project name.",
                suggestion="Use 2–58 chars: lowercase letters, digits, dashes; no leading/trailing dash.",
            ),
        )
        sys.exit(emit(env))

    if source_type == "github":
        if not repo_owner or not _GH_OWNER_RE.match(repo_owner):
            env = PagesCreateProjectEnvelope(
                status="degraded",
                data=PagesCreateProjectData(
                    project_name=project_name, source_type=source_type, repo_owner=repo_owner  # type: ignore[arg-type]
                ),
                error=PagesCreateProjectError(
                    code="invalid_repo_owner",
                    message=f"--repo-owner {repo_owner!r} is missing or not a valid GitHub login.",
                    suggestion="Pass --repo-owner with the GitHub user or org login that owns the repo.",
                ),
            )
            sys.exit(emit(env))
        if not repo_name or not _GH_REPO_RE.match(repo_name):
            env = PagesCreateProjectEnvelope(
                status="degraded",
                data=PagesCreateProjectData(
                    project_name=project_name, source_type=source_type, repo_owner=repo_owner, repo_name=repo_name  # type: ignore[arg-type]
                ),
                error=PagesCreateProjectError(
                    code="invalid_repo_name",
                    message=f"--repo-name {repo_name!r} is missing or not a valid GitHub repo name.",
                    suggestion="Pass --repo-name with the bare repo name (no owner prefix, no .git suffix).",
                ),
            )
            sys.exit(emit(env))

    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    if not token:
        env = PagesCreateProjectEnvelope(
            status="degraded",
            data=PagesCreateProjectData(project_name=project_name, source_type=source_type),  # type: ignore[arg-type]
            error=PagesCreateProjectError(
                code="cf_unauthenticated",
                message="CLOUDFLARE_API_TOKEN not set.",
                suggestion="Store a token with Cloudflare Pages:Edit using `mb connect cloudflare`, then run this through `mb connect exec cloudflare -- <command>`. " + OWNER_HANDOFF,
            ),
        )
        sys.exit(emit(env))

    account_id = (account_id or os.environ.get("CF_ACCOUNT_ID") or "").strip()
    if not account_id:
        env = PagesCreateProjectEnvelope(
            status="degraded",
            data=PagesCreateProjectData(project_name=project_name, source_type=source_type),  # type: ignore[arg-type]
            error=PagesCreateProjectError(
                code="cf_account_id_missing",
                message="No Cloudflare account ID supplied.",
                suggestion="Pass --account-id, or set CF_ACCOUNT_ID for this command; it is not a secret.",
            ),
        )
        sys.exit(emit(env))

    # Idempotency check: GET the project first. 404 → fall through to create.
    log(f"Checking whether Pages project {project_name} already exists...")
    lookup = _cf_call("GET", f"/accounts/{account_id}/pages/projects/{project_name}", token)
    provenance["cf_pages_project_lookup"] = ProviderRunMetadata(
        status="ok" if lookup.ok else ("not_configured" if lookup.status_code == 404 else "failed"),
        latency_ms=lookup.latency_ms,
        error=None if lookup.ok else (lookup.error_message or "unknown"),
        provider_version="cloudflare-api-v4",
    )

    if lookup.ok:
        existing = lookup.payload if isinstance(lookup.payload, dict) else {}
        if _existing_project_source_matches(existing, source_type, repo_owner, repo_name, branch):
            log(f"Project exists with matching source config — idempotent ok.")
            env = PagesCreateProjectEnvelope(
                status="ok",
                data=PagesCreateProjectData(
                    project_name=project_name,
                    source_type=source_type,  # type: ignore[arg-type]
                    repo_owner=repo_owner,
                    repo_name=repo_name,
                    production_branch=branch,
                    project_id=existing.get("id"),
                    pages_subdomain=existing.get("subdomain"),
                    already_existed=True,
                    created_now=False,
                ),
                provenance=provenance,
            )
            sys.exit(emit(env))

        # Source mismatch: don't silently change. Surface for the operator.
        existing_source = (existing.get("source") or {}).get("type") or "direct-upload"
        env = PagesCreateProjectEnvelope(
            status="degraded",
            data=PagesCreateProjectData(
                project_name=project_name,
                source_type=source_type,  # type: ignore[arg-type]
                repo_owner=repo_owner,
                repo_name=repo_name,
                production_branch=branch,
                project_id=existing.get("id"),
                pages_subdomain=existing.get("subdomain"),
                already_existed=True,
                created_now=False,
            ),
            provenance=provenance,
            error=PagesCreateProjectError(
                code="project_source_mismatch",
                message=(
                    f"Project {project_name!r} exists with source.type={existing_source!r}, "
                    f"but caller requested {source_type!r} with owner={repo_owner}/{repo_name} "
                    f"branch={branch}."
                ),
                suggestion=(
                    "Direct-upload projects cannot be migrated via PATCH (CF code 8000069). "
                    "To switch source, delete the project and re-create with the desired source. "
                    "Note: deleting unbinds any custom domain, which would need re-attachment via set-domain."
                ),
            ),
        )
        sys.exit(emit(env))

    if lookup.status_code != 404:
        # Lookup failed for a reason other than 404. Surface that error.
        env = PagesCreateProjectEnvelope(
            status="degraded",
            data=PagesCreateProjectData(project_name=project_name, source_type=source_type),  # type: ignore[arg-type]
            provenance=provenance,
            error=_map_cf_create_error(lookup),
        )
        sys.exit(emit(env))

    # 404 → project does not exist. Create it.
    body: dict = {"name": project_name, "production_branch": branch}
    if source_type == "github":
        body["source"] = {
            "type": "github",
            "config": {
                "owner": repo_owner,
                "repo_name": repo_name,
                "production_branch": branch,
            },
        }
    else:
        # direct-upload: omit source field entirely (CF defaults to direct-upload)
        pass

    log(f"Creating Pages project {project_name} (source={source_type})...")
    create = _cf_call("POST", f"/accounts/{account_id}/pages/projects", token, json_body=body)
    provenance["cf_pages_project_create"] = ProviderRunMetadata(
        status="ok" if create.ok else "failed",
        latency_ms=create.latency_ms,
        error=None if create.ok else (create.error_message or "unknown"),
        provider_version="cloudflare-api-v4",
    )
    if not create.ok:
        env = PagesCreateProjectEnvelope(
            status="degraded",
            data=PagesCreateProjectData(
                project_name=project_name,
                source_type=source_type,  # type: ignore[arg-type]
                repo_owner=repo_owner,
                repo_name=repo_name,
                production_branch=branch,
            ),
            provenance=provenance,
            error=_map_cf_create_error(create),
        )
        sys.exit(emit(env))

    payload = create.payload if isinstance(create.payload, dict) else {}
    env = PagesCreateProjectEnvelope(
        status="ok",
        data=PagesCreateProjectData(
            project_name=project_name,
            source_type=source_type,  # type: ignore[arg-type]
            repo_owner=repo_owner,
            repo_name=repo_name,
            production_branch=branch,
            project_id=payload.get("id"),
            pages_subdomain=payload.get("subdomain"),
            already_existed=False,
            created_now=True,
        ),
        provenance=provenance,
    )
    sys.exit(emit(env))


@cli.command("set-domain")
@click.argument("project_name")
@click.argument("domain")
@click.option(
    "--account-id",
    default=None,
    help="Cloudflare account ID. Defaults to CF_ACCOUNT_ID from the environment.",
)
@click.option(
    "--timeout-seconds",
    default=180,
    show_default=True,
    type=int,
    help="Max wait for custom-domain SSL/domain status to become active.",
)
@click.option(
    "--skip-poll",
    is_flag=True,
    help="Attach the domain but skip polling for active SSL/domain status.",
)
def set_domain(
    project_name: str,
    domain: str,
    account_id: str | None,
    timeout_seconds: int,
    skip_poll: bool,
) -> None:
    """Attach DOMAIN to an existing Cloudflare Pages PROJECT_NAME."""
    project_name = project_name.strip().lower()
    domain = domain.strip().lower().rstrip(".")
    provenance: dict[str, ProviderRunMetadata] = {}

    if not _PROJECT_RE.match(project_name):
        env = PagesSetDomainEnvelope(
            status="degraded",
            data=PagesSetDomainData(project_name=project_name, domain=domain),
            error=PagesSetDomainError(
                code="invalid_project_name",
                message=f"Project name {project_name!r} is not a valid Cloudflare Pages project name.",
                suggestion="Pass the exact lowercase Pages project name, e.g. 'thelastbill'.",
            ),
        )
        sys.exit(emit(env))

    if not _DOMAIN_RE.match(domain):
        env = PagesSetDomainEnvelope(
            status="degraded",
            data=PagesSetDomainData(project_name=project_name, domain=domain),
            error=PagesSetDomainError(
                code="invalid_domain",
                message=f"Domain {domain!r} doesn't look like a valid apex or subdomain.",
                suggestion="Pass a domain like 'example.com' with no scheme or path.",
            ),
        )
        sys.exit(emit(env))

    token = os.environ.get("CLOUDFLARE_API_TOKEN")
    if not token:
        env = PagesSetDomainEnvelope(
            status="degraded",
            data=PagesSetDomainData(project_name=project_name, domain=domain),
            error=PagesSetDomainError(
                code="cf_unauthenticated",
                message="CLOUDFLARE_API_TOKEN not set.",
                suggestion="Store a token with Cloudflare Pages:Edit using `mb connect cloudflare`, then run this through `mb connect exec cloudflare -- <command>`. " + OWNER_HANDOFF,
            ),
        )
        sys.exit(emit(env))

    account_id = (account_id or os.environ.get("CF_ACCOUNT_ID") or "").strip()
    if not account_id:
        env = PagesSetDomainEnvelope(
            status="degraded",
            data=PagesSetDomainData(project_name=project_name, domain=domain),
            error=PagesSetDomainError(
                code="cf_account_id_missing",
                message="No Cloudflare account ID supplied.",
                suggestion="Pass --account-id, or set CF_ACCOUNT_ID for this command; it is not a secret.",
            ),
        )
        sys.exit(emit(env))

    log(f"Looking up Cloudflare Pages project {project_name}...")
    project = _cf_call("GET", f"/accounts/{account_id}/pages/projects/{project_name}", token)
    provenance["cf_pages_project_lookup"] = _provider_row(project)
    if not project.ok:
        env = PagesSetDomainEnvelope(
            status="degraded",
            data=PagesSetDomainData(project_name=project_name, domain=domain),
            provenance=provenance,
            error=_map_cf_error(project, project_checked=False),
        )
        sys.exit(emit(env))
    project_payload = project.payload if isinstance(project.payload, dict) else {}
    pages_subdomain = project_payload.get("subdomain")
    if not isinstance(pages_subdomain, str) or not pages_subdomain:
        pages_subdomain = f"{project_name}.pages.dev"

    log(f"Checking whether {domain} is already attached...")
    existing = _cf_call(
        "GET",
        f"/accounts/{account_id}/pages/projects/{project_name}/domains/{domain}",
        token,
    )
    provenance["cf_pages_domain_lookup"] = _provider_row(existing)

    already_attached = False
    attached_now = False
    payload: dict | None = None
    dns_record_id: str | None = None
    dns_record_created_now = False

    if existing.ok:
        already_attached = True
        payload = existing.payload if isinstance(existing.payload, dict) else {}
        log(f"Domain already attached: status={payload.get('status')}")
    elif not _is_missing_domain(existing):
        env = PagesSetDomainEnvelope(
            status="degraded",
            data=PagesSetDomainData(project_name=project_name, domain=domain),
            provenance=provenance,
            error=_map_cf_error(existing, project_checked=True),
        )
        sys.exit(emit(env))
    else:
        log(f"Attaching {domain} to Pages project {project_name}...")
        add = _cf_call(
            "POST",
            f"/accounts/{account_id}/pages/projects/{project_name}/domains",
            token,
            json_body={"name": domain},
        )
        provenance["cf_pages_domain_add"] = _provider_row(add)
        if not add.ok:
            err_msg = (add.error_message or "").lower()
            if add.status_code == 409 or "already" in err_msg:
                env = PagesSetDomainEnvelope(
                    status="degraded",
                    data=PagesSetDomainData(project_name=project_name, domain=domain),
                    provenance=provenance,
                    error=PagesSetDomainError(
                        code="domain_already_attached",
                        message=add.error_message or "Domain is already attached to a Pages project.",
                        suggestion="Check the existing Pages custom-domain attachment, then re-run with that project.",
                    ),
                )
                sys.exit(emit(env))
            env = PagesSetDomainEnvelope(
                status="degraded",
                data=PagesSetDomainData(project_name=project_name, domain=domain),
                provenance=provenance,
                error=_map_cf_error(add, project_checked=True),
            )
            sys.exit(emit(env))
        attached_now = True
        payload = add.payload if isinstance(add.payload, dict) else {}

    if (payload or {}).get("status") != "active":
        log(f"Ensuring Cloudflare DNS CNAME {domain} -> {pages_subdomain}...")
        dns_record_id, dns_record_created_now, dns_err = _ensure_pages_dns_record(
            account_id,
            domain,
            pages_subdomain,
            token,
            provenance,
            zone_tag=(payload or {}).get("zone_tag"),
        )
        if dns_err is not None:
            env = PagesSetDomainEnvelope(
                status="degraded",
                data=_domain_payload_to_data(
                    project_name,
                    domain,
                    payload or {},
                    already_attached=already_attached,
                    attached_now=attached_now,
                    poll_seconds=None,
                    pages_subdomain=pages_subdomain,
                    dns_record_id=dns_record_id,
                    dns_record_content=pages_subdomain,
                    dns_record_created_now=dns_record_created_now,
                ),
                provenance=provenance,
                error=dns_err,
            )
            sys.exit(emit(env))

    poll_seconds: int | None = None
    if not skip_poll:
        log(f"Polling Pages custom-domain status for {domain} (timeout {timeout_seconds}s)...")
        payload, poll_seconds, poll_err = _wait_for_domain_active(
            account_id, project_name, domain, token, timeout_seconds, provenance
        )
        if poll_err is not None:
            env = PagesSetDomainEnvelope(
                status="degraded",
                data=_domain_payload_to_data(
                    project_name,
                    domain,
                    payload or {},
                    already_attached=already_attached,
                    attached_now=attached_now,
                    poll_seconds=poll_seconds,
                    pages_subdomain=pages_subdomain,
                    dns_record_id=dns_record_id,
                    dns_record_content=pages_subdomain if dns_record_id else None,
                    dns_record_created_now=dns_record_created_now,
                ),
                provenance=provenance,
                error=poll_err,
            )
            sys.exit(emit(env))

    data = _domain_payload_to_data(
        project_name,
        domain,
        payload or {},
        already_attached=already_attached,
        attached_now=attached_now,
        poll_seconds=poll_seconds,
        pages_subdomain=pages_subdomain,
        dns_record_id=dns_record_id,
        dns_record_content=pages_subdomain if dns_record_id else None,
        dns_record_created_now=dns_record_created_now,
    )
    env = PagesSetDomainEnvelope(status="ok", data=data, provenance=provenance)
    sys.exit(emit(env))


if __name__ == "__main__":
    cli()
