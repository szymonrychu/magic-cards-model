""" "attach target Equipment you control to up to one target creature you
control" and "attach any number of target Equipment you control to target
creature you control", with the reflexive "When one or more Equipment become
attached to that creature this way, that creature deals damage equal to its
power to up to one target creature" trigger (CR 701.3a's attach, CR 603.12's
reflexive).

Iron Hills Stalwart: "When this creature enters, attach target Equipment you
control to up to one target creature you control." Thorin, Mountain-king:
"When Thorin enters, attach any number of target Equipment you control to
target creature you control. When one or more Equipment become attached to
that creature this way, that creature deals damage equal to its power to up
to one target creature."
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_iron_hills_stalwart_attaches_target_equipment_to_target_creature():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Iron Hills Stalwart"],
            battlefield=[
                "Dwarven Shortsword",
                "Grizzly Bears",
                "Mountain",
                "Mountain",
                "Mountain",
                "Mountain",
                "Mountain",
            ],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sword = scenario.find("Dwarven Shortsword", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.choose_trigger_targets("Iron Hills Stalwart", [sword, bears])

    sources = scenario.untapped_sources(*["Mountain"] * 5)
    scenario.cast_and_resolve("Iron Hills Stalwart", *sources)
    scenario.pass_until_resolved()

    assert sword.attached_to == bears.id


def test_blacksmiths_talent_level_2_attaches_target_equipment_to_target_creature():
    """Bloomburrow's own printing of the same "attach target Equipment you
    control to up to one target creature you control" template, proof the
    reader is not fitted to Iron Hills Stalwart's own wording. Its own copy
    is a triggered ability ("At the beginning of combat on your turn"), only
    live once the Class has reached level 2 (CR 716.2a)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Blacksmith's Talent"],
            battlefield=["Dwarven Shortsword", "Grizzly Bears"] + ["Mountain"] * 6,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sword = scenario.find("Dwarven Shortsword", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    sources = scenario.untapped_sources("Mountain", "Mountain")
    scenario.cast_and_resolve("Blacksmith's Talent", *sources)
    scenario.pass_until_resolved()
    talent = scenario.find("Blacksmith's Talent", Zone.BATTLEFIELD, "alice")

    level_sources = scenario.untapped_sources("Mountain", "Mountain")
    scenario.activate(talent, *level_sources, index=0)
    scenario.pass_until_resolved()
    assert talent.class_level == 2

    scenario.choose_trigger_targets("Blacksmith's Talent", [sword, bears])
    scenario.advance()
    scenario.pass_until_resolved()

    assert sword.attached_to == bears.id


def test_thorin_attaches_any_number_of_equipment_then_deals_damage():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Thorin, Mountain-king"],
            battlefield=[
                "Dwarven Shortsword",
                "Goblin Plate Mail",
                "Grizzly Bears",
                "Mountain",
                "Mountain",
                "Mountain",
                "Mountain",
            ],
        )
        .player("bob", battlefield=["Watchwolf"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sword = scenario.find("Dwarven Shortsword", Zone.BATTLEFIELD, "alice")
    mail = scenario.find("Goblin Plate Mail", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    watchwolf = scenario.creature("Watchwolf", "bob")
    scenario.choose_trigger_targets("Thorin, Mountain-king", [sword, mail, bears])
    scenario.will_choose_targets(watchwolf)

    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain", "Mountain")
    scenario.cast_and_resolve("Thorin, Mountain-king", *sources)
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()

    assert sword.attached_to == bears.id
    assert mail.attached_to == bears.id
    assert watchwolf.zone is Zone.GRAVEYARD or watchwolf.damage > 0


def test_super_soldier_serum_attaches_any_number_of_equipment_to_enchanted_creature():
    """Marvel's Spider-Man's own printing of the same "attach any number of
    target Equipment you control" template, aimed at the enchanted creature
    itself rather than a fresh target - proof the reader is not fitted to
    Thorin's own wording."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Super-Soldier Serum"],
            battlefield=["Dwarven Shortsword", "Grizzly Bears"] + ["Plains"] * 4,
        )
        .player("bob", battlefield=["Watchwolf"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sword = scenario.find("Dwarven Shortsword", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    sources = scenario.untapped_sources("Plains", "Plains", "Plains", "Plains")
    scenario.cast_and_resolve("Super-Soldier Serum", *sources, targets=[bears])
    scenario.pass_until_resolved()

    scenario.advance()  # into declare attackers
    scenario.choose_trigger_targets("Super-Soldier Serum", [sword])
    scenario.attack_with(bears)
    scenario.pass_until_resolved()

    assert sword.attached_to == bears.id


# --------------------------------------------------------------------------
# "If it's a <type>, you may attach an Equipment you control to it." (CR
# 608.2d's own "you may" choice riding a CR 607.1 anaphoric series)
# --------------------------------------------------------------------------
#
# Vow to Erebor: "Untap target creature you control. It gets +2/+2 until end
# of turn. If it's a Dwarf, you may attach an Equipment you control to it."


def test_vow_to_erebor_lets_a_dwarf_pick_up_an_equipment():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Vow to Erebor"],
            battlefield=["Iron Hills Stalwart", "Dwarven Shortsword", "Plains", "Plains"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dwarf = scenario.creature("Iron Hills Stalwart", "alice")
    sword = scenario.find("Dwarven Shortsword", Zone.BATTLEFIELD, "alice")
    dwarf.tap_if_untapped()

    scenario.will_take_the_may(True)
    scenario.will_choose_cards(sword)

    sources = scenario.untapped_sources("Plains", "Plains")
    scenario.cast_and_resolve("Vow to Erebor", *sources, targets=[dwarf])

    assert dwarf.untapped
    assert sword.attached_to == dwarf.id


def test_vow_to_erebor_offers_nothing_for_a_non_dwarf():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Vow to Erebor"],
            battlefield=["Grizzly Bears", "Dwarven Shortsword", "Plains", "Plains"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    sword = scenario.find("Dwarven Shortsword", Zone.BATTLEFIELD, "alice")
    bears.tap_if_untapped()

    sources = scenario.untapped_sources("Plains", "Plains")
    scenario.cast_and_resolve("Vow to Erebor", *sources, targets=[bears])

    assert bears.untapped
    assert sword.attached_to is None


def test_swordsman_attaches_up_to_one_equipment_when_a_villain_enters():
    """Swordsman, Sharp Scoundrel: "Whenever another Villain you control
    enters, attach up to one target Equipment you control to target creature
    you control." - the same attach reader, with CR 115.6's "up to one" on
    the Equipment half instead of the creature half."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Kang, Temporal Tyrant"],
            battlefield=["Swordsman, Sharp Scoundrel", "Bonesplitter", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    splitter = scenario.find("Bonesplitter", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.choose_trigger_targets("Swordsman, Sharp Scoundrel", [splitter, bears])

    scenario.put_onto_battlefield("Kang, Temporal Tyrant", "alice")
    scenario.pass_until_resolved()

    assert splitter.attached_to == bears.id


def test_swordsman_with_no_equipment_chosen_attaches_nothing():
    """ "Up to one" (CR 115.6): zero Equipment is a legal choice, and the
    creature target alone moves nothing."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Kang, Temporal Tyrant"],
            battlefield=["Swordsman, Sharp Scoundrel", "Bonesplitter", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    splitter = scenario.find("Bonesplitter", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.choose_trigger_targets("Swordsman, Sharp Scoundrel", [bears])

    scenario.put_onto_battlefield("Kang, Temporal Tyrant", "alice")
    scenario.pass_until_resolved()

    assert splitter.attached_to is None


def test_swordsman_ignores_a_non_villain():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Llanowar Elves"],
            battlefield=["Swordsman, Sharp Scoundrel", "Bonesplitter", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.put_onto_battlefield("Llanowar Elves", "alice")

    assert scenario.pending_triggers == []
    assert scenario.stack_names() == []


def test_proof_raubahn_attaches_up_to_one_equipment_to_an_attacking_creature():
    """Raubahn, Bull of Ala Mhigo (Modern, Pioneer, Standard; in no deck
    under `magic-cards-model-api/decks/`): "Whenever Raubahn attacks, attach
    up to one target Equipment you control to target attacking creature." -
    a different trigger and a different creature phrase on the same reader."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Raubahn, Bull of Ala Mhigo", "Bonesplitter", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    splitter = scenario.find("Bonesplitter", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    raubahn = scenario.creature("Raubahn, Bull of Ala Mhigo", "alice")
    scenario.will_choose_targets(splitter, bears)

    scenario.attack_with(raubahn, bears)
    scenario.pass_until_resolved()

    assert splitter.attached_to == bears.id
