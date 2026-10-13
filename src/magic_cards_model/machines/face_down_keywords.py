"""Alternative-cast, face-down and zone keywords this engine builds as one
family: embalm and eternalize (CR 702.128a, CR 702.129a), cloak (CR 701.58a),
disguise's self-reducing cost (CR 702.168d), the plot grant (CR 702.170f) and
mutate (CR 702.140, rule 730).

Every function here reads the keyword or keyword action off its own rule
text and the printed line's shape - never a card name.
"""

from __future__ import annotations

import re
from functools import cache
from typing import TYPE_CHECKING, Any

from ..models.card import Card, Color
from ..models.card_state import CardState, FaceDownCharacteristics
from ..models.mana import ManaCost
from ..models.zone import Zone
from .abilities import keyword_abilities

if TYPE_CHECKING:
    from ..models.game import Game
    from .abilities import KeywordAbility
    from .keywords import KeywordActivation

# --------------------------------------------------------------------------
# Embalm (CR 702.128a) and eternalize (CR 702.129a)
# --------------------------------------------------------------------------

#: CR 702.128a / CR 702.129a, per keyword: the rule's own rule number and the
#: copy exception it states ("except it's white ..." / "except it's black,
#: it's 4/4 ...").
TOKEN_COPY_KEYWORDS: dict[str, tuple[str, Color, tuple[int, int] | None]] = {
    "embalm": ("CR 702.128a", Color.WHITE, None),
    "eternalize": ("CR 702.129a", Color.BLACK, (4, 4)),
}


def token_copy_keyword_abilities(card: Card) -> list[KeywordAbility]:
    """Every embalm or eternalize ability printed on `card`, in printed order."""

    return [
        ability
        for ability in keyword_abilities(card)
        if ability.canonical.lower() in TOKEN_COPY_KEYWORDS and ability.cost
    ]


def token_copy_keyword_effect_text(keyword: str) -> str:
    """The rule's own effect sentence for `keyword` (CR 702.128a / 702.129a)."""
    _rule, color, pt = TOKEN_COPY_KEYWORDS[keyword.lower()]
    colour = "white" if color is Color.WHITE else "black"
    size = f", it's {pt[0]}/{pt[1]}" if pt else ""
    return (
        f"Create a token that's a copy of this card, except it's {colour}{size}, it has no "
        f"mana cost, and it's a Zombie in addition to its other types."
    )


def token_copy_keyword_activation(
    game: Any, card: CardState, player: str, index: int = 0
) -> KeywordActivation:
    """Build the activation of `card`'s embalm/eternalize ability number
    `index`: "[Cost], Exile this card from your graveyard: Create a token
    that's a copy of this card, except ... Activate only as a sorcery."
    (CR 702.128a, CR 702.129a). The exile is part of the cost, so the card
    has already left the graveyard when the ability resolves."""
    from .cost import ComponentKind, total_cost_for_phrase
    from .keywords import KeywordActivation, _synthetic_ability, statically_priced

    abilities = token_copy_keyword_abilities(card.card)
    if index < 0 or index >= len(abilities):
        raise ValueError(f"{card.name} has no embalm or eternalize ability number {index}")
    ability = abilities[index]
    rule = TOKEN_COPY_KEYWORDS[ability.canonical.lower()][0]
    cost_text = f"{ability.cost}, Exile this card from your graveyard"
    cost = total_cost_for_phrase(cost_text, player)
    if cost is None:
        raise ValueError(
            f"{card.name}'s {ability.canonical} cost {ability.cost!r} could not be read, "
            f"so it cannot be paid ({rule})"
        )
    for component in cost.components:
        if component.kind is ComponentKind.EXILE and not component.cards:
            component.cards = [card]  # "Exile this card": the cost names itself.
    return statically_priced(
        KeywordActivation(
            card=card,
            player=player,
            keyword=ability.canonical,
            rule=rule,
            zone=Zone.GRAVEYARD,
            cost=cost.assign_payer(player),
            sorcery_only=True,
            ability=_synthetic_ability(
                ability,
                cost_text=cost_text,
                effect=token_copy_keyword_effect_text(ability.canonical),
            ),
            game=game,
        )
    )


def token_copy_keyword_effect(activation: KeywordActivation) -> list[CardState]:
    """CR 702.128a / CR 702.129a's effect: one token copy of the exiled card
    (CR 707.2's copiable values), white (or black and 4/4), with no mana
    cost, and a Zombie in addition to its other types (CR 707.9b)."""
    from ..models.token import token_copy_of

    game = activation.game
    if game is None:
        return []
    _rule, color, pt = TOKEN_COPY_KEYWORDS[activation.keyword.lower()]
    return list(
        token_copy_of(
            game,
            activation.card,
            activation.player,
            colors=(color,),
            power=pt[0] if pt else None,
            toughness=pt[1] if pt else None,
            added_creature_type="Zombie",
            no_mana_cost=True,
        )
    )


# --------------------------------------------------------------------------
# Cloak (CR 701.58)
# --------------------------------------------------------------------------

#: CR 701.58a: "a 2/2 face-down creature card with ward {2}, no name, no
#: subtypes, and no mana cost" - disguise's own set (CR 702.168b).
CLOAK_RULE = "CR 701.58a"


def cloak(game: Game, controller: str, card_state: CardState) -> CardState:
    """CR 701.58a: turn `card_state` face down as a 2/2 with ward {2} and put
    it onto the battlefield under `controller`'s control.

    The permanent is stamped `manifested`: CR 701.58b's turn-up procedure
    (show it is a creature card, pay its mana cost) is word for word CR
    701.40b's, which `machines/keywords.why_cannot_turn_up_manifested` and
    `manifest_turn_up_cost` already implement off that flag, and CR
    701.58c-d's morph/disguise alternative is CR 701.40c-d's identical
    choice. Its ward is the face-down characteristics' own text."""
    card_state.turn_face_down(
        FaceDownCharacteristics(keywords=("Ward",), oracle_text="Ward {2}", rule=CLOAK_RULE)
    )
    card_state.manifested = True
    return game.put_onto_battlefield(card_state, controller)


#: "cloak the top card of your library", "cloak the top card of that player's
#: library", "cloak the top two cards of your library", "cloak a card from
#: your hand".
_CLOAK_RE = re.compile(
    r"^cloak (?:the top (?P<n>card|two cards|three cards|\d+ cards) of "
    r"(?P<whose>your|that player's|target player's|each opponent's) library"
    r"|(?P<hand>a card from your hand))$",
    re.IGNORECASE,
)


@cache
def read_cloak_clause(clause: str) -> tuple[int, str] | None:
    """`(count, whose)` for a cloak clause - `whose` is "your", "that
    player's", "target player's", "each opponent's" or "hand" - or None."""
    match = _CLOAK_RE.fullmatch(clause.strip().rstrip(".").strip())
    if match is None:
        return None
    if match["hand"]:
        return 1, "hand"
    words = {"card": 1, "two cards": 2, "three cards": 3}
    raw = match["n"].lower()
    count = words.get(raw) or int(raw.split()[0])
    return count, match["whose"].lower()


def cloak_from_library(game: Game, controller: str, library_owner: str, count: int) -> int:
    """CR 701.58e: cloak the top `count` cards of `library_owner`'s library
    one at a time, under `controller`'s control. Returns how many were cloaked."""
    owner = game.player(library_owner)
    done = 0
    for _ in range(count):
        if not owner.library:
            break
        top = owner.library[0]
        owner.zones[Zone.LIBRARY].remove(top)
        cloak(game, controller, top)
        done += 1
    return done


# --------------------------------------------------------------------------
# Disguise's self-reducing turn-up cost (CR 702.168d, CR 601.2f)
# --------------------------------------------------------------------------

#: "This cost is reduced by {1} for each instant and sorcery card in your
#: graveyard." - a disguise (or morph) line's own trailing sentence.
_FACE_UP_COST_REDUCTION_RE = re.compile(
    r"^this cost is reduced by \{(?P<amount>\d+)\} for each (?P<quality>.+?) cards? in "
    r"your graveyard\.?$",
    re.IGNORECASE,
)


@cache
def read_face_up_cost_reduction(sentence: str) -> tuple[int, str] | None:
    """`(amount, quality)` for a trailing "This cost is reduced by {N} for
    each <quality> card in your graveyard." sentence, or None when the
    quality is not one the engine's card-quality matcher reads."""
    from .effects import _card_description_is_readable

    match = _FACE_UP_COST_REDUCTION_RE.fullmatch(sentence.strip())
    if match is None:
        return None
    quality = re.sub(r"\s+and(?:/or)?\s+", " or ", match["quality"].strip())
    if not _card_description_is_readable(quality):
        return None
    return int(match["amount"]), quality


def split_face_up_cost_reduction(text: str) -> tuple[str, str] | None:
    """`(keyword line, reduction sentence)` when `text` is "Disguise {cost}.
    This cost is reduced by ..." - or None."""
    head, sep, tail = text.partition(". ")
    if not sep or read_face_up_cost_reduction(tail) is None:
        return None
    return head, tail


def face_up_cost_reduction(game: Game, permanent: CardState, player: str) -> ManaCost:
    """The generic mana a face-down permanent's own printed "This cost is
    reduced by {N} for each ..." sentence takes off its disguise/morph cost
    right now (CR 601.2f via CR 702.168d's "pay that cost"). Empty when the
    card prints none."""
    from .abilities import keyword_abilities
    from .effects import _quality_matcher

    for ability in keyword_abilities(permanent.card):
        if ability.canonical.lower() not in ("disguise", "morph", "megamorph"):
            continue
        reduction = ability.face_up_reduction
        if not reduction:
            continue
        read = read_face_up_cost_reduction(reduction)
        if read is None:
            continue
        amount, quality = read
        matches = _quality_matcher(quality)
        counted = sum(1 for card in game.player(player).graveyard if matches(card))
        return ManaCost.parse("{" + str(amount * counted) + "}") if counted else ManaCost()
    return ManaCost()


# --------------------------------------------------------------------------
# "Turn this creature face up. If you can't, exile it, then you may cast the
# exiled card without paying its mana cost." (CR 708.8, CR 701.58g, CR 608.2g)
# --------------------------------------------------------------------------

_TURN_UP_OR_EXILE_AND_CAST_RE = re.compile(
    r"^turn (?:this creature|this permanent|it) face up\. if you can't, exile it, then you may "
    r"cast the exiled card without paying its mana cost\.?$",
    re.IGNORECASE,
)

#: "Face-down creatures you control have "<ability>"." - the group a quoted
#: grant reaches by the CR 708.2 face-down status rather than a quality.
FACE_DOWN_GROUP_QUOTED_GRANT_RE = re.compile(
    r"^face-down creatures(?P<whose> you control| your opponents control)? have "
    r"\"(?P<ability>[^\"]+)\"\.?$",
    re.IGNORECASE,
)


def face_down_group_grant_targets(
    sentence: str, source: CardState, permanents: list[CardState]
) -> tuple[str, list[CardState]] | None:
    """`(granted text, the face-down creatures it reaches)` for a
    `FACE_DOWN_GROUP_QUOTED_GRANT_RE` sentence on `source`, or None."""
    match = FACE_DOWN_GROUP_QUOTED_GRANT_RE.fullmatch(sentence.strip())
    if match is None:
        return None
    whose = (match["whose"] or "").strip().lower()
    reached = [
        permanent
        for permanent in permanents
        if permanent.zone is Zone.BATTLEFIELD
        and permanent.face_down
        and (
            not whose
            or (whose == "you control" and permanent.controller == source.controller)
            or (whose == "your opponents control" and permanent.controller != source.controller)
        )
    ]
    return match["ability"].strip(), reached


def why_effect_cannot_turn_face_up(game: Game, permanent: CardState) -> str | None:
    """Why an effect cannot turn `permanent` face up right now (it is not a
    face-down permanent, a static forbids it, or CR 701.58g's instant or
    sorcery card that is revealed and left face down), or None."""
    from ..models.card import Type
    from .keywords import turn_face_up_ban

    if permanent.zone is not Zone.BATTLEFIELD or permanent.face_up:
        return f"{permanent.card.name} is not a face-down permanent"
    ban = turn_face_up_ban(game, permanent)
    if ban is not None:
        return ban
    types = set(permanent.card.types)
    if types & {Type.INSTANT, Type.SORCERY}:
        return (
            f"{permanent.card.name} is an instant or sorcery card, so it is revealed and left "
            f"face down (CR 701.58g)"
        )
    return None


def read_turn_up_or_exile_and_cast(text: str) -> Any:
    """The effect of "Turn this creature face up. If you can't, exile it,
    then you may cast the exiled card without paying its mana cost." - an
    ability of the face-down permanent itself (granted to it, Etrata, Deadly
    Fugitive) - or None.

    Turning up by an effect is not a special action, so no cost is paid and
    CR 708.8 applies (no enters abilities). When the permanent can't be
    turned up, it is exiled and its owner's controller may cast it during
    the resolution (CR 608.2g)."""
    if _TURN_UP_OR_EXILE_AND_CAST_RE.fullmatch(text.strip()) is None:
        return None

    def effect(game: Game, ability: Any) -> None:
        from .decisions import source_id_of

        permanent = ability.source(game)
        if not isinstance(permanent, CardState) or permanent.zone is not Zone.BATTLEFIELD:
            return
        controller = game.controller_of(ability).username
        if why_effect_cannot_turn_face_up(game, permanent) is None:
            game.turn_face_up(permanent, controller)
            return
        if permanent.face_up:
            return
        game.exile_permanent(permanent)
        if permanent.zone is not Zone.EXILE:
            return
        game.may_cast_during_resolution(
            permanent,
            controller,
            prompt=f"cast {permanent.name} without paying its mana cost",
            source=ability.source_name,
            source_id=source_id_of(ability),
            source_name=ability.source_name,
            rule="CR 608.2g",
        )

    return effect


# --------------------------------------------------------------------------
# Mutate (CR 702.140) and merged permanents (rule 730)
# --------------------------------------------------------------------------


def mutate_cast_zones(card: Card) -> frozenset[str]:
    """The zones `card` may be cast from for its mutate cost, understood.

    The hand from CR 702.140a's own alternative cost, plus every zone a
    printed "You may cast this card from your `<zone>` using its mutate
    ability." opens (CR 604.6, `permissions._printed_zone_permissions`) -
    read off the production cast options, not re-derived here."""
    from .casting.options import keyword_cast_options

    return frozenset(
        option.zone.value
        for option in keyword_cast_options(card)
        if option.keyword.lower() == "mutate" and option.understood
    )


#: The description every merged permanent's copy effect carries, so
#: `Game.merge` can replace it and CR 730.3's departure can end it.
MERGED_PERMANENT_EFFECT = "merged permanent (CR 730.2a)"


def merged_permanent_effect(game: Game, permanent: CardState, components: list[CardState]) -> Any:
    """CR 730.2a's copiable effect for a merged permanent, `components`
    topmost first.

    "A merged permanent has only the characteristics of its topmost
    component ... This is a copiable effect whose timestamp is the time the
    objects merged" - and CR 702.140e: "A mutated permanent has all
    abilities of each card and token that represents it. Its other
    characteristics are derived from the topmost card or token." So the
    topmost component's copiable values (CR 707.2) with every component's
    ability lines, topmost first, as one layer 1 copy effect built by the
    same builder every "becomes a copy" uses
    (`layers.parse._become_a_copy_builder`), fixed to this incarnation of
    the permanent (CR 400.7)."""
    from .layers.apply import copiable_characteristics
    from .layers.model import LayerContext, only_this_incarnation
    from .layers.parse import _become_a_copy_builder

    running = [
        effect
        for effect in game.continuous_effects.active(game)
        if effect.description != MERGED_PERMANENT_EFFECT or effect.source_id != permanent.id
    ]
    values = [
        copiable_characteristics(component, running if component is permanent else ())
        for component in components
    ]
    abilities: list[str] = []
    for value in values:
        abilities.extend(line for line in value.abilities if line not in abilities)
    merged = values[0].model_copy(update={"abilities": tuple(abilities)})
    built = _become_a_copy_builder(until_eot=False, copiable_values=merged)(
        permanent, game.continuous_effects.tick(), [permanent], LayerContext()
    )
    return [
        effect.model_copy(
            update={
                "description": MERGED_PERMANENT_EFFECT,
                "selector": only_this_incarnation(permanent, permanent.zone_change_stamp),
            }
        )
        for effect in built
    ]


def _mutate_target_is_legal(game: Game, spell: CardState, target: Any) -> bool:
    """CR 702.140a's target, rechecked as the spell begins resolving (CR
    702.140b): still on the battlefield as the same object, a creature, not a
    Human, with the same owner as the spell."""
    if not isinstance(target, CardState) or target.zone is not Zone.BATTLEFIELD:
        return False
    view = game.characteristics_of(target)
    if not view.is_creature or "Human" in view.subtypes:
        return False
    return target.owner == spell.owner


def resolve_mutating_spell(game: Game, spell: CardState) -> bool:
    """Resolve a mutating creature spell (CR 702.140b-d), or say it is not one.

    Returns True when the spell merged with its target and is done. Returns
    False for a spell not cast for its mutate cost, and for one whose target
    is illegal: CR 702.140b, "it ceases to be a mutating creature spell and
    continues resolving as a creature spell" - so the mutate target is
    dropped from it (no CR 608.2b fizzle) and the caller resolves it as the
    ordinary creature spell it now is.

    A legal target: CR 702.140c, the spell "merges with the target creature";
    "the spell's controller chooses whether the spell is put on top of the
    creature or on the bottom" (`DecisionKind.PUT_ON_TOP_OR_BOTTOM`, True for
    the top). `Game.mutate` merges and raises CR 702.140d's "whenever a
    creature mutates".
    """
    from .decisions import Decision, DecisionKind

    if (game.cast_record(spell).keyword or "").lower() != "mutate" or not spell.targets:
        return False
    slot = spell.targets[-1]
    target = game.legal_target(spell, slot)
    if not _mutate_target_is_legal(game, spell, target):
        spell.targets = spell.targets[:-1]
        return False
    assert isinstance(target, CardState)
    controller = spell.controller or game.controller_of(target).username
    on_top = game.ask(
        Decision(
            kind=DecisionKind.PUT_ON_TOP_OR_BOTTOM,
            player=controller,
            prompt=f"put {spell.name} on top of {target.name} (yes) or under it (no)",
            source=spell.name,
            source_id=str(spell.id),
        )
    )
    game.mutate(target, spell, on_top=bool(on_top))
    return True


# --------------------------------------------------------------------------
# Plot granted to the top card of the library (CR 702.170f)
# --------------------------------------------------------------------------

#: "The top card of your library has plot. The plot cost is equal to its mana
#: cost." - the keyword granted to whatever card is on top (CR 611.3d).
LIBRARY_TOP_HAS_PLOT_RE = re.compile(
    r"^the top card of your library has plot\. the plot cost is equal to its mana cost\.?$",
    re.IGNORECASE,
)

#: "You may plot `<quality>` cards from the top of your library." - CR
#: 702.170f's "an effect may allow the plot ability of a card to function in a
#: zone other than a player's hand".
PLOT_FROM_LIBRARY_TOP_RE = re.compile(
    r"^you may plot (?P<quality>[\w -]+?) cards from the top of your library\.?$",
    re.IGNORECASE,
)


@cache
def _plot_from_top_quality(text: str) -> Any:
    from .casting.permissions import spell_quality_predicate

    match = PLOT_FROM_LIBRARY_TOP_RE.fullmatch(text.strip())
    if match is None:
        return None
    return spell_quality_predicate(match.group("quality"))


def reads_library_plot_grant_line(text: str) -> bool:
    """Whether `text` is one of the two lines `library_top_plot_cost` reads."""
    stripped = text.strip()
    if LIBRARY_TOP_HAS_PLOT_RE.fullmatch(stripped) is not None:
        return True
    return _plot_from_top_quality(stripped) is not None


def library_top_plot_cost(game: Game | None, card: CardState, player: str) -> str | None:
    """The plot cost `card` has on top of `player`'s library, or None when no
    permanent `player` controls both gives the top card plot and lets a card
    of its quality be plotted from there (CR 702.170f). The cost is the card's
    own mana cost (the grant's "The plot cost is equal to its mana cost.").
    """
    if game is None or card.zone is not Zone.LIBRARY or card.owner != player:
        return None
    library = game.player(player).library
    if not library or library[0] is not card:
        return None
    board = game.computed_board()
    for permanent in game.permanents_controlled_by(player):
        lines = [line.strip() for line in board.of(permanent).abilities]
        if not any(LIBRARY_TOP_HAS_PLOT_RE.fullmatch(line) for line in lines):
            continue
        for line in lines:
            allows = _plot_from_top_quality(line)
            if allows is not None and allows(card):
                return card.card.mana_cost or "{0}"
    return None


def prints_cloak_clause(card: Card) -> bool:
    """Whether some ability of `card`'s own text performs a cloak instruction
    - its whole effect read by a production dispatcher, not a notice - which
    is what credits the Cloak keyword (CR 701.58a) as executed by
    `machines/effects/library._parse_cloak_clause`. A cloak clause inside an
    effect nothing reads whole (Cryptic Coat's "cloak ..., then attach this
    Equipment to it") credits nothing."""
    texts = [card.oracle_text or ""] + [face.oracle_text or "" for face in card.card_faces or []]
    return any(
        _cloak_line_is_performed(line)
        for text in texts
        for line in text.splitlines()
        if "cloak" in line.lower()
    )


@cache
def _cloak_line_is_performed(line: str) -> bool:
    from .effects.dispatch import _ability_effect_or_notice
    from .effects.tokens import _is_notice_only

    # A mode line ("\u2022 Cloak a card from your hand.") is its own effect.
    stripped = re.sub(r"\s*\([^()]*\)", "", line).strip().lstrip("\u2022").strip()
    if ": " in stripped:
        effect_text = stripped.split(": ", 1)[1]
    elif re.match(r"^(?:when|whenever|at)\b", stripped, re.IGNORECASE):
        effect_text = stripped.split(", ", 1)[1] if ", " in stripped else ""
    else:
        effect_text = stripped
    if not any(
        read_cloak_clause(re.sub(r"^(?:then|and)\s+", "", piece.strip(), flags=re.IGNORECASE))
        for piece in re.split(r"[.]|, (?:then )?", effect_text)
    ):
        return False
    effect = _ability_effect_or_notice(effect_text)
    return effect is not None and not _is_notice_only(effect)
