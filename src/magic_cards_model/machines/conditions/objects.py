"""Object-state conditions: the source's own state and the trigger event's own
subject ("it", "that creature"), with last known information for a subject
that has left (CR 603.10a).

Each reader here is a `ConditionReader` registered through `READERS`; see
`machines/conditions/__init__.py` for the contract every reader keeps.

**Who a clause is about.** A clause names its subject one of four ways, and
`_subject` resolves each the same way for every reader:

- the source itself - "this creature", "this artifact", "this card", or the
  source's own name or short name (CR 201.5, CR 201.5c: "Sarulf", "The
  Ozolith");
- the trigger event's own subject - "it", "he", "they", "that creature",
  "that spell": the object the event names (CR 603.2), or the source when
  the event names none or the trigger is the source's own ("Whenever this
  creature attacks, if it's saddled"); for a "... is dealt damage" event the
  object dealt the damage (CR 120.3);
- the object the source is attached to - "enchanted creature", "equipped
  creature", "enchanted Equipment" (CR 303.4, CR 301.5), read as it last was
  once the source has left;
- nothing: a name that is not the source's answers False.

**Looking back.** A past-tense clause ("it had a +1/+1 counter on it", "it
was a Human", "its power was 3 or greater") asks about a subject that has
left the battlefield as it last existed there (CR 603.10a, CR 608.2h) -
`CardState.last_known_counters`, `last_known_types` and their siblings, or
the event's own snapshot of the subject (`GameEvent.subject_types`).

Counts go through `magic_cards_model.numbers`; card qualities through
`models/game.py`'s own `_characteristic_word`.

Rules verified with `mise run rules:find`:

- CR 122.1: "A counter is a marker placed on an object or player that
  modifies its characteristics and/or interacts with a rule, ability, or
  effect." Any name is a kind.
- CR 122.2: counters are not retained when an object moves between zones.
- CR 603.10a: leaves-the-battlefield abilities look back in time.
- CR 605.1a: what makes an activated ability a mana ability - recorded on
  the activation event as `GameEvent.mana_ability`.
- CR 607.2a: "cards exiled with" an object are the ones its linked ability
  exiled (`Game.cards_exiled_with`).
- CR 508.1f: "Tapping a creature when it's declared as an attacker isn't a
  cost; attacking simply causes creatures to become tapped" - recorded on
  that tap's event as `GameEvent.declared_attacker`.
- CR 202.3e: a spell's mana value on the stack counts the X chosen for it -
  a cast event's own `GameEvent.amount`.
"""

import re
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ...models.card_state import counters_removed_fact, graveyard_with_counter_fact
from ...models.zone import Zone
from ...numbers import COUNT, parse_count
from . import ConditionReader

if TYPE_CHECKING:
    from ...models.card_state import CardState
    from . import ConditionContext


# -- subjects ------------------------------------------------------------------

_SELF_NOUN = (
    r"this (?:creature|permanent|artifact|enchantment|card|land|aura|equipment|vehicle"
    r"|planeswalker|spell|battle|mount|spacecraft)"
)
_EVENT_PRONOUN = r"it|he|she|they|that creature|that permanent|that spell|that card|that land"
_ATTACHED_TO = (
    r"(?:enchanted|equipped) (?:creature|permanent|artifact|land|equipment|planeswalker|vehicle)"
)
#: A card's own name, lowercased (the clause is), as a bounded run of words
#: that does not open like a description of something else.
_NAME = (
    r"(?!(?:a|an|another|each|all|no|any|target|that|those|these|this|it|its|you|your|their"
    r"|his|her|one|two|three|four|five|six|seven|eight|nine|ten|every|other|enchanted"
    r"|equipped|there|if|the number|the total|creatures?|permanents?|cards?|spells?|players?"
    r"|opponents?|defending)\b)"
    r"[a-z][a-z0-9'-]*(?:,? [a-z][a-z0-9'-]*){0,4}"
)
SUBJECT = rf"(?:{_SELF_NOUN}|{_ATTACHED_TO}|{_EVENT_PRONOUN}|{_NAME})"
#: The possessive of a subject: "its", "this creature's", "Kitsa's".
POSSESSIVE = rf"(?:its|his|her|their|(?:{_SELF_NOUN}|{_ATTACHED_TO}|that creature|{_NAME})'s)"


def _names_source(phrase: str, source: "CardState | None") -> bool:
    """Whether `phrase` is the source's own name or a short form of it."""
    from ..abilities import self_reference_names
    from ..triggers import _is_legendary_source

    if source is None:
        return False
    names = self_reference_names(source.name, legendary=_is_legendary_source(source))
    return phrase in {name.lower() for name in names}


def _event_names_the_recipient(context: "ConditionContext") -> bool:
    """A "... is dealt damage" trigger: "it" is what was dealt the damage
    (CR 120.3), which the damage event carries as its target."""
    from ..abilities import TriggeredAbility
    from ..triggers import TriggerEvent

    event = context.event
    ability = context.ability
    return (
        event is not None
        and event.event is TriggerEvent.DEALS_DAMAGE
        and isinstance(ability, TriggeredAbility)
        and re.search(r"\b(?:is|are) dealt\b", ability.condition.lower()) is not None
    )


def _event_subject(context: "ConditionContext") -> "CardState | None":
    """The object the trigger event names, or the source when it names none."""
    from ...models.card_state import CardState

    event = context.event
    if event is not None:
        wanted = event.target_id if _event_names_the_recipient(context) else event.subject_id
        if wanted is not None:
            found = context.game.find_by_id(wanted)
            if isinstance(found, CardState):
                return found
            if context.source is not None and context.source.id == wanted:
                return context.source
            return None
    return context.source


def _attached_to_of(context: "ConditionContext") -> "CardState | None":
    """What the source is attached to, or was as it last left (CR 608.2h)."""
    from ...models.card_state import CardState

    source = context.source
    if source is None:
        return None
    host = source.attached_to
    if host is None and source.zone is not Zone.BATTLEFIELD:
        host = source.last_known_attached_to
    if host is None:
        return None
    found = context.game.find_by_id(host)
    return found if isinstance(found, CardState) else None


def _subject(context: "ConditionContext", phrase: str) -> "CardState | None":
    """Who `phrase` names - see the module docstring."""
    phrase = phrase.strip()
    for possessive in ("'s",):
        phrase = phrase.removesuffix(possessive)
    if phrase in ("its", "his", "her", "their"):
        phrase = "it"
    if re.fullmatch(_SELF_NOUN, phrase):
        return context.source
    if re.fullmatch(_ATTACHED_TO, phrase):
        return _attached_to_of(context)
    if re.fullmatch(_EVENT_PRONOUN, phrase) or phrase == "the creature":
        # "the creature" is the trigger event's own subject too (Anax's "If the
        # creature had power 4 or greater, ..."): the object that died.
        return _event_subject(context)
    if _names_source(phrase, context.source):
        return context.source
    return None


# -- quantities ----------------------------------------------------------------

#: How many: "no", "a", "one or more", "N or more", "N or fewer", "fewer
#: than N", "more than N", "at least N", "exactly N", and the parity forms
#: "an odd number of" / "an even number of" (Sab-Sunen; zero is even).
QUANTITY = (
    rf"(?:no|one or more|an (?:odd|even) number of"
    rf"|(?:fewer than|more than|greater than|less than|at least|at most"
    rf"|exactly) {COUNT}"
    rf"|{COUNT} or (?:more|fewer|greater|less)|{COUNT})"
)


def quantity_test(text: str | None, *, plural_default: bool = True) -> Callable[[int], bool] | None:
    """`text` (a `QUANTITY` match, or None for a bare plural such as "it had
    counters on it") as a test on a count, or None when it is not read."""
    if text is None:
        return (lambda count: count >= 1) if plural_default else None
    text = text.strip()
    if text == "no":
        return lambda count: count == 0
    if text == "one or more":
        return lambda count: count >= 1
    if text in ("an odd number of", "an even number of"):
        remainder = 1 if "odd" in text else 0
        return lambda count: count % 2 == remainder
    for prefix, test in (
        ("fewer than ", lambda have, need: have < need),
        ("less than ", lambda have, need: have < need),
        ("more than ", lambda have, need: have > need),
        ("greater than ", lambda have, need: have > need),
        ("at least ", lambda have, need: have >= need),
        ("at most ", lambda have, need: have <= need),
        ("exactly ", lambda have, need: have == need),
    ):
        if text.startswith(prefix):
            need = parse_count(text.removeprefix(prefix))
            if need is None:
                return None
            return lambda count, need=need, test=test: test(count, need)
    for suffix, test in (
        (" or more", lambda have, need: have >= need),
        (" or greater", lambda have, need: have >= need),
        (" or fewer", lambda have, need: have <= need),
        (" or less", lambda have, need: have <= need),
    ):
        if text.endswith(suffix):
            need = parse_count(text.removesuffix(suffix))
            if need is None:
                return None
            return lambda count, need=need, test=test: test(count, need)
    need = parse_count(text)
    if need is None:
        return None
    # "a +1/+1 counter" / "an oil counter": at least one.
    if text in ("a", "an"):
        return lambda count: count >= 1
    return lambda count, need=need: count == need


# -- counters ------------------------------------------------------------------

_KIND = r"(?P<kind>[a-z0-9+/-]+(?: strike)?)"
_PAST = ("had", "didn't have", "did not have", "was", "wasn't", "was not", "were")


def _counters_of(state: "CardState", *, past: bool) -> Any:
    """The counters `state` has - or, looking back (CR 603.10a), had as it
    last left the battlefield."""
    if past and state.zone is not Zone.BATTLEFIELD:
        return state.last_known_counters
    return state.counters


def _count_of(counters: Any, kind: str | None) -> int:
    if kind is None:
        return sum(count for _kind, count in counters.items())
    return counters[kind]


def _has_counters(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "<subject> has/had/doesn't have [quantity] [kind] counter(s) on it"."""
    subject = _subject(context, match.group("subject"))
    test = quantity_test(match.group("q"))
    if subject is None or test is None:
        return False
    verb = match.group("verb")
    counters = _counters_of(subject, past=verb in _PAST or _left_with_the_event(context, subject))
    holds = test(_count_of(counters, match.group("kind")))
    return not holds if "n't" in verb or " not " in f" {verb} " else holds


def _there_are_counters_on(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "there are [quantity] <kind> counters on <subject>"."""
    subject = _subject(context, match.group("subject"))
    test = quantity_test(match.group("q"))
    if subject is None or test is None:
        return False
    return test(_count_of(subject.counters, match.group("kind")))


def _mana_value_of_subject(context: "ConditionContext", subject: "CardState") -> float:
    """CR 202.3e: a spell's mana value on the stack, X included - the cast
    event's own `amount` when the event is that cast."""
    from ..triggers import TriggerEvent

    event = context.event
    if (
        event is not None
        and event.event is TriggerEvent.CAST_SPELL
        and event.subject_id == subject.id
        and event.amount is not None
    ):
        return event.amount
    return context.game.characteristics_of(subject).mana_value


def _mana_value_against_counters(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "its mana value is equal to [N plus] the number of <kind> counters on
    <holder>" (Obscura Ascendancy)."""
    subject = _subject(context, match.group("subject"))
    holder = _subject(context, match.group("holder"))
    plus = parse_count(match.group("plus")) if match.group("plus") else 0
    if subject is None or holder is None or plus is None:
        return False
    return _mana_value_of_subject(context, subject) == plus + holder.counter_count(
        match.group("kind")
    )


# -- cards exiled with the source (CR 607.2a) ----------------------------------


def _exiled_with(context: "ConditionContext", phrase: str) -> list["CardState"] | None:
    holder = _subject(context, phrase)
    if holder is None:
        return None
    return context.game.cards_exiled_with(holder.id, holder.zone_change_stamp)


def _cards_exiled_with(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "N or more cards have been exiled with this artifact" (Colfenor's
    Urn), "there are cards exiled with this enchantment" (Valakut
    Exploration)."""
    cards = _exiled_with(context, match.group("holder"))
    test = quantity_test(match.group("q"))
    if cards is None or test is None:
        return False
    return test(len(cards))


def _same_name_as_exiled(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "it has the same name as one of the cards exiled with this artifact"
    (Spellweaver Helix) - CR 201.2's name, of the event's own subject."""
    subject = _subject(context, match.group("subject"))
    cards = _exiled_with(context, match.group("holder"))
    if subject is None or not cards:
        return False
    return any(card.name == subject.name for card in cards)


# -- where the subject is ------------------------------------------------------

_ZONE_WORDS = {
    "on the battlefield": Zone.BATTLEFIELD,
    "exiled": Zone.EXILE,
    "in exile": Zone.EXILE,
    "in your graveyard": Zone.GRAVEYARD,
    "in a graveyard": Zone.GRAVEYARD,
    "in your hand": Zone.HAND,
}


def _in_zone(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "this card is in your graveyard", "this card is exiled [with an egg
    counter on it]", "this enchantment is on the battlefield", "it's on the
    battlefield" (CR 400.1's zones; "your" graveyard is its owner's, CR
    404.1)."""
    subject = _subject(context, match.group("subject"))
    if subject is None:
        return False
    where = match.group("zone")
    zone = _ZONE_WORDS[where]
    if subject.zone is not zone:
        return False
    if where.startswith("in your") and subject.owner != context.controller:
        return False
    if match.group("kind") is None:
        return True
    test = quantity_test(match.group("q"))
    return test is not None and test(subject.counter_count(match.group("kind")))


# -- what happened to counters this turn ---------------------------------------


def _counters_removed_this_turn(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "an oil counter was removed from a permanent you controlled this turn"
    (Churning Reservoir), counted as `CardState.remove_counters` took them."""
    test = quantity_test(match.group("q"))
    if test is None:
        return False
    fact = counters_removed_fact(match.group("kind"))
    return test(context.game.turn_count(fact, context.controller))


def _put_into_graveyard_with_counter(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "a permanent with an oil counter on it was put into a graveyard this
    turn" - any player's graveyard, or "your" graveyard (CR 404.1: its
    owner's)."""
    fact = graveyard_with_counter_fact(match.group("kind"))
    players = (
        [context.controller]
        if match.group("whose") == "your"
        else [player.username for player in context.game.players]
    )
    return sum(context.game.turn_count(fact, player) for player in players) >= 1


# -- the event itself ----------------------------------------------------------


def _activated_ability_is_mana_ability(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "it isn't a mana ability" on an activation trigger (Rings of
    Brighthearth, Harsh Mentor): "it" is the activated ability the event
    names, and CR 605.1a's test was made as it was activated. No activation
    event, nothing to ask about."""
    from ..triggers import ExtraTriggerEvent

    event = context.event
    if event is None or event.event is not ExtraTriggerEvent.ABILITY_ACTIVATED:
        return False
    return event.mana_ability == (match.group("negated") is None)


def _declared_as_an_attacker(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "it isn't being declared as an attacker" (Verity Circle): whether the
    tap the trigger event reports was CR 508.1f's attack declaration."""
    from ..triggers import TriggerEvent

    event = context.event
    if event is None or event.event is not TriggerEvent.BECOMES_TAPPED:
        return False
    return event.declared_attacker == (match.group("negated") is None)


def _attacking_alone(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "it's attacking alone" (Yuan-Ti Malison, Gutter Skulker) - CR 506.5: a
    creature attacks alone if it's the only creature declared as an attacker.
    Read off `Game.combat` right now; False for a subject that is not
    attacking at all."""
    subject = _subject(context, match.group("subject"))
    attackers = context.game.combat.attacker_ids
    held = subject is not None and attackers == [subject.id]
    return not held if match.group("negated") else held


def _attacking_defender_quality(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "it's attacking a battle" (Rampaging Geoderm) - CR 508.1's declared
    defender, read off `Game.combat` right now rather than off the trigger
    event, since the object asked about is whichever creature the resolving
    pump names ("target attacking creature"), not necessarily the one whose
    attack triggered the ability. Templated over CR 508.1b's whole list of
    eligible defenders - a player, a planeswalker, or a battle - rather than
    fixed to the one word "battle" this session's reported card happens to
    print, so "attacking a planeswalker"/"attacking a player" read the same
    generic way.

    False for a subject that is not attacking at all. A battle defender is a
    `Type.BATTLE` permanent CR 508.1b's declaration already accepted, which
    is the only fact this clause needs."""
    from ...models.card import Type
    from ...models.card_state import CardState

    subject = _subject(context, match.group("subject"))
    if subject is None:
        return False
    attack = context.game.combat.attack_by(subject.id)
    if attack is None:
        held = False
    else:
        defender = context.game.resolve_target(attack.defender)
        quality = match.group("quality").lower()
        if quality == "player":
            held = defender is not None and not isinstance(defender, CardState)
        else:
            wanted = Type.PLANESWALKER if quality == "planeswalker" else Type.BATTLE
            held = (
                isinstance(defender, CardState)
                and wanted in context.game.characteristics_of(defender).types
            )
    return held != bool(match.group("negated"))


# -- characteristics, now or as it last existed --------------------------------


class _Seen:
    """The characteristics a clause reads off one object: computed on the
    battlefield (CR 613.5), the printed ones anywhere else, and - looking
    back (CR 603.10a, CR 608.2h) - as it last existed on the battlefield."""

    def __init__(self, context: "ConditionContext", state: "CardState", *, past: bool) -> None:
        chars = context.game.characteristics_of(state)
        self.types = tuple(chars.types)
        self.subtypes = tuple(chars.subtypes)
        self.supertypes = tuple(chars.supertypes)
        self.colors = tuple(chars.colors)
        self.power = chars.power
        self.toughness = chars.toughness
        self.mana_value = chars.mana_value
        self.chars = chars
        past = past or _left_with_the_event(context, state)
        if state.zone is Zone.BATTLEFIELD or not past:
            if state.zone is not Zone.BATTLEFIELD:
                self.power, self.toughness = state.power, state.toughness
            return
        event = context.event
        if event is not None and event.subject_id == state.id and event.subject_types is not None:
            self.types = tuple(event.subject_types)
            self.subtypes = tuple(event.subject_subtypes or self.subtypes)
            self.colors = tuple(event.subject_colors or self.colors)
        else:
            self.types = tuple(state.last_known_types or self.types)
            self.subtypes = tuple(state.last_known_subtypes or self.subtypes)
            self.colors = tuple(state.last_known_colors or self.colors)
        self.power, self.toughness = _last_known_power_toughness(state)


#: The events whose own subject has just left the battlefield (CR 603.10a's
#: look-back triggers).
_LEFT_THE_BATTLEFIELD = frozenset(
    {
        "dies",
        "is_sacrificed",
        "leaves_the_battlefield",
        "leaves_battlefield_to_exile",
        "leaves_battlefield_to_hand",
    }
)


def _left_with_the_event(context: "ConditionContext", state: "CardState") -> bool:
    """Whether `state` is the subject of a leaves-the-battlefield event and
    has left: a present-tense clause about it ("When Syr Vondam dies ...
    while its power is 4 or greater") can only be asked of the permanent as it
    last existed (CR 603.10a)."""
    event = context.event
    return (
        event is not None
        and state.zone is not Zone.BATTLEFIELD
        and event.subject_id == state.id
        and str(event.event.value) in _LEFT_THE_BATTLEFIELD
    )


def _last_known_power_toughness(state: "CardState") -> tuple[int | None, int | None]:
    """Power and toughness as the object last existed on the battlefield (CR
    608.2h): `CardState.last_known_power_toughness`."""
    return state.last_known_power_toughness()


#: A card quality one word can name: a colour (CR 105.1), a supertype (CR
#: 205.4a), a card type (CR 205.2a), a subtype (CR 205.3), "historic" (CR
#: 700.6), "permanent" (CR 110.4), "token" (CR 111.1), with an optional "non"
#: prefix.
def _quality_words() -> str:
    from ...data.subtypes import subtype_vocabulary
    from ...models.card import Supertype, Type

    words = {
        "white",
        "blue",
        "black",
        "red",
        "green",
        "colorless",
        "multicolored",
        "monocolored",
        "historic",
        "permanent",
        "token",
        "nontoken",
        *(each.value for each in Supertype),
        *(each.value for each in Type),
        *subtype_vocabulary(),
    }
    alternation = "|".join(re.escape(word) for word in sorted(words, key=len, reverse=True))
    return rf"(?:non-?)?(?:{alternation})"


_QUALITY_WORD = _quality_words()
_QUALITY_LIST = rf"(?:an? )?{_QUALITY_WORD}(?:(?:,| or| and/or|, or) (?:an? )?{_QUALITY_WORD})*"


def _quality_holds(seen: _Seen, state: "CardState", word: str) -> bool | None:
    """Whether one quality word is true of `seen`, or None when not read."""
    from ...models.card import Supertype, Type
    from ...models.game import _characteristic_word

    word = word.strip().removeprefix("a ").removeprefix("an ").strip()
    if word.startswith("non") and word not in ("nontoken",) and len(word) > 4:
        inner = _quality_holds(seen, state, word.removeprefix("non").lstrip("-"))
        return None if inner is None else not inner
    if word == "historic":
        # CR 700.6: artifacts, legendaries and Sagas are historic.
        return (
            Type.ARTIFACT in seen.types
            or Supertype.LEGENDARY in seen.supertypes
            or "Saga" in seen.subtypes
        )
    if word == "permanent":
        from ...models.card_state import PERMANENT_TYPES

        return bool(PERMANENT_TYPES.intersection(seen.types))
    if word in ("token", "nontoken"):
        return bool(state.token) == (word == "token")
    if word == "multicolored":
        return len(seen.colors) > 1
    if word == "monocolored":
        return len(seen.colors) == 1
    test = _characteristic_word(word)
    if test is None:
        return None
    return test(
        seen.chars.model_copy(
            update={
                "types": seen.types,
                "subtypes": seen.subtypes,
                "colors": seen.colors,
                "supertypes": seen.supertypes,
            }
        )
    )


def _qualities_hold(seen: _Seen, state: "CardState", phrase: str) -> bool:
    """A list of qualities joined by "or" - any of them."""
    words = [part for part in re.split(r",? or |, | and/or ", phrase) if part.strip()]
    answers = [_quality_holds(seen, state, word) for word in words]
    return bool(answers) and None not in answers and any(answers)


def _is_quality(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "it's a creature", "this permanent is an enchantment", "enchanted
    creature is a Wolf or Werewolf", "this creature is blue", "it was a
    Human", "it wasn't a Demon", "it was historic"."""
    subject = _subject(context, match.group("subject"))
    if subject is None:
        return False
    verb = match.group("verb").strip()
    past = verb.startswith("was") or verb == "were"
    holds = _qualities_hold(_Seen(context, subject, past=past), subject, match.group("quality"))
    return not holds if ("n't" in verb or verb.endswith(" not")) else holds


def _attachments(context: "ConditionContext", state: "CardState", *, past: bool) -> list:
    """What is attached to `state`, as `(types, subtypes, controller)`: the
    permanents attached now, or - looking back - as it last left (CR
    603.10a, `CardState.last_known_attachments`)."""
    if past and state.zone is not Zone.BATTLEFIELD:
        return [
            (snapshot.types, snapshot.subtypes, snapshot.controller)
            for snapshot in state.last_known_attachments
        ]
    found = []
    for permanent in context.game.battlefield:
        if permanent.attached_to == state.id and permanent is not state:
            chars = context.game.characteristics_of(permanent)
            found.append((tuple(chars.types), tuple(chars.subtypes), permanent.controller))
    return found


def _is_equipped(attached: list) -> bool:
    return any("Equipment" in subtypes for _types, subtypes, _controller in attached)


def _is_enchanted(attached: list) -> bool:
    return any("Aura" in subtypes for _types, subtypes, _controller in attached)


def _is_in_state(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "<subject> is [not] attacking / blocking / blocked / unblocked /
    tapped / untapped / saddled / suspected / monstrous / renowned /
    equipped / enchanted / enchanted or equipped", and "it was enchanted or
    equipped" looking back.

    CR 506.4 (attacking and blocking), CR 509.1h ("blocked"/"unblocked" - an
    attacking creature with a blocker declared for it stays blocked even
    once every one of them leaves combat; Cinder Crawler's own "Activate
    only if this creature is blocked", CR 602.5b), CR 701.26 (tapped), CR
    702.171b (saddled), CR 701.60b (suspected), CR 701.37b (monstrous), CR
    702.112b (renowned) - each a status or designation of the permanent,
    false off the battlefield; CR 301.5 and CR 303.4 for equipped and
    enchanted."""
    subject = _subject(context, match.group("subject"))
    if subject is None:
        return False
    verb = match.group("verb").strip()
    past = verb.startswith("was") or verb == "were"
    game = context.game
    on_battlefield = subject.zone is Zone.BATTLEFIELD
    answers = []
    for word in re.split(r" or ", match.group("state")):
        word = word.strip()
        if word in ("equipped", "enchanted"):
            attached = _attachments(context, subject, past=past)
            answers.append(
                _is_equipped(attached) if word == "equipped" else _is_enchanted(attached)
            )
        elif not on_battlefield:
            answers.append(False)
        elif word == "attacking":
            answers.append(game.is_attacking(subject))
        elif word == "blocking":
            answers.append(game.is_blocking(subject))
        elif word == "blocked":
            answers.append(game.is_blocked(subject))
        elif word == "unblocked":
            answers.append(game.is_attacking(subject) and not game.is_blocked(subject))
        elif word == "tapped":
            answers.append(subject.tapped)
        elif word == "untapped":
            answers.append(not subject.tapped)
        else:  # a designation field: saddled, suspected, monstrous, renowned
            answers.append(bool(getattr(subject, word)))
    holds = any(answers)
    negated = match.group("negated") is not None or "n't" in verb
    return not holds if negated else holds


def _enchanted_by(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "this creature is enchanted by two or more Auras" (Kitsune Mystic)."""
    subject = _subject(context, match.group("subject"))
    test = quantity_test(match.group("q"))
    if subject is None or test is None:
        return False
    attached = _attachments(context, subject, past=False)
    return test(sum(1 for _types, subtypes, _controller in attached if "Aura" in subtypes))


def _stat_compared_with_number(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "this creature's power is 4 or greater", "its power was 3 or greater",
    "its toughness was less than 1", "its power is 2 or less" (CR 208.1)."""
    subject = _subject(context, match.group("subject"))
    test = quantity_test(match.group("q"))
    if subject is None or test is None:
        return False
    seen = _Seen(context, subject, past=match.group("tense") in ("was", "had"))
    value = seen.power if match.group("stat") == "power" else seen.toughness
    return value is not None and test(value)


def _has_keyword(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "this creature has defender", "it doesn't have first strike",
    "it has mutate", "enchanted creature has toxic" (CR 702): the computed
    abilities on the battlefield (CR 613.5), last known information once it
    has left, the card's own abilities anywhere else."""
    from ..combat import has_keyword, source_had_keyword

    subject = _subject(context, match.group("subject"))
    if subject is None:
        return False
    keyword = match.group("keyword")
    verb = match.group("verb")
    if verb in _PAST:
        holds = source_had_keyword(subject, keyword, context.game)
    else:
        holds = has_keyword(subject, keyword, context.game)
        if not holds and subject.zone is not Zone.BATTLEFIELD:
            holds = any(
                ability.canonical.lower() == keyword for ability in _keyword_abilities(subject)
            )
    return not holds if "n't" in verb or verb.endswith(" not have") else holds


def _keyword_abilities(state: "CardState") -> list:
    from ..abilities import keyword_abilities

    try:
        return list(keyword_abilities(state.card))
    except Exception:  # noqa: BLE001 - a card the keyword reader refuses has none read
        return []


def _power_toughness_is(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "that creature is 1/1" (Sigil Captain) - both values (CR 208.1)."""
    subject = _subject(context, match.group("subject"))
    if subject is None:
        return False
    seen = _Seen(context, subject, past=False)
    return seen.power == int(match.group("power")) and seen.toughness == int(
        match.group("toughness")
    )


def _greater_stat_than(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "that creature has greater power or toughness than this creature"
    (Evolving Adaptive), "it has greater power or toughness than Hulkling":
    either value greater (CR 702.100a's own comparison, printed out)."""
    subject = _subject(context, match.group("subject"))
    other = _subject(context, match.group("other"))
    if subject is None or other is None:
        return False
    mine, theirs = _Seen(context, subject, past=False), _Seen(context, other, past=False)
    answers = []
    for stat in re.split(r" or ", match.group("stats")):
        a, b = getattr(mine, stat), getattr(theirs, stat)
        answers.append(a is not None and b is not None and a > b)
    return any(answers)


def _stat_compared_with_other(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "that creature's power is greater than this creature's" (Pelt
    Collector), "its toughness is greater than this creature's toughness"."""
    subject = _subject(context, match.group("subject"))
    other = _subject(context, match.group("other"))
    if subject is None or other is None:
        return False
    stat = match.group("stat")
    past = match.group("tense") == "was"
    a = getattr(_Seen(context, subject, past=past), stat)
    b = getattr(_Seen(context, other, past=False), stat)
    if a is None or b is None:
        return False
    return a > b if match.group("cmp") == "greater" else a < b


def _cast_from(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "it was cast from your graveyard" (Rocket-Powered Goblin Glider) -
    the cast record the object carries onto the battlefield (CR 400.7d),
    cast from that zone by a player who is "you" for a "your" zone."""
    subject = _subject(context, match.group("subject"))
    if subject is None:
        return False
    record = context.game.cast_record_of(subject)
    if record is None or record.origin_zone is not _ZONE_NAMES[match.group("zone")]:
        return False
    return match.group("whose") != "your" or subject.owner == context.controller


_ZONE_NAMES = {
    "graveyard": Zone.GRAVEYARD,
    "a graveyard": Zone.GRAVEYARD,
    "your graveyard": Zone.GRAVEYARD,
    "exile": Zone.EXILE,
    "hand": Zone.HAND,
    "your hand": Zone.HAND,
    "library": Zone.LIBRARY,
}


def _entered_or_cast_from(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "they entered or were cast from a graveyard" (Twilight Diviner), "one
    or more of them entered from exile or was cast from exile" (Extraordinary
    Journey): the enters event's own origin (`GameEvent.origin_zone`), or
    the zone its cast record says it was cast from (CR 400.7d)."""
    subject = _subject(context, "it")
    event = context.event
    if subject is None or event is None:
        return False
    cast_zone = _ZONE_NAMES[match.group("cast_zone")]
    entered_zone = _ZONE_NAMES[match.group("entered_zone") or match.group("cast_zone")]
    if event.origin_zone is entered_zone:
        return True
    record = context.game.cast_record_of(subject)
    return record is not None and record.origin_zone is cast_zone


def _shares_a_card_type_with_exiled(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "it shares a card type with the exiled card" (Cemetery Gatekeeper):
    the card exiled with the source (CR 607.2a) and the event's subject (CR
    205.2a's card types)."""
    subject = _subject(context, match.group("subject"))
    source = context.source
    if subject is None or source is None:
        return False
    exiled = context.game.cards_exiled_with(source.id, source.zone_change_stamp)
    mine = set(_Seen(context, subject, past=False).types)
    return any(mine.intersection(card.types) for card in exiled)


def _attached_to_quality(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "enchanted Equipment is attached to a creature" (Artificer's Hex)."""
    subject = _subject(context, match.group("subject"))
    if subject is None or subject.attached_to is None:
        return False
    from ...models.card_state import CardState

    host = context.game.find_by_id(subject.attached_to)
    if not isinstance(host, CardState):
        return False
    return _qualities_hold(_Seen(context, host, past=False), host, match.group("quality"))


def _dealt_combat_damage_to_this_turn(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "equipped creature didn't deal combat damage to a creature this turn"
    (Thirsting Axe), off the turn's damage ledger (`Game.
    damage_dealt_this_turn`, CR 120.1: the object that dealt it is its
    source)."""
    from ...models.card_state import CardState

    subject = _subject(context, match.group("subject"))
    if subject is None:
        return False
    game = context.game
    quality = match.group("quality")
    dealt = False
    for record in game.damage_dealt_this_turn:
        if record.source_id != subject.id or not record.combat or record.recipient_id is None:
            continue
        recipient = game.find_by_id(record.recipient_id)
        if not isinstance(recipient, CardState):
            continue
        if _qualities_hold(_Seen(context, recipient, past=True), recipient, quality):
            dealt = True
            break
    return not dealt if match.group("negated") else dealt


_STATE_WORD = (
    r"(?:attacking|blocking|blocked|unblocked|tapped|untapped|saddled|suspected|monstrous"
    r"|renowned|equipped|enchanted)"
)


def _keyword_alternation() -> str:
    from ..abilities import KEYWORD_ABILITY_NAMES

    names = sorted(KEYWORD_ABILITY_NAMES, key=len, reverse=True)
    return "(?:" + "|".join(re.escape(name) for name in names) + ")"


_KEYWORD = _keyword_alternation()


# -- the event's subject: what it targets, what it came with -------------------


def _distinct_targets(stack_object: Any) -> list:
    """A spell's or ability's chosen targets (CR 115.1), each object or player
    once however many instances of "target" chose it (CR 115.3)."""
    seen: list = []
    for ref in getattr(stack_object, "targets", None) or ():
        if ref not in seen:
            seen.append(ref)
    return seen


def _has_a_single_target(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "it has a single target" (Captured by the Consulate): the spell the
    event names targets exactly one object or player."""
    subject = _subject(context, match.group("subject"))
    return subject is not None and len(_distinct_targets(subject)) == 1


def _targets_only(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "that spell targets only this creature" (Ink-Treader Nephilim)."""
    subject = _subject(context, match.group("subject"))
    target = _subject(context, match.group("target"))
    if subject is None or target is None:
        return False
    refs = _distinct_targets(subject)
    return len(refs) == 1 and refs[0].is_card and refs[0].card_id == target.id


def _targets_quantity(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "it targets one or more other permanents you control" (Orvar, the
    All-Form): the permanents among the spell's targets with the quality,
    under the named control, other than the source when it says "other"."""
    from ...models.card_state import CardState

    subject = _subject(context, match.group("subject"))
    test = quantity_test(match.group("q"))
    if subject is None or test is None:
        return False
    source = context.source
    who = match.group("who")
    count = 0
    for ref in _distinct_targets(subject):
        if not ref.is_card:
            continue
        target = context.game.find_by_id(ref.card_id)
        if not isinstance(target, CardState) or target.zone is not Zone.BATTLEFIELD:
            continue
        if match.group("other") and source is not None and target.id == source.id:
            continue
        controller = context.game.controller_of(target).username
        if who == "you control" and controller != context.controller:
            continue
        if (
            who in ("an opponent controls", "you don't control")
            and controller == context.controller
        ):
            continue
        if not _qualities_hold(_Seen(context, target, past=False), target, match.group("quality")):
            continue
        count += 1
    return test(count)


def _attached_was(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "an Aura you controlled was attached to it" (Dawn Evangel): the
    attachments of the creature that died, as it last existed (CR
    603.10a), by subtype (CR 303.4 Aura, CR 301.5 Equipment) and by who
    controlled each."""
    subject = _subject(context, match.group("subject"))
    if subject is None:
        return False
    wanted = "Aura" if match.group("kind") == "aura" else "Equipment"
    who = match.group("who")
    for _types, subtypes, controller in _attachments(context, subject, past=True):
        if wanted not in subtypes:
            continue
        if who == "you" and controller != context.controller:
            continue
        if who == "an opponent" and controller == context.controller:
            continue
        return True
    return False


def _those_attackers_at_you(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "two or more of those creatures are attacking you and/or planeswalkers
    you control" (Mangara, the Diplomat): the creatures the attacking player
    the event names declared (CR 508.1), counted by what each attacks - you,
    or a planeswalker you control (CR 508.1b)."""
    from ...models.card import Type
    from ...models.card_state import CardState

    event = context.event
    test = quantity_test(match.group("q"))
    if event is None or test is None:
        return False
    attacker_player = event.player or event.subject_controller
    game = context.game
    you = context.controller
    targets = match.group("targets")
    count = 0
    for attack in game.combat.attacks:
        attacker = game.find_by_id(attack.attacker_id)
        if not isinstance(attacker, CardState):
            continue
        if attacker_player is not None and game.controller_of(attacker).username != attacker_player:
            continue
        defender = attack.defender
        if defender.is_player:
            if defender.username == you and "you" in targets.split(" and/or ")[0].split():
                count += 1
            continue
        permanent = game.resolve_target(defender)
        if (
            isinstance(permanent, CardState)
            and "planeswalkers you control" in targets
            and game.controller_of(permanent).username == you
            and Type.PLANESWALKER in game.characteristics_of(permanent).types
        ):
            count += 1
    return test(count)


def _chosen_colors(state: "CardState") -> tuple:
    """The colors its "as [this] enters, choose ..." answer named (CR
    614.12a), one letter each."""
    from ...models.card import Color
    from ...models.card_state import ChoiceKind

    choice = state.choice
    if choice is None or choice.kind not in (ChoiceKind.COLOR, ChoiceKind.COLORS):
        return ()
    return tuple(Color(letter) for letter in choice.value)


def _is_one_of_the_chosen_colors(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "it's at least one of the chosen colors" (Tablet of the Guilds): the
    spell's colors (CR 105.2) and the source's chosen ones share one."""
    subject = _subject(context, match.group("subject"))
    source = context.source
    if subject is None or source is None:
        return False
    chosen = set(_chosen_colors(source))
    return bool(chosen.intersection(_Seen(context, subject, past=False).colors))


def _cost_contains_symbol(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "that spell's mana cost or that ability's activation cost contains
    {X}" (Unbound Flourishing): the cast spell's own mana cost, or the cost
    of the ability the activation event announced (CR 107.3, CR 602.1a)."""
    from ...models.card_state import CardState
    from ..triggers import ExtraTriggerEvent, TriggerEvent

    event = context.event
    symbol = match.group("symbol").upper()
    if event is None or event.subject_id is None:
        return False
    parts = match.group("costs")
    if event.event is TriggerEvent.CAST_SPELL and "mana cost" in parts:
        spell = context.game.find_by_id(event.subject_id)
        mana_cost = spell.mana_cost if isinstance(spell, CardState) else None
        return symbol in (str(mana_cost or "") or "").upper()
    if event.event is ExtraTriggerEvent.ABILITY_ACTIVATED and "activation cost" in parts:
        for item in reversed(context.game.abilities_on_stack):
            if item.source_id == event.subject_id:
                cost = getattr(item.ability, "cost", None) or ""
                return symbol in cost.upper()
    return False


# -- designations of a player ----------------------------------------------------


def _citys_blessing(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "you have the city's blessing" (CR 702.131c) - the designation
    `Player.has_citys_blessing` holds, for "you" (CR 109.5)."""
    held = context.game.player(context.controller).has_citys_blessing
    return not held if match.group("negated") else held


def _full_party(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "you have a full party" (CR 700.8c)."""
    from ..designations import has_full_party

    held = has_full_party(context.game, context.controller)
    return not held if match.group("negated") else held


def _chose_another_ring_bearer(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "you chose a creature other than Aragorn as your Ring-bearer" (CR
    701.54a): the creature the Ring's temptation event names was chosen, and
    it is not the source."""
    from ..triggers import ExtraTriggerEvent

    event = context.event
    other = _subject(context, match.group("other"))
    if event is None or event.event is not ExtraTriggerEvent.RING_TEMPTS_YOU:
        return False
    if event.subject_id is None or other is None:
        return False
    return event.subject_id != other.id


def _controls_a_ring_bearer(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "you don't control a Ring-bearer" (CR 701.54e: `Game.ring_bearer_of`)."""
    held = context.game.ring_bearer_of(context.controller) is not None
    return not held if match.group("negated") else held


def _completed_a_dungeon(context: "ConditionContext", match: re.Match[str]) -> bool:
    """ "you've completed a dungeon", "you haven't completed Tomb of
    Annihilation" (CR 309.7)."""
    from ..dungeon import completed_dungeon_names

    names = completed_dungeon_names(context.game, context.controller)
    which = match.group("which")
    if which in ("a dungeon", "one or more dungeons"):
        held = bool(names)
    else:
        held = which in {name.lower() for name in names}
    return not held if match.group("negated") else held


READERS: tuple[ConditionReader, ...] = (
    ConditionReader(
        re.compile(r"it (?:is(?P<negated>n't| not)) a mana ability|it is a mana ability"),
        _activated_ability_is_mana_ability,
    ),
    ConditionReader(
        re.compile(r"it (?:is(?P<negated>n't| not)|is) being declared as an attacker"),
        _declared_as_an_attacker,
    ),
    ConditionReader(
        re.compile(rf"(?P<subject>{SUBJECT})(?:'s| is)(?P<negated> not)? attacking alone"),
        _attacking_alone,
    ),
    ConditionReader(
        re.compile(
            rf"(?P<subject>{SUBJECT})(?:'s| is|'re| are)(?P<negated>n'?t| not)? attacking an? "
            r"(?P<quality>player|planeswalker|battle)"
        ),
        _attacking_defender_quality,
    ),
    ConditionReader(
        re.compile(
            rf"(?P<subject>{SUBJECT}) (?P<verb>has|had|doesn't have|does not have|didn't have"
            rf"|did not have) (?:(?P<q>{QUANTITY}) )?(?:{_KIND} )?counters? on "
            r"(?:it|him|her|them|itself)"
        ),
        _has_counters,
    ),
    ConditionReader(
        re.compile(
            rf"there (?:is|are) (?P<q>{QUANTITY}) {_KIND} counters? on (?P<subject>{SUBJECT})"
        ),
        _there_are_counters_on,
    ),
    ConditionReader(
        re.compile(
            rf"(?P<subject>its|{SUBJECT}'s) mana value is (?:equal to )?(?:(?P<plus>{COUNT}) "
            rf"plus )?the number of {_KIND} counters on (?P<holder>{SUBJECT})"
        ),
        _mana_value_against_counters,
    ),
    ConditionReader(
        re.compile(
            rf"(?:(?P<q>{QUANTITY}) )?cards? (?:have|has) been exiled with (?P<holder>{SUBJECT})"
        ),
        _cards_exiled_with,
    ),
    ConditionReader(
        re.compile(
            rf"there (?:is|are) (?:(?P<q>{QUANTITY}) )?cards? exiled with (?P<holder>{SUBJECT})"
        ),
        _cards_exiled_with,
    ),
    ConditionReader(
        re.compile(
            rf"(?P<subject>{SUBJECT}) has the same name as (?:one of )?the cards? exiled with "
            rf"(?P<holder>{SUBJECT})"
        ),
        _same_name_as_exiled,
    ),
    ConditionReader(
        re.compile(
            rf"(?P<subject>{SUBJECT})(?:'s| is) (?P<zone>on the battlefield|exiled|in exile"
            rf"|in your graveyard|in a graveyard|in your hand)(?: with (?P<q>{QUANTITY}) "
            rf"{_KIND} counters? on (?:it|him|her|them))?"
        ),
        _in_zone,
    ),
    ConditionReader(
        re.compile(
            rf"(?P<q>{QUANTITY}) {_KIND} counters? (?:was|were) removed from (?:a|one or more) "
            r"permanents? you control(?:led)? this turn"
        ),
        _counters_removed_this_turn,
    ),
    ConditionReader(
        re.compile(
            rf"an? permanent with (?:an?|one or more) {_KIND} counters? on it was put into "
            r"(?P<whose>a|your) graveyard(?: from the battlefield)? this turn"
        ),
        _put_into_graveyard_with_counter,
    ),
    ConditionReader(
        re.compile(
            rf"(?P<subject>{SUBJECT})(?P<verb>'s| is| was| isn't| wasn't| are| were)"
            rf"(?P<negated> not)? (?P<state>{_STATE_WORD}(?: or {_STATE_WORD})*)"
        ),
        _is_in_state,
    ),
    ConditionReader(
        re.compile(rf"(?P<subject>{SUBJECT})(?:'s| is) enchanted by (?P<q>{QUANTITY}) auras?"),
        _enchanted_by,
    ),
    ConditionReader(
        re.compile(
            rf"(?P<subject>{SUBJECT})(?P<verb>'s| is| was| isn't| wasn't| is not| was not| are"
            rf"| were) (?P<quality>{_QUALITY_LIST})"
        ),
        _is_quality,
    ),
    ConditionReader(
        re.compile(
            rf"(?P<subject>{POSSESSIVE}) (?P<stat>power|toughness) (?P<tense>is|was) "
            rf"(?P<q>{QUANTITY})"
        ),
        _stat_compared_with_number,
    ),
    # "the creature had power 4 or greater" (Anax, Hardened in the Forge): the
    # same comparison, worded with "had" and the event's subject as "the
    # creature" (CR 603.10a, CR 608.2h: last known information).
    ConditionReader(
        re.compile(
            r"(?P<subject>the creature|it|that creature) (?P<tense>had|has) "
            rf"(?P<stat>power|toughness) (?P<q>{QUANTITY})"
        ),
        _stat_compared_with_number,
    ),
    ConditionReader(
        re.compile(
            rf"(?P<subject>{SUBJECT}) (?P<verb>has|had|doesn't have|does not have|didn't have"
            rf"|did not have) (?P<keyword>{_KEYWORD})"
        ),
        _has_keyword,
    ),
    ConditionReader(
        re.compile(rf"(?P<subject>{SUBJECT})(?:'s| is) (?P<power>\d+)/(?P<toughness>\d+)"),
        _power_toughness_is,
    ),
    ConditionReader(
        re.compile(
            rf"(?P<subject>{SUBJECT}) has greater (?P<stats>power or toughness|power|toughness) "
            rf"than (?P<other>{SUBJECT})"
        ),
        _greater_stat_than,
    ),
    ConditionReader(
        re.compile(
            rf"(?P<subject>{POSSESSIVE}) (?P<stat>power|toughness) (?P<tense>is|was) "
            rf"(?P<cmp>greater|less) than (?P<other>{POSSESSIVE})(?: (?:power|toughness))?"
        ),
        _stat_compared_with_other,
    ),
    ConditionReader(
        re.compile(
            rf"(?P<subject>{SUBJECT}) was cast from (?:(?P<whose>your|a|its owner's) )?"
            r"(?P<zone>graveyard|hand|library|exile)"
        ),
        _cast_from,
    ),
    ConditionReader(
        re.compile(
            r"(?:one or more of (?:them|those creatures)|they|it|that creature) entered"
            r"(?: the battlefield)?(?: from (?P<entered_zone>a graveyard|your graveyard|exile))? "
            r"or (?:was|were) cast from (?P<cast_zone>a graveyard|your graveyard|exile)"
        ),
        _entered_or_cast_from,
    ),
    ConditionReader(
        re.compile(rf"(?P<subject>{SUBJECT}) shares a card type with the exiled card"),
        _shares_a_card_type_with_exiled,
    ),
    ConditionReader(
        re.compile(rf"(?P<subject>{SUBJECT}) is attached to (?P<quality>{_QUALITY_LIST})"),
        _attached_to_quality,
    ),
    ConditionReader(
        re.compile(
            rf"(?P<subject>{SUBJECT}) (?:(?P<negated>didn't|did not) deal|dealt) combat damage "
            rf"to (?P<quality>{_QUALITY_LIST}) this turn"
        ),
        _dealt_combat_damage_to_this_turn,
    ),
    ConditionReader(
        re.compile(rf"(?P<subject>{SUBJECT}) has a single target"),
        _has_a_single_target,
    ),
    ConditionReader(
        re.compile(rf"(?P<subject>{SUBJECT}) targets only (?P<target>{SUBJECT})"),
        _targets_only,
    ),
    ConditionReader(
        re.compile(
            rf"(?P<subject>{SUBJECT}) targets (?P<q>{QUANTITY}) (?P<other>other )?"
            rf"(?P<quality>{_QUALITY_WORD})s?(?: (?P<who>you control|an opponent controls"
            r"|you don't control))?"
        ),
        _targets_quantity,
    ),
    ConditionReader(
        re.compile(
            rf"an? (?P<kind>aura|equipment) (?:(?P<who>you|an opponent) controlled )?was attached "
            rf"to (?P<subject>{SUBJECT})"
        ),
        _attached_was,
    ),
    ConditionReader(
        re.compile(
            rf"(?P<q>{QUANTITY}) of those creatures are attacking (?P<targets>you and/or "
            r"planeswalkers you control|you|planeswalkers you control)"
        ),
        _those_attackers_at_you,
    ),
    ConditionReader(
        re.compile(rf"(?P<subject>{SUBJECT})(?:'s| is) (?:at least )?one of the chosen colors"),
        _is_one_of_the_chosen_colors,
    ),
    ConditionReader(
        re.compile(
            r"(?P<costs>(?:that spell's mana cost|that ability's (?:activation )?cost)"
            r"(?: or (?:that spell's mana cost|that ability's (?:activation )?cost))?) "
            r"contains? (?P<symbol>\{[a-z0-9/]+\})"
        ),
        _cost_contains_symbol,
    ),
    ConditionReader(
        re.compile(r"you (?:have|(?P<negated>don't have|do not have)) the city's blessing"),
        _citys_blessing,
    ),
    ConditionReader(
        re.compile(r"you (?:have|(?P<negated>don't have|do not have)) a full party"),
        _full_party,
    ),
    ConditionReader(
        re.compile(rf"you chose a creature other than (?P<other>{SUBJECT}) as your ring-bearer"),
        _chose_another_ring_bearer,
    ),
    ConditionReader(
        re.compile(r"you (?:control|(?P<negated>don't control|do not control)) a ring-bearer"),
        _controls_a_ring_bearer,
    ),
    ConditionReader(
        re.compile(
            r"you(?:'ve| have|(?P<negated> haven't| have not)) completed "
            r"(?P<which>a dungeon|one or more dungeons|[a-z][a-z' -]+)"
        ),
        _completed_a_dungeon,
    ),
)


#: The words an effect's own "if" uses for an object an earlier instruction
#: named (CR 608.2c) - which only the parser of that instruction knows.
_ANAPHORS = frozenset(
    {
        "it",
        "its",
        "he",
        "his",
        "she",
        "her",
        "they",
        "their",
        "that creature",
        "that permanent",
        "that spell",
        "that card",
    }
)
#: Readers whose clause is about the trigger event's objects by construction
#: ("they entered ...", "those creatures", "that spell's mana cost").
_EVENT_ONLY_READERS = frozenset(
    {"_entered_or_cast_from", "_those_attackers_at_you", "_cost_contains_symbol"}
)


def names_an_anaphor(text: str) -> bool:
    """Whether `text` (or one half of it) is claimed here only through a
    subject that is an anaphor - "it", "its", "that creature". Read as an
    intervening "if" (CR 603.4) or an activation restriction, the anaphor is
    the trigger event's object or the source (`_subject`); inside a resolving
    effect's own "if" (CR 608.2c) it is whatever an earlier instruction of that
    effect named - a target, a revealed card - which a condition context does
    not carry. `machines/effects.py` asks this before gating an effect on such
    a clause, so it stays unread there rather than being asked of the wrong
    object."""
    from . import _binary_splits, _normalized

    clause = _normalized(text)
    candidates = [
        clause,
        *(half for _j, left, right in _binary_splits(clause) for half in (left, right)),
    ]
    for candidate in candidates:
        for reader in READERS:
            match = reader.pattern.fullmatch(candidate)
            if match is None:
                continue
            if getattr(reader.read, "__name__", "") in _EVENT_ONLY_READERS:
                return True
            for name in ("subject", "target", "other", "holder"):
                value = match.groupdict().get(name)
                if value is not None and value.removesuffix("'s") in _ANAPHORS:
                    return True
    return False
