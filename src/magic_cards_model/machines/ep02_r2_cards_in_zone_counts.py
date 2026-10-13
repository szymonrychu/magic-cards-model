"""EP-02 R2 T2: cards in a hand (and the remaining graveyard shapes) counted as
an amount, and "half" of a zone.

One reader per question, reused by every sentence that asks it:

    [the] [number of] [<description>] card(s) [with <keyword>] in <where>

- `<where>` is "your hand" (CR 402.1: the hand is a zone with no type
  restriction, so every card in it counts), "their hand" / "that player's
  hand" (the player the resolving ability targets or concerns, CR 109.5),
  "your opponents' hands" (every opponent's, summed), or a graveyard
  (CR 404.1, "your graveyard", "all graveyards", "your opponents'
  graveyards").
- `<keyword>` is a keyword ability the card carries; "cycling" also finds a
  card with typecycling (CR 702.29f).

`hand_count_expression` is the `(game, controller) -> int` reader
`amounts.count_expression` returns, taken once as the effect applies
(CR 608.2h). `static_zone_count` is the same count as a layer-engine `Count`
factory, so a static "gets +1/+1 for each card in your hand" re-reads the hand
on every board computation (CR 613.4c, CR 611.3a).

"Half of a zone" (CR 107.1a: the card prints which way the fraction rounds) is
`half_of_zone`: the `(game, player) -> int` size of half a player's hand,
library or permanents of a kind.
"""

import re
from collections.abc import Callable
from functools import cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..models.card_state import CardState
    from ..models.game import Game
    from .layers.apply import LayerContext
    from .layers.model import Count

Reader = Callable[["Game", str], int]

_WHERE = (
    r"(?P<where>your hand|their hand|that player's hand|your opponents' hands"
    r"|your graveyard|all graveyards|your opponents' graveyards)"
)
_ZONE_COUNT_RE = re.compile(
    rf"^(?:the )?(?:number of )?(?:(?P<quality>[a-z][a-z ,/-]*?) )?cards? "
    rf"(?:with (?:an? )?(?P<keyword>[a-z]+)(?: ability)? )?in {_WHERE}$",
    re.IGNORECASE,
)


def _has_keyword(card: "CardState", keyword: str) -> bool:
    """A card "with cycling": its keyword line carries it, and every
    typecycling is a cycling ability (CR 702.29f)."""
    return any(
        word.lower() == keyword or (keyword == "cycling" and word.lower().endswith("cycling"))
        for word in card.keywords
    )


@cache
def _parse(phrase: str):
    """`(quality, keyword, where)` for a zone-count phrase, or `None`."""
    text = " ".join(phrase.split()).rstrip(".")
    if " in " not in text or "card" not in text:
        return None
    match = _ZONE_COUNT_RE.fullmatch(text)
    if match is None:
        return None
    quality = match.group("quality")
    keyword = match.group("keyword")
    return quality, keyword.lower() if keyword else None, match.group("where").lower()


def hand_count_expression(phrase: str) -> Reader | None:
    """`phrase` as a live count of cards in a hand (or a graveyard, keyword
    description included), or `None` when it is not that shape."""
    return _hand_count_expression(" ".join(phrase.split()).rstrip("."))


@cache
def _hand_count_expression(text: str) -> Reader | None:
    parsed = _parse(text)
    if parsed is None:
        return None
    quality, keyword, where = parsed
    from .ep02_r1_graveyard_counts import _quality, _referent_player

    matches = _quality(quality)
    if matches is None:
        return None

    def count(game: "Game", controller: str) -> int:
        if where == "your hand":
            piles = [game.player(controller).hand]
        elif where in ("their hand", "that player's hand"):
            piles = [game.player(_referent_player(game, controller)).hand]
        elif where == "your opponents' hands":
            piles = [p.hand for p in game.players_in_game if p.username != controller]
        elif where == "your graveyard":
            piles = [game.player(controller).graveyard]
        elif where == "your opponents' graveyards":
            piles = [p.graveyard for p in game.players if p.username != controller]
        else:
            piles = [p.graveyard for p in game.players]
        return sum(
            1
            for pile in piles
            for card in pile
            if matches(card) and (keyword is None or _has_keyword(card, keyword))
        )

    return count


@cache
def static_zone_count(phrase: str) -> "Callable[[CardState, LayerContext], Count] | None":
    """The layer-engine twin of `hand_count_expression`: a factory of the
    `Count` a static ability's pump multiplies, re-built on every board
    computation so it follows the zone as cards enter and leave it."""
    parsed = _parse(" ".join(phrase.split()).rstrip("."))
    if parsed is None:
        return None
    quality, keyword, where = parsed
    from .layers.model import FixedCount
    from .layers.parse import _cda_card_matches, _cda_pile, _cda_quality, _CdaQuality

    if where in ("their hand", "that player's hand"):
        return None
    is_hand = where.endswith(("hand", "hands"))
    if is_hand and (quality is not None or keyword is not None):
        return None  # the layer context carries hand sizes, not hand cards
    description = (
        _CdaQuality((), (), (), False, False) if quality is None else _cda_quality(quality)
    )
    if description is None:
        return None

    def factory(source: "CardState", context: "LayerContext") -> "Count":
        mine = source.controller or ""
        if where == "your hand":
            return FixedCount(value=context.hand_size_by_controller.get(mine, 0))
        if where == "your opponents' hands":
            return FixedCount(
                value=sum(
                    size for who, size in context.hand_size_by_controller.items() if who != mine
                )
            )
        return FixedCount(
            value=sum(
                1
                for card in _cda_pile(where, source, context)
                if _cda_card_matches(description, card)
                and (keyword is None or _has_keyword(card, keyword))
            )
        )

    return factory


_ATTACHED_PUMP_PER_ZONE_RE = re.compile(
    r"^(?P<attachment>equipped|enchanted) creature "
    r"(?:has (?P<keywords>.+?) and )?"
    r"gets (?P<power>[+-]\d+)/(?P<toughness>[+-]\d+) for each (?P<each>.+?)"
    r"(?: and is an? (?P<subtype>[a-z]+) in addition to its other types)?\.?$",
    re.IGNORECASE,
)


@cache
def attached_pump_per_zone_count(sentence: str):
    """ "Equipped creature gets +1/+1 for each card in your hand" (Empyrial
    Plate), "Equipped creature has first strike and gets +1/+0 for each instant
    and sorcery card in your graveyard" (Glamdring), "Enchanted creature gets
    +1/+1 for each creature card in your graveyard and is an Avatar in addition
    to its other types" (Avatar Destiny): the attached creature's sublayer 7c
    bonus (CR 613.4c) sized by a zone count, re-read on every board computation
    (CR 611.3a). The keywords are layer 6 (CR 613.1f), the subtype layer 4
    (CR 613.1d, CR 205.1b: "in addition to" adds). An unattached source gives
    nothing (CR 301.5a, CR 303.4b). Returns an `EffectBuilder`, or `None`."""
    match = _ATTACHED_PUMP_PER_ZONE_RE.fullmatch(sentence.strip())
    if match is None:
        return None
    count = static_zone_count(match.group("each").strip())
    if count is None:
        return None
    from ..data.subtypes import canonical_subtype
    from .layers.model import (
        ContinuousEffect,
        Layer,
        Sublayer,
        add_subtype,
        modify_power_toughness_per,
    )
    from .layers.parse import (
        _attached_creature_static_builder,
        _only,
        _source_line_for,
        _split_and_validate_keywords,
    )

    keywords: list[str] = []
    if match.group("keywords") is not None:
        validated = _split_and_validate_keywords(match.group("keywords"))
        if validated is None:
            return None
        keywords = validated
    subtype = None
    if match.group("subtype") is not None:
        subtype = canonical_subtype(match.group("subtype"))
        if subtype is None:
            return None
    subject = match.group("attachment").lower()
    power, toughness = int(match.group("power")), int(match.group("toughness"))
    grants = _attached_creature_static_builder(0, 0, keywords, subject=subject, line=sentence)

    def builder(source, timestamp, targets, context):
        attached = source.attached_to
        if attached is None:
            return []
        effects = list(grants(source, timestamp, targets, context)) if keywords else []

        def effect(what, layer, sublayer, modification):
            return ContinuousEffect(
                description=f"{source.name}: {subject} creature {what}",
                layer=layer,
                sublayer=sublayer,
                timestamp=timestamp,
                source_id=source.id,
                source_ability=_source_line_for(source, sentence),
                selector=_only(attached),
                modification=modification,
            )

        effects.append(
            effect(
                f"gets {power:+d}/{toughness:+d} for each {match.group('each')}",
                Layer.POWER_TOUGHNESS,
                Sublayer.MODIFY,
                modify_power_toughness_per(count(source, context), power, toughness),
            )
        )
        if subtype is not None:
            effects.append(effect(f"is a {subtype}", Layer.TYPE, None, add_subtype(subtype)))
        return effects

    return builder


# --------------------------------------------------------------------------
# Half of a zone (CR 107.1a: the card prints which way the fraction rounds)
# --------------------------------------------------------------------------
#
# The clause runs against the player the wrapper resolved ("target opponent
# discards ...", "defending player ..."); "their"/"they" is that player.
# `mills`/`exiles` half a library is `dispatch._HALF_OF_OWN_LIBRARY_RE`'s.

_HALF_DISCARD_RE = re.compile(
    r"^discards? half (?:the cards in )?(?:their|your) hand, rounded (?P<direction>up|down)$",
    re.IGNORECASE,
)
_HALF_SACRIFICE_RE = re.compile(
    r"^sacrifices? half the (?P<description>.+?) (?:they|you) control of (?:their|your) choice, "
    r"rounded (?P<direction>up|down)$",
    re.IGNORECASE,
)


def parse_half_of_zone_clause(clause: str):
    """ "discards half the cards in their hand, rounded down" (Lord Xander),
    "sacrifices half the creatures they control of their choice, rounded up"
    (Rush of Dread), as a `ClauseEffect` `(game, player, source, source_id)`.

    The size is taken once, as the effect applies (CR 608.2h). A discard is the
    discarding player's own choice (CR 701.9b); a sacrifice picks among the
    permanents that player controls (CR 701.21a) and asks nothing when every
    one of them goes (CR 608.2d: no impossible choice)."""
    from ..numbers import halve

    text = clause.strip().rstrip(".")
    if not text.lower().startswith(("discard", "sacrifice")) or " half " not in text.lower():
        return None
    if match := _HALF_DISCARD_RE.fullmatch(text):
        round_up = match.group("direction").lower() == "up"

        def discard_half(game, player, source, source_id):
            from .effects.draw_discard import _discard_cards

            count = halve(len(player.hand), round_up=round_up)
            if count > 0:
                _discard_cards(game, player, count, source, source_id=source_id, exact=True)

        return discard_half
    if match := _HALF_SACRIFICE_RE.fullmatch(text):
        from .targeting import permanent_description

        # "creatures" / "nonland permanents": the target grammar reads the singular.
        requirement = permanent_description(re.sub(r"s$", "", match.group("description").strip()))
        if requirement is None:
            return None
        round_up = match.group("direction").lower() == "up"

        def sacrifice_half(game, player, source, source_id):
            from ..models.zone import Zone
            from .decisions import Decision, DecisionKind

            candidates = [
                permanent
                for permanent in game.permanents_controlled_by(player.username)
                if requirement.rejects(permanent, player.username, game) is None
            ]
            count = halve(len(candidates), round_up=round_up)
            if count <= 0:
                return
            chosen = candidates
            if count < len(candidates):
                ids = game.ask(
                    Decision(
                        kind=DecisionKind.CHOOSE_CARDS,
                        player=player.username,
                        prompt=f"sacrifice {count} of {len(candidates)} permanents",
                        source=source,
                        amount=count,
                        cards=tuple(permanent.id for permanent in candidates),
                        source_id=source_id,
                    )
                )
                by_id = {permanent.id: permanent for permanent in candidates}
                chosen = [by_id[card_id] for card_id in ids if card_id in by_id]
            for permanent in chosen:
                if permanent.zone is Zone.BATTLEFIELD:
                    game.sacrifice(permanent)

        return sacrifice_half
    return None


def parse_defending_player_clause(clause: str, *, for_spell: bool):
    """ "defending player mills half their library, rounded up" (Terisian
    Mindbreaker), "defending player discards a card": the verb is any clause
    `parse_clause_effect` reads, run against the defending player of the
    attacker that triggered it (CR 508.5, `damage._defending_player_of_trigger`).
    Ability-only: a spell has no attack event to name a defending player."""
    text = clause.strip()
    if for_spell or not text.lower().startswith("defending player "):
        return None
    from .decisions import source_id_of
    from .effects.damage import _defending_player_of_trigger
    from .effects.dispatch import parse_clause_effect
    from .triggers.events import AbilityOnStack

    rest = text[len("defending player ") :].strip()
    clause_effect = parse_clause_effect(rest) or parse_clause_effect(f"you {rest}")
    if clause_effect is None:
        return None

    def effect(game, stack_object):
        assert isinstance(stack_object, AbilityOnStack)
        defending = _defending_player_of_trigger(game, stack_object)
        if defending is None:
            return
        clause_effect(
            game, game.player(defending), stack_object.source_name, source_id_of(stack_object)
        )

    return effect
