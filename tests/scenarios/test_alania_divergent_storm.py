"""Alania, Divergent Storm's cast trigger (CR 603.4, CR 707.10).

"Whenever you cast a spell, if it's the first instant spell, the first
sorcery spell, or the first Otter spell other than Alania you've cast this
turn, you may have target opponent draw a card. If you do, copy that spell.
You may choose new targets for the copy."

Two things this file exists to prove work together now:

- **The intervening *if* is read whole** (W14 fix,
  `machines/abilities._INTERVENING_IF_CAST_THIS_TURN_BOUNDARY`): the clause's
  own internal commas used to truncate it before it ever reached
  `machines/triggers._first_spell_this_turn_holds` - see
  `tests/scenarios/test_intervening_if.py` and
  `tests/test_abilities.py::test_an_intervening_if_with_internal_commas_splits_correctly`.
- **CR 707.10's copy** is a new primitive (`Game.copy_spell`): a copy of a
  spell is not cast (so it never re-triggers Alania on itself), and it
  resolves independently, choosing new targets only if its controller wants
  to (CR 707.10c-shaped, `Game.offer_new_targets_for_copy`).

CR numbers looked up with `knowledge_search(type="rules")` in this session:
CR 603.4, CR 707.1, CR 707.2, CR 707.10, CR 112.1a.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Alania, Divergent Storm"] + ["Mountain"] * 4,
        )
        .player("bob", life=20, library=["Forest"] * 10)
    )


def test_the_first_instant_spell_this_turn_copies_and_the_copy_deals_damage_too():
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.will_take_the_may(True, source="Alania, Divergent Storm")
    scenario.will_take_the_may(True, source="Alania, Divergent Storm")  # new targets: keep same

    scenario.choose_trigger_targets("Alania, Divergent Storm", ["bob"])
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, targets=[scenario.player("bob")])

    assert scenario.stack_names() == [
        "Lightning Bolt",
        "Alania, Divergent Storm's triggered ability",
    ]
    while scenario.game.stack:
        scenario.resolve_top()

    assert bolt.zone is Zone.GRAVEYARD
    # bob drew a card from the trigger's own "have target opponent draw",
    # and took 3+3 = 6 damage: once from the real Bolt, once from its copy.
    assert len(scenario.player("bob").hand) == 1
    assert scenario.player("bob").life == 14


def test_the_copy_is_not_itself_a_cast_and_does_not_retrigger_alania():
    """CR 707.10: "a copy of a spell isn't cast." If the copy re-triggered
    Alania, a third Bolt's worth of damage (9 total) would land instead of
    two Bolts' worth (6)."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.will_take_the_may(True, source="Alania, Divergent Storm", times=None)
    scenario.choose_trigger_targets("Alania, Divergent Storm", ["bob"])
    scenario.cast_onto_stack("Lightning Bolt", mountain, targets=[scenario.player("bob")])

    while scenario.game.stack:
        scenario.resolve_top()

    assert scenario.player("bob").life == 14


def test_declining_the_draw_means_no_copy_either():
    """ "If you do" (CR 118.12): declining the optional draw skips the copy
    entirely - the copy is conditional on the draw, not a separate choice."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain")
    scenario.will_take_the_may(False, source="Alania, Divergent Storm")
    scenario.choose_trigger_targets("Alania, Divergent Storm", ["bob"])
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, targets=[scenario.player("bob")])

    while scenario.game.stack:
        scenario.resolve_top()

    assert bolt.zone is Zone.GRAVEYARD
    assert scenario.player("bob").hand == []
    assert scenario.player("bob").life == 17  # one Bolt only


def test_a_second_instant_spell_the_same_turn_does_not_trigger_again():
    """ "The first instant spell ... you've cast this turn" (CR 603.4): a
    second instant spell that same turn is not the first one any more, so
    Alania's trigger never fires for it."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt", "Lava Dart"],
            battlefield=["Alania, Divergent Storm"] + ["Mountain"] * 5,
        )
        .player("bob", life=20, library=["Forest"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (m1,) = scenario.untapped_sources("Mountain")
    scenario.will_take_the_may(True, source="Alania, Divergent Storm")
    scenario.choose_trigger_targets("Alania, Divergent Storm", ["bob"])
    scenario.cast_and_resolve("Lightning Bolt", m1, targets=[scenario.player("bob")])
    while scenario.game.stack:
        scenario.resolve_top()
    assert scenario.player("bob").life == 14  # Bolt + its copy

    remaining = scenario.untapped_sources("Mountain")[0]
    scenario.cast_and_resolve("Lava Dart", remaining, targets=[scenario.player("bob")])
    while scenario.game.stack:
        scenario.resolve_top()

    assert scenario.player("bob").life == 13  # Lava Dart alone, no second copy
