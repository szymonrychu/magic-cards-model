"""Delayed triggered abilities (CR 603.7).

An ordinary triggered ability is *printed* on a card and `machines/triggers.py`
reads it off the oracle text. A delayed one is not printed anywhere: it is
created by an effect, waits for its trigger event, and then goes on the stack
like any other trigger. Warp's "exile the permanent this spell becomes at the
beginning of the next end step" is one; so is every "at the beginning of the
next end step, sacrifice it".

The rule, in full, verified with `knowledge_search(type="rules")` and read out
of the 2026-08-19 Comprehensive Rules because the search excerpts truncate:

- **CR 603.7** - "An effect may create a delayed triggered ability that can do
  something at a later time. A delayed triggered ability will contain 'when,'
  'whenever,' or 'at,' although that word won't usually begin the ability."
- **CR 603.7a** - "Delayed triggered abilities are created during the resolution
  of spells or abilities, as the result of a replacement effect being applied,
  or as a result of a static ability that allows a player to take an action. A
  delayed triggered ability won't trigger until it has actually been created,
  even if its trigger event occurred just beforehand." So `create` is the
  moment, and an event that happened first does not count.
- **CR 603.7b** - "A delayed triggered ability will trigger only once - the next
  time its trigger event occurs - unless it has a stated duration, such as 'this
  turn.'" That is `remaining`, which defaults to one.
- **CR 603.7c** - "A delayed triggered ability that refers to a particular object
  still affects it even if the object changes characteristics. However, if that
  object is no longer in the zone it's expected to be in at the time the delayed
  triggered ability resolves, the ability won't affect it." That is
  `subject_id` plus `expected_zone`, checked at *resolution* rather than at
  trigger time - which is why `still_affects` is called from the effect and not
  from `fire`.
- **CR 603.7d/e** - the source and controller of a delayed triggered ability are
  the source and controller of the spell or ability that created it, taken as it
  resolved. Not "whoever controls the source now": CR 603.3a explicitly excepts
  delayed triggers from its usual rule and sends the reader here.
- **CR 608.3g** - "If the object that's resolving has a static ability that
  functions on the stack and creates a delayed triggered ability, that delayed
  triggered ability is created as that permanent is put onto the battlefield."
  Warp's shape exactly (CR 702.185a), which is why `Game.resolve_top` creates
  it after `enter_the_battlefield` rather than before.

Once created, a delayed trigger is an ordinary triggered ability in every other
respect: CR 603.3 puts it on the stack the next time a player would receive
priority, CR 603.3b orders it in APNAP order with everything else, and CR 608.2n
removes it from the stack when it resolves. So `fire` produces an
`AbilityOnStack` and hands it to `Game.pending_triggers`, and nothing downstream
needs to know it was delayed.

**What it does** is a hand-written registry keyed by a string, the same shape
`machines/effects.py` and `machines/replacement.py` use, and for the same reason:
the ability has no printed text to read. `DelayedTriggers.on_stack` remembers
which key each `AbilityOnStack` came from, because `AbilityOnStack` has no field
for it and `machines/triggers.py` is not this file's to change.
"""

from collections.abc import Callable
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from ..models.card_state import CardState
from ..models.zone import Zone
from .abilities import AbilityKind, TriggeredAbility, TriggerEvent, TriggerWord
from .triggers import AbilityOnStack, GameEvent
from .turn import Step

if TYPE_CHECKING:
    from ..models.game import Game


class DelayedTrigger(BaseModel):
    """One delayed triggered ability, waiting for its event (CR 603.7)."""

    id: UUID = Field(default_factory=uuid4)

    text: str
    """The ability as it would read on a card, for the stack listing and for a
    failure message. CR 603.7 says the word "when"/"whenever"/"at" is in there
    somewhere even though it does not usually begin the ability."""

    effect: str
    """The key into `DELAYED_EFFECTS`. A key with no entry does nothing, exactly
    as a spell with no `EFFECTS` entry does nothing."""

    event: TriggerEvent
    """The event to watch for, in the vocabulary `Game.emit` already speaks."""

    step: Step | None = None
    """For a `BEGINNING_OF_STEP` trigger, which step. None matches any step."""

    controller: str
    """CR 603.7d/e: the controller of the spell or ability that created this, as
    it resolved."""

    source_id: UUID | None = None
    source_name: str
    """CR 603.7d/e again: the *creating* spell or ability's source, not whatever
    the ability ends up affecting."""

    subject_id: UUID | None = None
    """The particular object the ability refers to (CR 603.7c), if any."""

    subject_player: str | None = None
    """The particular player the ability refers to, if any. CR 603.7c is about
    objects and their zones; a player cannot leave a zone, so nothing is checked
    for this beyond their still being in the game (CR 104.3a)."""

    only_when_active: str | None = None
    """Fire only while this player is the active player.

    "After that turn, that player takes an extra turn" (Emrakul, the Promised
    End) waits for the end of one *particular* turn, not for the next end step
    of any turn. There is no "that turn" object to hold, so the turn is named by
    whose it is - which is exactly how CR 723.1's player-controlling effect
    names it too."""

    expected_zone: Zone | None = None
    """Where CR 603.7c expects that object to be when the ability resolves.
    Somewhere else and the ability resolves without affecting it."""

    remaining: int | None = 1
    """How many more times this may trigger (CR 603.7b). One unless the ability
    has a stated duration; None means "no limit", for a duration-bounded ability
    that fires on every occurrence."""

    def matches(self, event: GameEvent) -> bool:
        """Whether this event is the one being waited for (CR 603.2, 603.7b)."""
        if self.remaining is not None and self.remaining <= 0:
            return False
        if event.event is not self.event:
            return False
        if self.step is not None and event.step is not self.step:
            return False
        return self.only_when_active is None or event.player == self.only_when_active

    def as_ability(self) -> TriggeredAbility:
        """The ability in the shape the rest of the engine handles triggers in.

        CR 603.7 puts the trigger word inside the ability rather than at its
        start, so `word` is recorded as the one the text actually carries and
        `condition` holds the delayed ability's own wait.
        """
        return TriggeredAbility(
            raw=self.text,
            text=self.text,
            face=self.source_name,
            word=TriggerWord.AT,
            condition=self.text,
            effect=self.text,
            event=self.event,
        )

    def on_stack(self, event: GameEvent) -> AbilityOnStack:
        """This ability, as the object CR 603.3 puts on the stack."""
        return AbilityOnStack(
            kind=AbilityKind.TRIGGERED,
            ability=self.as_ability(),
            source_id=self.source_id,
            source_name=self.source_name,
            controller=self.controller,
            event=event,
        )

    def still_affects(self, game: "Game") -> CardState | None:
        """The object this ability refers to, if CR 603.7c still lets it be affected.

        "If that object is no longer in the zone it's expected to be in at the
        time the delayed triggered ability resolves, the ability won't affect
        it." Returns None when there is nothing to affect - either because the
        ability names no object, or because the object has moved on.
        """
        if self.subject_id is None:
            return None
        found = game.find_by_id(self.subject_id)
        if not isinstance(found, CardState):
            return None
        if self.expected_zone is not None and found.zone is not self.expected_zone:
            return None
        return found


#: What a delayed triggered ability does when it resolves. Keyed by the string
#: in `DelayedTrigger.effect`.
DelayedEffect = Callable[["Game", AbilityOnStack, DelayedTrigger], None]


def _exile_warped(game: "Game", ability: AbilityOnStack, trigger: DelayedTrigger) -> None:
    """Warp's delayed trigger (CR 702.185a, CR 603.7).

    "If this spell's warp cost was paid, exile the permanent this spell becomes
    at the beginning of the next end step. Its owner may cast this card after
    the current turn has ended for as long as it remains exiled."

    CR 603.7c is what makes the zone check part of the rule rather than
    defensive coding: a warped permanent that died before the end step is no
    longer on the battlefield, so the ability resolves and affects nothing.
    """
    from .casting import exile_warped

    permanent = trigger.still_affects(game)
    if permanent is None:
        return
    exile_warped(game, permanent)


def _grant_extra_turn(game: "Game", ability: AbilityOnStack, trigger: DelayedTrigger) -> None:
    """ "After that turn, [a player] takes an extra turn" (CR 500.7, CR 603.7).

    Emrakul, the Promised End's second sentence. It has to be a delayed trigger
    rather than part of the resolution: CR 500.7 adds an extra turn "directly
    after the specified turn", so granting it while the cast trigger resolves
    would insert it before the turn Emrakul's controller is about to steal, and
    the controlled player would take their extra turn first.
    """
    username = trigger.subject_player or trigger.controller
    if game.is_in_game(username):
        game.grant_extra_turn(username)


def _sacrifice_subject(game: "Game", ability: AbilityOnStack, trigger: DelayedTrigger) -> None:
    """ "At the beginning of the next end step, sacrifice it."

    CR 701.21a: "To sacrifice a permanent, its controller moves it from the
    battlefield directly to its owner's graveyard." CR 603.7c is what stops it
    reaching a permanent that has already gone somewhere else.
    """
    permanent = trigger.still_affects(game)
    if permanent is not None:
        game.put_into_graveyard(permanent)


DELAYED_EFFECTS: dict[str, DelayedEffect] = {
    "warp:exile": _exile_warped,
    "grant_extra_turn": _grant_extra_turn,
    "sacrifice": _sacrifice_subject,
}


class DelayedTriggers(BaseModel):
    """Every delayed triggered ability a game is currently carrying (CR 603.7).

    A `Game` holds one. It is not a zone and not part of the board: CR 603.7a
    creates these during a resolution, and until the trigger event happens they
    are simply pending facts about the game.
    """

    triggers: list[DelayedTrigger] = Field(default_factory=list)

    pending: dict[UUID, DelayedTrigger] = Field(default_factory=dict)
    """Which delayed ability each `AbilityOnStack` this store produced came from.

    `AbilityOnStack` carries a printed `TriggeredAbility` and `Game._effect_of`
    looks its effect up by (card name, event) in `machines/effects.py`. A
    delayed ability has no printed text and no card, so the mapping has to live
    somewhere; it lives here, keyed by the ability's own id. It outlives
    `triggers`, because a one-shot ability is spent the moment it triggers and
    still has to resolve afterwards.
    """

    def create(self, trigger: DelayedTrigger) -> DelayedTrigger:
        """CR 603.7a: the ability exists from now, and not one moment earlier.

        "A delayed triggered ability won't trigger until it has actually been
        created, even if its trigger event occurred just beforehand."
        """
        self.triggers.append(trigger)
        return trigger

    def fire(self, event: GameEvent) -> list[AbilityOnStack]:
        """Everything this event triggers, in creation order (CR 603.2, 603.7b).

        CR 603.7b: "A delayed triggered ability will trigger only once - the next
        time its trigger event occurs - unless it has a stated duration", so a
        trigger with a count spends one and a spent trigger is dropped.
        """
        fired: list[AbilityOnStack] = []
        for trigger in list(self.triggers):
            if not trigger.matches(event):
                continue
            if trigger.remaining is not None:
                trigger.remaining -= 1
            ability = trigger.on_stack(event)
            self.pending[ability.id] = trigger
            fired.append(ability)
        self.triggers = [
            trigger
            for trigger in self.triggers
            if trigger.remaining is None or trigger.remaining > 0
        ]
        return fired

    def trigger_for(self, ability: AbilityOnStack) -> DelayedTrigger | None:
        """The delayed ability an object on the stack came from, if it came from one."""
        return self.pending.get(ability.id)

    def effect_for(self, ability: AbilityOnStack) -> DelayedEffect | None:
        """What this ability does, or None if it is not one of ours."""
        trigger = self.pending.get(ability.id)
        return DELAYED_EFFECTS.get(trigger.effect) if trigger is not None else None

    def discard(self, ability: AbilityOnStack) -> None:
        """Forget an ability that has finished resolving (CR 608.2n)."""
        self.pending.pop(ability.id, None)
