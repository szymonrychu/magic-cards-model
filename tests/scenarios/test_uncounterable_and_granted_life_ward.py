"""Scenario: a permanent's static "`<Quality>` spells you control can't be
countered." and a group grant of the costed ward "Ward-Pay 2 life."

Hexing Squelcher (ECL) prints both: "Spells you control can't be countered."
and "Other creatures you control have "Ward-Pay 2 life."". The proof
printings are Chimil, the Inner Sun (the same uncounterable static on an
artifact) and Winter, Cursed Rider ("Artifacts you control have "Ward-Pay 2
life."" - the same granted life ward over a different group).

- CR 604.2: a static ability's effect is active as long as the permanent
  with the ability remains on the battlefield - so the protection stops the
  moment Squelcher leaves, and never covers a spell while Squelcher itself
  is only a spell.
- CR 101.2: the "can't" of "can't be countered" takes precedence over the
  counterspell's instruction; the counterspell still resolves, its target
  simply stays on the stack (CR 701.6a is the verb it cannot perform).
- CR 702.21a: ward is a triggered ability - "counter that spell or ability
  unless that player pays [cost]" - here the cost is 2 life.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file: CR 604.2, CR 101.2, CR 701.6a, CR 702.21a.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _counter_war(protector: str, spell: str = "Divination", *, alice_extra=()):
    """Alice casts `spell` with `protector` on her battlefield; Bob answers
    with Counterspell."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[spell],
            battlefield=[protector, "Island", "Island", "Island", *alice_extra],
            library=["Island"] * 5,
        )
        .player("bob", hand=["Counterspell"], battlefield=["Island", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    cast = scenario.cast_onto_stack(spell, auto=True, username="alice")
    scenario.pass_priority("alice")
    scenario.cast_onto_stack("Counterspell", auto=True, username="bob", targets=[cast])
    return scenario, cast


def test_squelcher_stops_counterspell_from_countering_your_spell():
    scenario, divination = _counter_war("Hexing Squelcher")

    scenario.resolve_top()  # Counterspell resolves, and fails to counter

    assert divination.zone is Zone.STACK
    assert scenario.player("bob").graveyard[-1].name == "Counterspell"
    scenario.resolve_top()
    assert divination.zone is Zone.GRAVEYARD
    assert len(scenario.player("alice").hand) == 2, "Divination resolved and drew two"


def test_chimil_is_the_same_static_on_a_different_printing():
    """The proof printing: an artifact, not a creature, with the identical
    line - and a creature spell is covered as well as a noncreature one."""
    scenario, bears = _counter_war("Chimil, the Inner Sun", "Grizzly Bears", alice_extra=["Forest"])

    scenario.resolve_top()

    assert bears.zone is Zone.STACK
    scenario.resolve_top()
    assert bears.zone is Zone.BATTLEFIELD


def test_an_opponents_spell_is_not_protected():
    """ "Spells you control" - Bob's spell is countered normally."""
    scenario = (
        Scenario()
        .player(
            "alice", hand=["Counterspell"], battlefield=["Hexing Squelcher", "Island", "Island"]
        )
        .player("bob", hand=["Opt"], battlefield=["Island"], library=["Island"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.pass_priority("alice")
    opt = scenario.cast_onto_stack("Opt", auto=True, username="bob")
    scenario.pass_priority("bob")
    scenario.cast_onto_stack("Counterspell", auto=True, username="alice", targets=[opt])

    scenario.resolve_top()

    assert opt.zone is Zone.GRAVEYARD


def test_protection_ends_when_squelcher_leaves_the_battlefield():
    """CR 604.2: the static is active only while the permanent is on the
    battlefield - once Squelcher is gone, the same Counterspell counters."""
    scenario, divination = _counter_war("Hexing Squelcher")
    squelcher = scenario.creature("Hexing Squelcher", "alice")
    scenario.game.destroy(squelcher)
    assert squelcher.zone is Zone.GRAVEYARD

    scenario.resolve_top()

    assert divination.zone is Zone.GRAVEYARD


def test_an_ability_you_control_is_not_a_spell():
    """Only spells are covered: a ward trigger Alice controls is an ability,
    and "Spells you control" never reaches it."""
    from magic_cards_model.machines.casting_restrictions import spell_protected_from_countering

    scenario, divination = _counter_war("Hexing Squelcher")
    assert spell_protected_from_countering(scenario.game, divination)
    counterspell = scenario.game.stack[-1]
    assert not spell_protected_from_countering(scenario.game, counterspell), (
        "Bob's Counterspell is Bob's - Alice's Squelcher does not protect it"
    )


def _bolt_at_alices(creature: str, *, alice_board, bob_life: int = 20):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=list(alice_board))
        .player("bob", life=bob_life, hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    target = scenario.creature(creature, "alice")
    scenario.pass_priority("alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=[target])
    return scenario, target, bolt


def test_another_creature_gains_ward_pay_two_life_and_paying_lets_the_bolt_through():
    scenario, bears, bolt = _bolt_at_alices(
        "Grizzly Bears", alice_board=["Hexing Squelcher", "Grizzly Bears"]
    )
    assert scenario.stack_names() == ["Lightning Bolt", "Grizzly Bears's triggered ability"]
    scenario.will_pay_the_life(True, username="bob")

    scenario.resolve_top()  # the granted ward trigger

    (question,) = [d for d in scenario.questions_asked() if d.kind is DecisionKind.PAY_LIFE]
    assert question.player == "bob"
    assert question.amount == 2
    assert scenario.player("bob").life == 18
    scenario.resolve_top()
    assert bears.zone is Zone.GRAVEYARD


def test_declining_the_granted_ward_counters_the_bolt():
    scenario, bears, bolt = _bolt_at_alices(
        "Grizzly Bears", alice_board=["Hexing Squelcher", "Grizzly Bears"]
    )
    scenario.will_pay_the_life(False, username="bob")

    scenario.resolve_top()

    assert bolt.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.BATTLEFIELD
    assert scenario.player("bob").life == 20


def test_squelcher_itself_has_only_its_printed_ward():
    """ "Other creatures" - Squelcher is not granted a second ward instance
    by its own line, so one trigger, not two."""
    scenario, squelcher, _bolt = _bolt_at_alices(
        "Hexing Squelcher", alice_board=["Hexing Squelcher"]
    )
    assert scenario.stack_names() == ["Lightning Bolt", "Hexing Squelcher's triggered ability"]


def test_the_grant_reaches_only_your_own_creatures():
    """Bob's own creature, targeted by Bob, has no ward - and ward only
    triggers for an opponent's spell anyway."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Hexing Squelcher"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain", "Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.pass_priority("alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=[bears])
    assert scenario.stack_names() == ["Lightning Bolt"]


def test_the_grant_ends_when_squelcher_leaves():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Hexing Squelcher", "Grizzly Bears"])
        .player("bob", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.destroy(scenario.creature("Hexing Squelcher", "alice"))
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.pass_priority("alice")
    (mountain,) = scenario.untapped_sources("Mountain", username="bob")
    scenario.cast_onto_stack("Lightning Bolt", mountain, username="bob", targets=[bears])
    assert scenario.stack_names() == ["Lightning Bolt"]


def test_winter_grants_the_same_life_ward_to_artifacts():
    """The proof printing: Winter, Cursed Rider's "Artifacts you control have
    "Ward-Pay 2 life."" reaches Ornithopter the same way."""
    scenario, thopter, bolt = _bolt_at_alices(
        "Ornithopter", alice_board=["Winter, Cursed Rider", "Ornithopter"]
    )
    scenario.will_pay_the_life(True, username="bob")

    scenario.resolve_top()

    assert scenario.player("bob").life == 18
    scenario.resolve_top()
    assert thopter.zone is Zone.GRAVEYARD
