"""A permanent's printed power and toughness, beside the computed ones.

`CardState.power`/`toughness` answer with the computed board once the card is
bound to its game (CR 613.5). A client that shows both - "3/3, printed 2/2" -
needs the printed values through a public name, counters included (CR 122.1a)
and no continuous effect applied.

Every CR number here was read whole with `mise run rules:find` in the session
that wrote this file.
"""

from magic_cards_model.machines import Step

from .harness import Scenario


def test_printed_power_and_toughness_ignore_an_anthem():
    scenario = (
        Scenario()
        .player("alice", library=["Forest"], battlefield=["Glorious Anthem", "Grizzly Bears"])
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    assert (bears.power, bears.toughness) == (3, 3)
    assert (bears.printed_power, bears.printed_toughness) == (2, 2)
