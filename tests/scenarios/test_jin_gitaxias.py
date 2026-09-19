"""Jin-Gitaxias, Progress Tyrant's own two triggers (CR 603.1, CR 707.10,
CR 701.6a), verified with `mise run rules:find` in this session:

    Whenever you cast an artifact, instant, or sorcery spell, copy that
    spell. You may choose new targets for the copy. This ability triggers
    only once each turn. (A copy of a permanent spell becomes a token.)
    Whenever an opponent casts an artifact, instant, or sorcery spell,
    counter that spell. This ability triggers only once each turn.

Both used to fall through unread for the same structural reason:
"an artifact, instant, or sorcery spell" is a comma-separated type list
*inside* the trigger condition, ahead of the comma that actually separates
CR 603.1's "[condition], [effect]" - `machines/abilities._split_top_level`'s
naive first-top-level-comma cut sliced the condition down to "you cast an
artifact", leaving "instant, or sorcery spell, copy that spell. ..." as the
supposed effect text, which matched nothing (`machines/abilities.
_CAST_TYPE_LIST_CONDITION_BOUNDARY` is the fix, the same class of defect
`_INTERVENING_IF_CAST_THIS_TURN_BOUNDARY` already fixes on the intervening-
*if* side, per `test_alania_divergent_storm.py`).

The copy trigger's own bare "Copy that spell. You may choose new targets for
the copy." (no preceding action, unlike Alania, Divergent Storm's richer
two-clause chain) needed its own general reader,
`machines/effects._parse_copy_that_spell_clause` - CR 707.10's copy
(`Game.copy_spell`) and CR 707.10c's retargeting offer (`Game.
offer_new_targets_for_copy`), the same two primitives Alania's own reader
already uses. The counter trigger's "Counter that spell." already had a
general reader (`_parse_counter_that_spell_clause`, Vexing Bauble) once the
condition split correctly.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Jin-Gitaxias, Progress Tyrant"] + ["Mountain"] * 4,
        )
        .player("bob", life=20, hand=["Lightning Bolt"], battlefield=["Mountain"] * 4)
    )


def test_casting_an_instant_copies_it_and_the_copy_can_be_retargeted():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.will_take_the_may(True, source="Jin-Gitaxias, Progress Tyrant")
    scenario.choose_trigger_targets("Jin-Gitaxias, Progress Tyrant", ["bob"])

    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, targets=[scenario.player("bob")])
    scenario.game.put_triggers_on_stack()

    while scenario.game.stack:
        scenario.resolve_top()

    assert bolt.zone is Zone.GRAVEYARD
    # 3 from the real Bolt, 3 from its copy: 6 total.
    assert scenario.player("bob").life == 14


def test_declining_new_targets_leaves_the_copy_aimed_at_the_original_target():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.will_take_the_may(False, source="Jin-Gitaxias, Progress Tyrant")

    scenario.cast_onto_stack("Lightning Bolt", mountain, targets=[scenario.player("bob")])
    scenario.game.put_triggers_on_stack()

    while scenario.game.stack:
        scenario.resolve_top()

    assert scenario.player("bob").life == 14


def test_this_ability_triggers_only_once_each_turn_so_a_second_spell_is_not_copied():
    """CR 603.2h: the copy trigger's own restriction. Two instants cast in
    the same turn only copy the first."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt", "Shock"],
            battlefield=["Jin-Gitaxias, Progress Tyrant"] + ["Mountain"] * 6,
        )
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(True, source="Jin-Gitaxias, Progress Tyrant", times=None)

    sources = scenario.untapped_sources("Mountain", "Mountain")
    scenario.cast_onto_stack("Lightning Bolt", sources[0], targets=[scenario.player("bob")])
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
    after_first = scenario.player("bob").life
    assert after_first == 14  # 3 real + 3 copy

    more_sources = scenario.untapped_sources("Mountain", "Mountain")
    scenario.cast_onto_stack("Shock", more_sources[0], targets=[scenario.player("bob")])
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["Shock"]  # no second trigger
    while scenario.game.stack:
        scenario.resolve_top()

    assert scenario.player("bob").life == after_first - 2  # Shock alone, not copied


def test_an_opponents_spell_is_countered():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    while scenario.turn.active_player != "bob":
        scenario.advance()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")

    bolt = scenario.cast_onto_stack(
        "Lightning Bolt", mountain, targets=[scenario.player("alice")], username="bob"
    )
    scenario.game.put_triggers_on_stack()

    while scenario.game.stack:
        scenario.resolve_top()

    assert bolt.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 20  # never resolved
