import re
from collections.abc import Callable
from typing import Annotated

from pydantic import Field

from ...machines.triggers import (
    AbilityOnStack,
)
from ..card import (
    Color,
)
from ..card_state import (
    CardState,
)
from ..player import Player
from ..token import (
    TokenState,
)

#: Anything a spell can point at and then affect (CR 115.1).
Targetable = CardState | Player

#: What the stack holds. A spell is the card itself (CR 112.1); an ability is a
#: separate object with no card behind it (CR 405.1, 113.1c).
#:
#: A discriminated union on `state_class` (`CardState.state_class`,
#: `TokenState.state_class`, `AbilityOnStack.state_class`), not a plain
#: `CardState | AbilityOnStack`. `TokenState` needs its own explicit arm even
#: though it is a `CardState` subclass: pydantic builds `shared_zones`'s
#: schema from the field's declared type, an untagged union tries each arm's
#: *exact* schema against a `TokenState` instance, matches neither `CardState`
#: nor `AbilityOnStack`, and warns - `PydanticSerializationUnexpectedValue`,
#: once per arm per object, every time a dump reaches this field. Naming
#: `TokenState` as its own tagged arm gives pydantic an exact match to pick
#: instead of guessing. `CardState._resolve_token_subclass`'s wrap validator/
#: serializer pair (`models/card_state.py`) stays in place for the one field
#: that still needs it: `Player.zones` (`models/player.py`) is a bare
#: `list[CardState]`, not this union, and narrowing that pair to only this
#: union's shape would break `Player.zones`'s own `TokenState` round trip
#: silently.
StackObject = Annotated[CardState | TokenState | AbilityOnStack, Field(discriminator="state_class")]


#: The *unresolved* half of a protection phrase: a grant that names the quality
#: by a choice still to be made rather than by the quality itself. Mother of
#: Runes prints "gains protection from the color of your choice until end of
#: turn", and reading that sentence off her own printing yields the quality
#: "the color of your choice until end of turn", which names no colour and no
#: card type.
#:
#: CR 702.16a: "This quality is usually a color ... but can be any
#: characteristic value or information" - a choice not yet made is neither, so
#: the phrase is dropped here rather than carried as a quality nothing can ever
#: match. What Mother actually grants is written onto the *target* by
#: `machines/layers.py` as a resolved "Protection from red" line, and that line
#: is what `Game._effective_protection_qualities` reads.
#: CR 702.16i/702.16k's player quality: "protection from each of your
#: opponents" (Figure of Fable's Avatar) is shorthand for protection from
#: each opponent of the protected permanent's controller, and protection from
#: a player is protection from every object that player controls (and every
#: object they own that nobody else controls). Read by
#: `Game._player_quality_protects`, which knows who "your" is.
_EACH_OPPONENT_PROTECTION_QUALITY = re.compile(
    r"^each (?:of your )?opponents?$|^your opponents$", re.IGNORECASE
)


_ABILITY_WORD_PREFIX_RE = re.compile(r"^[A-Z][\w' -]*\s+[\u2014-]\s+")


#: CR 105.1: "There are five colors in the Magic game: white, blue, black, red,
#: and green." Colorless is not a sixth - CR 105.2c: "A colorless object has no
#: color" - so it is not a key here, and a source is matched against the colors
#: it has rather than against the ones it lacks.
_COLOR_WORDS: dict[str, Color] = {
    "white": Color.WHITE,
    "blue": Color.BLUE,
    "black": Color.BLACK,
    "red": Color.RED,
    "green": Color.GREEN,
}


#: "This permanent's"/`<card's own name>`'s power is equal to the number of
#: legendary `<type>` you control." - Super-Adaptoid's own CDA (CR 604.3a),
#: read here because `machines/layers.py::_QUALIFIER_COUNT_CDA_RE`'s own
#: `qualifier` group is a single bare word and cannot read the two-word
#: "legendary creatures" - see `Game._supplement_characteristics`'s own
#: docstring. `<type>` is any CR 205.2a card type word, not hardcoded to
#: "creatures" - Super-Adaptoid is the reported card, not the specification.
_LEGENDARY_TYPE_COUNT_POWER_RE = re.compile(
    r"^(?:this permanent's|[^.]+'s) power is equal to the number of "
    r"legendary (?P<type>[a-z]+) you control\.?$",
    re.IGNORECASE,
)


#: `Game.turn_counts` key for the energy counters a player removed from
#: themselves this turn to pay {E} (CR 107.14) - Izzet Generatorium's "if
#: you've paid or lost four or more {E} this turn".
ENERGY_PAID_OR_LOST = "energy_paid_or_lost"


#: CR 105.2a/105.2b: "monocolored" is exactly one of the five colors,
#: "multicolored" two or more - each a predicate on how many colours an
#: object has.
_COLOR_COUNT_QUALITIES: dict[str, Callable[[int], bool]] = {
    "monocolored": lambda count: count == 1,
    "multicolored": lambda count: count >= 2,
}


#: "permanents that were cast this turn" (Emrakul, the World Anew) / the
#: singular "permanent that was cast this turn" no printing uses yet - read
#: by the words rather than by the card, so a future printing that phrases
#: the singular still matches. Not a card type (CR 205.2a never lists
#: "permanent"), a colour, or CR 112.1's "spell" - its own temporal fact,
#: answered by `Game.was_cast_this_turn`.
_CAST_THIS_TURN_QUALITY_RE = re.compile(
    r"^permanents? that (?:were|was) cast this turn$", re.IGNORECASE
)


#: A static ability that stops players gaining life at all - Leyline of
#: Punishment's "Players can't gain life.", Sulfuric Vortex's and Rampaging
#: Ferocidon's "Players can't gain life." on the same one-sentence shape.
#:
#: This is the same *kind* of continuous effect as `_ACTIVATION_PROHIBITION_RE`
#: above and is here for the same reason: it changes no characteristic of any
#: object, so `machines/layers.py` has nothing to write - CR 613's layers are
#: for characteristics, control, and copiable values. CR 611.1 puts it in the
#: last of its three categories, "affects players or the rules of the game",
#: and CR 119.7 is where the rules read it back ("If an effect says that a
#: player can't gain life ..."). CR 604.2 and CR 611.3 bound it to while its
#: source is on the battlefield, which is why `life_gain_prohibited` rescans
#: the battlefield on every call rather than caching (CR 611.3a: not "locked
#: in").
#:
#: "Players" and "Each player" are both printed; a prohibition naming one
#: player specifically ("You can't gain life") is a different shape and is
#: deliberately not matched here - see `_LOOKS_LIKE_LIFE_GAIN_PROHIBITION_RE`.
_LIFE_GAIN_PROHIBITION_RE = re.compile(
    r"^(?:players|each player) can't gain life\.?$", re.IGNORECASE
)


#: ecl-T8: a static ability that stops players drawing cards at all -
#: Maralen of the Mornsong's "Players can't draw cards." CR 121.3: "if an
#: effect says that a player can't draw cards and another effect offers that
#: player the choice to draw a card, that player can't choose to do so" -
#: read the identical "while its source is on the battlefield" way
#: `_LIFE_GAIN_PROHIBITION_RE` reads Leyline of Punishment's own life-gain
#: twin, off `draw_prohibited` below rather than a persisted per-player flag,
#: since CR 604.2/611.3a bounds it to the source's own time on the
#: battlefield rather than "for the rest of the game".
_DRAW_PROHIBITION_RE = re.compile(r"^(?:players|each player) can'?t draw cards\.?$", re.IGNORECASE)

#: Mornsong Aria's own single-sentence combination of both prohibitions:
#: "Players can't draw cards or gain life." - read by both `draw_prohibited`
#: and `life_gain_prohibited`, since CR 608.2a's own text names two separate
#: "can't" effects (CR 101.2) in one sentence rather than two.
_DRAW_OR_LIFE_GAIN_PROHIBITION_RE = re.compile(
    r"^(?:players|each player) can'?t draw cards or gain life\.?$", re.IGNORECASE
)


#: Leyline of Punishment's, Sunspine Lynx's "Damage can't be prevented." and
#: Frenzied Baloth's "Combat damage can't be prevented." - CR 615.12, read by
#: `Game.damage_cant_be_prevented` while the permanent is on the battlefield.
_DAMAGE_CANT_BE_PREVENTED_RE = re.compile(
    r"^(?P<combat>combat )?damage can'?t be prevented\.?$", re.IGNORECASE
)


#: "You may spend mana as though it were mana of any color to activate
#: abilities of creatures you control." (Agatha's Soul Cauldron) and "... to
#: activate those abilities." (Drana and Linvala, whose "those abilities" are
#: the ones the sentence before it grants). CR 609.4b: "If an effect allows a
#: player to spend mana 'as though it were mana of any [type or color],' this
#: affects only how the player may pay a cost. It doesn't change that cost,
#: and it doesn't change what mana was actually spent to pay that cost." So
#: this is read where a payment is opened (`ManaSpend.any_color`) and nowhere
#: else. The subject is a plain "A, B and C" of card-type plurals "you
#: control", with CR 613's usual optional "other".
_SPEND_AS_ANY_COLOR_TO_ACTIVATE_RE = re.compile(
    r"^you may spend mana as though it were mana of any colou?r to activate "
    r"(?:abilities of (?P<other>other )?(?P<subjects>[a-z, ]+?) you control"
    r"|(?P<those>those abilities))\.?$",
    re.IGNORECASE,
)
