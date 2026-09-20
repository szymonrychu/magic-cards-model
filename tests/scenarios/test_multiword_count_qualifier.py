"""Scenario: `count_expression`'s "the number of `<qualifier>` you control"
reader (`machines/effects.py`) used to accept only a single word for
`<qualifier>` (`_COUNT_YOU_CONTROL_RE`'s own `[a-z]+` group) - enough for
"creatures" or "Elves", but not Harvest Season's own "the number of tapped
creatures you control", where the qualifier is two words: a status
(CR 110.5's tapped/untapped) plus a type. The regex simply never matched, so
`count_expression` returned `None` for the whole phrase and nothing downstream
ever read it.

This file proves the fix twice, on wording that differs from Harvest
Season's own sentence in every axis that matters: Throne of the God-Pharaoh
(off-pool, modern-legal) reaches the *same* reader through a fully different
mechanic - a triggered "each opponent loses life" rather than a search bound
- so the fix is proven end to end through a real trigger resolving on a real
board, not just the reader called directly. Ben-Ben, Akki Hermit (also
off-pool, modern-legal) swaps the status word ("untapped" instead of
"tapped") and the qualifier's own kind (a subtype, "Mountains", rather than a
card type, "creatures"), so both halves of `count_expression`'s branch - the
card-type read and the subtype read - are exercised with the new status
filter.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 110.5** - "A permanent's status is its physical state. There are four
  status categories ... tapped/untapped, ..." - the status word Harvest
  Season's and Ben-Ben's own qualifiers add.
- **CR 701.26a/701.26b** - tap and untap, the actions that change that status
  (not directly at issue here, but what `CardState.tapped` tracks).
- **CR 613.5** - "you control" is read off the *computed* board, the same
  correction `count_expression`'s other qualifiers already apply.
- **CR 119.3** - life loss, Throne of the God-Pharaoh's own effect.
- **CR 205.2a** - creature is a card type; CR 205.3m's own subtype list is
  where "Mountain" (a basic land type, CR 305.5) lives.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.effects import count_expression
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_harvest_seasons_own_qualifier_counts_tapped_creatures_on_a_real_board():
    """ "the number of tapped creatures you control" - Harvest Season's own
    qualifier, read directly against a real board: two of alice's three
    creatures are tapped, and the untapped one and Harvest Season itself (a
    sorcery, never a permanent) do not count.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Harvest Season"],
            battlefield=["Grizzly Bears", "Grizzly Bears", "Elvish Mystic"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = [c for c in scenario.game.battlefield if c.name == "Grizzly Bears"]
    bears[0].tap()
    bears[1].tap()
    alice = scenario.player("alice")

    counter = count_expression("the number of tapped creatures you control")
    assert counter is not None
    assert counter(scenario.game, alice.username) == 2


def test_throne_of_the_god_pharaoh_drains_life_equal_to_tapped_creatures():
    """Throne of the God-Pharaoh (off-pool, modern-legal): "At the beginning
    of your end step, each opponent loses life equal to the number of tapped
    creatures you control." Reaches `count_expression` through a wholly
    different mechanic than Harvest Season's search bound - a triggered
    life-loss effect (CR 119.3) with no target at all - proving the fix
    through a real trigger, not a direct reader call.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Throne of the God-Pharaoh", "Grizzly Bears", "Elvish Mystic"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.POSTCOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "alice")
    mystic = scenario.find("Elvish Mystic", Zone.BATTLEFIELD, "alice")
    bears.tap()
    mystic.tap()
    bob = scenario.player("bob")
    life_before = bob.life

    scenario.advance()  # end step: "At the beginning of your end step" triggers
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert bob.life == life_before - 2


def test_ben_bens_own_qualifier_counts_untapped_mountains_on_a_real_board():
    """Ben-Ben, Akki Hermit (off-pool, modern-legal): "{T}: Ben-Ben deals
    damage to target attacking creature equal to the number of untapped
    Mountains you control." Swaps both axes at once: "untapped" instead of
    "tapped", and a subtype ("Mountains", CR 205.3m/CR 305.5) instead of a
    card type - `count_expression`'s subtype branch, not its card-type one,
    with the same new status filter. Two of alice's three Mountains are
    untapped; the third and the two Forests do not count.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=[
                "Ben-Ben, Akki Hermit",
                "Mountain",
                "Mountain",
                "Mountain",
                "Forest",
                "Forest",
            ],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    mountains = [c for c in scenario.game.battlefield if c.name == "Mountain"]
    mountains[0].tap()
    alice = scenario.player("alice")

    counter = count_expression("the number of untapped Mountains you control")
    assert counter is not None
    assert counter(scenario.game, alice.username) == 2
