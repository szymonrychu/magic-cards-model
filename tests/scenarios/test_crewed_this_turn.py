"""A targeting restriction over this turn's own crew history (CR 702.122b):
"Whenever this Vehicle attacks, put a +1/+1 counter on target creature that
crewed it this turn. Then if that creature is a Mutant, Ninja, or Turtle,
double the number of +1/+1 counters on it." (Turtle Van).

"That crewed it this turn" is `machines/targeting.TargetRequirement.must_
have_crewed_source_this_turn`, read off `Game.turn_history`'s own "crewed"
entries (`machines/conditions/history._record_crew`/`_bind_crew`, which
already populate `related_id` with the Vehicle crewed and `object_id` with
the creature that crewed it, for every crew activation in the pool - nothing
new had to be tracked for this restriction, only read). The doubling half
reuses the identical CR 701.10e primitive sos-T3's Growth Curve reader
(`machines/counter_effects._put_counter_then_double_on_that`) already
established, gated on a subtype check instead of running unconditionally.

Getaway Car is the off-pool generality proof for the *targeting restriction*
on its own: a different Vehicle, a different consequence ("return ... to its
owner's hand" rather than "put a counter on ... then maybe double"), and an
"up to one" optional count rather than a mandatory one target.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 702.122a/702.122b** - crew's own activated ability, and a creature
  "crews a Vehicle" when tapped to pay that cost.
- **CR 115.1** - a target is declared as the spell or ability that names it
  goes on the stack (CR 603.3d for a triggered ability).
- **CR 608.2b** - a target rechecked as the ability resolves.
- **CR 701.10e** - doubling the number of a kind of counters on a permanent.
- **CR 205.3m** - creature types (Mutant, Ninja, Turtle).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import crew_activation
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def crew(scenario, vehicle, *creatures, username="alice"):
    """Activate a Vehicle's crew ability, pay it, and let it resolve - the
    identical helper `tests/scenarios/test_crew.py` already keeps."""
    activation = crew_activation(scenario.game, vehicle, list(creatures), username)
    activation.begin_paying()
    activation.payment.pay()
    activation.activate()
    activation.resolve()
    return activation


def _board(*extra: str):
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Turtle Van", "Leonardo, Big Brother", "Grizzly Bears", *extra],
        )
        .player("bob", battlefield=["Grizzly Bears"])
    )


def test_the_creature_that_crewed_it_gets_a_counter_and_doubles_if_a_mutant_ninja_or_turtle():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    van = scenario.find("Turtle Van", Zone.BATTLEFIELD)
    leonardo = scenario.find("Leonardo, Big Brother", Zone.BATTLEFIELD)
    crew(scenario, van, leonardo)

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.will_choose_targets(leonardo, source="Turtle Van")
    scenario.attack_with(van)

    assert scenario.stack_names() == ["Turtle Van's triggered ability"]
    scenario.resolve_top()

    # Leonardo, Big Brother is a Mutant Ninja Turtle: the +1/+1 counter this
    # ability just placed doubles (CR 701.10e), 1 -> 2.
    assert leonardo.counter_count(Counter.PLUS_ONE) == 2


def test_a_creature_that_crewed_it_but_is_not_a_mutant_ninja_or_turtle_does_not_double():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    van = scenario.find("Turtle Van", Zone.BATTLEFIELD)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    crew(scenario, van, bears)

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.will_choose_targets(bears, source="Turtle Van")
    scenario.attack_with(van)
    scenario.resolve_top()

    assert bears.counter_count(Counter.PLUS_ONE) == 1


def test_a_creature_that_did_not_crew_it_this_turn_is_not_a_legal_target():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    van = scenario.find("Turtle Van", Zone.BATTLEFIELD)
    leonardo = scenario.find("Leonardo, Big Brother", Zone.BATTLEFIELD)
    bystander = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    crew(scenario, van, leonardo)

    scenario.start_at(Step.DECLARE_ATTACKERS)
    with pytest.raises(ValueError):
        scenario.will_choose_targets(bystander, source="Turtle Van")
        scenario.attack_with(van)


def test_a_creature_that_crewed_a_different_vehicle_is_not_a_legal_target():
    """ "it" is *this* Vehicle - CR 702.122c's own Vehicle-specific "crewed
    by", not any Vehicle the creature happened to tap for."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Turtle Van", "Getaway Car", "Leonardo, Big Brother"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    van = scenario.find("Turtle Van", Zone.BATTLEFIELD)
    dreadnought = scenario.find("Getaway Car", Zone.BATTLEFIELD)
    leonardo = scenario.find("Leonardo, Big Brother", Zone.BATTLEFIELD)
    # Leonardo crews the *other* Vehicle (Getaway Car, also Crew 1), never
    # Turtle Van itself.
    crew(scenario, dreadnought, leonardo)
    # Turtle Van still needs a real crewer of its own to become a creature.
    leonardo.untap()
    crew(scenario, van, leonardo)

    scenario.start_at(Step.DECLARE_ATTACKERS)
    with pytest.raises(ValueError):
        scenario.will_choose_targets(dreadnought, source="Turtle Van")
        scenario.attack_with(van)


def test_getaway_car_off_pool_proof_returns_only_the_creature_that_crewed_it():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Getaway Car", "Grizzly Bears", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    car = scenario.find("Getaway Car", Zone.BATTLEFIELD)
    crewer, bystander = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="alice")
    crew(scenario, car, crewer)

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.will_choose_targets(crewer, source="Getaway Car")
    scenario.attack_with(car)

    assert scenario.stack_names() == ["Getaway Car's triggered ability"]
    scenario.resolve_top()

    assert crewer.zone is Zone.HAND
    assert bystander.zone is Zone.BATTLEFIELD
