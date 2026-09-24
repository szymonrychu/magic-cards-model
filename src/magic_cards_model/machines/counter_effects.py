"""Counters as a player puts them: who put them, on what, and when (CR 122).

The active-voice family of counter templates, read by shape and never by
card:

- **"Whenever you put a[n]/one or more `<kind>` counter(s) on `<a
  description>`"** (CR 122.6) - Ant-Man, Colony Commander's "a creature",
  Knight of Wundagore's "another creature", Invisible Woman, Sue Storm's "one
  or more other Heroes you control", Stocking the Pantry's and Terrasymbiosis'
  "a creature you control". `unread_trigger_events`/`condition_matches` are
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
    """`word` as a subtype in CR 205.3's vocabulary (its own spelling), or
    `None`. English plurals the subtype lists print: "s" (Goblins), "es"
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


def unread_trigger_events(condition: str) -> frozenset[TriggerEvent | ExtraTriggerEvent]:
    """The events one of this module's conditions watches, or an empty set.

    Asked by `machines/triggers._unread_trigger_events` after its own shapes,
    so an ability `machines/abilities._trigger_event` left with `event=None`
    is kept (`triggered_abilities_of`) and reaches `condition_matches`."""
    if _you_put_counters(condition) is not None:
        return frozenset({ExtraTriggerEvent.COUNTERS_PUT})
    if _deal_damage(condition) is not None:
        return frozenset({ExtraTriggerEvent.COMBAT_DAMAGE_TO_PLAYERS, TriggerEvent.DEALS_DAMAGE})
    return frozenset()


def condition_matches(
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


def put_this_turn(context: object, putter: str | None, card_id: object, kind: str) -> bool:
    """Whether `putter` has put one or more `kind` counters on `card_id` this
    turn, off `LayerContext.counters_put_this_turn`."""
    records = getattr(context, "counters_put_this_turn", ())
    return any(
        who == putter and on == card_id and placed.lower() == kind.lower()
        for who, on, placed in records
    )


def parse_static_layer_sentence(sentence: str):  # noqa: ANN201 - EffectBuilder
    """A static counter sentence as a `machines/layers` `EffectBuilder`, or
    `None`. Asked first by `machines/layers._parse_static_layer_sentence`."""
    from . import layers

    text = " ".join(sentence.split())
    match = _PUT_ON_SELF_THIS_TURN_GRANT_RE.fullmatch(text)
    if match is not None:
        keywords = layers._split_and_validate_keywords(match.group("keywords"))
        if keywords is None:
            return None
        kind = match.group("kind").lower()
        return layers._context_gated_self_static_builder(
            lambda source, context: put_this_turn(context, source.controller, source.id, kind),
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
            card_id
            for who, card_id, placed in getattr(context, "counters_put_this_turn", ())
            if who == source.controller and placed.lower() == kind
        ]
        effects = []
        for card_id in dict.fromkeys(marked):
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
                            username=source.controller, card_id=card_id
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


_WHOLE_TEXT_READERS = (
    lambda text, *, for_spell: _each_kind_another_counter(text),
    _create_that_many_tokens,
    _remove_a_counter_if_you_do,
)


def parse_resolution_text(text: str, *, for_spell: bool = False):  # noqa: ANN201
    """One of this module's whole-text resolution shapes, or `None`."""
    whole = " ".join(text.split())
    for reader in _WHOLE_TEXT_READERS:
        effect = reader(whole, for_spell=for_spell)
        if effect is not None:
            return effect
    return None
