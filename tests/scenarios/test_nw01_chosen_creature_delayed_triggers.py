"""A turn-scoped delayed triggered ability bound to one chosen creature:
"Whenever that creature <event> this turn, <effect>".

- **Hunter's Insight** - "Choose target creature you control. Whenever that
  creature deals combat damage to a player or planeswalker this turn, draw
  that many cards."
- **Arcbond** - "Choose target creature. Whenever that creature is dealt
  damage this turn, it deals that much damage to each other creature and
  each player."
- **Niko Aris** (proof printing, not a listed card) - "+1: Up to one target
  creature you control can't be blocked this turn. Whenever that creature
  deals damage this turn, return it to its owner's hand." The same
  "Whenever that creature ... this turn" sentence, after a targeted clause
  rather than a "Choose" opener, on a loyalty ability rather than a spell.

Rules, each looked up with `mise run rules:find` in the session that wrote
this file:

- **CR 115.1a** - the target is chosen as the spell is cast; the "Choose"
  opener names it, the later "that creature" refers back to it.
- **CR 603.7a** - resolving the spell creates the delayed triggered ability.
- **CR 603.7c** - the delayed ability refers to that particular object; a
  different creature, or the same card after it left and came back, is not
  it (CR 400.7).
- **CR 608.2h** - "it deals that much damage" uses the creature as it last
  existed when it has already died to the damage that triggered it.
- **CR 120.3** - the damage results (lifelink, deathtouch) follow the
  source, which is the creature, not the spell.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

# --------------------------------------------------------------------------
# Hunter's Insight
# --------------------------------------------------------------------------


def _insight_board(*, alice_battlefield: list[str] | None = None) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Hunter's Insight"],
            battlefield=["Forest", "Forest", "Forest", "Hill Giant", "Grizzly Bears"]
            + (alice_battlefield or []),
            library=["Island"] * 8,
        )
        .player("bob", battlefield=["Savannah Lions"], life=20)
    )


def _cast_insight(scenario, target) -> None:
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Hunter's Insight", auto=True, targets=[target])


def test_hunters_insight_draws_as_many_cards_as_the_combat_damage_dealt_to_a_player():
    scenario = _insight_board().build()
    giant = scenario.creature("Hill Giant", "alice")
    _cast_insight(scenario, giant)
    hand_before = len(scenario.player("alice").hand)

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(giant)
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert scenario.player("bob").life == 17
    assert len(scenario.player("alice").hand) == hand_before + 3


def test_hunters_insight_ignores_combat_damage_from_any_other_creature():
    """CR 603.7c: the ability is about the chosen creature only - Grizzly
    Bears connecting draws nothing."""
    scenario = _insight_board().build()
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    _cast_insight(scenario, giant)
    hand_before = len(scenario.player("alice").hand)

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    scenario.no_blocks()
    scenario.combat_damage()
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []
    assert scenario.player("bob").life == 18
    assert len(scenario.player("alice").hand) == hand_before


def test_hunters_insight_ignores_combat_damage_dealt_to_a_blocking_creature():
    """ "to a player or planeswalker": damage to a blocker is not it."""
    scenario = _insight_board().build()
    giant = scenario.creature("Hill Giant", "alice")
    lions = scenario.creature("Savannah Lions", "bob")
    _cast_insight(scenario, giant)
    hand_before = len(scenario.player("alice").hand)

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(giant)
    scenario.block(giant, lions)
    scenario.combat_damage()
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []
    assert lions.zone is Zone.GRAVEYARD
    assert len(scenario.player("alice").hand) == hand_before


def test_hunters_insight_ignores_noncombat_damage_from_the_chosen_creature():
    scenario = _insight_board().build()
    giant = scenario.creature("Hill Giant", "alice")
    _cast_insight(scenario, giant)
    hand_before = len(scenario.player("alice").hand)

    scenario.game.deal_damage(scenario.player("bob"), 3, source=giant)
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []
    assert len(scenario.player("alice").hand) == hand_before


def test_hunters_insight_ends_with_the_turn():
    """ "this turn" (CR 603.7b's stated duration): next turn's combat damage
    from the same creature draws nothing."""
    scenario = _insight_board().build()
    giant = scenario.creature("Hill Giant", "alice")
    _cast_insight(scenario, giant)

    assert len(scenario.game.delayed_triggers.triggers) == 1
    scenario.game.delayed_triggers.expire_this_turn()
    assert scenario.game.delayed_triggers.triggers == []


def test_hunters_insight_cannot_choose_a_creature_an_opponent_controls():
    scenario = _insight_board().build()
    lions = scenario.creature("Savannah Lions", "bob")
    scenario.start_at(Step.PRECOMBAT_MAIN)

    with pytest.raises(ValueError):
        scenario.cast_and_resolve("Hunter's Insight", auto=True, targets=[lions])


def test_hunters_insight_does_nothing_when_the_creature_is_gone_before_it_resolves():
    """CR 608.2b: the only target is illegal, so the spell does not resolve
    and creates no delayed trigger."""
    scenario = _insight_board().build()
    giant = scenario.creature("Hill Giant", "alice")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_onto_stack("Hunter's Insight", auto=True, targets=[giant])
    scenario.game.destroy(giant)

    scenario.resolve_top()

    assert scenario.game.delayed_triggers.triggers == []


# --------------------------------------------------------------------------
# Arcbond
# --------------------------------------------------------------------------


def _arcbond_board(bob_battlefield: list[str]) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Arcbond", "Lightning Bolt"],
            battlefield=["Mountain", "Mountain", "Mountain", "Mountain", "Hill Giant"],
            life=20,
        )
        .player("bob", battlefield=bob_battlefield, life=20)
    )


def test_arcbond_creature_deals_the_damage_it_was_dealt_to_each_other_creature_and_player():
    scenario = _arcbond_board(["Indomitable Ancients", "Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ancients = scenario.creature("Indomitable Ancients", "bob")
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.cast_and_resolve("Arcbond", auto=True, targets=[ancients])

    scenario.cast_and_resolve("Lightning Bolt", auto=True, targets=[ancients])
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert ancients.damage == 3  # the Bolt only; it does not damage itself
    assert giant.zone is Zone.GRAVEYARD  # 3 damage on a 3/3
    assert bears.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 17
    assert scenario.player("bob").life == 17


def test_arcbond_creature_is_the_source_even_after_it_died_to_the_damage():
    """CR 608.2h / 120.3: Vampire Nighthawk dies to the Bolt, and as it last
    existed it deals 3 to each other creature and each player - lifelink
    gains bob that much for each, deathtouch kills Hill Giant."""
    scenario = _arcbond_board(["Vampire Nighthawk"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    nighthawk = scenario.creature("Vampire Nighthawk", "bob")
    giant = scenario.creature("Hill Giant", "alice")
    scenario.cast_and_resolve("Arcbond", auto=True, targets=[nighthawk])

    scenario.cast_and_resolve("Lightning Bolt", auto=True, targets=[nighthawk])
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert nighthawk.zone is Zone.GRAVEYARD
    assert giant.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 17
    # bob takes 3 and lifelink gains him 3 for each of the three damage events
    assert scenario.player("bob").life == 20 - 3 + 3 * 3


def test_arcbond_ignores_damage_dealt_to_another_creature():
    scenario = _arcbond_board(["Indomitable Ancients", "Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ancients = scenario.creature("Indomitable Ancients", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.cast_and_resolve("Arcbond", auto=True, targets=[ancients])

    scenario.cast_and_resolve("Lightning Bolt", auto=True, targets=[bears])
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []
    assert scenario.player("alice").life == 20


def test_arcbond_triggers_every_time_the_creature_is_dealt_damage_this_turn():
    scenario = _arcbond_board(["Indomitable Ancients"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ancients = scenario.creature("Indomitable Ancients", "bob")
    giant = scenario.creature("Hill Giant", "alice")
    scenario.cast_and_resolve("Arcbond", auto=True, targets=[ancients])

    for amount in (1, 2):
        scenario.game.deal_damage(ancients, amount, source=giant)
        scenario.game.put_triggers_on_stack()
        scenario.pass_until_resolved()

    assert scenario.player("alice").life == 17
    assert scenario.player("bob").life == 17
    assert giant.zone is Zone.GRAVEYARD  # 1 + 2 = 3 damage on a 3/3


def test_arcbond_no_longer_watches_a_creature_that_left_and_came_back():
    """CR 400.7 / 603.7c: the same card returning is a new object."""
    scenario = _arcbond_board(["Indomitable Ancients"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ancients = scenario.creature("Indomitable Ancients", "bob")
    giant = scenario.creature("Hill Giant", "alice")
    scenario.cast_and_resolve("Arcbond", auto=True, targets=[ancients])
    scenario.game.return_to_hand(ancients)
    returned = scenario.find("Indomitable Ancients", Zone.HAND, "bob")
    scenario.game.put_onto_battlefield(returned, "bob")
    back = scenario.creature("Indomitable Ancients", "bob")

    scenario.game.deal_damage(back, 2, source=giant)
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []
    assert scenario.player("alice").life == 20


# --------------------------------------------------------------------------
# Niko Aris +1 (proof printing): the same sentence after a targeted clause
# --------------------------------------------------------------------------


def test_niko_aris_returns_only_the_targeted_creature_when_it_deals_damage():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Niko Aris", "Hill Giant", "Grizzly Bears"])
        .player("bob", life=20)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    niko = scenario.find("Niko Aris", Zone.BATTLEFIELD, "alice")
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.activate(niko, index=0, targets=[giant])
    scenario.pass_until_resolved()

    scenario.game.deal_damage(scenario.player("bob"), 2, source=bears)
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == []

    scenario.game.deal_damage(scenario.player("bob"), 3, source=giant)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert scenario.find("Hill Giant", Zone.HAND, "alice") is not None
    assert bears.zone is Zone.BATTLEFIELD
