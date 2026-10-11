"""Scenario: two statics that act at a turn-structure or zone-change seam.

- "Untap all <group> you control during each other player's untap step."
  (CR 502.3: the untap step untaps the active player's permanents; this static
  ability is an effect that does the same for its controller's group in every
  other player's untap step - CR 604.2, CR 611.3.)
- "If a spell or ability an opponent controls causes you to discard this card,
  put it onto the battlefield instead of putting it into your graveyard."
  (CR 701.9a, CR 614.1a.)
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _to_bobs_upkeep(scenario):
    for _ in range(60):
        scenario.advance()
        if scenario.turn.active_player == "bob" and scenario.step is Step.UPKEEP:
            return
    raise AssertionError("never reached bob's upkeep")


def _tapped_board(alice_battlefield, bob_battlefield=()):
    scenario = (
        Scenario()
        .player("alice", battlefield=list(alice_battlefield))
        .player("bob", battlefield=list(bob_battlefield))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    for state in scenario.game.battlefield:
        if state.controller == "alice" and state.name != "Murkfiend Liege":
            state.tapped = True
    return scenario


def _tapped(scenario, name):
    return scenario.creature(name, "alice").tapped


def test_green_and_blue_creatures_untap_in_the_opponents_untap_step():
    scenario = _tapped_board(["Murkfiend Liege", "Grizzly Bears", "Lord of Atlantis", "Goblin Piker"])
    _to_bobs_upkeep(scenario)
    assert not _tapped(scenario, "Grizzly Bears")
    assert not _tapped(scenario, "Lord of Atlantis")


def test_a_creature_outside_the_group_stays_tapped():
    scenario = _tapped_board(["Murkfiend Liege", "Grizzly Bears", "Goblin Piker"])
    _to_bobs_upkeep(scenario)
    assert _tapped(scenario, "Goblin Piker")


def test_lands_stay_tapped_when_only_creatures_untap():
    scenario = _tapped_board(["Murkfiend Liege", "Forest"])
    _to_bobs_upkeep(scenario)
    land = next(s for s in scenario.game.battlefield if s.name == "Forest")
    assert land.tapped


def test_nothing_untaps_extra_in_the_controllers_own_untap_step_logic():
    scenario = _tapped_board(["Murkfiend Liege", "Grizzly Bears"])
    scenario.game.untap_step()  # alice is the active player: her own step, as always
    assert not _tapped(scenario, "Grizzly Bears")


def test_the_static_ends_when_the_source_leaves():
    scenario = _tapped_board(["Murkfiend Liege", "Grizzly Bears"])
    scenario.game.put_into_graveyard(scenario.creature("Murkfiend Liege", "alice"))
    _to_bobs_upkeep(scenario)
    assert _tapped(scenario, "Grizzly Bears")


def test_creatures_and_lands_untap_for_a_differently_worded_source():
    scenario = _tapped_board(["Seedborn Muse", "Grizzly Bears", "Forest"])
    _to_bobs_upkeep(scenario)
    assert not _tapped(scenario, "Grizzly Bears")


def test_opponent_permanents_are_not_untapped_by_my_source():
    scenario = _tapped_board(["Murkfiend Liege"], ["Llanowar Elves"])
    for state in scenario.game.battlefield:
        if state.controller == "bob":
            state.tapped = True
    scenario.game.untap_step()
    bob_elves = scenario.creature("Llanowar Elves", "bob")
    assert bob_elves.tapped


def _discard_board(victim_hand, caster_hand=("Mind Rot",)):
    scenario = (
        Scenario()
        .player("alice", hand=list(caster_hand), battlefield=["Swamp"] * 3)
        .player("bob", hand=list(victim_hand), battlefield=[])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _mind_rot(scenario, target):
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp")
    scenario.cast_and_resolve("Mind Rot", *sources, targets=[target])


def _graveyard(scenario, who):
    return [s.name for s in scenario.player(who).graveyard]


def test_an_opponents_discard_spell_puts_the_card_onto_the_battlefield():
    scenario = _discard_board(["Wilt-Leaf Liege", "Island"])
    _mind_rot(scenario, "bob")
    assert [s.name for s in scenario.game.battlefield if s.controller == "bob"] == [
        "Wilt-Leaf Liege"
    ]
    assert _graveyard(scenario, "bob") == ["Island"]


def test_a_differently_worded_card_does_the_same():
    scenario = _discard_board(["Obstinate Baloth", "Island"])
    _mind_rot(scenario, "bob")
    assert [s.name for s in scenario.game.battlefield if s.controller == "bob"] == [
        "Obstinate Baloth"
    ]


def test_my_own_discard_still_goes_to_the_graveyard():
    scenario = _discard_board(["Island"], caster_hand=("Mind Rot", "Wilt-Leaf Liege", "Island"))
    _mind_rot(scenario, "alice")
    assert not [s for s in scenario.game.battlefield if s.name == "Wilt-Leaf Liege"]
    assert "Wilt-Leaf Liege" in _graveyard(scenario, "alice")


def test_a_cleanup_discard_is_not_caused_by_an_opponent():
    scenario = _discard_board(["Wilt-Leaf Liege"] + ["Island"] * 7)
    scenario.game.player("bob").discard_to_maximum_hand_size()
    assert not [s for s in scenario.game.battlefield if s.name == "Wilt-Leaf Liege"]
