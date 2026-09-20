"""Scenario: the next-turn mana hypothetical, `assuming_untapped=True`.

`payability_matrix(game, player, cards, lands, assuming_untapped=True)` answers
every question it already answers, but on a board where `player`'s untap step
has already happened. That is the one question a seat planning a land drop a
turn ahead needs and could not ask: "what does this hand cost me once my lands
untap", without the seat keeping a second copy of the untap rule of its own.

The rule it untaps by is `Game.untap_step_rule` - the same function the real
untap step reads - so the hypothetical and the step cannot drift apart:

- **CR 502.3** - "the active player determines which permanents they control
  will untap. Then they untap them all simultaneously. ... Normally, all of a
  player's permanents untap, but effects can keep one or more of a player's
  permanents from untapping." Only the permanents that player controls, and a
  "doesn't untap during your untap step" permanent is one of the effects that
  keeps one out.
- **CR 614.10** - "An effect that causes a player to skip an event, step,
  phase, or turn is a replacement effect. 'Skip [something]' is the same as
  'Instead of doing [something], do nothing.'" A player who is skipping their
  next untap step unlocks nothing at all.
- **CR 122.1d** - "One or more stun counters on a permanent create a single
  replacement effect that stops the permanent from untapping. That effect is
  'If a permanent with a stun counter on it would become untapped, instead
  remove a stun counter from it.'" `untap_step_rule` deliberately does not
  filter on it, because it replaces the untap rather than the batch; the
  hypothetical untaps through `Player.untap_all` for exactly that reason, so
  a stunned permanent stays tapped here as it would in the step.
- **CR 701.43a** - "To exert a permanent, you choose to have it not untap
  during your next untap step." Same route, same reason: it is spent inside
  `CardState.untap`.

Every CR number above was read in full from the primary source with
`mise run rules:find` in the session that wrote this file: 502.3, 614.10,
122.1d, 701.43a.

The board is one real board, every permanent on it tapped: alice controls two
Islands and a Basalt Monolith (which prints "This artifact doesn't untap during
your untap step"), bob controls an Island of his own. Alice holds Counterspell
({U}{U}), Stock Up ({2}{U}) and an Island. That is enough to separate all three
cases in one place - the two Islands untapping makes Counterspell payable, the
Monolith's three colorless staying locked away keeps Stock Up unpayable, and
bob's Island is never anybody's business but bob's.

No card is named by the implementation; the rule reads the computed board.
"""

import json

from magic_cards_model.machines import Step, payability_matrix
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import PlayedScenario, Scenario

MONOLITH = "Basalt Monolith"
HAND = ["Counterspell", "Stock Up", "Island"]
BATTLEFIELD = ["Island", "Island", MONOLITH]
#: A deep enough library to draw from, with two Islands buried under a
#: different printing: the top card is never folded into the batch's
#: same-printing cache, so the two below it are what proves the cache still
#: shares under the new flag.
LIBRARY = ["Forest", "Island", "Island", *["Forest"] * 12]


def board() -> PlayedScenario:
    """Every permanent on the battlefield tapped, alice to move."""
    scenario = (
        Scenario()
        .player("alice", hand=HAND, battlefield=BATTLEFIELD, library=LIBRARY)
        .player("bob", battlefield=["Island"], library=["Forest"] * 12)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    for state in scenario.game.battlefield:
        state.tapped = True
    return scenario


def hand_card(scenario: PlayedScenario, name: str):
    return scenario.find(name, Zone.HAND, "alice")


def asked(scenario: PlayedScenario):
    """The two spells every test asks about."""
    return [hand_card(scenario, name) for name in ("Counterspell", "Stock Up")]


def payable(matrix, card, land=None) -> bool:
    row = matrix.get(card.id, land.id if land is not None else None)
    assert row is not None
    return row.payable


def rows(matrix):
    """Every `Payability` the matrix answered, now and in every land column."""
    return [*matrix.now, *(row for column in matrix.lands for row in column.cards)]


def _without_land_ids(column):
    """One land column, with the id of the physical copy that entered taken
    out: two library copies of one printing are the same question, and the id
    is the only thing that tells their answers apart."""
    dumped = column.model_dump(mode="json")
    dumped.pop("land_id")
    dumped["prediction"].pop("card_id")
    for row in dumped["cards"]:
        row["assumed_land"].pop("card_id")
    return dumped


def test_the_board_is_four_tapped_permanents_and_three_cards_in_hand():
    scenario = board()

    assert [state.name for state in scenario.game.battlefield] == [
        "Island",
        "Island",
        MONOLITH,
        "Island",
    ]
    assert all(state.tapped for state in scenario.game.battlefield)
    assert [state.name for state in scenario.game.player("alice").hand] == HAND


def test_the_default_answers_byte_for_byte_what_the_old_call_shape_answers():
    """(a) The parameter's default changes nothing at all."""
    scenario = board()
    cards = asked(scenario)
    lands = [hand_card(scenario, "Island")]

    old = payability_matrix(scenario.game, "alice", cards, lands)
    new = payability_matrix(scenario.game, "alice", cards, lands, assuming_untapped=False)

    assert new.model_dump(mode="json") == old.model_dump(mode="json")


def test_a_tapped_basic_untaps_and_makes_a_hand_card_payable():
    """CR 502.3: the two Islands untap, and {U}{U} is payable that was not."""
    scenario = board()
    counterspell = hand_card(scenario, "Counterspell")

    now = payability_matrix(scenario.game, "alice", [counterspell], [])
    ahead = payability_matrix(scenario.game, "alice", [counterspell], [], assuming_untapped=True)

    assert not payable(now, counterspell), "both Islands are tapped right now"
    assert payable(ahead, counterspell), "and untapped they pay {U}{U}"


def test_a_land_column_is_answered_on_the_untapped_board_too():
    """Every answer moves, not only the `now` row."""
    scenario = board()
    stock_up = hand_card(scenario, "Stock Up")
    island = hand_card(scenario, "Island")

    now = payability_matrix(scenario.game, "alice", [stock_up], [island])
    ahead = payability_matrix(scenario.game, "alice", [stock_up], [island], assuming_untapped=True)

    assert not payable(now, stock_up, island), "one land untapped is one mana"
    assert payable(ahead, stock_up, island), "three untapped Islands pay {2}{U}"


def test_a_doesnt_untap_permanent_stays_tapped_and_unlocks_nothing():
    """CR 502.3's "effects can keep one or more ... from untapping"."""
    scenario = board()
    stock_up = hand_card(scenario, "Stock Up")

    ahead = payability_matrix(scenario.game, "alice", [stock_up], [], assuming_untapped=True)

    assert not payable(ahead, stock_up), "two Islands are two mana; {2}{U} needs three"
    assert not any(MONOLITH in notice for notice in ahead.now[0].notices)

    # The counterfactual, so the reason is the rule and not the board: the
    # Monolith's own three colorless is exactly what is missing.
    unlocked = board()
    unlocked.find(MONOLITH, Zone.BATTLEFIELD, "alice").tapped = False
    with_monolith = payability_matrix(
        unlocked.game, "alice", [hand_card(unlocked, "Stock Up")], [], assuming_untapped=True
    )
    assert payable(with_monolith, hand_card(unlocked, "Stock Up"))


def test_no_permanent_another_player_controls_is_untapped():
    """Only `player`'s own permanents, which is all CR 502.3 ever untaps."""
    scenario = board()
    counterspell = hand_card(scenario, "Counterspell")

    ahead = payability_matrix(scenario.game, "alice", [counterspell], [], assuming_untapped=True)

    untapped = next(notice for notice in ahead.now[0].notices if "untap for alice" in notice)
    assert untapped.startswith("assuming untapped: Island, Island untap for alice")
    assert MONOLITH not in untapped, "it prints the doesn't-untap line"
    # Bob's Island is a third Island, and the notice names two.
    assert untapped.count("Island") == 2
    assert scenario.find("Island", Zone.BATTLEFIELD, "bob").tapped


def test_a_player_skipping_their_untap_step_gets_nothing_untapped():
    """CR 614.10: skip the step and the hypothetical is the board as it is."""
    scenario = board()
    scenario.game.players_skipping_next_untap["alice"] = 1
    cards = asked(scenario)
    lands = [hand_card(scenario, "Island")]

    now = payability_matrix(scenario.game, "alice", cards, lands)
    ahead = payability_matrix(scenario.game, "alice", cards, lands, assuming_untapped=True)

    for card in cards:
        assert payable(ahead, card) == payable(now, card)
        assert payable(ahead, card, lands[0]) == payable(now, card, lands[0])
    assert any("skips their next untap step" in notice for notice in ahead.now[0].notices), (
        ahead.now[0].notices
    )
    assert scenario.game.players_skipping_next_untap["alice"] == 1, "reading it does not spend it"


def test_a_stun_counter_keeps_its_permanent_tapped():
    """CR 122.1d, which `untap_step_rule` does not filter on - the
    hypothetical untaps through `Player.untap_all`, so the counter is spent
    there exactly as the real step spends it."""
    scenario = board()
    stunned = scenario.find("Island", Zone.BATTLEFIELD, "alice")
    stunned.add_counters(Counter.STUN, 1)
    counterspell = hand_card(scenario, "Counterspell")

    ahead = payability_matrix(scenario.game, "alice", [counterspell], [], assuming_untapped=True)

    assert not payable(ahead, counterspell), "one Island is one mana"
    untapped = next(notice for notice in ahead.now[0].notices if "untap for alice" in notice)
    assert untapped.count("Island") == 1, untapped
    assert stunned.counter_count(Counter.STUN) == 1, "and the caller's counter is not spent"


def test_the_callers_game_is_not_mutated():
    """(c) The copy is a copy: every permanent, and the whole dump."""
    scenario = board()
    cards = asked(scenario)
    lands = [hand_card(scenario, "Island")]
    tapped_before = {state.id: state.tapped for state in scenario.game.battlefield}
    dump_before = json.dumps(scenario.game.model_dump(mode="json"), sort_keys=True)

    payability_matrix(scenario.game, "alice", cards, lands, assuming_untapped=True)

    assert {state.id: state.tapped for state in scenario.game.battlefield} == tapped_before
    assert json.dumps(scenario.game.model_dump(mode="json"), sort_keys=True) == dump_before


def test_nothing_is_emitted_and_no_turn_advances():
    """(d) A `GameEvent` has nowhere to hide: every one of them either puts a
    triggered ability in `pending_triggers` (CR 603.3) or changes the game
    state, and the dump above covers both. Asserted here by name anyway, so a
    failure says which half moved."""
    scenario = board()
    cards = asked(scenario)
    turn_before = scenario.game.turn.turn_number
    step_before = scenario.step

    payability_matrix(scenario.game, "alice", cards, [], assuming_untapped=True)

    assert scenario.game.pending_triggers == []
    assert scenario.game.stack == []
    assert scenario.game.turn.turn_number == turn_before
    assert scenario.step is step_before


def test_every_answer_says_it_is_a_hypothetical_and_not_a_prediction():
    """(e) On the `now` row and in every land column."""
    scenario = board()
    cards = asked(scenario)
    lands = [hand_card(scenario, "Island")]

    ahead = payability_matrix(scenario.game, "alice", cards, lands, assuming_untapped=True)

    answered = rows(ahead)
    assert len(answered) == 4, "two cards now, and both again under the hand land"
    for row in answered:
        said = " ".join(row.notices)
        assert "not a prediction of the next turn" in said
        assert "does not draw a card" in said
        assert "does not resolve an upkeep trigger" in said
        assert "does not advance the turn" in said
        assert "anything the opponent does in between" in said


def test_the_plain_answer_never_says_any_of_that():
    """The notice belongs to the flag, not to the function."""
    scenario = board()
    cards = asked(scenario)

    plain = payability_matrix(scenario.game, "alice", cards, [])

    for row in rows(plain):
        assert not any("assuming untapped" in notice for notice in row.notices)


def test_two_library_copies_of_one_printing_are_still_one_question():
    """The batch's same-printing cache keeps working under the flag."""
    scenario = board()
    stock_up = hand_card(scenario, "Stock Up")
    buried = [state for state in scenario.game.player("alice").library if state.name == "Island"]
    assert len(buried) == 2, "and neither is the top card"
    assert scenario.game.player("alice").library[0].name == "Forest"

    ahead = payability_matrix(scenario.game, "alice", [stock_up], buried, assuming_untapped=True)

    first, second = ahead.lands
    assert first.land_id == buried[0].id and second.land_id == buried[1].id
    # The same answer, down to the notices - only the physical copy's own id
    # is stamped differently, which is what `land_id` and `assumed_land` are.
    assert _without_land_ids(first) == _without_land_ids(second)
    assert payable(ahead, stock_up, buried[0]), "two untapped Islands plus the one entering"
