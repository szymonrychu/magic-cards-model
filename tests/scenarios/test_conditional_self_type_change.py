"""Scenario: "As long as `<condition>`, this `<object>` is an artifact creature." -
a static ability (CR 604.2) whose type-changing effect (layer 4, CR 613.1d)
applies exactly while its condition holds (CR 611.3a: never "locked in").

Phoenix Fleet Airship: "As long as you control eight or more permanents named
Phoenix Fleet Airship, this Vehicle is an artifact creature." The name is the
card's own (read from the sentence, CR 201.2), the count is permanents *you*
control with that name - tokens that are copies of it included (CR 707.2
copies the name) - and a Vehicle that becomes a creature has its printed
power and toughness (CR 301.7b).

Grond, the Gatebreaker's "As long as it's your turn and you control an Army,
Grond is an artifact creature." is the second printing: the same template
with the card's own name as the subject, a compound condition ("it's your
turn" and "you control an Army"), each half re-read on every computation.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Type
from tests.scenarios.harness import Scenario


def _airships(scenario: Scenario, username: str = "alice") -> list:
    return [
        state
        for state in scenario.game.permanents_controlled_by(username)
        if state.name == "Phoenix Fleet Airship"
    ]


def _board(alice: int, bob: int = 0) -> Scenario:
    return (
        Scenario()
        .player("alice", battlefield=["Phoenix Fleet Airship"] * alice, library=["Swamp"] * 3)
        .player("bob", battlefield=["Phoenix Fleet Airship"] * bob, library=["Island"] * 3)
        .build()
    )


def test_one_airship_is_not_a_creature():
    scenario = _board(1)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (airship,) = _airships(scenario)

    chars = scenario.game.computed_board().of(airship)
    assert not chars.is_creature
    assert scenario.game.continuous_effects.layer_notices == []


def test_seven_airships_are_not_creatures():
    scenario = _board(7)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    board = scenario.game.computed_board()

    assert not any(board.of(airship).is_creature for airship in _airships(scenario))


def test_eight_airships_are_all_artifact_creatures_with_printed_power():
    scenario = _board(8)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    board = scenario.game.computed_board()

    for airship in _airships(scenario):
        chars = board.of(airship)
        assert chars.is_creature
        assert Type.ARTIFACT in chars.types
        assert "Vehicle" in chars.subtypes
        assert chars.power_toughness == (4, 4)


def test_the_opponents_airships_do_not_count():
    scenario = _board(4, bob=4)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    board = scenario.game.computed_board()

    assert not any(board.of(airship).is_creature for airship in _airships(scenario))
    assert not any(board.of(airship).is_creature for airship in _airships(scenario, "bob"))


def test_losing_the_eighth_turns_them_all_back():
    """CR 611.3a: the moment the count drops under eight, none of them is a
    creature any more."""
    scenario = _board(8)
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.exile_cards([_airships(scenario)[0]])
    board = scenario.game.computed_board()

    assert len(_airships(scenario)) == 7
    assert not any(board.of(airship).is_creature for airship in _airships(scenario))


# -- Grond, the Gatebreaker: its own name, a compound condition --------------


def _grond_board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            hand=["Orcish Bowmasters"],
            battlefield=["Grond, the Gatebreaker", "Swamp", "Swamp"],
            library=["Swamp"] * 6,
        )
        .player("bob", library=["Island"] * 6)
        .build()
    )


def _make_an_army(scenario: Scenario) -> None:
    """Orcish Bowmasters' ETB ends "Then amass Orcs 1" (CR 701.47a)."""
    scenario.choose_trigger_targets("Orcish Bowmasters", ["bob"])
    sources = scenario.untapped_sources("Swamp", "Swamp", username="alice")
    scenario.cast_and_resolve("Orcish Bowmasters", *sources, username="alice")
    scenario.pass_until_resolved()
    scenario.creature("Orc Army Token", "alice")


def _grond(scenario: Scenario):
    return scenario.creature("Grond, the Gatebreaker", "alice")


def test_grond_without_an_army_is_not_a_creature_on_your_turn():
    scenario = _grond_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    assert not scenario.game.computed_board().of(_grond(scenario)).is_creature
    assert scenario.game.continuous_effects.layer_notices == []


def test_grond_with_an_army_on_your_turn_is_an_artifact_creature():
    scenario = _grond_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _make_an_army(scenario)

    chars = scenario.game.computed_board().of(_grond(scenario))
    assert chars.is_creature
    assert Type.ARTIFACT in chars.types
    assert chars.power_toughness == (5, 5)


def test_grond_with_an_army_on_the_opponents_turn_is_not_a_creature():
    scenario = _grond_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _make_an_army(scenario)
    while scenario.turn.active_player != "bob":
        scenario.advance()
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()

    assert not scenario.game.computed_board().of(_grond(scenario)).is_creature
