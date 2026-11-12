"""Scenario: "Draw a card, then discard a card. If <condition>, you may cast the
discarded card without paying its mana cost." - the card an earlier instruction of
the same ability discarded is the object a later "you may cast" names.

Rules, each read with `mise run rules:find` in the session that wrote this file:

- **CR 701.9a** - to discard a card is to move it from its owner's hand to that
  player's graveyard; the cast then happens from the graveyard.
- **CR 608.2g** - an effect that allows a cast during resolution follows 601.2a-i
  with no priority: the spell goes on top of the stack, the ability keeps
  resolving.
- **CR 118.9** - "You may cast [this object] without paying its mana cost" is an
  alternative cost the controller may decline (CR 118.9b).
- **CR 305.9** - a land is played, never cast, so a discarded land is not a card
  this text can cast.
- **CR 608.2h** - information from a specific object, the ability's own source
  included, is its current information while it is in the zone it was expected
  to be in, and its last known information after it left.

Card: **Malcolm, Alluring Scoundrel** (LCI, Modern-legal). It is the only printing
with this tail, so generality is shown on the head and the condition: the
discard may be a land or a spell, the count may be met by the counter the same
trigger put on, and the counter and source may be changed in response.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario

MALCOLM = "Malcolm, Alluring Scoundrel"
BEARS = "Grizzly Bears"


def _board(*, chorus: int, hand=(BEARS,), library=("Island", "Island")):
    scenario = (
        Scenario()
        .player("alice", hand=list(hand), library=list(library), battlefield=[MALCOLM])
        .player("bob", library=["Island"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    malcolm = scenario.creature(MALCOLM, "alice")
    if chorus:
        malcolm.add_counters("chorus", chorus)
    return scenario, malcolm


def _connect(scenario, malcolm):
    """Malcolm attacks unblocked and deals combat damage; its trigger is on the stack."""
    scenario.attack_with(malcolm, defending="bob")
    scenario.no_blocks()
    scenario.combat_damage()


def test_four_counters_after_this_one_offers_the_discarded_card_for_free():
    scenario, malcolm = _board(chorus=3)
    bears = scenario.find(BEARS, Zone.HAND, "alice")
    scenario.will_discard(bears, username="alice")
    scenario.will_take_the_may(True, source=MALCOLM)

    _connect(scenario, malcolm)
    scenario.resolve_top()  # Malcolm's trigger

    assert malcolm.counter_count("chorus") == 4
    assert bears.zone is Zone.STACK
    assert scenario.stack_names() == [BEARS]
    scenario.resolve_top()
    assert bears.zone is Zone.BATTLEFIELD
    assert scenario.player("alice").mana_pool.total == 0  # nothing was paid


def test_fewer_than_four_counters_only_loots():
    scenario, malcolm = _board(chorus=2)
    bears = scenario.find(BEARS, Zone.HAND, "alice")
    scenario.will_discard(bears, username="alice")
    scenario.will_take_the_may(True, source=MALCOLM)

    _connect(scenario, malcolm)
    scenario.resolve_top()

    assert malcolm.counter_count("chorus") == 3
    assert bears.zone is Zone.GRAVEYARD
    assert scenario.stack_names() == []
    assert [card.name for card in scenario.player("alice").hand] == ["Island"]


def test_the_first_hit_puts_the_first_counter_and_asks_nothing_about_a_cast():
    scenario, malcolm = _board(chorus=0)
    bears = scenario.find(BEARS, Zone.HAND, "alice")
    scenario.will_discard(bears, username="alice")

    _connect(scenario, malcolm)
    scenario.resolve_top()

    assert malcolm.counter_count("chorus") == 1
    assert bears.zone is Zone.GRAVEYARD
    assert not any(question.prompt.startswith("cast ") for question in scenario.questions_asked())


def test_more_than_four_counters_still_offers_the_cast():
    scenario, malcolm = _board(chorus=6)
    bears = scenario.find(BEARS, Zone.HAND, "alice")
    scenario.will_discard(bears, username="alice")
    scenario.will_take_the_may(True, source=MALCOLM)

    _connect(scenario, malcolm)
    scenario.resolve_top()

    assert malcolm.counter_count("chorus") == 7
    assert bears.zone is Zone.STACK


def test_declining_leaves_the_discarded_card_in_the_graveyard():
    scenario, malcolm = _board(chorus=3)
    bears = scenario.find(BEARS, Zone.HAND, "alice")
    scenario.will_discard(bears, username="alice")
    scenario.will_take_the_may(False, source=MALCOLM)

    _connect(scenario, malcolm)
    scenario.resolve_top()

    assert malcolm.counter_count("chorus") == 4
    assert bears.zone is Zone.GRAVEYARD
    assert scenario.stack_names() == []


def test_a_discarded_land_cannot_be_cast():
    scenario, malcolm = _board(chorus=3, hand=("Mountain",))
    mountain = scenario.find("Mountain", Zone.HAND, "alice")
    scenario.will_discard(mountain, username="alice")
    scenario.will_take_the_may(True, source=MALCOLM)

    _connect(scenario, malcolm)
    scenario.resolve_top()

    assert mountain.zone is Zone.GRAVEYARD
    assert scenario.stack_names() == []


def test_only_the_discarded_card_is_castable_not_an_older_graveyard_card():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Mountain"],
            graveyard=[BEARS],
            library=["Island"],
            battlefield=[MALCOLM],
        )
        .player("bob", library=["Island"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    malcolm = scenario.creature(MALCOLM, "alice")
    malcolm.add_counters("chorus", 3)
    older = scenario.find(BEARS, Zone.GRAVEYARD, "alice")
    mountain = scenario.find("Mountain", Zone.HAND, "alice")
    scenario.will_discard(mountain, username="alice")
    scenario.will_take_the_may(True, source=MALCOLM)

    _connect(scenario, malcolm)
    scenario.resolve_top()

    assert older.zone is Zone.GRAVEYARD
    assert scenario.stack_names() == []


def test_a_counter_removed_in_response_keeps_the_count_below_four():
    scenario, malcolm = _board(chorus=3)
    bears = scenario.find(BEARS, Zone.HAND, "alice")
    scenario.will_discard(bears, username="alice")
    scenario.will_take_the_may(True, source=MALCOLM)

    _connect(scenario, malcolm)
    malcolm.remove_counters("chorus", 1)  # in response, with the trigger on the stack
    scenario.resolve_top()

    assert malcolm.counter_count("chorus") == 3
    assert bears.zone is Zone.GRAVEYARD
    assert scenario.stack_names() == []


def test_four_counters_with_one_removed_in_response_is_met_by_the_new_counter():
    scenario, malcolm = _board(chorus=4)
    bears = scenario.find(BEARS, Zone.HAND, "alice")
    scenario.will_discard(bears, username="alice")
    scenario.will_take_the_may(True, source=MALCOLM)

    _connect(scenario, malcolm)
    malcolm.remove_counters("chorus", 1)
    scenario.resolve_top()

    assert malcolm.counter_count("chorus") == 4
    assert bears.zone is Zone.STACK


@pytest.mark.xfail(
    strict=True,
    reason=(
        "CR 608.2h: a source that left reads its last known counters, but the "
        "'there are N counters on <subject>' condition reader "
        "(conditions/objects._there_are_counters_on) reads the live counters of a "
        "source that is no longer on the battlefield"
    ),
)
def test_malcolm_gone_before_resolution_uses_its_last_known_counters():
    """CR 608.2h: no counter is put on a card that left, but the condition
    reads the source's last known information, and the loot still happens."""
    scenario, malcolm = _board(chorus=4)
    bears = scenario.find(BEARS, Zone.HAND, "alice")
    scenario.will_discard(bears, username="alice")
    scenario.will_take_the_may(True, source=MALCOLM)

    _connect(scenario, malcolm)
    scenario.game.return_to_hand(malcolm)  # in response
    scenario.resolve_top()

    assert malcolm.zone is Zone.HAND
    assert malcolm.counter_count("chorus") == 0
    assert bears.zone is Zone.STACK
