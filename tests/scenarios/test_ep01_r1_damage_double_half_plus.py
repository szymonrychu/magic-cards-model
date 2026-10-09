"""Scenario: static damage replacements that scale the damage ("it deals double
that damage", "half that damage, rounded down", "that much damage plus N") and
static prevention of a counted part of it ("prevent 1 of that damage", "prevent
X of that damage", "prevent all but 1 of that damage", "prevent half that
damage, rounded up") - EP-01 round 1, task T5.

CR 614.1a: effects that use "instead" are replacement effects; CR 701.10g:
doubling damage is the source dealing twice that much; CR 615.10: a static
"prevent 1 of that damage" prevents that amount in each applicable damage event
separately; CR 609.7b: the source's properties are checked as the damage would
be dealt; CR 616.1: the affected object's controller orders competing effects.

The damage amount is asserted on the recipient, the source filter is proven
true and false for each family, and a sibling condition ("as long as this
artifact is untapped", "another", "you control") is proven still read.

Every CR number here was looked up with `mise run rules:find`: 614.1a, 701.10g,
615.10, 609.7b, 616.1, 120.4b.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.cards import card_state
from tests.scenarios.harness import Scenario


def _board(alice=(), bob=(), alice_hand=(), bob_hand=()):
    return (
        Scenario()
        .player("alice", library=["Plains"], hand=list(alice_hand), battlefield=list(alice))
        .player("bob", library=["Mountain"], hand=list(bob_hand), battlefield=list(bob))
        .build()
    )


def _on(scenario, name, owner="alice"):
    return scenario.find(name, Zone.BATTLEFIELD, owner)


def _hit(scenario, target, amount, source, *, combat=False):
    game = scenario.game
    if combat:
        game._dealing_combat_damage = True
    try:
        return game.deal_damage(target, amount, source=source)
    finally:
        game._dealing_combat_damage = False


def _spell(scenario, name, owner):
    """A real card on the stack, controlled by `owner` - a damage source that is a spell."""
    spell = card_state(name, Zone.STACK, controller=owner, owner=owner)
    spell.bind_to_game(scenario.game)
    scenario.game.stack.append(spell)
    return spell


# -- double -----------------------------------------------------------------------


def test_goldnight_castigator_doubles_damage_to_its_controller_and_to_itself():
    scenario = _board(alice=["Goldnight Castigator"], bob=["Goblin Guide"])
    guide = scenario.creature("Goblin Guide", "bob")
    castigator = _on(scenario, "Goldnight Castigator")

    assert _hit(scenario, scenario.player("alice"), 3, guide) == 6
    assert scenario.player("alice").life == 14
    assert _hit(scenario, castigator, 2, guide) == 4
    assert castigator.damage == 4
    # Damage to anything else is untouched, including the opponent.
    assert _hit(scenario, scenario.player("bob"), 3, guide) == 3


def test_curse_of_bloodletting_doubles_damage_to_the_enchanted_player_only():
    from magic_cards_model.models.card_state import TargetKind, TargetRef

    scenario = _board(alice=["Curse of Bloodletting"], bob=["Goblin Guide"])
    curse = _on(scenario, "Curse of Bloodletting")
    guide = scenario.creature("Goblin Guide", "bob")
    curse.attachment = TargetRef(kind=TargetKind.PLAYER, username="bob")

    assert _hit(scenario, scenario.player("bob"), 3, guide) == 6
    assert _hit(scenario, scenario.player("alice"), 3, guide) == 3


def test_gisela_doubles_damage_to_opponents_and_halves_damage_to_you_rounded_up():
    scenario = _board(
        alice=["Gisela, Blade of Goldnight", "Grizzly Bears"], bob=["Goblin Guide", "Grizzly Bears"]
    )
    guide = scenario.creature("Goblin Guide", "bob")
    mine = scenario.creature("Grizzly Bears", "alice")
    theirs = scenario.creature("Grizzly Bears", "bob")

    # to an opponent or a permanent an opponent controls: double
    assert _hit(scenario, scenario.player("bob"), 3, mine) == 6
    assert _hit(scenario, theirs, 2, guide) == 4
    # to you or a permanent you control: prevent half, rounded up -> 5 damage leaves 2
    assert _hit(scenario, scenario.player("alice"), 5, guide) == 2
    assert _hit(scenario, mine, 3, guide) == 1
    assert _hit(scenario, mine, 1, guide) == 0  # half of 1, rounded up, is 1: all prevented


def test_charging_tuskodon_doubles_only_its_own_combat_damage_to_a_player():
    scenario = _board(alice=["Charging Tuskodon", "Grizzly Bears"], bob=["Goblin Guide"])
    tuskodon = _on(scenario, "Charging Tuskodon")
    bears = scenario.creature("Grizzly Bears", "alice")
    bob = scenario.player("bob")

    assert _hit(scenario, bob, 4, tuskodon, combat=True) == 8
    assert _hit(scenario, bob, 4, tuskodon) == 4  # noncombat: not "combat damage"
    assert _hit(scenario, bob, 2, bears, combat=True) == 2  # another source
    assert _hit(scenario, scenario.creature("Goblin Guide", "bob"), 4, tuskodon, combat=True) == 4


def test_fire_servant_doubles_damage_from_red_instants_and_sorceries_you_control():
    scenario = _board(alice=["Fire Servant"], bob=["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "bob")
    mine = _spell(scenario, "Lightning Bolt", "alice")
    theirs = _spell(scenario, "Lightning Bolt", "bob")
    blue = _spell(scenario, "Counterspell", "alice")

    assert _hit(scenario, bears, 3, mine) == 6
    assert _hit(scenario, bears, 3, theirs) == 3  # not "you control"
    assert _hit(scenario, bears, 3, blue) == 3  # not red
    assert _hit(scenario, bears, 3, scenario.creature("Fire Servant", "alice")) == 3  # not a spell


def test_obosh_doubles_damage_from_odd_mana_value_sources_you_control():
    scenario = _board(
        alice=["Obosh, the Preypiercer", "Llanowar Elves", "Grizzly Bears"], bob=["Goblin Guide"]
    )
    elves = scenario.creature("Llanowar Elves", "alice")  # mana value 1
    bears = scenario.creature("Grizzly Bears", "alice")  # mana value 2
    guide = scenario.creature("Goblin Guide", "bob")  # mana value 1, but not yours
    bob = scenario.player("bob")

    assert _hit(scenario, bob, 2, elves) == 4
    assert _hit(scenario, bob, 2, bears) == 2
    assert _hit(scenario, scenario.player("alice"), 2, guide) == 2


def test_neriv_doubles_damage_from_creatures_that_entered_this_turn():
    scenario = _board(
        alice=["Neriv, Heart of the Storm", "Grizzly Bears", "Llanowar Elves"], bob=["Goblin Guide"]
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    turn = scenario.game.turn.number
    new = scenario.creature("Grizzly Bears", "alice")
    old = scenario.creature("Llanowar Elves", "alice")
    new.turn_entered = turn
    old.turn_entered = turn - 2
    bob = scenario.player("bob")

    assert _hit(scenario, bob, 2, new) == 4
    assert _hit(scenario, bob, 2, old) == 2


def test_kuja_doubles_damage_from_wizards_you_control():
    scenario = _board(
        alice=["Kuja, Genome Sorcerer", "Tester of the Tangential", "Grizzly Bears"], bob=[]
    )
    bob = scenario.player("bob")
    assert _hit(scenario, bob, 2, scenario.creature("Tester of the Tangential", "alice")) == 4
    assert _hit(scenario, bob, 2, scenario.creature("Grizzly Bears", "alice")) == 2


# -- half -------------------------------------------------------------------------


@pytest.mark.parametrize(("damage", "dealt"), [(1, 0), (2, 1), (5, 2), (8, 4)])
def test_ghosts_of_the_innocent_halves_all_damage_rounded_down(damage, dealt):
    scenario = _board(alice=["Ghosts of the Innocent", "Grizzly Bears"], bob=["Goblin Guide"])
    guide = scenario.creature("Goblin Guide", "bob")
    assert _hit(scenario, scenario.creature("Grizzly Bears", "alice"), damage, guide) == dealt
    assert _hit(scenario, scenario.player("bob"), damage, guide) == dealt


# -- plus N ---------------------------------------------------------------------------


def test_embermaw_hellion_adds_one_to_damage_from_other_red_sources_you_control():
    scenario = _board(
        alice=["Embermaw Hellion", "Goblin Guide", "Grizzly Bears"], bob=["Goblin Guide"]
    )
    hellion = _on(scenario, "Embermaw Hellion")
    red = scenario.creature("Goblin Guide", "alice")
    green = scenario.creature("Grizzly Bears", "alice")
    opposing = scenario.creature("Goblin Guide", "bob")
    bob = scenario.player("bob")

    assert _hit(scenario, bob, 2, red) == 3
    assert _hit(scenario, bob, 2, hellion) == 2  # "another"
    assert _hit(scenario, bob, 2, green) == 2
    assert _hit(scenario, scenario.player("alice"), 2, opposing) == 2  # "you control"


def test_pyromancers_swath_adds_two_to_instant_and_sorcery_sources_you_control():
    scenario = _board(alice=["Pyromancer's Swath"], bob=["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "bob")
    assert _hit(scenario, bears, 3, _spell(scenario, "Lightning Bolt", "alice")) == 5
    assert _hit(scenario, bears, 3, _spell(scenario, "Lightning Bolt", "bob")) == 3
    assert _hit(scenario, bears, 3, scenario.creature("Grizzly Bears", "bob")) == 3  # not a spell


def test_pyromancers_gauntlet_covers_red_spells_and_red_planeswalkers_you_control():
    scenario = _board(
        alice=["Pyromancer's Gauntlet", "Chandra, Torch of Defiance", "Jace Beleren"], bob=[]
    )
    bob = scenario.player("bob")
    assert _hit(scenario, bob, 3, _spell(scenario, "Lightning Bolt", "alice")) == 5
    assert _hit(scenario, bob, 3, _on(scenario, "Chandra, Torch of Defiance")) == 5
    assert _hit(scenario, bob, 3, _on(scenario, "Jace Beleren")) == 3  # not red
    assert _hit(scenario, bob, 3, _spell(scenario, "Counterspell", "alice")) == 3  # not red


def test_valley_flamecaller_adds_one_for_the_listed_creature_types_only():
    scenario = _board(alice=["Valley Flamecaller", "Grizzly Bears"], bob=[])
    bob = scenario.player("bob")
    assert _hit(scenario, bob, 2, _on(scenario, "Valley Flamecaller")) == 3  # a Lizard
    assert _hit(scenario, bob, 2, scenario.creature("Grizzly Bears", "alice")) == 2  # a Bear


def test_mechanized_warfare_applies_to_red_or_artifact_sources_dealing_to_opponents():
    scenario = _board(
        alice=["Mechanized Warfare", "Goblin Guide", "Ornithopter", "Grizzly Bears"],
        bob=["Grizzly Bears"],
    )
    bob = scenario.player("bob")
    theirs = scenario.creature("Grizzly Bears", "bob")
    assert _hit(scenario, bob, 2, scenario.creature("Goblin Guide", "alice")) == 3  # red
    assert _hit(scenario, bob, 2, scenario.creature("Ornithopter", "alice")) == 3  # artifact
    assert _hit(scenario, bob, 2, scenario.creature("Grizzly Bears", "alice")) == 2  # neither
    assert (
        _hit(scenario, theirs, 2, scenario.creature("Goblin Guide", "alice")) == 3
    )  # their permanent
    assert (
        _hit(scenario, scenario.player("alice"), 2, scenario.creature("Goblin Guide", "alice")) == 2
    )


def test_fated_firepower_adds_its_fire_counters():
    scenario = _board(alice=["Fated Firepower", "Goblin Guide"], bob=[])
    firepower = _on(scenario, "Fated Firepower")
    firepower.add_counters("fire", 3)
    guide = scenario.creature("Goblin Guide", "alice")
    assert _hit(scenario, scenario.player("bob"), 2, guide) == 5
    firepower.remove_counters("fire", 3)
    assert _hit(scenario, scenario.player("bob"), 2, guide) == 2


def test_rem_karolus_prevents_spell_damage_to_you_and_adds_one_to_spell_damage_to_opponents():
    scenario = _board(
        alice=["Rem Karolus, Stalwart Slayer", "Grizzly Bears"], bob=["Grizzly Bears"]
    )
    rem = _on(scenario, "Rem Karolus, Stalwart Slayer")
    mine = scenario.creature("Grizzly Bears", "alice")
    theirs = scenario.creature("Grizzly Bears", "bob")
    bolt = _spell(scenario, "Lightning Bolt", "bob")
    mine_bolt = _spell(scenario, "Lightning Bolt", "alice")

    assert _hit(scenario, scenario.player("alice"), 3, bolt) == 0
    assert _hit(scenario, mine, 3, bolt) == 0  # another permanent you control
    assert _hit(scenario, rem, 3, bolt) == 3  # "another": Rem itself is dealt it
    assert (
        _hit(scenario, scenario.player("alice"), 3, scenario.creature("Grizzly Bears", "bob")) == 3
    )  # not a spell
    assert _hit(scenario, scenario.player("bob"), 3, mine_bolt) == 4
    assert _hit(scenario, theirs, 2, mine_bolt) == 3


# -- prevent N of that damage ---------------------------------------------------------------


@pytest.mark.parametrize("holder", ["Urza's Armor", "Protection of the Hekma"])
def test_prevent_one_of_that_damage_to_you(holder):
    scenario = _board(alice=[holder, "Grizzly Bears"], bob=["Goblin Guide"])
    guide = scenario.creature("Goblin Guide", "bob")
    assert _hit(scenario, scenario.player("alice"), 3, guide) == 2
    assert _hit(scenario, scenario.player("alice"), 1, guide) == 0
    assert (
        _hit(scenario, scenario.creature("Grizzly Bears", "alice"), 3, guide) == 3
    )  # you, not your creatures
    assert _hit(scenario, scenario.player("bob"), 3, guide) == 3


def test_protection_of_the_hekma_only_works_against_sources_an_opponent_controls():
    scenario = _board(alice=["Protection of the Hekma", "Grizzly Bears"], bob=["Goblin Guide"])
    assert (
        _hit(scenario, scenario.player("alice"), 3, scenario.creature("Grizzly Bears", "alice"))
        == 3
    )
    assert (
        _hit(scenario, scenario.player("alice"), 3, scenario.creature("Goblin Guide", "bob")) == 2
    )


def test_orbs_of_warding_works_against_creatures_only():
    scenario = _board(alice=["Orbs of Warding"], bob=["Goblin Guide"])
    alice = scenario.player("alice")
    assert _hit(scenario, alice, 3, scenario.creature("Goblin Guide", "bob")) == 2
    assert _hit(scenario, alice, 3, _spell(scenario, "Lightning Bolt", "bob")) == 3


def test_sphere_of_purity_works_against_artifacts_only():
    scenario = _board(alice=["Sphere of Purity"], bob=["Ornithopter", "Goblin Guide"])
    alice = scenario.player("alice")
    assert _hit(scenario, alice, 3, scenario.creature("Ornithopter", "bob")) == 2
    assert _hit(scenario, alice, 3, scenario.creature("Goblin Guide", "bob")) == 3


def test_guardian_seraph_prevents_one_from_each_opposing_source():
    scenario = _board(alice=["Guardian Seraph"], bob=["Goblin Guide", "Grizzly Bears"])
    alice = scenario.player("alice")
    assert _hit(scenario, alice, 2, scenario.creature("Goblin Guide", "bob")) == 1
    assert _hit(scenario, alice, 2, scenario.creature("Grizzly Bears", "bob")) == 1
    assert alice.life == 18


def test_plated_pegasus_prevents_one_of_each_spells_damage():
    scenario = _board(alice=["Plated Pegasus", "Grizzly Bears"], bob=["Goblin Guide"])
    bears = scenario.creature("Grizzly Bears", "alice")
    assert _hit(scenario, bears, 3, _spell(scenario, "Lightning Bolt", "bob")) == 2
    assert (
        _hit(scenario, scenario.player("bob"), 3, _spell(scenario, "Lightning Bolt", "alice")) == 2
    )
    assert _hit(scenario, bears, 3, scenario.creature("Goblin Guide", "bob")) == 3  # not a spell


def test_djeru_prevents_one_of_the_damage_to_your_planeswalkers_only():
    scenario = _board(
        alice=["Djeru, With Eyes Open", "Jace Beleren", "Grizzly Bears"], bob=["Goblin Guide"]
    )
    guide = scenario.creature("Goblin Guide", "bob")
    jace = _on(scenario, "Jace Beleren")
    assert _hit(scenario, jace, 3, guide) == 2
    assert _hit(scenario, scenario.creature("Grizzly Bears", "alice"), 3, guide) == 3
    assert _hit(scenario, scenario.player("alice"), 3, guide) == 3


def test_hedron_field_purists_prevent_the_amount_for_its_level():
    scenario = _board(alice=["Hedron-Field Purists", "Grizzly Bears"], bob=["Goblin Guide"])
    purists = _on(scenario, "Hedron-Field Purists")
    guide = scenario.creature("Goblin Guide", "bob")
    # No level counters: neither level line is active yet.
    assert _hit(scenario, scenario.player("alice"), 3, guide) == 3

    purists.add_counters("level", 1)
    assert _hit(scenario, scenario.player("alice"), 3, guide) == 2
    assert _hit(scenario, scenario.creature("Grizzly Bears", "alice"), 3, guide) == 2

    purists.remove_counters("level", 1)
    purists.add_counters("level", 5)
    assert _hit(scenario, scenario.player("alice"), 3, guide) == 1


def test_shield_of_the_realm_prevents_two_to_the_equipped_creature():
    scenario = _board(
        alice=["Shield of the Realm", "Grizzly Bears", "Llanowar Elves"], bob=["Goblin Guide"]
    )
    guide = scenario.creature("Goblin Guide", "bob")
    bears = scenario.creature("Grizzly Bears", "alice")
    elves = scenario.creature("Llanowar Elves", "alice")
    _on(scenario, "Shield of the Realm").attach_to(bears)
    assert _hit(scenario, bears, 5, guide) == 3
    assert _hit(scenario, bears, 1, guide) == 0
    assert _hit(scenario, elves, 5, guide) == 5
    assert _hit(scenario, scenario.player("alice"), 5, guide) == 5


def test_shield_of_the_avatar_prevents_as_many_as_creatures_you_control():
    scenario = _board(
        alice=["Shield of the Avatar", "Grizzly Bears", "Llanowar Elves"], bob=["Goblin Guide"]
    )
    guide = scenario.creature("Goblin Guide", "bob")
    bears = scenario.creature("Grizzly Bears", "alice")
    _on(scenario, "Shield of the Avatar").attach_to(bears)
    assert _hit(scenario, bears, 5, guide) == 3  # two creatures you control
    scenario.game.destroy(scenario.creature("Llanowar Elves", "alice"))
    assert _hit(scenario, bears, 5, guide) == 4  # one creature left


def test_temple_altisaur_leaves_one_damage_on_other_dinosaurs():
    scenario = _board(
        alice=["Temple Altisaur", "Ranging Raptors", "Grizzly Bears"], bob=["Goblin Guide"]
    )
    guide = scenario.creature("Goblin Guide", "bob")
    raptors = scenario.creature("Ranging Raptors", "alice")
    assert _hit(scenario, raptors, 4, guide) == 1
    assert _hit(scenario, raptors, 1, guide) == 1
    assert _hit(scenario, _on(scenario, "Temple Altisaur"), 4, guide) == 4  # "another"
    assert _hit(scenario, scenario.creature("Grizzly Bears", "alice"), 4, guide) == 4


def test_battletide_alchemist_may_prevent_one_per_cleric():
    scenario = _board(alice=["Battletide Alchemist", "Kitsune Bonesetter"], bob=["Goblin Guide"])
    guide = scenario.creature("Goblin Guide", "bob")
    scenario.will_take_the_may(True)
    assert (
        _hit(scenario, scenario.player("alice"), 5, guide) == 3
    )  # two Clerics: Alchemist and Bonesetter


def test_battletide_alchemist_prevention_is_optional():
    scenario = _board(alice=["Battletide Alchemist"], bob=["Goblin Guide"])
    guide = scenario.creature("Goblin Guide", "bob")
    scenario.will_take_the_may(False)
    assert _hit(scenario, scenario.player("alice"), 5, guide) == 5


def test_cover_of_winter_prevents_one_per_age_counter_of_combat_damage():
    scenario = _board(alice=["Cover of Winter", "Grizzly Bears"], bob=["Goblin Guide"])
    cover = _on(scenario, "Cover of Winter")
    cover.add_counters("age", 2)
    guide = scenario.creature("Goblin Guide", "bob")
    bears = scenario.creature("Grizzly Bears", "alice")
    assert _hit(scenario, scenario.player("alice"), 5, guide, combat=True) == 3
    assert _hit(scenario, bears, 5, guide, combat=True) == 3
    assert _hit(scenario, scenario.player("alice"), 5, guide) == 5  # not combat damage
    assert _hit(scenario, scenario.player("bob"), 5, bears, combat=True) == 5


def test_thunderstaff_prevents_one_only_while_untapped():
    scenario = _board(alice=["Thunderstaff"], bob=["Goblin Guide"])
    staff = _on(scenario, "Thunderstaff")
    guide = scenario.creature("Goblin Guide", "bob")
    alice = scenario.player("alice")
    assert _hit(scenario, alice, 3, guide, combat=True) == 2
    staff.tap()
    assert _hit(scenario, alice, 3, guide, combat=True) == 3
    staff.untap()
    assert _hit(scenario, alice, 3, guide) == 3  # noncombat damage
