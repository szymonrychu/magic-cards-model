"""Scenario: "Prevent all noncombat damage that would be dealt to `<group>`."

A static prevention effect (CR 615.1a: "Effects that use the word 'prevent'
are prevention effects") read off oracle text by `machines/replacement.py`'s
prevent-all compiler: Crystal Barricade's "to other creatures you control",
and the proof printing Mark of Asylum's "to creatures you control" (no
"other"). CR 510.2 marks combat damage, which "noncombat" leaves alone; CR
615.6: prevented damage never happens. The effect exists only while its
source is on the battlefield (CR 604.2, CR 611.3a).

CR 615.12: damage that "can't be prevented" still has the effect applied,
but nothing is prevented - Skullcrack's own sentence, covered at length in
`test_lifegain_and_prevention_bans.py`, is checked against this effect here.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file: 615.1a, 510.2, 615.6, 604.2, 611.3a, 615.12.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board(protector: str, *, alice_hand=None, bob_hand=None) -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            library=["Forest"],
            hand=alice_hand or [],
            battlefield=[protector, "Grizzly Bears", "Mountain"],
        )
        .player(
            "bob",
            library=["Forest"],
            hand=bob_hand or ["Lightning Bolt"],
            battlefield=["Savannah Lions", "Mountain", "Goblin Guide"],
        )
    )


def _bolt(scenario, target) -> None:
    """Bob casts Lightning Bolt in response to nothing, once Alice passes."""
    scenario.pass_priority("alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_and_resolve("Lightning Bolt", mountain, username="bob", targets=[target])


# -- Crystal Barricade: "to other creatures you control" -----------------------


def test_barricade_prevents_noncombat_damage_to_another_creature_you_control():
    scenario = _board("Crystal Barricade").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    _bolt(scenario, bears)

    assert bears.zone is Zone.BATTLEFIELD
    assert bears.damage == 0


def test_barricade_does_not_protect_itself():
    """ "other creatures" - the Barricade itself takes the damage."""
    scenario = _board("Crystal Barricade").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    barricade = scenario.creature("Crystal Barricade", "alice")

    assert (
        scenario.game.deal_damage(barricade, 3, source=scenario.creature("Goblin Guide", "bob"))
        == 3
    )
    assert barricade.damage == 3


def _bears_attack_into_lions(scenario) -> tuple:
    """Alice's Grizzly Bears attack; Bob's Savannah Lions block them - CR
    510.2's combat damage both ways."""
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    lions = scenario.creature("Savannah Lions", "bob")
    scenario.attack_with(bears)
    scenario.block(bears, lions)
    scenario.combat_damage()
    return bears, lions


def test_barricade_does_not_prevent_combat_damage():
    scenario = _board("Crystal Barricade").build()

    bears, lions = _bears_attack_into_lions(scenario)

    assert bears.zone is Zone.GRAVEYARD
    assert lions.zone is Zone.GRAVEYARD


def test_barricade_does_not_protect_an_opponents_creature():
    scenario = _board("Crystal Barricade").build()
    lions = scenario.creature("Savannah Lions", "bob")
    guide = scenario.creature("Goblin Guide", "bob")

    assert scenario.game.deal_damage(lions, 2, source=guide) == 2


def test_barricade_does_not_prevent_damage_to_its_controller():
    scenario = _board("Crystal Barricade").build()
    guide = scenario.creature("Goblin Guide", "bob")

    assert scenario.game.deal_damage(scenario.player("alice"), 2, source=guide) == 2
    assert scenario.player("alice").life == 18


def test_barricade_stops_preventing_once_it_leaves():
    """CR 611.3a: a static ability's effect is not locked in."""
    scenario = _board("Crystal Barricade").build()
    barricade = scenario.creature("Crystal Barricade", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    guide = scenario.creature("Goblin Guide", "bob")
    scenario.game.destroy(barricade)

    assert scenario.game.deal_damage(bears, 1, source=guide) == 1


def test_barricade_protects_its_own_controllers_damage_too():
    """ "noncombat damage" from any source - including alice's own."""
    scenario = _board("Crystal Barricade", alice_hand=["Lightning Bolt"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")

    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=[bears])

    assert bears.zone is Zone.BATTLEFIELD
    assert bears.damage == 0


def test_barricade_prevention_is_ignored_when_damage_cant_be_prevented():
    """CR 615.12 - Skullcrack's "Damage can't be prevented this turn." makes
    the Barricade apply and prevent nothing."""
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest"],
            hand=["Skullcrack"],
            battlefield=["Crystal Barricade", "Grizzly Bears", "Mountain", "Mountain"],
        )
        .player("bob", library=["Forest"], battlefield=["Goblin Guide"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    guide = scenario.creature("Goblin Guide", "bob")
    mountains = scenario.untapped_sources("Mountain", "Mountain", username="alice")
    scenario.cast_and_resolve("Skullcrack", *mountains, username="alice", targets=["bob"])

    assert scenario.game.deal_damage(bears, 1, source=guide) == 1


# -- Mark of Asylum (proof): "to creatures you control" -----------------------


def test_mark_of_asylum_prevents_noncombat_damage_to_every_creature_you_control():
    scenario = _board("Mark of Asylum").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    _bolt(scenario, bears)

    assert bears.damage == 0
    assert bears.zone is Zone.BATTLEFIELD


def test_mark_of_asylum_does_not_prevent_combat_damage():
    scenario = _board("Mark of Asylum").build()

    bears, _lions = _bears_attack_into_lions(scenario)

    assert bears.zone is Zone.GRAVEYARD


def test_mark_of_asylum_leaves_players_and_opponents_alone():
    scenario = _board("Mark of Asylum").build()
    guide = scenario.creature("Goblin Guide", "bob")
    lions = scenario.creature("Savannah Lions", "bob")

    assert scenario.game.deal_damage(scenario.player("alice"), 2, source=guide) == 2
    assert scenario.game.deal_damage(lions, 1, source=guide) == 1
