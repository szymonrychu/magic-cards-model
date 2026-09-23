"""FRA stream S8: "Exile another `<quality>` card from your graveyard" as an
additional cost (CR 118.8a, CR 406.2), and "Return this card from your
graveyard to the battlefield tapped with a `<n>` `<kind>` counter on
`<pronoun>`." (CR 110.2a, CR 122.1).

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file.

- **CR 118.8a** - additional costs, paid alongside the mana in the same
  activation.
- **CR 406.2** - exiling a card as a cost.
- **CR 601.2c/113.6** - "another" excludes the ability's own source card -
  read the same way `machines/targeting.py`'s own `TargetRequirement.
  excludes_source` already reads "another"/"other" on the targeting side, a
  new `CardRequirement.excludes_source` on the cost side.
- **CR 110.2a** - the returned permanent enters under its own controller.
- **CR 122.1** - the counter, placed as the permanent arrives.

Gallia, Tragic Host is the reported card: its own "her" is CR 201.5's
gendered self-pronoun, the same closed set `_OBJECT_ANAPHOR` already reads
for "it"/"him"/"her". Scrapheap Scrounger (Kaladesh, real, non-FRA, non-pool,
Modern legal) is the off-set proof: the identical "exile another creature
card from your graveyard" additional cost, with no tapped/counter rider at
all - proving the cost reader is what generalises, independent of the
return clause's own riders.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def test_gallia_exiles_another_creature_and_returns_tapped_with_a_counter():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Swamp"] * 5,
            graveyard=["Gallia, Tragic Host", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gallia = scenario.find("Gallia, Tragic Host", Zone.GRAVEYARD, "alice")
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp", "Swamp")

    scenario.activate(gallia, *sources, exiling=[bears])
    scenario.pass_until_resolved()

    assert gallia.zone is Zone.BATTLEFIELD
    assert gallia.tapped
    assert gallia.counter_count(Counter.PLUS_ONE) == 1
    assert bears.zone is Zone.EXILE


def test_gallia_cannot_exile_herself_to_pay_her_own_cost():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Swamp"] * 5, graveyard=["Gallia, Tragic Host"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gallia = scenario.find("Gallia, Tragic Host", Zone.GRAVEYARD, "alice")
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp", "Swamp")

    with pytest.raises(ValueError, match="excludes the ability's own source"):
        scenario.activate(gallia, *sources, exiling=[gallia])


def test_scrapheap_scrounger_reads_the_identical_cost_with_no_rider_at_all():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Swamp", "Swamp"],
            graveyard=["Scrapheap Scrounger", "Elvish Mystic"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scrounger = scenario.find("Scrapheap Scrounger", Zone.GRAVEYARD, "alice")
    mystic = scenario.find("Elvish Mystic", Zone.GRAVEYARD, "alice")
    sources = scenario.untapped_sources("Swamp", "Swamp")

    scenario.activate(scrounger, *sources, exiling=[mystic])
    scenario.pass_until_resolved()

    assert scrounger.zone is Zone.BATTLEFIELD
    assert not scrounger.tapped
    assert scrounger.counter_count(Counter.PLUS_ONE) == 0
    assert mystic.zone is Zone.EXILE


def test_the_off_zone_entry_point_pays_the_exile_cost_too():
    """`off_zone_activation` is the one entry point a caller holding an
    `ACTIVATE_OFF_ZONE` action (`legal_actions`) uses. It took a sacrifice
    and a discard but no exiled cards, so this cost - legal, and offered as
    an action - could not be paid through it at all. Found by the
    behavioural sweep."""
    from magic_cards_model.machines.keywords import off_zone_abilities, off_zone_activation

    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Swamp", "Swamp"],
            graveyard=["Scrapheap Scrounger", "Elvish Mystic"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scrounger = scenario.find("Scrapheap Scrounger", Zone.GRAVEYARD, "alice")
    mystic = scenario.find("Elvish Mystic", Zone.GRAVEYARD, "alice")
    (index,) = [
        i for i, entry in enumerate(off_zone_abilities(scrounger.card)) if entry.family == "printed"
    ]

    activation = off_zone_activation(scenario.game, scrounger, "alice", index, exiling=[mystic])
    scenario.pay_with(activation.begin_paying(), *scenario.untapped_sources("Swamp", "Swamp"))
    activation.activate()
    scenario.pass_until_resolved()

    assert scrounger.zone is Zone.BATTLEFIELD
    assert mystic.zone is Zone.EXILE
