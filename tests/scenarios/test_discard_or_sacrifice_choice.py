"""A two-way optional cost: "You may discard a card or sacrifice a `<permanent>`.
If you do, `<effect>`." (and the same sentence with the two halves swapped).

Every CR number below was read whole with `mise run rules:find` in the session
that wrote this file:

- **CR 118.12** - "[A player] may [do something]. If [that player] [does ...],
  [effect]." The action is a cost paid as the spell resolves; "If you do"
  checks whether the player chose to pay it.
- **CR 608.2d** - the player announces the choices an effect offers while
  applying it, and "can't choose an option that's illegal or impossible": an
  empty hand leaves only the sacrifice, no land leaves only the discard, and
  neither leaves nothing to say yes to.
- **CR 701.9b** - the discarding player chooses which card.
- **CR 701.21a** - a player sacrifices only a permanent they control.
- **CR 702.170d** - a plotted card is cast from exile on a later turn without
  paying its mana cost; what it does on resolution is unchanged.

Highway Robbery ("You may discard a card or sacrifice a land. If you do, draw
two cards.") is the reported card. Vision of Love ("You may sacrifice an
artifact or discard a card. If you do, draw two cards.") is the proof printing:
Standard-legal, not in any api deck, the halves in the other order and an
artifact instead of a land - it failed closed with a `ConditionalClauseNotice`
before this reader existed.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import MarkedExile
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

LIBRARY = ["Island", "Forest", "Swamp", "Plains"]


def robbery_board(hand: list[str], battlefield: list[str]) -> Scenario:
    return (
        Scenario()
        .player("alice", hand=["Highway Robbery", *hand], battlefield=battlefield, library=LIBRARY)
        .player("bob")
    )


def cast_robbery(scenario):
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Mountain", "Mountain", username="alice")
    return scenario.cast_and_resolve("Highway Robbery", *sources)


def test_discarding_a_card_draws_two():
    scenario = robbery_board(["Lightning Bolt"], ["Mountain", "Mountain"]).build()
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    scenario.will_take_the_may(True, source="Highway Robbery")
    scenario.will_choose("discard a card", source="Highway Robbery")
    scenario.will_discard(bolt)

    cast_robbery(scenario)

    alice = scenario.player("alice")
    assert bolt.zone is Zone.GRAVEYARD
    assert [state.name for state in alice.hand] == ["Island", "Forest"]
    assert all(state.zone is Zone.BATTLEFIELD for state in scenario.game.battlefield)
    assert len(scenario.game.permanents_controlled_by("alice")) == 2


def test_sacrificing_a_land_draws_two():
    scenario = robbery_board(["Lightning Bolt"], ["Mountain", "Mountain", "Forest"]).build()
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    scenario.will_take_the_may(True, source="Highway Robbery")
    scenario.will_choose("sacrifice a land", source="Highway Robbery")
    scenario.will_choose_cards(forest, source="Highway Robbery")

    cast_robbery(scenario)

    alice = scenario.player("alice")
    assert forest.zone is Zone.GRAVEYARD
    assert bolt.zone is Zone.HAND, "the discard half was not taken"
    assert sorted(state.name for state in alice.hand) == ["Forest", "Island", "Lightning Bolt"]


def test_a_tapped_land_is_still_a_land_to_sacrifice():
    """CR 701.21a asks only for a permanent the player controls - the two
    Mountains that just paid for the spell are as sacrificeable as any."""
    scenario = robbery_board([], ["Mountain", "Mountain"]).build()
    scenario.will_take_the_may(True, source="Highway Robbery")

    cast_robbery(scenario)

    alice = scenario.player("alice")
    assert len(scenario.game.permanents_controlled_by("alice")) == 1
    assert len(alice.hand) == 2


def test_declining_does_nothing():
    scenario = robbery_board(["Lightning Bolt"], ["Mountain", "Mountain"]).build()
    scenario.will_take_the_may(False, source="Highway Robbery")

    cast_robbery(scenario)

    alice = scenario.player("alice")
    assert [state.name for state in alice.hand] == ["Lightning Bolt"]
    assert len(scenario.game.permanents_controlled_by("alice")) == 2
    assert len(alice.library) == 4


def test_unscripted_the_first_printed_half_is_paid():
    """`machines/decisions.default_answer`: an unscripted "you may" is taken
    when it is legal, and an unscripted choice names the first option -
    here the first half as printed, the discard."""
    scenario = robbery_board(["Lightning Bolt"], ["Mountain", "Mountain"]).build()
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")

    cast_robbery(scenario)

    alice = scenario.player("alice")
    assert bolt.zone is Zone.GRAVEYARD
    assert len(scenario.game.permanents_controlled_by("alice")) == 2
    assert len(alice.hand) == 2


def test_an_empty_hand_offers_only_the_sacrifice():
    """CR 608.2d: the discard is impossible, so only the land is asked about -
    there is no which-one question at all."""
    scenario = robbery_board([], ["Mountain", "Mountain"]).build()
    scenario.will_take_the_may(True, source="Highway Robbery")

    cast_robbery(scenario)

    asked = [d.kind for d in scenario.questions_asked() if d.source == "Highway Robbery"]
    assert DecisionKind.CHOOSE_A_QUALITY not in asked
    assert len(scenario.player("alice").hand) == 2
    assert len(scenario.game.permanents_controlled_by("alice")) == 1


def test_the_choice_offers_both_halves_when_both_are_possible():
    scenario = robbery_board(["Lightning Bolt"], ["Mountain", "Mountain"]).build()
    scenario.will_take_the_may(True, source="Highway Robbery")
    scenario.will_choose("discard a card", source="Highway Robbery")

    cast_robbery(scenario)

    (choice,) = [
        d
        for d in scenario.questions_asked()
        if d.kind is DecisionKind.CHOOSE_A_QUALITY and d.source == "Highway Robbery"
    ]
    assert set(choice.options) == {"discard a card", "sacrifice a land"}


def test_plotted_robbery_is_cast_for_free_and_still_offers_the_choice():
    """CR 702.170d: plot changes how the spell is cast, not what it does."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Highway Robbery", "Lightning Bolt"],
            battlefield=["Mountain", "Mountain"],
            library=LIBRARY * 5,
        )
        .player("bob", library=LIBRARY * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    robbery = scenario.find("Highway Robbery", Zone.HAND, "alice")
    action = MarkedExile.plot(scenario.game, robbery, "alice")
    scenario.pay_with(
        action.begin_paying(), *scenario.untapped_sources("Mountain", "Mountain", username="alice")
    )
    action.take()
    assert robbery.zone is Zone.EXILE
    for _ in range(60):
        scenario.advance()
        if scenario.turn.active_player == "alice" and scenario.step is Step.PRECOMBAT_MAIN:
            break
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    hand_before = len(scenario.player("alice").hand)
    scenario.will_take_the_may(True, source="Highway Robbery")
    scenario.will_choose("discard a card", source="Highway Robbery")
    scenario.will_discard(bolt)

    casting = scenario.cast("Highway Robbery", from_zone=Zone.EXILE)
    casting.use_keyword("Plot")
    casting.begin_paying().pay()
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert bolt.zone is Zone.GRAVEYARD
    assert len(scenario.player("alice").hand) == hand_before - 1 + 2


# -- proof printing: Vision of Love -------------------------------------------


def love_board(hand: list[str], battlefield: list[str]) -> Scenario:
    return (
        Scenario()
        .player("alice", hand=["Vision of Love", *hand], battlefield=battlefield, library=LIBRARY)
        .player("bob")
    )


def cast_love(scenario):
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Mountain", "Mountain", username="alice")
    return scenario.cast_and_resolve("Vision of Love", *sources)


def test_vision_of_love_sacrifices_an_artifact_to_draw_two():
    scenario = love_board(["Lightning Bolt"], ["Mountain", "Mountain", "Ornithopter"]).build()
    thopter = scenario.find("Ornithopter", Zone.BATTLEFIELD, "alice")
    scenario.will_take_the_may(True, source="Vision of Love")
    scenario.will_choose("sacrifice an artifact", source="Vision of Love")
    scenario.will_choose_cards(thopter, source="Vision of Love")

    cast_love(scenario)

    assert thopter.zone is Zone.GRAVEYARD
    assert sorted(s.name for s in scenario.player("alice").hand) == [
        "Forest",
        "Island",
        "Lightning Bolt",
    ]


def test_vision_of_love_discards_to_draw_two():
    scenario = love_board(["Lightning Bolt"], ["Mountain", "Mountain", "Ornithopter"]).build()
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    thopter = scenario.find("Ornithopter", Zone.BATTLEFIELD, "alice")
    scenario.will_take_the_may(True, source="Vision of Love")
    scenario.will_choose("discard a card", source="Vision of Love")
    scenario.will_discard(bolt)

    cast_love(scenario)

    assert bolt.zone is Zone.GRAVEYARD
    assert thopter.zone is Zone.BATTLEFIELD
    assert sorted(s.name for s in scenario.player("alice").hand) == ["Forest", "Island"]


def test_a_land_is_not_an_artifact_to_sacrifice():
    """No artifact and an empty hand: neither half can be paid (CR 608.2d), so
    saying yes is not legal and nothing is drawn."""
    scenario = love_board([], ["Mountain", "Mountain"]).build()

    cast_love(scenario)

    assert scenario.player("alice").hand == []
    assert len(scenario.game.permanents_controlled_by("alice")) == 2
    (may,) = [
        d
        for d in scenario.questions_asked()
        if d.kind is DecisionKind.MAY and d.source == "Vision of Love"
    ]
    assert may.affirmative_is_legal is False


def test_no_artifact_offers_only_the_discard():
    scenario = love_board(["Lightning Bolt"], ["Mountain", "Mountain"]).build()
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    scenario.will_take_the_may(True, source="Vision of Love")

    cast_love(scenario)

    assert bolt.zone is Zone.GRAVEYARD
    asked = [d.kind for d in scenario.questions_asked() if d.source == "Vision of Love"]
    assert DecisionKind.CHOOSE_A_QUALITY not in asked
    assert len(scenario.player("alice").hand) == 2
