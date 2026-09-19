"""A plain "Each opponent discards N cards." with no consequence attached
(CR 701.9a, CR 102.2) - the shortfall-variant's sibling
(`test_each_opponent_discards_then_shortfall.py`), which already covers
`_each_opponent_discards_and_count_shortfalls`'s own antecedent but only
ever through a two-part sentence naming a shortfall consequence
("For each opponent who didn't discard ..., you draw a card."/"... loses 3
life."). This file is the bare instruction with no second half at all.

**Nicol Bolas, the Ravager** is the off-set proof: "When Nicol Bolas enters,
each opponent discards a card." - a plain enters trigger, one card, no
shortfall count, no "you choose" override, nothing after the period.

CR 701.9b: by default the discarding player chooses which card to discard -
unlike Thoughtseize's own overridden chooser
(`test_reveal_hand_and_choose.py`), nothing here names another chooser.
CR 609.3: a hand shorter than the printed count discards what it has rather
than the instruction failing outright.

Every CR number here was looked up with `mise run rules:find <number>` in
the session that wrote this file: CR 701.9a, 701.9b, 102.2, 609.3.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario

NICOL_BOLAS = "Nicol Bolas, the Ravager"


def test_each_opponent_discards_their_own_choice_of_one_card():
    """CR 701.9b's default chooser (the discarding player) picks which card,
    the same default `test_target_player_discards.py` already proves for a
    single named target - this is the identical default over "each
    opponent" instead of one chosen target."""
    scenario = (
        Scenario()
        .player("alice", hand=[NICOL_BOLAS], battlefield=["Island", "Swamp", "Mountain", "Plains"])
        .player("bob", hand=["Lightning Bolt", "Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "bob")
    forest = scenario.find("Forest", Zone.HAND, "bob")
    scenario.will_choose_cards(forest, username="bob", source=NICOL_BOLAS)

    sources = scenario.untapped_sources("Island", "Swamp", "Mountain", "Plains")
    scenario.cast_and_resolve(NICOL_BOLAS, *sources, username="alice")
    scenario.pass_until_resolved()

    assert forest.zone is Zone.GRAVEYARD, "bob's own chosen card was discarded"
    assert bolt.zone is Zone.HAND, "the card bob did not choose stays in hand"
    assert len(bob.hand) == 1


def test_an_opponent_with_an_empty_hand_discards_nothing():
    """CR 609.3: a hand shorter than the printed count discards what it has -
    zero, here - rather than the instruction failing to apply at all."""
    scenario = (
        Scenario()
        .player("alice", hand=[NICOL_BOLAS], battlefield=["Island", "Swamp", "Mountain", "Plains"])
        .player("bob", hand=[])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")

    sources = scenario.untapped_sources("Island", "Swamp", "Mountain", "Plains")
    scenario.cast_and_resolve(NICOL_BOLAS, *sources, username="alice")
    scenario.pass_until_resolved()

    assert bob.hand == []
