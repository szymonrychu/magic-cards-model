"""CR 611.3d's rules-modifying grants to a player, over the top of their own
library, from a static ability (task C02-T7):

- **"You may look at the top card of your library any time."** - Daredevil,
  Man Without Fear's own "Radar Sense", Ka-Zar of the Savage Land's, Iron
  Lad, Diverging Destiny's; Augur of Autumn (real Modern/Pioneer-legal
  Scryfall printing, added with `add_card.py`, not in any api deck list)
  proves the second printing. Read by `Game.controls_look_at_top_permission`
  and surfaced through `Game.known_to` - the top card of the granting
  player's own library is live `KnownCard` information for as long as the
  grant holds, computed fresh every call rather than stored as a one-shot
  `Reveal`.
- **"You may play lands from the top of your library."** - Ka-Zar's own
  second static; Courser of Kruphix and Augur of Autumn both print the
  identical sentence (Courser: Modern/Pioneer-legal; Augur: Modern/Pioneer-
  legal). Read by `Game.land_from_top_of_library_permission`, wired into
  `Game.play_land` beside the pre-existing `graveyard_land_permission`.
- **Iron Lad, Diverging Destiny's `{T}: Reveal the top card of your
  library. If it's an artifact card, draw a card.`** - a simpler sibling of
  the pool's existing "look/reveal the top card, if it's a `<quality>`,
  `<put it somewhere>`" readers, with an arbitrary trailing effect (a draw)
  instead of a "put" destination, and no "otherwise" branch at all.
- **Rick Jones, Destined Sidekick - VERIFY ONLY** (C01-T8's own reader):
  "`{3}`, `{T}`: Mill four cards. You may put a Hero or enchantment card
  from among those cards into your hand." `_MILL_THEN_MAY_TAKE_FROM_MILLED_
  RE` already read "from among **them**"; this task widened its alternation
  to also accept "from among **those cards**", the phrasing Rick Jones's own
  reminder text uses, with no other change to the reader or its effect.

Every rule cited here was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 701.31a** - to mill a card is to move it from the top of a library
  to a graveyard (Rick Jones' own {T} ability).

Every rule cited here was looked up with `mise run rules:find` in the
session that wrote this file:

- **CR 611.3d** - "Continuous effects from static abilities may allow a
  player to play a land or cast a permanent spell..." (the land half) - and,
  by the same static-ability-grants-a-rule mechanism, this project already
  reads an informational grant (`plays_lands_from_graveyard_line`'s own
  precedent) the identical way.
- **CR 305.1** - "A player who has priority may play a land card from their
  hand during a main phase of their turn when the stack is empty" - "from
  their hand" is the part a grant like this one opens onto a different zone.
- **CR 701.20a** - revealing a card "does not change its zone or move it
  within its zone" - the reveal in Iron Lad's own `{T}` ability leaves the
  card on top either way.
- **CR 400.1/108.3** - the library is a player's own zone; nothing here
  reaches past the granting player's own library.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

# -- "you may look at the top card of your library any time" ----------------


def test_a_granting_permanent_makes_the_top_card_known_to_its_controller():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Daredevil, Man Without Fear"],
            library=["Forest", "Island"],
        )
        .build()
    )
    top = scenario.find("Forest", Zone.LIBRARY, "alice")
    known = scenario.game.known_to("alice")
    assert any(card.card_id == top.id and card.index_from_top == 0 for card in known)


def test_the_known_card_is_never_shown_to_an_opponent():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Daredevil, Man Without Fear"], library=["Forest"])
        .player("bob")
        .build()
    )
    known = scenario.game.known_to("bob")
    assert known == []


def test_no_granting_permanent_means_nothing_extra_is_known():
    scenario = Scenario().player("alice", library=["Forest"]).build()
    known = scenario.game.known_to("alice")
    assert known == []


def test_the_known_card_tracks_a_draw_live_rather_than_staying_stale():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Ka-Zar of the Savage Land"],
            library=["Forest", "Island"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.find("Forest", Zone.LIBRARY, "alice")
    island = scenario.find("Island", Zone.LIBRARY, "alice")
    known_before = scenario.game.known_to("alice")
    assert any(card.card_id == forest.id for card in known_before)

    scenario.game.draw_cards("alice")

    known_after = scenario.game.known_to("alice")
    assert any(card.card_id == island.id for card in known_after)
    assert not any(card.card_id == forest.id for card in known_after)


def test_augur_of_autumn_second_printing_also_grants_it():
    scenario = (
        Scenario().player("alice", battlefield=["Augur of Autumn"], library=["Forest"]).build()
    )
    top = scenario.find("Forest", Zone.LIBRARY, "alice")
    known = scenario.game.known_to("alice")
    assert any(card.card_id == top.id for card in known)


# -- "you may play lands from the top of your library" ----------------------


def test_a_land_on_top_of_the_library_can_be_played_directly():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Ka-Zar of the Savage Land"], library=["Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.find("Forest", Zone.LIBRARY, "alice")

    scenario.play_land("Forest", from_zone=Zone.LIBRARY)

    assert forest.zone is Zone.BATTLEFIELD
    assert scenario.game.lands_played["alice"] == 1


def test_a_card_not_on_top_cannot_be_played_from_the_library():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Ka-Zar of the Savage Land"],
            library=["Island", "Forest"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    with pytest.raises(ValueError):
        scenario.play_land("Forest", from_zone=Zone.LIBRARY)


def test_without_the_granting_permanent_a_land_on_top_cannot_be_played():
    scenario = Scenario().player("alice", library=["Forest"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    with pytest.raises(ValueError):
        scenario.play_land("Forest", from_zone=Zone.LIBRARY)


def test_courser_of_kruphix_second_printing_also_grants_the_land_play():
    scenario = (
        Scenario().player("alice", battlefield=["Courser of Kruphix"], library=["Forest"]).build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.find("Forest", Zone.LIBRARY, "alice")

    scenario.play_land("Forest", from_zone=Zone.LIBRARY)

    assert forest.zone is Zone.BATTLEFIELD


# -- Iron Lad, Diverging Destiny's {T} ability -------------------------------


def test_iron_lad_draws_a_card_when_the_revealed_top_card_is_an_artifact():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Iron Lad, Diverging Destiny"],
            library=["Cosmic Cube"],
            hand=[],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    top = scenario.find("Cosmic Cube", Zone.LIBRARY, "alice")

    iron_lad = scenario.creature("Iron Lad, Diverging Destiny", "alice")
    scenario.activate(iron_lad)
    scenario.resolve_top()

    alice = scenario.player("alice")
    assert top.zone is Zone.HAND  # drawn
    assert [state.name for state in alice.hand] == ["Cosmic Cube"]


def test_iron_lad_draws_nothing_when_the_revealed_top_card_is_not_an_artifact():
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Iron Lad, Diverging Destiny"],
            library=["Forest"],
            hand=[],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    forest = scenario.find("Forest", Zone.LIBRARY, "alice")

    iron_lad = scenario.creature("Iron Lad, Diverging Destiny", "alice")
    scenario.activate(iron_lad)
    scenario.resolve_top()

    alice = scenario.player("alice")
    assert forest.zone is Zone.LIBRARY
    assert alice.hand == []


# -- Rick Jones, Destined Sidekick (verify only) -----------------------------


def test_rick_jones_mills_four_and_takes_an_enchantment_from_among_them():
    """VERIFY ONLY (C01-T8's own reader): confirms `_MILL_THEN_MAY_TAKE_FROM_
    MILLED_RE`'s "those cards" widening reads Rick Jones' own reminder-text
    phrasing with no other change to the reader or its effect."""
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Rick Jones, Destined Sidekick", "Forest", "Forest", "Forest"],
            library=["Alpine Moon", "Mountain", "Island", "Swamp"],
            hand=[],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    moon = scenario.find("Alpine Moon", Zone.LIBRARY, "alice")
    mountain = scenario.find("Mountain", Zone.LIBRARY, "alice")
    island = scenario.find("Island", Zone.LIBRARY, "alice")
    swamp = scenario.find("Swamp", Zone.LIBRARY, "alice")

    rick_jones = scenario.creature("Rick Jones, Destined Sidekick", "alice")
    sources = scenario.untapped_sources("Forest", "Forest", "Forest")
    scenario.will_take_the_may(True)
    scenario.will_choose_cards(moon, source="Rick Jones, Destined Sidekick")
    scenario.activate(rick_jones, *sources)
    scenario.resolve_top()

    alice = scenario.player("alice")
    assert moon.zone is Zone.HAND
    assert mountain.zone is Zone.GRAVEYARD
    assert island.zone is Zone.GRAVEYARD
    assert swamp.zone is Zone.GRAVEYARD
    assert [state.name for state in alice.hand] == ["Alpine Moon"]
