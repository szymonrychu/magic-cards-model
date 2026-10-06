"""Ghostfire: "Ghostfire is colorless. Ghostfire deals 3 damage to any target."

The first sentence is CR 604.3's characteristic-defining ability: it functions
on the stack and in every other zone, overriding the colour the {2}{R} mana
cost would give (CR 202.2) with no colour at all (CR 105.2c). It is never a
CR 608.2c resolution instruction, so it is stripped off the resolution text
exactly as "is all colors" (Awaken the Maelstrom) is - the shared reader is
`_strip_self_is_all_colors_sentence`, and `test_self_is_all_colors_cda.py` /
`test_awaken_the_maelstrom_spell_effects.py` keep the "all colors" half green.

The proof that the engine really treats it as colourless is protection: a
red source cannot target or damage a creature with protection from red
(CR 702.16b-e), but a colourless one can. Kor Firewalker has protection from
red; Lightning Bolt, a red spell, is the control.

Ghostfire has no other in-pool printing with an "is colorless" sentence
(Ghostflame Sliver's "All Slivers are colorless" is a different, layered
shape), so the shared strip is proven on the all-colors twin staying green.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.effects import spell_resolution_text
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Ghostfire", "Lightning Bolt"],
            battlefield=["Mountain"] * 6,
        )
        .player("bob", life=20, battlefield=["Kor Firewalker"])
    )


def test_ghostfire_is_colourless_not_red_from_its_cost():
    scenario = _board().build()
    ghostfire = scenario.find("Ghostfire", Zone.HAND)
    assert "{R}" in (ghostfire.mana_cost or "")
    assert ghostfire.colors == ()


def test_the_colourless_sentence_is_not_a_resolution_instruction():
    text = spell_resolution_text(
        "Ghostfire",
        "Ghostfire is colorless.\nGhostfire deals 3 damage to any target.",
    )
    assert text == "Ghostfire deals 3 damage to any target."


def test_ghostfire_deals_damage_to_a_protection_from_red_creature():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    firewalker = scenario.creature("Kor Firewalker", "bob")

    scenario.cast_and_resolve(
        "Ghostfire",
        *scenario.untapped_sources("Mountain", "Mountain", "Mountain"),
        targets=[firewalker],
    )

    assert firewalker.zone is Zone.GRAVEYARD


def test_a_red_spell_cannot_target_that_creature():
    """The control: Lightning Bolt is red, so protection from red refuses it."""
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    firewalker = scenario.creature("Kor Firewalker", "bob")

    with pytest.raises(ValueError):
        scenario.cast("Lightning Bolt", targets=[firewalker])


def test_ghostfire_deals_three_to_a_player():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_and_resolve(
        "Ghostfire",
        *scenario.untapped_sources("Mountain", "Mountain", "Mountain"),
        targets=["bob"],
    )

    assert scenario.player("bob").life == 17


def test_all_colors_sentence_is_still_stripped():
    """The widened strip keeps its original reader: Awaken the Maelstrom."""
    text = spell_resolution_text(
        "Awaken the Maelstrom",
        "Awaken the Maelstrom is all colors.\nTarget player draws two cards.",
    )
    assert text == "Target player draws two cards."
