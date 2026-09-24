"""Equipment attaching as part of another instruction (CR 701.3a), and the
riders that follow the attach.

- "When this Equipment enters, attach it to target creature you control."
  (Falcon's Wing Harness) - C01-T2's reader, proven here.
- "... That creature gains indestructible until end of turn." (Stolen Stark
  Tech); Quick-Draw Dagger's "That creature gains first strike until end of
  turn." is the second printing.
- "... Untap that creature." (Super Suit); Galadhrim Bow's identical rider is
  the second printing.
- "When U.S.Agent enters, create a colorless Equipment artifact token named
  Sturdy Shield with "Equipped creature gets +1/+2" and equip {2}. Attach it
  to U.S.Agent." - C01-T2's named-Equipment-token reader, with the attach
  onto the source itself.
- "Whenever enchanted creature attacks or blocks, attach any number of
  target Equipment you control to it." (Super-Soldier Serum) - C01-T2's
  reader, proven here.
- "At the beginning of combat on your turn, you may put an artifact card
  from your hand onto the battlefield. If it's an Equipment, attach it to
  The Invincible Iron Man." (Tony Stark // The Invincible Iron Man) - the put
  is the reader Master Transmuter's "You may put an artifact card from your
  hand onto the battlefield." already goes through; the Equipment attach
  rider is printed on no other card.
- "{3}{W}{B}: Return this card from your graveyard to the battlefield with a
  finality counter on him. Then you may attach an Equipment you control to
  him." (Winter Soldier, Icy Assassin) - CR 122.1g's finality counter, then
  an optional attach. The whole shape is printed on no other card; Resolute
  Strike's "you may attach an Equipment you control to it" is the second
  printing of the optional attach.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.combat import has_keyword
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card
from tests.scenarios.harness import Scenario


def _pt(scenario, state):
    return scenario.game.power_of(state), scenario.game.toughness_of(state)


# -- attach-on-enter, verified ---------------------------------------------------


def test_falcons_wing_harness_attaches_to_its_target_on_entering():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Falcon's Wing Harness"],
            battlefield=["Grizzly Bears", "Island", "Island"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.choose_trigger_targets("Falcon's Wing Harness", [bears])
    scenario.cast_and_resolve(
        "Falcon's Wing Harness", *scenario.untapped_sources("Island", "Island")
    )
    scenario.pass_until_resolved()

    harness = scenario.find("Falcon's Wing Harness", Zone.BATTLEFIELD, "alice")
    assert harness.attached_to == bears.id
    assert _pt(scenario, bears) == (3, 3)
    assert has_keyword(bears, "flying", scenario.game)


# -- "That creature gains <keyword> until end of turn." ---------------------------


def test_stolen_stark_tech_attaches_and_makes_its_creature_indestructible():
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Stolen Stark Tech"], battlefield=["Grizzly Bears", "Swamp", "Swamp"]
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.choose_trigger_targets("Stolen Stark Tech", [bears])
    scenario.cast_and_resolve("Stolen Stark Tech", *scenario.untapped_sources("Swamp", "Swamp"))
    scenario.pass_until_resolved()

    tech = scenario.find("Stolen Stark Tech", Zone.BATTLEFIELD, "alice")
    assert tech.attached_to == bears.id
    assert has_keyword(bears, "indestructible", scenario.game)
    assert _pt(scenario, bears) == (3, 2)

    scenario.game.destroy(bears)
    assert bears.zone is Zone.BATTLEFIELD, "indestructible (CR 702.12b)"


def test_stolen_stark_techs_indestructible_ends_with_the_turn():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice", hand=["Stolen Stark Tech"], battlefield=["Grizzly Bears", "Swamp", "Swamp"]
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.choose_trigger_targets("Stolen Stark Tech", [bears])
    scenario.cast_and_resolve("Stolen Stark Tech", *scenario.untapped_sources("Swamp", "Swamp"))
    scenario.pass_until_resolved()
    while scenario.step is not Step.CLEANUP:
        scenario.advance()
    scenario.turn_based_actions()

    assert not has_keyword(bears, "indestructible", scenario.game)
    assert _pt(scenario, bears) == (3, 2), "the Equipment's own bonus stays"


def test_the_rider_goes_with_the_attach_to_the_trigger_target_only():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Stolen Stark Tech"],
            battlefield=["Grizzly Bears", "Hill Giant", "Swamp", "Swamp"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    scenario.choose_trigger_targets("Stolen Stark Tech", [giant])
    scenario.cast_and_resolve("Stolen Stark Tech", *scenario.untapped_sources("Swamp", "Swamp"))
    scenario.pass_until_resolved()

    assert has_keyword(giant, "indestructible", scenario.game)
    assert not has_keyword(bears, "indestructible", scenario.game)


def test_with_no_creature_the_equipment_just_enters():
    """CR 603.3d: no legal target, so the trigger is removed and neither the
    attach nor the rider happens."""
    scenario = (
        Scenario()
        .player("alice", hand=["Stolen Stark Tech"], battlefield=["Swamp", "Swamp"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("Stolen Stark Tech", *scenario.untapped_sources("Swamp", "Swamp"))
    scenario.pass_until_resolved()

    tech = scenario.find("Stolen Stark Tech", Zone.BATTLEFIELD, "alice")
    assert tech.attached_to is None


def test_quick_draw_dagger_gives_first_strike_until_end_of_turn():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Quick-Draw Dagger"],
            battlefield=["Grizzly Bears", "Plains", "Plains", "Plains"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.choose_trigger_targets("Quick-Draw Dagger", [bears])
    scenario.cast_and_resolve(
        "Quick-Draw Dagger", *scenario.untapped_sources("Plains", "Plains", "Plains")
    )
    scenario.pass_until_resolved()

    assert has_keyword(bears, "first strike", scenario.game)
    assert _pt(scenario, bears) == (3, 3)


# -- "Untap that creature." ---------------------------------------------------------


def test_super_suit_attaches_and_untaps_its_creature():
    scenario = (
        Scenario()
        .player("alice", hand=["Super Suit"], battlefield=["Grizzly Bears", "Island", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.tap()
    scenario.choose_trigger_targets("Super Suit", [bears])
    scenario.cast_and_resolve("Super Suit", *scenario.untapped_sources("Island", "Island"))
    scenario.pass_until_resolved()

    suit = scenario.find("Super Suit", Zone.BATTLEFIELD, "alice")
    assert suit.attached_to == bears.id
    assert not bears.tapped
    assert _pt(scenario, bears) == (3, 4)


def test_super_suit_untaps_an_attacker_after_blockers():
    """Flash at instant speed during combat: the attacker untaps and stays
    attacking (CR 506.4 - untapping does not remove it from combat)."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Super Suit"], battlefield=["Grizzly Bears", "Island", "Island"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.advance()
    scenario.advance()
    scenario.attack_with(bears)
    assert bears.tapped
    scenario.choose_trigger_targets("Super Suit", [bears])
    scenario.cast_and_resolve("Super Suit", *scenario.untapped_sources("Island", "Island"))
    scenario.pass_until_resolved()

    assert not bears.tapped
    assert scenario.attackers() == [bears]


def test_galadhrim_bow_untaps_its_creature():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Galadhrim Bow"],
            battlefield=["Grizzly Bears", "Forest", "Forest", "Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    bears.tap()
    scenario.choose_trigger_targets("Galadhrim Bow", [bears])
    scenario.cast_and_resolve(
        "Galadhrim Bow", *scenario.untapped_sources("Forest", "Forest", "Forest")
    )
    scenario.pass_until_resolved()

    assert not bears.tapped
    assert has_keyword(bears, "reach", scenario.game)


# -- named Equipment token attached to its creator ---------------------------------


def test_us_agent_creates_sturdy_shield_attached_to_himself():
    scenario = (
        Scenario()
        .player("alice", hand=["U.S.Agent, John Walker"], battlefield=["Plains"] * 4)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    agent = scenario.cast_and_resolve(
        "U.S.Agent, John Walker", *scenario.untapped_sources(*["Plains"] * 4)
    )
    scenario.pass_until_resolved()

    shield = scenario.find("Sturdy Shield", Zone.BATTLEFIELD, "alice")
    assert shield.token
    assert "Equipment" in shield.subtypes
    assert shield.attached_to == agent.id
    assert _pt(scenario, agent) == (4, 4)


def test_sturdy_shield_can_be_moved_by_its_equip_ability():
    from magic_cards_model.machines.keywords import equip_activation
    from tests.scenarios.harness import mana_from

    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["U.S.Agent, John Walker"],
            battlefield=["Grizzly Bears"] + ["Plains"] * 6,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve("U.S.Agent, John Walker", *scenario.untapped_sources(*["Plains"] * 4))
    scenario.pass_until_resolved()
    shield = scenario.find("Sturdy Shield", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    activation = equip_activation(scenario.game, shield, bears, "alice")
    payment = activation.begin_paying()
    for source in scenario.untapped_sources("Plains", "Plains"):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    activation.activate()
    scenario.pass_until_resolved()

    assert shield.attached_to == bears.id
    assert _pt(scenario, bears) == (3, 4)


def test_if_us_agent_is_gone_the_shield_stays_unattached():
    """CR 701.3b: an Equipment can't be attached to an object that isn't on
    the battlefield - the token is still created."""
    scenario = (
        Scenario()
        .player("alice", hand=["U.S.Agent, John Walker"], battlefield=["Plains"] * 4)
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    agent = scenario.cast_and_resolve(
        "U.S.Agent, John Walker", *scenario.untapped_sources(*["Plains"] * 4)
    )
    assert scenario.stack_names(), "the ETB trigger waits on the stack"
    scenario.game.destroy(agent)
    scenario.pass_until_resolved()

    shield = scenario.find("Sturdy Shield", Zone.BATTLEFIELD, "alice")
    assert shield.attached_to is None


# -- Super-Soldier Serum's attack/block attach, verified --------------------------


def test_super_soldier_serum_attaches_equipment_when_its_creature_attacks():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Grizzly Bears", "Super-Soldier Serum", "Quick-Draw Dagger", "Super Suit"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.find("Super-Soldier Serum", Zone.BATTLEFIELD, "alice").attach_to(bears)
    dagger = scenario.find("Quick-Draw Dagger", Zone.BATTLEFIELD, "alice")
    suit = scenario.find("Super Suit", Zone.BATTLEFIELD, "alice")
    scenario.choose_trigger_targets("Super-Soldier Serum", [dagger, suit])
    scenario.advance()
    scenario.advance()
    scenario.attack_with(bears)
    scenario.pass_until_resolved()

    assert dagger.attached_to == bears.id
    assert suit.attached_to == bears.id
    # 2/2 + Serum +2/+2 + Dagger +1/+1 + Suit +1/+2
    assert _pt(scenario, bears) == (6, 7)


# -- put an artifact onto the battlefield, attach if it's an Equipment -------------


def _iron_man_board(hand):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=hand, battlefield=["Tony Stark // The Invincible Iron Man"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    tony = scenario.creature("Tony Stark", "alice")
    tony.transform()
    assert tony.name == "The Invincible Iron Man"
    return scenario, tony


def test_iron_man_puts_an_equipment_from_hand_onto_the_battlefield_attached():
    scenario, iron_man = _iron_man_board(["Quick-Draw Dagger"])
    scenario.will_take_the_may(True)
    scenario.advance()
    assert scenario.step is Step.BEGINNING_OF_COMBAT
    scenario.pass_until_resolved()

    dagger = scenario.find("Quick-Draw Dagger", Zone.BATTLEFIELD, "alice")
    assert dagger.attached_to == iron_man.id
    assert _pt(scenario, iron_man) == (6, 6)


def test_iron_man_puts_a_non_equipment_artifact_onto_the_battlefield_unattached():
    scenario, iron_man = _iron_man_board(["Master Transmuter"])
    scenario.will_take_the_may(True)
    scenario.advance()
    scenario.pass_until_resolved()

    transmuter = scenario.find("Master Transmuter", Zone.BATTLEFIELD, "alice")
    assert transmuter.attached_to is None


def test_iron_man_may_decline():
    scenario, iron_man = _iron_man_board(["Quick-Draw Dagger"])
    scenario.will_take_the_may(False)
    scenario.advance()
    scenario.pass_until_resolved()

    assert scenario.find("Quick-Draw Dagger", Zone.HAND, "alice") is not None


def test_iron_man_with_no_artifact_in_hand_does_nothing():
    scenario, iron_man = _iron_man_board(["Grizzly Bears"])
    scenario.will_take_the_may(True)
    scenario.advance()
    scenario.pass_until_resolved()
    assert scenario.find("Grizzly Bears", Zone.HAND, "alice") is not None


# -- return from graveyard with a finality counter, then may attach ---------------


def test_winter_soldier_returns_with_a_finality_counter_and_takes_an_equipment():
    scenario = (
        Scenario()
        .player(
            "alice",
            graveyard=["Winter Soldier, Icy Assassin"],
            battlefield=["Quick-Draw Dagger", "Plains", "Plains", "Plains", "Swamp", "Swamp"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    soldier = scenario.find("Winter Soldier, Icy Assassin", Zone.GRAVEYARD, "alice")
    dagger = scenario.find("Quick-Draw Dagger", Zone.BATTLEFIELD, "alice")
    scenario.will_take_the_may(True)
    scenario.will_choose_cards(dagger)
    scenario.activate(
        soldier, *scenario.untapped_sources("Plains", "Plains", "Plains", "Swamp", "Swamp")
    )
    scenario.pass_until_resolved()

    returned = scenario.creature("Winter Soldier, Icy Assassin", "alice")
    assert returned.counters["finality"] == 1
    assert dagger.attached_to == returned.id
    # 2/2 + Dagger +1/+1 + 2 for the attached Equipment
    assert _pt(scenario, returned) == (5, 3)


def test_winter_soldier_may_return_without_an_attach():
    scenario = (
        Scenario()
        .player(
            "alice",
            graveyard=["Winter Soldier, Icy Assassin"],
            battlefield=["Quick-Draw Dagger", "Plains", "Plains", "Plains", "Swamp", "Swamp"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    soldier = scenario.find("Winter Soldier, Icy Assassin", Zone.GRAVEYARD, "alice")
    dagger = scenario.find("Quick-Draw Dagger", Zone.BATTLEFIELD, "alice")
    scenario.will_take_the_may(False)
    scenario.activate(
        soldier, *scenario.untapped_sources("Plains", "Plains", "Plains", "Swamp", "Swamp")
    )
    scenario.pass_until_resolved()

    returned = scenario.creature("Winter Soldier, Icy Assassin", "alice")
    assert returned.counters["finality"] == 1
    assert dagger.attached_to is None


def test_the_finality_counter_exiles_him_when_he_would_die():
    scenario = (
        Scenario()
        .player(
            "alice",
            graveyard=["Winter Soldier, Icy Assassin"],
            battlefield=["Plains", "Plains", "Plains", "Swamp", "Swamp"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    soldier = scenario.find("Winter Soldier, Icy Assassin", Zone.GRAVEYARD, "alice")
    scenario.will_take_the_may(False)
    scenario.activate(
        soldier, *scenario.untapped_sources("Plains", "Plains", "Plains", "Swamp", "Swamp")
    )
    scenario.pass_until_resolved()
    returned = scenario.creature("Winter Soldier, Icy Assassin", "alice")

    scenario.game.destroy(returned)

    assert scenario.find("Winter Soldier, Icy Assassin", Zone.EXILE, "alice") is not None


def test_resolute_strike_may_attach_an_equipment_to_a_warrior():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Resolute Strike"],
            battlefield=["Okoye, Dora Milaje Leader", "Quick-Draw Dagger", "Plains"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    okoye = scenario.creature("Okoye, Dora Milaje Leader", "alice")
    dagger = scenario.find("Quick-Draw Dagger", Zone.BATTLEFIELD, "alice")
    scenario.will_take_the_may(True)
    scenario.will_choose_cards(dagger)
    scenario.cast_and_resolve(
        "Resolute Strike", *scenario.untapped_sources("Plains"), targets=[okoye]
    )

    assert dagger.attached_to == okoye.id


def test_every_clause_of_the_listed_cards_is_handled():
    for name in (
        "Falcon's Wing Harness",
        "U.S.Agent, John Walker",
        "Stolen Stark Tech",
        "Super Suit",
        "Super-Soldier Serum",
        "Tony Stark // The Invincible Iron Man",
        "Winter Soldier, Icy Assassin",
        "Quick-Draw Dagger",
        "Galadhrim Bow",
        "Resolute Strike",
    ):
        for clause in card_support(card(name)).clauses:
            assert clause.outcome == "handled", (name, clause.text, clause.outcome)
