"""Scenario: "Spells and abilities can't be countered." (Spider-Punk) - a
static ability of a permanent that covers EVERY spell, whoever controls it, as
long as the permanent is on the battlefield (CR 604.2, CR 101.2, CR 113.6g,
CR 701.6a). Contrast "Spells you control can't be countered", which covers only
the controller's own spells (`test_ep01_r1_group_cost_modification.py`).
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting_restrictions import static_uncounterable_source
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import pool
from tests.scenarios.harness import Scenario


def _board(alice_battlefield, bob_battlefield):
    scenario = (
        Scenario()
        .player("alice", hand=["Opt"], battlefield=["Island", *alice_battlefield])
        .player("bob", battlefield=bob_battlefield)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _opt_on_stack(scenario):
    (island,) = scenario.untapped_sources("Island", username="alice")
    scenario.cast_onto_stack("Opt", island, username="alice")
    return scenario.find("Opt", Zone.STACK)


def test_without_the_static_a_spell_is_countered():
    scenario = _board([], [])
    opt = _opt_on_stack(scenario)
    scenario.game.counter(opt)
    assert opt.zone is Zone.GRAVEYARD


def test_the_controllers_own_spell_cannot_be_countered():
    scenario = _board(["Spider-Punk"], [])
    opt = _opt_on_stack(scenario)
    assert static_uncounterable_source(scenario.game, opt) is not None
    scenario.game.counter(opt)
    assert opt.zone is Zone.STACK


def test_an_opponents_spider_punk_protects_my_spell_too():
    """Unlike "Spells you control", the line names no controller."""
    scenario = _board([], ["Spider-Punk"])
    opt = _opt_on_stack(scenario)
    scenario.game.counter(opt)
    assert opt.zone is Zone.STACK


def test_the_protection_ends_when_spider_punk_leaves():
    scenario = _board([], ["Spider-Punk"])
    opt = _opt_on_stack(scenario)
    punk = scenario.creature("Spider-Punk", "bob")
    scenario.game.put_into_graveyard(punk)
    scenario.game.counter(opt)
    assert opt.zone is Zone.GRAVEYARD


def test_the_line_reads_handled_on_the_audit():
    from magic_cards_model.support import HANDLED

    support = card_support(pool()["Spider-Punk"])
    assert all(c.outcome == HANDLED for c in support.clauses)
