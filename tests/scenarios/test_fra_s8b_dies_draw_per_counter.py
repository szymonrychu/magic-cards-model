"""FRA stream S8b: "When this creature dies, draw a card for each `<kind>`
counter on it." - the source-relative "for each counter" reader
(`_COUNTER_ON_IT_RE` in `machines/effects.py`), reached through `_DRAW_RE`'s
own existing "for each `<expr>`" tail (`_for_each_multiplier`).

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file.

- **CR 122.1** - a counter is placed on an object and modifies it until
  removed. **CR 122.2** - a counter is destroyed, not merely removed, the
  moment its object changes zones.
- **CR 603.10a** - a leaves-the-battlefield ability "looks back in time" -
  it sees the game state immediately *before* the event, so a dies
  trigger's "for each counter on it" reads the counters the permanent had
  the instant before it died, not the none a graveyard card has now.

Vexing Sphinx is the reported card ("When this creature dies, draw a card
for each age counter on it.") - the identical CR 603.10a/CR 122.2 read
Hangarback Walker's own registry-row `hangarback_dies` already gives
"create a token ... for each +1/+1 counter on this creature", now folded
into a real parser rather than a second hardcoded row (`docs/engine-
coverage.md`'s "keep one mechanism" - `EFFECTS`/`TRIGGER_EFFECTS`/
`ACTIVATED_EFFECTS` gains no new row here). Vogar, Necropolis Tyrant (real,
non-FRA, non-pool) is the off-set proof: "When Vogar dies, draw a card for
each +1/+1 counter on it." - a genuinely different counter kind (CR 122.1a's
special +1/+1 spelling rather than "age"'s plain open-set word), proving
`_counter_kind` is what the reader defers to rather than a bare string match
against "age".
"""

from magic_cards_model.machines import Step
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def test_vexing_sphinx_draws_a_card_for_each_age_counter_it_had():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Vexing Sphinx"], library=["Forest"] * 5)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    sphinx = scenario.creature("Vexing Sphinx", "alice")
    sphinx.add_counters("age", 3)
    cards_before = len(alice.hand)

    scenario.game.destroy(sphinx)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert len(alice.hand) == cards_before + 3
    assert sphinx.counters["age"] == 0, "CR 122.2 destroyed them on the zone change"


def test_vexing_sphinx_with_no_age_counters_draws_nothing():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Vexing Sphinx"], library=["Forest"] * 5)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    sphinx = scenario.creature("Vexing Sphinx", "alice")
    cards_before = len(alice.hand)

    scenario.game.destroy(sphinx)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert len(alice.hand) == cards_before


def test_vogar_draws_a_card_for_each_plus_one_counter_it_had():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Vogar, Necropolis Tyrant"], library=["Forest"] * 5)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    vogar = scenario.creature("Vogar, Necropolis Tyrant", "alice")
    vogar.add_counters(Counter.PLUS_ONE, 2)
    cards_before = len(alice.hand)

    scenario.game.destroy(vogar)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert len(alice.hand) == cards_before + 2
