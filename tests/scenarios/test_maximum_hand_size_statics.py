"""Scenario: maximum hand size statics and "draw cards equal to the difference".

CR 402.2: "Each player has a maximum hand size, which is normally seven
cards." CR 514.1's cleanup discard is down to it. CR 613.11 makes an effect
that changes it a rule-modifying continuous effect, applied in timestamp order
(CR 613.7a: a static ability's effect has its permanent's timestamp).

- **The Ten Rings** (msh): "Your maximum hand size is ten." and "At the
  beginning of your end step, if you have fewer than ten cards in hand, draw
  cards equal to the difference." (CR 603.4's intervening if, checked as it
  triggers and again as it resolves; the difference read as it resolves,
  CR 608.2h).
- **Doctor Octopus, Master Planner** (off-msh, Standard): the same two
  sentences with eight.
- **Kozilek, the Great Distortion** (off-msh, Modern/Pioneer): "When you cast
  this spell, if you have fewer than seven cards in hand, draw cards equal to
  the difference." - the difference on a cast trigger.
- **Reliquary Tower** (Modern/Pioneer): "You have no maximum hand size." - the
  other maximum-hand-size static, and its timestamp order against "is ten".

Rules, each read with `mise run rules:find` in the session that wrote this
file: CR 402.2, CR 514.1, CR 613.11, CR 613.7a, CR 604.2, CR 603.4,
CR 608.2h.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def _resolve_everything(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.pass_until_resolved()
        scenario.game.put_triggers_on_stack()


def _board(battlefield, hand_size: int, library: int = 20):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=list(battlefield),
            hand=["Island"] * hand_size,
            library=["Island"] * library,
        )
        .player("bob", library=["Island"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


# -- "Your maximum hand size is N." -------------------------------------------


def test_the_ten_rings_keeps_ten_cards_through_cleanup():
    scenario = _board(["The Ten Rings"], hand_size=10)

    assert scenario.player("alice").cards_over_maximum_hand_size == 0
    scenario.game.cleanup_step()
    assert len(scenario.player("alice").hand) == 10


def test_the_ten_rings_still_discards_down_to_ten():
    scenario = _board(["The Ten Rings"], hand_size=12)

    assert scenario.player("alice").cards_over_maximum_hand_size == 2


def test_without_the_ten_rings_the_maximum_is_seven():
    scenario = _board([], hand_size=10)

    assert scenario.player("alice").cards_over_maximum_hand_size == 3


def test_the_ten_rings_does_not_change_an_opponents_maximum():
    scenario = _board(["The Ten Rings"], hand_size=0)
    bob = scenario.player("bob")
    scenario.game.draw_cards("bob", 9)

    assert bob.cards_over_maximum_hand_size == 2


def test_off_msh_doctor_octopus_sets_eight():
    scenario = _board(["Doctor Octopus, Master Planner"], hand_size=10)

    assert scenario.player("alice").cards_over_maximum_hand_size == 2


def test_the_later_timestamp_wins_between_two_maximums():
    """CR 613.11/613.7a: Doctor Octopus entering after The Ten Rings makes it
    eight; the order the other way round makes it ten."""
    scenario = _board(["The Ten Rings", "Doctor Octopus, Master Planner"], hand_size=11)
    assert scenario.player("alice").cards_over_maximum_hand_size == 3

    scenario = _board(["Doctor Octopus, Master Planner", "The Ten Rings"], hand_size=11)
    assert scenario.player("alice").cards_over_maximum_hand_size == 1


def test_reliquary_tower_has_no_maximum():
    scenario = _board(["Reliquary Tower"], hand_size=15)

    assert scenario.player("alice").cards_over_maximum_hand_size == 0


def test_the_ten_rings_after_reliquary_tower_sets_ten_again():
    """CR 613.11: timestamp order, so the later "is ten" applies over the
    earlier "no maximum"; the other way round, no maximum."""
    scenario = _board(["Reliquary Tower", "The Ten Rings"], hand_size=12)
    assert scenario.player("alice").cards_over_maximum_hand_size == 2

    scenario = _board(["The Ten Rings", "Reliquary Tower"], hand_size=12)
    assert scenario.player("alice").cards_over_maximum_hand_size == 0


def test_the_maximum_ends_with_the_ten_rings():
    """CR 604.2: the effect lasts only while the permanent is there."""
    scenario = _board(["The Ten Rings"], hand_size=10)
    scenario.game.destroy(scenario.find("The Ten Rings", Zone.BATTLEFIELD, "alice"))

    assert scenario.player("alice").cards_over_maximum_hand_size == 3


# -- "if you have fewer than N cards in hand, draw cards equal to the
# difference" ---------------------------------------------------------------


def _end_step(scenario) -> None:
    scenario.turn.advance_to(Step.POSTCOMBAT_MAIN)
    scenario.advance()  # end step: "at the beginning of your end step"
    _resolve_everything(scenario)


def test_the_ten_rings_fills_the_hand_to_ten_at_the_end_step():
    scenario = _board(["The Ten Rings"], hand_size=3)

    _end_step(scenario)

    assert len(scenario.player("alice").hand) == 10


def test_the_ten_rings_does_not_trigger_with_ten_in_hand():
    scenario = _board(["The Ten Rings"], hand_size=10)

    _end_step(scenario)

    assert len(scenario.player("alice").hand) == 10


def test_the_difference_is_read_as_it_resolves():
    """CR 608.2h: two cards drawn in response make the difference five, not
    seven."""
    scenario = _board(["The Ten Rings"], hand_size=3)
    scenario.turn.advance_to(Step.POSTCOMBAT_MAIN)
    scenario.advance()
    scenario.game.put_triggers_on_stack()
    scenario.game.draw_cards("alice", 2)

    _resolve_everything(scenario)

    assert len(scenario.player("alice").hand) == 10


def test_the_intervening_if_is_checked_again_on_resolution():
    """CR 603.4: at ten by then, the ability does nothing."""
    scenario = _board(["The Ten Rings"], hand_size=3)
    scenario.turn.advance_to(Step.POSTCOMBAT_MAIN)
    scenario.advance()
    scenario.game.put_triggers_on_stack()
    scenario.game.draw_cards("alice", 8)

    _resolve_everything(scenario)

    assert len(scenario.player("alice").hand) == 11


def test_the_ten_rings_only_on_its_controllers_end_step():
    scenario = _board(["The Ten Rings"], hand_size=3)
    _end_step(scenario)
    scenario.advance()  # cleanup
    scenario.advance()
    scenario.turn.advance_to(Step.POSTCOMBAT_MAIN)
    hand = len(scenario.player("alice").hand)

    scenario.advance()  # bob's end step
    _resolve_everything(scenario)

    assert scenario.turn.active_player == "bob"
    assert len(scenario.player("alice").hand) == hand


def test_off_msh_doctor_octopus_fills_to_eight():
    scenario = _board(["Doctor Octopus, Master Planner"], hand_size=5)

    _end_step(scenario)

    assert len(scenario.player("alice").hand) == 8


def test_off_msh_kozilek_draws_the_difference_as_it_is_cast():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Kozilek, the Great Distortion", "Island", "Island"],
            battlefield=["Wastes"] * 10,
            library=["Island"] * 10,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast_onto_stack("Kozilek, the Great Distortion", auto=True)
    _resolve_everything(scenario)

    # Two cards left when the cast trigger resolves: five drawn to make seven.
    assert len(scenario.player("alice").hand) == 7
