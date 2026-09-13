"""A modal triggered ability chooses its mode as it goes on the stack.

- **CR 603.3c** - "If a triggered ability is modal, its controller announces
  the mode choice when putting the ability on the stack. If one of the modes
  would be illegal (due to an inability to choose legal targets, for example),
  that mode can't be chosen. If no mode is chosen, the ability is removed from
  the stack."
- **CR 700.2b** - the same rule from the modal side.
- **CR 700.2c** - "If a spell or ability targets one or more targets only if a
  particular mode is chosen for it, its controller will need to choose those
  targets only if they chose that mode."
- **CR 603.3d** - the rest of putting it on the stack is CR 601.2c-d: targets
  are announced then, after the mode.
- **CR 608.2b** - a chosen target that has become illegal by resolution leaves
  the ability with nothing to do.

Abiding Grace's "choose one - You gain 1 life. / Return target creature card
with mana value 1 from your graveyard to the battlefield." is the reported
card: with no mana value 1 creature card in the graveyard the life mode is
still choosable, and the ability is never removed for want of a return target.

Coliseum Behemoth (a targeting mode and a draw) and Flash Thompson, Spider-Fan
("choose one or both", flavor-word labelled modes, CR 207.2d) are not in any
deck pool; they prove the template rather than the reported card.

Every CR number above was read in full from `mise run rules:find` in the
session that wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.machines.effects import NO_FURTHER_MODES
from magic_cards_model.machines.triggers import AbilityOnStack
from magic_cards_model.models import Zone

from .harness import Scenario

GAIN = "You gain 1 life."
RETURN = "Return target creature card with mana value 1 from your graveyard to the battlefield."


def grace_board(graveyard: list[str]) -> Scenario:
    return (
        Scenario()
        .player("alice", battlefield=["Abiding Grace"], graveyard=graveyard, library=["Plains"] * 3)
        .player("bob", library=["Plains"] * 3)
        .build()
    )


def to_end_step(scenario: Scenario) -> None:
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    while scenario.step is not Step.END_STEP:
        scenario.advance()


def kinds(scenario: Scenario) -> list[DecisionKind]:
    return [
        q.kind
        for q in scenario.questions_asked()
        if q.kind in (DecisionKind.CHOOSE_A_MODE, DecisionKind.CHOOSE_TARGETS)
    ]


def mode_questions(scenario: Scenario):
    return [q for q in scenario.questions_asked() if q.kind is DecisionKind.CHOOSE_A_MODE]


def grace_on_stack(scenario: Scenario) -> AbilityOnStack:
    (ability,) = [
        item
        for item in scenario.game.stack
        if isinstance(item, AbilityOnStack) and item.source_name == "Abiding Grace"
    ]
    return ability


def resolve_all(scenario: Scenario) -> None:
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()


def test_with_no_return_target_the_life_mode_is_still_chosen():
    scenario = grace_board(["Grizzly Bears", "Ephemerate"])
    to_end_step(scenario)

    grace_on_stack(scenario)
    (question,) = mode_questions(scenario)
    assert question.options == (GAIN,)
    resolve_all(scenario)

    assert scenario.player("alice").life == 21


def test_the_mode_then_the_target_are_chosen_as_it_goes_on_the_stack():
    scenario = grace_board(["Llanowar Elves"])
    elves = scenario.find("Llanowar Elves", Zone.GRAVEYARD, "alice")
    scenario.will_choose_mode(RETURN, username="alice")
    scenario.will_choose_targets(elves, username="alice")
    to_end_step(scenario)

    ability = grace_on_stack(scenario)
    assert kinds(scenario) == [DecisionKind.CHOOSE_A_MODE, DecisionKind.CHOOSE_TARGETS]
    assert [target.card_id for target in ability.targets] == [elves.id]
    assert set(mode_questions(scenario)[0].options) == {GAIN, RETURN}

    resolve_all(scenario)

    assert elves.zone is Zone.BATTLEFIELD
    assert len(mode_questions(scenario)) == 1
    assert scenario.player("alice").life == 20


def test_choosing_the_life_mode_asks_for_no_target():
    scenario = grace_board(["Llanowar Elves"])
    elves = scenario.find("Llanowar Elves", Zone.GRAVEYARD, "alice")
    scenario.will_choose_mode(GAIN, username="alice")
    to_end_step(scenario)

    assert grace_on_stack(scenario).targets == []
    resolve_all(scenario)

    assert kinds(scenario) == [DecisionKind.CHOOSE_A_MODE]
    assert elves.zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 21


def test_a_return_target_that_leaves_before_resolution_does_nothing():
    scenario = grace_board(["Llanowar Elves"])
    elves = scenario.find("Llanowar Elves", Zone.GRAVEYARD, "alice")
    scenario.will_choose_mode(RETURN, username="alice")
    scenario.will_choose_targets(elves, username="alice")
    to_end_step(scenario)

    scenario.game.exile_cards([elves])
    resolve_all(scenario)

    assert elves.zone is Zone.EXILE
    assert scenario.player("alice").life == 20
    assert len(mode_questions(scenario)) == 1


# -- the template, not the card ------------------------------------------------


def _behemoth(bob_battlefield: list[str]) -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Coliseum Behemoth"],
            battlefield=["Forest"] * 7,
            library=["Forest"] * 3,
        )
        .player("bob", battlefield=bob_battlefield)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_behemoth(scenario: Scenario) -> None:
    scenario.cast_and_resolve("Coliseum Behemoth", *scenario.untapped_sources(*["Forest"] * 7))


def test_coliseum_behemoth_with_no_artifact_or_enchantment_offers_only_the_draw():
    scenario = _behemoth(["Grizzly Bears"])
    hand_before = len(scenario.player("alice").hand)

    _cast_behemoth(scenario)
    (question,) = mode_questions(scenario)
    resolve_all(scenario)

    assert question.options == ("Draw a card.",)
    assert len(scenario.player("alice").hand) == hand_before
    assert len(scenario.player("alice").library) == 2


def test_coliseum_behemoth_with_an_artifact_offers_both_and_destroys_it():
    scenario = _behemoth(["Mind Stone"])
    stone = scenario.find("Mind Stone", Zone.BATTLEFIELD, "bob")
    scenario.will_choose_mode("Destroy target artifact or enchantment.", username="alice")
    scenario.will_choose_targets(stone, username="alice")

    _cast_behemoth(scenario)
    (question,) = mode_questions(scenario)
    resolve_all(scenario)

    assert set(question.options) == {"Destroy target artifact or enchantment.", "Draw a card."}
    assert stone.zone is Zone.GRAVEYARD


def _flash_thompson(*, elves_tapped: bool = True) -> Scenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Flash Thompson, Spider-Fan"],
            battlefield=["Plains", "Plains", "Llanowar Elves"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    if elves_tapped:
        scenario.creature("Llanowar Elves", "alice").tap()
    return scenario


HECKLE = "Heckle \u2014 Tap target creature."
HERO_WORSHIP = "Hero Worship \u2014 Untap target creature."


def test_choose_one_or_both_takes_both_modes_with_a_target_each():
    scenario = _flash_thompson()
    bears = scenario.creature("Grizzly Bears", "bob")
    elves = scenario.creature("Llanowar Elves", "alice")
    scenario.will_choose_mode(HECKLE, username="alice")
    scenario.will_choose_mode(HERO_WORSHIP, username="alice")
    scenario.will_choose_targets(bears, username="alice")
    scenario.will_choose_targets(elves, username="alice")

    scenario.cast_and_resolve(
        "Flash Thompson, Spider-Fan", *scenario.untapped_sources("Plains", "Plains")
    )
    resolve_all(scenario)

    assert bears.tapped is True
    assert elves.tapped is False


def test_choose_one_or_both_may_stop_after_one_mode():
    scenario = _flash_thompson()
    bears = scenario.creature("Grizzly Bears", "bob")
    elves = scenario.creature("Llanowar Elves", "alice")
    scenario.will_choose_mode(HECKLE, username="alice")
    scenario.will_choose_mode(NO_FURTHER_MODES, username="alice")
    scenario.will_choose_targets(bears, username="alice")

    scenario.cast_and_resolve(
        "Flash Thompson, Spider-Fan", *scenario.untapped_sources("Plains", "Plains")
    )
    resolve_all(scenario)

    first, second = mode_questions(scenario)
    assert NO_FURTHER_MODES not in first.options
    assert second.options == (NO_FURTHER_MODES, HERO_WORSHIP)
    assert bears.tapped is True
    assert elves.tapped is True


def test_an_unscripted_one_or_both_takes_the_first_mode_only():
    scenario = _flash_thompson(elves_tapped=False)

    scenario.cast_and_resolve(
        "Flash Thompson, Spider-Fan", *scenario.untapped_sources("Plains", "Plains")
    )
    resolve_all(scenario)

    assert len(mode_questions(scenario)) == 2
    assert kinds(scenario).count(DecisionKind.CHOOSE_TARGETS) == 1
