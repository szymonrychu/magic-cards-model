"""Scenario: delayed triggered abilities (CR 603.7).

An ordinary triggered ability is printed on a card and `machines/triggers.py`
reads it off the oracle text. A delayed one is printed nowhere: an effect
creates it, it waits for its trigger event, and then it goes on the stack like
any other trigger. "At the beginning of the next end step, sacrifice it" is the
shape; warp's exile (CR 702.185a) and Emrakul's extra turn are the two the
engine needs it for.

The rules this file asserts, every one of them looked up with
`knowledge_search(q=..., type="rules")` in the session that wrote it and then
read in full out of the 2026-08-19 Comprehensive Rules, because the search
excerpts truncate at roughly 150 characters:

- **CR 603.7** - an effect may create a delayed triggered ability that does
  something at a later time.
- **CR 603.7a** - "A delayed triggered ability won't trigger until it has
  actually been created, even if its trigger event occurred just beforehand."
- **CR 603.7b** - "A delayed triggered ability will trigger only once - the next
  time its trigger event occurs - unless it has a stated duration."
- **CR 603.7c** - "if that object is no longer in the zone it's expected to be in
  at the time the delayed triggered ability resolves, the ability won't affect
  it."
- **CR 603.7d/e** - the source and controller are those of the spell or ability
  that created it, taken as it resolved. CR 603.3a excepts delayed triggers from
  the usual controller rule and points here.
- **CR 603.3** - once it has triggered it goes on the stack the next time a
  player would receive priority, like every other trigger.
- **CR 608.2n** - and it is removed from the stack when it resolves.
- **CR 500.7** - extra turns are added directly after the specified turn, most
  recently created first, which is why Emrakul's has to be granted late.
- **CR 701.21a** - "To sacrifice a permanent, its controller moves it from the
  battlefield directly to its owner's graveyard."

`machines/delayed.py` holds the machinery and `Game.create_delayed_trigger` is
the way in, which is what `machines/effects.py` will call from a resolving spell.
The abilities here are created through that API rather than by a card, because
no card in the pool has a delayed trigger the engine can read yet - warp's is a
keyword, not printed text, and needs `machines/casting.py` to record that the
warp cost was paid. See `docs/engine-coverage.md`.
"""

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import TriggerEvent
from magic_cards_model.machines.delayed import DelayedTrigger, GrantExtraTurn, SacrificeSubject
from magic_cards_model.models import Zone
from tests.scenarios.harness import Scenario


def board() -> Scenario:
    """Two players, a Bear each, and nothing that acts on its own."""
    return (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", library=["Forest"], battlefield=["Grizzly Bears", "Forest"])
        .player("bob", library=["Island"], battlefield=["Watchwolf", "Island"])
    )


def sacrifice_at_next_end_step(scenario, permanent, controller: str) -> DelayedTrigger:
    """ "At the beginning of the next end step, sacrifice it."

    The commonest delayed trigger in the game, and the one evoke's cousin
    templates print verbatim. CR 603.7d/e give it the creating spell's
    controller, which is why that is an argument rather than read off the
    permanent.
    """
    return scenario.game.create_delayed_trigger(
        DelayedTrigger(
            text="At the beginning of the next end step, sacrifice it.",
            effect=SacrificeSubject(),
            event=TriggerEvent.BEGINNING_OF_STEP,
            step=Step.END_STEP,
            controller=controller,
            source_name="a resolving spell",
            subject_id=permanent.id,
            expected_zone=Zone.BATTLEFIELD,
        )
    )


def run_to_end_step(scenario) -> None:
    """Advance until the end step has begun and everything has resolved.

    `advance` is what emits CR 500.6's "a step began" event, so the turn has to
    be walked rather than jumped to - `start_at` moves the turn machine directly
    and fires nothing.
    """
    while scenario.step is not Step.END_STEP:
        scenario.advance()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()


def next_turn(scenario) -> None:
    """Walk on into the following turn, resolving whatever fires."""
    turns = scenario.turn.turns_taken
    while scenario.turn.turns_taken == turns:
        scenario.advance()
        while not scenario.game.stack_is_empty:
            scenario.resolve_top()


# --------------------------------------------------------------------------
# The happy path
# --------------------------------------------------------------------------


def test_a_delayed_trigger_fires_at_the_step_it_was_told_to_wait_for():
    """CR 603.7: "an effect may create a delayed triggered ability that can do
    something at a later time"."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    sacrifice_at_next_end_step(scenario, bears, "alice")
    run_to_end_step(scenario)

    assert bears.zone is Zone.GRAVEYARD


def test_it_does_nothing_until_its_event_happens():
    """CR 603.2: "the ability doesn't do anything at this point".

    Created in the precombat main phase, it sits there through combat. Nothing
    is on the stack and nothing has been sacrificed.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    sacrifice_at_next_end_step(scenario, bears, "alice")
    while scenario.step is not Step.POSTCOMBAT_MAIN:
        scenario.advance()

    assert bears.zone is Zone.BATTLEFIELD
    assert scenario.stack_names() == []


def test_it_goes_on_the_stack_as_an_ability_and_can_be_responded_to():
    """CR 603.3, CR 113.1c: it is an object on the stack like any other trigger.

    So it is visible before it resolves, which is the window a response would
    use, and CR 608.2n takes it off the stack afterwards leaving nothing behind.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    sacrifice_at_next_end_step(scenario, bears, "alice")
    while scenario.step is not Step.END_STEP:
        scenario.advance()

    (ability,) = scenario.game.abilities_on_stack
    assert ability.controller == "alice"
    assert bears.zone is Zone.BATTLEFIELD, "it has triggered, it has not resolved"

    scenario.resolve_top()

    assert scenario.game.stack == []
    assert bears.zone is Zone.GRAVEYARD


# --------------------------------------------------------------------------
# When it may trigger: CR 603.7a and CR 603.7b
# --------------------------------------------------------------------------


def test_an_event_that_already_happened_does_not_count():
    """CR 603.7a: "A delayed triggered ability won't trigger until it has
    actually been created, even if its trigger event occurred just beforehand."

    Created *during* the end step, after that step's beginning has already been
    and gone. It waits for the next end step - the following player's - rather
    than firing on the one it was born in.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    while scenario.step is not Step.END_STEP:
        scenario.advance()
    sacrifice_at_next_end_step(scenario, bears, "alice")

    assert scenario.game.stack == [], "the step had already begun"
    assert bears.zone is Zone.BATTLEFIELD

    next_turn(scenario)
    run_to_end_step(scenario)

    assert bears.zone is Zone.GRAVEYARD


def test_it_triggers_only_once():
    """CR 603.7b: "will trigger only once - the next time its trigger event
    occurs - unless it has a stated duration, such as 'this turn'."

    The Bear is gone after the first end step. The store is empty afterwards, so
    the second end step has nothing left to fire - which is the assertion that
    would fail if the ability had merely found nothing to affect.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    sacrifice_at_next_end_step(scenario, bears, "alice")
    run_to_end_step(scenario)
    assert bears.zone is Zone.GRAVEYARD

    next_turn(scenario)
    run_to_end_step(scenario)

    assert scenario.game.delayed_triggers.triggers == []


def test_an_ability_told_to_wait_for_one_players_turn_ignores_everyone_elses():
    """ "After that turn" is one particular turn, not the next end step anywhere.

    Emrakul, the Promised End's second sentence needs this: the extra turn comes
    after the turn its victim takes, and the victim's turn is not the one the
    spell was cast in. Alice's end step passes it by; bob's fires it.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wolf = scenario.creature("Watchwolf", "bob")

    scenario.game.create_delayed_trigger(
        DelayedTrigger(
            text="At the beginning of bob's next end step, sacrifice it.",
            effect=SacrificeSubject(),
            event=TriggerEvent.BEGINNING_OF_STEP,
            step=Step.END_STEP,
            controller="bob",
            source_name="a resolving spell",
            subject_id=wolf.id,
            expected_zone=Zone.BATTLEFIELD,
            only_when_active="bob",
        )
    )

    run_to_end_step(scenario)  # alice's end step
    assert wolf.zone is Zone.BATTLEFIELD

    next_turn(scenario)
    run_to_end_step(scenario)  # bob's end step

    assert wolf.zone is Zone.GRAVEYARD


# --------------------------------------------------------------------------
# What it may affect: CR 603.7c
# --------------------------------------------------------------------------


def test_it_does_not_affect_an_object_that_left_the_zone_it_was_expected_in():
    """CR 603.7c: "if that object is no longer in the zone it's expected to be in
    at the time the delayed triggered ability resolves, the ability won't affect
    it."

    The rule's own example is warp's: "An ability that reads 'Exile this creature
    at the beginning of the next end step' will exile the permanent even if it's
    no longer a creature during the next end step. However, it won't do anything
    if the permanent left the battlefield before then."
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    sacrifice_at_next_end_step(scenario, bears, "alice")
    scenario.game.exile_permanent(bears)
    assert bears.zone is Zone.EXILE

    run_to_end_step(scenario)

    assert bears.zone is Zone.EXILE, "the ability resolved and affected nothing"
    assert scenario.game.stack == []


def test_it_still_triggers_even_when_it_can_affect_nothing():
    """CR 603.7c stops the *effect*, not the trigger.

    The ability triggers, goes on the stack, and resolves; CR 608.2n removes it.
    Only the part that would have touched the object is skipped. That matters
    because a real card's delayed trigger often does something else as well.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "alice")

    sacrifice_at_next_end_step(scenario, bears, "alice")
    scenario.game.exile_permanent(bears)

    while scenario.step is not Step.END_STEP:
        scenario.advance()

    assert len(scenario.game.abilities_on_stack) == 1
    scenario.resolve_top()
    assert scenario.game.stack == []


def test_it_affects_the_object_it_named_and_not_a_twin_of_it():
    """CR 603.7c refers to "a particular object", and two Bears are two objects.

    The delayed trigger was aimed at one of them by id; the other is not
    something it can reach, however identical the printing.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player(
            "alice",
            library=["Forest"],
            battlefield=["Grizzly Bears", "Grizzly Bears", "Forest"],
        )
        .player("bob", library=["Island"], battlefield=["Island"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    first, second = scenario.creatures("Grizzly Bears", "Grizzly Bears", username="alice")

    sacrifice_at_next_end_step(scenario, second, "alice")
    run_to_end_step(scenario)

    assert first.zone is Zone.BATTLEFIELD
    assert second.zone is Zone.GRAVEYARD


# --------------------------------------------------------------------------
# Who controls it: CR 603.7d, CR 603.7e
# --------------------------------------------------------------------------


def test_the_controller_is_the_one_who_created_it_not_the_object_it_affects():
    """CR 603.7d: "The controller of that delayed triggered ability is the player
    who controlled that spell as it resolved."

    CR 603.3a is the rule this is an exception to: an ordinary trigger belongs to
    whoever controlled its source when it triggered. A delayed one does not ask.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    wolf = scenario.creature("Watchwolf", "bob")

    sacrifice_at_next_end_step(scenario, wolf, "alice")
    while scenario.step is not Step.END_STEP:
        scenario.advance()

    (ability,) = scenario.game.abilities_on_stack

    assert ability.controller == "alice", "bob's creature, alice's ability"


# --------------------------------------------------------------------------
# Granting an extra turn late, which is the whole point of CR 500.7 ordering
# --------------------------------------------------------------------------


def test_an_extra_turn_granted_by_a_delayed_trigger_comes_after_the_turn_it_waited_for():
    """CR 500.7 through CR 603.7: why Emrakul's extra turn cannot be granted early.

    "Some effects can give a player extra turns. They do this by adding the turns
    directly after the specified turn. ... The most recently created turn will be
    taken first."

    Emrakul's controller takes bob's turn for him and *then* bob takes an extra
    one. Granting it while the cast trigger resolves would insert it directly
    after alice's turn - before the turn being stolen - and bob would take his
    extra turn first, which is not what the card does. Waiting for the end of
    bob's turn puts it where CR 500.7 says it goes.
    """
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.game.create_delayed_trigger(
        DelayedTrigger(
            text="After that turn, that player takes an extra turn.",
            effect=GrantExtraTurn(),
            event=TriggerEvent.BEGINNING_OF_STEP,
            step=Step.END_STEP,
            controller="alice",
            source_name="Emrakul, the Promised End",
            subject_player="bob",
            only_when_active="bob",
        )
    )

    run_to_end_step(scenario)  # alice's end step: not bob's turn, nothing fires
    assert scenario.turn.extra_turns == []

    next_turn(scenario)  # bob's turn
    assert scenario.turn.active_player == "bob"
    run_to_end_step(scenario)

    assert scenario.turn.extra_turns == ["bob"], "granted at the end of bob's turn"

    next_turn(scenario)

    assert scenario.turn.active_player == "bob"
    assert scenario.turn.taking_extra_turn


# --------------------------------------------------------------------------
# Gaps
# --------------------------------------------------------------------------


def test_a_card_creates_its_own_delayed_trigger():
    """The integration this whole file works around.

    Everything above builds the ability through `Game.create_delayed_trigger`,
    which is the API `machines/effects.py` and `Game.resolve_top` use. What is
    missing is a card whose text or keyword reaches that call on its own.
    """
    scenario = (
        Scenario()
        .manual_turn_based_actions()
        .player("alice", library=["Island"], battlefield=["Island"] * 3, hand=["Bygone Colossus"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    sources = scenario.untapped_sources("Island", "Island", "Island")
    casting = scenario.cast("Bygone Colossus")
    casting.use_keyword("Warp")
    scenario.pay_with(casting.begin_paying(), *sources)
    scenario.put_on_stack(casting)
    scenario.resolve_top()

    assert scenario.game.delayed_triggers.triggers, "warp created its delayed trigger"
