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

import re
from enum import StrEnum
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from ..models.card import Card, Color, Type
from ..models.card_state import CardState, Counter, TargetRef
from ..models.zone import Zone
from .abilities import (
    AbilityKind,
    ActivatedAbility,
    TriggeredAbility,
    TriggerEvent,
    intrinsic_land_ability,
    parse_abilities,
)
from .turn import Step

if TYPE_CHECKING:  # pragma: no cover - import cycle: Game builds on the machines
    from ..models.game import CastRecord, Game


class GameEvent(BaseModel):
    """One thing that happened, in the shape a trigger condition is matched against.

    CR 603.2 asks whether "a game event or game state matches a triggered
    ability's trigger event". This is that game event, reduced to the handful of
    facts the conditions in `condition_matches` actually ask about.
    """

    event: TriggerEvent

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


class TargetingNotice(BaseModel):
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


class InterveningIfNotice(BaseModel):
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


class AbilityOnStack(BaseModel):
    """An activated or triggered ability as an object on the stack (CR 113.1c).

    This is deliberately *not* a `CardState`. CR 405.1: an ability "goes on top
    of the stack without any card associated with it", so it has no zone to
    return to and never reaches a graveyard - CR 608.2n removes it from the
    stack and it ceases to exist.

    It keeps its source's id *and* its source's name, because CR 113.7a lets the
    source be destroyed while the ability is still waiting to resolve; the name
    is what is left to describe the ability once the object is gone.
    """

    id: UUID = Field(default_factory=uuid4)
    kind: AbilityKind
    ability: TriggeredAbility | ActivatedAbility
    source_id: UUID | None = None
    source_name: str
    controller: str
    targets: list[TargetRef] = Field(default_factory=list)
    event: GameEvent | None = None
    """The event that triggered it, for an effect that needs to know which
    creature attacked or what blocked what. None for an activated ability."""

    keyword_activation: Any = Field(default=None, exclude=True, repr=False)
    """The `machines/keywords.KeywordActivation` this ability came from, if any.

    `machines/effects.py` keys an ability's effect by the name of the card it is
    printed on. A CR 702 keyword's ability is printed on no card in particular -
    cycling (CR 702.29a) and equip (CR 702.6a) are the same ability wherever
    they appear - so there is no name to key it under and the effect lives with
    the keyword instead.

    This is the link back. `machines/keywords.keyword_effect_for` reads it, and
    it is the one thing a resolver needs to run a keyword's effect through the
    ordinary CR 608.2 path rather than by hand. Excluded from serialisation,
    because the activation holds a live `Game`.
    """

    unless_payment: Any = Field(default=None, exclude=True, repr=False)
    """The `machines/cost.CostPayment` made for an "unless that player pays" clause.

    CR 702.21a's ward is the one ability of this shape the engine produces:
    "counter that spell or ability unless that player pays [cost]". The cost is
    paid *as the ability resolves*, so the payment has to live on the ability
    that is on the stack - **the object that is paid must be the object that
    resolves**. `machines/keywords.WardTrigger` is the view that opens it and
    `machines/keywords._ward_effect` is what reads it back.

    Excluded from serialisation, because a `CostPayment` holds a live `Game`.
    """

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


def tapped_for_mana_event(source: CardState) -> GameEvent:
    """CR 106.12a: this permanent's mana ability just resolved and produced mana.

    Built once and reused by every place the engine taps something for mana -
    `machines/cost.CostPayment.tap_for_mana` (tapping a land to pay a total
    cost) and `Game.activate_ability`'s mana-ability fast path (CR 605.3b: the
    ability itself never reaches the stack, but the event still happens) -
    so the two call sites cannot drift apart on what the event looks like.
    """
    return GameEvent(
        event=TriggerEvent.TAPPED_FOR_MANA,
        subject_id=source.id,
        subject_name=source.name,
        subject_controller=source.controller,
        subject_card=source.card,
        subject_types=source.types,
        subject_subtypes=source.subtypes,
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


def _required_subtype(condition: str) -> str | None:
    match = _OTHER_SUBTYPE.search(condition)
    return match.group(1) if match else None


def _subtype_matches(subtypes: tuple[str, ...] | None, subtype: str | None) -> bool:
    """Whether `subtypes` names `subtype` (CR 712.8f). See `_types_match`'s
    docstring for why this reads `GameEvent.subject_subtypes`, not a raw
    `Card`."""
    if subtype is None:
        return True
    if subtypes is None:
        return False
    return any(word.lower() == subtype.lower() for word in subtypes)


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


def condition_matches(
    ability: TriggeredAbility,
    source: CardState,
    controller: str,
    event: GameEvent,
) -> bool:
    """Whether this printed condition is matched by this event (CR 603.2).

    The shapes read, one per `TriggerEvent`:

    - **enters** (CR 603.6a) - "When this creature enters" fires for the source
      itself; "Whenever [another] [type] you control enters" fires for another
      permanent of that type.
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
      "Whenever you cast a[n] [type] spell" for anything that player casts.
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

    Anything else returns False. A condition this module cannot read never fires
    a trigger, which is the safe direction to be wrong in.
    """
    condition = ability.condition
    lowered = condition.lower()
    mine = _self_referential(condition, source.name)

    if event.event is not ability.event:
        return False

    if ability.event is TriggerEvent.ENTERS_THE_BATTLEFIELD:
        if mine:
            return event.subject_id == source.id
        if "another" in lowered and event.subject_id == source.id:
            return False
        return _controller_clause_holds(
            condition, controller, event.subject_controller
        ) and _types_match(event.subject_types, condition)

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
        return _controller_clause_holds(condition, controller, event.player) and _types_match(
            event.subject_types, condition
        )

    if ability.event is TriggerEvent.EXILED:
        # CR 702.35a: "When this card is exiled this way". Only the
        # self-referential form is read, which is the only form madness prints;
        # the "this way" is enforced by the emitter, which raises the event only
        # for the exile the madness replacement performed.
        return mine and event.subject_id == source.id

    if ability.event is TriggerEvent.BECOMES_TARGET:
        # CR 702.21a: "Whenever this permanent becomes the target of a spell or
        # ability an opponent controls". Only the self-referential form is read,
        # which is the only form ward prints.
        if not mine or event.subject_id != source.id:
            return False
        if "an opponent controls" in lowered:
            return event.player is not None and event.player != controller
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
        # type. Nothing in the pool prints the self-referential form.
        return _controller_clause_holds(
            condition, controller, event.subject_controller
        ) and _types_match(event.subject_types, condition)

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
_LOOK_BACK_EVENTS = (
    TriggerEvent.DIES,
    TriggerEvent.IS_SACRIFICED,
    TriggerEvent.SPELL_IS_COUNTERED,
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

    # CR 603.10a: dies, is-sacrificed and countered triggers look back at the
    # object as it existed immediately beforehand, so they function from the
    # battlefield the source just left as well as wherever it ended up -
    # `source.zone` already reflects the post-event location, since these are
    # exactly the events `Game.emit` widens `sources` for after the move has
    # already happened.
    if ability.event in _LOOK_BACK_EVENTS:
        return frozenset({Zone.BATTLEFIELD, source.zone})

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

#: CR 601.2h's "no mana was spent to cast it" (Vexing Bauble) and "[mana
#: symbols] was spent to cast it" (Wistfulness's "{G}{G}", Drowner of Truth's
#: "{C}") - both always phrased as "... to cast it" in the pool, never "...
#: to cast this spell/creature".
_NO_MANA_SPENT_CLAUSE = re.compile(r"^no mana was spent to cast it$")
_MANA_SPENT_CLAUSE = re.compile(r"^(?P<symbols>(?:\{[wubrgc]\})+) was spent to cast it$")
_MANA_SYMBOL_LETTER = re.compile(r"\{([wubrgc])\}")
_COLOR_LETTERS: dict[str, Color] = {
    "w": Color.WHITE,
    "u": Color.BLUE,
    "b": Color.BLACK,
    "r": Color.RED,
    "g": Color.GREEN,
    "c": Color.COLORLESS,
}


def _cast_record_for_clause(
    game: "Game", ability: TriggeredAbility, source: CardState, event: "GameEvent | None"
) -> "CastRecord | None":
    """The `CastRecord` a mana-spent or kicked clause's "it" refers to, or
    `None` if there is no longer one to read.

    A self-referential clause - Sowing Mycospawn's "if it was kicked" ("it" is
    "this spell"), Wistfulness's and Drowner of Truth's "if ... was spent to
    cast it" ("it" is "this creature"/"this spell") - means the ability's own
    source, whose id is unchanged whether it is still a spell on the stack or
    has since resolved onto the battlefield (CR 400.7 moves the object, not its
    identity). Vexing Bauble's "Whenever a player casts a spell, if no mana was
    spent to cast it" is not self-referential at all: "it" is *that* spell, the
    trigger event's own subject, not Vexing Bauble itself.

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
        return game.cast_records.get(subject.id)
    return game.cast_records.get(source.id)


def intervening_if_holds(
    game: "Game",
    ability: TriggeredAbility,
    source: CardState,
    event: "GameEvent | None" = None,
) -> bool:
    """Whether an intervening *if* clause is true right now (CR 603.4, 608.2a).

    "When the trigger event occurs, the ability checks whether the stated
    condition is true. The ability triggers only if it's true" (CR 603.4);
    CR 608.2a rechecks the same clause again as the ability resolves.

    Clause shapes read: persist's "it had no -1/-1 counters on it"
    (CR 702.79a), Thopter Assembly's "you control no [subtype]s other than
    this creature", Ocelot Pride's "you gained life this turn", Alania,
    Divergent Storm's "it's the first [type] spell ... you've cast this turn",
    kicker's "if it was kicked" (CR 702.33a, 702.33d), and CR 601.2h's "if no
    mana was spent to cast it" / "if [mana symbols] was spent to cast it"
    (Vexing Bauble, Wistfulness, Drowner of Truth). The last two read
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

    if _KICKED_CLAUSE.match(clause):
        record = _cast_record_for_clause(game, ability, source, event)
        if record is None:
            return _fail_closed(game, ability, source)
        return record.kicked > 0

    if _NO_MANA_SPENT_CLAUSE.match(clause):
        record = _cast_record_for_clause(game, ability, source, event)
        if record is None:
            return _fail_closed(game, ability, source)
        return not record.any_mana_spent

    mana_match = _MANA_SPENT_CLAUSE.match(clause)
    if mana_match is not None:
        record = _cast_record_for_clause(game, ability, source, event)
        if record is None:
            return _fail_closed(game, ability, source)
        required: dict[Color, int] = {}
        for letter in _MANA_SYMBOL_LETTER.findall(mana_match.group("symbols")):
            color = _COLOR_LETTERS[letter]
            required[color] = required.get(color, 0) + 1
        return all(record.mana_of_color_spent(color) >= count for color, count in required.items())

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
        others = [
            state
            for state in game.permanents_controlled_by(controller)
            if state.id != source.id and any(word.lower() == subtype for word in state.subtypes)
        ]
        return not others

    if clause == "you gained life this turn":
        controller = source.controller or game.active_player.username
        return controller in game.life_gained_this_turn

    first_spell = _first_spell_this_turn_holds(game, clause, source, event)
    if first_spell is not None:
        return first_spell

    last_turn = _spells_cast_last_turn_holds(game, clause)
    if last_turn is not None:
        return last_turn

    return _fail_closed(game, ability, source)


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
        if isinstance(ability, TriggeredAbility) and ability.event is not None
    ]
    return printed + keyword_triggered_abilities(card)


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
    """
    printed = [
        ability
        for ability in parse_abilities(card)
        if isinstance(ability, ActivatedAbility) and (face is None or ability.face == face)
    ]
    if printed:
        return printed
    intrinsic = intrinsic_land_ability(card)
    return [intrinsic] if intrinsic is not None else []


def triggers_for(game: "Game", event: GameEvent, sources: list[CardState]) -> list[AbilityOnStack]:
    """Every ability `sources` have that this event triggers (CR 603.2).

    The intervening *if* of CR 603.4 is checked here: an ability whose clause is
    false does not trigger at all, which is a different thing from triggering and
    then doing nothing.
    """
    triggered: list[AbilityOnStack] = []
    for source in sources:
        controller = source.controller or game.active_player.username
        for ability in triggered_abilities_of(source.card):
            up_face_name = source.up_face_name
            if up_face_name is not None and ability.face != up_face_name:
                # CR 712.8d/712.8e/712.8f: a double-faced permanent has only
                # the characteristics of the face that's up, and CR 109.3
                # counts abilities among them. Witch-Blessed Meadow, played as
                # a land (CR 712.12), has no "when this creature enters"
                # trigger, because that line was printed on Witch Enchanter's
                # face; a transformed Duskwatch Recruiter has Krallenhorde
                # Howler's upkeep trigger and not its own (CR 701.27g), and an
                # untransformed one has the mirror.
                continue
            if not condition_matches(ability, source, controller, event):
                continue
            if source.zone not in zones_ability_functions_in(ability, source):
                continue  # CR 113.6: doesn't function from the zone it's in.
            if not intervening_if_holds(game, ability, source, event):
                continue  # CR 603.4: it does not trigger at all.
            triggered.append(
                AbilityOnStack(
                    kind=AbilityKind.TRIGGERED,
                    ability=ability,
                    source_id=source.id,
                    source_name=source.name,
                    controller=controller,
                    event=event,
                )
            )
    return triggered


def apnap_order(triggered: list[AbilityOnStack], turn_order: list[str]) -> list[AbilityOnStack]:
    """Sort triggers into the order they are put on the stack (CR 603.3b).

    "First, each player, in APNAP order, puts each triggered ability they
    control on the stack in any order they choose." The active player goes
    first, so the active player's trigger ends up at the *bottom* of the pile
    and resolves last. Within one player's set the order they triggered in is
    kept, which the rules leave to the player.
    """
    rank = {username: index for index, username in enumerate(turn_order)}
    return sorted(triggered, key=lambda item: rank.get(item.controller, len(rank)))
