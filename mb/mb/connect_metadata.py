"""Pure credential-shape analysis for connection metadata."""

from __future__ import annotations

import math
import re
import urllib.parse

# Public credential grammars, one per provider family: the prefix plus the
# shape of the generated part. Each is matched in full, so a word that merely
# shares a prefix ("re_engagement", "pk_test_publishable") is not a key, and a
# real-shaped key is caught whatever its characters ("ghp_" plus lowercase).
# The rule name keeps the prefix so a refusal says which family matched.
METADATA_SECRET_GRAMMARS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("sk_", re.compile(r"sk_(?:live|test)_[A-Za-z0-9]{8,}")),
    ("rk_", re.compile(r"rk_(?:live|test)_[A-Za-z0-9]{8,}")),
    ("pk_live_", re.compile(r"pk_live_[A-Za-z0-9]{8,}")),
    ("whsec_", re.compile(r"whsec_[A-Za-z0-9+/=]{16,}")),
    ("re_", re.compile(r"re_[A-Za-z0-9]{8}_[A-Za-z0-9]{16,}")),
    ("sk-", re.compile(r"sk-[A-Za-z0-9_\-]{20,}")),
    ("ghp_", re.compile(r"ghp_[A-Za-z0-9]{30,}")),
    ("gho_", re.compile(r"gho_[A-Za-z0-9]{30,}")),
    ("ghu_", re.compile(r"ghu_[A-Za-z0-9]{30,}")),
    ("ghs_", re.compile(r"ghs_[A-Za-z0-9]{30,}")),
    ("ghr_", re.compile(r"ghr_[A-Za-z0-9]{30,}")),
    ("github_pat_", re.compile(r"github_pat_[A-Za-z0-9_]{16,}")),
    ("glpat-", re.compile(r"glpat-[A-Za-z0-9_\-]{20,}")),
    ("xox", re.compile(r"xox[abposr]-[A-Za-z0-9\-]{10,}")),
    ("AKIA", re.compile(r"(?:AKIA|ASIA)[A-Z0-9]{16}")),
    ("AIza", re.compile(r"AIza[A-Za-z0-9_\-]{35}")),
    ("cfat_", re.compile(r"cfat_[A-Za-z0-9_\-]{20,}")),
)
_JWT_RE = re.compile(r"^eyJ[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]{4,}\.[A-Za-z0-9_-]*$")
# "Bearer <anything>" as the whole value, or "Bearer <long token>" after a
# label; "bearer" inside an ordinary phrase is not a credential.
_BEARER_RE = re.compile(r"^bearer\s+\S|\sbearer\s+[A-Za-z0-9._~+/=\-]{16,}", re.IGNORECASE)
_TOKEN_CHARSET_RE = re.compile(r"^[A-Za-z0-9+/=_.\-]+$")
# Split a value into words so a credential behind a short label ("note: <key>")
# is judged on its own: first on spaces, commas and semicolons, then on `:`
# and `=`. Structured references (URLs, op:// refs, emails) are not split on
# `:`/`=`; a URL's query values are judged one by one instead.
_METADATA_CHUNK_SPLIT_RE = re.compile(r"[\s,;]+")
_METADATA_LABEL_SPLIT_RE = re.compile(r"[:=]")
_METADATA_URL_START_RE = re.compile(r"(?<![A-Za-z0-9+.\-])[A-Za-z][A-Za-z0-9+.\-]*://")
_METADATA_URL_PIECE_RE = re.compile(r"[/&?;#@]")
_METADATA_IPV4_RE = re.compile(r"[0-9]{1,3}(?:\.[0-9]{1,3}){3}")
_METADATA_URL_DECODE_PASSES = 3
_METADATA_URL_MAX_DEPTH = 3
_METADATA_EMAIL_RE = re.compile(r"^[^@\s:=/]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
METADATA_ENTROPY_MIN_LENGTH = 24
METADATA_ENTROPY_MIN_BITS = 3.5
# CamelCase and digit segments: "AcmeProd2026" -> Acme, Prod, 2026.
_METADATA_SEGMENT_RE = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|[0-9]+")
_METADATA_VERSION_TAIL_RE = re.compile(r"[A-Z][0-9]{1,3}$")
_VOWELS = frozenset("aeiouyAEIOUY")
# Abbreviations with digits between words ("CloudflareR2Storage",
# "B2BMarketing"): capital and digit segments that together form a short code.
_METADATA_CODE_PART_RE = re.compile(r"[A-Z]+|[0-9]+")
_METADATA_CODE_MAX_LENGTH = 4
# At the start or end of a value only the tightest code shape counts ("S3",
# "B2B"), next to a word of at least this many letters.
_METADATA_EDGE_CODE_RE = re.compile(r"[A-Z][0-9]{1,2}[A-Z]?")
_METADATA_EDGE_WORD_MIN_LENGTH = 6
_METADATA_WORD_RE = re.compile(r"[A-Z][a-z]{3,}")
_METADATA_CONSONANT_RUN_RE = re.compile(r"[^aeiouyAEIOUY]{4,}")
# Share of segments that look generated rather than written. Labels are made
# of words ("Us", "Api", "Name", "2026") and score near 0; random tokens break
# into single letters, vowel-less runs and lone digits and score well above.
# Miss rates for this threshold are measured in docs/connect.md.
METADATA_MIN_GENERATED_SEGMENT_SHARE = 0.3


def _shannon_bits_per_char(value: str) -> float:
    counts: dict[str, int] = {}
    for char in value:
        counts[char] = counts.get(char, 0) + 1
    total = len(value)
    return -sum((count / total) * math.log2(count / total) for count in counts.values())


def _reads_as_word(segment: str) -> bool:
    """A capitalised, pronounceable word of four or more letters."""
    if not _METADATA_WORD_RE.fullmatch(segment):
        return False
    vowels = sum(char in _VOWELS for char in segment)
    return vowels * 10 >= 3 * len(segment) and not _METADATA_CONSONANT_RUN_RE.search(segment)


def _merge_metadata_codes(segments: list[str]) -> list[str | None]:
    """Replace short letter-digit codes between words with ``None`` (a word).

    "CloudflareR2Storage" segments as Cloudflare, R, 2, Storage; R and 2 read
    as generated on their own. Merged, R2 sits between two real words and
    counts as one word. Random tokens rarely put a code between pronounceable
    words, so the miss rates in docs/connect.md hold.
    """
    merged: list[str | None] = []
    index = 0
    while index < len(segments):
        if not _METADATA_CODE_PART_RE.fullmatch(segments[index]):
            merged.append(segments[index])
            index += 1
            continue
        end = index
        while end < len(segments) and _METADATA_CODE_PART_RE.fullmatch(segments[end]):
            end += 1
        run = segments[index:end]
        code = "".join(run)
        left = segments[index - 1] if index > 0 else None
        right = segments[end] if end < len(segments) else None
        if left is not None and right is not None:
            beside_words = _reads_as_word(left) and _reads_as_word(right)
        else:
            neighbour = left if left is not None else right
            beside_words = (
                neighbour is not None
                and _reads_as_word(neighbour)
                and len(neighbour) >= _METADATA_EDGE_WORD_MIN_LENGTH
                and bool(_METADATA_EDGE_CODE_RE.fullmatch(code))
            )
        if (
            len(run) > 1
            and len(code) <= _METADATA_CODE_MAX_LENGTH
            and any(char.isdigit() for char in code)
            and beside_words
        ):
            merged.append(None)
        else:
            merged.extend(run)
        index = end
    return merged


def _segment_is_generated(segment: str) -> bool:
    if segment.isdigit():
        return len(segment) == 1
    return len(segment) == 1 or not any(char in _VOWELS for char in segment)


def _generated_segment_share(value: str) -> float:
    """Share of CamelCase/digit segments that do not read as words.

    A segment counts as generated when it is a single letter, a letter run
    with no vowel, or a lone digit. A trailing version such as ``V2`` counts
    as a word. A short code between words such as ``R2`` or ``B2B`` counts
    as a word only when every other segment reads as a word too, apart from
    a final lone digit (``S3ProductionBucketUsWest2``); a code next to a
    generated tail ("<words>R2<words>Qe7Lo") is judged letter by letter.
    """
    body = value
    version = _METADATA_VERSION_TAIL_RE.search(value)
    if version:
        body = value[: version.start()]
    raw = _METADATA_SEGMENT_RE.findall(body)
    segments = _merge_metadata_codes(raw)
    if None in segments:
        others = [segment for segment in segments if segment is not None]
        if others and others[-1].isdigit() and segments[-1] is not None:
            others = others[:-1]
        if any(_segment_is_generated(segment) for segment in others):
            segments = list(raw)
    total = len(segments) + (1 if version else 0)
    if not total:
        return 0.0
    generated = sum(
        1 for segment in segments if segment is not None and _segment_is_generated(segment)
    )
    return generated / total


def _word_secret_rule(word: str) -> str:
    for prefix, grammar in METADATA_SECRET_GRAMMARS:
        if grammar.fullmatch(word):
            return f"credential_prefix:{prefix}"
    if _JWT_RE.fullmatch(word):
        return "jwt_shape"
    # Long random-looking strings: mixed case, nothing but token characters,
    # enough entropy, and segments that do not read as words. Hex ids, UUIDs,
    # numeric ids, URLs, emails, lowercase paths and CamelCase labels fall
    # outside this on purpose.
    if (
        len(word) >= METADATA_ENTROPY_MIN_LENGTH
        and _TOKEN_CHARSET_RE.fullmatch(word)
        and any(char.isupper() for char in word)
        and any(char.islower() for char in word)
        and _shannon_bits_per_char(word) >= METADATA_ENTROPY_MIN_BITS
        and _generated_segment_share(word) >= METADATA_MIN_GENERATED_SEGMENT_SHARE
    ):
        return "high_entropy"
    return ""


def _fully_unquote(text: str) -> str:
    """Percent-decode until stable, at most ``_METADATA_URL_DECODE_PASSES`` times."""
    for _ in range(_METADATA_URL_DECODE_PASSES):
        decoded = urllib.parse.unquote(text)
        if decoded == text:
            break
        text = decoded
    return text


def _url_host_labels(netloc: str) -> list[str]:
    """Host labels as written (case kept), minus IP addresses and punycode."""
    host = netloc.rpartition("@")[2]
    if host.startswith("["):
        return []
    host = host.split(":", 1)[0]
    if _METADATA_IPV4_RE.fullmatch(host):
        return []
    return [label for label in host.split(".") if not label.lower().startswith("xn--")]


def _url_parts(reference: str, depth: int = 0) -> list[str]:
    """Decoded user name, password, host labels, path, query and fragment pieces.

    Each component is fully decoded before it is split, so an encoded
    separator (``%2F``) or a double-encoded token is judged as written. A URL
    nested inside a component is inspected the same way, up to
    ``_METADATA_URL_MAX_DEPTH`` levels.
    """
    try:
        parsed = urllib.parse.urlsplit(reference)
        # Reading every field validates it: a bad port or bracket raises here.
        components = [parsed.username or "", parsed.password or ""]
        _ = (parsed.hostname, parsed.port)
    except ValueError:
        # Unparseable: judge the decoded raw pieces instead.
        return [piece for piece in _METADATA_URL_PIECE_RE.split(_fully_unquote(reference)) if piece]
    parts = list(_url_host_labels(parsed.netloc))
    components += [parsed.path, parsed.query, parsed.fragment]
    for component in components:
        decoded = _fully_unquote(component)
        nested = _METADATA_URL_START_RE.search(decoded)
        if nested and depth < _METADATA_URL_MAX_DEPTH:
            parts.extend(_url_parts(decoded[nested.start() :], depth + 1))
            decoded = decoded[: nested.start()]
        parts.extend(piece for piece in _METADATA_URL_PIECE_RE.split(decoded) if piece)
    return parts
