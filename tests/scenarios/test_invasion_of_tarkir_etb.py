"""Invasion of Tarkir's own ETB: "reveal any number of Dragon cards from
your hand. When you do, this Siege deals X plus 2 damage to any other
target, where X is the number of cards revealed this way. (X can be 0.)"

Verified this session with `mise run rules:find` against the current CR:

- **CR 701.20a** - "To reveal a card, show that card to all players for a
  brief time."
- **CR 603.12** - a reflexive triggered ability "triggers based on whether
  the trigger event or events occurred earlier during the resolution of the
  spell or ability that created it" - the printed reminder "(X can be 0.)"
  is what says revealing zero Dragon cards still counts as the reveal
  happening, so the reflexive always fires.

The reflexive damage is a fresh triggered ability (CR 603.12) with its own
target announcement (CR 603.3d), placed on the stack automatically as part
of resolving the ETB ability that creates it (CR 603.3b) - before a scenario
gets a chance to call `choose_trigger_targets` after the fact. It is
scripted instead with `Scenario.will_choose_targets`, queued ahead of the
resolution that creates it; the ETB ability's own announcement asks no
target at all ("reveal any number of ... cards" needs none), so the queued
answer survives untouched until the reflexive's own announcement is the one
that actually asks.
"""

from magic_cards_model.machines import Step
from tests.scenarios.harness import Scenario

TARKIR = "Invasion of Tarkir"


def test_revealing_two_dragons_deals_four_damage():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=[TARKIR, "Archive Dragon", "Archive Dragon"],
            battlefield=["Mountain", "Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lands = scenario.untapped_sources("Mountain", "Mountain")
    alice = scenario.player("alice")
    dragons = [state for state in alice.hand if state.name == "Archive Dragon"]
    bob = scenario.player("bob")
    life_before = bob.life

    scenario.cast_and_resolve(TARKIR, *lands)
    scenario.game.put_triggers_on_stack()
    scenario.will_choose_cards(*dragons, username="alice")
    scenario.will_choose_targets("bob", username="alice", source=TARKIR)
    scenario.pass_until_resolved()  # the ETB trigger: reveals both Dragons,
    # creating and placing the reflexive (CR 603.3b) with the queued target
    scenario.pass_until_resolved()  # the reflexive itself: X=2, deals 2+2

    assert bob.life == life_before - 4


def test_revealing_no_dragons_still_deals_two_damage():
    """ "(X can be 0.)" - declining to reveal any Dragon (or having none)
    still triggers the reflexive, for the bare +2."""
    scenario = (
        Scenario()
        .player("alice", hand=[TARKIR], battlefield=["Mountain", "Mountain"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    lands = scenario.untapped_sources("Mountain", "Mountain")
    bob = scenario.player("bob")
    life_before = bob.life

    scenario.cast_and_resolve(TARKIR, *lands)
    scenario.game.put_triggers_on_stack()
    scenario.will_choose_targets("bob", username="alice", source=TARKIR)
    scenario.pass_until_resolved()  # the ETB trigger: no Dragons to reveal,
    # creating and placing the reflexive (CR 603.3b) with the queued target
    scenario.pass_until_resolved()  # the reflexive still fires: X=0, deals 0+2

    assert bob.life == life_before - 2
