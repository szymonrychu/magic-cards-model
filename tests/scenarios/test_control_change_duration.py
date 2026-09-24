"""Control-changing effects with a stated duration (CR 613.1b, layer 2;
CR 611.2a: an effect lasts "as long as stated by the spell or ability
creating it").

- Evil's Thrall: "Gain control of target creature until end of turn. If you
  control a Villain with greater mana value than that creature, gain control
  of that creature until the end of your next turn instead. Untap that
  creature. It gains haste until end of turn." - the "instead" is decided as
  the spell resolves; "until the end of your next turn" outlives this turn's
  cleanup and the opponent's turn, and ends at the cleanup of the caster's
  next turn (CR 514.2).
- The Super Hero Civil War, chapter I: "Gain control of up to two target
  creatures with total mana value 6 or less for as long as this Saga remains
  on the battlefield." - CR 611.2b's duration, and a restriction across the
  targets (CR 601.2c). Chapter III: "Target creature you control fights up to
  one other target creature." (CR 701.14a; CR 115.6 "up to one").

Off-set proof (legal, in no deck list):

- Rangers of Ithilien: "When this creature enters, gain control of up to one
  target creature with lesser power for as long as you control this
  creature. Then the Ring tempts you." - the same "for as long as" control
  reader, "you control" instead of "remains", and a "Then" instruction after
  it.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario

THRALL = "Evil's Thrall"
CIVIL_WAR = "The Super Hero Civil War"


def _controller(scenario, permanent):
    return scenario.game.controller_of(permanent).username


def _next_turn(scenario):
    """Walk into the following turn, resolving whatever fires."""
    turns = scenario.turn.turns_taken
    while scenario.turn.turns_taken == turns:
        scenario.advance()
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()


def _cleanup(scenario):
    scenario.start_at(Step.END_STEP)
    scenario.advance()


# -- Evil's Thrall ------------------------------------------------------------------


def _thrall_board(*, alice=()):
    return (
        Scenario()
        .player(
            "alice",
            hand=[THRALL],
            battlefield=["Mountain"] * 3 + list(alice),
            library=["Mountain"] * 5,
        )
        .player("bob", battlefield=["Grizzly Bears"], library=["Forest"] * 5)
        .build()
    )


def _cast_thrall(scenario, target):
    return scenario.cast_and_resolve(
        THRALL, *scenario.untapped_sources("Mountain", "Mountain", "Mountain"), targets=[target]
    )


def test_evils_thrall_steals_untaps_and_hastes_until_end_of_turn():
    scenario = _thrall_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    bears.tap()

    _cast_thrall(scenario, bears)

    assert _controller(scenario, bears) == "alice"
    assert not bears.tapped
    assert "Haste" in scenario.game.computed_board().of(bears).abilities
    _cleanup(scenario)
    assert _controller(scenario, bears) == "bob"


def test_evils_thrall_with_a_bigger_villain_keeps_it_through_your_next_turn():
    """Fin Fang Foom (a Villain, mana value 4) against Grizzly Bears (2)."""
    scenario = _thrall_board(alice=["Fin Fang Foom"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    _cast_thrall(scenario, bears)
    _cleanup(scenario)
    assert _controller(scenario, bears) == "alice"  # past this turn's cleanup

    _next_turn(scenario)  # bob's turn
    assert scenario.turn.active_player == "bob"
    assert _controller(scenario, bears) == "alice"

    _next_turn(scenario)  # alice's next turn
    assert scenario.turn.active_player == "alice"
    assert _controller(scenario, bears) == "alice"
    _cleanup(scenario)
    assert _controller(scenario, bears) == "bob"


def test_haste_from_evils_thrall_still_ends_this_turn():
    scenario = _thrall_board(alice=["Fin Fang Foom"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    _cast_thrall(scenario, bears)
    _cleanup(scenario)

    assert "Haste" not in scenario.game.computed_board().of(bears).abilities


def test_a_villain_of_equal_mana_value_is_not_enough():
    """ "Greater" mana value: Scientist Supreme of A.I.M. (2) is not greater
    than Grizzly Bears (2)."""
    scenario = _thrall_board(alice=["Scientist Supreme of A.I.M."])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    _cast_thrall(scenario, bears)
    _cleanup(scenario)

    assert _controller(scenario, bears) == "bob"


def test_a_bigger_non_villain_does_not_count():
    scenario = _thrall_board(alice=["Hill Giant", "Serra Angel"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    _cast_thrall(scenario, bears)
    _cleanup(scenario)

    assert _controller(scenario, bears) == "bob"


def test_the_stolen_creature_can_attack_at_once():
    scenario = _thrall_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    _cast_thrall(scenario, bears)

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)

    assert bears in scenario.attackers()


# -- The Super Hero Civil War ------------------------------------------------------


def _civil_war_board(bob):
    return (
        Scenario()
        .player(
            "alice",
            hand=[CIVIL_WAR],
            battlefield=["Mountain", "Mountain", "Mountain", "Plains", "Plains", "Grizzly Bears"],
            library=["Mountain"] * 5,
        )
        .player("bob", battlefield=list(bob), library=["Forest"] * 5)
        .build()
    )


def _cast_civil_war(scenario, targets):
    scenario.choose_trigger_targets(CIVIL_WAR, list(targets))
    scenario.cast_and_resolve(
        CIVIL_WAR,
        *scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Plains", "Plains"),
    )
    scenario.pass_until_resolved()  # chapter I
    return scenario.find(CIVIL_WAR, Zone.BATTLEFIELD, "alice")


def _chapter(scenario, targets):
    scenario.choose_trigger_targets(CIVIL_WAR, list(targets))
    scenario.game.saga_lore_step()
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()


def test_chapter_one_steals_two_creatures_while_the_saga_remains():
    scenario = _civil_war_board(["Hill Giant", "Grizzly Bears"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")

    saga = _cast_civil_war(scenario, [giant, bears])

    assert _controller(scenario, giant) == "alice"
    assert _controller(scenario, bears) == "alice"
    _cleanup(scenario)
    assert _controller(scenario, giant) == "alice"  # not an end-of-turn effect

    scenario.game.destroy(saga)
    assert _controller(scenario, giant) == "bob"
    assert _controller(scenario, bears) == "bob"


def test_chapter_one_refuses_targets_over_total_mana_value_six():
    """Serra Angel (5) and Grizzly Bears (2) total 7 - not a legal pair."""
    scenario = _civil_war_board(["Serra Angel", "Grizzly Bears"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")

    with pytest.raises(ValueError, match="total mana value"):
        _cast_civil_war(scenario, [angel, bears])


def test_chapter_one_may_take_just_one_or_none():
    scenario = _civil_war_board(["Serra Angel"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    angel = scenario.creature("Serra Angel", "bob")

    _cast_civil_war(scenario, [angel])
    assert _controller(scenario, angel) == "alice"


def test_control_ends_when_the_saga_is_sacrificed_after_chapter_three():
    scenario = _civil_war_board(["Hill Giant"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    saga = _cast_civil_war(scenario, [giant])
    alices_bears = scenario.creature("Grizzly Bears", "alice")

    _chapter(scenario, [])  # II
    _chapter(scenario, [alices_bears])  # III, fight nothing
    scenario.state_based_actions()

    assert saga.zone is Zone.GRAVEYARD  # CR 714.4
    assert _controller(scenario, giant) == "bob"


def test_chapter_three_fights():
    scenario = _civil_war_board(["Hill Giant"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    _cast_civil_war(scenario, [])
    bears = scenario.creature("Grizzly Bears", "alice")

    _chapter(scenario, [])  # II: +1/+1 and vigilance until end of turn
    _next_turn(scenario)
    _next_turn(scenario)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _chapter(scenario, [bears, giant])  # III
    scenario.state_based_actions()

    assert bears.zone is Zone.GRAVEYARD  # 2/2 took 3
    assert giant.damage == 2


def test_chapter_three_with_no_second_target_fights_nothing():
    scenario = _civil_war_board(["Hill Giant"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    _cast_civil_war(scenario, [])
    bears = scenario.creature("Grizzly Bears", "alice")

    _chapter(scenario, [])
    _next_turn(scenario)
    _next_turn(scenario)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _chapter(scenario, [bears])

    assert bears.damage == 0
    assert giant.damage == 0


# -- Rangers of Ithilien (off-set proof) ---------------------------------------------


def test_rangers_of_ithilien_steal_a_smaller_creature_while_controlled():
    scenario = (
        Scenario()
        .player("alice", hand=["Rangers of Ithilien"], library=["Mountain"] * 5)
        .player("bob", battlefield=["Grizzly Bears"], library=["Forest"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.choose_trigger_targets("Rangers of Ithilien", [bears])
    rangers = scenario.put_onto_battlefield("Rangers of Ithilien", "alice")
    scenario.pass_until_resolved()

    assert _controller(scenario, bears) == "alice"
    _cleanup(scenario)
    assert _controller(scenario, bears) == "alice"

    scenario.game.destroy(rangers)
    assert _controller(scenario, bears) == "bob"
