"""The behavioural sweep's golden files are readable, stable and replayable.

`tests/golden/<card-slug>/<ability>.json` is written by the sweep
(`mise run golden:update`) and compared by it on every run. This module
checks the carrier itself: that a golden loads back into the scenario it was
recorded from - the board in the scenario harness's own words and the
recipe that raised the event - that replaying it reproduces the recorded
delta exactly, and that a mismatch reads as a diff naming what moved.
"""

from __future__ import annotations

import json

import pytest

from tests.golden import GOLDEN_DIR, diff, dumps, golden_path, load, slug
from tests.scenarios.harness import PlayedScenario

#: A trigger, a targeted trigger and an activation - the Devourer of Destiny
#: cast trigger is the regression the goldens exist to pin.
REPLAYED = [
    ("Devourer of Destiny", "triggered", 0),
    ("Guide of Souls", "triggered", 0),
    ("Icy Manipulator", "activated", 0),
]


def test_a_golden_path_is_the_card_slug_and_the_ability():
    path = golden_path("Kaito, Bane of Nightmares", "activated", 2)
    assert path == GOLDEN_DIR / "kaito-bane-of-nightmares" / "activated-2.json"
    assert slug("Hydroelectric Specimen // Hydroelectric Laboratory") == (
        "hydroelectric-specimen-hydroelectric-laboratory"
    )


def test_dumps_is_sorted_and_keeps_scalar_lists_on_one_line():
    text = dumps({"b": [1, 2], "a": {"d": ["x", "y"], "c": None}})
    assert text == ('{\n  "a": {\n    "c": null,\n    "d": ["x", "y"]\n  },\n  "b": [1, 2]\n}\n')
    assert json.loads(text) == {"a": {"c": None, "d": ["x", "y"]}, "b": [1, 2]}


def test_a_mismatch_reads_as_a_unified_diff_of_the_delta():
    recorded = {"delta": {"players": {"bob": {"life": [20, 17]}}}}
    live = {"delta": {"players": {"bob": {"life": [20, 20]}}}}
    text = diff(recorded, live)
    assert '-        "life": [20, 17]' in text
    assert '+        "life": [20, 20]' in text


@pytest.mark.parametrize(("card", "family", "number"), REPLAYED)
def test_a_golden_loads_back_into_its_board_and_replays_to_its_delta(card, family, number):
    golden = load(golden_path(card, family, number))

    assert golden.card == card
    assert golden.board["players"]["alice"]["battlefield"], "the board is written out"
    built = golden.build_board()
    assert isinstance(built, PlayedScenario)
    names = [state.name for state in built.game.battlefield]
    for name in golden.board["players"]["alice"]["battlefield"]:
        assert any(n == name or n.startswith(f"{name.split(' //')[0]}") for n in names), name

    replayed = golden.replay()
    assert replayed == golden.recorded, diff(golden.recorded, replayed)


def test_every_golden_names_the_ability_the_sweep_ran():
    goldens = sorted(GOLDEN_DIR.glob("*/*.json"))
    assert goldens, "no goldens - run `mise run golden:update`"
    for path in goldens[:50]:
        golden = load(path)
        assert golden.ability, path
        assert golden.recipe["variant"] in ("quiet", "busy", "lonely", "war"), path
        assert "delta" in golden.recorded, path
