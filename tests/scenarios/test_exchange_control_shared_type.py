"""Exchanging control of two permanents (CR 701.12) - Bilbo, Luckwearer //
Burglar's Plot's Adventure: "Exchange control of two target nonland
permanents that share a card type." - and Bilbo's own "Bilbo can't be
blocked."

- CR 701.12b: the two permanents' controllers simultaneously gain control of
  the other one; if one player controls both, the exchange does nothing.
- CR 701.12a: if the entire exchange can't be completed, no part of it
  occurs - a target gone before resolution stops the whole exchange.
- "that share a card type" restricts the pair (CR 601.2c): at least one card
  type in common.
- The control change is a layer 2 effect (CR 613.1b) with no duration: it
  lasts past the turn.

Off-set proofs, not in any deck list: Switcheroo ("Exchange control of two
target creatures.") and Shifting Loyalties ("Exchange control of two target
permanents that share a card type." - lands included).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario

BILBO = "Bilbo, Luckwearer // Burglar's Plot"


def _controller(scenario, permanent):
    return scenario.game.controller_of(permanent).username


def _cast_plot(scenario, *targets, resolve=True):
    casting = scenario.cast("Bilbo, Luckwearer", username="alice")
    casting.cast_as_adventure()
    casting.choose_targets(list(targets))
    scenario.pay_with(
        casting.begin_paying(), *scenario.untapped_sources(*["Island"] * 5, username="alice")
    )
    spell = scenario.put_on_stack(casting)
    if resolve:
        scenario.pass_until_resolved()
    return spell


def _plot_board(*, alice=(), bob=()):
    return (
        Scenario()
        .player("alice", hand=[BILBO], battlefield=[*["Island"] * 5, *alice])
        .player("bob", battlefield=list(bob))
        .build()
    )


def test_burglars_plot_swaps_two_creatures():
    scenario = _plot_board(alice=["Grizzly Bears"], bob=["Hill Giant"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")

    plot = _cast_plot(scenario, bears, giant)

    assert _controller(scenario, bears) == "bob"
    assert _controller(scenario, giant) == "alice"
    # CR 715.3d: an Adventure that resolves is exiled, to be cast later as Bilbo.
    assert plot.zone is Zone.EXILE


def test_the_exchange_outlasts_the_turn():
    scenario = _plot_board(alice=["Grizzly Bears"], bob=["Hill Giant"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    _cast_plot(scenario, bears, giant)

    scenario.start_at(Step.END_STEP)
    scenario.advance()  # cleanup (CR 514.2)

    assert _controller(scenario, giant) == "alice"
    assert _controller(scenario, bears) == "bob"


def test_artifacts_can_be_exchanged_too():
    """ "nonland permanents that share a card type" - two artifacts."""
    scenario = _plot_board(alice=["Mind Stone"], bob=["Sol Ring"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "alice")
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")

    _cast_plot(scenario, stone, ring)

    assert _controller(scenario, ring) == "alice"
    assert _controller(scenario, stone) == "bob"


def test_an_artifact_creature_shares_a_type_with_a_plain_artifact():
    scenario = _plot_board(alice=["Ornithopter"], bob=["Sol Ring"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    thopter = scenario.creature("Ornithopter", "alice")
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")

    _cast_plot(scenario, thopter, ring)

    assert _controller(scenario, ring) == "alice"


def test_targets_that_share_no_card_type_are_refused():
    scenario = _plot_board(alice=["Grizzly Bears"], bob=["Sol Ring"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")

    casting = scenario.cast("Bilbo, Luckwearer", username="alice")
    casting.cast_as_adventure()
    with pytest.raises(ValueError, match="share a card type"):
        casting.choose_targets([bears, ring])


def test_a_land_is_not_a_legal_target():
    scenario = _plot_board(alice=["Grizzly Bears"], bob=["Forest"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "bob")

    casting = scenario.cast("Bilbo, Luckwearer", username="alice")
    casting.cast_as_adventure()
    with pytest.raises(ValueError):
        casting.choose_targets([bears, forest])


def test_two_permanents_one_player_controls_are_not_exchanged():
    """CR 701.12b: "if those permanents are controlled by the same player,
    the exchange effect does nothing"."""
    scenario = _plot_board(alice=["Grizzly Bears", "Hill Giant"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")

    _cast_plot(scenario, bears, giant)

    assert _controller(scenario, bears) == "alice"
    assert _controller(scenario, giant) == "alice"
    assert scenario.game.continuous_effects.effects == []


def test_a_target_gone_before_resolution_stops_the_whole_exchange():
    """CR 701.12a: no part of an incomplete exchange occurs - the Bears still
    on the battlefield stay with alice."""
    scenario = _plot_board(alice=["Grizzly Bears"], bob=["Hill Giant"])
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    _cast_plot(scenario, bears, giant, resolve=False)

    scenario.game.destroy(giant)
    scenario.pass_until_resolved()

    assert _controller(scenario, bears) == "alice"


def test_bilbo_cannot_be_blocked():
    scenario = (
        Scenario()
        .player("alice", battlefield=[BILBO], library=["Island"] * 3)
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bilbo = scenario.creature("Bilbo, Luckwearer", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.attack_with(bilbo)
    scenario.pass_until_resolved()
    scenario.advance()  # declare blockers

    with pytest.raises(ValueError):
        scenario.block(bilbo, bears)


# -- Switcheroo and Shifting Loyalties (off-set proofs) --------------------


def test_switcheroo_swaps_two_creatures():
    scenario = (
        Scenario()
        .player("alice", hand=["Switcheroo"], battlefield=[*["Island"] * 5, "Grizzly Bears"])
        .player("bob", battlefield=["Serra Angel"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    angel = scenario.creature("Serra Angel", "bob")

    scenario.cast_and_resolve(
        "Switcheroo", *scenario.untapped_sources(*["Island"] * 5), targets=[bears, angel]
    )

    assert _controller(scenario, angel) == "alice"
    assert _controller(scenario, bears) == "bob"


def test_switcheroo_two_of_the_opponents_creatures_does_nothing():
    scenario = (
        Scenario()
        .player("alice", hand=["Switcheroo"], battlefield=["Island"] * 5)
        .player("bob", battlefield=["Serra Angel", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    angel = scenario.creature("Serra Angel", "bob")

    scenario.cast_and_resolve(
        "Switcheroo", *scenario.untapped_sources(*["Island"] * 5), targets=[bears, angel]
    )

    assert _controller(scenario, angel) == "bob"
    assert _controller(scenario, bears) == "bob"


def test_shifting_loyalties_can_swap_lands():
    scenario = (
        Scenario()
        .player("alice", hand=["Shifting Loyalties"], battlefield=["Island"] * 6)
        .player("bob", battlefield=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    islands = scenario.untapped_sources(*["Island"] * 6)
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "bob")

    scenario.cast_and_resolve("Shifting Loyalties", *islands[:6], targets=[islands[0], forest])

    assert _controller(scenario, forest) == "alice"
    assert _controller(scenario, islands[0]) == "bob"
