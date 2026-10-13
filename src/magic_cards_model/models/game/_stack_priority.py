import re
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Literal
from uuid import UUID

from ...ids import new_id
from ...machines.abilities import (
    ActivatedAbility,
    TriggeredAbility,
    TriggerEvent,
    parse_abilities,
    parse_triggered_mana,
    self_normalized_effect_text,
)
from ...machines.blitz import create_blitz_delayed_trigger
from ...machines.casting import (
    _OPTIONAL_ADDITIONAL_COST,
    grant_suspend_haste,
    has_quality,
    hexproof_abilities_in,
    or_additional_cost_alternatives,
    with_keyword_spell_ability_target,
)
from ...machines.casting_restrictions import (
    cannot_be_copied,
    cannot_be_countered,
    conditionally_cannot_be_countered,
    spell_protected_from_countering,
)
from ...machines.combat import (
    has_keyword,
)
from ...machines.cost import (
    additional_cost_phrases,
    cost_announces_x,
    total_cost_for_phrase,
)
from ...machines.counter_effects import event_count_target_text
from ...machines.decisions import (
    Decision,
    DecisionKind,
    PendingDecision,
)
from ...machines.delayed import (
    DelayedEffectSpecBase,
    DelayedTrigger,
    ExileWarped,
    return_subject_to_hand,
)
from ...machines.effects import (
    UnmodeledTriggerEffectNotice,
    activated_effect_for,
    apply_gift_if_promised,
    effect_for,
    effect_text_with_named_token_reminder,
    link_cards_exiled_during,
    modal_trigger_profile,
    trigger_effect_for,
)
from ...machines.keywords import (
    ascend_as_a_spell_resolves,
    awaken_as_the_spell_resolves,
    awaken_target_held_apart,
    keyword_effect_for,
    keyword_triggered_abilities,
)
from ...machines.layers import (
    Characteristics,
)
from ...machines.modes import (
    modal_profile,
    substitute_x,
)
from ...machines.monarch import monarch_effect_for
from ...machines.next_spell import (
    next_spell_keyword_grants_for,
    spell_has_quality,
)
from ...machines.priority import PriorityOutcome
from ...machines.replacement import (
    EventKind,
    ReplaceableEvent,
    apply_replacements,
)
from ...machines.targeting import (
    RetargetScope,
    TargetingProfile,
    TargetRequirement,
    announce_trigger_division,
    face_spell_profile,
    kicked_instead_target_text,
    per_kick_target_text,
    profile_for_modes,
    profile_for_modes_with_owners,
    profile_for_text,
    reflexive_consequence_text,
    spell_profile_for_text,
    targeting_profile,
)
from ...machines.teamwork import teamwork_instead_target_text
from ...machines.triggers import (
    AbilityOnStack,
    ExtraTriggerEvent,
    GameEvent,
    TargetingNotice,
    TargetingNoticeKind,
    apnap_order,
    intervening_if_holds,
    mana_added_event,
    resolution_key,
    state_triggers_for,
)
from ...machines.turn import (
    Step,
)
from ..action import Action
from ..card import (
    Card,
    Color,
    Layout,
    Supertype,
)
from ..card_state import (
    CardState,
    ChoiceKind,
    TargetRef,
)
from ..mana import ManaCost
from ..player import Player
from ..token import (
    TokenState,
    move_refused,
)
from ..zone import Zone
from ._common import StackObject, Targetable
from .records import CastRecord

if TYPE_CHECKING:
    from . import Game


#: "You have protection from the chosen card name" - Runed Halo's second line,
#: and the only shape in the pool that grants protection to a *player*. The
#: quality is the CR 614.12a name chosen as the permanent entered, which
#: `machines/replacement.py` stores on `CardState.choice`.
_PLAYER_PROTECTION_FROM_CHOSEN_NAME = re.compile(
    r"^you have protection from the chosen card name\b", re.IGNORECASE
)


def protection_qualities(card: Card) -> list[str]:
    """Every quality this printing has protection from, in printed order (CR 702.16a).

    Read straight off the oracle text, which is how every other keyword in this
    engine is read: Scryfall's `keywords` field says only "Protection", never
    from what. CR 702.16g's "protection from [A] and from [B]" is two separate
    protection abilities, so the phrase is split on "and from".

    This is the printing's own protection only. A permanent can also have
    protection *granted* to it by another static ability (Akroma's Memorial's
    "creatures you control have ... protection from black and from red") -
    `Game._effective_protection_qualities` is the one that reads both.
    """
    text = card.oracle_text
    if text is None and card.card_faces:
        # A flip or transform card prints its text per face (Tok-Tok's
        # "Protection from red" sits on the flipped half).
        text = "\n".join(face.oracle_text or "" for face in card.card_faces)
    return _qualities_from_text(text)


def protection_quality_readable(quality: str) -> bool:
    """Whether the engine's protection readers (`Game.source_has_quality`,
    `Game.source_has_quality_of_card`, `Game._player_quality_protects`) can
    tell if a source has `quality` at all. A quality none of them reads is
    never enforced - the support oracle scores such a Protection keyword a
    notice rather than crediting it on presence."""
    wanted = quality.strip().lower()
    return (
        wanted == "everything"
        or _is_spell_quality(wanted)
        or _card_type_named(wanted) is not None
        or wanted in _COLOR_WORDS
        or wanted in _COLOR_COUNT_QUALITIES
        or _EACH_OPPONENT_PROTECTION_QUALITY.match(quality.strip()) is not None
        or _CAST_THIS_TURN_QUALITY_RE.match(quality.strip()) is not None
        or _spell_colour_quality(quality) is not None
        or _characteristic_quality(quality) is not None
    )


def _illegal_option_refusal(decision: Decision) -> str:
    """The refusal for choosing an option CR 608.2d rules out, in its words."""
    refusal = (
        f"{decision.prompt}: that option is illegal, so CR 608.2d does not allow choosing "
        "it (\"The player can't choose an option that's illegal or impossible\")"
    )
    if decision.kind is DecisionKind.PAY_MANA:
        refusal += (
            " - the floating mana and the untapped mana sources available cannot pay it "
            "(CR 118.3: \"A player can't pay a cost without having the necessary "
            'resources to pay it fully")'
        )
    return refusal


#: "target (player|opponent)" ahead of "that player controls" - then "that
#: player" is that target, not whoever the trigger event named.
_TARGET_PLAYER_BEFORE_THAT_PLAYER_RE = re.compile(r"\btarget (?:player|opponent)\b", re.IGNORECASE)

#: The phrases that bind "that player" to the trigger event's own player
#: (`GameEvent.player`) rather than leaving `ControllerRestriction.EVENT_
#: PLAYER`/its zone-clause twin unbound - "that player controls" for a
#: permanent (CR 508.5-style "that player"), and "that player's graveyard"
#: (or another zone) for a card, Shark Shredder, Killer Clone's own combat-
#: damage trigger: "put up to one target creature card from that player's
#: graveyard onto the battlefield under your control." Both are searched for
#: in printed order and the earliest one found is what "target player"/
#: "target opponent" is checked against below - a card could in principle
#: print either first.
_THAT_PLAYER_BINDING_RE = re.compile(
    r"that player controls|that player'?s (?:graveyards?|hands?|libraries?|library|exile)",
    re.IGNORECASE,
)


def _costs_carry_x(source: CardState) -> bool:
    """Whether a cost of the spell `source` was printed with an {X} - its mana
    cost, or a kicker cost (CR 107.3a: X in an additional cost)."""
    if "{X}" in (source.mana_cost or ""):
        return True
    from ...machines.casting import kicker_costs

    return any("{X}" in cost for cost in kicker_costs(source.card))


def _that_player_of(ability: "AbilityOnStack") -> str | None:
    """Who a triggered ability's "... that player controls"/"... that
    player's `<zone>`" names: the player its trigger event names
    (`GameEvent.player` - the player dealt the damage for "deals combat
    damage to a player"), bound into the targeting restriction by
    `TargetingProfile.for_event_player`.

    `None` - the restriction left unbound, exactly as it read before - when
    there is no event or it names nobody, when the text has neither phrase at
    all, and when a "target player"/"target opponent" comes first, since
    "that player" is then that target rather than the event's.
    """
    event = ability.event
    if event is None or event.player is None:
        return None
    text = ability.ability.text or ""
    match = _THAT_PLAYER_BINDING_RE.search(text)
    if match is None or _TARGET_PLAYER_BEFORE_THAT_PLAYER_RE.search(text[: match.start()]):
        return None
    return event.player


class StackPriorityMixin:
    @property
    def stack(self: "Game") -> list[StackObject]:
        """The stack, top last. Holds spells (cards) and abilities (CR 405.1)."""
        return self.shared_zones[Zone.STACK]

    @property
    def spells_on_stack(self: "Game") -> list[CardState]:
        """Just the spells: a card on the stack is a spell, an ability is not (CR 112.1)."""
        return [item for item in self.stack if isinstance(item, CardState)]

    @property
    def abilities_on_stack(self: "Game") -> list[AbilityOnStack]:
        return [item for item in self.stack if isinstance(item, AbilityOnStack)]

    @property
    def stack_is_empty(self: "Game") -> bool:
        return not self.stack

    def _resolve_declaration(
        self: "Game",
        pairs: "list[tuple[CardState | UUID, CardState | Player | TargetRef | UUID | str]]",
    ) -> list[tuple[CardState, "CardState | Player | TargetRef | str"]]:
        """Turn one `ask_attackers`/`ask_blockers` answer's pairs into the
        `CardState`/`Player`/`str` objects `declare_attackers`/
        `declare_blockers` expect.

        A scripted or defaulted answer already names real objects - every
        scenario in `tests/scenarios/` stages `(CardState, Targetable | str)`
        pairs directly (see `_ask_declaration`), where `Targetable` is
        `CardState | Player` - and passes through here unchanged, `Player`
        included. A recorded `Answer.pairs` entry (a tape of `DeclaredPair`,
        see `machines/decisions.py`) names cards by id instead, because a
        `DeclaredPair` cannot hold a live `CardState` reference; those ids are
        resolved here, against the board as it stands right now.
        `_ask_declaration` already turns a `DeclaredPair`'s `defender_player`
        into the plain username `str` this method's passthrough branch
        already handles, so a recorded attack on a player reaches this method
        exactly the way a scripted one does.

        An id naming nothing in any zone this game can see is refused rather
        than dropped or silently skipped (CR 508.1a's/CR 509.1a's declaration
        is the whole creature or defender named, not whichever of it can be
        found) - see `memory/silent-default-dispatch-tables.md`.
        """
        resolved: list[tuple[CardState, CardState | Player | TargetRef | str]] = []
        for creature, target in pairs:
            creature_state = (
                creature if isinstance(creature, CardState) else self.find_by_id(creature)
            )
            if creature_state is None:
                raise ValueError(f"declaration names {creature!r}, not a card in any zone")
            if isinstance(target, CardState | Player | TargetRef | str):
                resolved.append((creature_state, target))
                continue
            target_state = self.find_by_id(target)
            if target_state is None:
                raise ValueError(
                    f"declaration names {target!r} as a defender, but no such card exists "
                    f"in any zone"
                )
            resolved.append((creature_state, target_state))
        return resolved

    def put_on_stack(self: "Game", card_state: CardState, controller: str) -> CardState:
        """Put a spell onto the stack. The stack's last entry is its top.

        Refused for a token that has left the battlefield (CR 111.8). A token is
        not a card and can never be cast (CR 111.6), so this only ever matters
        for an effect that would move one onto the stack.
        """
        if move_refused(card_state, Zone.STACK) is not None:
            return card_state
        with self._id_allocator_scope():
            return self._put_on_stack(card_state, controller)

    def _put_on_stack(self: "Game", card_state: CardState, controller: str) -> CardState:
        """The rest of `put_on_stack`, run with `_allocate_id` installed - see
        `objects_created`'s own docstring for why that installation is scoped
        to this one call rather than done once for the object's whole life."""
        # CR 400.7: the card is about to become a new object on the stack, so
        # its origin has to be read *now* - `GameEvent.origin_zone` is what
        # Knowledge Pool's "from their hand" and Appa, Steadfast Guardian's
        # "from exile" restrict a CAST_SPELL trigger to (`machines/triggers.
        # _origin_zone_matches`).
        #
        # `card_state.zone` is *not* reliably that answer any more by the
        # time this method runs: `machines/casting.Casting._move_to_the_
        # stack` moves the card onto `game.stack` itself, at CR 601.2a's own
        # "first step" of the announcement, well before `Casting.cast()`
        # calls this method - so for a spell cast the ordinary way,
        # `card_state.zone` already reads `Zone.STACK` here, which is not an
        # origin at all. `Casting.cast()` calls `Game.note_cast` with the
        # real origin before it ever reaches this method (see that method's
        # own `self.origin_zone`), so the `CastRecord` it just wrote is
        # consulted first; `cast_during_resolution` is the one other caller,
        # ordered the same way for the same reason (its own docstring), so
        # its record is there too. `card_state.zone` is the fallback for a
        # spell that reaches here with no record at all - there is no such
        # path in this engine today, but reading a zone that has not been
        # moved yet is still the right default if one is ever added.
        record = self.cast_record_of(card_state)
        origin_zone = record.origin_zone if record is not None else card_state.zone
        # Exile and the command zone are modelled as shared, not per-player
        # (`shared_zones`, not `owner.zones`) - a card foretold, plotted, or
        # exiled by an Adventure sits there, and was left behind (duplicated
        # onto the stack) when only the player's own zones were searched.
        self._take_out_of_every_zone(card_state)

        card_state.controller = controller
        stamp_before = card_state.zone_change_stamp
        # CR 712.11a: a spell announced transformed is already on the stack
        # back face up, and stays that way.
        cast_transformed = card_state.zone is Zone.STACK and card_state.transformed
        card_state.move_to(Zone.STACK)
        card_state.transformed = cast_transformed
        self._carry_cast_record(card_state, stamp_before)
        if card_state not in self.stack:
            self.stack.append(card_state)
        self.spells_cast_this_turn.setdefault(controller, []).append(card_state)
        if origin_zone is Zone.HAND:
            self.record_turn_fact("cast_spell_from_hand", controller)
        # CR 700.13: casting a spell that targets an opponent or what they
        # control is a crime, committed as the spell becomes cast.
        from ...machines.conditions import history as condition_history

        condition_history.record_crime(self, controller, card_state.targets)

        if card_state.prepare_spell_face:
            # CR 601.2i: "That permanent loses the prepared designation at
            # the time the spell becomes cast" (CR 722.3c) - this is that
            # instant, now that CR 601.2a's move above has actually happened.
            # `id` survives the zone move (CR 400.7's own exception for this
            # engine - see `CardState.move_to`), so the permanent that minted
            # this exact copy is still found by it. `become_unprepared`'s own
            # "remove the copy from exile" half is a no-op here: this copy
            # has already left `self.exile` for the stack.
            source = next(
                (
                    permanent
                    for permanent in self.battlefield
                    if permanent.prepared_copy_id == card_state.id
                ),
                None,
            )
            if source is not None:
                self.become_unprepared(source)

        # CR 601.2a: the card is now a spell on the stack, so the casting event
        # has happened and anything watching for it triggers (CR 603.2).
        # CR 202.3e: while this spell is on the stack, an {X} in its cost is
        # the value actually chosen for X, not CR 107.3g's off-stack "X is 0"
        # reading `card_state.card.cmc` gives - `Game.note_cast` (called by
        # `Casting.cast` before this) already has that value on record, the
        # same one CR 107.3m's own X-counters replacement in
        # `machines/replacement.py` reads. Chalice of the Void's "mana value
        # equal to the number of charge counters" needs this real number, not
        # the printed one - see `GameEvent.amount`'s docstring.
        # CR 107.3i: "all instances of X on an object have the same value at
        # any given time" - Walking Ballista's `{X}{X}` is two symbols each
        # worth the one chosen X, so the printed cmc (which already reads
        # both as 0, CR 107.3g) gains `count * x_value`, not just `x_value`.
        mana_value = card_state.card.cmc or 0
        x_count = (card_state.mana_cost or "").count("{X}")
        if x_count:
            mana_value += x_count * self.cast_record(card_state).x_value
        # CR 601.2i: this is "the next <quality> spell you cast this turn" -
        # the permission is used up by it, taken or not.
        self.next_spell_free_cast_grants = [
            grant
            for grant in self.next_spell_free_cast_grants
            if not (grant.controller == controller and spell_has_quality(card_state, grant.quality))
        ]
        # CR 601.2i again: "the next `<quality>` spell you cast this turn has
        # `<keyword>`" - every such grant this spell answers for is used up
        # by it (two Don & Raph triggers both applied to this one spell).
        used = next_spell_keyword_grants_for(self, card_state, controller)
        if used:
            self.next_spell_keyword_grants = [
                grant for grant in self.next_spell_keyword_grants if grant not in used
            ]
        self.emit(
            GameEvent(
                event=TriggerEvent.CAST_SPELL,
                subject_id=card_state.id,
                subject_name=card_state.name,
                subject_controller=controller,
                subject_card=card_state.card,
                subject_stamp=card_state.zone_change_stamp,
                subject_types=card_state.types,
                subject_subtypes=card_state.subtypes,
                subject_colors=card_state.colors,
                player=controller,
                amount=int(mana_value),
                origin_zone=origin_zone,
                origin_exile_annotation=record.exile_annotation if record is not None else None,
            )
        )
        # CR 117.3c gives priority straight back to the caster, so this is the
        # "next time a player would receive priority" of CR 603.3 - a cast
        # trigger goes on the stack above the spell that caused it.
        self.put_triggers_on_stack()
        return card_state

    def resolve_top(self: "Game") -> StackObject:
        """Resolve the top of the stack, recording what is resolving (CR 608.2).

        The object is popped off the stack before its effect runs, so nothing
        downstream could otherwise answer "which object is resolving right
        now?" - and CR 724.1b needs exactly that: "Exile every object on the
        stack, **including the object that's resolving**." `Game.resolving` is
        that answer, live only for the length of one resolution.
        """
        # CR 608.2: one resolution is one batch for CR 603.10a's look-back.
        self._departure_epoch += 1
        self._refuse_if_over()
        if self.stack_is_empty:
            raise ValueError("the stack is empty")
        self.resolving = self.stack[-1]
        self._forget_counts()
        try:
            with self._id_allocator_scope():
                return self._resolve_top()
        finally:
            self.resolving = None
            self._forget_counts()

    def _resolve_top(self: "Game") -> StackObject:
        """Resolve the top of the stack (CR 608).

        A spell's effect happens, then permanents land on the battlefield and
        everything else goes to its controller's graveyard. An ability resolves
        through `_resolve_ability` instead, because CR 608.2n removes it from the
        stack rather than putting it anywhere.

        An Aura is a permanent spell too, but CR 608.3c gives it one more step
        than "enters the battlefield": it enters *attached* to whatever it was
        targeting, so `_aura_attachment` re-resolves that target and
        `enter_the_battlefield` is asked to attach it in the same event, not
        afterwards - see both docstrings.

        State-based actions are checked afterwards and anything that triggered is
        put on the stack, since both happen before any player next receives
        priority (CR 704.3, 603.3).
        """
        if self.stack_is_empty:
            raise ValueError("the stack is empty")

        top = self.stack.pop()
        if isinstance(top, AbilityOnStack):
            return self._resolve_ability(top)

        spell = top
        # CR 702.140b/c: a mutating creature spell checks its own target as
        # it begins resolving - merged when legal, otherwise a plain creature
        # spell with that target dropped, so never a CR 608.2b fizzle.
        from ...machines.face_down_keywords import resolve_mutating_spell

        if isinstance(spell, CardState) and resolve_mutating_spell(self, spell):
            self.forget_cast_record(spell)
            self._before_priority()
            return spell
        if self.spell_fizzles(spell):
            # CR 608.2b: it does not resolve. None of its effects happen, not
            # even the untargeted ones, and it is put into its owner's
            # graveyard straight from the stack.
            self.fizzled.append(spell.id)
            self.put_into_graveyard(spell)
            # Same cleanup as the successful path below: nothing further on
            # this route will read what was announced for this spell, and
            # `machines/triggers._cast_record_for_clause` now fails an
            # intervening *if* closed rather than misreading a lingering
            # record as "nothing was spent" once it is gone.
            self.forget_cast_record(spell)
            self._before_priority()
            return spell

        # CR 712.8c/712.8f: a double-faced spell on the stack has only the
        # characteristics of the face that's up - `oracle_text` already reads
        # that face, but `spell.card.oracle_text` is the raw Scryfall field,
        # which Scryfall leaves null for `modal_dfc`/`transform` layouts (the
        # text lives on `card_faces` instead). Reading it directly here made
        # every modal-DFC spell side (Shatterskull Smashing, Valakut
        # Awakening, Sink into Stupor, Turntimber Symbiosis) resolve to
        # nothing, since `effect_text` came back empty.
        # CR 107.3a: X is fixed for the whole spell once announced, but only
        # for a spell whose own *cost* actually carries an X to announce - a
        # spell whose text defines its own X some other way (CR 107.3f) gets
        # no substitution at all, which is `effect_for`'s own `x_value=None`
        # default. `spell.mana_cost` already reads the up face of a DFC.
        #
        # Not only `"{X}" in mana_cost`: CR 107.3a's X is announced whenever
        # the cost's own text names it, and a printed cost is not only the
        # mana symbols - Soul Immolation's "As an additional cost to cast
        # this spell, blight X" announces X inside an additional cost with
        # no `{X}` anywhere in its `{3}{R}{R}` mana cost, which used to leave
        # its own "deals X damage to each opponent" sentence unsubstituted
        # even though `blight`'s own X was announced and paid correctly.
        # `cost_announces_x` on each additional-cost sentence is the same
        # general "does this cost's own text carry a bare X" reader
        # `create_continuous_effect_of_ability` now uses for an activated
        # ability's own cost.
        cost_has_x = "{X}" in (spell.mana_cost or "") or any(
            cost_announces_x(phrase) for phrase in additional_cost_phrases(spell.card)
        )
        x_value = self.cast_record(spell).x_value if cost_has_x else None
        # CR 702.102d: a fused split spell resolves the left half's
        # instructions and then the right half's - two independent texts,
        # neither of which is `spell.oracle_text` (that property reads
        # `up_face`, which is undefined for "both faces at once" the same
        # way `base_cost`/`targeting` bypass it for a fused `Casting`).
        # Ordinary resolution stays exactly what it was: one name, one text.
        if spell.fused and spell.card.card_faces and len(spell.card.card_faces) == 2:
            faces_to_resolve = [
                (face.name, face.oracle_text or "") for face in spell.card.card_faces
            ]
        else:
            faces_to_resolve = [(spell.name, spell.oracle_text)]
        # CR 702.174j: an instant or sorcery's gift effect happens before any
        # of the spell's other abilities - ahead of `effect_for`'s own
        # dispatch, not folded into it, because gift is never a clause of
        # the card's own printed text (it lives on the keyword line alone).
        apply_gift_if_promised(self, spell)
        # CR 702.131a: ascend on an instant or sorcery is a spell ability,
        # followed as the spell resolves and ahead of the text printed after it.
        ascend_as_a_spell_resolves(self, spell)
        # CR 608.3: a resolving *permanent* spell's steps are 608.3a-g -
        # become a permanent and enter the battlefield, check its target,
        # attach/merge/go to the graveyard, become a token if it was a copy,
        # create a static-ability-on-the-stack's delayed trigger (dash,
        # blitz, warp). None of those steps runs the permanent's own printed
        # text: CR 112.6a/113.6 make a triggered, activated, or static
        # ability function only once the permanent is on the battlefield.
        # `effect_for`/`_spell_effect_or_notice` exist to read CR 608.2c's
        # "follow the instructions" for an instant/sorcery/ability on the
        # stack, and must never see a permanent's oracle text at all - the
        # bug this guards against ran a permanent's whole printed text as if
        # it were a resolving instant's, so casting Screeching Soulbreaker
        # (a triggered ability's body) drained life immediately, and Ghalta
        # the Immovable's two static lines (a CR 611.3 ability that already
        # reapplies from the battlefield every time the board is computed)
        # were also created a second time here as spurious, indefinite-
        # duration `ContinuousEffect`s that outlived it.
        effects = []
        unread_faces: list[tuple[str, str]] = []
        if not spell.is_permanent:
            for face_name, face_text in faces_to_resolve:
                effect = effect_for(face_name, face_text, x_value=x_value)
                if effect is not None:
                    effects.append(effect)
                elif face_text.strip():
                    unread_faces.append((face_name, face_text))
        if effects:
            try:
                # CR 702.113a/b: an awakened spell's own text resolves without
                # the awaken target; its spell ability follows, printed last.
                with awaken_target_held_apart(self, spell) as awaken_target:
                    for effect in effects:
                        effect(self, spell)
                awaken_as_the_spell_resolves(self, spell, awaken_target)
            except Exception:
                # CR 400.1: "a zone is a place where objects can be during a
                # game" and every object not outside the game is in exactly
                # one. `spell` was already popped off `self.stack` above, so
                # once it is resolving it has no zone of its own until this
                # function gives it one again - the graveyard placement a few
                # lines down (non-permanent) or `enter_the_battlefield`
                # (permanent). If `effect` raises before reaching either -
                # which is exactly what `Game.ask` does when CR 608.2d refuses
                # a mid-resolution answer, an empty `choose_cards` reply among
                # them - the spell is left popped from the stack and
                # nowhere else: this is the bug reported from game
                # 535264e8458e461d874d0d38f4b1866e, where Malevolent Rumble
                # vanished from every zone and the deck came up 59 of 60.
                #
                # CR 733.1 governs a player's illegal action: "the entire
                # action is reversed and any payments already made are
                # canceled" (already the model `machines/cost.py`'s own
                # `unpay` follows for an aborted payment, citing the same
                # rule). There is no way back onto the stack mid-resolution -
                # CR 608.2 has no such step - so the closest legal landing
                # spot is the one CR 608.2n/307.2/304.2 already mandate as the
                # *last* step of every instant's and sorcery's resolution: its
                # owner's graveyard. A permanent spell that could not finish
                # entering is sent there too, the same place CR 608.3e already
                # sends one whose controller "can't put it onto the
                # battlefield" (Worms of the Earth's own example). Whatever
                # the effect had not yet done when it raised - the revealed
                # cards a reveal effect had not yet moved off the library,
                # here - simply never happened, which is the fail-closed,
                # nothing-half-applied posture this project's abilities keep
                # everywhere else.
                #
                # The refusal itself is already on record: `Game.ask` appends
                # every `Decision` to `self.decisions.asked` before it
                # validates the answer, so the question that could not be
                # legally answered is not lost even though its effect never
                # ran. This re-raises afterwards rather than swallowing the
                # error, matching the existing convention for every other
                # illegal `Game.ask` answer (`Seasoned Pyromancer`'s own
                # `test_an_illegal_discard_answer_is_refused_without_
                # corrupting_the_hand`) - the caller still learns the answer
                # was refused at the moment it was given; the difference this
                # branch fixes is that the spell no longer disappears while
                # that exception unwinds.
                self.put_into_graveyard(spell, resolving=True)
                self.forget_cast_record(spell)
                self._before_priority()
                raise

        if unread_faces and not spell.is_permanent:
            # Fail closed: an instant or sorcery whose printed text no parser
            # reads used to resolve as nothing with no trace (Stock Up, live
            # game). A permanent spell's `None` is correct (CR 608.3a).
            for face_name, face_text in unread_faces:
                self.unmodeled_trigger_effect_notices.append(
                    UnmodeledTriggerEffectNotice(
                        source_id=spell.id, source_name=face_name, text=face_text
                    )
                )

        if spell.id in self.turn_ended_exiled_ids or spell.zone in (
            Zone.EXILE,
            Zone.BATTLEFIELD,
            Zone.LIBRARY,
        ):
            # (Also a spell whose own text exiled it as it resolved - Burning
            # Wish's "Exile Burning Wish." (CR 201.5): CR 608.2n's final
            # graveyard step finds no spell left on its way there. Esper
            # Origins' "exile it, then put it onto the battlefield
            # transformed" has already moved it on to the battlefield.
            # Serene Remembrance's own "Shuffle Serene Remembrance and up to
            # three target cards from a single graveyard into their owners'
            # libraries." is the identical shape one zone over - `machines/
            # effects._parse_shuffle_self_and_targets_into_owners_libraries_
            # clause` has already shuffled it into its owner's library by the
            # time this runs.)
            # CR 724.1b exiled this spell while it was resolving, and CR 608.2m
            # let it finish resolving anyway ("If an instant spell, sorcery
            # spell, or ability that can legally resolve leaves the stack once
            # it starts to resolve, it will continue to resolve fully"). It has
            # already been given a zone, so neither of the two placements below
            # applies - it does not reach a graveyard and it does not enter the
            # battlefield.
            self.turn_ended_exiled_ids.discard(spell.id)
            self.forget_cast_record(spell)
            self._before_priority()
            return spell

        if spell.is_permanent:
            # CR 608.3, 608.3a: a resolving permanent spell "becomes a permanent
            # and enters the battlefield under the control of the spell's
            # controller". It was cast, so Containment Priest does not catch it.
            if spell.is_copy:
                # CR 707.10f: "Some effects copy a permanent spell. As that
                # copy resolves, it ceases being a copy of a spell and becomes
                # a token permanent." CR 111.13 says the same from the token
                # side - "A copy of a permanent spell becomes a token as it
                # resolves. The token has the characteristics of the spell
                # that became that token. The token is not 'created' for the
                # purposes of any replacement effect" - and CR 608.3f is the
                # resolution step itself. `CardState.token` is the flag
                # `models/token.is_token` and CR 111.7's state-based action
                # both read; setting it here, rather than at `copy_spell`, is
                # what "as that copy resolves" means: while it is still a
                # spell on the stack it is a copy of a spell, not a token.
                # Nothing is "created", so no token-creation replacement
                # effect (Doubling Season) applies - which is exactly why this
                # sets the flag directly instead of routing through
                # `models/token.create_tokens`.
                spell.token = True
                # "It ceases being a copy of a spell" - CR 707.10f's own
                # words, taken literally: `is_copy` comes off in the same
                # breath `token` goes on, or `Game._copies_that_cease_to_
                # exist`'s CR 704.5e sweep (a copy of a *spell* in a zone
                # other than the stack) would destroy this permanent the very
                # next state-based-action check, the instant after it landed
                # on the battlefield.
                spell.is_copy = False
            if "Aura" in spell.subtypes:
                attachment = self._aura_attachment(spell)
                if attachment is None:
                    # Not fizzled (that was checked above), yet nothing to
                    # attach to - a shape `machines/targeting.py` cannot fully
                    # read for this Aura. CR 608.3c gives it nothing to enter
                    # attached to, and letting it land unattached would only
                    # have CR 704.5m destroy it a moment later - so it does not
                    # enter at all, the same fail-closed policy as the fizzle
                    # branch just above.
                    self.targeting_notices.append(
                        TargetingNotice(
                            kind=TargetingNoticeKind.NO_LEGAL_TARGET,
                            source_id=spell.id,
                            source_name=spell.name,
                            text=spell.oracle_text,
                        )
                    )
                    self.put_into_graveyard(spell)
                    self.forget_cast_record(spell)
                    self._before_priority()
                    return spell
            else:
                attachment = None
            sneak_defender = self._sneak_defender_of(spell)
            self.enter_the_battlefield(
                spell,
                spell.controller or self.active_player.username,
                tapped=sneak_defender is not None,
                # CR 712.13: "the same face up that was face up on the stack".
                transformed=spell.transformed,
                was_cast=True,
                attach_to=attachment,
            )
            if sneak_defender is not None and spell.zone is Zone.BATTLEFIELD:
                from ..token import _put_onto_the_battlefield_attacking

                _put_onto_the_battlefield_attacking(self, spell, sneak_defender)
            self._apply_mana_spend_effects(spell)
            self._create_resolution_delayed_triggers(spell)
            self._keep_keywords_gained_as_a_spell(spell)
            # Deliberately *not* popped here, unlike the graveyard-bound branch
            # below. CR 608.2a rechecks a triggered ability's intervening *if*
            # again as it resolves, and an "enters, if [mana] was spent to cast
            # it" ability (Wistfulness) is only created *now* - it has not
            # resolved yet, and will not until a later priority round, by which
            # time this permanent is long past `enter_the_battlefield`. Popping
            # the record here left that later recheck reading `CastRecord()`'s
            # empty default (`cast_record`'s own fallback) - "no mana was
            # spent" - and the ability silently did nothing on every resolution
            # even though it had correctly gone on the stack in the first
            # place (`test_wistfulness_paid_with_double_blue_draws_two_then_
            # discards_one` is the regression test). The record is keyed by
            # the permanent's own `zone_change_stamp` (`enter_the_battlefield`
            # carried it across, CR 400.7d), so it answers for this object
            # only: once the permanent leaves, nothing finds it (CR 400.7).
        else:
            # CR 614.1: the move to the graveyard is an event like any other, so
            # it goes through the replacement effects. That is the hook
            # CR 702.34a's flashback exile, CR 715.3d's Adventure exile, and
            # CR 702.88a's rebound exile all hang off - each replaces where the
            # card goes as it leaves the stack.
            #
            # Rebound's own delayed trigger (CR 702.88a's "at the beginning of
            # your next upkeep") is created here rather than inside the
            # replacement effect itself: `_create_rebound_delayed_trigger`
            # needs to know whether the spell was cast from hand, and that is
            # `Game.cast_record(spell)` - which is forgotten two lines below,
            # so it has to be read before `put_into_graveyard` runs, not after.
            #
            # Popped here, unlike the permanent branch above: a non-permanent
            # spell's own "when you cast this" trigger (if any) sits *above* it
            # on the stack and has already resolved by the time control
            # reaches this branch (CR 603.3), and nothing else this engine
            # builds watches a graveyard-bound spell's own cast facts once it
            # is there - so there is no later recheck this needs to survive
            # for, and leaving it around risks nothing but also gains nothing.
            cast_from_hand = self.cast_record(spell).origin_zone is Zone.HAND
            self.put_into_graveyard(spell, resolving=True)
            self._create_rebound_delayed_trigger(spell, cast_from_hand)
            self._create_paradigm_delayed_trigger(spell)
            self.forget_cast_record(spell)

        self._before_priority()
        return spell

    def _create_resolution_delayed_triggers(self: "Game", spell: CardState) -> None:
        """Delayed triggered abilities a resolving permanent spell creates (CR 603.7a).

        CR 608.3g: "If the object that's resolving has a static ability that
        functions on the stack and creates a delayed triggered ability, that
        delayed triggered ability is created as that permanent is put onto the
        battlefield." So this runs *after* `enter_the_battlefield`, and the
        object the ability refers to is the permanent, not the spell.

        Two keywords need it. CR 702.185a: "Warp represents two static
        abilities that function while the card with warp is on the stack, one
        of which may create a delayed triggered ability. ... 'If this spell's
        warp cost was paid, exile the permanent this spell becomes at the
        beginning of the next end step.'" CR 702.109a's dash is the same
        shape with a different verb: "If this spell's dash cost was paid,
        return the permanent this spell becomes to its owner's hand at the
        beginning of the next end step."

        CR 603.7d/e give the ability the creating spell's source and its
        controller as it resolved, which is what is recorded here.
        """
        if self.was_cast_with(spell, "Warp") and self.cast_record(spell).keyword_cost_paid:
            self.delayed_triggers.create(
                DelayedTrigger(
                    text=(
                        "Exile the permanent this spell becomes at the "
                        "beginning of the next end step."
                    ),
                    effect=ExileWarped(),
                    event=TriggerEvent.BEGINNING_OF_STEP,
                    step=Step.END_STEP,
                    controller=spell.controller or self.active_player.username,
                    source_id=spell.id,
                    source_name=spell.name,
                    subject_id=spell.id,
                    expected_zone=Zone.BATTLEFIELD,  # CR 603.7c
                    expected_stamp=spell.zone_change_stamp,  # CR 603.7c parenthetical
                )
            )
        if self.was_cast_with(spell, "Suspend") and spell.is_creature:
            # CR 702.62a: "If you cast a creature spell this way, it gains
            # haste until you lose control of the spell or the permanent it
            # becomes." `cast_during_resolution` labels the cast "Suspend".
            grant_suspend_haste(self, spell)
        # CR 702.152a: blitz's delayed sacrifice (`machines/blitz.py`).
        create_blitz_delayed_trigger(self, spell)
        if self.was_cast_with(spell, "Dash"):
            self._grant_dash_haste(spell)
            self.delayed_triggers.create(
                DelayedTrigger(
                    text=(
                        "Return the permanent this spell becomes to its "
                        "owner's hand at the beginning of the next end step."
                    ),
                    controller=spell.controller or self.active_player.username,
                    source_id=spell.id,
                    source_name=spell.name,
                    subject_id=spell.id,
                    expected_zone=Zone.BATTLEFIELD,  # CR 603.7c
                    expected_stamp=spell.zone_change_stamp,  # CR 603.7c parenthetical
                    event=TriggerEvent.BEGINNING_OF_STEP,
                    step=Step.END_STEP,
                    effect=return_subject_to_hand,
                )
            )

    def _resolution_cast_option_is_legal(
        self: "Game", card: CardState, caster: str, option: str | None
    ) -> bool:
        text = card.oracle_text or ""
        if option is not None:
            face = next((f for f in card.card.card_faces or [] if f.name == option), None)
            text = (face.oracle_text if face is not None else None) or ""
        modal = modal_profile(card.card) if option is None else None
        if modal is not None and modal.understood:
            legal = [mode for mode in modal.modes if self._spell_mode_is_legal(card, caster, mode)]
            alternative = self.modal_alternative_applies(modal, caster, card.id, card.name, card)
            if len(legal) < modal.allowed_range(alternative=alternative)[0]:
                return False
        else:
            # Spell-scoped (CR 115.1a-b): a permanent spell's own activated or
            # triggered abilities target nothing as it is cast (CR 113.1c) -
            # Boiling Rock Rioter's "Exile target card from a graveyard" is
            # not a target its creature spell needs. `Casting.targeting` reads
            # the spell the same way when the cast is actually made.
            profile = spell_profile_for_text(text, card.card if option is None else None)
            if (
                profile.understood
                and profile.requirements
                and profile.min_targets > 0
                and not self._legal_target_candidates(profile, caster, card.id)
            ):
                return False
        taken: set[UUID] = set()
        for printed in additional_cost_phrases(card.card):
            phrase = substitute_x(printed, 0)
            if _OPTIONAL_ADDITIONAL_COST.match(phrase):
                continue
            cost = total_cost_for_phrase(phrase, caster)
            alternatives = or_additional_cost_alternatives(phrase) if cost is None else None
            if alternatives is not None:
                # CR 601.2b's "[cost] or [cost]": a mana half is always a way
                # to pay it, and mana is not counted here (see above); a
                # non-mana set is payable when any one alternative's objects
                # and life are (CR 118.3).
                if alternatives[-1].startswith("{"):
                    continue
                if any(
                    option is not None and self._cost_objects_available(option, caster, taken)
                    for option in (total_cost_for_phrase(half, caster) for half in alternatives)
                ):
                    continue
                return False
            if cost is None or not self._cost_objects_available(cost, caster, taken):
                return False
        return True

    def copy_spell(
        self: "Game", spell: CardState, controller: str | None = None
    ) -> CardState | None:
        """CR 707.10: put a copy of `spell` onto the stack - or nothing, for a
        spell that says "This spell can't be copied." (CR 113.6g,
        `casting_restrictions.cannot_be_copied`), which is why every caller
        is handed `None` to pass over rather than a copy.

        "To copy a spell ... means to put a copy of it onto the stack; a copy
        of a spell isn't cast." Unlike `cast_during_resolution`, this does not
        go through `put_on_stack` at all - that method's own CAST_SPELL emit
        is exactly the event CR 707.10 says does *not* happen for a copy, and
        `spells_cast_this_turn` (Alania's own "the first instant spell ...
        you've cast this turn" reads it) must not count a copy as a cast
        either.

        CR 707.2: the copy acquires the original's copiable values - built
        around the same `Card`, since `machines/effects.py` has no
        modification to apply here - "and, for an object on the stack,
        choices made when casting or activating it (mode, targets, the value
        of X, whether it was kicked, how it will affect multiple targets, and
        so on)". `targets`/`division` (CR 601.2d's damage split) are simple
        scalar copiable values carried straight off `spell`; `x_value`,
        `modes`/`mode_targets`, `kicked`, `replicated`, `offspring_paid`,
        `blight_paid`, `gift_promised`/`gift_chosen_player`,
        `additional_cost_cards`, `keyword` and `keyword_cost_paid` all live on
        the *original's* `CastRecord` instead, so they are copied below by
        writing the copy its own record (`Game.note_cast(..., is_copy=True)`),
        keyed by the copy's own `zone_change_stamp` rather than shared with
        the original's. A caller wanting CR 707.10c's "new targets" permission
        chooses them afterward through `offer_new_targets_for_copy`, the same
        way `cast_during_resolution` lets a resolving ability choose targets
        for what it casts.

        **Not copied** (CR 707.2's own list of exclusions): `mana_spent` and
        `spend_effects` - "a copy of Dawnglow Infusion won't cause you to gain
        any life", because the mana that paid the *original's* cost was never
        spent paying the copy's (a copy is never cast, so it has no cost to
        pay at all) - and `exile_instead_of_graveyard`, CR 604.5's own grant
        tied to how the *original* left the stack, not to a copy that ceases
        to exist rather than reaching a graveyard in the first place
        (CR 707.10a).

        The copy is owned **and** controlled by `controller` if given, or by
        the original spell's own controller otherwise (CR 707.10: "A copy of
        a spell is owned by the player under whose control it was put on the
        stack. A copy of a spell or ability is controlled by the player under
        whose control it was put on the stack.") - both halves of that
        sentence name the *copy's own* controller, never the original's
        owner, which is why `owner` is set to `controller` below rather than
        to `spell.owner`: Reverberate copying an opponent's spell is owned by
        the Reverberate caster from the moment it exists, not by whoever owns
        the card the original spell's `Card` came from (a copy has no card of
        its own to begin with - CR 707.10a's own "even if it has no card
        associated with it", CR 112.1a).

        CR 707.10f/111.13: a copy of a *permanent* spell becomes a token as
        it resolves (`token=True`, set below in `_resolve_top_impl` once it
        does), so the object it becomes has to already be a `TokenState` -
        `token` alone is not enough. `TokenState.move_to`'s CR 111.8 override
        ("a token that has left the battlefield can't move ... back onto the
        battlefield") and its `left_the_battlefield` bookkeeping only exist
        on that subclass; a plain `CardState` with `token` flipped true reads
        as a token everywhere `models/token.is_token` is asked, but a second
        zone change through it never sees CR 111.8 refuse it, and a decode
        of it - which reads the same `token` flag - builds a real
        `TokenState` where the live game never had one, so the two disagree
        about a rule the live game was silently missing all along (T10's own
        finding). Built `token=False` here regardless, matching the existing
        comment at the resolution site: while still a copy of a spell on the
        stack it is not yet a token (CR 707.10f's "as that copy resolves").
        A copy of a non-permanent spell (an instant or sorcery) never becomes
        a token at all, so it stays a plain `CardState`.
        """
        return self._put_spell_copy(
            spell,
            controller,
            original_record=self.cast_record(spell),
            targets=list(spell.targets),
            division=spell.division,
        )

    def copy_spell_as_last_known(
        self: "Game", spell: CardState, controller: str | None = None
    ) -> CardState | None:
        """`copy_spell` for "copy that spell" (CR 707.10) naming a spell that
        may have left the stack since the ability triggered: still on the
        stack, it is copied as it is; gone, it is copied as it last existed
        there (CR 608.2h, `CardState.last_known_spell`) - its targets,
        division and the record of how it was cast. `None` for a spell that
        never left the stack as a cast card (a copy ceases to exist, CR
        707.10a) or that can't be copied (CR 113.6g)."""
        if spell in self.stack:
            return self.copy_spell(spell, controller)
        last_known = spell.last_known_spell
        if last_known is None:
            return None
        if last_known.cast_record is not None:
            record = CastRecord.model_validate(last_known.cast_record)
        else:
            record = self.cast_record_as_last_known(last_known.stamp) or CastRecord()
        return self._put_spell_copy(
            spell,
            controller,
            original_record=record,
            targets=list(last_known.targets),
            division=list(last_known.division) if last_known.division is not None else None,
        )

    def _put_spell_copy(
        self: "Game",
        spell: CardState,
        controller: str | None,
        *,
        original_record: CastRecord,
        targets: list[TargetRef],
        division: list[int] | None,
    ) -> CardState | None:
        if cannot_be_copied(spell):
            return None
        with self._id_allocator_scope():
            controller = controller or spell.controller or self.controller_of(spell).username
            state_type = TokenState if spell.is_permanent else CardState
            copy = state_type(
                # CR 707.2: a text-changing effect on the original isn't copied.
                card=self.text_change_originals.get(str(spell.id), spell.card),
                zone=Zone.STACK,
                controller=controller,
                owner=controller,
                is_copy=True,
                token=False,
                targets=targets,
                face_played=spell.face_played,
                land_face_played=spell.land_face_played,
                division=division,
                # CR 722.3d: "If a prepare spell is copied, the copy is also
                # a prepare spell" - carried onto any further copy of a
                # CR 722.3c exile copy, so it keeps reading its inset face's
                # characteristics and still counts as "a prepared spell" for
                # `machines/triggers.py`'s CAST_SPELL condition, though a
                # copy made here is never itself cast (CR 707.10).
                prepare_spell_face=spell.prepare_spell_face,
                # CR 707.10g: a copy of a double-faced spell with its back
                # face up (a disturbed one, CR 702.146b) is created back face
                # up too.
                transformed=spell.transformed,
            )
            self.stack.append(copy)
            from ...machines.text_changes import sync_text_changes

            sync_text_changes(self)
            self.note_cast(
                copy,
                keyword=original_record.keyword,
                keyword_cost_paid=original_record.keyword_cost_paid,
                face=original_record.face,
                modes=list(original_record.modes),
                mode_targets=[list(slice_) for slice_ in original_record.mode_targets],
                x_value=original_record.x_value,
                kicked=original_record.kicked,
                replicated=original_record.replicated,
                casualty_paid=original_record.casualty_paid,
                conspire_paid=original_record.conspire_paid,
                offspring_paid=original_record.offspring_paid,
                blight_paid=original_record.blight_paid,
                gift_promised=original_record.gift_promised,
                gift_chosen_player=original_record.gift_chosen_player,
                additional_cost_cards=list(original_record.additional_cost_cards),
                additional_cost_mana_values=list(original_record.additional_cost_mana_values),
                additional_cost_kinds=list(original_record.additional_cost_kinds),
                additional_cost_powers=list(original_record.additional_cost_powers),
                is_copy=True,
                # CR 707.10: the additional and alternative cost decisions.
                kicker_costs_paid=list(original_record.kicker_costs_paid),
                bargained=original_record.bargained,
                evidence_collected=original_record.evidence_collected,
                revealed_for_cost=original_record.revealed_for_cost,
                beheld_for_cost=original_record.beheld_for_cost,
                waterbend_paid=original_record.waterbend_paid,
            )
            return copy

    def copy_ability(
        self: "Game", ability: AbilityOnStack, controller: str | None = None
    ) -> AbilityOnStack:
        """CR 707.10: put a copy of an activated or triggered ability onto the
        stack - "a copy of an activated ability isn't activated", so no cost
        is paid and nothing that watches activations sees it.

        The copy "copies both the characteristics of the spell or ability and
        all decisions made for it, including modes, targets, the value of X"
        (CR 707.10), so it is the original object's own data under a fresh
        id; CR 707.10b: it has the same source, and CR 707.10: it is
        controlled by the player under whose control it was put on the stack.
        A ward-style payment already made for the original is not the copy's
        (`unless_payment` starts empty), and a delayed trigger's copy resolves
        through the same delayed effect the original would have.
        """
        with self._id_allocator_scope():
            data = ability.model_dump(mode="json")
            data["id"] = str(new_id())
            data["controller"] = controller or ability.controller
            data["unless_payment"] = None
            copy = AbilityOnStack.model_validate(data)
            if copy.keyword_activation is not None:
                copy.keyword_activation.game = self
                if copy.keyword_activation.payment is not None:
                    copy.keyword_activation.payment.game = self
            pending = self.delayed_triggers.pending.get(ability.id)
            if pending is not None:
                self.delayed_triggers.pending[copy.id] = pending
            self.stack.append(copy)
            return copy

    def offer_new_targets_for_copy(
        self: "Game",
        copy: CardState | None,
        controller: str,
        *,
        source_name: str = "",
        source_id: str | None,
    ) -> None:
        """CR 707.10c-shaped permission: "you may choose new targets for the
        copy" (Alania, Divergent Storm being the only printing in the pool).

        A plain `MAY` (CR 608.2d), then the same `CHOOSE_TARGETS` question
        `cast_during_resolution` asks - reusing `_legal_target_candidates`
        rather than a second target-legality reader. Declining, or a
        restriction this session's targeting reader cannot parse at all,
        leaves the copy with whatever it already had (CR 707.2's copied
        targets), never with none chosen instead - "new targets" is an
        option to replace them, not a second, separate targeting event that
        could come back empty.

        A **modal** copy (`cast_record(copy).modes` non-empty) profiles only
        its chosen modes' own targeting requirements (CR 700.2c/700.2f), the
        same way `_resolution_profile` rechecks an ordinary modal spell's
        targets rather than `profile_for_text`ing the whole "Choose two -"
        printed text (which `TargetingProfile` reads as unmodal and
        unreadable): `profile_for_modes_with_owners` gives the per-mode
        requirements plus which chosen mode instance each one belongs to, and
        that same `owners` list is what lets a changed target be written back
        into the *right* mode's own slice of `CastRecord.mode_targets`
        (`TargetingProfile.assign_to_owners`) rather than left stale while
        only the flat `copy.targets` moves - CR 700.2g still holds regardless
        (the modes themselves are never touched here, only their targets).
        """
        if copy is None:
            # `copy_spell` made no copy (CR 113.6g): nothing to retarget.
            return
        record = self.cast_record(copy)
        owners: list[int] | None = None
        if record.modes:
            try:
                profile, owners = profile_for_modes_with_owners(
                    copy.card, record.modes, record.x_value or None
                )
            except ValueError:
                # Not actually a modal card - fall through to its plain text.
                profile = profile_for_text(copy.oracle_text or "")
        else:
            profile = profile_for_text(copy.oracle_text or "")
        if not profile.understood or not profile.requirements:
            return
        candidates = self._legal_target_candidates(profile, controller, copy.id)
        if not candidates:
            return
        if not self.may(
            self.player(controller),
            "choose new targets for the copy",
            source=source_name,
            source_id=source_id,
        ):
            return
        decision = Decision(
            kind=DecisionKind.CHOOSE_TARGETS,
            player=controller,
            prompt=f"choose new targets for the copy of {copy.name}",
            source=source_name,
            source_id=source_id,
            targets=tuple(TargetRef.coerce(candidate) for candidate in candidates),
            target_maximum=profile.max_targets,
            # Deliberately 0, not `profile.min_targets`: CR 707.10c is "you may
            # choose new targets for the copy. If you choose to change one or
            # more of the targets, follow the rules ... in rule 601.2c-601.2d"
            # - the mandatory floor only binds *after* a target is actually
            # being changed. Choosing to change none, having already said
            # `may` above, is still a legal outcome (the copy keeps CR 707.2's
            # copied targets), not the `may`'s own decline read twice.
        )
        chosen = self.ask(decision)
        assert isinstance(chosen, (list, tuple))
        if not chosen:
            return
        copy.targets = list(chosen)
        if owners is not None:
            assignment = profile.assign_to_owners(
                owners, list(chosen), controller, game=self, source_id=copy.id
            )
            mode_targets = [list(assignment.get(index, [])) for index in range(len(record.modes))]
            self.cast_records[copy.zone_change_stamp] = record.model_copy(
                update={"mode_targets": mode_targets}
            )

    def copy_spell_targeting(
        self: "Game", spell: CardState, controller: str, target: "Targetable | AbilityOnStack"
    ) -> CardState | None:
        """CR 707.10e: an effect that copies a spell and *specifies* a new
        target for the copy, rather than CR 707.10c's optional "you may
        choose new targets" permission `offer_new_targets_for_copy` covers -
        Frontline Heroism's own "create a 1/1 red Soldier ... token, then
        copy that spell. The copy targets that token" is the one printing in
        the pool.

        CR 707.10e, verbatim: "Some effects copy a spell or ability and
        specify a new target for the copy... If that player or object isn't
        a legal target for each instance of the word 'target,' the copy
        isn't created."

        Reuses the same target-legality primitive `_legal_target_candidates`
        already calls (`TargetRequirement.rejects`) and the same profile
        `_resolution_profile` already builds for an ordinary CR 608.2b
        recheck - modal, X, split, and Adventure spells included - rather
        than a second reader: `target` has to satisfy *every* requirement
        the spell's text has ("each instance of the word 'target'"), not
        just one, which is why this checks all of `profile.requirements`
        rather than reusing `_legal_target_candidates`'s own any-of-them
        membership test. A profile this session's reader could not parse at
        all, or a spell with no targets to begin with, refuses the same way -
        a restriction that cannot be read is never treated as satisfied.

        No copy reaches the stack when `target` fails - CR 707.10e's own "the
        copy isn't created", not a copy made and then fizzled - which is why
        this builds the copy only *after* every requirement has already
        accepted `target`, and returns `None` with nothing created otherwise.

        A **modal** copy's `CastRecord.mode_targets` is kept in step with the
        forced retarget the same way `offer_new_targets_for_copy` keeps it in
        step with an *optional* one (CR 700.2f): `machines/effects.py`'s
        modal resolution reads `mode_targets`, not `copy.targets`, so a modal
        spell copied through this path without the sync would resolve every
        chosen mode against the *original's* pre-retarget slices instead of
        `target`.
        """
        profile = self._resolution_profile(spell)
        if not profile.understood or not profile.requirements:
            return None
        for requirement in profile.requirements:
            if requirement.rejects(target, controller, self, spell.id) is not None:
                return None
        copy = self.copy_spell(spell, controller=controller)
        if copy is None:
            return None
        ref = TargetRef.coerce(target)
        copy.targets = [ref for _ in profile.requirements]
        record = self.cast_record(copy)
        if record.modes:
            try:
                mode_profile, owners = profile_for_modes_with_owners(
                    copy.card, record.modes, record.x_value or None
                )
            except ValueError:
                mode_profile = None
            if mode_profile is not None and mode_profile.requirements:
                assignment = mode_profile.assign_to_owners(
                    owners, copy.targets, controller, game=self, source_id=copy.id
                )
                mode_targets = [
                    list(assignment.get(index, [])) for index in range(len(record.modes))
                ]
                self.cast_records[copy.zone_change_stamp] = record.model_copy(
                    update={"mode_targets": mode_targets}
                )
        return copy

    def change_targets(
        self: "Game",
        subject: "CardState | AbilityOnStack",
        chooser: str,
        *,
        scope: RetargetScope,
        to: "CardState | None" = None,
        optional: bool = False,
        source_name: str = "",
        source_id: str | None = None,
    ) -> bool:
        """CR 115.7: change the target(s) of a spell or ability on the stack.

        `scope` is how many may change (`RetargetScope`): CR 115.7a's "change
        the target(s)" is all or none, CR 115.7b's "change a target" exactly
        one, CR 115.7c/115.7d's "change any targets"/"choose new targets" any
        number. `to` is "... to this creature" (Hydroelectric Specimen,
        Spellskite): the one object a changed target may become. `optional`
        is the effect's own "you may", asked (CR 608.2d) only once a legal
        change actually exists - CR 115.7a: "If a target can't be changed to
        another legal target, the original target is unchanged", so there is
        nothing to ask about otherwise.

        Every new target must be *another* target (CR 115.7a), legal for the
        requirement the old one filled, judged from the changed object's own
        controller - the same `TargetRequirement.rejects` plus shroud,
        hexproof and protection checks an announcement makes (CR 601.2c) -
        and must not name one object twice for one instance of "target"
        (CR 115.3). CR 115.7e: only the final set is evaluated, which is why
        each target is judged against the other targets as they will stand.
        CR 115.7f: a division is never touched.

        Returns whether anything changed. `chooser` answers every question -
        the player the effect names, not the changed object's controller.
        """
        profile = self._stack_object_profile(subject)
        if not profile.understood or not profile.requirements or not subject.targets:
            return False
        owner = (
            subject.controller
            if isinstance(subject, AbilityOnStack)
            else self.controller_of(subject).username
        )
        slots = self._target_slots(profile, subject, owner)
        if slots is None:
            return False
        refs = list(subject.targets)
        candidates = [
            thing
            for thing in ([to] if to is not None else self.targetable_objects())
            if thing is not None
        ]

        def legal_at(position: int, current: list[TargetRef]) -> list[Any]:
            return [
                thing
                for thing in candidates
                if self._legal_retarget(thing, position, current, slots, owner, subject)
            ]

        eligible = [position for position in range(len(refs)) if legal_at(position, refs)]
        if scope is RetargetScope.ALL and len(eligible) != len(refs):
            return False
        if not eligible:
            return False
        if optional and not self.may(
            self.player(chooser),
            f"change the target of {subject.name}",
            source=source_name,
            source_id=source_id,
        ):
            return False

        def choose(position: int, current: list[TargetRef], minimum: int) -> TargetRef | None:
            legal = legal_at(position, current)
            if not legal:
                return None
            if to is not None and minimum:
                return TargetRef.coerce(to)
            chosen = self.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_TARGETS,
                    player=chooser,
                    prompt=f"choose a new target for {subject.name} (was {current[position]})",
                    source=source_name,
                    source_id=source_id,
                    targets=tuple(TargetRef.coerce(thing) for thing in legal),
                    target_maximum=1,
                    target_minimum=minimum,
                )
            )
            assert isinstance(chosen, (list, tuple))
            return TargetRef.coerce(chosen[0]) if chosen else None

        updated = list(refs)
        if scope is RetargetScope.ONE:
            position = eligible[0]
            distinct = list(dict.fromkeys(refs[index] for index in eligible))
            if len(distinct) > 1:
                picked = self.ask(
                    Decision(
                        kind=DecisionKind.CHOOSE_TARGETS,
                        player=chooser,
                        prompt=f"choose which target of {subject.name} to change",
                        source=source_name,
                        source_id=source_id,
                        targets=tuple(distinct),
                        target_maximum=1,
                        target_minimum=1,
                    )
                )
                assert isinstance(picked, (list, tuple))
                position = next(index for index in eligible if refs[index] == picked[0])
            new = choose(position, updated, 1)
            if new is None:
                return False
            updated[position] = new
        else:
            minimum = 1 if scope is RetargetScope.ALL else 0
            for position in eligible:
                new = choose(position, updated, minimum)
                if new is None:
                    if scope is RetargetScope.ALL:
                        # CR 115.7a: "If all the targets aren't changed to other
                        # legal targets, none of them are changed."
                        return False
                    continue
                updated[position] = new
        if updated == refs and all(
            a.zone_change_stamp == b.zone_change_stamp for a, b in zip(updated, refs, strict=True)
        ):
            return False
        self._write_retargeted(subject, refs, updated)
        return True

    def _stack_object_profile(
        self: "Game", subject: "CardState | AbilityOnStack"
    ) -> TargetingProfile:
        """The targeting requirements a stack object's targets were chosen
        against: a spell's own resolution profile, or an ability's own text
        with its announced X substituted - the same two readings `legal_target`
        rechecks with at resolution (CR 608.2b)."""
        if isinstance(subject, AbilityOnStack):
            text = (
                substitute_x(subject.ability.text, subject.x_value)
                if isinstance(subject.ability, ActivatedAbility)
                and cost_announces_x(subject.ability.cost)
                else subject.ability.text
            )
            return profile_for_text(text)
        return self._resolution_profile(subject)

    def _target_slots(
        self: "Game",
        profile: TargetingProfile,
        subject: "CardState | AbilityOnStack",
        owner: str,
    ) -> "list[TargetRequirement] | None":
        """Which requirement ("instance of the word 'target'", CR 115.3) each
        of `subject`'s targets fills, in target order.

        Placed the way `TargetingProfile._fill_slots` places an announcement:
        each target takes the first open requirement that accepts it. A target
        that is no longer legal anywhere (CR 115.7a leaves it in place "even if
        the original target is itself illegal by then") falls back to the
        first open requirement of its kind, judged off its bare reference.
        """
        source_ref = subject.source_id if isinstance(subject, AbilityOnStack) else subject.id
        fixed = [
            requirement
            for requirement in profile.requirements
            if not requirement.unbounded
            for _ in range(requirement.count)
        ]
        unbounded = [requirement for requirement in profile.requirements if requirement.unbounded]
        placed: list[TargetRequirement] = []
        for ref in subject.targets:
            live = self.resolve_target(ref)
            slot: TargetRequirement | None = None
            for probe in [thing for thing in (live, ref) if thing is not None]:
                for index, requirement in enumerate(fixed):
                    if requirement.rejects(probe, owner, self, source_ref) is None:
                        slot = fixed.pop(index)
                        break
                else:
                    slot = next(
                        (
                            requirement
                            for requirement in unbounded
                            if requirement.rejects(probe, owner, self, source_ref) is None
                        ),
                        None,
                    )
                if slot is not None:
                    break
            if slot is None:
                return None
            placed.append(slot)
        return placed

    def _legal_retarget(
        self: "Game",
        thing: Any,
        position: int,
        current: list[TargetRef],
        slots: "list[TargetRequirement]",
        owner: str,
        subject: "CardState | AbilityOnStack",
    ) -> bool:
        """Whether `thing` may replace `current[position]` (CR 115.7a/115.7e)."""
        if thing is None or thing is subject or getattr(thing, "id", None) == subject.id:
            # CR 115.5: a spell or ability on the stack is an illegal target
            # for itself.
            return False
        new = TargetRef.coerce(thing)
        if new == current[position]:
            return False
        source_ref = subject.source_id if isinstance(subject, AbilityOnStack) else subject.id
        if slots[position].rejects(thing, owner, self, source_ref) is not None:
            return False
        if any(
            index != position and slots[index] is slots[position] and other == new
            for index, other in enumerate(current)
        ):
            return False
        source_card = self._source_card_of(subject)
        if not isinstance(thing, AbilityOnStack):
            if (
                source_card is not None
                and self.protection_refusal(
                    thing,
                    source_card,
                    source_controller=owner,
                    is_spell=isinstance(subject, CardState),
                    source_state=None if isinstance(subject, CardState) else subject.source(self),
                    source_mana_value=(
                        self._protection_characteristics(subject).mana_value
                        if isinstance(subject, CardState)
                        else None
                    ),
                )
                is not None
            ):
                return False
            if self.shroud_refusal(thing) is not None:
                return False
            if self.hexproof_refusal(thing, owner, subject) is not None:
                return False
        return True

    def _write_retargeted(
        self: "Game",
        subject: "CardState | AbilityOnStack",
        before: list[TargetRef],
        after: list[TargetRef],
    ) -> None:
        """Store a changed target list, keeping a modal spell's per-mode slices
        (`CastRecord.mode_targets`, CR 700.2f) in step with it."""
        subject.targets = list(after)
        if not isinstance(subject, CardState):
            return
        record = self.cast_record(subject)
        if not record.mode_targets:
            return
        replacements = [(old, new) for old, new in zip(before, after, strict=True) if old != new]
        mode_targets = [list(slice_) for slice_ in record.mode_targets]
        for old, new in replacements:
            for slice_ in mode_targets:
                if old in slice_:
                    slice_[slice_.index(old)] = new
                    break
        self.cast_records[subject.zone_change_stamp] = record.model_copy(
            update={"mode_targets": mode_targets}
        )

    def resolve_triggered_mana_abilities(
        self: "Game",
        triggered: Sequence[AbilityOnStack],
        *,
        color_hints: Sequence[Color] = (),
        planned: bool = False,
    ) -> None:
        """Resolve CR 605.1b's triggered mana abilities inline (CR 605.4a).

        CR 605.1b: "A triggered ability is a mana ability if it meets all of the
        following criteria: it doesn't require a target (see rule 115.6), it
        triggers from the activation or resolution of an activated mana ability
        ...". CR 605.4a then keeps it off the stack: it "resolves immediately
        after the mana ability that triggered it, without waiting for priority".

        Everything handed here triggered off a mana ability resolving: CR
        106.12a's tap (`tapped_for_mana_event`, Leyline of Abundance) or the
        adding (`ExtraTriggerEvent.MANA_ADDED`, Caged Sun), raised by
        `activate_ability`'s fast path and by `CostPayment.tap_for_mana` alike.
        So the remaining criteria are the two checked below: no target, and an
        effect that could add mana (`parse_triggered_mana`). Anything else
        stays pending for the stack (CR 605.5a).

        `color_hints` are colours a payment's solver already chose for this
        mana (`take_mana_color_hint`); a colour not hinted is asked. `planned`
        says the hints are a payment plan's, so a "may add" the plan left out
        is declined instead of asked (CR 608.2d); otherwise it is asked.

        Each resolution that actually puts mana in the pool re-raises the same
        event from the same source, because a triggered mana ability's own
        "add" is itself something causing a player to add mana - which is what
        makes DDR#990's Caged Sun-under-Toph loop a loop at all.

        **CR 104.4b** is the bound: "If a game that's not using the limited
        range of influence option (including a two-player game) somehow enters
        a 'loop' of mandatory actions, repeating a sequence of events with no
        way to stop, the game is a draw." Past
        `TRIGGERED_MANA_ABILITY_LOOP_BOUND` consecutive inline resolutions off
        one activation, `Game.drawn` is set and the chain stops.
        """
        previous_hints = self._mana_color_hints
        previous_planned = self._mana_hints_planned
        self._mana_color_hints = tuple(color_hints)
        self._mana_hints_planned = planned
        try:
            self._resolve_triggered_mana_abilities(list(triggered))
        finally:
            self._mana_color_hints = previous_hints
            self._mana_hints_planned = previous_planned

    def _resolve_triggered_mana_abilities(self: "Game", pending: list[AbilityOnStack]) -> None:
        resolved = 0
        while pending:
            ability = pending.pop(0)
            if ability not in self.pending_triggers:
                continue
            if ability.targets:
                continue  # CR 605.5a: not a mana ability.
            # CR 603.7: a delayed triggered ability's own effect is not
            # printed on any card (Molten Tide's, High Tide's own "until end
            # of turn, whenever you tap ..." grant), so whether it is a mana
            # ability at all is read off `DelayedEffectSpecBase.is_mana_
            # ability` - the same self-description `_resolve_ability` already
            # reaches for through `DelayedTriggers.effect_for` - rather than
            # off printed text `parse_triggered_mana` was never going to
            # find, since `ability.ability.effect` here is the *whole*
            # "until end of turn, whenever ..." sentence, not a resolution
            # instruction to re-read as one.
            delayed = self.delayed_triggers.trigger_for(ability)
            run_delayed: DelayedEffectSpecBase | None = None
            if delayed is not None:
                run_delayed = self.delayed_triggers.effect_for(ability)
                if run_delayed is None or not run_delayed.is_mana_ability:
                    continue
            else:
                printed = ability.ability
                if not isinstance(printed, TriggeredAbility):
                    continue
                effect_text = printed.effect.lower().strip()
                if parse_triggered_mana(printed.effect) is None and not effect_text.startswith(
                    "add "
                ):
                    continue  # CR 605.5a: not a mana ability.
            if resolved >= self.TRIGGERED_MANA_ABILITY_LOOP_BOUND:
                # CR 104.4b. See `Game.drawn`'s own docstring for what this
                # detection does and does not cover.
                self.drawn = True
                return
            self.pending_triggers.remove(ability)
            source = ability.source(self)
            before = {
                player.username: dict(self.mana_pool_receiving(player.username).floating)
                for player in self.players
            }
            # CR 605.4a: no stack and no priority, so none of `_resolve_ability`'s
            # before-priority work (state-based actions, putting other waiting
            # triggers on the stack) happens between one mana ability and the
            # next - only the CR 603.4 recheck and the effect itself.
            if self._intervening_if_still_true(ability):
                if delayed is not None:
                    if run_delayed is not None:
                        run_delayed(self, ability, delayed)
                else:
                    run_printed = self._effect_of(ability)
                    if run_printed is not None:
                        run_printed(self, ability)
                    else:
                        self._note_unread_trigger(ability)
            resolved += 1
            added: list[Color] = []
            for username, was in before.items():
                now = self.mana_pool_receiving(username).floating
                for color, count in now.items():
                    added.extend([color] * max(0, count - was.get(color, 0)))
            if added and source is not None:
                pending.extend(self.emit(mana_added_event(source, self, mana_added=added)))

    def _resolve_ability(self: "Game", ability: AbilityOnStack) -> AbilityOnStack:
        """Resolve an ability that was on the stack (CR 608.2).

        Two things can stop the effect happening:

        - **CR 608.2b** - if every target it chose is now illegal, it does not
          resolve at all.
        - **CR 608.2a** - an intervening *if* clause (CR 603.4) is checked again
          here; if it is false "the ability is removed from the stack and does
          nothing".

        Either way **CR 608.2n** applies: "As the final part of an ability's
        resolution, the ability is removed from the stack and ceases to exist."
        An ability is not a card (CR 405.1), so it goes to no zone - not even a
        graveyard - and its source is irrelevant by now (CR 113.7a).

        Some of `machines/effects.py`'s ability effects apply one clause of
        their printed text unconditionally (Fight Rigging's own +1/+1 counter,
        Cori-Steel Cutter's own token, Tyvar's and Six's own mill) and only
        *then* ask a later CR 608.2d question about an optional clause that
        follows it (the free cast, the attach, the return, the pick from among
        the milled cards). That earlier mutation is not something to reverse
        if the later question can't be legally answered and `Game.ask` raises
        - CR 733.1's reversal is for an action that "can't legally complete",
        and the first clause already did, in full, exactly as printed
        (CR 608.2c's textual order). What was not guaranteed before this fix
        is the bookkeeping below: `discard` and `_before_priority` never ran
        if `effect` raised, the same gap `Game.resolve_top` had for a spell's
        own final-resolution step before it started catching and re-raising.
        Left alone here, an ability that got that far - counter or token or
        milled cards already real - would leave the stack with CR 608.2n's own
        "ceases to exist" bookkeeping undone and CR 704.3's state-based-action
        check skipped before whatever comes next, which is its own kind of
        half-applied state even though no zone placement needs reversing.
        """
        try:
            if self.spell_fizzles(ability):
                self.fizzled.append(ability.id)
            elif self._intervening_if_still_true(ability):
                delayed = self.delayed_triggers.trigger_for(ability)
                if delayed is not None:
                    # CR 603.7: a delayed triggered ability's effect is not
                    # printed anywhere, so it comes from `machines/delayed.py`
                    # rather than from the registry keyed on the source
                    # card's text.
                    run = self.delayed_triggers.effect_for(ability)
                    if run is not None:
                        run(self, ability, delayed)
                else:
                    key = resolution_key(ability)
                    self.ability_resolutions_this_turn[key] = (
                        self.ability_resolutions_this_turn.get(key, 0) + 1
                    )
                    effect = self._effect_of(ability)
                    if effect is not None:
                        exiled_before = {card.id for card in self.exile}
                        effect(self, ability)
                        # CR 607.2a: what this ability exiled is "exiled with"
                        # its source for the source's other linked ability.
                        link_cards_exiled_during(self, ability, exiled_before)
                        self._announce_final_chapter_resolved(ability)
                    else:
                        self._note_unread_trigger(ability)
        except Exception:
            self.delayed_triggers.discard(ability)  # CR 608.2n: it ceases to exist
            self._before_priority()
            raise

        self.delayed_triggers.discard(ability)  # CR 608.2n: it ceases to exist
        self._before_priority()
        return ability

    def _announce_final_chapter_resolved(self: "Game", ability: AbilityOnStack) -> None:
        """Raise `FINAL_CHAPTER_RESOLVED` when `ability` is a Saga's final
        chapter ability and has just finished resolving (CR 714.2e names the
        final chapter ability: the chapter ability with the Saga's final
        chapter number in its chapter symbol). The Saga is read as it was
        (CR 608.2h's last known information) when it has since left."""
        printed = ability.ability
        if not isinstance(printed, TriggeredAbility) or printed.chapter is None:
            return
        saga = ability.source_or_last_known(self)
        if saga is None or saga.final_chapter_number != printed.chapter:
            return
        self.emit(
            GameEvent(
                event=ExtraTriggerEvent.FINAL_CHAPTER_RESOLVED,
                subject_id=saga.id,
                subject_name=saga.name,
                subject_controller=ability.controller,
                player=ability.controller,
                amount=printed.chapter,
            )
        )

    def _effect_of(self: "Game", ability: AbilityOnStack) -> object | None:
        """The scripted effect of an ability, or None if nobody has written one.

        A **keyword** ability is asked about first. `machines/effects.py` is keyed
        by `(card name, event)` and `(card name, index)`, and a CR 702 keyword
        ability belongs to no card name - cycling is the same ability on every
        card that prints it, and so are equip, ward, prowess, cascade, persist and
        madness. `machines/keywords.keyword_effect_for` answers for both kinds:
        an activated one through the `KeywordActivation` that put it on the stack
        (CR 602.2), a triggered one through `TriggeredAbility.keyword`
        (CR 603.2). Returning None there means no keyword owns the ability and
        the card-name registries are the right place to look.

        Asked *here* rather than anywhere else, a keyword ability's effect goes
        through the ordinary CR 608.2 resolution path with everything that
        implies: CR 608.2b's target recheck, CR 608.2a's intervening *if*, and
        CR 608.2n's removal from the stack.
        """
        keyword = keyword_effect_for(ability)
        if keyword is not None:
            return keyword
        # CR 725.2's own two abilities have no source and are printed on no
        # card - asked here, ahead of the card-name registries, for the same
        # reason a keyword ability is: neither could ever be keyed under a
        # card name.
        monarch = monarch_effect_for(ability)
        if monarch is not None:
            return monarch
        if isinstance(ability.ability, TriggeredAbility):
            # `event` may be None, and that is not "no effect": CR 603.8's
            # state triggers ("Some triggered abilities trigger when a game
            # state ... is true, rather than triggering when an event occurs")
            # have no `TriggerEvent` to name, and neither does a condition the
            # parser reads without matching one of the enumerated events -
            # Caged Sun's "Whenever a land's ability causes you to add one or
            # more mana of the chosen color". `trigger_effect_for` takes
            # `TriggerEvent | None` and keys such a row on the condition text,
            # so gating on the event here was refusing to look the effect up
            # at all.
            # CR 107.3m is scoped explicitly to "an object's enters-the-
            # battlefield triggered ability" (verified whole this merge,
            # `mise run rules:find 107.3`, rather than trusted from either
            # side's own paraphrase) - gated to `ENTERS_THE_BATTLEFIELD`
            # rather than applied to every triggered event, so a cast
            # spell's own X never bleeds into an unrelated attack/dies
            # trigger's bare "X" (CR 107.3f territory, not this rule).
            effect_text = self._etb_x_effect_text(ability, uncast_x=0)
            # CR 701.37c: "If a permanent's ability instructs a player to
            # 'monstrosity X,' other abilities of that permanent may also
            # refer to X. The value of X in those abilities is equal to the
            # value of X as that permanent became monstrous." Polukranos,
            # World Eater's own "it deals X damage divided ..." trigger is
            # exactly this - a bare "X" with no "where X is ..." clause of
            # its own, so it has to come from somewhere else, the same shape
            # CR 107.3m's ETB branch above reads off a spell's own cast
            # record. Here the somewhere else is the `GameEvent` `Game.
            # become_monstrous` emitted to raise this very trigger:
            # `ability.event.amount` is the N (or X) it became monstrous
            # with, already resolved to a real number by the time the
            # permanent triggered at all (CR 701.37a's own "put N +1/+1
            # counters on it" already spent it), so substituting the literal
            # digit here needs no separate `CastRecord` lookup the way a
            # cast spell's own X does.
            if (
                ability.ability.event is TriggerEvent.BECOMES_MONSTROUS
                and effect_text
                and re.search(r"\bX\b", effect_text)
                and ability.event is not None
                and ability.event.amount is not None
            ):
                effect_text = substitute_x(effect_text, ability.event.amount)
            trigger_source = ability.source(self)
            trigger_source_card = getattr(trigger_source, "card", None)
            legendary = trigger_source_card is not None and (
                Supertype.LEGENDARY in trigger_source_card.supertypes
            )
            return trigger_effect_for(
                ability.source_name, ability.ability.event, effect_text, legendary=legendary
            )
        if isinstance(ability.ability, ActivatedAbility):
            if ability.ability.class_level_target is not None:
                # CR 716.2a's own mechanical half - "This Class's level
                # becomes N" - generalised off the level bar itself rather
                # than a card-name-keyed row, so any Class works the same way.
                target = ability.ability.class_level_target

                def become_level(game: "Game", stack_object: "AbilityOnStack") -> None:
                    permanent = stack_object.source(game)
                    if permanent is None or permanent.class_level == target:
                        return
                    permanent.class_level = target
                    # CR 716.2a: "This Class's level becomes N" is the event
                    # a "When this Class becomes level N" trigger watches.
                    game.emit(
                        GameEvent(
                            event=ExtraTriggerEvent.CLASS_BECOMES_LEVEL,
                            subject_id=permanent.id,
                            subject_name=permanent.name,
                            subject_controller=permanent.controller,
                            subject_card=permanent.card,
                            player=permanent.controller,
                            amount=target,
                        )
                    )

                return become_level
            index = self._activated_index(ability)
            if index is None and ability.ability.effect is not None:
                # CR 111.7/CR 704.5d: a token sacrificed to pay its own
                # ability's cost (Clue's, Food's) has already ceased to exist
                # by the time this resolves, so `_activated_index` finds no
                # live source to enumerate abilities off and cannot answer
                # its own numbered position (CR 603.10a - this ability's
                # *effect*, already captured verbatim on `ability.ability`
                # when it went on the stack, is not looked back for the same
                # way). `index` only ever keys `ACTIVATED_EFFECTS`, which is
                # empty by design (every row is now read off printed text
                # instead, see that dict's own docstring) - so `0` here can
                # never shadow a real per-card row, today or as the registry
                # grows, because a token's synthesised name never collides
                # with a printed card's.
                index = 0
            if index is not None:
                # CR 107.3a's X, only when the printed cost actually carries
                # one (Fiend Artisan's `{X}{B/G}`) - the same "only if {X} is
                # in the mana cost" gate `resolve_top` uses for a spell's own
                # `x_value`, so an ordinary ability's bare "X" in its rules
                # text (CR 107.3f) is never mistaken for this one.
                x_value = ability.x_value if cost_announces_x(ability.ability.cost) else None
                activated_source = ability.source(self)
                activated_source_card = getattr(activated_source, "card", None)
                legendary = activated_source_card is not None and (
                    Supertype.LEGENDARY in activated_source_card.supertypes
                )
                return activated_effect_for(
                    ability.source_name,
                    index,
                    ability.ability.effect,
                    x_value=x_value,
                    legendary=legendary,
                )
        return None

    def _intervening_if_still_true(self: "Game", ability: AbilityOnStack) -> bool:
        """CR 608.2a: recheck the intervening *if* as the ability resolves.

        A trigger whose source has left is checked as true, because the clause is
        usually about the source and there is nothing left to read it against -
        and CR 113.7a says the ability resolves regardless of what happened to
        its source.

        `ability.event` is threaded through here because a non-self-referential
        "it" - Vexing Bauble's "Whenever a player casts a spell, if no mana was
        spent to cast it" - means the *cast spell*, not Vexing Bauble. Without
        the event, `_cast_record_for_clause` falls back to `game.cast_record`
        of the ability's own source, which is the wrong object for exactly the
        clause shape this recheck exists to handle.
        """
        printed = ability.ability
        if not isinstance(printed, TriggeredAbility) or not printed.intervening_if:
            return True
        source = ability.source(self)
        if source is None:
            return True
        return intervening_if_holds(
            self, printed, source, ability.event, source_stamp=ability.source_stamp
        )

    def put_triggers_on_stack(self: "Game") -> list[AbilityOnStack]:
        """Put everything that has triggered onto the stack (CR 603.3, 603.3b).

        CR 603.3b orders them: "each player, in APNAP order, puts each triggered
        ability they control on the stack in any order they choose". The active
        player goes first, so the active player's trigger sits *lowest* and
        resolves *last*. Within one player's abilities the order is that
        player's own choice, put to them by `_order_triggers_by_controller`
        through `machines/decisions.ask_trigger_order`; an unscripted, unasked
        player keeps the order they triggered in, which is what makes a
        scenario reproducible.

        This is the only path in the engine that puts more than one object on
        the stack at once. Every other stack append - a cast spell, an
        activated ability, a single `copy_spell` - is one object, so CR 405.3
        ("if an effect puts two or more objects on the stack at the same time,
        those controlled by the active player are put on lowest, followed by
        each other player's objects in APNAP order") is honoured here, by
        `machines/triggers.apnap_order`, or nowhere - because there is nowhere
        else it applies.

        Targets are chosen here, not when the ability triggered (CR 603.3d).

        A `choose_trigger_targets` answer is consumed by this one batch and no
        other: it is thrown away once every waiting ability has had its turn,
        so a later, separate trigger sharing the same source name (a second
        cast of the same card, or an unrelated delayed trigger printed on the
        same card) is asked fresh rather than inheriting a stale answer.

        Putting an ability on the stack can itself trigger something: CR 115.1c
        makes a targeted ability's targets chosen as it goes on the stack, and
        anything watching "becomes the target of ... an ability" (ward,
        CR 702.21a; Loki, God of Mischief) triggers on that. CR 603.3 puts
        *those* on the stack "the next time a player would receive priority" -
        which has still not happened, since this whole batch runs before
        anybody gets priority - so this drains repeatedly rather than leaving
        them for a later call that a scenario may never make.
        """
        if self.is_over:
            return []  # CR 104.1: the game has ended
        with self._id_allocator_scope():
            self.announce_batched_events()
            placed: list[AbilityOnStack] = []
            # CR 603.8 / CR 704.1a: a state trigger is a triggered ability whose
            # condition is a game state, so it is swept for here too - a state that
            # became true while an ability was resolving (or that was true before
            # anything ever happened, so no event was emitted to sweep on) has still
            # triggered, and CR 603.3 puts it on the stack at this same moment.
            self.pending_triggers.extend(state_triggers_for(self))
            while self.pending_triggers:
                placed.extend(self._put_pending_triggers_on_stack())
                self.pending_triggers.extend(state_triggers_for(self))
            return placed

    def _put_pending_triggers_on_stack(self: "Game") -> list[AbilityOnStack]:
        """One CR 603.3b batch: everything waiting right now, in APNAP order."""
        if not self.pending_triggers:
            return []
        assert self.turn is not None

        waiting, self.pending_triggers = self.pending_triggers, []
        waiting = [item for item in waiting if self.is_in_game(item.controller)]  # CR 800.4d
        ordered = self._order_triggers_by_controller(
            apnap_order(waiting, self._turn_order_from_active())
        )
        placed: list[AbilityOnStack] = []
        for ability in ordered:
            # CR 107.3m: The Ruinous Wrecking Crew's "choose up to X -" counts
            # the X its spell was cast with - 0 when it was never cast.
            modal = modal_trigger_profile(self._etb_x_effect_text(ability, uncast_x=0))
            if modal is not None:
                # CR 603.3c: the mode is announced as the ability is put on the
                # stack, then CR 603.3d/CR 700.2c's targets for the chosen
                # modes only. No mode chosen removes the ability.
                if not self._announce_trigger_modes(ability, modal):
                    continue
                self.stack.append(ability)
                self._emit_ability_becomes_target(ability)
                placed.append(ability)
                continue
            targets = self._targets_for_trigger(ability)
            if targets is None:
                # CR 603.3d: "if a choice is required when the triggered
                # ability goes on the stack but no legal choices can be made
                # for it, ... the ability is simply removed from the stack" -
                # for a mandatory target (`target_minimum` > 0) with no legal
                # candidate at all, that means it never goes on in the first
                # place, not that it goes on choosing nothing.
                continue
            ability.targets = list(targets)
            # CR 603.3d -> CR 601.2d: a divided effect's division is
            # announced with the targets, as it goes on the stack.
            announce_trigger_division(self, ability)
            self.stack.append(ability)
            self._emit_ability_becomes_target(ability)
            placed.append(ability)
        for ability in ordered:
            self.trigger_targets.pop(ability.source_name, None)
            self.trigger_targets.pop(ability.source_name.split("//")[0].strip(), None)
        return placed

    def _etb_x_effect_text(
        self: "Game", ability: AbilityOnStack, *, uncast_x: int | None = None
    ) -> str | None:
        """A triggered ability's effect text with CR 107.3m's X written in:
        "If an object's enters-the-battlefield triggered ability ... refers
        to X, and the spell that became that object as it resolved had a value
        of X chosen for any of its costs, the value of X for that ability is
        the same as the value of X for that spell."

        Ajani's Anguish's own "it deals X damage to any target." `cast_record_
        of` is already CR 400.7d's bridge (its own docstring), keyed by
        `zone_change_stamp`, which a spell resolving into a permanent carries
        across that exact zone change.

        Scoped to a spell whose *own* mana cost carried {X} (CR 107.3a):
        Craterhoof Behemoth's and Yuriko's own ETB triggers define X in their
        own text instead ("where X is the number of creatures you control", CR
        107.3f), which CR 107.3m does not touch at all - substituting the cast
        record's own default `x_value=0` into that text would silently
        overwrite the real, ability-defined X with zero.

        `uncast_x` is the X written in when no spell became the permanent (it
        was put onto the battlefield): 0 (CR 107.3b - nothing chose an X for
        it), or `None` to leave the text alone.
        """
        if not isinstance(ability.ability, TriggeredAbility):
            return None
        effect_text = effect_text_with_named_token_reminder(
            ability.ability.effect, ability.ability.reminder
        )
        return self.etb_x_substituted(ability, effect_text, uncast_x=uncast_x)

    def etb_x_substituted(
        self: "Game", ability: AbilityOnStack, text: str | None, *, uncast_x: int | None = None
    ) -> str | None:
        """`text` (an ETB trigger's effect, or the part its targets are read
        from) with CR 107.3m's X written in - see `_etb_x_effect_text`.

        "Had a value of X chosen for any of its costs" covers an X in an
        additional cost as much as one in the mana cost: Thieving Skydiver's
        "Kicker {X}" (CR 107.3a) is the X its "mana value X or less" reads."""
        if not (
            isinstance(ability.ability, TriggeredAbility)
            and ability.ability.event is TriggerEvent.ENTERS_THE_BATTLEFIELD
            and text
            and re.search(r"\bX\b", text)
        ):
            return text
        source = ability.source(self)
        if source is None or not _costs_carry_x(source):
            return text
        record = self.cast_record_of(source)
        if record is not None:
            return substitute_x(text, record.x_value)
        if uncast_x is not None:
            return substitute_x(text, uncast_x)
        return text

    def _targets_for_trigger(self: "Game", ability: AbilityOnStack) -> list[TargetRef] | None:
        """What this triggered ability targets, as it goes on the stack (CR 603.3d).

        A scripted `choose_trigger_targets(card_name, ...)` answer wins outright
        - it is keyed by name rather than by ability instance on purpose, so
        two simultaneous triggers sharing a name (Ugin, Eye of the Storms'
        pair of "when you cast this spell" lines) both see it. Nothing
        scripted falls through to `_ask_trigger_targets`, which asks this
        ability *instance*, addressed to its own controller.

        `None` (only ever from `_ask_trigger_targets`) means CR 603.3d removed
        this ability from the stack before it was ever placed - see there.
        """
        front = ability.source_name.split("//")[0].strip()
        scripted = self.trigger_targets.get(ability.source_name)
        if scripted is None:
            scripted = self.trigger_targets.get(front)
        if scripted is not None:
            profile, _ = self._trigger_target_profile(ability)
            # Only a count the event fixes ("up to that many target", CR 601.2c
            # via CR 603.3d) is held to here: the scripted answer could not be
            # judged against it when it was recorded, ahead of the event.
            maximum = profile.max_targets
            fixed_by_event = isinstance(ability.ability, TriggeredAbility) and (
                event_count_target_text(ability.ability.text, ability.event) != ability.ability.text
            )
            if (
                fixed_by_event
                and profile.understood
                and maximum is not None
                and len(scripted) > maximum
            ):
                raise ValueError(
                    f"too many targets: {len(scripted)} chosen where {ability.source_name}'s "
                    f"trigger takes at most {maximum}"
                )
            return self.stamp_target_slots(
                profile, list(scripted), ability.controller, ability.source_id
            )
        return self._ask_trigger_targets(ability)

    def _legal_target_candidates(
        self: "Game", profile: TargetingProfile, controller: str, source_id: UUID | None
    ) -> list[Targetable | AbilityOnStack]:
        """Every object or player `profile` could legally land on right now.

        Used only to tell CR 608.2d's "nothing satisfies the restriction"
        apart from "the restriction could not be read" - not a full
        target-choosing implementation, so every legal candidate is returned
        rather than just the first, letting the caller (a live decision, or
        this file's own notice check) pick among them.
        """
        seen: set[UUID] = set()
        candidates: list[Targetable | AbilityOnStack] = []
        for zone_cards in self.shared_zones.values():
            for state in zone_cards:
                if isinstance(state, CardState) and state.id not in seen:
                    seen.add(state.id)
                    candidates.append(state)
        for player in self.players:
            for zone_cards in player.zones.values():
                for state in zone_cards:
                    if state.id not in seen:
                        seen.add(state.id)
                        candidates.append(state)
        for item in self.stack:
            # CR 115.2(b): an activated or triggered ability on the stack is an
            # object a spell or ability may target when it says so (CR 113.1c).
            # Without it, a mandatory "target activated ability" read as having
            # no legal target and the activation was refused (CR 601.2c).
            if isinstance(item, AbilityOnStack) and item.id not in seen:
                seen.add(item.id)
                candidates.append(item)
        if profile.requirements and any(r.allows_players for r in profile.requirements):
            candidates.extend(self.players)
        # CR 702.18a and CR 702.11: printed on the *target*, so the
        # requirement's own `rejects` cannot see them - asked here, of the same
        # `shroud_refusal`/`hexproof_refusal` `TargetingProfile.check` uses, so
        # a live question never offers what the announcement would refuse.
        source = self.find_by_id(source_id) if source_id is not None else None
        return [
            candidate
            for candidate in candidates
            if any(
                requirement.rejects(candidate, controller, self, source_id) is None
                for requirement in profile.requirements
            )
            and self.shroud_refusal(candidate) is None
            and self.hexproof_refusal(candidate, controller, source) is None
        ]

    def why_cannot_target_with_trigger(
        self: "Game", card_name: str, targets: list[object], event: GameEvent | None = None
    ) -> str | None:
        """Why this card's trigger could not target those, or None (CR 601.2c, 603.3d).

        The source is found by name, first among the objects that can
        actually carry a trigger right now - the battlefield and the stack -
        and, failing that, anywhere else in the game (`_find_card_named_
        anywhere`): a scenario very often scripts a trigger's targets ahead
        of casting the card that will fire it (`trigger_targets` is keyed by
        name precisely so this can be done before there is an ability
        object to aim it at), and the ability's own printed text - what this
        method actually validates against - is identical wherever the card
        currently sits. Only when the card cannot be found *anywhere* is the
        choice genuinely left unchecked, the same way an unreadable spell's
        targets are (see `docs/engine-coverage.md`) - not merely because it
        has not been cast yet, which used to let an impossible target sail
        through untouched: real play never asks for this trigger's targets
        until the card *is* on the battlefield or the stack, at which point
        `_ask_trigger_targets` runs this identical `profile_for_text`/
        `TargetingProfile.check` pair for real, so scripting a target this
        method would already refuse was scripting something real play could
        never have accepted either.

        `event` is the trigger event whose count a "up to that many target"
        reads (CR 601.2c via CR 603.3d). A trigger scripted ahead of its event
        has none yet, so that count is read as unbounded here and held to the
        event's own number when the ability goes on the stack
        (`_targets_for_trigger`) - not as the one target a bare "that many"
        would otherwise read as.

        A card may print more than one targeting trigger. The announcement names
        the card, not the ability, so the targets are legal if *any* of its
        triggers would accept them; the first reason is reported when none do.

        Also tried, for each printed trigger: `reflexive_consequence_text`'s
        own reading of a CR 603.12 "`<action>`. When you do, `<consequence>`."
        shape - `profile_for_text(ability.text)` deliberately excludes that
        tail (it belongs to a *different*, reflexively created ability, not
        this one), so without this a card whose only targeted clause is its
        own reflexive consequence - Earthbender Ascension's Landfall trigger,
        "... put a quest counter on this enchantment. When you do, if it has
        four or more quest counters on it, put a +1/+1 counter on target
        creature you control." - had no profile anywhere in this function
        that would ever accept the target `Game.create_reflexive_trigger`
        goes on to ask for once the reflexive ability actually reaches the
        stack, `choose_trigger_targets(card_name, ...)` refuses to record any
        answer for it, and the shortcut cannot be used at all - only a live
        `DecisionKind.CHOOSE_TARGETS` question at resolution can supply it.
        The key `create_reflexive_trigger` puts the reflexive `AbilityOnStack`
        on the stack under is this same `source_name`
        (`Game.create_reflexive_trigger`'s own controller/source_id/source_name
        arguments), so a target recorded here under `card_name` is exactly
        what `_targets_for_trigger` reads back for it.
        """
        source = self._trigger_source_named(card_name) or self._find_card_named_anywhere(card_name)
        if source is None:
            return None
        # `controller_or_owner` (CR 108.4a), not `Game.controller_of`: a card
        # found only by `_find_card_named_anywhere` may not be on the
        # battlefield or the stack at all (CR 109.4 gives a card in a hand,
        # library, or graveyard no controller), and `controller_of` silently
        # answers `active_player` for one of those instead of raising - which
        # was this exact card's own bug: Badgermole Cub scripted from bob's
        # hand read back as alice's (the active player, always seat 0),
        # because "target land you control" was checked against whoever
        # `controller_of` defaults to rather than whoever actually owns the
        # ability being scripted.
        controller = source.controller_or_owner or self.active_player.username

        # `parse_abilities` rather than `triggers_for`'s `triggered_abilities_of`,
        # which keeps only the six trigger conditions the matcher recognises. A
        # trigger the matcher cannot read still announces targets, and Guide of
        # Souls' "Whenever you attack" is exactly that case.
        #
        # `keyword_triggered_abilities` too: CR 702.1's keyword shorthand (Ward,
        # Evoke, Battle cry, ...) never appears in `parse_abilities`' own output
        # at all - it parses as a `KeywordAbility`, and only `machines/keywords.
        # keyword_triggered_abilities` expands it into the `TriggeredAbility`
        # the rule actually means. None of that family needed a target before
        # "Partner with [name]" (CR 702.124j: "target player may search their
        # library ..."), so nothing exercised this gap until then - a scripted
        # `choose_trigger_targets("Evie Frye", ["bob"])` found no targeting
        # trigger here at all and fell through to whatever *other* printed
        # ability the card happened to carry, refusing a perfectly legal target
        # in that unrelated ability's name.
        printed = [
            ability
            for ability in parse_abilities(source.card)
            if isinstance(ability, TriggeredAbility)
        ] + keyword_triggered_abilities(source.card)
        # CR 603.12's reflexive ability is a plain triggered ability once
        # created (`Game.create_reflexive_trigger`), whatever *kind* of
        # ability's text it was carved out of - Agatha's Soul Cauldron's own
        # "{T}: Exile target card from a graveyard. When a creature card is
        # exiled this way, put a +1/+1 counter on target creature you
        # control." is activated, not triggered, so it never reaches
        # `printed` above, and its own outer target (the graveyard card) is
        # addressed through `Game.activate_ability`'s `targets`, not this
        # method - only the reflexive "target creature you control" the
        # `when ... this way,` tail names is this method's business here.
        printed_activated = [
            ability
            for ability in parse_abilities(source.card)
            if isinstance(ability, ActivatedAbility)
        ]
        reasons: list[str] = []
        for ability in printed:
            profile = profile_for_text(
                event_count_target_text(ability.text, event, unscoped_any=True)
            )
            if profile.understood and profile.requirements:
                try:
                    profile.check(list(targets), controller, self, source_id=source.id)
                except ValueError as refusal:
                    reasons.append(str(refusal))
                else:
                    return None
            # The reflexive tail, tried as an *additional* way to accept -
            # never to refuse. `profile_for_text(ability.text)` above already
            # cut this tail away because CR 603.3d has the reflexive ability
            # choose its own target once *it* exists, a separate
            # announcement from this (outer) one's; Guide of Souls' "Whenever
            # you attack, you may pay {E}{E}{E}. When you do, put ... on
            # target attacking creature" prints no target on the outer
            # trigger at all, and `test_the_outer_attack_trigger_has_no_
            # target_of_its_own` pins that a target named for it is accepted
            # unchecked regardless of what the *reflexive* half would want -
            # the "when you do" may never even be reached. So a target this
            # reflexive profile likes is accepted early; one it dislikes adds
            # no reason, and falls through exactly as if there were no
            # reflexive clause to read at all.
            reflexive_text = reflexive_consequence_text(ability.text)
            if not reflexive_text:
                continue
            reflexive_profile = profile_for_text(reflexive_text)
            if not reflexive_profile.understood or not reflexive_profile.requirements:
                continue
            try:
                reflexive_profile.check(list(targets), controller, self, source_id=source.id)
            except ValueError:
                pass
            else:
                return None
        for ability in printed_activated:
            reflexive_text = reflexive_consequence_text(ability.text)
            if not reflexive_text:
                continue
            profile = profile_for_text(reflexive_text)
            if not profile.understood or not profile.requirements:
                continue
            try:
                profile.check(list(targets), controller, self, source_id=source.id)
            except ValueError as refusal:
                reasons.append(str(refusal))
            else:
                return None
        return reasons[0] if reasons else None

    def _before_priority(self: "Game") -> None:
        """Everything that happens before a player would receive priority.

        CR 704.3 checks state-based actions first, then CR 603.3 puts anything
        that has triggered onto the stack, and only then does `PriorityMachine`
        hand priority out.

        **CR 724.1d/724.1f - the owed cleanup.** Every call site of this method
        is a resolution's own final step (see `resolve_top`/`_resolve_ability`),
        which is exactly when CR 608.2m says a spell or ability that called
        `end_the_turn` "will continue to resolve fully" - so if a cleanup step's
        own CR 514.1/514.2 turn-based actions are still owed (`cleanup_owed`),
        they happen first, right here, before the ordinary check below.

        **CR 514.3a - "another cleanup step".** Read in full: "... those
        state-based actions are performed, then those triggered abilities are
        put on the stack, then the active player gets priority. Players may
        cast spells and activate abilities. Once the stack is empty and all
        players pass in succession, another cleanup step begins." Every object
        this method is resolving that was sitting in a cleanup step (this
        method's own tail syncs priority to match, so nothing else could have
        put it there) got onto the stack only because that exception, or
        `cleanup_owed`'s own version of it just above, had already granted
        priority - so finding nothing left pending immediately after resolving
        it is exactly that "stack is empty and all players pass" moment. The
        fix is to pay off one more owed cleanup right away: CR 724.1d's "a new
        cleanup step begins" (ending the turn again from inside a cleanup step
        CR 514.3a had reopened) is the identical event, and reaches here as
        `cleanup_owed` being set once again.

        `was_owed` is what tells the two apart from CR 724.1f's own "if no
        triggered abilities have triggered during this process, no player gets
        priority" case: a cleanup step that owed its very first CR 514.1/514.2
        run and found nothing pending on the one check that followed never
        opened a CR 514.3a round at all, so nothing is owed back either.
        """
        was_owed = self.cleanup_owed
        if was_owed:
            self.cleanup_owed = False
            self.cleanup_step()
        was_in_cleanup = self.turn is not None and self.turn.step is Step.CLEANUP
        self._check_state_based_actions_and_stack_triggers()
        if self.priority is not None:
            self.priority.reset()
        # ... unless the step is one that hands none out (CR 502.4, 514.3). A
        # resolution cannot happen in the untap step at all, but Time Stop's
        # CR 724.1 drops the pointer into cleanup mid-resolution, and priority
        # must not come back on the way out of it.
        self.sync_priority_with_step()
        if was_in_cleanup and not was_owed and not self.step_grants_priority:
            self.cleanup_owed = True
            self._before_priority()

    def resolve_target(self: "Game", target: TargetRef) -> "Targetable | AbilityOnStack | None":
        """What a target reference points at now, or None if it is gone.

        A card that has left the zone it was targeted in, and a player who has
        left the game, are both simply not there any more.

        An **ability** on the stack is looked up too (CR 115.2, 113.1c). It has
        no zone list to walk, so `find_by_id` cannot see it; without this a
        `TargetRef` naming one always resolved to nothing and CR 608.2b removed
        the spell or ability that had legally targeted it. Tishana's Tidebinder
        is the card that needs it.
        """
        if target.is_player:
            username = target.username
            if username is None or not self.is_in_game(username):
                return None
            return self.player(username)
        if target.card_id is None:
            return None
        found = self.find_by_id(target.card_id)
        if found is not None:
            return found
        return self.find_ability_by_id(target.card_id)

    def resolve_targets(self: "Game", spell: StackObject) -> list[Targetable]:
        """The spell's targets that are still legal on resolution (CR 608.2b).

        Cards and players both, in the order they were chosen. An illegal
        target is skipped and the rest of the spell still happens; it is only
        when *every* target is illegal that the spell does not resolve at all,
        which `resolve_top` checks with `spell_fizzles` before getting here.
        """
        return [
            thing
            for target in spell.targets
            if (thing := self.legal_target(spell, target)) is not None
        ]

    def legal_target(
        self: "Game", spell: StackObject, target: TargetRef
    ) -> "Targetable | AbilityOnStack | None":
        """What this target points at, if it is still a legal target (CR 608.2b).

        "A target that's no longer in the zone it was in when it was targeted is
        illegal. Other changes to the game state may cause a target to no longer
        be legal." So a target that has gone is illegal, and so is one the
        spell's own text would no longer accept - a creature that stopped being
        one, or a permanent that changed controller under a "you control" clause.

        The zone-change half of that sentence is CR 400.7: an object that
        moved to a new zone and back is "a new object with no memory of, or
        relation to, its previous existence", even though this engine keeps
        the same `CardState.id` across the move (an Ephemerate-style blink
        while a single-target removal spell targeting the blinked permanent
        sits on the stack is the reported shape - `find_by_id` alone cannot
        tell the two incarnations apart, only `zone_change_stamp` can).
        `target.zone_change_stamp` is `None` when no live object was on hand
        to read one from at announcement (`TargetRef.zone_change_stamp`'s own
        docstring), and a reference this method cannot judge is treated as
        still legal rather than made to fizzle on a guess - the same posture
        already taken for an unparsed restriction, just below.

        Legality is judged by the same parser that checked it at announcement
        (`machines/targeting.py`), so a card whose text the parser cannot read
        is treated as still legal rather than made to fizzle on a guess.

        An **ability** on the stack is checked against its own printed text
        (`ability.ability.text`, the same source `activate_ability` and
        `_ask_trigger_targets` already read with `profile_for_text`) rather
        than a spell's `targeting_profile` - CR 113.1c's ability has no card
        text of its own to look up by name, but it carries its restriction
        right there on the object.
        """
        thing = self.resolve_target(target)
        if thing is None:
            return None

        if (
            isinstance(thing, CardState)
            and target.zone_change_stamp is not None
            and thing.zone_change_stamp != target.zone_change_stamp
        ):
            # CR 608.2b/CR 400.7: the object `find_by_id` just found is a new
            # object, not the one this reference named at announcement.
            return None

        source_card = self._source_card_of(spell)
        if (
            source_card is not None
            and self.protection_refusal(
                thing,
                source_card,
                source_controller=self.controller_of(spell).username,
                is_spell=isinstance(spell, CardState),
                source_state=None if isinstance(spell, CardState) else spell.source(self),
                source_mana_value=(
                    self._protection_characteristics(spell).mana_value
                    if isinstance(spell, CardState)
                    else None
                ),
            )
            is not None
        ):
            # CR 702.16b, checked again here because protection can be gained
            # after a spell was legally announced.
            return None
        if self.shroud_refusal(thing) is not None:
            # CR 702.18a, the same "gained after announcement" recheck as
            # protection just above - a granted shroud makes an already-legal
            # target illegal by the time it would resolve.
            return None
        spell_controller = (
            spell.controller
            if isinstance(spell, AbilityOnStack)
            else self.controller_of(spell).username
        )
        if self.hexproof_refusal(thing, spell_controller, spell) is not None:
            # CR 702.11b/702.11c/702.11d, the same recheck again: hexproof
            # gained in response (Blossoming Defense, Blossoming Calm) makes
            # the target illegal. An ability's source is read with its last
            # known information if it has left (CR 608.2b).
            return None

        if isinstance(spell, AbilityOnStack):
            # `x_value` substituted first, the same reason `activate_ability`
            # and `create_continuous_effect_of_ability` both do it before
            # building a profile off this ability's text - The Mycosynth
            # Gardens' own "target nontoken artifact you control with mana
            # value X" is a real restriction once X is known, not an
            # unreadable one, and a re-check that used the literal "X" would
            # judge every legal target illegal (`comparison_value=None`
            # matches nothing) rather than treat the restriction as read.
            #
            # `cost_announces_x`, not a bare `"{X}" in spell.ability.cost`:
            # CR 107.3a's X is announced by "a mana cost, alternative cost,
            # additional cost, and/or activation cost with an {X}, [-X], or X
            # in it" - a loyalty ability's own variable cost (CR 606.4's
            # printed `"−X"`/`"+X"` loyalty symbol, `LoyaltyCost.variable`)
            # carries no `{X}` mana symbol at all, so the old literal check
            # left every variable-loyalty-cost ability's own targets re-
            # checked against the unsubstituted, literal "X" - which,
            # exactly as the comment above already says, matches nothing and
            # silently drops every legal target. Sorin, Vengeful Bloodlord's
            # own "−X: Return target creature card with mana value X from
            # your graveyard to the battlefield." is the shape this fixes:
            # the ability resolved, paid its loyalty, and then reanimated
            # nothing, because `resolve_targets` filtered its own already-
            # legal target out from under it. `_effect_of` (this same file)
            # already reads the identical `cost_announces_x(ability.ability.
            # cost)` for the same reason on the resolution side; this is that
            # check's own re-legality twin, now reading it the same way.
            ability_text = (
                substitute_x(spell.ability.text, spell.x_value)
                if isinstance(spell.ability, ActivatedAbility)
                and cost_announces_x(spell.ability.cost)
                else spell.ability.text
            )
            # CR 107.3m: an ETB trigger's X is its spell's X, at the recheck
            # as at announcement (`_trigger_target_profile`).
            ability_text = self.etb_x_substituted(spell, ability_text) or ability_text
            # CR 201.5's self-reference, normalized to "this permanent" the
            # same way `_activation_target_text` already normalizes it for
            # the initial announcement (Hope of Ghirapur's own "by Hope of
            # Ghirapur") - `find_by_id` for a still-live source's real
            # supertypes, `legendary=True` (the function's own documented
            # default) once the source is gone and there is nothing left to
            # check.
            ability_source = self.find_by_id(spell.source_id) if spell.source_id else None
            ability_legendary = (
                Supertype.LEGENDARY in ability_source.card.supertypes
                if ability_source is not None
                else True
            )
            ability_text = self_normalized_effect_text(
                spell.source_name, ability_text, legendary=ability_legendary
            )
            profile = (
                profile_for_text(ability_text)
                .for_event_player(_that_player_of(spell))
                .for_defending_player(self._defending_player_of(spell))
            )
            if not profile.understood or not profile.requirements:
                return thing
            caster = spell.controller
            if any(
                requirement.rejects(thing, caster, self, spell.source_id) is None
                for requirement in profile.requirements
            ):
                return thing
            return None

        record = self.cast_record_of(spell)
        # CR 702.113b: an awakened spell also targets "target land you control".
        profile = with_keyword_spell_ability_target(
            self._resolution_profile(spell),
            record.keyword if record is not None and record.keyword_cost_paid else None,
        )
        if not profile.understood or not profile.requirements:
            return thing
        caster = spell.controller or self.active_player.username
        # The game is handed over because not every restriction is a
        # characteristic: CR 109.3 lists what a characteristic is and being in
        # combat is not among them. "Target attacking creature" is answered off
        # `Game.combat` (CR 508.1k, 509.1g), and CR 511.3 taking everything out
        # of combat is exactly the "other changes to the game state may cause a
        # target to no longer be legal" of CR 608.2b.
        if any(
            requirement.rejects(thing, caster, self) is None for requirement in profile.requirements
        ):
            return thing
        return None

    def targetable_objects(self: "Game") -> list[Any]:
        """Every object a target could name right now: every player, every
        card in a public zone (CR 400.2 - the battlefield, every graveyard,
        every exile), and every spell or ability on the stack.

        This is engine knowledge, not API knowledge - moved out of
        `magic_cards_model_api.affordances._all_targetables`, which hardcoded
        the same walk, so `legal_targets` below and any future caller share
        one answer to "what could a target possibly name" instead of the api
        maintaining a second copy that could drift from the engine's own
        rules. A hand or library card is deliberately absent - nothing in
        this pool targets one, and enumerating a hidden zone is exactly what
        the visibility layer exists to prevent.
        """
        things: list[Any] = list(self.players)
        for zone in (Zone.BATTLEFIELD, Zone.GRAVEYARD, Zone.EXILE):
            for state in self.shared_zones.get(zone, []):
                if isinstance(state, CardState):
                    things.append(state)
        # The battlefield and exile are shared zones (CR 400.1: "The other
        # zones are shared by all players"), already walked once each above
        # via `self.shared_zones` - `Player.zones` never holds either one.
        # Only the graveyard is a real per-player zone. `Player.cards_in` was
        # `zones.setdefault(zone, [])`, so asking it for `Zone.BATTLEFIELD`/
        # `Zone.EXILE` here used to both return nothing (every permanent and
        # exiled card was already added above, so nothing was lost) and
        # permanently add two spurious empty keys to every player's own
        # serialized `zones` as a side effect of a read-only query - a
        # documented pure query mutating the game it was asked about. It
        # raises `SharedZoneError` now rather than answering at all.
        for player in self.players:
            things.extend(player.cards_in(Zone.GRAVEYARD))
        things.extend(self.stack)
        return things

    def legal_targets(
        self: "Game",
        source: CardState,
        caster: str,
        *,
        ability_index: int | None = None,
        modes: list[int] | None = None,
        x_value: int | None = None,
        spell_face: str | None = None,
    ) -> tuple[tuple[Any, ...], ...]:
        """Every legal target for each requirement `source` would announce
        right now, one tuple per requirement (CR 601.2c) - the enumerating
        cousin of `legal_target` above, which only rechecks one target already
        chosen (CR 608.2b).

        `spell_face` names the half being cast (CR 709.3, CR 715.3), and is
        forwarded untouched to `_announcement_profile` so the candidate list
        can never disagree with the `Action.target_slots` built from the same
        call - which is the whole point of a candidate list. Without it, both
        halves of Wear // Tear offered the same artifacts.

        `TargetRequirement.rejects` is the single predicate both this and
        `legal_target` call, so a candidate list built here can never disagree
        with what an actual announcement would accept or refuse - the same
        argument `could_pay_mana_cost` already makes for `auto_tap`
        (`machines/cost.py`).

        Returns `()` when the profile could not be read or names no
        requirements at all (an unmodelled targeting phrase, or a card with
        none) - an empty tuple of tuples rather than a tuple of empty ones, so
        a caller can tell "nothing here targets" from "every requirement
        happens to have no legal candidate right now".
        """
        profile = self._announcement_profile(
            source,
            ability_index=ability_index,
            modes=modes,
            x_value=x_value,
            spell_face=spell_face,
        )
        if not profile.understood or not profile.requirements:
            return ()
        pool = self.targetable_objects()
        result: list[tuple[Any, ...]] = []
        for requirement in profile.requirements:
            legal = tuple(
                thing
                for thing in pool
                if not (thing is source and source.zone is not Zone.STACK)
                and requirement.rejects(thing, caster, self, source.id) is None
                # Printed on the target (CR 702.18a, CR 702.11), so asked of
                # the same refusals `TargetingProfile.check` uses.
                and self.shroud_refusal(thing) is None
                and self.hexproof_refusal(thing, caster, source) is None
            )
            result.append(legal)
        return tuple(result)

    def legal_actions(
        self: "Game", player: str, *, pending: PendingDecision | None = None
    ) -> list[Action]:
        """Every legal action `player` could take right now -
        `machines.legal_actions.legal_actions` bound here, since three of
        `machines/cost.py`'s own docstrings already cite it as `Game.
        legal_actions`. See that module's own docstring for what "legal"
        means (never gated on affordability), what a pending `Decision` does
        to the answer, and what is deliberately not enumerated.
        """
        from ...machines.legal_actions import legal_actions as _legal_actions

        return _legal_actions(self, player, pending=pending)

    def _resolution_profile(self: "Game", spell: CardState) -> "TargetingProfile":
        """What this spell may legally be targeting now (CR 608.2b, 700.2c).

        For an ordinary spell that is simply the card's text. For a **modal**
        one it is not: `targeting_profile` reports `understood=False` for every
        modal card on purpose, because CR 700.2c makes the targets depend on the
        modes - "if a spell or ability targets one or more targets only if a
        particular mode is chosen for it, its controller will need to choose
        those targets only if they chose that mode. Otherwise, the spell or
        ability is treated as though it did not have those targets."

        So the modes announced during casting are read back off `cast_records`
        and `profile_for_modes` is asked instead. Without them the spell stays
        unchecked, which is the old behaviour and the honest one: a modal spell
        whose modes were never recorded cannot be judged.

        A **non-modal** spell whose own mana cost has `{X}` (Postmortem
        Lunge's "target creature card with mana value X") gets the same
        substitution `machines/casting.Casting.targeting` already applies at
        announcement - `targeting_profile(spell.card)` alone never resolves a
        bare "X" (CR 107.3a's value is not part of the card's own printed
        text), so without this the CR 608.2b recheck this method exists for
        would refuse every target forever, on a card the caster legally
        targeted moments earlier.

        A **split card's** (CR 709) chosen half reads its own text too, the
        same case `Casting.targeting`'s own docstring explains -
        `targeting_profile(spell.card)` always reads the combined printing's
        *front* half (`Card.front_oracle_text`), never the half actually
        cast. Left unfixed, this recheck refused every legal target on a
        split card's back half forever - the CR 608.2b recheck this method
        exists for judging the back half's own restriction against the
        front half's - found auditing Repudiate // Replicate's Replicate
        half ("Create a token that's a copy of target creature you
        control.") against Wear // Tear's own front-face-only "target
        artifact" requirement. `spell.oracle_text` already reads the chosen
        half while the spell is on the stack (`CardState.up_face`), so this
        only has to stop *discarding* that in favour of the printing's front
        half.

        An **Adventure** spell reads the same way and for the same reason:
        CR 715.3b ("while on the stack as an Adventure, the spell has only
        its alternative characteristics") is CR 709.3b word for word, and
        `CardState.up_face` already covers both layouts. `face_played` is set
        only for those two (`machines/casting.Casting.cast`), so it is the
        whole discriminator here - a modal-DFC or transforming spell never
        reaches this branch.
        """
        record = self.cast_record_of(spell)
        if record is not None and record.modes:
            try:
                return profile_for_modes(spell.card, record.modes, record.x_value or None)
            except ValueError:
                # Not a modal card after all; fall through to its plain text.
                pass
        kicked_alternative = kicked_instead_target_text(spell.oracle_text or "")
        if kicked_alternative is not None:
            # CR 601.2c's kicked targets, rechecked against the same sentence
            # they were chosen under (CR 608.2b).
            kicked = record is not None and record.kicked > 0
            return profile_for_text(kicked_alternative[1 if kicked else 0])
        per_kick = per_kick_target_text(
            spell.oracle_text or "", record.kicked if record is not None else 0
        )
        if per_kick is not None:
            # CR 608.2b's recheck of "choose another target for each time this
            # spell was kicked": one requirement per kick, as announced.
            if record is not None and "{X}" in (spell.mana_cost or ""):
                per_kick = substitute_x(per_kick, record.x_value)
            return spell_profile_for_text(per_kick, spell.card)
        teamwork_alternative = teamwork_instead_target_text(spell.oracle_text or "")
        if teamwork_alternative is not None:
            # The identical CR 601.2c/608.2b recheck for Teamwork's own
            # additional cost (`machines/teamwork.py`).
            teamwork = record is not None and record.cast_using_teamwork
            return profile_for_text(teamwork_alternative[1 if teamwork else 0])
        if spell.fused and spell.card.card_faces and len(spell.card.card_faces) == 2:
            # CR 702.102b/709.4b: the same combined-profile shape `Casting.
            # targeting` builds at announcement, rebuilt here for CR 608.2b's
            # recheck - a fused Wear // Tear's artifact target is judged
            # against Wear's own restriction and its enchantment target
            # against Tear's, never against just one half's text.
            left, right = spell.card.card_faces[0], spell.card.card_faces[1]
            left_profile = profile_for_text(left.oracle_text or "")
            right_profile = profile_for_text(right.oracle_text or "")
            return TargetingProfile(
                requirements=(*left_profile.requirements, *right_profile.requirements),
                understood=left_profile.understood and right_profile.understood,
            )
        if spell.face_played is not None and spell.card.layout in (
            Layout.SPLIT,
            Layout.ADVENTURE,
        ):
            return face_spell_profile(spell.up_face, spell.oracle_text)
        if record is not None and "{X}" in (spell.mana_cost or ""):
            return profile_for_text(substitute_x(spell.oracle_text, record.x_value))
        return targeting_profile(spell.card)

    # -- protection (CR 702.16) --------------------------------------------

    def _source_card_of(self: "Game", spell: StackObject) -> "Card | None":
        """The card a stack object's protection quality is judged against.

        For a spell that is the card itself; for an ability it is the card the
        ability came from, because CR 702.16b speaks of "abilities from a source
        with the stated quality" rather than of the ability's own type.
        """
        if isinstance(spell, CardState):
            return spell.card
        source = spell.source(self)
        return source.card if source is not None else None

    def protection_refusal(
        self: "Game",
        target: "Targetable | AbilityOnStack",
        source: "Card",
        *,
        source_controller: str | None = None,
        is_spell: bool = False,
        source_state: CardState | None = None,
        source_mana_value: float | None = None,
    ) -> str | None:
        """Why protection stops this source touching this target, or None (CR 702.16b).

        "A permanent or player with protection can't be targeted by spells with
        the stated quality and can't be targeted by abilities from a source with
        the stated quality."

        The quality is matched by `source_has_quality`, which reads both
        flavours CR 702.16a names - "This quality is usually a color (as in
        'protection from black') but can be any characteristic value or
        information" - so a colour quality refuses a targeting spell here
        exactly as it prevents that source's damage in `protection_from_damage`.
        Reading only the card-type half here was a real split: Lightning Bolt
        could still be *announced* at a creature with protection from red, and
        only its damage was prevented on resolution, which is CR 702.16e doing
        CR 702.16b's job.

        `is_spell` is CR 112.1's "spell" quality (Emrakul, the World Anew's
        own "protection from spells") - true exactly when `source` is the
        card behind a spell rather than an ability's, which every caller
        already knows (it is what tells `source` apart from an ability's own
        source card in the first place) and passes through.

        `source_state` is the live `CardState` behind an ability's source
        permanent, for "permanents that were cast this turn" (Emrakul's other
        quality) - a bare `Card` cannot answer whether *this* object was cast
        this turn, only `Game.was_cast_this_turn` can, and it needs the live
        object. `None` for a spell (never a permanent, CR 110.1) and for any
        caller that has not looked one up.

        A quality this engine cannot read is not enforced - see
        `docs/engine-coverage.md`.

        A **player** target is answered by `Player.protection_refusal`, which
        matches the card-name flavour off `Player.protection_from` (Runed
        Halo's CR 614.12a chosen name), unioned with the grants currently on
        the battlefield - see `player_protection_qualities`.
        """
        target = self._targeted_thing(target)
        if isinstance(target, Player):
            return self._player_protection_refusal(
                target,
                source,
                source_controller,
                is_spell=is_spell,
                source_state=source_state,
                source_mana_value=source_mana_value,
            )
        if not isinstance(target, CardState):
            return None
        for quality in self._effective_protection_qualities(target):
            if self._player_quality_protects(
                target, quality, source_controller
            ) or self.source_has_quality_of_card(
                source,
                quality,
                is_spell=is_spell,
                source_state=source_state,
                source_mana_value=source_mana_value,
            ):
                return (
                    f"{target.name} has protection from {quality}, so {source.name} "
                    f"cannot target it (CR 702.16b)"
                )
        return None

    def _targeted_thing(self: "Game", target: Any) -> Any:
        """A target as the object or player it names: a username becomes the
        `Player`, a `TargetRef` or id the object it points at. Anything else is
        returned unchanged - the refusals below read only a `CardState` or a
        `Player` and let every other shape through."""
        if isinstance(target, str):
            try:
                return self.player(target)
            except KeyError:
                return target
        if isinstance(target, TargetRef):
            return self.resolve_target(target) or target
        if isinstance(target, UUID):
            return self.find_by_id(target) or target
        return target

    def shroud_refusal(self: "Game", target: Any) -> str | None:
        """Why shroud stops this target being targeted at all, or None (CR 702.18).

        CR 702.18a: "Shroud is a static ability. 'Shroud' means 'This
        permanent or player can't be the target of spells or abilities.'"
        Unlike hexproof (CR 702.11b's "your opponents control"), there is no
        controller exception at all: a shrouded permanent's own controller
        cannot target it either, so this needs no `source` to compare
        against - CR 702.18b's redundancy rule is the only thing that varies
        with *how many* instances there are, never with who is asking.

        A permanent's shroud is read off `has_keyword`, the computed-board
        reader, so a printed "Shroud" line and one granted in layer 6 (CR
        613.1f) are the same keyword. A **player's** is `player_has_shroud`:
        a static "You have shroud." on a permanent they control, or an
        effect's grant on `Player.targeting_grants`.
        """
        target = self._targeted_thing(target)
        if isinstance(target, Player):
            if not self.player_has_shroud(target):
                return None
            return (
                f"{target.username} has shroud, so they can't be the target of spells "
                f"or abilities (CR 702.18a)"
            )
        if not isinstance(target, CardState):
            return None
        if target.zone is not Zone.BATTLEFIELD:
            # CR 702.18a speaks of a permanent, and a permanent is on the
            # battlefield (CR 110.1).
            return None
        if not has_keyword(target, "shroud", self):
            return None
        return (
            f"{target.name} has shroud, so it can't be the target of spells or "
            f"abilities (CR 702.18a)"
        )

    def hexproof_refusal(
        self: "Game", target: Any, source_controller: str, source: Any
    ) -> str | None:
        """Why hexproof stops `source_controller`'s spell or ability targeting
        this, or None (CR 702.11).

        CR 702.11b: "'Hexproof' on a permanent means 'This permanent can't be
        the target of spells or abilities your opponents control.'" CR
        702.11c says the same of a player. CR 702.11d: "'Hexproof from
        [quality]' on a permanent means 'This permanent can't be the target of
        [quality] spells your opponents control or abilities your opponents
        control from [quality] sources.'" CR 702.11f makes "from A and from B"
        two abilities and CR 702.11h makes repeats redundant.

        The one hexproof vocabulary: `TargetingProfile.check` asks it at
        announcement for spells and for activated and triggered abilities
        alike, `_legal_target_candidates` and `legal_actions` filter live
        candidates through it, and `legal_target` asks it again at CR 608.2b's
        resolution recheck - so hexproof gained in response makes a target
        illegal.

        `source` is what "[quality]" is judged on: the spell (a `CardState` on
        the stack, or about to be), or an ability - an `AbilityOnStack`, or its
        source object - whose source is read with computed characteristics on
        the battlefield and its last known information once it has left
        (CR 113.7a, CR 608.2b); see `_quality_characteristics_of`. With no
        `source`, only plain hexproof is decided.

        The exception is for the target's own controller only: CR 702.11b's
        "your opponents".
        """
        target = self._targeted_thing(target)
        from ...machines.protection_statics import static_target_refusal

        restricted = static_target_refusal(self, target, source_controller, source)
        if restricted is not None:
            return restricted
        if isinstance(target, Player):
            plain, qualities = self.player_hexproof(target)
            protected = target.username
            pronoun = "them"
            rule_plain = "CR 702.11c"
        elif isinstance(target, CardState):
            if target.zone is not Zone.BATTLEFIELD:
                # CR 702.11b speaks of a permanent, and a permanent is on the
                # battlefield (CR 110.1).
                return None
            plain, qualities = self.hexproof_abilities(target)
            protected = self.controller_of(target).username
            pronoun = "it"
            rule_plain = "CR 702.11b"
        else:
            return None
        if not plain and not qualities:
            return None
        if protected == source_controller:
            return None
        from ...machines.targeting import ignores_hexproof

        if ignores_hexproof(self, target, source_controller):
            # CR 702.11e: "as though it didn't have hexproof" - every hexproof
            # ability, "hexproof from" included (`machines/targeting.py`).
            return None
        name = target.username if isinstance(target, Player) else target.name
        if plain:
            return (
                f"{name} has hexproof, so {source_controller} - an opponent of its "
                f"controller - cannot target {pronoun} ({rule_plain})"
            )
        characteristics = self._quality_characteristics_of(source)
        if characteristics is None:
            return None
        colors, types, subtypes, supertypes, source_name = characteristics
        for quality in qualities:
            if has_quality(
                quality, colors=colors, types=types, subtypes=subtypes, supertypes=supertypes
            ):
                return (
                    f"{name} has hexproof from {quality}, so {source_controller} - an "
                    f"opponent of its controller - cannot target {pronoun} with "
                    f"{source_name} (CR 702.11d)"
                )
        return None

    def hexproof_abilities(self: "Game", target: CardState) -> tuple[bool, list[str]]:
        """Whether this permanent has plain hexproof, and every quality it has
        hexproof from (CR 702.11b, CR 702.11d, CR 702.11f, CR 702.11h).

        Read off the permanent's ability text on the computed board, so a
        hexproof granted in layer 6 (Blossoming Defense, Dragonfire Blade)
        counts and one an effect removed does not (CR 613.5); off the object's
        own text when it has no computed board. A face-down permanent has no
        text at all (CR 708.2) and so has neither.
        """
        try:
            lines = list(self.characteristics_of(target).abilities)
        except KeyError:
            lines = target.oracle_text.splitlines()
        from ...machines.protection_statics import hexproof_suppressed

        if hexproof_suppressed(self, target):
            # CR 702.11e: "lose hexproof" takes every "hexproof from" with it,
            # and "can't have or gain" keeps a later grant from returning it.
            return False, []
        return hexproof_abilities_in(lines)

    def player_hexproof(self: "Game", player: Player) -> tuple[bool, list[str]]:
        """Whether this player has plain hexproof, and every quality they have
        hexproof from (CR 702.11c, CR 702.11d, CR 702.11h) - static grants
        from permanents they control, plus effect grants on
        `Player.targeting_grants`."""
        plain = False
        qualities: list[str] = []
        sources = [
            (keyword, list(found)) for keyword, found in self._player_static_keyword_grants(player)
        ]
        sources.extend(
            (grant.keyword, [] if grant.quality is None else [grant.quality])
            for grant in player.targeting_grants
        )
        for keyword, found in sources:
            if keyword != "hexproof":
                continue
            if not found:
                plain = True
            for quality in found:
                if quality not in qualities:
                    qualities.append(quality)
        return plain, qualities

    def player_has_shroud(self: "Game", player: Player) -> bool:
        """CR 702.18a's "or player": a static "You have shroud." on a permanent
        they control, or an effect grant on `Player.targeting_grants`."""
        if any(grant.keyword == "shroud" for grant in player.targeting_grants):
            return True
        return any(keyword == "shroud" for keyword, _ in self._player_static_keyword_grants(player))

    def _player_protection_refusal(
        self: "Game",
        target: Player,
        source: "Card",
        source_controller: str | None = None,
        *,
        is_spell: bool = False,
        source_state: CardState | None = None,
        source_mana_value: float | None = None,
    ) -> str | None:
        """Why a *player's* protection stops `source` targeting them (CR 702.16b).

        Two sources of quality, unioned: what the player carries on
        `Player.protection_from` - the card-name flavour, which
        `Player.protection_refusal` matches - and what the battlefield is
        granting them right now (`player_protection_qualities`), which is read
        fresh so the grant ends with its permanent (CR 604.2).
        """
        refusal = target.protection_refusal(source)
        if refusal is not None:
            return refusal
        for quality in self.player_protection_qualities(target.username):
            # CR 702.16k: "each of your opponents" is every object that player
            # controls - the source's controller decides, not its characteristics.
            from_opponent = (
                source_controller is not None
                and _EACH_OPPONENT_PROTECTION_QUALITY.match(quality.strip())
                and source_controller != target.username
            )
            if (
                from_opponent
                or quality == source.name
                or self.source_has_quality_of_card(
                    source,
                    quality,
                    is_spell=is_spell,
                    source_state=source_state,
                    source_mana_value=source_mana_value,
                )
            ):
                return (
                    f"{target.username} has protection from {quality}, so {source.name} "
                    f"cannot target them (CR 702.16b)"
                )
        return None

    def player_protection_qualities(self: "Game", username: str) -> list[str]:
        """Every quality the battlefield currently grants this *player*
        protection from (CR 702.16a, CR 613.10).

        CR 613.10: "Some continuous effects affect players rather than objects.
        For example, an effect might give a player protection from red." That
        is this, and it is deliberately **not** a CR 613 layer: the layers write
        characteristics onto objects, and a player is not an object, so
        `machines/layers.py`'s permanent-only sweep has nowhere to put it.

        Read fresh from the battlefield on every call rather than latched onto
        the player, because CR 604.2 bounds a static ability's continuous effect
        to while its source is on the battlefield - a Runed Halo that leaves
        must take its protection with it, and a value written once onto
        `Player.protection_from` would outlive its source.
        """
        qualities: list[str] = []
        from ...machines.protection_statics import player_protection_qualities_of

        board = self.computed_board()
        for permanent in self.battlefield:
            if self.controller_of(permanent).username != username:
                continue
            for quality in player_protection_qualities_of(self, permanent, board, username):
                if quality not in qualities:
                    qualities.append(quality)
            for line in (permanent.card.oracle_text or "").split("\n"):
                if not _PLAYER_PROTECTION_FROM_CHOSEN_NAME.match(line.strip()):
                    continue
                chosen = permanent.choice
                # The line says "the chosen **card name**", so only a
                # CR 614.12a card-name choice answers it - a colour choice on
                # some other permanent is not this quality.
                if chosen is None or chosen.kind is not ChoiceKind.CARD_NAME:
                    continue
                if chosen.value and chosen.value not in qualities:
                    qualities.append(chosen.value)
        return qualities

    def protection_quality_against(
        self: "Game", target: CardState, source: CardState
    ) -> str | None:
        """The quality `target` has protection from that `source` has, or None.

        The shared question behind CR 702.16c ("can't be enchanted by Auras
        that have the stated quality"), CR 702.16d ("can't be equipped by
        Equipment that have the stated quality") and CR 702.16f ("Attacking
        creatures with protection can't be blocked by creatures that have the
        stated quality"): each asks it of a *permanent* source, so the source's
        qualities are read the way `source_has_quality` reads a damage
        source's - computed on the battlefield (CR 613.5), printed elsewhere -
        and the target's protection is `_effective_protection_qualities`', its
        printed protection plus any granted in layer 6 (CR 613.1f).
        """
        source_controller = self.controller_of(source).username
        for quality in self._effective_protection_qualities(target):
            if self._player_quality_protects(
                target, quality, source_controller
            ) or self.source_has_quality(source, quality):
                return quality
        return None

    def _effective_protection_qualities(self: "Game", target: CardState) -> list[str]:
        """Every quality `target` has protection from right now: its own printed
        text plus anything granted to it by another static ability (CR 613.1f).

        Akroma's Memorial's "creatures you control have ... protection from
        black and from red" is layer 6, not the permanent's own printing, so
        `protection_qualities(target.card)` alone misses it - it only reads
        what `machines/layers.py` left in `Characteristics.abilities` as a
        "Protection from <quality>" line, the same way `combat.has_keyword`
        reads a granted keyword off the same list. A permanent not on the
        battlefield (a spell on the stack, say) has no computed board to ask,
        so only its own printed protection applies there.
        """
        # The face that is up (CR 710.2, CR 712.8d): a flip card's protection
        # sits on its flipped half only.
        qualities = _qualities_from_text(target.oracle_text)
        if target.zone is Zone.BATTLEFIELD:
            try:
                characteristics = self.characteristics_of(target)
            except KeyError:
                characteristics = None
            if characteristics is not None:
                for line in characteristics.abilities:
                    for quality in _qualities_from_text(line):
                        if quality not in qualities:
                            qualities.append(quality)
        return qualities

    def why_cannot_target(self: "Game", spell: StackObject, target: Targetable) -> str | None:
        """Why this stack object may not target that, as far as protection goes.

        CR 601.2c chooses targets and CR 608.2b rechecks them; this answers the
        protection half of both questions. `Casting.choose_targets` does not
        consult it yet - `machines/targeting.py` reads the *caster's* text and
        has nothing to say about the target's - so announcement is still
        unchecked and only `legal_target` enforces it. See
        `docs/engine-coverage.md`.
        """
        source = self._source_card_of(spell)
        if source is None:
            return None
        return self.protection_refusal(
            target,
            source,
            source_controller=self.controller_of(spell).username,
            is_spell=isinstance(spell, CardState),
            source_state=None if isinstance(spell, CardState) else spell.source(self),
            source_mana_value=(
                self._protection_characteristics(spell).mana_value
                if isinstance(spell, CardState)
                else None
            ),
        )

    def resolve_card_targets(self: "Game", spell: StackObject) -> list[CardState]:
        """Just the card targets, for effects that cannot touch a player."""
        return [thing for thing in self.resolve_targets(spell) if isinstance(thing, CardState)]

    def _protection_characteristics(self: "Game", source: CardState) -> Characteristics:
        """The characteristics a damage, blocking or attachment source is asked
        about (CR 702.16a): computed on the battlefield (CR 613.5), the printed
        ones elsewhere - changeling's creature types included (CR 702.73a) -
        with a spell's mana value counting the X it was cast with (CR 202.3e)."""
        if source.zone is Zone.BATTLEFIELD:
            return self.characteristics_of(source)
        mana_value = source.mana_value
        if source.zone is Zone.STACK:
            mana_value += (source.mana_cost or "").count("{X}") * self.cast_record(source).x_value
        return Characteristics(
            card_id=source.id,
            name=source.name,
            mana_value=mana_value,
            supertypes=source.supertypes,
            types=source.types,
            subtypes=source.subtypes,
            colors=source.colors,
        )

    def protection_from_damage(self: "Game", event: ReplaceableEvent) -> str | None:
        """Why protection prevents this damage, or None (CR 702.16e).

        "Any damage that would be dealt by sources that have the stated quality
        to a permanent or player with protection is prevented."

        Damage with no known source is never prevented here: CR 702.16e asks
        about the source's qualities, and an anonymous source has none to check.

        The rule says "to a permanent **or player** with protection", so a
        damage event aimed at a player is read the same way, against the
        qualities that player holds (`Player.protection_from`, the card-name
        flavour) and the ones the battlefield grants them right now
        (`player_protection_qualities`).
        """
        if event.kind is not EventKind.DAMAGE or event.source is None:
            return None
        if event.card is None:
            return self._player_protection_from_damage(event)
        source_controller = self.controller_of(event.source).username
        for quality in self._effective_protection_qualities(event.card):
            if self._player_quality_protects(
                event.card, quality, source_controller
            ) or self.source_has_quality(event.source, quality):
                return (
                    f"{event.card.name} has protection from {quality}, so damage from "
                    f"{event.source.name} is prevented (CR 702.16e)"
                )
        return None

    def _player_protection_from_damage(self: "Game", event: ReplaceableEvent) -> str | None:
        """CR 702.16e's player half: damage from a source with the stated
        quality, aimed at a player with protection from it, is prevented."""
        player = event.player
        if player is None or event.source is None:
            return None
        qualities = list(player.protection_from)
        for quality in self.player_protection_qualities(player.username):
            if quality not in qualities:
                qualities.append(quality)
        source_controller = self.controller_of(event.source).username
        for quality in qualities:
            if (
                (
                    _EACH_OPPONENT_PROTECTION_QUALITY.match(quality.strip())
                    and source_controller != player.username
                )
                or quality == event.source.name
                or self.source_has_quality(event.source, quality)
            ):
                return (
                    f"{player.username} has protection from {quality}, so damage from "
                    f"{event.source.name} is prevented (CR 702.16e)"
                )
        return None

    def counter(
        self: "Game",
        spell: StackObject,
        *,
        to_exile: bool = False,
        to_library: Literal["top", "bottom"] | None = None,
    ) -> StackObject:
        """Counter a spell or an ability on the stack: it never resolves (CR 701.6).

        `to_library` sends a countered spell to the top or the bottom of its
        owner's library instead - Memory Lapse's "put it on top of its owner's
        library instead of into that player's graveyard" - through
        `put_cards_into_library`, one CR 401.1 instruction every player saw
        (CR 400.2).

        CR 113.9: an activated or triggered ability on the stack is not a spell,
        but it can still be countered by an effect that counters abilities. It
        goes nowhere when it is - there is no card behind it (CR 405.1) - while a
        countered spell is put into its owner's graveyard.

        `to_exile` is Force of Negation's and Delay's own override - "exile it
        instead of putting it into its owner's graveyard" - read by
        `machines/effects.py`'s paired clause parsers off the card's second
        sentence. It moves the card straight to the shared exile zone rather
        than through `put_into_graveyard`'s own CR 614 replacement check,
        because the card was never headed for a graveyard to begin with; the
        card's own text is what is redirecting it, not a separate replacement
        effect watching for the move.

        Countering is a trigger event in its own right (CR 701.6a is the verb,
        CR 603.10e the look back in time), which is why the event is emitted
        after the spell has moved to its graveyard (or exile): the subject is
        found where it went, and the trigger reads it as it last existed on
        the stack.

        **"This spell can't be countered" is enforced here**, and here only.
        CR 113.6g: "An object's ability that states it can't be countered or
        can't be copied functions on the stack", so the ability is live exactly
        while the spell this method was handed is sitting on the stack.
        CR 701.6a is the verb it makes impossible - "to counter a spell or
        ability means to cancel it, removing it from the stack" - so the
        refusal is simply that the removal does not happen: the object is
        returned untouched, still on the stack, and **no** counter event is
        emitted, because nothing was countered for a trigger to watch.

        **Veil of Summer's "Spells you control can't be countered this
        turn"** is the identical refusal from a different source: not the
        spell's own printed or granted ability (`cannot_be_countered`), but a
        recorded CR 611.2c effect `spell_protected_from_countering` reads off
        `casting_rule_effects` - CR 101.2 gives either "can't" the same
        precedence, so the two checks are tried together and either one
        alone is enough to refuse the counter.

        The guard sits above the `to_exile` branch on purpose. Force of
        Negation's and Delay's "exile it instead of putting it into its owner's
        graveyard" is a rider on the countering, not an alternative to it; if
        the countering cannot happen, there is no graveyard-bound move for the
        rider to redirect, so an uncounterable spell is not exiled either.

        The counterspell that failed is not refused or rewound anywhere - it
        was legally cast and legally resolved (CR 608.2b knows nothing about
        counterability) and simply fails to do the one thing it says.
        """
        with self._id_allocator_scope():
            if spell not in self.stack:
                raise ValueError(f"{spell.name} is not on the stack")
            if (
                cannot_be_countered(spell)
                or conditionally_cannot_be_countered(self, spell)
                or spell_protected_from_countering(self, spell)
            ):
                return spell
            free_player: str | None = None
            free_source = ""
            if isinstance(spell, CardState) and not to_exile and to_library is None:
                # CR 701.6a / CR 614.1a: "if a spell or ability you control
                # would counter a spell, instead exile ..." (Guile).
                resolving = self.resolving
                event = ReplaceableEvent(
                    kind=EventKind.COUNTER_SPELL,
                    card=spell,
                    origin=Zone.STACK,
                    destination=Zone.GRAVEYARD,
                    cause_controller=resolving.controller if resolving is not None else None,
                )
                apply_replacements(self, event)
                if event.destination is Zone.EXILE:
                    to_exile = True
                    free_player = event.free_play_player
                    free_source = event.free_play_source
            self.stack.remove(spell)
            if isinstance(spell, CardState):
                if to_library is not None:
                    self.put_cards_into_library([spell], to_bottom=to_library == "bottom")
                elif to_exile:
                    self._take_out_of_every_zone(spell)
                    self.combat.remove(spell.id)  # CR 506.4
                    spell.move_to(Zone.EXILE)
                    self.exile.append(spell)
                else:
                    self.put_into_graveyard(spell)
                # Same cleanup `resolve_top` does on every other way off the
                # stack: a countered spell will not be read again through the
                # normal fast-forward paths, and a `CastRecord` this module can no
                # longer answer for now fails an intervening *if* closed
                # (`machines/triggers._cast_record_for_clause`) instead of a
                # lingering record being misread as "nothing was spent".
                self.forget_cast_record(spell)
                if free_player is not None and spell.zone is Zone.EXILE:
                    # ", you may play that card without paying its mana cost":
                    # carried out as the countering effect resolves (CR 608.2g).
                    self.may_cast_during_resolution(
                        spell,
                        free_player,
                        prompt=f"play {spell.name} without paying its mana cost",
                        source=free_source,
                        source_id=None,
                        source_name=free_source,
                        rule="CR 608.2g",
                        play=True,
                    )
            self.emit(
                GameEvent(
                    event=TriggerEvent.SPELL_IS_COUNTERED,
                    subject_id=spell.id,
                    subject_name=spell.name,
                    subject_controller=spell.controller,
                    subject_card=spell.card if isinstance(spell, CardState) else None,
                    player=spell.controller,
                )
            )
            return spell

    def _copies_that_cease_to_exist(self: "Game") -> list[CardState]:
        """CR 704.5e / 707.10a, both sentences, as one state-based action:
        "If a copy of a spell is in a zone other than the stack, it ceases
        to exist. If a copy of a card is in any zone other than the stack or
        the battlefield, it ceases to exist."

        `CardState.is_copy` is the one flag both sentences read (CR 112.1a's
        "a copy of a spell is also a spell", CR 112.1b's "some effects allow
        a player to cast a copy of a card; if the player does, that copy is
        a spell as well" - the *same* copy is "a copy of a card" before it is
        ever cast and "a copy of a spell" once it is, which is why one flag
        and one sweep covers both sentences rather than needing two). The
        two sentences differ only in which zones they exempt - the stack
        alone for a spell-copy, the stack *and* the battlefield for a
        card-copy - which is exactly `_EXEMPT_ZONES` below.

        Proven on three unrelated mechanisms, none sharing a card or a
        mechanism with either of the others
        (`scenarios/test_copies_cease_to_exist.py`):
        - **First sentence**, a copy that reached the stack and resolved: a
          CR 722.3c prepare-spell copy (Enroot, `is_copy` still true after
          casting per CR 722.3d) and a plain `Game.copy_spell` copy of an
          instant (Alania, Divergent Storm's copy of Lightning Bolt).
        - **Second sentence**, a copy that was never cast at all - purely "a
          copy of a card", never "a copy of a spell": Isochron Scepter's own
          copy of its imprinted card, abandoned mid-resolution with the
          "cast the copy?" question left unanswered (`DecisionPending`) so
          none of the ability's own hand-written cleanup for a *declined*
          cast (`_parse_copy_exiled_card_and_cast`'s `if copy in game.exile:
          game.exile.remove(copy)`) ever runs - this state-based action is
          the only thing that removes it.

        **Never a copy of a *permanent* spell that already resolved.**
        CR 707.10f/111.13: "As that copy resolves, it ceases being a copy of
        a spell and becomes a token permanent" - `Game._resolve_top_impl`
        clears `is_copy` there, in the same branch that sets `token = True`,
        for exactly that reason (a copy of Solitude sitting on the
        battlefield is not swept the instant it lands, and the second
        sentence's own battlefield exemption is for exactly this case too,
        belt and braces: nothing in this engine currently reaches the
        battlefield still carrying `is_copy`, since everything that resolves
        into a permanent already has it cleared here, but the exemption is
        read from the rule's own words rather than relied on staying moot).
        This is why that clearing is part of the same fix as this method:
        without it, this state-based action would have destroyed every
        copied permanent one round after it resolved.

        **CR 722.3c's own exile copy is this rule's one written exception**
        ("This is an exception to rule 704.5e"), read here rather than on
        `CardState` itself: a copy in `Zone.EXILE` is spared for as long as
        some battlefield permanent's `prepared_copy_id` still names it -
        `Game.become_prepared`/`become_unprepared` are what maintain that
        link, and once nothing names it any more (it was cast, or the
        permanent lost the designation or left the battlefield), the
        exemption ends and the very next check this method makes is what
        actually removes it.

        Mirrors `models/token.tokens_that_cease_to_exist`'s own shape: every
        shared zone but the exempt ones, then every player's own zones (none
        of which is ever the stack or the battlefield).
        """
        exempt_zones = (Zone.STACK, Zone.BATTLEFIELD)
        linked_exile_copy_ids = {
            permanent.prepared_copy_id
            for permanent in self.battlefield
            if permanent.prepared_copy_id is not None
        }

        def sweep(zone: Zone, cards: list[Any]) -> list[CardState]:
            doomed = [
                state
                for state in cards
                if isinstance(state, CardState)
                and state.is_copy
                and not (zone is Zone.EXILE and state.id in linked_exile_copy_ids)
            ]
            for state in doomed:
                cards.remove(state)
            return doomed

        gone: list[CardState] = []
        for zone, cards in self.shared_zones.items():
            if zone in exempt_zones:
                continue
            gone.extend(sweep(zone, cards))
        for player in self.players:
            for zone, cards in player.zones.items():
                if zone in exempt_zones:
                    continue
                gone.extend(sweep(zone, cards))
        return gone

    def assert_quiescent(self: "Game") -> None:
        """Raise loudly if the game is sitting mid-announcement or mid-resolution.

        `Casting` and `CostPayment` (see `Game.cast` below) are locals that
        never outlive one call - they are not `Game` fields, so nothing about
        them is ever written into a `Game.model_dump()`. A caller who drives
        their step-by-step API by hand and forgets to reach `cast()`/`cancel()`
        or `pay()`/`rewind()` before letting the `Game` be persisted leaves no
        trace of the object that could still finish or cancel the action - a
        card sitting on the stack that decodes back with no `Casting` behind
        it any more. `Game.resolving` (unset outside the length of one
        `resolve_top` call) and `open_payment_pools` (emptied the moment a
        `CostPayment` is paid, cancelled or rewound - `CostPayment._register_
        pool`/`_unregister_pool`) are the two pieces of `Game` state such an
        abandoned action would leave behind, so together they are what this
        checks.
        """
        if self.resolving is not None:
            raise AssertionError(
                f"game is mid-resolution: {self.resolving!r} is still Game.resolving "
                "with no resolve_top() call left on the stack to finish or undo it"
            )
        if self.open_payment_pools:
            raise AssertionError(
                "game has an open CostPayment for "
                f"{sorted(self.open_payment_pools)} with no CostPayment object left "
                "to pay or rewind it"
            )

    def _target_spell_reduction(
        self: "Game", match: re.Match[str], targets: Sequence[TargetRef]
    ) -> ManaCost | None:
        """`_COSTS_LESS_IF_TARGETS_SPELL_RE`'s reduction when one of
        `targets` is a spell of its quality, or None. CR 109.2b: "spell"
        means an object on the stack - a target that has already left the
        stack (countered, or resolved by the time this is asked) is not a
        spell any more and cannot satisfy "if it targets a ... spell"."""
        from ...machines.next_spell import spell_has_quality, spell_quality_is_readable

        reduction = ManaCost.try_parse(match.group("amount"))
        quality = re.sub(r"\s+and\s+", " or ", match.group("quality").strip().lower())
        if reduction is None or not spell_quality_is_readable(quality):
            return None
        for ref in targets:
            if ref.is_player:
                continue
            target = self.find_by_id(ref.card_id)
            if target is None or target.zone is not Zone.STACK:
                continue
            if spell_has_quality(target, quality):
                return reduction
        return None

    def _target_description_reduction(
        self: "Game", match: re.Match[str], targets: Sequence[TargetRef], caster: str
    ) -> ManaCost | None:
        """`_COSTS_LESS_IF_TARGETS_DESCRIPTION_RE`'s reduction when one of
        `targets` fits the description, or None - also None when the
        description is not one the target grammar reads, so an unread
        condition never discounts a spell."""
        from ...machines.targeting import chosen_target_description

        reduction = ManaCost.try_parse(match.group("amount"))
        requirement = chosen_target_description(match.group("description"))
        if reduction is None or requirement is None:
            return None
        for ref in targets:
            if ref.is_player:
                continue
            target = self.find_by_id(ref.card_id)
            if target is not None and requirement.rejects(target, caster, self) is None:
                return reduction
        return None

    def why_not_holding_priority(self: "Game", username: str, rule: str) -> str | None:
        """Why `username` may not take an action that needs priority right
        now, citing `rule`, or None: they hold it, or decide for whoever does
        (CR 723.5). `Priority.retain`'s own gate, asked before the action
        begins - CR 117.1a for a cast, CR 117.1b for an activation - so
        nothing the action asks or triggers is put to anyone ahead of a
        refusal that was always coming. A caller that drives `Casting` itself
        rather than through `cast` (the api's `engine_api.cast_card`) asks it
        the same way, before building one: `put_on_stack` stacks the cast's
        own triggers (CR 603.3b asks their controller to order them) before
        `retain_priority` ever gets to refuse."""
        if self.priority is None:
            return None
        not_holding = self.priority.why_cannot_act(username)
        return None if not_holding is None else f"{not_holding} ({rule})"

    @property
    def priority_holder(self: "Game") -> str | None:
        """Who has priority right now, or None if nobody does (CR 502.4, 514.3).

        The single honest answer for a client asking "whose move is it". None is
        not "unknown" and not "the game is stuck" - it is the untap step (or an
        ordinary cleanup step) saying that the next thing to happen is the step
        ending, not a player acting.
        """
        return None if self.priority is None else self.priority.holder

    def sync_priority_with_step(self: "Game") -> None:
        """Withhold or restore priority to match the step now in progress.

        Called at every point the step pointer moves. CR 502.4 and CR 514.3 are
        the two withholding rules and their own wording is what gets stored, so
        the refusal a caller gets back is the rule.
        """
        assert self.turn is not None
        if self.priority is None:
            return
        if self.step_grants_priority:
            self.priority.grant()
        elif self.turn.step is Step.UNTAP:
            self.priority.withhold(self.UNTAP_HAS_NO_PRIORITY)
        elif self.turn.step is Step.CLEANUP:
            self.priority.withhold(self.CLEANUP_HAS_NO_PRIORITY)
        else:
            self.priority.grant()

    def pass_priority(self: "Game", username: str) -> PriorityOutcome:
        """Pass priority. If everyone passes, resolve the top of the stack.

        CR 117.4: "If all players pass in succession ... the spell or ability
        on top of the stack resolves or, if the stack is empty, the phase or
        step ends." CR 405.5: the next step or phase then begins - nobody has
        to move the game on; passing is saying "I am done for now". So on
        END_STEP the turn rolls forward here, with everything that boundary
        brings (CR 500.5's mana-pool emptying among them), and the next
        step's first priority round starts with its active player (CR 117.1).

        Refused outright in a step that grants nobody priority (CR 502.4, 514.3),
        with that rule's own words. The refusal comes *before* CR 704.3's
        state-based check and CR 603.3's stacking below, because both of those
        are "the next time a player would receive priority" moments and this is
        not one: running them here would put an untap-step trigger straight onto
        the stack, which is the very thing CR 502.4's second sentence forbids.
        """
        self._refuse_if_over()
        assert self.priority is not None
        if self.priority.withheld is not None:
            # Through `require`, so a player who is not at the table at all is
            # still told *that* first: "carol is not in this game" outranks
            # "nobody has priority", because the second answer would be just as
            # true next turn and would send the caller looking in the wrong place.
            self.priority.require(username)
        with self._id_allocator_scope():
            # CR 704.3, then CR 603.3: state-based actions, then anything that
            # has triggered goes on the stack, before the pass is acted on -
            # the next player (or nobody, if the stack resolves) is about to
            # receive priority. This is also the check a special action like
            # playing a land relies on: CR 116.2a hands out no priority of its
            # own, so the legend rule or any other state-based action it
            # caused is caught here, the next time anyone would receive
            # priority.
            self._check_state_based_actions_and_stack_triggers()
            if self.is_over:
                # CR 104.1: the check that preceded this pass ended the game,
                # so the pass does nothing - no resolution, no step change.
                return PriorityOutcome.GAME_OVER
            outcome = self.priority.pass_priority(username, self.stack_is_empty)
            if outcome is PriorityOutcome.RESOLVE_TOP:
                self.resolve_top()
            elif outcome is PriorityOutcome.END_STEP and not self.is_over:
                self.advance()
            return outcome

    def retain_priority(self: "Game", username: str) -> str:
        """The player who just cast or activated keeps priority (CR 117.3c).

        Keeping priority is still *receiving* it, so CR 704.3 applies here too:
        a cost paid to cast or activate (a sacrifice, most often, but also life
        paid down to 0) can leave two legendary permanents, a 0-toughness
        creature, or even take the activator themselves out of the game before
        their own ability ever resolves (CR 704.5a) - and that must be resolved
        before this player would act again rather than waiting for the next
        pass. If the check just removed `username`, CR 800.4j has already
        moved priority on to whoever is next seated, so there is nobody left
        to hand it back to.

        Run under `_id_allocator_scope`: `_check_state_based_actions_and_
        stack_triggers` below both checks state-based actions (a graveyard
        move's `zone_change_stamp`) and calls `put_triggers_on_stack`, which
        mints a fresh `AbilityOnStack` id for every trigger it moves off
        `pending_triggers`. `pass_priority` and `resolve_top` already reach
        the same helper from inside their own scopes, but the api calls this
        directly after every `cast_card`, `activate_ability`, `cycle_card`
        and `declare_attack` (`engine_api.py`, e.g. around lines 375, 440,
        608, 731), so it needs a scope of its own.
        """
        if self.is_over:
            # CR 104.1: the cast or activation this follows may itself have ended
            # the game (a CR 104.4b draw off a mana ability), and nobody receives
            # priority in a game that is over.
            return username
        with self._id_allocator_scope():
            return self._retain_priority_impl(username)

    def _retain_priority_impl(self: "Game", username: str) -> str:
        """The rest of `retain_priority` - see its own docstring for why it
        is split out."""
        assert self.priority is not None
        self._check_state_based_actions_and_stack_triggers()
        if not self.is_in_game(username):
            return self.priority.holder
        return self.priority.retain(username)


from ._casting import _is_spell_quality, _spell_colour_quality  # noqa: E402
from ._common import (  # noqa: E402
    _CAST_THIS_TURN_QUALITY_RE,
    _COLOR_COUNT_QUALITIES,
    _COLOR_WORDS,
    _EACH_OPPONENT_PROTECTION_QUALITY,
)
from ._conditions import _card_type_named, _qualities_from_text  # noqa: E402
from ._continuous import _characteristic_quality  # noqa: E402
