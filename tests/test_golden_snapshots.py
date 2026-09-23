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

from tests.golden import GOLDEN_DIR, _counters, diff, dumps, golden_path, load, slug
from tests.scenarios.harness import PlayedScenario

#: A targeted cast trigger, an enters trigger and an activation - the
#: Devourer of Destiny cast trigger is the regression the goldens exist to pin.
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


@pytest.mark.parametrize(
    ("card", "family", "number"),
    [("Arclight Phoenix", "triggered", 0), ("Baxter Building", "activated", 0)],
)
def test_a_busy_golden_builds_the_board_after_its_eventful_turn(card, family, number):
    golden = load(golden_path(card, family, number))
    assert golden.board["busy_turn"], "the golden records a busy turn"

    built = golden.build_board()

    cast = built.game.spells_cast_this_turn.get("alice", [])
    assert len(cast) >= 3, "the busy turn's spells were cast before the action"


@pytest.mark.parametrize(
    ("card", "family", "number"),
    [("Lagomos, Hand of Hatred", "activated", 0), ("Minas Tirith", "activated", 0)],
)
def test_a_war_golden_builds_the_board_after_its_bloody_turn(card, family, number):
    from magic_cards_model.machines import Step

    golden = load(golden_path(card, family, number))
    assert golden.board["war_turn"], "the golden records a war turn"

    built = golden.build_board()

    assert built.step is Step.POSTCOMBAT_MAIN, "the war turn ends in the postcombat main"


def _on_battlefield(built: PlayedScenario, name: str):
    return next(state for state in built.game.battlefield if state.name == name)


def test_a_golden_builds_its_source_primed_for_an_intervening_if():
    """Lightning Coils' upkeep trigger checks "if this artifact has five or
    more charge counters on it" (CR 603.4): the built board carries them."""
    built = load(golden_path("Lightning Coils", "triggered", 1)).build_board()

    assert _counters(_on_battlefield(built, "Lightning Coils").counters).get("charge", 0) >= 5


def test_a_golden_builds_its_class_at_the_level_the_ability_unlocks_at():
    """Wizard Class' "whenever you draw a card" is a level 3 ability (CR 716.2a)."""
    built = load(golden_path("Wizard Class", "triggered", 1)).build_board()

    assert _on_battlefield(built, "Wizard Class").class_level == 3


def test_a_golden_builds_the_spell_its_ability_targets_on_the_stack():
    """Spellskite's "change the target of target spell or ability" needs a
    spell to aim at (CR 115.1): the built board has it on the stack, and the
    activation itself has not happened yet."""
    built = load(golden_path("Spellskite", "activated", 0)).build_board()

    assert built.game.stack, "the target spell was cast before the activation"
    assert all(getattr(item, "source_name", None) != "Spellskite" for item in built.game.stack), (
        "the board is the one the activation is made on, not after it"
    )
