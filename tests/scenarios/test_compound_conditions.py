"""The compound condition: "X and Y", "X or Y", "X or if Y", each half read by
whatever reads it alone.

Rules verified with `mise run rules:find` in the session that wrote this file:

- **CR 603.4** - the intervening "if" is checked as the trigger event occurs,
  and **CR 608.2a** again as the ability resolves: a compound clause is one
  condition, true or false as a whole each time.
- **CR 602.5b** - "Activate only if <condition>" (read by the same
  `Game.condition_holds`).
- **CR 601.2** - "you cast them": the object was cast, as opposed to put
  onto the battlefield.

`machines/conditions`' combinator reads a compound only when every half is
read, "and" as all of them, "or" as any, each half against the same context
- so "them" in one half and a count in the other are both about the same
ability. A compound with one unread half is not read at all, and fails closed.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

DRAGONS_AND_LESSONS = ["Murktide Regent", "Hellkite Charger", "Airbending Lesson"]


def _ran_and_shaw(graveyard: list[str]):
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Ran and Shaw"],
            graveyard=graveyard,
            battlefield=["Mountain"] * 5,
            library=["Plains"] * 3,
        )
        .player("bob", library=["Plains"] * 3)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def _cast_ran_and_shaw(scenario):
    scenario.cast_and_resolve("Ran and Shaw", *scenario.untapped_sources(*["Mountain"] * 5))


# -- "and": a triggered ability's two halves ----------------------------------


def test_both_halves_true_triggers():
    """Ran and Shaw: "When Ran and Shaw enter, if you cast them and there are
    three or more Dragon and/or Lesson cards in your graveyard, create a token
    that's a copy of Ran and Shaw ..." - cast, with three."""
    scenario = _ran_and_shaw(DRAGONS_AND_LESSONS)
    _cast_ran_and_shaw(scenario)
    assert scenario.stack_names() == ["Ran and Shaw's triggered ability"]
    assert scenario.game.intervening_if_notices == []


def test_the_second_half_false_does_not_trigger():
    """Cast, but only two Dragon and/or Lesson cards: "and" needs both."""
    scenario = _ran_and_shaw(DRAGONS_AND_LESSONS[:2])
    _cast_ran_and_shaw(scenario)
    assert scenario.stack_names() == []
    assert scenario.game.intervening_if_notices == []


def test_the_first_half_false_does_not_trigger():
    """Three in the graveyard, but put onto the battlefield rather than cast:
    "you cast them" is false, so the whole clause is (CR 601.2)."""
    scenario = _ran_and_shaw(DRAGONS_AND_LESSONS)
    scenario.put_onto_battlefield("Ran and Shaw", "alice")
    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == []
    assert scenario.game.intervening_if_notices == []


def test_a_half_false_by_resolution_removes_the_ability():
    """CR 608.2a: true as the trigger event occurred, then a Dragon leaves the
    graveyard before the ability resolves - the recheck reads the same
    compound and it is false now."""
    scenario = _ran_and_shaw(DRAGONS_AND_LESSONS)
    _cast_ran_and_shaw(scenario)
    (trigger,) = scenario.game.stack
    assert scenario.game._intervening_if_still_true(trigger)  # noqa: SLF001

    scenario.game.exile_cards([scenario.find("Murktide Regent", Zone.GRAVEYARD, "alice")])
    assert not scenario.game._intervening_if_still_true(trigger)  # noqa: SLF001
    scenario.pass_until_resolved()
    assert scenario.game.stack_is_empty
    assert [state.name for state in scenario.game.permanents_controlled_by("alice")].count(
        "Ran and Shaw"
    ) == 1


# -- "and" / "or" on halves read today, on a real board -----------------------


def _a_board_where_alice_attacked_and_a_creature_died():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Grizzly Bears", "Mountain"], hand=["Lightning Bolt"])
        .player("bob", battlefield=["Llanowar Elves"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_and_needs_every_half_and_or_needs_one():
    """ "you attacked this turn" (`Game.turn_facts`) and "a creature died this
    turn" (CR 700.4) are both read alone today; joined, "and" is all of them
    and "or" any."""
    scenario = _a_board_where_alice_attacked_and_a_creature_died()
    game = scenario.game
    both = "you attacked this turn and a creature died this turn"
    either = "you attacked this turn or a creature died this turn"
    assert game.condition_holds("alice", both) is False
    assert game.condition_holds("alice", either) is False

    elves = scenario.creature("Llanowar Elves", "bob")
    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[elves]
    )
    assert elves.zone is Zone.GRAVEYARD
    assert game.condition_holds("alice", both) is False
    assert game.condition_holds("alice", either) is True

    scenario.advance()  # beginning of combat
    scenario.advance()  # declare attackers
    scenario.attack_with(scenario.creature("Grizzly Bears", "alice"))
    assert game.condition_holds("alice", both) is True
    # Bob attacked with nothing: his "you" makes the first half false.
    assert game.condition_holds("bob", both) is False
    assert game.condition_holds("bob", either) is True


def test_or_if_reads_the_same_way():
    scenario = _a_board_where_alice_attacked_and_a_creature_died()
    assert (
        scenario.game.condition_holds("alice", "it's your turn or if a creature died this turn")
        is True
    )
    assert (
        scenario.game.condition_holds("bob", "it's your turn or if a creature died this turn")
        is False
    )


def test_a_half_nobody_reads_leaves_the_whole_compound_unread():
    """One unread half and the compound is not read at all - None, which every
    caller fails closed on - even when the half that is read is true."""
    scenario = _a_board_where_alice_attacked_and_a_creature_died()
    game = scenario.game
    assert game.condition_holds("alice", "it's your turn") is True
    assert game.condition_holds("alice", "it's your turn and the moon is full") is None
    assert game.condition_holds("alice", "it's your turn or the moon is full") is None


def test_or_if_with_an_unread_half_is_unread_too():
    """The same rule for "or if" (Gathering Place's joiner): a true half does
    not stand in for a half nobody can check."""
    scenario = _a_board_where_alice_attacked_and_a_creature_died()
    elves = scenario.creature("Llanowar Elves", "bob")
    scenario.cast_and_resolve(
        "Lightning Bolt", *scenario.untapped_sources("Mountain"), targets=[elves]
    )
    game = scenario.game
    assert game.condition_holds("alice", "a creature died this turn") is True
    assert game.condition_holds("alice", "a creature died this turn or if the moon is full") is None
