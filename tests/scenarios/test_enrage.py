"""Scenario: Enrage (CR 207.2c ability word - "Enrage — Whenever this
creature is dealt damage, [effect]", no rules meaning of its own beyond
tying together cards that share the trigger).

Bellowing Aegisaur and Ranging Raptors, the pool's own Enrage printings, are
already covered by `test_damage_recipient_triggers.py` and
`test_fra_s8_dealt_damage_search.py`. This file is the off-pool proof the
requirement names: **Needletooth Raptor** - "Enrage — Whenever this creature
is dealt damage, it deals 5 damage to target creature an opponent controls."
- exercising the trigger itself rather than the clause after it, on every
shape CR 120.1-120.3 and CR 603.2g distinguish:

- Combat damage (CR 510) and noncombat damage (a direct-damage spell) both
  fire it - "is dealt damage" carries neither word, so nothing filters
  either kind out (`machines/triggers.py`'s own `DEALS_DAMAGE`/passive-voice
  reading).
- Zero damage does not fire it: "deals `N` damage" with `N` = 0 is not an
  event at all (CR 119.8, and `Game.deal_damage`'s own "zero damage is not
  damage dealt").
- Damage a prevention effect reduces to zero does not fire it either (CR
  615.1a: "a prevented event deals zero damage rather than dealing damage
  and undoing it") - built directly with `PreventionShield`, the same way
  `test_prevention_effects.py` proves CR 615 in isolation.

The Marvel Hulks print riders after the same trigger (C02, MSH):

- "If he's attacking, untap him and there is an additional combat phase after
  this phase." (Bruce Banner // The Incredible Hulk) - a condition on the
  source's own attacking status (CR 506.4), CR 701.26b's untap and CR 500.8's
  additional combat phase. The rider is printed on no other card; Snapping
  Sailback's plain "Enrage - Whenever this creature is dealt damage, put a
  +1/+1 counter on it." is the second printing of the trigger and counter,
  and Red Hulk's differently worded rider is the second listed card.
- "When you do, he deals damage equal to the number of +1/+1 counters on him
  to any other target." (Red Hulk) - CR 603.12's reflexive trigger, created
  only once the counter really was put (it targets as it goes on the stack,
  CR 603.3d, and "other" leaves Red Hulk himself out).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.game import PreventionShield, ShieldKind
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario


def _board() -> Scenario:
    return (
        Scenario()
        .player("alice", battlefield=["Needletooth Raptor"])
        .player("bob", life=20, battlefield=["Grizzly Bears", "Hill Giant"])
    )


def test_off_pool_needletooth_raptor_enrages_on_combat_damage():
    scenario = _board().build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    raptor = scenario.creature("Needletooth Raptor", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.choose_trigger_targets("Needletooth Raptor", [bears])

    scenario.attack_with(raptor)
    scenario.block(raptor, bears)
    scenario.combat_damage()
    scenario.pass_until_resolved()  # the Enrage trigger

    assert raptor.zone is Zone.GRAVEYARD, "the Bears' own 2 power is lethal for a 2/2"
    assert bears.zone is Zone.GRAVEYARD, "2 toughness, 5 damage from the Enrage trigger"


def test_off_pool_needletooth_raptor_enrages_on_noncombat_damage():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    raptor = scenario.creature("Needletooth Raptor", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.choose_trigger_targets("Needletooth Raptor", [bears])

    scenario.game.deal_damage(raptor, 1)
    scenario.pass_until_resolved()

    assert bears.zone is Zone.GRAVEYARD, "the Enrage trigger's own 5 damage is lethal"


def test_zero_damage_does_not_enrage_needletooth_raptor():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    raptor = scenario.creature("Needletooth Raptor", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")

    dealt = scenario.game.deal_damage(raptor, 0)

    assert dealt == 0
    assert scenario.pending_triggers == []
    assert scenario.game.stack_is_empty
    assert bears.zone is Zone.BATTLEFIELD


def test_prevented_damage_does_not_enrage_needletooth_raptor():
    """CR 615.1a: a prevention shield reduces what is *dealt*, not what
    merely would have been - the trigger's own premise never arises."""
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    raptor = scenario.creature("Needletooth Raptor", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.game.create_prevention_shield(
        PreventionShield(
            kind=ShieldKind.ALL,
            label="prevent all damage that would be dealt to Needletooth Raptor this turn",
            controller="alice",
            card_id=raptor.id,
        )
    )

    dealt = scenario.game.deal_damage(raptor, 3)

    assert dealt == 0
    assert scenario.pending_triggers == []
    assert scenario.game.stack_is_empty
    assert bears.zone is Zone.BATTLEFIELD


# -- the Marvel Hulks ---------------------------------------------------------


def _hulk_board(*, opponent=None, manual=False):
    scenario = Scenario()
    if manual:
        scenario = scenario.manual_turn_based_actions()
    scenario = (
        scenario.player("alice", battlefield=["Bruce Banner // The Incredible Hulk"])
        .player("bob", **(opponent or {}))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hulk = scenario.creature("Bruce Banner", "alice")
    hulk.transform()
    assert hulk.name == "The Incredible Hulk"
    return scenario, hulk


def test_hulk_dealt_damage_outside_combat_gets_a_counter_only():
    scenario, hulk = _hulk_board()
    scenario.game.deal_damage(hulk, 3, source=scenario.creature("The Incredible Hulk", "alice"))
    scenario.pass_until_resolved()

    assert hulk.counter_count("+1/+1") == 1
    assert scenario.step is Step.PRECOMBAT_MAIN
    assert scenario.game.power_of(hulk) == 9


def test_hulk_dealt_damage_while_attacking_untaps_and_adds_a_combat_phase():
    scenario, hulk = _hulk_board(opponent={"battlefield": ["Hill Giant"]}, manual=True)
    giant = scenario.creature("Hill Giant", "bob")
    scenario.advance()
    scenario.advance()
    scenario.attack_with(hulk)
    assert hulk.tapped
    scenario.advance()
    scenario.block(hulk, giant)
    scenario.advance()
    scenario.combat_damage()
    scenario.pass_until_resolved()

    assert hulk.counter_count("+1/+1") == 1
    assert not hulk.tapped, "untapped by the enrage rider"
    step = scenario.advance()
    while step is not Step.DECLARE_ATTACKERS and step is not Step.POSTCOMBAT_MAIN:
        step = scenario.advance()
    assert step is Step.DECLARE_ATTACKERS, "the additional combat phase (CR 500.8)"


def test_each_enrage_trigger_adds_its_own_counter():
    scenario, hulk = _hulk_board()
    scenario.game.deal_damage(hulk, 1, source=hulk)
    scenario.pass_until_resolved()
    scenario.game.deal_damage(hulk, 1, source=hulk)
    scenario.pass_until_resolved()
    assert hulk.counter_count("+1/+1") == 2


def test_snapping_sailback_gets_a_counter_when_dealt_damage():
    scenario = Scenario().player("alice", battlefield=["Snapping Sailback"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sailback = scenario.creature("Snapping Sailback", "alice")
    scenario.game.deal_damage(sailback, 2, source=sailback)
    scenario.pass_until_resolved()
    assert sailback.counter_count("+1/+1") == 1


# -- Red Hulk ------------------------------------------------------------------------


def test_red_hulk_deals_damage_equal_to_his_counters_to_another_target():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Red Hulk"])
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    red_hulk = scenario.creature("Red Hulk", "alice")
    red_hulk.add_counters("+1/+1", 2)
    scenario.game.deal_damage(red_hulk, 1, source=scenario.creature("Hill Giant", "bob"))
    scenario.will_choose_targets("bob", source="Red Hulk")
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()

    assert red_hulk.counter_count("+1/+1") == 3
    assert scenario.player("bob").life == 17


def test_red_hulk_can_hit_a_creature():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Red Hulk"])
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    red_hulk = scenario.creature("Red Hulk", "alice")
    giant = scenario.creature("Hill Giant", "bob")
    red_hulk.add_counters("+1/+1", 2)
    scenario.game.deal_damage(red_hulk, 1, source=giant)
    scenario.will_choose_targets(giant, source="Red Hulk")
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    scenario.state_based_actions()

    assert giant.zone is Zone.GRAVEYARD, "3 damage to a 3/3"


def test_red_hulk_cannot_target_himself():
    """ "any other target": CR 115.10 - the source is not a legal target, so
    naming it is refused."""
    scenario = Scenario().player("alice", battlefield=["Red Hulk"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    red_hulk = scenario.creature("Red Hulk", "alice")
    scenario.game.deal_damage(red_hulk, 1, source=red_hulk)
    scenario.will_choose_targets(red_hulk, source="Red Hulk")
    with pytest.raises(ValueError):
        scenario.pass_until_resolved()
        scenario.pass_until_resolved()


def test_red_hulk_killed_by_the_damage_puts_no_counter_and_deals_nothing():
    """CR 603.12: "When you do" triggers only if the counter was put; a Red
    Hulk that died to the damage is no longer there to take it."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Red Hulk"])
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    red_hulk = scenario.creature("Red Hulk", "alice")
    scenario.game.deal_damage(red_hulk, 7, source=scenario.creature("Hill Giant", "bob"))
    scenario.state_based_actions()
    assert red_hulk.zone is Zone.GRAVEYARD
    scenario.pass_until_resolved()

    assert scenario.player("bob").life == 20
    assert scenario.stack_names() == []


@pytest.mark.parametrize(
    "name", ["Bruce Banner // The Incredible Hulk", "Red Hulk", "Snapping Sailback"]
)
def test_every_clause_is_handled(name):
    for clause in card_support(card(name)).clauses:
        assert clause.outcome == "handled", (name, clause.text, clause.outcome)
