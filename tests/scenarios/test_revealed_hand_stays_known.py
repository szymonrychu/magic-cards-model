"""A hand shown by a resolving spell is a hand the viewers keep knowing, card
by card, until each card leaves it.

Two shapes put a whole hand in front of a player:

- **"Target player reveals their hand. You choose a ... card from it."**
  (Thoughtseize, Distress) - CR 701.20a: "To reveal a card, show that card to
  all players for a brief time." The whole hand is revealed, not only the
  cards the choice may take, so every card in it is recorded with no viewers
  (all players), and it is recorded before the choice is asked - the chooser
  picks out of a hand already shown.
- **"Look at target player's hand."** (Gitaxian Probe, Peek) - CR 701.20e:
  "Looking at a card follows the same rules as revealing a card, except that
  the card is shown only to the specified player." One record per card, with
  the looker as its only viewer.

CR 701.20b - "Revealing a card doesn't cause it to leave the zone it's in" -
is why these are records and nothing moves. CR 402.3 - "A player can't look
at the cards in another player's hand" - is why the target of a look learns
nothing from it. CR 400.7 - "An object that moves from one zone to another
becomes a new object with no memory of, or relation to, its previous
existence" - is why each record ends the moment its card leaves the hand, by
discard, by being cast (CR 601.2a moves it to the stack), or otherwise, and
why a card drawn into the hand afterwards was never shown at all.

Distress and Peek are here because neither is a reported card nor in any deck
pool: they prove the oracle-text reading, not a card.

Every scenario in this directory round-trips and replays through
`tests/scenarios/conftest.py`; `test_hand_knowledge_survives_a_round_trip`
also checks the decoded game answers `known_to` the same way.

Every CR number above was read in full with `mise run rules:find` in the
session that wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Game, Zone

from .harness import Scenario


def known(game: Game, viewer: str) -> list[tuple[str, Zone, bool]]:
    return sorted((entry.card_name, entry.zone, entry.carried) for entry in game.known_to(viewer))


def next_turn(scenario: Scenario) -> None:
    """Walk on into the following turn, resolving whatever fires."""
    turns = scenario.turn.turns_taken
    while scenario.turn.turns_taken == turns:
        scenario.advance()
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()


def _discard_spell_at(
    spell: str, land: str, bob_hand: list[str], take: str | None, **bob: list[str]
) -> Scenario:
    scenario = (
        Scenario()
        .player("alice", hand=[spell], battlefield=[land, land])
        .player("bob", hand=bob_hand, **bob)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    if take is not None:
        scenario.will_discard(scenario.find(take, Zone.HAND, "bob"), username="alice")
    card = scenario.find(spell, Zone.HAND, "alice")
    sources = scenario.untapped_sources(*[land] * int(card.mana_value))
    scenario.cast_and_resolve(spell, *sources, targets=["bob"])
    return scenario


def _look_spell_at(spell: str, bob_hand: list[str], **bob: list[str]) -> Scenario:
    scenario = (
        Scenario()
        .player("alice", hand=[spell], battlefield=["Island"], library=["Plains"])
        .player("bob", hand=bob_hand, **bob)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Island")
    scenario.cast_and_resolve(spell, *sources, targets=["bob"])
    return scenario


# -- a reveal (CR 701.20a) ----------------------------------------------------


def test_thoughtseize_reveals_every_card_in_the_hand_to_both_players():
    scenario = _discard_spell_at(
        "Thoughtseize", "Swamp", ["Lightning Bolt", "Forest", "Mountain"], take="Lightning Bolt"
    )
    game = scenario.game

    expected = [("Forest", Zone.HAND, False), ("Mountain", Zone.HAND, False)]
    assert known(game, "alice") == expected
    assert known(game, "bob") == expected
    assert sorted(r.card_name for r in game.reveals) == ["Forest", "Lightning Bolt", "Mountain"]
    for reveal in game.reveals:
        assert reveal.viewers is None, "CR 701.20a: shown to all players"
        assert reveal.zone is Zone.HAND
        assert reveal.revealed_by == "bob"
        assert reveal.source == "Thoughtseize"


def test_the_whole_hand_is_revealed_before_the_choice_takes_a_card():
    """The taken card's record names the hand, with the stamp it had there:
    it was written while the card still sat in the hand, before the choice
    moved it (CR 400.7 would have given it a new stamp in the graveyard)."""
    scenario = _discard_spell_at(
        "Thoughtseize", "Swamp", ["Lightning Bolt", "Forest"], take="Lightning Bolt"
    )
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "bob")

    (record,) = [r for r in scenario.game.reveals if r.card_id == bolt.id]
    assert record.zone is Zone.HAND
    assert record.zone_change_stamp is not None
    assert record.zone_change_stamp != bolt.zone_change_stamp


def test_the_card_the_choice_takes_is_no_longer_known():
    scenario = _discard_spell_at(
        "Thoughtseize", "Swamp", ["Lightning Bolt", "Forest"], take="Lightning Bolt"
    )

    assert "Lightning Bolt" not in [name for name, _, _ in known(scenario.game, "alice")]
    assert known(scenario.game, "alice") == [("Forest", Zone.HAND, False)]


def test_distress_reveals_every_card_too_and_not_only_the_nonland_ones():
    scenario = _discard_spell_at(
        "Distress", "Swamp", ["Counterspell", "Island", "Plains"], take="Counterspell"
    )

    expected = [("Island", Zone.HAND, False), ("Plains", Zone.HAND, False)]
    assert known(scenario.game, "alice") == expected
    assert known(scenario.game, "bob") == expected


def test_an_all_land_hand_is_still_revealed_though_nothing_can_be_chosen():
    """CR 608.2d: no nonland card, no choice - but the reveal still happened."""
    scenario = _discard_spell_at("Distress", "Swamp", ["Island", "Plains"], take=None)

    expected = [("Island", Zone.HAND, False), ("Plains", Zone.HAND, False)]
    assert known(scenario.game, "alice") == expected
    assert known(scenario.game, "bob") == expected


def test_untaken_cards_stay_known_across_turns_until_they_leave_the_hand():
    scenario = _discard_spell_at(
        "Thoughtseize",
        "Swamp",
        ["Lightning Bolt", "Forest", "Mountain"],
        take="Lightning Bolt",
        library=["Island", "Plains"],
    )
    game = scenario.game
    expected = [("Forest", Zone.HAND, False), ("Mountain", Zone.HAND, False)]

    next_turn(scenario)
    assert scenario.turn.active_player == "bob"
    next_turn(scenario)
    assert scenario.turn.active_player == "alice"
    assert known(game, "alice") == expected

    forest = scenario.find("Forest", Zone.HAND, "bob")
    game.discard_cards("bob", [forest])

    assert known(game, "alice") == [("Mountain", Zone.HAND, False)]
    assert known(game, "bob") == [("Mountain", Zone.HAND, False)]


def test_a_card_drawn_after_the_reveal_is_not_known():
    scenario = _discard_spell_at(
        "Thoughtseize",
        "Swamp",
        ["Lightning Bolt", "Forest"],
        take="Lightning Bolt",
        library=["Island"],
    )

    (drawn,) = scenario.draw(username="bob")

    assert drawn.name == "Island" and drawn.zone is Zone.HAND
    assert known(scenario.game, "alice") == [("Forest", Zone.HAND, False)]


def test_a_revealed_card_cast_from_hand_stops_being_known():
    scenario = _discard_spell_at(
        "Thoughtseize",
        "Swamp",
        ["Counterspell", "Lightning Bolt"],
        take="Counterspell",
        battlefield=["Mountain"],
    )
    game = scenario.game
    assert known(game, "alice") == [("Lightning Bolt", Zone.HAND, False)]

    scenario.pass_priority()
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    bolt = scenario.cast_onto_stack(
        "Lightning Bolt", mountain, username="bob", targets=[scenario.player("alice")]
    )

    assert bolt.zone is Zone.STACK
    assert known(game, "alice") == []
    assert known(game, "bob") == []


# -- a look (CR 701.20e) ------------------------------------------------------


def test_peek_makes_the_hand_known_to_the_looker_only():
    scenario = _look_spell_at("Peek", ["Lightning Bolt", "Forest"])
    game = scenario.game

    assert known(game, "alice") == [
        ("Forest", Zone.HAND, False),
        ("Lightning Bolt", Zone.HAND, False),
    ]
    assert known(game, "bob") == [], "CR 402.3: the look shows bob nothing new"
    assert sorted(r.card_name for r in game.reveals) == ["Forest", "Lightning Bolt"]
    for reveal in game.reveals:
        assert reveal.viewers == ["alice"]
        assert reveal.zone is Zone.HAND
        assert reveal.source == "Peek"


def test_gitaxian_probe_records_the_same_look():
    scenario = _look_spell_at("Gitaxian Probe", ["Lightning Bolt", "Forest"])

    assert known(scenario.game, "alice") == [
        ("Forest", Zone.HAND, False),
        ("Lightning Bolt", Zone.HAND, False),
    ]
    assert known(scenario.game, "bob") == []


def test_a_looked_at_card_that_leaves_the_hand_and_a_card_drawn_later_are_not_known():
    scenario = _look_spell_at("Peek", ["Lightning Bolt", "Forest"], library=["Island"])
    game = scenario.game

    game.discard_cards("bob", [scenario.find("Lightning Bolt", Zone.HAND, "bob")])
    scenario.draw(username="bob")

    assert known(game, "alice") == [("Forest", Zone.HAND, False)]


def test_looking_at_an_empty_hand_records_nothing():
    scenario = _look_spell_at("Peek", [])

    assert scenario.game.reveals == []
    assert known(scenario.game, "alice") == []


# -- round trip ---------------------------------------------------------------


def test_hand_knowledge_survives_a_round_trip():
    scenario = _discard_spell_at(
        "Thoughtseize", "Swamp", ["Lightning Bolt", "Forest", "Mountain"], take="Lightning Bolt"
    )
    game = scenario.game

    decoded = Game.model_validate(game.model_dump(mode="json"))

    assert known(decoded, "alice") == known(game, "alice")
    assert known(decoded, "bob") == known(game, "bob")
    assert decoded.reveals == game.reveals
