"""Route evidence in Markdown table rows."""

from typing import Any

import pytest

from mb import release_simulation


def _score(answer: str) -> dict[str, Any]:
    simulation = next(
        item
        for item in release_simulation.simulations()
        if item.id == "conversion_video_natural_prompt_routing"
    )
    return release_simulation.score_simulation_assertions(simulation, answer)


def _states(answer: str) -> dict[str, str]:
    return {check["kind"]: check["state"] for check in _score(answer)["checks"]}


@pytest.mark.parametrize(
    "header",
    ["", "| Your request | Goes to | Why |\n|---|---|---|\n"],
)
def test_f1_explanation_cell_route_is_not_the_route(header: str) -> None:
    row = (
        '| "Make short clips from this sales video" | `/mb-organic` '
        "(sales-video repurpose) | It turns a sales video into short organic clips. "
        "`/mb-ads` also sends this request to `/mb-organic`. |"
    )
    score = _score(header + row)
    states = _states(header + row)
    assert states["route_required"] == "pass"
    assert states["route_forbidden"] == "pass"
    assert score["state"] != "fail"


@pytest.mark.parametrize(
    "header",
    ["", "| Your request | Goes to | Why |\n|---|---|---|\n"],
)
def test_f2_destination_cell_forbidden_route_still_fails(header: str) -> None:
    row = (
        '| "Make short clips from this sales video" | `/mb-ads` | '
        "`/mb-organic` handles organic clips. |"
    )
    states = _states(header + row)
    assert states["route_forbidden"] == "fail"
    assert states["route_required"] != "pass"


def test_f3_header_column_picks_destination() -> None:
    header = "| Route | Request | Notes |\n|---|---|---|\n"
    right = "| /mb-organic | Make short clips from this sales video | /mb-ads is for paid video |"
    wrong = "| /mb-ads | Make short clips from this sales video | /mb-organic is for clips |"
    assert _states(header + right)["route_required"] == "pass"
    assert _states(header + right)["route_forbidden"] == "pass"
    assert _states(header + wrong)["route_forbidden"] == "fail"


def test_f4_route_only_outside_destination_is_review() -> None:
    row = "| Make short clips | (ask first) | /mb-organic would handle it |"
    states = _states(row)
    assert states["route_required"] == "review"
    assert states["route_forbidden"] == "review"
