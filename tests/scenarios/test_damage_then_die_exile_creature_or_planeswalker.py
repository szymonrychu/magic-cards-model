"""Scenario: "`<this spell>` deals N damage to target creature or
planeswalker. If that creature or planeswalker would die this turn, exile it
instead." - the two-noun anaphor ("that creature or planeswalker") naming the
one target a "creature or planeswalker" phrase chose.

- **Bouncer's Beatdown** - X damage, "where X is the greatest power among
  creatures you control".
- **Scorching Dragonfire** - a fixed 3.
- Essence Burn's "If that permanent would die this turn ..." and Combustion
  Technique's "If it would die ..." are the one-word anaphors this shares a
  reader with (`test_essence_burn` and friends).

Rules, each read with `mise run rules:find` in the session that wrote this:

- **CR 614.1a** - "instead" makes it a replacement effect.
- **CR 700.4** - "dies" means put into a graveyard from the battlefield, which
  a planeswalker with no loyalty counters does too (CR 704.5i).
- **CR 704.5g** - lethal damage destroys a creature as a state-based action;
  **CR 120.3c** - damage to a planeswalker removes that many loyalty counters.
- **CR 514.2** - "this turn" effects end in the cleanup step.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card
from tests.scenarios.harness import Scenario

BEATDOWN = "Bouncer's Beatdown"
DRAGONFIRE = "Scorching Dragonfire"


def test_both_printings_are_fully_handled():
    for name in (BEATDOWN, DRAGONFIRE):
        bad = [c for c in card_support(card(name)).clauses if c.outcome != "handled"]
        assert not bad, (name, bad)


def _beatdown(alice_creatures=("Craw Wurm",), bob=("Grizzly Bears",), hand=()) -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest"] * 3,
            hand=[BEATDOWN, *hand],
            battlefield=["Forest", "Forest", "Forest", "Mountain", *alice_creatures],
        )
        .player("bob", library=["Swamp"] * 3, battlefield=list(bob))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_beatdown(scenario: Scenario, target) -> None:
    forests = scenario.untapped_sources("Forest", "Forest", "Forest", username="alice")
    scenario.cast_and_resolve(BEATDOWN, *forests, targets=[target])


def test_x_is_the_greatest_power_and_the_dead_creature_is_exiled():
    scenario = _beatdown(alice_creatures=("Craw Wurm", "Grizzly Bears"), bob=("Serra Angel",))
    angel = scenario.creature("Serra Angel", "bob")

    _cast_beatdown(scenario, angel)

    assert angel.zone is Zone.EXILE, "6 damage (Craw Wurm's power) kills a 4/4"


def test_a_planeswalker_that_would_die_is_exiled_too():
    scenario = _beatdown(bob=("Liliana of the Veil",))
    liliana = scenario.find("Liliana of the Veil", Zone.BATTLEFIELD, "bob")

    _cast_beatdown(scenario, liliana)
    scenario.state_based_actions()

    assert liliana.zone is Zone.EXILE


def test_nonlethal_damage_then_a_later_death_this_turn_is_still_exiled():
    """The replacement lasts the whole turn, not just the spell's own damage."""
    scenario = _beatdown(alice_creatures=("Grizzly Bears",), bob=("Serra Angel",), hand=["Shock"])
    angel = scenario.creature("Serra Angel", "bob")
    _cast_beatdown(scenario, angel)
    assert angel.zone is Zone.BATTLEFIELD and angel.damage == 2

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Shock", mountain, targets=[angel])

    assert angel.zone is Zone.EXILE


def test_no_creatures_means_zero_damage_but_the_replacement_still_applies():
    """X is 0 with no creature to measure; the spell still resolves and the
    second sentence still sets up its replacement for that permanent."""
    scenario = _beatdown(alice_creatures=(), bob=("Grizzly Bears",), hand=["Shock"])
    bears = scenario.creature("Grizzly Bears", "bob")
    _cast_beatdown(scenario, bears)
    assert bears.damage == 0

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Shock", mountain, targets=[bears])

    assert bears.zone is Zone.EXILE


def test_the_replacement_does_not_reach_other_creatures():
    scenario = _beatdown(bob=("Serra Angel", "Grizzly Bears"), hand=["Shock"])
    angel = scenario.creature("Serra Angel", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    _cast_beatdown(scenario, angel)

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    scenario.cast_and_resolve("Shock", mountain, targets=[bears])

    assert angel.zone is Zone.EXILE
    assert bears.zone is Zone.GRAVEYARD


# -- second printing: Scorching Dragonfire -------------------------------------


def _dragonfire(*bob: str) -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Mountain"] * 3,
            hand=[DRAGONFIRE],
            battlefield=["Mountain", "Mountain"],
        )
        .player("bob", library=["Swamp"] * 3, battlefield=list(bob))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_dragonfire_exiles_the_creature_it_kills():
    scenario = _dragonfire("Grizzly Bears")
    bears = scenario.creature("Grizzly Bears", "bob")
    mountains = scenario.untapped_sources("Mountain", "Mountain", username="alice")

    scenario.cast_and_resolve(DRAGONFIRE, *mountains, targets=[bears])

    assert bears.zone is Zone.EXILE


def test_dragonfire_exiles_a_planeswalker_it_empties():
    scenario = _dragonfire("Liliana of the Veil")
    liliana = scenario.find("Liliana of the Veil", Zone.BATTLEFIELD, "bob")
    mountains = scenario.untapped_sources("Mountain", "Mountain", username="alice")

    scenario.cast_and_resolve(DRAGONFIRE, *mountains, targets=[liliana])
    scenario.state_based_actions()

    assert liliana.zone is Zone.EXILE
