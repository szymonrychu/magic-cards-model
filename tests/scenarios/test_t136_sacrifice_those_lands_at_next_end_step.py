"""A plural delayed sacrifice about the cards a reveal-until just put onto
the battlefield, named by their type: "Sacrifice those lands at the
beginning of your next end step."

- **Will Riker, First in the Field** - "At the beginning of combat on your
  turn, reveal cards from the top of your library until you reveal two land
  cards. Put those land cards onto the battlefield and the rest on the
  bottom of your library in a random order. Sacrifice those lands at the
  beginning of your next end step."

The reveal-until half is Skyserpent Seeker's (`test_reveal_until_n_cards.py`);
this file is the fourth sentence. No other printing says "those <type>s" in
a delayed clause (Scryfall, 2026-11-12: only Will Riker), so generality is
shown by varying the board: a land that is also a creature (Dryad Arbor),
a land that left and came back, a land that died before the end step, a
library with only one land and one with none.

Rules, each looked up with `mise run rules:find` in the session that wrote
this file:

- **CR 500.6** - "at the beginning of" a step triggers when that step begins.
- **CR 513.1** - each turn has one end step; "your next end step" is this
  turn's when the ability is created during your own combat.
- **CR 603.7a** - resolving the ability creates the delayed triggered ability.
- **CR 603.7c** - it affects the objects it refers to only while they are
  still where it expects them; one that left and came back is a new object
  (CR 400.7).
- **CR 701.21a** - a player sacrifices only permanents they control.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.delayed import parse_anaphoric_delayed_clause
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

_RIKER = "Will Riker, First in the Field"


def _board(library: list[str]) -> Scenario:
    return Scenario().player("alice", battlefield=[_RIKER], hand=[], library=library).player("bob")


def _riker_trigger(scenario) -> None:
    """Move from the precombat main phase into combat (CR 500.6) and resolve
    Will Riker's trigger."""
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert scenario.advance() is Step.BEGINNING_OF_COMBAT
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()


def _to_end_step(scenario) -> None:
    while scenario.step is not Step.END_STEP:
        scenario.advance()
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()


def _lands_on_battlefield(scenario, name: str) -> list:
    return [
        state
        for state in scenario.game.battlefield
        if state.name == name and scenario.game.controller_of(state).username == "alice"
    ]


def test_riker_puts_two_lands_down_and_sacrifices_them_at_the_end_step():
    scenario = _board(["Lightning Bolt", "Mountain", "Shock", "Forest", "Island"]).build()
    _riker_trigger(scenario)

    mountain = scenario.find("Mountain", Zone.BATTLEFIELD, "alice")
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    assert scenario.find("Island", Zone.LIBRARY, "alice").zone is Zone.LIBRARY
    library = [state.name for state in scenario.player("alice").library]
    assert library[0] == "Island", "the unrevealed card stays on top"
    assert sorted(library[1:]) == ["Lightning Bolt", "Shock"], "the rest go to the bottom"
    assert len(scenario.game.delayed_triggers.triggers) == 1, "one ability about both lands"

    _to_end_step(scenario)

    assert mountain.zone is Zone.GRAVEYARD
    assert forest.zone is Zone.GRAVEYARD
    assert scenario.find(_RIKER, Zone.BATTLEFIELD, "alice").zone is Zone.BATTLEFIELD


def test_the_lands_stay_through_combat_and_the_second_main_phase():
    """The sacrifice waits for the end step (CR 513.1), not end of combat."""
    scenario = _board(["Mountain", "Forest"]).build()
    _riker_trigger(scenario)
    while scenario.step is not Step.POSTCOMBAT_MAIN:
        scenario.advance()

    assert len(_lands_on_battlefield(scenario, "Mountain")) == 1
    assert len(_lands_on_battlefield(scenario, "Forest")) == 1


def test_a_land_creature_is_one_of_those_lands():
    """Dryad Arbor is a land card (it stops the reveal) and a land on the
    battlefield, so "those lands" agrees with it and it is sacrificed too."""
    scenario = _board(["Shock", "Dryad Arbor", "Mountain"]).build()
    _riker_trigger(scenario)
    arbor = scenario.find("Dryad Arbor", Zone.BATTLEFIELD, "alice")

    _to_end_step(scenario)

    assert arbor.zone is Zone.GRAVEYARD
    assert sorted(state.name for state in scenario.player("alice").graveyard) == [
        "Dryad Arbor",
        "Mountain",
    ]


def test_a_land_that_left_and_came_back_is_a_new_object_and_stays():
    """CR 603.7c / CR 400.7: the Forest that was returned to hand and put
    back is not the land the ability refers to; the Mountain still is."""
    scenario = _board(["Mountain", "Forest"]).build()
    _riker_trigger(scenario)
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    scenario.game.return_to_hand(forest)
    back = scenario.put_onto_battlefield("Forest", "alice")

    _to_end_step(scenario)

    assert back.zone is Zone.BATTLEFIELD
    assert scenario.find("Mountain", Zone.GRAVEYARD, "alice").zone is Zone.GRAVEYARD


def test_a_land_already_gone_leaves_the_other_to_be_sacrificed():
    scenario = _board(["Mountain", "Forest"]).build()
    _riker_trigger(scenario)
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD, "alice")
    scenario.game.destroy(mountain)
    assert mountain.zone is Zone.GRAVEYARD

    _to_end_step(scenario)

    assert scenario.find("Forest", Zone.GRAVEYARD, "alice").zone is Zone.GRAVEYARD
    assert sorted(state.name for state in scenario.player("alice").graveyard) == [
        "Forest",
        "Mountain",
    ]


def test_only_one_land_in_the_library_is_still_put_down_and_sacrificed():
    """The reveal runs out of library one land short; the one found is still
    "those lands" for the delayed sacrifice."""
    scenario = _board(["Shock", "Mountain", "Lightning Bolt"]).build()
    _riker_trigger(scenario)
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD, "alice")

    _to_end_step(scenario)

    assert mountain.zone is Zone.GRAVEYARD


def test_no_land_found_creates_no_delayed_trigger():
    scenario = _board(["Shock", "Lightning Bolt"]).build()
    _riker_trigger(scenario)

    assert scenario.game.delayed_triggers.triggers == []
    _to_end_step(scenario)
    assert scenario.player("alice").graveyard == []


def test_those_type_plural_anaphors_read_for_every_permanent_type():
    """ "those lands" is one word of a family: any plural permanent type is a
    plural anaphor that names the objects one by one (CR 603.7c)."""
    for noun in ("lands", "artifacts", "enchantments", "permanents", "creatures"):
        parsed = parse_anaphoric_delayed_clause(
            f"Sacrifice those {noun} at the beginning of your next end step."
        )
        assert parsed is not None, noun
        assert parsed.plural, noun
        assert parsed.own_turn_player, noun
    assert parse_anaphoric_delayed_clause("Sacrifice those wizards at end of combat") is None
