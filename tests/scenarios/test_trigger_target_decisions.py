"""Scenario: a triggered ability's controller is asked for its targets (CR 603.3d).

The defect this file is written against: a trigger that requires a target used
to go on the stack with `targets: []` unconditionally, because
`Game.put_triggers_on_stack` read a `dict[str, list[TargetRef]]` keyed by the
source's card *name* and defaulted to empty when nobody had pre-populated it
for that name out of band. Nothing in production ever populated it, so every
targeted trigger no-opped. The dict also had three further bugs, all sharing
the same root cause (state keyed by name instead of by ability instance):
entries were never consumed (a stale choice could be reused by a later,
unrelated trigger of the same name), two copies of one card could not be
targeted separately, and a delayed triggered ability inherited whatever the
name-keyed lookup last held, ignoring `ability.controller` entirely.

The fix, all in `Game.put_triggers_on_stack` / `Game._ask_trigger_targets`:
each ability instance is now asked, through `Game.ask`, for its own targets,
addressed to its own controller, before it is appended to the stack (CR
603.3d: "the remainder of the process for putting a triggered ability on the
stack is identical to the process for casting a spell listed in rules
601.2c-d" - `601.2c-601.2d` are looked up in `test_triggered_abilities.py` and
elsewhere in this suite already). `DecisionKind.CHOOSE_TARGETS` is the new
question kind; its candidates are worked out by
`machines/targeting.py`'s own `TargetRequirement.rejects` - the same checker
`activate_ability` already uses - so this file does not grow a second target
grammar. The default answer is empty, byte-identical to the behaviour the
dict produced, which is why no test written before this file moved.

`Game.choose_trigger_targets` (the `~34`-call-site scripting helper every
other scenario file uses) still exists and is still keyed by card name: it
stages a `DecisionScript` answer that every ability sharing that name hears
while it is being put on the stack in the *same* batch (Ugin, Eye of the
Storms genuinely prints two "when you cast this spell"-shaped lines that both
fire off one casting, and both used to share the dict entry by name - that
part of the old behaviour is real and kept), but `put_triggers_on_stack`
throws the answer away once the batch is done, so a later, separate trigger of
the same name cannot see a stale one. Telling two *simultaneous* instances of
the same name apart - the two-copies and controller-respecting cases below -
is a production capability with no test-harness shorthand, so those tests
drive `Game.ask` directly through a `DecisionProvider` stub instead, which is
exactly the shape a live player's answer takes (see `machines/decisions.py`).
"""

from dataclasses import dataclass, field

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.abilities import TriggerEvent
from magic_cards_model.machines.decisions import (
    NOT_ANSWERED,
    Decision,
    DecisionKind,
)
from magic_cards_model.machines.delayed import DelayedTrigger
from magic_cards_model.machines.triggers import GameEvent
from magic_cards_model.models import Zone
from magic_cards_model.models.card_state import TargetRef
from tests.scenarios.harness import Scenario


@dataclass
class QueueProvider:
    """A `DecisionProvider` that answers `CHOOSE_TARGETS` questions in order.

    Not a mock: it is a real implementation of the one-method `DecisionProvider`
    protocol `Game.ask` already calls, standing in for what a live player at a
    keyboard would be behind. `asked` records every `Decision` it was handed,
    which is how a test proves *which* controller a question was addressed to.
    """

    answers: list[tuple[object, ...]] = field(default_factory=list)
    asked: list[Decision] = field(default_factory=list)

    def decide(self, decision: Decision) -> object:
        self.asked.append(decision)
        if decision.kind is not DecisionKind.CHOOSE_TARGETS or not self.answers:
            return NOT_ANSWERED
        return self.answers.pop(0)


def _devourer_board() -> Scenario:
    return (
        Scenario()
        .player(
            "alice",
            library=["Forest"],
            hand=["Devourer of Destiny"],
            battlefield=["Sol Ring"] + ["Forest"] * 5,
        )
        .player("bob", library=["Forest"], battlefield=["Grizzly Bears", "Watchwolf"])
    )


# -- the reported case: Devourer of Destiny's cast trigger ----------------


def test_devourer_of_destinys_cast_trigger_exiles_the_chosen_target():
    """alice taps for 8, casts Devourer of Destiny, and is asked for a target.

    This is the playtest bug verbatim: previously the trigger went on the
    stack with `targets: []` and resolved exiling nothing, because nobody ever
    populated the name-keyed dict `_targets_for_trigger` read. It is now asked
    through `Game.ask`, with no script staged, purely through a
    `DecisionProvider` - the shape a real seat's answer takes.
    """
    scenario = _devourer_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    provider = QueueProvider(answers=[(bears,)])
    scenario.game.decisions.provider = provider

    sources = scenario.untapped_sources("Sol Ring", *["Forest"] * 5)
    scenario.cast_onto_stack("Devourer of Destiny", *sources)

    assert len(provider.asked) == 1
    assert provider.asked[0].player == "alice"
    assert provider.asked[0].kind is DecisionKind.CHOOSE_TARGETS
    assert TargetRef.to_card(bears) in provider.asked[0].targets, "bears was offered"

    scenario.pass_until_resolved()
    assert bears.zone is Zone.EXILE


def test_choosing_a_different_legal_target_exiles_that_one_instead():
    """The answer actually drives the effect - it is not read back off a default.

    Watchwolf is offered too; choosing it rather than the Grizzly Bears is what
    proves the provider's answer, not some fallback, picked the target.
    """
    scenario = _devourer_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    watchwolf = scenario.creature("Watchwolf", "bob")
    scenario.game.decisions.provider = QueueProvider(answers=[(watchwolf,)])

    sources = scenario.untapped_sources("Sol Ring", *["Forest"] * 5)
    scenario.cast_onto_stack("Devourer of Destiny", *sources)
    scenario.pass_until_resolved()

    assert watchwolf.zone is Zone.EXILE
    assert bears.zone is Zone.BATTLEFIELD, "only the chosen target moved"


def test_no_provider_present_targets_nothing_todays_behaviour_unchanged():
    """Nobody scripted an answer and nobody is standing behind the seat.

    `default_answer` for `CHOOSE_TARGETS` is empty, byte-identical to what the
    name-keyed dict produced when nothing had populated it - this is the
    "nothing moves" guarantee the fix was built around.
    """
    scenario = _devourer_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")

    sources = scenario.untapped_sources("Sol Ring", *["Forest"] * 5)
    scenario.cast_onto_stack("Devourer of Destiny", *sources)

    (trigger,) = [item for item in scenario.game.stack if item is not scenario.game.stack[0]]
    assert trigger.targets == []

    scenario.pass_until_resolved()
    assert bears.zone is Zone.BATTLEFIELD, "no target chosen, nothing exiled"


def test_a_scripted_answer_still_beats_the_provider():
    """`Game.ask` tries the `DecisionScript` before the provider, always.

    A provider is staged that would exile Watchwolf; `choose_trigger_targets`
    stages the Grizzly Bears answer on top. The scripted answer wins.
    """
    scenario = _devourer_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    watchwolf = scenario.creature("Watchwolf", "bob")
    scenario.game.decisions.provider = QueueProvider(answers=[(watchwolf,)])
    scenario.choose_trigger_targets("Devourer of Destiny", [bears])

    sources = scenario.untapped_sources("Sol Ring", *["Forest"] * 5)
    scenario.cast_onto_stack("Devourer of Destiny", *sources)
    scenario.pass_until_resolved()

    assert bears.zone is Zone.EXILE, "the script, not the provider, was heard"
    assert watchwolf.zone is Zone.BATTLEFIELD


def test_an_illegal_target_is_refused_without_corrupting_state():
    """Ravenous Chupacabra needs "a creature an opponent controls" - its own
    controller's Watchwolf is refused.

    `choose_trigger_targets` validates through the same
    `TargetRequirement.rejects` a live ask's candidate list is built from
    (`why_cannot_target_with_trigger`), so an illegal choice is refused before
    it is ever staged - nothing is left half-set.
    """

    scenario = (
        Scenario()
        .player("alice", hand=["Ravenous Chupacabra"], battlefield=["Watchwolf"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    watchwolf = scenario.creature("Watchwolf", "alice")
    scenario.put_onto_battlefield("Ravenous Chupacabra")

    with pytest.raises(ValueError, match="which alice controls"):
        scenario.choose_trigger_targets("Ravenous Chupacabra", [watchwolf])

    assert scenario.game.decisions.answers == [], "the refused choice was never staged"
    assert len(scenario.pending_triggers) == 1, "the ETB trigger is still waiting, untouched"


# -- two copies of the same card, targeted separately (the name-keying bug) --


def test_two_copies_of_the_same_card_are_targeted_separately():
    """Two Ravenous Chupacabras enter together; each destroys a different bear.

    The old dict held one entry per *name* - two simultaneous triggers from two
    copies of the same card shared it. Here both enter in the same batch (the
    two `put_onto_battlefield` calls both just queue a pending trigger; nothing
    puts them on the stack until `put_triggers_on_stack` is called once for
    both), and a `QueueProvider` hands out two different answers - proving the
    two ability *instances*, not the shared name, are what get asked.
    """
    scenario = (
        Scenario()
        .player("alice", hand=["Ravenous Chupacabra", "Ravenous Chupacabra"])
        .player("bob", battlefield=["Grizzly Bears", "Watchwolf"])
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    watchwolf = scenario.creature("Watchwolf", "bob")
    scenario.put_onto_battlefield("Ravenous Chupacabra")
    scenario.put_onto_battlefield("Ravenous Chupacabra")
    assert len(scenario.pending_triggers) == 2, "both ETBs are waiting in one batch"

    provider = QueueProvider(answers=[(bears,), (watchwolf,)])
    scenario.game.decisions.provider = provider
    scenario.game.put_triggers_on_stack()

    while not scenario.game.stack_is_empty:
        scenario.resolve_top()

    assert bears.zone is Zone.GRAVEYARD
    assert watchwolf.zone is Zone.GRAVEYARD


def test_two_triggers_of_the_same_card_name_in_succession_each_get_a_fresh_choice():
    """The stale-entry bug: a second cast must not see the first cast's answer.

    Each cast is its own event and its own `put_triggers_on_stack` batch, so
    `choose_trigger_targets` is staged again for the second - and
    `put_triggers_on_stack` has already thrown the first batch's answer away by
    the time the second casting happens, which is what makes a leftover
    reference impossible rather than merely unlikely.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest"],
            hand=["Devourer of Destiny", "Devourer of Destiny"],
            battlefield=["Sol Ring", "Sol Ring"] + ["Forest"] * 10,
        )
        .player("bob", library=["Forest"], battlefield=["Grizzly Bears", "Watchwolf"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    watchwolf = scenario.creature("Watchwolf", "bob")

    (sol_ring_1, sol_ring_2) = scenario.untapped_sources("Sol Ring", "Sol Ring")
    scenario.choose_trigger_targets("Devourer of Destiny", [bears])
    sources = [sol_ring_1, *scenario.untapped_sources(*["Forest"] * 5)]
    scenario.cast_onto_stack("Devourer of Destiny", *sources)
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()
    assert bears.zone is Zone.EXILE
    assert scenario.game.decisions.answers == [], "the first answer did not survive its batch"

    scenario.choose_trigger_targets("Devourer of Destiny", [watchwolf])
    sources = [sol_ring_2, *scenario.untapped_sources(*["Forest"] * 5)]
    scenario.cast_onto_stack("Devourer of Destiny", *sources)
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()

    assert watchwolf.zone is Zone.EXILE, "the second cast got its own, fresh choice"


# -- a trigger controlled by each player -----------------------------------


def test_the_trigger_is_addressed_to_its_own_controller():
    """alice's Devourer asks alice; bob's Ravenous Chupacabra asks bob.

    `_ask_trigger_targets` builds the `Decision` from `ability.controller`,
    which is the per-instance value the old name-keyed lookup never consulted.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest"],
            hand=["Devourer of Destiny"],
            battlefield=["Sol Ring", "Elvish Mystic"] + ["Forest"] * 5,
        )
        .player(
            "bob",
            library=["Forest"],
            hand=["Ravenous Chupacabra"],
            battlefield=["Watchwolf", "Grizzly Bears"],
        )
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    mystic = scenario.creature("Elvish Mystic", "alice")
    provider = QueueProvider(answers=[(bears,)])
    scenario.game.decisions.provider = provider

    sources = scenario.untapped_sources("Sol Ring", *["Forest"] * 5)
    scenario.cast_onto_stack("Devourer of Destiny", *sources, username="alice")
    assert provider.asked[-1].player == "alice"

    provider.answers.append((mystic,))
    chupacabra = scenario.put_onto_battlefield("Ravenous Chupacabra", "bob")
    scenario.game.put_triggers_on_stack()
    assert provider.asked[-1].player == "bob"
    assert chupacabra.zone is Zone.BATTLEFIELD


# -- a delayed triggered ability does not inherit another trigger's targets --


def test_a_delayed_trigger_does_not_inherit_an_earlier_triggers_targets():
    """A delayed trigger sharing a card's name starts with no memory of it.

    First, an ordinary Devourer of Destiny cast trigger is scripted and fully
    resolved, exiling the Grizzly Bears - and, per the fix, its scripted answer
    is discarded once that batch is done. A *delayed* triggered ability is then
    created by hand (the same way `test_delayed_triggered_abilities.py` builds
    one - no card in the pool prints a delayed trigger with a target yet), given
    the same source name on purpose, and fired. If it inherited the old dict
    entry it would arrive with Watchwolf already targeted; instead it is asked
    fresh and, with nothing scripted or provided this time, defaults to no
    target at all.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            library=["Forest"],
            hand=["Devourer of Destiny"],
            battlefield=["Sol Ring"] + ["Forest"] * 5,
        )
        .player("bob", library=["Forest"], battlefield=["Grizzly Bears", "Watchwolf"])
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    watchwolf = scenario.creature("Watchwolf", "bob")

    scenario.choose_trigger_targets("Devourer of Destiny", [bears])
    sources = scenario.untapped_sources("Sol Ring", *["Forest"] * 5)
    scenario.cast_onto_stack("Devourer of Destiny", *sources)
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()
    assert bears.zone is Zone.EXILE

    scenario.game.create_delayed_trigger(
        DelayedTrigger(
            text="At the beginning of the next end step, exile target creature.",
            effect="unregistered_test_effect",
            event=TriggerEvent.BEGINNING_OF_STEP,
            step=Step.END_STEP,
            controller="alice",
            source_name="Devourer of Destiny",
        )
    )
    fired = scenario.game.delayed_triggers.fire(
        GameEvent(event=TriggerEvent.BEGINNING_OF_STEP, step=Step.END_STEP, player="alice")
    )
    scenario.game.pending_triggers.extend(fired)
    scenario.game.put_triggers_on_stack()

    (delayed_ability,) = scenario.game.abilities_on_stack
    assert delayed_ability.targets == [], "it did not inherit Watchwolf, or anything else"
    assert watchwolf.zone is Zone.BATTLEFIELD


# -- ETB, cast, and attack trigger shapes ------------------------------------


def test_the_etb_shape_ravenous_chupacabra():
    scenario = (
        Scenario()
        .player("alice", hand=["Ravenous Chupacabra"])
        .player("bob", battlefield=["Grizzly Bears"])
        .build()
    )
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.game.decisions.provider = QueueProvider(answers=[(bears,)])
    scenario.put_onto_battlefield("Ravenous Chupacabra")
    scenario.game.put_triggers_on_stack()
    while not scenario.game.stack_is_empty:
        scenario.resolve_top()
    assert bears.zone is Zone.GRAVEYARD


def test_the_cast_trigger_shape_devourer_of_destiny():
    scenario = _devourer_board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.creature("Grizzly Bears", "bob")
    scenario.game.decisions.provider = QueueProvider(answers=[(bears,)])
    sources = scenario.untapped_sources("Sol Ring", *["Forest"] * 5)
    scenario.cast_onto_stack("Devourer of Destiny", *sources)
    scenario.pass_until_resolved()
    assert bears.zone is Zone.EXILE


def test_the_attack_trigger_shape_alaborn_cavalier():
    scenario = (
        Scenario()
        .player("alice", battlefield=["Alaborn Cavalier"])
        .player("bob", battlefield=["Elvish Mystic"])
        .build()
    )
    scenario.start_at(Step.DECLARE_ATTACKERS)
    cavalier = scenario.creature("Alaborn Cavalier", "alice")
    mystic = scenario.creature("Elvish Mystic", "bob")
    scenario.game.decisions.provider = QueueProvider(answers=[(mystic,)])
    scenario.will_take_the_may(True, source="Alaborn Cavalier")

    scenario.attack_with(cavalier)
    scenario.game.put_triggers_on_stack()
    scenario.pass_until_resolved()

    assert mystic.tapped
