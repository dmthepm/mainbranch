"""The media library's index: what was seen where, as one plain file.

It is rebuildable from the sources, so nothing is lost if it is deleted or
unreadable. It is loaded whole and replaced whole through the checked folder
descriptor (:func:`mb.library_files.write_file`), so every byte it writes goes
where the folder checks said. A database engine opens files by path and keeps
side files of its own; this does neither.
"""

from __future__ import annotations

import json
from typing import Any, NamedTuple

from mb.library_files import LibraryError, read_file, write_file

INDEX_NAME = "index.json"
_VERSION = 1


class Sighting(NamedTuple):
    asset: str
    size: int
    mtime_ns: int
    kind: str


class Index:
    def __init__(self, dir_fd: int, rows: dict[tuple[str, str], Sighting]) -> None:
        self._fd = dir_fd
        self._rows = rows

    @classmethod
    def load(cls, dir_fd: int, *, rebuild: bool = False) -> Index:
        """Read the index. An unreadable one is refused, or with `rebuild` started afresh."""
        raw = read_file(dir_fd, INDEX_NAME)
        if raw is None:
            return cls(dir_fd, {})
        try:
            return cls(dir_fd, _decode(raw))
        except (ValueError, TypeError, KeyError, IndexError, RecursionError):
            if rebuild:
                return cls(dir_fd, {})
            raise LibraryError(
                f"the index ({INDEX_NAME}) cannot be read; delete it and run `mb library scan`"
            ) from None

    def flush(self) -> None:
        rows = [[s, p, *row] for (s, p), row in sorted(self._rows.items())]
        blob = json.dumps({"version": _VERSION, "sightings": rows}, separators=(",", ":"))
        write_file(self._fd, INDEX_NAME, blob.encode())

    def known(self, source: str) -> dict[str, tuple[int, int, str]]:
        """Path -> (size, mtime_ns, asset) for one source."""
        return {
            path: (row.size, row.mtime_ns, row.asset)
            for (name, path), row in self._rows.items()
            if name == source
        }

    def put(self, source: str, path: str, row: Sighting) -> None:
        self._rows[(source, path)] = row

    def remove(self, source: str, paths: list[str]) -> None:
        for path in paths:
            self._rows.pop((source, path), None)

    def count(self) -> int:
        return len(self._rows)

    def by_asset(self) -> dict[str, list[tuple[str, str, Sighting]]]:
        """Every asset's sightings, ordered by (source, path); assets in id order."""
        grouped: dict[str, list[tuple[str, str, Sighting]]] = {}
        for (source, path), row in sorted(self._rows.items(), key=lambda it: (it[1].asset, *it[0])):
            grouped.setdefault(row.asset, []).append((source, path, row))
        return grouped


def _decode(raw: bytes) -> dict[tuple[str, str], Sighting]:
    data: Any = json.loads(raw)
    if data["version"] != _VERSION:
        raise ValueError("unknown index version")
    rows: dict[tuple[str, str], Sighting] = {}
    for source, path, asset, size, mtime_ns, kind in data["sightings"]:
        texts = (source, path, asset, kind)
        numbers = (size, mtime_ns)
        if not all(isinstance(t, str) for t in texts) or not all(
            isinstance(n, int) and not isinstance(n, bool) for n in numbers
        ):
            raise ValueError("index row has the wrong types")
        rows[(source, path)] = Sighting(asset, size, mtime_ns, kind)
    return rows
