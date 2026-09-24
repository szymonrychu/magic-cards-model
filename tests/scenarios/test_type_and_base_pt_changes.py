"""Type changes riding on a base power/toughness set or a pump, and doubling.

The listed printings:

- Reptil, Dinomorpher: "Brontosaurus - {3}: Until end of turn, Reptil
  becomes a Dinosaur Hero with base power and toughness 3/5 and gains reach
  and vigilance." (and the {6} 6/6 trample twin). "Becomes a Dinosaur Hero"
  sets the creature types (CR 205.1a: the new subtypes replace the old ones
  of that set), the base P/T is sublayer 7b (CR 613.4b), the keywords layer 6
  (CR 613.1f).
- I Am Iron Man: "Until end of turn, target artifact or creature becomes an
  artifact creature with base power and toughness 4/4 and gains flying. Draw
  a card." - CR 205.1b: an effect that makes an object an "artifact
  creature" lets it retain all its prior card types and subtypes.
- Undercover Skrull: "As long as there are two or more creature cards in
  your graveyard, this creature gets +2/+2 and is all creature types."
- Iron Man Armor: "{2}: If this Equipment isn't a creature, it becomes a 0/0
  Construct Hero artifact creature with flying and "This creature gets +1/+1
  for each artifact you control" until end of turn." An Equipment that is
  also a creature can't equip a creature (CR 301.5c) and becomes unattached
  as a state-based action (CR 704.5n). Its "When this Equipment enters,
  attach it to target creature you control." is proven here too.
- Epic Fight: "Choose one or both - Double target creature's power and
  toughness until end of turn. / Target creature you control fights target
  creature an opponent controls." CR 701.10b: doubling gives +X/+Y where X
  and Y are the power and toughness as the spell resolves, a 7c modification
  (CR 701.10a, CR 613.4c). CR 701.14a: fighting creatures deal damage equal to
  their power to each other.

Off-set proofs (legal, in no deck list, different wording):

- Mordenkainen's Polymorph: "Until end of turn, target creature becomes a
  Dragon with base power and toughness 4/4 and gains flying." - one creature
  type, a spell subject.
- Stalactite Dagger: "Equipped creature gets +1/+1 and is all creature
  types." - the "is all creature types" rider on an attached subject.
- Great Hall of the Biblioplex: "{5}: If this land isn't a creature, it
  becomes a 2/4 Wizard creature with "Whenever you cast an instant or sorcery
  spell, this creature gets +1/+0 until end of turn." It's still a land." -
  the "if this isn't a creature" gate and a quoted granted ability on a land.
- Choose Your Weapon: "Two-Weapon Fighting - Double target creature's power
  and toughness until end of turn." - the doubling mode on another modal.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Type, Zone
from magic_cards_model.models.card_state import Counter

from .harness import Scenario


def _chars(scenario, permanent):
    return scenario.game.computed_board().of(permanent)


def _pt(scenario, permanent):
    return _chars(scenario, permanent).power_toughness


def _end_turn(scenario):
    scenario.start_at(Step.END_STEP)
    scenario.advance()  # cleanup (CR 514.2)


# -- Reptil, Dinomorpher -----------------------------------------------------


def _reptil(scenario):
    return scenario.creature("Reptil, Dinomorpher", "alice")


def test_reptil_brontosaurus_sets_types_base_pt_and_keywords():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Reptil, Dinomorpher", "Forest", "Forest", "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    reptil = _reptil(scenario)

    scenario.activate(reptil, *scenario.untapped_sources("Forest", "Forest", "Forest"), index=0)
    scenario.pass_until_resolved()

    chars = _chars(scenario, reptil)
    assert chars.power_toughness == (3, 5)
    assert set(chars.subtypes) == {"Dinosaur", "Hero"}  # Human is replaced
    assert "Reach" in chars.abilities
    assert "Vigilance" in chars.abilities


def test_reptil_tyrannosaurus_is_the_six_six_trample_form():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Reptil, Dinomorpher"] + ["Forest"] * 6)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    reptil = _reptil(scenario)

    scenario.activate(reptil, *scenario.untapped_sources(*["Forest"] * 6), index=1)
    scenario.pass_until_resolved()

    chars = _chars(scenario, reptil)
    assert chars.power_toughness == (6, 6)
    assert "Trample" in chars.abilities
    assert "Reach" not in chars.abilities


def test_reptil_later_form_wins_by_timestamp_and_a_counter_applies_on_top():
    """Two 7b sets: the later one wins (CR 613.7); a +1/+1 counter is 7c and
    applies on top of whichever base is current (CR 613.4c)."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Reptil, Dinomorpher"] + ["Forest"] * 9)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    reptil = _reptil(scenario)
    scenario.activate(reptil, *scenario.untapped_sources(*["Forest"] * 6), index=1)
    scenario.pass_until_resolved()
    scenario.activate(reptil, *scenario.untapped_sources(*["Forest"] * 3), index=0)
    scenario.pass_until_resolved()
    scenario.game.add_counters(reptil, Counter.PLUS_ONE, 1)

    chars = _chars(scenario, reptil)
    assert chars.power_toughness == (4, 6)
    # Both grants are still in force - keywords are additive.
    assert "Trample" in chars.abilities
    assert "Reach" in chars.abilities


def test_reptil_returns_to_a_human_hero_after_cleanup():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Reptil, Dinomorpher", "Forest", "Forest", "Forest"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    reptil = _reptil(scenario)
    scenario.activate(reptil, *scenario.untapped_sources("Forest", "Forest", "Forest"), index=0)
    scenario.pass_until_resolved()

    _end_turn(scenario)

    chars = _chars(scenario, reptil)
    assert chars.power_toughness == (1, 2)
    assert set(chars.subtypes) == {"Human", "Hero"}
    assert "Reach" not in chars.abilities


# -- Mordenkainen's Polymorph (off-set proof) --------------------------------


def test_mordenkainens_polymorph_makes_a_four_four_flying_dragon():
    scenario = (
        Scenario()
        .player("alice", hand=["Mordenkainen's Polymorph"], battlefield=["Island", "Island"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.cast_and_resolve(
        "Mordenkainen's Polymorph", *scenario.untapped_sources("Island", "Island"), targets=[bears]
    )

    chars = _chars(scenario, bears)
    assert chars.power_toughness == (4, 4)
    assert chars.subtypes == ("Dragon",)
    assert "Flying" in chars.abilities
    _end_turn(scenario)
    assert _pt(scenario, bears) == (2, 2)
    assert _chars(scenario, bears).subtypes == ("Bear",)


# -- I Am Iron Man -------------------------------------------------------------


def test_i_am_iron_man_animates_a_noncreature_artifact_and_draws():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["I Am Iron Man"],
            battlefield=["Island", "Island", "Island", "Mind Stone"],
            library=["Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "alice")
    hand_before = len(scenario.player("alice").hand)

    scenario.cast_and_resolve(
        "I Am Iron Man", *scenario.untapped_sources("Island", "Island", "Island"), targets=[stone]
    )

    chars = _chars(scenario, stone)
    assert Type.ARTIFACT in chars.types
    assert Type.CREATURE in chars.types
    assert chars.power_toughness == (4, 4)
    assert "Flying" in chars.abilities
    # The draw is the second instruction; the spell itself left the hand.
    assert len(scenario.player("alice").hand) == hand_before
    _end_turn(scenario)
    assert Type.CREATURE not in _chars(scenario, stone).types


def test_i_am_iron_man_on_a_creature_keeps_its_creature_types():
    """CR 205.1b: "artifact creature" retains every prior card type and
    subtype - the Bear stays a Bear, now also an artifact."""
    scenario = (
        Scenario()
        .player("alice", hand=["I Am Iron Man"], battlefield=["Island", "Island", "Island"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.cast_and_resolve(
        "I Am Iron Man", *scenario.untapped_sources("Island", "Island", "Island"), targets=[bears]
    )

    chars = _chars(scenario, bears)
    assert Type.ARTIFACT in chars.types and Type.CREATURE in chars.types
    assert "Bear" in chars.subtypes
    assert chars.power_toughness == (4, 4)


# -- Undercover Skrull ---------------------------------------------------------


def test_undercover_skrull_is_a_one_one_with_fewer_than_two_creature_cards():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Undercover Skrull"], graveyard=["Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    skrull = scenario.creature("Undercover Skrull", "alice")

    chars = _chars(scenario, skrull)
    assert chars.power_toughness == (1, 1)
    assert "Elf" not in chars.subtypes


def test_undercover_skrull_grows_and_is_every_creature_type_at_two():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Undercover Skrull"],
            graveyard=["Grizzly Bears", "Hill Giant", "Lightning Bolt"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    skrull = scenario.creature("Undercover Skrull", "alice")

    chars = _chars(scenario, skrull)
    assert chars.power_toughness == (3, 3)
    assert "Elf" in chars.subtypes and "Dragon" in chars.subtypes


def test_undercover_skrull_only_counts_its_controllers_graveyard():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Undercover Skrull"], graveyard=["Grizzly Bears"])
        .player("bob", graveyard=["Hill Giant", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    skrull = scenario.creature("Undercover Skrull", "alice")

    assert _pt(scenario, skrull) == (1, 1)


# -- Stalactite Dagger (off-set proof) ----------------------------------------


def test_stalactite_dagger_pumps_and_makes_the_equipped_creature_every_type():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Stalactite Dagger", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    dagger = scenario.find("Stalactite Dagger", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    dagger.attach_to(bears)

    chars = _chars(scenario, bears)
    assert chars.power_toughness == (3, 3)
    assert "Goblin" in chars.subtypes and "Bear" in chars.subtypes


# -- Iron Man Armor --------------------------------------------------------------


def test_iron_man_armor_attaches_itself_as_it_enters():
    """VERIFY: "When this Equipment enters, attach it to target creature you
    control." and its static "+2/+1 and has flying"."""
    scenario = (
        Scenario()
        .player("alice", hand=["Iron Man Armor"], battlefield=["Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.choose_trigger_targets("Iron Man Armor", [bears])
    armor = scenario.put_onto_battlefield("Iron Man Armor", "alice")
    scenario.pass_until_resolved()

    assert armor.attached_to == bears.id
    chars = _chars(scenario, bears)
    assert chars.power_toughness == (4, 3)
    assert "Flying" in chars.abilities


def _armor_on_battlefield(scenario_builder):
    scenario = scenario_builder.build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario, scenario.find("Iron Man Armor", Zone.BATTLEFIELD, "alice")


def test_iron_man_armor_becomes_a_construct_hero_counting_artifacts():
    scenario, armor = _armor_on_battlefield(
        Scenario()
        .player("alice", battlefield=["Iron Man Armor", "Mind Stone", "Island", "Island"])
        .player("bob")
    )

    scenario.activate(armor, *scenario.untapped_sources("Island", "Island"), index=0)
    scenario.pass_until_resolved()

    chars = _chars(scenario, armor)
    assert Type.CREATURE in chars.types and Type.ARTIFACT in chars.types
    assert set(chars.subtypes) >= {"Construct", "Hero"}
    assert "Flying" in chars.abilities
    # 0/0 base, +1/+1 for each of the two artifacts alice controls (itself
    # and Mind Stone).
    assert chars.power_toughness == (2, 2)
    _end_turn(scenario)
    assert Type.CREATURE not in _chars(scenario, armor).types


def test_iron_man_armor_becoming_a_creature_falls_off_what_it_equipped():
    """CR 301.5c / CR 704.5n: an Equipment that is also a creature can't
    equip a creature - it becomes unattached as a state-based action."""
    scenario, armor = _armor_on_battlefield(
        Scenario()
        .player("alice", battlefield=["Iron Man Armor", "Grizzly Bears", "Island", "Island"])
        .player("bob")
    )
    bears = scenario.creature("Grizzly Bears", "alice")
    armor.attach_to(bears)

    scenario.activate(armor, *scenario.untapped_sources("Island", "Island"), index=0)
    scenario.pass_until_resolved()
    scenario.state_based_actions()

    assert armor.attached_to is None
    assert _pt(scenario, bears) == (2, 2)


def test_iron_man_armor_already_a_creature_does_nothing_more():
    """ "If this Equipment isn't a creature" is checked as the ability
    resolves; a second activation while animated changes nothing."""
    scenario, armor = _armor_on_battlefield(
        Scenario().player("alice", battlefield=["Iron Man Armor"] + ["Island"] * 4).player("bob")
    )
    scenario.activate(armor, *scenario.untapped_sources("Island", "Island"), index=0)
    scenario.pass_until_resolved()
    effects_before = len(scenario.game.continuous_effects.effects)

    scenario.activate(armor, *scenario.untapped_sources("Island", "Island"), index=0)
    scenario.pass_until_resolved()

    assert len(scenario.game.continuous_effects.effects) == effects_before
    assert _pt(scenario, armor) == (1, 1)


# -- Great Hall of the Biblioplex (off-set proof) -------------------------------


def test_great_hall_becomes_a_wizard_that_grows_on_each_instant():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Great Hall of the Biblioplex", "Mountain"] + ["Island"] * 5,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    hall = scenario.find("Great Hall of the Biblioplex", Zone.BATTLEFIELD, "alice")

    scenario.activate(hall, *scenario.untapped_sources(*["Island"] * 5), index=2)
    scenario.pass_until_resolved()

    chars = _chars(scenario, hall)
    assert Type.LAND in chars.types and Type.CREATURE in chars.types
    assert "Wizard" in chars.subtypes
    assert chars.power_toughness == (2, 4)

    scenario.cast_onto_stack(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=["bob"]
    )
    scenario.pass_until_resolved()  # the granted trigger
    scenario.pass_until_resolved()  # the Bolt

    assert _pt(scenario, hall) == (3, 4)


# -- Epic Fight / Choose Your Weapon ---------------------------------------------


def _cast_modal(scenario, name, modes, targets, lands):
    casting = scenario.cast(name, username="alice")
    casting.choose_modes(modes)
    casting.choose_targets(targets)
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources(*lands, username="alice"))
    scenario.put_on_stack(casting)
    scenario.pass_until_resolved()


def test_epic_fight_doubles_power_and_toughness_until_end_of_turn():
    scenario = (
        Scenario()
        .player("alice", hand=["Epic Fight"], battlefield=["Hill Giant"] + ["Forest"] * 3)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "alice")

    _cast_modal(scenario, "Epic Fight", [1], [giant], ["Forest"] * 3)

    assert _pt(scenario, giant) == (6, 6)
    _end_turn(scenario)
    assert _pt(scenario, giant) == (3, 3)


def test_epic_fight_doubling_is_fixed_at_resolution():
    """CR 701.10b: +X/+Y where X/Y are read as the spell resolves - a later
    pump is not doubled."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Epic Fight", "Giant Growth"],
            battlefield=["Hill Giant"] + ["Forest"] * 4,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "alice")
    _cast_modal(scenario, "Epic Fight", [1], [giant], ["Forest"] * 3)

    scenario.cast_and_resolve("Giant Growth", *scenario.untapped_sources("Forest"), targets=[giant])

    assert _pt(scenario, giant) == (9, 9)


def test_epic_fight_both_modes_double_then_fight():
    """Both modes, in printed order (CR 700.2): the doubled creature fights."""
    scenario = (
        Scenario()
        .player("alice", hand=["Epic Fight"], battlefield=["Grizzly Bears"] + ["Forest"] * 3)
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    giant = scenario.creature("Hill Giant", "bob")

    _cast_modal(scenario, "Epic Fight", [1, 2], [bears, bears, giant], ["Forest"] * 3)
    scenario.state_based_actions()

    assert bears.zone is Zone.BATTLEFIELD  # 4/4 took 3
    assert giant.zone is Zone.GRAVEYARD  # 3/3 took 4


def test_epic_fight_fight_mode_alone():
    scenario = (
        Scenario()
        .player("alice", hand=["Epic Fight"], battlefield=["Hill Giant"] + ["Forest"] * 3)
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")

    _cast_modal(scenario, "Epic Fight", [2], [giant, bears], ["Forest"] * 3)
    scenario.state_based_actions()

    assert bears.zone is Zone.GRAVEYARD
    assert giant.damage == 2


def test_choose_your_weapon_doubles_an_opponents_creature():
    """The off-set proof's doubling mode: any target creature, not only
    one the caster controls."""
    scenario = (
        Scenario()
        .player("alice", hand=["Choose Your Weapon"], battlefield=["Forest"] * 3)
        .player("bob", battlefield=["Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")

    _cast_modal(scenario, "Choose Your Weapon", [1], [giant], ["Forest"] * 3)

    assert _pt(scenario, giant) == (6, 6)
