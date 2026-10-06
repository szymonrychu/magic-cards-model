import re

from ...models.card import Type
from ...numbers import (
    count_pattern,
)

#: `CostComponent.counter_kind` for a cost that names no kind - Glen Elendra
#: Guardian's "Remove a counter from this creature" (CR 122.1: any counter
#: of any kind pays it).
ANY_COUNTER_KIND = "any"


#: The plain positive-inclusion shape - Ral, Monsoon Mage's own front-face
#: static "Instant and sorcery spells you cast cost {1} less to cast.",
#: Goblin Electromancer's identical wording. One or two type words, joined by
#: "and" the way the templating always prints a two-type qualifier.
_TYPE_WORDS: dict[str, Type] = {
    "creature": Type.CREATURE,
    "instant": Type.INSTANT,
    "sorcery": Type.SORCERY,
    "artifact": Type.ARTIFACT,
    "enchantment": Type.ENCHANTMENT,
    "planeswalker": Type.PLANESWALKER,
    "land": Type.LAND,
}


#: "Pay 2 life" and CR 107.3a's "Pay X life" (Krumar Initiate), whose amount is
#: the X announced as the cost is paid.
_PHRASE_PAY_LIFE = re.compile(rf"^pay {count_pattern('amount', x=True)} life$", re.IGNORECASE)


#: Connector words a comma-and-"or" (or "and") list of card types leaves
#: between its items - "an artifact, creature, or land" - that name nothing
#: themselves and are skipped rather than treated as an unread word.
#:
#: "other" joins them for the same reason: CR 201.4's self-exclusion word,
#: printed on a cost that names a count of cards rather than "this card"
#: itself - Escape's own template (CR 702.138a), "Exile five **other** cards
#: from your graveyard" (Cling to Dust, Uro, Titan of Nature's Wrath). It adds
#: no restriction on *which* cards may pay: by the time this cost is paid, the
#: escaping card itself is on the stack (CR 601.2a moved it there before
#: CR 601.2h ever pays anything), not sitting in the graveyard pile this
#: exiles from, so "other" is satisfied by the zone alone and the word is
#: correctly a no-op rather than an unread one.
_QUALITY_CONNECTORS = {"or", "and", "other"}
