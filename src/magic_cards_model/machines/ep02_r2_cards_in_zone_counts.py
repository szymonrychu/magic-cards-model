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


# --------------------------------------------------------------------------
# The difference between two hand sizes
# --------------------------------------------------------------------------

_HAND_DIFFERENCE_SPELL_RE = re.compile(
    r"^if target (?:opponent|player) has more cards in hand than you, "
    r"draw cards equal to the difference$",
    re.IGNORECASE,
)


def parse_hand_difference_spell(text: str):
    """ "If target opponent has more cards in hand than you, draw cards equal
    to the difference." (Balance of Power): both hand sizes are read as the
    spell resolves (CR 608.2h), so the spell itself has already left the
    caster's hand. A tie, or a target with fewer cards, draws nothing
    (CR 608.2c). Returns an `Effect` `(game, spell)`, or `None`."""
    if "equal to the difference" not in text.lower():
        return None
    if _HAND_DIFFERENCE_SPELL_RE.fullmatch(" ".join(text.split()).rstrip(".")) is None:
        return None
    from ..models.player import Player

    def effect(game, spell):
        controller = game.controller_of(spell)
        targets = [t for t in game.resolve_targets(spell) if isinstance(t, Player)]
        if not targets:
            return  # CR 608.2b: no legal target, nothing happens
        difference = len(targets[0].hand) - len(controller.hand)
        if difference > 0:
            game.draw_cards(controller.username, difference)

    return effect


# --------------------------------------------------------------------------
# An attached creature (and a named creature) pumped by a hand count
# --------------------------------------------------------------------------

_ATTACHED_PUMP_UNTIL_EOT_RE = re.compile(
    r"^(?P<attachment>equipped|enchanted) creature"
    r"(?: or an? (?:other )?creature you control named (?P<named>.+?))? "
    r"gets (?P<power>[+-](?:\d+|x))/(?P<toughness>[+-](?:\d+|x)) until end of turn"
    r"(?:, where x is (?P<where>.+?))?$",
    re.IGNORECASE,
)


def parse_attached_pump_until_end_of_turn_clause(clause: str, *, for_spell: bool):
    """ "equipped creature or a creature you control named Vecna gets +X/+X
    until end of turn, where X is the number of cards in your hand" (Hand of
    Vecna), "equipped creature gets +1/+1 until end of turn" off a beginning
    of combat trigger: a one-shot continuous effect (CR 611.2) on each creature
    the phrase names as the ability resolves - the creature the source is
    attached to, and every creature its controller controls with the printed
    name (CR 201.2). X is taken once, as the ability resolves (CR 608.2h), and
    an unattached source pumps only the named creature (CR 301.5). Ability-only:
    the source is a permanent. Returns an `AbilityEffect`, or `None`."""
    if for_spell:
        return None
    match = _ATTACHED_PUMP_UNTIL_EOT_RE.fullmatch(" ".join(clause.split()).rstrip("."))
    if match is None:
        return None
    from .effects.amounts import count_expression

    where = match.group("where")
    count = count_expression(where.strip()) if where else None
    if count is None and "x" in (match.group("power") + match.group("toughness")).lower():
        return None
    named = match.group("named")
    power, toughness = match.group("power").lower(), match.group("toughness").lower()

    def effect(game, ability):
        from ..models.card_state import CardState
        from ..models.zone import Zone
        from .effects.continuous import continuous_effects
        from .layers import (
            ContinuousEffect,
            Duration,
            Layer,
            Sublayer,
            modify_power_toughness,
        )
        from .layers.model import only_this_incarnation

        controller = game.controller_of(ability)
        x = count(game, controller.username) if count is not None else 0

        def amount(printed: str) -> int:
            return int(printed[0] + "1") * x if printed[1:] == "x" else int(printed)

        source = ability.source_or_last_known(game)
        recipients = []
        if source is not None and source.attached_to is not None:
            attached = game.find_by_id(source.attached_to)
            if isinstance(attached, CardState) and attached.zone is Zone.BATTLEFIELD:
                recipients.append(attached)
        if named is not None:
            for permanent in game.permanents_controlled_by(controller.username):
                if permanent.name.lower() == named.strip().lower() and permanent not in recipients:
                    recipients.append(permanent)
        store = continuous_effects(game)
        for recipient in recipients:
            store.add(
                ContinuousEffect(
                    description=(
                        f"{recipient.name}: gets {amount(power):+d}/{amount(toughness):+d} "
                        "until end of turn"
                    ),
                    layer=Layer.POWER_TOUGHNESS,
                    sublayer=Sublayer.MODIFY,
                    timestamp=store.tick(),
                    duration=Duration.UNTIL_END_OF_TURN,
                    source_id=ability.source_id,
                    selector=only_this_incarnation(recipient, recipient.zone_change_stamp),
                    modification=modify_power_toughness(amount(power), amount(toughness)),
                )
            )

    return effect


# --------------------------------------------------------------------------
# A keyword cost scaled by the hand: "Equip - Pay 1 life for each card in your hand"
# --------------------------------------------------------------------------

_PAY_LIFE_PER_HAND_CARD_RE = re.compile(
    r"^pay (?P<n>\d+) life for each card in your hand$", re.IGNORECASE
)


def hand_scaled_cost(phrase: str, game, payer: str):
    """ "Pay 1 life for each card in your hand" (Hand of Vecna's equip) as a
    `TotalCost`: the amount is the hand size now, as the cost is determined
    (CR 601.2f via CR 602.2b), so an empty hand pays nothing (CR 118.3b: 0 life
    is always payable). `None` when `phrase` is not that shape."""
    match = _PAY_LIFE_PER_HAND_CARD_RE.fullmatch(phrase.strip().rstrip("."))
    if match is None or game is None:
        return None
    from .cost import pay_life_cost
    from .cost.components import TotalCost

    amount = int(match.group("n")) * len(game.player(payer).hand)
    return TotalCost(components=[pay_life_cost(amount, payer, description=phrase)]).assign_payer(
        payer
    )


# --------------------------------------------------------------------------
# "Mill cards equal to its power. Return this card to its owner's hand and up
# to one creature card milled this way to the battlefield under your control."
# --------------------------------------------------------------------------

_RETURN_SELF_AND_MILLED_RE = re.compile(
    r"^return (?:this card|it) to its owner's hand and up to one (?P<group>[a-z]+) card "
    r"milled this way to the battlefield under your control\.?$",
    re.IGNORECASE,
)


def parse_mill_by_stat_then_return_self_and_milled(text: str):
    """Avatar Destiny's dies trigger. Sentence one mills as many cards as the
    object that died had power (CR 603.10a's last known information, the same
    `StatRef` reader every "equal to its power" amount uses). Sentence two
    returns the source to its owner's hand if it is still in the graveyard it
    just went to (CR 400.7) and lets the controller put up to one qualifying
    card among the milled ones onto the battlefield under their control
    (CR 608.2d: only milled cards still in the graveyard are offered).
    Returns an `AbilityEffect`, or `None`."""
    from .amount_sentences import parse_mill_clause
    from .ep02_r1_referenced_stat import (
        default_referent,
        normalize,
        parse_stat_phrase,
        stat_value,
    )

    sentences = [part.strip() for part in re.split(r"(?<=\.)\s+", " ".join(text.split()))]
    if len(sentences) != 2 or "milled this way" not in text.lower():
        return None
    mill = parse_mill_clause(normalize(sentences[0]))
    ref = parse_stat_phrase(mill.expr or "") if mill is not None and mill.kind == "equal" else None
    second = _RETURN_SELF_AND_MILLED_RE.fullmatch(sentences[1])
    if mill is None or ref is None or mill.who not in ("", "you") or second is None:
        return None
    from .effects.library import _card_description_is_readable, _mill, _quality_matcher

    if not _card_description_is_readable(second.group("group")):
        return None
    wanted = _quality_matcher(second.group("group"))

    def effect(game, ability):
        from ..models.zone import Zone
        from .decisions import Decision, DecisionKind, source_id_of

        controller = game.controller_of(ability)
        amount = stat_value(default_referent(game, ability, ref.anchor), ref.stat)
        milled = _mill(game, controller, amount) if amount > 0 else []
        source = game.find_by_id(ability.source_id)
        if source is not None and source.zone is Zone.GRAVEYARD:
            game.return_to_hand(source)
        candidates = [card for card in milled if card.zone is Zone.GRAVEYARD and wanted(card)]
        if not candidates:
            return
        chosen_ids = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=controller.username,
                prompt=f"put up to one {second.group('group')} card milled this way "
                "onto the battlefield",
                source=ability.source_name,
                source_id=source_id_of(ability),
                amount=1,
                exact=False,
                cards=tuple(card.id for card in candidates),
            )
        )
        by_id = {card.id: card for card in candidates}
        for card_id in list(chosen_ids)[:1]:
            if (card := by_id.get(card_id)) is not None and card.zone is Zone.GRAVEYARD:
                game.put_onto_battlefield(card, controller.username)

    return effect


# --------------------------------------------------------------------------
# "You have no maximum hand size for as long as you control this Saga."
# --------------------------------------------------------------------------

_NO_MAX_HAND_WHILE_CONTROLLING_RE = re.compile(
    r"^you have no maximum hand size for as long as you control (?:this [a-z]+|it)$",
    re.IGNORECASE,
)


def parse_no_maximum_hand_size_while_controlling_clause(clause: str, *, for_spell: bool):
    """Jin-Gitaxias // The Great Synthesis' chapter I rider. A layer 6 grant
    (CR 613.1f) of the static "You have no maximum hand size." to the source,
    which `Player.has_no_maximum_hand_size` already reads off a permanent's
    lines (CR 402.2, CR 613.11). Duration is CR 611.2b's "for as long as you
    control this", `YouStillControl`: it ends the moment the source leaves or
    changes controller and does not come back (CR 400.7). Ability-only."""
    if (
        for_spell
        or _NO_MAX_HAND_WHILE_CONTROLLING_RE.fullmatch(" ".join(clause.split()).rstrip(".")) is None
    ):
        return None

    def effect(game, ability):
        from ..models.zone import Zone
        from .effects.continuous import continuous_effects
        from .layers import ContinuousEffect, Duration, Layer, grant_ability
        from .layers.model import YouStillControl, only_this_incarnation

        source = ability.source(game)
        if (
            source is None
            or source.zone is not Zone.BATTLEFIELD
            or source.zone_change_stamp is None
            or source.controller is None
            or (
                ability.source_stamp is not None
                and source.zone_change_stamp != ability.source_stamp
            )
        ):
            return
        store = continuous_effects(game)
        store.add(
            ContinuousEffect(
                description=f"{source.name}: its controller has no maximum hand size",
                layer=Layer.ABILITY,
                timestamp=store.tick(),
                duration=Duration.FOR_AS_LONG_AS,
                condition=YouStillControl(
                    card_id=source.id,
                    stamp=source.zone_change_stamp,
                    controller=source.controller,
                ),
                selector=only_this_incarnation(source, source.zone_change_stamp),
                modification=grant_ability("You have no maximum hand size."),
            ),
            game,
        )

    return effect


# --------------------------------------------------------------------------
# "You may cast any number of spells from your hand without paying their mana costs."
# --------------------------------------------------------------------------

_CAST_ANY_NUMBER_FROM_HAND_FREE_RE = re.compile(
    r"^you may cast any number of spells from your hand without paying their mana costs$",
    re.IGNORECASE,
)


def parse_cast_any_number_from_hand_free_clause(clause: str, *, for_spell: bool):
    """Jin-Gitaxias // The Great Synthesis' chapter III. Spells are cast one at
    a time during resolution (CR 608.2g: each follows CR 601.2a-i with no
    priority, and lands as the topmost object of the stack), choosing among
    the cards that can really be cast now (CR 608.2d) until the controller
    stops or none is left. Casting one first can empty or change the hand, so
    the choice is offered again afterwards."""
    if _CAST_ANY_NUMBER_FROM_HAND_FREE_RE.fullmatch(" ".join(clause.split()).rstrip(".")) is None:
        return None

    def effect(game, stack_object):
        from .decisions import Decision, DecisionKind, source_id_of

        player = game.controller_of(stack_object)
        source = getattr(stack_object, "source_name", None) or stack_object.name
        while True:
            legal = [
                card
                for card in player.hand
                if not card.card.is_land and game.can_cast_during_resolution(card, player.username)
            ]
            if not legal:
                return
            chosen_ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=player.username,
                    prompt="choose a spell to cast without paying its mana cost",
                    source=source,
                    source_id=source_id_of(stack_object),
                    amount=1,
                    exact=False,
                    cards=tuple(card.id for card in legal),
                )
            )
            by_id = {card.id: card for card in legal}
            picked = [by_id[card_id] for card_id in chosen_ids if card_id in by_id]
            if not picked:
                return
            game.cast_during_resolution(
                picked[0], player.username, source_name=source, rule="CR 608.2g"
            )
            if picked[0] in player.hand:
                return  # the cast was not made; offering it again would loop

    return effect
