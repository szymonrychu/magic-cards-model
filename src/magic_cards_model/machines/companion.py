"""Companion (CR 702.139): a keyword ability that functions outside the game.

CR 702.139a: "Companion is a keyword ability that functions outside the game.
It's written as 'Companion—[Condition].' Before the game begins, you may
reveal one card you own from outside the game with a companion ability whose
condition is fulfilled by your starting deck. (See rule 103.2b.) Once during
the game, any time you have priority and the stack is empty, but only during a
main phase of your turn, you may pay {3} and put that card into your hand.
This is a special action that doesn't use the stack (see rule 116.2g)."

Two halves, on two sides of the boundary CR 400.11a draws:

- **The deck-legality half** (this module, plus `Deck.companion_problems`):
  whether a chosen companion's printed condition is fulfilled by the
  player's starting deck (CR 702.139b: "your starting deck ... after you've
  set aside any sideboard cards"). The condition is parsed off the card's own
  oracle text - Kaheera, Yorion, Lurrus and the rest each print a different
  condition in the same templated shape ("Companion — [Condition]. (reminder
  text)"), so this reads the shape rather than keying behaviour to a name.
- **The in-game half** (`models/player.py`'s `Player.companion_id`/
  `companion_action_used`, `models/game.py`'s `Game.why_cannot_bring_
  companion_to_hand`/`begin_bringing_companion_to_hand`/`bring_companion_to_
  hand`): CR 116.2g's special action, which moves the already-legal
  companion from outside the game (`Zone.SIDEBOARD`, per `models/zone.py`)
  into the player's hand, once per game, for {3}.

Every CR number here was looked up with `mise run rules:find` against the
2026-08-19 Comprehensive Rules text in the session that wrote this module.
"""

import re
from dataclasses import dataclass

from ..models.card import (
    Card,
    Type,
    has_changeling,
    subtypes_of,
    types_of,
    with_every_creature_type,
)
from ..numbers import parse_count

#: CR 702.139a's own templating: "Companion—[Condition]." The reminder text
#: that follows in parentheses is not part of the condition and is dropped.
_COMPANION_LINE_RE = re.compile(
    r"^companion\s*[—-]\s*(?P<condition>[^(\n]+?)\.?\s*(?:\(.*\))?\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def has_companion(card: Card) -> bool:
    """CR 702.139a: whether this card has the companion keyword.

    Read off Scryfall's own `keywords` list, the same way `machines/keywords.
    has_rebound`/`has_persist` do - a card that only *mentions* "companion" in
    some other ability's reminder text is never mistaken for one that prints
    the keyword.
    """
    return any(keyword.lower() == "companion" for keyword in card.keywords)


def companion_condition_text(card: Card) -> str | None:
    """The condition clause off "Companion—[Condition]." (CR 702.139a), or
    None if the card has no such line at all.

    The reminder text in parentheses ("If this card is your chosen
    companion, ...") is stripped - it restates CR 702.139a itself, not the
    per-card condition, and every companion printed so far carries it
    verbatim.
    """
    if not has_companion(card):
        return None
    match = _COMPANION_LINE_RE.search(card.oracle_text or "")
    if match is None:
        return None
    return match.group("condition").strip()


@dataclass(frozen=True)
class CompanionConditionResult:
    """The outcome of checking one companion's condition against a decklist.

    `satisfied` is `None` when the condition's printed shape could not be
    read at all - CR 702.139a only lets a player reveal a companion "whose
    condition is fulfilled by your starting deck", and a condition this
    reader cannot evaluate is not *known* to be fulfilled, so it is refused
    the same fail-closed way `machines/triggers.intervening_if_holds` refuses
    an unrecognised intervening *if* clause, rather than being waved through.
    """

    satisfied: bool | None
    reason: str


#: Kaheera's own shape: "Each creature card in your starting deck is a Cat,
#: Elemental, Nightmare, Dinosaur, or Beast card." One or more card types or
#: subtypes, disjunctively, restricted to one printed card-type qualifier.
_TYPE_DISJUNCTION_RE = re.compile(
    r"^each (?P<qualifier>[a-z]+) card in your starting deck is an? "
    r"(?P<options>.+?) cards?$",
    re.IGNORECASE,
)

#: Lurrus's own verified shape: "Each permanent card in your starting deck
#: has mana value 2 or less." - checked against the real printing added to
#: the fixture pool (`lurrus_of_the_dream_den.json`), not assumed.
_MANA_VALUE_THRESHOLD_RE = re.compile(
    r"^each (?P<qualifier>[a-z]+) card in your starting deck has mana value "
    r"(?P<number>\w+) or (?P<comparison>less|greater)$",
    re.IGNORECASE,
)

#: Keruga's own verified shape (`resolve_cards`, this session): "Your
#: starting deck contains only cards with mana value 3 or greater and land
#: cards." - a different template from Lurrus's, "contains only" rather than
#: "each ... has", with lands named as an explicit exemption rather than
#: excluded by a "permanent"/"nonland" qualifier word. Read as applying to
#: every nonland card, which "and land cards" being a *separate*, unrestricted
#: clause makes equivalent to.
_CONTAINS_ONLY_MANA_VALUE_THRESHOLD_RE = re.compile(
    r"^your starting deck contains only cards with mana value (?P<number>\w+) "
    r"or (?P<comparison>less|greater)(?: and land cards)?$",
    re.IGNORECASE,
)

#: Gyruda's own verified shape (`resolve_cards`, this session): "Your
#: starting deck contains only cards with even mana values." Obosh's own:
#: "...odd mana values and land cards." Both "contains only", not "each ...
#: has an even/odd mana value" - an earlier draft of this reader assumed the
#: latter without checking and matched neither real card; fixed before
#: shipping, not left as dead code.
_CONTAINS_ONLY_MANA_VALUE_PARITY_RE = re.compile(
    r"^your starting deck contains only cards with (?P<parity>even|odd) mana "
    r"values(?: and land cards)?$",
    re.IGNORECASE,
)

#: Yorion's own verified shape (`resolve_cards`, this session): "Your
#: starting deck contains at least twenty cards more than the minimum deck
#: size." - relative to the format's own minimum (CR 100.2a's 60 by default,
#: `DeckLimits.min_mainboard`), not an absolute count; an earlier draft of
#: this reader assumed a flat "at least 40 cards" and matched no real
#: printing, fixed the same way the mana-value-parity shape was.
_DECK_SIZE_RE = re.compile(
    r"^your starting deck contains at least (?P<number>\w+) cards? more "
    r"than the minimum deck size$",
    re.IGNORECASE,
)

_QUALIFIER_TO_TYPE = {
    "creature": Type.CREATURE,
    "permanent": None,  # every card type that is a permanent
    "nonland": None,  # every card type except land
    "land": Type.LAND,
    "artifact": Type.ARTIFACT,
    "enchantment": Type.ENCHANTMENT,
    "instant": Type.INSTANT,
    "sorcery": Type.SORCERY,
}

_PERMANENT_TYPES = frozenset(
    {Type.ARTIFACT, Type.BATTLE, Type.CREATURE, Type.ENCHANTMENT, Type.LAND, Type.PLANESWALKER}
)


def _qualifying_cards(qualifier: str, cards: list[Card]) -> list[Card] | None:
    """The subset of `cards` a "<qualifier> card"/"nonland card" phrase names.

    `None` for a qualifier this reader does not recognise, which the caller
    treats as an unreadable condition (fail closed).
    """
    lowered = qualifier.strip().lower()
    if lowered == "permanent":
        return [card for card in cards if _PERMANENT_TYPES & set(types_of(card.type_line))]
    if lowered == "nonland":
        return [card for card in cards if Type.LAND not in types_of(card.type_line)]
    card_type = _QUALIFIER_TO_TYPE.get(lowered)
    if card_type is None:
        return None
    return [card for card in cards if card_type in types_of(card.type_line)]


def _deck_card_subtypes(card: Card) -> tuple[str, ...]:
    """A deck card's subtypes before the game begins, changeling included:
    CR 604.3's characteristic-defining abilities "also function outside the
    game and before the game begins", and CR 702.73a makes a changeling card
    every creature type there too."""
    subtypes = subtypes_of(card.type_line)
    if has_changeling(card.front_oracle_text):
        return with_every_creature_type(types_of(card.type_line), subtypes)
    return tuple(subtypes)


def companion_condition_satisfied(
    card: Card, mainboard_cards: list[Card], *, minimum_deck_size: int = 60
) -> CompanionConditionResult:
    """Whether `card`'s printed companion condition (CR 702.139a) holds for
    `mainboard_cards` - CR 702.139b's "starting deck", already narrowed to the
    mainboard by the caller (`Deck.companion_problems`).

    Every shape below is read off the condition's own templated English, not
    off the companion's name - Kaheera and a differently-worded companion
    (Lurrus's mana-value threshold, say) both go through the same readers,
    each verified against a real printing's exact wording with `resolve_cards`
    rather than assumed. A condition whose shape none of them match fails
    closed (`satisfied=None`), same as an unreadable intervening *if*.

    `minimum_deck_size` is CR 100.2a's default sixty, overridable by a caller
    whose format sets a different one (`DeckLimits.min_mainboard`) - Yorion's
    own condition is stated relative to it ("twenty cards more than the
    minimum deck size"), not as a flat number.
    """
    condition = companion_condition_text(card)
    if condition is None:
        return CompanionConditionResult(
            satisfied=None, reason=f"{card.name} has no readable Companion condition"
        )
    normalized = " ".join(condition.split())

    match = _TYPE_DISJUNCTION_RE.match(normalized)
    if match is not None:
        qualifying = _qualifying_cards(match.group("qualifier"), mainboard_cards)
        if qualifying is None:
            return CompanionConditionResult(
                satisfied=None,
                reason=f"{card.name}'s qualifier {match.group('qualifier')!r} is unreadable",
            )
        options = re.split(r",\s*or\s+|,\s*|\s+or\s+", match.group("options").strip())
        wanted = {word.strip().lower() for word in options if word.strip()}
        offending = [
            candidate.name
            for candidate in qualifying
            if not (wanted & {t.lower() for t in _deck_card_subtypes(candidate)})
        ]
        if offending:
            return CompanionConditionResult(
                satisfied=False,
                reason=f"{', '.join(offending)} is not among {sorted(wanted)}",
            )
        return CompanionConditionResult(satisfied=True, reason=f"{card.name}'s condition holds")

    match = _MANA_VALUE_THRESHOLD_RE.match(normalized)
    if match is not None:
        qualifying = _qualifying_cards(match.group("qualifier"), mainboard_cards)
        number = parse_count(match.group("number"), article=False)
        if qualifying is None or number is None:
            return CompanionConditionResult(
                satisfied=None, reason=f"{card.name}'s mana-value threshold is unreadable"
            )
        comparison = match.group("comparison").lower()
        offending = [
            candidate.name
            for candidate in qualifying
            if (candidate.cmc > number if comparison == "less" else candidate.cmc < number)
        ]
        if offending:
            return CompanionConditionResult(
                satisfied=False,
                reason=f"{', '.join(offending)} breaks the mana value {comparison} {number} rule",
            )
        return CompanionConditionResult(satisfied=True, reason=f"{card.name}'s condition holds")

    match = _CONTAINS_ONLY_MANA_VALUE_THRESHOLD_RE.match(normalized)
    if match is not None:
        # "... and land cards" exempts lands unconditionally (Keruga), which
        # is exactly `_qualifying_cards("nonland", ...)`'s own restriction.
        qualifying = _qualifying_cards("nonland", mainboard_cards)
        number = parse_count(match.group("number"), article=False)
        if number is None:
            return CompanionConditionResult(
                satisfied=None, reason=f"{card.name}'s mana-value threshold is unreadable"
            )
        comparison = match.group("comparison").lower()
        offending = [
            candidate.name
            for candidate in qualifying
            if (candidate.cmc > number if comparison == "less" else candidate.cmc < number)
        ]
        if offending:
            return CompanionConditionResult(
                satisfied=False,
                reason=f"{', '.join(offending)} breaks the mana value {comparison} {number} rule",
            )
        return CompanionConditionResult(satisfied=True, reason=f"{card.name}'s condition holds")

    match = _CONTAINS_ONLY_MANA_VALUE_PARITY_RE.match(normalized)
    if match is not None:
        # "... and land cards" (Obosh) exempts lands the same way; Gyruda's
        # own wording omits the clause entirely and applies to every card.
        qualifying = (
            _qualifying_cards("nonland", mainboard_cards)
            if "and land cards" in normalized
            else mainboard_cards
        )
        wants_even = match.group("parity").lower() == "even"
        offending = [
            candidate.name
            for candidate in qualifying
            if (int(candidate.cmc) % 2 == 0) != wants_even
        ]
        if offending:
            return CompanionConditionResult(
                satisfied=False,
                reason=f"{', '.join(offending)} breaks the {match.group('parity')}-mana-value rule",
            )
        return CompanionConditionResult(satisfied=True, reason=f"{card.name}'s condition holds")

    match = _DECK_SIZE_RE.match(normalized)
    if match is not None:
        number = parse_count(match.group("number"), article=False)
        if number is None:
            return CompanionConditionResult(
                satisfied=None, reason=f"{card.name}'s deck-size threshold is unreadable"
            )
        required = minimum_deck_size + number
        if len(mainboard_cards) < required:
            return CompanionConditionResult(
                satisfied=False,
                reason=f"{len(mainboard_cards)} cards is fewer than the {required} required",
            )
        return CompanionConditionResult(satisfied=True, reason=f"{card.name}'s condition holds")

    return CompanionConditionResult(
        satisfied=None, reason=f"{card.name}'s condition {condition!r} is not a recognised shape"
    )
