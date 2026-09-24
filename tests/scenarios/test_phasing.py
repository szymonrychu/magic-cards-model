"""Scenario: phasing (CR 702.26), through "Target <creature> phases out."

Teferi, Master of Time's "-3: Target creature you don't control phases out."
is the reported card; Haystack's "{2}, {T}: Target creature you control phases
out." is the second printing proving the reader is the template, not the card
(a different target restriction, a mana-and-tap cost rather than a loyalty
one, and a phase-out of the activator's own creature).

The rules, read whole with `mise run rules:find` this session:

- CR 702.26b: "If a permanent phases out, its status changes to 'phased out.'
  Except for rules and effects that specifically mention phased-out
  permanents, a phased-out permanent is treated as though it does not exist.
  It can't affect or be affected by anything else in the game. A permanent
  that phases out is removed from combat."
- CR 702.26d: phasing changes no zone and no control; zone-change triggers do
  not trigger; tokens continue to exist; counters remain.
- CR 702.26g: Auras and Equipment attached to it phase out "indirectly" at
  the same time and phase back in along with it.
- CR 702.26m: "If an effect causes a player to skip their untap step, the
  phasing event simply doesn't occur that turn."
- CR 702.26k: phased-out permanents owned by a player who leaves the game also
  leave the game.
- CR 502.1: in the untap step, "all phased-out permanents that the active
  player controlled when they phased out phase in", before anything untaps
  (CR 502.3).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.legal_actions import legal_actions
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from magic_cards_model.models.token import token_copy_of

from .harness import Scenario

TEFERI = "Teferi, Master of Time"
TEFERI_MINUS_THREE = 1


def _to_turn_of(scenario, username: str) -> None:
    """Advance, turn-based actions and all, into `username`'s next turn -
    a later one than the turn in progress, even when that is theirs."""
    begun = scenario.turn.turns_taken
    scenario.advance()
    while scenario.turn.turns_taken == begun or scenario.turn.active_player != username:
        scenario.advance()


def _to_main_of(scenario, username: str) -> None:
    _to_turn_of(scenario, username)
    while scenario.step is not Step.PRECOMBAT_MAIN:
        scenario.advance()


def _teferi_board(*bob_battlefield: str, alice_hand: tuple[str, ...] = ()) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            library=["Island"] * 6,
            hand=list(alice_hand),
            battlefield=[TEFERI, "Mountain", "Mountain"],
        )
        .player("bob", library=["Forest"] * 6, battlefield=list(bob_battlefield))
    )


def _phase_out_with_teferi(scenario, victim) -> None:
    teferi = scenario.creature(TEFERI, "alice")
    scenario.activate(teferi, index=TEFERI_MINUS_THREE, username="alice", targets=[victim])
    scenario.resolve_top()


# -- the basic event -------------------------------------------------------


def test_teferi_phases_out_a_creature_it_does_not_exist_but_changes_no_zone():
    scenario = _teferi_board("Grizzly Bears").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    _phase_out_with_teferi(scenario, bears)

    assert bears.phased_out
    # CR 702.26d: no zone change - still a battlefield object ...
    assert bears.zone is Zone.BATTLEFIELD
    # ... but CR 702.26b: treated as though it does not exist.
    assert bears not in scenario.game.battlefield
    assert bears not in scenario.game.permanents_controlled_by("bob")
    assert scenario.game.find_by_id(bears.id) is None
    assert bears in scenario.game.phased_out


def test_teferi_refuses_a_creature_its_controller_controls():
    """ "you don't control" is the target restriction, read off the text."""
    scenario = (
        Scenario()
        .player("alice", library=["Island"] * 3, battlefield=[TEFERI, "Grizzly Bears"])
        .player("bob", library=["Forest"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    teferi = scenario.creature(TEFERI, "alice")
    own_bears = scenario.creature("Grizzly Bears", "alice")

    with pytest.raises(ValueError):
        scenario.activate(teferi, index=TEFERI_MINUS_THREE, targets=[own_bears])


def test_a_phased_out_creature_cannot_be_targeted():
    scenario = _teferi_board("Grizzly Bears", alice_hand=("Shock",)).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    _phase_out_with_teferi(scenario, bears)

    with pytest.raises(ValueError):
        scenario.cast("Shock", "alice", targets=[bears])


# -- phasing back in (CR 502.1) --------------------------------------------


def test_it_phases_in_during_its_controllers_next_untap_step_and_can_attack():
    """CR 702.26d: phasing changes no control, so a creature that phases in
    has been under its controller's control continuously - no summoning
    sickness - and CR 502.1 phases it in before CR 502.3 untaps it."""
    scenario = _teferi_board("Grizzly Bears").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    bears.tap()
    _phase_out_with_teferi(scenario, bears)

    _to_main_of(scenario, "bob")

    assert not bears.phased_out
    assert bears in scenario.game.battlefield
    assert bears not in scenario.game.phased_out
    assert not bears.tapped, "CR 502.1 phases it in before CR 502.3 untaps"
    while scenario.step is not Step.DECLARE_ATTACKERS:
        scenario.advance()
    assert scenario.can_attack(bears, "alice")


def test_it_stays_phased_out_through_the_other_players_turn():
    """Phased out on bob's own turn, it misses alice's whole turn too and only
    returns at bob's *next* untap step (CR 502.1: the untap step of the player
    who controlled it when it phased out)."""
    scenario = (
        Scenario()
        .player("alice", library=["Island"] * 6, battlefield=[TEFERI])
        .player("bob", library=["Forest"] * 6, battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _to_main_of(scenario, "bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.pass_priority("bob")
    _phase_out_with_teferi(scenario, bears)

    _to_main_of(scenario, "alice")
    assert bears.phased_out, "alice's untap step does not phase bob's creature in"

    _to_turn_of(scenario, "bob")
    assert not bears.phased_out


def test_a_skipped_untap_step_does_not_phase_it_in():
    """CR 702.26m, with Haystack on alice's own creature and Savor the Moment's
    "Skip the untap step of that turn": the extra turn's untap step never
    happens, so the phasing event does not either; it phases in at the next
    untap step alice actually has."""
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Island"] * 8,
            hand=["Savor the Moment"],
            battlefield=["Haystack", "Grizzly Bears", "Plains"] + ["Island"] * 4,
        )
        .player("bob", library=["Forest"] * 8)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    haystack = scenario.creature("Haystack", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    islands = scenario.untapped_sources("Island", "Island", "Island", username="alice")
    scenario.cast_and_resolve("Savor the Moment", *islands)
    plains_and_island = scenario.untapped_sources("Plains", "Island", username="alice")
    scenario.activate(haystack, *plains_and_island, targets=[bears])
    scenario.resolve_top()
    assert bears.phased_out

    _to_turn_of(scenario, "alice")  # the extra turn, untap step skipped
    assert scenario.turn.taking_extra_turn
    assert bears.phased_out, "CR 702.26m: no untap step, no phasing"

    _to_turn_of(scenario, "bob")
    _to_turn_of(scenario, "alice")
    assert not bears.phased_out


# -- combat (CR 702.26b, CR 506.4) ------------------------------------------


def test_phasing_out_an_attacker_removes_it_from_combat():
    """Teferi's own static puts the -3 on bob's turn, after attackers are
    declared: the attacker is removed from combat and deals no damage."""
    scenario = (
        Scenario()
        .player("alice", library=["Island"] * 6, battlefield=[TEFERI])
        .player("bob", library=["Forest"] * 6, battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _to_turn_of(scenario, "bob")
    while scenario.step is not Step.DECLARE_ATTACKERS:
        scenario.advance()
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(bears, defending="alice")
    assert bears in scenario.attackers()

    scenario.pass_priority("bob")
    _phase_out_with_teferi(scenario, bears)

    assert bears not in scenario.attackers()
    assert scenario.game.combat.attack_by(bears.id) is None
    life = scenario.player("alice").life
    while scenario.step is not Step.END_OF_COMBAT:
        scenario.advance()
    assert scenario.player("alice").life == life


def test_a_phased_out_creature_cannot_block():
    scenario = (
        Scenario()
        .player("alice", library=["Island"] * 6, battlefield=[TEFERI, "Runeclaw Bear"])
        .player("bob", library=["Forest"] * 6, battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    _phase_out_with_teferi(scenario, bears)
    runeclaw = scenario.creature("Runeclaw Bear", "alice")
    runeclaw.summoning_sick = False
    while scenario.step is not Step.DECLARE_ATTACKERS:
        scenario.advance()
    scenario.attack_with(runeclaw, defending="bob")
    while scenario.step is not Step.DECLARE_BLOCKERS:
        scenario.advance()

    with pytest.raises(ValueError):
        scenario.block(runeclaw, bears)


# -- static abilities and counts --------------------------------------------


def test_a_phased_out_lord_stops_applying_its_static_ability():
    """Angel of Jubilation's "Other nonblack creatures you control get +1/+1"
    does not exist while the Angel is phased out, and applies again once it
    is back (CR 702.26b, CR 702.26c)."""
    scenario = _teferi_board("Angel of Jubilation", "Grizzly Bears").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Angel of Jubilation", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    assert (bears.power, bears.toughness) == (3, 3)

    _phase_out_with_teferi(scenario, angel)
    assert (bears.power, bears.toughness) == (2, 2)

    _to_turn_of(scenario, "bob")
    assert (bears.power, bears.toughness) == (3, 3)


def test_a_phased_out_creature_is_not_counted():
    """Armorcraft Judge's "draw a card for each creature you control with a
    +1/+1 counter on it" does not count alice's own creature phased out by
    Haystack, while a phased-in one beside it is counted - and CR 702.26d
    keeps the counter on it while it is gone."""
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Island"] * 6,
            hand=["Armorcraft Judge"],
            battlefield=["Haystack", "Grizzly Bears", "Runeclaw Bear"] + ["Forest"] * 6,
        )
        .player("bob", library=["Forest"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.add_counters(Counter.PLUS_ONE, 1)
    scenario.creature("Runeclaw Bear", "alice").add_counters(Counter.PLUS_ONE, 1)
    haystack = scenario.creature("Haystack", "alice")
    forests = scenario.untapped_sources("Forest", "Forest", username="alice")
    scenario.activate(haystack, *forests, targets=[bears])
    scenario.resolve_top()
    assert bears.phased_out
    hand_before = len(scenario.player("alice").hand)

    scenario.cast_and_resolve("Armorcraft Judge", auto=True)
    while scenario.game.stack:
        scenario.resolve_top()

    # The Judge left the hand and drew one card - for the Runeclaw Bear,
    # none for the phased-out Grizzly Bears.
    assert len(scenario.player("alice").hand) == hand_before - 1 + 1
    assert bears.counter_count(Counter.PLUS_ONE) == 1


# -- state-based actions ----------------------------------------------------


def test_a_second_legend_cast_while_the_first_is_phased_out_survives():
    """CR 704.5j sees only one Thalia while the other is phased out, and both
    once it phases back in - then its controller keeps one."""
    scenario = (
        Scenario()
        .player("alice", library=["Island"] * 6, battlefield=[TEFERI])
        .player(
            "bob",
            library=["Forest"] * 6,
            hand=["Thalia, Guardian of Thraben"],
            battlefield=["Thalia, Guardian of Thraben", "Plains", "Plains"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _to_main_of(scenario, "bob")
    first = scenario.creature("Thalia, Guardian of Thraben", "bob")
    scenario.pass_priority("bob")
    _phase_out_with_teferi(scenario, first)

    plains = scenario.untapped_sources("Plains", "Plains", username="bob")
    second = scenario.cast_and_resolve("Thalia, Guardian of Thraben", *plains, username="bob")
    scenario.state_based_actions()
    assert second.zone is Zone.BATTLEFIELD
    assert first.phased_out

    _to_turn_of(scenario, "alice")
    assert first.phased_out
    _to_turn_of(scenario, "bob")
    scenario.state_based_actions()
    thalias = [
        state for state in scenario.game.battlefield if state.name == "Thalia, Guardian of Thraben"
    ]
    assert len(thalias) == 1, "CR 704.5j once both exist again"


# -- attachments phase indirectly (CR 702.26g) ------------------------------


def test_an_aura_and_an_equipment_phase_out_and_in_with_the_creature():
    scenario = _teferi_board("Grizzly Bears", "Rancor", "Bonesplitter").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    rancor = scenario.creature("Rancor", "bob")
    bonesplitter = scenario.creature("Bonesplitter", "bob")
    rancor.attach_to(bears)
    bonesplitter.attach_to(bears)

    _phase_out_with_teferi(scenario, bears)
    scenario.state_based_actions()

    for attached in (rancor, bonesplitter):
        assert attached.phased_out
        assert attached not in scenario.game.battlefield
        assert attached.zone is Zone.BATTLEFIELD, "CR 704.5m never saw a lone Aura"

    _to_turn_of(scenario, "bob")
    for attached in (rancor, bonesplitter):
        assert not attached.phased_out
        assert attached.attached_to == bears.id
    assert bears.power == 2 + 2 + 2


# -- zone-change triggers, tokens and counters (CR 702.26d) -----------------


def test_phasing_in_is_not_entering_the_battlefield():
    """Didact Echo's "When this creature enters, draw a card" does not trigger
    when it phases back in."""
    scenario = _teferi_board("Didact Echo").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    echo = scenario.creature("Didact Echo", "bob")
    _phase_out_with_teferi(scenario, echo)
    assert not scenario.pending_triggers

    _to_turn_of(scenario, "bob")
    assert not echo.phased_out
    assert not scenario.pending_triggers
    assert not any(item.name == "Didact Echo" for item in scenario.game.stack)


def test_a_token_continues_to_exist_while_phased_out():
    scenario = (
        Scenario()
        .player("alice", library=["Island"] * 6, battlefield=[TEFERI])
        .player("bob", library=["Forest"] * 6, battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    # A token copy the engine itself makes (CR 707.2), not a hand-built one.
    (token,) = token_copy_of(scenario.game, bears, "bob")
    _phase_out_with_teferi(scenario, token)
    scenario.state_based_actions()
    assert token.phased_out

    _to_turn_of(scenario, "bob")
    assert token in scenario.game.battlefield


# -- effects that expire while it is gone (CR 702.26f) ----------------------


def test_an_until_end_of_turn_pump_expires_while_it_is_phased_out():
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Island"] * 6,
            hand=["Giant Growth"],
            battlefield=["Haystack", "Grizzly Bears", "Forest", "Forest", "Forest"],
        )
        .player("bob", library=["Forest"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    (forest,) = scenario.untapped_sources("Forest", username="alice")
    scenario.cast_and_resolve("Giant Growth", forest, targets=[bears])
    assert bears.power == 5
    haystack = scenario.creature("Haystack", "alice")
    forests = scenario.untapped_sources("Forest", "Forest", username="alice")
    scenario.activate(haystack, *forests, targets=[bears])
    scenario.resolve_top()

    _to_turn_of(scenario, "bob")
    _to_turn_of(scenario, "alice")
    assert not bears.phased_out
    assert bears.power == 2


# -- a player leaving (CR 702.26k) ------------------------------------------


def test_a_phased_out_permanent_leaves_with_its_owner():
    scenario = (
        Scenario()
        .player("alice", library=["Island"] * 6, battlefield=[TEFERI])
        .player("bob", library=["Forest"] * 6, battlefield=["Grizzly Bears"])
        .player("carol", library=["Swamp"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    _phase_out_with_teferi(scenario, bears)

    scenario.game.concede("bob")

    assert bears not in scenario.game.phased_out


# -- the action surface -----------------------------------------------------


def test_legal_actions_offer_no_target_that_is_phased_out():
    scenario = _teferi_board("Grizzly Bears", "Runeclaw Bear", alice_hand=("Shock",)).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    _phase_out_with_teferi(scenario, bears)

    offered = [
        candidate
        for action in legal_actions(scenario.game, "alice")
        for slot in action.target_slots
        for candidate in slot.candidates
    ]
    assert offered, "the board still offers the Runeclaw Bear as a target"
    assert bears.id not in offered
