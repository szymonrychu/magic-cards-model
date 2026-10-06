import re
from typing import Any

from ...data.subtypes import canonical_subtype
from ...models.card import Card, Color, Supertype, Type
from ...models.mana import (
    ManaCost,
)
from ...models.zone import Zone
from ...numbers import (
    VariableX,
    count_pattern,
    parse_amount,
    parse_count,
)
from .components import (
    ActivatedAbilityGroupDiscount,
    AlternativeCostOffer,
    CardRequirement,
    ComponentKind,
    CostComponent,
    CostModifierEffect,
    StaticFreeCastGrant,
    TotalCost,
)

_QUALIFIER_EXCLUDES: dict[str, Type] = {
    "Noncreature": Type.CREATURE,
    "Nonartifact": Type.ARTIFACT,
    "Nonland": Type.LAND,
    "Noninstant": Type.INSTANT,
    "Nonsorcery": Type.SORCERY,
    "Nonenchantment": Type.ENCHANTMENT,
    "Nonplaneswalker": Type.PLANESWALKER,
}

_FLAT_COST_INCREASE = re.compile(
    r"(?:(?P<qualifier>Noncreature|Nonartifact|Nonland|Noninstant|Nonsorcery|"
    r"Nonenchantment|Nonplaneswalker) )?[Ss]pells? cost \{(?P<amount>\d+)\} more to cast\."
)
#: Disruptor Flute's own tax, scoped by the card name it chose as it entered
#: (CR 614.12a) rather than by a card type. Matched ahead of
#: `_FLAT_COST_INCREASE` so the qualifier is never dropped: that pattern wants
#: "spells cost {N} more" contiguously and so cannot read this line at all,
#: which is precisely why the increase used to be recorded as an unparsed
#: notice and applied to nothing.
_NAMED_COST_INCREASE = re.compile(
    r"[Ss]pells with the chosen name cost \{(?P<amount>\d+)\} more to cast\."
)
#: Gathering Stone's own discount, `_NAMED_COST_INCREASE`'s twin scoped by a
#: CR 614.12a creature-type choice instead of a card name - "Spells you cast
#: of the chosen type cost `{N}` less to cast." Urza's Incubator (Modern-legal,
#: proof printing) prints the identical CR 614.12a choice two words
#: narrower and one word wider: "`Creature` spells [no `you cast`] of the
#: chosen type cost `{N}` less to cast" - `creature_only` is the first
#: difference (only a creature spell of the type qualifies, not any spell
#: with the subtype); the missing "you cast" is the second, read as
#: `scoped_to_caster=False` below rather than a fixed True, since CR 601.2f
#: cost reductions apply exactly to whoever the printed sentence names as
#: casting, and this sentence names nobody - it discounts the spell for
#: *whichever* player casts it, not only this permanent's own controller.
_CHOSEN_TYPE_COST_DECREASE = re.compile(
    r"(?P<creature_only>[Cc]reature )?[Ss]pells(?P<scoped> you cast)? of the chosen type cost "
    r"\{(?P<amount>\d+)\} less to cast\."
)
#: Thalia, the Survivor's tax, and Grand Arbiter Augustin IV's own
#: unqualified "Spells your opponents cast cost {1} more to cast." - the
#: opponent-scoped mirror of `_FLAT_COST_INCREASE`. Matched ahead of it for
#: the same reason `_NAMED_COST_INCREASE` is: "spells ... your opponents
#: cast cost {N} more" is not contiguous "spells cost {N} more", so the
#: qualifier and the tax would otherwise be silently dropped rather than
#: read, the exact DDR#978 shape this permanent's own docstring names.
_OPPONENT_COST_INCREASE = re.compile(
    r"(?:(?P<qualifier>Noncreature|Nonartifact|Nonland|Noninstant|Nonsorcery|"
    r"Nonenchantment|Nonplaneswalker) )?[Ss]pells your opponents cast cost "
    r"\{(?P<amount>\d+)\} more to cast\."
)
#: Pursued Whale's own tax: `OPPONENT_TYPE_INCREASE`'s sentence with a "that
#: target this <noun>" relative clause between "cast" and "cost".
_TARGETING_THIS_COST_INCREASE = re.compile(
    r"[Ss]pells your opponents cast that target this \w+ cost "
    r"\{(?P<amount>\d+)\} more to cast\."
)
_PER_SPELL_COST_INCREASE = re.compile(
    r"Each spell a player casts costs \{(?P<amount>\d+)\} more to cast for each "
    r"other spell that player has cast this turn\."
)
_SPELL_COST_FLOOR = re.compile(
    r"(?P<condition>As long as this \w+ is untapped, )?"
    r"[Ee]ach spell that would cost less than (?P<threshold>\w+) mana to cast "
    r"costs (?P<total>\w+) mana to cast\."
)

#: The Medallion cycle's own template - one color, one flat amount. Reads
#: through the wider `_COLOR_WORDS` defined below (with "colorless"), which
#: this regex's own closed color alternation can never actually produce -
#: it exists once, past `_TYPE_WORDS`, so both this and `_requirement`'s
#: colorless-aware quality reading share one source of truth.
_COLOR_COST_DECREASE = re.compile(
    r"(?P<color>White|Blue|Black|Red|Green) spells you cast cost \{(?P<amount>\d+)\} "
    r"less to cast\.",
    re.IGNORECASE,
)

#: The exclusion-qualified shape - Artist's Talent's own level-2 "Noncreature
#: spells you cast cost {1} less to cast." - matched before the plain
#: inclusion shape below so its "Non..." prefix is not mistaken for the bare
#: type word inside it (though the two never actually collide: `\bcreature\b`
#: cannot match inside the single unbroken token "Noncreature").
_NONTYPE_COST_DECREASE = re.compile(
    r"(?P<qualifier>Noncreature|Nonartifact|Nonland|Noninstant|Nonsorcery|"
    r"Nonenchantment|Nonplaneswalker) spells you cast cost \{(?P<amount>\d+)\} "
    r"less to cast\.",
)


_TYPE_COST_DECREASE = re.compile(
    r"\b(?P<types>(?:Creature|Instant|Sorcery|Artifact|Enchantment|Planeswalker|Land)"
    r"(?: and (?:Creature|Instant|Sorcery|Artifact|Enchantment|Planeswalker|Land))?) "
    r"spells you cast cost \{(?P<amount>\d+)\} less to cast"
    # Mindsplice Apparatus: "... for each oil counter on this artifact."
    r"(?: for each (?P<each>[^.]+))?\.",
    re.IGNORECASE,
)

#: "`<type list>` spells you cast cost `{X}` less to cast, where X is
#: equipped creature's power." - Glamdring, Foe-hammer's own static. A
#: dynamic sibling of `_TYPE_COST_DECREASE` above: that regex only ever reads
#: a literal digit for the discount (`{(?P<amount>\d+)}`), which cannot
#: match a printed `{X}` at all, so this magnitude - CR 301.5a's "equipped
#: creature", recomputed fresh every time a cost is determined (CR 611.3a) -
#: needs its own shape rather than a wider `\d+` that would also start
#: matching a bare literal "X" typo no printing actually has.
_TYPE_COST_DECREASE_EQUIPPED_POWER_RE = re.compile(
    r"\b(?P<types>(?:Creature|Instant|Sorcery|Artifact|Enchantment|Planeswalker|Land)"
    r"(?: and (?:Creature|Instant|Sorcery|Artifact|Enchantment|Planeswalker|Land))?) "
    r"spells you cast cost \{X\} less to cast, where X is equipped creature'?s power\.?$",
    re.IGNORECASE,
)

#: Doran, Besieged by Time: "Each creature spell you cast with toughness
#: greater than its power costs {1} less to cast." - a `TYPE_DECREASE` on
#: creature spells, further filtered by the spell's own P/T comparison
#: (`CostModifierEffect.requires_toughness_greater_than_power`) rather than by
#: a card-type/subtype/keyword. "Each" is CR 601.2f's plain "spells you cast",
#: not a per-instance multiplier - Doran taxes every qualifying spell the
#: flat amount, it never scales with how many are cast.
_CREATURE_SPELL_TOUGHNESS_OVER_POWER_COST_DECREASE_RE = re.compile(
    r"^each creature spell you cast with toughness greater than its power "
    r"costs \{(?P<amount>\d+)\} less to cast\.?$",
    re.IGNORECASE,
)

#: "The first instant or sorcery spell you cast each turn costs {3} less to
#: cast." (Melek, Reforged Researcher), "The first creature spell you cast each
#: turn costs {2} less to cast." (Conduit of Ruin's shape), "The first
#: instant or sorcery spell you cast each turn costs {U} (or {1}) less to cast
#: for each land you control with a flood counter on it." (Eluge, the
#: Shoreless Sea), Radagast of Rhosgobel's own "The first creature spell
#: you cast each turn costs {2} less to cast and can be cast as though it had
#: flash.", and Momo, Friendly Flier's own "The first **non-Lemur** creature
#: spell **with flying** you cast **during each of your turns** costs {1}
#: less to cast." - a `TYPE_DECREASE` limited to the caster's first spell of
#: the named types this turn, generic or one colored symbol per unit, with an
#: optional leading subtype exclusion (`excludes_subtype`, read against the
#: spell's own `CardState.subtypes` the identical way `_SUBTYPE_COST_
#: DECREASE`'s positive form already is), an optional trailing keyword
#: requirement (`requires_keyword`, `combat.has_keyword`), an optional "for
#: each" count, an optional trailing flash grant (`grants_flash`, read by
#: `Game.has_first_spell_flash_grant`), and the turn window spelled either
#: "each turn" or "during each of your turns" - the same CR 500.7 turn Momo's
#: own wording names explicitly rather than leaving implicit.
_FIRST_SPELL_EACH_TURN_COST_DECREASE = re.compile(
    r"^The first (?:non-(?P<excludes_subtype>[A-Za-z]+) )?"
    r"(?P<types>(?:Creature|Instant|Sorcery|Artifact|Enchantment|Planeswalker)"
    r"(?: or (?:Creature|Instant|Sorcery|Artifact|Enchantment|Planeswalker))?) spell"
    r"(?: with (?P<keyword>[a-z]+))? you cast "
    r"(?:each turn|during each of your turns) costs \{(?P<symbol>\d+|[WUBRG])\}"
    r"(?: \(or \{1\}\))? less to cast"
    r"(?: for each (?P<each>[^.]+))?"
    r"(?P<flash> and can be cast as though it had flash)?\.$",
    re.IGNORECASE,
)

#: The unqualified, symbol-written shape - Aang, Master of Elements' "Spells you
#: cast cost {W}{U}{B}{R}{G} less to cast. (This can reduce generic costs.)" and
#: The Immortal Sun's "Spells you cast cost {1} less to cast." Any run of plain
#: generic, coloured or colourless symbols; a hybrid symbol is left unread
#: (CR 118.7e has the payer choose a half, which nothing here asks). A trailing
#: reminder is allowed, a trailing rider is not - "This effect reduces only
#: the amount of colored mana you pay." is a different reduction (no CR 118.7b
#: spill into generic), and anything else after the full stop is unread text.
_SYMBOL_COST_DECREASE = re.compile(
    r"^Spells you cast cost (?P<symbols>(?:\{(?:\d+|[WUBRGC])\})+) less to cast\."
    r"(?:\s*\([^)]*\))?$",
    re.IGNORECASE,
)

#: "Spells you cast from `<zone>` cost {N} less to cast." / "... from
#: anywhere other than `<zone>` ..." - Bilbo, Thief in the Night.
_ZONE_COST_DECREASE = re.compile(
    r"^Spells you cast from (?P<other>anywhere other than )?(?P<zone>your hand|your graveyard"
    r"|exile|your library) cost \{(?P<amount>\d+)\} less to cast\.$",
    re.IGNORECASE,
)
_COST_ZONE_WORDS: dict[str, Zone] = {
    "your hand": Zone.HAND,
    "your graveyard": Zone.GRAVEYARD,
    "exile": Zone.EXILE,
    "your library": Zone.LIBRARY,
}

#: The subtype shape - Goblin Warchief's own "Goblin spells you cast cost {1}
#: less to cast." One capitalised word that `canonical_subtype` places in
#: CR 205.3's list; a card type or a color word never reaches here, because
#: the two shapes above are tried first.
_SUBTYPE_COST_DECREASE = re.compile(
    r"(?:^|(?<=[.\n]))\s*(?P<subtype>[A-Z][a-z'-]+) spells you cast cost \{(?P<amount>\d+)\} "
    r"less to cast\."
)

#: Anything that talks about a spell costing more, or a floor on what a spell
#: would cost, whether or not the shapes above could read it - Grand Arbiter
#: Augustin IV's "Spells your opponents cast cost {1} more to cast" mentions
#: an increase but is controller-relative, a shape none of the above parse.
_COST_MODIFIER_SIGNAL = re.compile(r"more to cast|would cost .* mana to cast")

#: The board-wide *decrease* signal, kept narrower and separate from
#: `_COST_MODIFIER_SIGNAL`: it is anchored on "spells you cast", the
#: Medallion/Electromancer grant's own grammatical subject, so it never fires
#: on a spell's *own* self-reduction sentence (Emrakul's "This spell costs
#: [N] less to cast for each card type...", already `Game.cost_reduction_for`'s
#: job, not this one) even after that spell resolves onto the battlefield and
#: its printed text is scanned here again.
_COST_DECREASE_SIGNAL = re.compile(
    r"spells you cast cost (?:\{(?:\d+|[WUBRGC])\})+ less to cast", re.IGNORECASE
)


#: A static cost modifier's trailing condition - Gran-Gran's "Noncreature
#: spells you cast cost {1} less to cast as long as there are three or more
#: Lesson cards in your graveyard."
_AS_LONG_AS_TAIL = re.compile(r"^(?P<base>.+?) as long as (?P<condition>[^.]+)\.?$", re.DOTALL)


def cost_modifier_effect(text: str) -> CostModifierEffect | None:
    """Read one static cost-modifying sentence off a permanent's oracle text.

    Returns `None` if nothing here matches a recognised shape - which is not
    the same as "this text has nothing to say about costs"; that distinction
    is `looks_like_unparsed_cost_modifier`'s job, kept separate so a numeral
    this engine cannot read (an out-of-range word, say) is reported rather
    than silently treated as "no effect here".

    A sentence that is a recognised shape followed by "as long as
    `<condition>`" reads as that shape with `condition` set, provided
    `condition_is_readable` recognises the condition - an unreadable one
    leaves the whole sentence unread (and so reported), never applied
    unconditionally.
    """
    from ...models.game import condition_is_readable

    effect = _unconditional_cost_modifier_effect(text)
    if effect is not None:
        return effect
    tail = _AS_LONG_AS_TAIL.fullmatch(text.strip())
    if tail is None or not condition_is_readable(tail.group("condition")):
        return None
    base = _unconditional_cost_modifier_effect(f"{tail.group('base').strip()}.")
    if base is None:
        return None
    return base.model_copy(update={"condition": tail.group("condition").strip()})


def _unconditional_cost_modifier_effect(text: str) -> CostModifierEffect | None:
    """`cost_modifier_effect`'s recognised shapes, with no condition."""
    match = _NAMED_COST_INCREASE.search(text)
    if match is not None:
        return CostModifierEffect(
            kind=CostModifierKind.NAMED_INCREASE, amount=int(match.group("amount"))
        )
    match = _CHOSEN_TYPE_COST_DECREASE.search(text)
    if match is not None:
        return CostModifierEffect(
            kind=CostModifierKind.CHOSEN_TYPE_DECREASE,
            amount=int(match.group("amount")),
            creature_only=match.group("creature_only") is not None,
            scoped_to_caster=match.group("scoped") is not None,
        )
    match = _TARGETING_THIS_COST_INCREASE.search(text)
    if match is not None:
        return CostModifierEffect(
            kind=CostModifierKind.TARGETING_THIS_INCREASE, amount=int(match.group("amount"))
        )
    match = _OPPONENT_COST_INCREASE.search(text)
    if match is not None:
        qualifier = match.group("qualifier")
        return CostModifierEffect(
            kind=CostModifierKind.OPPONENT_TYPE_INCREASE,
            amount=int(match.group("amount")),
            excludes_type=_QUALIFIER_EXCLUDES.get(qualifier) if qualifier else None,
        )
    match = _FLAT_COST_INCREASE.search(text)
    if match is not None:
        qualifier = match.group("qualifier")
        return CostModifierEffect(
            kind=CostModifierKind.FLAT_INCREASE,
            amount=int(match.group("amount")),
            excludes_type=_QUALIFIER_EXCLUDES.get(qualifier) if qualifier else None,
        )
    match = _PER_SPELL_COST_INCREASE.search(text)
    if match is not None:
        return CostModifierEffect(
            kind=CostModifierKind.PER_SPELL_INCREASE, amount=int(match.group("amount"))
        )
    match = _SPELL_COST_FLOOR.search(text)
    if match is not None:
        threshold = parse_count(match.group("threshold"))
        total = parse_count(match.group("total"))
        if threshold is None or total is None:
            return None
        return CostModifierEffect(
            kind=CostModifierKind.FLOOR,
            amount=total,
            requires_untapped=match.group("condition") is not None,
        )
    match = _ZONE_COST_DECREASE.fullmatch(text.strip())
    if match is not None:
        zone = _COST_ZONE_WORDS[match.group("zone").lower()]
        return CostModifierEffect(
            kind=CostModifierKind.ZONE_DECREASE,
            amount=int(match.group("amount")),
            from_zone=None if match.group("other") else zone,
            not_from_zone=zone if match.group("other") else None,
        )
    match = _SYMBOL_COST_DECREASE.fullmatch(text.strip())
    if match is not None:
        reduction = match.group("symbols").upper()
        return CostModifierEffect(
            kind=CostModifierKind.SYMBOL_DECREASE,
            amount=ManaCost.parse(reduction).converted,
            reduction=reduction,
        )
    match = _COLOR_COST_DECREASE.search(text)
    if match is not None:
        return CostModifierEffect(
            kind=CostModifierKind.COLOR_DECREASE,
            amount=int(match.group("amount")),
            applies_to_color=_COLOR_WORDS[match.group("color").lower()],
        )
    match = _NONTYPE_COST_DECREASE.search(text)
    if match is not None:
        return CostModifierEffect(
            kind=CostModifierKind.TYPE_DECREASE,
            amount=int(match.group("amount")),
            excludes_type=_QUALIFIER_EXCLUDES[match.group("qualifier")],
        )
    match = _FIRST_SPELL_EACH_TURN_COST_DECREASE.fullmatch(text.strip())
    if match is not None:
        words = [word.strip().lower() for word in match.group("types").split(" or ")]
        types = tuple(_TYPE_WORDS[word] for word in words if word in _TYPE_WORDS)
        each = match.group("each")
        excludes_word = match.group("excludes_subtype")
        excludes_subtype = canonical_subtype(excludes_word) if excludes_word else None
        if (
            types
            and (each is None or _for_each_count_is_readable(each))
            and (excludes_word is None or excludes_subtype is not None)
        ):
            symbol = match.group("symbol")
            colored = None if symbol.isdigit() else _SYMBOL_COLORS[symbol.upper()]
            return CostModifierEffect(
                kind=CostModifierKind.TYPE_DECREASE,
                amount=int(symbol) if symbol.isdigit() else 1,
                applies_to_types=types,
                first_each_turn=True,
                colored=colored,
                per_each=each.strip() if each is not None else None,
                grants_flash=match.group("flash") is not None,
                excludes_subtype=excludes_subtype,
                requires_keyword=(match.group("keyword") or "").lower() or None,
            )
    match = _TYPE_COST_DECREASE_EQUIPPED_POWER_RE.search(text)
    if match is not None:
        words = [word.strip().lower() for word in match.group("types").split(" and ")]
        types = tuple(_TYPE_WORDS[word] for word in words if word in _TYPE_WORDS)
        if types:
            return CostModifierEffect(
                kind=CostModifierKind.TYPE_DECREASE,
                amount=0,
                applies_to_types=types,
                per_equipped_power=True,
            )
    match = _CREATURE_SPELL_TOUGHNESS_OVER_POWER_COST_DECREASE_RE.fullmatch(text.strip())
    if match is not None:
        return CostModifierEffect(
            kind=CostModifierKind.TYPE_DECREASE,
            amount=int(match.group("amount")),
            applies_to_types=(Type.CREATURE,),
            requires_toughness_greater_than_power=True,
        )
    match = _TYPE_COST_DECREASE.search(text)
    if match is not None:
        words = [word.strip().lower() for word in match.group("types").split(" and ")]
        types = tuple(_TYPE_WORDS[word] for word in words if word in _TYPE_WORDS)
        each = match.group("each")
        if types and (each is None or _for_each_count_is_readable(each)):
            return CostModifierEffect(
                kind=CostModifierKind.TYPE_DECREASE,
                amount=int(match.group("amount")),
                applies_to_types=types,
                per_each=each.strip() if each is not None else None,
            )
    match = _SUBTYPE_COST_DECREASE.search(text)
    if match is not None:
        subtype = canonical_subtype(match.group("subtype"))
        if subtype is not None:
            return CostModifierEffect(
                kind=CostModifierKind.TYPE_DECREASE,
                amount=int(match.group("amount")),
                applies_to_subtype=subtype,
            )
    return None


#: A colored mana symbol's letter to its `Color` (CR 107.4a).
_SYMBOL_COLORS: dict[str, Color] = {
    "W": Color.WHITE,
    "U": Color.BLUE,
    "B": Color.BLACK,
    "R": Color.RED,
    "G": Color.GREEN,
}


def _for_each_count_is_readable(phrase: str) -> bool:
    """Whether `machines/effects.py`'s "for each" reader knows `phrase` - a
    cost decrease with an unreadable count is not read at all (so it fails
    closed as a notice) rather than applied with no multiplier."""
    from ..effects import _for_each_multiplier

    return _for_each_multiplier(phrase) is not None


def looks_like_unparsed_cost_modifier(text: str) -> bool:
    """True if `text` reads like a cost-increase/floor effect this cannot
    turn into a `CostModifierEffect` - the fail-closed signal a caller records
    as a notice rather than silently skipping (the exact shape of DDR#978:
    a cost increase that fails to apply looks identical to ordinary play)."""
    if cost_modifier_effect(text) is not None:
        return False
    return bool(_COST_MODIFIER_SIGNAL.search(text)) or bool(_COST_DECREASE_SIGNAL.search(text))


#: "Activated abilities of `<group>` you control cost `{N}` less to
#: activate[. This effect can't reduce the mana in that cost to less than one
#: mana]." - Mutagen Man, Living Ooze's own "artifact tokens", Sam, Loyal
#: Attendant's "Foods", Blossoming Tortoise's "lands", Embalmer's Tools's
#: "creature cards in your graveyard" (not modelled: that names a zone, not
#: "you control", so it never matches this group-scoped shape), Training
#: Grounds's/Heartstone's/Biomancer's Familiar's/Agatha of the Vile
#: Cauldron's/Convergence of Dominion's "creatures"/"cards in your graveyard"
#: each paired with the "can't reduce ... to less than one mana" floor, and
#: Forensic Gadgeteer's "artifacts" with the identical floor. `<group>` is
#: read generically off its own words by `Game`'s board-wide reader, not
#: hardcoded to any one of these - a future printing naming a different
#: quality needs no new row here.
_ACTIVATED_ABILITY_GROUP_DISCOUNT_RE = re.compile(
    r"^activated abilities of (?P<quality>[a-z][a-z '-]*?) you control cost "
    r"\{(?P<amount>\d+)\} less to activate\.?"
    r"(?:\s*this effect can'?t reduce the mana in that cost to less than one mana\.?)?$",
    re.IGNORECASE,
)


def activated_ability_group_discount_effect(text: str) -> ActivatedAbilityGroupDiscount | None:
    """`_ACTIVATED_ABILITY_GROUP_DISCOUNT_RE`'s shape, or `None`."""
    match = _ACTIVATED_ABILITY_GROUP_DISCOUNT_RE.fullmatch(text.strip())
    if match is None:
        return None
    return ActivatedAbilityGroupDiscount(
        quality=match.group("quality").strip(),
        amount=int(match.group("amount")),
        floor_one="less than one mana" in text.lower(),
    )


# --------------------------------------------------------------------------
# Reading a card's own additional and alternative costs
# --------------------------------------------------------------------------

_ADDITIONAL = re.compile(
    r"^As an additional cost to cast this spell, (?P<what>[^.]+)\.", re.MULTILINE
)
_ALTERNATIVE = re.compile(
    r"^You may (?P<what>[^.]+?) rather than pay this spell's mana cost\.", re.MULTILINE
)
#: Force of Negation's and Force of Vigor's own cousin of `_ALTERNATIVE`: the
#: same CR 118.9 offer, gated on a plain "if it's not your turn" timing
#: condition printed ahead of it rather than offered unconditionally.
_ALTERNATIVE_IF_NOT_YOUR_TURN = re.compile(
    r"^If it's not your turn, you may (?P<what>[^.]+?) rather than pay this spell's mana cost\.",
    re.MULTILINE,
)


def _oracle_text_for_face(card: Card, face: str | None) -> str:
    """`card`'s own printed text, narrowed to `face` when it names one of
    `card.card_faces` (CR 715.3a/CR 709.3a: only that face's own text is
    evaluated).

    Split, Adventure, and modal-DFC printings carry no top-level
    `Card.oracle_text` at all - Scryfall leaves it null and puts each half's
    sentences on its own `CardFace` instead - so reading `card.oracle_text`
    unconditionally answers "" for every one of them regardless of what
    either face prints. `face=None` (every caller that has not chosen a
    face yet) keeps exactly the old, whole-card answer.
    """
    if face is not None and card.card_faces:
        for card_face in card.card_faces:
            if card_face.name == face:
                return card_face.oracle_text or ""
    return card.oracle_text or ""


def additional_cost_phrases(card: Card, *, face: str | None = None) -> list[str]:
    """The "as an additional cost" sentences printed on the card (CR 118.8a),
    or on `face` alone once one has been chosen (CR 715.3a, CR 709.3a)."""
    return [
        match.group("what") for match in _ADDITIONAL.finditer(_oracle_text_for_face(card, face))
    ]


def alternative_cost_phrases(card: Card, *, face: str | None = None) -> list[str]:
    """The "rather than pay this spell's mana cost" offers on the card (CR
    118.9), or on `face` alone once one has been chosen."""
    return [
        match.group("what") for match in _ALTERNATIVE.finditer(_oracle_text_for_face(card, face))
    ]


def alternative_cost_offers(card: Card) -> list[AlternativeCostOffer]:
    """Every inline CR 118.9 offer this card's own text prints - Force of
    Will's unconditional "You may pay 1 life and exile a blue card from your
    hand rather than pay this spell's mana cost." and Force of Negation's
    "If it's not your turn, you may exile a blue card from your hand rather
    than pay this spell's mana cost." alike.
    """
    offers = [
        AlternativeCostOffer(phrase=match.group("what"))
        for match in _ALTERNATIVE.finditer(card.oracle_text or "")
    ]
    offers.extend(
        AlternativeCostOffer(phrase=match.group("what"), requires_not_your_turn=True)
        for match in _ALTERNATIVE_IF_NOT_YOUR_TURN.finditer(card.oracle_text or "")
    )
    return offers


def _per_object_reduction_re(verb: str) -> re.Pattern[str]:
    return re.compile(
        r"this spell costs (?P<amount>\{[^}]+\}(?:\{[^}]+\})*) less to cast for each "
        rf"(?P<noun>[a-z]+) {verb} this way\.?",
        re.IGNORECASE,
    )


#: Rottenmouth Viper's own second sentence of its own additional cost
#: paragraph: "As an additional cost to cast this spell, you may sacrifice
#: any number of nonland permanents. This spell costs {1} less to cast for
#: each permanent sacrificed this way." CR 118.7a confines a generic-mana
#: reduction like this one to the cost's own generic component - the same
#: floor `ManaCost.minus` already enforces for every other per-count
#: reduction `Game.cost_reduction_for` reads - so this only ever carries a
#: `ManaCost` built from a plain `{N}`, never a coloured symbol. Distinct
#: from `Game.cost_reduction_for`'s own board-state reductions: what this
#: counts is not a fact about the board when the cost is determined, it is
#: how many objects the payer chose to sacrifice for *this* announced
#: additional cost (CR 601.2b), so it is read by `Casting.
#: sacrifice_for_cost_reduction` itself rather than by that generic reader.
_PER_OBJECT_SACRIFICE_COST_REDUCTION_RE = _per_object_reduction_re("sacrificed")
#: March of Wretched Sorrow's and its siblings' own linked sentence, the exile
#: twin of the one above: "As an additional cost to cast this spell, you may
#: exile any number of black cards from your hand. This spell costs {2} less
#: to cast for each card exiled this way." Read by `Casting.
#: exile_for_cost_reduction`, again only ever as a generic `{N}` (CR 118.7a).
_PER_OBJECT_EXILE_COST_REDUCTION_RE = _per_object_reduction_re("exiled")


def _per_object_reduction(pattern: re.Pattern[str], text: str, *, whole: bool) -> ManaCost | None:
    match = pattern.fullmatch(text.strip()) if whole else pattern.search(text)
    return None if match is None else ManaCost.try_parse(match.group("amount"))


def per_object_sacrifice_cost_reduction(card: Card, *, face: str | None = None) -> ManaCost | None:
    """The per-object amount `_PER_OBJECT_SACRIFICE_COST_REDUCTION_RE` prints
    on `card` - or on `face` alone once one has been chosen (CR 712.11b/c: a
    modal double-faced card's back face, Awaken the Blood Avatar, is the only
    text evaluated while it is cast) - or `None` when it prints no such
    sentence at all - as opposed to printing one this engine cannot read,
    which `Casting.sacrifice_for_cost_reduction` tells apart by trying to
    parse the amount and raising when that fails rather than silently
    reducing nothing."""
    return _per_object_reduction(
        _PER_OBJECT_SACRIFICE_COST_REDUCTION_RE, _oracle_text_for_face(card, face), whole=False
    )


def per_object_sacrifice_reduction_of_sentence(sentence: str) -> ManaCost | None:
    """`per_object_sacrifice_cost_reduction`'s amount when `sentence` is
    wholly that reduction sentence, else None."""
    return _per_object_reduction(_PER_OBJECT_SACRIFICE_COST_REDUCTION_RE, sentence, whole=True)


def per_object_exile_cost_reduction(card: Card, *, face: str | None = None) -> ManaCost | None:
    """`per_object_sacrifice_cost_reduction`'s exile twin: the per-card amount
    of "This spell costs {N} less to cast for each card exiled this way."."""
    return _per_object_reduction(
        _PER_OBJECT_EXILE_COST_REDUCTION_RE, _oracle_text_for_face(card, face), whole=False
    )


def per_object_exile_reduction_of_sentence(sentence: str) -> ManaCost | None:
    """`per_object_exile_cost_reduction`'s amount when `sentence` is wholly
    that reduction sentence, else None."""
    return _per_object_reduction(_PER_OBJECT_EXILE_COST_REDUCTION_RE, sentence, whole=True)


def alternative_cost_phrase_of_line(text: str) -> str | None:
    """The cost of a line that is wholly `alternative_cost_offers`'
    unconditional "You may <cost> rather than pay this spell's mana cost."
    (CR 118.9), else None."""
    match = _ALTERNATIVE.fullmatch(text.strip())
    return None if match is None else match.group("what")


#: Omniscience: "You may cast spells from your hand without paying their mana
#: costs." CR 118.9's *other* half - "a cost listed in a spell's text, **or
#: applied to it from another effect**" - so this is read off a permanent on
#: the battlefield rather than off the spell being cast, and the spell it
#: applies to prints nothing about it at all.
#:
#: Omnipresence's own sibling narrows by mana value instead of by type:
#: "You may cast spells with mana value less than or equal to the number of
#: creatures you control from your hand without paying their mana costs." -
#: the optional clause between "spells" and "from your hand" reads either a
#: literal number ("mana value 3 or less", not printed on any pool card but
#: the same CR 107.3a-free shape) or a live count phrased "the number of
#: [quality] you control", read again at CR 601.2f by `mana_value_cap_for`.
_STATIC_FREE_CAST = re.compile(
    r"^You may cast (?P<what>[\w' -]*?spells?)"
    r"(?: with mana value (?:(?P<mv_number>\d+) or less"
    r"|less than or equal to (?P<mv_quality>.+?)))?"
    r" from your (?P<zone>hand|graveyard) "
    r"without paying (?:its|their) mana costs?\.$",
    re.IGNORECASE,
)

#: "the number of creatures you control" - `mana_value_cap_for`'s own reading
#: of `StaticFreeCastGrant.max_mana_value_quality`, sharing `_requirement`
#: with every other quality this module already counts (`_PHRASE_SACRIFICE`
#: and friends), rather than a new vocabulary just for this one card.
_THE_NUMBER_OF_YOU_CONTROL = re.compile(r"^the number of (?P<quality>.+?) you control$")


#: Zaffai and the Tempests: "Once during each of your turns, you may cast an
#: instant or sorcery spell from your hand without paying its mana cost." One
#: with the Multiverse: "Once during each of your turns, you may cast a spell
#: from your hand or the top of your library without paying its mana cost."
#: CR 118.9's alternative cost again, applied from another effect, limited to
#: one use per turn of the permanent printing it.
_ONCE_EACH_TURN_FREE_CAST = re.compile(
    r"^Once during each of your turns, you may cast an? (?P<what>[\w' -]*?spell)"
    r" from your (?P<zone>hand)(?P<library> or the top of your library)?"
    r" without paying its mana cost\.?$",
    re.IGNORECASE,
)


def static_free_cast_grant(text: str) -> StaticFreeCastGrant | None:
    """Read one static ability line into a `StaticFreeCastGrant`, or None.

    Fails closed: a line this cannot read returns None rather than a guess, so
    a spell is never quietly made free by text nobody parsed.
    """
    once = _ONCE_EACH_TURN_FREE_CAST.match(text.strip())
    if once is not None:
        qualifier = re.sub(r"spells?$", "", once.group("what").strip().lower()).strip()
        return StaticFreeCastGrant(
            zone=_ZONE_WORDS[once.group("zone").lower()],
            type_word=qualifier or None,
            once_each_of_your_turns=True,
            also_top_of_library=once.group("library") is not None,
        )
    match = _STATIC_FREE_CAST.match(text.strip())
    if match is None:
        return None
    zone = _ZONE_WORDS.get(match.group("zone").lower())
    if zone is None:
        return None
    what = match.group("what").strip().lower()
    qualifier = re.sub(r"spells?$", "", what).strip()
    mv_number = match.group("mv_number")
    mv_quality = match.group("mv_quality")
    return StaticFreeCastGrant(
        zone=zone,
        type_word=qualifier or None,
        max_mana_value=int(mv_number) if mv_number is not None else None,
        max_mana_value_quality=mv_quality.strip() if mv_quality is not None else None,
    )


def mana_value_cap_for(
    grant: StaticFreeCastGrant, game: Any = None, controller: str | None = None
) -> int | None:
    """The live mana-value cap `grant` puts on what it makes free.

    `None` either when the grant carries no cap at all (an ordinary
    Omniscience-shaped grant, `grant.max_mana_value_quality` unset - the
    caller tells this apart from the case below by checking that field
    itself, a printed fact rather than a computed one) or when a printed
    quality this cannot read leaves a *live* cap unreadable - CR 118.3's
    "cannot use what was not read", not "nothing to cap", which is why the
    caller has to distinguish the two rather than treating both as free.
    """
    if grant.max_mana_value is not None:
        return grant.max_mana_value
    if grant.max_mana_value_quality is None:
        return None
    match = _THE_NUMBER_OF_YOU_CONTROL.fullmatch(grant.max_mana_value_quality.strip().lower())
    if match is None or game is None or controller is None:
        return None
    requirement = _requirement(match.group("quality"))
    if requirement is None:
        return None
    return sum(
        1
        for state in game.permanents_controlled_by(controller)
        if requirement.why_not(state, game, controller) is None
    )


# --------------------------------------------------------------------------
# Reading a printed cost phrase into something payable
# --------------------------------------------------------------------------

_COLOR_WORDS = {
    "white": Color.WHITE,
    "blue": Color.BLUE,
    "black": Color.BLACK,
    "red": Color.RED,
    "green": Color.GREEN,
    "colorless": Color.COLORLESS,
}


#: The count of an object cost: a number, CR 107.3a's X ("Exile X cards from
#: your graveyard", Necropolis Fiend), "one or more" ("Sacrifice one or
#: more artifacts", Radiant Lotus), or CR 107.1c's "any number of"
#: ("Sacrifice any number of nonland permanents", Rottenmouth Viper's own
#: additional cost) - the same zero-or-more range `parse_quantity` already
#: answers `QuantitySource.ANY_NUMBER` for; unlike "one or more" the payer
#: may name none at all, which `_cost_count` is what tells the two apart.
#: Read back with `_cost_count`.
_COST_COUNT = rf"(?P<count>any number of|one or more|{count_pattern(x=True)})"
#: `Exile a black card from your hand` (Force of Will) and the self-referential
#: `Exile this card from your graveyard` (Seasoned Pyromancer). CR 406.2 never
#: restricts exiling to the hand, so the zone is read off the sentence rather
#: than assumed - `exile_cost`'s default is only ever a fallback for a
#: sentence that names none.
#: The optional "with mana value N" tail Disrupting Shoal's pitch cost prints
#: ("exile a blue card with mana value X from your hand", CR 107.3a's X already
#: substituted). It sits between the noun and the zone, so it is spelled once
#: here and shared by every phrase that can carry it.
_MANA_VALUE_TAIL = r"(?: with mana value (?P<mana_value>\d+))?"
#: Gallia, Tragic Host's own "exile another creature card from your
#: graveyard" - CR 601.2c/113.6's "another"/"other" reads as a single
#: implicit "one", excluding the ability's own source (the same concept
#: `machines/targeting.py`'s own `TargetRequirement.excludes_source` already
#: names on the targeting side; `_requirement`'s caller below is what
#: actually marks `CardRequirement.excludes_source`, since `_requirement`
#: itself never sees which permanent this cost belongs to).
#: "Exile this artifact" (Wand of Vertebrae, Perpetual Timepiece) names the
#: permanent itself by type (CR 700.7's "this"), so it is exiled from the
#: battlefield; "this card" keeps its own zone default.
_PHRASE_EXILE = re.compile(
    rf"^exile (?:this (?P<self_noun>card|artifact|creature|enchantment|land|planeswalker|permanent)"
    rf"|(?:(?P<another>another)|{_COST_COUNT}) (?P<quality>[\w ]*?)cards?)"
    + _MANA_VALUE_TAIL
    + r"(?: from (?:your|their) (?P<zone>hand|graveyard|library|battlefield))?$",
    re.IGNORECASE,
)
#: "Exile a creature you control" (The Soul Stone): CR 406.2's exile from the
#: battlefield as a cost, of a permanent the payer controls (CR 118.3) - the
#: exile twin of `_PHRASE_SACRIFICE`, "another" excluding the source.
_PHRASE_EXILE_PERMANENT = re.compile(
    rf"^exile (?:(?P<another>another)|{_COST_COUNT}) (?P<quality>[\w ,]+?) you control$",
    re.IGNORECASE,
)
#: CR 701.20a's reveal as a cost: "Reveal X white cards from your hand"
#: (Martyr of Sands, Martyr of Spores), "reveal a creature card from your
#: hand" (Living Destiny). The count is a number word or CR 107.3a's X, and
#: the quality is read by `_requirement` like every other object cost's. A
#: rider after "hand" - Illuminated Folio's "that share a color" - is not this
#: shape, so that phrase stays unread rather than paying for the wrong cards.
#:
#: `self_noun` is the `_PHRASE_EXILE` shape one cost verb over: "Reveal this
#: card from your hand" (CR 702.57a's Forecast template, Writ of Passage),
#: "Reveal this creature from your hand" (Pride of the Clouds) - CR 201.5's
#: self-reference, so there is no count or quality to read at all, only the
#: caller's own object (`Game.activation_cost`'s `_cost_refers_to_self` fills
#: it in, same as an exiled or discarded "this card").
_PHRASE_REVEAL = re.compile(
    r"^reveal (?:this (?P<self_noun>card|artifact|creature|enchantment|land|planeswalker|permanent)"
    r" from (?:your|their) hand"
    r"|(?P<count>x|\w+) (?P<quality>[\w ,]*?)cards? from your hand)$",
    re.IGNORECASE,
)
#: CR 701.4a's keyword action as a cost: "behold a Jace" (Countersculpt,
#: Theorist's Sanctum), "behold a Kithkin" (Kinsbaile Aspirant, off-set), and
#: - CR 118.8/601.2f's own two-verbs-one-object shape - "behold a Kithkin
#: and exile it" (Champion of the Clachan, Champions of the Perfect/Shoal,
#: Champion of the Path/Weird), whose trailing "and exile it" the optional
#: `exile` group captures. "Reveal a [quality] card from your hand or choose
#: a [quality] permanent you control on the battlefield" - one component,
#: `ComponentKind.BEHOLD`, since CR 701.4a is a single keyword action with
#: two ways to satisfy it, not two separate costs the way sacrifice-or-discard
#: would be; the exile, when printed, applies to whichever one the payer chose.
_PHRASE_BEHOLD = re.compile(
    r"^behold (?:a|an) (?P<quality>[\w' ]+?)(?P<exile> and exile it)?$", re.IGNORECASE
)
#: CR 701.4a's action, counted and pluralised rather than singular and
#: articled - Kindle the Inner Flame's own flashback cost, "Flashback—{1}{R},
#: Behold three Elementals." (CR 702.34a's flashback cost is itself an
#: alternative cost built from ordinary cost pieces, split apart and each
#: piece read through this same phrase table - `machines/casting.py`.) The
#: quality is read plural here ("Elementals") where `_PHRASE_BEHOLD`'s
#: singular callers already hand `_requirement` the printed capitalised
#: singular noun; `_behold_n_requirement` below is what turns the plural back
#: into the singular subtype `_requirement` already understands.
_PHRASE_BEHOLD_N = re.compile(r"^behold (?P<count>\w+) (?P<quality>[\w' ]+)$", re.IGNORECASE)
_ZONE_WORDS: dict[str, Zone] = {
    "hand": Zone.HAND,
    "graveyard": Zone.GRAVEYARD,
    "library": Zone.LIBRARY,
    "battlefield": Zone.BATTLEFIELD,
}
#: Back from the Brink: "Exile a creature card from your graveyard and pay
#: its mana cost". Ahead of `_PHRASE_EXILE`, whose own trailing zone group is
#: a strict subset of this one's start, so this is tried first rather than
#: matching the exile half and silently dropping "and pay its mana cost".
_PHRASE_EXILE_AND_PAY_MANA_COST = re.compile(
    rf"^exile (?:this card|{count_pattern('count')} (?P<quality>[\w ]*?)cards?)"
    r"(?: from (?:your|their) (?P<zone>hand|graveyard|library|battlefield))? and pay "
    r"(?:its|their) mana cost$",
    re.IGNORECASE,
)
#: `quality`'s character class allows a comma so a disjunctive list -
#: "Sacrifice an artifact, creature, or land" (Greater Gargadon) - matches as
#: one phrase rather than being split by `_split_cost_phrase`'s own comma cut;
#: `_requirement` is what turns the list into a `CardRequirement` disjunction.
#: "Sacrifice another creature or artifact" (Vanguard of the Rose) reads
#: "another" as `_PHRASE_EXILE` does below: one, excluding the source.
_PHRASE_SACRIFICE = re.compile(
    rf"^sacrifice (?:(?P<another>another)|{_COST_COUNT}) (?P<quality>[\w ,]+)$", re.IGNORECASE
)
#: "sacrifice all creatures you control" (Soulblast's additional cost),
#: "Sacrifice all lands you control" (Tomb of Urami's activation cost) - no
#: count and no choice: every permanent of the quality the payer controls
#: when the cost is paid (CR 601.2h, CR 701.21a), `CostComponent.
#: every_matching`. "You control" is optional in the reading because CR
#: 701.21a already confines a sacrifice to the payer's own permanents.
_PHRASE_SACRIFICE_ALL = re.compile(
    r"^sacrifice all (?P<quality>[\w ,]+?)(?: you control)?$", re.IGNORECASE
)
#: `Discard a card`, `Discard a legendary card with the same name as a
#: legendary permanent you control` (Key to the Side-Door). The same-name tail
#: is a second demand on the *same* card - CR 201.2a's "at least one name in
#: common" against something the payer controls - not a second card to choose,
#: so it becomes a nested `CardRequirement` rather than another component.
_PHRASE_DISCARD = re.compile(
    rf"^discard {_COST_COUNT} (?P<quality>[\w ]*?)cards?"
    r"(?: with the same name as (?:a|an) (?P<same_name>[\w ]+?) you control)?$",
    re.IGNORECASE,
)
#: `Tap an untapped creature you control` (Swallow Whole's printed additional
#: cost, CR 118.8a). Distinct from the `{T}` symbol, which CR 107.5 defines as
#: "Tap this permanent" and never needs a choice made: this sentence names a
#: *quality*, so the permanent tapped is chosen at announcement (CR 601.2b) and
#: tapped as the total cost is paid (CR 601.2h). "untapped" is optional in the
#: wording because CR 107.5's "a permanent that's already tapped can't be
#: tapped again to pay the cost" is true whether or not the sentence says so -
#: `CostComponent._why_not_tap` enforces it either way.
#: "Tap another untapped creature you control" (Tyvar, the Pummeler) reads
#: "another" the same way: one, and never the ability's own source.
#: "Tap two other untapped artifacts you control" (Bladewheel Chariot) reads
#: "other" after a count the same way: never the ability's own source.
_PHRASE_TAP = re.compile(
    rf"^tap (?:(?P<another>another)|{_COST_COUNT}) (?P<other>other )?(?:untapped )?"
    r"(?P<quality>[\w ,]+?) "
    r"you control$",
    re.IGNORECASE,
)
#: `Return a land you control to its owner's hand` (Tameshi, Reality
#: Architect's activation cost) - CR 118.3's object cost with a quality and a
#: count, the same shape as `_PHRASE_SACRIFICE`, paid by `Game.return_to_hand`.
_PHRASE_RETURN_TO_HAND = re.compile(
    rf"^return (?:(?P<another>another)|{_COST_COUNT}) (?P<quality>[\w ,]+?) you control "
    r"to (?:its owner's hand|their owner's hand|their owners' hands)$",
    re.IGNORECASE,
)
#: `Return this land to its owner's hand` (Maze's End's activation cost) - the
#: self-referential twin of `_PHRASE_RETURN_TO_HAND`: the permanent the
#: ability is on (CR 602.1a), built empty and filled with it by `Game.
#: activation_cost`'s self-reference fill-in, like "Exert this land".
_PHRASE_RETURN_SELF_TO_HAND = re.compile(
    r"^return this (?P<self_noun>artifact|creature|enchantment|land|permanent|planeswalker"
    r"|battle) to its owner's hand$",
    re.IGNORECASE,
)
#: `Collect evidence 6` (Detective's Phoenix's `Bestow-{R}, Collect evidence
#: 6.`) - CR 701.59a's keyword action used as a cost. Nothing is named to
#: choose: "any number of cards ... with total mana value N or greater" is a
#: threshold, not a count, so this carries only N.
_PHRASE_COLLECT_EVIDENCE = re.compile(
    rf"^collect evidence {count_pattern('amount', article=False)}$", re.IGNORECASE
)
#: `{Q}`, CR 107.6's untap symbol, which "in an activation cost means 'Untap
#: this permanent.'" Umbral Mantle's granted `{3}, {Q}:` is the pool's
#: printing. Read here rather than left to `ManaCost.parse` because it is not
#: mana at all - it is an action, exactly as `{T}` is (CR 107.5).
_PHRASE_UNTAP_SYMBOL = re.compile(r"^\{Q\}$", re.IGNORECASE)
#: `Mill a card` (Millikin's `{T}, Mill a card: Add {C}.`) - CR 701.17a's
#: keyword action used as a cost. Nothing is chosen: the cards come off the top
#: of the payer's own library, so this carries a count and no requirement.
_PHRASE_MILL = re.compile(rf"^mill {count_pattern('count')} cards?$", re.IGNORECASE)


#: `Exert this land`, `Exert this creature` (CR 701.43a). Only the self-
#: referential form, which is the only one printed inside a cost.
_PHRASE_EXERT_SELF = re.compile(
    r"^exert this (?:land|creature|permanent|artifact|enchantment)$", re.IGNORECASE
)
#: "Put a -1/-1 counter on this creature" (Devoted Druid) and "Remove a +1/+1
#: counter from this creature" (Walking Ballista) - CR 118.3, 122.1, 122.6.
#: Only the self-referential "this <type>" shape is read; a cost that names a
#: chosen target ("Remove a counter from target permanent") would need target
#: resolution this builder does not have, so it is left unmatched and the
#: caller fails closed (see `cost_component_for_phrase`'s docstring).
_COUNTER_SELF_SUBJECT = r"this (?:creature|permanent|artifact|enchantment|planeswalker|land)"
_PHRASE_PLACE_COUNTERS = re.compile(
    rf"^put {count_pattern('count')} (?P<kind>[\w+/−-]+) counters? on {_COUNTER_SELF_SUBJECT}$",
    re.IGNORECASE,
)
#: "Remove a counter from this creature" (Glen Elendra Guardian) - no kind
#: named, so any counter pays it (`ANY_COUNTER_KIND`).
#: "Remove three counters from among creatures you control" (Dawnhand
#: Dissident's and Quilled Greatwurm's own "by removing ..."), "Remove two
#: +1/+1 counters from among creatures you control" (Hopeful Initiate) -
#: CR 118.3's counters, summed across the permanents chosen
#: (`CostComponent.from_among`).
_PHRASE_REMOVE_COUNTERS_FROM_AMONG = re.compile(
    rf"^remov(?:e|ing) {_COST_COUNT} (?:(?P<kind>[\w+/−-]+) )?counters? from among "
    r"(?P<group>[a-z ]+?)s you control$",
    re.IGNORECASE,
)
_PHRASE_REMOVE_ANY_COUNTERS = re.compile(
    rf"^remove {_COST_COUNT} counters? from {_COUNTER_SELF_SUBJECT}$", re.IGNORECASE
)
_PHRASE_REMOVE_COUNTERS = re.compile(
    rf"^remove (?:(?P<any_number>any number of)|{_COST_COUNT}) (?P<kind>[\w+/−-]+) counters? "
    # "from a creature you control" (Ray Fillet, Man Ray; Korozda Gorgon):
    # a permanent the payer chooses as the cost is paid, the same empty-then-
    # chosen shape blight's "a creature you control" uses below (CR 118.3).
    rf"from (?:an? (?P<chosen>[\w -]+?) you control|"
    # The Astonishing Ant-Man's "from The Astonishing Ant-Man": CR 201.5's
    # self-reference by name, filled in by `Game`'s `_cost_refers_to_self`.
    rf"{_COUNTER_SELF_SUBJECT}|(?-i:[A-Z][\w,' -]*))$",
    re.IGNORECASE,
)


#: CR 701.68a's "Blight N" as a cost - "{1}{R}, {T}, Blight 1" (Sting-Slinger),
#: "blight X" (Soul Immolation, X already substituted when announced): N -1/-1
#: counters on a creature the payer controls, chosen as the cost is paid.
_PHRASE_BLIGHT = re.compile(
    rf"^blight {count_pattern('count', x=True, article=False)}$", re.IGNORECASE
)


def _counter_kind_word(word: str) -> str:
    """Normalise a counter kind read out of a cost sentence.

    `+1/+1` and `-1/-1` are kept exactly as `Counter` spells them (accepting
    the U+2212 minus Scryfall sometimes prints, same as `_LOYALTY_SYMBOL`);
    any named kind - "oil", "fate", "charge" - is lower-cased so it matches
    however else the engine already stores it (Gemstone Caverns's "luck" is
    lower-cased the same way in `machines/abilities.py`).
    """
    if re.fullmatch(r"[+−-]1/[+−-]1", word):
        return word.replace("−", "-")
    return word.lower()


def _requirement(quality: str) -> CardRequirement | None:
    """Turn `black`, `creature`, `Mountain`, or `artifact, creature, or land`
    into what the cards must be.

    `CardRequirement.types` (like `.colors` and `.subtypes`) is already a
    disjunction - "at least one of these" - so a comma-and-"or" list of card
    types (Greater Gargadon's "Sacrifice an artifact, creature, or land") is
    the same shape as a single type, just with more words: each word is
    stripped of the punctuation the list leaves on it and matched the same
    way, and a bare connector ("or", "and") names nothing and is skipped
    rather than failing the whole phrase.

    Unrecognised wording returns None, which the caller reads as "this phrase
    was not understood" rather than as "anything will do" - a cost that silently
    accepts the wrong card is worse than one that refuses to be built.
    """
    words = [word for word in quality.strip().split() if word]
    if not words:
        return CardRequirement(description=quality.strip())

    colors: list[Color] = []
    types: list[Type] = []
    excluded_types: list[Type] = []
    subtypes: list[str] = []
    supertypes: list[Supertype] = []
    tapped: bool | None = None
    token: bool | None = None
    for raw_word in words:
        word = raw_word.strip(",")
        if not word:
            continue
        lowered = word.lower().rstrip("s")
        if lowered in _QUALITY_CONNECTORS:
            continue
        if lowered in ("tapped", "untapped"):
            # CR 110.5's status: web-slinging's "a tapped creature you
            # control" (CR 702.188a).
            tapped = lowered == "tapped"
            continue
        if lowered in ("token", "nontoken", "non-token"):
            # CR 111.1: a token is a permanent no card represents.
            token = lowered == "token"
            continue
        negated_type = lowered.removeprefix("non-").removeprefix("non")
        if lowered.startswith("non") and negated_type in {type_.value for type_ in Type}:
            # "nonland permanents" (Rottenmouth Viper) - CR 118.7a's own
            # negated card type, read the same way for any type word rather
            # than pinned to "land".
            excluded_types.append(Type(negated_type))
            continue
        if lowered == "permanent":
            # CR 110.1 makes everything on the battlefield a permanent
            # already, so "permanent"/"permanents" names no card type at all
            # - the same "no restriction" reading `_controlled_requirement`
            # already gives it on same-name comparisons, needed here too for
            # a sacrifice cost with no type demand (Ward - Sacrifice three
            # permanents, CR 702.21a) rather than one word away from a
            # subtype (Greater Gargadon's "artifact, creature, or land" is
            # the demand-bearing shape; bare "permanents" is not).
            continue
        if lowered in _COLOR_WORDS:
            colors.append(_COLOR_WORDS[lowered])
        elif lowered in {supertype.value for supertype in Supertype}:
            # CR 205.4a's five supertypes. "A legendary card" is as much a
            # demand on what may pay as "a black card" is, and was previously
            # unread, which built no requirement at all and let anything pay.
            supertypes.append(Supertype(lowered))
        elif lowered in {type_.value for type_ in Type}:
            types.append(Type(lowered))
        elif word[:1].isupper():
            # A capitalised noun in a cost phrase is a subtype: `Sacrifice a
            # Mountain`, `Sacrifice a Goblin`.
            subtypes.append(word)
        else:
            return None
    return CardRequirement(
        colors=colors,
        types=types,
        excluded_types=excluded_types,
        subtypes=subtypes,
        supertypes=supertypes,
        description=quality.strip(),
        tapped=tapped,
        token=token,
    )


def _behold_n_requirement(plural_quality: str) -> CardRequirement | None:
    """`_requirement` for `_PHRASE_BEHOLD_N`'s own plural noun phrase -
    "Elementals" (Kindle the Inner Flame's "Behold three Elementals") rather
    than `_PHRASE_BEHOLD`'s singular, articled "an Elemental".

    `_requirement` keeps a capitalised word verbatim as a subtype
    (`Sacrifice a Mountain`), which is right for every existing caller since
    none of them is ever handed a plural - so the plural noun is singularised
    here, once, before the shared reader ever sees it: each capitalised word
    is looked up in `canonical_subtype` (which already knows "Elementals" ->
    "elemental" off the subtype pool's own plural index) and title-cased back
    to the shape `_requirement` already expects. A capitalised word
    `canonical_subtype` cannot place is left alone rather than guessed at -
    Ugin's Labyrinth's colour words never reach this branch at all, so the
    only risk is an unlisted subtype, which then simply fails to parse as a
    subtype the same way an unrecognised singular one already does."""
    words = plural_quality.strip().split()

    def _singular(word: str) -> str:
        if word[:1].isupper():
            canonical = canonical_subtype(word)
            if canonical is not None:
                return canonical.capitalize()
        return word

    singularised = [_singular(word) for word in words]
    return _requirement(" ".join(singularised))


def _controlled_requirement(quality: str) -> CardRequirement | None:
    """`_requirement` for the *other* side of a same-name comparison: what the
    permanent on the battlefield has to be.

    Only one word differs in practice, and it is the noun: "a legendary
    permanent you control" says nothing about card types, because CR 110.1
    makes every object on the battlefield a permanent already. So `permanent`
    is read as "no type demand at all" here, where on the paying side - "a
    permanent card" in a hand - it would be a real demand and is deliberately
    not accepted.
    """
    words = [word for word in quality.split() if word.lower().rstrip("s") != "permanent"]
    if not words:
        return CardRequirement(description=quality.strip())
    requirement = _requirement(" ".join(words))
    if requirement is None:
        return None
    requirement.description = quality.strip()
    return requirement


def cost_component_for_phrase(phrase: str, payer: str | None = None) -> CostComponent | None:
    """Read one printed cost sentence into a payable `CostComponent`.

    This is what makes `Evoke—Exile a black card from your hand.` more than a
    string: CR 118.9 calls it an alternative cost, and an alternative cost has
    to be *paid*, which means knowing that it exiles one black card out of the
    caster's hand.

    Also reads "Put a -1/-1 counter on this creature" (Devoted Druid) and
    "Remove a +1/+1 counter from this creature" (Walking Ballista) - the
    templated counter-cost shapes CR 122.1/122.6 describe - but only the
    self-referential "this <type>" form; a phrase naming a chosen target
    ("Remove a counter from target permanent") is outside what this builder
    can resolve and returns None like any other unread shape.

    Returns None for a phrase it cannot read, so the caller can leave the
    keyword unexecuted rather than charge the wrong thing - `Game.activation_cost`
    turns that `None` into a raised refusal (CR 602.5) instead of silently
    skipping the cost, so an ability this cannot template is refused, never
    activated for free.
    """
    text = phrase.strip().rstrip(".")

    life = _PHRASE_PAY_LIFE.match(text)
    if life is not None:
        amount = parse_amount(life.group("amount"))
        if amount is None:
            return None
        if isinstance(amount, VariableX):
            # CR 118.3b: players can always pay 0 life, so 0 stands until the
            # X is announced (`Game.activation_cost`).
            return pay_life_cost(0, payer, description=text).model_copy(
                update={"variable_count": True}
            )
        return pay_life_cost(amount, payer, description=text)

    mill = _PHRASE_MILL.match(text)
    if mill is not None:
        count = parse_count(mill.group("count"))
        if count is None:
            return None
        return mill_cost(count, payer, description=text)

    evidence = _PHRASE_COLLECT_EVIDENCE.match(text)
    if evidence is not None:
        amount = parse_count(evidence.group("amount"), article=False)
        if amount is None:
            return None
        return collect_evidence_cost(amount, payer, description=text)

    if _PHRASE_UNTAP_SYMBOL.match(text):
        # CR 107.6's "Untap this permanent": the permanent is the one whose
        # ability this is, and only the caller knows which that is, so the
        # component is built empty and correctly refuses to be paid until the
        # card is filled in (CR 118.3) - same as `_PHRASE_EXERT_SELF` below.
        return untap_cost(payer=payer, description=text)

    if _PHRASE_EXERT_SELF.match(text):
        # The permanent exerted is the one whose ability this is, and only the
        # caller knows which that is, so the component is built empty and
        # correctly refuses to be paid until the card is filled in (CR 118.3).
        return exert_cost(payer=payer, required=1, description=text)

    place = _PHRASE_PLACE_COUNTERS.match(text)
    if place is not None:
        count = parse_count(place.group("count"))
        if count is None:
            return None
        kind = _counter_kind_word(place.group("kind"))
        return place_counters_cost(None, count, counter_kind=kind, payer=payer, description=text)

    from_among = _PHRASE_REMOVE_COUNTERS_FROM_AMONG.match(text)
    if from_among is not None:
        read = _cost_count(from_among.group("count"))
        if read is None or read[1]:
            return None
        kind_word = from_among.group("kind")
        requirement = _requirement(from_among.group("group"))
        if requirement is None:
            return None
        component = remove_counters_cost(
            None,
            read[0],
            counter_kind=_counter_kind_word(kind_word) if kind_word else ANY_COUNTER_KIND,
            payer=payer,
            description=text,
        )
        component.from_among = True
        component.required = 0
        component.requirement = requirement
        return component
    remove_any = _PHRASE_REMOVE_ANY_COUNTERS.match(text)
    if remove_any is not None:
        read = _cost_count(remove_any.group("count"))
        if read is None or read[1]:
            return None
        return remove_counters_cost(
            None, read[0], counter_kind=ANY_COUNTER_KIND, payer=payer, description=text
        )
    remove_counters = _PHRASE_REMOVE_COUNTERS.match(text)
    if remove_counters is not None and remove_counters.group("any_number") is not None:
        # "Remove any number of `<kind>` counters from `<this>`" (The
        # Astonishing Ant-Man, Geistflame Reservoir): CR 107.3a's announced
        # number, the same as an X - zero included.
        component = remove_counters_cost(
            None,
            0,
            counter_kind=_counter_kind_word(remove_counters.group("kind")),
            payer=payer,
            description=text,
        )
        component.variable_count = True
        return component
    if remove_counters is not None:
        read = _cost_count(remove_counters.group("count"))
        if read is None or (read[1] and read[0]):
            # "Remove one or more counters" has no announced number to remove.
            return None
        count, variable = read
        kind = _counter_kind_word(remove_counters.group("kind"))
        component = remove_counters_cost(
            None, count, counter_kind=kind, payer=payer, description=text
        )
        component.variable_count = variable
        chosen = remove_counters.group("chosen")
        if chosen is not None:
            # "from a creature you control": the control half is
            # `_why_not_controlled`, the quality half this requirement.
            component.requirement = _requirement(chosen)
            if component.requirement is None:
                return None
        return component

    blight = _PHRASE_BLIGHT.match(text)
    if blight is not None:
        amount = parse_amount(blight.group("count"))
        if amount is None:
            return None
        variable = isinstance(amount, VariableX)
        component = place_counters_cost(
            None,
            0 if variable else amount,
            counter_kind=_counter_kind_word("-1/-1"),
            payer=payer,
            description=text,
        )
        # CR 701.68a: "a creature you control" - the control half is
        # `_why_not_controlled`, the creature half this requirement.
        component.requirement = _requirement("creature")
        component.variable_count = variable
        return component

    reveal = _PHRASE_REVEAL.match(text)
    if reveal is not None:
        if reveal.group("self_noun") is not None:
            # "Reveal this card/creature from your hand": CR 201.5's self-
            # reference, so there is nothing to choose - only the caller
            # knows which card this is (`_PHRASE_EXILE`'s own "Exile this
            # card" branch is the identical shape one cost verb over).
            return reveal_cost(payer=payer, required=1, description=text)
        reveal_requirement = _requirement(reveal.group("quality"))
        if reveal_requirement is None:
            return None
        if reveal.group("count").lower() == "x":
            component = reveal_cost(payer=payer, required=0, description=text, variable_count=True)
        else:
            reveal_count = parse_count(reveal.group("count"))
            if reveal_count is None:
                return None
            component = reveal_cost(payer=payer, required=reveal_count, description=text)
        component.requirement = reveal_requirement
        return component

    behold = _PHRASE_BEHOLD.match(text)
    if behold is not None:
        behold_requirement = _requirement(behold.group("quality"))
        if behold_requirement is None:
            return None
        component = behold_cost(
            payer=payer,
            required=1,
            description=text,
            exile_after=behold.group("exile") is not None,
        )
        component.requirement = behold_requirement
        return component

    behold_n = _PHRASE_BEHOLD_N.match(text)
    if behold_n is not None:
        count = parse_count(behold_n.group("count"), article=False)
        behold_n_requirement = _behold_n_requirement(behold_n.group("quality"))
        if count is None or behold_n_requirement is None:
            return None
        component = behold_cost(payer=payer, required=count, description=text)
        component.requirement = behold_n_requirement
        return component

    exile_and_pay = _PHRASE_EXILE_AND_PAY_MANA_COST.match(text)
    if exile_and_pay is not None:
        zone = _ZONE_WORDS.get((exile_and_pay.group("zone") or "graveyard").lower(), Zone.GRAVEYARD)
        count = parse_count(exile_and_pay.group("count"))
        requirement = _requirement(exile_and_pay.group("quality") or "")
        if count is None or requirement is None:
            return None
        return exile_and_pay_mana_cost_cost(
            payer=payer, required=count, description=text, zone=zone, requirement=requirement
        )

    exile = _PHRASE_EXILE.match(text)
    if exile is not None:
        self_noun = (exile.group("self_noun") or "card").lower()
        default_zone = "hand" if self_noun == "card" else "battlefield"
        zone = _ZONE_WORDS.get((exile.group("zone") or default_zone).lower(), Zone.HAND)
        if exile.group("count") is None and exile.group("another") is None:
            # "Exile this card [from your graveyard]": CR 700.7's self-
            # reference, so there is nothing to choose - only the caller
            # knows which permanent this is, same as `_PHRASE_EXERT_SELF`.
            return exile_cost(payer=payer, required=1, description=text, zone=zone)
        if exile.group("another") is not None:
            # "Exile another <quality> card": CR 601.2c/113.6's "another" -
            # a plain, implicit one, excluding the ability's own source
            # (`Game.activation_cost` fills in which permanent that is).
            requirement = _requirement(exile.group("quality"))
            if requirement is None:
                return None
            requirement.excludes_source = True
            component = exile_cost(payer=payer, required=1, description=text, zone=zone)
            component.requirement = requirement
            return component
        read = _cost_count(exile.group("count"))
        requirement = _requirement(exile.group("quality"))
        if read is None or requirement is None:
            return None
        if exile.group("mana_value") is not None:
            requirement.mana_value = int(exile.group("mana_value"))
        component = exile_cost(payer=payer, required=read[0], description=text, zone=zone)
        component.requirement = requirement
        component.variable_count = read[1]
        return component

    exile_permanent = _PHRASE_EXILE_PERMANENT.match(text)
    if exile_permanent is not None:
        read = (
            (1, False)
            if exile_permanent.group("another")
            else _cost_count(exile_permanent.group("count"))
        )
        requirement = _requirement(exile_permanent.group("quality"))
        if read is None or requirement is None:
            return None
        if exile_permanent.group("another") is not None:
            requirement.excludes_source = True
        component = exile_cost(
            payer=payer, required=read[0], description=text, zone=Zone.BATTLEFIELD
        )
        component.requirement = requirement
        component.variable_count = read[1]
        return component

    discard = _PHRASE_DISCARD.match(text)
    if discard is not None:
        read = _cost_count(discard.group("count"))
        requirement = _requirement(discard.group("quality"))
        if read is None or requirement is None:
            return None
        if discard.group("same_name") is not None:
            same_name = _controlled_requirement(discard.group("same_name"))
            if same_name is None:
                return None
            requirement.same_name_as = same_name
        component = discard_cost(payer=payer, required=read[0], description=text)
        component.requirement = requirement
        component.variable_count = read[1]
        return component

    sacrifice_all = _PHRASE_SACRIFICE_ALL.match(text)
    if sacrifice_all is not None:
        requirement = _requirement(sacrifice_all.group("quality"))
        if requirement is None:
            return None
        component = sacrifice_cost(payer=payer, required=0, description=text)
        component.requirement = requirement
        component.every_matching = True
        return component

    sacrifice = _PHRASE_SACRIFICE.match(text)
    if sacrifice is not None:
        another = sacrifice.group("another") is not None
        read = (1, False) if another else _cost_count(sacrifice.group("count"))
        requirement = _requirement(sacrifice.group("quality"))
        if read is None or requirement is None:
            return None
        # CR 601.2c/113.6's "another": `Game.activation_cost` fills in which
        # permanent is excluded, the same as for "Exile another ...".
        requirement.excludes_source = another
        component = sacrifice_cost(payer=payer, required=read[0], description=text)
        component.requirement = requirement
        component.variable_count = read[1]
        return component

    returning = _PHRASE_RETURN_TO_HAND.match(text)
    if returning is not None:
        another = returning.group("another") is not None
        read = (1, False) if another else _cost_count(returning.group("count"))
        requirement = _requirement(returning.group("quality"))
        if read is None or requirement is None or read[1]:
            return None
        requirement.excludes_source = another
        component = return_to_hand_cost(payer=payer, required=read[0], description=text)
        component.requirement = requirement
        return component

    returning_self = _PHRASE_RETURN_SELF_TO_HAND.match(text)
    if returning_self is not None:
        # A requirement marks this as an object cost rather than ninjutsu's
        # "unblocked attacker" one (`_why_not_return_to_hand`).
        requirement = _requirement(returning_self.group("self_noun"))
        if requirement is None:
            return None
        component = return_to_hand_cost(payer=payer, required=1, description=text)
        component.requirement = requirement
        return component

    tap = _PHRASE_TAP.match(text)
    if tap is not None:
        another = tap.group("another") is not None
        read = (1, False) if another else _cost_count(tap.group("count"))
        requirement = _requirement(tap.group("quality"))
        if read is None or requirement is None:
            return None
        requirement.excludes_source = another or tap.group("other") is not None
        component = tap_cost(payer=payer, description=text)
        component.required = read[0]
        component.requirement = requirement
        component.variable_count = read[1]
        return component

    return None


def total_cost_for_phrase(phrase: str, payer: str | None = None) -> TotalCost | None:
    """A whole printed cost, mana or otherwise, as a `TotalCost`.

    `Flashback {2}{R}` is mana; `Evoke—Exile a black card from your hand.` is a
    component; a comma-separated phrase can be both.

    `Waterbend {3}` is mana too, spelled with an action word in front of it
    (CR 701.67a: "'Waterbend [cost]' means 'Pay [cost]. ...'"). The permission
    that word carries - tapping an untapped artifact or creature for each
    generic mana - is CR 701.67b's alternate payment method and belongs to an
    open `CostPayment`, not to the total cost, exactly as CR 702.51b puts
    convoke after the cost is determined.
    """
    mana = ManaCost()
    components: list[CostComponent] = []
    waterbend_generic: int | None = None
    if "," not in phrase:
        # `_split_cost_phrase` also splits on a bare " and " - right for a
        # comma-joined or genuinely compound cost ("Tap two untapped
        # creatures you control and discard a card", none printed yet, would
        # be two components), wrong for a *single* component whose own
        # phrase happens to contain "and" internally - "behold a Kithkin
        # and exile it" (CR 118.8/601.2f's one object, two verbs) is not
        # "behold a Kithkin" plus a bare, unreadable "exile it". Trying the
        # whole un-split phrase first, only when there is no comma to say
        # this is genuinely a list, catches that shape without touching any
        # phrase that only reads at all once split.
        whole = cost_component_for_phrase(phrase.strip().rstrip("."), payer)
        if whole is not None:
            return TotalCost(mana=mana, components=[whole], waterbend_generic=waterbend_generic)
    for part in _split_cost_phrase(phrase):
        if _ONLY_MANA.match(part) and not _ACTION_SYMBOL.match(part):
            # A run of braced symbols that is not all mana - CR 107.14's {E}
            # among them - is a cost this phrase reader does not know how to
            # pay, so the whole phrase is unread rather than raising.
            read = ManaCost.try_parse(part)
            if read is None:
                return None
            mana = mana.plus(read)
            continue
        waterbend = waterbend_mana_cost(part)
        if waterbend is not None:
            mana = mana.plus(waterbend)
            # CR 701.67b's own bound: only *this* piece's generic, not the
            # whole phrase's - a second, plain-mana piece in the same
            # comma-separated cost (none printed yet, but CR 602.1a allows
            # it) must not widen what the tap method may cover.
            waterbend_generic = (waterbend_generic or 0) + waterbend.generic
            continue
        repeated_symbol = pay_repeated_symbol_mana_cost(part)
        if repeated_symbol is not None:
            mana = mana.plus(repeated_symbol)
            continue
        component = cost_component_for_phrase(part, payer)
        if component is None:
            return None
        components.append(component)
    return TotalCost(mana=mana, components=components, waterbend_generic=waterbend_generic)


#: "{G} or {W}" - Arctic Nishoba's cumulative upkeep cost: one mana symbol or
#: another, chosen each time the cost is paid.
_ONE_SYMBOL_OR_ANOTHER = re.compile(
    r"^(?P<a>\{[^{}/]+\})\s+or\s+(?P<b>\{[^{}/]+\})$", re.IGNORECASE
)

#: The non-mana kinds `Game.may_pay_unless_cost` can pay mid-resolution, and
#: so the only ones a cumulative upkeep cost may carry here.
_UPKEEP_PAYABLE_KINDS = frozenset(
    {ComponentKind.DISCARD, ComponentKind.SACRIFICE, ComponentKind.PAY_LIFE}
)


def cumulative_upkeep_cost(printed: str, count: int, payer: str | None = None) -> TotalCost | None:
    """CR 702.24a's "[cost] for each age counter on it", as one `TotalCost`.

    "If [cost] has choices associated with it, each choice is made separately
    for each age counter, then either the entire set of costs is paid, or none
    of them is paid." So the printed cost is repeated `count` times into a
    single total, and the choices stay per copy: "{G} or {W}" becomes one
    `{G/W}` symbol per counter (each symbol is paid with either colour on its
    own), "Discard a card" becomes a discard of `count` cards (one chosen card
    per counter), "Pay 1 life" `count` life. One total is what makes the
    payment all or nothing: `Game.may_pay_unless_cost` offers it only when all
    of it can be paid (CR 118.3) and then pays all of it.

    `None` when the printed cost is not one this engine can read and pay
    mid-resolution - the caller fails closed rather than offering a payment
    that could never be made.
    """
    either = _ONE_SYMBOL_OR_ANOTHER.fullmatch(printed.strip().rstrip("."))
    if either is not None:
        hybrid = ManaCost.try_parse(f"{{{either.group('a')[1:-1]}/{either.group('b')[1:-1]}}}")
        if hybrid is None:
            return None
        one = TotalCost.of(hybrid)
    else:
        read = total_cost_for_phrase(printed, payer)
        if read is None:
            return None
        one = read
    if any(component.kind not in _UPKEEP_PAYABLE_KINDS for component in one.components):
        return None
    if any(component.variable_count for component in one.components):
        return None
    mana = ManaCost()
    for _ in range(count):
        mana = mana.plus(one.mana)
    components = [
        component.model_copy(
            update={
                "required": component.required * count,
                "amount": component.amount * count,
                "cards": [],
                "description": "",
            }
        )
        for component in one.components
        if count > 0
    ]
    total = TotalCost(mana=mana, components=components)
    return total if payer is None else total.assign_payer(payer)


_ONLY_MANA = re.compile(r"^(?:\{[^{}]+\}|\s)+$")

#: The two brace-wrapped symbols that are *not* mana: CR 107.5's tap symbol
#: `{T}` and CR 107.6's untap symbol `{Q}`, each of which "in an activation
#: cost means" an action rather than a payment from the mana pool. They match
#: `_ONLY_MANA`'s shape and would otherwise be handed to `ManaCost.parse`,
#: which rightly refuses them - so `total_cost_for_phrase` checks this first
#: and lets `cost_component_for_phrase` read them as the actions they are.
_ACTION_SYMBOL = re.compile(r"^\s*\{[TQ]\}\s*$", re.IGNORECASE)


#: Splits a printed cost on its commas, or on a joining "and" with no comma at
#: all - "pay 1 life and exile a blue card from your hand" (Force of Will's
#: pitch cost) never has one. A run of mana symbols never contains the word
#: "and", so this never cuts one of those in half.
_COST_PHRASE_SEPARATOR = re.compile(r",\s*|\s+and\s+")


def _split_cost_phrase(phrase: str) -> list[str]:
    """Split a printed cost into its components, keeping mana symbols whole."""
    parts = _COST_PHRASE_SEPARATOR.split(phrase.strip().rstrip("."))
    return [part.strip() for part in parts if part.strip()]


from ._common import (  # noqa: E402
    _PHRASE_PAY_LIFE,
    _QUALITY_CONNECTORS,
    _TYPE_WORDS,
    ANY_COUNTER_KIND,
)
from .components import (  # noqa: E402
    CostModifierKind,
    _cost_count,
    behold_cost,
    collect_evidence_cost,
    discard_cost,
    exert_cost,
    exile_and_pay_mana_cost_cost,
    exile_cost,
    mill_cost,
    pay_life_cost,
    place_counters_cost,
    remove_counters_cost,
    return_to_hand_cost,
    reveal_cost,
    sacrifice_cost,
    tap_cost,
    untap_cost,
    waterbend_mana_cost,
)
from .payment import pay_repeated_symbol_mana_cost  # noqa: E402
