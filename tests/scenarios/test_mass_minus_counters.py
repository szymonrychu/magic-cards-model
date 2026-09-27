"""Darkness Descends: "Put two -1/-1 counters on each creature." - CR 608.2c's
unqualified "each creature", every creature on the battlefield regardless of
who controls it, distinct from `machines/effects._parse_counter_each_
creature_target_player_clause`'s "each creature target player controls" and
`_parse_counter_each_creature_with_counter_clause`'s "each creature you
control with a counter on it", neither of which this widens or duplicates -
`machines/minus_counters._parse_counter_each_creature_clause` is its own new
reader for the bare shape.

Soul Snuffers (Modern-legal, off pool) - "When this creature enters, put a
-1/-1 counter on each creature." - proves the reader is not fitted to
Darkness Descends' own count of two, or to its own sorcery-speed spell shape:
Soul Snuffers puts the identical clause behind a triggered ability's own
"when this creature enters" instead.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def test_darkness_descends_puts_two_counters_on_every_creature_either_side():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Craw Wurm", "Swamp", "Swamp", "Swamp", "Swamp"],
            hand=["Darkness Descends"],
        )
        .player("bob", battlefield=["Colossal Dreadmaw"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wurm = scenario.creature("Craw Wurm", "alice")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")

    scenario.cast_and_resolve("Darkness Descends", auto=True, username="alice")

    assert wurm.counter_count(Counter.MINUS_ONE) == 2
    assert dreadmaw.counter_count(Counter.MINUS_ONE) == 2


def test_darkness_descends_leaves_noncreature_permanents_alone():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Grizzly Bears", "Forest", "Swamp", "Swamp", "Swamp", "Swamp"],
            hand=["Darkness Descends"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (forest,) = scenario.untapped_sources("Forest")

    scenario.cast_and_resolve("Darkness Descends", auto=True, username="alice")

    assert forest.counter_count(Counter.MINUS_ONE) == 0


def test_darkness_descends_can_kill_a_small_creature_via_state_based_actions():
    """A 1/1 taking two -1/-1 counters is a 0/0, CR 704.5f."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Llanowar Elves", "Swamp", "Swamp", "Swamp", "Swamp"],
            hand=["Darkness Descends"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    elves = scenario.creature("Llanowar Elves", "alice")

    scenario.cast_and_resolve("Darkness Descends", auto=True, username="alice")
    scenario.state_based_actions()

    assert elves.zone is Zone.GRAVEYARD


def test_soul_snuffers_off_pool_proves_the_reader_is_the_template_not_the_card():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Grizzly Bears", "Swamp", "Swamp", "Swamp", "Swamp"],
            hand=["Soul Snuffers"],
        )
        .player("bob", battlefield=["Colossal Dreadmaw"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")

    scenario.cast_and_resolve("Soul Snuffers", auto=True, username="alice")
    snuffers = scenario.creature("Soul Snuffers", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert bears.counter_count(Counter.MINUS_ONE) == 1
    assert dreadmaw.counter_count(Counter.MINUS_ONE) == 1
    # Soul Snuffers is itself a creature and so is affected by its own ETB.
    assert snuffers.counter_count(Counter.MINUS_ONE) == 1
