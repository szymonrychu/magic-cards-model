"""Graveyard Trespasser // Graveyard Glutton's own "enters or attacks, exile
... from a graveyard[s]" drain trigger (R0a T8).

Every CR number here was looked up with `mise run rules:find <number>` against
the 2026-09-25 Comprehensive Rules release in the session that wrote this
file.

- **CR 608.2c** - "The controller ... follows the instructions in the order
  written": the exile happens, then the conditional/counted drain reads what
  it actually exiled.
- **CR 400.7/CR 700.4** - whether an exiled card "is a creature card" is read
  off the card itself before it moves.
- **CR 119.3** - life loss and gain from the drain, CR 102.2's "each
  opponent" the drain's own scope.
- **CR 702.145a-b** - Daybound/Nightbound, and **CR 702.11a-d**'s Ward, are
  already `handled` per `scripts/sweep_pool.py --card "Graveyard Trespasser"`
  before this task - untouched here.

Graveyard Trespasser's front face: "Whenever this creature enters or
attacks, exile up to one target card from a graveyard. If a creature card
was exiled this way, each opponent loses 1 life and you gain 1 life." - the
binary form, running the drain once regardless of how many (0 or 1) creature
cards were exiled. Its night face Graveyard Glutton: "... exile up to two
target cards from graveyards. For each creature card exiled this way, each
opponent loses 1 life and you gain 1 life." - the count-scaled form, running
the drain once per creature card actually exiled (0, 1 or 2 times).

Generality is proven on Soul-Shackled Zombie (legal Modern/Pioneer/Standard,
not in `code/magic-cards-model-api/decks/*.txt`): "When this creature
enters, exile up to two target cards from a single graveyard. If at least
one creature card was exiled this way, each opponent loses 2 life and you
gain 2 life." - a different trigger event (enters only, not enters-or-
attacks), a different quantifier word ("at least one", not "a"), a "from a
single graveyard" zone restriction, and a different drain amount (2, not 1) -
none of it fitted to Graveyard Trespasser's own sentence.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

TRESPASSER = "Graveyard Trespasser"
ZOMBIE = "Soul-Shackled Zombie"


def _board(**kwargs) -> Scenario:
    return Scenario().player("alice", **kwargs)


def test_trespasser_drains_once_when_a_creature_card_is_exiled():
    """The front face's binary drain: exactly one creature card exiled,
    exactly one 1-life drain."""
    scenario = (
        _board(
            hand=[TRESPASSER],
            battlefield=["Swamp"] * 3,
        )
        .player("bob", graveyard=["Grizzly Bears"], life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob")
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp", username="alice")
    scenario.choose_trigger_targets(TRESPASSER, [bears])

    scenario.cast_and_resolve(TRESPASSER, *sources, username="alice")
    scenario.resolve_top()

    alice = scenario.player("alice")
    bob = scenario.player("bob")
    assert (alice.life, bob.life) == (21, 19)
    assert bears.zone is Zone.EXILE


def test_trespasser_drains_nothing_exiling_a_noncreature_card():
    """CR 107.1b: no creature card exiled is no drain at all - not a drain
    of zero, simply nothing."""
    scenario = (
        _board(hand=[TRESPASSER], battlefield=["Swamp"] * 3)
        .player("bob", graveyard=["Lightning Bolt"], life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "bob")
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp", username="alice")
    scenario.choose_trigger_targets(TRESPASSER, [bolt])

    scenario.cast_and_resolve(TRESPASSER, *sources, username="alice")
    scenario.resolve_top()

    alice = scenario.player("alice")
    bob = scenario.player("bob")
    assert (alice.life, bob.life) == (20, 20)
    assert bolt.zone is Zone.EXILE


def test_glutton_drains_twice_exiling_two_creature_cards():
    """The night face's count-scaled drain: two creature cards exiled, two
    1-life drains (not one drain of 2)."""
    scenario = (
        _board(battlefield=[TRESPASSER])
        .player("bob", graveyard=["Grizzly Bears", "Runeclaw Bear"], life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    glutton = scenario.find(TRESPASSER, Zone.BATTLEFIELD, "alice")
    glutton.transformed = True
    assert glutton.name == "Graveyard Glutton"
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob")
    other_bears = scenario.find("Runeclaw Bear", Zone.GRAVEYARD, "bob")

    scenario.choose_trigger_targets("Graveyard Glutton", [bears, other_bears])
    scenario.game.declare_attacker(glutton, "bob")
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    alice = scenario.player("alice")
    bob = scenario.player("bob")
    assert (alice.life, bob.life) == (22, 18)
    assert bears.zone is Zone.EXILE
    assert other_bears.zone is Zone.EXILE


def test_soul_shackled_zombie_drains_two_on_a_single_hit_from_a_single_graveyard():
    """Proof of generality: "at least one" phrasing, a "from a single
    graveyard" restriction, a different drain amount (2), and an enters-only
    trigger (no "or attacks")."""
    scenario = (
        _board(hand=[ZOMBIE], battlefield=["Swamp"] * 4)
        .player("bob", graveyard=["Grizzly Bears", "Lightning Bolt"], life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob")
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "bob")
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp", username="alice")
    scenario.choose_trigger_targets(ZOMBIE, [bears, bolt])

    scenario.cast_and_resolve(ZOMBIE, *sources, username="alice")
    scenario.resolve_top()

    alice = scenario.player("alice")
    bob = scenario.player("bob")
    # "If at least one" runs the drain exactly once even though two cards
    # were exiled and one of them was a creature card.
    assert (alice.life, bob.life) == (22, 18)
    assert bears.zone is Zone.EXILE
    assert bolt.zone is Zone.EXILE
