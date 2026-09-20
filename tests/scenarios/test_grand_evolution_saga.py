"""Vorinclex // The Grand Evolution's own Saga chapters II and III, once
Vorinclex has transformed (`test_exile_self_then_return_transformed.py`
already covers the transform itself):

- **II - "Distribute seven +1/+1 counters among any number of target
  creatures you control."** CR 601.2d's "divide or distribute an effect
  (such as damage or counters) among one or more targets" -
  `machines/targeting._read_division` already reads this shape at
  announcement time; `_distribute_counters_shares` is the resolution half,
  the counter-kind twin of `_deal_divided_damage_shares`.
- **III - "Until end of turn, creatures you control gain "{1}: This
  creature fights target creature you don't control." Exile this Saga, then
  return it to the battlefield (front face up)."** A group layer-6 grant
  (CR 613.1f) built by hand (`creatures_controlled_by`, `grant_ability`),
  paired with CR 712.2's *absolute* "front face up" return - distinct from
  CR 701.27a's relative "transformed", which always flips.

`Game.saga_lore_step()` is called directly to add each lore counter, the
same shortcut `test_sagas.py`'s own chapter-three test already uses "in
place of driving two full opposing turns" - CR 703.4f is turn-agnostic once
it fires. Chapter I ("Mill ten cards. Put up to two creature cards from
among the milled cards onto the battlefield.") is left to run and resolve
on an all-land library, so it makes no choice of its own and this file's own
assertions stay on chapters II and III.

Every CR number below was verified with `mise run rules:find` in this
session: 601.2d, 613.1f, 712.2, 714.2/714.3a/714.4 (already verified for
`test_sagas.py`).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import CardState, Counter

from .harness import Scenario

VORINCLEX = "Vorinclex // The Grand Evolution"
GRAND_EVOLUTION = "The Grand Evolution"


def _transformed_saga() -> tuple[Scenario, CardState]:
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=[VORINCLEX, "Grizzly Bears", "Elvish Mystic"] + ["Forest"] * 8,
            library=["Forest"] * 10,
        )
        .player("bob", battlefield=["Watchwolf"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    vorinclex = scenario.find("Vorinclex", Zone.BATTLEFIELD, "alice")
    scenario.activate(vorinclex, auto=True)
    scenario.pass_until_resolved()
    assert vorinclex.transformed is True
    assert vorinclex.name == "The Grand Evolution"

    # Chapter I fired as the Saga entered (CR 714.3a's intrinsic lore
    # counter). Resolve it - milling an all-land library finds no creature
    # cards, so nothing is put onto the battlefield and no decision is asked.
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
    assert vorinclex.counters[Counter.LORE] == 1
    return scenario, vorinclex


def test_chapter_two_distributes_seven_counters_among_alices_creatures():
    scenario, saga = _transformed_saga()
    bears = scenario.creature("Grizzly Bears", "alice")
    mystic = scenario.creature("Elvish Mystic", "alice")

    scenario.game.saga_lore_step()
    assert saga.counters[Counter.LORE] == 2
    scenario.choose_trigger_targets(GRAND_EVOLUTION, [bears, mystic])
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()

    total = bears.counters[Counter.PLUS_ONE] + mystic.counters[Counter.PLUS_ONE]
    assert total == 7
    # CR 601.2d: each chosen target must receive at least one.
    assert bears.counters[Counter.PLUS_ONE] >= 1
    assert mystic.counters[Counter.PLUS_ONE] >= 1


def test_chapter_three_grants_the_fight_ability_then_returns_front_face_up():
    scenario, saga = _transformed_saga()
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.game.saga_lore_step()
    scenario.choose_trigger_targets(GRAND_EVOLUTION, [])
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
    assert saga.counters[Counter.LORE] == 2

    scenario.game.saga_lore_step()
    assert saga.counters[Counter.LORE] == 3
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()

    chars = scenario.game.computed_board().of(bears)
    assert any(ability.startswith("{1}: This creature fights") for ability in chars.abilities)

    # "Exile this Saga, then return it to the battlefield (front face up)."
    assert saga.zone is Zone.BATTLEFIELD
    assert saga.transformed is False
    assert saga.name == "Vorinclex"
    assert saga.controller == "alice"
