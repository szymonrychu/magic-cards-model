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

**What it does** used to be a hand-written registry keyed by a string
(`DELAYED_EFFECTS`) or a bare Python closure carried on `DelayedTrigger.
callback` (`exclude=True`, so it never survived a `model_dump`). Both are gone.
`DelayedTrigger.effect` is now a single `kind`-discriminated union,
`DelayedEffectSpec` - frozen pydantic models, each carrying the exact body of
the closure it replaces, moved rather than rewritten, so a decoded trigger
resolves identically to the one that was dumped. This is the same shape
commit 739ee2b already gave `machines/layers.py`'s continuous effects
(`Selector`/`Modification`/`Count`), for the identical reason: a plain Python
function cannot survive `Game.model_dump(mode="json")`, and a registry keyed by
a string silently resolves to nothing for any key the registry does not have -
see `memory/silent-default-dispatch-tables.md`. A discriminated union fails
loudly instead: an unrecognised `kind` refuses at decode, it does not resolve
and do nothing.

Every previous factory name survives, as either the class itself or a
singleton instance of it, so no construction site outside this file has to
change *except* the handful this task's own requirement 2-4 rewrites.
`models/game.py`'s three call sites (warp's, dash's, and rebound's) build
`effect=` directly - `ExileWarped()`, `return_subject_to_hand`,
`rebound_recast` - the same as everywhere else in the codebase. An earlier
revision of this module carried a `DelayedTrigger` before-validator that
translated a `callback=` keyword and a bare-string `effect=` into that shape,
because `models/game.py` was locked by a concurrent worktree at the time; the
lock is gone, those three sites were converted, and the validator was deleted
with them (see `memory/delayed-trigger-serialization-game-py-isolation.md`).
"""

import re
from collections.abc import Callable
from functools import cache
from typing import TYPE_CHECKING, Annotated, ClassVar, Literal
from uuid import UUID

from pydantic import ConfigDict, Field

from magic_cards_model.text_norm import collapsed

from ..ids import new_id
from ..models.card import Card, Color, Type
from ..models.card_state import PERMANENT_TYPES, CardState, Counter
from ..models.mana import ManaCost
from ..models.token import TokenDefinition, create_tokens, is_token, token_copy_of
from ..models.zone import Zone
from ..snapshot import EngineModel
from .abilities import AbilityKind, TriggeredAbility, TriggerEvent, TriggerWord
from .decisions import Decision, DecisionKind, source_id_of
from .layers import (
    ContinuousEffect,
    Duration,
    Layer,
    Sublayer,
    grant_ability,
    modify_power_toughness,
    only_this_incarnation,
)
from .triggers import AbilityOnStack, GameEvent
from .turn import MAIN_PHASES, Step

if TYPE_CHECKING:
    from ..models.game import Game

#: A callable shaped like a `DelayedEffectSpec`'s own `__call__`. Kept, and
#: kept meaning exactly this, only because `models/game.py` - off limits to
#: this task - type-hints `Game.create_reflexive_trigger`'s own `callback`
#: parameter with this name; every `DelayedEffectSpecBase` subclass satisfies
#: it structurally (matching `__call__` signature), so that hint stays
#: accurate without that file changing. New code should type against
#: `DelayedEffectSpecBase` directly instead.
DelayedEffect = Callable[["Game", AbilityOnStack, "DelayedTrigger"], None]


# ---------------------------------------------------------------------------
# DelayedEffectSpec - what a delayed (or reflexive) triggered ability does
# when it resolves, as data rather than as a closure.
# ---------------------------------------------------------------------------


class DelayedEffectSpecBase(EngineModel):
    """One delayed triggered ability's resolution, as a frozen, serializable
    value rather than a Python closure.

    Every subclass carries the exact body of the closure or registry entry it
    replaces - the correctness argument is that decoded behaviour is identical
    by construction, not by test coverage (see this module's own docstring and
    `machines/layers.py`'s `SelectorBase`/`ModificationBase`, which this
    mirrors).
    """

    model_config = ConfigDict(frozen=True)

    is_mana_ability: ClassVar[bool] = False
    """CR 605.1b's third criterion, self-described rather than inferred from
    `kind`: `models.game.Game._resolve_triggered_mana_abilities` reads this
    (alongside the ordinary "no target" check every delayed trigger already
    gets) to decide whether this delayed triggered ability resolves inline,
    with no stack, the moment its own mana-ability event fires (CR 605.4a) -
    the same immediate treatment a *printed* triggered mana ability's
    `parse_triggered_mana`-readable effect text already gets. `False` for
    every ordinary delayed effect; a mana-adding one (`AddManaWhenLandTapped`)
    overrides it to `True`. A `ClassVar`, not a field: it describes the whole
    *kind* of effect, the same way `kind` itself does, not one instance's
    own data - so it never needs a value at construction and never appears
    in a decode."""

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        raise NotImplementedError

    matches_against_the_game: ClassVar[bool] = False
    """Whether `event_matches` needs the game to answer - `DelayedTriggers.
    fire` called without one never fires such a trigger."""

    def event_matches(self, game: "Game", trigger: "DelayedTrigger", event: GameEvent) -> bool:
        """A further, game-aware check on an event `DelayedTrigger.matches`
        already accepted. `True` for every kind but one whose own condition is
        read by `machines/triggers.condition_matches` (`CreatedTriggeredAbility`)."""
        return True

    def printed_ability(self, trigger: "DelayedTrigger") -> TriggeredAbility | None:
        """The ability as a printed `TriggeredAbility`, when this kind carries
        one; `None` keeps `DelayedTrigger.as_ability`'s own stand-in."""
        return None


class ExileWarped(DelayedEffectSpecBase):
    """Warp's delayed trigger (CR 702.185a, CR 603.7).

    "If this spell's warp cost was paid, exile the permanent this spell becomes
    at the beginning of the next end step. Its owner may cast this card after
    the current turn has ended for as long as it remains exiled."

    CR 603.7c is what makes the zone check part of the rule rather than
    defensive coding: a warped permanent that died before the end step is no
    longer on the battlefield, so the ability resolves and affects nothing.
    """

    kind: Literal["warp:exile"] = "warp:exile"

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        from .casting import exile_warped

        permanent = trigger.still_affects(game)
        if permanent is None:
            return
        exile_warped(game, permanent)


class GrantExtraTurn(DelayedEffectSpecBase):
    """ "After that turn, [a player] takes an extra turn" (CR 500.7, CR 603.7).

    Emrakul, the Promised End's second sentence. It has to be a delayed trigger
    rather than part of the resolution: CR 500.7 adds an extra turn "directly
    after the specified turn", so granting it while the cast trigger resolves
    would insert it before the turn Emrakul's controller is about to steal, and
    the controlled player would take their extra turn first.
    """

    kind: Literal["grant_extra_turn"] = "grant_extra_turn"

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        username = trigger.subject_player or trigger.controller
        if game.is_in_game(username):
            game.grant_extra_turn(username)


class SacrificeSubject(DelayedEffectSpecBase):
    """ "At the beginning of the next end step, sacrifice it."

    CR 701.21a: "To sacrifice a permanent, its controller moves it from the
    battlefield directly to its owner's graveyard." CR 603.7c is what stops it
    reaching a permanent that has already gone somewhere else.
    """

    kind: Literal["sacrifice"] = "sacrifice"

    max_mana_value: int | None = None
    """"... if it has mana value 3 or less" (Angrath, the Flame-Chained): the intervening *if*
    (CR 603.4) read off the permanent as it is when the ability resolves (CR 613.5). None: no
    condition."""

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        permanent = trigger.still_affects(game)
        if permanent is None:
            return
        if (
            self.max_mana_value is not None
            and game.characteristics_of(permanent).mana_value > self.max_mana_value
        ):
            return
        game.put_into_graveyard(permanent)


class SacrificedByItsController(DelayedEffectSpecBase):
    """ "... the blocking creature's controller sacrifices it at end of
    combat." (The Ring's third ability, CR 701.54c) - the subject is
    sacrificed by whoever controls it when this resolves, not by the delayed
    ability's own controller (CR 603.7d/e make that the Ring's owner, who is
    the blocker's opponent). CR 701.21a: "To sacrifice a permanent, its
    controller moves it from the battlefield directly to its owner's
    graveyard", so this is `Game.sacrifice` and its sacrifice events, not a
    bare move. CR 603.7c stops it reaching a permanent that already left.
    """

    kind: Literal["sacrificed_by_its_controller"] = "sacrificed_by_its_controller"

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        permanent = trigger.still_affects(game)
        if permanent is not None:
            game.sacrifice(permanent)


class SacrificeEach(DelayedEffectSpecBase):
    """ "Sacrifice them at the beginning of the next end step." - one delayed
    triggered ability about several objects, where `SacrificeSubject` is about
    one. Mobilize's tokens are the shape (CR 702.181a): the trigger that made
    them creates a single delayed ability, so a single object goes on the
    stack at the end step, not one per token.

    `subjects` pairs each object's id with the `zone_change_stamp` it had when
    the ability was created. CR 603.7c is applied object by object: "if that
    object is no longer in the zone it's expected to be in at the time the
    delayed triggered ability resolves, the ability won't affect it", and one
    that left and came back is a new object. CR 701.21a: "A player can't
    sacrifice ... something that's a permanent they don't control", so an
    object now controlled by someone else is skipped too.
    """

    kind: Literal["sacrifice_each"] = "sacrifice_each"

    subjects: tuple[tuple[UUID, UUID], ...]

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        for subject_id, stamp in self.subjects:
            found = game.find_by_id(subject_id)
            if not isinstance(found, CardState) or found.zone is not Zone.BATTLEFIELD:
                continue
            if found.zone_change_stamp != stamp:
                continue
            if game.controller_of(found).username != trigger.controller:
                continue
            game.sacrifice(found)


class ExileSubjectAtNextEndStep(DelayedEffectSpecBase):
    """ "Exile it at the beginning of the next end step" - Postmortem Lunge's
    own delayed exile of the creature it just returned to the battlefield
    (CR 701.13a: "To exile an object, move it to the exile zone from wherever
    it is"). CR 603.7c is what stops this reaching a permanent that already
    left the battlefield some other way - destroyed in response, sacrificed,
    or bounced - before the delayed step arrived.
    """

    kind: Literal["exile_subject_at_next_end_step"] = "exile_subject_at_next_end_step"

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        permanent = trigger.still_affects(game)
        if permanent is not None:
            game.exile_permanent(permanent)


class ReturnSubjectToBattlefieldUnderOwner(DelayedEffectSpecBase):
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

    kind: Literal["return_subject_to_battlefield_under_owner"] = (
        "return_subject_to_battlefield_under_owner"
    )

    #: ecl-T8: Morningtide's Light's own "return those cards to the
    #: battlefield tapped under their owners' control" - the identical
    #: "tapped" rider `ReturnSubjectFromGraveyardToBattlefield` already
    #: carries for its own graveyard-return shape.
    tapped: bool = False

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        permanent = trigger.still_affects(game)
        if permanent is None or permanent.owner is None:
            return
        game.put_onto_battlefield(permanent, permanent.owner, tapped=self.tapped)


class ReturnSubjectThenDiscardItsStat(DelayedEffectSpecBase):
    """ "At the beginning of your next upkeep, return that card to the
    battlefield under its owner's control. If you do, discard cards equal to
    that creature's toughness." (Vanish into Memory) - the blink return
    (`ReturnSubjectToBattlefieldUnderOwner`) plus a rider that spends the
    returned object's own characteristic.

    "If you do" is the return itself (CR 603.7c: the card is no longer where
    it was exiled to, or is a new object, and nothing returns). "That
    creature" is the object that just returned - a new object (CR 400.7) read
    on the battlefield, so it counts its own counters-free printed values and
    whatever continuous effects apply to it now (CR 613.5). The discard is the
    delayed trigger's controller's, of their own choice (CR 701.9b).
    """

    kind: Literal["return_subject_then_discard_its_stat"] = "return_subject_then_discard_its_stat"
    stat: Literal["power", "toughness", "mana value", "power plus toughness"]

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        from .ep02_r1_referenced_stat import discard_equal_to_stat, snapshot_of

        permanent = trigger.still_affects(game)
        if permanent is None or permanent.owner is None:
            return
        game.put_onto_battlefield(permanent, permanent.owner)
        if permanent.zone is not Zone.BATTLEFIELD:
            return
        discard_equal_to_stat(
            game,
            trigger.controller,
            snapshot_of(game, permanent),
            self.stat,
            trigger.source_name,
            trigger.source_id,
        )


class ReturnSubjectToBattlefieldUnderController(DelayedEffectSpecBase):
    """ "Return it to the battlefield under your control at the beginning of
    the next end step" (Argent Sphinx) - CR 610.3c's "unless otherwise
    specified": the delayed ability's controller (CR 603.7d/e: the player who
    controlled the ability that created it), not the owner."""

    kind: Literal["return_subject_to_battlefield_under_controller"] = (
        "return_subject_to_battlefield_under_controller"
    )

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        permanent = trigger.still_affects(game)
        if permanent is None:
            return
        game.put_onto_battlefield(permanent, trigger.controller)


class ReturnSubjectToHand(DelayedEffectSpecBase):
    """ "Return it to its owner's hand at the beginning of the next end step" -
    Aether Membrane's and dash's shape. `Game.return_to_hand` already goes to
    the *owner's* hand, whoever controls it now.

    Dash is **CR 702.109a**: "Dash represents three abilities: two static
    abilities that function while the card with dash is on the stack, one of
    which may create a delayed triggered ability, and a static ability that
    functions while the object with dash is on the battlefield." That delayed
    triggered ability is this one.
    """

    kind: Literal["return_subject_to_hand"] = "return_subject_to_hand"

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        permanent = trigger.still_affects(game)
        if permanent is not None:
            game.return_to_hand(permanent)


class ReboundRecast(DelayedEffectSpecBase):
    """CR 702.88a's own recast: "At the beginning of your next upkeep, you may
    cast this card from exile without paying its mana cost."

    Optional (`Game.may`), and only for the exact card this rebound sent to
    exile: `still_affects` is CR 603.7c's check that it is still there,
    unmoved by anything else, when this trigger finally resolves - a rebound
    card someone managed to remove from exile in the meantime is not cast at
    all, rather than this reaching for whatever else has `subject_id`'s id
    now (CR 400.7 - once it moves again, it is a new object).

    `Game.may_cast_during_resolution` asks and casts: CR 702.88b's
    alternative-cost cast through the one CR 608.2g funnel, which announces
    the card's own new targets (CR 601.2c) and refuses a cast CR 611.1
    prohibits.
    """

    kind: Literal["rebound_recast"] = "rebound_recast"

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        card = trigger.still_affects(game)
        if card is None:
            return
        game.may_cast_during_resolution(
            card,
            trigger.controller,
            prompt=f"cast {card.name} from exile without paying its mana cost",
            source=card.name,
            source_id=source_id_of(ability),
            source_name=f"{card.name}'s rebound",
            rule="CR 702.88a",
            keyword="Rebound",
        )


class ParadigmCopyAndCast(DelayedEffectSpecBase):
    """CR 702.192a's own delayed trigger: "at the beginning of each of your
    precombat main phases for the rest of the game, create a copy of this
    object in exile. You may cast the copy without paying its mana cost."

    Unlike `ReboundRecast`, which recasts the *same* exiled card, this
    creates a brand-new copy (CR 707.2) each time it fires - `remaining=None`
    on the `DelayedTrigger` that carries this ("for the rest of the game"),
    so one Paradigm spell's first resolution can produce a fresh free cast
    on every one of its controller's precombat mains from then on.

    `still_affects` (CR 603.7c) is asked about the *original* exiled object,
    not the copy: if something has removed the original Paradigm spell from
    exile since it was created, there is nothing left to copy, and the
    trigger simply produces nothing on that firing (and every one after,
    since nothing here ever finds the original again) - the trigger itself
    is not removed, matching CR 603.7b's "for the rest of the game" duration.

    A declined copy does not linger: CR 704.5e/707.10a make "a copy of a
    card is in any zone other than the stack or the battlefield" a
    state-based action that erases it, and nothing here ever gives another
    player a priority window between the copy's creation and the "you may
    cast it" choice (both happen inside this one ability's resolution), so
    removing a declined copy immediately is the same outcome that
    state-based action would produce the next time it is checked - not a
    substitute for building the general SBA (`docs/engine-coverage.md`
    still lists it as unmodelled), just the one case this effect can settle
    on its own without it.
    """

    kind: Literal["paradigm_copy_and_cast"] = "paradigm_copy_and_cast"

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        original = trigger.still_affects(game)
        if original is None:
            return
        with game._id_allocator_scope():
            state_type = CardState
            copy = state_type(
                card=original.card,
                zone=Zone.EXILE,
                controller=trigger.controller,
                owner=original.owner,
                is_copy=True,
            )
            game.exile.append(copy)
        cast = game.may_cast_during_resolution(
            copy,
            trigger.controller,
            prompt=f"cast the copy of {copy.name} without paying its mana cost",
            source=copy.name,
            source_id=source_id_of(ability),
            source_name=f"{copy.name}'s paradigm",
            rule="CR 702.192a",
            keyword="Paradigm",
        )
        if cast is None and copy in game.exile:
            # CR 704.5e/707.10a: a copy not cast has nowhere to persist.
            game.exile.remove(copy)


class CipherCopyAndCast(DelayedEffectSpecBase):
    """CR 702.99a's second ability: "For as long as this card is encoded on that
    creature, that creature has 'Whenever this creature deals combat damage to a player,
    you may copy the encoded card and you may cast the copy without paying its mana
    cost.'" - a delayed trigger kept for the encoding's whole life (`remaining=None`),
    watching the creature (`DelayedTrigger.subject_id`, with its zone and stamp, CR 400.7).

    CR 702.99c: the card stays encoded while it stays exiled and the creature stays on
    the battlefield, whoever controls the creature - so the ability is its current
    controller's (not the trigger's creating controller's), and a card that has left
    exile, or a creature that is a new object, ends the trigger the next time it is
    asked. The copy is made in exile (CR 707.12) and ceases to exist if it is not cast
    (CR 707.10a).
    """

    kind: Literal["cipher_copy_and_cast"] = "cipher_copy_and_cast"
    card_id: UUID
    """The exiled card the creature has encoded."""
    card_stamp: UUID
    """Its `zone_change_stamp` in exile: a card that left and came back is a new object."""

    matches_against_the_game: ClassVar[bool] = True

    def _encoded_card(self, game: "Game") -> CardState | None:
        found = game.find_by_id(self.card_id)
        if (
            isinstance(found, CardState)
            and found.zone is Zone.EXILE
            and found.zone_change_stamp == self.card_stamp
        ):
            return found
        return None

    def event_matches(self, game: "Game", trigger: "DelayedTrigger", event: GameEvent) -> bool:
        if trigger.still_affects(game) is not None and self._encoded_card(game) is not None:
            return True
        trigger.remaining = 0  # CR 702.99c: no longer encoded, so nothing is left to watch
        return False

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        creature = trigger.still_affects(game)
        card = self._encoded_card(game)
        if creature is None or card is None:
            return
        caster = game.controller_of(creature).username
        with game._id_allocator_scope():
            copy = CardState(
                card=card.card,
                zone=Zone.EXILE,
                controller=caster,
                owner=caster,
                is_copy=True,
            )
            game.exile.append(copy)
        cast = game.may_cast_during_resolution(
            copy,
            caster,
            prompt=f"cast a copy of {copy.name} without paying its mana cost",
            source=copy.name,
            source_id=source_id_of(ability),
            source_name=f"{copy.name}'s cipher",
            rule="CR 702.99a",
            keyword="Cipher",
        )
        if cast is None and copy in game.exile:
            game.exile.remove(copy)  # CR 704.5e/707.10a: a copy not cast does not persist


class CopyEpicSpell(DelayedEffectSpecBase):
    """CR 702.50a's second spell ability: "At the beginning of each of your
    upkeeps for the rest of the game, copy this spell except for its epic
    ability. If the spell has any targets, you may choose new targets for the
    copy."

    The spell is the card the delayed trigger names (`subject_id`), copied as
    it last existed on the stack (CR 608.2h, `Game.copy_spell_as_last_known`):
    its targets, X, modes and the rest of how it was cast. The copy is marked
    `epic_suppressed`, so resolving it makes no further delayed trigger and no
    further restriction (CR 702.50a's "except for its epic ability"). A copy
    is never cast (CR 707.10), so CR 702.50b's ban does not stop it.
    """

    kind: Literal["epic_copy_spell"] = "epic_copy_spell"

    copy_of: CardState | None = None
    """Set only when the epic spell was itself a copy (Reverberate on it): a
    copy ceases to exist as it leaves the stack (CR 707.10a), so nothing could
    be looked up by id at the upkeep. This is the copy as it last existed on
    the stack, with its targets and `cast_record` (its modes and X, dumped as
    JSON), and the upkeep copies it from there (CR 608.2h)."""

    cast_record: dict | None = None

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        if trigger.subject_id is None or not game.is_in_game(trigger.controller):
            return
        if self.copy_of is not None:
            from ..models.game.records import CastRecord

            copy = game._put_spell_copy(
                self.copy_of,
                trigger.controller,
                original_record=CastRecord.model_validate(self.cast_record or {}),
                targets=list(self.copy_of.targets),
                division=self.copy_of.division,
            )
        else:
            spell = game.find_by_id(trigger.subject_id)
            if not isinstance(spell, CardState):
                return
            copy = game.copy_spell_as_last_known(spell, controller=trigger.controller)
        if copy is None:
            return
        copy.epic_suppressed = True
        game.offer_new_targets_for_copy(
            copy,
            trigger.controller,
            source_name=trigger.source_name,
            source_id=source_id_of(ability),
        )


class DiscardCardsAtRandomForController(DelayedEffectSpecBase):
    """ "At the beginning of your next upkeep, discard `<n>` cards at
    random." - Casey Jones, Vigilante's own delayed half (TMT). Like
    `DrawACardForController`, no object is named at all: the discard is the
    creating ability's own controller's (CR 121.2's twin, CR 701.9's
    discard), on their own behalf, and `count` carries the printed number so
    a future different-count printing of the same shape reads the same way
    rather than needing a new `kind`.

    `machines/effects._discard_at_random` is CR 701.9b's random discard - no
    decision asked of anybody, since there is no "which card" question for a
    random discard the way there is for a chosen one.
    """

    kind: Literal["discard_cards_at_random_for_controller"] = (
        "discard_cards_at_random_for_controller"
    )
    count: int

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        if not game.is_in_game(trigger.controller):
            return
        from .effects import _discard_at_random

        _discard_at_random(game, game.player(trigger.controller), self.count, trigger.source_name)


class DrawACardForController(DelayedEffectSpecBase):
    """ "Draw a card at the beginning of the next turn's upkeep" - Mishra's
    Bauble's second half. No object is named at all (CR 603.7c has nothing to
    check), so this is the creating ability's controller, drawing on their own
    behalf (CR 121.2). `count` is 1 for every card in the pool; a future
    "draw `<n>` cards at the beginning of ..." delayed trigger reads the same
    way with a different count, rather than needing a new `kind` of its own.
    """

    kind: Literal["draw_a_card_for_controller"] = "draw_a_card_for_controller"
    count: int = 1

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        if game.is_in_game(trigger.controller):
            game.draw_cards(trigger.controller, self.count)


class UntapAllCreaturesForController(DelayedEffectSpecBase):
    """ "At the beginning of that combat, untap all creatures you control" -
    Moraug, Fury of Akoum's additional combat phase (CR 500.8). The creating
    ability's controller untaps every creature they control as the delayed
    trigger resolves (CR 701.26b); no object is named (CR 603.7c has nothing
    to check)."""

    kind: Literal["untap_all_creatures_for_controller"] = "untap_all_creatures_for_controller"

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        if not game.is_in_game(trigger.controller):
            return
        board = game.computed_board()
        for permanent in game.permanents_controlled_by(trigger.controller):
            if Type.CREATURE in board.of(permanent).types and permanent.tapped:
                permanent.untap(exert_applies=False)


class DamageEachOpponentPerCardStillExiled(DelayedEffectSpecBase):
    """ "At the beginning of your next end step, `<this>` deals `<n>` damage to
    each opponent for each of those cards that are still exiled" - Dragonhawk,
    Fate's Tempest's third sentence (CR 603.7).

    CR 603.7c: the delayed ability refers to particular objects, so it names the
    cards the first sentence exiled and counts only those still in the exile
    zone as the same object. CR 400.7: a card that left exile (played, or
    returned anywhere) is a new object, so its zone-change stamp no longer
    matches the one captured when it was exiled. The count is taken once as the
    ability resolves (CR 608.2h).
    """

    kind: Literal["damage_each_opponent_per_card_still_exiled"] = (
        "damage_each_opponent_per_card_still_exiled"
    )
    card_ids: tuple[UUID, ...]
    stamps: tuple[UUID | None, ...]
    per_card: int

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        from .effects.damage import _opponents

        still_exiled = 0
        for card_id, stamp in zip(self.card_ids, self.stamps, strict=True):
            card = game.find_by_id(card_id)
            if card is not None and card.zone is Zone.EXILE and card.zone_change_stamp == stamp:
                still_exiled += 1
        amount = still_exiled * self.per_card
        if amount <= 0:
            return
        source = ability.source_or_last_known(game)
        for opponent in _opponents(game, trigger.controller):
            game.deal_damage(opponent, amount, source=source)


class AddManaAmountForController(DelayedEffectSpecBase):
    """ "Add an amount of `<color>` equal to `<n>` at the beginning of your
    next main phase" - Mana Sculpt's own delayed trigger (CR 603.7), created
    only when its own "if you control a Wizard" condition already held as the
    countering spell resolved (`machines/effects._parse_counter_then_wizard_
    mana_from_countered_pair` reads and gates that condition before ever
    creating this trigger; it is not re-checked here). `amount` is CR
    601.2h's mana spent casting the *countered* spell, captured as a plain
    integer while that spell still existed on the stack - by the time this
    trigger is even created it is on its way to a graveyard (CR 608.2b), let
    alone by the time it resolves, so nothing here ever needs its long-gone
    `CastRecord` again.

    Not CR 605.1b's mana ability: CR 605.1b's second criterion is that it
    "triggers from the activation or resolution of an activated mana ability
    ... or from mana being added to a player's mana pool" - a step
    beginning is neither, so this goes on the stack and waits for priority
    like any other triggered ability, the same reasoning `machines/effects.
    _parse_add_mana_clause` already gives for Ugin, Eye of the Storms' own
    "Add {C}{C}{C}" loyalty ability.
    """

    kind: Literal["add_mana_amount_for_controller"] = "add_mana_amount_for_controller"
    amount: int
    color: Color

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        if not game.is_in_game(trigger.controller) or self.amount <= 0:
            return
        pool = game.mana_pool_receiving(trigger.controller)
        for _ in range(self.amount):
            pool.add(self.color)


class AddManaInAnyCombinationForController(DelayedEffectSpecBase):
    """ "At the beginning of your next first main phase, add X mana in any
    combination of colors, where X is that spell's mana value" - Plasm
    Capture's own delayed trigger (CR 603.7). `amount` is the countered
    spell's mana value, captured as the countering spell resolved, since the
    spell itself is gone by now (CR 608.2b, CR 608.2h). Each unit's colour is
    chosen as this resolves (CR 608.2d), among `palette` - CR 106.1a's five
    for "colors", a printed palette for "{R} and/or {G}".

    Not a mana ability, for the reason `AddManaAmountForController` gives: a
    step beginning is not CR 605.1b's trigger, so this uses the stack.
    """

    kind: Literal["add_mana_in_any_combination_for_controller"] = (
        "add_mana_in_any_combination_for_controller"
    )
    amount: int
    palette: list[Color]

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        if not game.is_in_game(trigger.controller) or self.amount <= 0 or not self.palette:
            return
        from .effects import _add_mana_in_any_combination

        _add_mana_in_any_combination(game, ability, self.amount, self.palette)


class DestroySubject(DelayedEffectSpecBase):
    """ "Destroy it at the beginning of the next end step" - CR 701.8a: "To
    destroy a permanent, move it from the battlefield to its owner's
    graveyard." Distinct from sacrifice (CR 701.21a) because destruction can
    be regenerated or replaced and sacrifice cannot; `Game.destroy` is where
    that difference lives. CR 603.7c is the usual guard on the object still
    being where the ability expects it.
    """

    kind: Literal["destroy_subject"] = "destroy_subject"

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        permanent = trigger.still_affects(game)
        if permanent is not None:
            game.destroy(permanent)


class TapSubject(DelayedEffectSpecBase):
    """ "Tap it at the beginning of the next turn's upkeep" - CR 701.26a: "To
    tap a permanent, turn it sideways from an upright position. Only untapped
    permanents can be tapped." `CardState.tap_if_untapped` leaves an
    already-tapped subject as it is, with no error, which is that second
    sentence.
    """

    kind: Literal["tap_subject"] = "tap_subject"

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        permanent = trigger.still_affects(game)
        if permanent is not None:
            game.tap_permanent(permanent)


class GainControlUntapHasteOfSubject(DelayedEffectSpecBase):
    """ "At the beginning of the next combat this turn, gain control of that
    creature until end of turn. Untap it. It gains haste until end of turn." -
    The Wrath of Khan's chapter I. Threaten's three instructions
    (`effects.continuous._untap_and_apply_control_sentences`) run when the
    delayed trigger resolves, on the creature the trigger was created about;
    CR 603.7c: one that has left the battlefield since (the 4 damage may have
    killed it) is not affected."""

    kind: Literal["gain_control_untap_haste_of_subject"] = "gain_control_untap_haste_of_subject"

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        from .effects.continuous import _untap_and_apply_control_sentences

        permanent = trigger.still_affects(game)
        if permanent is None:
            return
        found = game.find_by_id(trigger.source_id)
        source = found if isinstance(found, CardState) else permanent
        _untap_and_apply_control_sentences(
            game,
            source,
            game.player(trigger.controller),
            [permanent],
            (
                "gain control of it until end of turn.",
                "target creature gains haste until end of turn.",
            ),
        )


class TransformSubject(DelayedEffectSpecBase):
    """ "Transform `<this>` at the beginning of the next upkeep" - Aang, at the
    Crossroads' and Archangel Avacyn's own delayed trigger (CR 603.7,
    CR 701.27a).

    Two guards, both from the rules rather than from caution:

    - CR 603.7c: the permanent must still be the object the trigger was
      created about - `still_affects` refuses one that left the battlefield,
      even if it has since come back (CR 400.7).
    - CR 701.27f: "If a delayed triggered ability of a permanent tries to
      transform that permanent, the permanent does so only if it hasn't
      transformed or converted since that delayed triggered ability was
      created." `times_transformed` is `CardState.times_transformed` as it
      was at creation, so a second trigger from the same board wipe finds the
      permanent already turned over and leaves it alone rather than turning
      it back.
    """

    kind: Literal["transform_subject"] = "transform_subject"
    times_transformed: int = 0

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        from .effects import transform_permanent

        permanent = trigger.still_affects(game)
        if permanent is None or permanent.times_transformed != self.times_transformed:
            return
        transform_permanent(game, permanent)


def _drop_sibling_triggers(game: "Game", trigger: "DelayedTrigger") -> None:
    """Drop every sibling delayed trigger once one of them has fired - CR
    603.7a's one-shot spends the whole ability, not just the one event that
    happened to occur first, and leaving a dead watcher behind risks a second,
    wrong resolution later. Shared by `StaticPrisonReturn` and
    `ReturnEarthbentLand`, whose sibling-dropping bodies used to be two
    identical private functions (`_dismiss_other_static_prison_triggers`,
    `_dismiss_other_earthbend_trigger`) in `machines/effects.py`.
    """
    game.delayed_triggers.triggers = [
        candidate
        for candidate in game.delayed_triggers.triggers
        if candidate.id not in trigger.sibling_ids
    ]


class ReturnEarthbentLand(DelayedEffectSpecBase):
    """CR 701.66a's own return: tapped, and under the earthbend ability's
    *controller* - not `ReturnSubjectToBattlefieldUnderOwner`'s owner-and-
    untapped default, which is CR 610.3c's default for a blink effect that
    says nothing more specific. Earthbend overrides both halves of that
    default explicitly, so it needs its own effect rather than the shared one.
    """

    kind: Literal["return_earthbent_land"] = "return_earthbent_land"

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        permanent = trigger.still_affects(game)
        _drop_sibling_triggers(game, trigger)
        if permanent is None:
            return
        game.put_onto_battlefield(permanent, trigger.controller, tapped=True)


class CounterOnSubjectWhileSourceTapped(DelayedEffectSpecBase):
    """Giant Oyster's "For as long as this creature remains tapped, ... at the
    beginning of each of your draw steps, put a -1/-1 counter on that
    creature." - a delayed trigger with a stated duration (CR 603.7b), the
    duration being CR 611.2b's "for as long as" on the *source's* tapped
    status. The trigger only fires while that holds (`event_matches`); once
    the source untaps or leaves, its sibling `RemoveCountersFromLinkedCreature`
    drops it for good."""

    kind: Literal["counter_on_subject_while_source_tapped"] = (
        "counter_on_subject_while_source_tapped"
    )
    source_card_id: UUID
    source_stamp: UUID
    counter_kind: str

    matches_against_the_game: ClassVar[bool] = True

    def event_matches(self, game: "Game", trigger: "DelayedTrigger", event: GameEvent) -> bool:
        source = game.find_by_id(self.source_card_id)
        return (
            isinstance(source, CardState)
            and source.zone is Zone.BATTLEFIELD
            and source.zone_change_stamp == self.source_stamp
            and source.tapped
        )

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        permanent = trigger.still_affects(game)
        if permanent is None:
            return
        game.add_counters(permanent, self.counter_kind, putter=trigger.controller)


class RemoveCountersFromLinkedCreature(DelayedEffectSpecBase):
    """Giant Oyster's "When this creature leaves the battlefield or becomes
    untapped, remove all -1/-1 counters from the creature." - one CR 603.7a
    ability watching two events, so two sibling `DelayedTrigger`s keyed on the
    *source* (`subject_id`); the creature it acts on is carried here. Whichever
    fires first drops the other and the draw-step sibling."""

    kind: Literal["remove_counters_from_linked_creature"] = "remove_counters_from_linked_creature"
    creature_id: UUID
    creature_stamp: UUID
    counter_kind: str

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        _drop_sibling_triggers(game, trigger)
        creature = game.find_by_id(self.creature_id)
        if (
            not isinstance(creature, CardState)
            or creature.zone is not Zone.BATTLEFIELD
            or creature.zone_change_stamp != self.creature_stamp
        ):
            return
        present = creature.counters[self.counter_kind]
        if present:
            creature.remove_counters(self.counter_kind, present)


class DevourerOfDestinyFirstUpkeep(DelayedEffectSpecBase):
    """ "look at the top four cards of your library. You may put one of those
    cards back on top of your library. Exile the rest." (Devourer of Destiny.)

    Retired: nothing creates this any more. The opening-hand rider that used
    to is parsed now (`machines/opening_hand.read_rider`), and its delayed
    trigger is a `CreatedTriggeredAbility` whose effect
    `machines/effects._parse_look_top_keep_one_on_top_clause` reads off the
    printed text. The kind stays only so the persisted shape of a `Game` - and
    so `schema_version` - is unchanged; drop it with the next schema bump.

    `Game.look_at_top_and_split` asks CR 701.22a's shared look-then-split
    question; the "moved" half is read here as the card kept on top, so an
    unscripted player - whose default answer moves nothing - exiles all four,
    which is what declining a "you may put one back" does. The question says
    "at most one" (`moved_amount=1`) and `Game.ask` refuses more: the card
    says "one".

    "Exile the rest" goes through `Game.exile_cards`, never
    `Player.add(state, Zone.EXILE)`. CR 400.1 lists the seven zones and says
    which are whose: "Each player has their own library, hand, and graveyard.
    The other zones are shared by all players" - so there is exactly one exile
    zone, `Game.shared_zones[Zone.EXILE]`, and CR 406.2's "put it into the
    exile zone" means that one. Exiling into a per-player pile instead is what
    this effect used to do, and it left all four cards somewhere no
    shared-zone reader looks - not `Game.exile`, not `Game.all_targetables`,
    not the exile pile a seat is shown - so from the table the cards were
    neither back on the library nor in exile, which is neither outcome this
    ability has.
    """

    kind: Literal["devourer_of_destiny_first_upkeep"] = "devourer_of_destiny_first_upkeep"

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        player = game.player(trigger.controller)
        kept, rest = game.look_at_top_and_split(
            player,
            4,
            source=trigger.source_name,
            source_id=source_id_of(ability),
            prompt="look at the top four cards; you may put one back on top",
            moved_label="top of your library",
            kept_label="exiled",
            moved_amount=1,
        )
        game.exile_cards(rest)
        for index, state in enumerate(kept):
            player.library.insert(index, state)
        if kept:
            player.note_library_changed()  # CR 701.20d


class StaticPrisonReturn(DelayedEffectSpecBase):
    """The delayed trigger's own effect (CR 610.2, CR 603.7): return the one
    exiled card - not `still_affects`, which reads `DelayedTrigger.subject_id`
    for both "what event fires this" *and* "what does it affect" alike.

    Those are two different objects here: the trigger's own `subject_id` is
    the *enchantment* (CR 603.7a's event is "Static Prison leaves the
    battlefield", not "the exiled card does anything"), but the card this
    effect has to bring back is whatever was exiled - a different id entirely.
    `exiled_id`/`expected_stamp` are captured at the moment of exile (CR
    603.7c's own check: same id, same zone, same incarnation) without forcing
    the trigger's single `subject_id` field to mean two different things at
    once.

    `return_zone` is CR 610.3's own "previous zone": most CR 610.2 exiles of
    this shape take a permanent off the battlefield (Oblivion Ring's own
    template), so `Zone.BATTLEFIELD` is the default every existing caller
    still gets un-changed. Cloak and Dagger, Entwined is the first printing in
    the pool whose "exile a nonland card from their hand or the chosen
    creature" can exile a *hand* card instead - CR 610.3 returns it to
    whichever zone it actually left, not always the battlefield - so that
    caller passes `Zone.HAND` explicitly when the chosen object was a hand
    card.
    """

    kind: Literal["static_prison_return"] = "static_prison_return"

    exiled_id: UUID
    expected_stamp: UUID
    return_zone: Zone = Zone.BATTLEFIELD

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        _drop_sibling_triggers(game, trigger)
        card = game.find_by_id(self.exiled_id)
        if not isinstance(card, CardState):
            return
        if card.zone is not Zone.EXILE or card.zone_change_stamp != self.expected_stamp:
            return  # CR 603.7c: gone, or a new incarnation - not this card any more.
        if card.owner is None:
            return
        if self.return_zone is Zone.HAND:
            game.return_to_hand(card)
        else:
            game.put_onto_battlefield(card, card.owner, tapped=False)


class PhaseInEach(DelayedEffectSpecBase):
    """The end of "those creatures phase out until this enchantment leaves the
    battlefield" (Out of Time; CR 702.26c, CR 610.3): when the source leaves, the
    permanents it phased out phase back in. Which permanents is carried here (the
    trigger's own `subject_id` is the source whose departure fires it). A
    permanent that is not (or no longer) held out by this duration - gone, or
    phased in by other means - is left alone."""

    kind: Literal["phase_in_each"] = "phase_in_each"
    ids: tuple[UUID, ...]
    held_by: str
    """`CardState.phased_out_under` as the duration recorded it (`until:<source id>`)."""

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        _drop_sibling_triggers(game, trigger)
        for card_id in self.ids:
            card = next((c for c in game.phased_out if c.id == card_id), None)
            if card is not None and card.phased_out_under == self.held_by:
                game.phase_in(card)


class ReturnExiledCardAndAddCounters(DelayedEffectSpecBase):
    """Lagrella, the Magpie's second sentence: "When an exiled card enters
    under your control this way, put two +1/+1 counters on it."

    `counter_kind`/`amount` are this effect's own data; the controller who has
    to have regained it ("under **your** control") is `trigger.controller` -
    the same value the closure this replaces captured, since both were always
    the creating ability's own controller (CR 603.7d/e).
    """

    kind: Literal["return_exiled_card_and_add_counters"] = "return_exiled_card_and_add_counters"

    counter_kind: Counter | str
    amount: int

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        card = trigger.still_affects(game)
        if card is None:
            return
        if card.controller != trigger.controller:
            return  # "under **your** control": an opponent's creature went home.
        # `Game.add_counters`, never `CardState.add_counters`: CR 614.16 - "some
        # replacement effects apply ... 'if an effect would put one or more
        # counters on a permanent'. These replacement effects apply if the effect
        # of a resolving spell or ability [does so]" - and this delayed ability
        # resolving is exactly that, so Vizier of Remedies and a doubling effect
        # get their say. CR 122.6's "counters being put on an object" event is
        # raised on the same route, which is what a "whenever one or more +1/+1
        # counters are put on this creature" ability watches for; the bare
        # `CardState` call raised neither.
        game.add_counters(card, self.counter_kind, self.amount)


class CreateAttackingTokens(DelayedEffectSpecBase):
    """Dalkovan Encampment's whole attack trigger: "Whenever you attack this
    turn, create `<n>` `<token>` tokens that are tapped and attacking.
    Sacrifice them at the beginning of the next end step."

    `count`/`definition` are this effect's own data; the controller and
    source are `trigger.controller`/`trigger.source_id`/`trigger.source_name`
    - the same values the closure this replaces closed over, since both were
    always the creating ability's own (CR 603.7d/e). Each token created gets
    its own one-shot `SacrificeSubject` trigger, the same "sacrifice this
    specific object at the next end step" idiom every other token-then-
    sacrifice clause in `machines/effects.py` uses.
    """

    kind: Literal["create_attacking_tokens"] = "create_attacking_tokens"

    count: int
    definition: TokenDefinition

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        defender = next(
            (
                attack.defender
                for attack in game.combat.attacks
                if (attacker := game.find_by_id(attack.attacker_id)) is not None
                and game.controller_of(attacker).username == trigger.controller
            ),
            None,
        )
        created = create_tokens(
            game,
            self.definition,
            trigger.controller,
            self.count,
            tapped=True,
            attacking=defender,
        )
        for token in created:
            game.create_delayed_trigger(
                DelayedTrigger(
                    text="Sacrifice them at the beginning of the next end step.",
                    effect=SacrificeSubject(),
                    event=TriggerEvent.BEGINNING_OF_STEP,
                    step=Step.END_STEP,
                    controller=trigger.controller,
                    source_id=trigger.source_id,
                    source_name=trigger.source_name,
                    subject_id=token.id,
                    expected_zone=Zone.BATTLEFIELD,
                    expected_stamp=token.zone_change_stamp,
                )
            )


class CreateTokensForController(DelayedEffectSpecBase):
    """ecl-T8: Scarblade's Malice's own "When that creature dies this turn,
    create a 2/2 black and green Elf creature token." - a plain CR 701.7a
    token creation with no rider, fired by a one-shot `TriggerEvent.DIES`
    delayed trigger (`expires_end_of_turn=True`, `subject_id` the targeted
    creature) rather than a step. `count`/`definition` are this effect's own
    data; `trigger.controller` is CR 603.7d/e's creating spell's own
    controller, who creates the token (CR 111.2) even though the creature
    that died may have belonged to someone else by then.
    """

    kind: Literal["create_tokens_for_controller"] = "create_tokens_for_controller"

    count: int
    definition: TokenDefinition

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        create_tokens(game, self.definition, trigger.controller, self.count)


class CreateTokenCopyOfControlledToken(DelayedEffectSpecBase):
    """ "Create a token that's a copy of a `[non-<Subtype>]` token you
    control." - Summon: Good King Mog XII's own Saga chapters II and III:
    "Whenever you cast a noncreature spell this turn, create a token that's
    a copy of a non-Saga token you control." CR 707.2's copy, over CR 111.1's
    token qualifier, filtered by `excluded_subtypes` (empty reads "any token
    you control" - no printing in the pool needs that bare form yet, but
    nothing here assumes there is always a filter).

    No target (CR 115.1 has nothing to check - "a ... token you control" is
    not "target ... token"), so the choice among more than one qualifying
    token is the controller's own, asked here at resolution (CR 608.2c) -
    `DecisionKind.CHOOSE_CARDS`, the same shape `machines/effects.py`'s own
    `_choose_permanents_to_sacrifice` already asks for a single pick among
    several legal ones. Exactly one candidate skips the question outright;
    CR 601.2c does not require asking a question with only one legal answer.
    None at all is not an error - CR 608.2c has no notion of a partially
    completed instruction, so the ability simply creates nothing.
    """

    kind: Literal["create_token_copy_of_controlled_token"] = "create_token_copy_of_controlled_token"

    excluded_subtypes: tuple[str, ...] = ()

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        if not game.is_in_game(trigger.controller):
            return
        board = game.computed_board()
        excluded = {subtype.lower() for subtype in self.excluded_subtypes}
        candidates = [
            state
            for state in game.permanents_controlled_by(trigger.controller)
            if is_token(state)
            and not any(word.lower() in excluded for word in board.of(state).subtypes)
        ]
        if not candidates:
            return
        if len(candidates) == 1:
            chosen = candidates[0]
        else:
            chosen_ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=trigger.controller,
                    prompt="choose a token to copy",
                    source=trigger.source_name,
                    source_id=trigger.source_id,
                    amount=1,
                    exact=True,
                    cards=tuple(state.id for state in candidates),
                )
            )
            chosen = next((state for state in candidates if state.id in chosen_ids), None)
            if chosen is None:
                return
        token_copy_of(game, chosen, trigger.controller)


class CreateTokenCopyOfLastKnown(DelayedEffectSpecBase):
    """ "create a token that's a copy of it at the beginning of the next end
    step. The token enters with half that many +1/+1 counters on it, rounded
    down." - Ochre Jelly's Split, via `machines/effects.py`'s
    `_parse_delayed_token_copy_of_it_clauses`.

    The object "it" names has usually left the battlefield (a dies trigger)
    and may have left its graveyard too, or ceased to exist as a token (CR
    704.5d) - so CR 707.2's copiable values are taken when the creating
    ability resolves and persisted here as `copiable`, the same way
    `CreatedTriggeredAbility.source_card` keeps a vanished source's printing.
    `enters_with_counters` is the count already worked out from what the
    object had (CR 614.1c's "enters with"), `(kind, amount)` pairs.
    """

    kind: Literal["create_token_copy_of_last_known"] = "create_token_copy_of_last_known"

    copiable: Card
    subject_id: UUID | None = None
    enters_with_counters: tuple[tuple[str, int], ...] = ()

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        if not game.is_in_game(trigger.controller):
            return
        original = CardState(
            id=self.subject_id or self.copiable.id,
            card=self.copiable,
            zone=Zone.EXILE,
            controller=trigger.controller,
            owner=trigger.controller,
        )
        token_copy_of(
            game,
            original,
            trigger.controller,
            enters_with_counters=self.enters_with_counters,
        )


class PayOrLoseTheGame(DelayedEffectSpecBase):
    """Summoner's Pact's own delayed half: pay `cost` - from floating mana and,
    per CR 608.2g, mana abilities activated while paying - or lose the game
    (CR 104.3e) trying.

    CR 603.7d/e: the controller who owes this is the one who created the
    delayed trigger, taken as it resolved - `trigger.controller`, not whoever
    controls anything now. A player already gone by the time this fires (a
    concession, an earlier loss) owes nothing further; CR 800.4a already took
    everything of theirs off the board.
    """

    kind: Literal["pay_or_lose_the_game"] = "pay_or_lose_the_game"

    cost: ManaCost

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        if not game.is_in_game(trigger.controller):
            return
        if game.may_pay_mana_cost(
            trigger.controller,
            self.cost,
            source=trigger.source_name,
            source_id=source_id_of(ability),
        ):
            return
        game.player_loses_the_game(trigger.controller)


class PayOrElseReturnExiledCard(DelayedEffectSpecBase):
    """Koya, Death from Above's own delayed half (TMT): "At the beginning of
    the next end step, you may pay `<cost>`. If you don't, return that card
    to the battlefield under its owner's control." CR 118.12's "unless" shape
    read the same direction `PayOrLoseTheGame` already reads it, except the
    consequence of *not* paying is CR 610.3's own return rather than a loss.

    `subject_id`/`expected_zone`/`expected_stamp` name the exiled card the
    antecedent "exile up to one other target creature" clause actually
    exiled (CR 400.7's own incarnation guard, the same `still_affects` check
    `DestroySubject` and every other blink-return spec here already share) -
    not this trigger's event subject, since the beginning-of-step event
    names no object of its own.
    """

    kind: Literal["pay_or_else_return_exiled_card"] = "pay_or_else_return_exiled_card"

    cost: ManaCost

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        if not game.is_in_game(trigger.controller):
            return
        if game.may_pay_mana_cost(
            trigger.controller,
            self.cost,
            source=trigger.source_name,
            source_id=source_id_of(ability),
        ):
            return
        card = trigger.still_affects(game)
        if card is None or card.owner is None:
            return
        game.put_onto_battlefield(card, card.owner)


class CombatDamageToPlayerDraw(DelayedEffectSpecBase):
    """Captain Howler, Sea Scourge's own delayed half: "Whenever that creature
    deals combat damage to a player this turn, you draw a card."

    `matches()` only checks the event kind and the subject's id (CR 603.7c);
    "combat damage" and "to a player" are this delayed trigger's own narrower
    condition, the same two checks `machines/triggers.condition_matches`'s
    DEALS_DAMAGE branch makes for a printed version of this shape.
    """

    kind: Literal["combat_damage_to_player_draw"] = "combat_damage_to_player_draw"

    that_many: bool = False
    """ "you draw that many cards" (The Inner Light's chapter II): the count is the
    combat damage the event reports (`GameEvent.amount`), not one."""

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        event = ability.event
        if event is None or not event.combat or event.player is None:
            return
        if not game.is_in_game(trigger.controller):
            return
        count = (event.amount or 0) if self.that_many else 1
        if count > 0:
            game.draw_cards(trigger.controller, count)


class CopyNextSpellYouCast(DelayedEffectSpecBase):
    """Dargo, the Shipwrecker's - and every "copy the next spell you cast this
    turn" shape's - own delayed half.

    **The spell is resolved from last known information.** The copy still
    happens when the original was countered in response: the delayed ability
    goes on the stack above the spell it is copying, an opponent may then put
    a counterspell above *that*, and by the time this resolves the original
    may be in a graveyard. So the object is fetched by `Game.find_by_id` -
    which searches every zone - rather than off `Game.stack`. CR 608.2b's
    on-resolution target check does not apply here: it only refuses an object
    that "specifies targets", and this ability specifies none.

    CR 707.10c is `may_retarget`: "Some effects copy a spell or ability and
    state that its controller may choose new targets for the copy." It is only
    offered when the card actually prints it.
    """

    kind: Literal["copy_next_spell_you_cast"] = "copy_next_spell_you_cast"

    may_retarget: bool

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        event = ability.event
        if event is None or event.subject_id is None:
            return
        spell = game.find_by_id(event.subject_id)
        if not isinstance(spell, CardState):
            return
        copy = game.copy_spell(spell, controller=trigger.controller)
        if self.may_retarget:
            game.offer_new_targets_for_copy(
                copy,
                trigger.controller,
                source_name=trigger.source_name,
                source_id=source_id_of(ability),
            )


class SpellEntersWithAdditionalCounter(DelayedEffectSpecBase):
    """ "When you next cast a creature spell this turn, that creature enters
    with an additional +1/+1 counter on it." (Kumano Faces Kakkazan's chapter
    II) - the delayed half. The cast spell is found by id (it may have been
    countered in response, CR 608.2b does not apply: no target), and its cast
    record gains one counter, which `replacement._cast_permission_rider_
    modifiers` applies as CR 614.1c's "enters with" on the permanent the spell
    becomes (CR 400.7d carries the record across)."""

    kind: Literal["spell_enters_with_additional_counter"] = "spell_enters_with_additional_counter"

    counter_kind: str

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        event = ability.event
        if event is None or event.subject_id is None:
            return
        spell = game.find_by_id(event.subject_id)
        record = game.cast_record_of(spell) if isinstance(spell, CardState) else None
        if record is not None and spell.zone is Zone.STACK:
            record.enters_with_counters.append(self.counter_kind)


class ReturnThatCardToBattlefieldUnderOwner(DelayedEffectSpecBase):
    """ "When it's put into a graveyard this turn, return that card to the
    battlefield under its owner's control." (Melira, the Living Cure) - the
    delayed half. The watched permanent is on the battlefield when the ability
    is created, so (CR 400.7) the only way "it" reaches a graveyard is straight
    off the battlefield, which is the `DIES` event; the card is the event's
    subject, and returns only if it is still in that graveyard as the very
    object the event named (CR 603.7c)."""

    kind: Literal["return_that_card_to_battlefield_under_owner"] = (
        "return_that_card_to_battlefield_under_owner"
    )

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        event = ability.event
        if event is None or event.subject_id is None:
            return
        card_state = game.find_by_id(event.subject_id)
        if (
            not isinstance(card_state, CardState)
            or card_state.zone is not Zone.GRAVEYARD
            or card_state.owner is None
            or card_state.zone_change_stamp != event.zone_change_stamp
        ):
            return
        game.put_onto_battlefield(card_state, card_state.owner)


class CopyNextSpellWithinManaValue(DelayedEffectSpecBase):
    """ "When you next cast an instant or sorcery spell with mana value `<N>`
    or less this turn, copy that spell." (Dual Strike, Gadwick's First Duel's
    chapter III) and its "... with mana value less than or equal to Loki's
    power ..." twin (Loki Laufeyson) - `CopyNextSpellYouCast` with a bound
    on the spell cast, checked as it is cast (CR 603.2: the event is the
    cast; CR 202.3 its mana value, `GameEvent.amount`).

    A spell above the bound is not "the next" matching spell, so the delayed
    ability keeps waiting (`DelayedTriggers.fire` spends `remaining` only on a
    match). The source's power is read when the spell is cast - the current
    value (CR 613.5), or its last known one once it has left (CR 608.2h).
    """

    kind: Literal["copy_next_spell_within_mana_value"] = "copy_next_spell_within_mana_value"

    may_retarget: bool
    at_most: int | None = None
    at_most_source_power: bool = False

    matches_against_the_game: ClassVar[bool] = True

    def event_matches(self, game: "Game", trigger: "DelayedTrigger", event: GameEvent) -> bool:
        mana_value = event.amount
        if mana_value is None and event.subject_id is not None:
            spell = game.find_by_id(event.subject_id)
            mana_value = spell.mana_value if isinstance(spell, CardState) else None
        if mana_value is None:
            return False
        bound: float | None = self.at_most
        if self.at_most_source_power:
            source = game.find_by_id(trigger.source_id) if trigger.source_id else None
            if not isinstance(source, CardState):
                return False
            bound = game.power_of(source) if source.zone is Zone.BATTLEFIELD else source.power
        return bound is not None and mana_value <= bound

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        CopyNextSpellYouCast(may_retarget=self.may_retarget)(game, ability, trigger)


class NextSpellCannotBeCountered(DelayedEffectSpecBase):
    """ "The next spell you cast this turn can't be countered." - Theorist's
    Sanctum's own Theorist's Proxy, and Mistrise Village (Tarkir:
    Dragonstorm), the off-set card proving the shape is general.

    The same CR 603.7 delayed-trigger shape `CopyNextSpellYouCast` already
    uses for an identical "the next spell you cast this turn" template, down
    to the same last-known-information fetch: if the spell was already
    countered by the time this resolves (someone responded to the delayed
    trigger itself rather than to the grant it was too late to give), there
    is nothing left to mark and this is a no-op, not an error.

    What "can't be countered" *means* is `machines/casting_restrictions.
    cannot_be_countered`'s job, not this one's - this only records the grant,
    the same way a permanent's layer-6 "gains an ability" grant is recorded
    on `CardState.granted_ability_texts` rather than mutating some separate
    uncounterable flag, so `cannot_be_countered` reads one place for both a
    printed and a granted "This spell can't be countered."
    """

    kind: Literal["next_spell_cannot_be_countered"] = "next_spell_cannot_be_countered"

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        event = ability.event
        if event is None or event.subject_id is None:
            return
        spell = game.find_by_id(event.subject_id)
        if not isinstance(spell, CardState) or spell.zone is not Zone.STACK:
            return
        spell.granted_ability_texts = (
            *spell.granted_ability_texts,
            "This spell can't be countered.",
        )


class ReturnRiderCounter(EngineModel):
    """Phelia, Exuberant Shepherd's third sentence: "If it entered under your
    control, put a +1/+1 counter on Phelia."

    Not a `DelayedEffectSpecBase` itself - its call shape is the blink idiom's
    own rider shape (`Game`, the returned card, the creating ability's
    controller/source id/source name), not a delayed effect's - it only ever
    appears nested inside `DelayedBlinkReturnWithRider.rider`. Conditional on
    the delayed return itself (not on anything true when the outer ability
    resolved), so it has to run as part of the delayed trigger's own
    resolution, not the attack trigger's.
    """

    model_config = ConfigDict(frozen=True)

    amount: int
    who: str
    """`<recipient>`, lowercased - checked against the resolving source's own
    name at run time (its short form, "Phelia", included), never hardcoded, so
    this reads any card printing the same shape rather than being one more
    name-keyed table row."""

    def __call__(
        self,
        game: "Game",
        returned: CardState,
        controller: str,
        source_id: UUID | None,
        source_name: str,
    ) -> None:
        if returned.controller != controller:
            return  # "if it entered under your control"
        recipient = game.find_by_id(source_id) if source_id is not None else None
        if recipient is None or recipient.zone is not Zone.BATTLEFIELD:
            return  # the source is gone; CR 608.2b's outcome for no legal target
        short_name = source_name.split(",")[0].strip().lower()
        if self.who not in ("this creature", "this permanent", source_name.lower(), short_name):
            return
        game.add_counters(recipient, Counter.PLUS_ONE, self.amount)


class DelayedBlinkReturnWithRider(DelayedEffectSpecBase):
    """The blink idiom (`ReturnSubjectToBattlefieldUnderOwner`) plus a rider
    clause conditional on the return actually happening - Phelia's own three-
    clause paragraph, via `machines/effects.py`'s `_parse_delayed_blink_
    clauses`. Used only when a rider clause is present; with none, the plain
    `ReturnSubjectToBattlefieldUnderOwner` effect is used directly.
    """

    kind: Literal["delayed_blink_return_with_rider"] = "delayed_blink_return_with_rider"

    rider: ReturnRiderCounter

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        returned = trigger.still_affects(game)
        if returned is None or returned.owner is None:
            return
        game.put_onto_battlefield(returned, returned.owner, tapped=False)
        if returned.zone is Zone.BATTLEFIELD:
            self.rider(game, returned, trigger.controller, trigger.source_id, trigger.source_name)


# ---------------------------------------------------------------------------
# CR 603.12 reflexive triggered abilities' own consequences.
# ---------------------------------------------------------------------------
#
# `DelayedTriggers.create_reflexive` (below) stores its trigger in `pending`
# exactly like an ordinary delayed trigger fired by `fire` does, and `pending`
# is a persisted field - a reflexive ability sits on the stack, waiting for
# priority to pass around it, for exactly as long as an ordinary one does, so
# it can just as easily be serialized mid-resolution. (The task that asked for
# this file's own rewrite floated the opposite as something to confirm rather
# than assume; this is that confirmation, and it was wrong - the four
# `resolve_reflexive` closures `machines/effects.py` used to build inline, and
# `machines/replacement.py`'s own `exile_that_card`, needed exactly the same
# treatment as every other `DelayedTrigger.callback`.)
#
# Three of the four `resolve_reflexive` shapes need no data of their own at
# all: each one's `text` argument to `create_reflexive_trigger` is always the
# very same `consequence_text` the closure re-parses, which is already
# `DelayedTrigger.text` by the time this runs - so re-reading `trigger.text`
# needs no field. `parse_mixed_effect`/`_parse_counters_and_becomes_type_
# clause`/`_parse_if_control_colored_permanent_damage_clause` are re-run here
# exactly the way this engine already re-derives a printed ability's effect
# from its oracle text on every resolution rather than caching a closure -
# `machines/effects.py` imports from here, so the import has to run the other
# way, inside `__call__`.


class ReflexiveConsequence(DelayedEffectSpecBase):
    """ "You may sacrifice `<restriction>`. When you do, `<consequence>`."
    (CR 603.12) and "exile target card from a graveyard. When a creature card
    is exiled this way, `<consequence>`." - `machines/effects.py`'s
    `_parse_reflexive_sacrifice_clause` and `_parse_exile_target_card_
    reflexive_creature_counter`.
    """

    kind: Literal["reflexive_consequence"] = "reflexive_consequence"

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        from .effects import reflexive_consequence_effect

        consequence_effect = reflexive_consequence_effect(trigger.text)
        if consequence_effect is not None:
            consequence_effect(game, ability)


class DungeonRoomAbility(DelayedEffectSpecBase):
    """A dungeon room's ability (CR 309.4c): "When you move your venture
    marker into this room, [effect.]", queued by `machines/dungeon.venture`
    as the marker moves in. The effect is the room's own printed text
    (`trigger.text`), resolved through the triggered-ability dispatcher; a
    room whose text nothing reads leaves an `UnmodeledTriggerEffectNotice`
    rather than doing nothing silently. Once it has resolved, CR 309.6's
    state-based action is performed for its dungeon (`machines/dungeon.
    complete_finished_dungeons`)."""

    kind: Literal["dungeon_room"] = "dungeon_room"
    room: str

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        from .dungeon import complete_finished_dungeons
        from .effects import UnmodeledTriggerEffectNotice, trigger_effect_for

        effect = trigger_effect_for(trigger.source_name, None, trigger.text)
        if effect is None:
            game.unmodeled_trigger_effect_notices.append(
                UnmodeledTriggerEffectNotice(
                    source_id=trigger.source_id,
                    source_name=trigger.source_name,
                    text=trigger.text,
                )
            )
        else:
            effect(game, ability)
        complete_finished_dungeons(game, resolving_id=ability.id)


class ReflexivePayEnergyConsequence(DelayedEffectSpecBase):
    """ "You may pay `{E}{E}{E}`. When you do, `<consequence>`." (CR 603.12,
    CR 107.14, CR 118.3) - Guide of Souls' attack trigger,
    `machines/effects.py`'s `_parse_reflexive_pay_energy_clause`. The
    consequence is `reflexive_pay_consequence_effect`'s to read.
    """

    kind: Literal["reflexive_pay_energy_consequence"] = "reflexive_pay_energy_consequence"

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        from .effects import reflexive_pay_consequence_effect

        consequence_effect = reflexive_pay_consequence_effect(trigger.text)
        if consequence_effect is not None:
            consequence_effect(game, ability)


class ReflexivePayManaConsequence(DelayedEffectSpecBase):
    """ "You may pay `{N}`. When you do, `<consequence>`." (CR 603.12, CR
    118.3) - Lich's Relic's and Labyrinth Adversary's own triggers,
    `machines/effects.py`'s `_parse_reflexive_pay_mana_clause`: the ordinary-
    mana twin of `ReflexivePayEnergyConsequence`, reading the same
    consequences (`reflexive_pay_consequence_effect`).
    """

    kind: Literal["reflexive_pay_mana_consequence"] = "reflexive_pay_mana_consequence"

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        from .effects import reflexive_pay_consequence_effect

        consequence_effect = reflexive_pay_consequence_effect(trigger.text)
        if consequence_effect is not None:
            consequence_effect(game, ability)


class ReflexiveMayPayManaIfYouDo(DelayedEffectSpecBase):
    """ "You may pay `{N}`. If you do, `<consequence>`." as the body of a
    reflexive ability (CR 603.12 + CR 118.12) - the "When you do, you may pay
    {2}. If you do, create a 1/1 ... Pest" rider on Valentin, Dean of the
    Vein's dies replacement (`machines/replacement/other_statics.py`). The
    payment and its consequence resolve together on this one ability, read by
    `machines/effects/mana.py`'s `_parse_may_pay_mana_if_you_do_clause`.
    """

    kind: Literal["reflexive_may_pay_mana_if_you_do"] = "reflexive_may_pay_mana_if_you_do"

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        from .effects.mana import _parse_may_pay_mana_if_you_do_clause

        effect = _parse_may_pay_mana_if_you_do_clause(trigger.text)
        if effect is not None:
            effect(game, ability)


class ReflexiveMandatoryTokenDamageConsequence(DelayedEffectSpecBase):
    """ "Create `<n>` `<token>` token[s]. When you do, if ..., `<damage>`."
    (CR 603.12, CR 603.4) - Ajani, Nacatl Avenger's `0`,
    `machines/effects.py`'s `_parse_reflexive_mandatory_token_clause`.

    The intervening *if* (CR 603.4) is already checked, once, before this
    reflexive ability was even created (CR 603.12's "checked immediately after
    being created") - only the damage half is left to run here.
    """

    kind: Literal["reflexive_mandatory_token_damage_consequence"] = (
        "reflexive_mandatory_token_damage_consequence"
    )

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        from .effects import _parse_if_control_colored_permanent_damage_clause

        parsed = _parse_if_control_colored_permanent_damage_clause(trigger.text)
        if parsed is None:
            return
        _condition_holds, deal_the_damage = parsed
        deal_the_damage(game, ability)


class ReflexiveCounterCountConsequence(DelayedEffectSpecBase):
    """ "Put a `<kind>` counter on this `<permanent>`. When you do, if it has
    `<N>` or more `<kind>` counters on it, `<consequence>`." (CR 603.12, CR
    603.4) - Earthbender Ascension's landfall, `machines/effects.py`'s
    `_parse_reflexive_self_counter_if_clause`.

    The intervening *if* was checked as this reflexive ability was created;
    CR 603.4 checks it again as it resolves, against the same source, and the
    ability does nothing if it is no longer true.
    """

    kind: Literal["reflexive_counter_count_consequence"] = "reflexive_counter_count_consequence"

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        from .effects import _reflexive_counter_count_parts

        parts = _reflexive_counter_count_parts(trigger.text)
        if parts is None:
            return
        holds, consequence = parts
        source = ability.source(game)
        if source is None or not holds(source):
            return
        consequence(game, ability)


def _reflexive_when_you_do_ability(trigger: "DelayedTrigger") -> TriggeredAbility | None:
    """ "When you do, `<effect>`." (CR 603.12) as a `TriggeredAbility` whose
    `effect` field holds only `<effect>` - not `DelayedTrigger.as_ability`'s
    own fallback, which leaves `condition` *and* `effect` both set to the
    whole unsplit sentence.

    That fallback is fine for every reflexive consequence that reads its own
    resolution off `trigger.text` again (`ReflexiveConsequence` and its
    siblings, none of which name a target of their own), but it breaks a
    reflexive ability whose `<effect>` half prints "target ...": CR 603.3d's
    targets are announced as the ability goes on the stack, off
    `AbilityOnStack.ability.text` via `machines/targeting.profile_for_text`,
    and that reader has no shape for a target sitting inside an unstripped
    "When you do," preamble - the whole sentence answers "no targets" and the
    ability sits on the stack unable to find what "it"/"that creature" means
    once it resolves. Splitting the two apart here, the same way any other
    printed "When ..., ..." sentence already is, is what lets `profile_for_
    text` see the effect's own "target creature you control" (or "target
    creature") on its own.
    """
    prefix = "when you do, "
    if not trigger.text.lower().startswith(prefix):
        return None
    return TriggeredAbility(
        raw=trigger.text,
        text=trigger.text,
        face=trigger.source_name,
        word=TriggerWord.WHEN,
        condition="you do",
        effect=trigger.text[len(prefix) :].strip(),
        event=trigger.event,
    )


class ReflexiveAttachSubjectToTargetConsequence(DelayedEffectSpecBase):
    """ "Create `<a token>` [...]. When you do, attach it to target creature
    you control." (CR 603.12) - Dain Ironfoot's own named-Equipment-token
    trigger, `machines/effects.py`'s equipment-token-then-attach reader.

    Unlike `ReflexiveConsequence`'s own "it"/"that" antecedents, which are
    all still on the battlefield and findable off the *creating* ability's
    own source or target list, "it" here is the token the antecedent just
    created - an object with no printed description this reflexive trigger
    could re-derive, so its id is carried on `DelayedTrigger.subject_id`
    (CR 603.7c) instead of re-parsed from text.
    """

    kind: Literal["reflexive_attach_subject_to_target_consequence"] = (
        "reflexive_attach_subject_to_target_consequence"
    )

    def printed_ability(self, trigger: "DelayedTrigger") -> TriggeredAbility | None:
        return _reflexive_when_you_do_ability(trigger)

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        from .effects import attach_permanent

        if trigger.subject_id is None:
            return
        subject = game.find_by_id(trigger.subject_id)
        if not isinstance(subject, CardState) or subject.zone is not Zone.BATTLEFIELD:
            return
        for target in game.resolve_targets(ability):
            if isinstance(target, CardState) and attach_permanent(game, subject, target):
                return


class ReflexiveReturnThenAttachToSubjectConsequence(DelayedEffectSpecBase):
    """ "Create `<a token>`. When you do, return target `<card>` from your
    graveyard to the battlefield, then attach it to that token." (CR 603.12,
    CR 701.3a) - Ratonhnhake:ton's combat damage trigger.

    The reflexive ability names its own target (announced off `<effect>`
    alone, `printed_ability`, CR 603.3d); "that token" is the one the
    antecedent created, carried on `DelayedTrigger.subject_id` (CR 603.7c).
    The return is read like any other "return ... to the battlefield" clause
    and run first, the attach follows (CR 608.2c) to whatever came back.
    """

    kind: Literal["reflexive_return_then_attach_to_subject_consequence"] = (
        "reflexive_return_then_attach_to_subject_consequence"
    )

    def printed_ability(self, trigger: "DelayedTrigger") -> TriggeredAbility | None:
        return _reflexive_when_you_do_ability(trigger)

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        from .effects import attach_permanent, parse_mixed_effect

        printed = _reflexive_when_you_do_ability(trigger)
        if printed is None or printed.effect is None or trigger.subject_id is None:
            return
        returned, _, _ = printed.effect.rstrip(".").partition(", then attach it to that token")
        returning = parse_mixed_effect(returned + ".")
        if returning is None:
            return
        targets = [t for t in game.resolve_targets(ability) if isinstance(t, CardState)]
        returning(game, ability)
        subject = game.find_by_id(trigger.subject_id)
        if not isinstance(subject, CardState) or subject.zone is not Zone.BATTLEFIELD:
            return
        for target in targets:
            if target.zone is Zone.BATTLEFIELD:
                attach_permanent(game, target, subject)


class ReflexiveDamageEqualToSubjectPowerConsequence(DelayedEffectSpecBase):
    """ "When one or more Equipment become attached to that creature this
    way, that creature deals damage equal to its power to up to one target
    creature." (CR 603.12) - Thorin, Mountain-king's own reflexive trigger,
    `machines/effects.py`'s attach-any-number-of-Equipment reader.

    "That creature" is the one the antecedent attached Equipment to - not
    this ability's own source (Thorin, whose own power the sentence never
    names) - carried the same way, on `DelayedTrigger.subject_id`.
    """

    kind: Literal["reflexive_damage_equal_to_subject_power_consequence"] = (
        "reflexive_damage_equal_to_subject_power_consequence"
    )

    def printed_ability(self, trigger: "DelayedTrigger") -> TriggeredAbility | None:
        return _reflexive_when_you_do_ability(trigger)

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        if trigger.subject_id is None:
            return
        dealer = game.find_by_id(trigger.subject_id)
        if not isinstance(dealer, CardState) or dealer.zone is not Zone.BATTLEFIELD:
            return
        amount = game.power_of(dealer)
        if amount is None or amount <= 0:
            return
        for target in game.resolve_targets(ability):
            if isinstance(target, CardState) and target.zone is not Zone.BATTLEFIELD:
                continue
            game.deal_damage(target, amount, source=dealer)


class ReflexiveDamageEqualToSubjectManaValueConsequence(DelayedEffectSpecBase):
    """ "When you reveal [or exile] a nonland card this way, `<source>` deals
    damage equal to that card's mana value to any target." (CR 603.12) -
    Calibrated Blast's and Hidetsugu, Devouring Chaos's reflexive trigger.

    "That card" is the one the antecedent revealed or exiled - an object that
    has already moved on (the bottom of a library, exile) and that no printed
    description could re-derive - so its id is carried on
    `DelayedTrigger.subject_id` (CR 603.7c) and its mana value (CR 202.3) is
    read as the ability resolves. The damage is dealt by the source that
    created the trigger (CR 120.1), found by id wherever it now is.
    """

    kind: Literal["reflexive_damage_equal_to_subject_mana_value_consequence"] = (
        "reflexive_damage_equal_to_subject_mana_value_consequence"
    )

    def printed_ability(self, trigger: "DelayedTrigger") -> TriggeredAbility | None:
        return _reflexive_when_you_do_ability(trigger)

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        if trigger.subject_id is None:
            return
        subject = game.find_by_id(trigger.subject_id)
        if not isinstance(subject, CardState):
            return
        amount = game.characteristics_of(subject).mana_value
        if not amount or amount <= 0:
            return
        dealer = game.find_by_id(trigger.source_id) if trigger.source_id is not None else None
        for target in game.resolve_targets(ability):
            if isinstance(target, CardState) and target.zone is not Zone.BATTLEFIELD:
                continue
            game.deal_damage(
                target, int(amount), source=dealer if isinstance(dealer, CardState) else None
            )


class ReflexiveWhenYouDoConsequence(DelayedEffectSpecBase):
    """ "`<mandatory instruction>`. When you do, `<effect>`." (CR 603.12) -
    Red Hulk's "put a +1/+1 counter on him. When you do, he deals damage
    equal to the number of +1/+1 counters on him to any other target.",
    `machines/effects.py`'s counter-then-reflexive reader. The effect half
    names its own targets, so it is announced off `<effect>` alone (`printed_
    ability`, CR 603.3d) and re-read from the text as it resolves.
    """

    kind: Literal["reflexive_when_you_do_consequence"] = "reflexive_when_you_do_consequence"

    def printed_ability(self, trigger: "DelayedTrigger") -> TriggeredAbility | None:
        return _reflexive_when_you_do_ability(trigger)

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        from .effects import reflexive_consequence_effect

        printed = _reflexive_when_you_do_ability(trigger)
        if printed is None or printed.effect is None:
            return
        consequence = reflexive_consequence_effect(printed.effect)
        if consequence is not None:
            consequence(game, ability)


class ReflexivePreventedDamagePayoff(DelayedEffectSpecBase):
    """ "When damage is prevented this way, `<spell>` deals that much damage
    to that source's controller and you draw that many cards." (CR 603.12,
    CR 615.5) - New Way Forward's payoff, created by `Game.
    _deal_reflected_damage` the moment its shield prevents damage. The amount
    prevented and the source's controller are fixed then (CR 608.2h) and
    carried here as data; the spell that made the shield deals the damage
    from wherever it now is, as it last existed (CR 113.7a, CR 608.2h)."""

    kind: Literal["reflexive_prevented_damage_payoff"] = "reflexive_prevented_damage_payoff"
    amount: int
    player: str
    draws: bool = False

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        source = game.find_by_id(trigger.source_id) if trigger.source_id is not None else None
        dealer = source if isinstance(source, CardState) else None
        if game.is_in_game(self.player):
            game.deal_damage(game.player(self.player), self.amount, source=dealer)
        if self.draws and game.is_in_game(trigger.controller):
            game.draw_cards(trigger.controller, self.amount)


class ReflexiveExileCopiedCard(DelayedEffectSpecBase):
    """Superior Spider-Man's "When you do, exile that card." (CR 603.12,
    `machines/replacement.py`'s `_choose_a_quality`-adjacent copy-choice
    reflexive), for DDR#986.

    **CR 400.7 is why this re-reads the zone.** "An object that moves from one
    zone to another becomes a new object with no memory of, or relation to,
    its previous existence" - so a card that has left `zone_when_copied` by
    the time this resolves is not "that card" any more and nothing is exiled.
    """

    kind: Literal["reflexive_exile_copied_card"] = "reflexive_exile_copied_card"

    card_id: UUID
    zone_when_copied: Zone

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        card = game.find_by_id(self.card_id)
        if not isinstance(card, CardState):
            return
        if card.zone is not self.zone_when_copied or card.owner is None:
            return  # CR 400.7: no longer the object the ability referred to.
        # `zone_when_copied` can be a shared one (CR 400.1) - the copy this
        # ability follows is made on the stack - so the lift-out and the move
        # both go through `Game`, which owns those. `Player.cards_in` refuses
        # a shared zone rather than answering with an empty pile of its own.
        game.exile_permanent(card)


class RevokeGrantedAbility(DelayedEffectSpecBase):
    """Strip a granted activation text off a permanent once this delayed
    trigger's own watched event fires - Emrakul, the Exigent Doom: "Target
    land gains "{T}: Add {C}{C}" until this card is cast from exile." The
    grant itself (CR 113.10) is made immediately, by the ability that reads
    this sentence; this is only the "until" half, watching `TriggerEvent.
    CAST_SPELL` with `DelayedTrigger.subject_id` set to the *exiled card*, not
    the land - the same "two different objects" split `StaticPrisonReturn`'s
    own docstring explains, since the event this waits for and the permanent
    this changes are never the same object here either.

    CR 603.7c's own guard: `land_id`/`land_stamp` are the land's identity at
    the moment it was granted the ability, so a land that has since left the
    battlefield, or been replaced by a new incarnation of the same id, is
    left alone rather than having some other object's granted text stripped.
    """

    kind: Literal["revoke_granted_ability"] = "revoke_granted_ability"

    land_id: UUID
    land_stamp: UUID
    granted_text: str

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        land = game.find_by_id(self.land_id)
        if not isinstance(land, CardState):
            return
        if land.zone is not Zone.BATTLEFIELD or land.zone_change_stamp != self.land_stamp:
            return
        if self.granted_text in land.granted_ability_texts:
            land.granted_ability_texts = tuple(
                text for text in land.granted_ability_texts if text != self.granted_text
            )


class AddManaWhenLandTapped(DelayedEffectSpecBase):
    """Molten Tide's and High Tide's shared shape: "Until end of turn,
    whenever [you tap|a player taps] a[n] <land subtype> for mana, [add|that
    player adds] an additional <mana>." (Molten Tide: "you tap a Mountain
    ... add"; High Tide: "a player taps an Island ... that player adds".)

    CR 605.1b: the created ability is itself a mana ability - it doesn't
    require a target, it triggers from the activation of an activated mana
    ability (CR 106.12a's tap), and it could add mana to a player's mana
    pool when it resolves - so `is_mana_ability = True` here, and CR 605.4a
    resolves it inline the instant it fires (`models.game.Game._resolve_
    triggered_mana_abilities`, which reads this flag), with no stack and no
    waiting for priority, exactly as a printed triggered mana ability
    already does.
    """

    kind: Literal["add_mana_when_land_tapped"] = "add_mana_when_land_tapped"
    is_mana_ability: ClassVar[bool] = True

    land_subtype: str
    mana: tuple[Color, ...]
    only_creators_own_taps: bool
    """True for "you tap" (Molten Tide - only the ability's own controller's
    taps count, and the mana goes to them). False for "a player taps ...
    that player adds" (High Tide - any player's tap counts, and the mana
    goes to whoever tapped, not necessarily this ability's own controller)."""

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        event = ability.event
        if event is None or event.subject_controller is None:
            return
        if self.only_creators_own_taps and event.subject_controller != trigger.controller:
            return
        if not any(word.lower() == self.land_subtype.lower() for word in event.subject_subtypes):
            return
        pool = game.mana_pool_receiving(event.subject_controller)
        for color in self.mana:
            pool.add(color)


class PumpEventSubject(DelayedEffectSpecBase):
    """ "Until your next turn, whenever a creature attacks you or a
    planeswalker you control, it gets `<power>`/`<toughness>` until end of
    turn." - Jace, Reality Sculptor's own `-3`. Unlike `TapSubject`'s fixed
    `trigger.subject_id` (CR 603.7c: an object this ability was created
    already knowing about), this trigger names no object at creation time at
    all - "a creature" is answered fresh by whichever creature the `ATTACKS`
    event that fired it was actually about, read off `AbilityOnStack.event`
    the same way `AddManaWhenLandTapped` reads its own tapped land.

    Sublayer 7c (CR 613.4c), `Duration.UNTIL_END_OF_TURN` - this pump has its
    own, shorter duration, independent of the delayed trigger's own longer
    "until your next turn" watch: the trigger can fire again tomorrow, on a
    fresh attacker, but each pump it grants ends at the ordinary cleanup.

    `keywords` is the same sentence's own trailing "and gain[s] `<keyword-
    list>`" - Garruk, Curse Breaker's own `-4`, "... those creatures get
    +2/+2 and gain trample until end of turn." One `ContinuousEffect` per
    keyword, layer 6 (CR 613.1f), alongside the layer 7c pump - the same two-
    layer split `_SELF_KEYWORD_GRANT_UNTIL_EOT_RE`'s own effect in
    `machines/effects.py` already makes for a plain "gets `<P>`/`<T>` and
    gains `<keyword>`" clause. Empty (the default) for Jace's own printing,
    which grants no keyword at all.
    """

    kind: Literal["pump_event_subject"] = "pump_event_subject"

    power: int
    toughness: int
    keywords: tuple[str, ...] = ()

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        event = ability.event
        if event is None or event.subject_id is None:
            return
        target = game.find_by_id(event.subject_id)
        if not isinstance(target, CardState) or target.zone != Zone.BATTLEFIELD:
            return
        selector = only_this_incarnation(target, target.zone_change_stamp)
        if self.power != 0 or self.toughness != 0:
            game.continuous_effects.add(
                ContinuousEffect(
                    description=(
                        f"{trigger.source_name}: {target.name} gets "
                        f"{self.power:+d}/{self.toughness:+d}"
                    ),
                    layer=Layer.POWER_TOUGHNESS,
                    sublayer=Sublayer.MODIFY,
                    timestamp=game.continuous_effects.tick(),
                    duration=Duration.UNTIL_END_OF_TURN,
                    source_id=trigger.source_id,
                    # No `source_ability`, deliberately: CR 611.2c's one-time
                    # resolved effect does not depend on the source still
                    # *having* this ability once it has fired - unlike a static
                    # grant's own `_source_line_for`-matched `source_ability`
                    # (CR 613.6), there is no "for as long as" here for a source
                    # leaving, or having its text rewritten, to end early. Setting
                    # this to `trigger.text` used to fail CR 613.6's `has_ability`
                    # check on every board computation - `trigger.text` is only
                    # the parsed *effect* clause, with the printed cost/chapter
                    # prefix ("−3: ", "I — ") already stripped off by the parser
                    # that built it, so it could never equal the permanent's own
                    # verbatim printed line and the pump silently never applied.
                    selector=selector,
                    modification=modify_power_toughness(self.power, self.toughness),
                ),
                game,
            )
        for keyword in self.keywords:
            game.continuous_effects.add(
                ContinuousEffect(
                    description=f"{trigger.source_name}: {target.name} gains {keyword}",
                    layer=Layer.ABILITY,
                    timestamp=game.continuous_effects.tick(),
                    duration=Duration.UNTIL_END_OF_TURN,
                    source_id=trigger.source_id,
                    selector=selector,
                    modification=grant_ability(keyword),
                ),
                game,
            )


class CountersAndKeywordsEventSubject(DelayedEffectSpecBase):
    """ "Whenever a creature you control attacks alone this turn, put three
    +1/+1 counters on it. It gains trample, lifelink, and indestructible
    until end of turn." - The Last Ronin's own Saga chapter III (CR 714.4):
    a delayed trigger created as that chapter's own effect, watching
    whichever creature the *next* qualifying `ATTACKS` event names, the
    identical "a creature" reading `PumpEventSubject` already gives Jace,
    Reality Sculptor's own delayed pump - but putting a *permanent* counter
    (CR 122.1) on the subject alongside a temporary keyword grant, rather
    than `PumpEventSubject`'s own single until-end-of-turn power/toughness
    change.

    `counter_kind`/`counter_amount` of `0` skips the counter half entirely
    (Group 0b's "put N counters" convention elsewhere already treats zero as
    nothing to add), and an empty `keywords` skips the grant half - so this
    also covers a card that prints only one half of the shape, not only
    both at once.
    """

    kind: Literal["counters_and_keywords_event_subject"] = "counters_and_keywords_event_subject"

    counter_kind: Counter | str
    counter_amount: int
    keywords: tuple[str, ...]

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        put_counters_and_grant_keywords_to_event_subject(
            game,
            ability.event,
            self.counter_kind,
            self.counter_amount,
            self.keywords,
            source_name=trigger.source_name,
            source_id=trigger.source_id,
        )


def put_counters_and_grant_keywords_to_event_subject(
    game: "Game",
    event: GameEvent | None,
    counter_kind: Counter | str,
    counter_amount: int,
    keywords: tuple[str, ...],
    *,
    source_name: str,
    source_id: UUID | None,
) -> None:
    """Put `counter_amount` `counter_kind` counters on the object the
    triggering event names and grant it `keywords` until end of turn - the
    shared body of `CountersAndKeywordsEventSubject` and `machines/effects.
    _parse_event_subject_counters_and_keywords_clause` ("put a +1/+1 counter
    on it and it gains haste until end of turn").

    Nothing happens when that object is no longer on the battlefield: the
    counters and the grant are both about a permanent (CR 122.1, CR 611.2a).
    """
    if event is None or event.subject_id is None:
        return
    target = game.find_by_id(event.subject_id)
    if not isinstance(target, CardState) or target.zone is not Zone.BATTLEFIELD:
        return
    if counter_amount > 0:
        # `Game.add_counters`, never `CardState.add_counters` - CR 614.16's
        # replacement effects (Vizier of Remedies, a doubling effect) and
        # CR 122.6's "counters put on an object" event both need this to
        # go through the game, the same reason `ReturnExiledCardAndAdd
        # Counters` above does.
        game.add_counters(target, counter_kind, counter_amount)
    for keyword in keywords:
        game.continuous_effects.add(
            ContinuousEffect(
                description=f"{source_name}: {target.name} gains {keyword}",
                layer=Layer.ABILITY,
                timestamp=game.continuous_effects.tick(),
                duration=Duration.UNTIL_END_OF_TURN,
                source_id=source_id,
                selector=only_this_incarnation(target, target.zone_change_stamp),
                modification=grant_ability(keyword),
            ),
            game,
        )


@cache
def _created_ability(text: str) -> TriggeredAbility | None:
    """`text` read as one printed triggered ability, once per distinct text -
    `CreatedTriggeredAbility` asks on every event it might match."""
    from .triggers import granted_triggered_abilities_of

    found = granted_triggered_abilities_of([text])
    return found[0] if found else None


class CreatedTriggeredAbility(DelayedEffectSpecBase):
    """A triggered ability a resolving spell or ability creates for a stated
    duration - "Whenever a creature you control enters this turn, ..." (First
    Day of Class), "Until end of turn, whenever a creature you control deals
    combat damage to a player, ..." (Dovin, Grand Arbiter's +1).

    CR 603.7: "An effect may create a delayed triggered ability that can do
    something at a later time." CR 603.7b: it triggers only once "unless it
    has a stated duration, such as 'this turn'" - so the `DelayedTrigger`
    carrying this is built with `remaining=None` and `expires_end_of_turn=
    True`, and CR 514.2's cleanup step ends it.

    `ability_text` is the created ability written as a printed one ("Whenever
    a creature you control enters, put a +1/+1 counter on it ..."), the
    duration words already taken off by the reader that built it (`machines/
    effects._parse_turn_scoped_trigger_creation`). Everything about it is read
    back off that text by the same machinery a printed trigger goes through:
    the condition by `machines/triggers.condition_matches` (`event_matches`),
    the effect by `machines/effects.trigger_effect_for` (`__call__`). So one
    template closes every created trigger whose printed twin is already read,
    rather than one hand-written filter field per card, and the record stays a
    string - it round-trips through `Game.model_dump` with no callable on it.

    `source_card` is the creating object's printing, kept so the condition
    can still be matched when that object is in no zone at all - a spell
    mid-resolution (a fused Beck // Call's Birds enter while it resolves), a
    copy of a spell (CR 707.10a), a token that left (CR 111.7) - since CR
    603.7d/e fix the source as it was when the ability was created, not
    whatever is left of it.
    """

    kind: Literal["created_triggered_ability"] = "created_triggered_ability"

    matches_against_the_game: ClassVar[bool] = True

    ability_text: str
    source_card: Card | None = None

    def parsed(self) -> TriggeredAbility | None:
        return _created_ability(self.ability_text)

    def printed_ability(self, trigger: "DelayedTrigger") -> TriggeredAbility | None:
        parsed = self.parsed()
        if parsed is None:
            return None
        # Shown as the trigger's own text: the opening-hand rider reads "your
        # upkeep" for the matcher but prints "your first upkeep" (CR 603.7b's
        # once is `remaining=1`), and a seat is shown what was printed.
        return parsed.model_copy(
            update={"face": trigger.source_name, "text": trigger.text, "raw": trigger.text}
        )

    def _source(self, game: "Game", trigger: "DelayedTrigger") -> CardState | None:
        if trigger.source_id is not None:
            found = game.find_by_id(trigger.source_id)
            if isinstance(found, CardState):
                return found
        if self.source_card is None:
            return None
        return CardState(
            id=trigger.source_id or self.source_card.id,
            card=self.source_card,
            zone=Zone.EXILE,
            controller=trigger.controller,
            owner=trigger.controller,
        )

    def event_matches(self, game: "Game", trigger: "DelayedTrigger", event: GameEvent) -> bool:
        from .triggers import condition_matches

        parsed = self.parsed()
        source = self._source(game, trigger)
        if parsed is None or source is None:
            return False
        return condition_matches(game, parsed, source, trigger.controller, event)

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        from .effects import trigger_effect_for

        parsed = self.parsed()
        if parsed is None:
            return
        effect = trigger_effect_for(trigger.source_name, parsed.event, parsed.effect)
        if effect is not None:
            effect(game, ability)


class ActOnEachSubject(DelayedEffectSpecBase):
    """ "Exile them" / "Sacrifice those tokens" at the beginning of the next
    end step - one delayed triggered ability about every object its own
    paragraph just made (Lightning Coils, Feral Lightning, Chandra,
    Flamecaller), where `SacrificeSubject`/`ExileSubjectAtNextEndStep` are
    about one.

    CR 603.7c is applied object by object: `subjects` pairs each object's id
    with the `zone_change_stamp` it had when the ability was created, and an
    object no longer on the battlefield, or back as a new object (CR 400.7),
    is skipped. CR 701.21a: "A player can't sacrifice ... something that's a
    permanent they don't control", so a sacrifice skips an object someone
    else controls now; exile (CR 701.13a) and a return to hand have no such
    restriction.
    """

    kind: Literal["act_on_each_subject"] = "act_on_each_subject"

    action: Literal["exile", "sacrifice", "destroy", "return_to_hand"]
    subjects: tuple[tuple[UUID, UUID], ...]

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        for subject_id, stamp in self.subjects:
            found = game.find_by_id(subject_id)
            if not isinstance(found, CardState) or found.zone is not Zone.BATTLEFIELD:
                continue
            if found.zone_change_stamp != stamp:
                continue
            if self.action == "sacrifice":
                if game.controller_of(found).username != trigger.controller:
                    continue
                game.sacrifice(found)
            elif self.action == "exile":
                game.exile_permanent(found)
            elif self.action == "destroy":
                game.destroy(found)
            else:
                game.return_to_hand(found)


class ReturnEachExiledToBattlefieldUnderOwner(DelayedEffectSpecBase):
    """ "Return those cards to the battlefield under their owner's control at
    the beginning of the next end step" - Elrond, Moon-Reader's activation
    and Eerie Interlude: one delayed triggered ability about every card its
    own instruction exiled, where `ReturnSubjectToBattlefieldUnderOwner` is
    about one.

    CR 603.7c is applied card by card (`subjects` pairs each id with the
    `zone_change_stamp` it had in exile): a card no longer in exile, or back
    as a new object (CR 400.7), is skipped. The rest return together, one
    event (CR 603.6a), each under its owner's control (CR 610.3c).
    """

    kind: Literal["return_each_exiled_to_battlefield_under_owner"] = (
        "return_each_exiled_to_battlefield_under_owner"
    )

    subjects: tuple[tuple[UUID, UUID], ...]

    #: ecl-T8: Morningtide's Light's own "return those cards to the
    #: battlefield tapped under their owners' control" - the multi-target
    #: twin of `ReturnSubjectToBattlefieldUnderOwner.tapped`.
    tapped: bool = False

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        found: list[CardState] = []
        for subject_id, stamp in self.subjects:
            card_state = game.find_by_id(subject_id)
            if not isinstance(card_state, CardState) or card_state.zone is not Zone.EXILE:
                continue
            if card_state.zone_change_stamp != stamp or card_state.owner is None:
                continue
            found.append(card_state)
        from .effects import _aura_host_for_entry

        # CR 303.4f: a returning Aura enchants what its owner chooses as it
        # enters, among what is already on the battlefield - never a card
        # returning alongside it, so every host is chosen before any enters.
        # With nothing legal it stays in exile (CR 303.4g).
        hosts: dict[UUID, object] = {}
        for card_state in found:
            assert card_state.owner is not None
            host = _aura_host_for_entry(
                game,
                card_state,
                card_state.owner,
                trigger.source_name,
                source_id_of(trigger.source_id),
            )
            if host is not None:
                hosts[card_state.id] = host
        with game.entering_together():
            for card_state in found:
                if card_state.id not in hosts:
                    continue
                assert card_state.owner is not None
                game.put_onto_battlefield(card_state, card_state.owner, tapped=self.tapped)
                host = hosts[card_state.id]
                if host is not True and card_state.zone is Zone.BATTLEFIELD:
                    card_state.attach_to(host)


class ReturnSubjectFromGraveyardToBattlefield(DelayedEffectSpecBase):
    """ "Return this card from your graveyard to the battlefield [tapped] at
    the beginning of the next end step" - Prized Amalgam's own delayed return
    of itself.

    CR 603.7c is the zone check: the card has to still be the same object in
    the graveyard (`expected_zone`/`expected_stamp`); one that was exiled, or
    that left and came back, is not returned. It returns under the delayed
    ability's controller - the player who controlled the ability that made it
    (CR 603.7e) and whose graveyard "your graveyard" names - and tapped when
    the clause says so.
    """

    kind: Literal["return_subject_from_graveyard_to_battlefield"] = (
        "return_subject_from_graveyard_to_battlefield"
    )

    tapped: bool = False

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        card = trigger.still_affects(game)
        if card is None:
            return
        game.put_onto_battlefield(card, trigger.controller, tapped=self.tapped)


class PutCountersOnSubject(DelayedEffectSpecBase):
    """ "Put two +1/+1 counters on it at the beginning of the next end step" -
    Protean Hydra's delayed payoff. The subject is the permanent the creating
    ability named ("it" - the ability's own source), and CR 603.7c is the
    zone check: a Hydra that died or left and came back since is not given the
    counters."""

    kind: Literal["put_counters_on_subject"] = "put_counters_on_subject"

    counter_kind: str
    amount: int

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        permanent = trigger.still_affects(game)
        if permanent is not None:
            game.add_counters(permanent, self.counter_kind, self.amount)


class ReturnSubjectFromGraveyardWithCounters(DelayedEffectSpecBase):
    """ "Return it to the battlefield with one fewer revival counter on it at
    the beginning of the next end step" - Nine-Lives Familiar's delayed
    return of the creature that died.

    `counters` is `(kind, amount)` already worked out when the creating
    ability resolved (the object's last-known counters, CR 603.10a, minus the
    "fewer"); a zero amount puts none. CR 603.7c's zone check keeps it from
    pulling a card that was exiled from the graveyard in the meantime, and it
    returns under its owner's control (CR 110.2a), tapped when the clause
    says so.
    """

    kind: Literal["return_subject_from_graveyard_with_counters"] = (
        "return_subject_from_graveyard_with_counters"
    )

    counters: tuple[tuple[str, int], ...] = ()
    tapped: bool = False

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        card = trigger.still_affects(game)
        if card is None or card.owner is None:
            return
        game.put_onto_battlefield(
            card,
            card.owner,
            tapped=self.tapped,
            counters={kind: amount for kind, amount in self.counters if amount > 0},
        )


#: What a delayed (or reflexive) triggered ability does when it resolves -
#: `DelayedTrigger.effect`'s own type. Every string this task's requirement 2
#: names (`"warp:exile"`, `"grant_extra_turn"`, `"sacrifice"`) is a member's
#: own `kind` tag, so those exact strings still validate - now into a real,
#: callable object rather than a `DELAYED_EFFECTS.get` lookup that could miss.
#: An unrecognised `kind` refuses at decode (`pydantic.ValidationError`)
#: instead of resolving to nothing; see this module's own docstring.
class ThatCreatureDiesConsequence(DelayedEffectSpecBase):
    """ "When that creature dies this turn, `<consequence>`." (End-Blaze
    Epiphany, Burn Away) - CR 603.7's delayed triggered ability, watching the
    one creature the creating spell named (`DelayedTrigger.subject_id`) and
    ending with the turn (CR 603.7b's stated duration). `trigger.text` is the
    consequence, read back at resolution by `machines/dies_this_turn.
    dies_consequence_effect` - its "its power"/"its controller" are CR
    603.10a's look back at the creature as it last existed, off the DIES
    event the ability carries."""

    kind: Literal["that_creature_dies_consequence"] = "that_creature_dies_consequence"
    source_stamp: UUID | None = None
    """The creating ability's source as it was then, for a consequence about
    "this creature" (Initiate of Blood's flip) - see `dies_consequence_effect`."""

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        from .dies_this_turn import dies_consequence_effect

        effect = dies_consequence_effect(trigger.text, source_stamp=self.source_stamp)
        if effect is not None:
            effect(game, ability)


#: "that much" / "that many" in a created ability's effect: the triggering
#: event's own amount (CR 603.2's event, `GameEvent.amount`), written in as a
#: digit before the effect is read when no reader takes the anaphor itself -
#: Arcbond's "it deals that much damage to each other creature and each
#: player" reads as the fixed-amount group damage it then is.
_THAT_MUCH_RE = re.compile(r"\bthat (?:much|many)\b", re.IGNORECASE)

#: "Whenever that <noun> <condition> this turn, <effect>" - a delayed
#: triggered ability (CR 603.7a) about one particular object (CR 603.7c), with
#: CR 603.7b's stated duration. `noun` is what the earlier text chose.
_THAT_OBJECT_TURN_TRIGGER_RE = re.compile(
    r"^whenever that (?P<noun>creature|permanent|planeswalker|artifact|land) "
    r"(?P<condition>[^,.]+?) this turn,\s*(?P<effect>[^\n]+?)\s*$",
    re.IGNORECASE,
)


def _chosen_object_trigger_effect(
    source_name: str, event: TriggerEvent, effect_text: str, amount: int | None
) -> "Callable[[Game, AbilityOnStack], None] | None":
    """The created ability's effect, read as a printed trigger's would be;
    when only the event's own amount makes it readable, read with that amount
    written in (`_THAT_MUCH_RE`). `amount` is `None` at parse time, where a
    sample amount only proves the text is readable."""
    from .effects import _is_notice_only, trigger_effect_for

    effect = trigger_effect_for(source_name, event, effect_text)
    if effect is not None and not _is_notice_only(effect):
        return effect
    if _THAT_MUCH_RE.search(effect_text) is None:
        return None
    carried = _THAT_MUCH_RE.sub(str(2 if amount is None else amount), effect_text)
    effect = trigger_effect_for(source_name, event, carried)
    if effect is None or _is_notice_only(effect):
        return None
    return effect


class ChosenObjectTriggeredAbility(DelayedEffectSpecBase):
    """ "Whenever that creature `<condition>` this turn, `<effect>`" - a
    delayed triggered ability (CR 603.7a) about the one object an earlier
    instruction chose (CR 603.7c): Hunter's Insight's "Choose target creature
    you control. Whenever that creature deals combat damage to a player or
    planeswalker this turn, draw that many cards", Arcbond's "... Whenever
    that creature is dealt damage this turn, it deals that much damage to
    each other creature and each player".

    `ability_text` is the sentence as the chosen object's own printed trigger
    ("Whenever this creature deals combat damage ..."), so the condition is
    matched by `machines/triggers.condition_matches` with the chosen object
    standing where "this creature" stands - not the creating spell, which is
    in a graveyard by then - and the effect is read by `trigger_effect_for`.
    `chosen_id`/`chosen_stamp` pin that object: one that left the battlefield
    and came back is a new object the ability never refers to (CR 400.7).

    The ability's source and controller stay the creating spell's (CR
    603.7d/e: "draw that many cards" is its controller's draw), but its "it"
    is the chosen object: the effect runs with that object as the acting
    source, as it last existed if the damage that triggered the ability
    killed it (CR 608.2h) - Arcbond's creature deals the damage, so its own
    lifelink and deathtouch apply (CR 120.3).
    """

    kind: Literal["chosen_object_triggered_ability"] = "chosen_object_triggered_ability"

    matches_against_the_game: ClassVar[bool] = True

    ability_text: str
    chosen_id: UUID
    chosen_stamp: UUID | None = None
    chosen_card: Card | None = None

    def parsed(self) -> TriggeredAbility | None:
        return _created_ability(self.ability_text)

    def printed_ability(self, trigger: "DelayedTrigger") -> TriggeredAbility | None:
        parsed = self.parsed()
        if parsed is None:
            return None
        return parsed.model_copy(
            update={"face": trigger.source_name, "text": trigger.text, "raw": trigger.text}
        )

    def _chosen_on_battlefield(self, game: "Game") -> CardState | None:
        found = game.find_by_id(self.chosen_id)
        if not isinstance(found, CardState) or found.zone is not Zone.BATTLEFIELD:
            return None
        if self.chosen_stamp is not None and found.zone_change_stamp != self.chosen_stamp:
            return None
        return found

    def event_matches(self, game: "Game", trigger: "DelayedTrigger", event: GameEvent) -> bool:
        from .triggers import condition_matches

        parsed = self.parsed()
        chosen = self._chosen_on_battlefield(game)
        if parsed is None or chosen is None:
            return False
        return condition_matches(game, parsed, chosen, trigger.controller, event)

    def __call__(self, game: "Game", ability: AbilityOnStack, trigger: "DelayedTrigger") -> None:
        parsed = self.parsed()
        if parsed is None or parsed.event is None:
            return
        amount = ability.event.amount if ability.event is not None else None
        effect = _chosen_object_trigger_effect(
            trigger.source_name, parsed.event, parsed.effect, amount
        )
        if effect is None:
            return
        found = game.find_by_id(self.chosen_id)
        last_known = found if isinstance(found, CardState) else None
        if last_known is None and self.chosen_card is not None:
            last_known = CardState(
                id=self.chosen_id,
                card=self.chosen_card,
                zone=Zone.GRAVEYARD,
                controller=trigger.controller,
                owner=trigger.controller,
            )
        acting = ability.model_copy(
            update={
                "source_id": self.chosen_id,
                "source_name": last_known.name if last_known is not None else ability.source_name,
                "source_last_known": last_known,
            }
        )
        effect(game, acting)


def chosen_object_turn_trigger_line(text: str) -> str | None:
    """ "Whenever that creature `<condition>` this turn, `<effect>`" as the
    chosen object's own printed trigger ("Whenever this creature
    `<condition>`, `<effect>`"), or `None` when `text` is not that shape or
    either half is not read: a condition `condition_matches` matches off a
    plain event (no intervening "if", CR 603.4) and an effect
    `trigger_effect_for` reads, directly or with the event's amount written
    in for its "that much"."""
    match = _THAT_OBJECT_TURN_TRIGGER_RE.fullmatch(collapsed(text.strip()))
    if match is None:
        return None
    effect_text = match.group("effect")
    line = f"Whenever this {match.group('noun').lower()} {match.group('condition')}, {effect_text}"
    parsed = _created_ability(line)
    if (
        parsed is None
        or parsed.event is None
        or parsed.intervening_if is not None
        or parsed.once_per_turn
    ):
        return None
    if _chosen_object_trigger_effect("", parsed.event, parsed.effect, None) is None:
        return None
    return line


def create_chosen_object_turn_trigger(
    game: "Game",
    line: str,
    chosen: CardState,
    *,
    text: str,
    controller: str,
    source_id: UUID | None,
    source_name: str,
) -> None:
    """CR 603.7a: resolving the instruction creates the ability, watching
    `chosen` for the rest of the turn (CR 603.7b: a stated duration fires on
    every matching event, and CR 514.2's cleanup ends it)."""
    parsed = _created_ability(line)
    if parsed is None or parsed.event is None:
        return
    game.create_delayed_trigger(
        DelayedTrigger(
            text=text,
            event=parsed.event,
            controller=controller,
            source_id=source_id,
            source_name=source_name,
            remaining=None,
            expires_end_of_turn=True,
            effect=ChosenObjectTriggeredAbility(
                ability_text=line,
                chosen_id=chosen.id,
                chosen_stamp=chosen.zone_change_stamp,
                chosen_card=chosen.card,
            ),
        )
    )


DelayedEffectSpec = Annotated[
    ExileWarped
    | GrantExtraTurn
    | SacrificeSubject
    | SacrificedByItsController
    | SacrificeEach
    | ExileSubjectAtNextEndStep
    | ReturnSubjectToBattlefieldUnderOwner
    | ReturnSubjectThenDiscardItsStat
    | ReturnSubjectToBattlefieldUnderController
    | ReturnSubjectToHand
    | ReboundRecast
    | ParadigmCopyAndCast
    | CipherCopyAndCast
    | CopyEpicSpell
    | DrawACardForController
    | UntapAllCreaturesForController
    | AddManaAmountForController
    | DamageEachOpponentPerCardStillExiled
    | AddManaInAnyCombinationForController
    | DestroySubject
    | TapSubject
    | TransformSubject
    | GainControlUntapHasteOfSubject
    | ReturnEarthbentLand
    | DevourerOfDestinyFirstUpkeep
    | StaticPrisonReturn
    | PhaseInEach
    | ReturnExiledCardAndAddCounters
    | CreateAttackingTokens
    | CreateTokensForController
    | CreateTokenCopyOfControlledToken
    | CreateTokenCopyOfLastKnown
    | PayOrLoseTheGame
    | CombatDamageToPlayerDraw
    | CopyNextSpellYouCast
    | SpellEntersWithAdditionalCounter
    | ReturnThatCardToBattlefieldUnderOwner
    | CopyNextSpellWithinManaValue
    | NextSpellCannotBeCountered
    | DelayedBlinkReturnWithRider
    | ReflexiveConsequence
    | DungeonRoomAbility
    | ReflexivePayEnergyConsequence
    | ReflexivePayManaConsequence
    | ReflexiveMayPayManaIfYouDo
    | ReflexiveMandatoryTokenDamageConsequence
    | ReflexiveCounterCountConsequence
    | ReflexiveAttachSubjectToTargetConsequence
    | ReflexiveReturnThenAttachToSubjectConsequence
    | ReflexiveDamageEqualToSubjectPowerConsequence
    | ReflexiveDamageEqualToSubjectManaValueConsequence
    | ReflexiveWhenYouDoConsequence
    | ReflexiveExileCopiedCard
    | ReflexivePreventedDamagePayoff
    | RevokeGrantedAbility
    | AddManaWhenLandTapped
    | PumpEventSubject
    | CountersAndKeywordsEventSubject
    | CreatedTriggeredAbility
    | ActOnEachSubject
    | ReturnSubjectFromGraveyardToBattlefield
    | ReturnEachExiledToBattlefieldUnderOwner
    | PayOrElseReturnExiledCard
    | DiscardCardsAtRandomForController
    | ThatCreatureDiesConsequence
    | ChosenObjectTriggeredAbility
    | CounterOnSubjectWhileSourceTapped
    | RemoveCountersFromLinkedCreature
    | PutCountersOnSubject
    | ReturnSubjectFromGraveyardWithCounters,
    Field(discriminator="kind"),
]

#: Singleton instances of every zero-argument member, kept under their old
#: pre-refactor names so every reference-by-name call site outside this file -
#: `models/game.py`'s dash and rebound triggers included - keeps working
#: unedited: passing `return_subject_to_hand` (the name) around used to hand
#: over a bare function; it now hands over this one frozen, serializable
#: instance instead, and calling it (`return_subject_to_hand(game, ability,
#: trigger)`) still works identically because `DelayedEffectSpecBase` defines
#: `__call__`.
exile_warped = ExileWarped()
grant_extra_turn = GrantExtraTurn()
sacrifice_subject = SacrificeSubject()
sacrificed_by_its_controller = SacrificedByItsController()
exile_subject_at_next_end_step = ExileSubjectAtNextEndStep()
return_subject_to_battlefield_under_owner = ReturnSubjectToBattlefieldUnderOwner()
return_subject_to_hand = ReturnSubjectToHand()
rebound_recast = ReboundRecast()
paradigm_copy_and_cast = ParadigmCopyAndCast()
copy_epic_spell = CopyEpicSpell()
draw_a_card_for_controller = DrawACardForController()
destroy_subject = DestroySubject()
tap_subject = TapSubject()
return_earthbent_land = ReturnEarthbentLand()
devourer_of_destiny_first_upkeep = DevourerOfDestinyFirstUpkeep()


class DelayedTrigger(EngineModel):
    """One delayed triggered ability, waiting for its event (CR 603.7)."""

    id: UUID = Field(default_factory=new_id)

    text: str
    """The ability as it would read on a card, for the stack listing and for a
    failure message. CR 603.7 says the word "when"/"whenever"/"at" is in there
    somewhere even though it does not usually begin the ability."""

    effect: DelayedEffectSpec
    """What this does when it resolves - see the module docstring and
    `DelayedEffectSpec` above."""

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

    any_main_phase: bool = False
    """Match either main phase (CR 505.1, `machines.turn.MAIN_PHASES`) rather
    than one fixed `step` - "at the beginning of your next main phase" (Mana
    Sculpt) means whichever of precombat or postcombat main comes first, not
    a printed choice between the two the way `step` names one exactly.
    `False` (the default) leaves `step` as the sole gate, unchanged for every
    delayed trigger that predates this."""

    controller: str
    """CR 603.7d/e: the controller of the spell or ability that created this, as
    it resolved."""

    source_id: UUID | None = None
    source_name: str
    """CR 603.7d/e again: the *creating* spell or ability's own source, not
    whatever the ability ends up affecting."""

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

    expires_end_of_next_turn: bool = False
    """CR 603.7b's own longer "stated duration" - Jace, Reality Sculptor's
    own `-3`, "Until your next turn, whenever a creature attacks you or a
    planeswalker you control, it gets -5/-0 until end of turn." - the
    delayed-trigger twin of `machines.layers.Duration.UNTIL_YOUR_NEXT_TURN`
    (CR 611.2a) and of `PlayPermission.expires_end_of_next_turn`. Unlike
    either of those two, a delayed trigger this stream ends outright rather
    than only marking: the stated duration ends the moment that turn would
    have begun, the same instant `Game.begin_turn_for` already reads for
    the other two, and there is no reason for a spent trigger to survive its
    own controller's next turn beginning - it has nothing left to watch
    for. `DelayedTriggers.expire_end_of_next_turn_for`, called from `Game.
    begin_turn_for` the same moment `ContinuousEffects.end_for_next_turn`
    and the `casting_rule_effects`/`play_permissions` sweeps already run,
    drops it there.

    `remaining=None` for a trigger carrying this, the same reason `expires_
    end_of_turn` needs it: the ability fires on every matching event for the
    rest of its stated duration, not once."""

    defending_controller_only: bool = False
    """"whenever a creature attacks you or a planeswalker you control" -
    CR 508.3d/CR 306.6's compound defender: an `ATTACKS` event's own
    `GameEvent.defender_controller` (resolved once, at emission, since this
    model has no `Game` to ask "who controls this id" of) must be this
    trigger's own `controller` for either half - a player defending
    themselves, or a planeswalker they control - to count. Not folded into
    `subject_id`: the subject of an `ATTACKS` event is the *attacking*
    creature (CR 508.3c), which this trigger does not know in advance,
    while the defender is what the trigger's own printed text names."""

    defending_opponent_only: bool = False
    """"whenever one or more creatures attack one of your opponents" -
    Garruk, Curse Breaker's own `-4`. The opposite half of `defending_
    controller_only`'s compound defender: an `ATTACKS` event's own
    `GameEvent.defender_controller` must be someone *other than* this
    trigger's own `controller` (CR 508.3a's "a player, planeswalker, or
    battle", restricted to an opponent) rather than equal to it. A `None`
    defender (an attack this delayed trigger somehow never learns a
    defender for) does not count as "an opponent" either."""

    forbidden_types: tuple[Type, ...] = ()
    """The types the watched event's own subject must *not* have - CR 205.2a's
    "a noncreature spell" (Summon: Good King Mog XII's own Saga chapters II
    and III: "Whenever you cast a noncreature spell this turn, ..."), the
    delayed-trigger twin of `machines/triggers._required_types`'s "forbidden"
    half, which the *ordinary*, printed form of "a noncreature spell" already
    reads off `GameEvent.subject_types` the same way. Empty matches any
    event regardless of type, the same as no clause naming a type at all."""

    required_any_types: tuple[Type, ...] = ()
    """The types the watched event's own subject must have *at least one*
    of - CR 300.1's own card types, `forbidden_types`' positive twin. Way of
    the Cryomancer's own granted "[-3]: When you next cast an instant or
    sorcery spell this turn, copy that spell." needs "instant or sorcery"
    read this way rather than as two sibling triggers, since CR 603.7a
    creates one delayed ability per printed sentence, not one per type
    named in it. Empty matches any event regardless of type, the same as
    `forbidden_types`' own empty default."""

    sibling_ids: tuple[UUID, ...] = ()
    """Other `DelayedTrigger`s created alongside this one that watch for a
    different event but the same underlying CR 603.7a ability - earthbend's
    "when that land dies **or** is put into exile" is one ability watching two
    events, represented as two `DelayedTrigger`s since each of those only
    watches one. Read by `ReturnEarthbentLand`/`StaticPrisonReturn`'s shared
    `_drop_sibling_triggers` to drop the sibling once either half fires, so a
    one-shot ability does not sit around forever after it has already done its
    job."""

    combat_only: bool = False
    """Match only a `TriggerEvent.DEALS_DAMAGE` event with `GameEvent.combat`
    true (CR 120.2a) - Lyra, Tolarian Archangel's own "Until end of turn,
    whenever Lyra deals **combat** damage to a player, draw two cards."
    Unlike the ordinary printed-ability `DEALS_DAMAGE` matcher in
    `machines/triggers.condition_matches`, `DelayedTrigger.matches` has no
    string condition to read "combat" off, so this is its own narrow filter
    field in the same spirit `subjectless_only`/`only_when_active` already
    are - one purpose-built flag per mechanic this model actually needs,
    not a general clause parser. `False` (the default) matches damage of
    either kind, which is every delayed trigger in the pool before this one."""

    to_player_only: bool = False
    """Match only a `TriggerEvent.DEALS_DAMAGE` event with a player as its
    target (`GameEvent.player is not None`) - the other half of Lyra's own
    "... deals combat damage **to a player** ...". `False` matches damage to
    a permanent too."""

    attacking_alone_only: bool = False
    """Match only an `ATTACKS` event with `GameEvent.attacking_alone` true
    (CR 506.5) - The Last Ronin's own Saga chapter III, "Whenever a creature
    you control attacks alone this turn, ...". The printed-ability matcher in
    `machines/triggers.condition_matches` reads "alone" off the ability's own
    condition string; `DelayedTrigger.matches` has no string to read it off
    (the same reason `combat_only`/`to_player_only` are their own narrow
    fields rather than a clause parser), so this is that one purpose-built
    flag. `False` (the default) matches any attack, which is every delayed
    trigger in the pool before this one."""

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
        if self.any_main_phase and event.step not in MAIN_PHASES:
            return False
        if self.subjectless_only and event.subject_id is not None:
            return False
        if (
            self.subject_id is not None
            and event.subject_id is not None
            and event.subject_id != self.subject_id
        ):
            return False
        if self.combat_only and not event.combat:
            return False
        if self.defending_controller_only and event.defender_controller != self.controller:
            return False
        if self.defending_opponent_only and (
            event.defender_controller is None or event.defender_controller == self.controller
        ):
            return False
        if self.to_player_only and event.player is None:
            return False
        if self.attacking_alone_only and not event.attacking_alone:
            return False
        if (
            self.forbidden_types
            and event.subject_types is not None
            and any(t in event.subject_types for t in self.forbidden_types)
        ):
            return False
        if self.required_any_types and (
            event.subject_types is None
            or not any(t in event.subject_types for t in self.required_any_types)
        ):
            return False
        return self.only_when_active is None or event.player == self.only_when_active

    def as_ability(self) -> TriggeredAbility:
        """The ability in the shape the rest of the engine handles triggers in.

        CR 603.7 puts the trigger word inside the ability rather than at its
        start, so `word` is recorded as the one the text actually carries and
        `condition` holds the delayed ability's own wait. A created ability
        that carries its own printed shape (`CreatedTriggeredAbility`) is
        handed over as that parse instead, so an effect parser reading the
        ability's condition or effect text sees the real split.
        """
        printed = self.effect.printed_ability(self)
        if printed is not None:
            return printed
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
#: module, so the dependency can only run one way.
ANAPHORIC_TIMING_STEPS: dict[str, Step] = {
    "the beginning of the next end step": Step.END_STEP,
    "the beginning of the next turn's upkeep": Step.UPKEEP,
    "the beginning of your next upkeep": Step.UPKEEP,
    "end of combat": Step.END_OF_COMBAT,
}

#: A step of the creating ability's controller's own turn (CR 500.1, CR 513.1: each
#: turn has one end step, and "your next end step" is the one of a turn that player
#: is the active player of). Read only here, by the anaphoric clause, which then
#: scopes its trigger to that player's turn (`DelayedTrigger.only_when_active`);
#: kept out of `ANAPHORIC_TIMING_STEPS`, whose other readers would drop the scope.
OWN_TURN_TIMING_STEPS: dict[str, Step] = {
    "the beginning of your next end step": Step.END_STEP,
}

_TIMING_PATTERN = "|".join(
    re.escape(phrase) for phrase in (*ANAPHORIC_TIMING_STEPS, *OWN_TURN_TIMING_STEPS)
)

#: "At <timing>, <instruction>." - Phelia, Exuberant Shepherd's word order.
_TIMING_LEADING_RE = re.compile(
    rf"^at (?P<timing>{_TIMING_PATTERN}),\s*(?P<instruction>.+)$", re.IGNORECASE
)
#: "... if it has mana value N or less" after the timing (Angrath, the Flame-Chained's
#: "Sacrifice it at the beginning of the next end step if it has mana value 3 or less").
_IF_MANA_VALUE_OR_LESS_RE = re.compile(
    r"\s+if (?:it|that creature) has mana value (?P<n>\d+) or less$", re.IGNORECASE
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
#:
#: Timing is CR 603.7c's business, not CR 613.5's: the referent is normally
#: already on the battlefield when this runs (Goryo's Vengeance returns it,
#: then names it in the same sentence), and CR 613.5 says the layer system's
#: answer is what the game asks about a permanent, "continually and
#: automatically" - a land earthbend (CR 701.66a) already made a creature "in
#: addition to its other types" (CR 205.1b) agrees with "that creature" even
#: though its printed type line still says only Land. `game` is the same
#: optional context every other call site in this defect class threads
#: through: `None` (no caller has been updated yet, or the referent is not on
#: the battlefield) falls back to the printed reading below, unchanged.
def _agreement_types(state: CardState, game: "Game | None") -> tuple[Type, ...]:
    if game is not None and state.zone is Zone.BATTLEFIELD:
        return game.characteristics_of(state).types
    return state.types


_ANAPHOR_AGREEMENT: dict[str, Callable[[CardState, "Game | None"], bool]] = {
    "it": lambda state, game: True,
    "that permanent": lambda state, game: bool(
        set(_agreement_types(state, game)) & PERMANENT_TYPES
    ),
    "that card": lambda state, game: not state.token,  # CR 108.2b
    "that token": lambda state, game: state.token,  # CR 111.1
    "the token": lambda state, game: state.token,  # CR 111.1
    "that creature": lambda state, game: Type.CREATURE in _agreement_types(state, game),
    "that creature token": lambda state, game: (
        state.token and Type.CREATURE in _agreement_types(state, game)
    ),
    "that artifact": lambda state, game: Type.ARTIFACT in _agreement_types(state, game),
    "that land": lambda state, game: Type.LAND in _agreement_types(state, game),
    "that enchantment": lambda state, game: Type.ENCHANTMENT in _agreement_types(state, game),
    # CR 201.5 / CR 700.7's self-reference: the ability's own source, which
    # the caller hands over as the subject. A card, never a token (CR 108.2b).
    "this card": lambda state, game: not state.token,
    # The plural pronouns - Lightning Coils' "Exile them", Mirror March's
    # "Those tokens gain haste. Exile them" - each checked object by object.
    "them": lambda state, game: True,
    "those tokens": lambda state, game: state.token,
    "the tokens": lambda state, game: state.token,
    "those creatures": lambda state, game: Type.CREATURE in _agreement_types(state, game),
}

#: The pronouns that name several objects at once: one delayed triggered
#: ability about all of them (`ActOnEachSubject`), not one per object.
_PLURAL_ANAPHORS = frozenset({"them", "those tokens", "the tokens", "those creatures"})

#: What `ActOnEachSubject` does for each verb a plural pronoun can take.
_PLURAL_ACTIONS: dict[str, Literal["exile", "sacrifice", "destroy", "return_to_hand"]] = {
    "exile": "exile",
    "sacrifice": "sacrifice",
    "destroy": "destroy",
    "return_to_hand": "return_to_hand",
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
    rf"^return (?P<anaphor>{_ANAPHOR_PATTERN}) (?P<from_graveyard>from your graveyard )?to "
    r"(?P<destination>its owner's hand|your hand|their owners' hands"
    r"|the battlefield under its owner's control|the battlefield)(?P<tapped> tapped)?$",
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
_ANAPHORIC_VERBS: dict[str, tuple[DelayedEffectSpecBase, Zone]] = {
    "exile": (exile_subject_at_next_end_step, Zone.BATTLEFIELD),
    "sacrifice": (sacrifice_subject, Zone.BATTLEFIELD),
    "destroy": (destroy_subject, Zone.BATTLEFIELD),
    "tap": (tap_subject, Zone.BATTLEFIELD),
    "return_to_hand": (return_subject_to_hand, Zone.BATTLEFIELD),
    "return_to_battlefield": (return_subject_to_battlefield_under_owner, Zone.EXILE),
    # Prized Amalgam's "return this card from your graveyard to the
    # battlefield tapped": the object waits in the graveyard, and CR 603.7c
    # checks it is still that same card there.
    "return_from_graveyard": (ReturnSubjectFromGraveyardToBattlefield(), Zone.GRAVEYARD),
    "return_from_graveyard_tapped": (
        ReturnSubjectFromGraveyardToBattlefield(tapped=True),
        Zone.GRAVEYARD,
    ),
}


class AnaphoricDelayedClause(EngineModel):
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

    max_mana_value: int | None = None
    """The "if it has mana value N or less" the clause ends with, for a sacrifice."""

    def agrees_with(self, subject: CardState, game: "Game | None" = None) -> bool:
        """Whether `subject` is the kind of object this clause's pronoun names.

        Checked at creation time only - CR 603.7c lets the object change
        characteristics afterwards and still be affected.

        `game`, when given, is what lets a type-word pronoun ("that creature",
        "that land", ...) read the computed board for a battlefield referent
        (CR 613.5) rather than only the printing (CR 613.1's starting point).
        `None` keeps the printed-only behaviour every caller had before this.
        """
        return _ANAPHOR_AGREEMENT[self.anaphor](subject, game)

    @property
    def expected_zone(self) -> Zone:
        """Where CR 603.7c will expect the object to be when this resolves."""
        return _ANAPHORIC_VERBS[self.verb][1]

    @property
    def own_turn_player(self) -> bool:
        """Whether the timing is "your next ..." - only the controller's own turn
        counts (`DelayedTrigger.only_when_active`)."""
        return any(phrase in self.text.lower() for phrase in OWN_TURN_TIMING_STEPS)

    @property
    def plural(self) -> bool:
        """Whether the pronoun names several objects ("them", "those
        tokens") - one ability about all of them, `ActOnEachSubject`."""
        return self.anaphor in _PLURAL_ANAPHORS

    @property
    def self_referential(self) -> bool:
        """Whether the pronoun is the ability's own source ("this card")
        rather than something an earlier sentence produced."""
        return self.anaphor == "this card"

    def triggers_for_all(
        self,
        subjects: "list[CardState]",
        *,
        controller: str,
        source_id: UUID | None,
        source_name: str,
        game: "Game | None" = None,
    ) -> list[DelayedTrigger] | None:
        """The delayed triggered ability(ies) this clause creates about every
        object in `subjects` - the objects the paragraph's earlier sentence
        just produced.

        A plural pronoun makes **one** ability about all of them (CR 603.7a:
        the paragraph creates one delayed triggered ability, however many
        objects it names). A singular pronoun names exactly one object, so
        more than one subject is a mismatch and fails closed (`None`), the
        same as a pronoun that does not agree. No subjects at all is an empty
        list: nothing was produced, so nothing is created (CR 101.3).
        """
        if not subjects:
            return []
        if not all(self.agrees_with(subject, game) for subject in subjects):
            return None
        if self.plural:
            return [
                DelayedTrigger(
                    text=self.text,
                    event=TriggerEvent.BEGINNING_OF_STEP,
                    step=self.step,
                    controller=controller,
                    source_id=source_id,
                    source_name=source_name,
                    only_when_active=controller if self.own_turn_player else None,
                    effect=ActOnEachSubject(
                        action=_PLURAL_ACTIONS[self.verb],
                        subjects=tuple(
                            (subject.id, subject.zone_change_stamp) for subject in subjects
                        ),
                    ),
                )
            ]
        if len(subjects) != 1:
            return None
        single = self.trigger_for(
            subjects[0],
            controller=controller,
            source_id=source_id,
            source_name=source_name,
            game=game,
        )
        return None if single is None else [single]

    @property
    def effect(self) -> DelayedEffectSpecBase:
        """What this does when it resolves."""
        if self.max_mana_value is not None:
            return SacrificeSubject(max_mana_value=self.max_mana_value)
        return _ANAPHORIC_VERBS[self.verb][0]

    def trigger_for(
        self,
        subject: CardState,
        *,
        controller: str,
        source_id: UUID | None,
        source_name: str,
        game: "Game | None" = None,
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

        `game`, when given, is forwarded to `agrees_with` so a battlefield
        referent's *computed* characteristics decide agreement (CR 613.5).
        """
        if self.plural or not self.agrees_with(subject, game):
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
            only_when_active=controller if self.own_turn_player else None,
            effect=self.effect,
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
    text = clause
    limited = _IF_MANA_VALUE_OR_LESS_RE.search(clause)
    if limited is not None:
        clause = clause[: limited.start()]
    match = _TIMING_LEADING_RE.fullmatch(clause) or _TIMING_TRAILING_RE.fullmatch(clause)
    if match is None:
        return None
    timing = match.group("timing").lower()
    step = ANAPHORIC_TIMING_STEPS.get(timing) or OWN_TURN_TIMING_STEPS.get(timing)
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
        destination = returning.group("destination").lower()
        from_graveyard = returning.group("from_graveyard") is not None
        tapped = returning.group("tapped") is not None
        if destination in ("its owner's hand", "your hand", "their owners' hands"):
            if from_graveyard or tapped:
                return None
            verb = "return_to_hand"
        elif destination == "the battlefield":
            # Only the graveyard return names no controller: CR 603.7e's
            # controller of the delayed ability is who "your graveyard" is.
            if not from_graveyard:
                return None
            verb = "return_from_graveyard_tapped" if tapped else "return_from_graveyard"
        else:
            if from_graveyard or tapped:
                return None
            verb = "return_to_battlefield"

    if anaphor in _PLURAL_ANAPHORS and verb not in _PLURAL_ACTIONS:
        return None
    max_mana_value = None
    if limited is not None:
        # Only a singular sacrifice carries the condition (CR 603.4): any other verb or a
        # plural pronoun would silently drop it, so the clause is refused instead.
        if verb != "sacrifice" or anaphor in _PLURAL_ANAPHORS:
            return None
        max_mana_value = int(limited.group("n"))
    return AnaphoricDelayedClause(
        text=text, step=step, anaphor=anaphor, verb=verb, max_mana_value=max_mana_value
    )


def anaphoric_delayed_trigger(
    clause: str,
    *,
    subject: CardState,
    controller: str,
    source_id: UUID | None,
    source_name: str,
    game: "Game | None" = None,
) -> DelayedTrigger | None:
    """`parse_anaphoric_delayed_clause` and `trigger_for` in one call - the
    whole primitive, for a caller that has just moved or created `subject` and
    has the clause that talks about it.

    The result is not registered anywhere: CR 603.7a's creation is
    `Game.create_delayed_trigger`, which the caller does once it is satisfied
    the rest of its paragraph succeeded.

    `game`, when the caller has one, is forwarded to `trigger_for` so
    agreement reads `subject`'s computed characteristics on the battlefield
    (CR 613.5) rather than only its printed type line. `None` (the default)
    keeps every existing caller's behaviour unchanged.
    """
    parsed = parse_anaphoric_delayed_clause(clause)
    if parsed is None:
        return None
    trigger = parsed.trigger_for(
        subject,
        controller=controller,
        source_id=source_id,
        source_name=source_name,
        game=game,
    )
    if trigger is None:
        return None
    # The stack listing should read as the card does, full stop and all; the
    # parse strips it only to match.
    return trigger.model_copy(update={"text": clause.strip()})


class DelayedTriggers(EngineModel):
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
    still has to resolve afterwards - and, for a reflexive ability
    (`create_reflexive`), because it is never in `triggers` to begin with. Both
    halves are ordinary `DelayedTrigger`s with a real `effect:
    DelayedEffectSpec`, so both round-trip through `model_dump` the same way.
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
        callback: DelayedEffectSpec,
        subject_id: UUID | None = None,
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

        `callback` keeps its pre-refactor name and its `DelayedEffect`
        (`Callable`) type, rather than being renamed to `effect: DelayedEffect
        Spec`, purely so `Game.create_reflexive_trigger` - `models/game.py`,
        off limits to this task - keeps forwarding its own `callback` keyword
        through unedited. Every real caller (`machines/effects.py`, `machines/
        replacement.py`) already passes a genuine `DelayedEffectSpecBase`
        instance, which satisfies `DelayedEffect`'s `Callable` shape
        structurally; it is used below exactly the way `effect=` is used
        everywhere else.

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
            subject_id=subject_id,
            effect=callback,
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

    def fire(self, event: GameEvent, game: "Game | None" = None) -> list[AbilityOnStack]:
        """Everything this event triggers, in creation order (CR 603.2, 603.7b).

        CR 603.7b: "A delayed triggered ability will trigger only once - the next
        time its trigger event occurs - unless it has a stated duration", so a
        trigger with a count spends one and a spent trigger is dropped.

        `game` lets a trigger whose condition needs the board
        (`DelayedEffectSpecBase.event_matches`) ask it; without one such a
        trigger never fires, the safe direction to be wrong in.
        """
        fired: list[AbilityOnStack] = []
        for trigger in list(self.triggers):
            if not trigger.matches(event):
                continue
            if game is None:
                if trigger.effect.matches_against_the_game:
                    continue
            elif not trigger.effect.event_matches(game, trigger, event):
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

    def expire_end_of_next_turn_for(self, username: str) -> list[DelayedTrigger]:
        """CR 603.7b's stated duration: end every `username`-owned "until
        your next turn" delayed trigger the moment `username`'s next turn
        would begin.

        `Game.begin_turn_for` calls this at the identical instant it already
        ends `Duration.UNTIL_YOUR_NEXT_TURN` continuous effects
        (`ContinuousEffects.end_for_next_turn`) and marks `expires_end_of_
        next_turn` play permissions for this same player - the three
        `UNTIL_YOUR_NEXT_TURN`-shaped stores this engine carries, ended the
        same way for the same reason. Scoped to `controller`, not every
        trigger with the flag set: two players' own "until your next turn"
        grants end on two different turns.
        """
        ending = [
            trigger
            for trigger in self.triggers
            if trigger.expires_end_of_next_turn and trigger.controller == username
        ]
        ending_ids = {trigger.id for trigger in ending}
        self.triggers = [trigger for trigger in self.triggers if trigger.id not in ending_ids]
        return ending

    def trigger_for(self, ability: AbilityOnStack) -> DelayedTrigger | None:
        """The delayed ability an object on the stack came from, if it came from one."""
        return self.pending.get(ability.id)

    def effect_for(self, ability: AbilityOnStack) -> DelayedEffectSpecBase | None:
        """What this ability does, or None if it is not one of ours.

        Used to key off `DelayedTrigger.callback` first and fall back to
        `DELAYED_EFFECTS.get(trigger.effect)` for the string-keyed entries
        that predated it - both gone now that `effect` is always a real
        `DelayedEffectSpec`, so this reduces to the one line CR 603.7 always
        actually needed.
        """
        trigger = self.pending.get(ability.id)
        if trigger is None:
            return None
        return trigger.effect

    def discard(self, ability: AbilityOnStack) -> None:
        """Forget an ability that has finished resolving (CR 608.2n)."""
        self.pending.pop(ability.id, None)


# --------------------------------------------------------------------------
# R0a-T5: "Exile this creature. Return it to the battlefield under its
# owner's/your control at the beginning of the next end step." (CR 603.7a)
# --------------------------------------------------------------------------

#: The activated self-flicker - Fleeting Spirit, Aetherling, Argent Sphinx.
_SELF_FLICKER_AT_NEXT_END_STEP_RE = re.compile(
    r"^exile (?:this (?:creature|permanent|artifact|enchantment)|it)\. return (?:it|that card) "
    r"to the battlefield(?P<tapped> tapped)? under (?P<whose>its owner's|your) control at "
    r"the beginning of the next end step\.?$",
    re.IGNORECASE,
)


def parse_self_flicker_at_next_end_step_clause(text: str) -> "Callable[..., None] | None":
    """`_SELF_FLICKER_AT_NEXT_END_STEP_RE`'s effect: the ability's source is
    exiled, and a delayed trigger (CR 603.7a) returns that exiled object at
    the beginning of the next end step - not if it has moved on (CR 603.7c)."""
    match = _SELF_FLICKER_AT_NEXT_END_STEP_RE.fullmatch(collapsed(text))
    if match is None:
        return None
    tapped = match.group("tapped") is not None
    under_owner = match.group("whose").lower() == "its owner's"
    return_text = text.split(". ", 1)[1].strip()

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        from ..machines import Step
        from ..models.zone import Zone
        from .abilities import TriggerEvent

        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        game.exile_permanent(source)
        if source.zone is not Zone.EXILE:
            return
        spec: ReturnSubjectToBattlefieldUnderOwner | ReturnSubjectToBattlefieldUnderController = (
            ReturnSubjectToBattlefieldUnderOwner(tapped=tapped)
            if under_owner
            else ReturnSubjectToBattlefieldUnderController()
        )
        game.create_delayed_trigger(
            DelayedTrigger(
                text=return_text,
                event=TriggerEvent.BEGINNING_OF_STEP,
                step=Step.END_STEP,
                controller=ability.controller,
                source_id=ability.source_id,
                source_name=ability.source_name,
                subject_id=source.id,
                expected_zone=Zone.EXILE,
                expected_stamp=source.zone_change_stamp,
                effect=spec,
            )
        )

    return effect
