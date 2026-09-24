"""Airbend, whatever the count: "any number of", "up to one", or a bare "target".

CR 701.65a: "Certain spells and abilities instruct a player to airbend one or
more permanents and/or spells. To do so, that player exiles those objects. For
each card exiled this way, for as long as it remains exiled, its owner may cast
it by paying {2} rather than paying its mana cost."

CR 701.65b: "An ability that triggers whenever a player airbends triggers when
that player exiles one or more objects as a result of an instruction to
airbend."

The instruction reader (`machines/effects._parse_airbend_clause`) does not read
the count at all: CR 115's announcement rules and `machines/targeting.py`
already bound how many targets were chosen, off the same printed words. So one
reader serves:

- Appa, Steadfast Guardian: "When Appa enters, airbend any number of other
  target nonland permanents you control." - CR 107.1c's "any number", nought
  upwards, restricted to the controller's own nonland permanents, never Appa
  itself.
- Airbending Lesson (the second printing, legal in Modern, Pioneer and
  Standard, in no deck list here): "Airbend target nonland permanent. Draw a
  card." - an instant, a bare single target, anyone's permanent.

Appa's own "Whenever you cast a spell from exile, create a 1/1 white Ally
creature token." is what an airbent card's {2} recast sets off.

Every CR number here was read whole with `mise run rules:find`.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import marker_cast_options
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import ExileMarker
from magic_cards_model.models.token import is_token
from tests.scenarios.harness import Scenario

APPA = "Appa, Steadfast Guardian"


def _appa_board(*extra: str):
    """Alice holds Appa with exactly {2}{W}{W} available, and a board of
    things Appa's trigger may or may not reach."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            library=["Island"] * 5,
            hand=[APPA],
            battlefield=[
                "Plains",
                "Plains",
                "Island",
                "Island",
                "Grizzly Bears",
                "Glorious Anthem",
                "Memnite",
                *extra,
            ],
        )
        .player("bob", library=["Island"] * 5, battlefield=["Runeclaw Bear", "Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_appa(scenario, targets):
    scenario.choose_trigger_targets(APPA, targets)
    scenario.cast_and_resolve(
        APPA, *scenario.untapped_sources("Plains", "Plains", "Island", "Island")
    )
    while scenario.game.stack or scenario.pending_triggers:
        scenario.pass_until_resolved()


def test_appa_airbends_every_chosen_permanent_at_once():
    """Two targets chosen, two permanents exiled, each a card carrying CR
    701.65a's {2} permission for its owner."""
    scenario = _appa_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    anthem = scenario.find("Glorious Anthem", Zone.BATTLEFIELD, "alice")
    memnite = scenario.creature("Memnite", "alice")

    _cast_appa(scenario, [bears, anthem])

    assert bears.zone is Zone.EXILE
    assert anthem.zone is Zone.EXILE
    assert memnite.zone is Zone.BATTLEFIELD
    for card in (bears, anthem):
        assert card.exile_annotation is not None
        assert card.exile_annotation.marker is ExileMarker.AIRBENT
        (option,) = marker_cast_options(card)
        assert str(option.cost.mana) == "{2}"
        assert option.why_not(card, "alice") is None
    assert scenario.creature(APPA, "alice").zone is Zone.BATTLEFIELD


def test_appa_may_airbend_nothing_at_all():
    """CR 107.1c: "any number" includes zero, so a trigger with no targets is
    legal and simply exiles nothing (CR 603.3d announced none)."""
    scenario = _appa_board()
    _cast_appa(scenario, [])

    assert scenario.creature("Grizzly Bears", "alice").zone is Zone.BATTLEFIELD
    assert scenario.find("Glorious Anthem", Zone.BATTLEFIELD, "alice").zone is Zone.BATTLEFIELD
    assert scenario.game.exile == []


def test_appa_airbends_many_permanents_in_one_trigger():
    """No upper bound: every other nonland permanent alice controls at once."""
    scenario = _appa_board("Ornithopter")
    chosen = [
        scenario.creature("Grizzly Bears", "alice"),
        scenario.find("Glorious Anthem", Zone.BATTLEFIELD, "alice"),
        scenario.creature("Memnite", "alice"),
        scenario.creature("Ornithopter", "alice"),
    ]
    _cast_appa(scenario, chosen)

    assert all(card.zone is Zone.EXILE for card in chosen)


def test_appa_cannot_airbend_itself():
    """ "Other" - the source is not a legal target of its own ability."""
    scenario = _appa_board()
    scenario.choose_trigger_targets(APPA, [])
    scenario.cast_and_resolve(
        APPA, *scenario.untapped_sources("Plains", "Plains", "Island", "Island")
    )
    appa = scenario.creature(APPA, "alice")

    with pytest.raises(ValueError):
        scenario.choose_trigger_targets(APPA, [appa])


def test_appa_cannot_airbend_a_land():
    scenario = _appa_board()
    plains = scenario.find("Plains", Zone.BATTLEFIELD, "alice")

    with pytest.raises(ValueError):
        scenario.choose_trigger_targets(APPA, [plains])


def test_appa_cannot_airbend_an_opponents_permanent():
    """ "You control" - bob's creature is out of reach."""
    scenario = _appa_board()
    bob_bear = scenario.creature("Runeclaw Bear", "bob")

    with pytest.raises(ValueError):
        scenario.choose_trigger_targets(APPA, [bob_bear])


def test_a_target_gone_before_resolution_is_skipped_and_the_rest_airbent():
    """CR 608.2b: an illegal target is not affected; the legal ones still are.
    Bob bolts the Bears in response to Appa's trigger."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            library=["Island"] * 5,
            hand=[APPA],
            battlefield=["Plains", "Plains", "Island", "Island", "Grizzly Bears", "Memnite"],
        )
        .player("bob", library=["Island"] * 5, hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    memnite = scenario.creature("Memnite", "alice")
    scenario.choose_trigger_targets(APPA, [bears, memnite])
    scenario.cast_and_resolve(
        APPA, *scenario.untapped_sources("Plains", "Plains", "Island", "Island")
    )
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == [f"{APPA}'s triggered ability"]

    scenario.pass_priority("alice")
    scenario.cast_and_resolve(
        "Lightning Bolt",
        *scenario.untapped_sources("Mountain", username="bob"),
        username="bob",
        targets=[bears],
    )
    scenario.state_based_actions()
    assert bears.zone is Zone.GRAVEYARD
    while scenario.game.stack:
        scenario.pass_until_resolved()

    assert bears.zone is Zone.GRAVEYARD
    assert memnite.zone is Zone.EXILE
    assert memnite.exile_annotation is not None
    assert memnite.exile_annotation.marker is ExileMarker.AIRBENT


def test_recasting_an_airbent_card_for_two_sets_off_appas_cast_from_exile_trigger():
    """The {2} recast is a cast from exile, so Appa makes a 1/1 white Ally."""
    scenario = _appa_board()
    bears = scenario.creature("Grizzly Bears", "alice")
    _cast_appa(scenario, [bears])
    assert bears.zone is Zone.EXILE

    # A new turn's worth of mana: untap alice's lands by hand.
    for land in scenario.game.permanents_controlled_by("alice"):
        land.tapped = False
    casting = scenario.cast("Grizzly Bears", "alice", from_zone=Zone.EXILE)
    casting.use_keyword("Airbend")
    assert str(casting.total_cost.mana) == "{2}"
    scenario.pay_with(casting.begin_paying(), *scenario.untapped_sources("Plains", "Plains"))
    scenario.put_on_stack(casting)
    while scenario.game.stack or scenario.pending_triggers:
        scenario.pass_until_resolved()

    assert bears.zone is Zone.BATTLEFIELD
    allies = [
        permanent
        for permanent in scenario.game.permanents_controlled_by("alice")
        if "Ally" in permanent.subtypes and is_token(permanent)
    ]
    assert len(allies) == 1
    # A 1/1, pumped by the Glorious Anthem still on alice's side.
    assert (allies[0].power, allies[0].toughness) == (2, 2)


def test_one_airbend_of_several_objects_is_one_airbend_event():
    """CR 701.65b: the trigger fires once for the instruction, however many
    objects it exiled - Avatar Aang's "Whenever you ... airbend, draw a card"
    draws exactly one card for Appa exiling two permanents, and the turn
    remembers alice airbent."""
    scenario = _appa_board("Avatar Aang")
    hand_before = len(scenario.player("alice").hand)
    bears = scenario.creature("Grizzly Bears", "alice")
    memnite = scenario.creature("Memnite", "alice")

    _cast_appa(scenario, [bears, memnite])

    # Appa left the hand (-1); Avatar Aang drew one (+1).
    assert len(scenario.player("alice").hand) == hand_before - 1 + 1
    assert "alice" in scenario.game.turn_facts.get("airbent", set())


def test_airbending_nothing_is_no_airbend_event():
    """CR 701.65b triggers on exiling "one or more objects" - none, no trigger."""
    scenario = _appa_board("Avatar Aang")
    hand_before = len(scenario.player("alice").hand)

    _cast_appa(scenario, [])

    assert len(scenario.player("alice").hand) == hand_before - 1
    assert "alice" not in scenario.game.turn_facts.get("airbent", set())


# --------------------------------------------------------------------------
# Airbending Lesson - the same reader on a spell with a bare single target
# --------------------------------------------------------------------------


def _lesson_board():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            library=["Island"] * 5,
            hand=["Airbending Lesson"],
            battlefield=["Plains", "Island", "Island"],
        )
        .player("bob", library=["Island"] * 5, battlefield=["Runeclaw Bear", "Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_airbending_lesson_airbends_an_opponents_permanent_and_draws():
    scenario = _lesson_board()
    bear = scenario.creature("Runeclaw Bear", "bob")
    hand_before = len(scenario.player("alice").hand)

    scenario.cast_and_resolve(
        "Airbending Lesson",
        *scenario.untapped_sources("Plains", "Island", "Island"),
        targets=[bear],
    )

    assert bear.zone is Zone.EXILE
    assert bear.exile_annotation is not None
    assert bear.exile_annotation.marker is ExileMarker.AIRBENT
    # CR 701.65a: the permission is the *owner's* - bob's, not alice's.
    (option,) = marker_cast_options(bear)
    assert option.why_not(bear, "bob") is None
    assert option.why_not(bear, "alice") is not None
    # The lesson went to the graveyard and alice drew its card.
    assert len(scenario.player("alice").hand) == hand_before - 1 + 1
    assert "alice" in scenario.game.turn_facts.get("airbent", set())


def test_airbending_lesson_cannot_target_a_land():
    scenario = _lesson_board()
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD, "bob")

    with pytest.raises(ValueError):
        scenario.cast("Airbending Lesson", targets=[mountain])
