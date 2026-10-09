"""CR 122.1b/122.1c: two counter kinds the rules themselves give meaning to,
beyond `machines/layers.py`'s own narrower "combat keyword" grant.

Every rule below was read whole with `mise run rules:find` in the session
that wrote this file.

**CR 122.1b** - "A keyword counter on a permanent or on a card in a zone
other than the battlefield causes that object to gain that keyword. The
keywords that a keyword counter can be are flying, first strike, double
strike, deathtouch, decayed, exalted, haste, hexproof, indestructible,
lifelink, menace, reach, shadow, trample, and vigilance, as well as any
variants of those keywords."

`machines/layers.py`'s own `_keyword_counter_lines` already turns a keyword
counter into a granted ability line (Guide of Souls' reflexive consequence
is what it was built for) - but only for the names in
`machines/combat.py::Keyword`, the module's *combat* vocabulary (flying,
reach, trample, menace, haste, vigilance, first strike, double strike,
deathtouch, lifelink, and the rest CR 702 gives combat a rule for).
Indestructible and hexproof are CR 122.1b keywords too, but they are not
combat keywords at all (CR 702.11a, CR 702.12a both call them static
abilities with no combat rule of their own) - they live in `machines/
combat.py::KEYWORDS_OUTSIDE_COMBAT` instead, which `_keyword_counter_lines`
never reads. Captain Marvel, Earth's Protector's own power-up ("Put a +1/+1
counter and an indestructible counter on Captain Marvel.") is what exposed
the gap: the indestructible counter went on, and nothing on the board ever
read it.

This module supplements what layers.py already computes, additively and
from the one place in this codebase that is free to: `Game.characteristics_
of` (owned by this task's own `models/game.py`), which every reader of a
permanent's keywords (`machines/combat.py::has_keyword`,
`machines/keywords.py::is_indestructible`) already goes through. It never
edits `machines/layers.py` or `machines/combat.py` - both are owned by a
different task this round - it only adds ability lines `_keyword_counter_
lines` left off, on top of the `Characteristics` those modules already
computed, the same "grant" shape CR 613.1f already gives every other keyword
counter.

**CR 122.1c** - "One or more shield counters on a permanent create a single
replacement effect and a single prevention effect that protect the
permanent. These effects are 'If this permanent would be destroyed as the
result of an effect, instead remove a shield counter from it' and 'If damage
would be dealt to this permanent, prevent that damage and remove a shield
counter from it.'"

Diamond City's own "move a shield counter" (`tests/scenarios/
test_diamond_city_shield_counter.py`) already proves the counter *moves*;
it never had to prove what the counter *does*, because nothing in the pool
before Captain America, Super-Soldier ("Captain America enters with a
shield counter on him.") put one on a creature that then took damage or was
destroyed. `machines/replacement.py` already carries CR 122.1d's own
identically-shaped stun-counter rule as a single hardcoded check at the one
place every untap passes through (`CardState.untap`) rather than as a
registered `ContinuousEffect` the general layer/replacement machinery
discovers - the same shape this module gives CR 122.1c, at the two places
every destruction and every instance of damage pass through instead
(`Game._destroy_impl`, `Game.deal_damage`), both in `models/game.py`.
"""

import re

from ..models.card_state import CardState
from ..numbers import COUNT, parse_count
from .combat import Keyword

#: CR 122.1b's own closed list of keywords a keyword counter can be, spelled
#: as the counter kind (`CardState.counters`' own docstring: "a flying
#: counter is `counters['flying']`" - lower-cased, spaces kept). Exalted and
#: shadow are in the rule's own list but have no reading vocabulary anywhere
#: in this engine yet (no `Keyword` member, no `KEYWORDS_OUTSIDE_COMBAT`
#: entry) - granting a line for them would be correct and inert, since
#: nothing reads it, so they are left off this constant rather than granted a
#: dead line; see this module's own docstring for the two names that *did*
#: need adding here (indestructible, hexproof). Decayed is now read
#: (`Keyword.DECAYED`, `machines/combat.block_refusal`,
#: `machines/keywords._decayed_ability`), so it is listed below.
#:
#: Every kind here is granted in layer 6 at its own CR 613.7c timestamp by
#: `machines/layers.ContinuousEffects.keyword_counter_grants` (ecl T5), which
#: replaced the post-layer supplement this module used to hand
#: `Game.characteristics_of` for indestructible and hexproof: added after
#: every layer, those two survived a later "loses all abilities", which CR
#: 613.1f's own ordering does not allow.
KEYWORD_COUNTER_KEYWORDS: frozenset[str] = frozenset(
    {
        Keyword.FLYING.value,
        Keyword.FIRST_STRIKE.value,
        Keyword.DOUBLE_STRIKE.value,
        Keyword.DEATHTOUCH.value,
        Keyword.DECAYED.value,
        Keyword.HASTE.value,
        Keyword.LIFELINK.value,
        Keyword.MENACE.value,
        Keyword.REACH.value,
        Keyword.TRAMPLE.value,
        Keyword.VIGILANCE.value,
        "indestructible",
        "hexproof",
    }
)

#: CR 122.1c's own counter kind, as `CardState.counters`/`Game.add_counters`
#: key it - Diamond City's own "Move a shield counter" (`tests/scenarios/
#: test_diamond_city_shield_counter.py`) already uses this exact string.
SHIELD_COUNTER_KIND = "shield"


def has_shield_counter(permanent: CardState) -> bool:
    """Whether `permanent` carries at least one CR 122.1c shield counter
    right now - the presence check both `Game._destroy_impl` and
    `Game.deal_damage` make before consulting CR 702.12b's indestructible or
    CR 615's ordinary prevention shields, so a permanent that has neither of
    those but does have a shield counter is still protected."""
    return permanent.counters[SHIELD_COUNTER_KIND] > 0


def consume_shield_counter(permanent: CardState) -> None:
    """Remove one CR 122.1c shield counter - the "instead" half of both of
    the rule's own replacement/prevention effects, called only once the
    caller has already decided the counter is what stopped the event."""
    permanent.remove_counters(SHIELD_COUNTER_KIND, 1)


#: CR 614.1c's own "[Subject] enters with [a/N] [kind] counter(s) on [him/
#: her]." - `machines/replacement.py::_ENTERS_WITH` already reads this whole
#: shape *except* a gendered pronoun standing in for the impersonal "on it"
#: its own trailing group looks for (`(?:\s+on it)?`) - Captain America,
#: Super-Soldier's own "Captain America enters with a shield counter on
#: him." matches `_ENTERS_WITH` up through `subject`/the "enters with", but
#: "on him" then rides along inside its own `what` group instead of being
#: stripped, so the trailing "on him" defeats `_COUNTERS`'s own `... counters?
#: $` end anchor and the whole clause comes back `UNPARSED` - verified in
#: the session that wrote this file by calling `_ENTERS_WITH.match` and
#: `_try_enters_with` directly against the printed line.
#:
#: `machines/replacement.py` is owned by a different task this round, so
#: this is a fallback, not a fix in place: `Game.enter_the_battlefield`
#: (`models/game.py`, this task's own file) calls it only once the ordinary
#: pipeline has already run and placed nothing, so a printing the ordinary
#: reader already handles correctly is never double-counted.
#: No trailing `$`: Captain America, Super-Soldier's own printing carries
#: reminder text after the sentence's own period ("... on him. (If he would
#: be dealt damage or destroyed, remove a shield counter from him
#: instead.)"), which a `$`-anchored match would refuse outright. Matching
#: only up through "on him."/"on her." and letting anything follow is the
#: same posture every other reader in this codebase takes toward reminder
#: text - read past it, never trip on it.
_ENTERS_WITH_PRONOUN_RE = re.compile(
    r"^.+? enters with (?P<what>.+?) on (?:him|her)\.", re.IGNORECASE
)
_ENTERS_WITH_PRONOUN_COUNTER_DESC_RE = re.compile(
    rf"^(?P<amount>{COUNT}) (?P<kind>[a-z][a-z ]*?) counters?$", re.IGNORECASE
)


def enters_with_counters_pronoun_fallback(oracle_text: str | None) -> tuple[str, int] | None:
    """The `(kind, amount)` a pronoun-suffixed "enters with" line names, or
    `None` when the printing has no such line at all - see this module's
    own docstring just above for why this exists and when it applies.
    """
    for line in (oracle_text or "").splitlines():
        match = _ENTERS_WITH_PRONOUN_RE.match(line.strip())
        if match is None:
            continue
        desc = _ENTERS_WITH_PRONOUN_COUNTER_DESC_RE.match(match.group("what").strip())
        if desc is None:
            continue
        amount = parse_count(desc.group("amount"))
        if amount is None or amount <= 0:
            continue
        return desc.group("kind").strip().lower(), amount
    return None


#: "As long as [subject] has a [kind] counter on [him/her/it], you and other
#: [subtype] you control have [keyword]." - Captain America, Super-Soldier's
#: own "As long as Captain America has a shield counter on him, you and
#: other Heroes you control have hexproof." CR 613.1f's own ordinary "As
#: long as ... has ..." condition on a counter (a plain presence check, CR
#: 122.1) gating a compound grant: the controlling *player* (CR 702.11c) and
#: every *other* permanent with the named subtype that player controls (CR
#: 613.1f) both gain the same keyword.
#:
#: This is a fallback for the identical "different task owns that file"
#: reason `enters_with_counters_pronoun_fallback` is: `machines/casting.py::
#: player_keyword_grant_of_line` only reads a bare "You have `<keyword>`."
#: for the player half, and `machines/layers.py` has no reader for the
#: creature half at all - "you and other `<subtype>`" is not a shape any
#: existing anthem/keyword-grant regex there matches (verified against the
#: sweep: the line came back `static_unaudited` with nothing computed, not
#: a `LayerNotice`, which is how the gap was found). `Game._player_static_
#: keyword_grants`/`Game._supplement_characteristics` (`models/game.py`,
#: this task's own file) are what call it - see each one's own docstring
#: for the half it fills in.
#:
#: `<subtype>` and `<keyword>` are read generally, not hardcoded to
#: "Heroes"/"hexproof" - only the counter kind is left open to any CR 122.1
#: name, the same open universe every other counter-presence check in this
#: codebase already reads.
_CONDITIONAL_GROUP_KEYWORD_GRANT_RE = re.compile(
    r"^as long as .+? has an? (?P<counter_kind>[a-z][a-z ]*?) counter on (?:him|her|it), "
    r"you and other (?P<subtype>[a-z]+) you control have (?P<keyword>[a-z]+)\.?$",
    re.IGNORECASE,
)


def conditional_group_keyword_grant_of_line(
    line: str,
) -> tuple[str, str, str] | None:
    """`(counter_kind, subtype, keyword)` from `_CONDITIONAL_GROUP_KEYWORD_
    GRANT_RE`'s shape, or `None` for any other line - see that constant's
    own docstring. `counter_kind`/`subtype`/`keyword` are all lower-cased;
    `subtype` is left plural exactly as printed ("Heroes"), which is how
    `CardState.subtypes` also spells it (Scryfall's own type-line casing,
    read case-sensitively by every subtype check in this codebase).
    """
    match = _CONDITIONAL_GROUP_KEYWORD_GRANT_RE.fullmatch(line.strip())
    if match is None:
        return None
    return (
        match.group("counter_kind").strip().lower(),
        match.group("subtype").strip(),
        match.group("keyword").strip().lower(),
    )


# -- "enters with a counter for each <description>" counts (CR 614.1c) ------
#
# `enters_count_reader` turns the description after "for each" of an
# "enters with" line into a reader evaluated as the permanent enters (CR
# 614.12): `(game, controller, entering, x) -> int`. The shared
# `machines/effects.amount_expression` reads the "the number of <plural>"
# phrasing; these printings say "for each other Kithkin you control", so the
# singular description is first re-phrased into that plural form, and the
# shapes `amount_expression` has no term for (counters on other creatures,
# spells cast by anyone, mana spent, distinct mana costs, ...) are read here.

_PERMANENT_TYPES = {
    "creature": "creature",
    "artifact": "artifact",
    "land": "land",
    "planeswalker": "planeswalker",
    "enchantment": "enchantment",
    "permanent": None,
}
_COLOR_LETTERS = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}
_BOARD_COUNT_RE = re.compile(
    r"^(?P<other>other )?(?P<nontoken>nontoken )?(?P<color>white |blue |black |red |green )?"
    r"(?P<kinds>[a-z][a-z-]*(?: and/or [a-z][a-z-]*)?)"
    r" you (?:already )?control(?P<counter> with an? \+1/\+1 counter(?: on (?:it|them))?)?$"
)
_GRAVEYARD_COUNT_RE = re.compile(
    r"^(?P<kinds>[a-z][a-z-]*) cards? in (?P<whose>your|all) graveyards?$"
)
_SPLIT_TERMS_RE = re.compile(
    r" and (?:an? \+1/\+1 counter on it )?for each | and each ", re.IGNORECASE
)


def _characteristics(game, permanent):
    return game.computed_board().of(permanent)


def _kind_matcher(word: str):
    """A predicate over computed characteristics for one type or subtype
    word as printed ("creature", "artifact", "Kithkin"), or `None`."""
    from ..models.card import Type

    lowered = word.lower()
    if lowered in _PERMANENT_TYPES:
        wanted = _PERMANENT_TYPES[lowered]
        if wanted is None:
            return lambda chars: True
        return lambda chars: Type(wanted) in chars.types
    from ..data.creature_types import creature_types

    for subtype in creature_types():
        if subtype.lower() == lowered or f"{subtype.lower()}s" == lowered:
            return lambda chars, subtype=subtype: subtype in chars.subtypes
    return None


def _board_count_term(original: str, text: str):
    match = _BOARD_COUNT_RE.match(text)
    if match is None:
        return None
    matchers = [_kind_matcher(word) for word in match.group("kinds").split(" and/or ")]
    if any(matcher is None for matcher in matchers):
        return None
    letter = _COLOR_LETTERS.get((match.group("color") or "").strip())
    other, nontoken = match.group("other"), match.group("nontoken")
    with_counter = match.group("counter") is not None

    def count(game, controller, entering, _x):
        from ..models.card import Color

        total = 0
        for permanent in game.permanents_controlled_by(controller):
            if other and permanent.id == entering.id:
                continue
            if nontoken and permanent.token:
                continue
            chars = _characteristics(game, permanent)
            if not any(matcher(chars) for matcher in matchers):
                continue
            if letter is not None and Color(letter) not in chars.colors:
                continue
            if with_counter and not permanent.counter_count("+1/+1"):
                continue
            total += 1
        return total

    return count


def _graveyard_count_term(text: str):
    match = _GRAVEYARD_COUNT_RE.match(text)
    if match is None:
        return None
    matcher = _kind_matcher(match.group("kinds"))
    if matcher is None:
        return None
    everyone = match.group("whose") == "all"

    def count(game, controller, entering, _x):
        players = game.players if everyone else [game.player(controller)]
        return sum(
            1 for player in players for card in player.graveyard if matcher(_FakeChars(card))
        )

    return count


class _FakeChars:
    """Printed characteristics of a card in a graveyard (CR 109.3), shaped
    like the computed characteristics `_kind_matcher` predicates read."""

    def __init__(self, card: CardState) -> None:
        self.types = tuple(card.types)
        self.subtypes = tuple(card.card.subtypes)


def _spent_total(game, entering) -> int:
    record = game.cast_record_of(entering)
    return sum(record.mana_spent.values()) if record is not None else 0


def _returned_mana_value(game, entering) -> int:
    record = game.cast_record_of(entering)
    return record.returned_mana_value if record is not None else 0


def _convoked_total(game, entering) -> int:
    record = game.cast_record_of(entering)
    return record.convoked if record is not None else 0


def _other_spells_cast(game, controller, entering, _x) -> int:
    total = sum(len(spells) for spells in game.spells_cast_this_turn.values())
    own = any(
        spell.id == entering.id
        for spells in game.spells_cast_this_turn.values()
        for spell in spells
    )
    return max(total - (1 if own else 0), 0)


def _loyalty_on_planeswalkers(game, controller, entering, _x) -> int:
    from ..models.card import Type

    return sum(
        permanent.counters.get("loyalty", 0)
        for permanent in game.permanents_controlled_by(controller)
        if Type.PLANESWALKER in _characteristics(game, permanent).types
    )


def _different_mana_costs(game, controller, entering, _x) -> int:
    from ..models.card import Type

    return len(
        {
            str(card.card.mana_cost)
            for card in game.player(controller).graveyard
            if Type.LAND not in card.types
        }
    )


def _greatest_creature_count(game, controller, entering, _x) -> int:
    from ..models.card import Type

    return max(
        (
            sum(
                1
                for permanent in game.permanents_controlled_by(player.username)
                if Type.CREATURE in _characteristics(game, permanent).types
            )
            for player in game.players_in_game
        ),
        default=0,
    )


def _opponents_who_lost_life(game, controller, entering, _x) -> int:
    return sum(
        1
        for player in game.players_in_game
        if player.username != controller and player.life_lost_this_turn > 0
    )


def _treasure_mana_spent(game, controller, entering, _x) -> int:
    record = game.cast_record_of(entering)
    return record.treasure_mana_spent if record is not None else 0


def _chosen_type_count(game, controller, entering, _x) -> int:
    from ..models.card import Type

    chosen = getattr(entering.choice, "value", entering.choice)
    if not chosen:
        return 0
    return sum(
        1
        for permanent in game.permanents_controlled_by(controller)
        if permanent.id != entering.id
        and Type.CREATURE in _characteristics(game, permanent).types
        and chosen in _characteristics(game, permanent).subtypes
    )


def _chosen_opponent_creatures(game, controller, entering, _x) -> int:
    from ..models.card import Type

    chosen = getattr(entering.choice, "value", entering.choice)
    return sum(
        1
        for permanent in game.permanents_controlled_by(str(chosen))
        if Type.CREATURE in _characteristics(game, permanent).types
    )


_FIXED_COUNT_TERMS = {
    "creature that died this turn": lambda game, c, e, x: game.creatures_died_this_turn,
    "other spell cast this turn": _other_spells_cast,
    "loyalty counter on planeswalkers you control": _loyalty_on_planeswalkers,
    "different mana cost among nonland cards in your graveyard": _different_mana_costs,
    "greatest number of creatures a player controls": _greatest_creature_count,
    "opponent who lost life this turn": _opponents_who_lost_life,
    # CR 702.188a: web-slinging's returned creature, fixed as it was chosen.
    "mana value of the returned creature": lambda game, c, e, x: _returned_mana_value(game, e),
    "mana spent to cast it": lambda game, c, e, x: _spent_total(game, e),
    # CR 702.51c: a creature tapped to pay for a spell with convoke "convoked" it.
    "creature that convoked it": lambda game, c, e, x: _convoked_total(game, e),
    "mana from a treasure spent to cast them": _treasure_mana_spent,
    "creature you control of the chosen type": _chosen_type_count,
    "creature that player controls": _chosen_opponent_creatures,
}


def _pluralised_variants(text: str):
    yield text
    words = text.split(" ")
    for index, word in enumerate(words):
        if word in {"other", "you", "control", "already", "in", "of", "the", "a", "an"}:
            continue
        for suffix in ("s", "es"):
            yield " ".join([*words[:index], word + suffix, *words[index + 1 :]])


def _one_term(description: str):
    text = " ".join(description.strip().rstrip(".").split())
    lowered = text.lower()
    for article in ("the amount of ", "the number of ", "the "):
        if lowered.startswith(article):
            lowered = lowered[len(article) :]
            break
    fixed = _FIXED_COUNT_TERMS.get(lowered)
    if fixed is not None:
        return fixed
    if lowered in ("time it was kicked", "times it was kicked"):
        return _kicked_times
    symbols = _SYMBOLS_SPENT_RE.match(lowered)
    if symbols is not None:
        return _symbol_groups_spent(symbols.group("symbols"))
    term = _board_count_term(text, lowered) or _graveyard_count_term(lowered)
    if term is not None:
        return term
    from .effects import amount_expression

    prefix = "" if lowered.startswith(("the ", "a ")) else "the number of "
    for variant in _pluralised_variants(text):
        reader = amount_expression(prefix + variant)
        if reader is not None:
            return reader
    return None


_N_TIMES_RE = re.compile(rf"^(?P<n>{COUNT}) (?P<op>times|plus) (?P<rest>.+)$", re.IGNORECASE)
_SYMBOLS_SPENT_RE = re.compile(r"^(?P<symbols>(?:\{[wubrg]\})+) spent to cast it$")


def _kicked_times(game, controller, entering, _x) -> int:
    record = game.cast_record_of(entering)
    return record.kicked if record is not None else 0


def _symbol_groups_spent(symbols: str):
    """ "for each {G}{G} spent to cast it" (Clay Champion): how many whole
    groups of that many mana of that colour the spell's payment holds."""
    from ..models.card import Color

    letters = re.findall(r"[wubrg]", symbols)
    color = Color(letters[0].upper())

    def count(game, controller, entering, _x):
        record = game.cast_record_of(entering)
        return record.mana_spent.get(color, 0) // len(letters) if record is not None else 0

    return count


def fixed_enters_count_reader(description: str):
    """The reader for a count this module defines outright ("mana value of the
    returned creature", "creature that convoked it"), tried ahead of the
    general expression readers so a phrase they would half-read is not."""
    text = " ".join(description.strip().rstrip(".").split()).lower()
    for article in ("the amount of ", "the number of ", "the "):
        if text.startswith(article):
            text = text[len(article) :]
            break
    return _FIXED_COUNT_TERMS.get(text)


def enters_count_reader(description: str):
    """The reader for a "for each `<description>`" count evaluated as the
    permanent enters, or `None` when any term of it is not one this engine
    can count (the caller then fails closed with a notice)."""
    multiplied = _N_TIMES_RE.match(description.strip())
    if multiplied is not None:
        n = parse_count(multiplied.group("n"))
        inner = enters_count_reader(multiplied.group("rest"))
        if n is None or inner is None:
            return None
        if multiplied.group("op").lower() == "plus":
            return lambda game, controller, entering, x: n + inner(game, controller, entering, x)
        return lambda game, controller, entering, x: n * inner(game, controller, entering, x)
    terms = [_one_term(part) for part in _SPLIT_TERMS_RE.split(description.strip())]
    if not terms or any(term is None for term in terms):
        return None
    readers = [term for term in terms if term is not None]
    return lambda game, controller, entering, x: sum(
        reader(game, controller, entering, x) for reader in readers
    )
