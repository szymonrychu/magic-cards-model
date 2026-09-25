"""Scenario: Saddle (CR 702.171), and a Mount's "whenever it attacks while
saddled" trigger.

Rules read whole with `mise run rules:find` in the session that wrote this:

- **CR 702.171a** - "Saddle is an activated ability. 'Saddle N' means 'Tap
  any number of other untapped creatures you control with total power N or
  greater: This permanent becomes saddled until end of turn. Activate only
  as a sorcery.'"
- **CR 702.171b** - "Saddled is a designation that has no rules meaning
  other than to act as a marker that spells and abilities can identify. Only
  permanents can be or become saddled. Once a permanent has become saddled,
  it stays saddled until the end of the turn or it leaves the battlefield.
  Being saddled is not a part of the permanent's copiable values."
- **CR 702.171c** - "A creature 'saddles' a permanent as it's tapped to pay
  the cost to activate a permanent's saddle ability."
- **CR 307.5** - "as a sorcery": main phase, own turn, empty stack.
- **CR 302.6** - summoning sickness restricts a creature's own {T}
  abilities; tapping it for another permanent's cost is not one.
- **CR 514.2** - "until end of turn" ends in the cleanup step.
- **CR 603.4** / **CR 608.2a** - the "while saddled" clause.

Brightfield Mustang (Saddle 1) is the reported printing; Drover Grizzly
(Saddle 1), Gloryheath Lynx (Saddle 2) and Guardian Sunmare (Saddle 4, no
reminder text) are the second printings.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import executes, saddle_activation, saddle_number
from tests.cards import card
from tests.scenarios.harness import Scenario


def _board(alice, *, bob=()):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=list(alice), library=["Plains"] * 5)
        .player("bob", battlefield=list(bob), library=["Plains"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _saddle(scenario, mount, *saddling, player="alice"):
    activation = saddle_activation(scenario.game, mount, list(saddling), player)
    refusal = activation.why_not()
    if refusal is not None:
        raise ValueError(refusal)
    activation.begin_paying()
    activation.payment.pay()
    activation.activate()
    return activation


def test_the_saddle_number_is_read_off_every_printing():
    assert saddle_number(card("Brightfield Mustang")) == 1
    assert saddle_number(card("Gloryheath Lynx")) == 2
    assert saddle_number(card("Guardian Sunmare")) == 4
    assert saddle_number(card("Grizzly Bears")) is None
    assert executes("Saddle")


def test_saddling_taps_the_creatures_and_the_mount_becomes_saddled():
    scenario = _board(["Brightfield Mustang", "Memnite"])
    mustang = scenario.creature("Brightfield Mustang", "alice")
    memnite = scenario.creature("Memnite", "alice")
    _saddle(scenario, mustang, memnite)
    assert memnite.tapped
    assert not mustang.tapped
    assert not mustang.saddled, "it goes on the stack first"
    scenario.pass_until_resolved()
    assert mustang.saddled
    assert mustang.saddled_by == (memnite.id,)


def test_total_power_below_n_is_refused():
    scenario = _board(["Gloryheath Lynx", "Memnite"])
    lynx = scenario.creature("Gloryheath Lynx", "alice")
    with pytest.raises(ValueError, match="702.171a"):
        _saddle(scenario, lynx, scenario.creature("Memnite", "alice"))
    assert not scenario.creature("Memnite", "alice").tapped


def test_several_creatures_add_their_power():
    scenario = _board(["Guardian Sunmare", "Grizzly Bears", "Grizzly Bears"])
    sunmare = scenario.creature("Guardian Sunmare", "alice")
    bears = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="alice")
    _saddle(scenario, sunmare, *bears)
    scenario.pass_until_resolved()
    assert sunmare.saddled
    assert set(sunmare.saddled_by) == {bear.id for bear in bears}


def test_the_mount_cannot_saddle_itself():
    scenario = _board(["Brightfield Mustang"])
    mustang = scenario.creature("Brightfield Mustang", "alice")
    with pytest.raises(ValueError):
        _saddle(scenario, mustang, mustang)


def test_an_opponents_creature_cannot_saddle():
    scenario = _board(["Brightfield Mustang"], bob=["Grizzly Bears"])
    mustang = scenario.creature("Brightfield Mustang", "alice")
    with pytest.raises(ValueError):
        _saddle(scenario, mustang, scenario.creature("Grizzly Bears", "bob"))


def test_a_tapped_creature_cannot_saddle():
    scenario = _board(["Brightfield Mustang", "Grizzly Bears"])
    mustang = scenario.creature("Brightfield Mustang", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.tap()
    with pytest.raises(ValueError):
        _saddle(scenario, mustang, bears)


def test_a_summoning_sick_creature_can_saddle():
    scenario = _board(["Brightfield Mustang", "Grizzly Bears"])
    mustang = scenario.creature("Brightfield Mustang", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.summoning_sick = True
    _saddle(scenario, mustang, bears)
    scenario.pass_until_resolved()
    assert mustang.saddled


def test_saddle_only_as_a_sorcery():
    """CR 702.171a's "Activate only as a sorcery" (CR 307.5): not in combat,
    not on the opponent's turn."""
    scenario = _board(["Brightfield Mustang", "Grizzly Bears"])
    mustang = scenario.creature("Brightfield Mustang", "alice")
    scenario.start_at(Step.BEGINNING_OF_COMBAT)
    with pytest.raises(ValueError, match="sorcery"):
        _saddle(scenario, mustang, scenario.creature("Grizzly Bears", "alice"))


def test_saddled_ends_in_the_cleanup_step():
    scenario = _board(["Brightfield Mustang", "Grizzly Bears"])
    mustang = scenario.creature("Brightfield Mustang", "alice")
    _saddle(scenario, mustang, scenario.creature("Grizzly Bears", "alice"))
    scenario.pass_until_resolved()
    assert mustang.saddled
    scenario.turn.advance_to(Step.CLEANUP)
    scenario.game.cleanup_step()
    assert not mustang.saddled
    assert mustang.saddled_by == ()


def test_saddled_ends_when_it_leaves_the_battlefield():
    scenario = _board(["Brightfield Mustang", "Grizzly Bears"])
    mustang = scenario.creature("Brightfield Mustang", "alice")
    _saddle(scenario, mustang, scenario.creature("Grizzly Bears", "alice"))
    scenario.pass_until_resolved()
    scenario.game.exile_permanent(mustang)
    assert not mustang.saddled


def test_a_mount_that_left_in_response_is_not_saddled():
    """CR 400.7: the ability resolves (CR 113.7a) but there is no permanent
    left to become saddled."""
    scenario = _board(["Brightfield Mustang", "Grizzly Bears"])
    mustang = scenario.creature("Brightfield Mustang", "alice")
    _saddle(scenario, mustang, scenario.creature("Grizzly Bears", "alice"))
    scenario.game.destroy(mustang)
    scenario.pass_until_resolved()
    assert not mustang.saddled


# -- "whenever this creature attacks while saddled" ------------------------------


def _attack(scenario, *attackers):
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(*attackers)
    scenario.game.put_triggers_on_stack()


def test_brightfield_mustang_attacking_saddled_triggers():
    scenario = _board(["Brightfield Mustang", "Grizzly Bears"])
    mustang = scenario.creature("Brightfield Mustang", "alice")
    _saddle(scenario, mustang, scenario.creature("Grizzly Bears", "alice"))
    scenario.pass_until_resolved()
    _attack(scenario, mustang)
    assert scenario.stack_names() == ["Brightfield Mustang's triggered ability"]
    (trigger,) = scenario.game.stack
    assert scenario.game._intervening_if_still_true(trigger)  # noqa: SLF001
    assert scenario.game.intervening_if_notices == []


def test_brightfield_mustang_attacking_unsaddled_does_not_trigger():
    scenario = _board(["Brightfield Mustang"])
    mustang = scenario.creature("Brightfield Mustang", "alice")
    _attack(scenario, mustang)
    assert scenario.stack_names() == []
    assert scenario.game.intervening_if_notices == []


def test_drover_grizzly_second_printing_resolves():
    """ "Whenever this creature attacks while saddled, creatures you control
    gain trample until end of turn." """
    from magic_cards_model.machines.combat import has_keyword

    scenario = _board(["Drover Grizzly", "Memnite"])
    grizzly = scenario.creature("Drover Grizzly", "alice")
    _saddle(scenario, grizzly, scenario.creature("Memnite", "alice"))
    scenario.pass_until_resolved()
    _attack(scenario, grizzly)
    assert scenario.stack_names() == ["Drover Grizzly's triggered ability"]
    scenario.pass_until_resolved()
    assert has_keyword(grizzly, "trample", scenario.game)


def test_venomsac_lagac_saddle_two_pumps_itself():
    scenario = _board(["Venomsac Lagac", "Grizzly Bears"])
    lagac = scenario.creature("Venomsac Lagac", "alice")
    _saddle(scenario, lagac, scenario.creature("Grizzly Bears", "alice"))
    scenario.pass_until_resolved()
    _attack(scenario, lagac)
    scenario.pass_until_resolved()
    assert scenario.game.characteristics_of(lagac).toughness == 4


def test_a_saddled_mount_that_leaves_before_resolution_is_removed():
    """CR 608.2a: the clause is rechecked - the Mount is gone, and a new
    object is not saddled."""
    scenario = _board(["Brightfield Mustang", "Grizzly Bears"])
    mustang = scenario.creature("Brightfield Mustang", "alice")
    _saddle(scenario, mustang, scenario.creature("Grizzly Bears", "alice"))
    scenario.pass_until_resolved()
    _attack(scenario, mustang)
    (trigger,) = scenario.game.stack
    scenario.game.exile_permanent(mustang)
    assert not scenario.game._intervening_if_still_true(trigger)  # noqa: SLF001
