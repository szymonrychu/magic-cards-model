"""Exile from the top of a library "until" a condition, then cast what was
exiled without paying its mana cost (ECL).

Two whole-text shapes, each one CR 608.2c instruction chain whose later
sentences point back ("exiled this way", "that card") at the first:

- **"Each `<opponent|player>` exiles cards from the top of their library
  until they have exiled cards with total mana value N or greater[ this
  way]. [Until end of turn, you may cast cards exiled this way without
  paying their mana costs.]"** - Dream Harvest, and Tasha's Hideous
  Laughter's bare first sentence. The same `keywords.exile_until` process
  every "until" shape uses, stopping once the running total of CR 202.3's
  mana values (a land's is 0) reaches N, run for each named player in APNAP
  order (CR 101.4). The permission is CR 601.3's, one `PlayPermission` per
  exiled card that can be cast at all (CR 305.9: a land is never cast),
  without paying its mana cost (CR 118.9), ending in the cleanup step
  (CR 514.2); timing is untouched (CR 117.1a).
- **"Exile cards from the top of your library until you exile a nonland
  card. You may cast that card without paying its mana cost if the spell's
  mana value is `<comparison>`. Otherwise, put it into your hand."** - Bre
  of Clan Stoutarm ("less than or equal to the amount of life you gained
  this turn"), Solstice Revelations ("less than the number of Mountains you
  control" ... "If you don't cast that card this way, put it into your
  hand.") and Breaching Dragonstorm ("You may cast it ... if that spell's
  mana value is 8 or less. If you don't, put that card into your hand.").
  The cast happens during the resolution (CR 608.2g); a card whose mana
  value misses the bound, or that the player declines to cast, goes to its
  owner's hand.
"""

import re
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ..models.card_state import CardState
from ..models.player import Player
from .decisions import source_id_of
from .effects import _INLINE_REMINDER_RE, _strip_keyword_ability_lines

if TYPE_CHECKING:
    from ..models.game import Game

_EACH_EXILES_UNTIL_TOTAL_RE = re.compile(
    r"^each (?P<who>opponent|player) exiles cards from the top of (?:their|his or her) library "
    r"until (?:they have|that player has|he or she has) exiled cards with total mana value "
    r"(?P<n>\d+) or greater(?: this way)?\.?$",
    re.IGNORECASE,
)
_CAST_EXILED_THIS_WAY_FREE_UNTIL_EOT_RE = re.compile(
    r"^until end of turn, you may cast (?:cards|spells from among cards) exiled this way "
    r"without paying their mana costs\.?$",
    re.IGNORECASE,
)
_MAY_CAST_IF_MANA_VALUE_RE = re.compile(
    r"^you may cast (?:that card|it) without paying its mana cost if (?:that|the) spell'?s "
    r"mana value is (?P<comparison>.+?)\.?$",
    re.IGNORECASE,
)
_OTHERWISE_TO_HAND_RE = re.compile(
    r"^(?:otherwise|if you don'?t(?: cast (?:that card|it) this way)?), put (?:it|that card) "
    r"into your hand\.?$",
    re.IGNORECASE,
)
_AT_MOST_N_RE = re.compile(r"^(?P<n>\d+) or less$", re.IGNORECASE)
_BOUND_BY_EXPRESSION_RE = re.compile(
    r"^less than (?P<or_equal>or equal to )?(?P<expr>.+)$", re.IGNORECASE
)


def _sentences(text: str) -> list[str]:
    """The instruction sentences, keyword-ability lines (Solstice
    Revelations' own "Flashback {6}{R} (...)") and reminder text dropped."""

    text = _strip_keyword_ability_lines(_INLINE_REMINDER_RE.sub("", text))
    return [s.strip() for s in re.split(r"(?<=\.)\s+", " ".join(text.split())) if s.strip()]


def _players_in_apnap_order(game: "Game") -> list[Player]:
    from .effects import _players_in_apnap_order as apnap

    return apnap(game)


def _source_name(stack_object: Any) -> str:
    return (
        stack_object.card.name if isinstance(stack_object, CardState) else stack_object.source_name
    )


def each_exiles_until_total(sentence: str) -> Callable[["Game", Any], list[CardState]] | None:
    """`_EACH_EXILES_UNTIL_TOTAL_RE`'s process, returning every card exiled."""
    from .keywords import exile_until

    match = _EACH_EXILES_UNTIL_TOTAL_RE.fullmatch(" ".join(sentence.split()))
    if match is None:
        return None
    threshold = int(match.group("n"))
    opponents_only = match.group("who").lower() == "opponent"

    def exile_each(game: "Game", stack_object: Any) -> list[CardState]:
        controller = game.controller_of(stack_object).username
        exiled: list[CardState] = []
        for player in _players_in_apnap_order(game):
            if opponents_only and player.username == controller:
                continue
            exiled.extend(
                exile_until(
                    game,
                    player,
                    lambda _, so_far: sum(card.card.cmc for card in so_far) >= threshold,
                    source_name=_source_name(stack_object),
                )
            )
        return exiled

    return exile_each


def _parse_exile_until_total_then_free_casts(text: str, *, for_spell: bool) -> Any:
    sentences = _sentences(text)
    if not sentences or len(sentences) > 2:
        return None
    exile_each = each_exiles_until_total(sentences[0])
    if exile_each is None:
        return None
    grants = False
    if len(sentences) == 2:
        if _CAST_EXILED_THIS_WAY_FREE_UNTIL_EOT_RE.fullmatch(sentences[1]) is None:
            return None
        grants = True

    def effect(game: "Game", stack_object: Any) -> None:
        from .casting import PlayAction

        exiled = exile_each(game, stack_object)
        if not grants:
            return
        controller = game.controller_of(stack_object).username
        for card in exiled:
            if card.card.is_land:
                continue
            game.grant_play_permission(
                card,
                controller,
                action=PlayAction.CAST,
                pays_mana_cost=False,
                source_name=_source_name(stack_object),
                rule="CR 601.3, CR 118.9",
                until_end_of_turn=True,
            )

    return effect


def _mana_value_bound(comparison: str) -> Callable[["Game", str], tuple[int, bool]] | None:
    """`(bound, inclusive)` for a printed comparison, read when the spell is
    offered (CR 608.2h)."""
    from .effects import count_expression

    comparison = comparison.strip()
    if match := _AT_MOST_N_RE.fullmatch(comparison):
        amount = int(match.group("n"))
        return lambda game, controller: (amount, True)
    if match := _BOUND_BY_EXPRESSION_RE.fullmatch(comparison):
        counter = count_expression(match.group("expr"))
        if counter is None:
            return None
        inclusive = match.group("or_equal") is not None
        return lambda game, controller: (counter(game, controller), inclusive)
    return None


def _parse_exile_until_then_cast_if_mana_value(text: str, *, for_spell: bool) -> Any:
    sentences = _sentences(text)
    if len(sentences) != 3:
        return None

    from .effects import _offer_free_casts_from_among, _parse_exile_until_antecedent

    antecedent = _parse_exile_until_antecedent(sentences[0])
    if antecedent is None:
        return None
    exile, exiles_many = antecedent
    if exiles_many:
        return None
    cast_match = _MAY_CAST_IF_MANA_VALUE_RE.fullmatch(sentences[1])
    if cast_match is None or _OTHERWISE_TO_HAND_RE.fullmatch(sentences[2]) is None:
        return None
    bound = _mana_value_bound(cast_match.group("comparison"))
    if bound is None:
        return None

    def effect(game: "Game", stack_object: Any) -> None:
        found = exile(game, stack_object)
        if not found:
            return
        card = found[0]
        controller = game.controller_of(stack_object).username
        limit, inclusive = bound(game, controller)
        mana_value = card.card.cmc
        fits = mana_value <= limit if inclusive else mana_value < limit
        if fits:
            _offer_free_casts_from_among(
                game,
                [card],
                controller,
                source_name=_source_name(stack_object),
                source_id=source_id_of(stack_object),
                play=False,
                limit=1,
            )
        if card in game.exile:
            game.return_to_hand(card)

    return effect


def exile_until_casts_whole_text(text: str, *, for_spell: bool) -> Any:
    """This module's whole-text readers, or None."""
    for reader in (
        _parse_exile_until_total_then_free_casts,
        _parse_exile_until_then_cast_if_mana_value,
    ):
        effect = reader(text, for_spell=for_spell)
        if effect is not None:
            return effect
    return None
