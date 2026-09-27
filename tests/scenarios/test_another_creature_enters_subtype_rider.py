"""Scenario: "Whenever another creature you control enters, `<effect>`. If
it's a `<subtype>`, `<rider>`." - Aunt May's own ETB trigger, whose rider's
"it" is the trigger event's own subject (CR 603.2), not an object some
earlier instruction of the *same* effect chose.

`machines/effects._effect_condition_is_readable` used to refuse **every**
anaphoric "if" clause outright (`machines/conditions/objects.
names_an_anaphor`), spell and triggered ability alike, because a spell's own
resolving effect has no trigger event to read "it" off - the anaphor there
names whatever an earlier instruction of that same effect chose (a target, a
revealed card), which `Game.condition_holds` cannot know. A *triggered*
ability's own trigger event is a different, already-known object
(`AbilityOnStack.event`), and `Game.condition_holds` already carries
`ability`/`event`/`source_stamp` parameters built for exactly this (Molten-
Core Maestro's own cast-trigger rider) - they were simply never threaded
through from this one caller.

Oracle text, pulled with `scripts/add_card.py` and verified against the
printings pool (every card Modern-legal):

- **Aunt May**: "Whenever another creature you control enters, you gain 1
  life. If it's a Spider, put a +1/+1 counter on it."

No second, off-pool printing was found for this exact rider shape (a
trigger's-own-subject anaphor read inside a resolution-time "if") in a
Modern/Pioneer/Standard-legal card - recorded in `MEMORY.md` rather than
asserted. The widening itself is untouched by card name: it is `Game.
condition_holds`'s own `ability`/`event` parameters, already built for a
*different* card's cast-trigger rider, now also reached from this caller.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models.card_state import Counter

from .harness import Scenario

AUNT_MAY = "Aunt May"


def _board() -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Giant Spider", "Grizzly Bears"],
            battlefield=[AUNT_MAY, "Forest", "Forest", "Forest", "Forest"],
        )
        .player("bob", battlefield=[])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_a_spider_entering_gains_life_and_a_counter():
    scenario = _board()
    life_before = scenario.player("alice").life
    (f1, f2, f3, f4) = scenario.untapped_sources("Forest", "Forest", "Forest", "Forest")

    spider = scenario.cast_and_resolve("Giant Spider", f1, f2, f3, f4)
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == [f"{AUNT_MAY}'s triggered ability"]
    scenario.resolve_top()

    assert scenario.player("alice").life == life_before + 1
    assert spider.counter_count(Counter.PLUS_ONE) == 1


def test_a_non_spider_entering_gains_life_only():
    scenario = _board()
    life_before = scenario.player("alice").life
    (f1, f2) = scenario.untapped_sources("Forest", "Forest")

    bears = scenario.cast_and_resolve("Grizzly Bears", f1, f2)
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == [f"{AUNT_MAY}'s triggered ability"]
    scenario.resolve_top()

    assert scenario.player("alice").life == life_before + 1
    assert bears.counter_count(Counter.PLUS_ONE) == 0


def test_aunt_may_herself_entering_does_not_trigger_her_own_ability():
    """ "Another" creature (CR 700.7): Aunt May's own entrance is not it."""
    scenario = (
        Scenario()
        .player("alice", hand=[AUNT_MAY], battlefield=["Plains"])
        .player("bob", battlefield=[])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (plains,) = scenario.untapped_sources("Plains")
    scenario.cast_and_resolve(AUNT_MAY, plains)
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []
