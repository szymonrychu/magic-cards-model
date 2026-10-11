import re
from typing import TYPE_CHECKING
from uuid import UUID

from ...machines import combat as combat_rules
from ...machines.abilities import (
    TriggeredAbility,
    TriggerEvent,
)
from ...machines.casting_restrictions import (
    CastingRuleEffect,
)
from ...machines.decisions import (
    Decision,
    DecisionKind,
    source_id_of,
)
from ...machines.keywords import (
    apply_daybound_nightbound,
    attachment_state_based_actions,
    aura_state_based_actions,
    equipment_state_based_actions,
    grant_enduring_stories,
    grant_the_citys_blessing,
    is_indestructible,
    transform_for_day_night,
)
from ...machines.layers import (
    DOESNT_UNTAP_TEXT,
    LEGEND_RULE_EXEMPT_TEXT,
    ComputedBoard,
    Duration,
)
from ...machines.opening_hand import (
    OpeningHandAction,
    OpeningHandActionKind,
    perform_rider,
    read_opening_hand_actions,
)
from ...machines.replacement import (
    EventKind,
    ReplaceableEvent,
    apply_replacements,
)
from ...machines.speed import (
    players_starting_their_engines,
    start_engines,
)
from ...machines.triggers import (
    ExtraTriggerEvent,
    GameEvent,
)
from ...machines.turn import (
    STEP_SEQUENCE,
    DayNight,
    Step,
    day_night_after_untap_check,
)
from ...snapshot import scan_pin
from ..card import (
    Supertype,
    Type,
)
from ..card_state import (
    LETHAL_BY_POWER_TEXT,
    MAY_STAY_TAPPED_TEXT,
    UNTAPS_IN_OTHER_UNTAP_TEXT,
    CardState,
    Counter,
    annihilate_counters_on,
    planeswalkers_with_zero_loyalty,
)
from ..mana import ManaRetentionScope
from ..player import Player
from ..token import (
    tokens_that_cease_to_exist,
)
from ..zone import Zone
from .records import UntapStepRule

if TYPE_CHECKING:
    from . import Game


#: Sanctum Lurker's own "Planeswalkers you control aren't put into their
#: owners' graveyards for having 0 loyalty." - a real, printed CR 704.5i
#: exemption, read off a permanent's own printed text the same way
#: `_CONDITION_SUSPENDED` and every other bare board-fact regex here is
#: (`class_ability_text`, not the computed board - CR 101.2's "the card
#: overrides the rule" needs the card to still be one that overrides it,
#: which a permanent that lost its own ability in layer 6 would not be, but
#: nothing in the pool ever grants *this* ability to something else, so the
#: simpler printed-text read is what the pool actually needs).
_ZERO_LOYALTY_EXEMPTION_RE = re.compile(
    r"planeswalkers you control aren'?t put into (?:their|his or her) owners'? graveyards? "
    r"for having 0 loyalty",
    re.IGNORECASE,
)


class TurnSbaMixin:
    @property
    def is_over(self: "Game") -> bool:
        """A game with a winner is over, and so is a drawn one (CR 104.1)."""
        return self.winner is not None or self.drawn

    def why_game_is_over(self: "Game") -> str | None:
        """Why nothing more may happen in this game, or None while it goes on.

        CR 104.1: "A game ends immediately when a player wins, when the game is
        a draw, or when the game is restarted." Once it has ended nothing
        resolves, nothing is put on the stack, no decision is raised, and every
        action is refused with this reason (battle report B6-06).
        """
        if not self.is_over:
            return None
        outcome = f"{self.winner} won" if self.winner is not None else "it is a draw"
        return (
            f"the game is over: {outcome} (CR 104.1: a game ends immediately when a "
            "player wins, when the game is a draw, or when the game is restarted)"
        )

    def _refuse_if_over(self: "Game") -> None:
        """Raise `why_game_is_over`'s reason once the game has ended (CR 104.1)."""
        refusal = self.why_game_is_over()
        if refusal is not None:
            raise ValueError(refusal)

    @property
    def active_player(self: "Game") -> Player:
        assert self.turn is not None
        return self.player(self.turn.active_player)

    def player(self: "Game", username: str) -> Player:
        for player in self.players:
            if player.username == username:
                return player
        raise KeyError(f"no player named {username}")

    @property
    def players_in_game(self: "Game") -> list[Player]:
        """Everyone who has not yet lost or conceded (CR 104.3a, 104.5)."""
        return [player for player in self.players if self.is_in_game(player.username)]

    def is_in_game(self: "Game", username: str) -> bool:
        """True while this player is still playing.

        A player who has conceded or lost leaves the game immediately, and is
        no longer something a spell can affect: a player who concedes leaves
        the game immediately (CR 104.3a), a player who loses leaves too
        (CR 104.5), and their objects leave with them (CR 800.4a).
        """
        return (
            any(player.username == username for player in self.players)
            and username not in self.conceded
            and username not in self.losers
        )

    def untap_step_rule(self: "Game", username: str) -> UntapStepRule:
        """Which permanents this player would untap at their untap step.

        The one place the "what untaps" rule lives. `_untap_step_impl` reads
        it and then does the untapping; any other reader that needs to know
        what the next untap step would do - a mana hypothetical looking a turn
        ahead - asks this rather than keeping a second copy of the filter,
        which is the only way the two cannot drift apart.

        A **question, not a move**: it mutates nothing and emits nothing. It
        does not spend the skip it reports, does not untap anything, and
        raises no CR 502.3 untap event. The caller does all three, afterwards.

        Two rules, in the order the step applies them:

        - **CR 614.10**: "Skip [something]" is "Instead of doing [something],
          do nothing", so a pending skip is the verdict for the whole step and
          the permanent list is empty - nothing untaps, and no permanent is
          reported as untapping.
        - **CR 502.3**: "the active player determines which permanents they
          control will untap ... Normally, all of a player's permanents untap,
          but effects can keep one or more of a player's permanents from
          untapping." The permanents this player controls, less the ones
          carrying the "doesn't untap during its controller's untap step"
          line, read off the computed board (CR 613.5: the layer system is
          applied "continually and automatically") rather than printed text.

        **The one thing this rule does not cover: stun counters (CR 122.1d).**
        A stun counter is a replacement effect on the untap itself - "If a
        permanent with a stun counter on it would become untapped, instead
        remove a stun counter from it" - and it is spent inside
        `CardState.untap`, where every route to untapping passes. It is
        deliberately not part of this filter, because this filter answers
        which permanents the step *attempts* to untap and CR 122.1d replaces
        the attempt rather than removing the permanent from the batch. A
        caller that reads this function and does not go on through
        `Player.untap_all` therefore **over-reports a stunned permanent as
        untapping**, and must consume `CardState.counter_count(Counter.STUN)`
        itself if it needs the real answer.
        """
        if self.players_skipping_next_untap.get(username, 0) > 0:
            return UntapStepRule(skipped=True, permanents=[])
        return UntapStepRule(
            skipped=False,
            permanents=[
                state
                for state in self.permanents_controlled_by(username)
                if not self.characteristics_of(state).has_ability(DOESNT_UNTAP_TEXT)
                and not state.cant_become_untapped
            ],
        )

    def untap_step(self: "Game") -> None:
        """Untap everything the active player controls (CR 502.3).

        The turn has begun by now, so anything the active player already
        controls stops being summoning sick (CR 302.6).

        CR 502.3 untaps them "all simultaneously", but each permanent that
        untaps is its own event (CR 603.2c: an ability triggers each time its
        trigger event occurs), so "Whenever this creature becomes untapped"
        (CR 701.26b) fires once per tapped permanent, not once for the batch.
        A permanent that was already untapped is not untapped by this step -
        only tapped permanents can be untapped (CR 701.26b) - and so triggers
        nothing.

        Run under `_id_allocator_scope`: `_untap_step_impl`'s own `emit` per
        untapped permanent mints a fresh `AbilityOnStack` id for every
        "becomes untapped" trigger it finds. `turn_based_actions` already
        reaches this from inside `advance`'s own scope, but the api's `set_
        step` also calls it directly on its own (`engine_api.py` around line
        953), so it needs a scope of its own rather than relying on that
        nesting.
        """
        with self._id_allocator_scope():
            self._untap_step_impl()

    def _untap_step_impl(self: "Game") -> None:
        """The rest of `untap_step` - see its own docstring for why it is split out."""
        active = self.active_player
        from ...machines.conditions.history import note_hand_sizes_at_turn_start

        note_hand_sizes_at_turn_start(self)
        # CR 502.1 comes first in the step: phased-out permanents the active
        # player controlled when they phased out phase in, before CR 502.3
        # untaps anything - and before `begin_turn_for`, so a permanent
        # phasing in is one its controller has controlled continuously
        # (CR 702.26d: phasing changes no control) and sheds summoning
        # sickness with the rest. CR 702.26m: "If an effect causes a player
        # to skip their untap step, the phasing event simply doesn't occur
        # that turn."
        if self.players_skipping_next_untap.get(active.username, 0) == 0:
            self.phase_in_for(active.username)
        self.begin_turn_for(active.username)
        # `untap_step_rule` is the rule itself - the CR 614.10 skip verdict and
        # the CR 502.3 batch, with CR 122.1d's stun counter deliberately left
        # to `CardState.untap` (see its docstring). It reads; this method is
        # the only place that then writes: spending the skip, untapping, and
        # emitting.
        verdict = self.untap_step_rule(active.username)
        if verdict.skipped:
            # CR 614.10: "skip [something]" replaces the step with nothing -
            # nothing untaps and no BECOMES_UNTAPPED event fires, exactly as
            # if the step never happened.
            remaining = self.players_skipping_next_untap[active.username]
            if remaining > 1:
                self.players_skipping_next_untap[active.username] = remaining - 1
            else:
                del self.players_skipping_next_untap[active.username]
            return
        # CR 502.2: second, the day/night check (CR 731.2) - after CR 502.1's
        # phasing and before CR 502.3's untap, and skipped with the step.
        self._day_night_untap_check()
        untappable = [
            state
            for state in (
                *verdict.permanents,
                *self._untapping_in_others_untap_step(active.username),
            )
            if not self._chooses_not_to_untap(state)
        ]
        tapped = [state for state in untappable if state.tapped]
        active.untap_all(untappable)
        for state in tapped:
            self.emit(
                GameEvent(
                    event=TriggerEvent.BECOMES_UNTAPPED,
                    subject_id=state.id,
                    subject_name=state.name,
                    subject_controller=state.controller,
                    subject_card=state.card,
                    player=state.controller,
                )
            )
        # CR 502.3's untap is one simultaneous event for the whole step, and
        # "you untap one or more permanents" asks about it with its count -
        # the permanents that actually untapped, and none at all is no event
        # (CR 603.2g).
        untapped = sum(1 for state in tapped if not state.tapped)
        if untapped:
            self.emit(
                GameEvent(
                    event=ExtraTriggerEvent.UNTAPPED_DURING_UNTAP_STEP,
                    player=active.username,
                    amount=untapped,
                    step=Step.UNTAP,
                )
            )

    def _chooses_not_to_untap(self: "Game", state: CardState) -> bool:
        """CR 502.3, CR 604.2: "You may choose not to untap this <permanent>
        during your untap step." - asked of the controller only while the
        permanent is tapped, and an unscripted player declines (it untaps)."""
        if not state.tapped or state.controller is None:
            return False
        if not self.characteristics_of(state).has_ability(MAY_STAY_TAPPED_TEXT):
            return False
        return bool(
            self.ask(
                Decision(
                    kind=DecisionKind.MAY,
                    player=state.controller,
                    prompt=f"leave {state.name} tapped instead of untapping it (CR 502.3)?",
                    source=state.name,
                    source_id=source_id_of(state),
                    default_may=False,
                )
            )
        )

    def _untapping_in_others_untap_step(self: "Game", active: str) -> list[CardState]:
        """CR 502.3, CR 604.2: the permanents "Untap all <group> you control
        during each other player's untap step." (Seedborn Muse) reaches - those
        controlled by someone other than the active player that carry the
        marker the group sentence grants. Stun (CR 122.1d) and "can't become
        untapped" apply as they do to any untap."""
        return [
            state
            for state in self.battlefield
            if state.controller != active
            and not state.cant_become_untapped
            and self.characteristics_of(state).has_ability(UNTAPS_IN_OTHER_UNTAP_TEXT)
        ]

    def _day_night_untap_check(self: "Game") -> None:
        """CR 502.2's turn-based action: the previous turn's active player's
        spells decide whether day becomes night or night becomes day
        (CR 731.2a, CR 731.2b); with neither designation nothing is checked
        (CR 731.2c). Copies are not cast, so `spells_cast_last_turn` already
        leaves them out."""
        if self.day_night is None or self.previous_turn_active_player is None:
            return
        cast = len(self.spells_cast_last_turn.get(self.previous_turn_active_player, []))
        designation = day_night_after_untap_check(self.day_night, cast)
        if designation is not None:
            self.set_day_night(designation)

    def set_day_night(self: "Game", designation: DayNight) -> None:
        """Make it day or night (CR 731.1).

        As it becomes night, every front-face-up daybound permanent transforms
        (CR 702.145b); as it becomes day, every back-face-up nightbound one
        does (CR 702.145e). Only replacing one designation with the other is
        "day becomes night" or "night becomes day" (CR 731.1a), so only that
        raises the event a "Whenever day becomes night or night becomes day"
        trigger watches - becoming day from neither triggers nothing.
        """
        with self._id_allocator_scope():
            previous = self.day_night
            if previous is designation:
                return
            self.day_night = designation
            transform_for_day_night(self)
            if previous is None:
                return
            self.emit(
                GameEvent(
                    event=ExtraTriggerEvent.DAY_BECOMES_NIGHT
                    if designation is DayNight.NIGHT
                    else ExtraTriggerEvent.NIGHT_BECOMES_DAY
                )
            )

    def become_day(self: "Game") -> None:
        """ "It becomes day" (CR 731.1)."""
        self.set_day_night(DayNight.DAY)

    def become_night(self: "Game") -> None:
        """ "It becomes night" (CR 731.1)."""
        self.set_day_night(DayNight.NIGHT)

    def phase_out(self: "Game", permanent: CardState) -> None:
        """`permanent` phases out, with everything attached to it (CR 702.26b,
        CR 702.26g).

        CR 702.26b: its status becomes "phased out" and it "is treated as
        though it does not exist ... A permanent that phases out is removed
        from combat" (CR 506.4 too). It leaves `battlefield` for
        `phased_out`, which is the whole of "does not exist" for every reader
        of the battlefield. CR 702.26d: no zone change - `zone` is untouched,
        no leaves-the-battlefield event is emitted, and counters stay on it.

        CR 702.26g: Auras, Equipment and Fortifications attached to it phase
        out "indirectly" at the same time, and CR 702.26h makes an object
        that would phase out both ways at once phase out only indirectly.
        CR 702.26j: nothing becomes attached or unattached, so `attachment`
        is left exactly as it was.

        A permanent that is not on the battlefield (already phased out, or
        gone) does nothing: CR 702.26b's phased-out permanent "can't ... be
        affected by anything else in the game".
        """
        if permanent not in self.battlefield:
            return
        under = self.controller_of(permanent).username
        attached = self._attached_to_recursively(permanent)
        for state in (permanent, *attached):
            self.battlefield.remove(state)
            self.combat.remove(state.id)
            state.phased_out_under = under
            state.phased_out_indirectly = state is not permanent
            self.phased_out.append(state)

    def phase_in(self: "Game", permanent: CardState) -> None:
        """`permanent` phases in, with what phased out indirectly with it
        (CR 702.26c, CR 702.26g).

        CR 702.26c: "The game once again treats it as though it exists." It
        goes back to `battlefield` with its counters and attachments intact;
        CR 702.26d: no enters-the-battlefield event. An Aura or Equipment
        that phased out indirectly comes back only here, along with its host.
        """
        if permanent not in self.phased_out:
            return
        returning = [permanent]
        frontier = [permanent.id]
        while frontier:
            host_id = frontier.pop()
            for state in self.phased_out:
                if (
                    state.phased_out_indirectly
                    and state.attached_to == host_id
                    and state not in returning
                ):
                    returning.append(state)
                    frontier.append(state.id)
        for state in returning:
            self.phased_out.remove(state)
            state.phased_out_under = None
            state.phased_out_indirectly = False
            self.battlefield.append(state)

    def phase_in_for(self: "Game", username: str) -> None:
        """CR 502.1's phasing turn-based action for `username`'s untap step:
        "all phased-out permanents that the active player controlled when
        they phased out phase in ... This all happens simultaneously."

        Only permanents that phased out directly are picked up here; an
        indirectly phased-out one phases in with its host (CR 702.26g).

        The other half of CR 502.1 - permanents *with phasing* phasing out -
        is not run here: no printing legal in Modern, Pioneer or Standard
        carries the phasing keyword (CR 702.26a), so nothing could exercise
        it.
        """
        for state in [
            state
            for state in self.phased_out
            if state.phased_out_under == username and not state.phased_out_indirectly
        ]:
            self.phase_in(state)

    def turn_based_actions(self: "Game") -> None:
        """Perform the turn-based actions of the step that has just begun (CR 703.3).

        These happen automatically, are controlled by no player (CR 703.2), and
        do not use the stack (CR 703.1). CR 703.3 puts them before state-based
        actions and before anybody would receive priority, which is the order
        `advance` runs them in.

        What is implemented here, from the CR 703.4 list:

        - **CR 703.4c / 502.3** - the untap step untaps the active player's
          permanents.
        - **CR 703.4d / 504.1** - the draw step draws a card, unless this is the
          first turn of a two-player game and the active player played first
          (CR 103.8a).
        - **CR 703.4f / 505.4 / 714.3c** - the precombat main phase puts a lore
          counter on each Saga the active player controls with one or more
          chapter abilities (`saga_lore_step`).
        - **CR 703.4i / 508.1** - the declare attackers step asks the active
          player which creatures attack, and at whom (`declare_attackers_step`).
        - **CR 703.4j / 509.1** - the declare blockers step asks each defending
          player, in turn order (CR 802.4), which creatures block
          (`declare_blockers_step`).
        - **CR 703.4k / 510.1** - the combat damage step deals the assigned
          damage. Exactly one `combat_damage_step()` per occurrence of the
          step - CR 510.4's second occurrence is its own step, with its own
          beginning and its own turn-based action, queued by
          `_advance_past_checks` rather than run twice in a row here
          (`Game.combat_damage()` is the two-step helper for a caller driving
          combat manually, outside this automatic path).
        - **CR 703.4n / 514.1** - the cleanup step discards down to maximum hand
          size.
        - **CR 703.4p / 514.2** - then removes all damage marked on permanents.
        - **CR 703.4q / 500.5** - as each step or phase ends, mana pools empty
          (`empty_mana_pools`, run at every boundary `advance` and `advance_to`
          cross; a step-end action, unlike the step-begin ones above).

        Everything else on the CR 703.4 list needs a mechanic this model does
        not have - see `docs/engine-coverage.md`.
        """
        assert self.turn is not None
        if not self.is_in_game(self.turn.active_player):
            # CR 800.4j: the turn runs to its end without an active player, so
            # there is nobody to untap, draw, attack, block, or discard.
            return
        step = self.turn.step
        if step is Step.UNTAP:
            self.untap_step()
        elif step is Step.DRAW:
            self.draw_step()
        elif step is Step.PRECOMBAT_MAIN:
            self.saga_lore_step()
        elif step is Step.DECLARE_ATTACKERS:
            self.declare_attackers_step()
        elif step is Step.DECLARE_BLOCKERS:
            self.declare_blockers_step()
        elif step is Step.COMBAT_DAMAGE:
            self.combat_damage_step()
        elif step is Step.CLEANUP:
            self.cleanup_step()

    def draw_step(self: "Game") -> list[CardState]:
        """The active player draws a card (CR 504.1, 703.4d).

        Drawing from a library that cannot supply the card is not an error: the
        player draws what is there and loses at the next state-based check
        (CR 104.3c, 704.5b).
        """
        assert self.turn is not None
        if self.turn.skips_draw() or self.static_skips_draw_step():
            return []
        return self.draw_cards(self.active_player, 1)

    def saga_lore_step(self: "Game") -> None:
        """CR 703.4f, 505.4, 714.3c: a lore counter on each Saga the active
        player controls with one or more chapter abilities, as their
        precombat main phase begins.

        "This turn-based action doesn't use the stack" (CR 714.3c) - straight
        through `add_counters`, same as any other counter placed outside a
        resolving effect, which is what lets `_emit_lore_counters_added` fire
        CR 107.15a's chapter trigger for whichever threshold this crosses.
        Every Saga controlled gets exactly one, all "simultaneously" the way
        CR 703.4f's own wording has it - order between different Sagas is
        never observable here since nothing this engine reads depends on it.
        """
        active = self.active_player
        for permanent in self.permanents_controlled_by(active.username):
            if permanent.is_saga and permanent.chapter_numbers:
                self.add_counters(permanent, Counter.LORE, 1)

    def end_the_turn(self: "Game") -> None:
        """CR 724.1's "end the turn" procedure - Time Stop's whole text.

        CR 724.1: "Some cards end the turn. When an effect ends the turn, follow
        these steps in order, as they differ from the normal process for
        resolving spells and abilities (see rule 608)." The steps this performs,
        each looked up in full:

        - **CR 724.1a** - "If there are any triggered abilities that triggered
          before this process began but haven't been put onto the stack yet,
          those abilities cease to exist. They won't be put onto the stack."
          `pending_triggers` is emptied.
        - **CR 724.1b** - "Exile every object on the stack, including the object
          that's resolving." An ability on the stack has no card behind it
          (CR 405.1), so it simply ceases to exist; a spell is a card and goes
          to the exile zone. The resolving object is `Game.resolving`, and
          **CR 608.2m** is why exiling it does not stop it: "If an instant
          spell, sorcery spell, or ability that can legally resolve leaves the
          stack once it starts to resolve, it will continue to resolve fully."
          So Time Stop's own remaining text - a spliced-on card's, say - still
          runs after this returns.
        - **CR 724.1c** - "Check state-based actions. No player gets priority,
          and no triggered abilities are put onto the stack." `check_state_
          based_actions` alone is exactly this half of CR 704.3: it performs
          every applicable state-based action (a lethally damaged creature
          here, say) and records whatever that triggers in `pending_triggers`
          the same way any other state-based check does, but - unlike
          `_check_state_based_actions_and_stack_triggers`, which every ordinary
          priority moment goes through - it never calls `put_triggers_on_stack`
          itself, so nothing this finds reaches the stack here.
        - **CR 724.1d** - "The current phase and/or step ends. If this happens
          during combat, remove all creatures and planeswalkers from combat.
          The game skips straight to the cleanup step; skip any phases or
          steps between this phase or step and the cleanup step. If an effect
          ends the turn during the cleanup step, a new cleanup step begins."
          `advance_to(Step.CLEANUP)` is a no-op when the pointer is already
          there, which is exactly how "a new cleanup step begins" for that
          case reaches the same `cleanup_owed` machinery as the ordinary one -
          see below.
        - **CR 724.1e** - "Even though the turn ends, 'at the beginning of the
          end step' triggered abilities don't trigger because the end step is
          skipped." `TurnMachine.advance_to` moves the pointer with no event of
          its own; only `Game._advance_past_checks`'s own step-by-step walk
          ever emits `TriggerEvent.BEGINNING_OF_STEP`, and this never calls it,
          so the end step's trigger simply never gets a moment to fire.
        - **CR 724.1f** - "No player gets priority during this process, so
          triggered abilities are not put onto the stack. If any triggered
          abilities have triggered since this process began, those abilities
          are put onto the stack during the cleanup step, then the active
          player gets priority and players can cast spells and activate
          abilities. Then there will be another cleanup step before the turn
          finally ends. If no triggered abilities have triggered during this
          process, no player gets priority during the cleanup step." The
          cleanup step's own CR 514.1/514.2 turn-based actions are not
          performed here - `cleanup_owed` records that they are owed instead -
          which is what leaves an "until end of turn" effect (Giant Growth's
          own pump, say) still running for whatever the resolution does next.
          `Game._before_priority`, called as that resolution finishes (every
          call site of it is a resolution's own final step), pays the debt:
          it runs `cleanup_step`, then the ordinary CR 704.3/603.3 check every
          resolution already gets - which is CR 514.3a's own text a second
          time, catching whatever CR 724.1c or the cleanup step itself left
          pending and putting it on the stack with the active player given
          priority - and finding nothing left pending immediately after
          resolving whatever *did* get stacked is that same method's cue to
          pay off "another cleanup step" the identical way, recursively.
        """
        with self._id_allocator_scope():
            assert self.turn is not None
            self.pending_triggers = []  # CR 724.1a
            for stack_object in list(self.stack):  # CR 724.1b
                self.stack.remove(stack_object)
                if isinstance(stack_object, CardState):
                    self._take_out_of_every_zone(stack_object)
                    self.combat.remove(stack_object.id)
                    stack_object.move_to(Zone.EXILE)
                    self.exile.append(stack_object)
                    self.forget_cast_record(stack_object)
            resolving = self.resolving
            if isinstance(resolving, CardState) and resolving not in self.exile:
                # CR 724.1b's "including the object that's resolving" - already
                # popped off the stack by `resolve_top`, so it is exiled by name.
                self._take_out_of_every_zone(resolving)
                self.combat.remove(resolving.id)
                resolving.move_to(Zone.EXILE)
                self.exile.append(resolving)
                self.turn_ended_exiled_ids.add(resolving.id)
            self.check_state_based_actions()  # CR 724.1c
            # CR 724.1d, the combat half: removing every creature and planeswalker
            # from combat is `CombatMachine.clear`'s whole job.
            self.combat.clear()
            self.turn.advance_to(Step.CLEANUP)  # CR 724.1d, the step-skip half
            self.cleanup_owed = True  # CR 724.1d/f: owed, not performed, here
            # CR 724.1c/724.1f: "No player gets priority during this process".
            # `step_grants_priority` reads `cleanup_owed` to keep withholding it
            # even though CR 724.1c's own check, just above, may already have
            # left something in `pending_triggers` - see that property's own
            # docstring.
            self.sync_priority_with_step()

    def cleanup_step(self: "Game") -> list[CardState]:
        """The cleanup step's two turn-based actions, in order (CR 514.1, 514.2).

        First the active player discards down to their maximum hand size
        (CR 703.4n). Then, as one simultaneous event (CR 703.4p), CR 514.2
        happens: "all damage marked on permanents (including phased-out
        permanents) is removed and all 'until end of turn' and 'this turn'
        effects end."

        Both halves are performed here, in that order, because they are one
        turn-based action rather than two - which is also why "until end of
        turn" outlasts the end step and only stops in cleanup.

        A prevention shield with a "this turn" duration ends in the same
        sentence: CR 615.3 gives a prevention effect a duration and CR 514.2
        ends every "this turn" effect here, so an unused shield stops existing
        rather than carrying into the next turn.
        """
        with self._id_allocator_scope():
            discarded = self.active_player.discard_to_maximum_hand_size()
            self.remove_all_damage()
            self.continuous_effects.end_the_turn(self)  # CR 514.2, the other half
            self.delayed_triggers.expire_this_turn()  # CR 514.2, the delayed-trigger half
            # CR 500.5b / 514.2, the same simultaneous action once more: Photon,
            # Mighty Marvel's "until end of turn, you don't lose this mana as
            # steps and phases end" mana (`ManaRetentionScope.END_OF_TURN`) has
            # survived every ordinary CR 500.5 emptying since it was added -
            # this is where it finally empties, alongside every other "until
            # end of turn" effect this step ends.
            self.empty_mana_pools(expiring=frozenset({ManaRetentionScope.END_OF_TURN}))
            self.prevention_shields = [
                shield
                for shield in self.prevention_shields
                if not shield.spent and not shield.until_end_of_turn
            ]
            # CR 514.2's same sentence again, for the replacement effects a
            # resolved spell or ability left behind: an "until end of turn" /
            # "this turn" one ends here, *after* the discard above - which is
            # the whole of DDR#957's ruling, since a draw that happens earlier
            # in this same cleanup step is still replaced.
            self.created_replacements = [
                replacement
                for replacement in self.created_replacements
                if not replacement.until_end_of_turn
            ]
            # CR 514.2's same sentence again, for the one-shot "next time ...
            # would draw ..., instead ..." replacements: whichever of these
            # never got a draw to consume this turn stops existing here.
            self.next_time_draw_replacements = [
                replacement
                for replacement in self.next_time_draw_replacements
                if not replacement.spent and not replacement.until_end_of_turn
            ]
            # CR 514.2's same sentence again, for Essence Burn's/Combustion
            # Technique's own this-turn die-to-exile replacements.
            self.die_to_exile_this_turn = []
            # CR 514.2's same sentence: "all 'until end of turn' ... effects end".
            # A card exiled by Ugin's −11 stays exiled and stops being castable.
            # A Wrenn's Resolve/Reckless Impulse grant (`expires_end_of_next_turn`)
            # is dropped here too, but only once `Game.begin_turn_for` has already
            # marked `owner_next_turn_started` for it (that player's own next turn
            # has begun) *and* this cleanup belongs to that same turn - i.e. this
            # is that turn's own end, not some later one.
            self.play_permissions = [
                permission
                for permission in self.play_permissions
                if not permission.until_end_of_turn
                and not (
                    permission.expires_end_of_next_turn
                    and permission.owner_next_turn_started
                    and self.turn.active_player == permission.player
                )
                # A Riveteers Charm grant whose end step has come and gone
                # (the pointer reached cleanup without `_note_step_began`
                # seeing the end step begin).
                and not permission.reached_next_end_step(self)
            ]
            # CR 514.2's same sentence, for Jace's Machinations' own "until
            # end of turn" instant-speed loyalty-activation grant.
            self.loyalty_instant_speed_permissions = [
                permission
                for permission in self.loyalty_instant_speed_permissions
                if not permission.until_end_of_turn
            ]
            # CR 514.2's same sentence, for CR 611.1's "affects the rules of the
            # game" effects: Ranger-Captain of Eos's "this turn" noncreature ban.
            self.casting_rule_effects = [
                effect
                for effect in self.casting_rule_effects
                if effect.duration is not Duration.UNTIL_END_OF_TURN
            ]
            # CR 514.2's same sentence, for a player's "until end of turn"
            # hexproof or shroud (CR 702.11c, CR 702.18a).
            for player in self.players:
                player.targeting_grants = [
                    grant
                    for grant in player.targeting_grants
                    if grant.duration is not Duration.UNTIL_END_OF_TURN
                ]
            # CR 514.2's same sentence, for The Vision's own "choose one that
            # hasn't been chosen this turn -": the per-turn half of
            # `CardState.chosen_modal_options_this_turn` ends here so next
            # turn's trigger offers every mode again. Gollum, Riddle
            # Master's unqualified `chosen_modal_options` is a different
            # field precisely so this reset never touches it.
            for permanent in self.battlefield:
                permanent.chosen_modal_options_this_turn = ()
            return discarded

    def begin_turn_for(self: "Game", username: str) -> None:
        """This player's turn has begun, so their permanents lose summoning sickness.

        "Continuously since their most recent turn began" (CR 302.6) is a
        one-way door per turn: everything they control right now has been here
        since the turn began, by definition.

        CR 611.2a: an "until [a player's] next turn" effect "lasts as long as
        stated by the spell or ability creating it", and that stated point is
        this same moment, so any effect keyed to this player's next turn ends
        here too (Karn, the Great Creator's +1).
        """
        for permanent in self.permanents_controlled_by(username):
            permanent.summoning_sick = False
        # CR 701.15a: a goad lasts "until the next turn of the controller of
        # that spell or ability" - this player's goads end now, and only
        # theirs (CR 701.15c: another goader's requirements stand).
        for permanent in self.battlefield:
            if username in permanent.goaded_by:
                permanent.goaded_by = [p for p in permanent.goaded_by if p != username]
        self.continuous_effects.end_for_next_turn(username)
        # ecl-T8: Morningtide's Light's own "Until your next turn, prevent
        # all damage that would be dealt to you." ends the same moment,
        # CR 611.2a's own stated duration - the identical hook every other
        # "until your next turn" store on this method already ends through.
        self.prevention_shields = [
            shield for shield in self.prevention_shields if shield.until_next_turn_of != username
        ]
        # Jace, Reality Sculptor's own `-3`: a delayed trigger's own "until
        # your next turn" ends the same instant the continuous-effect and
        # casting-rule stores above do (CR 603.7b's own "stated duration").
        self.delayed_triggers.expire_end_of_next_turn_for(username)
        # Teferi, Time Raveler's +1: "Until your next turn" ends the moment
        # this player's next turn would begin (CR 611.2a), the same instant
        # `end_for_next_turn` clears its own layer effects for this player.
        self.casting_rule_effects = [
            effect
            for effect in self.casting_rule_effects
            if not (
                effect.duration is Duration.UNTIL_YOUR_NEXT_TURN
                and effect.until_next_turn_of == username
            )
        ]
        # Blossoming Calm's "You gain hexproof until your next turn": the
        # player grant ends at the same moment (CR 611.2a).
        for player in self.players:
            player.targeting_grants = [
                grant
                for grant in player.targeting_grants
                if not (
                    grant.duration is Duration.UNTIL_YOUR_NEXT_TURN
                    and grant.until_next_turn_of == username
                )
            ]
        # Two different "next turn" permissions expire off this same hook, and
        # they are not the same shape. Hex Magic's own "Until the end of your
        # next turn, you may play cards exiled this way" (CR 611.2a again) is
        # carried by `PlayPermission.until_next_turn_of` and is dropped here,
        # the same moment as the two stores above. Wrenn's Resolve / Reckless
        # Impulse's own "until the end of your next turn" is carried by
        # `expires_end_of_next_turn` and is *not* dropped here: the moment this
        # is `username`'s own turn beginning again, past the turn it was granted
        # on, that permission's "next turn" has arrived, so it is only marked -
        # `Game.cleanup_step` removes it at this turn's own cleanup, once
        # `owner_next_turn_started` is set. Dropping happens first so a
        # permission carrying both is not marked on its way out.
        self.play_permissions = [
            permission.model_copy(update={"owner_next_turn_started": True})
            if (
                permission.player == username
                and permission.expires_end_of_next_turn
                and not permission.owner_next_turn_started
                and permission.granted_turns_taken != self.turn.turns_taken
            )
            else permission
            for permission in self.play_permissions
            if permission.until_next_turn_of != username
        ]

    def _turn_order_from_active(self: "Game") -> list[str]:
        """Every player, starting with the active player (CR 101.4, APNAP order)."""
        assert self.turn is not None
        players = list(self.turn.players)
        start = self.turn.active_index % len(players)
        return [players[(start + offset) % len(players)] for offset in range(len(players))]

    def _check_state_based_actions_and_stack_triggers(self: "Game") -> list[CardState]:
        """CR 704.3, then CR 603.3: the pair that precedes every "would receive
        priority" moment, not only a fresh step.

        CR 704.3: "Whenever a player would get priority ... the game checks for
        any of the listed conditions for state-based actions ... then performs
        all applicable state-based actions simultaneously ... This process
        repeats". CR 117.3c is exactly such a moment for the player who just
        cast a spell or activated an ability - they receive priority right back
        - so `retain_priority` calls this too, not only a step change or a
        resolution. A land drop uses no stack and never hands priority
        anywhere (CR 116.2a), so nothing changes for the player who played it
        until they next pass, which `pass_priority` covers by calling this
        before `PriorityMachine` acts on the pass.
        """
        gone = self.check_state_based_actions()
        self.put_triggers_on_stack()
        return gone

    def note_turn_count(self: "Game", fact: str, player: str, amount: int = 1) -> None:
        """Count `amount` more of `fact` for `player` this turn - `turn_counts`'
        own write half."""
        counts = self.turn_counts.setdefault(fact, {})
        counts[player] = counts.get(player, 0) + amount

    def turn_count(self: "Game", fact: str, player: str, *, last_turn: bool = False) -> int:
        """How many times `fact` has happened for `player` this turn, or last
        turn with `last_turn=True` (`turn_counts_last_turn`)."""
        ledger = self.turn_counts_last_turn if last_turn else self.turn_counts
        return ledger.get(fact, {}).get(player, 0)

    def turn_fact_holds(self: "Game", fact: str, player: str, *, last_turn: bool = False) -> bool:
        """Whether `fact` has happened for `player` this turn, or last turn
        with `last_turn=True` (`turn_facts_last_turn`, the same snapshot
        `spells_cast_last_turn` already takes for its own ledger)."""
        ledger = self.turn_facts_last_turn if last_turn else self.turn_facts
        return player in ledger.get(fact, set())

        # -- the pregame sequence (CR 103.5, CR 103.6) ----------------------------
        #
        # A game dealt from decklists *rests* in `Step.MULLIGAN` and then in
        # `Step.PREGAME_ACTIONS`, and every seat acts through the methods below.
        # Neither step asks anybody anything: `declare_mulligan`,
        # `take_opening_hand_action` and `finish_opening_hand_actions` are told an
        # answer that has already been made, so nothing here ever waits on a person.
        #
        # That is the whole point of the restructure. The previous shape ran both
        # sequences inside one call that put every question through `Game.ask`; with
        # a live seat behind an API that blocks until a human answers,
        # starting a game took one full answer timeout *per question per seat* -
        # measured at 1200 s (4 x 300 s) for two seats across both sequences - while
        # holding the game lock. A step the game rests in has no wait to hold: the
        # game sits there, publishes what it is waiting for, and moves the moment the
        # last seat has spoken.
        #
        # `settle_pregame` is the headless path and keeps the old behaviour exactly:
        # it asks each seat through the ordinary decision machinery, where an
        # unanswered question falls through to `default_answer` immediately.

    @property
    def in_pregame(self: "Game") -> bool:
        """Whether the game is still before CR 103.8's first turn."""
        return self.turn is not None and self.turn.in_pregame

    def begin_pregame(self: "Game", seed_prefix: str = "") -> Step:
        """Put this game in CR 103.5's mulligan step, before any turn has begun.

        Called by `Match.start_game` once the hands are dealt. `seed_prefix` is
        where every mulligan reshuffle's seed comes from - see `pregame_seed`.
        """
        assert self.turn is not None
        with self._id_allocator_scope():
            self.pregame_seed = seed_prefix
            self.mulligan_declarations = {}
            step = self.turn.begin_pregame()
            self._resolve_mulligan_round_if_ready()
            return self.turn.step if self.turn.in_pregame else step

    # -- CR 103.5: the mulligan process ---------------------------------------

    @property
    def mulligan_seats(self: "Game") -> list[Player]:
        """Players who have not yet kept a hand, in CR 103.5's declaration order.

        "First, the starting player declares whether they will take a mulligan.
        Then each other player in turn order does the same." `self.players` is
        seated with the starting player first, so walking it is that order.
        """
        return [player for player in self.players if not player.hand_kept]

    @property
    def awaiting_mulligan_declarations(self: "Game") -> list[str]:
        """Who still owes a declaration this round, in turn order.

        A player at CR 103.5's ceiling - "a player can take mulligans until their
        opening hand would be zero cards, after which they may not take further
        mulligans" - is offered no declaration at all and so is never awaited;
        keeping a hand of nothing is what is left to them.
        """
        if self.turn is None or self.turn.step is not Step.MULLIGAN:
            return []
        return [
            player.username
            for player in self.mulligan_seats
            if player.can_mulligan and player.username not in self.mulligan_declarations
        ]

    def declare_mulligan(self: "Game", username: str, take: bool) -> Step:
        """Record one seat's CR 103.5 declaration, resolving the round when it completes.

        This is the live seat's whole move, and it blocks on nothing: the answer
        is passed in, already made. When the last seat still owed a declaration
        has spoken, the round resolves here - "once each player has made a
        declaration, all players who decided to take mulligans do so at the same
        time" - and either a fresh round opens or the process is over and the
        game moves to `Step.PREGAME_ACTIONS`.

        Returns the step the game is in afterwards, which is how a caller learns
        that its declaration was the one that finished the round.
        """
        self._refuse_if_over()
        assert self.turn is not None
        if self.turn.step is not Step.MULLIGAN:
            raise ValueError(
                f"CR 103.5's mulligan process is not under way - the game is at {self.turn.step}"
            )
        player = self.player(username)
        if player.hand_kept:
            raise ValueError(f"{username} has already kept a hand")
        if username in self.mulligan_declarations:
            raise ValueError(f"{username} has already declared this round")
        if take and not player.can_mulligan:
            raise ValueError(
                f"{username} cannot mulligan past a hand of nothing "
                f"({player.mulligans_taken} taken) (CR 103.5)"
            )

        with self._id_allocator_scope():
            self.mulligan_declarations[username] = take
            self._resolve_mulligan_round_if_ready()
            return self.turn.step

    def _resolve_mulligan_round_if_ready(self: "Game") -> None:
        """Carry out one round of CR 103.5 once every declaration is in.

        Nothing happens while a seat still owes one. When they are all in:

        - if nobody declared a mulligan, everybody keeps, paying CR 103.5's
          bottoming cost, and the process is over;
        - otherwise "all players who decided to take mulligans do so at the same
          time" - every declaration was collected before any of this ran, which
          is what makes them simultaneous - and the players who declared against
          keep instead. A fresh round then opens for whoever mulliganed.

        A seat with no legal mulligan left counts as a declaration to keep, which
        is why the process always terminates: a player who keeps mulliganing runs
        out of hand.
        """
        assert self.turn is not None
        if self.turn.step is not Step.MULLIGAN:
            return
        if self.awaiting_mulligan_declarations:
            return

        deciding = self.mulligan_seats
        declarations = [
            (player, self.mulligan_declarations.get(player.username, False)) for player in deciding
        ]
        self.mulligan_declarations = {}

        for player, take in declarations:
            if take:
                # The same seed string the blocking loop derived, component for
                # component, so a replay with the same declarations is identical.
                player.mulligan(
                    f"{self.pregame_seed}:mulligan:{player.username}:{player.mulligans_taken}"
                )
        for player, take in declarations:
            if not take:
                player.keep_hand(self._bottom_for_keep(player))

        if not self.mulligan_seats:
            # CR 103.6 begins "once the mulligan process ... is complete".
            self.turn.advance()

    # -- opening-hand actions (CR 103.6) --------------------------------------

    def opening_hand_options(self: "Game", username: str) -> list[Decision]:
        """The CR 103.6 actions this seat may take right now, in hand order.

        "Some cards allow a player to take actions with them from their opening
        hand." A card that offers none, and a card whose restriction is not met
        (Gemstone Caverns in the starting player's hand), produce nothing here:
        the card does not "allow a player to take" that action, which is
        CR 103.6's own condition for there being a question at all.

        Read fresh off the hand every time, so an action already taken - the card
        has left the hand under CR 103.6a - is gone from the list. The `source`
        of each `Decision` names the card, and `Decision.card` its id, which is
        what `take_opening_hand_action` is keyed by.
        """
        player = self.player(username)
        return [decision for decision, _, _ in self._opening_hand_offers(player)]

    def _opening_hand_offers(
        self: "Game", player: Player
    ) -> list[tuple[Decision, OpeningHandAction, CardState]]:
        """Every CR 103.6 action on offer to this player, with what carries it."""
        assert self.turn is not None
        starting_player = self.turn.starting_player
        offers: list[tuple[Decision, OpeningHandAction, CardState]] = []
        for card_state in list(player.hand):
            actions, notices = read_opening_hand_actions(card_state.card)
            seen = {(notice.card_name, notice.text) for notice in self.opening_hand_notices}
            for notice in notices:
                if (notice.card_name, notice.text) not in seen:
                    self.opening_hand_notices.append(notice)
            for action in actions:
                if action.requires_not_starting_player and player.username == starting_player:
                    continue
                if card_state.id in self.opening_hand_reveals:
                    # CR 103.6b: "Each card may be revealed this way only
                    # once." A card put onto the battlefield under CR 103.6a
                    # leaves the hand, so the loop above stops offering it on
                    # its own - but a *revealed* card stays in hand
                    # (CR 701.20b), so without this it was offered again after
                    # being taken, for ever. Through the API that read as a
                    # button that did nothing: the action really was performed
                    # each time, and the panel came back unchanged.
                    continue
                offers.append(
                    (
                        Decision(
                            kind=DecisionKind.OPENING_HAND_ACTION,
                            player=player.username,
                            prompt=action.text,
                            source=card_state.name,
                            source_id=source_id_of(card_state),
                            card=card_state.id,
                        ),
                        action,
                        card_state,
                    )
                )
        return offers

    def take_opening_hand_action(self: "Game", username: str, card: UUID) -> None:
        """Take one CR 103.6 action with a card in this seat's opening hand.

        The live seat's move, and it blocks on nothing: taking it *is* the
        answer, and a seat that wants none calls `finish_opening_hand_actions`
        instead. "The starting player may take any such actions in any order" -
        so the order within a seat is the seat's, and this performs whichever
        card it is handed.

        Refused when it is not this seat's turn in CR 103.6's order, when the
        game is not in the opening-hand step, and when the named card offers no
        action - a card that does not allow the action is not permission to take
        it.
        """
        self._refuse_if_over()
        assert self.turn is not None
        if self.turn.step is not Step.PREGAME_ACTIONS:
            raise ValueError(
                f"CR 103.6's opening-hand actions are not under way - "
                f"the game is at {self.turn.step}"
            )
        if username != self.opening_hand_actor:
            raise ValueError(
                f"it is {self.opening_hand_actor}'s turn to take opening-hand "
                f"actions, not {username}'s (CR 103.6)"
            )
        player = self.player(username)
        with self._id_allocator_scope():
            for _, action, card_state in self._opening_hand_offers(player):
                if card_state.id == card:
                    self._perform_opening_hand_action(action, card_state, player)
                    return
        raise ValueError(f"no card in {username}'s opening hand offers that action (CR 103.6)")

    @property
    def opening_hand_actor(self: "Game") -> str | None:
        """Whose CR 103.6 actions the game is waiting on, or None if it is not waiting."""
        if self.turn is None or self.turn.step is not Step.PREGAME_ACTIONS:
            return None
        if self.opening_hand_seat >= len(self.players):
            return None
        return self.players[self.opening_hand_seat].username

    def finish_opening_hand_actions(self: "Game", username: str) -> Step:
        """This seat is done taking CR 103.6 actions; pass to the next one.

        When the last seat is done the pregame is over and CR 103.8's first turn
        begins - `Step.UNTAP`, turn 1, with `turn_number` and `turns_taken`
        moving off zero for the first time. Nothing untaps and nobody draws
        because of this: it moves the pointer, and the untap step's own
        turn-based actions happen when the game advances out of it, exactly as on
        every later turn.
        """
        self._refuse_if_over()
        with self._id_allocator_scope():
            assert self.turn is not None
            if self.turn.step is not Step.PREGAME_ACTIONS:
                raise ValueError(
                    f"CR 103.6's opening-hand actions are not under way - "
                    f"the game is at {self.turn.step}"
                )
            if username != self.opening_hand_actor:
                raise ValueError(
                    f"it is {self.opening_hand_actor}'s turn to take opening-hand "
                    f"actions, not {username}'s (CR 103.6)"
                )
            self.opening_hand_seat += 1
            if self.opening_hand_seat >= len(self.players):
                self.opening_hand_actions_taken = True
                self.turn.advance()  # CR 103.8: the starting player takes their first turn
            return self.turn.step

    def take_opening_hand_actions(self: "Game") -> list[Decision]:
        """CR 103.6's sequence: after the mulligan, before the first turn.

        "Some cards allow a player to take actions with them from their opening
        hand. Once the mulligan process (see rule 103.5) is complete, the
        starting player may take any such actions in any order. Then ea[ch other
        player ...]" - the excerpt from `knowledge_search` truncates there, so
        what is implemented is only what it states outright: the starting player
        first, then the rest, each player's own actions in an order this engine
        picks (hand order) because the rule leaves it free.

        `self.players` is seated with the starting player first (CR 103.8,
        `TurnMachine.starting_player`), so walking it *is* that order - the same
        list and the same reasoning `Match.run_mulligans` already uses for
        CR 103.5's declarations. CR 101.4's APNAP ordering is not what applies
        here: no turn has begun, so there is no active player, and CR 103.6
        states its own order.

        Every action is optional - "may take any such actions" - so every one is
        put to its player as a `DecisionKind.OPENING_HAND_ACTION` question and
        an unscripted player declines (see `machines/decisions.py`). A player
        holding no card that offers one is asked nothing at all, and a card
        whose restriction is not met (Gemstone Caverns in the starting player's
        hand) offers no action, so it is not asked either: the card does not
        "allow a player to take" that action, which is CR 103.6's own condition
        for there being a question.

        Nothing in this sequence is random, so nothing here needs the match seed
        that `Match.run_mulligans` derives for its reshuffles: given the same
        declarations and the same scripted answers, a replay reproduces it
        exactly.

        This is the **ask-driven** whole-sequence path: it puts every action to
        its player through `Game.ask`, which is what an unattended game wants and
        what every scenario here uses. A live seat that blocks on each answer
        should not be driven this way - it is one blocking wait per offer - and
        uses `opening_hand_options`, `take_opening_hand_action` and
        `finish_opening_hand_actions` instead, which ask nobody anything.

        Returns the questions that were put, in order. Idempotent: CR 103.6's
        sequence happens once per game, and CR 103.6b's "each card may be
        revealed this way only on[ce]" would be broken by a second run. When the
        game is resting in `Step.PREGAME_ACTIONS` this finishes every remaining
        seat, so it leaves the game at `Step.UNTAP` of CR 103.8's first turn.
        """
        with self._id_allocator_scope():
            if self.opening_hand_actions_taken:
                return []

            asked: list[Decision] = []
            in_pregame = self.turn is not None and self.turn.step is Step.PREGAME_ACTIONS

            if not in_pregame:
                # No pregame to walk - a game built board-first, which never entered
                # `Step.MULLIGAN`. The seat-by-seat bookkeeping has nothing to track,
                # so the sequence is run over the players directly and marked done.
                self.opening_hand_actions_taken = True
                for player in list(self.players):
                    asked.extend(self._ask_opening_hand_actions_of(player))
                return asked

            while (actor := self.opening_hand_actor) is not None:
                asked.extend(self._ask_opening_hand_actions_of(self.player(actor)))
                self.finish_opening_hand_actions(actor)

            return asked

    def _perform_opening_hand_action(
        self: "Game",
        action: OpeningHandAction,
        card_state: CardState,
        player: Player,
    ) -> None:
        """Carry out one accepted CR 103.6 action, then its rider.

        CR 103.6a puts the card onto the battlefield; CR 103.6b reveals it and
        leaves it where it is (CR 701.20b). The rider - the card's own trailing
        "If you do, ..." - runs afterwards, in the order the card prints it, and
        is parsed by `machines/opening_hand.read_rider` and carried out by
        `perform_rider`. An action whose rider no reader recognises never
        reaches here: it is refused while being read, with a notice.
        """
        if action.kind is OpeningHandActionKind.BEGIN_ON_BATTLEFIELD:
            self.put_onto_battlefield(card_state, player.username)
            if action.counter and card_state.zone is Zone.BATTLEFIELD:
                # "with a luck counter on it" - part of how it begins the game
                # there, so it is put on as soon as the permanent exists.
                self.add_counters(card_state, action.counter)
        else:
            # CR 103.6b: revealed, and it stays in hand (CR 701.20b).
            self.reveal(card_state, source=card_state.name)
            self.opening_hand_reveals.append(card_state.id)

        if action.rider:
            perform_rider(self, card_state, player, action.rider)

    def _turns_taken(self: "Game") -> int:
        return self.turn.turns_taken if self.turn is not None else 0

    def _is_draw_step_draw(self: "Game", player: Player) -> bool:
        """Whether this is the active player's draw-step draw (CR 504.1, 703.4d)."""
        assert self.turn is not None
        return self.turn.step is Step.DRAW and self.turn.active_player == player.username

    def check_state_based_actions(self: "Game") -> list[CardState]:
        """Apply state-based actions, returning whatever left the battlefield (CR 704).

        CR 704.3 performs every applicable action simultaneously as a single
        event, then checks again, repeating until none apply - which is why
        this loops rather than making one pass.

        What is checked, from the CR 704.5 list:

        - **CR 704.5a** - a player at 0 or less life loses the game.
        - **CR 704.5b** - a player who tried to draw from an empty library since
          the last check loses the game (CR 104.3c).
        - **CR 704.5c** - a player with ten or more poison counters loses.
        - **CR 704.5d** - "If a token is in a zone other than the battlefield, it
          ceases to exist." Not a zone change and not a death: the token is
          simply gone. CR 111.7's parenthesis is what makes the dying token's own
          trigger safe - it triggered while the token was still in the graveyard.
        - **CR 704.5f** - a creature with toughness 0 or less is put into its
          owner's graveyard.
        - **CR 704.5g** - a creature with lethal damage marked on it is destroyed.
        - **CR 704.5h** - "If a creature has toughness greater than 0, and it's
          been dealt damage by a source with deathtouch since the last time
          state-based actions were checked, that creature is destroyed." A
          separate rule from CR 704.5g, with a separate condition: one point of
          deathtouch damage is enough and the amount never enters into it.
        - **CR 704.5i** - "If a planeswalker has loyalty 0, it's put into its
          owner's graveyard." Loyalty is the number of loyalty counters on it
          (CR 306.5c, CR 122.1e), which a loyalty cost removes (CR 606.4) as
          often as it can take the walker to zero.
        - **CR 704.5j** - the legend rule.
        - **CR 704.5m** - "If an Aura is attached to an illegal object or player,
          or is not attached to an object or player, that Aura is put into its
          owner's graveyard." The opposite of CR 704.5n's Equipment, which stays
          on the battlefield. What counts as illegal is read off the Aura's own
          enchant ability by `machines/keywords.aura_state_based_actions`
          (CR 702.5a), so the announcement and the state-based action cannot
          disagree about the same sentence.
        - **CR 704.5n** - "If an Equipment or Fortification is attached to an
          illegal permanent or to a player, it becomes unattached from that
          permanent or player. It remains on the battlefield."
        - **CR 704.5z** - every Role but the newest on one permanent, controlled
          by one player, goes to its owner's graveyard.
        - **CR 704.5s** - a Saga whose lore counters (CR 714.3) are at least its
          final chapter number (CR 714.2e), and that is not the source of a
          chapter ability that has triggered but not yet left the stack, goes
          to its owner's graveyard.

        - **CR 704.5x / 704.5y** - a battle with no protector (and nobody
          attacking it), or a protector who can't be one, gets a new protector
          chosen by its controller, or goes to its owner's graveyard.

        The rest of CR 704.5 needs a mechanic this model does not have: copies
        (704.5e) and battle defense (704.5v-704.5w). See `docs/engine-coverage.md`.

        Losing is one-way: a player who is gone stays gone even if something
        later adds life back.

        When a check would remove *every* player still in the game at once, the
        game is a draw (CR 104.4a): nobody is left to win (CR 104.2a needs a
        player still in the game), so `drawn` is set and the losers leave under
        CR 104.5 like any other loss. The check that finds the game already
        over does nothing - CR 104.1 ends the game immediately, and a state
        that arrives after the end never happens.

        Run under `_id_allocator_scope`: each round's `_state_based_actions_
        once` mints a `zone_change_stamp` for every permanent it moves to a
        graveyard (CR 704.5f/704.5g/704.5h/704.5i/704.5m/704.5z/704.5s) and
        may emit a "dies" trigger for each, all persisted ids. `pass_priority`
        and `resolve_top` already reach this from inside their own scopes,
        but the api's `run_state_based_actions` calls it directly too
        (`engine_api.py` around line 862), so it needs a scope of its own
        rather than relying on that nesting.
        """
        with self._id_allocator_scope():
            return self._check_state_based_actions_impl()

    def _drop_ended_while_source_rules(self: "Game") -> None:
        """CR 611.2b: a recorded "for as long as this remains on the
        battlefield" rule ends when that object leaves (CR 400.7: a return is
        a new object). `player_counters_prohibited` already stops reading an
        ended one; this drops it from the game so it is not carried in every
        later snapshot. Every point state-based actions are checked is a point
        the game looks, the same way daybound is caught below."""

        def running(effect: CastingRuleEffect) -> bool:
            if effect.while_source_id is None:
                return True
            source = self.find_by_id(effect.while_source_id)
            return (
                source is not None
                and source.zone is Zone.BATTLEFIELD
                and source.zone_change_stamp == effect.while_source_stamp
            )

        if any(not running(effect) for effect in self.casting_rule_effects):
            self.casting_rule_effects = [
                effect for effect in self.casting_rule_effects if running(effect)
            ]

    def note_control_changes(self: "Game") -> None:
        """Stamp every permanent that has come under a new controller since it
        was last looked at with that controller's upkeep count
        (`CardState.controlled_since_upkeep`), for echo's "came under your
        control since the beginning of your last upkeep" (CR 702.30a).

        Control is a layer 2 answer (CR 613.1b), so a change of control has no
        single place it happens; every point state-based actions are checked
        is a point the game looks, and so is the beginning of each upkeep
        (`_advance_past_checks`), before its triggers are looked for - which catches an
        "until end of turn" control change that ended in the cleanup step."""
        for permanent in self.battlefield:
            current = permanent.controller
            if current is None:
                continue
            record = permanent.controlled_since_upkeep
            recorded = permanent.stored_controller if record is None else record[0]
            if current != recorded:
                permanent.controlled_since_upkeep = (current, self.upkeeps_begun.get(current, 0))

    def came_under_control_since_last_upkeep(self: "Game", permanent: CardState) -> bool:
        """CR 702.30a's intervening "if": this permanent came under its
        controller's control since the beginning of that player's last upkeep.

        Asked at the beginning of an upkeep (and again on resolution, CR
        603.4), after `_advance_past_checks` has counted the upkeep now beginning, so
        "your last upkeep" is the one before it: a stamp taken at or after that
        one began (`upkeeps >= count - 1`) came under control since then. A
        permanent never stamped has been under its controller's control since
        before any upkeep began (stamp 0)."""
        controller = permanent.controller
        if controller is None:
            return False
        self.note_control_changes()
        record = permanent.controlled_since_upkeep or (controller, 0)
        if record[0] != controller:
            return False
        return record[1] >= self.upkeeps_begun.get(controller, 0) - 1

    def _check_state_based_actions_impl(self: "Game") -> list[CardState]:
        """The rest of `check_state_based_actions` - see its own docstring
        for why it is split out."""
        if self.is_over:
            return []
        self._drop_ended_while_source_rules()
        self.note_control_changes()
        # CR 702.145c/d/f/g are not state-based actions - each "happens
        # immediately" any time its condition is true - but every point the
        # game checks state-based actions is a point it looks, so a permanent
        # that gained or lost daybound some other way is caught here too.
        apply_daybound_nightbound(self)
        # CR 603.2c: what the resolution or payment before this check did is
        # one batch, and each round of state-based actions below is another.
        self.announce_batched_events()
        gone: list[CardState] = []
        for _ in range(len(self.players) + len(self.battlefield) + 1):
            leaving = self._state_based_actions_once()
            gone.extend(leaving)
            self.announce_batched_events()
            would_lose = self._losing_players()
            if not leaving and not would_lose:
                break
            # CR 614/616.1: a player this check would remove gets a "would
            # lose the game" replacement's own first refusal (Exquisite
            # Archangel, Lich's Mirror) before the loss is real - so `losing`,
            # not `would_lose`, is what the draw check and the actual removal
            # below both read. A player whose loss got replaced never joins
            # either.
            losing = [
                username
                for username in would_lose
                if self._apply_lose_the_game_replacements(username)
            ]
            # CR 104.4a: "If all the players remaining in a game lose
            # simultaneously, the game is a draw." `losing` is who this check
            # actually removes and `players_in_game` is who it found still in
            # the game, so equal sets mean nobody survives to win. A solo game
            # has no draw to hand out, matching `_check_for_a_winner`'s guard.
            remaining = {player.username for player in self.players_in_game}
            if len(self.players) > 1 and losing and set(losing) == remaining:
                self.drawn = True
            for username in losing:
                self._lose_the_game(username)
        self._check_for_a_winner()
        return gone

    def _state_based_actions_once(self: "Game") -> list[CardState]:
        """One simultaneous round of the permanent-facing state-based actions.

        Toughness is the *computed* toughness (CR 613.5), not the printed value
        plus counters, because both rules are written about the creature as it
        is right now:

        - **CR 704.5f** - "If a creature has toughness 0 or less, it's put into
          its owner's graveyard. Regeneration can't replace this event."
        - **CR 704.5g** - "If a creature has toughness greater than 0, it has
          damage marked on it, and the total damage marked on it is greater than
          or equal to its toughness, that creature has been dealt lethal damage
          and is destroyed."

        That is what lets Elesh Norn's -2/-2 in layer 7c kill a 2/1, and what
        makes three damage on a Giant Spider lethal the moment layer 7d turns it
        into a 4/2. A creature whose computed toughness is not a number - which
        cannot happen once layer 7a has run, but can if the board is
        uncomputable - falls back to the printed value rather than being spared
        on a technicality.

        CR 704.5d and CR 704.5e (both sentences) all run first, against the
        board as the check found it: "If a token is in a zone other than the
        battlefield, it ceases to exist", "If a copy of a spell is in a zone
        other than the stack, it ceases to exist", and "If a copy of a card
        is in any zone other than the stack or the battlefield, it ceases to
        exist." A token or a copy that one of the actions below sends off in
        *this* round was still where it started when the conditions were
        checked, so it ceases to exist on the repeat check CR 704.3
        guarantees, not in the same event. See `_copies_that_cease_to_exist`
        for CR 704.5e's own scope; CR 722.3c's exile copy is that rule's one
        written exception, and this method is not where the exception lives.
        """
        # CR 704.3: the round is one simultaneous event (CR 603.10a).
        self._departure_epoch += 1
        gone_tokens = tokens_that_cease_to_exist(self)  # CR 704.5d, CR 111.7
        gone_copies = self._copies_that_cease_to_exist()  # CR 704.5e/707.10a
        self._remember_sources_that_ceased_to_exist(gone_tokens + gone_copies)

        # CR 704.5q: "If a permanent has both a +1/+1 counter and a -1/-1
        # counter on it, N +1/+1 and N -1/-1 counters are removed from it,
        # where N is the smaller of the number of +1/+1 and -1/-1 counters on
        # it" (CR 122.3 states the same rule from the counters' own side). A
        # direct mutation, not a move, so it runs before the read-only board
        # snapshot below rather than through `leaving`/`_put_state_based_
        # action_losers` - and it needs no repeat-until-stable loop of its
        # own: removing equal piles of +1/+1 and -1/-1 never changes net
        # power or toughness, so it can never make a *different* CR 704.5
        # condition newly true, only ever the same one CR 704.3's outer loop
        # in `_check_state_based_actions_impl` already repeats.
        annihilate_counters_on(self.battlefield)
        if any(state.paired_with is not None for state in self.battlefield):
            from ...machines.soulbond import release_broken_pairs

            release_broken_pairs(self)  # CR 702.95e

        # Every check below reads the battlefield and moves nothing, so they
        # share one layered board (`snapshot.scan_pin`); the moves come after.
        # CR 702.179a says outright that start your engines! is a state-based
        # action, so it is read off the same board as the rest of the round.
        with scan_pin(self):
            board, leaving = self._state_based_action_losers()
            starting = players_starting_their_engines(self)
        start_engines(starting)
        self._put_state_based_action_losers(leaving, board)
        return leaving + gone_tokens + gone_copies

    def _zero_loyalty_exemption_controllers(self: "Game") -> set[str]:
        """Every controller who controls a permanent granting CR 704.5i's own
        exemption ("Planeswalkers you control aren't put into their owners'
        graveyards for having 0 loyalty.", Sanctum Lurker) - see
        `_ZERO_LOYALTY_EXEMPTION_RE`."""
        return {
            self.controller_of(permanent).username
            for permanent in self.battlefield
            if _ZERO_LOYALTY_EXEMPTION_RE.search(permanent.class_ability_text)
        }

    def _state_based_action_losers(self: "Game") -> tuple[ComputedBoard, list[CardState]]:
        """The permanents one round of `_state_based_actions_once` removes, and
        the board they were judged on. Reads only."""
        board = self.computed_board()
        leaving = [
            state
            for state in list(self.battlefield)
            # CR 704.5f before CR 704.5g: a 0-toughness creature is put into the
            # graveyard whatever damage it has, and regeneration cannot stop it.
            # `board.of(state).is_creature` rather than the printed
            # `state.is_creature` (CR 613.5): an animated artifact (Karn, the
            # Great Creator's +1) is a creature on the computed board only.
            if board.of(state).is_creature and self._dies_to_state_based_action(state, board)
        ]
        leaving += [state for state in self._legend_rule_losers(board) if state not in leaving]
        # CR 704.5m, read off the Aura's own enchant ability (CR 702.5a) by
        # `machines/keywords.py`, which owns the reader `Casting` uses for the
        # announcement half of the same sentence.
        leaving += [state for state in aura_state_based_actions(self) if state not in leaving]
        leaving += [state for state in self._roles_beyond_the_newest(board) if state not in leaving]
        # CR 704.5i: "If a planeswalker has loyalty 0, it's put into its owner's
        # graveyard." Loyalty is the counter count (CR 306.5c), which is what
        # `planeswalkers_with_zero_loyalty` reads. Sanctum Lurker's own
        # "Planeswalkers you control aren't put into their owners' graveyards
        # for having 0 loyalty." is a real, printed exemption from this exact
        # SBA (CR 704.5i names no exception of its own; a card creating one is
        # ordinary CR 101.2 "the card overrides the rule"), scoped per
        # controller - `_zero_loyalty_exemption_controllers` below.
        exempt_controllers = self._zero_loyalty_exemption_controllers()
        leaving += [
            state
            for state in planeswalkers_with_zero_loyalty(self.battlefield)
            if state not in leaving and self.controller_of(state).username not in exempt_controllers
        ]
        # CR 704.5s, CR 714.4: a Saga whose lore counters reached its final
        # chapter number, once nothing left to run off it is still triggered.
        leaving += [state for state in self._sagas_to_put_into_graveyard() if state not in leaving]
        # CR 704.5v / 704.5w: a battle with defense 0.
        leaving += [
            state
            for state in self._defeated_battles_to_put_into_graveyard(board)
            if state not in leaving
        ]
        # CR 704.5x / 704.5y: a battle without a legal protector gets one, or
        # goes to its owner's graveyard when nobody can be chosen.
        leaving += [
            state
            for state in combat_rules.battle_protector_state_based_actions(self, board)
            if state not in leaving
        ]
        return board, leaving

    def _put_state_based_action_losers(
        self: "Game", leaving: list[CardState], board: ComputedBoard
    ) -> None:
        """`_state_based_actions_once`'s acting half: move `leaving`, then the
        attachment and ascend checks that follow it."""
        # `put_into_graveyard` rather than `destroy`, because CR 701.8b says only
        # CR 704.5g and CR 704.5h destroy: CR 704.5f, the legend rule (704.5j),
        # CR 704.5i, CR 704.5m and CR 704.5z all read "is put into its owner's
        # graveyard".
        # The two that *do* destroy have already had CR 702.12b applied to them
        # by `_dies_to_state_based_action`, so an indestructible permanent is not
        # in this list for either of them - and an indestructible 0/0 is, which
        # is the point of the distinction.
        for state in leaving:
            # CR 704.5g and CR 704.5h are destructions (CR 701.8b), so a
            # destruction-replacement - regeneration, umbra armor - gets its
            # say before the move. Everything else in `leaving` is "put into
            # its owner's graveyard" and cannot be replaced that way; CR 704.5f
            # states it outright ("Regeneration can't replace this event").
            if self._destroyed_by_state_based_action(state, board) and not self.destruction_happens(
                state
            ):
                continue
            self.put_into_graveyard(state)

        # CR 704.5n, after the round that killed the host: an Equipment whose
        # creature has just left becomes unattached and *stays on the
        # battlefield*, so it is not part of `leaving`. CR 704.3 makes every
        # applicable action one simultaneous event and then checks again, which
        # is what the caller's loop does. It runs after CR 704.5m so that an Aura
        # is already off the battlefield by the time it looks: `equipment_state_based_actions`
        # does not check that what it is unattaching is an Equipment.
        equipment_state_based_actions(self)
        # CR 704.5p, immediately after it: "If a battle or creature is attached
        # to an object or player, it becomes unattached and remains on the
        # battlefield." Unconditional where CR 704.5n asks whether the host is
        # legal, and read off the *computed* types (CR 613.5), which is how
        # CR 301.5c's "An Equipment that's also a creature can't equip a
        # creature" is enforced when a layer 4 effect animates an Equipment
        # that is already equipping something.
        attachment_state_based_actions(self)
        # CR 702.131b (ascend): "Any time you control ten or more permanents
        # ..." - granted the moment an event is raised (`emit`), and checked
        # here too for a change no event announces. See
        # `machines/keywords.grant_the_citys_blessing`.
        grant_the_citys_blessing(self)
        # CR 702.195a (storied): the enduring story, checked the same way.
        grant_enduring_stories(self)

    def _roles_beyond_the_newest(self: "Game", board: ComputedBoard) -> list[CardState]:
        """The Roles CR 704.5z puts into their owners' graveyards.

        "If a permanent has more than one Role controlled by the same player
        attached to it, each of those Roles except the one with the most recent
        timestamp is put into its owner's graveyard." CR 303.7a states the same
        rule, and CR 303.7 is what makes Role a subtype of Aura at all.

        Two conditions in that sentence do the work, and both are easy to drop:
        the Roles must be on the **same permanent**, and they must be controlled
        by the **same player** - two players' Roles on one creature both stay.

        The timestamp is CR 613.7a's, the one the permanent got as it entered the
        battlefield, which `machines/layers.ContinuousEffects` already keeps in
        `entered`. `board` is the one `_state_based_actions_once` already
        computed one frame earlier - CR 613.5's computed subtypes, not the
        printed `CardState.subtypes`, threaded in rather than recomputed so a
        board read from `.types`/`.subtypes` here never risks the exponential
        nested-computation trap a plain `CardState` read would (see
        `_asking_the_board`'s own docstring).
        """
        stamps = self.continuous_effects.entered
        groups: dict[tuple[UUID, str], list[CardState]] = {}
        for permanent in self.battlefield:
            if "Role" not in board.of(permanent).subtypes or permanent.attached_to is None:
                continue
            groups.setdefault((permanent.attached_to, permanent.controller or ""), []).append(
                permanent
            )

        doomed: list[CardState] = []
        for roles in groups.values():
            if len(roles) < 2:
                continue
            roles.sort(key=lambda role: stamps.get(role.id, 0))
            doomed.extend(roles[:-1])  # every one but the most recent timestamp
        return doomed

    def _defeated_battles_to_put_into_graveyard(
        self: "Game", board: ComputedBoard
    ) -> list[CardState]:
        """CR 704.5v: "If a Siege battle has defense 0 and it isn't the source
        of an ability that has triggered but not yet left the stack, it's put
        into its owner's graveyard." CR 704.5w: a non-Siege battle with
        defense 0 is, with no exception. Defense on the battlefield is the
        number of defense counters (CR 310.4c). "Triggered but not yet left
        the stack" is read the way `_sagas_to_put_into_graveyard` reads it:
        still pending (CR 603.3) or an `AbilityOnStack`."""
        still_owed = {
            item.source_id
            for item in (*self.pending_triggers, *self.abilities_on_stack)
            if isinstance(item.ability, TriggeredAbility)
        }
        defeated: list[CardState] = []
        for permanent in self.battlefield:
            chars = board.of(permanent)
            if Type.BATTLE not in chars.types or permanent.counter_count(Counter.DEFENSE) > 0:
                continue
            if "Siege" in chars.subtypes and permanent.id in still_owed:
                continue
            defeated.append(permanent)
        return defeated

    def _sagas_to_put_into_graveyard(self: "Game") -> list[CardState]:
        """CR 704.5s, CR 714.4: every Saga whose lore counters have reached
        its final chapter number, except one that is still the source of a
        chapter ability that "has triggered but not yet left the stack" -
        read here as either still `pending_triggers` (CR 603.3's window
        between triggering and actually being put on the stack) or already an
        `AbilityOnStack` in `self.stack` (CR 608.2n's window up to
        resolution) - a chapter III still resolving must not have its own
        Saga vanish out from under it mid-effect.
        """
        still_owed = {
            item.source_id
            for item in (*self.pending_triggers, *self.abilities_on_stack)
            if isinstance(item.ability, TriggeredAbility) and item.ability.chapter is not None
        }
        return [
            permanent
            for permanent in self.battlefield
            if permanent.lore_counters_exhausted and permanent.id not in still_owed
        ]

    def _dies_to_state_based_action(self: "Game", state: CardState, board: ComputedBoard) -> bool:
        """CR 704.5f and CR 704.5g, judged against the computed toughness.

        CR 702.12b splits the two: "A permanent with indestructible can't be
        destroyed. Such permanents aren't destroyed by lethal damage, and **they
        ignore the state-based action that checks for lethal damage** (see rule
        704.5g)." CR 704.5h destroys as well, and a permanent that can't be
        destroyed is not destroyed by it either.

        **CR 704.5f keeps applying.** "If a creature has toughness 0 or less,
        it's put into its owner's graveyard" - put into, not destroyed, which
        CR 701.8b confirms is a different thing, and the rule's own
        "Regeneration can't replace this event" is the clue that it is not a
        destruction to be stopped. An indestructible 0/0 dies.
        """
        if is_indestructible(state, self):
            # Only 704.5f is left, and it is judged below on toughness alone.
            return self._toughness_is_zero_or_less(state, board)
        try:
            toughness = board.of(state).toughness
        except KeyError:
            toughness = state.toughness
        if toughness is None:
            # A printed `*` with no characteristic-defining ability the engine
            # can read. CR 208.5 would call that 0 and CR 704.5f would bin the
            # creature; that is a worse answer than leaving it alone, because
            # the gap is in the registry rather than on the board. Neither rule
            # is applied, and CR 704.5h still is.
            return state.dealt_deathtouch_damage
        if toughness <= 0:
            return True  # CR 704.5f
        # CR 704.5g's arithmetic, plus CR 704.5h's deathtouch, which needs none.
        return self._damage_is_lethal(state, board, toughness)

    def _damage_is_lethal(
        self: "Game", state: CardState, board: ComputedBoard, toughness: int
    ) -> bool:
        """CR 704.5g / 704.5h against `toughness`, or against power while an
        effect says lethal damage is determined by power (Zilortha) - which
        still needs damage marked on the creature (CR 704.5g)."""
        chars = board.of(state)
        if LETHAL_BY_POWER_TEXT in chars.abilities and chars.power is not None:
            return (
                state.damage > 0 and state.damage >= chars.power
            ) or state.dealt_deathtouch_damage
        return state.damage >= toughness or state.dealt_deathtouch_damage

    def _destroyed_by_state_based_action(
        self: "Game", state: CardState, board: ComputedBoard
    ) -> bool:
        """Which of the state-based actions taking this permanent is a *destroy*.

        CR 701.8b names exactly two: CR 704.5g's lethal damage and CR 704.5h's
        damage from a deathtouch source. CR 704.5f's toughness of 0 or less,
        the legend rule, CR 704.5i, CR 704.5m and CR 704.5z all read "is put
        into its owner's graveyard" instead, so a destruction-replacement must
        not reach them.

        CR 704.5f wins where both would apply: a creature at 0 toughness is put
        into the graveyard whatever damage is marked on it, and regeneration
        cannot replace that event. So a 0-toughness creature answers False here
        even when it also has lethal damage marked.
        """
        if is_indestructible(state, self):
            return False  # CR 702.12b - it was never in `leaving` for these two
        if self._toughness_is_zero_or_less(state, board):
            return False  # CR 704.5f, not a destruction
        try:
            toughness = board.of(state).toughness
        except KeyError:
            toughness = state.toughness
        if toughness is None:
            return state.dealt_deathtouch_damage  # CR 704.5h needs no arithmetic
        return self._damage_is_lethal(state, board, toughness)

    def _legend_rule_losers(self: "Game", board: ComputedBoard) -> list[CardState]:
        """The legendary permanents the legend rule puts into graveyards (CR 704.5j).

        "If two or more legendary permanents with the same name are controlled
        by the same player, **that player chooses one of them**, and the rest
        are put into their owners' graveyards."

        The choice is real and is asked, one `CHOOSE_CARDS` question per
        (controller, name) group. Two players each holding two copies of the
        same legend is two separate choices made at the same time, which is
        what CR 101.4 orders: "If multiple players would make choices and/or
        take actions at the same time, the active player ... makes any choices
        required, then the next player in turn order". So the groups are walked
        in `_turn_order_from_active` order, active player first, and the
        question for each of that player's groups is put before the next
        player's.

        **The group is offered reversed.** `default_answer` for an exact
        `CHOOSE_CARDS` answers with the *back* of the offered cards, so
        reversing the group makes the unscripted default keep the copy that has
        been on the battlefield longest - the behaviour every scenario that
        does not care about the choice was already relying on. A scenario that
        does care answers the question instead.

        CR 613.5: grouped by the computed supertypes and name, not the
        printed ones - `BecomeACopy` (CR 707.2, 707.4) writes both, so a
        clone copying a legendary permanent has to be seen as sharing that
        legend's name and Legendary supertype, or the collision this rule
        exists for goes unnoticed.
        """
        groups: dict[str, dict[str, list[CardState]]] = {}
        for state in self.battlefield:
            chars = board.of(state)
            if Supertype.LEGENDARY not in chars.supertypes:
                continue
            controller = self.controller_of(state).username
            groups.setdefault(controller, {}).setdefault(chars.name, []).append(state)

        # Mirror Box / Sakashima of a Thousand Faces' own permanent static,
        # and Hall of Echoes' "... this turn" one-shot version: CR 604.2/
        # CR 611.2a either way, so the same computed-board question answers
        # both - a permanent controlled by `username` carrying the grant
        # exempts every legendary permanent that player controls, not only
        # the one granting it.
        exempt_players = {
            board.of(state).controller
            for state in self.battlefield
            if board.of(state).has_ability(LEGEND_RULE_EXEMPT_TEXT)
        }

        losers: list[CardState] = []
        for username in self._turn_order_from_active():
            if username in exempt_players:
                continue
            for name, copies in groups.get(username, {}).items():
                if len(copies) < 2:
                    continue
                kept = self._ask_which_legend_to_keep(username, name, copies)
                losers.extend(state for state in copies if state is not kept)
        return losers

    def _losing_players(self: "Game") -> list[str]:
        """Players a state-based action would remove right now.

        - **CR 704.5a** - 0 or less life.
        - **CR 704.5b** - tried to draw from an empty library since the last check.
        - **CR 704.5c** - "If a player has ten or more poison counters, that
          player loses the game." `Player.loses_to_poison` is the threshold; the
          Two-Headed Giant exception the rule names is not modelled.

        A player who can't lose the game (`why_cant_lose_the_game`) is left
        out of all three.
        """
        losing: list[str] = []
        for player in self.players:
            if not self.is_in_game(player.username) or not (
                player.life <= 0
                or player.tried_to_draw_from_empty_library
                or player.loses_to_poison
            ):
                continue
            if self.why_cant_lose_the_game(player.username) is not None:
                # CR 101.2: "can't lose the game" beats every CR 704.5a-c
                # loss. CR 704.5b counts only a draw "since the last time
                # state-based actions were checked", and this check has now
                # looked, so the failed draw is not held over to the check
                # after the effect ends; life and poison are state, and are.
                player.tried_to_draw_from_empty_library = False
                continue
            losing.append(player.username)
        return losing

    def _apply_lose_the_game_replacements(self: "Game", username: str) -> bool:
        """CR 614: raise `username`'s loss as a replaceable event (CR 104.3b/
        c/d/e), before it becomes real.

        Returns `True` when the loss still happens - nothing replaced it, so
        the caller should still call `_lose_the_game` - and `False` when a
        printed "if you would lose the game, instead ..." effect (Exquisite
        Archangel, Lich's Mirror) applied instead; that effect's own `apply`
        performs whatever it says (exile, a shuffle-and-draw, a new life
        total) as it runs, so there is nothing further for the caller to do
        beyond not removing the player.

        A no-op (still `True`) for a player already gone - the same guard
        `player_loses_the_game` already carries, needed here too now that
        both call sites share this one choke point.
        """
        if not self.is_in_game(username):
            return False
        player = self.player(username)
        event = ReplaceableEvent(kind=EventKind.LOSE_THE_GAME, player=player)
        apply_replacements(self, event)
        return not event.replaced

    def _lose_the_game(self: "Game", username: str) -> None:
        """This player loses, and so leaves the game (CR 104.5)."""
        if username not in self.losers:
            self.losers.append(username)
        self._player_left(username)

    def _player_left(self: "Game", username: str) -> None:
        """Clean up after a player who is no longer in the game (CR 800.4).

        CR 800.4a: everything they own leaves the game, and CR 800.4j has the
        turn carry on without them. Ownership is not modelled separately from
        control, so this reads their objects off `controller`.

        **CR 800.4n is the one exception**: "When a player leaves the game,
        objects that player owns in the ante zone do not leave the game." The
        ante zone is skipped entirely here for that reason.
        """
        assert self.turn is not None
        for zone, zone_cards in self.shared_zones.items():
            if zone is Zone.ANTE:
                continue  # CR 800.4n
            for state in list(zone_cards):
                if state.controller == username:
                    self.combat.remove(state.id)
                    zone_cards.remove(state)
        # CR 702.26k: "Phased-out permanents owned by a player who leaves the
        # game also leave the game."
        self.phased_out = [
            state
            for state in self.phased_out
            if (state.owner if state.owner is not None else state.controller) != username
        ]
        # CR 800.4d: a triggered ability that would be controlled by a player who
        # has left the game is never put on the stack.
        self.pending_triggers = [
            trigger for trigger in self.pending_triggers if trigger.controller != username
        ]
        self.turn.leave(username)
        if self.priority is not None:
            self.priority.leave(username)
        self._reassign_monarch_after_departure(username)

    def _check_for_a_winner(self: "Game") -> None:
        """The last player left in a two-or-more player game wins (CR 104.2a).

        Runs after every state-based-action check and after every concession.
        When a draw has emptied the game - every player still in it lost at the
        same check, CR 104.4a - there is nobody left to win, `winner` stays
        None, and the draw recorded by `check_state_based_actions` says the
        game is over.
        """
        remaining = self.players_in_game
        if len(remaining) == 1 and len(self.players) > 1:
            self.winner = remaining[0].username

    @property
    def step_grants_priority(self: "Game") -> bool:
        """Whether anybody receives priority in the step now in progress.

        `TurnMachine.grants_priority` answers for the *shape* of the step and is
        the whole answer for eleven of the twelve. The cleanup step is the one it
        cannot answer, because CR 514.3 only says "normally" and CR 514.3a's
        exception is about game state:

        CR 514.3a: "At this point, the game checks to see if any state-based
        actions would be performed and/or any triggered abilities are waiting to
        be put onto the stack (including those that trigger 'at the beginnin[g of
        the next cleanup step]')."

        So a cleanup step with something waiting in `pending_triggers` - or with
        an object already on the stack, which is that same trigger a moment later
        - is a cleanup step in which players do receive priority. An empty one is
        CR 514.3's ordinary case and grants none.

        `cleanup_owed` overrides that to False regardless of `pending_triggers`:
        CR 724.1c's own state-based check, run inside `end_the_turn` before the
        cleanup step's CR 514.1/514.2 turn-based actions have happened, can
        already have left something waiting there, but CR 724.1c/724.1f are
        explicit that "no player gets priority" until that debt is paid - see
        `_before_priority`, which is what pays it and then re-asks this same
        question with the debt cleared.
        """
        assert self.turn is not None
        if self.turn.step is Step.CLEANUP:
            if self.cleanup_owed:
                return False
            return bool(self.pending_triggers) or bool(self.stack)
        return self.turn.grants_priority

    def _skip_replaced_extra_turns(self: "Game") -> None:
        """CR 614.10: "If a player would begin an extra turn, that player skips
        that turn instead" (Ugin's Nexus). Each extra turn about to begin is
        offered to the replacement effects as `EventKind.BEGIN_EXTRA_TURN` and,
        if one replaced it, spent without being taken (CR 500.7: the most
        recently created turn comes first)."""
        assert self.turn is not None
        while (username := self.turn.pending_extra_turn()) is not None:
            event = apply_replacements(
                self,
                ReplaceableEvent(kind=EventKind.BEGIN_EXTRA_TURN, player=self.player(username)),
            )
            if event.happens:
                return
            self.turn.skip_pending_extra_turn()

    def skip_next_turns(self: "Game", username: str, count: int = 1) -> None:
        """`username` skips their next `count` turns (CR 614.10, CR 614.10a) -
        Ral Zarek, Guest Lecturer's own coin-flip "−7"."""
        assert self.turn is not None
        self.player(username)  # raises if unknown
        self.turn.skip_next_turns(username, count)

    def concede(self: "Game", username: str, by: str | None = None) -> None:
        """A player concedes and leaves the game immediately (CR 104.3a).

        Conceding is not a state-based action and does not wait for one: the
        player is gone at once, their objects go with them (CR 800.4a), and the
        last player standing wins (CR 104.2a).

        `by` is who is taking the action, and defaults to the player themselves.
        It exists for CR 723.6: "The controller of another player can't make
        that player concede. A player may concede the game at any time, even if
        they are controlled by another player." That is the one decision a
        player-controlling effect never reaches - CR 723.5 hands over every
        choice "the rules or any objects" call for, and conceding is neither.
        """
        self._refuse_if_over()
        with self._id_allocator_scope():
            self.player(username)  # raises if unknown
            if by is not None and by != username:
                raise ValueError(
                    f"{by} cannot make {username} concede, even while controlling them (CR 723.6)"
                )
            if username not in self.conceded:
                self.conceded.append(username)
            self._player_left(username)
            self._check_for_a_winner()

    def end_with_winner(self: "Game", username: str) -> None:
        self._refuse_if_over()
        self.player(username)  # raises if unknown
        self.winner = username

    def end_in_draw(self: "Game") -> None:
        """End this game as a draw, with no winner (CR 104.4a).

        The state-based-action path sets `drawn` itself when one check removes
        every player still in the game; this is the entry for a draw that does
        not come from a check - the mandatory-action loops of CR 104.4b are not
        modelled, and CR 104.4c's "an effect may state that the game is a draw"
        has no registry effect behind it, so a scenario stages one here.

        CR 104.5 sends a player the game is a draw for out of the game, and the
        game is a draw for everyone still in it, so they all leave and their
        objects go with them (CR 800.4a).
        """
        if self.is_over:
            raise ValueError("the game is already over")
        self.drawn = True
        for username in [player.username for player in self.players_in_game]:
            self._lose_the_game(username)

    def player_loses_the_game(self: "Game", username: str) -> None:
        """CR 104.3e: "An effect may state that a player loses the game."

        Applied immediately as the stating effect resolves, not deferred to a
        state-based-action sweep the way life-loss (CR 104.3b), an empty-library
        draw (CR 104.3c), and ten-or-more poison counters (CR 104.3d) all are -
        104.3e carries none of those three's "the next time a player would
        receive priority" wording. `end_in_draw`'s own CR 104.4c loss is the
        same shape: call `_lose_the_game` directly and check for a winner right
        away, rather than only setting a flag for a later check.

        A no-op for a player already gone - `_lose_the_game` is not idempotent
        about `_player_left`'s cleanup, and CR 104.3a already makes "losing
        stays gone" the rule (`check_state_based_actions`'s own docstring).

        CR 614: this loss is exactly as replaceable as the state-based ones -
        `_apply_lose_the_game_replacements` is the one choke point both this
        method and `_check_state_based_actions_impl` raise it through, so a
        card whose "if you would lose the game, instead ..." fires here too,
        never only against the three state-based losses.
        """
        if not self.is_in_game(username):
            return
        if self.why_cant_lose_the_game(username) is not None:
            return  # CR 101.2: the loss can't happen, so nothing replaces it
        if not self._apply_lose_the_game_replacements(username):
            return
        self._lose_the_game(username)
        self._check_for_a_winner()

    def player_wins_the_game(self: "Game", username: str) -> None:
        """CR 104.2b: "An effect may state that a player wins the game."

        Applied immediately as the stating effect resolves - Felidar
        Sovereign's own worked example (CR 104.2b's rules-text comment):
        "If that player has 40 or more life at this time, the ability
        resolves and that player wins the game", no state-based check
        deferred the way a losing effect's own CR 104.3b-d siblings are -
        the win-side twin of `player_loses_the_game`, built on the same
        `end_with_winner` a `Match` series already uses to record one.

        A no-op once the game is already over (`end_with_winner` itself
        raises there, CR 104.2a's own "this happens immediately" is not a
        race this wave models - nothing in the pool states two different
        winners from one resolution) or for a player who already left.
        """
        if not self.is_in_game(username) or self.is_over:
            return
        if self.why_cant_win_the_game(username) is not None:
            return  # CR 101.2 over CR 104.2b; only CR 104.2a overrides it
        self.end_with_winner(username)

    def why_cant_lose_the_game(self: "Game", username: str) -> str | None:
        """Why `username` can't lose the game right now, or None (CR 101.2).

        "You can't lose the game" stops every loss but a concession (CR
        104.3a, `concede`): CR 704.5a-c's state-based losses
        (`_losing_players`) and an effect saying the player loses (CR 104.3e,
        `player_loses_the_game`). Two sources, one sentence shape
        (`machines/layers/parse.read_cant_lose_cant_win`):

        - a permanent's static line (Platinum Angel, Herald of Eternal Dawn),
          read off its computed abilities so it applies only while the
          permanent is on the battlefield and still has it (CR 604.2, CR
          611.3a, CR 613 layer 6) and only for its current controller;
        - a resolved "this turn" form (Angel's Grace), recorded on
          `casting_rule_effects` (CR 611.2a) until CR 514.2 ends it.
        """
        return self._game_outcome_prohibition(username, lose=True)

    def why_cant_win_the_game(self: "Game", username: str) -> str | None:
        """Why `username` can't win the game right now, or None (CR 101.2):
        an opponent's "your opponents can't win the game", from the same two
        sources as `why_cant_lose_the_game`. It stops a win an effect states
        (CR 104.2b, `player_wins_the_game`); CR 104.2a's last-player-standing
        win "overrides all effects that would preclude that player from
        winning the game", so `_check_for_a_winner` never asks."""
        return self._game_outcome_prohibition(username, lose=False)

    def _game_outcome_prohibition(self: "Game", username: str, *, lose: bool) -> str | None:
        def applies(controller: str, you_cant_lose: bool, opponents_cant_win: bool) -> bool:
            if lose:
                return you_cant_lose and controller == username
            return opponents_cant_win and controller != username

        verb = "lose" if lose else "win"
        for effect in self.casting_rule_effects:
            if applies(
                effect.controller,
                effect.kind == CANT_LOSE_THE_GAME,
                effect.kind == OPPONENTS_CANT_WIN_THE_GAME,
            ):
                return (
                    f"{username} can't {verb} the game this turn: {effect.source_name} "
                    "says so (CR 101.2, CR 611.2a)"
                )
        # Asked only when a loss or a win is about to happen, so the whole
        # computed board is read: a granted line (an Equipment's quoted
        # ability) is as much the permanent's own as a printed one.
        for permanent in self.battlefield:
            characteristics = self.characteristics_of(permanent)
            controller = characteristics.controller or permanent.controller
            for line in characteristics.abilities:
                prohibition = read_cant_lose_cant_win(line)
                if prohibition is None or prohibition.this_turn:
                    continue
                if applies(controller, prohibition.you_cant_lose, prohibition.opponents_cant_win):
                    return (
                        f"{username} can't {verb} the game: {permanent.name} says so "
                        "(CR 101.2, CR 604.2)"
                    )
        return None

    def advance(self: "Game", username: str | None = None) -> Step:
        """Move to the next step (CR 500.1), as `username`'s own decision.

        `username` defaults to whoever is actually authorized right now (the
        active player, or their CR 723.5 controller) so a caller that is not
        testing the refusal itself does not have to look that player up.

        In the order CR 703.3, CR 704.3 and CR 603.3 set out: the step begins and
        anything that triggers "at the beginning of" it triggers (CR 500.6), its
        turn-based actions happen, state-based actions are checked, everything
        that has triggered goes on the stack, and only then does a player receive
        priority. The turn-based actions are run only when
        `automatic_turn_based_actions` is on - see that field.

        Nothing is put on the stack in the untap step, where no player receives
        priority (CR 502.4); CR 502.4's own second sentence holds those triggers
        over ("Any ability that triggers during this step will be held until the
        n[ext time a player would receive priority]"), which is what leaving
        them in `pending_triggers` does. A cleanup step holds them over too
        *unless* CR 514.3a's exception applies - see `step_grants_priority`.

        Two refusals, both raised before anything moves:

        - **CR 117.3a**: the active player is the one whose decision this is -
          or, under a CR 723.5 control effect, whoever is deciding for them.
          Anyone else is refused outright.
        - **CR 500.2 / CR 117.4 / CR 405.5**: a step or phase that grants
          priority (i.e. not one of CR 500.3's untap/cleanup exceptions -
          `step_grants_priority`) ends only once the stack is empty and every player has
          passed in succession. A non-empty stack means that has not happened
          yet, so advancing past it here would strand whatever is waiting -
          the caller must pass priority and let it resolve instead.
        """
        assert self.turn is not None
        self._refuse_if_over()
        if self.turn.in_pregame:
            # CR 500.1's steps are parts of a turn and no turn has begun yet, so
            # there is no step to advance and no active player whose decision it
            # would be. The pregame moves when its own sequence completes.
            raise ValueError(
                f"the game is still in its pregame ({self.turn.step}) - "
                f"CR 103.8's first turn has not begun. Settle CR 103.5's "
                f"mulligans and CR 103.6's opening-hand actions first"
            )

        decider = self.controller_of_player(self.turn.active_player)
        if username is None:
            username = decider
        if username != decider:
            raise ValueError(
                f"{username} may not advance the turn - only {decider} may, as "
                f"{self.turn.active_player}'s active-player decision (CR 117.3a, 723.5)"
            )
        if self.step_grants_priority and not self.stack_is_empty:
            raise ValueError(
                f"cannot advance past {self.turn.step} while the stack is "
                f"non-empty - pass priority instead (CR 500.2)"
            )

        with self._id_allocator_scope():
            return self._advance_past_checks()

    def _advance_past_checks(self: "Game") -> Step:
        """The rest of `advance`, run with `_allocate_id` installed.

        Split out only so `advance` can wrap it in `_id_allocator_scope` -
        see `objects_created`'s docstring for why that installation is scoped
        to this one call rather than done once for the object's whole life.
        """
        assert self.turn is not None
        previous_turns_taken = self.turn.turns_taken
        previous_active_player = self.turn.active_player
        previous_step = self.turn.step
        if (
            self.automatic_turn_based_actions
            and previous_step is Step.COMBAT_DAMAGE
            and self.combat.first_strike_damage_step
        ):
            # CR 510.4: queued before the pointer leaves the first-strike
            # step, so the second occurrence of `Step.COMBAT_DAMAGE` is what
            # `self.turn.advance()` walks into next rather than
            # `Step.END_OF_COMBAT`. Only the automatic path queues it - a
            # caller driving combat by hand uses `Game.combat_damage()`,
            # which stays the two-step helper and never sets this flag true
            # across an `advance()` boundary.
            self.turn.add_second_combat_damage_step()
        if previous_step is Step.CLEANUP and not self.turn.extra_phase_queue:
            self._skip_replaced_extra_turns()
        step = self.turn.advance()
        if step is Step.DRAW and (self.turn.skips_draw() or self.static_skips_draw_step()):
            # CR 103.8a skips the starting player's whole first draw step, and
            # CR 500.11: to skip a step "is to proceed past it as though it
            # didn't exist" - no beginning event, so no "at the beginning of
            # your draw step" trigger, no priority, nothing scheduled for it
            # (CR 614.10a). `draw_step` still checks too, for a caller that
            # walks the pointer into the step some other way.
            step = self.turn.advance()
        self._note_step_began(step)

        if self.automatic_turn_based_actions and previous_step is Step.DECLARE_ATTACKERS:
            # CR 508.8: "If no creatures are declared as attackers or put onto
            # the battlefield attacking, skip the declare blockers and combat
            # damage steps." A skipped step is one that never happens (CR
            # 500.11: "to skip a step ... is to proceed past it as though it
            # didn't exist"), so it gets no beginning event, no turn-based
            # actions, no priority round, and nothing scheduled for it happens
            # (CR 614.10a). Walking the pointer past them here, before either
            # begins, does that.
            #
            # The condition is what happened, not who is still in combat:
            # CR 508.8 keys off "declared as attackers or put onto the
            # battlefield attacking", so CR 506.4 removing an attacker after
            # the fact does not un-skip the combat. Both halves of that union
            # set `attacked_this_combat` - `combat.declare_attacker` for the
            # declaration, `models/token._put_onto_the_battlefield_attacking`
            # for Parhelion II's Angels and Ilharg's creature card, which
            # CR 508.4c says were never declared - so the flag is the whole of
            # it and asking `combat.attacks` here would be the wrong reading
            # anyway. Only the automatic path
            # skips: a caller driving combat by hand may have declared its
            # attackers in whatever way it likes, and its steps must be there
            # when it steps into them.
            while step in (Step.DECLARE_BLOCKERS, Step.COMBAT_DAMAGE) and (
                not self.combat.attacked_this_combat
            ):
                step = self.turn.advance()

        if previous_step is Step.END_OF_COMBAT:
            # CR 511.3: everything leaves combat as the end of combat step ends.
            self.end_of_combat()

        # CR 500.5: as the step that just ended ends, any unspent mana empties.
        # The pointer may have crossed several boundaries (the skip loop above,
        # or a cleanup that rolled into the next turn); nothing between them
        # can add mana, so one emptying covers every boundary crossed.
        #
        # CR 500.5a: firebending's "until end of combat" mana (`ManaRetentionScope
        # .END_OF_COMBAT`) expires "at the end of the combat phase, not at the
        # beginning of the end of combat step" - the same instant CR 511.3's
        # combat-clearing above fires, since both are keyed off leaving the
        # combat phase behind, which `previous_step is Step.END_OF_COMBAT`
        # already answers.
        self.empty_mana_pools(
            expiring=frozenset({ManaRetentionScope.END_OF_COMBAT})
            if previous_step is Step.END_OF_COMBAT
            else None
        )

        if self.turn.turns_taken != previous_turns_taken:
            # The turn that just ended is closed off first, while its own
            # per-turn fields still hold it: its life lost and gained into
            # the count ledger rolled below, the exile zone's residents as
            # the new turn's baseline (`machines/conditions/history.
            # end_turn`).
            from ...machines.conditions import history as condition_history

            condition_history.end_turn(self, previous_turns_taken, previous_active_player)
            # A new turn: land drops reset and the new active player gets
            # priority. `turns_taken` is the signal rather than the active seat
            # or the turn number, because an extra turn (CR 500.7) moves
            # neither: the same player can take two turns in a row.
            self.lands_played = {}
            self.extra_land_plays = {}  # Way of the Paradox's own "this turn" grant
            self.activations = {}  # CR 602.5b restrictions are per turn
            self.loyalty_activations = {}  # CR 606.3's once-per-turn is per turn too
            self.forecast_activations = set()  # CR 702.57b's once-per-turn is per turn too
            self.once_per_turn_triggers = {}  # CR 603.2h restrictions are per turn too
            self.once_per_turn_cast_permissions_used = {}  # "Once during each of your turns"
            # Snapshotted, not dropped: "last turn" is a question the
            # werewolves ask every upkeep (CR 603.4) and nothing else can
            # answer once this is cleared.
            self.spells_cast_last_turn = self.spells_cast_this_turn
            self.spells_cast_this_turn = {}
            self.previous_turn_active_player = previous_active_player
            self.permanents_left_battlefield_this_turn = {}
            self.lands_entered_this_turn = {}
            self.attacked_this_turn = set()
            self.attacked_players_this_turn = {}
            self.became_tapped_count_this_turn = {}
            self.permanents_sacrificed_this_turn = {}
            self.creatures_died_this_turn = 0
            self.noncombat_damage_to_players_this_turn = {}
            self.nontoken_creatures_died_under_control_this_turn = {}
            self.ability_resolutions_this_turn = {}
            self.cards_drawn_this_turn = {}
            self.cards_drawn_in_own_draw_step = {}
            self.cards_discarded_this_turn = {}
            self.life_gained_this_turn = set()
            self.life_gained_amount_this_turn = {}
            # Snapshotted the same way `spells_cast_last_turn` is: Command
            # the Stage's own "dealt noncombat damage last turn" needs it.
            self.turn_facts_last_turn = self.turn_facts
            self.turn_facts = {}
            self.turn_counts_last_turn = self.turn_counts
            self.turn_counts = {}
            condition_history.note_hand_sizes_at_turn_start(self)  # CR 500.1: the turn just began
            self.turn_history_last_turn = self.turn_history
            self.turn_history = []
            self.combat_damage_dealt_this_turn_by = set()
            self.combat_damage_to_players_this_turn = []
            self.counters_put_this_turn = []
            self.announce_batched_events()
            self.damage_dealt_this_turn = []
            self.graveyard_arrivals_this_turn = []
            self.graveyard_arrivals_announced = 0
            self.next_spell_free_cast_grants = []
            self.next_spell_keyword_grants = []
            self.spell_cost_reduction_grants = []
            # `play_permissions` is deliberately **not** cleared here. CR 514.2
            # ends an "until end of turn" effect in the cleanup step and
            # `cleanup_step` does exactly that; a game driven step by step may
            # never run one, and `PlayPermission.expired` - which compares
            # `turns_taken` - is what answers correctly in that case. Purging
            # here as well would replace that specific refusal ("that turn is
            # over") with the generic "nothing allows this", which is a worse
            # message for the same wrong move.
            self.end_of_combat()
            self.begin_turn_for(self.turn.active_player)
            self._sync_player_control()  # CR 723.1

        if step is Step.UPKEEP:
            # CR 702.30a's clock: control changes made before this upkeep
            # began are stamped against the count before it, then the count
            # moves on.
            self.note_control_changes()
            active = self.turn.active_player
            self.upkeeps_begun[active] = self.upkeeps_begun.get(active, 0) + 1

        # CR 500.6: "When a phase or step begins, any abilities that trigger 'at
        # the beginning of' that phase or step trigger."
        self.emit(
            GameEvent(
                event=TriggerEvent.BEGINNING_OF_STEP,
                step=step,
                player=self.turn.active_player,
            )
        )

        if self.automatic_turn_based_actions:
            self.turn_based_actions()  # CR 703.3, before state-based actions
            self.check_state_based_actions()  # CR 704.3, before anyone has priority

        # CR 603.3, before anyone has priority - and only where anyone does.
        # CR 502.4's second sentence is the untap half: "Any ability that
        # triggers during this step will be held until the n[ext time a player
        # would receive priority]", which is exactly leaving it in
        # `pending_triggers`. The cleanup half is CR 514.3a: a cleanup step with
        # something waiting *is* one where players receive priority, so the
        # waiting abilities go on the stack here rather than being held over.
        if self.step_grants_priority:
            self.put_triggers_on_stack()

        if self.priority is not None:
            self.priority.reset(self.turn.active_index)
        # CR 502.4 / CR 514.3: and then take it straight back off the ones that
        # grant nobody priority, so `priority_holder` says nobody rather than
        # naming a player who may not act.
        self.sync_priority_with_step()
        return step

    def _note_step_began(self: "Game", step: Step) -> None:
        """Per-step bookkeeping for a step that has just begun: a draw step
        starts `cards_drawn_in_own_draw_step` over (CR 500.8/501.1 can put
        more than one in a turn)."""
        if step is Step.DRAW:
            self.cards_drawn_in_own_draw_step = {}
        if step is Step.BEGINNING_OF_COMBAT and self.turn is not None:
            # CR 506.1: every combat phase begins with its beginning of combat
            # step, so counting that step counts combat phases - an
            # additional one (CR 500.8) included - for "it's the first combat
            # phase of the turn" (`machines/conditions/timing.py`).
            self.note_turn_count("combat_phases", self.turn.active_player)
        if step is Step.END_STEP:
            # "Until your next end step" (CR 611.2a's stated duration) ends
            # the moment the named player's end step begins - see
            # `PlayPermission.until_next_end_step_of`.
            self.play_permissions = [
                permission
                for permission in self.play_permissions
                if not permission.reached_next_end_step(self)
            ]

    def advance_to(self: "Game", step: Step) -> Step:
        """Move the turn marker forward through every boundary up to `step`.

        The full funnel is `advance`, which also performs what each *beginning*
        needs - beginning-of-step triggers, turn-based actions, state-based
        actions, priority. This one crosses boundaries only, and at each of
        them performs the step-end turn-based action CR 500.5 requires: mana
        pools empty as every crossed step ends. Raises if `step` has already
        passed this turn, exactly as `TurnMachine.advance_to` does.

        Refuses while the game is still in its pregame, for `advance`'s reason:
        the steps this walks are CR 500's, and CR 103.8's first turn has not
        begun. `TurnMachine.advance_to` will move the raw pointer through the
        pregame for a caller that genuinely wants only the pointer moved.
        """
        self._refuse_if_over()
        assert self.turn is not None
        if self.turn.in_pregame:
            raise ValueError(
                f"the game is still in its pregame ({self.turn.step}) - "
                f"CR 103.8's first turn has not begun. Settle CR 103.5's "
                f"mulligans and CR 103.6's opening-hand actions first"
            )
        if STEP_SEQUENCE.index(step) < STEP_SEQUENCE.index(self.turn.step):
            raise ValueError(f"{step} already passed this turn, currently at {self.turn.step}")
        while self.turn.step is not step:
            previous_step = self.turn.step
            self._note_step_began(self.turn.advance())
            # CR 500.5a, the same reading `_advance_past_checks` uses above:
            # firebending's "until end of combat" mana expires exactly when
            # the combat phase this boundary just left behind ends, and so do
            # "until end of combat" / "this combat" effects (CR 511.2).
            if previous_step is Step.END_OF_COMBAT:
                self.continuous_effects.end_the_combat(self)
            self.empty_mana_pools(
                expiring=frozenset({ManaRetentionScope.END_OF_COMBAT})
                if previous_step is Step.END_OF_COMBAT
                else None
            )
        self.sync_priority_with_step()  # CR 502.4, 514.3
        return self.turn.step


from ...machines.layers.parse import read_cant_lose_cant_win  # noqa: E402
from ...machines.turn_scoped_riders import (  # noqa: E402
    CANT_LOSE_THE_GAME,
    OPPONENTS_CANT_WIN_THE_GAME,
)
