"""ecl-T8's own mill-then-select widenings (CR 701.17a's mill):

1. **A brand-new destination**: "mill N cards, then [you may ]put a[n]
   `<quality>` card [from among them|from your graveyard] on top of your
   library." (`_MILL_THEN_MAY_PUT_ON_TOP_RE`) - Lluwen, Imperfect
   Naturalist's own ETB trigger, "mill four cards, then you may put a
   creature or land card from among the milled cards on top of your
   library," and, with a different candidate pool, Sequestered Stash's own
   activated ability: "Mill five cards. Then you may put an artifact card
   from your graveyard on top of your library." No existing reader put a
   card on top of the library at all - `_MILL_THEN_MAY_TAKE_FROM_MILLED_RE`'s
   own family only ever lands a card in a hand or on the battlefield.

2. **Two widenings of `_MILL_THEN_MAY_TAKE_FROM_MILLED_RE`** (already
   proven generally on Rapid Rescue/Cantankerous Keepers/Glamdring in
   `test_mill_then_take_from_milled.py`): an anaphor with no "from among"
   prefix at all ("milled this way" standing alone, Vivien on the Hunt's own
   `+1`: "Mill five cards, then put any number of creature cards milled this
   way into your hand."), and "return ... to your hand" as the identical
   move `_parse_mill_then_may_take_from_milled` already reads as "put ...
   into your hand" (Midnight Tilling's own "Mill four cards, then you may
   return a permanent card from among them to your hand.").

Proof printings (both real Scryfall data, added with `scripts/add_card.py`,
neither a listed ecl-T8 card, neither in any deck list):

- **Sequestered Stash** (Pioneer/Modern `legal`) - the "from your graveyard"
  candidate pool (the *whole* graveyard, not just what this instruction's
  own mill just made - the same pool/anaphora distinction
  `_MILL_THEN_MAY_RETURN_CREATURE_RE` already draws for its own "from your
  graveyard" shape), and a single-word quality ("artifact") where Lluwen's
  own is a two-word "creature or land" alternation.
- **Vivien on the Hunt** (Pioneer/Modern `legal`) - the "milled this way"
  anaphor with no "from among" prefix, and "any number of" (CR 107.1c)
  where Midnight Tilling's own is a bare, "you may"-gated single card.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 701.17a** - "To mill a card, a player puts the top card of their
  library into their graveyard."
- **CR 400.7** - "from among them"/"milled this way" both name the cards
  this same instruction's own mill just moved, not the graveyard generally.
- **CR 401.2** - "on top of" a library is the position new cards go by
  default; nothing here needs a separate rule for it beyond "the top card".
- **CR 608.2d** - a printed "you may" is CR 608.2d's own optional
  instruction; "any number of" is CR 107.1c's built-in range, needing no
  separate "may" gate.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.support import card_support
from tests.cards import card

from .harness import Scenario

LLUWEN = "Lluwen, Imperfect Naturalist"
MIDNIGHT_TILLING = "Midnight Tilling"
SEQUESTERED_STASH = "Sequestered Stash"
VIVIEN = "Vivien on the Hunt"


def test_all_four_printings_are_fully_handled():
    for name in (LLUWEN, MIDNIGHT_TILLING, SEQUESTERED_STASH, VIVIEN):
        bad = [c for c in card_support(card(name)).clauses if c.outcome != "handled"]
        assert not bad, (name, bad)


# -- Lluwen: mill, then may put a creature-or-land card among them on top ---


def test_lluwen_puts_a_milled_land_on_top_of_the_library():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=[LLUWEN],
            battlefield=["Forest"] * 2 + ["Swamp"] * 2,
            library=["Mountain", "Lightning Bolt", "Grizzly Bears", "Opt"],
        )
        .player("bob")
        .build()
    )
    alice = scenario.player("alice")
    mountain, bolt, bears, opt = alice.library
    sources = scenario.untapped_sources("Forest", "Forest", "Swamp", "Swamp")

    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(True, username="alice", source=LLUWEN)
    scenario.will_choose_cards(bears, username="alice", source=LLUWEN)
    scenario.cast_and_resolve(LLUWEN, *sources)
    scenario.pass_until_resolved()  # the ETB trigger

    assert mountain.zone is Zone.GRAVEYARD
    assert bolt.zone is Zone.GRAVEYARD
    assert opt.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.LIBRARY
    assert alice.library[0] is bears, "CR 401.2: on top, above every card already there"


def test_lluwen_declining_the_may_leaves_every_milled_card_in_the_graveyard():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=[LLUWEN],
            battlefield=["Forest"] * 2 + ["Swamp"] * 2,
            library=["Mountain", "Lightning Bolt", "Grizzly Bears", "Opt"],
        )
        .player("bob")
        .build()
    )
    alice = scenario.player("alice")
    mountain, bolt, bears, opt = alice.library
    sources = scenario.untapped_sources("Forest", "Forest", "Swamp", "Swamp")

    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(False, username="alice", source=LLUWEN)
    scenario.cast_and_resolve(LLUWEN, *sources)
    scenario.pass_until_resolved()

    assert {mountain.zone, bolt.zone, bears.zone, opt.zone} == {Zone.GRAVEYARD}


# -- Sequestered Stash: mill, then may put an artifact from the graveyard ---
# (not just what was milled this way) on top -------------------------------


def test_sequestered_stash_puts_an_artifact_already_in_the_graveyard_on_top():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=[SEQUESTERED_STASH] * 5,
            graveyard=["Mind Stone"],
            library=["Mountain", "Grizzly Bears", "Opt", "Lightning Bolt"],
        )
        .player("bob")
        .build()
    )
    alice = scenario.player("alice")
    stone = alice.graveyard[0]
    mountain, bears, opt, bolt = alice.library
    stash, *mana_sources = scenario.untapped_sources(*([SEQUESTERED_STASH] * 5))

    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(True, username="alice", source=SEQUESTERED_STASH)
    scenario.will_choose_cards(stone, username="alice", source=SEQUESTERED_STASH)
    scenario.activate(stash, *mana_sources, index=1, sacrificing=[stash])
    scenario.resolve_top()

    assert mountain.zone is Zone.GRAVEYARD
    assert bears.zone is Zone.GRAVEYARD
    assert opt.zone is Zone.GRAVEYARD
    assert bolt.zone is Zone.GRAVEYARD
    assert stone.zone is Zone.LIBRARY
    assert alice.library[0] is stone, "an artifact from the graveyard generally, not from the mill"


# -- Midnight Tilling: mill, then may return a permanent card to hand ------


def test_midnight_tilling_returns_a_milled_permanent_to_hand():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=[MIDNIGHT_TILLING],
            battlefield=["Forest"] * 2,
            library=["Grizzly Bears", "Lightning Bolt", "Opt", "Mountain"],
        )
        .player("bob")
        .build()
    )
    alice = scenario.player("alice")
    bears, bolt, opt, mountain = alice.library
    sources = scenario.untapped_sources("Forest", "Forest")

    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_take_the_may(True, username="alice", source=MIDNIGHT_TILLING)
    scenario.will_choose_cards(bears, username="alice", source=MIDNIGHT_TILLING)
    scenario.cast_and_resolve(MIDNIGHT_TILLING, *sources)

    assert bears.zone is Zone.HAND, "'return ... to your hand' is 'put ... into your hand'"
    assert bolt.zone is Zone.GRAVEYARD
    assert opt.zone is Zone.GRAVEYARD
    assert mountain.zone is Zone.GRAVEYARD


# -- Vivien on the Hunt: mill, then any number of creature cards to hand ----


def test_vivien_mills_and_takes_every_creature_milled_this_way():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            battlefield=[VIVIEN],
            library=["Grizzly Bears", "Lightning Bolt", "Elvish Mystic", "Opt", "Mountain"],
        )
        .player("bob")
        .build()
    )
    alice = scenario.player("alice")
    bears, bolt, mystic, opt, mountain = alice.library
    vivien = scenario.find(VIVIEN, Zone.BATTLEFIELD, "alice")

    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.will_choose_cards(bears, mystic, username="alice", source=VIVIEN)
    scenario.activate(vivien, index=1)
    scenario.resolve_top()

    assert bears.zone is Zone.HAND, "'milled this way' names the cards this mill just moved"
    assert mystic.zone is Zone.HAND
    assert bolt.zone is Zone.GRAVEYARD, "not a creature - never offered"
    assert opt.zone is Zone.GRAVEYARD
    assert mountain.zone is Zone.GRAVEYARD
