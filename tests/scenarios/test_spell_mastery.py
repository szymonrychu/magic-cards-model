"""Scenario: *spell mastery* - "If there are two or more instant and/or sorcery
cards in your graveyard, ..." (Magic Origins).

Spell mastery is an ability word (CR 207.2c: ability words "have no special
rules meaning and no individual entries in the Comprehensive Rules"), so the
whole mechanic is the condition printed after it. The condition is read by
`Game.condition_holds` (`_CONDITION_GRAVEYARD_CARDS`, widened to the "X and/or
Y" card quality), so every rider shape that already reads a condition reads
this one too:

- Exquisite Firecraft: "... this spell can't be countered." - a static ability
  of the spell that functions on the stack (CR 113.6g, CR 604.5), read by
  `casting_restrictions.cannot_be_countered` as the counterspell resolves
  (CR 701.6a).
- Fiery Impulse (proof printing): "... Fiery Impulse deals 3 damage instead."
  (CR 614.1a).
- Unholy Hunger (proof printing): "Destroy target creature. / ... you gain 2
  life." - a plain conditional instruction (CR 608.2c).

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file: 207.2c, 113.6g, 604.5, 701.6a, 614.1a, 608.2c.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

TWO_SPELLS = ["Lightning Bolt", "Preordain"]


def _board(hand: list[str], graveyard: list[str], lands: int = 2, bob_hand=None) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            library=["Forest"],
            hand=hand,
            battlefield=["Mountain"] * lands,
            graveyard=graveyard,
        )
        .player(
            "bob",
            library=["Forest"],
            hand=bob_hand or [],
            battlefield=["Serra Angel", "Island", "Island"],
        )
    )


# -- the condition itself: what counts ---------------------------------------


def test_fiery_impulse_deals_two_without_spell_mastery():
    scenario = _board(["Fiery Impulse"], ["Lightning Bolt"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    (mountain,) = scenario.untapped_sources("Mountain")

    scenario.cast_and_resolve("Fiery Impulse", mountain, targets=[angel])

    assert angel.damage == 2


def test_fiery_impulse_deals_three_with_an_instant_and_a_sorcery():
    """ "instant and/or sorcery" - one of each counts as two."""
    scenario = _board(["Fiery Impulse"], TWO_SPELLS).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    (mountain,) = scenario.untapped_sources("Mountain")

    scenario.cast_and_resolve("Fiery Impulse", mountain, targets=[angel])

    assert angel.damage == 3


def test_two_instants_count_as_well():
    scenario = _board(["Fiery Impulse"], ["Lightning Bolt", "Lightning Bolt"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    (mountain,) = scenario.untapped_sources("Mountain")

    scenario.cast_and_resolve("Fiery Impulse", mountain, targets=[angel])

    assert angel.damage == 3


def test_other_card_types_do_not_count():
    """A creature card and a land card beside one instant are still only one
    instant or sorcery card."""
    scenario = _board(["Fiery Impulse"], ["Lightning Bolt", "Grizzly Bears", "Forest"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    (mountain,) = scenario.untapped_sources("Mountain")

    scenario.cast_and_resolve("Fiery Impulse", mountain, targets=[angel])

    assert angel.damage == 2


def test_only_your_own_graveyard_counts():
    scenario = (
        Scenario()
        .player("alice", library=["Forest"], hand=["Fiery Impulse"], battlefield=["Mountain"])
        .player("bob", library=["Forest"], battlefield=["Serra Angel"], graveyard=TWO_SPELLS)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    (mountain,) = scenario.untapped_sources("Mountain")

    scenario.cast_and_resolve("Fiery Impulse", mountain, targets=[angel])

    assert angel.damage == 2


# -- a conditional additional instruction -------------------------------------


def test_unholy_hunger_gains_life_only_with_spell_mastery():
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest"],
            hand=["Unholy Hunger"],
            battlefield=["Swamp"] * 5,
            graveyard=TWO_SPELLS,
        )
        .player("bob", library=["Forest"], battlefield=["Serra Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    swamps = scenario.untapped_sources(*["Swamp"] * 5)

    scenario.cast_and_resolve("Unholy Hunger", *swamps, targets=[angel])

    assert angel.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 22


def test_unholy_hunger_without_spell_mastery_only_destroys():
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest"],
            hand=["Unholy Hunger"],
            battlefield=["Swamp"] * 5,
            graveyard=["Preordain"],
        )
        .player("bob", library=["Forest"], battlefield=["Serra Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    swamps = scenario.untapped_sources(*["Swamp"] * 5)

    scenario.cast_and_resolve("Unholy Hunger", *swamps, targets=[angel])

    assert angel.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 20


# -- Exquisite Firecraft: "this spell can't be countered" ---------------------


def _firecraft_countered(graveyard: list[str]) -> tuple:
    scenario = _board(
        ["Exquisite Firecraft"], graveyard, lands=4, bob_hand=["Counterspell"]
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mountains = scenario.untapped_sources(*["Mountain"] * 4)
    firecraft = scenario.cast_onto_stack(
        "Exquisite Firecraft", *mountains, targets=["bob"], username="alice"
    )
    scenario.pass_priority("alice")
    islands = scenario.untapped_sources("Island", "Island", username="bob")
    scenario.cast_onto_stack("Counterspell", *islands, username="bob", targets=[firecraft])
    scenario.pass_until_resolved()  # Counterspell
    return scenario, firecraft


def test_firecraft_is_countered_without_spell_mastery():
    scenario, firecraft = _firecraft_countered(["Lightning Bolt"])

    assert firecraft.zone is Zone.GRAVEYARD
    assert scenario.stack_names() == []
    assert scenario.player("bob").life == 20


def test_firecraft_cannot_be_countered_with_spell_mastery():
    """CR 113.6g: the ability functions on the stack. CR 701.6a's counter does
    nothing to it, so it stays there and then resolves for its 4 damage."""
    scenario, firecraft = _firecraft_countered(TWO_SPELLS)

    assert firecraft.zone is Zone.STACK
    scenario.pass_until_resolved()
    assert scenario.player("bob").life == 16


def test_firecraft_deals_four_to_a_creature():
    scenario = _board(["Exquisite Firecraft"], [], lands=4).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    mountains = scenario.untapped_sources(*["Mountain"] * 4)

    scenario.cast_and_resolve("Exquisite Firecraft", *mountains, targets=[angel])

    assert angel.zone is Zone.GRAVEYARD
