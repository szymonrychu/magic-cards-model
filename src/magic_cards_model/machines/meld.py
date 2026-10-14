"""Meld (CR 701.42, CR 712.4-712.21): two cards becoming one permanent.

CR 701.42a: "Meld is a keyword action that appears in an ability on one card
in a meld pair. To meld the two cards in a meld pair, put them onto the
battlefield with their back faces up and combined. The resulting permanent
is a single object represented by two cards."

Every real meld pair prints the same templated condition and instruction
(CR 712.5's own list of seven), on either an *activated* ability (Hanweir
Battlements: "{3}{R}{R}, {T}: If you both own and control this land and a
creature named Hanweir Garrison, exile them, then meld them into Hanweir,
the Writhing Township.") or a *triggered* one (Graf Rats: "At the beginning
of combat on your turn, if you both own and control this creature and a
creature named Midnight Scavengers, exile them, then meld them into
Chittering Host."). Both share the identical inner clause - "you both own
and control this <type> and a[nother] <type> named <partner>, exile them,
then meld them into <result>" - which is what this module reads, once,
rather than teaching the activated and triggered dispatchers two unrelated
parsers.

`Game.meld` (in `models/game.py`) is the actual mechanic - the object-
identity subsystem this module's parsers call into. Every CR number here was
looked up with `mise run rules:find` against the 2026-08-19 Comprehensive
Rules in the session that wrote this file.
"""

import re
from typing import TYPE_CHECKING

from magic_cards_model.text_norm import collapsed

from ..data.printing_pool import resolve_printing
from ..models.card import Card, Component
from ..models.card_state import CardState

if TYPE_CHECKING:
    from ..models.game import Game
    from .triggers import AbilityOnStack


def has_meld(card: Card) -> bool:
    """CR 701.42a: whether this card carries the meld keyword action, read
    off Scryfall's own `keywords` list - the same convention `machines/
    keywords.has_rebound`/`has_paradigm` use."""
    return any(keyword.lower() == "meld" for keyword in card.keywords)


def meld_result_name(card: Card) -> str | None:
    """The name of the combined back face this card's meld pair forms
    (CR 701.42a, CR 712.5), read off Scryfall's own `all_parts` component -
    not off the ability's own prose, which `tests/test_mana.py::_is_meld_
    result` reads the same way in the opposite direction."""
    for part in card.all_parts or ():
        if part.component == Component.MELD_RESULT:
            return part.name
    return None


#: The condition's own inner shape, common to every meld pair (CR 712.5a-g):
#: "you both own and control this <type> and a[nother] [<type> ]named
#: <partner>". Matched against the *whole* condition string, whether that
#: string is a triggered ability's stripped `intervening_if` (no leading
#: "if") or a fragment inside the activated form's own longer sentence.
_OWN_CONTROL_RE = re.compile(
    r"you both own and control this \w+ and an?(?:other)? (?:\w+ )?named (?P<partner>[^,]+)",
    re.IGNORECASE,
)

#: The resolution instruction alone: "exile them, then meld them into
#: <result>." This is all that is left of a triggered ability's `effect`
#: once the ordinary trigger parser has split its own leading intervening
#: *if* off into `condition`/`intervening_if` - and it is also the tail of
#: the activated form's one sentence, matched separately by `_ACTIVATION_RE`
#: below rather than split in two.
_MELD_RESOLUTION_RE = re.compile(
    r"^exile them,?\s*then meld them into (?P<result>.+?)\.?$", re.IGNORECASE
)

#: The whole activated-ability sentence, condition and resolution together -
#: an activated ability has no separate intervening-*if* field the way a
#: triggered ability's `TriggeredAbility.intervening_if` does, so both halves
#: have to come out of one match here.
_ACTIVATION_RE = re.compile(
    r"^if (?P<condition>you both own and control this \w+ and an?(?:other)? "
    r"(?:\w+ )?named [^,]+),\s*exile them,?\s*then meld them into "
    r"(?P<result>.+?)\.?$",
    re.IGNORECASE,
)


def meld_condition_holds(game: "Game", clause: str, source: CardState) -> bool | None:
    """Whether CR 701.42a's "you both own and control ..." clause is true
    for `source` right now.

    `None` when `clause` is not this shape at all - a signal to the caller
    (`machines/triggers.intervening_if_holds`) to keep trying its other
    readers rather than treat an unrelated clause as a definite `False`.
    """
    match = _OWN_CONTROL_RE.search(clause.strip())
    if match is None:
        return None
    return _find_partner(game, source, match.group("partner").strip()) is not None


def _find_partner(game: "Game", source: CardState, partner_name: str) -> CardState | None:
    """The named partner, on the battlefield, owned *and* controlled by
    `source`'s own controller (CR 701.42a's "you both own and control").

    Matched case-insensitively: `machines/triggers.intervening_if_holds`
    lowercases `TriggeredAbility.intervening_if` before this is ever asked
    (see `meld_condition_holds`'s own caller), while `parse_meld_resolution_
    clause`'s effect closure reads the same field's original casing - both
    have to find the identical permanent.
    """
    lowered = partner_name.lower()
    controller = game.controller_of(source).username
    for permanent in game.permanents_controlled_by(controller):
        if (
            permanent.id != source.id
            and permanent.name.lower() == lowered
            and permanent.owner == controller
        ):
            return permanent
    return None


def _do_meld(game: "Game", ability: "AbilityOnStack", partner_name: str, result_name: str) -> None:
    """CR 701.42a/701.42c: meld if the pair can still be found, otherwise
    "they stay in their current zone" - a no-op, since nothing has moved yet.
    """
    source = game.find_by_id(ability.source_id) if ability.source_id is not None else None
    if not isinstance(source, CardState):
        return
    partner = _find_partner(game, source, partner_name)
    if partner is None:
        return  # CR 701.42c: can't be melded (only one half present, say).
    result_card = resolve_printing(collapsed(result_name))
    if result_card is None:
        from .effects import UnmodeledTriggerEffectNotice

        game.unmodeled_trigger_effect_notices.append(
            UnmodeledTriggerEffectNotice(
                source_id=source.id,
                source_name=source.name,
                text=f"meld them into {result_name}",
            )
        )
        return
    game.meld(source, partner, result_card)


def parse_meld_activation_clause(effect_text: str):
    """An activated ability's own meld clause (Hanweir Battlements' shape),
    or `None`. Returned as the `AbilityEffect` `activated_effect_for`'s
    fallback chain expects: `(game, ability) -> None`.
    """
    match = _ACTIVATION_RE.match(collapsed(effect_text))
    if match is None:
        return None
    result_name = match.group("result")
    condition_match = _OWN_CONTROL_RE.search(match.group("condition"))
    if condition_match is None:
        return None
    partner_name = condition_match.group("partner").strip()

    def effect(game: "Game", ability: "AbilityOnStack") -> None:
        # An activated ability's cost is already paid by the time this runs
        # (CR 602.2), and CR 701.42c's own "can't be melded -> stays put" is
        # exactly `_do_meld`'s no-op branch when `partner_name` cannot be
        # found - so the CR 701.42a condition is re-checked here for real,
        # not merely announced, the same way any other "if you control ..."
        # resolution-time conditional in this engine is.
        _do_meld(game, ability, partner_name, result_name)

    return effect


def parse_meld_resolution_clause(effect_text: str):
    """A triggered ability's meld *resolution* (Graf Rats' shape, once its
    own intervening `if you both own and control ...` clause has already
    gated whether this ever runs) - or `None`. The partner's name is not in
    `effect_text` at all (it was in the condition, already checked by the
    time this resolves), so it is re-read off the ability's own printed
    `intervening_if`/`condition` at call time rather than threaded through a
    second parameter no other `AbilityEffect` in this codebase carries.
    """
    match = _MELD_RESOLUTION_RE.match(collapsed(effect_text))
    if match is None:
        return None
    result_name = match.group("result")

    def effect(game: "Game", ability: "AbilityOnStack") -> None:
        printed = ability.ability
        clause = (
            getattr(printed, "intervening_if", None) or getattr(printed, "condition", None) or ""
        )
        condition_match = _OWN_CONTROL_RE.search(clause)
        if condition_match is None:
            return
        _do_meld(game, ability, condition_match.group("partner").strip(), result_name)

    return effect
