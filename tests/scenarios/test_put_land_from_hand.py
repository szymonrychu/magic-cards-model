"""Scenario: an enters-the-battlefield trigger putting a land straight from
hand onto the battlefield (CR 110.2a's special action never applies here -
this is an *effect*, not a land drop), with Cultivator Colossus's own
"repeat this process" looping the same choice.

The rules this file asserts, every one looked up with `knowledge_search(q=...,
type="rules")` in the session that wrote it:

- **CR 603.6a** - enters-the-battlefield abilities trigger when a permanent
  enters the battlefield.
- **CR 608.2d** - a resolving ability's "you may" is the controller's own
  choice, and it "can't choose an option that's illegal or impossible" - with
  no land in hand, there is nothing to choose, so the choice is never offered.
- **CR 110.5b** - permanents enter the battlefield untapped unless a spell or
  ability says otherwise.
- **CR 118.12** - "[Effect]. If you do, [consequence]." reads the "if you do"
  half as conditioned on whether the action actually happened.
- **CR 121.2** - a draw of more than one card is that many individual draws.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_arboreal_grazer_puts_a_land_from_hand_tapped():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Arboreal Grazer", "Mountain"],
            battlefield=["Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (forest,) = scenario.untapped_sources("Forest")
    grazer = scenario.cast_and_resolve("Arboreal Grazer", forest)
    scenario.pass_until_resolved()  # the enters trigger, put on the stack separately

    assert grazer.zone is Zone.BATTLEFIELD
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD)
    assert mountain.tapped, "CR 614.1c: the sentence says tapped"
    assert scenario.player("alice").hand == []


def test_arboreal_grazer_may_be_declined():
    scenario = (
        Scenario()
        .player("alice", hand=["Arboreal Grazer", "Mountain"], battlefield=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False, username="alice", source="Arboreal Grazer")
    (forest,) = scenario.untapped_sources("Forest")
    scenario.cast_and_resolve("Arboreal Grazer", forest)
    scenario.pass_until_resolved()

    assert scenario.find("Mountain", Zone.HAND).zone is Zone.HAND, "declined: stayed in hand"


def test_arboreal_grazer_asks_nothing_with_no_land_in_hand():
    """CR 608.2d: a "you may" with no legal option is never even asked."""
    scenario = Scenario().player("alice", hand=["Arboreal Grazer"], battlefield=["Forest"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (forest,) = scenario.untapped_sources("Forest")
    scenario.cast_and_resolve("Arboreal Grazer", forest)
    scenario.pass_until_resolved()

    assert scenario.game.decisions.asked == []


def test_cultivator_colossus_repeats_putting_lands_and_drawing():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Cultivator Colossus", "Mountain", "Swamp"],
            library=["Lightning Bolt", "Opt"],
            battlefield=["Forest"] * 7,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*(["Forest"] * 7))
    colossus = scenario.cast_and_resolve("Cultivator Colossus", *sources)
    scenario.pass_until_resolved()  # the enters trigger, put on the stack separately

    assert colossus.zone is Zone.BATTLEFIELD
    alice = scenario.player("alice")
    assert scenario.find("Mountain", Zone.BATTLEFIELD).tapped
    assert scenario.find("Swamp", Zone.BATTLEFIELD).tapped
    assert {c.name for c in alice.hand} == {"Lightning Bolt", "Opt"}, (
        "one card drawn per land put onto the battlefield (CR 121.2)"
    )
    assert alice.library == [], "both draws came from a two-card library"


def test_cultivator_colossus_stops_when_declined_partway():
    """CR 118.12: "if you do" only loops while the answer keeps being yes -
    declining the second offer stops the process with the first land already
    placed and drawn for."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Cultivator Colossus", "Mountain", "Swamp"],
            library=["Opt"],
            battlefield=["Forest"] * 7,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(True, username="alice", source="Cultivator Colossus", times=1)
    scenario.will_take_the_may(False, username="alice", source="Cultivator Colossus", times=1)
    sources = scenario.untapped_sources(*(["Forest"] * 7))
    scenario.cast_and_resolve("Cultivator Colossus", *sources)
    scenario.pass_until_resolved()  # the enters trigger, put on the stack separately

    alice = scenario.player("alice")
    battlefield_names = scenario.battlefield_names()
    assert battlefield_names.count("Mountain") + battlefield_names.count("Swamp") == 1, (
        "only the first offer was taken"
    )
    assert "Opt" in [c.name for c in alice.hand], "one draw happened, for the land that was placed"
    assert battlefield_names.count("Mountain") == 0 or battlefield_names.count("Swamp") == 0, (
        "the other land is still in hand, never chosen"
    )


def test_cultivator_colossus_stops_with_no_land_left_in_hand():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Cultivator Colossus", "Mountain"],
            library=["Opt"],
            battlefield=["Forest"] * 7,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources(*(["Forest"] * 7))
    scenario.cast_and_resolve("Cultivator Colossus", *sources)
    scenario.pass_until_resolved()  # the enters trigger, put on the stack separately

    alice = scenario.player("alice")
    assert scenario.find("Mountain", Zone.BATTLEFIELD).tapped
    assert [c.name for c in alice.hand] == ["Opt"], "drew once for the one land placed"
