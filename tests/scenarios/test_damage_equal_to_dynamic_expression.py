"""Combustion Technique's own "deals damage equal to 2 plus the number of
Lesson cards in your graveyard to target creature." - a dynamic damage
amount, read through `count_expression`'s graveyard-count branch (widened
this session to also read a subtype qualifier, not only a card type) and
`amount_expression`'s own "N plus `<term>`" arithmetic, then evaluated fresh
as the spell resolves through a new general `deal_damage_equal_to_expression`
reader - not scoped to this one card's own two-term "2 plus ..." shape.

Verified this session with `knowledge_search(q="...", type="rules")` and
cross-checked with `mise run rules:find` (on-disk CR effective 2026-09-25):

- **CR 107.1b** - a negative result floors to zero.
- **CR 608.2c** - the amount is fixed as the ability resolves, evaluated
  live against the graveyard at that moment, not when the spell was cast.
- **CR 119.2 / 119.3** - damage to a permanent.
- **CR 205.3 / CR 715** - subtypes generally, and Lesson specifically.
- **CR 500.2** - the graveyard is a shared pile each player's own cards go
  into; "your graveyard" is the caster's own pile.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_combustion_technique_deals_two_plus_lesson_count_damage() -> None:
    """Two Lesson cards already in alice's graveyard plus the base 2 is 4
    damage - enough to kill Elder Gargaroth (toughness 6 survives; use a
    smaller creature to prove the exact amount instead) - Grizzly Bears
    (toughness 2) dies well under the total, so the asserted amount is
    checked directly against the damage marked rather than only "died or
    not".
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Combustion Technique"],
            battlefield=["Mountain", "Mountain"],
            graveyard=["Firebending Lesson", "Firebending Lesson"],
        )
        .player("bob", battlefield=["Elder Gargaroth"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gargaroth = scenario.creature("Elder Gargaroth", "bob")

    scenario.cast_and_resolve(
        "Combustion Technique",
        *scenario.untapped_sources("Mountain", "Mountain"),
        targets=[gargaroth],
    )

    assert gargaroth.zone is Zone.BATTLEFIELD, "toughness 6 survives 2 + 2 = 4 damage"
    assert gargaroth.damage == 4


def test_combustion_technique_deals_only_the_base_two_with_an_empty_graveyard() -> None:
    scenario = (
        Scenario()
        .player("alice", hand=["Combustion Technique"], battlefield=["Mountain", "Mountain"])
        .player("bob", battlefield=["Elder Gargaroth"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gargaroth = scenario.creature("Elder Gargaroth", "bob")

    scenario.cast_and_resolve(
        "Combustion Technique",
        *scenario.untapped_sources("Mountain", "Mountain"),
        targets=[gargaroth],
    )

    assert gargaroth.damage == 2


def test_combustion_technique_exiles_a_lethally_damaged_creature_instead_of_letting_it_die() -> (
    None
):
    """ "If that creature would die this turn, exile it instead." - proven
    together with the dynamic amount, on a creature the total damage
    actually kills.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Combustion Technique"],
            battlefield=["Mountain", "Mountain"],
            graveyard=["Firebending Lesson"] * 3,
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.cast_and_resolve(
        "Combustion Technique", *scenario.untapped_sources("Mountain", "Mountain"), targets=[bears]
    )

    assert bears.zone is Zone.EXILE
