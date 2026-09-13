"""A look-and-split question says how many cards the player may pick, and a
refused pick says what was actually wrong with it.

Every CR number below was read in full with `mise run rules:find` in the
session that wrote this file:

- **CR 608.2d** - "The player can't choose an option that's illegal or
  impossible." Devourer of Destiny's "You may put one of those cards back on
  top" and Ancient Stirrings' "You may reveal a colorless card" each allow at
  most one card, so the question advertises `amount=1, exact=False`, never the
  number of cards looked at.
- **CR 107.1c** - "If a rule or ability instructs a player to choose 'any
  number,' that player may choose any positive number or zero." Scry's and
  surveil's "any number of them" is that shape: `amount` is the ceiling and
  `exact` is False.
- **CR 105.2c** - "A colorless object has no color." A green card is refused
  for Ancient Stirrings because it is not colorless, not because of the count.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import TriggerEvent
from magic_cards_model.machines.decisions import CardSplit, DecisionKind, ScriptedAnswer
from magic_cards_model.machines.delayed import DelayedTrigger, devourer_of_destiny_first_upkeep
from tests.scenarios.harness import Scenario


def _split_questions(scenario, source: str):
    return [
        d for d in scenario.questions_asked() if d.kind is DecisionKind.SCRY and d.source == source
    ]


def _script_split(scenario, moved) -> None:
    scenario.game.decisions.add(
        ScriptedAnswer(kind=DecisionKind.SCRY, value=CardSplit(moved=tuple(moved)), player="alice")
    )


# -- Devourer of Destiny's first-upkeep look ------------------------------------


def _devourer_board():
    scenario = (
        Scenario()
        .player("alice", library=["Forest", "Island", "Swamp", "Mountain", "Plains", "Forest"])
        .player("bob", library=["Island", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.create_delayed_trigger(
        DelayedTrigger(
            text=(
                "At the beginning of your first upkeep, look at the top four cards of "
                "your library. You may put one of those cards back on top of your "
                "library. Exile the rest."
            ),
            effect=devourer_of_destiny_first_upkeep,
            event=TriggerEvent.BEGINNING_OF_STEP,
            step=Step.UPKEEP,
            controller="alice",
            source_name="Devourer of Destiny",
            only_when_active="alice",
        )
    )
    return scenario


def _walk_to_alices_upkeep(scenario) -> None:
    while not (scenario.step is Step.UPKEEP and scenario.turn.active_player == "alice"):
        scenario.advance()
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()


def test_devourers_look_allows_at_most_one_card_back_on_top():
    scenario = _devourer_board()

    _walk_to_alices_upkeep(scenario)

    (question,) = _split_questions(scenario, "Devourer of Destiny")
    assert len(question.cards) == 4
    assert question.amount == 1
    assert question.exact is False
    assert question.moved_label == "top of your library"


def test_devourers_look_refuses_two_cards_put_back():
    scenario = _devourer_board()
    top = scenario.top_of_library(2)
    _script_split(scenario, [state.id for state in top])

    with pytest.raises(ValueError, match=r"at most 1 card.*\(CR 608\.2d\)"):
        _walk_to_alices_upkeep(scenario)


# -- Ancient Stirrings' "reveal a colorless card" --------------------------------


def _stirrings_board():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Ancient Stirrings"],
            battlefield=["Forest"],
            library=[
                "Malevolent Rumble",
                "Sol Ring",
                "Mishra's Bauble",
                "Lightning Bolt",
                "Island",
                "Swamp",
            ],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_stirrings(scenario):
    (forest,) = scenario.untapped_sources("Forest", username="alice")
    return scenario.cast_and_resolve("Ancient Stirrings", forest)


def test_stirrings_look_advertises_one_optional_card():
    scenario = _stirrings_board()

    _cast_stirrings(scenario)

    (question,) = _split_questions(scenario, "Ancient Stirrings")
    assert len(question.cards) == 5
    assert question.amount == 1
    assert question.exact is False


def test_stirrings_refuses_a_green_card_because_it_is_not_colorless():
    scenario = _stirrings_board()
    (rumble,) = scenario.top_of_library(1)
    _script_split(scenario, [rumble.id])

    with pytest.raises(ValueError) as refused:
        _cast_stirrings(scenario)

    message = str(refused.value)
    assert "Malevolent Rumble is not a colorless card" in message
    assert "CR 608.2d" in message
    assert "at most" not in message


def test_stirrings_refuses_two_colorless_cards_because_of_the_count():
    scenario = _stirrings_board()
    _rumble, sol_ring, bauble = scenario.top_of_library(3)
    _script_split(scenario, [sol_ring.id, bauble.id])

    with pytest.raises(ValueError, match=r"at most 1 card.*\(CR 608\.2d\)"):
        _cast_stirrings(scenario)


def test_duskwatch_refuses_a_land_because_it_is_not_a_creature_card():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Duskwatch Recruiter", "Forest", "Forest", "Forest"],
            library=["Forest", "Mountain", "Swamp"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (forest, _mountain, _swamp) = scenario.top_of_library(3)
    _script_split(scenario, [forest.id])

    recruiter = scenario.creature("Duskwatch Recruiter")
    mana = scenario.untapped_sources("Forest", "Forest", "Forest")
    scenario.activate(recruiter, *mana, index=0)
    with pytest.raises(ValueError, match=r"Forest is not a creature card \(CR 608\.2d\)"):
        scenario.resolve_top()


# -- Codecracker Hound's "put one into your hand": exactly one ---------------------


def _codecracker_board():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Codecracker Hound"],
            library=["Lightning Bolt", "Forest", "Island"],
            battlefield=["Island", "Island", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_codecracker(scenario) -> None:
    sources = scenario.untapped_sources("Island", "Island", "Island")
    scenario.cast_and_resolve("Codecracker Hound", *sources)
    scenario.pass_until_resolved()


def test_codecracker_look_advertises_exactly_one_card():
    scenario = _codecracker_board()
    bolt, _forest = scenario.top_of_library(2)
    _script_split(scenario, [bolt.id])

    _cast_codecracker(scenario)

    (question,) = _split_questions(scenario, "Codecracker Hound")
    assert len(question.cards) == 2
    assert question.amount == 1
    assert question.exact is True


def test_an_unscripted_codecracker_still_puts_exactly_one_card_into_hand():
    """ "Put one into your hand" is not optional, so an unscripted player's
    default has to be a legal split: the first card looked at goes to hand."""
    scenario = _codecracker_board()
    bolt, forest = scenario.top_of_library(2)

    _cast_codecracker(scenario)

    assert [state.name for state in scenario.player("alice").hand] == ["Lightning Bolt"]
    assert forest in scenario.player("alice").graveyard
    assert bolt not in scenario.player("alice").library


def test_codecracker_refuses_an_empty_split():
    scenario = _codecracker_board()
    _script_split(scenario, [])

    with pytest.raises(ValueError, match=r"exactly 1 card.*\(CR 608\.2d\)"):
        _cast_codecracker(scenario)


# -- scry and surveil: "any number of them" ---------------------------------------


def test_scry_advertises_any_number_up_to_the_cards_looked_at():
    scenario = (
        Scenario().player("alice", library=["Forest", "Island", "Swamp"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.game.scry("alice", 2, source="test")

    (question,) = _split_questions(scenario, "test")
    assert question.amount == 2
    assert question.exact is False


def test_surveil_advertises_any_number_up_to_the_cards_looked_at():
    scenario = (
        Scenario().player("alice", library=["Forest", "Island", "Swamp"]).player("bob").build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.game.surveil("alice", 2, source="test")

    (question,) = [
        d
        for d in scenario.questions_asked()
        if d.kind is DecisionKind.SURVEIL and d.source == "test"
    ]
    assert question.amount == 2
    assert question.exact is False
