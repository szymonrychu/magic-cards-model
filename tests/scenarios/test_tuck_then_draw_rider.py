""" "`<this>` deals `<n>` damage to target creature. You may put a card from
your hand on the bottom of your library. If you do, draw a card." - CR
118.12's optional-cost shape, with a tuck rather than a discard, sacrifice, or
tap as the thing paid.

Manhole Missile: "Manhole Missile deals 3 damage to target creature. You may
put a card from your hand on the bottom of your library. If you do, draw a
card."

- **CR 118.12** - "If [a player] does..." checks whether the player chose to
  do it, not whether anything downstream happened to work - `_merge_may_
  then_if_you_do_clauses` already reads this generically for any wrapped
  action `parse_clause_effect` understands; the only new piece is teaching
  that function to read "put a card from your hand on the bottom of your
  library" at all.
- **CR 401.2** - the bottom of the library, not shuffled in and not the top.
- **CR 608.2d** - the choice of which card is the player's own, made only
  when the hand actually has one to offer.

Fire Prophecy is the second, non-pool printing that proves the tuck-then-draw
reader is not fitted to Manhole Missile's own wording - it prints the
identical sentence word for word, over a different fixed damage amount and a
different (irrelevant) card name. Verified legal in Modern and Pioneer.

Every CR number here was looked up with `mise run rules:find` in the session
that wrote this file.
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_declining_to_tuck_deals_damage_and_stops_there():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Manhole Missile", "Opt"],
            battlefield=["Mountain", "Mountain"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.will_take_the_may(False, username="alice")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources("Mountain", "Mountain")

    scenario.cast_and_resolve("Manhole Missile", *sources, targets=[bears])

    assert bears.zone is Zone.GRAVEYARD  # 3 damage kills a 2/2
    assert [state.name for state in scenario.player("alice").hand] == ["Opt"]


def test_tucking_a_card_draws_a_replacement():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Manhole Missile", "Opt"],
            battlefield=["Mountain", "Mountain"],
            library=["Lightning Bolt", "Forest"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.will_take_the_may(True, username="alice")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    opt = scenario.find("Opt", Zone.HAND, "alice")
    sources = scenario.untapped_sources("Mountain", "Mountain")

    scenario.will_choose_cards(opt, username="alice", source="Manhole Missile")
    scenario.cast_and_resolve("Manhole Missile", *sources, targets=[bears])

    assert bears.zone is Zone.GRAVEYARD
    # Opt went to the bottom of the library (CR 401.2), and Lightning Bolt -
    # the card that was on top - was drawn in its place.
    assert opt.zone is Zone.LIBRARY
    assert scenario.player("alice").library[-1] is opt
    hand_names = [state.name for state in scenario.player("alice").hand]
    assert hand_names == ["Lightning Bolt"]


def test_an_empty_hand_is_never_asked_the_question():
    scenario = (
        Scenario()
        .player("alice", hand=["Manhole Missile"], battlefield=["Mountain", "Mountain"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    sources = scenario.untapped_sources("Mountain", "Mountain")

    scenario.cast_and_resolve("Manhole Missile", *sources, targets=[bears])

    assert bears.zone is Zone.GRAVEYARD
    assert scenario.player("alice").hand == []


def test_fire_prophecy_proves_the_reader_generalizes_off_a_second_printing():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Fire Prophecy", "Opt"],
            battlefield=["Mountain", "Mountain"],
            library=["Lightning Bolt", "Forest"],
        )
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.will_take_the_may(True, username="alice")
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    opt = scenario.find("Opt", Zone.HAND, "alice")
    sources = scenario.untapped_sources("Mountain", "Mountain")

    scenario.will_choose_cards(opt, username="alice", source="Fire Prophecy")
    scenario.cast_and_resolve("Fire Prophecy", *sources, targets=[bears])

    assert bears.zone is Zone.GRAVEYARD
    assert opt.zone is Zone.LIBRARY
    assert [state.name for state in scenario.player("alice").hand] == ["Lightning Bolt"]
