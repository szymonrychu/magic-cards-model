"""Scenario: Spelunking - one enchantment, two abilities, one paragraph each
(CR 113.3): an enters trigger that draws and may add a land from hand, with a
bonus for a Cave specifically, and a static ability overriding how every land
its controller controls enters the battlefield.

The rules this file asserts, every one looked up with `knowledge_search(q=...,
type="rules")` in the session that wrote it:

- **CR 603.6a** - enters-the-battlefield abilities trigger when a permanent
  enters the battlefield.
- **CR 305.6** - "Cave" is a land subtype like any other; a card's stated
  quality naming one is a subtype question, not a name question.
- **CR 614.1d** - "Continuous effects that read '[This permanent] enters ...'
  or '[Objects] enter [the battlefield] ...' are replacement effects" - a
  general effect watching a class of permanent, not only the printing card's
  own arrival (CR 614.12's self/other split).
- **CR 616.1** - more than one applicable replacement effect in a row is
  applied one at a time, in an order the affected object's controller picks
  among their own.
- **CR 110.5b** - permanents enter the battlefield untapped unless a spell or
  ability says otherwise; Spelunking's own static restates that default over
  whatever a search's own "tapped" instruction would otherwise have done.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_spelunking_draws_and_puts_a_land_from_hand():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Spelunking", "Mountain"],
            library=["Swamp"],
            battlefield=["Forest", "Forest", "Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mountain_in_hand = scenario.find("Mountain", Zone.HAND)
    scenario.will_choose_cards(mountain_in_hand, username="alice", source="Spelunking")
    sources = scenario.untapped_sources("Forest", "Forest", "Forest")
    spelunking = scenario.cast_and_resolve("Spelunking", *sources)
    scenario.pass_until_resolved()  # the enters trigger, put on the stack separately

    assert spelunking.zone is Zone.BATTLEFIELD
    alice = scenario.player("alice")
    assert "Swamp" in [c.name for c in alice.hand], "drew a card first"
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD)
    assert not mountain.tapped, "no 'tapped' printed on this half at all (CR 110.5b)"
    assert alice.life == 20, "no Cave was put onto the battlefield this way"


def test_spelunking_gains_four_life_for_a_cave():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Spelunking", "Captivating Cave"],
            library=["Swamp"],
            battlefield=["Forest", "Forest", "Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cave_in_hand = scenario.find("Captivating Cave", Zone.HAND)
    scenario.will_choose_cards(cave_in_hand, username="alice", source="Spelunking")
    sources = scenario.untapped_sources("Forest", "Forest", "Forest")
    scenario.cast_and_resolve("Spelunking", *sources)
    scenario.pass_until_resolved()

    assert scenario.find("Captivating Cave", Zone.BATTLEFIELD).zone is Zone.BATTLEFIELD
    assert scenario.player("alice").life == 24, "CR 119.3: 20 + 4"


def test_spelunking_put_land_may_be_declined():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Spelunking", "Mountain"],
            library=["Swamp"],
            battlefield=["Forest", "Forest", "Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False, username="alice", source="Spelunking")
    sources = scenario.untapped_sources("Forest", "Forest", "Forest")
    scenario.cast_and_resolve("Spelunking", *sources)
    scenario.pass_until_resolved()

    assert scenario.find("Mountain", Zone.HAND).zone is Zone.HAND
    assert scenario.player("alice").life == 20


def test_spelunking_makes_a_later_search_enter_untapped():
    """The static half, working on a *different* card's arrival: a fetched
    land that would otherwise enter tapped (Primeval Titan's own search)
    enters untapped instead, once Spelunking is on the battlefield first.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Primeval Titan"],
            library=["Forest", "Mountain"],
            battlefield=["Spelunking", "Forest", "Forest", "Forest", "Forest", "Forest", "Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*(["Forest"] * 6))
    scenario.cast_and_resolve("Primeval Titan", *sources)
    scenario.pass_until_resolved()  # the enters trigger, put on the stack separately

    mountain = scenario.find("Mountain", Zone.BATTLEFIELD)
    assert not mountain.tapped, "CR 614.1d overrides the search's own 'tapped'"


def test_spelunking_does_not_untap_an_opponents_lands():
    scenario = (
        Scenario()
        .player(
            "bob",
            hand=["Primeval Titan"],
            library=["Forest", "Mountain"],
            battlefield=["Forest"] * 6,
        )
        .player("alice", battlefield=["Spelunking"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*(["Forest"] * 6), username="bob")
    scenario.cast_and_resolve("Primeval Titan", *sources, username="bob")
    scenario.pass_until_resolved()

    mountain = scenario.find("Mountain", Zone.BATTLEFIELD)
    assert mountain.tapped, "Spelunking says 'lands you control', not any land anywhere"
