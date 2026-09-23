"""Scenario: "Partner with [name]" (CR 702.124j), the in-game half.

CR 702.124j (verified with `mise run rules:find 702.124` in the session that
wrote this file): "'Partner with [name]' represents two abilities. It means
'You may designate two legendary cards as your commander rather than one if
each has a "partner with [name]" ability with the other's name' and 'When
this permanent enters, target player may search their library for a card
named [name], reveal it, put it into their hand, then shuffle.'"

Only the **second** ability - the one that fires during a game - is this
file's subject. The first is CR 702.124a's own deck-construction rule
("modify the rules for deck construction in the Commander variant ... and
function before the game begins"): this engine targets Modern, Pioneer, and
Standard only (`CLAUDE.md`), none of which is Commander, so that half stays
inert. `scripts/sweep_pool.py`'s `NEEDS_NO_CODE` documents plain "partner"
(CR 702.124h) on the identical rule; `test_the_deck_construction_half_is_
still_inert` below is this file's own proof that crediting "Partner with"
here never widens that inertness by accident (CR 702.124f: the two are
"distinct ... and cannot be combined").

**Every card here is a real Scryfall printing** (`tests/cards.py`), added
with `scripts/add_card.py`. `mise run rules:find 701.23` backs the search
mechanics below:

- **CR 701.23a** - "To search for a card in a zone, look at all cards in
  that zone (even if it's a hidden zone) and find a card that matches the
  given description."
- **CR 701.23b** - "If a player is searching a hidden zone for cards with a
  stated quality, such as a card with a certain card type or color, that
  player isn't required to find some or all of those cards even if they're
  present in that zone." A name is a stated quality the identical way a type
  or a color is (CR 201, card name is a characteristic), so this is what
  makes the search declinable even once "may" has been taken -
  `Game.search_and_put` already reads it that way for every other named- or
  typed-card search in this engine.
- **CR 701.23d/701.24a** - a search of a library always ends in a shuffle,
  whether or not anything was found.

Evie Frye's WotC ruling (`published_at: 2024-07-05`, fetched fresh in the
session that wrote this file via Scryfall's `rulings_uri`) is the other
citation load-bearing here: "'Partner with [name]' represents two abilities.
The first is a triggered ability: 'When this permanent enters the
battlefield, target player may search their library for a card named
[name], reveal it, put it into their hand, then shuffle their library.'" and
"Note that the target player searches their library (which may be affected
by effects such as that of Stranglehold) and that the card they find is
revealed, even though these words aren't included in the ability's reminder
text." The *printed* reminder text on current cards elides "search" and
"reveal" for space ("target player may put [name] into their hand from
their library, then shuffle") - this file's assertions follow the ruling's
fuller wording, which is also what `machines/keywords._partner_with_ability`
generates.

**On the missing second legal pair.** The plan called for a second
Modern/Pioneer/Standard-legal "Partner with" pair, off the Evie Frye/Jacob
Frye pair already in the `magic-cards-model-api` deck pool, to prove the
implementation reads a name off the card rather than off a table. Checked
exhaustively this session against Scryfall's full `keyword:"partner with"`
listing (52 printings total, every one's `legalities.modern`/`.pioneer`/
`.standard` read): **Evie Frye and Jacob Frye are the only "Partner with"
pair ever printed that is legal in any of the three formats** - every other
printing (Commander Legends, Commander precons, Battlebond, Doctor Who,
Jurassic World, Lord of the Rings, ...) is `not_legal` in all three, because
"Partner with" has otherwise only ever been printed into Commander-exclusive
products. No second real pair exists to add. This file proves genericity a
different way instead: `test_jacob_frye_enters_and_finds_evie_frye` runs the
*same* code path in the *other* direction, off the *other* card's own
printed name - a hardcoded "the named card is Jacob Frye" would pass every
Evie-side test here and fail that one outright.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def _board(
    *,
    alice_hand: list[str],
    alice_battlefield: list[str],
    alice_library: list[str] | None = None,
    bob_library: list[str] | None = None,
) -> Scenario:
    return (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=alice_hand,
            battlefield=alice_battlefield,
            library=alice_library or [],
        )
        .player("bob", library=bob_library or [])
    )


def _cast_partner_with(scenario, card_name: str, *sources) -> None:
    """Cast `card_name` and resolve it, then resolve its own ETB trigger.

    CR 603.3b: state-based actions are checked and a pending trigger is put
    on the stack before any player next gets priority, which
    `Game._resolve_top` already does as part of resolving the creature spell
    itself (see `models/game.py`'s own docstring) - so by the time
    `cast_and_resolve` returns, the "Partner with" trigger is already the
    top of the stack, with whatever target `choose_trigger_targets` named
    (queued by the caller before this runs, CR 603.3d).
    """
    permanent = scenario.cast_and_resolve(card_name, *sources)
    assert scenario.stack_names() == [f"{card_name}'s triggered ability"]
    scenario.resolve_top()
    return permanent


# -- target self: finds and reveals the named card --------------------------


def test_evie_frye_targets_herself_and_finds_jacob_frye():
    """The happy path: Evie's controller targets herself, Jacob Frye is
    sitting in her own library, and CR 702.124j's whole chain runs - found,
    revealed (CR 701.20a), put into her hand, library shuffled (CR 701.24a).
    """
    scenario = _board(
        alice_hand=["Evie Frye"],
        alice_battlefield=["Island", "Mountain"],
        alice_library=["Jacob Frye", "Forest", "Forest"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.choose_trigger_targets("Evie Frye", ["alice"])
    scenario.will_take_the_may(True, username="alice", source="Evie Frye")
    shuffles_before = scenario.game.shuffles_performed

    sources = scenario.untapped_sources("Island", "Mountain")
    _cast_partner_with(scenario, "Evie Frye", *sources)

    jacob = scenario.find("Jacob Frye", Zone.HAND, "alice")
    assert jacob in scenario.player("alice").hand
    assert "Jacob Frye" not in [state.name for state in scenario.player("alice").library]
    assert any(
        reveal.card_id == jacob.id and reveal.card_name == "Jacob Frye"
        for reveal in scenario.game.reveals
    ), "CR 701.20a: the found card is revealed even though the printed reminder omits it"
    assert scenario.game.shuffles_performed == shuffles_before + 1, "CR 701.24a"


# -- target opponent: may decline, or may find it in their own library ------


def test_evie_frye_targets_an_opponent_who_finds_jacob_in_their_own_library():
    """ "Target player" - not "you" - searches: Evie's controller (alice)
    targets bob, and the search runs against **bob's** library, not
    alice's, even though bob never cast anything and does not control Evie.
    """
    scenario = _board(
        alice_hand=["Evie Frye"],
        alice_battlefield=["Island", "Mountain"],
        alice_library=["Forest"],  # no Jacob Frye here - proves whose library was read
        bob_library=["Jacob Frye", "Swamp"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.choose_trigger_targets("Evie Frye", ["bob"])
    scenario.will_take_the_may(True, username="bob", source="Evie Frye")

    sources = scenario.untapped_sources("Island", "Mountain")
    _cast_partner_with(scenario, "Evie Frye", *sources)

    jacob = scenario.find("Jacob Frye", Zone.HAND, "bob")
    assert jacob in scenario.player("bob").hand
    assert scenario.player("alice").hand == []  # alice controls Evie but gets nothing


def test_target_opponent_may_decline_the_search_outright():
    """The whole ability is behind its own CR 608.2d "may": bob can refuse
    to search at all, even with Jacob Frye sitting right there. Declining
    skips the search - and its shuffle - entirely, the same way declining
    any other "you may search ..." effect does
    (`_parse_search_reveal_shuffle_top_clause`'s own convention).
    """
    scenario = _board(
        alice_hand=["Evie Frye"],
        alice_battlefield=["Island", "Mountain"],
        bob_library=["Jacob Frye", "Swamp"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.choose_trigger_targets("Evie Frye", ["bob"])
    scenario.will_take_the_may(False, username="bob", source="Evie Frye")
    shuffles_before = scenario.game.shuffles_performed

    sources = scenario.untapped_sources("Island", "Mountain")
    _cast_partner_with(scenario, "Evie Frye", *sources)

    assert scenario.player("bob").hand == []
    assert [state.name for state in scenario.player("bob").library] == ["Jacob Frye", "Swamp"]
    assert scenario.game.shuffles_performed == shuffles_before, "declined outright: no shuffle"


def test_target_player_may_decline_the_find_even_once_searching():
    """CR 701.23b's own declinable find, distinct from the outer "may" above:
    bob agrees to search, Jacob Frye is right there, and he still chooses not
    to take it. The library **does** get shuffled here - the search itself
    ran - which is what tells this case apart from the outright decline.
    """
    scenario = _board(
        alice_hand=["Evie Frye"],
        alice_battlefield=["Island", "Mountain"],
        bob_library=["Jacob Frye", "Swamp"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.choose_trigger_targets("Evie Frye", ["bob"])
    scenario.will_take_the_may(True, username="bob", source="Evie Frye")
    scenario.will_choose_cards(username="bob", source="Evie Frye")  # find none, though offered
    shuffles_before = scenario.game.shuffles_performed

    sources = scenario.untapped_sources("Island", "Mountain")
    _cast_partner_with(scenario, "Evie Frye", *sources)

    assert scenario.player("bob").hand == []
    assert "Jacob Frye" in [state.name for state in scenario.player("bob").library]
    assert scenario.game.shuffles_performed == shuffles_before + 1, "CR 701.24a: still searched"


# -- the named card is not there at all --------------------------------------


def test_the_named_card_absent_from_the_library_still_shuffles():
    """No Jacob Frye anywhere in alice's library: the search still happens
    (CR 701.23a - it is not skipped merely because it cannot succeed) and
    CR 701.24a's shuffle still runs; only the find comes up empty.
    """
    scenario = _board(
        alice_hand=["Evie Frye"],
        alice_battlefield=["Island", "Mountain"],
        alice_library=["Forest", "Mountain"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.choose_trigger_targets("Evie Frye", ["alice"])
    scenario.will_take_the_may(True, username="alice", source="Evie Frye")
    shuffles_before = scenario.game.shuffles_performed
    library_before = sorted(state.name for state in scenario.player("alice").library)

    sources = scenario.untapped_sources("Island", "Mountain")
    _cast_partner_with(scenario, "Evie Frye", *sources)

    assert "Jacob Frye" not in [state.name for state in scenario.player("alice").hand]
    assert sorted(state.name for state in scenario.player("alice").library) == library_before
    assert scenario.game.shuffles_performed == shuffles_before + 1


# -- the name is read off the card's own text, in both directions -----------


def test_jacob_frye_enters_and_finds_evie_frye():
    """The mirror card: Jacob Frye's own "Partner with Evie Frye" line reads
    "Evie Frye" as the name to search for, off *his* printed text.

    A hardcoded "the partner's name is Jacob Frye" (or any single fixed
    string) would pass every test above and fail only this one - which is
    exactly why it is here (`CLAUDE.md`'s "target the mechanic, never the
    card": prove generality on more than one instance of the same shape).
    """
    scenario = _board(
        alice_hand=["Jacob Frye"],
        alice_battlefield=["Swamp", "Forest", "Mountain"],
        alice_library=["Evie Frye", "Island"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.choose_trigger_targets("Jacob Frye", ["alice"])
    scenario.will_take_the_may(True, username="alice", source="Jacob Frye")

    sources = scenario.untapped_sources("Swamp", "Forest", "Mountain")
    _cast_partner_with(scenario, "Jacob Frye", *sources)

    assert scenario.find("Evie Frye", Zone.HAND, "alice") in scenario.player("alice").hand


# -- the trigger is self-referential: it never fires for another card -------


def test_the_trigger_does_not_fire_when_a_different_creature_enters():
    """CR 702.124j's condition is "when **this permanent** enters" - not "a
    creature enters" - so an unrelated creature entering while Evie Frye is
    already on the battlefield asks no search question and moves nothing.
    """
    scenario = _board(
        alice_hand=["Grizzly Bears"],
        alice_battlefield=["Evie Frye", "Forest", "Forest"],
        alice_library=["Jacob Frye"],
    ).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    assert scenario.pending_triggers == []  # staged, not entered - no trigger queued yet

    sources = scenario.untapped_sources("Forest", "Forest")
    scenario.cast_and_resolve("Grizzly Bears", *sources)

    assert scenario.pending_triggers == []
    assert scenario.stack_names() == []
    assert scenario.game.reveals == []
    assert [state.name for state in scenario.player("alice").library] == ["Jacob Frye"]
    assert scenario.player("alice").hand == []


# -- the deck-construction half stays inert ----------------------------------


def test_the_deck_construction_half_is_still_inert():
    """CR 702.124a's own half - designating Evie Frye and Jacob Frye as a
    two-commander Commander pair - has nothing for this engine to execute:
    it targets Modern, Pioneer, and Standard only (`CLAUDE.md`), none of
    which is Commander. Nothing on `Game`/`Player` models a command zone or a
    commander designation at all, so there is no state to assert *against*;
    this test instead pins down the only place that claim is made -
    `machines/keywords.executes` - and confirms the *other* partner ability,
    plain "partner" (CR 702.124h, no "with"), is still the inert one:
    `scripts/sweep_pool.py`'s `NEEDS_NO_CODE` set, not `machines/keywords.
    executes`, which is exactly the CR 702.124f distinction ("Different
    partner abilities are distinct from one another and cannot be
    combined") this task was told to keep straight.
    """
    from magic_cards_model.machines import keywords

    assert keywords.executes("Partner with") is True
    assert keywords.executes("partner with") is True
    assert keywords.executes("Partner") is False
    assert keywords.executes("Choose a Background") is False
