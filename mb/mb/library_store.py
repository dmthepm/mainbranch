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
    display,
    exclusive,
    open_dir,
    read_file,
    refuse_overlap,
    write_file,
)
from mb.library_index import ASSET_ID, SOURCE_NAME, Index, Sighting

CONFIG_REL = ".mb/private/library"
DEFAULT_RECORDS = "library/records"
BATCH = 5000  # files between index rewrites; the index is replaced whole each time
MAX_YAML_BYTES = 1 << 20
MAX_YAML_DEPTH = 12
MAX_YAML_NODES = 50_000
_NAME = SOURCE_NAME
_ASSET = ASSET_ID
_KINDS = {
    "photo": {"jpg", "jpeg", "png", "webp", "gif", "heic", "tif", "tiff", "avif"},
    "video": {"mp4", "mov", "m4v", "webm", "mkv", "avi"},
    "audio": {"mp3", "wav", "m4a", "aac", "flac", "ogg"},
    "document": {"pdf"},
}
_MERGE_TAG = "tag:yaml.org,2002:merge"
LOCK_NAME = "index.lock"


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
class FindReport:
    hits: list[Hit]
    not_cleared: int = 0


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


def deal_status(deal: rights.Deal, asset: str, provenance: str) -> str:
    if deal.state == "approved" and not deal.is_active_for(asset, provenance):
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
        no_library = LibraryError(
            "no media library here yet: add a source first (mb library source add <name> <folder>)"
        )
        try:
            with self._dir(CONFIG_REL, create=init) as fd:
                raw = read_file(fd, "config.yaml", limit=MAX_YAML_BYTES)
        except MissingFolder:
            raise no_library from None
        if raw is None and not init:
            raise no_library
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
        data = _load_yaml(raw or b"", "config.yaml")
        if not isinstance(data, dict):
            raise LibraryError("config.yaml must be a mapping")
        sources = data.get("sources") or {}
        records = data.get("records_dir", DEFAULT_RECORDS)
        zone = data.get("timezone", "UTC")
        if not isinstance(zone, str):
            raise LibraryError("config.yaml timezone must be text such as UTC")
        if not isinstance(sources, dict) or not all(
            isinstance(k, str) and _NAME.fullmatch(k) and isinstance(v, str)
            for k, v in sources.items()
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
            write_file(fd, "config.yaml", _readable(text, "config.yaml"))

    def add_source(self, name: str, path: str | Path) -> Path:
        if not _NAME.fullmatch(name):
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
    def _index(self) -> Iterator[Index]:
        """The index for reading. Replaced whole by a scan, so a read sees one whole version."""
        with self._dir(CONFIG_REL, create=False) as fd:
            yield Index.load(fd)

    @contextlib.contextmanager
    def _index_for_scan(self) -> Iterator[Index]:
        with self._dir(CONFIG_REL, create=False) as fd, exclusive(fd, LOCK_NAME):
            yield Index.load(fd, rebuild=True)

    def scan(self, *, verify: bool = False) -> ScanReport:
        report = ScanReport()
        for name, folder in sorted(self.sources.items()):
            if library_source.root_problem(folder) == "writable":
                raise LibraryError(
                    f"source {name!r} ({folder}) is writable by this user; refusing to scan"
                )
        now_ns = int(self._now().timestamp() * 1_000_000_000)
        with self._index_for_scan() as index:
            for name, folder in sorted(self.sources.items()):
                problem = library_source.root_problem(folder)
                if problem:
                    report.unavailable.append((name, problem))
                    continue
                self._scan_one(index, name, folder, now_ns, verify, report)
            report.indexed = index.count()
            report.duplicates = {
                asset: sorted(f"{source}:{path}" for source, path, _ in places)
                for asset, places in index.by_asset().items()
                if len(places) > 1
            }
        return report

    def _scan_one(
        self,
        index: Index,
        name: str,
        folder: Path,
        now_ns: int,
        verify: bool,
        report: ScanReport,
    ) -> None:
        known = index.known(name)
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
                index.put(
                    name,
                    item.rel,
                    Sighting(item.sha256, item.size, item.mtime_ns, kind_of(item.rel)),
                )
                pending += 1
                if pending >= BATCH:
                    index.flush()
                    pending = 0
        except OSError as exc:
            report.unavailable.append((name, exc.strerror or "unreadable"))
            index.flush()
            return
        gone = [path for path in known if path not in seen]
        report.removed += len(gone)
        index.remove(name, gone)
        index.flush()
        report.skipped.extend(skipped)

    # -- records ------------------------------------------------------------------

    def _records_fd(self, *, create: bool) -> contextlib.AbstractContextManager[int]:
        return self._dir(self.records_rel, create=create)

    def _read_record(self, fd: int, asset: str) -> Record | None:
        raw = read_file(fd, f"{asset}.yaml", limit=MAX_YAML_BYTES)
        if raw is None:
            return None
        label = f"record {asset[:12]}"
        data = _load_yaml(raw, label)
        if not isinstance(data, dict):
            raise LibraryError(f"{label} must be a mapping")
        if data.get("asset") != asset:
            raise LibraryError(
                f"{label}: its asset field {display(str(data.get('asset')))!r} does not match "
                "the file name; a record belongs to the bytes it was written for"
            )
        provenance = data.get("provenance", "unknown")
        if provenance not in rights.PROVENANCE:
            raise LibraryError(
                f"{label}: provenance {provenance!r} must be one of {', '.join(rights.PROVENANCE)}"
            )
        tags = data.get("tags") or []
        if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
            raise LibraryError(f"{label}: tags must be a list of text")
        creator = data.get("creator") or ""
        if not isinstance(creator, str):
            raise LibraryError(f"{label}: creator must be text")
        raw_deals = data.get("deals") or []
        if not isinstance(raw_deals, list):
            raise LibraryError(f"{label}: deals must be a list")
        try:
            deals = [rights.Deal.from_mapping(d) for d in raw_deals]
        except (ValueError, AttributeError, TypeError) as exc:
            raise LibraryError(f"{label}: {exc}") from exc
        return Record(asset, provenance, list(tags), creator, deals)

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
        write_file(fd, f"{record.asset}.yaml", _readable(text, f"record {record.asset[:12]}"))

    def _all_records(self) -> dict[str, Record]:
        records: dict[str, Record] = {}
        try:
            with self._records_fd(create=False) as fd:
                with os.scandir(fd) as entries:
                    names = sorted(e.name for e in entries)
                for name in names:
                    stem = name[:-5]
                    if name.endswith(".yaml") and _ASSET.fullmatch(stem):
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
        if not _ASSET.fullmatch(asset):
            raise LibraryError("give the full 64-character asset id (see `mb library find`)")
        return asset

    def _sightings_of(self, index: Index, asset: str) -> list[tuple[str, int, str]]:
        rows = index.by_asset().get(asset)
        if not rows:
            raise LibraryError(f"unknown asset {asset[:12]}…; run `mb library scan` first")
        return [(f"{s}:{p}", row.size, row.kind) for s, p, row in rows]

    def find(
        self,
        query: str = "",
        *,
        kind: str | None = None,
        use: rights.Use | None = None,
        window: tuple[date, date] | None = None,
        any_word: bool = False,
    ) -> list[Hit]:
        return self.find_report(query, kind=kind, use=use, window=window, any_word=any_word).hits

    def find_report(
        self,
        query: str = "",
        *,
        kind: str | None = None,
        use: rights.Use | None = None,
        window: tuple[date, date] | None = None,
        any_word: bool = False,
    ) -> FindReport:
        """Matches for the words; with a use, only cleared ones, and a count of the rest."""
        if use is not None:
            self._check_use(use)
        span = self._window(window)
        words = _words(query)
        grouped: dict[str, list[tuple[str, int, str]]] = defaultdict(list)
        with self._index() as index:
            for asset, places in index.by_asset().items():
                grouped[asset] = [(f"{s}:{p}", row.size, row.kind) for s, p, row in places]
        records = self._all_records() if (words or use is not None) else {}
        hits: list[Hit] = []
        not_cleared = 0
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
                    if rights.verdict(rec.deals, s, rec.provenance, use, span, asset=asset).cleared
                ]
                if not cleared:
                    not_cleared += 1
                    continue
            names = [s for s, _, _ in sightings]
            hits.append(Hit(asset, sightings[0][2], sightings[0][1], names, cleared))
        return FindReport(hits, not_cleared)

    def show(self, asset: str) -> AssetView:
        asset = self._asset_id(asset)
        with self._index() as index:
            sightings = self._sightings_of(index, asset)
        rec = self._record_or_default(asset)
        return AssetView(
            asset=asset,
            kind=sightings[0][2],
            size=sightings[0][1],
            sightings=[s for s, _, _ in sightings],
            provenance=rec.provenance,
            tags=rec.tags,
            creator=rec.creator,
            deals=[DealView(d.id, deal_status(d, asset, rec.provenance), d) for d in rec.deals],
        )

    def check(
        self, asset: str, use: rights.Use, window: tuple[date, date] | None
    ) -> list[SightingVerdict]:
        asset = self._asset_id(asset)
        self._check_use(use)
        span = self._window(window)
        with self._index() as index:
            sightings = self._sightings_of(index, asset)
        rec = self._record_or_default(asset)
        return [
            SightingVerdict(s, rights.verdict(rec.deals, s, rec.provenance, use, span, asset=asset))
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
        with self._index() as index:
            current = [s for s, _, _ in self._sightings_of(index, asset)]
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
        approved = deal.approve(
            by=approver,
            at=self._now().isoformat(),
            asset=record.asset,
            provenance=record.provenance,
        )
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


def _load_yaml(raw: bytes, label: str) -> Any:
    """Parse a small YAML file, refusing big or deeply nested input by name."""
    if len(raw) > MAX_YAML_BYTES:
        raise LibraryError(f"{label} is too large ({len(raw)} bytes; limit {MAX_YAML_BYTES})")
    _refuse_aliases(raw, label)
    try:
        data = yaml.safe_load(raw) or {}
    except yaml.YAMLError as exc:
        raise LibraryError(f"{label} is not valid YAML: {exc}") from exc
    except RecursionError:
        raise LibraryError(f"{label} is nested too deeply to read") from None
    pending: list[tuple[Any, int]] = [(data, 1)]
    seen = 0
    while pending:
        value, depth = pending.pop()
        seen += 1
        if depth > MAX_YAML_DEPTH:
            raise LibraryError(f"{label} is nested too deeply (limit {MAX_YAML_DEPTH} levels)")
        if seen > MAX_YAML_NODES:
            raise LibraryError(f"{label} has too many entries (limit {MAX_YAML_NODES})")
        if isinstance(value, dict):
            pending.extend((item, depth + 1) for item in [*value.keys(), *value.values()])
        elif isinstance(value, list):
            pending.extend((item, depth + 1) for item in value)
    return data


def _readable(text: str, label: str) -> bytes:
    """`text` as bytes, if the reader would accept it; else refuse, so the old file stays."""
    data = text.encode()
    try:
        _load_yaml(data, label)
    except LibraryError as exc:
        raise LibraryError(f"{exc}; nothing was saved and the earlier version is kept") from exc
    return data


def _refuse_aliases(raw: bytes, label: str) -> None:
    """Refuse aliases and merge keys from the parser's events, before anything is built.

    Records and config never need them, and building a document that uses them
    can expand a few hundred bytes into more memory than the process has.
    """
    try:
        for event in yaml.parse(raw, Loader=yaml.SafeLoader):
            merge = isinstance(event, yaml.ScalarEvent) and (
                (event.value == "<<" and event.implicit[0]) or event.tag == _MERGE_TAG
            )
            if isinstance(event, yaml.AliasEvent) or merge:
                raise LibraryError(f"{label} uses a YAML alias or merge key, which is not allowed")
    except yaml.YAMLError as exc:
        raise LibraryError(f"{label} is not valid YAML: {exc}") from exc


def _flat(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower())


def _words(query: str) -> list[str]:
    return _flat(query).split()
