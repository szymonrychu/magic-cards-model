"""Scenario: a counter-doubling (or otherwise amount-modifying) replacement
effect applies to counters put on a *player*, not only counters put on a
permanent.

CR 122.6 (already cited by `Game.add_counters`'s own docstring): "Some spells
and abilities refer to counters being put on an object. This refers to
putting counters on that object while it's on the battlefield." The player
half of the same idea has no object at all - CR 121.6-style replaceable
events exist for a player gaining life or drawing a card, but until this
change `Player.add_counters` was called directly with no `ReplaceableEvent`
in between, so a replacement effect written "If you would get one or more
counters, ..." (CR 614.1a) had no event to apply to and silently never fired.

Oracle text pulled with `scripts/add_card.py` and verified against
`src/magic_cards_model/data/printings/`:

- **Winding Constrictor** (the follow-up's own named card): "If one or more
  counters would be put on an artifact or creature you control, that many
  plus one of each of those kinds of counters are put on that permanent
  instead.\\nIf you would get one or more counters, you get that many plus
  one of each of those kinds of counters instead." The second line is the
  one this change makes compile and apply; any counter kind, "plus one".
- **Aether Chaser**: "When this creature enters, you get {E}{E} (two energy
  counters)." - the ordinary player-counter-granting trigger both tests
  below use as their source event.
- **Aether Refinery** (off-pool, proves the parser generalises rather than
  reading Winding Constrictor's exact sentence): "If you would get one or
  more {E} (energy counters), you get twice that many {E} instead." A
  *kind-specific* replacement ({E} only, not "one or more counters" of any
  kind) with a "twice" multiplier rather than Winding Constrictor's "plus
  one" addend.

CR 614.1a: "Some replacement effects use the word 'instead' ... Others state
that an event doesn't happen at all." CR 122.1: "A counter is a marker...
Some kinds of counters are normally placed on players rather than on
objects" is the general backing for a counter existing on a player at all.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models.card_state import Counter

from .harness import Scenario


def test_winding_constrictor_adds_one_to_energy_a_player_gets():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Aether Chaser"],
            battlefield=["Winding Constrictor"] + ["Mountain"] * 2,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Mountain", "Mountain")

    scenario.cast_and_resolve("Aether Chaser", *sources)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    # Printed: two energy counters. Winding Constrictor: "that many plus one".
    assert scenario.player("alice").counters[Counter.ENERGY] == 3


def test_off_pool_aether_refinery_doubles_energy_a_player_gets():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Aether Chaser"],
            battlefield=["Aether Refinery"] + ["Mountain"] * 8,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Mountain", "Mountain")

    scenario.cast_and_resolve("Aether Chaser", *sources)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    # Printed: two energy counters. Aether Refinery: "twice that many".
    assert scenario.player("alice").counters[Counter.ENERGY] == 4
