"""Trigger events and the machinery that emits them: drawing, life, damage,
sacrifice, countering, untapping.

Every rule cited here was looked up with `knowledge_search(type="rules")` in the
session that wrote the file. The spine of it:

- **CR 121.2** - "Cards may only be drawn one at a time. If a player is
  instructed to draw multiple cards, that player performs that many individual
  card draws." A draw of three is three trigger events, not one with a count.
- **CR 119.3** - "If an effect causes a player to gain life or lose life, that
  player's life total is adjusted accordingly." One event per gain or loss.
- **CR 119.9** - a trigger written "Whenever [a player] gains life" is treated
  as written "Whenever a source causes [a player] to gain life".
- **CR 702.15e** - simultaneous lifelink sources cause separate life gain
  events, so gains are never batched.
- **CR 120.1** - "An object that deals damage is the source of that damage";
  CR 120.2a - "Damage may be dealt as a result of combat", which is the word
  the printed conditions hang on.
- **CR 603.2g** - "An ability triggers only if its trigger event actually
  occurs. An event that's prevented or replaced won't trigger anything."
- **CR 701.21a** - "To sacrifice a permanent, its controller moves it from the
  battlefield directly to its owner's graveyard." CR 700.4 - "dies" means "is
  put into a graveyard from the battlefield". One sacrifice is therefore two
  trigger events, and CR 603.10a lets sacrifice triggers look back in time.
- **CR 701.6a** - to counter a spell is to cancel it and put it into its
  owner's graveyard; CR 603.10e has the triggers watching that look back in
  time.
- **CR 701.26a** - "To tap a permanent, turn it sideways from an upright
  position. Only untapped permanents can be tapped." Paying a tap cost and
  attacking without vigilance (CR 508.1f, CR 702.20b) both turn the
  permanent sideways, so both are tap events.
- **CR 702.48b** - "You choose which permanent to sacrifice as you make choices
  for the spell (see rule 601.2b), and you sacrifice that permanent as you pay
  the total cost (see rule 601.2h)." A sacrifice paid as a cost is a sacrifice,
  so it is the same two events as any other.
- **CR 701.26b** - to untap is to rotate back upright, and only tapped
  permanents can be untapped; CR 502.3 is the untap step that untaps them all.

The events are staged through `Game.create_delayed_trigger` where no card in
the pool prints the condition - the sanctioned path, per
`test_delayed_triggered_abilities.py` - and through real pool cards wherever
one does: Sheoldred, the Apocalypse (both draw halves), Ragavan, Nimble
Pilferer, Questing Beast, and Dragon Appeasement.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import TriggerEvent
from magic_cards_model.machines.delayed import DelayedTrigger, SacrificeSubject
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def board(battlefield: list[str], **alice_kwargs) -> Scenario:
    """Alice and bob, each with a few cards to draw, and Alice's battlefield."""
    return (
        Scenario()
        .player(
            "alice",
            library=["Forest", "Island", "Mountain"],
            battlefield=battlefield,
            **alice_kwargs,
        )
        .player("bob", library=["Island", "Island", "Island"], battlefield=["Grizzly Bears"])
    )


def watcher(scenario, event: TriggerEvent, text: str, controller: str = "alice") -> DelayedTrigger:
    """Stage a delayed trigger watching `event`, as a resolving spell would.

    CR 603.7: a delayed triggered ability is created by an effect and waits
    for its event. No card in the pool prints "whenever a player loses life"
    or the counter and untap conditions, so the watcher is created through
    `Game.create_delayed_trigger` rather than by a card. Its effect key has no
    entry in `machines/delayed.py`, which resolves as nothing - what is under
    test is that the trigger fires, not what it does.
    """
    return scenario.game.create_delayed_trigger(
        DelayedTrigger(
            text=text,
            effect=SacrificeSubject(),
            event=event,
            controller=controller,
            source_name="a resolving spell",
        )
    )


def conditions(scenario) -> list[str]:
    """The conditions of everything that has triggered but not gone on the stack."""
    return [item.ability.condition for item in scenario.pending_triggers]


# -- drawing (CR 121.2) ----------------------------------------------------


def test_a_draw_of_two_triggers_the_draw_trigger_once_per_card():
    """CR 121.2: the draws are individual, so the trigger fires per card.

    Sheoldred, the Apocalypse prints "Whenever you draw a card, you gain 2
    life" - and the gains are the ability's business, not this test's: what is
    under test is that two individual draws are two events.
    """
    scenario = board(["Sheoldred, the Apocalypse"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.game.draw_cards("alice", 2)

    assert len(scenario.pending_triggers) == 2
    assert conditions(scenario) == ["you draw a card", "you draw a card"]


def test_an_opponents_draw_fires_only_the_opponent_half():
    """Sheoldred's second half: "Whenever an opponent draws a card".

    One draw for bob, one trigger, and it is the opponent half - alice's own
    draw condition is not satisfied by bob's card.
    """
    scenario = board(["Sheoldred, the Apocalypse"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.game.draw_cards("bob", 1)

    assert conditions(scenario) == ["an opponent draws a card"]


def test_a_draw_replacement_made_of_two_cards_triggers_twice():
    """Alhammarret's Archive turns one draw into two; CR 121.2 makes those two.

    The replacement is applied per individual draw (CR 121.6a), and the two
    cards it produces are themselves two individual card draws - so Sheoldred
    sees two events, not one fat one.
    """
    scenario = board(["Sheoldred, the Apocalypse", "Alhammarret's Archive"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    drawn = scenario.game.draw_cards("alice", 1)

    assert len(drawn) == 2, "the Archive replaced one draw with two"
    assert len(scenario.pending_triggers) == 2
    assert conditions(scenario) == ["you draw a card", "you draw a card"]


# -- combat damage (CR 120.1, 120.2a) ---------------------------------------


def test_ragavan_triggers_when_his_combat_damage_hits_a_player():
    """The whole path: declare, connect, trigger, go on the stack.

    "Whenever Ragavan deals combat damage to a player" (CR 120.2a) fires for
    the unblocked one damage, and CR 510.3a puts the ability on the stack
    before the active player gets priority - inside the combat damage step
    itself, so nothing else has to flush the queue. Its effect - the Treasure
    and the exile - is the effects registry's business and does nothing here.
    """
    scenario = board(["Ragavan, Nimble Pilferer"]).build()
    ragavan = scenario.creature("Ragavan, Nimble Pilferer", "alice")

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(ragavan)
    scenario.no_blocks()
    scenario.combat_damage()

    assert conditions(scenario) == [], "CR 510.3a already moved it off the queue"
    assert scenario.stack_names() == ["Ragavan, Nimble Pilferer's triggered ability"]
    assert scenario.player("bob").life == 18, "Ragavan is a 2/1"


def test_ragavan_does_not_trigger_when_his_combat_damage_is_blocked():
    """Damage to a creature is not damage "to a player" (CR 120.2a).

    The Grizzly Bears take the one damage and live; no player lost life, so
    the condition does not match and nothing triggers.
    """
    scenario = board(["Ragavan, Nimble Pilferer"]).build()
    ragavan = scenario.creature("Ragavan, Nimble Pilferer", "alice")

    scenario.start_at(Step.DECLARE_BLOCKERS)
    scenario.attack_with(ragavan)
    scenario.block(ragavan, scenario.creature("Grizzly Bears", "bob"))
    scenario.combat_damage()

    assert scenario.pending_triggers == []
    assert scenario.player("bob").life == 20


def test_a_combat_damage_trigger_does_not_fire_on_a_spells_damage():
    """CR 120.2a: Lightning Bolt's damage is not "combat damage".

    The Bolt resolves with the Ragavan spell as its source (CR 120.1), so the
    event is well-formed and aimed at a player - it is just not combat damage,
    which is the one word the condition asks for.
    """
    scenario = board(["Mountain", "Ragavan, Nimble Pilferer"], hand=["Lightning Bolt"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")

    scenario.cast_and_resolve("Lightning Bolt", mountain, username="alice", targets=["bob"])

    assert scenario.player("bob").life == 17, "the damage was dealt"
    assert scenario.pending_triggers == [], "but it was not combat damage"


def test_questing_beast_triggers_on_combat_damage_to_an_opponent():
    """ "Whenever Questing Beast deals combat damage to an opponent".

    The opponent clause is the part under test: bob is alice's opponent, and
    the trigger reads the damaged player against the Beast's controller. Its
    follow-up aims at "target planeswalker that player controls", and bob
    controls none, so when CR 510.3a puts the batch on the stack the ability
    finds no legal target (CR 603.3d) and is removed - leaving the
    `NO_LEGAL_TARGET` notice as the record that it did trigger.
    """
    scenario = board(["Questing Beast"]).build()
    beast = scenario.creature("Questing Beast", "alice")

    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(beast)
    scenario.no_blocks()
    scenario.combat_damage()

    assert conditions(scenario) == []
    assert scenario.stack_names() == []
    assert [notice.source_name for notice in scenario.game.targeting_notices] == ["Questing Beast"]


# -- life (CR 119.3, 119.9) -------------------------------------------------


def test_gaining_life_triggers_a_life_gain_watcher():
    """CR 119.9: "Whenever [a player] gains life" watches the gain itself.

    No pool card prints the condition, so the watcher is staged - what is
    under test is that `gain_life` emits one event per gain.
    """
    scenario = board([]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    watcher(scenario, TriggerEvent.GAINS_LIFE, "Whenever you gain life, note it.")

    scenario.game.gain_life("alice", 2)

    assert len(scenario.pending_triggers) == 1
    assert scenario.player("alice").life == 22


def test_a_gain_of_no_life_triggers_nothing():
    """CR 603.2g: an event that never happened triggers nothing.

    A gain of zero adjusts nothing, so there is no gain event to match.
    """
    scenario = board([]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    watcher(scenario, TriggerEvent.GAINS_LIFE, "Whenever you gain life, note it.")

    scenario.game.gain_life("alice", 0)

    assert scenario.pending_triggers == []
    assert scenario.player("alice").life == 20


def test_losing_life_to_damage_triggers_a_life_loss_watcher():
    """CR 119.3: the loss is its own event, separate from the damage.

    Bolt costs bob three life; the damage event and the loss event are two
    facts about the same hit, and a trigger watching the loss fires for it.
    Three damage is one loss, so one trigger.
    """
    scenario = board(["Mountain"], hand=["Lightning Bolt"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    watcher(
        scenario,
        TriggerEvent.LOSES_LIFE,
        "Whenever a player loses life, note it.",
        controller="bob",
    )
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")

    scenario.cast_onto_stack("Lightning Bolt", mountain, username="alice", targets=["bob"])
    scenario.pass_priority("alice")
    scenario.pass_priority("bob")  # resolves the Bolt

    # The loss fires as the Bolt resolves and goes on the stack when bob next
    # would receive priority - which pass_priority already handed him.
    assert "a resolving spell's triggered ability" in scenario.stack_names()
    assert scenario.player("bob").life == 17


# -- countering (CR 701.6a) -------------------------------------------------


def test_countering_a_spell_triggers_a_counter_watcher():
    """CR 701.6a: a countered spell is cancelled and put into its graveyard.

    CR 603.10e has the triggers watching the countering look back in time,
    which is why the counter is emitted after the spell has moved.
    """
    scenario = board(["Mountain"], hand=["Lightning Bolt"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    watcher(scenario, TriggerEvent.SPELL_IS_COUNTERED, "Whenever a spell is countered, note it.")
    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, username="alice", targets=["bob"])

    scenario.game.counter(bolt)

    assert len(scenario.pending_triggers) == 1
    assert scenario.find("Lightning Bolt", Zone.GRAVEYARD) is not None
    assert scenario.player("bob").life == 20, "a countered spell never resolves"


# -- sacrificing (CR 701.21a, 700.4) ----------------------------------------


def test_sacrificing_a_creature_fires_both_the_sacrifice_and_the_dies_trigger():
    """One sacrifice, two trigger events (CR 701.21a and CR 700.4).

    Dragon Appeasement watches the sacrifice; Footlight Fiend watches its own
    death. CR 603.10a lets both look back in time, and the sacrifice fires
    first because the move to the graveyard is what causes the death.
    """
    scenario = board(["Dragon Appeasement", "Footlight Fiend"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    fiend = scenario.creature("Footlight Fiend", "alice")
    scenario.choose_trigger_targets("Footlight Fiend", ["bob"])

    scenario.game.sacrifice(fiend)

    assert fiend.zone is Zone.GRAVEYARD
    assert conditions(scenario) == ["you sacrifice a creature", "this creature dies"]

    scenario.game.put_triggers_on_stack()
    assert scenario.stack_names() == [
        "Dragon Appeasement's triggered ability",
        "Footlight Fiend's triggered ability",
    ]


def test_something_not_on_the_battlefield_cannot_be_sacrificed():
    """CR 701.21a: a player can't sacrifice something that isn't a permanent."""
    scenario = board([], hand=["Footlight Fiend"]).build()
    fiend = scenario.find("Footlight Fiend", Zone.HAND)

    with pytest.raises(ValueError):
        scenario.game.sacrifice(fiend)

    assert scenario.pending_triggers == []
    assert scenario.find("Footlight Fiend", Zone.HAND) is not None


# -- leaving the battlefield generically (CR 603.6c) ------------------------


def test_leaving_the_battlefield_to_exile_fires_the_generic_departure_event():
    """`TriggerEvent.LEAVES_THE_BATTLEFIELD` fires alongside the destination-
    specific `LEAVES_BATTLEFIELD_TO_EXILE` - CR 603.6c's plain "leaves the
    battlefield" condition (Thought-Knot Seer's own, tested through the real
    card in `test_dies_trigger_scope.py`) is broader than any one
    destination, so nothing in the pool needs this specific-plus-generic pair
    watched together except through a bare delayed-trigger watcher."""
    scenario = board(["Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    watcher(scenario, TriggerEvent.LEAVES_THE_BATTLEFIELD, "test watcher")

    scenario.game.exile_permanent(bears)

    assert bears.zone is Zone.EXILE
    assert len(scenario.pending_triggers) == 1


def test_leaving_the_battlefield_to_hand_fires_the_generic_departure_event():
    """The third destination, `LEAVES_BATTLEFIELD_TO_HAND` (a bounce), pairs
    with the same generic event the other two destinations do."""
    scenario = board(["Grizzly Bears"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")
    watcher(scenario, TriggerEvent.LEAVES_THE_BATTLEFIELD, "test watcher")

    scenario.game.return_to_hand(bears)

    assert bears.zone is Zone.HAND
    assert len(scenario.pending_triggers) == 1


# -- untapping (CR 701.26b, 502.3) ------------------------------------------


def test_the_untap_step_triggers_becomes_untapped_once_per_tapped_permanent():
    """CR 502.3 untaps them all at once; each one untapping is its own event.

    The Forest was never tapped, and only tapped permanents can be untapped
    (CR 701.26b), so one tapped Bear means exactly one event.
    """
    scenario = board([], hand=["Grizzly Bears", "Forest"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    watcher(
        scenario,
        TriggerEvent.BECOMES_UNTAPPED,
        "Whenever this creature becomes untapped, note it.",
    )
    bears = scenario.put_onto_battlefield("Grizzly Bears", "alice", tapped=True)
    scenario.put_onto_battlefield("Forest", "alice")

    # CR 500.6's step-began events fire from `advance`, so walk into alice's
    # next untap step rather than jumping to it with `start_at` - and it is
    # her next turn: bob untaps first.
    scenario.start_at(Step.END_STEP)
    while scenario.step is not Step.UNTAP or scenario.player().username != "alice":
        scenario.advance()

    assert bears.untapped
    assert len(scenario.pending_triggers) == 1


# -- being tapped (CR 701.26a) -----------------------------------------------


def test_a_tap_paid_as_a_cost_fires_becomes_tapped():
    """CR 701.26a: paying the {T} of "{T}, Sacrifice this artifact" turns
    Mishra's Bauble sideways, which is the trigger event.

    The activation is real: `activate` announces the ability (CR 602.2a), pays
    the {T} component and the sacrifice component (CR 601.2h), and puts the
    ability on the stack. The tap is one event, not two - the bauble is only
    untapped once when it is paid. The trigger rides to the stack with the
    ability (CR 603.3: the next time a player would receive priority), which
    is why the assertion reads the stack and not `pending_triggers`.
    """
    scenario = board(["Mishra's Bauble"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bauble = scenario.find("Mishra's Bauble", Zone.BATTLEFIELD)
    watcher(scenario, TriggerEvent.BECOMES_TAPPED, "Whenever this becomes tapped, note it.")

    scenario.activate(bauble, sacrificing=[bauble], targets=["bob"])

    assert scenario.stack_names() == [
        "Mishra's Bauble's activated ability",
        "a resolving spell's triggered ability",
    ]


def test_declaring_an_attacker_fires_becomes_tapped():
    """CR 508.1f: "Tapping a creature when it's declared as an attacker isn't a
    cost; attacking simply causes creatures to become tapped" - and becoming
    tapped is the event CR 701.26a names.

    The watcher is the only ability watching, so it is the only one the
    declaration puts on the stack (CR 508.2b).
    """
    scenario = board(["Grizzly Bears"]).build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    bears = scenario.creature("Grizzly Bears", "alice")
    watcher(scenario, TriggerEvent.BECOMES_TAPPED, "Whenever this becomes tapped, note it.")

    scenario.attack_with(bears)

    assert bears.tapped
    assert scenario.stack_names() == ["a resolving spell's triggered ability"]


def test_vigilance_keeps_the_attack_from_firing_becomes_tapped():
    """CR 702.20b: attacking doesn't cause a creature with vigilance to tap -
    and a permanent that never taps never became tapped (CR 701.26a).

    No event, no trigger: CR 603.2g is about events that actually occur.
    """
    scenario = board(["Serra Angel"]).build()
    scenario.start_at(Step.DECLARE_ATTACKERS)
    angel = scenario.creature("Serra Angel", "alice")
    watcher(scenario, TriggerEvent.BECOMES_TAPPED, "Whenever this becomes tapped, note it.")

    scenario.attack_with(angel)

    assert angel.untapped
    assert scenario.pending_triggers == []
    assert scenario.game.stack_is_empty


# -- sacrifices paid as costs (CR 702.48b, 701.21a, 700.4) -------------------


def test_a_sacrifice_paid_as_a_cost_fires_both_the_sacrifice_and_the_dies_trigger():
    """CR 702.48b: "you sacrifice that permanent as you pay the total cost" -
    and what is sacrificed is sacrificed (CR 701.21a), so the same two events
    fire as when an effect does it.

    The cost route used to destroy instead of sacrifice, which is CR 701.8b's
    line in the sand: "The only ways a permanent can be destroyed are as a
    result of an effect that uses the word 'destroy' or as a result of the
    state-based actions..." - a cost is neither, and a destruction would have
    refused an indestructible permanent outright rather than sacrificing it.

    The two watchers are named apart so the stack shows their order: the
    sacrifice event fires first, because the move to the graveyard is what
    causes the death (the same order the Dragon Appeasement test above
    reads off two real cards).
    """
    scenario = board(["Mishra's Bauble"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bauble = scenario.find("Mishra's Bauble", Zone.BATTLEFIELD)
    for event, text, source in [
        (
            TriggerEvent.IS_SACRIFICED,
            "Whenever a permanent is sacrificed, note it.",
            "the sacrifice watcher",
        ),
        (TriggerEvent.DIES, "When this artifact dies, note it.", "the dies watcher"),
    ]:
        scenario.game.create_delayed_trigger(
            DelayedTrigger(
                text=text,
                effect=SacrificeSubject(),
                event=event,
                controller="alice",
                source_name=source,
            )
        )

    scenario.activate(bauble, sacrificing=[bauble], targets=["bob"])

    assert bauble.zone is Zone.GRAVEYARD
    assert scenario.stack_names() == [
        "Mishra's Bauble's activated ability",
        "the sacrifice watcher's triggered ability",
        "the dies watcher's triggered ability",
    ]


# -- draws made by spell effects (CR 121.2) ----------------------------------


def test_a_spells_effect_draw_fires_one_draw_event_per_card():
    """CR 121.2 for the effect-mediated path: Preordain's "then draw a card"
    goes through the same individual draws as the draw step does.

    The scry 2 before it is a question with a default, not a draw, and moves
    no card into a hand - so one card drawn is exactly one event. This is the
    wiring under test: the spell's effect reads the game's `draw_cards`, so
    what triggers is the same CR 121.2 machinery the draw step uses. The
    watcher goes on the stack as the spell finishes resolving and a player
    would next receive priority (CR 603.3).
    """
    scenario = board(["Island"], hand=["Preordain"]).build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    (island,) = scenario.untapped_sources("Island", username="alice")
    watcher(scenario, TriggerEvent.DRAWS_A_CARD, "Whenever you draw a card, note it.")

    scenario.cast_and_resolve("Preordain", island, username="alice")

    assert scenario.stack_names() == ["a resolving spell's triggered ability"]
