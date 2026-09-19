"""FRA stream S8b: "Separate all `<quality>` target player controls into two
piles. `<consequence>` all `<quality>` in the pile of that player's choice."
- CR 700.3's pile primitive
(`_SEPARATE_INTO_TWO_PILES_RE` in `machines/effects.py`).

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file.

- **CR 700.3/700.3a** - "Some effects cause objects to be temporarily
  grouped into piles. Each of the affected objects must be put into exactly
  one of those piles, unless the effect specifies otherwise."
- **CR 700.3d** - "A pile can contain zero or more objects."
- **CR 701.21a** - sacrifice. **CR 701.16a** - regeneration replaces
  destruction with a specific set of effects; this instruction is destroy,
  not a "would be destroyed" event, so "they can't be regenerated" only
  ever reinforces the outcome this clause already produces.
- **CR 115.1** - "target player" is a real target, chosen as the ability is
  activated (CR 601.2c/602.2b).

Liliana of the Veil's own `-6` is the reported ability. Do or Die (real,
non-FRA, non-pool) is the off-set proof: an instant printing the identical
two-sentence pile shape narrowed to "creatures" and "Destroy" rather than
"permanents" and "sacrifices" - proof the consequence verb, not just the
pile-division sentence, generalises.

Both cards give the *same* player both the division and the pick, which
this file's own docstring in `machines/effects.py` argues is rules-
equivalent to that player freely choosing any subset (zero up to all) of
their own qualifying permanents for the consequence pile - the scenarios
below are written directly against that free choice.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def test_liliana_of_the_veils_minus_six_lets_the_target_choose_which_pile_to_sacrifice():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Liliana of the Veil"])
        .player(
            "bob",
            battlefield=["Grizzly Bears", "Hill Giant", "Elvish Mystic", "Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    liliana = scenario.find("Liliana of the Veil", Zone.BATTLEFIELD, "alice")
    liliana.add_counters(Counter.LOYALTY, 3)  # 3 printed -> 6, enough for -6
    bears = scenario.creature("Grizzly Bears", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    elves = scenario.creature("Elvish Mystic", "bob")
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD, "bob")

    scenario.will_choose_cards(bears, giant, username="bob", source="Liliana of the Veil")
    scenario.activate(liliana, index=2, targets=["bob"])
    scenario.pass_until_resolved()

    assert bears.zone is Zone.GRAVEYARD
    assert giant.zone is Zone.GRAVEYARD
    assert elves.zone is Zone.BATTLEFIELD, "bob's own choice: the rest stayed out of the pile"
    assert mountain.zone is Zone.BATTLEFIELD, "a land is a permanent bob controls, not excluded"


def test_liliana_of_the_veils_minus_six_can_choose_an_empty_pile():
    """CR 700.3d: a pile may be empty - choosing none is a real answer, not
    a forced sacrifice of everything."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Liliana of the Veil"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    liliana = scenario.find("Liliana of the Veil", Zone.BATTLEFIELD, "alice")
    liliana.add_counters(Counter.LOYALTY, 3)  # 3 printed -> 6, enough for -6
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.will_choose_cards(username="bob", source="Liliana of the Veil")
    scenario.activate(liliana, index=2, targets=["bob"])
    scenario.pass_until_resolved()

    assert bears.zone is Zone.BATTLEFIELD


def test_do_or_die_destroys_the_chosen_pile_of_creatures_only():
    scenario = (
        Scenario()
        .player("alice", hand=["Do or Die"], battlefield=["Swamp", "Swamp"])
        .player("bob", battlefield=["Grizzly Bears", "Hill Giant", "Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD, "bob")
    sources = scenario.untapped_sources("Swamp", "Swamp")

    scenario.will_choose_cards(bears, username="bob", source="Do or Die")
    scenario.cast_and_resolve("Do or Die", *sources, targets=["bob"])

    assert bears.zone is Zone.GRAVEYARD
    assert giant.zone is Zone.BATTLEFIELD, "bob's own choice left the giant out"
    assert mountain.zone is Zone.BATTLEFIELD, "Do or Die's own quality is creatures only"
