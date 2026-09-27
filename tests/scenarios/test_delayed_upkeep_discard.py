"""Scenario: a delayed random discard, created by an enters-the-battlefield
trigger and firing at the controller's own next upkeep (CR 603.7).

Casey Jones, Vigilante: "When Casey Jones enters, draw three cards. At the
beginning of your next upkeep, discard three cards at random." The draw is
an ordinary plain player clause with no reader of its own; what is new is
`DiscardCardsAtRandomForController`, a thin `DelayedEffectSpec` wrapper
around the already-existing, already-tested `_discard_at_random` (CR
701.9b's random discard, no decision asked of anybody - Curse-Marred Demon's
own immediate "discard a card at random" already exercises that primitive),
created by the same "at the beginning of your next upkeep" timing
`test_pact_delayed_upkeep_cost.py`'s Summoner's Pact and
`test_delayed_transform_next_upkeep.py`'s Aang already build delayed
triggers with.

No second real printing shares this exact "draw N. At the beginning of your
next upkeep, discard N at random." template - verified by a Scryfall
full-text oracle search for "at the beginning of your next upkeep, discard"
(and the looser "next upkeep" + "discard" + "at random"), which returns
Casey Jones alone among Modern/Pioneer/Standard-legal printings; recorded as
a dated line in `MEMORY.md`. This file leans on corner cases on the
listed card itself instead: a hand shorter than three at the time the
discard actually happens, the delayed trigger firing only on its own
controller's own upkeep and not an opponent's, and the trigger never firing
at all when it was never created.

CR numbers verified with `mise run rules:find` in the session that wrote
this file: 603.7/603.7a (a delayed triggered ability, created now, waiting
for a later event), 603.7d/e (its controller is the creating ability's
controller, taken as it resolved - not whoever's upkeep happens to come
first), 701.9b (a random discard lets the affected player choose nothing;
CR 701.9a's own floor, "if that player is instructed to discard more cards
than they have, they discard their hand", is what a short hand falls back
to), 500.4 (mana empties between steps - not needed here, but the same
turn-structure primitive the untap-to-upkeep walk below relies on), 121.2
(a player draws for themselves unless told otherwise).
"""

from magic_cards_model.machines import Step
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario

CASEY_JONES = "Casey Jones, Vigilante"


def test_listed_printing_is_handled():
    bad = [c for c in card_support(card(CASEY_JONES)).clauses if c.outcome != "handled"]
    assert not bad, bad


def _casey_board(**alice_extra):
    return (
        Scenario()
        .player(
            "alice",
            hand=[CASEY_JONES],
            battlefield=["Mountain"] * 3,
            library=["Grizzly Bears", "Hill Giant", "Lightning Bolt", "Mountain", "Mountain"],
            **alice_extra,
        )
        .player("bob", library=["Mountain"] * 5)
        .build()
    )


def _advance_to_next_upkeep_of(scenario, username: str) -> None:
    while not (scenario.step is Step.UPKEEP and scenario.turn.active_player == username):
        scenario.advance()
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()


def test_casey_jones_draws_three_cards_immediately():
    scenario = _casey_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    scenario.cast_and_resolve(CASEY_JONES, *sources)
    scenario.pass_until_resolved()  # the ETB trigger

    assert len(scenario.player("alice").hand) == 3


def test_the_delayed_discard_fires_at_alices_own_next_upkeep():
    scenario = _casey_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    scenario.cast_and_resolve(CASEY_JONES, *sources)
    scenario.pass_until_resolved()
    assert len(scenario.player("alice").hand) == 3

    _advance_to_next_upkeep_of(scenario, "alice")

    assert scenario.player("alice").hand == []


def test_it_only_watches_its_own_controllers_upkeep_not_bobs():
    """CR 603.7d/e: "your next upkeep" is Casey Jones's own controller's,
    not whichever upkeep step happens to come first in the game."""
    scenario = _casey_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    scenario.cast_and_resolve(CASEY_JONES, *sources)
    scenario.pass_until_resolved()

    while scenario.turn.active_player != "bob" or scenario.step is not Step.UPKEEP:
        scenario.advance()
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()

    assert len(scenario.player("alice").hand) == 3, "bob's upkeep is not alice's own next upkeep"
    assert scenario.game.delayed_triggers.triggers, "the delayed trigger is still waiting"


def test_a_hand_shorter_than_three_at_discard_time_discards_the_whole_hand():
    """CR 701.9a's own floor: instructed to discard more than the hand
    holds, the player discards everything they have."""
    scenario = _casey_board()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Mountain", "Mountain", "Mountain")
    scenario.cast_and_resolve(CASEY_JONES, *sources)
    scenario.pass_until_resolved()

    hand = list(scenario.player("alice").hand)
    scenario.game.discard_cards("alice", hand[:2], source=CASEY_JONES)
    assert len(scenario.player("alice").hand) == 1

    _advance_to_next_upkeep_of(scenario, "alice")

    assert scenario.player("alice").hand == []
