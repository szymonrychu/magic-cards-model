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

from ..models.card import Type
from ..models.card_state import CardState
from ..models.zone import Zone
from ..numbers import COUNT, parse_count
from .amount_sentences import (
    Amount,
    apply_life,
    clean,
    life_clause_amount,
    parse_life_clause,
    parse_put_counters,
    recipient_amount,
    recipient_for_each,
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
_LOOK_OPENING_RE = re.compile(r"^(?:look at|reveal) the top\b", re.IGNORECASE)
_SENTENCE_END_RE = re.compile(r"(?<=[.])\s+(?=[A-Z])")


@functools.cache
def look_top_effect(text: str, *, for_spell: bool = False) -> "Any | None":
    """The whole-text reader described in the module docstring, or `None`.
    Works for a spell (`(game, spell)`) and for an ability (`(game, ability)`).
    Sentences before the look or reveal are an ordinary instruction run first
    ("Search your library for up to two land cards ..., then shuffle." - Slimefoot's
    Survey)."""
    from .effects.dispatch import parse_mixed_effect, parse_mixed_effect_for_spell
    from .effects.text import _strip_non_effect_preamble

    lowered = text.lower()
    if "the top " not in lowered or " of your library" not in lowered:
        return None
    whole = " ".join(_strip_non_effect_preamble(text).split())
    opening = _SENTENCE_END_RE.split(whole)
    at = next((i for i, part in enumerate(opening) if _LOOK_OPENING_RE.match(part)), None)
    if at is None:
        return None
    lead = " ".join(opening[:at])
    head = _LOOK_RE.match(" ".join(opening[at:]))
    if head is None:
        return None
    lead_effect = None
    if lead:
        lead_effect = (parse_mixed_effect_for_spell if for_spell else parse_mixed_effect)(lead)
        if lead_effect is None:
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
    look = _build(reveal, depth, kept_kind, k, rest_to, win, draw_at, tuple(life_tails))
    if lead_effect is None:
        return look

    def lead_then_look(game: "Game", stack_object: Any) -> None:
        lead_effect(game, stack_object)
        look(game, stack_object)

    return lead_then_look


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
        if draw_at is not None and (_domain(game, controller.username) >= draw_at):
            game.draw_cards(controller.username, 1)
        if win and x >= len(controller.library):
            game.player_wins_the_game(controller.username)

    return effect


# --------------------------------------------------------------------------
# Counters sized by a count: "Put a +1/+1 counter on it for each creature in your
# party" (Emeria Captain), "Choose target creature you control. Put a +1/+1 counter
# on it for each creature in your party." (Strength of Solidarity), "Put a +1/+1
# counter on each creature you control with toughness less than the number of basic
# land types among lands you control." (Zar Ojanen)
# --------------------------------------------------------------------------

#: The one reader of a leading "Choose target X." sentence; `rest` is the effect body that
#: follows it, absent when the sentence stands alone. `ep02_r2_card_mana_value` reuses it.
CHOOSE_TARGET_RE = re.compile(
    r"^choose (?P<target>any target|target [^.]+?)(?:\.\s+(?P<rest>.+)|\.?)$", re.IGNORECASE
)
_EACH_WITH_STAT_RE = re.compile(
    rf"^put (?P<n>{COUNT}) (?P<kind>\+1/\+1|-1/-1|[a-z]+) counters? on each "
    r"(?P<group>creature you control) with (?P<stat>power|toughness) "
    r"(?P<cmp>less than or equal to|less than|greater than or equal to|greater than) "
    r"(?P<expr>.+)$",
    re.IGNORECASE,
)
_COMPARE = {
    "less than": lambda stat, bound: stat < bound,
    "less than or equal to": lambda stat, bound: stat <= bound,
    "greater than": lambda stat, bound: stat > bound,
    "greater than or equal to": lambda stat, bound: stat >= bound,
}


def _it_subject(game: "Game", stack_object: Any, chosen: bool) -> CardState | None:
    """What "it" names: the target a "Choose target ..." lead-in picked, else the object the
    trigger's event is about, else the ability's own source (CR 608.2c)."""
    if chosen:
        targets = [t for t in game.resolve_card_targets(stack_object) if isinstance(t, CardState)]
        return targets[0] if targets else None
    event = getattr(stack_object, "event", None)
    if event is not None and event.subject_id is not None:
        return game.find_by_id(event.subject_id)
    return stack_object.source(game) if hasattr(stack_object, "source") else stack_object


@functools.cache
def counters_amount_effect(text: str) -> "Any | None":
    """The two counter readers described above, or `None`."""
    from .effects.counters import _counter_kind
    from .effects.text import _strip_non_effect_preamble

    lowered = text.lower()
    if "counter" not in lowered or not ("for each " in lowered or " with " in lowered):
        return None
    whole = " ".join(_strip_non_effect_preamble(text).split())
    chosen = CHOOSE_TARGET_RE.match(whole)
    if chosen is not None and not chosen.group("rest"):
        return None
    body = chosen.group("rest") if chosen is not None else whole
    each_with = _EACH_WITH_STAT_RE.match(clean(body))
    if each_with is not None and chosen is None:
        unit = parse_count(each_with.group("n"))
        bound_of = recipient_amount(each_with.group("expr"))
        if unit is None or bound_of is None:
            return None
        kind = _counter_kind(each_with.group("kind"))
        compare = _COMPARE[each_with.group("cmp").lower()]
        stat = each_with.group("stat").lower()

        def each_effect(game: "Game", stack_object: Any) -> None:
            controller = game.controller_of(stack_object)
            bound = bound_of(game, stack_object, controller)
            for permanent in list(game.battlefield):
                chars = game.computed_board().of(permanent)
                if chars.controller != controller.username or Type.CREATURE not in chars.types:
                    continue
                value = (
                    game.power_of(permanent) if stat == "power" else game.toughness_of(permanent)
                )
                if value is not None and compare(value, bound):
                    game.add_counters(permanent, kind, unit)

        return each_effect
    put = parse_put_counters(body)
    if put is None or put.x or put.each is None or not (put.on.lower() == "it" or put.on_self):
        return None
    colors = colors_of_reference(put.each)
    per = recipient_for_each(put.each)
    if (per is None and colors is None) or (put.on_self and colors is None):
        return None  # a plain count on the source is `self_counters_for_each_effect`'s
    unit, kind = put.n, _counter_kind(put.kind)
    lead_in = chosen is not None
    on_self = put.on_self

    def it_effect(game: "Game", stack_object: Any) -> None:
        if colors is not None:
            amount = unit * colors(game, stack_object)
        else:
            amount = unit * per(game, stack_object, game.controller_of(stack_object))
        subject = stack_object.source(game) if on_self else _it_subject(game, stack_object, lead_in)
        if subject is not None and subject.zone is Zone.BATTLEFIELD and amount > 0:
            game.add_counters(subject, kind, amount)

    return it_effect


# --------------------------------------------------------------------------
# "Choose target creature card in your graveyard. Return that card to the battlefield
# if its mana value is less than or equal to <amount>. Otherwise, put it into your hand."
# (Bortuk Bonerattle)
# --------------------------------------------------------------------------

_RETURN_IF_MV_RE = re.compile(
    r"^return that card to the battlefield if its mana value is "
    r"(?P<cmp>less than or equal to|less than|greater than or equal to|greater than) "
    r"(?P<expr>.+?)\.\s+otherwise, put it into your hand$",
    re.IGNORECASE,
)


@functools.cache
def return_if_mana_value_effect(text: str) -> "Any | None":
    """The two-sentence reader above, or `None`. The target is the lead-in's."""
    from .effects.text import _strip_non_effect_preamble

    if "if its mana value is" not in text.lower():
        return None
    whole = " ".join(_strip_non_effect_preamble(text).split())
    chosen = CHOOSE_TARGET_RE.match(whole)
    if chosen is None or not chosen.group("rest"):
        return None
    match = _RETURN_IF_MV_RE.fullmatch(clean(chosen.group("rest")))
    bound_of = recipient_amount(match.group("expr")) if match is not None else None
    if match is None or bound_of is None:
        return None
    compare = _COMPARE[match.group("cmp").lower()]

    def effect(game: "Game", stack_object: Any) -> None:
        targets = [t for t in game.resolve_card_targets(stack_object) if isinstance(t, CardState)]
        if not targets or targets[0].zone is not Zone.GRAVEYARD:
            return
        card = targets[0]
        controller = game.controller_of(stack_object)
        if compare(card.mana_value, bound_of(game, stack_object, controller)):
            game.put_onto_battlefield(card, controller.username)
        else:
            controller.move(card, Zone.HAND)

    return effect


# --------------------------------------------------------------------------
# Life per color of an object (CR 105.1): "You gain 1 life for each of its colors."
# after a destroy (Breathe Your Last), "you may gain 1 life for each of that spell's
# colors. Do this only once each turn." (Ancient Cornucopia)
# --------------------------------------------------------------------------

_LIFE_PER_COLOR_RE = re.compile(
    rf"^you (?P<may>may )?gain (?P<n>{COUNT}) life for each of (?P<ref>its|that spell's) colou?rs"
    r"(?P<once>\.\s+do this only once each turn)?$",
    re.IGNORECASE,
)


def colors_of(game: "Game", state: CardState | None) -> int:
    """How many colors the object has (CR 105.1); colorless is no color (CR 105.2c)."""
    from ..models.card import Color

    if state is None:
        return 0
    return len({c for c in game.characteristics_of(state).colors if c is not Color.COLORLESS})


_COLORS_OF_RE = re.compile(r"^(?:of )?(?P<ref>its|that spell's) colou?rs$", re.IGNORECASE)


@functools.cache
def colors_of_reference(each: str) -> "Any | None":
    """`(game, stack_object) -> int` for the counted phrase "each of its colors" (the
    first card target, Might of the Nephilim, Breathe Your Last) or "each of that spell's
    colors" (the spell a cast trigger is about, Ramos, Ancient Cornucopia), or `None`."""
    match = _COLORS_OF_RE.match(clean(each))
    if match is None:
        return None
    of_spell = match.group("ref").lower() != "its"

    def count(game: "Game", stack_object: Any) -> int:
        if of_spell:
            event = getattr(stack_object, "event", None)
            ref = game.find_by_id(event.subject_id) if event and event.subject_id else None
        else:
            targets = [
                t for t in game.resolve_card_targets(stack_object) if isinstance(t, CardState)
            ]
            ref = targets[0] if targets else None
        return colors_of(game, ref)

    return count


@functools.cache
def life_per_color_effect(text: str, *, for_spell: bool) -> "Any | None":
    """The reader above (a leading instruction, if any, is read by the ordinary dispatcher)."""
    from .effects.dispatch import parse_mixed_effect, parse_mixed_effect_for_spell
    from .effects.text import _strip_non_effect_preamble

    if "life for each of " not in text.lower():
        return None
    whole = " ".join(_strip_non_effect_preamble(text).split())
    split = re.split(r"(?<=\.)\s+(?=you (?:may )?gain )", whole, maxsplit=1, flags=re.IGNORECASE)
    lead, last = (split[0], split[1]) if len(split) == 2 else ("", whole)
    match = _LIFE_PER_COLOR_RE.fullmatch(last.strip().rstrip("."))
    unit = parse_count(match.group("n")) if match is not None else None
    if match is None or unit is None:
        return None
    lead_effect = None
    if lead:
        lead_effect = (parse_mixed_effect_for_spell if for_spell else parse_mixed_effect)(lead)
        if lead_effect is None:
            return None
    may = match.group("may") is not None
    once = match.group("once") is not None
    count_colors = colors_of_reference(match.group("ref") + " colors")
    assert count_colors is not None

    def effect(game: "Game", stack_object: Any) -> None:
        controller = game.controller_of(stack_object)
        colors = count_colors(
            game, stack_object
        )  # read before the lead instruction can change it (CR 608.2h)
        if lead_effect is not None:
            lead_effect(game, stack_object)
        if once:
            key = f"{stack_object.source_id}:do-this-only-once-each-turn"
            if game.once_per_turn_triggers.get(key):
                return
        name = getattr(stack_object, "source_name", None) or getattr(stack_object, "name", "")
        if may and not game.may(
            controller.username, "gain life", source=name, source_id=source_id_of(stack_object)
        ):
            return
        if once:
            game.once_per_turn_triggers[key] = 1
        if colors > 0:
            game.gain_life(controller, unit * colors)

    return effect


_DISCARD_HAND_DRAW_PER_COLOR_RE = re.compile(
    r"^you may discard your hand\.\s*if you do, draw a card for each (?P<each>of [^.]+)$",
    re.IGNORECASE,
)


@functools.cache
def discard_hand_draw_per_color_effect(text: str) -> "Any | None":
    """ "You may discard your hand. If you do, draw a card for each of that spell's colors."
    (Moonveil Regent): the colors are read first (CR 608.2h); the draw follows only if a hand
    was discarded (CR 701.9a)."""
    from .effects.text import _strip_non_effect_preamble

    if "discard your hand" not in text.lower():
        return None
    whole = " ".join(_strip_non_effect_preamble(text).split())
    match = _DISCARD_HAND_DRAW_PER_COLOR_RE.fullmatch(whole.rstrip("."))
    count_colors = colors_of_reference(match.group("each")) if match is not None else None
    if count_colors is None:
        return None

    def effect(game: "Game", stack_object: Any) -> None:
        controller = game.controller_of(stack_object)
        colors = count_colors(game, stack_object)
        name = getattr(stack_object, "source_name", "")
        if not game.may(
            controller.username,
            "discard your hand",
            source=name,
            source_id=source_id_of(stack_object),
        ):
            return
        hand = list(controller.hand)
        if hand and len(game.discard_cards(controller.username, hand, source=name)) and colors:
            game.draw_cards(controller.username, colors)

    return effect


_EACH_CREATURE_GETS_RE = re.compile(r"^each creature gets\b", re.IGNORECASE)
_TARGETS_EACH_RE = re.compile(r"\b(target creatures) each (gain|get)\b", re.IGNORECASE)
#: "Ally creatures you control get +X/+X ..., where X is the number of colors among those
#: creatures" (General Tazri): the group the colors are counted among is the group
#: the pump names.
_TYPED_GROUP_THOSE_RE = re.compile(
    r"^(?P<sub>[A-Z][a-z]+) creatures you control (?P<rest>(?:get|gain) [^,]*?),\s*where x is the "
    r"number of colou?rs among those creatures\.?$",
    re.IGNORECASE,
)
_UP_TO_X_TARGET_RE = re.compile(r"^up to x target\b", re.IGNORECASE)


def where_x_pump_text_normalised(text: str) -> str:
    """The sentence with the two wordings the layer reader does not know spelled the
    ones it does: "Each creature gets -X/-X ..." (Drag to the Bottom) is its "All
    creatures get ..." and "up to X target creatures each gain ..." (Mogis's
    Marauder) its "... target creatures gain ..." - the same group, the same effect."""
    lowered = text.lower()
    typed = _TYPED_GROUP_THOSE_RE.match(text) if "those creatures" in lowered else None
    if typed is not None:
        noun = typed.group("sub")
        plural = (
            noun[:-1] + "ies"
            if noun.endswith("y")
            else noun[:-1] + "ves"
            if noun.endswith("f")
            else noun + "s"
        )
        group = f"{plural} you control"
        subject = f"{group[0].upper()}{group[1:]}"
        text = f"{subject} {typed.group('rest')}, where X is the number of colors among {group}."
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


__all__ = [
    "counters_amount_effect",
    "discard_hand_draw_per_color_effect",
    "life_per_color_effect",
    "look_top_effect",
    "return_if_mana_value_effect",
    "up_to_x_targets",
    "where_x_pump_text_normalised",
]
