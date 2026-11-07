"""`mb card render`: JSON spec in, JPG out, house rules enforced by the tool."""

from __future__ import annotations

import json
from pathlib import Path

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
