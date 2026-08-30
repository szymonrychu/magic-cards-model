"""Counters on permanents and players (CR 122).

One mechanic per file, and this file is counters: what they do to power and
toughness, the state-based actions they drive, what happens to them when the
object changes zones, and where they land in the layer system.

Every card is a real Scryfall printing out of `tests/fixtures/cards`. Walking
Ballista, Devoted Druid, Basking Broodscale, Hangarback Walker and Kalonian
Hydra are all cards whose whole text is counters, which is why they are the
ones here.

Every CR number in this file was looked up with `knowledge_search` in the
session that wrote it. Two are worth calling out because folklore has them
wrong:

- Counters modify power and toughness in **layer 7c** (CR 613.4c, "effects
  *and counters* that modify power and/or toughness"). There is no separate
  counters sublayer and no 613.4e.
- +1/+1 and -1/-1 counters annihilate under **CR 704.5q** (CR 122.3 states the
  same rule from the counters' side).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.layers import compute_board, static_effects
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from magic_cards_model.models.player import POISON_TO_LOSE
from tests.scenarios.harness import Scenario


def board(**kwargs) -> Scenario:
    """One player with a battlefield, ready to build.

    Unbuilt, so each test calls `.build()` on a fresh game. Turn-based actions
    are off: these boards have no library, and an automatic draw would lose the
    game before the counters got a look in (CR 104.3c).
    """
    return Scenario().manual_turn_based_actions().player("alice", **kwargs)


# --------------------------------------------------------------------------
# What a counter does (CR 122.1a)
# --------------------------------------------------------------------------


def test_plus_one_counters_add_to_power_and_toughness():
    """CR 122.1a: a +1/+1 counter adds 1 to power and 1 to toughness.

    Hangarback Walker is printed 0/0 and is only ever a creature because of the
    counters it enters with, so it is the honest test that the counters are
    doing the work rather than the printing.
    """
    scenario = board(battlefield=["Hangarback Walker"]).build()
    walker = scenario.creature("Hangarback Walker")

    assert (walker.power, walker.toughness) == (0, 0)
    walker.add_counters(Counter.PLUS_ONE, 3)

    assert (walker.power, walker.toughness) == (3, 3)
    assert walker.counter_count("+1/+1") == 3


def test_minus_one_counters_subtract_from_power_and_toughness():
    """CR 122.1a again, the other way: "a -X/-Y counter ... subtracts"."""
    scenario = board(battlefield=["Questing Beast"]).build()
    beast = scenario.creature("Questing Beast")

    beast.add_counters(Counter.MINUS_ONE, 2)

    assert (beast.power, beast.toughness) == (2, 2)


def test_a_counter_kind_is_any_name_at_all():
    """CR 122.1: counters are markers, and the set of kinds is open.

    Charge, ticket, rust, or a name a card invents this year - none of them is
    special to the engine, and only the kinds with rules attached behave
    differently.
    """
    scenario = board(battlefield=["Sol Ring"]).build()
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD)

    ring.add_counters(Counter.CHARGE, 2)
    ring.add_counters("shrapnel", 1)

    assert ring.counters == {"charge": 2, "shrapnel": 1}
    assert ring.counter_count("charge") == 2
    assert ring.counter_count("oil") == 0


def test_removing_more_counters_than_are_there_is_refused():
    """CR 118.3: nobody can pay a cost without the resources to pay it fully."""
    scenario = board(battlefield=["Walking Ballista"]).build()
    ballista = scenario.creature("Walking Ballista")
    ballista.add_counters(Counter.PLUS_ONE, 1)

    assert ballista.can_remove_counters("+1/+1", 1)
    assert not ballista.can_remove_counters("+1/+1", 2)
    with pytest.raises(ValueError, match="cannot remove 2"):
        ballista.remove_counters(Counter.PLUS_ONE, 2)


# --------------------------------------------------------------------------
# Annihilation (CR 704.5q, CR 122.3)
# --------------------------------------------------------------------------


def test_plus_and_minus_counters_annihilate_in_pairs():
    """CR 704.5q: N +1/+1 and N -1/-1 come off, N being the smaller pile.

    Basking Broodscale grows with +1/+1 counters; something else shrinking it
    does not cancel the growth arithmetically and then leave both piles sitting
    there. The state-based action removes them in pairs, so what is left is the
    difference and nothing else.
    """
    scenario = board(battlefield=["Basking Broodscale"]).build()
    broodscale = scenario.creature("Basking Broodscale")
    broodscale.add_counters(Counter.PLUS_ONE, 3)
    broodscale.add_counters(Counter.MINUS_ONE, 1)

    scenario.state_based_actions()

    assert broodscale.counters == {"+1/+1": 2}
    assert (broodscale.power, broodscale.toughness) == (4, 4)


def test_annihilation_can_clear_both_piles():
    """CR 704.5q with equal piles: nothing is left on the permanent at all."""
    scenario = board(battlefield=["Grizzly Bears"]).build()
    bears = scenario.creature("Grizzly Bears")
    bears.add_counters(Counter.PLUS_ONE, 2)
    bears.add_counters(Counter.MINUS_ONE, 2)

    assert (bears.power, bears.toughness) == (2, 2)
    scenario.state_based_actions()

    assert bears.counters == {}
    assert (bears.power, bears.toughness) == (2, 2)
    assert bears.zone is Zone.BATTLEFIELD


def test_annihilation_does_not_touch_other_counter_kinds():
    """CR 704.5q names +1/+1 and -1/-1 only; a charge counter is not a pair.

    Grizzly Bears rather than a 0/0, because a permanent whose counters were
    holding it alive is in the graveyard by the end of the check and takes its
    charge counter with it (CR 122.2).
    """
    scenario = board(battlefield=["Grizzly Bears"]).build()
    bears = scenario.creature("Grizzly Bears")
    bears.add_counters(Counter.PLUS_ONE, 1)
    bears.add_counters(Counter.MINUS_ONE, 1)
    bears.add_counters(Counter.CHARGE, 1)

    scenario.state_based_actions()

    assert bears.counters == {"charge": 1}


# --------------------------------------------------------------------------
# Dying to counters (CR 704.5f)
# --------------------------------------------------------------------------


def test_minus_one_counters_take_a_creature_to_zero_toughness():
    """CR 704.5f: "if a creature has toughness 0 or less, it's put into its
    owner's graveyard. Regeneration can't replace this event."

    Devoted Druid is the real card that does this to itself: its untap ability
    costs a -1/-1 counter, and the second one kills a printed 0/2.
    """
    scenario = board(battlefield=["Devoted Druid"]).build()
    druid = scenario.creature("Devoted Druid")

    druid.tap()
    druid.add_counters(Counter.MINUS_ONE, 1)  # "Put a -1/-1 counter on this: untap"
    druid.untap()
    assert (druid.power, druid.toughness) == (-1, 1)
    assert scenario.state_based_actions() == []

    druid.tap()
    druid.add_counters(Counter.MINUS_ONE, 1)
    druid.untap()

    assert druid.toughness == 0
    assert druid in scenario.state_based_actions()
    assert druid.zone is Zone.GRAVEYARD


def test_a_zero_zero_with_no_counters_left_dies():
    """CR 704.5f: Walking Ballista is a 0/0 the moment its counters run out.

    This is the interaction that makes the card a combo piece: the last +1/+1
    counter is both the ammunition and the reason it is still alive.
    """
    scenario = board(battlefield=["Walking Ballista"]).build()
    ballista = scenario.creature("Walking Ballista")
    ballista.add_counters(Counter.PLUS_ONE, 1)

    assert scenario.state_based_actions() == []

    ballista.remove_counters(Counter.PLUS_ONE, 1)

    assert ballista in scenario.state_based_actions()
    assert ballista.zone is Zone.GRAVEYARD


def test_annihilation_happens_before_a_creature_is_checked_for_death():
    """CR 704.3: every applicable state-based action happens as one event.

    Grizzly Bears with two of each is a 2/2 either way - annihilation is not
    what saves it - but after the check the counters are gone *and* it is still
    on the battlefield, which is only true if both actions were considered in
    the same pass rather than one of them destroying it first.
    """
    scenario = board(battlefield=["Grizzly Bears"]).build()
    bears = scenario.creature("Grizzly Bears")
    bears.add_counters(Counter.MINUS_ONE, 2)
    bears.add_counters(Counter.PLUS_ONE, 2)

    assert scenario.state_based_actions() == []

    assert bears.zone is Zone.BATTLEFIELD
    assert bears.counters == {}


# --------------------------------------------------------------------------
# Counters and zone changes (CR 122.2)
# --------------------------------------------------------------------------


def test_counters_cease_to_exist_when_a_permanent_changes_zones():
    """CR 122.2: "counters on an object are not retained if that object moves
    from one zone to another. The counters are not 'removed'; they simply cease
    to exist."

    A Hangarback Walker that dies with counters on it is a 0/0 card in the
    graveyard, not a 4/4 one, which is why returning it to play starts the
    whole business over.
    """
    scenario = board(battlefield=["Hangarback Walker"]).build()
    walker = scenario.creature("Hangarback Walker")
    walker.add_counters(Counter.PLUS_ONE, 4)

    scenario.game.destroy(walker)

    assert walker.zone is Zone.GRAVEYARD
    assert walker.counters == {}
    assert (walker.power, walker.toughness) == (0, 0)


def test_counters_do_not_come_back_when_the_card_returns():
    """CR 122.2 again: a new object, with none of the old object's counters."""
    scenario = board(battlefield=["Walking Ballista"]).build()
    ballista = scenario.creature("Walking Ballista")
    ballista.add_counters(Counter.PLUS_ONE, 2)

    scenario.game.destroy(ballista)
    scenario.player().move(ballista, Zone.HAND)

    assert ballista.counters == {}


# --------------------------------------------------------------------------
# Counters in the layer system (CR 613.4c)
# --------------------------------------------------------------------------


def test_a_lord_and_the_permanents_own_counters_both_apply_in_7c():
    """CR 613.4c: "effects **and counters** that modify power and/or toughness".

    Glorious Anthem's +1/+1 is a 7c effect and the counters are 7c too. Kalonian
    Hydra is printed 0/0 and is a creature at all only because of the four
    +1/+1 counters it enters with, so two counters and an Anthem make it 3/3:
    nothing printed, plus two from counters, plus one from the lord.

    The counters are read off the permanent - `compute_board` is not told about
    them separately.
    """
    scenario = board(battlefield=["Kalonian Hydra", "Glorious Anthem"]).build()
    hydra = scenario.creature("Kalonian Hydra")
    hydra.add_counters(Counter.PLUS_ONE, 2)
    permanents = scenario.game.battlefield

    computed = compute_board(permanents, static_effects(permanents))

    assert computed.of(hydra).power_toughness == (3, 3)
    assert computed.of(hydra).counters == {"+1/+1": 2}
    assert any("from counters" in applied for applied in computed.journal.applied)


def test_setting_base_power_still_beats_counters():
    """CR 613.4b before CR 613.4c, whatever else is going on.

    Humility sets base power and toughness to 1/1 in 7b; the counters modify in
    7c and so land on top of the 1/1, not under it. A Hangarback Walker with
    three counters is a 4/4 under Humility, not a 1/1 - the classic answer that
    trips people up because they expect Humility to win outright.
    """
    scenario = board(battlefield=["Hangarback Walker", "Humility"]).build()
    walker = scenario.creature("Hangarback Walker")
    walker.add_counters(Counter.PLUS_ONE, 3)
    permanents = scenario.game.battlefield

    computed = compute_board(permanents, static_effects(permanents))

    assert computed.of(walker).power_toughness == (4, 4)


def test_the_layer_engine_never_writes_counters_back():
    """CR 613.5: the layer system computes, it does not store.

    Asking for the board must not annihilate anything or move a counter - the
    state-based action is the only thing that changes what is on a permanent.
    """
    scenario = board(battlefield=["Grizzly Bears"]).build()
    bears = scenario.creature("Grizzly Bears")
    bears.add_counters(Counter.PLUS_ONE, 2)
    bears.add_counters(Counter.MINUS_ONE, 1)

    computed = compute_board([bears])

    assert computed.of(bears).power_toughness == (3, 3)
    assert bears.counters == {"+1/+1": 2, "-1/-1": 1}


# --------------------------------------------------------------------------
# Loyalty (CR 306, CR 704.5i)
# --------------------------------------------------------------------------


def test_a_planeswalker_enters_with_its_printed_loyalty_in_counters():
    """CR 306.5b: a planeswalker has the intrinsic ability "this permanent
    enters with a number of loyalty counters on it equal to its printed loyalty
    number", and CR 306.5c makes those counters its loyalty.
    """
    scenario = board(battlefield=["Tamiyo, Compleated Sage"]).build()
    tamiyo = scenario.find("Tamiyo, Compleated Sage", Zone.BATTLEFIELD)

    assert tamiyo.counter_count(Counter.LOYALTY) == 5
    assert tamiyo.loyalty == 5


def test_a_planeswalker_at_zero_loyalty_is_put_into_the_graveyard():
    """CR 704.5i: "if a planeswalker has loyalty 0, it's put into its owner's
    graveyard." CR 306.9 says the same thing from the planeswalker's side.

    Loyalty is counters, so activating a minus ability, or damage removing
    loyalty counters (CR 120.3c), is the same event as far as this rule is
    concerned.
    """
    scenario = board(battlefield=["Tamiyo, Compleated Sage"]).build()
    tamiyo = scenario.find("Tamiyo, Compleated Sage", Zone.BATTLEFIELD)

    tamiyo.remove_counters(Counter.LOYALTY, 4)
    assert scenario.state_based_actions() == []
    assert tamiyo.zone is Zone.BATTLEFIELD

    tamiyo.remove_counters(Counter.LOYALTY, 1)

    assert tamiyo.has_zero_loyalty
    assert tamiyo in scenario.state_based_actions()
    assert tamiyo.zone is Zone.GRAVEYARD


def test_loyalty_off_the_battlefield_is_the_printed_number():
    """CR 306.5a: "the loyalty of a planeswalker card not on the battlefield is
    equal to the number printed in its lower right corner" - it has no counters
    there (CR 122.2), and the printing is what a spell in hand shows.
    """
    scenario = board(hand=["Tamiyo, Compleated Sage"]).build()
    tamiyo = scenario.find("Tamiyo, Compleated Sage", Zone.HAND)

    assert tamiyo.counters == {}
    assert tamiyo.loyalty == 5


def test_a_creature_has_no_loyalty():
    """CR 306.5 is about planeswalkers; a creature with counters has none."""
    scenario = board(battlefield=["Grizzly Bears"]).build()
    bears = scenario.creature("Grizzly Bears")

    assert bears.loyalty is None
    assert not bears.has_zero_loyalty


# --------------------------------------------------------------------------
# Counters on players (CR 122.1f, CR 704.5c)
# --------------------------------------------------------------------------


def test_a_player_carries_counters_of_their_own():
    """CR 122.1: a counter is a marker on "an object or player".

    Poison has a rule (CR 122.1f); energy is what `{E}` pays with (CR 107.14);
    experience is a count and nothing more.
    """
    scenario = board().build()
    alice = scenario.player("alice")

    alice.add_counters(Counter.POISON, 3)
    alice.add_counters(Counter.ENERGY, 2)
    alice.add_counters(Counter.EXPERIENCE)

    assert (alice.poison, alice.energy, alice.experience) == (3, 2, 1)
    assert alice.is_poisoned
    assert not alice.loses_to_poison


def test_paying_energy_removes_counters_from_the_player():
    """CR 107.14: "to pay {E}, a player removes one energy counter from
    themselves." Spending more than they have is refused (CR 118.3).
    """
    scenario = board().build()
    alice = scenario.player("alice")
    alice.add_counters(Counter.ENERGY, 2)

    alice.remove_counters(Counter.ENERGY, 2)

    assert alice.energy == 0
    with pytest.raises(ValueError, match="cannot remove 1 energy"):
        alice.remove_counters(Counter.ENERGY)


def test_ten_poison_counters_is_the_losing_threshold():
    """CR 704.5c: "if a player has ten or more poison counters, that player
    loses the game." CR 122.1f states it too, and CR 104.3d has it happen the
    next time a player would receive priority.
    """
    scenario = board().build()
    alice = scenario.player("alice")

    alice.add_counters(Counter.POISON, POISON_TO_LOSE - 1)
    assert not alice.loses_to_poison

    alice.add_counters(Counter.POISON)
    assert alice.loses_to_poison


def test_a_poisoned_player_actually_loses_the_game():
    """CR 704.5c as a state-based action, not just as a threshold.

    `Player.loses_to_poison` is the rule; nothing in `Game` asks it yet.
    """
    scenario = board().player("bob").build()
    alice = scenario.player("alice")
    alice.add_counters(Counter.POISON, POISON_TO_LOSE)

    scenario.state_based_actions()

    assert "alice" in scenario.game.losers


# --------------------------------------------------------------------------
# Counters as a cost (CR 118.3)
# --------------------------------------------------------------------------


def test_removing_counters_pays_a_cost():
    """CR 118.3: a cost that removes counters is payable exactly when they are
    there. Walking Ballista's "remove a +1/+1 counter from this creature: it
    deals 1 damage to any target" is the cost in question.
    """
    from magic_cards_model.machines.cost import remove_counters_cost

    scenario = board(battlefield=["Walking Ballista"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ballista = scenario.creature("Walking Ballista")
    ballista.add_counters(Counter.PLUS_ONE, 2)

    component = remove_counters_cost(ballista, 1, payer="alice")
    assert component.why_not(scenario.game) is None
    component.pay(scenario.game)

    assert ballista.counter_count(Counter.PLUS_ONE) == 1
