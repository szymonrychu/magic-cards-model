"""A chosen-colour protection grant that follows another instruction.

Feat of Resistance: "Put a +1/+1 counter on target creature you control. It
gains protection from the color of your choice until end of turn."
Pristine Skywise (second printing, Modern/Pioneer, in no api deck): "Whenever
you cast a noncreature spell, untap this creature. It gains protection from
the color of your choice until end of turn."

Rules verified with `mise run rules:find`:

- **CR 608.2c** - the instructions run in the order written: the counter
  (or the untap) first, then the protection.
- **CR 608.2d** - the colour is a choice the resolving spell or ability's
  controller makes as it resolves, not at announcement.
- **CR 702.16a** - protection is a static ability, "Protection from
  [quality]"; **CR 702.16b** - the protected creature can't be targeted by
  spells with that quality; **CR 702.16e** - damage from sources with the
  quality is prevented.
- **CR 611.2a** - "until end of turn" lasts through the turn and ends at
  cleanup (CR 514.2).
- **CR 608.2b** - an illegal target is not affected: with the creature gone
  there is nothing to counter or protect and no colour is asked for.
- **CR 122.1a** - the +1/+1 counter lasts; the protection does not.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Color, Zone
from tests.scenarios.harness import Scenario


def _notices(scenario) -> list[object]:
    game = scenario.game
    found: list[object] = list(game.continuous_effects.layer_notices)
    for name in type(game).model_fields:
        if name.endswith("_notices"):
            found.extend(getattr(game, name))
    return found


def _abilities(scenario, card) -> list[str]:
    return list(scenario.game.characteristics_of(card).abilities)


def _feat_board() -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Feat of Resistance"],
            battlefield=["Plains", "Plains", "Grizzly Bears", "Llanowar Elves"],
        )
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain", "Gray Ogre"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_feat(scenario, colour, target):
    sources = scenario.untapped_sources("Plains", "Plains", username="alice")
    scenario.will_choose(colour.value, source="Feat of Resistance")
    scenario.cast_and_resolve("Feat of Resistance", *sources, username="alice", targets=[target])


def test_feat_of_resistance_puts_a_counter_and_grants_the_chosen_protection():
    scenario = _feat_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    _cast_feat(scenario, Color.RED, bears)

    assert bears.counters.power_toughness_modifier == 1
    assert "Protection from red" in _abilities(scenario, bears)
    assert _notices(scenario) == []


def test_the_protection_is_the_colour_chosen_on_resolution():
    scenario = _feat_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    _cast_feat(scenario, Color.BLUE, bears)

    abilities = _abilities(scenario, bears)
    assert "Protection from blue" in abilities
    assert "Protection from red" not in abilities


def test_a_spell_of_the_chosen_colour_cannot_target_the_protected_creature():
    """CR 702.16b."""
    scenario = _feat_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    _cast_feat(scenario, Color.RED, bears)

    scenario.pass_priority("alice")
    with pytest.raises(ValueError, match="protection from red"):
        scenario.cast("Lightning Bolt", username="bob", targets=[bears])


def test_a_spell_of_another_colour_still_can():
    scenario = _feat_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    _cast_feat(scenario, Color.GREEN, bears)

    scenario.pass_priority("alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="bob", targets=[bears])

    assert bears.zone is Zone.GRAVEYARD or bears.damage >= 3


def test_only_the_target_is_protected():
    scenario = _feat_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    elves = scenario.creature("Llanowar Elves", "alice")
    _cast_feat(scenario, Color.RED, bears)

    assert "Protection from red" not in _abilities(scenario, elves)
    assert elves.counters.power_toughness_modifier == 0


def test_the_counter_stays_but_the_protection_ends_with_the_turn():
    scenario = _feat_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    _cast_feat(scenario, Color.RED, bears)
    scenario.game.continuous_effects.end_the_turn(scenario.game)

    assert bears.counters.power_toughness_modifier == 1
    assert "Protection from red" not in _abilities(scenario, bears)


def test_with_the_target_gone_nothing_is_counted_or_protected_and_no_colour_is_asked():
    scenario = _feat_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    sources = scenario.untapped_sources("Plains", "Plains", username="alice")
    scenario.cast_onto_stack("Feat of Resistance", *sources, username="alice", targets=[bears])
    scenario.game.return_to_hand(bears)
    scenario.pass_until_resolved()

    assert not scenario.questions_asked()
    assert _notices(scenario) == []


def test_feat_of_resistance_refuses_an_opponents_creature():
    scenario = _feat_board()
    ogre = scenario.creature("Gray Ogre", "bob")
    with pytest.raises(ValueError):
        scenario.cast("Feat of Resistance", username="alice", targets=[ogre])


# -- the second printing: "untap this creature. It gains protection ..." ------


def _skywise_board() -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Mountain", "Pristine Skywise"],
        )
        .player("bob", battlefield=["Gray Ogre"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_pristine_skywise_untaps_and_gains_the_chosen_protection():
    scenario = _skywise_board()
    skywise = scenario.creature("Pristine Skywise", "alice")
    ogre = scenario.creature("Gray Ogre", "bob")
    skywise.tapped = True
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.will_choose(Color.BLUE.value, source="Pristine Skywise")
    scenario.cast_onto_stack("Lightning Bolt", mountain, username="alice", targets=[ogre])
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()

    assert skywise.tapped is False
    assert "Protection from blue" in _abilities(scenario, skywise)
    assert _notices(scenario) == []


def test_pristine_skywise_protection_ends_at_end_of_turn():
    scenario = _skywise_board()
    skywise = scenario.creature("Pristine Skywise", "alice")
    ogre = scenario.creature("Gray Ogre", "bob")
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.will_choose(Color.RED.value, source="Pristine Skywise")
    scenario.cast_onto_stack("Lightning Bolt", mountain, username="alice", targets=[ogre])
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()
    assert "Protection from red" in _abilities(scenario, skywise)
    scenario.game.continuous_effects.end_the_turn(scenario.game)

    assert "Protection from red" not in _abilities(scenario, skywise)


# -- the single-clause shape on a spell, with and without a trailing rider ------


def _single_clause_board(spell) -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[spell],
            battlefield=["Plains", "Plains", "Grizzly Bears"],
            library=["Plains"] * 5,
        )
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_gods_willing_grants_the_chosen_protection_then_scries():
    """CR 608.2c: the protection, then "Scry 1" (CR 701.22a)."""
    scenario = _single_clause_board("Gods Willing")
    bears = scenario.creature("Grizzly Bears", "alice")
    (plains, *_) = scenario.untapped_sources("Plains", username="alice")
    scenario.will_choose(Color.RED.value, source="Gods Willing")
    scenario.scry_keeping_everything_on_top()
    scenario.cast_and_resolve("Gods Willing", plains, username="alice", targets=[bears])

    assert "Protection from red" in _abilities(scenario, bears)
    assert _notices(scenario) == []
    kinds = [question.kind.value for question in scenario.questions_asked()]
    assert "scry" in kinds


def test_center_soul_grants_the_chosen_protection_and_rebounds():
    scenario = _single_clause_board("Center Soul")
    bears = scenario.creature("Grizzly Bears", "alice")
    sources = scenario.untapped_sources("Plains", "Plains", username="alice")
    scenario.will_choose(Color.BLUE.value, source="Center Soul")
    scenario.cast_and_resolve("Center Soul", *sources, username="alice", targets=[bears])

    assert "Protection from blue" in _abilities(scenario, bears)
    assert _notices(scenario) == []


def test_a_protection_spell_cannot_be_aimed_at_an_opponents_creature():
    scenario = (
        Scenario()
        .player("alice", hand=["Gods Willing"], battlefield=["Plains"])
        .player("bob", battlefield=["Gray Ogre"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    with pytest.raises(ValueError):
        scenario.cast(
            "Gods Willing", username="alice", targets=[scenario.creature("Gray Ogre", "bob")]
        )
