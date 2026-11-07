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

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

WIDTH = 1320
MARGIN = 64
MAX_RATIO = 3
MAX_BYTES = 2_000_000
QUALITIES = (88, 80, 72, 64)

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
            raise CardError(f"unknown field {prefix}{name} (allowed: {', '.join(sorted(allowed))})")


def _text(obj: dict[str, Any], name: str, label: str, required: bool = False) -> None:
    value = obj.get(name)
    if value is None and not required:
        return
    if not isinstance(value, str) or not value.strip():
        raise CardError(f"{label} must be a non-empty string")


@dataclass
class Plan:
    height: int = 0
    ops: list[tuple[Any, ...]] = field(default_factory=list)
    section_numbers: list[int] = field(default_factory=list)

    def text_lines(self) -> list[str]:
        return [op[2] for op in self.ops if op[0] in ("t", "o")]


def _font(image_font: Any, size: int) -> Any:
    return image_font.load_default(size=size)


def _wrap(text: str, font: Any, width: int, stroke: int = 0) -> list[str]:
    lines: list[str] = []
    for para in text.splitlines() or [""]:
        line = ""
        for word in para.split():
            trial = f"{line} {word}".strip()
            if line and font.getlength(trial) + 2 * stroke > width:
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

    def put(text: str, font: Any, color: Any, x: int = MARGIN, width: int = inner,
            step: int = 78, bold: bool = False) -> None:
        nonlocal y
        for line in _wrap(text, font, width, 1 if bold else 0):
            plan.ops.append(("t", x, line, font, color, y, bold))
            y += step

    put(spec["title"], big, INK, step=104, bold=True)
    y += 20
    if spec.get("sub"):
        put(spec["sub"], mid, GREY)
    for n, sec in enumerate(spec["sections"], 1):
        plan.section_numbers.append(n)
        y += 50
        plan.ops.append(("h", n, sec["head"], mid, INK, y, True))
        y += 110
        for bullet in sec.get("bullets", []):
            plan.ops.append(("b", MARGIN + 14, "", None, INK, y, False))
            put(bullet, body, INK, x=MARGIN + 60, width=inner - 60)
            y += 18
        for opt in sec.get("options", []):
            pick = bool(opt.get("rec"))
            head = f"{opt['key']}. {opt['label']}" + (" (my pick)" if pick else "")
            head_lines = _wrap(head, mid, inner - 80, 1)
            detail = _wrap(opt["detail"], body, inner - 80) if opt.get("detail") else []
            height = 30 + 80 * (len(head_lines) + len(detail)) + 30
            plan.ops.append(("o", y, head, height, pick, head_lines, detail))
            y += height + 24
    if spec.get("footer"):
        y += 40
        put(spec["footer"], mid, GREY)
    plan.height = y + MARGIN
    if plan.height > MAX_RATIO * WIDTH:
        raise CardError(
            f"card is {plan.height} px tall for {WIDTH} px wide, over the 3:1 limit; "
            "split it into two cards or cut the words"
        )
    return plan


def render(spec_path: Path, out_path: Path) -> tuple[int, int, int]:
    """Write the JPG; return (width, height, bytes). Nothing is written on refusal."""
    try:
        spec = json.loads(spec_path.read_text())
    except OSError as exc:
        raise CardError(f"cannot read {spec_path}: {exc.strerror}") from exc
    except ValueError as exc:
        raise CardError(f"{spec_path} is not valid JSON: {exc}") from exc
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
            d.text((x, y), line, font=font, fill=color, stroke_width=1 if bold else 0,
                   stroke_fill=color)
        elif kind == "b":
            y = op[5]
            d.ellipse((op[1], y + 20, op[1] + 16, y + 36), fill=INK)
        elif kind == "h":
            _, n, head, font, color, y, _bold = op
            d.ellipse((MARGIN, y, MARGIN + 84, y + 84), fill=INK)
            d.text((MARGIN + 42, y + 42), str(n), font=font, fill="white", anchor="mm")
            d.text((MARGIN + 110, y + 8), head, font=font, fill=color, stroke_width=1,
                   stroke_fill=color)
        else:
            _, y, _head, height, pick, head_lines, detail = op
            d.rounded_rectangle((MARGIN, y, WIDTH - MARGIN, y + height), 24,
                                fill=PICK if pick else PALE)
            yy = y + 30
            color = GREEN if pick else INK
            for line in head_lines:
                d.text((MARGIN + 40, yy), line, font=mid, fill=color, stroke_width=1,
                       stroke_fill=color)
                yy += 80
            for line in detail:
                d.text((MARGIN + 40, yy), line, font=body, fill=INK)
                yy += 80
    for quality in QUALITIES:
        img.save(out_path, quality=quality)
        size = out_path.stat().st_size
        if size < MAX_BYTES:
            return WIDTH, plan.height, size
    out_path.unlink()
    raise CardError(f"card is still {size} bytes at the lowest quality, over 2 MB; cut the words")
