"""Scenario: "Spend only <colour> mana on X." - a restriction on how the X part
of a cost is paid.

Consume Spirit: "{X}{B} ... Spend only black mana on X. Consume Spirit deals X
damage to any target and you gain X life." Crypt Rats prints the same sentence
on an activated ability ("{X}: This creature deals X damage to each creature
and each player. Spend only black mana on X."), so the restriction is proven on
a spell cost and on an activation cost by the same reader.

CR 107.3a: the controller announces X as the spell is cast or the ability is
activated, and X in the cost then equals the announced value; CR 601.2f/601.2h:
the total cost is determined and then paid in full. The restriction is on the
mana paying X's share of that cost: the rest of the cost ({B}, or any cost
increase's generic) is paid as usual. A payment that would spend other mana on
X is refused with the engine's own words naming the sentence, and auto-pay
never chooses it.

Every CR number here was verified with `mise run rules:find` in the session
that wrote this file.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario


def _board(lands, *, hand=("Consume Spirit",), battlefield_extra=(), bob_bf=("Colossal Dreadmaw",)):
    scenario = (
        Scenario()
        .player("alice", hand=list(hand), battlefield=[*lands, *battlefield_extra])
        .player("bob", battlefield=list(bob_bf))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _casting(scenario, x, targets):
    casting = scenario.cast("Consume Spirit")
    casting.choose_modes([], x_value=x)
    casting.choose_targets(targets)
    casting.determine_cost(x_value=x)
    return casting


def _cast_with(scenario, x, targets, sources):
    casting = _casting(scenario, x, targets)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()


# ---------------------------------------------------------------------------
# Consume Spirit - a spell. {X}{1}{B}: X's share must be black, the {1} and the
# {B} are the rest of the total cost.
# ---------------------------------------------------------------------------


def test_x_paid_with_black_mana_deals_x_and_gains_x():
    scenario = _board(["Swamp"] * 5)
    sources = scenario.untapped_sources(*["Swamp"] * 5)
    _cast_with(scenario, 3, ["bob"], sources)
    assert scenario.player("bob").life == 17
    assert scenario.player("alice").life == 23
    assert scenario.find("Consume Spirit", Zone.GRAVEYARD, "alice") is not None


def test_x_can_target_a_creature():
    scenario = _board(["Swamp"] * 4)
    dreadmaw = scenario.creature("Colossal Dreadmaw", "bob")
    sources = scenario.untapped_sources(*["Swamp"] * 4)
    casting = _casting(scenario, 2, [dreadmaw])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    assert dreadmaw.damage == 2
    assert scenario.player("alice").life == 22


def test_the_generic_one_is_not_x_so_any_mana_pays_it():
    """X=2: two black for X, {B}, and a Mountain for the printed {1}."""
    scenario = _board(["Swamp", "Swamp", "Swamp", "Mountain"])
    sources = scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Mountain")
    _cast_with(scenario, 2, ["bob"], sources)
    assert scenario.player("bob").life == 18
    assert scenario.player("alice").life == 22


def test_non_black_mana_cannot_pay_for_x():
    """X=2 on {X}{1}{B}: four mana, but only one non-black may be spent (on the
    {1}); the second Mountain would be paying for X, so the payment is refused
    and says which sentence forbids it."""
    scenario = _board(["Swamp", "Swamp", "Mountain", "Mountain"])
    sources = scenario.untapped_sources("Swamp", "Swamp", "Mountain", "Mountain")
    casting = _casting(scenario, 2, ["bob"])
    payment = casting.begin_paying()
    with pytest.raises(ValueError, match="Spend only black mana on X"):
        scenario.pay_with(payment, *sources)


def test_colourless_mana_cannot_pay_for_x_either():
    scenario = _board(["Swamp", "Swamp", "Wastes", "Wastes"])
    sources = scenario.untapped_sources("Swamp", "Swamp", "Wastes", "Wastes")
    casting = _casting(scenario, 2, ["bob"])
    payment = casting.begin_paying()
    with pytest.raises(ValueError, match="Spend only black mana on X"):
        scenario.pay_with(payment, *sources)


def test_a_refused_payment_leaves_the_lands_untapped():
    """CR 733.1: an illegal payment is reversed - nothing is spent."""
    scenario = _board(["Swamp", "Swamp", "Mountain", "Mountain"])
    sources = scenario.untapped_sources("Swamp", "Swamp", "Mountain", "Mountain")
    casting = _casting(scenario, 2, ["bob"])
    payment = casting.begin_paying()
    with pytest.raises(ValueError):
        scenario.pay_with(payment, *sources)
    payment.cancel()
    assert all(not source.tapped for source in sources)


def test_x_zero_pays_the_one_and_the_black_pip_with_anything_black_or_not():
    scenario = _board(["Swamp", "Mountain"])
    sources = scenario.untapped_sources("Swamp", "Mountain")
    _cast_with(scenario, 0, ["bob"], sources)
    assert scenario.player("bob").life == 20
    assert scenario.player("alice").life == 20
    assert scenario.find("Consume Spirit", Zone.GRAVEYARD, "alice") is not None


def test_a_cost_increase_is_not_x_so_any_mana_pays_it():
    """Sphere of Resistance: "Spells cost {1} more to cast." That {1} is a cost
    increase (CR 601.2f), not X: with X=1 the generic is X + {1} + {1}, four
    mana with the {B}, and the two Mountains pay the two that are not X."""
    scenario = _board(
        ["Swamp", "Swamp", "Mountain", "Mountain"], battlefield_extra=["Sphere of Resistance"]
    )
    sources = scenario.untapped_sources("Swamp", "Swamp", "Mountain", "Mountain")
    _cast_with(scenario, 1, ["bob"], sources)
    assert scenario.player("bob").life == 19


def test_auto_pay_chooses_black_for_x_when_other_mana_is_available():
    scenario = _board(["Mountain", "Mountain", "Swamp", "Swamp", "Swamp"])
    casting = _casting(scenario, 2, ["bob"])
    payment = casting.begin_paying()
    scenario.auto_pay(payment)
    scenario.put_on_stack(casting)
    scenario.resolve_top()
    assert scenario.player("bob").life == 18
    swamps = [land for land in scenario.game.battlefield if land.name == "Swamp"]
    assert all(land.tapped for land in swamps)


def test_auto_pay_cannot_find_a_payment_without_enough_black_mana():
    scenario = _board(["Mountain", "Mountain", "Mountain", "Swamp", "Swamp"])
    casting = _casting(scenario, 3, ["bob"])
    payment = casting.begin_paying()
    with pytest.raises(ValueError, match="Spend only black mana on X"):
        scenario.auto_pay(payment)


def test_the_stack_object_keeps_its_full_mana_value():
    """The restriction changes what may pay, not what the spell costs: X=3 on
    {X}{1}{B} is mana value 5 (CR 202.3e) and five mana are spent."""
    scenario = _board(["Swamp"] * 5)
    sources = scenario.untapped_sources(*["Swamp"] * 5)
    casting = _casting(scenario, 3, ["bob"])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *sources)
    spell = scenario.put_on_stack(casting)
    assert all(source.tapped for source in sources)
    assert scenario.game.cast_record_of(spell).x_value == 3


# ---------------------------------------------------------------------------
# Crypt Rats - an activated ability (the second printing of the sentence)
# ---------------------------------------------------------------------------


def _rats_board(lands):
    scenario = (
        Scenario()
        .player("alice", battlefield=["Crypt Rats", *lands])
        .player("bob", battlefield=["Colossal Dreadmaw", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_crypt_rats_x_paid_with_black_mana_hits_everything():
    scenario = _rats_board(["Swamp", "Swamp"])
    rats = scenario.creature("Crypt Rats", "alice")
    sources = scenario.untapped_sources("Swamp", "Swamp")
    scenario.activate(rats, *sources, x_value=2)
    scenario.resolve_top()
    assert scenario.player("alice").life == 18
    assert scenario.player("bob").life == 18
    assert scenario.creature("Colossal Dreadmaw", "bob").damage == 2
    assert scenario.find("Grizzly Bears", Zone.GRAVEYARD, "bob") is not None
    assert scenario.find("Crypt Rats", Zone.GRAVEYARD, "alice") is not None


def test_crypt_rats_x_cannot_be_paid_with_other_mana():
    scenario = _rats_board(["Swamp", "Mountain"])
    rats = scenario.creature("Crypt Rats", "alice")
    sources = scenario.untapped_sources("Swamp", "Mountain")
    with pytest.raises(ValueError, match="Spend only black mana on X"):
        scenario.activate(rats, *sources, x_value=2)


def test_crypt_rats_auto_pay_picks_the_swamps():
    scenario = _rats_board(["Mountain", "Swamp", "Mountain", "Swamp"])
    rats = scenario.creature("Crypt Rats", "alice")
    scenario.activate(rats, auto=True, x_value=2)
    scenario.resolve_top()
    assert scenario.player("bob").life == 18
    assert not any(land.tapped for land in scenario.game.battlefield if land.name == "Mountain")
