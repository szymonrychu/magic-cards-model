"""Judge scenarios: several token doublers applying to one creation event.

Sourced from the DDR judge transcripts. Episode covered:

- **DDR#1008** - Miirym, Sentinel Wyrm + Astral Dragon + Parallel Lives

The episode's headline is a combo whose token count has more digits than the
universe has atoms, and its actual *ruling* is that the number is nonetheless
determined: five Parallel Lives is a multiplication by thirty-two, not a game
state a judge would have to declare unresolvable.

What is testable here is the engine of that claim, at a size that fits in a
test: each Parallel Lives is its own replacement effect (CR 616.1), each applies
once to the same creation event (CR 614.5), and applying N of them multiplies
the count by 2^N. Parallel Lives' real oracle text, confirmed with
`resolve_cards`: "If an effect would create one or more tokens under your
control, it creates twice that many of those tokens instead."

Every CR number here was looked up with `knowledge_search(type="rules")` in the
session that wrote the file. The Miirym/Astral Dragon half of the combo is not
built: neither card has an entry in `machines/effects.py`, so their copy-token
triggers do nothing - see `COVERED-waveA.md`.
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def _cats(scenario) -> list:
    return [state for state in scenario.game.battlefield if state.name == "Cat Warrior Token"]


def _make_one_cat(*doublers: str):
    """Ajani, Nacatl Pariah's own enters trigger creates one Cat Warrior token.

    A triggered ability's resolution is an "effect" for CR 701.7b's purposes
    exactly as a spell's is, which is why a doubler sees it at all.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Ajani, Nacatl Pariah"],
            battlefield=["Plains", "Plains", *doublers],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Plains", "Plains", username="alice")
    scenario.cast_and_resolve("Ajani, Nacatl Pariah", *sources, username="alice")
    scenario.resolve_top()  # the enters trigger
    return scenario


def test_one_parallel_lives_doubles_the_creation():
    """CR 701.7b: "If a replacement effect applies to a token being created,
    that effect applies before considering any continuous effects that will
    modify the characteristics of that token."

    The base case the episode builds on: one token becomes two.
    """
    scenario = _make_one_cat("Parallel Lives")

    assert len(_cats(scenario)) == 2


def test_two_parallel_lives_multiply_rather_than_add():
    """CR 616.1 orders replacement effects that all apply to one event; CR 614.5
    gives each one exactly one opportunity to apply to it.

    So the second Parallel Lives applies to the *already replaced* event and
    doubles two into four. Four, not three: this is the multiplication the
    episode's 2^5 = 32 rests on, and the reason the combo's numbers explode.
    """
    scenario = _make_one_cat("Parallel Lives", "Parallel Lives")

    assert len(_cats(scenario)) == 4


def test_three_doublers_are_two_to_the_third():
    """The same rule once more, at the size where "each applies once" and "the
    last one wins" would give visibly different answers (8 against 2).
    """
    scenario = _make_one_cat("Parallel Lives", "Parallel Lives", "Parallel Lives")

    assert len(_cats(scenario)) == 8


def test_two_different_doublers_compound_the_same_way():
    """Doubling Season's first line and Parallel Lives are the same replacement
    shape on different cards, and CR 616.1 does not care that they share a name.

    The affected player - the one creating the tokens (CR 111.2) - chooses the
    order to apply them in, and here every order gives four.
    """
    scenario = _make_one_cat("Parallel Lives", "Doubling Season")

    assert len(_cats(scenario)) == 4


def test_without_a_doubler_the_stated_number_stands():
    """The control case. CR 701.7a: "To create one or more tokens ... put the
    specified number of tokens ... onto the battlefield" - one, because Ajani
    says one and nothing replaced the event.
    """
    scenario = _make_one_cat()

    assert len(_cats(scenario)) == 1
