"""Scenario: two `machines/triggers.py` clause readers ask a target's or a
controlled permanent's *computed* characteristics (CR 613.5), not the
printed `CardState.types`/`.subtypes` (CR 712.8d's up-face-only reading).

Every CR number below was looked up with `mise run rules:find` this session.

- **`condition_matches`'s "targets only a single creature you control"**
  clause (Frontline Heroism: "Whenever you cast a spell that targets only a
  single creature you control, create a 1/1 red Soldier creature token with
  haste, then copy that spell.") checked `Type.CREATURE not in target.types`
  two lines after already confirming the target is on the battlefield - the
  printed line, not CR 613.5's computed one. Giant Growth cast at an
  earthbent land (CR 701.66a) is exactly that shape: the land is a creature
  only on the computed board.
- **`intervening_if_holds`'s "you control no [subtype]s other than this
  creature"** clause (Thopter Assembly: "if you control no Thopters other
  than this creature") reads every *other* controlled permanent's printed
  `.subtypes`. No printing in the pool grants a computed-only subtype to a
  second controlled permanent that would make this specific clause fire
  differently from its own regression test below - see the note on that
  test for why. Fixed anyway (CR 613.5 makes no exception for an untested
  consumer) and hoisted to one `computed_board()` per call, mirroring the
  sibling clause handlers already on the computed board
  (`_control_creature_with_power_holds`, `_controlled_subtype_count_holds`).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_frontline_heroism_triggers_off_a_spell_that_targets_an_animated_land():
    """Giant Growth targets alice's own earthbent Forest - "only a single
    creature you control" is true only if the target's computed types say
    creature, which the printed Land-only line does not.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Badgermole Cub", "Giant Growth"],
            battlefield=["Forest", "Forest", "Forest", "Forest", "Frontline Heroism"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest")
    pay_sources, target_forest, pump_source = sources[:2], sources[2], sources[3]
    scenario.choose_trigger_targets("Badgermole Cub", [target_forest])
    scenario.cast_and_resolve("Badgermole Cub", *pay_sources)
    scenario.pass_until_resolved()
    assert scenario.game.characteristics_of(target_forest).is_creature

    soldiers_before = len([s for s in scenario.game.battlefield if s.name == "Soldier Token"])
    scenario.cast_and_resolve("Giant Growth", pump_source, targets=[target_forest])
    scenario.pass_until_resolved()

    soldiers_after = [s for s in scenario.game.battlefield if s.name == "Soldier Token"]
    assert len(soldiers_after) == soldiers_before + 1, (
        "Frontline Heroism's trigger fired: the target was a creature on the computed board"
    )


def test_frontline_heroism_does_not_trigger_targeting_a_plain_land():
    """The inverse: Giant Growth cannot even legally target a plain Forest
    (CR 601.2c: it names only a creature), so the trigger's own premise
    never arises. Guards a fix that treated every permanent as a creature.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Giant Growth"],
            battlefield=["Forest", "Frontline Heroism"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.find("Forest", Zone.BATTLEFIELD)
    (source,) = scenario.untapped_sources("Forest")

    with pytest.raises(ValueError):
        scenario.cast_and_resolve("Giant Growth", source, targets=[forest])


def test_thopter_assemblys_own_intervening_if_still_returns_it_to_hand():
    """Regression for `intervening_if_holds`'s move to a hoisted board:
    Thopter Assembly's own "if you control no Thopters other than this
    creature" still fires when it is genuinely alone. No printing in the
    pool grants the Thopter subtype computed-only to a *different*
    permanent, so this cannot probe the printed/computed distinction the
    way the module's other tests do; it exists so the threading-through of
    one board per call is not a silent regression on Thopter Assembly's own
    behaviour.
    """
    scenario = Scenario().player("alice", battlefield=["Thopter Assembly"]).build()
    assembly = scenario.find("Thopter Assembly", Zone.BATTLEFIELD)
    scenario.advance()  # untap -> upkeep
    assert scenario.stack_names() == ["Thopter Assembly's triggered ability"]

    scenario.pass_until_resolved()

    assert assembly.zone is Zone.HAND
    thopters = [state for state in scenario.game.battlefield if state.name == "Thopter Token"]
    assert len(thopters) == 5
