"""Nissa's Defeat's own "Destroy target Forest, green enchantment, or green
planeswalker." - a compound noun list mixing a bare land subtype (no color
at all) with two color-qualified card types. Extends `permanent_description`
and the shared targeting profile with `TargetRequirement.alternatives`, a
general OR of fully independent sub-requirements, for any future card
printed the same mixed way - not scoped to this one card's own wording.

Verified this session with `knowledge_search(q="...", type="rules")` and
cross-checked with `mise run rules:find` (on-disk CR effective 2026-09-25):

- **CR 115.1** - "some spells and abilities require that one or more
  targets be chosen for them" - a target satisfies the requirement if it
  matches what the phrase names, and a compound "or" phrase is satisfied by
  matching any one of its own listed shapes.
- **CR 205.3i** - basic land types are also subtypes (CR 205.3).
- **CR 105.1 / 105.2b** - a card's colors, and a compound "black or red"
  disjunction across them.
- **CR 300.1** - card types, including land, enchantment, and planeswalker.
- **CR 603.10a / CR 704.8** - the destroyed permanent's own last-known
  information is what the second sentence's "that permanent was a ..."
  reads.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.targeting import permanent_description
from magic_cards_model.models import Color, Type, Zone
from tests.scenarios.harness import Scenario


def test_permanent_description_reads_the_mixed_compound_list() -> None:
    """Unit-level: the requirement itself, and its alternatives, read the
    right axes for each of the three items - proven before the full
    scenario, since a wrong requirement here would otherwise only surface
    as a confusing illegal-target error deep inside casting.
    """
    requirement = permanent_description("Forest, green enchantment, or green planeswalker")
    assert requirement is not None
    assert requirement.card_types == frozenset({Type.LAND})
    assert requirement.required_subtypes == frozenset({"forest"})
    assert requirement.required_colors == frozenset()
    assert len(requirement.alternatives) == 2
    enchantment_alt, planeswalker_alt = requirement.alternatives
    assert enchantment_alt.card_types == frozenset({Type.ENCHANTMENT})
    assert enchantment_alt.required_colors == frozenset({Color.GREEN})
    assert planeswalker_alt.card_types == frozenset({Type.PLANESWALKER})
    assert planeswalker_alt.required_colors == frozenset({Color.GREEN})


def test_nissas_defeat_destroys_a_forest_with_no_color_requirement() -> None:
    """A basic Forest is a legal target on its own - the first item of the
    list carries no color qualifier at all, and must not inherit "green"
    from the other two items the way a single shared `required_colors`
    would wrongly demand.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Nissa's Defeat"], battlefield=["Forest", "Forest", "Mountain"])
        .player("bob", battlefield=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "bob")

    scenario.cast_and_resolve(
        "Nissa's Defeat",
        *scenario.untapped_sources("Forest", "Forest", "Mountain"),
        targets=[forest],
    )

    assert forest.zone is Zone.GRAVEYARD


def test_nissas_defeat_destroys_a_green_enchantment() -> None:
    scenario = (
        Scenario()
        .player("alice", hand=["Nissa's Defeat"], battlefield=["Forest", "Forest", "Mountain"])
        .player("bob", battlefield=["Utopia Sprawl"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sprawl = scenario.find("Utopia Sprawl", Zone.BATTLEFIELD, "bob")

    scenario.cast_and_resolve(
        "Nissa's Defeat",
        *scenario.untapped_sources("Forest", "Forest", "Mountain"),
        targets=[sprawl],
    )

    assert sprawl.zone is Zone.GRAVEYARD


def test_nissas_defeat_cannot_target_a_nongreen_enchantment() -> None:
    """Oath of Jace is blue, not green - a color-qualified alternative still
    enforces its own color, even though the list's first item (Forest)
    carries none at all.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Nissa's Defeat"], battlefield=["Forest", "Forest", "Mountain"])
        .player("bob", battlefield=["Oath of Jace"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    oath = scenario.find("Oath of Jace", Zone.BATTLEFIELD, "bob")

    casting = scenario.cast("Nissa's Defeat")

    with pytest.raises(ValueError):
        casting.choose_targets([oath])


def test_nissas_defeat_draws_a_card_when_the_destroyed_permanent_was_nissa() -> None:
    """ "If that permanent was a Nissa planeswalker, draw a card." - proven
    on Nissa, Who Shakes the World, a real Nissa planeswalker legal as the
    third compound-list item (a green planeswalker).
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Nissa's Defeat"],
            battlefield=["Forest", "Forest", "Mountain"],
            library=["Opt"],
        )
        .player("bob", battlefield=["Nissa, Who Shakes the World"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    nissa = scenario.find("Nissa, Who Shakes the World", Zone.BATTLEFIELD, "bob")
    alice_hand_before = len(scenario.game.player("alice").hand)

    scenario.cast_and_resolve(
        "Nissa's Defeat",
        *scenario.untapped_sources("Forest", "Forest", "Mountain"),
        targets=[nissa],
    )

    assert nissa.zone is Zone.GRAVEYARD
    # alice_hand_before still counts Nissa's Defeat itself, which then
    # leaves her hand to be cast - so the net change from the draw alone is
    # the same count, not +1.
    assert len(scenario.game.player("alice").hand) == alice_hand_before
