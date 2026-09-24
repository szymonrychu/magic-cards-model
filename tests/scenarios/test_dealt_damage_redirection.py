"""A creature dealt damage deals that much damage onward.

Screaming Nemesis: "Whenever this creature is dealt damage, it deals that much
damage to any other target. If a player is dealt damage this way, they can't
gain life for the rest of the game." Boros Reckoner (Modern, Pioneer; oracle
text and legality checked against Scryfall on 2026-09-23, in no deck) prints
the same trigger with "any target" and no rider: "Whenever this creature is
dealt damage, it deals that much damage to any target."

- "That much" is the damage actually dealt. Prevented damage is never dealt
  (CR 615.6), so a prevention shield (CR 615.7) shrinks the amount, and a
  fully prevented hit is no trigger event at all (CR 603.2).
- "Any other target" is CR 115.4's "another target": the source can't be
  chosen. Plain "any target" can choose the source itself.
- It is the creature, as it last existed, that deals the damage (CR 608.2h),
  so the trigger still resolves when the damage that caused it also killed it.
- "If a player is dealt damage this way" reads what the damage actually did:
  a player whose damage was all prevented was not dealt any.
- "For the rest of the game" is a stated duration on an effect of a resolved
  ability (CR 611.2a). It does not end with the turn or with Nemesis, and
  it is persisted game state, so it survives an encode/decode round trip.
  "Can't gain life" wins over any instruction to gain (CR 101.2, CR 119.7).

Every CR number in this file was read in full with `mise run rules:find`:
CR 101.2, CR 115.4, CR 119.7, CR 603.2, CR 608.2h, CR 611.2a, CR 615.6,
CR 615.7.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Game, Zone
from tests.scenarios.harness import Scenario


def _nemesis_board(**alice: list[str]) -> Scenario:
    battlefield = ["Screaming Nemesis", "Mountain", "Mountain", *alice.pop("battlefield", [])]
    return (
        Scenario()
        .player(
            "alice", battlefield=battlefield, hand=alice.pop("hand", ["Lightning Bolt"]), **alice
        )
        .player(
            "bob",
            battlefield=["Grizzly Bears", "Plains", "Mountain"],
            hand=["Lightning Helix"],
            library=["Plains", "Plains"],
        )
    )


def _bolt_own(scenario, creature_name: str = "Screaming Nemesis") -> None:
    creature = scenario.creature(creature_name, "alice")
    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[creature]
    )
    scenario.game.put_triggers_on_stack()


def test_nemesis_deals_the_damage_it_was_dealt_to_a_player_and_locks_their_life_gain() -> None:
    scenario = _nemesis_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    scenario.choose_trigger_targets("Screaming Nemesis", ["bob"])

    _bolt_own(scenario)
    scenario.resolve_top()

    assert bob.life == 17
    assert bob.cannot_gain_life is True
    assert scenario.player("alice").cannot_gain_life is False


def test_nemesis_still_resolves_after_the_damage_killed_it() -> None:
    """CR 608.2h: Bolt's 3 kills the 3/3 Nemesis before its trigger
    resolves; the trigger still deals 3, as Nemesis last existed."""
    scenario = _nemesis_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    nemesis = scenario.creature("Screaming Nemesis", "alice")
    scenario.choose_trigger_targets("Screaming Nemesis", ["bob"])

    _bolt_own(scenario)
    scenario.state_based_actions()
    assert nemesis.zone is Zone.GRAVEYARD
    scenario.resolve_top()

    assert scenario.player("bob").life == 17


def test_nemesis_cannot_target_itself() -> None:
    """CR 115.4: "any other target" excludes the source."""
    scenario = _nemesis_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    nemesis = scenario.creature("Screaming Nemesis", "alice")

    assert scenario.game.why_cannot_target_with_trigger("Screaming Nemesis", [nemesis])
    with pytest.raises(ValueError):
        scenario.choose_trigger_targets("Screaming Nemesis", [nemesis])
    assert scenario.game.why_cannot_target_with_trigger("Screaming Nemesis", ["bob"]) is None


def test_prevented_damage_shrinks_that_much() -> None:
    """CR 615.6/615.7: Bandage prevents 1 of Bolt's 3, so Nemesis is dealt 2
    and deals 2."""
    scenario = _nemesis_board(
        battlefield=["Plains"], hand=["Bandage", "Lightning Bolt"], library=["Plains"]
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    nemesis = scenario.creature("Screaming Nemesis", "alice")
    scenario.cast_and_resolve("Bandage", *scenario.untapped_sources("Plains"), targets=[nemesis])
    scenario.choose_trigger_targets("Screaming Nemesis", ["bob"])

    _bolt_own(scenario)
    scenario.resolve_top()

    assert nemesis.damage == 2
    assert scenario.player("bob").life == 18


def test_a_player_whose_damage_is_all_prevented_is_not_locked() -> None:
    """ "If a player is dealt damage this way": Shock through a Bandage deals
    Nemesis 1; Nemesis's 1 to bob is prevented by a second Bandage on bob, so
    bob was dealt no damage and can still gain life."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Screaming Nemesis", "Mountain", "Plains", "Plains"],
            hand=["Bandage", "Bandage", "Shock"],
            library=["Plains", "Plains"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    nemesis = scenario.creature("Screaming Nemesis", "alice")
    first, second = scenario.untapped_sources("Plains", "Plains")
    scenario.cast_and_resolve("Bandage", first, targets=["bob"])
    scenario.cast_and_resolve("Bandage", second, targets=[nemesis])
    scenario.choose_trigger_targets("Screaming Nemesis", ["bob"])

    scenario.cast_and_resolve("Shock", *scenario.untapped_sources("Mountain"), targets=[nemesis])
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    bob = scenario.player("bob")
    assert bob.life == 20
    assert bob.cannot_gain_life is False


def test_fully_prevented_damage_to_nemesis_is_no_trigger() -> None:
    """CR 615.6: prevented damage never happens, so there is nothing for
    "is dealt damage" to match (CR 603.2)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Screaming Nemesis", "Plains"],
            hand=["Bandage"],
            library=["Plains"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    nemesis = scenario.creature("Screaming Nemesis", "alice")
    scenario.cast_and_resolve("Bandage", *scenario.untapped_sources("Plains"), targets=[nemesis])

    scenario.game.deal_damage(nemesis, 1)
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []


def test_damage_redirected_to_a_creature_locks_nobody() -> None:
    scenario = _nemesis_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.choose_trigger_targets("Screaming Nemesis", [bears])

    _bolt_own(scenario)
    scenario.resolve_top()
    scenario.state_based_actions()

    assert bears.zone is Zone.GRAVEYARD
    assert scenario.player("bob").cannot_gain_life is False
    assert scenario.player("alice").cannot_gain_life is False


def test_combat_damage_to_nemesis_is_redirected_too() -> None:
    """Grizzly Bears blocks Nemesis: 2 combat damage to Nemesis, 2 onward."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Screaming Nemesis"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    nemesis = scenario.creature("Screaming Nemesis", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.choose_trigger_targets("Screaming Nemesis", ["bob"])

    scenario.attack_with(nemesis)
    scenario.block(nemesis, bears)
    scenario.combat_damage()
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert scenario.player("bob").life == 18
    assert scenario.player("bob").cannot_gain_life is True


def _to_bobs_main_phase(scenario) -> None:
    while not (scenario.turn.active_player == "bob" and scenario.step is Step.PRECOMBAT_MAIN):
        scenario.advance()


def test_the_lock_lasts_for_the_rest_of_the_game() -> None:
    """CR 611.2a: the stated duration outlives the turn and Nemesis itself.
    On bob's own next turn, with Nemesis dead, Lightning Helix still deals
    its 3 to alice but gains bob nothing (CR 101.2, CR 119.7)."""
    scenario = _nemesis_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    nemesis = scenario.creature("Screaming Nemesis", "alice")
    scenario.choose_trigger_targets("Screaming Nemesis", ["bob"])
    _bolt_own(scenario)
    scenario.resolve_top()
    scenario.state_based_actions()
    assert nemesis.zone is Zone.GRAVEYARD

    _to_bobs_main_phase(scenario)
    bob = scenario.player("bob")
    life_before = bob.life
    scenario.cast_and_resolve(
        "Lightning Helix",
        *scenario.untapped_sources("Plains", "Mountain", username="bob"),
        username="bob",
        targets=["alice"],
    )

    assert bob.life == life_before
    assert scenario.player("alice").life == 17


def test_the_lock_survives_an_encode_decode_round_trip() -> None:
    scenario = _nemesis_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.choose_trigger_targets("Screaming Nemesis", ["bob"])
    _bolt_own(scenario)
    scenario.resolve_top()

    decoded = Game.model_validate(scenario.game.model_dump(mode="json"))
    bob = decoded.player("bob")

    assert bob.cannot_gain_life is True
    assert bob.gain_life(5) == bob.life == 17


# -- proof: Boros Reckoner, "any target" and no rider


def test_boros_reckoner_deals_that_much_to_any_target_without_a_lock() -> None:
    scenario = (
        Scenario()
        .player("alice", battlefield=["Boros Reckoner", "Mountain"], hand=["Lightning Bolt"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    reckoner = scenario.creature("Boros Reckoner", "alice")
    scenario.choose_trigger_targets("Boros Reckoner", ["bob"])

    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[reckoner]
    )
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    bob = scenario.player("bob")
    assert bob.life == 17
    assert bob.cannot_gain_life is False


def test_boros_reckoner_may_target_itself() -> None:
    """Plain "any target" (CR 115.4) does not exclude the source: Shock deals
    Reckoner 2, and the trigger deals those 2 back to Reckoner itself - 4
    marked on a 3/3, so it dies to the next state-based action check."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Boros Reckoner", "Mountain"], hand=["Shock"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    reckoner = scenario.creature("Boros Reckoner", "alice")
    scenario.choose_trigger_targets("Boros Reckoner", [reckoner])

    scenario.cast_and_resolve("Shock", *scenario.untapped_sources("Mountain"), targets=[reckoner])
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    scenario.state_based_actions()
    assert reckoner.zone is Zone.GRAVEYARD, "Shock's 2 alone leaves a 3/3 alive"
    assert scenario.player("bob").life == 20
