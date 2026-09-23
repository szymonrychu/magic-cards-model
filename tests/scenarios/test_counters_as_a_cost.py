"""Counters as an activation cost (CR 118.3, CR 122.1, CR 122.6).

`test_counters.py` covers counters as a mechanic - what they do to power and
toughness, annihilation, the layer system. This file is the one place a
counter is not just sitting on a permanent but is being *spent*: "Put a -1/-1
counter on this creature:" (Devoted Druid) and "Remove a +1/+1 counter from
this creature:" (Walking Ballista) as the whole cost of an activated ability.

Every CR number here was looked up with `knowledge_search(type="rules")` in
the session that wrote the file:

- **CR 118.3** - "A player can't pay a cost without having the necessary
  resources to pay it fully" - the same rule that refuses an already-tapped
  permanent refuses removing a counter that is not there.
- **CR 122.1, 122.6** - what a counter is, and that "putting counters on an
  object" means while it is on the battlefield.
- **CR 602.2b** - activating an ability follows the same process as casting a
  spell (CR 601.2b-i): the cost is paid as part of activation, before the
  ability - now on the stack - ever resolves.
- **CR 613.4c** - counters modify power and toughness in layer 7c, alongside
  any static effect (an anthem) also modifying it there.
- **CR 704.5f** - a creature with toughness 0 or less goes to the graveyard,
  judged against the fully computed toughness (CR 613.5).
- **CR 704.3 / 117.5** - state-based actions are checked whenever a player
  would receive priority, not the instant a cost is paid - so a permanent can
  sit at 0 toughness for a moment before anything acts on it.
- **CR 704.5q / 122.3** - +1/+1 and -1/-1 counters annihilate as a state-based
  action, N pairs at a time.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.layers import compute_board, static_effects
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def board(**kwargs) -> Scenario:
    """One player, no library, ready to build (see `test_counters.board`)."""
    return Scenario().manual_turn_based_actions().player("alice", **kwargs)


# --------------------------------------------------------------------------
# Removing counters as a cost (Walking Ballista)
# --------------------------------------------------------------------------


def test_removing_a_counter_pays_for_the_ability():
    """The happy path: a counter is there, so the cost can be paid.

    Walking Ballista's "Remove a +1/+1 counter from this creature: It deals 1
    damage to any target." The counter comes off as the ability is activated,
    which is why it is gone immediately - before the damage ability has even
    resolved (CR 602.2b).
    """
    scenario = board(battlefield=["Walking Ballista"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ballista = scenario.creature("Walking Ballista")
    ballista.add_counters(Counter.PLUS_ONE, 2)

    scenario.activate(ballista, index=1, targets=["alice"])

    assert ballista.counter_count(Counter.PLUS_ONE) == 1


def test_removing_a_counter_that_is_not_there_is_refused():
    """CR 118.3: no +1/+1 counters at all means the cost cannot be paid, so
    the ability cannot even be activated - not silently activated for free.
    """
    scenario = board(battlefield=["Walking Ballista"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ballista = scenario.creature("Walking Ballista")
    assert ballista.counter_count(Counter.PLUS_ONE) == 0

    with pytest.raises(ValueError, match="counter"):
        scenario.activate(ballista, index=1, targets=["alice"])

    # Refused, not partially paid: nothing changed.
    assert ballista.counter_count(Counter.PLUS_ONE) == 0
    assert ballista.zone is Zone.BATTLEFIELD


def test_removing_the_last_counter_is_still_legal():
    """CR 118.3 only refuses a shortfall - one counter for a cost of one is a
    full payment, not a partial one, even though it leaves none behind.
    """
    scenario = board(battlefield=["Walking Ballista"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ballista = scenario.creature("Walking Ballista")
    ballista.add_counters(Counter.PLUS_ONE, 1)

    scenario.activate(ballista, index=1, targets=["alice"])

    assert ballista.counter_count(Counter.PLUS_ONE) == 0


# --------------------------------------------------------------------------
# Putting a counter on as a cost (Devoted Druid), and its loop
# --------------------------------------------------------------------------


def test_putting_the_counter_on_happens_at_payment_time_not_resolution():
    """CR 602.2b: the cost is paid as the ability is activated, before the
    ability - now sitting on the stack - has resolved at all.

    Devoted Druid's "Put a -1/-1 counter on this creature: Untap this
    creature." is not a mana ability (untapping adds no mana, CR 605.1a), so it
    goes on the stack rather than resolving immediately. The counter is
    already there the moment `activate` returns, whatever the untap effect
    itself does or does not do.
    """
    scenario = board(battlefield=["Devoted Druid"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    druid = scenario.creature("Devoted Druid")
    assert druid.counter_count(Counter.MINUS_ONE) == 0

    on_stack = scenario.activate(druid, index=1)

    assert on_stack is not None  # went on the stack, unlike a mana ability
    assert druid.counter_count(Counter.MINUS_ONE) == 1


def test_the_druid_survives_its_first_counter():
    """Devoted Druid is printed 0/2 (verified with `resolve_cards`, not
    memory - it is easy to misremember as 2/2 from the vanilla-stats era).
    A -1/-1 counter subtracts from power too (CR 122.1a): one counter takes it
    to -1/1 - alive, CR 704.5f does nothing yet.
    """
    scenario = board(battlefield=["Devoted Druid"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    druid = scenario.creature("Devoted Druid")
    assert (druid.power, druid.toughness) == (0, 2)

    scenario.activate(druid, index=1)

    assert (druid.power, druid.toughness) == (-1, 1)
    scenario.state_based_actions()
    assert druid.zone is Zone.BATTLEFIELD


def test_a_second_activation_pays_the_cost_that_kills_it():
    """The well-known interaction, without Vizier of Remedies to stop it:
    Devoted Druid can only untap itself once before its own cost's second
    counter takes its toughness to 0 (CR 704.5f) - 0/2, then -1/1, then -2/0.

    The second activation's cost is paid in full (CR 118.3 asks nothing about
    what happens *after* a cost is paid, only whether it can be paid right
    now, and a second -1/-1 counter is exactly as payable as the first).
    Nothing here calls `state_based_actions()` by hand: `Game.retain_priority`
    - which every `activate()` call ends with (CR 117.3c: the activator keeps
    priority) - already checks CR 704.5f itself (CR 704.3/117.5, a check is
    due whenever a player would receive priority), so the creature is already
    in the graveyard by the time `activate()` returns from paying the second
    cost.
    """
    scenario = board(battlefield=["Devoted Druid"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    druid = scenario.creature("Devoted Druid")

    scenario.activate(druid, index=1)
    assert druid.zone is Zone.BATTLEFIELD
    assert (druid.power, druid.toughness) == (-1, 1)

    scenario.activate(druid, index=1)

    assert druid.zone is Zone.GRAVEYARD
    # CR 603.10a: last known information survives the state-based action that
    # sent it to the graveyard, so both counters the cost placed still show.
    assert druid.last_known_counters[Counter.MINUS_ONE] == 2


def test_once_dead_a_third_activation_has_no_permanent_to_pay_with():
    """CR 602.5/602.1a: only a permanent on the battlefield has this ability
    to activate at all - `why_cannot_activate` refuses it outright once
    Devoted Druid is in the graveyard, before the cost is even considered.
    """
    scenario = board(battlefield=["Devoted Druid"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    druid = scenario.creature("Devoted Druid")
    scenario.activate(druid, index=1)
    scenario.activate(druid, index=1)
    scenario.state_based_actions()
    assert druid.zone is Zone.GRAVEYARD

    assert scenario.why_cannot_activate(druid, index=1) is not None
    with pytest.raises(ValueError):
        scenario.activate(druid, index=1)


def test_a_counter_cost_still_pays_when_toughness_is_boosted_by_a_static_effect():
    """CR 613.4c: an anthem's +N/+N and a counter's own -1/-1 both apply in
    layer 7c - together, not one overriding the other - so Glorious Anthem's
    "Creatures you control get +1/+1." keeps Devoted Druid alive for one more
    activation than it would manage alone (two successful untaps instead of
    one before the cost that kills it).

    Computed P/T is base (0/2) plus the anthem (+1/+1) plus n counters
    (-n/-n) = (1-n, 3-n). n=1 is 0/2 (alive), n=2 is -1/1 (alive - the
    undecorated Druid was already dead at n=2), n=3 is -2/0 and CR 704.5f
    takes it. The point: the cost's own payability never looks at toughness
    at all (CR 118.3 only asks whether the counters removed/placed are
    there), so the cost keeps being paid right up to the state-based action
    that ends the creature - the anthem changes *when* death happens, never
    *whether* the cost can be paid.
    """
    scenario = board(battlefield=["Devoted Druid", "Glorious Anthem"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    druid = scenario.creature("Devoted Druid")

    def computed_pt() -> tuple[int, int]:
        permanents = scenario.game.battlefield
        return compute_board(permanents, static_effects(permanents)).of(druid).power_toughness

    assert computed_pt() == (1, 3)

    scenario.activate(druid, index=1)
    assert druid.zone is Zone.BATTLEFIELD
    assert computed_pt() == (0, 2)

    scenario.activate(druid, index=1)
    assert druid.zone is Zone.BATTLEFIELD  # the anthem bought it one more
    assert computed_pt() == (-1, 1)

    scenario.activate(druid, index=1)
    assert druid.zone is Zone.GRAVEYARD


# --------------------------------------------------------------------------
# +1/+1 and -1/-1 annihilating a counter cost just placed (CR 704.5q, 122.3)
# --------------------------------------------------------------------------


def test_a_placed_minus_one_counter_annihilates_an_existing_plus_one_counter():
    """A permanent that already carries a +1/+1 counter and then pays a cost
    that puts a -1/-1 counter on itself ends up with neither, not both -
    CR 704.5q's pairwise removal is a state-based action, so it is not part of
    paying the cost itself (CR 118.3 never reads it), but CR 704.3 checks
    whenever a player *would get priority*, and CR 117.3c makes the activating
    player receive priority right back the moment activation finishes
    (`Game.retain_priority`'s own docstring cites both) - so by the time
    `activate` returns, the pair is already gone, with no separate call
    needed to see it.

    Devoted Druid has no way to gain a +1/+1 counter printed on itself, so
    this drives the annihilation directly the way `test_counters.py` does,
    confirming the *cost*'s own counter (not just an effect's) is ordinary
    enough to annihilate like any other.
    """
    scenario = board(battlefield=["Devoted Druid"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    druid = scenario.creature("Devoted Druid")
    druid.add_counters(Counter.PLUS_ONE, 1)

    scenario.activate(druid, index=1)

    assert druid.counter_count(Counter.MINUS_ONE) == 0
    assert druid.counter_count(Counter.PLUS_ONE) == 0
    # Annihilated back to 0/2 base, one pair of counters removed rather than
    # kept as a net -0/-0 sitting on the permanent (CR 122.3's own wording).
    assert (druid.power, druid.toughness) == (0, 2)
    assert druid.zone is Zone.BATTLEFIELD


# --------------------------------------------------------------------------
# The rewind (CR 733.1) - cancelling a payment puts the counter back
# --------------------------------------------------------------------------


def test_a_cancelled_payment_leaves_the_counter_where_it_was():
    """CR 733.1: an action that cannot be completed legally is reversed in
    full, any payments already made included. Paying the counter component
    and then cancelling the whole `CostPayment` (rather than finishing it)
    must put the counter back - the exact rewind bug `docs/engine-coverage.md`
    used to flag: `CostComponent._remember` snapshots by reference, so a
    payment that mutates `counters` in place would corrupt its own snapshot.
    `_remember_counters`'s deep copy is what this test would catch failing.
    """
    scenario = board(battlefield=["Walking Ballista"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ballista = scenario.creature("Walking Ballista")
    ballista.add_counters(Counter.PLUS_ONE, 2)

    payment = scenario.game.begin_activating(ballista, index=1, controller="alice")
    payment.pay()
    assert ballista.counter_count(Counter.PLUS_ONE) == 1

    payment.rewind()

    assert ballista.counter_count(Counter.PLUS_ONE) == 2
