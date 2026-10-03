"""Scenario: a kicker-specific enter trigger that taps a target untapped
creature, which then deals damage equal to its power to its controller (Ana
Battlemage's {1}{B} kicker), and the same rider on a spell (Traitor's Roar).

    When this creature enters, if it was kicked with its {1}{B} kicker, tap
    target untapped creature and that creature deals damage equal to its power
    to its controller.

    Tap target untapped creature. It deals damage equal to its power to its
    controller.

Rules read whole with `mise run rules:find` in the session that wrote this:

- **CR 702.33a/702.33b/702.33d/702.33f** - kicker (and/or) is two kicker costs;
  "kicked with its [A] kicker" is linked to that one cost.
- **CR 603.4** - an intervening "if" false as the event occurs never triggers.
- **CR 120.3** - damage dealt to a player makes them lose that much life.
- **CR 120.1** - the object that deals damage is the damage's source (here
  the tapped creature, not the spell/trigger source).
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario

LANDS = ["Forest", "Forest", "Forest", "Swamp", "Swamp", "Island", "Island", "Island"]


def _board(*, alice_creatures=(), bob_creatures=(), hand=("Ana Battlemage",), lands=LANDS):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=[*lands, *alice_creatures],
            hand=list(hand),
            library=["Plains"] * 8,
        )
        .player("bob", battlefield=list(bob_creatures), hand=["Plains"] * 5, library=["Plains"] * 8)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_ana(scenario, kickers, targets=()):
    for target in targets:
        scenario.will_choose_targets(target)
    casting = scenario.cast("Ana Battlemage", "alice")
    for which in kickers:
        casting.pay_kicker(1, which=which)
    payment = casting.begin_paying()
    lands = {
        (): ["Forest"] * 3,
        ("{1}{B}",): ["Forest", "Forest", "Forest", "Swamp", "Swamp"],
        ("{2}{U}",): ["Forest", "Forest", "Forest", "Island", "Island", "Island"],
    }.get(tuple(kickers), LANDS)
    scenario.pay_with(payment, *scenario.untapped_sources(*lands))
    scenario.put_on_stack(casting)
    scenario.resolve_top()


def _triggers(scenario):
    scenario.game.put_triggers_on_stack()
    return [n for n in scenario.stack_names() if n.endswith("triggered ability")]


def test_black_kicker_taps_and_the_creature_hits_its_controller():
    scenario = _board(bob_creatures=["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "bob")
    _cast_ana(scenario, ["{1}{B}"], [bears])
    assert _triggers(scenario) == ["Ana Battlemage's triggered ability"]
    scenario.pass_until_resolved()
    assert bears.tapped
    assert scenario.player("bob").life == 18
    assert scenario.player("alice").life == 20


def test_the_creature_can_be_the_casters_own_and_hits_the_caster():
    scenario = _board(alice_creatures=["Hill Giant"])
    giant = scenario.creature("Hill Giant", "alice")
    _cast_ana(scenario, ["{1}{B}"], [giant])
    _triggers(scenario)
    scenario.pass_until_resolved()
    assert giant.tapped
    assert scenario.player("alice").life == 17


def test_not_kicked_never_triggers():
    scenario = _board(bob_creatures=["Grizzly Bears"])
    _cast_ana(scenario, [])
    assert _triggers(scenario) == []
    assert scenario.player("bob").life == 20


def test_only_the_blue_kicker_does_not_run_the_tap_ability():
    scenario = _board(bob_creatures=["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "bob")
    _cast_ana(scenario, ["{2}{U}"], ["bob"])
    assert _triggers(scenario) == ["Ana Battlemage's triggered ability"]
    scenario.pass_until_resolved()
    assert not bears.tapped
    assert scenario.player("bob").life == 20


def test_both_kickers_run_both_abilities():
    scenario = _board(bob_creatures=["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "bob")
    _cast_ana(scenario, ["{2}{U}", "{1}{B}"], ["bob", bears])
    scenario.will_discard(*scenario.player("bob").hand[:3], username="bob")
    assert _triggers(scenario) == [
        "Ana Battlemage's triggered ability",
        "Ana Battlemage's triggered ability",
    ]
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()
    assert bears.tapped
    assert scenario.player("bob").life == 18
    assert len(scenario.player("bob").hand) == 2  # five cards, discard three


def test_a_tapped_creature_is_not_a_legal_target():
    scenario = _board(bob_creatures=["Grizzly Bears", "Hill Giant"])
    bears = scenario.creature("Grizzly Bears", "bob")
    giant = scenario.creature("Hill Giant", "bob")
    giant.tapped = True
    _cast_ana(scenario, ["{1}{B}"])
    _triggers(scenario)
    # The only legal target is chosen for the controller: the tapped Giant is not one.
    assert [t.card_id for t in scenario.game.stack[-1].targets] == [bears.id]
    scenario.pass_until_resolved()
    assert scenario.player("bob").life == 18


def test_zero_power_creature_taps_but_deals_no_damage():
    scenario = _board(bob_creatures=["Wall of Omens"])
    wall = scenario.creature("Wall of Omens", "bob")
    _cast_ana(scenario, ["{1}{B}"], [wall])
    _triggers(scenario)
    scenario.pass_until_resolved()
    assert wall.tapped
    assert scenario.player("bob").life == 20


def test_power_is_read_as_it_resolves():
    scenario = _board(
        bob_creatures=["Grizzly Bears"],
        hand=("Ana Battlemage", "Giant Growth"),
        lands=[*LANDS, "Forest"],
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    _cast_ana(scenario, ["{1}{B}"], [bears])
    _triggers(scenario)
    scenario.cast_and_resolve("Giant Growth", *scenario.untapped_sources("Forest"), targets=[bears])
    scenario.pass_until_resolved()
    assert scenario.player("bob").life == 15


def test_target_gone_before_resolution_does_nothing():
    scenario = _board(bob_creatures=["Grizzly Bears"])
    bears = scenario.creature("Grizzly Bears", "bob")
    _cast_ana(scenario, ["{1}{B}"], [bears])
    _triggers(scenario)
    scenario.game.put_into_graveyard(bears)
    scenario.pass_until_resolved()
    assert scenario.player("bob").life == 20


# -- second printing: Traitor's Roar, a spell with the same rider -----------------------


def test_traitors_roar_taps_and_the_creature_hits_its_controller():
    scenario = _board(
        bob_creatures=["Grizzly Bears"], hand=("Traitor's Roar",), lands=["Swamp"] * 5
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.cast_and_resolve(
        "Traitor's Roar", *scenario.untapped_sources(*["Swamp"] * 5), targets=[bears]
    )
    assert bears.tapped
    assert scenario.player("bob").life == 18
