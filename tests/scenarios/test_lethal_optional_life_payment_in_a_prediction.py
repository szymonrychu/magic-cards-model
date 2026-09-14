"""A land's optional life payment that would lose the game.

CR 119.4 lets a player pay life equal to their whole life total, so a
shockland at 2 life can still be entered untapped. The payment then leaves the
player at 0 life, and the next state-based action check ends the game for them.
A prediction that offers that option without saying so, or a payability answer
that counts that land's mana, recommends losing.

Rules, each read in full with `mise run rules:find` in the session that wrote
this file:

- **CR 119.4** - life may be paid only if the life total is at least the
  payment; 2 life at 2 life is a legal payment.
- **CR 704.3** - state-based actions are checked whenever a player would get
  priority.
- **CR 704.5a** - "If a player has 0 or less life, that player loses the
  game."
- **CR 614.12a** - the choice to pay is made before the land enters.
"""

from magic_cards_model.machines import EntersState, Step, payability, predict_enters
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board(life, hand=("Watery Grave",), battlefield=()):
    scenario = (
        Scenario()
        .player("alice", hand=list(hand), battlefield=list(battlefield), life=life)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _predict(scenario):
    return predict_enters(scenario.game, "alice", scenario.find("Watery Grave", Zone.HAND, "alice"))


def test_at_two_life_the_payment_is_legal_but_lethal():
    prediction = _predict(_board(life=2))

    assert prediction.state is EntersState.UNTAPPED_IF_PAID
    assert prediction.optional_costs == ("pay 2 life",)
    assert prediction.lethal_if_paid is True
    assert any("704.5a" in notice for notice in prediction.notices)


def test_at_three_life_the_payment_is_not_lethal():
    prediction = _predict(_board(life=3))

    assert prediction.state is EntersState.UNTAPPED_IF_PAID
    assert prediction.lethal_if_paid is False
    assert prediction.notices == ()


def test_a_land_with_no_payment_is_never_lethal():
    scenario = _board(life=1, hand=("Island",))

    prediction = predict_enters(scenario.game, "alice", scenario.find("Island", Zone.HAND, "alice"))

    assert prediction.lethal_if_paid is False


def _frog(life):
    scenario = _board(life=life, hand=("Psychic Frog", "Watery Grave"), battlefield=("Swamp",))
    return payability(
        scenario.game,
        "alice",
        scenario.find("Psychic Frog", Zone.HAND, "alice"),
        assuming_land=scenario.find("Watery Grave", Zone.HAND, "alice"),
    )


def test_a_lethal_payment_does_not_make_psychic_frog_payable():
    """The Grave's {U} exists only if alice pays her last 2 life."""
    report = _frog(life=2)

    assert not report.payable
    assert report.assumed_land.lethal_if_paid is True


def test_a_survivable_payment_makes_psychic_frog_payable():
    report = _frog(life=3)

    assert report.payable
    assert report.assumed_land.lethal_if_paid is False


def test_asking_at_two_life_mutates_nothing():
    scenario = _board(life=2, hand=("Psychic Frog", "Watery Grave"), battlefield=("Swamp",))
    before = scenario.game.model_dump_json()

    _predict(scenario)
    payability(
        scenario.game,
        "alice",
        scenario.find("Psychic Frog", Zone.HAND, "alice"),
        assuming_land=scenario.find("Watery Grave", Zone.HAND, "alice"),
    )

    assert scenario.game.model_dump_json() == before
    assert scenario.player("alice").life == 2
