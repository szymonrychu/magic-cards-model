"""Scenario: "Choose up to N target cards in graveyards. The owners of those
cards shuffle them into their libraries." (T-136 b1).

The singular wording ("Its owner shuffles it into their library", Deglamer,
Living Library) had a reader; the plural wording, whose "those cards" are the
targets the first sentence chose, did not. `merges._merge_choose_targets_then_
owners_shuffle_them_clauses` reads the pair so a rider sentence after it still
reads by itself.

- Those Old Scientists (trk) chapter III: "Choose up to two target cards in
  graveyards. The owners of those cards shuffle them into their libraries." -
  nothing follows, and it is a Saga chapter ability.
- Turn the Earth (mid, Modern legal) is the differently worded proof: an
  instant, up to *three* targets, a trailing "You gain 2 life.", and flashback.

Both choose among *every* graveyard (the target is not "your"), so the cards
of two owners move at once and each owner, not the controller, shuffles.

Every CR number was looked up with `mise run rules:find`:

- **CR 108.3** - the owner is the player who started the game with the card.
- **CR 115.6** - "up to" allows zero targets.
- **CR 608.2b** - a target that left its zone is illegal and left alone.
- **CR 701.24a** - to shuffle a library is to randomize it.
- **CR 714.2b** - a chapter ability triggers when its lore counter lands.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone

from .harness import PlayedScenario, Scenario


def _settle(scenario: PlayedScenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()


def _saga_at_chapter_three(alice_graveyard: list[str], bob_graveyard: list[str]) -> PlayedScenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Those Old Scientists"],
            graveyard=alice_graveyard,
            library=["Plains", "Plains"],
        )
        .player("bob", graveyard=bob_graveyard, library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    saga = scenario.find("Those Old Scientists", Zone.BATTLEFIELD, "alice")
    scenario.game.add_counters(saga, "lore", 2 - saga.counter_count("lore"))
    scenario.game.pending_triggers.clear()
    return scenario


def _chapter_three(scenario: PlayedScenario) -> None:
    scenario.game.saga_lore_step()
    _settle(scenario)


# ---------------------------------------------------------------------------
# Those Old Scientists, chapter III
# ---------------------------------------------------------------------------


def test_both_targets_go_to_their_owners_libraries_and_each_owner_shuffles():
    scenario = _saga_at_chapter_three(["Lightning Bolt"], ["Shock"])
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    shock = scenario.find("Shock", Zone.GRAVEYARD, "bob")
    scenario.will_choose_targets(bolt, shock, username="alice")
    before = scenario.game.shuffles_performed

    _chapter_three(scenario)

    assert bolt.zone is Zone.LIBRARY and bolt in scenario.player("alice").library
    assert shock.zone is Zone.LIBRARY and shock in scenario.player("bob").library
    assert scenario.game.shuffles_performed == before + 2


def test_two_cards_of_one_owner_shuffle_that_library_once():
    scenario = _saga_at_chapter_three(["Lightning Bolt", "Island"], [])
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    island = scenario.find("Island", Zone.GRAVEYARD, "alice")
    scenario.will_choose_targets(bolt, island, username="alice")
    before = scenario.game.shuffles_performed

    _chapter_three(scenario)

    assert len(scenario.player("alice").library) == 4
    assert scenario.game.shuffles_performed == before + 1


def test_one_target_of_two_is_enough():
    scenario = _saga_at_chapter_three([], ["Shock"])
    shock = scenario.find("Shock", Zone.GRAVEYARD, "bob")
    scenario.will_choose_targets(shock, username="alice")

    _chapter_three(scenario)

    assert shock.zone is Zone.LIBRARY
    assert len(scenario.player("alice").library) == 2


def test_zero_targets_shuffles_nobody():
    """CR 115.6: "up to two" allows none. The shuffling is the owners' act and
    no card was chosen, so no library is shuffled, the controller's included."""
    scenario = _saga_at_chapter_three(["Lightning Bolt"], ["Shock"])
    scenario.will_choose_targets(username="alice")
    before = scenario.game.shuffles_performed

    _chapter_three(scenario)

    assert scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice").zone is Zone.GRAVEYARD
    assert scenario.find("Shock", Zone.GRAVEYARD, "bob").zone is Zone.GRAVEYARD
    assert scenario.game.shuffles_performed == before


def test_a_card_that_is_not_in_a_graveyard_is_not_a_legal_target():
    scenario = _saga_at_chapter_three(["Lightning Bolt"], [])
    island = scenario.find("Island", Zone.LIBRARY, "bob")
    scenario.will_choose_targets(island, username="alice")
    with pytest.raises(ValueError):
        _chapter_three(scenario)


def test_the_saga_leaves_only_after_chapter_three_resolved():
    """CR 714.4 sacrifices the Saga after the chapter left the stack, so it is
    not among the graveyard cards the chapter could shuffle."""
    scenario = _saga_at_chapter_three(["Lightning Bolt"], [])
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    scenario.will_choose_targets(bolt, username="alice")

    _chapter_three(scenario)

    assert scenario.find("Those Old Scientists", Zone.GRAVEYARD, "alice").zone is Zone.GRAVEYARD


# ---------------------------------------------------------------------------
# Turn the Earth - the same pair on an instant, with a rider
# ---------------------------------------------------------------------------


def _turn_the_earth(
    alice_graveyard: list[str], bob_graveyard: list[str], *, life: int = 20
) -> PlayedScenario:
    scenario = (
        Scenario()
        .player(
            "alice",
            life=life,
            hand=["Turn the Earth"],
            battlefield=["Forest"],
            graveyard=alice_graveyard,
            library=["Plains"],
        )
        .player("bob", graveyard=bob_graveyard, library=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def test_turn_the_earth_moves_three_cards_of_two_owners_and_gains_two_life():
    scenario = _turn_the_earth(["Lightning Bolt", "Island"], ["Shock"])
    cards = [
        scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice"),
        scenario.find("Island", Zone.GRAVEYARD, "alice"),
        scenario.find("Shock", Zone.GRAVEYARD, "bob"),
    ]
    (forest,) = scenario.untapped_sources("Forest")
    before = scenario.game.shuffles_performed

    scenario.cast_and_resolve("Turn the Earth", forest, targets=cards)

    assert [card.zone for card in cards] == [Zone.LIBRARY] * 3
    assert len(scenario.player("alice").library) == 3
    assert len(scenario.player("bob").library) == 2
    assert scenario.player("alice").life == 22
    assert scenario.game.shuffles_performed == before + 2


def test_turn_the_earth_with_no_target_still_gains_the_life_and_shuffles_nobody():
    scenario = _turn_the_earth(["Lightning Bolt"], [])
    (forest,) = scenario.untapped_sources("Forest")
    before = scenario.game.shuffles_performed

    scenario.cast_and_resolve("Turn the Earth", forest, targets=[])

    assert scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice").zone is Zone.GRAVEYARD
    assert scenario.player("alice").life == 22
    assert scenario.game.shuffles_performed == before


def test_turn_the_earth_leaves_the_target_that_left_the_graveyard_alone():
    """CR 608.2b: one of two targets is exiled in response; the other is still
    legal, so the spell resolves for it and the rider still happens."""
    scenario = _turn_the_earth(["Lightning Bolt", "Island"], [])
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    island = scenario.find("Island", Zone.GRAVEYARD, "alice")
    (forest,) = scenario.untapped_sources("Forest")
    scenario.cast_onto_stack("Turn the Earth", forest, targets=[bolt, island])
    scenario.game.exile_permanent(island)
    scenario.resolve_top()

    assert bolt.zone is Zone.LIBRARY
    assert island.zone is Zone.EXILE
    assert scenario.player("alice").life == 22


def test_turn_the_earth_fizzles_when_every_target_left():
    """CR 608.2b: with every target illegal the spell does nothing at all, so
    the rider's life is not gained either."""
    scenario = _turn_the_earth(["Lightning Bolt"], [])
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    (forest,) = scenario.untapped_sources("Forest")
    scenario.cast_onto_stack("Turn the Earth", forest, targets=[bolt])
    scenario.game.exile_permanent(bolt)
    scenario.resolve_top()

    assert scenario.player("alice").life == 20
