"""Phone decision cards: a JSON spec in, a JPG out, house rules enforced here.

Spec: {"title", "sub", "sections": [{"head", "bullets": [...],
"options": [{"key", "label", "detail", "rec"}]}], "footer"}

Rules the tool enforces so nobody has to remember them: 1320 px wide, large
type, numbered sections, lettered options with the pick marked, no taller than
3:1, under 2 MB. Pillow is optional (``pip install 'mainbranch[cards]'``) and
the type is Pillow's own built-in font, so output does not depend on which
fonts the machine has.
"""

from __future__ import annotations

import io
import json
import os
import secrets
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

WIDTH = 1320
MARGIN = 64
MAX_RATIO = 3
MAX_BYTES = 2_000_000
QUALITIES = (88, 80, 72, 64)
MAX_SPEC_BYTES = 100_000
MAX_SECTIONS = 12
MAX_ITEMS = 12  # bullets, and options, per section
MAX_TEXT = 1000  # characters in any one field

INSTALL_HINT = "mb card needs Pillow: pip install 'mainbranch[cards]'"

_TOP = {"title", "sub", "sections", "footer"}
_SECTION = {"head", "bullets", "options"}
_OPTION = {"key", "label", "detail", "rec"}

INK, GREY, GREEN = (28, 25, 23), (87, 80, 75), (21, 128, 61)
PALE, PICK = (245, 243, 240), (220, 252, 231)


class CardError(Exception):
    """The spec or the result breaks a house rule; the message names which."""


def _load_pillow() -> Any:
    """Pillow's ImageFont module, or None if Pillow is missing or too old for its built-in font."""
    try:
        import PIL
        from PIL import ImageFont
    except ImportError:
        return None
    major, minor, *_ = (int(p) for p in PIL.__version__.split(".")[:2] + ["0"])
    return ImageFont if (major, minor) >= (10, 1) else None


def validate(spec: object) -> dict[str, Any]:
    """Return the spec if it is well formed; otherwise raise naming the bad field."""
    if not isinstance(spec, dict):
        raise CardError("spec must be a JSON object")
    _only(spec, _TOP, "")
    _text(spec, "title", "title", required=True)
    _text(spec, "sub", "sub")
    _text(spec, "footer", "footer")
    sections = spec.get("sections")
    if not isinstance(sections, list) or not sections:
        raise CardError("sections must be a non-empty list")
    if len(sections) > MAX_SECTIONS:
        raise CardError(f"sections has {len(sections)} entries, over the limit of {MAX_SECTIONS}")
    for i, sec in enumerate(sections):
        where = f"sections[{i}]"
        if not isinstance(sec, dict):
            raise CardError(f"{where} must be an object")
        _only(sec, _SECTION, where + ".")
        _text(sec, "head", f"{where}.head", required=True)
        bullets = sec.get("bullets", [])
        if not isinstance(bullets, list) or not all(isinstance(b, str) and b for b in bullets):
            raise CardError(f"{where}.bullets must be a list of non-empty strings")
        options = sec.get("options", [])
        if not isinstance(options, list):
            raise CardError(f"{where}.options must be a list")
        for what, items in (("bullets", bullets), ("options", options)):
            if len(items) > MAX_ITEMS:
                raise CardError(
                    f"{where}.{what} has {len(items)} entries, over the limit of {MAX_ITEMS}"
                )
        for k, bullet in enumerate(bullets):
            _check_text(bullet, f"{where}.bullets[{k}]")
        for j, opt in enumerate(options):
            ow = f"{where}.options[{j}]"
            if not isinstance(opt, dict):
                raise CardError(f"{ow} must be an object")
            _only(opt, _OPTION, ow + ".")
            _text(opt, "key", f"{ow}.key", required=True)
            _text(opt, "label", f"{ow}.label", required=True)
            _text(opt, "detail", f"{ow}.detail")
            if not isinstance(opt.get("rec", False), bool):
                raise CardError(f"{ow}.rec must be true or false")
    return spec


def _only(obj: dict[str, Any], allowed: set[str], prefix: str) -> None:
    for name in obj:
        if name not in allowed:
            raise CardError(
                f"unknown field {prefix}{_safe(name)} (allowed: {', '.join(sorted(allowed))})"
            )


def _text(obj: dict[str, Any], name: str, label: str, required: bool = False) -> None:
    value = obj.get(name)
    if value is None and not required:
        return
    if not isinstance(value, str) or not value.strip():
        raise CardError(f"{label} must be a non-empty string")
    _check_text(value, label)


def _check_text(value: str, label: str) -> None:
    if len(value) > MAX_TEXT:
        raise CardError(f"{label} is {len(value)} characters, over the limit of {MAX_TEXT}")
    if any(unicodedata.category(c) == "Cc" and c != "\n" for c in value):
        raise CardError(f"{label} contains a control character")


def _safe(value: object, limit: int = 200) -> str:
    """Show caller-supplied text in a message with control characters escaped."""
    return str(value).encode("unicode_escape").decode("ascii")[:limit]


@dataclass
class Plan:
    height: int = 0
    ops: list[tuple[Any, ...]] = field(default_factory=list)
    section_numbers: list[int] = field(default_factory=list)

    def text_lines(self) -> list[str]:
        lines: list[str] = []
        for op in self.ops:
            if op[0] == "h":
                lines.extend(op[2])
            elif op[0] in ("t", "o"):
                lines.append(op[2])
        return lines


def _font(image_font: Any, size: int) -> Any:
    return image_font.load_default(size=size)


def _wrap(text: str, font: Any, width: int, stroke: int = 0) -> list[str]:
    """Wrap to width; a word wider than a whole line is split, never clipped."""

    def fits(t: str) -> bool:
        return bool(font.getlength(t) + 2 * stroke <= width)

    lines: list[str] = []
    for para in text.splitlines() or [""]:
        line = ""
        for word in para.split():
            while not fits(word):
                n = 1
                while n < len(word) - 1 and fits(word[: n + 1]):
                    n += 1
                if line:
                    lines.append(line)
                    line = ""
                lines.append(word[:n])
                word = word[n:]
            trial = f"{line} {word}".strip()
            if line and not fits(trial):
                lines.append(line)
                line = word
            else:
                line = trial
        lines.append(line)
    return lines


def layout(spec: dict[str, Any]) -> Plan:
    """Measure the card. Raises CardError above 3:1; needs Pillow."""
    pil = _load_pillow()
    if pil is None:
        raise CardError(INSTALL_HINT)
    validate(spec)
    big, mid, body = _font(pil, 84), _font(pil, 56), _font(pil, 54)
    inner = WIDTH - 2 * MARGIN
    plan = Plan()
    y = MARGIN

    def check() -> None:
        # Stop as soon as the card is past the limit, not after laying out the rest.
        if y + MARGIN > MAX_RATIO * WIDTH:
            raise CardError(
                f"card is over {MAX_RATIO * WIDTH} px tall for {WIDTH} px wide, "
                "over the 3:1 limit; split it into two cards or cut the words"
            )

    def put(
        text: str,
        font: Any,
        color: Any,
        x: int = MARGIN,
        width: int = inner,
        step: int = 78,
        bold: bool = False,
    ) -> None:
        nonlocal y
        for line in _wrap(text, font, width, 1 if bold else 0):
            plan.ops.append(("t", x, line, font, color, y, bold))
            y += step
            check()

    put(spec["title"], big, INK, step=104, bold=True)
    y += 20
    if spec.get("sub"):
        put(spec["sub"], mid, GREY)
    for n, sec in enumerate(spec["sections"], 1):
        plan.section_numbers.append(n)
        y += 50
        head_lines = _wrap(sec["head"], mid, inner - 110, 1)
        plan.ops.append(("h", n, head_lines, mid, INK, y, True))
        y += 110 + 78 * (len(head_lines) - 1)
        check()
        for bullet in sec.get("bullets", []):
            plan.ops.append(("b", MARGIN + 14, "", None, INK, y, False))
            put(bullet, body, INK, x=MARGIN + 60, width=inner - 60)
            y += 18
            check()
        for opt in sec.get("options", []):
            pick = bool(opt.get("rec"))
            head = f"{opt['key']}. {opt['label']}" + (" (my pick)" if pick else "")
            lines = _wrap(head, mid, inner - 80, 1)
            detail = _wrap(opt["detail"], body, inner - 80) if opt.get("detail") else []
            height = 30 + 80 * (len(lines) + len(detail)) + 30
            plan.ops.append(("o", y, head, height, pick, lines, detail))
            y += height + 24
            check()
    if spec.get("footer"):
        y += 40
        put(spec["footer"], mid, GREY)
    plan.height = y + MARGIN
    check()
    return plan


def _read_spec(spec_path: Path) -> Any:
    try:
        with spec_path.open("rb") as fh:
            raw = fh.read(MAX_SPEC_BYTES + 1)
    except OSError as exc:
        raise CardError(f"cannot read {_safe(spec_path)}: {exc.strerror}") from exc
    if len(raw) > MAX_SPEC_BYTES:
        raise CardError(f"{_safe(spec_path)} is over {MAX_SPEC_BYTES} bytes; cut the words")
    try:
        return json.loads(raw)
    except (ValueError, RecursionError) as exc:
        raise CardError(f"{_safe(spec_path)} is not valid JSON: {_safe(exc, 200)}") from exc


def _check_destination(spec_path: Path, out_path: Path) -> None:
    """Refuse before any work: wrong name, the spec itself, a symlink, or an existing file."""
    if out_path.suffix.lower() not in (".jpg", ".jpeg"):
        raise CardError(f"output {_safe(out_path)} must end in .jpg or .jpeg")
    if out_path.resolve() == spec_path.resolve():
        raise CardError(f"output {_safe(out_path)} is the spec file")
    if out_path.is_symlink():
        raise CardError(f"output {_safe(out_path)} is a symlink; name a new file")
    if os.path.lexists(out_path):
        raise CardError(f"output {_safe(out_path)} already exists; name a new file")


def _publish(data: bytes, out_path: Path) -> None:
    """Write via a temp file and hard-link it into place: the name appears whole or not at all.

    The destination directory is held open and every step is relative to that descriptor, so
    replacing or renaming the directory mid-write cannot redirect the link or strand the temp.
    os.link refuses an existing name, so a file created after the earlier check is still safe.
    The file is synced before the link and the folder after it, so a power cut cannot leave a
    name that points at empty bytes; a failed folder sync is reported, never passed off as done.
    """
    name = out_path.name
    try:
        dfd = os.open(out_path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    except OSError as exc:
        raise CardError(f"cannot write {_safe(out_path)}: {exc.strerror}") from exc
    tmp = f".mbcard-{secrets.token_hex(8)}.tmp"
    problem: CardError | None = None
    made = False
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=dfd)
        made = True
        try:
            view = memoryview(data)
            while view:
                view = view[os.write(fd, view) :]
            os.fsync(fd)
        finally:
            os.close(fd)
        os.link(tmp, name, src_dir_fd=dfd, dst_dir_fd=dfd, follow_symlinks=False)
    except FileExistsError as exc:
        problem = CardError(f"output {_safe(out_path)} already exists; name a new file")
        problem.__cause__ = exc
    except OSError as exc:
        problem = CardError(f"cannot write {_safe(out_path)}: {exc.strerror}")
        problem.__cause__ = exc
    leftover = ""
    if made:
        try:
            os.unlink(tmp, dir_fd=dfd)
        except OSError as exc:
            leftover = (
                f"; could not remove temp file {tmp} in {_safe(out_path.parent)}: {exc.strerror}"
            )
    unconfirmed = ""
    if made and problem is None:
        try:
            os.fsync(dfd)
        except OSError as exc:
            unconfirmed = f"; could not confirm it reached disk: {exc.strerror}"
    os.close(dfd)
    if problem is not None:
        if leftover:
            problem = CardError(f"{problem}{leftover}")
        raise problem
    if leftover or unconfirmed:
        raise CardError(f"card written to {_safe(out_path)}{unconfirmed}{leftover}")


def _encode(img: Any) -> bytes:
    size = 0
    for quality in QUALITIES:
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        data = buf.getvalue()
        size = len(data)
        if size < MAX_BYTES:
            return data
    raise CardError(f"card is still {size} bytes at the lowest quality, over 2 MB; cut the words")


def render(spec_path: Path, out_path: Path) -> tuple[int, int, int]:
    """Write a new JPG; return (width, height, bytes). A refusal or failure writes nothing."""
    _check_destination(spec_path, out_path)
    spec = _read_spec(spec_path)
    validate(spec)
    pil = _load_pillow()
    if pil is None:
        raise CardError(INSTALL_HINT)
    from PIL import Image, ImageDraw

    plan = layout(spec)
    mid, body = _font(pil, 56), _font(pil, 54)
    img = Image.new("RGB", (WIDTH, plan.height), "white")
    d = ImageDraw.Draw(img)
    for op in plan.ops:
        kind = op[0]
        if kind == "t":
            _, x, line, font, color, y, bold = op
            d.text(
                (x, y),
                line,
                font=font,
                fill=color,
                stroke_width=1 if bold else 0,
                stroke_fill=color,
            )
        elif kind == "b":
            y = op[5]
            d.ellipse((op[1], y + 20, op[1] + 16, y + 36), fill=INK)
        elif kind == "h":
            _, n, lines, font, color, y, _bold = op
            d.ellipse((MARGIN, y, MARGIN + 84, y + 84), fill=INK)
            d.text((MARGIN + 42, y + 42), str(n), font=font, fill="white", anchor="mm")
            for k, line in enumerate(lines):
                d.text(
                    (MARGIN + 110, y + 8 + 78 * k),
                    line,
                    font=font,
                    fill=color,
                    stroke_width=1,
                    stroke_fill=color,
                )
        else:
            _, y, _head, height, pick, head_lines, detail = op
            d.rounded_rectangle(
                (MARGIN, y, WIDTH - MARGIN, y + height), 24, fill=PICK if pick else PALE
            )
            yy = y + 30
            color = GREEN if pick else INK
            for line in head_lines:
                d.text(
                    (MARGIN + 40, yy), line, font=mid, fill=color, stroke_width=1, stroke_fill=color
                )
                yy += 80
            for line in detail:
                d.text((MARGIN + 40, yy), line, font=body, fill=INK)
                yy += 80
    data = _encode(img)
    _publish(data, out_path)
    return WIDTH, plan.height, len(data)
