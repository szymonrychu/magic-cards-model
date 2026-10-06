"""Scenario: Molten Psyche - each player wheels, then metalcraft damage per opponent.

"Each player shuffles the cards from their hand into their library, then draws
that many cards. Metalcraft - If you control three or more artifacts, Molten
Psyche deals damage to each opponent equal to the number of cards that player
has drawn this turn."

Molten Psyche is the only Modern/Pioneer/Standard printing of both halves
(Scryfall `o:/shuffles the cards from their hand into their library/` and
`o:/damage to each opponent equal to the number of cards that player has drawn/`
return it alone); the draw-count amount is the per-opponent counted read, so
every opponent takes their own total.

Verified this session with `mise run rules:find`:

- **CR 701.24a** - shuffling randomizes the library so no player knows its order.
- **CR 121.2** - draws happen one at a time; each of the n draws is its own.
- **CR 608.2c** - "that many" is each player's own count of cards put into the
  library, and instructions happen in the order written.
- **CR 207.2c** - metalcraft is an ability word with no rules meaning of its
  own; the "If you control three or more artifacts" is checked on resolution.
- **CR 120.3a** - damage to a player makes them lose that much life.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario

_ARTIFACTS = ["Sol Ring", "Ornithopter", "Bonesplitter"]


def _board(
    *,
    artifacts=_ARTIFACTS,
    alice_extra_hand=(),
    bob_hand=(),
    bob_library=("Island",) * 8,
    carol_hand=None,
):
    builder = (
        Scenario()
        .player(
            "alice",
            life=20,
            hand=["Molten Psyche", *alice_extra_hand],
            battlefield=["Mountain", "Mountain", "Mountain", *artifacts],
            library=["Mountain"] * 8,
        )
        .player("bob", life=20, hand=list(bob_hand), library=list(bob_library))
    )
    if carol_hand is not None:
        builder = builder.player("carol", life=20, hand=list(carol_hand), library=["Swamp"] * 8)
    scenario = builder.build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast(scenario):
    scenario.cast_and_resolve(
        "Molten Psyche", *scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    )


def _hand_names(scenario, username):
    return sorted(card.name for card in scenario.player(username).hand)


def test_each_player_puts_their_hand_in_the_library_and_draws_that_many():
    scenario = _board(
        alice_extra_hand=["Plains", "Plains"],
        bob_hand=["Forest", "Forest", "Forest"],
        bob_library=["Island"] * 8,
    )
    _cast(scenario)

    assert len(scenario.player("alice").hand) == 2, "alice's hand after casting held two cards"
    assert len(scenario.player("bob").hand) == 3
    assert len(scenario.player("bob").library) == 8
    assert len(scenario.player("alice").library) == 8


def test_metalcraft_deals_each_opponent_the_cards_they_drew():
    scenario = _board(bob_hand=["Forest"] * 4)
    _cast(scenario)

    assert scenario.player("bob").life == 16, "bob drew four cards this turn"
    assert scenario.player("alice").life == 20, "the caster is not an opponent"


def test_the_amount_counts_every_card_drawn_this_turn_not_only_the_wheel():
    scenario = _board(bob_hand=["Forest", "Forest"])
    scenario.draw(1, username="bob")
    _cast(scenario)

    assert scenario.player("bob").life == 16, "one earlier draw plus a wheel of three"


def test_without_metalcraft_the_wheel_still_happens_and_nobody_is_damaged():
    scenario = _board(artifacts=["Sol Ring", "Ornithopter"], bob_hand=["Forest"] * 3)
    _cast(scenario)

    assert len(scenario.player("bob").hand) == 3
    assert scenario.player("bob").life == 20


def test_an_empty_hand_draws_nothing_and_takes_nothing():
    scenario = _board(bob_hand=[])
    _cast(scenario)

    assert scenario.player("bob").hand == []
    assert scenario.player("bob").life == 20


def test_each_opponent_takes_their_own_count():
    scenario = _board(bob_hand=["Forest"] * 2, carol_hand=["Swamp"] * 5)
    _cast(scenario)

    assert scenario.player("bob").life == 18
    assert scenario.player("carol").life == 15


def test_the_old_hand_cards_are_in_the_library_after_the_shuffle():
    """Distinct hand cards go into the library and nothing is left in the hand
    that was not drawn back: the library plus hand still hold every card."""
    scenario = _board(bob_hand=["Forest", "Island", "Swamp"], bob_library=("Plains",) * 5)
    _cast(scenario)

    bob = scenario.player("bob")
    assert len(bob.hand) == 3 and len(bob.library) == 5
    assert sorted(c.name for c in bob.hand + bob.library).count("Forest") == 1


def test_a_player_with_an_empty_library_draws_back_exactly_the_cards_put_in():
    """The hand goes into an otherwise empty library and is drawn back: no
    draw from an empty library is ever attempted."""
    scenario = _board(bob_hand=["Forest", "Forest"], bob_library=())
    _cast(scenario)
    scenario.state_based_actions()

    assert len(scenario.player("bob").hand) == 2
    assert scenario.player("bob").life == 18
    assert scenario.player("bob").library == []


def test_the_wheel_puts_cards_in_the_library_not_the_graveyard():
    scenario = _board(bob_hand=["Forest", "Island"])
    _cast(scenario)

    assert scenario.player("bob").graveyard == []
    assert not any(card.zone is Zone.GRAVEYARD for card in scenario.player("bob").hand)
