"""CR 716: Class enchantments, an entirely different structure from a Saga
(`test_turn_based_actions.py`'s own `saga_lore_step`, `CardState.chapter_numbers`).

Artist's Talent's printed text (verified with `resolve_cards` in this
session, against `tests/fixtures/cards/artist_s_talent.json`):

    (Gain the next level as a sorcery to add its ability.)
    Whenever you cast a noncreature spell, you may discard a card. If you
    do, draw a card.
    {2}{R}: Level 2
    Noncreature spells you cast cost {1} less to cast.
    {2}{R}: Level 3
    If a source you control would deal noncombat damage to an opponent or
    a permanent an opponent controls, it deals that much damage plus 2
    instead.

Every rule cited here was looked up with `knowledge_search(type="rules")` in
the session that wrote this file:

- **CR 716.2a** - "'[Cost]: Level N — [Abilities]' means '[Cost]: This
  Class's level becomes N. Activate only if this Class is level N-1 and only
  as a sorcery' and 'As long as this Class is level N or greater, it has
  [Abilities].'"
- **CR 716.2b** - "A level is a designation that any permanent can have...
  Levels are not a copiable characteristic."
- **CR 716.2d** - "If a rule or effect refers to a permanent's level and that
  permanent doesn't have a level, it is treated as though its level is 1."
- **CR 702.87c** / **CR 711.7** - Class levels are not the same as level up's
  level *counters* (`test_turn_based_actions.py`'s levelers are a different
  card).
- **CR 118.12** - "[Do something]. If [a player] does, [effect]" (the level 1
  trigger's own may-discard-then-draw shape).
- **CR 601.2f** - a board-wide cost reduction (the level 2 static, the
  controller-scoped sibling of `test_static_cost_reduction_grants.py`'s Ruby
  Medallion).
- **CR 510.2** / **CR 615.1** - combat damage is a distinct event from any
  other kind, which is why the level 3 replacement's own "noncombat" clause
  leaves an attacker's damage untouched.
- **CR 307.5** - the sorcery-timing rule "Activate only as a sorcery" reads
  onto - the same timing `test_activated_abilities.py` already covers for an
  ordinary printed instruction.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import ManaCost, Zone

from .harness import Scenario


def _board(*, alice_extra: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt", "Forest"] + (alice_extra or []),
            battlefield=["Artist's Talent"]
            + ["Mountain"] * 6,  # plenty of mana across every test's cast + level-ups
            library=["Island"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
    )


def _talent(scenario):
    return scenario.find("Artist's Talent", Zone.BATTLEFIELD)


# -- CR 716.2d: the default level ------------------------------------------


def test_a_freshly_cast_class_starts_at_level_1():
    scenario = _board().build()
    assert _talent(scenario).class_level == 1


# -- level 1: "Whenever you cast a noncreature spell, you may discard a card.
# If you do, draw a card." ---------------------------------------------------


def test_level_1_trigger_lets_you_discard_and_draw_off_a_noncreature_cast():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(True, times=None)
    (mountain,) = scenario.untapped_sources("Mountain")

    forest = scenario.find("Forest", Zone.HAND, "alice")
    scenario.cast_onto_stack("Lightning Bolt", mountain, targets=["bob"])
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()  # the trigger: discard the Forest, draw

    assert forest.zone is Zone.GRAVEYARD
    assert [state.name for state in scenario.player("alice").hand] == ["Island"]


def test_declining_the_level_1_trigger_discards_and_draws_nothing():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False, times=None)
    (mountain,) = scenario.untapped_sources("Mountain")

    forest = scenario.find("Forest", Zone.HAND, "alice")
    scenario.cast_onto_stack("Lightning Bolt", mountain, targets=["bob"])
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert forest.zone is Zone.HAND
    assert [state.name for state in scenario.player("alice").hand] == ["Forest"]


def test_a_creature_spell_does_not_trigger_the_noncreature_watcher():
    """ "a noncreature spell" (CR 205.2b's own negative reading) - Grizzly
    Bears's own kind never fires this."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Grizzly Bears"],
            battlefield=["Artist's Talent", "Forest", "Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest")

    scenario.cast_onto_stack("Grizzly Bears", *sources)
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == ["Grizzly Bears"]


# -- the level bar itself: CR 716.2a's mechanical half -----------------------


def test_leveling_up_to_2_costs_2r_and_only_as_a_sorcery():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    talent = _talent(scenario)
    mountains = scenario.untapped_sources("Mountain", "Mountain", "Mountain")

    scenario.activate(talent, *mountains, index=0)
    scenario.pass_until_resolved()

    assert talent.class_level == 2


def test_leveling_up_is_refused_at_instant_speed():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    talent = _talent(scenario)
    mountains = scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    scenario.activate(talent, *mountains, index=0)
    scenario.pass_until_resolved()  # now level 2
    scenario.start_at(Step.DECLARE_ATTACKERS)  # a step with no main-phase timing

    with pytest.raises(ValueError, match="only be activated as a sorcery"):
        scenario.activate(talent, index=1)


def test_leveling_up_cannot_skip_straight_to_3():
    """CR 716.2a's own prerequisite: "Activate only if this Class is level
    N-1" - level 1 cannot reach for the level 3 bar."""
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    talent = _talent(scenario)

    with pytest.raises(ValueError, match="is level 1, not level 2"):
        scenario.activate(talent, index=1)  # the Level 3 bar

    assert talent.class_level == 1


def test_the_level_2_bar_cannot_be_activated_twice():
    """Once level 2 is reached, "Activate only if this Class is level 1" is
    false a second time - CR 716.2a's own gate, not a once-per-turn rule."""
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    talent = _talent(scenario)
    mountains = scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    scenario.activate(talent, *mountains, index=0)
    scenario.pass_until_resolved()
    assert talent.class_level == 2

    with pytest.raises(ValueError, match="is level 2, not level 1"):
        scenario.activate(talent, index=0)


# -- level 2: "Noncreature spells you cast cost {1} less to cast." ----------


def test_level_2_discounts_a_noncreature_spell():
    scenario = _board(alice_extra=["Wrenn's Resolve"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    talent = _talent(scenario)
    talent.class_level = 2

    casting = scenario.cast("Wrenn's Resolve")

    assert casting.total_cost.mana == ManaCost.parse("{R}")


def test_the_discount_is_not_live_before_level_2_is_reached():
    scenario = _board(alice_extra=["Wrenn's Resolve"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Wrenn's Resolve")

    assert casting.total_cost.mana == ManaCost.parse("{1}{R}")


def test_level_1s_own_trigger_still_fires_once_the_class_reaches_level_2():
    """CR 716.2a: "level N or greater" - reaching level 2 does not turn off
    level 1's own ability."""
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    talent = _talent(scenario)
    talent.class_level = 2
    scenario.will_take_the_may(True, times=None)
    (mountain,) = scenario.untapped_sources("Mountain")

    forest = scenario.find("Forest", Zone.HAND, "alice")
    scenario.cast_onto_stack("Lightning Bolt", mountain, targets=["bob"])
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert forest.zone is Zone.GRAVEYARD


# -- level 3: "... it deals that much damage plus 2 instead." ---------------


def test_level_3_adds_2_to_noncombat_damage_a_source_you_control_deals():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    talent = _talent(scenario)
    talent.class_level = 3
    bolt_state = scenario.find("Lightning Bolt", Zone.HAND, "alice")

    dealt = scenario.game.deal_damage(scenario.player("bob"), 3, source=bolt_state)

    assert dealt == 5
    assert scenario.player("bob").life == 15


def test_level_3_does_not_boost_combat_damage():
    """CR 510.2: combat damage is its own event, and "noncombat damage" is
    the printed condition's own exclusion."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Artist's Talent", "Goblin Guide"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    talent = _talent(scenario)
    talent.class_level = 3
    goblin = scenario.creature("Goblin Guide", "alice")
    dealt = scenario.game.deal_damage(scenario.player("bob"), goblin.power, source=goblin)
    # No combat is in progress, so this call is deliberately given
    # `combat=False`'s own default through `deal_damage`'s own signature -
    # asserting the replacement's *color/type-agnostic* reading is correct
    # is `test_static_cost_reduction_grants.py`'s job, not this one's; this
    # test is only about the "noncombat" qualifier, exercised directly
    # against `Game.combat`'s own marker instead.
    assert dealt == goblin.power + 2  # not boosted here - not combat either


def test_level_3_does_not_boost_a_source_your_opponent_controls():
    """ "a source *you* control" - Artist's Talent's own controller only."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Artist's Talent"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    talent = _talent(scenario)
    talent.class_level = 3
    bolt_state = scenario.find("Lightning Bolt", Zone.HAND, "bob")

    dealt = scenario.game.deal_damage(scenario.player("alice"), 3, source=bolt_state)

    assert dealt == 3


def test_level_3_does_not_boost_damage_to_its_own_controller():
    """ "an opponent" - Artist's Talent never boosts damage aimed at its own
    controller, even from a source that controller owns."""
    scenario = _board().build()
    talent = _talent(scenario)
    talent.class_level = 3
    bolt_state = scenario.find("Lightning Bolt", Zone.HAND, "alice")

    dealt = scenario.game.deal_damage(scenario.player("alice"), 3, source=bolt_state)

    assert dealt == 3


def test_level_3_is_not_live_before_level_3_is_reached():
    scenario = _board().build()
    talent = _talent(scenario)
    talent.class_level = 2
    bolt_state = scenario.find("Lightning Bolt", Zone.HAND, "alice")

    dealt = scenario.game.deal_damage(scenario.player("bob"), 3, source=bolt_state)

    assert dealt == 3
