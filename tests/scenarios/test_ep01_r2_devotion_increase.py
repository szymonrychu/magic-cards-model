"""Scenario: "Your devotion to each color and each combination of colors is
increased by one." (CR 700.5: devotion counts mana symbols among the mana costs
of permanents a player controls; the static ability adds one to every devotion
its controller has, CR 604.2.)
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def _board(alice_battlefield, hand=()):
    scenario = (
        Scenario()
        .player("alice", hand=list(hand), battlefield=list(alice_battlefield), library=["Swamp"] * 5)
        .player("bob", battlefield=[], library=["Swamp"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_gray_merchant(scenario):
    sources = scenario.untapped_sources(*["Swamp"] * 5)
    scenario.cast_and_resolve("Gray Merchant of Asphodel", *sources)
    while scenario.game.stack:
        scenario.resolve_top()


def test_a_drain_counts_the_extra_devotion():
    scenario = _board(["Altar of the Pantheon", *["Swamp"] * 5], hand=["Gray Merchant of Asphodel"])
    _cast_gray_merchant(scenario)
    assert scenario.player("bob").life == 20 - 3


def test_without_the_artifact_the_drain_counts_only_the_symbols():
    scenario = _board([*["Swamp"] * 5], hand=["Gray Merchant of Asphodel"])
    _cast_gray_merchant(scenario)
    assert scenario.player("bob").life == 20 - 2


def test_two_of_them_add_two():
    scenario = _board(
        ["Altar of the Pantheon", "Altar of the Pantheon", *["Swamp"] * 5],
        hand=["Gray Merchant of Asphodel"],
    )
    _cast_gray_merchant(scenario)
    assert scenario.player("bob").life == 20 - 4


def test_the_opponents_devotion_is_not_increased():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Altar of the Pantheon"], library=["Swamp"] * 5)
        .player(
            "bob",
            hand=["Gray Merchant of Asphodel"],
            battlefield=["Swamp"] * 5,
            library=["Swamp"] * 5,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    # Bob is not the active player, so score his devotion directly.
    from magic_cards_model.machines.effects.amounts import devotion_to
    from magic_cards_model.models.card import Color

    assert devotion_to(scenario.game, "bob", Color.BLACK) == 0
    assert devotion_to(scenario.game, "alice", Color.BLACK) == 1


def test_a_layer_count_reads_it_too():
    scenario = _board(["Altar of the Pantheon", "Anax, Hardened in the Forge"])
    anax = scenario.creature("Anax, Hardened in the Forge", "alice")
    board = scenario.game.computed_board().of(anax)
    assert board.power == 2 + 1  # Anax's own {1}{R} costs one red symbol, plus the Altar's one
