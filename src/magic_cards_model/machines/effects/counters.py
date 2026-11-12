import re
from collections.abc import Callable
from random import Random
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from magic_cards_model.phrases import with_indefinite_article
from magic_cards_model.text_norm import collapsed

from ...models.card import Color, Layout, Supertype, Type
from ...models.card_state import (
    CardState,
    Counter,
)
from ...models.player import Player
from ...models.token import (
    create_tokens,
)
from ...models.zone import Zone
from ...numbers import (
    COUNT,
    count_pattern,
    halve,
    parse_count,
    where_x_pattern,
)
from ..abilities import (
    TriggeredAbility,
    TriggerEvent,
)
from ..casting import (
    PlayAction,
    remove_suspend_time_counter,
)
from ..chosen_type import (
    shares_creature_type,
)
from ..decisions import Decision, DecisionKind, source_id_of
from ..delayed import (
    ANAPHORIC_TIMING_STEPS,
    AddManaAmountForController,
    AddManaInAnyCombinationForController,
    DelayedTrigger,
    PutCountersOnSubject,
    ReflexiveWhenYouDoConsequence,
    put_counters_and_grant_keywords_to_event_subject,
)
from ..ep02_r2_devotion_domain_party import counters_amount_effect
from ..keyword_counters import symbol_groups_spent
from ..layers import (
    ContinuousEffect,
    Duration,
    Layer,
    RemainsOnBattlefield,
    _only,
    _split_and_validate_keywords,
    add_subtype,
    grant_ability,
    only_this_incarnation,
    split_and_validate_keywords,
)
from ..legacy_keywords import BACKUP_GRANT_CLAUSE, backup_granted_lines
from ..triggers import (
    AbilityOnStack,
    GameEvent,
    event_subject_power,
    has_self_reference_type_word,
)
from ..turn import Step

if TYPE_CHECKING:
    from ...models.game import Game, StackObject
from ._chains import ABILITY_TEXT, FORWARD, MIXED_CLAUSE, SPELL_TEXT
from ._common import _SELF_ANAPHOR, _SPELL_QUALIFIER, AbilityEffect, Effect, TargetedClause

#: "Remove a `<kind>` counter from it. Then if this card has no `<kind>`
#: counters on it, return it to the battlefield." - Darigaaz Reincarnated's
#: egg-counter upkeep trigger, the suspend-shaped countdown of a card that
#: waits in exile (CR 113.6b: it functions from the exile zone it names).
#: The return puts the card onto the battlefield under its owner's control
#: (CR 110.2a: not cast; CR 400.7: a new object).
_COUNTER_REMOVAL_THEN_RETURN_SELF_RE = re.compile(
    r"^remove an? (?P<kind>[a-z0-9+/-]+) counter from (?:it|this card)\. "
    r"then if (?:this card|it) has no (?P=kind) counters? on it, "
    r"return (?:it|this card) to the battlefield\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s26")
def _parse_counter_removal_then_return_self_clause(text: str) -> AbilityEffect | None:
    """`_COUNTER_REMOVAL_THEN_RETURN_SELF_RE`'s shape. The ability's source is
    found by id wherever it is now (CR 113.7a); it counts down only while it is
    still the exiled card, and returns only on the removal that empties it."""
    match = _COUNTER_REMOVAL_THEN_RETURN_SELF_RE.fullmatch(text.strip())
    if match is None:
        return None
    kind = _counter_kind(match.group("kind"))

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.EXILE or source.counter_count(kind) < 1:
            return
        source.remove_counters(kind, 1)
        if source.counter_count(kind) == 0:
            game.put_onto_battlefield(source, source.owner)

    return effect


#: "Put N `<kind>` counters on it at the beginning of the next end step." -
#: Protean Hydra's payoff for each counter removed from it. The counters are a
#: delayed triggered ability (CR 603.7a) created as this one resolves, about
#: the permanent "it" names - the ability's own source - and CR 603.7c has it
#: add nothing to a permanent that left the battlefield (or came back as a new
#: object, CR 400.7) before the step arrives. The timing phrase is any
#: `ANAPHORIC_TIMING_STEPS` entry.
_PUT_COUNTERS_ON_SELF_AT_STEP_RE = re.compile(
    rf"^put (?P<n>{COUNT}|an?) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on "
    rf"(?P<object>it|this [a-z]+) at (?P<timing>{'|'.join(map(re.escape, ANAPHORIC_TIMING_STEPS))})"
    r"\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s26")
def _parse_put_counters_on_self_at_step_clause(text: str) -> AbilityEffect | None:
    """`_PUT_COUNTERS_ON_SELF_AT_STEP_RE`'s shape (CR 122.1, 603.7)."""
    if " at " not in text:
        return None
    match = _PUT_COUNTERS_ON_SELF_AT_STEP_RE.fullmatch(collapsed(text))
    if match is None:
        return None
    amount = parse_count(match.group("n"))
    step = ANAPHORIC_TIMING_STEPS[match.group("timing").lower()]
    if amount is None:
        return None
    kind = str(_counter_kind(match.group("kind")))
    clause = text.strip().rstrip(".")

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        game.create_delayed_trigger(
            DelayedTrigger(
                text=clause,
                event=TriggerEvent.BEGINNING_OF_STEP,
                step=step,
                controller=ability.controller,
                source_id=ability.source_id,
                source_name=ability.source_name,
                subject_id=source.id,
                expected_zone=Zone.BATTLEFIELD,
                expected_stamp=source.zone_change_stamp,
                effect=PutCountersOnSubject(counter_kind=kind, amount=amount),
            )
        )

    return effect


#: "Put a number of `<kind>` counters on it/this `<noun>`/`<Name>` equal to
#: `<expr>`." - the resolving-effect twin of the "enters with a number of
#: `<kind>` counters on it equal to `<expr>`" replacement (Reverent Hunter's
#: enters trigger). The third `object` shape is Drizzt Do'Urden's own "put a
#: number of +1/+1 counters on Drizzt equal to the difference" - CR 201.5's
#: self-reference by the card's own (here, CR 201.5c's *shortened*) printed
#: name rather than CR 700.7's "this creature"; `_parse_put_counters_equal_
#: to_clause` below checks the captured name against the resolving ability's
#: actual source before treating it as one, the same guard `_parse_may_
#: exile_self_then_return_clause` already uses for its own CR 201.5 shape.
_COUNTERS_EQUAL_TO_ON_OBJECT_RE = re.compile(
    r"^(?i:put a number of (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on )"
    r"(?P<object>(?i:it|this \w+)|[A-Z][A-Za-z']*)"
    r"(?i: equal to )(?P<expression>.+?)\.?$"
)


@ABILITY_TEXT.rung("s26")
def _parse_put_counters_equal_to_clause(text: str) -> AbilityEffect | None:
    """`_COUNTERS_EQUAL_TO_ON_OBJECT_RE`'s shape (CR 122.1, 608.2c).

    "This `<noun>`" is the ability's source (CR 109.2). "It" is the object the
    trigger's own condition named (`GameEvent.subject_id`, the same referent
    `_parse_untap_trigger_subject_clause` reads), falling back to the source for
    an ability with no event. X is the ability's own announced X. An
    expression `amount_expression` cannot read records an
    `UnreadableCounterAmountNotice` and places nothing.

    "The difference" is Drizzt Do'Urden's own magnitude - "if it had power
    greater than Drizzt's power, put a number of +1/+1 counters on Drizzt
    equal to the difference" - read here rather than as an `amount_expression`
    term: it needs `AbilityOnStack.event` (the dying creature `event_subject_
    power` reads, CR 603.10a's look-back), which `amount_expression`'s own
    `(game, controller, obj, x)` reader shape has no room for. CR 107.1b's
    "if a calculation ... yields a negative number, zero is used instead"
    applies the same way it does inside `amount_expression` itself.
    """
    match = _COUNTERS_EQUAL_TO_ON_OBJECT_RE.fullmatch(text.strip())
    if match is None:
        return None
    kind = _counter_kind(match.group("kind"))
    expression = match.group("expression").strip()
    is_the_difference = expression.lower() == "the difference"
    reader = None if is_the_difference else amount_expression(expression)
    object_phrase = match.group("object")
    names_the_subject = object_phrase.lower() == "it"
    # CR 201.5/201.5c: anything left is neither "it" nor "this <noun>" -
    # the card's own (possibly shortened) printed name, self-referencing the
    # ability's own source and nothing else with the same name.
    self_named = (
        None if names_the_subject or object_phrase.lower().startswith("this ") else object_phrase
    )

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        obj = ability.source(game)
        event = ability.event
        if names_the_subject and event is not None and event.subject_id is not None:
            obj = game.find_by_id(event.subject_id)
        if obj is None or obj.zone is not Zone.BATTLEFIELD:
            return
        if self_named is not None and self_named.lower() not in (obj.name or "").lower():
            return
        if is_the_difference:
            dying = event_subject_power(game, event)
            if dying is None:
                return
            amount = max(dying - (game.power_of(obj) or 0), 0)
        elif reader is None:
            game.unreadable_counter_amount_notices.append(
                UnreadableCounterAmountNotice(
                    source_id=ability.source_id,
                    source_name=ability.source_name,
                    text=text.strip(),
                    expression=expression,
                )
            )
            return
        else:
            amount = reader(game, ability.controller, obj, ability.x_value)
        if amount > 0:
            game.add_counters(obj, kind, amount)

    return effect


#: "Put a `<kind>` counter on it. Then for each `<kind>` counter on it,
#: `<effect>`." - Rottenmouth Viper's own "Whenever this creature enters or
#: attacks, put a blight counter on it. Then for each blight counter on it,
#: each opponent loses 4 life unless that player sacrifices a nonland
#: permanent of their choice or discards a card." Read as one CR 608.2c
#: instruction, the same way `_parse_ante_self_if_you_do_clause` and every
#: other "run the first sentence, then act on its own result" reader in this
#: file is: the second sentence's own count is CR 122.1's count on the exact
#: object the first sentence just modified, not a fresh board fact to
#: recompute, so a source already carrying counters from an earlier trigger
#: (an attack after an earlier attack or entrance) punishes that many times
#: over. `<effect>` is read generically through `parse_clause_effect` - the
#: same per-clause dispatcher every other player clause in this module goes
#: through - so a future card pairing a different counter kind with a
#: different repeated effect reads here too, not only this one punisher.
_PUT_COUNTER_THEN_FOR_EACH_COUNTER_RE = re.compile(
    r"^put an? (?P<kind>[a-z]+) counter on it\.\s*"
    r"then for each (?P<kind2>[a-z]+) counter on it,\s*(?P<rest>.+)$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s1")
def _parse_put_counter_then_for_each_counter_punisher_clause(
    text: str,
) -> AbilityEffect | None:
    """`_PUT_COUNTER_THEN_FOR_EACH_COUNTER_RE`'s shape, or `None`.

    Ability-only in practice (the "it" is CR 109.2's self-reference to the
    ability's own source, which a resolving spell has none of the way a
    permanent's own triggered ability does) - nothing in the pool prints
    this shape on a spell, so this is never tried against one.
    """
    match = _PUT_COUNTER_THEN_FOR_EACH_COUNTER_RE.fullmatch(
        _strip_non_effect_preamble(text).strip()
    )
    if match is None:
        return None
    kind = match.group("kind").lower()
    if match.group("kind2").lower() != kind:
        return None
    inner = parse_clause_effect(match.group("rest").strip())
    if inner is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        game.add_counters(source, kind, 1)
        count = source.counter_count(kind)
        if count <= 0:
            return
        player = game.player(ability.controller)
        source_name = ability.source_name
        source_id = source_id_of(ability)
        for _ in range(count):
            inner(game, player, source_name, source_id)
            game.announce_batched_events()  # CR 603.2c: one event per instruction

    return effect


#: Vraska, Betrayal's Sting's -9: "If target player has fewer than nine poison
#: counters, they get a number of poison counters equal to the difference."
#: CR 122.1: counters on a player; the difference is the threshold minus the
#: counters the target already has, counted once as the ability resolves (CR
#: 608.2h) - a player at or past the threshold gets none.
_PLAYER_COUNTERS_UP_TO_THRESHOLD_RE = re.compile(
    rf"^if target (?:player|opponent) has fewer than (?P<n>{COUNT}) (?P<kind>[a-z]+) counters, "
    r"they get a number of (?P<kind2>[a-z]+) counters equal to the difference\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s26")
def _parse_player_counters_up_to_threshold_clause(text: str) -> AbilityEffect | None:
    """`_PLAYER_COUNTERS_UP_TO_THRESHOLD_RE`'s shape, or `None`."""
    match = _PLAYER_COUNTERS_UP_TO_THRESHOLD_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None or match.group("kind").lower() != match.group("kind2").lower():
        return None
    threshold = parse_count(match.group("n"))
    if threshold is None:
        return None
    kind = _counter_kind(match.group("kind"))

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        target = next((t for t in game.resolve_targets(ability) if isinstance(t, Player)), None)
        if target is None:  # CR 608.2b: the target is gone, the ability does nothing
            return
        missing = threshold - target.counters[kind]
        if missing > 0:
            game.add_player_counters(target, kind, missing)

    return effect


#: "Each opponent gets a poison counter." (Infectious Bite, Infectious
#: Inquiry, Prologue to Phyresis) / "Each player gets two poison counters." -
#: CR 122.1f: poison counters are a kind a player gets; ten or more lose the
#: game as a state-based action (CR 704.5c). "Each opponent" is every player
#: in the game but the clause's own controller, each getting the counters in
#: turn.
_EACH_PLAYER_GETS_COUNTERS_RE = re.compile(
    rf"^each (?P<who>opponent|player) gets (?P<n>{COUNT}) (?P<kind>poison|energy|rad) "
    r"counters?\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s13", for_spell=FORWARD)
def _parse_each_player_gets_counters_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_EACH_PLAYER_GETS_COUNTERS_RE`'s shape, or `None`."""
    match = _EACH_PLAYER_GETS_COUNTERS_RE.fullmatch(collapsed(clause.strip()))
    if match is None:
        return None
    amount = parse_count(match.group("n"))
    if amount is None:
        return None
    kind = _counter_kind(match.group("kind"))
    opponents_only = match.group("who").lower() == "opponent"

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object).username
        for player in list(game.players_in_game):
            if opponents_only and player.username == controller:
                continue
            game.add_player_counters(player, kind, amount)

    return effect


#: Diamond City: "Move a shield counter from this land onto target creature."
#: CR 122.5's "move" keyword action, self-referential source (`_COUNTER_
#: SELF_SUBJECT`'s "this `<noun>`" shape, reused from `cost.py`'s own counter
#: phrasing) and a target destination.
#:
#: "onto **another** target creature" (Scrounging Bandar's "you may move any
#: number of +1/+1 counters from this creature onto another target
#: creature.", Tester of the Tangential's reflexive "move X +1/+1 counters
#: from this creature onto another target creature.") is CR 115.1's ordinary
#: "another" exclusion on the same destination phrase - `phrase` already
#: reaches `_targets_understood`, which reads "another" the same way every
#: other target phrase in this file does, so this only has to stop refusing
#: the word before that check is ever reached.
_MOVE_COUNTER_RE = re.compile(
    rf"^move (?P<n>{COUNT}) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? from this \w+ onto "
    r"(?P<phrase>(?:another )?target .+)\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s36")
def _parse_move_counter_clause(text: str) -> AbilityEffect | None:
    """CR 122.5: "to 'move' a counter ... means to remove that counter from
    the object it's currently on and put it onto a second object. If either
    of these actions isn't possible, it's not done at all." Both halves are
    checked before either happens - a source with too few counters, or a
    target that is no longer legal, leaves the source's counters untouched
    rather than removing them into nothing.
    """
    match = _MOVE_COUNTER_RE.fullmatch(text.strip())
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=False):
        return None
    amount = parse_count(match.group("n"))
    kind = _counter_kind(match.group("kind"))
    if amount is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        if not source.can_remove_counters(kind, amount):
            return
        targets = [
            target
            for target in game.resolve_targets(ability)
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
        ]
        if not targets:
            return
        source.remove_counters(kind, amount)
        game.add_counters(targets[0], kind, amount)

    return effect


#: Graft (CR 702.58a): "you may move a +1/+1 counter from this permanent onto
#: that creature" - the destination is the creature whose entering triggered
#: the ability (the event's subject), not a target (CR 115.10a: nothing here
#: says "target").
_MOVE_COUNTER_ONTO_EVENT_SUBJECT_RE = re.compile(
    rf"^(?P<may>you may )?move (?P<n>{COUNT}) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? "
    r"from this \w+ onto that (?:creature|permanent)\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s36")
def _parse_move_counter_onto_event_subject_clause(text: str) -> AbilityEffect | None:
    """CR 122.5 as `_parse_move_counter_clause` reads it, with the destination
    being the triggering event's subject. Both halves are checked before
    either happens: a source with too few counters, or a subject that has left
    the battlefield, moves nothing."""
    match = _MOVE_COUNTER_ONTO_EVENT_SUBJECT_RE.fullmatch(text.strip())
    if match is None:
        return None
    raw_amount = match.group("n").lower()
    amount = 1 if raw_amount in ("a", "an", "one") else parse_count(raw_amount)
    if amount is None or amount < 1:
        return None
    kind = _counter_kind(match.group("kind"))
    optional = match.group("may") is not None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        event = ability.event
        if source is None or source.zone is not Zone.BATTLEFIELD or event is None:
            return
        destination = game.find_by_id(event.subject_id) if event.subject_id else None
        if (
            not isinstance(destination, CardState)
            or destination.zone is not Zone.BATTLEFIELD
            or not source.can_remove_counters(kind, amount)
        ):
            return
        if optional and not game.ask(
            Decision(
                kind=DecisionKind.MAY,
                player=ability.controller,
                prompt=f"move a {kind} counter from {source.name} onto {destination.name}",
                source=source.name,
                source_id=source_id_of(ability),
            )
        ):
            return
        source.remove_counters(kind, amount)
        game.add_counters(destination, kind, amount)

    return effect


#: Backup (CR 702.165a): "put N +1/+1 counters on target creature. If that's
#: another creature, it also gains the non-backup abilities of this creature
#: printed below this one until end of turn."
_BACKUP_RE = re.compile(
    rf"^put (?P<n>{COUNT}) (?P<kind>\+1/\+1) counters? on (?P<phrase>target creature)\. "
    rf"{re.escape(BACKUP_GRANT_CLAUSE)}\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s36")
def _parse_backup_clause(text: str) -> AbilityEffect | None:
    """`_BACKUP_RE`'s shape. The granted abilities are the lines printed below
    the backup line on the source's printing, fixed as the ability resolves
    (CR 702.165d); only the object's own printed abilities count (CR 702.165c)."""
    match = _BACKUP_RE.fullmatch(collapsed(text.strip()))
    if match is None:
        return None
    raw_amount = match.group("n").lower()
    amount = 1 if raw_amount in ("a", "an", "one") else parse_count(raw_amount)
    if amount is None:
        return None
    kind = _counter_kind(match.group("kind"))

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        targets = [
            target
            for target in game.resolve_targets(ability)
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
        ]
        if not targets:
            return
        target = targets[0]
        game.add_counters(target, kind, amount)
        if source is None or target.id == source.id:
            return
        store = continuous_effects(game)
        timestamp = store.tick()
        for line in backup_granted_lines(source.card.oracle_text or ""):
            store.add(
                ContinuousEffect(
                    description=f"{source.name}: {target.name} gains {line}",
                    layer=Layer.ABILITY,
                    timestamp=timestamp,
                    duration=Duration.UNTIL_END_OF_TURN,
                    source_id=source.id,
                    selector=only_this_incarnation(target, target.zone_change_stamp),
                    modification=grant_ability(line),
                ),
                game,
            )

    return effect


#: "Put a number of `<kind>` counters equal to the power of the card you
#: exiled on target creature." - CR 702.97a's whole scavenge effect. "The card
#: you exiled" is the object the ability's own cost exiled, found by id
#: wherever it is now (CR 113.7a), and its power is the one it had there
#: (CR 208.3's printed power for a card outside the battlefield).
_COUNTERS_EQUAL_TO_EXILED_POWER_RE = re.compile(
    r"^put a number of (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters equal to the power of the "
    r"card you exiled on (?P<phrase>target .+?)\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s36")
def _parse_counters_equal_to_exiled_power_clause(text: str) -> AbilityEffect | None:
    """`_COUNTERS_EQUAL_TO_EXILED_POWER_RE`'s shape, or `None`."""
    match = _COUNTERS_EQUAL_TO_EXILED_POWER_RE.fullmatch(text.strip())
    if match is None or not _targets_understood(match.group("phrase"), count_agnostic=False):
        return None
    kind = _counter_kind(match.group("kind"))

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        exiled = ability.source(game)
        if exiled is None:
            return
        power = game.characteristics_of(exiled).power
        if power is None or power <= 0:
            return
        for target in game.resolve_targets(ability):
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD:
                game.add_counters(target, kind, power)

    return effect


def put_counters_on_ability_targets(
    kind: Counter | str,
    amount: int,
    multiplier: Callable[["Game", str], int] | None = None,
) -> TargetedClause:
    """Put counters on each permanent this still legally targets (CR 122.1).

    `multiplier`, when given, is Immaculate Magistrate's own "... for each
    Elf you control" shape: `amount` is the per-instance count printed before
    "for each", multiplied by the quality's count, read once against the
    resolving object's controller (CR 611.2c fixes the magnitude once, at
    resolution, not once per target).
    """

    def effect(game: "Game", stack_object: "StackObject") -> None:
        total = amount
        if multiplier is not None:
            controller = game.controller_of(stack_object).username
            total = amount * multiplier(game, controller)
        if total <= 0:
            return
        for target in game.resolve_targets(stack_object):
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD:
                game.add_counters(target, kind, total)

    return effect


# --------------------------------------------------------------------------
# P4: put N counters on each member of a group ("each Cat you control"),
# rather than on something targeted (CR 122.1)
# --------------------------------------------------------------------------
#
# "Put a +1/+1 counter on each Cat you control." (Ajani, Nacatl Pariah's
# +2) and "... on each creature you control." (Leyline of Abundance) name no
# target at all - CR 115.1 has nothing to check here, so `put_counters_on_
# ability_targets`'s `game.resolve_targets` is the wrong tool. Ouroboroid's
# own "put X +1/+1 counters on each creature you control, where X is this
# creature's power" adds a magnitude read off the source itself - not
# `count_expression`'s "the number of ..." shape, since this is a plain
# characteristic read (CR 613.4, CR 613.5), not a count of anything.
#
# An optional leading "tapped"/"untapped" - Aang and La, Ocean's Fury's own
# attack trigger, "put a +1/+1 counter on each tapped creature you control" -
# is CR 110.5's status, read off the permanent's own live `tapped` field
# rather than the computed board `color`/`group` reads below: CR 110.5a says
# status "is not a characteristic", so it is never something a layer effect
# (CR 613.5) could have changed as of resolution the way a granted color or
# type can. Effie, Fast Learner (off-pool, not legal in any target format)
# proves the word is read generally rather than fitted to Aang's own card.
#
# `group` also reads a comma/"and"/"or"-joined **list** of subtypes - SOS's
# Blech, Loafing Pest: "put a +1/+1 counter on each Pest, Bat, Insect, Snake,
# and Spider you control." (CR 205.3's own subtype list, an inclusive "or":
# one creature carrying two of the named types still gets one counter, not
# two, since `place`'s `any(...)` below never adds twice for one permanent).
# Agent Phil Coulson's single-subtype "each other Hero you control" already
# read through the bare-word branch before this list widened it; that word
# is just the list's own one-element case now.
_COUNTER_EACH_GROUP_RE = re.compile(
    rf"^put (?P<n>{COUNT}|x) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on each "
    rf"(?P<other>other )?"
    r"(?:(?P<tap_state>tapped|untapped) )?"
    r"(?:(?P<color>white|blue|black|red|green|colorless|monocolored|multicolored) )?"
    r"(?:(?P<supertype>legendary|nonlegendary) )?"
    r"(?P<group>[a-z]+(?:,\s*[a-z]+)*(?:,?\s+(?:and|or)\s+[a-z]+)?) "
    rf"(?P<whose>you control|you don't control|your opponents control|an opponent controls)"
    rf"{where_x_pattern('expr')}\.?$",
    re.IGNORECASE,
)

#: "Put a +1/+1 counter on each creature you control and those creatures gain
#: trample until end of turn." (Lisette, Dean of the Root) - the group counter
#: clause plus a grant to the group it just marked (CR 608.2c: "those
#: creatures" are the ones that received a counter).
_COUNTER_EACH_GROUP_THEN_GRANT_RE = re.compile(
    r"^(?P<head>put .+? counters? on each [^,.]+?)(?:,)? (?:and|then) "
    r"(?:those|these) (?:creatures|permanents) gain (?P<keywords>[a-z][a-z, ]*?) "
    r"until end of turn\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s26")
def _parse_counters_on_group_then_grant_clause(text: str) -> AbilityEffect | None:
    """`_COUNTER_EACH_GROUP_THEN_GRANT_RE`'s shape: the ordinary group-counter
    clause, then each permanent whose counters grew gains the keywords until
    end of turn (CR 611.2a)."""
    match = _COUNTER_EACH_GROUP_THEN_GRANT_RE.fullmatch(text.strip())
    if match is None:
        return None
    head_text = match.group("head").strip()
    head = _parse_put_counters_on_group_clause(head_text)
    counted = _COUNTER_EACH_GROUP_RE.fullmatch(head_text)
    keywords = split_and_validate_keywords(match.group("keywords"))
    if head is None or counted is None or keywords is None:
        return None
    kind = _counter_kind(counted.group("kind"))

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        before = {state.id: state.counter_count(kind) for state in game.battlefield}
        head(game, ability)
        for permanent in list(game.battlefield):
            if permanent.counter_count(kind) > before.get(
                permanent.id, permanent.counter_count(kind)
            ):
                _grant_keywords_to(
                    game,
                    permanent,
                    list(keywords),
                    "until end of turn",
                    controller=ability.controller,
                    source_name=ability.source_name,
                )

    return effect


#: Guiding Hydra: "put a +1/+1 counter on each other creature you control." -
#: `_COUNTER_EACH_GROUP_RE`'s "each `<group>` you control" grammar only ever
#: reads one bare word for the group (a card type or a subtype), so "other"
#: needs its own shape rather than a widened group-word set.
_COUNTER_EACH_OTHER_CREATURE_RE = re.compile(
    rf"^put (?P<n>{COUNT}) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on each other creature "
    r"you control\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s13", for_spell=FORWARD)
def _parse_counter_each_other_creature_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_COUNTER_EACH_OTHER_CREATURE_RE`'s shape; see the banner above.

    CR 109.2's "other" excludes the resolving permanent itself (CR 201.5's
    self-reference the other direction) - read from `stack_object`'s own
    source when it is a permanent, and excluding nothing when it is a spell
    (a resolving spell is never itself a creature on the battlefield to be
    "other" than, CR 300.1). On a spell that targeted creatures earlier in
    its text - Moment of Glory's "Put a +1/+1 counter on target creature you
    control. If this spell was cast from a graveyard, also put a +1/+1
    counter on each other creature you control." - "other" is other than
    those targets, the English reading CR 608.2c asks for.
    """
    match = _COUNTER_EACH_OTHER_CREATURE_RE.fullmatch(clause.strip())
    if match is None:
        return None
    amount = parse_count(match.group("n"))
    if amount is None:
        return None
    kind = _counter_kind(match.group("kind"))

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object).username
        source = (
            stack_object if isinstance(stack_object, CardState) else stack_object.source(game)  # type: ignore[union-attr]
        )
        excluded = (
            {reference.card_id for reference in stack_object.targets if reference.is_card}
            if isinstance(stack_object, CardState)
            else set()
        )
        for permanent in list(game.battlefield):
            if source is not None and permanent.id == source.id:
                continue
            if permanent.id in excluded:
                continue
            if game.controller_of(permanent).username != controller:
                continue
            if not game.characteristics_of(permanent).is_creature:
                continue
            game.add_counters(permanent, kind, amount)

    return effect


#: Edgar, Moonlit Sovereign: "Put a +1/+1 counter on each creature you control
#: with a +1/+1 counter on it." - CR 122.1's existing-counter filter as the
#: selector, not "each `<group>`"'s type/subtype one. The filter's kind may be
#: left out - The Doctor, EMH's "with a counter on it" is a counter of any kind.
_COUNTER_EACH_CREATURE_WITH_COUNTER_RE = re.compile(
    rf"^put (?P<n>{COUNT}) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on each creature you "
    r"control with an? (?:(?P<filter_kind>\+1/\+1|-1/-1|(?!counters?\b)[a-z]+) )?"
    r"counters? on it\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s15", for_spell=FORWARD)
def _parse_counter_each_creature_with_counter_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_COUNTER_EACH_CREATURE_WITH_COUNTER_RE`'s shape; see the banner above.

    Every qualifying creature is judged against the board as it stood before
    this ability started resolving (CR 608.2f: the affected set is
    determined once), which needs no snapshot here because one permanent's
    own counter count never depends on another's - unlike a selector keyed
    on total board state, adding a counter to one creature cannot make or
    unmake a *different* creature's own qualification mid-loop.
    """
    match = _COUNTER_EACH_CREATURE_WITH_COUNTER_RE.fullmatch(clause.strip())
    if match is None:
        return None
    amount = parse_count(match.group("n"))
    if amount is None:
        return None
    kind = _counter_kind(match.group("kind"))
    filter_kind = _counter_kind(match.group("filter_kind")) if match.group("filter_kind") else None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object).username
        for permanent in list(game.battlefield):
            if game.controller_of(permanent).username != controller:
                continue
            if not game.characteristics_of(permanent).is_creature:
                continue
            if filter_kind is None:
                if not permanent.counters.counts:
                    continue
            elif permanent.counter_count(filter_kind) <= 0:
                continue
            game.add_counters(permanent, kind, amount)

    return effect


#: "Put a +1/+1 counter on each creature that attacked this turn." -
#: Invasion of Gobakhan's own back face, Lightshield Array. Unqualified by
#: any controller ("you control"/"an opponent controls" - `_COUNTER_EACH_
#: GROUP_RE`'s own mandatory `whose` group), unlike every other "each
#: `<group>`" counter clause in this file: CR 608.2c's plain reading is
#: every creature that attacked this turn, whoever controls it, read off
#: `Game.attacked_this_turn` (Hexhaven Dueling Arena's own per-turn set,
#: cleared at cleanup, `machines/targeting.py`'s "target creature that
#: attacked this turn" and Rowdy Research's/Witchstalker Frenzy's own cost
#: reduction "for each creature that attacked this turn" already read the
#: identical historical fact off the same field).
_COUNTER_EACH_ATTACKED_THIS_TURN_RE = re.compile(
    rf"^put (?P<n>{COUNT}) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on each creature "
    r"that attacked this turn\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s14")
def _parse_counter_each_attacked_this_turn_clause(clause: str) -> AbilityEffect | None:
    """`_COUNTER_EACH_ATTACKED_THIS_TURN_RE`'s shape, or `None`.

    Ability-only (`Game.attacked_this_turn` is a live per-turn fact a
    resolving spell reads exactly the same way, but nothing in the pool
    prints this on a spell): each creature that attacked this turn, still on
    the battlefield right now, gets the counter - a creature that attacked
    and later left keeps no counter to give (CR 400.7: it would be a new
    object anyway).
    """
    match = _COUNTER_EACH_ATTACKED_THIS_TURN_RE.fullmatch(clause.strip())
    if match is None:
        return None
    amount = parse_count(match.group("n"))
    if amount is None:
        return None
    kind = _counter_kind(match.group("kind"))

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        for permanent in list(game.battlefield):
            if permanent.id in game.attacked_this_turn:
                game.add_counters(permanent, kind, amount)

    return effect


@ABILITY_TEXT.rung("s26")
def _parse_put_counters_on_group_clause(
    text: str, *, for_spell: bool = False
) -> AbilityEffect | None:
    """ "Put N <kind> counter(s) on each <group> you control." - the group-wide
    twin of `_COUNTER_TARGET_RE`'s "on target X" below.

    `<group>` is read off the **computed** board (CR 613.5, CR 613.4): a
    creature that gained the Cat type only through a continuous effect still
    counts, and one that stops being a Cat before this resolves does not -
    the same defect class this repo's own MDFC front-face bugs already
    documented for a printed-type-line-only read. `<group>` "creature" is a
    card type (CR 205.2a); anything else is read as a creature subtype
    (CR 205.3) rather than a card type, since Ajani's own "Cat" is one.

    "X, where X is `<expr>`" reads `<expr>` through the shared `amount_
    expression` (Ouroboroid's own "this creature's power", the same reader
    Voja, Jaws of the Conclave's "the number of Elves you control" already
    goes through) rather than a literal string match against one printed
    expression - an expression it cannot read fails closed with an
    `UnreadableCounterAmountNotice` instead of placing a guessed number
    (CR 611.2c: the magnitude is fixed once, at resolution).

    An optional leading "other" - Summon: Good King Mog XII's own Saga
    chapter IV, "Put two +1/+1 counters on each **other** Moogle you
    control" - excludes the ability's own source (CR 109.2) from the group,
    the same "other" every targeted clause in this file already reads for a
    single target.

    An optional leading "tapped"/"untapped" - Aang and La, Ocean's Fury's own
    "put a +1/+1 counter on each tapped creature you control" - is CR 110.5's
    status, read off `CardState.tapped` directly rather than through `board`
    (CR 110.5a: status is not a characteristic, so it is never a layer
    effect's business the way the color/group check below is).

    `for_spell=True` is the same sentence resolving as a spell (Germination
    Practicum, Basri's Solidarity): "you" is the spell's controller, and only
    a fixed count with no "other" is read - a resolving spell is not a
    permanent on the battlefield to be "other" than or to read its own power
    off.
    """
    match = _COUNTER_EACH_GROUP_RE.fullmatch(text.strip())
    if match is None:
        return None
    if for_spell and (match.group("other") is not None or match.group("n").lower() == "x"):
        return None
    kind = match.group("kind").lower()
    group = match.group("group")
    # CR 205.3's subtype list, comma/"and"/"or" joined - a single bare word
    # ("creature", "Hero") is just this list's one-element case.
    group_words = [
        word.strip() for word in re.split(r",\s*|\s+and\s+|\s+or\s+", group) if word.strip()
    ]
    excludes_source = match.group("other") is not None
    tap_state = (match.group("tap_state") or "").lower()
    color_word = (match.group("color") or "").lower()
    # Archfiend of Ifnir's "each creature your opponents control": the
    # opponents of the resolving object's controller (CR 102.3: every
    # player not on that player's team), not that controller.
    opponents = not match.group("whose").lower().startswith("you control")
    supertype_word = (match.group("supertype") or "").lower()

    def color_matches(colors: tuple[Color, ...]) -> bool:
        if not color_word:
            return True
        if color_word in _COLOR_COUNT_WORDS:
            return _COLOR_COUNT_WORDS[color_word](len(colors))
        color = _HAND_EXILE_COLOR_WORDS[color_word]
        return not colors if color is None else color in colors

    n_text = match.group("n").lower()
    expr = match.group("expr")
    reader: AmountReader | None = None
    fixed_amount: int | None = None
    if n_text == "x":
        if expr is None:
            return None
        reader = amount_expression(expr)
    else:
        fixed_amount = parse_count(n_text)

    def place(game: "Game", controller: str, amount: int, excluded: UUID | None) -> None:
        board = game.computed_board()
        for permanent in game.battlefield:
            if excluded is not None and permanent.id == excluded:
                continue
            chars = board.of(permanent)
            if (chars.controller == controller) is opponents:
                continue
            if tap_state == "tapped" and not permanent.tapped:
                continue
            if tap_state == "untapped" and permanent.tapped:
                continue
            # CR 105.2c: "colorless" (Titans' Vanguard's "each colorless
            # creature you control"), or a color / CR 105.2a-b color count,
            # read off the computed board like the type below.
            if not color_matches(chars.colors):
                continue
            if supertype_word and (Supertype.LEGENDARY in chars.supertypes) != (
                supertype_word == "legendary"
            ):
                continue
            if len(group_words) == 1 and group_words[0].lower() == "creature":
                if not chars.is_creature:
                    continue
            elif len(group_words) == 1 and group_words[0].lower() == "planeswalker":
                # CR 205.2a: a card type, not a subtype - Way of the Mentor's
                # and Way of the Necromancer's "put a loyalty counter on each
                # planeswalker you control".
                if Type.PLANESWALKER not in chars.types:
                    continue
            elif not any(word in chars.subtypes for word in group_words):
                continue
            game.add_counters(permanent, kind, amount)

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        if isinstance(ability, CardState):
            # A resolving spell: a fixed count, never "other" (see above).
            if fixed_amount:
                place(game, game.controller_of(ability).username, fixed_amount, None)
            return
        source = ability.source(game)
        if source is None:
            return
        if fixed_amount is not None:
            amount = fixed_amount
        elif source.zone is not Zone.BATTLEFIELD:
            amount = 0
        elif reader is None:
            game.unreadable_counter_amount_notices.append(
                UnreadableCounterAmountNotice(
                    source_id=ability.source_id,
                    source_name=ability.source_name,
                    text=text.strip(),
                    expression=(expr or "").strip(),
                )
            )
            return
        else:
            amount = max(reader(game, ability.controller, source, ability.x_value), 0)
        if amount <= 0:
            return
        place(game, ability.controller, amount, source.id if excludes_source else None)

    return effect


#: "Put `<n>`/a number of `<kind>` counters[ equal to `<expr>`] on each
#: [other ]creature you control named `<Name>`." - Gruff Triplets' own dies
#: trigger: "put a number of +1/+1 counters equal to its power on each
#: creature you control named Gruff Triplets." CR 201.5's own name-based
#: reference (CR 205.3's subtype grouping is `_COUNTER_EACH_GROUP_RE`'s own
#: job above; this is a *name*, not a type or subtype) - a real, multi-card
#: MTG template, not invented for this one card: off-set Baloth Packhunter's
#: own "When this creature enters, put two +1/+1 counters on each other
#: creature you control named Baloth Packhunter." prints the identical
#: "each [other ]creature you control named `<Name>`" selector with a fixed
#: literal count instead of an "equal to" expression, and an "other" (its
#: own trigger fires while it is still alive and on the battlefield, unlike
#: Gruff Triplets' dies trigger, where the dead source is never part of the
#: scan to begin with).
_COUNTERS_ON_NAMED_GROUP_RE = re.compile(
    rf"^(?i:put )(?P<n>{COUNT}|a number of)(?i: )(?P<kind>\+1/\+1|-1/-1|[a-z]+)(?i: counters?)"
    r"(?:(?i: equal to )(?P<expression>.+?))?"
    r"(?i: on each )(?P<other>(?i:other ))?"
    r"(?i:creatures? you control named )"
    r"(?P<name>[A-Z][A-Za-z']*(?:\s[A-Z][A-Za-z']*)*)\.?$"
)


@ABILITY_TEXT.rung("s26")
def _parse_counters_on_named_group_clause(text: str) -> AbilityEffect | None:
    """`_COUNTERS_ON_NAMED_GROUP_RE`'s shape, or `None`.

    "Its power" is Gruff Triplets' own magnitude: CR 700.7's "this creature"
    read on a *dies* trigger, so "its" means the ability's own source as it
    last existed (CR 603.10a's look-back) - `event_subject_power` reads
    that off `AbilityOnStack.event`, the same helper Drizzt Do'Urden's own
    "the difference" uses, because a departed source is not part of any
    battlefield the layer system (`Game.power_of`) computes over. Any other
    "equal to" expression goes through the shared `amount_expression`,
    evaluated against the ability's own source - one neither reads fails
    closed with an `UnreadableCounterAmountNotice` rather than placing a
    guessed number (CR 611.2c). A bare literal count (Baloth Packhunter's
    "two") needs neither: `parse_count` already reads `numbers.COUNT`'s own
    "a"/"an" as one, so "a number of" is the only count word this pattern's
    `n` group does not hand straight to it.

    The name match is exact and case-sensitive against `CardState.name` -
    CR 707.2 already makes a token copy's name the same as the original's,
    so Gruff Triplets' own token copies (`_parse_self_copy_token_clause`)
    are "creatures you control named Gruff Triplets" too, with no special
    case needed for the fact that they are tokens.
    """
    match = _COUNTERS_ON_NAMED_GROUP_RE.fullmatch(text.strip())
    if match is None:
        return None
    kind = _counter_kind(match.group("kind"))
    n_text = match.group("n").lower()
    expression = match.group("expression")
    is_its_power = expression is not None and expression.strip().lower() == "its power"
    fixed_amount = None if n_text == "a number of" else parse_count(n_text)
    reader = (
        None
        if fixed_amount is not None or is_its_power
        else amount_expression((expression or "").strip())
    )
    excludes_source = match.group("other") is not None
    name = match.group("name").strip()

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if fixed_amount is not None:
            amount = fixed_amount
        elif is_its_power:
            dying = event_subject_power(game, ability.event)
            amount = max(dying, 0) if dying is not None else 0
        elif reader is None:
            game.unreadable_counter_amount_notices.append(
                UnreadableCounterAmountNotice(
                    source_id=ability.source_id,
                    source_name=ability.source_name,
                    text=text.strip(),
                    expression=(expression or "").strip(),
                )
            )
            return
        else:
            amount = max(reader(game, ability.controller, source, ability.x_value), 0)
        if amount <= 0:
            return
        controller = ability.controller
        board = game.computed_board()
        for permanent in game.battlefield:
            if excludes_source and source is not None and permanent.id == source.id:
                continue
            chars = board.of(permanent)
            if chars.controller != controller or not chars.is_creature:
                continue
            if permanent.name != name:
                continue
            game.add_counters(permanent, kind, amount)

    return effect


def _counter_kind(word: str) -> Counter | str:
    """Normalise a printed counter-kind word into what `add_counters`/
    `remove_counters` key on - the two CR 122.1a power/toughness spellings as
    `Counter.PLUS_ONE`/`Counter.MINUS_ONE`, and any other bare word (`oil`,
    `charge`, `fate`, ...) as the matching `Counter` member when the rules
    name one, or the plain lower-cased string otherwise (CR 122.1's kinds are
    an open set).
    """
    lowered = word.lower()
    if lowered == "+1/+1":
        return Counter.PLUS_ONE
    if lowered == "-1/-1":
        return Counter.MINUS_ONE
    try:
        return Counter(lowered)
    except ValueError:
        return lowered


#: "Distribute seven +1/+1 counters among any number of target creatures you
#: control." (Vorinclex // The Grand Evolution's own Saga chapter II) -
#: CR 601.2d's "divide or distribute an effect (such as damage or counters)
#: among one or more targets", read the same way `_DIVIDED_DAMAGE_RE` reads
#: its damage twin. `machines/targeting._read_division`'s own `_DIVIDED`
#: regex already reads this exact shape at announcement time into
#: `Division(amount=7, what="+1/+1 counters")` - this is the resolution
#: half, paying out `AbilityOnStack.division`/`CardState.division`'s
#: announced shares (or the same even-split fallback `_deal_divided_damage_
#: shares` already gives an un-announced spell) through `Game.add_counters`
#: rather than `Game.deal_damage`.
_DISTRIBUTE_COUNTERS_AMONG_TARGETS_RE = re.compile(
    rf"^distributes? (?P<n>{COUNT}) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? among "
    r"(?P<phrase>.+?)\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_distribute_counters_among_targets_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_DISTRIBUTE_COUNTERS_AMONG_TARGETS_RE`'s shape.

    Not `for_spell`-gated: the same CR 601.2d division reads off either kind
    of stack object (`_deal_divided_damage_shares`'s own docstring explains
    why - CR 602.2b makes an ability's announcement identical to a spell's).
    """
    match = _DISTRIBUTE_COUNTERS_AMONG_TARGETS_RE.fullmatch(clause.strip())
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=True):
        return None
    amount = parse_count(match.group("n"))
    if amount is None or amount <= 0:
        return None
    kind = _counter_kind(match.group("kind"))

    def effect(game: "Game", stack_object: "StackObject") -> None:
        _distribute_counters_shares(game, stack_object, kind, amount)

    return effect


#: The plural anaphors a "They gain <keyword>" rider can use to name the
#: creatures a distribute head just targeted.
_DISTRIBUTE_RIDER_ANAPHORS = frozenset({"they", "those creatures"})


def _parse_distribute_counters_then_targets_gain_clause_pair(
    first: str, second: str, *, for_spell: bool
) -> TargetedClause | None:
    """ "Distribute N `<kind>` counters among up to N target creatures. They
    gain `<keywords>` until end of turn." - Ajani, Sleeper Agent's `-3`
    (vigilance) and Vivien, Arkbow Ranger's `+1` (trample).

    "They" is CR 608.2c's anaphor back to the creatures the first sentence
    targeted - not to anything that entered the battlefield (the reading
    `_parse_put_then_grant_then_delayed_whole_text` gives the same pronoun
    after a "put ... onto the battlefield" head, which is why this pair is
    read here, ahead of it). Only targets still legal on resolution get the
    keyword (CR 608.2b), the same set `_distribute_counters_shares` pays.
    """
    head = _parse_distribute_counters_among_targets_clause(
        first.strip().rstrip("."), for_spell=for_spell
    )
    if head is None:
        return None
    grant = _ANAPHOR_GAINS_KEYWORDS_RE.fullmatch(second.strip().rstrip("."))
    if grant is None or grant.group("anaphor").lower() not in _DISTRIBUTE_RIDER_ANAPHORS:
        return None
    keywords = split_and_validate_keywords(grant.group("keywords"))
    if keywords is None:
        return None
    duration = (grant.group("duration") or "").lower() or None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        head(game, stack_object)
        controller = game.controller_of(stack_object).username
        source_name = (
            stack_object.card.name
            if isinstance(stack_object, CardState)
            else stack_object.source_name
        )
        for reference in stack_object.targets:
            target = game.legal_target(stack_object, reference)
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD:
                _grant_keywords_to(
                    game,
                    target,
                    list(keywords),
                    duration,
                    controller=controller,
                    source_name=source_name,
                )

    return effect


def _departed_stat_with_counters(
    game: "Game",
    event: "GameEvent | None",
    read_stat: Callable[["Game", "GameEvent | None"], int | None],
) -> int | None:
    """`read_stat`'s own answer. Kept as a facade name
    (`scripts/split/surface/effects.json`): the event-subject readers now go
    through `CardState.last_known_power_toughness`, which already includes a
    departed subject's counters (CR 608.2h), so nothing is added here."""
    return read_stat(game, event)


def _distribute_counters_shares(
    game: "Game", stack_object: "StackObject", kind: Counter | str, total: int
) -> None:
    """Pay out `total` counters of `kind` divided among `stack_object.targets`
    (CR 601.2d, CR 608.2b) - the counter twin of `_deal_divided_damage_
    shares`, sharing its `_divided_damage_shares` split (the real
    announcement when there is one, otherwise as even a split as it goes
    with the remainder on the first target). Only targets still legal on
    resolution (CR 608.2b) are paid; an illegal one's share is simply not
    placed, the division stays locked in as announced.
    """
    chosen = len(stack_object.targets)
    if chosen == 0 or total <= 0:
        return
    shares = _divided_damage_shares(total, chosen, stack_object.division)
    for reference, share in zip(stack_object.targets, shares, strict=True):
        target = game.legal_target(stack_object, reference)
        if isinstance(target, CardState) and share > 0:
            game.add_counters(target, kind, share)


_DISTRIBUTE_COUNTERS_AMONG_YOU_CONTROL_RE = re.compile(
    rf"^distributes? (?P<n>{COUNT}) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? among "
    r"(?P<count_phrase>any number of|[a-z]+(?:,\s*[a-z]+)*,?\s+or\s+[a-z]+) "
    r"(?P<quality>[a-z]+) you control\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s27")
def _parse_distribute_counters_among_you_control_clause(clause: str) -> Effect | None:
    """`_DISTRIBUTE_COUNTERS_AMONG_YOU_CONTROL_RE`'s shape, or `None`."""
    match = _DISTRIBUTE_COUNTERS_AMONG_YOU_CONTROL_RE.fullmatch(clause.strip())
    if match is None:
        return None
    amount = parse_count(match.group("n"))
    if amount is None or amount <= 0:
        return None
    kind = _counter_kind(match.group("kind"))
    count_phrase = match.group("count_phrase")
    uncapped = count_phrase.strip().lower() == "any number of"
    if not uncapped and _max_untargeted_recipients(count_phrase) is None:
        return None
    max_recipients = None if uncapped else _max_untargeted_recipients(count_phrase)
    # The noun is always plural here ("creatures you control") - the quality
    # family's own words are singular ("a creature card"), so this
    # singularises the same simple way `_singular_card_type`'s own callers
    # already do for a mass battlefield clause's plural subject.
    quality = match.group("quality").removesuffix("s")
    if not _search_quality_is_readable(quality):
        return None
    matches = _quality_matcher(quality)

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        candidates = [
            permanent
            for permanent in game.permanents_controlled_by(controller.username)
            if matches(permanent)
        ]
        if not candidates:
            return
        limit = len(candidates) if max_recipients is None else min(max_recipients, len(candidates))
        source = (
            stack_object.name if isinstance(stack_object, CardState) else stack_object.source_name
        )
        chosen_ids = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=controller.username,
                prompt=(
                    f"choose up to {limit} {quality}(s) you control to distribute counters among"
                ),
                source=source,
                source_id=source_id_of(stack_object),
                amount=limit,
                exact=False,
                cards=tuple(permanent.id for permanent in candidates),
                card_labels=tuple(permanent.name for permanent in candidates),
                default_cards=tuple(permanent.id for permanent in candidates[:limit]),
            )
        )
        assert isinstance(chosen_ids, tuple)
        if not chosen_ids:
            return
        by_id = {permanent.id: permanent for permanent in candidates}
        chosen = [by_id[card_id] for card_id in chosen_ids if card_id in by_id]
        shares = _divided_damage_shares(amount, len(chosen), None)
        for permanent, share in zip(chosen, shares, strict=True):
            if share > 0:
                game.add_counters(permanent, kind, share)

    return effect


# --------------------------------------------------------------------------
# W7a: put N counters on *this* permanent, or untap it - CR 602.2's activated
# ability naming no target at all, only itself (CR 113.7a's own object).
# Walking Ballista's "{4}: Put a +1/+1 counter on this creature." and Devoted
# Druid's "Put a -1/-1 counter on this creature: Untap this creature." are
# both this shape: a plain self-reference, never a "target", so
# `_parse_targeted_clause`'s whole `TargetedClause` family (which always reads
# a target off `game.resolve_targets`) is the wrong tool - these two read
# `ability.source(game)` instead, the same self lookup `damage_each_opponent`
# and `_parse_destroy_each_clause` already use for a source-only effect with
# nothing to target.
# --------------------------------------------------------------------------

#: "Put N `<kind>` counter(s) on this `<noun>`." - the self-referential twin of
#: `_COUNTER_TARGET_RE`'s "on target X" and `_COUNTER_EACH_GROUP_RE`'s "on each
#: `<group>` you control". `<noun>` is any word ("creature", "artifact",
#: "permanent") - the source's own name has already been normalised to "this
#: permanent" by `_self_normalized_effect_text` by the time this ever runs, so
#: a card that prints its own name instead of "this" (The Filigree Sylex, and
#: Grist, the Hunger Tide's own "+1") reads exactly the same way. "That many"
#: (Marauding Mako's "Whenever you discard one or more cards, put that many
#: +1/+1 counters on this creature.", The Millennium Calendar's own untap-step
#: trigger) is CR 607.1's anaphora back to this same ability's triggering
#: event, read by `that_many`.
_COUNTER_ON_SELF_RE = re.compile(
    rf"^put (?P<n>{COUNT}|x|that many) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on this \w+"
    rf"{where_x_pattern('expr')}\.?$",
    re.IGNORECASE,
)

#: "Put `<n1>` `<kind1>` counter(s) and `<n2>` `<kind2>` counter(s) on this
#: `<noun>`." - Captain Marvel, Earth's Protector's own power-up effect
#: ("Put a +1/+1 counter and an indestructible counter on Captain Marvel.")
#: and Quicksilver, Brash Blur's ("Put a +1/+1 counter and a double strike
#: counter on Quicksilver.") - both keyword counters (CR 122.1a/122.1b),
#: placed by one instruction (CR 608.2c). Read whole, ahead of
#: `_CLAUSE_SEPARATOR`'s own bare " and " split, which would otherwise cut
#: "counter" away from "on this permanent" and leave both fragments
#: unreadable - neither carries a verb, and neither names a target.
_TWO_COUNTERS_ON_SELF_RE = re.compile(
    rf"^put (?P<n1>{COUNT}) (?P<kind1>\+1/\+1|-1/-1|[a-z]+(?: [a-z]+)?) counters? "
    rf"and (?P<n2>{COUNT}) (?P<kind2>\+1/\+1|-1/-1|[a-z]+(?: [a-z]+)?) counters? "
    r"on this \w+\.?$",
    re.IGNORECASE,
)


def _parse_two_counters_on_self_clause(text: str, *, for_spell: bool) -> AbilityEffect | None:
    """`_TWO_COUNTERS_ON_SELF_RE`'s shape - see its own docstring.

    Ability-only (CR 122.1: a counter marks a permanent, and a resolving
    spell is never one) - the same restriction `_parse_put_counters_on_self_
    clause` already draws for its single-counter shape, and `ability.
    source(game)` is the identical "this permanent" self-lookup that
    function and `_parse_self_fights_target_clause` both already use.
    """
    if for_spell:
        return None
    match = _TWO_COUNTERS_ON_SELF_RE.fullmatch(text.strip())
    if match is None:
        return None
    n1 = parse_count(match.group("n1"))
    n2 = parse_count(match.group("n2"))
    if n1 is None or n2 is None or n1 <= 0 or n2 <= 0:
        return None
    kind1 = _counter_kind(match.group("kind1"))
    kind2 = _counter_kind(match.group("kind2"))

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        game.add_counters(source, kind1, n1)
        game.add_counters(source, kind2, n2)

    return effect


@ABILITY_TEXT.rung("s26")
def _parse_put_counters_on_self_clause(text: str) -> AbilityEffect | None:
    """`_COUNTER_ON_SELF_RE`'s shape - Walking Ballista's `{4}` ability and
    The Filigree Sylex's `{T}` ability (CR 122.1), Heroes' Bane's own
    "Put X +1/+1 counters on this creature, where X is its power", and
    Marauding Mako's/The Millennium Calendar's "that many" off the untap-step
    trigger's own count.

    CR 113.7a: an ability existing "independently of its source"'s object can
    still be found by id in whatever zone it now occupies, but only a
    permanent still on the battlefield can receive a counter (CR 122.1: a
    counter marks a permanent, and one that left the battlefield is a new
    object with no counters to add to; `CardState.move_to` already clears them
    on the way out).

    "X, where X is `<expr>`" reads `<expr>` through the shared `amount_
    expression`; an expression it cannot read fails closed with an
    `UnreadableCounterAmountNotice`. "That many" whose triggering event
    carries no count fails closed the same way with an
    `UnmodeledTriggerEffectNotice` instead of guessing a number - "unreadable
    is not the same as no effect".
    """
    match = _COUNTER_ON_SELF_RE.fullmatch(text.strip())
    if match is None:
        return None
    n_text = match.group("n").lower()
    kind = _counter_kind(match.group("kind"))
    expr = match.group("expr")
    that_many_count = n_text == "that many"
    reader: AmountReader | None = None
    fixed_amount: int | None = None
    if not that_many_count:
        if n_text == "x":
            if expr is None:
                return None
            reader = amount_expression(expr)
        else:
            fixed_amount = parse_count(n_text)

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        if that_many_count:
            count = _that_many_or_notice(
                game,
                text,
                source_id=ability.source_id,
                source_name=ability.source_name,
                stack_object=ability,
            )
            if count is None:
                return
            amount = count
        elif fixed_amount is not None:
            amount = fixed_amount
        elif reader is None:
            game.unreadable_counter_amount_notices.append(
                UnreadableCounterAmountNotice(
                    source_id=ability.source_id,
                    source_name=ability.source_name,
                    text=text.strip(),
                    expression=(expr or "").strip(),
                )
            )
            return
        else:
            amount = max(reader(game, ability.controller, source, ability.x_value), 0)
        if amount > 0:
            game.add_counters(source, kind, amount)

    return effect


#: "Put up to `<n>` `<kind>` counter(s) on this `<noun>`. This ability can't
#: cause the total number of `<kind>` counter(s) on this `<noun>` to be
#: greater than `<cap>`." - Clockwork Steed's own `{X}, {T}` ability (the
#: trailing "Activate only during your upkeep." is a separate activation-
#: timing restriction, already stripped by `_TRAILING_ACTIVATION_TIMING_
#: RESTRICTION_RE` before `activated_effect_for` ever hands this text here).
#: `<n>` reaches this reader as a real number - `activated_effect_for`
#: substitutes the announced X (CR 107.3a) for a literal "X" before this
#: dispatcher ever sees the text, the same substitution every other X-cost
#: activated ability in this pool already goes through.
#:
#: Clockwork Beast/Clockwork Avian/Clockwork Swarm print the identical
#: template with a different starting count and a different printed cap
#: ("seven"), so both numbers are read generally rather than pinned to
#: Steed's own "four" - none of the three is legal in Modern, Pioneer, or
#: Standard (Scryfall legalities checked this session), so Clockwork Steed
#: is this reader's only in-format proof; the generality is in the grammar
#: itself (any counter kind, any cap) rather than a second pool card.
#:
#: "Up to N" (CR 608.2d) always permits choosing fewer, including none - the
#: controller's own real choice, per Clockwork Steed's own Scryfall ruling
#: (2008-10-01): "When Clockwork Steed's last ability resolves, you can
#: choose to put fewer than X +1/+0 counters on it." Asked through `Game.
#: choose_an_amount` rather than defaulted to the ceiling the way `_parse_
#: remove_up_to_n_counters_from_target_clause`'s own "remove up to N
#: counters" always takes the maximum - fewer counters removed is never
#: better than more, but fewer counters *added* can matter (a threshold the
#: controller does not want crossed yet), so this is not that shape's twin.
#: Any "+X/+Y"/"-X/-Y"-shaped counter kind (CR 122.1a's own open-ended
#: numbers, never just the ±1/±1 pair `_COUNTER_ON_SELF_RE`'s own `kind`
#: group is fitted to) or a plain named kind ("charge").
_PT_OR_NAMED_COUNTER_KIND = r"[+-]\d+/[+-]\d+|[a-z]+"

_PUT_UP_TO_N_COUNTERS_ON_SELF_CAPPED_RE = re.compile(
    rf"^put up to (?P<n>{COUNT}) (?P<kind>{_PT_OR_NAMED_COUNTER_KIND}) counters? on this \w+\.\s*"
    rf"this ability can'?t cause the total number of "
    rf"(?P<kind2>{_PT_OR_NAMED_COUNTER_KIND}) counters? "
    rf"on this \w+ to be greater than (?P<cap>{COUNT})\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s26")
def _parse_put_up_to_n_counters_on_self_capped_clause(text: str) -> AbilityEffect | None:
    """`_PUT_UP_TO_N_COUNTERS_ON_SELF_CAPPED_RE`'s shape; see the banner
    above."""
    match = _PUT_UP_TO_N_COUNTERS_ON_SELF_CAPPED_RE.fullmatch(text.strip())
    if match is None:
        return None
    limit = parse_count(match.group("n"))
    cap = parse_count(match.group("cap"))
    if limit is None or cap is None or limit < 0 or cap < 0:
        return None
    kind = _counter_kind(match.group("kind"))
    if kind != _counter_kind(match.group("kind2")):
        return None  # the two sentences name different counter kinds
    kind_word = match.group("kind")

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        room = max(cap - source.counter_count(kind), 0)
        ceiling = min(limit, room)
        if ceiling <= 0:
            return
        amount = game.choose_an_amount(
            game.controller_of(ability),
            ceiling,
            source=ability.source_name,
            source_id=source_id_of(ability),
            prompt=f"choose how many {kind_word} counters to put on {source.name}",
        )
        if amount > 0:
            game.add_counters(source, kind, amount)

    return effect


#: "Put `<self>` into its owner's library `<ordinal>` from the top." -
#: Borborygmos and Fblthp's own `{1}{U}` ability, self-referential the way
#: `_COUNTER_ON_SELF_RE` is: `<self>` is whatever `_self_normalized_effect_
#: text` has already turned the card's own printed name into ("this
#: permanent"/"this creature") for an ability read off the battlefield, or
#: the literal printed "this card" for one read off the graveyard - Bookwurm
#: and Screaming Swarm both activate their identical library-placement
#: ability from there, where CR 110.4a's "permanent" is not even true of the
#: source yet. "Its owner's"/"your" library are the same library either way
#: (CR 108.3, CR 400.1) - Borborygmos prints the first, Bookwurm and
#: Screaming Swarm the second. CR 401.2 keeps the rest of the library's own
#: order; nothing else in it moves. Read by `_parse_dead_object_to_library_
#: clause` (below, in the dead-self family) rather than a reader of its own -
#: see that function's own docstring for why one reader now covers both this
#: self-referential activated shape and a dies trigger's own "it".


#: "Put a +1/+1 counter on it. Then if it has exactly four +1/+1 counters on
#: it, `<instruction>`" - Ayara's Oathsworn's whole trigger effect, behind its
#: own intervening *if* (which `machines/triggers.py` reads separately, CR
#: 603.4).
#:
#: Read as one paragraph rather than as two independent clauses, and matched
#: against the *whole*, unsplit effect text, for two reasons:
#:
#: - The leading "it" is CR 607.1's within-one-ability anaphora back to the
#:   ability's own source, and there is nothing in a lone clause "put a +1/+1
#:   counter on it" to say so. Reading "it" as the source is only safe when the
#:   reflexive sentence beside it says "it has ... counters on it" of the same
#:   object, which is exactly what this shape requires and a free-standing
#:   clause parser could not check.
#: - CR 608.2c - "The controller of the spell or ability follows its
#:   instructions in the order written" - is what makes the condition true at
#:   four: the counter from the first sentence is already on when the second
#:   sentence's "exactly four" is evaluated. Splitting the paragraph would let
#:   the two run in either order and quietly get this wrong.
#:
#: "Exactly", "at least" and "fewer than" are all read, because the shape is
#: the reflexive check, not the one comparison this card happens to print.
_PUT_COUNTER_ON_SELF_THEN_IF_COUNT_RE = re.compile(
    rf"^put (?P<n>{COUNT}) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on (?:it|this \w+)\.\s*"
    rf"then if it has (?P<comparison>exactly|at least|fewer than|more than) "
    rf"(?P<threshold>{COUNT}) (?P<other_kind>\+1/\+1|-1/-1|[a-z]+) counters? on it, "
    r"(?P<rest>.+)$",
    re.IGNORECASE | re.DOTALL,
)

#: The comparisons `_PUT_COUNTER_ON_SELF_THEN_IF_COUNT_RE` reads, as plain
#: arithmetic on the count CR 122.1's counters give the permanent right now.
_COUNTER_COUNT_COMPARISONS: dict[str, Callable[[int, int], bool]] = {
    "exactly": lambda have, want: have == want,
    "at least": lambda have, want: have >= want,
    "fewer than": lambda have, want: have < want,
    "more than": lambda have, want: have > want,
}


@ABILITY_TEXT.rung("s26")
def _parse_put_counter_on_self_then_if_count_clause(text: str) -> AbilityEffect | None:
    """`_PUT_COUNTER_ON_SELF_THEN_IF_COUNT_RE`'s shape - Ayara's Oathsworn.

    Fail-closed on the trailing instruction: if `parse_mixed_effect` cannot
    read what follows the condition, the counter placement in front of it does
    not run either. CR 608.2c has no notion of half an instruction, and a
    counter placed with the search silently skipped is a wrong game state that
    looks like a right one - the more so here, where the counter is what makes
    the condition true.

    A source that has left the battlefield receives nothing and the condition
    is false: CR 122.1 marks a permanent, and a card that changed zones is a
    new object with no counters (`CardState.move_to` clears them).
    """
    match = _PUT_COUNTER_ON_SELF_THEN_IF_COUNT_RE.fullmatch(collapsed(text))
    if match is None:
        return None
    if match.group("kind").lower() != match.group("other_kind").lower():
        # The condition asks about a different kind of counter than the one
        # just placed. A real card could print that; nothing in the pool does,
        # and reading it would need the two kinds tracked apart here, so it
        # fails closed rather than being answered with the wrong count.
        return None
    amount = parse_count(match.group("n"))
    threshold = parse_count(match.group("threshold"))
    kind = _counter_kind(match.group("kind"))
    compare = _COUNTER_COUNT_COMPARISONS[match.group("comparison").lower()]
    rest = parse_mixed_effect(match.group("rest").strip())
    if rest is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        game.add_counters(source, kind, amount)
        if compare(source.counters[kind], threshold):
            rest(game, ability)

    return effect


#: CR 701.46a: "'Adapt N' means 'If this permanent has no +1/+1 counters on
#: it, put N +1/+1 counters on it.'" A keyword action (CR 701), not a keyword
#: ability - the printed line is just "Adapt N.", the whole conditional
#: sentence being the reminder text substituted in. Basking Broodscale's
#: "{1}{G}: Adapt 1." is the pool's only printing.
_ADAPT_RE = re.compile(r"^adapt (?P<n>\d+)\.?$", re.IGNORECASE)


@ABILITY_TEXT.rung("s26")
def _parse_adapt_clause(text: str) -> AbilityEffect | None:
    """CR 701.46a's "Adapt N" - see `_ADAPT_RE`.

    Read off the ability's own printed text with no per-card row: any future
    "Adapt N" printing reaches this the same way. The condition is checked at
    resolution - CR 701.46a's own "if this permanent has no +1/+1 counters on
    it" - so a permanent that already carries a +1/+1 counter is untouched,
    not merely reduced by the difference.
    """
    match = _ADAPT_RE.fullmatch(text.strip())
    if match is None:
        return None
    amount = int(match.group("n"))

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        if source.counters[Counter.PLUS_ONE] > 0:
            return
        game.add_counters(source, Counter.PLUS_ONE, amount)

    return effect


#: CR 701.63a: "Certain abilities instruct a permanent to endure N. To do so,
#: that permanent's controller creates an N/N white Spirit creature token
#: unless they put N +1/+1 counters on that permanent." A keyword action
#: (CR 701), read the same way `_ADAPT_RE` is - off the ability's own printed
#: sentence, whether it names itself ("this creature") or reads back the
#: trigger's own subject ("it", Fortress Kin-Guard's own ETB). `\d+` rather
#: than a bare `X` is deliberate: `activated_effect_for` already substitutes
#: an announced `X` (CR 107.3a) into the text before trying this, the same
#: convention `_ADAPT_RE` and every other keyword-action regex in this module
#: hold themselves to, so Krumar Initiate's "This creature endures X." is
#: read as a real number by the time this ever sees it.
_ENDURE_RE = re.compile(
    r"^(?:this (?:creature|permanent)|it) endures? (?P<n>\d+)\.?$", re.IGNORECASE
)


@ABILITY_TEXT.rung("s26")
def _parse_endure_clause(text: str) -> AbilityEffect | None:
    """CR 701.63a's "endure N" - see `_ENDURE_RE`.

    CR 701.63b: "If a permanent is instructed to endure 0, nothing happens.
    No counters are put on that permanent and no tokens are created" - read
    first, before any decision is asked, so declining nothing is not offered
    as a choice at all.

    The choice between the token and the counters is the controller's own
    ("unless they put N counters", CR 701.63a) - `DecisionKind.MAY` (CR
    608.2d), the same primitive `_parse_conditional_sacrifice_clause` and
    every other "unless"/"you may instead" clause in this module already use.
    Declining creates the token (the sentence's own default action); taking
    the "may" puts the counters on instead. The token is built through
    `_parse_token_clause`, the same general "create an N/N `<color>`
    `<subtype>` creature token" reader every other token-creating clause in
    the module goes through, rather than a bespoke `TokenDefinition` here.
    """
    match = _ENDURE_RE.fullmatch(text.strip())
    if match is None:
        return None
    amount = int(match.group("n"))
    token_clause = _parse_token_clause(
        f"a {amount}/{amount} white Spirit creature token", for_spell=False
    )

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        if amount <= 0:
            return  # CR 701.63b
        decision = Decision(
            kind=DecisionKind.MAY,
            player=ability.controller,
            prompt=f"put {amount} +1/+1 counters on {source.name} instead of creating a Spirit",
            source=ability.source_name,
            source_id=source_id_of(ability),
            affirmative_is_legal=True,
        )
        if game.ask(decision):
            game.add_counters(source, Counter.PLUS_ONE, amount)
        elif token_clause is not None:
            token_clause(game, ability)

    return effect


#: CR 701.37a: "'Monstrosity N' means 'If this permanent isn't monstrous, put
#: N +1/+1 counters on it and it becomes monstrous.'" A keyword action (CR
#: 701), read off the activated ability's own printed effect text the same
#: way `_ENDURE_RE`/`_ADAPT_RE` are - never keyed to a card name, so any
#: printing whose activation cost ends in the words "Monstrosity N" reads the
#: same way. `\d+` rather than a bare `X` is the same deliberate choice
#: `_ENDURE_RE`'s own docstring explains: `activated_effect_for` already
#: substitutes an announced X (CR 107.3a) into the text before trying this,
#: so Polukranos, World Eater's own "{X}{X}{G}: Monstrosity X." is read as a
#: real number by the time this ever sees it.
_MONSTROSITY_RE = re.compile(r"^monstrosity (?P<n>\d+)\.?$", re.IGNORECASE)


@ABILITY_TEXT.rung("s26")
def _parse_monstrosity_clause(text: str) -> AbilityEffect | None:
    """CR 701.37a's "Monstrosity N" - see `_MONSTROSITY_RE`.

    `Game.become_monstrous` is the whole of CR 701.37a-c: it puts the
    counters (`Game.add_counters`, CR 122.6, replacement effects included),
    sets the `monstrous`/`monstrous_x` designation, and raises the
    `TriggerEvent.BECOMES_MONSTROUS` event - or, on an already-monstrous
    permanent, silently does none of that (CR 701.37a's own second refusal).
    Either way the *activation* stays legal, since CR 701.37a is the effect
    of the ability resolving, not a cost or a timing restriction on
    activating it - a second "Monstrosity N" activation is simply an
    ability that resolves and, this time, does nothing (CR 101.3), the same
    silent-no-op shape `Game.become_prepared`'s own second refusal already
    gives CR 722.3a's identical "can't gain this designation if it already
    has it".
    """
    match = _MONSTROSITY_RE.fullmatch(text.strip())
    if match is None:
        return None
    amount = int(match.group("n"))

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        game.become_monstrous(source, amount)

    return effect


#: "put `<n>` `<kind>` counter(s) on that `<noun>`[ for each `<expr>`]." -
#: CR 400.7 anaphora back to the trigger's own condition subject
#: (`GameEvent.subject_id`), the identical referent `_parse_untap_trigger_
#: subject_clause` already reads for "untap it" - Jiang Yanggu, Alone's own
#: "... put a +1/+1 counter on that creature for each card you've discarded
#: this turn." Not a "target" clause (CR 115.1 has nothing to check here:
#: the ability's own printed text never says "target") and not the source's
#: own "this `<noun>`" (CR 700.7) either - `that <noun>` is always whichever
#: object the trigger's condition already named.
_COUNTER_ON_TRIGGER_SUBJECT_RE = re.compile(
    rf"^put (?P<n>{COUNT}) (?P<kind>\+1/\+1|-1/-1|(?:first|double) strike|[a-z]+) "
    rf"counters? on that [a-z]+"
    rf"(?: for each (?P<each>.+))?\.?$",
    re.IGNORECASE,
)


def _parse_counter_on_trigger_subject_clause(clause: str) -> TargetedClause | None:
    """`_COUNTER_ON_TRIGGER_SUBJECT_RE`'s shape - see the banner above.

    The "for each `<expr>`" multiplier is `_for_each_multiplier`'s own
    reader, the same one `parse_clause_effect`'s "draw"/"gain life"/"lose
    life" clauses already share (CR 608.2h: the count is taken once, when
    the effect applies). A magnitude of zero (an empty count, or a fixed
    amount times a multiplier that reads zero) places no counters at all
    rather than calling `Game.add_counters` with nothing to add.
    """
    match = _COUNTER_ON_TRIGGER_SUBJECT_RE.fullmatch(clause.strip())
    if match is None:
        return None
    base = parse_count(match.group("n"))
    if base is None:
        return None
    kind = _counter_kind(match.group("kind"))
    each = match.group("each")
    multiplier = _for_each_multiplier(each) if each is not None else None
    if each is not None and multiplier is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        if not isinstance(stack_object, AbilityOnStack):
            return
        event = stack_object.event
        if event is None or event.subject_id is None:
            return
        subject = game.find_by_id(event.subject_id)
        if subject is None or subject.zone is not Zone.BATTLEFIELD:
            return
        amount = base
        if multiplier is not None:
            amount *= multiplier(game, stack_object.controller, source_id_of(stack_object))
        if amount > 0:
            game.add_counters(subject, kind, amount)

    return effect


#: "put `<n>` `<kind>` counter(s) on it." as a triggered ability's whole
#: instruction - Predator Ooze's "Whenever this creature attacks, put a +1/+1
#: counter on it.", Gleam of Battle's "Whenever a creature you control
#: attacks, put a +1/+1 counter on it." Nothing earlier in the effect text
#: for "it" to point back to, so it is the object the trigger's own condition
#: named (`GameEvent.subject_id`: the attacker, CR 508.1), the referent
#: `_parse_untap_trigger_subject_clause` reads for "untap it". Tried only
#: after every clause pair has declined the text (`_parse_mixed_clauses`
#: pairs first), so an "it" with an antecedent in its own sentence list
#: never reaches here.
_COUNTER_ON_IT_TRIGGER_SUBJECT_RE = re.compile(
    rf"^put (?P<n>{COUNT}) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on it\.?$",
    re.IGNORECASE,
)


def _parse_counter_on_it_trigger_subject_clause(clause: str) -> TargetedClause | None:
    """`_COUNTER_ON_IT_TRIGGER_SUBJECT_RE`'s shape - a subject that has left
    the battlefield (CR 400.7) gets nothing and nothing else is picked."""
    match = _COUNTER_ON_IT_TRIGGER_SUBJECT_RE.fullmatch(clause.strip())
    if match is None:
        return None
    amount = parse_count(match.group("n"))
    if amount is None:
        return None
    kind = _counter_kind(match.group("kind"))

    def effect(game: "Game", stack_object: "StackObject") -> None:
        if not isinstance(stack_object, AbilityOnStack):
            return
        event = stack_object.event
        if _only_intervening_if_names_source(stack_object):
            # "Whenever you cast a noncreature spell, if this Spacecraft isn't
            # a creature, put two charge counters on it." (Romulan
            # Bird-of-Prey): the nearest antecedent of "it" is the source the
            # "if" names, not the spell the trigger condition is about.
            subject = stack_object.source(game)
        elif event is not None and _damage_recipient_is_its_subject(stack_object):
            subject = game.find_by_id(event.target_id)
        elif event is not None and event.subject_id is not None:
            subject = game.find_by_id(event.subject_id)
        elif _names_its_source(stack_object):
            # "At end of combat, if this Vehicle attacked or blocked this
            # combat, put a velocity counter on it." (Daredevil Dragster): a
            # step trigger has no event subject, so "it" is the only object
            # the ability has named - its own source (CR 608.2c).
            subject = stack_object.source(game)
        else:
            return
        if not isinstance(subject, CardState) or subject.zone is not Zone.BATTLEFIELD:
            return
        if amount > 0:
            game.add_counters(subject, kind, amount)

    return effect


def _only_intervening_if_names_source(ability: AbilityOnStack) -> bool:
    """Whether the intervening "if" names the source by CR 700.7's "this [type]"
    while the trigger condition itself does not."""
    printed = ability.ability
    if not isinstance(printed, TriggeredAbility) or not printed.intervening_if:
        return False
    return has_self_reference_type_word(
        printed.intervening_if.lower()
    ) and not has_self_reference_type_word((printed.condition or "").lower())


def _names_its_source(ability: AbilityOnStack) -> bool:
    """Whether a triggered ability's own trigger condition or intervening
    "if" names its source by CR 700.7's "this [type or subtype]" ("this
    Vehicle", "this creature"; never "this turn" or "this way") - the antecedent
    a later bare "it" then refers to."""
    printed = ability.ability
    if not isinstance(printed, TriggeredAbility):
        return False
    words = f"{printed.condition or ''} {printed.intervening_if or ''}".lower()
    return has_self_reference_type_word(words)


#: "Remove a time counter from this card." - Greater Gargadon's own second
#: ability, CR 702.62a's second ability spelled out on the card itself rather
#: than left to suspend's own reminder text. Unlike `_COUNTER_ON_SELF_RE`
#: above, this source is never on the battlefield when the ability resolves -
#: `machines.abilities._activated_ability_zone` reads the card's own
#: "Activate only if this card is suspended" restriction as CR 702.62b's
#: proof the source functions from exile - so there is no battlefield gate
#: to check here.
#: The counter count is read through `numbers.COUNT` rather than pinned to
#: Greater Gargadon's own "a", so a future card removing more than one time
#: counter this way reads for free.
_REMOVE_TIME_COUNTER_SELF_RE = re.compile(
    rf"^remove {count_pattern('n')} time counters? from this (?:card|permanent)\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s28")
def _parse_remove_time_counter_from_self_clause(text: str) -> AbilityEffect | None:
    """`_REMOVE_TIME_COUNTER_SELF_RE`'s shape - Greater Gargadon's suspend-
    only sacrifice ability (CR 702.62a, CR 702.62b).

    Reuses `machines.casting.remove_suspend_time_counter` rather than a
    second counter-removal path, so a card whose own printed ability takes a
    time counter off this way is read by the identical CR 702.62b "suspended"
    check the upkeep trigger already uses - a card that is not actually
    suspended (already cast, already left exile, already at zero counters) is
    left untouched rather than erroring, the same "the *if* was false" shape.

    It does **not** call `machines.casting.finish_suspend` itself any more.
    CR 702.62a's third ability - "When the last time counter is removed from
    this card, ..." - is a triggered ability like any other now, and
    `remove_suspend_time_counter` raises its trigger condition
    (`ExtraTriggerEvent.LAST_TIME_COUNTER_REMOVED`) when the count reaches
    zero, whichever route emptied the card. Calling `finish_suspend` here as
    well would grant the same `PlayPermission` twice: once immediately, in
    the middle of this ability's own resolution, and once again when the
    triggered ability that actually owns that instruction resolves. CR 603.3
    is the reason the trigger is the right one of the two - it goes on the
    stack the next time a player would receive priority, so it can be
    responded to, rather than happening invisibly inside somebody else's
    resolution.
    """
    match = _REMOVE_TIME_COUNTER_SELF_RE.fullmatch(text.strip())
    if match is None:
        return None
    count = parse_count(match.group("n"))
    if count is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None:
            return
        for _ in range(count):
            remove_suspend_time_counter(game, source)

    return effect


#: Vampire Hexmage: "Remove all counters from target permanent." - and the
#: same sentence narrowed to one kind ("Remove all +1/+1 counters from target
#: creature."), or with CR 115.6's count words ahead of "target" (Marchesa,
#: Resolute Monarch's and Purging Stormbrood's "from up to one target ...").
#: Every counter of the kind named, or of every kind, comes off each target;
#: removing what is not there is simply nothing to remove.
_REMOVE_ALL_COUNTERS_FROM_TARGET_RE = re.compile(
    r"^remove all (?:(?P<kind>\+1/\+1|-1/-1|[a-z]+) )?counters from"
    r" (?P<phrase>(?:up to \w+ |another )?target .+?)\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s28")
@MIXED_CLAUSE.rung("s16")
def _parse_remove_all_counters_from_target_clause(text: str) -> AbilityEffect | None:
    """`_REMOVE_ALL_COUNTERS_FROM_TARGET_RE`'s shape.

    Counters are removed from the object itself, so whatever reads them next
    - a layer 4 "as long as it has a time counter on it" (impending, CR
    702.176a), a +1/+1 counter's layer 7c bonus - reads the empty count the
    next time the board is computed.
    """
    match = _REMOVE_ALL_COUNTERS_FROM_TARGET_RE.fullmatch(text.strip())
    if match is None:
        return None
    # CR 115.6: removing counters repeats itself per target, so "up to one"
    # (zero included) is the same verb.
    if not _targets_understood(match.group("phrase"), count_agnostic=True):
        return None
    kind = _counter_kind(match.group("kind")) if match.group("kind") else None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        for target in game.resolve_targets(ability):
            if not isinstance(target, CardState) or target.zone is not Zone.BATTLEFIELD:
                continue
            for each in [kind] if kind is not None else list(target.counters):
                present = target.counter_count(each)
                if present:
                    target.remove_counters(each, present)

    return effect


#: Suncleanser's first mode: "Remove all counters from target creature. It
#: can't have counters put on it for as long as this creature remains on the
#: battlefield." - the target sheds every counter, then CR 611.2b's
#: "for as long as" grant of CR 122.6's prohibition (`CANT_HAVE_COUNTERS_TEXT`,
#: read by `Game.add_counters`) lands on that same object (CR 400.7), tied to
#: the source staying the same object on the battlefield.
_REMOVE_ALL_COUNTERS_THEN_CANT_HAVE_RE = re.compile(
    r"^remove all counters from (?P<phrase>(?:up to \w+ |another )?target [^.]+?)\.\s*"
    r"(?:it|that (?:creature|permanent)) can'?t have counters put on it for as long as"
    r" this (?:creature|permanent|artifact|enchantment|land|saga) remains on the battlefield\.?$",
    re.IGNORECASE,
)


def _source_still_here(game: "Game", stack_object: "StackObject") -> CardState | None:
    """The resolving ability's source, if it is still the same object on the
    battlefield - CR 611.2b: a "for as long as" duration that never starts
    does nothing. A spell has no such source (CR 608.2h: "this creature" on a
    spell names nothing on the battlefield)."""
    if isinstance(stack_object, CardState):
        return None
    source = stack_object.source(game)
    if source is None or source.zone is not Zone.BATTLEFIELD or source.zone_change_stamp is None:
        return None
    stamp = getattr(stack_object, "source_stamp", None)
    if stamp is not None and source.zone_change_stamp != stamp:
        return None
    return source


def _parse_remove_all_counters_then_cant_have_clause(text: str) -> TargetedClause | None:
    """`_REMOVE_ALL_COUNTERS_THEN_CANT_HAVE_RE`'s shape; see the banner above."""
    match = _REMOVE_ALL_COUNTERS_THEN_CANT_HAVE_RE.fullmatch(collapsed(text.strip()))
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=True):
        return None
    from ...models.card_state import CANT_HAVE_COUNTERS_TEXT

    def effect(game: "Game", stack_object: "StackObject") -> None:
        targets = [
            target
            for target in game.resolve_card_targets(stack_object)
            if target.zone is Zone.BATTLEFIELD
        ]
        for target in targets:
            for kind in list(target.counters):
                present = target.counter_count(kind)
                if present:
                    target.remove_counters(kind, present)
        source = _source_still_here(game, stack_object)
        if source is None or source.zone_change_stamp is None:
            return
        store = continuous_effects(game)
        timestamp = store.tick()
        for target in targets:
            store.add(
                ContinuousEffect(
                    description=f"{source.name}: {target.name} can't have counters put on it",
                    layer=Layer.ABILITY,
                    timestamp=timestamp,
                    duration=Duration.FOR_AS_LONG_AS,
                    condition=RemainsOnBattlefield(
                        card_id=source.id, stamp=source.zone_change_stamp
                    ),
                    selector=only_this_incarnation(target, target.zone_change_stamp),
                    modification=grant_ability(CANT_HAVE_COUNTERS_TEXT),
                ),
                game,
            )

    return effect


#: Aether Snap: "Remove all counters from all permanents ..." - the mass twin
#: of `_REMOVE_ALL_COUNTERS_FROM_TARGET_RE`, sharing `_DESTROY_EACH_RE`'s
#: qualifier grammar (`_parse_mass_destroy_predicate`). One instruction over a
#: set snapshotted before anything changes (CR 608.2f); the counters are
#: removed (`CardState.remove_counters`), so what watches for removal sees them.
_REMOVE_ALL_COUNTERS_FROM_EACH_RE = re.compile(
    r"^remove all (?:(?P<kind>\+1/\+1|-1/-1|[a-z]+) )?counters from (?:each|all) (?P<rest>.+?)\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s35")
def _parse_remove_all_counters_from_each_clause(text: str) -> TargetedClause | None:
    """`_REMOVE_ALL_COUNTERS_FROM_EACH_RE`'s shape; see the banner above."""
    match = _REMOVE_ALL_COUNTERS_FROM_EACH_RE.fullmatch(text.strip())
    if match is None:
        return None
    predicate = _parse_mass_destroy_predicate(match.group("rest"))
    if predicate is None:
        return None
    kind = _counter_kind(match.group("kind")) if match.group("kind") else None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source = stack_object if isinstance(stack_object, CardState) else stack_object.source(game)
        chosen = [p for p in list(game.battlefield) if predicate(game, p, source)]
        for permanent in chosen:
            for each in [kind] if kind is not None else list(permanent.counters):
                present = permanent.counter_count(each)
                if present:
                    permanent.remove_counters(each, present)

    return effect


#: Mabel, Bitter Recluse: "remove up to three counters from another target
#: creature or planeswalker." - CR 122.1's counters left unnamed by kind
#: (unlike the "+1/+1"/"-1/-1" pair `_REMOVE_ALL_COUNTERS_FROM_TARGET_RE`
#: reads), and "up to N" rather than "all" (CR 115.6's own "up to" reading,
#: extended here from targets to a resolution-time amount, CR 608.2d).
#: **Scoped simplification, recorded rather than hidden**: CR 608.2d lets the
#: resolving controller choose fewer than the stated maximum; this always
#: takes the maximum available (up to N, across every kind present, largest
#: stack first) rather than asking a separate "how many" question, since no
#: `DecisionKind` exists yet for an open-ended amount unconnected to a cost.
#: Removing more counters is never illegal here (CR 122.5 has no floor), so
#: this is a real answer, just not the single most permissive one CR 608.2d
#: allows - recorded in `docs/engine-coverage.md`.
_REMOVE_UP_TO_N_COUNTERS_FROM_TARGET_RE = re.compile(
    rf"^remove up to (?P<n>{COUNT}) counters from (?P<phrase>(?:another )?target .+?)\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s28")
@MIXED_CLAUSE.rung("s16")
def _parse_remove_up_to_n_counters_from_target_clause(text: str) -> AbilityEffect | None:
    """`_REMOVE_UP_TO_N_COUNTERS_FROM_TARGET_RE`'s shape; see the banner above."""
    match = _REMOVE_UP_TO_N_COUNTERS_FROM_TARGET_RE.fullmatch(text.strip())
    if match is None:
        return None
    limit = parse_count(match.group("n"))
    if limit is None or limit < 1:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=True):
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        for target in game.resolve_targets(ability):
            if not isinstance(target, CardState) or target.zone is not Zone.BATTLEFIELD:
                continue
            from ..ep02_r1_counter_amounts import choose_counters_to_remove

            choose_counters_to_remove(game, ability, target, limit)

    return effect


#: "Remove a lore counter from target Saga you control." (Clash of the
#: Eikons), "Remove a -1/-1 counter from target creature." (Chainbreaker) -
#: CR 122.1's counters of one named kind, N of them, off one target (rechecked
#: as it resolves, CR 608.2b). A target with fewer has what it has removed
#: (CR 608.2d). Removing a lore counter triggers no chapter (CR 714.2b: a
#: chapter ability triggers on lore counters being *put* on a Saga).
_REMOVE_N_KIND_COUNTERS_FROM_TARGET_RE = re.compile(
    rf"^remove (?P<n>{COUNT}) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? from "
    r"(?P<phrase>(?:another )?target [^.]+?)\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s16", for_spell=FORWARD)
def _parse_remove_n_kind_counters_from_target_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_REMOVE_N_KIND_COUNTERS_FROM_TARGET_RE`'s shape; see the banner above."""
    stripped = collapsed(clause)
    if not stripped.lower().startswith("remove "):
        return None
    match = _REMOVE_N_KIND_COUNTERS_FROM_TARGET_RE.fullmatch(stripped)
    if match is None:
        return None
    amount = parse_count(match.group("n"))
    if amount is None or amount < 1:
        return None
    if not _targets_understood(match.group("phrase")):
        return None
    kind = _counter_kind(match.group("kind"))

    def effect(game: "Game", stack_object: "StackObject") -> None:
        # Any zone the target was legally chosen in: a suspended card's time
        # counters are removed in exile (CR 702.62a), the rest on the
        # battlefield; `resolve_targets` already dropped an illegal one.
        for target in game.resolve_targets(stack_object):
            if not isinstance(target, CardState):
                continue
            present = target.counter_count(kind)
            if present:
                target.remove_counters(kind, min(amount, present))

    return effect


#: "remove a -1/-1 counter from target creature you control and put a -1/-1
#: counter on up to one target creature defending player controls." (Decimator
#: Beetle) - the two halves each act on their own target (CR 115.1d: both
#: chosen as the ability goes on the stack, in printed order - the first
#: announced is the first phrase's), which the clause splitter
#: cannot keep apart: each half alone would act on every target. Read whole.
_REMOVE_FROM_TARGET_AND_PUT_ON_TARGET_RE = re.compile(
    rf"^remove (?P<n>{COUNT}) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? from "
    r"(?P<first>(?:another )?target [^.]+?) and put "
    rf"(?P<m>{COUNT}) (?P<put_kind>\+1/\+1|-1/-1|[a-z]+) counters? on "
    r"(?P<second>(?:up to one )?(?:another )?target [^.]+?)\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s4")
def _parse_remove_from_target_and_put_on_target_clause(text: str) -> AbilityEffect | None:
    """`_REMOVE_FROM_TARGET_AND_PUT_ON_TARGET_RE`'s shape; see the banner above."""
    stripped = collapsed(text)
    if not stripped.lower().startswith("remove ") or " and put " not in stripped.lower():
        return None
    match = _REMOVE_FROM_TARGET_AND_PUT_ON_TARGET_RE.fullmatch(stripped)
    if match is None:
        return None
    removed, put = parse_count(match.group("n")), parse_count(match.group("m"))
    if removed is None or put is None or removed < 1 or put < 1:
        return None
    first, second = match.group("first"), match.group("second")
    if not (_targets_understood(first) and _targets_understood(second, count_agnostic=True)):
        return None
    remove_kind = _counter_kind(match.group("kind"))
    put_kind = _counter_kind(match.group("put_kind"))

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        refs = list(ability.targets)
        for index, ref in enumerate(refs):
            target = game.legal_target(ability, ref)
            if not isinstance(target, CardState) or target.zone is not Zone.BATTLEFIELD:
                continue  # CR 608.2b
            if index == 0:
                present = target.counter_count(remove_kind)
                if present:
                    target.remove_counters(remove_kind, min(removed, present))
            else:
                game.add_counters(target, put_kind, put)

    return effect


#: Graft Surgeon: "When this creature dies, put its counters on up to one
#: target creature you control." - CR 109.2's "its" is the dying source, read
#: through CR 603.10a/CR 704.8's last-known-information the same way
#: `hangarback_dies` already reads `CardState.last_known_counters` for a
#: dies trigger's own count. Every kind the source carried moves, not one
#: named kind, matching the printed "its counters" (CR 122.1 leaves the kind
#: open); CR 122.5's "counter is removed from the first ... and put onto the
#: second" is what "put ... on" invokes, not two independent instructions.
#:
#: "those" (SOS's Scolding Administrator: "When this creature dies, if it had
#: counters on it, put those counters on up to one target creature.") is the
#: identical CR 400.7 anaphora back to the same dying source, spelled with a
#: demonstrative instead of the possessive - the intervening *if* ahead of it
#: is `machines/triggers.py`'s own condition to answer, already split off
#: `TriggeredAbility.effect` before this text is ever seen here.
_PUT_ITS_COUNTERS_ON_TARGET_RE = re.compile(
    r"^put (?:its|those) counters on (?P<phrase>(?:up to \S+ )?target .+)\.?$", re.IGNORECASE
)


@ABILITY_TEXT.rung("s29", for_spell=False)
def _parse_put_its_counters_on_target_clause(text: str, *, for_spell: bool) -> AbilityEffect | None:
    """`_PUT_ITS_COUNTERS_ON_TARGET_RE`'s shape; see the banner above."""
    if for_spell:
        return None
    match = _PUT_ITS_COUNTERS_ON_TARGET_RE.fullmatch(text.strip())
    if match is None:
        return None
    phrase = match.group("phrase").strip()
    if not _targets_understood(phrase, count_agnostic=True):
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None:
            return
        counters = (
            source.counters if source.zone is Zone.BATTLEFIELD else source.last_known_counters
        )
        targets = [
            target
            for target in game.resolve_targets(ability)
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
        ]
        if not targets:
            return  # CR 115.6: "up to one" chose none, or none was legal.
        target = targets[0]
        for kind in counters:
            amount = counters[kind]
            if amount:
                game.add_counters(target, kind, amount)

    return effect


#: "double the number of `<kind>` counters on `<group>`" - Kalonian Hydra's
#: own attack trigger doubles them on *every* creature its controller
#: controls, not only itself, which is why this is a group shape
#: (`_parse_put_counters_on_group_clause`'s own "each creature you control"
#: vocabulary) rather than the self-only `_COUNTER_ON_SELF_RE` above. CR
#: 701.10e: "To double the number of a kind of counters on a player or
#: permanent, give that player or permanent as many of those counters as
#: that player or permanent already has" - read here as one `add_counters`
#: call per qualifying permanent, for however many it already carries (zero
#: is a legal, silent no-op: doubling zero counters gives zero more).
_DOUBLE_COUNTERS_ON_GROUP_RE = re.compile(
    r"^double the number of (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters on "
    r"(?:this \w+|each (?P<group>creature|artifact|permanent) you control)\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s28")
def _parse_double_counters_on_group_clause(text: str) -> AbilityEffect | None:
    """`_DOUBLE_COUNTERS_ON_GROUP_RE`'s shape - Kalonian Hydra's "double the
    number of +1/+1 counters on each creature you control" (CR 701.10e).

    Reads the group off the *computed* board (CR 613.5), the same
    "you control" reading `_parse_put_counters_on_group_clause` already
    applies, so a permanent turned into a creature this turn is doubled too
    and one that stopped being one is not. "This `<noun>`" (no group named at
    all) doubles only the source itself, since the regex's other branch
    requires the "each ... you control" wording explicitly.
    """
    match = _DOUBLE_COUNTERS_ON_GROUP_RE.fullmatch(text.strip())
    if match is None:
        return None
    kind = _counter_kind(match.group("kind"))
    group_word = match.group("group")

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        if group_word is None:
            source = ability.source(game)
            targets = [source] if source is not None and source.zone is Zone.BATTLEFIELD else []
        else:
            board = game.computed_board()
            targets = [
                permanent
                for permanent in game.permanents_controlled_by(ability.controller)
                if Type.CREATURE in board.of(permanent).types
            ]
        for permanent in targets:
            key = kind if isinstance(kind, str) else kind.value
            current = permanent.counters[key]
            if current:
                game.add_counters(permanent, kind, current)

    return effect


#: "Whenever you cast a creature spell, put X `<kind>` counters on target
#: `<X>`, where X is that spell's mana value." - Dancing from Dark to Dawn's
#: own cast trigger. `_COUNTER_TARGET_RE` just above only ever reads a fixed
#: `COUNT` word for `n` (CR 107.3a's own announced X, when there is one, is
#: substituted into a literal number by `effect_for`/`trigger_effect_for`
#: before either parser is tried), so a bare "X" left in the text always
#: means CR 107.3f's *other* X - one the sentence itself defines - and here
#: it is defined by CR 400.7's anaphora back to "that spell", the very spell
#: whose casting made this CAST_SPELL-conditioned ability trigger, not a
#: game-wide count `count_expression` could evaluate on its own. The same
#: "that spell" reading `_parse_counter_that_spell_clause` and `_parse_
#: counter_then_create_tokens_by_mana_value_pair` already give through
#: `ability.event.subject_id`.
_PUT_COUNTERS_ON_TARGET_BY_THAT_SPELLS_MANA_VALUE_RE = re.compile(
    r"^put x (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on (?P<phrase>.*target.+?),?"
    r"\s*where x is that spell'?s mana value\.?$",
    re.IGNORECASE,
)


def _parse_put_counters_on_target_by_that_spells_mana_value_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_PUT_COUNTERS_ON_TARGET_BY_THAT_SPELLS_MANA_VALUE_RE`'s shape.

    Ability-only: "that spell" resolves only against `ability.event`, the
    same restriction `_parse_counter_that_spell_clause` already holds itself
    to - a spell being cast has no `.event` of its own to read "that spell"
    against.

    The mana value is CR 202.3's own, read off the cast spell's still-live
    `CardState.card.cmc` (CR 400.7: the spell has not left the stack merely
    because this trigger is resolving above it) rather than a snapshot -
    nothing between the cast and this resolution can change what a card's own
    mana value is. A spell that has already left the stack by the time this
    resolves (countered, or - impossible for a creature spell - already
    resolved) leaves nothing to read and places no counters, the same
    "nothing left to act on" outcome `_parse_counter_that_spell_clause`
    reaches for a target already gone.
    """
    if for_spell:
        return None
    match = _PUT_COUNTERS_ON_TARGET_BY_THAT_SPELLS_MANA_VALUE_RE.fullmatch(clause.strip())
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=True):
        return None
    kind = _counter_kind(match.group("kind"))

    def effect(game: "Game", stack_object: "StackObject") -> None:
        ability = stack_object
        assert isinstance(ability, AbilityOnStack)
        event = ability.event
        if event is None or event.subject_id is None:
            return
        spell = game.find_by_id(event.subject_id)
        if spell is None:
            return
        mana_value = int(spell.card.cmc)
        if mana_value <= 0:
            return
        for target in game.resolve_targets(stack_object):
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD:
                game.add_counters(target, kind, mana_value)

    return effect


#: Swallow Whole: "Put a +1/+1 counter on the creature tapped to pay this
#: spell's additional cost." Not a target of this sentence at all (CR 118.8a:
#: the additional cost - "tap an untapped creature you control" - was chosen
#: and paid before the spell was even put on the stack, CR 601.2h), so
#: `_COUNTER_TARGET_RE`'s "target ..." shape does not match and should not:
#: this reads the same `Game.cast_record(spell).additional_cost_cards`
#: `_deal_damage_equal_to_sacrificed_creature_power` already reads for Fling.
#: The creature stays on the battlefield (only tapped, not sacrificed), so
#: `game.find_by_id` reaches it with no zone lookup needed.
_COUNTER_ON_ADDITIONAL_COST_CARD_RE = re.compile(
    rf"^put (?P<n>{COUNT}) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on the "
    r"(?:creature|permanent|card) (?:tapped|sacrificed|exiled|discarded) to pay "
    r"this spell'?s additional cost\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s24")
def _parse_counter_on_additional_cost_card_clause(clause: str) -> TargetedClause | None:
    """`_COUNTER_ON_ADDITIONAL_COST_CARD_RE`'s shape, or `None` if not it."""
    match = _COUNTER_ON_ADDITIONAL_COST_CARD_RE.fullmatch(clause.strip())
    if match is None:
        return None
    amount = parse_count(match.group("n"))
    if amount is None:
        return None
    kind = _counter_kind(match.group("kind"))

    def effect(game: "Game", stack_object: "StackObject") -> None:
        record = game.cast_record(stack_object)
        if not record.additional_cost_cards:
            return
        card_state = game.find_by_id(record.additional_cost_cards[0])
        if card_state is not None:
            # Through `Game.add_counters`, not `CardState.add_counters`: CR
            # 122.6 - "Some spells and abilities refer to counters being put on
            # an object" - and a counter placed straight onto the `CardState`
            # raises no event, so every "whenever one or more counters are put
            # on" ability was blind to this clause. CR 603.2c makes the whole
            # instruction one occurrence ("An ability triggers only once each
            # time its trigger event occurs"), which is what one call with the
            # full `amount` gives.
            game.add_counters(card_state, kind, amount)

    return effect


#: Nick Fury, Agent of S.H.I.E.L.D.'s own power-up effect: "Put two +1/+1
#: counters on this permanent, then look at the top seven cards of your
#: library. You may put a Hero, Equipment, or Vehicle card from among them
#: onto the battlefield. If it's a double-faced card, you may transform it.
#: Put the rest on the bottom of your library in a random order." - the
#: identical impulsive-look-and-put shape `_LOOK_TOP_N_MAY_BATTLEFIELD_
#: CREATURE_BONUS_RE` reads for Turntimber Symbiosis, plus a leading
#: self-counter clause the "then" joins into the same instruction (CR
#: 608.2c) and a trailing optional transform (CR 701.27a) for the card just
#: put onto the battlefield. Read whole, ahead of `_CLAUSE_SEPARATOR`'s own
#: bare ", then "/" and " splits, the same reason every other multi-sentence
#: shape in this file is. `<quality>` is any comma/"or" list `_quality_
#: matcher` already reads - Hero, Equipment and Vehicle are not hardcoded
#: here, only in the card's own printed text this regex captures.
_COUNTERS_THEN_LOOK_TOP_MAY_BATTLEFIELD_TRANSFORM_RE = re.compile(
    rf"^put (?P<n>{COUNT}) \+1/\+1 counters? on this \w+, then "
    rf"look at the top (?P<look_n>{COUNT}) cards? of your library\.\s*"
    r"you may put an? (?P<quality>[a-z][a-z, ]*?) card from among them onto the battlefield\.\s*"
    r"if it'?s a double-faced card, you may transform it\.\s*"
    r"put the rest on the bottom of your library in a random order\.?$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_counters_then_look_top_may_battlefield_transform_clause(
    text: str, *, for_spell: bool
) -> AbilityEffect | None:
    """`_COUNTERS_THEN_LOOK_TOP_MAY_BATTLEFIELD_TRANSFORM_RE`'s shape - see
    its own docstring. Ability-only (the leading counter clause names "this
    permanent", CR 122.1's own permanent-only restriction every other
    self-counter reader in this file already draws).
    """
    if for_spell:
        return None
    match = _COUNTERS_THEN_LOOK_TOP_MAY_BATTLEFIELD_TRANSFORM_RE.fullmatch(text.strip())
    if match is None:
        return None
    n = parse_count(match.group("n"))
    look_n = parse_count(match.group("look_n"))
    quality = match.group("quality").strip()
    if n is None or look_n is None or n <= 0 or look_n <= 0:
        return None
    if not _card_description_is_readable(quality):
        return None
    matches_quality = _quality_matcher(quality)

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        game.add_counters(source, Counter.PLUS_ONE, n)
        controller = game.player(ability.controller)
        looked = list(controller.library[:look_n])
        candidates = [state for state in looked if matches_quality(state)]
        chosen: CardState | None = None
        if candidates and game.may(
            controller.username,
            f"put {with_indefinite_article(quality)} card onto the battlefield",
            source=ability.source_name,
            source_id=source_id_of(ability),
        ):
            decision = Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=controller.username,
                prompt=(
                    f"choose {with_indefinite_article(quality)} card to put onto the battlefield"
                ),
                source=ability.source_name,
                source_id=source_id_of(ability),
                amount=1,
                cards=tuple(state.id for state in reversed(candidates)),
            )
            chosen_ids = game.ask(decision)
            by_id = {state.id: state for state in candidates}
            chosen = by_id[chosen_ids[0]]
        rest = [state for state in looked if state is not chosen]
        if chosen is not None:
            put = game.put_onto_battlefield(chosen, controller.username)
            if put.card.layout in (Layout.TRANSFORM, Layout.MODAL_DFC) and game.may(
                controller.username,
                "transform it",
                source=ability.source_name,
                source_id=source_id_of(ability),
            ):
                transform_permanent(game, put)
        if rest:
            rng = Random(f"{game.shuffle_seed}:{game.shuffles_performed}:nick-fury-bottom")  # noqa: S311
            rng.shuffle(rest)
            for state in rest:
                controller.move(state, Zone.LIBRARY)
            game.shuffles_performed += 1

    return effect


#: "put x `<kind>` counters on target `<phrase>`, where x is `<expr>`[. If x
#: is `<threshold>` or more, that creature gains `<keyword(s)>` until end of
#: turn.]" - Proft's Eidetic Memory's own X ("the number of cards you've
#: drawn this turn minus one", no rider) and Obsessive Pursuit's identical
#: shape with the optional threshold rider. `_COUNTER_TARGET_RE`/`_PUT_
#: COUNTERS_ON_TARGET_BY_THAT_SPELLS_MANA_VALUE_RE` read a fixed count or
#: one specific X definition; this is the general "where X is `<count_
#: expression term>`" tail neither already covers, reusing the identical
#: `amount_expression` a spell's own "counters equal to X" clause already
#: evaluates.
_PUT_COUNTERS_ON_TARGET_WHERE_X_IS_RE = re.compile(
    r"^put x (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on (?P<phrase>.*target.+?),\s*"
    r"where x is (?P<expr>.+?)\."
    r"(?:\s*if x is (?:"
    r"(?P<cmp>at least|exactly|more than|less than) (?P<threshold1>[a-z0-9]+)"
    r"|(?P<threshold2>[a-z0-9]+) or (?P<cmp2>more|fewer|less|greater)"
    r"),\s*that creature gains (?P<keywords>[a-z][a-z ,]*?) until end of turn\.)?\s*$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s22")
def _parse_put_counters_on_target_where_x_is_clause(text: str) -> AbilityEffect | None:
    """`_PUT_COUNTERS_ON_TARGET_WHERE_X_IS_RE`'s shape - see its own docstring."""
    match = _PUT_COUNTERS_ON_TARGET_WHERE_X_IS_RE.fullmatch(text.strip())
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=True):
        return None
    kind = _counter_kind(match.group("kind"))
    reader = amount_expression(match.group("expr"))
    if reader is None:
        return None
    threshold_test = None
    keywords: list[str] = []
    threshold_word = match.group("threshold1") or match.group("threshold2")
    if threshold_word is not None:
        threshold = parse_count(threshold_word)
        if threshold is None:
            return None
        cmp = match.group("cmp")
        cmp2 = match.group("cmp2")
        if cmp == "at least" or cmp2 in ("more", "greater"):
            threshold_test = lambda value, threshold=threshold: value >= threshold  # noqa: E731
        elif cmp == "exactly":
            threshold_test = lambda value, threshold=threshold: value == threshold  # noqa: E731
        elif cmp == "more than":
            threshold_test = lambda value, threshold=threshold: value > threshold  # noqa: E731
        else:  # "less than", or "or fewer"/"or less"
            threshold_test = lambda value, threshold=threshold: value < threshold  # noqa: E731
        keywords_read = _split_and_validate_keywords(match.group("keywords"))
        if keywords_read is None:
            return None
        keywords = keywords_read

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.controller_of(ability).username
        targets = [
            target
            for target in game.resolve_targets(ability)
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
        ]
        if not targets:
            return
        x = reader(game, controller, targets[0], ability.x_value)
        for target in targets:
            if x > 0:
                game.add_counters(target, kind, x)
            if threshold_test is not None and threshold_test(x):
                store = game.continuous_effects
                timestamp = store.tick()
                for keyword in keywords:
                    store.add(
                        ContinuousEffect(
                            description=f"{target.name} gains {keyword}",
                            layer=Layer.ABILITY,
                            timestamp=timestamp,
                            duration=Duration.UNTIL_END_OF_TURN,
                            selector=_only(target.id),
                            modification=grant_ability(keyword),
                        )
                    )

    return effect


#: "Put a +1/+1 counter on `<object>`. If `<it>` is a[n] `<Subtype>`, put N
#: +1/+1 counters on it instead." - Blade of the Bloodchief's "equipped
#: creature ... a Vampire", Elder Cathar's "target creature you control ...
#: that creature is a Human". CR 614.1a: "instead" replaces the first
#: placement, so a creature of that subtype gets N, never one plus N. The
#: subtype is read off the computed object (CR 613.5); "equipped"/"enchanted
#: creature" is the permanent the source is attached to (CR 301.5a, CR
#: 303.4b).
_COUNTERS_MORE_IF_SUBTYPE_RE = re.compile(
    rf"^put (?P<n>{COUNT}) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on "
    r"(?P<subject>equipped creature|enchanted creature|target [^.]+?)\.\s*"
    # Wakandan Royal Guard's "If that creature is another Hero" - "another"
    # (any Hero but the ability's own source) in place of the article.
    r"if (?:equipped creature|enchanted creature|that creature|it) is "
    r"(?:an? |(?P<another>another ))"
    rf"(?P<subtype>[a-z]+), put (?P<m>{COUNT}) (?:(?:\+1/\+1|-1/-1|[a-z]+) )?counters? "
    r"on it instead\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s23")
def _parse_counters_more_if_subtype_clause(text: str) -> AbilityEffect | None:
    """`_COUNTERS_MORE_IF_SUBTYPE_RE`'s shape, ability-side."""
    match = _COUNTERS_MORE_IF_SUBTYPE_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    base, more = parse_count(match.group("n")), parse_count(match.group("m"))
    subtype = _bare_subtype_word(match.group("subtype"))
    subject = match.group("subject").lower()
    attached = subject in ("equipped creature", "enchanted creature")
    another = match.group("another") is not None
    if base is None or more is None or subtype is None:
        return None
    if not attached and not _targets_understood(match.group("subject")):
        return None
    kind = _counter_kind(match.group("kind"))

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        if attached:
            source = ability.source(game)
            if source is None or source.zone is not Zone.BATTLEFIELD:
                return
            holder_id = source.attached_to
            creature = game.find_by_id(holder_id) if holder_id is not None else None
        else:
            creature = next(
                (t for t in game.resolve_targets(ability) if isinstance(t, CardState)), None
            )
        if creature is None or creature.zone is not Zone.BATTLEFIELD:
            return
        subtypes = {word.lower() for word in game.characteristics_of(creature).subtypes}
        qualifies = subtype in subtypes and not (another and creature.id == ability.source_id)
        game.add_counters(creature, kind, more if qualifies else base)

    return effect


#: "Put N `<kind>` counters on enchanted creature." / "... on equipped
#: creature." - Krasis Incubation's "{1}{G}{U}, Return this Aura to its owner's
#: hand: Put two +1/+1 counters on enchanted creature." The creature is the
#: permanent the source is attached to, never a target (CR 303.4b, CR 301.5a),
#: read through the source's last known attachment once the cost has moved it
#: (CR 113.7a, CR 608.2h) - `continuous._attached_object`, the lookup Honest
#: Work's "tap enchanted creature" already uses. CR 122.1: a counter is placed.
_COUNTERS_ON_ATTACHED_RE = re.compile(
    rf"^put (?P<n>{COUNT}) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on "
    r"(?:enchanted|equipped|fortified) (?:creature|permanent|artifact|land)\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s23")
def _parse_counters_on_attached_clause(text: str) -> AbilityEffect | None:
    """`_COUNTERS_ON_ATTACHED_RE`'s shape. Nothing attached, or a host that has
    left the battlefield, is nothing to put counters on."""
    match = _COUNTERS_ON_ATTACHED_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    amount = parse_count(match.group("n"))
    if amount is None:
        return None
    kind = _counter_kind(match.group("kind"))

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        host = _attached_object(game, ability)
        if host is not None and amount > 0:
            game.add_counters(host, kind, amount)

    return effect


#: "Whenever equipped creature attacks, put a +1/+1 counter on that creature
#: and each other creature you control that shares a creature type with it."
#: (Invasion of New Capenna // Holy Frazzle-Cannon) - CR 702.73a's shared-type
#: comparison (`shares_creature_type`, already read for Winnowing's own "...
#: that don't share a creature type ...") applied to a counter-placement
#: group instead, with "that creature"/"it" resolved off the trigger's own
#: condition (`_attack_trigger_pump_subject`, already built for the identical
#: equipped-vs-enchanted-vs-self self-reference above) rather than off the
#: ability's own source directly - Sigil of Valor's own reason for that
#: helper existing applies here too.
_COUNTER_ON_SUBJECT_AND_SHARED_TYPE_RE = re.compile(
    rf"^put (?P<n>{COUNT}) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on that creature and each "
    r"other creature you control that shares a creature type with it\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s22")
def _parse_counter_on_subject_and_shared_type_clause(text: str) -> AbilityEffect | None:
    """`_COUNTER_ON_SUBJECT_AND_SHARED_TYPE_RE`'s shape; see the banner
    above. CR 122.1c: counters never change a creature's own types or
    subtypes, so one permanent gaining a counter mid-loop cannot make or
    unmake a different permanent's own "shares a creature type" answer -
    the same no-snapshot-needed reasoning `_parse_counter_each_creature_
    with_counter_clause` already documents for its own group loop.
    """
    match = _COUNTER_ON_SUBJECT_AND_SHARED_TYPE_RE.fullmatch(text.strip())
    if match is None:
        return None
    amount = parse_count(match.group("n"))
    if amount is None:
        return None
    kind = _counter_kind(match.group("kind"))

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        subject = _attack_trigger_pump_subject(game, ability)
        if subject is None or subject.zone is not Zone.BATTLEFIELD:
            return
        controller = game.controller_of(ability).username
        game.add_counters(subject, kind, amount)
        for permanent in list(game.battlefield):
            if permanent.id == subject.id:
                continue
            if game.controller_of(permanent).username != controller:
                continue
            if not game.characteristics_of(permanent).is_creature:
                continue
            if shares_creature_type(game, subject, permanent):
                game.add_counters(permanent, kind, amount)

    return effect


#: "Put `<n>` `<kind>` counter(s) on this `<noun>`. Then if there are N or
#: more `<kind>` counters on it, `<consequences>`." - Treasure Map's "remove
#: those counters, transform this artifact, and create three Treasure
#: tokens", Ludevic's Test Subject's "remove all of them and transform it",
#: Hostile Hostel's "remove those counters, transform it, then untap it",
#: Primal Amulet's "you may remove those counters and transform it". Any
#: sentences ahead of the counter (Treasure Map's "Scry 1.") are read by the
#: ordinary clause reader first (CR 608.2c, in the order written). "It" is the
#: permanent the counter was just put on - the source itself (CR 700.7).
#:
#: The counter instruction may be a "put" or a "remove" (Thing in the Ice's
#: "remove an ice counter from this creature. Then if it has no ice counters
#: on it, transform it."), and the check reads either "there are N or more"
#: or "it has N or more" / "this `<noun>` has N or more" (The Emperor of
#: Palamecia's "Then if it has three or more +1/+1 counters on it, transform
#: it."), or "no" counters at all. The kind is a P/T pair or a word.
_COUNTER_THRESHOLD_RE = re.compile(
    r"^(?P<pre>(?:[^.]+\.\s+)*?)"
    r"(?P<put>(?:put|remove) [^.]+? (?:on|from) this (?P<noun>[a-z]+))\.\s*"
    r"then if (?:there (?:are|is)|(?:it|this (?P=noun)) has) "
    rf"(?:(?P<threshold>{COUNT}) or more|(?P<none>no)) "
    r"(?P<kind>[+-]\d+/[+-]\d+|[a-z]+) counters? on "
    r"(?:it|this (?P=noun)), (?P<rest>[^.]+)\.?$",
    re.IGNORECASE | re.DOTALL,
)
#: The consequence list's own separators: a comma (optionally ", and" /
#: ", then"), a bare " and ", a bare " then ".
_COUNTER_THRESHOLD_ITEM_SPLIT_RE = re.compile(
    r",\s*(?:and\s+|then\s+)?|\s+and\s+|\s+then\s+", re.IGNORECASE
)
_COUNTER_THRESHOLD_REMOVE_RE = re.compile(
    r"^remove (?:those(?: [a-z]+)? counters|all of them|them|all [a-z]+ counters from it)$",
    re.IGNORECASE,
)
_COUNTER_THRESHOLD_SELF_RE = re.compile(
    r"^(?P<verb>transform|untap) (?:it|this (?:creature|permanent|artifact|enchantment|land))$",
    re.IGNORECASE,
)

#: What one consequence of `_COUNTER_THRESHOLD_RE` does, given the source
#: still on the battlefield (`None` once it has left).
ThresholdConsequence = Callable[["Game", "StackObject", CardState | None], None]


def _counter_threshold_consequence(
    item: str, kind: str, *, for_spell: bool
) -> ThresholdConsequence | None:
    """One item of `_COUNTER_THRESHOLD_RE`'s consequence list, or `None` when
    no reader here knows it (which refuses the whole shape)."""
    if _COUNTER_THRESHOLD_REMOVE_RE.fullmatch(item):

        def remove(game: "Game", stack_object: "StackObject", live: CardState | None) -> None:
            if live is not None and live.counter_count(kind):
                live.remove_counters(kind, live.counter_count(kind))

        return remove
    if self_match := _COUNTER_THRESHOLD_SELF_RE.fullmatch(item):
        if self_match.group("verb").lower() == "transform":

            def transform(
                game: "Game", stack_object: "StackObject", live: CardState | None
            ) -> None:
                if live is not None:
                    transform_permanent(game, live)

            return transform

        def untap(game: "Game", stack_object: "StackObject", live: CardState | None) -> None:
            if live is not None:
                live.untap()

        return untap
    clause = _parse_mixed_clause(item, for_spell=for_spell)
    if clause is None:
        return None

    def other(game: "Game", stack_object: "StackObject", live: CardState | None) -> None:
        clause(game, stack_object)

    return other


def _parse_counter_threshold_whole_text(text: str, *, for_spell: bool) -> TargetedClause | None:
    """`_COUNTER_THRESHOLD_RE`'s shape.

    The threshold is checked once, after the counter is put on (CR 608.2c),
    against the source as it is now or, if it has left the battlefield, its
    last known information (CR 608.2h) - Treasure Map's own ruling
    (2017-09-29): a Map that left with three landmark counters still makes
    three Treasures, with nothing left to remove counters from or transform.
    A counter put on some other way never transforms it by itself: only this
    resolution checks. "Remove those counters" removes every counter of that
    kind, not only the threshold's worth (four found, four removed). A
    leading "you may" is one CR 608.2d choice over the whole list.
    """
    whole = collapsed(_strip_non_effect_preamble(text).strip())
    match = _COUNTER_THRESHOLD_RE.fullmatch(whole)
    if match is None:
        return None
    pre_text = match.group("pre").strip()
    pre = _parse_mixed_clauses(pre_text, for_spell=for_spell) if pre_text else []
    if pre is None:
        return None
    put = _parse_mixed_clause(match.group("put"), for_spell=for_spell)
    threshold = 0 if match.group("none") else parse_count(match.group("threshold"))
    # The counter instruction must be about the very kind the check counts.
    if (
        put is None
        or threshold is None
        or match.group("kind").lower() not in match.group("put").lower()
    ):
        return None
    reached: Callable[[int], bool] = (
        (lambda found: found == 0) if match.group("none") else (lambda found: found >= threshold)
    )
    kind = _counter_kind(match.group("kind"))
    rest = match.group("rest").strip()
    optional = rest.lower().startswith("you may ")
    if optional:
        rest = rest[len("you may ") :]
    items: list[ThresholdConsequence] = []
    for raw in _COUNTER_THRESHOLD_ITEM_SPLIT_RE.split(rest):
        if not raw.strip():
            continue
        consequence = _counter_threshold_consequence(raw.strip(), kind, for_spell=for_spell)
        if consequence is None:
            return None
        items.append(consequence)
    if not items:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        for clause in pre:
            clause(game, stack_object)
            game.announce_batched_events()  # CR 603.2c: one event per instruction
        put(game, stack_object)
        known: CardState | None = (
            stack_object.source_or_last_known(game)
            if isinstance(stack_object, AbilityOnStack)
            else stack_object
        )
        if known is None:
            return
        live = known if known.zone is Zone.BATTLEFIELD else None
        # CR 608.2h: a source that left the battlefield is counted as it last
        # existed there - `last_known_counters`, snapshotted on the way out.
        found = known.counters[kind] if live is not None else known.last_known_counters[kind]
        if not reached(found):
            return
        if optional:
            source = (
                stack_object.source_name
                if isinstance(stack_object, AbilityOnStack)
                else stack_object.name
            )
            if not game.may(
                game.controller_of(stack_object),
                rest,
                source=source,
                source_id=source_id_of(stack_object),
            ):
                return
        for item in items:
            item(game, stack_object, live)
            game.announce_batched_events()  # CR 603.2c: one event per instruction

    return effect


#: "Remove a `<kind>` counter from it/this creature." - Clockwork Steed's own
#: end-of-combat trigger ("... remove a +1/+0 counter from it"), Encumbered
#: Reejerey's and Bristlebane Battler's identical -1/-1 shape: CR 122.5's
#: counter removal, self-referential and for a specific count rather than
#: `_RIDER_REMOVE_ALL_COUNTERS_RE`'s "all" - the same generalization
#: `_parse_remove_time_counter_from_self_clause` already gives "remove N
#: time counters from this card/permanent", widened here from that one
#: counter kind to any named or P/T-shaped kind (the same
#: `[+-]\d+/[+-]\d+|[a-z]+` alternation other counter-kind regexes in this
#: file already read, never pinned to Clockwork Steed's own literal "+1/+0"
#: or a fixed "+1/+1"/"-1/-1" pair) and from "this card"/"this permanent" to
#: every self-reference `_SELF_ANAPHOR` reads, since nothing about the
#: mechanic is specific to time counters or to that literal wording.
_REMOVE_N_COUNTERS_FROM_SELF_RE = re.compile(
    rf"^remove {count_pattern('n')} (?P<kind>[+-]\d+/[+-]\d+|[a-z]+) counters? from "
    rf"{_SELF_ANAPHOR}\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s28")
def _parse_remove_n_counters_from_self_clause(text: str) -> AbilityEffect | None:
    """`_REMOVE_N_COUNTERS_FROM_SELF_RE`'s shape; see the banner above."""
    match = _REMOVE_N_COUNTERS_FROM_SELF_RE.fullmatch(text.strip())
    if match is None:
        return None
    count = parse_count(match.group("n"))
    if count is None:
        return None
    kind = _counter_kind(match.group("kind"))

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        present = source.counter_count(kind)
        if present:
            source.remove_counters(kind, min(count, present))

    return effect


def _parse_counter_then_referent_pair(
    first: str, second: str, *, for_spell: bool
) -> TargetedClause | None:
    """ "Counter target `<qualifier>` spell. Its controller `<referent
    clause>`." - Strix Serenade's and Swan Song's "Its controller creates a
    2/2 blue Bird creature token with flying.", An Offer You Can't Refuse's
    "Its controller creates two Treasure tokens." and Punish Ignorance's "Its
    controller loses 3 life" - as one CR 608.2c instruction pair.

    The stack-side twin of `_parse_anaphoric_clause_pair`: "its controller" is
    CR 400.7's anaphora back to the spell the first sentence targeted, never a
    target of its own, so the referent player is read off that spell *before*
    it is countered (a card in a graveyard is no spell, so CR 108.4a would
    answer its owner instead), and the second sentence is read by the same
    `_parse_referent_clause` Crib Swap's permanent-side sentence already goes
    through.

    CR 113.6g: a spell that can't be countered stays on the stack, but the
    second sentence still runs - CR 608.2b's target is legal, so the spell
    "will resolve normally", and the printed rulings for this exact template
    say so (Strix Serenade 2024-06-07, Swan Song 2013-09-15, Punish Ignorance
    2008-10-01). A target already gone from the stack is CR 608.2b's illegal
    target: no counter and no second sentence.

    Widened (ecl T7) to an *ability* with the same pair - Glen Elendra
    Guardian's "{1}{U}, Remove a counter from this creature: Counter target
    noncreature spell. Its controller draws a card." and Fear of Impostors'
    enters trigger "counter target spell. Its controller manifests dread." -
    the same CR 701.6a verb and CR 400.7 anaphora, named by the ability's
    source rather than by a spell's own name.
    """
    if not _COUNTER_TARGET_SPELL_RE.fullmatch(first.strip()):
        return None
    subject_match = _ANAPHORIC_SUBJECT_RE.fullmatch(second.strip())
    if subject_match is None:
        return None
    second_clause = _parse_referent_clause(subject_match.group("rest"))
    if second_clause is None:
        return None

    def effect(game: "Game", spell: "StackObject") -> None:
        name = spell.name if for_spell else spell.source_name  # type: ignore[union-attr]
        for reference in spell.targets:
            if not reference.is_card:
                continue
            target = next((item for item in game.stack if item.id == reference.card_id), None)
            if target is None:
                continue
            referent = game.controller_of(target)
            game.counter(target)
            second_clause(game, referent, None, name, source_id_of(spell))

    return effect


def _parse_counter_on_target_then_controller_pair(
    first: str, second: str, *, for_spell: bool
) -> TargetedClause | None:
    """ "Put a `<kind>` counter on target `<permanent>`. Its controller
    `<referent clause>`." - Gwafa Hazid's "Put a bribery counter on target
    creature you don't control. Its controller draws a card." as one CR 608.2c
    instruction pair.

    "Its controller" is CR 400.7's anaphora back to the permanent the first
    sentence targeted (the same one `_parse_anaphoric_clause_pair` reads after a
    destroy), read once the counter is on it, so a target that stopped being
    legal (CR 608.2b) leaves both sentences undone.
    """
    if " controller " not in second or " counter" not in first:
        return None
    put = _COUNTER_TARGET_RE.fullmatch(first.strip())
    subject = _ANAPHORIC_SUBJECT_RE.fullmatch(second.strip())
    if put is None or subject is None or put.group("each") is not None:
        return None
    if not second.strip().lower().startswith(("its controller", "that creature's controller")):
        return None
    amount = parse_count(put.group("n"))
    second_clause = _parse_referent_clause(subject.group("rest"))
    if amount is None or second_clause is None:
        return None
    if not _targets_understood(put.group("phrase"), count_agnostic=True):
        return None
    put_counters = put_counters_on_ability_targets(_counter_kind(put.group("kind")), amount)

    def effect(game: "Game", stack_object: "StackObject") -> None:
        name = stack_object.name if for_spell else stack_object.source_name  # type: ignore[union-attr]
        targets = [
            target
            for target in game.resolve_targets(stack_object)
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
        ]
        if not targets:
            return
        put_counters(game, stack_object)
        second_clause(game, game.controller_of(targets[0]), None, name, source_id_of(stack_object))

    return effect


#: "For each {W}{W} spent to cast this creature, `<instruction>`." (Bladecoil
#: Serpent) - the instruction runs once for each whole group of that many mana
#: of that colour in the payment of the spell this permanent was (CR 601.2h,
#: CR 400.7d; `keyword_counters.symbol_groups_spent`).
_FOR_EACH_SYMBOLS_SPENT_RE = re.compile(
    r"^for each (?P<symbols>(?:\{[wubrg]\})+) spent to cast (?:it|this creature|this spell),\s*"
    r"(?P<inner>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)
#: Clay Champion's "choose up to two other target creatures you control. For
#: each {W}{W} spent to cast this creature, put a +1/+1 counter on each of them."
_CHOOSE_THEN_COUNTERS_PER_SYMBOLS_SPENT_RE = re.compile(
    r"^choose (?P<phrase>up to [a-z]+ other target creatures you control)\.\s*"
    r"for each (?P<symbols>(?:\{[wubrg]\})+) spent to cast (?:it|this creature|this spell),\s*"
    rf"put (?P<n>{COUNT}) (?P<kind>\+1/\+1) counters? on each of them\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s28")
def _parse_for_each_symbols_spent_clause(text: str) -> AbilityEffect | None:
    """`_FOR_EACH_SYMBOLS_SPENT_RE`'s shape: the instruction is read as it would
    be on its own and run once per group spent."""
    if " spent to cast " not in text:
        return None
    match = _FOR_EACH_SYMBOLS_SPENT_RE.fullmatch(collapsed(text))
    if match is None:
        return None
    from .dispatch import _ability_effect_or_notice

    inner = _ability_effect_or_notice(match.group("inner") + ".")
    if inner is None:
        return None
    groups = symbol_groups_spent(match.group("symbols").lower())

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source_or_last_known(game)
        if source is None:
            return
        for _ in range(groups(game, ability.controller, source, 0)):
            inner(game, ability)

    return effect


@ABILITY_TEXT.rung("s28")
def _parse_choose_then_counters_per_symbols_spent_clause(text: str) -> AbilityEffect | None:
    """`_CHOOSE_THEN_COUNTERS_PER_SYMBOLS_SPENT_RE`'s shape."""
    if " spent to cast " not in text or not text.lower().startswith("choose "):
        return None
    match = _CHOOSE_THEN_COUNTERS_PER_SYMBOLS_SPENT_RE.fullmatch(collapsed(text))
    each = parse_count(match.group("n")) if match else None
    if match is None or each is None:
        return None
    groups = symbol_groups_spent(match.group("symbols").lower())
    kind = _counter_kind(match.group("kind"))

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source_or_last_known(game)
        total = each * (0 if source is None else groups(game, ability.controller, source, 0))
        if total <= 0:
            return
        for target in game.resolve_targets(ability):
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD:
                game.add_counters(target, kind, total)

    return effect


#: "Create X 1/1 colorless Thopter artifact creature tokens with flying, where
#: X is that spell's mana value." (Access Denied) - CR 107.3's X, set by the
#: very spell the paired first clause just countered, not chosen by the
#: caster. `desc`/`tail` are read exactly like `_TOKEN_CLAUSE_RE`'s own groups
#: (`_parse_generic_token_descriptor`/`_parse_token_tail`); only the leading
#: "X" and the trailing "where X is ..." are specific to this shape.
_CREATE_TOKENS_WHERE_X_IS_THAT_SPELLS_MANA_VALUE_RE = re.compile(
    r"^create x (?P<desc>.+?) \btokens?\b(?:\s+with\s+(?P<tail>.+?))?"
    r",?\s*where x is that spell'?s mana value\.?$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_counter_then_create_tokens_by_mana_value_pair(
    first: str, second: str, *, for_spell: bool
) -> TargetedClause | None:
    """ "Counter target spell. Create X ... tokens ..., where X is that
    spell's mana value." as one CR 608.2c instruction pair, or `None` if this
    shape does not match.

    CR 400.7's anaphora: "that spell" in the second sentence is whatever the
    first sentence's "target spell" found, not a target of its own - the same
    reasoning `_parse_anaphoric_clause_pair` already documents for "its
    controller ...". The mana value is read off the countered spell's own
    printed card (`CardState.card.cmc`) *before* the token count is decided,
    which only matters in that both happen in the same breath here: `Game.
    counter` never changes what `.card` reports, so the order between
    countering and reading the mana value could not produce a different
    answer either way, unlike a permanent's power or toughness once it has
    left the battlefield (see `hangarback_walkers_thopters`'s own docstring
    for why *that* one has to read `last_known_counters`).

    A target that already left the stack (CR 608.2b) is neither countered nor
    read for a mana value, and no tokens are created - there is no spell left
    to have had one.
    """
    if not for_spell:
        return None
    if not _COUNTER_TARGET_SPELL_RE.fullmatch(first.strip()):
        return None
    match = _CREATE_TOKENS_WHERE_X_IS_THAT_SPELLS_MANA_VALUE_RE.fullmatch(second.strip())
    if match is None:
        return None
    words = match.group("desc").strip().split()
    if not words:
        return None
    definition = _parse_generic_token_descriptor(words, match.group("tail"))
    if definition is None:
        return None

    def effect(game: "Game", spell: CardState) -> None:
        controller = game.controller_of(spell).username
        countered: CardState | None = None
        for reference in spell.targets:
            if not reference.is_card:
                continue
            target = next((item for item in game.stack if item.id == reference.card_id), None)
            if target is not None:
                countered = target
                game.counter(target)
        if countered is None:
            return
        mana_value = int(countered.card.cmc)
        create_tokens(game, definition, controller, mana_value)

    return effect


#: Mana Sculpt: "Counter target spell. If you control a Wizard, add an
#: amount of `<color>` equal to the amount of mana spent to cast that spell
#: at the beginning of your next main phase." "You control a Wizard" is
#: already a generic board condition (`Game.builtin_condition_holds`'s own
#: `_CONDITION_CONTROLS_A`), read here through `Game.condition_holds` like
#: every other printed "if" - no new reader for it. The mana-spent amount is
#: CR 601.2h's own already-readable condition family too
#: (`machines/conditions/cast_record`), but here it names a *number*, not a
#: boolean, so it is captured directly off the countered spell's own
#: `CastRecord` rather than through that boolean reader.
_COUNTER_THEN_CONDITIONAL_MANA_FROM_COUNTERED_RE = re.compile(
    r"^if (?P<condition>[^,]+), add an amount of \{(?P<symbol>[wubrgc])\} equal to the "
    r"amount of mana spent to cast that spell at the beginning of your next main phase$",
    re.IGNORECASE,
)


def _parse_counter_then_wizard_mana_from_countered_pair(
    first: str, second: str, *, for_spell: bool
) -> TargetedClause | None:
    """Mana Sculpt's whole text as one CR 608.2c instruction pair - see the
    banner above.

    CR 601.2h's mana spent is read off the countered spell's own `CastRecord`
    *before* `Game.counter` moves it off the stack (CR 608.2b leaves nothing
    behind to read once it has), and captured as a plain integer onto the
    delayed trigger - the same "last known information, taken now" reasoning
    `_parse_counter_then_create_tokens_by_mana_value_pair` already gives for
    a countered spell's mana value.

    "If you control a Wizard" gates whether the delayed trigger is created
    at all, checked once as this spell resolves (CR 608.2c: instructions run
    in the order written) - it is not itself a delayed condition rechecked
    at the next main phase, since the printed sentence names no "still" or
    "as long as". An unreadable condition fails closed with a
    `ConditionalClauseNotice` rather than guessing; a spell whose target
    already left the stack (CR 608.2b) is neither countered nor read for a
    mana value, and no trigger is created.
    """
    if not for_spell:
        return None
    if not _COUNTER_TARGET_SPELL_RE.fullmatch(first.strip()):
        return None
    match = _COUNTER_THEN_CONDITIONAL_MANA_FROM_COUNTERED_RE.fullmatch(second.strip().rstrip("."))
    if match is None:
        return None
    condition_text = match.group("condition").strip()
    if not _effect_condition_is_readable(condition_text):
        return None
    color = Color(match.group("symbol").upper())

    def effect(game: "Game", spell: CardState) -> None:
        controller = game.controller_of(spell)
        held = game.condition_holds(controller.username, condition_text, spell)
        if held is None:
            notice = ConditionalClauseNotice(
                source_id=spell.id, source_name=spell.card.name, text=second
            )
            if notice not in game.conditional_clause_notices:
                game.conditional_clause_notices.append(notice)
            held = False
        countered: CardState | None = None
        amount = 0
        for reference in spell.targets:
            if not reference.is_card:
                continue
            target = next((item for item in game.stack if item.id == reference.card_id), None)
            if target is None:
                continue
            record = game.cast_record_of(target)
            amount = record.total_mana_spent if record is not None else 0
            countered = target
            game.counter(target)
        if held and countered is not None:
            game.create_delayed_trigger(
                DelayedTrigger(
                    text=(
                        f"At the beginning of your next main phase, add an amount of "
                        f"{{{color.value}}} equal to the amount of mana spent to cast "
                        "that spell."
                    ),
                    effect=AddManaAmountForController(amount=amount, color=color),
                    event=TriggerEvent.BEGINNING_OF_STEP,
                    any_main_phase=True,
                    controller=controller.username,
                    source_id=spell.id,
                    source_name=spell.card.name,
                    only_when_active=controller.username,
                )
            )

    return effect


#: Plasm Capture: "Counter target spell. At the beginning of your next first
#: main phase, add X mana in any combination of colors, where X is that
#: spell's mana value." The countered spell's mana value is read the way
#: Access Denied's is (CR 400.7's "that spell", captured before the counter
#: moves it); the mana is CR 603.7's delayed trigger, at the beginning of the
#: controller's next first main phase (CR 505.1a: the precombat one) - or of
#: any next main phase when "first" is not printed - adding that many mana in
#: `_ADD_ANY_COMBINATION_MANA_RE`'s per-unit choice.
_AT_NEXT_MAIN_PHASE_ADD_RE = re.compile(
    r"^at the beginning of your next (?P<first>first )?main phase, (?P<add>add .+)$",
    re.IGNORECASE,
)
_THAT_SPELLS_MANA_VALUE_RE = re.compile(r"^that spell'?s mana value$", re.IGNORECASE)


def _parse_counter_then_delayed_any_combination_mana_pair(
    first: str, second: str, *, for_spell: bool
) -> TargetedClause | None:
    """Plasm Capture's whole text as one CR 608.2c instruction pair - see the
    banner above. A target that already left the stack (CR 608.2b) is
    neither countered nor read, and no trigger is created."""
    if not for_spell:
        return None
    if not _COUNTER_TARGET_SPELL_RE.fullmatch(first.strip()):
        return None
    timing = _AT_NEXT_MAIN_PHASE_ADD_RE.fullmatch(second.strip().rstrip("."))
    if timing is None:
        return None
    match = _ADD_ANY_COMBINATION_MANA_RE.fullmatch(timing.group("add").strip())
    if match is None or match.group("n") is None or match.group("n").lower() != "x":
        return None
    where_x = match.group("where_x")
    if where_x is None or not _THAT_SPELLS_MANA_VALUE_RE.fullmatch(where_x.strip()):
        return None
    palette_text = match.group("palette")
    palette = (
        [Color(letter) for letter in _COLOR_LETTERS]
        if palette_text.lower() == "colors"
        else [Color(symbol.upper()) for symbol in _MANA_SYMBOL_RE.findall(palette_text)]
    )
    precombat_only = timing.group("first") is not None
    trigger_text = second.strip()
    if not trigger_text.endswith("."):
        trigger_text += "."
    trigger_text = trigger_text[0].upper() + trigger_text[1:]

    def effect(game: "Game", spell: CardState) -> None:
        controller = game.controller_of(spell)
        countered: CardState | None = None
        for reference in spell.targets:
            if not reference.is_card:
                continue
            target = next((item for item in game.stack if item.id == reference.card_id), None)
            if target is None:
                continue
            countered = target
            game.counter(target)
        if countered is None:
            return
        game.create_delayed_trigger(
            DelayedTrigger(
                text=trigger_text,
                effect=AddManaInAnyCombinationForController(
                    amount=int(countered.card.cmc), palette=palette
                ),
                event=TriggerEvent.BEGINNING_OF_STEP,
                step=Step.PRECOMBAT_MAIN if precombat_only else None,
                any_main_phase=not precombat_only,
                controller=controller.username,
                source_id=spell.id,
                source_name=spell.card.name,
                only_when_active=controller.username,
            )
        )

    return effect


#: Sound the Trumpets: "Counter target spell. If that spell's mana value was
#: 2 or less, recruit." - the same "that spell" anaphora
#: `_CREATE_TOKENS_WHERE_X_IS_THAT_SPELLS_MANA_VALUE_RE` reads for Access
#: Denied, gating CR 701.70a's own keyword action instead of a token count.
_COUNTER_THEN_RECRUIT_IF_MANA_VALUE_RE = re.compile(
    r"^if that spell'?s mana value was (?P<n>\d+) or less, recruit\.?$", re.IGNORECASE
)


def _parse_counter_then_recruit_by_mana_value_pair(
    first: str, second: str, *, for_spell: bool
) -> TargetedClause | None:
    """Sound the Trumpets - see `_COUNTER_THEN_RECRUIT_IF_MANA_VALUE_RE`.

    CR 400.7's anaphora ("that spell" is whatever the first sentence's
    "target spell" found) and the mana-value-before-countering order are
    exactly `_parse_counter_then_create_tokens_by_mana_value_pair`'s own
    reasoning; only the gated instruction differs, so this reuses `_parse_
    recruit_clause`'s own effect rather than repeating CR 701.70a's draw/
    discard/token steps a second time.
    """
    if not for_spell:
        return None
    if not _COUNTER_TARGET_SPELL_RE.fullmatch(first.strip()):
        return None
    match = _COUNTER_THEN_RECRUIT_IF_MANA_VALUE_RE.fullmatch(second.strip())
    if match is None:
        return None
    threshold = int(match.group("n"))
    recruit_effect = _parse_recruit_clause("recruit", for_spell=for_spell)
    assert recruit_effect is not None

    def effect(game: "Game", spell: CardState) -> None:
        countered: CardState | None = None
        for reference in spell.targets:
            if not reference.is_card:
                continue
            target = next((item for item in game.stack if item.id == reference.card_id), None)
            if target is not None:
                countered = target
                game.counter(target)
        if countered is None:
            return
        if int(countered.card.cmc) <= threshold:
            recruit_effect(game, spell)

    return effect


#: "If that spell is countered this way, exile it instead of putting it into
#: its owner's graveyard." (Force of Negation) or "..., put it on top of its
#: owner's library instead of into that player's graveyard." (Memory Lapse) -
#: CR 701.6a's default destination, overridden. `that spell` is CR 400.7
#: anaphora back to whatever the first sentence's "target ... spell" found,
#: the same reading `_parse_counter_then_create_tokens_by_mana_value_pair` and
#: `_parse_anaphoric_clause_pair` already give a second sentence's pronoun.
_COUNTER_THEN_EXILE_INSTEAD_RE = re.compile(
    r"^if (?:that|the) spell is countered this way, "
    r"(?:(?P<exile>exile it)|put (?:it|that card) on (?:the )?(?P<end>top|bottom) of "
    r"its owner'?s library) instead of (?:putting it )?into "
    r"(?:its owner'?s|that player'?s) graveyard\.?$",
    re.IGNORECASE,
)


def _parse_counter_then_exile_instead_of_graveyard_pair(
    first: str, second: str, *, for_spell: bool
) -> TargetedClause | None:
    """ "Counter target ... spell. If that spell is countered this way, exile
    it instead of putting it into its owner's graveyard." as one CR 608.2c
    instruction pair, or `None` if this shape does not match.

    `Game.counter` always sends a countered spell to its owner's graveyard
    (CR 701.6a); `to_exile=True` is exactly this override. A target that
    already left the stack is simply not countered and nothing is exiled, the
    same as plain `counter_targets`.

    The first sentence may also be CR 118.12a's conditional counter -
    Syncopate's "Counter target spell unless its controller pays {X}." - in
    which case the exile rider rides on the counter that clause performs,
    and nothing at all happens when the payment is made. Without this second
    shape Syncopate's whole effect failed closed: the counter half read fine
    on its own, but the exile sentence matched no clause, and CR 608.2c has
    no half-effect.
    """
    if not for_spell:
        return None
    destination = _COUNTER_THEN_EXILE_INSTEAD_RE.fullmatch(second.strip())
    if destination is None:
        return None
    to_exile = destination.group("exile") is not None
    end = destination.group("end")
    to_library: Literal["top", "bottom"] | None = (
        None if end is None else ("top" if end.lower() == "top" else "bottom")
    )
    if unless := _COUNTER_UNLESS_PAYS_RE.fullmatch(first.strip()):
        return _counter_unless_pays_effect(
            int(unless.group("n")), to_exile=to_exile, to_library=to_library
        )
    if not _COUNTER_TARGET_SPELL_RE.fullmatch(first.strip()):
        return None

    def effect(game: "Game", spell: CardState) -> None:
        for reference in spell.targets:
            if not reference.is_card:
                continue
            target = next((item for item in game.stack if item.id == reference.card_id), None)
            if target is not None:
                game.counter(target, to_exile=to_exile, to_library=to_library)

    return effect


#: Disrupting Shoal: "Counter target spell if its mana value is X." The "if"
#: is a condition on the counter itself rather than a target restriction
#: (CR 601.2c would have to read it at announcement for that, and the card
#: does not print it as part of the target's noun phrase), so a target whose
#: mana value turns out not to match is simply not countered.
#:
#: `X` never reaches here as a literal: CR 107.3a's X is announced as the
#: spell is cast, and `effect_for` substitutes the announced value into the
#: text before this is read (`substitute_x`) - the same path Syncopate's
#: "{X}" already takes. With no announced X the clause does not match and the
#: card fails closed, which is the honest answer while Disrupting Shoal's own
#: CR 118.9 pitch cost ("exile a blue card with mana value X from your hand
#: rather than pay this spell's mana cost") is still unreadable by
#: `machines/cost.py` and no X is ever recorded.
_COUNTER_TARGET_SPELL_IF_MANA_VALUE_RE = re.compile(
    r"^counter target spell if its mana value is (?P<n>\d+)\.?$", re.IGNORECASE
)


def _parse_counter_if_mana_value_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """Disrupting Shoal - see `_COUNTER_TARGET_SPELL_IF_MANA_VALUE_RE`.

    CR 202.3e is what the comparison is against: "X is treated as 0 while the
    object is not on the stack, and X is treated as the number chosen for it
    while the object is on the stack" - the targeted spell is on the stack
    while this resolves, so `CardState.mana_value` is its real, announced one.
    """
    if not for_spell:
        return None
    match = _COUNTER_TARGET_SPELL_IF_MANA_VALUE_RE.fullmatch(clause.strip())
    if match is None:
        return None
    wanted = int(match.group("n"))

    def effect(game: "Game", spell: CardState) -> None:
        for reference in spell.targets:
            if not reference.is_card:
                continue
            target = next((item for item in game.stack if item.id == reference.card_id), None)
            if target is None or target.mana_value != wanted:
                continue
            game.counter(target)

    return effect


#: "you may cast it without paying its mana cost" (Transcendent Dragon) - the
#: tail end of its own counter-then-exile-then-cast paragraph, with no
#: "until end of turn" the way Ragavan's and Ugin's own permission sentences
#: print it (`_PLAY_PERMISSION_RE`).
_CAST_IT_FREE_RE = re.compile(r"^you may cast it without paying its mana cost$", re.IGNORECASE)


def _parse_counter_exile_then_cast_free_clauses(
    clauses: list[str], index: int, *, for_spell: bool
) -> tuple[int, TargetedClause] | None:
    """Transcendent Dragon's whole trigger: "counter target spell. If that
    spell is countered this way, exile it instead of putting it into its
    owner's graveyard, then you may cast it without paying its mana cost."
    read as one CR 608.2c instruction, the ability-side counterpart of
    `_parse_counter_then_exile_instead_of_graveyard_pair` (which only ever
    fires `for_spell=True` - nothing in the pool prints the plain
    counter-then-exile pair on a triggered ability until this card).

    Three clauses, not two: `split_effect_clauses` cuts the second sentence's
    trailing ", then you may cast it without paying its mana cost" away from
    the exile clause in front of it, so this reads all three together.

    CR 611.2a: a continuous effect with no stated duration lasts until the
    end of the game, and this permission prints none - unlike Ragavan's and
    Ugin's own "until end of turn" sentence (`_PLAY_PERMISSION_RE`) - so the
    grant is made with `until_end_of_turn=False`.

    A target that already left the stack (CR 608.2b) is neither countered nor
    exiled, and no permission is granted - there is no spell left to grant one
    over, the same as plain `counter_targets`.
    """
    if for_spell or index + 2 >= len(clauses):
        return None
    if not _COUNTER_TARGET_SPELL_RE.fullmatch(clauses[index].strip()):
        return None
    if not _COUNTER_THEN_EXILE_INSTEAD_RE.fullmatch(clauses[index + 1].strip()):
        return None
    if not _CAST_IT_FREE_RE.fullmatch(clauses[index + 2].strip()):
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        ability = stack_object
        assert isinstance(ability, AbilityOnStack)
        controller = game.controller_of(ability).username
        for reference in ability.targets:
            if not reference.is_card:
                continue
            target = next((item for item in game.stack if item.id == reference.card_id), None)
            if target is None:
                continue
            game.counter(target, to_exile=True)
            if target.zone is not Zone.EXILE:
                continue
            # ", then you may cast it" is carried out while this ability
            # resolves (CR 608.2g), not a permission used later.
            game.may_cast_during_resolution(
                target,
                controller,
                prompt=f"cast {target.name} without paying its mana cost",
                source=ability.source_name,
                source_id=source_id_of(ability),
                source_name=ability.source_name,
                rule="CR 608.2g",
            )

    return 3, effect


#: Guiding Hydra: "you may remove a +1/+1 counter from this creature. If you
#: do, put a +1/+1 counter on each other creature you control." - CR 118.12's
#: shape once more, with the optional cost a counter removed from the source
#: itself (CR 122.1) rather than `_MAY_SACRIFICE_IF_YOU_DO_RE`'s sacrifice.
#: Clockwork Hydra's mandatory "remove a +1/+1 counter from it. If you do, it
#: deals 1 damage to any target." is the same shape without "you may": the
#: consequence runs only if the counter was actually removed.
_MAY_REMOVE_COUNTER_FROM_SELF_IF_YOU_DO_RE = re.compile(
    r"^(?P<may>you may )?remove (?P<n>a|an|one|two|three|\d+) "
    r"(?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? from "
    r"(?:this (?:creature|permanent|artifact)|it)"
    r"\.\s*if you do,\s*(?P<consequence>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s19", for_spell=False)
def _parse_conditional_remove_counter_from_self_clause(
    text: str, *, for_spell: bool
) -> AbilityEffect | None:
    """`_MAY_REMOVE_COUNTER_FROM_SELF_IF_YOU_DO_RE`'s shape; see the banner
    above. A resolving spell is never itself a permanent carrying counters
    (CR 122.1), so this reads permanents only, the same restriction the
    other bare self-reference parsers in this file already draw.
    """
    if for_spell:
        return None
    match = _MAY_REMOVE_COUNTER_FROM_SELF_IF_YOU_DO_RE.fullmatch(
        _strip_non_effect_preamble(text).strip()
    )
    if match is None:
        return None
    raw_amount = match.group("n").lower()
    amount = 1 if raw_amount in ("a", "an", "one") else parse_count(raw_amount)
    if amount is None or amount < 1:
        return None
    kind = _counter_kind(match.group("kind"))
    consequence_text = match.group("consequence").strip()
    clause = parse_mixed_effect(consequence_text)
    if clause is None:
        from ..if_you_do_chains import if_you_do_consequence

        clause = if_you_do_consequence(consequence_text + ".")
    if clause is None:
        return None
    optional = match.group("may") is not None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        if optional:
            decision = Decision(
                kind=DecisionKind.MAY,
                player=ability.controller,
                prompt=f"remove a {kind} counter from {source.name}",
                source=source.name,
                affirmative_is_legal=source.counter_count(kind) >= amount,
                source_id=source_id_of(ability),
            )
            if not game.ask(decision):
                return
        if source.counter_count(kind) < amount:
            return  # CR 608.2d: nothing left to pay with by the time this runs.
        source.remove_counters(kind, amount)
        clause(game, ability)

    return effect

    return effect


#: "put `<n>` +1/+1 counters and a[n] `<keyword>` counter on `<phrase>`. It
#: becomes a[n] `<subtype>` in addition to its other types." - Guide of
#: Souls' own reflexive consequence: two keyword counters (CR 122.1a, CR
#: 122.1b) in one clause, then an anaphoric "It" (CR 400.7) naming the same
#: target for a layer 4 type change (CR 613.1d) with no stated duration, so
#: it lasts for as long as the permanent exists (CR 611.2c) rather than
#: "until end of turn" the way `_BECOMES_TYPE_IN_ADDITION_RE` above always
#: does - the whole reason this is its own reader rather than a
#: `parsed_layer_effects` sentence.
_COUNTERS_AND_BECOMES_TYPE_RE = re.compile(
    rf"^put (?P<n>{COUNT}) \+1/\+1 counters? and an? (?P<keyword>[a-z]+) counter on "
    r"(?P<phrase>target [^.]+)\.\s*it becomes an? (?P<subtype>[a-z]+) in addition to "
    r"its other types\.?$",
    re.IGNORECASE,
)


def _parse_counters_and_becomes_type_clause(text: str) -> AbilityEffect | None:
    """Guide of Souls' own consequence, see `_COUNTERS_AND_BECOMES_TYPE_RE`.

    The keyword counter is CR 122.1b: "A keyword counter on a permanent ...
    causes that object to gain that keyword" - stored under the keyword's own
    name (`CardState.counters`'s own docstring), and read back by
    `machines/combat.py::has_keyword` through `printed_characteristics`'s own
    keyword-counter lines. The type change has no target of its own to
    re-announce: it is the same object clause one just put the counters on,
    discovered here rather than asked for again (CR 608.2b's recheck already
    happened once, for the ability's one real target).
    """
    match = _COUNTERS_AND_BECOMES_TYPE_RE.fullmatch(text.strip())
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=True):
        return None
    amount = parse_count(match.group("n"))
    if amount is None:
        return None
    keyword = match.group("keyword").lower()
    subtype = match.group("subtype").capitalize()

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source_name = ability.source_name
        for target in game.resolve_targets(ability):
            if not isinstance(target, CardState) or target.zone is not Zone.BATTLEFIELD:
                continue
            game.add_counters(target, Counter.PLUS_ONE, amount)
            game.add_counters(target, keyword, 1)
            store = continuous_effects(game)
            store.add(
                ContinuousEffect(
                    description=(
                        f"{source_name}: {target.name} becomes {with_indefinite_article(subtype)} "
                        "in addition to its other types"
                    ),
                    layer=Layer.TYPE,
                    timestamp=store.tick(),
                    duration=Duration.INDEFINITE,
                    selector=_only(target.id),
                    modification=add_subtype(subtype),
                )
            )

    return effect


#: "Put `<n>` `<kind>` counter(s) on each creature target player controls." -
#: Twisted Fates' own second sentence; the real, off-set printing is
#: Meadowboon's whole own trigger, the identical clause standing alone. The
#: subject-first form "Target player puts a +1/+1 counter on each creature
#: they control." (a Shadrix Silverquill mode bullet) names the same player
#: and the same group.
_COUNTER_EACH_CREATURE_TARGET_PLAYER_RE = re.compile(
    rf"^(?:put (?P<n>{COUNT}) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on each creature "
    r"target player controls"
    rf"|target player puts (?P<n2>{COUNT}) (?P<kind2>\+1/\+1|-1/-1|[a-z]+) counters? on each "
    r"creature they control)\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s21", for_spell=FORWARD)
def _parse_counter_each_creature_target_player_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_COUNTER_EACH_CREATURE_TARGET_PLAYER_RE`'s shape; see the banner
    above. The player is this clause's own target, independent of whatever
    else the same ability also targets (Twisted Fates' own destroyed
    permanent) - told apart at resolution by `isinstance`, the same way
    every other mixed-target-kind clause in this file already is.
    """
    match = _COUNTER_EACH_CREATURE_TARGET_PLAYER_RE.fullmatch(clause.strip())
    if match is None:
        return None
    if not _targets_understood("target player", allow_player_targets=True):
        return None
    amount = parse_count(match.group("n") or match.group("n2"))
    if amount is None:
        return None
    kind = _counter_kind(match.group("kind") or match.group("kind2"))

    def effect(game: "Game", stack_object: "StackObject") -> None:
        targets = [
            target for target in game.resolve_targets(stack_object) if isinstance(target, Player)
        ]
        if not targets:
            return
        player = targets[0]
        board = game.computed_board()
        for permanent in list(game.battlefield):
            if game.controller_of(permanent).username != player.username:
                continue
            if Type.CREATURE not in board.of(permanent).types:
                continue
            game.add_counters(permanent, kind, amount)

    return effect


#: CR 702.112a's own effect, as `machines/keywords._renown_ability` writes it
#: out: "put N +1/+1 counters on it and it becomes renowned" - the counters are
#: the ordinary put-counters clause; this reads the second half.
_BECOMES_RENOWNED_RE = re.compile(r"^(?:it|this creature) becomes renowned\.?$", re.IGNORECASE)


@MIXED_CLAUSE.rung("s17", for_spell=FORWARD)
def _parse_renown_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """ "It becomes renowned" (CR 702.112a/b): the ability's source becomes
    renowned - if it is still the permanent the ability came from (CR 400.7),
    otherwise nothing."""
    if for_spell or _BECOMES_RENOWNED_RE.fullmatch(clause.strip()) is None:
        return None

    def renown(game: "Game", stack_object: "StackObject") -> None:
        source = stack_object.source(game) if isinstance(stack_object, AbilityOnStack) else None
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        stamp = getattr(stack_object, "source_stamp", None)
        if stamp is not None and source.zone_change_stamp != stamp:
            return
        source.renowned = True

    return renown


#: "Put a `<kind>` counter on this `<noun>`. If it has `<n>` or more `<kind>`
#: counters on it, sacrifice it. If you do, search your hand and/or library
#: for a[n] `<quality>` card and put it onto the battlefield. If you search
#: your library this way, shuffle." - Last Light of Durin's Day's own quest
#: counter rider. Unlike `_REFLEXIVE_SELF_COUNTER_IF_RE`'s own "put a counter
#: ... When you do, if ..." shape (CR 603.12's mandatory reflexive trigger),
#: this card prints no "when you do" at all: the threshold check and every
#: sentence after it are plain CR 608.2c sequential instructions on the same
#: ability, each one conditioned on the one before it actually happening
#: ("if it has ... counters", "if you do"), not a new triggered ability.
_QUEST_COUNTER_THRESHOLD_SACRIFICE_SEARCH_RE = re.compile(
    r"^put an? (?P<kind>[a-z]+) counter on this (?P<noun>[a-z]+)\.\s*"
    r"if it has (?P<n>[a-z0-9]+) or more (?P=kind) counters? on it, sacrifice it\.\s*"
    r"if you do, search your hand and/or library for an? (?P<quality>.+?) card "
    r"and put it onto the battlefield\.\s*"
    r"if you search your library this way, shuffle\.?$",
    re.IGNORECASE | re.DOTALL,
)


def _parse_quest_counter_threshold_sacrifice_search_clause(text: str) -> AbilityEffect | None:
    """`_QUEST_COUNTER_THRESHOLD_SACRIFICE_SEARCH_RE`'s shape.

    The counters are put on the ability's own source (CR 122.1). CR 608.2h's
    order matters: the count is read *after* the put, so an already-high
    count plus this one put is what the threshold checks. Once sacrificed
    (CR 701.21a), the search runs over the *combined* candidate pool of the
    hand and library at once - CR 701.23a's "find a card that matches the
    given description" is one search naming two zones, a single choice over
    every legal candidate wherever it sits, unlike `Game.search_library`'s
    own "graveyard, hand, and library" precedent (Surgical Extraction, The
    Stone Brain) which runs one independent search *per* zone because that
    shape moves every matching card out of every zone named, not "a card"
    from wherever it happens to be. The library is shuffled whenever it was
    part of the search (CR 701.24a: it was looked through either way, found
    card or not) - "if you search your library this way" is CR 701.23a's own
    "look at all cards in that zone", not a report of which zone the find
    came from.
    """
    match = _QUEST_COUNTER_THRESHOLD_SACRIFICE_SEARCH_RE.fullmatch(
        _strip_non_effect_preamble(text).strip()
    )
    if match is None:
        return None
    kind = _counter_kind(match.group("kind"))
    threshold = parse_count(match.group("n"))
    if threshold is None or threshold < 1:
        return None
    quality = match.group("quality").strip()
    if not _search_quality_is_readable(quality):
        return None
    matches = _quality_matcher(quality)

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        game.add_counters(source, kind, 1)
        if source.zone is not Zone.BATTLEFIELD or source.counter_count(kind) < threshold:
            return
        game.sacrifice(source)
        if source.zone is Zone.BATTLEFIELD:
            return  # CR 118.12: the sacrifice did not happen after all.
        controller = game.controller_of(ability)
        source_name = ability.source_name
        candidates = [state for state in (*controller.hand, *controller.library) if matches(state)]
        if candidates:
            chosen_ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=controller.username,
                    prompt=(
                        f"search your hand and/or library for "
                        f"{with_indefinite_article(quality)} card"
                    ),
                    source=source_name,
                    source_id=ability.source_id,
                    amount=1,
                    cards=tuple(state.id for state in candidates),
                    card_labels=tuple(state.name for state in candidates),
                    exact=False,
                    # CR 701.23b's own declinable search, with `Game.
                    # search_library`'s own unscripted-fetch convention: the
                    # first legal candidate, so a scenario that never scripts
                    # this answer still finds a real card rather than nothing
                    # (`default_answer`'s own CHOOSE_CARDS branch otherwise
                    # takes an unset default straight to "found nothing" for
                    # any optional search).
                    default_cards=tuple(state.id for state in candidates[:1]),
                )
            )
            assert isinstance(chosen_ids, tuple)
            if chosen_ids:
                by_id = {state.id: state for state in candidates}
                found = by_id[chosen_ids[0]]
                zone = found.zone
                if zone is Zone.HAND:
                    controller.hand.remove(found)
                elif zone is Zone.LIBRARY:
                    controller.library.remove(found)
                game.put_onto_battlefield(found, controller.username)
        game.shuffle_library(controller)

    return effect


_FOR_EACH_OPPONENT_COUNTERS_RE = re.compile(
    rf"^for each opponent, put (?P<n>{COUNT}|x) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on "
    rf"up to one target (?P<desc>.+?) that player controls{where_x_pattern('expr')}\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s29", for_spell=False)
@MIXED_CLAUSE.rung("s21", for_spell=FORWARD)
def _parse_for_each_opponent_counters_clause(text: str, *, for_spell: bool) -> AbilityEffect | None:
    """ "For each opponent, put X `<kind>` counters on up to one target `<X>`
    that player controls[, where X is `<expr>`]." - Hapatra, the Desert
    Fang's own ETB trigger; `<expr>` reads through the same shared
    `amount_expression` `_parse_put_counters_on_group_clause` already uses.
    """
    match = _FOR_EACH_OPPONENT_COUNTERS_RE.fullmatch(text.strip())
    if match is None:
        return None
    phrase = _for_each_opponent_target_phrase(match.group("desc"))
    if not _targets_understood(phrase, count_agnostic=True):
        return None
    kind = _counter_kind(match.group("kind"))
    n_text = match.group("n").lower()
    reader: AmountReader | None = None
    fixed_amount: int | None = None
    if n_text == "x":
        expr = match.group("expr")
        if expr is None:
            return None
        reader = amount_expression(expr)
    else:
        fixed_amount = parse_count(n_text)
        if fixed_amount is None:
            return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        source = (
            stack_object if isinstance(stack_object, CardState) else stack_object.source(game)  # type: ignore[union-attr]
        )
        if fixed_amount is not None:
            amount = fixed_amount
        elif reader is None or source is None:
            return
        else:
            x_value = getattr(stack_object, "x_value", 0) or 0
            amount = max(reader(game, controller.username, source, x_value), 0)
        if amount <= 0:
            return
        for target in game.resolve_targets(stack_object):
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD:
                game.add_counters(target, kind, amount)

    return effect


#: "Put N `<kind>` counter(s) on it/that creature and it gains `<keywords>`
#: until end of turn." (or the same as two sentences) - the effect of a
#: trigger whose condition names the object: First Day of Class's created
#: "Whenever a creature you control enters, ...", Wartime Protestors' printed
#: "Whenever another Ally you control enters, put a +1/+1 counter on that
#: creature and it gains haste until end of turn." "It"/"that creature" is the
#: object the trigger event names (CR 603.2's event, the entering creature),
#: not the ability's source; CR 122.1's counters are permanent, CR 611.2a's
#: grant ends at cleanup.
_EVENT_SUBJECT_COUNTERS_AND_KEYWORDS_RE = re.compile(
    rf"^put (?P<n>{COUNT}) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on (?:it|that creature)"
    r"(?:\.\s*|,?\s+and\s+)(?:it|that creature) gains (?P<keywords>[^.]+?) until end of turn\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s20")
def _parse_event_subject_counters_and_keywords_clause(text: str) -> AbilityEffect | None:
    """`_EVENT_SUBJECT_COUNTERS_AND_KEYWORDS_RE`'s shape."""
    match = _EVENT_SUBJECT_COUNTERS_AND_KEYWORDS_RE.fullmatch(collapsed(text.strip()))
    if match is None:
        return None
    amount = parse_count(match.group("n"))
    keywords = split_and_validate_keywords(match.group("keywords"))
    if amount is None or keywords is None:
        return None
    kind = _counter_kind(match.group("kind"))

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        put_counters_and_grant_keywords_to_event_subject(
            game,
            ability.event,
            kind,
            amount,
            tuple(keywords),
            source_name=ability.source_name,
            source_id=ability.source_id,
        )

    return effect


#: "Put a `<kind>` counter on this permanent for each creature target
#: opponent controls. Attach this permanent to up to one target creature you
#: control." - Sting, Bilbo's Sword's own ETB trigger (`self_normalized_
#: effect_text` has already turned "Sting"/"Attach Sting" into "this
#: permanent" by the time this is tried, the same normalization every other
#: CR 201.5 self-reference in this file already reads through). CR 122.1j's
#: hone counter is the pool's own instance of `<kind>`, but the count and
#: the counter kind are both read generically - any future Equipment that
#: puts a named counter on itself scaled by an opponent's board reaches this
#: the same way.
_PUT_SELF_COUNTER_FOR_EACH_OPPONENT_CREATURE_THEN_ATTACH_RE = re.compile(
    r"^put an? (?P<kind>[\w+/-]+) counters? on this permanent for each creature "
    r"target opponent controls\. attach this permanent to up to one target "
    r"creature you control\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s20")
def _parse_put_self_counter_for_each_opponent_creature_then_attach_clause(
    text: str,
) -> AbilityEffect | None:
    """`_PUT_SELF_COUNTER_FOR_EACH_OPPONENT_CREATURE_THEN_ATTACH_RE`'s shape -
    see the banner above. Both sentences share one target opponent
    (CR 115.1's ordinary "target opponent") and one up-to-one creature
    target; the count is read off the computed board (CR 613.5) at
    resolution, after the opponent is known, never re-derived from a
    battlefield sweep of "creatures" in general.
    """
    match = _PUT_SELF_COUNTER_FOR_EACH_OPPONENT_CREATURE_THEN_ATTACH_RE.fullmatch(text.strip())
    if match is None:
        return None
    kind = _counter_kind(match.group("kind"))

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        resolved = game.resolve_targets(ability)
        opponent = next((t for t in resolved if isinstance(t, Player)), None)
        creature = next(
            (t for t in resolved if isinstance(t, CardState) and t.zone is Zone.BATTLEFIELD),
            None,
        )
        if opponent is not None:
            count = sum(
                1
                for permanent in game.battlefield
                if permanent.zone is Zone.BATTLEFIELD
                and game.controller_of(permanent).username == opponent.username
                and game.characteristics_of(permanent).is_creature
            )
            if count:
                game.add_counters(source, kind, count)
        if creature is not None:
            attach_permanent(game, source, creature)

    return effect


#: "put `<n>` `<kind>` counters on him/her/it/this `<noun>`. Then draw half
#: `<n>` cards, rounded up/down." - Wan Shi Tong, Librarian's own ETB
#: trigger for its `{X}{U}{U}` cost's X (CR 107.3m: `Game._etb_x_effect_text`
#: already substitutes a literal number for a bare "X" here before this is
#: ever reached, off the cast record's own announced X; `n` still accepts a
#: literal "x" too, for a caller that reaches this with `ability.x_value`
#: unsubstituted). CR 122.6/CR 121.2: the counters and the draw are one CR
#: 608.2c instruction in the ability's own printed order, not two
#: independent clauses `split_effect_clauses`'s ordinary period-split could
#: read apart - "draw half `<n>` cards" names no target of its own to
#: dispatch through the ordinary player-clause reader alone.
_PUT_N_COUNTERS_ON_SELF_THEN_DRAW_HALF_N_RE = re.compile(
    r"^put (?P<n>x|\d+) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on "
    r"(?:him|her|it|this \w+)\.\s*then draw half (?P<n2>x|\d+) cards?, "
    r"rounded (?P<round>up|down)\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s3")
def _parse_put_n_counters_on_self_then_draw_half_n_clause(text: str) -> AbilityEffect | None:
    """`_PUT_N_COUNTERS_ON_SELF_THEN_DRAW_HALF_N_RE`'s shape - see its own
    docstring."""
    match = _PUT_N_COUNTERS_ON_SELF_THEN_DRAW_HALF_N_RE.fullmatch(text.strip())
    if match is None:
        return None
    kind = _counter_kind(match.group("kind"))
    round_up = match.group("round") == "up"
    n_word = match.group("n")
    n2_word = match.group("n2")

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        n = ability.x_value if n_word.lower() == "x" or n2_word.lower() == "x" else int(n_word)
        source = ability.source(game)
        if source is not None and source.zone is Zone.BATTLEFIELD and n > 0:
            game.add_counters(source, kind, n)
        player = game.controller_of(ability)
        draw = halve(n, round_up=round_up)
        if draw > 0:
            game.draw_cards(player, draw)

    return effect


#: "exile a(n) `<quality>` card from your graveyard. Put a number of `<kind>`
#: counters on `<this permanent>` equal to [half] that card's mana value[,
#: rounded up/down]." - Torrent Sculptor's own ETB trigger. CR 608.2c: "that
#: card" is the card the first instruction exiled, so the pair is read whole
#: rather than as two clauses (the second would have no antecedent). The count
#: is the exiled card's mana value (CR 202.3), read once as the card leaves
#: the graveyard (CR 608.2h); with no card of that quality in the graveyard
#: nothing is exiled and so there is no "that card" to count (CR 608.2c's
#: instructions are followed as far as they can be).
_EXILE_FROM_GRAVEYARD_THEN_COUNTERS_EQUAL_TO_ITS_MANA_VALUE_RE = re.compile(
    r"^exile an? (?P<quality>[a-z, ]+?) card from your graveyard\.\s*"
    r"put a number of (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters on (?:him|her|it|this \w+) "
    r"equal to (?P<half>half )?that card'?s mana value(?:, rounded (?P<round>up|down))?\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s3")
def _parse_exile_from_graveyard_then_counters_equal_to_mana_value_clause(
    text: str,
) -> AbilityEffect | None:
    """`_EXILE_FROM_GRAVEYARD_THEN_COUNTERS_EQUAL_TO_ITS_MANA_VALUE_RE`'s shape
    - see its own docstring. More than one card of the quality is the
    controller's choice (CR 608.2d), asked as one exact-one `CHOOSE_CARDS`."""
    match = _EXILE_FROM_GRAVEYARD_THEN_COUNTERS_EQUAL_TO_ITS_MANA_VALUE_RE.fullmatch(
        collapsed(_strip_non_effect_preamble(text))
    )
    if match is None:
        return None
    matches_quality = _nonland_or_typed_card_matcher(match.group("quality"))
    if matches_quality is None:
        return None
    kind = _counter_kind(match.group("kind"))
    halved = match.group("half") is not None
    round_up = match.group("round") != "down"

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        player = game.controller_of(ability)
        candidates = [state for state in player.graveyard if matches_quality(state)]
        if not candidates:
            return
        chosen = candidates[0]
        if len(candidates) > 1:
            chosen_ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=player.username,
                    prompt=f"exile {with_indefinite_article(match.group('quality'))} card "
                    "from your graveyard",
                    source=ability.source_name,
                    source_id=source_id_of(ability),
                    amount=1,
                    cards=tuple(state.id for state in candidates),
                    exact=True,
                )
            )
            assert isinstance(chosen_ids, tuple)
            chosen = next(state for state in candidates if state.id in chosen_ids)
        mana_value = int(chosen.mana_value)
        game.exile_cards([chosen])
        amount = halve(mana_value, round_up=round_up) if halved else mana_value
        source = ability.source(game)
        if source is not None and source.zone is Zone.BATTLEFIELD and amount > 0:
            game.add_counters(source, kind, amount)

    return effect


#: "[Until end of turn, ]you may activate loyalty abilities of `<subject>`
#: on any player's turn any time you could cast an instant." - Jace's
#: Machinations' own first sentence ("Jace planeswalkers you control",
#: bounded), Teferi's Talent's and Teferi, Temporal Archmage's shared
#: emblem text ("planeswalkers you control", permanent), and Teferi,
#: Master of Time's own self-reference ("Teferi", permanent, off-set - CR
#: 201.5's own planeswalker self-reference is by name, not "this
#: permanent", so the subject is read against the resolving ability's own
#: source name rather than a fixed pronoun).
_LOYALTY_INSTANT_SPEED_RE = re.compile(
    r"^(?P<until_eot>until end of turn, )?you may activate loyalty abilities of "
    r"(?P<subject>planeswalkers you control|(?P<subtype>[a-z]+) planeswalkers you control"
    r"|(?P<self_name>[a-z][a-z' ]*?)) on any player'?s turn any time you could cast "
    r"an instant\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s8", for_spell=FORWARD)
def _parse_loyalty_instant_speed_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """`_LOYALTY_INSTANT_SPEED_RE`'s shape."""
    match = _LOYALTY_INSTANT_SPEED_RE.fullmatch(clause.strip())
    if match is None:
        return None
    until_end_of_turn = match.group("until_eot") is not None
    subtype = match.group("subtype")
    self_name = match.group("self_name")

    def effect(game: "Game", stack_object: "StackObject") -> None:
        from ...models.game import LoyaltyInstantSpeedPermission

        controller = game.controller_of(stack_object).username
        self_source_id = None
        if self_name is not None:
            source = (
                stack_object if isinstance(stack_object, CardState) else stack_object.source(game)  # type: ignore[union-attr]
            )
            if source is None or source.name.split(",")[0].strip().lower() != self_name.lower():
                return
            self_source_id = source.id
        game.loyalty_instant_speed_permissions.append(
            LoyaltyInstantSpeedPermission(
                player=controller,
                subtype=subtype,
                self_source_id=self_source_id,
                until_end_of_turn=until_end_of_turn,
            )
        )

    return effect


#: "Support N." - CR 701.41a's keyword action: "Put a +1/+1 counter on each of
#: up to N [other] target creatures." The reminder text is stripped before a
#: clause is read; the targets are announced by `targeting._expand_support_
#: keyword`, so every legal target still on the battlefield gets its counter.
_SUPPORT_RE = re.compile(r"^support (?P<n>[1-9]\d*)\.?$", re.IGNORECASE)


def put_support_counters(game: "Game", targets: "list[object]", limit: int) -> None:
    """CR 701.41a: a +1/+1 counter on each of the first `limit` creatures in
    `targets` that is still a creature on the battlefield (CR 608.2b)."""
    for target in targets[:limit]:
        if (
            isinstance(target, CardState)
            and target.zone is Zone.BATTLEFIELD
            and game.characteristics_of(target).is_creature
        ):
            game.add_counters(target, "+1/+1", 1)


@MIXED_CLAUSE.rung("s9")
def _parse_support_clause(clause: str) -> TargetedClause | None:
    """`_SUPPORT_RE`'s shape - see the banner above."""
    match = _SUPPORT_RE.fullmatch(clause.strip())
    if match is None:
        return None
    limit = int(match.group("n"))

    def effect(game: "Game", stack_object: "StackObject") -> None:
        put_support_counters(game, list(game.resolve_targets(stack_object)), limit)

    return effect


#: "Proliferate[ `<n>` times][, where X is `<expr>`]." - CR 701.34's keyword
#: action, bare (Tribute to Horobi's own kicker mode) or repeated (Tam, the
#: Possibility's own "Proliferate X times, where X is the number of
#: planeswalker types among planeswalkers you control."). `_fixed_or_where_x_
#: amount` is the same CR 107.3f reader Empower Jace's own "N, where X is
#: ..." shape already uses, so a fixed repeat count and an X-defined one read
#: through the identical path.
_PROLIFERATE_RE = re.compile(
    rf"^proliferate(?: (?:{count_pattern('times', x=True)} times|(?P<twice>twice)))?"
    rf"{where_x_pattern()}\.?$",
    re.IGNORECASE,
)


def proliferate_times(game: "Game", stack_object: "StackObject", times: int) -> None:
    """CR 701.34a, `times` times over: the one place a proliferate runs, for
    `_parse_proliferate_clause` and any reader that proliferates a computed
    number of times (Expand the Sphere)."""
    controller = game.controller_of(stack_object)
    source_name = (
        stack_object.source_name if isinstance(stack_object, AbilityOnStack) else stack_object.name
    )
    # CR 614.1a: each proliferate is its own event (Tekuthal: "proliferate
    # twice instead"), and each of the resulting ones is its own choice.
    repeats = sum(game.proliferation_count(controller.username) for _ in range(max(times, 0)))
    for _ in range(repeats):
        candidates = [
            state
            for state in game.battlefield
            if any(count > 0 for count in state.counters.counts.values())
        ]
        chosen: list[CardState] = []
        if candidates:
            chosen_ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=controller.username,
                    prompt="choose any number of permanents to proliferate",
                    source=source_name,
                    source_id=source_id_of(stack_object),
                    amount=len(candidates),
                    cards=tuple(state.id for state in candidates),
                    exact=False,
                )
            )
            by_id = {state.id: state for state in candidates}
            chosen = [by_id[card_id] for card_id in chosen_ids if card_id in by_id]
        player_candidates = [
            player
            for player in game.players
            if any(count > 0 for count in player.counters.counts.values())
        ]
        chosen_players: list[str] = []
        if player_candidates:
            chosen_usernames = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_PLAYERS,
                    player=controller.username,
                    prompt="choose any number of players to proliferate",
                    source=source_name,
                    source_id=source_id_of(stack_object),
                    amount=len(player_candidates),
                    players=tuple(player.username for player in player_candidates),
                    exact=False,
                )
            )
            offered_usernames = {player.username for player in player_candidates}
            chosen_players = [
                username for username in chosen_usernames if username in offered_usernames
            ]
        if not chosen and not chosen_players:
            continue
        game.proliferate(chosen, chosen_players)


@MIXED_CLAUSE.rung("s9")
def _parse_proliferate_clause(clause: str) -> TargetedClause | None:
    """`_PROLIFERATE_RE`'s shape.

    CR 701.34a's own choice - "any number of permanents and/or players ...
    that have a counter" - is asked fresh each repetition (`game.
    proliferate` itself only ever applies to what it is handed, never
    re-derives candidates), since a counter proliferate just added can make
    a permanent or player that had none a legal choice for the *next*
    repetition. Permanents and players are asked as two separate
    questions (`Game.proliferate`'s own docstring explains why that is
    still one CR 608.2c instruction), each skipped outright when its own
    candidate list is empty rather than asked with nothing to offer.
    """
    match = _PROLIFERATE_RE.fullmatch(clause.strip())
    if match is None:
        return None
    # Contagion Engine's "Proliferate twice": CR 107.1a, "twice" is two times.
    times_raw = match.group("times") or ("two" if match.group("twice") else None)
    where_x = match.group("where_x")
    times_reader = None
    if times_raw is not None:
        # A printed "N times" that this wave cannot read (an unfamiliar
        # "where X is ..." expression, or a literal "X" with no definition
        # at all) fails the whole clause closed here, at parse time - not a
        # silent `times = 1` fallback at resolution, which would quietly run
        # Tam, the Possibility's own "Proliferate X times" once regardless
        # of what X actually was.
        times_reader = _fixed_or_where_x_amount(times_raw, where_x)
        if times_reader is None:
            return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        x_value = stack_object.x_value if isinstance(stack_object, AbilityOnStack) else 0
        times = times_reader(game, controller.username, None, x_value or 0) if times_reader else 1
        proliferate_times(game, stack_object, times)

    return effect


@MIXED_CLAUSE.rung("s37", for_spell=FORWARD)
def _parse_self_counters_for_each_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """ "Put a +1/+1 counter on this creature for each creature card in your
    graveyard.", "Put a loyalty counter on this permanent for each creature
    you control.": the one reader, `amount_sentences.self_counters_for_each_effect`."""
    from ..amount_sentences import self_counters_for_each_effect

    return self_counters_for_each_effect(clause, for_spell=for_spell)


@MIXED_CLAUSE.rung("s37", for_spell=FORWARD)
def _parse_minus_counters_mixed_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """`machines/minus_counters.parse_resolution_text`, tried as one more
    entry in `_parse_mixed_clause`'s own dispatch chain below.

    `_ability_effect_or_notice` already tries `machines/counter_effects.
    parse_resolution_text` (which chains to this same module) against the
    *whole*, unsplit text of an ordinary ability or non-modal spell - which
    is how Darkness Descends' own "Put two -1/-1 counters on each creature."
    and Rhys, the Evermore's activated ability already reach it. A modal
    spell's own chosen mode never goes through that whole-text path at all
    (`parse_mode_effect` falls back to `parse_mixed_effect_for_spell`
    instead, CR 700.2a's own mode being read as one card's worth of
    CR 608.2c instructions on its own) - Perfect Intimidation's own "Target
    opponent exiles two cards from their hand." bullet is what this call
    reaches that the whole-text path cannot.
    """
    from ..minus_counters import parse_resolution_text as _parse_minus_counters_text

    return _parse_minus_counters_text(clause, for_spell=for_spell)


#: "Remove all of them from it and <instruction with 'that many'>." -
#: Lightning Coils. "Them" is the counters the ability's own intervening "if"
#: named ("if this artifact has five or more charge counters on it"), "it"
#: the source; "that many" is how many were actually removed. A printed kind
#: ("remove all charge counters from it") names the counters itself.
_REMOVE_ALL_COUNTERS_THEN_THAT_MANY_RE = re.compile(
    r"^remove all (?:of them|(?P<kind>[a-z0-9+/-]+) counters) from (?:it|this [a-z]+)"
    r"(?:,)? and (?P<rest>.*\bthat many\b.*)$",
    re.IGNORECASE,
)

#: The counter kind an intervening "if" names - `machines/triggers.py`'s own
#: `_COUNTER_COUNT_CLAUSE` reads the same clause for CR 603.4.
_INTERVENING_COUNTER_KIND_RE = re.compile(r"\b(?P<kind>[a-z0-9+/-]+) counters? on it$")


@ABILITY_TEXT.rung("s13")
def _parse_remove_all_counters_then_that_many_clause(text: str) -> AbilityEffect | None:
    """`_REMOVE_ALL_COUNTERS_THEN_THAT_MANY_RE`'s shape, or `None`.

    CR 608.2c: one instruction - the second half's number is whatever the
    first half actually removed, read then, not the number the condition
    promised. The second half is parsed by the ordinary dispatcher with the
    number substituted in, checked here once against a probe value so an
    unreadable remainder fails the whole ability closed now rather than at
    resolution. Zero removed does nothing more (CR 101.3).
    """
    match = _REMOVE_ALL_COUNTERS_THEN_THAT_MANY_RE.fullmatch(collapsed(text).rstrip("."))
    if match is None:
        return None
    rest = match.group("rest")
    printed_kind = match.group("kind")

    def rest_for(amount: int) -> AbilityEffect | None:
        substituted = re.sub(r"\bthat many\b", str(amount), rest, count=1, flags=re.IGNORECASE)
        parsed = _ability_effect_or_notice(substituted)
        return parsed if _is_readable_head(parsed) else None

    if rest_for(2) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game) if ability.source_id is not None else None
        if not isinstance(source, CardState):
            return
        kind = printed_kind
        if kind is None:
            clause = (getattr(ability.ability, "intervening_if", None) or "").lower().strip()
            named = _INTERVENING_COUNTER_KIND_RE.search(clause)
            if named is None:
                return
            kind = named.group("kind")
        amount = source.counter_count(kind.lower())
        if amount <= 0:
            return
        source.remove_counters(kind.lower(), amount)
        follow = rest_for(amount)
        if follow is not None:
            follow(game, ability)

    return effect


#: "Counter target `<qualifier>` spell. If {that spell|a `<type>` spell} is
#: countered this way, exile it instead of putting it into its owner's
#: graveyard. You may cast that card without paying its mana cost for as long
#: as it remains exiled." - Thranduil's Decree ("a permanent spell") and
#: Kheru Spellsnatcher's turned-face-up trigger ("that spell"). CR 701.6a's
#: graveyard is replaced by exile (CR 614.1a) - for the "a `<type>` spell"
#: form only when the countered spell is one (CR 110.4b's "permanent spell")
#: - and CR 601.3's permission hands the exiled card to the countering
#: object's controller ("you"), free (CR 118.9), with no "this turn" limit:
#: "for as long as it remains exiled" is the permission's own CR 400.7 stamp.
_COUNTER_EXILE_MAY_CAST_FREE_RE = re.compile(
    rf"^counter target(?: {_SPELL_QUALIFIER})? spell\.\s*"
    r"if (?:that spell|an? (?P<quality>permanent|creature|noncreature|artifact|enchantment"
    r"|instant|sorcery|planeswalker) spell) is countered this way, exile it instead of "
    r"putting it into its owner'?s graveyard\.\s*"
    r"you may cast (?:that card|it) without paying its mana cost for as long as it "
    r"remains exiled\.?$",
    re.IGNORECASE,
)


def _counter_exile_quality_holds(spell: CardState, quality: str | None) -> bool:
    """Whether the countered `spell` is the "a `<quality>` spell" the rider
    names (CR 110.4b for "permanent"; a card type otherwise, CR 205.2a)."""
    if quality is None:
        return True
    word = quality.lower()
    if word == "permanent":
        return spell.is_permanent
    types = {type_.value.lower() for type_ in spell.types}
    if word.startswith("non"):
        return word[3:] not in types
    return word in types


@ABILITY_TEXT.rung("s9")
@SPELL_TEXT.rung("s14")
def _parse_counter_exile_may_cast_free_clause(effect_text: str) -> TargetedClause | None:
    """`_COUNTER_EXILE_MAY_CAST_FREE_RE`'s shape, read whole: the three
    sentences are one CR 608.2c instruction, "it" and "that card" both CR
    400.7 anaphora back to the countered spell. A spell that could not be
    countered (CR 101.2's "can't be countered") stays on the stack and is
    neither exiled nor handed out; a target already gone is skipped."""
    whole = collapsed(_strip_non_effect_preamble(effect_text))
    match = _COUNTER_EXILE_MAY_CAST_FREE_RE.fullmatch(whole)
    if match is None:
        return None
    quality = match.group("quality")

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object).username
        source_name = (
            stack_object.name if isinstance(stack_object, CardState) else stack_object.source_name
        )
        for reference in stack_object.targets:
            if not reference.is_card:
                continue
            target = next((item for item in game.stack if item.id == reference.card_id), None)
            if target is None:
                continue
            exiles = isinstance(target, CardState) and _counter_exile_quality_holds(target, quality)
            countered = game.counter(target, to_exile=exiles)
            if not exiles or countered in game.stack:
                continue
            assert isinstance(countered, CardState)
            if countered.zone is not Zone.EXILE:
                continue
            game.grant_play_permission(
                countered,
                controller,
                action=PlayAction.CAST,
                pays_mana_cost=False,
                source_name=source_name,
                rule="CR 601.3",
                zone=Zone.EXILE,
                until_end_of_turn=False,
            )

    return effect


#: "put a +1/+1 counter on him. If he's attacking, untap him and there is
#: an additional combat phase after this phase." (Bruce Banner // The
#: Incredible Hulk's enrage) and "put a +1/+1 counter on him. When you do,
#: he deals damage equal to the number of +1/+1 counters on him to any other
#: target." (Red Hulk's) - a counter on the source (CR 122.1), then either a
#: rider gated on the source attacking right now (CR 508.1k) or CR 603.12's
#: reflexive trigger, created only if the counter really was put.
_SELF_COUNTER_THEN_RIDER_RE = re.compile(
    r"^put an? \+1/\+1 counter on (?:it|him|her|this (?:creature|permanent))\.\s*"
    r"(?:(?P<if_attacking>if (?:it's|he's|she's|this creature is) attacking, (?P<rider>.+))"
    r"|when you do, (?P<reflexive>.+))$",
    re.IGNORECASE | re.DOTALL,
)


_LEGEND_PRONOUN_RE = re.compile(r"\b(?:he|she|him|her)\b", re.IGNORECASE)


def _parse_self_counter_then_rider(text: str) -> AbilityEffect | None:
    """`_SELF_COUNTER_THEN_RIDER_RE`'s shape, or `None`."""
    match = _SELF_COUNTER_THEN_RIDER_RE.fullmatch(collapsed(text.strip()))
    if match is None:
        return None
    put_counter = parse_mixed_effect("Put a +1/+1 counter on this creature.")
    if put_counter is None:
        return None
    if match.group("if_attacking") is not None:
        rider_text = match.group("rider")
        rider = _untap_self_and_additional_combat(rider_text) or parse_mixed_effect(
            _LEGEND_PRONOUN_RE.sub("it", rider_text)
        )
        if rider is None:
            return None

        def attacking_rider(game: "Game", ability: AbilityOnStack) -> None:
            put_counter(game, ability)
            source = ability.source(game)
            if source is not None and source.zone is Zone.BATTLEFIELD and game.is_attacking(source):
                rider(game, ability)  # type: ignore[misc]

        return attacking_rider
    reflexive_effect = _LEGEND_PRONOUN_RE.sub(
        lambda m: "it" if m.group(0).lower() in ("he", "she", "him", "her") else m.group(0),
        match.group("reflexive").strip(),
    )
    reflexive_effect = reflexive_effect[:1].upper() + reflexive_effect[1:]
    if reflexive_consequence_effect(reflexive_effect) is None:
        return None
    reflexive_text = f"When you do, {reflexive_effect[:1].lower()}{reflexive_effect[1:]}"

    def counter_then_reflexive(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        before = source.counter_count(Counter.PLUS_ONE)
        put_counter(game, ability)
        if source.zone is not Zone.BATTLEFIELD or source.counter_count(Counter.PLUS_ONE) <= before:
            return
        game.create_reflexive_trigger(
            text=reflexive_text,
            controller=ability.controller,
            source_id=ability.source_id,
            source_name=ability.source_name,
            callback=ReflexiveWhenYouDoConsequence(),
        )

    return counter_then_reflexive


#: "Choose a counter on target `<object>`. Put another counter of that kind on
#: it." (Dathon, His Heart Open), "... Put an additional counter of that kind
#: on that permanent." (Ichormoon Gauntlet), "... Give that permanent or
#: player another counter of that kind." (Animation Module). CR 122.1: a
#: counter's kind is its name, so the choice is among the distinct names
#: already on the target; CR 608.2d: its controller chooses as the ability
#: resolves, from the kinds the target actually has. The giving is CR 122.6's
#: putting, so replacement effects (Hardened Scales) apply. The target is a
#: permanent and/or a player, whichever the text names - legality is
#: `machines/targeting.py`'s, read off the same sentence.
_CHOOSE_A_COUNTER_ADD_ANOTHER_RE = re.compile(
    r"^choose a counter on target [^.]+?\. "
    r"(?:put|give) (?:(?:that [a-z ]+|it) )?(?:another|an additional) counter of that kind"
    r"(?: on (?:it|that [a-z ]+?))?\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s26")
def _parse_choose_a_counter_put_another_of_that_kind(text: str) -> AbilityEffect | None:
    """`_CHOOSE_A_COUNTER_ADD_ANOTHER_RE`'s shape (CR 122.1, 122.6, 608.2d)."""
    if not text.lower().startswith("choose a counter on target"):
        return None
    if _CHOOSE_A_COUNTER_ADD_ANOTHER_RE.fullmatch(collapsed(text)) is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = game.controller_of(ability).username
        for target in game.resolve_targets(ability):
            if isinstance(target, CardState):
                if target.zone is not Zone.BATTLEFIELD:
                    continue
            elif not isinstance(target, Player):
                continue
            kinds = [str(kind) for kind, count in target.counters.counts.items() if count > 0]
            if not kinds:
                continue  # nothing to choose (CR 608.2d: no illegal option)
            kind = kinds[0]
            if len(kinds) > 1:
                subject = target.name if isinstance(target, CardState) else target.username
                answer = game.ask(
                    Decision(
                        kind=DecisionKind.CHOOSE_A_QUALITY,
                        player=controller,
                        prompt=f"choose a counter on {subject}",
                        source=ability.source_name,
                        source_id=source_id_of(ability),
                        options=tuple(kinds),
                    )
                )
                assert isinstance(answer, str)
                kind = answer
            if isinstance(target, CardState):
                game.add_counters(target, kind, 1, putter=controller)
            else:
                game.add_player_counters(target, kind, 1)

    return effect


from ._common import (  # noqa: E402
    _ADD_ANY_COMBINATION_MANA_RE,
    _ANAPHOR_GAINS_KEYWORDS_RE,
    _ANAPHORIC_SUBJECT_RE,
    _COLOR_COUNT_WORDS,
    _COLOR_LETTERS,
    _COUNTER_TARGET_RE,
    _COUNTER_TARGET_SPELL_RE,
    _COUNTER_UNLESS_PAYS_RE,
    _HAND_EXILE_COLOR_WORDS,
    _MANA_SYMBOL_RE,
    AmountReader,
    ConditionalClauseNotice,
    UnreadableCounterAmountNotice,
    _card_description_is_readable,
    _effect_condition_is_readable,
    _nonland_or_typed_card_matcher,
    _quality_matcher,
    _targets_understood,
)
from .amounts import (  # noqa: E402
    _fixed_or_where_x_amount,
    _for_each_multiplier,
    _max_untargeted_recipients,
    _that_many_or_notice,
    amount_expression,
)
from .continuous import (  # noqa: E402
    _attached_object,
    _attack_trigger_pump_subject,
    _for_each_opponent_target_phrase,
    _grant_keywords_to,
    _is_readable_head,
    _untap_self_and_additional_combat,
    attach_permanent,
    continuous_effects,
    transform_permanent,
)
from .damage import _damage_recipient_is_its_subject, _divided_damage_shares  # noqa: E402
from .dispatch import (  # noqa: E402
    _ability_effect_or_notice,
    _parse_mixed_clause,
    _parse_mixed_clauses,
    parse_clause_effect,
    parse_mixed_effect,
)
from .library import _parse_recruit_clause  # noqa: E402
from .modal import reflexive_consequence_effect  # noqa: E402
from .removal import _counter_unless_pays_effect, _parse_mass_destroy_predicate  # noqa: E402
from .search import _search_quality_is_readable  # noqa: E402
from .text import (  # noqa: E402
    _bare_subtype_word,
    _parse_referent_clause,
    _strip_non_effect_preamble,
)
from .tokens import _parse_generic_token_descriptor, _parse_token_clause  # noqa: E402


@ABILITY_TEXT.rung("s19", for_spell=False)
def _parse_remove_counter_from_each_of_n_clause(
    text: str, *, for_spell: bool
) -> AbilityEffect | None:
    """ "you may remove a <kind> counter from each of <N> creatures you
    control. If you do, <consequence>." - `machines/if_you_do_chains.
    parse_remove_counter_from_each_of_n`."""
    if for_spell or "counter from each of" not in text.lower():
        return None
    from ..if_you_do_chains import parse_remove_counter_from_each_of_n

    return parse_remove_counter_from_each_of_n(text)


#: "Remove up to `<n>` counters from target `<permanent>`. For each counter
#: removed this way, `<it>` gets +`<a>`/+`<b>` until end of turn." - Hex Parasite
#: (`{X}{B/P}`, with X already read into `<n>` by `activated_effect_for`). The
#: removal is `_parse_remove_up_to_n_counters_from_target_clause`'s own (CR 122.1,
#: CR 608.2d: up to N, as many as are there); the second sentence is CR 608.2c
#: reading the number of counters actually removed (CR 122.5), so a target with
#: fewer pumps by fewer, and a target that is gone (CR 608.2b) pumps nothing.
_REMOVE_UP_TO_THEN_PUMP_PER_REMOVED_RE = re.compile(
    rf"^(?P<remove>remove up to {COUNT} counters from (?:another )?target [^.]+?)\.\s*"
    r"for each counter removed this way, (?P<who>[^.]+?) gets "
    r"(?P<p>[+-]\d+)/(?P<t>[+-]\d+) until end of turn\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s28")
def _parse_remove_up_to_then_pump_per_removed(text: str) -> AbilityEffect | None:
    """`_REMOVE_UP_TO_THEN_PUMP_PER_REMOVED_RE`'s shape; see the banner above."""
    from .dispatch import _parse_mixed_clauses

    match = _REMOVE_UP_TO_THEN_PUMP_PER_REMOVED_RE.fullmatch(collapsed(text))
    if match is None:
        return None
    removal = _parse_remove_up_to_n_counters_from_target_clause(match.group("remove") + ".")
    if removal is None:
        return None
    power, toughness, who = int(match.group("p")), int(match.group("t")), match.group("who")
    if (
        _parse_mixed_clauses(
            f"{who} gets {power:+d}/{toughness:+d} until end of turn.", for_spell=False
        )
        is None
    ):
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        targets = [
            t
            for t in game.resolve_targets(ability)
            if isinstance(t, CardState) and t.zone is Zone.BATTLEFIELD
        ]

        def held() -> int:
            return sum(count for t in targets for _kind, count in t.counters.items())

        before = held()
        removal(game, ability)
        removed = before - held()
        if removed <= 0:
            return
        clauses = _parse_mixed_clauses(
            f"{who} gets {power * removed:+d}/{toughness * removed:+d} until end of turn.",
            for_spell=False,
        )
        for clause in clauses or ():
            clause(game, ability)

    return effect


#: "You may remove a `<kind>` counter from each of any number of `<Saga>`s you
#: control. Put a `<kind>` counter on `<this>` for each `<kind>` counter removed
#: this way." - Garnet, Princess of Alexandria. CR 608.2d: the controller chooses
#: whether, then which of the permanents that really have one (CR 107.1c: any
#: number, none included); CR 122.5 each loses one, and CR 608.2c's second
#: sentence counts the ones removed.
_MAY_REMOVE_FROM_EACH_THEN_PUT_PER_REMOVED_RE = re.compile(
    r"^you may remove an? (?P<kind>[+\-/\d]+|[a-z]+) counter from each of any number of "
    r"(?P<noun>[a-z]+)s you control\.\s*"
    r"put an? (?P<ck>\+1/\+1|-1/-1|[a-z]+) counter on (?:this \w+|it) "
    r"for each (?P=kind) counter removed this way\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s28")
def _parse_may_remove_from_each_then_put_per_removed(text: str) -> AbilityEffect | None:
    """`_MAY_REMOVE_FROM_EACH_THEN_PUT_PER_REMOVED_RE`'s shape; see the banner above."""
    match = _MAY_REMOVE_FROM_EACH_THEN_PUT_PER_REMOVED_RE.fullmatch(collapsed(text))
    if match is None or not _search_quality_is_readable(match.group("noun")):
        return None
    kind = match.group("kind").lower()
    put_kind = match.group("ck").lower()
    quality = _quality_matcher(match.group("noun"))

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        controller = game.controller_of(ability)
        candidates = [
            permanent
            for permanent in game.permanents_controlled_by(controller.username)
            if quality(permanent) and permanent.counter_count(kind) >= 1
        ]
        if not candidates:
            return
        if not game.may(
            controller,
            f"remove a {kind} counter from each of any number of "
            f"{match.group('noun')}s you control",
            source=ability.source_name,
            source_id=source_id_of(ability),
            cards=tuple(candidates),
        ):
            return
        chosen_ids = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=controller.username,
                prompt=f"choose any number of {match.group('noun')}s to lose a {kind} counter",
                source=ability.source_name,
                source_id=source_id_of(ability),
                amount=len(candidates),
                exact=False,
                cards=tuple(card.id for card in candidates),
            )
        )
        assert isinstance(chosen_ids, tuple)
        removed = 0
        for card in candidates:
            if card.id in chosen_ids and card.can_remove_counters(kind, 1):
                card.remove_counters(kind, 1)
                removed += 1
        if removed:
            game.add_counters(source, put_kind, removed)

    return effect


@ABILITY_TEXT.rung("s1", for_spell=False)
@SPELL_TEXT.rung("s1", for_spell=True)
def _parse_counters_amount_text(text: str, *, for_spell: bool) -> Effect | AbilityEffect | None:
    """ "Put a +1/+1 counter on it for each creature in your party", "Choose target creature
    you control. Put ... on it for each ...", "Put a +1/+1 counter on each creature you control
    with toughness less than <amount>" (`ep02_r2_devotion_domain_party`)."""
    return counters_amount_effect(text)
