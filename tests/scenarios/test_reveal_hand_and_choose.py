"""A player other than a revealed hand's owner choosing a card from it (CR
701.20a, CR 701.9b) - `_merge_reveal_hand_choose_discard_clauses` in
`machines/effects.py`.

Thoughtseize is the vehicle: "Target player reveals their hand. You choose a
nonland card from it. That player discards that card. You lose 2 life." Every
`DecisionKind.CHOOSE_CARDS` question in the codebase before this file put the
choice to the player whose cards they were - the cleanup discard
(`Game.ask_cleanup_discard`), a fetchland's own search - because CR 701.9b's
*default* chooser on a discard is the discarding player. Thoughtseize
overrides that default outright: the resolving spell's controller chooses,
not the player whose hand is revealed and who then discards.

Every CR number below was looked up with `knowledge_search(q="...",
type="rules")` in the session that wrote this file:

- **CR 701.20a** - "To reveal a card, show that card to all players for a
  brief time." Purely informational - nothing about the board state changes
  from a reveal alone, the same "nothing to do" `_look_at_top_card`'s own
  docstring already documents for CR 701.20e's look.
- **CR 701.9a** - "To discard a card, move it from its owner's hand to that
  player's graveyard."
- **CR 701.9b** - "By default, effects that cause a player to discard a card
  allow the affected player to choose which card to discard. Some effects,
  however, ... allow another player to choose which card is discarded" -
  Thoughtseize's own "you choose" is that override.
- **CR 608.2d** - "The player can't choose an option that's illegal or
  impossible" - an all-land hand has no legal nonland card, so the choice is
  never even offered, exactly the same impossible-option shape `may_pay_life`
  (CR 119.4) already carries.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import DecisionKind
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import ExileMarker

from .harness import Scenario


def test_the_caster_chooses_a_nonland_card_and_the_target_discards_it():
    """The default chooser is overridden: alice (the caster) picks which
    nonland card bob discards, not bob himself."""
    scenario = (
        Scenario()
        .player("alice", hand=["Thoughtseize"], battlefield=["Swamp"])
        .player("bob", hand=["Lightning Bolt", "Forest", "Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bob = scenario.player("bob")
    (swamp,) = scenario.untapped_sources("Swamp")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "bob")

    scenario.will_discard(bolt, username="alice")

    scenario.cast_and_resolve("Thoughtseize", swamp, targets=["bob"])

    assert bolt.zone is Zone.GRAVEYARD
    assert bolt not in bob.hand
    assert len(bob.hand) == 2
    assert alice.life == 18


def test_the_choice_is_recorded_as_the_casters_decision_not_the_targets():
    """`Decision.player` is the resolving spell's controller (alice), the
    proof that CR 701.9b's default was actually overridden rather than the
    question just happening to land on the right answer by coincidence."""
    scenario = (
        Scenario()
        .player("alice", hand=["Thoughtseize"], battlefield=["Swamp"])
        .player("bob", hand=["Lightning Bolt", "Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (swamp,) = scenario.untapped_sources("Swamp")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "bob")
    scenario.will_discard(bolt, username="alice")

    scenario.cast_and_resolve("Thoughtseize", swamp, targets=["bob"])

    choose = next(d for d in scenario.questions_asked() if d.kind is DecisionKind.CHOOSE_CARDS)
    assert choose.player == "alice"


def test_an_all_land_hand_has_no_legal_choice_but_life_is_still_lost():
    """CR 608.2d: no nonland card exists, so the question is never asked at
    all - not asked-and-declined, simply never put. "You lose 2 life" is a
    separate, unconditional sentence with no "if you do" gate on it, so it
    still happens."""
    scenario = (
        Scenario()
        .player("alice", hand=["Thoughtseize"], battlefield=["Swamp"])
        .player("bob", hand=["Forest", "Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    bob = scenario.player("bob")
    (swamp,) = scenario.untapped_sources("Swamp")

    scenario.cast_and_resolve("Thoughtseize", swamp, targets=["bob"])

    assert not any(d.kind is DecisionKind.CHOOSE_CARDS for d in scenario.questions_asked())
    assert len(bob.hand) == 2
    assert alice.life == 18


def test_an_empty_hand_reveals_nothing_but_life_is_still_lost():
    """An empty hand is not a special case CR 701.9b needs to name: there is
    still nothing to choose, and the life loss still happens."""
    scenario = (
        Scenario()
        .player("alice", hand=["Thoughtseize"], battlefield=["Swamp"])
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    alice = scenario.player("alice")
    (swamp,) = scenario.untapped_sources("Swamp")

    scenario.cast_and_resolve("Thoughtseize", swamp, targets=["bob"])

    assert alice.life == 18


def test_the_discard_routes_through_madness_not_a_bare_hand_removal():
    """The discard has to go through `machines/keywords.discard`
    (`Player.discard` already routes there when a game is attached), not a
    bare `hand.remove`, so a card with madness in the revealed hand is
    exiled rather than put into the graveyard (CR 702.35a) - proof this
    effect used the real discard path and not a hand-clearing shortcut that
    would look identical for an ordinary card."""
    scenario = (
        Scenario()
        .player("alice", hand=["Thoughtseize"], battlefield=["Swamp"])
        .player("bob", hand=["Basking Rootwalla", "Forest"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    (swamp,) = scenario.untapped_sources("Swamp")
    rootwalla = scenario.find("Basking Rootwalla", Zone.HAND, "bob")
    scenario.will_discard(rootwalla, username="alice")

    scenario.cast_and_resolve("Thoughtseize", swamp, targets=["bob"])

    assert rootwalla.zone is Zone.EXILE
    assert rootwalla.exile_annotation is not None
    assert rootwalla.exile_annotation.marker is ExileMarker.MADNESS
    assert rootwalla not in bob.hand


# -- Grief: "target opponent", and a discard read off a triggered ability --


def test_griefs_own_enters_the_battlefield_trigger_reads_target_opponent():
    """Grief prints "target opponent" (Thoughtseize prints "target player"),
    and the same template otherwise: "You choose a nonland card from it.
    That player discards that card." - `_REVEAL_HAND_RE` widened to read
    both spellings, exercised here as a triggered ability rather than a
    resolving spell's own effect."""
    scenario = (
        Scenario()
        .player("alice", hand=["Grief"], battlefield=["Swamp"] * 4)
        .player("bob", hand=["Lightning Bolt", "Forest", "Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    swamps = scenario.untapped_sources("Swamp", "Swamp", "Swamp", "Swamp")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "bob")
    scenario.choose_trigger_targets("Grief", ["bob"])
    scenario.will_discard(bolt, username="alice")

    scenario.cast_and_resolve("Grief", *swamps)
    scenario.pass_until_resolved()

    assert bolt.zone is Zone.GRAVEYARD
    assert bolt not in bob.hand
    assert len(bob.hand) == 2


# -- Thought-Knot Seer: exile, not discard, and folded into one sentence ---


def test_thought_knot_seer_exiles_the_chosen_card_instead_of_discarding_it():
    """Thought-Knot Seer's own second sentence reads "You choose a nonland
    card from it **and exile that card**" - the same anaphoric run, ending in
    `_EXILE_THAT_CARD_RE`'s CR 701.13a exile rather than `_DISCARD_THAT_CARD_
    RE`'s CR 701.9a discard. `split_effect_clauses` cuts the bare "and" the
    same way it does everywhere else, so this reads as three clauses just
    like Thoughtseize's three sentences do."""
    scenario = (
        Scenario()
        .player("alice", hand=["Thought-Knot Seer"], battlefield=["Wastes"] * 4)
        .player("bob", hand=["Lightning Bolt", "Forest", "Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    sources = scenario.untapped_sources("Wastes", "Wastes", "Wastes", "Wastes")
    bolt = scenario.find("Lightning Bolt", Zone.HAND, "bob")
    scenario.choose_trigger_targets("Thought-Knot Seer", ["bob"])
    scenario.will_discard(bolt, username="alice")

    scenario.cast_and_resolve("Thought-Knot Seer", *sources)
    scenario.pass_until_resolved()

    assert bolt.zone is Zone.EXILE
    assert bolt not in bob.hand
    assert len(bob.hand) == 2


def test_thought_knot_seer_leaving_gives_the_card_back_with_a_fresh_draw():
    """The second trigger, "When this creature leaves the battlefield,
    target opponent draws a card" - CR 121.2's plain draw, aimed at whichever
    player this leaves-the-battlefield trigger targets, not the card Thought-
    Knot Seer itself took (CR 108.3: a new card, not the returned one)."""
    scenario = (
        Scenario()
        .player("alice", hand=["Thought-Knot Seer"], battlefield=["Wastes"] * 4)
        .player("bob", hand=["Forest"], library=["Mountain"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bob = scenario.player("bob")
    sources = scenario.untapped_sources("Wastes", "Wastes", "Wastes", "Wastes")
    scenario.choose_trigger_targets("Thought-Knot Seer", ["bob"])

    scenario.cast_and_resolve("Thought-Knot Seer", *sources)
    scenario.pass_until_resolved()

    seer = scenario.creature("Thought-Knot Seer", "alice")
    scenario.choose_trigger_targets("Thought-Knot Seer", ["bob"])

    scenario.game.destroy(seer)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert [state.name for state in bob.hand] == ["Forest", "Mountain"]
