"""Scenario: Adapt (CR 701.46), Basking Broodscale's "{1}{G}: Adapt 1."

CR 701.46a: "'Adapt N' means 'If this permanent has no +1/+1 counters on it,
put N +1/+1 counters on it.'" Adapt is a keyword *action* (CR 701), not a
keyword ability - the printed line is just "Adapt N.", so
`machines/effects.py`'s `_parse_adapt_clause` reads the reminder text's own
conditional sentence off the ability's effect, with no per-card row.

CR number verified with `knowledge_search(q="Adapt N keyword action",
type="rules")` in the session that wrote this file.

Basking Broodscale (MH3) also carries a third paragraph - "Whenever one or
more +1/+1 counters are put on this creature, you may create a ... Eldrazi
Spawn" - which `docs/engine-coverage.md` already records as unbuilt (the
counter-placed trigger condition is not one `machines/triggers.py` reads).
That paragraph is untouched here; this file is about the activated ability
alone (CR 113.3, paragraph-atomic).
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter

from .harness import Scenario


def _scenario() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Basking Broodscale"],
            battlefield=["Forest", "Forest", "Forest", "Forest"],
        )
        .player("bob")
    )


def test_adapt_puts_counters_on_a_creature_with_none():
    scenario = _scenario().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest")
    broodscale = scenario.cast_and_resolve("Basking Broodscale", *sources)

    remaining = scenario.untapped_sources("Forest", "Forest")
    scenario.activate(broodscale, *remaining)
    scenario.resolve_top()

    assert broodscale.counters[Counter.PLUS_ONE] == 1
    assert broodscale.power == 3
    assert broodscale.toughness == 3


def test_adapt_does_nothing_to_a_creature_that_already_has_a_plus_one_counter():
    """CR 701.46a's own condition: adapting again once a +1/+1 counter is
    already there is a real activation (it still costs mana) that changes
    nothing on the board - not a partial top-up to N."""
    scenario = _scenario().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest")
    broodscale = scenario.cast_and_resolve("Basking Broodscale", *sources)
    broodscale.add_counters(Counter.PLUS_ONE, 3)

    remaining = scenario.untapped_sources("Forest", "Forest")
    scenario.activate(broodscale, *remaining)
    scenario.resolve_top()

    assert broodscale.counters[Counter.PLUS_ONE] == 3


def test_adapt_is_untouched_by_a_minus_one_counter():
    """A -1/-1 counter is not a +1/+1 counter (CR 122.3's annihilation only
    ever removes matched pairs), so a creature carrying only -1/-1 counters
    still has "no +1/+1 counters on it" and adapts normally."""
    scenario = _scenario().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest")
    broodscale = scenario.cast_and_resolve("Basking Broodscale", *sources)
    broodscale.add_counters(Counter.MINUS_ONE, 1)

    remaining = scenario.untapped_sources("Forest", "Forest")
    scenario.activate(broodscale, *remaining)
    scenario.resolve_top()

    assert broodscale.counters[Counter.PLUS_ONE] == 1
    assert broodscale.counters[Counter.MINUS_ONE] == 1


def test_adapt_does_nothing_once_the_creature_has_left_the_battlefield():
    """CR 113.7a: the ability resolves even if its source is gone, but there
    is nothing left to put a counter on."""
    scenario = _scenario().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest")
    broodscale = scenario.cast_and_resolve("Basking Broodscale", *sources)

    remaining = scenario.untapped_sources("Forest", "Forest")
    ability = scenario.activate(broodscale, *remaining)
    assert ability is not None

    scenario.game.sacrifice(broodscale)
    assert broodscale.zone is Zone.GRAVEYARD

    scenario.resolve_top()

    assert broodscale.counters[Counter.PLUS_ONE] == 0
