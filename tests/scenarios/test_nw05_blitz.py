"""Blitz (CR 702.152): a creature cast cheap and hasty that is sacrificed at
the next end step and draws a card when it dies.

Read whole with `mise run rules:find` in the session that wrote this file:

- **CR 702.152a** - "Blitz represents three abilities: two static abilities
  that function while the card with blitz is on the stack, one of which may
  create a delayed triggered ability, and a static ability that functions
  while the object with blitz is on the battlefield. 'Blitz [cost]' means
  'You may cast this card by paying [cost] rather than its mana cost,' 'If
  this spell's blitz cost was paid, sacrifice the permanent this spell
  becomes at the beginning of the next end step,' and 'As long as this
  permanent's blitz cost was paid, it has haste and "When this permanent is
  put into a graveyard from the battlefield, draw a card."' Casting a spell
  for its blitz cost follows the rules for paying alternative costs in rules
  601.2b and 601.2f-h."
- **CR 608.3g** - the delayed triggered ability is created as the permanent
  is put onto the battlefield.
- **CR 603.7c** - a delayed triggered ability that refers to an object that
  left its zone and came back (a new object, CR 400.7) does nothing to it.
- **CR 701.21a** - "To sacrifice a permanent, its controller moves it from
  the battlefield directly to its owner's graveyard."

Proved on Pugnacious Pugilist (the listed card) and on Night Clubber, Girder
Goons and Caldaia Strongarm - Modern/Pioneer-legal printings in no deck list,
each with a different blitz cost and a different own trigger.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import keyword_cast_options
from magic_cards_model.machines.combat import Keyword, has_keyword
from magic_cards_model.machines.keywords import executes
from magic_cards_model.models import Zone
from magic_cards_model.models.mana import ManaCost
from magic_cards_model.support import card_support, executed_keywords
from tests.cards import card
from tests.scenarios.harness import Scenario


def board(name: str, lands: list[str]) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", library=["Plains"] * 5, hand=[name], battlefield=lands)
        .player("bob", library=["Plains"] * 5, battlefield=["Grizzly Bears"])
    )


def cast_it(scenario, name: str, *, blitz: bool, lands: list[str]):
    casting = scenario.cast(name)
    if blitz:
        casting.use_keyword("Blitz")
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*lands))
    scenario.put_on_stack(casting)
    permanent = scenario.resolve_top()
    _drain(scenario)
    return permanent


def _drain(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def to_end_step(scenario) -> None:
    while scenario.step is not Step.END_STEP:
        scenario.advance()
    _drain(scenario)


CLUBBER = ["Swamp", "Swamp", "Swamp"]


# --------------------------------------------------------------------------
# The alternative cost (CR 702.152a's first ability, CR 118.9)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "cost"),
    [
        ("Pugnacious Pugilist", "{3}{R}"),
        ("Night Clubber", "{2}{B}"),
        ("Girder Goons", "{3}{B}"),
        ("Caldaia Strongarm", "{3}{G}"),
        ("Mayhem Patrol", "{1}{R}"),
    ],
)
def test_blitz_is_a_way_to_cast_from_hand_for_its_cost(name, cost):
    (option,) = [o for o in keyword_cast_options(card(name)) if o.keyword.lower() == "blitz"]
    assert option.zone is Zone.HAND
    assert option.pays_mana_cost is False
    assert option.rule == "CR 702.152a"
    assert option.cost is not None and option.cost.mana == ManaCost.parse(cost)


def test_the_blitz_cost_replaces_the_mana_cost():
    scenario = board("Night Clubber", CLUBBER).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    casting = scenario.cast("Night Clubber")
    casting.use_keyword("Blitz")

    assert casting.total_cost.mana == ManaCost.parse("{2}{B}")
    assert casting.base_cost == ManaCost.parse("{1}{B}{B}")


def test_the_cast_record_remembers_blitz():
    scenario = board("Night Clubber", CLUBBER).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    casting = scenario.cast("Night Clubber")
    casting.use_keyword("Blitz")
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources(*CLUBBER))
    spell = casting.cast()

    assert scenario.game.was_cast_with(spell, "Blitz")


# --------------------------------------------------------------------------
# Haste and the dies-draw while the blitz cost was paid (third ability)
# --------------------------------------------------------------------------


def test_a_blitzed_creature_has_haste():
    scenario = board("Night Clubber", CLUBBER).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    clubber = cast_it(scenario, "Night Clubber", blitz=True, lands=CLUBBER)

    assert has_keyword(clubber, Keyword.HASTE, scenario.game)
    assert scenario.can_attack(clubber)


def test_a_creature_cast_normally_has_no_haste():
    scenario = board("Night Clubber", CLUBBER).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    clubber = cast_it(scenario, "Night Clubber", blitz=False, lands=CLUBBER)

    assert not has_keyword(clubber, Keyword.HASTE, scenario.game)
    assert not scenario.can_attack(clubber)


def test_a_blitzed_creature_that_dies_draws_a_card():
    scenario = board("Night Clubber", [*CLUBBER, "Mountain"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    clubber = cast_it(scenario, "Night Clubber", blitz=True, lands=CLUBBER)
    hand_before = len(scenario.player("alice").hand)

    scenario.game.destroy(clubber)
    _drain(scenario)

    assert clubber.zone is Zone.GRAVEYARD
    assert len(scenario.player("alice").hand) == hand_before + 1


def test_a_creature_cast_normally_that_dies_draws_nothing():
    scenario = board("Night Clubber", CLUBBER).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    clubber = cast_it(scenario, "Night Clubber", blitz=False, lands=CLUBBER)
    hand_before = len(scenario.player("alice").hand)

    scenario.game.destroy(clubber)
    _drain(scenario)

    assert len(scenario.player("alice").hand) == hand_before


# --------------------------------------------------------------------------
# The delayed sacrifice (second ability, CR 608.3g, CR 603.7)
# --------------------------------------------------------------------------


def test_a_blitzed_creature_is_sacrificed_at_the_next_end_step_and_draws():
    scenario = board("Night Clubber", CLUBBER).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    clubber = cast_it(scenario, "Night Clubber", blitz=True, lands=CLUBBER)
    hand_before = len(scenario.player("alice").hand)

    to_end_step(scenario)

    assert clubber.zone is Zone.GRAVEYARD
    assert len(scenario.player("alice").hand) == hand_before + 1


def test_a_creature_cast_normally_stays_past_the_end_step():
    scenario = board("Night Clubber", CLUBBER).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    clubber = cast_it(scenario, "Night Clubber", blitz=False, lands=CLUBBER)

    to_end_step(scenario)

    assert clubber.zone is Zone.BATTLEFIELD


def test_a_blitzed_creature_that_left_and_came_back_is_not_sacrificed():
    """CR 603.7c / CR 400.7: the new object is not the one the delayed
    trigger refers to, and it has neither haste nor the dies-draw."""
    scenario = board("Night Clubber", CLUBBER).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    clubber = cast_it(scenario, "Night Clubber", blitz=True, lands=CLUBBER)

    scenario.game.return_to_hand(clubber)
    returned = scenario.put_onto_battlefield("Night Clubber")
    _drain(scenario)
    assert not has_keyword(returned, Keyword.HASTE, scenario.game)

    to_end_step(scenario)

    assert returned.zone is Zone.BATTLEFIELD


def test_the_sacrifice_also_fires_the_creatures_own_dies_trigger():
    """Girder Goons: its own "When this creature dies, create a tapped 2/2
    black Rogue creature token." and blitz's draw both trigger off the end
    step sacrifice."""
    lands = ["Swamp"] * 4
    scenario = board("Girder Goons", lands).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    goons = cast_it(scenario, "Girder Goons", blitz=True, lands=lands)
    hand_before = len(scenario.player("alice").hand)

    to_end_step(scenario)

    assert goons.zone is Zone.GRAVEYARD
    assert len(scenario.player("alice").hand) == hand_before + 1
    rogues = [p for p in scenario.game.permanents_controlled_by("alice") if "Rogue" in p.subtypes]
    assert len(rogues) == 1 and rogues[0].tapped


def test_caldaia_strongarm_blitzed_resolves_its_enters_trigger_and_has_haste():
    lands = ["Forest"] * 4
    scenario = board("Caldaia Strongarm", lands).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.game.choose_trigger_targets("Caldaia Strongarm", [bears])
    strongarm = cast_it(scenario, "Caldaia Strongarm", blitz=True, lands=lands)

    assert has_keyword(strongarm, Keyword.HASTE, scenario.game)
    assert bears.counter_count("+1/+1") == 2


def test_mayhem_patrol_blitzed_for_its_own_mana_cost_still_gains_haste():
    """Mayhem Patrol's blitz cost {1}{R} equals its mana cost: still an
    alternative cost (CR 118.9), and it is what grants haste."""
    lands = ["Mountain"] * 2
    scenario = board("Mayhem Patrol", lands).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    patrol = cast_it(scenario, "Mayhem Patrol", blitz=True, lands=lands)

    assert scenario.game.was_cast_with(patrol, "Blitz")
    assert has_keyword(patrol, Keyword.HASTE, scenario.game)
    assert has_keyword(patrol, Keyword.MENACE, scenario.game)

    to_end_step(scenario)
    assert patrol.zone is Zone.GRAVEYARD


def test_pugnacious_pugilist_blitzed_attacks_the_turn_it_is_cast():
    lands = ["Mountain"] * 4
    scenario = board("Pugnacious Pugilist", lands).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    pugilist = cast_it(scenario, "Pugnacious Pugilist", blitz=True, lands=lands)

    assert has_keyword(pugilist, Keyword.HASTE, scenario.game)
    assert scenario.can_attack(pugilist)

    to_end_step(scenario)
    assert pugilist.zone is Zone.GRAVEYARD


# --------------------------------------------------------------------------
# Support audit
# --------------------------------------------------------------------------


def test_blitz_is_executed_by_the_casting_machine():
    assert executed_keywords(card("Night Clubber"))["blitz"].startswith("machines/casting.py")
    assert executes("Blitz") or "blitz" in executed_keywords(card("Night Clubber"))


@pytest.mark.parametrize(
    "name",
    ["Pugnacious Pugilist", "Night Clubber", "Girder Goons", "Caldaia Strongarm", "Mayhem Patrol"],
)
def test_the_blitz_keyword_clause_reads_handled(name):
    (clause,) = [
        c for c in card_support(card(name)).clauses if c.kind == "keyword" and c.text == "Blitz"
    ]
    assert clause.outcome == "handled"


@pytest.mark.parametrize(
    "name", ["Night Clubber", "Girder Goons", "Caldaia Strongarm", "Mayhem Patrol"]
)
def test_the_proof_blitz_printings_read_handled_on_every_clause(name):
    support = card_support(card(name))
    assert support.status == "handled", [
        (c.text, c.outcome) for c in support.clauses if c.outcome != "handled"
    ]
