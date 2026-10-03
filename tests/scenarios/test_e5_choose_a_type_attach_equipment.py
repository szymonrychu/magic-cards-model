"""Armed and Armored: "Vehicles you control become artifact creatures until
end of turn. Choose a Dwarf you control. Attach any number of Equipment you
control to it."

- **CR 608.2d** the Dwarf is chosen as the spell resolves (no target), and
  "any number" is the player's choice, zero included.
- **CR 701.3b** attaching moves an Equipment from whatever it was on.
- **CR 301.5** an Equipment can be attached only to a creature.
- **CR 301.5b** an Equipment that cannot be attached to the object does not move.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import Scenario

ARMED = "Armed and Armored"


def _board(*, alice_extra=(), bob=()):
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[ARMED],
            battlefield=[
                "Plains",
                "Plains",
                "Seven Dwarves",
                "Grizzly Bears",
                "Bonesplitter",
                "Lightning Greaves",
                "Smuggler's Copter",
                *alice_extra,
            ],
        )
        .player("bob", battlefield=list(bob))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast(scenario):
    return scenario.cast_and_resolve(ARMED, *scenario.untapped_sources("Plains", "Plains"))


def test_vehicles_you_control_become_artifact_creatures():
    scenario = _board()
    copter = scenario.find("Smuggler's Copter", Zone.BATTLEFIELD, "alice")
    assert not scenario.game.characteristics_of(copter).is_creature
    scenario.will_choose_cards(scenario.creature("Seven Dwarves", "alice"), username="alice", source=ARMED)
    scenario.will_choose_cards(username="alice", source=ARMED)
    _cast(scenario)
    assert scenario.game.characteristics_of(copter).is_creature


def test_the_chosen_dwarf_gets_every_equipment_chosen():
    scenario = _board()
    dwarf = scenario.creature("Seven Dwarves", "alice")
    bone = scenario.find("Bonesplitter", Zone.BATTLEFIELD, "alice")
    greaves = scenario.find("Lightning Greaves", Zone.BATTLEFIELD, "alice")
    scenario.will_choose_cards(dwarf, username="alice", source=ARMED)
    scenario.will_choose_cards(bone, greaves, username="alice", source=ARMED)
    _cast(scenario)
    assert bone.attached_to == dwarf.id
    assert greaves.attached_to == dwarf.id
    chars = scenario.game.characteristics_of(dwarf)
    assert (chars.power, chars.toughness) == (4, 2)


def test_fewer_than_all_equipment_may_be_attached():
    scenario = _board()
    dwarf = scenario.creature("Seven Dwarves", "alice")
    bone = scenario.find("Bonesplitter", Zone.BATTLEFIELD, "alice")
    greaves = scenario.find("Lightning Greaves", Zone.BATTLEFIELD, "alice")
    scenario.will_choose_cards(dwarf, username="alice", source=ARMED)
    scenario.will_choose_cards(bone, username="alice", source=ARMED)
    _cast(scenario)
    assert scenario.game.characteristics_of(dwarf).power == 4
    assert greaves.attached_to is None


def test_attaching_none_is_allowed():
    scenario = _board()
    dwarf = scenario.creature("Seven Dwarves", "alice")
    scenario.will_choose_cards(dwarf, username="alice", source=ARMED)
    scenario.will_choose_cards(username="alice", source=ARMED)
    _cast(scenario)
    assert scenario.game.characteristics_of(dwarf).power == 2


def test_equipment_moves_off_the_creature_it_was_on():
    scenario = _board()
    dwarf = scenario.creature("Seven Dwarves", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    bone = scenario.find("Bonesplitter", Zone.BATTLEFIELD, "alice")
    bone.attach_to(bears)
    assert scenario.game.characteristics_of(bears).power == 4
    scenario.will_choose_cards(dwarf, username="alice", source=ARMED)
    scenario.will_choose_cards(bone, username="alice", source=ARMED)
    _cast(scenario)
    assert scenario.game.characteristics_of(bears).power == 2
    assert scenario.game.characteristics_of(dwarf).power == 4


def test_with_no_dwarf_nothing_is_attached_and_nothing_is_asked():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[ARMED],
            battlefield=["Plains", "Plains", "Grizzly Bears", "Bonesplitter"],
        )
        .player("bob", battlefield=["Seven Dwarves"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bone = scenario.find("Bonesplitter", Zone.BATTLEFIELD, "alice")
    _cast(scenario)
    assert bone.attached_to is None
    assert scenario.questions_asked() == []


def test_an_opponents_dwarf_is_not_choosable():
    scenario = _board(bob=["Dwarven Mauler"])
    theirs = scenario.creature("Dwarven Mauler", "bob")
    bone = scenario.find("Bonesplitter", Zone.BATTLEFIELD, "alice")
    dwarf = scenario.creature("Seven Dwarves", "alice")
    scenario.will_choose_cards(dwarf, username="alice", source=ARMED)
    scenario.will_choose_cards(bone, username="alice", source=ARMED)
    _cast(scenario)
    assert not scenario.game.characteristics_of(theirs).power == 4
