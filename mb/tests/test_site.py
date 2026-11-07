"""``mb site`` paid-traffic readiness checks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mb.cli import app
from mb.init import run as init_run

runner = CliRunner()
REPO_ROOT = Path(__file__).resolve().parents[2]


def _write_conversion(site: Path, payload: dict[str, object]) -> None:
    target = site / ".mainbranch" / "conversion.json"
    target.parent.mkdir(parents=True)
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_html(
    site: Path, *, gtm_id: str = "GTM-ABC1234", events: list[str] | None = None
) -> None:
    event_lines = "\n".join(
        f'window.dataLayer.push({{event: "{event}", mb_event_id: "test"}});'
        for event in (events or [])
    )
    (site / "index.html").write_text(
        f"""<!doctype html>
<html>
<head>
<script>window.dataLayer = window.dataLayer || [];</script>
<script src="https://www.googletagmanager.com/gtm.js?id={gtm_id}"></script>
<script>{event_lines}</script>
</head>
<body>
<noscript><iframe src="https://www.googletagmanager.com/ns.html?id={gtm_id}"></iframe></noscript>
</body>
</html>
""",
        encoding="utf-8",
    )


def _write_dist_html(
    site: Path, *, gtm_id: str = "GTM-ABC1234", events: list[str] | None = None
) -> None:
    (site / "dist").mkdir()
    original = site / "index.html"
    _write_html(site, gtm_id=gtm_id, events=events)
    original.replace(site / "dist" / "index.html")


def test_mb_site_skill_hard_gates_cloudflare_dependent_work() -> None:
    skill = (REPO_ROOT / ".claude" / "skills" / "mb-site" / "SKILL.md").read_text(encoding="utf-8")
    setup = (
        REPO_ROOT / ".claude" / "skills" / "mb-site" / "references" / "minisite-setup.md"
    ).read_text(encoding="utf-8")
    pages_link = (
        REPO_ROOT / ".claude" / "skills" / "mb-site" / "references" / "cloudflare-pages-link.md"
    ).read_text(encoding="utf-8")

    assert "mb connect doctor --json" in skill
    assert "continue read-only" in skill
    assert "--metadata token_type=account --metadata account_id=..." in skill
    assert "`cfat_` account tokens route automatically" in skill
    assert "mb connect doctor --json" in pages_link
    assert "`cfat_` account tokens route automatically" in pages_link
    assert "no buy, DNS, Pages, custom-domain, or deploy calls" in setup
    assert "Main Branch cannot buy domains through `domain.py` yet" in setup


def test_mb_site_business_repo_saves_use_checkpoint_contract() -> None:
    skill = (REPO_ROOT / ".claude" / "skills" / "mb-site" / "SKILL.md").read_text(encoding="utf-8")
    brief = (
        REPO_ROOT / ".claude" / "skills" / "mb-site" / "references" / "minisite-brief.md"
    ).read_text(encoding="utf-8")
    research = (
        REPO_ROOT / ".claude" / "skills" / "mb-site" / "references" / "minisite-research.md"
    ).read_text(encoding="utf-8")
    setup = (
        REPO_ROOT / ".claude" / "skills" / "mb-site" / "references" / "minisite-setup.md"
    ).read_text(encoding="utf-8")
    workflow = (
        REPO_ROOT / ".claude" / "skills" / "mb-site" / "references" / "site-repo-workflow.md"
    ).read_text(encoding="utf-8")

    assert "Business-repo saves use `mb checkpoint`, not raw git commits." in skill
    assert "site repo\ncode commits still use that site's normal git flow" in skill.lower()
    assert 'git commit -m "[lock]' not in brief
    assert "git add decisions/" not in brief
    assert 'mb checkpoint --validate "[decided] minisite brief -- <slug>" --json' in brief
    assert 'mb checkpoint --validate "[drafted] minisite research -- <slug>" --json' in research
    assert 'mb checkpoint --validate "[connected] site repo -- <slug>" --json' in setup
    assert 'mb checkpoint --validate "[connected] site repo -- <slug>" --json' in workflow


def test_site_check_reports_ready_for_operator_review(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "local-file")
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "home"))
    business = tmp_path / "business"
    site = tmp_path / "site"
    init_run(path=str(business), name="Acme")
    site.mkdir()
    (business / "core" / "offer.md").write_text(
        (
            "---\n"
            "gtm_container_id: GTM-ABC1234\n"
            "google_ads_customer_id: '5550100000'\n"
            "consent_posture: standard_tag_consent_reviewed\n"
            "privacy_policy_url: https://example.com/privacy\n"
            "---\n\n"
            "# Offer\n"
        ),
        encoding="utf-8",
    )
    _write_conversion(
        site,
        {
            "kind": "lead_form",
            "url": "https://tally.so/r/example",
            "render": "link_out",
            "primary_conversions": ["mb_lead_submit"],
            "secondary_conversions": ["mb_cta_click", "mb_form_start"],
            "metadata": {"provider": "tally"},
        },
    )
    _write_html(site, events=["mb_cta_click", "mb_form_start", "mb_lead_submit"])

    result = runner.invoke(
        app,
        ["site", "check", str(site), "--business-repo", str(business), "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["state"] == "ready_for_operator_review"
    assert payload["facts"]["expected_events"] == [
        "mb_cta_click",
        "mb_form_start",
        "mb_lead_submit",
    ]
    assert payload["facts"]["provider_state"]["google"]["state"] == "not_connected"
    assert not payload["blocked"]
    assert any(item["kind"] == "operator_approval" for item in payload["manual"])


def test_site_check_inspects_dist_build_output(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "local-file")
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "home"))
    business = tmp_path / "business"
    site = tmp_path / "site"
    init_run(path=str(business), name="Acme")
    site.mkdir()
    (business / "core" / "offer.md").write_text(
        (
            "---\n"
            "gtm_container_id: GTM-ABC1234\n"
            "google_ads_customer_id: '5550100000'\n"
            "consent_posture: standard_tag_consent_reviewed\n"
            "privacy_policy_url: https://example.com/privacy\n"
            "---\n\n"
            "# Offer\n"
        ),
        encoding="utf-8",
    )
    _write_conversion(
        site,
        {
            "kind": "lead_form",
            "url": "https://tally.so/r/example",
            "render": "link_out",
            "primary_conversions": ["mb_lead_submit"],
        },
    )
    _write_dist_html(site, events=["mb_cta_click", "mb_form_start", "mb_lead_submit"])

    result = runner.invoke(
        app,
        ["site", "check", str(site), "--business-repo", str(business), "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["state"] == "ready_for_operator_review"
    assert payload["html"]["html_files"] == ["dist/index.html"]


def test_site_check_reports_astro_launch_instrumentation_widgets(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "local-file")
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "home"))
    business = tmp_path / "business"
    site = tmp_path / "astro-site"
    init_run(path=str(business), name="Acme")
    (site / "dist").mkdir(parents=True)
    (business / "core" / "offer.md").write_text(
        (
            "---\n"
            "gtm_container_id: GTM-ABC1234\n"
            "ga4_measurement_id: G-ABC123DEF\n"
            "meta_pixel_id: '123456789012345'\n"
            "google_ads_customer_id: '5550100000'\n"
            "consent_posture: standard_tag_consent_reviewed\n"
            "privacy_policy_url: https://example.com/privacy\n"
            "---\n\n"
            "# Offer\n"
        ),
        encoding="utf-8",
    )
    _write_conversion(
        site,
        {
            "kind": "appointment_booking",
            "url": "https://calendly.com/acme/demo",
            "render": "link_out",
            "primary_conversions": ["mb_booked_call"],
        },
    )
    (site / "dist" / "index.html").write_text(
        """<!doctype html>
<html>
<head>
<script>window.dataLayer = window.dataLayer || [];</script>
<script src="https://www.googletagmanager.com/gtm.js?id=GTM-ABC1234"></script>
<script async src="https://www.googletagmanager.com/gtag/js?id=G-ABC123DEF"></script>
<script>
fbq('init', '123456789012345');
window.dataLayer.push({event: "mb_calendar_click", mb_event_id: "test"});
window.dataLayer.push({event: "mb_booked_call", mb_event_id: "test"});
</script>
<script src="https://assets.calendly.com/assets/external/widget.js"></script>
<script src="https://js.hs-scripts.com/123456.js"></script>
</head>
<body>
<noscript><iframe src="https://www.googletagmanager.com/ns.html?id=GTM-ABC1234"></iframe></noscript>
<div class="calendly-inline-widget" data-url="https://calendly.com/acme/demo"></div>
<form action="/thanks"><button>Book</button></form>
</body>
</html>
""",
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["site", "check", str(site), "--business-repo", str(business), "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    instrumentation = payload["facts"]["instrumentation"]
    assert instrumentation["declared"]["ga4_measurement_id"] is True
    assert instrumentation["declared"]["meta_pixel_id"] is True
    assert instrumentation["detected"]["ga4_ids"] == ["G-ABC123DEF"]
    assert instrumentation["detected"]["meta_pixel_ids"] == ["123456789012345"]
    assert instrumentation["detected"]["booking_widgets"] == ["calendly"]
    assert instrumentation["detected"]["crm_widgets"] == ["hubspot"]
    assert instrumentation["detected"]["form_count"] == 1
    assert instrumentation["conversion_surface"]["state"] == "planned"
    assert any(item["kind"] == "form_booking_smoke" for item in payload["manual"])


def test_site_check_classifies_detectable_widget_without_conversion_plan(tmp_path: Path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text(
        """<!doctype html>
<html>
<body>
<script src="https://js.hsforms.net/forms/embed/v2.js"></script>
<script>hbspt.forms.create({region: "na1", portalId: "123", formId: "abc"});</script>
<form action="https://example.com/private-lead?token=secret"><button>Submit</button></form>
</body>
</html>
""",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["site", "check", str(site), "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    instrumentation = payload["facts"]["instrumentation"]
    assert instrumentation["conversion_surface"]["state"] == "detectable_unplanned"
    assert instrumentation["conversion_surface"]["detected_only"] is True
    assert instrumentation["detected"]["crm_widgets"] == ["hubspot"]
    assert instrumentation["detected"]["form_actions"] == ["https://example.com/private-lead"]
    conversion_surface = next(
        item for item in payload["evidence"] if item["kind"] == "conversion_surface"
    )
    assert conversion_surface["state"] == "manual"


def test_site_check_uses_source_link_when_business_repo_is_omitted(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "local-file")
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "home"))
    business = tmp_path / "business"
    site = tmp_path / "site"
    init_run(path=str(business), name="Acme")
    site.mkdir()
    (business / "core" / "offer.md").write_text(
        (
            "---\n"
            "gtm_container_id: GTM-ABC1234\n"
            "google_ads_customer_id: '5550100000'\n"
            "consent_posture: standard_tag_consent_reviewed\n"
            "privacy_policy_url: https://example.com/privacy\n"
            "---\n\n"
            "# Offer\n"
        ),
        encoding="utf-8",
    )
    _write_conversion(
        site,
        {
            "kind": "lead_form",
            "url": "https://tally.so/r/example",
            "render": "link_out",
            "primary_conversions": ["mb_lead_submit"],
        },
    )
    (site / ".mainbranch" / "source.json").write_text(
        json.dumps(
            {
                "business_repo": str(business),
                "offer_path": "core/offer.md",
                "campaign_path": "campaigns/smoke.md",
            }
        ),
        encoding="utf-8",
    )
    _write_html(site, events=["mb_cta_click", "mb_form_start", "mb_lead_submit"])

    result = runner.invoke(app, ["site", "check", str(site), "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["business_repo"] == str(business.resolve())
    assert payload["source"]["offer_path"] == "core/offer.md"
    assert any(item["kind"] == "site_source_link" for item in payload["evidence"])


def test_site_check_uses_child_descriptor_relative_hub_when_source_link_is_omitted(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "local-file")
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "home"))
    business = tmp_path / "business"
    site = tmp_path / "site"
    init_run(path=str(business), name="Acme")
    site.mkdir()
    (business / "core" / "offer.md").write_text(
        (
            "---\n"
            "gtm_container_id: GTM-ABC1234\n"
            "google_ads_customer_id: '5550100000'\n"
            "consent_posture: standard_tag_consent_reviewed\n"
            "privacy_policy_url: https://example.com/privacy\n"
            "---\n\n"
            "# Offer\n"
        ),
        encoding="utf-8",
    )
    _write_conversion(
        site,
        {
            "kind": "lead_form",
            "url": "https://tally.so/r/example",
            "render": "link_out",
            "primary_conversions": ["mb_lead_submit"],
        },
    )
    (site / ".mainbranch" / "repo.json").write_text(
        json.dumps(
            {
                "schema": "mb.child_repo.v0",
                "role": "site",
                "display_name": "Acme site",
                "github_owner": "example-co",
                "repo_name": "acme-site",
                "safe_purpose": "Public paid-traffic site for Acme.",
                "parent": {
                    "display_name": "Acme",
                    "github_owner": "example-co",
                    "repo_name": "acme",
                    "remote": "github:example-co/acme",
                    "local_checkout": "../business",
                },
                "linked": {
                    "offers": ["core/offer.md"],
                    "pushes": ["pushes/2026-05-06-paid-minisite/push.md"],
                    "bets": ["bets/2026-05-01-acme-offer.md"],
                    "decisions": ["decisions/2026-05-01-site.md"],
                },
                "return_to_hub_command": "cd ../business",
                "safe_to_share": True,
            }
        ),
        encoding="utf-8",
    )
    _write_html(site, events=["mb_cta_click", "mb_form_start", "mb_lead_submit"])

    result = runner.invoke(app, ["site", "check", str(site), "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["business_repo"] == str(business.resolve())
    assert payload["source"] == {}
    assert payload["child_descriptor"]["role"] == "site"
    assert payload["child_descriptor"]["parent"]["resolved_local_checkout"] == str(
        business.resolve()
    )
    assert payload["child_descriptor"]["linked"]["pushes"] == [
        "pushes/2026-05-06-paid-minisite/push.md"
    ]
    evidence = {item["kind"]: item for item in payload["evidence"]}
    assert evidence["site_source_link"]["state"] == "passed"
    assert evidence["child_repo_descriptor"]["state"] == "passed"


def test_site_check_blocks_child_descriptor_with_absolute_local_checkout(
    tmp_path: Path,
) -> None:
    business = tmp_path / "business"
    site = tmp_path / "site"
    init_run(path=str(business), name="Acme")
    site.mkdir()
    _write_conversion(
        site,
        {
            "kind": "lead_form",
            "gtm_container_id": "GTM-ABC1234",
            "google_ads_customer_id": "5550100000",
            "primary_conversions": ["mb_lead_submit"],
            "metadata": {
                "consent_posture": "standard_tag_consent_reviewed",
                "privacy_policy_url": "https://example.com/privacy",
            },
        },
    )
    (site / ".mainbranch" / "repo.json").write_text(
        json.dumps(
            {
                "schema": "mb.child_repo.v0",
                "role": "site",
                "parent": {
                    "github_owner": "example-co",
                    "repo_name": "acme",
                    "local_checkout": str(business),
                },
            }
        ),
        encoding="utf-8",
    )
    _write_html(site, events=["mb_cta_click", "mb_form_start", "mb_lead_submit"])

    result = runner.invoke(app, ["site", "check", str(site), "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["business_repo"] == ""
    descriptor_evidence = next(
        item for item in payload["evidence"] if item["kind"] == "child_repo_descriptor"
    )
    assert descriptor_evidence["state"] == "blocked"
    assert "must be relative" in descriptor_evidence["summary"]


def test_site_check_accepts_child_descriptor_with_explicit_business_repo(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "local-file")
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "home"))
    business = tmp_path / "business"
    site = tmp_path / "site"
    init_run(path=str(business), name="Acme")
    site.mkdir()
    (business / "core" / "offer.md").write_text(
        (
            "---\n"
            "gtm_container_id: GTM-ABC1234\n"
            "google_ads_customer_id: '5550100000'\n"
            "consent_posture: standard_tag_consent_reviewed\n"
            "privacy_policy_url: https://example.com/privacy\n"
            "---\n\n"
            "# Offer\n"
        ),
        encoding="utf-8",
    )
    _write_conversion(
        site,
        {
            "kind": "lead_form",
            "url": "https://tally.so/r/example",
            "render": "link_out",
            "primary_conversions": ["mb_lead_submit"],
        },
    )
    (site / ".mainbranch" / "repo.json").write_text(
        json.dumps(
            {
                "schema": "mb.child_repo.v0",
                "role": "site",
                "display_name": "Acme site",
                "github_owner": "example-co",
                "repo_name": "acme-site",
                "parent": {
                    "display_name": "Acme",
                    "github_owner": "example-co",
                    "repo_name": "acme",
                    "remote": "github:example-co/acme",
                },
                "linked": {"offers": ["core/offer.md"]},
                "safe_to_share": True,
            }
        ),
        encoding="utf-8",
    )
    _write_html(site, events=["mb_cta_click", "mb_form_start", "mb_lead_submit"])

    result = runner.invoke(
        app,
        ["site", "check", str(site), "--business-repo", str(business), "--json"],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["business_repo"] == str(business.resolve())
    evidence = {item["kind"]: item for item in payload["evidence"]}
    assert evidence["site_source_link"]["state"] == "passed"
    assert payload["child_descriptor"]["parent"]["remote"] == "github:example-co/acme"


def test_site_check_blocks_missing_gtm_noscript_event_and_consent(tmp_path: Path) -> None:
    business = tmp_path / "business"
    site = tmp_path / "site"
    init_run(path=str(business), name="Acme")
    site.mkdir()
    (business / "core" / "offer.md").write_text(
        "---\ngtm_container_id: GTM-XXXXXXX\n---\n\n# Offer\n",
        encoding="utf-8",
    )
    _write_conversion(
        site,
        {"kind": "appointment_booking", "url": "https://cal.com/example", "render": "link_out"},
    )
    (site / "index.html").write_text(
        '<script src="https://www.googletagmanager.com/gtm.js?id=GTM-XXXXXXX"></script>',
        encoding="utf-8",
    )

    result = runner.invoke(
        app,
        ["site", "check", str(site), "--business-repo", str(business), "--json"],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["state"] == "blocked"
    blocked_kinds = {item["kind"] for item in payload["blocked"]}
    assert "gtm_container" in blocked_kinds
    assert "static_html" in blocked_kinds
    assert "data_layer_events" in blocked_kinds
    assert "consent_privacy" in blocked_kinds


def test_site_check_keeps_conversion_and_source_link_evidence_distinct(tmp_path: Path) -> None:
    site = tmp_path / "site"
    site.mkdir()

    result = runner.invoke(app, ["site", "check", str(site), "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    evidence_by_kind: dict[str, list[dict[str, object]]] = {}
    for item in payload["evidence"]:
        evidence_by_kind.setdefault(item["kind"], []).append(item)
    assert evidence_by_kind["conversion_plan"] == [
        {
            "kind": "conversion_plan",
            "state": "missing",
            "summary": ".mainbranch/conversion.json is missing.",
        }
    ]
    assert evidence_by_kind["site_source_link"] == [
        {
            "kind": "site_source_link",
            "state": "missing",
            "summary": ".mainbranch/source.json is missing.",
        }
    ]


def test_site_check_blocks_wrong_gtm_loader_id(tmp_path: Path) -> None:
    business = tmp_path / "business"
    site = tmp_path / "site"
    init_run(path=str(business), name="Acme")
    site.mkdir()
    (business / "core" / "offer.md").write_text(
        (
            "---\n"
            "gtm_container_id: GTM-ABC1234\n"
            "consent_posture: standard_tag_consent_reviewed\n"
            "privacy_policy_url: https://example.com/privacy\n"
            "---\n\n"
            "# Offer\n"
        ),
        encoding="utf-8",
    )
    _write_conversion(
        site,
        {"kind": "lead_form", "url": "https://tally.so/r/example", "render": "link_out"},
    )
    _write_html(site, gtm_id="GTM-OTHER1", events=["mb_cta_click", "mb_form_start"])

    result = runner.invoke(
        app,
        ["site", "check", str(site), "--business-repo", str(business), "--json"],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    static_html = next(item for item in payload["evidence"] if item["kind"] == "static_html")
    assert static_html["state"] == "blocked"
    assert "head script" in static_html["summary"]
    assert "body noscript" in static_html["summary"]


def test_site_check_skips_template_gtm_config_when_no_container_is_declared(tmp_path: Path) -> None:
    site = tmp_path / "site"
    site.mkdir()
    _write_conversion(
        site,
        {"kind": "lead_form", "url": "https://tally.so/r/example", "render": "link_out"},
    )
    _write_html(site, events=["mb_cta_click", "mb_form_start"])

    result = runner.invoke(app, ["site", "check", str(site), "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert not any(item["kind"] == "template_gtm_config" for item in payload["evidence"])


def test_status_includes_measurement_summary_when_conversion_plan_exists(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("mb.status._which", lambda name: "")
    repo = tmp_path / "business"
    init_run(path=str(repo), name="Acme")
    (repo / "core" / "offer.md").write_text(
        (
            "---\n"
            "gtm_container_id: GTM-ABC1234\n"
            "google_ads_customer_id: '5550100000'\n"
            "consent_posture: standard_tag_consent_reviewed\n"
            "privacy_policy_url: https://example.com/privacy\n"
            "---\n\n"
            "# Offer\n"
        ),
        encoding="utf-8",
    )
    _write_conversion(
        repo,
        {
            "kind": "lead_form",
            "url": "https://tally.so/r/example",
            "render": "link_out",
            "primary_conversions": ["mb_lead_submit"],
        },
    )
    _write_html(repo, events=["mb_cta_click", "mb_form_start", "mb_lead_submit"])

    result = runner.invoke(app, ["status", str(repo), "--json", "--peek"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["measurement"]["available"] is True
    assert payload["measurement"]["state"] == "ready_for_operator_review"
    assert payload["measurement"]["facts"]["primary_conversions"] == ["mb_lead_submit"]
    assert (
        payload["measurement"]["facts"]["instrumentation"]["conversion_surface"]["state"]
        == "planned"
    )


def test_status_follows_business_repo_site_record_for_measurement(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("mb.status._which", lambda name: "")
    business = tmp_path / "business"
    site = tmp_path / "site"
    init_run(path=str(business), name="Acme")
    site.mkdir()
    (business / "core" / "offer.md").write_text(
        (
            "---\n"
            "gtm_container_id: GTM-ABC1234\n"
            "google_ads_customer_id: '5550100000'\n"
            "consent_posture: standard_tag_consent_reviewed\n"
            "privacy_policy_url: https://example.com/privacy\n"
            "---\n\n"
            "# Offer\n"
        ),
        encoding="utf-8",
    )
    (business / "pushes" / "paid-site.md").write_text(
        f"---\nsite_repo_path: {site}\n---\n\n# Paid Site\n",
        encoding="utf-8",
    )
    _write_conversion(
        site,
        {
            "kind": "lead_form",
            "url": "https://tally.so/r/example",
            "render": "link_out",
            "primary_conversions": ["mb_lead_submit"],
        },
    )
    _write_html(site, events=["mb_cta_click", "mb_form_start", "mb_lead_submit"])

    result = runner.invoke(app, ["status", str(business), "--json", "--peek"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["measurement"]["available"] is True
    assert payload["measurement"]["site_repo"] == str(site.resolve())
    assert payload["measurement"]["business_repo"] == str(business.resolve())
    assert payload["measurement"]["source_record"] == "pushes/paid-site.md"


def test_site_check_reports_repo_role_site_from_signals(tmp_path: Path) -> None:
    from mb import site as site_mod

    site = tmp_path / "rankedhvac"
    site.mkdir()
    # conversion.json is a site signal; no repo.json role declared.
    _write_conversion(site, {"kind": "lead_form", "url": "https://example.com"})

    result = site_mod.check(str(site))

    assert result["facts"]["repo_role"] == "site"
    role_ev = next(item for item in result["evidence"] if item["kind"] == "repo_role")
    assert role_ev["state"] == "passed"


def test_site_check_flags_non_site_repo_role(tmp_path: Path) -> None:
    from mb import site as site_mod

    site = tmp_path / "ledger"
    (site / ".mainbranch").mkdir(parents=True)
    (site / ".mainbranch" / "repo.json").write_text(
        json.dumps({"schema": "mb.child_repo.v0", "role": "finance"}), encoding="utf-8"
    )

    result = site_mod.check(str(site))

    assert result["facts"]["repo_role"] == "finance"
    role_ev = next(item for item in result["evidence"] if item["kind"] == "repo_role")
    assert role_ev["state"] == "manual"
    assert "not a site" in role_ev["summary"]


def test_site_check_flags_missing_repo_role(tmp_path: Path) -> None:
    from mb import site as site_mod

    site = tmp_path / "bare"
    site.mkdir()

    result = site_mod.check(str(site))

    assert result["facts"]["repo_role"] == ""
    role_ev = next(item for item in result["evidence"] if item["kind"] == "repo_role")
    assert role_ev["state"] == "manual"
    assert "no topology role" in role_ev["summary"]


def _seed_site_for_identity(site: Path) -> None:
    _write_conversion(
        site,
        {
            "kind": "lead_form",
            "url": "https://tally.so/r/example",
            "render": "link_out",
            "primary_conversions": ["mb_lead_submit"],
        },
    )
    _write_html(site, events=["mb_cta_click", "mb_form_start", "mb_lead_submit"])


def _write_business_descriptor(business: Path, owner: str, repo: str) -> None:
    (business / ".mainbranch").mkdir(parents=True, exist_ok=True)
    (business / ".mainbranch" / "repo.json").write_text(
        json.dumps(
            {
                "schema": "mb.child_repo.v0",
                "role": "business",
                "display_name": repo,
                "github_owner": owner,
                "repo_name": repo,
            }
        ),
        encoding="utf-8",
    )


def test_site_check_blocks_forked_descriptor_github_identity_leak(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "local-file")
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "home"))
    business = tmp_path / "business"
    site = tmp_path / "site"
    init_run(path=str(business), name="Acme")
    _write_business_descriptor(business, "acme-co", "acme")
    site.mkdir()
    _seed_site_for_identity(site)
    # Site carries a FORKED descriptor pointing at a different business.
    (site / ".mainbranch" / "repo.json").write_text(
        json.dumps(
            {
                "schema": "mb.child_repo.v0",
                "role": "site",
                "display_name": "Acme site",
                "parent": {
                    "display_name": "Previous Co",
                    "github_owner": "previous-co",
                    "repo_name": "previous-biz",
                    "remote": "github:previous-co/previous-biz",
                },
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app, ["site", "check", str(site), "--business-repo", str(business), "--json"]
    )
    payload = json.loads(result.stdout)
    evidence = {item["kind"]: item for item in payload["evidence"]}
    assert "descriptor_identity" in evidence
    assert evidence["descriptor_identity"]["state"] == "blocked"
    assert payload["state"] == "blocked"


def test_site_check_passes_descriptor_identity_when_business_matches(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "local-file")
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "home"))
    business = tmp_path / "business"
    site = tmp_path / "site"
    init_run(path=str(business), name="Acme")
    _write_business_descriptor(business, "acme-co", "acme")
    site.mkdir()
    _seed_site_for_identity(site)
    (site / ".mainbranch" / "repo.json").write_text(
        json.dumps(
            {
                "schema": "mb.child_repo.v0",
                "role": "site",
                "display_name": "Acme site",
                "parent": {
                    "display_name": "Acme",
                    "github_owner": "acme-co",
                    "repo_name": "acme",
                    "remote": "github:acme-co/acme",
                },
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app, ["site", "check", str(site), "--business-repo", str(business), "--json"]
    )
    payload = json.loads(result.stdout)
    evidence = {item["kind"]: item for item in payload["evidence"]}
    assert evidence["descriptor_identity"]["state"] == "passed"


def test_site_check_blocks_forked_descriptor_parent_path_leak(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "local-file")
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "home"))
    business = tmp_path / "business"
    other = tmp_path / "other-business"
    site = tmp_path / "site"
    init_run(path=str(business), name="Acme")
    other.mkdir()
    site.mkdir()
    _seed_site_for_identity(site)
    # parent.local_checkout resolves to a DIFFERENT business than --business-repo.
    (site / ".mainbranch" / "repo.json").write_text(
        json.dumps(
            {
                "schema": "mb.child_repo.v0",
                "role": "site",
                "display_name": "Acme site",
                "parent": {
                    "display_name": "Other",
                    "local_checkout": "../other-business",
                },
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(
        app, ["site", "check", str(site), "--business-repo", str(business), "--json"]
    )
    payload = json.loads(result.stdout)
    evidence = {item["kind"]: item for item in payload["evidence"]}
    assert evidence["descriptor_identity"]["state"] == "blocked"
    assert payload["state"] == "blocked"


def _set_origin(repo: Path, url: str) -> None:
    import subprocess

    if not (repo / ".git").exists():
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "remote", "remove", "origin"], capture_output=True)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", url], check=True)


def _write_site_descriptor_with_parent(site: Path, owner: str, repo: str) -> None:
    (site / ".mainbranch" / "repo.json").write_text(
        json.dumps(
            {
                "schema": "mb.child_repo.v0",
                "role": "site",
                "display_name": "Acme site",
                "parent": {"github_owner": owner, "repo_name": repo},
            }
        ),
        encoding="utf-8",
    )


def test_site_check_blocks_descriptor_identity_mismatch_via_git_remote(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "local-file")
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "home"))
    business = tmp_path / "business"
    site = tmp_path / "site"
    init_run(path=str(business), name="Acme")
    assert not (business / ".mainbranch" / "repo.json").exists()
    _set_origin(business, "https://github.com/acme-co/acme.git")
    site.mkdir()
    _seed_site_for_identity(site)
    _write_site_descriptor_with_parent(site, "previous-co", "previous-biz")

    result = runner.invoke(
        app, ["site", "check", str(site), "--business-repo", str(business), "--json"]
    )
    payload = json.loads(result.stdout)
    evidence = {item["kind"]: item for item in payload["evidence"]}
    assert evidence["descriptor_identity"]["state"] == "blocked"
    assert "acme-co/acme" in evidence["descriptor_identity"]["summary"]
    assert payload["state"] == "blocked"


def test_site_check_passes_descriptor_identity_match_via_git_remote(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "local-file")
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "home"))
    business = tmp_path / "business"
    site = tmp_path / "site"
    init_run(path=str(business), name="Acme")
    _set_origin(business, "git@github.com:acme-co/acme.git")
    site.mkdir()
    _seed_site_for_identity(site)
    _write_site_descriptor_with_parent(site, "acme-co", "acme")

    result = runner.invoke(
        app, ["site", "check", str(site), "--business-repo", str(business), "--json"]
    )
    payload = json.loads(result.stdout)
    evidence = {item["kind"]: item for item in payload["evidence"]}
    assert evidence["descriptor_identity"]["state"] == "passed"


def test_site_check_no_remote_no_descriptor_has_no_identity_evidence(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "local-file")
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "home"))
    business = tmp_path / "business"
    site = tmp_path / "site"
    business.mkdir()
    site.mkdir()
    _seed_site_for_identity(site)
    _write_site_descriptor_with_parent(site, "acme-co", "acme")

    result = runner.invoke(
        app, ["site", "check", str(site), "--business-repo", str(business), "--json"]
    )
    payload = json.loads(result.stdout)
    kinds = [item["kind"] for item in payload["evidence"]]
    assert "descriptor_identity" not in kinds


def _write_multi_site_repo(repo: Path) -> None:
    (repo / ".mainbranch").mkdir(parents=True)
    for slug in ("alpha", "beta"):
        (repo / "clients" / slug).mkdir(parents=True)
    (repo / ".mainbranch" / "repo.json").write_text(
        json.dumps(
            {
                "schema": "mb.child_repo.v0",
                "role": "site",
                "display_name": "Acme client sites",
                "sites": [
                    {
                        "slug": "alpha",
                        "display_name": "Alpha",
                        "dir": "clients/alpha",
                        "domains": ["alpha.example"],
                        "deploy": {"provider": "cloudflare-pages", "project": "alpha"},
                        "lifecycle": "active",
                    },
                    {"slug": "beta", "dir": "clients/beta"},
                ],
            }
        ),
        encoding="utf-8",
    )


def test_site_check_site_option_reads_that_sites_dir(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "local-file")
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "home"))
    repo = tmp_path / "acme-sites"
    _write_multi_site_repo(repo)
    _seed_site_for_identity(repo / "clients" / "alpha")

    alpha = runner.invoke(app, ["site", "check", str(repo), "--site", "alpha", "--json"])
    beta = runner.invoke(app, ["site", "check", str(repo), "--site", "beta", "--json"])

    alpha_payload = json.loads(alpha.stdout)
    beta_payload = json.loads(beta.stdout)
    assert alpha_payload["site"]["slug"] == "alpha"
    assert alpha_payload["site"]["deploy"] == {"provider": "cloudflare-pages", "project": "alpha"}
    assert alpha_payload["facts"]["conversion_kind"] == "lead_form"
    assert alpha_payload["facts"]["repo_role"] == "site"
    # beta has no conversion plan of its own; alpha's must not leak into it.
    assert beta_payload["site"]["slug"] == "beta"
    assert beta_payload["facts"]["conversion_kind"] == ""


def test_site_check_unknown_site_exits_2(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "local-file")
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "home"))
    repo = tmp_path / "acme-sites"
    _write_multi_site_repo(repo)

    result = runner.invoke(app, ["site", "check", str(repo), "--site", "gamma", "--json"])

    assert result.exit_code == 2
    assert "gamma" in result.stderr
    assert "alpha, beta" in result.stderr


def _ads_site(
    tmp_path: Path,
    *,
    customer: bool = True,
    primary: bool = True,
    approvals: bool = False,
    customer_id: str = "5550100000",
    gtm_id: str = "GTM-ABC1234",
) -> tuple[Path, Path]:
    business = tmp_path / "business"
    site = tmp_path / "site"
    init_run(path=str(business), name="Acme")
    site.mkdir()
    customer_line = f"google_ads_customer_id: '{customer_id}'\n" if customer else ""
    (business / "core" / "offer.md").write_text(
        (
            "---\n"
            f"gtm_container_id: {gtm_id}\n"
            f"{customer_line}"
            "consent_posture: standard_tag_consent_reviewed\n"
            "privacy_policy_url: https://example.com/privacy\n"
            "---\n\n"
            "# Offer\n"
        ),
        encoding="utf-8",
    )
    conversion: dict[str, object] = {
        "kind": "lead_form",
        "url": "https://tally.so/r/example",
        "render": "link_out",
    }
    if primary:
        conversion["primary_conversions"] = ["mb_lead_submit"]
    if approvals:
        conversion["operator_approvals"] = {
            "gtm_container_reviewed": True,
            "conversion_actions_reviewed": True,
            "consent_posture_reviewed": True,
        }
    _write_conversion(site, conversion)
    _write_html(site, events=["mb_cta_click", "mb_form_start", "mb_lead_submit"])
    return business, site


def _evidence(payload: dict[str, object], kind: str) -> dict[str, object]:
    items = payload["evidence"]
    assert isinstance(items, list)
    return next(item for item in items if item["kind"] == kind)


def test_site_check_reports_google_ads_declared_connected_and_evidence_separately(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "local-file")
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "home"))
    business, site = _ads_site(tmp_path)

    result = runner.invoke(
        app, ["site", "check", str(site), "--business-repo", str(business), "--json"]
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["state"] == "ready_for_operator_review"
    plan = _evidence(payload, "google_ads_plan")
    assert plan["state"] == "passed"
    assert plan["status"] == "declared"
    assert str(plan["summary"]).startswith("Declared:")
    connection = _evidence(payload, "google_ads_connection")
    assert connection["state"] == "manual"
    assert connection["status"] == "not_checked"
    assert "read-only Google Ads MCP" in str(connection["next"])
    assert "CSV export" in str(connection["next"])
    conversion = _evidence(payload, "google_ads_conversion_evidence")
    assert conversion["state"] == "manual"
    assert conversion["status"] == "no_evidence_recorded"
    assert conversion["tag_fired"] == "no_evidence_recorded"
    assert conversion["attributed_conversion"] == "no_evidence_recorded"
    manual_kinds = {item["kind"] for item in payload["manual"]}
    assert {"google_ads_connection", "google_ads_conversion_evidence"} <= manual_kinds


def test_site_check_never_reports_google_ads_connected_from_google_sign_in(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "local-file")
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "home"))
    business, site = _ads_site(tmp_path)
    monkeypatch.setattr(
        "mb.site.connect_mod.status_all",
        lambda *args, **kwargs: {
            "providers": [
                {"provider": "google", "state": "connected", "connected": True, "ok": True}
            ],
            "summary": {},
        },
    )

    result = runner.invoke(
        app, ["site", "check", str(site), "--business-repo", str(business), "--json"]
    )

    payload = json.loads(result.stdout)
    assert payload["facts"]["provider_state"]["google"]["connected"] is True
    assert _evidence(payload, "google_ads_connection")["status"] == "not_checked"


def test_site_check_google_ads_partly_declared_still_reports_other_checks(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "local-file")
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "home"))
    business, site = _ads_site(tmp_path, primary=False)

    result = runner.invoke(
        app, ["site", "check", str(site), "--business-repo", str(business), "--json"]
    )

    payload = json.loads(result.stdout)
    plan = _evidence(payload, "google_ads_plan")
    assert plan["state"] == "manual"
    assert plan["status"] == "partly_declared"
    assert plan["summary"] == "Missing primary conversion plan before launch review."
    assert _evidence(payload, "google_ads_connection")["status"] == "not_checked"
    assert _evidence(payload, "google_ads_conversion_evidence")["status"] == "no_evidence_recorded"


def test_site_check_without_google_ads_customer_adds_no_google_ads_checks(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "local-file")
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "home"))
    business, site = _ads_site(tmp_path, customer=False)

    result = runner.invoke(
        app, ["site", "check", str(site), "--business-repo", str(business), "--json"]
    )

    payload = json.loads(result.stdout)
    assert _evidence(payload, "google_ads_plan") == {
        "kind": "google_ads_plan",
        "state": "manual",
        "summary": "Missing Google Ads customer ID before launch review.",
    }
    kinds = {item["kind"] for item in payload["evidence"]}
    assert "google_ads_connection" not in kinds
    assert "google_ads_conversion_evidence" not in kinds


def test_site_check_google_ads_checks_do_not_block_ready(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "local-file")
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "home"))
    business, site = _ads_site(tmp_path, approvals=True)

    result = runner.invoke(
        app, ["site", "check", str(site), "--business-repo", str(business), "--json"]
    )

    payload = json.loads(result.stdout)
    assert payload["state"] == "ready"
    assert payload["ok"] is True
    assert _evidence(payload, "google_ads_connection")["status"] == "not_checked"


def test_site_check_human_output_names_google_ads_next_steps(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "local-file")
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "home"))
    business, site = _ads_site(tmp_path)

    result = runner.invoke(app, ["site", "check", str(site), "--business-repo", str(business)])

    assert result.exit_code == 0
    assert "google_ads_plan: Declared:" in result.stdout
    assert "manual   google_ads_connection: Not checked:" in result.stdout
    assert "manual   google_ads_conversion_evidence: No conversion evidence recorded:" in (
        result.stdout
    )
    assert "next: Read the account through Google's read-only Google Ads MCP" in result.stdout
    assert "next: Confirm the tag fires in GTM Preview or Tag Assistant" in result.stdout


@pytest.mark.parametrize(
    "customer_id",
    [
        "000-000-0000",
        "0000000000",
        "TODO",
        "tbd",
        "xxx-xxx-xxxx",
        "XXXXXXXXXX",
        "placeholder",
        "TODO: add id",
        "N/A",
        "none",
        "123",
        "555-010-000",
        "555-010-00001",
        "555-010-000A",
    ],
)
def test_site_check_placeholder_google_ads_customer_is_not_declared(
    tmp_path: Path, monkeypatch, customer_id: str
) -> None:
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "local-file")
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "home"))
    business, site = _ads_site(tmp_path, approvals=True, customer_id=customer_id)

    result = runner.invoke(
        app, ["site", "check", str(site), "--business-repo", str(business), "--json"]
    )

    payload = json.loads(result.stdout)
    assert _evidence(payload, "google_ads_plan") == {
        "kind": "google_ads_plan",
        "state": "manual",
        "status": "placeholder",
        "summary": (
            "Not declared: the Google Ads customer ID is a placeholder, "
            "so no Google Ads customer is recorded."
        ),
        "next": (
            "Replace it with the 10-digit customer ID shown at the top of "
            "the Google Ads account, then run mb site check again."
        ),
    }
    kinds = {item["kind"] for item in payload["evidence"]}
    assert "google_ads_connection" not in kinds
    assert "google_ads_conversion_evidence" not in kinds
    # A placeholder customer never makes the repo ready for paid traffic.
    assert payload["state"] == "ready_for_preview"


def test_site_check_placeholder_google_ads_customer_names_missing_plan(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "local-file")
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "home"))
    business, site = _ads_site(tmp_path, primary=False, customer_id="000-000-0000")

    result = runner.invoke(app, ["site", "check", str(site), "--business-repo", str(business)])

    assert result.exit_code == 0
    assert (
        "manual google_ads_plan: Not declared: the Google Ads customer ID is a "
        "placeholder, so no Google Ads customer is recorded. The primary conversion "
        "plan is also missing."
    ) in " ".join(result.stdout.split())
    assert "next: Replace it with the 10-digit customer ID" in result.stdout


@pytest.mark.parametrize("customer_id", ["", "   "])
def test_site_check_blank_google_ads_customer_reads_as_missing(
    tmp_path: Path, monkeypatch, customer_id: str
) -> None:
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "local-file")
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "home"))
    business, site = _ads_site(tmp_path, customer_id=customer_id)

    result = runner.invoke(
        app, ["site", "check", str(site), "--business-repo", str(business), "--json"]
    )

    payload = json.loads(result.stdout)
    assert _evidence(payload, "google_ads_plan") == {
        "kind": "google_ads_plan",
        "state": "manual",
        "summary": "Missing Google Ads customer ID before launch review.",
    }


@pytest.mark.parametrize("customer_id", ["5550100000", "555 010 0000", "123-456-7890"])
def test_site_check_ten_digit_google_ads_customer_is_declared(
    tmp_path: Path, monkeypatch, customer_id: str
) -> None:
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "local-file")
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "home"))
    business, site = _ads_site(tmp_path, approvals=True, customer_id=customer_id)

    result = runner.invoke(
        app, ["site", "check", str(site), "--business-repo", str(business), "--json"]
    )

    payload = json.loads(result.stdout)
    assert _evidence(payload, "google_ads_plan")["status"] == "declared"


def test_site_check_dashed_google_ads_customer_is_declared(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "local-file")
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "home"))
    business, site = _ads_site(tmp_path, approvals=True, customer_id="555-010-0000")

    result = runner.invoke(
        app, ["site", "check", str(site), "--business-repo", str(business), "--json"]
    )

    payload = json.loads(result.stdout)
    assert _evidence(payload, "google_ads_plan")["status"] == "declared"
    assert payload["state"] == "ready"


@pytest.mark.parametrize("gtm_id", ["GTM-TODO", "GTM-TBD"])
def test_site_check_gtm_shares_the_placeholder_words(
    tmp_path: Path, monkeypatch, gtm_id: str
) -> None:
    monkeypatch.setenv("MB_CONNECT_SECRET_BACKEND", "local-file")
    monkeypatch.setenv("MAINBRANCH_HOME", str(tmp_path / "home"))
    business, site = _ads_site(tmp_path, gtm_id=gtm_id)

    result = runner.invoke(
        app, ["site", "check", str(site), "--business-repo", str(business), "--json"]
    )

    payload = json.loads(result.stdout)
    assert _evidence(payload, "gtm_container")["state"] == "blocked"
