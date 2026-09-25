"""Increment: a creature that grows when you spend more mana on a spell than
it is big (CR 702.191).

Rules verified with `mise run rules:find` in the session that wrote this file:

- **CR 702.191a** - "Increment is a triggered ability. 'Increment' means
  'Whenever you cast a spell, if this permanent is a creature and the amount
  of mana spent to cast that spell is greater than this creature's power or
  this creature's toughness, put a +1/+1 counter on this creature.'"
- **CR 702.191b** - multiple instances trigger separately.
- **CR 603.4** / **CR 608.2a** - an intervening "if": checked as the spell is
  cast, and again as the trigger resolves.
- **CR 601.2h** - the mana spent is what was paid for the total cost.

Fractal Tender brought the keyword into the pool (its own end step trigger is
EC4 cluster H5); Hungry Graffalon (3/4) is a second printing in no deck, with a
power and a toughness that differ, which is what tells "power or toughness"
apart from either alone.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

_LANDS = ["Mountain"] * 5 + ["Plains"] * 5 + ["Island"] * 3


def _board(creature: str, hand: list[str]):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=[creature, *_LANDS], hand=hand, library=["Plains"] * 6)
        .player("bob", library=["Plains"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast(scenario, name: str, *lands: str) -> None:
    scenario.cast_onto_stack(name, *scenario.untapped_sources(*lands))
    scenario.game.put_triggers_on_stack()


def _triggered(scenario, name: str) -> bool:
    return f"{name}'s triggered ability" in scenario.stack_names()


def test_five_mana_is_more_than_a_three_three():
    """Fractal Tender (3/3), Serra Angel for five: the trigger resolves and
    the Tender gets a +1/+1 counter."""
    scenario = _board("Fractal Tender", ["Serra Angel"])
    _cast(scenario, "Serra Angel", "Plains", "Plains", "Mountain", "Mountain", "Mountain")
    assert _triggered(scenario, "Fractal Tender")
    scenario.pass_until_resolved()
    assert scenario.creature("Fractal Tender", "alice").counter_count("+1/+1") == 1


def test_three_mana_is_not_more_than_a_three_three():
    """False when the spell is cast: CR 603.4 - it never triggers."""
    scenario = _board("Fractal Tender", ["Divination"])
    _cast(scenario, "Divination", "Island", "Mountain", "Mountain")
    assert not _triggered(scenario, "Fractal Tender")
    assert scenario.game.intervening_if_notices == []


def test_more_than_the_power_alone_is_enough():
    """Hungry Graffalon (3/4), a four-mana spell: 4 is greater than its power
    3, not its toughness 4 - "or" needs only one."""
    scenario = _board("Hungry Graffalon", ["Gorehorn Minotaurs"])
    _cast(scenario, "Gorehorn Minotaurs", "Mountain", "Mountain", "Plains", "Plains")
    assert _triggered(scenario, "Hungry Graffalon")


def test_not_more_than_either_never_triggers():
    scenario = _board("Hungry Graffalon", ["Divination"])
    _cast(scenario, "Divination", "Island", "Plains", "Plains")
    assert not _triggered(scenario, "Hungry Graffalon")
    assert scenario.game.intervening_if_notices == []


def test_growing_in_response_removes_it_on_resolution():
    """True as it triggers (4 > power 3), false by resolution once the
    Graffalon is 4/5: CR 608.2a removes it and it does nothing."""
    scenario = _board("Hungry Graffalon", ["Gorehorn Minotaurs"])
    _cast(scenario, "Gorehorn Minotaurs", "Mountain", "Mountain", "Plains", "Plains")
    assert _triggered(scenario, "Hungry Graffalon")
    graffalon = scenario.creature("Hungry Graffalon", "alice")
    scenario.game.add_counters(graffalon, "+1/+1", 1)

    scenario.pass_until_resolved()

    assert scenario.creature("Hungry Graffalon", "alice").counter_count("+1/+1") == 1
    assert scenario.find("Gorehorn Minotaurs", Zone.STACK) is not None


def test_an_opponents_spell_is_not_yours():
    """ "Whenever you cast a spell": the opponent's spell does not trigger it."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("bob", battlefield=_LANDS, hand=["Serra Angel"], library=["Plains"] * 6)
        .player("alice", battlefield=["Fractal Tender"], library=["Plains"] * 6)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_onto_stack(
        "Serra Angel",
        *scenario.untapped_sources(
            "Plains", "Plains", "Mountain", "Mountain", "Mountain", username="bob"
        ),
        username="bob",
    )
    scenario.game.put_triggers_on_stack()
    assert not _triggered(scenario, "Fractal Tender")
