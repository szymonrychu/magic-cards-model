import re

from ...models.card import Type

#: "When you do, ..." - CR 603.12's reflexive opener. "When you don't, ..." is
#: the rule's other half ("triggers 'when [a player] [does or doesn't]' take
#: that action") and is admitted here so a card printing it is recognised
#: rather than silently read as an ordinary sentence.
_REFLEXIVE_OPENER = re.compile(r"^When you (?:do|don[’']?t),\s*(?P<effect>.+)$", re.IGNORECASE)


#: The card types a filter may name, as CR 205.2a spells them.
_CARD_TYPE_WORDS: dict[str, Type] = {
    "artifact": Type.ARTIFACT,
    "creature": Type.CREATURE,
    "enchantment": Type.ENCHANTMENT,
    "land": Type.LAND,
    "planeswalker": Type.PLANESWALKER,
}
