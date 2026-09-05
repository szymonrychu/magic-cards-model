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

import re
from collections.abc import Callable
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from ..models.card import Type
from ..models.card_state import CardState
from ..models.zone import Zone
from .abilities import AbilityKind, TriggeredAbility, TriggerEvent, TriggerWord
from .triggers import AbilityOnStack, GameEvent
from .turn import Step

if TYPE_CHECKING:
    from ..models.game import Game

#: What a delayed triggered ability does when it resolves. Keyed by the string
#: in `DelayedTrigger.effect`, or carried directly on `DelayedTrigger.callback`.
DelayedEffect = Callable[["Game", AbilityOnStack, "DelayedTrigger"], None]


class DelayedTrigger(BaseModel):
    """One delayed triggered ability, waiting for its event (CR 603.7)."""

    id: UUID = Field(default_factory=uuid4)

    text: str
    """The ability as it would read on a card, for the stack listing and for a
    failure message. CR 603.7 says the word "when"/"whenever"/"at" is in there
    somewhere even though it does not usually begin the ability."""

    effect: str = ""
    """The key into `DELAYED_EFFECTS`, for the hand-written entries (warp,
    Emrakul's extra turn, and the test-only sacrifice helper) that predate
    `callback`. Left empty when `callback` is set instead."""

    callback: Any = Field(default=None, exclude=True, repr=False)
    """A `DelayedEffect`, or `None`. Typed `Any` rather than `DelayedEffect`
    itself for the same reason `AbilityOnStack.keyword_activation` is
    (`machines/triggers.py`): a `Callable[["Game", ...], None]` field forces
    pydantic to resolve the forward reference to `Game` when the schema is
    built, which is before `Game` exists in this module's world.

    What this ability does, read straight off a card's own printed text by
    `machines/effects.py`'s delayed-trigger clause parser, with no registry
    row. `DELAYED_EFFECTS` used to be the only way in, and its own docstring's
    justification - "the ability has no printed text to read" - never held for
    a delayed trigger a card prints itself (Phelia, Exuberant Shepherd's own
    "at the beginning of the next end step, return that card ..."), so a
    parsed clause carries its own callable here instead of adding another
    name-keyed row. Checked ahead of `effect`/`DELAYED_EFFECTS` in
    `DelayedTriggers.effect_for`."""

    event: TriggerEvent | None = None
    """The event to watch for, in the vocabulary `Game.emit` already speaks.

    `None` only for a reflexive triggered ability (CR 603.12, see
    `DelayedTriggers.create_reflexive`): CR 603.12 checks that ability
    "immediately after being created" against whether its trigger event
    "occurred earlier during the resolution of the spell or ability that
    created it" - which by construction it already has, since the caller
    only reaches `create_reflexive` once that action has actually happened.
    There is nothing left to watch for, so the record is never appended to
    `DelayedTriggers.triggers` and `matches`/`fire` never see it; `None` here
    just satisfies this field rather than borrowing an unrelated
    `TriggerEvent` member that would be misleading to read."""

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

    expected_stamp: UUID | None = None
    """`CardState.zone_change_stamp` as it was when this trigger was created
    (CR 603.7c's parenthetical): "if that object left that zone and then
    returned, it's a new object and thus won't be affected." A same-`id`,
    same-zone match is not enough to prove that - `still_affects` also
    requires the stamp to match, so an object that round-tripped through
    another zone and landed back in `expected_zone` by some other route is
    correctly refused. `None` skips the check, for a trigger built before this
    existed."""

    remaining: int | None = 1
    """How many more times this may trigger (CR 603.7b). One unless the ability
    has a stated duration; None means "no limit", for a duration-bounded ability
    that fires on every occurrence."""

    subjectless_only: bool = False
    """Match only an event with no `subject_id` at all - CR 508.3d's "you
    attack" shape (`machines/triggers.py`'s own `condition_matches` reads the
    identical `event.subject_id is None` for the ordinary, printed version of
    this trigger). `Game.declare_attackers` emits *two* `ATTACKS` events per
    attack declared with one or more attackers: one per attacking creature
    (`subject_id` set) and one subjectless summary, once per attacking
    player. Dalkovan Encampment's delayed trigger has no per-creature meaning
    at all ("whenever you attack", not "whenever this creature attacks"), so
    without this it would match both and fire twice per declaration -
    `test_dalkovan_encampment_creates_warriors_tapped_and_attacking` is the
    regression guard."""

    expires_end_of_turn: bool = False
    """CR 603.7b's "unless it has a stated duration, such as 'this turn'":
    Dalkovan Encampment's "Whenever you attack this turn" is exactly that
    stated duration - `remaining=None` lets it fire on every attack for the
    rest of the turn rather than only once, and this flag is what stops it
    from also firing on next turn's attack. CR 514.2 ends every "this turn"
    effect in the cleanup step, so `DelayedTriggers.expire_this_turn` (called
    from `Game.cleanup_step`, alongside `ContinuousEffects.end_the_turn`) is
    what actually drops it - matching does not check the calendar itself."""

    sibling_ids: tuple[UUID, ...] = ()
    """Other `DelayedTrigger`s created alongside this one that watch for a
    different event but the same underlying CR 603.7a ability - earthbend's
    "when that land dies **or** is put into exile" is one ability watching two
    events, represented as two `DelayedTrigger`s since each of those only
    watches one. Read by `machines/effects.py`'s earthbend callback to drop
    the sibling once either half fires, so a one-shot ability does not sit
    around forever after it has already done its job."""

    def matches(self, event: GameEvent) -> bool:
        """Whether this event is the one being waited for (CR 603.2, 603.7b).

        Every delayed trigger shipped before earthbend watches
        `BEGINNING_OF_STEP`, whose `GameEvent` never carries a `subject_id` -
        so this subject check was never reachable and the latent bug below
        never surfaced. Earthbend is the first *event-keyed, subject-scoped*
        delayed trigger (CR 701.66a's "when that land dies or is put into
        exile"): without this check, a `DIES`-keyed trigger watching one
        specific land matched *any* creature's death, and CR 603.7b's
        one-shot `remaining` was spent on the wrong one - the real death
        would then find nothing left waiting. Guarded on both sides being
        non-None so a subject-less trigger (draw a card, grant an extra turn)
        and a step event (which never has a subject at all) are unaffected.
        """
        if self.remaining is not None and self.remaining <= 0:
            return False
        if event.event is not self.event:
            return False
        if self.step is not None and event.step is not self.step:
            return False
        if self.subjectless_only and event.subject_id is not None:
            return False
        if (
            self.subject_id is not None
            and event.subject_id is not None
            and event.subject_id != self.subject_id
        ):
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
        if self.expected_stamp is not None and found.zone_change_stamp != self.expected_stamp:
            # CR 603.7c's parenthetical: same zone, same `id`, but a different
            # incarnation - it left and came back, so it is a new object.
            return None
        return found


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


def exile_subject_at_next_end_step(
    game: "Game", ability: AbilityOnStack, trigger: DelayedTrigger
) -> None:
    """ "Exile it at the beginning of the next end step" - Postmortem Lunge's
    own delayed exile of the creature it just returned to the battlefield
    (CR 701.13a: "To exile an object, move it to the exile zone from wherever
    it is"). CR 603.7c is what stops this reaching a permanent that already
    left the battlefield some other way - destroyed in response, sacrificed,
    or bounced - before the delayed step arrived.
    """
    permanent = trigger.still_affects(game)
    if permanent is not None:
        game.exile_permanent(permanent)


def return_subject_to_battlefield_under_owner(
    game: "Game", ability: AbilityOnStack, trigger: DelayedTrigger
) -> None:
    """ "At the beginning of the next end step, return that card to the
    battlefield under its owner's control" - Phelia, Exuberant Shepherd's
    shape, and the blink idiom generally (Blizzard Strix, Angel of
    Condemnation, Astral Drift).

    CR 610.3c: "An object returned to the battlefield this way returns under
    its owner's control unless otherwise specified" - the owner, not whoever
    controlled it before it left, which is why this reads `owner` rather than
    `controller_or_owner`. CR 110.5b: permanents enter untapped by default,
    and nothing here retaps it - it left `tapped=False` on the way into exile
    (`CardState.move_to`) and nothing has touched it since. CR 603.7c is what
    stops this reaching a permanent that is no longer where it was exiled to,
    or that left and came back as a new object (`expected_stamp`).

    A token never gets here in the first place: `CardState.exile_permanent`
    already ran without objection to put it into exile, but CR 111.8 refuses a
    *second* zone change for a token that has already left the battlefield
    once, so `Game.put_onto_battlefield` (via `enter_the_battlefield`) silently
    declines and the token stays in exile - where CR 111.7/704.5d already
    destines it to cease to exist as a state-based action.
    """
    permanent = trigger.still_affects(game)
    if permanent is None or permanent.owner is None:
        return
    game.put_onto_battlefield(permanent, permanent.owner, tapped=False)


def return_subject_to_hand(game: "Game", ability: AbilityOnStack, trigger: DelayedTrigger) -> None:
    """ "Return it to its owner's hand at the beginning of the next end step" -
    Aether Membrane's and dash's shape. `Game.return_to_hand` already goes to
    the *owner's* hand, whoever controls it now.

    Dash is **CR 702.109a**: "Dash represents three abilities: two static
    abilities that function while the card with dash is on the stack, one of
    which may create a delayed triggered ability, and a static ability that
    functions while the object with dash is on the battlefield." That delayed
    triggered ability is this one. (This docstring cited CR 701.19a until now,
    which is Regenerate - a number nobody had looked up.)
    """
    permanent = trigger.still_affects(game)
    if permanent is not None:
        game.return_to_hand(permanent)


def rebound_recast(game: "Game", ability: AbilityOnStack, trigger: DelayedTrigger) -> None:
    """CR 702.88a's own recast: "At the beginning of your next upkeep, you may
    cast this card from exile without paying its mana cost."

    Optional (`Game.may`), and only for the exact card this rebound sent to
    exile: `still_affects` is CR 603.7c's check that it is still there,
    unmoved by anything else, when this trigger finally resolves - a rebound
    card someone managed to remove from exile in the meantime is not cast at
    all, rather than this reaching for whatever else has `subject_id`'s id
    now (CR 400.7 - once it moves again, it is a new object).

    `Game.cast_free_from_exile` is where CR 702.88b's alternative-cost
    casting actually happens, and where the card's own new targets (CR
    601.2c) are chosen; this function only asks whether to do it at all.
    """
    card = trigger.still_affects(game)
    if card is None:
        return
    prompt = f"cast {card.name} from exile without paying its mana cost"
    if not game.may(trigger.controller, prompt, source=card.name):
        return
    game.cast_free_from_exile(card, trigger.controller, keyword="Rebound")


def draw_a_card_for_controller(
    game: "Game", ability: AbilityOnStack, trigger: DelayedTrigger
) -> None:
    """ "Draw a card at the beginning of the next turn's upkeep" - Mishra's
    Bauble's second half. No object is named at all (CR 603.7c has nothing to
    check), so this is the creating ability's controller, drawing on their own
    behalf (CR 121.2).
    """
    if game.is_in_game(trigger.controller):
        game.draw_cards(trigger.controller, 1)


def destroy_subject(game: "Game", ability: AbilityOnStack, trigger: DelayedTrigger) -> None:
    """ "Destroy it at the beginning of the next end step" - CR 701.8a: "To
    destroy a permanent, move it from the battlefield to its owner's
    graveyard." Distinct from the sacrifice above (CR 701.21a) because
    destruction can be regenerated or replaced and sacrifice cannot;
    `Game.destroy` is where that difference lives. CR 603.7c is the usual
    guard on the object still being where the ability expects it.
    """
    permanent = trigger.still_affects(game)
    if permanent is not None:
        game.destroy(permanent)


def tap_subject(game: "Game", ability: AbilityOnStack, trigger: DelayedTrigger) -> None:
    """ "Tap it at the beginning of the next turn's upkeep" - CR 701.26a: "To
    tap a permanent, turn it sideways from an upright position. Only untapped
    permanents can be tapped." `CardState.tap` is a no-op on a permanent that
    is already tapped, which is that second sentence.
    """
    permanent = trigger.still_affects(game)
    if permanent is not None:
        permanent.tap()


DELAYED_EFFECTS: dict[str, DelayedEffect] = {
    "warp:exile": _exile_warped,
    "grant_extra_turn": _grant_extra_turn,
    "sacrifice": _sacrifice_subject,
}


# ---------------------------------------------------------------------------
# The anaphoric delayed triggered ability
# ---------------------------------------------------------------------------
#
# Every delayed trigger above is *built by hand* at a call site that already
# knows which object it is about. That covers the shapes whose object the
# calling code chose itself - warp's own permanent, dash's own creature, the
# Pact's own controller - but not the shape that is by far the most common in
# print:
#
#     Return target legendary creature card from your graveyard to the
#     battlefield. That creature gains haste. **Exile it** at the beginning of
#     the next end step.
#
# The last sentence names no object at all. "It" is *anaphoric*: it means
# whatever the paragraph's own first sentence just moved, and nothing in the
# sentence's text can say which permanent that turned out to be - the target
# was chosen on announcement (CR 601.2c) and the object that ends up on the
# battlefield is a new one (CR 400.7), discovered only as the first sentence
# actually runs.
#
# That is why the shape needs a primitive rather than another hand-written
# row: the *text* is fully readable, and only the referent has to come from
# the caller. `parse_anaphoric_delayed_clause` reads the text; the caller
# supplies the referent to `AnaphoricDelayedClause.trigger_for` (or to the
# one-call `anaphoric_delayed_trigger`) at the moment its own earlier sentence
# produced it.
#
# CR 603.7c is what makes the referent more than an id: "A delayed triggered
# ability that refers to a particular object still affects it even if the
# object changes characteristics. However, if that object is no longer in the
# zone it's expected to be in at the time the delayed triggered ability
# resolves, the ability won't affect it." So the trigger records the zone the
# *verb* implies as `expected_zone`, and `expected_stamp` for that rule's
# parenthetical about an object that left and came back. Both are already
# checked by `still_affects`; this just fills them in correctly, which a
# hand-written call site regularly forgets to.
#
# CR 603.7d/e give the source and controller: the creating spell's own, taken
# as it resolved. They are parameters here for the same reason - only the
# caller knows what created this.

#: Which step each printed timing phrase waits for, in the shape
#: `TriggerEvent.BEGINNING_OF_STEP` and `DelayedTrigger.step` already speak.
#:
#: CR 500.6: "When a phase or step begins, any abilities that trigger 'at the
#: beginning of' that phase or step trigger", and CR 511.2: "Abilities that
#: trigger 'at end of combat' trigger as the end of combat step begins" - the
#: same event, a different step, which is why "at end of combat" needs no
#: separate machinery.
#:
#: CR 513.2 is why waiting for the *next* occurrence needs no bookkeeping at
#: all: "If a permanent with an ability that triggers 'at the beginning of the
#: end step' enters the battlefield during this step, that ability won't
#: trigger until the next turn's end step. Likewise, if a delayed triggered
#: ability that triggers 'at the beginning of the next end step' is created
#: during an end step, that ability won't trigger until the next turn's end
#: step." The event for the current occurrence of a step has already been
#: emitted by the time a trigger created during it could see it, so `matches`
#: never fires on the step it was born in.
#:
#: Deliberately a duplicate of `machines/effects.py`'s own private
#: `_DELAYED_TIMING_STEPS` rather than an import: `effects.py` imports this
#: module, so the dependency can only run one way. When Task 2.11 wires the
#: call site, `effects.py`'s copy should be deleted in favour of this one.
ANAPHORIC_TIMING_STEPS: dict[str, Step] = {
    "the beginning of the next end step": Step.END_STEP,
    "the beginning of the next turn's upkeep": Step.UPKEEP,
    "the beginning of your next upkeep": Step.UPKEEP,
    "end of combat": Step.END_OF_COMBAT,
}

_TIMING_PATTERN = "|".join(re.escape(phrase) for phrase in ANAPHORIC_TIMING_STEPS)

#: "At <timing>, <instruction>." - Phelia, Exuberant Shepherd's word order.
_TIMING_LEADING_RE = re.compile(
    rf"^at (?P<timing>{_TIMING_PATTERN}),\s*(?P<instruction>.+)$", re.IGNORECASE
)
#: "<Instruction> at <timing>." - Goryo's Vengeance's, Postmortem Lunge's and
#: Fire Navy Trebuchet's word order.
_TIMING_TRAILING_RE = re.compile(
    rf"^(?P<instruction>.+?)\s+at (?P<timing>{_TIMING_PATTERN})$", re.IGNORECASE
)

#: The pronouns a delayed clause uses for the object its own paragraph just
#: acted on, mapped to what the referent must actually be for the pronoun to
#: agree with it.
#:
#: A bare "it" constrains nothing. The demonstratives do: "that token" is Fire
#: Navy Trebuchet naming the token it just created, and CR 108.2b ("Tokens
#: aren't considered cards") is why the mirror matters too - a clause reading
#: "that card" was never about a token, and CR 111.8 is the consequence if one
#: is handed over anyway ("A token that has left the battlefield can't move to
#: another zone or come back onto the battlefield"), a blink that would
#: silently do nothing.
#:
#: The agreement is checked when the ability is *created*, not when it
#: resolves. CR 603.7c is explicit that the object may change characteristics
#: afterwards and still be affected, so re-checking "that creature" at
#: resolution would be wrong.
_ANAPHOR_AGREEMENT: dict[str, Callable[[CardState], bool]] = {
    "it": lambda state: True,
    "that permanent": lambda state: state.is_permanent,
    "that card": lambda state: not state.token,  # CR 108.2b
    "that token": lambda state: state.token,  # CR 111.1
    "that creature": lambda state: state.is_creature,
    "that creature token": lambda state: state.token and state.is_creature,
    "that artifact": lambda state: Type.ARTIFACT in state.types,
    "that land": lambda state: Type.LAND in state.types,
    "that enchantment": lambda state: Type.ENCHANTMENT in state.types,
}

_ANAPHOR_PATTERN = "|".join(
    re.escape(phrase) for phrase in sorted(_ANAPHOR_AGREEMENT, key=len, reverse=True)
)

#: "<verb> <anaphor>" for the verbs that take the object directly.
_SIMPLE_VERB_RE = re.compile(
    rf"^(?P<verb>exile|sacrifice|destroy|tap) (?P<anaphor>{_ANAPHOR_PATTERN})$",
    re.IGNORECASE,
)
#: "return <anaphor> to <destination>" - the two destinations that recur.
#: "your hand" is the same destination as "its owner's hand" here, and CR 400.3
#: is why: "if an object would go to any library, graveyard, or hand other than
#: its owner's, it goes to its owner's corresponding zone." A card Ilharg, the
#: Raze-Boar put onto the battlefield out of your own hand is one you own, so
#: the two phrasings name the same zone; `Game.return_to_hand` sends it to the
#: owner's hand either way, which is the only thing the rules permit.
_RETURN_RE = re.compile(
    rf"^return (?P<anaphor>{_ANAPHOR_PATTERN}) to "
    r"(?P<destination>its owner's hand|your hand|the battlefield under its owner's control)$",
    re.IGNORECASE,
)

#: What each verb does, and where CR 603.7c should expect to find the object
#: when the ability resolves.
#:
#: The expected zone is a property of the *verb*, not a caller's choice: a
#: sacrifice, a destruction, a tap and a return-to-hand all act on a permanent
#: and so wait for the battlefield (CR 701.21a, 701.8a, 701.26a), while a
#: return *to* the battlefield is waiting for a card in exile - the blink
#: idiom, where the object was put there by the same paragraph's earlier
#: sentence. Exile is the exception with no zone of its own: CR 701.13a is "To
#: exile an object, move it to the exile zone from wherever it is", but every
#: printed anaphoric use of it (Goryo's Vengeance, Postmortem Lunge) is
#: exiling the permanent that sentence one put onto the battlefield, and the
#: whole point of CR 603.7c is that one which has since died is *not* to be
#: dug out of the graveyard.
_ANAPHORIC_VERBS: dict[str, tuple[DelayedEffect, Zone]] = {
    "exile": (exile_subject_at_next_end_step, Zone.BATTLEFIELD),
    "sacrifice": (_sacrifice_subject, Zone.BATTLEFIELD),
    "destroy": (destroy_subject, Zone.BATTLEFIELD),
    "tap": (tap_subject, Zone.BATTLEFIELD),
    "return_to_hand": (return_subject_to_hand, Zone.BATTLEFIELD),
    "return_to_battlefield": (return_subject_to_battlefield_under_owner, Zone.EXILE),
}


class AnaphoricDelayedClause(BaseModel):
    """One delayed-trigger clause (CR 603.7) whose subject is a pronoun,
    read off the printed text but not yet attached to an object.

    Everything here comes from the clause itself. The referent does not, and
    cannot: see the module comment above `ANAPHORIC_TIMING_STEPS`. Call
    `trigger_for` with the object the caller's own earlier sentence produced.
    """

    model_config = ConfigDict(frozen=True)

    text: str
    """The clause as printed, for `DelayedTrigger.text` and the stack listing."""

    step: Step
    """The step CR 500.6 / CR 511.2 will trigger this at."""

    anaphor: str
    """The pronoun, lowercased - a key of `_ANAPHOR_AGREEMENT`."""

    verb: str
    """A key of `_ANAPHORIC_VERBS`: what this does when it resolves."""

    def agrees_with(self, subject: CardState) -> bool:
        """Whether `subject` is the kind of object this clause's pronoun names.

        Checked at creation time only - CR 603.7c lets the object change
        characteristics afterwards and still be affected.
        """
        return _ANAPHOR_AGREEMENT[self.anaphor](subject)

    @property
    def expected_zone(self) -> Zone:
        """Where CR 603.7c will expect the object to be when this resolves."""
        return _ANAPHORIC_VERBS[self.verb][1]

    @property
    def callback(self) -> DelayedEffect:
        """What this does when it resolves."""
        return _ANAPHORIC_VERBS[self.verb][0]

    def trigger_for(
        self,
        subject: CardState,
        *,
        controller: str,
        source_id: UUID | None,
        source_name: str,
    ) -> DelayedTrigger | None:
        """The delayed triggered ability this clause creates about `subject`
        (CR 603.7a: it exists from now, and not one moment earlier).

        `None` when the pronoun does not agree with the object handed over -
        the caller reached for the wrong thing, and refusing is the project's
        fail-closed invariant rather than acting on a permanent the card never
        named.

        CR 603.7d/e: `controller`, `source_id` and `source_name` are the
        creating spell or ability's own, taken as it resolved, which is why
        they are the caller's to supply and not inferred from `subject`.
        """
        if not self.agrees_with(subject):
            return None
        return DelayedTrigger(
            text=self.text,
            event=TriggerEvent.BEGINNING_OF_STEP,
            step=self.step,
            controller=controller,
            source_id=source_id,
            source_name=source_name,
            subject_id=subject.id,
            expected_zone=self.expected_zone,
            expected_stamp=subject.zone_change_stamp,
            callback=self.callback,
        )


def parse_anaphoric_delayed_clause(clause: str) -> AnaphoricDelayedClause | None:
    """Read one printed clause as an anaphoric delayed triggered ability, or
    `None` if it is not one.

    `None` covers three different refusals and deliberately does not
    distinguish them, because the caller's response to all three is the same -
    fail the whole paragraph closed:

    - no timing phrase at all, so it is an ordinary instruction rather than a
      delayed one (CR 603.7's "when"/"whenever"/"at" is absent);
    - a timing phrase or verb outside what this reads;
    - a subject that is *not* a pronoun ("exile that creature card"), which
      names its own object and so is not this shape's problem to solve.
    """
    clause = clause.strip().rstrip(".")
    match = _TIMING_LEADING_RE.fullmatch(clause) or _TIMING_TRAILING_RE.fullmatch(clause)
    if match is None:
        return None
    step = ANAPHORIC_TIMING_STEPS.get(match.group("timing").lower())
    if step is None:
        return None
    instruction = match.group("instruction").strip().rstrip(".")

    simple = _SIMPLE_VERB_RE.fullmatch(instruction)
    if simple is not None:
        verb = simple.group("verb").lower()
        anaphor = simple.group("anaphor").lower()
    else:
        returning = _RETURN_RE.fullmatch(instruction)
        if returning is None:
            return None
        anaphor = returning.group("anaphor").lower()
        verb = (
            "return_to_hand"
            if returning.group("destination").lower() in ("its owner's hand", "your hand")
            else "return_to_battlefield"
        )

    return AnaphoricDelayedClause(text=clause, step=step, anaphor=anaphor, verb=verb)


def anaphoric_delayed_trigger(
    clause: str,
    *,
    subject: CardState,
    controller: str,
    source_id: UUID | None,
    source_name: str,
) -> DelayedTrigger | None:
    """`parse_anaphoric_delayed_clause` and `trigger_for` in one call - the
    whole primitive, for a caller that has just moved or created `subject` and
    has the clause that talks about it.

    The result is not registered anywhere: CR 603.7a's creation is
    `Game.create_delayed_trigger`, which the caller does once it is satisfied
    the rest of its paragraph succeeded.
    """
    parsed = parse_anaphoric_delayed_clause(clause)
    if parsed is None:
        return None
    trigger = parsed.trigger_for(
        subject,
        controller=controller,
        source_id=source_id,
        source_name=source_name,
    )
    if trigger is None:
        return None
    # The stack listing should read as the card does, full stop and all; the
    # parse strips it only to match.
    return trigger.model_copy(update={"text": clause.strip()})


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

    def create_reflexive(
        self,
        *,
        text: str,
        controller: str,
        source_id: UUID | None,
        source_name: str,
        callback: DelayedEffect,
    ) -> AbilityOnStack:
        """CR 603.12: create a reflexive triggered ability and hand back the
        stack object it becomes - with no wait, unlike an ordinary delayed
        trigger (CR 603.7).

        "A resolving spell or ability may allow or instruct a player to take
        an action and create a triggered ability that triggers 'when [a
        player] [does or doesn't]' take that action ... These reflexive
        triggered abilities follow the rules for delayed triggered abilities
        (see rule 603.7), except that they're checked immediately after being
        created and trigger based on whether the trigger event or events
        occurred earlier during the resolution of the spell or ability that
        created them." The caller (`machines/effects.py`'s "you may sacrifice
        ... When you do, ..." clause, Grist, the Hunger Tide's shape) only
        calls this *after* the action has actually happened, so "checked
        immediately" and "occurred earlier" are both already true by
        construction - there is no event left to wait for, so unlike `create`
        this never touches `self.triggers`, and `fire`/`matches` never see it.

        CR 603.7d/e give the source and controller as the creating spell or
        ability's own, as it resolved - the caller's job, since only it knows
        which ability created this one.

        The resulting `AbilityOnStack` is not put on the stack here. CR 603.3
        puts a triggered ability on the stack "the next time a player would
        receive priority", which the caller reaches by handing the return
        value to `Game.pending_triggers` - the same queue `put_triggers_on_
        stack` already drains for every other triggered ability, which is
        what makes this a *separate* stack object an opponent can respond to
        (CR 405.6a) rather than part of the parent's own resolution - the
        CR 118.12 "If you do" shape's whole distinction from this one.
        """
        trigger = DelayedTrigger(
            text=text,
            controller=controller,
            source_id=source_id,
            source_name=source_name,
            callback=callback,
            remaining=0,  # CR 603.7b/603.12: spent the moment it is created
        )
        ability = AbilityOnStack(
            kind=AbilityKind.TRIGGERED,
            ability=trigger.as_ability(),
            source_id=source_id,
            source_name=source_name,
            controller=controller,
        )
        self.pending[ability.id] = trigger
        return ability

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

    def expire_this_turn(self) -> list[DelayedTrigger]:
        """CR 514.2: end every "this turn" delayed trigger, in the cleanup step.

        The `ContinuousEffects.end_the_turn` twin for a trigger rather than a
        static effect - Dalkovan Encampment's "Whenever you attack this turn"
        needs to stop matching once the turn that created it is over, or it
        would also fire on every later turn's attack. Only
        `expires_end_of_turn` triggers are touched; an ordinary one-shot
        delayed trigger (Warp's exile, a sacrifice at the next end step) has
        no such duration and outlives this call untouched, same as a static
        effect with no "until end of turn" survives `end_the_turn`.
        """
        ending = [trigger for trigger in self.triggers if trigger.expires_end_of_turn]
        ending_ids = {trigger.id for trigger in ending}
        self.triggers = [trigger for trigger in self.triggers if trigger.id not in ending_ids]
        return ending

    def trigger_for(self, ability: AbilityOnStack) -> DelayedTrigger | None:
        """The delayed ability an object on the stack came from, if it came from one."""
        return self.pending.get(ability.id)

    def effect_for(self, ability: AbilityOnStack) -> DelayedEffect | None:
        """What this ability does, or None if it is not one of ours.

        `callback` wins when a parsed clause carried one - see its docstring
        on `DelayedTrigger` - and `DELAYED_EFFECTS`'s string key is the
        fallback for the hand-written triggers that predate it.
        """
        trigger = self.pending.get(ability.id)
        if trigger is None:
            return None
        if trigger.callback is not None:
            return trigger.callback
        return DELAYED_EFFECTS.get(trigger.effect)

    def discard(self, ability: AbilityOnStack) -> None:
        """Forget an ability that has finished resolving (CR 608.2n)."""
        self.pending.pop(ability.id, None)
