"""FRA stream S8b: "Search your library for a `<quality>` card with mana
value less than this permanent's power, put that card onto the battlefield,
then shuffle." - a search bounded by the source's own computed power
(`_SEARCH_MV_LESS_THAN_SELF_POWER_RE` in `machines/effects.py`).

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file.

- **CR 613** - power is a computed characteristic (layers), read fresh at
  resolution rather than off the printed card.
- **CR 205.4a** - legendary is a supertype, not a card type; CR 110.4a's
  "permanent" is the six-type umbrella. Sisay's own "a legendary permanent
  card" needs both checks at once, which is why `_quality_matcher` gained a
  "legendary " prefix branch the same shape its existing "basic "/"snow "
  branches already have.
- **CR 701.23a/701.23b** - a stated-quality search; failing to find remains
  legal. **CR 701.24a** - the shuffle that follows.

Sisay, Weatherlight Captain's own `{W}{U}{B}{R}{G}` ability is the reported
card - its own printed base power (2/2) is what this test drives the bound
off, since its other static ability (a continuous +1/+1 pump per color among
other legendary permanents controlled) is a separate, unrelated mechanic
this stream does not touch. Verified via Scryfall's own oracle-text search in
the session that wrote this file: Sisay is the only real printing combining
"search your library" with a bound on the *source's own power* today, so
generality here rests on `_self_normalized_effect_text`'s own normalisation
(any future card printing the identical templated sentence reads the same
way, the way `_COUNTER_ON_SELF_RE`'s "this creature"/"this permanent" already
does for every self-referential counter clause) rather than on a second
current printing of this exact compound shape.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_sisay_finds_a_legendary_permanent_under_her_own_power():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "Sisay, Weatherlight Captain",
                "Plains",
                "Island",
                "Swamp",
                "Mountain",
                "Forest",
            ],
            library=["Ragavan, Nimble Pilferer", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sisay = scenario.creature("Sisay, Weatherlight Captain", "alice")
    ragavan = scenario.find("Ragavan, Nimble Pilferer", Zone.LIBRARY, "alice")
    sources = scenario.untapped_sources("Plains", "Island", "Swamp", "Mountain", "Forest")

    scenario.activate(sisay, *sources, index=0)
    scenario.pass_until_resolved()

    assert ragavan.zone is Zone.BATTLEFIELD
    assert ragavan.controller == "alice"


def test_sisay_will_not_find_a_legendary_permanent_at_or_above_her_own_power():
    """Wrenn and Six is mana value 2 - not *less than* Sisay's own printed
    power of 2, so it is not a legal find at all (CR 701.23b: nothing is
    forced when the only matches fail the stated quality)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "Sisay, Weatherlight Captain",
                "Plains",
                "Island",
                "Swamp",
                "Mountain",
                "Forest",
            ],
            library=["Wrenn and Six"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sisay = scenario.creature("Sisay, Weatherlight Captain", "alice")
    wrenn = scenario.find("Wrenn and Six", Zone.LIBRARY, "alice")
    sources = scenario.untapped_sources("Plains", "Island", "Swamp", "Mountain", "Forest")

    scenario.activate(sisay, *sources, index=0)
    scenario.pass_until_resolved()

    assert wrenn.zone is Zone.LIBRARY


def test_sisay_will_not_find_a_nonlegendary_permanent_even_under_the_power_bound():
    """Llanowar Elves is mana value 1 (under Sisay's power of 2) but is not
    legendary - CR 205.4a's own supertype half of the printed quality still
    has to hold, mana value bound or not."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "Sisay, Weatherlight Captain",
                "Plains",
                "Island",
                "Swamp",
                "Mountain",
                "Forest",
            ],
            library=["Llanowar Elves"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sisay = scenario.creature("Sisay, Weatherlight Captain", "alice")
    elves = scenario.find("Llanowar Elves", Zone.LIBRARY, "alice")
    sources = scenario.untapped_sources("Plains", "Island", "Swamp", "Mountain", "Forest")

    scenario.activate(sisay, *sources, index=0)
    scenario.pass_until_resolved()

    assert elves.zone is Zone.LIBRARY
