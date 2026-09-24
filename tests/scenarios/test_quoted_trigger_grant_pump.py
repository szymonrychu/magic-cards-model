"""Scenario: "Until end of turn, target creature gets +N/+N and gains
<keyword(s)> and "<triggered ability>"." - a pump, keyword grants and a
quoted triggered ability from one resolving instruction.

Every CR number here was read in full with `mise run rules:find` in the
session that wrote this file:

- **CR 613.1f** - layer 6: ability-adding effects - each keyword and the
  quoted ability.
- **CR 613.4c** - layer 7c: the +N/+N modification.
- **CR 613.6** / **CR 613.7b** - one effect in each layer it names, all
  timestamped as the spell resolves.
- **CR 113.10** - an effect that adds an ability says the object "gains" it;
  the quoted text is the whole ability, and the creature has it.
- **CR 611.2a** - "until end of turn" ends in the cleanup step, and the
  granted ability goes with it.
- **CR 611.2c** - the affected object is fixed as the spell resolves.
- **CR 509.1c** - a "blocks it this turn if able" requirement must be obeyed
  when blockers are declared.
- **CR 702.80a** - wither: damage to a creature becomes -1/-1 counters.

Tower Above is the reported card (trample, wither and "When this creature
attacks, target creature blocks it this turn if able."; its {2/G} hybrid
symbols are paid with green or two generic each). Dreadmaw's Ire is the
second printing: an *attacking*-creature target, a single keyword, and a
combat-damage trigger with its own target - legal in Modern, Pioneer and
Standard (Scryfall legalities, 2026-09-23) and in no deck under
`magic-cards-model-api/decks/`.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.machines.layers import Layer, Sublayer
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

GRANTED = "When this creature attacks, target creature blocks it this turn if able."


def computed(scenario: Scenario):
    return scenario.game.continuous_effects.board(scenario.game.battlefield)


def notices(scenario: Scenario) -> list[object]:
    game = scenario.game
    found: list[object] = list(game.continuous_effects.layer_notices)
    for name in type(game).model_fields:
        if name.endswith("_notices"):
            found.extend(getattr(game, name))
    return found


def _resolve_stack(scenario: Scenario) -> None:
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()


def _tower_board(*, lands=("Forest", "Forest", "Forest"), bob=("Serra Angel",)):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Tower Above"],
            battlefield=["Grizzly Bears", *lands],
            library=["Forest"] * 10,
        )
        .player("bob", battlefield=list(bob), library=["Forest"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears")
    bears.summoning_sick = False
    return scenario, bears


def _cast_tower(scenario: Scenario, target, lands=("Forest", "Forest", "Forest")) -> None:
    sources = scenario.untapped_sources(*lands, username="alice")
    scenario.cast_and_resolve("Tower Above", *sources, targets=[target])


def _attack_and_lure(scenario: Scenario, attacker, lured) -> None:
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.choose_trigger_targets(attacker.name, [lured])
    scenario.attack_with(attacker)
    scenario.pass_until_resolved()
    _resolve_stack(scenario)


def test_tower_above_pumps_and_grants_trample_wither_and_the_trigger():
    scenario, bears = _tower_board()
    _cast_tower(scenario, bears)

    board = computed(scenario).of(bears)
    assert (board.power, board.toughness) == (6, 6)
    assert has_keyword(bears, Keyword.TRAMPLE, scenario.game)
    assert has_keyword(bears, Keyword.WITHER, scenario.game)
    assert board.has_ability(GRANTED)
    assert notices(scenario) == []


def test_the_parts_land_in_layer_6_and_7c_with_one_timestamp():
    scenario, bears = _tower_board()
    _cast_tower(scenario, bears)

    effects = scenario.game.continuous_effects.effects
    assert sorted((e.layer.value, e.sublayer) for e in effects) == sorted(
        [
            (Layer.ABILITY.value, None),
            (Layer.ABILITY.value, None),
            (Layer.ABILITY.value, None),
            (Layer.POWER_TOUGHNESS.value, Sublayer.MODIFY),
        ]
    )
    assert len({e.timestamp for e in effects}) == 1


def test_the_granted_trigger_forces_the_target_to_block():
    """CR 509.1c: after the granted attack trigger resolves, declaring no
    blockers is refused while the Angel can block."""
    scenario, bears = _tower_board()
    angel = scenario.creature("Serra Angel", "bob")
    _cast_tower(scenario, bears)
    _attack_and_lure(scenario, bears, angel)

    with pytest.raises(ValueError, match=r"CR 509\.1c"):
        scenario.no_blocks()
    scenario.block(bears, angel)
    assert scenario.blockers() == [angel]


def test_wither_puts_counters_on_the_forced_blocker_and_trample_goes_through():
    """CR 702.80a: the Angel (4/4) takes four -1/-1 counters and dies; the
    other two damage tramples over to bob."""
    scenario, bears = _tower_board()
    angel = scenario.creature("Serra Angel", "bob")
    _cast_tower(scenario, bears)
    _attack_and_lure(scenario, bears, angel)
    scenario.block(bears, angel)
    scenario.combat_damage()
    scenario.state_based_actions()

    assert angel.zone is Zone.GRAVEYARD
    assert angel.damage == 0, "wither marks no damage"
    assert scenario.player("bob").life == 18
    assert bears.zone is Zone.BATTLEFIELD, "a 6/6 survives the Angel's 4"


def test_the_trigger_does_nothing_if_the_creature_is_not_granted_it():
    """Control: the same attack without Tower Above triggers nothing, and no
    block is required."""
    scenario, bears = _tower_board()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)

    assert scenario.pending_triggers == []
    assert scenario.game.stack_is_empty
    scenario.no_blocks()


def test_the_grant_ends_in_the_cleanup_step():
    scenario, bears = _tower_board()
    _cast_tower(scenario, bears)
    scenario.start_at(Step.END_STEP)
    scenario.advance()  # cleanup

    board = computed(scenario).of(bears)
    assert (board.power, board.toughness) == (2, 2)
    assert not board.has_ability(GRANTED)
    assert not has_keyword(bears, Keyword.TRAMPLE, scenario.game)
    assert not has_keyword(bears, Keyword.WITHER, scenario.game)


def test_a_new_object_has_nothing():
    """CR 400.7: bounced and replayed, it is a new object the effect never
    named - no pump, no trigger."""
    scenario, bears = _tower_board()
    _cast_tower(scenario, bears)
    scenario.game.return_to_hand(bears)
    again = scenario.put_onto_battlefield("Grizzly Bears", "alice")

    board = computed(scenario).of(again)
    assert (board.power, board.toughness) == (2, 2)
    assert not board.has_ability(GRANTED)


def test_the_hybrid_cost_can_be_paid_with_generic_mana():
    """{2/G}{2/G}{2/G}: each symbol is {G} or two generic - six Wastes pay it
    and the spell resolves the same way."""
    lands = ("Wastes",) * 6
    scenario, bears = _tower_board(lands=lands)
    _cast_tower(scenario, bears, lands=lands)

    board = computed(scenario).of(bears)
    assert (board.power, board.toughness) == (6, 6)
    assert board.has_ability(GRANTED)


def test_it_can_grant_an_opponents_creature_too():
    """ "target creature" - no controller restriction; the grant lands on
    bob's Angel and bob's Angel is the one that would trigger."""
    scenario, _bears = _tower_board()
    angel = scenario.creature("Serra Angel", "bob")
    _cast_tower(scenario, angel)

    board = computed(scenario).of(angel)
    assert (board.power, board.toughness) == (8, 8)
    assert board.has_ability(GRANTED)
    assert has_keyword(angel, Keyword.WITHER, scenario.game)


# --------------------------------------------------------------------------
# Dreadmaw's Ire - the second printing
# --------------------------------------------------------------------------


def _ire_board(*, bob=("Sol Ring",)):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Dreadmaw's Ire"],
            battlefield=["Hill Giant", "Mountain"],
            library=["Mountain"] * 10,
        )
        .player("bob", battlefield=list(bob), library=["Mountain"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant")
    giant.summoning_sick = False
    return scenario, giant


def test_dreadmaws_ire_grant_destroys_an_artifact_on_combat_damage():
    scenario, giant = _ire_board()
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(giant)
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Dreadmaw's Ire", mountain, targets=[giant])

    board = computed(scenario).of(giant)
    assert (board.power, board.toughness) == (5, 5)
    assert has_keyword(giant, Keyword.TRAMPLE, scenario.game)

    scenario.no_blocks()
    scenario.choose_trigger_targets("Hill Giant", [ring])
    scenario.combat_damage()
    scenario.pass_until_resolved()
    _resolve_stack(scenario)

    assert scenario.player("bob").life == 15
    assert ring.zone is Zone.GRAVEYARD
    assert notices(scenario) == []


def test_dreadmaws_ire_cannot_target_a_creature_that_is_not_attacking():
    scenario, giant = _ire_board()

    with pytest.raises(ValueError):
        scenario.cast("Dreadmaw's Ire", "alice", targets=[giant])
