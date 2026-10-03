"""An "If <condition>, A and B." sentence gates both A and B (CR 608.2c).

Daredevil Dragster: "At end of combat, if this Vehicle attacked or blocked
this combat, put a velocity counter on it. Then if it has two or more
velocity counters on it, sacrifice it and draw two cards." The sacrifice and
the draw are one conditional instruction: with one counter the Vehicle stays
and nothing is drawn; with two it is sacrificed and two cards are drawn.

Rules verified with `mise run rules:find`:

- **CR 608.2c** - the controller follows the instructions in the order
  written; later text may modify earlier text, and the whole text is read
  with the rules of English.
- **CR 702.122a** - Crew N: tap untapped creatures with total power N or
  more; the Vehicle becomes an artifact creature until end of turn.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.effects import parse_mixed_effect, split_effect_clauses
from magic_cards_model.machines.keywords import crew_activation
from magic_cards_model.models import Zone
from tests.scenarios.harness import PlayedScenario, Scenario

_DRAGSTER = "Daredevil Dragster"


def _attack_once(scenario: PlayedScenario, dragster, crew) -> None:
    activation = crew_activation(scenario.game, dragster, [crew], "alice")
    activation.begin_paying()
    activation.payment.pay()
    activation.activate()
    activation.resolve()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(dragster)
    scenario.no_blocks()
    while scenario.step is not Step.END_OF_COMBAT:
        scenario.advance()
        scenario.game.put_triggers_on_stack()
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()
            scenario.game.put_triggers_on_stack()


def _board() -> PlayedScenario:
    scenario = (
        Scenario()
        .player("alice", battlefield=[_DRAGSTER, "Serra Angel"], library=["Island"] * 10)
        .player("bob", library=["Island"] * 10)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_the_first_counter_neither_sacrifices_nor_draws():
    scenario = _board()
    dragster = scenario.creature(_DRAGSTER, "alice")
    hand_before = len(scenario.game.player("alice").hand)

    _attack_once(scenario, dragster, scenario.creature("Serra Angel", "alice"))

    assert dragster.counter_count("velocity") == 1
    assert dragster.zone is Zone.BATTLEFIELD
    assert len(scenario.game.player("alice").hand) == hand_before


def test_the_second_counter_sacrifices_and_draws_two():
    scenario = _board()
    dragster = scenario.creature(_DRAGSTER, "alice")
    scenario.game.add_counters(dragster, "velocity", 1)
    hand_before = len(scenario.game.player("alice").hand)

    _attack_once(scenario, dragster, scenario.creature("Serra Angel", "alice"))

    assert dragster.zone is Zone.GRAVEYARD
    assert len(scenario.game.player("alice").hand) == hand_before + 2


def test_an_if_sentence_keeps_its_whole_consequence_in_one_clause():
    """The splitter never cuts an "If <condition>, A and B" consequence at its
    "and": the conditional clause reader gets the whole of it."""
    text = (
        "put a velocity counter on it. Then if it has two or more velocity "
        "counters on it, sacrifice it and draw two cards."
    )
    assert split_effect_clauses(text) == [
        "put a velocity counter on it",
        "if it has two or more velocity counters on it, sacrifice it and draw two cards",
    ]
    assert parse_mixed_effect(text) is not None
