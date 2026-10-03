"""Festering March: "Creatures your opponents control get -1/-1 until end of
turn. Exile Festering March with three time counters on it. Suspend
3-{2}{B}" - the mass shrink, then the spell exiles itself carrying three time
counters and, having suspend, is suspended (CR 702.62b) and recurs.

- **CR 608.2n** the spell is put into the graveyard only if still on the stack
  as its last step; its own exile instruction runs first.
- **CR 702.62b** in exile, has suspend, has a time counter: suspended.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario

LIBRARY = ["Island"] * 12
MARCH = "Festering March"


def _board():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=[MARCH], battlefield=["Swamp"] * 5 + ["Grizzly Bears"], library=LIBRARY)
        .player("bob", battlefield=["Grizzly Bears", "Hill Giant"], library=LIBRARY)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_shrinks_only_the_opponents_creatures_then_exiles_itself_suspended():
    scenario = _board()
    march = scenario.cast_and_resolve(MARCH, *scenario.untapped_sources(*["Swamp"] * 5))
    bob_bears = scenario.creature("Grizzly Bears", "bob")
    alice_bears = scenario.creature("Grizzly Bears", "alice")
    chars = scenario.game.characteristics_of(bob_bears)
    assert (chars.power, chars.toughness) == (1, 1)
    chars = scenario.game.characteristics_of(alice_bears)
    assert (chars.power, chars.toughness) == (2, 2)
    assert march.zone is Zone.EXILE
    assert march.counter_count(Counter.TIME) == 3
    assert march.is_suspended


def test_a_countered_march_goes_to_the_graveyard_without_counters():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=[MARCH], battlefield=["Swamp"] * 5, library=LIBRARY)
        .player("bob", hand=["Counterspell"], battlefield=["Island", "Island"], library=LIBRARY)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    march = scenario.cast_onto_stack(MARCH, *scenario.untapped_sources(*["Swamp"] * 5))
    scenario.pass_priority("alice")
    scenario.cast_and_resolve("Counterspell", username="bob", auto=True, targets=[march])
    assert march.zone is Zone.GRAVEYARD
    assert march.counter_count(Counter.TIME) == 0


def test_the_support_oracle_scores_it_as_read():
    from magic_cards_model.support import HANDLED, card_support
    from tests.cards import card

    assert card_support(card(MARCH)).status == HANDLED
