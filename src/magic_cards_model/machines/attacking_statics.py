"""Layer 6 keyword grants (CR 613.1f) to a group filtered on combat state
(CR 508.1k, "attacking") rather than the token status `machines/layers.
AttackingTokensControlledBy` already covers.

"Attacking creatures you control have double strike." (Raphael, the
Nightwatcher) and "Attacking Ninjas you control have deathtouch." (Dark Leo &
Shredder) are the same shape either way: a keyword granted right now to
whichever of the controller's own creatures - optionally narrowed to a
printed subtype list, CR 205.3m - are attacking at this moment. CR 508.1k's
attacking status is not a characteristic and never reaches the board, so
`AttackingGroupControlledBy` (`machines/layers.py`) reads it fresh off
`LayerContext.attacking` on every computation (CR 613.5): a creature stops
being selected the instant it is removed from combat (CR 506.4), and the
grant never lingers past that.

Double strike matters only "as the combat damage step begins" (CR 702.4b):
this file grants no more than an ordinary layer-6 ability, and it is the
combat machinery that already reads a creature's *current* keywords at that
moment, so nothing here has to special-case the timing itself. Deathtouch
(CR 702.2b) is likewise read live, off the same computed characteristics, at
whatever moment the game actually checks it.

Both regexes are read by `machines/layers._parse_layer_sentence`, imported
there lazily (inside the function, not at module scope) to avoid a cycle -
this module imports the selector and a handful of small helpers *from*
`layers.py` at module scope, so `layers.py` cannot import this module back at
its own module scope without a loop.
"""

import re
from collections.abc import Sequence

from ..models.card_state import CardState
from .layers import (
    AttackingGroupControlledBy,
    ContinuousEffect,
    EffectBuilder,
    Layer,
    LayerContext,
    TappedCreaturesControlledBy,
    _source_line_for,
    _split_and_validate_keywords,
    grant_ability,
)
from .triggers import _parse_subtype_list

#: "Attacking creatures you control have double strike[, deathtouch, ...]."
#: The generic, case-insensitive "creatures" subject - no subtype filter at
#: all, every creature the controller attacks with.
_ATTACKING_CREATURES_KEYWORD_GRANT_RE = re.compile(
    r"^attacking creatures you control have (?P<keywords>[a-z][a-z ,{}0-9]*?)\.?$",
    re.IGNORECASE,
)

#: "Attacking `<Subtype[, Subtype, or Subtype]>`s you control have
#: `<keyword[, keyword, and keyword]>`." (Dark Leo & Shredder's own
#: "Ninjas"; Crossway Troublemakers' own "Vampires", verified Modern/
#: Pioneer/Standard legal - "have deathtouch and lifelink", a two-keyword
#: proof of generality on a second printing). Matched **case-sensitively**
#: against the sentence as printed - Oracle's own capitalisation is what
#: tells a subtype word from an ordinary lowercase adjective, the identical
#: convention `_parse_subtype_list`'s own callers already rely on - so this
#: is tried only after the all-lowercase "creatures" shape above has already
#: declined.
#:
#: Each word is matched **non-greedily** (`[A-Za-z]*?`) so the trailing plural
#: `s?` outside the group is what consumes "Ninjas"'s own final letter,
#: leaving `_parse_subtype_list` the singular "Ninja" it expects
#: (`_parse_subtype_list`'s own docstring: it does not strip a plural
#: itself). A greedy word class would swallow that "s" into the captured
#: text instead, handing the reader "Ninjas" - a word `canonical_subtype`
#: never recognises - and the grant would parse clean but select nothing.
_ATTACKING_SUBTYPE_KEYWORD_GRANT_RE = re.compile(
    r"^Attacking (?P<subtypes>[A-Z][A-Za-z]*?(?:,\s*[A-Z][A-Za-z]*?)*"
    r"(?:,?\s+or\s+[A-Z][A-Za-z]*?)?)s? "
    r"you control have (?P<keywords>[a-z][a-z ,{}0-9]*?)\.?$"
)


def _attacking_group_keyword_grant_builder(
    keywords: list[str], *, subtypes: tuple[str, ...], line: str
) -> EffectBuilder:
    """One `ContinuousEffect` per granted keyword, each selecting the
    controller's own currently-attacking creatures (optionally narrowed to
    `subtypes`) fresh at every computation - see this module's own docstring
    for why the selector, not this builder, is what re-reads combat state."""

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        selector = AttackingGroupControlledBy(
            username=source.controller,
            attacking_ids=tuple(sorted(context.attacking, key=str)),
            subtypes=subtypes,
        )
        group = "attacking creatures" if not subtypes else f"attacking {'/'.join(subtypes)}s"
        return [
            ContinuousEffect(
                description=f"{source.name}: {group} you control have {keyword}",
                layer=Layer.ABILITY,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=_source_line_for(source, line),
                selector=selector,
                modification=grant_ability(keyword),
            )
            for keyword in keywords
        ]

    return builder


def parse_attacking_group_keyword_grant(sentence: str) -> EffectBuilder | None:
    """Either of this module's two shapes, or `None` if `sentence` is
    neither. Tried by `machines/layers._parse_layer_sentence`."""
    match = _ATTACKING_CREATURES_KEYWORD_GRANT_RE.fullmatch(sentence)
    if match is not None:
        keywords = _split_and_validate_keywords(match.group("keywords"))
        if keywords is None:
            return None
        return _attacking_group_keyword_grant_builder(keywords, subtypes=(), line=sentence)
    match = _ATTACKING_SUBTYPE_KEYWORD_GRANT_RE.fullmatch(sentence)
    if match is not None:
        subtypes = _parse_subtype_list(match.group("subtypes"))
        if subtypes is None:
            return None
        keywords = _split_and_validate_keywords(match.group("keywords"))
        if keywords is None:
            return None
        return _attacking_group_keyword_grant_builder(keywords, subtypes=subtypes, line=sentence)
    return None


# --------------------------------------------------------------------------
# Tapped-status group keyword grants (CR 110.5) - the tapped/untapped twin of
# this module's own attacking-status grant just above.
# --------------------------------------------------------------------------
#
# "Other tapped creatures you control have indestructible." (Adept
# Watershaper) is CR 110.5's physical tapped status, not a characteristic
# `Characteristics` carries any more than CR 508.1k's attacking status is -
# `TappedCreaturesControlledBy` (`machines/layers.py`) reads a snapshot of
# tapped ids off `LayerContext.tapped_ids` the identical way `AttackingGroup
# ControlledBy` reads `LayerContext.attacking`, rebuilt on every CR 613.5
# computation so a creature stops being selected the instant it untaps.

#: "Other tapped creatures you control have indestructible[, deathtouch,
#: ...]." - the generic "creatures" subject, every one of the controller's
#: own tapped creatures except the source itself. "Other" is not optional
#: here (unlike the attacking-status sibling's plain "attacking creatures"):
#: every printing of this template excludes the source, since the source
#: itself is usually the thing being kept safe from the group's own effect
#: (Adept Watershaper wants indestructible on its *teammates*, not on
#: itself, which never taps to earn it).
_TAPPED_CREATURES_KEYWORD_GRANT_RE = re.compile(
    r"^other tapped creatures you control (?:have|has) "
    r"(?P<keywords>[a-z][a-z ,{}0-9]*?)\.?$",
    re.IGNORECASE,
)


def _tapped_group_keyword_grant_builder(keywords: list[str], *, line: str) -> EffectBuilder:
    """One `ContinuousEffect` per granted keyword, selecting the controller's
    own currently-tapped creatures (the source excluded) fresh at every
    computation - see this module's own docstring for why the selector, not
    this builder, is what re-reads tap status."""

    def builder(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        selector = TappedCreaturesControlledBy(
            username=source.controller,
            tapped_ids=tuple(sorted(context.tapped_ids, key=str)),
            excludes_self=True,
            source_id=source.id,
        )
        return [
            ContinuousEffect(
                description=f"{source.name}: other tapped creatures you control have {keyword}",
                layer=Layer.ABILITY,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=_source_line_for(source, line),
                selector=selector,
                modification=grant_ability(keyword),
            )
            for keyword in keywords
        ]

    return builder


def parse_tapped_group_keyword_grant(sentence: str) -> EffectBuilder | None:
    """`_TAPPED_CREATURES_KEYWORD_GRANT_RE`'s shape, or `None`. Tried by
    `machines/layers._parse_layer_sentence`."""
    match = _TAPPED_CREATURES_KEYWORD_GRANT_RE.fullmatch(sentence)
    if match is None:
        return None
    keywords = _split_and_validate_keywords(match.group("keywords"))
    if keywords is None:
        return None
    return _tapped_group_keyword_grant_builder(keywords, line=sentence)
