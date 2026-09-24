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
#: counter is `counters['flying']`" - lower-cased, spaces kept). Decayed,
#: exalted and shadow are in the rule's own list but have no reading
#: vocabulary anywhere in this engine yet (no `Keyword` member, no
#: `KEYWORDS_OUTSIDE_COMBAT` entry) - granting a line for them would be
#: correct and inert, since nothing reads it, so they are left off this
#: constant rather than granted a dead line; see this module's own docstring
#: for the two names that *did* need adding (indestructible, hexproof).
KEYWORD_COUNTER_KEYWORDS: frozenset[str] = frozenset(
    {
        Keyword.FLYING.value,
        Keyword.FIRST_STRIKE.value,
        Keyword.DOUBLE_STRIKE.value,
        Keyword.DEATHTOUCH.value,
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

#: The keywords `machines/layers.py::_keyword_counter_lines` already grants a
#: line for on its own (every `Keyword` member) - this module supplements
#: only the rest of `KEYWORD_COUNTER_KEYWORDS`, so a keyword already granted
#: there is never granted twice.
_ALREADY_GRANTED_BY_LAYERS = frozenset(keyword.value for keyword in Keyword)

#: What CR 122.1b's own vocabulary calls each of the keywords this module
#: grants a line for, title-cased the identical way `_keyword_counter_lines`
#: already spells a granted keyword - `machines/combat.py::_reading_
#: vocabulary` compares case-insensitively, so the casing itself is
#: cosmetic, but matching it keeps a granted line indistinguishable from one
#: `machines/layers.py` would have written.
_KEYWORD_COUNTER_LINE_TEXT: dict[str, str] = {
    keyword: keyword.replace("_", " ").title()
    for keyword in KEYWORD_COUNTER_KEYWORDS
    if keyword not in _ALREADY_GRANTED_BY_LAYERS
}


def supplemental_keyword_counter_lines(counters: dict[str, int]) -> tuple[str, ...]:
    """CR 122.1b's own ability lines for a keyword counter that
    `machines/layers.py::_keyword_counter_lines` does not already grant one
    for (indestructible, hexproof) - see this module's own docstring.

    `counters` is a permanent's counter map exactly as `Characteristics.
    counters` already carries it (`CardState.counters.as_dict()`), so a
    caller with a `Characteristics` in hand passes `chars.counters` straight
    through.
    """
    return tuple(
        text for keyword, text in _KEYWORD_COUNTER_LINE_TEXT.items() if counters.get(keyword, 0) > 0
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
    permanent.counters.remove(SHIELD_COUNTER_KIND, 1)


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
