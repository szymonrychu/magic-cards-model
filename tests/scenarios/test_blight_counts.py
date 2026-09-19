"""Blight N as a cost, with its count read from the sentence: "Blight 1" and
"Blight 2" in an activation cost (Sting-Slinger, Dawnhand Dissident), "blight
2 or pay {1}" as a spell's additional cost (Wild Unraveling), and "blight X"
(Soul Immolation).

- **CR 701.68a** - "To 'blight N' means to put N -1/-1 counters on a creature
  you control."
- **CR 701.68b** - a player unable to put N -1/-1 counters on a creature they
  control can't choose to blight.
- **CR 601.2b** - the player announces their intentions to pay additional
  costs as the spell is cast, and the value of a variable cost.
- **CR 107.3a** - an X in an additional cost that the text does not define is
  chosen and announced by the caster.
- **CR 118.3** - a cost cannot be paid without the resources to pay it fully.

The optional "you may blight 1" (Requiting Hex, Burning Curiosity) is in
`test_blight.py`. Every CR number above was read with `mise run rules:find` in
the session that wrote this file.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _resolve(scenario: Scenario) -> None:
    while scenario.game.stack:
        scenario.pass_until_resolved()


# -- Blight N in an activation cost ----------------------------------------


def test_blight_1_puts_one_counter_on_the_chosen_creature():
    """Sting-Slinger: "{1}{R}, {T}, Blight 1: This creature deals 2 damage to
    each opponent." """
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Mountain"],
            battlefield=["Sting-Slinger", "Mountain", "Mountain", "Grizzly Bears"],
        )
        .player("bob", library=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    slinger = scenario.creature("Sting-Slinger", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.will_choose_cards(bears, username="alice")
    scenario.activate(slinger, *scenario.untapped_sources("Mountain", "Mountain"))
    _resolve(scenario)

    assert bears.counters[Counter.MINUS_ONE] == 1
    assert slinger.counters[Counter.MINUS_ONE] == 0
    assert scenario.player("bob").life == 18


def test_blight_2_puts_two_counters_on_the_chosen_creature():
    """Dawnhand Dissident: "{T}, Blight 2: Exile target card from a
    graveyard." - its second ability, a different count."""
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Swamp"],
            battlefield=["Dawnhand Dissident", "Sting-Slinger"],
        )
        .player("bob", library=["Swamp"], graveyard=["Memnite"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dissident = scenario.creature("Dawnhand Dissident", "alice")
    slinger = scenario.creature("Sting-Slinger", "alice")
    memnite = scenario.find("Memnite", Zone.GRAVEYARD, "bob")

    scenario.will_choose_cards(slinger, username="alice")
    scenario.activate(dissident, index=1, targets=[memnite])
    _resolve(scenario)

    assert slinger.counters[Counter.MINUS_ONE] == 2
    assert memnite.zone is Zone.EXILE


def test_blight_is_refused_on_a_creature_the_payer_does_not_control():
    """CR 701.68a: a creature *you control*."""
    scenario = (
        Scenario()
        .player(
            "alice", library=["Mountain"], battlefield=["Sting-Slinger", "Mountain", "Mountain"]
        )
        .player("bob", library=["Mountain"], battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    slinger = scenario.creature("Sting-Slinger", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.will_choose_cards(bears, username="alice")
    with pytest.raises(ValueError):
        scenario.activate(slinger, *scenario.untapped_sources("Mountain", "Mountain"))
    assert bears.counters[Counter.MINUS_ONE] == 0


# -- "blight 2 or pay {1}" -------------------------------------------------


def _unraveling_board(islands: int) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Mountain"],
            library=["Mountain"],
        )
        .player(
            "bob",
            hand=["Wild Unraveling"],
            battlefield=["Sting-Slinger", *(["Island"] * islands)],
            library=["Island"],
        )
    )


def test_blighting_instead_of_paying_the_mana():
    scenario = _unraveling_board(islands=2).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.cast_onto_stack("Lightning Bolt", username="alice", auto=True, targets=["bob"])
    scenario.pass_priority("alice")
    slinger = scenario.creature("Sting-Slinger", "bob")
    islands = scenario.untapped_sources("Island", "Island", username="bob")

    casting = scenario.cast("Wild Unraveling", username="bob")
    casting.pay_blight(slinger)
    casting.choose_targets([bolt])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *islands)
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()

    assert slinger.counters[Counter.MINUS_ONE] == 2
    assert bolt.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 20


def test_not_blighting_pays_the_extra_mana():
    scenario = _unraveling_board(islands=3).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.cast_onto_stack("Lightning Bolt", username="alice", auto=True, targets=["bob"])
    scenario.pass_priority("alice")
    slinger = scenario.creature("Sting-Slinger", "bob")
    islands = scenario.untapped_sources("Island", "Island", "Island", username="bob")

    scenario.cast_and_resolve("Wild Unraveling", *islands, username="bob", targets=[bolt])

    assert slinger.counters[Counter.MINUS_ONE] == 0
    assert bolt.zone is Zone.GRAVEYARD
    assert all(island.tapped for island in islands)


def test_not_blighting_with_only_the_printed_mana_is_refused():
    scenario = _unraveling_board(islands=2).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.cast_onto_stack("Lightning Bolt", username="alice", auto=True, targets=["bob"])
    scenario.pass_priority("alice")
    islands = scenario.untapped_sources("Island", "Island", username="bob")

    with pytest.raises(ValueError):
        scenario.cast_and_resolve("Wild Unraveling", *islands, username="bob", targets=[bolt])


# -- blight X --------------------------------------------------------------


def _immolation_board() -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Soul Immolation"],
            battlefield=["Sting-Slinger", *(["Mountain"] * 5)],
            library=["Mountain"],
        )
        .player("bob", library=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


@pytest.mark.parametrize("x_value", [1, 2])
def test_blight_x_puts_the_announced_x_counters(x_value: int):
    """Sting-Slinger is a 3/3, so X may be 1 or 2 and it survives (at X of 3
    CR 704.5f puts it into the graveyard, taking its counters with it)."""
    scenario = _immolation_board()
    slinger = scenario.creature("Sting-Slinger", "alice")
    mountains = scenario.untapped_sources(*["Mountain"] * 5)

    casting = scenario.cast("Soul Immolation", username="alice")
    casting.pay_blight(slinger)
    payment = casting.determine_cost(x_value=x_value)
    casting.begin_paying()
    scenario.pay_with(payment, *mountains)
    scenario.put_on_stack(casting)

    assert slinger.counters[Counter.MINUS_ONE] == x_value


def test_blight_x_above_the_greatest_toughness_is_refused():
    """ "X can't be greater than the greatest toughness among creatures you
    control." - Sting-Slinger's toughness is 3."""
    scenario = _immolation_board()
    slinger = scenario.creature("Sting-Slinger", "alice")

    casting = scenario.cast("Soul Immolation", username="alice")
    casting.pay_blight(slinger)
    with pytest.raises(ValueError, match="greatest toughness"):
        casting.determine_cost(x_value=4)
    assert slinger.counters[Counter.MINUS_ONE] == 0
