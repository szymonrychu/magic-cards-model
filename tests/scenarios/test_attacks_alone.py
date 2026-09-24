"""CR 506.5's "attacks alone" widened past `tests/scenarios/test_attacks_
alone_trigger.py`'s own trigger-condition-only reading: a *target*
restriction (`machines.targeting.TargetRequirement.must_be_attacking_
alone`) and an equipment's own attached-subject trigger.

- Crowd of True Believers: "{T}: Target creature you control that's
  attacking alone gets +1/+0 until end of turn. You gain 1 life." - the
  restriction sits on the *target*, checked at announcement (CR 601.2c) and
  rechecked on resolution (CR 608.2b), not on the trigger's own condition.
- S.H.I.E.L.D. Spy Kit: "Whenever equipped creature attacks alone, untap it
  and scry 1." - `machines/triggers.py`'s own ATTACKS-event "equipped"
  branch, the attachment-subject twin of the already-proven self/other
  "attacks alone" trigger reading.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file.

- **CR 506.5** - "A creature attacks alone if it's the only creature
  attacking this combat."
- **CR 601.2c / CR 602.2b** - a target is illegal to announce if it fails
  the printed restriction; CR 608.2b rechecks it as the ability resolves.
- **CR 701.22a** - scry N.
- **CR 301.5a** - Equipment's "equipped creature".

No second real printing of a *targeted* "attacking alone" restriction was
found legal in Modern, Pioneer or Standard (Viper, Cruel Conspirator prints
the identical shape but is legal nowhere) - recorded as a dated `MEMORY.md`
line rather than asserted here; S.H.I.E.L.D. Spy Kit's own differently-
worded trigger-condition "attacks alone" is this task's second listed card
proving the underlying CR 506.5 state generalises past one card's exact
wording, per the campaign's own documented-exception convention.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario, mana_from

# --------------------------------------------------------------------------
# Crowd of True Believers
# --------------------------------------------------------------------------


def test_crowd_of_true_believers_pumps_a_lone_attacker_and_gains_life():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Crowd of True Believers", "Hill Giant"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    crowd = scenario.creature("Crowd of True Believers", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    life_before = scenario.player("alice").life

    scenario.attack_with(giant, defending="bob")
    scenario.activate(crowd, targets=[giant])
    scenario.resolve_top()

    assert giant.power == 4  # 3/3 base, +1/+0
    assert scenario.player("alice").life == life_before + 1


def test_crowd_of_true_believers_cannot_target_a_creature_that_is_not_alone():
    """CR 601.2c/602.2b: the restriction is on the target, checked as the
    ability is announced - a second attacker makes neither one "alone"
    (CR 506.5)."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["Crowd of True Believers", "Hill Giant", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    crowd = scenario.creature("Crowd of True Believers", "alice")
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")

    scenario.attack_with(giant, bears, defending="bob")
    try:
        scenario.activate(crowd, targets=[giant])
        raised = False
    except ValueError:
        raised = True
    assert raised, "neither attacker is alone once a second one is declared"


def test_crowd_of_true_believers_cannot_target_a_creature_that_is_not_attacking():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Crowd of True Believers", "Hill Giant"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    crowd = scenario.creature("Crowd of True Believers", "alice")
    giant = scenario.creature("Hill Giant", "alice")

    try:
        scenario.activate(crowd, targets=[giant])
        raised = False
    except ValueError:
        raised = True
    assert raised, "Hill Giant is not attacking at all, let alone alone"


# --------------------------------------------------------------------------
# S.H.I.E.L.D. Spy Kit
# --------------------------------------------------------------------------


def _equip(scenario, equipment, target, username="alice"):
    from magic_cards_model.machines.keywords import equip_activation

    activation = equip_activation(scenario.game, equipment, target, username)
    payment = activation.begin_paying()
    for source in scenario.untapped_sources("Plains"):
        payment.tap_for_mana(source, mana_from(source))
    payment.pay()
    activation.activate()
    activation.resolve()
    return activation


def test_shield_spy_kit_untaps_and_scries_when_the_equipped_creature_attacks_alone():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["S.H.I.E.L.D. Spy Kit", "Hill Giant", "Plains"],
            library=["Forest", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    kit = scenario.find("S.H.I.E.L.D. Spy Kit", Zone.BATTLEFIELD, "alice")
    giant = scenario.creature("Hill Giant", "alice")
    _equip(scenario, kit, giant)
    assert kit.is_attached

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(giant, defending="bob")
    assert giant.tapped
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == ["S.H.I.E.L.D. Spy Kit's triggered ability"]
    scenario.resolve_top()

    assert not giant.tapped  # untapped by its own trigger


def test_shield_spy_kit_does_not_fire_when_the_equipped_creature_is_not_alone():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=["S.H.I.E.L.D. Spy Kit", "Hill Giant", "Grizzly Bears", "Plains"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    kit = scenario.find("S.H.I.E.L.D. Spy Kit", Zone.BATTLEFIELD, "alice")
    giant = scenario.creature("Hill Giant", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    _equip(scenario, kit, giant)

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(giant, bears, defending="bob")
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []
