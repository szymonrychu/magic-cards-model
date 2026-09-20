"""Mana that survives a step or phase ending (CR 500.5a, 500.5b, 514.2).

CR 500.5's ordinary rule empties every player's mana pool as each step and
phase ends (`tests/scenarios/test_mana_pool_emptying.py`). Two printed
sentences replace that turn-based action for the mana they themselves added:

- CR 702.189a's firebending ("Until end of combat, you don't lose this mana
  as steps and phases end") - proved here on Boiling Rock Rioter, "Firebending
  1", a fixed count. CR 500.5a: "Effects that last 'until end of combat'
  expire at the end of the combat phase, not at the beginning of the end of
  combat step."
- Photon, Mighty Marvel's combat-damage trigger ("add that much mana of any
  one color. Until end of turn, you don't lose this mana as steps and phases
  end.") - CR 500.5b points at CR 514.2, which ends "until end of turn"
  effects in the cleanup step.

Both sentences were already matched by `machines/effects.py`'s parsers
(`_parse_firebending_add_mana`, `_parse_add_one_mana_of_any_color_trigger`)
but not carried out; `models/mana.py`'s `ManaRetentionScope`/`RetainedMana`
and `ManaPool.empty`'s new `expiring` parameter are the general mechanism
that now does, wired through `Game.empty_mana_pools`/`_advance_past_checks`/
`advance_to` (CR 500.5a's boundary) and `Game.cleanup_step` (CR 500.5b/514.2's).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Color, Zone

from .harness import Scenario


def test_photon_mana_survives_combat_and_second_main_dies_at_cleanup():
    """Photon, Mighty Marvel: 2 power deals 2 combat damage to bob, adding 2
    mana of a chosen colour that survives every ordinary CR 500.5 boundary for
    the rest of the turn and only empties in the cleanup step (CR 514.2)."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Photon, Mighty Marvel"])
        .player("bob")
        .manual_turn_based_actions()
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    photon = scenario.creature("Photon, Mighty Marvel", "alice")
    scenario.attack_with(photon)
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.will_choose(Color.RED.value, source="Photon, Mighty Marvel")
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    pool = scenario.player("alice").mana_pool
    assert pool.floating.get(Color.RED) == 2  # added, during the combat damage step

    scenario.advance()  # declare attackers -> declare blockers (harness never
    # left declare attackers for the trigger above, so this is the combat
    # damage step's own boundary ending)
    scenario.advance()  # -> combat damage
    scenario.advance()  # -> end of combat
    assert pool.floating.get(Color.RED) == 2  # survives into the end of combat step

    scenario.advance()  # end of combat -> postcombat main: the combat PHASE
    # ends crossing this boundary (CR 511.3) - an "until end of combat" tag
    # would die right here, but Photon's is "until end of turn"
    assert pool.floating.get(Color.RED) == 2  # survives the second main phase

    scenario.advance()  # -> end step
    assert pool.floating.get(Color.RED) == 2

    scenario.advance()  # -> cleanup step. Ordinary CR 500.5 boundary emptying
    # ran on the way in (`manual_turn_based_actions` still runs it - only the
    # step's *own* turn-based action is skipped), and it is not CR 514.2's
    # own action, so the mana is still here.
    assert pool.floating.get(Color.RED) == 2

    scenario.turn_based_actions()  # CR 514.1/514.2, run by hand under manual
    # mode - the second of its two simultaneous actions is where "until end
    # of turn" mana finally empties.
    assert pool.floating.get(Color.RED, 0) == 0
    assert pool.retained == []


def test_firebending_mana_survives_end_of_combat_step_dies_at_phase_end():
    """Boiling Rock Rioter: "Firebending 1 (Whenever this creature attacks,
    add {R}. This mana lasts until end of combat.)" Its mana outlives the end
    of combat step but is gone the instant the combat phase itself ends
    (CR 500.5a), which is one step boundary earlier than Photon's own tag."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Boiling Rock Rioter"])
        .player("bob")
        .manual_turn_based_actions()
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    rioter = scenario.creature("Boiling Rock Rioter", "alice")
    scenario.attack_with(rioter)
    while scenario.game.stack or scenario.pending_triggers:
        scenario.pass_until_resolved()

    pool = scenario.player("alice").mana_pool
    assert pool.floating.get(Color.RED) == 1

    scenario.no_blocks()
    scenario.combat_damage()

    scenario.advance()  # declare attackers -> declare blockers
    assert pool.floating.get(Color.RED) == 1
    scenario.advance()  # -> combat damage
    assert pool.floating.get(Color.RED) == 1
    scenario.advance()  # -> end of combat
    assert pool.floating.get(Color.RED) == 1  # survives into the end of combat step

    scenario.advance()  # end of combat -> postcombat main: the combat phase
    # ends crossing this boundary (CR 511.3, CR 500.5a) - firebending's own
    # tag dies right here, one boundary before Photon's would.
    assert pool.floating.get(Color.RED, 0) == 0
    assert pool.retained == []


def test_ordinary_mana_alongside_retained_still_empties_at_step_end():
    """Firebending's red is retained; a Forest tapped in the same step for
    green is not - only the ordinary mana is gone once that step ends."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Boiling Rock Rioter", "Forest"])
        .player("bob")
        .manual_turn_based_actions()
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    rioter = scenario.creature("Boiling Rock Rioter", "alice")
    scenario.attack_with(rioter)
    while scenario.game.stack or scenario.pending_triggers:
        scenario.pass_until_resolved()

    (forest,) = scenario.untapped_sources("Forest")
    scenario.activate(forest)

    pool = scenario.player("alice").mana_pool
    assert pool.floating.get(Color.RED) == 1
    assert pool.floating.get(Color.GREEN) == 1

    scenario.advance()  # declare attackers -> declare blockers: an ordinary
    # CR 500.5 boundary, nowhere near either retention's own named point
    assert pool.floating.get(Color.GREEN, 0) == 0  # ordinary mana empties as usual
    assert pool.floating.get(Color.RED) == 1  # firebending's tag keeps its mana


def test_retained_mana_pays_a_cost_like_ordinary_mana():
    """Firebending's red is spendable exactly like ordinary floating mana -
    nothing about the retention tag narrows what it may pay for."""
    scenario = (
        Scenario()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Boiling Rock Rioter"])
        .player("bob")
        .manual_turn_based_actions()
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    rioter = scenario.creature("Boiling Rock Rioter", "alice")
    scenario.attack_with(rioter)
    while scenario.game.stack or scenario.pending_triggers:
        scenario.pass_until_resolved()

    pool = scenario.player("alice").mana_pool
    assert pool.floating.get(Color.RED) == 1
    assert pool.retained_total == 1

    bolt = scenario.cast_and_resolve("Lightning Bolt", targets=["bob"])

    assert bolt.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 17
    assert pool.floating.get(Color.RED, 0) == 0
    assert pool.retained == []
