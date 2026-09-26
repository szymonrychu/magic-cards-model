"""Casualty (CR 702.153): an optional sacrifice as the spell is cast, and a
copy when it was paid.

CR 702.153a, read whole with `mise run rules:find` in the session that wrote
this file: "Casualty is a keyword that represents two abilities. The first is
a static ability that functions while the spell with casualty is on the
stack. The second is a triggered ability that functions while the spell with
casualty is on the stack. Casualty N means 'As an additional cost to cast
this spell, you may sacrifice a creature with power N or greater,' and 'When
you cast this spell, if a casualty cost was paid for it, copy it. If the
spell has any targets, you may choose new targets for the copy.' Paying a
spell's casualty cost follows the rules for paying additional costs in rules
601.2b and 601.2f-h."

CR 702.153b: "If a spell has multiple instances of casualty, each is paid
separately and triggers based on the payments made for it, not any other
instance of casualty."

CR 707.10: "a copy of a spell isn't cast", so the copy never triggers
casualty again. CR 601.2h: the sacrifice happens as the total cost is paid.

Join the Maestros (Casualty 2) is the printed proof; Silverquill, the
Disputant's granted "casualty 1" is in `test_spell_keyword_grants.py`.
Neither is in the api deck pool.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import executes
from magic_cards_model.machines.legal_actions import legal_actions
from magic_cards_model.models import Zone
from tests.scenarios.harness import PlayedScenario, Scenario


def maestros_board(*creatures: str, hand: list[str] | None = None) -> PlayedScenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=hand or ["Join the Maestros"],
            battlefield=["Swamp"] * 5 + list(creatures),
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def ogres(scenario: PlayedScenario) -> list:
    return [p for p in scenario.game.battlefield if p.name == "Ogre Warrior Token"]


def casualty_triggers(scenario: PlayedScenario) -> list:
    return [
        item
        for item in [*scenario.game.stack, *scenario.game.pending_triggers]
        if getattr(item, "is_ability", False)
        and (getattr(item.ability, "keyword", None) or "").lower() == "casualty"
    ]


def cast_maestros(scenario: PlayedScenario, *sacrificed):
    casting = scenario.cast("Join the Maestros")
    for creature in sacrificed:
        casting.pay_casualty(creature)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*["Swamp"] * 5))
    return scenario.put_on_stack(casting)


def resolve_everything(scenario: PlayedScenario) -> None:
    while scenario.game.stack:
        scenario.resolve_top()


def test_casualty_is_an_executed_keyword():
    assert executes("Casualty")


def test_paying_casualty_sacrifices_the_creature_and_copies_the_spell():
    scenario = maestros_board("Grizzly Bears")
    bears = scenario.creature("Grizzly Bears", "alice")

    cast_maestros(scenario, bears)

    assert bears.zone is Zone.GRAVEYARD
    assert len(casualty_triggers(scenario)) == 1
    record = scenario.game.cast_record_of(scenario.find("Join the Maestros", Zone.STACK))
    assert record.casualty_paid == 1
    resolve_everything(scenario)
    assert len(ogres(scenario)) == 2


def test_not_paying_casualty_casts_the_spell_once():
    scenario = maestros_board("Grizzly Bears")
    cast_maestros(scenario)
    assert casualty_triggers(scenario) == []
    resolve_everything(scenario)
    assert len(ogres(scenario)) == 1
    assert scenario.creature("Grizzly Bears", "alice").zone is Zone.BATTLEFIELD


def test_a_creature_with_too_little_power_cannot_pay_casualty_2():
    scenario = maestros_board("Llanowar Elves")
    elves = scenario.creature("Llanowar Elves", "alice")
    casting = scenario.cast("Join the Maestros")
    with pytest.raises(ValueError, match="power"):
        casting.pay_casualty(elves)


def test_an_opponents_creature_cannot_pay_casualty():
    scenario = (
        Scenario()
        .player("alice", hand=["Join the Maestros"], battlefield=["Swamp"] * 5)
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    casting = scenario.cast("Join the Maestros")
    with pytest.raises(ValueError, match="control"):
        casting.pay_casualty(bears)


def test_a_single_instance_of_casualty_is_paid_once():
    """The ruling: "You may sacrifice only one creature to pay a spell's
    casualty cost, and you copy the spell only once." """
    scenario = maestros_board("Grizzly Bears", "Grizzly Bears")
    first, second = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="alice")
    casting = scenario.cast("Join the Maestros")
    casting.pay_casualty(first)
    with pytest.raises(ValueError, match="casualty"):
        casting.pay_casualty(second)


def test_a_spell_without_casualty_refuses_a_casualty_payment():
    scenario = maestros_board("Grizzly Bears", hand=["Divination"])
    bears = scenario.creature("Grizzly Bears", "alice")
    casting = scenario.cast("Divination")
    with pytest.raises(ValueError, match="casualty"):
        casting.pay_casualty(bears)


def test_the_copy_is_not_cast_and_does_not_trigger_casualty_again():
    scenario = maestros_board("Grizzly Bears")
    cast_maestros(scenario, scenario.creature("Grizzly Bears", "alice"))
    scenario.resolve_top()  # the casualty trigger: the copy goes on the stack
    assert [state.name for state in scenario.game.stack] == [
        "Join the Maestros",
        "Join the Maestros",
    ]
    assert casualty_triggers(scenario) == []
    copy = scenario.game.stack[-1]
    assert copy.is_copy


def test_game_cast_announces_casualty():
    scenario = maestros_board("Grizzly Bears")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.cast(
        scenario.find("Join the Maestros", Zone.HAND, "alice"),
        "alice",
        casualty=[bears],
        mana_sources=scenario.untapped_sources(*["Swamp"] * 5),
    )
    assert bears.zone is Zone.GRAVEYARD
    resolve_everything(scenario)
    assert len(ogres(scenario)) == 2


def test_legal_actions_offer_the_casualty_cost():
    scenario = maestros_board("Grizzly Bears")
    (cast,) = [
        action
        for action in legal_actions(scenario.game, "alice")
        if action.kind.value == "cast"
        and action.card_id == scenario.find("Join the Maestros", Zone.HAND, "alice").id
    ]
    (option,) = [o for o in cast.additional_cost_options if o.keyword == "casualty"]
    assert "power 2 or greater" in option.cost


def test_the_casualty_trigger_copies_even_after_the_sacrificed_creature_is_gone():
    """The sacrifice is the cost, paid at CR 601.2h; the trigger asks only
    whether it was paid."""
    scenario = maestros_board("Grizzly Bears")
    cast_maestros(scenario, scenario.creature("Grizzly Bears", "alice"))
    assert scenario.player("alice").graveyard[-1].name == "Grizzly Bears"
    resolve_everything(scenario)
    assert len(ogres(scenario)) == 2
