"""Mutate and merged permanents (EP-01 round 3, T4).

Brokkos, Apex of Forever: "Mutate {2}{U/B}{G}{G}", "Trample", "You may cast
this card from your graveyard using its mutate ability." Gemrazer: "Mutate
{1}{G}{G}", "Reach, trample", "Whenever this creature mutates, destroy target
artifact or enchantment an opponent controls."

Rules read with `mise run rules:find` in the session that wrote this:

- **CR 702.140a** - mutate is an alternative cost; the spell becomes a
  mutating creature spell targeting a non-Human creature with the same owner.
- **CR 702.140b** - an illegal target as it begins resolving: it continues
  resolving as a plain creature spell.
- **CR 702.140c** - a legal target: it merges with it, over or under, the
  controller's choice.
- **CR 702.140d** - "whenever a creature mutates" triggers on that merge.
- **CR 702.140e** - abilities of every component, other characteristics of
  the topmost.
- **CR 730.2a-c** - the merged permanent is the same object; not new.
- **CR 730.3** - leaving the battlefield moves every component.
- **CR 604.6** - the graveyard permission names the mutate ability.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.machines.legal_actions import legal_actions
from magic_cards_model.models import Zone
from magic_cards_model.models.action import ActionKind
from magic_cards_model.models.game import Game
from magic_cards_model.models.mana import ManaCost
from tests.scenarios.harness import PlayedScenario, Scenario

BROKKOS = "Brokkos, Apex of Forever"
GEMRAZER = "Gemrazer"
LANDS = ["Forest", "Forest", "Forest", "Forest", "Swamp", "Swamp"]


def _board(
    *,
    hand=(),
    graveyard=(),
    battlefield=("Grizzly Bears",),
    bob_battlefield=(),
) -> PlayedScenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=list(hand),
            graveyard=list(graveyard),
            battlefield=[*battlefield, *LANDS],
            library=["Island"] * 10,
        )
        .player("bob", battlefield=list(bob_battlefield), library=["Island"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _mutate_onto(scenario, name, target, *, from_zone=Zone.HAND, top=True):
    casting = scenario.cast(name, from_zone=from_zone)
    casting.use_keyword("Mutate")
    casting.choose_targets([target])
    payment = casting.begin_paying()
    scenario.auto_pay(payment, username="alice")
    spell = scenario.put_on_stack(casting)
    scenario.will_choose_top(top, username="alice")
    scenario.resolve_top()
    return casting, spell


def _creatures(scenario):
    return [
        state
        for state in scenario.game.battlefield
        if state.is_creature and state.controller == "alice"
    ]


def test_brokkos_mutated_over_a_non_human_creature_is_one_brokkos_with_both_abilities():
    scenario = _board(hand=[BROKKOS])
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    casting, brokkos = _mutate_onto(scenario, BROKKOS, bears, top=True)

    assert casting.total_cost.mana == ManaCost.parse("{2}{U/B}{G}{G}")
    creatures = _creatures(scenario)
    assert [state.id for state in creatures] == [bears.id]
    merged = creatures[0]
    view = scenario.game.characteristics_of(merged)
    assert view.name == BROKKOS
    assert (view.power, view.toughness) == (6, 6)
    assert has_keyword(merged, Keyword.TRAMPLE, scenario.game)
    assert view.mana_value == 5
    assert brokkos.zone is Zone.BATTLEFIELD
    assert brokkos not in scenario.game.battlefield
    assert scenario.player("alice").hand == []


def test_brokkos_mutated_under_keeps_the_creatures_characteristics_and_adds_trample():
    scenario = _board(hand=[BROKKOS])
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    _mutate_onto(scenario, BROKKOS, bears, top=False)

    [merged] = _creatures(scenario)
    view = scenario.game.characteristics_of(merged)
    assert view.name == "Grizzly Bears"
    assert (view.power, view.toughness) == (2, 2)
    assert has_keyword(merged, Keyword.TRAMPLE, scenario.game)
    assert view.mana_value == 2


def test_a_human_target_is_refused():
    scenario = _board(hand=[BROKKOS], battlefield=("Elite Vanguard",))
    vanguard = scenario.find("Elite Vanguard", Zone.BATTLEFIELD, "alice")
    casting = scenario.cast(BROKKOS)
    casting.use_keyword("Mutate")
    with pytest.raises(ValueError):
        casting.choose_targets([vanguard])


def test_a_creature_alice_does_not_own_is_refused():
    scenario = _board(hand=[BROKKOS], battlefield=(), bob_battlefield=("Grizzly Bears",))
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    casting = scenario.cast(BROKKOS)
    casting.use_keyword("Mutate")
    with pytest.raises(ValueError):
        casting.choose_targets([bears])


def test_an_illegal_target_on_resolution_puts_brokkos_onto_the_battlefield_as_a_creature():
    scenario = _board(hand=[BROKKOS])
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    casting = scenario.cast(BROKKOS)
    casting.use_keyword("Mutate")
    casting.choose_targets([bears])
    scenario.auto_pay(casting.begin_paying(), username="alice")
    brokkos = scenario.put_on_stack(casting)
    scenario.game.destroy(bears)
    scenario.resolve_top()

    assert bears.zone is Zone.GRAVEYARD
    assert brokkos.zone is Zone.BATTLEFIELD
    assert brokkos in scenario.game.battlefield
    assert brokkos.name == BROKKOS
    view = scenario.game.characteristics_of(brokkos)
    assert (view.power, view.toughness) == (6, 6)


def test_brokkos_is_cast_from_the_graveyard_using_its_mutate_ability():
    scenario = _board(graveyard=[BROKKOS])
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    _mutate_onto(scenario, BROKKOS, bears, from_zone=Zone.GRAVEYARD, top=True)

    [merged] = _creatures(scenario)
    assert merged.id == bears.id
    assert scenario.game.characteristics_of(merged).name == BROKKOS
    assert scenario.player("alice").graveyard == []


def test_brokkos_is_not_cast_from_the_graveyard_for_its_mana_cost():
    scenario = _board(graveyard=[BROKKOS])
    casting = scenario.cast(BROKKOS, from_zone=Zone.GRAVEYARD)
    with pytest.raises(ValueError):
        scenario.auto_pay(casting.begin_paying(), username="alice")
        scenario.put_on_stack(casting)


def test_gemrazers_mutate_trigger_destroys_an_opponents_artifact():
    scenario = _board(hand=[GEMRAZER], bob_battlefield=("Ornithopter",))
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    ornithopter = scenario.find("Ornithopter", Zone.BATTLEFIELD, "bob")
    _mutate_onto(scenario, GEMRAZER, bears, top=False)

    [merged] = _creatures(scenario)
    assert scenario.game.characteristics_of(merged).name == "Grizzly Bears"
    assert has_keyword(merged, Keyword.REACH, scenario.game)
    assert has_keyword(merged, Keyword.TRAMPLE, scenario.game)
    assert not scenario.game.stack_is_empty
    scenario.resolve_top()
    assert ornithopter.zone is Zone.GRAVEYARD


def test_a_merged_permanent_that_dies_puts_every_card_in_the_graveyard():
    scenario = _board(hand=[BROKKOS])
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    _mutate_onto(scenario, BROKKOS, bears, top=True)
    [merged] = _creatures(scenario)
    scenario.game.destroy(merged)

    graveyard = sorted(state.name for state in scenario.player("alice").graveyard)
    assert graveyard == [BROKKOS, "Grizzly Bears"]
    assert _creatures(scenario) == []
    bears_card = next(s for s in scenario.player("alice").graveyard if s.id == bears.id)
    assert bears_card.name == "Grizzly Bears"
    assert scenario.game.merged_components == {}


def test_a_merged_permanent_survives_a_replay_round_trip():
    scenario = _board(hand=[BROKKOS])
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    _mutate_onto(scenario, BROKKOS, bears, top=True)

    restored = Game.model_validate_json(scenario.game.model_dump_json())
    [merged] = [state for state in restored.battlefield if state.is_creature]
    assert restored.characteristics_of(merged).name == BROKKOS
    assert has_keyword(merged, Keyword.TRAMPLE, restored)
    restored.destroy(merged)
    owner = next(player for player in restored.players if player.username == "alice")
    assert sorted(state.name for state in owner.graveyard) == [BROKKOS, "Grizzly Bears"]


def test_the_graveyard_mutate_cast_is_the_one_legal_cast_of_brokkos_there():
    scenario = _board(graveyard=[BROKKOS])
    brokkos = scenario.player("alice").graveyard[0]
    casts = [
        (action.keyword, action.from_zone)
        for action in legal_actions(scenario.game, "alice")
        if action.kind is ActionKind.CAST and action.card_id == brokkos.id
    ]
    assert casts == [("Mutate", Zone.GRAVEYARD)]
