"""Self pumps counted off the board (CR 613.4c, sublayer 7c), recounted on
every computation of the board (CR 611.3a, CR 613.5).

- "`<this>` gets +N/+M for each Equipment attached to `<him|it>`" - Winter
  Soldier, Icy Assassin ("+2/+0 ... attached to him"), Loxodon Punisher
  ("This creature gets +2/+2 for each Equipment attached to it.") as the
  second printing. The count is of CR 301.5's Equipment attached to the
  creature itself, never of Equipment its controller merely controls.
- "`<this>` gets +N/+M for each other `<type>` you control" - Iron Man,
  Master of Machines ("+1/+0 for each other artifact you control"), Rat
  Colony ("for each other Rat you control", a subtype) and Leonardo, Big
  Brother ("for each other creature you control") as the second printings:
  "other" leaves the source itself out of its own count.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import equip_activation
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario, mana_from


def _equip(scenario, equipment, target, *mana_sources, username="alice"):
    activation = equip_activation(scenario.game, equipment, target, username)
    payment = activation.begin_paying()
    for source in mana_sources:
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    activation.activate()
    scenario.pass_until_resolved()


def _pt(scenario, state):
    return scenario.game.power_of(state), scenario.game.toughness_of(state)


def test_winter_soldier_gets_two_power_for_each_equipment_attached_to_him():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=[
                "Winter Soldier, Icy Assassin",
                "Quick-Draw Dagger",
                "Stolen Stark Tech",
                "Plains",
                "Plains",
            ],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    soldier = scenario.creature("Winter Soldier, Icy Assassin", "alice")
    dagger = scenario.find("Quick-Draw Dagger", Zone.BATTLEFIELD, "alice")
    tech = scenario.find("Stolen Stark Tech", Zone.BATTLEFIELD, "alice")

    assert _pt(scenario, soldier) == (2, 2), "unequipped Equipment is not attached to him"

    (first,) = scenario.untapped_sources("Plains", username="alice")
    _equip(scenario, dagger, soldier, first)
    # 2/2 + Dagger's +1/+1 + 2 for one Equipment.
    assert _pt(scenario, soldier) == (5, 3)

    (second,) = scenario.untapped_sources("Plains", username="alice")
    _equip(scenario, tech, soldier, second)
    # + Tech's +1/+0 + 2 more for the second Equipment.
    assert _pt(scenario, soldier) == (8, 3)


def test_equipment_attached_to_another_creature_does_not_count():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=[
                "Winter Soldier, Icy Assassin",
                "Grizzly Bears",
                "Quick-Draw Dagger",
                "Plains",
            ],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    soldier = scenario.creature("Winter Soldier, Icy Assassin", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    dagger = scenario.find("Quick-Draw Dagger", Zone.BATTLEFIELD, "alice")

    _equip(scenario, dagger, bears, *scenario.untapped_sources("Plains", username="alice"))

    assert dagger.attached_to == bears.id
    assert _pt(scenario, soldier) == (2, 2)
    assert _pt(scenario, bears) == (3, 3)


def test_an_aura_attached_to_him_is_not_an_equipment():
    """CR 301.5: only an Equipment counts - an Aura on him adds its own bonus
    and nothing else."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Super-Soldier Serum"],
            battlefield=["Winter Soldier, Icy Assassin", "Plains", "Plains"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    soldier = scenario.creature("Winter Soldier, Icy Assassin", "alice")

    scenario.cast_and_resolve(
        "Super-Soldier Serum", *scenario.untapped_sources("Plains", "Plains"), targets=[soldier]
    )

    serum = scenario.find("Super-Soldier Serum", Zone.BATTLEFIELD, "alice")
    assert serum.attached_to == soldier.id
    assert _pt(scenario, soldier) == (4, 4)


def test_loxodon_punisher_gets_plus_two_plus_two_for_each_equipment():
    """The second printing: "it" rather than "him", and a +2/+2 pump."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Loxodon Punisher", "Quick-Draw Dagger", "Plains"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    punisher = scenario.creature("Loxodon Punisher", "alice")
    dagger = scenario.find("Quick-Draw Dagger", Zone.BATTLEFIELD, "alice")
    assert _pt(scenario, punisher) == (2, 2)

    _equip(scenario, dagger, punisher, *scenario.untapped_sources("Plains", username="alice"))

    assert _pt(scenario, punisher) == (5, 5)


def test_the_bonus_goes_away_when_the_equipment_leaves():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Loxodon Punisher", "Quick-Draw Dagger", "Plains"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    punisher = scenario.creature("Loxodon Punisher", "alice")
    dagger = scenario.find("Quick-Draw Dagger", Zone.BATTLEFIELD, "alice")
    dagger.attach_to(punisher)
    assert _pt(scenario, punisher) == (5, 5)

    scenario.game.destroy(dagger)

    assert _pt(scenario, punisher) == (2, 2)


def test_iron_man_counts_every_other_artifact_you_control():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "Iron Man, Master of Machines",
                "Quick-Draw Dagger",
                "Stolen Stark Tech",
                "Plains",
            ],
        )
        .player("bob", battlefield=["Super Suit"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    iron_man = scenario.creature("Iron Man, Master of Machines", "alice")

    # Iron Man is himself an artifact creature: "other" leaves him out, and
    # an opponent's artifact is not one "you control".
    assert _pt(scenario, iron_man) == (3, 4)


def test_iron_man_with_no_other_artifact_is_his_printed_self():
    scenario = (
        Scenario().player("alice", battlefield=["Iron Man, Master of Machines", "Plains"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    iron_man = scenario.creature("Iron Man, Master of Machines", "alice")
    assert _pt(scenario, iron_man) == (1, 4)


def test_rat_colony_counts_other_rats_by_subtype():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Rat Colony", "Rat Colony", "Rat Colony", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    colonies = [s for s in scenario.game.battlefield if s.name == "Rat Colony"]
    # Two *other* Rats each; the Bears is no Rat.
    assert all(_pt(scenario, colony) == (4, 1) for colony in colonies)


def test_leonardo_counts_other_creatures_by_his_own_name():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Leonardo, Big Brother", "Grizzly Bears", "Grizzly Bears"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    leonardo = scenario.creature("Leonardo, Big Brother", "alice")
    assert _pt(scenario, leonardo) == (3, 3)
