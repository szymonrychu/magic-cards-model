"""The Modern "hollow one" archetype as a real, registered sixty.

The list is hockeybro26's, from the 2026-08-29 event recorded as source deck
`videre-58656118` - a list that sums cleanly to 60 mainboard and 15 sideboard
with no duplicated rows, and every one of its twenty-six distinct names checked
Modern-legal with `resolve_cards(format="modern", fields="legality")` in the
session that added it. Every printing here comes from `tests/fixtures/cards`.

This file is the archetype's *deck* smoke test, not its mechanics test: it
proves the list is a legal deck under CR 100.2a / 100.4a and that a game
dealt from it obeys CR 103 - the deck becomes a library (CR 401.1), it is
shuffled (CR 103.3), and each player draws a starting hand of seven (CR 103.5),
leaving fifty-three cards behind. The sideboard is set aside rather than
shuffled in (CR 103.2a).

What this file deliberately does *not* claim is that the whole archetype's
engine works. Hollow One's own "costs {2} less to cast for each card you've
cycled or discarded this turn" now *is* a shape `Game.cost_reduction_for`
reads (CR 601.2f), counted by `Game.cards_discarded_this_turn`, and the test
at the bottom of this file asserts it. What is still missing is Vengevine's
"whenever you cast a spell, if it's the second creature spell you cast this
turn" (CR 603.4's intervening-if shape), which reaches a dispatcher that
returns nothing - the remaining `xfail`, per the project rule that a missing
rule is an `xfail`, never a reshaped scenario. `docs/deck-gaps/hollow-one.md`
records the archetype's gaps.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Deck, Game, Match, Player, Zone
from tests.cards import card

#: hockeybro26, 2026-08-29, source deck videre-58656118. Sixty cards.
HOLLOW_ONE_SIXTY = {
    "Arena of Glory": 1,
    "Bloodstained Mire": 3,
    "Blazing Rootwalla": 4,
    "Faithless Looting": 4,
    "Burning Inquiry": 4,
    "Detective's Phoenix": 4,
    "Elegant Parlor": 1,
    "Sacred Foundry": 4,
    "Hardened Academic": 4,
    "Hollow One": 4,
    "Mountain": 2,
    "Marauding Mako": 4,
    "Lightning Bolt": 4,
    "Practiced Offense": 2,
    "Scalding Tarn": 2,
    "Street Wraith": 4,
    "Vengevine": 4,
    "Wooded Foothills": 2,
    "Arid Mesa": 3,
}

#: The same list's fifteen-card sideboard.
HOLLOW_ONE_SIDEBOARD = {
    "Damping Sphere": 2,
    "Enter the Avatar State": 2,
    "Prismatic Ending": 2,
    "Rough // Tumble": 2,
    "Vexing Bauble": 2,
    "Wear // Tear": 2,
    "Surgical Extraction": 3,
}

#: An opposing sixty that shares no card with the list above, so "this card
#: came from the hollow one deck" is a decidable question in a dealt game.
OPPOSING_SIXTY = {
    "Forest": 26,
    "Island": 14,
    "Llanowar Elves": 4,
    "Birds of Paradise": 4,
    "Giant Growth": 4,
    "Grizzly Bears": 4,
    "Chromatic Lantern": 4,
}


def hollow_one() -> Deck:
    return Deck(mainboard=dict(HOLLOW_ONE_SIXTY), sideboard=dict(HOLLOW_ONE_SIDEBOARD))


def match(seed: int | str = "hollow-one") -> Match:
    series = Match(
        players=[Player(username="alice"), Player(username="bob")],
        card_resolver=card,
        seed=seed,
    )
    series.register_deck("alice", hollow_one())
    series.register_deck("bob", Deck(mainboard=dict(OPPOSING_SIXTY)))
    return series


# -- the list is a deck (CR 100.2a, 100.4a) --------------------------------


def test_the_registered_list_is_a_legal_constructed_deck():
    """CR 100.2a: sixty cards, at most four of anything but a basic land.
    CR 100.4a: a constructed sideboard is at most fifteen cards."""
    deck = hollow_one()

    assert deck.mainboard_size == 60
    assert sum(HOLLOW_ONE_SIDEBOARD.values()) == 15
    assert deck.problems(card) == []
    assert deck.is_legal(card)
    deck.check_legality(card)


def test_every_name_in_the_list_resolves_to_a_real_printing():
    """No hand-written card data: each of the twenty-six names is a fixture.

    The two split cards are the reason this is worth asserting separately -
    a split card is one card with two faces (CR 709.3), and its printed name
    carries both halves.
    """
    names = set(HOLLOW_ONE_SIXTY) | set(HOLLOW_ONE_SIDEBOARD)

    assert len(names) == 26
    assert {card(name).name for name in names} == names
    assert card("Rough // Tumble").card_faces is not None
    assert card("Wear // Tear").card_faces is not None


# -- dealing a game from it (CR 103) ---------------------------------------


def test_a_game_dealt_from_the_list_opens_on_seven_and_fifty_three():
    """CR 401.1: the deck becomes the library. CR 103.5: each player draws a
    starting hand of seven, which is normally seven cards."""
    game = match().start_game()
    alice = game.player("alice")

    assert len(alice.hand) == 7
    assert len(alice.library) == 53
    assert len(alice.hand) + len(alice.library) == 60
    assert all(state.zone is Zone.HAND for state in alice.hand)
    assert all(state.name in HOLLOW_ONE_SIXTY for state in alice.hand + alice.library)


def test_the_opponent_draws_seven_from_their_own_deck():
    """CR 103.5 applies to each player; nothing crosses between libraries."""
    game = match().start_game()
    bob = game.player("bob")

    assert len(bob.hand) == 7
    assert len(bob.library) == 53
    assert all(state.name in OPPOSING_SIXTY for state in bob.hand + bob.library)
    assert "Hollow One" not in {state.name for state in bob.hand + bob.library}


def test_the_sideboard_is_set_aside_rather_than_shuffled_in():
    """CR 103.2a: sideboard cards start outside the game."""
    game = match().start_game()
    alice = game.player("alice")

    assert len(alice.sideboard) == 15
    assert all(state.zone is Zone.SIDEBOARD for state in alice.sideboard)
    assert "Surgical Extraction" not in {state.name for state in alice.library}


def test_the_four_hollow_ones_are_four_separate_cards():
    """Four copies are four objects sharing one immutable printing."""
    game = match().start_game()
    alice = game.player("alice")

    golems = [s for s in alice.hand + alice.library if s.name == "Hollow One"]

    assert len(golems) == 4
    assert len({state.id for state in golems}) == 4
    assert len({id(state.card) for state in golems}) == 1


def test_shuffling_is_seeded_and_reproducible():
    """CR 103.3: the deck is shuffled into a random order - which for a test
    means a *reproducible* random order, not an unexamined one."""
    first = [state.name for state in match(seed="a").start_game().player("alice").library]
    second = [state.name for state in match(seed="a").start_game().player("alice").library]
    other = [state.name for state in match(seed="b").start_game().player("alice").library]

    assert first == second
    assert first != other


def test_the_game_starts_at_untap_on_twenty_life():
    """CR 103.4: each player begins on a starting life total of 20.
    CR 103.8: the starting player takes their first turn."""
    game = match().start_game()

    assert isinstance(game, Game)
    assert game.turn is not None
    # CR 103.5 first: a dealt game rests in the mulligan step, before any turn.
    assert game.turn.step is Step.MULLIGAN
    assert game.turn.turn_number == 0

    game.settle_pregame()

    # CR 103.8: the starting player takes their first turn, which begins at untap.
    assert game.turn.step is Step.UNTAP
    assert all(player.life == 20 for player in game.players)


# -- what the archetype cannot yet do -------------------------------------


def test_hollow_one_is_cheaper_after_a_discard():
    """CR 601.2f: cost reductions apply when the total cost is determined.

    One card discarded (CR 701.9a) takes {2} off the golem - the reduction
    `Game.cards_discarded_this_turn` now counts for.
    """
    from magic_cards_model.models.mana import ManaCost

    game = match().start_game()
    alice = game.player("alice")
    golem = next(state for state in alice.library if state.name == "Hollow One")
    game.discard_cards("alice", [alice.hand[0]])

    reduction = game.cost_reduction_for(golem, "alice")

    assert reduction == ManaCost.parse("{2}")


def test_vengevine_has_a_recursion_effect_to_run():
    """CR 603.4: the intervening-if clause is checked, then the effect runs -
    but only if there is an effect to run at all.

    This was `xfail(strict=True)` while `trigger_effect_for` answered `None`.
    The return itself was always readable; what was missing was a "you may"
    over a *board* instruction (CR 608.2d) - the optional wrapper only ever
    covered the plain-player vocabulary of life totals, draws and mills.
    """
    from magic_cards_model.machines.abilities import TriggeredAbility, parse_abilities
    from magic_cards_model.machines.effects import trigger_effect_for

    vengevine = card("Vengevine")
    (trigger,) = [a for a in parse_abilities(vengevine) if isinstance(a, TriggeredAbility)]

    assert trigger.event is not None
    assert trigger_effect_for(vengevine.name, trigger.event, trigger.effect) is not None
