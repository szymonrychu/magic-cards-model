"""Counters as a player puts them: who put them, on what, and when (CR 122).

The active-voice family of counter templates, read by shape and never by
card:

- **"Whenever you put a[n]/one or more `<kind>` counter(s) on `<a
  description>`"** (CR 122.6) - Ant-Man, Colony Commander's "a creature",
  Knight of Wundagore's "another creature", Invisible Woman, Sue Storm's "one
  or more other Heroes you control", Stocking the Pantry's and Terrasymbiosis'
  "a creature you control". `counter_trigger_events`/`counter_condition_matches` are
  the two halves `machines/triggers.py`'s unread-condition fallback asks.
- **"Whenever one or more `<description>` you control deal damage to a
  player"** (CR 120.1, CR 603.2c) - The Thing, Ben Grimm's own batched damage
  condition, combat damage as one event per step and noncombat damage as its
  own event.

"You put" is CR 122.6a's putter - the player following the instruction, the
object's controller when nothing else is named - which `Game.add_counters`
already works out for its replacement event and now carries on the trigger
event as `GameEvent.player`.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ..data.subtypes import subtype_vocabulary
from ..models.card import Type
from .triggers import ExtraTriggerEvent, GameEvent, TriggerEvent

if TYPE_CHECKING:
    from ..models.card_state import CardState
    from ..models.game import Game
    from .triggers import TriggeredAbility


# ---------------------------------------------------------------------------
# Descriptions: "a creature", "another creature", "one or more other Heroes
# you control", "an artifact or creature you control"
# ---------------------------------------------------------------------------

_CARD_TYPE_WORDS: dict[str, Type] = {
    "creature": Type.CREATURE,
    "creatures": Type.CREATURE,
    "artifact": Type.ARTIFACT,
    "artifacts": Type.ARTIFACT,
    "enchantment": Type.ENCHANTMENT,
    "enchantments": Type.ENCHANTMENT,
    "land": Type.LAND,
    "lands": Type.LAND,
    "planeswalker": Type.PLANESWALKER,
    "planeswalkers": Type.PLANESWALKER,
}

_DESCRIPTION_RE = re.compile(
    r"^(?:(?P<another>another)|an?|one or more)\s+(?P<other>other\s+)?"
    r"(?P<noun>.+?)(?P<you_control>\s+you control)?$",
    re.IGNORECASE,
)


def singular_subtype(word: str) -> str | None:
    """`word` as a subtype in CR 205.3's vocabulary (lower-cased, as the
    vocabulary stores it), or `None`. English plurals the subtype lists print: "s" (Goblins), "es"
    (Heroes), "ies" (Allies), "ves" (Elves)."""
    vocabulary = {entry.lower(): entry for entry in subtype_vocabulary()}
    lowered = word.lower()
    candidates = [lowered]
    if lowered.endswith("ies"):
        candidates.append(lowered[:-3] + "y")
    if lowered.endswith("ves"):
        candidates.append(lowered[:-3] + "f")
    if lowered.endswith("es"):
        candidates.append(lowered[:-2])
    if lowered.endswith("s"):
        candidates.append(lowered[:-1])
    return next((vocabulary[c] for c in candidates if c in vocabulary), None)


class Description:
    """A parsed "a[n] / another / one or more [other] `<noun>` [you control]"
    permanent description, judged against a `GameEvent`'s subject."""

    def __init__(
        self,
        *,
        types: frozenset[Type],
        subtypes: frozenset[str],
        other: bool,
        you_control: bool,
        batched: bool,
    ) -> None:
        self.types = types
        self.subtypes = subtypes
        self.other = other
        self.you_control = you_control
        #: "one or more `<plural>`" - CR 603.2c's one event however many
        #: objects the one instruction reached.
        self.batched = batched

    def matches(self, event: GameEvent, source: CardState, controller: str) -> bool:
        if self.other and event.subject_id == source.id:
            return False
        if self.you_control and event.subject_controller != controller:
            return False
        if self.types and not self.types & set(event.subject_types or ()):
            return False
        if self.subtypes:
            have = {word.lower() for word in event.subject_subtypes or ()}
            if not {word.lower() for word in self.subtypes} & have:
                return False
        return True


def parse_description(text: str) -> Description | None:
    """`text` as a `Description`, or `None` when any word of its noun is not a
    card type or a subtype (a qualifier this does not read is never guessed
    at)."""
    match = _DESCRIPTION_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None
    words = [w for w in re.split(r",\s*(?:or\s+)?|\s+or\s+|\s+and/or\s+", match.group("noun")) if w]
    types: set[Type] = set()
    subtypes: set[str] = set()
    for word in words:
        word = word.strip()
        card_type = _CARD_TYPE_WORDS.get(word.lower())
        if card_type is not None:
            types.add(card_type)
            continue
        if word.lower() in ("permanent", "permanents"):
            continue
        if not word[:1].isupper():
            return None
        subtype = singular_subtype(word)
        if subtype is None:
            return None
        subtypes.add(subtype)
    if types and subtypes:
        return None
    lowered = match.group(0).lower()
    return Description(
        types=frozenset(types),
        subtypes=frozenset(subtypes),
        other=bool(match.group("another") or match.group("other")),
        you_control=match.group("you_control") is not None,
        batched=lowered.startswith("one or more"),
    )


# ---------------------------------------------------------------------------
# "Whenever you put a[n]/one or more <kind> counter(s) on <description>"
# ---------------------------------------------------------------------------

_YOU_PUT_COUNTERS_CONDITION = re.compile(
    r"^you put (?:an?|one or more) (?P<kind>[+-]1/[+-]1|[a-z]+) counters? on "
    r"(?P<description>.+)$",
    re.IGNORECASE,
)


def _you_put_counters(condition: str) -> tuple[str, Description] | None:
    match = _YOU_PUT_COUNTERS_CONDITION.fullmatch(" ".join(condition.split()))
    if match is None:
        return None
    description = parse_description(match.group("description"))
    if description is None:
        return None
    return match.group("kind").lower(), description


# ---------------------------------------------------------------------------
# "Whenever one or more <description> you control deal damage to a player"
# ---------------------------------------------------------------------------

_ONE_OR_MORE_DEAL_DAMAGE_CONDITION = re.compile(
    r"^(?P<description>one or more .+? you control) deal damage to "
    r"(?P<recipient>a player|an opponent)$",
    re.IGNORECASE,
)


def _deal_damage(condition: str) -> tuple[Description, bool] | None:
    match = _ONE_OR_MORE_DEAL_DAMAGE_CONDITION.fullmatch(" ".join(condition.split()))
    if match is None:
        return None
    description = parse_description(match.group("description"))
    if description is None:
        return None
    return description, match.group("recipient").lower() == "an opponent"


def counter_trigger_events(condition: str) -> frozenset[TriggerEvent | ExtraTriggerEvent]:
    """The events one of this module's conditions watches, or an empty set.

    Asked by `machines/triggers._unread_trigger_events` after its own shapes,
    so an ability `machines/abilities._trigger_event` left with `event=None`
    is kept (`triggered_abilities_of`) and reaches `condition_matches`."""
    if _you_put_counters(condition) is not None:
        return frozenset({ExtraTriggerEvent.COUNTERS_PUT})
    if _deal_damage(condition) is not None:
        return frozenset({ExtraTriggerEvent.COMBAT_DAMAGE_TO_PLAYERS, TriggerEvent.DEALS_DAMAGE})
    return frozenset()


def counter_condition_matches(
    game: Game,
    ability: TriggeredAbility,
    source: CardState,
    controller: str,
    event: GameEvent,
) -> bool | None:
    """Whether `event` matches one of this module's conditions, or `None`
    when the condition is not one of them."""
    put = _you_put_counters(ability.condition)
    if put is not None:
        kind, description = put
        if event.event is not ExtraTriggerEvent.COUNTERS_PUT:
            return False
        if (event.counter_kind or "").lower() != kind:
            return False
        # CR 122.6a: "you put" - the player who followed the instruction.
        if event.player != controller:
            return False
        if not description.matches(event, source, controller):
            return False
        # CR 603.2c: "one or more" is one event, however many objects it reached.
        return not (description.batched and _already_pending(game, ability, source, event))
    damage = _deal_damage(ability.condition)
    if damage is not None:
        description, opponent_only = damage
        return _damage_matches(game, description, opponent_only, source, controller, event)
    return None


def _already_pending(
    game: Game, ability: TriggeredAbility, source: CardState, event: GameEvent
) -> bool:
    """Whether this very ability already triggered off an earlier object of
    the same instruction - still waiting in `Game.pending_triggers` (CR
    603.3: nothing is put on the stack until a player would receive priority,
    so every counter one instruction places lands in the same wait)."""
    for pending in game.pending_triggers:
        if pending.source_id != source.id:
            continue
        if getattr(pending.ability, "text", None) != ability.text:
            continue
        earlier = pending.event
        if (
            earlier is not None
            and earlier.event is ExtraTriggerEvent.COUNTERS_PUT
            and earlier.player == event.player
            and earlier.counter_kind == event.counter_kind
        ):
            return True
    return False


def _damage_matches(
    game: Game,
    description: Description,
    opponent_only: bool,
    source: CardState,
    controller: str,
    event: GameEvent,
) -> bool:
    """CR 120.1's damage to a player by one or more described permanents.

    Combat damage is one `COMBAT_DAMAGE_TO_PLAYERS` event per player per step
    (CR 510.2's simultaneous damage, CR 603.2c's one event), judged off the
    step's own records - what each source *was* as it dealt the damage.
    Noncombat damage is its own `DEALS_DAMAGE` event, judged off the source as
    the event recorded it; the combat half of that event is refused so a
    combat hit is never counted twice."""
    if event.player is None:
        return False
    if opponent_only and event.player == controller:
        return False
    if event.event is ExtraTriggerEvent.COMBAT_DAMAGE_TO_PLAYERS:
        records = game.combat_damage_to_players_this_turn
        step = records[len(records) - (event.amount or 0) :] if event.amount else []
        for record in step:
            if record.player != event.player or record.controller != controller:
                continue
            if description.other and record.source_id == source.id:
                continue
            if description.subtypes:
                have = {word.lower() for word in record.creature_types}
                if not {word.lower() for word in description.subtypes} & have:
                    continue
            elif description.types and Type.CREATURE not in description.types:
                continue
            return True
        return False
    if event.event is TriggerEvent.DEALS_DAMAGE and not event.combat:
        if event.target_id is not None:
            return False
        return description.matches(event, source, controller)
    return False


# ---------------------------------------------------------------------------
# Statics over counters (CR 604.2, CR 611.3a, CR 613.1f)
# ---------------------------------------------------------------------------

_KEYWORDS = r"(?P<keywords>[a-z]+(?: [a-z]+)?(?:(?:,\s*|,? and )[a-z]+(?: [a-z]+)?)*)"

#: "As long as you've put one or more `<kind>` counters on `<this>` this
#: turn, `<this | he | she | it>` has `<keywords>`." (Beast, Erudite
#: Aerialist). The source's own name reaches here already rewritten to "this
#: permanent" (`machines/abilities.self_normalized_effect_text`, CR 201.5).
_PUT_ON_SELF_THIS_TURN_GRANT_RE = re.compile(
    r"^as long as you(?:'ve| have) put one or more (?P<kind>[+-]1/[+-]1|[a-z]+) counters? "
    r"on this (?:creature|permanent) this turn, "
    r"(?:he|she|it|they|this (?:creature|permanent)) (?:has|have) " + _KEYWORDS + r"\.?$",
    re.IGNORECASE,
)

#: "Each creature you control that you've put one or more `<kind>` counters
#: on this turn has `<keywords>`." (Kid Loki).
_EACH_PUT_ON_THIS_TURN_GRANT_RE = re.compile(
    r"^each (?P<other>other )?creature you control that you(?:'ve| have) put one or more "
    r"(?P<kind>[+-]1/[+-]1|[a-z]+) counters? on this turn (?:has|have) " + _KEYWORDS + r"\.?$",
    re.IGNORECASE,
)

#: "Creatures you control with `<kind>` counters on them have `<keywords>`."
#: (Training Regimen, Badgermole) - the plural of `machines/layers`'s own
#: "Each creature you control with a `<kind>` counter on it has ..." (Gallia,
#: the Merrymaker), the same counter-gated grant.
_CREATURES_WITH_COUNTERS_GRANT_RE = re.compile(
    r"^(?P<other>other )?creatures you control with (?P<kind>[+-]1/[+-]1|[a-z]+) counters "
    r"on them (?:has|have) " + _KEYWORDS + r"\.?$",
    re.IGNORECASE,
)


def put_this_turn(context: object, putter: str | None, permanent: CardState, kind: str) -> bool:
    """Whether `putter` has put one or more `kind` counters on this very
    object (CR 400.7: this incarnation of it) this turn, off
    `LayerContext.counters_put_this_turn`."""
    records = getattr(context, "counters_put_this_turn", ())
    return any(
        who == putter
        and on == permanent.id
        and stamp in (None, permanent.zone_change_stamp)
        and placed.lower() == kind.lower()
        for who, on, placed, stamp in records
    )


#: "As long as there are `<N>` or more `<kind>` counters on this `<type>`,
#: `<group>` you control get `<power>/<toughness>`." (SOS's Comforting
#: Counsel; Obscura Ascendancy, the off-pool generality proof, whose
#: "Spirits you control" is a subtype list rather than the bare word
#: "creatures") - CR 611.3a's own "isn't 'locked in'" threshold static,
#: gated on the *source's own* counter count rather than a board-wide count
#: (`machines/layers.py`'s own `_BOARD_COUNT_GATE_RE` reads "as long as you
#: control N or more `<type>`" instead - a different subject entirely). CR
#: 604.2/611.3a mean the gate is re-asked on every CR 613.5 computation, not
#: fixed once when the permanent entered.
_COUNTER_THRESHOLD_ANTHEM_RE = re.compile(
    r"^as long as there (?:is|are) (?P<q>[a-z]+|\d+) or more "
    r"(?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on this [a-z]+, "
    r"(?P<other>[Oo]ther )?(?P<group>[a-zA-Z]+) you control get "
    r"(?P<power>[+-]\d+)/(?P<toughness>[+-]\d+)\.?$",
    re.IGNORECASE,
)


def _counter_threshold_anthem_builder(
    kind: str, threshold: int, power: int, toughness: int, *, other: bool, group: str, line: str
):  # noqa: ANN202
    from . import layers

    is_creatures = group.lower() == "creatures"
    subtypes = None if is_creatures else layers._subtype_list_words(group)

    def builder(source: CardState, timestamp: int, targets, context) -> list:  # noqa: ANN001
        if source.counter_count(kind) < threshold:
            return []
        if is_creatures:
            inner = layers._anthem_builder(
                power, toughness, other=other, whose="you control", line=line
            )
        else:
            inner = layers._filtered_anthem_builder(
                subtypes, power, toughness, [], other=other, line=line
            )
        return inner(source, timestamp, targets, context)

    return builder


def parse_static_layer_sentence(sentence: str):  # noqa: ANN201 - EffectBuilder
    """A static counter sentence as a `machines/layers` `EffectBuilder`, or
    `None`. Asked first by `machines/layers._parse_static_layer_sentence`."""
    from ..numbers import parse_count
    from . import layers

    text = " ".join(sentence.split())
    match = _COUNTER_THRESHOLD_ANTHEM_RE.fullmatch(text)
    if match is not None:
        threshold = parse_count(match.group("q"), article=False)
        if threshold is None:
            return None
        group = match.group("group")
        if group.lower() != "creatures" and layers._subtype_list_words(group) is None:
            return None
        kind = match.group("kind").lower()
        return _counter_threshold_anthem_builder(
            kind,
            threshold,
            int(match.group("power")),
            int(match.group("toughness")),
            other=match.group("other") is not None,
            group=group,
            line=sentence,
        )
    match = _PUT_ON_SELF_THIS_TURN_GRANT_RE.fullmatch(text)
    if match is not None:
        keywords = layers._split_and_validate_keywords(match.group("keywords"))
        if keywords is None:
            return None
        kind = match.group("kind").lower()
        return layers._context_gated_self_static_builder(
            lambda source, context: put_this_turn(context, source.controller, source, kind),
            keywords,
            line=sentence,
            description=f"as long as you've put a {kind} counter on it this turn",
        )
    match = _EACH_PUT_ON_THIS_TURN_GRANT_RE.fullmatch(text)
    if match is not None:
        keywords = layers._split_and_validate_keywords(match.group("keywords"))
        if keywords is None:
            return None
        return _each_put_on_this_turn_builder(
            match.group("kind").lower(),
            keywords,
            other=match.group("other") is not None,
            line=sentence,
        )
    match = _CREATURES_WITH_COUNTERS_GRANT_RE.fullmatch(text)
    if match is not None:
        keywords = layers._split_and_validate_keywords(match.group("keywords"))
        if keywords is None:
            return None
        return layers._counter_gated_keyword_grant_builder(
            match.group("kind").lower(),
            keywords,
            other=match.group("other") is not None,
            line=sentence,
        )
    return None


def _each_put_on_this_turn_builder(kind: str, keywords: list[str], *, other: bool, line: str):  # noqa: ANN202
    """Kid Loki's grant: one layer 6 effect (CR 613.1f) per keyword and per
    creature its controller put a `kind` counter on this turn, rebuilt on
    every CR 613.5 computation from a fresh `LayerContext` - so a creature
    that changes control, or a new turn, drops out at once (CR 611.3a)."""
    from . import layers

    def builder(source, timestamp, targets, context):  # noqa: ANN001, ANN202
        marked = [
            (card_id, stamp)
            for who, card_id, placed, stamp in getattr(context, "counters_put_this_turn", ())
            if who == source.controller and placed.lower() == kind
        ]
        effects = []
        for card_id, stamp in dict.fromkeys(marked):
            if other and card_id == source.id:
                continue
            for keyword in keywords:
                effects.append(
                    layers.ContinuousEffect(
                        description=(
                            f"{source.name}: a creature you put a {kind} counter on this "
                            f"turn has {keyword}"
                        ),
                        layer=layers.Layer.ABILITY,
                        timestamp=timestamp,
                        source_id=source.id,
                        source_ability=layers._source_line_for(source, line),
                        selector=layers.CreatureControlledByWithId(
                            username=source.controller, card_id=card_id, stamp=stamp
                        ),
                        modification=layers.grant_ability(keyword),
                    )
                )
        return effects

    return builder


# ---------------------------------------------------------------------------
# Counting the history: "for each +1/+1 counter you've put on creatures under
# your control this turn" (Iridescent Hornbeetle)
# ---------------------------------------------------------------------------

_FOR_EACH_COUNTER_PUT_THIS_TURN_RE = re.compile(
    r"^(?P<kind>[+-]1/[+-]1|[a-z]+) counters? you(?:'ve| have) put on "
    r"(?P<noun>creatures|permanents|artifacts)"
    r"(?P<yours> (?:under your control|you control))? this turn$",
    re.IGNORECASE,
)


def counter_history_count(phrase: str):  # noqa: ANN201 - (game, controller) -> int
    """ "`<kind>` counter[s] you've put on `<creatures>` [under your control]
    this turn" as an `effects.count_expression` reader, or `None`.

    Counted off `Game.counters_put_this_turn`: every counter of that kind
    the controller put (CR 122.6a) on a permanent of that type, judged - type
    and control both - as it was when the counters landed."""
    match = _FOR_EACH_COUNTER_PUT_THIS_TURN_RE.fullmatch(" ".join(phrase.split()))
    if match is None:
        return None
    kind = match.group("kind").lower()
    card_type = _CARD_TYPE_WORDS.get(match.group("noun").lower())
    yours = match.group("yours") is not None

    def count(game: Game, controller: str) -> int:
        return sum(
            record.amount
            for record in game.counters_put_this_turn
            if record.putter == controller
            and record.kind.lower() == kind
            and (card_type is None or card_type in record.types)
            and (not yours or record.controller == controller)
        )

    return count


# ---------------------------------------------------------------------------
# Resolution text (CR 608.2): the whole-text readers `machines/effects.py`
# asks first, for an ability (`_ability_effect_or_notice`) and a spell
# (`_spell_effect_or_notice`). Each returns a `(game, stack_object) -> None`
# callable, which is the shape both of those callers hand back.
# ---------------------------------------------------------------------------

#: "For each kind of counter on target permanent or player, give that
#: permanent or player another counter of that kind." (Powerful Broker,
#: Maulfist Revolutionary, Skyship Plunderer) - CR 701.34a's proliferate gift
#: ("give each one additional counter of each kind that permanent or player
#: already has") to one target.
_EACH_KIND_ANOTHER_COUNTER_RE = re.compile(
    r"^for each kind of counter on target (?P<noun>permanent or player|permanent|player|creature),"
    r" give that (?P=noun) another counter of that kind\.?$",
    re.IGNORECASE,
)


def _each_kind_another_counter(text: str):  # noqa: ANN202
    if _EACH_KIND_ANOTHER_COUNTER_RE.fullmatch(text) is None:
        return None

    def effect(game: Game, stack_object) -> None:  # noqa: ANN001
        from ..models.card_state import CardState
        from ..models.player import Player

        for target in game.resolve_targets(stack_object):
            if isinstance(target, CardState):
                for kind, count in list(target.counters.counts.items()):
                    if count > 0 and target.zone.value == "battlefield":
                        game.add_counters(target, kind, 1)
            elif isinstance(target, Player):
                for kind, count in list(target.counters.counts.items()):
                    if count > 0:
                        game.add_player_counters(target, kind, 1)

    return effect


#: "Create that many `<token>` tokens[ with `<tail>`]." (The Astonishing
#: Ant-Man) - CR 701.7a's token creation, its count CR 607.1's "that many"
#: back to the count its own cost or triggering event carried
#: (`effects.that_many`).
_CREATE_THAT_MANY_TOKENS_RE = re.compile(
    r"^create that many (?P<desc>.+?) tokens?(?: with (?P<tail>.+?))?\.?$",
    re.IGNORECASE,
)


def _create_that_many_tokens(text: str, *, for_spell: bool):  # noqa: ANN202
    from . import effects

    match = _CREATE_THAT_MANY_TOKENS_RE.fullmatch(text)
    if match is None:
        return None
    desc = match.group("desc")
    tapped = desc.lower().startswith("tapped ")
    if tapped:
        desc = desc[len("tapped ") :]
    definition = effects._token_definition_from_words(desc, match.group("tail"))
    if definition is None:
        return None

    def effect(game: Game, stack_object) -> None:  # noqa: ANN001
        # Namor the Sub-Mariner's "that many" is its condition's own count
        # of coloured mana symbols, not the event's or a cost's.
        count = effects.color_pip_count_named_by_trigger(stack_object)
        if count is None:
            count = effects._that_many_or_notice(
                game,
                text,
                source_id=getattr(stack_object, "source_id", None),
                source_name=stack_object.name,
                stack_object=stack_object,
            )
        if not count or count <= 0:
            return
        controller = game.controller_of(stack_object).username
        effects.create_tokens(game, definition, controller, count, tapped=tapped)

    return effect


#: "[You may] remove a counter from a[n] `<description>` you control. If you
#: do, `<effect>`." (Mister Hyde, Monster Within's mode; Sanctuary Warden) -
#: CR 118.12: the removal is a cost paid as the ability resolves, and "if you
#: do" asks whether it was paid.
_REMOVE_A_COUNTER_IF_YOU_DO_RE = re.compile(
    r"^(?P<may>you may )?remove (?:a|one) counter from (?P<description>an? .+? you control)\. "
    r"if you do, (?P<rest>.+)$",
    re.IGNORECASE,
)


def _remove_a_counter_if_you_do(text: str, *, for_spell: bool):  # noqa: ANN202
    from . import effects

    match = _REMOVE_A_COUNTER_IF_YOU_DO_RE.fullmatch(text)
    if match is None:
        return None
    description = parse_description(match.group("description"))
    if description is None:
        return None
    rest_text = match.group("rest").strip()
    rest_text = rest_text[:1].upper() + rest_text[1:]
    rest = (
        effects._spell_effect_or_notice(rest_text)
        if for_spell
        else effects._ability_effect_or_notice(rest_text)
    )
    if rest is None or effects._is_notice_only(rest):
        return None
    optional = match.group("may") is not None

    def effect(game: Game, stack_object) -> None:  # noqa: ANN001
        if _remove_one_counter(game, stack_object, description, optional=optional):
            rest(game, stack_object)

    return effect


def _remove_one_counter(
    game: Game,
    stack_object,  # noqa: ANN001
    description: Description,
    *,
    optional: bool,
) -> bool:
    """Pay "remove a counter from a[n] `<description>` you control" on
    resolution (CR 118.12), asking which permanent and - when it carries
    several kinds - which kind. `False` when it was not paid: declined, or no
    permanent of the description the controller controls has a counter."""
    from .decisions import Decision, DecisionKind, source_id_of

    controller = game.controller_of(stack_object).username
    board = game.computed_board()
    candidates = []
    for permanent in game.battlefield:
        chars = board.of(permanent)
        if chars.controller != controller or not permanent.counters.counts:
            continue
        if description.types and not description.types & set(chars.types):
            continue
        if description.subtypes and not {s.lower() for s in description.subtypes} & {
            s.lower() for s in chars.subtypes
        }:
            continue
        candidates.append(permanent)
    if not candidates:
        return False
    source_id = source_id_of(stack_object)
    if optional and not game.may(
        controller, "remove a counter", source=stack_object.name, source_id=source_id
    ):
        return False
    chosen_ids = game.ask(
        Decision(
            kind=DecisionKind.CHOOSE_CARDS,
            player=controller,
            prompt="choose a permanent you control to remove a counter from",
            source=stack_object.name,
            source_id=source_id,
            amount=1,
            cards=tuple(permanent.id for permanent in candidates),
            card_labels=tuple(permanent.name for permanent in candidates),
        )
    )
    by_id = {permanent.id: permanent for permanent in candidates}
    chosen = next((by_id[card_id] for card_id in chosen_ids or () if card_id in by_id), None)
    if chosen is None:
        return False
    kinds = tuple(sorted(kind for kind, count in chosen.counters.counts.items() if count > 0))
    kind = kinds[0]
    if len(kinds) > 1:
        answer = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_A_MODE,
                player=controller,
                prompt=f"choose the kind of counter to remove from {chosen.name}",
                source=stack_object.name,
                source_id=source_id,
                options=kinds,
            )
        )
        kind = answer if answer in kinds else kinds[0]
    chosen.remove_counters(kind, 1)
    return True


#: "create a `<Predefined>` token or a `<Predefined>` token" (Ant-Man's Army,
#: Tireless Provisioner) - CR 111.10's predefined tokens, one of the two, the
#: controller's choice as it resolves (CR 608.2d).
_CREATE_ONE_TOKEN_OR_ANOTHER_RE = re.compile(
    r"^(?i:create an?) (?P<first>[A-Z][\w'-]*) (?i:token or an?) (?P<second>[A-Z][\w'-]*)"
    r" (?i:token)\.?$"
)


def _create_one_token_or_another(text: str, *, for_spell: bool):  # noqa: ANN202
    from ..models.token import PREDEFINED
    from . import effects
    from .decisions import Decision, DecisionKind, source_id_of

    match = _CREATE_ONE_TOKEN_OR_ANOTHER_RE.fullmatch(text)
    if match is None:
        return None
    options = (match.group("first"), match.group("second"))
    if any(option not in PREDEFINED for option in options):
        return None

    def effect(game: Game, stack_object) -> None:  # noqa: ANN001
        controller = game.controller_of(stack_object).username
        answer = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_A_MODE,
                player=controller,
                prompt="choose which token to create",
                source=stack_object.name,
                source_id=source_id_of(stack_object),
                options=options,
            )
        )
        chosen = answer if answer in options else options[0]
        effects.create_tokens(game, PREDEFINED[chosen], controller, 1)

    return effect


#: "`<effect>` if there are N or more `<quality>` cards in your graveyard.
#: Otherwise, `<effect>`." (HYDRA Troopers) - CR 608.2c: one condition, read
#: as it resolves, choosing between two instructions.
_IF_GRAVEYARD_COUNT_OTHERWISE_RE = re.compile(
    r"^(?P<first>.+?) if there are (?P<n>[\w-]+) or more (?P<quality>[a-z ]+?) cards in your "
    r"graveyard\. otherwise, (?P<second>.+)$",
    re.IGNORECASE,
)


def _sentence(text: str) -> str:
    text = text.strip()
    text = text[:1].upper() + text[1:]
    return text if text.endswith(".") else text + "."


def _resolution_clause(text: str, *, for_spell: bool):  # noqa: ANN202
    """`text` read by `machines/effects`' own whole-text dispatcher for the
    same kind of object, or `None` for unread or notice-only text."""
    from . import effects

    parsed = (
        effects._spell_effect_or_notice(_sentence(text))
        if for_spell
        else effects._ability_effect_or_notice(_sentence(text))
    )
    if parsed is None or effects._is_notice_only(parsed):
        return None
    return parsed


def _if_graveyard_count_otherwise(text: str, *, for_spell: bool):  # noqa: ANN202
    from ..numbers import parse_count
    from . import effects

    match = _IF_GRAVEYARD_COUNT_OTHERWISE_RE.fullmatch(text)
    if match is None:
        return None
    threshold = parse_count(match.group("n"), article=False)
    counter = effects.count_expression(
        f"the number of {match.group('quality')} cards in your graveyard"
    )
    first = _resolution_clause(match.group("first"), for_spell=for_spell)
    second = _resolution_clause(match.group("second"), for_spell=for_spell)
    if threshold is None or counter is None or first is None or second is None:
        return None

    def effect(game: Game, stack_object) -> None:  # noqa: ANN001
        controller = game.controller_of(stack_object).username
        if counter(game, controller) >= threshold:
            first(game, stack_object)
        else:
            second(game, stack_object)

    return effect


#: "Target player investigates. `<rest>`" (Panther Pounce) - CR 701.16a's
#: Clue for the targeted player, then the rest of the spell against its own
#: (card) targets.
_TARGET_PLAYER_INVESTIGATES_RE = re.compile(
    r"^target (?P<who>player|opponent) investigates\.(?: (?P<rest>.+))?$", re.IGNORECASE
)


def _target_player_investigates(text: str, *, for_spell: bool):  # noqa: ANN202
    from ..models.player import Player
    from . import effects

    match = _TARGET_PLAYER_INVESTIGATES_RE.fullmatch(text)
    if match is None:
        return None
    rest = None
    if match.group("rest"):
        rest = _resolution_clause(match.group("rest"), for_spell=for_spell)
        if rest is None:
            return None

    def effect(game: Game, stack_object) -> None:  # noqa: ANN001
        player = next(
            (t for t in game.resolve_targets(stack_object) if isinstance(t, Player)), None
        )
        if player is not None:
            effects.investigate(game, player.username, 1)
        if rest is not None:
            rest(game, stack_object)

    return effect


#: "Target player gains N life, then searches their library for a[n]
#: `<quality>` card, puts it onto the battlefield [tapped]/into their hand,
#: then shuffles. `<rest>`" (Restorative Technique) - the targeted player
#: gains the life (CR 119.3) and does the searching (CR 701.23a).
_TARGET_PLAYER_GAINS_THEN_SEARCHES_RE = re.compile(
    r"^target player gains (?P<n>[\w-]+) life, then searches their library for "
    r"(?:an? )?(?P<quality>.+?) card, puts it (?P<dest>onto the battlefield(?P<tapped> tapped)?"
    r"|into their hand), then shuffles\.(?: (?P<rest>.+))?$",
    re.IGNORECASE,
)


def _target_player_gains_then_searches(text: str, *, for_spell: bool):  # noqa: ANN202
    from ..models.player import Player
    from ..models.zone import Zone
    from ..numbers import parse_count
    from . import effects
    from .decisions import source_id_of

    match = _TARGET_PLAYER_GAINS_THEN_SEARCHES_RE.fullmatch(text)
    if match is None:
        return None
    amount = parse_count(match.group("n"))
    quality = match.group("quality")
    if amount is None or not effects._search_quality_is_readable(quality):
        return None
    matches = effects._quality_matcher(quality)
    to_battlefield = match.group("dest").lower().startswith("onto")
    tapped = match.group("tapped") is not None
    rest = None
    if match.group("rest"):
        rest = _resolution_clause(match.group("rest"), for_spell=for_spell)
        if rest is None:
            return None

    def effect(game: Game, stack_object) -> None:  # noqa: ANN001
        controller = game.controller_of(stack_object).username
        player = next(
            (t for t in game.resolve_targets(stack_object) if isinstance(t, Player)), None
        )
        if player is not None:
            game.gain_life(player, amount)
            game.search_and_put(
                player,
                matches,
                destination=Zone.BATTLEFIELD if to_battlefield else Zone.HAND,
                count=1,
                tapped=tapped,
                source=stack_object.name,
                source_id=source_id_of(stack_object),
                caused_by=controller,
            )
        if rest is not None:
            rest(game, stack_object)

    return effect


#: "[You may] search your library and/or graveyard for a[n] `<quality>` card
#: [with no abilities] [with mana value N or less][, reveal it,] [and] put it
#: onto the battlefield [tapped] / into your hand [with N additional `<kind>`
#: counters on it]. [If N is M or greater, it gains `<keywords>` until end of
#: turn.] If you search your library this way, shuffle." (Vision Quest,
#: Fang-Druid Summoner) - CR 701.23a's search of two zones, one of them
#: optional ("and/or"), with the shuffle owed only for the library.
_SEARCH_LIBRARY_AND_OR_GRAVEYARD_RE = re.compile(
    r"^(?P<may>you may )?search your library and/or graveyard for (?:an? )?(?P<quality>.+?) card"
    r"(?P<no_abilities> with no abilities)?"
    r"(?: with mana value (?P<mv>x|\d+) or less)?"
    r"(?:,? reveal it,)?(?: and)? put it "
    r"(?P<dest>onto the battlefield(?P<tapped> tapped)?|into your hand)"
    r"(?: with (?P<counters>x|[\w-]+) additional (?P<kind>[+-]1/[+-]1|[a-z]+) counters? on it)?\."
    r"(?: if (?P<cond_x>x|\d+) is (?P<min>\d+) or greater, it gains (?P<keywords>[a-z ,]+?)"
    r" until end of turn\.)?"
    r" if you search your library this way, shuffle\.?$",
    re.IGNORECASE,
)


def _announced_x(game: Game, stack_object) -> int:  # noqa: ANN001
    """CR 107.3a's X: a spell's from its cast record, an ability's own."""
    from ..models.card_state import CardState

    if isinstance(stack_object, CardState):
        return game.cast_record(stack_object).x_value
    return getattr(stack_object, "x_value", None) or 0


def _card_quality(quality: str):  # noqa: ANN202 - Callable[[CardState], bool] | None
    """A search's stated quality as a card predicate: "artifact creature" is
    both card types at once (CR 205.2a's card types, every one the type line
    prints), anything else `machines/effects`' own search-quality reader."""
    from . import effects

    words = quality.lower().split()
    types = [_CARD_TYPE_WORDS.get(word) for word in words]
    if len(words) > 1 and all(types):
        wanted = frozenset(t for t in types if t is not None)
        return lambda state: wanted <= set(state.types)
    if not effects._search_quality_is_readable(quality):
        return None
    return effects._quality_matcher(quality)


def _search_library_and_or_graveyard(text: str, *, for_spell: bool):  # noqa: ANN202
    from ..models.zone import Zone
    from ..numbers import parse_count
    from . import effects
    from .decisions import Decision, DecisionKind, source_id_of
    from .layers import ContinuousEffect, Duration, Layer, grant_ability, only_this_incarnation

    match = _SEARCH_LIBRARY_AND_OR_GRAVEYARD_RE.fullmatch(text)
    if match is None:
        return None
    quality = match.group("quality")
    matches_quality = _card_quality(quality)
    if matches_quality is None:
        return None
    no_abilities = match.group("no_abilities") is not None

    def number(word: str | None, x: int) -> int | None:
        if word is None:
            return None
        return x if word.lower() == "x" else parse_count(word)

    for word in (match.group("mv"), match.group("counters"), match.group("cond_x")):
        if word is not None and word.lower() != "x" and parse_count(word) is None:
            return None
    keywords = None
    if match.group("keywords"):
        keywords = effects.split_and_validate_keywords(match.group("keywords"))
        if keywords is None:
            return None
    to_battlefield = match.group("dest").lower().startswith("onto")
    tapped = match.group("tapped") is not None
    kind = (match.group("kind") or "+1/+1").lower()
    optional = match.group("may") is not None

    def effect(game: Game, stack_object) -> None:  # noqa: ANN001
        player = game.controller_of(stack_object)
        source = stack_object.name
        source_id = source_id_of(stack_object)
        x = _announced_x(game, stack_object)
        ceiling = number(match.group("mv"), x)

        def qualifies(state: CardState) -> bool:
            if not matches_quality(state):
                return False
            if no_abilities and (state.oracle_text or "").strip():
                return False
            return ceiling is None or state.mana_value <= ceiling

        if optional and not game.may(
            player,
            f"search your library and/or graveyard for {quality}",
            source=source,
            source_id=source_id,
        ):
            return
        searched_library = game.may(
            player, "search your library too", source=source, source_id=source_id
        )
        candidates = [card for card in player.graveyard if qualifies(card)]
        if searched_library:
            candidates += [card for card in player.library if qualifies(card)]
        found = None
        if candidates:
            chosen_ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=player.username,
                    prompt=f"choose up to one {quality} card",
                    source=source,
                    source_id=source_id,
                    amount=1,
                    cards=tuple(card.id for card in candidates),
                    card_labels=tuple(card.name for card in candidates),
                    exact=False,
                )
            )
            wanted = next(iter(chosen_ids or ()), None)
            pick = next((card for card in candidates if card.id == wanted), None)
            if pick is not None:
                taken = game.search_library(
                    player,
                    lambda state, pick_id=pick.id: state.id == pick_id,
                    count=1,
                    shuffle=False,
                    source=source,
                    source_id=source_id,
                    zone=pick.zone,
                    caused_by=player.username,
                )
                found = taken[0] if taken else None
        if found is not None:
            if match.group(0).lower().find("reveal it") != -1:
                game.reveal(found, source=source)
            if to_battlefield:
                permanent = game.put_onto_battlefield(found, player.username, tapped=tapped)
                counters = number(match.group("counters"), x)
                if counters and permanent.zone is Zone.BATTLEFIELD:
                    game.add_counters(permanent, kind, counters)
                condition = number(match.group("cond_x"), x)
                if (
                    keywords
                    and permanent.zone is Zone.BATTLEFIELD
                    and condition is not None
                    and condition >= int(match.group("min"))
                ):
                    for keyword in keywords:
                        game.continuous_effects.add(
                            ContinuousEffect(
                                description=f"{source}: {permanent.name} gains {keyword}",
                                layer=Layer.ABILITY,
                                timestamp=game.continuous_effects.tick(),
                                duration=Duration.UNTIL_END_OF_TURN,
                                source_id=getattr(stack_object, "source_id", None),
                                selector=only_this_incarnation(
                                    permanent, permanent.zone_change_stamp
                                ),
                                modification=grant_ability(keyword),
                            ),
                            game,
                        )
            else:
                player.add(found, Zone.HAND)
        if searched_library:
            game.shuffle_library(player)

    return effect


#: "choose up to that many target `<description>`" - Heroic Feast's own
#: target count, fixed by the triggering event as the ability goes on the
#: stack (CR 601.2c via CR 603.3d).
_UP_TO_THAT_MANY_TARGET_RE = re.compile(r"\bup to that many (?=target\b)", re.IGNORECASE)


def event_count_target_text(text: str, event: GameEvent | None) -> str:
    """`text` with "up to that many target" written as the event's own count,
    for `machines/targeting.profile_for_text` to read - or `text` unchanged
    when there is no count to write in."""
    if event is None or event.amount is None or not _UP_TO_THAT_MANY_TARGET_RE.search(text):
        return text
    return _UP_TO_THAT_MANY_TARGET_RE.sub(f"up to {event.amount} ", text)


#: "choose up to that many/N target `<description>`. Put a[n]/N `<kind>`
#: counter[s] on each of them." (Heroic Feast) - CR 122.1's counters on every
#: chosen target still legal as it resolves (CR 608.2b).
_CHOOSE_TARGETS_PUT_COUNTER_ON_EACH_RE = re.compile(
    r"^choose (?:up to )?(?:that many|[\w-]+) target [^.]+\. "
    r"put (?P<n>an?|[\w-]+) (?P<kind>[+-]1/[+-]1|[a-z]+) counters? on each of them\.?$",
    re.IGNORECASE,
)


def _choose_targets_put_counter_on_each(text: str, *, for_spell: bool):  # noqa: ANN202
    from ..numbers import parse_count

    match = _CHOOSE_TARGETS_PUT_COUNTER_ON_EACH_RE.fullmatch(text)
    if match is None:
        return None
    amount = parse_count(match.group("n"))
    if amount is None:
        return None
    kind = match.group("kind").lower()

    def effect(game: Game, stack_object) -> None:  # noqa: ANN001
        for permanent in game.resolve_card_targets(stack_object):
            game.add_counters(permanent, kind, amount)

    return effect


#: "create `<token>`. Put a[n]/N `<kind>` counter[s] on it for each `<kind>`
#: counter on this `<type>`, then put a[n]/N `<kind>` counter[s] on this
#: `<type>`." (Alien Invasion) - "it" is the token just created (CR 608.2c's
#: order: the count is read before the source's own counter is added).
_CREATE_THEN_COUNTERS_PER_SOURCE_COUNTER_RE = re.compile(
    r"^(?P<create>create .+?)\s+put (?P<n>an?|[\w-]+) (?P<kind>[+-]1/[+-]1|[a-z]+) counters? on "
    r"it for each (?P<each>[a-z+/-]+ counters? on this [a-z]+), then put (?P<m>an?|[\w-]+) "
    r"(?P<kind2>[+-]1/[+-]1|[a-z]+) counters? on this [a-z]+\.?$",
    re.IGNORECASE,
)


def _create_then_counters_per_source_counter(text: str, *, for_spell: bool):  # noqa: ANN202
    from ..models.token import is_token
    from ..models.zone import Zone
    from ..numbers import parse_count
    from . import effects
    from .decisions import source_id_of

    if for_spell:
        return None
    match = _CREATE_THEN_COUNTERS_PER_SOURCE_COUNTER_RE.fullmatch(text)
    if match is None:
        return None
    create = effects._parse_token_clause(match.group("create"), for_spell=False)
    per = parse_count(match.group("n"))
    multiplier = effects._for_each_multiplier(match.group("each"))
    own = parse_count(match.group("m"))
    if create is None or per is None or multiplier is None or own is None:
        return None
    kind = match.group("kind").lower()
    own_kind = match.group("kind2").lower()

    def effect(game: Game, ability) -> None:  # noqa: ANN001
        controller = game.controller_of(ability).username
        before = {permanent.id for permanent in game.battlefield}
        create(game, ability)
        created = [
            permanent
            for permanent in game.battlefield
            if permanent.id not in before and is_token(permanent)
        ]
        count = multiplier(game, controller, source_id_of(ability))
        for token in created:
            if per * count > 0:
                game.add_counters(token, kind, per * count)
        source = ability.source(game)
        if source is not None and source.zone is Zone.BATTLEFIELD:
            game.add_counters(source, own_kind, own)

    return effect


#: "When this creature dies, if it had one or more counters on it, create a
#: `<token>`, then put this creature's counters on that token." (SOS's
#: Ambitious Augmenter) - CR 603.4's intervening *if* is already split off
#: `TriggeredAbility.effect` by `machines/abilities.py` before this text is
#: ever seen here, and answered by `machines/conditions/objects.py`'s "it
#: had ... counters on it" reader (`_has_counters`, in its own `READERS`
#: tuple), so only the create-then-move half is this module's to read: CR
#: 400.7/603.10a's last-known information for the already-dead source (the
#: same ternary `_parse_put_its_counters_on_target_clause` and
#: `hangarback_dies` already read in `machines/effects.py`), CR 122.6's
#: counters landing on the object the token clause just created.
_CREATE_TOKEN_THEN_PUT_THIS_CREATURES_COUNTERS_ON_IT_RE = re.compile(
    r"^(?P<create>create .+? tokens?(?:\s+with\s+.+?)?), then put this "
    r"(?:creature|permanent|card)'s counters on (?:that|this) token\.?$",
    re.IGNORECASE,
)


def _create_token_then_put_this_creatures_counters_on_it(text: str, *, for_spell: bool):  # noqa: ANN202
    from ..models.token import is_token
    from ..models.zone import Zone
    from . import effects

    if for_spell:
        return None
    match = _CREATE_TOKEN_THEN_PUT_THIS_CREATURES_COUNTERS_ON_IT_RE.fullmatch(text.strip())
    if match is None:
        return None
    create = effects._parse_token_clause(match.group("create"), for_spell=False)
    if create is None:
        return None

    def effect(game: Game, ability) -> None:  # noqa: ANN001
        source = ability.source(game)
        if source is None:
            return
        counters = (
            source.counters if source.zone is Zone.BATTLEFIELD else source.last_known_counters
        )
        before = {permanent.id for permanent in game.battlefield}
        create(game, ability)
        created = [
            permanent
            for permanent in game.battlefield
            if permanent.id not in before and is_token(permanent)
        ]
        if not created:
            return
        token = created[0]
        for kind, amount in counters.items():
            if amount:
                game.add_counters(token, kind, amount)

    return effect


#: "you may pay {X}. When you do, move X `<kind>` counters from this
#: `<type>` onto `<phrase>`." (SOS's Tester of the Tangential) - CR 118.9's
#: variable-amount cost paid one generic mana at a time, the same "ask again
#: until declined or unaffordable" shape `effects._parse_reflexive_pay_up_
#: to_n_times_choose_modes_clause` already uses for a *fixed* repeat count,
#: unbounded here since {X} prints no ceiling of its own - the loop simply
#: stops the moment `Game.may_pay_mana_cost` is no longer payable (CR 118.3)
#: or the controller declines. CR 603.12's reflexive trigger is then created
#: with the actual paid amount substituted in as a literal count -
#: `effects._MOVE_COUNTER_RE` already reads "move `<n>` ... onto `<phrase>`"
#: for any literal `<n>`, so nothing new is needed to run the consequence
#: itself once X is known.
_REFLEXIVE_MAY_PAY_X_MOVE_COUNTERS_RE = re.compile(
    r"^you may pay \{x\}\.\s*when you do, move x (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? "
    r"from this (?P<noun>[a-z]+) onto (?P<phrase>(?:another )?target .+?)\.?$",
    re.IGNORECASE,
)


def _reflexive_may_pay_x_move_counters(text: str, *, for_spell: bool):  # noqa: ANN202
    from ..models.mana import ManaCost
    from . import effects
    from .decisions import source_id_of
    from .delayed import ReflexiveConsequence

    if for_spell:
        return None
    match = _REFLEXIVE_MAY_PAY_X_MOVE_COUNTERS_RE.fullmatch(text.strip())
    if match is None:
        return None
    kind = match.group("kind").lower()
    noun = match.group("noun")
    phrase = match.group("phrase").strip()
    if not effects._targets_understood(phrase, count_agnostic=False):
        return None
    one_generic = ManaCost.parse("{1}")

    def effect(game: Game, ability) -> None:  # noqa: ANN001
        player = game.controller_of(ability)
        source_id, source_name = effects._permanent_id_and_name(ability, for_spell=False)
        paid = 0
        while game.may_pay_mana_cost(
            player, one_generic, source=source_name, source_id=source_id_of(ability)
        ):
            paid += 1
        if paid <= 0:
            return
        consequence_text = f"move {paid} {kind} counters from this {noun} onto {phrase}."
        game.create_reflexive_trigger(
            text=consequence_text,
            controller=player.username,
            source_id=ability.source_id,
            source_name=source_name,
            callback=ReflexiveConsequence(),
        )

    return effect


#: "you may move any number of `<kind>` counters from this `<type>` onto
#: `<phrase>`." (Scrounging Bandar, the off-pool generality proof for
#: `effects._MOVE_COUNTER_RE`'s "onto another target" widening) - CR 608.2d's
#: open amount with no `DecisionKind` built for it yet, the same documented
#: scoped simplification `effects._parse_remove_up_to_n_counters_from_
#: target_clause` already takes for its own "remove up to N counters": the
#: maximum available rather than a separate "how many" question (recorded
#: here, not hidden, for the identical reason). The move itself is optional
#: (a plain `MAY` question, CR 608.2d), and CR 122.5 checks both halves -
#: source has the counters, destination is still legal - before either one
#: happens.
_MAY_MOVE_ANY_NUMBER_COUNTERS_RE = re.compile(
    r"^you may move any number of (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? from this "
    r"(?P<noun>[a-z]+) onto (?P<phrase>(?:another )?target .+?)\.?$",
    re.IGNORECASE,
)


def _may_move_any_number_counters(text: str, *, for_spell: bool):  # noqa: ANN202
    from ..models.card_state import CardState
    from ..models.zone import Zone
    from . import effects
    from .decisions import Decision, DecisionKind, source_id_of

    if for_spell:
        return None
    match = _MAY_MOVE_ANY_NUMBER_COUNTERS_RE.fullmatch(text.strip())
    if match is None:
        return None
    kind = match.group("kind").lower()
    phrase = match.group("phrase").strip()
    if not effects._targets_understood(phrase, count_agnostic=False):
        return None

    def effect(game: Game, ability) -> None:  # noqa: ANN001
        source = ability.source(game)
        if source is None or source.zone is not Zone.BATTLEFIELD:
            return
        available = source.counter_count(kind)
        if available <= 0:
            return
        player = game.controller_of(ability)
        if not game.ask(
            Decision(
                kind=DecisionKind.MAY,
                player=player.username,
                prompt=f"move {kind} counters from {ability.source_name}",
                source=ability.source_name,
                source_id=source_id_of(ability),
                affirmative_is_legal=True,
            )
        ):
            return
        targets = [
            target
            for target in game.resolve_targets(ability)
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
        ]
        if not targets:
            return
        source.remove_counters(kind, available)
        game.add_counters(targets[0], kind, available)

    return effect


#: "Put a[n] `<kind>` counter on target creature you control, then double
#: the number of `<kind>` counters on that creature." (SOS's Growth Curve) -
#: CR 122.1's counter placement followed immediately by CR 701.10e's
#: doubling of whatever the *same* target now carries (the counter this
#: instruction itself just added included, since CR 608.2c runs the two
#: clauses of one printed instruction in order).
_PUT_COUNTER_THEN_DOUBLE_ON_THAT_RE = re.compile(
    r"^put (?P<n>an?|[\w-]+) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on "
    r"(?P<phrase>target .+?), then double the number of (?P<kind2>\+1/\+1|-1/-1|[a-z]+) "
    r"counters? on (?:that creature|it|this [a-z]+)\.?$",
    re.IGNORECASE,
)


def _put_counter_then_double_on_that(text: str, *, for_spell: bool):  # noqa: ANN202
    from ..models.card_state import CardState
    from ..models.zone import Zone
    from ..numbers import parse_count
    from . import effects

    match = _PUT_COUNTER_THEN_DOUBLE_ON_THAT_RE.fullmatch(text.strip())
    if match is None:
        return None
    if match.group("kind").lower() != match.group("kind2").lower():
        return None
    kind = match.group("kind").lower()
    amount = parse_count(match.group("n"))
    if amount is None:
        return None
    phrase = match.group("phrase").strip()
    if not effects._targets_understood(phrase, count_agnostic=False):
        return None

    def effect(game: Game, stack_object) -> None:  # noqa: ANN001
        targets = [
            target
            for target in game.resolve_targets(stack_object)
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
        ]
        if not targets:
            return
        target = targets[0]
        game.add_counters(target, kind, amount)
        current = target.counter_count(kind)
        if current:
            game.add_counters(target, kind, current)

    return effect


#: "Choose any number of target creatures. Double the number of `<kind>`
#: counters on each of them." (Solidarity of Heroes, the off-pool generality
#: proof of the doubling primitive over a multi-target choice rather than
#: `_put_counter_then_double_on_that`'s single "that creature") - CR 701.10e
#: applied once per chosen, still-legal target (CR 608.2b).
_CHOOSE_ANY_NUMBER_THEN_DOUBLE_EACH_RE = re.compile(
    r"^choose any number of (?P<phrase>target .+?)\. double the number of "
    r"(?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on each of them\.?$",
    re.IGNORECASE,
)


def _choose_any_number_then_double_each(text: str, *, for_spell: bool):  # noqa: ANN202
    from ..models.card_state import CardState
    from ..models.zone import Zone
    from . import effects

    match = _CHOOSE_ANY_NUMBER_THEN_DOUBLE_EACH_RE.fullmatch(text.strip())
    if match is None:
        return None
    phrase = match.group("phrase").strip()
    if not effects._targets_understood(phrase, count_agnostic=True):
        return None
    kind = match.group("kind").lower()

    def effect(game: Game, stack_object) -> None:  # noqa: ANN001
        for target in game.resolve_targets(stack_object):
            if not isinstance(target, CardState) or target.zone is not Zone.BATTLEFIELD:
                continue
            current = target.counter_count(kind)
            if current:
                game.add_counters(target, kind, current)

    return effect


#: "`<Name>` deals `<N>` damage to target creature. You may exile a card
#: from your graveyard. If you do, `<name>` also deals `<M>` damage to that
#: creature's controller." (SOS's Heated Argument) - CR 118.12's optional
#: cost read during resolution (a graveyard card chosen and exiled, CR
#: 608.2d, the same `_exile_cards_from_graveyard` helper an ordinary forced
#: exile already uses), gating a second instance of damage to the first
#: sentence's own target's controller (CR 400.7 anaphora: "that creature",
#: read before the first damage might destroy it). No second Modern/
#: Pioneer/Standard-legal printing of this exact optional-graveyard-exile
#: rider turned up a `card_search`; see MEMORY.md for the dated note. The
#: leading name is matched, not assumed, so a same-shaped future printing
#: with a different name reads identically - a `(?P=name)` backreference is
#: what makes the second "also deals" sentence name *this* spell rather than
#: a different one.
_DEALS_DAMAGE_THEN_MAY_EXILE_GRAVEYARD_EXTRA_DAMAGE_RE = re.compile(
    r"^(?P<name>[A-Z][A-Za-z',.\- ]*?) deals (?P<n1>\d+) damage to target creature\. "
    r"You may exile a card from your graveyard\. If you do, (?P=name) also deals "
    r"(?P<n2>\d+) damage to that creature'?s controller\.?$"
)


def _deals_damage_then_may_exile_graveyard_extra_damage(text: str, *, for_spell: bool):  # noqa: ANN202
    from ..models.card_state import CardState
    from ..models.zone import Zone
    from . import effects
    from .decisions import source_id_of

    if not for_spell:
        return None
    match = _DEALS_DAMAGE_THEN_MAY_EXILE_GRAVEYARD_EXTRA_DAMAGE_RE.fullmatch(text.strip())
    if match is None:
        return None
    amount = int(match.group("n1"))
    extra = int(match.group("n2"))

    def effect(game: Game, spell) -> None:  # noqa: ANN001
        targets = [
            target
            for target in game.resolve_targets(spell)
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
        ]
        if not targets:
            return
        target = targets[0]
        controller_username = target.controller
        game.deal_damage(target, amount, source=spell)
        player = game.controller_of(spell)
        if not player.graveyard:
            return
        if not game.may(
            player,
            "exile a card from your graveyard",
            source=spell.name,
            source_id=source_id_of(spell),
        ):
            return
        exiled = effects._exile_cards_from_graveyard(
            game, player, 1, spell.name, source_id=source_id_of(spell)
        )
        if not exiled or not controller_username:
            return
        game.deal_damage(game.player(controller_username), extra, source=spell)

    return effect


def _counter_payoffs_resolution_text(text: str, *, for_spell: bool):  # noqa: ANN202
    """`machines/counter_payoffs.parse_resolution_text`, tried as one more
    entry in `_WHOLE_TEXT_READERS` below - CR 120.3's "that many" damage
    counters, CR 122.1's counters-on-self X, CR 603.12's reflexive
    remove-a-counter, the crewed-this-turn target-and-double pair, and the
    pay-life-for-counters optional cost, none of which are this module's own
    to add a card-name row for. Deferred to a function (rather than a bare
    tuple entry naming the imported callable) only so this module's own
    import list stays untouched by a sibling task's additions to that one."""
    from . import counter_payoffs

    return counter_payoffs.parse_resolution_text(text, for_spell=for_spell)


def _minus_counters_resolution_text(text: str, *, for_spell: bool):  # noqa: ANN202
    """`machines/minus_counters.parse_resolution_text`, tried as one more
    entry in `_WHOLE_TEXT_READERS` below - CR 122.5's bare self-removal, the
    surveil-then-remove-a-counter pair, the dies-and-returns-losing-all-
    abilities shape, the unqualified mass "each creature" placement, "remove
    any number of counters from target", and "target opponent exiles cards
    from their hand", none of which are this module's own to add a
    card-name row for. Deferred to a function (rather than a bare tuple
    entry naming the imported callable) for the identical reason `_counter_
    payoffs_resolution_text` is: this module's own import list stays
    untouched by a sibling task's additions to that one."""
    from . import minus_counters

    return minus_counters.parse_resolution_text(text, for_spell=for_spell)


_WHOLE_TEXT_READERS = (
    lambda text, *, for_spell: _each_kind_another_counter(text),
    _create_that_many_tokens,
    _remove_a_counter_if_you_do,
    _create_one_token_or_another,
    _if_graveyard_count_otherwise,
    _target_player_investigates,
    _target_player_gains_then_searches,
    _search_library_and_or_graveyard,
    _choose_targets_put_counter_on_each,
    _create_then_counters_per_source_counter,
    _create_token_then_put_this_creatures_counters_on_it,
    _reflexive_may_pay_x_move_counters,
    _may_move_any_number_counters,
    _put_counter_then_double_on_that,
    _choose_any_number_then_double_each,
    _deals_damage_then_may_exile_graveyard_extra_damage,
    _counter_payoffs_resolution_text,
    _minus_counters_resolution_text,
)


def parse_resolution_text(text: str, *, for_spell: bool = False):  # noqa: ANN201
    """One of this module's whole-text resolution shapes, or `None`."""
    whole = " ".join(text.split())
    for reader in _WHOLE_TEXT_READERS:
        effect = reader(whole, for_spell=for_spell)
        if effect is not None:
            return effect
    return None


# ---------------------------------------------------------------------------
# A "put" that names several counters or several recipients
# ---------------------------------------------------------------------------
#
# "Put a +1/+1 counter and a lifelink counter on that creature and a +1/+1
# counter and a lifelink counter on this permanent." (Arwen, Mortal Queen),
# "Put two +1/+1 counters and a flying counter on target attacking creature."
# (Guide of Souls' reflexive trigger). CR 608.2c has the controller follow the
# instructions in the order written, and every counter named is the same
# instruction "put a <kind> counter on <recipient>" (CR 122.1) done once more,
# so the compound sentence is the sequence of its simple ones, in the order
# printed, which every simple-put reader already performs.
#
# A recipient is named once however many counters it gets. When it is a
# *target* the later counters go on "that <noun>", not on a second "target
# ..." - a second "target" would be a second target (CR 115.1) the printed
# sentence never chose. Only recipients whose later mentions are unambiguous
# are expanded (a target phrase with an "or", say, is left alone and fails
# closed in the dispatcher exactly as before).

_COUNTER_NUMBER = r"(?:an?|one|two|three|four|five|six|seven|eight|nine|ten|X|\d+)"
_ONE_COUNTER = rf"{_COUNTER_NUMBER} (?:[+\-]\d+/[+\-]\d+|[a-z]+(?: [a-z]+)?) counters?"
_COUNTER_LIST = rf"{_ONE_COUNTER}(?:(?:, and |, | and ){_ONE_COUNTER})*"
_PUT_RECIPIENT = (
    r"(?:that (?:creature|permanent|artifact|land|token|player)|it|this [a-z]+"
    r"|(?:up to (?:one|two|three) )?(?:another )?target [a-z]+(?: [a-z]+)*?)"
)
_COMPOUND_PUT_RE = re.compile(
    rf"^[Pp]ut (?P<first>{_COUNTER_LIST}) on (?P<first_to>{_PUT_RECIPIENT})"
    rf"(?: and (?P<second>{_COUNTER_LIST}) on (?P<second_to>{_PUT_RECIPIENT}))?$"
)
_ONE_COUNTER_RE = re.compile(_ONE_COUNTER)
#: Words that end the noun phrase of a "target <noun phrase>" for the purpose
#: of naming it again as "that <noun>".
_TARGET_PHRASE_STOP = frozenset({"you", "an", "opponent", "that", "with", "without", "of"})


def _later_mention(recipient: str) -> str | None:
    """How a later counter names a recipient that is already chosen, or
    `None` when it cannot be said without guessing."""
    if recipient.startswith(("that ", "this ")) or recipient == "it":
        return recipient
    match = re.fullmatch(
        r"(?:up to (?:one|two|three) )?(?:another )?target (?P<phrase>.+)", recipient
    )
    if match is None:
        return None
    words = match.group("phrase").split()
    if "or" in words or "and" in words:
        return None  # "target creature or planeswalker": "that creature" would guess the type
    noun = ""
    for word in words:
        if word in _TARGET_PHRASE_STOP:
            break
        noun = word
    if not noun or noun.endswith("s"):
        return None  # a plural recipient ("two target creatures") has no singular anaphor
    return f"that {noun}"


def expand_compound_counter_puts(text: str) -> str:
    """`text` with every compound "put" sentence written out as the simple
    ones it stands for (see the banner above), else `text` unchanged.

    A sentence is compound when a counter list names more than one counter;
    "put a +1/+1 counter on X and a +1/+1 counter on Y" (one counter each)
    already has its own readers and is left alone.
    """
    if '"' in text:
        return text
    sentences = re.split(r"(?<=\.)\s+", text.strip())
    changed = False
    out: list[str] = []
    for sentence in sentences:
        body = sentence.rstrip(".")
        match = _COMPOUND_PUT_RE.fullmatch(body)
        if match is None:
            out.append(sentence)
            continue
        groups = [(match.group("first"), match.group("first_to"))]
        if match.group("second") is not None:
            groups.append((match.group("second"), match.group("second_to")))
        if all(len(_ONE_COUNTER_RE.findall(counters)) == 1 for counters, _ in groups):
            out.append(sentence)
            continue
        expanded: list[str] = []
        for counters, recipient in groups:
            later = _later_mention(recipient)
            items = _ONE_COUNTER_RE.findall(counters)
            if later is None and len(items) > 1:
                expanded = []
                break
            expanded.append(f"Put {items[0]} on {recipient}.")
            expanded.extend(f"Put {item} on {later}." for item in items[1:])
        if not expanded:
            out.append(sentence)
            continue
        changed = True
        out.extend(expanded)
    return " ".join(out) if changed else text
