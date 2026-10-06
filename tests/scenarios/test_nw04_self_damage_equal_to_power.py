"""A targeted creature deals damage equal to its power to itself, with riders,
and the two "and to its controller" / "and X damage to itself" pairings.

- Wisecrack: "Target creature deals damage equal to its power to itself. If
  that creature is attacking, Wisecrack deals 2 damage to that creature's
  controller."
- Cut Propulsion: "Target creature deals damage to itself equal to its power.
  If that creature has flying, it deals twice that much damage to itself
  instead."
- Justice Strike (proof printing, the other word order): "Target creature
  deals damage to itself equal to its power."
- Self-Destruct: "Target creature you control deals X damage to any other
  target and X damage to itself, where X is its power."
- Neonate's Rush: "This spell costs {1} less to cast if you control a Vampire.
  Neonate's Rush deals 1 damage to target creature and 1 damage to its
  controller. Draw a card."

Rules verified with `mise run rules:find`:

- **CR 608.2c** - instructions in the order written; a later "instead"
  modifies the earlier instruction (one damage event of the doubled amount),
  and an "if" rider is checked as it is reached, on resolution.
- **CR 608.2h** - power read as the damage is dealt; "its controller" of a
  creature that has left is its last known information.
- **CR 608.2b** - an illegal target is not affected; Self-Destruct's biter
  still damages itself when only its other target is gone.
- **CR 508.1k/506.4** - an attacking creature stays attacking until removed
  from combat.
- **CR 120.3a/120.3e/120.3f** - damage to a player and a creature; lifelink.
- **CR 115.4** - "any other target" may be a creature, player,
  planeswalker or battle, but not the object already chosen (CR 115.3).
- **CR 601.2f** - cost reductions apply as the total cost is determined.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _notices(scenario) -> list[object]:
    game = scenario.game
    found: list[object] = list(game.continuous_effects.layer_notices)
    for name in type(game).model_fields:
        if name.endswith("_notices"):
            found.extend(getattr(game, name))
    return found


def _board(spell, lands, mine=(), theirs=(), *, library=()) -> Scenario:
    scenario = (
        Scenario()
        .player("alice", hand=[spell], battlefield=[*lands, *mine], library=list(library))
        .player("bob", battlefield=list(theirs), life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast(scenario, spell, lands, targets):
    sources = scenario.untapped_sources(*lands, username="alice")
    scenario.cast_and_resolve(spell, *sources, username="alice", targets=targets)


def _on_stack(scenario, spell, lands, targets):
    sources = scenario.untapped_sources(*lands, username="alice")
    return scenario.cast_onto_stack(spell, *sources, username="alice", targets=targets)


# -- Wisecrack -----------------------------------------------------------------

WISECRACK = ("Mountain",) * 3


def test_wisecrack_on_a_creature_not_attacking_hurts_only_the_creature():
    scenario = _board("Wisecrack", WISECRACK, theirs=("Giant Spider",))
    spider = scenario.creature("Giant Spider", "bob")
    _cast(scenario, "Wisecrack", WISECRACK, [spider])

    assert spider.damage == 2
    assert scenario.player("bob").life == 20
    assert _notices(scenario) == []


def test_wisecrack_on_an_attacking_creature_also_hits_its_controller():
    scenario = _board("Wisecrack", WISECRACK, mine=("Giant Spider",))
    spider = scenario.creature("Giant Spider", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(spider)
    _cast(scenario, "Wisecrack", WISECRACK, [spider])

    assert spider.damage == 2
    assert scenario.player("alice").life == 18  # the attacker's controller
    assert scenario.player("bob").life == 20
    assert _notices(scenario) == []


def test_wisecrack_attacking_creature_of_the_opponent_hits_the_opponent():
    """Cast on bob's turn at bob's attacker: "that creature's controller" is
    bob, not the caster."""
    scenario = (
        Scenario()
        .player("bob", battlefield=["Giant Spider"], life=20)
        .player("alice", hand=["Wisecrack"], battlefield=list(WISECRACK))
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    attacker = scenario.creature("Giant Spider", "bob")
    scenario.attack_with(attacker)
    scenario.pass_priority("bob")
    _cast(scenario, "Wisecrack", WISECRACK, [attacker])

    assert attacker.damage == 2
    assert scenario.player("bob").life == 18
    assert scenario.player("alice").life == 20


def test_wisecrack_target_gone_does_nothing():
    scenario = _board("Wisecrack", WISECRACK, mine=("Giant Spider",))
    spider = scenario.creature("Giant Spider", "alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(spider)
    _on_stack(scenario, "Wisecrack", WISECRACK, [spider])
    scenario.game.return_to_hand(spider)
    scenario.pass_until_resolved()

    assert scenario.player("alice").life == 20


# -- Cut Propulsion ------------------------------------------------------------

CUT = ("Mountain",) * 3


def test_cut_propulsion_without_flying_deals_power_once():
    scenario = _board("Cut Propulsion", CUT, theirs=("Giant Spider",))
    spider = scenario.creature("Giant Spider", "bob")
    _cast(scenario, "Cut Propulsion", CUT, [spider])

    assert spider.damage == 2
    assert _notices(scenario) == []


def test_cut_propulsion_with_flying_deals_twice_its_power_instead():
    scenario = _board("Cut Propulsion", CUT, theirs=("Serra Angel",))
    angel = scenario.creature("Serra Angel", "bob")
    _cast(scenario, "Cut Propulsion", CUT, [angel])

    assert angel.zone is Zone.GRAVEYARD


def test_cut_propulsion_flying_lifelink_gains_the_doubled_amount():
    """CR 120.3f: the doubled damage is the damage dealt, so lifelink gains it."""
    scenario = _board("Cut Propulsion", CUT, theirs=("Vampire Nighthawk",))
    nighthawk = scenario.creature("Vampire Nighthawk", "bob")
    _cast(scenario, "Cut Propulsion", CUT, [nighthawk])

    # One event of 2 x 2, not 2 then 4 more: lifelink gains exactly 4.
    assert scenario.player("bob").life == 24
    assert nighthawk.zone is Zone.GRAVEYARD


def test_justice_strike_reads_the_other_word_order():
    """Proof printing for the shared reader."""
    lands = ("Mountain", "Plains")
    scenario = _board("Justice Strike", lands, theirs=("Giant Spider",))
    spider = scenario.creature("Giant Spider", "bob")
    _cast(scenario, "Justice Strike", lands, [spider])

    assert spider.damage == 2
    assert _notices(scenario) == []


# -- Self-Destruct -------------------------------------------------------------

DESTRUCT = ("Mountain", "Mountain")


def test_self_destruct_hits_the_other_target_and_itself():
    scenario = _board("Self-Destruct", DESTRUCT, mine=("Giant Spider",), theirs=("Watchwolf",))
    spider = scenario.creature("Giant Spider", "alice")
    wolf = scenario.creature("Watchwolf", "bob")
    _cast(scenario, "Self-Destruct", DESTRUCT, [spider, wolf])

    assert wolf.damage == 2
    assert spider.damage == 2
    assert _notices(scenario) == []


def test_self_destruct_at_a_player():
    scenario = _board("Self-Destruct", DESTRUCT, mine=("Giant Spider",))
    spider = scenario.creature("Giant Spider", "alice")
    _cast(scenario, "Self-Destruct", DESTRUCT, [spider, "bob"])

    assert scenario.player("bob").life == 18
    assert spider.damage == 2


def test_self_destruct_other_target_gone_still_damages_itself():
    scenario = _board("Self-Destruct", DESTRUCT, mine=("Giant Spider",), theirs=("Watchwolf",))
    spider = scenario.creature("Giant Spider", "alice")
    wolf = scenario.creature("Watchwolf", "bob")
    _on_stack(scenario, "Self-Destruct", DESTRUCT, [spider, wolf])
    scenario.game.return_to_hand(wolf)
    scenario.pass_until_resolved()

    assert spider.damage == 2


def test_self_destruct_biter_gone_deals_nothing():
    scenario = _board("Self-Destruct", DESTRUCT, mine=("Giant Spider",), theirs=("Watchwolf",))
    spider = scenario.creature("Giant Spider", "alice")
    wolf = scenario.creature("Watchwolf", "bob")
    _on_stack(scenario, "Self-Destruct", DESTRUCT, [spider, wolf])
    scenario.game.return_to_hand(spider)
    scenario.pass_until_resolved()

    assert wolf.damage == 0


def test_self_destruct_cannot_name_its_biter_as_the_other_target():
    scenario = _board("Self-Destruct", DESTRUCT, mine=("Giant Spider",))
    spider = scenario.creature("Giant Spider", "alice")
    with pytest.raises(ValueError):
        scenario.cast("Self-Destruct", "alice", targets=[spider, spider])


# -- Neonate's Rush ------------------------------------------------------------

RUSH = ("Mountain",) * 3


def test_neonates_rush_damages_the_creature_and_its_controller_then_draws():
    scenario = _board("Neonate's Rush", RUSH, theirs=("Hill Giant",), library=("Forest",))
    giant = scenario.creature("Hill Giant", "bob")
    hand_before = len(scenario.player("alice").hand)
    _cast(scenario, "Neonate's Rush", RUSH, [giant])

    assert giant.damage == 1
    assert scenario.player("bob").life == 19
    assert len(scenario.player("alice").hand) == hand_before  # cast one, drew one
    assert _notices(scenario) == []


def test_neonates_rush_on_your_own_creature_damages_you():
    scenario = _board("Neonate's Rush", RUSH, mine=("Hill Giant",), library=("Forest",))
    giant = scenario.creature("Hill Giant", "alice")
    _cast(scenario, "Neonate's Rush", RUSH, [giant])

    assert scenario.player("alice").life == 19
    assert scenario.player("bob").life == 20


def test_neonates_rush_kills_a_one_toughness_creature_and_still_hits_its_controller():
    """CR 608.2h: "its controller" is still read for the creature it just
    damaged (state-based actions have not run yet, and would not matter)."""
    scenario = _board("Neonate's Rush", RUSH, theirs=("Raging Goblin",), library=("Forest",))
    goblin = scenario.creature("Raging Goblin", "bob")
    _cast(scenario, "Neonate's Rush", RUSH, [goblin])
    scenario.state_based_actions()

    assert goblin.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 19


def test_neonates_rush_target_gone_does_not_resolve_and_draws_nothing():
    scenario = _board("Neonate's Rush", RUSH, theirs=("Hill Giant",), library=("Forest",))
    giant = scenario.creature("Hill Giant", "bob")
    _on_stack(scenario, "Neonate's Rush", RUSH, [giant])
    hand_before = len(scenario.player("alice").hand)
    scenario.game.return_to_hand(giant)
    scenario.pass_until_resolved()

    assert scenario.player("bob").life == 20
    assert len(scenario.player("alice").hand) == hand_before


def test_neonates_rush_costs_one_less_with_a_vampire():
    scenario = _board(
        "Neonate's Rush",
        ("Mountain", "Mountain"),
        mine=("Vampire Nighthawk",),
        theirs=("Hill Giant",),
        library=("Forest",),
    )
    giant = scenario.creature("Hill Giant", "bob")
    casting = scenario.cast("Neonate's Rush", "alice", targets=[giant])
    payment = casting.begin_paying()
    assert str(payment.cost) == "{1}{R}"
    scenario.pay_with(payment, *scenario.untapped_sources("Mountain", "Mountain", username="alice"))
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()

    assert giant.damage == 1
    assert scenario.player("bob").life == 19
