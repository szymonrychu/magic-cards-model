"""CR 603.12's reflexive triggered ability, on a self-referential "remove a
counter" cost: "Whenever <this> deals combat damage to a player, you may
remove a counter from her. When you do, destroy target artifact or
enchantment that player controls." (Leatherhead, Swamp Stalker).

Unlike `machines/counter_effects._remove_a_counter_if_you_do`'s "remove a
counter from a[n] `<description>` you control. If you do, ..." (a same-
instruction CR 118.12 cost paid against a *chosen* other permanent -
Sanctuary Warden's own shape), this is CR 603.12's different one: the
counter always comes off the ability's own source, "When you do" creates a
genuinely new object on the stack (CR 405.6a: an opponent gets a real chance
to respond before the destroy ever happens), and its own target - "that
player controls" - is not chosen until *that* reflexive ability goes on the
stack, bound to whichever player Leatherhead's own combat damage actually
hit.

Slumbering Walker is the off-pool generality proof: a different trigger
condition ("at the beginning of your end step" rather than "deals combat
damage to a player"), a different consequence with no "that player" restraint
at all (a plain "return target creature card ... from your graveyard"), and
the ordinary self-reference "this creature" rather than a legendary pronoun.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 603.12** - a reflexive triggered ability: created and checked
  immediately, never watching for a future event.
- **CR 118.12** - "[Do something]. If [a player] does, [effect]" is a cost
  paid on resolution - the same shape "When you do" builds a whole new
  ability out of instead of running in the same instruction.
- **CR 405.6a** - a player may respond to an ability on the stack.
- **CR 122.1** - a counter, and CR 122.1's own open set of kinds - "remove a
  counter" with no kind named may take any one the permanent has.
- **CR 608.2d** - a plain "you may" during resolution.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _combat_damage_board():
    return (
        Scenario()
        .player("alice", battlefield=["Leatherhead, Swamp Stalker", "Sol Ring"])
        .player("bob", battlefield=["Sol Ring"])
    )


def test_leatherhead_destroys_the_damaged_players_permanent_when_the_cost_is_paid():
    scenario = _combat_damage_board().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    leatherhead = scenario.find("Leatherhead, Swamp Stalker", Zone.BATTLEFIELD)
    bobs_ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")
    alices_ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")
    scenario.game.add_counters(leatherhead, "hexproof", 1)
    assert leatherhead.counter_count("hexproof") == 1

    scenario.will_take_the_may(True, source="Leatherhead, Swamp Stalker")
    scenario.attack_with(leatherhead)
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.stack_names() == ["Leatherhead, Swamp Stalker's triggered ability"]
    scenario.resolve_top()

    assert leatherhead.counter_count("hexproof") == 0
    assert len(scenario.stack_names()) == 1
    scenario.will_choose_targets(bobs_ring, source="Leatherhead, Swamp Stalker")
    scenario.resolve_top()

    assert bobs_ring.zone is Zone.GRAVEYARD
    assert alices_ring.zone is Zone.BATTLEFIELD


def test_leatherhead_cannot_target_the_leatherhead_players_own_permanent():
    """ "that player controls" is bound to the player Leatherhead's own
    combat damage actually hit (CR 603.3d) - never the ability's own
    controller."""
    scenario = _combat_damage_board().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    leatherhead = scenario.find("Leatherhead, Swamp Stalker", Zone.BATTLEFIELD)
    alices_ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "alice")

    scenario.will_take_the_may(True, source="Leatherhead, Swamp Stalker")
    scenario.attack_with(leatherhead)
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.resolve_top()

    with pytest.raises(ValueError):
        scenario.will_choose_targets(alices_ring, source="Leatherhead, Swamp Stalker")
        scenario.resolve_top()


def test_declining_the_cost_leaves_the_counter_and_creates_no_reflexive_ability():
    scenario = _combat_damage_board().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    leatherhead = scenario.find("Leatherhead, Swamp Stalker", Zone.BATTLEFIELD)
    bobs_ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")
    scenario.game.add_counters(leatherhead, "hexproof", 1)

    scenario.will_take_the_may(False, source="Leatherhead, Swamp Stalker")
    scenario.attack_with(leatherhead)
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.resolve_top()

    assert leatherhead.counter_count("hexproof") == 1
    assert scenario.stack_names() == []
    assert bobs_ring.zone is Zone.BATTLEFIELD


def test_with_no_counters_left_the_ability_asks_nothing_and_does_nothing():
    """`_remove_a_counter_from_it_when_you_do`'s own early refusal: with no
    counter to remove at all, CR 608.2d's "you may" is never even asked."""
    scenario = _combat_damage_board().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    leatherhead = scenario.find("Leatherhead, Swamp Stalker", Zone.BATTLEFIELD)
    assert leatherhead.counter_count("hexproof") == 0

    scenario.attack_with(leatherhead)
    scenario.no_blocks()
    scenario.combat_damage()

    assert scenario.stack_names() == ["Leatherhead, Swamp Stalker's triggered ability"]
    asked_before = len(scenario.questions_asked())
    scenario.resolve_top()

    assert len(scenario.questions_asked()) == asked_before
    assert scenario.stack_names() == []


def test_slumbering_walker_off_pool_proof_reflexively_reanimates_a_small_creature():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Slumbering Walker"],
            graveyard=["Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    walker = scenario.find("Slumbering Walker", Zone.BATTLEFIELD)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD)
    scenario.game.add_counters(walker, "-1/-1", 2)
    assert walker.counter_count("-1/-1") == 2

    scenario.will_take_the_may(True, source="Slumbering Walker")
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.advance()  # end step

    assert scenario.stack_names() == ["Slumbering Walker's triggered ability"]
    scenario.resolve_top()

    assert walker.counter_count("-1/-1") == 1
    assert len(scenario.stack_names()) == 1
    scenario.will_choose_targets(bears, source="Slumbering Walker")
    scenario.resolve_top()

    assert bears.zone is Zone.BATTLEFIELD
