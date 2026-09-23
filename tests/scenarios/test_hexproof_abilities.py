"""Hexproof against *abilities*, not only spells (CR 702.11b, CR 702.11d).

Verified this session with `mise run rules:find`:

- CR 702.11b: "'Hexproof' on a permanent means 'This permanent can't be the
  target of spells or abilities your opponents control.'"
- CR 702.11d: "'Hexproof from [quality]' on a permanent means 'This permanent
  can't be the target of [quality] spells your opponents control or abilities
  your opponents control from [quality] sources.'"
- CR 702.11f: "from [quality A] and from [quality B]" is two abilities.
- CR 702.11h: "Multiple instances of the same hexproof ability on the same
  permanent or player are redundant."
- CR 113.7 / CR 113.7a: the source of an ability is the object that generated
  it; once it has left its zone, its last known information is used.
- CR 608.2b: "If the source of an ability has left the zone it was in, its last
  known information is used during this process."

The check lives in one place (`Game.hexproof_refusal`, reached from
`TargetingProfile.check`, the candidate lists offered to a live
`CHOOSE_TARGETS` question, and `Game.legal_target`'s CR 608.2b recheck), so a
triggered ability, an activated ability and a spell are judged by the same
words.

Knight of Grace is CR 702.11d's shape ("Hexproof from black"); Gladecover
Scout is CR 702.11b's plain one; both are off-pool printings.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.triggers import TargetingNoticeKind
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

# -- Knight of Grace: hexproof from black ----------------------------------


def test_an_opponents_black_spell_cannot_target_knight_of_grace():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Fatal Push"], battlefield=["Swamp"])
        .player("bob", battlefield=["Knight of Grace"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    knight = scenario.creature("Knight of Grace", "bob")

    casting = scenario.cast("Fatal Push", username="alice")
    with pytest.raises(ValueError, match="hexproof from black"):
        casting.choose_targets([knight])


def test_an_opponents_non_black_spell_can_target_knight_of_grace():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .player("bob", battlefield=["Knight of Grace"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    knight = scenario.creature("Knight of Grace", "bob")

    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[knight]
    )
    assert knight.zone is Zone.GRAVEYARD


def test_its_controllers_own_black_spell_can_target_it():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Fatal Push"], battlefield=["Swamp", "Knight of Grace"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    knight = scenario.creature("Knight of Grace", "alice")

    scenario.cast_and_resolve("Fatal Push", *scenario.untapped_sources("Swamp"), targets=[knight])
    assert knight.zone is Zone.GRAVEYARD


def test_an_opponents_triggered_ability_from_a_black_permanent_cannot_target_it():
    """Ravenous Chupacabra is black: its "destroy target creature an opponent
    controls" is an ability from a black source (CR 702.11d)."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Ravenous Chupacabra"])
        .player("bob", battlefield=["Knight of Grace"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    knight = scenario.creature("Knight of Grace", "bob")
    scenario.put_onto_battlefield("Ravenous Chupacabra", "alice")

    with pytest.raises(ValueError, match="hexproof from black"):
        scenario.choose_trigger_targets("Ravenous Chupacabra", [knight])


def test_a_black_trigger_with_only_knight_to_target_is_removed():
    """Asked live, Knight of Grace is no candidate at all, so the mandatory
    target has no legal choice and CR 603.3d removes the trigger."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Ravenous Chupacabra"])
        .player("bob", battlefield=["Knight of Grace"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    knight = scenario.creature("Knight of Grace", "bob")
    scenario.put_onto_battlefield("Ravenous Chupacabra", "alice")
    scenario.game.put_triggers_on_stack()

    assert scenario.game.stack == []
    assert knight.zone is Zone.BATTLEFIELD
    assert any(
        notice.kind is TargetingNoticeKind.NO_LEGAL_TARGET
        for notice in scenario.game.targeting_notices
    )


def test_an_opponents_activated_ability_from_a_black_permanent_cannot_target_it():
    """Vampire Hexmage (black): "Sacrifice this creature: Remove all counters
    from target permanent." - refused at CR 602.2b's announcement."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Vampire Hexmage"])
        .player("bob", battlefield=["Knight of Grace"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    knight = scenario.creature("Knight of Grace", "bob")
    hexmage = scenario.creature("Vampire Hexmage", "alice")

    with pytest.raises(ValueError, match="hexproof from black"):
        scenario.activate(hexmage, sacrificing=[hexmage], targets=[knight])
    assert hexmage.zone is Zone.BATTLEFIELD


def test_its_controllers_own_black_ability_can_target_it():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Vampire Hexmage", "Knight of Grace"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    knight = scenario.creature("Knight of Grace", "alice")
    hexmage = scenario.creature("Vampire Hexmage", "alice")

    ability = scenario.activate(hexmage, sacrificing=[hexmage], targets=[knight])
    assert ability is not None
    assert ability.targets[0].card_id == knight.id


def test_an_opponents_ability_from_a_non_black_permanent_can_target_it():
    """Goblin Bombardment is red: "Sacrifice a creature: This enchantment deals
    1 damage to any target." - hexproof from black says nothing about it."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Goblin Bombardment", "Runeclaw Bear"])
        .player("bob", battlefield=["Knight of Grace"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    knight = scenario.creature("Knight of Grace", "bob")
    bombardment = scenario.find("Goblin Bombardment", Zone.BATTLEFIELD, "alice")
    fodder = scenario.creature("Runeclaw Bear", "alice")

    scenario.activate(bombardment, sacrificing=[fodder], targets=[knight])
    scenario.resolve_top()
    assert knight.damage == 1


def test_the_quality_of_an_ability_whose_source_has_left_is_its_last_known_information():
    """CR 113.7a / CR 608.2b: the Chupacabra trigger is on the stack aimed at
    a Grizzly Bears, and the Chupacabra itself is gone. Asked whether that
    ability could target Knight of Grace, the answer reads the source as it
    last existed - black - and refuses."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Ravenous Chupacabra"])
        .player("bob", battlefield=["Knight of Grace", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    knight = scenario.creature("Knight of Grace", "bob")
    bears = scenario.creature("Grizzly Bears", "bob")
    chupacabra = scenario.put_onto_battlefield("Ravenous Chupacabra", "alice")
    scenario.choose_trigger_targets("Ravenous Chupacabra", [bears])
    scenario.game.put_triggers_on_stack()
    (trigger,) = scenario.game.abilities_on_stack

    scenario.game.put_into_graveyard(chupacabra)

    refusal = scenario.game.hexproof_refusal(knight, "alice", trigger)
    assert refusal is not None and "hexproof from black" in refusal


def test_hexproof_from_black_is_one_ability_however_it_is_read():
    """CR 702.11h: Knight of Grace's quality list is "black", once."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice")
        .player("bob", battlefield=["Knight of Grace"])
        .build()
    )
    knight = scenario.creature("Knight of Grace", "bob")
    assert scenario.game.hexproof_abilities(knight) == (False, ["black"])


def test_hexproof_from_a_list_refuses_an_ability_from_each_listed_quality():
    """CR 702.11f: Nevinyrral's "from artifacts, creatures, and enchantments"
    refuses an ability from a creature (Ravenous Chupacabra) and one from an
    enchantment (Goblin Bombardment) alike."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Ravenous Chupacabra"],
            battlefield=["Goblin Bombardment", "Runeclaw Bear"],
        )
        .player("bob", battlefield=["Nevinyrral, Urborg Tyrant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    nevinyrral = scenario.creature("Nevinyrral, Urborg Tyrant", "bob")
    bombardment = scenario.find("Goblin Bombardment", Zone.BATTLEFIELD, "alice")
    fodder = scenario.creature("Runeclaw Bear", "alice")

    with pytest.raises(ValueError, match="hexproof from enchantments"):
        scenario.activate(bombardment, sacrificing=[fodder], targets=[nevinyrral])

    scenario.put_onto_battlefield("Ravenous Chupacabra", "alice")
    with pytest.raises(ValueError, match="hexproof from creatures"):
        scenario.choose_trigger_targets("Ravenous Chupacabra", [nevinyrral])


# -- Gladecover Scout: plain hexproof --------------------------------------


def test_an_opponents_triggered_ability_cannot_target_a_hexproof_creature():
    """CR 702.11b: Ravenous Chupacabra's ETB cannot name Gladecover Scout."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Ravenous Chupacabra"])
        .player("bob", battlefield=["Gladecover Scout"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scout = scenario.creature("Gladecover Scout", "bob")
    scenario.put_onto_battlefield("Ravenous Chupacabra", "alice")

    with pytest.raises(ValueError, match="has hexproof"):
        scenario.choose_trigger_targets("Ravenous Chupacabra", [scout])


def test_a_trigger_with_only_a_hexproof_creature_to_target_is_removed():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Ravenous Chupacabra"])
        .player("bob", battlefield=["Gladecover Scout"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scout = scenario.creature("Gladecover Scout", "bob")
    scenario.put_onto_battlefield("Ravenous Chupacabra", "alice")
    scenario.game.put_triggers_on_stack()

    assert scenario.game.stack == []
    assert scout.zone is Zone.BATTLEFIELD


def test_an_opponents_activated_ability_cannot_target_a_hexproof_creature():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Goblin Bombardment", "Runeclaw Bear"])
        .player("bob", battlefield=["Gladecover Scout"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scout = scenario.creature("Gladecover Scout", "bob")
    bombardment = scenario.find("Goblin Bombardment", Zone.BATTLEFIELD, "alice")
    fodder = scenario.creature("Runeclaw Bear", "alice")

    with pytest.raises(ValueError, match="has hexproof"):
        scenario.activate(bombardment, sacrificing=[fodder], targets=[scout])


def test_its_controllers_own_activated_ability_can_target_it():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Goblin Bombardment", "Runeclaw Bear", "Gladecover Scout"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scout = scenario.creature("Gladecover Scout", "alice")
    bombardment = scenario.find("Goblin Bombardment", Zone.BATTLEFIELD, "alice")
    fodder = scenario.creature("Runeclaw Bear", "alice")

    scenario.activate(bombardment, sacrificing=[fodder], targets=[scout])
    scenario.resolve_top()
    assert scout.zone is Zone.GRAVEYARD


# -- Knight of Grace's other static line -----------------------------------
#
# "This creature gets +1/+0 as long as any player controls a black
# permanent." - a CR 611.3a live condition over the whole board (any
# player's permanents, judged by computed colour), applied in layer 7c
# (CR 613.4c).


def test_knight_of_grace_is_unpumped_with_no_black_permanent_anywhere():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Swamp", "Grizzly Bears"])
        .player("bob", battlefield=["Knight of Grace"])
        .build()
    )
    knight = scenario.creature("Knight of Grace", "bob")
    assert (scenario.game.power_of(knight), scenario.game.toughness_of(knight)) == (2, 2)


def test_knight_of_grace_gets_plus_one_while_an_opponent_controls_a_black_permanent():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Vampire Hexmage"])
        .player("bob", battlefield=["Knight of Grace"])
        .build()
    )
    knight = scenario.creature("Knight of Grace", "bob")
    assert (scenario.game.power_of(knight), scenario.game.toughness_of(knight)) == (3, 2)

    scenario.game.put_into_graveyard(scenario.creature("Vampire Hexmage", "alice"))
    assert scenario.game.power_of(knight) == 2


def test_knight_of_grace_counts_its_own_controllers_black_permanent_too():
    """ "any player" includes the Knight's own controller."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice")
        .player("bob", battlefield=["Knight of Grace", "Vampire Hexmage"])
        .build()
    )
    knight = scenario.creature("Knight of Grace", "bob")
    assert scenario.game.power_of(knight) == 3


# -- Knight of Malice: the same two lines, in the other colour -------------
#
# "Hexproof from white" and "gets +1/+0 as long as any player controls a white
# permanent" - an off-pool printing proving both readers are the shape, not
# Knight of Grace's sentence.


def test_knight_of_malice_refuses_an_opponents_white_ability_and_allows_a_red_one():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice", hand=["Blossoming Calm"], battlefield=["Goblin Bombardment", "Runeclaw Bear"]
        )
        .player("bob", battlefield=["Knight of Malice"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    knight = scenario.creature("Knight of Malice", "bob")
    calm = scenario.find("Blossoming Calm", Zone.HAND, "alice")
    assert "hexproof from white" in scenario.game.hexproof_refusal(knight, "alice", calm)

    bombardment = scenario.find("Goblin Bombardment", Zone.BATTLEFIELD, "alice")
    fodder = scenario.creature("Runeclaw Bear", "alice")
    scenario.activate(bombardment, sacrificing=[fodder], targets=[knight])
    scenario.resolve_top()
    assert knight.damage == 1


def test_knight_of_malice_gets_plus_one_while_a_white_permanent_is_out():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Leyline of Sanctity"])
        .player("bob", battlefield=["Knight of Malice"])
        .build()
    )
    knight = scenario.creature("Knight of Malice", "bob")
    assert scenario.game.power_of(knight) == 3
    scenario.game.put_into_graveyard(
        scenario.find("Leyline of Sanctity", Zone.BATTLEFIELD, "alice")
    )
    assert scenario.game.power_of(knight) == 2
