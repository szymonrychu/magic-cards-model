"""Scenario: CR 603.10a's look-back is for the event the source left in.

A leaves-the-battlefield ability ("Whenever another creature you control
dies") looks back in time, so it triggers for a creature that dies at the
same time as its source - CR 603.10a's own example: an artifact with
"Whenever a creature dies, you gain 1 life" destroyed together with two
creatures triggers twice. It does not make the ability work from a graveyard
afterwards: a source that died earlier, or never reached the battlefield,
is not asked about a later death (CR 113.6, CR 603.10).

Found by the behavioural sweep once it took optional targets: Syr Vondam,
Sunstar Exemplar's dies trigger destroyed Memnite and Syr Vondam, already in
the graveyard, triggered on it. Proven again on Blood Artist.

CR numbers read with `mise run rules:find` in the session that wrote this
file: 603.10, 603.10a, 603.6c, 113.6.
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario

SYR = "Syr Vondam, Sunstar Exemplar"


def _triggered(scenario, name: str) -> bool:
    scenario.game.check_state_based_actions()
    scenario.game.put_triggers_on_stack()
    return f"{name}'s triggered ability" in scenario.stack_names()


def test_a_source_already_in_the_graveyard_does_not_see_a_later_death():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Memnite", "Mountain"],
            hand=["Lightning Bolt"],
            graveyard=[SYR],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    memnite = scenario.creature("Memnite", "alice")

    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[memnite]
    )

    assert not _triggered(scenario, SYR)


def test_a_source_that_died_earlier_does_not_see_a_later_death():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[SYR, "Memnite", "Mountain", "Mountain"],
            hand=["Lightning Bolt", "Lightning Bolt"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    syr = scenario.creature(SYR, "alice")
    scenario.game.destroy(syr)
    scenario.game.check_state_based_actions()
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.game.resolve_top()
    memnite = scenario.creature("Memnite", "alice")
    (mountain,) = scenario.untapped_sources("Mountain")[:1]

    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=[memnite])

    assert not _triggered(scenario, SYR)


def test_dying_together_still_looks_back():
    """CR 603.10a's own example, on Blood Artist ("Whenever Blood Artist or
    another creature dies"): destroyed with two other creatures by one
    Wrath of God, it triggers three times."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Blood Artist", "Memnite", "Grizzly Bears", *["Plains"] * 4],
            hand=["Wrath of God"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose_targets("bob", times=None)

    scenario.cast_and_resolve("Wrath of God", *scenario.untapped_sources(*["Plains"] * 4))
    scenario.game.check_state_based_actions()
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names().count("Blood Artist's triggered ability") == 3


def test_blood_artist_in_the_graveyard_does_not_see_a_later_death():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Memnite", "Mountain"],
            hand=["Lightning Bolt"],
            graveyard=["Blood Artist"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    memnite = scenario.creature("Memnite", "alice")

    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[memnite]
    )

    assert not _triggered(scenario, "Blood Artist")
