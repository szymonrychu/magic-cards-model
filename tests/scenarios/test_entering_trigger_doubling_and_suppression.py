"""Entering-trigger multipliers and suppressors (CR 603.2d; CR 603.2).

Two static templates about what a permanent *entering* makes trigger:

- "If a permanent entering [the battlefield] causes a triggered ability of a
  permanent you control to trigger, that ability triggers an additional time."
  (Elesh Norn, Mother of Machines; Starfield Vocalist) - and the same template
  gated on another card type, Ancient Greenwarden's "If a land entering ...",
  the second printing (legal in Modern and Pioneer, in no deck in the api's
  pool) that proves the cause is read, not the one card.
- "Permanents entering don't cause abilities of permanents your opponents
  control to trigger." (Elesh Norn) - Torpor Orb's suppression template with a
  controller scope on the abilities it stops.

Every CR number below was looked up with `mise run rules:find` in the session
that wrote this file:

- **CR 603.2d** - "An ability may state that a triggered ability triggers
  additional times. In this case, rather than simply determining that such an
  ability has triggered, determine how many times it should trigger, then that
  ability triggers that many times."
- **CR 603.6a** - "Enters-the-battlefield abilities trigger when a permanent
  enters the battlefield. ... all permanents on the battlefield (including the
  newcomers) are checked for any enters-the-battlefield triggers that match
  the event."
"""

from magic_cards_model.machines import Step
from magic_cards_model.support import HANDLED, classify_clauses
from tests.cards import card
from tests.scenarios.harness import PlayedScenario, Scenario

NORN = "Elesh Norn, Mother of Machines"
VOCALIST = "Starfield Vocalist"
GREENWARDEN = "Ancient Greenwarden"


def triggered(scenario: PlayedScenario) -> list[tuple[str, str]]:
    """Each pending trigger as (source, controller)."""
    return [(item.source_name, item.controller) for item in scenario.game.pending_triggers]


def board(
    alice_board: list[str],
    bob_board: list[str] | None = None,
    *,
    alice_hand: list[str] | None = None,
    bob_hand: list[str] | None = None,
) -> PlayedScenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=alice_board,
            hand=alice_hand or [],
            library=["Forest"] * 10,
        )
        .player(
            "bob",
            battlefield=bob_board or [],
            hand=bob_hand or [],
            library=["Forest"] * 10,
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.pending_triggers.clear()
    return scenario


# -- the sweep reads both lines ------------------------------------------------


def test_every_multiplier_and_suppressor_line_is_handled() -> None:
    for name in (NORN, VOCALIST, GREENWARDEN):
        lines = [
            c for c in classify_clauses(card(name)) if "entering" in c.text and "trigger" in c.text
        ]
        assert lines, name
        assert {c.category for c in lines} == {HANDLED}, name


# -- doubling (CR 603.2d) --------------------------------------------------------


def test_a_permanent_entering_doubles_its_own_enters_trigger() -> None:
    scenario = board([NORN], alice_hand=["Didact Echo"])

    scenario.put_onto_battlefield("Didact Echo", "alice")

    assert triggered(scenario) == [("Didact Echo", "alice")] * 2


def test_a_permanent_entering_doubles_another_permanent_s_trigger() -> None:
    """Soul Warden watches; the Grizzly Bears entering is the cause."""
    scenario = board([NORN, "Soul Warden"], alice_hand=["Grizzly Bears"])

    scenario.put_onto_battlefield("Grizzly Bears", "alice")

    assert triggered(scenario) == [("Soul Warden", "alice")] * 2


def test_a_land_is_a_permanent_so_landfall_is_doubled_too() -> None:
    """ "a permanent entering" - not only an artifact or creature."""
    scenario = board([VOCALIST, "Icetill Explorer"], alice_hand=["Forest"])

    scenario.put_onto_battlefield("Forest", "alice")

    assert triggered(scenario) == [("Icetill Explorer", "alice")] * 2


def test_the_doubled_triggers_both_resolve() -> None:
    scenario = board([NORN], alice_hand=["Didact Echo"])
    hand_before = len(scenario.player("alice").hand)

    scenario.put_onto_battlefield("Didact Echo", "alice")
    scenario.pass_until_resolved()
    scenario.pass_until_resolved()

    # Didact Echo left the hand; two cards were drawn.
    assert len(scenario.player("alice").hand) == hand_before - 1 + 2


def test_an_opponent_s_permanent_is_not_doubled() -> None:
    """ "a triggered ability of a permanent **you** control"."""
    scenario = board([VOCALIST], ["Soul Warden"], alice_hand=["Grizzly Bears"])

    scenario.put_onto_battlefield("Grizzly Bears", "alice")

    assert triggered(scenario) == [("Soul Warden", "bob")]


def test_a_trigger_not_caused_by_an_entrance_is_not_doubled() -> None:
    """Soul Warden gains life off a creature entering; a land entering does
    not cause it, and Didact Echo's draw is not caused by anything entering
    once it is already there - here the event is a *land*, which Soul Warden
    ignores, so nothing triggers at all."""
    scenario = board([NORN, "Soul Warden"], alice_hand=["Forest"])

    scenario.put_onto_battlefield("Forest", "alice")

    assert triggered(scenario) == []


def test_two_multipliers_each_add_one_more() -> None:
    scenario = board([NORN, VOCALIST], alice_hand=["Didact Echo"])

    scenario.put_onto_battlefield("Didact Echo", "alice")

    assert triggered(scenario) == [("Didact Echo", "alice")] * 3


def test_a_land_gated_multiplier_doubles_landfall() -> None:
    """Ancient Greenwarden: "If a land entering causes ..."."""
    scenario = board([GREENWARDEN, "Icetill Explorer"], alice_hand=["Forest"])

    scenario.put_onto_battlefield("Forest", "alice")

    assert triggered(scenario) == [("Icetill Explorer", "alice")] * 2


def test_a_land_gated_multiplier_ignores_a_creature_entering() -> None:
    scenario = board([GREENWARDEN], alice_hand=["Didact Echo"])

    scenario.put_onto_battlefield("Didact Echo", "alice")

    assert triggered(scenario) == [("Didact Echo", "alice")]


def test_the_multiplier_stops_when_it_leaves() -> None:
    scenario = board([VOCALIST], alice_hand=["Didact Echo"])
    vocalist = scenario.creature(VOCALIST, "alice")
    scenario.game.put_into_graveyard(vocalist)

    scenario.put_onto_battlefield("Didact Echo", "alice")

    assert triggered(scenario) == [("Didact Echo", "alice")]


# -- suppression (Elesh Norn's second line) ------------------------------------


def test_an_opponent_s_own_enters_trigger_does_not_trigger() -> None:
    scenario = board([NORN], bob_hand=["Didact Echo"])

    scenario.put_onto_battlefield("Didact Echo", "bob")

    assert triggered(scenario) == []


def test_an_opponent_s_watcher_does_not_trigger_off_my_creature() -> None:
    """Bob's Soul Warden is a permanent Norn's controller's opponent controls;
    alice's Grizzly Bears entering does not cause it to trigger - and alice's
    own Soul Warden still does, doubled."""
    scenario = board([NORN, "Soul Warden"], ["Soul Warden"], alice_hand=["Grizzly Bears"])

    scenario.put_onto_battlefield("Grizzly Bears", "alice")

    assert triggered(scenario) == [("Soul Warden", "alice")] * 2


def test_my_own_permanents_still_trigger_off_an_opponent_s_entrance() -> None:
    """The scope is whose ability it is, not whose permanent entered: bob's
    creature entering still triggers alice's Soul Warden."""
    scenario = board([NORN, "Soul Warden"], bob_hand=["Grizzly Bears"])

    scenario.put_onto_battlefield("Grizzly Bears", "bob")

    assert triggered(scenario) == [("Soul Warden", "alice")] * 2


def test_the_suppression_ends_when_norn_leaves() -> None:
    scenario = board([NORN], bob_hand=["Didact Echo"])
    norn = scenario.creature(NORN, "alice")
    scenario.game.put_into_graveyard(norn)

    scenario.put_onto_battlefield("Didact Echo", "bob")

    assert triggered(scenario) == [("Didact Echo", "bob")]


def test_two_norns_on_opposite_sides_stop_each_other_s_entering_triggers() -> None:
    scenario = board([NORN], [NORN, "Soul Warden"], alice_hand=["Didact Echo"])

    scenario.put_onto_battlefield("Didact Echo", "alice")

    # Alice's Didact Echo is an ability of a permanent bob's opponent (alice)
    # controls: bob's Norn stops it. Bob's Soul Warden is stopped by alice's.
    assert triggered(scenario) == []


def test_a_creature_gated_suppressor_still_stops_everything() -> None:
    """Hushwing Gryff's unscoped "Creatures entering don't cause abilities to
    trigger." is unchanged: every ability, whoever controls it."""
    scenario = board(["Hushwing Gryff", "Soul Warden"], ["Soul Warden"], alice_hand=["Didact Echo"])

    scenario.put_onto_battlefield("Didact Echo", "alice")

    assert triggered(scenario) == []


# -- a subtype cause with "you control" (Naban, Dean of Iteration) --------------


def test_a_wizard_you_control_entering_doubles_a_watcher() -> None:
    """Naban - the second printing of the cause reader: a subtype, and "you
    control" on the entering permanent."""
    scenario = board(["Naban, Dean of Iteration", "Soul Warden"], alice_hand=["Aether Adept"])

    scenario.put_onto_battlefield("Aether Adept", "alice")

    wardens = [entry for entry in triggered(scenario) if entry[0] == "Soul Warden"]
    assert wardens == [("Soul Warden", "alice")] * 2


def test_a_non_wizard_entering_is_not_doubled_by_naban() -> None:
    scenario = board(["Naban, Dean of Iteration", "Soul Warden"], alice_hand=["Grizzly Bears"])

    scenario.put_onto_battlefield("Grizzly Bears", "alice")

    assert triggered(scenario) == [("Soul Warden", "alice")]


def test_an_opponent_s_wizard_entering_is_not_doubled_by_naban() -> None:
    """ "a Wizard **you control** entering" - bob's Wizard does not count."""
    scenario = board(["Naban, Dean of Iteration", "Soul Warden"], bob_hand=["Aether Adept"])

    scenario.put_onto_battlefield("Aether Adept", "bob")

    wardens = [entry for entry in triggered(scenario) if entry[0] == "Soul Warden"]
    assert wardens == [("Soul Warden", "alice")]
