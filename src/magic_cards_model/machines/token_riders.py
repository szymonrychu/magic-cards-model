"""Token-creation riders that need more than "create a token" alone:

- A trigger's own multiplier counting *another* object's last-known counters
  (CR 603.10a / CR 704.8 / CR 122.1), not the ability's own source's - The
  Ooze's own "Whenever a creature you control with a +1/+1 counter on it
  leaves the battlefield, create a Mutagen token for each +1/+1 counter on
  it." `machines/effects.py`'s own `_COUNTER_ON_IT_RE`/`_for_each_multiplier`
  already read a source-relative "for each `<kind>` counter on it" (Hangarback
  Walker's own dies trigger); this is the same phrase read off the *departed*
  object the trigger's condition names instead, which needs the resolving
  `AbilityOnStack`'s own `event` rather than its `source_id`.
- "Destroy target `<X>`. If its mana value was `<N>` or less, `<consequence>`."
  (CR 603.10a/400.7's own look-back for a destroyed object's last-known mana
  value) - Tainted Treats' own "create a Food token" consequence and
  Extinguish the Light's off-set "you gain 3 life" one, read by one shared
  parser so a third consequence needs only a new tail, not a new pair.
- "You may search your library for a `<quality>` card, reveal it, put it into
  your hand, then shuffle. If you don't put a card into your hand this way,
  create a `<token>`." (CR 701.23a/701.23g's own search, CR 118.12's "if you
  don't" reading the search's own outcome) - Courier of Comestibles.

Every helper here is imported by `machines/effects.py` at module load; none of
them import `effects` back at module load (the identical one-way rule
`machines/counter_effects.py`'s own header already keeps), so any of *this*
module's own functions that genuinely need one of `effects`'s private
per-clause readers - the generic token descriptor, the search-quality
matcher - import `effects` locally, inside the function that needs it, the
same way `counter_effects.py` already does throughout.
"""

import re
from typing import TYPE_CHECKING

from ..models.card_state import CardState
from ..models.zone import Zone
from . import effects  # noqa: PLC0415 - see module docstring: one-way import rule
from . import triggers as _triggers
from .decisions import source_id_of
from .ep01_r3_amounts import counters_on_it_total

if TYPE_CHECKING:  # pragma: no cover - import cycle: Game builds on the machines
    from ..models.game import Game, StackObject
    from .effects import TargetedClause


# --------------------------------------------------------------------------
# "... for each `<kind>` counter on it" - the *event subject's* own counters,
# not the ability's source's (CR 603.10a, CR 704.8, CR 122.1)
# --------------------------------------------------------------------------

#: `machines/effects._COUNTER_ON_IT_RE`'s own shape, read as a standalone
#: multiplier phrase (the tail of `_TOKEN_FOR_EACH_TAIL_RE`'s own "each"
#: group, with any trailing period already stripped by that reader).
_EVENT_SUBJECT_COUNTER_RE = re.compile(
    r"^(?:(?P<kind>\+1/\+1|-1/-1|[a-z]+) )?counters? on (?P<who>it|this \w+)$", re.IGNORECASE
)


def event_subject_counter_multiplier(phrase: str):  # noqa: ANN201 - Callable[[Game, StackObject], int] | None
    """`_EVENT_SUBJECT_COUNTER_RE`'s shape as a `(game, stack_object) -> int`
    reader, or `None` when `phrase` is not that shape.

    The Ooze's own "leaves the battlefield" trigger fires off *another*
    creature - `AbilityOnStack.event` (the `GameEvent` that raised this very
    trigger, not the ability's own `source_id`) is the only place that
    creature's identity survives to resolution, and its own `last_known_
    counters` is what CR 603.10a's look-back reads once CR 122.2 has emptied
    its live `.counters` on the way out - the identical ternary `machines/
    effects.py`'s own `_for_each_multiplier`/`_COUNTER_ON_IT_RE` already read
    for a *source*-relative count (Hangarback Walker's own dies trigger),
    mirrored here for the event's subject instead.
    """
    match = _EVENT_SUBJECT_COUNTER_RE.fullmatch(phrase.strip().rstrip("."))
    if match is None:
        return None
    kind = (
        _triggers._counter_kind_word(match.group("kind"))  # noqa: SLF001
        if match.group("kind")
        else None
    )

    def count(game: "Game", stack_object: "StackObject") -> int:
        event = getattr(stack_object, "event", None)
        subject_id = getattr(event, "subject_id", None) if event is not None else None
        if subject_id is None or match.group("who").lower() != "it":
            # "on this creature" (Twitching Doll) and an "it" with no event
            # subject both name the ability's own source.
            subject_id = getattr(stack_object, "source_id", None)
        if subject_id is None:
            return 0
        subject = game.find_by_id(subject_id)
        if subject is None:
            return 0
        return counters_on_it_total(subject, kind)

    return count


def token_clause_for_each_event_subject_counter(
    template: "TargetedClause", multiplier, counted=None
) -> "TargetedClause":
    """Run `template` (already built by `effects._token_creation_clause`)
    once per unit `event_subject_counter_multiplier` counts off the trigger's
    own event subject - the identical "count taken once, before any token is
    created" reading (CR 608.2h) `effects._token_clause_for_each` already
    gives a board-wide "for each `<quality>` you control" multiplier, just
    over a different count source.
    """

    def effect(game: "Game", stack_object: "StackObject") -> None:
        from .effects.tokens import create_for_each

        create_for_each(game, stack_object, template, counted, multiplier(game, stack_object))

    return effect


# --------------------------------------------------------------------------
# "Destroy target `<X>`. If its mana value was `<N>` or less, `<consequence>`."
# (CR 603.10a/400.7's own look-back for a destroyed object's last-known mana
# value, captured here in a local variable *before* the destruction the same
# way `effects._parse_exile_if_mv_return_then_re_exile_clause` already
# captures `target.mana_value` ahead of its own `game.exile_permanent`)
# --------------------------------------------------------------------------

#: "if its mana value was `<N>` or less, `<consequence>`." - Tainted Treats'
#: own "its", Carnivorous Canopy's/Vindictive Triumph's own "that permanent's"
#: for the identical CR 400.7d/603.10a look-back read off the same antecedent
#: object, folded into one group so either wording reaches the same reader.
_IF_MANA_VALUE_WAS_CONSEQUENCE_RE = re.compile(
    r"^if (?:its|that permanent'?s|that spell'?s) mana value was (?P<mv>\d+) or less,\s*"
    r"(?P<consequence>.+)$",
    re.IGNORECASE | re.DOTALL,
)

#: "you gain `<N>` life." - Extinguish the Light's own consequence, the
#: off-set proof this reader is not fitted to Tainted Treats' token alone.
_GAIN_LIFE_CONSEQUENCE_RE = re.compile(r"^you gain (?P<n>\d+) life\.?$", re.IGNORECASE)


def parse_destroy_if_mv_then_consequence_clause_pair(first: str, second: str, *, for_spell: bool):  # noqa: ANN201 - TargetedClause | None
    """ "Destroy target `<X>`. If its mana value was `<N>` or less,
    `<consequence>`." - Tainted Treats' whole text (`<consequence>` a token
    creation) and Extinguish the Light's (`<consequence>` a life gain), read
    as one CR 608.2c instruction pair: the second sentence's "its" is CR
    400.7d/603.10a anaphora back to the object the first sentence destroyed,
    which only a caller holding both clauses together can resolve.

    The destroy must actually have happened for the consequence to apply -
    read the identical way `effects._parse_destroy_then_if_that_permanent_
    was_draw_clause_pair` already gates its own consequence on `target.zone
    is not Zone.BATTLEFIELD` (an indestructible or regenerated target never
    triggers the "if" at all, the same as a `-1/-1`-immune creature never
    triggering Diregraf Ghoul's Zombie-count check): the mana value itself is
    snapshotted into a local variable *before* `game.destroy(target)` runs,
    since CR 122.2/400.7 make the departed object's live characteristics
    unreliable the instant it leaves, and a Python local outlives that move
    exactly the way `last_known_counters` outlives a counter wipe.
    """

    verb_match = effects._DESTROY_TARGET_RE.fullmatch(first.strip())  # noqa: SLF001
    if verb_match is None:
        return None
    if not effects._targets_understood(  # noqa: SLF001
        verb_match.group("phrase"), count_agnostic=True, battlefield_only=True
    ):
        return None
    cond_match = _IF_MANA_VALUE_WAS_CONSEQUENCE_RE.fullmatch(second.strip())
    if cond_match is None:
        return None
    threshold = int(cond_match.group("mv"))
    consequence_text = cond_match.group("consequence").strip()
    token_clause = effects._parse_token_clause(consequence_text, for_spell=for_spell)  # noqa: SLF001
    life_match = _GAIN_LIFE_CONSEQUENCE_RE.fullmatch(consequence_text)
    if token_clause is None and life_match is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        targets = [
            target
            for target in game.resolve_targets(stack_object)
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
        ]
        if not targets:
            return
        target = targets[0]
        mana_value = target.mana_value
        game.destroy(target)
        if target.zone is Zone.BATTLEFIELD:
            return
        if mana_value > threshold:
            return
        if token_clause is not None:
            token_clause(game, stack_object)
        else:
            assert life_match is not None
            game.gain_life(controller, int(life_match.group("n")))

    return effect


# --------------------------------------------------------------------------
# "You may search your library for a `<quality>` card, reveal it, put it
# into your hand, then shuffle. If you don't put a card into your hand this
# way, create a `<token>`." (CR 701.23a/701.23g's own optional search, CR
# 118.12's "if you don't" reading whether that search actually put a card
# into the searcher's hand)
# --------------------------------------------------------------------------

_SEARCH_OR_ELSE_CREATE_TOKEN_RE = re.compile(
    r"^you may search (?:your|their) library for an? (?P<quality>.+?) card, reveal it, "
    r"put it into your hand, then shuffle\.\s*"
    r"if you don'?t put a card into your hand this way,\s*(?P<token_clause>create .+)$",
    re.IGNORECASE | re.DOTALL,
)


def parse_search_or_else_create_token_clause(text: str, *, for_spell: bool):  # noqa: ANN201 - AbilityEffect | None
    """`_SEARCH_OR_ELSE_CREATE_TOKEN_RE`'s shape - Courier of Comestibles'
    whole ETB text - or `None`.

    Read as one whole-text instruction rather than two independent clauses:
    the second sentence's "this way" is CR 118.12 anaphora straight back to
    the first sentence's own search, which the ordinary per-clause splitter
    (`effects._parse_mixed_clauses`) has no way to rejoin once it has already
    cut the text at the period - the identical reason that function's own
    docstring gives for trying several other whole-text pairs (Knowledge
    Pool's own "If the player does, ...") ahead of its per-clause path.
    """
    match = _SEARCH_OR_ELSE_CREATE_TOKEN_RE.fullmatch(text.strip())
    if match is None:
        return None
    from . import effects  # noqa: PLC0415 - see module docstring: one-way import rule

    quality = match.group("quality").strip()
    if not effects._card_description_is_readable(quality):  # noqa: SLF001
        return None
    matches = effects._quality_matcher(quality)  # noqa: SLF001
    token_clause = effects._parse_token_clause(  # noqa: SLF001
        match.group("token_clause").strip(), for_spell=for_spell
    )
    if token_clause is None:
        return None

    def effect(game: "Game", stack_object: "StackObject") -> None:
        controller = game.controller_of(stack_object)
        source = (
            stack_object.name  # type: ignore[union-attr]
            if for_spell
            else stack_object.source_name  # type: ignore[union-attr]
        )
        source_id = source_id_of(stack_object)
        found = effects._search_library(  # noqa: SLF001
            game, controller, matches, source=source, source_id=source_id
        )
        if found is not None:
            game.reveal(found, source=source)
            controller.add(found, Zone.HAND)
            return
        token_clause(game, stack_object)

    return effect
