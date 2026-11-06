"""The media library: sources, a rebuildable index, records and deals.

A Library is opened on one business folder and nothing else. It answers what
exists, where, and whether a given sighting may be used. It hands out no bytes.
Safety here is same-user accident prevention: nothing enforces rights at
publication, and a process running as the same OS user can edit any file this
module writes.
"""

from __future__ import annotations

import contextlib
import os
import re
import secrets
import sqlite3
from collections import defaultdict
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from mb import library_rights as rights
from mb import library_source
from mb.library_files import (
    LibraryError,
    MissingFolder,
    check_file,
    open_dir,
    read_file,
    refuse_overlap,
    write_file,
)

CONFIG_REL = ".mb/private/library"
DEFAULT_RECORDS = "library/records"
BATCH = 200
_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_ASSET = re.compile(r"^[0-9a-f]{64}$")
_KINDS = {
    "photo": {"jpg", "jpeg", "png", "webp", "gif", "heic", "tif", "tiff", "avif"},
    "video": {"mp4", "mov", "m4v", "webm", "mkv", "avi"},
    "audio": {"mp3", "wav", "m4a", "aac", "flac", "ogg"},
    "document": {"pdf"},
}
_SCHEMA = """
CREATE TABLE IF NOT EXISTS sightings (
    source TEXT NOT NULL, path TEXT NOT NULL, asset TEXT NOT NULL,
    size INTEGER NOT NULL, mtime_ns INTEGER NOT NULL, kind TEXT NOT NULL,
    PRIMARY KEY (source, path));
CREATE INDEX IF NOT EXISTS sightings_asset ON sightings (asset);
CREATE TABLE IF NOT EXISTS skipped (
    source TEXT NOT NULL, path TEXT NOT NULL, reason TEXT NOT NULL,
    PRIMARY KEY (source, path));
"""


def kind_of(path: str) -> str:
    ext = path.rsplit(".", 1)[-1].lower() if "." in path.rsplit("/", 1)[-1] else ""
    return next((kind for kind, exts in _KINDS.items() if ext in exts), "other")


@dataclass(frozen=True)
class SkippedItem:
    source: str
    path: str
    reason: str


@dataclass
class ScanReport:
    indexed: int = 0
    new: int = 0
    changed: int = 0
    removed: int = 0
    hashed: int = 0
    mismatched: list[str] = field(default_factory=list)
    skipped: list[SkippedItem] = field(default_factory=list)
    duplicates: dict[str, list[str]] = field(default_factory=dict)
    unavailable: list[tuple[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class Hit:
    asset: str
    kind: str
    size: int
    sightings: list[str]
    cleared: list[str] | None = None


@dataclass(frozen=True)
class SightingVerdict:
    sighting: str
    verdict: rights.Verdict


@dataclass(frozen=True)
class DealView:
    id: str
    status: str
    deal: rights.Deal


@dataclass(frozen=True)
class AssetView:
    asset: str
    kind: str
    size: int
    sightings: list[str]
    provenance: str
    tags: list[str]
    creator: str
    deals: list[DealView]


@dataclass
class Record:
    asset: str
    provenance: str = "unknown"
    tags: list[str] = field(default_factory=list)
    creator: str = ""
    deals: list[rights.Deal] = field(default_factory=list)


def deal_status(deal: rights.Deal) -> str:
    if deal.state == "approved" and not deal.is_active:
        return "edited since approval: not active"
    return deal.state


class Library:
    def __init__(
        self,
        root: Path,
        *,
        now: Callable[[], datetime] | None = None,
        init: bool = False,
    ) -> None:
        self._now = now or (lambda: datetime.now(timezone.utc))
        self.root = Path(root)
        if not (self.root.is_dir() and any((self.root / m).exists() for m in (".mb", ".git"))):
            raise LibraryError(
                f"{self.root} is not a business folder (no .mb or .git); "
                "run this from your business folder"
            )
        self.root = self.root.resolve()
        with self._dir(CONFIG_REL, create=init) as fd:
            raw = read_file(fd, "config.yaml")
        if raw is None and not init:
            raise LibraryError(
                "no media library here yet: add a source first "
                "(mb library source add <name> <folder>)"
            )
        self._config = self._parse_config(raw)
        self.timezone: str = self._config["timezone"]
        self.records_rel: str = self._config["records_dir"]
        self.sources: dict[str, Path] = {
            name: Path(path) for name, path in self._config["sources"].items()
        }
        for target in (self.root / CONFIG_REL, self.root / self.records_rel):
            refuse_overlap(target, self.sources.values())

    # -- config and folders ---------------------------------------------------

    @contextlib.contextmanager
    def _dir(self, rel: str, *, create: bool) -> Iterator[int]:
        fd = open_dir(self.root, rel, create=create)
        try:
            yield fd
        finally:
            os.close(fd)

    def _parse_config(self, raw: bytes | None) -> dict[str, Any]:
        try:
            data = yaml.safe_load(raw or b"") or {}
        except yaml.YAMLError as exc:
            raise LibraryError(f"config.yaml is not valid YAML: {exc}") from exc
        if not isinstance(data, dict):
            raise LibraryError("config.yaml must be a mapping")
        sources = data.get("sources") or {}
        records = data.get("records_dir", DEFAULT_RECORDS)
        zone = data.get("timezone", "UTC")
        if not isinstance(sources, dict) or not all(
            isinstance(k, str) and _NAME.match(k) and isinstance(v, str) for k, v in sources.items()
        ):
            raise LibraryError("config.yaml sources must map plain names to folder paths")
        if (
            not isinstance(records, str)
            or Path(records).is_absolute()
            or ".." in Path(records).parts
        ):
            raise LibraryError("records_dir must stay inside the business folder")
        try:
            rights.today(self._now(), str(zone))
        except ValueError as exc:
            raise LibraryError(f"config.yaml timezone: {exc}") from exc
        return {"sources": dict(sources), "records_dir": records, "timezone": str(zone)}

    def _save_config(self) -> None:
        text = yaml.safe_dump(
            {
                "timezone": self.timezone,
                "records_dir": self.records_rel,
                "sources": {n: str(p) for n, p in sorted(self.sources.items())},
            },
            sort_keys=False,
        )
        with self._dir(CONFIG_REL, create=True) as fd:
            write_file(fd, "config.yaml", text.encode())

    def add_source(self, name: str, path: str | Path) -> Path:
        if not _NAME.match(name):
            raise LibraryError(
                f"source name {name!r} must be lowercase letters, digits, - or _ (no ':' or '/')"
            )
        if name in self.sources:
            raise LibraryError(f"source {name!r} is already registered")
        folder = Path(path).expanduser().resolve()
        problem = library_source.root_problem(folder)
        if problem == "writable":
            raise LibraryError(
                f"{folder} is writable by this user. The library only reads folders it cannot "
                "write; mount it read-only or use a read-only copy of its permissions."
            )
        if problem:
            raise LibraryError(f"{folder}: {problem}")
        for target in (self.root / CONFIG_REL, self.root / self.records_rel):
            refuse_overlap(target, [folder])
        self.sources[name] = folder
        self._save_config()
        return folder

    # -- index ------------------------------------------------------------------

    @contextlib.contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        with self._dir(CONFIG_REL, create=False) as fd:
            for name in ("index.db", "index.db-journal", "index.db-wal", "index.db-shm"):
                check_file(fd, name)
            conn = sqlite3.connect(self.root / CONFIG_REL / "index.db")
            try:
                conn.executescript(_SCHEMA)
                conn.commit()
                with contextlib.suppress(FileNotFoundError):
                    os.chmod("index.db", 0o600, dir_fd=fd)
                yield conn
            finally:
                conn.close()

    def scan(self, *, verify: bool = False) -> ScanReport:
        report = ScanReport()
        for name, folder in sorted(self.sources.items()):
            if library_source.root_problem(folder) == "writable":
                raise LibraryError(
                    f"source {name!r} ({folder}) is writable by this user; refusing to scan"
                )
        now_ns = int(self._now().timestamp() * 1_000_000_000)
        with self._db() as db:
            for name, folder in sorted(self.sources.items()):
                problem = library_source.root_problem(folder)
                if problem:
                    report.unavailable.append((name, problem))
                    continue
                self._scan_one(db, name, folder, now_ns, verify, report)
            report.indexed = db.execute("SELECT COUNT(*) FROM sightings").fetchone()[0]
            report.duplicates = {
                asset: self._sighting_names(db, asset)
                for (asset,) in db.execute(
                    "SELECT asset FROM sightings GROUP BY asset HAVING COUNT(*) > 1"
                ).fetchall()
            }
        return report

    def _scan_one(
        self,
        db: sqlite3.Connection,
        name: str,
        folder: Path,
        now_ns: int,
        verify: bool,
        report: ScanReport,
    ) -> None:
        known = {
            path: (size, mtime, asset)
            for path, size, mtime, asset in db.execute(
                "SELECT path, size, mtime_ns, asset FROM sightings WHERE source = ?", (name,)
            )
        }
        seen: set[str] = set()
        skipped: list[SkippedItem] = []
        pending = 0
        try:
            for item in library_source.scan_source(folder, known, now_ns=now_ns, reverify=verify):
                if isinstance(item, library_source.Skipped):
                    skipped.append(SkippedItem(name, item.rel, item.reason))
                    continue
                seen.add(item.rel)
                before = known.get(item.rel)
                reused = before is not None and before[:2] == (item.size, item.mtime_ns)
                if not reused or verify:
                    report.hashed += 1
                if before is None:
                    report.new += 1
                elif before[2] != item.sha256:
                    report.changed += 1
                    if reused:
                        report.mismatched.append(f"{name}:{item.rel}")
                db.execute(
                    "INSERT OR REPLACE INTO sightings VALUES (?, ?, ?, ?, ?, ?)",
                    (name, item.rel, item.sha256, item.size, item.mtime_ns, kind_of(item.rel)),
                )
                pending += 1
                if pending >= BATCH:
                    db.commit()
                    pending = 0
        except OSError as exc:
            report.unavailable.append((name, exc.strerror or "unreadable"))
            db.commit()
            return
        gone = [path for path in known if path not in seen]
        report.removed += len(gone)
        db.executemany(
            "DELETE FROM sightings WHERE source = ? AND path = ?",
            [(name, path) for path in gone],
        )
        db.execute("DELETE FROM skipped WHERE source = ?", (name,))
        db.executemany(
            "INSERT OR REPLACE INTO skipped VALUES (?, ?, ?)",
            [(s.source, s.path, s.reason) for s in skipped],
        )
        db.commit()
        report.skipped.extend(skipped)

    @staticmethod
    def _sighting_names(db: sqlite3.Connection, asset: str) -> list[str]:
        rows = db.execute("SELECT source, path FROM sightings WHERE asset = ?", (asset,))
        return sorted(f"{source}:{path}" for source, path in rows)

    # -- records ------------------------------------------------------------------

    def _records_fd(self, *, create: bool) -> contextlib.AbstractContextManager[int]:
        return self._dir(self.records_rel, create=create)

    def _read_record(self, fd: int, asset: str) -> Record | None:
        raw = read_file(fd, f"{asset}.yaml")
        if raw is None:
            return None
        label = f"record {asset[:12]}"
        try:
            data = yaml.safe_load(raw) or {}
        except yaml.YAMLError as exc:
            raise LibraryError(f"{label} is not valid YAML: {exc}") from exc
        if not isinstance(data, dict):
            raise LibraryError(f"{label} must be a mapping")
        provenance = data.get("provenance", "unknown")
        if provenance not in rights.PROVENANCE:
            raise LibraryError(
                f"{label}: provenance {provenance!r} must be one of {', '.join(rights.PROVENANCE)}"
            )
        tags = data.get("tags") or []
        if not isinstance(tags, list):
            raise LibraryError(f"{label}: tags must be a list")
        try:
            deals = [rights.Deal.from_mapping(d) for d in (data.get("deals") or [])]
        except (ValueError, AttributeError, TypeError) as exc:
            raise LibraryError(f"{label}: {exc}") from exc
        return Record(
            asset, provenance, [str(t) for t in tags], str(data.get("creator") or ""), deals
        )

    def _write_record(self, fd: int, record: Record) -> None:
        text = yaml.safe_dump(
            {
                "asset": record.asset,
                "provenance": record.provenance,
                "tags": record.tags,
                "creator": record.creator,
                "deals": [d.to_mapping() for d in record.deals],
            },
            sort_keys=False,
        )
        write_file(fd, f"{record.asset}.yaml", text.encode())

    def _all_records(self) -> dict[str, Record]:
        records: dict[str, Record] = {}
        try:
            with self._records_fd(create=False) as fd:
                with os.scandir(fd) as entries:
                    names = sorted(e.name for e in entries)
                for name in names:
                    stem = name[:-5]
                    if name.endswith(".yaml") and _ASSET.match(stem):
                        rec = self._read_record(fd, stem)
                        if rec:
                            records[stem] = rec
        except MissingFolder:
            return {}
        return records

    def _record_or_default(self, asset: str) -> Record:
        try:
            with self._records_fd(create=False) as fd:
                return self._read_record(fd, asset) or Record(asset)
        except MissingFolder:
            return Record(asset)

    # -- queries ----------------------------------------------------------------------

    def _window(self, window: tuple[date, date] | None) -> tuple[date, date]:
        if window is not None:
            return window
        day = rights.today(self._now(), self.timezone)
        return (day, day)

    @staticmethod
    def _check_use(use: rights.Use) -> None:
        if use.kind not in rights.USES:
            raise LibraryError(f"unknown use {use.kind!r}; use one of: {', '.join(rights.USES)}")
        if use.kind in rights.PLATFORM_USES and use.platform not in rights.PLATFORMS:
            raise LibraryError(f"{use.kind} needs a platform: one of {', '.join(rights.PLATFORMS)}")

    @staticmethod
    def _asset_id(asset: str) -> str:
        if not _ASSET.match(asset):
            raise LibraryError("give the full 64-character asset id (see `mb library find`)")
        return asset

    def _sightings_of(self, db: sqlite3.Connection, asset: str) -> list[tuple[str, int, str]]:
        rows = db.execute(
            "SELECT source, path, size, kind FROM sightings WHERE asset = ? ORDER BY source, path",
            (asset,),
        ).fetchall()
        if not rows:
            raise LibraryError(f"unknown asset {asset[:12]}…; run `mb library scan` first")
        return [(f"{s}:{p}", size, kind) for s, p, size, kind in rows]

    def find(
        self,
        query: str = "",
        *,
        kind: str | None = None,
        use: rights.Use | None = None,
        window: tuple[date, date] | None = None,
        any_word: bool = False,
    ) -> list[Hit]:
        if use is not None:
            self._check_use(use)
        span = self._window(window)
        words = _words(query)
        grouped: dict[str, list[tuple[str, int, str]]] = defaultdict(list)
        with self._db() as db:
            rows = db.execute(
                "SELECT asset, source, path, size, kind FROM sightings ORDER BY asset, source, path"
            )
            for asset, source, path, size, row_kind in rows:
                grouped[asset].append((f"{source}:{path}", size, row_kind))
        records = self._all_records() if (words or use is not None) else {}
        hits: list[Hit] = []
        for asset, sightings in grouped.items():
            if kind and sightings[0][2] != kind:
                continue
            rec = records.get(asset) or Record(asset)
            if words:
                haystack = " ".join(
                    [_flat(s) for s, _, _ in sightings]
                    + [_flat(t) for t in rec.tags]
                    + [_flat(rec.creator)]
                )
                found = [w in haystack for w in words]
                if not (any(found) if any_word else all(found)):
                    continue
            cleared = None
            if use is not None:
                cleared = [
                    s
                    for s, _, _ in sightings
                    if rights.verdict(rec.deals, s, rec.provenance, use, span).cleared
                ]
                if not cleared:
                    continue
            names = [s for s, _, _ in sightings]
            hits.append(Hit(asset, sightings[0][2], sightings[0][1], names, cleared))
        return hits

    def show(self, asset: str) -> AssetView:
        asset = self._asset_id(asset)
        with self._db() as db:
            sightings = self._sightings_of(db, asset)
        rec = self._record_or_default(asset)
        return AssetView(
            asset=asset,
            kind=sightings[0][2],
            size=sightings[0][1],
            sightings=[s for s, _, _ in sightings],
            provenance=rec.provenance,
            tags=rec.tags,
            creator=rec.creator,
            deals=[DealView(d.id, deal_status(d), d) for d in rec.deals],
        )

    def check(
        self, asset: str, use: rights.Use, window: tuple[date, date] | None
    ) -> list[SightingVerdict]:
        asset = self._asset_id(asset)
        self._check_use(use)
        span = self._window(window)
        with self._db() as db:
            sightings = self._sightings_of(db, asset)
        rec = self._record_or_default(asset)
        return [
            SightingVerdict(s, rights.verdict(rec.deals, s, rec.provenance, use, span))
            for s, _, _ in sightings
        ]

    # -- deals ----------------------------------------------------------------------------

    def propose_deal(
        self,
        asset: str,
        *,
        uses: tuple[str, ...],
        platforms: tuple[str, ...],
        from_date: date,
        to_date: date | None,
        perpetual: bool,
        music: str,
        said_by: str,
        platform_code: tuple[str, date] | None = None,
        evidence_hash: str = "",
        sightings: list[str] | None = None,
    ) -> rights.Deal:
        asset = self._asset_id(asset)
        with self._db() as db:
            current = [s for s, _, _ in self._sightings_of(db, asset)]
        chosen = sightings if sightings else current
        for name in chosen:
            if name not in current:
                raise LibraryError(f"{name} is not a sighting of this asset")
        with self._records_fd(create=True) as fd:
            record = self._read_record(fd, asset) or Record(asset)
            taken = {d.id for r in self._all_records().values() for d in r.deals}
            deal_id = secrets.token_hex(4)
            while deal_id in taken:
                deal_id = secrets.token_hex(4)
            try:
                deal = rights.Deal(
                    id=deal_id,
                    uses=uses,
                    platforms=platforms,
                    from_date=from_date,
                    to_date=to_date,
                    perpetual=perpetual,
                    music=music,
                    platform_code=platform_code,
                    said_by=said_by,
                    evidence_hash=evidence_hash,
                    sightings=tuple(chosen),
                )
            except ValueError as exc:
                raise LibraryError(str(exc)) from exc
            record.deals.append(deal)
            self._write_record(fd, record)
        return deal

    def _locate(self, deal_id: str) -> tuple[Record, int]:
        for record in self._all_records().values():
            for index, deal in enumerate(record.deals):
                if deal.id == deal_id:
                    return record, index
        raise LibraryError(f"no deal {deal_id!r}")

    def _replace_deal(self, record: Record, index: int, deal: rights.Deal) -> None:
        record.deals[index] = deal
        with self._records_fd(create=False) as fd:
            self._write_record(fd, record)

    def approve_deal(
        self, deal_id: str, typed: str, *, has_terminal: bool, approver: str
    ) -> rights.Deal:
        if not has_terminal:
            raise LibraryError("approving a deal needs a person at a terminal; none is attached")
        record, index = self._locate(deal_id)
        deal = record.deals[index]
        if typed.strip() != deal.id:
            raise LibraryError(f"to approve, type the deal id exactly: {deal.id}")
        if deal.state == "revoked":
            raise LibraryError(f"deal {deal.id} is revoked; propose a new deal")
        approved = deal.approve(by=approver, at=self._now().isoformat())
        self._replace_deal(record, index, approved)
        return approved

    def revoke_deal(self, deal_id: str, reason: str) -> rights.Deal:
        record, index = self._locate(deal_id)
        deal = record.deals[index]
        if deal.state == "revoked":
            raise LibraryError(f"deal {deal.id} is already revoked")
        revoked = deal.revoke(reason, self._now().isoformat())
        self._replace_deal(record, index, revoked)
        return revoked


def _flat(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower())


def _words(query: str) -> list[str]:
    return _flat(query).split()
