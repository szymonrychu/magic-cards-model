"""Scenario: CR 601.2a, the first step of casting.

"To propose the casting of a spell, a player first moves that card (or that
copy of a card) from where it is to the stack. It becomes the topmost object on
the stack." Everything else about casting - modes, targets, the total cost -
happens with the card already there, which is what makes a spell that counts
its controller's graveyard not count itself.

CR numbers, each looked up with `knowledge_search(type="rules")` in the session
that wrote this file and quoted from what it returned:

- **CR 601.2a** - quoted above.
- **CR 112.1** - "A spell is a card on the stack. As the first step of being
  cast, the card becomes a spell and is moved to the top of the stack from the
  zone it was in."
- **CR 405.1** - "When a spell is cast, the physical card is put on the stack."
- **CR 601.6** - a cast that turns out to be illegal is rewound: "the game
  returns to the moment before the casting was proposed", which now includes
  putting the card back where it was.
- **CR 733.1** - the rewind itself, payments included.
- **CR 115.5** - "A spell or ability on the stack is an illegal target for
  itself." Newly load-bearing: with the spell on the stack from announcement,
  nothing else keeps a Counterspell off itself.
- **CR 400.7** - a card that changes zones becomes a new object, which is why
  the rewind restores the identity it had as well as the zone.
- **CR 406.4** - each set of exiled cards is kept separate, which is the pile a
  plotted card has to go back to.
- **CR 601.2f** - the total cost, determined five steps after the move.

Every printing is a real Scryfall fixture from `tests/fixtures/cards/`.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.casting import CastingStep, MarkedExile
from magic_cards_model.models import Zone

from .harness import Scenario


def _board(**hands: list[str]) -> Scenario:
    scenario = Scenario()
    for username, hand in hands.items():
        scenario = scenario.player(username, hand=hand, battlefield=["Mountain"] * 4)
    return scenario


def test_the_card_leaves_the_hand_as_the_cast_is_proposed():
    """CR 112.1: the card becomes a spell and is on the stack, before a single
    mana has been paid."""
    scenario = _board(alice=["Lightning Bolt"], bob=[]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Lightning Bolt", Zone.HAND)

    casting = scenario.cast("Lightning Bolt", targets=["bob"])

    assert bolt.zone is Zone.STACK
    assert scenario.player("alice").hand == []
    assert casting.payment is None, "nothing has been paid yet (CR 601.2f is later)"


def test_the_spell_is_the_topmost_object_on_the_stack():
    """CR 601.2a: "It becomes the topmost object on the stack." - above the
    spell it is answering."""
    scenario = (
        Scenario()
        .player("bob", hand=["Grizzly Bears"], battlefield=["Forest", "Forest"])
        .player("alice", hand=["Lightning Bolt"], battlefield=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest", username="bob")
    scenario.cast_onto_stack("Grizzly Bears", *sources, username="bob")
    scenario.pass_priority("bob")

    scenario.cast("Lightning Bolt", username="alice", targets=["bob"])

    assert scenario.stack_names() == ["Grizzly Bears", "Lightning Bolt"]


def test_cancelling_puts_the_card_back_with_the_identity_it_had():
    """CR 601.6 and CR 733.1: the whole proposal is reversed. CR 400.7 makes a
    card that changed zones a new object, so a rewound announcement has to
    restore the old one - otherwise every effect that recorded *that* object
    (an exile grant, a delayed trigger) would lose it."""
    scenario = _board(alice=["Lightning Bolt"], bob=[]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Lightning Bolt", Zone.HAND)
    stamp = bolt.zone_change_stamp

    casting = scenario.cast("Lightning Bolt", targets=["bob"])
    casting.cancel()

    assert bolt.zone is Zone.HAND
    assert bolt.zone_change_stamp == stamp
    assert scenario.game.stack == []
    assert scenario.player("alice").hand == [bolt]
    assert casting.step is CastingStep.CANCELLED


def test_an_illegal_target_rewinds_the_proposal_by_itself():
    """CR 601.6: a cast that cannot be made legally returns the game to the
    moment before it was proposed - the caller does not have to ask."""
    scenario = (
        Scenario()
        .player("alice", hand=["Swords to Plowshares"], battlefield=["Plains"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    swords = scenario.find("Swords to Plowshares", Zone.HAND)

    with pytest.raises(ValueError, match="cannot target the player"):
        scenario.cast("Swords to Plowshares", targets=["bob"])

    assert swords.zone is Zone.HAND
    assert scenario.game.stack == []


def test_a_spell_cannot_target_itself():
    """CR 115.5, which the move makes necessary: a Counterspell on the stack is
    a spell on the stack, and it is an illegal target for itself."""
    scenario = (
        Scenario()
        .player("bob", hand=["Grizzly Bears"], battlefield=["Forest", "Forest"])
        .player("alice", hand=["Counterspell"], battlefield=["Island", "Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    sources = scenario.untapped_sources("Forest", "Forest", username="bob")
    scenario.cast_onto_stack("Grizzly Bears", *sources, username="bob")
    scenario.pass_priority("bob")

    casting = scenario.cast("Counterspell", username="alice")

    with pytest.raises(ValueError, match="illegal target for itself"):
        casting.choose_targets([casting.spell])


def test_the_spell_is_not_in_the_graveyard_it_counts_at_cost_time():
    """The whole point of the ordering: CR 601.2a runs five steps before
    CR 601.2f, so Emrakul's "for each card type among cards in your graveyard"
    counts what is left after the card it is on has gone.

    Flashing a Lesson back is the DDR#996 version of this; here it is the
    plainer one - the card being cast is in hand, and what changes is that a
    *second* copy in the graveyard is all that is counted.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Faithless Looting"],
            graveyard=["Faithless Looting"],
            battlefield=["Mountain"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.cast("Faithless Looting")

    assert [state.name for state in scenario.player("alice").graveyard] == ["Faithless Looting"]


def test_a_cancelled_cast_from_exile_goes_back_to_its_own_pile():
    """CR 406.4: exile is not one heap. A plotted card whose cast is rewound is
    plotted again, or it could never be cast at all afterwards
    (CR 702.170d)."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Slickshot Show-Off"], battlefield=["Mountain", "Mountain"])
        .player("bob", battlefield=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    show_off = scenario.find("Slickshot Show-Off", Zone.HAND, "alice")
    action = MarkedExile.plot(scenario.game, show_off, "alice")
    scenario.pay_with(action.begin_paying(), *scenario.untapped_sources("Mountain", "Mountain"))
    action.take()
    annotation = show_off.exile_annotation

    for _ in range(60):
        scenario.advance()
        if scenario.turn.active_player == "alice" and scenario.step is Step.PRECOMBAT_MAIN:
            break

    casting = scenario.cast("Slickshot Show-Off", from_zone=Zone.EXILE)
    casting.use_keyword("Plot")
    casting.cancel()

    assert show_off.zone is Zone.EXILE
    assert show_off.exile_annotation == annotation
    assert show_off in scenario.game.exile
