"""CR 107.3c / 107.3i: "where X is <count>" defines X for the whole ability,
so a later sentence that only says "X" uses the same definition - Tezzeret,
Master of the Bridge's "+2: Tezzeret deals X damage to each opponent, where
X is the number of artifacts you control. You gain X life." Each sentence
reads X as it is applied (CR 107.3c: "the value of X may change while that
spell or ability is on the stack").
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _ability_index(scenario, permanent, starts_with: str) -> int:
    for index, ability in enumerate(scenario.game.activated_abilities(permanent)):
        if ability.effect.startswith(starts_with):
            return index
    raise AssertionError(f"{permanent.name} has no ability starting {starts_with!r}")


def test_tezzeret_plus_two_carries_its_x_into_the_life_gain():
    """Tezzeret, Master of the Bridge: "+2: Tezzeret deals X damage to each
    opponent, where X is the number of artifacts you control. You gain X
    life." CR 107.3c/107.3i: the second sentence's X is the one the first
    defined - three artifacts, 3 damage and 3 life."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Tezzeret, Master of the Bridge", "Sol Ring", "Ornithopter", "Mind Stone"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    tezzeret = scenario.find("Tezzeret, Master of the Bridge", Zone.BATTLEFIELD)
    index = _ability_index(scenario, tezzeret, "Tezzeret deals X damage")

    scenario.activate(tezzeret, index=index)
    scenario.pass_until_resolved()

    assert scenario.game.player("bob").life == 17
    assert scenario.game.player("alice").life == 23
