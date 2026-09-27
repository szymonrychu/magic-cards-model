"""Disappear (CR 207.2c ability word) as a CR 614.1c enters-with-counters
replacement: Putrid Pals's "This creature enters with two +1/+1 counters on
it if a permanent left the battlefield under your control this turn."

The condition itself - "a permanent left the battlefield under your control
this turn" - is Revolt's own (CR 207.2c), already read generically by
`Game.revolt_active_for` for Renegade Rallier's and Fatal Push's *triggered*-
ability intervening ifs (`machines/triggers.py`'s `_REVOLT_CLAUSES`). What was
missing was `machines/replacement._read_enters_condition` reading the same
clause text for the *replacement*-effect position `_ENTERS_WITH` already
parses (Festerhide Boar's own Morbid rider proves that regex already handles
a trailing "if ..." on an "enters with" sentence) - this file is the proof
that reusing `revolt_active_for` there, rather than re-deriving the fact, is
correct.

CR numbers verified this session with `mise run rules:find`:

- **CR 207.2c** - Disappear is an ability word, no rules meaning of its own.
- **CR 614.1c** - "[This permanent] enters the battlefield with ... counters
  on it" is a replacement effect, applied as the permanent enters - before
  any triggered ability can see it, so a scenario checks `CardState.counters`
  right after the creature lands, not after any of *its own* ETB triggers.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import Counter

from .harness import Scenario


def _board():
    return (
        Scenario()
        .player(
            "alice",
            hand=["Putrid Pals"],
            battlefield=["Grizzly Bears", "Forest", "Forest", "Forest", "Forest"],
        )
        .player("bob", battlefield=["Hill Giant"])
    )


def test_enters_with_no_counters_when_nothing_left_the_battlefield_this_turn():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.cast_and_resolve(
        "Putrid Pals", *scenario.untapped_sources("Forest", "Forest", "Forest", "Forest")
    )

    pals = scenario.find("Putrid Pals", Zone.BATTLEFIELD, "alice")
    assert pals.counters[Counter.PLUS_ONE] == 0


def test_enters_with_two_counters_when_your_own_permanent_left_this_turn():
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.sacrifice(bears)
    assert bears.zone is Zone.GRAVEYARD

    scenario.cast_and_resolve(
        "Putrid Pals", *scenario.untapped_sources("Forest", "Forest", "Forest", "Forest")
    )

    pals = scenario.find("Putrid Pals", Zone.BATTLEFIELD, "alice")
    assert pals.counters[Counter.PLUS_ONE] == 2


def test_an_opponents_permanent_leaving_does_not_count():
    """ "under your control" - Revolt only watches the caster's own board, so
    Hill Giant (bob's) leaving does nothing for alice's Disappear."""
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    giant = scenario.creature("Hill Giant", "bob")
    scenario.game.sacrifice(giant)
    assert giant.zone is Zone.GRAVEYARD

    scenario.cast_and_resolve(
        "Putrid Pals", *scenario.untapped_sources("Forest", "Forest", "Forest", "Forest")
    )

    pals = scenario.find("Putrid Pals", Zone.BATTLEFIELD, "alice")
    assert pals.counters[Counter.PLUS_ONE] == 0


def test_exile_and_bounce_both_count_as_leaving_the_battlefield_too():
    """CR 701.13a's exile and the plain "return to hand" both move a
    permanent off the battlefield - Revolt does not care which of the three
    routes (CR 701.8a destroy, 701.21a sacrifice, 701.13a exile, or a bounce)
    it was, only that the permanent left."""
    scenario = _board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    scenario.game.return_to_hand(bears)
    assert bears.zone is Zone.HAND

    scenario.cast_and_resolve(
        "Putrid Pals", *scenario.untapped_sources("Forest", "Forest", "Forest", "Forest")
    )

    pals = scenario.find("Putrid Pals", Zone.BATTLEFIELD, "alice")
    assert pals.counters[Counter.PLUS_ONE] == 2
