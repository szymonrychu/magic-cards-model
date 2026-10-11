"""Mana costs and the mana pool.

Every mana symbol of CR 107.4 that can appear in a printed mana cost is
modelled here:

| Symbol   | CR      | Paid with                                    |
|----------|---------|----------------------------------------------|
| `{3}`    | 107.4b  | any three mana                               |
| `{C}`    | 107.4c  | one colourless mana, and nothing else        |
| `{W}`    | 107.4a  | one mana of that colour                      |
| `{X}`    | 107.3, 107.4b | resolved to a number before the cost is paid |
| `{W/U}`  | 107.4e  | one mana of either half                      |
| `{2/W}`  | 107.4e  | two generic mana, or one white               |
| `{W/P}`  | 107.4f  | one white mana, or 2 life                    |
| `{G/U/P}`| 107.4f  | green, blue, or 2 life                       |
| `{S}`    | 107.4h  | one mana of any type from a snow source      |

A symbol that can be paid in more than one way (CR 118.13) turns paying into a
search: `ManaPool.payment_for` picks a way, or proves there is none. The choice
belongs to the payer (CR 118.13a), so it can be pinned with `choices=`.
"""

import re
from collections import Counter
from collections.abc import Hashable, Iterable, Sequence
from enum import StrEnum
from itertools import combinations_with_replacement, product
from typing import Any, Protocol

from pydantic import ConfigDict, Field, model_validator

from ..serialization import SortedFrozenSet
from ..snapshot import EngineModel, announce_mutation, mutation_landed
from .card import Card, Color, Layout, Supertype, Type
from .zone import Zone


class HasCharacteristics(Protocol):
    """The four characteristics CR 106.6's restrictions are written against,
    plus a name for the refusal message.

    A structural type, because the two things that answer these questions are
    not related by inheritance and must not be: `CardState` is the spell
    (right for a spell on the stack, which `Game.computed_board` does not
    cover - its face and its changeling CDA included, CR 604.3), and
    `machines/layers.Characteristics` is the layer-computed answer (CR 613.5,
    right for a permanent). Both print `name`, `types`, `subtypes`,
    `supertypes` and `colors` with the same meanings, so `ManaSpend._of` needs
    no branch.

    `machines` may not be imported from `models` (the dependency runs the other
    way), which is the other reason this is a Protocol and not a union.
    """

    @property
    def name(self) -> str: ...

    @property
    def types(self) -> tuple[Type, ...]: ...

    @property
    def subtypes(self) -> tuple[str, ...]: ...

    @property
    def supertypes(self) -> tuple[Supertype, ...]: ...

    @property
    def colors(self) -> tuple[Color, ...] | None: ...


_SYMBOL = re.compile(r"\{([^}]+)\}")

#: Scryfall separates a split card's two halves with this (CR 709.4b).
_SPLIT = " // "
_COLOR_SYMBOLS = frozenset(color.value for color in Color)

#: CR 107.4f: a Phyrexian symbol is paid with its colour or with 2 life.
PHYREXIAN_LIFE = 2


class SymbolKind(StrEnum):
    """The shapes a mana symbol in a printed cost can take (CR 107.4)."""

    GENERIC = "generic"
    VARIABLE = "variable"
    COLORED = "colored"
    HYBRID = "hybrid"
    MONOCOLORED_HYBRID = "monocolored_hybrid"
    PHYREXIAN = "phyrexian"
    SNOW = "snow"


class PaymentOption(EngineModel):
    """One way a single symbol may be paid.

    Exactly one of the three resources is used: `generic` mana, one mana of
    `color` (with `snow` demanding it came from a snow source), or `life`.
    """

    model_config = ConfigDict(frozen=True)

    generic: int = 0
    color: Color | None = None
    snow: bool = False
    life: int = 0

    def __str__(self) -> str:
        if self.life:
            return f"{self.life} life"
        if self.snow:
            return "one snow mana"
        if self.color is not None:
            return f"{{{self.color.value}}}"
        return f"{{{self.generic}}}"


class ManaSymbol(EngineModel):
    """One symbol of a mana cost, and the ways it can be paid."""

    model_config = ConfigDict(frozen=True)

    kind: SymbolKind
    amount: int = 0
    colors: tuple[Color, ...] = ()

    # -- building ----------------------------------------------------------

    @classmethod
    def parse(cls, symbol: str) -> "ManaSymbol":
        """Parse the text inside one pair of braces, such as `W/U` or `2`."""
        if symbol.isdigit():
            return cls(kind=SymbolKind.GENERIC, amount=int(symbol))
        if symbol == "X":
            return cls(kind=SymbolKind.VARIABLE)
        if symbol == "S":
            return cls(kind=SymbolKind.SNOW)
        if symbol in _COLOR_SYMBOLS:
            return cls(kind=SymbolKind.COLORED, colors=(Color(symbol),))

        parts = symbol.split("/")
        if len(parts) >= 2:
            if parts[-1] == "P" and all(part in _COLOR_SYMBOLS for part in parts[:-1]):
                # {W/P}, and the hybrid Phyrexian {G/U/P}.
                return cls(
                    kind=SymbolKind.PHYREXIAN,
                    colors=tuple(Color(part) for part in parts[:-1]),
                )
            if len(parts) == 2 and parts[0].isdigit() and parts[1] in _COLOR_SYMBOLS:
                # {2/W}: two generic, or one white.
                return cls(
                    kind=SymbolKind.MONOCOLORED_HYBRID,
                    amount=int(parts[0]),
                    colors=(Color(parts[1]),),
                )
            if len(parts) == 2 and all(part in _COLOR_SYMBOLS for part in parts):
                # {W/U}, and the colourless hybrids such as {C/W}.
                return cls(
                    kind=SymbolKind.HYBRID,
                    colors=tuple(Color(part) for part in parts),
                )

        raise ValueError(f"unsupported mana symbol: {{{symbol}}}")

    # -- reading -----------------------------------------------------------

    @property
    def mana_value(self) -> int:
        """This symbol's contribution to mana value (CR 202.3, 202.3f, 202.3g)."""
        match self.kind:
            case SymbolKind.GENERIC:
                return self.amount
            case SymbolKind.VARIABLE:
                # CR 202.3e: X is treated as 0 while the object is not on the
                # stack, and as the number chosen for it while it is.
                return 0
            case SymbolKind.MONOCOLORED_HYBRID:
                # CR 202.3f: the largest component of a hybrid symbol.
                return max(self.amount, 1)
            case _:
                return 1

    @property
    def options(self) -> tuple[PaymentOption, ...]:
        """Every way this symbol may be paid, cheapest first."""
        match self.kind:
            case SymbolKind.GENERIC:
                return (PaymentOption(generic=self.amount),)
            case SymbolKind.COLORED:
                return (PaymentOption(color=self.colors[0]),)
            case SymbolKind.SNOW:
                return (PaymentOption(snow=True),)
            case SymbolKind.HYBRID:
                return tuple(PaymentOption(color=color) for color in self.colors)
            case SymbolKind.MONOCOLORED_HYBRID:
                return (
                    PaymentOption(color=self.colors[0]),
                    PaymentOption(generic=self.amount),
                )
            case SymbolKind.PHYREXIAN:
                return tuple(PaymentOption(color=color) for color in self.colors) + (
                    PaymentOption(life=PHYREXIAN_LIFE),
                )
            case _:
                raise ValueError(f"{self} cannot be paid; resolve it first")

    def __str__(self) -> str:
        match self.kind:
            case SymbolKind.GENERIC:
                return f"{{{self.amount}}}"
            case SymbolKind.VARIABLE:
                return "{X}"
            case SymbolKind.SNOW:
                return "{S}"
            case SymbolKind.COLORED:
                return f"{{{self.colors[0].value}}}"
            case SymbolKind.HYBRID:
                return "{" + "/".join(color.value for color in self.colors) + "}"
            case SymbolKind.MONOCOLORED_HYBRID:
                return f"{{{self.amount}/{self.colors[0].value}}}"
            case SymbolKind.PHYREXIAN:
                return "{" + "/".join(color.value for color in self.colors) + "/P}"
        raise AssertionError(f"unhandled symbol kind {self.kind}")  # pragma: no cover


def _symbols_from_parts(
    generic: int, colored: dict[Color, int] | None, x_count: int
) -> list[ManaSymbol]:
    """Symbols for the plain generic/coloured/X shape, in printed order."""
    symbols = [ManaSymbol(kind=SymbolKind.VARIABLE)] * x_count
    if generic:
        symbols.append(ManaSymbol(kind=SymbolKind.GENERIC, amount=generic))
    for color, count in (colored or {}).items():
        symbols.extend([ManaSymbol(kind=SymbolKind.COLORED, colors=(Color(color),))] * count)
    return symbols


class ManaCost(EngineModel):
    """A mana cost as its ordered list of symbols.

    Order is kept so `str(ManaCost.parse(s)) == s` for a real printed cost;
    Tamiyo, Compleated Sage is `{2}{G}{G/U/P}{U}`, which no bucketing into
    generic-then-colours could reproduce.

    The old `generic=`/`colored=`/`x_count=` constructor still works and is
    still readable as properties, so `{2}{U}{U}` is generic 2, colored {U: 2}.
    """

    symbols: tuple[ManaSymbol, ...] = ()

    split_after: int | None = None
    """Where a split card's two halves meet, as an index into `symbols`.

    CR 709.4b: the mana cost of a split card is the combined mana costs of its
    two halves, and its mana value comes from that combined cost - which is
    what this models. Scryfall writes it with a ` // ` between the halves, so
    the index is kept to put the separator back and round-trip the printed
    string. `None` for every ordinary card.

    While a split card is on the stack only the half being cast exists
    (CR 709.3b), so a caster should parse that half's cost, not this one.
    """

    @model_validator(mode="before")
    @classmethod
    def _accept_legacy_parts(cls, data: object) -> object:
        """Allow `ManaCost(generic=2, colored={Color.BLUE: 2})`."""
        if not isinstance(data, dict) or "symbols" in data:
            return data
        legacy = {"generic", "colored", "x_count"}
        if not legacy & set(data):
            return data
        rest = {key: value for key, value in data.items() if key not in legacy}
        return rest | {
            "symbols": _symbols_from_parts(
                data.get("generic", 0), data.get("colored"), data.get("x_count", 0)
            )
        }

    @classmethod
    def parse(cls, mana_cost: str) -> "ManaCost":
        """Parse a Scryfall `mana_cost` string such as `{3}{W}{W}` or `{2/W}`.

        A split card arrives as both halves either side of a ` // ` and is read
        as their combined cost (CR 709.4b).
        """
        text = mana_cost or ""
        if _SPLIT in text:
            left, _, right = text.partition(_SPLIT)
            first = tuple(ManaSymbol.parse(s) for s in _SYMBOL.findall(left))
            second = tuple(ManaSymbol.parse(s) for s in _SYMBOL.findall(right))
            return cls(symbols=first + second, split_after=len(first))
        return cls(symbols=tuple(ManaSymbol.parse(s) for s in _SYMBOL.findall(text)))

    @classmethod
    def try_parse(cls, mana_cost: str) -> "ManaCost | None":
        """`parse` for printed text a parser captured, or `None` when any
        braced symbol in it is not a mana symbol.

        `parse` is a primitive and refuses an unknown symbol with a
        `ValueError`. Oracle text braces symbols that are not mana at all -
        CR 107.14's energy `{E}`, CR 107.5's tap `{T}`, CR 107.6's untap `{Q}`
        - so a regex that captures a run of braced symbols out of a sentence
        must not hand it to `parse` and let that raise into a live game: it
        asks here and reads the text, or declines so its clause fails closed.
        """
        try:
            return cls.parse(mana_cost)
        except ValueError:
            return None

    @classmethod
    def for_card(cls, card: Card) -> "ManaCost":
        """The mana cost this card has in a zone other than the stack.

        Scryfall writes any two-part card's cost with a ` // ` between the
        halves, but only a **split** card actually costs both: CR 709.4b makes
        its mana cost the two combined. An adventurer card has only its normal
        characteristics outside the stack (CR 715.4), and a double-faced card
        only those of its front face (CR 712.8a) - so for those the second half
        is not part of the cost at all and is dropped.

        While a two-part card is on the stack only the half being cast exists
        (CR 709.3b, CR 715.3b), so a caster should parse that half instead.
        """
        printed = card.mana_cost or ""
        if _SPLIT not in printed or card.layout is Layout.SPLIT:
            return cls.parse(printed)
        front, _, _ = printed.partition(_SPLIT)
        return cls.parse(front)

    # -- the plain parts, for the costs that only have them ----------------

    @property
    def generic(self) -> int:
        """Generic mana in the cost. A `{2/W}` is not counted: it may be neither."""
        return sum(s.amount for s in self.symbols if s.kind is SymbolKind.GENERIC)

    @property
    def colored(self) -> dict[Color, int]:
        """Mana of a fixed colour the cost demands. Hybrids are not counted."""
        counts: Counter[Color] = Counter()
        for symbol in self.symbols:
            if symbol.kind is SymbolKind.COLORED:
                counts[symbol.colors[0]] += 1
        return dict(counts)

    @property
    def x_count(self) -> int:
        return sum(1 for s in self.symbols if s.kind is SymbolKind.VARIABLE)

    @property
    def converted(self) -> int:
        """Mana value (CR 202.3). X counts as zero off the stack (CR 202.3e)."""
        return sum(symbol.mana_value for symbol in self.symbols)

    @property
    def is_payable_in_multiple_ways(self) -> bool:
        """CR 118.13: true if some symbol offers the payer a choice."""
        return any(len(symbol.options) > 1 for symbol in self.symbols)

    def with_x(self, value: int) -> "ManaCost":
        """This cost with X resolved to `value`, folded into the generic part."""
        resolved: list[ManaSymbol] = []
        extra = 0
        for symbol in self.symbols:
            if symbol.kind is SymbolKind.VARIABLE:
                extra += value
            else:
                resolved.append(symbol)
        if extra:
            # Fold it into the generic symbol the cost already has, if any, so
            # {2}{X}{R} with X=1 is {3}{R} rather than {1}{2}{R}.
            for index, symbol in enumerate(resolved):
                if symbol.kind is SymbolKind.GENERIC:
                    resolved[index] = ManaSymbol(
                        kind=SymbolKind.GENERIC, amount=symbol.amount + extra
                    )
                    break
            else:
                resolved.insert(0, ManaSymbol(kind=SymbolKind.GENERIC, amount=extra))
        return ManaCost(symbols=tuple(resolved))

    # -- combining two costs, symbol for symbol ----------------------------

    def plus(self, other: "ManaCost") -> "ManaCost":
        """This cost with `other` added to it (CR 601.2f, 118.8a).

        Generic mana merges into the generic symbol this cost already has, so
        `{1}{G}` plus `{2}{G}` is `{3}{G}{G}` and not `{1}{2}{G}{G}`. Every
        other symbol is appended exactly as it was printed, which is what stops
        a hybrid, Phyrexian, or snow symbol being dropped on the way.
        """
        extra = other.generic
        symbols = list(self.symbols)
        if extra:
            symbols = _fold_generic(symbols, extra)
        symbols.extend(s for s in other.symbols if s.kind is not SymbolKind.GENERIC)
        return ManaCost(symbols=tuple(symbols))

    def minus(self, other: "ManaCost") -> "ManaCost":
        """This cost reduced by `other`, following CR 118.7a-d, 118.7f-g.

        118.7a: a reduction of generic mana touches only the generic component,
        so `{1}` off `{G}{G}` leaves `{G}{G}` alone. 118.7b: a reduction of a
        type the cost does not require reduces generic instead. 118.7c-d: a
        reduction beyond what the cost requires of that type spills over into
        generic. 118.7f: a reduction by a Phyrexian symbol reduces by one mana
        of that symbol's colour. 118.7g: a reduction by snow symbols reduces
        that much generic mana.

        A symbol the cost merely *contains* is never a component of a type:
        `{G/W}` does not require green (CR 107.4e leaves the choice until the
        cost is paid), so a `{G}` reduction against Kitchen Finks takes generic
        under 118.7b rather than eating half a hybrid symbol.

        Reducing *by* a hybrid symbol is refused: CR 118.7e has the payer
        choose a half when the reduction is applied, and this engine has nobody
        to ask.
        """
        generic_reduction, colored_reduction = _reduction_parts(other)

        kept: list[ManaSymbol] = []
        for symbol in self.symbols:
            color = symbol.colors[0] if symbol.kind is SymbolKind.COLORED else None
            if color is not None and colored_reduction[color] > 0:
                colored_reduction[color] -= 1
                continue
            kept.append(symbol)
        generic_reduction += sum(colored_reduction.values())

        reduced: list[ManaSymbol] = []
        for symbol in kept:
            if symbol.kind is not SymbolKind.GENERIC or not generic_reduction:
                reduced.append(symbol)
                continue
            left = symbol.amount - min(symbol.amount, generic_reduction)
            generic_reduction -= symbol.amount - left
            if left:
                reduced.append(ManaSymbol(kind=SymbolKind.GENERIC, amount=left))
        return ManaCost(symbols=tuple(reduced))

    def __str__(self) -> str:
        if self.split_after is None:
            return "".join(str(symbol) for symbol in self.symbols)
        left = "".join(str(s) for s in self.symbols[: self.split_after])
        right = "".join(str(s) for s in self.symbols[self.split_after :])
        return f"{left}{_SPLIT}{right}"


def _fold_generic(symbols: list[ManaSymbol], amount: int) -> list[ManaSymbol]:
    """Add `amount` generic mana to these symbols, keeping printed order.

    It joins the generic symbol already there if there is one; otherwise it is
    inserted where a printed cost puts it, after any {X} and before the pips.
    """
    folded = list(symbols)
    for index, symbol in enumerate(folded):
        if symbol.kind is SymbolKind.GENERIC:
            folded[index] = ManaSymbol(kind=SymbolKind.GENERIC, amount=symbol.amount + amount)
            return folded

    at = 0
    while at < len(folded) and folded[at].kind is SymbolKind.VARIABLE:
        at += 1
    folded.insert(at, ManaSymbol(kind=SymbolKind.GENERIC, amount=amount))
    return folded


def _reduction_parts(by: ManaCost) -> tuple[int, Counter[Color]]:
    """Split a cost reduction into generic and per-type amounts (CR 118.7).

    {X} in a reduction is ignored: there is nothing to resolve it against.
    """
    generic = 0
    colored: Counter[Color] = Counter()
    for symbol in by.symbols:
        match symbol.kind:
            case SymbolKind.GENERIC:
                generic += symbol.amount
            case SymbolKind.VARIABLE:
                continue
            case SymbolKind.COLORED:
                # CR 118.7b-d treat colourless {C} the same way as a colour.
                colored[symbol.colors[0]] += 1
            case SymbolKind.SNOW:
                # CR 118.7g: a snow symbol reduces generic mana.
                generic += 1
            case SymbolKind.PHYREXIAN if len(symbol.colors) == 1:
                # CR 118.7f: one mana of that symbol's colour.
                colored[symbol.colors[0]] += 1
            case _:
                raise ValueError(
                    f"cannot reduce a cost by {symbol}: CR 118.7e has the payer choose "
                    "a half of a hybrid symbol, and this engine has nobody to ask"
                )
    return generic, colored


# --------------------------------------------------------------------------
# Spend restrictions (CR 106.6)
# --------------------------------------------------------------------------
#
# CR 106.6, looked up this session: "Some spells or abilities that produce mana
# restrict how that mana can be spent, have an additional effect that affects
# the spell or ability that mana is spent on, or create a delayed triggered
# ability..." Only the first of those three - the restriction on *how the mana
# can be spent* - is modelled here.
#
# Two consequences of that wording decide the whole design:
#
# - The restriction is on the **mana**, not on its source. The mana ability has
#   long since resolved (CR 605.3b) by the time the mana is spent, so the tag
#   travels with the mana in the pool and outlives its source leaving the
#   battlefield. `ManaPool.restricted` is where it lives.
# - It restricts what the mana **can** pay for, not merely what the player is
#   advised to pay with it, so a payment that would spend it on anything else
#   is not a legal payment at all (CR 118.3a: "Paying mana is done by removing
#   the indicated mana from a player's mana pool") and `payment_for` refuses
#   rather than deprioritising.
#
# The tag dies with the mana: CR 703.4q and CR 500.5, both looked up this
# session - "as each step or phase ends, any unspent mana left in a player's
# mana pool empties" - so `ManaPool.empty` clears `restricted` along with
# `floating`, and there is no separate lifetime to get wrong.


class SpendPurpose(StrEnum):
    """What mana is being spent on, as far as a CR 106.6 restriction cares.

    Every printed restriction in this pool distinguishes casting a spell from
    activating an ability - Eldrazi Temple's "cast colorless Eldrazi spells or
    activate abilities of colorless Eldrazi" prints both halves side by side -
    so this is the axis a restriction is checked on first.
    """

    CAST_SPELL = "cast_spell"
    ACTIVATE_ABILITY = "activate_ability"
    #: Snowfall's "Spend this mana only to pay cumulative upkeep costs"
    #: (CR 702.24a): neither a cast nor an activation. The one spend that
    #: carries it is `machines/keywords._cumulative_upkeep_effect`'s payment
    #: (`ManaSpend.paying_cumulative_upkeep`).
    PAY_CUMULATIVE_UPKEEP = "pay_cumulative_upkeep"


_CANT_SPEND_MANA_RE = re.compile(r"^You can't spend mana to cast this spell\.$", re.MULTILINE)


def reads_cant_spend_mana_line(oracle_text: str) -> bool:
    """Whether a card's text carries "You can't spend mana to cast this spell."
    - the line `ManaSpend.casting` turns into `no_mana`."""
    return _CANT_SPEND_MANA_RE.search(oracle_text) is not None


_SPEND_ONLY_FROM_RE = re.compile(
    r"^Spend only mana produced by (?P<what>basic lands|creatures) to cast this spell\.$",
    re.MULTILINE,
)
_SPEND_ONLY_FROM = {"basic lands": "basic_land", "creatures": "creature"}


def spend_only_from(oracle_text: str) -> str | None:
    """Which source kind a card's own "Spend only mana produced by <kind> to
    cast this spell." limits its cost to (`ManaSpend.only_from`), or `None`."""
    match = _SPEND_ONLY_FROM_RE.search(oracle_text)
    return None if match is None else _SPEND_ONLY_FROM[match.group("what")]


class ManaSpend(EngineModel):
    """The object mana is about to be spent on, reduced to what a restriction
    can ask about: whether it is being cast or activated, and the
    characteristics of the spell (for a cast) or of the ability's source (for
    an activation).

    "Abilities of creature sources" is a question about the **source**, not
    about a spell - Shang-Chi's mana pays to activate an ability of a creature
    already on the battlefield and does not pay for a creature *spell* - so the
    two are built by two different constructors and never conflated.
    """

    model_config = ConfigDict(frozen=True)

    purpose: SpendPurpose
    name: str = ""
    """Whose cost this is, for the message when the mana is refused."""

    types: SortedFrozenSet[Type] = frozenset()
    subtypes: SortedFrozenSet[str] = frozenset()
    """Lowercased, since a restriction's chosen creature type is matched
    case-insensitively against a printed subtype."""
    supertypes: SortedFrozenSet[Supertype] = frozenset()
    colorless: bool = False
    zone: Zone | None = None
    """CR 601.2a's "moves that card ... from where it is to the stack": the
    zone the spell is being cast **from**, which is a question about the cast
    and not about the card - the same printing cast from the hand and from
    exile is the same object with two different answers here.

    `None` means the caller could not say, and a clause that names a zone
    refuses it for the same reason `ManaRestriction.allows(None)` refuses an
    unknown spend: the engine cannot show the restriction was honoured. It is
    always `None` for an activation, where no card moves anywhere.
    """
    any_color: bool = False
    """CR 609.4b: the payer "may spend mana as though it were mana of any
    color" on this cost - Agatha's Soul Cauldron's "... to activate abilities
    of creatures you control", Drana and Linvala's "... to activate those
    abilities". Set by the caller that knows the permission applies
    (`Game.spends_mana_as_any_color`); the flag "affects only how the player
    may pay a cost. It doesn't change that cost, and it doesn't change what
    mana was actually spent to pay that cost", which is why it widens only
    the coloured demands `_demand_list` builds and nothing about the cost or
    the mana itself. A `{C}` symbol still wants colorless mana (colorless is
    not a color, CR 105.1) and `{S}` still wants snow mana."""
    snow_any_color: bool = False
    """CR 609.4b narrowed to snow sources: "you may spend mana from snow
    sources as though it were mana of any color to cast those spells" (Draugr
    Necromancer). Only mana produced by a snow source is widened; every other
    mana still pays only the color it is."""

    treasure_only: bool = False
    """Security Rhox's "Spend only mana produced by Treasures to cast it this
    way." (CR 106.6): only mana a Treasure produced (`ManaPool.treasure`) may
    pay this cost. A restriction on the *cost* rather than on the mana, so it
    lives on the spend, not in `ManaRestriction`; floating mana from any other
    source is simply not available to this payment."""

    only_from: str | None = None
    """"Spend only mana produced by basic lands [creatures] to cast this spell."
    (Imperiosaur, Myr Superion; CR 106.6 / CR 601.2h): `"basic_land"` or
    `"creature"`. A restriction on the *cost*, like `treasure_only`: only the
    part of the pool that source kind made (`ManaPool.basic_land`,
    `ManaPool.creature`) is available to this payment, and a tap of any other
    source is refused."""
    any_type: bool = False
    """CR 609.4b's "mana of any type can be spent" (Vizier of the Menagerie):
    `any_color`'s wider twin - a `{C}` demand accepts coloured mana too."""

    mana_value: float | None = None
    """CR 202.3's mana value of the spell being cast - X counted as the number
    chosen for it (CR 202.3e: the spell is on the stack by the time its cost
    is paid). `None` for an activation, which has no spell to ask about."""
    x_in_cost: bool = False
    """Whether the spell being cast has an {X} in its mana cost."""
    no_mana: bool = False
    """The spell says "You can't spend mana to cast this spell." (Hogaak,
    Arisen Necropolis): no mana of any kind may pay for it, only the objects
    convoke and delve tap and exile (CR 601.2h, CR 702.51b, CR 702.66b)."""
    class_level: bool = False
    """Whether the ability being activated is a Class's level bar - CR 716.2a's
    "[Cost]: Level N", an activated ability whose resolution is how a Class
    gains a level. Sorcerer Class's "Spend this mana only to ... gain a Class
    level" asks exactly this."""

    @classmethod
    def _of(
        cls,
        purpose: SpendPurpose,
        card: "HasCharacteristics",
        zone: Zone | None,
        *,
        any_color: bool = False,
    ) -> "ManaSpend":
        return cls(
            purpose=purpose,
            name=card.name,
            types=frozenset(card.types),
            subtypes=frozenset(subtype.lower() for subtype in card.subtypes),
            supertypes=frozenset(card.supertypes),
            colorless=not card.colors,
            zone=zone,
            any_color=any_color,
        )

    @classmethod
    def casting(
        cls,
        card: "HasCharacteristics",
        *,
        zone: Zone | None,
        x_value: int = 0,
        snow_any_color: bool = False,
    ) -> "ManaSpend":
        """Mana spent to cast `card` as a spell, out of `zone`.

        A spell is on the stack, which `Game.computed_board` does not cover, so
        the caller gives the spell's own `CardState`: the face being cast
        (CR 709.3b, CR 715.3b) and its characteristic-defining abilities -
        a changeling spell is a Dragon spell (CR 702.73a, CR 604.3).

        `zone` is keyword-only and has **no default** on purpose. CR 601.2a
        moves the card to the stack as the very first step of the
        announcement, so by the time a cost is being paid `spell.zone` is
        always `Zone.STACK` and the origin has to be carried from before the
        move (`Casting.origin_zone`, `CardState.zone` at the moment
        `legal_actions` enumerates the cast). A default here would be that
        answer guessed rather than carried, and "usually the hand"
        (CR 701.18a's own hedge) is exactly the guess Interdimensional Web
        Watch's "cast spells from exile" is about.
        """
        spend = cls._of(SpendPurpose.CAST_SPELL, card, zone)
        printed = getattr(card, "mana_cost", None)
        x_count = ManaCost.parse(printed).x_count if printed else 0
        base = getattr(card, "mana_value", None)
        if base is None:
            base = getattr(card, "cmc", None) or 0.0
        return spend.model_copy(
            update={
                "mana_value": float(base) + x_count * x_value,
                "x_in_cost": x_count > 0,
                "snow_any_color": snow_any_color,
                "no_mana": reads_cant_spend_mana_line(getattr(card, "oracle_text", "") or ""),
                "only_from": spend_only_from(getattr(card, "oracle_text", "") or ""),
            }
        )

    @classmethod
    def activating(
        cls, card: "HasCharacteristics", *, any_color: bool = False, class_level: bool = False
    ) -> "ManaSpend":
        """Mana spent to activate an ability whose source is `card`.

        Unlike `casting`, the source of an activated ability is normally a
        permanent, and CR 613.5 makes its card types the layer-computed ones -
        so a caller with a `Game` in hand passes `Game.characteristics_of(...)`
        rather than the printing, and a land animated into a creature counts as
        a creature source for CR 106.6's "spend this mana only to activate
        abilities of creature sources". `Characteristics` (machines/layers.py)
        prints the same four names this reads, so no branch is needed here -
        only the type had to stop saying `Card`.

        `any_color` is CR 609.4b's permission and `class_level` says the
        ability is a CR 716.2a level bar, see each field's own docstring.
        """
        spend = cls._of(SpendPurpose.ACTIVATE_ABILITY, card, None, any_color=any_color)
        return spend.model_copy(update={"class_level": True}) if class_level else spend

    @classmethod
    def paying_cumulative_upkeep(cls, card: "HasCharacteristics") -> "ManaSpend":
        """Mana spent to pay `card`'s cumulative upkeep (CR 702.24a) - the
        resolving trigger's "you may pay [cost] for each age counter on it",
        which is neither a cast nor an activation."""
        return cls._of(SpendPurpose.PAY_CUMULATIVE_UPKEEP, card, None)


class SpendClause(EngineModel):
    """One thing a CR 106.6 restriction permits its mana to be spent on.

    A restriction can permit more than one - Eldrazi Temple's is two clauses
    joined by "or" - so a restriction holds a tuple of these and the mana is
    spendable if **any** of them accepts.

    Every field is a further narrowing and an empty one asks nothing, except
    that `purpose` is always required: a clause with no purpose could not be
    read off a printed sentence in the first place.
    """

    model_config = ConfigDict(frozen=True)

    purpose: SpendPurpose
    types: SortedFrozenSet[Type] = frozenset()
    """The card types the sentence printed - "creature spell" style. Whether
    the object needs one of them or all of them is `joined`'s answer."""
    excluded_types: SortedFrozenSet[Type] = frozenset()
    """CR 109.2's negation of a printed card type - Chandra, Chill of
    Compliance's own "a noncreature spell". Always a conjunction regardless
    of `joined`: "a noncreature, nonland spell" (De Morgan on "a creature or
    land spell", the same reading `machines/effects.py`'s own
    `_nonland_or_typed_card_matcher` already gives a comma-joined negation
    list) means the object may be neither, and there is no printed shape
    where a mana-spend restriction offers "not a creature, or not a land" as
    two independent ways to satisfy it - only ever "not either"."""
    subtypes: SortedFrozenSet[str] = frozenset()
    """The subtypes the sentence printed, lowercased and singular (the printed
    word is read back to the subtype it names by `data/subtypes.py`) - plus
    Cavern of Souls's chosen creature type (CR 614.12a), which every printing
    that names one attaches to a single quality rather than to a list."""
    supertypes: SortedFrozenSet[Supertype] = frozenset()
    """The supertypes the sentence printed - Delighted Halfling's "a legendary
    spell"."""
    joined: bool = False
    """Whether the printed qualities were a **list** - and so alternatives -
    rather than one description of one object.

    The joining word is the whole discriminator, and Magic's templating is
    consistent about it. A list is joined ("instant and sorcery spells", "a
    Knight or Equipment spell", "Aura and/or Equipment spells", "instant,
    sorcery, Demon, and Spirit spells") and means **any one of them**: CR
    205.2b makes an object "satisfy the criteria for any effect that applies to
    any of their card types", and no spell is ever both an instant and a
    sorcery, so a joined list read as a conjunction would permit nothing at
    all. Juxtaposition is not joined ("Dragon creature spells", "colorless
    Eldrazi spells", "an Elf creature spell") and means **all of them**,
    because those words describe one object that is every one of them at once -
    which is what makes "artifact creature spells" refuse a plain creature.

    The two readings only differ when a clause names more than one quality, so
    every single-quality clause carries the default. A sentence that mixes the
    two ("artifact creature or enchantment spells") is not read at all: see
    `machines/cost._spend_clause`, which fails it closed rather than choosing
    one of the two readings for it."""
    colorless: bool = False
    """Eldrazi Temple's "colorless": the object must have no colours."""
    zone: Zone | None = None
    """Interdimensional Web Watch's "from exile": the spell's CR 601.2a move
    must have started in this one of CR 400.1's zones. `None` asks nothing,
    like every other empty field here."""
    min_mana_value: int | None = None
    """Helga, Skittish Seer's "creature spells with mana value 4 or greater":
    the spell's CR 202.3 mana value must reach this. `None` asks nothing."""
    requires_x_in_cost: bool = False
    """Helga's "creature spells with {X} in their mana costs"."""
    class_level: bool = False
    """Sorcerer Class's "to gain a Class level": only a CR 716.2a level bar's
    activation (`ManaSpend.class_level`)."""

    def accepts(self, spend: ManaSpend) -> bool:
        # `colorless` and `zone` are never alternatives: no printing offers
        # "colorless or ..." and a zone tail ("from exile") narrows the clause
        # it is attached to rather than adding a way to satisfy it. Both are
        # asked whichever reading `joined` gives the qualities.
        if spend.purpose is not self.purpose:
            return False
        if self.colorless and not spend.colorless:
            return False
        # An unknown origin (`ManaSpend.zone` None) fails this the same way a
        # wrong one does, which is the fail-closed direction: a clause that
        # names a zone is not satisfied by a caller who could not say.
        if self.zone is not None and spend.zone is not self.zone:
            return False
        if self.min_mana_value is not None and (
            spend.mana_value is None or spend.mana_value < self.min_mana_value
        ):
            return False
        if self.requires_x_in_cost and not spend.x_in_cost:
            return False
        if self.class_level and not spend.class_level:
            return False
        # CR 109.2: every negated type must be absent, independently of
        # `joined` and of whatever the positive qualities below ask - "not
        # this" is never one alternative among several the way a positive
        # type list can be.
        if self.excluded_types & spend.types:
            return False

        printed: list[tuple[frozenset[Any], frozenset[Any]]] = [
            (asked, held)
            for asked, held in (
                (self.types, spend.types),
                (self.subtypes, spend.subtypes),
                (self.supertypes, spend.supertypes),
            )
            if asked
        ]
        if not printed:
            return True
        if self.joined:
            return any(asked & held for asked, held in printed)
        return all(asked <= held for asked, held in printed)


class ManaRestriction(EngineModel):
    """A CR 106.6 "Spend this mana only to ..." tag, carried by the mana.

    `text` is the printed sentence verbatim, so a refusal can quote the card
    rather than the parser's reading of it.

    A restriction with **no** clauses is the fail-closed reading of a sentence
    this engine could not parse: `allows` then answers False for everything, so
    the mana exists, is announced (CR 106.4a), empties with the pool
    (CR 703.4q), and pays for nothing at all. Producing mana that looks
    spendable and is not is the exact defect this subsystem was written to
    avoid, so an unread restriction fails towards refusing, never towards
    permitting.
    """

    model_config = ConfigDict(frozen=True)

    text: str
    clauses: tuple[SpendClause, ...] = ()

    @property
    def understood(self) -> bool:
        """Whether the printed sentence was read into anything checkable."""
        return bool(self.clauses)

    def allows(self, spend: ManaSpend | None) -> bool:
        """Whether this mana may pay for `spend`.

        `None` means the caller could not say what the mana is being spent on.
        That is refused for the same reason an unread sentence is: the engine
        cannot show the restriction was honoured, so it does not pretend it
        was.
        """
        if spend is None:
            return False
        return any(clause.accepts(spend) for clause in self.clauses)

    def __str__(self) -> str:
        return self.text


class ManaSpendEffect(EngineModel):
    """CR 106.6's *second* clause, carried by the mana the same way a
    restriction is: "have an additional effect that affects the spell or
    ability that mana is spent on".

    Arena of Glory prints the only one in this pool: "{R}, {T}, Exert this
    land: Add {R}{R}. If that mana is spent on a creature spell, it gains
    haste until end of turn." `text` is that trailing sentence verbatim, read
    off the mana ability by `machines/abilities.parse_mana_abilities` onto
    `ManaAbility.spend_effect` and handed to `ManaPool.add` as the mana is
    produced - the tag is on the *mana*, not on the land, which is what makes
    it survive the land being destroyed and makes it apply to nothing else the
    land ever taps for.

    Unlike `ManaRestriction`, an unread sentence here is not fail-closed and
    could not be: this clause never narrows what the mana may pay for, so
    refusing to spend it would be strictly worse than spending it and applying
    nothing. The reading happens later, at CR 601.2h, in
    `machines/layers.spend_effect_grant`; a sentence nothing there recognises
    is recorded, spent, and quietly does nothing extra.
    """

    model_config = ConfigDict(frozen=True)

    text: str

    def __str__(self) -> str:
        return self.text


class SpendEffectMana(EngineModel):
    """How much mana in a pool carries one particular `ManaSpendEffect`.

    `RestrictedMana`'s twin, kept in its own list for the same reason: the
    pool's `floating` total stays the whole amount of mana that is there
    (CR 106.4a), and this says which part of it is tagged.
    """

    effect: ManaSpendEffect
    amounts: dict[Color, int] = Field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.amounts.values())


class RestrictedMana(EngineModel):
    """How much mana in a pool carries one particular restriction.

    A pool holds a list of these beside its `floating` total, rather than
    replacing `floating`, so every existing reader of the pool still sees the
    whole amount of mana that is there - the restriction narrows what may be
    *done* with it, and CR 106.4a still has the player announce all of it.
    """

    restriction: ManaRestriction
    amounts: dict[Color, int] = Field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.amounts.values())


# --------------------------------------------------------------------------
# Mana that survives a step or phase ending (CR 500.5, 500.5a, 500.5b)
# --------------------------------------------------------------------------
#
# CR 500.5, looked up this session: "As a step or phase ends ... any unspent
# mana left in a player's mana pool empties. This is a turn-based action that
# doesn't use the stack." A handful of effects replace that turn-based action
# for the mana *they* added, keeping it past the boundary that would
# otherwise empty it - CR 702.189a's firebending ("Until end of combat, you
# don't lose this mana as steps and phases end") and Photon, Mighty Marvel's
# combat-damage trigger ("Until end of turn, you don't lose this mana as
# steps and phases end").
#
# Two named points cover every printed sentence this engine reads:
#
# - **CR 500.5a**: "Effects that last 'until end of combat' expire at the end
#   of the combat phase, not at the beginning of the end of combat step" - so
#   firebending's mana survives the end of combat *step* and only empties
#   when the combat *phase* itself ends (`Game.empty_mana_pools`, called with
#   `Step.END_OF_COMBAT` as the step that just ended).
# - **CR 500.5b / CR 514.2**: "until end of turn" effects end in the cleanup
#   step, "as one simultaneous event" with the marked damage clearing - so
#   Photon's mana survives every ordinary step and phase boundary for the
#   rest of the turn and only empties there (`Game.cleanup_step`).
#
# The tag is on the **mana**, the same way a CR 106.6 restriction is
# (`RestrictedMana`'s own docstring above) - it travels with the mana in the
# pool, is spendable exactly like ordinary mana in the meantime (nothing here
# narrows what it may pay for), and dies with the mana once its own named
# point is reached, never later.


class ManaRetentionScope(StrEnum):
    """The named point a retained mana's exemption from CR 500.5 runs to.

    Every printed sentence in this pool names one of these two points. A third
    point - Horizon Stone's differently-worded "doesn't empty ... this turn" -
    is not read by any parser yet (`machines/effects.py`'s
    `_KEEP_MANA_UNTIL_END_OF_TURN_RE`/`_FIREBENDING_ADD_MANA_RE` match only
    the "you don't lose this mana as steps and phases end" phrasing), so no
    third member exists to be silently misread.
    """

    END_OF_COMBAT = "end_of_combat"
    """CR 500.5a: the end of the combat phase, not the end of combat step."""
    END_OF_TURN = "end_of_turn"
    """CR 500.5b / 514.2: the cleanup step's "until end of turn" action."""


class RetainedMana(EngineModel):
    """How much mana in a pool is exempt from CR 500.5's step/phase emptying
    until `until`, one entry per distinct scope.

    `RestrictedMana`/`SpendEffectMana`'s third sibling: narrows nothing about
    what the mana may pay for (`ManaPool.payment_for` never reads this), so
    ordinary spending doesn't need to know about it - only `ManaPool.empty`
    does, to decide what survives a boundary. No printed source of retained
    mana in this pool is also snow or CR 106.6-restricted, so `ManaPool.empty`
    does not attempt to carry a colour's snow flag or restriction tag through
    a boundary retained mana of that colour survives; a future card that
    combines them would need that taught here.
    """

    until: ManaRetentionScope
    amounts: dict[Color, int] = Field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.amounts.values())


class ManaPayment(EngineModel):
    """One settled way to pay a cost: what each symbol was paid with.

    `options` lines up with `ManaCost.symbols`. `spend` is the mana taken out
    of the pool, of which `snow_spent` came from snow sources, and `life_paid`
    is what the payer still owes their life total (CR 118.13a).

    `restricted_spent` says how much of `spend` carried a CR 106.6 restriction
    and which - the pool needs it to take the mana out of the right bucket, and
    a test needs it to prove that restricted mana was preferred over
    unrestricted mana that would also have paid.
    """

    options: tuple[PaymentOption, ...] = ()
    spend: dict[Color, int] = Field(default_factory=dict)
    snow_spent: dict[Color, int] = Field(default_factory=dict)
    restricted_spent: list[RestrictedMana] = Field(default_factory=list)
    spend_effects_spent: list[SpendEffectMana] = Field(default_factory=list)
    """How much of `spend` carried a CR 106.6 spend *effect*, and which.

    `restricted_spent`'s twin. The caller that put the payment together -
    `machines/casting.Casting._move_to_the_stack`, at CR 601.2h - reads this
    to record on the spell what the mana it was paid with does to it.
    """
    treasure_spent: dict[Color, int] = Field(default_factory=dict)
    """How much of `spend` came from a Treasure (CR 106.3's source of mana) -
    "if mana from a Treasure was spent to cast it". A sub-count of the
    untagged mana spent, like `snow_spent`; read onto `CastRecord`."""
    creature_spent: dict[Color, int] = Field(default_factory=dict)
    """How much of `spend` came from a creature (CR 106.3: the source of mana
    is the source of the ability that produced it) - Inga and Esika's "if
    three or more mana from creatures was spent to cast it". A sub-count of
    `spend` whatever tags the mana carried, since a creature's mana may be
    restricted (Inga and Esika's own grant is); read onto `CastRecord`."""
    basic_land_spent: dict[Color, int] = Field(default_factory=dict)
    """How much of `spend` came from a basic land (CR 106.3), so paying with the
    restricted sub-pool also takes it out of `ManaPool.basic_land`."""
    retained_spent: list[RetainedMana] = Field(default_factory=list)
    """How much of `spend` was retained mana (CR 500.5a/500.5b), and under
    which scope - `restricted_spent`'s third sibling, read back by `pay` so
    spending retained mana takes it out of `ManaPool.retained` too, the same
    way spending restricted mana takes it out of `ManaPool.restricted`."""
    life_paid: int = 0

    @property
    def mana_spent(self) -> int:
        return sum(self.spend.values())

    @property
    def restricted_mana_spent(self) -> int:
        return sum(entry.total for entry in self.restricted_spent)


# --------------------------------------------------------------------------
# The pool
# --------------------------------------------------------------------------

#: (colour, came from a snow source, index into `ManaPool.restricted` or -1
#: for mana with no CR 106.6 restriction on it, index into
#: `ManaPool.spend_effects` or -1 for mana carrying no CR 106.6 spend effect,
#: index into `ManaPool.retained` or -1 for mana with no CR 500.5a/500.5b
#: retention on it).
#:
#: The last three slots are separate dimensions because a card may print any
#: of CR 106.6's restriction, CR 106.6's additional effect, and CR 500.5's
#: retention independently of the other two. Nothing in this pool prints more
#: than one of them on the same mana ability, and `_buckets` says what it
#: assumes when that changes.
_Bucket = tuple[Color, bool, int, int, int]

#: The `_Bucket` slot meaning "no spend restriction".
UNRESTRICTED = -1

#: The `_Bucket` slot meaning "no CR 106.6 spend effect".
NO_SPEND_EFFECT = -1

#: The `_Bucket` slot meaning "no CR 500.5a/500.5b retention".
NOT_RETAINED = -1


def _candidate_options(
    cost: ManaCost, choices: Sequence[int | None] | None
) -> Iterable[tuple[PaymentOption, ...]]:
    """Every distinct assignment of one payment option per symbol of `cost`.

    Module-level rather than a `ManaPool` method - despite living beside it,
    it reads only `cost`/`choices` and touches no pool state, so a caller that
    has no pool at all (`machines/cost.py`'s tap-solving, which is choosing
    *sources*, not settling a payment against a live pool) can enumerate the
    cost's own payable-in-multiple-ways symbols (CR 118.13a) the same way
    `ManaPool.payment_for` does, without constructing a throwaway pool just to
    reach a method that never looks at it.

    Identical symbols are grouped and enumerated as multisets rather than as
    ordered tuples, so `{2/W}{2/W}{2/W}` is four candidates and not eight. A
    pinned choice collapses its symbol to one option.
    """
    groups: dict[ManaSymbol, list[int]] = {}
    for index, symbol in enumerate(cost.symbols):
        groups.setdefault(symbol, []).append(index)

    per_group: list[list[list[tuple[int, PaymentOption]]]] = []
    for symbol, indexes in groups.items():
        options = symbol.options
        pinned = {i: choices[i] for i in indexes if choices and choices[i] is not None}
        free = [i for i in indexes if i not in pinned]
        fixed = [(i, options[choice]) for i, choice in pinned.items()]  # type: ignore[index]
        per_group.append(
            [
                fixed + list(zip(free, picks, strict=True))
                for picks in combinations_with_replacement(options, len(free))
            ]
        )

    for combination in product(*per_group):
        assignment: dict[int, PaymentOption] = {}
        for group in combination:
            assignment.update(group)
        yield tuple(assignment[i] for i in range(len(cost.symbols)))


def _demand_list(
    options: Sequence[PaymentOption],
    buckets: Iterable[_Bucket],
    *,
    any_color: bool = False,
    snow_any_color: bool = False,
    any_type: bool = False,
) -> list[tuple[int, list[_Bucket]]]:
    """The demand list `_assign` (and `machines/cost.py`'s source-picking
    `_assign_sources`) solve against, built from one resolution of a cost's
    payable-in-multiple-ways symbols (CR 118.13a - `_candidate_options`) and
    the buckets that exist to pay them.

    Most restrictive demand first: a fixed colour, then snow (CR 107.4h - any
    colour but only from a snow source), then generic, which takes anything.
    Each `allowed` list is filtered out of `buckets` rather than rebuilt, so
    whatever preference order `buckets` already carries (restricted before
    unrestricted, non-snow before snow - see `ManaPool._buckets`) survives
    into the demand list unchanged, which is what makes a restricted bucket
    the one spent when either would do.

    `any_color` is CR 609.4b's "spend mana as though it were mana of any
    color" (`ManaSpend.any_color`): a coloured demand then accepts every
    bucket - colorless mana included, since it is spent *as though* it were
    that color - while a `{C}` demand (`Color.COLORLESS`, not a color) and a
    snow demand stay as they are.

    `any_type` is CR 609.4b's "mana of any type can be spent" (Vizier of the
    Menagerie): the `{C}` demand then accepts every bucket as well.

    `snow_any_color` is the same permission narrowed to mana from snow sources
    (`ManaSpend.snow_any_color`, Draugr Necromancer): only a snow bucket is
    widened.
    """
    buckets = list(buckets)
    generic = sum(option.generic for option in options)
    snow_needed = sum(1 for option in options if option.snow)
    colors: Counter[Color] = Counter(
        option.color for option in options if option.color is not None and not option.snow
    )
    demands: list[tuple[int, list[_Bucket]]] = [
        (
            count,
            list(buckets)
            if any_color and (color is not Color.COLORLESS or any_type)
            else [
                b
                for b in buckets
                if b[0] == color or (snow_any_color and b[1] and color is not Color.COLORLESS)
            ],
        )
        for color, count in colors.items()
    ]
    if snow_needed:
        demands.append((snow_needed, [b for b in buckets if b[1]]))
    if generic:
        demands.append((generic, list(buckets)))
    return demands


def _kept(amounts: dict[Color, int], keep: frozenset[Color]) -> dict[Color, int]:
    """The part of a per-colour tally whose colour a CR 614.1a "don't lose"
    replacement keeps (`ManaPool.empty`)."""
    return {color: amount for color, amount in amounts.items() if color in keep and amount}


def _recoloured(
    amounts: dict[Color, int], lost: dict[Color, int], becomes: Color
) -> dict[Color, int]:
    """A per-colour tally after the mana `lost` would have lost became
    `becomes` instead (`ManaPool.empty`): up to the lost amount of each colour
    moves to the new colour, whatever retained mana is left of it stays."""
    moved: dict[Color, int] = {}
    for color, amount in amounts.items():
        shift = min(amount, lost.get(color, 0))
        if amount - shift:
            moved[color] = moved.get(color, 0) + amount - shift
        if shift:
            moved[becomes] = moved.get(becomes, 0) + shift
    return moved


def _clipped(tagged: dict[Color, int], within: dict[Color, int]) -> dict[Color, int]:
    """`tagged` limited, colour by colour, to what `within` holds."""
    return {c: n for c, n in ((c, min(n, within.get(c, 0))) for c, n in tagged.items()) if n > 0}


class ManaPool(EngineModel):
    """Mana floating in a player's pool.

    Mana knows whether it came from a snow source (CR 106.3), because `{S}`
    can only be paid with mana that did, and whether a CR 106.6 spend
    restriction came with it, because that decides what it may pay for at all.
    """

    floating: dict[Color, int] = Field(default_factory=dict)
    snow: dict[Color, int] = Field(default_factory=dict)
    treasure: dict[Color, int] = Field(default_factory=dict)
    """The part of `floating` a Treasure produced (CR 106.3: the source of
    mana is the source of the ability that produced it) - what "if mana from
    a Treasure was spent to cast it" asks after. It narrows nothing: a
    Treasure's mana carries no CR 106.6 tag, so it is always among the
    untagged, non-snow mana, and a payment spends it before other mana of
    the same colour (CR 118.3a leaves which mana to the payer)."""
    basic_land: dict[Color, int] = Field(default_factory=dict)
    """The part of `floating` a basic land produced (CR 106.3), whatever else it
    is tagged with - what "Spend only mana produced by basic lands to cast this
    spell" (`ManaSpend.only_from`) may draw on. Like `treasure` it narrows
    nothing by itself; the spell's own restriction does."""
    creature: dict[Color, int] = Field(default_factory=dict)
    """The part of `floating` a creature produced (CR 106.3), whatever else it
    is tagged with - what "mana from creatures was spent to cast it" asks
    after. Like `treasure` it narrows nothing; a payment spends it before
    other mana of the same colour (CR 118.3a leaves which mana to the
    payer)."""
    restricted: list[RestrictedMana] = Field(default_factory=list)
    """The CR 106.6-restricted part of `floating`, one entry per distinct
    restriction. Never more than `floating` holds of that colour; the rest of
    `floating` is spendable on anything."""

    spend_effects: list[SpendEffectMana] = Field(default_factory=list)
    """The part of `floating` carrying CR 106.6's *additional effect* clause,
    one entry per distinct effect. Unlike `restricted` this narrows nothing -
    the mana pays for whatever it could have paid for anyway - it only records
    what happens to the spell it is spent on."""

    retained: list[RetainedMana] = Field(default_factory=list)
    """The part of `floating` exempt from CR 500.5's step/phase emptying
    until its own named point (CR 500.5a/500.5b), one entry per distinct
    scope. Like `spend_effects` this narrows nothing about what the mana may
    pay for - only `empty` reads it."""

    @property
    def total(self) -> int:
        return sum(self.floating.values())

    @property
    def is_empty(self) -> bool:
        return self.total == 0

    @property
    def snow_total(self) -> int:
        return sum(self.snow.values())

    @property
    def restricted_total(self) -> int:
        return sum(entry.total for entry in self.restricted)

    @property
    def retained_total(self) -> int:
        return sum(entry.total for entry in self.retained)

    def restrictions(self) -> list[ManaRestriction]:
        """Every distinct restriction currently on mana in this pool."""
        return [entry.restriction for entry in self.restricted if entry.total]

    def retentions(self) -> list[ManaRetentionScope]:
        """Every distinct retention scope currently on mana in this pool."""
        return [entry.until for entry in self.retained if entry.total]

    def add(
        self,
        color: Color,
        amount: int = 1,
        snow: bool = False,
        restriction: "ManaRestriction | None" = None,
        spend_effect: "ManaSpendEffect | None" = None,
        retain_until: "ManaRetentionScope | None" = None,
        treasure: bool = False,
        creature: bool = False,
        basic_land: bool = False,
    ) -> None:
        if amount < 0:
            raise ValueError("cannot add a negative amount of mana")
        announce_mutation(self)
        self.floating[color] = self.floating.get(color, 0) + amount
        if snow:
            self.snow[color] = self.snow.get(color, 0) + amount
        if creature and amount:
            self.creature[color] = self.creature.get(color, 0) + amount
        if basic_land and amount:
            self.basic_land[color] = self.basic_land.get(color, 0) + amount
        if (
            treasure
            and amount
            and not snow
            and restriction is None
            and spend_effect is None
            and retain_until is None
        ):
            self.treasure[color] = self.treasure.get(color, 0) + amount
        if restriction is not None and amount:
            entry = self._entry_for(restriction)
            entry.amounts[color] = entry.amounts.get(color, 0) + amount
        if spend_effect is not None and amount:
            tagged = self._effect_entry_for(spend_effect)
            tagged.amounts[color] = tagged.amounts.get(color, 0) + amount
        if retain_until is not None and amount:
            kept = self._retained_entry_for(retain_until)
            kept.amounts[color] = kept.amounts.get(color, 0) + amount
        mutation_landed(self, structural=False)

    def add_all(
        self,
        colors: Iterable[Color],
        snow: bool = False,
        restriction: "ManaRestriction | None" = None,
        spend_effect: "ManaSpendEffect | None" = None,
        retain_until: "ManaRetentionScope | None" = None,
        treasure: bool = False,
        creature: bool = False,
        basic_land: bool = False,
    ) -> None:
        for color in colors:
            self.add(
                color,
                snow=snow,
                restriction=restriction,
                spend_effect=spend_effect,
                retain_until=retain_until,
                treasure=treasure,
                creature=creature,
                basic_land=basic_land,
            )

    def empty(
        self,
        *,
        expiring: frozenset[ManaRetentionScope] = frozenset(),
        keep: frozenset[Color] = frozenset(),
        becomes: Color | None = None,
    ) -> None:
        """Empty the pool, as happens when each step and phase ends.

        CR 703.4q and CR 500.5: "as each step or phase ends, any unspent mana
        left in a player's mana pool empties". The restriction goes with the
        mana it was on, because it was never anywhere else - it is not a
        property of the source, which may still be on the battlefield, so
        there is nothing left over to carry into the next step.

        `expiring` names whichever `ManaRetentionScope`s reach their own named
        point at this exact boundary (CR 500.5a's end of the combat phase,
        CR 500.5b/514.2's cleanup step) - retained mana tagged with one of
        them empties too, along with everything ordinary. A scope left out of
        `expiring` keeps its mana floating, still spendable exactly like
        ordinary mana, until a later call names it.

        `keep` and `becomes` are what replaced the loss of the rest (CR
        614.1a, `machines/unspent_mana.settle_mana_loss`): mana of a colour in
        `keep` is not lost at all and stays exactly as it is ("You don't lose
        unspent red mana as steps and phases end"), and whatever would still
        be lost becomes `becomes` instead ("If you would lose unspent mana,
        that mana becomes black instead"). The printings' rulings keep a
        restriction or rider with mana that changes colour, so every tag
        travels with it to the new colour.
        """
        surviving = [entry for entry in self.retained if entry.until not in expiring]
        survived: dict[Color, int] = {}
        for entry in surviving:
            for color, amount in entry.amounts.items():
                survived[color] = survived.get(color, 0) + amount
        if not keep and becomes is None:
            self.floating = survived
            self.snow = {}
            self.treasure = {}
            self.creature = {}
            self.basic_land = {}
            self.restricted = []
            self.spend_effects = []
            self.retained = surviving
            return
        lost = {
            color: amount - survived.get(color, 0)
            for color, amount in self.floating.items()
            if color not in keep and amount - survived.get(color, 0) > 0
        }
        if becomes is None or not lost:
            floating = {
                color: amount if color in keep else survived.get(color, 0)
                for color, amount in self.floating.items()
            }
            self.floating = {color: amount for color, amount in floating.items() if amount}
            self.snow = _kept(self.snow, keep)
            self.treasure = _kept(self.treasure, keep)
            self.creature = _kept(self.creature, keep)
            self.basic_land = _kept(self.basic_land, keep)
            for tagged in (*self.restricted, *self.spend_effects):
                tagged.amounts = _kept(tagged.amounts, keep)
            self.restricted = [entry for entry in self.restricted if entry.amounts]
            self.spend_effects = [entry for entry in self.spend_effects if entry.amounts]
            # An expired retention's tag goes even where the mana stays: what
            # keeps that mana now is the static, not the retention.
            self.retained = surviving
            return
        floating = {color: amount for color, amount in self.floating.items() if color not in lost}
        for color, amount in lost.items():
            floating[color] = floating.get(color, 0) + (self.floating[color] - amount)
        floating[becomes] = floating.get(becomes, 0) + sum(lost.values())
        self.floating = {color: amount for color, amount in floating.items() if amount}
        self.snow = _recoloured(self.snow, lost, becomes)
        self.treasure = _recoloured(self.treasure, lost, becomes)
        self.creature = _recoloured(self.creature, lost, becomes)
        self.basic_land = _recoloured(self.basic_land, lost, becomes)
        for tagged in (*self.restricted, *self.spend_effects):
            tagged.amounts = _recoloured(tagged.amounts, lost, becomes)
        self.retained = surviving

    def _entry_for(self, restriction: ManaRestriction) -> RestrictedMana:
        for entry in self.restricted:
            if entry.restriction == restriction:
                return entry
        entry = RestrictedMana(restriction=restriction)
        announce_mutation(self)
        self.restricted.append(entry)
        mutation_landed(self)
        return entry

    def _effect_entry_for(self, effect: ManaSpendEffect) -> SpendEffectMana:
        for entry in self.spend_effects:
            if entry.effect == effect:
                return entry
        entry = SpendEffectMana(effect=effect)
        announce_mutation(self)
        self.spend_effects.append(entry)
        mutation_landed(self)
        return entry

    def _retained_entry_for(self, until: ManaRetentionScope) -> RetainedMana:
        for entry in self.retained:
            if entry.until == until:
                return entry
        entry = RetainedMana(until=until)
        announce_mutation(self)
        self.retained.append(entry)
        mutation_landed(self)
        return entry

    # -- paying ------------------------------------------------------------

    def can_pay(
        self, cost: ManaCost, *, life_available: int = 0, spend: ManaSpend | None = None
    ) -> bool:
        """True if some way of paying `cost` exists.

        `life_available` is what the payer may spend on Phyrexian symbols; it
        defaults to nothing, so a Phyrexian cost is only payable with mana
        unless the caller says the life is on the table.

        `spend` is what the mana would be paid for, which is what any CR 106.6
        restricted mana in the pool is judged against. Left out, restricted
        mana is not counted as available at all.
        """
        return self.payment_for(cost, life_available=life_available, spend=spend) is not None

    def payment_for(
        self,
        cost: ManaCost,
        *,
        life_available: int = 0,
        choices: Sequence[int | None] | None = None,
        spend: ManaSpend | None = None,
    ) -> ManaPayment | None:
        """Work out a way to pay `cost`, or None if the pool cannot.

        The payer may pin any symbol's choice by passing `choices`, one index
        into that symbol's `options` per symbol, `None` to leave it open. What
        is left open is chosen for them: least life first, then least mana.

        `spend` names what the cost belongs to, so mana carrying a CR 106.6
        restriction can be judged against it. Restricted mana the restriction
        does not permit is not available to this payment at all - a pool of
        two restricted mana cannot pay a cost it is not allowed to pay, which
        is a refusal, not a preference.
        """
        if cost.x_count:
            raise ValueError("resolve X with ManaCost.with_x before paying")
        if choices is not None and len(choices) != len(cost.symbols):
            raise ValueError(f"expected {len(cost.symbols)} choices, got {len(choices)}")
        if spend is not None and spend.only_from is not None:
            # Only the part of the pool that kind of source made is spendable.
            source = getattr(self, spend.only_from)
            narrowed = ManaPool(
                floating=dict(source),
                treasure=_clipped(self.treasure, source),
                creature=_clipped(self.creature, source),
                basic_land=_clipped(self.basic_land, source),
                snow=_clipped(self.snow, source),
            )
            return narrowed.payment_for(
                cost,
                life_available=life_available,
                choices=choices,
                spend=spend.model_copy(update={"only_from": None}),
            )
        if spend is not None and spend.treasure_only:
            # Only the Treasure-made part of the pool is spendable at all.
            treasures = ManaPool(floating=dict(self.treasure), treasure=dict(self.treasure))
            return treasures.payment_for(
                cost,
                life_available=life_available,
                choices=choices,
                spend=spend.model_copy(update={"treasure_only": False}),
            )

        best: ManaPayment | None = None
        for options in _candidate_options(cost, choices):
            life = sum(option.life for option in options)
            if life > life_available:
                continue
            if best is not None and life > best.life_paid:
                continue
            settled = self._settle(options, life, spend)
            if settled is None:
                continue
            if best is None or (settled.life_paid, settled.mana_spent) < (
                best.life_paid,
                best.mana_spent,
            ):
                best = settled
        return best

    def pay(
        self,
        cost: ManaCost,
        *,
        life_available: int = 0,
        payment: ManaPayment | None = None,
        spend: ManaSpend | None = None,
    ) -> "ManaPool":
        """Spend `cost` from the pool and return what is left floating.

        The pool is emptied of the mana spent, so the returned pool is this same
        object: the overflow that survives the payment.

        Life is *not* deducted here - the pool cannot reach a life total. The
        caller must apply `payment.life_paid` with `Player.lose_life`; use
        `payment_for` first when the cost has a Phyrexian symbol.
        """
        if payment is None:
            payment = self.payment_for(cost, life_available=life_available, spend=spend)
        if payment is None:
            if spend is not None and spend.no_mana and cost.symbols:
                raise ValueError(
                    f"{spend.name} says you can't spend mana to cast this spell, so {cost} "
                    "can only be paid with convoke and delve (CR 601.2h)"
                )
            raise ValueError(f"pool {self.floating} cannot pay {cost}")

        announce_mutation(self)
        try:
            for color, amount in payment.spend.items():
                left = self.floating.get(color, 0) - amount
                if left < 0:
                    raise ValueError(f"pool {self.floating} cannot pay {cost}")
                self.floating[color] = left
            for color, amount in payment.snow_spent.items():
                self.snow[color] = max(self.snow.get(color, 0) - amount, 0)
            for color, amount in payment.treasure_spent.items():
                self.treasure[color] = max(self.treasure.get(color, 0) - amount, 0)
            for color, amount in payment.creature_spent.items():
                self.creature[color] = max(self.creature.get(color, 0) - amount, 0)
            for color, amount in payment.basic_land_spent.items():
                self.basic_land[color] = max(self.basic_land.get(color, 0) - amount, 0)
            for taken in payment.restricted_spent:
                entry = self._entry_for(taken.restriction)
                for color, amount in taken.amounts.items():
                    entry.amounts[color] = max(entry.amounts.get(color, 0) - amount, 0)
            for tagged in payment.spend_effects_spent:
                marked = self._effect_entry_for(tagged.effect)
                for color, amount in tagged.amounts.items():
                    marked.amounts[color] = max(marked.amounts.get(color, 0) - amount, 0)
            for kept in payment.retained_spent:
                entry = self._retained_entry_for(kept.until)
                for color, amount in kept.amounts.items():
                    entry.amounts[color] = max(entry.amounts.get(color, 0) - amount, 0)
        finally:
            mutation_landed(self, structural=False)

        self.floating = {color: n for color, n in self.floating.items() if n > 0}
        self.snow = {color: n for color, n in self.snow.items() if n > 0}
        self.treasure = {color: n for color, n in self.treasure.items() if n > 0}
        self.creature = {color: n for color, n in self.creature.items() if n > 0}
        self.basic_land = {color: n for color, n in self.basic_land.items() if n > 0}
        for entry in self.restricted:
            entry.amounts = {color: n for color, n in entry.amounts.items() if n > 0}
        self.restricted = [entry for entry in self.restricted if entry.amounts]
        for tagged in self.spend_effects:
            tagged.amounts = {color: n for color, n in tagged.amounts.items() if n > 0}
        self.spend_effects = [tagged for tagged in self.spend_effects if tagged.amounts]
        for entry in self.retained:
            entry.amounts = {color: n for color, n in entry.amounts.items() if n > 0}
        self.retained = [entry for entry in self.retained if entry.amounts]
        return self

    # -- the search --------------------------------------------------------

    def _settle(
        self,
        options: Sequence[PaymentOption],
        life: int,
        spend_on: ManaSpend | None = None,
    ) -> ManaPayment | None:
        """Can the pool cover these fixed demands? If so, with what mana?"""
        buckets = self._spendable_buckets(spend_on)
        demands = _demand_list(
            options,
            buckets,
            any_color=spend_on is not None and spend_on.any_color,
            snow_any_color=spend_on is not None and spend_on.snow_any_color,
            any_type=spend_on is not None and spend_on.any_type,
        )
        spent = _assign(buckets, demands)
        if spent is None:
            return None

        spend: Counter[Color] = Counter()
        snow_spent: Counter[Color] = Counter()
        untagged_spent: Counter[Color] = Counter()
        restricted_spent: dict[int, Counter[Color]] = {}
        effects_spent: dict[int, Counter[Color]] = {}
        retained_spent: dict[int, Counter[Color]] = {}
        for (color, is_snow, slot, effect_slot, retained_slot), amount in spent.items():
            spend[color] += amount
            if is_snow:
                snow_spent[color] += amount
            elif (slot, effect_slot, retained_slot) == (
                UNRESTRICTED,
                NO_SPEND_EFFECT,
                NOT_RETAINED,
            ):
                untagged_spent[color] += amount
            if slot != UNRESTRICTED:
                restricted_spent.setdefault(slot, Counter())[color] += amount
            if effect_slot != NO_SPEND_EFFECT:
                effects_spent.setdefault(effect_slot, Counter())[color] += amount
            if retained_slot != NOT_RETAINED:
                retained_spent.setdefault(retained_slot, Counter())[color] += amount
        return ManaPayment(
            options=tuple(options),
            spend=dict(spend),
            snow_spent=dict(snow_spent),
            treasure_spent={
                color: taken
                for color, amount in untagged_spent.items()
                if (taken := min(amount, self.treasure.get(color, 0))) > 0
            },
            creature_spent={
                color: taken
                for color, amount in spend.items()
                if (taken := min(amount, self.creature.get(color, 0))) > 0
            },
            basic_land_spent={
                color: taken
                for color, amount in spend.items()
                if (taken := min(amount, self.basic_land.get(color, 0))) > 0
            },
            restricted_spent=[
                RestrictedMana(restriction=self.restricted[slot].restriction, amounts=dict(taken))
                for slot, taken in sorted(restricted_spent.items())
            ],
            spend_effects_spent=[
                SpendEffectMana(effect=self.spend_effects[slot].effect, amounts=dict(taken))
                for slot, taken in sorted(effects_spent.items())
            ],
            retained_spent=[
                RetainedMana(until=self.retained[slot].until, amounts=dict(taken))
                for slot, taken in sorted(retained_spent.items())
            ],
            life_paid=life,
        )

    def _spendable_buckets(self, spend_on: ManaSpend | None) -> dict[_Bucket, int]:
        """`_buckets`, minus every bucket CR 106.6 forbids this payment.

        Mana whose restriction does not permit `spend_on` is not merely a last
        resort here, it is absent: the pool genuinely cannot pay with it, and a
        cost that needs it is refused (CR 118.3a - paying is removing the
        indicated mana from the pool, and this mana may not be removed for
        this).
        """
        if spend_on is not None and spend_on.no_mana:
            return {}
        return {
            bucket: amount
            for bucket, amount in self._buckets().items()
            if bucket[2] == UNRESTRICTED or self.restricted[bucket[2]].restriction.allows(spend_on)
        }

    def _buckets(self) -> dict[_Bucket, int]:
        """The pool split by restriction and by snow, least flexible first.

        The order is the whole of this engine's spending preference, and it is
        one rule: spend the mana that can do the least, so the mana that can do
        the most is what stays floating.

        - **Restricted before unrestricted.** A CR 106.6 restriction only ever
          narrows what mana can do, so restricted mana is strictly the less
          useful of the two and burning the unrestricted mana first would
          strand it - a board where a legal play is then wrongly refused. This
          is a choice about *which* mana pays among several that legally could
          (CR 118.3a leaves it to the payer); it never lets restricted mana pay
          for something its restriction forbids, which `_spendable_buckets` has
          already made impossible.
        - **Non-snow before snow**, for exactly the same reason: snow mana can
          pay a `{S}` and anything else, so it is the flexible one and is left
          floating for a `{S}` that may still need it (CR 107.4h, 106.3).
        - Then the most plentiful bucket, which only decides between equals.

        The snow count is allocated to the unrestricted part of a colour
        first. Nothing in this card pool produces mana that is both snow and
        restricted, so the two never actually meet; when they do, the choice
        made here is the conservative one, keeping the restricted bucket the
        plain one.
        """
        buckets: dict[_Bucket, int] = {}
        for color, amount in self.floating.items():
            per_slot = [
                (slot, entry.amounts.get(color, 0))
                for slot, entry in enumerate(self.restricted)
                if entry.amounts.get(color, 0)
            ]
            per_effect = [
                (slot, tagged.amounts.get(color, 0))
                for slot, tagged in enumerate(self.spend_effects)
                if tagged.amounts.get(color, 0)
            ]
            per_retained = [
                (slot, entry.amounts.get(color, 0))
                for slot, entry in enumerate(self.retained)
                if entry.amounts.get(color, 0)
            ]
            restricted_here = sum(count for _slot, count in per_slot)
            tagged_here = sum(count for _slot, count in per_effect)
            retained_here = sum(count for _slot, count in per_retained)
            # A restricted bucket, a spend-effect bucket and a retained bucket
            # are counted as disjoint parts of the same colour. No card in
            # this pool prints two of CR 106.6's/CR 500.5's clauses on one
            # mana ability; when one does, the lists have to be crossed here
            # instead of subtracted, and the `_Bucket` key already has the
            # room for it.
            unrestricted = max(amount - restricted_here - tagged_here - retained_here, 0)
            snow = min(self.snow.get(color, 0), unrestricted)
            for is_snow, count in ((False, unrestricted - snow), (True, snow)):
                if count:
                    buckets[(color, is_snow, UNRESTRICTED, NO_SPEND_EFFECT, NOT_RETAINED)] = count
            for slot, count in per_slot:
                buckets[(color, False, slot, NO_SPEND_EFFECT, NOT_RETAINED)] = count
            for slot, count in per_effect:
                buckets[(color, False, UNRESTRICTED, slot, NOT_RETAINED)] = count
            for slot, count in per_retained:
                buckets[(color, False, UNRESTRICTED, NO_SPEND_EFFECT, slot)] = count
        return dict(
            sorted(
                buckets.items(),
                key=lambda item: (
                    item[0][2] == UNRESTRICTED,
                    item[0][3] == NO_SPEND_EFFECT,
                    item[0][4] != NOT_RETAINED,
                    item[0][1],
                    -item[1],
                ),
            )
        )


def _assign(
    buckets: dict[_Bucket, int], demands: list[tuple[int, list[_Bucket]]]
) -> dict[_Bucket, int] | None:
    """Match demands against buckets exactly, or return None if impossible.

    Each demand needs `count` mana and accepts only certain buckets, so this is
    a transportation problem. Greedy gets it wrong - a colour demand and a
    generic demand can want the same mana while a swap satisfies both - so it
    is solved as a max-flow: source -> demand -> allowed buckets -> sink, with
    the demand feasible exactly when the flow saturates the source.

    The degenerate case of `_assign_sources` where every bucket is its own
    sole provider, capped at its own pool amount - which is exactly what a
    live `ManaPool` already has, mana already produced and just sitting
    there, with no permanent behind it left to solve for. `machines/cost.py`'s
    tap-solving needs the extra layer because it is choosing *which
    permanents to tap*, not settling a payment against mana that already
    exists; see that function's own docstring for why one bucket can need more
    than one provider once it is fed by permanents instead.
    """
    solved = _assign_sources(
        demands,
        {bucket: {bucket: amount} for bucket, amount in buckets.items()},
        dict(buckets),
    )
    if solved is None:
        return None
    return {bucket: amounts[bucket] for bucket, amounts in solved.items()}


def _assign_sources(
    demands: list[tuple[int, list[_Bucket]]],
    sources: dict[Hashable, dict[_Bucket, int]],
    capacity: dict[Hashable, int],
) -> dict[Hashable, dict[_Bucket, int]] | None:
    """Match demands against buckets that are themselves fed by providers with
    their own total capacity, or return `None` if impossible.

    `_assign`'s own network extended by one layer, as `machines/cost.py`'s
    auto-tap solver needs it: `source -> demand -> bucket -> sink` becomes
    `source -> demand -> bucket -> provider -> sink`, with the new provider ->
    sink edge, capped at `capacity[provider]`, the one thing this adds. A
    provider is a permanent about to be tapped (or the payer's mana already
    floating, itself capped at the amount it holds) and `sources[provider]` is
    how much of each bucket it could contribute if it were the *only* thing
    spent - a dual land offers 1 into its `{W}` bucket and 1 into its `{U}`
    bucket, never both, which `capacity[provider] = 1` is what actually
    enforces; without that separate cut, two colour edges each capped at 1
    would let the max-flow solver read a one-mana choice as two, the same way
    it would misread Shang-Chi's own choice of colour if that one were routed
    through here as ordinary buckets rather than branched over externally (see
    `machines/cost.py`'s own docstring on which sources this layer can and
    cannot express).

    A provider whose only way to help is a single fixed multiset - a Tron
    piece boosted to `{C}{C}`, Eldrazi Temple's *unrestricted* `{T}: Add {C}.`
    - is never ambiguous even past one mana: it has only one bucket to put
    that mana in (or, if that one option happens to mix colours, one bucket
    per colour it is fixed to), so nothing here needs to choose between two
    ways to spend the same tap. What this layer cannot express, and what a
    caller must resolve before ever building `sources` for it, is a *choice*
    among options where not every option is a single mana of a single colour
    - `machines/cost.py`'s own grouping of a permanent's abilities decides
    that before this is ever called.

    Ford-Fulkerson with a BFS augmenting path, same as `_assign`: O(V * E * F)
    where F is the mana value of the cost. `sources`/`capacity` add at most one
    provider node per permanent under consideration to V, and at most one
    bucket -> provider edge per (bucket, provider) pair to E - still small
    enough, on any real board, for this to run in single-digit milliseconds.
    The order `sources` and each provider's own bucket dict are built in
    decides which provider is spent when several would do, the same way
    `buckets`'s order already decides it for `_assign`.
    """
    needed = sum(count for count, _ in demands)
    if needed == 0:
        return {}

    source_alg, sink_alg = "source", "sink"
    residual: dict[object, dict[object, int]] = {source_alg: {}, sink_alg: {}}

    bucket_nodes: dict[_Bucket, object] = {}

    def bucket_node(bucket: _Bucket) -> object:
        node = bucket_nodes.get(bucket)
        if node is None:
            node = ("bucket", bucket)
            bucket_nodes[bucket] = node
            residual[node] = {}
        return node

    provider_nodes: dict[Hashable, object] = {}
    for provider, amounts in sources.items():
        node = ("provider", provider)
        provider_nodes[provider] = node
        residual.setdefault(node, {})[sink_alg] = capacity.get(provider, sum(amounts.values()))
        residual[sink_alg][node] = 0
        for bucket, amount in amounts.items():
            if amount <= 0:
                continue
            bnode = bucket_node(bucket)
            residual[bnode][node] = amount
            residual[node].setdefault(bnode, 0)

    for index, (count, allowed) in enumerate(demands):
        node = ("demand", index)
        residual[source_alg][node] = count
        residual[node] = {source_alg: 0}
        for bucket in allowed:
            if bucket in bucket_nodes:
                bnode = bucket_nodes[bucket]
                residual[node][bnode] = count
                residual[bnode].setdefault(node, 0)

    flow = 0
    while True:
        parents: dict[object, object] = {source_alg: source_alg}
        queue = [source_alg]
        while queue and sink_alg not in parents:
            node = queue.pop(0)
            for neighbour, edge_capacity in residual[node].items():
                if edge_capacity > 0 and neighbour not in parents:
                    parents[neighbour] = node
                    queue.append(neighbour)
        if sink_alg not in parents:
            break

        path: list[tuple[object, object]] = []
        node = sink_alg
        while node != source_alg:
            path.append((parents[node], node))
            node = parents[node]
        bottleneck = min(residual[a][b] for a, b in path)
        for a, b in path:
            residual[a][b] -= bottleneck
            residual[b][a] = residual[b].get(a, 0) + bottleneck
        flow += bottleneck

    if flow < needed:
        return None

    result: dict[Hashable, dict[_Bucket, int]] = {}
    for provider, amounts in sources.items():
        node = provider_nodes[provider]
        used = {
            bucket: amount - residual[bucket_nodes[bucket]][node]
            for bucket, amount in amounts.items()
            if amount > 0 and amount - residual[bucket_nodes[bucket]][node] > 0
        }
        if used:
            result[provider] = used
    return result
