"""EP-02 R3 T4: library look / search / return with amount-bounded criteria.

One reader per question, shared by every sentence that asks it:

- `parse_mana_value_bound` - "mana value `<N>` or less", "mana value less than
  or equal to the number of `<things>` you control", "... to `<this>`'s power",
  "mana value X or less, where X is the number of creatures that convoked this
  creature": a ceiling on CR 202.3's mana value, taken once, as the instruction
  is applied (CR 608.2h).
- the *look plan* - "Look at / Reveal the top `<N>` cards of your library"
  (or "twice `<N>` cards from the top", the X already written in per
  CR 107.3a) followed by what is done with the cards (CR 701.20a, CR 701.20e):
  take any number / an exact number / a bounded creature or spell, into hand /
  onto the battlefield / cast without paying, the rest to the graveyard / the
  bottom in a random order / left in the library and shuffled, then the
  riders that read what was really taken ("You lose 3 life for each card you
  put into your hand this way", "When a creature is put onto the battlefield
  this way, it deals damage equal to its power to target creature an opponent
  controls" - a CR 603.12 reflexive trigger).

CR 608.2d: a card outside the description, or above the bound, is never
offered; nothing is asked when nothing qualifies. A short library is looked at
whole (CR 701.20a looks at the cards that are there).

Registered as one SPELL_TEXT and one ABILITY_TEXT rung behind a cheap lowercase
gate, with memoised parsers, to stay inside the classify budget.
"""

import functools
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ..models.card import Color, Type
from ..models.card_state import CardState
from ..models.player import Player
from ..models.zone import Zone
from ..numbers import COUNT, parse_count
from .amount_sentences import token_maker
from .chosen_type import shares_creature_type
from .converge import colors_of_mana_spent
from .decisions import Decision, DecisionKind, source_id_of
from .delayed import ReflexiveDamageEqualToSubjectPowerConsequence
from .effects._chains import ABILITY_TEXT, FORWARD, MIXED_CLAUSE, SPELL_TEXT
from .effects._common import _card_description_is_readable, _quality_matcher, _targets_understood
from .effects.amounts import count_expression
from .effects.dispatch import (
    _ability_effect_or_notice,
    _parse_mixed_clause,
    _spell_effect_or_notice,
)
from .effects.library import (
    _bottom_in_random_order,
    _put_rest_on_bottom,
    put_ability_targets_on_bottom_of_owners_library,
)
from .effects.search import _search_and_exile_matching_name, _single_names
from .return_transformed_attached import _back_face_enchant_refusal
from .targeting import profile_for_text
from .triggers import is_ability

if TYPE_CHECKING:
    from ..models.game import Game

Bound = Callable[["Game", Any, Player], int | None]

# --------------------------------------------------------------------------
# The mana value ceiling
# --------------------------------------------------------------------------

_SELF_POWER = r"(?:this creature|this permanent|~)'s power"
_FIXED_BOUND_RE = re.compile(r"^(?P<n>\d+) or less$", re.IGNORECASE)
_LTE_BOUND_RE = re.compile(r"^less than or equal to (?P<expr>.+)$", re.IGNORECASE)
_X_BOUND_RE = re.compile(r"^x or less$", re.IGNORECASE)
_THAT_SUBJECT_RE = re.compile(r"^that (?:aura|creature|permanent|card|spell)$", re.IGNORECASE)
_CONVERGE_RE = re.compile(
    r"^the number of colors of mana spent to cast (?:this spell|~)$", re.IGNORECASE
)
_CONVOKED_RE = re.compile(r"^the number of creatures that convoked (?:this creature|~)$")


@functools.cache
def parse_mana_value_bound(bound: str, where_x: str | None = None) -> Bound | None:
    """The ceiling `bound` names (the text after "with mana value"), as a
    function of the game, the resolving spell or ability and its controller.
    `None` result at resolution means the ceiling cannot be known, so nothing
    qualifies (CR 608.2d)."""
    text = bound.strip().rstrip(".")
    fixed = _FIXED_BOUND_RE.fullmatch(text)
    if fixed is not None and where_x is None:
        number = int(fixed.group("n"))
        return lambda _game, _obj, _controller: number
    if _X_BOUND_RE.fullmatch(text) is not None and where_x is not None:
        if _CONVOKED_RE.fullmatch(where_x.strip().rstrip(".").lower()) is None:
            return None

        def convoked(game: "Game", obj: Any, _controller: Player) -> int | None:
            # CR 702.51c: a creature tapped to pay for the spell with convoke
            # "convoked" it; the count was settled when the cost was paid.
            source = obj.source(game) if is_ability(obj) else obj
            record = game.cast_record_of(source) if source is not None else None
            return 0 if record is None else record.convoked

        return convoked
    lte = _LTE_BOUND_RE.fullmatch(text)
    if lte is None or where_x is not None:
        return None
    expr = lte.group("expr").strip()
    if re.fullmatch(_SELF_POWER, expr, re.IGNORECASE):

        def power(game: "Game", obj: Any, _controller: Player) -> int | None:
            source = obj.source(game) if is_ability(obj) else obj
            return None if source is None else game.power_of(source)

        return power
    subject = _THAT_SUBJECT_RE.fullmatch(expr)
    if subject is not None:

        def referenced(game: "Game", obj: Any, _controller: Player) -> int | None:
            # "that Aura" / "that creature": the object the trigger event names,
            # its mana value as it is now (CR 202.3, CR 608.2h).
            event = getattr(obj, "event", None)
            if event is None or event.subject_id is None:
                return None
            state = game.find_by_id(event.subject_id)
            return None if state is None else int(state.mana_value)

        return referenced
    if _CONVERGE_RE.fullmatch(expr):

        def converge(game: "Game", obj: Any, _controller: Player) -> int | None:
            # Converge: the colors of mana spent to cast this spell (CR 105.1).
            return colors_of_mana_spent(game, obj)

        return converge
    counted = count_expression(expr)
    if counted is None:
        return None
    return lambda game, _obj, controller: counted(game, controller.username)


# --------------------------------------------------------------------------
# The look plan
# --------------------------------------------------------------------------

_LOOK_RE = re.compile(
    rf"^(?P<verb>look at|reveal) (?:the top (?P<n>{COUNT}) cards?|twice (?P<twice>{COUNT}) "
    r"cards from the top) of your library\.?$",
    re.IGNORECASE,
)
_HAND_SPLIT_RE = re.compile(
    rf"^(?:you may put (?P<any>any number) of them|"
    rf"put (?:(?P<upto>up to {COUNT})|(?P<n>{COUNT}|an?)) "
    r"(?:(?P<desc>[a-z ,/-]+?) )?cards? from among them) into your hand and the rest into "
    r"your graveyard\.?$",
    re.IGNORECASE,
)
_LOSE_PER_RE = re.compile(
    rf"^you lose (?P<n>{COUNT}) life for each card you put into your hand this way\.?$",
    re.IGNORECASE,
)
_LOSE_RE = re.compile(rf"^you lose (?P<n>{COUNT}) life\.?$", re.IGNORECASE)
_REVEAL_HAND_RE = re.compile(
    rf"^you may reveal (?:up to (?P<upto>{COUNT})|(?P<one>an?)) (?P<desc>[a-z ,/-]+?) cards? "
    r"with mana value (?P<bound>[^,]+?) from among them(?:, where x is (?P<wx>.+))?\.?$",
    re.IGNORECASE,
)
_REVEALED_TO_HAND_RE = re.compile(
    r"^put the revealed cards into your hand, then shuffle\.?$", re.IGNORECASE
)
_PUT_BF_RE = re.compile(
    r"^you may (?:reveal an? (?P<rdesc>[a-z ,/-]+?) card(?: with mana value (?P<bound>.+?))? "
    r"from among them and put it|put an? (?P<pdesc>[a-z ,/-]+?) card from among them) "
    r"onto the battlefield\.?$",
    re.IGNORECASE,
)
_REST_BOTTOM_RE = re.compile(
    r"^put the rest on the bottom(?: of your library)? in a random order\.?$", re.IGNORECASE
)
_CAST_FREE_RE = re.compile(
    r"^you may cast an? (?P<desc>[a-z ,/-]+?) spell with mana value (?P<bound>.+?) from among "
    r"them without paying its mana cost\.?$",
    re.IGNORECASE,
)
_REFLEXIVE_RE = re.compile(
    r"^when an? (?P<q>[a-z]+) is put onto the battlefield this way, it deals damage equal to "
    r"its power to (?P<target>target [a-z ]+)\.?$",
    re.IGNORECASE,
)
_PAIR_CHOOSE_RE = re.compile(
    r"^for each color pair, choose a card that's exactly those colors from among them\.?$",
    re.IGNORECASE,
)
_PAIR_TAKE_RE = re.compile(
    r"^put the chosen cards into your hand and the rest on the bottom of your library in a "
    r"random order\.?$",
    re.IGNORECASE,
)

_COLORS = (Color.WHITE, Color.BLUE, Color.BLACK, Color.RED, Color.GREEN)


@dataclass(frozen=True)
class _Plan:
    kind: str  # hand_split | reveal_hand | put_battlefield | cast_free | color_pairs
    count: int
    twice: bool
    reveal_top: bool
    quantity: int | None = None  # None = any number
    exact: bool = False
    matcher: Callable[[CardState], bool] | None = None
    description: str = "card"
    bound: Bound | None = None
    life_per_card: int = 0
    life_flat: int = 0
    reflexive_target: str | None = None


def _sentences(text: str) -> list[str]:
    return [part for part in re.split(r"(?<=\.)\s+", " ".join(text.strip().split())) if part]


def _description(desc: str | None) -> tuple[Callable[[CardState], bool], str] | None:
    """The card matcher for a `<desc>` card / spell, `None` when unreadable."""
    if desc is None or not desc.strip():
        return (lambda _state: True), "card"
    cleaned = re.sub(r",\s+or\s+", ", ", desc.strip(), flags=re.IGNORECASE)
    cleaned = cleaned.replace(" and/or ", " or ")
    if not _card_description_is_readable(cleaned):
        return None
    return _quality_matcher(cleaned), cleaned


def _quantity(match: re.Match[str]) -> tuple[int | None, bool] | None:
    groups = match.groupdict()
    if groups.get("any"):
        return None, False
    if groups.get("upto"):
        number = parse_count(groups["upto"].lower().removeprefix("up to ").strip())
        return (None, False) if number is None else (number, False)
    word = groups.get("n") or groups.get("one") or ""
    if word.lower() in {"a", "an"}:
        return 1, True
    number = parse_count(word)
    return (None, False) if number is None else (number, True)


@functools.lru_cache(maxsize=2048)
def _plan(text: str) -> _Plan | None:
    parts = _sentences(text)
    if len(parts) < 2:
        return None
    look = _LOOK_RE.fullmatch(parts[0])
    if look is None:
        return None
    twice = look.group("twice") is not None
    count = parse_count(look.group("twice") or look.group("n"))
    if count is None:
        return None
    base: dict[str, Any] = {
        "count": count,
        "twice": twice,
        "reveal_top": look.group("verb").lower() == "reveal",
    }
    rest = parts[1:]
    head = rest[0]

    hand = _HAND_SPLIT_RE.fullmatch(head)
    if hand is not None:
        described = _description(hand.group("desc"))
        quantity = _quantity(hand)
        if described is None or quantity is None:
            return None
        amount, exact = quantity
        if hand.group("any") or hand.group("upto"):
            exact = False
        plan = _Plan(
            "hand_split",
            quantity=amount,
            exact=exact,
            matcher=described[0],
            description=described[1],
            **base,
        )
        return _with_life(plan, rest[1:])

    reveal = _REVEAL_HAND_RE.fullmatch(head)
    if reveal is not None and len(rest) == 2 and _REVEALED_TO_HAND_RE.fullmatch(rest[1]):
        described = _description(reveal.group("desc"))
        bound = parse_mana_value_bound(reveal.group("bound"), reveal.group("wx"))
        if described is None or bound is None:
            return None
        number = 1 if reveal.group("one") else parse_count(reveal.group("upto"))
        if number is None:
            return None
        return _Plan(
            "reveal_hand",
            quantity=number,
            matcher=described[0],
            description=described[1],
            bound=bound,
            **base,
        )

    put = _PUT_BF_RE.fullmatch(head)
    if put is not None and len(rest) >= 2 and _REST_BOTTOM_RE.fullmatch(rest[1]):
        described = _description(put.group("rdesc") or put.group("pdesc"))
        bound = None
        if put.group("bound") is not None:
            bound = parse_mana_value_bound(put.group("bound"))
            if bound is None:
                return None
        if described is None:
            return None
        target = None
        if len(rest) == 3:
            reflexive = _REFLEXIVE_RE.fullmatch(rest[2])
            if reflexive is None or reflexive.group("q").lower() not in described[1].lower():
                return None
            target = reflexive.group("target")
        elif len(rest) != 2:
            return None
        return _Plan(
            "put_battlefield",
            quantity=1,
            matcher=described[0],
            description=described[1],
            bound=bound,
            reflexive_target=target,
            **base,
        )

    cast = _CAST_FREE_RE.fullmatch(head)
    if cast is not None and len(rest) == 2 and _REST_BOTTOM_RE.fullmatch(rest[1]):
        described = _description(cast.group("desc"))
        bound = parse_mana_value_bound(cast.group("bound"))
        if described is None or bound is None:
            return None
        return _Plan(
            "cast_free",
            quantity=1,
            matcher=described[0],
            description=described[1],
            bound=bound,
            **base,
        )

    if (
        _PAIR_CHOOSE_RE.fullmatch(head)
        and len(rest) == 2
        and _PAIR_TAKE_RE.fullmatch(rest[1])
        and base["reveal_top"]
    ):
        return _Plan("color_pairs", **base)
    return None


def _with_life(plan: _Plan, tail: list[str]) -> _Plan | None:
    if not tail:
        return plan
    if len(tail) != 1:
        return None
    per_card = _LOSE_PER_RE.fullmatch(tail[0])
    if per_card is not None:
        number = parse_count(per_card.group("n"))
        return None if number is None else _replace(plan, life_per_card=number)
    flat = _LOSE_RE.fullmatch(tail[0])
    if flat is not None:
        number = parse_count(flat.group("n"))
        return None if number is None else _replace(plan, life_flat=number)
    return None


def _replace(plan: _Plan, **changes: Any) -> _Plan:
    fields = {name: getattr(plan, name) for name in plan.__dataclass_fields__}
    fields.update(changes)
    return _Plan(**fields)


def _to_graveyard(game: "Game", player: Player, states: list[CardState]) -> None:
    for state in states:
        player.add(state, Zone.GRAVEYARD)
        game._record_graveyard_arrival(  # noqa: SLF001
            state, origin_zone=Zone.LIBRARY, permanent_types=None
        )


def _color_pair_key(state: CardState) -> frozenset[Color]:
    return frozenset(state.card.colors or ())


def _run(plan: _Plan, game: "Game", obj: Any, *, for_spell: bool) -> None:
    controller = game.controller_of(obj)
    source = obj.name if for_spell else obj.source_name
    source_id = source_id_of(obj)
    count = plan.count * (2 if plan.twice else 1)
    ceiling = None if plan.bound is None else plan.bound(game, obj, controller)
    bounded_out = plan.bound is not None and ceiling is None

    def admits(state: CardState) -> bool:
        if bounded_out or plan.matcher is None:
            return False
        if ceiling is not None and state.mana_value > ceiling:
            return False
        return plan.matcher(state)

    if plan.kind == "cast_free":
        _cast_free(plan, game, controller, source, source_id, count, admits)
        return
    if plan.kind == "color_pairs":
        _color_pairs(game, controller, source, source_id, count)
        return

    label, kept = {
        "hand_split": ("your hand", "your graveyard"),
        "reveal_hand": ("your hand", "your library"),
        "put_battlefield": ("the battlefield", "the bottom of your library"),
    }[plan.kind]
    candidates = (lambda _state: True) if plan.kind == "hand_split" and plan.bound is None else None
    if plan.kind == "hand_split" and plan.matcher is not None:
        candidates = plan.matcher
    elif plan.kind != "hand_split":
        candidates = admits
    moved, rest = game.look_at_top_and_split(
        controller,
        count,
        source=source,
        source_id=source_id,
        prompt=f"choose among the top {count} card(s)",
        moved_label=label,
        kept_label=kept,
        rest_in_random_order=plan.kind in {"put_battlefield", "reveal_hand"},
        moved_amount=plan.quantity,
        moved_exact=plan.exact,
        moved_candidates=candidates,
    )
    if plan.kind == "hand_split":
        for state in moved:
            controller.add(state, Zone.HAND)
        _to_graveyard(game, controller, rest)
        lost = plan.life_flat + plan.life_per_card * len(moved)
        if lost:
            game.lose_life(controller, lost)
        return
    if plan.kind == "reveal_hand":
        for state in moved:
            game.reveal(state, source=source)
            controller.add(state, Zone.HAND)
        _return_to_library_and_shuffle(game, controller, rest)
        return
    with game.entering_together():  # CR 603.6a: one instruction, one event
        for state in moved:
            game.put_onto_battlefield(state, controller.username)
    _put_rest_on_bottom(game, controller, rest, randomised=True, source=source, source_id=source_id)
    if plan.reflexive_target is not None:
        for state in moved:
            game.create_reflexive_trigger(
                text=(
                    "When you do, that creature deals damage equal to its power to "
                    f"{plan.reflexive_target}."
                ),
                controller=controller.username,
                source_id=source_id_of(obj),
                source_name=source,
                callback=ReflexiveDamageEqualToSubjectPowerConsequence(),
                subject_id=state.id,
            )


def _return_to_library_and_shuffle(game: "Game", controller: Player, rest: list[CardState]) -> None:
    """The unchosen looked-at cards go back and "then shuffle" (CR 701.24a)."""
    for state in rest:
        controller.library.append(state)
    if rest:
        controller.note_library_changed(placed=rest)
    game.shuffle_library(controller)


def _cast_free(
    plan: _Plan,
    game: "Game",
    controller: Player,
    source: str,
    source_id: str | None,
    count: int,
    admits: Callable[[CardState], bool],
) -> None:
    """Look at the top `count`, offer one spell that qualifies for a free cast
    (CR 118.9, CR 608.2g; CR 608.2d - only a spell that can really be cast is
    offered), then put the rest on the bottom in a random order."""
    looked_at = list(controller.library[: max(count, 0)])
    for state in looked_at:
        game.look(state, controller.username, source=source)
    legal = [
        state
        for state in looked_at
        if not state.card.is_land
        and admits(state)
        and game.can_cast_during_resolution(state, controller.username)
    ]
    chosen: CardState | None = None
    if legal and game.may(
        controller,
        f"cast {plan.description} spell from among the top {count} cards without paying its mana "
        "cost",
        source=source,
        source_id=source_id,
        cards=tuple(legal),
    ):
        answer = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=controller.username,
                prompt="choose a spell to cast without paying its mana cost",
                source=source,
                source_id=source_id,
                amount=1,
                cards=tuple(state.id for state in legal),
            )
        )
        assert isinstance(answer, tuple)
        if answer:
            chosen = next(state for state in legal if state.id == answer[0])
    if chosen is not None:
        game.cast_during_resolution(
            chosen, controller.username, source_name=source, rule="CR 608.2g"
        )
    _bottom_in_random_order(
        game, controller, [state for state in looked_at if chosen is None or state.id != chosen.id]
    )


def _color_pairs(
    game: "Game", controller: Player, source: str, source_id: str | None, count: int
) -> None:
    """Reveal the top `count`; for each of the ten color pairs choose a card
    that is exactly those two colors (CR 105.1: the five colors; a card of
    exactly two colors has exactly one pair). Chosen cards go to hand, the rest
    to the bottom in a random order."""
    revealed = list(controller.library[: max(count, 0)])
    for state in revealed:
        game.reveal(state, source=source)
    chosen: list[CardState] = []
    for index, first in enumerate(_COLORS):
        for second in _COLORS[index + 1 :]:
            pair = frozenset({first, second})
            options = [state for state in revealed if _color_pair_key(state) == pair]
            if not options:
                continue
            if len(options) == 1:
                chosen.append(options[0])
                continue
            answer = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=controller.username,
                    prompt=f"choose a {first.value}/{second.value} card from the revealed cards",
                    source=source,
                    source_id=source_id,
                    amount=1,
                    exact=True,
                    cards=tuple(state.id for state in options),
                )
            )
            assert isinstance(answer, tuple)
            chosen.append(next(state for state in options if state.id == answer[0]))
    for state in chosen:
        controller.add(state, Zone.HAND)
    _bottom_in_random_order(game, controller, [state for state in revealed if state not in chosen])


def _gate(text: str) -> bool:
    lowered = text.lower()
    return " of your library" in lowered and ("look at " in lowered or "reveal the top" in lowered)


def _effect(text: str, *, for_spell: bool) -> Any:
    if not _gate(text):
        return None
    plan = _plan(text)
    if plan is None:
        return None

    def effect(game: "Game", obj: Any) -> None:
        _run(plan, game, obj, for_spell=for_spell)

    return effect


@SPELL_TEXT.rung("s23", before=("parse_mixed_effect_for_spell",))
def _parse_look_plan_spell(text: str) -> Any:
    """A spell that looks at the top of the library and takes some of it."""
    return _effect(text, for_spell=True)


@ABILITY_TEXT.rung("s40", before=("parse_mixed_effect",))
def _parse_look_plan_ability(text: str) -> Any:
    """An ability that looks at the top of the library and takes some of it."""
    return _effect(text, for_spell=False)


# --------------------------------------------------------------------------
# Searching the library with an amount-bounded or relational criterion
# --------------------------------------------------------------------------
#
# "Search your library for `<criterion>`[, reveal it], put it into your hand /
# onto the battlefield[ tapped][ attached to this creature], then shuffle."
# The criterion is read by `_criteria` into a predicate built at resolution
# (CR 608.2h): a bound taken from the board, from the cast, from the trigger
# event's subject or from the sacrificed creature. CR 701.23b: a stated quality
# lets the searcher find fewer (or none), which `Game.search_library` honours.

_SEARCH_JOIN_RE = re.compile(r"\.\s+(put (?:those cards|that card|them|it)\b)", re.IGNORECASE)
_REMINDER_RE = re.compile(r"\s*\([^)]*\)")

_SEARCH_PUT_RE = re.compile(
    r"^(?P<may>you may )?search your library for (?P<crit>.+?)"
    r"(?P<reveal>, reveal (?:it|them|that card|those cards))?"
    r", put (?:it|them|that card|those cards) (?P<dest>into your hand|onto the battlefield)"
    r"(?P<tapped> tapped)?(?P<attached> attached to (?:this creature|this permanent|~))?"
    r", then shuffle(?P<tail>\.?(?: you gain 1 life for each \{s\} spent to cast this spell)?)\.?$",
    re.IGNORECASE,
)
_TOTAL_RE = re.compile(
    r"^any number of (?P<q>.+?) cards? with total mana value (?P<n>\d+) or less$", re.IGNORECASE
)
_UP_TO_RE = re.compile(
    rf"^up to (?P<n>x|{COUNT}) (?P<q>.+?) cards?(?:, where x is (?P<wx>.+))?$", re.IGNORECASE
)
_NAMED_PAIR_RE = re.compile(
    r"^a card named (?P<a>.+?) and/or a card named (?P<b>.+)$", re.IGNORECASE
)
_ALTERNATIVES_RE = re.compile(r"^an? .+? card(?:, an? .+? card)+,? or an? .+? card$", re.IGNORECASE)
_SINGLE_RE = re.compile(
    r"^an? (?:(?P<q>.+?) )?card"
    r"(?: with mana value (?P<bound>.+?))?"
    r"(?: and with a different name than each (?P<uniq>[a-z]+) you control)?"
    r"(?: with the same (?P<same>total power and toughness))?"
    r"(?P<shares> that shares a creature type with the sacrificed creature and has mana value "
    r"equal to 1 plus that creature's mana value)?$",
    re.IGNORECASE,
)

Predicate = Callable[[CardState], bool]
PredicateFactory = Callable[["Game", Any, Player], Predicate | None]


@dataclass(frozen=True)
class _Crit:
    make: PredicateFactory
    count: Callable[["Game", Any, Player], int]
    total: Callable[["Game", Any, Player], int] | None = None


def _quality(text: str | None) -> Predicate | None:
    """The card matcher for a `<quality>` card, `None` when unreadable; an
    absent quality is "a card" (anything)."""
    if text is None or not text.strip():
        return lambda _state: True
    cleaned = re.sub(r",\s+or\s+", ", ", text.strip(), flags=re.IGNORECASE)
    if not _card_description_is_readable(cleaned):
        return None
    return _quality_matcher(cleaned)


def _fixed(matcher: Predicate, count: int = 1) -> _Crit:
    return _Crit(lambda _g, _o, _c: matcher, lambda _g, _o, _c: count)


def _event_subject(game: "Game", obj: Any) -> CardState | None:
    event = getattr(obj, "event", None)
    if event is None or event.subject_id is None:
        return None
    return game.find_by_id(event.subject_id)


def _total_power_toughness(game: "Game", state: CardState) -> int | None:
    if state.zone is Zone.BATTLEFIELD:
        power, toughness = game.power_of(state), game.toughness_of(state)
    else:
        try:
            power, toughness = int(state.card.power or ""), int(state.card.toughness or "")
        except ValueError:
            return None
    return None if power is None or toughness is None else power + toughness


def _printed_total(state: CardState) -> int | None:
    try:
        return int(state.card.power or "") + int(state.card.toughness or "")
    except ValueError:
        return None


@functools.lru_cache(maxsize=2048)
def _criteria(text: str) -> _Crit | None:
    total = _TOTAL_RE.fullmatch(text)
    if total is not None:
        matcher = _quality(total.group("q"))
        if matcher is None:
            return None
        limit = int(total.group("n"))
        return _Crit(
            lambda _g, _o, _c: matcher,
            lambda _g, _o, controller: len(controller.library),
            lambda _g, _o, _c: limit,
        )
    up_to = _UP_TO_RE.fullmatch(text)
    if up_to is not None:
        matcher = _quality(up_to.group("q"))
        if matcher is None:
            return None
        word = up_to.group("n").lower()
        if word == "x":
            amount = _where_x_amount(up_to.group("wx"))
            if amount is None:
                return None
            return _Crit(lambda _g, _o, _c: matcher, amount)
        number = parse_count(word)
        return None if number is None else _fixed(matcher, number)
    named = _NAMED_PAIR_RE.fullmatch(text)
    if named is not None:
        names = {named.group("a").strip(), named.group("b").strip()}
        return _Crit(
            lambda _g, _o, _c: lambda state: state.name in names,
            lambda _g, _o, _c: len(names),
        )
    if _ALTERNATIVES_RE.fullmatch(text) is not None:
        matchers = [_quality(item) for item in re.findall(r"an? (.+?) card", text, re.IGNORECASE)]
        if not matchers or any(matcher is None for matcher in matchers):
            return None
        ready = [matcher for matcher in matchers if matcher is not None]
        return _fixed(lambda state: any(matcher(state) for matcher in ready))
    single = _SINGLE_RE.fullmatch(text)
    if single is None:
        return None
    base = _quality(single.group("q"))
    bound = None
    if single.group("bound") is not None:
        bound = parse_mana_value_bound(single.group("bound"))
        if bound is None:
            return None
    if base is None:
        return None
    uniq, same, shares = single.group("uniq"), single.group("same"), single.group("shares")
    if uniq is not None and not _card_description_is_readable(uniq):
        return None

    def make(game: "Game", obj: Any, controller: Player) -> Predicate | None:
        ceiling = None
        if bound is not None:
            ceiling = bound(game, obj, controller)
            if ceiling is None:
                return None
        taken: set[str] = set()
        if uniq is not None:
            kind = _quality_matcher(uniq)
            taken = {
                name
                for permanent in game.permanents_controlled_by(controller.username)
                if kind(permanent)
                for name in _single_names(permanent.name)
            }
        wanted_total = None
        if same is not None:
            subject = _event_subject(game, obj)
            wanted_total = None if subject is None else _total_power_toughness(game, subject)
            if wanted_total is None:
                return None
        sacrificed: CardState | None = None
        sacrificed_value = 0
        if shares is not None:
            ids = getattr(obj, "cost_sacrificed_card_ids", ())
            values = getattr(obj, "cost_sacrificed_mana_values", ())
            sacrificed = game.find_by_id(ids[0]) if ids else None
            if sacrificed is None or not values:
                return None
            sacrificed_value = int(values[0])

        def predicate(state: CardState) -> bool:
            if not base(state):
                return False
            if ceiling is not None and state.mana_value > ceiling:
                return False
            if taken and not taken.isdisjoint(_single_names(state.card.name)):
                return False
            if wanted_total is not None and _printed_total(state) != wanted_total:
                return False
            return sacrificed is None or (
                state.mana_value == sacrificed_value + 1
                and shares_creature_type(game, sacrificed, state)
            )

        return predicate

    return _Crit(make, lambda _g, _o, _c: 1)


def _where_x_amount(where_x: str | None) -> Callable[["Game", Any, Player], int] | None:
    if where_x is None:
        return None
    counted = count_expression(where_x.strip().rstrip(".").lower())
    if counted is None:
        return None
    return lambda game, _obj, controller: counted(game, controller.username)


@dataclass(frozen=True)
class _SearchPlan:
    optional: bool
    crit: _Crit
    prompt: str
    battlefield: bool
    tapped: bool
    attached: bool
    reveal: bool
    snow_life: bool


@functools.lru_cache(maxsize=2048)
def _search_plan(text: str) -> _SearchPlan | None:
    joined = _SEARCH_JOIN_RE.sub(r", \1", _REMINDER_RE.sub("", " ".join(text.strip().split())))
    match = _SEARCH_PUT_RE.fullmatch(joined)
    if match is None:
        return None
    crit = _criteria(match.group("crit").strip())
    if crit is None:
        return None
    battlefield = match.group("dest").lower() == "onto the battlefield"
    attached = match.group("attached") is not None
    if attached and not battlefield:
        return None
    return _SearchPlan(
        optional=match.group("may") is not None,
        crit=crit,
        prompt=f"search your library for {match.group('crit').strip()}",
        battlefield=battlefield,
        tapped=match.group("tapped") is not None,
        attached=attached,
        reveal=match.group("reveal") is not None,
        snow_life="{s}" in match.group("tail").lower(),
    )


def _snow_mana_spent(game: "Game", obj: Any) -> int:
    record = game.cast_record_of(obj)
    return 0 if record is None else sum(record.snow_mana_spent.values())


def _run_search(plan: _SearchPlan, game: "Game", obj: Any, *, for_spell: bool) -> None:
    controller = game.controller_of(obj)
    source = obj.name if for_spell else obj.source_name
    source_id = source_id_of(obj)
    if plan.optional and not game.may(controller, plan.prompt, source=source, source_id=source_id):
        return
    predicate = plan.crit.make(game, obj, controller)
    if predicate is None:
        game.shuffle_library(controller)  # nothing can qualify; the search still happens
        return
    host = None
    if plan.attached:
        host = obj.source(game) if is_ability(obj) else None
        if host is None:
            return
        base = predicate

        def predicate(state: CardState, _base=base, _host=host) -> bool:  # type: ignore[misc]
            # CR 303.4i: an Aura that cannot enchant the host stays in the library.
            return _base(state) and (
                _back_face_enchant_refusal(
                    game, state, _host, controller.username, transformed=False
                )
                is None
            )

    count = plan.crit.count(game, obj, controller)
    total = None if plan.crit.total is None else plan.crit.total(game, obj, controller)
    if plan.attached:
        found = game.search_library(
            controller,
            predicate,
            count=count,
            optional=True,
            shuffle=False,
            source=source,
            source_id=source_id,
            caused_by=controller.username,
        )
        with game.entering_together():
            for state in found:
                entered = game.put_onto_battlefield(state, controller.username, tapped=plan.tapped)
                if entered.zone is Zone.BATTLEFIELD and host is not None:
                    entered.attach_to(host)
        game.shuffle_library(controller)
    else:
        game.search_and_put(
            controller,
            predicate,
            destination=Zone.BATTLEFIELD if plan.battlefield else Zone.HAND,
            count=count,
            reveal=plan.reveal,
            tapped=plan.tapped,
            source=source,
            source_id=source_id,
            caused_by=controller.username,
            total_mana_value=total,
        )
    if plan.snow_life:
        game.gain_life(controller, _snow_mana_spent(game, obj))


# Bring to Light: converge - search, exile, then a free cast.
_CONVERGE_EXILE_RE = re.compile(
    r"^(?:converge\s+[-—]\s+)?search your library for (?P<crit>.+?), exile that card, then "
    r"shuffle\. you may cast that card without paying its mana cost\.?$",
    re.IGNORECASE,
)


@functools.lru_cache(maxsize=1024)
def _converge_plan(text: str) -> _Crit | None:
    match = _CONVERGE_EXILE_RE.fullmatch(" ".join(text.strip().split()))
    return None if match is None else _criteria(match.group("crit").strip())


def _run_search_exile_cast(crit: _Crit, game: "Game", obj: Any, *, for_spell: bool) -> None:
    controller = game.controller_of(obj)
    source = obj.name if for_spell else obj.source_name
    source_id = source_id_of(obj)
    predicate = crit.make(game, obj, controller)
    found = (
        []
        if predicate is None
        else game.search_library(
            controller,
            predicate,
            count=1,
            optional=True,
            source=source,
            source_id=source_id,
            caused_by=controller.username,
        )
    )
    game.exile_cards(found)
    for state in found:
        game.may_cast_during_resolution(
            state,
            controller.username,
            prompt=f"cast {state.name} without paying its mana cost",
            source=source,
            source_id=source_id,
            source_name=source,
            rule="CR 608.2g",
        )


# Hide // Seek's second half: search an opponent's library, exile, gain life.
_SEARCH_OPPONENT_EXILE_RE = re.compile(
    r"^search target opponent's library for a card and exile it\. you gain life equal to its "
    r"mana value\. then that player shuffles\.?$",
    re.IGNORECASE,
)


def _search_opponent_exile(text: str, *, for_spell: bool) -> Any:
    if _SEARCH_OPPONENT_EXILE_RE.fullmatch(" ".join(text.strip().split())) is None:
        return None
    if not _targets_understood("target opponent", allow_player_targets=True):
        return None

    def effect(game: "Game", obj: Any) -> None:
        controller = game.controller_of(obj)
        source = obj.name if for_spell else obj.source_name
        target = next(
            (t for t in game.resolve_targets(obj) if isinstance(t, Player)),
            None,
        )
        if target is None:
            return
        # CR 701.23d: a search for "a card" with no quality finds one if it can.
        found = game.search_library(
            target,
            lambda _state: True,
            count=1,
            optional=False,
            shuffle=False,
            searcher=controller.username,
            source=source,
            source_id=source_id_of(obj),
        )
        game.exile_cards(found)
        for state in found:
            game.gain_life(controller, int(state.mana_value))
        game.shuffle_library(target)

    return effect


# Necromentia / The End: a name chosen or taken from a permanent, exiled from
# the graveyard, hand and library of a player, then a payoff per card exiled
# from the hand.
_CHOOSE_NAME_EXILE_RE = re.compile(
    r"^choose a card name other than a basic land card name\. search target opponent's "
    r"graveyard, hand, and library for any number of cards with that name and exile them\. "
    r"that player shuffles, then creates (?P<token>an? .+? tokens?) for each card exiled from "
    r"their hand this way\.?$",
    re.IGNORECASE,
)
_EXILE_TARGET_THEN_NAME_RE = re.compile(
    r"^exile target (?P<what>[a-z ]+?)\. search its controller's graveyard, hand, and library "
    r"for any number of cards with the same name as that permanent and exile them\. that "
    r"player shuffles, then draws a card for each card exiled from their hand this way\.?$",
    re.IGNORECASE,
)


def _is_basic_land_name(name: str) -> bool:
    from ..data.printing_pool import resolve_printing
    from ..models.card import Supertype, Type

    printing = resolve_printing(name)
    return (
        printing is not None
        and Supertype.BASIC in set(printing.supertypes)
        and Type.LAND in set(printing.types)
    )


def _choose_name_exile(text: str, *, for_spell: bool) -> Any:
    match = _CHOOSE_NAME_EXILE_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    if not _targets_understood("target opponent", allow_player_targets=True):
        return None
    maker = token_maker(match.group("token"))
    if maker is None:
        return None

    def effect(game: "Game", obj: Any) -> None:
        controller = game.controller_of(obj)
        source = obj.name if for_spell else obj.source_name
        target = next((t for t in game.resolve_targets(obj) if isinstance(t, Player)), None)
        if target is None:
            return
        name = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_A_QUALITY,
                player=controller.username,
                prompt="choose a card name other than a basic land card name",
                source=source,
                source_id=source_id_of(obj),
                quality="card name",
            )
        )
        assert isinstance(name, str)
        if _is_basic_land_name(name):
            raise ValueError(f"{source}: {name!r} is a basic land card name (CR 201.4a)")
        _exiled, from_hand = _search_and_exile_matching_name(
            game,
            target,
            name,
            chooser=controller,
            cap=None,
            source=source,
            source_id=source_id_of(obj),
        )
        maker(game, target.username, from_hand)

    return effect


def _exile_then_name_exile(text: str, *, for_spell: bool) -> Any:
    match = _EXILE_TARGET_THEN_NAME_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    if not _targets_understood(f"target {match.group('what')}", battlefield_only=True):
        return None

    def effect(game: "Game", obj: Any) -> None:
        controller = game.controller_of(obj)
        source = obj.name if for_spell else obj.source_name
        target = next((t for t in game.resolve_targets(obj) if isinstance(t, CardState)), None)
        if target is None or target.zone is not Zone.BATTLEFIELD:
            return
        owner_name = game.controller_of(target).username
        name = target.name
        game.exile_permanent(target)
        owner = game.player(owner_name)
        _exiled, from_hand = _search_and_exile_matching_name(
            game,
            owner,
            name,
            chooser=controller,
            cap=None,
            source=source,
            source_id=source_id_of(obj),
        )
        if from_hand:
            game.draw_cards(owner.username, from_hand)

    return effect


# Doubling Chant / Clarion Ultimatum: for each of a group of permanents, find a
# card with the same name; all the finds enter together, then one shuffle.
_FOR_EACH_SAME_NAME_RE = re.compile(
    r"^for each (?P<what>creature|permanent) you control, you may search your library for "
    r"an? (?:(?P<q>creature) )?card with the same name as that (?P=what)\. put those cards "
    r"onto the battlefield(?P<tapped> tapped)?, then shuffle\.?$",
    re.IGNORECASE,
)
_CHOSEN_SAME_NAME_RE = re.compile(
    rf"^choose (?P<n>{COUNT}) permanents you control\. for each of those permanents, you may "
    r"search your library for a card with the same name as that permanent\. put those cards "
    r"onto the battlefield(?P<tapped> tapped)?, then shuffle\.?$",
    re.IGNORECASE,
)


def _same_name_group(text: str, *, for_spell: bool) -> Any:
    whole = " ".join(text.strip().split())
    each = _FOR_EACH_SAME_NAME_RE.fullmatch(whole)
    chosen = None if each is not None else _CHOSEN_SAME_NAME_RE.fullmatch(whole)
    if each is None and chosen is None:
        return None
    match = each or chosen
    assert match is not None
    tapped = match.group("tapped") is not None
    chosen_count = None if chosen is None else parse_count(chosen.group("n"))
    if chosen is not None and chosen_count is None:
        return None
    only_creatures = each is not None and each.group("what").lower() == "creature"

    def effect(game: "Game", obj: Any) -> None:
        controller = game.controller_of(obj)
        source = obj.name if for_spell else obj.source_name
        source_id = source_id_of(obj)
        group = [
            permanent
            for permanent in game.permanents_controlled_by(controller.username)
            if not only_creatures or Type.CREATURE in game.characteristics_of(permanent).types
        ]
        if chosen_count is not None and len(group) > chosen_count:
            answer = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=controller.username,
                    prompt=f"choose {chosen_count} permanents you control",
                    source=source,
                    source_id=source_id,
                    amount=chosen_count,
                    exact=True,
                    cards=tuple(permanent.id for permanent in group),
                )
            )
            assert isinstance(answer, tuple)
            group = [permanent for permanent in group if permanent.id in set(answer)]
        names = [permanent.name for permanent in group]
        entering: list[CardState] = []
        for name in names:
            single = _single_names(name)
            entering.extend(
                game.search_library(
                    controller,
                    lambda state, _single=single, _taken=entering: (
                        not _single.isdisjoint(_single_names(state.card.name))
                        and state not in _taken
                        and (not only_creatures or state.card.is_creature)
                    ),
                    count=1,
                    optional=True,
                    shuffle=False,
                    source=source,
                    source_id=source_id,
                    caused_by=controller.username,
                )
            )
        with game.entering_together():
            for state in entering:
                game.put_onto_battlefield(state, controller.username, tapped=tapped)
        game.shuffle_library(controller)

    return effect


def _search_effect(text: str, *, for_spell: bool) -> Any:
    lowered = text.lower()
    if "search " not in lowered:
        return None
    plan = _search_plan(text)
    if plan is not None:

        def effect(game: "Game", obj: Any) -> None:
            _run_search(plan, game, obj, for_spell=for_spell)

        return effect
    crit = _converge_plan(text)
    if crit is not None:

        def converge_effect(game: "Game", obj: Any) -> None:
            _run_search_exile_cast(crit, game, obj, for_spell=for_spell)

        return converge_effect
    for reader in (
        _search_opponent_exile,
        _choose_name_exile,
        _exile_then_name_exile,
        _same_name_group,
    ):
        found = reader(text, for_spell=for_spell)
        if found is not None:
            return found
    return None


@SPELL_TEXT.rung("s23", before=("parse_mixed_effect_for_spell",))
def _parse_search_spell(text: str) -> Any:
    """A spell that searches with an amount-bounded or relational criterion."""
    return _search_effect(text, for_spell=True)


@ABILITY_TEXT.rung("s40", before=("parse_mixed_effect",))
def _parse_search_ability(text: str) -> Any:
    """An ability that searches with an amount-bounded or relational criterion."""
    return _search_effect(text, for_spell=False)


# "put target <permanent> on the bottom of its owner's library" (Hide).
_PUT_BOTTOM_RE = re.compile(
    r"^put (?P<phrase>target [a-z, ]+?) on the bottom of its owner's library\.?$", re.IGNORECASE
)


@MIXED_CLAUSE.rung("s31", for_spell=FORWARD)
def _parse_put_permanent_on_bottom_clause(clause: str, *, for_spell: bool) -> Any:
    """CR 401.1: a permanent put on the bottom of its owner's library; the
    battlefield twin of the graveyard reader (CR 401.2 keeps the order)."""
    match = _PUT_BOTTOM_RE.fullmatch(clause.strip())
    if match is None:
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=True):
        return None
    return put_ability_targets_on_bottom_of_owners_library


# "deals twice N damage": X written in by CR 107.3a becomes a plain number.
_TWICE_DAMAGE_RE = re.compile(r"\btwice (\d+) damage\b", re.IGNORECASE)


@MIXED_CLAUSE.rung("s1", for_spell=FORWARD)
def _parse_twice_n_damage_clause(clause: str, *, for_spell: bool) -> Any:
    """ "`<source>` deals twice 3 damage to ..." is "deals 6 damage": the
    doubled number, read by the ordinary damage clause readers."""
    if "twice " not in clause.lower():
        return None
    rewritten = _TWICE_DAMAGE_RE.sub(lambda m: f"{2 * int(m.group(1))} damage", clause)
    if rewritten == clause:
        return None
    return _parse_mixed_clause(rewritten, for_spell=for_spell)


# "gets +X/+0 until end of turn, where X is the number of other attacking
# creatures" is the per-attacker pump the older reader already performs.
_WHERE_X_OTHER_ATTACKERS_RE = re.compile(
    r"^(?P<subject>it|this creature|~) gets (?P<p>\+x|\+0)/(?P<t>\+x|\+0) until end of turn, "
    r"where x is the number of other attacking creatures\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s40", before=("parse_mixed_effect",))
def _parse_pump_where_x_other_attackers(text: str) -> Any:
    match = _WHERE_X_OTHER_ATTACKERS_RE.fullmatch(" ".join(text.strip().split()))
    if match is None or (match.group("p") == "+0" and match.group("t") == "+0"):
        return None

    def per(value: str) -> str:
        return "+1" if value.lower() == "+x" else "+0"

    return _ability_effect_or_notice(
        f"{match.group('subject')} gets {per(match.group('p'))}/{per(match.group('t'))} "
        "until end of turn for each other attacking creature."
    )


# --------------------------------------------------------------------------
# Return a permanent and the Auras attached to it, and the "destroy X and you
# lose life equal to its toughness" single-sentence form.
# --------------------------------------------------------------------------

_RETURN_WITH_AURAS_RE = re.compile(
    r"^return (?P<phrase>(?:another )?target [a-z ]+?) and all auras(?P<mine> you control)? "
    r"attached to (?:it|that creature|that permanent) to (?:their|its) owners?'s? hands?\.?$",
    re.IGNORECASE,
)
_AND_LIFE_RE = re.compile(
    r"^(?P<lead>(?:destroy|exile) target [^.]+?) and (?P<who>you|its controller) "
    r"(?P<verb>lose|loses|gain|gains) life equal to "
    r"(?P<rest>its (?:power|toughness|mana value))\.?$",
    re.IGNORECASE,
)


def _return_with_auras(text: str) -> Any:
    """CR 608.2c: "Return target `<permanent>` and all Auras (you control)
    attached to it to their owner's hand" - the Auras are those attached as the
    instruction starts, all moved together with the permanent so
    none falls off first (CR 704.5m)."""
    match = _RETURN_WITH_AURAS_RE.fullmatch(" ".join(text.strip().split()))
    if match is None or not _targets_understood(match.group("phrase"), count_agnostic=True):
        return None
    mine_only = match.group("mine") is not None

    def effect(game: "Game", obj: Any) -> None:
        controller = game.controller_of(obj)
        moved: list[CardState] = []
        for target in game.resolve_targets(obj):
            if not isinstance(target, CardState) or target.zone is not Zone.BATTLEFIELD:
                continue
            moved.append(target)
            moved.extend(
                aura
                for aura in game.battlefield
                if aura.attached_to == target.id
                and "Aura" in game.characteristics_of(aura).subtypes
                and (not mine_only or game.controller_of(aura).username == controller.username)
            )
        for permanent in moved:
            game.return_to_hand(permanent)

    return effect


def _and_life_clause(text: str, *, for_spell: bool) -> Any:
    """ "Destroy target creature and you lose life equal to its toughness" is
    the two-sentence form (CR 608.2c: in order) the ordinary readers hold."""
    match = _AND_LIFE_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    who = match.group("who").capitalize()
    split = (
        f"{match.group('lead')}. {who} {match.group('verb')} life equal to {match.group('rest')}."
    )
    return (_spell_effect_or_notice if for_spell else _ability_effect_or_notice)(split)


def aura_return_effect(text: str, *, for_spell: bool) -> Any:
    """The readers of this section for a modal spell's mode text."""
    return _return_with_auras(text) or _and_life_clause(text, for_spell=for_spell)


@SPELL_TEXT.rung("s23", before=("parse_mixed_effect_for_spell",))
def _parse_aura_return_spell(text: str) -> Any:
    lowered = text.lower()
    if " and all auras" not in lowered and " life equal to " not in lowered:
        return None
    return aura_return_effect(text, for_spell=True)


@ABILITY_TEXT.rung("s40", before=("parse_mixed_effect",))
def _parse_aura_return_ability(text: str) -> Any:
    lowered = text.lower()
    if " and all auras" not in lowered and " life equal to " not in lowered:
        return None
    return aura_return_effect(text, for_spell=False)


# --------------------------------------------------------------------------
# Several graveyard cards returned at once: "For each color, return up to one
# target card of that color ..." and "Return target X card and (up to one)
# target Y card from your graveyard to ...".
# --------------------------------------------------------------------------

_PER_COLOR_RETURN_RE = re.compile(
    r"^for each color, return up to one target (?:[a-z]+ )?card of that color "
    r"from your graveyard to your hand\.?$",
    re.IGNORECASE,
)
_PAIR_RETURN_RE = re.compile(
    r"^return (?P<first>target [a-z ,]+? card) and (?P<second>(?:up to one )?target [^.]+? card) "
    r"from your graveyard to (?P<dest>the battlefield|your hand)\.?$",
    re.IGNORECASE,
)


def _graveyard_card_targets(game: "Game", obj: Any) -> list[CardState]:
    """The still-legal targets (CR 608.2b) that are cards in a graveyard,
    each once and in the order chosen."""
    seen: set[Any] = set()
    found: list[CardState] = []
    for target in game.resolve_targets(obj):
        if (
            isinstance(target, CardState)
            and target.zone is Zone.GRAVEYARD
            and target.id not in seen
        ):
            seen.add(target.id)
            found.append(target)
    return found


def _return_chosen_graveyard_cards(*, to_battlefield: bool) -> Any:
    def effect(game: "Game", obj: Any) -> None:
        controller = game.controller_of(obj)
        cards = _graveyard_card_targets(game, obj)
        if to_battlefield:
            with game.entering_together():  # CR 603.6a: one instruction, one event
                for card in cards:
                    game.put_onto_battlefield(card, controller.username)
        else:
            for card in cards:
                game.player(card.owner).move(card, Zone.HAND)

    return effect


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_per_color_graveyard_return(clause: str, *, for_spell: bool) -> Any:
    """CR 115.6 / CR 105.1: five optional colour slots (the targeting profile
    holds them), every chosen card returned to its owner's hand."""
    if "for each color" not in clause.lower():
        return None
    if _PER_COLOR_RETURN_RE.fullmatch(" ".join(clause.strip().split())) is None:
        return None
    if not profile_for_text(clause).understood:
        return None
    return _return_chosen_graveyard_cards(to_battlefield=False)


def _pair_graveyard_return(clause: str) -> Any:
    clause = _REMINDER_RE.sub("", clause).strip()
    """ "Return target creature card and up to one target Cleric ... card from
    your graveyard to the battlefield" - two targets from one instruction
    (CR 601.2c), both returned together (CR 603.6a)."""
    match = _PAIR_RETURN_RE.fullmatch(" ".join(clause.strip().split()))
    if match is None:
        return None
    profile = profile_for_text(clause)
    if not profile.understood or len(profile.requirements) != 2:
        return None
    if any(Zone.GRAVEYARD not in requirement.zones for requirement in profile.requirements):
        return None
    return _return_chosen_graveyard_cards(to_battlefield=match.group("dest").lower() != "your hand")


@SPELL_TEXT.rung("s23", before=("parse_mixed_effect_for_spell",))
def _parse_pair_graveyard_return_spell(text: str) -> Any:
    return _pair_graveyard_return(text) if " card and " in text.lower() else None


@ABILITY_TEXT.rung("s40", before=("parse_mixed_effect",))
def _parse_pair_graveyard_return_ability(text: str) -> Any:
    return _pair_graveyard_return(text) if " card and " in text.lower() else None


# --------------------------------------------------------------------------
# "Whenever Venom attacks, you may sacrifice another creature. If you do, draw
# X cards, then you may put a permanent card with mana value X or less from
# your hand onto the battlefield, where X is the sacrificed creature's mana
# value." - the consequence half, run by the conditional-sacrifice reader.
# --------------------------------------------------------------------------

_DRAW_X_THEN_PUT_RE = re.compile(
    r"^draw x cards, then you may put an? (?P<quality>.+?) card with mana value x or less "
    r"from your hand onto the battlefield, where x is the sacrificed "
    r"(?:creature|permanent|artifact|enchantment)'s mana value\.?$",
    re.IGNORECASE,
)


def sacrificed_value_draw_and_put(text: str) -> Callable[..., None] | None:
    """CR 608.2c: draw X (the sacrificed permanent's mana value as it last
    existed, CR 608.2h), then optionally put one qualifying card of mana value
    X or less from the hand (including the cards just drawn) onto the
    battlefield - a put, not a cast (CR 110.2a)."""
    match = _DRAW_X_THEN_PUT_RE.fullmatch(" ".join(text.strip().split()))
    if match is None or not _card_description_is_readable(match.group("quality")):
        return None
    matches_quality = _quality_matcher(match.group("quality"))

    def run(
        game: "Game", player: Player, sacrificed: float, source: str, source_id: str | None
    ) -> None:
        amount = int(sacrificed)
        if amount > 0:
            game.draw_cards(player.username, amount)
        candidates = [
            state
            for state in player.hand
            if state.mana_value <= sacrificed and matches_quality(state)
        ]
        if not candidates:
            return
        answer = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=player.username,
                prompt=(
                    f"you may put a card with mana value {amount} or less onto the battlefield"
                ),
                source=source,
                source_id=source_id,
                amount=1,
                exact=False,
                cards=tuple(state.id for state in candidates),
            )
        )
        assert isinstance(answer, tuple)
        for state in candidates:
            if state.id in set(answer):
                game.put_onto_battlefield(state, player.username)

    return run


# --------------------------------------------------------------------------
# "Surveil 2, then exile a card from a graveyard." and the exiled-batch trigger
# "you may choose a creature card from among them. Until end of turn, target
# token you control becomes a copy of it, except it has flying."
# --------------------------------------------------------------------------

_THEN_EXILE_GRAVEYARD_RE = re.compile(
    r"^(?P<lead>(?:surveil|scry) \d+), then (?P<tail>exile a card from a graveyard)\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s40", before=("parse_mixed_effect",))
def _parse_surveil_then_exile_from_graveyard(text: str) -> Any:
    """CR 608.2c: the lead instruction (CR 701.25 surveil / CR 701.22 scry)
    runs, then the controller exiles a card of their choice from any
    graveyard (the reader that holds the bare sentence)."""
    match = _THEN_EXILE_GRAVEYARD_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    from .exiled_with_peek import parse_exile_a_card_from_a_graveyard

    lead = _ability_effect_or_notice(f"{match.group('lead')}.")
    tail = parse_exile_a_card_from_a_graveyard(match.group("tail"))
    if lead is None or tail is None:
        return None

    def effect(game: "Game", ability: Any) -> None:
        lead(game, ability)
        tail(game, ability)

    return effect


_CHOOSE_FROM_AMONG_THEM_COPY_RE = re.compile(
    r"^you may choose an? (?P<quality>[a-z ]+?) card from among them\. "
    r"until end of turn, target (?P<subject>[a-z ]+?) becomes a copy of it, "
    r"except (?P<exception>it has [a-z ]+)\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s40", before=("parse_mixed_effect",))
def _parse_choose_exiled_card_then_become_copy(text: str) -> Any:
    """CR 603.2c / CR 707.9: off a batched "put into exile" event, choose one
    of the exiled cards (never a token, CR 108.2) and make the targeted
    permanent a copy of it until end of turn, with the stated exception
    written into the copy (CR 707.9b)."""
    match = _CHOOSE_FROM_AMONG_THEM_COPY_RE.fullmatch(" ".join(text.strip().split()))
    if match is None or not _card_description_is_readable(match.group("quality")):
        return None
    from .copy_effects import _become_a_copy, _copiable_values_of, _parse_become_copy_exceptions
    from .layers import Duration

    if not _targets_understood(f"target {match.group('subject')}", count_agnostic=True):
        return None
    exceptions = _parse_become_copy_exceptions(match.group("exception"))
    if exceptions is None:
        return None
    matches_quality = _quality_matcher(match.group("quality"))

    def effect(game: "Game", ability: Any) -> None:
        batch = ability.event.batch_ids if ability.event is not None else ()
        cards = [
            state
            for card_id in batch
            if isinstance(state := game.find_by_id(card_id), CardState)
            and state.zone is Zone.EXILE
            and not state.token
            and matches_quality(state)
        ]
        subject = next(
            (
                target
                for target in game.resolve_card_targets(ability)
                if target.zone is Zone.BATTLEFIELD
            ),
            None,
        )
        if not cards or subject is None:
            return
        controller = game.controller_of(ability)
        answer = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=controller.username,
                prompt=f"you may choose a {match.group('quality')} card from among them",
                source=ability.source_name,
                source_id=source_id_of(ability),
                amount=1,
                exact=False,
                cards=tuple(state.id for state in cards),
            )
        )
        assert isinstance(answer, tuple)
        chosen = next((state for state in cards if state.id in set(answer)), None)
        if chosen is None:
            return
        _become_a_copy(
            game,
            subject=subject,
            copied=_copiable_values_of(game, chosen),
            exceptions=exceptions,
            source_name=ability.source_name,
            own_name=subject.name,
            this_ability=None,
            duration=Duration.UNTIL_END_OF_TURN,
        )

    return effect
