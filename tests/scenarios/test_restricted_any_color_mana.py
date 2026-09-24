"""Scenario: "Add `<n>` mana in any combination of colors. Spend this mana
only to cast `<type>` spells." - Desolation of Smaug's own second sentence,
"Add four mana in any combination of colors. Spend this mana only to cast
Dragon spells."

A new merge-clause reader, `machines/effects._merge_add_any_combination_
mana_with_restriction_clauses`: the pre-existing per-unit-colour production
(`_parse_add_any_combination_mana_clause`, Manamorphose's own unrestricted
"Add two mana in any combination of colors.") plus the pre-existing CR 106.6
restriction reader every mana ability's own trailing sentence already goes
through (`machines/cost.spend_restriction`) - read together as one CR 608.2c
instruction because the clause splitter's period cuts them into two raw
clauses that name each other ("this mana" in the second is the first's own
production).

Proven generic on Sarkhan, Fireblood's real, modern/pioneer-legal "+1: Add
two mana in any combination of colors. Spend this mana only to cast Dragon
spells." - the identical sentence pair on a planeswalker's loyalty ability
rather than a sorcery's own second instruction.

CR 106.6 ("Some effects state that a source produces mana that can only be
spent a certain way... 'Spend this mana only to...'") and CR 106.4 ("mana
goes into a player's mana pool") were verified with `mise run rules:find` in
the session that wrote this file - see `machines/mana.py`'s own `ManaRestriction`
docstring for the exact wording it already cites.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_the_restricted_mana_pays_for_a_dragon_spell():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Desolation of Smaug", "Smaug the Magnificent"],
            battlefield=["Mountain", "Mountain", "Mountain", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.will_choose("R", source="Desolation of Smaug", times=4)
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain")
    scenario.cast_and_resolve("Desolation of Smaug", *sources, username="alice")

    pool = scenario.player("alice").mana_pool
    assert pool.total == 4
    assert pool.restricted_total == 4, "every bit of it carries the restriction"

    casting = scenario.cast("Smaug the Magnificent")
    payment = casting.begin_paying()
    payment.pay()
    smaug = scenario.put_on_stack(casting)

    assert smaug.zone is Zone.STACK, "the restricted mana alone paid for a Dragon spell"


def test_the_restricted_mana_cannot_pay_for_a_non_dragon_spell():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Desolation of Smaug", "Grizzly Bears"],
            battlefield=["Mountain", "Mountain", "Mountain", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.will_choose("G", source="Desolation of Smaug", times=4)
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain")
    scenario.cast_and_resolve("Desolation of Smaug", *sources, username="alice")

    pool = scenario.player("alice").mana_pool
    assert pool.total == 4

    casting = scenario.cast("Grizzly Bears")
    payment = casting.begin_paying()

    with pytest.raises(ValueError):
        payment.pay()


def test_sarkhan_fireblood_a_second_real_printing_of_the_same_sentence_pair():
    """Sarkhan, Fireblood's identical "Add two mana in any combination of
    colors. Spend this mana only to cast Dragon spells." on a loyalty
    ability rather than a sorcery's own second instruction."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Desert Were-Worm"],
            battlefield=["Sarkhan, Fireblood", "Mountain", "Mountain", "Mountain", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sarkhan = scenario.find("Sarkhan, Fireblood", Zone.BATTLEFIELD, "alice")

    scenario.will_choose("R", source="Sarkhan, Fireblood", times=2)
    scenario.activate(sarkhan, index=1)
    scenario.resolve_top()

    pool = scenario.player("alice").mana_pool
    assert pool.total == 2
    assert pool.restricted_total == 2

    casting = scenario.cast("Desert Were-Worm")
    payment = casting.begin_paying()
    mountains = scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain")
    scenario.pay_with(payment, *mountains)
    were_worm = scenario.put_on_stack(casting)

    assert were_worm.zone is Zone.STACK, (
        "2 of the {4}{R}{R} paid by Sarkhan's restricted mana, the rest by four Mountains"
    )
