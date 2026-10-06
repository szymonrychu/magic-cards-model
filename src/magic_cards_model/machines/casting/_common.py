import re

from ...numbers import count_pattern

#: CR 702.166a: "'Bargain' means 'As an additional cost to cast this spell,
#: you may sacrifice an artifact, enchantment, or token.'" - the cost a
#: bargain line never prints, spelled out for `optional_additional_costs`.
BARGAIN_COST = "Sacrifice an artifact, enchantment, or token"


#: An optional additional-cost sentence this engine charges (CR 118.8b):
#: CR 701.59a's "you may collect evidence N" and a "you may reveal a
#: <quality> card from your hand" (CR 701.20a).
_OPTIONAL_COLLECT_EVIDENCE = re.compile(r"^you may (?P<cost>collect evidence \d+)$", re.IGNORECASE)
_OPTIONAL_REVEAL = re.compile(
    r"^you may (?P<cost>reveal an? [\w-]+ card from your hand)$", re.IGNORECASE
)
#: Celestial Reunion's own optional additional cost: "you may choose a
#: creature type and behold two creatures of that type." CR 118.8b's "you
#: may" plus CR 607.2d's own "choose a [value]" - the type named is not
#: fixed by the printed text (unlike `_OPTIONAL_REVEAL`'s "a Dragon card"),
#: so paying it needs both a type and the beheld creatures, which is why this
#: gets its own method (`behold_chosen_type_for_cost`) rather than sharing
#: `_optional_sentence`'s single-group "cost" read.
_OPTIONAL_BEHOLD_CHOSEN_TYPE = re.compile(
    r"^you may choose a creature type and behold (?P<count>\w+) creatures of that type$",
    re.IGNORECASE,
)
#: Dispelling Exhale's own plain "you may behold a Dragon" - CR 701.4a's
#: keyword action, a single unrestricted behold with no chosen type and no
#: count, the shape `_PHRASE_BEHOLD` already reads generally into a
#: `ComponentKind.BEHOLD` component (`Behold`, Champion of the Path and
#: friends). `_OPTIONAL_BEHOLD_CHOSEN_TYPE` above is Celestial Reunion's own
#: different shape - a type the caster picks rather than one the card
#: prints - which is why that one gets its own `count`/type reading and this
#: one needs only `Casting.behold_for_cost`'s plain `cost_component_for_
#: phrase` call, the same as `collect_evidence`/`reveal_for_cost`.
_OPTIONAL_BEHOLD = re.compile(r"^you may (?P<cost>behold an? [\w' -]+?)$", re.IGNORECASE)
#: Rottenmouth Viper's own "you may sacrifice any number of nonland
#: permanents" - CR 118.8b's optional additional cost, CR 107.1c's "any
#: number of" read the same zero-floor way `_COST_COUNT` (`machines/cost.py`)
#: now reads it for every other object cost. Paid by `Casting.
#: sacrifice_for_cost_reduction`, which is also what applies the linked "This
#: spell costs `<amount>` less to cast for each `<noun>` sacrificed this way"
#: sentence (`machines.cost.per_object_sacrifice_cost_reduction`) - a second
#: sentence, never part of this phrase itself.
_OPTIONAL_SACRIFICE_ANY_NUMBER = re.compile(
    r"^you may (?P<cost>sacrifice any number of [\w ,]+)$", re.IGNORECASE
)
#: March of Wretched Sorrow's (and every "March of ..." sibling's) "you may
#: exile any number of black cards from your hand" - CR 118.8b's optional
#: additional cost, the exile-from-hand twin of the sacrifice above. Paid by
#: `Casting.exile_for_cost_reduction`, which also applies the linked "This
#: spell costs {2} less to cast for each card exiled this way." sentence
#: (`machines.cost.per_object_exile_cost_reduction`).
_OPTIONAL_EXILE_ANY_NUMBER_FROM_HAND = re.compile(
    r"^you may (?P<cost>exile any number of [\w ]+ from your hand)$", re.IGNORECASE
)


#: CR 702.78a's cost, spelled out.
CONSPIRE_COST = "Tap two untapped creatures you control that each share a color with it"


#: CR 701.68a's own inline shape, printed inside the card's "As an additional
#: cost to cast this spell, ..." sentence rather than as a keyword-cost line,
#: which is why this is read off `additional_cost_phrases` rather than
#: `_keyword`. Three forms: optional "you may blight 1" (Requiting Hex),
#: mandatory "blight X" (Soul Immolation), and "blight 2 or pay {1}" (Wild
#: Unraveling), where CR 601.2b's announcement picks one of the two.
_BLIGHT_PHRASE = re.compile(
    rf"^(?P<optional>you may )?blight {count_pattern('n', x=True, article=False)}"
    r"(?: or pay (?P<instead>(?:\{[^{}]+\})+))?$",
    re.IGNORECASE,
)
