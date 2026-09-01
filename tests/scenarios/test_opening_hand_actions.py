"""Opening-hand actions: CR 103.6, between the mulligan and the first turn.

The mechanic this file covers is the *sequence*, not any one card: once
CR 103.5's mulligan process is complete and before CR 103.8's first turn, each
player may take the actions their opening hand allows.

Every CR number below was verified with `knowledge_search(q="...",
type="rules")` in the session that wrote this file. The search excerpts
truncate at roughly two hundred characters, so where a rule's tail is cut off
that is marked rather than filled in from memory:

- **CR 103.6** - "Some cards allow a player to take actions with them from
  their opening hand. Once the mulligan process (see rule 103.5) is complete,
  the starting player may take any such actions in any order. Then ea[ch other
  player ...]" (truncated). Three things are quoted and three things are
  tested: the sequence runs after the mulligan, the starting player goes first,
  and the actions are a "may".
- **CR 103.6a** - "If a card allows a player to begin the game with that card on
  the battlefield, the player taking this action puts that card onto the
  battlefield." The four Leylines and Gemstone Caverns.
- **CR 103.6b** - "If a card allows a player to reveal it from their opening
  hand, the player taking this action does so. The card remains revealed until
  the first turn begins. Each card may be revealed this way only on[ce ...]"
  (truncated). Devourer of Destiny.
- **CR 103.8** - "The starting player takes their first turn." Which is what
  makes Gemstone Caverns' "you're not the starting player" a real restriction.
- **CR 101.4** - "If multiple players would make choices and/or take actions at
  the same time, the active player (the player whose turn it is) makes any
  choices required, then the next player in turn order (usually the ..."
  (truncated). Checked and *not* applicable: no turn has begun, so there is no
  active player, and CR 103.6 states its own order.
- **CR 603.7** / **CR 603.7b** - the delayed triggered ability Devourer of
  Destiny's reveal creates, and why it fires only once.
- **CR 701.20a** / **CR 701.20b** - revealing shows a card and does not move it.
- **CR 122.1** - counters on a permanent, which is Gemstone Caverns' luck
  counter.

Two real registered lists supply the cards, reused rather than reinvented:
broodscale bloodchief (pilot **unagieel**, **2026-08-30**, deck
`videre-58656378`), which plays one Gemstone Caverns and two Devourers of
Destiny, and devoted combo (pilot **musasabi**, **2026-08-29**, deck
`videre-58655572`), which plays four Leylines of Abundance. Libraries are
rigged so the card in question is dealt - CR 103.3 staging, not a mock: every
card is the same real Scryfall printing the registered list names.
"""

from pathlib import Path

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import CardSplit, DecisionKind, ScriptedAnswer
from magic_cards_model.machines.opening_hand import (
    RIDERS,
    OpeningHandActionKind,
    read_opening_hand_actions,
)
from magic_cards_model.models import Card, Deck, Game, Match, Player, Zone
from tests.cards import card
from tests.scenarios.test_broodscale_bloodchief_deck import BROODSCALE_MAIN, BROODSCALE_SIDE
from tests.scenarios.test_devoted_combo_deck import DEVOTED_COMBO_MAIN, DEVOTED_COMBO_SIDE


def broodscale() -> Deck:
    return Deck(
        name="broodscale bloodchief",
        mainboard=dict(BROODSCALE_MAIN),
        sideboard=dict(BROODSCALE_SIDE),
    )


def devoted() -> Deck:
    return Deck(
        name="devoted combo",
        mainboard=dict(DEVOTED_COMBO_MAIN),
        sideboard=dict(DEVOTED_COMBO_SIDE),
    )


def series(alice: Deck, bob: Deck, seed: str = "opening-hand") -> Match:
    match = Match(
        players=[Player(username="alice"), Player(username="bob")],
        card_resolver=card,
        seed=seed,
    )
    match.register_deck("alice", alice)
    match.register_deck("bob", bob)
    return match


def rig(game: Game, username: str, name: str) -> None:
    """Put a named card on top of a player's library, before hands are dealt.

    CR 103.3 staging: the sixty are the registered sixty, only the order is
    chosen. Without it a one-of like Gemstone Caverns is dealt roughly one game
    in nine and the scenario would test nothing most of the time.
    """
    player = game.player(username)
    state = next(s for s in player.library if s.card.name == name)
    player.library.remove(state)
    player.library.insert(0, state)


def bury(game: Game, username: str, names: set[str]) -> None:
    """Send every copy of `names` to the bottom of a player's library.

    The other half of `rig`, and the same CR 103.3 staging: the sixty are still
    the registered sixty. Needed to state "a player with no such card" without
    depending on which seven a particular seed happened to deal.
    """
    player = game.player(username)
    buried = [state for state in player.library if state.card.name in names]
    for state in buried:
        player.library.remove(state)
    player.library.extend(buried)


def dealt(match: Match, rigged: dict[str, str], **kwargs) -> Game:
    """Start a game with `rigged`'s cards on top of each named player's library."""
    game = match.start_game(deal_opening_hands=False, **kwargs)
    for username, name in rigged.items():
        rig(game, username, name)
    for player in game.players:
        player.draw_opening_hand()
    return game


def will_take(game: Game, player: str, source: str, times: int | None = None) -> None:
    """Script one player's "yes" to one card's CR 103.6 offer."""
    game.decisions.add(
        ScriptedAnswer(
            kind=DecisionKind.OPENING_HAND_ACTION,
            value=True,
            player=player,
            source=source,
            uses=times,
        )
    )


def offers(game: Game, player: str | None = None) -> list[str]:
    """The cards whose CR 103.6 action was actually put to a player, in order."""
    return [
        decision.source or ""
        for decision in game.decisions.asked
        if decision.kind is DecisionKind.OPENING_HAND_ACTION
        and (player is None or decision.player == player)
    ]


# -- what the two templates say (CR 103.6a, CR 103.6b) ---------------------


def test_the_leyline_template_is_read_as_a_begin_on_the_battlefield_action():
    """CR 103.6a, off the real printing rather than a paraphrase of it."""
    actions, notices = read_opening_hand_actions(card("Leyline of Abundance"))

    assert notices == []
    (action,) = actions
    assert action.kind is OpeningHandActionKind.BEGIN_ON_BATTLEFIELD
    assert action.counter is None
    assert action.requires_not_starting_player is False
    assert action.rider == ""


def test_gemstone_caverns_carries_a_restriction_a_counter_and_a_rider():
    """CR 103.6a plus everything the Leyline template does not have.

    "If this card is in your opening hand and you're not the starting player,
    you may begin the game with Gemstone Caverns on the battlefield with a luck
    counter on it. If you do, exile a card from your hand."
    """
    actions, notices = read_opening_hand_actions(card("Gemstone Caverns"))

    assert notices == []
    (action,) = actions
    assert action.kind is OpeningHandActionKind.BEGIN_ON_BATTLEFIELD
    assert action.requires_not_starting_player is True
    assert action.counter == "luck"
    assert action.rider == "If you do, exile a card from your hand."


def test_devourer_of_destiny_is_read_as_a_reveal():
    """CR 103.6b: "You may reveal this card from your opening hand.\""""
    actions, notices = read_opening_hand_actions(card("Devourer of Destiny"))

    assert notices == []
    (action,) = actions
    assert action.kind is OpeningHandActionKind.REVEAL
    assert action.rider.startswith("If you do, at the beginning of your first upkeep")


def test_a_card_with_no_opening_hand_text_offers_nothing():
    """The clause has to be printed - a Forest is not silently offered anything."""
    assert read_opening_hand_actions(card("Forest")) == ([], [])
    assert read_opening_hand_actions(card("Emrakul, the Promised End")) == ([], [])


def test_every_printing_in_the_pool_that_mentions_an_opening_hand_is_readable():
    """The fail-closed path has nothing to fire on today, and that is the assertion.

    A paragraph mentioning an opening hand that matches neither template, or one
    that matches but carries a rider with no `RIDERS` entry, is refused with an
    `OpeningHandNotice` rather than half-performed. Nothing in the current
    fixture pool hits that path; this is the guard that says so when a new
    printing does.
    """
    unreadable: list[tuple[str, str]] = []
    for path in sorted(Path("tests/fixtures/cards").glob("*.json")):
        printing = Card.model_validate_json(path.read_text())
        _, notices = read_opening_hand_actions(printing)
        unreadable.extend((notice.card_name, notice.reason) for notice in notices)

    assert unreadable == []


def test_every_rider_in_the_pool_has_an_entry():
    """The other half of the same guard, from the registry's side."""
    assert set(RIDERS) == {"Gemstone Caverns", "Devourer of Destiny"}


# -- offered, and declined (CR 103.6's "may") ------------------------------


def test_an_unscripted_player_is_offered_the_action_and_declines():
    """CR 103.6: "may take any such actions" - not "does".

    The engine has no player agent, so an unasked-for action must not simply
    happen; the question is put and the documented default declines it.
    """
    match = series(devoted(), broodscale())
    game = dealt(match, {"alice": "Leyline of Abundance"})
    leyline = next(s for s in game.player("alice").hand if s.name == "Leyline of Abundance")

    match.run_mulligans(game)

    assert offers(game, "alice") == ["Leyline of Abundance"]
    assert leyline.zone is Zone.HAND


def test_taking_the_action_puts_the_card_onto_the_battlefield():
    """CR 103.6a: "the player taking this action puts that card onto the battlefield.\""""
    match = series(devoted(), broodscale())
    game = dealt(match, {"alice": "Leyline of Abundance"})
    leyline = next(s for s in game.player("alice").hand if s.name == "Leyline of Abundance")
    will_take(game, "alice", "Leyline of Abundance")

    match.run_mulligans(game)

    assert leyline.zone is Zone.BATTLEFIELD
    assert leyline in game.battlefield
    assert leyline not in game.player("alice").hand


def test_the_hand_is_one_card_smaller_and_the_library_untouched():
    """CR 103.6a moves the card out of the hand and touches nothing else."""
    match = series(devoted(), broodscale())
    game = dealt(match, {"alice": "Leyline of Abundance"})
    will_take(game, "alice", "Leyline of Abundance")

    match.run_mulligans(game)
    alice = game.player("alice")

    assert len(alice.hand) == 6
    assert len(alice.library) == 53
    assert len(game.battlefield) == 1


def test_a_player_holding_no_such_card_is_never_asked():
    """CR 103.6's question exists only where a card "allows a player to take" one."""
    match = series(devoted(), broodscale())
    game = match.start_game(deal_opening_hands=False)
    rig(game, "alice", "Leyline of Abundance")
    # Bob's seat is the broodscale list, which plays both an opening-hand land
    # and an opening-hand creature; bury them so his seven provably has neither.
    bury(game, "bob", {"Gemstone Caverns", "Devourer of Destiny"})
    for player in game.players:
        player.draw_opening_hand()

    match.run_mulligans(game)

    assert offers(game, "alice") == ["Leyline of Abundance"]
    assert offers(game, "bob") == []


def test_a_second_run_asks_nothing_more():
    """CR 103.6 is one sequence per game, and CR 103.6b forbids a second reveal."""
    match = series(devoted(), broodscale())
    game = dealt(match, {"alice": "Leyline of Abundance"})

    match.run_mulligans(game)
    before = len(offers(game))
    game.take_opening_hand_actions()

    assert len(offers(game)) == before


# -- turn order (CR 103.6) -------------------------------------------------


def test_the_starting_player_is_asked_first_then_the_other():
    """CR 103.6: "the starting player may take any such actions ... Then ea[ch
    other player ...]" - with both seats holding a Leyline, the order is visible.
    """
    match = series(devoted(), devoted())
    game = dealt(
        match,
        {"alice": "Leyline of Abundance", "bob": "Leyline of Abundance"},
        on_the_play="bob",
    )
    assert game.turn.starting_player == "bob"

    match.run_mulligans(game)
    asked = [
        decision.player
        for decision in game.decisions.asked
        if decision.kind is DecisionKind.OPENING_HAND_ACTION
    ]

    assert asked == ["bob", "alice"]


def test_both_players_may_take_their_own_action():
    """Two Leylines, two seats, both accepted - CR 103.6a twice over."""
    match = series(devoted(), devoted())
    game = dealt(match, {"alice": "Leyline of Abundance", "bob": "Leyline of Abundance"})
    will_take(game, "alice", "Leyline of Abundance")
    will_take(game, "bob", "Leyline of Abundance")

    match.run_mulligans(game)

    assert sorted(state.name for state in game.battlefield) == [
        "Leyline of Abundance",
        "Leyline of Abundance",
    ]
    assert {state.controller for state in game.battlefield} == {"alice", "bob"}


def test_one_seat_taking_it_does_not_take_the_others():
    """The declaration is per player and per card, not a table-wide switch."""
    match = series(devoted(), devoted())
    game = dealt(match, {"alice": "Leyline of Abundance", "bob": "Leyline of Abundance"})
    will_take(game, "bob", "Leyline of Abundance")

    match.run_mulligans(game)

    assert [state.controller for state in game.battlefield] == ["bob"]


# -- the starting-player restriction (Gemstone Caverns, CR 103.8) ----------


def test_the_starting_player_is_not_offered_gemstone_caverns():
    """ "and you're not the starting player" - CR 103.8 names who that is.

    The card does not allow the starting player to take the action at all, so
    CR 103.6's question is never put: there is nothing to decline.
    """
    match = series(broodscale(), devoted())
    game = dealt(match, {"alice": "Gemstone Caverns"}, on_the_play="alice")
    caverns = next(s for s in game.player("alice").hand if s.name == "Gemstone Caverns")

    match.run_mulligans(game)

    assert offers(game, "alice") == []
    assert caverns.zone is Zone.HAND


def test_the_non_starting_player_is_offered_it():
    match = series(broodscale(), devoted())
    game = dealt(match, {"alice": "Gemstone Caverns"}, on_the_play="bob")

    match.run_mulligans(game)

    assert offers(game, "alice") == ["Gemstone Caverns"]


def test_gemstone_caverns_begins_the_game_with_a_luck_counter_and_exiles_a_card():
    """CR 103.6a plus CR 122.1's counter plus the card's own "If you do" rider.

    "you may begin the game with Gemstone Caverns on the battlefield with a luck
    counter on it. If you do, exile a card from your hand."
    """
    match = series(broodscale(), devoted())
    game = dealt(match, {"alice": "Gemstone Caverns"}, on_the_play="bob")
    alice = game.player("alice")
    caverns = next(s for s in alice.hand if s.name == "Gemstone Caverns")
    will_take(game, "alice", "Gemstone Caverns")

    match.run_mulligans(game)

    assert caverns.zone is Zone.BATTLEFIELD
    assert caverns.counter_count("luck") == 1
    assert len(alice.hand) == 5  # seven, less the Caverns, less the exiled card
    assert len(alice.cards_in(Zone.EXILE)) == 1


def test_declining_gemstone_caverns_exiles_nothing():
    """The rider is "If you do" - no action, no cost."""
    match = series(broodscale(), devoted())
    game = dealt(match, {"alice": "Gemstone Caverns"}, on_the_play="bob")
    alice = game.player("alice")

    match.run_mulligans(game)

    assert len(alice.hand) == 7
    assert alice.cards_in(Zone.EXILE) == []


def test_which_card_the_caverns_exiles_is_its_holder_s_choice():
    """CR 608.2d's own "the player announces these" - a `CHOOSE_CARDS` question."""
    match = series(broodscale(), devoted())
    game = dealt(match, {"alice": "Gemstone Caverns"}, on_the_play="bob")
    alice = game.player("alice")
    will_take(game, "alice", "Gemstone Caverns")
    chosen = next(state for state in alice.hand if state.name != "Gemstone Caverns")
    game.decisions.add(
        ScriptedAnswer(
            kind=DecisionKind.CHOOSE_CARDS,
            value=(chosen.id,),
            player="alice",
            source="Gemstone Caverns",
        )
    )

    match.run_mulligans(game)

    assert chosen.zone is Zone.EXILE
    assert alice.cards_in(Zone.EXILE) == [chosen]


# -- revealing from the opening hand (Devourer of Destiny, CR 103.6b) ------


def test_revealing_shows_the_card_and_leaves_it_in_hand():
    """CR 103.6b's action, and CR 701.20b's "doesn't cause it to leave the zone".

    The reveal is recorded twice on purpose: `Game.reveals` is CR 701.20a's
    momentary showing, and `opening_hand_reveals` is CR 103.6b's separate,
    longer-lived fact ("remains revealed until the first turn begins").
    """
    match = series(broodscale(), devoted())
    game = dealt(match, {"alice": "Devourer of Destiny"})
    devourer = next(s for s in game.player("alice").hand if s.name == "Devourer of Destiny")
    will_take(game, "alice", "Devourer of Destiny")

    match.run_mulligans(game)

    assert devourer.zone is Zone.HAND
    assert devourer.id in game.opening_hand_reveals
    assert [reveal.card_name for reveal in game.reveals] == ["Devourer of Destiny"]
    assert len(game.player("alice").hand) == 7


def test_declining_the_reveal_shows_nothing():
    match = series(broodscale(), devoted())
    game = dealt(match, {"alice": "Devourer of Destiny"})

    match.run_mulligans(game)

    assert offers(game, "alice") == ["Devourer of Destiny"]
    assert game.reveals == []
    assert game.opening_hand_reveals == []
    assert game.delayed_triggers.triggers == []


def test_the_reveal_creates_a_delayed_trigger_for_the_first_upkeep():
    """CR 603.7: "an effect may create a delayed triggered ability that can do
    something at a later time", and CR 603.7b makes it fire once."""
    match = series(broodscale(), devoted())
    game = dealt(match, {"alice": "Devourer of Destiny"}, on_the_play="alice")
    will_take(game, "alice", "Devourer of Destiny")

    match.run_mulligans(game)
    (trigger,) = game.delayed_triggers.triggers

    assert trigger.controller == "alice"
    assert trigger.source_name == "Devourer of Destiny"
    assert trigger.step is Step.UPKEEP
    assert trigger.only_when_active == "alice"
    assert trigger.remaining == 1


def test_the_first_upkeep_trigger_exiles_all_four_when_nothing_is_put_back():
    """ "You may put one of those cards back on top" declined - "Exile the rest.\""""
    match = series(broodscale(), devoted())
    game = dealt(match, {"alice": "Devourer of Destiny"}, on_the_play="alice")
    alice = game.player("alice")
    will_take(game, "alice", "Devourer of Destiny")
    match.run_mulligans(game)
    top_four = list(alice.library[:4])

    game.advance("alice")  # untap -> upkeep, CR 500.6 puts the trigger on the stack
    assert game.turn.step is Step.UPKEEP
    game.resolve_top()

    assert all(state.zone is Zone.EXILE for state in top_four)
    assert len(alice.library) == 49


def test_one_card_may_be_put_back_on_top_and_the_rest_exiled():
    """The "you may" branch taken: one card survives, on top, and three do not."""
    match = series(broodscale(), devoted())
    game = dealt(match, {"alice": "Devourer of Destiny"}, on_the_play="alice")
    alice = game.player("alice")
    will_take(game, "alice", "Devourer of Destiny")
    match.run_mulligans(game)
    top_four = list(alice.library[:4])
    kept = top_four[2]
    game.decisions.add(
        ScriptedAnswer(
            kind=DecisionKind.SCRY,
            value=CardSplit(moved=(kept.id,)),
            player="alice",
            source="Devourer of Destiny",
        )
    )

    game.advance("alice")
    game.resolve_top()

    assert alice.library[0] is kept
    assert len(alice.library) == 50
    assert sorted(state.id for state in top_four if state is not kept) == sorted(
        state.id for state in alice.cards_in(Zone.EXILE)
    )


def test_the_trigger_waits_for_its_own_controller_s_upkeep():
    """CR 603.7b plus `only_when_active`: "your first upkeep", not the next one.

    Alice is not the starting player here, so bob's upkeep comes first and must
    not spend her one-shot trigger.
    """
    match = series(broodscale(), devoted())
    game = dealt(match, {"alice": "Devourer of Destiny"}, on_the_play="bob")
    will_take(game, "alice", "Devourer of Destiny")
    match.run_mulligans(game)

    game.advance("bob")  # bob's upkeep

    assert game.turn.step is Step.UPKEEP
    assert game.turn.active_player == "bob"
    assert game.stack_is_empty
    assert len(game.delayed_triggers.triggers) == 1


# -- determinism (CR 103.3's seed, carried through CR 103.6) ---------------


def test_a_seeded_replay_reproduces_the_same_opening_hand_actions():
    """CR 103.6 adds no randomness, so the mulligan's replay guarantee survives.

    Two matches on the same seed, given the same declarations, take the same
    actions on the same cards and leave the same board; a different seed deals
    a different sixty and so a different result.
    """

    def played(seed: str) -> tuple[list[str], list[str], list[str]]:
        match = series(broodscale(), devoted(), seed=seed)
        game = dealt(match, {"alice": "Gemstone Caverns"}, on_the_play="bob")
        will_take(game, "alice", "Gemstone Caverns")
        match.run_mulligans(game)
        return (
            offers(game),
            [state.name for state in game.battlefield],
            [state.name for state in game.player("alice").cards_in(Zone.EXILE)],
        )

    assert played("replay") == played("replay")
    assert played("replay")[2] != played("a-different-seed")[2]


def test_the_same_seed_without_the_declaration_leaves_the_card_in_hand():
    """The seed fixes the deal; the declaration is what decides the action."""
    match = series(broodscale(), devoted(), seed="replay")
    game = dealt(match, {"alice": "Gemstone Caverns"}, on_the_play="bob")

    match.run_mulligans(game)
    alice = game.player("alice")

    assert [state.name for state in alice.hand].count("Gemstone Caverns") == 1
    assert game.battlefield == []


# -- the sequence's place in CR 103 ----------------------------------------


def test_the_actions_happen_after_a_mulligan_has_been_taken():
    """CR 103.6: "once the mulligan process (see rule 103.5) is complete".

    Alice mulligans once, so the Leyline she is offered has to be one from the
    *second* hand - the sequence cannot have run against the first, and the
    first hand's cards are back in the library by the time it does. The seed is
    chosen so that the six she keeps actually contain a Leyline; without that
    the assertion below would hold vacuously.
    """
    match = series(devoted(), devoted(), seed="mull-8")
    game = match.start_game()
    game.decisions.add(
        ScriptedAnswer(kind=DecisionKind.MULLIGAN, value=True, player="alice", uses=1)
    )
    first_hand = [state.id for state in game.player("alice").hand]

    match.run_mulligans(game)
    alice = game.player("alice")

    assert alice.mulligans_taken == 1
    assert len(alice.hand) == 6
    assert [state.id for state in alice.hand] != first_hand
    assert offers(game, "alice") == ["Leyline of Abundance"]
    assert "Leyline of Abundance" in {state.name for state in alice.hand}


def test_no_action_is_offered_for_a_card_that_is_not_in_the_opening_hand():
    """ "If this card is in your opening hand" - a Leyline in the library is not."""
    match = series(devoted(), devoted())
    game = match.start_game(deal_opening_hands=False)
    bury(game, "alice", {"Leyline of Abundance"})
    for player in game.players:
        player.draw_opening_hand()

    match.run_mulligans(game)
    alice = game.player("alice")

    assert [state.name for state in alice.library].count("Leyline of Abundance") == 4
    assert offers(game, "alice") == []
    assert alice.cards_in(Zone.BATTLEFIELD) == []


@pytest.mark.parametrize("name", sorted(RIDERS))
def test_every_card_with_a_rider_is_a_real_printing_in_the_pool(name: str):
    """A registry entry for a card the fixture pool does not have tests nothing."""
    assert card(name) is not None


def test_a_revealed_card_is_not_offered_a_second_time():
    """CR 103.6b: "Each card may be revealed this way only once."

    CR 103.6a's card leaves the hand for the battlefield, so it stops being
    offered on its own. A reveal does not - CR 701.20b leaves the card exactly
    where it is - so the offer has to be withdrawn deliberately, and it was
    not: Devourer of Destiny was offered again after being revealed, for ever.

    Through the API that read to a player as a button that did nothing. The
    action really was performed on every click, the panel came back identical,
    and the rider was scheduled again each time.
    """
    match = series(broodscale(), devoted(), seed="reveal-once")
    game = dealt(match, {"alice": "Devourer of Destiny"}, on_the_play="alice")
    for player in game.players:
        game.declare_mulligan(player.username, take=False)
    alice = game.player("alice")
    devourer = next(state for state in alice.hand if state.name == "Devourer of Destiny")

    assert [d.source for d in game.opening_hand_options("alice")] == ["Devourer of Destiny"]

    game.take_opening_hand_action("alice", devourer.id)

    assert devourer.zone is Zone.HAND, "CR 701.20b: revealing leaves it in hand"
    assert game.opening_hand_reveals == [devourer.id]
    assert game.opening_hand_options("alice") == [], "CR 103.6b allows the reveal only once"

    with pytest.raises(ValueError, match="offers that action"):
        game.take_opening_hand_action("alice", devourer.id)

    assert game.opening_hand_reveals == [devourer.id], "the second attempt changed nothing"
