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

import dataclasses
import functools
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from random import Random
from typing import TYPE_CHECKING, Any
from uuid import UUID

from ..data.subtypes import canonical_subtype
from ..models.card import Type
from ..models.card_state import CardState, ChoiceKind
from ..models.player import Player
from ..models.token import is_token
from ..models.zone import Zone
from ..numbers import parse_count
from .casting import PlayAction
from .conditions.history import excess_damage
from .amount_sentences import recipient_amount
from .decisions import Decision, DecisionKind, source_id_of
from .delayed import (
    DelayedTrigger,
    PhaseInEach,
    ReflexiveDamageEqualToSubjectManaValueConsequence,
)
from .effects._chains import ABILITY_TEXT, SPELL_TEXT
from .effects._common import (
    _card_description_is_readable,
    _players_in_apnap_order,
    _quality_matcher,
    _targets_understood,
)
from .effects.library import _mill
from .effects.continuous import continuous_effects
from .effects.search import _search_and_exile_matching_name
from .effects.dispatch import _ability_effect_or_notice, _spell_effect_or_notice
from .effects.text import _plain_resolution_sentences, _strip_non_effect_preamble
from .effects.tokens import _is_notice_only, investigate
from .ep02_r1_this_way_counts import _VERBS as _r1_verbs
from .ep02_r1_this_way_counts import _first_instruction as _r1_first_instruction
from .ep02_r1_this_way_counts import _objects as _r1_objects
from .ep02_r1_this_way_counts import _plan as _r1_plan
from .ep02_r1_this_way_counts import _sentences as _r1_sentences
from .ep02_r1_this_way_counts import affected as _r1_affected
from .ep02_r1_this_way_counts import snapshot as _r1_snapshot
from .layers import ContinuousEffect, Layer, add_subtype, only_this_incarnation
from .targeting import profile_for_text
from .triggers import TriggerEvent
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
    referent_chars: Any = None  # the referent as it last existed (CR 608.2h)
    excess: int = 0
    chosen: CardState | None = None  # the permanent a "choose a ..." sentence picked
    referent_controller: str | None = None
    x: int = 0  # the value of ", where X is ..."
    last_amount: int = 0  # the number the latest damage or life instruction used

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
            if ctx.referent is None and ctx.referent_chars is None:
                return False
            chars = ctx.referent_chars or game.characteristics_of(ctx.referent)
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
    r"(?P<named> with that name| that shares a card type with it)?(?: is revealed)?"
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
    r"(?P<sel>that card|those cards|those (?P<kq>[a-z]+) cards|the revealed cards|the exiled cards"
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
    rf"^(?:(?P<subj>you|they|that player|the player|its controller|those players) )?(?P<verb>put|puts) "
    rf"{_SELECTOR} {_DEST}$",
    re.IGNORECASE,
)
_EXILE_RE = re.compile(
    rf"^(?:(?P<subj>you|they|that player|the player|its controller|those players) )?(?P<verb>exile|exiles) "
    rf"{_SELECTOR}$",
    re.IGNORECASE,
)
_SHUFFLE_IN_RE = re.compile(
    rf"^(?:(?P<subj>you|they|that player|the player|its controller|those players) )?shuffles? "
    rf"{_SELECTOR} into (?:your|their|that player's) library$",
    re.IGNORECASE,
)
_SHUFFLE_BARE_RE = re.compile(
    r"^(?:(?:you|they|that player|those players|its controller) )?shuffles?$", re.IGNORECASE
)


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

    if raw == "that card":
        return lambda _g, _o, ctx: [c for c in ctx.stoppers[:1] if c.id not in ctx.disposed]
    if raw == "the exiled cards":
        return lambda _g, _o, ctx: [c for c in ctx.moved.get("exile", []) if c.zone is Zone.EXILE]
    if raw == "those cards":
        # Cards a search found (a for-each plan keeps every one the player
        # found), else the cards the latest reveal stopped at.
        return lambda _g, _o, ctx: [
            c for c in (ctx.moved.get("found") or ctx.stoppers) if c.id not in ctx.disposed
        ]
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


def _shuffle_bare_step(_match: re.Match[str]) -> Step:
    def step(game: "Game", obj: Any, ctx: _Ctx) -> None:
        game.shuffle_library(ctx.actor)

    return step


_SEARCH_RE = re.compile(
    r"^(?:(?P<subj>you|they|that player|its controller) )?(?P<may>may )?searche?s? "
    r"(?:your|their|that player's) library for (?P<n>an?|one|two|three|four|\d+) "
    r"(?P<q>[a-z' ,-]+?) cards?$",
    re.IGNORECASE,
)


def _search_step(match: re.Match[str]) -> Step | None:
    quality = match.group("q").strip().lower()
    if not _card_description_is_readable(quality):
        return None
    matcher = _quality_matcher(quality)
    count = 1 if match.group("n").lower() in ("a", "an", "one") else parse_count(match.group("n"))
    if count is None:
        return None
    subj = (match.group("subj") or "you").lower()

    def step(game: "Game", obj: Any, ctx: _Ctx) -> None:
        player = ctx.controller if subj == "you" else ctx.actor
        ctx.actor = player
        # CR 701.23b: a search for a stated quality may find fewer; the shuffle
        # is its own later instruction (CR 701.24b), so it is held back here.
        found = game.search_library(
            player,
            lambda state: bool(matcher(state)),
            count=count,
            optional=True,
            shuffle=False,
            source=_source_name(obj),
            source_id=source_id_of(obj),
        )
        ctx.revealed, ctx.stoppers = list(found), list(found)
        ctx.moved.setdefault("found", []).extend(found)

    return step


_INVESTIGATES_RE = re.compile(r"^(?:that player|its controller|they) investigates?$", re.IGNORECASE)


def _investigate_step(_match: re.Match[str]) -> Step:
    def step(game: "Game", obj: Any, ctx: _Ctx) -> None:
        investigate(game, ctx.actor.username)

    return step


_NO_SPLIT = "\u0001"
_SAME_NAME_RE = re.compile(r"(same name as that card) and exile them", re.IGNORECASE)
_SEARCH_SAME_NAME_RE = re.compile(
    r"^(?:(?:you|they) )?searche?s? (?:that player's|their|your) "
    r"(?P<zones>library|graveyard, hand, and library) for "
    rf"(?P<amount>all|any number of|up to (?P<n>{_COUNT_WORD})) cards with the same name as "
    rf"that card{_NO_SPLIT}exile them$",
    re.IGNORECASE,
)


def _search_same_name_step(match: re.Match[str]) -> Step | None:
    """CR 701.23a: search the named zones of the player for the cards sharing the
    exiled card's name and exile them; the shuffle is a later instruction."""
    cap = parse_count(match.group("n")) if match.group("n") else None
    if match.group("n") and cap is None:
        return None
    zones = (
        (Zone.LIBRARY,)
        if match.group("zones").lower() == "library"
        else (Zone.GRAVEYARD, Zone.HAND, Zone.LIBRARY)
    )

    def step(game: "Game", obj: Any, ctx: _Ctx) -> None:
        if ctx.referent is None:
            return
        exiled, _from_hand = _search_and_exile_matching_name(
            game,
            ctx.actor,
            ctx.referent.name,
            chooser=ctx.controller,
            cap=cap,
            source=_source_name(obj),
            source_id=source_id_of(obj),
            zones=zones,
            shuffle=False,
        )
        ctx.moved.setdefault("exile", []).extend(exiled)

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


def _power_tapped_for_cost(_match: re.Match[str]) -> Amount:
    """CR 602.2b / CR 608.2h: the power the creature tapped to pay the cost had."""
    return lambda _g, obj, _ctx: sum(
        int(power or 0) for power in getattr(obj, "cost_tapped_powers", ())
    )


def _count_in_moved(key: str) -> Callable[[re.Match[str]], Amount]:
    return lambda _match: lambda _g, _o, ctx: len(ctx.moved.get(key, ()))


def _cards_owned_in_exile(_match: re.Match[str]) -> Amount:
    return lambda game, _o, ctx: sum(1 for c in game.exile if c.owner == ctx.actor.username)


_AMOUNT_PATTERNS = (
    (
        re.compile(r"^the power of the (?:creature|permanent) tapped this way$", re.IGNORECASE),
        _power_tapped_for_cost,
    ),
    (
        re.compile(r"^(?:the number of )?spells? countered this way$", re.IGNORECASE),
        _count_in_moved("countered"),
    ),
    (
        re.compile(
            r"^(?:the number of )?cards? shuffled into your library this way$", re.IGNORECASE
        ),
        _count_in_moved("shuffled"),
    ),
    (
        re.compile(r"^the number of cards that player owns in exile$", re.IGNORECASE),
        _cards_owned_in_exile,
    ),
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
    r"^(?P<src>.+?) deals damage to (?P<to>you|that player|target player) equal to (?P<expr>.+)$",
    re.IGNORECASE,
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
        to = match.group("to").lower()
        if to == "target player":
            targeted = _targeted_player(game, obj)
            if targeted is None:
                return
            ctx.actor = targeted
        n = amount(game, obj, ctx)
        ctx.last_amount = max(n, 0)
        if n <= 0:
            return
        source = _source_of(obj) or (obj.source(game) if hasattr(obj, "source") else None)
        player = ctx.controller if to == "you" else ctx.actor
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


_COUNTER_ALL_OTHER_RE = re.compile(r"^counter all other spells$", re.IGNORECASE)


def _counter_all_other(_match: re.Match[str]) -> Step:
    """CR 701.6a: every spell on the stack but this one is countered; an
    uncounterable one stays (CR 113.6g), so the count is of what really left."""

    def step(game: "Game", obj: Any, ctx: _Ctx) -> None:
        for item in list(game.stack):
            if isinstance(item, CardState) and item.id != getattr(obj, "id", None):
                game.counter(item)
                if item not in game.stack:
                    ctx.moved.setdefault("countered", []).append(item)

    return step


_DRAW_FOR_EACH_RE = re.compile(
    r"^(?:you )?draws? (?P<n>a|one|two|three|\d+) cards? for each (?P<each>.+)$", re.IGNORECASE
)


def _draw_for_each(match: re.Match[str]) -> Step | None:
    count = _amount(match.group("each"))
    if count is None:
        return None
    unit = 1 if match.group("n").lower() in ("a", "one") else parse_count(match.group("n"))
    if unit is None:
        return None

    def step(game: "Game", obj: Any, ctx: _Ctx) -> None:
        n = unit * count(game, obj, ctx)
        if n > 0:
            game.draw_cards(ctx.controller.username, n)

    return step


_SHUFFLE_GRAVEYARD_RE = re.compile(
    r"^shuffle all (?P<q>[a-z-]+) cards from your graveyard into your library$", re.IGNORECASE
)


def _shuffle_graveyard(match: re.Match[str]) -> Step | None:
    quality = match.group("q").strip().lower()
    if not _card_description_is_readable(quality):
        return None
    matcher = _quality_matcher(quality)

    def step(game: "Game", obj: Any, ctx: _Ctx) -> None:
        player = ctx.controller
        ctx.actor = player
        cards = [c for c in player.graveyard if matcher(c)]
        for state in cards:
            player.move(state, Zone.LIBRARY)
        game.shuffle_library(player)
        ctx.moved.setdefault("shuffled", []).extend(cards)

    return step


_MILL_RE = re.compile(
    r"^(?P<who>target player|target opponent|you|that player) mills? "
    r"(?P<n>a|one|two|three|four|five|\d+) cards?$",
    re.IGNORECASE,
)


def _mill_step(match: re.Match[str]) -> Step | None:
    count = 1 if match.group("n").lower() in ("a", "one") else parse_count(match.group("n"))
    who = match.group("who").lower()
    if count is None:
        return None

    def step(game: "Game", obj: Any, ctx: _Ctx) -> None:
        player = _actor_for(game, obj, ctx, who)
        if player is None:
            return
        ctx.actor = player
        ctx.moved.setdefault("milled", []).extend(_mill(game, player, count))

    return step


_IF_NAMED_MILLED_RE = re.compile(
    r"^if a card with the chosen name was milled this way, you gain life equal to its mana value$",
    re.IGNORECASE,
)


def _if_named_milled(_match: re.Match[str]) -> Step:
    def step(game: "Game", obj: Any, ctx: _Ctx) -> None:
        for card in ctx.moved.get("milled", ()):
            if card.name == ctx.name:
                value = int(game.characteristics_of(card).mana_value or 0)
                if value > 0:
                    game.gain_life(ctx.controller, value)
                return

    return step


_DISCARD_RANDOM_RE = re.compile(r"^discard (?P<n>a|one|two|three|\d+) cards? at random$", re.I)


def _discard_random(match: re.Match[str]) -> Step | None:
    count = 1 if match.group("n").lower() in ("a", "one") else parse_count(match.group("n"))
    if count is None:
        return None

    def step(game: "Game", obj: Any, ctx: _Ctx) -> None:
        # CR 701.9b: a random discard asks nobody; the seed keeps a scenario replayable.
        hand = list(ctx.controller.hand)
        rng = Random(f"{game.shuffle_seed}:{game.shuffles_performed}:discard-at-random")  # noqa: S311
        rng.shuffle(hand)
        game.shuffles_performed += 1
        ctx.moved.setdefault("discarded", []).extend(
            game.discard_cards(ctx.controller.username, hand[:count], source=_source_name(obj))
        )

    return step


_IF_DISCARDED_DAMAGE_RE = re.compile(
    r"^if you discard an? (?P<q>[a-z-]+) card this way, (?P<src>.+?) deals damage equal to "
    r"that card's (?P<stat>power|toughness|mana value) to (?P<to>target [a-z ]+)$",
    re.IGNORECASE,
)


def _if_discarded_damage(match: re.Match[str]) -> Step | None:
    quality = match.group("q")
    if not _card_description_is_readable(quality) or not profile_for_text(match.group("to")).understood:
        return None
    matcher = _quality_matcher(quality)
    stat = match.group("stat").lower().replace(" ", "_")

    def step(game: "Game", obj: Any, ctx: _Ctx) -> None:
        card = next((c for c in ctx.moved.get("discarded", ()) if matcher(c)), None)
        if card is None:
            return
        amount = int(getattr(game.characteristics_of(card), stat, 0) or 0)
        source = _source_of(obj) or (obj.source(game) if hasattr(obj, "source") else None)
        for target in game.resolve_targets(obj):
            if isinstance(target, Player) or (
                isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
            ):
                if amount > 0:
                    game.deal_damage(target, amount, source=source)
                return

    return step


_GAIN_THAT_MUCH_RE = re.compile(r"^you (?P<verb>gain|lose) that much life$", re.IGNORECASE)


def _that_much_life(match: re.Match[str]) -> Step:
    gains = match.group("verb").lower() == "gain"

    def step(game: "Game", obj: Any, ctx: _Ctx) -> None:
        if ctx.last_amount > 0:
            (game.gain_life if gains else game.lose_life)(ctx.controller, ctx.last_amount)

    return step


_CHOOSE_PERMANENT_RE = re.compile(
    r"^choose an? (?P<q>[a-z' -]+?) you control$", re.IGNORECASE
)


def _choose_permanent(match: re.Match[str]) -> Step | None:
    """ "Choose a planeswalker you control." - the controller picks one (CR 608.2d)."""
    quality = match.group("q").strip().lower()
    if not _card_description_is_readable(quality):
        return None
    matcher = _quality_matcher(quality)

    def step(game: "Game", obj: Any, ctx: _Ctx) -> None:
        candidates = [p for p in game.permanents_controlled_by(ctx.controller.username) if matcher(p)]
        ctx.chosen = None
        if not candidates:
            return
        chosen = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=ctx.controller.username,
                prompt=f"choose a {quality} you control",
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
        ctx.chosen = next((c for c in candidates if c.id in chosen), None)

    return step


_PUT_COUNTERS_ON_IT_RE = re.compile(
    r"^put (?P<n>a|one|two|three|four|\d+) (?P<kind>[a-z+/0-9-]+) counters? on it$", re.IGNORECASE
)


def _put_counters_on_chosen(match: re.Match[str]) -> Step | None:
    count = 1 if match.group("n").lower() in ("a", "one") else parse_count(match.group("n"))
    if count is None:
        return None
    kind = match.group("kind").lower()

    def step(game: "Game", obj: Any, ctx: _Ctx) -> None:
        if ctx.chosen is not None and ctx.chosen.zone is Zone.BATTLEFIELD:
            game.add_counters(ctx.chosen, kind, count)

    return step


_X_CLAUSE_RE = re.compile(
    r"^(?:you )?(?P<verb>draw|gain|lose)s? x (?P<what>cards?|life)$", re.IGNORECASE
)


def _x_clause(match: re.Match[str]) -> Step | None:
    verb, what = match.group("verb").lower(), match.group("what").lower()
    if (verb == "draw") != what.startswith("card"):
        return None

    def step(game: "Game", obj: Any, ctx: _Ctx) -> None:
        if ctx.x <= 0:
            return
        if verb == "draw":
            game.draw_cards(ctx.controller.username, ctx.x)
        elif verb == "gain":
            game.gain_life(ctx.controller, ctx.x)
        else:
            game.lose_life(ctx.controller, ctx.x)

    return step


_DAMAGE_ITS_CONTROLLER_RE = re.compile(
    r"^(?P<src>(?!if )[^,]+?) deals damage to that (?P<noun>[a-z ]+?)'s controller equal to "
    r"(?P<expr>.+)$",
    re.IGNORECASE,
)


def _damage_its_controller(match: re.Match[str]) -> Step | None:
    reader = recipient_amount(match.group("expr"))
    if reader is None:
        return None

    def step(game: "Game", obj: Any, ctx: _Ctx) -> None:
        if ctx.referent_controller is None:
            return
        player = game.player(ctx.referent_controller)
        amount = reader(game, obj, ctx.controller)
        if amount > 0:
            source = _source_of(obj) or (obj.source(game) if hasattr(obj, "source") else None)
            game.deal_damage(player, amount, source=source)

    return step


def _pump_source(game: "Game", obj: Any, power: int, toughness: int) -> None:
    """"This creature gets +N/+M until end of turn", read by the ordinary clause
    parsers once the numbers are written in, aimed at the object's source."""
    pump = _parse_cached(f"this creature gets {power:+d}/{toughness:+d} until end of turn.", False)
    if pump is not None:
        pump(game, obj)


_PUMP_WHERE_X_RE = re.compile(
    r"^this creature gets \+x/\+(?P<t>x|\d+) until end of turn, where x is (?P<expr>.+)$",
    re.IGNORECASE,
)


def _pump_where_x(match: re.Match[str]) -> Step | None:
    amount = _amount(match.group("expr"))
    if amount is None:
        return None
    toughness = match.group("t").lower()

    def step(game: "Game", obj: Any, ctx: _Ctx) -> None:
        n = amount(game, obj, ctx)
        if n > 0 or toughness != "x":
            _pump_source(game, obj, max(n, 0), max(n, 0) if toughness == "x" else int(toughness))

    return step


_TAP_ALL_RE = re.compile(r"^tap all untapped (?P<q>[a-z' -]+?) you control$", re.IGNORECASE)


def _tap_all(match: re.Match[str]) -> Step | None:
    quality = re.sub(r"s$", "", match.group("q").strip().lower())  # "wolf creatures"
    if not _card_description_is_readable(quality):
        return None
    matcher = _quality_matcher(quality)

    def step(game: "Game", obj: Any, ctx: _Ctx) -> None:
        tapped = []
        for permanent in list(game.permanents_controlled_by(ctx.controller.username)):
            if not permanent.tapped and matcher(game.characteristics_of(permanent)):
                if game.tap_permanent(permanent):
                    tapped.append(permanent)
        ctx.moved["tapped"] = tapped

    return step


_EACH_TAPPED_DEALS_RE = re.compile(
    r"^each (?P<noun>[a-z]+) tapped this way deals damage equal to its power to "
    r"(?P<to>target [a-z ]+)$",
    re.IGNORECASE,
)


def _target_permanent(game: "Game", obj: Any) -> CardState | None:
    return next(
        (
            t
            for t in game.resolve_targets(obj)
            if isinstance(t, CardState) and t.zone is Zone.BATTLEFIELD
        ),
        None,
    )


def _each_tapped_deals(match: re.Match[str]) -> Step | None:
    if not profile_for_text(match.group("to")).understood:
        return None

    def step(game: "Game", obj: Any, ctx: _Ctx) -> None:
        target = _target_permanent(game, obj)
        ctx.referent = target
        if target is None:
            return
        for source in ctx.moved.get("tapped", ()):
            power = game.power_of(source) if source.zone is Zone.BATTLEFIELD else 0
            if power and power > 0 and target.zone is Zone.BATTLEFIELD:
                game.deal_damage(target, power, source=source)

    return step


_THAT_DEALS_DIVIDED_RE = re.compile(
    r"^that (?P<noun>[a-z]+) deals damage equal to its power divided as its controller chooses "
    r"among any number of those (?P<those>[a-z]+)$",
    re.IGNORECASE,
)


def _that_deals_divided(_match: re.Match[str]) -> Step:
    """The target's controller divides its power among the tapped creatures
    (CR 608.2d): every share but the last is asked, the last takes the rest."""

    def step(game: "Game", obj: Any, ctx: _Ctx) -> None:
        creature = ctx.referent
        if creature is None or creature.zone is not Zone.BATTLEFIELD:
            return
        power = int(game.power_of(creature) or 0)
        recipients = [c for c in ctx.moved.get("tapped", ()) if c.zone is Zone.BATTLEFIELD]
        if power <= 0 or not recipients:
            return
        chooser = game.controller_of(creature).username
        remaining = power
        shares: list[tuple[CardState, int]] = []
        for index, recipient in enumerate(recipients):
            if index == len(recipients) - 1:
                share = remaining
            else:
                share = int(
                    game.ask(
                        Decision(
                            kind=DecisionKind.CHOOSE_AN_AMOUNT,
                            player=chooser,
                            prompt=f"choose how much of {creature.name}'s damage {recipient.name} takes",
                            source=_source_name(obj),
                            source_id=source_id_of(obj),
                            amount=remaining,
                        )
                    )
                )
                share = min(max(share, 0), remaining)
            remaining -= share
            shares.append((recipient, share))
        for recipient, share in shares:
            if share > 0 and recipient.zone is Zone.BATTLEFIELD:
                game.deal_damage(recipient, share, source=creature)

    return step


_PHASE_OUT_UNTIL_RE = re.compile(
    r"^those creatures phase out until this (?P<noun>[a-z]+) leaves the battlefield$", re.IGNORECASE
)


def _phase_out_until_leaves(_match: re.Match[str]) -> Step:
    """CR 702.26a-b: the creatures phase out and stay out (they do not phase in at
    their controller's untap step) until the source leaves the battlefield
    (CR 610.3): three sibling delayed triggers watch for that."""

    def step(game: "Game", obj: Any, ctx: _Ctx) -> None:
        source = obj.source(game) if hasattr(obj, "source") else None
        if not isinstance(source, CardState) or source.zone is not Zone.BATTLEFIELD:
            return  # CR 610.3b: the duration is already over, so nothing phases out
        held_by = f"until:{source.id}"
        phased: list[CardState] = []
        for permanent in [
            p for p in game.battlefield if Type.CREATURE in game.characteristics_of(p).types
        ]:
            game.phase_out(permanent)
            if permanent in game.phased_out:
                permanent.phased_out_under = held_by
                phased.append(permanent)
        ctx.moved["phased"] = phased
        if not phased:
            return
        effect = PhaseInEach(ids=tuple(p.id for p in phased), held_by=held_by)
        text = f"When {source.name} leaves the battlefield, those creatures phase in."
        siblings = [
            game.create_delayed_trigger(
                DelayedTrigger(
                    text=text,
                    event=event,
                    controller=ctx.controller.username,
                    source_id=source.id,
                    source_name=source.name,
                    subject_id=source.id,
                    effect=effect,
                )
            )
            for event in (
                TriggerEvent.DIES,
                TriggerEvent.LEAVES_BATTLEFIELD_TO_EXILE,
                TriggerEvent.LEAVES_BATTLEFIELD_TO_HAND,
            )
        ]
        for trigger in siblings:
            trigger.sibling_ids = tuple(o.id for o in siblings if o is not trigger)

    return step


_COUNTERS_FOR_EACH_PHASED_RE = re.compile(
    r"^put (?P<n>a|one|two|three|\d+) (?P<kind>[a-z+/0-9-]+) counters? on this (?P<noun>[a-z]+) "
    r"for each creature that phased out this way$",
    re.IGNORECASE,
)


def _counters_for_each_phased(match: re.Match[str]) -> Step | None:
    unit = 1 if match.group("n").lower() in ("a", "one") else parse_count(match.group("n"))
    if unit is None:
        return None
    kind = match.group("kind").lower()

    def step(game: "Game", obj: Any, ctx: _Ctx) -> None:
        source = obj.source(game) if hasattr(obj, "source") else None
        n = unit * len(ctx.moved.get("phased", ()))
        if isinstance(source, CardState) and source.zone is Zone.BATTLEFIELD and n > 0:
            game.add_counters(source, kind, n)

    return step


_RETURN_ALL_RE = re.compile(
    r"^return each (?P<q>[a-z' -]+?) cards? from your graveyard to the battlefield"
    r"(?P<tapped> tapped)?(?: with an? (?P<kind>[a-z]+) counter on (?:it|them))?$",
    re.IGNORECASE,
)


def _return_all(match: re.Match[str]) -> Step | None:
    """CR 400.7 / CR 614.1c: every matching card in the controller's graveyard enters
    together, each with the counter."""
    quality = match.group("q").strip().lower()
    if not _card_description_is_readable(quality):
        return None
    matcher = _quality_matcher(quality)
    tapped = match.group("tapped") is not None
    kind = (match.group("kind") or "").lower() or None

    def step(game: "Game", obj: Any, ctx: _Ctx) -> None:
        returned: list[CardState] = []
        with game.entering_together():  # CR 603.6a: one arrival, together
            for card in [c for c in ctx.controller.graveyard if matcher(c)]:
                permanent = game.put_onto_battlefield(card, ctx.controller.username, tapped=tapped)
                if permanent.zone is Zone.BATTLEFIELD:
                    if kind is not None:
                        game.add_counters(permanent, kind, 1)
                    returned.append(permanent)
        ctx.moved["returned"] = returned

    return step


_THOSE_ARE_RE = re.compile(
    r"^those creatures are (?P<types>[A-Za-z][A-Za-z' ,-]*?) in addition to their other types$",
    re.IGNORECASE,
)


def _those_are(match: re.Match[str]) -> Step | None:
    words = [w.strip() for w in re.split(r",| and ", match.group("types")) if w.strip()]
    found = [canonical_subtype(word) for word in words]  # "Vampires" -> "vampire"
    if not found or any(subtype is None for subtype in found):
        return None
    subtypes = [subtype.title() for subtype in found if subtype is not None]

    def step(game: "Game", obj: Any, ctx: _Ctx) -> None:
        store = continuous_effects(game)
        timestamp = store.tick()
        for permanent in ctx.moved.get("returned", ()):
            if permanent.zone is not Zone.BATTLEFIELD:
                continue
            for subtype in subtypes:
                store.add(
                    ContinuousEffect(
                        description=f"{_source_name(obj)}: {permanent.name} is a {subtype}",
                        layer=Layer.TYPE,
                        timestamp=timestamp,
                        selector=only_this_incarnation(permanent, permanent.zone_change_stamp),
                        modification=add_subtype(subtype),
                    ),
                    game,
                )

    return step


@dataclass(frozen=True)
class _Instead:
    """A clause that replaces the clause before it when its condition holds
    (CR 608.2c: "instead" modifies the earlier instruction)."""

    condition: Callable[["Game", Any, _Ctx], bool]
    replacement: Step


_IF_SACRIFICED_INSTEAD_RE = re.compile(
    r"^if you sacrificed an? (?P<q>[a-z-]+) this way, create a number of (?P<token>[A-Za-z ]+?) "
    r"tokens equal to its (?P<stat>power|toughness) instead$",
    re.IGNORECASE,
)


def _if_sacrificed_instead(match: re.Match[str]) -> _Instead | None:
    from ..models.token import PREDEFINED, create_tokens

    quality = match.group("q").lower()
    definition = PREDEFINED.get(match.group("token").strip())
    if definition is None:
        return None
    stat = match.group("stat").lower()

    def sacrificed_index(obj: Any) -> int | None:
        types = getattr(obj, "cost_sacrificed_types", ())
        return next((i for i, words in enumerate(types) if quality in words), None)

    def condition(_game: "Game", obj: Any, _ctx: _Ctx) -> bool:
        return sacrificed_index(obj) is not None

    def replacement(game: "Game", obj: Any, ctx: _Ctx) -> None:
        index = sacrificed_index(obj)
        if index is None:
            return
        values = obj.cost_sacrificed_powers if stat == "power" else obj.cost_sacrificed_toughnesses
        amount = int(values[index] or 0)
        if amount > 0:
            create_tokens(game, definition, ctx.controller.username, amount)

    return _Instead(condition, replacement)


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
    (_SHUFFLE_BARE_RE, _shuffle_bare_step),
    (_SEARCH_RE, _search_step),
    (_SEARCH_SAME_NAME_RE, _search_same_name_step),
    (_INVESTIGATES_RE, _investigate_step),
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
    (_COUNTER_ALL_OTHER_RE, _counter_all_other),
    (_DRAW_FOR_EACH_RE, _draw_for_each),
    (_SHUFFLE_GRAVEYARD_RE, _shuffle_graveyard),
    (_MILL_RE, _mill_step),
    (_IF_NAMED_MILLED_RE, _if_named_milled),
    (_DISCARD_RANDOM_RE, _discard_random),
    (_IF_DISCARDED_DAMAGE_RE, _if_discarded_damage),
    (_GAIN_THAT_MUCH_RE, _that_much_life),
    (_CHOOSE_PERMANENT_RE, _choose_permanent),
    (_PUT_COUNTERS_ON_IT_RE, _put_counters_on_chosen),
    (_X_CLAUSE_RE, _x_clause),
    (_DAMAGE_ITS_CONTROLLER_RE, _damage_its_controller),
    (_PUMP_WHERE_X_RE, _pump_where_x),
    (_TAP_ALL_RE, _tap_all),
    (_EACH_TAPPED_DEALS_RE, _each_tapped_deals),
    (_THAT_DEALS_DIVIDED_RE, _that_deals_divided),
    (_PHASE_OUT_UNTIL_RE, _phase_out_until_leaves),
    (_COUNTERS_FOR_EACH_PHASED_RE, _counters_for_each_phased),
    (_RETURN_ALL_RE, _return_all),
    (_THOSE_ARE_RE, _those_are),
    (_IF_SACRIFICED_INSTEAD_RE, _if_sacrificed_instead),
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
    protected = _SAME_NAME_RE.sub(
        rf"\1{_NO_SPLIT}exile them", re.sub(r"^then ", "", sentence.strip().rstrip("."), flags=re.I)
    )
    parts = [p.strip() for p in _CLAUSE_SPLIT_RE.split(protected)]
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


def _either(instead: "_Instead", base: Step) -> Step:
    def step(game: "Game", obj: Any, ctx: _Ctx) -> None:
        if instead.condition(game, obj, ctx):
            instead.replacement(game, obj, ctx)
        else:
            base(game, obj, ctx)

    return step


def _steps_of(clauses: list[str], for_spell: bool) -> tuple[list[Step], int] | None:
    """One step per clause, and how many of them this module's own readers
    built; `None` when a clause nothing reads is left over."""
    steps: list[Step] = []
    mine = 0
    for clause in clauses:
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
        if isinstance(step, _Instead):
            if not steps:
                return None
            steps[-1] = _either(step, steps[-1])
            continue
        steps.append(step)
    return steps, mine


def _plan_uncached(text: str, for_spell: bool) -> _Plan | None:
    clauses: list[str] = []
    each_player = False
    for sentence in _plain_resolution_sentences(_strip_non_effect_preamble(text)):
        if re.match(r"^each player reveals", sentence.strip(), re.IGNORECASE):
            each_player = True
        clauses.extend(_clauses(sentence))
    read = _steps_of(clauses, for_spell)
    if read is None or read[1] == 0:
        return None
    return _Plan(tuple(read[0]), each_player)


def _plain_step(effect: Any) -> Step:
    return lambda game, obj, ctx: effect(game, obj)


# --------------------------------------------------------------------------
# "For each <permanent> <verb> this way, its controller ..." - the R1 ledger
# --------------------------------------------------------------------------

_FOR_EACH_RE = re.compile(r"^for each (?P<each>.+? this way), (?P<rest>.+)$", re.IGNORECASE)
_MULTI_TARGET_FIRST_RE = re.compile(
    r"^(?P<lead>for each player, )?(?P<verb>exile|destroy) "
    r"(?P<phrase>(?:up to |any number of |x )?[a-z ]*?target .+)$",
    re.IGNORECASE,
)


def _multi_target_first(text: str) -> Callable[["Game", Any], None] | None:
    """ "Exile up to one target artifact, up to one target creature, ... and/or
    up to one target land." - every target the announcement chose that is still
    on the battlefield (CR 608.2b) is exiled or destroyed; each target
    requirement is its own "up to" choice (CR 115.6)."""
    match = _MULTI_TARGET_FIRST_RE.fullmatch(text.strip().rstrip("."))
    if match is None:
        return None
    profile = profile_for_text(match.group(0))
    if not profile.understood or not profile.requirements:
        return None
    if len(profile.requirements) < 2 and not match.group("lead"):
        return None  # one ordinary target is the clause parsers' own
    if any(r.allows_players or r.zones != frozenset({Zone.BATTLEFIELD}) for r in profile.requirements):
        return None
    destroy = match.group("verb").lower() == "destroy"

    def effect(game: "Game", obj: Any) -> None:
        for target in list(game.resolve_targets(obj)):
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD:
                (game.destroy if destroy else game.exile_permanent)(target)

    return effect


_EXILE_GRAVEYARD_OTHER_THAN_RE = re.compile(
    r"^exile all cards from target (?:player|opponent)'s graveyard"
    r"(?: other than (?P<q>[a-z ]+?) cards?)?$",
    re.IGNORECASE,
)


def _exile_graveyard_other_than(text: str) -> Callable[["Game", Any], None] | None:
    """ "Exile all cards from target player's graveyard other than basic land
    cards." (CR 406.2, CR 701.13a): every card of the targeted player's
    graveyard except the excluded quality."""
    match = _EXILE_GRAVEYARD_OTHER_THAN_RE.fullmatch(text.strip().rstrip("."))
    if match is None:
        return None
    quality = (match.group("q") or "").strip()
    if quality and not _card_description_is_readable(quality):
        return None
    excluded = _quality_matcher(quality) if quality else None
    if not _targets_understood(
        "target player's graveyard", allow_player_targets=True, count_agnostic=True
    ):
        return None

    def effect(game: "Game", obj: Any) -> None:
        for target in game.resolve_targets(obj):
            if isinstance(target, Player):
                for state in list(target.graveyard):
                    if excluded is None or not excluded(state):
                        game.exile_permanent(state)

    return effect


_EXILE_TARGET_AND_SAME_NAME_RE = re.compile(
    r"^(?P<verb>exile|destroy) target (?P<desc>[a-z ]+?) and all other (?P<plural>[a-z ]+?) "
    r"its controller controls with the same name as that (?P<noun>[a-z ]+)$",
    re.IGNORECASE,
)


def _target_and_same_name_first(text: str) -> Callable[["Game", Any], None] | None:
    """ "Exile target creature and all other creatures its controller controls
    with the same name as that creature." - the target and every other
    permanent of that quality its controller has under the same name, together
    (CR 608.2b: a target that is gone leaves the rest of the sentence unread)."""
    match = _EXILE_TARGET_AND_SAME_NAME_RE.fullmatch(text.strip().rstrip("."))
    if match is None:
        return None
    desc = match.group("desc").strip().lower()
    plural = match.group("plural").strip().lower()
    if not _card_description_is_readable(desc) or not _card_description_is_readable(
        plural.removesuffix("s")
    ):
        return None
    if not profile_for_text(f"target {desc}").understood:
        return None
    wanted = _quality_matcher(plural.removesuffix("s"))
    destroy = match.group("verb").lower() == "destroy"

    def effect(game: "Game", obj: Any) -> None:
        target = next(
            (
                t
                for t in game.resolve_targets(obj)
                if isinstance(t, CardState) and t.zone is Zone.BATTLEFIELD
            ),
            None,
        )
        if target is None:
            return
        owner = game.controller_of(target).username
        group = [target] + [
            p
            for p in game.permanents_controlled_by(owner)
            if p.id != target.id and p.name == target.name and wanted(p)
        ]
        for permanent in group:
            if permanent.zone is Zone.BATTLEFIELD:
                (game.destroy if destroy else game.exile_permanent)(permanent)

    return effect


def _first_instruction_of(text: str, for_spell: bool) -> Callable[["Game", Any], None] | None:
    return (
        _r1_first_instruction(text, for_spell)
        or _multi_target_first(text)
        or _exile_graveyard_other_than(text)
        or _target_and_same_name_first(text)
    )


_TRAILING_EACH_RE = re.compile(
    r"^(?P<rest>.+?) for each (?P<each>(?:non)?(?:token )?[a-z' ,-]+? this way)$", re.IGNORECASE
)
_IF_ANY_RE = re.compile(
    r"^(?P<rest>.+?) if at least one (?P<each>[a-z' ,-]+? (?:was|were) [a-z ]+? this way)$",
    re.IGNORECASE,
)
_IF_LEADING_RE = re.compile(
    r"^if (?:an?|that|at least one) (?P<each>[a-z' ,-]+? (?:was|were|is|are) [a-z ]+? this way), "
    r"(?P<rest>.+)$",
    re.IGNORECASE,
)
_WHERE_X_RE = re.compile(r"^(?P<rest>.+?),? where x is (?P<expr>.+ this way)$", re.IGNORECASE)
_WHERE_X_OBJECTS_RE = re.compile(
    r"\b(?P<noun>(?:(?!among\b)[a-z-]+ )?(?:cards?|permanents?|creatures?)) "
    r"(?P<verb>exiled|destroyed|sacrificed|milled|discarded) this way$",
    re.IGNORECASE,
)
_TOKEN_PREFIX_RE = re.compile(r"^(?P<tok>nontoken|token) (?P<rest>.+)$", re.IGNORECASE)


@dataclass(frozen=True)
class _EachPlan:
    first: Callable[["Game", Any], None]
    pre: tuple[Step, ...]  # sentences between the first instruction and the payoff
    objects: Any  # ep02_r1_this_way_counts._Objects
    token_wanted: bool | None
    mode: str  # "each" per object, "any" once if some moved, "always" once
    x_amount: Amount | None  # ", where X is ..." read once before the steps
    inner: tuple[Step, ...]
    post: tuple[Step, ...]


def _ledger_sentence(sentences: list[str]) -> tuple[int, str, str, str, Amount | None] | None:
    """`(index, mode, object phrase, payoff clauses text, X amount)` of the first
    sentence that counts what an earlier instruction really did."""
    for index, sentence in enumerate(sentences):
        if index == 0 or " this way" not in sentence.lower():
            continue
        if (m := _FOR_EACH_RE.fullmatch(sentence)) is not None:
            return index, "each", m.group("each"), m.group("rest"), None
        if (m := _IF_LEADING_RE.fullmatch(sentence)) is not None:
            return index, "any", m.group("each"), m.group("rest"), None
        if (m := _IF_ANY_RE.fullmatch(sentence)) is not None:
            return index, "any", m.group("each"), m.group("rest"), None
        if (m := _WHERE_X_RE.fullmatch(sentence)) is not None:
            amount = _amount(m.group("expr"))
            objects = _WHERE_X_OBJECTS_RE.search(m.group("expr"))
            if amount is None or objects is None:
                continue
            each = f"{objects.group('noun')} {objects.group('verb')} this way"
            return index, "always", each, m.group("rest"), amount
        if (m := _TRAILING_EACH_RE.fullmatch(sentence)) is not None:
            return index, "each", m.group("each"), m.group("rest"), None
    return None


def _each_plan_uncached(text: str, for_spell: bool) -> _EachPlan | None:
    sentences = _r1_sentences(text)
    ledger = _ledger_sentence(sentences)
    if ledger is None:
        return None
    index, mode, each, rest, x_amount = ledger
    each = re.sub(r" (?:was|were|is|are) ", " ", each)
    token_match = _TOKEN_PREFIX_RE.fullmatch(each)
    token_wanted = None
    if token_match is not None:
        token_wanted = token_match.group("tok").lower() == "token"
        each = token_match.group("rest")
    objects = _r1_objects(each)
    if objects is None:
        return None
    first = None
    pre: tuple[Step, ...] = ()
    for cut in range(index, 0, -1):
        first = _first_instruction_of(". ".join(sentences[:cut]) + ".", for_spell)
        if first is None:
            continue
        between = _steps_of(
            [c for sentence in sentences[cut:index] for c in _clauses(sentence)], for_spell
        )
        if between is not None:
            pre = tuple(between[0])
            break
        first = None
    if first is None:
        return None
    inner = _steps_of(_clauses(rest), for_spell)
    post_clauses = [c for sentence in sentences[index + 1 :] for c in _clauses(sentence)]
    post = _steps_of(post_clauses, for_spell)
    if inner is None or post is None:
        return None
    if mode == "each" and inner[1] + post[1] == 0:
        return None
    return _EachPlan(
        first, pre, objects, token_wanted, mode, x_amount, tuple(inner[0]), tuple(post[0])
    )


@functools.lru_cache(maxsize=1024)
def _each_plan(text: str, for_spell: bool) -> _EachPlan | None:
    _READING.append(True)
    try:
        return _each_plan_uncached(text, for_spell)
    finally:
        _READING.pop()


def _derived(base: _Ctx, player: Player) -> _Ctx:
    """A fresh context for `player`'s own share of a payoff, keeping what the
    earlier sentences chose (a name, a type, a permanent)."""
    return dataclasses.replace(
        base, actor=player, revealed=[], stoppers=[], disposed=set(), moved={}
    )


def _for_each_effect(text: str, for_spell: bool) -> Any:
    if _r1_plan(text, for_spell) is not None:
        return None  # the R1 payoffs read this text; one reader per text
    plan = _each_plan(text, for_spell)
    if plan is None:
        return None
    verb = _r1_verbs[plan.objects.verb]
    moved_key = "exile" if verb.destination is Zone.EXILE else "graveyard"

    def effect(game: "Game", obj: Any) -> None:
        marks = _r1_snapshot(game, verb.sources)
        plan.first(game, obj)
        controller = game.controller_of(obj)
        moved = [
            entry
            for entry in plan.objects.matching(_r1_affected(game, marks, verb), controller.username)
            if plan.token_wanted is None or is_token(entry.card) is plan.token_wanted
        ]
        base = _Ctx(actor=controller, controller=controller)
        for step in plan.pre:
            step(game, obj, base)
        if plan.mode != "each":
            if plan.mode == "any" and not moved:
                return
            ctx = _derived(base, controller)
            ctx.moved[moved_key] = [entry.card for entry in moved]
            if moved:
                ctx.referent, ctx.referent_chars = moved[0].card, moved[0].characteristics
                ctx.referent_controller = moved[0].controller
            if plan.x_amount is not None:
                ctx.x = plan.x_amount(game, obj, ctx)
            for step in plan.inner:
                step(game, obj, ctx)
            return
        contexts: dict[str, _Ctx] = {}
        order = _players_in_apnap_order(game)
        for player in order:
            ctx = _derived(base, player)
            for entry in (e for e in moved if e.controller == player.username):
                contexts[player.username] = ctx
                ctx.referent, ctx.referent_chars = entry.card, entry.characteristics
                ctx.referent_controller = entry.controller
                for step in plan.inner:
                    step(game, obj, ctx)
        for player in order:
            ctx = contexts.get(player.username)
            if ctx is not None:
                ctx.actor = player
                for step in plan.post:
                    step(game, obj, ctx)

    return effect


def _gate(text: str) -> bool:
    lowered = text.lower()
    return (
        "this way" in lowered
        or "reveals cards from the top" in lowered
        or "cards that player owns in exile" in lowered
        or "those creatures are " in lowered
    )


def _effect(text: str, for_spell: bool) -> Any:
    if _READING or not _gate(text):
        return None
    plan = _plan(text, for_spell)
    if plan is None:
        return _for_each_effect(text, for_spell)

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
