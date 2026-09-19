"""FRA stream S8: "Mill `<n>` cards. When you do, return target `<quality>`
card from your graveyard to the battlefield[ tapped]." - CR 603.12's
mandatory ("instruct") reflexive trigger, the same general shape
`_parse_reflexive_mandatory_token_clause` already reads for a token-creation
consequence, now for a mill-then-return one.

Every CR number below was looked up with `mise run rules:find` in the
session that wrote this file.

- **CR 701.17a** - milling: that many cards from the top of the library into
  the graveyard.
- **CR 701.17b** - milling more than the library holds mills as many as
  possible instead; a plain mandatory mill never grants a choice to decline.
- **CR 603.12** - "A resolving spell or ability may allow or instruct a
  player to take an action and create a triggered ability that triggers
  ... 'when [something happens] this way.'" Primal Witchstalker's own "mill
  four cards" is the *instruct* half (no "may"), so the reflexive ability is
  created unconditionally once the mill has happened, mirroring
  `_parse_reflexive_mandatory_token_clause`'s own token-creation sibling.
- **CR 714.2b** - a Saga chapter ability, for The Last Ronin's own chapter
  II below.
- **CR 714.3a / CR 122.6** - a Saga's own intrinsic "enters with a lore
  counter" replacement effect, which is what fires chapter I the instant it
  resolves.

Primal Witchstalker's own ETB is the reported card - a mandatory mill of
four, then a reflexive "return target land card from your graveyard to the
battlefield tapped." The Last Ronin (real, non-FRA, non-pool) is the off-set
proof: the identical mandatory-mill-then-reflexive-return shape, printed on a
Saga chapter rather than an ETB, with a different quality (creature card, not
land) and a different destination (hand, not the battlefield, and so no
"tapped" rider at all) - proving the merge and the return-side regex both
read the general shape, not Primal Witchstalker's own exact sentence. Read at
the clause level rather than played through a full Saga cast, for the reason
given in its own test's docstring below.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from magic_cards_model.models.card import Type
from tests.scenarios.harness import Scenario


def test_primal_witchstalker_mills_then_returns_a_land_tapped():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Primal Witchstalker"],
            battlefield=["Swamp", "Forest", "Island"],
            library=["Plains", "Mountain", "Grizzly Bears", "Lightning Bolt"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Swamp", "Forest", "Island")
    library_before = list(scenario.player("alice").library)

    scenario.will_choose_targets(library_before[1], username="alice")
    scenario.cast_and_resolve("Primal Witchstalker", *sources)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    alice = scenario.player("alice")
    assert len(alice.graveyard) == 3, "four milled, one (the Mountain) returned"
    mountain = scenario.find("Mountain", Zone.BATTLEFIELD, "alice")
    assert mountain.zone is Zone.BATTLEFIELD
    assert mountain.tapped, "CR 603.12's return specifies tapped"


def test_primal_witchstalker_returns_nothing_with_no_land_in_the_mill():
    """No land card ever reaches the graveyard, so there is nothing that
    satisfies "target land card from your graveyard" - the reflexive ability
    is still created (CR 603.12: the mill already happened unconditionally),
    but its own targeted return simply has no legal target and does
    nothing."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Primal Witchstalker"],
            battlefield=["Swamp", "Forest", "Island"],
            library=["Grizzly Bears", "Lightning Bolt", "Grizzly Bears", "Lightning Bolt"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Swamp", "Forest", "Island")
    lands_before = {
        p.id for p in scenario.game.battlefield if p.controller == "alice" and Type.LAND in p.types
    }

    scenario.cast_and_resolve("Primal Witchstalker", *sources)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    alice = scenario.player("alice")
    assert len(alice.graveyard) == 4, "the mill still happened with no land among it"
    lands_after = {
        p.id for p in scenario.game.battlefield if p.controller == "alice" and Type.LAND in p.types
    }
    assert lands_after == lands_before, "no land ever reached the graveyard to return"


def test_the_last_ronin_chapter_reads_a_hand_destination_with_no_tapped_rider():
    """The Last Ronin's own chapter II: "Mill four cards. When you do,
    return target creature card from your graveyard to your hand." - a
    different quality (creature card, not land) and a different destination
    (hand, not the battlefield, and so no "tapped" rider), proving the
    merge and the return-side regex both read the general shape rather than
    Primal Witchstalker's own exact sentence.

    Cast end to end, once `_spell_text`'s own chapter-line strip (see
    `test_saga_chapter_targets_do_not_reach_spell_level_announcement.py`)
    stops a later chapter's own "target" phrase from being read as the
    casting Saga spell's own target.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["The Last Ronin"],
            battlefield=[
                "Grizzly Bears",
                "Swamp",
                "Forest",
                "Plains",
                "Plains",
                "Plains",
                "Plains",
            ],
            library=["Forest", "Mountain", "Swamp", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Swamp", "Forest", "Plains", "Plains", "Plains", "Plains")
    alice = scenario.player("alice")

    # Chapter I ("Destroy all creatures") fires the instant the Saga enters
    # (CR 714.3a, CR 122.6) - Grizzly Bears dies into the graveyard, giving
    # chapter II's own return a real creature card to target.
    scenario.cast_and_resolve("The Last Ronin", *sources)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")
    assert bears.zone is Zone.GRAVEYARD

    hand_before = len(alice.hand)
    scenario.will_choose_targets(bears, username="alice")
    scenario.game.saga_lore_step()
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert bears.zone is Zone.HAND, "the general merge reads a hand destination too"
    assert len(alice.hand) == hand_before + 1
