"""Look at the top N cards of a library, then put them back in any order,
with an optional shuffle - Ponder, Index, Pondering Mage's own ETB trigger,
and Architects of Will's targeted variant.

`_merge_look_top_put_back_any_order_clauses` (`machines/effects.py`) reads
"look at the top N cards of your/target player's library, then put them back
in any order" as one anaphoric pair, reusing `Game.look_at_top_and_split`
(the same CR 608.2d split question `_merge_look_top_reveal_to_hand_clauses`
already asks for Duskwatch Recruiter) with `moved_amount=0`: nothing is ever a
legal "moved" answer, so the entire looked-at set is always `rest`, and its
`top_order` is CR 401.4's free arrangement. A separate clause reader answers
"you may shuffle" with `Game.may` + `Game.shuffle_library`, the same "you may"
machinery (`_parse_optional_player_clause`) every other optional clause in
this parser already goes through - so its unscripted default is `Game.may`'s
own documented one, "take it" (see `test_conditional_sacrifice_clauses.
test_the_sacrifice_defaults_to_taking_it_unscripted`), not a bespoke default
invented for this one clause.

Every CR number below was looked up with `mise run rules:find` in the session
that wrote this file, against the on-disk Comprehensive Rules effective
2026-09-25:

- **CR 608.2d** - "The player can't choose an option that's illegal or
  impossible" - `moved_amount=0` makes every option but the empty one
  illegal, so `Game.ask` refuses a scripted answer that tries to move a card
  before this reader's own code ever runs.
- **CR 401.4** - "If an effect puts two or more cards in a specific position
  in a library at the same time, the owner of those cards may arrange them in
  any order" - the free `top_order`.
- **CR 609.3** - "If an effect attempts to do something impossible, it does
  only as much as possible" - a library shorter than the printed count looks
  at and orders whatever is actually there.
- **CR 701.24a** - "To shuffle a library ... randomize the cards within it so
  that no player knows their order."
- **CR 701.20d** - a reveal or a look ends when the library "is shuffled or
  otherwise reordered."
- **CR 701.20e** - "looking at a card follows the same rules as revealing a
  card, except that the card is shown only to the specified player" - the
  official Architects of Will ruling: "You look at the cards, not the
  targeted player."
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_ponder_orders_the_top_three_and_declining_the_shuffle_keeps_that_order():
    """Ponder: one SCRY-kind question over the top three, the chosen
    `top_order` becomes the library's top three, and declining the shuffle
    (scripted `False`, not left to the default) keeps that order - then one
    card is drawn, the new top."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Ponder"],
            library=["Forest", "Island", "Swamp", "Mountain"],
            battlefield=["Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    forest, island, swamp = scenario.top_of_library(3)
    mountain = alice.library[3]

    scenario.scry_bottoming(top_order=[swamp, forest, island], username="alice")
    scenario.will_take_the_may(False, username="alice", source="Ponder")

    ponder = scenario.cast_and_resolve("Ponder", *scenario.untapped_sources("Island"))

    scry_asked = [d for d in scenario.game.decisions.asked if d.kind is DecisionKind.SCRY]
    assert len(scry_asked) == 1
    assert set(scry_asked[0].cards) == {forest.id, island.id, swamp.id}

    assert ponder.zone is Zone.GRAVEYARD
    assert swamp in alice.hand and swamp.zone is Zone.HAND, "the new top, drawn"
    assert alice.library[:3] == [forest, island, mountain]


def test_ponder_with_the_shuffle_accepted_randomises_and_ends_the_look():
    """Accepting the shuffle: the library is a permutation of the pre-cast
    library minus the one drawn card, `library_epoch` has moved on past the
    look, and the look's own knowledge is gone (`Game.known_to`)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Ponder"],
            library=["Forest", "Island", "Swamp", "Mountain", "Plains", "Wastes"],
            battlefield=["Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    pre_cast_ids = {state.id for state in alice.library}
    looked_at_ids = {state.id for state in alice.library[:3]}
    epoch_before = alice.library_epoch
    shuffles_before = scenario.game.shuffles_performed

    scenario.will_take_the_may(True, username="alice", source="Ponder")

    ponder = scenario.cast_and_resolve("Ponder", *scenario.untapped_sources("Island"))

    assert ponder.zone is Zone.GRAVEYARD
    assert scenario.game.shuffles_performed == shuffles_before + 1
    assert alice.library_epoch > epoch_before, "CR 701.20d: shuffled, a fresh epoch"
    assert len(alice.hand) == 1, "one card drawn, nothing else"
    (drawn,) = alice.hand
    assert drawn.id in pre_cast_ids
    remaining_ids = {state.id for state in alice.library}
    assert remaining_ids | {drawn.id} == pre_cast_ids, "a permutation, nothing lost or gained"
    assert len(alice.library) == len(pre_cast_ids) - 1

    known_ids = {card.card_id for card in scenario.game.known_to("alice")}
    assert not (looked_at_ids & known_ids), "the shuffle ends the look (CR 701.20d)"


def test_an_unscripted_seat_keeps_the_order_and_declines_the_shuffle_by_default():
    """Nothing scripted at all: `default_answer`'s own `SCRY` default ("keep
    every card on top", no card moved and no order named) leaves the
    looked-at order unchanged - the same reason `tests/scenarios/test_
    conditional_alternative_costs.py`'s own unscripted Ponder casts need no
    change here, since none of its assertions read library order or count.

    The shuffle is a second question with its own default, and this file
    covers it on its own terms rather than assuming it from the split: `MAY`'s
    documented default is "take it" (`test_conditional_sacrifice_clauses.
    test_the_sacrifice_defaults_to_taking_it_unscripted` is the precedent),
    so an entirely unscripted Ponder both keeps the looked-at order (`SCRY`'s
    own default) *and* shuffles the rest of the library behind it (`MAY`'s
    own default) - the shuffle is over the whole library, so it never
    contradicts the three-card order the split already fixed above it.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Ponder"],
            library=["Forest", "Island", "Swamp", "Mountain"],
            battlefield=["Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    shuffles_before = scenario.game.shuffles_performed

    ponder = scenario.cast_and_resolve("Ponder", *scenario.untapped_sources("Island"))

    assert ponder.zone is Zone.GRAVEYARD
    assert len(alice.hand) == 1, "the draw happens either way"
    assert scenario.game.shuffles_performed == shuffles_before + 1, (
        "MAY's own default is 'take it' - see test_conditional_sacrifice_clauses"
    )


def test_index_counts_five_and_asks_no_shuffle_question():
    """Index: "Look at the top five cards of your library, then put them back
    in any order." - the split half only, no "you may shuffle" and no draw,
    so exactly one SCRY question is asked and no MAY question at all."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Index"],
            library=["Forest", "Island", "Swamp", "Mountain", "Plains", "Wastes"],
            battlefield=["Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    top_five = scenario.top_of_library(5)
    wastes = alice.library[5]

    scenario.scry_bottoming(top_order=list(reversed(top_five)), username="alice")

    index_card = scenario.cast_and_resolve("Index", *scenario.untapped_sources("Island"))

    asked_kinds = [d.kind for d in scenario.game.decisions.asked]
    assert asked_kinds.count(DecisionKind.SCRY) == 1
    assert DecisionKind.MAY not in asked_kinds

    assert index_card.zone is Zone.GRAVEYARD
    assert alice.hand == [], "no draw clause on Index"
    assert alice.library == [*reversed(top_five), wastes]


def test_index_with_only_two_cards_in_the_library_orders_both():
    """CR 609.3: a library shorter than the printed count looks at and
    orders whatever is actually there - Index's own "top five" over a
    two-card library."""
    scenario = (
        Scenario()
        .player("alice", hand=["Index"], library=["Forest", "Island"], battlefield=["Island"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    forest, island = alice.library[:2]

    scenario.scry_bottoming(top_order=[island, forest], username="alice")

    scenario.cast_and_resolve("Index", *scenario.untapped_sources("Island"))
    scry_asked = [d for d in scenario.game.decisions.asked if d.kind is DecisionKind.SCRY]

    assert len(scry_asked) == 1
    assert set(scry_asked[0].cards) == {forest.id, island.id}
    assert alice.library == [island, forest]


def test_pondering_mage_reads_the_same_text_on_an_etb_trigger_with_a_draw_after():
    """Pondering Mage: "When this creature enters, look at the top three
    cards of your library, then put them back in any order. You may shuffle.
    Draw a card." - the identical text on a triggered ability's own
    resolution (`AbilityOnStack`, not a spell), so `for_spell=False`."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Pondering Mage"],
            library=["Forest", "Island", "Swamp", "Mountain"],
            battlefield=["Island"] * 5,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    forest, island, swamp = scenario.top_of_library(3)
    mountain = alice.library[3]

    scenario.scry_bottoming(top_order=[island, swamp, forest], username="alice")
    scenario.will_take_the_may(False, username="alice", source="Pondering Mage")

    scenario.cast_and_resolve("Pondering Mage", *scenario.untapped_sources(*["Island"] * 5))
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    assert len(alice.hand) == 1, "the ETB's own draw"
    (drawn,) = alice.hand
    assert drawn is island, "the new top, after the ordered put-back"
    assert alice.library == [swamp, forest, mountain]


def test_architects_of_will_targets_a_players_library_but_the_controller_looks():
    """Architects of Will: "When this creature enters, look at the top three
    cards of target player's library, then put them back in any order." -
    the controller does the looking and the ordering (the official ruling:
    "You look at the cards, not the targeted player."), and CR 701.20e's
    knowledge is recorded for the controller alone."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Architects of Will"],
            battlefield=["Island", "Swamp", "Forest", "Mountain"],
        )
        .player("bob", library=["Forest", "Swamp", "Mountain", "Plains"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    forest, swamp, mountain = bob.library[:3]
    plains = bob.library[3]

    scenario.choose_trigger_targets("Architects of Will", ["bob"])
    scenario.scry_bottoming(top_order=[mountain, forest, swamp], username="alice")

    scenario.cast_and_resolve(
        "Architects of Will", *scenario.untapped_sources("Island", "Swamp", "Forest", "Mountain")
    )
    scenario.game.put_triggers_on_stack()
    scenario.resolve_top()

    scry_asked = [d for d in scenario.game.decisions.asked if d.kind is DecisionKind.SCRY]
    assert len(scry_asked) == 1
    assert scry_asked[0].player == "alice", "the controller looks, not the targeted player"

    assert bob.library == [mountain, forest, swamp, plains]

    controller_known = {card.card_id for card in scenario.game.known_to("alice")}
    target_known = {card.card_id for card in scenario.game.known_to("bob")}
    assert {mountain.id, forest.id, swamp.id} <= controller_known
    assert not ({mountain.id, forest.id, swamp.id} & target_known), (
        "CR 701.20e: shown only to the specified player - the controller, not the target"
    )
