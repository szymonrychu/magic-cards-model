"""Forsaken Crossroads' own ETB trigger: "Scry 1. If you weren't the
starting player, you may untap Forsaken Crossroads instead." -
`_parse_scry_or_untap_if_not_starting_player_clauses` in `machines/
effects.py`, and `TurnMachine.starting_player` in `machines/turn.py`.

Every CR number below was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 103.8** - "The starting player takes their first turn." -
  `TurnMachine.starting_player` reads `players[0]`, the seat fixed for the
  whole game.
- **CR 701.22a** - scry: "look at the top N cards ... then put any number of
  them on the bottom ... and the rest on top ... in any order" - a reorder,
  not a removal, which is why a scried library still holds every card.
- **CR 608.2d** - "The player can't choose an option that's illegal or
  impossible" - the untap substitution is only ever offered to a player who
  was not the starting player; the starting player never sees the question.
- **CR 701.43b** - untapping a permanent through an effect (rather than the
  untap step) never triggers exert's own "does not untap" clause.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from tests.scenarios.harness import Scenario


def _advance_to_bobs_precombat_main(scenario: Scenario) -> None:
    while scenario.turn.active_player != "bob" or scenario.step is not Step.PRECOMBAT_MAIN:
        scenario.advance()


def test_the_player_on_the_draw_may_untap_the_land_instead_of_scrying():
    """Bob is declared second, so he is not `TurnMachine.starting_player`
    (CR 103.8) - the substitution is legal, and taking it skips the scry."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", library=["Forest", "Island"])
        .player(
            "bob",
            hand=["Forsaken Crossroads"],
            library=["Mountain", "Swamp"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert scenario.game.turn.starting_player == "alice"
    _advance_to_bobs_precombat_main(scenario)

    land = scenario.play_land("Forsaken Crossroads", "bob")
    assert land.tapped is True

    scenario.will_take_the_may(True, username="bob", source="Forsaken Crossroads")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert land.tapped is False
    assert not any(d.kind is DecisionKind.SCRY for d in scenario.questions_asked())
    assert [state.name for state in scenario.player("bob").library] == ["Mountain", "Swamp"]


def test_declining_the_substitution_scries_instead():
    """The same not-starting-player scenario, declined - the land stays
    tapped and the scry happens instead."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", library=["Forest", "Island"])
        .player(
            "bob",
            hand=["Forsaken Crossroads"],
            library=["Mountain", "Swamp"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    _advance_to_bobs_precombat_main(scenario)

    land = scenario.play_land("Forsaken Crossroads", "bob")
    assert land.tapped is True

    scenario.will_take_the_may(False, username="bob", source="Forsaken Crossroads")
    top = scenario.top_of_library(1, username="bob")[0]
    scenario.scry_bottoming(top, username="bob")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert land.tapped is True
    # CR 701.22a is a reorder, not a removal: the scried card (Mountain) is
    # bottomed, Swamp comes to the top.
    assert [state.name for state in scenario.player("bob").library] == ["Swamp", "Mountain"]


def test_the_starting_player_is_never_offered_the_substitution_and_just_scries():
    """Alice is `TurnMachine.starting_player` here - CR 608.2d's "impossible
    option" is never even asked, and the land stays tapped and scries."""
    scenario = (
        Scenario()
        .player("alice", hand=["Forsaken Crossroads"], library=["Mountain", "Swamp"])
        .player("bob", library=["Forest", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert scenario.game.turn.starting_player == "alice"

    land = scenario.play_land("Forsaken Crossroads", "alice")
    assert land.tapped is True

    top = scenario.top_of_library(1, username="alice")[0]
    scenario.scry_bottoming(top, username="alice")
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert land.tapped is True
    assert not any(d.kind is DecisionKind.MAY for d in scenario.questions_asked())
    assert [state.name for state in scenario.player("alice").library] == ["Swamp", "Mountain"]
