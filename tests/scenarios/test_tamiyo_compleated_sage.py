"""Scenario: Tamiyo, Compleated Sage's "+1: Tap up to one target artifact or
creature. It doesn't untap during its controller's next untap step."

Two sentences, one ability (CR 113.3, paragraph-atomic): the second's "it" is
CR 400.7's anaphora back to whatever the first sentence targeted, so
`machines/effects.py`'s `_parse_tap_target_then_no_untap_clause` reads the
whole loyalty ability at once rather than through the per-clause dispatcher.
CR 701.43a's exert wording - "you choose to have it not untap during your
controller's next untap step" - is functionally identical to this sentence
even though nothing here is exerted as a cost, so the resolving effect
reuses `CardState.exerted`/`CardState.untap` directly rather than building a
second not-untap mechanism.

Every rule cited here was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 606.3** - "A player may activate a loyalty ability of a permanent
  they control any time they have priority and the stack is empty during a
  main phase of their turn, but only if no player has previously activated a
  loyalty ability of that permanent that turn."
- **CR 606.4** - the loyalty cost itself: `[+1]` puts one loyalty counter on.
- **CR 701.43a** - exert's own "does not untap during its controller's next
  untap step" wording, reused here for the mechanism.
- **CR 115.6** - "up to one" target, optional.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def _scenario() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Tamiyo, Compleated Sage"],
            battlefield=["Forest", "Forest", "Island", "Island", "Island", "Goblin Guide"],
        )
        .player("bob")
    )


def test_plus_one_taps_the_target_and_it_stays_tapped_through_the_next_untap():
    scenario = _scenario().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest", "Island", "Island", "Island")
    tamiyo = scenario.cast_and_resolve("Tamiyo, Compleated Sage", *sources)

    goblin = scenario.find("Goblin Guide", Zone.BATTLEFIELD, "alice")
    assert not goblin.tapped

    scenario.activate(tamiyo, targets=[goblin])
    scenario.resolve_top()

    assert goblin.tapped
    assert goblin.exerted
    assert tamiyo.counters["loyalty"] == 6

    scenario.game.untap_step()

    assert goblin.tapped
    assert not goblin.exerted

    scenario.game.untap_step()

    assert not goblin.tapped


def test_up_to_one_target_may_tap_nothing_at_all():
    scenario = _scenario().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest", "Island", "Island", "Island")
    tamiyo = scenario.cast_and_resolve("Tamiyo, Compleated Sage", *sources)

    goblin = scenario.find("Goblin Guide", Zone.BATTLEFIELD, "alice")

    scenario.activate(tamiyo, targets=[])
    scenario.resolve_top()

    assert not goblin.tapped
    assert tamiyo.counters["loyalty"] == 6


def test_only_one_loyalty_ability_per_turn():
    scenario = _scenario().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest", "Island", "Island", "Island")
    tamiyo = scenario.cast_and_resolve("Tamiyo, Compleated Sage", *sources)

    goblin = scenario.find("Goblin Guide", Zone.BATTLEFIELD, "alice")
    scenario.activate(tamiyo, targets=[goblin])
    scenario.resolve_top()

    reason = scenario.why_cannot_activate(tamiyo)
    assert reason is not None
    assert "already been activated" in reason


def test_tamiyo_can_tap_a_noncreature_artifact_too():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Tamiyo, Compleated Sage"],
            battlefield=["Forest", "Forest", "Island", "Island", "Island"],
        )
        .player("bob", battlefield=["The Filigree Sylex"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest", "Island", "Island", "Island")
    tamiyo = scenario.cast_and_resolve("Tamiyo, Compleated Sage", *sources)

    sylex = scenario.find("The Filigree Sylex", Zone.BATTLEFIELD, "bob")
    scenario.activate(tamiyo, targets=[sylex])
    scenario.resolve_top()

    assert sylex.tapped
    assert sylex.exerted
