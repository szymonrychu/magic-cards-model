"""Scenario: Celestial Purge - "Exile target black or red permanent." A
colour-restricted target, read off the printed adjective pair rather than a
registry row.

Every CR number here was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 105.2a** - "A monocolored object is exactly one of the five colors."
- **CR 105.2b** - "A multicolored object is two or more of the five colors."
- **CR 105.2c** - "A colorless object has no color."
- **CR 109.3** - color is one of an object's characteristics, so a
  colour-changing continuous effect (layer 5, CR 613.1e) is read off the
  computed board, not the printed card.
- **CR 613.1e** - "Layer 5: Color-changing effects are applied."
- **CR 701.13a** - "To exile an object, move it to the exile zone from
  wherever it is."
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _to_main(scenario) -> None:
    scenario.start_at(Step.PRECOMBAT_MAIN)


def test_celestial_purge_exiles_a_black_permanent():
    """The happy path: a black creature is a legal target and is exiled."""
    scenario = (
        Scenario()
        .player("alice", hand=["Celestial Purge"], battlefield=["Plains", "Plains"])
        .player("bob", battlefield=["Gray Merchant of Asphodel"])
        .build()
    )
    _to_main(scenario)
    merchant = scenario.creature("Gray Merchant of Asphodel", "bob")

    sources = scenario.untapped_sources("Plains", "Plains")
    scenario.cast_and_resolve("Celestial Purge", *sources, targets=[merchant])

    assert merchant.zone is Zone.EXILE


def test_celestial_purge_exiles_a_red_permanent():
    """ "Black or red" is a disjunction (CR 105.2a) - red alone is enough."""
    scenario = (
        Scenario()
        .player("alice", hand=["Celestial Purge"], battlefield=["Plains", "Plains"])
        .player("bob", battlefield=["Goblin Guide"])
        .build()
    )
    _to_main(scenario)
    goblin = scenario.creature("Goblin Guide", "bob")

    sources = scenario.untapped_sources("Plains", "Plains")
    scenario.cast_and_resolve("Celestial Purge", *sources, targets=[goblin])

    assert goblin.zone is Zone.EXILE


def test_celestial_purge_cannot_target_a_green_permanent():
    """A creature that is neither black nor red is not a legal target at all -
    `Casting.choose_targets` refuses the announcement (CR 601.2c), the spell
    never reaches the stack over an illegal target.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Celestial Purge"], battlefield=["Plains", "Plains"])
        .player("bob", battlefield=["Elvish Mystic"])
        .build()
    )
    _to_main(scenario)
    mystic = scenario.creature("Elvish Mystic", "bob")

    casting = scenario.cast("Celestial Purge")
    with pytest.raises(ValueError, match="black or red"):
        casting.choose_targets([mystic])


def test_celestial_purge_can_target_a_permanent_alice_controls():
    """Nothing in the printed text restricts control (unlike "target permanent
    an opponent controls") - a caster may exile their own black or red
    permanent, however unlikely that is to be useful.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Celestial Purge"], battlefield=["Plains", "Plains", "Goblin Guide"])
        .build()
    )
    _to_main(scenario)
    goblin = scenario.creature("Goblin Guide", "alice")

    sources = scenario.untapped_sources("Plains", "Plains")
    scenario.cast_and_resolve("Celestial Purge", *sources, targets=[goblin])

    assert goblin.zone is Zone.EXILE
