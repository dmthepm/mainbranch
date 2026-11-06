"""Media library rights: deals and the verdict. Pure; no files, no clock.

The verdict answers one question per sighting: may we use this copy of this
asset like this, over this whole window. It reads deals, the sighting,
provenance, the use and the window. It never reads tags or creator.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

USES = ("paid-ad", "organic-social", "website", "email")
PLATFORM_USES = ("paid-ad", "organic-social")
PLATFORMS = (
    "meta",
    "tiktok",
    "youtube",
    "google",
    "x",
    "linkedin",
    "pinterest",
    "snapchat",
)
MUSIC = ("original", "licensed", "none", "unknown")
SUBJECTS = ("none-shown", "agreed", "unknown")
STATES = ("proposed", "approved", "revoked")
PROVENANCE = ("own", "licensed", "third_party", "unknown")
CLEARABLE_PROVENANCE = ("own", "licensed")

DEAL_KEYS = frozenset(
    {
        "id",
        "uses",
        "platforms",
        "from",
        "to",
        "perpetual",
        "music",
        "platform_code",
        "said_by",
        "evidence_hash",
        "sightings",
        "subject",
        "subject_proof",
        "state",
        "approved_by",
        "approved_at",
        "approval_hash",
        "revoked_reason",
        "revoked_at",
    }
)
_DEAL_ID = re.compile(r"[0-9a-f]{8}")
_UNAPPROVED_FIELDS = frozenset(
    {"state", "approved_by", "approved_at", "approval_hash", "revoked_reason", "revoked_at"}
)


@dataclass(frozen=True)
class Use:
    kind: str
    platform: str | None = None


@dataclass(frozen=True)
class Verdict:
    cleared: bool
    deal_id: str = ""
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class Deal:
    """One written permission. Never edited; a change is a new deal."""

    id: str
    uses: tuple[str, ...]
    platforms: tuple[str, ...]
    from_date: date
    to_date: date | None
    perpetual: bool
    music: str
    platform_code: tuple[str, date] | None
    said_by: str
    evidence_hash: str
    sightings: tuple[str, ...]
    subject: str = "unknown"
    subject_proof: str = ""
    state: str = "proposed"
    approved_by: str = ""
    approved_at: str = ""
    approval_hash: str = ""
    revoked_reason: str = ""
    revoked_at: str = ""

    def __post_init__(self) -> None:
        if self.to_date is None and not self.perpetual:
            raise ValueError("deal needs a to date, or perpetual set explicitly")
        if self.to_date is not None and self.perpetual:
            raise ValueError("deal is either perpetual or has a to date, not both")
        if self.to_date is not None and self.to_date < self.from_date:
            raise ValueError("deal to date is before its from date")
        _closed("use", self.uses, USES)
        _closed("platform", self.platforms, PLATFORMS)
        _closed("music", (self.music,), MUSIC)
        _closed("state", (self.state,), STATES)
        _closed("subject", (self.subject,), SUBJECTS)
        if self.subject == "agreed" and not self.subject_proof.strip():
            raise ValueError(
                "subject agreed needs a proof location: where the proof sits, never a name"
            )
        if self.subject != "agreed" and self.subject_proof:
            raise ValueError("a subject proof location goes with subject agreed only")
        if self.platform_code is not None:
            _closed("platform", (self.platform_code[0],), PLATFORMS)
        if not self.uses:
            raise ValueError("deal needs at least one use")
        if not self.sightings:
            raise ValueError("deal needs at least one sighting it covers")
        if not self.said_by.strip():
            raise ValueError("deal needs said-by: who said yes, and how")

    def fields_hash(self, asset: str = "", provenance: str = "") -> str:
        """Hash of the terms, plus the asset and provenance they were approved for.

        State and approval fields are not terms. This catches an accidental edit of
        the terms or a record reused for other bytes; it is not a seal over every
        field of the record file.
        """
        terms = {k: v for k, v in self.to_mapping().items() if k not in _UNAPPROVED_FIELDS}
        terms["_asset"] = asset
        terms["_provenance"] = provenance
        blob = json.dumps(terms, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode()).hexdigest()

    def approve(self, by: str, at: str, *, asset: str, provenance: str) -> Deal:
        return dataclasses.replace(
            self,
            state="approved",
            approved_by=by,
            approved_at=at,
            approval_hash=self.fields_hash(asset, provenance),
        )

    def revoke(self, reason: str, at: str) -> Deal:
        return dataclasses.replace(self, state="revoked", revoked_reason=reason, revoked_at=at)

    def is_active_for(self, asset: str, provenance: str) -> bool:
        """Approved, for this asset and provenance, with the terms that were approved."""
        return self.state == "approved" and self.approval_hash == self.fields_hash(
            asset, provenance
        )

    def to_mapping(self) -> dict[str, Any]:
        code = None
        if self.platform_code is not None:
            code = {"platform": self.platform_code[0], "expires": self.platform_code[1].isoformat()}
        # Subject keys are left out while the subject is unknown, so a deal approved
        # before they existed keeps the hash it was approved under.
        subject = (
            {}
            if self.subject == "unknown"
            else {"subject": self.subject, "subject_proof": self.subject_proof}
        )
        return {
            "id": self.id,
            "uses": list(self.uses),
            "platforms": list(self.platforms),
            "from": self.from_date.isoformat(),
            "to": self.to_date.isoformat() if self.to_date else None,
            "perpetual": self.perpetual,
            "music": self.music,
            "platform_code": code,
            "said_by": self.said_by,
            "evidence_hash": self.evidence_hash,
            "sightings": list(self.sightings),
            **subject,
            "state": self.state,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at,
            "approval_hash": self.approval_hash,
            "revoked_reason": self.revoked_reason,
            "revoked_at": self.revoked_at,
        }

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> Deal:
        """Build a deal from a record. Types are checked, never coerced."""
        if not isinstance(raw, dict):
            raise ValueError("deal record is malformed: a deal must be a mapping")
        for key in raw:
            if key not in DEAL_KEYS:
                raise ValueError(f"deal has unknown field {key!r}; put business-only facts in tags")
        try:
            code = raw.get("platform_code")
            to_raw = raw.get("to")
            return cls(
                id=_deal_id(_text(raw, "id")),
                uses=_texts(raw, "uses"),
                platforms=_texts(raw, "platforms", default=()),
                from_date=_to_date(raw["from"]),
                to_date=_to_date(to_raw) if to_raw is not None else None,
                perpetual=_flag(raw, "perpetual"),
                music=_text(raw, "music", default="unknown"),
                platform_code=_platform_code(code),
                said_by=_text(raw, "said_by"),
                evidence_hash=_text(raw, "evidence_hash", default=""),
                sightings=_texts(raw, "sightings"),
                subject=_text(raw, "subject", default="unknown"),
                subject_proof=_text(raw, "subject_proof", default=""),
                state=_text(raw, "state", default="proposed"),
                approved_by=_text(raw, "approved_by", default=""),
                approved_at=_stamp(raw, "approved_at"),
                approval_hash=_text(raw, "approval_hash", default=""),
                revoked_reason=_text(raw, "revoked_reason", default=""),
                revoked_at=_stamp(raw, "revoked_at"),
            )
        except (KeyError, TypeError) as exc:
            raise ValueError(f"deal record is malformed: {exc!r}") from exc


_MISSING: Any = object()


def _text(raw: dict[str, Any], key: str, *, default: Any = _MISSING) -> str:
    value = raw.get(key, default)
    if value is _MISSING:
        raise KeyError(key)
    if not isinstance(value, str):
        raise ValueError(f"deal field {key} must be text, not {type(value).__name__}")
    return value


def _deal_id(value: str) -> str:
    if not _DEAL_ID.fullmatch(value):
        raise ValueError("deal field id must be 8 lowercase hex characters")
    return value


def _stamp(raw: dict[str, Any], key: str) -> str:
    """Empty, or a time as `datetime.isoformat` writes it; nothing else is printed back."""
    value = _text(raw, key, default="")
    if value:
        try:
            datetime.fromisoformat(value)
        except ValueError:
            raise ValueError(f"deal field {key} must be empty or an ISO time") from None
        if not value.isprintable():
            raise ValueError(f"deal field {key} must be empty or an ISO time")
    return value


def _texts(raw: dict[str, Any], key: str, *, default: Any = _MISSING) -> tuple[str, ...]:
    value = raw.get(key, default)
    if value is _MISSING:
        raise KeyError(key)
    if value is None and default is not _MISSING:
        return tuple(default)
    if isinstance(value, tuple):
        value = list(value)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"deal field {key} must be a list of text")
    return tuple(value)


def _flag(raw: dict[str, Any], key: str) -> bool:
    value = raw.get(key, False)
    if not isinstance(value, bool):
        raise ValueError(f"deal field {key} must be true or false without quotes, not {value!r}")
    return value


def _platform_code(code: Any) -> tuple[str, date] | None:
    if code is None:
        return None
    if not isinstance(code, dict) or not isinstance(code.get("platform"), str):
        raise ValueError("deal field platform_code must be a mapping with a text platform")
    return (code["platform"], _to_date(code["expires"]))


def _closed(label: str, values: tuple[str, ...], allowed: tuple[str, ...]) -> None:
    for value in values:
        if value not in allowed:
            raise ValueError(f"unknown {label} {value!r}; use one of: {', '.join(allowed)}")


def _to_date(value: Any) -> date:
    if isinstance(value, datetime):
        raise ValueError(f"expected a date, got a datetime: {value!r}")
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise ValueError(f"expected a date as YYYY-MM-DD, got {type(value).__name__}")
    return date.fromisoformat(value)


def today(now: datetime, timezone_name: str) -> date:
    """The business's calendar date. `now` must be timezone-aware."""
    try:
        zone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"unknown timezone {timezone_name!r}") from exc
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return now.astimezone(zone).date()


def verdict(
    deals: list[Deal] | tuple[Deal, ...],
    sighting: str,
    provenance: str,
    use: Use,
    window: tuple[date, date],
    *,
    asset: str,
) -> Verdict:
    """Cleared only when one approved deal covers sighting, use, platform and the whole window."""
    start, end = window
    if end < start:
        raise ValueError("window ends before it starts")
    if provenance not in CLEARABLE_PROVENANCE:
        return Verdict(False, reasons=("provenance-not-clearable",))
    if not deals:
        return Verdict(False, reasons=("no-deal",))
    failures: set[str] = set()
    for deal in deals:
        reasons = _deal_reasons(deal, asset, sighting, provenance, use, start, end)
        if not reasons:
            return Verdict(True, deal_id=deal.id)
        failures.update(reasons)
    return Verdict(False, reasons=tuple(sorted(failures)))


def _deal_reasons(
    deal: Deal, asset: str, sighting: str, provenance: str, use: Use, start: date, end: date
) -> list[str]:
    if deal.state == "revoked":
        return ["revoked"]
    if not deal.is_active_for(asset, provenance):
        return ["not-approved"]
    reasons: list[str] = []
    if sighting not in deal.sightings:
        reasons.append("sighting-not-covered")
    if use.kind not in deal.uses:
        reasons.append("wrong-use")
    if use.kind in PLATFORM_USES and use.platform not in deal.platforms:
        reasons.append("wrong-platform")
    if start < deal.from_date or (deal.to_date is not None and end > deal.to_date):
        reasons.append("outside-window")
    if deal.music == "unknown":
        reasons.append("music-unknown")
    if deal.subject == "unknown":
        reasons.append("subject-unknown")
    reasons.extend(_platform_code_reasons(deal, provenance, use, end))
    return sorted(reasons)


def _platform_code_reasons(deal: Deal, provenance: str, use: Use, end: date) -> list[str]:
    """A code speaks only for its own platform; licensed paid ads must have theirs."""
    needs = provenance == "licensed" and use.kind == "paid-ad"
    if deal.platform_code is None:
        return ["platform-code-missing"] if needs else []
    platform, expires = deal.platform_code
    if platform != use.platform:
        return ["platform-code-other-platform"] if needs else []
    if expires < end:
        return ["platform-code-expires"]
    return []
