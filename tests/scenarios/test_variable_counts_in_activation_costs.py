"""Object costs whose count is X or "one or more": "Remove X +1/+1 counters
from this creature" (Chamber Sentry), "Exile X cards from your graveyard"
(Necropolis Fiend), "Sacrifice X other creatures" (Champion of Stray Souls),
"Discard X cards" (Gix, Yawgmoth Praetor), "Exile one or more creature cards
from your graveyard" (Corpseweft), "Sacrifice one or more artifacts" (Radiant
Lotus).

- **CR 107.3a** - an X in an activation cost that the ability does not define
  is chosen and announced by its controller as it activates; "while an
  activated ability is on the stack, any X in its activation cost equals the
  announced value".
- **CR 118.3** - "A player can't pay a cost without having the necessary
  resources to pay it fully." An X above what the payer has is refused, and so
  is "one or more" with nothing chosen.

These costs used to be refused outright (X is not a number word) or, for
sacrifice and discard, read as one card of any kind. Every CR number above was
read with `mise run rules:find` in the session that wrote this file.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter
from tests.scenarios.harness import Scenario


def _resolve(scenario: Scenario) -> None:
    while scenario.game.stack:
        scenario.pass_until_resolved()


# -- Remove X counters -----------------------------------------------------


@pytest.mark.parametrize("x_value", [2, 3])
def test_remove_x_counters_removes_the_announced_x(x_value: int):
    scenario = (
        Scenario()
        .player("alice", library=["Plains"], battlefield=["Chamber Sentry", *(["Plains"] * 3)])
        .player("bob", library=["Plains"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sentry = scenario.creature("Chamber Sentry", "alice")
    scenario.game.add_counters(sentry, Counter.PLUS_ONE, 4)
    bob = scenario.player("bob")

    plains = scenario.untapped_sources(*["Plains"] * x_value)
    scenario.activate(sentry, *plains, x_value=x_value, targets=[bob])
    _resolve(scenario)

    assert sentry.counters[Counter.PLUS_ONE] == 4 - x_value
    assert bob.life == 20 - x_value


def test_remove_x_counters_above_the_counters_there_is_refused():
    scenario = (
        Scenario()
        .player("alice", library=["Plains"], battlefield=["Chamber Sentry", "Plains", "Plains"])
        .player("bob", library=["Plains"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sentry = scenario.creature("Chamber Sentry", "alice")
    scenario.game.add_counters(sentry, Counter.PLUS_ONE, 1)

    plains = scenario.untapped_sources("Plains", "Plains")
    with pytest.raises(ValueError, match="counter"):
        scenario.activate(sentry, *plains, x_value=2, targets=[scenario.player("bob")])
    assert sentry.counters[Counter.PLUS_ONE] == 1


# -- Exile X cards from your graveyard -------------------------------------


def _fiend_board(graveyard: int) -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Swamp"],
            battlefield=["Necropolis Fiend", *(["Swamp"] * 3)],
            graveyard=["Grizzly Bears"] * graveyard,
        )
        .player("bob", library=["Swamp"], battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


@pytest.mark.parametrize("x_value", [2, 3])
def test_exile_x_cards_from_the_graveyard_exiles_the_announced_x(x_value: int):
    scenario = _fiend_board(graveyard=3)
    fiend = scenario.creature("Necropolis Fiend", "alice")
    alice = scenario.player("alice")
    chosen = list(alice.graveyard[:x_value])
    bears = scenario.creature("Grizzly Bears", "bob")

    swamps = scenario.untapped_sources(*["Swamp"] * x_value)
    scenario.activate(fiend, *swamps, x_value=x_value, exiling=chosen, targets=[bears])

    assert all(card.zone is Zone.EXILE for card in chosen)
    assert len(alice.graveyard) == 3 - x_value


def test_exile_x_cards_with_too_few_in_the_graveyard_is_refused():
    scenario = _fiend_board(graveyard=1)
    fiend = scenario.creature("Necropolis Fiend", "alice")
    alice = scenario.player("alice")
    bears = scenario.creature("Grizzly Bears", "bob")

    swamps = scenario.untapped_sources("Swamp", "Swamp")
    with pytest.raises(ValueError, match="needs 2 card"):
        scenario.activate(fiend, *swamps, x_value=2, exiling=list(alice.graveyard), targets=[bears])
    assert len(alice.graveyard) == 1


# -- Sacrifice X other creatures -------------------------------------------


@pytest.mark.parametrize("x_value", [1, 2])
def test_sacrifice_x_creatures_sacrifices_the_announced_x(x_value: int):
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Swamp"],
            battlefield=[
                "Champion of Stray Souls",
                *(["Swamp"] * 5),
                "Grizzly Bears",
                "Grizzly Bears",
                "Memnite",
            ],
            graveyard=["Memnite", "Memnite"],
        )
        .player("bob", library=["Swamp"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    champion = scenario.creature("Champion of Stray Souls", "alice")
    alice = scenario.player("alice")
    victims = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="alice")[:x_value]
    returning = list(alice.graveyard[:x_value])

    swamps = scenario.untapped_sources(*["Swamp"] * 5)
    scenario.activate(
        champion, *swamps, x_value=x_value, sacrificing=list(victims), targets=list(returning)
    )

    assert all(victim.zone is Zone.GRAVEYARD for victim in victims)
    assert scenario.creature("Memnite", "alice").zone is Zone.BATTLEFIELD
    assert len([c for c in alice.graveyard if c.name == "Grizzly Bears"]) == x_value


# -- Discard X cards -------------------------------------------------------


@pytest.mark.parametrize("x_value", [1, 2])
def test_discard_x_cards_discards_the_announced_x(x_value: int):
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Swamp"],
            hand=["Grizzly Bears", "Memnite", "Swamp"],
            battlefield=["Gix, Yawgmoth Praetor", *(["Swamp"] * 7)],
        )
        .player("bob", library=["Swamp", "Swamp", "Swamp"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gix = scenario.creature("Gix, Yawgmoth Praetor", "alice")
    alice = scenario.player("alice")
    discards = list(alice.hand[:x_value])

    swamps = scenario.untapped_sources(*["Swamp"] * 7)
    scenario.activate(
        gix, *swamps, x_value=x_value, discarding=discards, targets=[scenario.player("bob")]
    )

    assert all(card.zone is Zone.GRAVEYARD for card in discards)
    assert len(alice.hand) == 3 - x_value


# -- one or more -----------------------------------------------------------


def _corpseweft_board(graveyard: tuple[str, ...] = ("Grizzly Bears", "Grizzly Bears", "Memnite")):
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Swamp"],
            battlefield=["Corpseweft", "Swamp", "Swamp"],
            graveyard=list(graveyard),
        )
        .player("bob", library=["Swamp"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


@pytest.mark.parametrize("count", [1, 2])
def test_exile_one_or_more_exiles_every_card_chosen(count: int):
    scenario = _corpseweft_board()
    corpseweft = scenario.find("Corpseweft", Zone.BATTLEFIELD, "alice")
    alice = scenario.player("alice")
    chosen = [card for card in alice.graveyard if card.name == "Grizzly Bears"][:count]

    swamps = scenario.untapped_sources("Swamp", "Swamp")
    scenario.activate(corpseweft, *swamps, exiling=chosen)

    assert all(card.zone is Zone.EXILE for card in chosen)
    assert len(alice.graveyard) == 3 - count


def test_exile_one_or_more_with_nothing_chosen_is_refused():
    scenario = _corpseweft_board()
    corpseweft = scenario.find("Corpseweft", Zone.BATTLEFIELD, "alice")

    swamps = scenario.untapped_sources("Swamp", "Swamp")
    with pytest.raises(ValueError, match="needs 1 card"):
        scenario.activate(corpseweft, *swamps, exiling=[])
    assert len(scenario.player("alice").graveyard) == 3


def test_exile_one_or_more_refuses_a_card_without_the_quality():
    """A land card is not a creature card, so it cannot pay "creature cards"."""
    scenario = _corpseweft_board(graveyard=("Grizzly Bears", "Swamp"))
    corpseweft = scenario.find("Corpseweft", Zone.BATTLEFIELD, "alice")
    alice = scenario.player("alice")
    land = next(card for card in alice.graveyard if card.name == "Swamp")

    swamps = scenario.untapped_sources("Swamp", "Swamp")
    with pytest.raises(ValueError):
        scenario.activate(corpseweft, *swamps, exiling=[land])


@pytest.mark.parametrize("count", [1, 2])
def test_sacrifice_one_or_more_sacrifices_every_artifact_chosen(count: int):
    scenario = (
        Scenario()
        .player("alice", library=["Swamp"], battlefield=["Radiant Lotus", "Memnite", "Memnite"])
        .player("bob", library=["Swamp"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lotus = scenario.find("Radiant Lotus", Zone.BATTLEFIELD, "alice")
    victims = scenario.creatures("Memnite", "Memnite", username="alice")[:count]

    scenario.activate(lotus, sacrificing=list(victims), targets=[scenario.player("alice")])

    assert all(victim.zone is Zone.GRAVEYARD for victim in victims)
    assert lotus.zone is Zone.BATTLEFIELD


def test_sacrifice_one_or_more_with_nothing_chosen_is_refused():
    scenario = (
        Scenario()
        .player("alice", library=["Swamp"], battlefield=["Radiant Lotus", "Memnite"])
        .player("bob", library=["Swamp"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lotus = scenario.find("Radiant Lotus", Zone.BATTLEFIELD, "alice")

    with pytest.raises(ValueError, match="needs 1 card"):
        scenario.activate(lotus, sacrificing=[], targets=[scenario.player("alice")])
    assert scenario.creature("Memnite", "alice").zone is Zone.BATTLEFIELD
