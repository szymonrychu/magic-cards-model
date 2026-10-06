"""Scenario: excess damage from a fight paying out mana, "you don't lose unspent
red mana" for the turn, and "when the permanent you don't control dies this
turn, you gain N life".

The Last Agni Kai: "Target creature you control fights target creature an
opponent controls. If the creature the opponent controls is dealt excess
damage this way, add that much {R}. Until end of turn, you don't lose unspent
red mana as steps and phases end."

- the fight is simultaneous damage both ways (CR 701.14a), and its damage is
  not combat damage (CR 701.14d);
- the excess is the damage above what is lethal for the victim, counting
  damage already marked on it, and a deathtouch source makes any damage above
  1 excess (CR 120.4a); prevented damage is never dealt, so it is never
  excess (CR 615.6);
- the mana is added to the controller's pool (CR 106.4) as the spell
  resolves;
- the second paragraph is a continuous effect that lasts until end of turn
  (CR 611.2a), not tied to the mana already in the pool (CR 611.2c), and only
  red mana is kept: other mana still empties as each step and phase ends
  (CR 500.5) and so does everyone else's.

Devouring Tendrils: "Target creature you control deals damage equal to its
power to target creature or planeswalker you don't control. When the permanent
you don't control dies this turn, you gain 2 life." The second sentence creates
a delayed triggered ability (CR 603.7a) watching the bite's victim (CR 603.7c,
that object only) for the rest of the turn (CR 603.7b).

Every CR number below was read in full with `mise run rules:find` in the
session that wrote this file.

Listed printings: The Last Agni Kai, Devouring Tendrils.

No other printing legal in Modern, Pioneer or Standard carries "add that much"
after an excess-damage condition, "until end of turn, you don't lose unspent"
(the static "you don't lose unspent <colour> mana" of Leyline Tyrant and
Fangorn, Tree Shepherd is the permanent version and is checked below to keep
working beside the new turn-scoped one), or "When the permanent you don't
control dies this turn" (Scryfall `o:` searches over the three formats), so
there is no second printing to prove these three on; the nearest printing of
each is exercised instead and the substitution is recorded in MEMORY.md.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Color
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario

LISTED = ("The Last Agni Kai", "Devouring Tendrils")
NEAREST = ("Leyline Tyrant", "Fangorn, Tree Shepherd")


@pytest.mark.parametrize("name", LISTED)
def test_every_listed_card_reads_handled(name):
    outcomes = {clause.outcome for clause in card_support(card(name)).clauses}
    assert outcomes == {"handled"}, name


def _board(
    *,
    alice_hand=(),
    alice_battlefield=(),
    bob_battlefield=(),
    bob_hand=(),
):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=list(alice_hand),
            battlefield=[*["Mountain"] * 4, *["Forest"] * 3, *alice_battlefield],
            library=["Mountain"] * 6,
        )
        .player(
            "bob",
            hand=list(bob_hand),
            battlefield=[*["Mountain"] * 2, *bob_battlefield],
            library=["Mountain"] * 6,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _red(scenario, username="alice"):
    return scenario.player(username).mana_pool.floating.get(Color.RED, 0)


def _pool_total(scenario, username="alice"):
    return scenario.player(username).mana_pool.total


def _kai(scenario, mine, theirs):
    return scenario.cast_and_resolve(
        "The Last Agni Kai",
        *scenario.untapped_sources("Mountain", "Mountain"),
        username="alice",
        targets=[mine, theirs],
    )


def _walk_to_next_turn_of(scenario, username):
    while not (scenario.step is Step.UPKEEP and scenario.turn.active_player == username):
        scenario.advance()
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()


# -- The Last Agni Kai: the fight and its excess ------------------------------


def test_the_excess_over_lethal_damage_is_added_as_red_mana():
    scenario = _board(
        alice_hand=["The Last Agni Kai"],
        alice_battlefield=["Hill Giant"],
        bob_battlefield=["Grizzly Bears"],
    )
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")

    _kai(scenario, giant, bears)

    assert bears.zone is Zone.BATTLEFIELD or bears in scenario.player("bob").graveyard
    assert giant.damage == 2  # the fight is two-way
    assert _red(scenario) == 1  # 3 damage to a 2/2: 1 excess
    assert _pool_total(scenario) == 1


def test_a_bigger_fighter_adds_more_mana():
    scenario = _board(
        alice_hand=["The Last Agni Kai"],
        alice_battlefield=["Colossal Dreadmaw"],
        bob_battlefield=["Grizzly Bears"],
    )
    dreadmaw = scenario.creature("Colossal Dreadmaw", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")

    _kai(scenario, dreadmaw, bears)

    assert _red(scenario) == 4  # 6 damage to a 2/2


def test_exactly_lethal_damage_has_no_excess():
    scenario = _board(
        alice_hand=["The Last Agni Kai"],
        alice_battlefield=["Hill Giant"],
        bob_battlefield=["Hill Giant"],
    )
    mine = scenario.creature("Hill Giant", "alice")
    theirs = scenario.creature("Hill Giant", "bob")

    _kai(scenario, mine, theirs)

    assert _red(scenario) == 0


def test_a_victim_that_survives_the_damage_has_no_excess():
    scenario = _board(
        alice_hand=["The Last Agni Kai"],
        alice_battlefield=["Grizzly Bears"],
        bob_battlefield=["Colossal Dreadmaw"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")

    _kai(scenario, bears, dreadmaw)

    assert dreadmaw.damage == 2
    assert _red(scenario) == 0


def test_damage_already_marked_on_the_victim_lowers_what_is_lethal():
    scenario = _board(
        alice_hand=["The Last Agni Kai"],
        alice_battlefield=["Hill Giant"],
        bob_battlefield=["Giant Spider"],
    )
    giant = scenario.creature("Hill Giant", "alice")
    spider = scenario.creature("Giant Spider", "bob")
    spider.damage = 2  # a 2/4 with 2 left to be lethal

    _kai(scenario, giant, spider)

    assert _red(scenario) == 1  # 3 damage, 2 lethal


def test_a_deathtouch_fighter_makes_everything_above_one_excess():
    scenario = _board(
        alice_hand=["The Last Agni Kai"],
        alice_battlefield=["Perforating Artist"],
        bob_battlefield=["Colossal Dreadmaw"],
    )
    artist = scenario.creature("Perforating Artist", "alice")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")

    _kai(scenario, artist, dreadmaw)

    assert _red(scenario) == 2  # 3 deathtouch damage, 1 is lethal (CR 120.4a)


def test_prevented_damage_is_never_dealt_so_it_is_never_excess():
    scenario = _board(
        alice_hand=["The Last Agni Kai"],
        alice_battlefield=["Hill Giant"],
        bob_battlefield=["Grizzly Bears", "Plains"],
        bob_hand=["Shielded Passage"],
    )
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.cast_onto_stack(
        "The Last Agni Kai",
        *scenario.untapped_sources("Mountain", "Mountain"),
        username="alice",
        targets=[giant, bears],
    )
    scenario.pass_priority("alice")
    scenario.cast_and_resolve(
        "Shielded Passage",
        *scenario.untapped_sources("Plains", username="bob"),
        username="bob",
        targets=[bears],
    )
    scenario.resolve_top()  # the fight: the damage to the Bears is prevented

    assert bears.damage == 0  # CR 615.6
    assert giant.damage == 2  # the Bears still hit back
    assert _red(scenario) == 0


def test_the_fight_does_nothing_when_the_opponents_creature_is_gone():
    scenario = _board(
        alice_hand=["The Last Agni Kai"],
        alice_battlefield=["Hill Giant"],
        bob_battlefield=["Grizzly Bears", "Hill Giant"],
        bob_hand=["Lightning Bolt"],
    )
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.cast_onto_stack(
        "The Last Agni Kai",
        *scenario.untapped_sources("Mountain", "Mountain"),
        username="alice",
        targets=[giant, bears],
    )
    scenario.pass_priority("alice")
    scenario.cast_onto_stack(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="bob"),
        username="bob",
        targets=[bears],
    )
    scenario.resolve_top()
    scenario.resolve_top()

    assert giant.damage == 0  # CR 701.14b: neither fights
    assert _red(scenario) == 0


def test_the_mana_goes_to_the_controller_not_the_opponent():
    scenario = _board(
        alice_hand=["The Last Agni Kai"],
        alice_battlefield=["Hill Giant"],
        bob_battlefield=["Grizzly Bears"],
    )
    _kai(
        scenario,
        scenario.creature("Hill Giant", "alice"),
        scenario.creature("Grizzly Bears", "bob"),
    )
    assert _pool_total(scenario, "bob") == 0


# -- The Last Agni Kai: "you don't lose unspent red mana" ----------------------


def test_red_mana_survives_the_end_of_the_main_phase_and_step_changes():
    scenario = _board(
        alice_hand=["The Last Agni Kai"],
        alice_battlefield=["Hill Giant"],
        bob_battlefield=["Grizzly Bears"],
    )
    _kai(
        scenario,
        scenario.creature("Hill Giant", "alice"),
        scenario.creature("Grizzly Bears", "bob"),
    )
    assert _red(scenario) == 1

    scenario.advance()  # into combat
    scenario.advance()
    scenario.advance()

    assert _red(scenario) == 1
    assert scenario.step is not Step.PRECOMBAT_MAIN


def test_red_mana_added_after_the_spell_is_kept_too():
    scenario = _board(
        alice_hand=["The Last Agni Kai"],
        alice_battlefield=["Hill Giant"],
        bob_battlefield=["Hill Giant"],
    )
    _kai(
        scenario,
        scenario.creature("Hill Giant", "alice"),
        scenario.creature("Hill Giant", "bob"),
    )
    (mountain,) = scenario.untapped_sources("Mountain")[:1]
    scenario.activate(mountain, color=Color.RED)
    assert _red(scenario) == 1

    scenario.advance()

    assert _red(scenario) == 1


def test_mana_of_other_colours_still_empties():
    scenario = _board(
        alice_hand=["The Last Agni Kai"],
        alice_battlefield=["Hill Giant"],
        bob_battlefield=["Hill Giant"],
    )
    _kai(
        scenario,
        scenario.creature("Hill Giant", "alice"),
        scenario.creature("Hill Giant", "bob"),
    )
    (forest,) = scenario.untapped_sources("Forest")[:1]
    scenario.activate(forest, color=Color.GREEN)
    (mountain,) = scenario.untapped_sources("Mountain")[:1]
    scenario.activate(mountain, color=Color.RED)
    assert _pool_total(scenario) == 2

    scenario.advance()

    assert _red(scenario) == 1
    assert _pool_total(scenario) == 1


def test_the_opponents_red_mana_still_empties():
    scenario = _board(
        alice_hand=["The Last Agni Kai"],
        alice_battlefield=["Hill Giant"],
        bob_battlefield=["Hill Giant"],
    )
    _kai(
        scenario,
        scenario.creature("Hill Giant", "alice"),
        scenario.creature("Hill Giant", "bob"),
    )
    scenario.game.mana_pool_receiving("bob").add(Color.RED)
    assert _red(scenario, "bob") == 1

    scenario.advance()

    assert _red(scenario, "bob") == 0


def test_the_effect_ends_with_the_turn():
    scenario = _board(
        alice_hand=["The Last Agni Kai"],
        alice_battlefield=["Hill Giant"],
        bob_battlefield=["Grizzly Bears"],
    )
    _kai(
        scenario,
        scenario.creature("Hill Giant", "alice"),
        scenario.creature("Grizzly Bears", "bob"),
    )
    assert _red(scenario) == 1

    _walk_to_next_turn_of(scenario, "bob")

    assert _red(scenario) == 0
    assert _pool_total(scenario) == 0
    scenario.game.mana_pool_receiving("alice").add(Color.RED)
    scenario.advance()
    assert _red(scenario) == 0  # a new turn: nothing is kept any more


def test_red_mana_is_still_lost_on_a_turn_with_no_effect():
    scenario = _board()
    scenario.game.mana_pool_receiving("alice").add(Color.RED)

    scenario.advance()

    assert _red(scenario) == 0


# -- the permanent version keeps working beside the turn-scoped one -----------


@pytest.mark.parametrize("name", NEAREST)
def test_the_static_unspent_mana_lines_still_read_handled(name):
    clauses = card_support(card(name)).clauses
    unspent = [c for c in clauses if "unspent" in c.text.lower()]
    assert unspent
    assert {c.outcome for c in unspent} == {"handled"}


def test_a_permanent_keeping_green_mana_and_the_spell_keeping_red_both_apply():
    scenario = _board(
        alice_hand=["The Last Agni Kai"],
        alice_battlefield=["Hill Giant", "Fangorn, Tree Shepherd"],
        bob_battlefield=["Hill Giant"],
    )
    _kai(
        scenario,
        scenario.creature("Hill Giant", "alice"),
        scenario.creature("Hill Giant", "bob"),
    )
    (forest,) = scenario.untapped_sources("Forest")[:1]
    scenario.activate(forest, color=Color.GREEN)
    (mountain,) = scenario.untapped_sources("Mountain")[:1]
    scenario.activate(mountain, color=Color.RED)

    scenario.advance()

    assert _pool_total(scenario) == 2


# -- Devouring Tendrils ----------------------------------------------------------


def _tendrils(scenario, biter, victim):
    scenario.cast_and_resolve(
        "Devouring Tendrils",
        *scenario.untapped_sources("Forest", "Forest"),
        username="alice",
        targets=[biter, victim],
    )
    scenario.state_based_actions()
    scenario.pass_until_resolved()


def test_the_victim_dying_gains_two_life():
    scenario = _board(
        alice_hand=["Devouring Tendrils"],
        alice_battlefield=["Hill Giant"],
        bob_battlefield=["Grizzly Bears"],
    )
    bears = scenario.creature("Grizzly Bears", "bob")

    _tendrils(scenario, scenario.creature("Hill Giant", "alice"), bears)

    assert bears.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 22
    assert scenario.player("bob").life == 20


def test_a_victim_that_survives_the_bite_but_dies_later_this_turn_still_pays_out():
    scenario = _board(
        alice_hand=["Devouring Tendrils", "Lightning Bolt"],
        alice_battlefield=["Grizzly Bears"],
        bob_battlefield=["Hill Giant"],
    )
    giant = scenario.creature("Hill Giant", "bob")

    _tendrils(scenario, scenario.creature("Grizzly Bears", "alice"), giant)
    assert giant.zone is Zone.BATTLEFIELD
    assert scenario.player("alice").life == 20
    scenario.cast_and_resolve(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain"),
        username="alice",
        targets=[giant],
    )
    scenario.state_based_actions()
    scenario.pass_until_resolved()

    assert giant.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 22


def test_a_victim_that_dies_on_a_later_turn_pays_nothing():
    scenario = _board(
        alice_hand=["Devouring Tendrils"],
        alice_battlefield=["Grizzly Bears"],
        bob_battlefield=["Hill Giant"],
        bob_hand=["Lightning Bolt"],
    )
    giant = scenario.creature("Hill Giant", "bob")
    _tendrils(scenario, scenario.creature("Grizzly Bears", "alice"), giant)

    _walk_to_next_turn_of(scenario, "bob")
    scenario.cast_and_resolve(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="bob"),
        username="bob",
        targets=[giant],
    )
    scenario.state_based_actions()
    scenario.pass_until_resolved()

    assert giant.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 20


def test_another_creature_dying_this_turn_does_not_pay_out():
    scenario = _board(
        alice_hand=["Devouring Tendrils", "Lightning Bolt"],
        alice_battlefield=["Grizzly Bears"],
        bob_battlefield=["Hill Giant", "Savannah Lions"],
    )
    giant = scenario.creature("Hill Giant", "bob")
    lions = scenario.creature("Savannah Lions", "bob")
    _tendrils(scenario, scenario.creature("Grizzly Bears", "alice"), giant)

    scenario.cast_and_resolve(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain"),
        username="alice",
        targets=[lions],
    )
    scenario.state_based_actions()
    scenario.pass_until_resolved()

    assert lions.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 20


def test_the_biter_dying_does_not_pay_out():
    scenario = _board(
        alice_hand=["Devouring Tendrils", "Lightning Bolt"],
        alice_battlefield=["Grizzly Bears"],
        bob_battlefield=["Hill Giant"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    _tendrils(scenario, bears, giant)

    scenario.cast_and_resolve(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain"),
        username="alice",
        targets=[bears],
    )
    scenario.state_based_actions()
    scenario.pass_until_resolved()

    assert bears.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 20


def test_a_planeswalker_victim_dying_pays_out_too():
    scenario = _board(
        alice_hand=["Devouring Tendrils"],
        alice_battlefield=["Hill Giant"],
        bob_battlefield=["Jace Beleren"],
    )
    jace = scenario.find("Jace Beleren", Zone.BATTLEFIELD, "bob")

    _tendrils(scenario, scenario.creature("Hill Giant", "alice"), jace)

    assert jace.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 22


def test_a_victim_that_leaves_by_exile_instead_of_dying_pays_nothing():
    scenario = _board(
        alice_hand=["Devouring Tendrils", "Swords to Plowshares"],
        alice_battlefield=["Grizzly Bears", "Plains"],
        bob_battlefield=["Hill Giant"],
    )
    giant = scenario.creature("Hill Giant", "bob")
    _tendrils(scenario, scenario.creature("Grizzly Bears", "alice"), giant)

    scenario.cast_and_resolve(
        "Swords to Plowshares",
        *scenario.untapped_sources("Plains"),
        username="alice",
        targets=[giant],
    )
    scenario.state_based_actions()
    scenario.pass_until_resolved()

    assert giant.zone is Zone.EXILE
    assert scenario.player("alice").life == 20  # no bite payout
    assert scenario.player("bob").life == 23  # Swords' own life gain, to the Giant's controller
