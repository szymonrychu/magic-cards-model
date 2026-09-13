"""A target phrase with a comma list of restrictions, a controller and a
mana value bound, and the linked "the exiled card" ability that reads its exile.

"When this creature enters, exile up to one target nonland, nontoken permanent
you don't control with mana value 4 or less. / When this creature leaves the
battlefield, the exiled card's owner creates an X/X blue Illusion creature
token, where X is the mana value of the exiled card." (Skyclave Apparition)

- **CR 115.6** - "up to one target": zero targets may be chosen.
- **CR 603.3d** - the target is chosen as the trigger goes on the stack.
- **CR 110.4** / CR 111.1 - "nonland" and "nontoken" each rule out a kind of
  permanent; a comma between the two is a list of restrictions that all apply.
- **CR 202.3** - mana value, compared "4 or less".
- **CR 607.2a** / CR 406.6 - "the exiled card" in the second ability refers
  only to a card the first ability exiled, and only that object's own exile.
- **CR 111.2** - "The player who creates a token is its owner", so the token
  belongs to the exiled card's owner, not to the Apparition's controller.

Witherbloom Command's "Destroy target noncreature, nonland permanent with mana
value 2 or less" is not in any deck pool; it proves the phrase reader on a
different comma list, a different verb and bound, and a modal spell's mode.

Every CR number above was read in full from `mise run rules:find` in the
session that wrote this file.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Color, Zone
from magic_cards_model.models.token import TokenDefinition, create_tokens

from .harness import Scenario


def board(bob_battlefield: list[str], alice_hand: list[str] | None = None) -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Skyclave Apparition", "Lightning Bolt", *(alice_hand or [])],
            battlefield=["Plains", "Plains", "Plains", "Mountain", "Grizzly Bears"],
        )
        .player("bob", battlefield=bob_battlefield)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    create_tokens(
        scenario.game,
        TokenDefinition(subtypes=("Soldier",), colors=(Color.WHITE,), power=1, toughness=1),
        "bob",
    )
    return scenario


BOB = ["Grizzly Bears", "Forest", "Alhammarret's Archive", "Ocelot Pride", "Memnite"]


def cast_apparition(scenario: Scenario):
    return scenario.cast_and_resolve(
        "Skyclave Apparition", *scenario.untapped_sources("Plains", "Plains", "Plains")
    )


def target_question(scenario: Scenario):
    (asked,) = [q for q in scenario.questions_asked() if q.kind is DecisionKind.CHOOSE_TARGETS]
    return asked


def bolt(scenario: Scenario, creature) -> None:
    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[creature]
    )
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()


def illusions(scenario: Scenario, controller: str):
    return [
        state
        for state in scenario.game.permanents_controlled_by(controller)
        if state.token and "Illusion" in state.subtypes
    ]


def test_only_nonland_nontoken_permanents_bob_controls_with_mana_value_4_or_less():
    scenario = board(BOB)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.will_choose_targets(bears, username="alice")

    cast_apparition(scenario)
    offered = {
        scenario.game.find_by_id(ref.card_id).name for ref in target_question(scenario).targets
    }
    scenario.pass_until_resolved()

    assert offered == {"Grizzly Bears", "Ocelot Pride", "Memnite"}
    assert target_question(scenario).target_minimum == 0
    assert bears.zone is Zone.EXILE
    assert scenario.game.targeting_notices == []


def test_up_to_one_may_choose_nothing_and_then_no_token_is_made():
    scenario = board(BOB)
    scenario.will_choose_targets(username="alice")

    apparition = cast_apparition(scenario)
    scenario.pass_until_resolved()
    bolt(scenario, apparition)

    assert scenario.creature("Grizzly Bears", "bob").zone is Zone.BATTLEFIELD
    assert illusions(scenario, "bob") == [] and illusions(scenario, "alice") == []


def test_leaving_the_battlefield_gives_the_exiled_cards_owner_an_x_x_blue_illusion():
    scenario = board(BOB)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.will_choose_targets(bears, username="alice")

    apparition = cast_apparition(scenario)
    scenario.pass_until_resolved()
    bolt(scenario, apparition)

    (token,) = illusions(scenario, "bob")
    assert (token.power, token.toughness) == (2, 2)
    assert token.colors == [Color.BLUE] or set(token.colors) == {Color.BLUE}
    assert token.controller == "bob"
    assert illusions(scenario, "alice") == []


def test_a_mana_value_zero_card_makes_a_zero_zero_token_that_dies():
    scenario = board(BOB)
    memnite = scenario.find("Memnite", Zone.BATTLEFIELD, "bob")
    scenario.will_choose_targets(memnite, username="alice")

    apparition = cast_apparition(scenario)
    scenario.pass_until_resolved()
    bolt(scenario, apparition)
    scenario.state_based_actions()

    assert illusions(scenario, "bob") == []
    assert memnite.zone is Zone.EXILE


def test_each_apparition_reads_only_its_own_exiled_card():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Skyclave Apparition", "Skyclave Apparition", "Lightning Bolt"],
            battlefield=["Plains"] * 6 + ["Mountain"],
        )
        .player("bob", battlefield=["Grizzly Bears", "Ocelot Pride"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    ocelot = scenario.creature("Ocelot Pride", "bob")
    scenario.will_choose_targets(bears, username="alice")
    first = cast_apparition(scenario)
    scenario.pass_until_resolved()
    scenario.will_choose_targets(ocelot, username="alice")
    cast_apparition(scenario)
    scenario.pass_until_resolved()

    bolt(scenario, first)

    (token,) = illusions(scenario, "bob")
    assert (token.power, token.toughness) == (2, 2)


def _witherbloom_board() -> Scenario:
    scenario = (
        Scenario()
        .player("alice", hand=["Witherbloom Command"], battlefield=["Swamp", "Forest"])
        .player(
            "bob",
            battlefield=["Mind Stone", "Ensnaring Bridge", "Grizzly Bears", "Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_witherbloom_command_destroys_a_noncreature_nonland_permanent_with_mana_value_2():
    scenario = _witherbloom_board()
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "bob")

    casting = scenario.cast("Witherbloom Command")
    casting.choose_modes([2, 4])
    casting.choose_targets([stone, "bob"])
    payment = casting.begin_paying()
    scenario.pay_with(payment, *scenario.untapped_sources("Swamp", "Forest"))
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert stone.zone is Zone.GRAVEYARD
    assert scenario.player("bob").life == 18
    assert scenario.player("alice").life == 22


def test_witherbloom_command_refuses_each_restriction_in_the_comma_list_and_the_bound():
    for name in ("Forest", "Grizzly Bears", "Ensnaring Bridge"):
        scenario = _witherbloom_board()
        illegal = scenario.find(name, Zone.BATTLEFIELD, "bob")
        casting = scenario.cast("Witherbloom Command")
        casting.choose_modes([2, 4])
        with pytest.raises(ValueError):
            casting.choose_targets([illegal, "bob"])


def test_a_token_apparition_that_ceased_to_exist_still_links_its_exile():
    """CR 113.7a/608.2b: a token copy of Skyclave Apparition is destroyed with
    its enters trigger on the stack and ceases to exist (CR 704.5d). The trigger
    still exiles its target, and whether its source had the linked "the exiled
    card" ability (CR 607.2a) is read from the source's last known information,
    not dropped because the token can no longer be found."""
    from magic_cards_model.models.card_state import ExileMarker
    from magic_cards_model.models.token import token_copy_of

    scenario = board(BOB)
    printed = scenario.find("Skyclave Apparition", Zone.HAND, "alice")
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.will_choose_targets(bears, username="alice")
    (apparition,) = token_copy_of(scenario.game, printed, "alice")
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names(), "the enters trigger is on the stack"

    scenario.game.destroy(apparition)
    scenario.state_based_actions()
    assert scenario.game.find_by_id(apparition.id) is None, "CR 704.5d: the token is gone"
    while scenario.stack_names():
        scenario.resolve_top()

    assert bears.zone is Zone.EXILE
    assert bears.exile_annotation is not None
    assert bears.exile_annotation.marker is ExileMarker.LINKED
    assert bears.exile_annotation.linked_permanent_id == apparition.id
