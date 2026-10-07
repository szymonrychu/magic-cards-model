"""An optional fight - "you may have <this creature | it> fight <target>" -
and a damage instruction replaced by a larger one when its target has a
subtype (NW-05, task T5).

- **CR 701.14a** - "Each of those creatures deals damage equal to its power
  to the other creature." The "you may" is answered as the ability resolves
  (CR 608.2d); declining fights nothing.
- **CR 603.4** - the intervening "if" of Nessian Wilds Ravager ("if tribute
  wasn't paid", CR 702.104b) and Temur War Shaman ("if it's a creature") is
  checked as the ability triggers and again as it resolves; it is still read.
- Temur War Shaman's "it" is the permanent that was turned face up (the
  trigger event's object), not the Shaman. Affectionate Indrik's "it" and
  Nessian Wilds Ravager's "this creature" are the source. Atzocan Archer's
  "another target creature" may be the controller's own.
- **CR 608.2c / CR 614.1a** - Purifying Dragon's "it deals 1 damage to target
  creature defending player controls. If that creature is a Zombie, this
  creature deals 2 damage to it instead." is one damage event: 2 to a
  Zombie, 1 to anything else, never both. The subtype is read off the target
  as the ability resolves (CR 608.2b), on the computed board (CR 613.5).
  Electrostatic Bolt's spell twin ("If it's an artifact creature, ... deals 4
  damage to it instead") stays as it was.

CR numbers checked with `mise run rules:find` (rules effective 2026-09-25).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.triggers import AbilityOnStack
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card
from tests.scenarios.harness import Scenario

LISTED = ["Purifying Dragon", "Nessian Wilds Ravager", "Temur War Shaman"]
SECOND_PRINTINGS = ["Affectionate Indrik", "Atzocan Archer", "Electrostatic Bolt"]


@pytest.mark.parametrize("name", LISTED + SECOND_PRINTINGS)
def test_every_printing_is_fully_handled(name):
    bad = [c for c in card_support(card(name)).clauses if c.outcome != "handled"]
    assert not bad, (name, bad)


def _resolve_all(scenario):
    scenario.game.put_triggers_on_stack()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()
        scenario.game.put_triggers_on_stack()


def _triggers_of(scenario, name):
    return [
        item
        for item in scenario.game.stack
        if isinstance(item, AbilityOnStack) and item.source_name == name
    ]


# -- Purifying Dragon ---------------------------------------------------------


def _dragon_attacks(target_name):
    scenario = (
        Scenario()
        .player("alice", battlefield=["Purifying Dragon"])
        .player("bob", battlefield=[target_name, "Grizzly Bears"])
        .build()
    )
    dragon = scenario.creature("Purifying Dragon", "alice")
    target = scenario.creature(target_name, "bob")
    scenario.will_choose_targets(target, username="alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(dragon)
    _resolve_all(scenario)
    return scenario, target


def test_a_zombie_target_takes_two_damage_and_only_two():
    scenario, horseman = _dragon_attacks("Fell Horseman")
    assert horseman.damage == 2
    assert scenario.game.conditional_clause_notices == []


def test_a_two_toughness_zombie_dies():
    _, corpse = _dragon_attacks("Walking Corpse")
    assert corpse.zone is Zone.GRAVEYARD


def test_a_non_zombie_target_takes_one():
    scenario, bears = _dragon_attacks("Grizzly Bears")
    assert bears.damage == 1
    assert bears.zone is Zone.BATTLEFIELD


def test_a_target_gone_before_resolution_takes_nothing():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Purifying Dragon"])
        .player("bob", battlefield=["Walking Corpse"])
        .build()
    )
    dragon = scenario.creature("Purifying Dragon", "alice")
    corpse = scenario.creature("Walking Corpse", "bob")
    scenario.will_choose_targets(corpse, username="alice")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(dragon)
    scenario.game.destroy(corpse)
    _resolve_all(scenario)

    assert corpse.zone is Zone.GRAVEYARD
    assert dragon.damage == 0


def test_electrostatic_bolt_still_reads_its_artifact_creature_alternative():
    scenario = (
        Scenario()
        .player("alice", hand=["Electrostatic Bolt"], battlefield=["Mountain"])
        .player("bob", battlefield=["Chainbreaker", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    chainbreaker = scenario.creature("Chainbreaker", "bob")
    scenario.cast_and_resolve(
        "Electrostatic Bolt", *scenario.untapped_sources("Mountain"), targets=[chainbreaker]
    )
    assert chainbreaker.zone is Zone.GRAVEYARD  # 4 damage to a 3/3


# -- Nessian Wilds Ravager: if tribute wasn't paid, you may have it fight ----


def _ravager(*, tribute_paid: bool, take: bool = True):
    scenario = (
        Scenario()
        .player("alice", hand=["Nessian Wilds Ravager"], battlefield=["Llanowar Elves"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.will_take_the_may(tribute_paid, username="bob")
    scenario.will_choose_targets(bears, username="alice")
    scenario.will_take_the_may(take, username="alice", source="Nessian Wilds Ravager")
    ravager = scenario.put_onto_battlefield("Nessian Wilds Ravager", "alice")
    scenario.game.put_triggers_on_stack()
    return scenario, ravager, bears


def test_ravager_with_tribute_unpaid_fights_the_target():
    scenario, ravager, bears = _ravager(tribute_paid=False)
    assert len(_triggers_of(scenario, "Nessian Wilds Ravager")) == 1
    _resolve_all(scenario)

    assert bears.zone is Zone.GRAVEYARD
    assert ravager.damage == 2


def test_ravager_declining_the_may_fights_nothing():
    scenario, ravager, bears = _ravager(tribute_paid=False, take=False)
    _resolve_all(scenario)

    assert bears.zone is Zone.BATTLEFIELD and bears.damage == 0
    assert ravager.damage == 0


def test_ravager_with_tribute_paid_never_triggers():
    """CR 603.4: the intervening "if" is still read - paid tribute, no
    trigger and no fight."""
    scenario, ravager, bears = _ravager(tribute_paid=True)
    assert ravager.counter_count("+1/+1") == 6
    assert _triggers_of(scenario, "Nessian Wilds Ravager") == []
    _resolve_all(scenario)

    assert bears.zone is Zone.BATTLEFIELD


def test_ravager_cannot_target_itself():
    """ "another target creature" (CR 115.1, the source excluded)."""
    scenario = Scenario().player("alice", hand=["Nessian Wilds Ravager"]).player("bob").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False, username="bob")
    ravager = scenario.put_onto_battlefield("Nessian Wilds Ravager", "alice")
    _resolve_all(scenario)

    assert ravager.damage == 0
    assert ravager.zone is Zone.BATTLEFIELD


# -- Temur War Shaman: the permanent turned face up fights -------------------


def _shaman(*, library_top="Grizzly Bears", alice_extra=(), hand_extra=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Temur War Shaman", *hand_extra],
            battlefield=["Forest", "Forest", "Forest", *alice_extra],
            library=[library_top, "Forest", "Forest"],
        )
        .player("bob", battlefield=["Llanowar Elves"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    shaman = scenario.put_onto_battlefield("Temur War Shaman", "alice")
    _resolve_all(scenario)  # its enters trigger manifests the top card
    (face_down,) = [p for p in scenario.game.permanents_controlled_by("alice") if p.face_down]
    return scenario, shaman, face_down


def test_the_turned_up_creature_itself_fights():
    scenario, shaman, face_down = _shaman()
    elves = scenario.creature("Llanowar Elves", "bob")
    scenario.will_choose_targets(elves, username="alice")
    scenario.will_take_the_may(True, username="alice", source="Temur War Shaman")
    turned = scenario.turn_face_up(face_down, *scenario.untapped_sources("Forest", "Forest"))
    assert len(_triggers_of(scenario, "Temur War Shaman")) == 1
    _resolve_all(scenario)

    assert turned.name == "Grizzly Bears"
    assert elves.zone is Zone.GRAVEYARD
    assert turned.damage == 1
    assert shaman.damage == 0


def test_declining_the_war_shaman_fight_does_nothing():
    scenario, shaman, face_down = _shaman()
    elves = scenario.creature("Llanowar Elves", "bob")
    scenario.will_choose_targets(elves, username="alice")
    scenario.will_take_the_may(False, username="alice", source="Temur War Shaman")
    turned = scenario.turn_face_up(face_down, *scenario.untapped_sources("Forest", "Forest"))
    _resolve_all(scenario)

    assert elves.zone is Zone.BATTLEFIELD
    assert turned.damage == 0


def test_a_permanent_turned_up_as_a_noncreature_triggers_nothing():
    """CR 603.4: "if it's a creature" is still read. The manifested card is
    Purphoros, God of the Forge; turned face up for its mana cost (CR 701.40b)
    with alice's devotion to red below five, "Purphoros isn't a creature" -
    a noncreature enchantment turned face up, so no trigger and no fight."""
    scenario, shaman, face_down = _shaman(
        library_top="Purphoros, God of the Forge", alice_extra=["Mountain", "Forest"]
    )
    elves = scenario.creature("Llanowar Elves", "bob")
    turned = scenario.turn_face_up(
        face_down, *scenario.untapped_sources("Mountain", "Forest", "Forest", "Forest")
    )

    assert turned.name == "Purphoros, God of the Forge"
    assert not scenario.game.characteristics_of(turned).is_creature
    scenario.game.put_triggers_on_stack()
    assert _triggers_of(scenario, "Temur War Shaman") == []
    _resolve_all(scenario)
    assert elves.zone is Zone.BATTLEFIELD


# -- Affectionate Indrik / Atzocan Archer: "you may have it fight" -----------


def test_affectionate_indrik_may_fight_a_creature_it_does_not_control():
    scenario = (
        Scenario()
        .player("alice", hand=["Affectionate Indrik"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.will_choose_targets(bears, username="alice")
    scenario.will_take_the_may(True, username="alice", source="Affectionate Indrik")
    indrik = scenario.put_onto_battlefield("Affectionate Indrik", "alice")
    _resolve_all(scenario)

    assert bears.zone is Zone.GRAVEYARD
    assert indrik.damage == 2


def test_affectionate_indrik_fights_nothing_if_the_target_left():
    """CR 608.2b: the only target is gone, so the ability does nothing."""
    scenario = (
        Scenario()
        .player("alice", hand=["Affectionate Indrik"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.will_choose_targets(bears, username="alice")
    scenario.will_take_the_may(True, username="alice", source="Affectionate Indrik")
    indrik = scenario.put_onto_battlefield("Affectionate Indrik", "alice")
    scenario.game.destroy(bears)
    _resolve_all(scenario)

    assert indrik.damage == 0


def test_atzocan_archer_may_fight_its_controllers_own_creature():
    """ "another target creature": any creature but the Archer, alice's own
    included."""
    scenario = (
        Scenario()
        .player("alice", hand=["Atzocan Archer"], battlefield=["Llanowar Elves"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    elves = scenario.creature("Llanowar Elves", "alice")
    scenario.will_choose_targets(elves, username="alice")
    scenario.will_take_the_may(True, username="alice", source="Atzocan Archer")
    archer = scenario.put_onto_battlefield("Atzocan Archer", "alice")
    _resolve_all(scenario)

    assert elves.zone is Zone.GRAVEYARD
    assert archer.damage == 1
