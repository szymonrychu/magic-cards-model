"""Scenario: one player controlling another during their turn (CR 723).

The mechanic is CR 723, "Controlling Another Player" - the section Emrakul, the
Promised End's cast trigger reaches for: "you gain control of target opponent
during that player's next turn."

The rules it is built out of, all of them read this session:

- **CR 723.1** - "This effect applies to the next turn that the affected player
  actually takes. The affected player is controlled during the entire turn; the
  effect doesn't end until the beginning of the next turn."
- **CR 723.1a** - multiple effects on the same player overwrite; the last one
  created works.
- **CR 723.1b** - "If a turn is skipped, any pending player-controlling effects
  wait until the player who would be affected actually takes a turn."
- **CR 723.3** - "Only control of the player changes. All objects are controlled
  by their normal controllers. A player who's being controlled during their turn
  is still the active player."
- **CR 723.5** - the controller "makes all choices and decisions the controlled
  player is allowed to make or is told to make by the rules or by any objects".
- **CR 723.5a** - "can use only that player's resources (cards, mana, and so on)
  to pay costs for that player".
- **CR 723.6** - "The controller of another player can't make that player
  concede."
- **CR 723.8** - the controller goes on making their own choices.
- **CR 723.9** - an effect may give a player control of themselves.

The effect lives on `TurnMachine`, because CR 723.1 scopes it to a whole turn;
`PriorityMachine` mirrors it so it knows who may act.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.turn import TurnMachine

from .harness import Scenario


def two_players() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", library=["Forest"], battlefield=["Forest", "Sol Ring"])
        .player("bob", library=["Island"], battlefield=["Island", "Grizzly Bears"])
    )


def three_players() -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", library=["Forest"], battlefield=["Forest"])
        .player("bob", library=["Island"], battlefield=["Island"])
        .player("carol", library=["Swamp"], battlefield=["Swamp"])
    )


def next_turn(scenario) -> None:
    """Run the rest of the current turn out and begin the next one, at upkeep.

    Stops at upkeep rather than untap because CR 502.4 gives nobody priority in
    the untap step, and every caller here is about who holds priority on the new
    turn. CR 117.3a's "the active player receives priority at the beginning of
    most steps" is true of upkeep, which is the first step of the new turn where
    there is any priority to be had.
    """
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()  # the new turn's untap step
    scenario.advance()  # upkeep, where somebody has priority again


# -- when the effect applies (CR 723.1) ------------------------------------


def test_gaining_control_changes_nothing_on_the_turn_it_was_gained():
    """CR 723.1 scopes the effect to the controlled player's *next* turn."""
    scenario = two_players().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.game.gain_control_of_player("alice", "bob")

    assert scenario.game.controller_of_player("bob") == "bob"
    assert not scenario.game.is_controlling_player("alice", "bob")


def test_the_effect_takes_hold_when_the_controlled_player_s_turn_begins():
    scenario = two_players().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.gain_control_of_player("alice", "bob")

    next_turn(scenario)

    assert scenario.turn.active_player == "bob"
    assert scenario.game.controller_of_player("bob") == "alice"
    assert scenario.game.is_controlling_player("alice", "bob")


def test_the_controlled_player_is_still_the_active_player():
    """CR 723.3: control of the player changes and nothing else does."""
    scenario = two_players().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.gain_control_of_player("alice", "bob")
    next_turn(scenario)

    assert scenario.turn.active_player == "bob"
    assert scenario.game.active_player.username == "bob"


def test_only_control_of_the_player_changes_not_of_their_permanents():
    """CR 723.3: "All objects are controlled by their normal controllers"."""
    scenario = two_players().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.gain_control_of_player("alice", "bob")
    next_turn(scenario)

    bears = scenario.creature("Grizzly Bears", "bob")
    assert scenario.game.controller_of(bears).username == "bob"
    assert bears in scenario.game.permanents_controlled_by("bob")
    assert bears not in scenario.game.permanents_controlled_by("alice")


def test_the_effect_lasts_the_whole_turn():
    """CR 723.1: "The affected player is controlled during the entire turn"."""
    scenario = two_players().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.gain_control_of_player("alice", "bob")
    next_turn(scenario)

    for _ in range(len(list(Step)) - 1):
        if scenario.step is Step.CLEANUP:
            break
        scenario.advance()
        assert scenario.game.controller_of_player("bob") == "alice", (
            f"still controlled in {scenario.step}"
        )
    assert scenario.step is Step.CLEANUP


def test_the_effect_ends_at_the_beginning_of_the_next_turn():
    """CR 723.1: "the effect doesn't end until the beginning of the next turn"."""
    scenario = two_players().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.gain_control_of_player("alice", "bob")

    next_turn(scenario)
    assert scenario.game.controller_of_player("bob") == "alice"

    next_turn(scenario)
    assert scenario.turn.active_player == "alice"
    assert scenario.game.controller_of_player("bob") == "bob"


def test_a_pending_effect_waits_until_the_player_actually_takes_a_turn():
    """CR 723.1b: a turn the controlled player never takes does not spend it.

    Modelled here with an extra turn (CR 500.7): alice queues an extra turn for
    herself, so bob's turn does not come next. The effect is still waiting when
    it finally does.
    """
    scenario = two_players().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.gain_control_of_player("alice", "bob")
    scenario.game.grant_extra_turn("alice")

    next_turn(scenario)
    assert scenario.turn.active_player == "alice", "alice's extra turn came first"
    assert scenario.game.controller_of_player("bob") == "bob", "nothing was spent on it"

    next_turn(scenario)
    assert scenario.turn.active_player == "bob"
    assert scenario.game.controller_of_player("bob") == "alice"


def test_a_later_effect_overwrites_an_earlier_one():
    """CR 723.1a: "The last one to be created is the one that works"."""
    scenario = three_players().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.game.gain_control_of_player("carol", "bob")
    scenario.game.gain_control_of_player("alice", "bob")

    next_turn(scenario)
    assert scenario.game.controller_of_player("bob") == "alice"


def test_control_of_yourself_leaves_every_decision_where_it_was():
    """CR 723.9: "That player will make their own decisions and choices as normal"."""
    scenario = two_players().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.gain_control_of_player("bob", "bob")
    next_turn(scenario)

    assert scenario.game.controller_of_player("bob") == "bob"
    assert not scenario.game.is_controlling_player("bob", "bob")


# -- who decides (CR 723.5, 723.8) -----------------------------------------


def test_the_controller_acts_on_the_controlled_player_s_priority():
    """CR 723.5, with CR 723.3 keeping the priority itself where it was."""
    scenario = two_players().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.gain_control_of_player("alice", "bob")
    next_turn(scenario)

    assert scenario.priority_holder == "bob", "CR 723.3: bob still holds it"
    assert scenario.game.priority.decider == "alice"

    scenario.pass_priority("alice")

    assert scenario.priority_holder == "alice", "the pass was bob's, made by alice"


def test_the_controlled_player_makes_no_decisions_of_their_own():
    """CR 723.5 hands over *all* the choices the controlled player may make."""
    scenario = two_players().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.gain_control_of_player("alice", "bob")
    next_turn(scenario)

    with pytest.raises(ValueError, match="alice is making bob's decisions"):
        scenario.pass_priority("bob")


def test_a_third_player_still_cannot_act_on_that_priority():
    scenario = three_players().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.gain_control_of_player("alice", "bob")
    next_turn(scenario)

    with pytest.raises(ValueError, match="does not have priority"):
        scenario.pass_priority("carol")


def test_the_controller_still_makes_their_own_choices():
    """CR 723.8: controlling bob does not stop alice deciding for alice."""
    scenario = two_players().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.gain_control_of_player("alice", "bob")
    next_turn(scenario)

    scenario.pass_priority("alice")  # bob's priority, alice deciding
    assert scenario.priority_holder == "alice"

    scenario.pass_priority("alice")  # alice's own priority, alice deciding
    assert scenario.game.why_cannot_decide_for("alice", "alice") is None


def test_nothing_lets_a_player_decide_for_somebody_they_do_not_control():
    scenario = two_players().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert scenario.game.why_cannot_decide_for("bob", "bob") is None
    refusal = scenario.game.why_cannot_decide_for("alice", "bob")
    assert refusal is not None
    assert "CR 723.5" in refusal


# -- what the controller may spend (CR 723.5a) ------------------------------


def test_the_controller_may_spend_only_the_controlled_player_s_resources():
    """CR 723.5a: alice making bob cast something pays out of bob's board."""
    scenario = two_players().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.gain_control_of_player("alice", "bob")
    next_turn(scenario)

    (bobs_island,) = scenario.untapped_sources("Island", username="bob")
    (alices_forest,) = scenario.untapped_sources("Forest", username="alice")

    assert scenario.game.why_cannot_pay_with("bob", bobs_island) is None

    refusal = scenario.game.why_cannot_pay_with("bob", alices_forest)
    assert refusal is not None
    assert "CR 723.5a" in refusal


# -- the one decision that is never handed over (CR 723.6) ------------------


def test_the_controller_cannot_make_the_controlled_player_concede():
    scenario = two_players().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.gain_control_of_player("alice", "bob")
    next_turn(scenario)

    with pytest.raises(ValueError, match="CR 723.6"):
        scenario.game.concede("bob", by="alice")

    assert scenario.game.is_in_game("bob")
    assert scenario.game.winner is None


def test_the_controlled_player_may_still_concede_themselves():
    """CR 723.6: "A player may concede the game at any time, even if they are
    controlled by another player." """
    scenario = two_players().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.gain_control_of_player("alice", "bob")
    next_turn(scenario)

    scenario.game.concede("bob", by="bob")

    assert not scenario.game.is_in_game("bob")
    assert scenario.game.winner == "alice"  # CR 104.2a


# -- a player who leaves (CR 800.4) ----------------------------------------


def test_a_player_who_leaves_takes_the_control_effect_with_them():
    scenario = three_players().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.gain_control_of_player("alice", "bob")

    scenario.game.concede("alice")

    next_turn(scenario)
    assert scenario.turn.active_player == "bob"
    assert scenario.game.controller_of_player("bob") == "bob"


# -- the card that does this (CR 603.2, CR 723.1) ---------------------------


def emrakul_castable() -> Scenario:
    """Alice with Emrakul, a graveyard worth {3} off it, and five Sol Rings."""
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Emrakul, the Promised End"],
            graveyard=["Counterspell", "Lava Spike", "Grizzly Bears"],
            battlefield=["Sol Ring"] * 5,
        )
        .player("bob", library=["Island"], battlefield=["Island"])
    )


def cast_emrakul(scenario, at: str = "bob"):
    """Cast Emrakul with its cast trigger aimed at one opponent (CR 603.3d)."""
    scenario.choose_trigger_targets("Emrakul, the Promised End", [at])
    casting = scenario.cast("Emrakul, the Promised End")
    payment = scenario.game.determine_total_cost(casting)
    scenario.pay_with(payment, *scenario.untapped_sources(*["Sol Ring"] * 5))
    return scenario.put_on_stack(casting)


def test_the_cast_trigger_goes_on_the_stack_above_the_spell():
    """CR 603.2g, 601.2a: "When you cast this spell" fires as it is cast, and
    CR 603.3 puts it on the stack above the spell that caused it."""
    scenario = emrakul_castable().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    cast_emrakul(scenario)

    assert scenario.stack_names() == [
        "Emrakul, the Promised End",
        "Emrakul, the Promised End's triggered ability",
    ]
    (trigger,) = scenario.game.abilities_on_stack
    assert [str(target) for target in trigger.targets] == ["bob"]
    assert trigger.controller == "alice"


def test_emrakuls_cast_trigger_gains_control_of_the_targeted_opponent():
    """CR 723.1, straight off the card."""
    scenario = emrakul_castable().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    cast_emrakul(scenario)
    scenario.resolve_top()  # the trigger

    assert scenario.turn.pending_player_control == {"bob": "alice"}


# -- the machine on its own -------------------------------------------------


def test_the_turn_machine_refuses_a_control_effect_for_a_stranger():
    machine = TurnMachine(players=["alice", "bob"])

    with pytest.raises(KeyError):
        machine.gain_control_of_player("alice", "mallory")


def test_a_pending_effect_is_spent_the_first_time_it_applies():
    """One turn per effect: bob's turn after next is his own again."""
    machine = TurnMachine(players=["alice", "bob"])
    machine.gain_control_of_player("alice", "bob")

    machine.begin_next_turn()  # bob's turn
    assert machine.controller_of_player("bob") == "alice"
    assert machine.pending_player_control == {}

    machine.begin_next_turn()  # alice's turn
    machine.begin_next_turn()  # bob's turn again
    assert machine.controller_of_player("bob") == "bob"
