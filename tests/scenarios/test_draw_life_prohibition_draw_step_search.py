"""Mornsong Aria's own two-ability shape:

- **Static**: "Players can't draw cards or gain life." - CR 119.7's own
  life-gain prohibition (`Game.life_gain_prohibited`, already read off the
  battlefield for Leyline of Punishment's "Players can't gain life.")
  combined in one sentence with CR 121.3's drawing twin, which this file adds
  as `Game.draw_prohibited` - a mirror-image dynamic scan, not a persisted
  per-player flag, since CR 604.2/611.3a bounds it to the source's own time
  on the battlefield.
- **Triggered**: "At the beginning of each player's draw step, that player
  loses 3 life, searches their library for a card, puts it into their hand,
  then shuffles." - the ordinary turn-based draw (CR 121.1) never happens at
  all (the static ban above), and this ability performs the search-and-
  shuffle instead, for *whichever* player's draw step just began ("that
  player" reading CR 607.1's anaphora onto the trigger event's own subject,
  `_step_matches`'s existing "each `<step>`" CR 500.6 fallback).

Proof printing: **Maralen of the Mornsong** (real Scryfall data, added with
`scripts/add_card.py`, Modern-legal, not a listed ecl-T8 card, not in any
deck list) - the identical draw-step ability, paired with a bare "Players
can't draw cards." (no combined "or gain life") - proving the static
prohibition reader generally, on its own, single-clause shape rather than
only Mornsong Aria's combined one.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 119.7** - "If an effect says that a player can't gain life ... a cost
  that involves having that player gain life can't be paid."
- **CR 121.3 / 121.3a** - "if an effect says that a player can't draw cards
  and another effect offers that player the choice to draw a card, that
  player can't choose to do so" - extended here to the plain turn-based draw
  itself, the same "can't precedence" CR 101.2 already gives the life-gain
  twin.
- **CR 121.1** - the turn-based draw this ban suppresses.
- **CR 500.6** - "any abilities that trigger 'at the beginning of' that
  phase or step trigger" - "each player's draw step" needs no restriction
  read to the ability's own controller.
- **CR 607.1** - "that player" is anaphora back to the triggering event's
  own subject.
- **CR 611.1 / CR 604.2 / CR 611.3a** - a static ability's continuous effect
  bound to while its source is on the battlefield, not "locked in".
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario

MORNSONG_ARIA = "Mornsong Aria"
MARALEN = "Maralen of the Mornsong"


def test_both_printings_are_fully_handled():
    for name in (MORNSONG_ARIA, MARALEN):
        bad = [c for c in card_support(card(name)).clauses if c.outcome != "handled"]
        assert not bad, (name, bad)


def _board(*, source: str):
    return (
        Scenario()
        .player(
            "alice",
            battlefield=[source],
            library=["Grizzly Bears", "Opt", "Mountain"],
        )
        .player("bob", library=["Lightning Bolt", "Forest"])
        .build()
    )


def test_mornsong_aria_replaces_a_players_draw_with_lose_life_and_search():
    """Driven onto bob's own draw step, not alice's (Mornsong Aria's own
    controller): CR 103.8a skips only *the starting player's* very first
    draw step, and bob is not seat 0, so his own first turn is the plain
    case that also proves 'each player's draw step' fires for a player other
    than this ability's controller."""
    scenario = _board(source=MORNSONG_ARIA)
    bob = scenario.player("bob")
    bolt, forest = bob.library
    bob.life = 20

    scenario.turn.advance_to(Step.CLEANUP)
    scenario.game.sync_priority_with_step()
    scenario.advance()  # bob's untap
    scenario.advance()  # bob's upkeep
    scenario.will_choose_cards(bolt, username="bob", source=MORNSONG_ARIA)
    scenario.advance()  # bob's draw step: the trigger fires
    scenario.pass_until_resolved()

    assert bob.life == 17, "CR 119.4: loses 3 life"
    assert bolt in bob.hand, "searched for and found"
    assert forest.zone is Zone.LIBRARY
    assert bob.hand == [bolt], "CR 121.3: the ordinary turn-based draw never happened"


def test_mornsong_aria_blocks_an_effect_that_would_gain_life():
    scenario = _board(source=MORNSONG_ARIA)
    alice = scenario.player("alice")
    alice.life = 10

    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.gain_life(alice, 5)

    assert alice.life == 10, "CR 119.7: the gain simply does not occur"


def test_mornsong_aria_blocks_an_effect_that_would_draw_a_card():
    scenario = _board(source=MORNSONG_ARIA)
    alice = scenario.player("alice")
    bears, opt, mountain = alice.library

    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.draw_cards(alice, 1)

    assert alice.hand == [], "CR 121.3: the draw simply does not happen"
    assert bears.zone is Zone.LIBRARY


def test_mornsong_aria_stops_prohibiting_once_it_leaves_the_battlefield():
    """CR 604.2/611.3a: the static effect is not 'locked in' - destroying the
    source mid-turn lets ordinary draws and life gain resume at once."""
    scenario = _board(source=MORNSONG_ARIA)
    alice = scenario.player("alice")
    aria = scenario.find(MORNSONG_ARIA, Zone.BATTLEFIELD, "alice")
    alice.life = 10

    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.destroy(aria)
    scenario.game.check_state_based_actions()
    scenario.game.draw_cards(alice, 1)
    scenario.game.gain_life(alice, 4)

    assert len(alice.hand) == 1, "the ban is gone with its source"
    assert alice.life == 14


def test_maralens_bare_draw_prohibition_still_blocks_the_draw_alone():
    """Maralen prints only "Players can't draw cards." (no "or gain life") -
    proving the single-clause reader generally, not just Mornsong Aria's own
    combined sentence."""
    scenario = _board(source=MARALEN)
    alice = scenario.player("alice")

    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.game.draw_cards(alice, 1)
    scenario.game.gain_life(alice, 3)  # Maralen names no life-gain ban at all

    assert alice.hand == [], "CR 121.3: drawing is banned"
    assert alice.life == 23, "Maralen alone never bans gaining life"
