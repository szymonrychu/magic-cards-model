"""Convoke spell bodies: CR 702.51a's own convoke tap already worked before
this task (`machines/keywords.py`) and is not retested here - what was
silent on Bloodline Bidding, Harmonized Crescendo, and Wanderwine Farewell
was every one of their own *resolution* sentences, not the keyword line
above them.

- Bloodline Bidding: "Choose a creature type. Return all creature cards of
  the chosen type from your graveyard to the battlefield."
- Harmonized Crescendo: "Choose a creature type. Draw a card for each
  permanent you control of that type."
- Wanderwine Farewell: "Return one or two target nonland permanents to
  their owners' hands. Then if you control a Merfolk, create a 1/1 white
  and blue Merfolk creature token for each permanent returned to its
  owner's hand this way."

Each reads a *fresh* "choose a creature type" (CR 608.2b, made as the spell
resolves) through `machines/chosen_type.ask_creature_type` - not CR
614.12a's own "as [this] enters" choice, since a sorcery/instant has no
permanent incarnation to carry that choice on.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_bloodline_bidding_returns_all_graveyard_creatures_of_the_chosen_type():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Bloodline Bidding"],
            battlefield=["Swamp"] * 8,
            graveyard=["Grizzly Bears", "Lys Alana Dignitary", "Eclipsed Boggart"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose("Bear")
    sources = scenario.untapped_sources(*["Swamp"] * 8)
    scenario.cast_and_resolve("Bloodline Bidding", *sources)

    assert scenario.find("Grizzly Bears", Zone.BATTLEFIELD) is not None
    assert scenario.find("Lys Alana Dignitary", Zone.GRAVEYARD) is not None
    assert scenario.find("Eclipsed Boggart", Zone.GRAVEYARD) is not None


def test_bloodline_bidding_returns_nothing_when_no_graveyard_creature_matches():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Bloodline Bidding"],
            battlefield=["Swamp"] * 8,
            graveyard=["Lys Alana Dignitary"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose("Bear")
    sources = scenario.untapped_sources(*["Swamp"] * 8)
    scenario.cast_and_resolve("Bloodline Bidding", *sources)

    assert scenario.find("Lys Alana Dignitary", Zone.GRAVEYARD) is not None


def test_harmonized_crescendo_draws_a_card_per_permanent_of_the_chosen_type():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Harmonized Crescendo"],
            battlefield=(
                ["Island"] * 6 + ["Grizzly Bears", "Grizzly Bears", "Lys Alana Dignitary"]
            ),
            library=["Island"] * 5,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose("Bear")
    sources = scenario.untapped_sources(*["Island"] * 6)
    before = len(scenario.player("alice").hand)
    scenario.cast_and_resolve("Harmonized Crescendo", *sources)

    # Two Bears of the chosen type; the Elf does not count.
    assert len(scenario.player("alice").hand) == before - 1 + 2


def test_wanderwine_farewell_bounces_and_makes_merfolk_tokens_when_you_control_one():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Wanderwine Farewell"],
            battlefield=["Island"] * 7 + ["Deepway Navigator"],
        )
        .player("bob", battlefield=["Grizzly Bears", "Lys Alana Dignitary"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    dignitary = scenario.creature("Lys Alana Dignitary", "bob")
    sources = scenario.untapped_sources(*["Island"] * 7)

    scenario.cast_and_resolve("Wanderwine Farewell", *sources, targets=[bears, dignitary])

    assert bears.zone is Zone.HAND
    assert dignitary.zone is Zone.HAND
    tokens = [
        state
        for state in scenario.game.permanents_controlled_by("alice")
        if state.token and state.name == "Merfolk Token"
    ]
    assert len(tokens) == 2


def test_wanderwine_farewell_makes_no_tokens_without_a_merfolk():
    scenario = (
        Scenario()
        .player("alice", hand=["Wanderwine Farewell"], battlefield=["Island"] * 7)
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources(*["Island"] * 7)

    scenario.cast_and_resolve("Wanderwine Farewell", *sources, targets=[bears])

    assert bears.zone is Zone.HAND
    tokens = [state for state in scenario.game.permanents_controlled_by("alice") if state.token]
    assert tokens == []
