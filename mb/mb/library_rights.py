"""Media library rights: deals and the verdict. Pure; no files, no clock.

The verdict answers one question per sighting: may we use this copy of this
asset like this, over this whole window. It reads deals, the sighting,
provenance, the use and the window. It never reads tags or creator.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
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
STATES = ("proposed", "approved", "revoked")
PROVENANCE = ("own", "licensed", "third_party", "unknown")
CLEARABLE_PROVENANCE = ("own", "licensed")

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
        if self.platform_code is not None:
            _closed("platform", (self.platform_code[0],), PLATFORMS)
        if not self.uses:
            raise ValueError("deal needs at least one use")
        if not self.sightings:
            raise ValueError("deal needs at least one sighting it covers")
        if not self.said_by.strip():
            raise ValueError("deal needs said-by: who said yes, and how")

    def fields_hash(self) -> str:
        """Hash of the terms. State and approval fields are not terms."""
        terms = {k: v for k, v in self.to_mapping().items() if k not in _UNAPPROVED_FIELDS}
        blob = json.dumps(terms, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode()).hexdigest()

    def approve(self, by: str, at: str) -> Deal:
        return dataclasses.replace(
            self,
            state="approved",
            approved_by=by,
            approved_at=at,
            approval_hash=self.fields_hash(),
        )

    def revoke(self, reason: str, at: str) -> Deal:
        return dataclasses.replace(self, state="revoked", revoked_reason=reason, revoked_at=at)

    @property
    def is_active(self) -> bool:
        """Approved, and the terms are still the ones that were approved."""
        return self.state == "approved" and self.approval_hash == self.fields_hash()

    def to_mapping(self) -> dict[str, Any]:
        code = None
        if self.platform_code is not None:
            code = {"platform": self.platform_code[0], "expires": self.platform_code[1].isoformat()}
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
            "state": self.state,
            "approved_by": self.approved_by,
            "approved_at": self.approved_at,
            "approval_hash": self.approval_hash,
            "revoked_reason": self.revoked_reason,
            "revoked_at": self.revoked_at,
        }

    @classmethod
    def from_mapping(cls, raw: dict[str, Any]) -> Deal:
        try:
            code = raw.get("platform_code")
            to_raw = raw.get("to")
            return cls(
                id=str(raw["id"]),
                uses=tuple(raw["uses"]),
                platforms=tuple(raw.get("platforms") or ()),
                from_date=_to_date(raw["from"]),
                to_date=_to_date(to_raw) if to_raw else None,
                perpetual=bool(raw.get("perpetual", False)),
                music=str(raw.get("music", "unknown")),
                platform_code=(
                    (str(code["platform"]), _to_date(code["expires"])) if code else None
                ),
                said_by=str(raw["said_by"]),
                evidence_hash=str(raw.get("evidence_hash", "")),
                sightings=tuple(raw["sightings"]),
                state=str(raw.get("state", "proposed")),
                approved_by=str(raw.get("approved_by", "")),
                approved_at=str(raw.get("approved_at", "")),
                approval_hash=str(raw.get("approval_hash", "")),
                revoked_reason=str(raw.get("revoked_reason", "")),
                revoked_at=str(raw.get("revoked_at", "")),
            )
        except (KeyError, TypeError) as exc:
            raise ValueError(f"deal record is malformed: {exc!r}") from exc


def _closed(label: str, values: tuple[str, ...], allowed: tuple[str, ...]) -> None:
    for value in values:
        if value not in allowed:
            raise ValueError(f"unknown {label} {value!r}; use one of: {', '.join(allowed)}")


def _to_date(value: Any) -> date:
    if isinstance(value, datetime):
        raise ValueError(f"expected a date, got a datetime: {value!r}")
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


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
        reasons = _deal_reasons(deal, sighting, provenance, use, start, end)
        if not reasons:
            return Verdict(True, deal_id=deal.id)
        failures.update(reasons)
    return Verdict(False, reasons=tuple(sorted(failures)))


def _deal_reasons(
    deal: Deal, sighting: str, provenance: str, use: Use, start: date, end: date
) -> list[str]:
    if deal.state == "revoked":
        return ["revoked"]
    if not deal.is_active:
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
    reasons.extend(_platform_code_reasons(deal, provenance, use, end))
    return sorted(reasons)


def _platform_code_reasons(deal: Deal, provenance: str, use: Use, end: date) -> list[str]:
    if deal.platform_code is None:
        needs = provenance == "licensed" and use.kind == "paid-ad"
        return ["platform-code-missing"] if needs else []
    platform, expires = deal.platform_code
    if platform != use.platform:
        return ["platform-code-other-platform"]
    if expires < end:
        return ["platform-code-expires"]
    return []
