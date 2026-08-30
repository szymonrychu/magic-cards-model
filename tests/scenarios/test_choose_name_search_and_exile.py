"""Choose a card name, then search a graveyard, a hand, and a library for
cards with that name and exile them all - `_search_and_exile_matching_name`
in `machines/effects.py`, built on `Game.search_library`'s `zone` parameter
(P7's own zone widening) and a `machines/targeting.py` shape for "target card
in a graveyard other than a basic land card".

Two cards, each covering one half of the shape:

- **The Stone Brain**: "Choose a card name. Search target opponent's
  graveyard, hand, and library for up to four cards with that name and exile
  them. That player shuffles, then draws a card for each card exiled from
  their hand this way." A real `DecisionKind.CHOOSE_A_QUALITY` "choose a card
  name" question (the same kind CR 614.12a's "as this enters, choose ..."
  already asks through, reused rather than a new kind), a targeted player
  (CR 115.1), and a capped search.
- **Surgical Extraction**: "Choose target card in a graveyard other than a
  basic land card. Search its owner's graveyard, hand, and library for any
  number of cards with the same name as that card and exile them. Then that
  player shuffles." The name comes off the targeted card itself, so no
  `CHOOSE_A_QUALITY` question is asked at all, and the search is uncapped.

Every CR number below was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 701.23a** - "To search for a card in a zone, look at all cards in
  that zone (even if it's a hidden zone) and find a card that matches the
  given description" - `search_library`'s `zone` parameter, run once per
  zone in the order printed (graveyard, hand, library).
- **CR 701.24b** - a library search that moves found cards elsewhere also
  shuffles that library; **CR 701.24e** - that shuffle happens even off a
  library with nothing found in it. Neither a hand nor a graveyard search
  shuffles anything (`Game.search_library`'s own docstring).
- **CR 205.4a** - "the supertypes are basic, legendary, ongoing, snow, and
  world", and only a land is ever printed with "Basic" on its type line - the
  rule that makes excluding `Supertype.BASIC` alone the correct reading of
  "other than a basic land card" (`machines/targeting.py`'s `_read_other_
  than_exclusion`), with no separate `Type.LAND` exclusion needed or wanted
  (that would also refuse a perfectly legal nonbasic dual).
- **CR 608.2d** - "the player can't choose an option that's illegal or
  impossible" - the reason The Stone Brain's own "up to four" only asks a
  real `CHOOSE_CARDS` question when there are more than four matches to
  choose from; at or under four, there is nothing to decide.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone

from .harness import Scenario

STONE_BRAIN = "The Stone Brain"


def _activate_stone_brain(scenario: Scenario, *, targets):
    stone_brain = scenario.find("The Stone Brain", Zone.BATTLEFIELD, "alice")
    sources = scenario.untapped_sources("Island", "Island")
    return scenario.activate(stone_brain, *sources, targets=targets)


# --------------------------------------------------------------------------
# The Stone Brain
# --------------------------------------------------------------------------


def test_stone_brain_exiles_every_matching_card_across_all_three_zones():
    scenario = (
        Scenario()
        .player("alice", battlefield=["The Stone Brain", "Island", "Island"])
        .player(
            "bob",
            hand=["Lightning Bolt", "Forest"],
            graveyard=["Lightning Bolt"],
            library=["Lightning Bolt", "Mountain", "Swamp"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    in_hand = scenario.find("Lightning Bolt", Zone.HAND, "bob")
    in_graveyard = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "bob")
    in_library = next(c for c in bob.library if c.name == "Lightning Bolt")

    scenario.will_choose("Lightning Bolt", source=STONE_BRAIN)
    _activate_stone_brain(scenario, targets=["bob"])
    scenario.resolve_top()

    assert in_hand.zone is Zone.EXILE
    assert in_graveyard.zone is Zone.EXILE
    assert in_library.zone is Zone.EXILE
    assert scenario.find("The Stone Brain", Zone.EXILE, "alice") is not None


def test_stone_brain_grants_a_draw_for_each_card_exiled_from_hand():
    scenario = (
        Scenario()
        .player("alice", battlefield=["The Stone Brain", "Island", "Island"])
        .player(
            "bob",
            hand=["Lightning Bolt"],
            library=["Forest", "Mountain"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")

    scenario.will_choose("Lightning Bolt", source=STONE_BRAIN)
    _activate_stone_brain(scenario, targets=["bob"])
    scenario.resolve_top()

    assert all(c.name != "Lightning Bolt" for c in bob.hand)
    assert len(bob.hand) == 1, "the exiled Bolt was replaced by the drawn card"
    assert len(bob.library) == 1, "one card drawn as the replacement for the exiled hand card"


def test_stone_brains_library_shuffles_even_when_nothing_matches_there():
    """CR 701.24e: the shuffle happens whether or not the search in that
    zone actually found anything."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["The Stone Brain", "Island", "Island"])
        .player("bob", hand=["Lightning Bolt"], library=["Forest", "Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.will_choose("Lightning Bolt", source=STONE_BRAIN)
    _activate_stone_brain(scenario, targets=["bob"])
    scenario.resolve_top()

    assert scenario.game.shuffles_performed == 1


def test_choosing_a_name_nobody_has_finds_nothing_but_still_shuffles():
    scenario = (
        Scenario()
        .player("alice", battlefield=["The Stone Brain", "Island", "Island"])
        .player("bob", hand=["Forest"], library=["Mountain", "Swamp"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")

    scenario.will_choose("Lightning Bolt", source=STONE_BRAIN)
    _activate_stone_brain(scenario, targets=["bob"])
    scenario.resolve_top()

    assert [c.name for c in bob.hand] == ["Forest"]
    assert len(bob.library) == 2
    assert scenario.game.shuffles_performed == 1


def test_more_than_four_matches_asks_which_four_to_exile():
    """CR 608.2d: only asked when the choice is real - five matches for a
    cap of four."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["The Stone Brain", "Island", "Island"])
        .player(
            "bob",
            hand=["Lightning Bolt", "Lightning Bolt"],
            graveyard=["Lightning Bolt"],
            library=["Lightning Bolt", "Lightning Bolt", "Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    all_bolts = (
        [c for c in bob.hand if c.name == "Lightning Bolt"]
        + [c for c in bob.graveyard if c.name == "Lightning Bolt"]
        + [c for c in bob.library if c.name == "Lightning Bolt"]
    )
    assert len(all_bolts) == 5
    chosen_four = all_bolts[:4]

    scenario.will_choose("Lightning Bolt", source=STONE_BRAIN)
    scenario.will_discard(*chosen_four, username="alice")
    _activate_stone_brain(scenario, targets=["bob"])
    scenario.resolve_top()

    exiled = [c for c in chosen_four if c.zone is Zone.EXILE]
    left_behind = all_bolts[4]
    assert len(exiled) == 4
    assert left_behind.zone is not Zone.EXILE

    choose_cards = [
        d
        for d in scenario.questions_asked()
        if d.kind is DecisionKind.CHOOSE_CARDS and d.player == "alice"
    ]
    assert choose_cards, "a real choice was offered for the excess match"


def test_at_or_under_four_matches_asks_no_choice_at_all():
    """The mirror of the test above: three matches for a cap of four is no
    real choice, so no `CHOOSE_CARDS` question is put at all."""
    scenario = (
        Scenario()
        .player("alice", battlefield=["The Stone Brain", "Island", "Island"])
        .player(
            "bob",
            hand=["Lightning Bolt"],
            graveyard=["Lightning Bolt"],
            library=["Lightning Bolt"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.will_choose("Lightning Bolt", source=STONE_BRAIN)
    _activate_stone_brain(scenario, targets=["bob"])
    scenario.resolve_top()

    assert not any(
        d.kind is DecisionKind.CHOOSE_CARDS and d.player == "alice"
        for d in scenario.questions_asked()
    )


# --------------------------------------------------------------------------
# Surgical Extraction
# --------------------------------------------------------------------------


def test_surgical_extraction_exiles_every_copy_across_all_three_zones():
    scenario = (
        Scenario()
        .player("alice", hand=["Surgical Extraction"])
        .player(
            "bob",
            hand=["Lightning Bolt"],
            graveyard=["Lightning Bolt"],
            library=["Lightning Bolt", "Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    targeted = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "bob")
    in_hand = scenario.find("Lightning Bolt", Zone.HAND, "bob")
    in_library = next(c for c in bob.library if c.name == "Lightning Bolt")

    scenario.cast_and_resolve("Surgical Extraction", targets=[targeted])

    assert targeted.zone is Zone.EXILE
    assert in_hand.zone is Zone.EXILE
    assert in_library.zone is Zone.EXILE
    assert scenario.game.shuffles_performed == 1


def test_surgical_extraction_uncapped_exiles_every_copy_with_no_choice():
    """ "Any number" (unlike The Stone Brain's "up to four") never asks a
    `CHOOSE_CARDS` question, however many copies there are."""
    scenario = (
        Scenario()
        .player("alice", hand=["Surgical Extraction"])
        .player(
            "bob",
            hand=["Lightning Bolt", "Lightning Bolt"],
            graveyard=["Lightning Bolt"],
            library=["Lightning Bolt", "Lightning Bolt", "Lightning Bolt"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    targeted = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "bob")

    scenario.cast_and_resolve("Surgical Extraction", targets=[targeted])

    assert bob.hand == []
    assert bob.graveyard == []
    assert all(c.name != "Lightning Bolt" for c in bob.library)
    assert not any(d.kind is DecisionKind.CHOOSE_CARDS for d in scenario.questions_asked())


def test_a_basic_land_in_a_graveyard_is_an_illegal_target():
    """CR 205.4a: "other than a basic land card" excludes exactly a basic
    land, read off `machines/targeting.py`'s own `excluded_supertypes`."""
    scenario = (
        Scenario()
        .player("alice", hand=["Surgical Extraction"])
        .player("bob", graveyard=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.find("Forest", Zone.GRAVEYARD, "bob")

    with pytest.raises(ValueError, match="basic"):
        scenario.cast("Surgical Extraction", username="alice", targets=[forest])


def test_a_nonbasic_land_in_a_graveyard_is_still_a_legal_target():
    """The exclusion is exactly "basic", not "land" - a nonbasic land (a dual,
    say) is a perfectly legal target, and every other copy of it (however
    few) is exiled the same way any other named card's copies would be."""
    scenario = (
        Scenario()
        .player("alice", hand=["Surgical Extraction"])
        .player("bob", graveyard=["Boseiju, Who Endures"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    targeted = scenario.find("Boseiju, Who Endures", Zone.GRAVEYARD, "bob")

    scenario.cast_and_resolve("Surgical Extraction", targets=[targeted])

    assert targeted.zone is Zone.EXILE
    assert bob.graveyard == []


def test_targeting_a_card_in_the_casters_own_graveyard_searches_their_own_zones():
    """Surgical Extraction names no "opponent" the way The Stone Brain does -
    the caster's own graveyard is exactly as legal a target as an
    opponent's, and the search then runs against the caster's own zones."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Surgical Extraction", "Lightning Bolt"],
            graveyard=["Lightning Bolt"],
            library=["Lightning Bolt"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    targeted = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    in_hand = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    in_library = next(c for c in alice.library if c.name == "Lightning Bolt")

    scenario.cast_and_resolve("Surgical Extraction", targets=[targeted])

    assert targeted.zone is Zone.EXILE
    assert in_hand.zone is Zone.EXILE
    assert in_library.zone is Zone.EXILE


def test_no_other_copies_still_exiles_the_targeted_card_alone():
    scenario = (
        Scenario()
        .player("alice", hand=["Surgical Extraction"])
        .player("bob", graveyard=["Lightning Bolt"], library=["Forest", "Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    targeted = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "bob")

    scenario.cast_and_resolve("Surgical Extraction", targets=[targeted])

    assert targeted.zone is Zone.EXILE
    assert len(bob.library) == 2
    assert scenario.game.shuffles_performed == 1
