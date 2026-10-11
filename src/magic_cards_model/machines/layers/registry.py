from __future__ import annotations

import re
from collections.abc import Sequence

from ...models.card import Color, Supertype, Type
from ...models.card_state import (
    CardState,
    ChoiceKind,
    Counter,
)
from ...models.zone import Zone
from .apply import EffectBuilder


def _humility(
    source: CardState,
    timestamp: int,
    targets: Sequence[CardState],
    context: LayerContext,
) -> list[ContinuousEffect]:
    """ "All creatures lose all abilities and have base power and toughness 1/1."

    One ability, two layers: the removal is layer 6 (CR 613.1f) and the base P/T
    is 7b (CR 613.4b), because "base power and toughness" sets a value
    (CR 208.4a). Both parts share `source_ability`, so once either has started
    applying, removing Humility's own ability cannot stop the other (CR 613.6).
    """
    text = "All creatures lose all abilities and have base power and toughness 1/1."
    return [
        ContinuousEffect(
            description="Humility: creatures lose all abilities",
            layer=Layer.ABILITY,
            timestamp=timestamp,
            source_id=source.id,
            source_ability=text,
            selector=every_creature,
            modification=lose_all_abilities,
        ),
        ContinuousEffect(
            description="Humility: creatures have base P/T 1/1",
            layer=Layer.POWER_TOUGHNESS,
            sublayer=Sublayer.SET,
            timestamp=timestamp,
            source_id=source.id,
            source_ability=text,
            selector=every_creature,
            modification=set_power_toughness(1, 1),
        ),
    ]


def _opalescence(
    source: CardState,
    timestamp: int,
    targets: Sequence[CardState],
    context: LayerContext,
) -> list[ContinuousEffect]:
    """ "Each other non-Aura enchantment is a creature ... base P/T equal to its mana value."

    Layer 4 for the type (CR 613.1d) and 7b for the P/T (CR 613.4b). Note that
    Opalescence excludes itself, so Humility - an enchantment - becomes a
    creature and falls under its own ability, while Opalescence does not.
    """
    text = (
        "Each other non-Aura enchantment is a creature in addition to its other types "
        "and has base power and base toughness each equal to its mana value."
    )
    selector = other_non_aura_enchantments(source.id)
    return [
        ContinuousEffect(
            description="Opalescence: other non-Aura enchantments are creatures",
            layer=Layer.TYPE,
            timestamp=timestamp,
            source_id=source.id,
            source_ability=text,
            selector=selector,
            modification=add_type(Type.CREATURE),
        ),
        ContinuousEffect(
            description="Opalescence: base P/T equal to mana value",
            layer=Layer.POWER_TOUGHNESS,
            sublayer=Sublayer.SET,
            timestamp=timestamp,
            source_id=source.id,
            source_ability=text,
            selector=selector,
            modification=set_power_toughness_to_mana_value,
        ),
    ]


#: "Nonbasic lands are Mountains." (Blood Moon) and "Each land is a Swamp in
#: addition to its other land types." (Urborg, Tomb of Yawgmoth) are no longer
#: hand-written here - both are `_parse_static_layer_sentence`'s generalised
#: shapes now, read off whichever card prints them. Harbinger of the Seas
#: ("Nonbasic lands are Islands.") and Yavimaya, Cradle of Growth ("Each land
#: is a Forest ...") are the cards that were silently doing nothing while the
#: shape was keyed by name.


#: "Creatures you control get +1/+1." (Glorious Anthem) and "Target creature
#: gets +3/+3 until end of turn." (Giant Growth) are no longer hand-written
#: here - both are `parsed_layer_effects`'s generalised shapes now. See
#: `test_layer_effects_registry_is_minimal.py`.


def _twisted_image(
    source: CardState,
    timestamp: int,
    targets: Sequence[CardState],
    context: LayerContext,
) -> list[ContinuousEffect]:
    """ "Switch target creature's power and toughness until end of turn." - 7d."""
    return [
        ContinuousEffect(
            description=f"Twisted Image: switch {target.name}'s power and toughness",
            layer=Layer.POWER_TOUGHNESS,
            sublayer=Sublayer.SWITCH,
            timestamp=timestamp,
            duration=Duration.UNTIL_END_OF_TURN,
            selector=only_this_incarnation(target, target.zone_change_stamp),
            modification=switch_power_toughness,
        )
        for target in targets
    ]


#: "Lands you control are every basic land type in addition to their other
#: types." (Dryad of the Ilysian Grove) is no longer hand-written here either -
#: it is `_lands_are_every_basic_type_builder`'s shape, which is what lets
#: Leyline of the Guildpact, printing the identical sentence, generate it too.
#: The Dryad's other line, "You may play an additional land on each of your
#: turns", is CR 611.3d's rule-modifying grant rather than a continuous effect
#: in any of the seven layers, and is read by `additional_land_plays_of_line`.


def _dress_down(
    source: CardState,
    timestamp: int,
    targets: Sequence[CardState],
    context: LayerContext,
) -> list[ContinuousEffect]:
    """ "Creatures lose all abilities." - layer 6 (CR 613.1f).

    Dress Down is an Enchantment and not a creature, so unlike Humility it does
    not strip its own ability. Its other three lines - flash, the enters-trigger
    and the end step sacrifice - are not continuous effects and are not modelled
    here.
    """
    text = "Creatures lose all abilities."
    return [
        ContinuousEffect(
            description="Dress Down: creatures lose all abilities",
            layer=Layer.ABILITY,
            timestamp=timestamp,
            source_id=source.id,
            source_ability=text,
            selector=every_creature,
            modification=lose_all_abilities,
        )
    ]


#: "Other creatures you control get +2/+2. Creatures your opponents control
#: get -2/-2." (Elesh Norn, Grand Cenobite) is no longer hand-written here -
#: both sentences are `parsed_layer_effects`'s anthem shape. Her own
#: "Vigilance" line is a printed keyword, not a continuous effect, so it needs
#: no entry at all.


def _tarmogoyf(
    source: CardState,
    timestamp: int,
    targets: Sequence[CardState],
    context: LayerContext,
) -> list[ContinuousEffect]:
    """ "Tarmogoyf's power is equal to the number of card types among cards in all
    graveyards and its toughness is equal to that number plus 1."

    A characteristic-defining ability (CR 604.3, CR 604.3a) - it defines the
    card's own power and toughness, is printed on the card it affects, and is
    not conditional - so it applies in sublayer 7a (CR 613.4a) ahead of every
    other power/toughness effect, whatever the timestamps say.

    The number is counted off `context.graveyards` when the effect is built,
    because the layer engine only ever sees the battlefield. Card types are the
    CR 300.1 list, so a creature land in a graveyard counts twice over.

    Being an ability, it can be removed in layer 6 (CR 613.1f) - by Dress Down
    or Humility - and then there is no value for either half, which CR 208.5
    reads as 0.
    """
    text = (
        "Tarmogoyf's power is equal to the number of card types among cards in "
        "all graveyards and its toughness is equal to that number plus 1."
    )
    types = count_card_types(context.graveyards)
    return [
        ContinuousEffect(
            description=f"Tarmogoyf: {types}/{types + 1} from card types in all graveyards",
            layer=Layer.POWER_TOUGHNESS,
            sublayer=Sublayer.CHARACTERISTIC_DEFINING,
            characteristic_defining=True,
            timestamp=timestamp,
            source_id=source.id,
            source_ability=text,
            selector=_only(source.id),
            modification=define_power_toughness(FixedCount(value=types), 0, 1),
        )
    ]


def _omnath_locus_of_mana(
    source: CardState,
    timestamp: int,
    targets: Sequence[CardState],
    context: LayerContext,
) -> list[ContinuousEffect]:
    """ "Omnath gets +1/+1 for each unspent green mana you have."

    Sublayer 7c (CR 613.4c: "modify power and/or toughness ... don't set"),
    not the characteristic-defining 7a of Tarmogoyf or Boneyard Wurm - Omnath
    is a printed 1/1 and this *adds* to that, so an empty pool leaves a 1/1
    rather than a 0/0. There is no duration: CR 611.3 gives a static ability's
    own continuous effect exactly the life of the ability.

    The count is read off `context.unspent_mana_of` at build time, and the
    board is rebuilt on every call (CR 613.5), so this tracks the pool live.
    That is the whole of DDR#955: with four green floating during CR 601.2h's
    payment, Omnath really is a 5/5 at the moment it is sacrificed, and it is
    a 1/1 again once that mana is spent.

    "You" is CR 109.5's - the object's controller - which is also whose pool
    `unspent_mana_of` is asked for.
    """
    green = context.unspent_mana_of(source.controller, Color.GREEN)
    if green == 0:
        return []
    return [
        ContinuousEffect(
            description=f"Omnath, Locus of Mana: +{green}/+{green} from unspent green mana",
            layer=Layer.POWER_TOUGHNESS,
            sublayer=Sublayer.MODIFY,
            timestamp=timestamp,
            source_id=source.id,
            selector=_only(source.id),
            modification=modify_power_toughness(green, green),
        )
    ]


def _boneyard_wurm(
    source: CardState,
    timestamp: int,
    targets: Sequence[CardState],
    context: LayerContext,
) -> list[ContinuousEffect]:
    """ "Boneyard Wurm's power and toughness are each equal to the number of
    creature cards in your graveyard."

    A characteristic-defining ability (CR 604.3, CR 604.3a) in sublayer 7a
    (CR 613.4a), like Tarmogoyf's - but it counts *creature cards*, not card
    types (CR 300.1), and only **your** graveyard, not every graveyard, so a
    stack of Bears in the opponent's bin does not grow it. `context.graveyard_of`
    looks up the caster's own graveyard by controller, because unlike Tarmogoyf
    (whose count is the same for everyone) this one is a different number for
    every player it could be printed under.
    """
    text = (
        "Boneyard Wurm's power and toughness are each equal to the number of "
        "creature cards in your graveyard."
    )
    creatures = sum(1 for card in context.graveyard_of(source.controller) if card.is_creature)
    return [
        ContinuousEffect(
            description=(
                f"Boneyard Wurm: {creatures}/{creatures} from creature cards in your graveyard"
            ),
            layer=Layer.POWER_TOUGHNESS,
            sublayer=Sublayer.CHARACTERISTIC_DEFINING,
            characteristic_defining=True,
            timestamp=timestamp,
            source_id=source.id,
            source_ability=text,
            selector=_only(source.id),
            modification=define_power_toughness(FixedCount(value=creatures), 0, 0),
        )
    ]


def _nighthawk_scavenger(
    source: CardState,
    timestamp: int,
    targets: Sequence[CardState],
    context: LayerContext,
) -> list[ContinuousEffect]:
    """ "Nighthawk Scavenger's power is equal to 1 plus the number of card
    types among cards in your opponents' graveyards."

    A third graveyard-reading shape alongside Tarmogoyf's (every graveyard) and
    Boneyard Wurm's (your own): this one counts every graveyard *except* your
    own, which `context.opponents_graveyard_of` answers as the set difference
    of the other two. Its toughness box is a plain `3` (CR 208.1) - only power
    is a CDA - so this is `define_power`, not `define_power_toughness`, and the
    printed Flying/deathtouch/lifelink lines need no entry at all (CR 604.3:
    only the P/T sentence is the characteristic-defining ability).
    """
    text = (
        "Nighthawk Scavenger's power is equal to 1 plus the number of card "
        "types among cards in your opponents' graveyards."
    )
    types = count_card_types(context.opponents_graveyard_of(source.controller))
    return [
        ContinuousEffect(
            description=f"Nighthawk Scavenger: power 1+{types} from opponents' graveyards",
            layer=Layer.POWER_TOUGHNESS,
            sublayer=Sublayer.CHARACTERISTIC_DEFINING,
            characteristic_defining=True,
            timestamp=timestamp,
            source_id=source.id,
            source_ability=text,
            selector=_only(source.id),
            modification=define_power(FixedCount(value=types), 1),
        )
    ]


def _allosaurus_rider(
    source: CardState,
    timestamp: int,
    targets: Sequence[CardState],
    context: LayerContext,
) -> list[ContinuousEffect]:
    """ "Allosaurus Rider's power and toughness are each equal to 1 plus the number
    of lands you control."

    The second CDA in the registry, and the one that reads the *board* rather
    than a zone outside it: the lands are counted in sublayer 7a (CR 613.4a)
    against the board as layers 1-6 left it, so a land that stopped being a land
    in layer 4 (CR 613.1d) is not counted.

    Its alternative cost line is a cost, not a continuous effect, and lives in
    `machines/cost.py`'s world rather than this one.
    """
    text = (
        "Allosaurus Rider's power and toughness are each equal to 1 plus the "
        "number of lands you control."
    )
    return [
        ContinuousEffect(
            description="Allosaurus Rider: 1 plus the lands you control",
            layer=Layer.POWER_TOUGHNESS,
            sublayer=Sublayer.CHARACTERISTIC_DEFINING,
            characteristic_defining=True,
            timestamp=timestamp,
            source_id=source.id,
            source_ability=text,
            selector=_only(source.id),
            modification=define_power_toughness(count_lands_controlled_by(source.controller), 1, 1),
        )
    ]


#: "Target creature gets -5/-5 until end of turn." (Dismember) is no longer
#: hand-written here - `parsed_layer_effects`'s pump shape reads it, its
#: Phyrexian-mana reminder line stripped like any other reminder text.
#:
#: "{1}{G}: This creature gets +2/+2 until end of turn." (Basking Rootwalla)
#: likewise: the activation cost is stripped ahead of the sentence, and
#: `static_effects`'s untargeted call still produces nothing, exactly as this
#: hand-written version used to - the shape only ever fires with
#: `targets=[source]`, from `create_continuous_effect_of_ability`.


def _tishanas_tidebinder(
    source: CardState,
    timestamp: int,
    targets: Sequence[CardState],
    context: LayerContext,
) -> list[ContinuousEffect]:
    """ "That permanent loses all abilities for as long as this creature remains
    on the battlefield."

    Layer 6 (CR 613.1f), created by a resolving triggered ability (CR 611.2) and
    timestamped then (CR 613.7b). The duration is the "for as long as" form of
    CR 611.2b, so the effect carries a condition rather than an expiry: it holds
    while the Tidebinder is on the battlefield and stops the moment it is not.

    CR 611.2b's corner case is handled by `ContinuousEffects.create` rather than
    here - "If the 'for as long as' duration never starts, the effect does
    nothing", so a Tidebinder that is already gone when its trigger resolves
    creates nothing at all.

    `source` is the Tidebinder; `targets` is the permanent whose ability was
    countered. There is no `source_ability`, because this is not a static
    ability of the Tidebinder and CR 613.6 has nothing to switch off - the
    duration does that job instead.
    """
    return [
        ContinuousEffect(
            description=f"Tishana's Tidebinder: {target.name} loses all abilities",
            layer=Layer.ABILITY,
            timestamp=timestamp,
            duration=Duration.FOR_AS_LONG_AS,
            condition=_remains_on_the_battlefield(source),
            selector=only_this_incarnation(target, target.zone_change_stamp),
            modification=lose_all_abilities,
        )
        for target in targets
    ]


#: "Target creature gets +2/+2 until end of turn." (Mutagenic Growth) and
#: "Target creature gains double strike until end of turn." (Assault Strobe)
#: are no longer hand-written here - the pump and keyword-grant shapes of
#: `parsed_layer_effects` read both, trailing reminder text stripped as usual.
#:
#: Monstrous Rage's first sentence, "Target creature gets +2/+0 until end of
#: turn.", is the same pump shape; its second sentence, "Create a Monster Role
#: token attached to it.", is not a continuous effect at all and is correctly
#: left to `machines/effects.py`'s `monstrous_rage` (token creation, CR 111.10k,
#: CR 701.7a) - `parsed_layer_effects` reads sentence by sentence and simply
#: has nothing to say about the second one, exactly like Dryad of the Ilysian
#: Grove's land-drop line above.


def _remains_on_the_battlefield(permanent: CardState) -> Condition:
    """ "For as long as this creature remains on the battlefield" (CR 611.2b).

    The zone is asked each time the board is computed, so the effect ends the
    moment the permanent leaves - and CR 400.7 means a permanent that leaves and
    comes back is a new object, so the stamp is what keeps the condition false
    for the returning one rather than reading the id alone and getting it
    wrong the same way a bare `_only` selector would (see `only_this_
    incarnation`'s own docstring for the identical argument).
    """
    return RemainsOnBattlefield(card_id=permanent.id, stamp=permanent.zone_change_stamp)


#: Continuous effects by card name, for the shapes `parsed_layer_effects`
#: cannot read. `effects_for`
#: checks here first and falls back to the parser on a miss, so a card with
#: neither generates no effect, which is right for a vanilla creature and
#: silently wrong for anything with text `parsed_layer_effects` cannot read
#: either - see `LayerNotice`.
#:
#: Glorious Anthem, Giant Growth, Elesh Norn, Dismember, Basking Rootwalla,
#: Mutagenic Growth, Assault Strobe, and Monstrous Rage's pump are not here any
#: more - each was exactly one of `parsed_layer_effects`'s four generalised
#: shapes, read off the card's own oracle text instead. See
#: `test_layer_effects_registry_is_minimal.py`.
#:
#: Blood Moon, Urborg, Tomb of Yawgmoth and Dryad of the Ilysian Grove are gone
#: for the same reason and a sharper one: a *name* key is not what CR 604.2 or
#: CR 611.3b says generates a static ability's continuous effect. Every one of
#: those three sentences is printed on some other card too - Harbinger of the
#: Seas, Yavimaya, Cradle of Growth, Leyline of the Guildpact - and each of
#: those cards silently generated nothing, without even a `LayerNotice`,
#: because a board-wide sentence does not open the way the pump and anthem
#: shapes `_LOOKS_LIKE_LAYER_EFFECT_RE` watches for do. Keying by the sentence
#: closes the class rather than the two cards.
LAYER_EFFECTS: dict[str, EffectBuilder] = {
    "Humility": _humility,
    "Opalescence": _opalescence,
    "Twisted Image": _twisted_image,
    "Dress Down": _dress_down,
    # Relentless Rats' own "This creature gets +1/+1 for each other creature
    # on the battlefield named Relentless Rats." is not entered here any
    # more: `_SELF_PUMP_PER_OTHER_CREATURE_NAMED_RE` reads the shape off the
    # card's own printed text with no card-name check at all, so a future
    # card sharing the template with a different name or magnitude - Seven
    # Dwarves among them - is covered for free.
    "Tarmogoyf": _tarmogoyf,
    "Boneyard Wurm": _boneyard_wurm,
    # "Omnath gets +1/+1 for each unspent green mana you have." A live count
    # of something that is not on the battlefield and not in a graveyard
    # either - the controller's own mana pool - so no generalised shape reads
    # it and the row is not dead weight.
    "Omnath, Locus of Mana": _omnath_locus_of_mana,
    "Nighthawk Scavenger": _nighthawk_scavenger,
    "Allosaurus Rider": _allosaurus_rider,
    "Tishana's Tidebinder": _tishanas_tidebinder,
    # "Violent Urge" has no row: its pump and first strike are the
    # generalised shapes, and its *Delirium* rider is read off the template
    # by `machines/effects.py`'s conditional referent rider
    # (`_parse_conditional_referent_clause`).
    # "Monstrous Rage" has no row: its pump is the generalised shape, read off
    # its own oracle text by the parser fallback; its token creation is
    # `machines/effects.py`'s job (CR 111.10k, CR 701.7a).
    # The Monster Role token of CR 111.10k had a row here until "Enchanted
    # creature ..." joined "Equipped creature ..." in
    # `_ATTACHED_CREATURE_STATIC_RE`. The rule states the token's whole text -
    # "enchant creature and 'Enchanted creature gets +1/+1 and has trample.'" -
    # and `machines/tokens.py` synthesises it onto the token's `Card`
    # (CR 111.3), so the parser now reads it off the token exactly as it reads
    # Rancor off a card, through the same `attached_to` link. The row is gone
    # because `test_layer_effects_registry_is_minimal.py` is right that a row
    # the parser can reach is dead weight.
}


def _granted_ability_effects(source: CardState, *, static_only: bool) -> EffectBuilder | None:
    """A builder read off an ability *granted* to this permanent (CR 613.1f).

    `CardState.granted_ability_texts` holds the quoted lines another
    permanent's layer-6 grant is putting on this one, printed exactly as the
    granting card quotes them - Umbral Mantle's "{3}, {Q}: This creature gets
    +2/+2 until end of turn." on an equipped Llanowar Elves. `LAYER_EFFECTS`
    is keyed by card name and the parser fallback reads the source's own
    printing, so neither can reach such a line: "Llanowar Elves" has no row
    and never will, because that pump was never printed on it.

    Consulted on both paths, `static_only` passed straight through to
    `parsed_layer_effects` exactly as `effects_for`'s own two other routes
    already do: on the resolution path (`static_only=False`) a granted
    *activated* ability's own body is fair game the same way it always was -
    Umbral Mantle's own case, and Iron Fist, Living Weapon's self-granted
    `"{T}: ..."`, both read only once that ability actually resolves. On the
    battlefield sweep (`static_only=True`, `_effect_sentences`'s own gate)
    only a `StaticAbility`-shaped granted line is read at all, so an
    activated ability's body is refused here exactly as a printed one would
    be (CR 611.3 never covers CR 602.1) - it does not leave the Elves
    permanently +2/+2 without anybody paying {3}. Ms. Marvel, Kamala Khan's
    own granted "'s base power is equal to the number of cards in your
    hand." is the reader that needs the sweep to see a granted line at all:
    a static/CDA sentence a resolved trigger put here (CR 613.1f) is exactly
    as much "this permanent's own static contribution" (CR 611.3) as one
    printed on the card would be, for as long as the grant that added it
    keeps holding.

    The first granted line that parses wins. A caller that knows *which*
    granted ability is resolving should say so with `effects_for`'s
    `ability_text` instead, which is checked first and is exact; this fallback
    exists because the resolution path currently hands `effects_for` only the
    permanent, and a permanent carrying two different granted quoted layer
    abilities at once would need it.
    """
    legendary = Supertype.LEGENDARY in source.card.supertypes
    for text in source.granted_ability_texts:
        builder = parsed_layer_effects(
            text, static_only=static_only, card_name=source.name, legendary=legendary
        )
        if builder is not None:
            return builder
    return None


_MODE_BULLET_LINE_RE = re.compile(r"^•\s*(?P<mode>[A-Z][\w'-]*)\s+—\s+(?P<body>.+)$", re.DOTALL)
_CHOOSES_MODE_LINE_RE = re.compile(r"\benters, choose [A-Z][\w'-]*(?:, [A-Z][\w'-]*)*,? or [A-Z]")


def _mode_gated_text(text: str | None, source: CardState) -> tuple[str | None, dict[str, str]]:
    """CR 614.12a: under an as-enters "choose Jeskai or Temur" line, a
    "• Temur — <static>" bullet is in effect only while that mode is the
    recorded choice (Frostcliff Siege's anthem). The chosen bullet reads as
    its bare body and every other bullet is dropped, so the ordinary
    sentence parser sees exactly the lines the permanent has. Triggered
    bullets are gated separately (`abilities._parse_line_mode_gated`) and are
    never read by the static sweep either way. Also returns each kept body ->
    its printed bullet line, the ability text CR 613.6 looks for on the
    permanent."""
    if not text or "•" not in text or not _CHOOSES_MODE_LINE_RE.search(text):
        return text, {}
    choice = source.choice
    chosen = choice.value.lower() if choice and choice.kind is ChoiceKind.MODE else None
    kept: list[str] = []
    printed: dict[str, str] = {}
    for line in text.split("\n"):
        bullet = _MODE_BULLET_LINE_RE.match(line.strip())
        if bullet is None:
            kept.append(line)
        elif bullet.group("mode").lower() == chosen:
            kept.append(bullet.group("body"))
            printed[bullet.group("body")] = line.strip()
    return "\n".join(kept), printed


def _combined_builders(first: EffectBuilder, second: EffectBuilder) -> EffectBuilder:
    def combined(
        source: CardState,
        timestamp: int,
        targets: Sequence[CardState],
        context: LayerContext,
    ) -> list[ContinuousEffect]:
        return [*first(source, timestamp, targets, context), *second(source, timestamp, targets, context)]

    return combined


def effects_for(
    source: CardState,
    timestamp: int,
    targets: Sequence[CardState] = (),
    context: LayerContext | None = None,
    notices: list[LayerNotice] | None = None,
    *,
    static_only: bool = False,
    ability_text: str | None = None,
) -> list[ContinuousEffect]:
    """The continuous effects one card generates, or none if it is not registered
    and its own oracle text is not one of `parsed_layer_effects`'s shapes either.

    `context` carries what a card reads outside the battlefield - the graveyards
    Tarmogoyf counts. Leave it out for every other card.

    `LAYER_EFFECTS` is tried first, so an explicit row always wins over the
    parser. On a miss, `notices` - when a caller passes one, which
    `ContinuousEffects` always does - collects a `LayerNotice` for oracle text
    that reads like a pump/keyword/anthem shape but did not fully parse,
    rather than the card silently doing nothing.

    This one function serves two different callers with two different
    questions, which is what `static_only` tells apart:

    - `static_effects` (the battlefield sweep, called for every permanent
      every time the board is computed, CR 613.5) asks "does this
      permanent's own *static* ability (CR 611.3) generate a continuous
      effect" - `static_only=True`, since a triggered or activated ability's
      own effect body is never this permanent's static contribution, whether
      or not it happens to parse. Without this, Kraul Harpooner's undergrowth
      pump - "This creature gets +X/+0 ... where X is the number of creature
      cards in your graveyard", fully handled by its own dedicated
      `_parse_undergrowth_pump_and_fight_clause` when the trigger actually
      resolves - used to record a false `LayerNotice` here, because the sweep
      read that triggered ability's own sentence and it looks like (but is
      not) one of this module's generalised pump shapes.
    - `ContinuousEffects.create` (a spell or ability that has just resolved,
      CR 611.2) asks "what does *this resolving ability's own effect* say" -
      `static_only=False` (the default), because the resolving ability may
      well be the `TriggeredAbility`/`ActivatedAbility` whose body this
      builds the effect from (Oliphaunt's attack trigger, Basking Rootwalla's
      activated pump): restricting to `StaticAbility` bodies there would make
      `create_continuous_effect_of_ability` blind to the exact text it exists
      to read.

    `ability_text` is the resolving ability's *own* text, when there is one -
    `machines/effects.create_continuous_effect_of_ability` passes it. Without
    it, both routes into a builder key off the source permanent: its name in
    `LAYER_EFFECTS`, or its own oracle text in the parser. Neither can ever
    reach an ability **granted** to that permanent by something else
    (CR 613.1f: "Layer 6: Ability-adding effects, keyword counters,
    ability-removing effects ... are applied"). Umbral Mantle's quoted "{3},
    {Q}: This creature gets +2/+2 until end of turn." is on Llanowar Elves,
    and "Llanowar Elves" has no `LAYER_EFFECTS` row and never will, because
    the pump was never printed on it - so the ability resolved and did
    nothing.

    It is tried *after* the name row and *before* the source's own text, which
    is the order that changes nothing already working: a card with a row keeps
    it, and a card whose own text carries the ability reaches the same builder
    either way (the ability text is a subset of that text). The only new
    outcome is the granted one.
    """
    legendary = Supertype.LEGENDARY in source.card.supertypes
    builder = LAYER_EFFECTS.get(source.name)
    if builder is None and ability_text:
        builder = parsed_layer_effects(
            ability_text, static_only=static_only, card_name=source.name, legendary=legendary
        )
    granted_builder: EffectBuilder | None = None
    if builder is None:
        granted_builder = _granted_ability_effects(source, static_only=static_only)
        builder = granted_builder
    # `oracle_text` reads the up face (CR 712.8d/712.8f); `card.oracle_text`
    # is the raw Scryfall field, null for a modal-DFC/transform permanent -
    # same family as `effect_for`'s fix in `Game.resolve_top`. Without this,
    # every layer-computed static/pump/anthem ability on such a permanent's
    # face-up side went unread.
    #
    # `class_ability_text` is `oracle_text` for everything that is not a Class
    # (CR 303.6), and for a Class it drops the paragraphs above its current
    # level - CR 716.2a's own gate. Without that, Innkeeper's Talent's level-2
    # "Permanents you control with counters on them have ward {1}" would be
    # read off a level-1 Class that does not have the ability yet.
    text, printed_bullets = _mode_gated_text(source.class_ability_text, source)
    # A keyword's own static ability has no printed sentence for the parser to
    # read, so it is added beside whatever the text produced.
    keyword_statics = (
        [
            *_impending_not_a_creature(source, timestamp),
            *_suspected_abilities(source, timestamp),
            *_station_symbol_effects(source, timestamp),
            *_level_symbol_effects(source, timestamp),
            *_blitz_effects(source, timestamp),
            *_reconfigure_effects(source, timestamp),
        ]
        if static_only
        else []
    )
    if builder is None or granted_builder is not None:
        # A granted static line (CR 613.1f) rides *beside* the permanent's own
        # printed statics, never instead of them: Sedge Sliver is granted a
        # conditional pump by its own "All Sliver creatures have ..." line and
        # still has to apply that line.
        own = parsed_layer_effects(
            text, static_only=static_only, card_name=source.name, legendary=legendary
        )
        if builder is None:
            builder = own
        elif own is not None:
            builder = _combined_builders(builder, own)
    if builder is None:
        if (
            notices is not None
            and looks_like_unparsed_layer_effect(
                text, static_only=static_only, card_name=source.name, legendary=legendary
            )
            # The board is recomputed continually (CR 613.5), so the same
            # unreadable permanent is asked about over and over - record it
            # once, not once per computation.
            and not any(notice.source_id == source.id for notice in notices)
        ):
            notices.append(
                LayerNotice(source_id=source.id, source_name=source.name, text=text or "")
            )
        return keyword_statics
    built = [*builder(source, timestamp, targets, context or LayerContext()), *keyword_statics]
    # `order` is this call's own answer to "which of these came first" - set
    # here, once, on the builder's actual output order, rather than trusting
    # every builder (a `LAYER_EFFECTS` row, the generic parser's per-sentence
    # `combined`, a granted-ability grant) to have stamped it itself. See
    # `ContinuousEffect.order`.
    return [
        effect.model_copy(
            update={
                "order": index,
                "source_ability": printed_bullets.get(
                    effect.source_ability or "", effect.source_ability
                ),
            }
        )
        for index, effect in enumerate(built)
    ]


def _impending_not_a_creature(source: CardState, timestamp: int) -> list[ContinuousEffect]:
    """CR 702.176a's third ability: "As long as this permanent's impending cost
    was paid and it has a time counter on it, it's not a creature."

    A static ability that functions on the battlefield, so a type-changing
    effect in layer 4 (CR 613.1d) with the permanent's own timestamp (CR
    613.7a). The "as long as" needs no stored condition: static effects are
    rebuilt every time the board is computed (CR 613.5), so the moment the
    last time counter comes off - the end step trigger, or anything else that
    removes it - this is simply not built any more. The paid half is
    `CardState.cast_with_keyword`, which belongs to this object only (CR
    400.7), so a blinked Overlord is a creature again.

    The keyword is read off the printing, not off the computed abilities: an
    ability-removing effect is layer 6, and CR 613.6 keeps a layer 4 effect
    that has already started applying from being switched off by it.
    """
    from ..abilities import keyword_abilities  # imported here: kept beside its one use

    if source.zone is not Zone.BATTLEFIELD:
        return []
    if (source.cast_with_keyword or "").lower() != "impending":
        return []
    if source.counter_count(Counter.TIME) <= 0:
        return []
    if not any(
        ability.canonical.lower() == "impending" for ability in keyword_abilities(source.card)
    ):
        return []
    return [
        ContinuousEffect(
            description=f"{source.name}: not a creature while it has a time counter (CR 702.176a)",
            layer=Layer.TYPE,
            timestamp=timestamp,
            source_id=source.id,
            selector=_only(source.id),
            modification=RemoveType(card_type=Type.CREATURE),
        )
    ]


def _station_symbol_effects(source: CardState, timestamp: int) -> list[ContinuousEffect]:
    """CR 721.2's station symbols, as the static abilities they are.

    CR 721.2a: "'{N+}[abilities]' means 'As long as this permanent has N or
    more charge counters on it, it has [abilities].'" - a layer 6 addition
    (CR 613.1f) of every ability printed in the striation, symbol taken off.
    CR 721.2b: "'{N+}[abilities][P/T]' means '... it has [abilities] and is a
    creature with base power and toughness [P/T] in addition to its other
    types.'" - a layer 4 type addition (CR 613.1d) and a layer 7b base P/T
    (CR 613.4b) for the striation holding the printed box
    (`abilities.station_creature_threshold`).

    Rebuilt with every static effect each time the board is computed
    (CR 613.5), so the moment the charge counters reach N the striation is on
    and the moment they fall below it it is off; stamped with the permanent's
    own timestamp (CR 613.7a). Read off the printing (the up face), like
    `_impending_not_a_creature`.
    """
    from ..abilities import station_creature_threshold, station_striations

    if source.zone is not Zone.BATTLEFIELD:
        return []
    text = source.oracle_text or ""
    striations = station_striations(text.splitlines())
    if not any(threshold is not None for _, threshold in striations):
        return []
    charge = source.counter_count(Counter.CHARGE)
    effects: list[ContinuousEffect] = []
    creature_at = station_creature_threshold(source.card, text)
    if creature_at is not None and charge >= creature_at:
        power = _as_number(source.card.power)
        toughness = _as_number(source.card.toughness)
        effects.append(
            ContinuousEffect(
                description=f"{source.name}: a creature at {creature_at}+ (CR 721.2b)",
                layer=Layer.TYPE,
                timestamp=timestamp,
                source_id=source.id,
                selector=_only(source.id),
                modification=AddType(card_type=Type.CREATURE),
            )
        )
        if power is not None and toughness is not None:
            effects.append(
                ContinuousEffect(
                    description=(
                        f"{source.name}: base {power}/{toughness} at {creature_at}+ (CR 721.2b)"
                    ),
                    layer=Layer.POWER_TOUGHNESS,
                    sublayer=Sublayer.SET,
                    timestamp=timestamp,
                    source_id=source.id,
                    selector=_only(source.id),
                    modification=SetPowerToughness(power=power, toughness=toughness),
                )
            )
    for line, threshold in striations:
        if threshold is None or charge < threshold or not line:
            continue
        effects.append(
            ContinuousEffect(
                description=f"{source.name}: {line!r} at {threshold}+ (CR 721.2a)",
                layer=Layer.ABILITY,
                timestamp=timestamp,
                source_id=source.id,
                selector=_only(source.id),
                modification=grant_ability(line),
            )
        )
    return effects


def _level_symbol_effects(source: CardState, timestamp: int) -> list[ContinuousEffect]:
    """CR 711.2a/b's level symbols, as the static abilities they are -
    `machines/level_up.level_symbol_effects` (imported here: that module
    builds on `machines/keywords.py`, which imports this package)."""
    if not source.is_leveler:
        return []
    from ..level_up import level_symbol_effects

    return level_symbol_effects(source, timestamp)


def _blitz_effects(source: CardState, timestamp: int) -> list[ContinuousEffect]:
    """CR 702.152a's battlefield static, `machines/blitz.blitz_static_effects`
    (imported here for the same cycle `_level_symbol_effects` names)."""
    if not source.cast_with_keyword:
        return []
    from ..blitz import blitz_static_effects

    return blitz_static_effects(source, timestamp)


def _reconfigure_effects(source: CardState, timestamp: int) -> list[ContinuousEffect]:
    """CR 702.151b's not-a-creature, `machines/reconfigure.reconfigure_not_a_
    creature` (imported here for the same cycle `_level_symbol_effects` names)."""
    if source.attached_to is None:
        return []
    from ..reconfigure import reconfigure_not_a_creature

    return reconfigure_not_a_creature(source, timestamp)


#: CR 701.60c: "A suspected permanent has menace and 'This creature can't
#: block' for as long as it's suspected."
SUSPECTED_ABILITY_TEXTS: tuple[str, ...] = ("Menace", "This creature can't block.")


def _suspected_abilities(source: CardState, timestamp: int) -> list[ContinuousEffect]:
    """CR 701.60c's two abilities, as layer 6 additions (CR 613.1f) for as long
    as `CardState.suspected` is set. Rebuilt with every static effect each time
    the board is computed (CR 613.5), so the moment the designation ends - the
    permanent leaves (CR 701.60a), or an effect says it is "no longer
    suspected" - they are simply not built any more. Stamped with the
    permanent's own timestamp, like every static effect it generates."""
    if source.zone is not Zone.BATTLEFIELD or not source.suspected:
        return []
    return [
        ContinuousEffect(
            description=f"{source.name}: suspected, has {text!r} (CR 701.60c)",
            layer=Layer.ABILITY,
            timestamp=timestamp,
            source_id=source.id,
            selector=_only(source.id),
            modification=grant_ability(text),
        )
        for text in SUSPECTED_ABILITY_TEXTS
    ]


def static_effects(
    permanents: Sequence[CardState],
    context: LayerContext | None = None,
    notices: list[LayerNotice] | None = None,
) -> list[ContinuousEffect]:
    """Every registered static effect on the battlefield, timestamped by order.

    CR 613.7a: a continuous effect from a static ability has the timestamp of
    the permanent it is on, so passing the permanents in the order they entered
    the battlefield gives the right timestamp order.
    """
    shared = context or LayerContext()
    sync_granted_ability_texts(permanents)
    effects: list[ContinuousEffect] = []
    for timestamp, permanent in enumerate(permanents, start=1):
        effects.extend(effects_for(permanent, timestamp, (), shared, notices, static_only=True))
    return effects


from .apply import LayerContext  # noqa: E402
from .model import (  # noqa: E402
    AddType,
    Condition,
    ContinuousEffect,
    Duration,
    FixedCount,
    Layer,
    LayerNotice,
    RemainsOnBattlefield,
    RemoveType,
    SetPowerToughness,
    Sublayer,
    _only,
    add_type,
    count_card_types,
    count_lands_controlled_by,
    define_power,
    define_power_toughness,
    every_creature,
    grant_ability,
    lose_all_abilities,
    modify_power_toughness,
    only_this_incarnation,
    other_non_aura_enchantments,
    set_power_toughness,
    set_power_toughness_to_mana_value,
    switch_power_toughness,
)
from .parse import (  # noqa: E402
    _as_number,
    looks_like_unparsed_layer_effect,
    parsed_layer_effects,
    sync_granted_ability_texts,
)
