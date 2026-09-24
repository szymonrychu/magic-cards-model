"""CR 603.4: intervening "if" clauses about timing - whose turn, which phase,
the first combat, the defending player, and when a spell was cast.

Rules verified with `mise run rules:find` in the session that wrote this file:

- **CR 603.4** - "When the trigger event occurs, the ability checks whether
  the stated condition is true. The ability triggers only if it is; otherwise
  it does nothing. If the ability triggers, it checks the stated condition
  again as it resolves."
- **CR 608.2a** - the recheck on resolution. A timing fact cannot change while
  the ability waits on the stack: CR 500.2 ends a step only "when the stack is
  empty and all players pass in succession", so each reader here is shown
  true-and-resolving and false-and-never-triggering.
- **CR 109.5** - "you" is the controller of the source when the ability
  triggered; "their" names the player the trigger event names.
- **CR 505.1** - "The precombat and postcombat main phases are individually
  and collectively known as the main phase."
- **CR 506.1** / **CR 500.8** - a turn's combat phases are counted: an
  additional one is not "the first combat phase of the turn".
- **CR 506.2** - "During the combat phase of a two-player game, the nonactive
  player is the defending player."

Every one of these clauses failed closed (`InterveningIfNotice`, never
triggering) before `machines/conditions/timing.py` read it.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

# -- "if it's not their turn" -------------------------------------------------


def _raptor_board():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Scytheclaw Raptor", "Mountain"],
            hand=["Lightning Bolt"],
            library=["Plains"] * 3,
        )
        .player(
            "bob",
            battlefield=["Mountain", "Grizzly Bears"],
            hand=["Lightning Bolt"],
            library=["Plains"] * 3,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_a_spell_cast_off_its_casters_turn_triggers():
    """Scytheclaw Raptor: "Whenever a player casts a spell, if it's not their
    turn, this creature deals 4 damage to them." - bob casts on alice's turn."""
    scenario = _raptor_board()
    scenario.pass_priority("alice")
    scenario.cast_onto_stack("Lightning Bolt", username="bob", auto=True, targets=["alice"])
    assert scenario.stack_names() == ["Lightning Bolt", "Scytheclaw Raptor's triggered ability"]
    scenario.resolve_top()
    assert scenario.player("bob").life == 16
    assert scenario.game.intervening_if_notices == []


def test_a_spell_cast_on_its_casters_own_turn_does_not_trigger():
    """Alice casting on her own turn is "their turn" - CR 603.4: nothing."""
    scenario = _raptor_board()
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.cast_onto_stack("Lightning Bolt", auto=True, targets=[bears])
    assert scenario.stack_names() == ["Lightning Bolt"]
    assert scenario.game.intervening_if_notices == []


def test_their_names_the_caster_even_when_that_is_the_controller():
    """ "A player" includes the Raptor's own controller: alice casting on bob's
    turn takes the 4 damage herself."""
    scenario = _raptor_board()
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()
    scenario.advance()  # bob's upkeep
    scenario.pass_priority("bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.cast_onto_stack("Lightning Bolt", username="alice", auto=True, targets=[bears])
    assert scenario.stack_names() == ["Lightning Bolt", "Scytheclaw Raptor's triggered ability"]
    scenario.resolve_top()
    assert scenario.player("alice").life == 16


def test_not_their_turn_on_a_second_printing():
    """March of the World Ooze: "Whenever an opponent casts a spell, if it's
    not their turn, you create a 3/3 green Elephant creature token." """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["March of the World Ooze"], library=["Plains"] * 3)
        .player("bob", battlefield=["Mountain"], hand=["Lightning Bolt"], library=["Plains"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")
    scenario.cast_onto_stack("Lightning Bolt", username="bob", auto=True, targets=["alice"])
    scenario.pass_until_resolved()  # the trigger, on top
    assert "Elephant Token" in [s.name for s in scenario.game.permanents_controlled_by("alice")]


# -- "if it's your turn" ------------------------------------------------------


def _instigator_board():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Jeering Instigator"],
            battlefield=["Mountain"] * 6,
            library=["Plains"] * 4,
        )
        .player("bob", battlefield=["Grizzly Bears"], library=["Plains"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Jeering Instigator", username="alice")
    casting.use_keyword("Morph")
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources(*["Mountain"] * 3))
    scenario.put_on_stack(casting)
    return scenario, scenario.resolve_top()


def test_turned_face_up_on_your_turn_triggers_and_resolves():
    """Jeering Instigator: "When this creature is turned face up, if it's your
    turn, gain control of another target creature until end of turn." """
    scenario, instigator = _instigator_board()
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.choose_trigger_targets("Jeering Instigator", [bears])
    scenario.turn_face_up(instigator, *scenario.untapped_sources(*["Mountain"] * 3))
    assert scenario.stack_names() == ["Jeering Instigator's triggered ability"]
    scenario.pass_until_resolved()
    assert scenario.game.controller_of(bears).username == "alice"


def test_turned_face_up_on_an_opponents_turn_does_not_trigger():
    scenario, instigator = _instigator_board()
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()
    scenario.advance()  # bob's upkeep
    scenario.pass_priority("bob")
    scenario.turn_face_up(
        instigator,
        *scenario.untapped_sources(*["Mountain"] * 3, username="alice"),
        username="alice",
    )
    assert scenario.stack_names() == []
    assert scenario.game.intervening_if_notices == []


# -- "if it's your main phase" --------------------------------------------------


def test_a_land_entering_in_your_main_phase_triggers():
    """Moraug, Fury of Akoum: "Landfall - Whenever a land you control enters,
    if it's your main phase, there's an additional combat phase after this
    phase." (CR 505.1)"""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Moraug, Fury of Akoum"], hand=["Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    scenario.play_land("Mountain")
    assert scenario.stack_names() == ["Moraug, Fury of Akoum's triggered ability"]


def test_a_land_entering_outside_your_main_phase_does_not_trigger():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Moraug, Fury of Akoum"], hand=["Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    scenario.put_onto_battlefield("Mountain", "alice")
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == []
    assert scenario.game.intervening_if_notices == []


def test_your_main_phase_is_not_an_opponents_main_phase():
    """A land entering under alice's control during bob's main phase: a main
    phase, but not alice's (CR 505.1's "your")."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Moraug, Fury of Akoum"],
            hand=["Mountain"],
            library=["Plains"] * 3,
        )
        .player("bob", library=["Plains"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()
    scenario.advance()
    scenario.start_at(Step.PRECOMBAT_MAIN)  # bob's
    scenario.put_onto_battlefield("Mountain", "alice")
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == []


# -- "if it's the first combat phase of the turn" -----------------------------


def test_the_first_combat_phase_triggers_and_resolves():
    """Raph & Leo, Sibling Rivals: "Whenever Raph & Leo attack, if it's the
    first combat phase of the turn, untap one or two target attacking
    creatures. After this phase, there is an additional combat phase." """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Raph & Leo, Sibling Rivals"], library=["Plains"] * 3)
        .player("bob", library=["Plains"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    rivals = scenario.creature("Raph & Leo, Sibling Rivals", "alice")
    scenario.advance()  # beginning of combat: the first combat phase begins
    assert scenario.game.turn_count("combat_phases", "alice") == 1
    scenario.advance()  # declare attackers
    scenario.will_choose_targets(rivals, source="Raph & Leo, Sibling Rivals")
    scenario.attack_with(rivals)
    assert scenario.stack_names() == ["Raph & Leo, Sibling Rivals's triggered ability"]
    scenario.pass_until_resolved()
    assert rivals.untapped
    assert scenario.game.intervening_if_notices == []


def test_an_additional_combat_phase_is_not_the_first():
    """CR 500.8's additional combat phase is the turn's second: attacking in
    it does not trigger. The phase is added straight through the turn machine
    after the first combat ends, the way an effect adds one."""
    from magic_cards_model.machines.turn import COMBAT_PHASE_STEPS

    scenario = (
        Scenario()
        .player("alice", battlefield=["Raph & Leo, Sibling Rivals"], library=["Plains"] * 3)
        .player("bob", library=["Plains"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    rivals = scenario.creature("Raph & Leo, Sibling Rivals", "alice")
    while scenario.step is not Step.END_OF_COMBAT:
        scenario.advance()
    scenario.turn.insert_extra_phase(COMBAT_PHASE_STEPS)
    scenario.advance()  # the additional combat's beginning of combat
    assert scenario.step is Step.BEGINNING_OF_COMBAT
    assert scenario.game.turn_count("combat_phases", "alice") == 2
    scenario.advance()  # its declare attackers
    scenario.attack_with(rivals)
    assert scenario.stack_names() == []
    assert scenario.game.intervening_if_notices == []


# -- "if you're the defending player" -----------------------------------------


def test_the_defending_player_reads_the_attack():
    """Kazuul, Tyrant of the Cliffs: "Whenever a creature an opponent controls
    attacks, if you're the defending player, create a 3/3 red Ogre ... unless
    that creature's controller pays {3}." (CR 506.2) - bob attacks alice."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Kazuul, Tyrant of the Cliffs"], library=["Plains"] * 3)
        .player("bob", battlefield=["Grizzly Bears"], library=["Plains"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.advance()
    scenario.advance()
    scenario.start_at(Step.DECLARE_ATTACKERS)  # bob's
    scenario.attack_with(scenario.creature("Grizzly Bears", "bob"), defending="alice")
    assert scenario.stack_names() == ["Kazuul, Tyrant of the Cliffs's triggered ability"]
    assert scenario.game.intervening_if_notices == []


def test_the_defending_player_reads_false_with_no_attack_on_you():
    """The same reader asked of a board where nobody attacks alice: with no
    attack event, and no attack in combat, alice is not defending."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Kazuul, Tyrant of the Cliffs"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    assert scenario.game.condition_holds("alice", "you're the defending player") is False
    assert scenario.game.condition_holds("bob", "you're the defending player") is False


# -- "if you cast it during your main phase" ----------------------------------


def _mark_board():
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Sentinel's Mark"],
            battlefield=["Grizzly Bears", "Plains", "Plains"],
            library=["Plains"] * 3,
        )
        .player("bob", library=["Plains"] * 3)
        .build()
    )


def test_cast_during_your_main_phase_triggers():
    """Sentinel's Mark (flash): "Addendum - When this Aura enters, if you cast
    it during your main phase, enchanted creature gains lifelink until end of
    turn." - the `CastRecord` keeps the step it was cast in."""
    scenario = _mark_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    mark = scenario.cast_onto_stack(
        "Sentinel's Mark", *scenario.untapped_sources("Plains", "Plains"), targets=[bears]
    )
    scenario.resolve_top()
    assert mark.zone is Zone.BATTLEFIELD
    assert scenario.stack_names() == ["Sentinel's Mark's triggered ability"]


def test_cast_with_flash_in_combat_does_not_trigger():
    scenario = _mark_board()
    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.cast_onto_stack(
        "Sentinel's Mark", *scenario.untapped_sources("Plains", "Plains"), targets=[bears]
    )
    scenario.resolve_top()
    assert scenario.stack_names() == []
    assert scenario.game.intervening_if_notices == []


def test_put_onto_the_battlefield_was_never_cast():
    """Not cast at all: no `CastRecord`, so "if you cast it" is false."""
    scenario = _mark_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose(scenario.creature("Grizzly Bears", "alice"), source="Sentinel's Mark")
    scenario.put_onto_battlefield("Sentinel's Mark", "alice")
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == []
