""" "When you next cast an instant or sorcery spell this turn, copy that
spell. You may choose new targets for the copy." - CR 603.7's delayed-trigger
shape (`machines.delayed.CopyNextSpellYouCast`), restricted to CR 300.1's
instant and sorcery card types by `DelayedTrigger.required_any_types` - the
positive twin of the existing `forbidden_types` filter.

Two parsers share this one shape: `_parse_copy_next_instant_or_sorcery_you_
cast_spell_clause` for a resolving *spell* (Doublecast, off-set - its entire
printed text is this one sentence) and `_parse_copy_next_instant_or_sorcery_
you_cast_clause` for a resolving *ability* (Way of the Cryomancer's own
granted `[-3]`: "Planeswalkers you control have '[-3]: When you next cast an
instant or sorcery spell this turn, copy that spell. You may choose new
targets for the copy.'" - staged the same way `test_empower_jace.py`'s own
Jace-token tests are, since Way of the Cryomancer's "empower Jace" ETB is
what actually puts a planeswalker with the granted ability onto the
battlefield).

CR numbers looked up with `knowledge_search(type="rules")` in this session:
CR 603.7, CR 603.7a, CR 603.7b, CR 707.10, CR 707.10c, CR 300.1.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _doublecast_board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Doublecast", "Lightning Bolt", "Lightning Bolt"],
            battlefield=["Mountain"] * 6,
        )
        .player("bob", life=20, battlefield=["Grizzly Bears"])
    )


def test_doublecast_copies_the_next_instant_and_the_copy_can_be_retargeted():
    """CR 707.10c: "you may choose new targets for the copy" actually runs
    (`Game.offer_new_targets_for_copy`) and actually changes what the copy
    hits - the copy is retargeted onto bob's Grizzly Bears while the real
    Bolt still hits bob himself, proving the retarget is not a no-op."""
    scenario = _doublecast_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bear = scenario.creature("Grizzly Bears", "bob")

    sources = scenario.untapped_sources("Mountain", "Mountain")
    scenario.cast_and_resolve("Doublecast", *sources)

    (mountain,) = scenario.untapped_sources("Mountain")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, targets=["bob"])
    assert scenario.stack_names() == [
        "Lightning Bolt",
        "Doublecast's triggered ability",
    ]

    scenario.will_take_the_may(True, source="Doublecast")
    scenario.will_choose_targets(bear, source="Doublecast")
    while scenario.game.stack:
        scenario.resolve_top()

    assert bolt.zone is Zone.GRAVEYARD
    assert bear.zone is Zone.GRAVEYARD, "the retargeted copy killed the bear, not bob"
    assert scenario.player("bob").life == 17, "only the real Bolt ever hit bob"


def test_a_creature_spell_cast_afterward_is_not_copied_but_a_later_instant_still_is():
    """`required_any_types=(Type.INSTANT, Type.SORCERY)` actually
    discriminates: a creature spell cast while the delayed trigger is
    waiting does not match `DelayedTrigger.matches` at all (no triggered
    ability appears, and the one-shot `remaining=1` is not spent), so the
    very next instant or sorcery still gets copied.

    Way of the Cryomancer's granted `[-3]` proves this from the *ability*
    side of the shared parser rather than Doublecast's spell side - staged
    the same way `test_empower_jace.py`'s Jace-token tests already are:
    "empower Jace 5" creates the token, and the static grant
    (`_GROUP_QUOTED_ABILITY_GRANT_RE`) gives it the `[-3]` ability to
    activate.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Way of the Cryomancer", "Grizzly Bears", "Lightning Bolt"],
            library=["Island"] * 3,
            battlefield=["Island", "Island", "Island", "Mountain", "Forest", "Forest"],
        )
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    sources = scenario.untapped_sources("Island", "Island", "Island")
    scenario.cast_and_resolve("Way of the Cryomancer", *sources)
    while scenario.game.stack:
        scenario.resolve_top()  # "When Way of the Cryomancer enters, empower Jace 5."

    jace = scenario.find("Jace", Zone.BATTLEFIELD, "alice")
    assert jace.loyalty == 5

    scenario.activate(jace, index=2)  # the granted "[-3]: When you next cast ..."
    while scenario.game.stack:
        scenario.resolve_top()
    assert jace.loyalty == 2

    forest, forest2 = scenario.untapped_sources("Forest", "Forest")
    scenario.cast_and_resolve("Grizzly Bears", forest, forest2)
    assert scenario.stack_names() == [], "a creature spell never matched the trigger"

    (mountain,) = scenario.untapped_sources("Mountain")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, targets=["bob"])
    assert scenario.stack_names() == [
        "Lightning Bolt",
        "Jace's triggered ability",
    ], "the very next instant still matches - the creature never consumed the trigger"

    scenario.will_take_the_may(False, source="Jace")  # keep the copy's targets as-is
    while scenario.game.stack:
        scenario.resolve_top()

    assert bolt.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 14, "the Bolt copied for 3+3 = 6"


def test_it_only_copies_the_first_instant_or_sorcery_cast_this_turn():
    """CR 603.7b: `remaining=1` is spent on the first match. A second
    instant that same turn is not copied a second time."""
    scenario = _doublecast_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    sources = scenario.untapped_sources("Mountain", "Mountain")
    scenario.cast_and_resolve("Doublecast", *sources)

    (m1,) = scenario.untapped_sources("Mountain")
    scenario.will_take_the_may(False, source="Doublecast")  # keep the copy's own targets
    scenario.cast_and_resolve("Lightning Bolt", m1, targets=["bob"])
    while scenario.game.stack:
        scenario.resolve_top()
    assert scenario.player("bob").life == 14, "the first Bolt copied for 3+3 = 6"

    (m2,) = scenario.untapped_sources("Mountain")
    scenario.cast_and_resolve("Lightning Bolt", m2, targets=["bob"])
    assert scenario.game.stack == [], "no trigger fires the second time to leave anything behind"

    assert scenario.player("bob").life == 11, "the second Bolt alone, no copy"


def test_the_delayed_trigger_expires_at_the_end_of_turn_if_unused():
    """CR 603.7's own "this turn" bound, ended by `Game.cleanup_step`
    (CR 514.2) through `DelayedTriggers.expire_this_turn` -
    `expires_end_of_turn=True` on the trigger Doublecast's own resolution
    created. Nothing is cast to consume it here; cleanup alone should clear
    it."""
    scenario = _doublecast_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    sources = scenario.untapped_sources("Mountain", "Mountain")
    scenario.cast_and_resolve("Doublecast", *sources)
    assert scenario.game.delayed_triggers.triggers != []

    scenario.start_at(Step.CLEANUP)
    scenario.turn_based_actions()

    assert scenario.game.delayed_triggers.triggers == []
