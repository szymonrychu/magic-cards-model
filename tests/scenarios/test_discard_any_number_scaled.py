"""A keyword action scaled by a count: "investigate twice for each card
discarded this way" after "Discard any number of cards", and "investigate for
each opponent who lost life this turn".

Every CR number below was read whole with `mise run rules:find` in the session
that wrote this file:

- **CR 701.16a** - "Investigate" means "Create a Clue token."
- **CR 107.1c** - "any number" is any positive number or zero, so discarding
  nothing is a legal answer and investigates zero times.
- **CR 701.9b** - the discarding player chooses which cards.
- **CR 608.2c** - "this way" reads the discard the same ability just made.
- **CR 608.2h** - a count the effect needs is taken once, as it applies.
- **CR 714.2b** - a chapter ability triggers when the lore counter that
  reaches its number is put on.

Tamiyo Meets the Story Circle's chapter II is the reported card. Teysa,
Opulent Oligarch ("At the beginning of your end step, investigate for each
opponent who lost life this turn.") is the proof printing: Standard-legal, in
no api deck, the same "investigate ... for each `<count>`" tail over a
different count and with no multiplier word.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def clues(scenario, username: str = "alice") -> int:
    return sum(
        1
        for state in scenario.game.permanents_controlled_by(username)
        if state.name == "Clue Token"
    )


def resolve_all(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()


def chapter_two(hand: list[str]):
    scenario = (
        Scenario()
        .player("alice", hand=hand, battlefield=["Tamiyo Meets the Story Circle"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    resolve_all(scenario)  # chapter I, from the lore counter it was staged with
    return scenario


def reach_chapter_two(scenario) -> None:
    scenario.game.saga_lore_step()
    resolve_all(scenario)


def test_discarding_two_cards_investigates_four_times():
    scenario = chapter_two(["Lightning Bolt", "Shock", "Island"])
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    shock = scenario.find("Shock", Zone.HAND, "alice")
    scenario.will_discard(bolt, shock)

    reach_chapter_two(scenario)

    assert bolt.zone is Zone.GRAVEYARD
    assert shock.zone is Zone.GRAVEYARD
    assert [state.name for state in scenario.player("alice").hand] == ["Island"]
    assert clues(scenario) == 4


def test_discarding_nothing_is_legal_and_investigates_nothing():
    """CR 107.1c: zero is "any number"."""
    scenario = chapter_two(["Lightning Bolt"])
    scenario.will_discard()

    reach_chapter_two(scenario)

    assert [state.name for state in scenario.player("alice").hand] == ["Lightning Bolt"]
    assert clues(scenario) == 0


def test_an_empty_hand_investigates_nothing():
    scenario = chapter_two([])

    reach_chapter_two(scenario)

    assert clues(scenario) == 0


def test_discarding_the_whole_hand_investigates_twice_each():
    scenario = chapter_two(["Lightning Bolt", "Shock", "Island"])
    hand = list(scenario.player("alice").hand)
    scenario.will_discard(*hand)

    reach_chapter_two(scenario)

    assert scenario.player("alice").hand == []
    assert clues(scenario) == 6


def test_the_discard_is_the_controllers_choice_of_which_cards():
    scenario = chapter_two(["Lightning Bolt", "Shock", "Island"])
    island = scenario.find("Island", Zone.HAND, "alice")
    scenario.will_discard(island)

    reach_chapter_two(scenario)

    assert island.zone is Zone.GRAVEYARD
    assert sorted(s.name for s in scenario.player("alice").hand) == ["Lightning Bolt", "Shock"]
    assert clues(scenario) == 2


# -- proof printing: Teysa, Opulent Oligarch ----------------------------------


def teysa_board(opponents: int = 1):
    builder = Scenario().player("alice", battlefield=["Teysa, Opulent Oligarch"])
    for name in ["bob", "carol"][:opponents]:
        builder = builder.player(name)
    scenario = builder.build()
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    return scenario


def to_end_step(scenario) -> None:
    scenario.advance()
    assert scenario.step is Step.END_STEP
    resolve_all(scenario)


def test_teysa_investigates_once_per_opponent_who_lost_life():
    scenario = teysa_board(opponents=2)
    scenario.player("bob").lose_life(1)
    scenario.player("carol").lose_life(2)

    to_end_step(scenario)

    assert clues(scenario) == 2


def test_teysa_skips_an_opponent_who_lost_no_life():
    scenario = teysa_board(opponents=2)
    scenario.player("bob").lose_life(3)

    to_end_step(scenario)

    assert clues(scenario) == 1


def test_teysa_investigates_nothing_when_no_opponent_lost_life():
    scenario = teysa_board()

    to_end_step(scenario)

    assert clues(scenario) == 0


def test_teysa_does_not_count_her_controllers_own_life_loss():
    scenario = teysa_board()
    scenario.player("alice").lose_life(4)

    to_end_step(scenario)

    assert clues(scenario) == 0
