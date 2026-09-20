"""Titanbones, Towering Heart's own "When you discard this card, you gain 3
life." (CR 701.9a's discard, CR 603.10a's look-back - the card is already
gone from the hand by the time the ability is checked).

`_trigger_event`'s discard regex only read "discard a card"/"discard one or
more cards"; "discard **this card**" left `event=None`, and `Game.discard_
cards` batches every card of one discard instruction into a single event with
no per-card identity at all, so a self-reference had nothing to check against
even once the phrase was recognised. `GameEvent.discarded_ids` is the new
per-batch record; `_self_referential`'s own `_SELF_PHRASES` already covers
"this card".
"""

from magic_cards_model.machines import Step
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def test_titanbones_gains_three_life_when_discarded():
    scenario = (
        Scenario()
        .player("alice", hand=["Titanbones, Towering Heart"], life=20)
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    titanbones = scenario.find("Titanbones, Towering Heart", Zone.HAND)

    scenario.game.discard_cards("alice", [titanbones])
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == ["Titanbones, Towering Heart's triggered ability"]
    scenario.pass_until_resolved()
    assert scenario.player("alice").life == 23


def test_discarding_a_different_card_does_not_trigger_titanbones():
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Titanbones, Towering Heart", "Lightning Bolt"],
            life=20,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bolt = scenario.find("Lightning Bolt", Zone.HAND)

    scenario.game.discard_cards("alice", [bolt])
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == []
    assert scenario.player("alice").life == 20


def test_titanbones_fires_even_discarded_alongside_another_card_in_the_same_batch():
    """CR 603.2c's "one event, multiple occurrences": a two-card discard is
    still one `DISCARDS_A_CARD` event, and Titanbones' self-reference is
    checked against the whole batch (`GameEvent.discarded_ids`), not just a
    single `subject_id`."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Titanbones, Towering Heart", "Lightning Bolt"],
            life=20,
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    titanbones = scenario.find("Titanbones, Towering Heart", Zone.HAND)
    bolt = scenario.find("Lightning Bolt", Zone.HAND)

    scenario.game.discard_cards("alice", [bolt, titanbones])
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == ["Titanbones, Towering Heart's triggered ability"]


def test_edgars_awakening_off_pool_proof_triggers_when_discarded():
    """Off-pool generality proof: Edgar's Awakening prints the identical
    "When you discard this card, ..." sentence on a sorcery, with a
    differently shaped effect (a reflexive "you may pay" clause) rather than
    Titanbones' plain life gain."""
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Edgar's Awakening"],
            graveyard=["Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    awakening = scenario.find("Edgar's Awakening", Zone.HAND)

    scenario.game.discard_cards("alice", [awakening])
    scenario.game.put_triggers_on_stack()

    assert scenario.stack_names() == ["Edgar's Awakening's triggered ability"]
