"""Kindred Judgment's own "Choose a creature type. Destroy all creatures
that aren't of the chosen type." - a board-wide destroy whose exemption is
a player's own free choice of creature type (CR 701.6a), not a target.

Verified this session with `knowledge_search(q="...", type="rules")` and
cross-checked with `mise run rules:find` (on-disk CR effective 2026-09-25):

- **CR 701.6a** - "the value of that choice may be any creature type, even
  one that's not on the battlefield, and even one that's not a creature
  type of a card actually in the game."
- **CR 205.3** - creature subtypes.
- **CR 115.10a** - a choice like this is not targeting.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_kindred_judgment_destroys_every_creature_not_of_the_chosen_type() -> None:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Kindred Judgment"],
            battlefield=["Plains"] * 7,
        )
        .player("bob", battlefield=["Grizzly Bears", "Elder Gargaroth"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    gargaroth = scenario.creature("Elder Gargaroth", "bob")
    scenario.will_choose("Bear", source="Kindred Judgment")

    scenario.cast_and_resolve("Kindred Judgment", *scenario.untapped_sources(*["Plains"] * 7))

    assert bears.zone is Zone.BATTLEFIELD, "a Bear survives the Bear-type choice"
    assert gargaroth.zone is Zone.GRAVEYARD, "a Beast is not a Bear"


def test_kindred_dominance_off_set_reads_the_same_shape() -> None:
    """Kindred Dominance (not in this pool, not the reported card): the
    identical "Choose a creature type. Destroy all creatures that aren't
    of the chosen type." wording.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Kindred Dominance"], battlefield=["Swamp"] * 7)
        .player("bob", battlefield=["Grizzly Bears", "Elder Gargaroth"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    gargaroth = scenario.creature("Elder Gargaroth", "bob")
    scenario.will_choose("Beast", source="Kindred Dominance")

    scenario.cast_and_resolve("Kindred Dominance", *scenario.untapped_sources(*["Swamp"] * 7))

    assert gargaroth.zone is Zone.BATTLEFIELD, "an Elder Gargaroth is a Beast"
    assert bears.zone is Zone.GRAVEYARD, "a Bear is not a Beast"
