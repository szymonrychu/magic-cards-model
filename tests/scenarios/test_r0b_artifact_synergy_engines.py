"""Scenario: artifact-synergy engines - Simulacrum Synthesizer and Repurposing
Bay, played through the engine.

Simulacrum Synthesizer: "When this artifact enters, scry 2." and "Whenever
another artifact you control with mana value 3 or greater enters, create a
0/0 colorless Construct artifact creature token with 'This token gets +1/+1
for each artifact you control.'" The Construct survives because it counts
itself.

Repurposing Bay: "{2}, {T}, Sacrifice another artifact: Search your library
for an artifact card with mana value equal to 1 plus the sacrificed
artifact's mana value, put that card onto the battlefield, then shuffle.
Activate only as a sorcery."

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 701.22a** - scry N: look at the top N, put any number on the bottom
  and the rest on top.
- **CR 603.6a** - an enters ability triggers for each permanent entering.
- **CR 613.4c** - layer 7c: effects that modify power and toughness.
- **CR 701.23a** - to search, look at all cards in the zone and find a card
  matching the description.
- **CR 113.7a** - an ability that refers to information about an object no
  longer in its zone uses its last known information.
- **CR 701.21a** - to sacrifice, its controller moves it to its owner's
  graveyard.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

SYNTH = "Simulacrum Synthesizer"
BAY = "Repurposing Bay"


def _resolve_everything(scenario):
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _chars(scenario, permanent):
    return scenario.game.computed_board().of(permanent)


def _constructs(scenario):
    return [p for p in scenario.game.battlefield if p.token and p.name == "Construct Token"]


def _board(alice=(), bob=(), *, hand=(), library=None, bob_hand=()):
    return (
        Scenario()
        .player(
            "alice",
            battlefield=list(alice),
            hand=list(hand),
            library=list(library) if library is not None else ["Island"] * 5,
        )
        .player("bob", battlefield=list(bob), hand=list(bob_hand), library=["Island"] * 5)
        .build()
    )


# -- Simulacrum Synthesizer ---------------------------------------------------


def test_synthesizer_entering_scries_two():
    """CR 701.22a: both looked-at cards may go to the bottom."""
    scenario = _board(hand=[SYNTH], library=["Plains", "Swamp", "Forest", "Island"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    plains, swamp = scenario.top_of_library(2, "alice")
    scenario.scry_bottoming(plains, swamp, username="alice")

    scenario.put_onto_battlefield(SYNTH, "alice")
    _resolve_everything(scenario)

    library = [c.name for c in scenario.player("alice").library]
    assert library[:2] == ["Forest", "Island"]
    assert set(library[2:]) == {"Plains", "Swamp"}


def test_synthesizer_makes_a_construct_for_a_mana_value_three_artifact():
    """Cogwork Assembler is mana value exactly 3: "3 or greater" includes it.
    The Construct counts the Synthesizer, the Assembler and itself."""
    scenario = _board([SYNTH], hand=["Cogwork Assembler"])
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.put_onto_battlefield("Cogwork Assembler", "alice")
    _resolve_everything(scenario)

    (construct,) = _constructs(scenario)
    chars = _chars(scenario, construct)
    assert construct.zone is Zone.BATTLEFIELD, "0/0 printed, but it counts itself"
    assert (chars.power, chars.toughness) == (3, 3)


def test_a_construct_grows_and_shrinks_with_the_artifact_count():
    scenario = _board([SYNTH, "Mind Stone"], hand=["Wurmcoil Engine"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.put_onto_battlefield("Wurmcoil Engine", "alice")
    _resolve_everything(scenario)
    (construct,) = _constructs(scenario)
    assert _chars(scenario, construct).power == 4  # Synth, Stone, Wurmcoil, itself

    scenario.game.destroy(scenario.find("Mind Stone", Zone.BATTLEFIELD, "alice"))
    _resolve_everything(scenario)

    assert (_chars(scenario, construct).power, _chars(scenario, construct).toughness) == (3, 3)


def test_synthesizer_ignores_an_artifact_below_mana_value_three():
    scenario = _board([SYNTH], hand=["Mind Stone"])
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.put_onto_battlefield("Mind Stone", "alice")
    scenario.game.put_triggers_on_stack()

    assert scenario.game.stack == []


def test_synthesizer_ignores_an_opponents_artifact():
    scenario = _board([SYNTH], bob_hand=["Wurmcoil Engine"])
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.put_onto_battlefield("Wurmcoil Engine", "bob")
    _resolve_everything(scenario)

    assert _constructs(scenario) == []


def test_synthesizer_does_not_trigger_on_its_own_entry():
    """ "another artifact": the Synthesizer (mana value 3) is not another."""
    scenario = _board(hand=[SYNTH], library=["Plains", "Swamp", "Forest"])
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.put_onto_battlefield(SYNTH, "alice")
    _resolve_everything(scenario)

    assert _constructs(scenario) == []


def test_a_nonartifact_entering_makes_no_construct():
    scenario = _board([SYNTH], hand=["Hill Giant"])
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.put_onto_battlefield("Hill Giant", "alice")
    _resolve_everything(scenario)

    assert _constructs(scenario) == []


# -- Repurposing Bay ----------------------------------------------------------

LIBRARY = ["Island", "Cogwork Assembler", "Wurmcoil Engine", "Sol Ring", "Bonesplitter"]


def _bay_board(*others, library=LIBRARY):
    scenario = _board([BAY, "Mountain", "Mountain", *others], library=library)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario, scenario.find(BAY, Zone.BATTLEFIELD, "alice")


def _activate_bay(scenario, bay, sacrificed):
    return scenario.activate(
        bay, *scenario.untapped_sources("Mountain", "Mountain"), sacrificing=[sacrificed]
    )


def test_bay_sacrificing_mana_value_two_fetches_a_mana_value_three_artifact():
    scenario, bay = _bay_board("Mind Stone")
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "alice")
    assembler = scenario.find("Cogwork Assembler", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(assembler, username="alice")

    _activate_bay(scenario, bay, stone)
    _resolve_everything(scenario)

    assert stone.zone is Zone.GRAVEYARD
    assert scenario.find("Cogwork Assembler", Zone.BATTLEFIELD, "alice").zone is Zone.BATTLEFIELD
    assert bay.tapped
    assert len(scenario.player("alice").library) == 4


def test_bay_offers_only_the_exact_mana_value():
    """Mana value 1 + 2 = 3 exactly: Sol Ring (1) and Wurmcoil Engine (6)
    are no answer."""
    scenario, bay = _bay_board("Mind Stone")
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "alice")
    ring = scenario.find("Sol Ring", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(ring, username="alice")

    _activate_bay(scenario, bay, stone)
    with pytest.raises(ValueError, match="not offered"):
        _resolve_everything(scenario)


def test_bay_sacrificing_mana_value_zero_fetches_mana_value_one():
    scenario, bay = _bay_board("Ornithopter")
    thopter = scenario.find("Ornithopter", Zone.BATTLEFIELD, "alice")
    splitter = scenario.find("Bonesplitter", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(splitter, username="alice")

    _activate_bay(scenario, bay, thopter)
    _resolve_everything(scenario)

    assert scenario.find("Bonesplitter", Zone.BATTLEFIELD, "alice").zone is Zone.BATTLEFIELD


def test_bay_with_no_matching_card_finds_nothing():
    """CR 701.23a: Cogwork Assembler (3) sacrificed asks for mana value 4;
    the library has none."""
    scenario, bay = _bay_board("Cogwork Assembler", library=["Island", "Sol Ring", "Mind Stone"])
    assembler = scenario.find("Cogwork Assembler", Zone.BATTLEFIELD, "alice")

    _activate_bay(scenario, bay, assembler)
    _resolve_everything(scenario)

    assert [p.name for p in scenario.game.battlefield if p.name in ("Sol Ring", "Mind Stone")] == []
    assert len(scenario.player("alice").library) == 3


def test_bay_cannot_sacrifice_itself():
    """ "Sacrifice another artifact"."""
    scenario, bay = _bay_board()

    with pytest.raises(ValueError, match="excludes the ability's own source"):
        _activate_bay(scenario, bay, bay)
    assert bay.zone is Zone.BATTLEFIELD


def test_bay_cannot_sacrifice_a_nonartifact():
    scenario, bay = _bay_board("Grizzly Bears")
    bears = scenario.creature("Grizzly Bears", "alice")

    with pytest.raises(ValueError, match="not an artifact"):
        _activate_bay(scenario, bay, bears)
    assert bears.zone is Zone.BATTLEFIELD


def test_bay_is_sorcery_speed():
    scenario = _board([BAY, "Mountain", "Mountain", "Mind Stone"], library=LIBRARY)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bay = scenario.find(BAY, Zone.BATTLEFIELD, "alice")

    assert "only be activated as a sorcery" in (scenario.why_cannot_activate(bay) or "")


def test_bay_uses_the_sacrificed_tokens_last_known_mana_value():
    """CR 113.7a: a Construct token (mana value 0) is gone by resolution;
    its last known mana value 0 asks for a mana value 1 artifact."""
    scenario = _board(
        [BAY, SYNTH, "Mountain", "Mountain"], hand=["Wurmcoil Engine"], library=LIBRARY
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bay = scenario.find(BAY, Zone.BATTLEFIELD, "alice")
    scenario.put_onto_battlefield("Wurmcoil Engine", "alice")
    _resolve_everything(scenario)
    (construct,) = _constructs(scenario)
    splitter = scenario.find("Bonesplitter", Zone.LIBRARY, "alice")
    scenario.will_choose_cards(splitter, username="alice")

    _activate_bay(scenario, bay, construct)
    _resolve_everything(scenario)

    assert scenario.find("Bonesplitter", Zone.BATTLEFIELD, "alice").zone is Zone.BATTLEFIELD


# -- The mana-value qualifier on an enters trigger, on a second printing ----
#
# Doc Ock's Tentacles (Modern/Pioneer/Standard legal, in no
# `magic-cards-model-api/decks/*.txt`): "Whenever a creature you control with
# mana value 5 or greater enters, you may attach this Equipment to it." The
# same CR 202.3 qualifier the Synthesizer prints, on a creature subject.


def test_tentacles_never_trigger_for_a_creature_below_mana_value_five():
    scenario = _board(["Doc Ock's Tentacles"], hand=["Hill Giant"])
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.put_onto_battlefield("Hill Giant", "alice")
    scenario.game.put_triggers_on_stack()

    assert scenario.game.stack == []


def test_tentacles_trigger_for_a_mana_value_six_creature():
    scenario = _board(["Doc Ock's Tentacles"], hand=["Wurmcoil Engine"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    tentacles = scenario.find("Doc Ock's Tentacles", Zone.BATTLEFIELD, "alice")
    scenario.will_take_the_may(True, username="alice")

    wurmcoil = scenario.put_onto_battlefield("Wurmcoil Engine", "alice")
    _resolve_everything(scenario)

    assert tentacles.attached_to == wurmcoil.id
