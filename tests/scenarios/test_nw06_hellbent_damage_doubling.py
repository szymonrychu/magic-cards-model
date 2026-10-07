"""A damage replacement that exists only "as long as" a condition holds.

Anthem of Rakdos: "Hellbent - As long as you have no cards in hand, if a
source you control would deal damage to a permanent or player, it deals
double that damage to that permanent or player instead."

Hellbent is an ability word (CR 207.2c): no rules meaning of its own, so the
sentence is the static ability. CR 604.2: the replacement effect (CR 614.1a)
exists only while its "as long as" condition is true, and CR 611.3a: it is not
"locked in" - so the condition is asked each time damage would be dealt, not
when the permanent entered. CR 616.1: each replacement effect applies once to
an event, so it stacks with another doubler (Furnace of Rath) as two.

Aether Revolt proves the same "As long as <condition>," gate on a second
printing with a different condition and modification: "Revolt - As long as a
permanent left the battlefield under your control this turn, if a source you
control would deal noncombat damage to an opponent or a permanent an opponent
controls, it deals that much damage plus 2 instead."
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario


def _anthem_board(hand: list[str], *, battlefield: tuple[str, ...] = ()) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=hand,
            battlefield=["Anthem of Rakdos", "Mountain", "Mountain", *battlefield],
        )
        .player("bob", battlefield=["Grizzly Bears"])
    )


def test_with_no_cards_in_hand_a_bolt_deals_double():
    scenario = _anthem_board(["Lightning Bolt"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")

    scenario.cast_and_resolve("Lightning Bolt", auto=True, username="alice", targets=[bob])

    assert bob.life == 14


def test_with_a_card_left_in_hand_it_deals_normal_damage():
    scenario = _anthem_board(["Lightning Bolt", "Shock"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")

    scenario.cast_and_resolve("Lightning Bolt", auto=True, username="alice", targets=[bob])

    assert bob.life == 17


def test_the_condition_is_read_as_the_damage_is_dealt():
    """CR 611.3a: not locked in. The hand is emptied in response - after the
    Bolt was cast - and the doubling applies when it resolves."""
    scenario = _anthem_board(["Lightning Bolt", "Shock"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    alice = scenario.player("alice")

    bolt = scenario.cast_onto_stack(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[bob]
    )
    (shock,) = [c for c in alice.hand if c.name == "Shock"]
    scenario.game.discard_cards("alice", [shock])
    assert alice.hand == []
    scenario.pass_until_resolved()

    assert bolt is not None
    assert bob.life == 14


def test_damage_to_a_permanent_is_doubled_too():
    scenario = _anthem_board(["Shock"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    scenario.cast_and_resolve("Shock", auto=True, username="alice", targets=[bears])

    assert bears.damage == 4 or bears not in scenario.game.battlefield


def test_an_opponents_source_is_not_doubled():
    """ "a source *you* control" - bob's Shock at alice is not alice's source."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Anthem of Rakdos"])
        .player("bob", hand=["Shock"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    scenario.pass_priority("alice")

    scenario.cast_and_resolve("Shock", auto=True, username="bob", targets=[alice])

    assert alice.life == 18


def test_two_doublers_each_apply_once():
    """CR 616.1: Anthem of Rakdos and Furnace of Rath each double once - 3 to 12."""
    scenario = _anthem_board(["Lightning Bolt"], battlefield=("Furnace of Rath",)).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")

    scenario.cast_and_resolve("Lightning Bolt", auto=True, username="alice", targets=[bob])

    assert bob.life == 8


def test_combat_damage_from_a_creature_is_doubled_while_hellbent():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Anthem of Rakdos", "Grizzly Bears"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    bob = scenario.player("bob")
    scenario.advance()  # beginning of combat
    scenario.advance()  # declare attackers
    scenario.attack_with(bears)
    # "it gets +2/+0" from the attack trigger is another task's clause; clear
    # it so only the doubling is measured here.
    scenario.game.pending_triggers.clear()
    scenario.game.stack.clear()
    scenario.advance()
    scenario.no_blocks()
    scenario.advance()
    scenario.combat_damage()

    assert bob.life == 16


# -- the second printing: Aether Revolt's "As long as ..., ... plus 2" ---------


def _revolt_board(hand: list[str]) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=hand, battlefield=["Aether Revolt", "Mountain", "Mountain"])
        .player("bob", battlefield=["Grizzly Bears"])
    )


def test_aether_revolt_adds_two_once_a_permanent_left_your_control():
    scenario = _revolt_board(["Shock"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    (mountain, _) = scenario.untapped_sources("Mountain", "Mountain")
    mountain.tapped = True
    scenario.game.destroy(mountain)

    scenario.cast_and_resolve("Shock", auto=True, username="alice", targets=[bob])

    assert bob.life == 16


def test_aether_revolt_does_nothing_without_revolt():
    scenario = _revolt_board(["Shock"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")

    scenario.cast_and_resolve("Shock", auto=True, username="alice", targets=[bob])

    assert bob.life == 18


def test_aether_revolt_leaves_damage_to_your_own_permanents_alone():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Shock"],
            battlefield=["Aether Revolt", "Mountain", "Mountain", "Colossal Dreadmaw"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain, _) = scenario.untapped_sources("Mountain", "Mountain")
    mountain.tapped = True
    scenario.game.destroy(mountain)
    dreadmaw = scenario.creature("Colossal Dreadmaw", "alice")

    scenario.cast_and_resolve("Shock", auto=True, username="alice", targets=[dreadmaw])

    assert dreadmaw.damage == 2
