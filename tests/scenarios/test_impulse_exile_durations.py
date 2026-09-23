"""Impulse exile: "Exile the top N cards of your library. <duration>, you may
play those cards/that card." - each printed duration honoured exactly.

Three durations are printed on this template, and they are not the same:

- **"this turn" / "until end of turn"** - CR 514.2: "all 'until end of
  turn' and 'this turn' effects end" in the cleanup step.
- **"Until the end of your next turn"** - Cori Mountain Monastery's `{3}{R},
  {T}` ability, Gundabad Opportunist's enters trigger (the second printing,
  off the deck pool). CR 611.2a: "lasts as long as stated" - past the
  granting turn's cleanup, past every opponent turn, and only gone at the
  cleanup of the controller's own next turn.
- **"Until your next end step"** - Riveteers Charm's second mode, Haste
  Magic's trailing "You may play it until your next end step." (the second
  printing, off the deck pool, and a different word order). Gone the moment
  the controller's next end step begins - never at a cleanup, and never on
  an opponent's end step; granted *during* that end step, it runs on to the
  next one.

Whichever duration, the permission is only permission (CR 601.3): a land
among the exiled cards is played only with a land drop available (CR 305.2a,
CR 305.2b) and only when CR 116.2a allows a land to be played at all (a main
phase of its controller's own turn, stack empty), and a spell pays its own
mana cost.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import PlayAction
from magic_cards_model.machines.effects import parse_mode_effect
from magic_cards_model.machines.modes import modal_profile
from magic_cards_model.models import Zone
from tests.cards import card
from tests.scenarios.harness import Scenario

CHARM = "Riveteers Charm"


def _end_turn(scenario: Scenario) -> None:
    """The active player's cleanup (CR 514.1, 514.2), then into the next turn."""
    scenario.start_at(Step.CLEANUP)
    scenario.turn_based_actions()
    scenario.advance()


def _exiled_since(scenario: Scenario, before: set) -> list:
    return [state for state in scenario.game.exile if state.id not in before]


# --------------------------------------------------------------------------
# "Until the end of your next turn" - Cori Mountain Monastery (ability form)
# --------------------------------------------------------------------------


def _cori_board(*, library: list[str] | None = None, hand: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=hand or [],
            battlefield=["Cori Mountain Monastery", "Mountain", "Mountain", "Mountain", "Mountain"],
            library=library if library is not None else ["Forest", "Island", "Island"],
        )
        .player("bob", library=["Island"] * 5)
    )


def _activate_cori(scenario: Scenario) -> list:
    cori = scenario.find("Cori Mountain Monastery", Zone.BATTLEFIELD, "alice")
    mountains = scenario.untapped_sources(
        "Mountain", "Mountain", "Mountain", "Mountain", username="alice"
    )
    before = {state.id for state in scenario.game.exile}
    scenario.activate(cori, *mountains, index=1, username="alice")
    scenario.resolve_top()
    return _exiled_since(scenario, before)


def test_cori_exiles_exactly_the_top_card_and_grants_a_play_permission():
    scenario = _cori_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    exiled = _activate_cori(scenario)

    assert [state.name for state in exiled] == ["Forest"]
    assert [state.name for state in scenario.player("alice").library] == ["Island", "Island"]
    permission = scenario.game.play_permission_for(exiled[0], "alice", PlayAction.PLAY)
    assert permission is not None
    assert permission.action is PlayAction.PLAY
    assert permission.pays_mana_cost is True
    assert permission.source_name == "Cori Mountain Monastery"


def test_cori_permission_survives_the_granting_turns_cleanup_and_the_opponents_turn():
    scenario = _cori_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (forest,) = _activate_cori(scenario)

    _end_turn(scenario)
    assert scenario.turn.active_player == "bob"
    assert scenario.game.play_permission_for(forest, "alice", PlayAction.PLAY) is not None

    _end_turn(scenario)
    assert scenario.turn.active_player == "alice"
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.play_land("Forest", from_zone=Zone.EXILE)
    assert forest.zone is Zone.BATTLEFIELD


def test_cori_permission_ends_at_the_cleanup_of_the_controllers_next_turn():
    scenario = _cori_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (forest,) = _activate_cori(scenario)

    _end_turn(scenario)  # alice's granting turn
    _end_turn(scenario)  # bob's turn
    scenario.start_at(Step.END_STEP)
    assert scenario.game.play_permission_for(forest, "alice", PlayAction.PLAY) is not None
    scenario.start_at(Step.CLEANUP)
    scenario.turn_based_actions()

    assert forest.zone is Zone.EXILE
    assert scenario.game.play_permission_for(forest, "alice", PlayAction.PLAY) is None


def test_cori_activated_on_the_opponents_turn_lasts_through_the_controllers_next_turn():
    """ "Your next turn" from bob's turn is alice's very next turn."""
    scenario = _cori_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _end_turn(scenario)
    assert scenario.turn.active_player == "bob"
    scenario.start_at(Step.PRECOMBAT_MAIN)
    for permanent in scenario.game.permanents_controlled_by("alice"):
        permanent.tapped = False
    scenario.pass_priority("bob")

    (forest,) = _activate_cori(scenario)
    _end_turn(scenario)  # bob's turn ends: not alice's turn, nothing ends
    assert scenario.game.play_permission_for(forest, "alice", PlayAction.PLAY) is not None

    _end_turn(scenario)  # alice's next turn ends
    assert scenario.game.play_permission_for(forest, "alice", PlayAction.PLAY) is None


def test_an_exiled_land_needs_a_land_drop_that_is_still_available():
    """CR 305.2b: the permission to play a card is not a second land drop."""
    scenario = _cori_board(hand=["Mountain"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (forest,) = _activate_cori(scenario)
    scenario.play_land("Mountain")

    with pytest.raises(ValueError):
        scenario.play_land("Forest", from_zone=Zone.EXILE)
    assert forest.zone is Zone.EXILE

    _end_turn(scenario)
    _end_turn(scenario)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.play_land("Forest", from_zone=Zone.EXILE)
    assert forest.zone is Zone.BATTLEFIELD


def test_an_exiled_land_is_played_only_at_sorcery_timing():
    """CR 116.2a: a land is played only in a main phase of its controller's own
    turn - the grant does not let it come down on the opponent's turn."""
    scenario = _cori_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (forest,) = _activate_cori(scenario)
    _end_turn(scenario)
    scenario.start_at(Step.PRECOMBAT_MAIN)

    with pytest.raises(ValueError):
        scenario.play_land("Forest", username="alice", from_zone=Zone.EXILE)
    assert forest.zone is Zone.EXILE


def test_gundabad_opportunist_enters_trigger_prints_the_same_template():
    """The second printing: a triggered ability, singular "that card"."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Gundabad Opportunist"],
            battlefield=["Mountain"] * 4,
            library=["Lightning Bolt", "Island"],
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    before = {state.id for state in scenario.game.exile}
    scenario.cast_and_resolve("Gundabad Opportunist", *scenario.untapped_sources(*["Mountain"] * 4))
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    (bolt,) = _exiled_since(scenario, before)
    assert bolt.name == "Lightning Bolt"
    _end_turn(scenario)
    _end_turn(scenario)
    assert scenario.game.play_permission_for(bolt, "alice") is not None
    _end_turn(scenario)
    assert scenario.game.play_permission_for(bolt, "alice") is None


# --------------------------------------------------------------------------
# "Until your next end step" - Riveteers Charm's mode 2 (a mode) and Haste
# Magic (a spell, trailing duration)
# --------------------------------------------------------------------------


def _charm_board(*, hand_extra: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=[CHARM, *(hand_extra or [])],
            battlefield=["Swamp", "Mountain", "Forest", "Mountain"],
            library=["Forest", "Lightning Bolt", "Island", "Swamp"],
        )
        .player("bob", library=["Island"] * 5)
    )


def _cast_charm_mode_two(scenario: Scenario, username: str = "alice") -> list:
    before = {state.id for state in scenario.game.exile}
    casting = scenario.cast(CHARM, username=username)
    casting.choose_modes([2])
    payment = casting.begin_paying()
    sources = scenario.untapped_sources("Swamp", "Mountain", "Forest", username=username)
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    return _exiled_since(scenario, before)


def test_riveteers_charm_mode_two_exiles_three_and_permits_playing_them():
    scenario = _charm_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    exiled = _cast_charm_mode_two(scenario)

    assert [state.name for state in exiled] == ["Forest", "Lightning Bolt", "Island"]
    assert [state.name for state in scenario.player("alice").library] == ["Swamp"]
    for state in exiled:
        permission = scenario.game.play_permission_for(state, "alice", PlayAction.PLAY)
        assert permission is not None
        assert permission.source_name == CHARM


def test_every_mode_of_riveteers_charm_is_read():
    modes = modal_profile(card(CHARM)).modes
    assert len(modes) == 3
    assert all(parse_mode_effect(mode, 0) is not None for mode in modes)


def test_the_exiled_spell_still_costs_its_own_mana():
    scenario = _charm_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    exiled = _cast_charm_mode_two(scenario)
    bolt = next(state for state in exiled if state.name == "Lightning Bolt")

    casting = scenario.cast("Lightning Bolt", from_zone=Zone.EXILE)
    casting.use_permission()
    casting.choose_targets(["bob"])
    assert str(casting.total_cost.mana) == "{R}"
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Mountain"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bolt.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 17


def test_only_one_of_two_exiled_lands_can_be_played_with_one_land_drop():
    scenario = _charm_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    exiled = _cast_charm_mode_two(scenario)
    forest = next(state for state in exiled if state.name == "Forest")
    island = next(state for state in exiled if state.name == "Island")

    scenario.play_land("Forest", from_zone=Zone.EXILE)
    with pytest.raises(ValueError):
        scenario.play_land("Island", from_zone=Zone.EXILE)

    assert forest.zone is Zone.BATTLEFIELD
    assert island.zone is Zone.EXILE


def test_the_end_step_permission_ends_as_the_controllers_end_step_begins():
    """Not at cleanup: the end step itself is the boundary."""
    scenario = _charm_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    exiled = _cast_charm_mode_two(scenario)

    scenario.start_at(Step.POSTCOMBAT_MAIN)
    assert all(scenario.game.play_permission_for(s, "alice", PlayAction.PLAY) for s in exiled)
    scenario.advance()
    assert scenario.step is Step.END_STEP

    for state in exiled:
        assert state.zone is Zone.EXILE
        assert scenario.game.play_permission_for(state, "alice", PlayAction.PLAY) is None
    assert not any(permission.source_name == CHARM for permission in scenario.game.play_permissions)


def test_cast_on_the_opponents_turn_the_permission_survives_their_end_step():
    """ "Your next end step": bob's end step is not alice's, so the grant runs
    through it and through alice's own next main phase."""
    scenario = _charm_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _end_turn(scenario)
    assert scenario.turn.active_player == "bob"
    scenario.start_at(Step.PRECOMBAT_MAIN)
    for permanent in scenario.game.permanents_controlled_by("alice"):
        permanent.tapped = False
    scenario.pass_priority("bob")
    exiled = _cast_charm_mode_two(scenario)
    forest = next(state for state in exiled if state.name == "Forest")

    scenario.start_at(Step.END_STEP)
    assert scenario.game.play_permission_for(forest, "alice", PlayAction.PLAY) is not None
    scenario.start_at(Step.CLEANUP)
    scenario.turn_based_actions()
    scenario.advance()
    assert scenario.turn.active_player == "alice"
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.play_land("Forest", from_zone=Zone.EXILE)
    assert forest.zone is Zone.BATTLEFIELD
    scenario.start_at(Step.END_STEP)
    assert all(
        scenario.game.play_permission_for(s, "alice", PlayAction.PLAY) is None
        for s in exiled
        if s.zone is Zone.EXILE
    )


def test_granted_during_the_controllers_own_end_step_it_runs_to_the_next_one():
    """An end step that has already begun is not the "next" one."""
    scenario = _charm_board().build()
    scenario.start_at(Step.END_STEP)
    exiled = _cast_charm_mode_two(scenario)
    bolt = next(state for state in exiled if state.name == "Lightning Bolt")

    assert scenario.game.play_permission_for(bolt, "alice") is not None
    scenario.start_at(Step.CLEANUP)
    scenario.turn_based_actions()
    assert scenario.game.play_permission_for(bolt, "alice") is not None
    scenario.advance()
    _end_turn(scenario)  # bob's turn
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert scenario.game.play_permission_for(bolt, "alice") is not None
    scenario.start_at(Step.END_STEP)
    assert scenario.game.play_permission_for(bolt, "alice") is None


def test_the_expired_end_step_permission_says_why():
    scenario = _charm_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _cast_charm_mode_two(scenario)
    scenario.start_at(Step.END_STEP)

    with pytest.raises(ValueError, match="end step"):
        scenario.cast("Lightning Bolt", from_zone=Zone.EXILE).use_permission()


def test_haste_magic_trailing_duration_reads_the_same_way():
    """The second printing: "Target creature gets +3/+1 and gains haste until
    end of turn. Exile the top card of your library. You may play it until
    your next end step." - singular "it", the duration printed last."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Haste Magic"],
            battlefield=["Mountain", "Mountain", "Grizzly Bears"],
            library=["Forest", "Island"],
        )
        .player("bob", library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    before = {state.id for state in scenario.game.exile}
    scenario.cast_and_resolve(
        "Haste Magic", *scenario.untapped_sources("Mountain", "Mountain"), targets=[bears]
    )

    (forest,) = _exiled_since(scenario, before)
    assert forest.name == "Forest"
    assert scenario.game.characteristics_of(bears).power == 5
    assert scenario.game.play_permission_for(forest, "alice", PlayAction.PLAY) is not None
    scenario.start_at(Step.END_STEP)
    assert scenario.game.play_permission_for(forest, "alice", PlayAction.PLAY) is None
