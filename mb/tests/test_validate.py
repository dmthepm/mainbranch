"""``mb validate`` frontmatter shape checks."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from mb import relationships
from mb.cli import app
from mb.validate import _owner_summary, render_human, run

runner = CliRunner()
REPO_ROOT = Path(__file__).resolve().parents[2]


def _write(p: Path, body: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


def _offer(slug: str = "workshop") -> str:
    return (
        "---\n"
        f"slug: {slug}\n"
        "status: running\n"
        "---\n"
        "# Workshop\n\n"
        "## Who this is for\n"
        "Solo operators with launch work scattered across tools.\n\n"
        "## Promise\n"
        "A clear business brain for deciding what to ship next.\n\n"
        "## Mechanism\n"
        "Main Branch turns offers, proof, decisions, and pushes into linked files.\n\n"
        "## Proof\n"
        "Approved outcome notes and testimonials live under core/proof/.\n\n"
        "## Price Or Value\n"
        "The value exchange is a focused setup sprint.\n\n"
        "## Next Step\n"
        "Book a review before writing launch copy.\n"
    )


def test_validate_passes_well_formed(tmp_path: Path) -> None:
    _write(
        tmp_path / "decisions" / "2026-04-29-ok.md",
        "---\ndate: 2026-04-29\nstatus: accepted\n---\n# ok\n",
    )
    _write(
        tmp_path / "research" / "2026-04-29-topic-claude-code.md",
        "---\ndate: 2026-04-29\ntopic: tau\nsource: claude-code\n---\n# r\n",
    )
    _write(
        tmp_path / "bets" / "2026-04-29-launch.md",
        (
            "---\n"
            "status: open\n"
            "opened: 2026-04-29\n"
            "deadline: 2026-05-13\n"
            "appetite: 2 weeks\n"
            "hypothesis: If we launch, qualified calls will increase.\n"
            "metric: qualified calls\n"
            "target: 10 qualified calls\n"
            "result: ''\n"
            "linked_decisions: []\n"
            "linked_research: []\n"
            "linked_campaigns: []\n"
            "linked_outcomes: []\n"
            "public: false\n"
            "channels: []\n"
            "tags: []\n"
            "---\n"
            "# Launch bet\n"
        ),
    )
    report = run(path=str(tmp_path))
    assert report["ok"] is True
    assert all(f["ok"] for f in report["files"])


def test_validate_accepts_simple_content_strategy_entry_point(tmp_path: Path) -> None:
    _write(
        tmp_path / "core" / "content-strategy.md",
        (
            "---\n"
            "type: content_strategy\n"
            "status: active\n"
            "---\n\n"
            "# Content Strategy\n\n"
            "## Known-for target\n"
            "Be known for helping solo operators keep business memory durable.\n\n"
            "## Pillars\n"
            "Repo truth, operator loops, and practical AI-assisted shipping.\n"
        ),
    )

    report = run(path=str(tmp_path))

    assert report["ok"] is True
    strategy = next(file for file in report["files"] if file["schema"] == "content-strategy")
    assert strategy["errors"] == []


def test_validate_accepts_team_members_and_normalized_github_handles(tmp_path: Path) -> None:
    _write(
        tmp_path / "core" / "team" / "maya.md",
        (
            "---\n"
            "type: team_member\n"
            "slug: maya\n"
            "name: Maya Chen\n"
            "preferred_name: Maya\n"
            "role: Growth Lead\n"
            "relationship: member\n"
            "github:\n"
            "  - mayachen\n"
            "areas:\n"
            "  - paid traffic\n"
            "  - launch reviews\n"
            "---\n\n"
            "# Maya\n"
        ),
    )
    _write(
        tmp_path / "core" / "team" / "rafa.md",
        (
            "---\n"
            "type: team_member\n"
            "slug: rafa\n"
            "name: Rafael Ortiz\n"
            "role: Advisor\n"
            "relationship: advisor\n"
            "github: rafa-ops\n"
            "---\n\n"
            "# Rafael\n"
        ),
    )

    report = run(path=str(tmp_path))

    assert report["ok"] is True
    team_files = [file for file in report["files"] if file["schema"] == "team-members"]
    assert len(team_files) == 2
    assert all(file["errors"] == [] for file in team_files)


def test_validate_rejects_duplicate_and_unnormalized_team_github_handles(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "core" / "team" / "maya.md",
        (
            "---\n"
            "type: team_member\n"
            "slug: maya\n"
            "name: Maya Chen\n"
            "relationship: member\n"
            "github:\n"
            "  - '@MayaChen'\n"
            "---\n\n"
            "# Maya\n"
        ),
    )
    _write(
        tmp_path / "core" / "team" / "ops.md",
        (
            "---\n"
            "type: team_member\n"
            "slug: ops\n"
            "name: Ops Contractor\n"
            "relationship: contractor\n"
            "github:\n"
            "  - mayachen\n"
            "---\n\n"
            "# Ops\n"
        ),
    )

    report = run(path=str(tmp_path))

    assert report["ok"] is False
    by_path = {file["path"]: file for file in report["files"]}
    assert any(
        "must be normalized as 'mayachen'" in error
        for error in by_path["core/team/maya.md"]["errors"]
    )
    assert any(
        "duplicate github handle 'mayachen'" in error
        for error in by_path["core/team/maya.md"]["errors"]
    )
    assert report["by_category"]["duplicate_github_handle"]["errors"] == 2


def test_validate_reports_layered_content_strategy_connection_failures(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "core" / "content-strategy.md",
        (
            "---\n"
            "type: content_strategy\n"
            "status: active\n"
            "linked_strategy_layers:\n"
            "  - core/marketing/accounts/x-founder.md\n"
            "---\n\n"
            "# Content Strategy\n\n"
            "The account layer should connect to a channel and person file.\n"
        ),
    )
    _write(
        tmp_path / "core" / "marketing" / "accounts" / "x-founder.md",
        (
            "---\n"
            "type: account_strategy\n"
            "status: active\n"
            "platform: x\n"
            "account: founder\n"
            "channel_strategy: core/marketing/channels/x.md\n"
            "voice_source: core/people/founder.md\n"
            "owner: Operator\n"
            "last_reviewed: 2026-05-12\n"
            "update_trigger: Platform norms changed.\n"
            "source_links: []\n"
            "---\n\n"
            "# X Founder Account\n\n"
            "Audience, allowed topics, voice, cadence, content mix, and CTA path.\n"
        ),
    )

    report = run(path=str(tmp_path))

    account = next(file for file in report["files"] if file["schema"] == "content-account-strategy")
    assert report["ok"] is False
    assert (
        "channel_strategy target 'core/marketing/channels/x.md' does not exist" in account["errors"]
    )
    assert "voice_source target 'core/people/founder.md' does not exist" in account["errors"]


def test_validate_reports_unindexed_and_stale_content_strategy_layers(tmp_path: Path) -> None:
    _write(
        tmp_path / "core" / "content-strategy.md",
        (
            "---\n"
            "type: content_strategy\n"
            "status: active\n"
            "---\n\n"
            "# Content Strategy\n\n"
            "Business-level strategy exists, but it has not indexed the channel layer yet.\n"
        ),
    )
    _write(
        tmp_path / "core" / "marketing" / "channels" / "reddit.md",
        (
            "---\n"
            "type: channel_strategy\n"
            "status: active\n"
            "channel: reddit\n"
            "owner: Operator\n"
            "last_reviewed: 2025-01-01\n"
            "update_trigger: Platform norms changed.\n"
            "source_links: []\n"
            "---\n\n"
            "# Reddit Channel Strategy\n\n"
            "Community norms, timing, content types, anti-spam rules, and review triggers.\n"
        ),
    )

    report = run(path=str(tmp_path))

    channel = next(file for file in report["files"] if file["schema"] == "content-channel-strategy")
    assert report["ok"] is True
    assert any("last_reviewed is" in warning for warning in channel["warnings"])
    assert "layer exists but is not indexed from core/content-strategy.md" in channel["warnings"]


def test_validate_accepts_canonical_bet_linked_pushes_without_legacy_campaigns(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "bets" / "2026-05-08-launch.md",
        (
            "---\n"
            "status: open\n"
            "opened: 2026-05-08\n"
            "deadline: 2026-05-22\n"
            "appetite: 2 weeks\n"
            "hypothesis: If we ship the push, qualified calls will increase.\n"
            "metric: qualified calls\n"
            "target: 10 qualified calls\n"
            "result: ''\n"
            "linked_decisions: []\n"
            "linked_research: []\n"
            "linked_pushes: []\n"
            "linked_outcomes: []\n"
            "public: false\n"
            "channels: []\n"
            "tags: []\n"
            "---\n"
            "# Launch bet\n"
        ),
    )

    report = run(path=str(tmp_path))

    assert report["ok"] is True
    bet = next(file for file in report["files"] if file["schema"] == "bets")
    assert bet["errors"] == []


def test_validate_accepts_bet_money_path_and_kill_rubric(tmp_path: Path) -> None:
    _write(
        tmp_path / "bets" / "2026-05-16-offer-test.md",
        (
            "---\n"
            "status: open\n"
            "opened: 2026-05-16\n"
            "deadline: 2026-05-30\n"
            "appetite: 2 weeks\n"
            "appetite_tier: small\n"
            "hypothesis: If we sharpen the offer, calls will increase.\n"
            "metric: qualified_calls\n"
            "target: 3 qualified calls\n"
            "result: ''\n"
            "money_path:\n"
            "  required: true\n"
            "  bet_id: 2026-05-16-offer-test\n"
            "  exposure_cap:\n"
            "    amount: 500\n"
            "    currency: USD\n"
            "  anchor_required_before: execution\n"
            "kill_rubric:\n"
            "  failure_signals:\n"
            "    - id: no-qualified-calls\n"
            "      metric: qualified_calls\n"
            "      comparator: <\n"
            "      threshold: 3\n"
            "      by: 2026-05-30\n"
            "      action: kill\n"
            "  double_down_signals:\n"
            "    - id: profitable-signal\n"
            "      metric: cost_per_qualified_call\n"
            "      comparator: <=\n"
            "      threshold: 150\n"
            "      action: double_down\n"
            "linked_decisions: []\n"
            "linked_research: []\n"
            "linked_pushes: []\n"
            "linked_outcomes: []\n"
            "public: false\n"
            "channels: []\n"
            "tags: []\n"
            "---\n"
            "# Offer test\n"
        ),
    )

    report = run(path=str(tmp_path))

    assert report["ok"] is True
    bet = next(file for file in report["files"] if file["schema"] == "bets")
    assert bet["errors"] == []
    assert bet["warnings"] == []


def test_validate_warns_on_malformed_bet_money_path_without_failing(tmp_path: Path) -> None:
    _write(
        tmp_path / "bets" / "2026-05-16-offer-test.md",
        (
            "---\n"
            "status: open\n"
            "opened: 2026-05-16\n"
            "deadline: 2026-05-30\n"
            "appetite: 2 weeks\n"
            "appetite_tier: giant\n"
            "hypothesis: If we sharpen the offer, calls will increase.\n"
            "metric: qualified_calls\n"
            "target: 3 qualified calls\n"
            "result: ''\n"
            "money_path:\n"
            "  required: true\n"
            "  bet_id: wrong-id\n"
            "  exposure_cap:\n"
            "    amount: -1\n"
            "    currency: ''\n"
            "kill_rubric:\n"
            "  failure_signals:\n"
            "    - id: no-qualified-calls\n"
            "      metric: qualified_calls\n"
            "      comparator: near\n"
            "      threshold: 3\n"
            "      action: kill\n"
            "linked_decisions: []\n"
            "linked_research: []\n"
            "linked_pushes: []\n"
            "linked_outcomes: []\n"
            "public: false\n"
            "channels: []\n"
            "tags: []\n"
            "---\n"
            "# Offer test\n"
        ),
    )

    report = run(path=str(tmp_path))

    assert report["ok"] is True
    bet = next(file for file in report["files"] if file["schema"] == "bets")
    assert bet["errors"] == []
    assert any("appetite_tier" in warning for warning in bet["warnings"])
    assert any("money_path.bet_id should match" in warning for warning in bet["warnings"])
    assert any(
        "kill_rubric.failure_signals[0].comparator" in warning for warning in bet["warnings"]
    )


_BET_BASE = (
    "status: {status}\n"
    "opened: 2026-05-16\n"
    "deadline: 2026-05-30\n"
    "appetite: 2 weeks\n"
    "hypothesis: If we do X, Y happens.\n"
    "metric: calls\n"
    "target: 3 calls\n"
    "result: ''\n"
    "{extra}"
    "linked_decisions: []\n"
    "linked_research: []\n"
    "linked_pushes: []\n"
    "linked_outcomes: []\n"
    "public: false\n"
    "channels: []\n"
    "tags: []\n"
)


def _validate_bet(tmp_path: Path, extra: str = "", status: str = "open") -> dict[str, Any]:
    _write(
        tmp_path / "bets" / "2026-05-16-daily.md",
        "---\n" + _BET_BASE.format(status=status, extra=extra) + "---\n# Daily bet\n",
    )
    report = run(path=str(tmp_path))
    return next(file for file in report["files"] if file["schema"] == "bets")


_COMMITMENT = (
    "commitment:\n"
    "  action: Send one outreach message\n"
    "  cadence: weekdays\n"
    "  owner: outreach-agent\n"
    "  evidence: send_id\n"
)


def test_validate_bet_without_stage_or_commitment_is_unchanged(tmp_path: Path) -> None:
    bet = _validate_bet(tmp_path)

    assert bet["errors"] == []
    assert bet["warnings"] == []


def test_validate_accepts_bet_stage_and_commitment(tmp_path: Path) -> None:
    bet = _validate_bet(tmp_path, "stage: working\n" + _COMMITMENT)

    assert bet["errors"] == []
    assert bet["warnings"] == []


def test_validate_commitment_owner_is_optional_and_unknown_keys_are_tolerated(
    tmp_path: Path,
) -> None:
    bet = _validate_bet(
        tmp_path,
        "commitment:\n  action: Post\n  cadence: daily\n  evidence: url\n  note: x\n",
    )

    assert bet["errors"] == []


def test_validate_rejects_unknown_bet_stage(tmp_path: Path) -> None:
    bet = _validate_bet(tmp_path, "stage: thriving\n")

    assert any(error.startswith("stage='thriving' not in") for error in bet["errors"])


def test_validate_rejects_non_string_bet_stage_without_crashing(tmp_path: Path) -> None:
    bet = _validate_bet(tmp_path, "stage: [working]\n")

    assert any(error.startswith("stage=['working'] not in") for error in bet["errors"])


def test_validate_rejects_bad_commitment_values(tmp_path: Path) -> None:
    bet = _validate_bet(
        tmp_path,
        "commitment:\n  action: '  '\n  cadence: hourly\n  evidence: [url]\n  owner: ''\n",
    )

    errors = bet["errors"]
    assert "commitment.action must be a non-empty string" in errors
    assert any(error.startswith("commitment.cadence='hourly' not in") for error in errors)
    assert any(error.startswith("commitment.evidence=['url'] not in") for error in errors)
    assert "commitment.owner must be a non-empty string when present" in errors


@pytest.mark.parametrize("owner_line", ["  owner: null\n", "  owner:\n"])
def test_validate_rejects_null_commitment_owner(tmp_path: Path, owner_line: str) -> None:
    bet = _validate_bet(
        tmp_path,
        "commitment:\n  action: Post\n  cadence: daily\n  evidence: url\n" + owner_line,
    )

    assert bet["errors"] == ["commitment.owner must be a non-empty string when present"]


def test_validate_requires_commitment_cadence_and_evidence(tmp_path: Path) -> None:
    bet = _validate_bet(tmp_path, "commitment:\n  action: Post\n")

    assert any(error.startswith("missing key: commitment.cadence") for error in bet["errors"])
    assert any(error.startswith("missing key: commitment.evidence") for error in bet["errors"])


def test_validate_rejects_non_mapping_commitment(tmp_path: Path) -> None:
    bet = _validate_bet(tmp_path, "commitment: daily\n")

    assert any(error.startswith("commitment must be a mapping") for error in bet["errors"])


def test_validate_warns_when_bet_stage_disagrees_with_status(tmp_path: Path) -> None:
    ended_open = _validate_bet(tmp_path, "stage: done\n", status="open")
    assert ended_open["errors"] == []
    assert any("stage='done' but status='open'" in w for w in ended_open["warnings"])

    live_closed = _validate_bet(tmp_path, "stage: ongoing\n", status="closed")
    assert live_closed["errors"] == []
    assert any("stage='ongoing' but status='closed'" in w for w in live_closed["warnings"])

    agreeing = _validate_bet(tmp_path, "stage: cut\n", status="canceled")
    assert agreeing["errors"] == []
    assert agreeing["warnings"] == []


def test_validate_keeps_legacy_bet_campaign_links_readable(tmp_path: Path) -> None:
    _write(
        tmp_path / "bets" / "2026-05-08-legacy.md",
        (
            "---\n"
            "status: open\n"
            "opened: 2026-05-08\n"
            "deadline: 2026-05-22\n"
            "appetite: 2 weeks\n"
            "hypothesis: If the legacy campaign lands, calls will increase.\n"
            "metric: qualified calls\n"
            "target: 10 qualified calls\n"
            "result: ''\n"
            "linked_decisions: []\n"
            "linked_research: []\n"
            "linked_campaigns: []\n"
            "linked_outcomes: []\n"
            "public: false\n"
            "channels: []\n"
            "tags: []\n"
            "---\n"
            "# Legacy bet\n"
        ),
    )

    report = run(path=str(tmp_path))

    assert report["ok"] is True
    bet = next(file for file in report["files"] if file["schema"] == "bets")
    assert bet["errors"] == []
    assert any("linked_campaigns" in warning for warning in bet["warnings"])


def test_validate_ignores_folder_readme_docs(tmp_path: Path) -> None:
    _write(tmp_path / "research" / "README.md", "# Research\n\nFolder docs without frontmatter.\n")
    _write(tmp_path / "decisions" / "README.md", "# Decisions\n\nFolder docs.\n")
    _write(tmp_path / "bets" / "README.md", "# Bets\n\nFolder docs.\n")
    _write(tmp_path / "log" / "README.md", "# Log\n\nFolder docs.\n")
    _write(tmp_path / "documents" / "README.md", "# Documents\n\nFolder docs.\n")
    _write(
        tmp_path / "pushes" / "2026-05-08-launch" / "playbooks" / "README.md",
        "# Playbooks\n\nFolder docs.\n",
    )
    _write(
        tmp_path / "research" / "2026-05-08-topic-source.md",
        "---\ndate: 2026-05-08\ntopic: topic\nsource: source\n---\n# Research\n",
    )

    report = run(path=str(tmp_path))

    assert report["ok"] is True
    paths = {file["path"] for file in report["files"]}
    assert "research/README.md" not in paths
    assert "decisions/README.md" not in paths
    assert "bets/README.md" not in paths
    assert "log/README.md" not in paths
    assert "documents/README.md" not in paths
    assert "pushes/2026-05-08-launch/playbooks/README.md" not in paths


def test_keyword_gate_documented_frontmatter_validates(tmp_path: Path) -> None:
    guide = REPO_ROOT / ".claude" / "skills" / "mb-think" / "references" / "keyword-gate.md"
    text = guide.read_text(encoding="utf-8")
    match = re.search(r"Frontmatter:\n\n```yaml\n(?P<frontmatter>---\n.*?\n---)\n```", text, re.S)
    assert match is not None

    frontmatter = (
        match.group("frontmatter")
        .replace("YYYY-MM-DD", "2026-05-08")
        .replace("offer-slug", "workshop")
        .replace("core/offers/<offer>/offer.md", "core/offers/workshop/offer.md")
    )
    _write(
        tmp_path / "research" / "2026-05-08-keyword-gate-workshop.md",
        f"{frontmatter}\n\n# Keyword Gate\n",
    )

    report = run(path=str(tmp_path))

    assert report["ok"] is True
    assert all(file["ok"] for file in report["files"])


def test_validate_flags_missing_status(tmp_path: Path) -> None:
    _write(
        tmp_path / "decisions" / "2026-04-29-broken.md",
        "---\ndate: 2026-04-29\n---\n# missing status\n",
    )
    report = run(path=str(tmp_path))
    assert report["ok"] is False
    bad = [f for f in report["files"] if not f["ok"]]
    assert any("status" in e for f in bad for e in f["errors"])


def test_validate_flags_bad_status_enum(tmp_path: Path) -> None:
    _write(
        tmp_path / "decisions" / "2026-04-29-typo.md",
        "---\ndate: 2026-04-29\nstatus: pending\n---\n# typo\n",
    )
    report = run(path=str(tmp_path))
    assert report["ok"] is False


def test_validate_explains_legacy_frontmatter_debt_after_migration(tmp_path: Path) -> None:
    _write(
        tmp_path / "decisions" / "2026-04-29-legacy.md",
        "---\ndate: 2026-04-29\nstatus: pending\n---\n# legacy\n",
    )
    (tmp_path / ".mb").mkdir()
    (tmp_path / ".mb" / "schema_version").write_text("0.2\n", encoding="utf-8")

    result = runner.invoke(app, ["validate", str(tmp_path), "--json"])

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["legacy_repair"]["code"] == "legacy-frontmatter-schema-debt"
    assert "not as evidence that the path migration failed" in payload["legacy_repair"]["message"]


def test_validate_handles_no_frontmatter(tmp_path: Path) -> None:
    _write(tmp_path / "decisions" / "2026-04-29-naked.md", "no frontmatter here\n")
    report = run(path=str(tmp_path))
    assert report["ok"] is False


def test_cross_refs_pass_when_targets_exist(tmp_path: Path) -> None:
    _write(
        tmp_path / "decisions" / "2026-04-29-ok.md",
        (
            "---\n"
            "date: 2026-04-29\n"
            "status: accepted\n"
            "linked_research:\n"
            "  - research/2026-04-29-topic-source.md\n"
            "---\n"
            "# ok\n"
            "\n"
            "## Related links\n"
            "\n"
            "- [Topic](../research/2026-04-29-topic-source.md)\n"
        ),
    )
    _write(
        tmp_path / "research" / "2026-04-29-topic-source.md",
        "---\ndate: 2026-04-29\ntopic: topic\nsource: source\n---\n# r\n",
    )

    report = run(path=str(tmp_path), cross_refs=True)

    assert report["ok"] is True
    assert report["cross_refs"]["enabled"] is True
    assert report["cross_refs"]["registry"]["version"] == "0.1"
    assert report["summary"]["warnings"] == 0


def test_source_scoped_offer_relationship_requires_source_path() -> None:
    assert relationships.relationship_for_field("offer") is None
    assert (
        relationships.relationship_for_field("offer", source_path="pushes/2026-05-07-demo/push.md")
        is not None
    )


def test_cross_refs_warn_when_frontmatter_link_missing_body_mirror(tmp_path: Path) -> None:
    _write(
        tmp_path / "decisions" / "2026-04-29-missing-mirror.md",
        (
            "---\n"
            "date: 2026-04-29\n"
            "status: accepted\n"
            "linked_research:\n"
            "  - research/2026-04-29-topic-source.md\n"
            "---\n"
            "# Missing mirror\n"
        ),
    )
    _write(
        tmp_path / "research" / "2026-04-29-topic-source.md",
        "---\ndate: 2026-04-29\ntopic: topic\nsource: source\n---\n# Topic\n",
    )

    report = run(path=str(tmp_path), cross_refs=True)

    assert report["ok"] is True
    assert report["summary"]["warnings"] == 1
    finding = report["cross_refs"]["warnings"][0]
    assert finding["code"] == "missing-related-link-mirror"
    assert finding["field"] == "linked_research"
    assert finding["target"] == "research/2026-04-29-topic-source.md"

    strict_report = run(path=str(tmp_path), cross_refs=True, strict=True)
    assert strict_report["ok"] is False
    strict_finding = strict_report["cross_refs"]["warnings"][0]
    assert strict_finding["code"] == "missing-related-link-mirror"
    assert (
        strict_report["validation_categories"]["by_category"]["missing_related_link_mirror"][
            "count"
        ]
        == 1
    )


def test_body_only_markdown_links_do_not_replace_typed_frontmatter(tmp_path: Path) -> None:
    _write(
        tmp_path / "research" / "2026-04-29-topic-source.md",
        "---\ndate: 2026-04-29\ntopic: topic\nsource: source\n---\n# Topic\n",
    )
    _write(
        tmp_path / "decisions" / "2026-04-29-body-only.md",
        (
            "---\n"
            "date: 2026-04-29\n"
            "status: accepted\n"
            "---\n"
            "# Body only\n"
            "\n"
            "## Related links\n"
            "\n"
            "- [Topic](../research/2026-04-29-topic-source.md)\n"
        ),
    )

    report = run(path=str(tmp_path), cross_refs=True, strict=True)

    assert report["ok"] is True
    assert report["summary"]["warnings"] == 0


def test_related_links_wikilink_satisfies_frontmatter_mirror(tmp_path: Path) -> None:
    _write(
        tmp_path / "research" / "2026-04-29-topic-source.md",
        "---\ndate: 2026-04-29\ntopic: topic\nsource: source\n---\n# Topic\n",
    )
    _write(
        tmp_path / "decisions" / "2026-04-29-wikilink-mirror.md",
        (
            "---\n"
            "date: 2026-04-29\n"
            "status: accepted\n"
            "linked_research:\n"
            "  - research/2026-04-29-topic-source.md\n"
            "---\n"
            "# Wikilink mirror\n"
            "\n"
            "## Related links\n"
            "\n"
            "- [[research/2026-04-29-topic-source|Topic]]\n"
        ),
    )

    report = run(path=str(tmp_path), cross_refs=True, strict=True)

    assert report["ok"] is True
    assert report["summary"]["warnings"] == 0


def test_cross_refs_warn_on_missing_targets_without_strict(tmp_path: Path) -> None:
    _write(
        tmp_path / "decisions" / "2026-04-29-broken.md",
        (
            "---\n"
            "date: 2026-04-29\n"
            "status: accepted\n"
            "linked_decisions:\n"
            "  - decisions/missing.md\n"
            "---\n"
            "# broken\n"
        ),
    )

    report = run(path=str(tmp_path), cross_refs=True)

    assert report["ok"] is True
    assert report["summary"]["warnings"] == 1
    finding = report["cross_refs"]["warnings"][0]
    assert finding["code"] == "missing-target"
    assert finding["path"] == "decisions/2026-04-29-broken.md"
    assert finding["field"] == "linked_decisions"
    assert finding["target"] == "decisions/missing.md"


def test_cross_refs_strict_fails_on_warnings(tmp_path: Path) -> None:
    _write(
        tmp_path / "decisions" / "2026-04-29-broken.md",
        (
            "---\n"
            "date: 2026-04-29\n"
            "status: accepted\n"
            "linked_research: research/missing.md\n"
            "---\n"
            "# broken\n"
        ),
    )

    report = run(path=str(tmp_path), cross_refs=True, strict=True)

    assert report["ok"] is False
    assert report["summary"] == {"errors": 0, "warnings": 1}
    assert report["files"][0]["ok"] is False


def test_cross_refs_skip_explicit_cross_repo_refs(tmp_path: Path) -> None:
    _write(
        tmp_path / "decisions" / "2026-04-29-cross-repo.md",
        (
            "---\n"
            "date: 2026-04-29\n"
            "status: accepted\n"
            "linked_research:\n"
            "  - noontide-projects/research/2026-04-29-note.md\n"
            "linked_decisions:\n"
            "  - repo:noontide-projects/decisions/2026-04-29-choice.md\n"
            "---\n"
            "# cross repo\n"
        ),
    )

    report = run(path=str(tmp_path), cross_refs=True, strict=True)

    assert report["ok"] is True
    assert report["summary"]["warnings"] == 0


def test_cross_refs_skip_bundled_package_data(tmp_path: Path) -> None:
    _write(
        tmp_path / "mb" / "_data" / "fixtures" / "decisions" / "fixture.md",
        (
            "---\n"
            "date: 2026-04-29\n"
            "status: accepted\n"
            "linked_research: research/missing.md\n"
            "---\n"
            "# fixture\n"
        ),
    )

    report = run(path=str(tmp_path), cross_refs=True, strict=True)

    assert report["ok"] is True
    assert report["summary"]["warnings"] == 0


def test_cross_refs_warn_on_missing_wikilink_target(tmp_path: Path) -> None:
    _write(
        tmp_path / "decisions" / "2026-05-04-link.md",
        "---\ndate: 2026-05-04\nstatus: accepted\n---\nSee [[missing-note]].\n",
    )

    report = run(path=str(tmp_path), cross_refs=True)

    assert report["ok"] is True
    assert report["summary"]["warnings"] == 1
    finding = report["cross_refs"]["warnings"][0]
    assert finding["code"] == "missing-wikilink-target"
    assert finding["field"] == "wikilink"
    assert finding["target"] == "missing-note"


def test_cross_refs_warn_on_ambiguous_wikilink_target(tmp_path: Path) -> None:
    _write(
        tmp_path / "research" / "note.md",
        "---\ndate: 2026-05-04\ntopic: one\nsource: manual\n---\n# Note\n",
    )
    _write(
        tmp_path / "documents" / "note.md",
        "---\ntitle: Other note\n---\n# Other\n",
    )
    _write(
        tmp_path / "decisions" / "2026-05-04-link.md",
        "---\ndate: 2026-05-04\nstatus: accepted\n---\nSee [[note]].\n",
    )

    report = run(path=str(tmp_path), cross_refs=True)

    assert report["summary"]["warnings"] == 1
    finding = report["cross_refs"]["warnings"][0]
    assert finding["code"] == "ambiguous-wikilink"
    assert finding["target"] == "note"


def test_cross_refs_accept_resolved_wikilink_target_without_extension(tmp_path: Path) -> None:
    _write(
        tmp_path / "research" / "audience.md",
        "---\ndate: 2026-05-04\ntopic: audience\nsource: manual\n---\n# Audience\n",
    )
    _write(
        tmp_path / "decisions" / "2026-05-04-link.md",
        "---\ndate: 2026-05-04\nstatus: accepted\n---\nSee [[research/audience|audience]].\n",
    )

    report = run(path=str(tmp_path), cross_refs=True, strict=True)

    assert report["ok"] is True
    assert report["summary"]["warnings"] == 0


def test_cross_refs_accept_resolved_wikilink_target_with_heading_anchor(tmp_path: Path) -> None:
    _write(
        tmp_path / "research" / "audience.md",
        "---\ndate: 2026-05-04\ntopic: audience\nsource: manual\n---\n# Details\n",
    )
    _write(
        tmp_path / "decisions" / "2026-05-04-link.md",
        "---\ndate: 2026-05-04\nstatus: accepted\n---\nSee [[research/audience#details]].\n",
    )

    report = run(path=str(tmp_path), cross_refs=True, strict=True)

    assert report["ok"] is True
    assert report["summary"]["warnings"] == 0


def test_cross_refs_do_not_stem_fallback_for_path_like_wikilinks(tmp_path: Path) -> None:
    _write(
        tmp_path / "documents" / "audience.md",
        "---\ntitle: Audience\n---\n# Audience\n",
    )
    _write(
        tmp_path / "decisions" / "2026-05-04-link.md",
        "---\ndate: 2026-05-04\nstatus: accepted\n---\nSee [[research/audience]].\n",
    )

    report = run(path=str(tmp_path), cross_refs=True)

    assert report["summary"]["warnings"] == 1
    finding = report["cross_refs"]["warnings"][0]
    assert finding["code"] == "missing-wikilink-target"
    assert finding["target"] == "research/audience"


def test_cross_refs_warn_when_wikilink_resolves_only_to_directory(tmp_path: Path) -> None:
    (tmp_path / "campaigns" / "spring-launch").mkdir(parents=True)
    _write(
        tmp_path / "decisions" / "2026-05-04-link.md",
        "---\ndate: 2026-05-04\nstatus: accepted\n---\nSee [[campaigns/spring-launch]].\n",
    )

    report = run(path=str(tmp_path), cross_refs=True)

    assert report["summary"]["warnings"] == 1
    finding = report["cross_refs"]["warnings"][0]
    assert finding["code"] == "missing-wikilink-target"
    assert finding["target"] == "campaigns/spring-launch"


def test_cross_refs_warn_when_wikilink_resolves_only_to_non_markdown_file(
    tmp_path: Path,
) -> None:
    _write(tmp_path / "documents" / "diagram.png", "fake image\n")
    _write(
        tmp_path / "decisions" / "2026-05-04-link.md",
        "---\ndate: 2026-05-04\nstatus: accepted\n---\nSee [[documents/diagram.png]].\n",
    )

    report = run(path=str(tmp_path), cross_refs=True)

    assert report["summary"]["warnings"] == 1
    finding = report["cross_refs"]["warnings"][0]
    assert finding["code"] == "missing-wikilink-target"
    assert finding["target"] == "documents/diagram.png"


def test_cross_refs_ignore_wikilink_like_syntax_inside_fenced_code(tmp_path: Path) -> None:
    _write(
        tmp_path / "documents" / "netlify.md",
        '---\ntitle: Netlify\n---\n```toml\n[[redirects]]\nfrom = "/"\n```\n',
    )

    report = run(path=str(tmp_path), cross_refs=True, strict=True)

    assert report["ok"] is True
    assert report["summary"]["warnings"] == 0


def test_cross_refs_ignore_wikilink_like_syntax_inside_inline_code(tmp_path: Path) -> None:
    _write(
        tmp_path / "documents" / "obsidian.md",
        "---\ntitle: Obsidian\n---\nUse `[[example]]` only when the target exists.\n",
    )

    report = run(path=str(tmp_path), cross_refs=True, strict=True)

    assert report["ok"] is True
    assert report["summary"]["warnings"] == 0


def test_cross_refs_resolve_standard_markdown_links_and_skip_safe_non_refs(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "research" / "audience.md",
        "---\ndate: 2026-05-07\ntopic: audience\nsource: manual\n---\n# Audience\n",
    )
    _write(
        tmp_path / "docs" / "brief.md",
        "---\ntitle: Brief\n---\n"
        "See [Audience](../research/audience.md), [root](research/audience.md), "
        "and [external](https://en.wikipedia.org/wiki/Foo_(bar)).\n"
        "![Chart](../research/chart.png)\n"
        "Use `[Missing](../research/missing.md)` as an example.\n"
        "```md\n[Missing](../research/missing.md)\n```\n",
    )

    report = run(path=str(tmp_path), cross_refs=True, strict=True)

    assert report["ok"] is True
    assert report["summary"]["warnings"] == 0


def test_cross_refs_warn_on_missing_standard_markdown_link_target(tmp_path: Path) -> None:
    _write(
        tmp_path / "docs" / "brief.md",
        "---\ntitle: Brief\n---\nSee [Missing](../research/missing.md).\n",
    )

    report = run(path=str(tmp_path), cross_refs=True)

    assert report["summary"]["warnings"] == 1
    finding = report["cross_refs"]["warnings"][0]
    assert finding["code"] == "missing-markdown-link-target"
    assert finding["field"] == "markdown_link"
    assert finding["target"] == "../research/missing.md"


def test_cross_refs_flag_status_transition_regressions(tmp_path: Path) -> None:
    _write(
        tmp_path / "decisions" / "2026-04-28-old.md",
        "---\ndate: 2026-04-28\nstatus: running\n---\n# old\n",
    )
    _write(
        tmp_path / "decisions" / "2026-04-29-new.md",
        (
            "---\n"
            "date: 2026-04-29\n"
            "status: proposed\n"
            "supersedes: decisions/2026-04-28-old.md\n"
            "---\n"
            "# new\n"
            "\n"
            "## Related links\n"
            "\n"
            "- [Old](2026-04-28-old.md)\n"
        ),
    )

    report = run(path=str(tmp_path), cross_refs=True)

    assert report["summary"]["warnings"] == 1
    assert report["cross_refs"]["warnings"][0]["code"] == "status-transition"
    assert "move backward" in report["cross_refs"]["warnings"][0]["message"]


def test_cross_refs_flag_orphan_offer_dirs(tmp_path: Path) -> None:
    (tmp_path / "core" / "offers" / "alpha").mkdir(parents=True)

    report = run(path=str(tmp_path), cross_refs=True)

    assert report["ok"] is True
    assert report["summary"]["warnings"] == 1
    assert report["cross_refs"]["orphan_offers"] == [
        {
            "code": "orphan-offer",
            "path": "core/offers/alpha",
            "field": "core/offers",
            "target": "offer.md",
            "message": "core/offers/alpha/ is missing offer.md",
        }
    ]


def test_cross_refs_warn_when_bet_link_lacks_reverse_link(tmp_path: Path) -> None:
    _write(
        tmp_path / "bets" / "2026-05-04-demo.md",
        (
            "---\n"
            "status: open\n"
            "opened: 2026-05-04\n"
            "deadline: 2026-05-11\n"
            "appetite: 1 week\n"
            "hypothesis: If demo prospects see the workflow, calls increase.\n"
            "metric: calls\n"
            "target: 5 calls\n"
            "result: ''\n"
            "linked_decisions:\n"
            "  - decisions/2026-05-04-demo.md\n"
            "linked_research: []\n"
            "linked_pushes: []\n"
            "linked_outcomes: []\n"
            "public: true\n"
            "channels:\n"
            "  - site\n"
            "tags:\n"
            "  - channel:site\n"
            "---\n"
            "# Demo bet\n"
            "\n"
            "## Related links\n"
            "\n"
            "- [Demo](../decisions/2026-05-04-demo.md)\n"
        ),
    )
    _write(
        tmp_path / "decisions" / "2026-05-04-demo.md",
        "---\ndate: 2026-05-04\nstatus: accepted\n---\n# Demo\n",
    )

    report = run(path=str(tmp_path), cross_refs=True)

    assert report["summary"]["warnings"] == 1
    finding = report["cross_refs"]["warnings"][0]
    assert finding["code"] == "missing-bet-backlink"
    assert finding["field"] == "linked_decisions"
    assert "linked_bets: bets/2026-05-04-demo.md" in finding["message"]


def test_cross_refs_pass_when_bet_links_are_bidirectional(tmp_path: Path) -> None:
    _write(
        tmp_path / "bets" / "2026-05-04-demo.md",
        (
            "---\n"
            "status: open\n"
            "opened: 2026-05-04\n"
            "deadline: 2026-05-11\n"
            "appetite: 1 week\n"
            "hypothesis: If demo prospects see the workflow, calls increase.\n"
            "metric: calls\n"
            "target: 5 calls\n"
            "result: ''\n"
            "linked_decisions:\n"
            "  - decisions/2026-05-04-demo.md\n"
            "linked_research: []\n"
            "linked_pushes: []\n"
            "linked_outcomes: []\n"
            "public: true\n"
            "channels:\n"
            "  - site\n"
            "tags: []\n"
            "---\n"
            "# Demo bet\n"
            "\n"
            "## Related links\n"
            "\n"
            "- [Demo](../decisions/2026-05-04-demo.md)\n"
        ),
    )
    _write(
        tmp_path / "decisions" / "2026-05-04-demo.md",
        (
            "---\n"
            "date: 2026-05-04\n"
            "status: accepted\n"
            "linked_bets:\n"
            "  - bets/2026-05-04-demo.md\n"
            "---\n"
            "# Demo\n"
            "\n"
            "## Related links\n"
            "\n"
            "- [Demo bet](../bets/2026-05-04-demo.md)\n"
        ),
    )

    report = run(path=str(tmp_path), cross_refs=True)

    assert report["ok"] is True
    assert report["summary"]["warnings"] == 0


def test_validate_cli_cross_refs_default_warns_strict_fails(tmp_path: Path) -> None:
    _write(
        tmp_path / "decisions" / "2026-04-29-broken.md",
        (
            "---\n"
            "date: 2026-04-29\n"
            "status: accepted\n"
            "linked_research: research/missing.md\n"
            "---\n"
            "# broken\n"
        ),
    )

    result = runner.invoke(app, ["validate", str(tmp_path), "--cross-refs", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["ok"] is True
    assert payload["summary"]["warnings"] == 1

    result = runner.invoke(
        app,
        ["validate", str(tmp_path), "--cross-refs", "--strict", "--json"],
    )
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["files"][0]["ok"] is False


def test_validate_cli_accepts_repo_alias(tmp_path: Path) -> None:
    _write(
        tmp_path / "decisions" / "2026-05-08-ok.md",
        "---\ndate: 2026-05-08\nstatus: accepted\n---\n# Ok\n",
    )

    result = runner.invoke(app, ["validate", "--repo", str(tmp_path), "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["repo"] == str(tmp_path.resolve())


def _campaign(status: str) -> str:
    return f"---\nslug: workshop-waitlist\nstatus: {status}\n---\n# Workshop waitlist\n"


def test_validate_accepts_campaign_lifecycle_statuses(tmp_path: Path) -> None:
    for status in ("draft", "planned", "active", "paused", "completed", "canceled", "archived"):
        path = tmp_path / "campaigns" / f"2026-05-{status}-push" / "campaign.md"
        _write(path, _campaign(status))

    report = run(path=str(tmp_path))

    assert report["ok"] is True, report
    campaign_files = [f for f in report["files"] if "campaigns/" in f["path"]]
    assert len(campaign_files) == 7
    assert all(f["ok"] for f in campaign_files)


def test_validate_rejects_offer_only_status_on_campaign(tmp_path: Path) -> None:
    # `running` and `scaling` are valid offer statuses but invalid for campaigns;
    # the merged decision tells operators to use `active`.
    _write(
        tmp_path / "campaigns" / "2026-05-bad" / "campaign.md",
        _campaign("scaling"),
    )

    report = run(path=str(tmp_path))

    assert report["ok"] is False
    bad = [f for f in report["files"] if not f["ok"]]
    assert any("status" in e for f in bad for e in f["errors"])


def test_validate_flags_unknown_campaign_status(tmp_path: Path) -> None:
    _write(
        tmp_path / "campaigns" / "2026-05-typo" / "campaign.md",
        _campaign("live"),  # operator-vocab synonym; not yet wired
    )

    report = run(path=str(tmp_path))

    assert report["ok"] is False
    bad = [f for f in report["files"] if not f["ok"]]
    assert any("status" in e for f in bad for e in f["errors"])


def _push(
    status: str,
    slug: str = "workshop-waitlist",
    *,
    kind: str = "launch",
    health: str = "on-track",
) -> str:
    return (
        "---\n"
        "type: push\n"
        f"slug: {slug}\n"
        f"kind: {kind}\n"
        f"status: {status}\n"
        f"health: {health}\n"
        "goal:\n"
        "  metric: qualified calls\n"
        "  target: 10 qualified calls\n"
        "  by: 2026-05-20\n"
        "owner: Devon\n"
        "audience: founders testing Main Branch\n"
        "offer: core/offers/workshop/offer.md\n"
        "promise: Own the launch memory in git.\n"
        "---\n"
        f"# {slug}\n"
    )


def _playbook(
    status: str = "draft",
    *,
    provider: str = "manual",
    provider_boundary: str = "plan-only",
    push: str = "../push.md",
) -> str:
    return (
        "---\n"
        "type: playbook\n"
        f"status: {status}\n"
        f"push: {push}\n"
        "platform: instagram\n"
        f"provider: {provider}\n"
        f"provider_boundary: {provider_boundary}\n"
        "trigger:\n"
        "  kind: comment_keyword\n"
        "  keyword: TEMPLATE\n"
        "resource:\n"
        "  kind: url\n"
        "  value: https://example.com/resource\n"
        "copy:\n"
        "  public_cta: Comment TEMPLATE for the resource.\n"
        "  reply: Thanks. The resource is linked in the post.\n"
        "approval:\n"
        "  required: true\n"
        "  status: needed\n"
        "  approved_by:\n"
        "  approved_at:\n"
        "state:\n"
        "  provider_refs: []\n"
        "  activated_at:\n"
        "  retired_at:\n"
        "validation:\n"
        "  dry_run: not-run\n"
        "  smoke_evidence: []\n"
        "  notes: Draft only; no provider mutation.\n"
        "linked_outcomes: []\n"
        "---\n"
        "# Comment keyword playbook\n"
    )


def test_validate_accepts_push_lifecycle_statuses(tmp_path: Path) -> None:
    for status in ("draft", "planned", "active", "paused", "completed", "canceled", "archived"):
        path = tmp_path / "pushes" / f"2026-05-06-{status}-push" / "push.md"
        _write(path, _push(status, slug=f"{status}-push"))

    report = run(path=str(tmp_path))

    assert report["ok"] is True, report
    push_files = [f for f in report["files"] if "pushes/" in f["path"]]
    assert len(push_files) == 7
    assert all(f["ok"] for f in push_files)


def test_validate_push_no_bet_reason_requires_non_empty_string(tmp_path: Path) -> None:
    for slug, reason in (
        ("one-off", "One-time notice"),
        ("empty", "'  '"),
        ("non-string", "123"),
    ):
        path = tmp_path / "pushes" / f"2026-05-06-{slug}" / "push.md"
        _write(
            path,
            _push("planned", slug=slug).replace(
                "---\n#", f"linked_bets: []\nno_bet_reason: {reason}\n---\n#"
            ),
        )

    report = run(path=str(tmp_path))
    files = {Path(item["path"]).parent.name: item for item in report["files"]}
    assert files["2026-05-06-one-off"]["ok"] is True
    for slug in ("empty", "non-string"):
        assert (
            "no_bet_reason must be a non-empty string when present"
            in files[f"2026-05-06-{slug}"]["errors"]
        )


def test_validate_requires_canonical_push_schema(tmp_path: Path) -> None:
    _write(
        tmp_path / "pushes" / "2026-05-06-incomplete" / "push.md",
        "---\nslug: incomplete\nstatus: active\n---\n# incomplete\n",
    )

    report = run(path=str(tmp_path))

    assert report["ok"] is False
    bad = [file for file in report["files"] if file["path"].endswith("push.md")][0]
    assert "missing key: type" in bad["errors"]
    assert "missing key: kind" in bad["errors"]
    assert "missing key: goal" in bad["errors"]
    assert "goal must be a mapping with metric, target, and by" not in bad["errors"]
    assert "missing key: owner" in bad["errors"]
    assert "missing key: audience" in bad["errors"]
    assert "missing key: offer" in bad["errors"]
    assert "missing key: promise" in bad["errors"]
    categories = report["validation_categories"]["by_category"]
    assert categories["missing_required_key"]["count"] >= 1
    assert "schema_shape_error" not in categories


def test_validate_categorizes_malformed_push_goal_shape(tmp_path: Path) -> None:
    _write(
        tmp_path / "pushes" / "2026-05-06-bad-goal" / "push.md",
        _push("active", slug="bad-goal").replace(
            "goal:\n  metric: qualified calls\n  target: 10 qualified calls\n  by: 2026-05-20\n",
            "goal: five calls\n",
        ),
    )

    report = run(path=str(tmp_path))

    bad = [file for file in report["files"] if file["path"].endswith("push.md")][0]
    assert "missing key: goal" not in bad["errors"]
    assert "goal must be a mapping with metric, target, and by" in bad["errors"]
    assert report["validation_categories"]["by_category"]["schema_shape_error"]["count"] == 1


def test_validate_flags_media_backend_without_location(tmp_path: Path) -> None:
    # #803: a media-bearing push must say where the finished creative lives.
    _write(
        tmp_path / "pushes" / "2026-05-06-ads-batch" / "push.md",
        _push("active", slug="ads-batch").replace(
            "promise: Own the launch memory in git.\n",
            "promise: Own the launch memory in git.\nmedia_backend: google-drive\n",
        ),
    )

    report = run(path=str(tmp_path))

    assert report["ok"] is False
    bad = [file for file in report["files"] if file["path"].endswith("push.md")][0]
    assert any("media_backend is set but media_location is missing" in e for e in bad["errors"])


def test_validate_accepts_push_with_both_media_fields(tmp_path: Path) -> None:
    _write(
        tmp_path / "pushes" / "2026-05-06-ads-batch" / "push.md",
        _push("active", slug="ads-batch").replace(
            "promise: Own the launch memory in git.\n",
            (
                "promise: Own the launch memory in git.\n"
                "media_location: https://drive.google.com/drive/folders/abc123\n"
                "media_backend: google-drive\n"
            ),
        ),
    )

    report = run(path=str(tmp_path))

    bad = [file for file in report["files"] if file["path"].endswith("push.md")][0]
    assert not any("media_" in e for e in bad["errors"]), bad["errors"]


def test_validate_flags_blank_media_location(tmp_path: Path) -> None:
    _write(
        tmp_path / "pushes" / "2026-05-06-ads-batch" / "push.md",
        _push("active", slug="ads-batch").replace(
            "promise: Own the launch memory in git.\n",
            'promise: Own the launch memory in git.\nmedia_location: ""\n',
        ),
    )

    report = run(path=str(tmp_path))

    bad = [file for file in report["files"] if file["path"].endswith("push.md")][0]
    assert any("media_location must be a non-empty string" in e for e in bad["errors"])


def test_validate_categorizes_large_frontmatter_repairs(tmp_path: Path) -> None:
    for index in range(3):
        _write(
            tmp_path / "core" / "offers" / f"offer-{index}" / "offer.md",
            "---\nstatus: running\n---\n# Offer\n",
        )
    _write(
        tmp_path / "decisions" / "2026-05-08-bad.md",
        "---\ndate: 2026-05-08\nstatus: pending\n---\n# Bad\n",
    )
    _write(tmp_path / "research" / "2026-05-08-no-frontmatter.md", "# No frontmatter\n")

    report = run(path=str(tmp_path))

    categories = report["validation_categories"]
    assert categories["top_category"] == "missing_slug"
    assert categories["by_category"]["missing_slug"]["count"] == 3
    assert categories["by_category"]["status_enum_mismatch"]["count"] == 1
    assert categories["by_category"]["no_frontmatter"]["count"] == 1
    assert report["summary"] == {"errors": 5, "warnings": 0}


def test_validate_requires_canonical_push_folder_shape(tmp_path: Path) -> None:
    _write(
        tmp_path / "pushes" / "workshop-waitlist" / "push.md",
        _push("active"),
    )

    report = run(path=str(tmp_path))

    assert report["ok"] is False
    bad = [file for file in report["files"] if file["path"].endswith("push.md")][0]
    assert "push folder must match YYYY-MM-DD-slug" in bad["errors"]


def test_validate_rejects_invalid_push_shape_fields(tmp_path: Path) -> None:
    _write(
        tmp_path / "pushes" / "2026-05-06-invalid" / "push.md",
        (
            "---\n"
            "type: campaign\n"
            "slug: invalid\n"
            "kind: sprint\n"
            "status: active\n"
            "health: spicy\n"
            "goal: 40 calls\n"
            "owner: ''\n"
            "audience: founders\n"
            "offer: core/offers/workshop/offer.md\n"
            "promise: " + ("x" * 141) + "\n"
            "---\n"
            "# invalid\n"
        ),
    )

    report = run(path=str(tmp_path))

    bad = [file for file in report["files"] if file["path"].endswith("push.md")][0]
    assert report["ok"] is False
    assert "type must be 'push'" in bad["errors"]
    assert any("kind=" in error for error in bad["errors"])
    assert any("health=" in error for error in bad["errors"])
    assert "goal must be a mapping with metric, target, and by" in bad["errors"]
    assert "owner must be a non-empty string" in bad["errors"]
    assert "promise must be 140 characters or fewer" in bad["errors"]


def test_validate_rejects_incomplete_structured_push_goal(tmp_path: Path) -> None:
    _write(
        tmp_path / "pushes" / "2026-05-06-bad-goal" / "push.md",
        (
            "---\n"
            "type: push\n"
            "slug: bad-goal\n"
            "kind: launch\n"
            "status: active\n"
            "health: on-track\n"
            "goal:\n"
            "  metric: qualified calls\n"
            "  target: ''\n"
            "  by: soon\n"
            "owner: Devon\n"
            "audience: founders\n"
            "offer: core/offers/workshop/offer.md\n"
            "promise: Own the launch memory in git.\n"
            "---\n"
            "# bad goal\n"
        ),
    )

    report = run(path=str(tmp_path))

    bad = [file for file in report["files"] if file["path"].endswith("push.md")][0]
    assert "goal.target must be a non-empty string" in bad["errors"]
    assert "goal.by must be YYYY-MM-DD" in bad["errors"]


def test_validate_rejects_unknown_push_status(tmp_path: Path) -> None:
    _write(
        tmp_path / "pushes" / "2026-05-06-typo" / "push.md",
        _push("live", slug="typo"),  # operator-vocab synonym; not engine canonical
    )

    report = run(path=str(tmp_path))

    assert report["ok"] is False


def test_validate_rejects_unknown_push_kind_even_when_vocabulary_renames_it(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "core" / "vocabulary.md",
        (
            "---\n"
            "type: vocabulary\n"
            "status: active\n"
            "terms:\n"
            "  kinds:\n"
            "    sprint: sprint\n"
            "---\n"
            "# Vocabulary\n"
        ),
    )
    _write(
        tmp_path / "pushes" / "2026-05-06-sprint" / "push.md",
        _push("active", slug="sprint", kind="sprint"),
    )

    report = run(path=str(tmp_path))

    assert report["ok"] is False
    bad = [file for file in report["files"] if file["path"].endswith("push.md")][0]
    assert any("kind=" in error for error in bad["errors"])


def test_validate_accepts_push_playbook_schema(tmp_path: Path) -> None:
    _write(
        tmp_path / "pushes" / "2026-05-06-target" / "push.md",
        _push("active", slug="target")
        + "\n## Related links\n\n- [Workshop](../../core/offers/workshop/offer.md)\n",
    )
    _write(
        tmp_path / "pushes" / "2026-05-06-target" / "playbooks" / "resource.md",
        _playbook(),
    )

    report = run(path=str(tmp_path))

    assert report["ok"] is True, report
    playbook = [file for file in report["files"] if file["path"].endswith("playbooks/resource.md")][
        0
    ]
    assert playbook["schema"] == "push-playbooks"
    assert playbook["ok"] is True


def test_validate_accepts_sanitized_push_playbook_fixture() -> None:
    fixture_root = Path(__file__).parent / "fixtures"

    report = run(path=str(fixture_root))

    assert report["ok"] is True, report
    assert any(
        file["path"] == "pushes/2026-05-06-resource-delivery/playbooks/valid-resource-delivery.md"
        and file["schema"] == "push-playbooks"
        and file["ok"]
        for file in report["files"]
    )
    assert any(
        file["path"] == "pushes/2026-05-08-google-ads-launch/playbooks/google-ads-launch-plan.md"
        and file["schema"] == "push-playbooks"
        and file["ok"]
        for file in report["files"]
    )


def test_validate_requires_push_playbook_shape(tmp_path: Path) -> None:
    _write(
        tmp_path / "pushes" / "2026-05-06-target" / "push.md",
        _push("active", slug="target")
        + "\n## Related links\n\n- [Workshop](../../core/offers/workshop/offer.md)\n",
    )
    _write(
        tmp_path / "pushes" / "2026-05-06-target" / "playbooks" / "incomplete.md",
        "---\ntype: playbook\nstatus: draft\n---\n# Incomplete\n",
    )

    report = run(path=str(tmp_path))

    assert report["ok"] is False
    bad = [file for file in report["files"] if file["path"].endswith("playbooks/incomplete.md")][0]
    assert "missing key: push" in bad["errors"]
    assert "missing key: provider_boundary" in bad["errors"]
    assert "missing key: resource" in bad["errors"]
    assert "missing key: approval" in bad["errors"]
    assert "missing key: linked_outcomes" in bad["errors"]


def test_validate_rejects_playbook_missing_linked_push(tmp_path: Path) -> None:
    _write(
        tmp_path / "pushes" / "2026-05-06-target" / "playbooks" / "resource.md",
        _playbook(),
    )

    report = run(path=str(tmp_path))

    bad = [file for file in report["files"] if file["path"].endswith("playbooks/resource.md")][0]
    assert report["ok"] is False
    assert "push target does not exist" in bad["errors"]


def test_validate_rejects_playbook_wrong_push_link(tmp_path: Path) -> None:
    _write(
        tmp_path / "pushes" / "2026-05-06-target" / "push.md",
        _push("active", slug="target")
        + "\n## Related links\n\n- [Workshop](../../core/offers/workshop/offer.md)\n",
    )
    _write(
        tmp_path / "pushes" / "2026-05-06-target" / "playbooks" / "resource.md",
        _playbook(push="pushes/2026-05-06-other/push.md"),
    )

    report = run(path=str(tmp_path))

    bad = [file for file in report["files"] if file["path"].endswith("playbooks/resource.md")][0]
    assert report["ok"] is False
    assert "push must link to the containing push.md" in bad["errors"]


def test_validate_rejects_unknown_playbook_status(tmp_path: Path) -> None:
    _write(
        tmp_path / "pushes" / "2026-05-06-target" / "push.md",
        _push("active", slug="target")
        + "\n## Related links\n\n- [Workshop](../../core/offers/workshop/offer.md)\n",
    )
    _write(
        tmp_path / "pushes" / "2026-05-06-target" / "playbooks" / "resource.md",
        _playbook(status="live"),
    )

    report = run(path=str(tmp_path))

    bad = [file for file in report["files"] if file["path"].endswith("playbooks/resource.md")][0]
    assert report["ok"] is False
    assert any("status=" in error for error in bad["errors"])


def test_validate_rejects_playbook_supported_provider_claim_without_adapter(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "pushes" / "2026-05-06-target" / "push.md",
        _push("active", slug="target"),
    )
    _write(
        tmp_path / "pushes" / "2026-05-06-target" / "playbooks" / "resource.md",
        _playbook(provider="postiz", provider_boundary="accepted-adapter"),
    )

    report = run(path=str(tmp_path))

    bad = [file for file in report["files"] if file["path"].endswith("playbooks/resource.md")][0]
    assert report["ok"] is False
    assert any("tested Main Branch provider adapter" in error for error in bad["errors"])


def test_validate_rejects_playbook_secret_frontmatter_value(tmp_path: Path) -> None:
    _write(
        tmp_path / "pushes" / "2026-05-06-target" / "push.md",
        _push("active", slug="target"),
    )
    _write(
        tmp_path / "pushes" / "2026-05-06-target" / "playbooks" / "resource.md",
        _playbook().replace(
            "  notes: Draft only; no provider mutation.\n",
            "  notes: ghp_123456789012345678901234567890123456\n",
        ),
    )

    report = run(path=str(tmp_path))

    bad = [file for file in report["files"] if file["path"].endswith("playbooks/resource.md")][0]
    assert report["ok"] is False
    assert any("validation.notes" in error for error in bad["errors"])


def test_validate_rejects_playbook_secret_frontmatter(tmp_path: Path) -> None:
    _write(
        tmp_path / "pushes" / "2026-05-06-target" / "push.md",
        _push("active", slug="target"),
    )
    _write(
        tmp_path / "pushes" / "2026-05-06-target" / "playbooks" / "resource.md",
        _playbook().replace(
            "  provider_refs: []\n",
            "  access_token: ghp_123456789012345678901234567890123456\n",
        ),
    )

    report = run(path=str(tmp_path))

    bad = [file for file in report["files"] if file["path"].endswith("playbooks/resource.md")][0]
    assert report["ok"] is False
    assert any("state.access_token" in error for error in bad["errors"])


def test_cross_refs_resolve_linked_pushes_field(tmp_path: Path) -> None:
    """linked_pushes is recognized as a graph link field and must resolve."""
    _write(
        tmp_path / "core" / "offers" / "workshop" / "offer.md",
        _offer(),
    )
    _write(
        tmp_path / "pushes" / "2026-05-06-target" / "push.md",
        _push("active", slug="target")
        + "\n## Related links\n\n- [Workshop](../../core/offers/workshop/offer.md)\n",
    )
    _write(
        tmp_path / "decisions" / "2026-05-06-with-link.md",
        (
            "---\n"
            "date: 2026-05-06\n"
            "status: accepted\n"
            "linked_pushes:\n"
            "  - pushes/2026-05-06-target/push.md\n"
            "---\n"
            "# decision\n"
            "\n"
            "## Related links\n"
            "\n"
            "- [Target](../pushes/2026-05-06-target/push.md)\n"
        ),
    )

    report = run(path=str(tmp_path), cross_refs=True)

    assert report["ok"] is True
    assert report["summary"]["warnings"] == 0


def test_cross_refs_validate_push_offer_relationship(tmp_path: Path) -> None:
    _write(
        tmp_path / "core" / "offers" / "workshop" / "offer.md",
        _offer(),
    )
    _write(
        tmp_path / "pushes" / "2026-05-06-target" / "push.md",
        _push("active", slug="target")
        + "\n## Related links\n\n- [Workshop](../../core/offers/workshop/offer.md)\n",
    )

    report = run(path=str(tmp_path), cross_refs=True, strict=True)

    assert report["ok"] is True
    assert report["summary"]["warnings"] == 0


def test_cross_refs_warn_on_missing_push_offer_relationship(tmp_path: Path) -> None:
    _write(
        tmp_path / "pushes" / "2026-05-06-target" / "push.md",
        _push("active", slug="target"),
    )

    report = run(path=str(tmp_path), cross_refs=True)

    assert report["summary"]["warnings"] == 1
    finding = report["cross_refs"]["warnings"][0]
    assert finding["code"] == "missing-target"
    assert finding["field"] == "offer"
    assert finding["target"] == "core/offers/workshop/offer.md"


def test_validate_accepts_provider_refs_mapping_shape(tmp_path: Path) -> None:
    _write(
        tmp_path / "pushes" / "2026-05-06-target" / "push.md",
        _push("active", slug="target").replace(
            "---\n# target\n",
            "provider_refs:\n  meta_ads:\n    campaign_id: '123'\n---\n# target\n",
        ),
    )

    report = run(path=str(tmp_path))

    assert report["ok"] is True


def test_validate_rejects_provider_refs_scalar_shape(tmp_path: Path) -> None:
    _write(
        tmp_path / "pushes" / "2026-05-06-target" / "push.md",
        _push("active", slug="target").replace(
            "---\n# target\n",
            "provider_refs: meta_ads:123\n---\n# target\n",
        ),
    )

    report = run(path=str(tmp_path))

    bad = [file for file in report["files"] if file["path"].endswith("push.md")][0]
    assert report["ok"] is False
    assert "provider_refs must be a mapping of provider names to non-secret refs" in bad["errors"]


def test_validate_rejects_provider_refs_list_with_empty_ref_name(tmp_path: Path) -> None:
    _write(
        tmp_path / "pushes" / "2026-05-06-target" / "push.md",
        _push("active", slug="target").replace(
            "---\n# target\n",
            "provider_refs:\n  meta_ads:\n    - \"\": '123'\n---\n# target\n",
        ),
    )

    report = run(path=str(tmp_path))

    bad = [file for file in report["files"] if file["path"].endswith("push.md")][0]
    assert report["ok"] is False
    assert "provider_refs.meta_ads ref names must be non-empty strings" in bad["errors"]


def _repo_topology(extra_repo_fields: str = "") -> str:
    return (
        "---\n"
        "type: repo_topology\n"
        "status: active\n"
        "schema: mb.repo_topology.v0\n"
        "home: github:example-co/example\n"
        'business_display_name: "Example Business"\n'
        "repos:\n"
        "  - slug: example\n"
        '    display_name: "Example Business"\n'
        "    role: business\n"
        "    lifecycle: active\n"
        "    github_owner: example-co\n"
        "    repo_name: example\n"
        "    remote: github:example-co/example\n"
        "    visibility: team_private\n"
        "    relationship: hub_for\n"
        "  - slug: workshop-site\n"
        '    display_name: "Workshop site"\n'
        "    role: site\n"
        "    lifecycle: active\n"
        "    relationship: execution_vehicle_for\n"
        "    parent: example\n"
        "    github_owner: example-co\n"
        "    repo_name: workshop-site\n"
        "    remote: https://github.com/example-co/workshop-site.git\n"
        "    visibility: public\n"
        "    domain: workshop.example.com\n"
        "    linked_offers:\n"
        "      - core/offers/workshop/offer.md\n"
        "    linked_pushes:\n"
        "      - pushes/2026-05-06-target/push.md\n"
        "    linked_playbook_runs:\n"
        "      - pushes/2026-05-06-target/playbooks/resource.md\n"
        f"{extra_repo_fields}"
        "  - slug: finance\n"
        '    display_name: "Finance source"\n'
        "    role: finance\n"
        "    lifecycle: active\n"
        "    visibility: restricted\n"
        "    relationship: reports_to\n"
        "    parent: example\n"
        "    purpose: Private bookkeeping source; hub stores approved summaries only.\n"
        "---\n"
        "# Repo Topology\n"
    )


def test_validate_accepts_repo_topology_schema_and_links(tmp_path: Path) -> None:
    _write(
        tmp_path / "core" / "offers" / "workshop" / "offer.md",
        _offer(),
    )
    _write(
        tmp_path / "pushes" / "2026-05-06-target" / "push.md",
        _push("active", slug="target"),
    )
    _write(
        tmp_path / "pushes" / "2026-05-06-target" / "playbooks" / "resource.md",
        _playbook(),
    )
    _write(tmp_path / "core" / "operations" / "repo-topology.md", _repo_topology())

    report = run(path=str(tmp_path), strict=True)

    assert report["ok"] is True, report
    topology = [
        file for file in report["files"] if file["path"] == "core/operations/repo-topology.md"
    ][0]
    assert topology["schema"] == "repo-topology"
    assert topology["warnings"] == []


def test_validate_rejects_unknown_repo_topology_values(tmp_path: Path) -> None:
    _write(
        tmp_path / "core" / "operations" / "repo-topology.md",
        _repo_topology()
        .replace("role: site", "role: website")
        .replace("lifecycle: active", "lifecycle: graduated", 1)
        .replace("visibility: public", "visibility: secret"),
    )

    report = run(path=str(tmp_path))

    bad = [file for file in report["files"] if file["schema"] == "repo-topology"][0]
    assert report["ok"] is False
    assert any("role='website'" in error for error in bad["errors"])
    lifecycle_errors = [error for error in bad["errors"] if ".lifecycle" in error]
    assert lifecycle_errors == [
        "repos[0].lifecycle must not be 'graduated'; use a relationship instead"
    ]
    assert any("visibility='secret'" in error for error in bad["errors"])
    assert report["validation_categories"]["by_category"]["enum_mismatch"]["count"] >= 2


def test_validate_repo_topology_status_uses_topology_lifecycle(tmp_path: Path) -> None:
    _write(
        tmp_path / "core" / "operations" / "repo-topology.md",
        _repo_topology().replace("status: active", "status: running"),
    )

    report = run(path=str(tmp_path))

    bad = [file for file in report["files"] if file["schema"] == "repo-topology"][0]
    assert report["ok"] is False
    assert any("topology status='running'" in error for error in bad["errors"])


def test_validate_allows_proposed_topology_rename_remote_mismatch(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "core" / "operations" / "repo-topology.md",
        _repo_topology()
        .replace(
            "    lifecycle: active\n    relationship: execution_vehicle_for\n",
            "    lifecycle: proposed\n    relationship: execution_vehicle_for\n",
        )
        .replace("    repo_name: workshop-site\n", "    repo_name: renamed-workshop-site\n"),
    )

    report = run(path=str(tmp_path))

    topology = [file for file in report["files"] if file["schema"] == "repo-topology"][0]
    assert not any("remote must match" in error for error in topology["errors"])
    assert any("allowed for lifecycle 'proposed'" in warning for warning in topology["warnings"])


def test_validate_repo_topology_warns_on_sensitive_boundary_metadata(tmp_path: Path) -> None:
    _write(
        tmp_path / "core" / "operations" / "repo-topology.md",
        _repo_topology(
            "    raw_ledger_path: /Users/alex/private/books.ledger\n"
            "    provider_cache: raw exports live here\n"
        ),
    )

    report = run(path=str(tmp_path), strict=False)

    topology = [file for file in report["files"] if file["schema"] == "repo-topology"][0]
    assert report["ok"] is True
    assert any("raw_ledger_path" in warning for warning in topology["warnings"])
    assert any("local absolute path" in warning for warning in topology["warnings"])
    assert any("provider_cache" in warning for warning in topology["warnings"])

    strict_report = run(path=str(tmp_path), strict=True)
    assert strict_report["ok"] is False


def test_validate_repo_topology_warns_on_missing_safe_links(tmp_path: Path) -> None:
    _write(tmp_path / "core" / "operations" / "repo-topology.md", _repo_topology())

    report = run(path=str(tmp_path))

    topology = [file for file in report["files"] if file["schema"] == "repo-topology"][0]
    assert report["ok"] is True
    assert any("linked_offers" in warning for warning in topology["warnings"])
    assert any("linked_playbook_runs" in warning for warning in topology["warnings"])


def test_cross_refs_warn_on_missing_linked_pushes_target(tmp_path: Path) -> None:
    _write(
        tmp_path / "decisions" / "2026-05-06-broken.md",
        (
            "---\n"
            "date: 2026-05-06\n"
            "status: accepted\n"
            "linked_pushes:\n"
            "  - pushes/2026-05-06-missing/push.md\n"
            "---\n"
            "# broken\n"
        ),
    )

    report = run(path=str(tmp_path), cross_refs=True)

    assert report["ok"] is True
    assert report["summary"]["warnings"] == 1
    finding = report["cross_refs"]["warnings"][0]
    assert finding["code"] == "missing-target"
    assert finding["field"] == "linked_pushes"


def test_cross_refs_flag_campaign_status_transition_regressions(tmp_path: Path) -> None:
    # A newer campaign supersedes an older one but reports a status earlier
    # in the campaign lifecycle. The status-transition checker should flag it
    # against CAMPAIGN_STATUS_ORDER, not the offer order.
    _write(
        tmp_path / "campaigns" / "2026-05-old-push" / "campaign.md",
        (
            "---\n"
            "slug: old-push\n"
            "status: completed\n"  # order = 3
            "---\n"
            "# old push\n"
        ),
    )
    _write(
        tmp_path / "campaigns" / "2026-05-new-push" / "campaign.md",
        (
            "---\n"
            "slug: new-push\n"
            "status: draft\n"  # order = 0 — backward
            "supersedes: campaigns/2026-05-old-push/campaign.md\n"
            "---\n"
            "# new push\n"
        ),
    )

    report = run(path=str(tmp_path), cross_refs=True)

    transition_warnings = [
        w for w in report["cross_refs"]["warnings"] if w["code"] == "status-transition"
    ]
    assert len(transition_warnings) == 1
    assert "move backward" in transition_warnings[0]["message"]


def _data_source(
    *,
    provider: str = "google-ads",
    owner: str = "growth",
    privacy: str = "team_private",
    cadence: str = "daily",
    freshness: str = "2026-05-10",
    extra: str = "",
) -> str:
    return (
        "---\n"
        "type: data_source\n"
        f"provider: {provider}\n"
        f"owner: {owner}\n"
        f"privacy: {privacy}\n"
        f"cadence: {cadence}\n"
        f"freshness: {freshness}\n"
        "storage:\n"
        f"  primary: data/{provider}/daily.sqlite\n"
        "  snapshots:\n"
        f"    - data/{provider}/snapshots/{freshness}.csv\n"
        "reports:\n"
        f"  - reports/{freshness}-{provider}-weekly.md\n"
        f"{extra}"
        "---\n"
        f"# {provider} data source\n"
    )


def test_validate_accepts_well_formed_data_source(tmp_path: Path) -> None:
    _write(tmp_path / "data" / "google-ads" / "source.md", _data_source())

    report = run(path=str(tmp_path))

    assert report["ok"] is True, report
    record = next(file for file in report["files"] if file["schema"] == "data-sources")
    assert record["errors"] == []
    assert record["warnings"] == []


def test_validate_rejects_data_source_missing_required_keys(tmp_path: Path) -> None:
    _write(
        tmp_path / "data" / "google-ads" / "source.md",
        "---\ntype: data_source\nprovider: google-ads\n---\n# bad\n",
    )

    report = run(path=str(tmp_path))

    record = next(file for file in report["files"] if file["schema"] == "data-sources")
    assert report["ok"] is False
    assert "missing key: owner" in record["errors"]
    assert "missing key: privacy" in record["errors"]


def test_validate_rejects_data_source_empty_provider(tmp_path: Path) -> None:
    _write(
        tmp_path / "data" / "google-ads" / "source.md",
        (
            "---\n"
            "type: data_source\n"
            "provider: ''\n"
            "owner: growth\n"
            "privacy: team_private\n"
            "---\n"
            "# bad\n"
        ),
    )

    report = run(path=str(tmp_path))

    record = next(file for file in report["files"] if file["schema"] == "data-sources")
    assert report["ok"] is False
    assert "provider must be a non-empty string" in record["errors"]


def test_validate_rejects_data_source_bad_enums_and_dates(tmp_path: Path) -> None:
    _write(
        tmp_path / "data" / "google-ads" / "source.md",
        (
            "---\n"
            "type: data_source\n"
            "provider: google-ads\n"
            "owner: growth\n"
            "privacy: world_readable\n"
            "freshness: 2026/05/10\n"
            "---\n"
            "# bad\n"
        ),
    )

    report = run(path=str(tmp_path))

    record = next(file for file in report["files"] if file["schema"] == "data-sources")
    assert report["ok"] is False
    assert any("privacy=" in err for err in record["errors"])
    assert "freshness must be a YYYY-MM-DD date" in record["errors"]


def test_validate_warns_when_provider_folder_mismatches(tmp_path: Path) -> None:
    _write(
        tmp_path / "data" / "googleads" / "source.md",
        _data_source(provider="google-ads"),
    )

    report = run(path=str(tmp_path))

    record = next(file for file in report["files"] if file["schema"] == "data-sources")
    assert record["ok"] is True
    assert any("does not match the parent folder" in w for w in record["warnings"])


def test_validate_data_source_rejects_bad_storage_and_query_shape(tmp_path: Path) -> None:
    _write(
        tmp_path / "data" / "google-ads" / "source.md",
        (
            "---\n"
            "type: data_source\n"
            "provider: google-ads\n"
            "owner: growth\n"
            "privacy: team_private\n"
            "storage: data/google-ads/daily.sqlite\n"
            "reports:\n"
            "  - 42\n"
            "useful_queries:\n"
            "  - name: ''\n"
            "    query: ''\n"
            "---\n"
            "# bad\n"
        ),
    )

    report = run(path=str(tmp_path))

    record = next(file for file in report["files"] if file["schema"] == "data-sources")
    assert report["ok"] is False
    assert any("storage must be a mapping" in err for err in record["errors"])
    assert any("reports must be a list" in err for err in record["errors"])
    assert any("useful_queries[0].name" in err for err in record["errors"])
    assert any("useful_queries[0].query" in err for err in record["errors"])


def test_validate_data_source_blocks_secret_frontmatter(tmp_path: Path) -> None:
    _write(
        tmp_path / "data" / "google-ads" / "source.md",
        (
            "---\n"
            "type: data_source\n"
            "provider: google-ads\n"
            "owner: growth\n"
            "privacy: team_private\n"
            "api_key: not-a-real-key\n"
            "---\n"
            "# bad\n"
        ),
    )

    report = run(path=str(tmp_path))

    record = next(file for file in report["files"] if file["schema"] == "data-sources")
    assert report["ok"] is False
    assert any("must not contain secrets" in err for err in record["errors"])


def test_validate_cross_refs_resolve_linked_data_sources(tmp_path: Path) -> None:
    _write(tmp_path / "data" / "google-ads" / "source.md", _data_source())
    _write(
        tmp_path / "decisions" / "2026-05-11-google-ads-first.md",
        (
            "---\n"
            "date: 2026-05-11\n"
            "status: accepted\n"
            "linked_data_sources:\n"
            "  - data/google-ads/source.md\n"
            "---\n"
            "# Decision\n"
            "\n## Related links\n\n"
            "- [Google Ads data source](../data/google-ads/source.md)\n"
        ),
    )

    report = run(path=str(tmp_path), cross_refs=True)

    decision = next(
        file for file in report["files"] if file["path"].endswith("google-ads-first.md")
    )
    assert decision["warnings"] == []
    assert "linked_data_sources" in report["cross_refs"]["checked_fields"]


def test_validate_cross_refs_flags_missing_linked_data_source_target(tmp_path: Path) -> None:
    _write(
        tmp_path / "decisions" / "2026-05-11-google-ads-first.md",
        (
            "---\n"
            "date: 2026-05-11\n"
            "status: accepted\n"
            "linked_data_sources:\n"
            "  - data/google-ads/source.md\n"
            "---\n"
            "# Decision\n"
        ),
    )

    report = run(path=str(tmp_path), cross_refs=True, strict=True)

    decision = next(
        file for file in report["files"] if file["path"].endswith("google-ads-first.md")
    )
    assert decision["ok"] is False
    assert any(
        "linked_data_sources" in warning and "does not exist" in warning
        for warning in decision["warnings"]
    )
    assert any(
        finding["field"] == "linked_data_sources"
        and finding["target"] == "data/google-ads/source.md"
        for finding in report["cross_refs"]["warnings"]
    )


def test_validate_data_source_rejects_absolute_paths(tmp_path: Path) -> None:
    _write(
        tmp_path / "data" / "google-ads" / "source.md",
        (
            "---\n"
            "type: data_source\n"
            "provider: google-ads\n"
            "owner: growth\n"
            "privacy: team_private\n"
            "storage:\n"
            "  primary: /Users/devon/Desktop/google-ads.sqlite\n"
            "  snapshots:\n"
            "    - ~/Downloads/2026-05-10.csv\n"
            "reports:\n"
            "  - C:\\\\Users\\\\devon\\\\report.md\n"
            "---\n"
            "# bad\n"
        ),
    )

    report = run(path=str(tmp_path))

    record = next(file for file in report["files"] if file["schema"] == "data-sources")
    assert report["ok"] is False
    assert any("storage.primary must be a repo-relative path" in err for err in record["errors"])
    assert any(
        "storage.snapshots[0] must be a repo-relative path" in err for err in record["errors"]
    )
    assert any("reports[0] must be a repo-relative path" in err for err in record["errors"])


def test_validation_categories_carry_audience_and_operator_summary(tmp_path: Path) -> None:
    for index in range(2):
        _write(
            tmp_path / "core" / "offers" / f"offer-{index}" / "offer.md",
            "---\nstatus: running\n---\n# Offer\n",
        )

    report = run(path=str(tmp_path))
    categories = report["validation_categories"]

    assert categories["top_category"] == "missing_slug"
    assert categories["top_audience"] == "operator_decision"
    assert categories["top_operator_summary"]
    assert "schema" not in categories["top_operator_summary"].lower()

    entry = categories["by_category"]["missing_slug"]
    assert entry["audience"] == "operator_decision"
    assert entry["operator_summary"]
    assert entry["repair"]  # legacy field still present


def _many_missing_mirrors(tmp_path: Path, count: int) -> None:
    """Write one shared research target plus `count` decisions that link it
    without mirroring the link in ## Related links — one mirror warning each."""
    _write(
        tmp_path / "research" / "2026-04-29-topic-source.md",
        "---\ndate: 2026-04-29\ntopic: topic\nsource: source\n---\n# Topic\n",
    )
    for index in range(count):
        _write(
            tmp_path / "decisions" / f"2026-04-29-link-{index:03d}.md",
            (
                "---\n"
                "date: 2026-04-29\n"
                "status: accepted\n"
                "linked_research:\n"
                "  - research/2026-04-29-topic-source.md\n"
                "---\n"
                f"# Link {index}\n"
            ),
        )


def test_many_mirror_warnings_keep_grouped_summary_small(tmp_path: Path) -> None:
    _many_missing_mirrors(tmp_path, 40)

    report = run(path=str(tmp_path), cross_refs=True)

    # Full machine-readable detail is preserved for power users / repair commands.
    assert report["summary"]["warnings"] == 40
    assert len(report["cross_refs"]["warnings"]) == 40

    categories = report["validation_categories"]
    by_category = categories["by_category"]
    # All 40 warnings collapse into a single grouped cluster with capped examples.
    assert set(by_category) == {"missing_related_link_mirror"}
    cluster = by_category["missing_related_link_mirror"]
    assert cluster["count"] == 40
    assert cluster["audience"] == "mechanical"
    assert len(cluster["examples"]) <= 5

    # New owner-facing rollup separates blockers from bulk-repairable mirrors.
    assert categories["blocker_count"] == 0
    assert categories["mechanical_warning_count"] == 40
    assert categories["operator_warning_count"] == 0
    assert "40 bulk-repairable warning(s)" in categories["owner_summary"]


def test_owner_summary_splits_blockers_from_mechanical(tmp_path: Path) -> None:
    _many_missing_mirrors(tmp_path, 5)
    # A blocking frontmatter error: offer missing required slug.
    _write(
        tmp_path / "core" / "offers" / "broken" / "offer.md",
        "---\nstatus: running\n---\n# Offer\n",
    )

    report = run(path=str(tmp_path), cross_refs=True)
    categories = report["validation_categories"]

    assert categories["blocker_count"] >= 1
    assert categories["mechanical_warning_count"] == 5
    summary = categories["owner_summary"]
    assert "blocker(s) to fix" in summary
    assert "5 bulk-repairable warning(s)" in summary


def test_owner_summary_label_is_generic_for_all_mechanical_warnings() -> None:
    # `mechanical` covers related-link mirrors AND migration drift, so the rollup
    # label must not claim every mechanical warning is a related-link mirror.
    summary = _owner_summary(0, 1, 0)
    assert summary == "1 bulk-repairable warning(s)."
    assert "mirror" not in summary
    assert _owner_summary(0, 0, 0) == "No validation issues."


def test_render_human_collapses_warnings_by_default(tmp_path: Path, capsys) -> None:
    _many_missing_mirrors(tmp_path, 40)
    report = run(path=str(tmp_path), cross_refs=True)

    render_human(report, verbose=False)
    default_out = capsys.readouterr().out
    # No per-file warning lines for the 40 warning-only files by default
    # (rich may wrap long warning text, so assert on the stable path token).
    assert default_out.count("2026-04-29-link-") == 0
    # The grouped summary still names the cluster and the bulk-repair framing.
    assert "Bulk-repairable (mechanical)" in default_out
    assert "bulk-repairable warning(s)" in default_out

    render_human(report, verbose=True)
    verbose_out = capsys.readouterr().out
    # Verbose restores the full per-file detail for power users.
    assert verbose_out.count("2026-04-29-link-") == 40


def test_validate_push_media_fields(tmp_path: Path) -> None:
    base = _push("active")

    with_media = base.replace(
        "promise: Own the launch memory in git.\n",
        "promise: Own the launch memory in git.\n"
        "media_location: https://drive.google.com/drive/folders/fixture\n"
        "media_backend: google-drive\n",
    )
    _write(tmp_path / "pushes" / "2026-05-07-with-media" / "push.md", with_media)

    backend_only = base.replace(
        "promise: Own the launch memory in git.\n",
        "promise: Own the launch memory in git.\nmedia_backend: google-drive\n",
    )
    _write(tmp_path / "pushes" / "2026-05-08-backend-only" / "push.md", backend_only)

    empty_location = base.replace(
        "promise: Own the launch memory in git.\n",
        "promise: Own the launch memory in git.\nmedia_location: ''\n",
    )
    _write(tmp_path / "pushes" / "2026-05-09-empty-loc" / "push.md", empty_location)

    report = run(str(tmp_path))

    by_path = {f["path"]: f for f in report["files"]}
    good = by_path["pushes/2026-05-07-with-media/push.md"]
    assert good["ok"], good["errors"]
    backend = by_path["pushes/2026-05-08-backend-only/push.md"]
    assert any("media_location is missing" in e for e in backend["errors"])
    empty = by_path["pushes/2026-05-09-empty-loc/push.md"]
    assert any("media_location must be a non-empty string" in e for e in empty["errors"])


def test_cross_refs_survive_empty_markdown_link_destination(tmp_path: Path) -> None:
    _write(
        tmp_path / "decisions" / "2026-06-12-ok.md",
        (
            "---\ndate: 2026-06-12\nstatus: accepted\n---\n# ok\n\n"
            "A placeholder [link with empty destination]() should not crash "
            "the run, and [another](<>) odd shape survives too.\n"
        ),
    )

    report = run(str(tmp_path), cross_refs=True)

    assert isinstance(report["ok"], bool)


def test_validate_json_stays_parseable_on_internal_error(tmp_path: Path, monkeypatch) -> None:
    import json as json_mod

    from typer.testing import CliRunner

    from mb import validate as validate_pkg
    from mb.cli import app as cli_app

    def boom(**kwargs):
        raise IndexError("synthetic crash")

    monkeypatch.setattr(validate_pkg, "run", boom)
    result = CliRunner().invoke(cli_app, ["validate", str(tmp_path), "--json"])

    assert result.exit_code == 2
    payload = json_mod.loads(result.stdout)
    assert payload["ok"] is False
    assert payload["error"]["type"] == "IndexError"


def test_validate_paths_scopes_report_to_touched_files(tmp_path: Path) -> None:
    _write(
        tmp_path / "decisions" / "2026-06-12-mine.md",
        "---\ndate: 2026-06-12\nstatus: accepted\n---\n# mine\n",
    )
    _write(
        tmp_path / "decisions" / "2026-06-12-legacy-broken.md",
        "---\nstatus: nonsense\n---\n# legacy\n",
    )
    _write(
        tmp_path / "research" / "2026-06-12-other-claude-code.md",
        "---\ndate: 2026-06-12\ntopic: t\nsource: claude-code\n---\n# r\n",
    )

    full = run(str(tmp_path))
    assert full["ok"] is False  # legacy debt fails the unscoped run

    scoped = run(str(tmp_path), paths=["decisions/2026-06-12-mine.md", "research"])
    scoped_paths = {f["path"] for f in scoped["files"]}
    assert "decisions/2026-06-12-mine.md" in scoped_paths
    assert "research/2026-06-12-other-claude-code.md" in scoped_paths
    assert "decisions/2026-06-12-legacy-broken.md" not in scoped_paths
    assert scoped["ok"] is True
    assert scoped["scoped_paths"] == ["decisions/2026-06-12-mine.md", "research"]


def test_validate_paths_rejects_escapes(tmp_path: Path) -> None:
    import pytest as pytest_mod

    with pytest_mod.raises(ValueError):
        run(str(tmp_path), paths=["../outside"])


def _valid_bet() -> str:
    return (
        "---\nstatus: open\nopened: 2026-10-01\ndeadline: 2026-10-10\nappetite: 2 weeks\n"
        "hypothesis: h\nmetric: m\ntarget: t\nresult: ''\nlinked_decisions: []\n"
        "linked_research: []\nlinked_pushes: []\nlinked_outcomes: []\npublic: false\n"
        "channels: []\ntags: []\n---\n# Bet\n"
    )


def test_validate_names_the_allowed_status_values_in_the_rollup(tmp_path: Path) -> None:
    # #1122: the rollup an agent reads (`repair`, shared with `mb status` and
    # `mb doctor`) named no values, and its example `shipped` is valid nowhere.
    from mb.validate import SCHEMAS

    _write(
        tmp_path / "bets" / "2026-10-01-bad.md",
        _valid_bet().replace("status: open\n", "status: running\n"),
    )
    _write(
        tmp_path / "decisions" / "2026-10-01-bad.md",
        "---\ndate: 2026-10-01\nstatus: pending\n---\n# Bad\n",
    )

    report = run(path=str(tmp_path))

    entry = report["validation_categories"]["by_category"]["status_enum_mismatch"]
    assert entry["allowed_status"] == {
        "bets": sorted(SCHEMAS["bets"]["enums"]["status"]),
        "decisions": sorted(SCHEMAS["decisions"]["enums"]["status"]),
    }
    for text in (entry["repair"], entry["operator_summary"]):
        assert "bets: canceled | closed | open | paused" in text
        assert "decisions: accepted | proposed | rejected | running | superseded" in text
        assert "shipped" not in text
    assert "allowed_status" not in report["validation_categories"]["by_category"].get(
        "missing_required_key", {}
    )
    assert report["validation_categories"]["top_repair"] == entry["repair"]
    assert "shipped" not in report["validation_categories"]["top_operator_summary"]


def _wrong_topology_status_report(tmp_path: Path) -> dict[str, Any]:
    # At the real path with the real schema id, so the topology check runs (#1133).
    _write(
        tmp_path / "core" / "operations" / "repo-topology.md",
        _repo_topology().replace("status: active\n", "status: wrong\n"),
    )
    report = run(path=str(tmp_path))
    topology = [f for f in report["files"] if f["path"] == "core/operations/repo-topology.md"][0]
    assert topology["schema"] == "repo-topology"
    assert any(error.startswith("topology status='wrong'") for error in topology["errors"])
    assert "status_enum_mismatch" in report["validation_categories"]["by_category"]
    return report


def test_validate_leaves_other_status_like_enums_out_of_the_allowed_status_list(
    tmp_path: Path,
) -> None:
    report = _wrong_topology_status_report(tmp_path)

    for entry in report["validation_categories"]["by_category"].values():
        assert "allowed_status" not in entry


def test_validate_status_rollup_for_a_topology_status_has_no_stale_example(
    tmp_path: Path,
) -> None:
    report = _wrong_topology_status_report(tmp_path)

    top = report["validation_categories"]
    assert top["top_category"] == "status_enum_mismatch"
    assert "shipped" not in top["top_operator_summary"] + top["top_repair"]
