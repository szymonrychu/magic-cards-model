"""Scenario: "You may choose not to untap this <permanent> during your untap
step." (CR 502.3: the active player determines which permanents untap; the
static ability lets its controller keep this one tapped, CR 604.2) and the
"becomes a creature for as long as this permanent remains tapped" animation
(CR 611.2b, CR 613.1d, CR 205.1b) the card family pairs it with.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Type
from tests.scenarios.harness import Scenario


def _to_alices_next_turn(scenario):
    """Walk the real turn machine to alice's next precombat main."""
    left = False
    for _ in range(80):
        scenario.advance()
        if scenario.turn.active_player == "bob":
            left = True
        if left and scenario.turn.active_player == "alice" and scenario.step is Step.UPKEEP:
            return
    raise AssertionError("never reached alice's next turn")


def _board(name, extra=()):
    scenario = (
        Scenario()
        .player("alice", battlefield=[name, *extra], library=["Island"] * 12)
        .player("bob", library=["Island"] * 12)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _permanent(scenario, name):
    return next(s for s in scenario.game.battlefield if s.name == name)


def test_choosing_not_to_untap_keeps_it_tapped():
    scenario = _board("Hedge Whisperer")
    whisperer = _permanent(scenario, "Hedge Whisperer")
    whisperer.tapped = True
    scenario.will_take_the_may(True, username="alice", source="Hedge Whisperer")
    _to_alices_next_turn(scenario)
    assert whisperer.tapped


def test_declining_the_choice_untaps_it_as_usual():
    scenario = _board("Hedge Whisperer")
    whisperer = _permanent(scenario, "Hedge Whisperer")
    whisperer.tapped = True
    scenario.will_take_the_may(False, username="alice", source="Hedge Whisperer")
    _to_alices_next_turn(scenario)
    assert not whisperer.tapped


def test_an_unscripted_player_untaps_by_default():
    scenario = _board("Hedge Whisperer")
    whisperer = _permanent(scenario, "Hedge Whisperer")
    whisperer.tapped = True
    _to_alices_next_turn(scenario)
    assert not whisperer.tapped


def test_an_untapped_one_is_never_asked():
    scenario = _board("Hedge Whisperer")
    _to_alices_next_turn(scenario)
    assert not [q for q in scenario.questions_asked() if q.source == "Hedge Whisperer"]


def test_a_differently_worded_card_has_the_same_choice():
    scenario = _board("The Blackstaff of Waterdeep")
    staff = _permanent(scenario, "The Blackstaff of Waterdeep")
    staff.tapped = True
    scenario.will_take_the_may(True, username="alice", source="The Blackstaff of Waterdeep")
    _to_alices_next_turn(scenario)
    assert staff.tapped


def test_other_permanents_untap_normally_while_it_stays_tapped():
    scenario = _board("Hedge Whisperer", ["Forest"])
    for state in scenario.game.battlefield:
        state.tapped = True
    scenario.will_take_the_may(True, username="alice", source="Hedge Whisperer")
    _to_alices_next_turn(scenario)
    assert _permanent(scenario, "Hedge Whisperer").tapped
    assert not _permanent(scenario, "Forest").tapped


def _activate_hedge(scenario):
    whisperer = _permanent(scenario, "Hedge Whisperer")
    sources = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest", "Forest")
    scenario.activate(whisperer, *sources[:4], index=0, username="alice", targets=[sources[4]])
    scenario.pass_until_resolved()
    return whisperer, sources[4]


def _hedge_board():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Hedge Whisperer", "Forest", "Forest", "Forest", "Forest", "Forest"],
            graveyard=["Craw Wurm"],
            library=["Island"] * 12,
        )
        .player("bob", library=["Island"] * 12)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_the_land_becomes_a_creature_while_the_source_stays_tapped():
    scenario = _hedge_board()
    _whisperer, land = _activate_hedge(scenario)
    chars = scenario.game.characteristics_of(land)
    assert Type.CREATURE in chars.types and Type.LAND in chars.types
    assert has_keyword(land, "haste", scenario.game)
    board = scenario.game.computed_board().of(land)
    assert (board.power, board.toughness) == (5, 5)


def test_the_animation_ends_when_the_source_untaps():
    scenario = _hedge_board()
    whisperer, land = _activate_hedge(scenario)
    whisperer.untap()
    chars = scenario.game.characteristics_of(land)
    assert Type.CREATURE not in chars.types
    assert Type.LAND in chars.types


def test_the_animation_does_not_return_when_the_source_taps_again():
    scenario = _hedge_board()
    whisperer, land = _activate_hedge(scenario)
    whisperer.untap()
    scenario.game.computed_board()
    whisperer.tapped = True
    assert Type.CREATURE not in scenario.game.characteristics_of(land).types


def test_the_blackstaff_animates_another_artifact_the_same_way():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["The Blackstaff of Waterdeep", "Sol Ring", "Island", "Island"],
            library=["Island"] * 12,
        )
        .player("bob", library=["Island"] * 12)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    staff = _permanent(scenario, "The Blackstaff of Waterdeep")
    ring = _permanent(scenario, "Sol Ring")
    sources = scenario.untapped_sources("Island", "Island")
    scenario.activate(staff, *sources, index=0, username="alice", targets=[ring])
    scenario.pass_until_resolved()
    assert Type.CREATURE in scenario.game.characteristics_of(ring).types
    board = scenario.game.computed_board().of(ring)
    assert (board.power, board.toughness) == (4, 4)
    staff.untap()
    assert Type.CREATURE not in scenario.game.characteristics_of(ring).types
    assert ring.zone is Zone.BATTLEFIELD
