"""Vivid - CR 207.2c: an ability word has no rules meaning of its own, so
"Vivid" itself names nothing the engine reads. What every Vivid card actually
prints is one amount, CR 105.1's colors among a group of permanents its
controller controls (CR 105.2c: a colorless permanent contributes none),
counted once when the printed effect asks for it (CR 608.2h).

That one amount is printed in several different positions across the ecl
pool - a resolving ability's "X" (an ETB's damage/tokens/life/draw, a beginning-
of-combat pump, a reveal-until count, a search-for-up-to count), a spell's own
CR 601.2f self cost reduction, and a characteristic-defining ability
(Squawkroaster's power) - so this module is the one place the count and its
qualifier phrase ("permanents" / "other permanents" / "legendary permanents" /
a card type / a subtype) are read, reused by:

- `machines/effects.py`'s `count_expression` - the resolution-time amount
  every "where X is the number of colors among `<qualifier>` you control"
  clause needs (Aurora Awakener, Explosive Prodigy, Glister Bairn, Kithkeeper,
  Luminollusk, Prismabasher, Prismatic Undercurrents, Sanar, Shimmercreep,
  Shinestriker).
- `machines/layers.py`'s `_COLOR_COUNT_CDA_RE` - Squawkroaster's own sublayer
  7a CDA (CR 604.3a), which reuses `_colors_among_count_factory` (already
  built for Sisay's/Earthen Ally's sublayer 7c pump) for the identical
  qualifier reading.
- `models/game.py`'s `cost_reduction_for` - Rime Chill's and Wildvine
  Pummeler's own CR 601.2f self reduction, "This spell costs `{N}` less to
  cast for each color among `<qualifier>` you control."

The qualifier grammar mirrors `machines/layers.py`'s own
`_SELF_PUMP_PER_COLOR_AMONG_RE`/`_colors_among_count_factory` exactly (an
optional "other", an optional "legendary", then "permanents" or a card type
or a subtype) so the same phrase reads identically wherever it is printed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..models.card import Color
    from ..models.card_state import CardState
    from ..models.game import Game


@dataclass(frozen=True)
class ColorsAmongQualifier:
    """What group of permanents a "colors among `<qualifier>` you control"
    phrase counts: every permanent a player controls, filtered by
    `card_type`/`subtype`/`legendary` (all `None`/`False` is every permanent),
    with `excludes_self` for "other" (CR 608.2h's own object, when the caller
    has one to exclude)."""

    card_type: object | None = None
    subtype: str | None = None
    legendary: bool = False
    excludes_self: bool = False
    #: "monocolored permanents" (Tarnation Vista): only objects of exactly one color count.
    monocolored: bool = False
    #: "the exiled cards used to craft this creature" (Sunbird Effigy; CR 702.167c): the
    #: cards recorded on the source as it was crafted, not permanents anyone controls.
    crafted: bool = False


#: `ManaAbility.each_color_among`'s qualifier for CR 702.167c's craft materials.
CRAFT_MATERIALS_QUALIFIER = "exiled cards used to craft this"


def parse_colors_among_qualifier(phrase: str) -> ColorsAmongQualifier | None:
    """ "permanents" / "other permanents" / "legendary permanents" /
    "creatures" / "Allies" - the group named between "colors among" and "you
    control". `None` when a word of it is not one of those shapes.

    Reuses `machines/effects.py`'s own card-type/subtype vocabulary
    (`_singular_card_type`, `_singular_subtype_for_count_expression`) so a
    qualifier this reads is exactly one `count_expression`'s "the number of
    `<qualifier>` you control" would also read - the same vocabulary, asked
    about the colors among the group instead of the group's own size.
    """
    from .effects import _singular_card_type, _singular_subtype_for_count_expression

    if phrase.strip().lower() == CRAFT_MATERIALS_QUALIFIER:
        return ColorsAmongQualifier(crafted=True)
    words = phrase.strip().lower().split()
    if not words:
        return None
    excludes_self = words[0] == "other"
    if excludes_self:
        words = words[1:]
    legendary = False
    monocolored = False
    if len(words) == 2 and words[0] == "legendary":
        legendary = True
        words = words[1:]
    elif len(words) == 2 and words[0] == "monocolored":
        monocolored = True
        words = words[1:]
    if len(words) != 1:
        return None
    noun = words[0]
    if noun == "permanents":
        return ColorsAmongQualifier(
            legendary=legendary, excludes_self=excludes_self, monocolored=monocolored
        )
    card_type = _singular_card_type(noun)
    if card_type is not None:
        return ColorsAmongQualifier(
            card_type=card_type, legendary=legendary, excludes_self=excludes_self
        )
    subtype = _singular_subtype_for_count_expression(noun)
    if subtype is None:
        return None
    return ColorsAmongQualifier(subtype=subtype, legendary=legendary, excludes_self=excludes_self)


def colors_among(
    game: Game,
    controller: str,
    qualifier: ColorsAmongQualifier,
    *,
    source: CardState | None = None,
) -> frozenset[Color]:
    """CR 105.1's colors among the permanents `controller` controls that
    match `qualifier`, read off the computed board (CR 613.5) - a creature
    that only became one through a continuous effect still counts, and a
    color a permanent only gained the same way counts too. CR 105.2c: "A
    colorless object has no color" - a colorless permanent contributes
    nothing to the set.
    """
    from ..models.card import Color, Supertype

    board = game.computed_board()
    colors: set[Color] = set()
    if qualifier.crafted:
        # CR 702.167c: the exiled cards used to craft the source, each colour once (CR 105.1).
        for card_id in () if source is None else source.crafted_with:
            used = game.find_by_id(card_id)
            if used is not None:
                colors.update(color for color in used.colors if color is not Color.COLORLESS)
        return frozenset(colors)
    for permanent in game.battlefield:
        chars = board.of(permanent)
        if chars.controller != controller:
            continue
        if qualifier.excludes_self and source is not None and permanent.id == source.id:
            continue
        if qualifier.card_type is not None and qualifier.card_type not in chars.types:
            continue
        if qualifier.subtype is not None and not any(
            word.lower() == qualifier.subtype for word in chars.subtypes
        ):
            continue
        if qualifier.legendary and Supertype.LEGENDARY not in chars.supertypes:
            continue
        own = {color for color in chars.colors if color is not Color.COLORLESS}
        if qualifier.monocolored and len(own) != 1:
            continue
        colors.update(own)
    return frozenset(colors)


def count_colors_among(
    game: Game,
    controller: str,
    qualifier: ColorsAmongQualifier,
    *,
    source: CardState | None = None,
) -> int:
    """How many colors `colors_among` finds."""
    return len(colors_among(game, controller, qualifier, source=source))


#: "the number of colors among `<qualifier>` you control" - every Vivid
#: card's own amount (Aurora Awakener through Shinestriker; Sanar's own
#: "reveal ... until you reveal X nonland cards" prints the identical
#: phrase).
COLORS_AMONG_AMOUNT_RE = re.compile(
    r"^(?:the )?number of colou?rs among (?P<qualifier>[a-z]+(?: [a-z]+)?) you control$",
    re.IGNORECASE,
)


def colors_among_count_expression(phrase: str):  # noqa: ANN201 - Callable[[Game, str], int] | None
    """`machines/effects.py`'s `count_expression` shape: `(game, controller)
    -> int`, or `None` when `phrase` is not `COLORS_AMONG_AMOUNT_RE`'s shape
    or its qualifier is unreadable. `source` (an "other" exclusion) is always
    `None` on this path - no pool card prints "colors among other permanents"
    - `costs_less_per_color_among_reduction`'s own caller and a future
    resolution-time caller that does hold the source can call
    `count_colors_among` directly instead.
    """
    match = COLORS_AMONG_AMOUNT_RE.fullmatch(phrase.strip().rstrip("."))
    if match is None:
        return None
    qualifier = parse_colors_among_qualifier(match.group("qualifier"))
    if qualifier is None:
        return None

    def read(game: Game, controller: str) -> int:
        return count_colors_among(game, controller, qualifier)

    return read


#: "This spell costs `{N}` less to cast for each color among `<qualifier>`
#: you control." - Rime Chill's and Wildvine Pummeler's own CR 601.2f self
#: reduction, read by `models/game.py`'s `cost_reduction_for` the same way
#: every other self-reduction shape there is: matched against the spell's own
#: printed text, evaluated fresh at the moment the cost is determined.
COSTS_LESS_PER_COLOR_AMONG_RE = re.compile(
    r"costs \{(?P<amount>\d+)\} less to cast for each colou?r among "
    r"(?P<qualifier>[a-z]+(?: [a-z]+)?) you control",
    re.IGNORECASE,
)


def costs_less_per_color_among_reduction(text: str, game: Game, controller: str) -> int:
    """The generic-mana amount `COSTS_LESS_PER_COLOR_AMONG_RE` takes off a
    spell's own cost right now (CR 601.2f), or 0 when `text` does not carry
    the shape at all or its qualifier is one this cannot read - `cost_
    reduction_for` adds this to whatever its other shapes find, never
    replacing them (CR 601.2f: "Some effects may increase or reduce the cost
    to pay", plural).
    """
    match = COSTS_LESS_PER_COLOR_AMONG_RE.search(text)
    if match is None:
        return 0
    qualifier = parse_colors_among_qualifier(match.group("qualifier"))
    if qualifier is None:
        return 0
    return int(match.group("amount")) * count_colors_among(game, controller, qualifier)
