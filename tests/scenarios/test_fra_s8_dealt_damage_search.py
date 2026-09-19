"""FRA stream S8: the passive "Whenever this creature is dealt damage, ..."
trigger (CR 120, CR 603.2), and Hexhaven Invigorator's own "search your
library for up to that many land cards" reading of it.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file.

- **CR 120.1** - "An object that deals damage is the source of that damage" -
  the *passive* voice asks about the other end of the same event, the
  recipient, read off `GameEvent.target_id`/`target_controller`/
  `target_types` (a permanent recipient) or `GameEvent.player` (a player
  one) - FRA S5's own fields, reconciled onto at the int-engine-dsl merge in
  place of this stream's own narrower, permanent-only `recipient_id`.
- **CR 120.3e** - damage marked on a creature.
- **CR 607.1** - "that many" is anaphora onto the event that triggered the
  ability - the amount of damage just dealt - read the same way Marauding
  Mako's own "that many" +1/+1 counters already are.
- **CR 701.23a/701.24a** - the search and its shuffle.

Hexhaven Invigorator is the reported card, its own "that many" reading the
proof this stream's own new clause needs. Ranging Raptors (Lost Caverns of
Ixalan, real, non-FRA, non-pool) is the off-set proof for the *trigger event*
itself: an identical passive "is dealt damage" condition, but with a fixed
"a basic land card" search instead of Hexhaven Invigorator's own "that
many" - read entirely by the *existing* `_SEARCH_AND_PUT_RE` parser once the
passive trigger event is recognised at all, independent of the new "that
many" reader this file's other test exercises.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_hexhaven_invigorator_searches_that_many_lands_onto_the_battlefield():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Hexhaven Invigorator"],
            library=["Forest", "Forest", "Forest", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    invigorator = scenario.creature("Hexhaven Invigorator", "alice")
    lands_before = len([state for state in alice.library if state.name in {"Forest", "Mountain"}])

    scenario.game.deal_damage(invigorator, 3)
    scenario.game.put_triggers_on_stack()
    scenario.will_take_the_may(True, source="Hexhaven Invigorator")
    scenario.will_choose_cards(
        *[state for state in alice.library if state.name == "Forest"][:3], username="alice"
    )
    scenario.pass_until_resolved()

    battlefield_lands = [
        state
        for state in scenario.game.battlefield
        if state.controller == "alice" and state.name == "Forest"
    ]
    assert len(battlefield_lands) == 3
    assert all(state.tapped for state in battlefield_lands)
    assert (
        len([state for state in alice.library if state.name in {"Forest", "Mountain"}])
        == lands_before - 3
    )


def test_ranging_raptors_off_set_reads_the_same_passive_trigger_for_a_fixed_count():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Ranging Raptors"],
            library=["Forest", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    raptors = scenario.creature("Ranging Raptors", "alice")
    forest = next(state for state in alice.library if state.name == "Forest")

    scenario.game.deal_damage(raptors, 2)
    scenario.game.put_triggers_on_stack()
    scenario.will_take_the_may(True, source="Ranging Raptors")
    scenario.will_choose_cards(forest, username="alice")
    scenario.pass_until_resolved()

    assert forest.zone is Zone.BATTLEFIELD
    assert forest.tapped
