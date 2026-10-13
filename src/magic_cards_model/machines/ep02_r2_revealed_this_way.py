"""EP-02 R2 T6: the "revealed / exiled / searched / separated this way"
back-reference - a later instruction that reads what an earlier one really did.

    Reveal cards from the top of your library until you reveal an artifact
    card. Put that card onto the battlefield and the rest on the bottom of your
    library in a random order. ~ deals damage to you equal to the number of
    cards revealed this way.

    Target opponent reveals the top card of their library. ~ deals damage equal
    to the revealed card's mana value to that player and each creature that
    player controls. If a land card is revealed this way, return ~ to its
    owner's hand.

CR 608.2c: the instructions of a spell or ability are followed in order, and
"this way" is the earlier instruction's own outcome - what it actually did.
CR 701.20a / CR 701.20b: to reveal a card is to show it to all players, and it
stays in the zone it is in; the reveal-until template reveals from the top one
card at a time, so the number revealed is a count of what was really shown.
CR 608.2h: information an effect needs from the game is taken once, when the
instruction is applied.

The reader is a small *plan*: the text is cut into clauses, and each clause is
one step that runs against a per-resolution context (`_Ctx`): the cards the
latest reveal showed, the cards that stopped it, and where each card was put.
Later steps ("put that card onto the battlefield", "the rest on the bottom",
"deals damage equal to the number of cards revealed this way") read the
context, so the same step vocabulary serves every card that prints the shape,
whoever reveals (you, a target opponent, the defending player, each player).
A clause no step here reads is handed back to the ordinary clause parsers; a
text with a clause nothing reads is refused whole (never half-read).

Registered as one SPELL_TEXT and one ABILITY_TEXT rung behind a cheap
lowercase gate, with memoised parsers, to stay inside the classify budget.
"""

import functools
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from random import Random
from typing import TYPE_CHECKING, Any
from uuid import UUID

from ..models.card import Type
from ..models.card_state import CardState, ChoiceKind
from ..models.player import Player
from ..models.zone import Zone
from ..numbers import parse_count
from .casting import PlayAction
from .conditions.history import excess_damage
from .decisions import Decision, DecisionKind, source_id_of
from .delayed import ReflexiveDamageEqualToSubjectManaValueConsequence
from .effects._chains import ABILITY_TEXT, SPELL_TEXT
from .effects._common import (
    _card_description_is_readable,
    _players_in_apnap_order,
    _quality_matcher,
)
from .effects.dispatch import _ability_effect_or_notice, _spell_effect_or_notice
from .effects.text import _plain_resolution_sentences, _strip_non_effect_preamble
from .effects.tokens import _is_notice_only
from .replacement.enters_choices import CARD_TYPE_OPTIONS

if TYPE_CHECKING:
    from ..models.game import Game

Step = Callable[["Game", Any, "_Ctx"], None]


# --------------------------------------------------------------------------
# The context a plan runs against
# --------------------------------------------------------------------------


@dataclass
class _Ctx:
    """What the instructions of one resolution have done so far."""

    actor: Player  # whose library is revealed / who "they" and "that player" are
    controller: Player  # the resolving spell's or ability's controller ("you")
    revealed: list[CardState] = field(default_factory=list)
    stoppers: list[CardState] = field(default_factory=list)
    disposed: set[UUID] = field(default_factory=set)
    moved: dict[str, list[CardState]] = field(default_factory=dict)
    name: str | None = None
    card_type: str | None = None
    referent: CardState | None = None
    excess: int = 0

    def subject_card(self) -> CardState | None:
        """The card "the revealed card" / "that card" names."""
        if self.stoppers:
            return self.stoppers[0]
        return self.revealed[-1] if self.revealed else None


def _source_of(obj: Any) -> CardState | None:
    return obj if isinstance(obj, CardState) else None


def _source_name(obj: Any) -> str:
    return getattr(obj, "source_name", None) or getattr(obj, "name", "")


def _targeted_player(game: "Game", obj: Any) -> Player | None:
    return next((t for t in game.resolve_targets(obj) if isinstance(t, Player)), None)


def _actor_for(game: "Game", obj: Any, ctx: _Ctx, who: str | None) -> Player | None:
    if who is None or who == "you":
        return ctx.controller
    if who in ("target opponent", "target player"):
        return _targeted_player(game, obj)
    if who == "defending player":
        name = game._defending_player_of(obj)
        return game.player(name) if name else None
    return ctx.actor  # they / that player / the player / its controller / each player


# --------------------------------------------------------------------------
# Matching the card a reveal stops at
# --------------------------------------------------------------------------

_SHARES_TYPE = "a card that shares a card type with it"


def _stop_matcher(quality: str) -> Callable[["Game", _Ctx, CardState], bool] | None:
    """The predicate for "a `<quality>` card": `quality` is a type phrase, "" for
    "a card" with a name (`with that name`) or `shares a card type with it`."""
    quality = quality.strip().lower()
    if quality == "with that name":
        return lambda game, ctx, state: state.name == ctx.name
    if quality == "that shares a card type with it":

        def shares(game: "Game", ctx: _Ctx, state: CardState) -> bool:
            if ctx.referent is None:
                return False
            chars = game.characteristics_of(ctx.referent)
            return bool(set(chars.types) & set(game.characteristics_of(state).types))

        return shares
    if not _card_description_is_readable(quality):
        return None
    matcher = _quality_matcher(quality)
    return lambda game, ctx, state: bool(matcher(state))


# --------------------------------------------------------------------------
# Reveal steps
# --------------------------------------------------------------------------

_WHO = (
    r"(?P<who>you|target opponent|target player|defending player|that player|they|the player"
    r"|its controller|each player)"
)
_LIBRARY = r"(?:your|their|that player's) library"
_COUNT_WORD = r"(?:a|an|one|two|three|four|five|six|seven|eight|nine|ten|x|\d+)"

_REVEAL_UNTIL_RE = re.compile(
    rf"^(?:{_WHO} )?(?P<verb>reveals?) cards from the top of {_LIBRARY} until "
    r"(?:(?:you|they|that player) reveal )?"
    r"(?:(?P<one>an?) (?P<q1>[a-z -]*?)\s*cards?"
    r"(?P<named> with that name| that shares a card type with it)?"
    r"|(?P<n>two|three|four|five|six|seven|eight|nine|ten|\d+) (?P<q2>[a-z -]*?)\s*cards"
    r"(?: are revealed)?)$",
    re.IGNORECASE,
)
_REVEAL_TOP_RE = re.compile(
    rf"^(?:{_WHO} )?(?P<verb>reveals?) the top "
    r"(?:(?P<n>two|three|four|five|six|seven|eight|nine|ten) cards|card) "
    rf"of {_LIBRARY}$",
    re.IGNORECASE,
)
_REVEAL_NUMBER_RE = re.compile(
    rf"^(?:{_WHO} )?(?P<verb>reveals?) a number of cards from the top of {_LIBRARY} "
    r"equal to the number of "
    r"(?P<q>[a-z -]+?) (?:they|you) control$",
    re.IGNORECASE,
)
_LOOK_TOP_RE = re.compile(
    r"^look at the top (?P<n>two|three|four|five|six|seven|eight|nine|ten) cards of your library$",
    re.IGNORECASE,
)


def _announce(game: "Game", obj: Any, state: CardState) -> None:
    game.reveal(state, source=_source_name(obj))


def _revealer(match: re.Match[str]) -> str | None:
    """Who reveals: the named player, or - for a bare third-person "reveals"
    ("... sacrifices it, then reveals cards") - whoever the last step named."""
    who = match.group("who")
    if who:
        return who.lower()
    return "they" if match.group("verb").lower() == "reveals" else None


def _reveal_until(match: re.Match[str]) -> Step | None:
    named = (match.group("named") or "").strip()
    quality = named if named else (match.group("q1") if match.group("one") else match.group("q2"))
    quality = quality or ""
    if not named and not quality.strip():
        # "a card" with nothing after it: every card stops the reveal.
        matcher: Callable[[Any, _Ctx, CardState], bool] | None = lambda _g, _c, _s: True  # noqa: E731
    else:
        matcher = _stop_matcher(quality)
    if matcher is None:
        return None
    count = 1 if match.group("one") else parse_count(match.group("n"))
    if count is None:
        return None
    who = _revealer(match)

    def step(game: "Game", obj: Any, ctx: _Ctx) -> None:
        actor = _actor_for(game, obj, ctx, who)
        if actor is None:
            return
        ctx.actor = actor
        ctx.revealed, ctx.stoppers = [], []
        for state in list(actor.library):
            _announce(game, obj, state)
            ctx.revealed.append(state)
            if matcher(game, ctx, state):
                ctx.stoppers.append(state)
                if len(ctx.stoppers) >= count:
                    break

    return step


def _reveal_top(match: re.Match[str]) -> Step:
    count = parse_count(match.group("n")) if match.group("n") else 1
    who = _revealer(match)

    def step(game: "Game", obj: Any, ctx: _Ctx) -> None:
        actor = _actor_for(game, obj, ctx, who)
        if actor is None:
            return
        ctx.actor = actor
        ctx.revealed, ctx.stoppers = list(actor.library[: count or 1]), []
        for state in ctx.revealed:
            _announce(game, obj, state)

    return step


def _reveal_number(match: re.Match[str]) -> Step | None:
    quality = match.group("q").strip().lower()
    if quality.endswith("permanents"):
        base = quality.removesuffix(" permanents").strip()
        if base and not _card_description_is_readable(base):
            return None
        matcher = _quality_matcher(base) if base else None
    else:
        return None
    who = _revealer(match)

    def step(game: "Game", obj: Any, ctx: _Ctx) -> None:
        actor = _actor_for(game, obj, ctx, who)
        if actor is None:
            return
        ctx.actor = actor
        count = sum(
            1
            for state in game.permanents_controlled_by(actor.username)
            if matcher is None or matcher(game.characteristics_of(state))
        )
        ctx.revealed, ctx.stoppers = list(actor.library[:count]), []
        for state in ctx.revealed:
            _announce(game, obj, state)

    return step


def _look_top(match: re.Match[str]) -> Step:
    count = parse_count(match.group("n")) or 1

    def step(game: "Game", obj: Any, ctx: _Ctx) -> None:
        ctx.actor = ctx.controller
        ctx.revealed, ctx.stoppers = list(ctx.controller.library[:count]), []

    return step


_CHOOSE_NAME_RE = re.compile(r"^choose a (?P<nonland>nonland )?card name$", re.IGNORECASE)
_CHOOSE_TYPE_RE = re.compile(r"^choose a card type$", re.IGNORECASE)


def _choose_name(match: re.Match[str]) -> Step:
    nonland = match.group("nonland") is not None

    def step(game: "Game", obj: Any, ctx: _Ctx) -> None:
        name = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_A_QUALITY,
                player=ctx.controller.username,
                prompt="choose a nonland card name" if nonland else "choose a card name",
                source=_source_name(obj),
                source_id=source_id_of(obj),
                quality=ChoiceKind.CARD_NAME.value,
            )
        )
        assert isinstance(name, str)
        ctx.name = name

    return step


def _choose_type(_match: re.Match[str]) -> Step:
    def step(game: "Game", obj: Any, ctx: _Ctx) -> None:
        answer = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_A_QUALITY,
                player=ctx.controller.username,
                prompt="choose a card type",
                source=_source_name(obj),
                source_id=source_id_of(obj),
                options=CARD_TYPE_OPTIONS,
                quality=ChoiceKind.CARD_TYPE.value,
            )
        )
        assert isinstance(answer, str)
        ctx.card_type = answer.lower()

    return step


# --------------------------------------------------------------------------
# Putting the revealed cards somewhere
# --------------------------------------------------------------------------

_SEL_TYPED = r"(?P<q>[a-z-]+(?: or [a-z-]+)?)"
_SELECTOR = (
    r"(?P<sel>that card|those cards|those (?P<kq>[a-z]+) cards|the revealed cards"
    r"|all cards revealed this way|all other cards revealed this way"
    r"|all cards of the chosen type revealed this way"
    rf"|(?:all |the ){_SEL_TYPED} cards (?:(?:they|you) )?revealed this way"
    rf"|the {_SEL_TYPED.replace('?P<q>', '?P<q3>')} card"
    r"|the rest(?: of the revealed cards| of them)?|one of them"
    r"|all cards with the chosen name from among them)"
)
_DEST = (
    r"(?P<dest>(?:into (?:your|their|that player's|its owner's|their owner's) "
    r"(?P<zone>hand|graveyard)"
    r"|onto the battlefield(?P<tapped> tapped)?(?P<under> under your control)?"
    r"|on the bottom of (?:your|their|that player's) library"
    r"(?P<order> in a random order| in any order)?"
    r"))"
)
_DISPOSE_RE = re.compile(
    rf"^(?:(?P<subj>you|they|that player|the player|its controller) )?(?P<verb>put|puts) "
    rf"{_SELECTOR} {_DEST}$",
    re.IGNORECASE,
)
_EXILE_RE = re.compile(
    rf"^(?:(?P<subj>you|they|that player|the player|its controller) )?(?P<verb>exile|exiles) "
    rf"{_SELECTOR}$",
    re.IGNORECASE,
)
_SHUFFLE_IN_RE = re.compile(
    rf"^(?:(?P<subj>you|they|that player|the player|its controller) )?shuffles? "
    rf"{_SELECTOR} into (?:your|their|that player's) library$",
    re.IGNORECASE,
)
_SHUFFLE_BARE_RE = re.compile(r"^(?:(?:you|they|that player) )?shuffles?$", re.IGNORECASE)


def _selector(match: re.Match[str]) -> Callable[["Game", Any, _Ctx], list[CardState]] | None:
    raw = match.group("sel").lower()
    groups = match.groupdict()
    quality = groups.get("q") or groups.get("kq") or groups.get("q3")
    matcher: Callable[[CardState], bool] | None = None
    if quality:
        if not _card_description_is_readable(quality):
            return None
        matcher = _quality_matcher(quality)

    def pool(ctx: _Ctx) -> list[CardState]:
        return [c for c in ctx.revealed if c.id not in ctx.disposed]

    if raw in ("that card",):
        return lambda _g, _o, ctx: [c for c in ctx.stoppers[:1] if c.id not in ctx.disposed]
    if raw.startswith("those ") or raw.startswith("the ") and raw.endswith(" card") and quality:
        return lambda _g, _o, ctx: [
            c for c in ctx.stoppers if c.id not in ctx.disposed and (matcher is None or matcher(c))
        ]
    if raw.startswith("the rest") or raw == "all other cards revealed this way":
        return lambda _g, _o, ctx: [c for c in pool(ctx) if c not in ctx.stoppers]
    if raw == "all cards of the chosen type revealed this way":
        return lambda _g, _o, ctx: [
            c
            for c in pool(ctx)
            if ctx.card_type and ctx.card_type in {t.value.lower() for t in c.card.types}
        ]
    if raw in ("the revealed cards", "all cards revealed this way"):
        return lambda _g, _o, ctx: pool(ctx)
    if raw == "all cards with the chosen name from among them":
        return lambda _g, _o, ctx: [c for c in pool(ctx) if c.name == ctx.name]
    if raw == "one of them":
        return lambda game, obj, ctx: _choose_one(game, obj, ctx, pool(ctx))
    if matcher is not None:
        return lambda _g, _o, ctx: [c for c in pool(ctx) if matcher(c)]
    return None


def _choose_one(game: "Game", obj: Any, ctx: _Ctx, candidates: list[CardState]) -> list[CardState]:
    if not candidates:
        return []
    chosen = game.ask(
        Decision(
            kind=DecisionKind.CHOOSE_CARDS,
            player=ctx.controller.username,
            prompt="choose one of the cards",
            source=_source_name(obj),
            source_id=source_id_of(obj),
            amount=1,
            exact=True,
            cards=tuple(c.id for c in candidates),
            card_labels=tuple(c.name for c in candidates),
            default_cards=(candidates[0].id,),
        )
    )
    assert isinstance(chosen, tuple)
    by_id = {c.id: c for c in candidates}
    return [by_id[i] for i in chosen if i in by_id][:1]


def _move_cards(
    game: "Game",
    obj: Any,
    ctx: _Ctx,
    cards: list[CardState],
    zone: str,
    *,
    tapped: bool = False,
    under_controller: bool = False,
    order: str | None = None,
) -> None:
    for state in cards:
        ctx.disposed.add(state.id)
    ctx.moved.setdefault(zone, [])
    if zone == "bottom":
        if order and "random" in order:
            rng = Random(f"{game.shuffle_seed}:{game.shuffles_performed}:revealed-bottom")  # noqa: S311
            cards = list(cards)
            rng.shuffle(cards)
            game.shuffles_performed += 1
        elif len(cards) > 1:
            cards = game.ask_library_bottom_order(
                ctx.actor, cards, source=_source_name(obj), source_id=source_id_of(obj)
            )
        for state in cards:
            game.player(state.owner or ctx.actor.username).move(state, Zone.LIBRARY)
        ctx.moved.setdefault("library", []).extend(cards)
        return
    for state in cards:
        if zone == "hand":
            game.player(state.owner or ctx.actor.username).move(state, Zone.HAND)
        elif zone == "graveyard":
            game.put_into_graveyard(state)
        elif zone == "exile":
            game.exile_permanent(state)
        elif zone == "battlefield":
            who = ctx.controller if under_controller else ctx.actor
            game.put_onto_battlefield(state, who.username, tapped=tapped)
        ctx.moved[zone].append(state)


def _dispose(match: re.Match[str]) -> Step | None:
    select = _selector(match)
    if select is None:
        return None
    zone_word = (match.group("zone") or "").lower()
    if match.group("dest").lower().startswith("onto"):
        zone = "battlefield"
    elif match.group("dest").lower().startswith("on the bottom"):
        zone = "bottom"
    else:
        zone = zone_word
    subj = (match.group("subj") or "").lower()
    # "Put ..." (imperative) and "you put ..." are the resolving player's act;
    # "puts ..." / "they put ..." are the revealing player's own.
    yours = (
        match.group("under") is not None
        or subj == "you"
        or (not subj and match.group("verb").lower() == "put")
    )
    tapped = match.group("tapped") is not None
    order = match.group("order")

    def step(game: "Game", obj: Any, ctx: _Ctx) -> None:
        _move_cards(
            game,
            obj,
            ctx,
            select(game, obj, ctx),
            zone,
            tapped=tapped,
            under_controller=yours,
            order=order,
        )

    return step


def _exile_step(match: re.Match[str]) -> Step | None:
    select = _selector(match)
    if select is None:
        return None

    def step(game: "Game", obj: Any, ctx: _Ctx) -> None:
        _move_cards(game, obj, ctx, select(game, obj, ctx), "exile")

    return step


def _shuffle_in_step(match: re.Match[str]) -> Step | None:
    select = _selector(match)
    if select is None:
        return None

    def step(game: "Game", obj: Any, ctx: _Ctx) -> None:
        cards = select(game, obj, ctx)
        for state in cards:
            ctx.disposed.add(state.id)
            game.player(state.owner or ctx.actor.username).move(state, Zone.LIBRARY)
        game.shuffle_library(ctx.actor)

    return step


# --------------------------------------------------------------------------
# Amounts and payoffs
# --------------------------------------------------------------------------

Amount = Callable[["Game", Any, _Ctx], int]

_AMOUNT_PATTERNS: tuple[tuple[re.Pattern[str], Callable[[re.Match[str]], Amount | None]], ...]


def _count_revealed(match: re.Match[str]) -> Amount | None:
    quality = (match.groupdict().get("q") or "").strip()
    if quality and not _card_description_is_readable(quality):
        return None
    matcher = _quality_matcher(quality) if quality else None
    return lambda _g, _o, ctx: sum(1 for c in ctx.revealed if matcher is None or matcher(c))


def _mana_value_of_subject(_match: re.Match[str]) -> Amount:
    def amount(game: "Game", _obj: Any, ctx: _Ctx) -> int:
        card = ctx.subject_card()
        return int(game.characteristics_of(card).mana_value or 0) if card else 0

    return amount


def _greatest_among_moved(match: re.Match[str]) -> Amount | None:
    quality = (match.group("q") or "").strip()
    if quality and not _card_description_is_readable(quality):
        return None
    matcher = _quality_matcher(quality) if quality else None
    stat = "power" if match.group("stat").lower() == "power" else "mana_value"
    zone = "graveyard" if "graveyard" in match.group("verb").lower() else "exile"

    def amount(game: "Game", _obj: Any, ctx: _Ctx) -> int:
        values = [
            int(getattr(game.characteristics_of(c), stat, 0) or 0)
            for c in ctx.moved.get(zone, ())
            if matcher is None or matcher(c)
        ]
        return max(values, default=0)

    return amount


def _count_moved(match: re.Match[str]) -> Amount:
    zone = "exile" if "exiled" in match.group("what").lower() else "graveyard"
    return lambda _g, _o, ctx: len(ctx.moved.get(zone, ()))


_AMOUNT_PATTERNS = (
    (
        re.compile(
            r"^the number of (?:(?P<q>[a-z-]+) )?cards (?:(?:they|you) )?revealed this way$",
            re.IGNORECASE,
        ),
        _count_revealed,
    ),
    (
        re.compile(
            r"^(?:the revealed card's|that card's|the exiled card's) mana value$", re.IGNORECASE
        ),
        _mana_value_of_subject,
    ),
    (
        re.compile(
            r"^the greatest (?P<stat>power|mana value) among (?:(?P<q>[a-z-]+) )?cards "
            r"(?P<verb>put into your graveyard|exiled) this way$",
            re.IGNORECASE,
        ),
        _greatest_among_moved,
    ),
    (
        re.compile(r"^of the (?P<what>exiled|milled) cards$", re.IGNORECASE),
        _count_moved,
    ),
)


@functools.cache
def _amount(expr: str) -> Amount | None:
    for pattern, build in _AMOUNT_PATTERNS:
        match = pattern.fullmatch(expr.strip())
        if match is not None:
            return build(match)
    return None


_DAMAGE_PLAYER_RE = re.compile(
    r"^(?P<src>.+?) deals damage to (?P<to>you|that player) equal to (?P<expr>.+)$", re.IGNORECASE
)
_DAMAGE_PLAYER_AND_CREATURES_RE = re.compile(
    r"^(?P<src>.+?) deals damage equal to (?P<expr>.+?) to (?P<to>that player) and each creature "
    r"that player controls$",
    re.IGNORECASE,
)
_LIFE_FOR_EACH_RE = re.compile(
    r"^(?P<who>you|that player) (?P<verb>lose|gain)s? (?P<n>a|one|\d+) life for each "
    r"(?P<each>.+)$",
    re.IGNORECASE,
)
_LIFE_EQUAL_RE = re.compile(
    r"^(?P<who>you|that player) (?P<verb>lose|gain)s? life equal to (?P<expr>.+)$", re.IGNORECASE
)
_IF_REVEALED_RETURN_RE = re.compile(
    r"^if an? (?P<q>[a-z-]+) card is revealed this way, return (?P<src>.+?) to its owner's hand$",
    re.IGNORECASE,
)


def _damage_players(match: re.Match[str]) -> Step | None:
    amount = _amount(match.group("expr"))
    if amount is None:
        return None
    to_creatures = "each creature" in match.string.lower()

    def step(game: "Game", obj: Any, ctx: _Ctx) -> None:
        n = amount(game, obj, ctx)
        if n <= 0:
            return
        source = _source_of(obj) or (obj.source(game) if hasattr(obj, "source") else None)
        player = ctx.controller if match.group("to").lower() == "you" else ctx.actor
        game.deal_damage(player, n, source=source)
        if to_creatures:
            for state in list(game.permanents_controlled_by(player.username)):
                if state.zone is Zone.BATTLEFIELD and Type.CREATURE in (
                    game.characteristics_of(state).types
                ):
                    game.deal_damage(state, n, source=source)

    return step


def _life_for_each(match: re.Match[str]) -> Step | None:
    each = match.group("each").strip()
    count = _amount(each)
    if count is None:
        return None
    unit = 1 if match.group("n").lower() in ("a", "one") else int(match.group("n"))
    gains = match.group("verb").lower() == "gain"
    who = match.group("who").lower()

    def step(game: "Game", obj: Any, ctx: _Ctx) -> None:
        n = unit * count(game, obj, ctx)
        player = ctx.controller if who == "you" else ctx.actor
        if n > 0:
            (game.gain_life if gains else game.lose_life)(player, n)

    return step


def _life_equal(match: re.Match[str]) -> Step | None:
    amount = _amount(match.group("expr"))
    if amount is None:
        return None
    gains = match.group("verb").lower() == "gain"
    who = match.group("who").lower()

    def step(game: "Game", obj: Any, ctx: _Ctx) -> None:
        n = amount(game, obj, ctx)
        player = ctx.controller if who == "you" else ctx.actor
        if n > 0:
            (game.gain_life if gains else game.lose_life)(player, n)

    return step


def _if_revealed_return(match: re.Match[str]) -> Step | None:
    quality = match.group("q")
    if not _card_description_is_readable(quality):
        return None
    matcher = _quality_matcher(quality)

    def step(game: "Game", obj: Any, ctx: _Ctx) -> None:
        if any(matcher(c) for c in ctx.revealed):
            source = _source_of(obj)
            if source is not None and source.zone is not Zone.HAND:
                game.return_to_hand(source)

    return step


_WHEN_REVEAL_DAMAGE_RE = re.compile(
    r"^when you (?P<verb>reveal|exile) an? (?P<q>[a-z -]+?) card this way, (?P<src>.+?) deals "
    r"damage equal to (?:that|the exiled|the revealed) card's mana value to any target$",
    re.IGNORECASE,
)


def _when_reveal_damage(match: re.Match[str]) -> Step | None:
    quality = match.group("q").strip()
    if not _card_description_is_readable(quality):
        return None
    matcher = _quality_matcher(quality)
    revealing = match.group("verb").lower() == "reveal"
    text = (
        f"When you do, {match.group('src')} deals damage equal to that card's mana value "
        "to any target."
    )

    def step(game: "Game", obj: Any, ctx: _Ctx) -> None:
        pool = ctx.stoppers if revealing else ctx.moved.get("exile", [])
        card = next((c for c in pool if matcher(c)), None)
        if card is None:
            return
        game.create_reflexive_trigger(
            text=text,
            controller=ctx.controller.username,
            source_id=source_id_of(obj),
            source_name=_source_name(obj),
            callback=ReflexiveDamageEqualToSubjectManaValueConsequence(),
            subject_id=card.id,
        )

    return step


_SACRIFICE_CONTROLLER_RE = re.compile(
    r"^the controller of target (?P<q>[a-z -]+?) sacrifices it$", re.IGNORECASE
)


def _sacrifice_by_controller(match: re.Match[str]) -> Step | None:
    quality = match.group("q").strip()
    if not _card_description_is_readable(quality):
        return None

    def step(game: "Game", obj: Any, ctx: _Ctx) -> None:
        for target in game.resolve_targets(obj):
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD:
                ctx.actor = game.controller_of(target)
                ctx.referent = target
                game.sacrifice(target)
                return

    return step


_DEAL_DAMAGE_TARGET_RE = re.compile(
    r"^(?P<src>.+?) deals (?P<n>\d+) damage to (?P<t>target [a-z, ]+)$", re.IGNORECASE
)
_LOOK_TOP_EXCESS_RE = re.compile(
    r"^look at the top x cards of your library, where x is the excess damage dealt this way$",
    re.IGNORECASE,
)
_MAY_EXILE_ONE_RE = re.compile(r"^you may exile one of those cards$", re.IGNORECASE)
_PLAY_EXILED_RE = re.compile(r"^you may play the exiled card this turn$", re.IGNORECASE)
_PUMP_REVEALED_RE = re.compile(
    r"^the creature gets \+(?P<p>\d+)/\+(?P<t>\d+) until end of turn for each card revealed "
    r"this way$",
    re.IGNORECASE,
)
_PLAN_TEXT: list[str] = []


def _deal_damage_noting_excess(match: re.Match[str]) -> Step | None:
    """ "`<source>` deals N damage to target `<thing>`." when a later instruction
    counts the excess damage dealt this way (CR 120.10)."""
    if not _PLAN_TEXT or "excess damage" not in _PLAN_TEXT[-1].lower():
        return None
    amount = int(match.group("n"))

    def step(game: "Game", obj: Any, ctx: _Ctx) -> None:
        source = _source_of(obj)
        ctx.excess = 0
        for target in game.resolve_targets(obj):
            if isinstance(target, CardState) and target.zone is not Zone.BATTLEFIELD:
                continue
            ctx.excess = excess_damage(game, target, amount, source)
            game.deal_damage(target, amount, source=source)
            return

    return step


def _look_top_excess(_match: re.Match[str]) -> Step:
    def step(game: "Game", obj: Any, ctx: _Ctx) -> None:
        ctx.actor = ctx.controller
        ctx.revealed, ctx.stoppers = list(ctx.controller.library[: ctx.excess]), []

    return step


def _may_exile_one(_match: re.Match[str]) -> Step:
    def step(game: "Game", obj: Any, ctx: _Ctx) -> None:
        pool = [c for c in ctx.revealed if c.id not in ctx.disposed]
        if not pool:
            return
        chosen = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=ctx.controller.username,
                prompt="you may exile one of those cards",
                source=_source_name(obj),
                source_id=source_id_of(obj),
                amount=1,
                exact=False,
                cards=tuple(c.id for c in pool),
                card_labels=tuple(c.name for c in pool),
                default_cards=(),
            )
        )
        assert isinstance(chosen, tuple)
        by_id = {c.id: c for c in pool}
        picked = [by_id[i] for i in chosen if i in by_id][:1]
        _move_cards(game, obj, ctx, picked, "exile")

    return step


def _pump_per_revealed(match: re.Match[str]) -> Step | None:
    power, toughness = int(match.group("p")), int(match.group("t"))

    def step(game: "Game", obj: Any, ctx: _Ctx) -> None:
        subject_id = getattr(getattr(obj, "event", None), "subject_id", None)
        creature = game.find_by_id(subject_id) if subject_id is not None else None
        n = len(ctx.revealed)
        if not isinstance(creature, CardState) or creature.zone is not Zone.BATTLEFIELD or n <= 0:
            return
        pump = _parse_cached(
            f"this creature gets +{power * n}/+{toughness * n} until end of turn.", False
        )
        if pump is not None:
            pump(
                game,
                obj.model_copy(update={"source_id": creature.id, "source_name": creature.name}),
            )

    return step


_EXILE_TOP_RE = re.compile(r"^exile the top card of your library$", re.IGNORECASE)
_PLAY_THAT_CARD_RE = re.compile(r"^you may play that card this turn$", re.IGNORECASE)


def _exile_top(_match: re.Match[str]) -> Step:
    def step(game: "Game", obj: Any, ctx: _Ctx) -> None:
        ctx.actor = ctx.controller
        if not ctx.controller.library:
            return
        card = game.exile_permanent(ctx.controller.library[0])
        ctx.revealed, ctx.stoppers = [card], []
        ctx.moved.setdefault("exile", []).append(card)

    return step


def _play_that_card(_match: re.Match[str]) -> Step:
    def step(game: "Game", obj: Any, ctx: _Ctx) -> None:
        for card in ctx.moved.get("exile", [])[-1:]:
            game.grant_play_permission(
                card,
                ctx.controller.username,
                action=PlayAction.PLAY,
                pays_mana_cost=True,
                source_name=_source_name(obj),
                rule="CR 601.3",
                zone=card.zone,
                until_end_of_turn=True,
            )

    return step


# Readers, tried in order; each is (pattern, builder).
_READERS: tuple[tuple[re.Pattern[str], Callable[[re.Match[str]], Step | None]], ...] = (
    (_CHOOSE_NAME_RE, _choose_name),
    (_CHOOSE_TYPE_RE, _choose_type),
    (_REVEAL_UNTIL_RE, _reveal_until),
    (_REVEAL_TOP_RE, _reveal_top),
    (_REVEAL_NUMBER_RE, _reveal_number),
    (_LOOK_TOP_RE, _look_top),
    (_DISPOSE_RE, _dispose),
    (_EXILE_RE, _exile_step),
    (_SHUFFLE_IN_RE, _shuffle_in_step),
    (_DAMAGE_PLAYER_RE, _damage_players),
    (_DAMAGE_PLAYER_AND_CREATURES_RE, _damage_players),
    (_LIFE_FOR_EACH_RE, _life_for_each),
    (_LIFE_EQUAL_RE, _life_equal),
    (_IF_REVEALED_RETURN_RE, _if_revealed_return),
    (_WHEN_REVEAL_DAMAGE_RE, _when_reveal_damage),
    (_SACRIFICE_CONTROLLER_RE, _sacrifice_by_controller),
    (_DEAL_DAMAGE_TARGET_RE, _deal_damage_noting_excess),
    (_LOOK_TOP_EXCESS_RE, _look_top_excess),
    (_MAY_EXILE_ONE_RE, _may_exile_one),
    (_PUMP_REVEALED_RE, _pump_per_revealed),
    (_EXILE_TOP_RE, _exile_top),
    (_PLAY_THAT_CARD_RE, _play_that_card),
    (_PLAY_EXILED_RE, _play_that_card),
)

# --------------------------------------------------------------------------
# Cutting a text into clauses and running the plan
# --------------------------------------------------------------------------

_CLAUSE_SPLIT_RE = re.compile(
    r",? (?:and|then) (?=(?:you |they |that player |puts? |exiles? |shuffles? |the rest |"
    r"all other |[a-z' ,-]+? deals ))|, then (?=[a-z])|, (?=puts? )",
    re.IGNORECASE,
)
_REST_LEAD_RE = re.compile(r"^(the rest .*)$", re.IGNORECASE)


def _clauses(sentence: str) -> list[str]:
    parts = [p.strip() for p in _CLAUSE_SPLIT_RE.split(sentence.strip().rstrip("."))]
    out = []
    for part in parts:
        if not part:
            continue
        if _REST_LEAD_RE.match(part):
            part = "put " + part
        out.append(part)
    return out


_READING: list[bool] = []


def _parse_cached(text: str, for_spell: bool) -> Any:
    """A clause handed back to the ordinary parsers; this module's own rungs
    stand aside while it is being read (a clause is never re-planned)."""
    _READING.append(True)
    try:
        effect = _spell_effect_or_notice(text) if for_spell else _ability_effect_or_notice(text)
    finally:
        _READING.pop()
    return None if effect is None or _is_notice_only(effect) else effect


@dataclass(frozen=True)
class _Plan:
    steps: tuple[Step, ...]
    each_player: bool


@functools.lru_cache(maxsize=2048)
def _plan(text: str, for_spell: bool) -> _Plan | None:
    _PLAN_TEXT.append(text)
    try:
        return _plan_uncached(text, for_spell)
    finally:
        _PLAN_TEXT.pop()


def _plan_uncached(text: str, for_spell: bool) -> _Plan | None:
    steps: list[Step] = []
    mine = 0
    each_player = False
    for sentence in _plain_resolution_sentences(_strip_non_effect_preamble(text)):
        if re.match(r"^each player reveals", sentence.strip(), re.IGNORECASE):
            each_player = True
        for clause in _clauses(sentence):
            step = None
            for pattern, build in _READERS:
                match = pattern.fullmatch(clause)
                if match is not None:
                    step = build(match)
                    if step is not None:
                        mine += 1
                        break
            if step is None:
                effect = _parse_cached(clause + ".", for_spell)
                if effect is None:
                    return None
                step = _plain_step(effect)
            steps.append(step)
    if mine == 0:
        return None
    return _Plan(tuple(steps), each_player)


def _plain_step(effect: Any) -> Step:
    return lambda game, obj, ctx: effect(game, obj)


def _gate(text: str) -> bool:
    lowered = text.lower()
    return "this way" in lowered or "reveals cards from the top" in lowered


def _effect(text: str, for_spell: bool) -> Any:
    if _READING or not _gate(text):
        return None
    plan = _plan(text, for_spell)
    if plan is None:
        return None

    def effect(game: "Game", obj: Any) -> None:
        controller = game.controller_of(obj)
        if plan.each_player:
            for player in _players_in_apnap_order(game):
                ctx = _Ctx(actor=player, controller=controller)
                for step in plan.steps:
                    step(game, obj, ctx)
            return
        ctx = _Ctx(actor=controller, controller=controller)
        for step in plan.steps:
            step(game, obj, ctx)

    return effect


@SPELL_TEXT.rung("s23", before=("parse_mixed_effect_for_spell",))
def _parse_revealed_this_way_spell(text: str) -> Any:
    """A spell whose later instruction reads what its reveal really showed."""
    return _effect(text, True)


@ABILITY_TEXT.rung("s40", before=("parse_mixed_effect",))
def _parse_revealed_this_way_ability(text: str) -> Any:
    """An ability whose later instruction reads what its reveal really showed."""
    return _effect(text, False)
