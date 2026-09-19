"""CR 601.2b's "[cost] or pay [mana]" additional-cost shape.

"As an additional cost to cast this spell, sacrifice a creature or planeswalker
or pay {3}." (Silence the Echo) is a mandatory additional cost with two legal
ways to pay it: CR 601.2b's own "the player announces their intentions to pay
any or all of those costs" applies to whichever half is chosen. Before this,
`total_cost_for_phrase` could not read the sentence as a whole (the trailing
"or pay {3}" is not part of any single component's own grammar), so
`mandatory_additional_costs` raised and the card was uncastable - CLAUDE.md's
"never state a rule from memory" aside, this one was read and simply not
implemented (S10 survey, 2026-09-19).

The fix is general, not specific to sacrifice: it reads any additional-cost
sentence's own trailing " or pay [mana]" the same way, and generality is
proved on Bayou Groff (Strixhaven), a different card in a different set with
the same "sacrifice a creature or pay {3}" shape but for a creature spell
rather than an instant.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.cost import additional_cost_phrases
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_silence_the_echo_can_be_cast_by_sacrificing_a_creature_or_planeswalker():
    """Silence the Echo: "sacrifice a creature or planeswalker or pay {3}."

    Choosing the sacrifice half pays no extra mana - {1}{B} is the whole cost.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Silence the Echo"],
            battlefield=["Swamp", "Swamp", "Grizzly Bears"],
        )
        .player("bob", battlefield=["Memnite"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert additional_cost_phrases(scenario.find("Silence the Echo", Zone.HAND).card) == [
        "sacrifice a creature or planeswalker or pay {3}"
    ]
    bears = scenario.creature("Grizzly Bears", "alice")
    memnite = scenario.creature("Memnite", "bob")
    sources = scenario.untapped_sources("Swamp", "Swamp", username="alice")

    scenario.cast_and_resolve("Silence the Echo", *sources, targets=[memnite], sacrificing=[bears])

    assert bears.zone is Zone.GRAVEYARD
    assert memnite.zone is Zone.GRAVEYARD


def test_silence_the_echo_can_be_cast_by_paying_three_more_instead():
    """The other half of the same choice: no creature or planeswalker
    sacrificed, {3} more paid instead - castable with nothing to sacrifice at
    all.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Silence the Echo"],
            battlefield=["Swamp", "Swamp", "Swamp", "Swamp", "Swamp"],
        )
        .player("bob", battlefield=["Memnite"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    memnite = scenario.creature("Memnite", "bob")
    sources = scenario.untapped_sources(
        "Swamp", "Swamp", "Swamp", "Swamp", "Swamp", username="alice"
    )

    scenario.cast_and_resolve("Silence the Echo", *sources, targets=[memnite])

    assert memnite.zone is Zone.GRAVEYARD
    assert all(source.tapped for source in sources)


def test_bayou_groff_generalizes_the_same_or_pay_shape_to_a_creature_spell():
    """Bayou Groff (Strixhaven): "sacrifice a creature or pay {3}." - a
    different card, a different set, a creature spell instead of an instant,
    proving the fix reads the mechanic, not Silence the Echo's own sentence.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Bayou Groff"],
            battlefield=["Forest", "Forest", "Grizzly Bears"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert additional_cost_phrases(scenario.find("Bayou Groff", Zone.HAND).card) == [
        "sacrifice a creature or pay {3}"
    ]
    bears = scenario.creature("Grizzly Bears", "alice")
    sources = scenario.untapped_sources("Forest", "Forest", username="alice")

    scenario.cast_and_resolve("Bayou Groff", *sources, sacrificing=[bears])

    assert bears.zone is Zone.GRAVEYARD
    assert scenario.find("Bayou Groff", Zone.BATTLEFIELD).zone is Zone.BATTLEFIELD


def test_bayou_groff_can_be_paid_with_mana_alone_with_no_creature_on_board():
    """The alternative half again, with nothing at all to sacrifice."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Bayou Groff"],
            battlefield=["Forest", "Forest", "Forest", "Forest", "Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(
        "Forest", "Forest", "Forest", "Forest", "Forest", username="alice"
    )

    scenario.cast_and_resolve("Bayou Groff", *sources)

    assert scenario.find("Bayou Groff", Zone.BATTLEFIELD).zone is Zone.BATTLEFIELD
    assert all(source.tapped for source in sources)
