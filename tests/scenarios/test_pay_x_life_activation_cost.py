"""An activation cost that pays X life: "{X}{B}, {T}, Pay X life" (Krumar
Initiate).

- **CR 107.3a** - X in an activation cost that the ability's text does not
  define is chosen and announced by the controller as it activates, and
  "while an activated ability is on the stack, any X in its activation cost
  equals the announced value".
- **CR 118.3b** - "Paying life is done by subtracting the indicated amount of
  life from a player's life total. (Players can always pay 0 life.)"
- **CR 119.4** - a player may pay an amount of life greater than 0 "only if
  their life total is greater than or equal to the amount of the payment".

The life paid is the announced X, read from the cost sentence rather than a
digit search that found none and paid 0. Every CR number above was read with
`mise run rules:find` in the session that wrote this file.
"""

import pytest

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def _board(swamps: int, life: int | None = None) -> Scenario:
    scenario = (
        Scenario()
        .player("alice", library=["Swamp"], battlefield=["Krumar Initiate", *(["Swamp"] * swamps)])
        .player("bob", library=["Swamp"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    if life is not None:
        scenario.player("alice").life = life
    return scenario


@pytest.mark.parametrize("x_value", [2, 3])
def test_pay_x_life_pays_the_announced_x(x_value: int):
    scenario = _board(swamps=x_value + 1)
    krumar = scenario.creature("Krumar Initiate", "alice")
    before = scenario.player("alice").life

    swamps = scenario.untapped_sources(*["Swamp"] * (x_value + 1))
    scenario.activate(krumar, *swamps, x_value=x_value)

    assert scenario.player("alice").life == before - x_value


def test_an_announced_x_above_the_life_total_is_refused():
    """CR 119.4: X of 3 cannot be paid from a life total of 2."""
    scenario = _board(swamps=4, life=2)
    krumar = scenario.creature("Krumar Initiate", "alice")

    swamps = scenario.untapped_sources(*["Swamp"] * 4)
    with pytest.raises(ValueError, match="life"):
        scenario.activate(krumar, *swamps, x_value=3)

    assert scenario.player("alice").life == 2
