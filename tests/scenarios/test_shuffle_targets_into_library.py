"""Shuffling targeted graveyard cards back: "Shuffle up to three target cards
from your graveyard into your library."

Every CR number below was read whole with `mise run rules:find` in the session
that wrote this file:

- **CR 115.6** - a spell or ability may allow zero targets to be chosen.
- **CR 601.2c** - a variable number of targets is announced before the
  targets themselves; the same target can't be chosen twice for one "target".
- **CR 608.2b** - a target no longer in the zone it was targeted in is
  illegal, and is left alone as the ability resolves.
- **CR 701.24a** - to shuffle a library is to randomize it.
- **CR 714.2b** - a chapter ability triggers when its lore counter lands.

Tamiyo Meets the Story Circle's chapter III is the reported card. Wand of
Vertebrae ("{2}, {T}, Exile this artifact: Shuffle up to five target cards
from your graveyard into your library.") is the proof printing: Pioneer and
Modern legal, in no api deck, a different count on an activated ability.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def resolve_all(scenario) -> None:
    scenario.game.put_triggers_on_stack()
    while scenario.game.stack:
        scenario.resolve_top()


def tamiyo_at_chapter_two(graveyard: list[str], bob_graveyard: list[str] | None = None):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Tamiyo Meets the Story Circle"],
            graveyard=graveyard,
            library=["Plains"],
        )
        .player("bob", graveyard=bob_graveyard or [])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    resolve_all(scenario)  # chapter I
    scenario.game.saga_lore_step()
    resolve_all(scenario)  # chapter II, nothing discarded
    return scenario


def chapter_three(scenario) -> None:
    scenario.game.saga_lore_step()
    resolve_all(scenario)


def test_three_targets_are_shuffled_into_the_library():
    scenario = tamiyo_at_chapter_two(["Lightning Bolt", "Shock", "Island", "Forest"])
    bolt, shock, island = (
        scenario.find(name, Zone.GRAVEYARD, "alice")
        for name in ("Lightning Bolt", "Shock", "Island")
    )
    scenario.will_choose_targets(bolt, shock, island, username="alice")

    chapter_three(scenario)

    alice = scenario.player("alice")
    assert {bolt.zone, shock.zone, island.zone} == {Zone.LIBRARY}
    assert len(alice.library) == 4
    assert [state.name for state in alice.graveyard if state.name == "Forest"] == ["Forest"]


def test_zero_targets_is_legal():
    """CR 115.6: "up to three" allows none."""
    scenario = tamiyo_at_chapter_two(["Lightning Bolt"])
    scenario.will_choose_targets(username="alice")

    chapter_three(scenario)

    assert scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice").zone is Zone.GRAVEYARD
    assert len(scenario.player("alice").library) == 1


def test_fewer_than_three_targets_are_all_shuffled():
    scenario = tamiyo_at_chapter_two(["Lightning Bolt"])
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    scenario.will_choose_targets(bolt, username="alice")

    chapter_three(scenario)

    assert bolt.zone is Zone.LIBRARY
    assert len(scenario.player("alice").library) == 2


def test_the_saga_itself_is_not_its_own_target_once_sacrificed():
    """The Saga goes to the graveyard only after chapter III has left the
    stack (CR 714.4), so it is not among the cards chapter III shuffles."""
    scenario = tamiyo_at_chapter_two(["Lightning Bolt"])
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    scenario.will_choose_targets(bolt, username="alice")

    chapter_three(scenario)

    saga = scenario.find("Tamiyo Meets the Story Circle", Zone.GRAVEYARD, "alice")
    assert saga.zone is Zone.GRAVEYARD


def test_an_opponents_graveyard_card_is_not_a_legal_target():
    scenario = tamiyo_at_chapter_two(["Lightning Bolt"], bob_graveyard=["Shock"])
    shock = scenario.find("Shock", Zone.GRAVEYARD, "bob")
    scenario.will_choose_targets(shock, username="alice")

    with pytest.raises(ValueError):
        chapter_three(scenario)


def test_a_target_that_left_the_graveyard_is_left_alone():
    """CR 608.2b: the target that is gone is illegal; the other is still
    shuffled in."""
    scenario = tamiyo_at_chapter_two(["Lightning Bolt", "Shock"])
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")
    shock = scenario.find("Shock", Zone.GRAVEYARD, "alice")
    scenario.will_choose_targets(bolt, shock, username="alice")
    scenario.game.saga_lore_step()
    scenario.game.put_triggers_on_stack()
    scenario.game.exile_cards([bolt])

    while scenario.game.stack:
        scenario.resolve_top()

    assert bolt.zone is Zone.EXILE
    assert shock.zone is Zone.LIBRARY


# -- proof printing: Wand of Vertebrae ----------------------------------------


def wand_board(graveyard: list[str]):
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Wand of Vertebrae", "Island", "Island"],
            graveyard=graveyard,
            library=["Plains"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    return scenario


def shuffle_with_wand(scenario, targets) -> None:
    wand = scenario.find("Wand of Vertebrae", Zone.BATTLEFIELD, "alice")
    islands = scenario.untapped_sources("Island", "Island", username="alice")
    scenario.activate(wand, *islands, index=1, targets=list(targets))
    scenario.resolve_top()


def test_wand_shuffles_up_to_five_cards():
    names = ["Lightning Bolt", "Shock", "Island", "Forest", "Swamp", "Mountain"]
    scenario = wand_board(names)
    chosen = [scenario.find(name, Zone.GRAVEYARD, "alice") for name in names[:5]]

    shuffle_with_wand(scenario, chosen)

    alice = scenario.player("alice")
    assert all(state.zone is Zone.LIBRARY for state in chosen)
    assert len(alice.library) == 6
    assert scenario.find("Mountain", Zone.GRAVEYARD, "alice").zone is Zone.GRAVEYARD


def test_wand_exiles_itself_as_a_cost():
    scenario = wand_board(["Lightning Bolt"])
    wand = scenario.find("Wand of Vertebrae", Zone.BATTLEFIELD, "alice")
    bolt = scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice")

    shuffle_with_wand(scenario, [bolt])

    assert wand.zone is Zone.EXILE
    assert bolt.zone is Zone.LIBRARY


def test_wand_with_no_targets_shuffles_nothing_in():
    scenario = wand_board(["Lightning Bolt"])

    shuffle_with_wand(scenario, [])

    assert scenario.find("Lightning Bolt", Zone.GRAVEYARD, "alice").zone is Zone.GRAVEYARD
    assert len(scenario.player("alice").library) == 1
