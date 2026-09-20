"""Scenario: "Reveal the top `<count>` cards of your library. Put all
`<quality>` cards revealed this way into your hand and the rest into your
graveyard." - Wrenn and Seven's own +1, word for word the same sentence
Mulch prints as a whole sorcery (off-pool, modern-legal). Every matching
card, mandatorily - unlike the "you may put a `<quality>` card from among
them" family (`_merge_reveal_top_to_hand_rest_to_graveyard_clauses`), which
is CR 608.2d's optional pick of at most one.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 701.20a** - "To reveal a card, show that card to all players for a
  brief time."
- **CR 701.20b** - "Revealing a card doesn't cause it to leave the zone
  it's in" - every revealed card is still in the library until this
  sentence's own instruction moves it.
- **CR 608.2c** - the resolving object's own instructions are followed in
  the order printed.
- **CR 205.2a** - land is a card type; which revealed cards qualify is a
  fixed instruction, not a choice.
- **CR 606.4** - a loyalty ability's cost, Wrenn and Seven's own +1.
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def test_wrenn_and_sevens_plus_one_puts_revealed_lands_to_hand_rest_to_graveyard():
    """Three lands and one nonland among the top four: Forest, Mountain, and
    Swamp go to alice's hand; Lightning Bolt goes to her graveyard."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Wrenn and Seven"],
            library=["Forest", "Lightning Bolt", "Mountain", "Swamp", "Island"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wrenn = scenario.creature("Wrenn and Seven", "alice")
    alice = scenario.player("alice")

    scenario.activate(wrenn, index=0)
    scenario.resolve_top()

    assert wrenn.loyalty == 6, "CR 606.4: +1 adds a loyalty counter"
    assert {c.name for c in alice.hand} == {"Forest", "Mountain", "Swamp"}
    assert {c.name for c in alice.graveyard} == {"Lightning Bolt"}
    assert [c.name for c in alice.library] == ["Island"], "only the top four were ever revealed"


def test_mulch_puts_revealed_lands_to_hand_rest_to_graveyard():
    """Mulch (off-pool, modern-legal): the identical sentence as a plain
    sorcery instead of a loyalty ability - proves the parser reads the
    mechanic, not Wrenn and Seven's own printed line.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Mulch"],
            battlefield=["Forest", "Forest"],
            library=["Plains", "Grizzly Bears", "Swamp", "Serra Angel"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest")
    alice = scenario.player("alice")

    scenario.cast_and_resolve("Mulch", *sources)

    assert {c.name for c in alice.hand} == {"Plains", "Swamp"}
    assert {c.name for c in alice.graveyard} == {"Mulch", "Grizzly Bears", "Serra Angel"}
    assert alice.library == []
