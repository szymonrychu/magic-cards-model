"""Counters as a payoff for something else happening to the object that
carries them (CR 122.1), read by shape and never by card:

- **"Whenever `<this>` is dealt damage, put that many `<kind>` counters on
  it."** (CR 120.3, CR 607.1's "that many" anaphora onto the very event that
  triggered the ability) - Venus, Torn Between Worlds. The trigger condition
  itself ("`<this>` is dealt damage") is already read generically
  (`machines/abilities._trigger_event`'s own `DEALS_DAMAGE` mapping,
  `machines/triggers.condition_matches`'s passive-voice branch) - Hexhaven
  Invigorator already proves it works; only this module's own "on it" +
  "that many" resolution shape was missing (the existing `_COUNTER_ON_IT_
  TRIGGER_SUBJECT_RE` in `machines/effects.py` only ever matched a fixed
  count, never "that many").
- **"At the beginning of combat on your turn, put a `<kind>` counter on
  `<this>`. Then you draw X cards and lose X life, where X is the number of
  counters on `<this>`."** (CR 122.1, CR 608.2c's in-order instructions - X
  is read *after* the counter this same sentence just placed, and across
  every counter kind the object carries, not only the one just added) -
  Savanti Romero, Time's Exile. The trigger condition is already generic
  (Agent Bishop, Man in Black and Old Hob, Alleycat Blues already prove "At
  the beginning of combat on your turn" triggers); only the resolution is
  this module's.
- **"Whenever `<this>` deals combat damage to a player, you may remove a
  counter from it. When you do, `<consequence>`."** (CR 603.12's reflexive
  triggered ability, CR 118.12's cost paid on resolution) - Leatherhead,
  Swamp Stalker. Unlike `machines/counter_effects.py`'s own `_remove_a_
  counter_if_you_do` ("remove a counter from a[n] `<description>` you
  control. If you do, ...", a same-instruction CR 118.12 cost with a chosen
  *other* permanent), this is CR 603.12's different shape: "When you do"
  creates a brand-new stack object an opponent can respond to (CR 405.6a),
  and the counter always comes off the ability's own self-referential
  source, never a chosen target.
- **"Whenever this Vehicle attacks, put a `<kind>` counter on target creature
  that crewed it this turn. Then if that creature is `<a/an> <quality>`,
  double the number of `<kind>` counters on it."** (CR 702.122b's own
  "crews", CR 701.10e's doubling) - Turtle Van. "That crewed it this turn" is
  a new targeting restriction (`machines/targeting.TargetRequirement.must_
  have_crewed_source_this_turn`); the doubling itself reuses the same CR
  701.10e primitive `machines/counter_effects._put_counter_then_double_on_
  that` already established for sos-T3's Growth Curve, just gated on a
  subtype check instead of being unconditional.
- **"Whenever another creature you control enters, you may pay life equal to
  its power. If you do, put that many `<kind>` counters on it."** (CR 118.12,
  CR 119.4's life payment) - Madame Null, Power Broker. The trigger condition
  ("another creature you control enters") is already generic (EPF Point
  Squad's Alliance trigger already proves it); "that many" here is *not*
  CR 607.1's anaphora onto the triggering event (`machines/effects.that_
  many`, which reads `GameEvent.amount`) - it is the amount of life actually
  paid, a value this resolution computes and pays itself, so it is carried
  as a local variable instead.

Every reader here is registered into `machines/counter_effects.parse_
resolution_text`'s own `_WHOLE_TEXT_READERS` tuple (an additive import and
tuple entry there, since that module and this one are both this task's to
add to) rather than into `machines/effects.py` directly, so no reader owned
by another task in this round is ever touched.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from magic_cards_model.text_norm import collapsed

from ..models.card_state import CardState
from ..models.zone import Zone
from ..numbers import parse_count
from . import effects
from .modes import substitute_x
from .targeting import permanent_description
from .triggers import AbilityOnStack

if TYPE_CHECKING:
    from ..models.game import Game
    from .triggers import StackObject


# ---------------------------------------------------------------------------
# Venus, Torn Between Worlds: "Whenever <this> is dealt damage, put that many
# <kind> counters on it."
# ---------------------------------------------------------------------------

#: "put that many `<kind>` counter(s) on it." as a triggered ability's whole
#: instruction, once the object's own self-reference has already been
#: normalised to the impersonal "it" (`machines/abilities.legendary_self_
#: pronoun_normalized`'s object-position rewrite, for a legendary source -
#: Venus's own "put that many +1/+1 counters on her." - or the plain word
#: "it" a non-legendary printing of the identical template would use
#: directly). CR 607.1's "that many" is this same ability's own triggering
#: event, read by `machines/effects.that_many` the identical way Marauding
#: Mako's "put that many +1/+1 counters on this creature" (a *different*
#: object doing the counting) already does - `_COUNTER_ON_IT_TRIGGER_
#: SUBJECT_RE` in `machines/effects.py` is that shape's own "on it" sibling,
#: but only for a literal fixed count, never "that many".
#:
#: "It" is read off the ability's own printed *source* (`AbilityOnStack.
#: source`), never `GameEvent.subject_id` - CR 120.1 makes the subject of a
#: `DEALS_DAMAGE` event the *dealer*, not the recipient (Lightning Bolt's own
#: "any target" does not even always carry one, `event.subject_id` coming
#: back `None`), so a passive "is dealt damage" self-trigger's own "it" is
#: never that field. `_COUNTER_ON_IT_TRIGGER_SUBJECT_RE`'s own "it" is safe
#: reading `subject_id` only because its condition is the *active* voice
#: ("attacks"), where the subject and the source happen to be the same
#: object - a coincidence this reader does not get to rely on.
_PUT_THAT_MANY_COUNTERS_ON_IT_RE = re.compile(
    r"^put that many (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on it\.?$", re.IGNORECASE
)


def _put_that_many_counters_on_it(text: str, *, for_spell: bool):  # noqa: ANN202
    if for_spell:
        return None

    match = _PUT_THAT_MANY_COUNTERS_ON_IT_RE.fullmatch(text.strip())
    if match is None:
        return None
    kind = effects._counter_kind(match.group("kind"))

    def effect(game: Game, stack_object: StackObject) -> None:
        from . import effects

        if not isinstance(stack_object, AbilityOnStack):
            return
        # CR 120.1: "An object that deals damage is the source of that
        # damage" - for a *passive* "is dealt damage" condition (Venus's own
        # shape) the recipient this ability's own "it" names is never
        # `GameEvent.subject_id` (the *dealer*, which the game does not even
        # always know - Lightning Bolt's own "any target" leaves it `None`),
        # so this reads the ability's own printed source instead
        # (`AbilityOnStack.source`), correct for any self-referential
        # trigger regardless of whether its condition's voice is active or
        # passive.
        subject = stack_object.source(game)
        # CR 400.7/603.10a: a subject that has since left the battlefield (a
        # lethal hit killed it before this ability could resolve - Venus's
        # own reminder text, "She must survive the damage to get the
        # counters") gets nothing, the same "no longer there" refusal
        # `_parse_counter_on_it_trigger_subject_clause` already gives its
        # own fixed-count sibling.
        if not isinstance(subject, CardState) or subject.zone is not Zone.BATTLEFIELD:
            return
        count = effects.that_many(game, stack_object)
        if count is None:
            game.unmodeled_trigger_effect_notices.append(
                effects.UnmodeledTriggerEffectNotice(
                    source_id=stack_object.source_id,
                    source_name=stack_object.source_name,
                    text=text.strip(),
                )
            )
            return
        if count > 0:
            game.add_counters(subject, kind, count)

    return effect


# ---------------------------------------------------------------------------
# Savanti Romero, Time's Exile: "At the beginning of combat on your turn, put
# a <kind> counter on <this>. Then you draw X cards and lose X life, where X
# is the number of counters on <this>."
# ---------------------------------------------------------------------------

#: `<this>` has already been rewritten to CR 700.7's "this permanent" by
#: `machines/abilities.self_normalized_effect_text` by the time this ever
#: runs (Savanti Romero's own literal-name self-reference, the identical
#: rewrite Grist's/The Filigree Sylex's own self-named clauses already
#: get). "The number of counters on this permanent" names no kind at all
#: (CR 122.1's open set of kinds) - unlike every existing "the number of
#: `<kind>` counters on it" reader in `machines/effects.py`
#: (`_COUNTER_ON_IT_RE` and siblings), X here is the *total* across every
#: kind the object carries, counted *after* this same sentence's own put
#: (CR 608.2c: instructions run in the order written, and "then" makes the
#: order explicit).
#:
#: `<clause>` is read generally (CR 107.3a's X, substituted by
#: `machines/modes.substitute_x` into whatever clause the card actually
#: prints, then dispatched by the ordinary whole-clause resolver) rather
#: than fixed to Savanti Romero's own "you draw X cards and lose X life":
#: no second Modern/Pioneer/Standard-legal printing combines *that* exact
#: clause with "where X is the number of counters on it" (`card_search`
#: found only Bebop, Skull & Crossbones, which is legal nowhere - see
#: MEMORY.md), but generalising the X-definition over an arbitrary clause
#: is what lets Spider-Man Noir's own "put a +1/+1 counter on it. Then
#: surveil X, where X is the number of counters on it." prove the same
#: counters-on-self X reader without re-confirming the one sentence it was
#: built against.
#:
#: The self-reference itself comes in two shapes that name *different*
#: objects and must never be conflated: "this creature"/"this permanent" is
#: CR 700.7's own reference to the ability's *source* (Savanti Romero's own
#: literal name, already rewritten by `machines/abilities.self_normalized_
#: effect_text`), while a bare "it" with no earlier noun in the same
#: sentence is CR 400.7 anaphora onto whatever this ability's own trigger
#: *condition* named - Spider-Man Noir's own "a creature you control attacks
#: alone" - which is very often a creature other than Spider-Man Noir
#: itself. `(?P<ref1>...)`/`(?P<ref2>...)` are captured (not just matched)
#: so the effect can tell the two apart and read `AbilityOnStack.source`
#: for the first, `GameEvent.subject_id` for the second - and a pattern
#: mixing the two ("... on this creature ... on it ...") is refused rather
#: than guessed at, since no printing in the pool does that and nothing
#: here should invent a meaning for it.
_PUT_COUNTER_THEN_X_CLAUSE_WHERE_X_IS_COUNTERS_ON_SELF_RE = re.compile(
    r"^put (?P<n>a|one|\d+) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on "
    r"(?P<ref1>this (?:creature|permanent)|it)\. "
    r"then (?P<clause>.+?), where x is the number of counters on "
    r"(?P<ref2>this (?:creature|permanent)|it)\.?$",
    re.IGNORECASE,
)

#: A bare, word-bounded "X" - the same check `machines/modes.substitute_x`
#: itself makes, used here only to refuse a `<clause>` that never actually
#: names the X this sentence just defined (a shape this reader has no
#: business claiming).
_BARE_X_RE = re.compile(r"(?<![\w])X(?![\w])", re.IGNORECASE)


def _sentence(text: str) -> str:
    text = text.strip()
    text = text[:1].upper() + text[1:]
    return text if text.endswith(".") else text + "."


def _resolution_clause(text: str):  # noqa: ANN202
    """`text` read by `machines/effects`' own whole-text ability resolver,
    or `None` for unread or notice-only text - the identical shape
    `machines/counter_effects._resolution_clause` already keeps for its own
    callers, duplicated rather than imported so this module and that one
    stay free of a mutual import (each reaches the other only lazily, to
    register into the other's own dispatch list)."""
    from . import effects

    parsed = effects._ability_effect_or_notice(_sentence(text))
    if parsed is None or effects._is_notice_only(parsed):
        return None
    return parsed


def _put_counter_then_x_clause_where_x_is_counters_on_self(text: str, *, for_spell: bool):  # noqa: ANN202
    if for_spell:
        return None

    match = _PUT_COUNTER_THEN_X_CLAUSE_WHERE_X_IS_COUNTERS_ON_SELF_RE.fullmatch(collapsed(text))
    if match is None:
        return None
    ref1 = match.group("ref1").lower()
    ref2 = match.group("ref2").lower()
    is_self_reference = ref1 != "it"
    if is_self_reference != (ref2 != "it"):
        # "this creature ... on it" or "it ... on this creature" - a mixed
        # pair no printing in the pool prints; refused rather than guessed.
        return None
    amount = parse_count(match.group("n"))
    if amount is None:
        return None
    kind = effects._counter_kind(match.group("kind"))
    clause_template = match.group("clause").strip()
    if _BARE_X_RE.search(clause_template) is None:
        return None
    # Fail closed at build time, the same "read a shape not read rather than
    # guess" posture every other reader here keeps: a clause this module
    # cannot dispatch once X is known is refused now, not silently ignored
    # the first time it actually resolves. Probed with a sentinel X=1 - the
    # real amount is not known until resolution.
    if _resolution_clause(substitute_x(clause_template, 1)) is None:
        return None

    def _referenced_permanent(game: Game, stack_object: StackObject) -> CardState | None:
        if is_self_reference:
            source = stack_object.source(game) if hasattr(stack_object, "source") else None
            return source
        # Bare "it": CR 400.7 anaphora onto this ability's own trigger
        # subject (Spider-Man Noir's own attacker) - the identical reference
        # `machines/effects._COUNTER_ON_IT_TRIGGER_SUBJECT_RE` already reads
        # for a plain, fixed-count "put N counters on it."
        if not isinstance(stack_object, AbilityOnStack) or stack_object.event is None:
            return None
        if stack_object.event.subject_id is None:
            return None
        return game.find_by_id(stack_object.event.subject_id)

    def effect(game: Game, stack_object: StackObject) -> None:
        permanent = _referenced_permanent(game, stack_object)
        if not isinstance(permanent, CardState) or permanent.zone is not Zone.BATTLEFIELD:
            return
        game.add_counters(permanent, kind, amount)
        # `Counters.counts` never carries a zero entry (a kind at zero is
        # dropped - `models.card_state.Counters`' own docstring), so this
        # total is exactly CR 122.1's "the number of counters" across every
        # kind, no filtering needed.
        total = sum(permanent.counters.counts.values())
        if total <= 0:
            return
        resolved = _resolution_clause(substitute_x(clause_template, total))
        if resolved is None:
            return
        resolved(game, stack_object)

    return effect


# ---------------------------------------------------------------------------
# Leatherhead, Swamp Stalker: "Whenever <this> deals combat damage to a
# player, you may remove a counter from it. When you do, <consequence>."
# ---------------------------------------------------------------------------

#: `<this>`'s own object-position self-reference (CR 201.5c) is read here
#: directly as "it"/"him"/"her" rather than relying on `machines/abilities.
#: legendary_self_pronoun_normalized`'s own rewrite of a gendered pronoun to
#: "it": `trigger_effect_for` tries a card's *raw*, unnormalized text first
#: (`machines/effects.py`'s own docstring on that ordering), and `machines/
#: effects._unreadable_reflexive_clause`'s pronoun-agnostic "`<action>`. When
#: you do, `<consequence>`." catch-all already matches that raw text and
#: returns a `ReflexiveClauseNotice` before a pronoun-normalized retry would
#: ever run - so a reader that only recognised "it" would lose to that
#: catch-all on every legendary printing of this template. Reading the
#: pronoun directly here, the same way `_REMOVE_A_COUNTER_FROM_IT_WHEN_YOU_
#: DO_RE`'s own alternation reads any of the three, wins the race instead.
#: This is CR 603.12's reflexive triggered ability shape - "When you do" -
#: never `machines/counter_effects._remove_a_counter_if_you_do`'s "If you
#: do" cost read in the same instruction: the counter always comes off this
#: ability's own source (never a chosen "a[n] `<description>` you control"),
#: and the consequence is a *new* stack object (CR 603.3, CR 405.6a) rather
#: than continuing the same resolution. "This creature"/"this permanent"
#: (Slumbering Walker's own non-legendary printing, the off-pool generality
#: proof - a different trigger condition, "at the beginning of your end
#: step", and a different consequence, "return target creature card ...")
#: is the identical CR 700.7 self-reference spelled the ordinary way rather
#: than as a pronoun.
_REMOVE_A_COUNTER_FROM_IT_WHEN_YOU_DO_RE = re.compile(
    r"^(?P<may>you may )?remove (?:a|one) counter from "
    r"(?:it|him|her|this (?:creature|permanent))\. "
    r"when you do, (?P<rest>.+)$",
    re.IGNORECASE,
)


def _remove_a_counter_from_it_when_you_do(text: str, *, for_spell: bool):  # noqa: ANN202
    if for_spell:
        return None

    match = _REMOVE_A_COUNTER_FROM_IT_WHEN_YOU_DO_RE.fullmatch(collapsed(text))
    if match is None:
        return None
    rest_text = match.group("rest").strip()
    rest_text = rest_text[:1].upper() + rest_text[1:]
    if not rest_text.endswith("."):
        rest_text += "."
    # A shape neither this module nor `machines/effects.reflexive_
    # consequence_effect` reads fails closed at parse time - a reflexive
    # trigger that then resolves to nothing would be silence with extra
    # steps, exactly the trap `machines/counter_effects._remove_a_counter_
    # if_you_do` already refuses the same way.
    if effects.reflexive_consequence_effect(rest_text) is None:
        return None
    optional = match.group("may") is not None

    def effect(game: Game, stack_object: StackObject) -> None:
        from .decisions import Decision, DecisionKind, source_id_of
        from .delayed import ReflexiveConsequence

        if not isinstance(stack_object, AbilityOnStack):
            return
        source = stack_object.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD or not source.counters.counts:
            return
        controller = game.controller_of(stack_object).username
        source_id = source_id_of(stack_object)
        if optional and not game.may(
            controller,
            "remove a counter from this permanent",
            source=stack_object.source_name,
            source_id=source_id,
        ):
            return
        kinds = tuple(sorted(kind for kind, count in source.counters.counts.items() if count > 0))
        if not kinds:
            return
        kind = kinds[0]
        if len(kinds) > 1:
            answer = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_A_MODE,
                    player=controller,
                    prompt=f"choose the kind of counter to remove from {source.name}",
                    source=stack_object.source_name,
                    source_id=source_id,
                    options=kinds,
                )
            )
            kind = answer if answer in kinds else kinds[0]
        source.remove_counters(kind, 1)
        # CR 603.12: the reflexive ability's own `event` carries the
        # *creating* ability's triggering event forward, purely so "that
        # player controls" (`models.game._that_player_of`, asked when this
        # reflexive ability's own targets are announced) binds to the player
        # this ability's own `DEALS_DAMAGE` event named - never re-fired,
        # never re-watched (CR 603.12: already checked, already true).
        game.create_reflexive_trigger(
            text=rest_text,
            controller=controller,
            source_id=stack_object.source_id,
            source_name=stack_object.source_name,
            callback=ReflexiveConsequence(),
            event=stack_object.event,
        )

    return effect


# ---------------------------------------------------------------------------
# Turtle Van: "Whenever this Vehicle attacks, put a <kind> counter on target
# creature that crewed it this turn. Then if that creature is a[n] <quality>,
# double the number of <kind> counters on it."
# ---------------------------------------------------------------------------

_CREWED_THIS_TURN_TARGET_THEN_MAYBE_DOUBLE_RE = re.compile(
    r"^put (?P<n>a|one|\d+) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on "
    r"(?P<phrase>target creature that crewed it this turn)\. "
    r"then if that creature is an? (?P<quality>.+?), double the number of "
    r"(?P<kind2>\+1/\+1|-1/-1|[a-z]+) counters? on it\.?$",
    re.IGNORECASE,
)


def _crewed_this_turn_target_then_maybe_double(text: str, *, for_spell: bool):  # noqa: ANN202
    if for_spell:
        return None

    match = _CREWED_THIS_TURN_TARGET_THEN_MAYBE_DOUBLE_RE.fullmatch(collapsed(text))
    if match is None:
        return None
    if match.group("kind").lower() != match.group("kind2").lower():
        return None
    kind = effects._counter_kind(match.group("kind"))
    amount = parse_count(match.group("n"))
    if amount is None:
        return None
    phrase = match.group("phrase").strip()
    if not effects._targets_understood(phrase, count_agnostic=False):
        return None
    requirement = permanent_description(match.group("quality").strip())
    if requirement is None:
        return None

    def effect(game: Game, stack_object: StackObject) -> None:
        targets = [
            target
            for target in game.resolve_targets(stack_object)
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
        ]
        if not targets:
            return
        target = targets[0]
        controller = game.controller_of(stack_object).username
        game.add_counters(target, kind, amount)
        if requirement.rejects(target, controller, game) is None:
            current = target.counter_count(kind)
            if current:
                game.add_counters(target, kind, current)

    return effect


# ---------------------------------------------------------------------------
# Madame Null, Power Broker: "Whenever another creature you control enters,
# you may pay life equal to its power. If you do, put that many <kind>
# counters on it."
# ---------------------------------------------------------------------------

_MAY_PAY_LIFE_EQUAL_TO_ITS_POWER_THEN_COUNTERS_RE = re.compile(
    r"^you may pay life equal to its power\. if you do, put that many "
    r"(?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on it\.?$",
    re.IGNORECASE,
)


def _may_pay_life_equal_to_its_power_then_counters(text: str, *, for_spell: bool):  # noqa: ANN202
    if for_spell:
        return None

    match = _MAY_PAY_LIFE_EQUAL_TO_ITS_POWER_THEN_COUNTERS_RE.fullmatch(collapsed(text))
    if match is None:
        return None
    kind = effects._counter_kind(match.group("kind"))

    def effect(game: Game, stack_object: StackObject) -> None:
        from .decisions import source_id_of

        if not isinstance(stack_object, AbilityOnStack):
            return
        event = stack_object.event
        if event is None or event.subject_id is None:
            return
        subject = game.find_by_id(event.subject_id)
        if not isinstance(subject, CardState) or subject.zone is not Zone.BATTLEFIELD:
            return
        power = game.power_of(subject)
        if power is None:
            return
        # CR 119.4: an amount of life to pay is never negative - a creature
        # whose power a continuous effect has pushed below zero costs
        # nothing to match, not a negative gain.
        amount = max(power, 0)
        controller = game.controller_of(stack_object)
        paid = game.may_pay_life(
            controller,
            amount,
            source=stack_object.source_name,
            source_id=source_id_of(stack_object),
        )
        if paid and amount > 0:
            game.add_counters(subject, kind, amount)

    return effect


_WHOLE_TEXT_READERS = (
    _put_that_many_counters_on_it,
    _put_counter_then_x_clause_where_x_is_counters_on_self,
    _remove_a_counter_from_it_when_you_do,
    _crewed_this_turn_target_then_maybe_double,
    _may_pay_life_equal_to_its_power_then_counters,
)


def parse_resolution_text(text: str, *, for_spell: bool = False):  # noqa: ANN201
    """One of this module's whole-text resolution shapes, or `None`. Chained
    onto `machines/counter_effects.parse_resolution_text` (the counter-effect
    extension point `machines/effects.py` already calls at every whole-text
    resolution attempt), so nothing new has to be wired into `machines/
    effects.py` itself for this task's own readers to reach a real ability."""
    whole = collapsed(text)
    for reader in _WHOLE_TEXT_READERS:
        effect = reader(whole, for_spell=for_spell)
        if effect is not None:
            return effect
    return None
