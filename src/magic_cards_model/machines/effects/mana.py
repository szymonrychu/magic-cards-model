import re
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

from ...data.subtypes import subtype_vocabulary
from ...models.card import Color
from ...models.card_state import (
    CardState,
    ChoiceKind,
)
from ...models.mana import ManaCost, ManaRestriction, ManaRetentionScope
from ...models.zone import Zone
from ...numbers import (
    count_pattern,
    parse_count,
    where_x_pattern,
)
from ..abilities import (
    parse_triggered_mana,
)
from ..cost import (
    is_snow_source,
    spend_restriction,
)
from ..decisions import source_id_of
from ..modes import (
    substitute_x,
)
from ..triggers import (
    AbilityOnStack,
    triggered_mana_count,
    triggered_mana_recipient,
)

if TYPE_CHECKING:
    from ...models.game import Game, StackObject
from ._chains import ABILITY_TEXT, FORWARD, MIXED_CLAUSE
from ._common import AbilityEffect, TargetedClause

#: "..., where X is the amount of mana spent to cast that spell." - Aberrant
#: Manawurm's and Shantotto, Tactician Magician's own cast-trigger pump: X is
#: never the ability's own announced X (CR 107.3a - a triggered ability
#: announces none) but CR 601.2h's mana spent on the spell that *triggered*
#: it, `AbilityOnStack.event`'s own subject, read the same anaphoric way
#: `machines/triggers.intervening_if_holds`'s self-referential "no mana was
#: spent to cast it" already reads it for a different object.
_CAST_TRIGGER_MANA_SPENT_WHERE_X_RE = re.compile(
    r",?\s*where x is the amount of mana spent to cast that spell", re.IGNORECASE
)


def _cast_trigger_mana_spent_x_value(game: "Game", ability: AbilityOnStack) -> int | None:
    """The mana spent (CR 601.2h) casting the spell that triggered `ability`,
    or `None` when there is no cast-trigger event or no record of it."""
    record = _cast_trigger_record(game, ability)
    return None if record is None else record.total_mana_spent


def _cast_trigger_mana_spent_x_ability_text(game: "Game", ability: AbilityOnStack) -> str | None:
    """`ability.ability.text` with X substituted for the mana spent on the
    spell that triggered it, and the "where X is ..." definition dropped -
    `_CAST_TRIGGER_MANA_SPENT_WHERE_X_RE`'s banner above - or `None` when the
    text does not carry that definition at all, or the value cannot be
    read (in which case the ordinary, unsubstituted path below is left to
    fail closed exactly as it already does for any other unreadable X).

    The definition is stripped *before* `substitute_x` runs, not after: once
    substituted, "where X is ..." would read "where `<n>` is ..." and no
    longer match `where_x_pattern()`'s own literal "where x is", which would
    make `_PUMP_RE` refuse the whole sentence instead of reading the plain
    "gets +`<n>`/+0 until end of turn." it has become.
    """
    text = getattr(ability.ability, "text", None)
    if not isinstance(text, str) or _CAST_TRIGGER_MANA_SPENT_WHERE_X_RE.search(text) is None:
        return None
    x = _cast_trigger_mana_spent_x_value(game, ability)
    if x is None:
        return None
    return substitute_x(_CAST_TRIGGER_MANA_SPENT_WHERE_X_RE.sub("", text), x)


def _exact_mana_cost_matcher(costs_text: str) -> Callable[[CardState], bool] | None:
    """Whether a card's mana cost is one of the printed costs in `costs_text`.

    CR 202.1: "A card's mana cost is indicated by mana symbols near the top of
    the card." So this compares symbols, never mana value: Engineered
    Explosives' {X} is not {0} even though CR 202.3e treats X as 0 for its
    mana value outside the stack, Swooping Lookout's {W} is not {1}, and a card
    with no mana cost (CR 202.1b) matches no cost at all. Symbols are compared
    as a multiset, so a cost printed in a different order still matches.

    `None` when a printed cost carries a symbol that is not a mana symbol
    (`ManaCost.try_parse`), so the description is refused rather than read.
    """
    parsed = [ManaCost.try_parse(cost) for cost in re.findall(r"(?:\{[^}\s]+\})+", costs_text)]
    if any(cost is None for cost in parsed):
        return None
    wanted = [sorted(str(symbol) for symbol in cost.symbols) for cost in parsed if cost is not None]

    def matches(state: CardState) -> bool:
        printed = state.mana_cost
        if not printed:
            return False
        symbols = sorted(str(symbol) for symbol in ManaCost.parse(printed).symbols)
        return symbols in wanted

    return matches


def _and_has_exact_mana_cost(
    base: Callable[[CardState], bool], exact: Callable[[CardState], bool]
) -> Callable[[CardState], bool]:
    def matches(state: CardState) -> bool:
        return base(state) and exact(state)

    return matches


#: "If that land is a `<basic land type>`, add `<mana>`." - Koth, the
#: Geomancer's own rider on its own landfall trigger, CR 400.7's "that land"
#: pointing at whichever permanent this ability's own `TriggerEvent.subject_
#: id` names (the land that just entered), read the same way `_parse_untap_
#: trigger_subject_clause` already reads a trigger's own subject with no
#: target and no self-reference. No off-set second printing of this exact
#: wording was found; recorded rather than asserted in
#: `docs/engine-coverage.md`, and the reader is general over land type and
#: mana symbol rather than fitted to "Mountain"/{R} alone.
_IF_THAT_LAND_IS_A_ADD_MANA_RE = re.compile(
    r"^if that land is an? (?P<type>[a-z]+), add (?P<mana>(?:\{[wubrgc]\}\s*)+)$",
    re.IGNORECASE,
)


def _parse_landfall_type_then_add_mana_clause_pair(
    first: str, second: str, *, for_spell: bool
) -> TargetedClause | None:
    """ "`<antecedent>`. If that land is a `<type>`, add `<mana>`." - see the
    banner above.
    """
    if for_spell:
        return None
    match = _IF_THAT_LAND_IS_A_ADD_MANA_RE.fullmatch(second.strip().rstrip("."))
    if match is None:
        return None
    antecedent = _parse_mixed_clause(first, for_spell=for_spell)
    if antecedent is None:
        return None
    land_type = match.group("type").strip().title()
    # CR 205.3i's basic land types, or any other printed land subtype -
    # rejected only when the word is not one at all (never a guess).
    if land_type.lower() not in subtype_vocabulary():
        return None
    symbols = [
        sym.strip("{}").upper()
        for sym in re.findall(r"\{([wubrgc])\}", match.group("mana"), re.IGNORECASE)
    ]
    if not symbols:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        antecedent(game, ability)
        event = ability.event
        if event is None or event.subject_id is None:
            return
        subject = game.find_by_id(event.subject_id)
        if subject is None or subject.zone is not Zone.BATTLEFIELD:
            return
        if land_type not in game.characteristics_of(subject).subtypes:
            return
        player_pool = game.player(ability.controller).mana_pool
        for symbol in symbols:
            player_pool.add(Color(symbol))

    return effect


@ABILITY_TEXT.rung(
    "s22",
    before=[
        "mana._parse_add_one_mana_of_any_color_trigger",
        "mana._parse_add_mana_in_any_combination_trigger",
    ],
)
def _parse_mana_adding_trigger(text: str) -> AbilityEffect | None:
    """CR 605.1b's triggered mana ability, resolving: the mana
    `parse_triggered_mana` reads off the effect text goes into the recipient's
    pool - "add an additional {G}" (Leyline of Abundance, Nirkana Revenant), "its
    controller adds an additional one mana of any color" (Fertile Ground),
    "one mana of the chosen color" (Utopia Sprawl), "one mana of any type that
    land produced" (Zendikar Resurgent).

    A text-template parser reached through `trigger_effect_for`'s fallback,
    not a per-card row. The recipient is `triggered_mana_recipient`'s: "its
    controller" is the controller of the permanent that was tapped (CR 303.4e
    lets it differ from the Aura's). The pool is `Game.mana_pool_receiving`'s,
    which is an open payment's own pool while one is being paid (CR 601.2g),
    so the mana pays that cost. Returns `None` for anything else.
    """
    shape = parse_triggered_mana(text)
    if shape is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        source = ability.source(game)
        recipient = triggered_mana_recipient(shape.recipient, ability.controller, ability.event)
        if recipient is None and source is not None and source.attached_to is not None:
            enchanted = game.find_by_id(source.attached_to)
            recipient = enchanted.controller if enchanted is not None else None
        if recipient is None:
            return
        # CR 608.2h: a "for each" count is taken now, as the mana is added.
        times = (
            triggered_mana_count(game, shape.count, ability.controller, source=source)
            if shape.count is not None
            else 1
        )
        if times <= 0:
            return
        colors = shape.colors
        if shape.snow_colors is not None and ability.event is not None:
            tapped = (
                game.find_by_id(ability.event.subject_id)
                if ability.event.subject_id is not None
                else None
            )
            if isinstance(tapped, CardState) and is_snow_source(tapped, game):
                colors = shape.snow_colors  # "If that Island is snow, ... instead"
        literal = list(colors) * times
        if shape.optional:
            # CR 608.2d: "may add" is the recipient's choice, asked in place -
            # unless a payment's own plan already named this mana, which is
            # the plan's answer (`Game.mana_hints_planned`).
            planned = game.take_mana_color_hints(literal)
            if not planned:
                if game.mana_hints_planned:
                    return
                if not game.may(
                    recipient,
                    f"add {''.join(f'{{{color.value}}}' for color in literal)}",
                    source=ability.source_name,
                    source_id=source_id_of(ability),
                ):
                    return
        else:
            game.take_mana_color_hints(literal)
        produced = literal
        if shape.chosen_color:
            choice = source.choice if source is not None else None
            if choice is None or choice.kind is not ChoiceKind.COLOR:
                return
            try:
                produced.extend([Color(choice.value)] * times)
            except ValueError:
                return
        five = tuple(Color(letter) for letter in _COLOR_LETTERS)
        for _ in range(shape.any_color * times):
            produced.append(
                _choose_mana_color(game, recipient, ability, five, "add one mana of any color")
            )
        if shape.produced_type:
            made = tuple(dict.fromkeys(ability.event.mana_added)) if ability.event else ()
            for _ in range(times if made else 0):
                produced.append(
                    _choose_mana_color(
                        game, recipient, ability, made, "add one mana of any type it produced"
                    )
                )
        restriction = (
            spend_restriction(shape.restriction, source) if shape.restriction is not None else None
        )
        pool = game.mana_pool_receiving(recipient)
        for color in produced:
            pool.add(color, restriction=restriction)

    return effect


#: "When this land enters, add one mana of any color." (Crumbling Vestige),
#: "When this Vehicle enters, add four mana of any one color." (Boommobile),
#: "At the beginning of your first main phase, add X mana of any one color,
#: where X is the number of Shrines you control." (Sanctum of Fruitful
#: Harvest). **Not** a mana ability - CR 605.1b requires a mana-producing
#: trigger to fire "from the activation or resolution of an activated mana
#: ability", and neither an enters-the-battlefield nor a beginning-of-phase
#: trigger fires from either, so CR 605.5's own catch-all ("abilities that
#: don't meet the criteria ... aren't mana abilities") applies: this is an
#: ordinary triggered ability, goes on the stack, and can be responded to,
#: unlike a permanent's own separate "{T}: Add ..." mana ability parsed off
#: its printed text by `machines/abilities.py` (which reads the identical "X
#: mana of any one color, where X is ..." shape for an *activated* ability -
#: Seance Board, Woodland Weavemaster - through its own `_read_mana_count`,
#: since a mana ability's own X has to be read off the board at the moment
#: *it* resolves, not here).
#:
#: "any one color" is one colour choice for the whole count; a count of one
#: makes that the same choice a bare "any color" (Crumbling Vestige, Lotus
#: Cobra) already is, which is why "one " is optional here rather than
#: required - every real printing above count one prints "any **one**
#: color", and none of these triggers prints "any color" (per-mana choice)
#: at a count above one, so a single colour chosen once and multiplied is
#: the right reading of every one of them.
#:
#: "add that much mana of any one color" (Photon, Mighty Marvel's combat
#: damage trigger) reads the trigger event's amount through the count channel
#: (`that_many`) - CR 120.3a's "that much" is the damage the event dealt.
_ADD_ONE_MANA_OF_ANY_COLOR_TRIGGER_RE = re.compile(
    rf"^add (?:(?P<that_much>that much)|{count_pattern('count', x=True)}) "
    rf"mana of any (?:one )?color{where_x_pattern()}\.?$",
    re.IGNORECASE,
)

#: "Until end of turn, you don't lose this mana as steps and phases end." -
#: a replacement of CR 500.5's mana emptying, modelled the same general way
#: firebending's "until end of combat" twin is (`_FIREBENDING_ADD_MANA_RE`,
#: `ManaRetentionScope`/`ManaPool.retained` in `models/mana.py`): any
#: sentence here that matches this regex tags the mana it follows with
#: `ManaRetentionScope.END_OF_TURN`, whether or not the trigger's count is
#: Photon's own "that much".
_KEEP_MANA_UNTIL_END_OF_TURN_RE = re.compile(
    r"^until end of turn, you don'?t lose this mana as steps and phases end\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s22")
def _parse_add_one_mana_of_any_color_trigger(text: str) -> AbilityEffect | None:
    """`_ADD_ONE_MANA_OF_ANY_COLOR_TRIGGER_RE`'s shape - Crumbling Vestige's
    "one", Boommobile's printed "four", and Sanctum of Fruitful Harvest's
    CR 107.3 X, defined by a `count_expression` shape ("the number of
    Shrines you control"). An X this parser cannot read - no "where X is ..."
    at all, or one naming something `count_expression` does not - fails the
    whole trigger closed rather than adding a guessed amount.

    CR 105.1/105.4: "any color" is one of the five colors - "if a player is
    asked to choose a color, they must choose one of the five colors ...
    [n]either is 'colorless'" - distinct from CR 106.1b's six *types* of mana
    (the five colors plus colorless), which is why this is never read as a
    sixth option. The choice is CR 608.2d's own, made once as the ability
    resolves, through the same `_choose_a_color`/`DecisionKind.CHOOSE_A_
    QUALITY` helper Wild Mongrel's and Culling Ritual's colour choices
    already use - "any **one** color" is a single choice for every mana
    added, not one choice per mana.
    """
    # CR 106.6's "Spend this mana only ..." sentence (Boommobile's own) is a
    # second sentence trailing the "add ..." one this regex reads - split it
    # off first, the same way `abilities._parse_mana_rider` and
    # `parse_triggered_mana`'s own `_TRIGGERED_MANA_SPEND_ONLY_RE` do for the
    # identical templating on an activated or a CR 605.1b triggered mana
    # ability, so it is never mistaken for part of the count/colour clause.
    sentences = [part for part in re.split(r"(?<=\.)\s+", text.strip()) if part]
    if not sentences:
        return None
    match = _ADD_ONE_MANA_OF_ANY_COLOR_TRIGGER_RE.fullmatch(sentences[0])
    if match is None:
        return None
    if len(sentences) > 1 and any(
        sentence.lower().startswith("spend this mana only") for sentence in sentences[1:]
    ):
        restriction_text: str | None = text
    else:
        restriction_text = None
    word = match.group("count")
    adds_that_much = match.group("that_much") is not None
    if adds_that_much and any(
        _KEEP_MANA_UNTIL_END_OF_TURN_RE.fullmatch(sentence) is None for sentence in sentences[1:]
    ):
        return None
    # CR 500.5b: whichever sentence carries the "you don't lose this mana as
    # steps and phases end" clause tags every unit of mana this trigger adds
    # with `ManaRetentionScope.END_OF_TURN` - Photon's own shape (checked
    # above: "that much" requires it), and, generally, any future non-"that
    # much" printing of the identical sentence.
    retain_until = (
        ManaRetentionScope.END_OF_TURN
        if any(
            _KEEP_MANA_UNTIL_END_OF_TURN_RE.fullmatch(sentence) is not None
            for sentence in sentences[1:]
        )
        else None
    )
    fixed_count: int | None = None
    count_reader: Callable[[Game, str], int] | None = None
    if adds_that_much:
        pass
    elif word.lower() == "x":
        where_x = match.group("where_x")
        if where_x is None:
            return None
        count_reader = count_expression(where_x.strip())
        if count_reader is None:
            return None
    else:
        fixed_count = parse_count(word)
        if fixed_count is None:
            return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        controller = ability.controller
        player = game.player(controller)
        # CR 608.2h: an X this trigger's own text defines is read now, as the
        # ability resolves - a board pumped while it waited on the stack adds
        # more mana. CR 107.1b: a result below 0 is 0 instead.
        if adds_that_much:
            counted = _that_many_or_notice(
                game,
                sentences[0],
                source_id=ability.source_id,
                source_name=ability.source_name,
                stack_object=ability,
            )
            if counted is None:
                return
            count = counted
        elif fixed_count is not None:
            count = fixed_count
        else:
            assert count_reader is not None
            count = max(count_reader(game, controller), 0)
        if count <= 0:
            return
        color = _choose_a_color(
            game,
            player,
            ability.source_name,
            "add mana of any color",
            source_id=source_id_of(ability),
        )
        restriction = (
            spend_restriction(restriction_text, ability.source(game))
            if restriction_text is not None
            else None
        )
        for _ in range(count):
            player.mana_pool.add(color, restriction=restriction, retain_until=retain_until)

    return effect


#: Enrage (CR 207.2c ability word): "Whenever `<this>` is dealt damage, add
#: that much `<mana>`. Until end of turn, you don't lose this mana as steps
#: and phases end." (Raphael, Ninja Destroyer's own "add that much {R}";
#: Sakiko, Mother of Summer's differently-triggered "add that much {G}") - the
#: fixed-colour twin of `_ADD_ONE_MANA_OF_ANY_COLOR_TRIGGER_RE`'s "add that
#: much mana of any one color" (Photon, Mighty Marvel): "that much" is CR
#: 607.1's anaphora onto the very event that triggered this ability (the
#: damage just dealt, `that_many`), and the second sentence tags every unit
#: added with `ManaRetentionScope.END_OF_TURN` the identical general way
#: (`models/mana.ManaPool.retained`) firebending's own "until end of combat"
#: twin already does. One or more literal mana symbols, the same "{R}{R}"
#: multi-symbol shape `_FIREBENDING_ADD_MANA_RE` already reads, though every
#: printing in the pool prints exactly one.
_ADD_THAT_MUCH_COLORED_MANA_RE = re.compile(
    r"^add that much (?P<mana>(?:\{[wubrgc]\}\s*)+)\.\s*"
    r"until end of turn, you don'?t lose this mana as steps and phases end\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s22")
def _parse_add_that_much_colored_mana_trigger(text: str) -> AbilityEffect | None:
    """`_ADD_THAT_MUCH_COLORED_MANA_RE`'s shape."""
    match = _ADD_THAT_MUCH_COLORED_MANA_RE.fullmatch(text.strip())
    if match is None:
        return None
    symbols = _MANA_SYMBOL_RE.findall(match.group("mana"))
    if not symbols:
        return None
    colors = [Color(symbol.upper()) for symbol in symbols]

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        count = _that_many_or_notice(
            game,
            text,
            source_id=ability.source_id,
            source_name=ability.source_name,
            stack_object=ability,
        )
        if count is None or count <= 0:
            return
        pool = game.player(ability.controller).mana_pool
        for _ in range(count):
            for color in colors:
                pool.add(color, retain_until=ManaRetentionScope.END_OF_TURN)

    return effect


def colored_mana_symbols(state: CardState) -> int:
    """How many colored mana symbols `state`'s mana cost has (CR 107.4)."""
    return sum(
        1
        for symbol in re.findall(r"\{([^}]+)\}", state.mana_cost or "")
        if set(symbol.upper()) & set(_COLOR_LETTERS)
    )


#: "add {R} or {G}" - one mana of one of the listed types, the player's choice
#: as the ability resolves (CR 608.2d). A non-mana triggered ability's own
#: mana instruction (Klothys's land branch); `_parse_mana_adding_trigger`
#: reads only a fixed list of symbols.
_ADD_ONE_OF_LISTED_MANA_RE = re.compile(
    r"^add (?P<first>\{[WUBRGC]\})(?P<middle>(?:, \{[WUBRGC]\})*),? or (?P<last>\{[WUBRGC]\})\.?$",
    re.IGNORECASE,
)


def _parse_add_one_of_listed_mana_clause(text: str) -> TargetedClause | None:
    """`_ADD_ONE_OF_LISTED_MANA_RE`'s shape, on an ability only: the mana goes
    into the resolving ability's controller's pool, one of the listed types,
    chosen as it resolves (`_choose_mana_color`)."""
    match = _ADD_ONE_OF_LISTED_MANA_RE.fullmatch(text.strip())
    if match is None:
        return None
    symbols = f"{match.group('first')}{match.group('middle')}{match.group('last')}"
    options = tuple(
        dict.fromkeys(Color(letter.upper()) for letter in _MANA_SYMBOL_RE.findall(symbols))
    )

    def effect(game: "Game", stack_object: "StackObject") -> None:
        assert isinstance(stack_object, AbilityOnStack)
        player = stack_object.controller
        color = _choose_mana_color(
            game,
            player,
            stack_object,
            options,
            "add " + " or ".join(f"{{{option.value}}}" for option in options),
        )
        game.mana_pool_receiving(player).add(color)

    return effect


#: "you may pay `<N>`. If you do, `<consequence>`." - Proft, Consulting
#: Detective's own "Whenever you scry or surveil, you may pay {2}. If you do,
#: put a +1/+1 counter on Proft and draw a card." - the ordinary-mana twin of
#: `_MAY_PAY_ENERGY_IF_YOU_DO_RE`'s energy symbols. CR 118.12, not CR 603.12
#: (see that regex's own docstring for why "if you do" and "when you do" are
#: never folded into one pattern): the consequence runs right here, on the
#: same `AbilityOnStack`, with no new triggered ability and nothing that
#: needs a target announced later.
_MAY_PAY_MANA_IF_YOU_DO_RE = re.compile(
    r"^you may pay (?P<mana>(?:\{[^}]+\})+)\.\s*if you do,\s*(?P<consequence>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)


@ABILITY_TEXT.rung("s20")
def _parse_may_pay_mana_if_you_do_clause(text: str) -> AbilityEffect | None:
    """`_MAY_PAY_MANA_IF_YOU_DO_RE`'s shape - see its own docstring for why
    this is CR 118.12, not CR 603.12. The symbol run is mana only
    (`ManaCost.try_parse`), and the consequence is `pay_consequence_effect`'s,
    shared with the energy twin."""
    match = _MAY_PAY_MANA_IF_YOU_DO_RE.fullmatch(_strip_non_effect_preamble(text).strip())
    if match is None:
        return None
    cost = ManaCost.try_parse(match.group("mana"))
    if cost is None:
        return None
    consequence = pay_consequence_effect(match.group("consequence").strip())
    if consequence is None:
        return None

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        player = game.controller_of(ability)
        _source_id, source_name = _permanent_id_and_name(ability, for_spell=False)
        paid = game.may_pay_mana_cost(
            player, cost, source=source_name, source_id=source_id_of(ability)
        )
        if not paid:
            return
        consequence(game, ability)

    return effect


#: "Add <mana>." as a *resolving* effect rather than a mana ability's fast
#: path - Ugin, Eye of the Storms' "0: Add {C}{C}{C}." CR 605.1a's third
#: criterion is "it's not a loyalty ability", and CR 606.2 makes any ability
#: with a loyalty symbol in its cost one, so this ability is not a mana ability
#: at all: CR 605.3b's "doesn't go on the stack" is false of it, it goes on the
#: stack like any other activated ability (CR 602.2, CR 113.3b), and the mana
#: arrives when it resolves. `machines/abilities.py` still parses the `Add`
#: into a `ManaAbility`, and `Game.activate_ability` already refuses it the
#: fast path; this is the resolution half, which had nothing written for it and
#: so silently added no mana at all.
#:
#: A literal run of mana symbols only - a choice of colors, or an amount that
#: depends on the board, is not read here and falls through to no effect rather
#: than to a guess.
_ADD_MANA_RE = re.compile(r"^add (?P<mana>(?:\{[wubrgc]\}\s*)+)$", re.IGNORECASE)


@MIXED_CLAUSE.rung("s31", for_spell=FORWARD)
def _parse_add_mana_clause(clause: str, *, for_spell: bool) -> TargetedClause | None:
    """ "Add {C}{C}{C}" on a resolving ability or spell (CR 106.4).

    Opened to spells (Pyretic Ritual, Desperate Ritual): CR 605.5 says "spells
    aren't mana abilities" - true, and irrelevant here, since this is the
    resolution-time reading of a plain "Add ..." sentence, not a fast-path mana
    ability (CR 605.1a already keeps a *spell* from ever qualifying as one,
    the same way it keeps Ugin, Eye of the Storms' loyalty ability from
    qualifying). CR 106.4's "when an effect instructs a player to add mana"
    does not care whether the instructing object was a spell or an ability,
    and `game.controller_of(stack_object)` already reads either kind
    (`StackObject` covers both `CardState` and `AbilityOnStack`), so nothing
    about the effect itself needed to change - only the early refusal that
    was guarding against a shape the pool had no evidence for yet.
    """
    match = _ADD_MANA_RE.fullmatch(clause.strip().rstrip("."))
    if match is None:
        return None
    symbols = _MANA_SYMBOL_RE.findall(match.group("mana"))
    colors = [Color(symbol.upper()) for symbol in symbols]

    def effect(game: "Game", stack_object: "StackObject") -> None:
        # CR 106.4: "When an effect instructs a player to add mana, that mana
        # goes into a player's mana pool."
        pool = game.controller_of(stack_object).mana_pool
        for color in colors:
            pool.add(color)

    return effect


#: "If five or more mana was spent to cast that spell, add an amount of {R}
#: equal to this creature's power." - Molten-Core Maestro's own Opus rider
#: (CR 601.2h's mana-spent condition, already read generically through
#: `Game.condition_holds`/`machines/conditions/cast_record._at_least_mana_
#: spent` - no new condition reader, only a new consequence). CR 106.3: the
#: mana enters the pool as this ability resolves, its amount computed then
#: (CR 608.2h), off the object the expression names - `amount_expression`
#: already reads "this creature's power"/"its power" generically
#: (`_OBJECT_CHARACTERISTIC_RE`), so a future card naming a different count
#: in this same position ("equal to the number of ... you control") reads
#: for free.
_IF_CONDITION_ADD_MANA_EQUAL_TO_RE = re.compile(
    r"^if (?P<condition>[^,]+), add an amount of \{(?P<symbol>[wubrgc])\} equal to "
    r"(?P<expr>.+?)\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s31", for_spell=FORWARD)
def _parse_if_condition_add_mana_equal_to_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_IF_CONDITION_ADD_MANA_EQUAL_TO_RE`'s shape - see the banner above.
    An unreadable condition fails closed with a `ConditionalClauseNotice`,
    the same treatment every other printed "if" here gets."""
    match = _IF_CONDITION_ADD_MANA_EQUAL_TO_RE.fullmatch(clause.strip())
    if match is None:
        return None
    condition_text = match.group("condition").strip()
    if not _effect_condition_is_readable(condition_text):
        return None
    reader = amount_expression(match.group("expr"))
    if reader is None:
        return None
    color = Color(match.group("symbol").upper())

    def effect(game: "Game", stack_object: "StackObject") -> None:
        source = (
            stack_object if isinstance(stack_object, CardState) else stack_object.source(game)  # type: ignore[union-attr]
        )
        held = _condition_holds_for_stack_object(game, stack_object, condition_text, source)
        if held is None:
            notice = ConditionalClauseNotice(
                source_id=source_id_of(stack_object),
                source_name=(
                    stack_object.name
                    if isinstance(stack_object, CardState)
                    else stack_object.source_name  # type: ignore[union-attr]
                ),
                text=clause,
            )
            if notice not in game.conditional_clause_notices:
                game.conditional_clause_notices.append(notice)
            return
        if not held:
            return
        controller = game.controller_of(stack_object)
        amount = reader(game, controller.username, source, 0)
        pool = controller.mana_pool
        for _ in range(max(amount, 0)):
            pool.add(color)

    return effect


#: How many mana an any-combination instruction adds, read as it resolves:
#: `None` when there is nothing to read (a "that much" with no event count,
#: which has already filed its own notice).
_AnyCombinationCount = Callable[["Game", "StackObject"], int | None]


def _read_any_combination_mana(
    match: "re.Match[str]", text: str
) -> tuple[tuple[Color, ...], _AnyCombinationCount] | None:
    """`_ADD_ANY_COMBINATION_MANA_RE`'s palette and count reader, or `None`
    when the count cannot be read at all (an unknown word, an X with no
    readable definition) - the instruction then fails closed whole."""
    palette_text = match.group("palette")
    palette = (
        tuple(Color(letter) for letter in _COLOR_LETTERS)
        if palette_text.lower() == "colors"
        else tuple(Color(symbol.upper()) for symbol in _MANA_SYMBOL_RE.findall(palette_text))
    )
    if match.group("that_much") is not None:

        def that_much(game: "Game", stack_object: "StackObject") -> int | None:
            if not isinstance(stack_object, AbilityOnStack):
                return None
            return _that_many_or_notice(
                game,
                text,
                source_id=stack_object.source_id,
                source_name=stack_object.source_name,
                stack_object=stack_object,
            )

        return palette, that_much
    word = match.group("n")
    if word.lower() == "x":
        where_x = match.group("where_x")
        if where_x is None:
            return None
        reader = count_expression(where_x.strip())
        if reader is None:
            return None

        def counted(game: "Game", stack_object: "StackObject") -> int | None:
            return max(reader(game, game.controller_of(stack_object).username), 0)

        return palette, counted
    if match.group("where_x") is not None:
        return None
    fixed = parse_count(word)
    if fixed is None or fixed <= 0:
        return None
    return palette, lambda _game, _stack_object: fixed


def _choose_mana_unit_color(
    game: "Game", stack_object: "StackObject", palette: Sequence[Color]
) -> Color:
    """One unit's colour among `palette`, the controller's choice as the
    instruction resolves (CR 608.2d); a palette of one is no choice at all."""
    if len(palette) == 1:
        return palette[0]
    source = stack_object.name if isinstance(stack_object, CardState) else stack_object.source_name
    return _choose_a_color(
        game,
        game.controller_of(stack_object),
        source,
        "choose a color for mana",
        source_id=source_id_of(stack_object),
        colors=None if len(palette) == len(_COLOR_LETTERS) else palette,
    )


def _add_mana_in_any_combination(
    game: "Game",
    stack_object: "StackObject",
    count: int,
    palette: Sequence[Color],
    *,
    restriction: "ManaRestriction | None" = None,
    retain_until: "ManaRetentionScope | None" = None,
) -> None:
    """Add `count` mana to the controller's pool, each unit's colour chosen
    on its own among `palette` (CR 106.1a, CR 608.2d)."""
    pool = game.controller_of(stack_object).mana_pool
    for _ in range(max(count, 0)):
        color = _choose_mana_unit_color(game, stack_object, palette)
        pool.add(color, restriction=restriction, retain_until=retain_until)


@MIXED_CLAUSE.rung("s31", for_spell=FORWARD)
def _parse_add_any_combination_mana_clause(
    clause: str, *, for_spell: bool
) -> TargetedClause | None:
    """`_ADD_ANY_COMBINATION_MANA_RE`'s shape, or `None` if this is not it."""
    match = _ADD_ANY_COMBINATION_MANA_RE.fullmatch(clause.strip())
    if match is None:
        return None
    read = _read_any_combination_mana(match, clause)
    if read is None:
        return None
    palette, count_of = read

    def effect(game: "Game", stack_object: "StackObject") -> None:
        count = count_of(game, stack_object)
        if count:
            _add_mana_in_any_combination(game, stack_object, count, palette)

    return effect


#: "`<add any combination>`. Until end of turn, you don't lose this mana as
#: steps and phases end." / "... Spend this mana only to `<restriction>`." -
#: the instruction with its own trailing sentences, read whole: CR 500.5b's
#: retention (`_KEEP_MANA_UNTIL_END_OF_TURN_RE`, Grand Warlord Radha) and
#: CR 106.6's restriction tag every unit it adds.
@ABILITY_TEXT.rung("s22")
def _parse_add_mana_in_any_combination_trigger(text: str) -> AbilityEffect | None:
    """`_ADD_ANY_COMBINATION_MANA_RE` plus its trailing sentences, as one
    triggered ability's whole effect - see the banner above."""
    sentences = [part for part in re.split(r"(?<=\.)\s+", text.strip()) if part]
    if not sentences:
        return None
    match = _ADD_ANY_COMBINATION_MANA_RE.fullmatch(sentences[0])
    if match is None:
        return None
    read = _read_any_combination_mana(match, sentences[0])
    if read is None:
        return None
    palette, count_of = read
    retain_until: ManaRetentionScope | None = None
    restriction_text: str | None = None
    for sentence in sentences[1:]:
        if _KEEP_MANA_UNTIL_END_OF_TURN_RE.fullmatch(sentence):
            retain_until = ManaRetentionScope.END_OF_TURN
            continue
        restriction = spend_restriction(sentence)
        if restriction is None or not restriction.understood:
            return None
        restriction_text = sentence

    def effect(game: "Game", ability: AbilityOnStack) -> None:
        count = count_of(game, ability)
        if not count:
            return
        restriction = (
            spend_restriction(restriction_text, ability.source(game))
            if restriction_text is not None
            else None
        )
        _add_mana_in_any_combination(
            game, ability, count, palette, restriction=restriction, retain_until=retain_until
        )

    return effect


#: "add `<n>` mana of any [one] color" - CR 105.1's five colours, one choice
#: for the whole count (CR 608.2d): Ancient Ziggurat's own "one mana of any
#: color" wording, read as a resolving instruction rather than a `{T}` mana
#: ability. A count with no fixed number is not read here.
_ADD_FIXED_MANA_OF_ANY_COLOR_RE = re.compile(
    rf"^add {count_pattern('n')} mana of any (?:one )?colou?r\.?$", re.IGNORECASE
)

#: What one "Add ..." instruction does as it resolves, given the CR 106.6
#: restriction (or `None`) every unit it adds is tagged with.
ManaAdder = Callable[["Game", "StackObject", "ManaRestriction | None"], None]


def _add_one_chosen_color(
    game: "Game",
    stack_object: "StackObject",
    count: int,
    palette: Sequence[Color],
    restriction: "ManaRestriction | None",
) -> None:
    """`count` mana of one colour chosen once among `palette` (CR 608.2d:
    "any **one** color" is a single choice for every unit) -
    `_add_mana_in_any_combination` asks once per unit instead."""
    if count <= 0:
        return
    color = _choose_mana_unit_color(game, stack_object, palette)
    pool = game.controller_of(stack_object).mana_pool
    for _ in range(count):
        pool.add(color, restriction=restriction)


def read_add_mana_instruction(clause: str) -> ManaAdder | None:
    """One CR 106.4 "Add ..." instruction, read as it resolves on any spell or
    ability, or `None` when it is not one of these shapes:

    - a literal run of symbols - "Add {U}." / "Add {C}{C}." (`_ADD_MANA_RE`);
    - one of a printed list - "Add {U}, {R}, or {W}." / "Add {U} or {R}."
      (`_ADD_ONE_OF_LISTED_MANA_RE`), the colour chosen as it resolves
      (CR 608.2d);
    - "Add `<n>` mana of any [one] color." - one CR 105.1 colour, chosen once;
    - "Add `<n>` mana in any combination of `<palette>`."
      (`_ADD_ANY_COMBINATION_MANA_RE`), one choice per unit.

    The adder tags every unit with the restriction it is handed, so a CR 106.6
    sentence printed after the instruction (`spend_restriction`) rides on all
    of it.
    """
    text = clause.strip()
    literal = _ADD_MANA_RE.fullmatch(text.rstrip("."))
    if literal is not None:
        colors = [
            Color(symbol.upper()) for symbol in _MANA_SYMBOL_RE.findall(literal.group("mana"))
        ]

        def add_literal(
            game: "Game", stack_object: "StackObject", restriction: "ManaRestriction | None"
        ) -> None:
            pool = game.controller_of(stack_object).mana_pool
            for color in colors:
                pool.add(color, restriction=restriction)

        return add_literal
    listed = _ADD_ONE_OF_LISTED_MANA_RE.fullmatch(text)
    if listed is not None:
        symbols = f"{listed.group('first')}{listed.group('middle')}{listed.group('last')}"
        options = tuple(
            dict.fromkeys(Color(letter.upper()) for letter in _MANA_SYMBOL_RE.findall(symbols))
        )

        def add_listed(
            game: "Game", stack_object: "StackObject", restriction: "ManaRestriction | None"
        ) -> None:
            _add_one_chosen_color(game, stack_object, 1, options, restriction)

        return add_listed
    any_color = _ADD_FIXED_MANA_OF_ANY_COLOR_RE.fullmatch(text)
    if any_color is not None:
        count = parse_count(any_color.group("n"))
        if count is None or count <= 0:
            return None
        five = tuple(Color(letter) for letter in _COLOR_LETTERS)

        def add_any_color(
            game: "Game", stack_object: "StackObject", restriction: "ManaRestriction | None"
        ) -> None:
            _add_one_chosen_color(game, stack_object, count, five, restriction)

        return add_any_color
    combination = _ADD_ANY_COMBINATION_MANA_RE.fullmatch(text)
    if combination is not None:
        read = _read_any_combination_mana(combination, clause)
        if read is None:
            return None
        palette, count_of = read

        def add_combination(
            game: "Game", stack_object: "StackObject", restriction: "ManaRestriction | None"
        ) -> None:
            count = count_of(game, stack_object)
            if count:
                _add_mana_in_any_combination(
                    game, stack_object, count, palette, restriction=restriction
                )

        return add_combination
    return None


from ._common import (  # noqa: E402
    _ADD_ANY_COMBINATION_MANA_RE,
    _COLOR_LETTERS,
    _MANA_SYMBOL_RE,
    ConditionalClauseNotice,
    _effect_condition_is_readable,
    _permanent_id_and_name,
    pay_consequence_effect,
)
from .amounts import _that_many_or_notice, amount_expression, count_expression  # noqa: E402
from .continuous import _cast_trigger_record  # noqa: E402
from .dispatch import _parse_mixed_clause  # noqa: E402
from .modal import (  # noqa: E402
    _choose_a_color,
    _choose_mana_color,
    _condition_holds_for_stack_object,
)
from .text import _strip_non_effect_preamble  # noqa: E402
