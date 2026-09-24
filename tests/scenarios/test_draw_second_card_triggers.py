"""Scenario: "whenever <someone> draws their second card each turn" and what
the listed Heroes do with it.

CR 121.2 makes every card drawn its own draw, so the second one is an event of
its own; `machines/triggers.py`'s `_NTH_DRAW_CONDITION` already read "you" and
"an opponent" (Faerie Vandal, Faerie Mastermind). This file covers:

- **King T'Challa** (msh): "Whenever a player draws their second card each
  turn, you draw a card." - the third subject, "a player", which is anyone,
  the controller included. Printed only on msh (MEMORY.md, 2026-09-24); its
  generality is the shared ordinal reader, exercised here against Moon Girl's
  and Construct a Cosmic Cube's "you draw your second card" and Faerie
  Mastermind's "an opponent draws their second card".
- **Moon Girl and Devil Dinosaur** (msh): "Whenever you draw your second card
  each turn, until end of turn, Moon Girl and Devil Dinosaur's base power and
  toughness become 6/6 and they gain trample." - CR 613.4b's layer 7b set
  with a keyword rider, the lead "until end of turn,". Proven off-msh on
  **Shorecrasher Mimic** (Modern): "this creature has base power and
  toughness 5/3 until end of turn and gains trample until end of turn."
- **Black Panther, Hope Enduring** (T'Challa's back face): "Prevent all damage
  that would be dealt to Black Panther." - CR 615.1a's prevention, from the
  battlefield. Proven off-msh on **Cho-Manno, Revolutionary** (Modern):
  "Prevent all damage that would be dealt to Cho-Manno."

Rules, each read with `mise run rules:find` in the session that wrote this
file: CR 121.2, CR 121.2c, CR 603.2, CR 613.4b, CR 613.4c, CR 611.2c,
CR 514.2, CR 615.1, CR 615.1a, CR 120.4, CR 201.5, CR 702.19b.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter

from .harness import Scenario


def _resolve_everything(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.pass_until_resolved()
        scenario.game.put_triggers_on_stack()


# -- "a player draws their second card each turn" ----------------------------


def _tchalla_board():
    scenario = (
        Scenario()
        .player("alice", battlefield=["King T'Challa"], library=["Plains"] * 10)
        .player("bob", library=["Island"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_tchalla_draws_when_an_opponent_draws_a_second_card():
    scenario = _tchalla_board()

    scenario.game.draw_cards("bob", 2)
    _resolve_everything(scenario)

    assert len(scenario.player("alice").hand) == 1


def test_tchalla_draws_when_his_own_controller_draws_a_second_card():
    """ "A player" includes the controller - and the card T'Challa draws is
    alice's third, which is not a second, so it does not loop."""
    scenario = _tchalla_board()

    scenario.game.draw_cards("alice", 2)
    _resolve_everything(scenario)

    assert len(scenario.player("alice").hand) == 3


def test_tchalla_ignores_a_first_draw_and_a_third():
    scenario = _tchalla_board()

    scenario.game.draw_cards("bob", 1)
    _resolve_everything(scenario)
    assert len(scenario.player("alice").hand) == 0

    scenario.game.draw_cards("bob", 1)
    scenario.game.draw_cards("bob", 1)
    _resolve_everything(scenario)
    assert len(scenario.player("alice").hand) == 1


def test_tchalla_triggers_once_per_player_reaching_two():
    """Both players drawing two: two second cards, two triggers (CR 603.2)."""
    scenario = _tchalla_board()

    scenario.game.draw_cards("bob", 2)
    scenario.game.draw_cards("alice", 2)
    _resolve_everything(scenario)

    assert len(scenario.player("alice").hand) == 2 + 2


def test_faerie_mastermind_still_ignores_its_own_controller():
    """The narrower "an opponent" is unchanged by the widening."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Faerie Mastermind"], library=["Island"] * 6)
        .player("bob", library=["Island"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.game.draw_cards("alice", 2)
    _resolve_everything(scenario)

    assert len(scenario.player("alice").hand) == 2


# -- Moon Girl and Devil Dinosaur: 6/6 trample until end of turn --------------


def _moon_board():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Moon Girl and Devil Dinosaur"],
            library=["Forest"] * 8,
        )
        .player("bob", library=["Island"] * 8)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _chars(scenario, permanent):
    return scenario.game.computed_board().of(permanent)


def test_moon_girl_becomes_a_six_six_with_trample_on_the_second_draw():
    scenario = _moon_board()
    moon = scenario.creature("Moon Girl and Devil Dinosaur", "alice")

    scenario.game.draw_cards("alice", 2)
    _resolve_everything(scenario)

    chars = _chars(scenario, moon)
    assert (chars.power, chars.toughness) == (6, 6)
    assert "Trample" in chars.abilities


def test_moon_girls_counters_apply_on_top_of_the_new_base():
    """CR 613.4b sets the base, CR 613.4c's +1/+1 counter applies after it."""
    scenario = _moon_board()
    moon = scenario.creature("Moon Girl and Devil Dinosaur", "alice")
    scenario.game.add_counters(moon, Counter.PLUS_ONE, 1)

    scenario.game.draw_cards("alice", 2)
    _resolve_everything(scenario)

    chars = _chars(scenario, moon)
    assert (chars.power, chars.toughness) == (7, 7)


def test_moon_girl_is_back_to_two_two_next_turn():
    scenario = _moon_board()
    moon = scenario.creature("Moon Girl and Devil Dinosaur", "alice")
    scenario.game.draw_cards("alice", 2)
    _resolve_everything(scenario)

    scenario.turn.advance_to(Step.END_STEP)
    scenario.advance()  # cleanup: "until end of turn" ends (CR 514.2)
    scenario.advance()

    chars = _chars(scenario, moon)
    assert (chars.power, chars.toughness) == (2, 2)
    assert "Trample" not in chars.abilities


def test_moon_girl_ignores_an_opponents_second_draw():
    scenario = _moon_board()
    moon = scenario.creature("Moon Girl and Devil Dinosaur", "alice")

    scenario.game.draw_cards("bob", 2)
    _resolve_everything(scenario)

    assert (_chars(scenario, moon).power, _chars(scenario, moon).toughness) == (2, 2)


def test_off_msh_shorecrasher_mimic_has_base_five_three_and_trample():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Shorecrasher Mimic", "Forest", "Island", "Island"],
            hand=["Moon Girl and Devil Dinosaur"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mimic = scenario.creature("Shorecrasher Mimic", "alice")

    scenario.cast_and_resolve("Moon Girl and Devil Dinosaur", auto=True)
    _resolve_everything(scenario)

    chars = _chars(scenario, mimic)
    assert (chars.power, chars.toughness) == (5, 3)
    assert "Trample" in chars.abilities


# -- Black Panther, Hope Enduring: "Prevent all damage that would be dealt to
# Black Panther." (CR 615.1a) ------------------------------------------------


def _panther_board():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["King T'Challa"] + ["Plains"] * 3 + ["Island"] * 3,
            library=["Plains"] * 6,
        )
        .player(
            "bob",
            hand=["Lightning Bolt", "Shock"],
            battlefield=["Mountain", "Mountain"],
            library=["Island"] * 6,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    tchalla = scenario.creature("King T'Challa", "alice")
    scenario.activate(tchalla, auto=True)
    scenario.pass_until_resolved()
    return scenario, tchalla


def test_tchalla_transforms_into_black_panther():
    scenario, panther = _panther_board()

    assert panther.name == "Black Panther, Hope Enduring"


def test_black_panther_takes_no_damage():
    scenario, panther = _panther_board()

    scenario.game.deal_damage(panther, 5, source=scenario.find("Mountain", Zone.BATTLEFIELD, "bob"))

    assert panther.damage == 0
    assert panther.zone is Zone.BATTLEFIELD


def test_black_panther_survives_a_bolt():
    scenario, panther = _panther_board()
    scenario.pass_priority("alice")

    scenario.cast_and_resolve("Lightning Bolt", username="bob", targets=[panther], auto=True)

    assert panther.zone is Zone.BATTLEFIELD
    assert panther.damage == 0


def test_king_tchalla_front_face_is_not_protected():
    scenario = (
        Scenario()
        .player("alice", battlefield=["King T'Challa"])
        .player("bob", battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    tchalla = scenario.creature("King T'Challa", "alice")

    scenario.game.deal_damage(tchalla, 1, source=scenario.find("Mountain", Zone.BATTLEFIELD, "bob"))

    assert tchalla.damage == 1


def test_off_msh_cho_manno_takes_no_damage():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Cho-Manno, Revolutionary"])
        .player("bob", battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cho = scenario.creature("Cho-Manno, Revolutionary", "alice")

    scenario.game.deal_damage(cho, 4, source=scenario.find("Mountain", Zone.BATTLEFIELD, "bob"))

    assert cho.damage == 0
