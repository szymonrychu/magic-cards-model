"""Doubling the triggered abilities of one kind of source (CR 603.2d), and
the equipment that hands out prowess to go with it:

- Bifur, Melodic Rider: "As long as you have an enduring story, if a
  triggered ability of a Dwarf you control triggers, that ability triggers an
  additional time."
- Wizard's Staff: "Equipped creature has prowess." and "If a triggered
  ability of equipped creature triggers, that ability triggers an additional
  time."
- Harmonic Prodigy (the proof printing, not a Hobbit card and not in any
  deck): "If a triggered ability of a Shaman or another Wizard you control
  triggers, that ability triggers an additional time." - two alternatives and
  an "another" that excludes the Prodigy itself.
- Narset, Enlightened Exile (proof printing): "Creatures you control have
  prowess." - the same granted prowess over a group.

Every rule cited here was read whole with `mise run rules:find` in the
session that wrote this file:

- **CR 603.2d** - "An ability may state that a triggered ability triggers
  additional times. In this case, rather than simply determining that such an
  ability has triggered, determine how many times it should trigger, then
  that ability triggers that many times. ... An effect that states a
  triggered ability of an object triggers additional times refers only to
  triggered abilities that object has, not to any delayed or reflexive
  triggered abilities ..."
- **CR 702.108a** - "Prowess is a triggered ability. 'Prowess' means
  'Whenever you cast a noncreature spell, this creature gets +1/+1 until end
  of turn.'"
- **CR 702.108b** - "If a creature has multiple instances of prowess, each
  triggers separately."
- **CR 301.5a** - "The creature an Equipment is attached to is called the
  'equipped creature.'"
- **CR 301.5d** - "An Equipment's controller is separate from the equipped
  creature's controller; the two need not be the same."
- **CR 702.195b** - the enduring story designation Bifur's gate reads.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import AbilityKind
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

STORY = ["Mox Amber", "Darksteel Relic"]


def _triggers_from(scenario, source) -> list:
    return [
        item
        for item in [*scenario.pending_triggers, *scenario.game.stack]
        if getattr(item, "kind", None) is AbilityKind.TRIGGERED
        and getattr(item, "source_id", None) == source.id
    ]


def _resolve_all(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.pass_until_resolved()


def _bolt_bob(scenario, username: str = "alice") -> None:
    scenario.cast_onto_stack(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username=username)[:1],
        username=username,
        targets=["bob" if username == "alice" else "alice"],
    )


# --------------------------------------------------------------------------
# Bifur: "a Dwarf you control", behind the enduring story
# --------------------------------------------------------------------------


def test_without_a_story_a_dwarf_trigger_triggers_once():
    scenario = (
        Scenario()
        .player("alice", hand=["Fíli the Pathfinder"], battlefield=["Bifur, Melodic Rider"])
        .player("bob")
        .build()
    )
    scenario.game.check_state_based_actions()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    fili = scenario.put_onto_battlefield("Fíli the Pathfinder")
    assert len(_triggers_from(scenario, fili)) == 1


def test_with_a_story_a_dwarf_trigger_triggers_twice():
    scenario = (
        Scenario()
        .player("alice", hand=["Dáin's Company"], battlefield=["Bifur, Melodic Rider", *STORY])
        .player("bob")
        .build()
    )
    scenario.game.check_state_based_actions()
    assert scenario.player("alice").has_enduring_story
    scenario.start_at(Step.PRECOMBAT_MAIN)
    company = scenario.put_onto_battlefield("Dáin's Company")
    triggered = _triggers_from(scenario, company)
    assert len(triggered) == 2
    assert len({item.id for item in triggered}) == 2, "each its own object on the stack"


def test_bifurs_own_attack_trigger_is_a_dwarfs_and_doubles():
    """Bifur is a Dwarf you control too: its own "Whenever Bifur enters or
    attacks" triggers twice when it attacks."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Bifur, Melodic Rider", *STORY])
        .player("bob")
        .build()
    )
    scenario.game.check_state_based_actions()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bifur = scenario.creature("Bifur, Melodic Rider")
    bifur.summoning_sick = False
    scenario.attack_with(bifur)
    assert len(_triggers_from(scenario, bifur)) == 2


def test_a_non_dwarfs_trigger_is_not_doubled():
    """Monastery Swiftspear is a Human Monk: its prowess triggers once."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Bifur, Melodic Rider", "Monastery Swiftspear", "Mountain", *STORY],
        )
        .player("bob")
        .build()
    )
    scenario.game.check_state_based_actions()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _bolt_bob(scenario)
    assert len(_triggers_from(scenario, scenario.creature("Monastery Swiftspear"))) == 1


def test_an_opponents_dwarf_is_not_doubled():
    """ "a Dwarf **you** control": Bob's Dwarf entering triggers once."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Bifur, Melodic Rider", *STORY])
        .player("bob", hand=["Dáin's Company"])
        .build()
    )
    scenario.game.check_state_based_actions()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    company = scenario.put_onto_battlefield("Dáin's Company", "bob")
    assert len(_triggers_from(scenario, company)) == 1


# --------------------------------------------------------------------------
# Wizard's Staff: prowess, and "equipped creature" doubling
# --------------------------------------------------------------------------


def _staffed(*extra: str) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Wizard's Staff", "Grizzly Bears", "Mountain", *extra],
        )
        .player("bob")
    )


def test_an_unattached_staff_grants_nothing():
    scenario = _staffed().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _bolt_bob(scenario)
    assert _triggers_from(scenario, scenario.creature("Grizzly Bears")) == []


def test_the_staff_gives_prowess_and_doubles_it():
    """Equipped Grizzly Bears has prowess, and its prowess is a triggered
    ability of the equipped creature, so it triggers twice - two +1/+1s."""
    scenario = _staffed().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    staff = scenario.find("Wizard's Staff", Zone.BATTLEFIELD, "alice")
    bears = scenario.creature("Grizzly Bears")
    staff.attach_to(bears)
    assert scenario.game.characteristics_of(bears).has_ability("Prowess")
    _bolt_bob(scenario)
    assert len(_triggers_from(scenario, bears)) == 2
    _resolve_all(scenario)
    assert (bears.power, bears.toughness) == (4, 4)


def test_the_staff_doubles_only_the_equipped_creature():
    """Monastery Swiftspear, unequipped, keeps one prowess trigger."""
    scenario = _staffed("Monastery Swiftspear").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    staff = scenario.find("Wizard's Staff", Zone.BATTLEFIELD, "alice")
    staff.attach_to(scenario.creature("Grizzly Bears"))
    _bolt_bob(scenario)
    assert len(_triggers_from(scenario, scenario.creature("Monastery Swiftspear"))) == 1


def test_the_staff_doubles_a_printed_trigger_of_the_equipped_creature():
    """Not only the prowess it grants: Swiftspear's own printed prowess and
    the Staff's granted one each trigger twice - four triggers (CR 702.108b:
    each instance triggers separately)."""
    scenario = _staffed("Monastery Swiftspear").build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    staff = scenario.find("Wizard's Staff", Zone.BATTLEFIELD, "alice")
    swiftspear = scenario.creature("Monastery Swiftspear")
    staff.attach_to(swiftspear)
    _bolt_bob(scenario)
    assert len(_triggers_from(scenario, swiftspear)) == 4


def test_the_staff_doubles_equipped_creature_whoever_controls_it():
    """ "a triggered ability of equipped creature" names the object, not "a
    permanent you control": Alice's Staff on Bob's Swiftspear (control of an
    Equipment and of its creature can differ, CR 301.5d) still doubles both
    of the Swiftspear's prowess triggers when Bob casts a noncreature spell."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Wizard's Staff"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Monastery Swiftspear", "Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    swiftspear = scenario.creature("Monastery Swiftspear", "bob")
    scenario.find("Wizard's Staff", Zone.BATTLEFIELD, "alice").attach_to(swiftspear)
    scenario.pass_priority("alice")
    _bolt_bob(scenario, "bob")
    assert len(_triggers_from(scenario, swiftspear)) == 4


# --------------------------------------------------------------------------
# Proof printings: Harmonic Prodigy and Narset, Enlightened Exile
# --------------------------------------------------------------------------


def test_harmonic_prodigy_does_not_double_its_own_trigger():
    """ "a Shaman or **another** Wizard": the Prodigy is a Wizard, but not
    another one, and not a Shaman."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Lightning Bolt"], battlefield=["Harmonic Prodigy", "Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _bolt_bob(scenario)
    assert len(_triggers_from(scenario, scenario.creature("Harmonic Prodigy"))) == 1


def test_two_harmonic_prodigies_double_each_other():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Harmonic Prodigy", "Harmonic Prodigy", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _bolt_bob(scenario)
    first, second = scenario.creatures("Harmonic Prodigy", "Harmonic Prodigy")
    assert len(_triggers_from(scenario, first)) == 2
    assert len(_triggers_from(scenario, second)) == 2


def test_multipliers_add_up():
    """CR 603.2d counts each effect: Harmonic Prodigy (a Wizard's trigger)
    and Wizard's Staff (the equipped creature's) both apply to a second
    Prodigy carrying the Staff - its prowess triggers 1 + 1 + 1 times, and
    the Staff's granted prowess three times too."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Harmonic Prodigy", "Harmonic Prodigy", "Wizard's Staff", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    first, second = scenario.creatures("Harmonic Prodigy", "Harmonic Prodigy")
    scenario.find("Wizard's Staff", Zone.BATTLEFIELD, "alice").attach_to(second)
    _bolt_bob(scenario)
    assert len(_triggers_from(scenario, second)) == 6
    assert len(_triggers_from(scenario, first)) == 2


def test_narset_gives_every_creature_you_control_prowess():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Lightning Bolt"],
            battlefield=["Narset, Enlightened Exile", "Grizzly Bears", "Mountain"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _bolt_bob(scenario)
    bears = scenario.creature("Grizzly Bears", "alice")
    assert len(_triggers_from(scenario, bears)) == 1
    assert len(_triggers_from(scenario, scenario.creature("Narset, Enlightened Exile"))) == 1
    assert _triggers_from(scenario, scenario.creature("Grizzly Bears", "bob")) == []
    _resolve_all(scenario)
    assert bears.power == 3
