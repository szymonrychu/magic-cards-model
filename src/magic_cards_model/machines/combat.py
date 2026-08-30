"""Combat, as a state machine (CR 506-511).

The turn machine already walks through the five combat steps; this is what
happens inside them. Three turn-based actions do the work, none of which use
the stack:

- **Declare attackers** (CR 508.1). The active player picks untapped creatures
  they control that are not summoning sick, and says what each one is attacking.
  Attacking taps them (CR 508.1f) unless they have vigilance (CR 702.20b).
- **Declare blockers** (CR 509.1). The defending player picks untapped creatures
  they control and says which attacker each one blocks. The declaration is
  legal or illegal as a whole, which is what lets menace work at all.
- **Combat damage** (CR 510). Everything assigns at once (CR 510.2), so the
  whole assignment is computed against the pre-damage board and only then dealt.
  First strike and double strike split this into two steps (CR 510.4).

The engine has no layers yet, so a creature's keywords are read straight off the
printing's Scryfall `keywords` field. That is real card data rather than a
hand-written table, but it means a keyword granted by another permanent or a
spell is invisible here.

There is no damage assignment order sub-step in the current rules: after
CR 509.1 declares the blockers, CR 509.2a puts the triggers on the stack and
the active player gets priority - nothing in between orders the blockers.
CR 510.1c instead governs how a blocked creature divides its damage among the
creatures blocking it, so the order blockers were declared in is the order
damage walks through here - `declare_blockers` takes them in that order.
"""

from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from pydantic import BaseModel, Field

from ..models.card import Type
from ..models.card_state import CardState, TargetRef
from ..models.zone import Zone
from .abilities import TriggerEvent, keywords_in_lines
from .triggers import GameEvent

#: What a creature may attack besides a player (CR 306.6, 310.5).
ATTACKABLE_PERMANENT_TYPES = frozenset({Type.PLANESWALKER, Type.BATTLE})

if TYPE_CHECKING:  # pragma: no cover - import cycle: Game builds on the machines
    from ..models.game import Game, Targetable


class Keyword(StrEnum):
    """The keyword abilities combat cares about, as Scryfall spells them.

    Scryfall's `keywords` field is title case ("First strike"), so every lookup
    goes through `has_keyword`, which compares case-insensitively.
    """

    FLYING = "flying"
    REACH = "reach"
    TRAMPLE = "trample"
    MENACE = "menace"
    HASTE = "haste"
    VIGILANCE = "vigilance"
    FIRST_STRIKE = "first strike"
    DOUBLE_STRIKE = "double strike"
    #: CR 702.3a-b: "Defender is a static ability. A creature with defender
    #: can't attack."
    DEFENDER = "defender"
    #: CR 702.2a-c: a static ability that changes what counts as lethal damage
    #: when this creature assigns it, and adds a state-based action (CR 704.5h).
    DEATHTOUCH = "deathtouch"
    #: CR 702.15b: damage dealt by a source with lifelink makes its controller
    #: gain that much life, in addition to the damage's other results.
    LIFELINK = "lifelink"
    #: CR 702.14a-c: the five basic landwalks. Landwalk is an evasion ability
    #: (CR 702.14b) whose name carries the land type it looks for, so the
    #: members are spelled out rather than derived.
    PLAINSWALK = "plainswalk"
    ISLANDWALK = "islandwalk"
    SWAMPWALK = "swampwalk"
    MOUNTAINWALK = "mountainwalk"
    FORESTWALK = "forestwalk"


#: Which land type each landwalk ability looks for (CR 702.14a, CR 305.6).
LANDWALK_TYPES: dict[Keyword, str] = {
    Keyword.PLAINSWALK: "Plains",
    Keyword.ISLANDWALK: "Island",
    Keyword.SWAMPWALK: "Swamp",
    Keyword.MOUNTAINWALK: "Mountain",
    Keyword.FORESTWALK: "Forest",
}


def has_keyword(state: CardState, keyword: Keyword | str, game: "Game | None" = None) -> bool:
    """True if this permanent has the keyword right now (CR 702, CR 613.5).

    With a game, the answer comes off the computed board: CR 613.5 says "the
    application of continuous effects as described by the layer system is
    continually and automatically performed by the game", so a keyword taken
    away in layer 6 is gone and one granted there is there. Humility and Dress
    Down are the cards in the pool that make the difference visible.

    Without a game there is no board to compute, so the printing's own Scryfall
    `keywords` field is the answer - which is what every caller used before and
    is still right for a permanent nothing is affecting.
    """
    wanted = str(keyword).lower()
    computed = _computed_keywords(state, game, wanted)
    if computed is not None:
        return wanted in computed
    # `state.keywords`, not `state.card.keywords`: a face-down permanent has no
    # text at all (CR 702.37c, CR 708.2), so it has none of the printing's
    # keywords however plainly the card says them.
    return any(printed.lower() == wanted for printed in state.keywords)


def _computed_keywords(state: CardState, game: "Game | None", *wanted: str) -> set[str] | None:
    """The keywords the layer system leaves this permanent with, or None.

    None means there is nothing to compute against - no game, or a card that is
    not a permanent, since CR 613 applies to objects on the battlefield and a
    card in a hand has only what is printed on it.

    `keywords_in_lines` has no keyword table of its own: the caller says which
    keywords it cares about. This module's own `Keyword` list is the combat
    vocabulary, and `wanted` adds whatever else is being asked about - CR 702.12a's
    indestructible is a static ability that changes no combat rule and is still a
    keyword a caller may need read off the computed board (CR 613.5).
    """
    if game is None or state.zone is not Zone.BATTLEFIELD:
        return None
    characteristics = game.characteristics_of(state)
    if characteristics is None:
        return None
    vocabulary = [keyword.value for keyword in Keyword] + [word for word in wanted if word]
    return keywords_in_lines(list(characteristics.abilities), vocabulary)


class Attack(BaseModel):
    """One attacking creature and what it is attacking (CR 508.1).

    `blockers` is in declaration order, which is the order combat damage is
    assigned through (CR 510.1c). `blocked` stays true once blockers have been
    declared for it even if every blocker later leaves combat (CR 509.1h) -
    which is exactly why such an attacker deals no damage at all.
    """

    attacker_id: UUID
    defender: TargetRef
    blockers: list[UUID] = Field(default_factory=list)
    blocked: bool = False


class CombatMachine(BaseModel):
    """Who is attacking whom, who is blocking, and how much damage is done.

    Everything is held by id rather than by object, so the combat state is one
    serializable record next to the battlefield rather than a second copy of it.
    """

    attacks: list[Attack] = Field(default_factory=list)
    blockers_declared: bool = False
    damage_steps_done: int = 0
    first_strike_step_happened: bool = False
    attacked_this_combat: bool = False
    """Whether anybody was declared as an attacker this combat (CR 508.8).

    CR 508.8 keys off the declaration - "If no creatures are declared as
    attackers or put onto the battlefield attacking" - not off who is still in
    combat, so CR 506.4's `remove` takes an attacker out without un-setting
    this: the declaration happened. Only `clear` resets it, at the end of
    combat (CR 511.3).
    """

    @property
    def attacker_ids(self) -> list[UUID]:
        return [attack.attacker_id for attack in self.attacks]

    @property
    def blocker_ids(self) -> list[UUID]:
        return [blocker for attack in self.attacks for blocker in attack.blockers]

    @property
    def is_active(self) -> bool:
        return bool(self.attacks)

    def attack_by(self, attacker_id: UUID) -> Attack | None:
        return next((a for a in self.attacks if a.attacker_id == attacker_id), None)

    def attack_blocked_by(self, blocker_id: UUID) -> Attack | None:
        return next((a for a in self.attacks if blocker_id in a.blockers), None)

    def remove(self, card_id: UUID) -> None:
        """Take a permanent out of combat (CR 506.4).

        An attacker that goes takes its whole attack with it. A blocker that
        goes stops blocking, but the creature it was blocking stays blocked.
        """
        self.attacks = [a for a in self.attacks if a.attacker_id != card_id]
        for attack in self.attacks:
            if card_id in attack.blockers:
                attack.blockers.remove(card_id)

    def clear(self) -> None:
        """Everything is removed from combat as the combat phase ends (CR 511.3)."""
        self.attacks = []
        self.blockers_declared = False
        self.damage_steps_done = 0
        self.first_strike_step_happened = False
        self.attacked_this_combat = False


# -- declaring attackers ---------------------------------------------------


def attack_refusal(game: "Game", creature: CardState, defender: TargetRef) -> str | None:
    """Why this creature cannot be declared as an attacker, or None (CR 508.1a).

    CR 508.1a: "The chosen creatures must be untapped, they can't also be
    battles, and each one must either have haste or have been ..." controlled
    by the active player since their most recent turn began - which is what
    `CardState.summoning_sick` tracks (CR 302.6, 702.10b).
    """
    assert game.turn is not None
    active = game.turn.active_player

    if creature.zone is not Zone.BATTLEFIELD:
        return f"{creature.name} is in {creature.zone.value}, not on the battlefield"
    if not game.characteristics_of(creature).is_creature:
        # Read off the computed board (CR 613.5), not the printed type line,
        # so a permanent a continuous effect turned into a creature - Karn,
        # the Great Creator's animated Trinisphere - can attack like any other.
        return f"{creature.name} is not a creature"
    if game.controller_of(creature).username != active:
        return f"{creature.name} is not controlled by the active player"
    if game.combat.attack_by(creature.id) is not None:
        # Checked before "is tapped", or attacking taps it and the second
        # declaration reports the wrong reason.
        return f"{creature.name} is already attacking"
    if creature.tapped:
        return f"{creature.name} is tapped"
    if creature.summoning_sick and not has_keyword(creature, Keyword.HASTE, game):
        return f"{creature.name} has summoning sickness and no haste"
    if has_keyword(creature, Keyword.DEFENDER, game):
        # CR 702.3b: "A creature with defender can't attack." Checked after
        # tapping and summoning sickness so a Wall that is also tapped still
        # reports the reason a scenario is most likely asking about.
        return f"{creature.name} has defender and cannot attack (CR 702.3b)"

    return _defender_refusal(game, defender, active)


def _defender_refusal(game: "Game", defender: TargetRef, active: str) -> str | None:
    """Whether this is something the active player may attack (CR 508.1a, 508.1c)."""
    if defender.is_player:
        username = defender.username
        if username == active:
            return "a creature cannot attack its own controller"
        if username is None or not game.is_in_game(username):
            return f"{username} is not a player in this game"
        return None

    permanent = game.resolve_target(defender)
    if not isinstance(permanent, CardState) or permanent.zone is not Zone.BATTLEFIELD:
        return "that permanent is not on the battlefield"
    if not set(permanent.card.types) & ATTACKABLE_PERMANENT_TYPES:
        return f"{permanent.name} is not a player, planeswalker, or battle"
    if game.controller_of(permanent).username == active:
        return f"{permanent.name} is not controlled by an opponent"
    return None


def declare_attacker(game: "Game", creature: CardState, defender: TargetRef) -> Attack:
    """Declare one attacker, tapping it unless it has vigilance.

    Tapping is not a cost - attacking simply causes it (CR 508.1f) - so a
    creature that is somehow already tapped is refused earlier rather than
    failing to pay. A creature that taps this way became tapped (CR 701.26a),
    which is its own trigger event; one with vigilance (CR 702.20b) never
    taps, and so never fires it.
    """
    refusal = attack_refusal(game, creature, defender)
    if refusal is not None:
        raise ValueError(refusal)

    if not has_keyword(creature, Keyword.VIGILANCE, game):
        creature.tap()  # CR 508.1f
        game.emit(
            GameEvent(
                event=TriggerEvent.BECOMES_TAPPED,
                subject_id=creature.id,
                subject_name=creature.name,
                subject_controller=game.controller_of(creature).username,
                subject_card=creature.card,
                player=game.controller_of(creature).username,
            )
        )

    game.combat.attacked_this_combat = True  # CR 508.8 reads the declaration
    attack = Attack(attacker_id=creature.id, defender=defender)
    game.combat.attacks.append(attack)
    return attack


# -- declaring blockers ----------------------------------------------------


def block_refusal(game: "Game", blocker: CardState, attack: Attack) -> str | None:
    """Why this creature cannot block that attacker, or None (CR 509.1a-b).

    Covers the base requirements, who the attacker is attacking (CR 802.4a),
    and the two evasion abilities that need nothing but the attacker and the
    blocker to decide: flying (CR 702.9b) and reach (CR 702.17b).
    """
    attacker = game.find_by_id(attack.attacker_id)
    if attacker is None or attacker.zone is not Zone.BATTLEFIELD:
        return "that creature is no longer attacking"

    if blocker.zone is not Zone.BATTLEFIELD:
        return f"{blocker.name} is in {blocker.zone.value}, not on the battlefield"
    if not game.characteristics_of(blocker).is_creature:
        # Computed, not printed (CR 613.5) - see `attack_refusal`'s identical
        # check for why.
        return f"{blocker.name} is not a creature"
    if blocker.tapped:
        return f"{blocker.name} is tapped"

    defending = defending_player(game, attack)
    if game.controller_of(blocker).username != defending:
        return f"{blocker.name} is not controlled by {defending}"

    if has_keyword(attacker, Keyword.FLYING, game) and not (
        has_keyword(blocker, Keyword.FLYING, game) or has_keyword(blocker, Keyword.REACH, game)
    ):
        return f"{attacker.name} has flying and {blocker.name} has neither flying nor reach"

    return landwalk_refusal(game, attacker, defending)


def landwalk_refusal(game: "Game", attacker: CardState, defending: str | None) -> str | None:
    """Why landwalk stops this attacker being blocked at all, or None (CR 702.14c).

    "A creature with landwalk can't be blocked as long as the defending player
    controls at least one land with the specified land type." It is an evasion
    ability (CR 702.14b) and it does not care what the *blocker* is, which is
    what makes it different from flying: nothing the defending player controls
    can block, so the refusal is about their lands rather than their creature.

    Only the five basic landwalks are read (CR 305.6). CR 702.14a allows other
    shapes - "nonbasic landwalk", "snow forestwalk" - and none are in the pool;
    a shape this does not know is not enforced, and `scripts/sweep_pool.py`
    reports it.
    """
    if defending is None:
        return None
    for keyword, land_type in LANDWALK_TYPES.items():
        if not has_keyword(attacker, keyword, game):
            continue
        lands = [
            permanent
            for permanent in game.permanents_controlled_by(defending)
            if land_type in permanent.card.subtypes
        ]
        if lands:
            return (
                f"{attacker.name} has {keyword.value} and {defending} controls "
                f"a {land_type}, so it cannot be blocked (CR 702.14c)"
            )
    return None


def declaration_refusal(game: "Game", declared: dict[UUID, list[CardState]]) -> str | None:
    """Why the whole block declaration is illegal, or None (CR 509.1).

    Some restrictions only make sense against the finished declaration rather
    than one blocker at a time - menace is the plain example, since a single
    blocker on a creature with menace is illegal but two are fine
    (CR 702.111b). Each creature may block only one attacker (CR 509.1a).
    """
    seen: set[UUID] = set()
    for attacker_id, blockers in declared.items():
        for blocker in blockers:
            if blocker.id in seen:
                return f"{blocker.name} cannot block more than one attacker"
            seen.add(blocker.id)

        attacker = game.find_by_id(attacker_id)
        if attacker is None:
            continue
        if has_keyword(attacker, Keyword.MENACE, game) and 0 < len(blockers) < 2:
            return f"{attacker.name} has menace and cannot be blocked by fewer than two creatures"
    return None


def declare_blockers(game: "Game", blocks: list[tuple[CardState, CardState]]) -> None:
    """Declare the whole block for this combat (CR 509.1).

    `blocks` is `(blocker, attacker)` pairs, in the order the blockers should
    be assigned damage in (CR 510.1c). Nothing is recorded unless the entire
    declaration is legal, so a refused declaration leaves combat untouched.
    """
    combat = game.combat
    declared: dict[UUID, list[CardState]] = {attack.attacker_id: [] for attack in combat.attacks}

    for blocker, attacker in blocks:
        attack = combat.attack_by(attacker.id)
        if attack is None:
            raise ValueError(f"{attacker.name} is not attacking")
        refusal = block_refusal(game, blocker, attack)
        if refusal is not None:
            raise ValueError(refusal)
        declared[attacker.id].append(blocker)

    refusal = declaration_refusal(game, declared)
    if refusal is not None:
        raise ValueError(refusal)

    for attack in combat.attacks:
        chosen = declared[attack.attacker_id]
        attack.blockers = [blocker.id for blocker in chosen]
        # CR 509.1h: once blocked, a creature stays blocked for the rest of combat.
        attack.blocked = attack.blocked or bool(chosen)
    combat.blockers_declared = True


def defending_player(game: "Game", attack: Attack) -> str | None:
    """Who is defending against this attack: the player, or the permanent's controller."""
    if attack.defender.is_player:
        return attack.defender.username
    permanent = game.resolve_target(attack.defender)
    if isinstance(permanent, CardState):
        return game.controller_of(permanent).username
    return None


# -- combat damage ---------------------------------------------------------


def combatants(game: "Game") -> list[CardState]:
    """Every attacking and blocking creature still on the battlefield."""
    ids = game.combat.attacker_ids + game.combat.blocker_ids
    found = (game.find_by_id(card_id) for card_id in ids)
    return [state for state in found if state is not None and state.zone is Zone.BATTLEFIELD]


def needs_first_strike_step(game: "Game") -> bool:
    """True if an extra combat damage step is needed (CR 510.4).

    Checked as the first combat damage step begins: if anything in combat has
    first strike or double strike, there are two damage steps rather than one.
    """
    return any(
        has_keyword(state, Keyword.FIRST_STRIKE, game)
        or has_keyword(state, Keyword.DOUBLE_STRIKE, game)
        for state in combatants(game)
    )


def deals_damage_this_step(
    state: CardState, *, first_strike_step: bool, game: "Game | None" = None
) -> bool:
    """Whether this creature assigns damage in the step about to happen (CR 510.4).

    CR 702.7a and CR 702.4a are static abilities like any other, so the answer
    comes off the computed board when there is one: a first strike granted in
    layer 6 makes the extra step happen (CR 510.4) and one removed by Humility
    stops it.

    In a first-strike step, only first strikers and double strikers assign. In
    the step after one, the double strikers assign again alongside everything
    that has neither ability.
    """
    first = has_keyword(state, Keyword.FIRST_STRIKE, game)
    double = has_keyword(state, Keyword.DOUBLE_STRIKE, game)
    if first_strike_step:
        return first or double
    return double or not first


def combat_damage_step(game: "Game") -> list[tuple["Targetable", int]]:
    """One combat damage step: assign, then deal it all at once (CR 510.1-510.2).

    Returns what was assigned, in assignment order, so a scenario can assert on
    the split rather than only on the wreckage. State-based actions run
    afterwards, as they do before any player would next get priority.
    """
    combat = game.combat
    first_strike_step = combat.damage_steps_done == 0 and needs_first_strike_step(game)
    if first_strike_step:
        combat.first_strike_step_happened = True

    assignments: list[tuple[CardState, Targetable, int]] = []

    # CR 510.1: attackers are announced first, then blockers - but nothing is
    # dealt until both are known, because combat damage is simultaneous.
    for attack in combat.attacks:
        attacker = game.find_by_id(attack.attacker_id)
        if attacker is None or attacker.zone is not Zone.BATTLEFIELD:
            continue
        if not deals_damage_this_step(attacker, first_strike_step=first_strike_step, game=game):
            continue
        assignments.extend(
            (attacker, target, amount)
            for target, amount in _attacker_assignment(game, attack, attacker)
        )

    for attack in combat.attacks:
        attacker = game.find_by_id(attack.attacker_id)
        for blocker_id in attack.blockers:
            blocker = game.find_by_id(blocker_id)
            if blocker is None or blocker.zone is not Zone.BATTLEFIELD:
                continue
            if not deals_damage_this_step(blocker, first_strike_step=first_strike_step, game=game):
                continue
            # CR 510.1d: a blocker whose attacker has gone assigns no damage.
            if attacker is None or attacker.zone is not Zone.BATTLEFIELD:
                continue
            power = _power_of(game, blocker)
            if power > 0:
                assignments.append((blocker, attacker, power))

    for source, target, amount in assignments:
        _deal_combat_damage(game, source, target, amount)

    combat.damage_steps_done += 1
    game.check_state_based_actions()
    return [(target, amount) for _, target, amount in assignments]


def _deal_combat_damage(game: "Game", source: CardState, target: "Targetable", amount: int) -> int:
    """Deal one creature's combat damage, then apply deathtouch and lifelink.

    Both keywords key off *damage that was actually dealt*, and `Game.deal_damage`
    returns it: a prevention effect (CR 615.1a) means the event dealt zero
    damage, and zero damage is not "dealt damage" for either CR 702.2b or
    CR 702.15b. Fog Bank is the card in the pool that makes the difference
    visible.

    The creature is named as the source, which is CR 120.1 - "An object that
    deals damage is the source of that damage" - and is what lets the prevention
    machinery answer the rules that ask about the source rather than the target:
    CR 609.7b's recheck, CR 615.8's "the next time a specific source would deal
    damage", and CR 702.16e's protection.
    """
    dealt = game.deal_damage(target, amount, source=source)
    if dealt <= 0:
        return 0

    if isinstance(target, CardState) and has_keyword(source, Keyword.DEATHTOUCH, game):
        # CR 702.2b: destroyed as a state-based action, whatever its toughness.
        target.dealt_deathtouch_damage = True
    if has_keyword(source, Keyword.LIFELINK, game):
        # CR 702.15b / CR 120.3f, and CR 702.15e keeps each source's life gain
        # a separate event, which is why this is inside the per-source loop.
        game.gain_life(game.controller_of(source), dealt)
    return dealt


def _power_of(game: "Game | None", creature: CardState) -> int:
    """CR 510.1a: a creature assigns combat damage equal to its power.

    "Each attacking creature and each blocking creature assigns combat damage
    equal to its power. Creatures that would assign 0 or less damage this way
    don't assign combat damage at all." Which power that is, is CR 613.5's
    question: the one the layer system leaves it with, not the printed value.
    `Game.power_of` computes the board; without a game the printed value plus
    counters (CR 122.1a) is all there is.
    """
    power = game.power_of(creature) if game is not None else creature.power
    return power or 0


def _toughness_of(game: "Game | None", creature: CardState) -> int | None:
    """This creature's toughness right now, layers included (CR 613.5)."""
    return game.toughness_of(creature) if game is not None else creature.toughness


def lethal_for(attacker: CardState, blocker: CardState, game: "Game | None" = None) -> int | None:
    """How much damage counts as lethal when `attacker` assigns to `blocker`.

    CR 510.1c divides a blocked creature's damage among its blockers, each
    assigned lethal damage before the next gets any, and CR 702.19b says the
    same for what trample may send past them. Ordinarily that is toughness less
    damage already marked, which is `lethal_damage_remaining`.

    CR 702.2c is deathtouch's whole contribution to the arithmetic: "Any nonzero
    amount of combat damage assigned to a creature by a source with deathtouch is
    considered to be lethal damage for the purposes of determining if excess
    damage is being dealt." One is a nonzero amount, so one is lethal - which is
    what lets a 5/5 with deathtouch and trample put four through a 4/4 blocker.

    None when the blocker's toughness is not a number.
    """
    if has_keyword(attacker, Keyword.DEATHTOUCH, game):
        return 1
    toughness = _toughness_of(game, blocker)
    return None if toughness is None else toughness - blocker.damage


def _attacker_assignment(
    game: "Game", attack: Attack, attacker: CardState
) -> list[tuple["Targetable", int]]:
    """How one attacking creature divides its damage (CR 510.1a-c, 702.19b).

    Unblocked, it all goes to whatever it is attacking. Blocked, it is divided
    among the blockers in declaration order, each one assigned lethal damage
    before the next gets any. With trample, whatever is left over once every
    blocker has lethal goes through to the defending player; without it, the
    leftover has nowhere to go but the last blocker.
    """
    power = _power_of(game, attacker)
    if power <= 0:  # CR 510.1a
        return []

    blockers = [
        blocker
        for blocker in (game.find_by_id(card_id) for card_id in attack.blockers)
        if blocker is not None and blocker.zone is Zone.BATTLEFIELD
    ]
    trample = has_keyword(attacker, Keyword.TRAMPLE, game)

    if not blockers:
        # CR 510.1c: blocked with every blocker gone means no damage at all,
        # unless trample sends it through anyway (CR 702.19d).
        if attack.blocked and not trample:
            return []
        defender = game.resolve_target(attack.defender)
        return [(defender, power)] if defender is not None else []

    assigned: list[tuple[Targetable, int]] = []
    remaining = power
    for blocker in blockers:
        if remaining <= 0:
            break
        lethal = lethal_for(attacker, blocker, game)
        share = remaining if lethal is None else min(remaining, max(lethal, 0))
        if share > 0:
            assigned.append((blocker, share))
            remaining -= share

    if remaining > 0:
        if trample:
            defender = game.resolve_target(attack.defender)
            if defender is not None:
                assigned.append((defender, remaining))
        elif assigned:
            target, amount = assigned[-1]
            assigned[-1] = (target, amount + remaining)
        else:
            assigned.append((blockers[-1], remaining))

    return assigned
