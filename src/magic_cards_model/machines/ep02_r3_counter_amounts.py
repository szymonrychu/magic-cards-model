"""EP-02 R3 T2: counter amounts and the keywords that put counters on a creature.

Fabricate (CR 702.123a): "When this permanent enters, you may put N +1/+1
counters on it. If you don't, create N 1/1 colorless Servo artifact creature
tokens." Each instance triggers separately (CR 702.123b).
"""

import re
from typing import TYPE_CHECKING

from ..models.card import Type
from ..models.player import Player
from ..models.zone import Zone
from ..numbers import COUNT, parse_count
from .abilities import KeywordAbility, TriggeredAbility, TriggerEvent, TriggerWord
from .amount_sentences import parse_put_counters
from .decisions import Decision, DecisionKind, source_id_of
from .effects._chains import ABILITY_TEXT, FORWARD, MIXED_CLAUSE, MIXED_CLAUSES
from .effects._common import AbilityEffect, TargetedClause, _targets_understood
from .effects.amounts import _for_each_multiplier
from .effects.counters import _counter_kind
from .effects.tokens import _parse_token_clause

if TYPE_CHECKING:
    from ..models.game import Game
    from .triggers import AbilityOnStack, StackObject

_WORDS = {1: "a", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six"}


def fabricate_ability(ability: KeywordAbility) -> TriggeredAbility:
    """CR 702.123a, written out as the triggered ability it stands for."""
    from .keywords import _expansion

    count = ability.count if ability.count is not None else 1
    quantity = _WORDS.get(count, str(count))
    counters = "counter" if count == 1 else "counters"
    servos = "Servo artifact creature token" if count == 1 else "Servo artifact creature tokens"
    return _expansion(
        ability,
        keyword="fabricate",
        word=TriggerWord.WHEN,
        condition="this permanent enters",
        effect=(
            f"you may put {quantity} +1/+1 {counters} on it. "
            f"If you don't, create {quantity} 1/1 colorless {servos}"
        ),
        event=TriggerEvent.ENTERS_THE_BATTLEFIELD,
    )


# -- "Exile a creature with the greatest power among creatures target opponent controls."

_GROUP_EXTREMUM_REMOVAL_RE = re.compile(
    r"^(?P<verb>exile|destroy) an? creature with the (?P<dir>greatest|least) "
    r"(?P<stat>power|toughness) among creatures "
    r"(?P<who>target opponent|target player) controls\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s34", for_spell=FORWARD)
def _parse_remove_extremum_creature_of_target_player(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """ "Exile a creature with the greatest power among creatures target
    opponent controls." (Fall of the Impostor III): the player is the target
    (CR 115.1), the creature is not (CR 115.10a), so hexproof on it stops
    nothing. The extremum is taken as the effect resolves (CR 608.2h); a tie
    for it is the ability controller's choice, since "a creature" is theirs to
    pick (CR 608.2d)."""
    match = _GROUP_EXTREMUM_REMOVAL_RE.fullmatch(clause.strip())
    if match is None or not _targets_understood(f"{match.group('who')}", allow_player_targets=True):
        return None
    greatest = match.group("dir").lower() == "greatest"
    stat = match.group("stat").lower()
    exiling = match.group("verb").lower() == "exile"

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object).username
        players = [t for t in game.resolve_targets(stack_object) if isinstance(t, Player)]
        pool = [
            permanent
            for player in players
            for permanent in game.permanents_controlled_by(player.username)
            if game.characteristics_of(permanent).is_creature
        ]
        if not pool:
            return

        def value(permanent) -> int:
            number = game.power_of(permanent) if stat == "power" else game.toughness_of(permanent)
            return number if number is not None else 0

        bound = (max if greatest else min)(value(permanent) for permanent in pool)
        tied = [permanent for permanent in pool if value(permanent) == bound]
        pick = tied[0]
        if len(tied) > 1:
            chosen_ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=controller,
                    prompt=f"choose a creature with the {match.group('dir').lower()} {stat}",
                    source=getattr(stack_object, "source_name", None) or stack_object.name,
                    amount=1,
                    exact=True,
                    cards=tuple(permanent.id for permanent in tied),
                    source_id=source_id_of(stack_object),
                )
            )
            by_id = {permanent.id: permanent for permanent in tied}
            pick = by_id.get(chosen_ids[0]) if chosen_ids else tied[0]
        if pick.zone is Zone.BATTLEFIELD:
            if exiling:
                game.exile_permanent(pick)
            else:
                game.destroy(pick)

    return effect


# -- "Create a <token>, then put N <kind> counters on it for each <thing>."

_THEN_PUT_RE = re.compile(
    r"^(?P<create>create .+?)(?:,|\.)\s+(?:and )?then put (?P<put>.+)$", re.IGNORECASE
)
_THAT_TOKEN_RE = re.compile(r"^(?:that token|it|each of them)$", re.IGNORECASE)


@MIXED_CLAUSES.rung("s1", for_spell=FORWARD)
def _parse_create_then_put_counters_for_each(
    text: str, *, for_spell: bool
) -> list[TargetedClause] | None:
    """ "Create a 2/2 ... token, then put two +1/+1 counters on that token for
    each spell you've cast this turn other than the first." (Outlaw Stitcher):
    the counters go on the token(s) the first instruction just made (CR 608.2c,
    instructions in order), `N` of them per counted thing, the count taken once
    as the instruction applies (CR 608.2h). Without a "for each" it is the
    plain "put N counters on it" riding on the new token."""
    if " then put " not in text.lower() or " token" not in text.lower():
        return None
    split = _THEN_PUT_RE.fullmatch(" ".join(text.strip().split()))
    if split is None:
        return None
    put = parse_put_counters(f"put {split.group('put').rstrip('.')}")
    if put is None or put.x or _THAT_TOKEN_RE.fullmatch(put.on) is None:
        return None
    if put.each is not None and "this way" in put.each.lower():
        return None  # the this-way ledger's count (ep02_r1_this_way_counts) is not a for-each
    reader = _for_each_multiplier(put.each) if put.each is not None else None
    if put.each is not None and reader is None:
        return None
    create = _parse_token_clause(split.group("create").rstrip(".").strip(), for_spell=for_spell)
    if create is None:
        return None
    kind = _counter_kind(put.kind)

    def effect(game: "Game", stack_object: "StackObject") -> None:
        before = {existing.id for existing in game.battlefield}
        create(game, stack_object)
        created = [state for state in game.battlefield if state.id not in before]
        amount = put.n
        if reader is not None:
            controller = game.controller_of(stack_object).username
            amount *= reader(game, controller, source_id_of(stack_object))
        if amount <= 0:
            return
        for token in created:
            game.add_counters(token, kind, amount)

    return [effect]


# -- "Put a +1/+1 counter on it for each other Zombie that entered the
# battlefield under your control this turn."

_TYPE_WORDS = frozenset(kind.value.lower() for kind in Type)
_ENTERED_THIS_TURN_COUNTERS_RE = re.compile(
    rf"^put (?P<n>{COUNT}) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on it for each other "
    r"(?P<what>[a-z]+) that entered the battlefield under your control this turn\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s36")
def _parse_counters_on_entering_object_for_each_other_entered(
    effect_text: str,
) -> AbilityEffect | None:
    """Geralf, the Fleshwright: "Whenever a Zombie you control enters, put a
    +1/+1 counter on it for each other Zombie that entered the battlefield
    under your control this turn." "It" is the entering object (the trigger
    event's subject); the count is `Game.turn_count`'s ledger of what entered
    for its controller this turn (still true of ones that have since left,
    CR 603.6a), less the subject itself, taken as the ability resolves
    (CR 608.2h)."""
    if "that entered the battlefield under your control this turn" not in effect_text.lower():
        return None
    match = _ENTERED_THIS_TURN_COUNTERS_RE.fullmatch(" ".join(effect_text.strip().split()))
    if match is None:
        return None
    unit = parse_count(match.group("n"))
    if unit is None:
        return None
    kind = _counter_kind(match.group("kind"))
    what = match.group("what").lower()
    fact = f"entered_type:{what}" if what in _TYPE_WORDS else f"entered_subtype:{what}"

    def effect(game: "Game", ability: "AbilityOnStack") -> None:
        event = ability.event
        subject = game.find_by_id(event.subject_id) if event and event.subject_id else None
        if subject is None or subject.zone is not Zone.BATTLEFIELD:
            return
        others = game.turn_count(fact, ability.controller) - 1
        if others > 0:
            game.add_counters(subject, kind, unit * others)

    return effect
