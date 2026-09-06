"""`Match.card_resolver` (CR 103.5 needs one to deal a real opening hand) is a
plain callable - `Callable[[str], Card]` - so it is `exclude=True` and a
`Match` rebuilt from a `model_dump`/`model_validate` round trip never has one,
even though its registered decklists and shuffle seed all survive fine.
`register_card_resolver` / `Match.bind_card_resolver` (`models/match.py`) is
the fix: name the resolver once, and a decoded `Match` can ask for it back by
that name.

`start_game` needing a resolver to load a deck at all is why a `Match` with no
resolver bound cannot deal a real opening hand - this file's whole point is
proving a *decoded* one can.
"""

from magic_cards_model.models import Deck, Match, Player
from magic_cards_model.models.match import register_card_resolver
from tests.cards import card

BURN_SIXTY = {
    "Mountain": 24,
    "Plains": 12,
    "Lightning Bolt": 4,
    "Grizzly Bears": 4,
    "Sol Ring": 4,
    "Questing Beast": 4,
    "Swords to Plowshares": 4,
    "Counterspell": 4,
}

RESOLVER_NAME = "tests.cards.card"

register_card_resolver(RESOLVER_NAME, card)


def test_a_decoded_match_can_deal_an_opening_hand():
    series = Match(
        players=[Player(username="alice"), Player(username="bob")],
        card_resolver=card,
        card_resolver_name=RESOLVER_NAME,
        seed="t7-card-resolver",
    )
    series.register_deck("alice", Deck(mainboard=BURN_SIXTY))

    dumped = series.model_dump(mode="json")
    assert "card_resolver" not in dumped, "the callable itself is not serializable"
    assert dumped["card_resolver_name"] == RESOLVER_NAME, "the name is what survives"

    decoded = Match.model_validate(dumped)
    assert decoded.card_resolver is None, "nothing has re-injected it yet"

    decoded.bind_card_resolver()
    assert decoded.card_resolver is card

    game = decoded.start_game()

    alice = game.player("alice")
    assert len(alice.hand) == 7, "CR 103.5's opening hand, dealt from a resolved decklist"
    assert len(alice.library) == 53
    assert all(state.card.name in BURN_SIXTY for state in alice.hand)


def test_bind_card_resolver_accepts_an_explicit_name_override():
    """A caller re-homing a decoded `Match` onto a resolver registered under a
    different name than the one it shipped with still has a way in - and the
    override is written back onto `card_resolver_name`.
    """
    series = Match(players=[Player(username="alice"), Player(username="bob")])
    dumped = series.model_dump(mode="json")
    assert dumped["card_resolver_name"] is None

    decoded = Match.model_validate(dumped)
    decoded.bind_card_resolver(RESOLVER_NAME)

    assert decoded.card_resolver is card
    assert decoded.card_resolver_name == RESOLVER_NAME


def test_bind_card_resolver_refuses_an_unregistered_name():
    series = Match(players=[Player(username="alice"), Player(username="bob")])

    try:
        series.bind_card_resolver("not-a-registered-resolver")
    except KeyError as error:
        assert "not-a-registered-resolver" in str(error)
    else:
        raise AssertionError("expected a KeyError for an unregistered resolver name")


def test_bind_card_resolver_with_nothing_to_go_on_refuses():
    series = Match(players=[Player(username="alice"), Player(username="bob")])

    try:
        series.bind_card_resolver()
    except ValueError as error:
        assert "card_resolver_name" in str(error)
    else:
        raise AssertionError("expected a ValueError with no name to bind")
