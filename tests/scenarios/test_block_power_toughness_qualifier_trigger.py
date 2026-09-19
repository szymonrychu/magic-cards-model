"""Tetsuko Umezawa, Pursuer's own "Whenever a creature an opponent controls
with power or toughness 1 or less blocks, ..." (CR 509.1a, CR 208.1).

`condition_matches`'s BLOCKS branch used to read only the self-referential
"this creature blocks"/"becomes blocked" forms; a non-self condition -
naming the *blocker*, not the source, restricted by controller and by a
power/toughness comparison - matched nothing at all (`sweep_pool`'s
`unmatchable_condition` category). No other printed Magic card combines a
"blocks" condition with a power/toughness qualifier the way Tetsuko does, so
`test_the_power_or_toughness_qualifier_reads_more_than_one_direction_and_stat`
proves the comparison reader itself is not hardcoded to "power or toughness 1
or less" by exercising it against differently shaped clauses directly,
against real battlefield creatures rather than a stand-in for one.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.triggers import _power_or_toughness_qualifier_holds
from tests.scenarios.harness import Scenario


def test_tetsuko_damages_the_controller_of_a_small_blocker():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Tetsuko Umezawa, Pursuer"], life=20)
        .player("bob", battlefield=["Steppe Lynx"], life=20)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    tetsuko = scenario.creature("Tetsuko Umezawa, Pursuer", "alice")
    lynx = scenario.creature("Steppe Lynx", "bob")

    scenario.attack_with(tetsuko, defending="bob")
    scenario.block(tetsuko, lynx)

    scenario.game.put_triggers_on_stack()
    # Only the trigger firing is this stream's own claim - the resolved
    # effect itself ("deals 1 damage to that creature's controller") is an
    # anaphoric targeted-damage clause outside S5's scope.
    assert scenario.stack_names() == ["Tetsuko Umezawa, Pursuer's triggered ability"]


def test_tetsuko_does_not_fire_for_a_big_blocker():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Tetsuko Umezawa, Pursuer"], life=20)
        .player("bob", battlefield=["Grizzly Bears"], life=20)
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    tetsuko = scenario.creature("Tetsuko Umezawa, Pursuer", "alice")
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.attack_with(tetsuko, defending="bob")
    scenario.block(tetsuko, bears)

    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == []


def test_tetsuko_does_not_fire_for_her_own_controllers_small_blocker():
    """The "an opponent controls" clause: bob's own Tetsuko does not care
    that bob's own small creature blocked - only an opponent's small blocker
    counts. Alice, not Tetsuko's controller, is the one attacking here."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears"], life=20)
        .player(
            "bob",
            battlefield=["Tetsuko Umezawa, Pursuer", "Steppe Lynx"],
            life=20,
        )
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    lynx = scenario.creature("Steppe Lynx", "bob")

    scenario.attack_with(bears, defending="bob")
    scenario.block(bears, lynx)

    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == []


def test_the_power_or_toughness_qualifier_reads_more_than_one_direction_and_stat():
    """`_power_or_toughness_qualifier_holds` is not a Tetsuko-shaped regex -
    it reads "power"/"toughness"/"power or toughness" and "or less"/"or
    greater" independently, off whatever a differently worded card would
    print. Read against real battlefield creatures (Grizzly Bears 2/2,
    Steppe Lynx 0/1) rather than a fake object, so this is still the live
    computed board (CR 613.5) the real matcher reads, not a stand-in for it.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears", "Steppe Lynx"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    lynx = scenario.creature("Steppe Lynx", "alice")
    game = scenario.game

    assert _power_or_toughness_qualifier_holds(
        game, "a creature with power 2 or greater blocks", bears.id
    )
    assert not _power_or_toughness_qualifier_holds(
        game, "a creature with power 2 or greater blocks", lynx.id
    )
    assert _power_or_toughness_qualifier_holds(
        game, "a creature with toughness 1 or less blocks", lynx.id
    )
    assert not _power_or_toughness_qualifier_holds(
        game, "a creature with toughness 1 or less blocks", bears.id
    )
    assert _power_or_toughness_qualifier_holds(
        game, "a creature with power or toughness 1 or less blocks", lynx.id
    )
    assert not _power_or_toughness_qualifier_holds(
        game, "a creature with power or toughness 1 or less blocks", bears.id
    )
    # No qualifier at all reads as "nothing to check" (`None`), not a refusal.
    assert _power_or_toughness_qualifier_holds(game, "a creature blocks", bears.id) is None
