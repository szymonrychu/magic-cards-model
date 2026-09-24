"""Mana-production replacement effects (CR 106.12, 106.12b, 614.1a, 616.1).

Two templates, one event:

- Damping Sphere: "If a land is tapped for two or more mana, it produces {C}
  instead of any other type and amount."
- Nyxbloom Ancient (the proof printing - neither a listed card nor in any api
  deck): "If you tap a permanent for mana, it produces three times as much of
  that mana instead."

Every CR number here was read in full with `mise run rules:find`:

- **CR 106.12** - to "tap [a permanent] for mana" is to activate a mana
  ability of that permanent that includes the {T} symbol in its activation
  cost.
- **CR 106.12b** - "A replacement effect that applies if a permanent 'is
  tapped for mana' or tapped for mana of a specific type and/or amount
  modifies the mana production event while such an ability is resolving and
  producing mana or the specified type and/or amount of mana."
- **CR 614.1a** - effects that use the word "instead" are replacement effects.
- **CR 614.5** - a replacement effect gets only one opportunity to affect an
  event or any modified events that may replace that event.
- **CR 616.1** - the affected player chooses the order; **CR 616.1e** any
  applicable effect may be chosen; **CR 616.1f** once one is applied, the
  process repeats "taking into account only replacement or prevention effects
  that would now be applicable".
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Color, Zone
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import Scenario


def _pool(scenario, username: str = "alice") -> dict[Color, int]:
    return dict(scenario.player(username).mana_pool.floating)


def _board(alice: list[str], bob: list[str] | None = None, *, hand: list[str] | None = None):
    scenario = (
        Scenario()
        .player("alice", battlefield=alice, hand=hand or [])
        .player("bob", battlefield=bob or [])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


# -- Damping Sphere ---------------------------------------------------------


def test_sphere_turns_a_land_tapped_for_two_mana_into_one_colorless():
    """Ancient Tomb's "{T}: Add {C}{C}" is a land tapped for two mana, so the
    production is replaced by a single {C} (CR 106.12b). The ability's other
    effect is not production and still happens (2 damage to its controller)."""
    scenario = _board(["Damping Sphere", "Ancient Tomb"])
    tomb = scenario.find("Ancient Tomb", Zone.BATTLEFIELD)

    scenario.activate(tomb)

    assert _pool(scenario) == {Color.COLORLESS: 1}
    assert scenario.player("alice").life == 18


def test_sphere_leaves_a_land_tapped_for_one_mana_alone():
    """ "Two or more mana" is the whole condition: a Mountain's single {R} is
    neither reduced nor recoloured."""
    scenario = _board(["Damping Sphere", "Mountain"])

    scenario.activate(scenario.find("Mountain", Zone.BATTLEFIELD))

    assert _pool(scenario) == {Color.RED: 1}


def test_sphere_does_not_touch_a_nonland_permanent():
    """ "If a land is tapped": Khalni Gem is an artifact tapped for two mana of
    one colour, and keeps both, colour and amount."""
    scenario = _board(["Damping Sphere", "Khalni Gem"])

    scenario.activate(scenario.find("Khalni Gem", Zone.BATTLEFIELD), color=Color.GREEN)

    assert _pool(scenario) == {Color.GREEN: 2}


def test_sphere_applies_to_an_opponents_land_too():
    """No "you" in Damping Sphere's text: bob's Sphere replaces alice's Tomb."""
    scenario = _board(["Ancient Tomb"], ["Damping Sphere"])

    scenario.activate(scenario.find("Ancient Tomb", Zone.BATTLEFIELD))

    assert _pool(scenario) == {Color.COLORLESS: 1}


def test_sphere_applies_on_the_spell_payment_path():
    """The same replacement on `CostPayment.tap_for_mana`, the path a spell's
    cost is paid through: Forest plus Ancient Tomb is exactly Tarmogoyf's
    {1}{G} under Sphere, with nothing left floating."""
    scenario = _board(["Damping Sphere", "Forest", "Ancient Tomb"], hand=["Tarmogoyf"])
    forest = scenario.find("Forest", Zone.BATTLEFIELD)
    tomb = scenario.find("Ancient Tomb", Zone.BATTLEFIELD)

    goyf = scenario.cast_and_resolve("Tarmogoyf", forest, tomb)

    assert goyf.zone is Zone.BATTLEFIELD
    assert _pool(scenario) == {}


def test_auto_tap_plans_with_the_replaced_production():
    """The auto-tap solver asks what a source really produces: under Sphere
    Ancient Tomb is one mana, so a {1}{G} spell needs the Forest *and* the
    Tomb, and the plan taps both."""
    scenario = _board(["Damping Sphere", "Forest", "Ancient Tomb"], hand=["Tarmogoyf"])

    goyf = scenario.cast_and_resolve("Tarmogoyf", auto=True)

    assert goyf.zone is Zone.BATTLEFIELD
    assert scenario.find("Ancient Tomb", Zone.BATTLEFIELD).tapped
    assert scenario.find("Forest", Zone.BATTLEFIELD).tapped


def test_auto_tap_refuses_a_cost_the_replaced_production_cannot_cover():
    """With only Ancient Tomb under Sphere, a {2} cost is unpayable: the
    solver must not count the Tomb as two."""
    scenario = _board(["Damping Sphere", "Ancient Tomb"], hand=["Mind Stone"])
    payment = scenario.cast("Mind Stone").begin_paying()

    with pytest.raises(ValueError):
        scenario.auto_pay(payment)

    assert not scenario.find("Ancient Tomb", Zone.BATTLEFIELD).tapped


# -- Nyxbloom Ancient (the proof printing) ------------------------------------


def test_nyxbloom_triples_a_land_you_tap():
    scenario = _board(["Nyxbloom Ancient", "Forest"])

    scenario.activate(scenario.find("Forest", Zone.BATTLEFIELD))

    assert _pool(scenario) == {Color.GREEN: 3}


def test_nyxbloom_triples_a_nonland_permanent_you_tap():
    """ "A permanent", not "a land": Mind Stone's {C} becomes {C}{C}{C}."""
    scenario = _board(["Nyxbloom Ancient", "Mind Stone"])

    scenario.activate(scenario.find("Mind Stone", Zone.BATTLEFIELD))

    assert _pool(scenario) == {Color.COLORLESS: 3}


def test_nyxbloom_ignores_an_opponent_tapping_their_own_land():
    """ "If *you* tap": bob's Forest, tapped by bob, is not alice's to triple."""
    scenario = _board(["Nyxbloom Ancient"], ["Forest"])
    scenario.pass_priority()  # bob holds priority to activate

    scenario.activate(scenario.find("Forest", Zone.BATTLEFIELD, "bob"))

    assert _pool(scenario, "bob") == {Color.GREEN: 1}


def test_nyxbloom_mana_pays_a_bigger_cost_from_one_land():
    """The auto-tap solver sees the tripled production: one Forest pays
    Tarmogoyf's {1}{G} and leaves one {G} floating."""
    scenario = _board(["Nyxbloom Ancient", "Forest"], hand=["Tarmogoyf"])

    goyf = scenario.cast_and_resolve("Tarmogoyf", auto=True)

    assert goyf.zone is Zone.BATTLEFIELD
    assert _pool(scenario) == {Color.GREEN: 1}


# -- ordering, CR 616.1 -------------------------------------------------------


def test_one_mana_land_is_tripled_first_and_then_dampened():
    """CR 616.1f: a Forest makes one mana, so only Nyxbloom applies at first.
    Once it has, the land is being tapped for three mana and Sphere applies
    to the modified event - one {C} in the end."""
    scenario = _board(["Nyxbloom Ancient", "Forest"], ["Damping Sphere"])

    scenario.activate(scenario.find("Forest", Zone.BATTLEFIELD))

    assert _pool(scenario) == {Color.COLORLESS: 1}


def test_two_mana_land_takes_the_order_that_keeps_the_most_mana():
    """CR 616.1/616.1e: Ancient Tomb makes two, so both effects apply and the
    affected player chooses. Sphere first then Nyxbloom is {C}{C}{C}; the
    other order is a single {C}. The engine chooses for the tapping player,
    the way it chooses a dual land's colour when it auto-taps, and keeps the
    most mana. CR 614.5: after both have applied, neither applies again."""
    scenario = _board(["Nyxbloom Ancient", "Ancient Tomb"], ["Damping Sphere"])

    scenario.activate(scenario.find("Ancient Tomb", Zone.BATTLEFIELD))

    assert _pool(scenario) == {Color.COLORLESS: 3}


# -- the audit ----------------------------------------------------------------


@pytest.mark.parametrize("name", ["Damping Sphere", "Nyxbloom Ancient"])
def test_every_clause_is_handled(name):
    outcomes = classify_clauses(card(name))
    assert outcomes
    assert {outcome.category for outcome in outcomes} == {HANDLED}, outcomes
