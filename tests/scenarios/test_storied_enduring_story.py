"""Storied and the enduring story designation (CR 702.195), through the
Hobbit Dwarves that print it - Ori, Keeper of Songs, Kili the Resourceful,
Bifur, Melodic Rider and Fili the Pathfinder among them:

    Storied (If you control three or more artifacts, legendaries, and/or
    Sagas, you have an enduring story for the rest of the game.)

Every rule cited here was read whole with `mise run rules:find` in the
session that wrote this file:

- **CR 702.195a** - "Storied is a static ability. It means 'Any time you
  control three or more permanents that are artifacts, Sagas, and/or
  legendary and you don't have an enduring story, you have an enduring story
  for the rest of the game.'" Three *permanents*: a legendary artifact is one
  permanent, never two.
- **CR 702.195b** - "Enduring story is a designation that has no rules
  meaning other than to act as a marker that other rules and effects can
  identify. Any number of players may have the enduring story designation at
  the same time." Nothing in the rules takes it away.
- **CR 702.195c** - "After a player gets an enduring story, continuous
  effects are reapplied before the game checks to see if the game state or
  preceding events have matched any trigger conditions." - so the permanent
  whose arrival grants the story already sees its effects when its own
  entrance is matched against triggers.
- **CR 613.1f** - layer 6, where a permanent can lose storied (Humility).

The designation is only the marker; what it switches on is covered by
`test_enduring_story_statics.py`, `test_typed_trigger_doubling.py` and
`test_discard_hand_draw_x.py`.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _story(scenario, username: str = "alice") -> bool:
    return scenario.player(username).has_enduring_story


# --------------------------------------------------------------------------
# CR 702.195a: the count - three permanents, each an artifact, a Saga, or
# legendary
# --------------------------------------------------------------------------


def test_two_qualifying_permanents_are_not_enough():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ori, Keeper of Songs", "Darksteel Relic", "Plains"])
        .build()
    )
    scenario.game.check_state_based_actions()
    assert _story(scenario) is False


def test_three_qualifying_permanents_grant_the_story():
    """Ori counts toward its own storied: it is legendary, and nothing in CR
    702.195a excludes the permanent the keyword is printed on."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Ori, Keeper of Songs", "Darksteel Relic", "History of Benalia"],
        )
        .build()
    )
    scenario.game.check_state_based_actions()
    assert _story(scenario) is True


def test_a_legendary_artifact_is_one_permanent_not_two():
    """ "three or more permanents that are artifacts, Sagas, and/or legendary"
    counts permanents: Mox Amber is both a legendary and an artifact, and is
    still only one of the three."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ori, Keeper of Songs", "Mox Amber", "Plains"])
        .build()
    )
    scenario.game.check_state_based_actions()
    assert _story(scenario) is False


def test_an_opponents_permanents_do_not_count():
    """ "you control": Bob's artifacts are not Alice's."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ori, Keeper of Songs", "Darksteel Relic"])
        .player("bob", battlefield=["Mox Amber", "Darksteel Relic"])
        .build()
    )
    scenario.game.check_state_based_actions()
    assert _story(scenario) is False
    assert _story(scenario, "bob") is False


def test_a_player_without_storied_never_gets_the_story():
    """The designation comes from the static ability, not from the count
    alone: three artifacts and no storied permanent grant nothing."""
    scenario = (
        Scenario()
        .player("bob", battlefield=["Mox Amber", "Darksteel Relic", "History of Benalia"])
        .build()
    )
    scenario.game.check_state_based_actions()
    assert _story(scenario, "bob") is False


def test_both_players_can_have_an_enduring_story():
    """CR 702.195b: "Any number of players may have the enduring story
    designation at the same time.\""""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ori, Keeper of Songs", "Mox Amber", "Darksteel Relic"])
        .player("bob", battlefield=["Kíli the Resourceful", "Mox Amber", "Darksteel Relic"])
        .build()
    )
    scenario.game.check_state_based_actions()
    assert _story(scenario) is True
    assert _story(scenario, "bob") is True


def test_the_story_persists_after_the_count_drops():
    """ "for the rest of the game" (CR 702.195a) and CR 702.195b's marker:
    losing the permanents - Ori itself included - does not take the story
    back."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ori, Keeper of Songs", "Mox Amber", "Darksteel Relic"])
        .build()
    )
    scenario.game.check_state_based_actions()
    assert _story(scenario) is True
    for permanent in list(scenario.game.permanents_controlled_by("alice")):
        scenario.game.sacrifice(permanent)
    scenario.game.check_state_based_actions()
    assert scenario.game.permanents_controlled_by("alice") == []
    assert _story(scenario) is True


def test_storied_removed_in_layer_6_grants_nothing():
    """Humility removes every creature's abilities in layer 6 (CR 613.1f), so
    Ori no longer has storied, and three qualifying permanents grant no
    story. Storied is read off the computed board, not the printed card."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Ori, Keeper of Songs", "Mox Amber", "Darksteel Relic", "Humility"],
        )
        .build()
    )
    scenario.game.check_state_based_actions()
    assert _story(scenario) is False


def test_the_same_board_without_humility_has_the_story():
    """The control for the Humility case above: a Plains in Humility's place,
    and the story is granted - the only difference was layer 6."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Ori, Keeper of Songs", "Mox Amber", "Darksteel Relic", "Plains"],
        )
        .build()
    )
    scenario.game.check_state_based_actions()
    assert _story(scenario) is True


# --------------------------------------------------------------------------
# "Any time": the story arrives as the third permanent enters (CR 702.195c)
# --------------------------------------------------------------------------


def test_the_story_is_granted_the_moment_the_third_permanent_enters():
    """No state-based check is needed in between: putting the third
    qualifying permanent onto the battlefield raises an event, and the story
    is granted before anything reads that event."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Mox Amber"],
            battlefield=["Ori, Keeper of Songs", "Darksteel Relic"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert _story(scenario) is False
    scenario.put_onto_battlefield("Mox Amber")
    assert _story(scenario) is True


def test_effects_are_reapplied_before_the_entering_permanents_triggers_are_matched():
    """CR 702.195c: Bifur's "As long as you have an enduring story, if a
    triggered ability of a Dwarf you control triggers, that ability triggers
    an additional time" is already on when Fili's own entrance is matched -
    Fili is the third qualifying permanent (Bifur, Darksteel Relic, Fili), and
    its "Whenever Fili or another nontoken Dwarf you control enters" triggers
    twice."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Fíli the Pathfinder"],
            battlefield=["Bifur, Melodic Rider", "Darksteel Relic"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert _story(scenario) is False
    fili = scenario.put_onto_battlefield("Fíli the Pathfinder")
    assert _story(scenario) is True
    fili_triggers = [
        item
        for item in [*scenario.pending_triggers, *scenario.game.stack]
        if getattr(item, "source_id", None) == fili.id
    ]
    assert len(fili_triggers) == 2


def test_the_story_survives_a_round_trip():
    """The designation is game state a decoded game must keep (the conftest
    replay check covers the rest)."""
    from magic_cards_model.models import Game

    scenario = (
        Scenario()
        .player("alice", battlefield=["Ori, Keeper of Songs", "Mox Amber", "Darksteel Relic"])
        .build()
    )
    scenario.game.check_state_based_actions()
    decoded = Game.model_validate(scenario.game.model_dump(mode="json"))
    assert decoded.player("alice").has_enduring_story is True
    assert scenario.find("Ori, Keeper of Songs", Zone.BATTLEFIELD, "alice") is not None
