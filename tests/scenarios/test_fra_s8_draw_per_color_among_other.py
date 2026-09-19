"""FRA stream S8: "N for each color among other `<quality>` you control" -
CR 105.1's five colors, counted once each regardless of how many qualifying
permanents share one, and "other" excluding the ability's own source.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file.

- **CR 105.1** - the five colors.
- **CR 613.5** - the count reads the computed board, not the printed card,
  so a colour granted by a continuous effect counts too.

Karn, Gilded Guardian is the reported card - "draw a card for each color
among other artifacts you control". Chromatic Orrery (Core Set 2021, real,
non-FRA, non-pool) is the off-set proof: the identical "draw a card for
each color among `<quality>` you control" shape with no "other" at all (the
ability's own source counts toward the total, unlike Karn's own "other"
excluding it) and a different quality ("permanents" rather than
"artifacts").
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_karn_draws_a_card_for_each_color_among_its_other_artifacts():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Karn, Gilded Guardian"],
            # Boots of Speed (red) and Aerial Doombot (blue): two colors
            # among Karn's *other* artifacts - never Karn's own five-hybrid
            # cost, which "other" excludes regardless.
            battlefield=["Boots of Speed", "Aerial Doombot", "Mox Diamond"] + ["Forest"] * 10,
            library=["Forest"] * 5,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    sources = scenario.untapped_sources(*(["Forest"] * 10))
    hand_before_cast = len(alice.hand)

    scenario.cast_and_resolve("Karn, Gilded Guardian", *sources)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    karn = scenario.find("Karn, Gilded Guardian", Zone.BATTLEFIELD, "alice")
    assert karn.zone is Zone.BATTLEFIELD
    # Karn himself left the hand (cast); two colors among his other
    # artifacts (Boots of Speed is red, Aerial Doombot is blue, Mox Diamond
    # is colorless) draw two back.
    assert len(alice.hand) == hand_before_cast - 1 + 2


def test_chromatic_orrery_draws_a_card_per_color_including_its_own():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Chromatic Orrery", "Boots of Speed", "Aerial Doombot"] + ["Forest"] * 5,
            library=["Forest"] * 5,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    orrery = scenario.creature("Chromatic Orrery", "alice")
    sources = scenario.untapped_sources(*(["Forest"] * 5))
    hand_before = len(alice.hand)

    scenario.activate(orrery, *sources, index=1)
    scenario.pass_until_resolved()

    # Boots of Speed (red) and Aerial Doombot (blue): two colors, with no
    # "other" to exclude Chromatic Orrery's own colorless self either way.
    assert len(alice.hand) == hand_before + 2
