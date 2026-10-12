"""Attach keywords: living weapon, For Mirrodin!, job select and fortify.

CR 702.92a: "Living weapon is a triggered ability. 'Living weapon' means 'When
this Equipment enters, create a 0/0 black Phyrexian Germ creature token, then
attach this Equipment to it.'"
CR 702.163a: "For Mirrodin! is a triggered ability. 'For Mirrodin!' means
'When this Equipment enters, create a 2/2 red Rebel creature token, then
attach this Equipment to it.'"
CR 702.182a: "Job select is a triggered ability. 'Job select' means 'When this
Equipment enters, create a 1/1 colorless Hero creature token, then attach this
Equipment to it.'"

The three are one shape - a token of a fixed description, then the attach - so
each is written out as the triggered ability the rule says it is
(`keywords._TRIGGER_EXPANSIONS`), and the effect text is the one the ordinary
"create a token, then attach this Equipment to it" reader
(`effects.tokens._parse_create_token_then_attach_clause`) already runs.

CR 702.67a: "Fortify is an activated ability of Fortification cards. 'Fortify
[cost]' means '[Cost]: Attach this Fortification to target land you control.
Activate only as a sorcery.'" It is equip's land twin (CR 301.6), written out
as a synthetic `KeywordActivation` the way `reconfigure.py` does: the target is
announced and checked at activation (CR 601.2c via CR 602.2b) and rechecked on
resolution (CR 608.2b). CR 702.67c: of several fortify abilities, any may be
used - the cheapest printed one is taken, as equip's CR 702.6c does.
"""

from typing import Any

from ..models.card import Card, Type
from ..models.card_state import CardState, TargetRef
from ..models.zone import Zone
from .abilities import KeywordAbility, TriggerEvent, TriggerWord, keyword_abilities
from .keywords import (
    _TRIGGER_EXPANSIONS,
    KEYWORD_EFFECTS,
    KeywordActivation,
    _expansion,
    _keyword_cost,
    _single,
    _synthetic_ability,
)

__all__ = [
    "FORTIFY_EFFECT",
    "FORTIFY_RULE",
    "fortify_activation",
    "has_fortify",
    "unannounced_fortify_activation",
]

FORTIFY_RULE = "CR 702.67a"
#: CR 702.67a's expansion of "Fortify [cost]", after the colon.
FORTIFY_EFFECT = "Attach this Fortification to target land you control."

#: keyword -> (rule, token description), each rule's own wording.
_TOKEN_KEYWORDS = {
    "living weapon": ("CR 702.92a", "a 0/0 black Phyrexian Germ creature token"),
    "for mirrodin!": ("CR 702.163a", "a 2/2 red Rebel creature token"),
    "job select": ("CR 702.182a", "a 1/1 colorless Hero creature token"),
}


def _token_then_attach(keyword: str):
    def build(ability: KeywordAbility):
        _rule, token = _TOKEN_KEYWORDS[keyword]
        return _expansion(
            ability,
            keyword=keyword,
            word=TriggerWord.WHEN,
            condition="this Equipment enters",
            effect=f"create {token}, then attach this Equipment to it",
            event=TriggerEvent.ENTERS_THE_BATTLEFIELD,
        )

    return build


_TRIGGER_EXPANSIONS.update({k: _single(_token_then_attach(k)) for k in _TOKEN_KEYWORDS})


# --------------------------------------------------------------------------
# Fortify (CR 702.67)
# --------------------------------------------------------------------------


def _fortify_abilities(card: Card) -> list[KeywordAbility]:
    return [a for a in keyword_abilities(card) if a.canonical.lower() == "fortify"]


def has_fortify(card: Card) -> bool:
    """Whether this card prints a fortify ability (CR 702.67a)."""
    return bool(_fortify_abilities(card))


def _is_land_now(game: Any, permanent: CardState) -> bool:
    try:
        return Type.LAND in game.characteristics_of(permanent).types
    except (AttributeError, KeyError):
        return permanent.is_land


def _cheapest(abilities: list[KeywordAbility], player: str) -> tuple[KeywordAbility, Any] | None:
    priced = [(a, _keyword_cost(a, player)) for a in abilities]
    priced = [(a, c) for a, c in priced if c is not None]
    if not priced:
        return None
    return min(priced, key=lambda pair: pair[1].mana.converted)


def unannounced_fortify_activation(
    game: Any, fortification: CardState, player: str
) -> KeywordActivation:
    """The fortify activation with no target announced yet (CR 702.67a): its
    cost, timing and rule, for a caller that asks before choosing
    (`legal_actions`). Never put on the stack; `fortify_activation` is the one
    that announces a target."""
    abilities = _fortify_abilities(fortification.card)
    if not abilities:
        raise ValueError(f"{fortification.name} has no fortify ability ({FORTIFY_RULE})")
    chosen = _cheapest(abilities, player)
    if chosen is None:
        raise ValueError(
            f"{fortification.name}'s fortify cost {abilities[0].cost!r} could not be read, "
            "so it cannot be paid"
        )
    ability, cost = chosen
    return KeywordActivation(
        card=fortification,
        player=player,
        keyword="Fortify",
        rule=FORTIFY_RULE,
        zone=Zone.BATTLEFIELD,
        cost=cost,
        sorcery_only=True,
        ability=_synthetic_ability(ability, cost_text=ability.cost or "", effect=FORTIFY_EFFECT),
        game=game,
    )


def _refusal(game: Any, fortification: CardState, land: Any, player: str) -> str | None:
    """Why `land` is not a legal fortify target (CR 301.6, CR 702.67a), or None."""
    from .keywords import _protection_refusal_for_attachment

    if not isinstance(land, CardState) or land.zone is not Zone.BATTLEFIELD:
        return f"{FORTIFY_RULE}: the target must be a land on the battlefield"
    if not _is_land_now(game, land):
        return f"{land.name} is not a land, so {fortification.name} cannot fortify it (CR 301.6)"
    if game.controller_of(land).username != player:
        return f"{player} does not control {land.name} ({FORTIFY_RULE})"
    if _is_creature_now(game, fortification):
        return f"{fortification.name} is a creature, so it cannot fortify a land (CR 301.6)"
    return _protection_refusal_for_attachment(game, fortification, land)


def _is_creature_now(game: Any, permanent: CardState) -> bool:
    try:
        return bool(game.characteristics_of(permanent).is_creature)
    except (AttributeError, KeyError):
        return permanent.is_creature


def fortify_activation(
    game: Any, fortification: CardState, land: CardState, player: str
) -> KeywordActivation:
    """CR 702.67a: "[Cost]: Attach this Fortification to target land you
    control. Activate only as a sorcery." The target is announced and checked
    here (CR 601.2c via CR 602.2b - an opponent's land, a nonland, a
    hexproof or protected land is refused before anything is paid); fortifying
    is rechecked on resolution (CR 608.2b)."""
    from .targeting import profile_for_text

    refusal = _refusal(game, fortification, land, player)
    if refusal is not None:
        raise ValueError(refusal)
    activation = unannounced_fortify_activation(game, fortification, player)
    profile_for_text(FORTIFY_EFFECT).check([land], player, game, source_id=fortification.id)
    activation.targets = [TargetRef.to_card(land)]
    return activation


def _fortify_effect(activation: KeywordActivation) -> CardState | None:
    """Resolve fortify (CR 608.2): attach to the target land if it is still
    legal (CR 608.2b), else nothing moves (CR 701.3b)."""
    game = activation.game
    fortification = game.find_by_id(activation.card.id)
    if not isinstance(fortification, CardState):
        fortification = activation.card
    if fortification.zone is not Zone.BATTLEFIELD:
        return None
    for target in activation.targets:
        land = game.resolve_target(target)
        if _refusal(game, fortification, land, activation.player) is not None:
            continue
        fortification.attach_to(land)
        return land
    return None


KEYWORD_EFFECTS["fortify"] = _fortify_effect
