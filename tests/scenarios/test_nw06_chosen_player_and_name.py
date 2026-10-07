"""As-enters player/opponent and card-name choices, and what reads them back.

Rules read in full with `mise run rules:find` this session:

- **CR 614.12a** - "If a replacement effect that modifies how a permanent
  enters the battlefield requires a choice, that choice is made before the
  permanent enters the battlefield."
- **CR 701.20a** - to reveal a card is to show it to all players.
- **CR 120.3a** - damage dealt to a player causes that much life loss.
- **CR 603.4** / **CR 603.2** - a trigger condition is checked as the event
  happens.

Cards: Stuffy Doll ("choose a player" + "deals that much damage to the
chosen player"), Booby Trap ("choose an opponent and a card name other than a
basic land card name", "The chosen player reveals each card they draw", and
"When the chosen player draws a card with the chosen name, ..."), and
Nyxathid ("choose an opponent" + "-1/-1 for each card in the chosen player's
hand"), the proof printing for the as-enters opponent choice that is not a
reported card. No other printing legal in Modern, Pioneer or Standard prints
"reveals each card they draw" or a draw trigger on "the chosen name"
(searched over the oracle bulk), so those two are proven on Booby Trap only.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _main(alice_hand=(), alice_battlefield=(), bob_hand=(), bob_library=None, alice_library=None):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=list(alice_hand),
            battlefield=list(alice_battlefield),
            library=alice_library if alice_library is not None else ["Mountain"] * 10,
        )
        .player(
            "bob",
            hand=list(bob_hand),
            library=bob_library if bob_library is not None else ["Mountain"] * 10,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _quality_asks(scenario, source):
    return [
        q
        for q in scenario.questions_asked()
        if q.kind is DecisionKind.CHOOSE_A_QUALITY and q.source == source
    ]


def _resolve_all(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


# -- Stuffy Doll: "choose a player" ------------------------------------------------


def test_stuffy_doll_asks_its_controller_to_choose_any_player_before_it_enters():
    scenario = _main(alice_hand=["Stuffy Doll"])
    scenario.will_choose("bob", username="alice", source="Stuffy Doll")
    doll = scenario.put_onto_battlefield("Stuffy Doll")

    (asked,) = _quality_asks(scenario, "Stuffy Doll")
    assert asked.player == "alice"
    assert set(asked.options) == {"alice", "bob"}
    assert doll.chosen_player == "bob"


def test_damage_dealt_to_stuffy_doll_is_dealt_again_to_the_chosen_player():
    scenario = _main(alice_hand=["Stuffy Doll", "Lightning Bolt"], alice_battlefield=["Mountain"])
    scenario.will_choose("bob", username="alice", source="Stuffy Doll")
    doll = scenario.put_onto_battlefield("Stuffy Doll")
    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.cast_and_resolve("Lightning Bolt", mountain, targets=[doll])
    _resolve_all(scenario)

    assert doll.zone is Zone.BATTLEFIELD, "indestructible"
    assert scenario.player("bob").life == 17
    assert scenario.player("alice").life == 20


def test_stuffy_dolls_own_tap_ability_pings_the_chosen_player_through_it():
    scenario = _main(alice_hand=["Stuffy Doll"])
    scenario.will_choose("bob", username="alice", source="Stuffy Doll")
    doll = scenario.put_onto_battlefield("Stuffy Doll")
    doll.summoning_sick = False
    scenario.activate(doll)
    _resolve_all(scenario)

    assert scenario.player("bob").life == 19


def test_choosing_yourself_turns_the_damage_on_you():
    scenario = _main(alice_hand=["Stuffy Doll"])
    scenario.will_choose("alice", username="alice", source="Stuffy Doll")
    doll = scenario.put_onto_battlefield("Stuffy Doll")
    doll.summoning_sick = False
    scenario.activate(doll)
    _resolve_all(scenario)

    assert scenario.player("alice").life == 19
    assert scenario.player("bob").life == 20


def test_a_player_not_offered_is_refused():
    scenario = _main(alice_hand=["Stuffy Doll"])
    scenario.will_choose("carol", username="alice", source="Stuffy Doll")
    with pytest.raises(ValueError):
        scenario.put_onto_battlefield("Stuffy Doll")


# -- Booby Trap: "choose an opponent and a card name other than a basic land card
# -- name", the reveal static and the chosen-name draw trigger -----------------------


def _trap(bob_library):
    scenario = _main(alice_hand=["Booby Trap"], bob_library=bob_library)
    scenario.will_choose("Lightning Bolt", username="alice", source="Booby Trap")
    trap = scenario.put_onto_battlefield("Booby Trap")
    return scenario, trap


def test_booby_trap_records_the_opponent_and_the_name():
    scenario, trap = _trap(["Mountain"] * 5)
    assert trap.chosen_player == "bob"
    assert trap.choice is not None and trap.choice.value == "Lightning Bolt"
    names = [q for q in _quality_asks(scenario, "Booby Trap") if q.quality == "card_name"]
    assert len(names) == 1 and names[0].player == "alice"


def test_a_basic_land_name_is_refused():
    scenario = _main(alice_hand=["Booby Trap"])
    scenario.will_choose("Mountain", username="alice", source="Booby Trap")
    with pytest.raises(ValueError, match="basic land"):
        scenario.put_onto_battlefield("Booby Trap")


def test_the_chosen_player_reveals_each_card_they_draw():
    scenario, _trap_state = _trap(["Shock", "Mountain", "Mountain"])
    before = len(scenario.game.reveals)
    scenario.draw(2, username="bob")

    shown = scenario.game.reveals[before:]
    assert [r.card_name for r in shown] == ["Shock", "Mountain"]
    assert all(r.revealed_by == "bob" and r.source == "Booby Trap" for r in shown)


def test_its_controller_does_not_reveal_their_own_draws():
    scenario, _trap_state = _trap(["Mountain"] * 3)
    before = len(scenario.game.reveals)
    scenario.draw(1, username="alice")
    assert scenario.game.reveals[before:] == []


def test_drawing_the_chosen_name_sacrifices_the_trap_and_deals_ten_to_that_player():
    scenario, trap = _trap(["Lightning Bolt", "Mountain"])
    scenario.draw(1, username="bob")
    _resolve_all(scenario)

    assert trap.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 10
    assert scenario.player("alice").life == 20


def test_drawing_another_name_does_nothing():
    scenario, trap = _trap(["Shock", "Mountain"])
    scenario.draw(1, username="bob")
    assert scenario.game.pending_triggers == []
    assert trap.zone is Zone.BATTLEFIELD


def test_the_chosen_name_drawn_by_a_player_not_chosen_does_nothing():
    scenario = _main(
        alice_hand=["Booby Trap"], alice_library=["Lightning Bolt"], bob_library=["Mountain"] * 3
    )
    scenario.will_choose("Lightning Bolt", username="alice", source="Booby Trap")
    trap = scenario.put_onto_battlefield("Booby Trap")
    scenario.draw(1, username="alice")

    assert scenario.game.pending_triggers == []
    assert trap.zone is Zone.BATTLEFIELD


# -- Nyxathid: "choose an opponent" read by "the chosen player's hand" ---------------


def test_nyxathid_shrinks_by_the_chosen_opponents_hand_and_tracks_it():
    scenario = _main(alice_hand=["Nyxathid"], bob_hand=["Shock", "Shock", "Mountain"])
    nyxathid = scenario.put_onto_battlefield("Nyxathid")
    assert nyxathid.chosen_player == "bob"
    assert (nyxathid.power, nyxathid.toughness) == (4, 4)

    scenario.draw(2, username="bob")
    assert (nyxathid.power, nyxathid.toughness) == (2, 2)
    scenario.draw(2, username="alice")
    assert (nyxathid.power, nyxathid.toughness) == (2, 2), "only the chosen player's hand"


def test_with_one_opponent_there_is_nothing_to_ask():
    scenario = _main(alice_hand=["Nyxathid"])
    scenario.put_onto_battlefield("Nyxathid")
    assert _quality_asks(scenario, "Nyxathid") == []
