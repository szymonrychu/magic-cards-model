"""Scenario: Goblin Charbelcher's open-ended reveal.

"{3}, {T}: Reveal cards from the top of your library until you reveal a land
card. This artifact deals damage equal to the number of nonland cards revealed
this way to any target. If the revealed land card was a Mountain, this artifact
deals double that damage instead. Put the revealed cards on the bottom of your
library in any order."

The amount is printed nowhere: it is however many cards it took to hit a land.
Nothing in the engine read that, so the ability resolved and the deck's only
win condition did nothing.

Every CR number here was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 701.20a** - "To reveal a card, show that card to all players for a
  brief time" - revealing moves nothing; the last sentence is what moves them.
- **CR 120.1** - "Objects can deal damage to battles, creatures, planeswalkers,
  and players. ... An object that deals damage is the source of that damage."
- **CR 119.2** - damage to a player costs that much life.
- **CR 305.6** - "The basic land types are Plains, Island, Swamp, Mountain, and
  Forest", which is what "was a Mountain" asks about: a subtype, not a name.
- **CR 400.5** - "The order of objects in a library ... can't be changed
  except when effects or rules allow it", so "in any order" is a choice this
  effect grants rather than a randomisation.
- **CR 608.2c** - the four sentences run in the order printed.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

FOUR_LANDS = ["Wastes"] * 4


def _belch(scenario, target):
    belcher = scenario.find("Goblin Charbelcher", Zone.BATTLEFIELD, "alice")
    scenario.activate(belcher, *scenario.untapped_sources(*FOUR_LANDS), targets=[target])
    scenario.resolve_top()


def test_the_damage_is_the_number_of_nonlands_it_took_to_find_a_land():
    """Three nonlands then a Forest: three damage, and the Forest is not a
    Mountain so nothing is doubled."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Goblin Charbelcher", *FOUR_LANDS],
            library=["Lightning Bolt", "Lightning Bolt", "Sol Ring", "Forest", "Island"],
        )
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _belch(scenario, scenario.player("bob"))

    assert scenario.player("bob").life == 17


def test_a_mountain_doubles_the_damage():
    """CR 305.6's subtype: stopping on a Mountain makes it one damage event of
    twice the size, not two events."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Goblin Charbelcher", *FOUR_LANDS],
            library=["Lightning Bolt", "Lightning Bolt", "Sol Ring", "Mountain", "Island"],
        )
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _belch(scenario, scenario.player("bob"))

    assert scenario.player("bob").life == 14, "three nonlands, doubled"


def test_a_land_on_top_deals_nothing_at_all():
    """The reveal stops immediately; zero nonlands is zero damage, doubled or
    not."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Goblin Charbelcher", *FOUR_LANDS],
            library=["Mountain", "Lightning Bolt"],
        )
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _belch(scenario, scenario.player("bob"))

    assert scenario.player("bob").life == 20


def test_a_library_with_no_land_reveals_all_of_it():
    """ "Until you reveal a land card" with no land to find runs out of
    library; every card seen was a nonland, so every card counts."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Goblin Charbelcher", *FOUR_LANDS],
            library=["Lightning Bolt", "Sol Ring", "Memnite"],
        )
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _belch(scenario, scenario.player("bob"))

    assert scenario.player("bob").life == 17


def test_the_revealed_cards_end_up_on_the_bottom():
    """CR 400.5: they go under whatever was already below them, and nothing
    was drawn or milled on the way."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Goblin Charbelcher", *FOUR_LANDS],
            library=["Lightning Bolt", "Forest", "Island", "Swamp"],
        )
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    _belch(scenario, scenario.player("bob"))

    library = [state.name for state in scenario.player("alice").library]
    assert library == ["Island", "Swamp", "Lightning Bolt", "Forest"]
    assert scenario.player("alice").graveyard == []


def test_it_can_point_at_a_creature_instead():
    """ "Any target" is CR 115.4's own group - a creature is as legal as a
    player, and the damage is marked rather than lost."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Goblin Charbelcher", *FOUR_LANDS],
            library=["Lightning Bolt", "Sol Ring", "Forest"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    _belch(scenario, bears)

    assert bears.zone is Zone.GRAVEYARD, "a 2/2 dies to two damage"
