"""Card models mirroring the gameplay-relevant subset of the Scryfall card object.

Print, market, and collector fields are deliberately absent: no images, prices,
artists, marketplace ids, uris, finishes, promo or reprint flags, or flavor text.
What remains is what the rules and deckbuilding care about.

Legality is clamped to standard, pioneer, and modern.

Reference: https://scryfall.com/docs/api/cards
"""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict

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


class ScryfallModel(BaseModel):
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
    """A card as the rules see it, modern frame era onward."""

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
        words = _words_before_dash(self.front_type_line)
        return [s for s in Supertype if s.value in words]

    @property
    def types(self) -> list[Type]:
        """Card types on the front face, parsed out of `type_line`."""
        words = _words_before_dash(self.front_type_line)
        return [t for t in Type if t.value in words]

    @property
    def subtypes(self) -> list[str]:
        """Subtypes on the front face, right of the em dash in `type_line`."""
        _, _, right = self.front_type_line.partition("—")
        return right.split()

    @property
    def is_land(self) -> bool:
        return Type.LAND in self.types

    @property
    def is_creature(self) -> bool:
        return Type.CREATURE in self.types


def _words_before_dash(type_line: str) -> frozenset[str]:
    """Lowercased words left of the em dash. Module level: `set` is a Card field."""
    left, _, _ = type_line.partition("—")
    return frozenset(word.lower() for word in left.split())
