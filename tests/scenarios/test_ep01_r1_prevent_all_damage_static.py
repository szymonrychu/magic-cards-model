"""Scenario: a permanent's static "Prevent all [combat] damage that would be
dealt to / by <group>" (EP-01 round 1, task T5).

CR 615.1 / 615.1a: effects that use "prevent" are prevention effects, applied
as damage events happen; CR 120.4b: damage is dealt "as modified by replacement
and prevention effects". Each family is proven on two differently worded
printings: enchanted creature as the source (Defang, Candletrap), as both
(Heart of Light, Ghostly Possession), a group of recipients (Emmara Tandris,
Iroas, Dolmen Gate, Light of Sanction), the controller (Solitary Confinement,
Personal Sanctuary), the permanent itself (Gideon Blackblade, Uncle Istvan,
Tresserhorn Skyknight, Armored Transport), "that ~ would deal" (Goblin Furrier,
Indentured Oaf) and a named-source recipient (Gideon's Intervention).

Every CR number here was looked up with `mise run rules:find`: 615.1, 615.1a,
120.4b, 120.2a, 510.2, 604.2.
"""

import pytest

from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Choice, ChoiceKind
from magic_cards_model.models.token import TokenDefinition, create_tokens
from tests.cards import card
from tests.scenarios.harness import Scenario


def _board(alice=(), bob=(), alice_life=20):
    return (
        Scenario()
        .player("alice", life=alice_life, library=["Plains"], battlefield=list(alice))
        .player("bob", library=["Mountain"], battlefield=list(bob))
        .build()
    )


def _on(scenario, name, owner="alice"):
    return scenario.find(name, Zone.BATTLEFIELD, owner)


def _hit(scenario, target, amount, source):
    return scenario.game.deal_damage(target, amount, source=source)


def _goblin_token(scenario, username="alice"):
    definition = TokenDefinition(
        types=card("Grizzly Bears").types, subtypes=("Goblin",), power=1, toughness=1
    )
    (token,) = create_tokens(scenario.game, definition, username)
    return token


# -- enchanted creature as the damage's source (Defang, Temporal Isolation) --


@pytest.mark.parametrize("aura", ["Defang", "Temporal Isolation"])
def test_damage_dealt_by_the_enchanted_creature_is_prevented(aura):
    scenario = _board(alice=[aura, "Grizzly Bears"], bob=["Goblin Guide", "Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "bob")
    _on(scenario, aura).attach_to(bears)
    guide = scenario.creature("Goblin Guide", "bob")

    assert _hit(scenario, scenario.creature("Grizzly Bears", "alice"), 3, bears) == 0
    assert _hit(scenario, scenario.player("alice"), 3, bears) == 0
    assert scenario.player("alice").life == 20
    # Damage the enchanted creature takes, and damage other sources deal, is not touched.
    assert _hit(scenario, bears, 1, guide) == 1
    assert _hit(scenario, scenario.player("alice"), 2, guide) == 2


def test_the_prevention_follows_the_aura_not_a_creature_it_left():
    scenario = _board(alice=["Defang"], bob=["Grizzly Bears", "Goblin Guide"])
    bears = scenario.creature("Grizzly Bears", "bob")
    guide = scenario.creature("Goblin Guide", "bob")
    defang = _on(scenario, "Defang")
    defang.attach_to(bears)
    assert _hit(scenario, scenario.player("alice"), 2, bears) == 0

    defang.attach_to(guide)

    assert _hit(scenario, scenario.player("alice"), 2, bears) == 2
    assert _hit(scenario, scenario.player("alice"), 2, guide) == 0


def test_an_unattached_aura_prevents_nothing():
    scenario = _board(alice=["Defang"], bob=["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "bob")
    assert _hit(scenario, scenario.player("alice"), 2, bears) == 2


def test_prevention_stops_when_the_aura_leaves_the_battlefield():
    scenario = _board(alice=["Defang"], bob=["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "bob")
    _on(scenario, "Defang").attach_to(bears)
    scenario.game.destroy(_on(scenario, "Defang"))
    assert _hit(scenario, scenario.player("alice"), 2, bears) == 2


# -- combat only (Candletrap) --------------------------------------------------


def test_candletrap_prevents_only_combat_damage_by_the_enchanted_creature():
    scenario = _board(alice=["Grizzly Bears"], bob=["Candletrap", "Goblin Guide"])
    guide = scenario.creature("Goblin Guide", "bob")
    _on(scenario, "Candletrap", "bob").attach_to(guide)

    # Noncombat damage by the enchanted creature is dealt (CR 120.2b).
    assert _hit(scenario, scenario.player("alice"), 2, guide) == 2


def test_candletrap_prevents_the_enchanted_blockers_combat_damage():
    from magic_cards_model.machines import Step

    scenario = _board(alice=["Candletrap", "Grizzly Bears"], bob=["Goblin Guide"])
    bears = scenario.creature("Grizzly Bears", "alice")
    guide = scenario.creature("Goblin Guide", "bob")
    _on(scenario, "Candletrap").attach_to(bears)  # enchanted creature has defender: it blocks
    scenario.game.turn.active_player = "bob"
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(guide, defending="alice")
    scenario.block(guide, bears)

    scenario.combat_damage()

    assert guide.damage == 0  # the Bears' combat damage was prevented
    assert bears.damage == 2  # but the Bears still take the Guide's


# -- to and by (Heart of Light, Ghostly Possession) ------------------------------


@pytest.mark.parametrize("aura", ["Heart of Light", "Ghostly Possession"])
def test_damage_to_and_by_the_enchanted_creature_is_prevented(aura):
    scenario = _board(alice=[aura, "Grizzly Bears"], bob=["Goblin Guide", "Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "alice")
    _on(scenario, aura).attach_to(bears)
    enemy = scenario.creature("Goblin Guide", "bob")

    from magic_cards_model.machines import Step

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears, defending="bob")
    scenario.block(bears, scenario.creature("Grizzly Bears", "bob"))
    scenario.combat_damage()

    assert bears.damage == 0
    assert scenario.creature("Grizzly Bears", "bob").damage == 0
    assert scenario.player("bob").life == 20
    assert enemy.damage == 0


def test_heart_of_light_prevents_noncombat_damage_too_but_ghostly_possession_does_not():
    scenario = _board(
        alice=["Heart of Light", "Ghostly Possession", "Grizzly Bears", "Llanowar Elves"],
        bob=["Goblin Guide"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    elves = scenario.creature("Llanowar Elves", "alice")
    _on(scenario, "Heart of Light").attach_to(bears)
    _on(scenario, "Ghostly Possession").attach_to(elves)
    guide = scenario.creature("Goblin Guide", "bob")

    assert _hit(scenario, bears, 5, guide) == 0
    assert _hit(scenario, elves, 5, guide) == 5  # not combat damage: Ghostly Possession ignores it


# -- groups of recipients ---------------------------------------------------------


def test_emmara_prevents_damage_to_creature_tokens_you_control_only():
    scenario = _board(alice=["Emmara Tandris", "Grizzly Bears"], bob=["Goblin Guide"])
    guide = scenario.creature("Goblin Guide", "bob")
    token = _goblin_token(scenario)
    bears = scenario.creature("Grizzly Bears", "alice")

    assert _hit(scenario, token, 3, guide) == 0
    assert _hit(scenario, bears, 1, guide) == 1  # a nontoken creature
    assert _hit(scenario, scenario.player("alice"), 1, guide) == 1  # the controller


def test_emmara_does_not_protect_the_opponents_tokens():
    scenario = _board(alice=["Emmara Tandris"], bob=["Goblin Guide"])
    guide = scenario.creature("Goblin Guide", "bob")
    token = _goblin_token(scenario, "bob")
    assert _hit(scenario, token, 3, guide) == 3


@pytest.mark.parametrize("holder", ["Iroas, God of Victory", "Dolmen Gate"])
def test_attacking_creatures_you_control_take_no_damage(holder):
    from magic_cards_model.machines import Step

    scenario = _board(alice=[holder, "Grizzly Bears", "Llanowar Elves"], bob=["Goblin Guide"])
    bears = scenario.creature("Grizzly Bears", "alice")
    elves = scenario.creature("Llanowar Elves", "alice")
    guide = scenario.creature("Goblin Guide", "bob")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears, defending="bob")

    assert _hit(scenario, bears, 4, guide) == 0 or holder == "Iroas, God of Victory"
    assert _hit(scenario, elves, 1, guide) == 1  # not attacking


def test_iroas_prevents_noncombat_damage_to_attackers_dolmen_gate_does_not():
    from magic_cards_model.machines import Step

    scenario = _board(
        alice=["Iroas, God of Victory", "Grizzly Bears"], bob=["Dolmen Gate", "Goblin Guide"]
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    guide = scenario.creature("Goblin Guide", "bob")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears, defending="bob")
    assert _hit(scenario, bears, 4, guide) == 0

    other = _board(alice=["Dolmen Gate", "Grizzly Bears"], bob=["Goblin Guide"])
    other.start_at(Step.DECLARE_ATTACKERS)
    other_bears = other.creature("Grizzly Bears", "alice")
    other.attack_with(other_bears, defending="bob")
    assert _hit(other, other_bears, 4, other.creature("Goblin Guide", "bob")) == 4


def test_rescue_retriever_protects_other_attacking_soldiers_only():
    from magic_cards_model.machines import Step

    scenario = _board(
        alice=["Rescue Retriever", "Goldmeadow Harrier", "Grizzly Bears"], bob=["Goblin Guide"]
    )
    retriever = scenario.creature("Rescue Retriever", "alice")
    harrier = scenario.creature("Goldmeadow Harrier", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    guide = scenario.creature("Goblin Guide", "bob")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    for creature in (retriever, harrier, bears):
        creature.summoning_sick = False
    scenario.attack_with(retriever, defending="bob")
    scenario.attack_with(harrier, defending="bob")
    scenario.attack_with(bears, defending="bob")

    assert _hit(scenario, harrier, 2, guide) == 0  # another attacking Soldier
    assert _hit(scenario, retriever, 2, guide) == 2  # "other": not itself
    assert _hit(scenario, bears, 1, guide) == 1  # not a Soldier


def test_light_of_sanction_prevents_damage_from_your_own_sources_to_your_creatures():
    scenario = _board(
        alice=["Light of Sanction", "Grizzly Bears", "Llanowar Elves"], bob=["Goblin Guide"]
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    elves = scenario.creature("Llanowar Elves", "alice")
    guide = scenario.creature("Goblin Guide", "bob")

    assert _hit(scenario, elves, 2, bears) == 0  # your source -> your creature
    assert _hit(scenario, elves, 2, guide) == 2  # an opposing source
    assert _hit(scenario, scenario.player("alice"), 2, bears) == 2  # to you, not a creature


# -- the controller (Solitary Confinement, Personal Sanctuary) ---------------------


def test_solitary_confinement_prevents_all_damage_to_you_on_any_turn():
    scenario = _board(alice=["Solitary Confinement"], bob=["Goblin Guide", "Grizzly Bears"])
    guide = scenario.creature("Goblin Guide", "bob")
    assert _hit(scenario, scenario.player("alice"), 5, guide) == 0
    assert scenario.player("alice").life == 20
    # Your creatures are not "you".
    assert _hit(scenario, scenario.creature("Grizzly Bears", "bob"), 1, guide) == 1
    assert _hit(scenario, scenario.player("bob"), 3, guide) == 3


def test_personal_sanctuary_only_works_during_your_turn():
    from magic_cards_model.machines import Step

    scenario = _board(alice=["Personal Sanctuary"], bob=["Goblin Guide"])
    guide = scenario.creature("Goblin Guide", "bob")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert scenario.game.turn.active_player == "alice"
    assert _hit(scenario, scenario.player("alice"), 5, guide) == 0

    scenario.game.turn.active_player = "bob"
    assert _hit(scenario, scenario.player("alice"), 5, guide) == 5


# -- the permanent itself ------------------------------------------------------------


def test_gideon_blackblade_takes_no_damage_during_its_controllers_turn_only():
    from magic_cards_model.machines import Step

    scenario = _board(alice=["Gideon Blackblade"], bob=["Goblin Guide"])
    gideon = _on(scenario, "Gideon Blackblade")
    guide = scenario.creature("Goblin Guide", "bob")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert _hit(scenario, gideon, 3, guide) == 0

    scenario.game.turn.active_player = "bob"
    assert _hit(scenario, gideon, 3, guide) == 3


def test_uncle_istvan_ignores_creature_damage_but_not_spell_damage():
    scenario = _board(alice=["Uncle Istvan"], bob=["Goblin Guide", "Mountain"])
    istvan = _on(scenario, "Uncle Istvan")
    guide = scenario.creature("Goblin Guide", "bob")
    assert _hit(scenario, istvan, 2, guide) == 0
    # Lightning Bolt is a spell on the stack, not a creature.
    scenario.game.battlefield.remove(_on(scenario, "Mountain", "bob"))
    bolt = _bolt_on_stack(scenario)
    assert _hit(scenario, istvan, 2, bolt) == 2


def _bolt_on_stack(scenario):
    from tests.cards import card_state

    bolt = card_state("Lightning Bolt", Zone.STACK, controller="bob", owner="bob")
    bolt.bind_to_game(scenario.game)
    scenario.game.stack.append(bolt)
    return bolt


def test_tresserhorn_skyknight_ignores_first_strikers_only():
    scenario = _board(
        alice=["Tresserhorn Skyknight"], bob=["Ash Zealot", "Goblin Guide", "Grizzly Bears"]
    )
    knight = _on(scenario, "Tresserhorn Skyknight")
    zealot = scenario.creature("Ash Zealot", "bob")
    guide = scenario.creature("Goblin Guide", "bob")

    assert _hit(scenario, knight, 2, zealot) == 0
    assert _hit(scenario, knight, 2, guide) == 2


def test_armored_transport_ignores_combat_damage_from_creatures_blocking_it():
    from magic_cards_model.machines import Step

    scenario = _board(alice=["Armored Transport"], bob=["Grizzly Bears", "Goblin Guide"])
    transport = _on(scenario, "Armored Transport")
    transport.summoning_sick = False
    bears = scenario.creature("Grizzly Bears", "bob")
    guide = scenario.creature("Goblin Guide", "bob")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(transport, defending="bob")
    scenario.block(transport, bears)
    scenario.combat_damage()

    assert transport.damage == 0  # the blocker's combat damage was prevented
    assert bears.zone is Zone.GRAVEYARD or bears.damage > 0  # the blocker still takes its

    # Noncombat damage from the same blocker, and damage from a non-blocker, is dealt.
    assert _hit(scenario, transport, 1, guide) == 1


# -- "Prevent all damage that ~ would deal to <group>" ----------------------------------


def test_goblin_furrier_deals_no_damage_to_snow_creatures():
    scenario = _board(alice=["Goblin Furrier"], bob=["Icehide Golem", "Grizzly Bears"])
    furrier = _on(scenario, "Goblin Furrier")
    assert _hit(scenario, scenario.creature("Icehide Golem", "bob"), 3, furrier) == 0
    assert _hit(scenario, scenario.creature("Grizzly Bears", "bob"), 3, furrier) == 3
    assert _hit(scenario, scenario.player("bob"), 3, furrier) == 3


def test_indentured_oaf_deals_no_damage_to_red_creatures():
    scenario = _board(alice=["Indentured Oaf"], bob=["Goblin Guide", "Grizzly Bears"])
    oaf = _on(scenario, "Indentured Oaf")
    assert _hit(scenario, scenario.creature("Goblin Guide", "bob"), 3, oaf) == 0
    assert _hit(scenario, scenario.creature("Grizzly Bears", "bob"), 3, oaf) == 3


def test_another_creatures_damage_to_snow_creatures_is_not_prevented():
    scenario = _board(alice=["Goblin Furrier"], bob=["Icehide Golem", "Goblin Guide"])
    assert (
        _hit(
            scenario,
            scenario.creature("Icehide Golem", "bob"),
            3,
            scenario.creature("Goblin Guide", "bob"),
        )
        == 3
    )


# -- named sources (Gideon's Intervention) -----------------------------------------------


def test_gideons_intervention_prevents_damage_from_sources_with_the_chosen_name():
    scenario = _board(
        alice=["Gideon's Intervention", "Grizzly Bears"], bob=["Goblin Guide", "Grizzly Bears"]
    )
    intervention = _on(scenario, "Gideon's Intervention")
    intervention.choice = Choice(kind=ChoiceKind.CARD_NAME, value="Goblin Guide")
    guide = scenario.creature("Goblin Guide", "bob")
    enemy_bears = scenario.creature("Grizzly Bears", "bob")
    my_bears = scenario.creature("Grizzly Bears", "alice")

    assert _hit(scenario, scenario.player("alice"), 3, guide) == 0
    assert _hit(scenario, my_bears, 3, guide) == 0
    assert _hit(scenario, scenario.player("alice"), 3, enemy_bears) == 3  # another name
    assert _hit(scenario, scenario.player("bob"), 3, guide) == 3  # not you / your permanents
