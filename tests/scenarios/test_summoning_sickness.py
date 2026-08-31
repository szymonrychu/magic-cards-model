"""Summoning sickness: how long a creature has been here (CR 302.6, 508.1a).

Two separate rules share one informal name. A creature cannot be declared as an
attacker unless it has been under its controller's control continuously since
their most recent turn began (CR 508.1a), and it cannot activate an ability
with `{T}` or `{Q}` in its cost under the same condition (CR 302.6, 602.5a).
Haste turns both off (CR 702.10b, 702.10c).

The model tracks this as `CardState.summoning_sick`, set when the card arrives
on the battlefield and cleared for the active player as their turn begins.
`CardState.is_summoning_sick` is the rule's answer rather than the raw fact:
the flag only matters for a creature (CR 302.6), so a land reports False even
on the turn it arrives while keeping its flag, because a permanent that
becomes a creature later in the turn is restricted from the moment it entered.
"""

import pytest

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def alice_casting_a_creature(name: str, *lands: str) -> Scenario:
    """Both players get a library, so a scenario may advance whole turns.

    The engine draws in the draw step (CR 703.4d), and a player who cannot
    draw loses (CR 704.5b) - so an empty library would end the game rather
    than test summoning sickness.
    """
    return (
        Scenario()
        .player("alice", hand=[name], battlefield=list(lands), library=["Forest"] * 5)
        .player("bob", library=["Forest"] * 5)
    )


def test_a_creature_that_arrived_this_turn_cannot_attack():
    """CR 508.1a: it has not been here since the turn began."""
    scenario = alice_casting_a_creature("Grizzly Bears", "Forest", "Forest").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    forests = scenario.untapped_sources("Forest", "Forest")
    bears = scenario.cast_and_resolve("Grizzly Bears", *forests)
    assert bears.summoning_sick

    scenario.advance()  # beginning of combat
    scenario.advance()  # declare attackers

    assert not scenario.can_attack(bears)
    with pytest.raises(ValueError, match="summoning sickness"):
        scenario.attack_with(bears)


def test_haste_lets_a_creature_attack_the_turn_it_arrives():
    """CR 702.10b: haste ignores the "since their most recent turn began" clause."""
    scenario = alice_casting_a_creature("Raging Goblin", "Mountain").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    (mountain,) = scenario.untapped_sources("Mountain")
    goblin = scenario.cast_and_resolve("Raging Goblin", mountain)
    assert goblin.summoning_sick, "haste does not stop it being new, only stop it mattering"

    scenario.advance()
    scenario.advance()

    scenario.attack_with(goblin)
    assert scenario.attackers() == [goblin]


def test_a_creature_already_on_the_battlefield_loses_sickness_as_the_turn_begins():
    """CR 302.6: control since the turn began is exactly what the untap step confirms."""
    scenario = Scenario().player("alice", battlefield=["Grizzly Bears"]).player("bob").build()
    bears = scenario.creature("Grizzly Bears")
    assert bears.summoning_sick, "nothing has told the game a turn began yet"

    scenario.start_at(Step.UPKEEP)

    assert not bears.summoning_sick


def test_the_defending_players_creatures_stay_sick_through_your_turn():
    """It is *their* most recent turn that matters, not the current one."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears"])
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)

    assert not scenario.creature("Grizzly Bears").summoning_sick
    assert scenario.creature("Hill Giant", "bob").summoning_sick


def test_a_creature_can_attack_on_its_controllers_next_turn():
    """The sickness clears when the turn rolls round, not when the creature is untapped."""
    scenario = alice_casting_a_creature("Grizzly Bears", "Forest", "Forest").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forests = scenario.untapped_sources("Forest", "Forest")
    bears = scenario.cast_and_resolve("Grizzly Bears", *forests)

    while not (scenario.turn.active_player == "alice" and scenario.turn.turn_number == 2):
        scenario.advance()

    assert not bears.summoning_sick
    scenario.turn.advance_to(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    assert scenario.attackers() == [bears]


def test_a_summoning_sick_creature_cannot_activate_a_tap_ability():
    """CR 302.6: the `{T}` half of the restriction, separate from attacking."""
    scenario = alice_casting_a_creature("Llanowar Elves", "Forest").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    (forest,) = scenario.untapped_sources("Forest")
    elves = scenario.cast_and_resolve("Llanowar Elves", forest)

    assert not scenario.game.can_activate_tap_ability(elves)


def test_a_land_may_tap_the_turn_it_is_played():
    """CR 302.6 is about creatures only - a land taps the moment it arrives."""
    scenario = Scenario().player("alice", hand=["Forest"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    forest = scenario.play_land("Forest")

    assert forest.summoning_sick, "it did arrive this turn"
    assert scenario.game.can_activate_tap_ability(forest)


def test_haste_allows_a_tap_ability_the_turn_it_arrives():
    """CR 702.10c: haste covers activated abilities as well as attacking."""
    scenario = alice_casting_a_creature("Raging Goblin", "Mountain").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    (mountain,) = scenario.untapped_sources("Mountain")
    goblin = scenario.cast_and_resolve("Raging Goblin", mountain)

    assert scenario.game.can_activate_tap_ability(goblin)


def test_paying_a_cost_refuses_to_tap_a_summoning_sick_mana_creature():
    """A Llanowar Elves cast this turn should not be able to pay for anything.

    Its `{G}` alone covers the second Elves' `{G}` cost, so the only thing that
    should stop the payment is CR 302.6.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Llanowar Elves", "Llanowar Elves"], battlefield=["Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (forest,) = scenario.untapped_sources("Forest")
    elves = scenario.cast_and_resolve("Llanowar Elves", forest)
    assert not scenario.game.can_activate_tap_ability(elves)

    casting = scenario.cast("Llanowar Elves")
    payment = casting.begin_paying()
    with pytest.raises(ValueError):
        scenario.pay_with(payment, elves)


# -- the rule's answer, not the raw flag (CR 302.6) -------------------------


def test_a_land_is_not_summoning_sick_even_the_turn_it_arrives():
    """CR 302.6 restricts "a creature's activated ability with the tap symbol";
    a land keeps its raw flag but the restriction does not apply to it."""
    scenario = Scenario().player("alice", hand=["Forest"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    forest = scenario.play_land("Forest")

    assert forest.summoning_sick, "it did arrive this turn"
    assert not forest.is_summoning_sick()


def test_a_freshly_cast_creature_is_summoning_sick():
    """The raw fact and the rule agree for a creature (CR 302.6, 508.1a)."""
    scenario = alice_casting_a_creature("Grizzly Bears", "Forest", "Forest").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    forests = scenario.untapped_sources("Forest", "Forest")
    bears = scenario.cast_and_resolve("Grizzly Bears", *forests)

    assert bears.summoning_sick
    assert bears.is_summoning_sick()


def test_a_creature_stops_being_summoning_sick_once_its_turn_begins():
    """CR 302.6: "continuously since their most recent turn began" - a new turn
    of its controller's is exactly that."""
    scenario = alice_casting_a_creature("Grizzly Bears", "Forest", "Forest").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forests = scenario.untapped_sources("Forest", "Forest")
    bears = scenario.cast_and_resolve("Grizzly Bears", *forests)
    assert bears.is_summoning_sick()

    while not (scenario.turn.active_player == "alice" and scenario.turn.turn_number == 2):
        scenario.advance()

    assert not bears.summoning_sick
    assert not bears.is_summoning_sick()
