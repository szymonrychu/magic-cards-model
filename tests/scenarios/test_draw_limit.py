"""Scenario: statics that cap how many cards a player may draw each turn -
Narset, Parter of Veils and Spirit of the Labyrinth.

- Narset, Parter of Veils: "Each opponent can't draw more than one card each
  turn."
- Spirit of the Labyrinth: "Each player can't draw more than one card each
  turn." - the widened-reader proof: the identical shape with "each player"
  in place of "each opponent", a real Modern- and Pioneer-legal printing, not
  in any decklist here.

CR 121.2b, verified this session: "Some effects say that a player can't draw
more than one card each turn. Such an effect applies to individual card
draws. Instructions to draw multiple cards may still be partially carried
out." That is the whole shape: `Game.draw_cards` asks `machines.
casting_restrictions.draw_cap_restriction` once per individual draw inside
its own CR 121.2 loop, so a single "draw two cards" instruction against a cap
of one performs the first and silently drops the second - it is not refused
outright, and no card is put anywhere in its place.

Like every other continuous effect over players (CR 611.1, CR 611.3a), this
is read fresh off the battlefield on every draw and dies the moment its
source leaves.
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def _board(*, hate_for: str, hate_card: str = "Narset, Parter of Veils") -> Scenario:
    alice_battlefield = ["Mountain"] * 4
    bob_battlefield = ["Mountain"] * 4
    if hate_for == "alice":
        alice_battlefield.append(hate_card)
    else:
        bob_battlefield.append(hate_card)
    return (
        Scenario()
        .player("alice", battlefield=alice_battlefield, library=["Mountain"] * 10)
        .player("bob", battlefield=bob_battlefield, library=["Mountain"] * 10)
        .build()
    )


# -- Narset, Parter of Veils: "each opponent" --------------------------------


def test_the_first_draw_of_the_turn_goes_through():
    scenario = _board(hate_for="alice")
    scenario.start_at(Step.PRECOMBAT_MAIN)

    drawn = scenario.draw(username="bob")

    assert len(drawn) == 1
    assert scenario.player("bob").hand


def test_the_second_draw_this_turn_is_dropped():
    scenario = _board(hate_for="alice")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.draw(username="bob")
    hand_size_after_first = len(scenario.player("bob").hand)

    drawn = scenario.draw(username="bob")

    assert drawn == [], "CR 121.2b: the second draw simply doesn't happen"
    assert len(scenario.player("bob").hand) == hand_size_after_first


def test_narset_leaves_her_own_controller_alone():
    """ "Each opponent" - alice, who controls Narset, may draw freely."""
    scenario = _board(hate_for="alice")
    scenario.start_at(Step.PRECOMBAT_MAIN)

    first = scenario.draw(username="alice")
    second = scenario.draw(username="alice")

    assert len(first) == 1
    assert len(second) == 1


def test_a_single_instruction_to_draw_two_is_partially_carried_out():
    """CR 121.2b's own sentence, staged as one instruction instead of two
    separate calls: `Game.draw_cards(player, 2)` is exactly the "instruction
    to draw multiple cards" the rule names, and only the first of the two
    individual draws it performs actually happens."""
    scenario = _board(hate_for="alice")
    scenario.start_at(Step.PRECOMBAT_MAIN)

    drawn = scenario.game.draw_cards(scenario.player("bob"), 2)

    assert len(drawn) == 1


# -- Spirit of the Labyrinth: the widened "each player" proof ---------------


def test_spirit_of_the_labyrinth_caps_its_own_controllers_draws_too():
    """ "Each player", not "each opponent" - unlike Narset, alice (who
    controls the Spirit) is capped as well."""
    scenario = _board(hate_for="alice", hate_card="Spirit of the Labyrinth")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.draw(username="alice")

    drawn = scenario.draw(username="alice")

    assert drawn == []


def test_spirit_of_the_labyrinth_also_caps_the_opponent():
    scenario = _board(hate_for="alice", hate_card="Spirit of the Labyrinth")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.draw(username="bob")

    drawn = scenario.draw(username="bob")

    assert drawn == []


# -- what the cap does not catch, and its lifetime ---------------------------


def test_the_cap_is_per_player_not_shared():
    scenario = _board(hate_for="alice")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.draw(username="bob")

    alices_draw = scenario.draw(username="alice")

    assert len(alices_draw) == 1, (
        "Narset restricts opponents only, and alice is not bob's opponent-of-self"
    )


def test_the_cap_resets_next_turn():
    """ "Each turn" - `Game.cards_drawn_this_turn` clears at the turn
    boundary. Advancing all the way to bob's own precombat main passes
    through his own draw step, which itself performs one automatic draw
    (CR 504.1) - if the cap had not reset, that automatic draw would already
    have been dropped, and this checks exactly that it was not."""
    scenario = _board(hate_for="alice")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.draw(username="bob")
    hand_before = len(scenario.player("bob").hand)
    while scenario.turn.active_player != "bob" or scenario.step is not Step.PRECOMBAT_MAIN:
        scenario.advance()

    assert len(scenario.player("bob").hand) == hand_before + 1, (
        "bob's own draw-step draw on his new turn was not dropped"
    )


def test_the_cap_dies_with_the_permanent():
    scenario = _board(hate_for="alice")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.draw(username="bob")
    (narset,) = [c for c in scenario.game.battlefield if c.name == "Narset, Parter of Veils"]
    scenario.game.destroy(narset)

    drawn = scenario.draw(username="bob")

    assert len(drawn) == 1


def test_an_empty_board_caps_nothing():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Mountain"] * 4, library=["Mountain"] * 10)
        .player("bob", battlefield=["Mountain"] * 4, library=["Mountain"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.draw(username="bob")

    drawn = scenario.draw(username="bob")

    assert len(drawn) == 1
