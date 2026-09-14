"""Abilities on the stack, and what makes a triggered ability trigger.

`machines/abilities.py` reads an ability off printed text and stops. This is the
half that makes one happen: it turns a game event into triggered abilities, and
it holds the object an ability becomes once it is on the stack.

Every rule number below was looked up in this session against the Comprehensive
Rules. The load-bearing ones:

- **CR 603.2** - "Whenever a game event or game state matches a triggered
  ability's trigger event, that ability automatically triggers. The ability
  doesn't do anything at this point."
- **CR 603.3** - "Once an ability has triggered, its controller puts it on the
  stack as an object that's not a card the next time a player would receive
  priority."
- **CR 603.3b** - several abilities that triggered since the last time a player
  received priority go on the stack in APNAP order: the active player puts
  theirs on first, so theirs end up *lowest* and resolve *last*.
- **CR 603.4** - the intervening *if*: the condition is checked when the trigger
  event occurs, and the ability triggers only if it is true. **CR 608.2a** then
  checks it again on resolution; if it is false the ability is removed from the
  stack and does nothing.
- **CR 405.1** - "When a spell is cast, the physical card is put on the stack.
  When an ability is activated or triggers, it goes on top of the stack without
  any card associated with it." **CR 113.1c** makes that ability an object.
- **CR 113.7 / 113.7a** - the source of an ability is the object that generated
  it, and "once activated or triggered, an ability exists on the stack
  independently of its source. Destruction or removal of the source after that
  time won't affect the ability."
- **CR 608.2n** - "As the final part of an ability's resolution, the ability is
  removed from the stack and ceases to exist." An ability never goes to a
  graveyard, because it is not a card.
- **CR 603.10a** - some zone-change triggers look back in time; a dies-trigger
  is one, so the permanent that just left the battlefield is still asked whether
  it triggered.
- **CR 500.6** - abilities that trigger "at the beginning of" a step trigger when
  that step begins and go on the stack the next time a player would receive
  priority.
- **CR 700.4** - "dies" means "is put into a graveyard from the battlefield".

## What this reads, and what it refuses to read

Trigger conditions are matched by a small set of shapes rather than by a general
parser. `condition_matches` returns False for anything it cannot read, which
means a card whose trigger is not one of these shapes simply never fires - it is
never *wrongly* fired. The shapes understood are listed on `condition_matches`.
"""

import contextlib
import operator
import re
from collections.abc import Sequence
from enum import StrEnum
from typing import TYPE_CHECKING, Annotated, Any, Literal
from uuid import UUID

from pydantic import ConfigDict, Field

from ..ids import new_id
from ..models.card import Card, Color, Type
from ..models.card_state import CardState, ChoiceKind, Counter, TargetRef
from ..models.token import TokenState
from ..models.zone import Zone
from ..snapshot import EngineModel
from .abilities import (
    Ability,
    AbilityKind,
    ActivatedAbility,
    TriggeredAbility,
    TriggerEvent,
    intrinsic_land_ability,
    parse_abilities,
    parse_granted_ability_lines,
    parse_mana_count,
)
from .turn import Step

if TYPE_CHECKING:  # pragma: no cover - import cycle: Game builds on the machines
    from ..models.game import CastRecord, Game

    # `.cost` imports names from this module and `.keywords` imports
    # `AbilityOnStack` itself, so neither can be imported for real up here -
    # `keyword_activation`/`unless_payment` below carry these as string
    # annotations, and `keywords.py`'s own `model_rebuild()` call, run once
    # both classes exist, is what resolves them for real.
    from .cost import CostPayment
    from .keywords import KeywordActivation


class ExtraTriggerEvent(StrEnum):
    """Trigger events with no `machines/abilities.TriggerEvent` member.

    `_trigger_event` (`machines/abilities.py`) reads a printed condition into a
    `TriggerEvent` or leaves `event` unset; a condition it cannot read parses
    with `event=None` and, until now, was dropped by `triggered_abilities_of`
    and could never fire. These are the events those dropped conditions watch,
    named here rather than there because this module owns the matching half.
    `condition_matches` reads them off the printed condition itself (see
    `_unread_trigger_events`), so a `TriggeredAbility` still carries
    `event=None` and nothing about the parser's own output changes.

    **Not all of these are emitted yet.** Each member below says either where
    it is raised from or which emit is still missing; a member with no emitter
    has a complete matcher here watching an event nothing raises.
    """

    #: CR 122.6: "Some spells and abilities refer to counters being put on an
    #: object. This refers to putting counters on that object while it's on the
    #: battlefield and also to an object that's given counters as it enters the
    #: battlefield." Basking Broodscale's and Emperor of Bones' "Whenever one
    #: or more +1/+1 counters are put on this creature". `GameEvent.
    #: counter_kind` is which kind, `GameEvent.amount` how many - CR 603.2c's
    #: "one event contains multiple occurrences" is *not* what a "one or more
    #: counters" condition asks for: that is one event with a count, so it
    #: fires once however many counters arrived at the same time.
    #: **Missing emit:** `Game.add_counters` (`models/game.py`), which today
    #: emits only for lore counters (CR 107.15a).
    COUNTERS_PUT = "counters_put"
    #: CR 603.10a names "abilities that trigger when a card leaves a graveyard"
    #: among the zone-change triggers that look back in time. Murktide Regent's
    #: "Whenever an instant or sorcery card leaves your graveyard" and Hardened
    #: Academic's "Whenever one or more cards leave your graveyard".
    #: **Missing emit:** every graveyard departure in `models/game.py` - the
    #: card exiled to pay delve, the card returned to hand, the card put onto
    #: the battlefield from a graveyard.
    LEAVES_GRAVEYARD = "leaves_graveyard"
    #: CR 401.1's library, as a destination: Wan Shi Tong, All-Knowing's
    #: "Whenever one or more cards are put into a library from anywhere". One
    #: event per instruction that moves cards there, with `GameEvent.amount`
    #: cards, since CR 603.2c makes several cards moved by one instruction one
    #: occurrence rather than several.
    #: **Missing emit:** the library moves in `models/game.py`/`machines/
    #: effects.py` (Brainstorm's own put-back among them).
    PUT_INTO_LIBRARY = "put_into_library"
    #: CR 406.2: "To exile an object is to put it into the exile zone from
    #: whatever zone it's currently in." Scoped to a *graveyard* as the origin,
    #: which is the half of Ketramose, the New Dawn's condition that
    #: `TriggerEvent.LEAVES_BATTLEFIELD_TO_EXILE` does not already cover.
    #: **Missing emit:** the graveyard-to-exile moves in `models/game.py`
    #: (delve, Rest in Peace's replacement, a graveyard-hate effect).
    EXILED_FROM_GRAVEYARD = "exiled_from_graveyard"
    #: "An ability caused a player to add mana", which is not the same event as
    #: CR 106.12's "tapped for mana": Caged Sun's "Whenever a land's ability
    #: causes you to add one or more mana of the chosen color" is about the
    #: *adding*, so a mana ability that costs no `{T}` matches it and so does
    #: another triggered mana ability's own addition - which is the whole of
    #: DDR#990's loop. `GameEvent.mana_added` carries which mana, and
    #: `GameEvent.subject_types` the type line of the object whose ability
    #: added it. Emitted by `Game.activate_ability`'s CR 605.3b fast path and
    #: by `Game.resolve_triggered_mana_abilities`.
    MANA_ADDED = "mana_added"
    #: CR 702.62a's third ability: "When the last time counter is removed from
    #: this card, if it's exiled, you may play it without paying its mana cost
    #: if able." The *last* one specifically - a suspended card going from one
    #: time counter to none - which is why this is its own event rather than a
    #: generic counters-removed one: the count reaching zero is the whole
    #: trigger condition. Emitted by `machines/casting.remove_suspend_time_
    #: counter`, the one place in the engine that takes a time counter off a
    #: suspended card, so both routes into it - suspend's own upkeep trigger
    #: and Greater Gargadon's printed "Sacrifice an artifact, creature, or
    #: land: Remove a time counter from this card" - raise it alike.
    LAST_TIME_COUNTER_REMOVED = "last_time_counter_removed"


class GameEvent(EngineModel):
    """One thing that happened, in the shape a trigger condition is matched against.

    CR 603.2 asks whether "a game event or game state matches a triggered
    ability's trigger event". This is that game event, reduced to the handful of
    facts the conditions in `condition_matches` actually ask about.
    """

    event: TriggerEvent | ExtraTriggerEvent
    """Which event this is. `ExtraTriggerEvent` widens the field rather than
    replacing it: the parser's own `TriggerEvent` stays the vocabulary every
    existing emitter speaks, and the members this module had to name for
    itself sit alongside them. The two enums' values are disjoint, so a
    serialised event still round-trips to exactly the member it was."""

    subject_id: UUID | None = None
    """The object the event happened to: the permanent that entered, died,
    attacked, blocked or was sacrificed, the card that was drawn, the spell
    that was cast or countered, or the source that dealt damage."""

    subject_name: str | None = None
    subject_controller: str | None = None
    subject_card: Card | None = None
    """The printing of the subject, kept so a cast trigger can ask what kind of
    spell it was after the card has moved on."""

    subject_types: tuple[Type, ...] | None = None
    """The subject's card types *as they actually are* right now (CR 712.8f,
    712.8a, 712.12), not the raw printing's front-face-only types.

    `subject_card.types` reads `Card.front_type_line`, which is structurally
    the front face - correct outside the battlefield and stack (CR 712.8a) but
    wrong for a modal double-faced permanent played for its back face: "While a
    modal double-faced ... permanent is on the battlefield, it has only the
    characteristics of the face that's up" (CR 712.8f), and CR 603.10 checks a
    trigger condition against the object "as it exists" (an enters-the-
    battlefield trigger is not one of the look-back exceptions, so this is the
    permanent as it exists on the battlefield now). `CardState.types` already
    reads the up face - the land face when `land_face_played` names one,
    otherwise the front face - so this is that value, captured at the moment
    the event is built rather than recomputed from a bare `Card` later.
    `None` for an event with no `CardState` subject to ask (a countered spell
    once removed from the stack, a leaves-battlefield-to-exile event no
    condition reads by type) - callers that use this fall back to "matches
    nothing named" the same way `subject_card=None` already did."""

    subject_subtypes: tuple[str, ...] | None = None
    """The subject's subtypes, read the same up-face-aware way as
    `subject_types` (CR 205.3a, 712.8f) - "whenever another Merfolk enters"
    needs the face that's actually up, not `Card.subtypes`'s front-face-only
    read."""

    subject_colors: tuple[Color, ...] | None = None
    """The subject's colors (CR 105.2), read the same up-face-aware way as
    `subject_types` - `CardState.colors` rather than `Card.colors`, which is
    front-face-only. A cast event populates this with the spell's colors as it
    sits on the stack, which is what "Whenever you cast a colorless spell ..."
    (Sanctum of Ugin, Ugin, Eye of the Storms) reads; `None` for an event with
    no `CardState` subject to ask, the same fallback `subject_types` already
    uses."""

    mana_added: tuple[Color, ...] = ()
    """The mana this event put into a player's pool, one entry per mana.

    CR 106.12a's "tapped for mana" event carried no colours at all, so a
    condition that asks *which* mana was added - Caged Sun's "Whenever a land's
    ability causes you to add one or more mana of the chosen color" - had
    nothing to read. Colourless is `Color.COLORLESS`, so `{C}{C}` is two
    entries, matching how `ManaAbility.produces` already reports a production.
    Empty for every event that is not about mana."""

    related_id: UUID | None = None
    """The other creature in a blocking pair (CR 509.1a)."""

    targeted_by: UUID | None = None
    """The spell or ability that targeted the subject (CR 702.21a).

    Ward's condition is "becomes the target of a spell or ability an opponent
    controls" and its effect is "counter *that* spell or ability", so the event
    has to carry which one it was. Held as an id, because CR 113.1c makes an
    ability on the stack an object with an id of its own and either kind can be
    the answer."""

    defender: TargetRef | None = None
    """What an attacking creature is attacking (CR 508.1a)."""

    player: str | None = None
    """The player the event is "yours" for: who cast the spell, whose step
    began, who drew the card, gained or lost the life, or took the damage."""

    combat: bool = False
    """For a damage event, whether it was dealt as a result of combat
    (CR 120.2a). "Deals combat damage" conditions refuse a noncombat event and
    the other way round, which is what separates Ragavan's trigger from the
    same creature taking a Lightning Bolt."""

    step: Step | None = None

    counter_kind: str | None = None
    """Which kind of counter was put on the subject, for an
    `ExtraTriggerEvent.COUNTERS_PUT` event (CR 122.1: "any name at all is a
    legal counter kind", which is why this is a plain string and not the
    `Counter` enum). `GameEvent.amount` is how many. `None` for every other
    event, and for a counters event whose emitter did not say - which a
    condition naming a kind ("one or more **+1/+1** counters") refuses, since
    a counter of unknown kind is not known to be the kind it asks for."""

    amount: int | None = None
    """How much, for an event a later clause refers back to by number rather
    than by object - "that much damage" (Questing Beast), "that many cards"
    (Nashi, Searcher in the Dark) - which is CR 607.1's linked-ability shape
    read within one ability rather than across two: the condition clause
    establishes the quantity and the effect clause points back at it. A
    damage event populates this with the amount CR 615.1's prevention and
    CR 608.2b's legality checks already settled on (`Game.deal_damage`'s own
    `event.amount` after replacement, not the raw amount requested).

    A cast event populates it too, with the spell's mana value **as it is on
    the stack** (CR 202.3e: "X is treated as ... the number chosen for it
    while the object is on the stack"), which `Game.put_on_stack` works out
    from `Card.cmc` (CR 107.3g's own X-is-0 reading of the printed cost) plus
    whatever `Game.cast_record` says X was paid as. This is *not* the same
    number as `subject_card.cmc` on this same event, which is always the
    static printed value - Chalice of the Void's "mana value equal to the
    number of charge counters" is exactly the condition that needs the real,
    on-stack number, not the printed one, or a Chalice on 3 would never catch
    a Fireball cast for X=3."""

    origin_zone: Zone | None = None
    """For a `TriggerEvent.CAST_SPELL` event, the zone the card was in
    immediately before CR 601.2a moved it to the stack (CR 400.7: it is a new
    object on the stack, so this has to be captured before the move, not
    re-derived from the object afterwards). `Game.put_on_stack` is the only
    place a `CAST_SPELL` event is built, and it reads `card_state.zone` before
    calling `_take_out_of_every_zone`/`move_to`.

    Knowledge Pool's "Whenever a player casts a spell **from their hand**" and
    Appa, Steadfast Guardian's "Whenever you cast a spell **from exile**" both
    restrict this event to a specific origin - CR 603.2's "matches a triggered
    ability's trigger event" is not satisfied by a cast from anywhere else,
    which is exactly what `condition_matches`'s `CAST_SPELL` branch reads this
    for. Without it, a flashback cast from the graveyard matched "from their
    hand" the same as a cast from hand, and a card whose own free cast comes
    from exile (Knowledge Pool's second ability) would re-trigger itself
    forever. `None` for an event this field was never populated for."""


class TargetingNoticeKind(StrEnum):
    """Why a triggered ability went on the stack with no targets chosen."""

    UNPARSED = "unparsed_targets"
    """`machines/targeting.py` could not read the restriction at all
    (`TargetingProfile.understood` is False). An engine gap, not a legal game
    state - the next unparsed shape must be audible, not silently dropped."""

    NO_LEGAL_TARGET = "no_legal_targets"
    """The restriction was read fine, but nothing satisfies it right now. A
    legitimate game state (CR 608.2d's own "nobody says otherwise" default),
    not a bug - and not the same thing as CR 608.2b's target-becomes-illegal
    fizzle, which only ever applies to a target that *was* chosen."""


class TargetingNotice(EngineModel):
    """One triggered ability whose targets could not be asked for as normal.

    `Game._ask_trigger_targets` used to `return []` silently whenever a
    restriction was unreadable, which is how White Orchid Phantom's "destroy up
    to one target nonbasic land" went on the stack, resolved, and did nothing -
    no decision offered, no record left anywhere. This is that record: appended
    to `Game.targeting_notices` so a player, a test, or a log consumer can see
    the difference between "the parser has a gap" and "there is genuinely
    nothing to target" instead of both looking like an ability that did
    nothing.
    """

    model_config = ConfigDict(frozen=True)

    kind: TargetingNoticeKind
    source_id: UUID | None
    source_name: str
    text: str
    """The ability's own rules text, read for its restriction."""


class InterveningIfNotice(EngineModel):
    """One triggered ability whose intervening *if* clause (CR 603.4) could not
    be evaluated, and so was made to fail closed rather than fire on a
    condition nobody actually checked.

    The old default in `intervening_if_holds` was the opposite: any clause it
    could not read was treated as true, which is how an unkicked Sowing
    Mycospawn exiled a land - "if it was kicked" was never checked, only ever
    assumed. Fail-open is worse than not implemented, so the new default is
    the reverse: a clause this module cannot read is treated as false, and
    that refusal is recorded here - the same "the engine could not read this"
    pattern `TargetingNotice` already established for target restrictions -
    so a gap in `intervening_if_holds` is visible instead of indistinguishable
    from an ability that legitimately never triggers.
    """

    model_config = ConfigDict(frozen=True)

    source_id: UUID | None
    source_name: str
    clause: str
    """The intervening *if* clause itself, as printed (without the leading
    "if")."""


class CastConditionNotice(EngineModel):
    """One "Whenever you cast a [restriction] spell" condition (CR 601.2,
    603.2) whose restriction this module recognised as a mana-value
    comparison but could not parse into a number and a direction, and so was
    made to fail closed rather than fire on a spell nobody actually checked.

    Sanctum of Ugin's "mana value 7 or greater" and its siblings ("... or
    less", "greater than ...", "less than ...", a bare "mana value N") are
    read by `condition_matches`; a mana-value clause shaped some other way is
    not known to be true, so the ability does not trigger, and that refusal is
    recorded here - the same "the engine could not read this" pattern
    `InterveningIfNotice` and `TargetingNotice` already established, so a gap
    stays visible instead of looking like a spell that legitimately did not
    match."""

    model_config = ConfigDict(frozen=True)

    source_id: UUID | None
    source_name: str
    condition: str
    """The trigger condition itself, as printed (without the leading "when",
    "whenever", or "at")."""


class AbilityOnStack(EngineModel):
    """An activated or triggered ability as an object on the stack (CR 113.1c).

    This is deliberately *not* a `CardState`. CR 405.1: an ability "goes on top
    of the stack without any card associated with it", so it has no zone to
    return to and never reaches a graveyard - CR 608.2n removes it from the
    stack and it ceases to exist.

    It keeps its source's id *and* its source's name, because CR 113.7a lets the
    source be destroyed while the ability is still waiting to resolve; the name
    is what is left to describe the ability once the object is gone.
    """

    id: UUID = Field(default_factory=new_id)
    kind: AbilityKind
    ability: TriggeredAbility | ActivatedAbility
    source_id: UUID | None = None
    source_name: str
    controller: str
    source_stamp: UUID | None = None
    """The source's `CardState.zone_change_stamp` when the ability triggered,
    so a recheck on resolution reads the object it came from (CR 113.7a: "if
    the source is no longer in the zone it's expected to be in at that time,
    its last known information is used"; CR 608.2h) rather than whatever new
    object the card has since become (CR 400.7). `None` for an ability that
    records no source object."""
    state_class: Literal["AbilityOnStack"] = "AbilityOnStack"
    """Which concrete Python class built this object - decode-time identity
    for `models.game.StackObject`'s discriminated union, the exact
    counterpart of `CardState.state_class` (see that field's own docstring).

    `StackObject` is `CardState | TokenState | AbilityOnStack`, tagged on
    this field via `Field(discriminator="state_class")`
    (`models/game.py:StackObject`) - not a rules concept, just the label
    pydantic reads to pick the right arm of the union without guessing from
    shape. An `AbilityOnStack` never changes Python class the way a token
    does, so unlike `CardState.state_class` this one has nothing else to key
    off and is always this one literal value.
    """
    source_last_known: (
        Annotated[CardState | TokenState, Field(discriminator="state_class")] | None
    ) = Field(default=None, repr=False)
    """The source as it last existed, kept once it has ceased to exist while
    this ability waits (a token, CR 704.5d). CR 113.7a: the ability "exists on
    the stack independently of its source", and CR 608.2h has an effect that
    needs the source use "the object's last known information" once it is no
    longer in its zone - nothing is left to find by `source_id`. None while the
    source can still be found. `source_or_last_known` reads it."""
    targets: list[TargetRef] = Field(default_factory=list)
    event: GameEvent | None = None
    """The event that triggered it, for an effect that needs to know which
    creature attacked or what blocked what. None for an activated ability."""

    modes: list[int] = Field(default_factory=list)
    """A modal triggered ability's chosen modes, as their 1-based printed
    positions in the order chosen (CR 700.2). CR 603.3c: "its controller
    announces the mode choice when putting the ability on the stack", so
    `Game.put_triggers_on_stack` fills this before any target is chosen, and
    the resolving effect reads it rather than asking again. Empty for a
    non-modal ability."""

    mode_targets: list[list[TargetRef]] = Field(default_factory=list)
    """Each chosen mode's own targets (CR 700.2c, CR 700.2f), aligned by
    position with `modes`; `targets` is their concatenation."""

    x_value: int = 0
    """CR 107.3a's X, as announced when this ability was activated (CR 602.2b
    - "the remainder of the process for activating an ability is identical to
    the process for casting a spell", which includes announcing X). Zero for
    an ability whose cost carries no `{X}` at all - Fiend Artisan's
    "{X}{B/G}, {T}, Sacrifice another creature: Search your library for a
    creature card with mana value X or less ..." is the only ability in the
    pool that reads this; `machines/effects.py`'s `activated_effect_for` is
    what turns it back into the literal word "X" in the ability's own text."""

    keyword_activation: "KeywordActivation | None" = Field(default=None, repr=False)
    """The `machines/keywords.KeywordActivation` this ability came from, if any.

    `machines/effects.py` keys an ability's effect by the name of the card it is
    printed on. A CR 702 keyword's ability is printed on no card in particular -
    cycling (CR 702.29a) and equip (CR 702.6a) are the same ability wherever
    they appear - so there is no name to key it under and the effect lives with
    the keyword instead.

    This is the link back. `machines/keywords.keyword_effect_for` reads it, and
    it is the one thing a resolver needs to run a keyword's effect through the
    ordinary CR 608.2 path rather than by hand.

    Round-trips as real data now, not dropped: a dumped-and-decoded ability
    used to lose this entirely (`exclude=True`), so `keyword_effect_for` fell
    through past a keyword's own effect to the ordinary card-name lookup and a
    decoded cycling or equip activation resolved as nothing. `KeywordActivation`
    itself needed three fixes before it could carry across a round trip -
    see its own docstring and `model_post_init` below:

    - `KeywordActivation.game` (a live `Game`) is still `exclude=True` and
      reset to `None` on decode; nothing this module's `run_effect` reaches
      needs it to have survived by the time an ability is resolved through
      `keyword_effect_for` after a round trip, because `Game.model_post_init`
      relinks it from the outside, the same way it already relinks
      `Player.game`.
    - `KeywordActivation.payment` is a `CostPayment`, which is already plain
      data once its own `.game` is excluded (see `unless_payment` below for
      why that is safe) - but a *paused* payment (still `PENDING`, mid crew or
      equip) does need `.game` back to resume: `Game.model_post_init` relinks
      `keyword_activation.payment.game` the same pass it relinks `keyword_
      activation.game` itself, not "no change needed" as this once claimed.
    - `KeywordActivation.on_stack` points back at this very `AbilityOnStack`,
      which would make a dump cycle forever if both sides kept the edge.
      `KeywordActivation.on_stack` is `exclude=True` for exactly that reason,
      and `model_post_init` below re-wires it from this side after a decode,
      the one direction that does not close a loop.
    - `KeywordActivation.result` (`Any`) stays `exclude=True`. The reason is
      not that a caller promises never to dump a `Game` mid-resolution -
      nothing in this model enforces a caller's contract, and `machines/
      decisions.py`'s pause-and-replay design is exactly that, a convention
      the caller follows, not something this class can rely on. What actually
      rules a mid-flight `result` out is `Game.resolve_top`/`_resolve_top`
      (`models/game.py`): the ability is popped off `self.stack` (CR 608.2n)
      before its effect ever runs, and on an exception `_resolve_ability`'s
      `except Exception` branch discards it and calls `_before_priority()`
      without ever pushing it back onto the stack. A mid-flight ability -
      resolving cleanly or blown up partway through - therefore sits in no
      serialized field at all: not `self.stack`, not `self.pending_triggers`,
      and not `Game.resolving` either, which is itself `exclude=True` and is
      reset to `None` in `resolve_top`'s own `finally` before control ever
      returns to a caller that might dump the game. There is no path back into
      a serialized `Game` for a `KeywordActivation` that is not pre-resolution
      - not a promise, a structural fact about where the reference lives.

      One field on this class *is* serialized in an intermediate-looking
      shape, though: `applied` is a plain `bool`, not excluded, and `run_
      effect` (`machines/keywords.py`) sets it `True` *before* calling the
      keyword's effect function. A dump taken from inside that call - a
      re-entrant `game.ask`, say - would decode to an activation reading
      `applied=True` with `result` still `None`, and `run_effect`'s own early
      return (`if self.applied: return self.result`) would then treat it as
      already run and silently do nothing. Unreachable today only because of
      the same pop: nothing dumps a `Game` from inside a running effect call,
      since the ability that effect belongs to has already left every
      serialized field by the time the call starts.
    """

    division: list[int] | None = None
    """CR 601.2d's announced division, `Casting.division`'s own field mirrored
    here so `machines/effects._deal_divided_damage_shares` reads the same
    attribute off either kind of stack object - CR 602.2b: "the remainder of
    the process for activating an ability is identical to the process for
    casting a spell", which is what makes an ability's own "deals N damage
    divided as you choose among one or two targets" (Ral, Monsoon Mage's −2)
    the same CR 601.2d announcement a spell's identical wording already gets.
    `None` here (no caller announces one yet for an ability) falls through to
    `_divided_damage_shares`'s own even-split fallback, exactly as an
    un-announced spell already does."""
    cost_exiled_card_id: UUID | None = None
    """The id of the card exiled to pay this ability's own cost, when the
    ability's *effect* refers back to it anaphorically - Back from the
    Brink's "Exile a creature card from your graveyard and pay its mana
    cost: Create a token that's a copy of **that card**." The choice is made
    while the cost is paid (CR 601.2b/602.2b), before this object even
    exists, so there is nowhere else on the ability itself to carry it -
    unlike a target, which `machines/targeting.py` already tracks through
    `targets`, this was never a target at all (CR 115.1 - Back from the
    Brink's own sentence never says "target")."""

    cost_sacrificed_card_ids: tuple[UUID, ...] = ()
    """The ids of the permanents sacrificed to pay this ability's own cost,
    when the ability's *effect* asks a question about them - Witch's Oven's
    "Create a Food token. If **the sacrificed creature's** toughness was 4 or
    greater, create two Food tokens instead."

    The sacrifice twin of `cost_exiled_card_id`, and there for the identical
    reason: CR 602.2b pays an activated ability's costs as it is activated,
    so by the time this object exists the permanent is already in a graveyard
    (CR 701.21a) and there is nothing on the battlefield to look at. It was
    never a target either - CR 115.10a: "Just because an object or player is
    being affected by a spell or ability doesn't make that object or player a
    target of that spell or ability", and Witch's Oven's sentence never says
    "target" - so `targets` is not where it can live.

    A tuple rather than a single id because a printed cost may sacrifice more
    than one permanent; every printing in the pool sacrifices exactly one."""

    unless_payment: "CostPayment | None" = Field(default=None, repr=False)
    """The `machines/cost.CostPayment` made for an "unless that player pays" clause.

    CR 702.21a's ward is the one ability of this shape the engine produces:
    "counter that spell or ability unless that player pays [cost]". The cost is
    paid *as the ability resolves*, so the payment has to live on the ability
    that is on the stack - **the object that is paid must be the object that
    resolves**. `machines/keywords.WardTrigger` is the view that opens it and
    `machines/keywords._ward_effect` is what reads it back.

    Option (a) of the two the serialization task offered - reduced to data,
    not refused. `_ward_effect` (`machines/keywords.py`) only ever reads
    `ward_was_paid`, which is `payment.step is CostStep.PAID` - never
    `payment.game` - so *counters or lets through* needs nothing more than
    what was serialized here.

    Resuming a *paused* payment is a different question, though, and an
    earlier version of this note answered it wrong by not asking it at all: it
    said every other field on `CostPayment` - "`cost`, `components`, `pool`,
    `step`, `tapped_for_mana`, and the rest" - was "already plain pydantic
    data with no callable or live object among them", and that a persisted
    `unless_payment` is always terminal (`None`, `PENDING` with nothing tapped
    yet, or settled `PAID`) so none of that mattered anyway. Both halves were
    wrong. `tapped_for_mana` held live `CardState`s by reference until it was
    reduced to `list[UUID]` (`machines/cost.py`) - a full duplicate permanent
    on every dump, and untapping those decoded copies on `rewind` silently
    left the real battlefield sources tapped forever. And a `CostStep.PENDING`
    payment mid-tapping - the exact shape ward is opened in, one priority pass
    before anyone decides whether to pay - round-trips identically to a
    finished one, so "always terminal" was never true either; resuming it
    needs `game` back to find its own tapped sources, seed its payer's pool,
    and keep tapping, which is why `Game.model_post_init` now relinks `.game`
    on both `keyword_activation.payment` and this field. `CostComponent.cards`
    still holds `CardState`s by reference too (ward itself never uses one, but
    `unless_payment`'s type does not rule one out for some future non-mana
    ward cost) - safe because the one place that both mutates through a
    captured reference and can run after a decode, `CostComponent.unpay`,
    re-resolves each one through `game.find_by_id` first. And two more pieces
    of this class's state genuinely do not survive a round trip at all:
    `CostComponent._undo` and `CostPayment._preexisting`
    are `PrivateAttr`s, so a decoded payment's `rewind`/`unpay` now refuse
    loudly rather than silently restoring nothing when that state is gone -
    see both methods' own docstrings.
    """

    def model_post_init(self, _context: object) -> None:
        """Re-close the `KeywordActivation.on_stack` loop `exclude=True` opened.

        `keyword_activation.on_stack` is excluded from serialisation so a dump
        does not chase `self -> keyword_activation -> on_stack -> self`
        forever; this is the one direction that puts the edge back without
        recreating that cycle, run after both live construction (`_activate_
        impl` already assigns `self.on_stack = AbilityOnStack(...,
        keyword_activation=self)`, so this only repeats what it just did) and
        `model_validate` decoding a dump (where nothing else would ever set it
        again). `KeywordActivation.game` is not relinked here - only `Game`
        itself has the reference to relink it with, so `Game.model_post_init`
        does that half, the same way it already relinks `Player.game`.
        """
        if self.keyword_activation is not None:
            self.keyword_activation.on_stack = self

    @property
    def name(self) -> str:
        """A readable name, so a stack listing reads the same for both kinds."""
        return f"{self.source_name}'s {self.kind.value} ability"

    @property
    def is_ability(self) -> bool:
        return True

    @property
    def is_permanent(self) -> bool:
        """An ability never becomes a permanent, whatever its source was."""
        return False

    @property
    def zone(self) -> Zone:
        return Zone.STACK

    def source(self, game: "Game") -> CardState | None:
        """The object that generated this ability, if it is still findable (CR 113.7)."""
        if self.source_id is None:
            return None
        return game.find_by_id(self.source_id)

    def source_or_last_known(self, game: "Game") -> CardState | None:
        """The source if it can still be found, otherwise its last known
        information (CR 113.7a, CR 608.2h), or None when there is neither."""
        return self.source(game) or self.source_last_known


def tapped_for_mana_event(
    source: CardState,
    game: "Game | None" = None,
    mana_added: "Sequence[Color] | None" = None,
) -> GameEvent:
    """CR 106.12a: this permanent's mana ability just resolved and produced mana.

    Built once and reused by every place the engine taps something for mana -
    `machines/cost.CostPayment.tap_for_mana` (tapping a land to pay a total
    cost) and `Game.activate_ability`'s mana-ability fast path (CR 605.3b: the
    ability itself never reaches the stack, but the event still happens) -
    so the two call sites cannot drift apart on what the event looks like.

    `game`, when given and `source` is still on the battlefield, reads
    `subject_types`/`subject_subtypes` off `Game.characteristics_of`
    (CR 613.5) rather than `CardState.types` - a land a continuous effect has
    turned into a creature (Badgermole Cub's own earthbend, Karn's animation)
    is only a Creature on the *computed* board; `CardState.types` is up-face
    aware (CR 712.8f) but knows nothing about layers, and reading it here
    would leave "whenever you tap a creature for mana" blind to exactly the
    land its own controller just animated. Falling back to
    `source.types`/`.subtypes` without a `game`, or once `source` has left the
    battlefield, keeps every existing caller working: Tinder Farm's own
    "{T}, Sacrifice this land: Add {R}{W}" pays its sacrifice before this event
    is emitted (CR 601.2h/602.2's cost is paid in full before the ability
    resolves and produces this event), so the computed board built from the
    *current* battlefield never has it to ask - `computed_board()` only knows
    about permanents still there (CR 613.5's "objects" are the ones on it).
    """
    on_battlefield = game is not None and source.zone is Zone.BATTLEFIELD
    if on_battlefield:
        characteristics = game.characteristics_of(source)
        types = characteristics.types
        subtypes = characteristics.subtypes
    else:
        types = source.types
        subtypes = source.subtypes
    return GameEvent(
        event=TriggerEvent.TAPPED_FOR_MANA,
        subject_id=source.id,
        subject_name=source.name,
        subject_controller=source.controller,
        subject_card=source.card,
        subject_types=types,
        subject_subtypes=subtypes,
        mana_added=tuple(mana_added or ()),
    )


def triggered_mana_count(game: "Game", phrase: str, controller: str) -> int:
    """How many times a triggered mana ability's "for each <phrase>" adds its
    mana, counted now (CR 608.2h: "the answer is determined only once, when
    the effect is applied"), off the computed board (CR 613.5). An unread
    phrase counts 0, adding nothing."""
    parsed = parse_mana_count(phrase)
    if parsed is None:
        return 0
    scope, card_type, subtype = parsed
    board = game.computed_board()
    total = 0
    for permanent in game.battlefield:
        characteristics = board.of(permanent)
        if scope == "you_control" and characteristics.controller != controller:
            continue
        if (
            card_type is not None
            and card_type in characteristics.types
            or subtype
            and any(word.lower() == subtype.lower() for word in characteristics.subtypes)
        ):
            total += 1
    return total


def triggered_mana_recipient(
    recipient: str, controller: str, event: "GameEvent | None"
) -> str | None:
    """Whose pool a triggered mana ability's mana goes to (CR 605.1b).

    "add" is the ability's own controller; "its controller" is the controller
    of the permanent the event is about - the land that was tapped, which for
    an Aura's "enchanted land" is the enchanted one; "that player" is the
    player the condition named, falling back to that same permanent's
    controller.
    """
    if recipient == "controller":
        return controller
    if event is not None:
        if recipient == "that_player" and event.player is not None:
            return event.player
        if event.subject_controller is not None:
            return event.subject_controller
    return None


def mana_added_event(
    source: CardState, game: "Game | None" = None, mana_added: "Sequence[Color] | None" = None
) -> GameEvent:
    """An ability of `source` just caused its controller to add mana.

    Distinct from `tapped_for_mana_event`: CR 106.12 defines "tap for mana" as
    activating a mana ability "that includes the {T} symbol in its activation
    cost", so a condition about *tapping* (Leyline of Abundance's "Whenever you
    tap a creature for mana") is not the same question as one about *adding*
    (Caged Sun's "Whenever a land's ability causes you to add one or more mana
    of the chosen color"). Only the second is matched against this event, which
    is why a triggered mana ability's own addition re-raises this one and never
    the tap.

    Types are read off `Game.characteristics_of` (CR 613.5) while the source is
    still on the battlefield, exactly as `tapped_for_mana_event` does and for
    the same reason: "a **land's** ability" is a question about the computed
    type line, which is how Toph, the First Metalbender's static ability can
    make Caged Sun's own trigger answer it.
    """
    on_battlefield = game is not None and source.zone is Zone.BATTLEFIELD
    if on_battlefield:
        characteristics = game.characteristics_of(source)
        types = characteristics.types
        subtypes = characteristics.subtypes
    else:
        types = source.types
        subtypes = source.subtypes
    return GameEvent(
        event=ExtraTriggerEvent.MANA_ADDED,
        subject_id=source.id,
        subject_name=source.name,
        subject_controller=source.controller,
        subject_card=source.card,
        subject_types=types,
        subject_subtypes=subtypes,
        mana_added=tuple(mana_added or ()),
    )


def is_ability(item: Any) -> bool:
    """True for a stack object that is an ability rather than a spell."""
    return isinstance(item, AbilityOnStack)


# --------------------------------------------------------------------------
# Matching an event against printed trigger conditions
# --------------------------------------------------------------------------

#: How a card refers to itself in modern templating. Older printings say the
#: card's own name instead, which `_self_referential` also accepts.
_SELF_PHRASES = (
    "this creature",
    "this permanent",
    "this artifact",
    "this enchantment",
    "this aura",
    "this land",
    "this planeswalker",
    "this spell",
    "this card",
    "this token",
)

_TYPE_WORDS: dict[str, Type] = {
    "artifact": Type.ARTIFACT,
    "creature": Type.CREATURE,
    "enchantment": Type.ENCHANTMENT,
    "instant": Type.INSTANT,
    "land": Type.LAND,
    "planeswalker": Type.PLANESWALKER,
    "sorcery": Type.SORCERY,
    "battle": Type.BATTLE,
}

#: "At the beginning of [your] upkeep" and friends, mapped onto the turn machine.
#: Ordered longest-phrase-first so "end step" is not mistaken for "step".
_STEP_PHRASES: tuple[tuple[str, Step], ...] = (
    ("end step", Step.END_STEP),
    ("upkeep", Step.UPKEEP),
    ("draw step", Step.DRAW),
    ("untap step", Step.UNTAP),
    ("precombat main phase", Step.PRECOMBAT_MAIN),
    # CR 505.1: "the first main phase (also known as the precombat main
    # phase)" - Static Prison's own "the beginning of your first main phase"
    # is this same phase under its other name, not a step this table was
    # missing a mapping for.
    ("first main phase", Step.PRECOMBAT_MAIN),
    ("postcombat main phase", Step.POSTCOMBAT_MAIN),
    # CR 505.1: "the first main phase (also known as the precombat main
    # phase) and the second main phase (also known as the postcombat main
    # phase)" - Kona, Rescue Beastie's own *survival* trigger says "your
    # second main phase", which is the same phase under its other name.
    # CR 505.1a's corner ("All other main phases are postcombat main phases.
    # This includes the second main phase of a turn in which the combat phase
    # has been skipped") does not arise here: this engine's turn machine has
    # exactly the two main phases CR 500.1 lists.
    ("second main phase", Step.POSTCOMBAT_MAIN),
    ("combat", Step.BEGINNING_OF_COMBAT),
)


class TriggerReadability(StrEnum):
    """Whether a printed condition is one of the shapes this module can read."""

    READ = "read"
    UNREAD = "unread"


#: Chalice of the Void's shape: "a player casts a spell with mana value equal
#: to the number of charge counters on this artifact". Read here rather than
#: left to `_types_match`'s "no type word means anything matches" default,
#: which would otherwise make Chalice counter every spell cast regardless of
#: mana value - the counter-count comparison is the entire point of the card.
_MANA_VALUE_EQUALS_COUNTERS = re.compile(
    r"with mana value equal to the number of (?P<kind>[a-z]+) counters on "
)


def _self_referential(condition: str, source_name: str) -> bool:
    lowered = condition.lower()
    if any(phrase in lowered for phrase in _SELF_PHRASES):
        return True
    front = source_name.split("//")[0].strip().lower()
    if front and front in lowered:
        return True
    # "Whenever Ragavan deals..." uses the short name before the comma.
    short = front.split(",")[0].strip()
    return bool(short) and short in lowered


def _required_types(condition: str) -> tuple[set[Type], set[Type]]:
    """The types a condition asks the subject to have, and the ones it forbids.

    `"an instant or sorcery spell"` requires one of instant or sorcery;
    `"a noncreature spell"` forbids creature. A condition naming no type at all
    requires nothing, which is what "whenever you cast a spell" means.
    """
    lowered = condition.lower()
    forbidden = {
        card_type
        for word, card_type in _TYPE_WORDS.items()
        if re.search(rf"\bnon-?{word}\b", lowered)
    }
    required = {
        card_type
        for word, card_type in _TYPE_WORDS.items()
        if card_type not in forbidden and re.search(rf"\b{word}\b", lowered)
    }
    return required, forbidden


def _types_match(types: tuple[Type, ...] | None, condition: str) -> bool:
    """Whether `types` satisfies a condition's type words (CR 712.8f).

    Takes the subject's *actual* types - `GameEvent.subject_types`, up-face
    aware - rather than a raw `Card`, whose `.types` reads the front face only
    (CR 712.8a) and is wrong for an MDFC on the battlefield for its back face.
    """
    required, forbidden = _required_types(condition)
    if types is None:
        return not required and not forbidden
    type_set = set(types)
    if forbidden & type_set:
        return False
    return not required or bool(required & type_set)


#: "one or more other Cats you control die" names a creature *subtype*
#: (CR 205.3m), not one of `_TYPE_WORDS`'s card types. Captured non-greedily
#: so "Cats" yields "Cat" rather than swallowing the trailing "s".
_OTHER_SUBTYPE = re.compile(r"\bother ([A-Za-z]+?)s?\s+you control\b", re.IGNORECASE)

#: Frontline Heroism's own clause - see `condition_matches`'s `CAST_SPELL`
#: branch for why it has to be stripped before `_types_match` sees it.
_TARGETS_ONLY_SINGLE_CREATURE_CLAUSE = re.compile(
    r"that targets only a single creature you control", re.IGNORECASE
)


def _required_subtype(condition: str) -> str | None:
    match = _OTHER_SUBTYPE.search(condition)
    return match.group(1) if match else None


#: "a Mountain you control enters" (Valakut, the Molten Pinnacle) - a *subtype*
#: named on an entry condition (CR 205.3i's land types here, but the shape is
#: subtype-generic). Capitalization is the discriminator, the same one
#: `_CAST_SUBTYPE`'s own comment relies on: Oracle templating always
#: capitalizes a subtype, and never capitalizes the card-type and colour words
#: `_types_match`/`_color_matches` already read, so "a creature you control
#: enters" and "a nonland permanent enters" cannot match this. Anchored at the
#: start so it reads the condition's *subject*, not a qualifier buried later
#: in the sentence.
#:
#: `another` sits alongside `a`/`an`/`one or more` - Miirym, Sentinel Wyrm's
#: own "another nontoken Dragon you control enters" (CR 205.3a's subtype) -
#: rather than in a second regex, because it is still the condition's subject,
#: read the identical way; self-exclusion for "another" is a separate general
#: rule `condition_matches` already applies to every ENTERS_THE_BATTLEFIELD
#: condition, not something this regex has to encode. An optional "nontoken"
#: (lowercase, so it can never itself be mistaken for the capitalized
#: subtype word right after it - Miirym's own reason to exist) sits between
#: the lead-in and the subtype for the identical reason: Miirym's subject is
#: not "a Dragon" but "another **nontoken** Dragon", and without skipping it
#: the capture would land on "nontoken" itself and fail the `[A-Z]` class.
_ENTERING_SUBTYPE = re.compile(
    r"^(?:an?|one or more|another) (?:nontoken )?(?P<subtype>[A-Z][A-Za-z]*?)s? "
    r"(?:you control |an opponent controls )?enters?\b"
)


#: "you tap a Swamp for mana" (Nirkana Revenant), "a Forest is tapped for mana"
#: (Vernal Bloom) - a subtype named as the tapped permanent (CR 205.3i's land
#: types). Capitalization tells it from the lowercase card-type words
#: `_types_match` reads ("a creature", "a land"), as `_ENTERING_SUBTYPE` does.
_TAPPED_SUBTYPE = re.compile(
    r"(?:\btaps? an? |^an? )(?P<subtype>[A-Z][A-Za-z]*) (?:for mana|is tapped for mana)"
)


def _required_tapped_subtype(condition: str) -> str | None:
    """The subtype a tapped-for-mana condition names, or `None`."""
    match = _TAPPED_SUBTYPE.search(condition)
    return match.group("subtype") if match else None


def _required_entering_subtype(condition: str) -> str | None:
    """The subtype an ENTERS_THE_BATTLEFIELD condition demands, or `None`.

    Split from `_required_subtype` because that one reads only the "other ...
    you control" shape CR 603.10a's death triggers print, which never matches
    an entry condition's plain "a Mountain you control enters".
    """
    match = _ENTERING_SUBTYPE.match(condition.strip())
    return match.group("subtype") if match else None


def _subtype_matches(subtypes: tuple[str, ...] | None, subtype: str | None) -> bool:
    """Whether `subtypes` names `subtype` (CR 712.8f). See `_types_match`'s
    docstring for why this reads `GameEvent.subject_subtypes`, not a raw
    `Card`."""
    if subtype is None:
        return True
    if subtypes is None:
        return False
    return any(word.lower() == subtype.lower() for word in subtypes)


#: "a Dragon spell", "the first Otter spell" - a subtype named on a "cast a
#: ... spell" condition (CR 205.3a). Templating always capitalizes a subtype
#: the way Scryfall's Oracle text does, which is what tells this apart from
#: the lowercase color and card-type words `_color_condition`/`_types_match`
#: already read - "a colorless spell" and "a noncreature spell" never match
#: here because "colorless" and "noncreature" are not capitalized.
_CAST_SUBTYPE_WORD = re.compile(r"\b(?:a|an)\s+([A-Z][a-z]+)\s+spell\b")


def _required_cast_subtype(condition: str) -> str | None:
    match = _CAST_SUBTYPE_WORD.search(condition)
    return match.group(1) if match else None


#: Cori-Steel Cutter's own *Flurry* shape: "you cast your second spell each
#: turn" (the ability word itself, CR 207.2c, carries no rules meaning and is
#: stripped before this text is ever seen). Unlike Alania, Divergent Storm's
#: "it's the first ... spell ... you've cast this turn" - an intervening *if*
#: read by `_first_spell_this_turn_holds`, rechecked at resolution (CR 603.4,
#: 608.2a) - this ordinal sits in the trigger condition itself (CR 603.2): the
#: ability triggers (or doesn't) once, at the moment of casting, and is never
#: revisited.
_ORDINAL_SPELL_EACH_TURN = re.compile(r"your (?P<ordinal>[a-z]+) spells? each turn")

#: The ordinals these clauses spell out. A word this doesn't know - "sixth"
#: and up, not printed on any pool card - falls through to `condition_matches`'
#: own "anything else returns False" default (see its docstring's closing
#: line), the same safe direction every other unread CAST_SPELL restriction
#: there already fails toward.
_ORDINAL_WORDS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5}


def _ordinal_spell_this_turn_matches(
    game: "Game", condition: str, controller: str, event: GameEvent
) -> bool | None:
    """Whether `event`'s spell is exactly the controller's Nth spell cast this
    turn (CR 603.2), for "you cast your [ordinal] spell each turn". `None`,
    not False, when `condition` isn't this shape at all, so the caller can
    tell "read and false" from "not this pattern" the same way
    `_first_spell_this_turn_holds` already does for its own clause.

    `game.spells_cast_this_turn` (`Game.put_on_stack`) already holds this very
    spell by the time the CAST_SPELL event reaches here - CR 601.2a's casting
    event has already happened - so its 1-indexed position in that per-turn,
    per-controller list *is* the ordinal this clause asks about, with no
    separate counter to maintain.
    """
    match = _ORDINAL_SPELL_EACH_TURN.search(condition.lower())
    if match is None:
        return None
    ordinal = _ORDINAL_WORDS.get(match.group("ordinal"))
    if ordinal is None:
        return False
    cast_this_turn = game.spells_cast_this_turn.get(controller, [])
    position = next(
        (
            index
            for index, state in enumerate(cast_this_turn, start=1)
            if state.id == event.subject_id
        ),
        None,
    )
    return position == ordinal


#: CR 105.2's five colors, as the adjective a "cast a ... spell" condition
#: names them with.
_COLOR_WORDS: dict[str, Color] = {
    "white": Color.WHITE,
    "blue": Color.BLUE,
    "black": Color.BLACK,
    "red": Color.RED,
    "green": Color.GREEN,
}


def _color_condition(condition: str) -> tuple[str, frozenset[Color]] | None:
    """The color restriction a "cast a ... spell" condition names, or `None`
    when it names none at all - which is what a plain "whenever you cast a
    spell" means.

    Reads CR 105.2's whole vocabulary for an object's color: "colorless"
    (CR 105.2c, 202.2b - no colored mana symbols), "monocolored" (CR 105.2a -
    exactly one color), "multicolored" (CR 105.2b - two or more), and one or
    more of the five color adjectives named outright (Frontline Heroism's
    "red" is not this shape - it colors a token the effect creates, not the
    spell the condition restricts, so this is only ever consulted for the
    condition clause itself, never the effect that follows it).
    """
    lowered = condition.lower()
    if re.search(r"\bcolorless\b", lowered):
        return "colorless", frozenset()
    if re.search(r"\bmonocolored\b", lowered):
        return "monocolored", frozenset()
    if re.search(r"\bmulticolored\b", lowered):
        return "multicolored", frozenset()
    named = frozenset(
        color for word, color in _COLOR_WORDS.items() if re.search(rf"\b{word}\b", lowered)
    )
    if named:
        return "named", named
    return None


def _color_matches(colors: tuple[Color, ...] | None, condition: str) -> bool:
    """Whether `colors` satisfies a "cast a ... spell" condition's color
    restriction, if it has one (CR 105.2). No restriction named matches
    anything, the same "nothing required" default `_types_match` uses.
    """
    requirement = _color_condition(condition)
    if requirement is None:
        return True
    kind, named = requirement
    color_set = set(colors or ())
    if kind == "colorless":
        return not color_set
    if kind == "monocolored":
        return len(color_set) == 1
    if kind == "multicolored":
        return len(color_set) >= 2
    return bool(color_set & named)


#: The zone words a "cast a ... spell **from** [zone]" clause names -
#: Knowledge Pool's and Possibility Storm's "from their hand" (also "from
#: your hand", the singular-controller phrasing prowess-style keyword
#: expansions would use if one ever named a zone) and Appa, Steadfast
#: Guardian's "from exile" are the two shapes actually printed in the pool
#: (grepped across `tests/fixtures/cards/*.json` rather than guessed), but
#: the word list is zone-generic so a future graveyard- or library-scoped
#: cast trigger reads correctly with no further parser work. "Exile" takes no
#: possessive ("from exile", never "from your exile" - exile is a shared
#: zone, CR 400.1: "Each player has their own library, hand, and graveyard.
#: The other zones are shared by all players."), so it is matched on its own
#: rather than through the
#: `their|your|his or her` possessive `_CAST_ORIGIN_ZONE_RE` group the other
#: four zones share.
_CAST_ORIGIN_ZONE_WORDS: dict[str, Zone] = {
    "hand": Zone.HAND,
    "graveyard": Zone.GRAVEYARD,
    "library": Zone.LIBRARY,
    "battlefield": Zone.BATTLEFIELD,
    "exile": Zone.EXILE,
}

_CAST_ORIGIN_ZONE_RE = re.compile(
    r"\bfrom (?:(?:their|your|his or her) (?P<possessive>hand|graveyard|library|battlefield)"
    r"|(?P<bare>exile))\b",
    re.IGNORECASE,
)


def _required_cast_origin_zone(condition: str) -> Zone | None:
    """The zone a "cast a ... spell from [zone]" condition restricts the cast
    to, or `None` when the condition names no origin at all - which is what a
    plain "whenever you cast a spell" means (CR 603.2: no restriction is no
    restriction).
    """
    match = _CAST_ORIGIN_ZONE_RE.search(condition)
    if match is None:
        return None
    word = (match.group("possessive") or match.group("bare") or "").lower()
    return _CAST_ORIGIN_ZONE_WORDS.get(word)


def _origin_zone_matches(origin_zone: Zone | None, condition: str) -> bool:
    """Whether a `CAST_SPELL` event's `GameEvent.origin_zone` satisfies a
    condition's "from [zone]" restriction, if it has one.

    `origin_zone is None` matches anything: every real `CAST_SPELL` event
    populates it (`Game.put_on_stack` is the only emitter), so `None` here
    means the condition asked about something this engine doesn't track
    rather than a cast this engine knows happened from nowhere - the same
    "nothing required" default `_types_match` and `_color_matches` already
    fall back to, kept on the permissive side rather than refusing a
    legitimate trigger over missing data.
    """
    required = _required_cast_origin_zone(condition)
    if required is None:
        return True
    if origin_zone is None:
        return True
    return origin_zone is required


#: CR 202.3's ordinary mana-value comparisons, as a "cast a ... spell"
#: condition phrases them. Order matters: the "or greater"/"or less"/
#: "greater than"/"less than" forms are tried before the bare-number
#: equality form, since a bare `\d+` would otherwise match the leading digit
#: of "7 or greater" and read it as equality.
_MANA_VALUE_OR_GREATER = re.compile(r"mana value (?:of )?(\d+) or greater")
_MANA_VALUE_OR_LESS = re.compile(r"mana value (?:of )?(\d+) or less")
_MANA_VALUE_GREATER_THAN = re.compile(r"mana value (?:of )?greater than (\d+)")
_MANA_VALUE_LESS_THAN = re.compile(r"mana value (?:of )?less than (\d+)")
_MANA_VALUE_EQUALS = re.compile(r"mana value (?:of )?(\d+)\b")


def _mana_value_comparison(condition: str) -> tuple[int, str] | None:
    """The `(threshold, comparator)` a "with mana value ..." clause names, or
    `None` when the condition names no mana-value restriction at all.

    `comparator` is one of `">="`, `"<="`, `">"`, `"<"`, `"=="`. Chalice of the
    Void's "equal to the number of ... counters" shape is read earlier, by
    `_MANA_VALUE_EQUALS_COUNTERS`, before this is ever reached - its threshold
    is not a literal number in the condition text, so it cannot be one of
    these five.
    """
    lowered = condition.lower()
    or_greater = _MANA_VALUE_OR_GREATER.search(lowered)
    if or_greater is not None:
        return int(or_greater.group(1)), ">="
    or_less = _MANA_VALUE_OR_LESS.search(lowered)
    if or_less is not None:
        return int(or_less.group(1)), "<="
    greater_than = _MANA_VALUE_GREATER_THAN.search(lowered)
    if greater_than is not None:
        return int(greater_than.group(1)), ">"
    less_than = _MANA_VALUE_LESS_THAN.search(lowered)
    if less_than is not None:
        return int(less_than.group(1)), "<"
    equals = _MANA_VALUE_EQUALS.search(lowered)
    if equals is not None:
        return int(equals.group(1)), "=="
    return None


def _controller_clause_holds(
    condition: str, controller: str, subject_controller: str | None
) -> bool:
    """Honour "you control" / "an opponent controls" in a trigger condition.

    A condition that names neither is true for anybody, which is what
    "whenever a creature dies" means.
    """
    lowered = condition.lower()
    if "you control" in lowered or lowered.startswith("you "):
        return subject_controller == controller
    if "an opponent controls" in lowered or "your opponents control" in lowered:
        return subject_controller is not None and subject_controller != controller
    return True


#: CR 603.6d: "Some permanents have text that reads '[This permanent] enters
#: with . . . ,' 'As [this permanent] enters . . . ,' '[This permanent]
#: enters as . . . ,' or '[This permanent] enters tapped.'" - the shapes that
#: qualify *how* a permanent enters, on top of CR 603.6a's bare "enters"/
#: "enters the battlefield". When a trigger condition is itself written with
#: one of these qualifiers - Amulet of Vigor's own "Whenever a permanent you
#: control enters tapped" - the qualifier narrows the CR 603.2 event match
#: itself, checked once when the event occurs; it is not an intervening "if"
#: (CR 603.4, 608.2a) rechecked at resolution, since the condition text never
#: spells "if" for this. `Game.put_onto_battlefield` (`models/game.py`) sets
#: `card_state.tapped` and applies any entering counters *before* emitting
#: `TriggerEvent.ENTERS_THE_BATTLEFIELD` (`Game._enters_event`), so the
#: subject looked up here already carries its real entering state.
_ENTERS_TAPPED_RE = re.compile(r"\benters?\b(?:[^.]*\bthe battlefield\b)?[^.]*?\btapped\b")
_ENTERS_UNTAPPED_RE = re.compile(r"\benters?\b(?:[^.]*\bthe battlefield\b)?[^.]*?\buntapped\b")
_ENTERS_WITH_COUNTER_RE = re.compile(
    r"\benters?\b[^.]*?\bwith\s+(?:a|an|one or more|\d+)\s+"
    r"(?P<kind>[+/\-\w]+(?:[ \-][+/\-\w]+)*?)\s+counters?\s+on\s+(?:it|them)\b"
)


def _entry_qualifier_matches(game: "Game", condition: str, event: "GameEvent") -> bool:
    """Whether an "enters tapped"/"enters untapped"/"enters with a ... counter
    on it" qualifier (CR 603.6d) on an ENTERS_THE_BATTLEFIELD condition holds
    for `event`.

    A condition naming none of these qualifiers imposes none, which is what a
    bare "enters"/"enters the battlefield" already means - this returns True
    for those unconditionally, the same "nothing named, nothing required"
    default `_controller_clause_holds` and `_types_match` already use.
    """
    lowered = condition.lower()
    subject: CardState | None = None
    if event.subject_id is not None:
        subject = game.find_by_id(event.subject_id)

    if _ENTERS_TAPPED_RE.search(lowered) is not None and (subject is None or not subject.tapped):
        return False
    if _ENTERS_UNTAPPED_RE.search(lowered) is not None and (subject is None or subject.tapped):
        return False

    counter_match = _ENTERS_WITH_COUNTER_RE.search(lowered)
    if counter_match is not None:
        if subject is None:
            return False
        kind = counter_match.group("kind").strip()
        if kind not in subject.counters:
            return False

    return True


#: CR 111.1's token, read off a condition's own printed word rather than
#: assumed from a card-name table. `\b` word boundaries so `_TOKEN_WORD`
#: cannot match the "token" inside "nontoken" (a substring, not a word) - see
#: `condition_matches`'s ENTERS_THE_BATTLEFIELD and IS_SACRIFICED branches for
#: why both directions are checked, not just the false-positive one a
#: word-boundary test alone would stop.
_NONTOKEN_WORD = re.compile(r"\bnontoken\b")
_TOKEN_WORD = re.compile(r"\btokens?\b")


def condition_matches(
    game: "Game",
    ability: TriggeredAbility,
    source: CardState,
    controller: str,
    event: GameEvent,
) -> bool:
    """Whether this printed condition is matched by this event (CR 603.2).

    The shapes read, one per `TriggerEvent`:

    - **enters** (CR 603.6a) - "When this creature enters" fires for the source
      itself; "Whenever [another] [type] you control enters" fires for another
      permanent of that type. A condition additionally qualified "... enters
      tapped"/"... enters untapped"/"... enters with a[n] [kind] counter on
      it" (CR 603.6d) only matches an event whose subject actually entered
      that way - see `_entry_qualifier_matches`.
    - **dies** (CR 700.4, 603.10a) - "When this creature dies" for the source
      itself, and "Whenever another creature you control dies" / "... one or
      more other Cats you control die" for anything else that dies, optionally
      narrowed by type or subtype. The plural "die" and the spelled-out CR
      700.4 form ("is put into a graveyard from the battlefield", Flagstones
      of Trokair) are both read as this event by `_trigger_event`. Simultaneous
      deaths are not deduplicated: the engine emits one DIES event per
      permanent that dies rather than batching a single state-based-action
      sweep, so a plural "one or more ... die" condition fires once per death
      that matches rather than once per sweep the way CR 603.2c's "one event,
      multiple occurrences" reading of the printed plural would - untested
      beyond one creature dying at a time, which is what the pool exercises.
    - **leaves the battlefield** (CR 603.6c) - "When this creature leaves the
      battlefield" (Thought-Knot Seer), self-referential only in this pool:
      the generic departure, distinct from `DIES`'s graveyard-specific one,
      emitted by all three of `Game.put_into_graveyard`, `Game.exile_
      permanent`, and `Game.return_to_hand` whenever the move actually
      started on the battlefield, regardless of which of those three it
      became.
    - **attacks** (CR 508.1, 508.3d) - "Whenever this creature attacks" for the
      source, "Whenever a creature you control attacks" for any attacker under
      the same control, and "Whenever you attack" for the controller once per
      combat regardless of how many creatures were declared - the last of
      those reads a second, playerwide event `Game.declare_attackers` emits
      once per attacking player after every per-creature attack event, and
      only that shape of condition is matched against it.
    - **blocks** (CR 509.1) - only the self-referential forms, "Whenever this
      creature blocks" and "... or becomes blocked".
    - **beginning of a step** (CR 500.6) - "At the beginning of your upkeep",
      "... of each upkeep", end step, draw step, untap step, the two main
      phases, and "combat on your turn".
    - **cast** (CR 601.2) - "When you cast this spell" for the spell itself, and
      "Whenever you cast a[n] [restriction] spell" for anything that player
      casts, where the restriction can name a card type/non-type
      (`_types_match`), a subtype (`_required_cast_subtype`,
      `_subtype_matches`), a color/colorless/monocolored/multicolored
      restriction (CR 105.2, `_color_matches`), or a mana-value comparison
      (CR 202.3, `_mana_value_comparison`) - Sanctum of Ugin's "a colorless
      spell with mana value 7 or greater" is all three of the last kinds at
      once. Chalice of the Void's "mana value equal to the number of ...
      counters" is its own shape, read first and separately, since its
      threshold is not a literal number in the condition text. A mana-value
      clause that names one but whose comparison shape none of the five
      regexes read fails closed and is recorded on
      `game.cast_condition_notices` (`CastConditionNotice`) - a restriction
      genuinely present but unrecognised must never be treated as satisfied,
      the same reasoning `intervening_if_holds` already applies to an
      unreadable intervening *if*.
    - **draws a card** (CR 121.2) - "Whenever you draw a card" for the
      controller's own draws and "Whenever an opponent draws a card" for the
      others. The subject is the card drawn; the player is the one who drew it.
    - **gains life** (CR 119.9) - "Whenever you gain life" for the
      controller's own gains, "Whenever an opponent gains life" against the
      others. The player is the one who gained it.
    - **deals damage** (CR 120.1, 120.2a) - "Whenever [this] deals combat
      damage to a player" and the same "to an opponent": combat damage only,
      aimed at a player, and an opponent is one who is not the source's
      controller. Damage to a creature carries no player, so neither clause
      matches; damage with no known source matches nothing self-referential.
    - **is sacrificed** (CR 701.21a, 603.10a) - "Whenever you sacrifice a
      [type]" for what the controller sacrifices, and the self-referential
      "when this [type] is sacrificed". The subject is the permanent that went.
    - **becomes tapped / untapped** (CR 701.26a/b) - only the self-referential
      forms, "Whenever [this] becomes tapped" and "Whenever this creature
      becomes untapped".
    - **is tapped for mana** (CR 106.12, 106.12a) - "Whenever you tap a
      creature for mana" for the controller's own taps, and "Whenever
      enchanted [land] is tapped for mana" for the permanent an Aura source is
      attached to. Emitted by `machines/cost.CostPayment.tap_for_mana`, the
      only place the engine taps a permanent for mana.

    - **becomes the target** (CR 115.1, 601.2c, 602.2b) - ward's and
      Bonecrusher Giant's self-referential forms, and Loki, God of Mischief's
      general "a player or permanent becomes the target of an ability you
      control", which asks nothing about *what* was targeted and everything
      about who controls the targeting object and whether it was a spell or an
      ability (`_targeting_object_matches`).

    An ability the parser left with `event=None` is matched from its printed
    condition instead, by `_unread_condition_matches` - the counters-put,
    leaves-a-graveyard, put-into-a-library, exiled-from-a-graveyard and
    Nth-draw shapes.

    Anything else returns False. A condition this module cannot read never fires
    a trigger, which is the safe direction to be wrong in.
    """
    condition = ability.condition
    lowered = condition.lower()
    mine = _self_referential(condition, source.name)

    if ability.event is None:
        # A condition `machines/abilities._trigger_event` could not read at
        # all. It still names a real trigger event (CR 603.1's "[trigger
        # condition or event]"), and `_unread_condition_matches` reads the
        # handful of those shapes this module knows - see
        # `_unread_trigger_events`.
        return _unread_condition_matches(game, ability, source, controller, event)

    if event.event is not ability.event:
        return False

    if ability.event is TriggerEvent.ENTERS_THE_BATTLEFIELD:
        if not _entry_qualifier_matches(game, condition, event):
            return False
        if mine:
            return event.subject_id == source.id
        if "another" in lowered and event.subject_id == source.id:
            return False
        if not _controller_clause_holds(
            condition, controller, event.subject_controller
        ) or not _types_match(event.subject_types, condition):
            return False
        # A subtype named as the entry condition's subject (CR 205.3i,
        # CR 712.8f) - Valakut, the Molten Pinnacle's "Whenever a Mountain you
        # control enters". `_types_match` reads *card* types only and so
        # answers True for any permanent at all here, which let a plain Forest
        # entering fire a Mountain trigger. `GameEvent.subject_subtypes` is the
        # computed, layer-aware read (CR 613.5), so a land that is a Mountain
        # only because of Blood Moon or Dryad of the Ilysian Grove counts, and
        # one that is not does not.
        if not _subtype_matches(event.subject_subtypes, _required_entering_subtype(condition)):
            return False
        # "Whenever one or more tokens you control enter" (Caretaker's
        # Talent) - CR 111.1's token, not a card type `_types_match` already
        # reads, so it is checked separately: whatever just entered must be
        # a token, not merely a permanent of some named type.
        #
        # "nontoken" contains "token" as a substring, so a plain `"token" in
        # lowered` test used to match Weapons Manufacturing's "a nontoken
        # artifact you control enters" and Miirym's "another nontoken Dragon
        # you control enters" too - and, since the guard demanded the
        # entering permanent *be* a token, it fired those two conditions on
        # exactly the class of permanent their own text excludes. `nontoken`
        # is checked first and enforces the opposite requirement; only when
        # it is absent does a bare `\btoken\b` (word-boundary, so "nontoken"
        # itself cannot match it) ask for the Caretaker's Talent/Belladonna
        # Took shape.
        if _NONTOKEN_WORD.search(lowered):
            subject = game.find_by_id(event.subject_id) if event.subject_id else None
            if subject is None or getattr(subject, "token", False):
                return False
        elif _TOKEN_WORD.search(lowered):
            subject = game.find_by_id(event.subject_id) if event.subject_id else None
            if not (subject is not None and getattr(subject, "token", False)):
                return False
        return True

    if ability.event is TriggerEvent.DIES:
        if event.subject_id == source.id:
            # Covers both "When this creature dies" and the self half of
            # "Whenever this creature or another creature dies" (Blood
            # Artist) - either way the source's own death matches only if
            # the condition names itself at all.
            return mine
        # Not the source's own death: only a condition that also names
        # something else - "another"/"other" - can still match (CR 700.4,
        # 603.10a). A pure "When this creature dies" does not.
        if "another" not in lowered and "other" not in lowered:
            return False
        subtype = _required_subtype(condition)
        return (
            _controller_clause_holds(condition, controller, event.subject_controller)
            and _types_match(event.subject_types, condition)
            and _subtype_matches(event.subject_subtypes, subtype)
        )

    if ability.event is TriggerEvent.LEAVES_THE_BATTLEFIELD:
        # CR 603.6c: only the self-referential form prints in this pool
        # ("When this creature leaves the battlefield", Thought-Knot Seer) -
        # a pure departure condition naming no destination at all, so nothing
        # here reads an "another"/"other" widening the way `DIES` does.
        return mine and event.subject_id == source.id

    if ability.event is TriggerEvent.ATTACKS:
        # CR 508.3d: "Whenever [a player] attacks, ..." triggers once when one
        # or more creatures that player controls are declared as attackers -
        # not once per attacker. `Game.declare_attackers` emits that as its
        # own event, with no subject, once per attacking player.
        if lowered.strip() == "you attack":
            return event.subject_id is None and event.player == controller
        if event.subject_id is None:
            return False
        if mine:
            return event.subject_id == source.id
        return _controller_clause_holds(
            condition, controller, event.subject_controller
        ) and _types_match(event.subject_types, condition)

    if ability.event is TriggerEvent.BLOCKS:
        if not mine:
            return False
        blocks = "blocks" in lowered and event.subject_id == source.id
        blocked = "becomes blocked" in lowered and event.related_id == source.id
        return blocks or blocked

    if ability.event is TriggerEvent.BEGINNING_OF_STEP:
        return _step_matches(condition, controller, event)

    if ability.event is TriggerEvent.CAST_SPELL:
        mv_match = _MANA_VALUE_EQUALS_COUNTERS.search(lowered)
        if mv_match is not None:
            if event.subject_card is None:
                return False
            threshold = source.counters[mv_match.group("kind")]
            # CR 202.3e: on the stack, an {X} spell's mana value is the value
            # chosen for X, not the printed cost's X-as-0 reading -
            # `event.amount` is `Game.put_on_stack`'s own computation of that
            # real number (see `GameEvent.amount`'s docstring); a spell with
            # no {X} at all has `event.amount` equal to `subject_card.cmc`
            # anyway, so this is not a narrower read for the ordinary case.
            mana_value = event.amount if event.amount is not None else event.subject_card.cmc
            return mana_value == threshold
        if mine and "this spell" in lowered:
            return event.subject_id == source.id
        if not _controller_clause_holds(condition, controller, event.player):
            return False
        if not _origin_zone_matches(event.origin_zone, condition):
            return False
        if "during your turn" in lowered or "during their turn" in lowered:
            # Ral, Monsoon Mage's own condition: the cast has to have
            # happened during *this ability's controller's* own turn, not
            # merely by that controller - CR 500.1's turn structure is what
            # "your turn" points at, read off the live `TurnMachine` rather
            # than any snapshot, since the trigger is checked as the cast
            # event fires, before anything else has moved the turn along.
            turn = getattr(game, "turn", None)
            if turn is None or turn.active_player != controller:
                return False
        ordinal_match = _ordinal_spell_this_turn_matches(game, condition, controller, event)
        if ordinal_match is not None:
            return ordinal_match
        # Frontline Heroism's own "that targets only a single creature you
        # control" clause names a type word ("creature") that describes the
        # *target*, not the cast spell itself - `_required_types`/
        # `_types_match` cannot tell the two apart on sight (it just scans
        # the whole condition for a known type word) and used to misread the
        # clause as "cast a creature spell", which Lightning Bolt aimed at
        # your own creature is not, wrongly refusing to fire at all. Stripped
        # out of the copy handed to the type/colour/subtype checks below,
        # which have nothing to do with what the spell targets.
        type_condition = _TARGETS_ONLY_SINGLE_CREATURE_CLAUSE.sub("", condition)
        if not _types_match(event.subject_types, type_condition):
            return False
        if not _color_matches(event.subject_colors, type_condition):
            return False
        subtype = _required_cast_subtype(type_condition)
        if not _subtype_matches(event.subject_subtypes, subtype):
            return False
        if "targets only a single creature you control" in lowered:
            # Frontline Heroism's own condition - not a fact about the cast
            # spell's own printed characteristics at all (CR 105, CR 202.3),
            # but about *what it targets* (CR 601.2c), read off the spell's
            # own `CardState.targets` now that it sits on the stack. "only a
            # single" is CR 115.3's exactly-one, "creature you control" is
            # CR 109.4/608.2b's ordinary target-legality vocabulary read
            # directly here rather than through `machines/targeting.py`,
            # since this is a *condition on an already-legal announcement*,
            # not a targeting requirement of Frontline Heroism's own.
            if event.subject_id is None:
                return False
            spell = game.find_by_id(event.subject_id)
            if spell is None or len(spell.targets) != 1:
                return False
            (only_target,) = spell.targets
            if only_target.is_player:
                return False
            target = game.find_by_id(only_target.card_id)
            if target is None or target.zone is not Zone.BATTLEFIELD:
                return False
            # CR 613.5: the target's computed types, not the printed line -
            # an earthbent land (CR 701.66a) is a creature only there.
            if not game.characteristics_of(target).is_creature:
                return False
            if game.controller_of(target).username != controller:
                return False
        if "mana value" in lowered:
            comparison = _mana_value_comparison(condition)
            if comparison is None:
                game.cast_condition_notices.append(
                    CastConditionNotice(
                        source_id=source.id,
                        source_name=source.name,
                        condition=condition,
                    )
                )
                return False
            threshold, comparator = comparison
            if event.amount is None:
                return False
            ops = {
                ">=": operator.ge,
                "<=": operator.le,
                ">": operator.gt,
                "<": operator.lt,
                "==": operator.eq,
            }
            if not ops[comparator](event.amount, threshold):
                return False
        return True

    if ability.event is TriggerEvent.EXILED:
        # CR 702.35a: "When this card is exiled this way". Only the
        # self-referential form is read, which is the only form madness prints;
        # the "this way" is enforced by the emitter, which raises the event only
        # for the exile the madness replacement performed.
        return mine and event.subject_id == source.id

    if ability.event is TriggerEvent.BECOMES_TARGET:
        # CR 115.1: "Some spells and abilities require their controller to
        # choose one or more targets for them ... These targets are declared as
        # part of the process of putting the spell or ability on the stack"
        # (CR 601.2c for a spell, imported wholesale for an ability by
        # CR 602.2b). Two shapes are read:
        #
        # - the self-referential one, which is what ward prints (CR 702.21a,
        #   "Whenever this permanent becomes the target of a spell or ability
        #   an opponent controls") and what Bonecrusher Giant prints
        #   ("Whenever this creature becomes the target of a spell");
        # - the general one, which names no particular object: Loki, God of
        #   Mischief's "Whenever a player or permanent becomes the target of
        #   an ability you control". Nothing about *what* was targeted is
        #   asked there - "a player or permanent" is every legal target of an
        #   ability - so the whole question is who controls the targeting
        #   object and whether it is a spell or an ability.
        if mine:
            if event.subject_id != source.id:
                return False
        elif not _target_subject_matches(condition):
            return False
        if not _targeting_object_matches(game, condition, event):
            return False
        if "an opponent controls" in lowered:
            return event.player is not None and event.player != controller
        if "you control" in lowered:
            # `GameEvent.player` on a becomes-target event is the controller
            # of the spell or ability that did the targeting (that is what
            # `machines/casting.Casting` puts there), which is exactly whose
            # "you control" this asks about.
            return event.player == controller
        return True

    if ability.event is TriggerEvent.DRAWS_A_CARD:
        if "an opponent" in lowered:
            return event.player is not None and event.player != controller
        return _controller_clause_holds(condition, controller, event.player)

    if ability.event is TriggerEvent.GAINS_LIFE:
        if "an opponent" in lowered:
            return event.player is not None and event.player != controller
        return _controller_clause_holds(condition, controller, event.player)

    if ability.event is TriggerEvent.DEALS_DAMAGE:
        # CR 120.1: "An object that deals damage is the source of that
        # damage" - the subject is the source, so the self-referential form
        # checks the source and the general form checks the controller clause
        # and types of whatever dealt it. Damage with no known source carries
        # neither an id nor a controller and matches nothing here.
        if mine:
            if event.subject_id != source.id:
                return False
        elif not (
            _controller_clause_holds(condition, controller, event.subject_controller)
            and _types_match(event.subject_types, condition)
        ):
            return False
        if "combat damage" in lowered and not event.combat:
            return False
        if "to an opponent" in lowered:
            return event.player is not None and event.player != controller
        if "to a player" in lowered:
            return event.player is not None
        return True

    if ability.event is TriggerEvent.IS_SACRIFICED:
        if mine:
            return event.subject_id == source.id
        # Ashling, the Limitless: "Whenever you sacrifice a nontoken
        # Elemental, ...". "Elemental" is CR 205.3a's creature subtype, not
        # one of `_TYPE_WORDS`'s card types, so `_types_match` cannot see
        # "nontoken" at all - it has to be read the same way
        # ENTERS_THE_BATTLEFIELD's own guard reads it, off the event's actual
        # subject rather than a type word.
        if _NONTOKEN_WORD.search(lowered):
            subject = game.find_by_id(event.subject_id) if event.subject_id else None
            if subject is None or getattr(subject, "token", False):
                return False
        return _controller_clause_holds(
            condition, controller, event.subject_controller
        ) and _types_match(event.subject_types, condition)

    if ability.event in (TriggerEvent.BECOMES_TAPPED, TriggerEvent.BECOMES_UNTAPPED):
        return mine and event.subject_id == source.id

    if ability.event is TriggerEvent.TAPPED_FOR_MANA:
        # CR 106.12a. "Whenever enchanted Forest is tapped for mana" (Utopia
        # Sprawl) asks about the land the Aura is attached to, not the Aura
        # itself - `source.attached_to` is that land's id (CR 303.4).
        if "enchanted" in lowered:
            return event.subject_id is not None and event.subject_id == source.attached_to
        # "Whenever you tap a creature for mana" (Badgermole Cub, Leyline of
        # Abundance) - the controller's own tap, of a permanent of the named
        # type - and "you tap a Swamp for mana" (Nirkana Revenant), "a Forest is
        # tapped for mana" (Vernal Bloom), naming a land subtype instead.
        # Nothing in the pool prints the self-referential form.
        return (
            _controller_clause_holds(condition, controller, event.subject_controller)
            and _types_match(event.subject_types, condition)
            and _subtype_matches(event.subject_subtypes, _required_tapped_subtype(condition))
        )

    if ability.event is TriggerEvent.TURNED_FACE_UP:
        # CR 702.37e/708.8. Brine Elemental's own printing is the only one
        # in the pool ("When this creature is turned face up, ..."), always
        # self-referential.
        return mine and event.subject_id == source.id

    if ability.event is TriggerEvent.DISCARDS_A_CARD:
        # CR 701.9a. "Whenever you discard one or more cards" (Captain
        # Howler, Sea Scourge) asks about the controller's own discards -
        # `event.player` is who did the discarding, `_controller_clause_
        # holds`'s "you " prefix already reads "you discard" the same way
        # every other "you [verb]" condition does.
        return _controller_clause_holds(condition, controller, event.player)

    if ability.event is TriggerEvent.LORE_COUNTERS_ADDED:
        # CR 107.15a: always self-referential (a chapter symbol is never
        # printed any other way) and always about the Saga's own threshold,
        # not the event's raw amount - `ability.chapter` is `N`, `source.
        # lore_counters` is the total *after* `event.amount` were just put
        # on, and CR 107.15a's own "was less than N and became at least N"
        # is exactly the range `event.amount` spans.
        if event.subject_id != source.id or ability.chapter is None:
            return False
        added = event.amount or 0
        new_total = source.lore_counters
        old_total = new_total - added
        return old_total < ability.chapter <= new_total

    return False


#: Loki, God of Mischief's own subject: "a **player or permanent** becomes the
#: target of an ability you control". The only non-self-referential
#: becomes-target subject read at all - anything else (a condition naming a
#: type, a controller, or a subtype for the *target*) is left unread, because
#: "you control" in such a condition can attach either to the target or to the
#: targeting object and reading it wrong fires a trigger that should not fire.
_ANY_TARGET_SUBJECT = re.compile(r"^(?:a player or permanent|a permanent or player)\b")


def _target_subject_matches(condition: str) -> bool:
    """Whether a non-self-referential becomes-target condition's *subject* is
    one this module reads (CR 115.1's "object(s) and/or player(s) the spell or
    ability will affect")."""
    return _ANY_TARGET_SUBJECT.match(condition.lower().strip()) is not None


def _targeting_object_matches(game: "Game", condition: str, event: GameEvent) -> bool:
    """Whether the spell or ability that did the targeting is the kind this
    condition names.

    CR 115.1 lets either kind target, and the printed conditions distinguish
    them: ward says "a spell or ability" (CR 702.21a), Bonecrusher Giant says
    "a spell", Loki, God of Mischief says "an ability". `GameEvent.targeted_by`
    is the id of whichever it was, and CR 113.1c makes an ability on the stack
    an object with an id of its own, so the two are told apart by looking for
    that id among the abilities on the stack.

    An event with no `targeted_by` at all answers only a condition that names
    neither kind, since an unknown kind is not known to be the named one.
    """
    lowered = condition.lower()
    names_spell = "spell" in lowered
    names_ability = "ability" in lowered
    if not names_spell and not names_ability:
        return True
    if event.targeted_by is None:
        return False
    is_ability_object = any(item.id == event.targeted_by for item in game.abilities_on_stack)
    if names_spell and names_ability:
        return True
    return is_ability_object if names_ability else not is_ability_object


#: Basking Broodscale's and Emperor of Bones' condition: "one or more +1/+1
#: counters are put on this creature" (CR 122.6). The kind is captured so a
#: condition naming +1/+1 is not fired by a charge counter.
_COUNTERS_PUT_CONDITION = re.compile(
    r"^one or more (?P<kind>\S+) counters are put on (?P<subject>.+)$"
)

#: Hardened Academic's "one or more cards leave your graveyard" and Murktide
#: Regent's "an instant or sorcery card leaves your graveyard" - one shape with
#: an optional type restriction (CR 603.10a's own "abilities that trigger when
#: a card leaves a graveyard").
_LEAVES_GRAVEYARD_CONDITION = re.compile(
    r"^(?:one or more cards leave|(?:an?|one) (?P<types>[a-z ]+?) card leaves) your graveyard$"
)

#: Wan Shi Tong, All-Knowing's "one or more cards are put into a library from
#: anywhere" (CR 401.1's library as a destination). "From anywhere" is every
#: other zone, so no origin is checked - and nothing that was already in the
#: library was *put into* one, which is why a scry never matches (the event is
#: simply never raised for a reorder).
_PUT_INTO_LIBRARY_CONDITION = re.compile(
    r"^one or more cards are put into a library from anywhere$"
)

#: Ketramose, the New Dawn's "one or more cards are put into exile from
#: graveyards and/or the battlefield during your turn" - one condition naming
#: two origins (CR 406.2's exile from "whatever zone it's currently in"),
#: matched against either of the two events that carry them.
_EXILE_FROM_GRAVEYARD_OR_BATTLEFIELD_CONDITION = re.compile(
    r"^one or more cards are put into exile from graveyards and/or the battlefield"
    r" during your turn$"
)

#: Caged Sun's "a land's ability causes you to add one or more mana of the
#: chosen color" - CR 605.1b's triggered mana ability, watching CR 106.12a's
#: own event for the mana it now carries (`GameEvent.mana_added`). "The chosen
#: color" is CR 614.12a's as-enters choice, recorded on `CardState.choice`.
_LAND_ADDED_CHOSEN_MANA_CONDITION = re.compile(
    r"^a land's ability causes you to add one or more mana of the chosen color$"
)

#: Tamiyo, Inquisitive Student's "you draw your third card in a turn" - an
#: ordinal over CR 121.2's individual card draws, which are one event each.
_NTH_DRAW_CONDITION = re.compile(r"^you draw your (?P<ordinal>[a-z]+) card in a turn$")

#: CR 702.62a's third ability, as `machines/keywords._suspend_abilities`
#: writes it out: "the last time counter is removed from this card". Never
#: printed as a line of condition text on any card - suspend prints it as one
#: word, and the only text on Lotus Bloom that resembles it is reminder text.
_LAST_TIME_COUNTER_CONDITION = re.compile(r"^the last time counter is removed from this card$")


def _unread_trigger_events(condition: str) -> frozenset[TriggerEvent | ExtraTriggerEvent]:
    """The events a condition `machines/abilities._trigger_event` left unread
    watches, or an empty set when this module cannot read it either.

    CR 603.1b: "A triggered ability may have more than one trigger condition" -
    Ketramose, the New Dawn's single printed condition names two origins for
    the same exile and so watches two events, which is why this returns a set
    rather than one event.
    """
    lowered = condition.lower().strip()
    if _COUNTERS_PUT_CONDITION.match(lowered):
        return frozenset({ExtraTriggerEvent.COUNTERS_PUT})
    if _LEAVES_GRAVEYARD_CONDITION.match(lowered):
        return frozenset({ExtraTriggerEvent.LEAVES_GRAVEYARD})
    if _PUT_INTO_LIBRARY_CONDITION.match(lowered):
        return frozenset({ExtraTriggerEvent.PUT_INTO_LIBRARY})
    if _EXILE_FROM_GRAVEYARD_OR_BATTLEFIELD_CONDITION.match(lowered):
        return frozenset(
            {
                ExtraTriggerEvent.EXILED_FROM_GRAVEYARD,
                TriggerEvent.LEAVES_BATTLEFIELD_TO_EXILE,
            }
        )
    if _NTH_DRAW_CONDITION.match(lowered):
        return frozenset({TriggerEvent.DRAWS_A_CARD})
    if _LAND_ADDED_CHOSEN_MANA_CONDITION.match(lowered):
        return frozenset({ExtraTriggerEvent.MANA_ADDED})
    if _LAST_TIME_COUNTER_CONDITION.match(lowered):
        return frozenset({ExtraTriggerEvent.LAST_TIME_COUNTER_REMOVED})
    return frozenset()


def _unread_condition_matches(
    game: "Game",
    ability: TriggeredAbility,
    source: CardState,
    controller: str,
    event: GameEvent,
) -> bool:
    """`condition_matches` for an ability the parser left with `event=None`.

    The shapes read, and what each asks beyond the event itself:

    - **counters put on this permanent** (CR 122.6) - self-referential only,
      which is the only form printed in this pool, and the counter kind has to
      be the kind named.
    - **cards leave your graveyard** (CR 603.10a) - "your" is the ability's
      controller, and an optional type restriction ("an instant or sorcery
      card") is checked against what left.
    - **cards put into a library** (CR 401.1) - "from anywhere", by anyone,
      into any library: nothing further is asked.
    - **cards put into exile from graveyards and/or the battlefield during
      your turn** (CR 406.2) - either origin, and only while the ability's
      controller is the active player.
    - **you draw your Nth card in a turn** (CR 121.2) - the controller's own
      draws, counted over the turn.

    Anything else is False, the same safe direction `condition_matches` fails
    in for a condition it cannot read.
    """
    condition = ability.condition.lower().strip()
    mine = _self_referential(ability.condition, source.name)

    match = _COUNTERS_PUT_CONDITION.match(condition)
    if match is not None:
        if event.event is not ExtraTriggerEvent.COUNTERS_PUT:
            return False
        if event.counter_kind != match.group("kind"):
            return False
        # CR 122.6 is about counters put on *an object*, and every printing in
        # the pool names itself as that object ("on this creature"). A
        # condition naming something else is not read at all.
        return mine and event.subject_id == source.id

    match = _LEAVES_GRAVEYARD_CONDITION.match(condition)
    if match is not None:
        if event.event is not ExtraTriggerEvent.LEAVES_GRAVEYARD:
            return False
        # "your graveyard": whose graveyard the card left, which the event
        # carries as `player` (the graveyard's owner), not the controller of
        # whatever effect moved it.
        if event.player != controller:
            return False
        types = match.group("types")
        return types is None or _types_match(event.subject_types, types)

    if _PUT_INTO_LIBRARY_CONDITION.match(condition):
        return event.event is ExtraTriggerEvent.PUT_INTO_LIBRARY

    if _EXILE_FROM_GRAVEYARD_OR_BATTLEFIELD_CONDITION.match(condition):
        if event.event not in (
            ExtraTriggerEvent.EXILED_FROM_GRAVEYARD,
            TriggerEvent.LEAVES_BATTLEFIELD_TO_EXILE,
        ):
            return False
        # "during your turn" - read off the live turn machine, the same way
        # the CAST_SPELL branch already reads Ral, Monsoon Mage's identical
        # clause, since the condition is checked as the event fires.
        turn = getattr(game, "turn", None)
        return turn is not None and turn.active_player == controller

    match = _NTH_DRAW_CONDITION.match(condition)
    if match is not None:
        if event.event is not TriggerEvent.DRAWS_A_CARD or event.player != controller:
            return False
        ordinal = _ORDINAL_WORDS.get(match.group("ordinal"))
        if ordinal is None:
            return False
        # CR 121.2 makes each card its own draw, so the ordinal is a count of
        # this player's draws so far this turn - a running total nothing in
        # `models/game.py` keeps yet (`Game.draw_cards` emits one event per
        # card and counts nothing). Without it the answer is not known, and an
        # unknown answer does not trigger.
        drawn = getattr(game, "cards_drawn_this_turn", None)
        if not isinstance(drawn, dict):
            return False
        return drawn.get(controller, 0) == ordinal

    if _LAND_ADDED_CHOSEN_MANA_CONDITION.match(condition):
        # CR 605.1b's triggered mana ability: Caged Sun's own condition, read
        # off `GameEvent.mana_added` (the colours CR 106.12a's event now
        # carries) and `CardState.choice` (CR 614.12a's as-enters choice).
        if event.event is not ExtraTriggerEvent.MANA_ADDED:
            return False
        if event.subject_controller != controller:
            return False  # "causes **you** to add".
        if Type.LAND not in (event.subject_types or ()):
            return False  # "a **land's** ability".
        chosen = source.choice
        if chosen is None or chosen.kind is not ChoiceKind.COLOR:
            # CR 106.5: with no choice recorded there is no "chosen color" for
            # the condition to be about, so it does not trigger.
            return False
        return any(color.value == chosen.value for color in event.mana_added)

    if _LAST_TIME_COUNTER_CONDITION.match(condition):
        # CR 702.62a's third ability. "This card" is the source itself and
        # nothing else - `machines/casting.remove_suspend_time_counter` raises
        # the event only for the card it just took the last counter off, so
        # two suspended cards reaching zero in the same upkeep each match only
        # their own.
        return (
            event.event is ExtraTriggerEvent.LAST_TIME_COUNTER_REMOVED
            and event.subject_id == source.id
        )

    return False


def _step_matches(condition: str, controller: str, event: GameEvent) -> bool:
    """ "At the beginning of [whose] [step]" against the step that just began."""
    lowered = condition.lower()
    step = next((step for phrase, step in _STEP_PHRASES if phrase in lowered), None)
    if step is None or step is not event.step:
        return False
    if "your" in lowered:
        return event.player == controller
    # "each upkeep", "the end step" - whoever's step it is.
    return True


#: CR 603.10a's look-back events: the source is deliberately still asked for
#: these even though it has already left the battlefield by the time the event
#: is worked out - `Game.emit` widens `sources` for exactly this reason.
#:
#: `LEAVES_THE_BATTLEFIELD` belongs here on CR 603.10a's own say-so - "Some
#: zone-change triggers look back in time. These are leaves-the-battlefield
#: abilities, abilities that trigger when a player sacrifices a permanent,
#: abilities that trigger when a card leaves a graveyard, and abilities that
#: trigger when an object that all players can see is put into a hand or
#: library" - not merely by analogy with `DIES`. Its absence was a real
#: defect: `Game.put_into_graveyard` happens to emit `LEAVES_THE_BATTLEFIELD`
#: *before* moving the card, so `source.zone` still read BATTLEFIELD when
#: this was checked and the plain-battlefield default below passed by
#: accident. `Game.exile_permanent`, `Game.return_to_hand`, `Game.
#: put_cards_into_library`, and `Game.ante` all emit it *after* the move, so
#: `source.zone` already read EXILE/HAND/LIBRARY/ANTE and the same default
#: refused every one of them - a leaves-the-battlefield ability fired for a
#: destroyed or sacrificed permanent and silently not for one exiled,
#: bounced, tucked, or anted. Adding it here fixes every route at once,
#: regardless of which side of its own move each one happens to emit on.
_LOOK_BACK_EVENTS = (
    TriggerEvent.DIES,
    TriggerEvent.IS_SACRIFICED,
    TriggerEvent.SPELL_IS_COUNTERED,
    TriggerEvent.LEAVES_THE_BATTLEFIELD,
)


def zones_ability_functions_in(ability: TriggeredAbility, source: CardState) -> frozenset[Zone]:
    """Which zone(s) this printed ability functions from (CR 113.6).

    CR 113.6: "Abilities of an instant or sorcery spell usually function only
    while that object is on the stack. Abilities of all other objects usually
    function only while that object is on the battlefield. The exce[ptions are
    listed below]" - the tail truncated for this session's `knowledge_search`
    too, so the exceptions list itself was never read directly; only the
    individually-served subrules below were. The conservative default kept
    here is the rule's own opening sentence: a permanent's ability functions
    on the battlefield unless one of the confirmed exceptions applies.

    Deliberately does **not** consult `_self_referential`/`mine` - CR 113.6k is
    a narrower question ("can this specific trigger condition occur anywhere
    other than the battlefield") than self-reference is ("does the condition
    name this object"). Ugin, Eye of the Storms prints two self-referential
    ("mine") cast triggers - "When you cast this spell" and "Whenever you cast
    a colorless spell" - and only the first can happen while Ugin is a spell
    rather than a permanent; the second names no spell in particular and keeps
    functioning from the battlefield. Gating on `mine` would have granted the
    second one stack rights it does not have.
    """
    lowered = ability.condition.lower()

    # CR 113.6b: "An ability that states which zones it functions in functions
    # only from those zones."
    if "in your graveyard" in lowered or "from your graveyard" in lowered:
        return frozenset({Zone.GRAVEYARD})
    if "opening hand" in lowered:
        return frozenset({Zone.HAND})

    # CR 113.6k: "A trigger condition that can't trigger from the battlefield
    # functions in all zones it can trigger from." A cast-trigger that names
    # "this spell" can only occur while the object is a spell on the stack -
    # once it resolves and becomes a permanent it is never "cast" again - so it
    # functions there instead of the battlefield default. Gated on the literal
    # phrase, not on `ability.event` being CAST_SPELL alone: Cityscape
    # Leveler's compound "When you cast this spell and whenever this creature
    # attacks" collapses to a single ATTACKS-typed ability whose condition
    # string still contains "this spell" as leftover text, and an ATTACKS
    # ability has no business on the stack regardless of what substring
    # survived the collapse - so this branch is reached only when the parsed
    # event itself is CAST_SPELL, never for an ability the parser filed under
    # a different event.
    if ability.event is TriggerEvent.CAST_SPELL and "this spell" in lowered:
        return frozenset({Zone.STACK})

    # CR 702.35a: madness watches its own exile, which can only be observed
    # while the card is, in fact, being exiled that way.
    if ability.event is TriggerEvent.EXILED:
        return frozenset({Zone.EXILE})

    # CR 702.62a says it in as many words: "Suspend is a keyword that
    # represents three abilities. The first is a static ability that functions
    # while the card with suspend is in a player's hand. The second and third
    # are triggered abilities that function in the exile zone." Read off
    # `TriggeredAbility.keyword` rather than off the condition text, because
    # neither of the two is printed as a line at all - `machines/keywords.
    # _suspend_abilities` writes both out from the rule, and the keyword is
    # what says which rule they came from. Both are covered by the one branch:
    # CR 702.62a scopes the sentence to the pair, not to either one.
    if ability.keyword is not None and ability.keyword.lower() == "suspend":
        return frozenset({Zone.EXILE})

    # CR 603.10a: dies, is-sacrificed, countered, and leaves-the-battlefield
    # triggers look back at the object as it existed immediately beforehand,
    # so they function from the battlefield the source just left as well as
    # wherever it ended up - `source.zone` already reflects the post-event
    # location for a route that emits after the move, and still reads
    # BATTLEFIELD for one that emits before it (`Game.put_into_graveyard`);
    # either way the object just left is exactly what `Game.emit` widens
    # `sources` for.
    if ability.event in _LOOK_BACK_EVENTS:
        return frozenset({Zone.BATTLEFIELD, source.zone})

    # CR 113.6m: "An ability whose cost or effect specifies that it moves the
    # object it's on out of a particular zone functions only in that zone,
    # unless its trigger condition or a previous part of its cost or effect
    # specifies that it moves the object it's on into that zone."
    #
    # Arclight Phoenix's "At the beginning of combat on your turn, if you've
    # cast three or more instant and sorcery spells this turn, return this
    # card from your graveyard to the battlefield" is exactly that: the
    # *effect*, not the condition, names the zone. Checked after the branches
    # above so the rule's own "unless" is honoured - a dies trigger whose
    # effect returns the card from the graveyard puts it *into* that zone as
    # its own trigger condition, and `_LOOK_BACK_EVENTS` has already answered
    # for those. `machines/abilities._activated_ability_zone` applies the
    # identical rule to an activated ability's effect text, which is why
    # Cauldron Familiar's `Sacrifice a Food:` ability already worked from a
    # graveyard and this triggered one did not.
    effect = (ability.effect or "").lower()
    if "from your graveyard" in effect and "this card" in effect:
        return frozenset({Zone.GRAVEYARD})

    return frozenset({Zone.BATTLEFIELD})


#: Alania, Divergent Storm's shape: "it's the first instant spell, the first
#: sorcery spell, or the first Otter spell other than Alania you've cast this
#: turn". The excluded name is optional - most cards of this shape (there is
#: only the one in the pool) name themselves so a recast copy of the permanent
#: doesn't retroactively make itself not-the-first.
_FIRST_SPELL_THIS_TURN = re.compile(
    r"^it'?s (?P<segments>.+?)"
    r"(?: other than (?P<excluded>[a-z][a-z' ]*?))?"
    r" you(?:'ve| have)? cast this turn$"
)
_FIRST_SPELL_SEGMENT = re.compile(r"^(?:the )?first (?P<word>[a-z]+) spell$")


def _first_spell_this_turn_holds(
    game: "Game", clause: str, source: CardState, event: "GameEvent | None"
) -> bool | None:
    """CR 603.4: "if it's the first [type] spell ... you've cast this turn".

    Returns `None`, not False, when the clause isn't this shape at all, so the
    caller can tell "read and false" from "not this pattern".
    """
    match = _FIRST_SPELL_THIS_TURN.match(clause)
    if match is None or event is None or event.subject_card is None:
        return None
    segments = [piece.strip() for piece in re.split(r",|\bor\b", match.group("segments"))]
    words: list[str] = []
    for segment in segments:
        if not segment:
            continue
        segment_match = _FIRST_SPELL_SEGMENT.match(segment)
        if segment_match is None:
            return None
        words.append(segment_match.group("word"))
    if not words:
        return None

    excluded = (match.group("excluded") or "").strip()
    controller = source.controller or game.active_player.username
    subject_types = event.subject_types or ()
    subject_subtypes = event.subject_subtypes or ()
    cast_this_turn = game.spells_cast_this_turn.get(controller, [])

    def _category_matches(word: str, types: tuple[Type, ...], subtypes: tuple[str, ...]) -> bool:
        type_ = _TYPE_WORDS.get(word)
        if type_ is not None:
            return type_ in types
        return any(subtype.lower() == word for subtype in subtypes)

    for word in words:
        if not _category_matches(word, subject_types, subject_subtypes):
            continue
        earlier = [
            state
            for state in cast_this_turn
            if state.id != event.subject_id
            and not (excluded and excluded in state.name.lower())
            # `state.types`/`state.subtypes` are `CardState`'s own up-face-aware
            # read (CR 712.8f) rather than `state.card`'s front-face-only one -
            # never actually different for a *cast* spell, since a card is
            # never cast as its MDFC land face, but reading the same field the
            # rest of this module now reads is what keeps this in step with it.
            and _category_matches(word, state.types, state.subtypes)
        ]
        if not earlier:
            return True
    return False


#: CR 702.33d's "if it was kicked" (Sowing Mycospawn) and CR 702.33f's
#: per-kicker variant, "if it was kicked with its [quality] kicker" - not in
#: the pool, so only the plain form is matched; a named-kicker clause falls
#: through to the fail-closed default rather than being misread as the plain
#: form.
_KICKED_CLAUSE = re.compile(r"^it was kicked$")

#: CR 702.56a's own intervening *if*, written out by
#: `machines/keywords._replicate_ability` - "a replicate cost was paid for it".
_REPLICATE_CLAUSE = re.compile(r"^a replicate cost was paid for it$")

#: CR 601.2h's "no mana was spent to cast it" (Vexing Bauble) and "[mana
#: symbols] was spent to cast it" (Wistfulness's "{G}{G}", Drowner of Truth's
#: "{C}") - both always phrased as "... to cast it" in the pool, never "...
#: to cast this spell/creature".
_NO_MANA_SPENT_CLAUSE = re.compile(r"^no mana was spent to cast it$")
_MANA_SPENT_CLAUSE = re.compile(r"^(?P<symbols>(?:\{[wubrgc]\})+) was spent to cast it$")
_MANA_SYMBOL_LETTER = re.compile(r"\{([wubrgc])\}")

#: CR 207.2c's Revolt ability word, both printed phrasings in the pool:
#: Renegade Rallier's and Fatal Push's own "a permanent left the battlefield
#: under your control this turn", and the generic reminder-text order
#: "a permanent you controlled left the battlefield this turn".
_REVOLT_CLAUSES = frozenset(
    {
        "a permanent left the battlefield under your control this turn",
        "a permanent you controlled left the battlefield this turn",
    }
)
_COLOR_LETTERS: dict[str, Color] = {
    "w": Color.WHITE,
    "u": Color.BLUE,
    "b": Color.BLACK,
    "r": Color.RED,
    "g": Color.GREEN,
    "c": Color.COLORLESS,
}


def _cast_record_for_clause(
    game: "Game",
    ability: TriggeredAbility,
    source: CardState,
    event: "GameEvent | None",
    source_stamp: UUID | None = None,
) -> "CastRecord | None":
    """The `CastRecord` a mana-spent or kicked clause's "it" refers to, or
    `None` if there is no longer one to read.

    A self-referential clause - Sowing Mycospawn's "if it was kicked" ("it" is
    "this spell"), Wistfulness's and Drowner of Truth's "if ... was spent to
    cast it" ("it" is "this creature"/"this spell") - means the ability's own
    source, whose record follows it from the stack onto the battlefield (CR
    400.7d) and no further: `Game.cast_record_of` keys it by the object, so a
    permanent that left and returned is a new object with no record (CR 400.7).
    Vexing Bauble's "Whenever a player casts a spell, if no mana was spent to
    cast it" is not self-referential at all: "it" is *that* spell, the trigger
    event's own subject, not Vexing Bauble itself.

    CR 601.2h's spend is recorded by `Game.note_cast` before the CAST_SPELL
    event that reaches this is ever emitted (`Game.put_on_stack`), so the
    record exists by the time this is first asked about, whichever object it
    belongs to. It does not necessarily still exist by CR 608.2a's *recheck*:
    `Game.resolve_top` (both the successful and the fizzled branches) and
    `Game.counter` all discard a spell's `CastRecord` once nothing on the
    normal path will read it again, but an intervening *if* one stack level up
    can still be waiting to ask about that exact spell after it fizzles or is
    countered. Reading `Game.cast_records` directly here, instead of going
    through `Game.cast_record`'s empty-record default, is what keeps "nobody
    ever recorded a cast" and "the record was cleaned up" both distinguishable
    from a genuine "no mana was spent" - the caller is the one that turns a
    missing record into a fail-closed `InterveningIfNotice` rather than a
    silent, wrong-object-shaped true.
    """
    if event is not None and not _self_referential(ability.condition, source.name):
        subject = game.find_by_id(event.subject_id) if event.subject_id else None
        if subject is None:
            return None
        return game.cast_record_of(subject)
    if source_stamp is not None:
        # CR 113.7a, CR 608.2h: the recheck on resolution reads the object
        # the ability came from, even if that object has since moved on.
        return game.cast_record_as_last_known(source_stamp)
    return game.cast_record_of(source)


#: Ruby, Daring Tracker's own clause, split off `condition` into
#: `intervening_if` by `abilities._parse_triggered`'s "while" handling: "you
#: control a creature with power 4 or greater". CR 208.1 is power; the
#: three comparison shapes mirror `_mana_value_comparison`'s above, reused
#: here for a different characteristic rather than duplicated wholesale since
#: the vocabulary ("or greater"/"or less"/a bare number) is the same across
#: both.
_CONTROL_CREATURE_WITH_POWER = re.compile(
    r"^you control a creature with power (?P<threshold>\d+)"
    r"(?P<comparator> or greater| or less)?$"
)


def _control_creature_with_power_holds(game: "Game", clause: str, source: CardState) -> bool | None:
    """CR 208.1's power, compared against every creature the controller has on
    the battlefield right now (CR 613.5's `characteristics_of`, not the
    printed `CardState.power`, so a pumped or shrunk creature is read
    correctly). `None`, not False, when `clause` isn't this shape at all."""
    match = _CONTROL_CREATURE_WITH_POWER.match(clause)
    if match is None:
        return None
    threshold = int(match.group("threshold"))
    comparator = (match.group("comparator") or "").strip()
    ops = {
        "or greater": operator.ge,
        "or less": operator.le,
        "": operator.eq,
    }
    op = ops[comparator]
    controller = source.controller or game.active_player.username
    for state in game.permanents_controlled_by(controller):
        characteristics = game.characteristics_of(state)
        if characteristics.is_creature and op(characteristics.power or 0, threshold):
            return True
    return False


#: CR 702.176a's own intervening *if*, read over the keyword and the counter
#: kind rather than over one card: "this permanent's impending cost was paid
#: and it has a time counter on it". The paid half is
#: `CardState.cast_with_keyword`, which belongs to this object only (CR
#: 400.7), the same way `Game.cast_record_of` answers only for this object.
_PERMANENT_KEYWORD_COST_PAID_WITH_COUNTER = re.compile(
    r"^this permanent's (?P<keyword>[a-z]+) cost was paid and it has an? "
    r"(?P<kind>\+1/\+1|-1/-1|[a-z]+) counter on it$"
)


def intervening_if_holds(
    game: "Game",
    ability: TriggeredAbility,
    source: CardState,
    event: "GameEvent | None" = None,
    source_stamp: UUID | None = None,
) -> bool:
    """Whether an intervening *if* clause is true right now (CR 603.4, 608.2a).

    "When the trigger event occurs, the ability checks whether the stated
    condition is true. The ability triggers only if it's true" (CR 603.4);
    CR 608.2a rechecks the same clause again as the ability resolves.

    Clause shapes read: persist's "it had no -1/-1 counters on it"
    (CR 702.79a), Thopter Assembly's "you control no [subtype]s other than
    this creature", Ocelot Pride's "you gained life this turn", Renegade
    Rallier's own Revolt clause "a permanent left the battlefield under your
    control this turn" (CR 207.2c, `_REVOLT_CLAUSES`, `Game.
    revolt_active_for`), Alania,
    Divergent Storm's "it's the first [type] spell ... you've cast this turn",
    kicker's "if it was kicked" (CR 702.33a, 702.33d), replicate's "a
    replicate cost was paid for it" (CR 702.56a), CR 601.2h's "if no
    mana was spent to cast it" / "if [mana symbols] was spent to cast it"
    (Vexing Bauble, Wistfulness, Drowner of Truth), Transcendent Dragon's
    plain "if you cast it" (CR 601.2's cast, as opposed to any other way a
    permanent reaches the battlefield), Ayara's Oathsworn's counter-count
    comparison "it has fewer than four +1/+1 counters on it"
    (`_counter_count_holds`, CR 122.1), Vengevine's ordinal "it's the second
    creature spell you cast this turn" (`_ordinal_spell_cast_this_turn_holds`),
    and Phoenix Fleet Airship's "you sacrificed a permanent this turn"
    (`_sacrificed_this_turn_holds`, CR 701.21a - read, but unanswerable until
    something records the sacrifices, so it still fails closed).

    The mana/kicker/cast clauses all read
    `Game.cast_record` - see `_cast_record_for_clause` for whose record "it"
    means, and `machines/casting.Casting.cast`/`Game.note_cast` for where the
    record comes from: `CostPayment.mana_payment.spend` at the moment CR 601.2h
    pays the total cost, and `Casting.kicked` at the moment CR 601.2b announces
    which optional additional costs are being paid.

    Anything else **fails closed**: CR 603.4 only lets the ability trigger if
    the condition is true, and a condition this module cannot read is not
    *known* to be true, so the ability does not trigger. This is the opposite
    of the old default, which read anything it could not recognise as true -
    fail-open is how an unkicked Sowing Mycospawn exiled a land. The refusal
    is recorded on `game.intervening_if_notices` (`InterveningIfNotice`) so it
    reads as an engine gap, not as a legal "nothing happened".
    """
    clause = (ability.intervening_if or "").lower().strip()
    if not clause:
        return True

    from .meld import meld_condition_holds

    meld_holds = meld_condition_holds(game, clause, source)
    if meld_holds is not None:
        # CR 701.42a's "you both own and control this <type> and a[nother]
        # <type> named <partner>" - Graf Rats' own triggered meld shape.
        # Answered directly rather than through `_fail_closed`: this clause
        # is fully readable (`machines/meld.py`'s regex is generic across
        # every meld pair, not keyed to a card name), so a `False` here is
        # a genuine "only one half is present right now", not an unreadable
        # shape.
        return meld_holds

    if clause == "you cast it":
        # CR 601.2's cast is a defined action distinct from every other way a
        # permanent can reach the battlefield (reanimation, a search-and-put
        # effect, ...); `Game.note_cast` (CR 601.2h) only ever records a
        # `CastRecord` when a card actually went through that process, so its
        # mere presence for the self-referential source (see
        # `_cast_record_for_clause`) already answers this clause. Unlike the
        # mana-spent clauses above, a missing record here is not an unreadable
        # shape to fail closed on - it is the legitimate, expected answer for
        # a creature that entered some other way, so this returns `False`
        # directly rather than through `_fail_closed`.
        record = _cast_record_for_clause(game, ability, source, event, source_stamp)
        return record is not None

    paid_with_counter = _PERMANENT_KEYWORD_COST_PAID_WITH_COUNTER.fullmatch(clause)
    if paid_with_counter is not None:
        # CR 702.176a, see the regex above. Fully readable, so a False here is
        # a real "not paid" or "no counter left", never a fail-closed notice.
        return (
            source.zone is Zone.BATTLEFIELD
            and (source.cast_with_keyword or "").lower() == paid_with_counter.group("keyword")
            and source.counter_count(paid_with_counter.group("kind")) > 0
        )

    if clause == "its evoke cost was paid":
        # CR 702.74a's own intervening *if*, written out by
        # `machines/keywords._evoke_ability`. What makes it answerable is
        # `CastRecord.keyword`: CR 118.9a allows one alternative cost per spell
        # and `machines/casting.Casting.cast` records which keyword's cost was
        # announced, so "was it evoked" is a lookup rather than an inference
        # from what was spent. A permanent that reached the battlefield without
        # being cast at all has no record, and that is the legitimate answer -
        # its evoke cost was not paid - not an unreadable clause, so this
        # returns False directly rather than through `_fail_closed`, exactly as
        # "you cast it" above does.
        record = _cast_record_for_clause(game, ability, source, event, source_stamp)
        return record is not None and (record.keyword or "").lower() == "evoke"

    if clause == "its offspring cost was paid":
        # CR 702.175a: "'Offspring [cost]' means 'You may pay an additional
        # [cost] as you cast this spell' and 'When this permanent enters, if
        # its offspring cost was paid, create a token that's a copy of it,
        # except it's 1/1.'" Offspring is an *additional* cost (CR 118.8a),
        # not an alternative one, so unlike evoke this reads
        # `CastRecord.offspring_paid` rather than `.keyword` - a spell can be
        # both kicked and offspring-paid at once, and each linked ability
        # only ever asks about its own cost (CR 702.175b).
        record = _cast_record_for_clause(game, ability, source, event, source_stamp)
        return record is not None and record.offspring_paid

    if _KICKED_CLAUSE.match(clause):
        record = _cast_record_for_clause(game, ability, source, event, source_stamp)
        if record is None:
            return _fail_closed(game, ability, source)
        return record.kicked > 0

    if _REPLICATE_CLAUSE.match(clause):
        record = _cast_record_for_clause(game, ability, source, event, source_stamp)
        if record is None:
            return _fail_closed(game, ability, source)
        return record.replicated > 0

    if _NO_MANA_SPENT_CLAUSE.match(clause):
        record = _cast_record_for_clause(game, ability, source, event, source_stamp)
        if record is None:
            return _fail_closed(game, ability, source)
        return not record.any_mana_spent

    mana_match = _MANA_SPENT_CLAUSE.match(clause)
    if mana_match is not None:
        record = _cast_record_for_clause(game, ability, source, event, source_stamp)
        if record is None:
            return _fail_closed(game, ability, source)
        required: dict[Color, int] = {}
        for letter in _MANA_SYMBOL_LETTER.findall(mana_match.group("symbols")):
            color = _COLOR_LETTERS[letter]
            required[color] = required.get(color, 0) + 1
        return all(record.mana_of_color_spent(color) >= count for color, count in required.items())

    if clause == "this card is suspended":
        # CR 702.62a's second ability, and CR 702.62b is its whole definition:
        # "A card is 'suspended' if it's in the exile zone, has suspend, and
        # has a time counter on it." `CardState.is_suspended` is that rule,
        # word for word, so a card already cast, already gone from exile some
        # other way, or already down to zero counters answers False here -
        # on the event (CR 603.4) and again on resolution (CR 608.2a).
        return source.is_suspended

    if clause == "it's exiled":
        # CR 702.62a's third ability. "It" is the card the last time counter
        # came off, which is this ability's own source; CR 406.1's exile zone
        # is the only thing asked about, not the marker that put it there -
        # by this point the card has no time counters left, so CR 702.62b's
        # "suspended" is deliberately *not* what the rule reaches for here.
        return source.zone is Zone.EXILE

    if clause == "it had no -1/-1 counters on it":
        # CR 702.79a asks about the permanent as it last existed on the
        # battlefield, and CR 122.2 has already destroyed its counters on the
        # way to the graveyard. CR 704.8 and CR 603.10a are what make that
        # question answerable at all, and `last_known_counters` is the answer.
        return not source.last_known_counters[Counter.MINUS_ONE]

    match = re.match(r"you control no (\w+?)s? other than this \w+", clause)
    if match is not None:
        subtype = match.group(1)
        controller = source.controller or game.active_player.username
        # CR 613.5: the computed subtypes, not the printed line - hoisted
        # once for the whole scan rather than asked per permanent (see
        # `Game._state_based_actions_once`'s own pattern).
        board = game.computed_board()
        others = [
            state
            for state in game.permanents_controlled_by(controller)
            if state.id != source.id
            and any(word.lower() == subtype for word in board.of(state).subtypes)
        ]
        return not others

    if clause == "you gained life this turn":
        controller = source.controller or game.active_player.username
        return controller in game.life_gained_this_turn

    if clause in _REVOLT_CLAUSES:
        # CR 207.2c: Revolt is an ability word, so no numbered rule spells out
        # the condition itself; the wording is the card's own. Renegade
        # Rallier's own ETB prints "a permanent left the battlefield under
        # your control this turn" - the identical clause Fatal Push carries,
        # except Fatal Push's is read directly by `machines/targeting.py`'s
        # `comparison_value_if_revolt` because it modifies a *target
        # restriction* rather than gating a triggered ability at all
        # (`test_fatal_push_revolt.py`). `Game.revolt_active_for` is the one
        # shared answer both readings ask.
        controller = source.controller or game.active_player.username
        return game.revolt_active_for(controller)

    power_control = _control_creature_with_power_holds(game, clause, source)
    if power_control is not None:
        return power_control

    first_spell = _first_spell_this_turn_holds(game, clause, source, event)
    if first_spell is not None:
        return first_spell

    last_turn = _spells_cast_last_turn_holds(game, clause)
    if last_turn is not None:
        return last_turn

    this_turn = _spells_cast_this_turn_holds(game, clause, source)
    if this_turn is not None:
        return this_turn

    another_spell = _another_spell_cast_this_turn_holds(game, clause, source)
    if another_spell is not None:
        return another_spell

    self_tapped = _source_tapped_holds(clause, source)
    if self_tapped is not None:
        return self_tapped

    counter_count = _counter_count_holds(clause, source)
    if counter_count is not None:
        return counter_count

    ordinal_spell = _ordinal_spell_cast_this_turn_holds(game, clause, source, event)
    if ordinal_spell is not None:
        return ordinal_spell

    sacrificed = _sacrificed_this_turn_holds(game, clause, source)
    if sacrificed is not None:
        return sacrificed

    subtype_count = _controlled_subtype_count_holds(game, clause, source)
    if subtype_count is not None:
        return subtype_count

    return _fail_closed(game, ability, source)


#: Ayara's Oathsworn's clause: "it has fewer than four +1/+1 counters on it".
#: "It" is the source itself - the only subject this shape is printed with in
#: this pool, and CR 603.4's clause is read about the ability's own source
#: unless it plainly names something else.
_COUNTER_COUNT_CLAUSE = re.compile(
    r"^(?:it|this [a-z]+) has "
    r"(?:(?P<comparison>fewer than|more than|at least|exactly) (?P<count>[a-z]+)|(?P<none>no))"
    r" (?P<kind>\S+) counters? on it$"
)

#: How each comparison word answers, given the counters actually there and the
#: number the clause names.
_COUNTER_COMPARISONS = {
    "fewer than": operator.lt,
    "more than": operator.gt,
    "at least": operator.ge,
    "exactly": operator.eq,
}


def _counter_count_holds(clause: str, source: CardState) -> bool | None:
    """CR 603.4's clause as a counter count on the source (CR 122.1's counters
    as "a marker placed on an object ... that modifies its characteristics
    and/or interacts with a rule, ability, or effect").

    `None`, not False, when the clause is not this shape, so an unrelated
    clause still reaches `_fail_closed`. A count word this does not know is
    left unread the same way, rather than guessed at.
    """
    match = _COUNTER_COUNT_CLAUSE.match(clause)
    if match is None:
        return None
    on_it = source.counter_count(match.group("kind"))
    if match.group("none") is not None:
        return on_it == 0
    wanted = _NUMBER_WORDS.get(match.group("count"))
    if wanted is None:
        return None
    return _COUNTER_COMPARISONS[match.group("comparison")](on_it, wanted)


#: Vengevine's clause: "it's the second creature spell you cast this turn".
#: The ordinal twin of `_FIRST_SPELL_THIS_TURN`, which reads only "first" and
#: so left every other ordinal to fail closed.
_ORDINAL_SPELL_CAST_THIS_TURN = re.compile(
    r"^it'?s the (?P<ordinal>[a-z]+) (?P<word>[a-z]+) spell you(?:'ve| have)? cast this turn$"
)


def _ordinal_spell_cast_this_turn_holds(
    game: "Game", clause: str, source: CardState, event: "GameEvent | None"
) -> bool | None:
    """Whether the spell this trigger is about is exactly the controller's Nth
    spell of the named kind cast this turn (CR 603.4).

    "It" is the cast spell the CAST_SPELL event carries, not the source - the
    same reading `_first_spell_this_turn_holds` already gives its own "it".
    Answered from `Game.spells_cast_this_turn`, which CR 601.2i's completed
    cast has already appended this very spell to, so the spell's 1-indexed
    position among that turn's spells of the named kind *is* the ordinal.

    `None` when the clause is not this shape, or when there is no event to
    identify the spell with, so the caller still fails closed.
    """
    match = _ORDINAL_SPELL_CAST_THIS_TURN.match(clause)
    if match is None or event is None or event.subject_id is None:
        return None
    ordinal = _ORDINAL_WORDS.get(match.group("ordinal"))
    card_type = _TYPE_WORDS.get(match.group("word"))
    if ordinal is None or card_type is None:
        return None
    controller = source.controller or game.active_player.username
    of_that_kind = [
        state
        for state in game.spells_cast_this_turn.get(controller, [])
        if card_type in state.types
    ]
    position = next(
        (
            index
            for index, state in enumerate(of_that_kind, start=1)
            if state.id == event.subject_id
        ),
        None,
    )
    return position == ordinal


#: Phoenix Fleet Airship's clause: "you sacrificed a permanent this turn"
#: (CR 701.21a's sacrifice, asked about the turn rather than about one event).
_SACRIFICED_THIS_TURN_CLAUSE = re.compile(r"^you sacrificed a permanent this turn$")


def _sacrificed_this_turn_holds(game: "Game", clause: str, source: CardState) -> bool | None:
    """CR 603.4's clause as "did this player sacrifice anything this turn".

    CR 701.21a: "To sacrifice a permanent, its controller moves it from the
    battlefield directly to its owner's graveyard" - a distinct action from
    the death it causes, which is why `Game.permanents_left_battlefield_this_
    turn` cannot answer this: a bounced or destroyed permanent left the
    battlefield without ever being sacrificed, and reading that counter here
    would fire the Airship on a turn nothing was sacrificed at all.

    Nothing in `models/game.py` records the sacrifices themselves yet, so the
    answer is unknown and this returns `None` - which sends the caller to
    `_fail_closed`, recording the gap rather than guessing. `Game.sacrifice`
    keeping a per-turn, per-controller record (the shape read here) is all
    this needs to become a real answer.
    """
    if _SACRIFICED_THIS_TURN_CLAUSE.match(clause) is None:
        return None
    sacrificed = getattr(game, "permanents_sacrificed_this_turn", None)
    if not isinstance(sacrificed, dict):
        return None
    controller = source.controller or game.active_player.username
    return bool(sacrificed.get(controller))


#: "if Kona is tapped" / "if this creature is untapped" - a clause about the
#: source's own tap state. The subject is either CR 700.7's "this [something]"
#: or CR 201.5's self-reference by printed name, which CR 201.5c lets a card
#: shorten ("Kona" for "Kona, Rescue Beastie").
_SOURCE_TAP_STATE = re.compile(r"^(?P<subject>.+?) is (?P<state>tapped|untapped)$")


def _source_tapped_holds(clause: str, source: CardState) -> bool | None:
    """`_SOURCE_TAP_STATE`'s shape - Kona, Rescue Beastie's *survival* trigger.

    `None` when the clause is not this shape, or when its subject is some
    other object than the source itself: this reads only the source's own tap
    state, so a clause about anything else still reaches `_fail_closed`
    rather than being answered from the wrong permanent.

    CR 201.5 is what makes a printed name mean "just that particular object
    and not any other objects with that name", and CR 201.5c is what lets the
    card print only the first part of it.
    """
    match = _SOURCE_TAP_STATE.match(clause)
    if match is None:
        return None
    subject = match.group("subject").strip().lower()
    name = source.name.lower()
    is_self = re.fullmatch(r"this \w+", subject) is not None or (
        subject
        and (name == subject or name.startswith(f"{subject},") or name.startswith(f"{subject} "))
    )
    if not is_self:
        return None
    return source.tapped if match.group("state") == "tapped" else not source.tapped


#: "you've cast three or more instant and sorcery spells this turn" - Arclight
#: Phoenix's own combat trigger. The type list is CR 205.2a's card types,
#: joined with a bare "and"/"or"/comma; a spell matching *any* of them counts
#: once, which is what the card means (an instant is not also a sorcery).
_SPELLS_CAST_THIS_TURN = re.compile(
    r"^you(?:'ve| have) cast (?P<count>\w+) or more (?P<types>[a-z, ]+?) spells this turn$"
)
#: "you've cast another spell this turn" - Sage of the Skies' own cast
#: trigger. "Another" excludes the spell the trigger is printed on, which is
#: itself already recorded in `Game.spells_cast_this_turn` by the time the
#: trigger is checked (CR 601.2i puts the spell on the stack, and the cast
#: trigger fires off that very event).
_ANOTHER_SPELL_THIS_TURN = re.compile(r"^you(?:'ve| have) cast another spell this turn$")


def _another_spell_cast_this_turn_holds(
    game: "Game", clause: str, source: CardState
) -> bool | None:
    """`_ANOTHER_SPELL_THIS_TURN`'s shape, or `None` if the clause is not it.

    Counted off `Game.spells_cast_this_turn`, with the source itself excluded
    by id - CR 201.5's "just that particular object", not "any object with
    that name", so a second copy of the same card cast earlier this turn does
    satisfy the clause.
    """
    if _ANOTHER_SPELL_THIS_TURN.match(clause) is None:
        return None
    controller = source.controller or game.active_player.username
    cast = game.spells_cast_this_turn.get(controller, [])
    return any(state.id != source.id for state in cast)


def _spells_cast_this_turn_holds(game: "Game", clause: str, source: CardState) -> bool | None:
    """`_SPELLS_CAST_THIS_TURN`'s shape, or `None` if the clause is not it.

    Answered from `Game.spells_cast_this_turn`, the running list this engine
    already keeps for Alania, Divergent Storm's own "the first instant spell
    ... you've cast this turn" - counted at the moment each spell was cast,
    and emptied as a new turn begins.

    "You" is the ability's own controller. Each recorded spell is measured by
    its printed card types (CR 205.2a): the object it was as a spell is long
    gone from the stack by the time this is asked, and CR 400.7 leaves
    whatever it became with no memory of that existence, so the printing is
    the only thing left to read - which is exact here, since no card in the
    pool changes an instant into a sorcery or back.

    Returns `None`, not `False`, for a count word this does not know, so the
    caller still fails closed and records the gap rather than silently
    answering "no".
    """
    match = _SPELLS_CAST_THIS_TURN.match(clause)
    if match is None:
        return None
    wanted = _NUMBER_WORDS.get(match.group("count"))
    if wanted is None:
        return None
    wanted_types: set[Type] = set()
    for word in re.split(r",|\band\b|\bor\b", match.group("types")):
        word = word.strip()
        if not word:
            continue
        card_type = next((t for t in Type if t.value == word.rstrip("s")), None)
        if card_type is None:
            return None
        wanted_types.add(card_type)
    if not wanted_types:
        return None
    controller = source.controller or game.active_player.username
    cast = game.spells_cast_this_turn.get(controller, [])
    matching = sum(1 for state in cast if wanted_types & set(state.card.types))
    return matching >= wanted


#: "if no spells were cast last turn" - the werewolves' transform condition
#: (Duskwatch Recruiter, and every other card printed with this line).
_NO_SPELLS_LAST_TURN = re.compile(r"^no spells were cast last turn$")
#: "if a player cast two or more spells last turn" - the mirror condition on
#: the back face (Krallenhorde Howler), asked of *each* player separately: one
#: player casting two is what it wants, not two spells between them.
_SPELLS_CAST_LAST_TURN = re.compile(r"^a player cast (?P<count>\w+) or more spells last turn$")

#: The counts these clauses are printed with, spelled out as the cards spell
#: them. A number this does not know is left to `_fail_closed`.
_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}


#: Valakut, the Molten Pinnacle's clause: "you control at least five other
#: Mountains". A board count of permanents with a named subtype (CR 205.3i's
#: land types here, but the shape is subtype-generic), optionally excluding the
#: ability's own source - which is what "other" means, and what makes Valakut
#: need *six* Mountains on the battlefield rather than five.
#:
#: `clause` reaches this lowercased, so the subtype cannot be told apart by
#: capitalization the way `_ENTERING_SUBTYPE` tells it apart. That is safe
#: here: the clause names the thing being counted and nothing else, and a
#: card-type word ("creatures", "lands") is counted correctly by
#: `_controlled_subtype_count_holds`'s own card-type branch rather than being
#: mistaken for a subtype.
_CONTROLLED_SUBTYPE_COUNT = re.compile(
    r"^you control (?P<comparison>at least|more than|fewer than|exactly) "
    r"(?P<count>[a-z]+) (?P<other>other )?(?P<subtype>[a-z]+?)s$"
)

#: How each comparison word in `_CONTROLLED_SUBTYPE_COUNT` answers.
_SUBTYPE_COUNT_COMPARISONS = {
    "at least": operator.ge,
    "more than": operator.gt,
    "fewer than": operator.lt,
    "exactly": operator.eq,
}


def _controlled_subtype_count_holds(game: "Game", clause: str, source: CardState) -> bool | None:
    """CR 603.4's clause as "how many <subtype>s do you control right now".

    Valakut, the Molten Pinnacle's "if you control at least five other
    Mountains". Two things make this more than a name count:

    - **CR 613.5** - the subtypes counted are the *computed* ones, so every
      land is a Mountain while Blood Moon is out, and every land you control is
      one while Dryad of the Ilysian Grove is. That is the whole Valakut combo,
      and reading `CardState.subtypes` here would miss all of it.
    - **CR 608.2a** - this same clause is asked again as the ability resolves,
      and the count is taken live both times, so a board that shrank in between
      answers False the second time and the ability is removed from the stack
      doing nothing.

    "Other" excludes the source itself (CR 700.4's "other" is "any object
    other than the object being referred to"). `None`, not False, when the
    clause is not this shape, so anything else still reaches `_fail_closed`.
    """
    match = _CONTROLLED_SUBTYPE_COUNT.match(clause)
    if match is None:
        return None
    wanted = _NUMBER_WORDS.get(match.group("count"))
    if wanted is None:
        return None

    subtype = match.group("subtype")
    controller = source.controller or game.active_player.username
    card_type = _card_type_for_word(subtype)

    count = 0
    for state in game.permanents_controlled_by(controller):
        if match.group("other") and state.id == source.id:
            continue
        characteristics = game.characteristics_of(state)
        if card_type is not None:
            if card_type in characteristics.types:
                count += 1
        elif any(word.lower() == subtype for word in characteristics.subtypes):
            count += 1

    return _SUBTYPE_COUNT_COMPARISONS[match.group("comparison")](count, wanted)


def _card_type_for_word(word: str) -> Type | None:
    """The CR 300.1 card type a counted noun names, or `None` for a subtype.

    "you control at least three other creatures" counts a card type; "at least
    five other Mountains" counts a subtype (CR 205.3i). The two are counted off
    different fields of the computed characteristics, so they have to be told
    apart before counting.
    """
    for kind in Type:
        if kind.value == word:
            return kind
    return None


def _spells_cast_last_turn_holds(game: "Game", clause: str) -> bool | None:
    """The two "last turn" spell-count clauses, or None if this is neither.

    Both are ordinary CR 603.4 intervening *if* clauses, and both are answered
    from `Game.spells_cast_last_turn` - the snapshot taken as a turn begins,
    counting each spell at the moment it was cast (CR 601.2a, CR 601.2i).
    """
    if _NO_SPELLS_LAST_TURN.match(clause):
        return not any(game.spells_cast_last_turn.values())

    match = _SPELLS_CAST_LAST_TURN.match(clause)
    if match is not None:
        wanted = _NUMBER_WORDS.get(match.group("count"))
        if wanted is None:
            return None
        return any(len(cast) >= wanted for cast in game.spells_cast_last_turn.values())

    return None


def _fail_closed(game: "Game", ability: TriggeredAbility, source: CardState) -> bool:
    """Record CR 603.4/608.2a's refusal and answer false - never true - for a
    clause this module cannot currently read, whether that is because nothing
    here recognises its shape or because the `CastRecord` it needs is gone
    (see `_cast_record_for_clause`). Shared so every unreadable clause leaves
    the same trail on `game.intervening_if_notices`.
    """
    game.intervening_if_notices.append(
        InterveningIfNotice(
            source_id=source.id,
            source_name=source.name,
            clause=ability.intervening_if or "",
        )
    )
    return False


# --------------------------------------------------------------------------
# Turning an event into abilities waiting to go on the stack
# --------------------------------------------------------------------------


def triggered_abilities_of(card: Card) -> list[TriggeredAbility]:
    """Every triggered ability a card has (CR 113.3c), printed or abbreviated.

    Two sources, and the second is why ward and prowess fire in a real game
    rather than only when a scenario drives them:

    - the lines that begin When, Whenever or At, read by
      `machines/abilities.parse_abilities`;
    - the CR 702 keywords that *are* triggered abilities without being printed
      as one - ward (CR 702.21a), prowess (CR 702.108a), cascade (CR 702.85a),
      persist (CR 702.79a) and mobilize (CR 702.181a). CR 702.1 calls a keyword
      "shorthand for one or more abilities", and
      `machines/keywords.keyword_triggered_abilities` writes each rule's own
      expansion out.

    Once they are in this list there is nothing further to special-case:
    `triggers_for`, `Game.emit` and CR 603.3's stack ordering treat an
    abbreviated trigger exactly like a spelled-out one.
    """
    # Imported here rather than at the top because `machines/keywords.py`
    # imports this module for `AbilityOnStack`; the cycle is real and only
    # resolvable at call time.
    from .keywords import keyword_triggered_abilities

    printed = [
        ability
        for ability in parse_abilities(card)
        if isinstance(ability, TriggeredAbility)
        # An ability the parser could not file under a `TriggerEvent` is kept
        # when this module can read its condition anyway (`_unread_trigger_
        # events`) - it is matched from the printed condition rather than from
        # `event`, which stays None. Everything else the parser left unread is
        # dropped exactly as before: an ability nothing can match would only
        # ever sit here waiting to fire on the wrong event.
        and (ability.event is not None or _unread_trigger_events(ability.condition))
    ]
    expanded: list[TriggeredAbility] = []
    for ability in printed:
        for split in _expand_attacks_or_blocks(ability):
            for enters_split in _expand_enters_or_attacks(split):
                expanded.extend(_expand_enters_or_leaves(enters_split))
    return expanded + keyword_triggered_abilities(card)


#: "Whenever this creature attacks or blocks, ..." - Elder Gargaroth's own
#: condition, and the shape CR 508.1/509.1 have no single `TriggerEvent` for:
#: `_trigger_event` (`machines/abilities.py`) reads the first event word it
#: recognises in the condition and stops there, so a compound "attacks or
#: blocks" condition is read as `TriggerEvent.ATTACKS` alone and the "or
#: blocks" half is silently dropped - a real game where Elder Gargaroth
#: blocks and never attacks would never see its own trigger.
_ATTACKS_OR_BLOCKS_RE = re.compile(r"^this creature attacks or blocks$", re.IGNORECASE)


def _expand_attacks_or_blocks(ability: TriggeredAbility) -> list[TriggeredAbility]:
    """One ability whose condition is `_ATTACKS_OR_BLOCKS_RE`'s shape becomes
    two: the same printed effect, once watching CR 508.1's attack and once
    watching CR 509.1's block, each a `TriggeredAbility` in its own right so
    `triggers_for`/`condition_matches` need no special case for a compound
    condition - this is the only place that reads "attacks or blocks" as two
    separate self-referential conditions rather than as raw text.

    Every other printed ability passes through unchanged, singleton-wrapped.
    """
    if not _ATTACKS_OR_BLOCKS_RE.match(ability.condition.strip()):
        return [ability]
    return [
        ability.model_copy(
            update={"condition": "this creature attacks", "event": TriggerEvent.ATTACKS}
        ),
        ability.model_copy(
            update={"condition": "this creature blocks", "event": TriggerEvent.BLOCKS}
        ),
    ]


#: "Whenever this creature enters or attacks, ..." - Primeval Titan's own
#: condition, the same compound shape `_ATTACKS_OR_BLOCKS_RE` reads for
#: "attacks or blocks": `_trigger_event` (`machines/abilities.py`) reads
#: "enters?" ahead of "attacks?" in its own precedence order, so a compound
#: "enters or attacks" condition is read as `TriggerEvent.ENTERS_THE_
#: BATTLEFIELD` alone and the "or attacks" half is silently dropped - a real
#: Primeval Titan that attacks without ever having triggered on entry (cast
#: with haste, or already on the battlefield when this engine first sees it)
#: would never see its own attack trigger.
_ENTERS_OR_ATTACKS_RE = re.compile(r"^this creature enters or attacks$", re.IGNORECASE)


def _expand_enters_or_attacks(ability: TriggeredAbility) -> list[TriggeredAbility]:
    """One ability whose condition is `_ENTERS_OR_ATTACKS_RE`'s shape becomes
    two: the same printed effect, once watching CR 603.6a's entering event and
    once watching CR 508.3c's attack, each a `TriggeredAbility` in its own
    right - the same split `_expand_attacks_or_blocks` already performs for
    its own compound condition, reused here for a second one rather than
    writing a second splitter.

    Every other printed ability passes through unchanged, singleton-wrapped.
    """
    if not _ENTERS_OR_ATTACKS_RE.match(ability.condition.strip()):
        return [ability]
    return [
        ability.model_copy(
            update={
                "condition": "this creature enters",
                "event": TriggerEvent.ENTERS_THE_BATTLEFIELD,
            }
        ),
        ability.model_copy(
            update={"condition": "this creature attacks", "event": TriggerEvent.ATTACKS}
        ),
    ]


#: "When this artifact enters or leaves the battlefield, ..." -
#: Sewer-veillance Cam's own condition, the third compound shape of the same
#: family as `_ATTACKS_OR_BLOCKS_RE` and `_ENTERS_OR_ATTACKS_RE`. CR 603.1b: "A
#: triggered ability may have more than one trigger condition"; `_trigger_
#: event` (`machines/abilities.py`) reads "enters" first and stops, so the
#: departure half - CR 603.6c's leaves-the-battlefield ability, which is the
#: half a deck actually uses when the Cam is sacrificed to its own draw
#: ability - was silently dropped.
_ENTERS_OR_LEAVES_RE = re.compile(
    r"^this (?P<kind>[a-z]+) enters or leaves the battlefield$", re.IGNORECASE
)


def _expand_enters_or_leaves(ability: TriggeredAbility) -> list[TriggeredAbility]:
    """One ability whose condition is `_ENTERS_OR_LEAVES_RE`'s shape becomes
    two: CR 603.6a's enters-the-battlefield ability and CR 603.6c's
    leaves-the-battlefield one, each self-referential and each a
    `TriggeredAbility` in its own right - the same split
    `_expand_attacks_or_blocks` and `_expand_enters_or_attacks` already
    perform for their own compound conditions.

    Every other printed ability passes through unchanged, singleton-wrapped.
    """
    match = _ENTERS_OR_LEAVES_RE.match(ability.condition.strip())
    if match is None:
        return [ability]
    kind = match.group("kind").lower()
    return [
        ability.model_copy(
            update={
                "condition": f"this {kind} enters",
                "event": TriggerEvent.ENTERS_THE_BATTLEFIELD,
            }
        ),
        ability.model_copy(
            update={
                "condition": f"this {kind} leaves the battlefield",
                "event": TriggerEvent.LEAVES_THE_BATTLEFIELD,
            }
        ),
    ]


#: `activated_abilities_of`'s memo, keyed on `(Card.id, face)` so two
#: different printings - and the same printing asked about two different
#: faces - can never collide. Sound for the same reason `_ability_cache` in
#: `machines/abilities.py` is: `Card` is immutable (`frozen=True`), verified by
#: `tests/test_card.py::test_card_is_immutable`.
_activated_abilities_cache: dict[tuple[UUID, str | None], list[ActivatedAbility]] = {}


def activated_abilities_of(card: Card, face: str | None = None) -> list[ActivatedAbility]:
    """Every activated ability printed on a card (CR 113.3b, 602.1).

    A basic land prints none of its own - its mana ability is reminder text,
    which `parse_abilities` correctly does not treat as rules text - so a card
    with the basic supertype and no printed activated ability falls back to
    `intrinsic_land_ability` (CR 305.6). That is what lets `Game.activate_ability`
    tap a Forest at all, not only pay a mana cost with it through the
    `tap_for_mana` shortcut.

    `face` narrows the list to the abilities printed on one face, and is how a
    double-faced permanent's abilities follow the face that is up: CR 109.3
    counts abilities among an object's characteristics and CR 712.8d/712.8e/
    712.8f give such a permanent only the characteristics of the face that's
    up, so a transformed Ajani, Nacatl Pariah has Ajani, Nacatl Avenger's three
    loyalty abilities and none of his front face's, and an untransformed one has
    neither. `CardState.up_face_name` is what callers pass; `None` - every
    single-faced card - filters nothing.

    Memoised on `(card.id, face)` - see `_activated_abilities_cache`.
    """
    key = (card.id, face)
    cached = _activated_abilities_cache.get(key)
    if cached is not None:
        return cached
    printed = [
        ability
        for ability in parse_abilities(card)
        if isinstance(ability, ActivatedAbility) and (face is None or ability.face == face)
    ]
    result = printed or ([intrinsic] if (intrinsic := intrinsic_land_ability(card, face)) else [])
    _activated_abilities_cache[key] = result
    return result


def granted_activated_abilities_of(texts: Sequence[str]) -> list[ActivatedAbility]:
    """`CardState.granted_ability_texts`'s own activated lines, read the same
    way `activated_abilities_of` reads a card's printed ones.

    Urza's Saga's chapter II - "This Saga gains '{2}, {T}: Create a 0/0
    colorless Construct artifact creature token ...'" - is the reason this
    exists: without it, a granted activated ability would sit on `CardState.
    granted_ability_texts` fully parsed and completely unreachable, since
    `Game.activate_ability` only ever indexes `activated_abilities_of`'s own
    printed-card list. Callers append this to that list (never replace it),
    the same "additional to what is printed" convention `granted_mana_
    abilities` documents for the mana half.
    """
    return [
        ability
        for ability in parse_granted_ability_lines(texts)
        if isinstance(ability, ActivatedAbility)
    ]


def rewritten_ability_lines(game: "Game", permanent: CardState) -> tuple[str, ...] | None:
    """This permanent's *computed* ability text when a continuous effect has
    rewritten it away from the printed card, else None.

    CR 613.5: "The application of continuous effects as described by the layer
    system is continually and automatically performed by the game. All resulting
    changes to an object's characteristics are instantaneous." CR 109.3 counts
    abilities among an object's characteristics, so a permanent whose layer 1
    (CR 613.2c, 707.2: "the copy acquires the copiable values of the original
    object's characteristics") copy effect replaced its rules text has the
    *copied* object's abilities and none of its own - a land that has become a
    copy of Sol Ring can be tapped for `{C}{C}` and cannot be tapped for green.

    Only a rewrite is reported, never a plain grant: if every printed line
    survives into `Characteristics.abilities`, the callers' printed-plus-granted
    list is already right and keeping it keeps every ability *index* stable.
    Nothing is reported for a permanent the layer engine has not computed, or
    for one that lost all its ability text - CR 613.1f removal is already
    policed by `Game._still_has_ability`.
    """
    if permanent.zone is not Zone.BATTLEFIELD:
        return None
    try:
        computed = game.characteristics_of(permanent)
    except KeyError:
        return None
    lines = tuple(computed.abilities)
    if not lines:
        return None
    printed = [line.strip() for line in (permanent.oracle_text or "").splitlines() if line.strip()]
    if all(line in lines for line in printed):
        return None
    return lines


def added_ability_lines(game: "Game", permanent: CardState) -> tuple[str, ...]:
    """The ability lines a continuous effect *added* to this permanent on top of
    everything it prints, in computed order.

    The additive twin of `rewritten_ability_lines`, which reports only the case
    where a printed line was taken *away*. A layer 4 effect that grants a basic
    land type grants the intrinsic "{T}: Add [mana symbol]" that comes with it
    (CR 305.6, CR 613.1d) - Urborg, Tomb of Yawgmoth's Swamp, Yavimaya, Cradle
    of Growth's Forest, Dryad of the Ilysian Grove's all five - and every
    printed line survives, so `rewritten_ability_lines` correctly answers None
    and the caller keeps its printed list. That left the added mana ability
    visible on the computed board (CR 613.5) and unusable: the Forest under an
    Urborg could not actually be tapped for {B}.

    Reported separately, rather than by widening `rewritten_ability_lines`, so
    a caller can **append** these and keep every printed ability's index where
    it was - the stability `Game.activated_abilities` depends on.

    A line the permanent already carries in `granted_ability_texts` is left out,
    since those are folded in by the callers themselves and would otherwise be
    counted twice.
    """
    if permanent.zone is not Zone.BATTLEFIELD:
        return ()
    try:
        computed = game.characteristics_of(permanent)
    except KeyError:
        return ()
    printed = {line.strip() for line in (permanent.oracle_text or "").splitlines() if line.strip()}
    granted = set(permanent.granted_ability_texts)
    return tuple(line for line in computed.abilities if line not in printed and line not in granted)


def activated_abilities_from_lines(
    lines: Sequence[str], card: Card, face: str | None = None
) -> list[ActivatedAbility]:
    """`rewritten_ability_lines`' output read as activated abilities (CR 602.1).

    The same fallback `activated_abilities_of` applies: a basic land prints no
    activated ability of its own (its mana ability is reminder text), so a
    computed line list that parses to nothing falls back to
    `intrinsic_land_ability` (CR 305.6).
    """
    abilities = [
        ability
        for ability in parse_granted_ability_lines(lines)
        if isinstance(ability, ActivatedAbility)
    ]
    if abilities:
        return abilities
    intrinsic = intrinsic_land_ability(card, face)
    return [intrinsic] if intrinsic is not None else []


def granted_triggered_abilities_of(texts: Sequence[str]) -> list[TriggeredAbility]:
    """`CardState.granted_ability_texts`' own triggered abilities, read the same
    way `triggered_abilities_of` reads a card's printed ones.

    Two sources, mirroring that function exactly:

    - the granted lines that begin When, Whenever or At, expanded through the
      same compound-condition splitters a printed line goes through;
    - the granted lines that are a bare CR 702 keyword, written out by
      `machines/keywords.granted_keyword_triggered_abilities`.

    The second is what makes a *granted* evoke behave like a printed one.
    CR 702.74a: "Evoke represents two abilities: a static ability that
    functions in any zone from which the card with evoke can be cast and a
    triggered ability that functions on the battlefield." `machines/casting.py`
    executes the first when the keyword is announced; this is where the second
    comes from once the permanent is on the battlefield, and CR 400.7b -
    "effects from static abilities that grant an ability to a permanent spell
    that functions on the battlefield continue to apply to the permanent that
    spell becomes" - is why it is read off the object rather than off whatever
    granted it, which may well be dead by then.
    """
    # Imported here rather than at the top for the same cycle
    # `triggered_abilities_of` documents: `machines/keywords.py` imports this
    # module for `AbilityOnStack`.
    from .keywords import granted_keyword_triggered_abilities

    granted = [
        ability
        for ability in parse_granted_ability_lines(texts)
        if isinstance(ability, TriggeredAbility)
        and (ability.event is not None or _unread_trigger_events(ability.condition))
    ]
    expanded: list[TriggeredAbility] = []
    for ability in granted:
        for split in _expand_attacks_or_blocks(ability):
            for enters_split in _expand_enters_or_attacks(split):
                expanded.extend(_expand_enters_or_leaves(enters_split))
    return expanded + granted_keyword_triggered_abilities(texts)


def controller_of_source(game: "Game", source: CardState) -> str:
    """Whose "you" a trigger on `source` means (CR 109.5, 108.4, 108.4a).

    CR 109.5: "The words 'you' and 'your' on an object refer to the object's
    controller, its would-be controller (if a player is attempting to play,
    cast, or activate it), or its owner (if it has no controller)."

    CR 108.4: "A card doesn't have a controller unless that card represents a
    permanent or spell", and CR 108.4a: "If anything asks for the controller
    of a card that doesn't have one (because it's not a permanent or spell),
    use its owner instead."

    So the zone is what decides, not whether `CardState.controller` happens
    to be filled in: a card on the battlefield is a permanent and a card on
    the stack is a spell, and each has a real controller. A card anywhere
    else - in exile, in a graveyard, in a hand or a library - has none, and
    its owner answers instead. `CardState.controller` is not cleared by
    `move_to` and a scenario can stage an exiled card with one still on it,
    so reading it first would have quietly kept the stale value.

    This is what makes CR 702.62a's "at the beginning of *your* upkeep" the
    **owner's** upkeep for a suspended card - a card another player exiled
    with time counters (Suspended Sentence's own last line, cast by somebody
    else) still ticks on its owner's turn, exactly as `machines/casting.
    finish_suspend` already reads "you" for the third ability.

    The active player is the last resort, for a card with neither: nothing in
    a real game reaches it, since CR 108.3 gives every card in the game an
    owner.
    """
    if source.zone in (Zone.BATTLEFIELD, Zone.STACK):
        return source.controller or game.active_player.username
    return source.owner or source.controller or game.active_player.username


def triggered_abilities_on(game: "Game", source: CardState) -> list[TriggeredAbility]:
    """Every triggered ability `source` has right now, printed and granted,
    before any condition is read - the abilities `triggers_for` asks."""
    # CR 400.7b / CR 611.3d: an ability granted to this object is had by
    # this object, so it is asked here alongside the card's own printed
    # ones. Never *instead* of them - a grant adds.
    granted = granted_triggered_abilities_of(source.granted_ability_texts)
    # CR 613.5 / CR 707.2: a permanent whose computed ability text has been
    # rewritten by a layer 1 copy effect has the *copied* object's triggers
    # and not its own, so the printed card is the wrong thing to read.
    # `rewritten_ability_lines` answers None whenever nothing was taken
    # away, which is every ordinary permanent.
    rewritten = rewritten_ability_lines(game, source)
    if rewritten is not None:
        granted = granted_triggered_abilities_of(rewritten)
    else:
        # CR 613.1f / CR 613.5: a layer 6 grant ("Other creatures you
        # control are ... and have '...'") can add a triggered ability
        # this object neither prints nor carries in
        # `granted_ability_texts` - `layers.quoted_ability_grants` writes
        # it onto the computed board only. `added_ability_lines` is the
        # reader `Game.activated_abilities` already uses for the
        # identical gap on the activated-ability side (the intrinsic mana
        # ability a granted basic land type brings with it); mirrored
        # here so a granted "Whenever ..." is actually found rather than
        # granted invisibly.
        granted = granted + granted_triggered_abilities_of(added_ability_lines(game, source))
    granted_ids = {id(ability) for ability in granted}
    printed_abilities = [] if rewritten is not None else triggered_abilities_of(source.card)
    had: list[TriggeredAbility] = []
    for ability in printed_abilities + granted:
        up_face_name = source.up_face_name
        if (
            up_face_name is not None
            # A granted line was never printed on any face (its `face` is
            # the empty string), so the double-faced filter below is not
            # a question that can be asked of it - CR 712.8d is about
            # which of the *card's* two printed sides is up, and a grant
            # is on neither.
            and id(ability) not in granted_ids
            and ability.face != up_face_name
        ):
            # CR 712.8d/712.8e/712.8f: a double-faced permanent has only
            # the characteristics of the face that's up, and CR 109.3
            # counts abilities among them. Witch-Blessed Meadow, played as
            # a land (CR 712.12), has no "when this creature enters"
            # trigger, because that line was printed on Witch Enchanter's
            # face; a transformed Duskwatch Recruiter has Krallenhorde
            # Howler's upkeep trigger and not its own (CR 701.27g), and an
            # untransformed one has the mirror.
            continue
        if ability.class_level is not None and source.class_level < ability.class_level:
            # CR 716.2a: "As long as this Class is level N or greater, it
            # has [Abilities]" - a level-gated trigger printed under a
            # bar the Class has not reached yet is not "in effect", the
            # same way `CardState.class_ability_text` already keeps a
            # static ability quiet until then.
            continue
        had.append(ability)
    return had


def abilities_triggered_by(
    game: "Game", event: GameEvent, sources: list[CardState]
) -> list[tuple[CardState, TriggeredAbility, str]]:
    """`(source, ability, controller)` for every ability of `sources` this
    event would trigger (CR 603.2, CR 603.4), without triggering anything.

    Changes nothing and mints nothing, so the payment search can ask what a
    tap would set off (`machines/cost.triggered_mana_bonus`) as often as it
    likes; `triggers_for` is this plus the once-per-turn bookkeeping and the
    stack objects.
    """
    found: list[tuple[CardState, TriggeredAbility, str]] = []
    for source in sources:
        controller = controller_of_source(game, source)
        for ability in triggered_abilities_on(game, source):
            if not condition_matches(game, ability, source, controller, event):
                continue
            if source.zone not in zones_ability_functions_in(ability, source):
                continue  # CR 113.6: doesn't function from the zone it's in.
            if not intervening_if_holds(game, ability, source, event):
                continue  # CR 603.4: it does not trigger at all.
            found.append((source, ability, controller))
    return found


def triggers_for(game: "Game", event: GameEvent, sources: list[CardState]) -> list[AbilityOnStack]:
    """Every ability `sources` have that this event triggers (CR 603.2).

    The intervening *if* of CR 603.4 is checked here: an ability whose clause is
    false does not trigger at all, which is a different thing from triggering and
    then doing nothing.
    """
    triggered: list[AbilityOnStack] = []
    for source, ability, controller in abilities_triggered_by(game, event, sources):
        if ability.once_per_turn:
            # CR 603.2h: "the ability triggers only if its source's
            # controller has not yet taken the indicated action that
            # turn" - Caretaker's Talent's own "This ability triggers
            # only once each turn." `key` pairs the source with the
            # ability's own printed condition, so a permanent with more
            # than one once-per-turn trigger is tracked separately for
            # each.
            key = f"{source.id}:{ability.condition}"
            fired = game.once_per_turn_triggers.get(key, 0)
            if fired > 0:
                continue
            game.once_per_turn_triggers[key] = fired + 1
        on_stack = AbilityOnStack(
            kind=AbilityKind.TRIGGERED,
            ability=ability,
            source_id=source.id,
            source_name=source.name,
            controller=controller,
            source_stamp=source.zone_change_stamp,
            event=event,
        )
        triggered.append(on_stack)
        # CR 603.2d: "determine how many times it should trigger, then
        # trigger it that many times" - Panharmonicon. Each extra time is a
        # separate ability on the stack in its own right, with its own id.
        for _ in range(additional_trigger_times(game, on_stack, source, event)):
            triggered.append(on_stack.model_copy(update={"id": new_id()}, deep=True))
    return triggered


#: CR 603.2d's own shape, as Panharmonicon prints it: "If an artifact or
#: creature entering causes a triggered ability of a permanent you control to
#: trigger, that ability triggers an additional time."
_ADDITIONAL_TRIGGER_RE = re.compile(
    r"^if (?P<cause>.+?) causes a triggered ability of a permanent you control "
    r"to trigger, that ability triggers an additional time\.?$",
    re.IGNORECASE,
)

#: The gate half of `_ADDITIONAL_TRIGGER_RE`: "an artifact or creature entering".
_ENTERING_CAUSE_RE = re.compile(r"^an? (?P<types>[a-z ]+?) entering$", re.IGNORECASE)


def _computed_ability_lines(game: "Game", permanent: CardState) -> tuple[str, ...]:
    """This permanent's ability text as the layer system computes it (CR 613.5),
    falling back to the printed lines for a permanent the engine has not
    computed."""
    try:
        return tuple(game.characteristics_of(permanent).abilities)
    except KeyError:
        return tuple(
            line.strip() for line in (permanent.oracle_text or "").splitlines() if line.strip()
        )


def _entering_cause_matches(game: "Game", cause: str, event: GameEvent) -> bool:
    """Whether this event is the "artifact or creature entering" the multiplier
    names (CR 603.2d's own "an ability may state that a triggered ability
    triggers additional times" is gated by the rest of the printed sentence)."""
    match = _ENTERING_CAUSE_RE.match(cause.strip())
    if match is None or event.event is not TriggerEvent.ENTERS_THE_BATTLEFIELD:
        return False
    wanted = {word.strip().lower() for word in match["types"].split(" or ") if word.strip()}
    entering = game.find_by_id(event.subject_id) if event.subject_id is not None else None
    if isinstance(entering, CardState):
        try:
            types = game.characteristics_of(entering).types
        except KeyError:
            types = tuple(entering.types)
    elif event.subject_card is not None:
        types = tuple(event.subject_card.types)
    else:
        return False
    return bool(wanted & {str(card_type).lower() for card_type in types})


def additional_trigger_times(
    game: "Game", ability: AbilityOnStack, source: CardState, event: GameEvent
) -> int:
    """How many *extra* times this ability triggers, by CR 603.2d.

    CR 603.2d: "An ability may state that a triggered ability triggers
    additional times. In this case, rather than simply determining that such an
    ability has triggered, determine how many times it should trigger, then
    trigger it that many times."

    Every permanent on the battlefield is asked whether one of its own static
    ability lines is a multiplier of this shape, read off the *computed* text
    (CR 613.5). Panharmonicon is the only printing in the pool. Its own gate is
    checked here rather than assumed: the ability's source has to be a permanent
    the Panharmonicon's controller controls, and the event has to be an artifact
    or creature entering.

    Only what `triggers_for` builds from a *printed* ability is multiplied. A
    delayed triggered ability (CR 603.7a) is created during the resolution of
    the ability it belongs to and fired by `DelayedTriggers`, never by this
    function - so doubling the ability that creates a delayed trigger does not
    double the delayed trigger, which is DDR#981's whole point.
    """
    if source.zone is not Zone.BATTLEFIELD:
        return 0
    extra = 0
    for permanent in list(game.battlefield):
        controller = permanent.controller
        if controller is None or controller != ability.controller:
            continue  # "a triggered ability of a permanent **you** control".
        for line in _computed_ability_lines(game, permanent):
            match = _ADDITIONAL_TRIGGER_RE.match(line.strip())
            if match is None:
                continue
            if _entering_cause_matches(game, match["cause"], event):
                extra += 1
    return extra


#: CR 603.8's own shape, as the pool prints it: The Millennium Calendar's
#: "When there are 1,000 or more time counters on The Millennium Calendar,
#: sacrifice it and each opponent loses 1,000 life." The count is written with
#: digit-group commas, which `machines/abilities._split_top_level` already
#: refuses to read as the CR 603.1 condition/effect boundary.
_STATE_COUNTER_TRIGGER_RE = re.compile(
    r"^there are (?P<count>\d[\d,]*) or more (?P<kind>.+?) counters on (?P<subject>.+?)$",
    re.IGNORECASE,
)


def _state_trigger_abilities(game: "Game", source: CardState) -> list[TriggeredAbility]:
    """The CR 603.8 abilities this permanent has right now.

    Read off the *computed* ability text (CR 613.5, CR 109.3: abilities are
    characteristics) rather than the printed card, so a permanent that has lost
    all abilities in layer 6 (CR 613.1f) has no state trigger left - which is
    DDR#961's Tishana's Tidebinder exactly. A permanent the layer engine has
    not computed falls back to its printed text.
    """
    try:
        lines: Sequence[str] = tuple(game.characteristics_of(source).abilities)
        parsed: list[Ability] = parse_granted_ability_lines(lines)
    except KeyError:
        parsed = parse_abilities(source.card)
    return [
        ability
        for ability in parsed
        if isinstance(ability, TriggeredAbility)
        and ability.event is None
        and _STATE_COUNTER_TRIGGER_RE.match(ability.condition.strip())
    ]


def _state_condition_holds(game: "Game", ability: TriggeredAbility, source: CardState) -> bool:
    """Whether this permanent's game state matches its CR 603.8 condition."""
    match = _STATE_COUNTER_TRIGGER_RE.match(ability.condition.strip())
    if match is None:
        return False
    subject = match["subject"].strip().rstrip(".").lower()
    names = {source.name.lower(), "it", "this permanent", "this creature", "this artifact"}
    with contextlib.suppress(KeyError):
        names.add(game.characteristics_of(source).name.lower())
    if subject not in names:
        # A condition about some *other* object is not something this matcher
        # can read; answering False keeps CR 603.2's "only if it actually
        # matches" rather than guessing.
        return False
    needed = int(match["count"].replace(",", ""))
    return source.counters[match["kind"].strip().lower()] >= needed


def state_triggers_for(game: "Game") -> list[AbilityOnStack]:
    """Every CR 603.8 state trigger that has just become true.

    CR 603.8: "Some triggered abilities trigger when a game state ... is true,
    rather than triggering when an event occurs." CR 704.1a confirms these are
    triggered abilities and not state-based actions, so what comes back here is
    an ordinary `AbilityOnStack` that CR 603.3 puts on the stack the next time a
    player would receive priority.

    The rest of CR 603.8 is the latch: such an ability "doesn't trigger again
    until it has left the stack". `Game.state_trigger_latches` holds, per source
    and condition, the id of the ability that is currently holding it shut, and
    the latch opens the moment that object is neither on the stack nor waiting
    in `pending_triggers` - which is true whether it left by resolving or by
    being countered (CR 701.6a: countering "means to cancel it, removing it from
    the stack"). Countering therefore frees the trigger to fire again at once,
    which is DDR#961's whole ruling.

    Nothing is appended to `pending_triggers` here; the caller does that, the
    same way `Game.emit` owns that step for event triggers.
    """
    live = {item.id for item in game.stack if isinstance(item, AbilityOnStack)}
    live |= {item.id for item in game.pending_triggers}
    for key, ability_id in list(game.state_trigger_latches.items()):
        if ability_id not in live:
            del game.state_trigger_latches[key]

    triggered: list[AbilityOnStack] = []
    for source in list(game.battlefield):
        controller = source.controller or game.active_player.username
        for ability in _state_trigger_abilities(game, source):
            if not _state_condition_holds(game, ability, source):
                continue
            key = f"{source.id}:{ability.condition}"
            if key in game.state_trigger_latches:
                continue
            on_stack = AbilityOnStack(
                kind=AbilityKind.TRIGGERED,
                ability=ability,
                source_id=source.id,
                source_name=source.name,
                controller=controller,
                source_stamp=source.zone_change_stamp,
            )
            game.state_trigger_latches[key] = on_stack.id
            triggered.append(on_stack)
    return triggered


def apnap_order(triggered: list[AbilityOnStack], turn_order: list[str]) -> list[AbilityOnStack]:
    """Sort triggers into the order they are put on the stack (CR 603.3b).

    "First, each player, in APNAP order, puts each triggered ability they
    control on the stack in any order they choose." The active player goes
    first, so the active player's trigger ends up at the *bottom* of the pile
    and resolves last. This settles only which *player's* block goes on first -
    CR 405.3's direction too, for objects an effect puts on the stack at once.
    Within one player's set the order they triggered in is kept here, and
    `Game._order_triggers_by_controller` is what then puts CR 603.3b's "in any
    order they choose" to that player.

    A stable sort, deliberately: one controller's abilities stay contiguous, so
    the caller can walk the result and hand each run to its own controller.
    """
    rank = {username: index for index, username in enumerate(turn_order)}
    return sorted(triggered, key=lambda item: rank.get(item.controller, len(rank)))
