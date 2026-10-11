from __future__ import annotations

import re

from ...models.card import Color
from ..combat import (
    KEYWORDS_OUTSIDE_COMBAT,
    Keyword,
)

#: The five basic land types (CR 305.6) and the mana ability each one carries.
#: "An object with the land card type and a basic land type has the intrinsic
#: ability '{T}: Add [mana symbol]'", so gaining the type gains the ability.
BASIC_LAND_TYPES: dict[str, str] = {
    "Plains": "{T}: Add {W}.",
    "Island": "{T}: Add {U}.",
    "Swamp": "{T}: Add {B}.",
    "Mountain": "{T}: Add {R}.",
    "Forest": "{T}: Add {G}.",
}


#: "You control enchanted creature." (Ghastly Haunting, Soul Seizer's back
#: face) - an Aura's own static control change (CR 613.1b: "Layer 2:
#: Control-changing effects are applied"), for as long as the Aura is on the
#: battlefield attached to it (CR 611.3a). The subject is whatever the Aura
#: or Equipment is attached to, never a target.
_YOU_CONTROL_ATTACHED_RE = re.compile(
    r"^[Yy]ou control (?P<attachment>enchanted|equipped) "
    r"(?P<subject>artifact creature|creature|permanent|artifact|enchantment|land|planeswalker)\.?$"
)


#: The five colour words, as a printed condition spells them (CR 105.1).
_COLOR_WORDS: dict[str, Color] = {
    "white": Color.WHITE,
    "blue": Color.BLUE,
    "black": Color.BLACK,
    "red": Color.RED,
    "green": Color.GREEN,
}


#: The keyword grant shapes grant bare keywords from `machines/combat.py`'s
#: own vocabulary, since that is what a grant needs to be able to do anything
#: (`combat.has_keyword` is the only reader). Aerial Maneuver's "gains flying
#: **and first strike**" is why this is a whitelist and not `[a-z ]+` on its
#: own: "flying and first strike" is split into its keywords
#: (`_split_and_validate_keywords`) and granted as two real ones, never one
#: bogus ability. A keyword outside this set fails the match and falls to
#: `looks_like_unparsed_layer_effect` instead of silently granting the wrong
#: thing.
# Keywords no combat rule reads, and so absent from `machines/combat.py`'s own
# `Keyword` vocabulary, that a grant still has to be able to name -
# CR 702.12a's indestructible ("Indestructible is a static ability"; before it
# was here, "gains flying until end of turn" parsed and "gains indestructible
# until end of turn" did not, so a real grant silently did nothing) and
# CR 702.11a's hexproof, which Scion of Draco's colour-conditioned grant names.
# Named once, in `machines/combat.py`, because the reading vocabulary there
# needs the same two words.
#
# What a granted line is *read* with is a separate question, and the assumption
# that used to be written here - that `combat.has_keyword` adding the word it
# is asked about to the vocabulary is enough for a granted line to be found by
# whoever asks - was wrong wherever a line holds more than one keyword. It held
# only for a line that is nothing but the single keyword being asked about;
# `machines/combat.py::_reading_vocabulary` is what makes a shared line work,
# and `KeywordLineNotice` is what records a line it still cannot read whole.
#: CR 702.108a's prowess is a triggered keyword a static can hand out too
#: (Wizard's Staff's "Equipped creature has prowess.", Narset, Enlightened
#: Exile's "Creatures you control have prowess."): the granted "Prowess" line
#: is expanded into its trigger by `machines/keywords.
#: granted_keyword_triggered_abilities`, the way a granted "Ward {1}" is.
#: CR 702.79a's persist joins it the same way - Eirdu, Carrier of Dawn's own
#: "Each other nontoken creature you control has persist." and Rhys, the
#: Evermore's temporary "gains persist until end of turn" both reach the
#: identical `_TRIGGER_EXPANSIONS["persist"]` builder once the granted
#: "Persist" line is on the computed board, which is what `machines/
#: keywords.persist_return`'s own `keyword_confirmed` escape hatch is for -
#: see that function's docstring.
#: CR 702.93a's undying is persist's mirror and is granted the same way
#: (Undying Evil's "Target creature gains undying until end of turn.").
_GRANTABLE_TRIGGERED_KEYWORDS = frozenset({"prowess", "persist", "undying"})
_KNOWN_KEYWORDS = (
    frozenset(keyword.value for keyword in Keyword)
    | KEYWORDS_OUTSIDE_COMBAT
    | _GRANTABLE_TRIGGERED_KEYWORDS
)
#: The public name for the same whitelist, for a caller outside this module
#: that needs to validate a keyword name the identical way every shape here
#: does - `machines/effects.py`'s own keyword-*choice* riders ("gains your
#: choice of trample, hexproof, or haste"), whose "or"-joined list is not
#: the "and"/comma grammar `_split_and_validate_keywords` reads.
KNOWN_KEYWORDS = _KNOWN_KEYWORDS
