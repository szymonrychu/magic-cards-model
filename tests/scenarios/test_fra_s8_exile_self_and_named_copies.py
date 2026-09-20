"""FRA stream S8: "`<antecedent>`. [Then ]you may exile `<self>` and `<n>`
cards named `<name>` from your graveyard. If you do, `<consequence>`." - the
Approach cycle's own "a deck can have any number of cards named `<name>`"
template (CR 118.12's cost-paid-on-resolution "if you do", CR 201.5's
self-reference).

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file.

- **CR 118.12** - the exile is a cost paid as the spell resolves; "if you
  do" checks whether the player chose to pay it, not what it accomplished.
- **CR 201.5** - a card's own printed name, wherever it appears in its own
  text, always means itself.
- **CR 608.2b** - the resolving spell and every chosen graveyard copy are
  exiled together, as one instruction.
- **CR 701.23a/701.23d** - the consequence's own mandatory, one-card search.
- **CR 119.2/119.3** - Dragon's Approach's own damage to each opponent.

Sphinx's Approach's own whole text is the reported card: "Draw two cards.
Then you may exile this spell and four cards named Sphinx's Approach from
your graveyard. If you do, search your library for a Sphinx creature card,
put it onto the battlefield, then shuffle." Dragon's Approach (real,
non-FRA, non-pool) is the off-set proof: the identical shape with a
different antecedent (damage to each opponent, not a draw - which needed
its own new `damage_each_opponent_for_spell`, since the existing "deals N
damage to each opponent" reader was ability-only), a different searched
creature type, and the literal printed name spelled out for the self-exile
("exile Dragon's Approach") rather than "exile this spell" - proving the
merge reads either self-reference wording and either antecedent shape.

Along the way, "a `<subtype>` creature card" (Sphinx's Approach's own
consequence) surfaced a second, genuinely general gap: `_quality_word_
matcher`/`_search_quality_is_readable`/`_card_description_is_readable` read
a two-word search quality as a single unmatchable token unless the first
word was a colour adjective, so "a Sphinx creature card" - CR 205.3's own
open-ended subtype vocabulary qualifying a card type - matched nothing at
all. Fixed generally (`subtype_vocabulary()`, not this card's name) rather
than worked around.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_sphinxs_approach_draws_then_exiles_five_and_finds_a_sphinx():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Sphinx's Approach"],
            battlefield=["Island", "Island", "Island"],
            library=["Forest", "Mountain", "Vexing Sphinx", "Plains"],
            graveyard=["Sphinx's Approach"] * 4,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Island", "Island", "Island")
    alice = scenario.player("alice")
    hand_before = len(alice.hand)
    graveyard_copies = list(alice.graveyard)
    assert len(graveyard_copies) == 4

    scenario.will_choose_cards(*graveyard_copies, username="alice")
    scenario.will_take_the_may(True)
    scenario.cast_and_resolve("Sphinx's Approach", *sources)
    scenario.pass_until_resolved()

    # Casting itself removed Sphinx's Approach from the hand; the draw put
    # two more cards there, so the net is +1.
    assert len(alice.hand) == hand_before - 1 + 2
    assert not any(card.zone is Zone.GRAVEYARD for card in graveyard_copies), (
        "CR 608.2b: the resolving spell and all four graveyard copies were exiled together"
    )
    assert all(card.zone is Zone.EXILE for card in graveyard_copies)
    sphinx = scenario.find("Vexing Sphinx", Zone.BATTLEFIELD, "alice")
    assert sphinx.zone is Zone.BATTLEFIELD


def test_dragons_approach_deals_damage_then_exiles_and_finds_a_dragon():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Dragon's Approach"],
            battlefield=["Mountain", "Mountain", "Mountain"],
            library=["Slumbering Dragon", "Forest", "Plains"],
            graveyard=["Dragon's Approach"] * 4,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    alice = scenario.player("alice")
    bob = scenario.player("bob")
    bob_life_before = bob.life
    graveyard_copies = list(alice.graveyard)

    scenario.will_choose_cards(*graveyard_copies, username="alice")
    scenario.will_take_the_may(True)
    scenario.cast_and_resolve("Dragon's Approach", *sources)
    scenario.pass_until_resolved()

    assert bob.life == bob_life_before - 3, "the antecedent's own damage to each opponent"
    assert all(card.zone is Zone.EXILE for card in graveyard_copies)
    dragon = scenario.find("Slumbering Dragon", Zone.BATTLEFIELD, "alice")
    assert dragon.zone is Zone.BATTLEFIELD


def test_declining_the_exile_leaves_the_graveyard_copies_untouched():
    """CR 118.12: declining the optional cost means "if you do" is false, so
    neither the exile nor the search happens - the antecedent still ran."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Sphinx's Approach"],
            battlefield=["Island", "Island", "Island"],
            library=["Forest", "Mountain", "Vexing Sphinx", "Plains"],
            graveyard=["Sphinx's Approach"] * 4,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Island", "Island", "Island")
    alice = scenario.player("alice")
    hand_before = len(alice.hand)
    graveyard_copies = list(alice.graveyard)

    scenario.will_take_the_may(False)
    scenario.cast_and_resolve("Sphinx's Approach", *sources)
    scenario.pass_until_resolved()

    assert len(alice.hand) == hand_before - 1 + 2, "the draw still happened"
    assert all(card.zone is Zone.GRAVEYARD for card in graveyard_copies)
    assert not any(p.name == "Vexing Sphinx" for p in scenario.game.battlefield)
