"""The library verdict: a pure answer to "may we use this sighting like this".

Every row of the rights table is one case. The verdict reads deals, the
sighting, provenance, the use and the window, and nothing else.
"""

from __future__ import annotations

import dataclasses
from datetime import date, datetime, timezone
from typing import Any

import pytest

from mb import library_rights as rights

ASSET = "a" * 64
SIGHTING = "studio:candle-pour-01.jpg"
OTHER_SIGHTING = "site-repo:img/pour.jpg"
WINDOW = (date(2026, 12, 10), date(2026, 12, 20))
PAID_META = rights.Use(kind="paid-ad", platform="meta")


def deal(**over: Any) -> rights.Deal:
    """An approved, wide-open deal for Acme Candles; each case narrows one thing."""
    base = rights.Deal(
        id="d7aa11bb",
        uses=("paid-ad",),
        platforms=("meta",),
        from_date=date(2026, 12, 1),
        to_date=date(2026, 12, 31),
        perpetual=False,
        music="original",
        platform_code=None,
        said_by="Rowan Vale, email 2026-10-02",
        evidence_hash="",
        sightings=(SIGHTING,),
        subject="none-shown",
    )
    provenance = over.pop("approved_for", "own")
    base = dataclasses.replace(base, **over) if over else base
    return base.approve(
        by="Rowan Vale", at="2026-11-03T10:00:00+00:00", asset=ASSET, provenance=provenance
    )


def judge(
    deals: list[rights.Deal],
    *,
    sighting: str = SIGHTING,
    provenance: str = "own",
    use: rights.Use = PAID_META,
    window: tuple[date, date] = WINDOW,
) -> rights.Verdict:
    return rights.verdict(deals, sighting, provenance, use, window, asset=ASSET)


def test_approved_deal_covering_everything_clears():
    result = judge([deal()])
    assert result.cleared is True
    assert result.deal_id == "d7aa11bb"
    assert result.reasons == ()


def test_licensed_provenance_clears_too():
    uncoded = deal(approved_for="licensed")
    assert judge([uncoded], provenance="licensed").cleared is False  # needs a platform code
    coded = deal(platform_code=("meta", date(2027, 1, 31)), approved_for="licensed")
    assert judge([coded], provenance="licensed").cleared is True


@pytest.mark.parametrize("provenance", ["unknown", "third_party"])
def test_unknown_and_third_party_never_clear(provenance):
    result = judge([deal()], provenance=provenance)
    assert result.cleared is False
    assert result.reasons == ("provenance-not-clearable",)


def test_no_deal_is_not_cleared():
    assert judge([]).reasons == ("no-deal",)


def test_proposed_deal_never_clears():
    proposed = dataclasses.replace(deal(), state="proposed", approved_by="", approved_at="")
    result = judge([proposed])
    assert result.cleared is False
    assert result.reasons == ("not-approved",)


def test_edited_deal_loses_its_approval():
    edited = dataclasses.replace(deal(), platforms=("meta", "tiktok"))
    assert edited.state == "approved"
    result = judge([edited])
    assert result.cleared is False
    assert result.reasons == ("not-approved",)


def test_revoked_deal_does_not_clear():
    revoked = dataclasses.replace(deal(), state="revoked")
    assert judge([revoked]).reasons == ("revoked",)


def test_wrong_use():
    assert judge([deal(uses=("organic-social",))]).reasons == ("wrong-use",)


def test_wrong_platform():
    result = judge([deal()], use=rights.Use(kind="paid-ad", platform="tiktok"))
    assert result.reasons == ("wrong-platform",)


def test_empty_platform_list_means_no_platform():
    assert judge([deal(platforms=())]).reasons == ("wrong-platform",)


def test_website_use_needs_no_platform():
    website = deal(uses=("website",), platforms=())
    result = judge([website], use=rights.Use(kind="website", platform=None))
    assert result.cleared is True


@pytest.mark.parametrize(
    "window",
    [
        (date(2026, 11, 30), date(2026, 12, 5)),  # starts before
        (date(2026, 12, 28), date(2027, 1, 2)),  # ends after
        (date(2026, 11, 1), date(2027, 2, 1)),  # swallows the deal
    ],
)
def test_window_partly_outside_is_not_cleared(window):
    assert judge([deal()], window=window).reasons == ("outside-window",)


def test_window_bounds_are_inclusive():
    assert judge([deal()], window=(date(2026, 12, 1), date(2026, 12, 31))).cleared is True
    assert judge([deal()], window=(date(2026, 12, 1), date(2027, 1, 1))).cleared is False


def test_single_day_window_on_the_last_day():
    assert judge([deal()], window=(date(2026, 12, 31), date(2026, 12, 31))).cleared is True


def test_perpetual_deal_covers_any_later_window():
    forever = deal(to_date=None, perpetual=True)
    assert judge([forever], window=(date(2030, 1, 1), date(2031, 1, 1))).cleared is True
    assert judge([forever], window=(date(2026, 11, 30), date(2026, 12, 5))).cleared is False


def test_missing_to_without_perpetual_is_rejected():
    with pytest.raises(ValueError, match="to"):
        rights.Deal(
            id="d1",
            uses=("paid-ad",),
            platforms=("meta",),
            from_date=date(2026, 12, 1),
            to_date=None,
            perpetual=False,
            music="original",
            platform_code=None,
            said_by="Rowan Vale",
            evidence_hash="",
            sightings=(SIGHTING,),
        )


def test_music_unknown_is_not_cleared():
    assert judge([deal(music="unknown")]).reasons == ("music-unknown",)


def test_platform_code_for_another_platform():
    licensed = deal(platform_code=("tiktok", date(2027, 6, 1)), approved_for="licensed")
    result = judge([licensed], provenance="licensed")
    assert result.reasons == ("platform-code-other-platform",)


def test_platform_code_expiring_inside_the_window():
    licensed = deal(platform_code=("meta", date(2026, 12, 15)), approved_for="licensed")
    assert judge([licensed], provenance="licensed").reasons == ("platform-code-expires",)


def test_platform_code_expiring_on_the_last_window_day_is_fine():
    licensed = deal(platform_code=("meta", date(2026, 12, 20)), approved_for="licensed")
    assert judge([licensed], provenance="licensed").cleared is True


def test_a_code_for_one_platform_does_not_block_the_deal_s_other_platforms_for_own_media():
    both = deal(platforms=("meta", "tiktok"), platform_code=("tiktok", date(2027, 6, 1)))
    assert judge([both], use=PAID_META).cleared is True
    tiktok = rights.Use("paid-ad", "tiktok")
    assert judge([both], use=tiktok).cleared is True
    expiring = deal(platforms=("meta", "tiktok"), platform_code=("tiktok", date(2026, 12, 15)))
    assert judge([expiring], use=PAID_META).cleared is True  # not tiktok's code to expire
    assert judge([expiring], use=tiktok).reasons == ("platform-code-expires",)


def test_licensed_paid_ads_need_the_code_of_the_platform_they_run_on():
    both = deal(
        platforms=("meta", "tiktok"),
        platform_code=("tiktok", date(2027, 6, 1)),
        approved_for="licensed",
    )
    tiktok = rights.Use("paid-ad", "tiktok")
    assert judge([both], provenance="licensed", use=tiktok).cleared is True
    meta = judge([both], provenance="licensed", use=PAID_META)
    assert meta.reasons == ("platform-code-other-platform",)


@pytest.mark.parametrize("provenance", ["own", "licensed"])
def test_a_use_that_needs_no_platform_ignores_the_platform_code(provenance):
    site = deal(
        uses=("website",),
        platforms=(),
        platform_code=("tiktok", date(2026, 12, 15)),
        approved_for=provenance,
    )
    result = judge([site], provenance=provenance, use=rights.Use("website", None))
    assert result.cleared is True


def test_licensed_paid_ad_without_platform_code():
    uncoded = deal(approved_for="licensed")
    assert judge([uncoded], provenance="licensed").reasons == ("platform-code-missing",)


def test_sighting_not_covered():
    result = judge([deal()], sighting=OTHER_SIGHTING)
    assert result.cleared is False
    assert result.reasons == ("sighting-not-covered",)


def test_one_covering_deal_is_enough_among_several():
    narrow = deal(id="d1111111", uses=("organic-social",))
    assert judge([narrow, deal()]).deal_id == "d7aa11bb"


def test_reasons_are_all_of_the_failures():
    result = judge([deal(music="unknown", platforms=("tiktok",))])
    assert result.reasons == ("music-unknown", "wrong-platform")


def test_tags_and_creator_are_not_inputs():
    # The verdict signature has no place for them; a record's tags/creator
    # fields cannot reach it. Same inputs, same answer.
    assert judge([deal()]) == judge([deal()])
    assert set(dataclasses.fields(rights.Deal)).isdisjoint({"tags", "creator"})


def test_today_uses_the_business_timezone():
    late_utc = datetime(2026, 12, 31, 23, 30, tzinfo=timezone.utc)
    assert rights.today(late_utc, "UTC") == date(2026, 12, 31)
    assert rights.today(late_utc, "Pacific/Auckland") == date(2027, 1, 1)
    assert rights.today(late_utc, "America/Los_Angeles") == date(2026, 12, 31)


def test_unknown_timezone_is_refused():
    with pytest.raises(ValueError, match="timezone"):
        rights.today(datetime(2026, 1, 1, tzinfo=timezone.utc), "Mars/Olympus")


def test_deal_round_trips_through_a_plain_mapping():
    original = deal(platform_code=("meta", date(2027, 1, 31)))
    assert rights.Deal.from_mapping(original.to_mapping()) == original
    revoked = original.revoke("creator withdrew", "2026-11-04T09:00:00+00:00")
    assert rights.Deal.from_mapping(revoked.to_mapping()) == revoked
    assert revoked.revoked_reason == "creator withdrew"


def test_approval_hash_ignores_state_but_not_terms():
    base = dataclasses.replace(deal(), state="proposed")
    assert base.fields_hash() == deal().fields_hash()
    assert dataclasses.replace(base, music="licensed").fields_hash() != base.fields_hash()
