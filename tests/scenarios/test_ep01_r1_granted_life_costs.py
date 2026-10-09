"""CR 118.8b / 601.2f: an optional additional cost another permanent grants,
and the conditional reduction tied to having paid it (EP-01 round 1, task T7).

    Defiler of Faith - As an additional cost to cast white permanent spells,
    you may pay 2 life. Those spells cost {W} less to cast if you paid life
    this way. This effect reduces only the amount of white mana you pay.

CR 118.7a/b: that last sentence turns off the spill of a coloured reduction
into generic mana, so a white spell with no {W} in its cost gets nothing.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _main(**players) -> Scenario:
    builder = Scenario().manual_turn_based_actions()
    for username, kwargs in players.items():
        builder = builder.player(username, **kwargs)
    scenario = builder.build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _total(scenario, name, *, pay_life: bool, username="alice"):
    casting = scenario.cast(name, username)
    if pay_life:
        (grant,) = casting.granted_life_costs()
        casting.pay_granted_life_cost(grant)
    scenario.game.determine_total_cost(casting)
    mana = str(casting.total_cost.mana)
    life = sum(
        component.amount
        for component in casting.total_cost.components
        if component.kind.value == "pay_life"
    )
    casting.cancel()
    return mana, life


def test_paying_two_life_takes_one_white_off_a_white_permanent_spell():
    scenario = _main(alice={"hand": ["Serra Angel"], "battlefield": ["Defiler of Faith"]}, bob={})
    assert _total(scenario, "Serra Angel", pay_life=False) == ("{3}{W}{W}", 0)
    assert _total(scenario, "Serra Angel", pay_life=True) == ("{3}{W}", 2)


def test_each_defiler_reaches_only_permanent_spells_of_its_own_colour():
    scenario = _main(
        alice={"hand": ["Grizzly Bears", "Lightning Bolt"], "battlefield": ["Defiler of Faith"]},
        bob={},
    )
    for name in ("Grizzly Bears", "Lightning Bolt"):
        casting = scenario.cast(name, "alice", targets=["bob"] if name == "Lightning Bolt" else None)
        assert casting.granted_life_costs() == []
        casting.cancel()


def test_the_green_defiler_reduces_green_not_white():
    scenario = _main(
        alice={"hand": ["Grizzly Bears", "Serra Angel"], "battlefield": ["Defiler of Vigor"]},
        bob={},
    )
    assert _total(scenario, "Grizzly Bears", pay_life=True) == ("{1}", 2)
    casting = scenario.cast("Serra Angel", "alice")
    assert casting.granted_life_costs() == []
    casting.cancel()


def test_the_reduction_never_spills_into_generic_mana():
    """Kitchen Finks is a white permanent spell whose cost, {1}{G/W}{G/W},
    has no {W} component; CR 118.7b's spill is exactly what the card's last
    sentence switches off."""
    scenario = _main(alice={"hand": ["Kitchen Finks"], "battlefield": ["Defiler of Faith"]}, bob={})
    assert _total(scenario, "Kitchen Finks", pay_life=True) == ("{1}{G/W}{G/W}", 2)


def test_the_opponents_defiler_grants_nothing():
    scenario = _main(
        alice={"hand": ["Serra Angel"]}, bob={"battlefield": ["Defiler of Faith"]}
    )
    casting = scenario.cast("Serra Angel", "alice")
    assert casting.granted_life_costs() == []
    casting.cancel()


def test_two_defilers_each_grant_their_own_optional_cost():
    scenario = _main(
        alice={"hand": ["Serra Angel"], "battlefield": ["Defiler of Faith", "Defiler of Faith"]},
        bob={},
    )
    casting = scenario.cast("Serra Angel", "alice")
    grants = casting.granted_life_costs()
    assert len(grants) == 2
    for grant in grants:
        casting.pay_granted_life_cost(grant)
    scenario.game.determine_total_cost(casting)
    assert str(casting.total_cost.mana) == "{3}"
    casting.cancel()


def test_a_full_cast_pays_the_life_and_the_reduced_mana():
    scenario = _main(
        alice={
            "hand": ["Serra Angel"],
            "battlefield": ["Defiler of Faith", "Plains", "Plains", "Plains", "Plains"],
        },
        bob={},
    )
    casting = scenario.cast("Serra Angel", "alice")
    (grant,) = casting.granted_life_costs()
    casting.pay_granted_life_cost(grant)
    payment = casting.begin_paying()
    payment.auto_tap(scenario.untapped_sources("Plains", "Plains", "Plains", "Plains"))
    payment.pay()
    scenario.put_on_stack(casting)
    assert scenario.game.player("alice").life == 18
    assert scenario.find("Serra Angel", Zone.STACK, "alice").zone is Zone.STACK


def test_the_option_is_listed_with_the_cast_action():
    from magic_cards_model.machines import legal_actions
    from magic_cards_model.models import ActionKind

    scenario = _main(alice={"hand": ["Serra Angel"], "battlefield": ["Defiler of Faith"]}, bob={})
    card = scenario.find("Serra Angel", Zone.HAND, "alice")
    (row,) = [
        action
        for action in legal_actions(scenario.game, "alice")
        if action.card_id == card.id and action.kind is ActionKind.CAST
    ]
    assert [option.cost for option in row.additional_cost_options] == ["pay 2 life"]


def test_life_cannot_be_paid_below_zero():
    scenario = _main(alice={"hand": ["Serra Angel"], "battlefield": ["Defiler of Faith"]}, bob={})
    scenario.game.player("alice").life = 1
    casting = scenario.cast("Serra Angel", "alice")
    (grant,) = casting.granted_life_costs()
    with pytest.raises(ValueError, match="life"):
        casting.pay_granted_life_cost(grant)
    casting.cancel()


def test_game_cast_takes_the_granted_life_cost_as_a_count():
    scenario = _main(
        alice={
            "hand": ["Serra Angel"],
            "battlefield": ["Defiler of Faith", "Plains", "Plains", "Plains", "Plains"],
        },
        bob={},
    )
    card = scenario.find("Serra Angel", Zone.HAND, "alice")
    sources = scenario.untapped_sources("Plains", "Plains", "Plains", "Plains")
    scenario.game.cast(card, "alice", granted_life_costs=1, mana_sources=sources)
    assert scenario.game.player("alice").life == 18
    assert all(source.tapped for source in sources)
