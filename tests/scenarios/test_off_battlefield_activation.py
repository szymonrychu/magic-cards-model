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

What each ability actually *does* once it resolves needed `machines/effects.py`
after all, in a follow-up pass: Boseiju's and Otawara's Channel abilities each
print a trailing "This ability costs {1} less to activate for each legendary
creature you control." sentence sharing their line with the destroy/bounce
effect. CR 604.1, together with CR 702.41a's Affinity and CR 702.125a's
Undaunted (the CR's own precedent for this exact "costs [N] less" sentence
being a **separate static ability**, not a clause of whatever else shares its
line), is why `machines/abilities._split_off_trailing_cost_reduction` peels it
off before the rest is ever read as an effect, rather than letting it sink the
whole paragraph the way an actually-unreadable clause correctly would. World
Breaker's own "Return this card from your graveyard to your hand" is a plain
self-reference (`machines/effects._parse_self_return_clause`), and Waker of
Waves' split needed `Game.look_at_top_and_split`
(`_merge_look_top_split_hand_graveyard_clauses`), which landed on main after
this file was first written. This file is about the activation itself - the
zone check, the cost (including the reduction), and the ability landing on the
stack independently of its source (CR 113.7a) - each card's own resolution is
exercised here as end-to-end proof that the whole thing actually works, not
duplicated unit coverage of `machines/effects.py`'s own clause parsers.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import CardSplit, DecisionKind, ScriptedAnswer
from magic_cards_model.machines.keywords import (
    off_battlefield_activation,
    off_zone_abilities,
    off_zone_activation,
)
from magic_cards_model.models import Zone
from tests.cards import card as card_named
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


def test_world_breaker_returns_itself_to_hand_once_the_ability_resolves():
    """World Breaker's own effect is "Return this card from your graveyard
    to your hand" - a self-reference `_RETURN_THIS_CARD_TO_HAND_RE` reads
    directly (CR 701.9a's shape of move, read off the object the ability is
    itself printed on rather than a target), so the card genuinely comes
    back."""
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


def test_otawara_channel_bounces_its_target():
    """Otawara's Channel prints two sentences: the bounce, and "This ability
    costs {1} less to activate for each legendary creature you control." The
    second is a *separate static ability* sharing the printed line (CR 604.1,
    CR 702.41a's Affinity and CR 702.125a's Undaunted are the CR's own
    precedent for this exact "costs [N] less" shape being its own ability,
    not a third clause of the first one's effect), so
    `machines/abilities._split_off_trailing_cost_reduction` reads it off
    before the bounce sentence is stored as `effect` - the paragraph-atomic
    rule is about a *genuinely* unreadable clause, and this one turned out to
    be readable once correctly told apart from the ability it shares a line
    with. The bounce itself is a single plain targeted clause once the
    trailing sentence is gone, and resolves for real.
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
    assert sol_ring.zone is Zone.HAND, "the bounce actually ran"
    assert scenario.game.controller_of(sol_ring).username == "bob"
    assert otawara.zone is Zone.GRAVEYARD, "the discard cost was still paid"


def test_otawaras_cost_reduction_is_its_own_ability_not_a_third_clause():
    """CR 601.2f via CR 602.2b: "This ability costs {1} less to activate for
    each legendary creature you control" is read and actually applied - two
    legendary creatures make the printed {3}{U} cost {1}{U}, verified here by
    paying exactly that and nothing more."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            hand=["Otawara, Soaring City"],
            battlefield=[
                "Island",
                "Island",
                "Ragavan, Nimble Pilferer",
                "Questing Beast",
            ],
        )
        .player("bob", battlefield=["Sol Ring"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    otawara = scenario.find("Otawara, Soaring City", Zone.HAND, "alice")
    sol_ring = scenario.find("Sol Ring", Zone.BATTLEFIELD, "bob")
    islands = scenario.untapped_sources("Island", "Island")

    activation = off_battlefield_activation(scenario.game, otawara, "alice", targets=[sol_ring])
    assert str(activation.cost.mana) == "{1}{U}"

    payment = activation.begin_paying()
    pay_with(*islands)(payment)
    payment.pay()
    activation.activate()
    activation.resolve()

    assert sol_ring.zone is Zone.HAND
    assert scenario.game.cost_modifier_notices == []


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


def test_waker_of_waves_splits_the_top_two_cards_between_hand_and_graveyard():
    """`Game.look_at_top_and_split` (landed on main since this file's own
    xfail was first written) is what `_merge_look_top_split_hand_graveyard_
    clauses` in `machines/effects.py` asks - the same CR 608.2d question
    `scry`/`surveil` already ask, generalised past their own fixed pair of
    destinations. Which of the two looked-at cards goes to hand is the
    controller's own unstated choice (CR 608.2d), scripted here the same way
    `test_look_at_top_and_split.py` scripts Duskwatch Recruiter's."""
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
    bolt, forest = scenario.top_of_library(2)

    scenario.game.decisions.add(
        ScriptedAnswer(kind=DecisionKind.SCRY, value=CardSplit(moved=(bolt.id,)), player="alice")
    )

    activation = off_battlefield_activation(scenario.game, waker, "alice")
    payment = activation.begin_paying()
    pay_with(*islands)(payment)
    payment.pay()
    activation.activate()
    activation.resolve()

    assert bolt.zone is Zone.HAND
    assert forest.zone is Zone.GRAVEYARD


# --------------------------------------------------------------------------
# One index space over every off-battlefield activation (CR 113.6j, CR 113.6m,
# CR 702.29a)
# --------------------------------------------------------------------------


def test_the_off_zone_pool_lists_cycling_and_printed_abilities_in_one_index_space():
    """`off_zone_abilities` is the single ordered pool `off_zone_activation`
    (and `machines/legal_actions`' own `ACTIVATE_OFF_ZONE` enumeration) count
    against - cycling first (CR 702.29a), then a printed ability whose own
    text puts it in another zone (CR 113.6j/CR 113.6m).

    Without it, "off-battlefield activation number 0" named two different
    abilities on a card that prints one of each, and no caller holding an
    `Action` could tell which of the two entry points it was supposed to
    call.
    """
    wraith = card_named("Street Wraith")
    waker = card_named("Waker of Waves")
    turtle = card_named("Colossal Skyturtle")

    (cycling,) = off_zone_abilities(wraith)
    assert cycling.family == "cycling"
    assert cycling.keyword == "Cycling"
    assert cycling.zone is Zone.HAND
    assert cycling.rule == "CR 702.29a"

    (plain,) = off_zone_abilities(waker)
    assert plain.family == "printed"
    assert plain.keyword is None, "Waker of Waves prints no ability word at all"
    assert plain.zone is Zone.HAND
    assert plain.rule == "CR 113.6j"

    both = off_zone_abilities(turtle)
    assert [ability.keyword for ability in both] == ["Channel", "Channel"]
    assert [ability.family for ability in both] == ["printed", "printed"]


def test_off_zone_activation_reaches_a_printed_ability_by_its_pool_index():
    """The unkeyworded shape the owner's own game reached for: Waker of Waves
    at index 0 of its own off-zone pool, activated from hand for
    `{1}{U}, Discard this card` (CR 113.6j)."""
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
    bolt, forest = scenario.top_of_library(2)
    scenario.game.decisions.add(
        ScriptedAnswer(kind=DecisionKind.SCRY, value=CardSplit(moved=(bolt.id,)), player="alice")
    )

    activation = off_zone_activation(scenario.game, waker, "alice", 0)
    assert activation.rule == "CR 113.6j"
    assert str(activation.cost) == "{1}{U}, Discard this card"

    payment = activation.begin_paying()
    pay_with(*islands)(payment)
    payment.pay()
    activation.activate()
    activation.resolve()

    assert waker.zone is Zone.GRAVEYARD, "the discard cost was paid"
    assert bolt.zone is Zone.HAND
    assert forest.zone is Zone.GRAVEYARD


def test_off_zone_activation_reaches_the_second_of_two_printed_abilities():
    """Colossal Skyturtle prints two Channel abilities, so its pool has a
    real index 1 - the case that proves the index is read against the pool
    and not assumed to be 0."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Colossal Skyturtle"], battlefield=["Island", "Island"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    turtle = scenario.find("Colossal Skyturtle", Zone.HAND, "alice")
    bears = scenario.find("Grizzly Bears", Zone.BATTLEFIELD, "bob")
    islands = scenario.untapped_sources("Island", "Island")

    activation = off_zone_activation(scenario.game, turtle, "alice", 1, targets=[bears])
    assert str(activation.cost) == "{1}{U}, Discard this card"

    payment = activation.begin_paying()
    pay_with(*islands)(payment)
    payment.pay()
    activation.activate()
    activation.resolve()

    assert bears.zone is Zone.HAND, "the bounce ran"
    assert turtle.zone is Zone.GRAVEYARD


def test_off_zone_activation_reaches_cycling_through_the_same_call():
    """Cycling is in the same pool (CR 702.29a makes it an ordinary activated
    ability), so a caller holding an `ACTIVATE_OFF_ZONE` action never has to
    work out which of two engine entry points it meant."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Street Wraith"], library=["Lightning Bolt"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    wraith = scenario.find("Street Wraith", Zone.HAND, "alice")
    activation = off_zone_activation(scenario.game, wraith, "alice", 0)
    assert activation.rule == "CR 702.29a"

    payment = activation.begin_paying()
    payment.pay()
    activation.activate()
    activation.resolve()

    assert wraith.zone is Zone.GRAVEYARD
    assert scenario.find("Lightning Bolt", Zone.HAND, "alice") is not None


def test_off_zone_activation_refuses_an_index_the_pool_does_not_have():
    """Fail closed, and in the engine's own words: a card with one off-zone
    ability has no number 1, and a card with none at all has no number 0."""
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", hand=["Waker of Waves", "Lightning Bolt"], battlefield=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    waker = scenario.find("Waker of Waves", Zone.HAND, "alice")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "alice")

    with pytest.raises(ValueError, match="no activated ability functioning off the battlefield"):
        off_zone_activation(scenario.game, waker, "alice", 1)
    with pytest.raises(ValueError, match="no activated ability functioning off the battlefield"):
        off_zone_activation(scenario.game, bolt, "alice", 0)


def test_off_zone_abilities_carry_a_display_ready_ability_object():
    """`OffZoneAbility.ability` is what a caller displaying "what does
    activating this ask for" reads (the api's `engine_api.list_abilities`
    is exactly that caller) - a plain `ActivatedAbility` for both families,
    so cycling's rule-defined text ("[Cost], Discard this card: Draw a
    card.") and a printed ability's own text (Waker of Waves', Boseiju's
    Channel) are read the same way, with no branch on which family built it.
    """
    wraith = card_named("Street Wraith")
    waker = card_named("Waker of Waves")
    boseiju = card_named("Boseiju, Who Endures")

    (cycling,) = off_zone_abilities(wraith)
    assert cycling.ability.cost == "Pay 2 life, Discard this card"
    assert cycling.ability.effect == "Draw a card."

    (plain,) = off_zone_abilities(waker)
    assert plain.ability.cost == "{1}{U}, Discard this card"
    assert "Look at the top two cards" in plain.ability.effect

    # Boseiju prints its mana ability first ({T}: Add {G}) and Channel
    # second, but `activated_abilities(boseiju)`'s full battlefield-oriented
    # list is not what `index` here counts against - only the printings that
    # have a `zone` at all (`off_battlefield_activation`'s own `candidates`
    # filter) do, so Channel is family-local index 0 even though it is
    # `activated_abilities_of(boseiju)`'s raw index 1. A caller that read
    # the ordinary battlefield ability list for this card's own index would
    # call the wrong number - see `engine_api.list_abilities`'s zone branch.
    (channel,) = off_zone_abilities(boseiju)
    assert channel.index == 0, "its own position within the filtered, zone-having family"
    assert channel.ability.cost == "{1}{G}, Discard this card"
