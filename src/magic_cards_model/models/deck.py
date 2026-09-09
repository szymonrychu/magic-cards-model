"""Decklists and deck construction rules (CR 100.2, 100.4, 100.5).

A `Deck` is a decklist, not a shuffled pile: card names and how many of each,
plus a sideboard. Turning it into the physical cards a game plays with is
`Player.load_deck`, which resolves each name to a real printing.

The limits live in `DeckLimits` rather than being baked in, because they are a
property of the format, not of the game: constructed wants sixty cards and four
copies (CR 100.2a) with a fifteen-card sideboard (CR 100.4a), limited wants
forty and no copy limit at all (CR 100.2b).

Resolving names to printings is deliberately somebody else's job: whether a card
is a basic land, and whether its own text lifts the copy limit, is on the card,
so full legality needs a resolver. Every check runs in one place, `problems`,
so a decklist is never half-validated: building a `Deck` shapes it, and
`check_legality` is what says whether it may be played.
"""

import re
from collections.abc import Callable, Iterator
from typing import Self

from pydantic import BaseModel, Field

from .card import Card, Supertype

CardResolver = Callable[[str], Card]
"""Turns a card name into a printing. `tests.cards.card` is one."""

_ANY_NUMBER = re.compile(r"A deck can have any number of cards named", re.IGNORECASE)
_UP_TO_N = re.compile(r"A deck can have up to (\w+) cards named", re.IGNORECASE)
_NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "twelve": 12,
}


class DeckIllegal(ValueError):
    """A decklist that breaks its format's construction rules.

    Carries every problem found, not just the first, because a decklist is
    fixed all at once rather than one violation per attempt.
    """

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("; ".join(problems))


class DeckLimits(BaseModel):
    """One format's deck construction limits.

    Defaults are constructed (CR 100.2a, 100.4a). Every field is overridable,
    and `unlimited()` turns the whole thing off for a format that does not care.
    """

    min_mainboard: int = 60
    max_mainboard: int | None = None  # CR 100.5: no maximum outside Commander
    max_sideboard: int | None = 15
    max_copies: int | None = 4
    copy_limit_spans_sideboard: bool = True  # CR 100.4a
    basics_are_unlimited: bool = True  # CR 100.2a

    @classmethod
    def constructed(cls) -> "DeckLimits":
        """CR 100.2a: sixty cards, four copies, and CR 100.4a's fifteen-card sideboard."""
        return cls()

    @classmethod
    def limited(cls) -> "DeckLimits":
        """CR 100.2b: forty cards, no copy limit, and everything else is sideboard."""
        return cls(min_mainboard=40, max_copies=None, max_sideboard=None)

    @classmethod
    def unlimited(cls) -> "DeckLimits":
        """No limits at all, for scenarios that just need a pile of cards."""
        return cls(min_mainboard=0, max_sideboard=None, max_copies=None)

    def copies_allowed(self, card: Card) -> int | None:
        """How many copies of this card a deck may have, or None for any number.

        The four-copy limit is a default a card can override in its own text
        (CR 100.2a): a basic land is exempt, and so is anything printed with
        "A deck can have any number of cards named ...".
        """
        if self.max_copies is None:
            return None
        if self.basics_are_unlimited and Supertype.BASIC in card.supertypes:
            return None

        text = card.oracle_text or ""
        if _ANY_NUMBER.search(text):
            return None
        printed = _UP_TO_N.search(text)
        if printed is not None:
            word = printed.group(1).lower()
            if word in _NUMBER_WORDS:
                return _NUMBER_WORDS[word]
        return self.max_copies


class Deck(BaseModel):
    """A decklist: how many of each card in the deck and in the sideboard.

    Counts rather than a list of names, because that is how a decklist is
    written and because it makes the copy limit a lookup instead of a tally.
    """

    name: str = "Unnamed"
    mainboard: dict[str, int] = Field(default_factory=dict)
    sideboard: dict[str, int] = Field(default_factory=dict)
    limits: DeckLimits = Field(default_factory=DeckLimits)
    companion: str | None = None
    """A card named here, owned by the deck's player, from outside the game
    (CR 400.11a) - not part of the mainboard or the fifteen-card sideboard,
    and not counted toward either's size or copy limit. `problems` checks
    that it actually has the companion keyword and that its own printed
    condition (CR 702.139a) is fulfilled by `mainboard` (CR 702.139b: "your
    starting deck ... after you've set aside any sideboard cards"), read off
    its oracle text by `machines.companion.companion_condition_satisfied`
    rather than keyed to the card's name."""

    # -- shape -------------------------------------------------------------

    @property
    def mainboard_size(self) -> int:
        return sum(self.mainboard.values())

    @property
    def sideboard_size(self) -> int:
        return sum(self.sideboard.values())

    @property
    def size(self) -> int:
        """Deck and sideboard together, which is what the copy limit spans."""
        return self.mainboard_size + self.sideboard_size

    @property
    def card_names(self) -> list[str]:
        """Every distinct name in the decklist, mainboard first."""
        return list(self.mainboard) + [n for n in self.sideboard if n not in self.mainboard]

    def total_copies(self, card_name: str) -> int:
        """Copies across deck and sideboard, or just the deck if the format splits them."""
        copies = self.mainboard.get(card_name, 0)
        if self.limits.copy_limit_spans_sideboard:
            copies += self.sideboard.get(card_name, 0)
        return copies

    def mainboard_names(self) -> Iterator[str]:
        """Every mainboard card, one name per physical copy, in decklist order."""
        for card_name, count in self.mainboard.items():
            yield from [card_name] * count

    def sideboard_names(self) -> Iterator[str]:
        for card_name, count in self.sideboard.items():
            yield from [card_name] * count

    # -- legality ----------------------------------------------------------

    def _size_problems(self) -> list[str]:
        """Everything checkable without knowing what the cards are."""
        problems = [
            f"{count} copies of {card_name} is not a sane count"
            for board in (self.mainboard, self.sideboard)
            for card_name, count in board.items()
            if count < 1
        ]
        if self.mainboard_size < self.limits.min_mainboard:
            problems.append(
                f"a deck needs at least {self.limits.min_mainboard} cards, this one has "
                f"{self.mainboard_size}"
            )
        if (
            self.limits.max_mainboard is not None
            and self.mainboard_size > self.limits.max_mainboard
        ):
            problems.append(
                f"a deck may have at most {self.limits.max_mainboard} cards, this one has "
                f"{self.mainboard_size}"
            )
        if (
            self.limits.max_sideboard is not None
            and self.sideboard_size > self.limits.max_sideboard
        ):
            problems.append(
                f"a sideboard may have at most {self.limits.max_sideboard} cards, this one has "
                f"{self.sideboard_size}"
            )
        return problems

    def problems(self, resolve: CardResolver) -> list[str]:
        """Every construction rule this decklist breaks, resolver and all.

        The copy limit needs the printing, so this is where a five-of shows up
        and where twenty-four Mountains do not (CR 100.2a).
        """
        problems = self._size_problems()
        for card_name in self.card_names:
            try:
                card = resolve(card_name)
            except (KeyError, LookupError) as missing:
                problems.append(f"{card_name} is not a real card: {missing}")
                continue

            allowed = self.limits.copies_allowed(card)
            copies = self.total_copies(card_name)
            if allowed is not None and copies > allowed:
                problems.append(f"{copies} copies of {card.name}, which is limited to {allowed}")
        problems.extend(self.companion_problems(resolve))
        return problems

    def companion_problems(self, resolve: CardResolver) -> list[str]:
        """CR 702.139a/b: `self.companion`, checked against the mainboard alone.

        Imported lazily - `machines/` imports `models/`, so the reverse
        import only resolves at call time, the same convention every other
        `models/` file that reaches into `machines/` already follows.
        """
        if self.companion is None:
            return []
        from ..machines.companion import companion_condition_satisfied, has_companion

        try:
            companion_card = resolve(self.companion)
        except (KeyError, LookupError) as missing:
            return [f"companion {self.companion} is not a real card: {missing}"]
        if not has_companion(companion_card):
            return [f"{companion_card.name} has no companion ability (CR 702.139a)"]
        mainboard_cards = []
        for card_name in self.mainboard_names():
            try:
                mainboard_cards.append(resolve(card_name))
            except (KeyError, LookupError) as missing:
                return [f"{card_name} is not a real card: {missing}"]
        result = companion_condition_satisfied(
            companion_card, mainboard_cards, minimum_deck_size=self.limits.min_mainboard
        )
        if result.satisfied is not True:
            return [f"companion condition not fulfilled: {result.reason}"]
        return []

    def is_legal(self, resolve: CardResolver) -> bool:
        return not self.problems(resolve)

    def check_legality(self, resolve: CardResolver) -> Self:
        """Raise `DeckIllegal` listing every problem, or return the deck."""
        problems = self.problems(resolve)
        if problems:
            raise DeckIllegal(problems)
        return self
