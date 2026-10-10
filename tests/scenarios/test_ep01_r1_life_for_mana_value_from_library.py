"""CR 118.9 / 601.2f / 119.4: casting from the top of the library for life.

    Bolas's Citadel - You may play lands and cast spells from the top of your
    library. If you cast a spell this way, pay life equal to its mana value
    rather than pay its mana cost.

The life replaces the mana cost (an alternative cost, CR 118.9); a spell with X
in its cost pays for the X chosen (CR 202.3e).
"""

import pytest

from magic_cards_model.machines import Step, payability
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

CAST_PERMISSION = "Cast permission"


def _board(library, *, life=20, battlefield=("Bolas's Citadel",)):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=list(battlefield), library=list(library))
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.game.player("alice").life = life
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_from_top(scenario, name, targets=None):
    casting = scenario.cast(name, "alice", from_zone=Zone.LIBRARY)
    casting.use_keyword(CAST_PERMISSION)
    if targets:
        casting.choose_targets(targets)
    payment = casting.begin_paying()
    payment.pay()
    return casting, scenario.put_on_stack(casting)


def test_the_top_card_is_cast_for_life_equal_to_its_mana_value_and_no_mana():
    scenario = _board(["Serra Angel", "Island"])
    _cast_from_top(scenario, "Serra Angel")
    assert scenario.game.player("alice").life == 15
    assert scenario.find("Serra Angel", Zone.STACK, "alice").zone is Zone.STACK


def test_a_one_mana_spell_costs_one_life():
    scenario = _board(["Lightning Bolt", "Island"])
    _cast_from_top(scenario, "Lightning Bolt", targets=["bob"])
    assert scenario.game.player("alice").life == 19


def test_x_in_the_cost_counts_toward_the_life_paid():
    scenario = _board(["Walking Ballista", "Island"])
    casting = scenario.cast("Walking Ballista", "alice", from_zone=Zone.LIBRARY)
    casting.use_keyword(CAST_PERMISSION)
    casting.x_value = 2
    casting.begin_paying().pay()
    scenario.put_on_stack(casting)
    assert scenario.game.player("alice").life == 16


def test_the_card_below_the_top_cannot_be_cast():
    scenario = _board(["Island", "Serra Angel"])
    card = scenario.find("Serra Angel", Zone.LIBRARY, "alice")
    assert not payability(scenario.game, "alice", card).payable


def test_life_that_cannot_be_paid_refuses_the_cast():
    scenario = _board(["Serra Angel", "Island"], life=4)
    card = scenario.find("Serra Angel", Zone.LIBRARY, "alice")
    assert not payability(scenario.game, "alice", card).payable
    with pytest.raises(ValueError):
        _cast_from_top(scenario, "Serra Angel")


def test_without_the_citadel_the_library_is_closed():
    scenario = _board(["Serra Angel"], battlefield=())
    card = scenario.find("Serra Angel", Zone.LIBRARY, "alice")
    assert not payability(scenario.game, "alice", card).payable
