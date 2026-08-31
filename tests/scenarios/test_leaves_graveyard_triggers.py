"""Scenario: "whenever [a card] leaves your graveyard".

Murktide Regent ("Whenever an instant or sorcery card leaves your graveyard,
put a +1/+1 counter on this creature") and Hardened Academic ("Whenever one or
more cards leave your graveyard, put a +1/+1 counter on target creature you
control") both parsed with `event=None` - `machines/abilities._trigger_event`
has no member for the condition - so `triggered_abilities_of` dropped them and
neither could ever fire. `machines/triggers.py` now reads the condition
(`ExtraTriggerEvent.LEAVES_GRAVEYARD`) and matches it, with the "your" and the
optional type restriction both checked.

The **emit is missing**: no call site raises the event. Every graveyard
departure the engine performs - delve's exile, a return-to-hand, a
graveyard-to-battlefield reanimation - moves the card through `models/game.py`
(Task 1.5's file), which is where the emit belongs. The strict `xfail` at the
end measures that through the real delve path.

Card text verified with `resolve_cards`. CR numbers looked up with
`knowledge_search(type="rules")` in the session that wrote this file:

- **CR 603.10a** - "Some zone-change triggers look back in time. These are
  leaves-the-battlefield abilities, abilities that trigger when a player
  sacrifices a permanent, abilities that trigger when a card leaves a
  graveyard ..." - this condition, named by the rules directly.
- **CR 603.2c** - "one or more cards" is one event with a count, so a batch
  leaving together is a single trigger.
- **CR 603.2g** - "An ability triggers only if its trigger event actually
  occurs", which is why the negatives below assert silence rather than a
  refusal.
"""

import pytest

from magic_cards_model.machines import Step
from magic_cards_model.machines.objects_as_costs import delve
from magic_cards_model.machines.triggers import ExtraTriggerEvent, GameEvent
from magic_cards_model.models.zone import Zone
from tests.scenarios.harness import Scenario


def board() -> Scenario:
    """Alice with both watchers out and an instant in her graveyard; bob with
    his own graveyard, so "your graveyard" has something to be wrong about."""
    return (
        Scenario()
        .player(
            "alice",
            graveyard=["Brainstorm", "Grizzly Bears"],
            battlefield=["Murktide Regent", "Hardened Academic", "Island"],
        )
        .player("bob", graveyard=["Brainstorm"])
    )


def leaves_graveyard(scenario, gone, owner: str) -> None:
    """CR 603.10a's event, raised through `Game.emit` - the real dispatcher.

    The event is staged rather than caused, because nothing causes it yet;
    everything downstream (`Game.emit`'s sweep, `triggers_for`,
    `condition_matches`) is the engine's own, and the `xfail` below is what
    records the missing cause.
    """
    scenario.game.emit(
        GameEvent(
            event=ExtraTriggerEvent.LEAVES_GRAVEYARD,
            subject_id=gone.id,
            subject_name=gone.name,
            subject_card=gone.card,
            subject_types=gone.types,
            subject_subtypes=gone.subtypes,
            player=owner,
            amount=1,
        )
    )


def test_an_instant_leaving_your_graveyard_triggers_both_watchers():
    """Brainstorm is an instant, so it satisfies Murktide's type restriction
    and Hardened Academic's unrestricted "one or more cards" alike."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    brainstorm = scenario.find("Brainstorm", Zone.GRAVEYARD, "alice")

    leaves_graveyard(scenario, brainstorm, "alice")

    assert sorted(trigger.source_name for trigger in scenario.pending_triggers) == [
        "Hardened Academic",
        "Murktide Regent",
    ]


def test_a_creature_leaving_your_graveyard_triggers_only_the_academic():
    """Murktide names "an instant or sorcery card"; a Grizzly Bears card is
    neither, and Hardened Academic names no type at all."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    bears = scenario.find("Grizzly Bears", Zone.GRAVEYARD, "alice")

    leaves_graveyard(scenario, bears, "alice")

    assert [trigger.source_name for trigger in scenario.pending_triggers] == ["Hardened Academic"]


def test_a_card_leaving_an_opponents_graveyard_triggers_neither():
    """The negative on "**your** graveyard". The same event in bob's graveyard
    is a real CR 603.10a event that neither of alice's cards watches."""
    scenario = board().build()
    scenario.start_at(Step.PRECOMBAT_MAIN)
    theirs = scenario.find("Brainstorm", Zone.GRAVEYARD, "bob")

    leaves_graveyard(scenario, theirs, "bob")

    assert scenario.pending_triggers == []


def test_neither_watcher_fires_on_an_unrelated_event():
    """The other negative: a permanent dying is not a card leaving a graveyard
    (CR 603.2g - only the event that actually occurred triggers anything)."""
    scenario = (
        Scenario()
        .player(
            "alice",
            graveyard=["Brainstorm"],
            battlefield=["Murktide Regent", "Hardened Academic", "Grizzly Bears"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)

    scenario.game.put_into_graveyard(scenario.creature("Grizzly Bears", "alice"))

    assert scenario.pending_triggers == []


@pytest.mark.xfail(
    strict=True,
    reason="the matcher is here and works (every test above), but nothing emits the event: "
    "the cards delve exiles out of the graveyard are moved by models/game.py - Task 1.5's file "
    "- which raises no leaves-a-graveyard event, so Murktide's own delve does not feed its own "
    "trigger.",
)
def test_delving_a_card_out_of_your_graveyard_triggers_the_academic():
    """The real path, played through the engine: casting Murktide Regent with
    delve exiles cards from alice's graveyard (CR 603.10a's "a card leaves a
    graveyard"), which Hardened Academic watches.

    The delve half genuinely happens - the assertions on the exiled cards below
    pass - and the trigger still does not, because the move raises no event.
    """
    scenario = (
        Scenario()
        .player(
            "alice",
            hand=["Murktide Regent"],
            graveyard=["Brainstorm"] * 5,
            battlefield=["Hardened Academic", "Island", "Island"],
        )
        .player("bob")
        .build()
    )
    scenario.start_at(Step.PRECOMBAT_MAIN)
    binned = list(scenario.player("alice").graveyard)

    casting = scenario.cast("Murktide Regent")
    payment = casting.begin_paying()
    delve(payment, casting.spell, *binned)
    scenario.pay_with(payment, *scenario.untapped_sources("Island", "Island", username="alice"))
    scenario.put_on_stack(casting)

    assert scenario.player("alice").graveyard == []
    assert all(state.zone is Zone.EXILE for state in binned)
    assert [trigger.source_name for trigger in scenario.pending_triggers] == ["Hardened Academic"]
