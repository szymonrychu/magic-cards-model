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

from ..models.card import Color
from ..models.card_state import CardState
from ..models.player import Player
from ..models.zone import Zone
from ..numbers import COUNT, parse_count
from .decisions import Decision, DecisionKind, source_id_of
from .delayed import ReflexiveDamageEqualToSubjectPowerConsequence
from .effects._chains import ABILITY_TEXT, SPELL_TEXT
from .effects._common import _card_description_is_readable, _quality_matcher
from .effects.amounts import count_expression
from .effects.library import _bottom_in_random_order, _put_rest_on_bottom
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
