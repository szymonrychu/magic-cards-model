"""Activated abilities that function off the battlefield (CR 113.6j, CR 113.6m).

CR 113.6: "Abilities of all other objects usually function only while that
object is on the battlefield." Cycling (CR 702.29a) and equip (CR 702.6a) are
the two exceptions this engine already had an execution path for, through
`machines/keywords.KeywordActivation` - but both are CR 702 keywords whose
ability is the *rule's* own fixed text, the same on every card that prints it.

Channel, and the plain unkeyworded abilities on World Breaker and Waker of
Waves, are a different shape: `[Cost]: [Effect.]`, printed like any battlefield
activated ability, whose effect is arbitrary card text. What makes each one
functionally leave the battlefield is read off its own words, not a keyword:

- CR 113.6j: "An object's activated ability that has a cost that can't be paid
  while the object is on the battlefield functions from any zone in which its
  cost can be paid." Discarding a card (CR 701.9a) only ever moves it from a
  hand, so an ability whose cost discards *itself* - Boseiju and Otawara's
  Channel, Waker of Waves' plain ability - can never have that cost paid on
  the battlefield, and so functions only in a hand.
- CR 113.6m: "An ability whose cost or effect specifies that it moves the
  object it's on out of a particular zone functions only in that zone." World
  Breaker's "Return this card from your graveyard to your hand" names its own
  graveyard as where it starts, so it functions only there.

`machines/abilities.py` reads this off the cost and effect text alone (no
table row for any of these three cards), and `machines/keywords.
off_battlefield_activation` is the general form of `KeywordActivation` this
wave adds to reach it - the same object cycling and equip already use for
their own zone check (CR 602.5) and payment (CR 602.2), just built from a
card's own printed ability instead of a keyword's fixed one.

What each ability actually *does* once it resolves is `machines/effects.py`'s
business, and this wave does not touch that file - see the Channel/World
Breaker/Waker rows in `docs/engine-coverage.md` for what is and isn't read
there. This file is about the activation itself: the zone check, the cost, and
the ability landing on the stack independently of its source (CR 113.7a).
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.keywords import off_battlefield_activation
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario, mana_from


def pay_with(*sources):
    def hook(payment):
        for source in sources:
            payment.tap_for_mana(source, mana_from(source))

    return hook


# --------------------------------------------------------------------------
# Channel (Boseiju, Who Endures)
# --------------------------------------------------------------------------


def test_channel_activates_by_discarding_the_card_itself():
    """The happy path: pay {1}{G}, discard Boseiju, and its Channel ability
    reaches the stack (CR 602.2)."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Boseiju, Who Endures"], battlefield=["Forest", "Forest"])
        .player("bob", battlefield=["Sol Ring"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    boseiju = scenario.find("Boseiju, Who Endures", Zone.HAND, "alice")
    sol_ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")
    forests = scenario.untapped_sources("Forest", "Forest")

    activation = off_battlefield_activation(scenario.game, boseiju, "alice", targets=[sol_ring])
    assert activation.zone is Zone.HAND
    assert activation.rule == "CR 113.6j"

    payment = activation.begin_paying()
    pay_with(*forests)(payment)
    payment.pay()
    on_stack = activation.activate()

    assert on_stack in scenario.game.stack
    assert boseiju.zone is Zone.GRAVEYARD


def test_the_ability_resolves_after_its_source_has_left_the_hand():
    """CR 113.7a: "Once activated ..., an ability exists on the stack
    independently of its source." The discard *is* the cost, so Boseiju is
    already in the graveyard by the time the ability is even on the stack,
    long before it resolves - and resolving it must not choke on that.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Boseiju, Who Endures"], battlefield=["Forest", "Forest"])
        .player("bob", battlefield=["Sol Ring"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    boseiju = scenario.find("Boseiju, Who Endures", Zone.HAND, "alice")
    sol_ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")
    forests = scenario.untapped_sources("Forest", "Forest")

    activation = off_battlefield_activation(scenario.game, boseiju, "alice", targets=[sol_ring])
    payment = activation.begin_paying()
    pay_with(*forests)(payment)
    payment.pay()

    assert boseiju.zone is Zone.GRAVEYARD, "the discard cost already moved it, before activate()"
    activation.activate()
    assert boseiju.zone is Zone.GRAVEYARD, "still there once the ability is on the stack"

    activation.resolve()  # must not raise for lack of a source in hand
    assert scenario.game.stack_is_empty  # CR 608.2n: the ability ceased to exist


def test_channel_is_refused_from_the_battlefield():
    """Boseiju as a land in play has no Channel ability available: CR 602.5
    refuses activating an ability from a zone it does not function in, and
    Channel's cost (discarding itself) can never be paid on the battlefield
    (CR 113.6j) - so a Boseiju already on the battlefield offers none."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["Boseiju, Who Endures"])
        .player("bob", battlefield=["Sol Ring"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    boseiju = scenario.find("Boseiju, Who Endures", Zone.BATTLEFIELD, "alice")
    sol_ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")
    activation = off_battlefield_activation(scenario.game, boseiju, "alice", targets=[sol_ring])
    with pytest.raises(ValueError, match="functions in the hand"):
        activation.begin_paying()


def test_channel_is_refused_from_the_graveyard():
    """A discarded or milled Boseiju is not in a hand either, so Channel is
    just as unavailable there as on the battlefield (CR 113.6j, CR 602.5)."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", graveyard=["Boseiju, Who Endures"], battlefield=["Forest", "Forest"])
        .player("bob", battlefield=["Sol Ring"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    boseiju = scenario.find("Boseiju, Who Endures", Zone.GRAVEYARD, "alice")
    sol_ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")
    activation = off_battlefield_activation(scenario.game, boseiju, "alice", targets=[sol_ring])
    with pytest.raises(ValueError, match="functions in the hand"):
        activation.begin_paying()


def test_channel_does_not_consume_the_land_drop():
    """Boseiju is a legendary land: activating Channel from hand is paying an
    activated ability's cost (CR 602.2), never CR 305.1's "play a land"
    special action, so it must not touch the one-land-per-turn allowance
    (CR 305.2a) - a second land is still playable afterwards."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Boseiju, Who Endures", "Forest"],
            battlefield=["Forest", "Forest"],
        )
        .player("bob", battlefield=["Sol Ring"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    boseiju = scenario.find("Boseiju, Who Endures", Zone.HAND, "alice")
    sol_ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")
    forests = scenario.untapped_sources("Forest", "Forest")
    assert scenario.game.can_play_land("alice")

    activation = off_battlefield_activation(scenario.game, boseiju, "alice", targets=[sol_ring])
    payment = activation.begin_paying()
    pay_with(*forests)(payment)
    payment.pay()
    activation.activate()
    # CR 305.1 also asks for an empty stack, which the activation itself now
    # occupies - a *different* reason `can_play_land` says no right now, so
    # the allowance itself (CR 305.2a) is checked directly rather than through
    # it, and only once the stack is clear again does the land drop's own
    # answer become visible.
    assert scenario.game.lands_played.get("alice", 0) == 0, "the land drop was not spent"
    activation.resolve()

    assert scenario.game.can_play_land("alice"), "the land drop is still there"
    played = scenario.play_land("Forest", "alice")
    assert played.zone is Zone.BATTLEFIELD
    assert not scenario.game.can_play_land("alice"), "and this is the one that used it"


def test_a_boseiju_still_in_hand_stays_a_legal_land_drop_after_a_cancelled_channel():
    """Cancelling a Channel activation before its cost is paid (CR 733.1's
    rewind) must leave Boseiju exactly as playable a land as if Channel had
    never been reached for - the discard has not happened yet, so nothing
    about the card itself has changed."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Boseiju, Who Endures"], battlefield=["Forest"])
        .player("bob", battlefield=["Sol Ring"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    boseiju = scenario.find("Boseiju, Who Endures", Zone.HAND, "alice")
    sol_ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")
    activation = off_battlefield_activation(scenario.game, boseiju, "alice", targets=[sol_ring])
    activation.begin_paying()  # one Forest is not enough for {1}{G}; never finish paying
    activation.cancel()

    assert boseiju.zone is Zone.HAND
    assert scenario.game.can_play_land("alice")
    played = scenario.play_land("Boseiju, Who Endures", "alice")
    assert played.zone is Zone.BATTLEFIELD


# --------------------------------------------------------------------------
# World Breaker's graveyard-only ability
# --------------------------------------------------------------------------


def test_world_breaker_activates_from_the_graveyard_independently_of_a_battlefield_copy():
    """A second World Breaker sitting on the battlefield must not interfere:
    `KeywordActivation.why_not` checks the specific `CardState` activating,
    not "a permanent named World Breaker" (CR 113.7a treats every ability by
    its own source)."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            graveyard=["World Breaker"],
            battlefield=["World Breaker", "Wastes", "Mountain", "Mountain", "Forest"],
        )
        .player("bob", battlefield=["Sol Ring"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    gy_breaker = scenario.find("World Breaker", Zone.GRAVEYARD, "alice")
    bf_breaker = scenario.find("World Breaker", Zone.BATTLEFIELD, "alice")
    (forest,) = scenario.untapped_sources("Forest")
    mana_sources = scenario.untapped_sources("Wastes", "Mountain", "Mountain")

    activation = off_battlefield_activation(
        scenario.game, gy_breaker, "alice", sacrificing=[forest]
    )
    assert activation.zone is Zone.GRAVEYARD
    assert activation.rule == "CR 113.6m"

    payment = activation.begin_paying()
    pay_with(*mana_sources)(payment)
    payment.pay()
    on_stack = activation.activate()

    assert on_stack in scenario.game.stack
    assert forest.zone is Zone.GRAVEYARD  # sacrificed to pay the cost
    assert bf_breaker.zone is Zone.BATTLEFIELD, "the other copy is untouched"


def test_world_breaker_is_refused_from_the_battlefield():
    """The battlefield copy's own ability functions only in a graveyard
    (CR 113.6m): its own "Return this card from your graveyard" effect names
    the zone it starts in, and the battlefield is not that zone."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", battlefield=["World Breaker", "Forest"])
        .player("bob", battlefield=["Sol Ring"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    bf_breaker = scenario.find("World Breaker", Zone.BATTLEFIELD, "alice")
    (forest,) = scenario.untapped_sources("Forest")
    activation = off_battlefield_activation(
        scenario.game, bf_breaker, "alice", sacrificing=[forest]
    )
    with pytest.raises(ValueError, match="functions in the graveyard"):
        activation.begin_paying()


@pytest.mark.xfail(
    reason=(
        "World Breaker's own effect is 'Return this card from your graveyard to your hand', "
        "a self-reference - every targeted-return clause machines/effects.py reads (Eternal "
        "Witness's shape) names 'target', not 'this card', so the activation resolves without "
        "moving the card. See the World Breaker row in docs/engine-coverage.md; fixing the "
        "clause reader is machines/effects.py's territory, not this wave's."
    )
)
def test_world_breaker_returns_itself_to_hand_once_the_ability_resolves():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            graveyard=["World Breaker"],
            battlefield=["Wastes", "Mountain", "Mountain", "Forest"],
        )
        .player("bob", battlefield=["Sol Ring"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    gy_breaker = scenario.find("World Breaker", Zone.GRAVEYARD, "alice")
    (forest,) = scenario.untapped_sources("Forest")
    mana_sources = scenario.untapped_sources("Wastes", "Mountain", "Mountain")

    activation = off_battlefield_activation(
        scenario.game, gy_breaker, "alice", sacrificing=[forest]
    )
    payment = activation.begin_paying()
    pay_with(*mana_sources)(payment)
    payment.pay()
    activation.activate()
    activation.resolve()

    assert gy_breaker.zone is Zone.HAND


# --------------------------------------------------------------------------
# Otawara's Channel: the paragraph-atomic rule in practice
# --------------------------------------------------------------------------


def test_otawara_channel_activates_and_fails_closed_as_a_whole_on_resolution():
    """Otawara's Channel prints two sentences: the bounce, and 'This ability
    costs {1} less to activate for each legendary creature you control.' The
    second is not a target-following clause any parser in machines/effects.py
    reads, and this project's paragraph-atomic rule says a multi-clause
    ability with one unreadable clause fails closed *entirely* rather than
    running the readable half. Activating still works end to end (that is
    this wave's job); the target surviving untouched is machines/effects.py's
    existing, correct refusal to run half an instruction (CR 608.2c has no
    notion of a partial resolution) - not a bug this wave introduces or should
    paper over.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Otawara, Soaring City"],
            battlefield=["Island", "Island", "Island", "Island"],
        )
        .player("bob", battlefield=["Sol Ring"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    otawara = scenario.find("Otawara, Soaring City", Zone.HAND, "alice")
    sol_ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")
    islands = scenario.untapped_sources("Island", "Island", "Island", "Island")

    activation = off_battlefield_activation(scenario.game, otawara, "alice", targets=[sol_ring])
    assert activation.zone is Zone.HAND

    payment = activation.begin_paying()
    pay_with(*islands)(payment)
    payment.pay()
    on_stack = activation.activate()
    assert on_stack in scenario.game.stack

    activation.resolve()
    assert sol_ring.zone is Zone.BATTLEFIELD, "unread clause -> the whole ability fails closed"
    assert otawara.zone is Zone.GRAVEYARD, "the discard cost was still paid, regardless"


def test_otawara_channel_refuses_a_target_its_own_text_does_not_allow():
    """CR 601.2c's target legality check runs the same way for an
    off-battlefield activation as for any other (`Game.activate_ability`'s own
    `profile_for_text` check) - Otawara's Channel names artifact, creature,
    enchantment, or planeswalker, not a land."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Otawara, Soaring City"], battlefield=["Island", "Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    otawara = scenario.find("Otawara, Soaring City", Zone.HAND, "alice")
    forest = scenario.find("Forest", Zone.BATTLEFIELD, "alice")
    with pytest.raises(ValueError):
        off_battlefield_activation(scenario.game, otawara, "alice", targets=[forest])


# --------------------------------------------------------------------------
# Waker of Waves: activation works, the effect does not (deferred)
# --------------------------------------------------------------------------


def test_waker_of_waves_activates_from_hand_by_discarding_itself():
    """The zone read is generic (CR 113.6j: a cost that discards the object
    itself), so Waker of Waves activates the same way Channel does even
    though it prints no ability word at all."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Waker of Waves"], battlefield=["Island", "Island"])
        .player("bob", battlefield=["Sol Ring"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    waker = scenario.find("Waker of Waves", Zone.HAND, "alice")
    islands = scenario.untapped_sources("Island", "Island")

    activation = off_battlefield_activation(scenario.game, waker, "alice")
    assert activation.zone is Zone.HAND
    assert activation.rule == "CR 113.6j"

    payment = activation.begin_paying()
    pay_with(*islands)(payment)
    payment.pay()
    on_stack = activation.activate()

    assert on_stack in scenario.game.stack
    assert waker.zone is Zone.GRAVEYARD


@pytest.mark.xfail(
    reason=(
        "Waker of Waves' effect - look at the top two cards, put one into hand and the other "
        "into the graveyard - needs a look-at-N-cards-and-split-to-different-destinations "
        "primitive that does not exist yet (a different shape from scry/surveil's keep-on-top-"
        "or-move-to-one-pile choice). Per the wave brief, do not build a second such primitive; "
        "leave this to whichever wave lands the first one. See docs/engine-coverage.md."
    )
)
def test_waker_of_waves_splits_the_top_two_cards_between_hand_and_graveyard():
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Waker of Waves"],
            library=["Lightning Bolt", "Forest"],
            battlefield=["Island", "Island"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    waker = scenario.find("Waker of Waves", Zone.HAND, "alice")
    islands = scenario.untapped_sources("Island", "Island")

    activation = off_battlefield_activation(scenario.game, waker, "alice")
    payment = activation.begin_paying()
    pay_with(*islands)(payment)
    payment.pay()
    activation.activate()
    activation.resolve()

    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")
    forest = scenario.find("Forest", Zone.GRAVEYARD, "alice")
    assert bolt.zone is Zone.HAND
    assert forest.zone is Zone.GRAVEYARD
