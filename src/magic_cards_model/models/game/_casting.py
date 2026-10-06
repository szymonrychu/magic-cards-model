import re
from collections.abc import Callable, Iterable, Iterator, Sequence
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any
from uuid import UUID

from ...data.creature_types import creature_types
from ...machines.abilities import (
    AbilityKind,
    TriggerEvent,
    parse_abilities,
)
from ...machines.casting import (
    _BLIGHT_PHRASE,
    AlternativeCostOption,
    AlternativeCostSource,
    Casting,
    KeywordCastOption,
    PlayAction,
    PlayPermission,
    _printed_alternative_total_cost,
    castable_faces,
    face_being_cast,
    granted_cast_options,
    keyword_cast_options,
    life_or_mana_additional_costs,
    linked_exile_play_source,
    marker_cast_options,
    optional_additional_costs,
    play_permissions_on,
    static_free_cast_grants,
    static_free_cast_refusal,
    static_zone_cast_permission,
    types_being_cast,
    usable_play_permission,
    why_cannot_cast_restriction,
)
from ...machines.cost import (
    ComponentKind,
    CostModifierKind,
    CostPayment,
    TotalCost,
    additional_cost_phrases,
    alternative_cost_offers,
    cost_modifier_effect,
    plan_mana_payment,
    total_cost_for_phrase,
)
from ...machines.decisions import (
    Decision,
    DecisionKind,
    source_id_of,
)
from ...machines.delayed import (
    DelayedTrigger,
    rebound_recast,
)
from ...machines.effects import (
    NO_FURTHER_MODES,
    ConditionalClauseNotice,
    mode_effect_body,
)
from ...machines.keywords import (
    has_rebound_now,
)
from ...machines.layers import (
    BASIC_LAND_TYPES,
    additional_land_plays_of_line,
)
from ...machines.modes import (
    ModalProfile,
    Mode,
    modal_profile,
    substitute_x,
)
from ...machines.next_spell import (
    NextSpellFreeCastGrant,
    spell_has_quality,
)
from ...machines.objects_as_costs import convoke as pay_convoke
from ...machines.objects_as_costs import delve as pay_delve
from ...machines.objects_as_costs import improvise as pay_improvise
from ...machines.targeting import (
    TargetingProfile,
    face_spell_profile,
    profile_for_modes_with_owners,
    profile_for_text,
    spell_profile_for_text,
    targeting_profile,
)
from ...machines.triggers import (
    AbilityOnStack,
    ExtraTriggerEvent,
    GameEvent,
)
from ...machines.turn import (
    MAIN_PHASES,
    Step,
)
from ...numbers import count_pattern, parse_count
from ..card import (
    Color,
    Layout,
    Type,
)
from ..card_state import (
    CardState,
    ExileAnnotation,
    TargetRef,
)
from ..zone import Zone
from ._common import StackObject

if TYPE_CHECKING:
    from . import Game


#: Thranduil's Company's own "As long as you control another Elf, you may
#: play an additional land on each of your turns." - the conditional twin of
#: `machines.layers._ADDITIONAL_LAND_PLAYS_RE` (Icetill Explorer's/Azusa's
#: own unconditional grant, CR 305.2/611.3d), gated on a board fact read
#: fresh every time `Game.land_allowance` asks (CR 611.3a: never "locked
#: in"). Kept here rather than widening that regex in `machines/layers.py`,
#: because deciding the condition needs a live `Game` (`condition_holds`)
#: that function's own pure per-line signature has no room for.
_CONDITIONAL_ADDITIONAL_LAND_PLAYS_RE = re.compile(
    rf"^as long as (?P<condition>[^,]+), you may play {count_pattern('n')} additional lands? "
    r"on each of your turns\.?$",
    re.IGNORECASE,
)


def conditional_additional_land_plays_of_line(text: str) -> tuple[int, str] | None:
    """`_CONDITIONAL_ADDITIONAL_LAND_PLAYS_RE`'s shape: how many additional
    lands the line grants and the condition that has to hold for it, or
    `None` when the line is not this shape."""
    match = _CONDITIONAL_ADDITIONAL_LAND_PLAYS_RE.fullmatch(text.strip())
    if match is None:
        return None
    n = parse_count(match.group("n"), article=True)
    if n is None:
        return None
    return n, match.group("condition").strip()


#: "spells that are one or more colors" (Emrakul, the Aeons Torn): CR 112.1's
#: spell narrowed by a colour quality - a colour word, a CR 105.2a/105.2b
#: colour count, or CR 105.2's "one or more colors" (anything not colorless,
#: CR 105.2c).
_SPELLS_THAT_ARE_QUALITY_RE = re.compile(r"^spells? that (?:are|is) (?P<colors>.+)$", re.IGNORECASE)


def _spell_colour_quality(quality: str) -> Callable[[Iterable[Color]], bool] | None:
    """The colour test a "spells that are `<colour quality>`" protection
    quality narrows CR 112.1's spell by, or `None` for any other quality."""
    match = _SPELLS_THAT_ARE_QUALITY_RE.fullmatch(quality.strip())
    if match is None:
        return None
    wanted = match.group("colors").strip().lower()
    if wanted in ("one or more colors", "one or more colours"):
        return lambda colors: len(set(colors)) >= 1
    if wanted in _COLOR_WORDS or wanted in _COLOR_COUNT_QUALITIES:
        return lambda colors: bool(_has_color_quality(wanted, colors))
    return None


def _is_spell_quality(quality: str) -> bool:
    """Whether a protection quality names CR 112.1's "spell" ("A spell is a
    card on the stack"), singular or plural - never a CR 205.2a card type,
    so it is checked ahead of `_card_type_named` rather than folded into it."""
    return quality.strip().lower() in ("spell", "spells")


def _is_cast_this_turn_quality(quality: str) -> bool:
    """Whether a protection quality names CR 400.7d's own provenance fact,
    narrowed to the current turn - `_CAST_THIS_TURN_QUALITY_RE`'s shape."""
    return _CAST_THIS_TURN_QUALITY_RE.fullmatch(quality.strip()) is not None


class CastingMixin:
    def can_cast_sorcery(self: "Game", username: str) -> bool:
        assert self.turn is not None
        return self.turn.can_cast_sorcery(self.stack_is_empty, username)

    def note_cast(
        self: "Game",
        spell: CardState,
        *,
        keyword: str | None = None,
        keyword_cost_paid: bool = False,
        exile_instead_of_graveyard: bool = False,
        origin_zone: Zone = Zone.HAND,
        face: str | None = None,
        exile_annotation: "ExileAnnotation | None" = None,
        modes: list[int] | None = None,
        mode_targets: list[list[TargetRef]] | None = None,
        x_value: int = 0,
        mana_spent: dict[Color, int] | None = None,
        spend_effects: list[str] | None = None,
        treasure_mana_spent: int = 0,
        kicked: int = 0,
        replicated: int = 0,
        casualty_paid: int = 0,
        conspire_paid: int = 0,
        offspring_paid: bool = False,
        blight_paid: bool = False,
        cast_using_teamwork: bool = False,
        phyrexian_life_symbols_paid: int = 0,
        gift_promised: bool = False,
        gift_chosen_player: str | None = None,
        behold_chosen_type_paid: bool = False,
        chosen_creature_type: str | None = None,
        additional_cost_cards: list[UUID] | None = None,
        additional_cost_mana_values: list[float] | None = None,
        additional_cost_kinds: list[str] | None = None,
        additional_cost_powers: list[int] | None = None,
        is_copy: bool = False,
        sneak_defender: TargetRef | None = None,
        enters_with_counters: list[str] | None = None,
        kicker_costs_paid: list[str] | None = None,
        bargained: bool = False,
        evidence_collected: bool = False,
        revealed_for_cost: bool = False,
        beheld_for_cost: bool = False,
        creature_mana_spent: int = 0,
        snow_mana_spent: dict[Color, int] | None = None,
        controlled_subtypes_as_cast: Sequence[str] = (),
    ) -> "CastRecord":
        """Record how a spell was cast, for the rules that ask afterwards.

        CR 601.2b is where a caster announces an alternative cost, a face, and
        the modes; the `CardState` that reaches the stack carries none of that.
        Five rules need it later:

        - **CR 702.34a** - "If the flashback cost was paid, exile this card
          instead of putting it anywhere else any time it would leave the
          stack."
        - **CR 702.185a** - warp's delayed trigger exists only "if this spell's
          warp cost was paid".
        - **CR 715.3d** - "Instead of putting a spell that was cast as an
          Adventure into its owner's graveyard as it resolves, its controller
          exiles it."
        - **CR 700.2c** - which targets a modal spell has depends on the modes
          chosen, which CR 608.2b then rechecks.
        - **CR 700.2f** - "Modal spells ... may have different targeting
          requirements for each mode", so each mode keeps its own slice of
          what was targeted rather than one flat list shared by all of them.
        - **CR 601.2h / CR 702.33d** - what mana was spent paying the total
          cost, and whether a kicker cost was among the costs paid; both are
          read afterwards by `machines/triggers.intervening_if_holds`.

        `machines/casting.py` calls this as the spell goes on the stack. A spell
        cast without going through a `Casting` has no record and is treated as
        cast plainly, which is exactly right.

        `is_copy` is `Game.copy_spell`'s own use of this method: CR 707.10
        makes a copy carry every CR 707.2 choice above except `mana_spent`/
        `spend_effects` (CR 707.2's own Dawnglow Infusion example) and
        `exile_instead_of_graveyard` (CR 604.5's grant belongs to how the
        *original* left the stack), with `origin_zone` forced to `Zone.STACK`
        regardless of what is passed - a copy "isn't cast", so it was never
        cast from anywhere.
        """
        if is_copy:
            origin_zone = Zone.STACK
        record = CastRecord(
            keyword=keyword,
            keyword_cost_paid=keyword_cost_paid,
            exile_instead_of_graveyard=exile_instead_of_graveyard,
            origin_zone=origin_zone,
            face=face,
            exile_annotation=exile_annotation,
            modes=list(modes or []),
            mode_targets=[list(slice_) for slice_ in mode_targets or []],
            x_value=x_value,
            mana_spent=dict(mana_spent or {}),
            spend_effects=tuple(spend_effects or ()),
            treasure_mana_spent=0 if is_copy else treasure_mana_spent,
            kicked=kicked,
            replicated=replicated,
            casualty_paid=casualty_paid,
            conspire_paid=conspire_paid,
            offspring_paid=offspring_paid,
            blight_paid=blight_paid,
            cast_using_teamwork=cast_using_teamwork,
            phyrexian_life_symbols_paid=phyrexian_life_symbols_paid,
            gift_promised=gift_promised,
            gift_chosen_player=gift_chosen_player,
            behold_chosen_type_paid=behold_chosen_type_paid,
            chosen_creature_type=chosen_creature_type,
            additional_cost_cards=list(additional_cost_cards or []),
            additional_cost_mana_values=(
                list(additional_cost_mana_values)
                if additional_cost_mana_values is not None
                else [
                    self.last_known_mana_value(card_id) for card_id in additional_cost_cards or []
                ]
            ),
            additional_cost_kinds=list(additional_cost_kinds or []),
            additional_cost_powers=(
                list(additional_cost_powers)
                if additional_cost_powers is not None
                else [
                    self._last_known_stat(card_id, "power") or 0
                    for card_id in additional_cost_cards or []
                ]
            ),
            card_id=spell.id,
            is_copy=is_copy,
            sneak_defender=sneak_defender,
            enters_with_counters=[] if is_copy else list(enters_with_counters or []),
            cast_step=None if is_copy or self.turn is None else self.turn.step,
            cast_during_turn_of=(None if is_copy or self.turn is None else self.turn.active_player),
            kicker_costs_paid=list(kicker_costs_paid or []),
            bargained=bargained,
            evidence_collected=evidence_collected,
            revealed_for_cost=revealed_for_cost,
            beheld_for_cost=beheld_for_cost,
            controlled_subtypes_as_cast=() if is_copy else tuple(controlled_subtypes_as_cast),
            creature_mana_spent=0 if is_copy else creature_mana_spent,
            snow_mana_spent={} if is_copy else dict(snow_mana_spent or {}),
        )
        self.forget_cast_record(spell)
        self.cast_records[spell.zone_change_stamp] = record
        return record

    def cast_record_of(self: "Game", state: StackObject | None) -> "CastRecord | None":
        """The record of how this exact object was cast, or `None` (CR 400.7).

        Keyed by the object's `zone_change_stamp`, so a card that moved since
        the cast finds nothing: CR 400.7 makes it "a new object with no memory
        of, or relation to, its previous existence". The one bridge is CR
        400.7d, "An ability of a permanent can reference information about the
        spell that became that permanent as it resolved", which
        `_carry_cast_record` follows as the spell becomes the permanent.
        """
        if not isinstance(state, CardState):
            return None
        return self.cast_records.get(state.zone_change_stamp)

    def was_cast_this_turn(self: "Game", permanent: CardState) -> bool:
        """Whether `permanent` became a permanent this turn by resolving a
        spell that was cast for it (CR 702.16a's "permanents that were cast
        this turn", CR 400.7d's own provenance link, narrowed to the current
        turn) - Emrakul, the World Anew's own second protection quality.

        Two questions, both already answered elsewhere, combined:

        - **Still the object that was cast, with no zone change since**
          (CR 400.7's "new object" rule) - `cast_record_of` already refuses
          this the moment any further move re-keys `zone_change_stamp`: a
          permanent destroyed and later reanimated, or exiled and returned
          (a flicker), is "a new object with no memory ... of its previous
          existence" the instant it leaves, so its cast record from before
          that move is unreachable off the object it becomes, whatever
          turn any of that happened on.
        - **This turn**, not some earlier one still undisturbed on the
          battlefield - `spells_cast_this_turn` is reset at the start of
          every turn (`Game.spells_cast_this_turn`'s own docstring), so a
          permanent's card id appearing there at all already means it was
          cast since this turn began; compared by `id` rather than object
          identity, since a decoded `Game`'s own copies of the same logical
          card are separate Python objects even when they share nothing but
          a field value.

        `permanent` also has to actually be a permanent right now (CR
        110.1: on the battlefield) - a card back in hand or in a graveyard
        is not one, whatever its history.
        """
        if permanent.zone is not Zone.BATTLEFIELD:
            return False
        if self.cast_record_of(permanent) is None:
            return False
        return any(
            cast_state.id == permanent.id
            for casters in self.spells_cast_this_turn.values()
            for cast_state in casters
        )

    def cast_record_as_last_known(self: "Game", stamp: UUID) -> "CastRecord | None":
        """The record of the object that had `stamp`, for an ability that
        remembers which object its source was (`AbilityOnStack.source_stamp`).

        CR 113.7a: "if the source is no longer in the zone it's expected to be
        in at that time, its last known information is used" - an evoked
        Wistfulness sacrificed before its "if {G}{G} was spent to cast it"
        trigger resolves is still the object that was cast that way. A later
        cast of the same card forgets this record (`note_cast`), and a new
        object never has this stamp (CR 400.7)."""
        return self.cast_records.get(stamp)

    def cast_record(self: "Game", spell: StackObject) -> "CastRecord":
        """How this spell was cast, or an empty record if nobody said."""
        found = self.cast_record_of(spell)
        return found if found is not None else CastRecord()

    def forget_cast_record(self: "Game", state: StackObject) -> None:
        """Drop every record of `state`'s card, whichever object it described.

        The record of the stack object the card last was is kept on its
        `last_known_spell` first (CR 608.2h): a "copy that spell" trigger
        resolving after the spell left still copies its modes, X and cost
        decisions (CR 707.10, `copy_spell_as_last_known`)."""
        if not isinstance(state, CardState):
            return
        last_known = state.last_known_spell
        if last_known is not None and last_known.cast_record is None:
            record = self.cast_records.get(last_known.stamp)
            if record is not None:
                state.last_known_spell = last_known.model_copy(
                    update={"cast_record": record.model_dump(mode="json")}
                )
        for stamp in [
            key for key, record in self.cast_records.items() if record.card_id == state.id
        ]:
            del self.cast_records[stamp]

    def was_cast_with(self: "Game", spell: StackObject, keyword: str) -> bool:
        """Whether this spell was cast using the named keyword (CR 601.2b)."""
        used = self.cast_record(spell).keyword
        return used is not None and used.lower() == keyword.lower()

    def _create_rebound_delayed_trigger(
        self: "Game", spell: CardState, cast_from_hand: bool
    ) -> None:
        """CR 702.88a's own delayed trigger: "At the beginning of your next
        upkeep, you may cast this card from exile without paying its mana
        cost."

        Created only once `put_into_graveyard` has already redirected this
        exact spell into exile because of its own rebound replacement
        (`machines/replacement._stack_replacements`) - not merely because the
        card happens to print the keyword. A card cast from anywhere but hand
        never gets that redirect (CR 702.88a's own "if this spell was cast
        from your hand"), which `cast_from_hand` - read by the caller from
        `Game.cast_records` *before* `resolve_top` pops it - is what decides;
        checking `spell.zone` here as well catches the case where the card
        has rebound printed but a *different* replacement effect sent it
        somewhere other than exile first (CR 616.1: only one effect can
        finally decide where an object goes).
        """
        if not cast_from_hand or not has_rebound_now(spell) or spell.zone is not Zone.EXILE:
            return
        controller = spell.controller or self.active_player.username
        self.delayed_triggers.create(
            DelayedTrigger(
                text=(
                    "At the beginning of your next upkeep, you may cast "
                    "this card from exile without paying its mana cost."
                ),
                event=TriggerEvent.BEGINNING_OF_STEP,
                step=Step.UPKEEP,
                # CR 702.88a says "your next upkeep", not "the next upkeep" -
                # Emrakul's own extra-turn trigger is the precedent for
                # `only_when_active` scoping a delayed trigger to one
                # player's turns. Without it, this one-shot trigger
                # (CR 603.7b) would spend itself on the *other* player's
                # upkeep if that happens to come first, and never fire again.
                only_when_active=controller,
                controller=controller,
                source_id=spell.id,
                source_name=spell.name,
                subject_id=spell.id,
                expected_zone=Zone.EXILE,  # CR 603.7c
                expected_stamp=spell.zone_change_stamp,  # CR 603.7c parenthetical
                effect=rebound_recast,
            )
        )

    def spell_options_castable_during_resolution(
        self: "Game", card: CardState, caster: str, *, mana_value_below: float | None = None
    ) -> list[str | None]:
        """Every way `caster` could cast `card` while a spell or ability
        resolves (CR 608.2g), as `Casting.face` values: `None` for the card's
        own characteristics, a face name for a split half (CR 709.3) or an
        Adventure (CR 715.3).

        An option CR 611.1 prohibits is left out, and so is one whose
        resulting spell's mana value is not below `mana_value_below` - CR
        702.85a's "if the resulting spell's mana value is less than this
        spell's mana value". CR 608.2d: "the player can't choose an option
        that's illegal or impossible", so an option left out is never offered.
        X counts as 0: a spell cast without paying its mana cost has X of 0
        (CR 107.3b). A land is never an option: "If an object is both a land
        and another card type, it can be played only as a land. It can't be
        cast as a spell" (CR 305.9), so an effect that offers a cast from among
        several cards (Portent of Calamity) never offers the land."""
        options: list[str | None] = []
        # CR 712.11c: a card about to be cast transformed (its back face up
        # off the battlefield, `_back_face_up_if_cast_transformed`) is
        # evaluated as that face.
        back_face = (
            card.card.back_face if card.transformed and card.zone is not Zone.BATTLEFIELD else None
        )
        for option in castable_faces(card.card):
            evaluated = back_face.name if back_face is not None and option is None else option
            if Type.LAND in types_being_cast(card.card, evaluated):
                continue
            if why_cannot_cast_restriction(card, caster, self, face=evaluated) is not None:
                continue
            if mana_value_below is not None and (
                self._resulting_mana_value(card, option) >= mana_value_below
            ):
                continue
            options.append(option)
        return options

    def can_cast_during_resolution(
        self: "Game", card: CardState, caster: str, *, mana_value_below: float | None = None
    ) -> bool:
        """Whether `cast_during_resolution(card, caster)` has a legal cast to
        make (CR 608.2d: "the player can't choose an option that's illegal or
        impossible"), without making it.

        A way to cast it must survive CR 611.1 and the mana-value bound
        (`spell_options_castable_during_resolution`), and for that way: a
        modal spell has enough modes with a legal target (CR 700.2a), a
        targeted spell has a legal target (CR 601.2c), and every mandatory
        additional cost has the objects and life to pay it (CR 118.3). Mana is
        not counted here: mana owed on the cast is asked for as it is paid.
        """
        with self._face_up_while_announced(card):
            return any(
                self._resolution_cast_option_is_legal(card, caster, option)
                for option in self.spell_options_castable_during_resolution(
                    card, caster, mana_value_below=mana_value_below
                )
            )

    @contextmanager
    def _back_face_up_if_cast_transformed(
        self: "Game", card: CardState, transformed: bool
    ) -> Iterator[None]:
        """CR 712.11c: "Only the face that will be face up on the stack is
        evaluated to determine if it can be cast" - for a cast "transformed"
        (CR 712.11a), the back face. Turned back afterwards."""
        was = card.transformed
        card.transformed = was or (transformed and card.card.back_face is not None)
        try:
            yield
        finally:
            card.transformed = was

    @contextmanager
    def _face_up_while_announced(self: "Game", card: CardState) -> Iterator[None]:
        """CR 406.3a: "Unless that card is being cast face down ..., the card
        is turned face up just before the player announces that they are
        playing the card." Turned back if the play does not happen."""
        was_face_up = card.face_up
        card.face_up = True
        try:
            yield
        finally:
            if card.zone is Zone.EXILE and not was_face_up:
                card.face_up = False

    def _can_play_land_during_resolution(self: "Game", username: str) -> bool:
        """CR 305.3, "A player can't play a land, for any reason, if it isn't
        their turn", and CR 305.2b, "... if the number of lands the player can
        play this turn is equal to or less than the number of lands they have
        already played this turn". CR 305.1's main phase and empty stack are
        priority's timing, which a resolving instruction does not use."""
        if self.turn is None or username != self.turn.active_player:
            return False
        return self.lands_played.get(username, 0) < self.land_allowance(username)

    def _play_land_during_resolution(
        self: "Game", land: CardState, username: str
    ) -> CardState | None:
        """Play `land` as an effect instructs during resolution. CR 305.2a
        counts "lands played during the resolution of spells and abilities",
        so this is a land play; the rest is `play_land`'s own entry, without
        the triggers it puts on the stack, which wait for the resolution to
        finish (CR 603.3)."""
        if not self._can_play_land_during_resolution(username):
            return None
        land.face_up = True
        self.lands_played[username] = self.lands_played.get(username, 0) + 1
        played = self._land_play_event(land, username)
        with self._id_allocator_scope():
            self.enter_the_battlefield(land, username, was_cast=False)
            self.emit(played)
        return land

    def _land_play_event(self: "Game", land: CardState, username: str) -> GameEvent:
        """`ExtraTriggerEvent.PLAYS_LAND` for `land`, built before the land
        moves: CR 400.7 makes it a new object on the battlefield, so the zone
        and exile pile it was played out of have to be read now."""
        return GameEvent(
            event=ExtraTriggerEvent.PLAYS_LAND,
            subject_id=land.id,
            subject_name=land.name,
            subject_controller=username,
            subject_card=land.card,
            subject_types=land.types,
            player=username,
            origin_zone=land.zone,
            origin_exile_annotation=land.exile_annotation if land.zone is Zone.EXILE else None,
        )

    def cast_during_resolution(
        self: "Game",
        card: CardState,
        caster: str,
        *,
        source_name: str,
        rule: str,
        keyword: str | None = None,
        mana_value_below: float | None = None,
        alternative_cost: TotalCost | None = None,
        pays_mana_cost: bool = False,
        exile_instead_of_graveyard: bool = False,
        transformed: bool = False,
    ) -> CardState | None:
        """CR 608.2g: cast `card` without paying its mana cost while the
        resolving spell or ability that allows it is still resolving - the one
        funnel every such effect uses (cascade, rebound, suspend, hideaway's
        play, Knowledge Pool, Possibility Storm, Isochron Scepter's copy,
        Transcendent Dragon, Paradigm).

        "If an effect specifically instructs or allows a player to cast a spell
        during resolution, they do so by following the steps in rules 601.2a-i,
        except no player receives priority after it's cast. That spell becomes
        the topmost object on the stack, and the currently resolving spell or
        ability continues to resolve". So this drives the real `Casting`
        machine under an `immediate` `PlayPermission` (CR 117.1's "unless a
        spell or ability is instructing a player to take an action": no timing
        restriction applies), asks each CR 601.2b-c announcement through
        `Game.ask` - which face (CR 709.3, CR 715.3); entwine (CR 702.42a); the
        modes (CR 700.2a) and escalate for each beyond the first (CR 702.120a);
        each optional additional cost, kicker, multikicker, replicate,
        offspring, gift and blight (CR 601.2b, CR 118.8a); the objects for a
        mandatory one (CR 118.8); the targets (CR 601.2c) - with X of 0 (CR
        107.3b), pays any mana still owed from untapped sources (CR 601.2g-h),
        and puts the spell on the stack without `retain_priority`. `keyword`
        labels the `CastRecord` (Rebound, Paradigm, Suspend).

        `alternative_cost` replaces "without paying its mana cost" with "by
        paying [cost] rather than its mana cost" - miracle's trigger (CR
        702.94a). It is announced as the spell's alternative cost (CR 118.9,
        CR 601.2b), and an X in it is the caster's to choose (CR 107.3a),
        asked as a `CHOOSE_A_QUALITY` over the values the caster's mana could
        pay; the timing is still the resolving trigger's (CR 608.2g), and the
        permission still never outlives this call.

        `pays_mana_cost` is a plain "you may cast `<card>`" or "you may cast
        the copy" with no cost waived at all - CR 707.12 (Jacob Frye, Nashi,
        Moon's Legacy), Boiling Rock Rioter's attack trigger, Kaho's paid
        branch: the resolving effect grants only the timing (CR 608.2g), and
        the spell's own mana cost is owed (CR 601.2f-h) and paid from untapped
        sources the same way a resolution cast's other owed mana is
        (`_pay_resolution_cast_mana`), an X in it chosen by the caster (CR
        107.3a).

        `transformed` casts a nonmodal double-faced card with its back face up
        (CR 712.11a, 712.8c) - a Siege's "cast it transformed" (CR 310.12b).

        Returns `None`, with the card back where it was, when the cast is not
        legal: no option qualifies, a mandatory announcement has no legal
        choice (CR 601.2c), or a cost cannot be paid (CR 118.3, CR 601.2h).
        CR 601.2's "the casting of the spell is illegal; the game returns to
        the moment before the casting of that spell was proposed" is `Casting.
        cancel` and `CostPayment.rewind`. The permission never outlives this
        call."""
        self._refuse_if_over()
        was_face_up = card.face_up
        card.face_up = True  # CR 406.3a
        # CR 712.11a/712.11c: a card cast transformed is evaluated, and goes
        # to the stack, back face up.
        transformed = transformed and card.card.back_face is not None
        card.transformed = card.transformed or transformed
        options = self.spell_options_castable_during_resolution(
            card, caster, mana_value_below=mana_value_below
        )
        if not options:
            card.face_up = was_face_up
            if card.zone is not Zone.BATTLEFIELD:
                card.transformed = False
            return None
        permission = self.grant_play_permission(
            card,
            caster,
            action=PlayAction.CAST,
            # An alternative cost is announced on the casting itself below;
            # the permission then only waives timing (CR 608.2g), not the cost.
            pays_mana_cost=alternative_cost is not None or pays_mana_cost,
            source_name=source_name,
            rule=rule,
            zone=card.zone,
            until_end_of_turn=False,
            immediate=True,
            # "If an instant or sorcery spell cast this way would be put into
            # your graveyard, exile it instead" (Bilbo, The Dawning Archaic):
            # CR 614.1a's rider rides on how this spell was cast.
            exile_instead_of_graveyard=exile_instead_of_graveyard,
        )
        casting: Casting | None = None
        payment: CostPayment | None = None
        x_value = 0
        try:
            face = options[0]
            if len(options) > 1:
                normal = (card.card.card_faces or [card.card])[0].name
                labels = [option or normal for option in options]
                answer = self.ask(
                    Decision(
                        kind=DecisionKind.CHOOSE_A_QUALITY,
                        player=caster,
                        prompt=f"choose how to cast {card.name} (CR 709.3, CR 715.3)",
                        source=card.name,
                        source_id=source_id_of(card),
                        options=tuple(labels),
                        quality="face",
                    )
                )
                face = options[labels.index(str(answer))]
            with self._id_allocator_scope():
                casting = Casting(
                    spell=card,
                    caster=caster,
                    origin_zone=card.zone,
                    game=self,
                    transformed=transformed,
                )
                casting.use_permission()
                if alternative_cost is not None:
                    casting.use_triggered_alternative_cost(keyword or "", alternative_cost)
                    x_value = self._announce_alternative_cost_x(card, caster, alternative_cost)
                    casting.x_value = x_value
                elif pays_mana_cost and card.mana_cost:
                    printed = total_cost_for_phrase(card.mana_cost, caster)
                    if printed is not None:
                        x_value = self._announce_alternative_cost_x(card, caster, printed)
                        casting.x_value = x_value
                if face is not None:
                    if card.card.layout is Layout.SPLIT:
                        casting.cast_as_split_half(face)
                    else:
                        casting.cast_as_adventure()
                taken: set[UUID] = set()
                chosen_modes = self._announce_resolution_modes(casting, card, caster, face, taken)
                self._announce_optional_costs(casting, card, caster, taken)
                self._announce_mandatory_costs(casting, card, caster, taken)
                targets = self._announce_resolution_targets(casting, card, caster, chosen_modes)
                if targets:
                    casting.choose_targets(targets)
                payment = casting.determine_cost(x_value=x_value)
                if payment.shortfall:
                    self._pay_resolution_cast_mana(casting, payment, card, caster)
                payment.pay()
                state = casting.cast()
                if keyword is not None:
                    record = self.cast_record_of(state)
                    if record is not None:
                        record.keyword = keyword
        except ValueError:
            if payment is not None:
                payment.rewind()
            if casting is not None and not casting.is_settled:
                casting.cancel()
            if card.zone is Zone.EXILE:
                card.face_up = was_face_up
            if card.zone is not Zone.BATTLEFIELD:
                card.transformed = False
            return None
        finally:
            self.play_permissions = [
                granted for granted in self.play_permissions if granted is not permission
            ]
        self.put_on_stack(state, caster)
        return state

    def _announce_alternative_cost_x(
        self: "Game", card: CardState, caster: str, cost: TotalCost
    ) -> int:
        """CR 107.3a: "the controller of that spell ... chooses and announces
        the value of X as part of casting the spell" - here for an X in the
        alternative cost a resolving trigger offers (Entreat the Angels'
        Miracle {X}{W}{W}). The options are every X the caster's floating mana
        and untapped sources could pay (CR 118.3, CR 608.2d: an impossible
        option is not offered), 0 always among them; no question is asked
        when the cost has no X."""
        if not cost.mana.x_count:
            return 0
        sources = self._mana_sources_while_resolving(self.player(caster))
        highest = 0
        while highest < self.ALTERNATIVE_COST_X_BOUND and (
            plan_mana_payment(cost.mana.with_x(highest + 1), sources, game=self, payer=caster)
            is not None
        ):
            highest += 1
        options = tuple(str(value) for value in range(highest + 1))
        answer = self.ask(
            Decision(
                kind=DecisionKind.CHOOSE_A_QUALITY,
                player=caster,
                prompt=f"choose X for {card.name}'s {cost} (CR 107.3a)",
                source=card.name,
                source_id=source_id_of(card),
                options=options,
                quality="x",
            )
        )
        return int(str(answer))

    def _announce_optional_costs(
        self: "Game", casting: Casting, card: CardState, caster: str, taken: set[UUID]
    ) -> None:
        """CR 601.2b's optional additional costs, read off the keywords that
        print them and the "you may" additional-cost sentence that blights.

        The keywords come from `optional_additional_costs`, the same
        enumeration `legal_actions` fills `Action.additional_cost_options`
        from, so what a seat is *told* it may announce and what the engine
        offers a cast it makes on that seat's behalf cannot drift apart."""
        options = optional_additional_costs(card.card)
        printed = {option.keyword: option for option in options}
        kickers = [option for option in options if option.keyword == "kicker"]
        if len(kickers) > 1:
            # CR 702.33b: "Kicker [cost 1] and/or [cost 2]" - each kicker cost
            # is its own announcement, paid at most once.
            for option in kickers:
                extra = total_cost_for_phrase(option.cost, caster)
                if extra is not None and self._offer_additional_cost(
                    casting, card, caster, "kicker", extra, taken
                ):
                    casting.pay_kicker(
                        1,
                        which=option.cost,
                        choosing=self._choose_cost_objects(extra, caster, card, taken),
                    )
        for keyword, pay in (
            ("kicker", casting.pay_kicker),
            ("multikicker", casting.pay_kicker),
            ("replicate", casting.pay_replicate),
        ):
            option = printed.get(keyword)
            if option is None or (keyword == "kicker" and len(kickers) > 1):
                continue
            # CR 702.33a's plain kicker is announced once; CR 702.33c's
            # multikicker and CR 702.56a's replicate are "any number of
            # times", bounded so a cost of nothing cannot loop.
            repeats = self.REPEATED_ADDITIONAL_COST_BOUND if option.repeatable else 1
            for _ in range(repeats):
                extra = total_cost_for_phrase(option.cost, caster)
                if extra is None or not self._offer_additional_cost(
                    casting, card, caster, keyword, extra, taken
                ):
                    break
                pay(1, choosing=self._choose_cost_objects(extra, caster, card, taken))
        offspring = printed.get("offspring")
        if offspring is not None:
            extra = total_cost_for_phrase(offspring.cost, caster)
            if extra is not None and self._offer_additional_cost(
                casting, card, caster, "offspring", extra, taken
            ):
                casting.pay_offspring()
        self._announce_casualty(casting, card, caster, taken)
        self._announce_conspire(casting, card, caster, taken)
        if "gift" in printed:
            opponents = [p.username for p in self.players_in_game if p.username != caster]
            promised = self.ask(
                Decision(
                    kind=DecisionKind.MAY,
                    player=caster,
                    prompt=f"promise an opponent a gift as you cast {card.name} (CR 702.174a)",
                    source=card.name,
                    source_id=source_id_of(card),
                    affirmative_is_legal=bool(opponents),
                )
            )
            if promised:
                opponent = opponents[0]
                if len(opponents) > 1:
                    opponent = str(
                        self.ask(
                            Decision(
                                kind=DecisionKind.CHOOSE_A_QUALITY,
                                player=caster,
                                prompt=f"choose the opponent to promise {card.name}'s gift",
                                source=card.name,
                                source_id=source_id_of(card),
                                options=tuple(opponents),
                                quality="opponent",
                            )
                        )
                    )
                casting.pay_gift(opponent)
        self._announce_bargain_evidence_and_reveal(casting, card, caster, printed)
        blights = [_BLIGHT_PHRASE.match(p) for p in additional_cost_phrases(card.card)]
        # Only the optional "you may blight N" is a `MAY` here. A mandatory
        # "blight X" and "blight 2 or pay {1}" are left to the printed cost:
        # unpaid, the first refuses (CR 118.3) and the second charges the mana.
        if any(match is not None and match.group("optional") for match in blights):
            creatures = [
                state
                for state in self.permanents_controlled_by(caster)
                if self.characteristics_of(state).is_creature
            ]
            if self.ask(
                Decision(
                    kind=DecisionKind.MAY,
                    player=caster,
                    prompt=f"blight as you cast {card.name} (CR 701.68a)",
                    source=card.name,
                    source_id=source_id_of(card),
                    affirmative_is_legal=bool(creatures),
                )
            ):
                answer = self.ask(
                    Decision(
                        kind=DecisionKind.CHOOSE_CARDS,
                        player=caster,
                        prompt=f"choose a creature you control to blight for {card.name}",
                        source=card.name,
                        source_id=source_id_of(card),
                        amount=1,
                        cards=tuple(state.id for state in creatures),
                    )
                )
                casting.pay_blight(next(state for state in creatures if state.id == answer[0]))

    def _announce_casualty(
        self: "Game", casting: Casting, card: CardState, caster: str, taken: set[UUID]
    ) -> None:
        """CR 702.153a's optional sacrifice, one `MAY` per casualty instance
        the spell has - printed or granted (CR 702.153b: "each is paid
        separately") - each legal only while a creature with enough power is
        left to sacrifice, then which creature (`CHOOSE_CARDS`)."""
        for number in casting.casualty_numbers():
            board = self.computed_board()
            fodder = [
                state
                for state in self.permanents_controlled_by(caster)
                if board.of(state).is_creature
                and state.id not in taken
                and (self.power_of(state) or 0) >= number
            ]
            if not self.ask(
                Decision(
                    kind=DecisionKind.MAY,
                    player=caster,
                    prompt=(
                        f"pay casualty {number} (sacrifice a creature with power {number} or "
                        f"greater) as you cast {card.name} (CR 702.153a)"
                    ),
                    source=card.name,
                    source_id=source_id_of(card),
                    affirmative_is_legal=bool(fodder),
                )
            ):
                return
            answer = self.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=caster,
                    prompt=f"choose a creature to sacrifice for {card.name}'s casualty {number}",
                    source=card.name,
                    source_id=source_id_of(card),
                    amount=1,
                    cards=tuple(state.id for state in fodder),
                )
            )
            chosen = next(state for state in fodder if state.id == answer[0])
            taken.add(chosen.id)
            casting.pay_casualty(chosen)

    def _announce_conspire(
        self: "Game", casting: Casting, card: CardState, caster: str, taken: set[UUID]
    ) -> None:
        """CR 702.78a's optional tap of two creatures, one `MAY` per conspire
        instance the spell has - printed or granted - legal only while two
        untapped creatures sharing a colour with it are left, then which two
        (`CHOOSE_CARDS`)."""
        for _ in range(casting.conspire_count()):
            fodder = [state for state in casting.conspire_candidates() if state.id not in taken]
            if not self.ask(
                Decision(
                    kind=DecisionKind.MAY,
                    player=caster,
                    prompt=(
                        f"pay conspire (tap two untapped creatures you control that share a "
                        f"color with it) as you cast {card.name} (CR 702.78a)"
                    ),
                    source=card.name,
                    source_id=source_id_of(card),
                    affirmative_is_legal=len(fodder) >= 2,
                )
            ):
                return
            answer = self.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=caster,
                    prompt=f"choose two creatures to tap for {card.name}'s conspire",
                    source=card.name,
                    source_id=source_id_of(card),
                    amount=2,
                    cards=tuple(state.id for state in fodder),
                )
            )
            chosen = [state for state in fodder if state.id in answer]
            taken.update(state.id for state in chosen)
            casting.pay_conspire(chosen)

    def _announce_bargain_evidence_and_reveal(
        self: "Game", casting: Casting, card: CardState, caster: str, printed: dict
    ) -> None:
        """CR 601.2b's announcement of the optional additional costs a cast
        made on a player's behalf may carry beyond the keyword-line ones:
        bargain (CR 702.166a), "you may collect evidence N" (CR 701.59a) and
        "you may reveal a <quality> card from your hand" (CR 701.20a). Each is
        a `MAY`, legal only when something could pay it."""

        def offered(prompt: str, legal: bool) -> bool:
            return bool(
                self.ask(
                    Decision(
                        kind=DecisionKind.MAY,
                        player=caster,
                        prompt=f"{prompt} as you cast {card.name}",
                        source=card.name,
                        source_id=source_id_of(card),
                        affirmative_is_legal=legal,
                    )
                )
            )

        def choose(prompt: str, candidates: list[CardState]) -> CardState:
            answer = self.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=caster,
                    prompt=prompt,
                    source=card.name,
                    source_id=source_id_of(card),
                    amount=1,
                    cards=tuple(state.id for state in candidates),
                )
            )
            return next(state for state in candidates if state.id == answer[0])

        if "bargain" in printed:
            board = self.computed_board()
            fodder = [
                state
                for state in self.permanents_controlled_by(caster)
                if state.token
                or Type.ARTIFACT in board.of(state).types
                or Type.ENCHANTMENT in board.of(state).types
            ]
            if offered("bargain (sacrifice an artifact, enchantment, or token)", bool(fodder)):
                casting.pay_bargain(
                    choose(f"choose what to sacrifice for {card.name}'s bargain", fodder)
                )
        if "collect evidence" in printed:
            wanted = re.search(r"\d+", printed["collect evidence"].cost)
            total = sum(state.mana_value for state in self.player(caster).graveyard)
            if offered(
                printed["collect evidence"].cost,
                wanted is not None and total >= int(wanted.group()),
            ):
                casting.collect_evidence()
        if "reveal" in printed:
            quality = re.search(r"reveal an? ([\w-]+) card", printed["reveal"].cost, re.IGNORECASE)
            subtype = quality.group(1).lower() if quality else ""
            revealable = [
                state
                for state in self.player(caster).hand
                if state.id != card.id and any(each.lower() == subtype for each in state.subtypes)
            ]
            if offered(printed["reveal"].cost, bool(revealable)):
                casting.reveal_for_cost(
                    choose(f"choose a card to reveal for {card.name}", revealable)
                )
        if "behold" in printed:
            self._announce_behold_chosen_type(casting, card, caster, printed["behold"].cost)

    def _announce_behold_chosen_type(
        self: "Game", casting: Casting, card: CardState, caster: str, cost: str
    ) -> None:
        """Celestial Reunion's "you may choose a creature type and behold two
        creatures of that type" on a cast made on the caster's behalf (CR
        118.8b, CR 601.2b): a `MAY`, legal only when some creature type is
        shared by enough creatures the caster could behold (CR 701.4a: a
        creature card in hand or a creature permanent they control); then
        the type (CR 607.2d) and the creatures of it."""
        wanted = re.search(r"behold (\w+) creatures", cost, re.IGNORECASE)
        count = parse_count(wanted.group(1), article=False) if wanted else None
        if count is None:
            return
        board = self.computed_board()
        beholdable: list[tuple[CardState, set[str]]] = []
        for state in self.permanents_controlled_by(caster):
            if Type.CREATURE in board.of(state).types:
                beholdable.append((state, {sub.lower() for sub in board.of(state).subtypes}))
        for state in self.player(caster).hand:
            if state.id != card.id and Type.CREATURE in state.types:
                beholdable.append((state, {sub.lower() for sub in state.subtypes}))
        known = {kind.lower() for kind in creature_types()}
        by_type: dict[str, list[CardState]] = {}
        for state, subtypes in beholdable:
            for subtype in subtypes:
                if subtype in known:
                    by_type.setdefault(subtype, []).append(state)
        eligible = sorted(kind for kind, states in by_type.items() if len(states) >= count)
        promised = self.ask(
            Decision(
                kind=DecisionKind.MAY,
                player=caster,
                prompt=f"{cost} as you cast {card.name}",
                source=card.name,
                source_id=source_id_of(card),
                affirmative_is_legal=bool(eligible),
            )
        )
        if not promised or not eligible:
            return
        labels = [kind.capitalize() for kind in eligible]
        chosen_type = str(
            self.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_A_QUALITY,
                    player=caster,
                    prompt=f"choose a creature type to behold for {card.name}",
                    source=card.name,
                    source_id=source_id_of(card),
                    options=tuple(labels),
                    quality="creature type",
                )
            )
        )
        candidates = by_type[chosen_type.lower()]
        answer = self.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=caster,
                prompt=f"choose {count} {chosen_type} creatures to behold for {card.name}",
                source=card.name,
                source_id=source_id_of(card),
                amount=count,
                cards=tuple(state.id for state in candidates),
            )
        )
        chosen = [state for state in candidates if state.id in set(answer)]
        casting.behold_chosen_type_for_cost(chosen_type, chosen)

    def _announce_mandatory_costs(
        self: "Game", casting: Casting, card: CardState, caster: str, taken: set[UUID]
    ) -> None:
        """CR 118.8's mandatory printed additional costs: the objects for each
        are chosen now (CR 601.2b) and handed to `Casting`, which charges them
        at CR 601.2f. Not enough objects raises (CR 118.3)."""
        if not additional_cost_phrases(card.card):
            return
        chosen_life: set[int] = set()
        for index, component in life_or_mana_additional_costs(card.card):
            # CR 601.2b: which half of "pay N life or pay {M}" is announced
            # now; the life half is offered as an illegal "yes" when the life
            # total cannot cover it (CR 119.4, CR 608.2d).
            component.payer = caster
            if self.ask(
                Decision(
                    kind=DecisionKind.MAY,
                    player=caster,
                    prompt=f"pay {component.amount} life rather than mana for {card.name}'s "
                    "additional cost (CR 601.2b)",
                    source=card.name,
                    source_id=source_id_of(card),
                    affirmative_is_legal=component.why_not(self) is None,
                    # Unasked, the mana half is paid - the same default an
                    # announcement that never names the life half gets.
                    default_may=False,
                )
            ):
                chosen_life.add(index)
        casting.paying_life_for_additional_cost = frozenset(chosen_life)
        pools = {
            ComponentKind.SACRIFICE: casting.sacrificing,
            ComponentKind.DISCARD: casting.discarding,
            ComponentKind.EXILE: casting.exiling,
            ComponentKind.TAP: casting.tapping,
            ComponentKind.BEHOLD: casting.beholding,
        }
        for cost in casting._printed_additional_costs():  # noqa: SLF001
            chosen = self._choose_cost_objects(cost, caster, card, taken)
            for component in cost.components:
                pool = pools.get(component.kind)
                if pool is not None:
                    pool.extend(state for state in chosen if state in component.cards)

    def _announce_resolution_modes(
        self: "Game",
        casting: Casting,
        card: CardState,
        caster: str,
        face: str | None,
        taken: set[UUID],
    ) -> list[Mode]:
        """CR 601.2b's modes for `cast_during_resolution`: entwine first (CR
        702.42a), otherwise the modes asked one at a time, then escalate's
        cost for each mode beyond the first (CR 702.120a). Raises when no legal
        choice exists (CR 700.2a)."""
        modal = casting.modal
        if face is not None or modal is None or not modal.understood:
            return []
        if modal.entwine_cost is not None:
            extra = total_cost_for_phrase(modal.entwine_cost, caster)
            all_legal = all(self._spell_mode_is_legal(card, caster, m) for m in modal.modes)
            if (
                extra is not None
                and all_legal
                and self._offer_additional_cost(casting, card, caster, "entwine", extra, taken)
            ):
                casting.choose_modes(
                    [mode.number for mode in modal.modes], x_value=0, entwined=True
                )
                return list(modal.modes)
        chosen = self._ask_spell_modes(card, caster, modal, taken)
        casting.choose_modes([mode.number for mode in chosen], x_value=0)
        if modal.escalate_cost is not None and len(chosen) > 1:
            choosing: list[CardState] = []
            for _ in range(len(chosen) - 1):
                extra = total_cost_for_phrase(modal.escalate_cost, caster)
                if extra is None:
                    raise ValueError(f"{card.name}'s escalate cost could not be read")
                choosing.extend(self._choose_cost_objects(extra, caster, card, taken))
            casting.pay_escalate(choosing=choosing)
        return chosen

    def _announce_resolution_targets(
        self: "Game", casting: Casting, card: CardState, caster: str, chosen_modes: list[Mode]
    ) -> list[TargetRef]:
        """CR 601.2c for `cast_during_resolution`: each chosen mode's targets,
        or the spell's own. Raises `ValueError` when a mandatory target has no
        legal choice, which makes the cast illegal."""
        if chosen_modes:
            targets: list[TargetRef] = []
            for mode in chosen_modes:
                body = mode_effect_body(mode)
                asked = self._ask_targets(profile_for_text(body), caster, card.id, card.name, body)
                if asked is None:
                    raise ValueError(f"{card.name}: a chosen mode has no legal target (CR 601.2c)")
                targets.extend(asked)
            return targets
        asked = self._ask_targets(
            casting.targeting, caster, card.id, card.name, card.oracle_text or ""
        )
        if asked is None:
            raise ValueError(f"{card.name} has no legal target (CR 601.2c)")
        return list(asked)

    def _spell_mode_is_legal(self: "Game", card: CardState, caster: str, mode: Mode) -> bool:
        """CR 700.2a: a mode "that would be illegal (due to an inability to
        choose legal targets, for example) ... can't be chosen"."""
        profile = profile_for_text(mode_effect_body(mode))
        if not profile.understood or not profile.requirements or profile.min_targets == 0:
            return True
        return bool(self._legal_target_candidates(profile, caster, card.id))

    def _announce_trigger_modes(self: "Game", ability: AbilityOnStack, modal: ModalProfile) -> bool:
        """Choose a modal triggered ability's modes and their targets as it goes
        on the stack (CR 603.3c, CR 700.2b, CR 700.2c). False when no mode is
        chosen, which removes the ability.

        "If one of the modes would be illegal (due to an inability to choose
        legal targets, for example), that mode can't be chosen" - so only a
        mode with a legal target for every mandatory target it names is
        offered, and a mode with no target at all always is. The first choice
        offers the legal modes; once the instruction's minimum is met, each
        further choice also offers `NO_FURTHER_MODES`, first, until the maximum.
        Then each chosen mode's targets are asked for in order.

        Gollum, Riddle Master's own "choose one that hasn't been chosen -"
        adds a second exclusion on top of legality: a mode this permanent's
        own trigger has already picked (`CardState.chosen_modal_options`,
        "modes tracked per object") is not offered again, the same way a
        mode with no legal target is not. If every mode has already been
        used, `legal` (after this filter) is short of `minimum` the same way
        an all-illegal set already is, and the ability is removed from the
        stack with none chosen (CR 700.2b) rather than repeating one.
        """
        legal = [mode for mode in modal.modes if self._trigger_mode_is_legal(ability, mode)]
        instruction_lower = modal.instruction.lower()
        exclusive_this_turn = "hasn't been chosen this turn" in instruction_lower
        exclusive = exclusive_this_turn or "hasn't been chosen" in instruction_lower
        source_state = ability.source(self) if exclusive else None
        if exclusive and source_state is not None:
            already = (
                source_state.chosen_modal_options_this_turn
                if exclusive_this_turn
                else source_state.chosen_modal_options
            )
            legal = [mode for mode in legal if mode.text not in already]
        # CR 603.3c: a "choose N instead" condition is checked as the ability
        # is put on the stack, the same moment its modes are announced.
        minimum, maximum = modal.allowed_range(
            alternative=self.modal_alternative_applies(
                modal, ability.controller, ability.source_id, ability.source_name
            )
        )
        if len(legal) < minimum:
            return False
        chosen: list[Mode] = []
        while len(chosen) < maximum:
            remaining = [mode for mode in legal if modal.repeatable or mode not in chosen]
            if not remaining:
                break
            options = tuple(mode.text for mode in remaining)
            if len(chosen) >= minimum:
                # "choose up to N -" (CR 700.2b) may stop before its first
                # mode too; offered last until a mode is chosen, so the first
                # printed mode stays the unscripted default (`default_answer`).
                options = (
                    (*options, NO_FURTHER_MODES) if not chosen else (NO_FURTHER_MODES, *options)
                )
            answer = self.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_A_MODE,
                    player=ability.controller,
                    prompt="choose a mode" if not chosen else "choose another mode",
                    source=ability.source_name,
                    source_id=source_id_of(ability),
                    options=options,
                )
            )
            if answer == NO_FURTHER_MODES:
                break
            chosen.append(next((m for m in remaining if m.text == answer), remaining[0]))
        if len(chosen) < minimum or not chosen:
            # CR 700.2b: "If no mode is chosen, the ability is removed from
            # the stack" - "choose up to X -" allows choosing none.
            return False
        if exclusive and source_state is not None and chosen:
            if exclusive_this_turn:
                source_state.chosen_modal_options_this_turn = (
                    source_state.chosen_modal_options_this_turn
                    + tuple(mode.text for mode in chosen)
                )
            else:
                source_state.chosen_modal_options = source_state.chosen_modal_options + tuple(
                    mode.text for mode in chosen
                )
        slices: list[list[TargetRef]] = []
        scripted = self.trigger_targets.get(ability.source_name)
        for mode in chosen:
            body = mode_effect_body(mode)
            profile = profile_for_text(body)
            if not profile.requirements and profile.understood:
                slices.append([])
                continue
            if scripted is not None:
                slices.append(list(scripted))
                scripted = None
                continue
            asked = self._ask_targets(
                profile, ability.controller, ability.source_id, ability.source_name, body
            )
            if asked is None:
                return False
            slices.append(list(asked))
        ability.modes = [mode.number for mode in chosen]
        ability.mode_targets = slices
        ability.targets = [target for slice_ in slices for target in slice_]
        return True

    def _announce_entry(self: "Game", card_state: CardState) -> None:
        """Raise the enters events for a permanent that is now on the battlefield."""
        with self._id_allocator_scope():
            event = self._enters_event(card_state)
            if Type.LAND in (event.subject_types or ()) and card_state.controller:
                # Landfall's own "If you had a land enter the battlefield
                # under your control this turn" (Searing Blaze) - a fact of
                # the turn, still true once the land has left again.
                self.record_turn_fact("land_entered", card_state.controller)
            if card_state.controller:
                # "if an artifact entered the battlefield under your control
                # this turn" (Iron Man, Master of Machines), "a Hero entered
                # the battlefield under your control this turn" (Avengers
                # Assemble!) - the entering object's own types, a fact of the
                # turn that stays true once it has left again.
                for fact in entered_type_facts(event.subject_types, event.subject_subtypes):
                    self.record_turn_fact(fact, card_state.controller)
                    # The counting twin - Kinbinding's own "Creatures you
                    # control get +X/+X, where X is the number of creatures
                    # that entered the battlefield under your control this
                    # turn." and Bristlebane Outrider's "another creature
                    # entered ... this turn" both ask "how many"/"which one",
                    # not the plain "did you" `turn_facts` answers.
                    self.note_turn_count(fact, card_state.controller)
            origin = self._entry_origins.pop(card_state.id, None)
            if origin is not None:
                event = event.model_copy(update={"origin_zone": origin})
            if self._entry_batch:
                event = event.model_copy(update={"entered_together": self._entry_batch})
            self.emit(event)

    def announce_batched_events(self: "Game") -> None:
        """Raise the "one or more" batch events (CR 603.2c) for everything
        since the last call: one `PERMANENTS_TAPPED` for the permanents tapped,
        one `PUT_INTO_GRAVEYARD` for the cards that reached a graveyard.

        Called where one batch ends and the next begins - after each
        instruction of a resolving spell or ability (CR 608.2c; every clause
        runner in `machines/effects.py` calls it between its steps), before
        and between rounds of state-based actions, and before triggers go on
        the stack (CR 603.3), which catches a cost or a declaration. One
        instruction moving several objects stays one event; two instructions
        are two.
        """
        with self._id_allocator_scope():
            if self.tapped_since_last_batch:
                tapped = [
                    permanent
                    for card_id in self.tapped_since_last_batch
                    if isinstance(permanent := self.find_by_id(card_id), CardState)
                ]
                self.tapped_since_last_batch = []
                if tapped:
                    self._tapped_batch = tuple(tapped)
                    try:
                        self.emit(
                            GameEvent(event=ExtraTriggerEvent.PERMANENTS_TAPPED, amount=len(tapped))
                        )
                    finally:
                        self._tapped_batch = ()
            if self.graveyard_arrivals_announced < len(self.graveyard_arrivals_this_turn):
                arrivals = self.graveyard_arrivals_this_turn[self.graveyard_arrivals_announced :]
                self.graveyard_arrivals_announced = len(self.graveyard_arrivals_this_turn)
                self._graveyard_batch = tuple(arrivals)
                try:
                    self.emit(
                        GameEvent(event=ExtraTriggerEvent.PUT_INTO_GRAVEYARD, amount=len(arrivals))
                    )
                finally:
                    self._graveyard_batch = ()

    def _announce_returns(self: "Game", returned: list[tuple[GameEvent, GameEvent]]) -> None:
        """Raise the departure events of one return-to-hand event (CR 603.6c)."""
        if not returned:
            return
        self._returned_to_hand_batch = tuple(to_hand for to_hand, _ in returned)
        try:
            for to_hand, departure in returned:
                self.emit(to_hand)
                # CR 603.6c: the generic departure, alongside the destination-
                # specific event just above - see `Game.put_into_graveyard`'s
                # matching emit for why both fire.
                self.emit(departure)
        finally:
            self._returned_to_hand_batch = ()

    def announcement_profile(
        self: "Game",
        state: CardState,
        *,
        ability_index: int | None = None,
        modes: list[int] | None = None,
        x_value: int | None = None,
        spell_face: str | None = None,
    ) -> TargetingProfile:
        """What `state` may legally target, for an announcement that has not
        happened yet - `legal_targets`'s own reading of CR 601.2c/700.2c,
        before any `Casting` or `AbilityOnStack` exists to ask.

        Public: this is the engine's answer to "what does this cast or
        activation target", and a consumer asks it here rather than
        re-reading card text. `ability_index` indexes
        `Game.activated_abilities(state)` (CR 602.2b applies CR 601.2c to an
        activation). The returned `TargetingProfile` carries one
        `TargetRequirement` per slot (`phrase`, `minimum`, `maximum`) and
        `understood=False` when the text could not be read.
        `legal_actions` builds every `Action.target_slots` from this call.
        `_announcement_profile` is kept as an alias of this method.

        The same three-way read `magic_cards_model_api.affordances._profile_for`
        used to hardcode: an activated ability's own effect text names the
        profile when `ability_index` is given; a modal card's *chosen* modes
        name it when `modes` is given (CR 700.2c: an unchosen mode's targets do
        not apply); the whole card's text, with `x_value` substituted first
        (CR 107.3a), otherwise. Kept in the engine so `legal_actions` and any
        other caller ask the same question the api's UI hints already did,
        rather than the api holding the only copy of how to ask it.

        **`spell_face` is the fourth read**, and the one this method had no
        answer for at all: a cast that names a half of a split card (CR 709.3)
        or an adventurer card's Adventure (CR 715.3) is announced against
        *that* face's own text (CR 709.3b, CR 715.3b), not the printing's.
        Without it every row `legal_actions` emitted for a multi-faced card
        carried the **front** half's targeting phrase on both halves, because
        `targeting_profile` reads `Card.front_oracle_text`: the Tear row of
        Wear // Tear said "target artifact", which is Wear's requirement, and
        the Incongruity row of Incubation // Incongruity said nothing at all,
        because Incubation targets nothing. This is the same read
        `machines/casting.Casting.targeting` already does once a face has been
        named, and `_resolution_profile` does at CR 608.2b's recheck - three
        paths, one reading, rather than two that agree and one that does not.
        It sits *below* `ability_index` and `modes` in precedence, because an
        activated ability's own effect text and a chosen mode's own text are
        both narrower than the face the mode or ability is printed on.

        **`state.prepare_spell_face` is a fifth read**, checked right after
        `ability_index` and ahead of everything else: CR 722.3c's exile copy
        "has only the characteristics of that permanent's prepare spell",
        the same face `Casting.base_cost`/`CardState.up_face` already read
        for this exact copy - `targeting_profile(state.card)`'s own fallback
        below reads the front permanent's text instead, since `state.card` is
        still the two-face preparation card and nothing else here ever asks
        `up_face`. Without this, `legal_targets` offered no target at all for
        a prepared spell that targets (Seed Suture, Vicious Verse), because
        `face_being_cast` needs an explicit `spell_face` name no caller had
        any reason to pass for a copy that is not a split card or an
        Adventure. No prepare spell in the pool is modal or split, so this
        is checked unconditionally rather than raced against those two.
        """
        if ability_index is not None:
            ability = self.activated_abilities(state)[ability_index]
            effect = getattr(ability, "effect", None) or getattr(ability, "text", "")
            return profile_for_text(substitute_x(effect, x_value))
        if state.prepare_spell_face:
            prepare_face = state.card.prepare_spell
            if prepare_face is not None:
                return profile_for_text(substitute_x(prepare_face.oracle_text or "", x_value))
        modal = modal_profile(state.card)
        if modes and modal is not None:
            chosen = modal.resolve(
                modes,
                alternative=self.modal_alternative_applies(
                    modal, state.controller or state.owner or "", state.id, state.name, state
                ),
            )
            profile, _owners = profile_for_modes_with_owners(state.card, chosen, x_value)
            return profile
        face = face_being_cast(state.card, spell_face)
        if face is not None:
            return face_spell_profile(face, substitute_x(face.oracle_text or "", x_value))
        if modal is None and x_value is not None and state.card.oracle_text:
            return spell_profile_for_text(substitute_x(state.card.oracle_text, x_value), state.card)
        return targeting_profile(state.card)

    _announcement_profile = announcement_profile

    def spell_fizzles(self: "Game", spell: StackObject) -> bool:
        """Whether this spell would be removed from the stack unresolved (CR 608.2b).

        A spell that chose no targets never fizzles - "if the spell or ability
        specifies targets" is the whole condition. One that did fizzles only if
        every one of them is now illegal.
        """
        if not spell.targets:
            return False
        return all(self.legal_target(spell, target) is None for target in spell.targets)

    # -- special actions ---------------------------------------------------

    def land_allowance(self: "Game", username: str) -> int:
        """The number of lands `username` can play this turn (CR 305.2, 305.2a).

        One by default - CR 305.2: "A player can normally play one land during
        their turn; however, continuous effects may increase this number." The
        increases come from static abilities of permanents the player controls,
        read off their computed ability text: `machines.layers.
        additional_land_plays_of_line` for an unconditional grant, and
        `conditional_additional_land_plays_of_line` just below for
        Thranduil's Company's own "As long as `<condition>`, you may play an
        additional land on each of your turns." - `condition_holds` decides
        the conditional grant the same way it already gates a static cost
        reduction's own "as long as" tail (`cost_modifier_effect`). CR 611.3d
        is the rule that lets a static ability allow playing a land at all.

        Azusa's printed "on each of your turns" adds no condition of its own
        here: `can_play_land` refuses anyone who is not the active player
        (CR 305.3), so the allowance is only ever consulted for a player on
        their own turn. And it reaches only its controller, because
        `permanents_controlled_by` is what feeds the read.

        CR 305.2a compares this number against `lands_played`, which counts
        "lands played as special actions and lands played during the resolution
        of spells and abilities". Every land play this engine has goes through
        `play_land`, so the one counter covers both halves of the
        parenthetical - and a land PUT onto the battlefield by an effect (a
        fetchland's find, CR 305.4) counts in neither number, because
        `put_onto_battlefield` never reaches `play_land`.
        """
        board = self.computed_board()
        total = 1 + self.extra_land_plays.get(username, 0)
        for permanent in self.permanents_controlled_by(username):
            for line in board.of(permanent).abilities:
                unconditional = additional_land_plays_of_line(line)
                if unconditional is not None:
                    total += unconditional
                    continue
                conditional = conditional_additional_land_plays_of_line(line)
                if conditional is None:
                    continue
                amount, condition = conditional
                if self.condition_holds(username, condition, permanent):
                    total += amount
        return total

    def _plays_lands_from_top_of_library_line(self: "Game", text: str) -> bool:
        """Whether one static line is "You may play lands from the top of
        your library." - or `casting.static_zone_cast_permission`'s "You may
        play lands and cast `<quality>` spells from the top of your library."
        (Mikey & Don, Party Planners; Traveling Chocobo), whose land half is
        this same CR 305.1 permission."""
        stripped = self._static_line_without_ability_word(text)
        if self._PLAYS_LANDS_FROM_TOP_OF_LIBRARY_RE.fullmatch(stripped) is not None:
            return True
        permission = static_zone_cast_permission(stripped)
        return permission is not None and permission.plays_lands and permission.zone is Zone.LIBRARY

    def land_from_top_of_library_permission(
        self: "Game", land: CardState, username: str
    ) -> CardState | None:
        """The permanent whose "You may play lands from the top of your
        library." lets `username` play `land` (CR 305.1, CR 611.3d), or
        None. Only the top card of `username`'s own library qualifies - the
        grant never reaches deeper, and CR 108.3's owner is irrelevant here
        the way `graveyard_land_permission`'s own docstring is silent on it
        too (a player only ever looks at and plays from their *own* library
        under this shape - no printing in the pool grants it over another
        player's)."""
        if land.zone is not Zone.LIBRARY:
            return None
        player = self.player(username)
        if not player.library or player.library[0] is not land:
            return None
        board = self.computed_board()
        for permanent in self.permanents_controlled_by(username):
            if any(
                self._plays_lands_from_top_of_library_line(line)
                for line in board.of(permanent).abilities
            ):
                return permanent
        return None

    def why_cannot_play_land(self: "Game", username: str) -> str | None:
        """Why `username` cannot play a land right now, or None (CR 305.1-305.3).

        The checks, in the order the rules number them:

        - **CR 305.1** - "A player who has priority may play a land card from
          their hand during a main phase of their turn when the stack is
          empty." Of that, the main phase and the empty stack are checked here.
          Priority is not, and that is a gap, not a reading: CR 116.2a times
          the special action to "any time they have priority and the stack is
          empty during a main phase of their turn", but the engine has no
          notion of a priority possession that persists between moves, so the
          caller is trusted to hold it the way the rules require.
        - **CR 305.3** - "A player can't play a land, for any reason, if it
          isn't their turn. Ignore any part of an effect that instructs a
          player to do so."
        - **CR 305.2b** - "A player can't play a land, for any reason, if the
          number of lands the player can play this turn is equal to or less
          than the number of lands they have already played this turn."
          CR 305.2a is the comparison: `land_allowance` against `lands_played`.
        """
        if self.is_over:
            return self.why_game_is_over()
        assert self.turn is not None
        if self.turn.step not in MAIN_PHASES:
            return (
                f"{username} cannot play a land outside a main phase of their turn "
                f"(CR 305.1); the turn is in {self.turn.step.value}"
            )
        if not self.stack_is_empty:
            return f"{username} cannot play a land while the stack is not empty (CR 305.1)"
        if username != self.turn.active_player:
            return (
                f"{username} cannot play a land, for any reason, if it isn't their turn "
                f"(CR 305.3); it is {self.turn.active_player}'s turn"
            )
        played = self.lands_played.get(username, 0)
        allowance = self.land_allowance(username)
        if played >= allowance:
            return (
                f"{username} cannot play a land: {played} of the {allowance} they may play "
                f"this turn already used (CR 305.2a, 305.2b)"
            )
        return None

    def play_permission_for(
        self: "Game", card: CardState, player: str, action: PlayAction = PlayAction.CAST
    ) -> PlayPermission | None:
        """The live permission letting `player` take `action` with `card`, or None."""
        return usable_play_permission(self, card, player, action)

    def alternative_costs_for(
        self: "Game", card: CardState, caster: str
    ) -> list[AlternativeCostOption]:
        """CR 118.9's alternative-cost menu for `card`, answerable before any
        `Casting` exists.

        `magic_cards_model_api.affordances.alternative_costs` used to build a
        throw-away `Casting` on a `dry_run_copy(game)` purely to ask this
        question - CR 601.2a moves the card to the stack as the *first* step
        of proposing a cast, so answering "what could this be cast for"
        needed a whole deep copy of the game just to avoid mutating the real
        one. This is the pure port instead: the same PRINTED and KEYWORD
        halves `Casting.alternative_costs` builds, read directly off
        `alternative_cost_offers`, `keyword_cast_options`, `marker_cast_options`,
        and `granted_cast_options` - none of which need a live announcement,
        because none of them ask anything a `Casting` in flight would know
        that `card.zone` does not already say.

        `legal_actions` is what this is for: Force of Negation for `{1}{U}{U}`
        and pitched are two different cast actions with two different costs,
        and this is how it finds the second one without ever moving the card.

        All four of `Casting.alternative_costs`'s sources are reproduced,
        PERMISSION and STATIC included. Both were once thought to need an
        in-flight `Casting`'s own state - they do not: `play_permissions_on`
        is keyed off `card`'s own CR 400.7 identity, which `card` already
        carries before any `Casting` exists, and `static_free_cast_grants`
        (cascade, Ugin's exiled cards, Omniscience) is a pure read of
        `self.battlefield`/`caster`. This is the same gap that made a
        cascade hit or an Omniscience-enabled spell invisible to this menu.
        """
        options: list[AlternativeCostOption] = []
        origin_zone = card.zone
        for offer in alternative_cost_offers(card.card):
            cost = _printed_alternative_total_cost(offer.phrase, payer=caster)
            unavailable: str | None = None
            if cost is None:
                unavailable = f"{card.name}'s alternative cost {offer.phrase!r} could not be read"
            elif offer.requires_not_your_turn and not (
                self.turn is not None and self.turn.active_player != caster
            ):
                unavailable = (
                    f"{card.name}'s alternative cost can only be paid on an opponent's turn"
                )
            options.append(
                AlternativeCostOption(
                    index=len(options),
                    source=AlternativeCostSource.PRINTED,
                    rule="CR 118.9",
                    source_name=card.name,
                    description=offer.phrase,
                    cost=cost,
                    requires=sum(component.required for component in cost.components)
                    if cost
                    else 0,
                    unavailable=unavailable,
                )
            )

        keyword_options: list[tuple[str, KeywordCastOption]] = [
            (card.name, option)
            for option in keyword_cast_options(card.card) + marker_cast_options(card)
        ]
        # CR 610.5: a keyword another permanent grants as this spell is cast is
        # an alternative cost like any other printed one.
        keyword_options.extend(
            (granted.source_name, granted.option)
            for granted in granted_cast_options(self, card, caster, origin_zone)
        )
        for offering_card, keyword_option in keyword_options:
            if keyword_option.pays_mana_cost:
                # A permission that still charges the mana cost (warp's second
                # half, flashback still charging a cost) is a zone permission,
                # not a CR 118.9 alternative cost.
                continue
            cost = keyword_option.cost
            options.append(
                AlternativeCostOption(
                    index=len(options),
                    source=AlternativeCostSource.KEYWORD,
                    rule=keyword_option.rule,
                    source_name=offering_card,
                    keyword=keyword_option.keyword,
                    description=str(cost) if cost is not None else "nothing",
                    cost=cost,
                    requires=sum(component.required for component in cost.components)
                    if cost
                    else 0,
                    unavailable=keyword_option.why_not(card, caster, self, origin=origin_zone),
                )
            )

        for permission in play_permissions_on(self, card):
            if permission.pays_mana_cost:
                continue
            options.append(
                AlternativeCostOption(
                    index=len(options),
                    source=AlternativeCostSource.PERMISSION,
                    rule=permission.rule,
                    source_name=permission.source_name,
                    # CR 107.3b keeps "no cost at all" apart from a cost of
                    # {0}, so this says nothing rather than {0}.
                    description="nothing",
                    cost=None,
                    unavailable=permission.why_not(card, caster, self),
                )
            )

        for free_grant in self.next_spell_free_cast_grants_for(card, caster):
            options.append(
                AlternativeCostOption(
                    index=len(options),
                    source=AlternativeCostSource.STATIC,
                    rule="CR 118.9",
                    source_name=free_grant.source_name,
                    description="nothing",
                    cost=None,
                )
            )

        for source_name, grant in static_free_cast_grants(self, caster):
            options.append(
                AlternativeCostOption(
                    index=len(options),
                    source=AlternativeCostSource.STATIC,
                    rule="CR 118.9",
                    source_name=source_name,
                    description="nothing",
                    cost=None,
                    unavailable=static_free_cast_refusal(
                        self, caster, card, origin_zone, source_name, grant
                    ),
                    once_per_turn_key=grant.once_per_turn_key,
                )
            )
        return options

    def next_spell_free_cast_grants_for(
        self: "Game", spell: CardState, caster: str
    ) -> list[NextSpellFreeCastGrant]:
        """The live "the next `<quality>` spell you cast this turn can be cast
        without paying its mana cost" grants `spell` answers for (CR 118.9)."""
        if self.turn is None:
            return []
        return [
            grant
            for grant in self.next_spell_free_cast_grants
            if grant.controller == caster
            and grant.turn == self.turn.turns_taken
            and spell_has_quality(spell, grant.quality)
        ]

    def cast(
        self: "Game",
        card: CardState,
        caster: str,
        *,
        modes: Sequence[int | str] | None = None,
        x_value: int | None = None,
        targets: Sequence[Any] | None = None,
        division: Sequence[int] | None = None,
        keyword: str | None = None,
        alternative_cost: int | str | None = None,
        choosing: list[CardState] | None = None,
        convoke: Sequence[tuple[CardState, Color | None]] | None = None,
        delve: Sequence[CardState] | None = None,
        improvise: Sequence[CardState] | None = None,
        mana_sources: Sequence[CardState | tuple[CardState, Sequence[Color]]] | None = None,
        splice: Sequence[UUID] | None = None,
        kicker: int = 0,
        replicate: int = 0,
        offspring: bool = False,
        blight: CardState | None = None,
        gift: str | None = None,
        harmonize_creature: CardState | None = None,
        pay_life_for_additional_cost: bool = False,
        kicker_costs: Sequence[str] | None = None,
        bargain: CardState | None = None,
        collect_evidence: bool = False,
        reveal_for_cost: CardState | None = None,
        casualty: Sequence[CardState] | None = None,
        conspire: Sequence[Sequence[CardState]] | None = None,
        exile_for_cost_reduction: Sequence[CardState] | None = None,
    ) -> CardState:
        """Cast `card` for `caster`, start to finish, as one atomic action.

        CR 601.2 lays casting out as an ordered sequence: propose (601.2a),
        announce modes and any alternative or variable costs (601.2b),
        announce targets (601.2c), announce a division among them (601.2d), a
        legality check (601.2e), determine the total cost (601.2f), activate
        mana abilities (601.2g), pay (601.2h) - and only then, at 601.2i,
        "the spell becomes cast." `Casting`/`CostPayment` model that sequence
        as an object the caller drives one step at a time (CR 601.2a already
        moves the card onto the stack, well before the cast is either legal
        or paid for), which is exactly what leaves a half-finished
        announcement observable to a caller that stops driving it partway
        through. This method is what makes the whole sequence atomic by
        construction instead of by caller discipline: both objects are
        created here, driven start to finish here, and never returned or
        stored anywhere `self` keeps a reference to - they are gone the
        moment this call returns, one way or the other.

        What makes reversing it safe, when it has to be reversed, is CR
        601.2's own closing sentence together with CR 601.6: "If a player is
        unable to comply with the requirements of a step ... the casting of
        the spell is illegal; the game returns to the moment before the
        casting of that spell was proposed." CR 733.1 spells out what that
        return means: "the entire action is reversed and any payments
        already made are canceled ... If the action was casting a spell, the
        spell returns to the zone it came from." `Casting.cancel` and
        `CostPayment.rewind` are this engine's own implementation of exactly
        that - and they restore the card's pre-move CR 400.7 identity stamp,
        not merely its zone, because CR 400.7's "an object that moves from
        one zone to another becomes a new object with no memory of ... its
        previous existence" is what a `PlayPermission` or a delayed trigger
        watching that exact object would otherwise lose. Every step below
        that can refuse raises `ValueError`; it is caught once, here, both
        objects are rewound (each rewind is already safe to call whether or
        not that step ever ran), and the exception is re-raised - so a caller
        of `Game.cast` either gets back a spell on the stack with its cost
        paid, or an untouched game and an exception, with nothing in between
        for it, or a decode of `self`, to ever observe.

        The keyword parameters mirror what `magic_cards_model_api.engine_api.
        cast_card` drives by hand today, minus the pieces that belong to an
        HTTP request rather than to the rule itself (a card looked up by id
        or name, a dry-run probe that is never atomic by definition since it
        must leave no trace whether or not the cast would succeed):
        `modes`/`x_value` and `targets`/`division` are CR 601.2b-d's own
        announcements; `keyword` and `alternative_cost` (with `choosing` for
        the objects either one's cost needs, such as a pitched card) are the
        two ways CR 601.3's permission to cast can be claimed, alongside a
        live `PlayPermission` this method checks for automatically wherever
        `keyword` and `alternative_cost` are both left unclaimed; `convoke`
        (CR 702.51a/b), `delve` (CR 702.66a/b) and `improvise` (CR 702.126a/b)
        apply "only after the total cost ... is determined", so they run
        against the open payment rather than the announcement; and
        `mana_sources` are the abilities this call may activate on `caster`'s
        behalf (CR 601.2g) - a bare source lets the engine choose what colour
        it makes, a `(source, colors)` pair pins it.

        `kicker` and `replicate` are CR 601.2b's optional additional costs, as a
        count of announcements rather than a bool, because CR 702.33c's
        multikicker and CR 702.56a's replicate may each be announced "any
        number of times" while CR 702.33a's plain kicker may not (`pay_kicker`
        refuses a second announcement rather than charging for it). `kicker`
        covers multikicker too, which CR 702.33c makes a variant of kicker
        and not a second keyword - "A multikicker cost is a kicker cost".
        `kicker_costs` names each kicker cost paid on a card that prints two
        (CR 702.33b's "Kicker [cost 1] and/or [cost 2]"), as printed.
        `bargain` is the artifact, enchantment or token sacrificed for CR
        702.166a's bargain; `collect_evidence` pays a printed "you may collect
        evidence N" (CR 701.59a); `reveal_for_cost` is the card revealed for a
        printed "you may reveal a <quality> card from your hand".
        `exile_for_cost_reduction` is the cards exiled from hand for a printed
        "you may exile any number of <quality> cards from your hand. This spell
        costs {N} less to cast for each card exiled this way." (March of
        Wretched Sorrow; CR 118.8b, CR 118.7a).
        `casualty` is the creature sacrificed for each casualty instance paid
        (CR 702.153a/b), in order - printed instances first, then granted.
        They join `offspring`, `blight` and `gift` as this method's whole
        CR 601.2b announcement; `machines/casting.optional_additional_costs`
        is what tells a caller which of them a given card actually prints,
        and `Action.additional_cost_options` is that same answer enumerated.

        `splice` is CR 702.47a: card ids, never names, matching `Action.
        splice_options`' own `SpliceOption.card_id` - this library's actions
        are ids only, and a caller holding two copies of the same splice card
        has to be able to name which one it means. Each id is applied with
        `Casting.splice_by_id` before `determine_cost`, because folding a
        splice cost into `additional_costs` changes the total cost CR 601.2f
        determines (`Casting._splice_card` nulls the announcement's own stale
        `payment` for exactly that reason).

        `pay_life_for_additional_cost` is CR 601.2b's announcement of which
        half of a "pay N life or pay {M}" additional cost is paid (Redirect
        Lightning): the life half when set, the mana half otherwise
        (`life_or_mana_additional_costs`). Set on a card that prints no such
        sentence it is refused, rather than silently ignored.
        """
        self._refuse_if_over()
        origin_zone = card.zone
        # CR 601.3's dynamic half is asked before CR 601.2a's move, exactly
        # like `engine_api.cast_card` asks it - the object `usable_play_
        # permission` looks for is recorded against the pre-move CR 400.7
        # stamp, and `origin_zone` itself is read now for the same reason.
        permitted = origin_zone is Zone.EXILE and self.play_permission_for(card, caster) is not None
        # A `Casting` that fails to build (CR 601.3's static half, checked in
        # its own `model_post_init`) has moved nothing and leaves nothing to
        # rewind, so this is not inside the try/except below.
        casting = Casting(spell=card, caster=caster, origin_zone=origin_zone, game=self)
        payment: CostPayment | None = None
        try:
            if alternative_cost is not None:
                casting.use_alternative_cost(alternative_cost, choosing=choosing)
            elif keyword:
                casting.use_keyword(keyword, choosing=choosing)
            elif permitted:
                casting.use_permission()
            if modes:
                casting.choose_modes(modes, x_value=x_value)
            # CR 601.2b: casualty's sacrifice is announced with the modes,
            # before CR 601.2c's targets.
            for creature in casualty or ():
                casting.pay_casualty(creature)
            # CR 702.78a: each conspire instance's two creatures, announced
            # with the rest of CR 601.2b's additional costs.
            for pair in conspire or ():
                casting.pay_conspire(list(pair))
            if exile_for_cost_reduction is not None:
                casting.exile_for_cost_reduction(exile_for_cost_reduction)
            # CR 601.2b announces every additional cost before CR 601.2c's
            # targets; `add_additional_cost` refuses once targets are chosen,
            # so a targeted bargained/evidence/reveal cast failed here.
            if bargain is not None:
                casting.pay_bargain(bargain)
            if collect_evidence:
                casting.collect_evidence()
            if reveal_for_cost is not None:
                casting.reveal_for_cost(reveal_for_cost)
            if targets:
                casting.choose_targets(list(targets))
            for card_id in splice or ():
                casting.splice_by_id(card_id)
            if kicker:
                casting.pay_kicker(kicker)
            for cost in kicker_costs or ():
                # CR 702.33b: a card with two kicker costs names each one paid.
                casting.pay_kicker(1, which=cost)
            if replicate:
                casting.pay_replicate(replicate)
            if offspring:
                casting.pay_offspring()
            if blight is not None:
                casting.pay_blight(blight)
            if gift is not None:
                casting.pay_gift(gift)
            if (keyword or "").lower() == "harmonize":
                casting.pay_harmonize(harmonize_creature)
            if pay_life_for_additional_cost:
                life_halves = life_or_mana_additional_costs(card.card)
                if not life_halves:
                    raise ValueError(
                        f"{card.name} has no 'pay N life or pay {{M}}' additional cost to pay "
                        "with life (CR 601.2b)"
                    )
                casting.paying_life_for_additional_cost = frozenset(
                    index for index, _ in life_halves
                )
            # CR 117.1a's "any time they have priority", asked once the card's
            # own refusals (timing, permission, prohibitions, the announcement)
            # have had their say and before any cost is determined or paid -
            # see `why_not_holding_priority`. The `except` below rewinds the
            # proposal like any other illegal one (CR 601.2e).
            refusal = self.why_not_holding_priority(caster, "CR 117.1a")
            if refusal is not None:
                raise ValueError(refusal)
            payment = casting.determine_cost(x_value=x_value)
            if division is not None:
                casting.announce_division(division)
            for creature, color in convoke or ():
                pay_convoke(payment, casting.spell, creature, color)
            if delve:
                pay_delve(payment, casting.spell, *delve)
            if improvise:
                pay_improvise(
                    payment,
                    casting.spell,
                    *improvise,
                    granted=self.has_granted_improvise(casting.caster, casting.spell),
                )
            unpinned: list[CardState] = []
            for entry in mana_sources or ():
                if isinstance(entry, tuple):
                    source, colors = entry
                    payment.tap_for_mana(source, list(colors))
                else:
                    unpinned.append(entry)
            if unpinned and payment.shortfall:
                payment.auto_tap(unpinned)
            payment.pay()
            state = casting.cast()
        except ValueError:
            if payment is not None:
                payment.rewind()
            if not casting.is_settled:
                casting.cancel()
            raise
        self.put_on_stack(state, casting.caster)
        self.retain_priority(casting.caster)
        return state

    def can_play_land(self: "Game", username: str) -> bool:
        """Whether `username` may play a land right now (CR 305.1-305.3).

        Every reason it could refuse is spelled out in `why_cannot_play_land`,
        which carries the rule for each check; this is that answer as a bool.
        """
        return self.why_cannot_play_land(username) is None

    def play_land(
        self: "Game", land: CardState, username: str, face: str | None = None
    ) -> CardState:
        """Play a land: a special action, so it uses no stack and no priority.

        Nobody gets a chance to respond, because nothing is ever put on the
        stack (CR 116.2a, 505.5b). Priority does not change hands.

        A modal double-faced card is not a land by `Card.is_land`, which only
        ever reads the front face (CR 712.8a) - Witch Enchanter // Witch-
        Blessed Meadow's front is a creature. `Card.land_face` is the mirror
        read for its back: CR 712.12 lets a player play an MDFC as a land by
        choosing "one of its faces that's a land" before it hits the
        battlefield, and CR 712.8f then gives the permanent only that face's
        characteristics for as long as it stays there. There is no separate
        "playing an MDFC's land face" special action in the rules - it is the
        same CR 305.1 land drop, so it is checked and counted exactly like any
        other land below.

        `face` is CR 712.12's choice of "one of its faces that's a land" for a
        modal double-faced card with more than one (a Pathway's front *and*
        back are lands). `None` keeps the default: the front face when it is a
        land, otherwise the card's land face.
        """
        self._refuse_if_over()
        land_face = land.card.land_face
        if face is not None:
            chosen = next((each for each in land.card.land_faces if each.name == face), None)
            if chosen is None:
                raise ValueError(
                    f"{face!r} is not a land face of {land.name} (CR 712.12: the player "
                    "chooses one of its faces that's a land)"
                )
            land_face = chosen
        if not land.card.is_land and land_face is None:
            raise ValueError(f"{land.name} is not a land")
        refusal = self.why_cannot_play_land(username)
        if refusal is not None:
            raise ValueError(refusal)
        permission: PlayPermission | None = None
        if land.zone is not Zone.HAND:
            # CR 305.1 plays a land "from their hand"; CR 701.18a's "from the
            # zone it's in (usually the hand)" is the wider action, and only an
            # effect can open one of those other zones (CR 601.3's twin for
            # lands). A `PlayPermission` that says *cast* is not one of them -
            # CR 601.1a keeps playing a land and casting a spell apart. A
            # permanent's "You may play lands from your graveyard." is the
            # other opener (`graveyard_land_permission`).
            permission = self.play_permission_for(land, username, PlayAction.PLAY)
            if (
                permission is None
                and self.graveyard_land_permission(land, username) is None
                and self.land_from_top_of_library_permission(land, username) is None
                and linked_exile_play_source(self, land, username) is None
            ):
                granted = play_permissions_on(self, land)
                if granted:
                    # A permission names this object and does not stretch this
                    # far - say which way it falls short (cast-not-play, wrong
                    # player, expired) rather than "nothing allows this".
                    raise ValueError(
                        granted[0].why_not(land, username, self, action=PlayAction.PLAY)
                    )
                raise ValueError(
                    f"nothing allows {username} to play {land.name} from the "
                    f"{land.zone.value} (CR 305.1, CR 701.18a)"
                )

        if permission is not None:
            self.spend_play_permission_choice(permission)
        # CR 406.3a: a card exiled face down "is turned face up just before
        # the player announces that they are playing the card".
        land.face_up = True

        # CR 305.2a counts "lands played as special actions and lands played
        # during the resolution of spells and abilities", so any future effect
        # that plays a land during a resolution must come through here to be
        # counted. A land PUT onto the battlefield (CR 305.4) must not.
        self.lands_played[username] = self.lands_played.get(username, 0) + 1

        if land_face is not None and (not land.card.is_land or face is not None):
            land.land_face_played = land_face.name

        # Playing a land is not casting it (CR 116.2a, 305.1), so `was_cast` is
        # False. The land itself used no stack, but its enters-the-battlefield
        # ability is an ordinary triggered ability and does (CR 603.6a) - and
        # "this land enters tapped" is a replacement effect, not a trigger
        # (CR 614.1c), which `enter_the_battlefield` applies on the way in.
        # The player who played the land keeps priority, so this is the CR 603.3
        # window.
        played = self._land_play_event(land, username)
        with self._id_allocator_scope():
            self.enter_the_battlefield(land, username, was_cast=False)
            # CR 601.1a: playing a land is playing a card - Voltaic
            # Visionary's "When you play a card exiled with this creature".
            self.emit(played)
            self.put_triggers_on_stack()
        return land

    # -- companion (CR 702.139, CR 116.2g) ----------------------------------

    def why_cannot_bring_companion_to_hand(self: "Game", username: str) -> str | None:
        """Why `username` cannot take CR 116.2g's special action right now,
        or None.

        CR 116.2g: "A player who has chosen a companion may pay {3} to put
        that card from outside the game into their hand. This is a special
        action. A player can take this action any time they have priority
        and the stack is empty during a main phase of their turn, but only
        if they haven't done so yet this game."

        `Player.companion_id` is set only once (`Player.load_deck`/
        `tests.scenarios.harness.Scenario.player`) after CR 702.139a's own
        condition check already passed, so this never re-checks the
        condition - only whether the action is available *now*, the same
        split `why_cannot_play_land` makes between CR 305.1's construction
        rules and CR 305.2's turn-by-turn ones. Priority itself is not
        checked, for the identical reason `why_cannot_play_land` does not:
        this engine has no notion of a priority possession that persists
        between moves, so the caller is trusted to hold it.
        """
        player = self.player(username)
        if player.companion_id is None:
            return f"{username} has not chosen a companion (CR 702.139a)"
        if player.companion_action_used:
            return (
                f"{username} has already brought their companion into their hand "
                f"this game (CR 116.2g)"
            )
        assert self.turn is not None
        if self.turn.step not in MAIN_PHASES:
            return (
                f"{username} cannot bring a companion into their hand outside a main "
                f"phase of their turn (CR 116.2g); the turn is in {self.turn.step.value}"
            )
        if not self.stack_is_empty:
            return (
                f"{username} cannot bring a companion into their hand while the stack "
                f"is not empty (CR 116.2g)"
            )
        if username != self.turn.active_player:
            return (
                f"{username} cannot take this special action outside their own turn "
                f"(CR 116.2g); it is {self.turn.active_player}'s turn"
            )
        return None

    def begin_bringing_companion_to_hand(self: "Game", username: str) -> CostPayment:
        """Announce CR 116.2g's special action and open its `{3}` payment.

        Mirrors `begin_turning_face_up`'s two-call split for the same reason:
        paying can take more than one priority-free moment, and CR 116.1 lets
        a special action be taken any time its controller could take one, not
        only once the whole cost is already in hand. Raises if the action is
        unavailable at all, before anything has been spent.
        """
        self._refuse_if_over()
        refusal = self.why_cannot_bring_companion_to_hand(username)
        if refusal is not None:
            raise ValueError(refusal)
        return CostPayment.for_total(TotalCost.of("{3}"), game=self, payer=username)

    def bring_companion_to_hand(self: "Game", username: str) -> CardState:
        """Finish CR 116.2g: put the chosen companion into hand.

        The `{3}` is paid by the caller through `begin_bringing_companion_to_
        hand`; this is the half that actually moves the card and spends the
        once-per-game action. `Player.bring_into_the_game` is CR 400.11b's
        general "from outside the game" mover - the same one Karn, the Great
        Creator's `−2` uses (`_bring_in_from_outside_the_game_or_exile`) -
        so companion gets CR 108.3b's ownership check and CR 400.11a's zone
        check for free rather than a second copy of either.
        """
        self._refuse_if_over()
        refusal = self.why_cannot_bring_companion_to_hand(username)
        if refusal is not None:
            raise ValueError(refusal)
        player = self.player(username)
        assert player.companion_id is not None
        companion_state = self.find_by_id(player.companion_id)
        if not isinstance(companion_state, CardState):
            raise ValueError(f"{username}'s companion could not be found")
        with self._id_allocator_scope():
            player.bring_into_the_game(companion_state, Zone.HAND)
            player.companion_action_used = True
        return companion_state

    def basic_land_types_controlled(self: "Game", controller: str) -> frozenset[str]:
        """The basic land types (CR 305.6) among lands this player controls -
        *domain*, which CR 207.2c leaves as an ability word with no rules
        meaning of its own.

        CR 305.6: "The basic land types are Plains, Island, Swamp, Mountain,
        and Forest. If an object uses the words 'basic land type,' it's
        referring to one of these subtypes."

        Read off `characteristics_of`, not off the printed type line, because
        CR 613.1d's layer 4 is where a land *gains* a type: Dryad of the
        Ilysian Grove's "Lands you control are every basic land type in
        addition to their other types" makes one land worth all five, and
        counting the printing would miss it. A land whose types layer 4 has not
        touched reads back exactly what it prints, so nothing else changes.
        """
        return frozenset(
            subtype
            for permanent in self.permanents_controlled_by(controller)
            for chars in [self.characteristics_of(permanent)]
            if Type.LAND in chars.types
            for subtype in chars.subtypes
            if subtype in BASIC_LAND_TYPES
        )

    @classmethod
    def flash_grant_condition_of_line(cls, text: str) -> str | None:
        """`support.py`'s credit for `has_static_spells_flash_grant`: `None`
        when one printed static line is not `_CAST_SPELLS_AS_THOUGH_FLASH_RE`'s
        shape, `""` when it is and is unconditional, else its "as long as"
        condition (which that reader asks `condition_holds` about)."""
        match = cls._CAST_SPELLS_AS_THOUGH_FLASH_RE.fullmatch(
            cls._static_line_without_ability_word(text)
        )
        if match is None:
            return None
        return (match.group("condition") or "").strip()

    def has_first_spell_flash_grant(self: "Game", caster: str, spell: CardState) -> bool:
        """Whether some permanent `caster` controls grants `spell` CR
        702.8a's flash right now, through Radagast of Rhosgobel's own shape:
        "The first `<type>` spell you cast each turn costs `<N>` less to cast
        and can be cast as though it had flash." (`CostModifierEffect.
        grants_flash`, read off the identical static line `_counted_type_
        decrease` already prices the discount from - the same permanent, the
        same "first this turn" gate, CR 601.2f and CR 702.8a both answered
        off one printed sentence).

        `spell` has to carry one of the effect's own named types, and the
        caster must not already have cast a spell of those types this turn -
        the exact `first_each_turn` gate `_counted_type_decrease` uses for
        the discount, asked here with no discount to compute.

        Also true - additively, alongside the Radagast shape above - when
        `has_static_spells_flash_grant` finds a wider, type-agnostic grant
        (Captain Mar-Vell's own "Cosmic Awareness").
        """
        if self.has_static_spells_flash_grant(caster, spell):
            return True
        for permanent in self.permanents_controlled_by(caster):
            up_face_name = permanent.up_face_name or permanent.card.name
            for line in parse_abilities(permanent.card):
                if line.kind is not AbilityKind.STATIC or line.face != up_face_name:
                    continue
                effect = cost_modifier_effect((line.text or "").strip())
                if (
                    effect is None
                    or not effect.grants_flash
                    or effect.kind is not CostModifierKind.TYPE_DECREASE
                ):
                    continue
                if effect.applies_to_types and not any(
                    card_type in spell.types for card_type in effect.applies_to_types
                ):
                    continue
                if effect.first_each_turn and any(
                    any(card_type in earlier.types for card_type in effect.applies_to_types or ())
                    for earlier in self.spells_cast_this_turn.get(caster, [])
                ):
                    continue
                return True
        return False

    def modal_alternative_applies(
        self: "Game",
        modal: ModalProfile,
        controller: str,
        source_id: UUID | None,
        source_name: str,
        source: CardState | None = None,
        *,
        condition_override: bool | None = None,
    ) -> bool:
        """Whether a modal instruction's "If <condition>, [you may] choose N
        instead" raises its mode count right now (CR 700.2).

        False when the instruction prints no such sentence. A condition
        `condition_holds` does not read, or an alternative count
        `machines/modes.py` did not read, keeps the printed count and records a
        `ConditionalClauseNotice`: the larger count is a permission nobody
        checked, and granting it unchecked would let a spell do more than its
        caster is entitled to.

        `condition_override`, when not `None`, is used in place of asking
        `condition_holds` at all - `Casting._alternative_mode_count`'s own
        "this spell was kicked" (CR 601.4) reads its still-in-progress
        `self.kicked` this way, because `condition_holds` can only ever read
        the finalized `CastRecord` a completed `cast()` writes, which does
        not exist yet while modes are still being chosen.
        """
        condition = modal.alternative_condition
        if condition is None:
            return False
        if condition_override is not None:
            held: bool | None = condition_override
        else:
            held = (
                None
                if modal.alternative_minimum is None
                else self.condition_holds(controller, condition, source)
            )
        if held is None:
            notice = ConditionalClauseNotice(
                source_id=source_id,
                source_name=source_name,
                text=f"If {condition}, choose {modal.alternative_text or 'more'} instead",
            )
            if notice not in self.conditional_clause_notices:
                self.conditional_clause_notices.append(notice)
            return False
        return held


from ._common import _CAST_THIS_TURN_QUALITY_RE, _COLOR_COUNT_QUALITIES, _COLOR_WORDS  # noqa: E402
from ._conditions import _has_color_quality  # noqa: E402
from ._zones import entered_type_facts  # noqa: E402
from .records import CastRecord  # noqa: E402
