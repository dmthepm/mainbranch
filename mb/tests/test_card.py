"""`mb card render`: JSON spec in, JPG out, house rules enforced by the tool."""

from __future__ import annotations

import errno
import json
import os
import stat
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from mb import card
from mb.cli import app

needs_pillow = pytest.mark.skipif(
    card._load_pillow() is None, reason="mb card needs the optional 'cards' extra"
)

runner = CliRunner()

SPEC = {
    "title": "Which plan do we run next quarter?",
    "sub": "Invented example for tests",
    "sections": [
        {
            "head": "What we know",
            "bullets": ["Sales are flat across both stores.", "Ad spend is capped."],
        },
        {
            "head": "Pick one",
            "options": [
                {"key": "A", "label": "Hold spend", "detail": "Keep the current cap."},
                {"key": "B", "label": "Raise spend", "detail": "Add ten percent.", "rec": True},
            ],
        },
    ],
    "footer": "Reply with a letter.",
}


def _write(tmp_path: Path, spec: object) -> Path:
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(spec))
    return path


def _render(tmp_path: Path, spec: object):
    out = tmp_path / "card.jpg"
    result = runner.invoke(app, ["card", "render", str(_write(tmp_path, spec)), str(out)])
    return result, out


@needs_pillow
def test_render_makes_a_1320_wide_jpg_under_2mb(tmp_path):
    from PIL import Image  # noqa: PLC0415

    result, out = _render(tmp_path, SPEC)
    assert result.exit_code == 0, result.output
    with Image.open(out) as img:
        assert img.format == "JPEG"
        assert img.width == 1320
        assert img.height <= 3 * img.width
    assert out.stat().st_size < 2_000_000


@needs_pillow
def test_recommended_option_is_marked_in_the_layout():
    plan = card.layout(SPEC)
    picks = [line for line in plan.text_lines() if "my pick" in line]
    assert picks == ["B. Raise spend (my pick)"]
    assert any(line.startswith("A. Hold spend") for line in plan.text_lines())


@needs_pillow
def test_sections_are_numbered():
    plan = card.layout(SPEC)
    assert plan.section_numbers == [1, 2]


@needs_pillow
def test_too_tall_card_is_refused_and_not_written(tmp_path):
    spec = {
        "title": "Long",
        "sections": [{"head": f"Part {n}", "bullets": ["word " * 60] * 4} for n in range(8)],
    }
    result, out = _render(tmp_path, spec)
    assert result.exit_code == 2
    assert "3:1" in result.output
    assert "split" in result.output
    assert not out.exists()


@pytest.mark.parametrize(
    "spec, named",
    [
        ({"sections": []}, "title"),
        ({"title": "T"}, "sections"),
        ({"title": "T", "sections": [{"bullets": ["x"]}]}, "sections[0].head"),
        ({"title": "T", "sections": [{"head": "H", "bullet": ["x"]}]}, "bullet"),
        (
            {"title": "T", "sections": [{"head": "H", "options": [{"label": "x"}]}]},
            "sections[0].options[0].key",
        ),
        ({"title": "T", "sections": [{"head": "H"}], "colour": "red"}, "colour"),
        ({"title": 5, "sections": [{"head": "H"}]}, "title"),
    ],
)
def test_bad_spec_is_refused_by_name(tmp_path, spec, named):
    result, out = _render(tmp_path, spec)
    assert result.exit_code == 2
    assert named in result.output
    assert not out.exists()


def test_spec_that_is_not_json_is_refused(tmp_path):
    spec = tmp_path / "spec.json"
    spec.write_text("{not json")
    result = runner.invoke(app, ["card", "render", str(spec), str(tmp_path / "c.jpg")])
    assert result.exit_code == 2
    assert "not valid JSON" in result.output


def test_missing_pillow_is_a_clear_refusal(tmp_path, monkeypatch):
    monkeypatch.setattr(card, "_load_pillow", lambda: None)
    result, out = _render(tmp_path, SPEC)
    assert result.exit_code == 2
    assert "pip install 'mainbranch[cards]'" in result.output
    assert not out.exists()


def _fits(plan: card.Plan) -> None:
    """Every drawn line, measured with the real font, sits inside the card's margins."""
    pil = card._load_pillow()
    widths = {84: card._font(pil, 84), 56: card._font(pil, 56), 54: card._font(pil, 54)}
    inner = card.WIDTH - 2 * card.MARGIN
    for op in plan.ops:
        if op[0] == "t":
            assert op[3].getlength(op[2]) <= card.WIDTH - card.MARGIN - op[1], op[2]
        elif op[0] == "h":
            assert all(op[3].getlength(line) <= inner - 110 for line in op[2])
        elif op[0] == "o":
            assert all(widths[56].getlength(line) <= inner - 80 for line in op[5])
            assert all(widths[54].getlength(line) <= inner - 80 for line in op[6])


@needs_pillow
def test_long_unbroken_text_is_wrapped_never_clipped():
    wide = "W" * 100
    spec = {
        "title": wide,
        "sub": wide,
        "sections": [
            {
                "head": wide + " heading",
                "bullets": [wide],
                "options": [{"key": "A", "label": wide, "detail": wide}],
            }
        ],
        "footer": wide,
    }
    plan = card.layout(spec)
    _fits(plan)
    heads = [op for op in plan.ops if op[0] == "h"]
    assert len(heads[0][2]) > 1


@needs_pillow
def test_wrapped_section_heading_pushes_following_content_down():
    one = card.layout({"title": "T", "sections": [{"head": "Short", "bullets": ["x"]}]})
    two = card.layout({"title": "T", "sections": [{"head": "W" * 100, "bullets": ["x"]}]})
    assert two.height > one.height


@needs_pillow
def test_layout_stops_once_over_the_height_budget(monkeypatch):
    calls: list[int] = []
    real = card._wrap

    def counting(*args: Any, **kwargs: Any) -> list[str]:
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(card, "_wrap", counting)
    spec = {
        "title": "T",
        "sections": [{"head": "H", "bullets": ["word " * 100] * 12} for _ in range(12)],
    }
    with pytest.raises(card.CardError, match="3:1"):
        card.layout(spec)
    assert len(calls) < 12 * 13  # nowhere near all 144 bullets plus heads


@pytest.mark.parametrize(
    "spec, named",
    [
        ({"title": "T" * 1001, "sections": [{"head": "H"}]}, "title"),
        ({"title": "T", "sections": [{"head": "H"}] * 13}, "sections"),
        ({"title": "T", "sections": [{"head": "H", "bullets": ["x"] * 13}]}, "bullets"),
        (
            {
                "title": "T",
                "sections": [{"head": "H", "options": [{"key": "A", "label": "x"}] * 13}],
            },
            "options",
        ),
    ],
)
def test_oversized_fields_are_refused(tmp_path, spec, named):
    result, out = _render(tmp_path, spec)
    assert result.exit_code == 2
    assert named in result.output
    assert not out.exists()


def test_oversized_spec_file_is_refused_unparsed(tmp_path):
    spec = tmp_path / "spec.json"
    spec.write_text(" " * (card.MAX_SPEC_BYTES + 1))
    result = runner.invoke(app, ["card", "render", str(spec), str(tmp_path / "c.jpg")])
    assert result.exit_code == 2
    assert "bytes" in result.output


def test_deeply_nested_spec_is_a_refusal_not_a_crash(tmp_path):
    spec = tmp_path / "spec.json"
    spec.write_text("[" * 90_000)
    result = runner.invoke(app, ["card", "render", str(spec), str(tmp_path / "c.jpg")])
    assert result.exit_code == 2


def test_control_characters_in_an_unknown_field_name_are_escaped(tmp_path):
    result, _ = _render(tmp_path, {"title": "T", "sections": [{"head": "H"}], "\x1b[2J": 1})
    assert result.exit_code == 2
    assert "\x1b" not in result.output
    assert "\\x1b[2J" in result.output


@pytest.mark.parametrize("bad", ["a\x00b", "a\x1b[2Jb", "tab\there"])
def test_control_characters_in_text_are_refused(tmp_path, bad):
    for spec in (
        {"title": bad, "sections": [{"head": "H"}]},
        {"title": "T", "sections": [{"head": "H", "bullets": [bad]}]},
    ):
        result, out = _render(tmp_path, spec)
        assert result.exit_code == 2
        assert "control character" in result.output
        assert "\x1b" not in result.output
        assert not out.exists()


def test_existing_destination_is_refused_and_untouched(tmp_path):
    out = tmp_path / "card.jpg"
    out.write_bytes(b"keep me")
    result, _ = _render(tmp_path, SPEC)
    assert result.exit_code == 2
    assert "already exists" in result.output
    assert out.read_bytes() == b"keep me"


def test_symlink_destination_is_refused_and_target_untouched(tmp_path):
    target = tmp_path / "other.jpg"
    target.write_bytes(b"keep me")
    (tmp_path / "card.jpg").symlink_to(target)
    result, _ = _render(tmp_path, SPEC)
    assert result.exit_code == 2
    assert "symlink" in result.output
    assert target.read_bytes() == b"keep me"


def test_dangling_symlink_destination_is_refused(tmp_path):
    (tmp_path / "card.jpg").symlink_to(tmp_path / "nowhere.jpg")
    result, _ = _render(tmp_path, SPEC)
    assert result.exit_code == 2
    assert not (tmp_path / "nowhere.jpg").exists()


def test_output_equal_to_the_spec_is_refused(tmp_path):
    spec = _write(tmp_path, SPEC)
    before = spec.read_bytes()
    jpg = tmp_path / "spec.jpg"
    spec.rename(jpg)
    result = runner.invoke(app, ["card", "render", str(jpg), str(jpg)])
    assert result.exit_code == 2
    assert "spec file" in result.output
    assert jpg.read_bytes() == before


@pytest.mark.parametrize("name", ["card.png", "card", "card.txt"])
def test_output_must_be_named_jpg(tmp_path, name):
    out = tmp_path / name
    result = runner.invoke(app, ["card", "render", str(_write(tmp_path, SPEC)), str(out)])
    assert result.exit_code == 2
    assert ".jpg" in result.output
    assert not out.exists()


@needs_pillow
def test_uppercase_jpeg_name_is_encoded_as_jpeg(tmp_path):
    from PIL import Image  # noqa: PLC0415

    out = tmp_path / "CARD.JPEG"
    result = runner.invoke(app, ["card", "render", str(_write(tmp_path, SPEC)), str(out)])
    assert result.exit_code == 0, result.output
    with Image.open(out) as img:
        assert img.format == "JPEG"


@needs_pillow
def test_size_retry_steps_down_quality_until_it_fits(tmp_path, monkeypatch):
    def size_at(quality: int) -> int:
        monkeypatch.setattr(card, "QUALITIES", (quality,))
        out = tmp_path / f"q{quality}.jpg"
        return card.render(_write(tmp_path, SPEC), out)[2]

    high, low = size_at(88), size_at(10)
    assert low < high
    monkeypatch.setattr(card, "QUALITIES", (88, 10))
    monkeypatch.setattr(card, "MAX_BYTES", (high + low) // 2)
    result, out = _render(tmp_path, SPEC)
    assert result.exit_code == 0, result.output
    assert out.stat().st_size == low


@needs_pillow
def test_still_too_big_at_lowest_quality_is_refused_and_not_written(tmp_path, monkeypatch):
    monkeypatch.setattr(card, "MAX_BYTES", 1000)
    result, out = _render(tmp_path, SPEC)
    assert result.exit_code == 2
    assert "2 MB" in result.output
    assert not out.exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["spec.json"]


@needs_pillow
def test_write_failure_is_a_refusal_and_leaves_no_file(tmp_path, monkeypatch):
    def full_disk(*_args, **_kwargs):
        raise OSError(errno.ENOSPC, os.strerror(errno.ENOSPC))

    monkeypatch.setattr(os, "link", full_disk)
    result, out = _render(tmp_path, SPEC)
    assert result.exit_code == 2
    assert "cannot write" in result.output
    assert not out.exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["spec.json"]


@needs_pillow
def test_temp_write_failure_is_a_refusal_and_leaves_no_file(tmp_path, monkeypatch):
    def full_disk(*_args, **_kwargs):
        raise OSError(errno.ENOSPC, os.strerror(errno.ENOSPC))

    monkeypatch.setattr(os, "write", full_disk)
    result, out = _render(tmp_path, SPEC)
    assert result.exit_code == 2
    assert "cannot write" in result.output
    assert not out.exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["spec.json"]


@needs_pillow
def test_unremovable_temp_file_is_named_not_swallowed(tmp_path, monkeypatch):
    def stuck(*_args, **_kwargs):
        raise OSError(errno.EBUSY, os.strerror(errno.EBUSY))

    monkeypatch.setattr(os, "unlink", stuck)
    result, out = _render(tmp_path, SPEC)
    assert result.exit_code == 2
    assert "could not remove temp file .mbcard-" in result.output
    leftovers = [p.name for p in tmp_path.iterdir() if p.name.startswith(".mbcard-")]
    assert len(leftovers) == 1
    assert leftovers[0] in result.output


@needs_pillow
def test_link_goes_to_the_held_directory_even_if_the_path_is_swapped(tmp_path, monkeypatch):
    real_link = os.link

    def swap_then_link(*args, **kwargs):
        moved = tmp_path.parent / (tmp_path.name + "-moved")
        tmp_path.rename(moved)
        tmp_path.mkdir()
        (tmp_path / "spec.json").write_text("{}")
        return real_link(*args, **kwargs)

    monkeypatch.setattr(os, "link", swap_then_link)
    spec = _write(tmp_path, SPEC)
    out = tmp_path / "card.jpg"
    card._publish(b"jpegbytes", out)
    moved = tmp_path.parent / (tmp_path.name + "-moved")
    assert (moved / "card.jpg").read_bytes() == b"jpegbytes"
    assert sorted(p.name for p in moved.iterdir()) == ["card.jpg", spec.name]
    assert not (tmp_path / "card.jpg").exists()


@needs_pillow
def test_missing_output_directory_is_a_refusal(tmp_path):
    out = tmp_path / "nope" / "card.jpg"
    result = runner.invoke(app, ["card", "render", str(_write(tmp_path, SPEC)), str(out)])
    assert result.exit_code == 2
    assert "cannot write" in result.output


def _record_syncs(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str]]:
    """Record each fsync and link in order, as ('file'|'dir', ...) and ('link',)."""
    events: list[tuple[str]] = []
    real_fsync, real_link = os.fsync, os.link

    def fsync(fd):
        events.append(("dir" if stat.S_ISDIR(os.fstat(fd).st_mode) else "file",))
        return real_fsync(fd)

    def link(*args, **kwargs):
        events.append(("link",))
        return real_link(*args, **kwargs)

    monkeypatch.setattr(os, "fsync", fsync)
    monkeypatch.setattr(os, "link", link)
    return events


def test_publish_syncs_the_file_before_the_link_and_the_folder_after(tmp_path, monkeypatch):
    events = _record_syncs(monkeypatch)
    card._publish(b"jpegbytes", tmp_path / "card.jpg")
    assert events == [("file",), ("link",), ("dir",)]
    assert (tmp_path / "card.jpg").read_bytes() == b"jpegbytes"


def test_publish_does_not_link_when_the_file_sync_fails(tmp_path, monkeypatch):
    def fail(fd):
        raise OSError(errno.EIO, "Input/output error")

    monkeypatch.setattr(os, "fsync", fail)
    with pytest.raises(card.CardError, match="cannot write"):
        card._publish(b"jpegbytes", tmp_path / "card.jpg")
    assert list(tmp_path.iterdir()) == []


def test_publish_reports_a_failed_folder_sync(tmp_path, monkeypatch):
    real_fsync = os.fsync

    def fsync(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError(errno.EIO, "Input/output error")
        return real_fsync(fd)

    monkeypatch.setattr(os, "fsync", fsync)
    with pytest.raises(card.CardError, match="could not confirm it reached disk"):
        card._publish(b"jpegbytes", tmp_path / "card.jpg")
    assert (tmp_path / "card.jpg").read_bytes() == b"jpegbytes"


@pytest.mark.parametrize("code", [errno.EINVAL, errno.ENOTSUP, errno.EOPNOTSUPP])
def test_publish_carries_on_past_a_disk_that_cannot_sync_a_folder(tmp_path, monkeypatch, code):
    real_fsync = os.fsync

    def fsync(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError(code, "Operation not supported")
        return real_fsync(fd)

    monkeypatch.setattr(os, "fsync", fsync)
    card._publish(b"jpegbytes", tmp_path / "card.jpg")
    assert (tmp_path / "card.jpg").read_bytes() == b"jpegbytes"
