"""Scenario: "Activate only if you control a creature that fought this
turn" (CR 602.5b, CR 701.14a) - Boxing Ring's own activation restriction,
read as a *quality suffix* (`machines/conditions/board.py`'s `_SUFFIXES`)
rather than a clause hardcoded to "creature", so it composes with any
quality the same way every other suffix ("with power 4 or greater", "you
control", ...) already does.

Verified with `mise run rules:find` in this session:

- **CR 701.14a**: "Each of those creatures deals damage equal to its power to
  the other creature." - every fight in the engine goes through the single
  `machines/effects._fight` function, which is where this turn's fights are
  now noted (`conditions.history.record_fight`), so any spell or ability
  that fights two creatures feeds the same ledger Boxing Ring reads.
- **CR 602.5b**: an "Activate only if" restriction refuses the activation
  when the condition is not met, and refuses it outright (rather than
  allowing it unchecked) when the condition is not read at all.

No card besides Boxing Ring prints "fought this turn" at all (a Scryfall
`o:"fought this turn"` search returns exactly one card, industry-wide, across
every format), so no second printing - Modern/Pioneer/Standard-legal or
otherwise - exists to add. Generality is instead demonstrated the way this
package's own suffix grammar is meant to: `Game.condition_holds` is asked the
identical clause with a *different* quality word ("a Zombie that fought this
turn") in `test_the_quality_suffix_generalizes_past_creature` below, backed
by two real, unrelated printings - Arisen Gorgon (a Zombie) and Prey Upon
(Modern-legal; "Target creature you control fights target creature you don't
control") - so the fight and the read are both genuine, only the sentence
asking about them is synthetic. Every fight here is sized so the "you
control" half of the clause stays true afterwards too (CR 701.14a's damage
is real - a fighter that dies stops being a creature you control the moment
state-based actions run, CR 704.5g, so a fight this file stages has to leave
the fighter alive to test the "fought" half in isolation).
"""

from magic_cards_model.machines import Step

from .harness import Scenario


def test_boxing_ring_cannot_be_activated_before_any_creature_has_fought():
    scenario = Scenario().player("alice", battlefield=["Boxing Ring", "Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ring = scenario.creature("Boxing Ring", "alice")

    assert scenario.why_cannot_activate(ring, index=0) is not None


def test_boxing_ring_activates_after_a_creature_you_control_fought_this_turn():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Prey Upon"],
            battlefield=["Boxing Ring", "Grizzly Bears", "Forest"],
        )
        .player("bob", battlefield=["Llanowar Elves"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ring = scenario.creature("Boxing Ring", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    elves = scenario.creature("Llanowar Elves", "bob")
    (forest,) = scenario.untapped_sources("Forest", username="alice")
    scenario.cast_and_resolve("Prey Upon", forest, targets=[bears, elves])

    assert scenario.why_cannot_activate(ring, index=0) is None


def test_boxing_ring_does_not_read_a_fight_from_a_different_turn():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Prey Upon"],
            battlefield=["Boxing Ring", "Grizzly Bears", "Forest"],
            library=["Island"] * 5,
        )
        .player("bob", battlefield=["Llanowar Elves"], library=["Island"] * 5)
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    ring = scenario.creature("Boxing Ring", "alice")
    bears = scenario.creature("Grizzly Bears", "alice")
    elves = scenario.creature("Llanowar Elves", "bob")
    (forest,) = scenario.untapped_sources("Forest", username="alice")
    scenario.cast_and_resolve("Prey Upon", forest, targets=[bears, elves])
    assert scenario.why_cannot_activate(ring, index=0) is None

    turn_now = scenario.game.turn.turns_taken
    while scenario.game.turn.turns_taken == turn_now:
        scenario.advance()
        if scenario.game.stack:
            scenario.pass_until_resolved()

    assert scenario.why_cannot_activate(ring, index=0) is not None


def test_the_quality_suffix_generalizes_past_creature():
    """No second "fought this turn" printing exists at all, so genericity is
    proven directly on `Game.condition_holds` instead: the same suffix that
    reads "a creature that fought this turn" for Boxing Ring reads "a Zombie
    that fought this turn" too, off a real Zombie (Arisen Gorgon, 3/3) that
    really fought (Prey Upon) and survived it."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Prey Upon"],
            battlefield=["Arisen Gorgon", "Forest"],
        )
        .player("bob", battlefield=["Llanowar Elves"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    gorgon = scenario.creature("Arisen Gorgon", "alice")
    elves = scenario.creature("Llanowar Elves", "bob")
    (forest,) = scenario.untapped_sources("Forest", username="alice")

    assert scenario.game.condition_holds("alice", "you control a Zombie that fought this turn") is (
        False
    )
    assert scenario.game.condition_holds("alice", "you control a Wizard that fought this turn") is (
        False
    )

    scenario.cast_and_resolve("Prey Upon", forest, targets=[gorgon, elves])

    assert scenario.game.condition_holds("alice", "you control a Zombie that fought this turn")
    assert not scenario.game.condition_holds("alice", "you control a Wizard that fought this turn")
