"""Who chooses the order objects go onto the stack.

Every rule number here was looked up with `knowledge_search(type="rules")` in
the session that wrote this file.

- **CR 405.2** - "The stack keeps track of the order that spells and/or
  abilities were added to it. Each time an object is put on the stack, it's put
  on top of all objects already there." The order is settled *as* objects go on.
- **CR 400.5** - "The order of objects in a library, in a graveyard, or on the
  stack can't be changed except when effects or rules allow it." So there is no
  window in which a player may rearrange a stack that has already been built.
  The agency a player has over stack order is exercised while the stack is
  being built, and nowhere else.
- **CR 603.3b** - "If multiple abilities have triggered since the last time a
  player received priority, the abilities are placed on the stack in a two-part
  process. First, each player, in APNAP order, puts each triggered ability they
  control on the stack in any order they choose." Two halves: APNAP decides
  which *player's* block goes on first, and the player decides the order
  *within* their own block. The active player's block goes on lowest and so
  resolves last.
- **CR 405.3** - "If an effect puts two or more objects on the stack at the
  same time, those controlled by the active player are put on lowest, followed
  by each other player's objects in APNAP order." The same direction as
  CR 603.3b's first half, for objects an effect puts on rather than triggers.
- **CR 503.1a** - "Any abilities that triggered during the untap step and any
  abilities that triggered at the beginning of the upkeep are put onto the
  stack before the active player gets priority" - one batch, not two, which is
  what makes a held untap trigger and an upkeep trigger a single CR 603.3b
  choice.
- **CR 502.4** - "No player receives priority during the untap step ... Any
  ability that triggers during this step will be held until the next time a
  player would receive priority."
- **CR 510.3a** - "Any abilities that triggered on damage being dealt or while
  state-based actions are performed afterward are put onto the stack before the
  active player gets priority" - the combat damage step flushes its own batch,
  and it is still a CR 603.3b batch.

Every test here asserts on **resolution order** - what has happened to the
board after the top object resolved and before the next one does - not on the
question having been asked. A test that only checks the question appeared
passes just as well when the answer is thrown away.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.decisions import Decision, DecisionKind
from magic_cards_model.models import Zone
from magic_cards_model.models.token import TokenState
from tests.scenarios.harness import PlayedScenario, Scenario

LIBRARY = ["Forest"] * 12
"""Enough cards that walking several turns never empties a library (CR 704.5b)."""


def order_questions(scenario: PlayedScenario) -> list[Decision]:
    """Every CR 603.3b ordering question put so far, in order."""
    return [
        question
        for question in scenario.questions_asked()
        if question.kind is DecisionKind.ORDER_TRIGGERS
    ]


# --------------------------------------------------------------------------
# A run of one is not a choice (CR 603.3b)
# --------------------------------------------------------------------------


def test_a_single_trigger_asks_nobody_which_order_it_goes_in():
    """One ability has exactly one order, so nothing is put to anybody.

    CR 603.3b's "in any order they choose" is a choice only when a player has
    more than one ability to order. Goblin Guide attacks alone; its trigger
    goes on the stack and resolves, and no ordering question was ever raised.
    """
    scenario = (
        Scenario()
        .player("alice", battlefield=["Goblin Guide"])
        .player("bob", library=["Forest"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(scenario.creature("Goblin Guide", "alice"))

    assert order_questions(scenario) == []
    assert scenario.stack_names() == ["Goblin Guide's triggered ability"]

    scenario.resolve_top()
    assert [card.name for card in scenario.player("bob").hand] == ["Forest"]


def test_one_trigger_each_is_no_choice_for_either_player():
    """Two controllers with one ability apiece is still nobody's choice.

    CR 603.3b's second half is per player, so a block of one is not a choice
    even when the batch as a whole holds several abilities. What settles their
    relative order is APNAP, which is the rules' business and not a player's -
    so nothing is asked here either.
    """
    scenario = two_hounds()
    assert len(scenario.game.abilities_on_stack) == 2
    assert order_questions(scenario) == []


# --------------------------------------------------------------------------
# Two controllers: APNAP, and the active player resolving last
# --------------------------------------------------------------------------


def test_the_active_players_trigger_resolves_last():
    """CR 603.3b's first half, asserted on which Hound dies first.

    Ashmouth Hound is a 2/1 with "Whenever this creature blocks or becomes
    blocked by a creature, this creature deals 1 damage to that creature", so
    each trigger kills the other Hound outright (CR 704.5g's lethal damage).
    alice is the active player, so her ability goes on the stack *lowest* and
    bob's resolves first - which means alice's Hound is in the graveyard while
    bob's is still on the battlefield, and only the second resolution evens it
    up. CR 113.7a is why alice's ability still resolves at all: "once activated
    or triggered, an ability exists on the stack independently of its source."
    """
    scenario = two_hounds()
    attacker = scenario.creature("Ashmouth Hound", "alice")
    blocker = scenario.creature("Ashmouth Hound", "bob")

    first = scenario.resolve_top()
    assert first.controller == "bob"
    assert attacker.zone is Zone.GRAVEYARD
    assert blocker.zone is Zone.BATTLEFIELD

    second = scenario.resolve_top()
    assert second.controller == "alice"
    assert blocker.zone is Zone.GRAVEYARD


def two_hounds() -> PlayedScenario:
    """alice's Hound attacks into bob's, so both sides trigger on one event."""
    scenario = (
        Scenario()
        .player("alice", library=list(LIBRARY), battlefield=["Ashmouth Hound"])
        .player("bob", library=list(LIBRARY), battlefield=["Ashmouth Hound"])
        .build()
    )
    scenario.start_at(Step.DECLARE_BLOCKERS)
    attacker = scenario.creature("Ashmouth Hound", "alice")
    scenario.attack_with(attacker)
    scenario.block(attacker, scenario.creature("Ashmouth Hound", "bob"))
    return scenario


def test_three_seats_put_their_blocks_on_in_turn_order_from_the_active_player():
    """CR 603.3b's APNAP, and CR 101.4's turn order, with three players.

    Every Chalice of the Void has one charge counter, so alice's Lightning Bolt
    (mana value 1) triggers all four of them at once - two of alice's, one of
    bob's, one of carol's. APNAP puts alice's block on lowest, then bob's, then
    carol's, so carol's resolves first and counters the Bolt (CR 701.6a), and
    the two blocks alice and bob control resolve afterwards with nothing left
    to counter.

    Only alice is asked anything: hers is the only block longer than one.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Chalice of the Void", "Chalice of the Void", "Mountain"],
            hand=["Lightning Bolt"],
            library=list(LIBRARY),
        )
        .player("bob", battlefield=["Chalice of the Void"], library=list(LIBRARY))
        .player("carol", battlefield=["Chalice of the Void"], library=list(LIBRARY))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    for chalice in scenario.game.battlefield:
        if chalice.name == "Chalice of the Void":
            chalice.add_counters("charge", 1)

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, targets=[scenario.player("bob")])

    (question,) = order_questions(scenario)
    assert question.player == "alice"
    assert len(question.cards) == 2

    first = scenario.resolve_top()
    assert first.controller == "carol"
    assert bolt.zone is Zone.GRAVEYARD, "carol's resolved first and countered it"
    assert scenario.player("bob").life == 20

    rest = [scenario.resolve_top() for _ in range(3)]
    assert [item.controller for item in rest] == ["bob", "alice", "alice"]
    assert scenario.game.stack_is_empty


def test_the_question_names_the_sources_it_is_offering():
    """A live seat has to be able to tell the two abilities apart.

    `Decision.cards` for this kind holds `AbilityOnStack` ids, and CR 113.1c
    plus CR 405.1 are why nothing can put a name to them from the board: an
    ability on the stack "is an object" that "goes on top of the stack without
    any card associated with it", so a lookup over the cards in play finds
    nothing. The prompt carries the printed sources instead, numbered against
    `cards`, which is the only thing standing between a live player and a
    choice between two anonymous ids.
    """
    scenario = combat_damage_board()

    (question,) = order_questions(scenario)
    assert question.prompt.endswith("1. Psychic Frog, 2. Ragavan, Nimble Pilferer")
    assert "bottom of the stack first" in question.prompt


def test_two_triggers_of_the_same_printed_source_cannot_be_named_apart():
    """A scripted answer names printed sources, so two of one card are refused.

    `machines/decisions._resolve_trigger_order` refuses a name matching more
    than one of the abilities offered rather than guessing which is which -
    "two triggers of the same permanent are two orderings and the answer would
    not have said which is which". A live seat answering by ability id (which
    is what the API's `order_triggers` decision carries) has no such problem;
    this is a limit of naming things that do not exist yet, not of the rule.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Chalice of the Void", "Chalice of the Void", "Mountain"],
            hand=["Lightning Bolt"],
            library=list(LIBRARY),
        )
        .player("bob", library=list(LIBRARY))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    for chalice in scenario.game.battlefield:
        if chalice.name == "Chalice of the Void":
            chalice.add_counters("charge", 1)
    scenario.will_order_triggers("Chalice of the Void", "Chalice of the Void", username="alice")

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    with pytest.raises(ValueError, match="names 2 of the abilities offered"):
        scenario.cast_onto_stack("Lightning Bolt", mountain, targets=[scenario.player("bob")])


# --------------------------------------------------------------------------
# Two triggers, one controller, in a batch the combat damage step flushes
# (CR 510.3a, CR 603.3b)
# --------------------------------------------------------------------------


def test_an_unscripted_controller_keeps_the_order_the_abilities_triggered_in():
    """Nobody choosing means the order they triggered in, and it is honoured.

    Psychic Frog and Ragavan connect in the same combat damage step, so
    CR 510.3a puts both triggers on before alice gets priority and CR 603.3b
    makes that one choice of hers. Unscripted, `machines/decisions.
    default_answer` hands the offered order back unchanged: the Frog triggered
    first, so its ability is lowest and Ragavan's resolves first.

    Asserted on the board between the two resolutions - the Treasure exists and
    alice has drawn nothing yet.
    """
    scenario = combat_damage_board()

    (question,) = order_questions(scenario)
    assert question.player == "alice"
    assert len(question.cards) == 2

    first = scenario.resolve_top()
    assert first.source_name == "Ragavan, Nimble Pilferer"
    assert treasures(scenario) == 1
    assert scenario.player("alice").hand == []

    second = scenario.resolve_top()
    assert second.source_name == "Psychic Frog"
    assert [card.name for card in scenario.player("alice").hand] == ["Forest"]


def test_the_controller_can_put_their_other_trigger_on_top_instead():
    """The same batch, ordered the other way, resolves the other way round.

    `will_order_triggers` names the block bottom of the stack first, so naming
    Ragavan first puts *his* ability lowest and leaves the Frog's on top. alice
    has drawn her card before any Treasure exists - the half a test that only
    asserted "the question was asked" would have passed without.
    """
    scenario = combat_damage_board(order=("Ragavan, Nimble Pilferer", "Psychic Frog"))

    first = scenario.resolve_top()
    assert first.source_name == "Psychic Frog"
    assert [card.name for card in scenario.player("alice").hand] == ["Forest"]
    assert treasures(scenario) == 0

    second = scenario.resolve_top()
    assert second.source_name == "Ragavan, Nimble Pilferer"
    assert treasures(scenario) == 1


def test_naming_the_order_the_abilities_already_had_changes_nothing():
    """The identity answer is still an answer, and lands the identity order."""
    scenario = combat_damage_board(order=("Psychic Frog", "Ragavan, Nimble Pilferer"))

    first = scenario.resolve_top()
    assert first.source_name == "Ragavan, Nimble Pilferer"
    assert scenario.player("alice").hand == []


def combat_damage_board(
    order: tuple[str, ...] | None = None, *, with_bolt: bool = False
) -> PlayedScenario:
    """alice's two creatures connect unblocked, in one combat damage step.

    The ordering answer, if any, is queued *before* the damage is dealt: the
    abilities do not exist until then, which is why `will_order_triggers` names
    their printed sources rather than their ids.
    """
    battlefield = ["Psychic Frog", "Ragavan, Nimble Pilferer"]
    if with_bolt:
        battlefield = [*battlefield, "Mountain"]
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=battlefield,
            hand=["Lightning Bolt"] if with_bolt else [],
            library=["Forest"],
        )
        .player("bob", library=list(LIBRARY))
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    scenario.attack_with(
        scenario.creature("Psychic Frog", "alice"),
        scenario.creature("Ragavan, Nimble Pilferer", "alice"),
    )
    scenario.advance()  # declare blockers
    scenario.no_blocks()
    if order is not None:
        scenario.will_order_triggers(*order, username="alice")
    scenario.advance()  # combat damage: CR 510.2 deals it, CR 510.3a stacks the triggers
    return scenario


def treasures(scenario: PlayedScenario) -> int:
    return len(
        [
            state
            for state in scenario.game.battlefield
            if isinstance(state, TokenState) and state.name == "Treasure Token"
        ]
    )


# --------------------------------------------------------------------------
# A batch the untap step held over (CR 502.4, 503.1a, 603.3b)
# --------------------------------------------------------------------------


def test_a_held_untap_trigger_and_an_upkeep_trigger_are_one_choice():
    """CR 502.4 holds it, CR 503.1a puts both on together, CR 603.3b orders them.

    "Any ability that triggers during this step will be held until the next
    time a player would receive priority" (CR 502.4), and "Any abilities that
    triggered during the untap step and any abilities that triggered at the
    beginning of the upkeep are put onto the stack before the active player
    gets priority" (CR 503.1a). One batch, so alice is asked once about both.
    Were the held one flushed on its own, each block would be a run of one and
    the choice would be silently skipped - the failure this test exists for.

    Deepwater Hypnotist is tapped on bob's turn so CR 502.3 untaps it on
    alice's, firing its inspired trigger inside the step that has no priority;
    Ajani's Mantra's "At the beginning of your upkeep, you may gain 1 life" is
    the upkeep half. Unscripted, the untap trigger keeps the lower slot it
    triggered into, so the Mantra resolves first and alice is on 21 before the
    inspired ability resolves at all.
    """
    scenario = untap_and_upkeep_board()

    (question,) = order_questions(scenario)
    assert question.player == "alice"
    assert [item.source_name for item in scenario.game.abilities_on_stack] == [
        "Deepwater Hypnotist",
        "Ajani's Mantra",
    ]

    first = scenario.resolve_top()
    assert first.source_name == "Ajani's Mantra"
    assert scenario.player("alice").life == 21

    second = scenario.resolve_top()
    assert second.source_name == "Deepwater Hypnotist"


def test_the_held_untap_trigger_can_be_put_on_top_of_the_upkeep_one():
    """The same batch, ordered the other way, resolves the other way.

    Named bottom of the stack first, so Ajani's Mantra goes on lowest and the
    inspired trigger resolves first: alice is still on 20 life when the untap
    trigger has already resolved, and only reaches 21 afterwards.

    Deepwater Hypnotist's own "-3/-0 until end of turn" is not applied by this
    engine (`docs/engine-coverage.md` records the gap), so the life total is
    what makes the order visible here rather than bob's Grizzly Bears shrinking.
    """
    scenario = untap_and_upkeep_board(order=("Ajani's Mantra", "Deepwater Hypnotist"))

    first = scenario.resolve_top()
    assert first.source_name == "Deepwater Hypnotist"
    assert scenario.player("alice").life == 20

    second = scenario.resolve_top()
    assert second.source_name == "Ajani's Mantra"
    assert scenario.player("alice").life == 21


def untap_and_upkeep_board(order: tuple[str, ...] | None = None) -> PlayedScenario:
    """Walk to alice's next untap step with the Hypnotist tapped, then to upkeep.

    Stepped rather than jumped, because CR 502.3's untapping is the event that
    fires the held trigger.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            battlefield=["Deepwater Hypnotist", "Ajani's Mantra"],
            library=list(LIBRARY),
        )
        .player("bob", battlefield=["Grizzly Bears"], library=list(LIBRARY))
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    scenario.creature("Deepwater Hypnotist", "alice").tap()
    scenario.start_at(Step.END_STEP)
    while not (scenario.step is Step.UNTAP and scenario.turn.active_player == "alice"):
        scenario.advance()

    assert [item.source_name for item in scenario.pending_triggers] == ["Deepwater Hypnotist"]
    if order is not None:
        scenario.will_order_triggers(*order, username="alice")
    scenario.advance()  # upkeep
    return scenario


# --------------------------------------------------------------------------
# The stack, once built, is not rearranged (CR 400.5, 405.2)
# --------------------------------------------------------------------------


def test_a_spell_cast_on_top_leaves_the_order_below_it_untouched():
    """CR 405.2 and CR 400.5 together: there is no second bite at the ordering.

    "Each time an object is put on the stack, it's put on top of all objects
    already there" (CR 405.2), and "the order of objects ... on the stack can't
    be changed except when effects or rules allow it" (CR 400.5). alice orders
    her two triggers as they go on; a Lightning Bolt cast afterwards goes
    strictly on top and resolves first, and the two triggers underneath still
    resolve in the order she chose. Nothing lets her - or anyone else - reopen
    that order because a spell was cast.
    """
    scenario = combat_damage_board(
        order=("Ragavan, Nimble Pilferer", "Psychic Frog"), with_bolt=True
    )
    below = scenario.stack_names()
    life_before = scenario.player("bob").life

    (mountain,) = scenario.untapped_sources("Mountain", username="alice")
    bolt = scenario.cast_onto_stack("Lightning Bolt", mountain, targets=[scenario.player("bob")])
    assert scenario.stack_names() == [*below, "Lightning Bolt"]

    assert scenario.resolve_top() is bolt
    assert scenario.player("bob").life == life_before - 3
    assert bolt.zone is Zone.GRAVEYARD
    assert scenario.stack_names() == below

    assert scenario.resolve_top().source_name == "Psychic Frog"
    assert scenario.resolve_top().source_name == "Ragavan, Nimble Pilferer"
