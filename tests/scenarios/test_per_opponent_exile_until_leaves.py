"""Scenario: "For each opponent, exile up to one target <description> that
player controls[ until this <permanent> leaves the battlefield | and that
player gains life equal to its power]."

"For each opponent" prints one target per opponent (CR 601.2c/603.3d target
every instance of "target"; CR 102.3's opponents are every player not on
the controller's team), each "up to one" (CR 115.6 lets zero be chosen). The
"until" form is CR 610.3's one-shot exile with a return: when the permanent
leaves the battlefield, each card exiled this way returns under its owner's
control (CR 610.3c). If the source has already left the battlefield when the
triggered ability resolves, nothing is exiled at all (CR 610.3b). The "gains
life" rider names "that
player" - the exiled permanent's controller - and "its power" is the exiled
creature's last known power (CR 608.2h).

Printings: Celebrate the Mountain-king ("nonland permanent", "until this
enchantment leaves the battlefield"), off-set Luminate Primordial
("creature", "and that player gains life equal to its power").

CR numbers verified with `mise run rules:find`: 601.2c, 603.3d, 102.3,
115.6, 610.3, 610.3b, 610.3c, 608.2h.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario

CELEBRATE = "Celebrate the Mountain-king"
LUMINATE = "Luminate Primordial"


def test_both_printings_are_handled():
    for name in (CELEBRATE, LUMINATE):
        triggered = [c for c in card_support(card(name)).clauses if c.kind == "triggered"]
        assert triggered and all(c.outcome == "handled" for c in triggered), name


def _three_players(alice_hand: list[str], alice_lands: list[str]):
    return (
        Scenario()
        .player("alice", hand=alice_hand, battlefield=alice_lands, library=["Plains"] * 5)
        .player(
            "bob", battlefield=["Grizzly Bears", "Mind Stone", "Forest"], library=["Forest"] * 3
        )
        .player("carol", battlefield=["Hill Giant"], library=["Forest"] * 3)
        .build()
    )


def _enter_celebrate(scenario, targets):
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.choose_trigger_targets(CELEBRATE, targets)
    scenario.will_discard(scenario.player("alice").library[0], username="alice")
    scenario.cast_onto_stack(CELEBRATE, auto=True)
    while scenario.stack_names() or scenario.game.pending_triggers:
        scenario.game.put_triggers_on_stack()
        scenario.pass_until_resolved()


def test_one_nonland_permanent_of_each_opponent_is_exiled_and_returns_when_it_leaves():
    scenario = _three_players([CELEBRATE], ["Plains"] * 4)
    bears = scenario.creature("Grizzly Bears", "bob")
    giant = scenario.creature("Hill Giant", "carol")
    _enter_celebrate(scenario, [bears, giant])
    assert bears.zone is Zone.EXILE and giant.zone is Zone.EXILE

    celebrate = scenario.find(CELEBRATE, Zone.BATTLEFIELD, "alice")
    scenario.game.destroy(celebrate)
    scenario.game.put_triggers_on_stack()
    while scenario.stack_names():
        scenario.pass_until_resolved()
    assert scenario.creature("Grizzly Bears", "bob").controller == "bob"
    assert scenario.creature("Hill Giant", "carol").controller == "carol"


def test_up_to_one_lets_an_opponent_be_skipped():
    scenario = _three_players([CELEBRATE], ["Plains"] * 4)
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "bob")
    _enter_celebrate(scenario, [stone])
    assert stone.zone is Zone.EXILE
    assert scenario.creature("Hill Giant", "carol").zone is Zone.BATTLEFIELD


def test_two_permanents_of_one_opponent_cannot_both_be_chosen():
    scenario = _three_players([CELEBRATE], ["Plains"] * 4)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "bob")
    assert scenario.game.why_cannot_target_with_trigger(CELEBRATE, [bears, stone]) is not None


def test_a_land_cannot_be_chosen():
    from magic_cards_model.machines.targeting import profile_for_text

    text = card(CELEBRATE).oracle_text.split("\n")[0]
    (requirement,) = profile_for_text(text).requirements
    assert "nonland" in requirement.phrase


# -- Luminate Primordial: the life rider, no return --------------------------


def test_luminate_exiles_each_opponents_creature_and_that_player_gains_its_power():
    scenario = _three_players([LUMINATE], ["Plains"] * 7)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    giant = scenario.creature("Hill Giant", "carol")
    scenario.choose_trigger_targets(LUMINATE, [bears, giant])
    scenario.cast_onto_stack(LUMINATE, auto=True)
    while scenario.stack_names() or scenario.game.pending_triggers:
        scenario.game.put_triggers_on_stack()
        scenario.pass_until_resolved()
    assert bears.zone is Zone.EXILE and giant.zone is Zone.EXILE
    assert scenario.player("bob").life == 22
    assert scenario.player("carol").life == 23
    assert scenario.player("alice").life == 20


def test_nothing_is_exiled_if_the_enchantment_left_before_the_trigger_resolved():
    """CR 610.3b: the specified event (leaving the battlefield) already
    happened after the ability triggered, so the object doesn't move."""
    scenario = _three_players([CELEBRATE, "Krosan Grip"], ["Plains"] * 4 + ["Forest"] * 3)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.choose_trigger_targets(CELEBRATE, [bears])
    scenario.will_discard(scenario.player("alice").library[0], username="alice")
    scenario.cast_onto_stack(CELEBRATE, *scenario.untapped_sources(*["Plains"] * 4))
    scenario.pass_until_resolved()  # the enchantment resolves; triggers wait
    scenario.game.put_triggers_on_stack()
    celebrate = scenario.find(CELEBRATE, Zone.BATTLEFIELD, "alice")
    scenario.cast_onto_stack("Krosan Grip", auto=True, targets=[celebrate])
    scenario.pass_until_resolved()  # Krosan Grip
    while scenario.stack_names():
        scenario.pass_until_resolved()
    assert bears.zone is Zone.BATTLEFIELD
