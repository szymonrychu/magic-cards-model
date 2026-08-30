"""Scenario: "Imprint" (CR 207.2c) and its "exiled with this permanent" shape.

Ugin's Labyrinth: "Imprint — When this land enters, you may exile a colorless
card with mana value 7 or greater from your hand.\n{T}: Add {C}. If a card is
exiled with this land, add {C}{C} instead.\n{T}: Return the exiled card to its
owner's hand."

This is the defect a live game log turned up: the land's enters-the-battlefield
trigger used to resolve with `changed: false` and no `decide` entry anywhere
between the land entering and its trigger resolving - the "you may" was never
offered at all, so the land's own mana ability silently produced half its
printed amount for the rest of the game. `machines/effects.py`'s
`_parse_imprint_clause` and `_parse_return_imprinted_clause` are the fix, read
off the ability's own printed text with no per-card registry row.

Every CR number here was looked up with `knowledge_search(q="...", type="rules")`
in the session that wrote this file:

- **CR 207.2c** - "An ability word appears in italics at the beginning of some
  abilities. Ability words ... have no special rules meaning" - "Imprint" is
  one, so nothing here reads the word itself, only the sentence after it.
- **CR 608.2d** - "If an effect of a spell or ability offers any choices ...
  the player announces these while applying the effect. The player can't
  choose an option that's illegal or impossible" - the exile is a plain "you
  may" that becomes illegal, not merely declined, once no legal card is in
  hand.
- **CR 605.1a** - the base mana ability, and the conditional "add X instead"
  clause `ManaCondition.imprinted` reads.
- **CR 105.2c** - "A colorless object has no color" - the quality Devourer of
  Destiny (colorless, mana value 7) satisfies and Lightning Bolt (red) does not.

`tests/fixtures/cards/ugins_labyrinth... ` - actually stored as
`ugin_s_labyrinth.json` - and `devourer_of_destiny.json` are the real Scryfall
printings this file plays with; no card text is hand-written.

A sweep of `tests/fixtures/cards` for "you may exile ... from your hand" and
for the `Imprint` keyword turned up exactly one card carrying this shape -
Ugin's Labyrinth itself. The Force of Vigor/Force of Negation/Act of
Authority/March of Otherworldly Light/Ajani, Nacatl Pariah hits on the same
substring are a different shape entirely (an alternative *cost*, or a targeted
"you may exile" with no persisting link) and are genuine exceptions, not
covered here.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Color, Zone
from magic_cards_model.models.card_state import ExileMarker

from .harness import Scenario

# --------------------------------------------------------------------------
# The enters-the-battlefield choice itself (CR 608.2d)
# --------------------------------------------------------------------------


def test_taking_the_imprint_exiles_the_chosen_card_and_links_it_to_the_land():
    """Taking the "you may": Devourer of Destiny (colorless, mana value 7) is
    a legal choice and is actually exiled, linked back to the land by
    `ExileMarker.IMPRINTED`.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Ugin's Labyrinth", "Devourer of Destiny", "Lightning Bolt"],
            battlefield=[],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    devourer = scenario.find("Devourer of Destiny", Zone.HAND, "alice")
    scenario.will_take_the_may(True, source="Ugin's Labyrinth")
    scenario.will_discard(devourer, username="alice")

    land = scenario.play_land("Ugin's Labyrinth", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert devourer.zone is Zone.EXILE
    assert devourer not in alice.hand
    assert devourer in scenario.game.exile
    annotation = devourer.exile_annotation
    assert annotation is not None
    assert annotation.marker is ExileMarker.IMPRINTED
    assert annotation.linked_permanent_id == land.id


def test_declining_the_imprint_leaves_the_card_in_hand():
    """Declining is legal (CR 608.2d): Devourer of Destiny stays put."""
    scenario = (
        Scenario()
        .player("alice", hand=["Ugin's Labyrinth", "Devourer of Destiny"], battlefield=[])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    scenario.will_take_the_may(False, source="Ugin's Labyrinth")

    scenario.play_land("Ugin's Labyrinth", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert [state.name for state in alice.hand] == ["Devourer of Destiny"]
    assert scenario.game.exile == []


def test_no_legal_card_in_hand_makes_the_choice_illegal_not_merely_declined():
    """Only Lightning Bolt (red, mana value 1) is in hand - neither colorless
    nor mana value 7 or greater, so CR 608.2d makes "yes" impossible, not just
    unappealing. The question is still put (so a scenario can tell "nothing to
    decide" from "never asked"), but its affirmative branch is not legal, and
    nobody answering it defaults to "no" rather than raising.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Ugin's Labyrinth", "Lightning Bolt"], battlefield=["Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")

    scenario.play_land("Ugin's Labyrinth", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    asked = [q for q in scenario.questions_asked() if q.kind is DecisionKind.MAY]
    assert len(asked) == 1
    assert asked[0].affirmative_is_legal is False
    assert [state.name for state in alice.hand] == ["Lightning Bolt"]
    assert scenario.game.exile == []


def test_the_imprint_defaults_to_taking_it_unscripted():
    """No answer queued: `default_answer` takes `MAY`'s affirmative branch
    whenever it is legal, the same default every other "you may" trigger uses.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Ugin's Labyrinth", "Devourer of Destiny"], battlefield=[])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")

    scenario.play_land("Ugin's Labyrinth", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert alice.hand == []
    (exiled,) = scenario.game.exile
    assert exiled.name == "Devourer of Destiny"


# --------------------------------------------------------------------------
# The conditional mana ability that reads the link back (CR 605.1a)
# --------------------------------------------------------------------------


def test_the_land_taps_for_the_base_amount_with_nothing_imprinted():
    scenario = Scenario().player("alice", battlefield=["Ugin's Labyrinth"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (land,) = scenario.untapped_sources("Ugin's Labyrinth")

    scenario.activate(land)

    assert scenario.player().mana_pool.floating == {Color.COLORLESS: 1}
    assert scenario.stack_names() == []


def test_the_land_taps_for_the_bonus_amount_once_a_card_is_imprinted():
    """The end-to-end proof: imprint for real, then tap, and the conditional
    mana clause (`ManaCondition.imprinted`) reads the link `Game.
    card_imprinted_on` finds, not a hardcoded amount.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Ugin's Labyrinth", "Devourer of Destiny"], battlefield=[])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(True, source="Ugin's Labyrinth")
    devourer = scenario.find("Devourer of Destiny", Zone.HAND, "alice")
    scenario.will_discard(devourer, username="alice")

    land = scenario.play_land("Ugin's Labyrinth", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()
    assert land.untapped, "CR 305: a land does not enter tapped unless told to"

    scenario.activate(land)

    assert scenario.player("alice").mana_pool.floating == {Color.COLORLESS: 2}
    assert scenario.stack_names() == [], "CR 605.3b: a mana ability never uses the stack"


# --------------------------------------------------------------------------
# Giving the linked card back (the land's third ability)
# --------------------------------------------------------------------------


def test_returning_the_imprinted_card_to_its_owners_hand():
    scenario = (
        Scenario()
        .player("alice", hand=["Ugin's Labyrinth", "Devourer of Destiny"], battlefield=[])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    scenario.will_take_the_may(True, source="Ugin's Labyrinth")
    devourer = scenario.find("Devourer of Destiny", Zone.HAND, "alice")
    scenario.will_discard(devourer, username="alice")

    land = scenario.play_land("Ugin's Labyrinth", "alice")
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()
    assert devourer.zone is Zone.EXILE

    scenario.activate(land, index=1)
    scenario.resolve_top()

    assert devourer.zone is Zone.HAND
    assert devourer in alice.hand
    assert devourer not in scenario.game.exile
    assert devourer.exile_annotation is None, "CR 400.7: a new object, the link included"


def test_returning_with_nothing_imprinted_does_nothing():
    """CR 608.2b's "the effect does as much as possible": no card was ever
    linked to this land, so the ability finds nothing and changes nothing -
    not an error.
    """
    scenario = Scenario().player("alice", battlefield=["Ugin's Labyrinth"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    (land,) = scenario.untapped_sources("Ugin's Labyrinth")

    scenario.activate(land, index=1)
    scenario.resolve_top()

    assert alice.hand == []
    assert scenario.game.exile == []
    assert land.tapped
