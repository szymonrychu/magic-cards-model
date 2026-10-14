import re
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING
from uuid import UUID

from ...data.card_names import is_card_name
from ...data.printing_pool import resolve_printing
from ...machines import combat as combat_rules
from ...machines.abilities import (
    TriggeredAbility,
    TriggerEvent,
    self_reference_names,
)
from ...machines.combat import (
    Attack,
)
from ...machines.cost import (
    ComponentKind,
    CostComponent,
    TotalCost,
    announce_count,
    cost_component_for_phrase,
    plan_mana_payment,
    total_cost_for_phrase,
)
from ...machines.counter_effects import event_count_target_text
from ...machines.decisions import (
    CardSplit,
    Decision,
    DecisionKind,
    DecisionPending,
    NamedManaAbility,
    PendingAbility,
    PendingDecision,
    ask_trigger_order,
    damage_assignment_answer,
    default_answer,
    legal_options,
    rule_for_kind,
    source_id_of,
)
from ...machines.delayed import (
    CopyEpicSpell,
    DelayedEffectSpec,
    DelayedTrigger,
    ParadigmCopyAndCast,
    copy_epic_spell,
    paradigm_copy_and_cast,
)
from ...machines.effects import (
    NO_FURTHER_MODES,
    UnmodeledTriggerEffectNotice,
    mode_effect_body,
)
from ...machines.ep02_r1_counter_amounts import counters_counted_for
from ...machines.keywords import (
    grant_enduring_stories,
    grant_the_citys_blessing,
    has_paradigm,
    why_cannot_dredge,
)
from ...machines.layers import (
    dont_cause_triggers_text,
)
from ...machines.modes import (
    ModalProfile,
    Mode,
)
from ...machines.monarch import inherent_triggers_for as monarch_inherent_triggers_for
from ...machines.speed import (
    check_speed_increase_on_life_loss,
)
from ...machines.targeting import (
    TargetingProfile,
    profile_for_text,
    reflexive_consequence_text,
)
from ...machines.trigger_doubling import without_suppressed
from ...machines.triggers import (
    AbilityOnStack,
    ExtraTriggerEvent,
    GameEvent,
    TargetingNotice,
    TargetingNoticeKind,
    state_triggers_for,
    triggered_abilities_of,
    triggers_for,
)
from ...machines.turn import (
    Step,
)
from ..card import (
    Layout,
    Supertype,
    Type,
)
from ..card_state import (
    CardState,
    ChoiceKind,
    Counter,
    TargetRef,
)
from ..mana import ManaCost, ManaSpend
from ..player import Player
from ..zone import Zone

if TYPE_CHECKING:
    from . import Game


_EXILE_CONDITIONED_TRIGGER: dict[object, bool] = {}


def _has_exile_conditioned_trigger(card: CardState) -> bool:
    """Whether a card in exile has a triggered ability whose intervening "if"
    says it is exiled (Darigaaz Reincarnated's "if this card is exiled with an
    egg counter on it", CR 113.6b): such a card is offered every event like a
    suspended one, and `zones_ability_functions_in` decides whether it really
    functions there. Memoised per printing."""
    key = card.card.id
    found = _EXILE_CONDITIONED_TRIGGER.get(key)
    if found is None:
        found = any(
            ability.intervening_if is not None
            and (
                "exiled" in ability.intervening_if.lower()
                or "in exile" in ability.intervening_if.lower()
            )
            for ability in triggered_abilities_of(card.card)
        )
        _EXILE_CONDITIONED_TRIGGER[key] = found
    return found


class TriggersDecisionsMixin:
    def create_delayed_trigger(self: "Game", trigger: DelayedTrigger) -> DelayedTrigger:
        """Create a delayed triggered ability (CR 603.7, 603.7a).

        The way in for `machines/effects.py`: a resolving spell or ability that
        says something will happen later builds one of these instead of doing it
        now. CR 603.7a is emphatic that the moment matters - "a delayed
        triggered ability won't trigger until it has actually been created, even
        if its trigger event occurred just beforehand" - so this is called
        during the resolution, not before it.

        CR 603.7d/e make the controller the controller of the spell or ability
        that created it, taken as that spell or ability resolved. The caller
        fills that in, because only the caller knows which it was.

        `trigger.id` is re-minted here rather than trusted from the caller:
        `DelayedTrigger.id`'s `default_factory=new_id` runs the moment the
        caller constructs it, which for `DelayedTrigger(text=..., ...)`
        written as this call's own argument is *before* the line below ever
        opens `_id_allocator_scope` - Python builds the argument first. A
        caller already inside another scope (`machines/effects.py`, mid-
        resolution) gets an id from that outer scope either way; one with
        none open - most of `tests/scenarios/`'s own direct `Game.
        create_delayed_trigger` calls - minted a bare `uuid4()` that survived
        nowhere else, so overwriting it here is free: nothing has read or
        stored the pre-mint id yet.
        """
        with self._id_allocator_scope():
            trigger = trigger.model_copy(update={"id": self._allocate_id()})
            return self.delayed_triggers.create(trigger)

    def create_reflexive_trigger(
        self: "Game",
        *,
        text: str,
        controller: str,
        source_id: UUID | None,
        source_name: str,
        callback: DelayedEffectSpec,
        subject_id: UUID | None = None,
        event: GameEvent | None = None,
    ) -> AbilityOnStack:
        """Create a reflexive triggered ability (CR 603.12) and queue it for
        the stack.

        `machines/effects.py`'s "you may sacrifice ... When you do, ..."
        clause is the way in: called only once the action it reflects has
        actually happened (Grist, the Hunger Tide's sacrifice), which is what
        lets `DelayedTriggers.create_reflexive` treat CR 603.12's "checked
        immediately after being created" as already satisfied rather than
        something to watch for.

        `subject_id` (CR 603.7c) is the particular object this reflexive
        ability refers to when it is not the creating ability's own source or
        target - Dain Ironfoot's "When you do, attach it to target creature
        you control." names the token the antecedent just created, which
        `ReflexiveAttachSubjectToTargetConsequence` reads back off this field
        rather than re-deriving it from printed text.

        `event` (optional, additive) carries the *creating* ability's own
        triggering event onto the reflexive `AbilityOnStack` - never onto the
        `DelayedTrigger` itself, which stays `event=None` exactly as CR
        603.12's docstring on `DelayedTrigger.event` already explains (there
        is nothing left to watch for). Leatherhead, Swamp Stalker's own
        "destroy target artifact or enchantment **that player** controls"
        needs this: `_that_player_of`/`TargetingProfile.for_event_player`
        (CR 603.3d's own target announcement, just below) read "that player"
        off `AbilityOnStack.event.player`, and a reflexive ability's own
        `DelayedTrigger.event` is never populated (there is no event left to
        wait for) - so without this, "that player" would come back unbound
        for a reflexive consequence that names one, wrongly letting *any*
        player's permanent be chosen. `None` (the default) is every existing
        caller's behaviour, unchanged.

        Appending straight to `pending_triggers` - the same queue `emit`
        fills for every ordinary trigger - is what makes `put_triggers_on_
        stack` pick this up the next time a player would receive priority
        (CR 603.3), asking its own targets then rather than now (CR 603.3d),
        and giving opponents a real stack object to respond to (CR 405.6a).
        """
        with self._id_allocator_scope():
            ability = self.delayed_triggers.create_reflexive(
                text=text,
                controller=controller,
                source_id=source_id,
                subject_id=subject_id,
                source_name=source_name,
                callback=callback,
            )
            if event is not None:
                # `model_copy` keeps `ability.id` unchanged, so `Delayed
                # Triggers.pending`'s existing `{ability.id: trigger}` entry
                # (set by `create_reflexive` above) still resolves this
                # ability to its trigger at resolution time - nothing else
                # to update.
                ability = ability.model_copy(update={"event": event})
            self.pending_triggers.append(ability)
            return ability

    def _resolve_epic(self: "Game", spell: CardState) -> None:
        """CR 702.50a: "Epic represents two spell abilities, one of which
        creates a delayed triggered ability." As a spell with epic resolves its
        controller can't cast spells for the rest of the game (CR 702.50b), and
        "at the beginning of each of your upkeeps for the rest of the game"
        (CR 603.7b, `remaining=None`) a copy of the spell is put on the stack
        (`CopyEpicSpell`). The copy that trigger makes is `epic_suppressed` and
        so makes neither; a spell that was countered or fizzled never resolved
        and does neither either (this runs only on resolution)."""
        if spell.epic_suppressed or not any(k.lower() == "epic" for k in spell.card.keywords):
            return
        controller = spell.controller or self.active_player.username
        self.player(controller).cannot_cast_spells_for_rest_of_game = True
        self.delayed_triggers.create(
            DelayedTrigger(
                text=(
                    "At the beginning of each of your upkeeps for the rest of the game, "
                    "copy this spell except for its epic ability. If the spell has any "
                    "targets, you may choose new targets for the copy."
                ),
                event=TriggerEvent.BEGINNING_OF_STEP,
                step=Step.UPKEEP,
                only_when_active=controller,  # CR 702.50a: "each of *your* upkeeps"
                remaining=None,  # CR 603.7b: "for the rest of the game"
                controller=controller,
                source_id=spell.id,
                source_name=spell.name,
                subject_id=spell.id,
                effect=(
                    CopyEpicSpell(
                        copy_of=spell.model_copy(deep=True),
                        cast_record=self.cast_record(spell).model_dump(mode="json"),
                    )
                    if spell.is_copy
                    else copy_epic_spell
                ),
            )
        )

    def _create_paradigm_delayed_trigger(self: "Game", spell: CardState) -> None:
        """CR 702.192a's own delayed trigger, the other half of Paradigm:
        "If this is the first time a spell you control with this spell's
        name has resolved this game, at the beginning of each of your
        precombat main phases for the rest of the game, create a copy of
        this object in exile. You may cast the copy without paying its mana
        cost."

        Created only once `put_into_graveyard` has already redirected this
        spell into exile because of its own Paradigm replacement
        (`machines/replacement._stack_replacements`), the same guard
        `_create_rebound_delayed_trigger` uses - `spell.zone is Zone.EXILE`
        confirms the replacement actually fired rather than merely that the
        card prints the keyword.

        "The first time ... has resolved this game" is read off whether a
        `ParadigmCopyAndCast` trigger for this exact (controller, name) pair
        already exists, rather than a separate counter: the trigger this
        method creates has `remaining=None` ("for the rest of the game"), so
        its own presence *is* the fact that a spell with this name already
        resolved once under this controller. A second resolution - a
        differently-cast, same-named copy from hand, or the delayed
        trigger's own free-cast copy resolving in turn - finds the existing
        trigger and creates no second one, which is what stops the number of
        copies created per turn from doubling every time one resolves.
        """
        if not has_paradigm(spell.card) or spell.zone is not Zone.EXILE:
            return
        controller = spell.controller or self.active_player.username
        name = spell.name
        already_triggered = any(
            isinstance(trigger.effect, ParadigmCopyAndCast)
            and trigger.controller == controller
            and trigger.source_name == name
            for trigger in self.delayed_triggers.triggers
        )
        if already_triggered:
            return
        self.delayed_triggers.create(
            DelayedTrigger(
                text=(
                    "At the beginning of each of your precombat main phases "
                    "for the rest of the game, create a copy of this object "
                    "in exile. You may cast the copy without paying its mana "
                    "cost."
                ),
                event=TriggerEvent.BEGINNING_OF_STEP,
                step=Step.PRECOMBAT_MAIN,
                only_when_active=controller,  # CR 702.192a: "each of *your* ..."
                remaining=None,  # CR 603.7b: "for the rest of the game"
                controller=controller,
                source_id=spell.id,
                source_name=name,
                subject_id=spell.id,
                expected_zone=Zone.EXILE,  # CR 603.7c
                expected_stamp=spell.zone_change_stamp,  # CR 603.7c parenthetical
                effect=paradigm_copy_and_cast,
            )
        )

    def _choose_cost_objects(
        self: "Game", cost: TotalCost, caster: str, card: CardState, taken: set[UUID]
    ) -> list[CardState]:
        """Ask `caster` which objects pay each component of `cost` that needs
        them (CR 601.2b announces them, CR 601.2h pays), in printed order.
        Raises `ValueError` when there are not enough (CR 118.3)."""
        chosen_all: list[CardState] = []
        for component in cost.components:
            pool = self._cost_candidates(component, caster)
            if pool is None or not component.required or component.cards:
                continue
            available = [state for state in pool if state.id not in taken]
            if len(available) < component.required:
                raise ValueError(
                    f"{caster} cannot pay {component.description or component.kind.value} "
                    f"to cast {card.name} (CR 118.3)"
                )
            answer = self.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=caster,
                    prompt=(
                        f"choose {component.required} to {component.kind.value} to cast {card.name}"
                    ),
                    source=card.name,
                    source_id=source_id_of(card),
                    amount=component.required,
                    cards=tuple(state.id for state in available),
                )
            )
            by_id = {state.id: state for state in available}
            chosen = [by_id[card_id] for card_id in answer]
            component.cards = chosen
            taken.update(state.id for state in chosen)
            chosen_all.extend(chosen)
        return chosen_all

    def may_cast_during_resolution(
        self: "Game",
        card: CardState,
        caster: str,
        *,
        prompt: str,
        source: str | None,
        source_id: str | None,
        source_name: str,
        rule: str,
        keyword: str | None = None,
        mana_value_below: float | None = None,
        play: bool = False,
        alternative_cost: TotalCost | None = None,
        pays_mana_cost: bool = False,
        transformed: bool = False,
        cost_reduction: int = 0,
    ) -> CardState | None:
        """A resolving "you may cast/play <card> without paying its mana cost"
        (CR 608.2d, CR 608.2g): one `MAY`, legal only when the cast or play is
        (`can_cast_during_resolution`), then `cast_during_resolution`.
        `pays_mana_cost` is the plain "you may cast the copy" with no
        "without paying" - see `cast_during_resolution`.

        `play=True` is the wider "play" (CR 601.1a): a land card is played,
        never cast (CR 305.9), through `_play_land_during_resolution`.
        `alternative_cost` is the "by paying [cost] rather than its mana cost"
        form instead (miracle, CR 702.94a) - see `cast_during_resolution`.
        Returns the spell or land, or `None` when nothing was cast or played.
        """
        is_land = play and card.card.is_land
        with self._back_face_up_if_cast_transformed(card, transformed):
            legal = (
                self._can_play_land_during_resolution(caster)
                if is_land
                else self.can_cast_during_resolution(
                    card, caster, mana_value_below=mana_value_below
                )
            )
            if not is_land:
                prompt = with_board_priced_cost(
                    self, prompt, card, caster, alternative_cost, pays_mana_cost
                )
        answer = self.ask(
            Decision(
                kind=DecisionKind.MAY,
                player=caster,
                prompt=prompt,
                source=source,
                source_id=source_id,
                affirmative_is_legal=legal,
                cards=(card.id,),
            )
        )
        if not answer:
            return None
        if is_land:
            return self._play_land_during_resolution(card, caster)
        return self.cast_during_resolution(
            card,
            caster,
            source_name=source_name,
            rule=rule,
            keyword=keyword,
            mana_value_below=mana_value_below,
            alternative_cost=alternative_cost,
            pays_mana_cost=pays_mana_cost,
            transformed=transformed,
            cost_reduction=cost_reduction,
        )

    def _ask_spell_modes(
        self: "Game", card: CardState, caster: str, modal: ModalProfile, taken: set[UUID]
    ) -> list[Mode]:
        """A modal spell's modes, asked as CR 601.2b announces them: only a
        legal mode is offered (CR 700.2a), once the minimum is met
        `NO_FURTHER_MODES` comes first (the shape `_announce_trigger_modes`
        uses), and an escalate spell offers a further mode only while its
        escalate cost's objects can still be paid (CR 702.120a, CR 118.3)."""
        offered = [mode for mode in modal.modes if self._spell_mode_is_legal(card, caster, mode)]
        minimum, maximum = modal.allowed_range(
            alternative=self.modal_alternative_applies(modal, caster, card.id, card.name, card)
        )
        if len(offered) < minimum:
            raise ValueError(f"{card.name} has too few legal modes to cast (CR 700.2a)")
        if modal.escalate_cost is not None:
            extra = total_cost_for_phrase(modal.escalate_cost, caster)
            capacity = 0
            if extra is not None:
                reserved = set(taken)
                while capacity < len(modal.modes) and self._cost_objects_available(
                    extra, caster, reserved
                ):
                    for component in extra.components:
                        pool = self._cost_candidates(component, caster) or []
                        free = [state for state in pool if state.id not in reserved]
                        reserved.update(state.id for state in free[: component.required])
                    capacity += 1
            maximum = min(maximum, 1 + capacity)
        chosen: list[Mode] = []
        while len(chosen) < maximum:
            remaining = [mode for mode in offered if modal.repeatable or mode not in chosen]
            if not remaining:
                break
            choices = tuple(mode.text for mode in remaining)
            if len(chosen) >= minimum:
                choices = (NO_FURTHER_MODES, *choices)
            answer = self.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_A_MODE,
                    player=caster,
                    prompt="choose a mode" if not chosen else "choose another mode",
                    source=card.name,
                    source_id=source_id_of(card),
                    options=choices,
                )
            )
            if answer == NO_FURTHER_MODES:
                break
            chosen.append(next((mode for mode in remaining if mode.text == answer), remaining[0]))
        return chosen

    def _note_unread_trigger(self: "Game", ability: AbilityOnStack) -> None:
        """Fail closed for a triggered ability that resolved with no effect.

        `_effect_of` answering None for a triggered ability with printed effect
        text means no reader exists for that text, not that the ability legally
        does nothing - Dress Down's end step trigger resolved as CHANGED
        NOTHING with no trace. Recorded as the ability resolves (nothing
        records it when it triggers), the same notice a resolving instant or
        sorcery with unread text leaves.
        """
        if not isinstance(ability.ability, TriggeredAbility) or not ability.ability.effect:
            return
        self.unmodeled_trigger_effect_notices.append(
            UnmodeledTriggerEffectNotice(
                source_id=ability.source_id,
                source_name=ability.source_name,
                text=ability.ability.effect,
            )
        )

    # -- events and triggered abilities (CR 603) ---------------------------

    def _enters_event(self: "Game", permanent: CardState) -> GameEvent:
        # CR 712.8f, 603.10: judged by the face that's actually up on the
        # battlefield (`CardState.types`/`.subtypes`, land-face aware), not
        # `permanent.card.types`'s front-face-only read - a Witch-Blessed
        # Meadow entering as a land is not a creature entering.
        #
        # CR 613.5 then has the layer system "continually and automatically"
        # applied, so the types and subtypes a trigger condition is judged
        # against are the *computed* ones, not the printed ones - exactly the
        # read `tapped_for_mana_event` and `mana_added_event` already document.
        # A Forest entering under Dryad of the Ilysian Grove ("Lands you
        # control are every basic land type in addition to their other types",
        # layer 4, CR 613.1d) really is a Mountain entering, which is what
        # Valakut, the Molten Pinnacle's "Whenever a Mountain you control
        # enters" has to see. `enter_the_battlefield` has already appended the
        # permanent and stamped its effects (CR 613.7a) before emitting this,
        # so the computed board is the post-entry one CR 603.10 asks about.
        types, subtypes = permanent.types, permanent.subtypes
        if permanent.zone is Zone.BATTLEFIELD:
            characteristics = self.characteristics_of(permanent)
            types, subtypes = characteristics.types, characteristics.subtypes
        return GameEvent(
            event=TriggerEvent.ENTERS_THE_BATTLEFIELD,
            subject_id=permanent.id,
            subject_name=permanent.name,
            subject_controller=permanent.controller,
            subject_card=permanent.card,
            subject_types=types,
            subject_subtypes=subtypes,
            player=permanent.controller,
        )

    def _emit_lore_counters_added(self: "Game", card_state: CardState, added: int) -> None:
        """CR 107.15a: a chapter ability triggers "when one or more lore
        counters are put onto this Saga" - CR 122.6 makes that true both for
        counters put on while already on the battlefield (`add_counters`) and
        for CR 714.3a's own intrinsic first one, put on as the Saga enters
        (`enter_the_battlefield`). Both routes call this with `added` set to
        how many just went on, and `machines/triggers.condition_matches`
        works out which of the Saga's own `TriggeredAbility.chapter`
        thresholds that crossed from the total already on it.
        """
        if added <= 0 or not card_state.is_saga or card_state.zone is not Zone.BATTLEFIELD:
            return
        self.emit(
            GameEvent(
                event=TriggerEvent.LORE_COUNTERS_ADDED,
                subject_id=card_state.id,
                subject_name=card_state.name,
                subject_controller=card_state.controller,
                subject_card=card_state.card,
                player=card_state.controller,
                amount=added,
            )
        )

    def _without_etb_suppressed(
        self: "Game", event: "GameEvent", triggered: list[AbilityOnStack]
    ) -> list[AbilityOnStack]:
        """`triggered` less what an entering-suppression grant stops -
        Torpor Orb's "Creatures entering don't cause abilities to trigger.";
        Karn, Argent Defender's "Artifacts and creatures entering the
        battlefield don't cause abilities to trigger."; Elesh Norn, Mother of
        Machines' "Permanents entering don't cause abilities of permanents your
        opponents control to trigger." CR 603.2's automatic trigger check is
        what this refuses, for the abilities that would otherwise fire off this
        one `ENTERS_THE_BATTLEFIELD` event - every one of them for an unscoped
        grant, whoever controls it; only those of permanents an opponent of the
        grant's controller controls for a scoped one.
        """
        if event.subject_id is None or not triggered:
            return triggered
        entering = self.find_by_id(event.subject_id)
        if not isinstance(entering, CardState):
            return triggered
        chars = self.characteristics_of(entering)
        entering_types: list[Type | None] = [None]
        entering_types += [card_type for card_type in chars.types]
        board = self.computed_board()
        for permanent in self.battlefield:
            abilities = board.of(permanent).abilities
            for card_type in entering_types:
                if dont_cause_triggers_text(card_type) in abilities:
                    return []
                if dont_cause_triggers_text(card_type, opponents_only=True) in abilities:
                    suppressor = board.of(permanent).controller
                    triggered = [
                        item
                        for item in triggered
                        if not self._ability_of_opponents_permanent(item, suppressor)
                    ]
        return triggered

    def emit_became_tapped(
        self: "Game",
        permanent: CardState,
        *,
        declared_attacker: bool = False,
        tapped_for_teamwork: bool = False,
    ) -> None:
        """Raise CR 701.26a's "becomes tapped" for `permanent`, which has just
        been tapped - by a cost, by a mana ability, by an effect, or by being
        declared as an attacker (CR 508.1f, `declared_attacker`), or to pay a
        teamwork cost (`tapped_for_teamwork`).

        The subject's types and subtypes are its *actual* ones (CR 613.5, off
        `characteristics_of`): "a creature you control becomes tapped"
        (Captain America, Living Legend) and "a Dwarf you control becomes
        tapped" (Magda, Brazen Outlaw) ask what it is now, not what it printed."""
        controller = self.controller_of(permanent).username
        chars = self.characteristics_of(permanent)
        self.emit(
            GameEvent(
                event=TriggerEvent.BECOMES_TAPPED,
                subject_id=permanent.id,
                subject_name=permanent.name,
                subject_controller=controller,
                subject_card=permanent.card,
                subject_types=chars.types,
                subject_subtypes=chars.subtypes,
                player=controller,
                declared_attacker=declared_attacker,
                tapped_for_teamwork=tapped_for_teamwork,
            )
        )

    def emit(self: "Game", event: GameEvent) -> list[AbilityOnStack]:
        """Something happened; work out what it triggered (CR 603.2).

        Nothing goes on the stack here. The abilities that triggered wait in
        `pending_triggers` until the next time a player would receive priority,
        which is CR 603.3 to the letter.

        Which objects are asked depends on the event. Normally it is everything
        on the battlefield. A cast trigger also asks the spells on the stack, so
        "When you cast this spell" can see itself. A dies trigger also asks the
        permanent that just left, because CR 603.10a has those triggers look
        back in time - and so do the other two events on that list, a permanent
        being sacrificed and a spell being countered (CR 603.10e), whose
        subjects have also moved by the time the trigger is worked out.
        """
        if event.event is TriggerEvent.BECOMES_TAPPED and event.subject_id is not None:
            # `became_tapped_count_this_turn`'s one write site (CR 701.26a) -
            # every `BECOMES_TAPPED` this engine ever emits passes through
            # here, from combat's attack-declaration tap, a cost's own
            # `ComponentKind.TAP` payment, or any future emitter, so Captain
            # America, Living Legend's "first time ... this turn" (`machines/
            # triggers.intervening_if_holds`) is answered off one count that
            # can never drift from what the trigger itself is watching,
            # rather than a second tally each tap site would have to
            # remember to keep in step.
            self.became_tapped_count_this_turn[event.subject_id] = (
                self.became_tapped_count_this_turn.get(event.subject_id, 0) + 1
            )
        if event.event is TriggerEvent.LOSES_LIFE and event.player is not None:
            # CR 702.179d's own inherent triggered ability: "Whenever one or
            # more opponents lose life during your turn ... your speed
            # increases by 1." Every `LOSES_LIFE` this engine ever emits
            # passes through here, the same "every emitter, one write site"
            # shape `became_tapped_count_this_turn` just above already uses.
            check_speed_increase_on_life_loss(self, event.player)
        if (
            event.event
            in (
                TriggerEvent.LEAVES_THE_BATTLEFIELD,
                TriggerEvent.LEAVES_BATTLEFIELD_TO_HAND,
                TriggerEvent.LEAVES_BATTLEFIELD_TO_EXILE,
            )
            and event.subject_types is None
            and event.subject_id in self._left_battlefield_characteristics
        ):
            # CR 603.10a: "When another creature you control leaves the
            # battlefield" asks what the object was as it left - a bounce or
            # an exile reaches here with no types stamped on it.
            left = self._left_battlefield_characteristics[event.subject_id]
            event = event.model_copy(
                update={"subject_types": left.types, "subject_subtypes": left.subtypes}
            )
        if self._paying_cost is not None and event.during_cost_of is None:
            what, keyword, payer = self._paying_cost
            event = event.model_copy(
                update={
                    "during_cost_of": what,
                    "during_cost_keyword": keyword,
                    "during_cost_player": payer,
                }
            )
        with self._id_allocator_scope():
            # CR 702.131b's "any time" and CR 702.131d's "before the game
            # checks ... trigger conditions": a player who has just come to
            # control a tenth permanent has the city's blessing before anything
            # below reads the event, and before the rest of a resolving effect
            # asks about it.
            grant_the_citys_blessing(self)
            # CR 702.195a's "any time" and CR 702.195c's "before the game
            # checks ... trigger conditions" - storied's enduring story, the
            # same timing as the city's blessing above.
            grant_enduring_stories(self)
            # The turn-history condition readers' own ledger hook
            # (`machines/conditions/history.record`): every event is noted as
            # it happens, before any trigger condition below is read, so an
            # intervening "if" about this turn (CR 603.4) already sees it.
            from ...machines.conditions import history as condition_history

            condition_history.record(self, event)
            sources: list[CardState] = list(self.battlefield)
            # CR 113.6m: "An ability whose cost or effect specifies that it moves
            # the object it's on out of a particular zone functions only in that
            # zone" - Arclight Phoenix's "At the beginning of combat on your turn,
            # ... return this card from your graveyard to the battlefield" is one,
            # and a graveyard card was never asked about any event at all, so it
            # could not fire. Every card in every graveyard is offered here and
            # `machines/triggers.triggers_for` filters on
            # `zones_ability_functions_in`, which still answers "battlefield" for
            # everything that has not earned otherwise - so this widens what is
            # *asked*, never what triggers.
            for player in self.players:
                sources.extend(player.graveyard)
            # CR 702.62a: "The second and third [suspend abilities] are
            # triggered abilities that function in the exile zone." Nothing in
            # exile was ever offered here, so a suspended card was never asked
            # about `TriggerEvent.BEGINNING_OF_STEP` and its time counters
            # only ever came off when a caller removed one by hand.
            #
            # Deliberately *not* the whole exile pile the way the graveyards
            # above are. Exile is one shared zone (`Game.shared_zones`) holding
            # every foretold, plotted, madness-discarded, cascaded and
            # hidden-away card in the game, and offering all of them would ask
            # each about every event that ever happens. CR 702.62b's own
            # three-clause definition of "suspended" - "in the exile zone, has
            # suspend, and has a time counter on it", which is exactly
            # `CardState.is_suspended` - is the filter, so the widening stays
            # the size of the rule that needed it.
            sources.extend(
                card
                for card in self.exile
                if card.is_suspended or _has_exile_conditioned_trigger(card)
            )
            # CR 114.4: "Abilities of emblems function in the command zone."
            sources.extend(
                state
                for state in self.shared_zones[Zone.COMMAND]
                if isinstance(state, CardState) and state.card.layout is Layout.EMBLEM
            )
            if event.event is TriggerEvent.CAST_SPELL:
                sources = self.spells_on_stack + sources
            elif (
                event.event
                in (
                    TriggerEvent.DIES,
                    TriggerEvent.IS_SACRIFICED,
                    TriggerEvent.SPELL_IS_COUNTERED,
                    TriggerEvent.LEAVES_BATTLEFIELD_TO_EXILE,
                    TriggerEvent.LEAVES_THE_BATTLEFIELD,
                    # CR 702.62a's third ability, "When the last time counter
                    # is removed from this card": by the time the event is
                    # raised the card has no time counters left, so CR
                    # 702.62b no longer calls it suspended and the widening
                    # above has already stopped offering it. The card is
                    # named as the event's own subject and asked here for the
                    # same reason the four departures above are - the state
                    # the condition is about is the state it was in a moment
                    # ago.
                    ExtraTriggerEvent.LAST_TIME_COUNTER_REMOVED,
                )
                and event.subject_id is not None
            ):
                gone = self.find_by_id(event.subject_id)
                if isinstance(gone, CardState) and gone not in sources:
                    sources = [*sources, gone]
            elif event.event is TriggerEvent.LEAVES_BATTLEFIELD_TO_HAND:
                # CR 603.10a: every permanent returned by this one event looks
                # back, itself included, though each is in a hand by now.
                for returned in self._returned_to_hand_batch or (event,):
                    gone = (
                        self.find_by_id(returned.subject_id)
                        if returned.subject_id is not None
                        else None
                    )
                    if isinstance(gone, CardState) and gone not in sources:
                        sources = [*sources, gone]

            triggered = triggers_for(self, event, sources)
            if event.event is TriggerEvent.ENTERS_THE_BATTLEFIELD:
                # Torpor Orb / Karn, Argent Defender / Elesh Norn: CR 603.2's
                # automatic trigger check never fires for what this entrance
                # is stopped from causing - on the entering permanent or on
                # any other.
                triggered = self._without_etb_suppressed(event, triggered)
            triggered = without_suppressed(self, event, triggered)
            # CR 603.7: a delayed triggered ability is not printed on any card, so
            # no source can be asked for it. It watches the event directly, and once
            # it has triggered it is an ordinary trigger in every other respect -
            # CR 603.3 puts it on the stack the next time a player would receive
            # priority, alongside these.
            triggered = triggered + self.delayed_triggers.fire(event, self)
            # CR 725.2: the monarch's own two inherent triggered abilities are
            # not printed on any card either - "these triggered abilities have
            # no source" - so they watch every event directly the same way a
            # delayed trigger does, rather than through anything on the
            # battlefield or in a graveyard `sources` above could have offered.
            triggered = triggered + monarch_inherent_triggers_for(self, event)
            # CR 603.8: a state trigger watches a game state, not an event, so it
            # is swept for after every event rather than matched against one. This
            # is what lets a countered state trigger fire again immediately - the
            # counter event is emitted from `Game.counter` after the ability has
            # already been removed from the stack (CR 701.6a).
            triggered = triggered + state_triggers_for(self)
            self.pending_triggers.extend(triggered)
            return triggered

    def _trigger_mode_is_legal(self: "Game", ability: AbilityOnStack, mode: Mode) -> bool:
        """CR 603.3c's legality of one mode: a mode whose mandatory target has
        no legal candidate "can't be chosen". A target this engine cannot read
        is not treated as unavailable - `_ask_targets` records that gap."""
        profile = profile_for_text(mode_effect_body(mode))
        if not profile.understood or not profile.requirements or profile.min_targets == 0:
            return True
        return bool(self._legal_target_candidates(profile, ability.controller, ability.source_id))

    def _order_triggers_by_controller(
        self: "Game", ordered: list[AbilityOnStack]
    ) -> list[AbilityOnStack]:
        """CR 603.3b's second half: each controller orders their own block.

        "First, each player, in APNAP order, puts each triggered ability they
        control on the stack in any order they choose." `apnap_order` settles
        which player's block goes on first and no more than that - within one
        block the order is the player's, and until this existed it was the
        order the abilities happened to trigger in, which nobody was asked
        about.

        `apnap_order` is a stable sort by seat, so one controller's abilities
        are already contiguous; each run is handed to `ask_trigger_order` and
        re-laid in the answer, bottom of the stack first. A block of one is not
        a choice and `ask_trigger_order` does not ask about it; an unscripted
        block of several keeps the order it triggered in, which is what
        `default_answer` returns, so nothing moves unless a caller says so.
        """
        result: list[AbilityOnStack] = []
        index = 0
        while index < len(ordered):
            stop = index
            while stop < len(ordered) and ordered[stop].controller == ordered[index].controller:
                stop += 1
            block = ordered[index:stop]
            index = stop
            if len(block) < 2:
                result.extend(block)
                continue
            by_id = {ability.id: ability for ability in block}
            # Two copies of one card is the ordinary case for this question,
            # so the source name alone does not distinguish the options - each
            # `PendingAbility` carries the ability's own source id and text
            # too. Nothing downstream can recover them from the board: CR
            # 603.3b is asked one step before CR 603.3 puts these on the
            # stack, so at this moment they are in no zone at all and this
            # frame is the only thing still holding them.
            chosen = ask_trigger_order(
                self.decisions,
                block[0].controller,
                tuple(
                    PendingAbility(
                        id=ability.id,
                        source_id=source_id_of(ability),
                        source_name=ability.source_name,
                        text=ability.ability.text,
                        controller=ability.controller,
                    )
                    for ability in block
                ),
            )
            result.extend(by_id[ability_id] for ability_id in chosen)
        return result

    def _emit_ability_becomes_target(self: "Game", ability: AbilityOnStack) -> None:
        """The objects this ability targeted have become targets (CR 115.1).

        "Some spells and abilities require their controller to choose one or
        more targets for them ... These targets are declared as part of the
        process of putting the spell or ability on the stack." CR 115.1c is the
        activated half ("An activated ability is targeted if it identifies
        something it will affect by using the phrase 'target [something]'") and
        CR 603.3d the triggered half, and both land here: `machines/casting.
        Casting._emit_becomes_target` is the spell-only twin of this, and
        nothing raised the event for an ability's targets at all, so ward
        (CR 702.21a) never saw an activated ability coming and Loki, God of
        Mischief's "becomes the target of an ability you control" could not
        fire.

        Raised once the ability is already on the stack, for two reasons: the
        targets are settled at that point (CR 602.2b imports CR 601.2c
        wholesale for an activated ability), and `machines/triggers.
        _becomes_target_names_ability` tells an ability apart from a spell by
        looking `targeted_by` up among `Game.abilities_on_stack` - an id that
        is not there yet reads as a spell.

        Only permanents are asked. CR 110.1: "A permanent is a card or token on
        the battlefield", so an object anywhere else is not one - the same
        filter the spell twin applies, since every condition in this pool is
        about a permanent (or a player, which carries no `card_id` to ask
        about) becoming a target.

        CR 700.13's crime is committed here too, for every kind of target: an
        ability activated or put on the stack that targets an opponent, what an
        opponent controls, or a card in an opponent's graveyard.
        """
        from ...machines.conditions import history as condition_history

        condition_history.record_crime(self, ability.controller, ability.targets)
        for target in ability.targets:
            if target.username is not None and not target.is_card:
                # CR 115.1: a player can be targeted too ("you or another
                # permanent you control becomes the target of ...").
                self.emit(
                    GameEvent(
                        event=TriggerEvent.BECOMES_TARGET,
                        subject_name=target.username,
                        subject_controller=target.username,
                        targeted_by=ability.id,
                        player=ability.controller,
                    )
                )
                continue
            if not target.is_card or target.card_id is None:
                continue
            targeted = self.find_by_id(target.card_id)
            if targeted is None or targeted.zone not in (Zone.BATTLEFIELD, Zone.STACK):
                continue
            self.emit(
                GameEvent(
                    event=TriggerEvent.BECOMES_TARGET,
                    subject_id=targeted.id,
                    subject_name=targeted.name,
                    subject_controller=(
                        targeted.controller
                        if targeted.zone is Zone.BATTLEFIELD
                        else self.controller_of(targeted).username
                    ),
                    subject_card=targeted.card,
                    targeted_by=ability.id,
                    player=ability.controller,
                )
            )

    def _ask_trigger_targets(self: "Game", ability: AbilityOnStack) -> list[TargetRef] | None:
        """Ask a triggered ability's own controller for its targets (CR 603.3d).

        "The remainder of the process for putting a triggered ability on the
        stack is identical to the process for casting a spell listed in rules
        601.2c-601.2d" - so this is CR 601.2c's target announcement, put to
        `ability.controller` through the ordinary `Game.ask` `CHOOSE_TARGETS`
        question, with the legal candidates worked out by
        `TargetRequirement.rejects` - the same checker `activate_ability` and
        `choose_trigger_targets` already use.

        Three things can leave this with no targets, and something to say
        about why, recorded on `targeting_notices` rather than silently
        returned as if nothing were amiss (the DDR#978-shaped defect: an
        ability that does nothing looks identical to one with nothing to
        point at):

        - the restriction itself could not be read at all
          (`TargetingProfile.understood` is False) - `TargetingNoticeKind.UNPARSED`,
          an engine gap this returns `[]` for, same as ever;
        - nothing on the battlefield satisfies it right now, but the
          requirement was optional anyway (CR 115.6's "up to N", CR 107.1c's
          "any number of" - `profile.min_targets` is 0) -
          `TargetingNoticeKind.NO_LEGAL_TARGET`, a legal game state
          (CR 608.2d's own "nobody says otherwise" default), not a bug -
          returns `[]`, and the ability still goes on the stack choosing
          nothing;
        - nothing satisfies it and the requirement was mandatory
          (`profile.min_targets` > 0, a plain "target permanent" with no
          "up to") - CR 603.3d: "if a choice is required when the triggered
          ability goes on the stack but no legal choices can be made for it,
          ... the ability is simply removed from the stack." Returns `None`
          so the caller never places it, rather than the pre-fix behaviour of
          putting it on the stack anyway with an empty target list, where it
          would sit doing nothing while still occupying a stack slot CR
          603.3d says it should never have taken.

        An ability with no targeting requirement at all is not asked anything
        and gets no notice either - there is nothing to be silent about.
        """
        profile, text = self._trigger_target_profile(ability)
        return self._ask_targets(
            profile, ability.controller, ability.source_id, ability.source_name, text
        )

    def _trigger_target_profile(
        self: "Game", ability: AbilityOnStack
    ) -> tuple[TargetingProfile, str]:
        """The targeting profile (and the text it was read from) a triggered
        ability announces its targets under (CR 603.3d)."""
        printed = ability.ability
        text = printed.text if isinstance(printed, TriggeredAbility) else ""
        # CR 603.12: when this ability *is itself* the reflexively created
        # one - its own printed text opens with "When you do," (or "when ...
        # this way,") rather than merely containing that clause somewhere
        # inside a larger antecedent - `profile_for_text`'s own
        # `_REFLEXIVE_CLAUSE_TAIL` cut (deliberately built for the *outer*
        # ability's own announcement, so it never claims a target that
        # belongs to a reflexive ability not yet created) would otherwise
        # strip the *entire* text here, since there is no antecedent in
        # front of it to leave behind - Dain Ironfoot's own "When you do,
        # attach it to target creature you control." always read as "no
        # target" this way, so the Equipment token it just created never
        # attached to anything. `reflexive_consequence_text` reads the exact
        # same words `profile_for_text` would have thrown away; using them
        # here is not new latitude, only reading them for the one ability
        # they actually belong to instead of discarding them.
        if re.match(r"^\s*(?:when you do|when [^,]+ this way)\s*,", text, re.IGNORECASE):
            consequence = reflexive_consequence_text(text)
            if consequence is not None:
                text = consequence
        elif isinstance(printed, TriggeredAbility) and printed.effect:
            # CR 603.1/601.2c: only the ability's own *effect* can name a
            # target it announces as it goes on the stack - the trigger
            # *condition* in front of it (CR 603.2) describes what already
            # happened, not what this ability itself points at. Speedball,
            # New Warrior's own "Whenever a player casts a spell that
            # targets Speedball, he gets +2/+2 ..." is the case that needs
            # this: scanning the whole text let `profile_for_text` misread
            # "targets Speedball" (a CR 201.5 self-reference sitting inside
            # the *condition*) as this ability's own "target <subtype>
            # creature" requirement - a mandatory target with no legal
            # candidate, which then removed the whole ability from the
            # stack outright (CR 603.3d) before its real, targetless effect
            # ever ran. `TriggeredAbility.effect` is already split off the
            # condition by `machines/abilities.py`'s own parser, so this
            # reuses that split instead of re-deriving it here.
            text = printed.effect
        # Heroic Feast's "choose up to that many target creatures": CR 601.2c
        # (via CR 603.3d) fixes the number as it goes on the stack, and "that
        # many" is what the triggering event carried.
        text = event_count_target_text(text, ability.event)
        # CR 107.3m: an ETB trigger's X is the X its spell was cast with -
        # read into the targets too ("target artifact with mana value X or
        # less", Thieving Skydiver), not only into the effect.
        text = self.etb_x_substituted(ability, text) or text
        source_card = ability.source_or_last_known(self)
        if source_card is not None:
            text = counters_counted_for(
                text,
                source_card,
                self_reference_names(
                    ability.source_name, legendary=Supertype.LEGENDARY in source_card.supertypes
                ),
            )
        profile = (
            profile_for_text(text)
            .for_event_player(_that_player_of(ability))
            .for_defending_player(self._defending_player_of(ability))
        )
        subject_card = ability.event.subject_card if ability.event is not None else None
        if subject_card is not None:
            power = str(subject_card.power) if subject_card.power is not None else ""
            profile = profile.for_event_subject(
                mana_value=subject_card.cmc,
                power=int(power) if power.lstrip("-").isdigit() else None,
            )
        return profile, text

    def stamp_target_slots(
        self: "Game",
        profile: TargetingProfile,
        refs: list[TargetRef],
        controller: str,
        source_id: UUID | None,
    ) -> list[TargetRef]:
        """Record on each announced target which of `profile`'s requirements it
        filled (CR 601.2c, via CR 602.2b / CR 603.3d), as a cast does.

        Only an ability with several requirements has anything to tell apart;
        resolution then judges each target against the requirement it was
        announced under (CR 608.2b) instead of replaying the placement on a
        board that may have changed - a source whose controller changed in
        response would otherwise be placed into a different requirement.
        """
        if not profile.understood or len(profile.requirements) < 2 or not refs:
            return refs
        slots = profile.assign_slots(
            [self.resolve_target(ref) for ref in refs], controller, self, source_id
        )
        return [
            ref if slot is None else ref.model_copy(update={"slot": slot})
            for ref, slot in zip(refs, slots, strict=True)
        ]

    def _ask_targets(
        self: "Game",
        profile: TargetingProfile,
        controller: str,
        source_id: UUID | None,
        source_name: str,
        text: str,
        *,
        excluding: set[TargetRef] | None = None,
    ) -> list[TargetRef] | None:
        """Ask `controller` for `profile`'s targets, addressed to `source_name` (CR 601.2c).

        `excluding` is a set of targets that may not be offered at all - the
        players an earlier mode of the same modal ability already aimed at,
        when "each mode must target a different player" (Shadrix Silverquill).

        The shared machinery behind both halves of CR 602.2b/603.3d's "the
        remainder of the process ... is identical to the process for casting a
        spell": a triggered ability's own announcement (`_ask_trigger_targets`)
        and an activated ability's, when its caller supplies no targets
        (`Game.activate_ability`). Both ask through the ordinary `CHOOSE_TARGETS`
        question, with the legal candidates worked out by `_legal_target_candidates`
        - the same checker `machines/targeting.py`'s `TargetingProfile.check`
        already uses - so this module does not grow a second target grammar.

        Three things can leave this with no targets, and something to say
        about why, recorded on `targeting_notices` rather than silently
        returned as if nothing were amiss (the DDR#978-shaped defect: an
        ability that does nothing looks identical to one with nothing to
        point at):

        - the restriction itself could not be read at all
          (`TargetingProfile.understood` is False) - `TargetingNoticeKind.UNPARSED`,
          an engine gap this returns `[]` for, same as ever;
        - nothing on the battlefield satisfies it right now, but the
          requirement was optional anyway (CR 115.6's "up to N", CR 107.1c's
          "any number of" - `profile.min_targets` is 0) -
          `TargetingNoticeKind.NO_LEGAL_TARGET`, a legal game state
          (CR 608.2d's own "nobody says otherwise" default), not a bug -
          returns `[]`, and the ability still goes on the stack choosing
          nothing;
        - nothing satisfies it and the requirement was mandatory
          (`profile.min_targets` > 0, a plain "target permanent" with no
          "up to") - `None`, so the caller never puts the ability where it
          would sit doing nothing: CR 603.3d removes a triggered ability from
          the stack in this case, and CR 601.2e/602.2b makes an activation
          with no legal target for a mandatory requirement illegal to begin
          at all (the same refusal `Game.cast_during_resolution` already gives
          a spell with no legal target, CR 601.2c).

        An ability with no targeting requirement at all is not asked anything
        and gets no notice either - there is nothing to be silent about.
        """
        if not profile.understood:
            self.targeting_notices.append(
                TargetingNotice(
                    kind=TargetingNoticeKind.UNPARSED,
                    source_id=source_id,
                    source_name=source_name,
                    text=text,
                )
            )
            return []
        if not profile.requirements:
            return []

        candidates = self._legal_target_candidates(profile, controller, source_id)
        if excluding:
            candidates = [c for c in candidates if TargetRef.coerce(c) not in excluding]
        if not candidates:
            self.targeting_notices.append(
                TargetingNotice(
                    kind=TargetingNoticeKind.NO_LEGAL_TARGET,
                    source_id=source_id,
                    source_name=source_name,
                    text=text,
                )
            )
            return None if profile.min_targets > 0 else []

        minimum = min(profile.min_targets, len(candidates))
        across = any(
            r.distinct_controllers
            or r.share_a_card_type
            or r.share_a_creature_type
            or r.distinct_names
            or r.total_mana_value_at_most is not None
            for r in profile.requirements
        )
        if any(r.distinct_controllers for r in profile.requirements):
            # "controlled by different players" (Kitsune, Dragon's Daughter's
            # exchange): each controller's first candidate leads, so the
            # default answer is a legal pair; with fewer controllers than
            # targets required there is no legal choice at all, and CR
            # 603.3d (via CR 601.2c) removes the ability from the stack.
            firsts_by_controller: dict[str, Targetable | AbilityOnStack] = {}
            for candidate in candidates:
                if isinstance(candidate, CardState) and candidate.zone is Zone.BATTLEFIELD:
                    firsts_by_controller.setdefault(
                        self.controller_of(candidate).username, candidate
                    )
            if len(firsts_by_controller) < profile.min_targets:
                self.targeting_notices.append(
                    TargetingNotice(
                        kind=TargetingNoticeKind.NO_LEGAL_TARGET,
                        source_id=source_id,
                        source_name=source_name,
                        text=text,
                    )
                )
                return None
            leading_pair = list(firsts_by_controller.values())
            candidates = leading_pair + [c for c in candidates if c not in leading_pair]
        if any(r.one_per_opponent for r in profile.requirements):
            # CR 601.2c: one target per opponent with a legal choice. Each
            # controller's first candidate leads, so the default answer (the
            # first `target_minimum` offered) is already one per opponent.
            firsts: dict[str, Targetable | AbilityOnStack] = {}
            for candidate in candidates:
                owner = getattr(candidate, "controller_or_owner", None)
                if isinstance(owner, str):
                    firsts.setdefault(owner, candidate)
            leading = list(firsts.values())
            candidates = leading + [c for c in candidates if c not in leading]
            minimum = len(leading)
        chooser = controller
        if any(r.chosen_by_opponent for r in profile.requirements):
            # "of an opponent's choice" (Mausoleum Turnkey): the target is
            # still announced as the ability goes on the stack (CR 603.3d), but
            # an opponent of its controller makes the choice.
            chooser = next(
                (p.username for p in self.players if p.username != controller), controller
            )
        decision = Decision(
            kind=DecisionKind.CHOOSE_TARGETS,
            player=chooser,
            prompt=f"choose targets for {source_name}",
            source=source_name,
            source_id=source_id_of(source_id),
            targets=tuple(TargetRef.coerce(candidate) for candidate in candidates),
            target_maximum=profile.max_targets,
            target_minimum=minimum,
        )
        chosen = self.ask(decision)
        assert isinstance(chosen, (list, tuple))
        if across:
            # `ask` checks each target and the count; a rule across targets
            # ("controlled by different players", one per opponent) is
            # `TargetingProfile.check`'s, judged on the objects themselves.
            by_id = {TargetRef.coerce(c): c for c in candidates}
            profile.check([by_id.get(ref, ref) for ref in chosen], controller, self, source_id)
        return self.stamp_target_slots(
            profile, [TargetRef.coerce(ref) for ref in chosen], controller, source_id
        )

    def choose_trigger_targets(self: "Game", card_name: str, targets: list[object]) -> None:
        """Say what a card's triggered ability will target when it goes on the stack.

        CR 603.3d: choosing a trigger's targets is part of putting the ability
        on the stack and "follows the rules for announcing targets" - which is
        CR 601.2c, the same check a spell's targets get. So the choice is
        refused here rather than recorded and discovered to be illegal later:
        `machines/targeting.py` reads the ability's own text through
        `profile_for_text`, because `targeting_profile` answers for the *spell*
        and drops the lines belonging to an ability (CR 113.1c).

        A card with no readable targeting ability is not checked, the same way
        an unreadable spell is not - see `docs/engine-coverage.md`.
        """
        refusal = self.why_cannot_target_with_trigger(card_name, targets)
        if refusal is not None:
            raise ValueError(refusal)
        self.trigger_targets[card_name] = [TargetRef.coerce(target) for target in targets]

    def _trigger_source_named(self: "Game", card_name: str) -> CardState | None:
        """The object a named card's trigger would come from, if it is here.

        CR 603.6a puts an enters-the-battlefield trigger's source on the
        battlefield; a cast trigger's source is the spell on the stack
        (CR 603.2g). Both are searched, front face first, matching how
        `_targets_for_trigger` reads the same key back out.
        """
        front = card_name.split("//")[0].strip()
        for state in [*self.battlefield, *self.spells_on_stack]:
            if state.name in (card_name, front) or state.name.split("//")[0].strip() == front:
                return state
        return None

    def _ask_opening_hand_actions_of(self: "Game", player: Player) -> list[Decision]:
        """Put every CR 103.6 action on offer to one player, in hand order.

        Every action is optional - "may take any such actions" - so every one is
        a `DecisionKind.OPENING_HAND_ACTION` question and an unscripted player
        declines (see `machines/decisions.py`). A player holding no card that
        offers one is asked nothing at all.
        """
        asked: list[Decision] = []
        for decision, action, card_state in self._opening_hand_offers(player):
            if card_state.zone is not Zone.HAND:
                # An earlier action already moved it out of the opening hand;
                # CR 103.6a/103.6b both act on a card *in* the hand.
                continue
            asked.append(decision)
            if self.ask(decision) is not True:
                continue
            self._perform_opening_hand_action(action, card_state, player)
        return asked

    def ask(self: "Game", decision: Decision) -> object:
        """Put one question to a player and get the answer back (CR 608.2d).

        "If an effect of a spell or ability offers any choices other than
        choices already made as part of casting the spell, activating the
        ability, or otherwise putting the spell or ability on the stack, the
        player announces these while applying the effect. The player can't
        choose an option that's illegal or impossible."

        That second sentence is enforced here and is the reason this is a method
        rather than a lookup: a scripted answer naming an illegal option is
        refused with the rule that makes it illegal, and an absent answer falls
        through to `default_answer`, which never returns one.

        A question whose only option is "no" - the shockland at 1 life, where
        CR 119.4 forbids the payment - has its answer forced rather than chosen.
        It is still recorded in `decisions.asked`, with
        `affirmative_is_legal` False, because "there was nothing to decide" is a
        fact a scenario may want to assert.

        A scripted answer always wins; failing that, the replay tape
        (`decisions.recorded`, see `machines/decisions.py`'s "Pausing instead
        of blocking") is read next, and only once neither has anything - no
        unconsumed tape entry either - does this raise `DecisionPending`
        (when `decisions.pause_when_unanswered` is set) or, failing that too,
        let `default_answer` speak for the player.

        Every `CHOOSE_CARDS` question is labelled on its way through here - see
        `_with_card_labels` - so a client is never handed a list of ids naming
        cards it cannot see.
        """
        if self.is_over:
            # CR 104.1: the game has ended, so no question is put to anybody -
            # nothing is recorded, nothing pauses, and the rest of a resolution
            # that ended the game reads the documented default.
            return default_answer(decision)
        decision = self._with_card_labels(decision)
        self.decisions.asked.append(decision)
        allowed = legal_options(decision)
        found, value = self.decisions.take(decision)
        if not found:
            found, value = self.decisions.take_from_tape(decision)
        if not found and self.decisions.pause_when_unanswered:
            raise DecisionPending(
                PendingDecision(
                    seq=len(self.decisions.asked) - 1,
                    decision=decision,
                    rule=rule_for_kind(decision.kind),
                )
            )
        if not found:
            return default_answer(decision)

        if decision.kind is DecisionKind.PAY_MANA and isinstance(value, tuple):
            # CR 608.2g / CR 605.3a: paying, and naming the mana sources to
            # activate while doing it. Every id must have been offered; a
            # `NamedManaAbility` (a mana ability of any cost) is checked by
            # activating it, which refuses in the engine's own words.
            if not all(isinstance(entry, UUID | NamedManaAbility) for entry in value):
                raise ValueError(f"{decision.prompt}: needs a tuple of mana source ids")
            offered = set(decision.mana_sources)
            stray = [
                str(entry) for entry in value if isinstance(entry, UUID) and entry not in offered
            ]
            if stray:
                raise ValueError(
                    f"{decision.prompt}: {', '.join(stray)} is not one of the mana sources "
                    f"{decision.player} can activate while paying (CR 605.3a)"
                )
            named = any(isinstance(entry, NamedManaAbility) for entry in value)
            if True not in allowed and not named:
                # `affirmative_is_legal` counts the offered `{T}` sources only;
                # an answer naming mana abilities of any cost is judged by the
                # payment itself (CR 118.3), which refuses what it cannot pay.
                raise ValueError(_illegal_option_refusal(decision))
            return value

        if decision.kind in (
            DecisionKind.MAY,
            DecisionKind.PAY_LIFE,
            DecisionKind.PAY_ENERGY,
            DecisionKind.PAY_MANA,
        ):
            if not isinstance(value, bool):
                raise ValueError(f"{decision.prompt}: a yes-or-no question needs a bool answer")
            if value not in allowed:
                raise ValueError(_illegal_option_refusal(decision))
            return value

        if decision.kind is DecisionKind.PAY_ENERGY_AMOUNT:
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError(f"{decision.prompt}: needs an integer amount of energy")
            if value < 0 or value > decision.amount:
                raise ValueError(
                    f"{decision.prompt}: cannot pay {value} energy, only {decision.amount} "
                    f"available (CR 118.3, CR 107.14)"
                )
            return value

        if decision.kind is DecisionKind.PAY_LIFE_AMOUNT:
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError(f"{decision.prompt}: needs an integer amount of life")
            if value < 0 or value > decision.amount:
                raise ValueError(
                    f"{decision.prompt}: cannot pay {value} life, life total is only "
                    f"{decision.amount} (CR 119.4)"
                )
            return value

        if decision.kind is DecisionKind.CHOOSE_AN_AMOUNT:
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValueError(f"{decision.prompt}: needs an integer amount")
            if value < 0 or value > decision.amount:
                raise ValueError(
                    f"{decision.prompt}: cannot choose {value}, at most {decision.amount} "
                    f"is legal (CR 608.2d)"
                )
            return value

        if decision.kind is DecisionKind.CHOOSE_CARDS:
            if not isinstance(value, tuple) or not all(isinstance(v, UUID) for v in value):
                raise ValueError(f"{decision.prompt}: needs a tuple of chosen card ids")
            offered = set(decision.cards)
            stray = [str(card_id) for card_id in value if card_id not in offered]
            if stray:
                raise ValueError(
                    f"{decision.prompt}: cannot choose a card that was not offered: "
                    f"{', '.join(stray)}"
                )
            if len(set(value)) != len(value):
                # One card is one object (CR 109.1) and can be chosen once.
                # Naming it twice would, for a search, take it out of the zone
                # twice; for a discard it would claim to discard two cards
                # while moving one.
                raise ValueError(f"{decision.prompt}: the same card cannot be chosen twice")
            if decision.exact:
                if len(value) != decision.amount:
                    raise ValueError(
                        f"{decision.prompt}: needs {decision.amount} card(s) chosen, "
                        f"{len(value)} given"
                    )
            elif len(value) > decision.amount:
                # CR 107.1c: "any number" runs zero up to every card offered,
                # never a fixed count - Valakut Awakening's own "any number of
                # cards from your hand" is the shape `exact=False` reads.
                raise ValueError(
                    f"{decision.prompt}: at most {decision.amount} card(s) may be chosen "
                    f"(CR 107.1c), {len(value)} given"
                )
            return value

        if decision.kind is DecisionKind.DREDGE:
            if not isinstance(value, tuple) or not all(isinstance(v, UUID) for v in value):
                raise ValueError(f"{decision.prompt}: needs a tuple of at most one dredge card")
            if len(value) > 1:
                raise ValueError(
                    f"{decision.prompt}: only one dredge card can replace a single draw "
                    f"(CR 702.52a)"
                )
            if value:
                (chosen_id,) = value
                chosen = self.find_by_id(chosen_id)
                if not isinstance(chosen, CardState):
                    raise ValueError(f"{decision.prompt}: {chosen_id} is not a card")
                reason = why_cannot_dredge(self, chosen, decision.player)
                if reason is not None:
                    raise ValueError(reason)
            return value

        if decision.kind is DecisionKind.CHOOSE_PLAYERS:
            if not isinstance(value, tuple) or not all(isinstance(v, str) for v in value):
                raise ValueError(f"{decision.prompt}: needs a tuple of chosen usernames")
            offered_players = set(decision.players)
            stray_players = [username for username in value if username not in offered_players]
            if stray_players:
                raise ValueError(
                    f"{decision.prompt}: cannot choose a player that was not offered: "
                    f"{', '.join(stray_players)}"
                )
            if len(set(value)) != len(value):
                raise ValueError(f"{decision.prompt}: the same player cannot be chosen twice")
            if decision.exact:
                if len(value) != decision.amount:
                    raise ValueError(
                        f"{decision.prompt}: needs {decision.amount} player(s) chosen, "
                        f"{len(value)} given"
                    )
            elif len(value) > decision.amount:
                raise ValueError(
                    f"{decision.prompt}: at most {decision.amount} player(s) may be chosen "
                    f"(CR 107.1c), {len(value)} given"
                )
            return value

        if decision.kind is DecisionKind.CHOOSE_TARGETS:
            if not isinstance(value, (tuple, list)):
                raise ValueError(f"{decision.prompt}: needs a tuple of targets")
            chosen = [TargetRef.coerce(target) for target in value]
            # `decision.targets` is the candidate pool this decision was built
            # with (`_ask_targets`, `_legal_target_candidates`), each entry
            # already carrying the `zone_change_stamp` its `CardState` had at
            # that moment (CR 601.2c/603.3d's announcement). A caller such as
            # `magic_cards_model_api.decisions.targets_answer` names a target
            # by a bare id with no stamp of its own - `TargetRef.__eq__`
            # ignores the stamp, so it still matches here, but swapping it for
            # its canonical pool entry is what actually carries the stamp
            # onto `self.targets`/`ability.targets` afterwards. Without this,
            # a target chosen through that path could never be judged illegal
            # by CR 608.2b's zone-change clause - the fix would be a no-op
            # over exactly the surface the bug was reported from.
            by_identity = {ref: ref for ref in decision.targets}
            stray = [str(ref) for ref in chosen if ref not in by_identity]
            if stray:
                raise ValueError(f"{decision.prompt}: not a legal target: {', '.join(stray)}")
            chosen = [by_identity[ref] for ref in chosen]
            if decision.target_maximum is not None and len(chosen) > decision.target_maximum:
                raise ValueError(
                    f"{decision.prompt}: too many targets chosen, at most "
                    f"{decision.target_maximum} (CR 115.6)"
                )
            if len(chosen) < decision.target_minimum:
                # CR 601.2c: "the player announces their choice of an
                # appropriate object or player for each target the spell
                # requires" - a plain "target permanent" is mandatory, not a
                # "you may", so declining while a legal target exists is
                # refused the same way an illegal target already is. CR 603.3d
                # extends this verbatim to a triggered ability's own
                # announcement.
                raise ValueError(
                    f"{decision.prompt}: at least {decision.target_minimum} target(s) "
                    f"must be chosen, {len(chosen)} given, while a legal target exists "
                    f"(CR 601.2c, CR 603.3d)"
                )
            return chosen

        if decision.kind is DecisionKind.ASSIGN_COMBAT_DAMAGE:
            return damage_assignment_answer(decision, value)

        if decision.kind is DecisionKind.CHOOSE_A_QUALITY:
            if not isinstance(value, str) or not value:
                raise ValueError(f"{decision.prompt}: needs a chosen value (CR 614.12a)")
            if decision.options and value not in decision.options:
                if decision.quality == ChoiceKind.CREATURE_TYPE:
                    # CR 205.3m is the whole list; naming it back would be
                    # three hundred words, so the refusal names the rule.
                    raise ValueError(
                        f"{decision.prompt}: {value!r} is not a creature type (CR 205.3m)"
                    )
                raise ValueError(
                    f"{decision.prompt}: {value!r} is not among the legal choices "
                    f"({', '.join(decision.options)})"
                )
            if decision.quality == ChoiceKind.CARD_NAME and not (
                is_card_name(value) or resolve_printing(value) is not None
            ):
                # CR 201.4: "the player must choose the name of a card in the
                # Oracle card reference" - not merely a non-empty string.
                # `decision.options` is deliberately never enumerated for a
                # card name (too large a universe, `machines/legal_actions.
                # py`'s own CHOOSE_A_QUALITY branch), so this is the one
                # place a card-name choice is checked: against Scryfall's own
                # card-name catalog (`data/card_names.py`), and the bundled
                # printings pool for a card newer than the bundled catalog.
                raise ValueError(
                    f"{decision.prompt}: {value!r} is not a card name this engine "
                    f"recognises (CR 201.4)"
                )
            return value

        if decision.kind is DecisionKind.CHOOSE_A_MODE:
            if not isinstance(value, str) or not value:
                raise ValueError(f"{decision.prompt}: needs a chosen mode (CR 700.2a)")
            if decision.options and value not in decision.options:
                raise ValueError(
                    f"{decision.prompt}: {value!r} is not among the printed modes "
                    f"({', '.join(decision.options)})"
                )
            return value

        if decision.kind is DecisionKind.PUT_ON_TOP_OR_BOTTOM:
            if not isinstance(value, bool):
                raise ValueError(f"{decision.prompt}: needs a top-or-bottom bool answer")
            return value

        if decision.kind is DecisionKind.PUT_INTO_HAND_OR_GRAVEYARD:
            if not isinstance(value, bool):
                raise ValueError(f"{decision.prompt}: needs a hand-or-graveyard bool answer")
            return value

        if decision.kind is DecisionKind.CHOOSE_PILE:
            if not isinstance(value, bool):
                raise ValueError(f"{decision.prompt}: needs a which-pile bool answer")
            return value

        if decision.kind is DecisionKind.OPENING_HAND_ACTION:
            # CR 103.6's "may take any such actions": a yes-or-no, both branches
            # always legal - a restriction the card prints (Gemstone Caverns'
            # "you're not the starting player") stops the question being asked
            # at all rather than making one answer illegal.
            if not isinstance(value, bool):
                raise ValueError(f"{decision.prompt}: a yes-or-no question needs a bool answer")
            return value

        if not isinstance(value, CardSplit):
            raise ValueError(f"{decision.prompt}: needs a CardSplit answer")
        looked_at = set(decision.cards)
        stray = [str(card_id) for card_id in value.moved if card_id not in looked_at]
        if stray:
            raise ValueError(
                f"{decision.prompt}: cannot move a card that was not looked at "
                f"(CR 701.22a, CR 701.25a): {', '.join(stray)}"
            )
        # `amount`/`exact` are the printed count of cards the player may pick:
        # scry's "any number" (CR 107.1c), Devourer of Destiny's "one of those
        # cards", Waker of Waves' "put one of them". Picking outside it is an
        # option CR 608.2d does not allow.
        chosen = len(set(value.moved))
        if decision.exact and chosen != decision.amount:
            raise ValueError(
                f"{decision.prompt}: exactly {decision.amount} card(s) must be chosen, "
                f"{chosen} given (CR 608.2d)"
            )
        if chosen > decision.amount:
            raise ValueError(
                f"{decision.prompt}: at most {decision.amount} card(s) may be chosen, "
                f"{chosen} given (CR 608.2d)"
            )
        return value

    def ask_cleanup_discard(self: "Game", player: Player, needed: int) -> list[CardState]:
        """Which cards a player discards to their maximum hand size (CR 514.1).

        CR 701.9b: "By default, effects that cause a player to discard a card
        allow the affected player to choose which card to discard" - the
        cleanup discard is such an effect, so this is a `CHOOSE_CARDS`
        question through `Game.ask`, the same CR 608.2d machinery every other
        discard-a-card choice in `machines/effects.py` uses.

        The hand is offered in hand order, so `default_answer`'s "back of the
        offered cards" lands on the actual back of the hand - the behaviour
        `Player.discard_to_maximum_hand_size` had before this question existed.
        """
        with self._id_allocator_scope():
            decision = Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=player.username,
                prompt=f"discard {needed} card(s) to maximum hand size",
                source_id=None,  # CR 514.1: a turn-based action, not an object's.
                amount=needed,
                cards=tuple(state.id for state in player.hand),
            )
            chosen_ids = self.ask(decision)
            assert isinstance(chosen_ids, tuple)
            by_id = {state.id: state for state in player.hand}
            return [by_id[card_id] for card_id in chosen_ids]

    def may(
        self: "Game",
        player: Player | str,
        prompt: str,
        *,
        source: str | None = None,
        source_id: str | None = None,
        cards: Sequence[CardState] = (),
        default: bool | None = None,
    ) -> bool:
        """A plain "you may" during resolution (CR 608.2d).

        Both branches are always legal, so this is the one question where the
        default - take it - is a genuine deviation rather than the only answer.
        `default` lets a caller write its own documented deviation from that
        instead (`Decision.default_may`); leaving it `None` keeps "take it".

        `cards` are the cards the "you may" is about - the revealed cards a
        player may take one of - published on `Decision.cards` so the player
        is not asked blind.
        """
        username = player if isinstance(player, str) else player.username
        answer = self.ask(
            Decision(
                kind=DecisionKind.MAY,
                player=username,
                prompt=prompt,
                source=source,
                source_id=source_id,
                cards=tuple(state.id for state in cards),
                default_may=default,
            )
        )
        return bool(answer)

    def may_pay_unless_cost(
        self: "Game",
        player: Player | str,
        cost: TotalCost,
        *,
        source: str | None = None,
        source_id: str | None = None,
        spend: ManaSpend | None = None,
        prompt: str | None = None,
    ) -> bool:
        """ "... unless that player pays [cost]", asked and then paid, for any
        printed cost (CR 118.12a, CR 608.2d) - ward's (CR 702.21a).

        CR 118.12a: "[Do something] unless [a player does something else]"
        means "[A player may do something else]. If [that player doesn't], [do
        something]." Paying is offered only when CR 118.3 allows it: "A player
        can't pay a cost without having the necessary resources to pay it
        fully."

        A mana-only cost is `may_pay_mana_cost`'s `PAY_MANA` question and a
        life-only cost `may_pay_life`'s `PAY_LIFE`, so those keep their own
        kinds and defaults. Anything else - a discard, a sacrifice, or a mix
        with mana or life - is one `MAY` for the whole cost, then a
        `CHOOSE_CARDS` for each part that needs objects: the discarding player
        chooses the discard (CR 701.9b), and a player sacrifices only a
        permanent they control (CR 701.21a). Mana is paid from the pool
        (CR 608.2g's mana abilities are not activated mid-resolution here; see
        `may_pay_mana`). A part of a kind this cannot pay makes the whole cost
        unpayable rather than half-paid.

        `spend` is what the mana is paid for (CR 106.6), so restricted mana
        whose restriction allows it can pay - cumulative upkeep's
        (`ManaSpend.paying_cumulative_upkeep`). `prompt` overrides the
        question's wording.

        Returns whether the cost was paid, and pays it.
        """
        username = player if isinstance(player, str) else player.username
        payer = self.player(username)
        components = [
            component.model_copy(update={"payer": username}) for component in cost.components
        ]
        if not components:
            return self.may_pay_mana_cost(
                payer, cost.mana, source=source, source_id=source_id, spend=spend, prompt=prompt
            )
        if not cost.mana.symbols and all(c.kind is ComponentKind.PAY_LIFE for c in components):
            total = sum(component.amount for component in components)
            return self.may_pay_life(payer, total, source=source, source_id=source_id)

        candidates: list[list[CardState]] = []
        payable = not cost.mana.symbols or payer.mana_pool.can_pay(cost.mana, spend=spend)
        for component in components:
            if component.kind is ComponentKind.DISCARD:
                pool = list(payer.hand)
            elif component.kind is ComponentKind.SACRIFICE:
                pool = list(self.permanents_controlled_by(username))
            elif component.kind is ComponentKind.GAIN_CONTROL:
                # CR 118.3: a permanent another player controls.
                pool = [
                    card
                    for card in self.battlefield
                    if self.controller_of(card).username != username
                ]
            elif component.kind is ComponentKind.PAY_LIFE:
                pool = []
                payable = payable and payer.life >= component.amount  # CR 119.4
            else:
                pool = []
                payable = False
            if component.requirement is not None:
                pool = [
                    card
                    for card in pool
                    if component.requirement.why_not(card, self, username) is None
                ]
            candidates.append(pool)
            if component.kind in _CHOSEN_OBJECT_KINDS:
                payable = payable and len(pool) >= component.required
        answer = self.ask(
            Decision(
                kind=DecisionKind.MAY,
                player=username,
                prompt=prompt or f"pay {cost}",
                source=source,
                source_id=source_id,
                affirmative_is_legal=payable,
            )
        )
        if not answer:
            return False
        for component, pool in zip(components, candidates, strict=True):
            if component.kind not in _CHOSEN_OBJECT_KINDS:
                continue
            verb = _CHOSEN_OBJECT_KINDS[component.kind]
            chosen_ids = self.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=username,
                    prompt=f"choose {component.required} card(s) to {verb}",
                    source=source,
                    source_id=source_id,
                    amount=component.required,
                    cards=tuple(card.id for card in pool),
                    default_cards=tuple(card.id for card in pool[: component.required]),
                )
            )
            assert isinstance(chosen_ids, tuple)
            by_id = {card.id: card for card in pool}
            component.cards = [by_id[card_id] for card_id in chosen_ids]
        if cost.mana.symbols:
            payer.mana_pool.pay(cost.mana, spend=spend)
        for component in components:
            component.pay(self)
        return True

    def may_pay_life(
        self: "Game",
        player: Player | str,
        amount: int,
        *,
        source: str | None = None,
        source_id: str | None = None,
    ) -> bool:
        """ "You may pay N life", asked and then paid (CR 119.4, CR 608.2d).

        CR 119.4: "If a cost or effect allows a player to pay an amount of life
        greater than 0, the player may do so only if their life total is greater
        than or equal to the amount of the payment. If a player pays life, the
        payment is subtracted from their life total; in other words, the player
        loses that much life."

        So the affirmative is *illegal* below that life total, not merely a bad
        idea, and CR 608.2d then forbids choosing it - which is how a shockland
        fetched at 1 life enters tapped without anybody deciding anything.
        CR 119.4b: "Players can always pay 0 life", whatever the total.

        Returns whether the life was paid, and pays it.
        """
        if isinstance(player, str):
            player = self.player(player)
        payable = amount <= 0 or player.life >= amount
        answer = self.ask(
            Decision(
                kind=DecisionKind.PAY_LIFE,
                player=player.username,
                prompt=f"pay {amount} life",
                source=source,
                source_id=source_id,
                amount=amount,
                affirmative_is_legal=payable,
            )
        )
        if not answer:
            return False
        if amount > 0:
            self.lose_life(player, amount, payment=True)  # CR 119.4
        return True

    def may_pay_energy(
        self: "Game",
        player: Player | str,
        amount: int,
        *,
        source: str | None = None,
        source_id: str | None = None,
    ) -> bool:
        """ "You may pay {E}{E}..." / "...unless you pay {E}", asked and then
        paid (CR 107.14, CR 118.3, CR 608.2d).

        CR 107.14: "To pay {E}, a player removes one energy counter from
        themselves." CR 118.3: "A player can't pay a cost without having the
        necessary resources to pay it fully" - so the affirmative is illegal
        below `amount` energy, exactly the shape `may_pay_life` already uses
        for CR 119.4's life-total floor, and the same reason: a scripted "yes"
        below the floor is a rules violation, not merely a bad idea, so it is
        removed from `legal_options` rather than trusted to self-police.

        Static Prison's "sacrifice this enchantment unless you pay {E}" reads
        this the same call the other way round: paying is what avoids the
        sacrifice rather than what causes a bonus, but the payment itself -
        can it be paid, and does paying spend exactly `amount` energy and
        nothing else - is identical either way.

        Returns whether the energy was paid, and pays it. A "no" answer -
        whether scripted, taped, or the fixed-cost default (`default_answer`
        takes the affirmative when it is legal, same as `PAY_LIFE`) - leaves
        the player's energy untouched.
        """
        if isinstance(player, str):
            player = self.player(player)
        payable = amount <= 0 or player.energy >= amount
        answer = self.ask(
            Decision(
                kind=DecisionKind.PAY_ENERGY,
                player=player.username,
                prompt=f"pay {amount} energy",
                source=source,
                source_id=source_id,
                amount=amount,
                affirmative_is_legal=payable,
            )
        )
        if not answer:
            return False
        if amount > 0:
            player.remove_counters(Counter.ENERGY, amount)
            # CR 107.14: paying {E} removes energy counters - "you've paid or
            # lost N or more {E} this turn" counts them.
            self.note_turn_count(ENERGY_PAID_OR_LOST, player.username, amount)
        return True

    def may_pay_mana(
        self: "Game",
        player: Player | str,
        amount: int,
        *,
        source: str | None = None,
        source_id: str | None = None,
    ) -> bool:
        """ "Unless its controller pays {N}", asked and then paid (CR 118.12a,
        CR 608.2d) - Censor's, Mana Leak's and Metallic Rebuke's shape.

        CR 118.12a: "[Do something] unless [a player does something else]"
        means "[a player] may [do something else]. If [that player] doesn't,
        [effect]." - the same reading `may_pay_energy` already gives Static
        Prison's own "unless", just with the branches swapped: paying here is
        what *avoids* the counter, not what triggers a bonus.

        CR 608.2g: "If an effect gives a player the option to pay mana, they
        may activate mana abilities before taking that action", and CR 605.3a
        allows it "even if it's in the middle of ... resolving a spell". So
        the payment counts the floating pool **and** the untapped mana sources
        the player could activate now (`Decision.mana_sources`); see
        `_pay_mana_while_resolving` for how the answer is paid.

        Returns whether the mana was paid, and spends it.
        """
        if isinstance(player, str):
            player = self.player(player)
        cost = ManaCost.parse(f"{{{amount}}}") if amount > 0 else ManaCost()
        return self._may_pay_mana_while_resolving(
            player,
            cost,
            prompt=f"pay {{{amount}}} or the spell is countered",
            amount=amount,
            source=source,
            source_id=source_id,
        )

    def may_pay_mana_cost(
        self: "Game",
        player: Player | str,
        cost: ManaCost,
        *,
        source: str | None = None,
        source_id: str | None = None,
        spend: ManaSpend | None = None,
        prompt: str | None = None,
    ) -> bool:
        """ "Pay {cost}. If you don't, ..." with a real (possibly colored) mana
        cost rather than `may_pay_mana`'s bare generic amount - the Pact
        cycle's own delayed-trigger shape (CR 603.7, CR 118.12a's "unless"
        read the other way round): "At the beginning of your next upkeep, pay
        {2}{G}{G}. If you don't, you lose the game."

        The same CR 608.2g payment as `may_pay_mana`: floating mana and the
        mana abilities of untapped sources both count.

        Returns whether the cost was paid, and pays it.
        """
        if isinstance(player, str):
            player = self.player(player)
        return self._may_pay_mana_while_resolving(
            player,
            cost,
            prompt=prompt or f"pay {cost}",
            amount=cost.converted,
            source=source,
            source_id=source_id,
            spend=spend,
        )

    def may_pay_mana_and_life(
        self: "Game",
        player: Player | str,
        cost: ManaCost,
        life: int,
        *,
        source: str | None = None,
        source_id: str | None = None,
        spend: ManaSpend | None = None,
        prompt: str | None = None,
    ) -> bool:
        """ "You may pay `<mana>` and `<N>` life." (CR 603.12/118.12, CR
        119.4) - Zoraline, Cosmos Caller's own "you may pay {W}{B} and 2
        life", the combined-cost twin of `may_pay_mana_cost`: one CR 608.2d
        question for the whole thing, mana tapped from untapped sources the
        same way that one taps them (CR 605.3a), paid together with the life
        or not at all. `may_pay_unless_cost` is the wrong tool for this -
        it reads mana `payable` off the floating pool alone, which is right
        for a cost paid as part of announcing a spell or ability but wrong
        here: a reflexive mid-resolution "you may pay" has no floating mana
        yet and has to be offered the untapped sources it can still tap,
        exactly as `may_pay_mana_cost` already is.

        Returns whether the whole cost was paid, and pays it.
        """
        if isinstance(player, str):
            player = self.player(player)
        sources = self._mana_sources_while_resolving(player)
        mana_payable = (
            plan_mana_payment(cost, sources, game=self, payer=player.username, spend=spend)
            is not None
        )
        payable = mana_payable and (life <= 0 or player.life >= life)
        full_prompt = prompt or f"pay {cost} and {life} life"
        answer = self.ask(
            Decision(
                kind=DecisionKind.MAY,
                player=player.username,
                prompt=full_prompt,
                source=source,
                source_id=source_id,
                affirmative_is_legal=payable,
            )
        )
        if not answer:
            return False
        self._pay_mana_while_resolving(player, cost, sources, prompt=full_prompt, spend=spend)
        if life > 0:
            self.lose_life(player, life, payment=True)  # CR 119.4
        return True

    def _may_pay_mana_while_resolving(
        self: "Game",
        player: Player,
        cost: ManaCost,
        *,
        prompt: str,
        amount: int,
        source: str | None,
        source_id: str | None,
        spend: ManaSpend | None = None,
    ) -> bool:
        """Ask `player` whether to pay `cost` mid-resolution, and pay it.

        The question offers every untapped mana source the player could
        activate (CR 605.3a) and is legal to accept exactly when the floating
        pool plus those sources can pay the cost fully (CR 118.3).
        """
        free = cost.converted <= 0 and not cost.symbols
        sources = [] if free else self._mana_sources_while_resolving(player)
        payable = free or (
            plan_mana_payment(cost, sources, game=self, payer=player.username, spend=spend)
            is not None
        )
        answer = self.ask(
            Decision(
                kind=DecisionKind.PAY_MANA,
                player=player.username,
                prompt=prompt,
                source=source,
                source_id=source_id,
                amount=amount,
                affirmative_is_legal=payable,
                mana_sources=tuple(state.id for state in sources),
            )
        )
        if answer is False:
            return False
        if not free:
            chosen = sources if answer is True else [s for s in sources if s.id in set(answer)]
            self._pay_mana_while_resolving(
                player,
                cost,
                chosen,
                prompt=prompt,
                spend=spend,
                named=_named_mana_abilities(answer),
            )
        return True

    def choose_an_amount(
        self: "Game",
        player: Player | str,
        ceiling: int,
        *,
        source: str | None = None,
        source_id: str | None = None,
        prompt: str = "choose an amount",
    ) -> int:
        """ "Put up to N `<kind>` counters on `<this>`" (Clockwork Steed) and
        any other resolution-time "choose an amount from 0 up to `ceiling`"
        with no cost or payment attached (CR 608.2d) - `pay_any_amount_of_
        life`/`pay_any_amount_of_energy`'s own shape, generalised past
        paying something: a real choice from 0 up to `ceiling`, never
        defaulted upward for an unscripted answer, since nothing here makes
        choosing fewer worse than choosing the maximum (unlike `_parse_
        remove_up_to_n_counters_from_target_clause`'s own "remove up to N",
        where fewer is never better and the effect always takes the
        maximum without asking).

        Returns whatever amount was actually chosen; unlike `pay_any_amount_
        of_life`, nothing here spends it - callers apply the chosen amount
        themselves, since "up to N counters" has no single universal
        payment this method could make on a caller's behalf the way losing
        life or removing energy counters is.
        """
        if isinstance(player, str):
            player = self.player(player)
        decision = Decision(
            kind=DecisionKind.CHOOSE_AN_AMOUNT,
            player=player.username,
            prompt=prompt,
            source=source,
            source_id=source_id,
            amount=max(ceiling, 0),
        )
        chosen = self.ask(decision)
        assert isinstance(chosen, int)
        return chosen

    def _choose_moved_candidates(
        self: "Game",
        chooser: Player,
        eligible: list[CardState],
        *,
        moved_amount: int | None,
        moved_exact: bool,
        prompt: str,
        source: str | None,
        source_id: str | None,
    ) -> CardSplit:
        """`look_at_top_and_split`'s question when only some looked-at cards
        may move: a `CHOOSE_CARDS` over `eligible` alone (CR 608.2d - "the
        player can't choose an option that's illegal"), asked only when there
        is a choice left to make."""
        most = len(eligible) if moved_amount is None else min(moved_amount, len(eligible))
        if most <= 0:
            return CardSplit()
        if moved_exact and most == len(eligible):
            return CardSplit(moved=tuple(state.id for state in eligible))
        chosen = self.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=chooser.username,
                prompt=prompt,
                source=source,
                source_id=source_id,
                amount=most,
                exact=moved_exact,
                cards=tuple(state.id for state in eligible),
            )
        )
        assert isinstance(chosen, tuple)
        return CardSplit(moved=tuple(chosen))

    def ask_library_bottom_order(
        self: "Game",
        player: Player | str,
        cards: Sequence[CardState],
        *,
        source: str | None = None,
        source_id: str | None = None,
    ) -> list[CardState]:
        """The order `cards` go to the bottom of a library, topmost first
        (CR 401.4).

        "If an effect puts two or more cards in a specific position in a
        library at the same time, the owner of those cards may arrange them in
        any order. That library's owner doesn't reveal the order in which the
        cards go into the library." So the order is the owner's choice, asked
        here as the engine's ordered `CHOOSE_CARDS` answer - every card offered,
        all of them required, the first named nearest the top - the same shape
        Brainstorm's "in any order" already answers.

        Nothing is asked when the order cannot matter: fewer than two cards, or
        cards that are all the same card, which make the same library in every
        order. An unscripted player keeps the order `cards` came in
        (`Decision.default_cards`), so a rigged library stays rigged.

        This only asks. Placing the cards, and moving the library epoch for
        what the owner knows (CR 701.20d), stays with the caller, whose
        placement already does both. Labels travel with the question because a
        caller may hold the cards off every zone while it asks.
        """
        if isinstance(player, str):
            player = self.player(player)
        ordered = list(cards)
        if len(ordered) < 2 or len({state.name for state in ordered}) == 1:
            return ordered
        ids = tuple(state.id for state in ordered)
        answer = self.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=player.username,
                prompt=(
                    f"order the {len(ordered)} cards going to the bottom of your library, "
                    "topmost first"
                ),
                source=source,
                source_id=source_id,
                amount=len(ordered),
                cards=ids,
                card_labels=tuple(state.name for state in ordered),
                default_cards=ids,
            )
        )
        assert isinstance(answer, tuple)
        by_id = {state.id: state for state in ordered}
        return [by_id[card_id] for card_id in answer]

    def choose_cards_to_reveal(
        self: "Game",
        component: CostComponent,
        payer: str,
        *,
        source: str,
        source_id: str | None,
        x_value: int = 0,
    ) -> None:
        """Ask `payer` which cards pay a reveal cost nobody named (CR 601.2h).

        Offered: the cards in `payer`'s own hand that meet the cost's quality
        (CR 118.3). For CR 107.3a's X with no X announced, any number of them
        is an answer and the number chosen becomes X; for a fixed count, or an
        X already announced, exactly that many. A hand that cannot cover the
        count is not asked - the component then refuses to be paid. The
        answer is written onto `component`, which is otherwise left alone.
        """
        if component.kind is not ComponentKind.REVEAL or component.cards:
            return
        eligible = [
            card
            for card in self.player(payer).hand
            if component.requirement is None
            or component.requirement.why_not(card, self, payer) is None
        ]
        description = component.description or "this cost"
        if component.variable_count and not x_value:
            if not eligible:
                component.required = 0
                return
            decision = Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=payer,
                prompt=f"choose any number of cards to reveal for {description!r}",
                source=source,
                source_id=source_id,
                amount=len(eligible),
                cards=tuple(card.id for card in eligible),
                exact=False,
            )
        else:
            needed = x_value if component.variable_count else component.required
            component.required = needed
            if needed <= 0 or len(eligible) < needed:
                return
            decision = Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=payer,
                prompt=f"choose {needed} card(s) to reveal for {description!r}",
                source=source,
                source_id=source_id,
                amount=needed,
                cards=tuple(card.id for card in eligible),
            )
        chosen = self.ask(decision)
        assert isinstance(chosen, tuple)
        by_id = {card.id: card for card in eligible}
        component.cards = [by_id[card_id] for card_id in chosen]
        if component.variable_count:
            component.required = len(component.cards)

    def _emit_player_counters_put(self: "Game", player: Player, kind: str, amount: int) -> None:
        """CR 122.6's "counters being put on ... an object that's given
        counters" event, for a player rather than a permanent - the player
        twin of `_emit_counters_put` just below.

        Fabrication Module's own "Whenever you get one or more {E} ..."
        (CR 107.14) is the shape this exists for: getting energy is CR
        122.6's own event from the player's side, the same way a permanent
        being given counters is from the object's side, so it needs the same
        once-per-instruction, whole-amount event `_emit_counters_put` already
        raises for a permanent.

        One event per instruction, carrying the whole amount - CR 603.2c's
        "one event, multiple occurrences" reading `_emit_counters_put`'s own
        docstring explains, unchanged here.

        Called only after `add_player_counters` has already applied
        replacements and confirmed `amount > 0` (CR 603.2g: "an ability
        triggers only if its trigger event actually occurs" - a replacement
        or a bare non-positive call leaves nothing to get, so nothing here
        fires).
        """
        if amount <= 0:
            return
        self.emit(
            GameEvent(
                event=ExtraTriggerEvent.PLAYER_COUNTERS_PUT,
                counter_kind=kind,
                amount=amount,
                player=player.username,
            )
        )

    def _emit_counters_put(
        self: "Game", permanent: CardState, kind: str, amount: int, *, putter: str | None = None
    ) -> None:
        """CR 122.6's generic "counters are put on this object" event.

        "Some spells and abilities refer to counters being put on an object.
        This refers to putting counters on that object while it's on the
        battlefield and also to an object that's given counters as it enters
        the battlefield" - Basking Broodscale's and Emperor of Bones'
        "Whenever one or more +1/+1 counters are put on this creature".

        One event per instruction, carrying the whole amount. CR 603.2c: "An
        ability triggers only once each time its trigger event occurs. However,
        it can trigger repeatedly if one event contains multiple occurrences" -
        and "one or more counters" is not several occurrences, it is one
        occurrence with a count, so two counters arriving together fire the
        ability once. The count travels on `GameEvent.amount` for any clause
        that later refers back to how many.

        The kind travels too (CR 122.1 leaves the set of counter kinds open, so
        it is a plain string), which is what stops a charge counter firing a
        condition that names +1/+1.

        Only a permanent is asked: the conditions in this pool are all
        self-referential ("this creature"), and CR 110.1 makes an object a
        permanent only while it is on the battlefield.
        """
        if amount <= 0 or permanent.zone is not Zone.BATTLEFIELD:
            return
        # CR 613.5: the object's characteristics for this event are the
        # computed ones, not the printed type line (CR 613.1's starting
        # point) - a land animated by earthbend is a creature only there.
        chars = self.characteristics_of(permanent)
        placement = len(self.counters_put_this_turn)
        self.counters_put_this_turn.append(
            CountersPutRecord(
                putter=putter or permanent.controller,
                card_id=permanent.id,
                kind=kind,
                amount=amount,
                controller=permanent.controller,
                types=chars.types,
                zone_change_stamp=permanent.zone_change_stamp,
            )
        )
        self.emit(
            GameEvent(
                event=ExtraTriggerEvent.COUNTERS_PUT,
                subject_id=permanent.id,
                subject_name=permanent.name,
                subject_controller=permanent.controller,
                subject_card=permanent.card,
                subject_types=chars.types,
                subject_subtypes=chars.subtypes,
                counter_kind=kind,
                amount=amount,
                # CR 122.6a: who put them - "whenever you put ..." asks this.
                player=putter or permanent.controller,
                counters_put_index=placement,
            )
        )

    def _emit_left_graveyard(
        self: "Game", owner: str, gone: list[CardState], *, exiled: bool = True
    ) -> None:
        """The events one batch of cards leaving a graveyard raises (CR 603.10a, 406.2).

        `ExtraTriggerEvent.LEAVES_GRAVEYARD` is CR 603.10a's own category -
        "abilities that trigger when a card leaves a graveyard" - and
        `ExtraTriggerEvent.EXILED_FROM_GRAVEYARD` is the narrower one that also
        names where the card went, which Ketramose, the New Dawn's "one or more
        cards are put into exile from graveyards and/or the battlefield" reads.
        Both are true of the same move, so both fire, the same way
        `LEAVES_BATTLEFIELD_TO_EXILE` and `LEAVES_THE_BATTLEFIELD` already do -
        but only when exile is where the cards actually went. `exiled=False` is
        a graveyard departure to somewhere else (a library, a hand), which is
        CR 603.10a's event and not CR 406.2's.

        `player` is the owner of the graveyard, which is what the matcher
        compares against the ability's controller for "your graveyard".

        The subject is filled in only when exactly one card left: a condition
        with a type restriction ("an instant or sorcery card leaves your
        graveyard", Murktide Regent) reads `subject_types`, and a batch of
        several cards has no single answer to give it. Left unset, that
        condition simply does not match - the same direction every other
        unanswerable question in this engine fails in, rather than picking one
        card of the batch and pretending it was the whole event.
        """
        if not gone:
            return
        only = gone[0] if len(gone) == 1 else None
        events = [ExtraTriggerEvent.LEAVES_GRAVEYARD]
        if exiled:
            events.append(ExtraTriggerEvent.EXILED_FROM_GRAVEYARD)
        for event in events:
            self.emit(
                GameEvent(
                    event=event,
                    subject_id=only.id if only is not None else None,
                    subject_name=only.name if only is not None else None,
                    subject_card=only.card if only is not None else None,
                    subject_types=only.types if only is not None else None,
                    subject_subtypes=only.subtypes if only is not None else None,
                    player=owner,
                    amount=len(gone),
                )
            )

    def _ask_which_legend_to_keep(
        self: "Game", username: str, name: str, copies: list[CardState]
    ) -> CardState:
        """CR 704.5j's "that player chooses one of them", asked once per group."""
        offered = list(reversed(copies))
        decision = Decision(
            kind=DecisionKind.CHOOSE_CARDS,
            player=username,
            prompt=f"choose which {name} to keep (CR 704.5j)",
            source_id=None,  # CR 704.5j: a state-based action, not an object's.
            amount=1,
            exact=True,
            cards=tuple(state.id for state in offered),
        )
        chosen_ids = self.ask(decision)
        assert isinstance(chosen_ids, tuple)
        by_id = {state.id: state for state in copies}
        for card_id in chosen_ids:
            kept = by_id.get(card_id)
            if kept is not None:
                return kept
        # An answer that named nothing on offer keeps the longest-standing
        # copy, the same as the unscripted default - the legend rule is a
        # state-based action and has to reach an answer.
        return copies[0]

    def _emit_attacks(self: "Game", creature: CardState, attack: "Attack") -> None:
        """Emit one attacker's own `ATTACKS` event (CR 508.3c/d), read against
        the *whole* attacking party as it stands right now.

        Split out of `declare_attacker` so `declare_attackers` can register
        every attacker of a batch first and only then call this once per
        attacker, which is what makes `attacking_alone`/`attacking_player_
        alone` (CR 506.5/506.6) correct for a multi-attacker declaration -
        both ask about the finished declaration, never a partial one.
        """
        # CR 613.5: the attacker's characteristics for this event are the
        # computed ones - a land animated by earthbend is a creature only
        # there - and it is still on the battlefield here (CR 508.1a).
        chars = self.characteristics_of(creature)
        # CR 506.5: "the only creature declared as an attacker" this combat.
        alone = len(self.combat.attacks) == 1
        # CR 506.6: "no other creature is declared as an attacker attacking
        # that player" - scoped to attacks sharing this one's defender, and
        # only meaningful when that defender is a player at all.
        player_alone = attack.defender.is_player and all(
            other.defender != attack.defender or other.attacker_id == creature.id
            for other in self.combat.attacks
        )
        # CR 508.5 / 310.9d: the defending player - a battle's protector,
        # not its controller.
        defender_controller = combat_rules.defending_player(self, attack.defender)
        self.emit(
            GameEvent(
                event=TriggerEvent.ATTACKS,
                subject_id=creature.id,
                subject_name=creature.name,
                subject_controller=self.controller_of(creature).username,
                subject_card=creature.card,
                subject_types=chars.types,
                subject_subtypes=chars.subtypes,
                defender=attack.defender,
                defender_controller=defender_controller,
                player=self.controller_of(creature).username,
                attacking_alone=alone,
                attacking_player_alone=player_alone,
            )
        )

    def _emit_blocks(self: "Game", blocker: CardState, attacker: CardState) -> None:
        """`blocker` blocked `attacker`: one `TriggerEvent.BLOCKS` for the pair."""
        # CR 613.5: the blocker's characteristics for this event are the
        # computed ones - Tetsuko Umezawa, Pursuer's own "a creature an
        # opponent controls with power or toughness 1 or less blocks" needs
        # both the up-face type/subtype and the live power/toughness, and the
        # blocker is still on the battlefield here (CR 509.1a).
        blocker_chars = self.characteristics_of(blocker)
        self.emit(
            GameEvent(
                event=TriggerEvent.BLOCKS,
                subject_id=blocker.id,
                subject_name=blocker.name,
                subject_controller=self.controller_of(blocker).username,
                subject_card=blocker.card,
                subject_types=blocker_chars.types,
                subject_subtypes=blocker_chars.subtypes,
                related_id=attacker.id,
                player=self.controller_of(blocker).username,
            )
        )

    def _choose_permanent_for_counters(
        self: "Game", component: CostComponent, payer: str, source: CardState
    ) -> None:
        """Ask `payer` which permanent a "Blight N" cost puts its counters on
        (CR 701.68a), or which one a "Remove a +1/+1 counter from a creature
        you control" cost takes them off (paid at CR 601.2h via CR 602.2b).
        Offered: the permanents `payer` controls that meet the cost's
        requirement - and, for a removal, carry enough of the counters
        (CR 118.3). None to offer leaves the component empty, and it refuses
        to be paid (CR 701.68b, CR 118.3)."""
        removes = component.kind is ComponentKind.REMOVE_COUNTERS
        eligible = [
            state
            for state in self.permanents_controlled_by(payer)
            if (
                component.requirement is None
                or component.requirement.why_not(state, self, payer) is None
            )
            and (not removes or state.can_remove_counters(component.counter_kind, component.amount))
        ]
        if not eligible:
            return
        answer = self.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=payer,
                prompt=f"choose a permanent you control for {component.description!r}",
                source=source.name,
                source_id=source_id_of(source),
                amount=1,
                cards=tuple(state.id for state in eligible),
            )
        )
        by_id = {state.id: state for state in eligible}
        component.cards = [by_id[card_id] for card_id in answer]

    def _choose_permanents_to_return(
        self: "Game", component: CostComponent, payer: str, source: CardState
    ) -> None:
        """Ask `payer` which permanents a printed "Return a land you control
        to its owner's hand" cost returns (CR 601.2h via CR 602.2b). Offered:
        the permanents `payer` controls that meet the requirement - "another"
        leaves the source out. Too few to offer leaves the component short,
        and it refuses to be paid (CR 118.3)."""
        eligible = [
            state
            for state in self.permanents_controlled_by(payer)
            if component.requirement is None
            or component.requirement.why_not(state, self, payer) is None
        ]
        if len(eligible) < component.required:
            return
        answer = self.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=payer,
                prompt=f"choose what to return for {component.description!r}",
                source=source.name,
                source_id=source_id_of(source),
                amount=component.required,
                cards=tuple(state.id for state in eligible),
                default_cards=tuple(state.id for state in eligible[: component.required]),
            )
        )
        by_id = {state.id: state for state in eligible}
        component.cards = [by_id[card_id] for card_id in answer if card_id in by_id]

    def _choice_cost(
        self: "Game",
        text: str,
        permanent: CardState,
        pool: list[CardState],
        controller: str,
        builder: Callable[..., CostComponent],
        x_value: int = 0,
        targets: list[object] | None = None,
    ) -> CostComponent:
        """One `[Sacrifice|Discard]` cost piece, self-reference and quality
        requirement both handled (CR 602.1a, CR 118.3).

        `cost_component_for_phrase` already reads the qualified shape -
        "Sacrifice a Goblin", "Discard two cards" - into a component carrying
        a `CardRequirement`, but always with `cards=[]`: it has no `pool` to
        choose from and no permanent to self-reference. This fills the gap
        either way: from `pool` (the caller's nomination) up to however many
        the cost asks for, or with `permanent` itself when nothing was
        nominated and the text names "this" card - the same self-reference
        `CostKind.OTHER`'s own fill-in below handles.

        Falls back to `builder` directly - no requirement, "sacrifice
        anything" - only when the phrase does not match the qualified shape
        at all (CR 602.1a - "Sacrifice this land"'s `count` position holds the
        word "this", not a number, so `cost_component_for_phrase` cannot read
        it as one).
        """
        # Kozilek's "Discard a card with mana value X": the X is the target
        # spell's mana value (CR 107.3), so once a target is chosen the
        # discarded card is held to it; before one is, the phrase asks for "a
        # card" and the requirement is added below.
        reading = re.sub(r" with mana value X$", "", text, flags=re.IGNORECASE)
        linked_mana_value = None
        if reading != text:
            for target in targets or []:
                state = target if isinstance(target, CardState) else self.find_by_id(target)
                if isinstance(state, CardState):
                    linked_mana_value = int(state.mana_value)
                    break
        component = cost_component_for_phrase(reading, payer=controller)
        if component is None:
            if not _cost_refers_to_self(text, permanent):
                # CR 602.5: a quality word nobody taught the reader must not
                # make the cost "sacrifice/discard anything" - refuse instead.
                raise ValueError(f"cannot build a cost for {text!r}")
            chosen = [pool.pop(0)] if pool else [permanent]
            return builder(*chosen, payer=controller, required=1, description=text)

        # "Sacrifice X Goats" / "Sacrifice one or more artifacts": the count is
        # the announced X or every nominated object (CR 107.3a).
        component = announce_count(component, x_value, len(pool))
        if linked_mana_value is not None and component.requirement is not None:
            component.requirement = component.requirement.model_copy(
                update={"mana_value": linked_mana_value}
            )
        if component.requirement is not None and component.requirement.excludes_source:
            # "Sacrifice another ..." (CR 601.2c/113.6): only here is the
            # source known, the same fill-in `CostKind.OTHER` does below.
            component.requirement.source_id = permanent.id
        chosen = []
        while pool and len(chosen) < component.required:
            chosen.append(pool.pop(0))
        if not chosen and _cost_refers_to_self(text, permanent):
            chosen = [permanent]
        return component.model_copy(update={"cards": chosen})

    def why_cannot_decide_for(self: "Game", decider: str, player: str) -> str | None:
        """Why `decider` may not make `player`'s choices, or None (CR 723.5).

        "While controlling another player, a player makes all choices and
        decisions the controlled player is allowed to make or is told to make by
        the rules or by any objects." Everyone decides for themselves by default
        (CR 723.9), and CR 723.8 leaves a controller's own choices theirs; the
        only thing refused here is a player reaching for somebody else's
        decisions without an effect that gives them.
        """
        if self.is_over:
            return self.why_game_is_over()
        actual = self.controller_of_player(player)
        if decider == actual:
            return None
        if actual != player:
            return f"{actual} is deciding for {player} this turn, not {decider} (CR 723.5)"
        return f"nothing gives {decider} control of {player} (CR 723.5)"


from ...machines.free_cast_price import with_board_priced_cost  # noqa: E402
from ._common import ENERGY_PAID_OR_LOST, Targetable  # noqa: E402
from ._costs_mana import _cost_refers_to_self, _named_mana_abilities  # noqa: E402
from ._stack_priority import _illegal_option_refusal, _that_player_of  # noqa: E402
from .records import CountersPutRecord  # noqa: E402

#: The cost components `Game.may_pay_unless_cost` has the payer choose objects for,
#: with the verb the question uses.
_CHOSEN_OBJECT_KINDS = {
    ComponentKind.DISCARD: "discard",
    ComponentKind.SACRIFICE: "sacrifice",
    ComponentKind.GAIN_CONTROL: "gain control of",
}
