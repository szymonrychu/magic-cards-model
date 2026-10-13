"""EP-02 R2 T1: devotion, domain, party and color counts as the amount of an instruction.

The counts themselves are old (`amounts._devotion_count`, the domain and party
terms of `count_expression`, `vivid.count_colors_among`); what this module adds
is the sentence that spends them, read once, as the instruction is applied
(CR 608.2h), for every card that prints the template:

- `look_top_effect` - "(Look at | Reveal) the top <N|X> cards of your library[,
  where X is <expr>]. <what is kept and where the rest goes>[. <tail>]": the
  kept cards go "into your hand" or "on top of your library", the rest "into
  your graveyard" or "on the bottom of your library in a random order"
  (CR 701.20 look/reveal; Thassa's Oracle, Voda, Nael, Shadow Prophecy), or an
  opponent separates the revealed cards into two piles and the controller
  takes one (CR 700.3; Sphinx of Clear Skies). The tails are the life lost, the
  win ("If X is greater than or equal to the number of cards in your library,
  you win the game", CR 104.2b) and the extra draw ("Then if there are five
  basic land types among lands you control, draw a card").

Everything here is a pure reader over the engine's own bookkeeping; no new
persisted field.
"""

import functools
import re
from typing import TYPE_CHECKING, Any

from ..models.card_state import CardState
from ..models.zone import Zone
from ..numbers import COUNT, parse_count
from .amount_sentences import (
    Amount,
    apply_life,
    life_clause_amount,
    parse_life_clause,
    recipient_amount,
)
from .decisions import Decision, DecisionKind, source_id_of

if TYPE_CHECKING:
    from ..models.game import Game

_LOOK_RE = re.compile(
    rf"^(?P<verb>look at|reveal) the top (?P<n>x|{COUNT}) cards? of your library"
    r"(?:, where x is (?P<expr>[^.]+))?\.\s*(?P<rest>.+)$",
    re.IGNORECASE | re.DOTALL,
)
_REST = (
    r"(?P<rest>into your graveyard"
    r"|on the bottom of your library(?: in a random order)?"
    r"|on the bottom in a random order)"
)
#: "Put up to one of them on top of your library and the rest on the bottom ..."
_KEEP_UP_TO_RE = re.compile(
    rf"^put up to (?P<k>{COUNT}) of them (?P<kept>into your hand|on top of your library)"
    rf" and the rest {_REST}$",
    re.IGNORECASE,
)
#: "You may put one of those cards on top of your library. Put the rest on the bottom ..."
_MAY_TOP_RE = re.compile(
    r"^you may put one of (?:them|those cards) on top of your library\.\s*"
    r"put the rest on the bottom of your library in a random order$",
    re.IGNORECASE,
)
#: "An opponent separates those cards into two piles. Put one pile into your hand and
#: the other into your graveyard."
_PILES_RE = re.compile(
    r"^an opponent separates those cards into two piles\.\s*"
    r"put one pile into your hand and the other into your graveyard$",
    re.IGNORECASE,
)
_WIN_TAIL_RE = re.compile(
    r"^if x is greater than or equal to the number of cards in your library, "
    r"you win the game$",
    re.IGNORECASE,
)
_DRAW_TAIL_RE = re.compile(
    rf"^(?:then )?if there are (?P<n>{COUNT}) basic land types among lands you control, "
    r"draw a card$",
    re.IGNORECASE,
)
_SENTENCE_END_RE = re.compile(r"(?<=[.])\s+(?=[A-Z])")


@functools.cache
def look_top_effect(text: str) -> "Any | None":
    """The whole-text reader described in the module docstring, or `None`.
    Works for a spell (`(game, spell)`) and for an ability (`(game, ability)`)."""
    from .effects.text import _strip_non_effect_preamble

    lowered = text.lower()
    if "the top " not in lowered or " of your library" not in lowered:
        return None
    whole = " ".join(_strip_non_effect_preamble(text).split())
    head = _LOOK_RE.match(whole)
    if head is None:
        return None
    reveal = head.group("verb").lower() == "reveal"
    count_word = head.group("n").lower()
    expr = head.group("expr")
    if (count_word == "x") != (expr is not None):
        return None
    sentences = _SENTENCE_END_RE.split(head.group("rest").strip())
    first = sentences[0].rstrip(".")
    kept_kind = None
    k = 1
    consumed = 1
    if (match := _KEEP_UP_TO_RE.fullmatch(first)) is not None:
        kept_kind = "top" if "top" in match.group("kept") else "hand"
        rest_to = "graveyard" if "graveyard" in match.group("rest") else "bottom"
        parsed = parse_count(match.group("k"))
        if parsed is None:
            return None
        k = parsed
    elif len(sentences) >= 2 and (
        _MAY_TOP_RE.fullmatch(f"{sentences[0].rstrip('.')}. {sentences[1].rstrip('.')}")
    ):
        kept_kind, rest_to, k, consumed = "top", "bottom", 1, 2
    elif len(sentences) >= 2 and _PILES_RE.fullmatch(
        f"{sentences[0].rstrip('.')}. {sentences[1].rstrip('.')}"
    ):
        kept_kind, rest_to, consumed = "piles", "graveyard", 2
    else:
        return None
    tails = [sentence.rstrip(".") for sentence in sentences[consumed:]]
    life_tails, win, draw_at = [], False, None
    for tail in tails:
        if _WIN_TAIL_RE.fullmatch(tail) and expr is not None:
            win = True
        elif (draw := _DRAW_TAIL_RE.fullmatch(tail)) is not None:
            draw_at = parse_count(draw.group("n"))
            if draw_at is None:
                return None
        elif (clause := parse_life_clause(tail)) is not None and clause.who == "you":
            amount = life_clause_amount(clause, spell_x=False)
            if amount is None:
                return None
            life_tails.append((clause, amount))
        else:
            return None
    if count_word == "x":
        depth: Amount | None = recipient_amount(expr or "")
    else:
        fixed = parse_count(count_word)
        depth = None if fixed is None else (lambda _g, _o, _who, _n=fixed: _n)
    if depth is None:
        return None
    return _build(reveal, depth, kept_kind, k, rest_to, win, draw_at, tuple(life_tails))


def _build(reveal, depth, kept_kind, k, rest_to, win, draw_at, life_tails):  # noqa: ANN001, ANN202
    def effect(game: "Game", stack_object: Any) -> None:
        from .effects.library import _bottom_in_random_order

        controller = game.controller_of(stack_object)
        name = getattr(stack_object, "source_name", None) or getattr(stack_object, "name", "")
        x = max(depth(game, stack_object, controller), 0)
        looked = list(controller.library[:x])
        for state in looked:
            if reveal:
                game.reveal(state, source=name)
            else:
                game.look(state, controller.username, source=name)
        kept: list[CardState] = []
        if looked and kept_kind == "piles":
            opponents = [p for p in game.players_in_game if p.username != controller.username]
            divider = opponents[0] if opponents else controller
            pile_ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=divider.username,
                    prompt="separate the revealed cards into pile one",
                    source=name,
                    source_id=source_id_of(stack_object),
                    amount=len(looked),
                    exact=False,
                    cards=tuple(state.id for state in looked),
                )
            )
            one = [state for state in looked if state.id in set(pile_ids)]
            two = [state for state in looked if state.id not in set(pile_ids)]
            takes_one = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_PILE,
                    player=controller.username,
                    prompt="choose a pile to put into your hand",
                    source=name,
                    source_id=source_id_of(stack_object),
                    cards=tuple(state.id for state in one),
                )
            )
            kept = one if takes_one else two
            rest = two if takes_one else one
        elif looked:
            chosen_ids = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=controller.username,
                    prompt=f"choose up to {k} of the cards to keep",
                    source=name,
                    source_id=source_id_of(stack_object),
                    amount=k,
                    exact=False,
                    cards=tuple(state.id for state in looked),
                )
            )
            by_id = {state.id: state for state in looked}
            kept = [by_id[i] for i in chosen_ids if i in by_id][:k]
            rest = [state for state in looked if state not in kept]
        else:
            rest = []
        if kept_kind == "top":
            game.put_cards_into_library(kept, to_bottom=False)
        else:
            for state in kept:
                controller.move(state, Zone.HAND)
        if rest_to == "graveyard":
            for state in rest:
                controller.move(state, Zone.GRAVEYARD)
        else:
            _bottom_in_random_order(game, controller, rest)
        for clause, amount in life_tails:
            apply_life(game, stack_object, clause.who, clause.gains, amount)
        if draw_at is not None and (
            _domain(game, controller.username) >= draw_at
        ):
            game.draw_cards(controller.username, 1)
        if win and x >= len(controller.library):
            game.player_wins_the_game(controller.username)

    return effect


_EACH_CREATURE_GETS_RE = re.compile(r"^each creature gets\b", re.IGNORECASE)
_TARGETS_EACH_RE = re.compile(r"\b(target creatures) each (gain|get)\b", re.IGNORECASE)
_UP_TO_X_TARGET_RE = re.compile(r"^up to x target\b", re.IGNORECASE)


def where_x_pump_text_normalised(text: str) -> str:
    """The sentence with the two wordings the layer reader does not know spelled the
    ones it does: "Each creature gets -X/-X ..." (Drag to the Bottom) is its "All
    creatures get ..." and "up to X target creatures each gain ..." (Mogis's
    Marauder) its "... target creatures gain ..." - the same group, the same effect."""
    lowered = text.lower()
    if lowered.startswith("each creature gets"):
        text = _EACH_CREATURE_GETS_RE.sub("All creatures get", text)
    if " each g" in lowered:
        text = _TARGETS_EACH_RE.sub(r"\1 \2", text)
    return text


def up_to_x_targets(sentence: str) -> bool:
    """Whether the sentence opens "Up to X target ...": the X the text defines is
    also the most targets it may have (CR 601.2c with CR 107.3f)."""
    return _UP_TO_X_TARGET_RE.match(sentence.strip()) is not None


def _domain(game: "Game", controller: str) -> int:
    """CR 305.6's basic land types among the lands `controller` controls."""
    from .effects.amounts import count_expression

    reader = count_expression("the number of basic land types among lands you control")
    return 0 if reader is None else reader(game, controller)


__all__ = ["look_top_effect", "up_to_x_targets", "where_x_pump_text_normalised"]
