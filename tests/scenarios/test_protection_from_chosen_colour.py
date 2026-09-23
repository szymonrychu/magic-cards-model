"""Scenario: "This creature has protection from the chosen color."

Voice of All: "Flying / As this creature enters, choose a color. / This
creature has protection from the chosen color." Order of the Stars (the
second printing, Modern-legal, not in any api deck) prints the same two lines
on a 0/1 defender.

CR 614.12a: the colour is chosen before the creature enters and recorded on
`CardState.choice`; the static then grants "Protection from <that colour>" in
layer 6 (CR 613.1f), which every protection reader already reads off the
computed board. CR 702.16a: "Protection is a static ability, written
'Protection from [quality].'" Each of its consequences is exercised here:

- CR 702.16b - it can't be targeted by spells with the quality, or abilities
  from a source with it (an Aura spell, an equip ability).
- CR 702.16c - it can't be enchanted by Auras with the quality; one already
  attached is put into its owner's graveyard as a state-based action
  (CR 704.5m).
- CR 702.16d - it can't be equipped by Equipment with the quality; one
  already attached becomes unattached and stays on the battlefield
  (CR 704.5n).
- CR 702.16e - damage from sources with the quality is prevented.
- CR 702.16f - while attacking, it can't be blocked by creatures with the
  quality. Only *attacking* creatures are protected this way; the
  protected creature may itself block a creature of that colour.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import (
    aura_state_based_actions,
    equip_activation,
    equipment_state_based_actions,
    equipped_creature,
)
from magic_cards_model.models import Color, Zone
from magic_cards_model.models.card_state import Choice, ChoiceKind
from tests.scenarios.harness import Scenario, mana_from


def entered_choosing(scenario, name, color, username="alice"):
    """Put `name` onto the battlefield, choosing `color` as it enters."""
    scenario.will_choose(color.value, source=name, username=username)
    return scenario.put_onto_battlefield(name, username)


def voice_board(color, *, alice=(), bob=(), alice_hand=(), bob_hand=()):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Voice of All", *alice_hand], battlefield=list(alice))
        .player("bob", hand=list(bob_hand), battlefield=list(bob))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    voice = entered_choosing(scenario, "Voice of All", color)
    return scenario, voice


def test_the_chosen_colour_becomes_a_protection_ability():
    scenario, voice = voice_board(Color.RED)

    assert voice.choice == Choice(kind=ChoiceKind.COLOR, value=Color.RED.value)
    assert scenario.game.characteristics_of(voice).has_ability("Protection from red")
    assert "red" in scenario.game._effective_protection_qualities(voice)


def test_a_different_choice_protects_from_a_different_colour():
    scenario, voice = voice_board(Color.BLUE)

    abilities = scenario.game.characteristics_of(voice).abilities
    assert "Protection from blue" in abilities
    assert "Protection from red" not in abilities


# -- CR 702.16b: targeting --------------------------------------------------


def test_a_spell_of_the_chosen_colour_cannot_target_it():
    scenario, voice = voice_board(Color.RED, bob=["Mountain"], bob_hand=["Lightning Bolt"])

    scenario.pass_priority("alice")

    with pytest.raises(ValueError, match="protection"):
        scenario.cast("Lightning Bolt", username="bob", targets=[voice])


def test_a_spell_of_another_colour_can_target_it():
    scenario, voice = voice_board(Color.BLUE, bob=["Mountain"], bob_hand=["Lightning Bolt"])
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.pass_priority("alice")

    scenario.cast_and_resolve("Lightning Bolt", mountain, username="bob", targets=[voice])

    assert voice.zone is Zone.GRAVEYARD


# -- CR 702.16e: damage -----------------------------------------------------


def test_damage_from_a_source_of_the_chosen_colour_is_prevented():
    """Pyroclasm targets nothing, so it reaches the damage step: the red 2
    damage is prevented on Voice and dealt to Grizzly Bears."""
    scenario, voice = voice_board(
        Color.RED,
        alice=["Grizzly Bears", "Mountain", "Mountain"],
        alice_hand=["Pyroclasm"],
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    sources = scenario.untapped_sources("Mountain", "Mountain", username="alice")

    scenario.cast_and_resolve("Pyroclasm", *sources, username="alice")
    scenario.game.check_state_based_actions()

    assert voice.damage == 0
    assert voice.zone is Zone.BATTLEFIELD
    assert bears.zone is Zone.GRAVEYARD


def test_damage_of_another_colour_is_not_prevented():
    scenario, voice = voice_board(
        Color.GREEN, alice=["Mountain", "Mountain"], alice_hand=["Pyroclasm"]
    )
    sources = scenario.untapped_sources("Mountain", "Mountain", username="alice")

    scenario.cast_and_resolve("Pyroclasm", *sources, username="alice")
    scenario.game.check_state_based_actions()

    assert voice.zone is Zone.GRAVEYARD


# -- CR 702.16c: enchant ----------------------------------------------------


def test_an_aura_of_the_chosen_colour_cannot_be_cast_on_it():
    scenario, voice = voice_board(
        Color.WHITE, alice=["Plains", "Plains"], alice_hand=["Battle Mastery"]
    )

    with pytest.raises(ValueError, match="protection"):
        scenario.cast("Battle Mastery", username="alice", targets=[voice])


def test_an_aura_of_another_colour_enchants_it():
    scenario, voice = voice_board(
        Color.RED, alice=["Plains", "Plains", "Plains"], alice_hand=["Battle Mastery"]
    )
    sources = scenario.untapped_sources("Plains", "Plains", "Plains", username="alice")

    mastery = scenario.cast_and_resolve("Battle Mastery", *sources, targets=[voice])

    assert mastery.zone is Zone.BATTLEFIELD
    assert mastery.attached_to == voice.id


def test_an_aura_of_the_chosen_colour_already_attached_goes_to_the_graveyard():
    """CR 702.16c's second sentence, CR 704.5m. Voice of All's protection
    exists from the moment it enters, so no legal play attaches a white Aura
    to a Voice that chose white; the board is built with the attachment in
    place and the state-based check run on it."""
    scenario, voice = voice_board(Color.WHITE, alice=["Battle Mastery"])
    mastery = scenario.find("Battle Mastery", Zone.BATTLEFIELD, "alice")
    mastery.attach_to(voice)

    doomed = aura_state_based_actions(scenario.game)
    scenario.game.check_state_based_actions()

    assert mastery in doomed
    assert mastery.zone is Zone.GRAVEYARD
    assert voice.zone is Zone.BATTLEFIELD


def test_an_aura_of_another_colour_already_attached_stays():
    scenario, voice = voice_board(Color.RED, alice=["Battle Mastery"])
    mastery = scenario.find("Battle Mastery", Zone.BATTLEFIELD, "alice")
    mastery.attach_to(voice)

    scenario.game.check_state_based_actions()

    assert mastery.zone is Zone.BATTLEFIELD
    assert mastery.attached_to == voice.id


# -- CR 702.16d: equip ------------------------------------------------------


def _pay_and_activate(scenario, activation, lands):
    payment = activation.begin_paying()
    for source in scenario.untapped_sources(*lands, username="alice"):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    activation.activate()
    return activation


def test_equipment_of_the_chosen_colour_cannot_equip_it():
    """Cori-Steel Cutter is red; its equip ability is from a red source, so
    CR 702.16b refuses the target as the ability is announced."""
    scenario, voice = voice_board(Color.RED, alice=["Cori-Steel Cutter", "Mountain", "Mountain"])
    cutter = scenario.find("Cori-Steel Cutter", Zone.BATTLEFIELD, "alice")

    with pytest.raises(ValueError, match="protection"):
        equip_activation(scenario.game, cutter, voice, "alice")


def test_equipment_of_another_colour_equips_it():
    scenario, voice = voice_board(Color.BLUE, alice=["Cori-Steel Cutter", "Mountain", "Mountain"])
    cutter = scenario.find("Cori-Steel Cutter", Zone.BATTLEFIELD, "alice")

    activation = _pay_and_activate(
        scenario, equip_activation(scenario.game, cutter, voice, "alice"), ("Mountain", "Mountain")
    )
    activation.resolve()

    assert equipped_creature(scenario.game, cutter) is voice


def test_equipment_of_the_chosen_colour_already_attached_falls_off_and_stays():
    """CR 702.16d / CR 704.5n: unattached, not destroyed."""
    scenario, voice = voice_board(Color.RED, alice=["Cori-Steel Cutter"])
    cutter = scenario.find("Cori-Steel Cutter", Zone.BATTLEFIELD, "alice")
    cutter.attach_to(voice)

    unattached = equipment_state_based_actions(scenario.game)

    assert cutter in unattached
    assert not cutter.is_attached
    assert cutter.zone is Zone.BATTLEFIELD


def test_equipment_does_not_move_onto_a_creature_that_gained_protection_in_response():
    """CR 301.5b: "If an effect attempts to attach an Equipment to an object
    that can't be equipped by it, the Equipment doesn't move." Cori-Steel
    Cutter's equip is aimed at Grizzly Bears; in response Mother of Runes
    gives the Bears protection from red, so on resolution the red Equipment
    stays where it was (CR 608.2b's recheck and CR 702.16d together)."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=[
                "Cori-Steel Cutter",
                "Grizzly Bears",
                "Mother of Runes",
                "Mountain",
                "Mountain",
            ],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cutter = scenario.find("Cori-Steel Cutter", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    mother = scenario.find("Mother of Runes", Zone.BATTLEFIELD, "alice")
    activation = _pay_and_activate(
        scenario, equip_activation(scenario.game, cutter, bears, "alice"), ("Mountain", "Mountain")
    )

    scenario.will_choose(Color.RED.value, source="Mother of Runes")
    scenario.activate(mother, username="alice", targets=[bears])
    scenario.resolve_top()
    activation.resolve()

    assert not cutter.is_attached
    assert cutter.zone is Zone.BATTLEFIELD


# -- CR 702.16f: blocking ---------------------------------------------------


def _attacking_voice(color, bob_battlefield):
    """Voice of All already on alice's battlefield since the turn began, with
    its CR 614.12a choice recorded as it entered - built directly, since a
    creature put onto the battlefield this turn could not attack (CR 302.6)."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Voice of All"])
        .player("bob", battlefield=list(bob_battlefield))
        .build()
    )
    voice = scenario.creature("Voice of All", "alice")
    voice.choice = Choice(kind=ChoiceKind.COLOR, value=color.value)
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(voice)
    scenario.advance()
    return scenario, voice


def test_an_attacker_cannot_be_blocked_by_a_creature_of_the_chosen_colour():
    """Giant Spider has reach, so flying alone would not stop it - protection
    from green does."""
    scenario, voice = _attacking_voice(Color.GREEN, ["Giant Spider"])
    spider = scenario.creature("Giant Spider", "bob")

    with pytest.raises(ValueError, match="protection"):
        scenario.block(voice, spider)


def test_an_attacker_can_be_blocked_by_a_creature_of_another_colour():
    scenario, voice = _attacking_voice(Color.GREEN, ["Wind Drake"])
    drake = scenario.creature("Wind Drake", "bob")

    scenario.block(voice, drake)

    assert drake in scenario.blockers()


def test_the_protected_creature_may_itself_block_one_of_the_chosen_colour():
    """CR 702.16f protects *attacking* creatures only. Voice of All
    (protection from green) blocks bob's attacking Grizzly Bears, and the
    green combat damage aimed at it is prevented (CR 702.16e)."""
    scenario = (
        Scenario()
        .player("bob", battlefield=["Grizzly Bears"])
        .player("alice", battlefield=["Voice of All"])
        .build()
    )
    voice = scenario.creature("Voice of All", "alice")
    voice.choice = Choice(kind=ChoiceKind.COLOR, value=Color.GREEN.value)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(bears)
    scenario.advance()

    scenario.block(bears, voice)
    assert voice in scenario.blockers()
    scenario.combat_damage()

    assert voice.damage == 0
    assert voice.zone is Zone.BATTLEFIELD


# -- Order of the Stars: the second printing ---------------------------------


def test_order_of_the_stars_reads_the_same_static():
    """Second printing: a 0/1 defender whose protection from red both refuses
    bob's Lightning Bolt (CR 702.16b) and prevents alice's own Pyroclasm
    (CR 702.16e) - protection does not care who controls the source."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Order of the Stars", "Pyroclasm"],
            battlefield=["Mountain", "Mountain"],
        )
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    order = entered_choosing(scenario, "Order of the Stars", Color.RED)
    sources = scenario.untapped_sources("Mountain", "Mountain", username="alice")

    scenario.cast_and_resolve("Pyroclasm", *sources, username="alice")
    scenario.game.check_state_based_actions()

    assert order.zone is Zone.BATTLEFIELD
    assert order.damage == 0

    scenario.pass_priority("alice")
    with pytest.raises(ValueError, match="protection"):
        scenario.cast("Lightning Bolt", username="bob", targets=[order])
