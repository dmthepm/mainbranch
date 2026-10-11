"""Fixture-safe image rail smoke helpers."""

from __future__ import annotations

import base64
import importlib
import importlib.util
import json
import os
import struct
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import yaml

from mb import http_safe

DEFAULT_PUSH_SLUG = "2026-05-13-openai-image-rail-smoke"
DEFAULT_ASSET_ID = "fake-openai-image-001"
DEFAULT_PROMPT_KEY = "lost-thread-branch-map.v1"
DEFAULT_BATCH_CANDIDATE_COUNT = 8
DEFAULT_MODEL = "gpt-image-2"
DEFAULT_MODEL_SNAPSHOT = "gpt-image-2-2026-04-21"
DEFAULT_SIZE = "1024x1536"
DEFAULT_QUALITY = "medium"
DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_FAL_PUSH_SLUG = "2026-06-10-fal-image-rail-smoke"
DEFAULT_FAL_ASSET_ID = "fake-fal-image-001"
DEFAULT_FAL_MODEL = "fal-ai/flux/dev"
DEFAULT_FAL_QUALITY = "default"
DEFAULT_PROMPT = """\
Create a fixture-safe Facebook feed image-ad base for a fictional business
operating system called Northstar Ledger. Visualize the customer phrase
"I keep losing the thread": tangled red thread winds through scattered decision
cards, invoices, launch notes, and half-finished task lists, then resolves into
a clean branch-map made of labeled-but-unreadable cards connected to one central
archive object. Make the transformation readable in one second, with stronger
ad-like contrast than a neutral desk scene. Avoid a clean desk, split-screen
chaos/order layout, website hero composition, fake dashboard, gradient SaaS
background, and professional photoshoot look. Keep the upper-right area clean
for a later deterministic headline overlay. No rendered words, real brands,
real people, customer data, logos, screenshots, account details, or private
information.
"""
DEFAULT_CONCEPT_ID = "lost-thread-branch-map"
REFERENCE_ROLES = (
    "logo",
    "product_photo",
    "style_reference",
    "screenshot_reference",
    "background",
    "mask_source",
)
CREATIVE_PLAYBOOK_IDS = (
    "native_problem_scene",
    "specific_object_metaphor",
    "proof_artifact",
    "myth_vs_fact",
    "with_without_transformation",
    "crossed_out_problem_list",
    "founder_pov",
    "high_contrast_poster",
    "simple_chart_comparison",
    "testimonials_with_artifact",
    "us_vs_them_split",
    "simple_list_framework",
)
PLACEMENT_PRESETS: dict[str, dict[str, Any]] = {
    "facebook_feed_portrait_4x5": {
        "aspect_ratio": "4:5",
        "nearest_provider_size": "1024x1536",
        "recommended_generation_size": "1440x1800",
        "final_export_size": "1080x1350",
        "safe_zone": {
            "top": "10%",
            "bottom": "10%",
            "sides": "10%",
            "notes": "Keep focal point and overlay text inside conservative feed margins.",
        },
        "deterministic_overlay_expected": True,
        "source_boundary": (
            "Aspect ratio checked against public Meta guidance; pixel sizes are "
            "planning defaults. Verify current Ads Manager specs before launch."
        ),
        "validation": "Preview in Meta Ads Manager before launch.",
    },
    "facebook_feed_square_1x1": {
        "aspect_ratio": "1:1",
        "nearest_provider_size": "1024x1024",
        "recommended_generation_size": "1440x1440",
        "final_export_size": "1080x1080",
        "safe_zone": {
            "top": "10%",
            "bottom": "10%",
            "sides": "10%",
            "notes": "Keep the focal point centered for mobile feed crop.",
        },
        "deterministic_overlay_expected": True,
        "source_boundary": (
            "Planning preset for square feed/carousel-style creative. Verify current "
            "Ads Manager specs before launch."
        ),
        "validation": "Preview in Meta Ads Manager before launch.",
    },
    "facebook_story_reels_9x16": {
        "aspect_ratio": "9:16",
        "nearest_provider_size": "1024x1792",
        "recommended_generation_size": "1440x2560",
        "final_export_size": "1080x1920",
        "safe_zone": {
            "top": "14%",
            "bottom": "35%",
            "sides": "6%",
            "notes": "Keep critical content inside the center safe band.",
        },
        "deterministic_overlay_expected": True,
        "source_boundary": (
            "9:16 vertical guidance checked against public Meta Reels guidance; "
            "verify current Ads Manager specs before launch."
        ),
        "validation": "Preview Stories/Reels placements before launch.",
    },
}

SmokeState = Literal["generated", "blocked"]


@dataclass(frozen=True)
class ImageProvider:
    """Image rail provider registry entry.

    Provider selection is explicit: each smoke surface names exactly one
    provider id, and ``openai`` stays the default rail. Local credential
    presence (for example ``FAL_KEY``) never auto-selects a provider.
    ``blocker_fn`` and ``generate_fn`` name module attributes so tests can
    patch the same seams the OpenAI rail already exposes.
    """

    id: str
    name: str
    model: str
    model_snapshot: str | None
    size: str
    quality: str
    endpoint: str
    credential_env: str
    credential_ref: str
    default_push_slug: str
    default_asset_id: str
    index_lede: str
    failure_hint: str
    blocker_fn: str
    generate_fn: str


IMAGE_PROVIDERS: dict[str, ImageProvider] = {
    "openai": ImageProvider(
        id="openai",
        name="OpenAI",
        model=DEFAULT_MODEL,
        model_snapshot=DEFAULT_MODEL_SNAPSHOT,
        size=DEFAULT_SIZE,
        quality=DEFAULT_QUALITY,
        endpoint="v1/images/generations",
        credential_env="OPENAI_API_KEY",
        credential_ref="openai:image-generation",
        default_push_slug=DEFAULT_PUSH_SLUG,
        default_asset_id=DEFAULT_ASSET_ID,
        index_lede="the first narrow OpenAI image rail",
        failure_hint=(
            "Check the local provider account, organization verification, quota, "
            "model access, and network state."
        ),
        blocker_fn="_provider_blocker",
        generate_fn="_generate_openai_image",
    ),
    "fal": ImageProvider(
        id="fal",
        name="fal.ai",
        model=DEFAULT_FAL_MODEL,
        model_snapshot=None,
        size=DEFAULT_SIZE,
        quality=DEFAULT_FAL_QUALITY,
        endpoint="fal.run/fal-ai/flux/dev",
        credential_env="FAL_KEY",
        credential_ref="fal:image-generation",
        default_push_slug=DEFAULT_FAL_PUSH_SLUG,
        default_asset_id=DEFAULT_FAL_ASSET_ID,
        index_lede="the narrow fal.ai FLUX image rail",
        failure_hint=("Check the local fal.ai account, quota, model access, and network state."),
        blocker_fn="_fal_provider_blocker",
        generate_fn="_generate_fal_image",
    ),
}


def image_provider(provider_id: str) -> ImageProvider:
    """Return the explicitly selected provider spec; unknown ids fail loudly."""

    spec = IMAGE_PROVIDERS.get(provider_id)
    if spec is None:
        known = ", ".join(sorted(IMAGE_PROVIDERS))
        raise ValueError(
            f"Unknown image provider {provider_id!r}. Configured providers: {known}. "
            "Provider selection is explicit; local credentials never auto-select a provider."
        )
    return spec


def _provider_fn(name: str) -> Any:
    """Resolve a provider hook through module globals so test patches apply."""

    return globals()[name]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _logical_output(push_slug: str, asset_id: str, extension: str = "png") -> str:
    return f"mb-media://pushes/{push_slug}/images/{asset_id}.{extension}"


def _logical_review_board(push_slug: str) -> str:
    return f"mb-media://pushes/{push_slug}/review-board.md"


def _repo_relative(path: Path, repo: Path) -> str:
    return path.resolve().relative_to(repo.resolve()).as_posix()


def _repo_relative_or_logical(path: Path, repo: Path, logical_reference: str) -> str:
    try:
        return _repo_relative(path, repo)
    except ValueError:
        return logical_reference


def _media_path(repo: Path, media_root: str, push_slug: str, asset_id: str) -> Path:
    root = Path(media_root).expanduser()
    if not root.is_absolute():
        root = repo / root
    return root / "pushes" / push_slug / "images" / f"{asset_id}.png"


def _review_board_path(repo: Path, media_root: str, push_slug: str) -> Path:
    root = Path(media_root).expanduser()
    if not root.is_absolute():
        root = repo / root
    return root / "pushes" / push_slug / "review-board.md"


def _provider_blocker(generate: bool) -> tuple[str, str]:
    if not generate:
        return (
            "generation_not_approved",
            (
                "Provider generation was not requested. Re-run with --generate only after "
                "the operator approves the provider call and local credential boundary."
            ),
        )
    if not os.environ.get("OPENAI_API_KEY"):
        return (
            "missing_openai_api_key",
            (
                "OPENAI_API_KEY is not set in the local runtime. Do not paste provider "
                "keys into chat or committed repo files."
            ),
        )
    if importlib.util.find_spec("openai") is None:
        return (
            "missing_openai_package",
            "The optional openai Python package is not installed in the local runtime.",
        )
    return "", ""


def _generate_openai_image(prompt: str, *, model: str, size: str, quality: str) -> bytes:
    openai_mod: Any = importlib.import_module("openai")
    client = openai_mod.OpenAI()

    response = client.images.generate(
        model=model,
        prompt=prompt,
        size=size,
        quality=quality,
        n=1,
    )
    encoded = response.data[0].b64_json
    if not encoded:
        raise RuntimeError("OpenAI image response did not include b64_json output")
    return base64.b64decode(encoded)


def _fal_provider_blocker(generate: bool) -> tuple[str, str]:
    if not generate:
        return (
            "generation_not_approved",
            (
                "Provider generation was not requested. Re-run with --generate only after "
                "the operator approves the provider call and local credential boundary."
            ),
        )
    if not os.environ.get("FAL_KEY"):
        return (
            "missing_fal_key",
            (
                "FAL_KEY is not set in the local runtime. Do not paste provider "
                "keys into chat or committed repo files."
            ),
        )
    return "", ""


def _generate_fal_image(prompt: str, *, model: str, size: str, quality: str) -> bytes:
    import urllib.error
    import urllib.request

    del quality  # fal FLUX endpoints tune steps/guidance, not an OpenAI-style quality knob.
    fal_key = os.environ.get("FAL_KEY", "")
    if not fal_key:
        raise RuntimeError("FAL_KEY is not set in the local runtime")
    width_text, _, height_text = size.partition("x")
    request_body = json.dumps(
        {
            "prompt": prompt,
            "image_size": {"width": int(width_text), "height": int(height_text)},
            "num_images": 1,
            "output_format": "png",
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"https://fal.run/{model}",
        data=request_body,
        headers={
            "Authorization": f"Key {fal_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with http_safe.open_no_redirect(request, timeout=DEFAULT_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # `from None` drops the HTTPError, whose response body may echo
        # request details; only the status code may reach logs or records.
        raise RuntimeError(f"fal.ai request failed with HTTP {exc.code}") from None
    images = payload.get("images") if isinstance(payload, dict) else None
    image_url = ""
    if isinstance(images, list) and images and isinstance(images[0], dict):
        image_url = str(images[0].get("url") or "")
    if not image_url:
        raise RuntimeError("fal.ai image response did not include an image url")
    if image_url.startswith("data:"):
        _, _, encoded = image_url.partition(",")
        return base64.b64decode(encoded)
    if not image_url.startswith("https://"):
        raise RuntimeError("fal.ai image response returned a non-https image url")
    try:
        with urllib.request.urlopen(image_url, timeout=DEFAULT_TIMEOUT_SECONDS) as image_response:
            return bytes(image_response.read())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"fal.ai image download failed with HTTP {exc.code}") from None


def _png_dimensions(image_bytes: bytes) -> dict[str, int] | None:
    if len(image_bytes) < 24:
        return None
    if not image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    if image_bytes[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", image_bytes[16:24])
    return {"width": width, "height": height}


def review_concept(concept: dict[str, Any]) -> dict[str, Any]:
    """Return a structured creative review for a planned or generated concept."""

    joined = " ".join(
        str(concept.get(key, ""))
        for key in (
            "visual_job",
            "visual_metaphor",
            "composition",
            "text_overlay_plan",
            "claim_boundary",
            "prompt",
        )
    ).lower()
    source_files = concept.get("source_files")
    references = concept.get("references")
    source_bite_value = concept.get("source_bite")
    source_bite: dict[str, Any] = source_bite_value if isinstance(source_bite_value, dict) else {}
    genericness_value = concept.get("genericness_check")
    genericness: dict[str, Any] = genericness_value if isinstance(genericness_value, dict) else {}
    placement = str(concept.get("placement", ""))
    text_overlay_plan = str(concept.get("text_overlay_plan", "")).lower()
    negative_constraints = [str(item).lower() for item in concept.get("negative_constraints", [])]

    fake_ui_terms = ("real meta ui", "ads manager", "dashboard screenshot", "fake ui")
    private_terms = ("customer data", "account id", "private screenshot", "token")
    unsupported_claim_terms = (
        "guaranteed revenue",
        "guaranteed profit",
        "meta partnership",
        "before/after income",
    )
    negative_text = " ".join(negative_constraints)

    fake_ui_risk = (
        "fail"
        if any(term in joined for term in fake_ui_terms)
        and not any(
            "no real meta ui" in item or "avoid fake ui" in item for item in negative_constraints
        )
        else "pass"
    )
    unsafe_private_data = False
    for term in private_terms:
        if term not in joined:
            continue
        if f"no {term}" in negative_text:
            continue
        if "do not include" in joined and term in joined:
            continue
        unsafe_private_data = True
    private_data_risk = "fail" if unsafe_private_data else "pass"
    unsupported_claim = False
    for term in unsupported_claim_terms:
        if term not in joined:
            continue
        if f"do not imply {term}" in joined or f"do not promise {term}" in joined:
            continue
        if "do not imply" in joined and term in joined:
            continue
        if "do not promise" in joined and term in joined:
            continue
        if f"no {term}" in negative_text:
            continue
        unsupported_claim = True
    claim_safety = "fail" if unsupported_claim else "pass"
    readability = (
        "warning"
        if "text-in-image" in text_overlay_plan or "render text" in joined or "tiny text" in joined
        else "pass"
    )
    placement_fit = "pass" if placement in PLACEMENT_PRESETS else "warning"
    brand_fit = "pass" if source_files else "warning"
    visual_hook_strength = "pass" if concept.get("visual_metaphor") else "warning"
    one_second_clarity = "pass" if concept.get("visual_job") else "warning"
    ad_usefulness = "pass" if concept.get("audience_state") else "warning"
    avoidance_strategy_fit = _avoidance_strategy_fit(concept)
    avoidance_check = _avoidance_check(joined, concept)
    avoidance_risk = _avoidance_risk(avoidance_check)
    prompt_record_complete = (
        "pass" if concept.get("prompt_key") and concept.get("prompt") else "fail"
    )
    reference_copy_risk = _reference_copy_risk(concept)
    export_readiness = (
        "pass" if placement in PLACEMENT_PRESETS and concept.get("text_overlay_plan") else "warning"
    )
    source_bite_fit = (
        "pass"
        if source_bite.get("source_file")
        and source_bite.get("extracted_phrase")
        and source_bite.get("visual_translation")
        else "fail"
    )
    specific_to_offer = genericness.get("specific_to_this_offer")
    genericness_risk = (
        "pass" if isinstance(specific_to_offer, int) and specific_to_offer >= 4 else "fail"
    )
    ai_generic_risk = "warning" if not references and "generic ai art" in joined else "pass"
    visual_quality = _visual_quality_scores(
        concept,
        avoidance_risk=avoidance_risk,
        brand_fit=brand_fit,
    )
    ad_quality = _ad_quality_scores(
        concept,
        one_second_clarity=one_second_clarity,
        source_bite_fit=source_bite_fit,
        genericness_risk=genericness_risk,
        avoidance_check=avoidance_check,
    )
    risk = _risk_scores(
        ai_generic_risk=ai_generic_risk,
        genericness_risk=genericness_risk,
        claim_safety=claim_safety,
        private_data_risk=private_data_risk,
        fake_ui_risk=fake_ui_risk,
        readability=readability,
    )
    click_reason_fit = "pass" if ad_quality["likely_click_reason"] else "fail"

    checks = {
        "one_second_clarity": one_second_clarity,
        "visual_hook_strength": visual_hook_strength,
        "ad_usefulness": ad_usefulness,
        "source_bite_fit": source_bite_fit,
        "genericness_risk": genericness_risk,
        "avoidance_strategy_fit": avoidance_strategy_fit,
        "avoidance_risk": avoidance_risk,
        "prompt_record_complete": prompt_record_complete,
        "reference_copy_risk": reference_copy_risk,
        "export_readiness": export_readiness,
        "readability": readability,
        "placement_fit": placement_fit,
        "brand_fit": brand_fit,
        "claim_safety": claim_safety,
        "fake_ui_risk": fake_ui_risk,
        "policy_risk": "pass" if claim_safety == "pass" else "fail",
        "private_data_risk": private_data_risk,
        "ai_generic_risk": ai_generic_risk,
        "click_reason_fit": click_reason_fit,
    }
    notes = []
    if fake_ui_risk == "fail":
        notes.append("Remove dashboard or Ads Manager UI cues before generation.")
    if readability == "warning":
        notes.append("Prefer a text-free base image and deterministic overlay later.")
    if brand_fit == "warning":
        notes.append("Add source files or references before approving generation.")
    if placement_fit == "warning":
        notes.append("Use one of the supported Facebook placement presets.")
    if claim_safety == "fail":
        notes.append("Remove unsupported revenue, partnership, or before/after claims.")
    if private_data_risk == "fail":
        notes.append("Remove private data, account identifiers, and screenshots.")
    if source_bite_fit == "fail":
        notes.append("Add a source_bite before turning the concept into a prompt.")
    if genericness_risk == "fail":
        notes.append("Do not generate unless the concept is specific to this offer.")
    if avoidance_strategy_fit == "fail":
        notes.append("Add an avoidance_strategy with soft-avoid rules before generation.")
    if avoidance_risk != "pass":
        notes.append("Revise the concept against the avoidance_check before generation.")
    if prompt_record_complete == "fail":
        notes.append("Record prompt_key and prompt before provider generation.")
    if reference_copy_risk != "pass":
        notes.append("Reference traits must say what to borrow and what not to copy.")
    if export_readiness != "pass":
        notes.append("Add placement and post-processing expectations before export.")
    if click_reason_fit != "pass":
        notes.append("Beautiful but no click reason = reject.")

    scores = {
        "one_second_clarity": _review_score(one_second_clarity),
        "visual_hook_strength": _review_score(visual_hook_strength),
        "specificity": _review_score(ad_usefulness),
        "brand_fit": _review_score(brand_fit),
        "source_bite_fit": _review_score(source_bite_fit),
        "specific_to_this_offer": (specific_to_offer if isinstance(specific_to_offer, int) else 1),
        "native_feed_fit": avoidance_check["native_feed_fit"],
        "export_readiness": _review_score(export_readiness),
        "ai_generic_risk": _review_score(ai_generic_risk, risk=True),
    }

    status = "accepted"
    if "fail" in checks.values():
        status = "rejected"
    elif "warning" in checks.values():
        status = "needs_revision"
    decision = {
        "accepted": "accept",
        "needs_revision": "revise",
        "rejected": "reject",
    }[status]

    return {
        "status": status,
        "decision": decision,
        **checks,
        "visual_quality": visual_quality,
        "ad_quality": ad_quality,
        "risk": risk,
        "avoidance_check": avoidance_check,
        "scores": scores,
        "notes": notes,
    }


def _avoidance_strategy_fit(concept: dict[str, Any]) -> str:
    strategy = concept.get("avoidance_strategy")
    if not isinstance(strategy, dict):
        return "fail"
    avoids = strategy.get("avoids")
    if isinstance(avoids, list) and avoids and strategy.get("reason"):
        return "pass"
    return "fail"


def _avoidance_check(joined: str, concept: dict[str, Any]) -> dict[str, Any]:
    strategy = concept.get("avoidance_strategy")
    intentionally_uses = []
    if isinstance(strategy, dict) and isinstance(strategy.get("intentionally_uses"), list):
        intentionally_uses = [str(item).lower() for item in strategy["intentionally_uses"]]

    def intentional(*terms: str) -> bool:
        return any(any(term in item for term in terms) for item in intentionally_uses)

    def soft_check(*terms: str) -> str:
        matched = False
        for term in terms:
            index = joined.find(term)
            if index == -1:
                continue
            previous = joined[max(0, index - 220) : index]
            if "avoid" in previous or "no " in previous or "not " in previous:
                continue
            matched = True
        if not matched:
            return "pass"
        return "pass" if intentional(*terms) else "warning"

    stock_photo_risk = soft_check(
        "stock photo",
        "professional photoshoot",
        "business people",
        "modern office",
    )
    website_hero_risk = soft_check(
        "website hero",
        "gradient background",
        "empty wall",
        "centered product",
    )
    clean_desk_cliche_risk = soft_check(
        "clean desk",
        "coffee",
        "notebook",
        "plant",
        "productivity desk",
    )
    generic_saas_risk = soft_check(
        "saas gradient",
        "hologram dashboard",
        "glossy 3d icon",
        "growth chart",
        "fake dashboard",
    )
    ai_slop_risk = "warning" if "generic ai art" in joined else "pass"
    overpolished_risk = soft_check(
        "high-end commercial",
        "premium luxury",
        "modern minimalist",
        "cinematic lighting",
        "professional photoshoot",
    )

    warnings = [
        stock_photo_risk,
        website_hero_risk,
        clean_desk_cliche_risk,
        generic_saas_risk,
        ai_slop_risk,
        overpolished_risk,
    ].count("warning")
    native_feed_fit = max(1, 5 - warnings)
    too_safe_to_stop_scroll = "warning" if native_feed_fit < 4 else "pass"
    notes = []
    if stock_photo_risk != "pass":
        notes.append("Avoid stock-photo business imagery unless intentionally justified.")
    if website_hero_risk != "pass":
        notes.append("Avoid website-hero composition for feed creative.")
    if clean_desk_cliche_risk != "pass":
        notes.append("Replace clean desk productivity cliches with a source-bite metaphor.")
    if generic_saas_risk != "pass":
        notes.append("Avoid generic SaaS gradients, fake dashboards, and growth-chart tropes.")
    if ai_slop_risk != "pass":
        notes.append("Add source specificity and real-world texture before generation.")
    if overpolished_risk != "pass":
        notes.append("Avoid overpolished prompt language unless the brand requires it.")
    if too_safe_to_stop_scroll != "pass":
        notes.append("The concept is likely too safe to stop the scroll.")

    return {
        "stock_photo_risk": stock_photo_risk,
        "website_hero_risk": website_hero_risk,
        "clean_desk_cliche_risk": clean_desk_cliche_risk,
        "generic_saas_risk": generic_saas_risk,
        "ai_slop_risk": ai_slop_risk,
        "overpolished_risk": overpolished_risk,
        "native_feed_fit": native_feed_fit,
        "too_safe_to_stop_scroll": too_safe_to_stop_scroll,
        "notes": notes,
    }


def _avoidance_risk(avoidance_check: dict[str, Any]) -> str:
    values = [
        value
        for key, value in avoidance_check.items()
        if key.endswith("_risk") or key == "too_safe_to_stop_scroll"
    ]
    if "fail" in values:
        return "fail"
    if "warning" in values:
        return "warning"
    return "pass"


def _reference_copy_risk(concept: dict[str, Any]) -> str:
    references = concept.get("references")
    if not references:
        return "pass"
    if not isinstance(references, list):
        return "warning"
    for reference in references:
        if not isinstance(reference, dict):
            return "warning"
        if not reference.get("use_for") or not reference.get("do_not_copy"):
            return "warning"
    return "pass"


def _review_score(value: str, *, risk: bool = False) -> int:
    if value == "pass":
        return 5 if not risk else 1
    if value == "warning":
        return 3
    return 1 if not risk else 5


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _fixture_playbook_metadata(concept_id: str) -> dict[str, Any]:
    common_router_inputs = {
        "niche": "founder_tool",
        "offer_type": "open_source_business_os",
        "audience": "solo founder or operator",
        "proof_available": False,
        "brand_style": "tactile, technical, irreverent",
        "platform": "facebook_feed",
    }
    by_concept: dict[str, dict[str, Any]] = {
        DEFAULT_CONCEPT_ID: {
            "creative_playbook_id": "specific_object_metaphor",
            "source_bite_type": "customer_language",
            "router_reason": (
                "The source bite is emotional and abstract, so a specific object "
                "metaphor is more useful than chart proof."
            ),
            "playbook_fit": {
                "source_bite_fit": 5,
                "offer_fit": 5,
                "audience_fit": 4,
                "visual_distinctiveness": 5,
                "conversion_pattern_fit": 4,
            },
            "external_pattern_signal": {
                "source_type": "grok_synthesis",
                "pattern": "specific_object_metaphor",
                "confidence": "medium",
                "primary_source_verified": False,
            },
            "reference_influence_test": {
                "mode": "none",
                "effect_on_specificity": 4,
                "effect_on_native_feed_fit": 4,
                "effect_on_ai_slop_risk": 2,
            },
            "likely_click_reason": (
                "A founder who feels context slipping away recognizes the lost-thread "
                "problem before reading the overlay."
            ),
        },
        "operator-before-after-chaos": {
            "creative_playbook_id": "native_problem_scene",
            "source_bite_type": "offer",
            "router_reason": (
                "The offer bite is broad, so a native problem scene gives the abstract "
                "business-memory promise a concrete feed-native setting."
            ),
            "playbook_fit": {
                "source_bite_fit": 4,
                "offer_fit": 5,
                "audience_fit": 4,
                "visual_distinctiveness": 3,
                "conversion_pattern_fit": 4,
            },
            "external_pattern_signal": {
                "source_type": "grok_synthesis",
                "pattern": "native_problem_scene",
                "confidence": "medium",
                "primary_source_verified": False,
            },
            "reference_influence_test": {
                "mode": "text_traits",
                "effect_on_specificity": 4,
                "effect_on_native_feed_fit": 4,
                "effect_on_ai_slop_risk": 2,
            },
            "likely_click_reason": (
                "The operator sees scattered business facts becoming a map they own."
            ),
        },
        "mobile-safe-progress-path": {
            "creative_playbook_id": "proof_artifact",
            "source_bite_type": "push_brief",
            "router_reason": (
                "The push bite asks for the next practical move, so a proof-artifact "
                "checkpoint scene can make progress feel inspectable without fake data."
            ),
            "playbook_fit": {
                "source_bite_fit": 4,
                "offer_fit": 4,
                "audience_fit": 4,
                "visual_distinctiveness": 3,
                "conversion_pattern_fit": 3,
            },
            "external_pattern_signal": {
                "source_type": "grok_synthesis",
                "pattern": "proof_artifact",
                "confidence": "low",
                "primary_source_verified": False,
            },
            "reference_influence_test": {
                "mode": "none",
                "effect_on_specificity": 3,
                "effect_on_native_feed_fit": 3,
                "effect_on_ai_slop_risk": 3,
            },
            "likely_click_reason": (
                "The image promises a practical next step instead of another vague "
                "productivity dashboard."
            ),
        },
        "app-sprawl-native-scene": {
            "creative_playbook_id": "native_problem_scene",
            "source_bite_type": "customer_language",
            "router_reason": (
                "The source bite describes a native operating problem, so the best "
                "test is a feed-native scene before abstract proof."
            ),
            "playbook_fit": {
                "source_bite_fit": 5,
                "offer_fit": 4,
                "audience_fit": 5,
                "visual_distinctiveness": 4,
                "conversion_pattern_fit": 4,
            },
            "external_pattern_signal": {
                "source_type": "grok_synthesis",
                "pattern": "native_problem_scene",
                "confidence": "medium",
                "primary_source_verified": False,
            },
            "reference_influence_test": {
                "mode": "none",
                "effect_on_specificity": 4,
                "effect_on_native_feed_fit": 5,
                "effect_on_ai_slop_risk": 2,
            },
            "likely_click_reason": (
                "The scene looks like the founder's real tabs-and-notes problem."
            ),
        },
        "myth-vs-folder": {
            "creative_playbook_id": "myth_vs_fact",
            "source_bite_type": "objection",
            "router_reason": (
                "The source bite is a misconception about needing another app, so a "
                "myth/fact frame can create a fast belief shift."
            ),
            "playbook_fit": {
                "source_bite_fit": 4,
                "offer_fit": 4,
                "audience_fit": 4,
                "visual_distinctiveness": 3,
                "conversion_pattern_fit": 4,
            },
            "external_pattern_signal": {
                "source_type": "grok_synthesis",
                "pattern": "myth_vs_fact",
                "confidence": "low",
                "primary_source_verified": False,
            },
            "reference_influence_test": {
                "mode": "none",
                "effect_on_specificity": 3,
                "effect_on_native_feed_fit": 3,
                "effect_on_ai_slop_risk": 3,
            },
            "likely_click_reason": "The ad challenges the assumption that the fix is another app.",
        },
        "with-without-context": {
            "creative_playbook_id": "with_without_transformation",
            "source_bite_type": "problem_outcome_contrast",
            "router_reason": (
                "The source bite has a before/after operating-state contrast, so a "
                "with/without transformation can make the promise concrete."
            ),
            "playbook_fit": {
                "source_bite_fit": 5,
                "offer_fit": 5,
                "audience_fit": 4,
                "visual_distinctiveness": 4,
                "conversion_pattern_fit": 4,
            },
            "external_pattern_signal": {
                "source_type": "grok_synthesis",
                "pattern": "with_without_transformation",
                "confidence": "medium",
                "primary_source_verified": False,
            },
            "reference_influence_test": {
                "mode": "text_traits",
                "effect_on_specificity": 4,
                "effect_on_native_feed_fit": 4,
                "effect_on_ai_slop_risk": 2,
            },
            "likely_click_reason": (
                "The operator can see the cost of scattered context and the relief "
                "of a durable operating folder."
            ),
        },
        "crossed-out-tools": {
            "creative_playbook_id": "crossed_out_problem_list",
            "source_bite_type": "problem_list",
            "router_reason": (
                "The source bite names multiple repeated pains, so a crossed-out "
                "problem list can test whether visual checklist relief works."
            ),
            "playbook_fit": {
                "source_bite_fit": 4,
                "offer_fit": 4,
                "audience_fit": 4,
                "visual_distinctiveness": 3,
                "conversion_pattern_fit": 4,
            },
            "external_pattern_signal": {
                "source_type": "grok_synthesis",
                "pattern": "crossed_out_problem_list",
                "confidence": "medium",
                "primary_source_verified": False,
            },
            "reference_influence_test": {
                "mode": "none",
                "effect_on_specificity": 3,
                "effect_on_native_feed_fit": 3,
                "effect_on_ai_slop_risk": 3,
            },
            "likely_click_reason": "The operator recognizes three repeated pains at once.",
        },
        "founder-pov-checkpoint": {
            "creative_playbook_id": "founder_pov",
            "source_bite_type": "founder_note",
            "router_reason": (
                "The source bite is a founder/operator moment, so first-person desk "
                "perspective is a better test than a polished product scene."
            ),
            "playbook_fit": {
                "source_bite_fit": 4,
                "offer_fit": 4,
                "audience_fit": 5,
                "visual_distinctiveness": 4,
                "conversion_pattern_fit": 3,
            },
            "external_pattern_signal": {
                "source_type": "grok_synthesis",
                "pattern": "founder_pov",
                "confidence": "low",
                "primary_source_verified": False,
            },
            "reference_influence_test": {
                "mode": "text_traits",
                "effect_on_specificity": 4,
                "effect_on_native_feed_fit": 5,
                "effect_on_ai_slop_risk": 2,
            },
            "likely_click_reason": "The viewpoint feels like the viewer's own work session.",
        },
        "high-contrast-context-poster": {
            "creative_playbook_id": "high_contrast_poster",
            "source_bite_type": "customer_language",
            "router_reason": (
                "The source bite is emotionally simple, so a high-contrast poster "
                "tests thumb-stop without leaning into casual meme language."
            ),
            "playbook_fit": {
                "source_bite_fit": 4,
                "offer_fit": 4,
                "audience_fit": 3,
                "visual_distinctiveness": 5,
                "conversion_pattern_fit": 3,
            },
            "external_pattern_signal": {
                "source_type": "grok_synthesis",
                "pattern": "high_contrast_poster",
                "confidence": "low",
                "primary_source_verified": False,
            },
            "reference_influence_test": {
                "mode": "none",
                "effect_on_specificity": 3,
                "effect_on_native_feed_fit": 3,
                "effect_on_ai_slop_risk": 3,
            },
            "likely_click_reason": "The stark visual makes the continuity pain impossible to miss.",
        },
    }
    metadata = by_concept[concept_id]
    router_inputs = dict(common_router_inputs)
    router_inputs["source_bite_type"] = metadata["source_bite_type"]
    return {
        "creative_playbook_id": metadata["creative_playbook_id"],
        "router_inputs": router_inputs,
        "router_reason": metadata["router_reason"],
        "playbook_fit": metadata["playbook_fit"],
        "external_pattern_signal": metadata["external_pattern_signal"],
        "reference_influence_test": metadata["reference_influence_test"],
        "reference_influence": {
            "mode": metadata["reference_influence_test"]["mode"],
            "influence_score": None,
            "copy_risk": "pass",
        },
        "likely_click_reason": metadata["likely_click_reason"],
    }


def _visual_quality_scores(
    concept: dict[str, Any],
    *,
    avoidance_risk: str,
    brand_fit: str,
) -> dict[str, int]:
    composition = 5 if concept.get("visual_hierarchy") and concept.get("composition") else 3
    if not concept.get("composition"):
        composition = 1
    style = 5 if concept.get("camera_language") and concept.get("style_strength") else 3
    if brand_fit == "warning":
        style = min(style, 4)
    polish_control = {"pass": 5, "warning": 3, "fail": 1}.get(avoidance_risk, 3)
    return {
        "composition": composition,
        "style": style,
        "polish_control": polish_control,
    }


def _ad_quality_scores(
    concept: dict[str, Any],
    *,
    one_second_clarity: str,
    source_bite_fit: str,
    genericness_risk: str,
    avoidance_check: dict[str, Any],
) -> dict[str, Any]:
    problem_clarity = _review_score(one_second_clarity)
    desire_clarity = 5 if concept.get("visual_job") and concept.get("audience_state") else 3
    if genericness_risk == "fail":
        desire_clarity = min(desire_clarity, 2)
    curiosity_gap = 5 if concept.get("visual_metaphor") else 3
    offer_relevance = min(_review_score(source_bite_fit), _review_score(genericness_risk))
    thumb_stop = int(avoidance_check.get("native_feed_fit") or 1)
    return {
        "thumb_stop": thumb_stop,
        "problem_clarity": problem_clarity,
        "desire_clarity": desire_clarity,
        "curiosity_gap": curiosity_gap,
        "offer_relevance": offer_relevance,
        "likely_click_reason": str(concept.get("likely_click_reason") or "").strip(),
    }


def _risk_scores(
    *,
    ai_generic_risk: str,
    genericness_risk: str,
    claim_safety: str,
    private_data_risk: str,
    fake_ui_risk: str,
    readability: str,
) -> dict[str, Any]:
    compliance_values = [claim_safety, private_data_risk, fake_ui_risk]
    if "fail" in compliance_values:
        compliance_risk = "fail"
    elif readability == "warning":
        compliance_risk = "warning"
    else:
        compliance_risk = "pass"
    return {
        "ai_slop_risk": _review_score(ai_generic_risk, risk=True),
        "genericness_risk": _review_score(genericness_risk, risk=True),
        "compliance_risk": compliance_risk,
    }


def _extra_fixture_concepts(push_slug: str, common_sources: list[str]) -> list[dict[str, Any]]:
    base = {
        "status": "planned",
        "prompt_strategy": "creative_director_brief_first_no_text_base",
        "viewer_scroll_context": "cold Facebook feed",
        "placement": "facebook_feed_portrait_4x5",
        "placement_details": PLACEMENT_PRESETS["facebook_feed_portrait_4x5"],
        "text_overlay_plan": "text-free base image; deterministic overlay later",
        "source_files": common_sources,
        "references": [],
        "reference_trait_extraction": [],
        "claim_boundary": (
            "do not imply automatic decisions, guaranteed outcomes, or provider partnership"
        ),
        "negative_constraints": [
            "no real Meta UI",
            "no real logos",
            "no rendered words",
            "no customer data",
            "no unsupported outcome claim",
        ],
    }

    extras = [
        {
            "concept_id": "app-sprawl-native-scene",
            "prompt_key": "app-sprawl-native-scene.v1",
            "source_bite": {
                "source_file": "research/customer-language.md",
                "source_type": "customer_language",
                "extracted_phrase": "everything is scattered across too many places",
                "insight": "The problem is visible in the operator's live work surface.",
                "visual_translation": (
                    "browser tabs, notes, and invoices crowding a laptop while one "
                    "folder anchors the scene"
                ),
            },
            "genericness_check": {
                "could_fit_notion": True,
                "could_fit_asana": True,
                "could_fit_quickbooks": False,
                "could_fit_generic_coaching_offer": False,
                "could_fit_generic_productivity_app": True,
                "could_fit_any_coaching_offer": False,
                "could_fit_accounting_software": False,
                "specific_to_this_offer": 4,
                "reason": "The folder-owned business memory cue narrows a common tab-sprawl scene.",
            },
            "avoidance_strategy": {
                "avoids": [
                    "stock-photo business imagery",
                    "fake dashboard",
                    "generic SaaS gradient",
                ],
                "intentionally_uses": [],
                "reason": "Uses a native problem scene instead of a polished product mockup.",
            },
            "first_second_read": "too many open loops, one owned business folder",
            "audience_state": "operator has too many tabs and notes open after a work session",
            "visual_job": "make app sprawl feel familiar and solvable",
            "visual_metaphor": "one physical folder grounding a messy laptop scene",
            "composition": (
                "phone-camera desk scene with laptop tabs, notes, and one "
                "labeled-but-unreadable folder"
            ),
            "visual_hierarchy": {
                "primary_focal_point": "owned folder beside laptop",
                "secondary_focal_point": "messy tabs and notes",
                "text_zone": "top third",
            },
            "camera_language": "native phone snapshot with natural desk mess",
            "style_strength": "lo-fi and specific, not polished",
            "emotional_tone": "recognition before relief",
            "prompt": (
                "Create a feed-native phone-style Facebook ad base image showing a "
                "founder desk with too many browser tabs, handwritten notes, and one "
                "plain business folder anchoring the mess. No readable text, UI, logos, "
                "customer data, or private details."
            ),
        },
        {
            "concept_id": "myth-vs-folder",
            "prompt_key": "myth-vs-folder.v1",
            "source_bite": {
                "source_file": "core/audience.md",
                "source_type": "objection",
                "extracted_phrase": "I probably need another app",
                "insight": (
                    "The audience may misdiagnose the memory problem as a "
                    "software-shopping problem."
                ),
                "visual_translation": "a pile of app icons fading behind one durable local folder",
            },
            "genericness_check": {
                "could_fit_notion": True,
                "could_fit_asana": True,
                "could_fit_quickbooks": False,
                "could_fit_generic_coaching_offer": False,
                "could_fit_generic_productivity_app": True,
                "could_fit_any_coaching_offer": False,
                "could_fit_accounting_software": False,
                "specific_to_this_offer": 4,
                "reason": "The local folder and owned-memory frame point back to Main Branch.",
            },
            "avoidance_strategy": {
                "avoids": ["fake app logos", "generic SaaS gradient", "website hero composition"],
                "intentionally_uses": [],
                "reason": "Tests an educational split without using real trademarks.",
            },
            "first_second_read": "not another app; one owned folder",
            "audience_state": "operator thinks the fix is buying or configuring another tool",
            "visual_job": "challenge the app-shopping misconception",
            "visual_metaphor": "ghosted generic app tiles behind a plain local folder",
            "composition": (
                "simple split-feel poster with a crossed-out app pile and one tactile folder"
            ),
            "visual_hierarchy": {
                "primary_focal_point": "plain folder",
                "secondary_focal_point": "crossed-out generic app pile",
                "text_zone": "upper right",
            },
            "camera_language": "flat editorial poster with tactile paper objects",
            "style_strength": "educational, high contrast, not glossy",
            "emotional_tone": "belief shift",
            "prompt": (
                "Create a text-free Facebook ad base image that visually contrasts a "
                "faded pile of generic unlabeled app tiles with one tactile local "
                "business folder. No rendered words, real logos, UI, customer data, "
                "or private details."
            ),
        },
        {
            "concept_id": "with-without-context",
            "prompt_key": "with-without-context.v1",
            "source_bite": {
                "source_file": "core/offer.md",
                "source_type": "problem_outcome_contrast",
                "extracted_phrase": "stop re-explaining the business every session",
                "insight": (
                    "The core transformation is from repeated context setup to preserved memory."
                ),
                "visual_translation": (
                    "two work surfaces: repeated sticky-note explanations versus "
                    "one connected repo map"
                ),
            },
            "genericness_check": {
                "could_fit_notion": True,
                "could_fit_asana": False,
                "could_fit_quickbooks": False,
                "could_fit_generic_coaching_offer": False,
                "could_fit_generic_productivity_app": True,
                "could_fit_any_coaching_offer": False,
                "could_fit_accounting_software": False,
                "specific_to_this_offer": 5,
                "reason": (
                    "The repeated re-explanation pain is tied to AI-assisted business memory."
                ),
            },
            "avoidance_strategy": {
                "avoids": ["split-screen chaos/order cliché", "clean desk productivity cliché"],
                "intentionally_uses": ["before/after contrast"],
                "reason": (
                    "Uses transformation contrast, but grounds it in source-specific "
                    "re-explanation."
                ),
            },
            "first_second_read": "without memory versus with durable business context",
            "audience_state": "operator keeps rebuilding context before useful work starts",
            "visual_job": "make the cost of re-explaining visible",
            "visual_metaphor": "sticky-note repetition becoming one connected map",
            "composition": (
                "subtle left/right transformation with sticky notes moving into a clean branch map"
            ),
            "visual_hierarchy": {
                "primary_focal_point": "connected branch map",
                "secondary_focal_point": "repeated sticky notes",
                "text_zone": "top center",
            },
            "camera_language": "editorial tabletop comparison, not sterile",
            "style_strength": "clear contrast with real paper texture",
            "emotional_tone": "frustration turning into relief",
            "prompt": (
                "Create a text-free Facebook feed ad base image showing a before/after "
                "operating-memory contrast: repeated sticky-note explanations resolving "
                "into one connected branch map. No readable words, logos, UI, customer "
                "data, or private details."
            ),
        },
        {
            "concept_id": "crossed-out-tools",
            "prompt_key": "crossed-out-tools.v1",
            "source_bite": {
                "source_file": "research/customer-language.md",
                "source_type": "problem_list",
                "extracted_phrase": "I forgot the decision, the offer, and the next step",
                "insight": "The pain is a cluster of repeated operating-memory failures.",
                "visual_translation": (
                    "three unlabeled problem cards crossed out beside one branch-map card"
                ),
            },
            "genericness_check": {
                "could_fit_notion": True,
                "could_fit_asana": True,
                "could_fit_quickbooks": False,
                "could_fit_generic_coaching_offer": True,
                "could_fit_generic_productivity_app": True,
                "could_fit_any_coaching_offer": False,
                "could_fit_accounting_software": False,
                "specific_to_this_offer": 4,
                "reason": (
                    "The decision/offer/next-step trio ties the checklist to the "
                    "business repo model."
                ),
            },
            "avoidance_strategy": {
                "avoids": ["tiny unreadable text", "generic checklist stock art"],
                "intentionally_uses": ["crossed-out problem list"],
                "reason": "Tests checklist relief while keeping final copy deterministic.",
            },
            "first_second_read": "the recurring memory failures get crossed out",
            "audience_state": "operator loses decisions, offers, and next steps between sessions",
            "visual_job": "make the solution feel like eliminating repeated pains",
            "visual_metaphor": "crossed-out problem cards beside one branch-map card",
            "composition": (
                "bold card layout with three crossed-out icons and one grounded folder card"
            ),
            "visual_hierarchy": {
                "primary_focal_point": "crossed-out problem cards",
                "secondary_focal_point": "branch-map card",
                "text_zone": "bottom third",
            },
            "camera_language": "simple poster-card composition",
            "style_strength": "bold, legible, controlled",
            "emotional_tone": "satisfying cleanup",
            "prompt": (
                "Create a text-free Facebook ad base image with three unlabeled problem "
                "cards crossed out and one clear branch-map card beside them. No readable "
                "words, logos, UI, customer data, or private details."
            ),
        },
        {
            "concept_id": "founder-pov-checkpoint",
            "prompt_key": "founder-pov-checkpoint.v1",
            "source_bite": {
                "source_file": f"pushes/{push_slug}/push.md",
                "source_type": "founder_note",
                "extracted_phrase": "what did we decide last time?",
                "insight": "The ad can start from the founder's own return-to-work moment.",
                "visual_translation": (
                    "first-person hand opening a checkpoint folder next to yesterday's notes"
                ),
            },
            "genericness_check": {
                "could_fit_notion": True,
                "could_fit_asana": False,
                "could_fit_quickbooks": False,
                "could_fit_generic_coaching_offer": False,
                "could_fit_generic_productivity_app": True,
                "could_fit_any_coaching_offer": False,
                "could_fit_accounting_software": False,
                "specific_to_this_offer": 4,
                "reason": "The checkpoint and decision-memory language tie the POV to Main Branch.",
            },
            "avoidance_strategy": {
                "avoids": ["stock-photo founder pose", "fake testimonial", "polished office"],
                "intentionally_uses": ["founder point of view"],
                "reason": "Keeps the scene first-person and tactile rather than influencer-style.",
            },
            "first_second_read": "opening yesterday's decision checkpoint",
            "audience_state": "founder is resuming after a context gap",
            "visual_job": "make preserved decision memory feel personal",
            "visual_metaphor": "hand opening a checkpoint folder beside yesterday's notes",
            "composition": "first-person phone-camera view of hand, folder, and scattered notes",
            "visual_hierarchy": {
                "primary_focal_point": "hand opening checkpoint folder",
                "secondary_focal_point": "yesterday notes",
                "text_zone": "upper left",
            },
            "camera_language": "first-person founder POV",
            "style_strength": "native, imperfect, close-range",
            "emotional_tone": "relief on return",
            "prompt": (
                "Create a first-person founder POV Facebook ad base image: a hand opens "
                "a plain checkpoint folder beside yesterday's messy notes. No readable "
                "words, face, logos, UI, customer data, or private details."
            ),
        },
        {
            "concept_id": "high-contrast-context-poster",
            "prompt_key": "high-contrast-context-poster.v1",
            "source_bite": {
                "source_file": "research/customer-language.md",
                "source_type": "customer_language",
                "extracted_phrase": "starting from zero every Monday",
                "insight": "The emotional hook is the waste of restarting context.",
                "visual_translation": "a stark reset button cracked by a small branch map",
            },
            "genericness_check": {
                "could_fit_notion": True,
                "could_fit_asana": True,
                "could_fit_quickbooks": False,
                "could_fit_generic_coaching_offer": True,
                "could_fit_generic_productivity_app": True,
                "could_fit_any_coaching_offer": True,
                "could_fit_accounting_software": False,
                "specific_to_this_offer": 4,
                "reason": "The branch-map reset visual narrows a broad restart frustration.",
            },
            "avoidance_strategy": {
                "avoids": ["casual meme template", "generic motivational poster", "glossy 3D icon"],
                "intentionally_uses": ["high contrast poster"],
                "reason": "Tests thumb-stop with a poster frame without drifting into meme tone.",
            },
            "first_second_read": "stop starting from zero",
            "audience_state": "operator dreads rebuilding context at the start of the week",
            "visual_job": "create a sharp pattern interrupt around reset fatigue",
            "visual_metaphor": "cracked reset button interrupted by a small branch map",
            "composition": (
                "high-contrast poster object scene, large reset object, branch-map detail"
            ),
            "visual_hierarchy": {
                "primary_focal_point": "cracked reset object",
                "secondary_focal_point": "branch-map detail",
                "text_zone": "top third",
            },
            "camera_language": "bold poster-like still life",
            "style_strength": "high contrast, spare, tactile",
            "emotional_tone": "frustrated pattern interrupt",
            "prompt": (
                "Create a text-free high-contrast Facebook ad base image: a stark reset "
                "button-like object cracked by a small branch-map detail. No rendered "
                "words, logos, UI, customer data, or private details."
            ),
        },
    ]
    return [{**base, **extra} for extra in extras]


def fixture_facebook_image_concepts(push_slug: str) -> list[dict[str, Any]]:
    """Build reviewable fixture concepts for the smoke image index."""

    common_sources = [
        "core/offer.md",
        "core/audience.md",
        "core/proof/testimonials.md",
        "core/brand/visual-style.md",
        "research/customer-language.md",
        f"pushes/{push_slug}/push.md",
    ]
    concepts: list[dict[str, Any]] = [
        {
            "concept_id": DEFAULT_CONCEPT_ID,
            "status": "planned",
            "prompt_key": DEFAULT_PROMPT_KEY,
            "creative_playbook": {
                "id": "specific_object_metaphor",
                "status": "candidate",
                "legacy_label": "technical-founder",
                "use_when": [
                    "audience speaks in systems, workflows, and operating clarity",
                    "offer promise is about memory, process, or context continuity",
                ],
                "default_avoid": [
                    "generic SaaS gradient",
                    "fake dashboard",
                    "hologram UI",
                    "robot assistant",
                ],
                "useful_metaphors": [
                    "dependency graph",
                    "broken pipeline",
                    "incident board",
                    "branch map",
                    "lost thread",
                ],
                "risky_metaphors": [
                    "glowing brain",
                    "robot assistant",
                    "generic command center",
                ],
                "prompt_bias": [
                    "tactile systems",
                    "real artifacts",
                    "visible consequence",
                    "source-bite metaphor",
                ],
            },
            "prompt_strategy": "creative_director_brief_first_no_text_base",
            "prompt_strategy_notes": (
                "Default production path: brief the visual job first, generate "
                "a text-free base image, then apply deterministic overlay later."
            ),
            "viewer_scroll_context": "cold Facebook feed",
            "source_bite": {
                "source_file": "research/customer-language.md",
                "source_type": "customer_language",
                "extracted_phrase": "I keep losing the thread",
                "insight": (
                    "The pain is not generic clutter; the operator loses continuity "
                    "when decisions and tasks scatter across tools."
                ),
                "visual_translation": (
                    "tangled red thread becoming a clean branch map connected to "
                    "one durable business archive"
                ),
            },
            "genericness_check": {
                "could_fit_notion": False,
                "could_fit_asana": False,
                "could_fit_quickbooks": False,
                "could_fit_generic_coaching_offer": False,
                "could_fit_generic_productivity_app": False,
                "could_fit_any_coaching_offer": False,
                "could_fit_accounting_software": False,
                "specific_to_this_offer": 5,
                "reason": (
                    "The thread, branch-map, and archive metaphor expresses the "
                    "repo-backed business memory promise."
                ),
            },
            "avoidance_strategy": {
                "avoids": [
                    "stock-photo business imagery",
                    "clean desk productivity cliché",
                    "split-screen chaos/order cliché",
                    "website hero composition",
                    "fake dashboard",
                    "generic SaaS gradient",
                ],
                "intentionally_uses": [],
                "reason": (
                    "Uses a customer-language source-bite metaphor instead of "
                    "generic productivity imagery."
                ),
            },
            "first_second_read": "lost business thread becomes one durable branch map",
            "audience_state": "operator is resuming work after context switching across tools",
            "visual_job": (
                "make continuity loss visible before showing the repo-backed memory fix"
            ),
            "visual_metaphor": ("tangled red thread resolving into a clean branch map and archive"),
            "composition": (
                "feed-native tactile maze of red thread and scattered cards, with one "
                "clear branch path emerging toward a central archive and upper-right "
                "overlay space"
            ),
            "visual_hierarchy": {
                "primary_focal_point": "red thread becoming a branch map",
                "secondary_focal_point": "central archive object",
                "text_zone": "upper right",
            },
            "camera_language": "slight top-down editorial ad composition",
            "style_strength": "specific metaphor, restrained production polish",
            "emotional_tone": "relief after broken continuity",
            "placement": "facebook_feed_portrait_4x5",
            "placement_details": PLACEMENT_PRESETS["facebook_feed_portrait_4x5"],
            "text_overlay_plan": "text-free base image; deterministic overlay later, max 4 words",
            "source_files": common_sources,
            "claim_boundary": (
                "do not imply automatic decisions, guaranteed outcomes, or provider partnership"
            ),
            "references": [],
            "reference_trait_extraction": [],
            "prompt": DEFAULT_PROMPT.strip(),
            "negative_constraints": [
                "no real Meta UI",
                "no real logos",
                "no rendered words",
                "no revenue screenshots",
                "no automatic outcome claim",
                "no customer data",
            ],
        },
        {
            "concept_id": "operator-before-after-chaos",
            "status": "planned",
            "prompt_key": "durable-memory-archive-map.v1",
            "prompt_strategy": "reference_aware_no_text_base",
            "prompt_strategy_notes": (
                "Use the style reference for mood and composition only; do not "
                "copy subjects, logos, text, or private details."
            ),
            "viewer_scroll_context": "mobile feed between founder and SaaS posts",
            "source_bite": {
                "source_file": "core/offer.md",
                "source_type": "offer",
                "extracted_phrase": "the business repo is durable business memory",
                "insight": ("The offer is not another dashboard; it is memory the operator owns."),
                "visual_translation": (
                    "a private archive object quietly connecting decisions, goals, "
                    "pushes, and proof cards"
                ),
            },
            "genericness_check": {
                "could_fit_notion": False,
                "could_fit_asana": False,
                "could_fit_quickbooks": False,
                "could_fit_generic_coaching_offer": False,
                "could_fit_generic_productivity_app": False,
                "could_fit_any_coaching_offer": False,
                "could_fit_accounting_software": False,
                "specific_to_this_offer": 5,
                "reason": (
                    "The repo/archive memory metaphor is specific to Main Branch's "
                    "durable business-memory promise."
                ),
            },
            "avoidance_strategy": {
                "avoids": [
                    "fake dashboard",
                    "generic SaaS gradient",
                    "hologram dashboard",
                    "glossy 3D icons",
                    "website hero composition",
                ],
                "intentionally_uses": [],
                "reason": "Uses a repo/archive metaphor instead of dashboard or SaaS tropes.",
            },
            "first_second_read": "scattered business facts snap into a simple map",
            "audience_state": "operator has business facts scattered across docs and dashboards",
            "visual_job": "make scattered operating memory feel visible and organized",
            "visual_metaphor": "paper fragments forming a simple business map on a wall",
            "composition": "square crop, centered map, clear negative space around the focal point",
            "visual_hierarchy": {
                "primary_focal_point": "simple business map",
                "secondary_focal_point": "paper fragments",
                "text_zone": "top third",
            },
            "camera_language": "straight-on editorial wall composition",
            "style_strength": "clean but still native to the feed",
            "emotional_tone": "control without hype",
            "placement": "facebook_feed_square_1x1",
            "placement_details": PLACEMENT_PRESETS["facebook_feed_square_1x1"],
            "text_overlay_plan": "no rendered text; reserve top third for overlay",
            "source_files": common_sources,
            "claim_boundary": "do not promise automatic growth or financial outcomes",
            "references": [
                {
                    "id": "style-001",
                    "role": "style_reference",
                    "path": "mb-media://references/style-001.png",
                    "safe_to_share": False,
                    "approval_required": True,
                    "privacy_level": "private",
                    "use_for": "color mood and simple composition",
                    "do_not_copy": "exact subject, logos, text, or private details",
                }
            ],
            "reference_trait_extraction": [
                {
                    "reference_id": "style-001",
                    "traits": {
                        "palette": "muted warm neutrals with one grounded accent",
                        "composition": "simple focal object with visible surrounding context",
                        "lighting": "natural, tactile, not glossy studio light",
                    },
                    "do_not_copy": "exact subject, text, logos, layout, or private details",
                }
            ],
            "prompt": (
                "Create a fixture-safe square Facebook ad base image for a "
                "fictional business operating system. Show scattered paper "
                "fragments forming a clean business map. No text, logos, "
                "screenshots, private data, or real brands."
            ),
            "negative_constraints": [
                "no real logos",
                "no rendered words",
                "no private screenshots",
                "no guaranteed outcome claim",
            ],
        },
        {
            "concept_id": "mobile-safe-progress-path",
            "status": "planned",
            "prompt_key": "mobile-safe-progress-path.v1",
            "prompt_strategy": "creative_director_brief_first_no_text_base",
            "prompt_strategy_notes": (
                "Plan the vertical composition and text-safe zone before any provider call."
            ),
            "viewer_scroll_context": "story or reels vertical placement",
            "source_bite": {
                "source_file": f"pushes/{push_slug}/push.md",
                "source_type": "push_brief",
                "extracted_phrase": "what is the next practical move?",
                "insight": (
                    "The operator wants the system to preserve enough context to make "
                    "the next action obvious."
                ),
                "visual_translation": (
                    "one lit checkpoint emerging from launch notes while the rest of "
                    "the clutter stays out of the safe zone"
                ),
            },
            "genericness_check": {
                "could_fit_notion": False,
                "could_fit_asana": False,
                "could_fit_quickbooks": False,
                "could_fit_generic_coaching_offer": True,
                "could_fit_generic_productivity_app": False,
                "could_fit_any_coaching_offer": True,
                "could_fit_accounting_software": False,
                "specific_to_this_offer": 4,
                "reason": (
                    "The checkpoint is broad, but the launch notes and preserved context "
                    "keep it tied to the Main Branch operator loop."
                ),
            },
            "avoidance_strategy": {
                "avoids": [
                    "centered product on white background",
                    "generic growth chart",
                    "website hero composition",
                    "overly cinematic lighting",
                    "fake dashboard",
                ],
                "intentionally_uses": [],
                "reason": "Keeps the story placement focused on a concrete next-step metaphor.",
            },
            "first_second_read": "one practical next step appears inside launch clutter",
            "audience_state": "solo operator wants the next practical move from a messy launch",
            "visual_job": "make the next step feel obvious on a phone screen",
            "visual_metaphor": (
                "a narrow lit path through launch notes toward one marked checkpoint"
            ),
            "composition": "vertical story crop, focal path inside center 1:1 safe zone",
            "visual_hierarchy": {
                "primary_focal_point": "lit path and checkpoint",
                "secondary_focal_point": "launch notes",
                "text_zone": "above center",
            },
            "camera_language": "vertical mobile-first scene with centered subject",
            "style_strength": "specific scene, low gloss",
            "emotional_tone": "focused momentum",
            "placement": "facebook_story_reels_9x16",
            "placement_details": PLACEMENT_PRESETS["facebook_story_reels_9x16"],
            "text_overlay_plan": "text-free base image; overlay after export above center",
            "source_files": common_sources,
            "claim_boundary": "do not imply the software launches or spends money automatically",
            "references": [],
            "reference_trait_extraction": [],
            "prompt": (
                "Create a vertical 9:16 Facebook story ad base image for a "
                "fictional business planning tool. A narrow lit path moves "
                "through launch notes toward one simple checkpoint. Keep all "
                "critical detail in the center safe zone. No text, UI, logos, "
                "screenshots, account data, or private details."
            ),
            "negative_constraints": [
                "no platform UI",
                "no logos",
                "no tiny text",
                "no account data",
                "no unsupported automation claim",
            ],
        },
    ]
    concepts.extend(_extra_fixture_concepts(push_slug, common_sources))
    for concept in concepts:
        playbook_metadata = _fixture_playbook_metadata(str(concept["concept_id"]))
        concept.update(playbook_metadata)
        creative_playbook = concept.setdefault(
            "creative_playbook",
            {
                "id": playbook_metadata["creative_playbook_id"],
                "status": "candidate",
            },
        )
        if isinstance(creative_playbook, dict):
            creative_playbook.setdefault("id", playbook_metadata["creative_playbook_id"])
            creative_playbook.setdefault("status", "candidate")
            creative_playbook["id"] = playbook_metadata["creative_playbook_id"]
        concept["review"] = review_concept(concept)
    return concepts


def _selected_source_bites(concepts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    bites = []
    for concept in concepts:
        source_bite = concept.get("source_bite")
        if not isinstance(source_bite, dict):
            continue
        bites.append(
            {
                "concept_id": concept.get("concept_id"),
                "source_file": source_bite.get("source_file"),
                "source_type": source_bite.get("source_type"),
                "extracted_phrase": source_bite.get("extracted_phrase"),
                "visual_translation": source_bite.get("visual_translation"),
            }
        )
    return bites


def _post_processing_plan() -> dict[str, Any]:
    return {
        "status": "planned_not_implemented",
        "resize_target": PLACEMENT_PRESETS["facebook_feed_portrait_4x5"]["final_export_size"],
        "overlay_expected": True,
        "overlay_method": "future_deterministic_overlay_step",
        "export_format": "png_source_then_jpeg_or_png_final",
        "compression_target": "future_export_step",
        "validation": "Preview in Meta Ads Manager before launch.",
    }


def _ad_readiness_gate() -> dict[str, Any]:
    required_fields = [
        "offer",
        "audience",
        "campaign_goal",
        "claim_proof_boundary",
    ]
    hard_stop_missing: list[str] = []
    soft_warning_missing = [
        "proof",
        "customer_language",
        "brand_visual_style",
        "prior_outcomes",
        "meta_summary",
        "reference_images",
    ]
    allowed_actions = [
        "intake",
        "repo_source_audit",
        "ad_strategy_outline",
        "missing_info_checklist",
        "exploration_concepts",
        "api_generation",
        "final_ad_package",
    ]
    blocked_actions = [
        "final_ad_package_when_hard_stop_missing",
        "provider_image_generation_when_hard_stop_missing",
        "campaign_ready_claims_when_hard_stop_missing",
        "meta_informed_recommendations_without_approved_summary",
    ]
    return {
        "state": "ready",
        "status": "fixture_ready",
        "required_fields": required_fields,
        "hard_stop_missing": hard_stop_missing,
        "hard_stop_missing_fields": hard_stop_missing,
        "soft_warning_missing": soft_warning_missing,
        "soft_warning_missing_fields": soft_warning_missing,
        "allowed_actions": allowed_actions,
        "allowed_low_context_actions": [
            "intake",
            "repo_source_audit",
            "ad_strategy_outline",
            "missing_info_checklist",
            "placeholder_concepts_marked_as_placeholders",
        ],
        "blocked_actions": blocked_actions,
        "blocked_low_context_actions": blocked_actions,
        "future_cli_candidate": "mb ads readiness --json",
        "rule": (
            "If hard-stop fields are missing, produce an intake/source-bite plan "
            "instead of final ads."
        ),
    }


def _image_generation_gate() -> dict[str, Any]:
    return {
        "required_before_provider_generation": [
            "selected_concept",
            "prompt_record",
            "safe_media_storage",
            "image_index_target",
            "credential_state",
            "operator_approval_for_live_provider_call",
        ],
        "workflow": [
            "repo_facts",
            "ad_readiness",
            "source_bites",
            "playbook_router",
            "concepts",
            "review_genericness_checks",
            "prompt_records",
            "generation_or_fallback",
            "review_board",
            "image_index",
        ],
    }


def _candidate_score(concept: dict[str, Any]) -> int:
    review = _dict_value(concept.get("review"))
    ad_quality = _dict_value(review.get("ad_quality"))
    visual_quality = _dict_value(review.get("visual_quality"))
    risk = _dict_value(review.get("risk"))
    risk_penalty = int(risk.get("ai_slop_risk") or 5) + int(risk.get("genericness_risk") or 5)
    return (
        int(ad_quality.get("thumb_stop") or 0)
        + int(ad_quality.get("problem_clarity") or 0)
        + int(ad_quality.get("offer_relevance") or 0)
        + int(visual_quality.get("composition") or 0)
        - risk_penalty
    )


def _visual_calibration_result(
    *,
    spec: ImageProvider,
    concepts: list[dict[str, Any]],
    assets: list[dict[str, Any]],
    generated_count: int,
    review_board_path: str,
) -> dict[str, Any]:
    generated_assets = [asset for asset in assets if asset.get("state") == "generated"]
    asset_by_concept = {str(asset.get("concept_id")): asset for asset in generated_assets}
    accepted = [
        concept
        for concept in concepts
        if str(concept.get("concept_id")) in asset_by_concept
        and _dict_value(concept.get("review")).get("decision") == "accept"
    ]
    if generated_count == 0:
        state = "blocked"
        best_candidate = None
        best_playbook = None
        all_rejected = None
        failure_modes = [
            "provider_generation_not_run",
            "no_visual_quality_proven",
            "overlay_not_tested",
        ]
    elif not accepted:
        state = "all_rejected"
        best_candidate = None
        best_playbook = None
        all_rejected = True
        failure_modes = [
            "no_candidate_passed_review",
            "no_click_reason_or_ad_quality_gap",
        ]
    else:
        state = "creative_review_winner_selected"
        winner = sorted(accepted, key=_candidate_score, reverse=True)[0]
        winning_asset = asset_by_concept[str(winner.get("concept_id"))]
        best_candidate = winning_asset.get("asset_id")
        best_playbook = winner.get("creative_playbook_id")
        all_rejected = False
        failure_modes = []
    return {
        "state": state,
        "generated_count": generated_count,
        "provider": spec.id,
        "model": spec.model,
        "binary_committed": False,
        "review_board_written": True,
        "review_board_path": review_board_path,
        "best_candidate": best_candidate,
        "best_playbook": best_playbook,
        "all_rejected": all_rejected,
        "overlay_tested": False,
        "overlay_required_for_best_1_to_3": True,
        "main_failure_modes": failure_modes,
        "note": (
            "This record proves batch plumbing when generation is blocked. It proves "
            "visual quality only after generated_count is greater than zero and the "
            "review board compares real outputs."
        ),
    }


def _dashboard_readiness(
    *,
    spec: ImageProvider,
    push_slug: str,
    ad_readiness: dict[str, Any],
    image_generation_gate: dict[str, Any],
    visual_calibration: dict[str, Any],
    assets: list[dict[str, Any]],
    review_board_path: str,
) -> dict[str, Any]:
    blocker_codes = sorted(
        {
            str(asset.get("blocker_code"))
            for asset in assets
            if asset.get("blocker_code") is not None
        }
    )
    credential_states = sorted(
        {
            str(asset.get("credential_state"))
            for asset in assets
            if asset.get("credential_state") is not None
        }
    )
    next_actions = [
        "review_hard_stop_offer_audience_campaign_goal_claim_boundary",
        "review_source_bites_before_generation",
    ]
    if int(visual_calibration.get("generated_count") or 0) == 0:
        next_actions.extend(
            [
                f"confirm_{spec.id}_image_credential_state",
                "get_operator_approval_for_live_provider_call",
                f"rerun_smoke_{spec.id}_with_generate",
            ]
        )
    elif visual_calibration.get("all_rejected") is True:
        next_actions.append("revise_or_replace_rejected_playbook_candidates")
    elif visual_calibration.get("best_candidate"):
        next_actions.extend(
            [
                "test_deterministic_overlay_on_best_one_to_three_candidates",
                "record_creative_review_winner_distinct_from_performance_winner",
            ]
        )

    return {
        "state": "readable",
        "read_only": True,
        "dashboard_role": "visual_map",
        "logic_owners": {
            "cli": "facts_and_safe_checks",
            "skills": "workflow_and_judgment",
            "repo_files": "memory",
            "dashboard": "visual_map",
        },
        "safe_sources": [
            "mb start --json",
            "mb status --json --peek",
            "mb ads meta summary --json when operator approved",
            f"pushes/{push_slug}/image-index.md",
            review_board_path,
            "current push files",
        ],
        "record_sections": {
            "ad_readiness": "ad_readiness_gate",
            "missing_inputs": [
                "ad_readiness_gate.hard_stop_missing_fields",
                "ad_readiness_gate.soft_warning_missing_fields",
            ],
            "source_bites": "selected_source_bites",
            "playbook_router_choices": [
                "concepts[].creative_playbook_id",
                "concepts[].router_inputs",
                "concepts[].router_reason",
                "concepts[].playbook_fit",
            ],
            "image_candidates": ["concepts[]", "assets[]"],
            "review_scores": [
                "concepts[].review.visual_quality",
                "concepts[].review.ad_quality",
                "concepts[].review.risk",
            ],
            "winner_or_rejection": "visual_calibration_result",
            "provider_readiness": [
                "assets[].credential_state",
                "assets[].blocker_code",
                "image_generation_gate.required_before_provider_generation",
            ],
            "next_actions": "dashboard_readiness.next_actions",
        },
        "provider_readiness": {
            "provider": spec.id,
            "model": spec.model,
            "credential_states": credential_states,
            "blocker_codes": blocker_codes,
            "required_before_generation": image_generation_gate[
                "required_before_provider_generation"
            ],
        },
        "missing_inputs": {
            "hard_stop": ad_readiness["hard_stop_missing_fields"],
            "soft_warning": ad_readiness["soft_warning_missing_fields"],
        },
        "next_actions": next_actions,
        "boundaries": [
            "no_secrets",
            "no_raw_provider_payloads",
            "no_private_paths",
            "no_committed_image_binaries",
        ],
    }


def _asset_record(
    *,
    spec: ImageProvider,
    push_slug: str,
    asset_id: str,
    concept_id: str,
    docs_checked: str,
    generated_at: str,
    state: SmokeState,
    blocker_code: str,
    blocker: str,
    credential_state: str,
    output_reference: str,
    prompt: str,
    prompt_key: str,
    model: str,
    size: str,
    quality: str,
    generated_dimensions: dict[str, int] | None,
) -> dict[str, Any]:
    return {
        "asset_id": asset_id,
        "concept_id": concept_id,
        "rail": "provider",
        "provider": spec.id,
        "model": model,
        "model_snapshot": spec.model_snapshot,
        "endpoint": spec.endpoint,
        "docs_checked": docs_checked,
        "state": state,
        "blocker_code": blocker_code or None,
        "blocker": blocker or None,
        "credential_ref": spec.credential_ref,
        "credential_state": credential_state,
        "prompt_key": prompt_key,
        "prompt": prompt.strip(),
        "source_context": [
            {
                "path": f"pushes/{push_slug}/image-index.md",
                "role": "fake_push_context",
                "safe_to_share": True,
            },
            {
                "path": "fixture:fictional-northstar-ledger",
                "role": "source_brief",
                "safe_to_share": True,
            },
        ],
        "references": [],
        "dimensions": {
            "requested_size": size,
            "requested_aspect_ratio": "2:3",
            "placement": "facebook_feed_portrait_4x5",
            "placement_aspect_ratio": PLACEMENT_PRESETS["facebook_feed_portrait_4x5"][
                "aspect_ratio"
            ],
            "nearest_provider_size": PLACEMENT_PRESETS["facebook_feed_portrait_4x5"][
                "nearest_provider_size"
            ],
            "final_export_size": PLACEMENT_PRESETS["facebook_feed_portrait_4x5"][
                "final_export_size"
            ],
            "format": "png",
            "quality": quality,
            "generated_width": (
                generated_dimensions["width"] if generated_dimensions is not None else None
            ),
            "generated_height": (
                generated_dimensions["height"] if generated_dimensions is not None else None
            ),
        },
        "output_reference": output_reference,
        "storage_backend": "mb-media",
        "committed_binary": False,
        "retries": 0,
        "timeout_seconds": DEFAULT_TIMEOUT_SECONDS,
        "cost": {
            "estimate": "unknown_token_metered",
            "actual": "unknown",
            "usage": None,
        },
        "review_status": "unreviewed",
        "safe_to_share": True,
        "generated_at": generated_at,
        "operator_notes": (
            f"Fixture-safe {spec.name} image rail smoke. Commit this record only; keep any "
            "generated binary in configured private media storage."
        ),
    }


def _render_review_board(
    *,
    push_slug: str,
    concepts: list[dict[str, Any]],
    assets: list[dict[str, Any]],
    generated_at: str,
) -> str:
    asset_by_concept = {str(asset.get("concept_id")): asset for asset in assets}
    lines = [
        f"# Image Review Board - {push_slug}",
        "",
        "Local scratch board. Do not commit raw generated images, private paths, "
        "provider payloads, or unverified external research.",
        "",
        "Question: Which playbook produced the best actual ad candidate?",
        "",
        "Rule: Beautiful but no click reason = reject.",
        "",
        f"Generated at: {generated_at}",
        "",
        "| Candidate | Playbook | Source Bite | Output | Thumb | Offer | Risk | "
        "Decision | Click Reason |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | --- | --- |",
    ]
    for concept in concepts:
        review = _dict_value(concept.get("review"))
        ad_quality = _dict_value(review.get("ad_quality"))
        risk = _dict_value(review.get("risk"))
        source_bite = _dict_value(concept.get("source_bite"))
        asset = _dict_value(asset_by_concept.get(str(concept.get("concept_id"))))
        lines.append(
            "| {candidate} | {playbook} | {bite} | {output} | {thumb} | {offer} | "
            "{risk_score} | {decision} | {reason} |".format(
                candidate=concept.get("concept_id", ""),
                playbook=concept.get("creative_playbook_id", ""),
                bite=str(source_bite.get("extracted_phrase", "")).replace("|", "/"),
                output=str(asset.get("output_reference", "")).replace("|", "/"),
                thumb=ad_quality.get("thumb_stop", ""),
                offer=ad_quality.get("offer_relevance", ""),
                risk_score=risk.get("ai_slop_risk", ""),
                decision=review.get("decision", ""),
                reason=str(ad_quality.get("likely_click_reason", "")).replace("|", "/"),
            )
        )
    lines.extend(
        [
            "",
            "## Boundary",
            "",
            "- Raw visual comparison belongs here or in ignored media storage.",
            "- Commit only `image-index.md` and distilled findings.",
            "- External pattern signals are scratch/source signal unless primary "
            "sources are verified.",
        ]
    )
    return "\n".join(lines) + "\n"


def _render_index(record: dict[str, Any], *, spec: ImageProvider) -> str:
    yaml_text = yaml.safe_dump(record, sort_keys=False, allow_unicode=False)
    return (
        f"# Image Index - {spec.name} Image Rail Smoke\n\n"
        f"This fixture-safe record proves {spec.index_lede} "
        "with reviewable Facebook image-ad concepts, safe logical media "
        "references, and no generated binaries, secrets, private paths, or "
        "provider request credentials committed.\n\n"
        "```yaml\n"
        f"{yaml_text}"
        "```\n"
    )


def _smoke_image_provider(
    spec: ImageProvider,
    *,
    repo: str,
    push_slug: str,
    docs_checked: str,
    media_root: str = ".mb/media",
    generate: bool = False,
) -> dict[str, Any]:
    """Run or block one explicitly selected image rail smoke and write an asset record."""

    repo_path = Path(repo).resolve()
    push_dir = repo_path / "pushes" / push_slug
    push_dir.mkdir(parents=True, exist_ok=True)

    index_path = push_dir / "image-index.md"
    generated_at = _utc_now()

    blocker_code, blocker = _provider_fn(spec.blocker_fn)(generate)
    credential_state = "configured_env" if os.environ.get(spec.credential_env) else "missing_env"
    default_state: SmokeState = "blocked" if blocker_code else "generated"

    concepts = fixture_facebook_image_concepts(push_slug)
    asset_records: list[dict[str, Any]] = []
    generated_count = 0
    binary_written_count = 0
    generated_dimensions: dict[str, int] | None = None
    for index, concept in enumerate(concepts, start=1):
        concept_id = str(concept.get("concept_id") or f"candidate-{index:03d}")
        asset_id = spec.default_asset_id if index == 1 else f"{concept_id}-001"
        output_reference = _logical_output(push_slug, asset_id)
        concept_state = default_state
        concept_blocker_code = blocker_code
        concept_blocker = blocker
        concept_dimensions: dict[str, int] | None = None
        if default_state == "generated":
            out_path = _media_path(repo_path, media_root, push_slug, asset_id)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                image_bytes = _provider_fn(spec.generate_fn)(
                    str(concept.get("prompt") or DEFAULT_PROMPT),
                    model=spec.model,
                    size=spec.size,
                    quality=spec.quality,
                )
            except Exception as exc:  # noqa: BLE001 - provider errors must become sanitized records.
                concept_state = "blocked"
                concept_blocker_code = "provider_request_failed"
                concept_blocker = (
                    f"{spec.name} image generation failed before a usable image was written "
                    f"({exc.__class__.__name__}). {spec.failure_hint}"
                )
            else:
                concept_dimensions = _png_dimensions(image_bytes)
                generated_dimensions = generated_dimensions or concept_dimensions
                out_path.write_bytes(image_bytes)
                generated_count += 1
                binary_written_count += 1
        asset_records.append(
            _asset_record(
                spec=spec,
                push_slug=push_slug,
                asset_id=asset_id,
                concept_id=concept_id,
                docs_checked=docs_checked,
                generated_at=generated_at,
                state=concept_state,
                blocker_code=concept_blocker_code,
                blocker=concept_blocker,
                credential_state=credential_state,
                output_reference=output_reference,
                prompt=str(concept.get("prompt") or DEFAULT_PROMPT),
                prompt_key=str(concept.get("prompt_key") or DEFAULT_PROMPT_KEY),
                model=spec.model,
                size=spec.size,
                quality=spec.quality,
                generated_dimensions=concept_dimensions,
            )
        )
    state: SmokeState = "generated" if generated_count else "blocked"
    review_board_path = _review_board_path(repo_path, media_root, push_slug)
    review_board_ref = _repo_relative_or_logical(
        review_board_path,
        repo_path,
        _logical_review_board(push_slug),
    )
    review_board_path.parent.mkdir(parents=True, exist_ok=True)
    review_board_path.write_text(
        _render_review_board(
            push_slug=push_slug,
            concepts=concepts,
            assets=asset_records,
            generated_at=generated_at,
        ),
        encoding="utf-8",
    )
    visual_calibration = _visual_calibration_result(
        spec=spec,
        concepts=concepts,
        assets=asset_records,
        generated_count=generated_count,
        review_board_path=review_board_ref,
    )
    ad_readiness = _ad_readiness_gate()
    image_generation_gate = _image_generation_gate()
    dashboard_readiness = _dashboard_readiness(
        spec=spec,
        push_slug=push_slug,
        ad_readiness=ad_readiness,
        image_generation_gate=image_generation_gate,
        visual_calibration=visual_calibration,
        assets=asset_records,
        review_board_path=review_board_ref,
    )
    record = {
        "schema": "mainbranch.image_index.v0",
        "push_slug": push_slug,
        "docs_checked": docs_checked,
        "output_record_written": True,
        "binary_committed": False,
        "experiment_frame": "first_creative_playbook_router_experiment",
        "conversion_language": "conversion_informed",
        "batch_plan": {
            "candidate_count": len(concepts),
            "target_range": "8-12",
            "strategy": "top playbook candidates with one to two variants each",
            "provider_validation": "official_api_rail_only",
        },
        "generated_count": generated_count,
        "best_candidate": visual_calibration["best_candidate"],
        "best_playbook": visual_calibration["best_playbook"],
        "all_rejected": visual_calibration["all_rejected"],
        "overlay_tested": visual_calibration["overlay_tested"],
        "main_failure_modes": visual_calibration["main_failure_modes"],
        "creative_playbook_ids": list(CREATIVE_PLAYBOOK_IDS),
        "review_board_question": "Which playbook produced the best actual ad candidate?",
        "review_board": {
            "path": review_board_ref,
            "committed": False,
            "storage": "ignored_media_storage",
        },
        "review_rule": "Beautiful but no click reason = reject.",
        "external_research_boundary": (
            "External creative research is scratch/source signal only; raw dumps, "
            "screenshots, and unverified claims are not committed."
        ),
        "ad_readiness_gate": ad_readiness,
        "image_generation_gate": image_generation_gate,
        "dashboard_readiness": dashboard_readiness,
        "placement_presets": PLACEMENT_PRESETS,
        "reference_roles": list(REFERENCE_ROLES),
        "selected_source_bites": _selected_source_bites(concepts),
        "post_processing_plan": _post_processing_plan(),
        "visual_calibration_result": visual_calibration,
        "concepts": concepts,
        "assets": asset_records,
    }
    index_path.write_text(_render_index(record, spec=spec), encoding="utf-8")
    result_blocker_code = blocker_code or None
    if state == "blocked" and result_blocker_code is None and asset_records:
        result_blocker_code = asset_records[0].get("blocker_code")

    return {
        "ok": True,
        "provider": spec.id,
        "model": spec.model,
        "state": state,
        "blocker_code": result_blocker_code,
        "candidate_count": len(concepts),
        "generated_count": generated_count,
        "best_candidate": visual_calibration["best_candidate"],
        "best_playbook": visual_calibration["best_playbook"],
        "all_rejected": visual_calibration["all_rejected"],
        "overlay_tested": visual_calibration["overlay_tested"],
        "main_failure_modes": visual_calibration["main_failure_modes"],
        "output_record_written": True,
        "record_path": _repo_relative(index_path, repo_path),
        "review_board_written": True,
        "review_board_path": review_board_ref,
        "output_reference": _logical_output(push_slug, spec.default_asset_id),
        "storage_backend": "mb-media",
        "dimensions": {
            "requested_size": spec.size,
            "requested_aspect_ratio": "2:3",
            "placement": "facebook_feed_portrait_4x5",
            "placement_aspect_ratio": PLACEMENT_PRESETS["facebook_feed_portrait_4x5"][
                "aspect_ratio"
            ],
            "format": "png",
            "quality": spec.quality,
        },
        "generated_dimensions": generated_dimensions,
        "binary_written": binary_written_count > 0,
        "binary_written_count": binary_written_count,
        "binary_committed": False,
        "safe_to_share": True,
        "docs_checked": docs_checked,
    }


def smoke_openai(
    *,
    repo: str,
    push_slug: str = DEFAULT_PUSH_SLUG,
    docs_checked: str,
    media_root: str = ".mb/media",
    generate: bool = False,
) -> dict[str, Any]:
    """Run or block the narrow OpenAI image rail smoke and write an asset record."""

    return _smoke_image_provider(
        image_provider("openai"),
        repo=repo,
        push_slug=push_slug,
        docs_checked=docs_checked,
        media_root=media_root,
        generate=generate,
    )


def smoke_fal(
    *,
    repo: str,
    push_slug: str = DEFAULT_FAL_PUSH_SLUG,
    docs_checked: str,
    media_root: str = ".mb/media",
    generate: bool = False,
) -> dict[str, Any]:
    """Run or block the narrow fal.ai FLUX image rail smoke and write an asset record."""

    return _smoke_image_provider(
        image_provider("fal"),
        repo=repo,
        push_slug=push_slug,
        docs_checked=docs_checked,
        media_root=media_root,
        generate=generate,
    )
