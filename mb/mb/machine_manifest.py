"""Bounded manifest loading and the committed schema's stdlib validation subset."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_PATH = Path("/etc/mainbranch/machine.json")
MAX_BYTES = 256 * 1024
SCHEMA = json.loads((Path(__file__).parent / "_data/machine-manifest.schema.json").read_text())
CHECK_IDS = frozenset(
    json.loads((Path(__file__).parent / "_data/machine-check-ids.json").read_text())
)


# Reviewed read identities and maximum ages in days. None means manifest policy.
ATTESTABLE: dict[tuple[str, str], int | None] = {
    ("host.power-on-after-loss", "bios_power_on"): 180,
    ("host.disk-luks2-tpm", "header_offbox"): 365,
    ("host.disk-luks2-tpm-arch", "header_offbox"): 365,
    ("owner.sudo-needs-password", "no_nopasswd"): 90,
    ("owner.no-sudo-into-business", "no_runas_business"): 90,
    ("backups.fresh", "last_backup"): None,
    ("backups.restore-tested", "restore_test_attested"): None,
    ("hardening.firmware-manual", "no_auto_firmware"): 180,
}


def attestation_time(value: str) -> datetime:
    """Parse a schema-validated UTC timestamp, including calendar validity."""
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError as exc:
        raise ManifestError("Invalid attestation timestamp") from exc


class ManifestError(ValueError):
    """Invalid manifest data, never containing the rejected value."""


class IntegrityError(ValueError):
    """Default policy could not be read through trusted descriptors."""


def _equal(left: Any, right: Any) -> bool:
    if isinstance(left, bool) != isinstance(right, bool):
        return False
    return bool(left == right)


def _matches(value: Any, schema: Any) -> bool:
    try:
        _validate(value, schema)
        return True
    except ManifestError:
        return False


def _validate(value: Any, schema: Any) -> None:
    if schema is False:
        raise ManifestError("Forbidden value")
    if schema is True:
        return
    if "$ref" in schema:
        _validate(value, SCHEMA["$defs"][schema["$ref"].split("/")[-1]])
    types = {"object": dict, "array": list, "string": str, "integer": int, "boolean": bool}
    if "type" in schema:
        allowed = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(type(value) is types[t] for t in allowed):
            raise ManifestError("Invalid type")
    if "const" in schema and not _equal(value, schema["const"]):
        raise ManifestError("Invalid constant")
    if "enum" in schema and not any(_equal(value, item) for item in schema["enum"]):
        raise ManifestError("Unknown value")
    if "not" in schema and _matches(value, schema["not"]):
        raise ManifestError("Forbidden value")
    if "oneOf" in schema and sum(_matches(value, s) for s in schema["oneOf"]) != 1:
        raise ManifestError("Invalid variant")
    for sub in schema.get("allOf", []):
        _validate(value, sub)
    if "if" in schema and _matches(value, schema["if"]):
        _validate(value, schema.get("then", True))
    if isinstance(value, dict):
        if not set(schema.get("required", [])).issubset(value):
            raise ManifestError("Missing required key")
        if len(value) < schema.get("minProperties", 0):
            raise ManifestError("Too few properties")
        props = schema.get("properties", {})
        for key, item in value.items():
            _validate(item, props.get(key, schema.get("additionalProperties", True)))
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            raise ManifestError("Too few items")
        if schema.get("uniqueItems") and any(
            _equal(item, earlier) for i, item in enumerate(value) for earlier in value[:i]
        ):
            raise ManifestError("Duplicate item")
        for item in value:
            _validate(item, schema.get("items", True))
    if isinstance(value, str):
        if not schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", MAX_BYTES):
            raise ManifestError("Invalid text length")
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            raise ManifestError("Invalid text pattern")
    if type(value) is int and not schema.get("minimum", value) <= value <= schema.get(
        "maximum", value
    ):
        raise ManifestError("Outside numeric range")


SUPPORTED_KEYWORDS = frozenset(
    [
        "$comment",
        "$defs",
        "$id",
        "$ref",
        "$schema",
        "additionalProperties",
        "allOf",
        "const",
        "default",
        "description",
        "enum",
        "if",
        "items",
        "maxLength",
        "maximum",
        "minItems",
        "minLength",
        "minProperties",
        "minimum",
        "not",
        "oneOf",
        "pattern",
        "properties",
        "required",
        "then",
        "title",
        "type",
        "uniqueItems",
    ]
)


def _has_control(value: Any) -> bool:
    if isinstance(value, str):
        return any(ord(char) < 32 or ord(char) == 127 for char in value)
    if isinstance(value, dict):
        return any(_has_control(key) or _has_control(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_has_control(item) for item in value)
    return False


def validate(value: Any) -> None:
    """Validate structure and references that JSON Schema cannot express.

    Python's ``$`` also matches before a final newline, so schema patterns
    alone would let ``x.service\\n`` through: no manifest text may hold a
    control character.
    """
    _validate(value, SCHEMA)
    if _has_control(value):
        raise ManifestError("Control character in manifest text")
    identities: set[tuple[str, str]] = set()
    for entry in value["checks"].get("attest", []):
        identity = (entry["id"], entry["read"])
        if identity not in ATTESTABLE or identity in identities:
            raise ManifestError("Invalid or duplicate attestation identity")
        identities.add(identity)
        attestation_time(entry["at"])
    classes = value["businesses"]["size_classes"]
    if any(user["size_class"] not in classes for user in value["businesses"]["users"]):
        raise ManifestError("Unknown size class")


def _pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in items:
        if key in result:
            raise ManifestError("Duplicate JSON key")
        result[key] = value
    return result


def _trusted(info: os.stat_result, directory: bool) -> None:
    kind = stat.S_ISDIR if directory else stat.S_ISREG
    if not kind(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
        raise IntegrityError("Untrusted default manifest")


def _read(path: Path, trusted: bool) -> bytes:
    """Walk from root with pinned directory descriptors and no symlink following."""
    current = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        if trusted:
            _trusted(os.fstat(current), True)
        parts = path.absolute().parts[1:]
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current)
            os.close(current)
            current = child
            if trusted:
                _trusted(os.fstat(current), True)
        info = os.stat(parts[-1], dir_fd=current, follow_symlinks=False)
        if trusted:
            _trusted(info, False)
        elif not stat.S_ISREG(info.st_mode):
            raise ManifestError("Manifest must be a regular file")
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=current)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if trusted:
                _trusted(info, False)
            elif not stat.S_ISREG(info.st_mode):
                raise ManifestError("Manifest must be a regular file")
            if info.st_size > MAX_BYTES:
                raise ManifestError("Manifest exceeds byte cap")
            data = stream.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                raise ManifestError("Manifest exceeds byte cap")
            return data
    finally:
        os.close(current)


def load(path: Path | None = None) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    trusted = path is None
    selected = DEFAULT_PATH if trusted else path
    assert selected is not None
    if trusted:
        try:
            selected.lstat()
        except FileNotFoundError:
            return None, {"source": "none", "reason": "no_manifest"}
        except OSError:
            raise IntegrityError("Cannot inspect default manifest") from None
    try:
        data = _read(selected, trusted)
    except OSError:
        error = IntegrityError if trusted else ManifestError
        raise error("Cannot read manifest") from None
    try:
        value = json.loads(
            data, object_pairs_hook=_pairs, parse_constant=lambda _: _reject_constant()
        )
        validate(value)
    except (ValueError, UnicodeError, RecursionError):
        raise ManifestError("Invalid manifest") from None
    return value, {
        "source": "default_path" if trusted else "caller_selected",
        "sha256": hashlib.sha256(data).hexdigest(),
        "manifest_version": 1,
    }


def _reject_constant() -> None:
    raise ManifestError("Non-JSON numeric constant")
