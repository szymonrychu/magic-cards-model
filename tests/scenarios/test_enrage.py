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
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.game import PreventionShield, ShieldKind

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
