"""Card models mirroring the gameplay-relevant subset of the Scryfall card object.

Print, market, and collector fields are deliberately absent: no images, prices,
artists, marketplace ids, uris, finishes, promo or reprint flags, or flavor text.
What remains is what the rules and deckbuilding care about.

Legality is clamped to standard, pioneer, and modern.

Reference: https://scryfall.com/docs/api/cards
"""

from enum import StrEnum
from functools import cache
from uuid import UUID

from pydantic import ConfigDict

from ..snapshot import EngineModel

# --------------------------------------------------------------------------
# Rules enums
# --------------------------------------------------------------------------


class Color(StrEnum):
    WHITE = "W"
    BLUE = "U"
    BLACK = "B"
    RED = "R"
    GREEN = "G"
    COLORLESS = "C"


class Rarity(StrEnum):
    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    SPECIAL = "special"
    MYTHIC = "mythic"
    BONUS = "bonus"


class Supertype(StrEnum):
    """CR 205.4a: "The supertypes are basic, legendary, ongoing, snow, and
    world." Closed at five - verified this session, not from memory.

    `ONGOING` only ever appears on a Scheme card (Archenemy), which this
    engine's `Card`/`Zone` model does not represent - it is included here for
    completeness against the CR list, not because anything else reads it."""

    BASIC = "basic"
    LEGENDARY = "legendary"
    ONGOING = "ongoing"
    SNOW = "snow"
    WORLD = "world"


class Type(StrEnum):
    # Permanent types
    ARTIFACT = "artifact"
    BATTLE = "battle"
    CREATURE = "creature"
    ENCHANTMENT = "enchantment"
    LAND = "land"
    PLANESWALKER = "planeswalker"

    # Spell types
    INSTANT = "instant"
    SORCERY = "sorcery"

    # Combines with another type
    KINDRED = "kindred"


class Layout(StrEnum):
    """How the card is arranged. Changes how it is cast and how it behaves in play."""

    NORMAL = "normal"
    SPLIT = "split"
    FLIP = "flip"
    TRANSFORM = "transform"
    MODAL_DFC = "modal_dfc"
    MELD = "meld"
    LEVELER = "leveler"
    CLASS = "class"
    CASE = "case"
    SAGA = "saga"
    ADVENTURE = "adventure"
    PREPARE = "prepare"
    MUTATE = "mutate"
    PROTOTYPE = "prototype"
    BATTLE = "battle"
    PLANAR = "planar"
    SCHEME = "scheme"
    VANGUARD = "vanguard"
    TOKEN = "token"
    DOUBLE_FACED_TOKEN = "double_faced_token"
    EMBLEM = "emblem"
    AUGMENT = "augment"
    HOST = "host"
    REVERSIBLE_CARD = "reversible_card"


class Component(StrEnum):
    TOKEN = "token"
    MELD_PART = "meld_part"
    MELD_RESULT = "meld_result"
    COMBO_PIECE = "combo_piece"


class Legality(StrEnum):
    LEGAL = "legal"
    NOT_LEGAL = "not_legal"
    RESTRICTED = "restricted"
    BANNED = "banned"


# --------------------------------------------------------------------------
# Nested objects
# --------------------------------------------------------------------------


class ScryfallModel(EngineModel):
    """Base for every Scryfall-shaped model.

    Unknown keys are ignored, which both drops the print fields and keeps a new
    Scryfall field from breaking parsing.
    """

    model_config = ConfigDict(extra="ignore")


class Legalities(ScryfallModel):
    """Clamped to the three rotating-to-modern constructed formats.

    Scryfall's other formats (legacy, vintage, commander, pauper, the Arena-only
    ones) are dropped by the `extra="ignore"` config.
    """

    standard: Legality
    pioneer: Legality
    modern: Legality


class RelatedCard(ScryfallModel):
    """A card this one is closely related to - a token, meld part, or combo piece."""

    id: UUID
    component: Component
    name: str
    type_line: str


class CardFace(ScryfallModel):
    """One face of a multifaced card."""

    name: str
    mana_cost: str
    type_line: str | None = None
    oracle_text: str | None = None
    colors: list[Color] | None = None
    color_indicator: list[Color] | None = None
    cmc: float | None = None
    power: str | None = None
    toughness: str | None = None
    loyalty: str | None = None
    defense: str | None = None
    layout: Layout | None = None
    oracle_id: UUID | None = None


# --------------------------------------------------------------------------
# Card
# --------------------------------------------------------------------------


class Card(ScryfallModel):
    """A card as the rules see it, modern frame era onward.

    Immutable once loaded - a printing does not change - `frozen=True` makes
    that a pydantic guarantee rather than a convention nobody checks, and
    it is not just documentation: `machines/abilities.parse_abilities` and
    `machines/triggers.activated_abilities_of` memoise their parse of a
    printing's oracle text keyed on `Card.id`, on the strength of this being
    true. A `Card` that could still be mutated after construction would make
    that cache wrong the moment anything did, silently - see
    `tests/test_card.py::test_card_is_immutable`.
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    # Identity
    id: UUID
    oracle_id: UUID | None = None
    name: str

    # Characteristics
    type_line: str
    mana_cost: str | None = None
    cmc: float
    oracle_text: str | None = None
    colors: list[Color] | None = None
    color_identity: list[Color]
    color_indicator: list[Color] | None = None
    produced_mana: list[Color] | None = None
    keywords: list[str]
    power: str | None = None
    toughness: str | None = None
    loyalty: str | None = None
    defense: str | None = None
    hand_modifier: str | None = None
    life_modifier: str | None = None

    # Structure
    layout: Layout
    card_faces: list[CardFace] | None = None
    all_parts: list[RelatedCard] | None = None

    # Deckbuilding
    legalities: Legalities
    game_changer: bool | None = None
    rarity: Rarity
    set: str

    @property
    def front_type_line(self) -> str:
        """The type line of the front face only, without the `//` back half."""
        return self.type_line.split("//")[0].strip()

    @property
    def supertypes(self) -> list[Supertype]:
        """Supertypes on the front face, parsed out of `type_line`."""
        return supertypes_of(self.front_type_line)

    @property
    def types(self) -> list[Type]:
        """Card types on the front face, parsed out of `type_line`."""
        return types_of(self.front_type_line)

    @property
    def subtypes(self) -> list[str]:
        """Subtypes on the front face, right of the em dash in `type_line`."""
        return subtypes_of(self.front_type_line)

    @property
    def front_oracle_text(self) -> str:
        """The front face's rules text - the top-level field when it is
        populated, `front_face`'s own text otherwise.

        Split and adventure cards keep a meaningful top-level `oracle_text`
        (both halves, newline-joined); a `transform` or `modal_dfc` card
        leaves it null and puts each face's text on `card_faces` instead
        (`front_face`'s docstring), so this falls back the same way
        `Casting.base_cost` already does for `mana_cost`. A spell defaults to
        its front face up (CR 712.11) and stays there unless cast
        "transformed"/"converted" or played as an MDFC's land face - neither
        of which any caller here reaches, since both are read straight off
        `CardState.oracle_text` instead once a `CardState` exists. This is the
        `Card`-only fallback for `machines/targeting.py` and `machines/modes.py`,
        which parse a spell's targets and modes before a `CardState` for it
        exists.
        """
        printed = self.oracle_text or ""
        if not printed and self.front_face is not None:
            return self.front_face.oracle_text or ""
        return printed

    @property
    def is_land(self) -> bool:
        return Type.LAND in self.types

    @property
    def is_creature(self) -> bool:
        return Type.CREATURE in self.types

    @property
    def front_face(self) -> "CardFace | None":
        """This card's front face, or None for a single-faced card (CR 712.2a,
        712.3a).

        Scryfall leaves the top-level `power`, `toughness`, `oracle_text` and
        `colors` null for a `transform` or `modal_dfc` card and puts each
        face's own values on `card_faces` instead - the top-level fields exist
        for split, adventure and (usually) meld cards, where the top-level
        value is still meaningful. `front_face` is the fallback callers reach
        for when a top-level field comes back empty on a card that has faces:
        CR 712.8a makes the front face this card's only characteristics
        outside the battlefield and stack, and CR 712.8d makes it the same
        while a double-faced permanent has its front face up, so "the front
        face when there is one" is the right default nearly everywhere -
        `CardState` layers a land face or a flipped face on top of it where
        CR 712.8f or CR 712.12 says otherwise.
        """
        return self.card_faces[0] if self.card_faces else None

    @property
    def back_face(self) -> "CardFace | None":
        """This card's back face, or None when it has fewer than two faces
        (CR 712.1, 712.8e).

        The face a transformed permanent shows: CR 701.27a turns the permanent
        over "so that its other face is up", CR 701.27g names the result a
        "transformed permanent", and CR 712.8e is what it then reads as - "while
        a nonmodal double-faced permanent has its back face up, it has only the
        characteristics of its back face". The one exception CR 712.8e itself
        carves out is mana value, which is "calculated using the mana cost of
        its front face" (CR 202.3b) - a back face prints no mana cost at all, so
        a caller reading mana value must not read this face for it.

        `CardState.up_face` is the only place the choice between this and
        `front_face` is made; nothing off the battlefield ever reaches it,
        since CR 712.8a gives a double-faced card in every other zone only its
        front face's characteristics.
        """
        faces = self.card_faces or []
        return faces[1] if len(faces) > 1 else None

    @property
    def land_face(self) -> "CardFace | None":
        """This card's land face, or None (CR 712.12).

        `is_land` only ever reads the front face - correct while the card sits
        anywhere but the battlefield or stack (CR 712.8a) - so it says False
        for a modal double-faced card like Valakut Awakening // Valakut
        Stoneforge, whose land is the *back* face. This is the mirror read
        `Casting.base_cost` already needed for an MDFC's blank top-level
        `mana_cost`: the land's own characteristics live only on `card_faces`,
        so a caller choosing which face to play (CR 712.12) has to look there.

        Only a `modal_dfc` has one. CR 712.12 lets a player play "a modal
        double-faced card" as a land, and CR 712.1 makes nonmodal (transform)
        and meld cards different kinds: Treasure Map // Treasure Cove's land
        back is reached only by transforming (CR 712.2), never by a land drop.
        """
        if self.layout is not Layout.MODAL_DFC:
            return None
        for face in self.card_faces or []:
            if face.type_line and "land" in _words_before_dash(face.type_line):
                return face
        return None

    @property
    def prepare_spell(self) -> "CardFace | None":
        """This card's inset "prepare spell" face, or None (CR 722.1, 722.2a).

        "The inset frame of a preparation card is called a 'prepare spell.'"
        Only a `Layout.PREPARE` card has one, and Scryfall's own shape for it
        is the ordinary two-face `card_faces` list every other multifaced
        layout uses - `card_faces[0]` the front (a normal permanent, cast and
        played like any other), `card_faces[1]` the inset spell. CR 722.3:
        "Preparation cards can't be cast using the alternative characteristics
        found within their inset frames" - this is read only to build a
        CR 722.3c exile copy from, never to cast the printing itself.
        """
        if self.layout is not Layout.PREPARE:
            return None
        return self.back_face


def _words_before_dash(type_line: str) -> frozenset[str]:
    """Lowercased words left of the em dash. Module level: `set` is a Card field."""
    left, _, _ = type_line.partition("—")
    return frozenset(word.lower() for word in left.split())


def types_of(type_line: str) -> list[Type]:
    """Card types parsed out of a single face's `type_line`.

    Shared by `Card.types` (the front face) and any caller reading a single
    `CardFace.type_line` directly - a modal double-faced card's chosen face
    (CR 712.8f) needs the same parse, not just the front one.
    """
    words = _words_before_dash(type_line)
    return [t for t in Type if t.value in words]


@cache
def _supertypes_of_cached(type_line: str) -> tuple[Supertype, ...]:
    """The precomputed set `supertypes_of` reads from, one entry per distinct
    `type_line` ever seen.

    A supertype is a printed constant (CR 205.4a) - the same `type_line`
    string always parses to the same answer - so this is memoised on the
    string itself rather than on a `Card`: two different printings that happen
    to share a type line (any two copies of the same land, from different
    sets) get the same cache hit, correctly, because the question was never
    about the printing's identity. `is_snow_source` (`machines/cost.py`) is
    the caller this matters for: a real 18-source board asked it 162,815 times
    answering one `{3}{W}{W}` affordability question, re-splitting the same
    handful of type lines every time before this cache existed.
    """
    words = _words_before_dash(type_line)
    return tuple(s for s in Supertype if s.value in words)


def supertypes_of(type_line: str) -> list[Supertype]:
    """Supertypes parsed out of a single face's `type_line` (CR 205.4a).

    Shared by `Card.supertypes` (the front face) and `CardState.supertypes`,
    which reads whichever face is up (CR 712.8d, 712.8e, 712.8f) - the same
    split `types_of` already makes.

    Always returns a fresh list: the parse itself is memoised
    (`_supertypes_of_cached`), but nothing here hands a caller the cached
    tuple to mutate.
    """
    return list(_supertypes_of_cached(type_line))


def subtypes_of(type_line: str) -> list[str]:
    """Subtypes parsed out of a single face's `type_line`, right of the em dash."""
    _, _, right = type_line.partition("—")
    return right.split()
