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
from collections.abc import Iterable, Sequence
from enum import StrEnum
from itertools import combinations_with_replacement, product

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .card import Card, Color, Layout

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


class PaymentOption(BaseModel):
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


class ManaSymbol(BaseModel):
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


class ManaCost(BaseModel):
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


class ManaPayment(BaseModel):
    """One settled way to pay a cost: what each symbol was paid with.

    `options` lines up with `ManaCost.symbols`. `spend` is the mana taken out
    of the pool, of which `snow_spent` came from snow sources, and `life_paid`
    is what the payer still owes their life total (CR 118.13a).
    """

    options: tuple[PaymentOption, ...] = ()
    spend: dict[Color, int] = Field(default_factory=dict)
    snow_spent: dict[Color, int] = Field(default_factory=dict)
    life_paid: int = 0

    @property
    def mana_spent(self) -> int:
        return sum(self.spend.values())


# --------------------------------------------------------------------------
# The pool
# --------------------------------------------------------------------------

_Bucket = tuple[Color, bool]  # (colour, came from a snow source)


class ManaPool(BaseModel):
    """Mana floating in a player's pool.

    Mana knows whether it came from a snow source (CR 106.3), because `{S}`
    can only be paid with mana that did.
    """

    floating: dict[Color, int] = Field(default_factory=dict)
    snow: dict[Color, int] = Field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.floating.values())

    @property
    def is_empty(self) -> bool:
        return self.total == 0

    @property
    def snow_total(self) -> int:
        return sum(self.snow.values())

    def add(self, color: Color, amount: int = 1, snow: bool = False) -> None:
        if amount < 0:
            raise ValueError("cannot add a negative amount of mana")
        self.floating[color] = self.floating.get(color, 0) + amount
        if snow:
            self.snow[color] = self.snow.get(color, 0) + amount

    def add_all(self, colors: Iterable[Color], snow: bool = False) -> None:
        for color in colors:
            self.add(color, snow=snow)

    def empty(self) -> None:
        """Empty the pool, as happens when each step and phase ends."""
        self.floating = {}
        self.snow = {}

    # -- paying ------------------------------------------------------------

    def can_pay(self, cost: ManaCost, *, life_available: int = 0) -> bool:
        """True if some way of paying `cost` exists.

        `life_available` is what the payer may spend on Phyrexian symbols; it
        defaults to nothing, so a Phyrexian cost is only payable with mana
        unless the caller says the life is on the table.
        """
        return self.payment_for(cost, life_available=life_available) is not None

    def payment_for(
        self,
        cost: ManaCost,
        *,
        life_available: int = 0,
        choices: Sequence[int | None] | None = None,
    ) -> ManaPayment | None:
        """Work out a way to pay `cost`, or None if the pool cannot.

        The payer may pin any symbol's choice by passing `choices`, one index
        into that symbol's `options` per symbol, `None` to leave it open. What
        is left open is chosen for them: least life first, then least mana.
        """
        if cost.x_count:
            raise ValueError("resolve X with ManaCost.with_x before paying")
        if choices is not None and len(choices) != len(cost.symbols):
            raise ValueError(f"expected {len(cost.symbols)} choices, got {len(choices)}")

        best: ManaPayment | None = None
        for options in self._candidate_options(cost, choices):
            life = sum(option.life for option in options)
            if life > life_available:
                continue
            if best is not None and life > best.life_paid:
                continue
            settled = self._settle(options, life)
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
    ) -> "ManaPool":
        """Spend `cost` from the pool and return what is left floating.

        The pool is emptied of the mana spent, so the returned pool is this same
        object: the overflow that survives the payment.

        Life is *not* deducted here - the pool cannot reach a life total. The
        caller must apply `payment.life_paid` with `Player.lose_life`; use
        `payment_for` first when the cost has a Phyrexian symbol.
        """
        if payment is None:
            payment = self.payment_for(cost, life_available=life_available)
        if payment is None:
            raise ValueError(f"pool {self.floating} cannot pay {cost}")

        for color, amount in payment.spend.items():
            left = self.floating.get(color, 0) - amount
            if left < 0:
                raise ValueError(f"pool {self.floating} cannot pay {cost}")
            self.floating[color] = left
        for color, amount in payment.snow_spent.items():
            self.snow[color] = max(self.snow.get(color, 0) - amount, 0)

        self.floating = {color: n for color, n in self.floating.items() if n > 0}
        self.snow = {color: n for color, n in self.snow.items() if n > 0}
        return self

    # -- the search --------------------------------------------------------

    def _candidate_options(
        self, cost: ManaCost, choices: Sequence[int | None] | None
    ) -> Iterable[tuple[PaymentOption, ...]]:
        """Every distinct assignment of one payment option per symbol.

        Identical symbols are grouped and enumerated as multisets rather than
        as ordered tuples, so `{2/W}{2/W}{2/W}` is four candidates and not
        eight. A pinned choice collapses its symbol to one option.
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

    def _settle(self, options: Sequence[PaymentOption], life: int) -> ManaPayment | None:
        """Can the pool cover these fixed demands? If so, with what mana?"""
        generic = sum(option.generic for option in options)
        snow_needed = sum(1 for option in options if option.snow)
        colors: Counter[Color] = Counter(
            option.color for option in options if option.color is not None and not option.snow
        )

        buckets = self._buckets()
        # Most restrictive demand first: a fixed colour, then snow (any colour
        # but only from a snow source), then generic, which takes anything.
        demands: list[tuple[int, list[_Bucket]]] = [
            (count, [(color, False), (color, True)]) for color, count in colors.items()
        ]
        if snow_needed:
            demands.append((snow_needed, [b for b in buckets if b[1]]))
        if generic:
            demands.append((generic, list(buckets)))

        spent = _assign(buckets, demands)
        if spent is None:
            return None

        spend: Counter[Color] = Counter()
        snow_spent: Counter[Color] = Counter()
        for (color, is_snow), amount in spent.items():
            spend[color] += amount
            if is_snow:
                snow_spent[color] += amount
        return ManaPayment(
            options=tuple(options),
            spend=dict(spend),
            snow_spent=dict(snow_spent),
            life_paid=life,
        )

    def _buckets(self) -> dict[_Bucket, int]:
        """The pool split into snow and non-snow mana, plentiful first.

        Non-snow comes first so a payment that has a choice leaves snow mana
        floating for a `{S}` that may still need it.
        """
        buckets: dict[_Bucket, int] = {}
        for color, amount in self.floating.items():
            snow = min(self.snow.get(color, 0), amount)
            for is_snow, count in ((False, amount - snow), (True, snow)):
                if count:
                    buckets[(color, is_snow)] = count
        return dict(sorted(buckets.items(), key=lambda item: (item[0][1], -item[1])))


def _assign(
    buckets: dict[_Bucket, int], demands: list[tuple[int, list[_Bucket]]]
) -> dict[_Bucket, int] | None:
    """Match demands against buckets exactly, or return None if impossible.

    Each demand needs `count` mana and accepts only certain buckets, so this is
    a transportation problem. Greedy gets it wrong - a colour demand and a
    generic demand can want the same mana while a swap satisfies both - so it
    is solved as a max-flow: source -> demand -> allowed buckets -> sink, with
    the demand feasible exactly when the flow saturates the source.

    Ford-Fulkerson with a BFS augmenting path: O(V * E * F), where F is the
    mana value of the cost, V is at most 14 and E at most 100. The bucket order
    decides which mana is spent when several would do.
    """
    needed = sum(count for count, _ in demands)
    if needed == 0:
        return {}
    if needed > sum(buckets.values()):
        return None

    source, sink = "source", "sink"
    residual: dict[object, dict[object, int]] = {source: {}, sink: {}}
    for bucket, amount in buckets.items():
        residual.setdefault(bucket, {})[sink] = amount
        residual[sink][bucket] = 0
    for index, (count, allowed) in enumerate(demands):
        node = ("demand", index)
        residual[source][node] = count
        residual[node] = {source: 0}
        for bucket in allowed:
            if bucket in buckets:
                residual[node][bucket] = count
                residual.setdefault(bucket, {})[node] = 0

    flow = 0
    while True:
        parents: dict[object, object] = {source: source}
        queue = [source]
        while queue and sink not in parents:
            node = queue.pop(0)
            for neighbour, capacity in residual[node].items():
                if capacity > 0 and neighbour not in parents:
                    parents[neighbour] = node
                    queue.append(neighbour)
        if sink not in parents:
            break

        path: list[tuple[object, object]] = []
        node = sink
        while node != source:
            path.append((parents[node], node))
            node = parents[node]
        bottleneck = min(residual[a][b] for a, b in path)
        for a, b in path:
            residual[a][b] -= bottleneck
            residual[b][a] = residual[b].get(a, 0) + bottleneck
        flow += bottleneck

    if flow < needed:
        return None
    return {
        bucket: amount - residual[bucket][sink]
        for bucket, amount in buckets.items()
        if amount - residual[bucket][sink] > 0
    }
