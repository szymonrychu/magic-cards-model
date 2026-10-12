from collections.abc import Sequence
from typing import TYPE_CHECKING, Any
from uuid import UUID

from ...machines import combat as combat_rules
from ...machines import enlist
from ...machines.abilities import (
    TriggerEvent,
)
from ...machines.combat import (
    Attack,
)
from ...machines.decisions import (
    ask_attackers,
    ask_blockers,
)
from ...machines.exert_on_attack import offer_exert_as_it_attacks
from ...machines.triggers import (
    GameEvent,
)
from ...machines.turn import (
    Step,
)
from ..card_state import (
    CardState,
    TargetRef,
)
from ..zone import Zone
from ._common import Targetable

if TYPE_CHECKING:
    from . import Game


def attacked_with_type_facts(types: object, subtypes: object) -> list[str]:
    """The `turn_facts` keys a declared attacker records for the attacking
    player (CR 508.1) - "attacked_with_type:creature",
    "attacked_with_subtype:hero"."""
    return [f"attacked_with_type:{str(kind).lower()}" for kind in (types or ())] + [
        f"attacked_with_subtype:{str(word).lower()}" for word in (subtypes or ())
    ]


class CombatMixin:
    def declare_attackers_step(self: "Game") -> None:
        """The declare attackers step's turn-based action (CR 703.4i, 508.1).

        CR 508.1: "First, the active player declares attackers. This
        turn-based action doesn't use the stack." CR 508.1a: "The active player
        chooses which creatures that they control, if any, will attack." The
        question is put through `machines/decisions.py` like the mulligan
        declaration is, and an unscripted player declares nobody - "if any"
        makes that legal.

        The declaration is a single whole: `declare_attackers` refuses it if any
        creature in it may not attack, and puts the abilities that triggered on
        attackers being declared onto the stack once the whole attack is
        declared (CR 508.2b), before the priority round `advance` runs next (CR
        508.2: "Second, the active player gets priority").

        CR 508.8 then skips the rest of the combat phase when nobody was
        declared as attacking; `advance` handles that, so the step that began
        here always runs, and is the one combat step that never skips.
        """
        assert self.turn is not None
        # Master of Cruelties' own "assigns no combat damage this combat":
        # scoped to the combat that already used it up, cleared here as the
        # next one's attackers are about to be declared - the same boundary
        # `CardState.exerted`'s own docstring gives "next untap step".
        for permanent in self.battlefield:
            permanent.assigns_no_combat_damage_this_combat = False
        active = self.turn.active_player
        attacks = ask_attackers(
            self.decisions,
            active,
            prompt="declare attackers",
            default=self._required_attack_declaration(active),
        )
        resolved = self._resolve_declaration(attacks)
        if resolved:
            self.declare_attackers(resolved)
        else:
            self._refuse_unobeyed_attack_requirements(resolved)

    def declare_blockers_step(self: "Game") -> None:
        """The declare blockers step's turn-based action (CR 703.4j, 509.1).

        CR 509.1: "First, the defending player declares blockers. This
        turn-based action doesn't use the stack." CR 509.1a: "The defending
        player chooses which creatures they control, if any, will block." With
        more than one of them, CR 802.4: "each defending player in APNAP order
        declares blockers as the declare blockers step begins". Every attack
        names its defender, so the question goes to each player defending
        against at least one attack, in `_turn_order_from_active` order - CR
        101.4's APNAP order, which starts at the active player and so visits
        the defenders in the order the rule names.

        The declarations are judged as one whole (CR 509.1's declaration rules
        - which is what lets menace work at all) once every answer is in, and
        `declare_blockers` puts the block triggers on the stack before the
        priority round `advance` runs next (CR 509.2a: "Any abilities that
        triggered on blockers being declared ... are put onto the stack before
        the active player gets priority").
        """
        attackers_by_defender: dict[str, list[UUID]] = {}
        for attack in self.combat.attacks:
            defender = combat_rules.defending_player(self, attack.defender)
            attackers_by_defender.setdefault(defender, []).append(attack.attacker_id)

        blocks: list[tuple[CardState, CardState]] = []
        for username in self._turn_order_from_active():
            if username not in attackers_by_defender:
                continue
            blocks.extend(
                self._resolve_declaration(
                    ask_blockers(
                        self.decisions,
                        username,
                        prompt="declare blockers",
                        attackers=tuple(attackers_by_defender[username]),
                        default=combat_rules.required_block_declaration(self, username),
                    )
                )
            )
        # CR 509.1's turn-based action runs whether or not anybody blocks -
        # "which creatures, if any, will block" - so `declare_blockers` is
        # called unconditionally. Skipping it when `blocks` is empty left
        # `Combat.blockers_declared` False on every fully unblocked attack,
        # which read as "blockers have not been declared yet" to any
        # unblocked-creature check (CR 509.1h) run afterward, such as
        # sneak's and ninjutsu's own availability.
        self.declare_blockers(blocks)

    def _sneak_defender_of(self: "Game", spell: CardState) -> "TargetRef | None":
        """CR 702.190b: "A permanent spell whose sneak cost was paid enters the
        battlefield tapped and attacking (see rule 506.3a). It will be
        attacking the same player, planeswalker, or battle as the creature
        that was returned to its owner's hand to pay the sneak cost."

        The defender that creature had, off the spell's `CastRecord`, or
        `None` when the sneak cost was not paid. CR 506.3a and CR 508.4a's
        exemptions (a noncreature permanent, a defender no longer there) are
        `models/token._put_onto_the_battlefield_attacking`'s, the same
        primitive ninjutsu (CR 702.49c) enters attacking through.
        """
        record = self.cast_record_of(spell)
        if record is None or not record.keyword_cost_paid:
            return None
        return record.sneak_defender

    def _defending_player_of(self: "Game", ability: Any) -> str | None:
        """CR 508.5's defending player for a triggered ability whose event is
        an attack: the player the attacker attacks, or the controller or
        protector of the planeswalker or battle it attacks
        (`combat.defending_player`, off `GameEvent.defender`). `None` for any
        other ability - its "defending player" restriction stays unbound."""
        from ...machines.combat import defending_player

        event = getattr(ability, "event", None)
        defender = getattr(event, "defender", None)
        if defender is None:
            return None
        return defending_player(self, defender)

    # -- combat ------------------------------------------------------------

    def attack_target(self: "Game", defender: "Targetable | str") -> TargetRef:
        """Read an attack target out of a player, a username, or a permanent."""
        return TargetRef.coerce(defender)

    def can_attack(self: "Game", creature: CardState, defender: "Targetable | str") -> bool:
        """Whether this creature could be declared attacking that (CR 508.1a)."""
        return combat_rules.attack_refusal(self, creature, self.attack_target(defender)) is None

    def why_cannot_attack(
        self: "Game", creature: CardState, defender: "Targetable | str"
    ) -> str | None:
        """The reason a declaration would be refused, for a scenario to assert on."""
        return combat_rules.attack_refusal(self, creature, self.attack_target(defender))

    def declare_attacker(
        self: "Game",
        creature: CardState,
        defender: "Targetable | str",
        attack_cost_sources: "Sequence[CardState] | None" = None,
        *,
        enlisting: CardState | None = None,
    ) -> Attack:
        """Declare one attacker (CR 508.1). Taps it unless it has vigilance.

        The attack triggers whatever watches for it, but nothing goes on the
        stack here: CR 508.2b puts the abilities that triggered on attackers
        being declared onto the stack "before the active player gets priority",
        and no player receives priority between one declaration and the next.
        `declare_attackers` opens that window once the whole attack is declared.

        A single call registers and emits together, correct for the only
        case a lone call to this method can mean: this creature really is the
        whole attacking party. `declare_attackers` (CR 508.1a's "all at
        once") does not call this - registering and emitting a whole batch
        one creature at a time here would settle "alone" (CR 506.5/506.6)
        off however many attackers happened to be registered *so far*, which
        is wrong for every attacker but the last; see its own docstring.
        """
        self._refuse_if_over()
        with self._id_allocator_scope():
            refusal = combat_rules.attack_refusal(self, creature, self.attack_target(defender))
            if refusal is not None:
                raise ValueError(refusal)
            if enlisting is not None:
                enlist_refusal = enlist.enlist_refusal(self, creature, enlisting, set())
                if enlist_refusal is not None:
                    raise ValueError(enlist_refusal)
            returned = self._pay_attack_costs([(creature, defender)], attack_cost_sources)
            attack = combat_rules.declare_attacker(self, creature, self.attack_target(defender))
            self._return_attack_cost_permanents(returned)
            if enlisting is not None:
                # CR 508.1g's optional cost, chosen alongside this one
                # attacker's own declaration.
                enlist.apply_enlist(self, creature, enlisting)
            self._emit_attacks(creature, attack)
        return attack

    def _refuse_unobeyed_attack_requirements(
        self: "Game", attacks: "Sequence[tuple[CardState, Targetable | str]]"
    ) -> None:
        """CR 508.1d: "If the number of requirements that are being obeyed is
        fewer than the maximum possible number of requirements that could be
        obeyed without disobeying any restrictions, the declaration of
        attackers is illegal." Checked on the whole declaration, before any
        creature is declared, so a refused one taps nothing."""
        unobeyed = combat_rules.unobeyed_attack_requirement(
            self, {creature.id: self.attack_target(defender) for creature, defender in attacks}
        )
        if unobeyed is not None:
            raise ValueError(f"{unobeyed.reason} (CR 508.1d)")

    def _refuse_illegal_attacker_caps(
        self: "Game", attacks: "Sequence[tuple[CardState, Targetable | str]]"
    ) -> None:
        """CR 508.1c: a defending planeswalker (or battle) carrying "no more
        than one creature can attack this `<subject>` each combat" - Tomik,
        Orzhov Lawmage's own granted restriction, and The Eternal Wanderer's
        identically-shaped self-printed one - refuses the whole declaration
        the moment a second attacker is aimed at it.

        Per defender, not per creature: `attack_refusal` judges each attacker
        against restrictions on *itself*, but this restriction is a fact
        about who it is attacking, so it can only be judged once the whole
        party's defenders are known - the same reason `_refuse_unobeyed_
        attack_requirements` reads the whole declaration rather than one
        attacker at a time.
        """
        by_defender: dict[UUID, list[CardState]] = {}
        for creature, defender in attacks:
            ref = self.attack_target(defender)
            if ref.card_id is None:
                continue
            by_defender.setdefault(ref.card_id, []).append(creature)
        for card_id, attackers in by_defender.items():
            if len(attackers) < 2:
                continue
            permanent = self.find_by_id(card_id)
            if not isinstance(permanent, CardState):
                continue
            restriction = combat_rules.attacker_cap_restriction(permanent, self)
            if restriction is not None:
                names = ", ".join(creature.name for creature in attackers)
                raise ValueError(
                    f"{permanent.name} allows no more than one creature to attack it each "
                    f'combat (CR 508.1c: "{restriction}"), but {names} were all declared '
                    "against it"
                )

    def _refuse_attack_alone_violations(
        self: "Game", attacks: "Sequence[tuple[CardState, Targetable | str]]"
    ) -> None:
        """CR 508.1c/CR 506.5: a creature whose own text says it "can only
        attack alone" (Master of Cruelties) is a restriction that it can't
        attack unless it "attacks alone" - the only creature declared as an
        attacker this combat. Judged on the whole declaration, the same
        reason `_refuse_illegal_attacker_caps` is: whether a creature is
        attacking alone is a fact about every creature declared, not about
        any one of them by itself.
        """
        if len(attacks) < 2:
            return
        for creature, _defender in attacks:
            restriction = combat_rules.self_attack_alone_only_sentence(creature, self)
            if restriction is not None:
                others = ", ".join(other.name for other, _ in attacks if other.id != creature.id)
                raise ValueError(
                    f'{creature.name} can\'t attack: "{restriction}" (CR 508.1c, CR 506.5), '
                    f"but {others} were also declared as attackers"
                )

    def _refuse_extra_attack_restrictions(
        self: "Game", attacks: "Sequence[tuple[CardState, Targetable | str]]"
    ) -> None:
        """CR 508.1c: restrictions that judge the whole attack declaration
        ("can't attack alone", "can't attack unless a creature with greater
        power also attacks") - `combat_statics.extra_attack_declaration_refusal`."""
        from ...machines.combat_statics import extra_attack_declaration_refusal

        refs = [(creature, self.attack_target(defender)) for creature, defender in attacks]
        refusal = extra_attack_declaration_refusal(self, refs)
        if refusal is not None:
            raise ValueError(refusal)

    def _required_attack_declaration(self: "Game", active: str) -> list[tuple[UUID, UUID | str]]:
        """The fewest attackers that obey every requirement that can be obeyed
        (CR 508.1d), each attacking the defender that obeys the most of its
        requirements (a goaded creature: a player other than its goader when
        one exists), ties going to an opponent in turn order, else a
        planeswalker or battle - what an unscripted seat declares instead of
        nobody."""
        declaration: list[tuple[UUID, UUID | str]] = []
        for creature in combat_rules.attack_requirement_holders(self, active):
            defender, _obeyed = combat_rules.most_obedient_attack(self, creature)
            if defender is None:
                continue
            target: UUID | str | None = (
                defender.username if defender.is_player else defender.card_id
            )
            if target is not None:
                declaration.append((creature.id, target))
        return declaration

    def declare_attackers(
        self: "Game",
        attacks: list[tuple[CardState, "Targetable | str"]],
        attack_cost_sources: "Sequence[CardState] | None" = None,
        *,
        enlist_choices: "dict[UUID, CardState] | None" = None,
    ) -> None:
        """Declare a whole attack at once, in order (CR 508.1, 508.2b).

        CR 508.1a: "the active player... declares [attackers]. This is done
        all at once". Registration (tapping, adding to `self.combat.attacks`)
        happens for every attacker first, in declaration order; only once the
        whole party is known does anything emit its own `ATTACKS` event, so
        `attacking_alone`/`attacking_player_alone` (CR 506.5/506.6) are read
        off the finished declaration for every attacker, not a partial one -
        see `_emit_attacks`'s own docstring.

        `enlist_choices` is CR 508.1g's own optional cost (CR 702.154a-c): a
        map from an attacking creature's id to the creature it enlists,
        keyed the same way `attack_cost_sources` names *which* mana sources
        pay CR 508.1h's cost rather than leaving that to be solved for.
        """
        self._refuse_if_over()
        with self._id_allocator_scope():
            self._refuse_unobeyed_attack_requirements(attacks)
            self._refuse_illegal_attacker_caps(attacks)
            self._refuse_attack_alone_violations(attacks)
            self._refuse_extra_attack_restrictions(attacks)
            # CR 508.1: an illegal declaration returns the game to the moment
            # before it, so every attacker is judged before any one taps.
            # CR 508.1a-b: each chosen creature attacks one player,
            # planeswalker, or battle, so naming one twice is illegal.
            seen: set[UUID] = set()
            for creature, _defender in attacks:
                if creature.id in seen:
                    raise ValueError(
                        f"{creature.name} is declared as an attacker more than once "
                        "(CR 508.1a, 508.1b)"
                    )
                seen.add(creature.id)
            for creature, defender in attacks:
                refusal = combat_rules.attack_refusal(self, creature, self.attack_target(defender))
                if refusal is not None:
                    raise ValueError(refusal)
            attacking_ids = {creature.id for creature, _defender in attacks}
            if enlist_choices:
                by_id = {creature.id: creature for creature, _defender in attacks}
                for creature_id, enlisted in enlist_choices.items():
                    attacker = by_id.get(creature_id)
                    if attacker is None:
                        raise ValueError(
                            f"{creature_id} is not one of the creatures being declared "
                            "as an attacker (CR 508.1g)"
                        )
                    enlist_refusal = enlist.enlist_refusal(self, attacker, enlisted, attacking_ids)
                    if enlist_refusal is not None:
                        raise ValueError(enlist_refusal)
            # CR 508.1h-j: the whole declaration's cost to attack, paid in
            # full before anyone becomes an attacking creature (CR 508.1k).
            returned = self._pay_attack_costs(attacks, attack_cost_sources)
            registered = [
                (
                    creature,
                    combat_rules.declare_attacker(self, creature, self.attack_target(defender)),
                )
                for creature, defender in attacks
            ]
            # The permanents returned to pay (Floodtide Serpent) go once every
            # attacker is registered, so the restriction they pay for is not
            # re-judged against a cost that has just been paid.
            self._return_attack_cost_permanents(returned)
            if enlist_choices:
                for creature, _attack in registered:
                    enlisted = enlist_choices.get(creature.id)
                    if enlisted is not None:
                        enlist.apply_enlist(self, creature, enlisted)
            for creature, _attack in registered:
                # CR 508.1g / CR 701.43d: "You may exert [this creature] as it
                # attacks" is an optional cost chosen with the declaration.
                offer_exert_as_it_attacks(self, creature)
            for creature, attack in registered:
                self._emit_attacks(creature, attack)
                # A per-turn historical fact, not `machines.combat.Combat`'s
                # live attacking status - Hexhaven Dueling Arena's "target
                # creature that attacked this turn" still needs an answer
                # after this combat (and this turn's whole combat phase) is
                # over. Cleared at the same new-turn reset as the rest of
                # `Game`'s "this turn" fields.
                self.attacked_this_turn.add(creature.id)
                # The same per-object historical fact as `attacked_this_turn`
                # above, but naming *whom* - Angel of Destiny's own "each
                # player this creature attacked this turn loses the game."
                # CR 508.5's defending player, resolved right away rather than
                # re-derived later: `defending_player` needs `attack.defender`
                # still resolvable, and a battle's protector (CR 310.9d) can
                # change once combat is over.
                # "Each opponent who attacked you or a planeswalker you
                # control this turn" (Sandswirl Wanderglyph).
                note_attacked(self, self.active_player.username, attack.defender)
                defender_username = combat_rules.defending_player(self, attack.defender)
                if defender_username is not None:
                    self.attacked_players_this_turn.setdefault(creature.id, set()).add(
                        defender_username
                    )
                # "you attacked with a Hero this turn" (Avengers Assemble!) -
                # the attacker's types as declared (CR 508.1).
                chars = self.characteristics_of(creature)
                for fact in attacked_with_type_facts(chars.types, chars.subtypes):
                    self.record_turn_fact(fact, self.active_player.username)
                    # The counting twin of the fact just above - Deepway
                    # Navigator's own "As long as you attacked with three or
                    # more Merfolk this turn, Merfolk you control get
                    # +1/+0.", which asks "how many", not "did you"
                    # (`turn_facts`' own docstring).
                    self.note_turn_count(fact, self.active_player.username)
            if attacks:
                # CR 508.1: declaring attackers is how a player attacks -
                # "you attacked this turn" (Kaito Shizuki) asks this.
                self.record_turn_fact("attacked", self.active_player.username)
                # CR 508.3d: "An ability that reads 'Whenever [a player]
                # attacks, . . .' triggers if one or more creatures that
                # player controls are declared as attackers" - once for the
                # whole declaration, not once per attacker, so this is its own
                # subject-less event alongside each creature's own ATTACKS
                # event above. Its `amount` is how many were declared -
                # the "that many" a batched attack trigger reads (Screaming
                # Swarm's "mills that many cards").
                self.emit(
                    GameEvent(
                        event=TriggerEvent.ATTACKS,
                        player=self.active_player.username,
                        amount=len(attacks),
                    )
                )
            self.put_triggers_on_stack()

    def can_block(self: "Game", blocker: CardState, attacker: CardState) -> bool:
        """Whether this creature could block that attacker on its own (CR 509.1a).

        Restrictions that only make sense against the finished declaration -
        menace - are checked by `declare_blockers`, not here.
        """
        return self.why_cannot_block(blocker, attacker) is None

    def why_cannot_block(self: "Game", blocker: CardState, attacker: CardState) -> str | None:
        attack = self.combat.attack_by(attacker.id)
        if attack is None:
            return f"{attacker.name} is not attacking"
        return combat_rules.block_refusal(self, blocker, attack)

    def declare_blockers(self: "Game", blocks: list[tuple[CardState, CardState]]) -> None:
        """Declare the blocks for this combat as one legal declaration (CR 509.1).

        `blocks` is `(blocker, attacker)` pairs, in the order damage should be
        assigned through them (CR 510.1c).

        Once the declaration is legal, each blocking pair is an event: the
        blocker blocked and the attacker became blocked (CR 509.1a), and both
        halves are what an Ashmouth Hound reads. A pair only ever triggers once
        per combat, so re-declaring a block that was already declared does not
        fire it again.
        """
        self._refuse_if_over()
        with self._id_allocator_scope():
            combat_rules.declare_blockers(self, blocks)

            for attack in self.combat.attacks:
                attacker = self.find_by_id(attack.attacker_id)
                for blocker_id in attack.blockers:
                    blocker = self.find_by_id(blocker_id)
                    if attacker is None or blocker is None:
                        continue
                    pair = f"{blocker_id}:{attack.attacker_id}"
                    if pair in self.blocks_triggered:
                        continue
                    self.blocks_triggered.append(pair)
                    self._emit_blocks(blocker, attacker)

            # CR 508.3f/509.3g: "Whenever [a creature] attacks and isn't
            # blocked, ..." - a separate event from `TriggerEvent.ATTACKS`,
            # fired here (the declare blockers step, once this declaration
            # is legal) rather than at `declare_attackers` time, since
            # "isn't blocked" is not knowable until now. CR 509.3g: "It will
            # trigger even if the creature was never declared as an
            # attacker" - `self.combat.attacks` already includes a creature
            # put onto the battlefield attacking (CR 508.4) the same way it
            # includes a declared one, so no separate case is needed for
            # that. CR 509.1h: a creature "stays blocked" even once its
            # blockers are removed, so `attack.blocked` (not "has blockers
            # right now") is the read this asks.
            for attack in self.combat.attacks:
                if attack.blocked or attack.attacker_id in self.attacks_unblocked_triggered:
                    continue
                attacker = self.find_by_id(attack.attacker_id)
                if attacker is None:
                    continue
                self.attacks_unblocked_triggered.append(attack.attacker_id)
                attacker_chars = self.characteristics_of(attacker)
                defender_controller = combat_rules.defending_player(self, attack.defender)
                self.emit(
                    GameEvent(
                        event=TriggerEvent.ATTACKS_UNBLOCKED,
                        subject_id=attacker.id,
                        subject_name=attacker.name,
                        subject_controller=self.controller_of(attacker).username,
                        subject_card=attacker.card,
                        subject_types=attacker_chars.types,
                        subject_subtypes=attacker_chars.subtypes,
                        defender=attack.defender,
                        defender_controller=defender_controller,
                    )
                )
            self.put_triggers_on_stack()

    def block_by_effect(self: "Game", blocker: CardState, attacker: CardState) -> None:
        """A resolving effect makes `blocker` block `attacker` - not a
        declaration, so no CR 509.1b/509.1c check (`CombatMachine.add_blocker`).

        CR 509.3b/509.3d: "Whenever [a creature] blocks a creature" and
        "becomes blocked by a creature" trigger when an effect causes the
        block, "but only if it wasn't already blocking that attacking creature
        at that time" - so the pair fires here even when it was declared (and
        so fired) earlier this combat, once it had since stopped blocking.
        """
        attack = self.combat.attack_by(attacker.id)
        if attack is None:
            return
        already_blocking = blocker.id in attack.blockers
        self.combat.add_blocker(blocker.id, attacker.id)
        if already_blocking:
            return
        pair = f"{blocker.id}:{attacker.id}"
        if pair not in self.blocks_triggered:
            self.blocks_triggered.append(pair)
        self._emit_blocks(blocker, attacker)

    def attacking_creatures(self: "Game") -> list[CardState]:
        found = (self.find_by_id(card_id) for card_id in self.combat.attacker_ids)
        return [state for state in found if state is not None]

    def blocking_creatures(self: "Game") -> list[CardState]:
        found = (self.find_by_id(card_id) for card_id in self.combat.blocker_ids)
        return [state for state in found if state is not None]

    def is_attacking(self: "Game", creature: CardState) -> bool:
        return self.combat.attack_by(creature.id) is not None

    def is_blocking(self: "Game", creature: CardState) -> bool:
        return self.combat.attack_blocked_by(creature.id) is not None

    def is_blocked(self: "Game", creature: CardState) -> bool:
        """A creature stays blocked even once its blockers are gone (CR 509.1h)."""
        attack = self.combat.attack_by(creature.id)
        return attack is not None and attack.blocked

    @property
    def needs_first_strike_damage_step(self: "Game") -> bool:
        """Whether combat takes two damage steps rather than one (CR 510.4)."""
        return combat_rules.needs_first_strike_step(self)

    @property
    def is_first_strike_damage_step(self: "Game") -> bool:
        """Whether the game is paused in CR 510.4's first-strike damage step.

        CR 510.4: "If at least one attacking or blocking creature has first
        strike ... or double strike ... as the combat damage step begins, the
        only creatures that assign combat damage in that step are those with
        first strike or double strike. After that step, instead of proceeding
        to the end of combat step, the phase gets a second combat damage
        step." CR 506.1: "There are two combat damage steps if any attacking
        or blocking creature has first strike ... or double strike."

        Both occurrences of the combat phase are the same `Step.COMBAT_DAMAGE`
        (there is no separate `Step` for the first-strike one - see
        `machines/turn.py`'s `TurnMachine.add_second_combat_damage_step`), so
        this - `turn.step` plus `combat.first_strike_damage_step`'s own
        per-occurrence flag - is the read that tells them apart. This is the
        read `magic_cards_model_api` consumes to show which of the two a
        paused game is sitting in.
        """
        return (
            self.turn is not None
            and self.turn.step is Step.COMBAT_DAMAGE
            and self.combat.first_strike_damage_step
        )

    def combat_damage_step(self: "Game") -> list[tuple[Targetable, int]]:
        """Run one combat damage step, returning what was assigned (CR 510).

        The flag marks every `deal_damage` inside the step as combat damage
        (CR 510.2), which is what a prevention effect limited to combat damage
        needs to know.
        """
        self._dealing_combat_damage = True
        self._combat_damage_this_step = {}
        try:
            return combat_rules.combat_damage_step(self)
        finally:
            self._dealing_combat_damage = False
            self._combat_damage_this_step = None

    def combat_damage_marked_this_step(self: "Game", permanent: CardState) -> int:
        """Damage marked on `permanent` so far in the combat damage step being
        dealt right now (CR 510.2) - 0 outside one."""
        ledger = self._combat_damage_this_step
        return 0 if ledger is None else ledger.get(permanent.id, 0)

    def combat_damage(self: "Game") -> list[tuple[Targetable, int]]:
        """Run every combat damage step this combat needs (CR 510.1, 510.4).

        One step normally; two when anything in combat has first strike or
        double strike, with state-based actions between them - which is what
        stops a creature killed by first strike from striking back.

        The manual-path helper for a scenario driving combat by hand: it runs
        both steps back to back with no priority round between them, unlike
        the automatic path (`turn_based_actions`/`_advance_past_checks`),
        which runs one `combat_damage_step()` per occurrence of
        `Step.COMBAT_DAMAGE` and gives CR 510.3's priority round its own turn
        in between. `combat.first_strike_damage_step` ends up False either
        way once this returns - the second `combat_damage_step()` call sets
        it, the same as it does on the automatic path's second occurrence.
        """
        assigned = self.combat_damage_step()
        if self.combat.first_strike_step_happened and self.combat.damage_steps_done < 2:
            assigned = assigned + self.combat_damage_step()
        return assigned

    def end_of_combat(self: "Game") -> None:
        """Everything is removed from combat as the step ends (CR 511.3), and
        "until end of combat" / "this combat" effects end with the phase (CR
        500.5a, CR 511.2)."""
        self.continuous_effects.end_the_combat(self)
        self.combat.clear()
        self.blocks_triggered = []
        self.attacks_unblocked_triggered = []

    # -- CR 722: preparation cards -----------------------------------------

    def goad(self: "Game", creature: CardState, goader: str) -> None:
        """CR 701.15a: `goader` (the controller of the goading spell or
        ability) goads `creature` until `goader`'s next turn. CR 701.15d: "Once
        a player has goaded a creature, the same player goading it again has
        no effect" - a repeat is a no-op, so it adds no requirement. Only a
        permanent can carry the designation (CR 701.15b)."""
        if creature.zone is not Zone.BATTLEFIELD or goader in creature.goaded_by:
            return
        creature.goaded_by.append(goader)


from ...machines.opponent_attack_restrictions import note_attacked  # noqa: E402
