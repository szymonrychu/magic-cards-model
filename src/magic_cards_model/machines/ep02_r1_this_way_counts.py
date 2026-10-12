"""EP-02 R1 T2: the "affected this way" count - a payoff sentence that counts
what the instruction before it really moved.

    Destroy all creatures. You gain 1 life for each creature destroyed this way.
    Destroy any number of target creatures. For each creature destroyed this
    way, its controller creates a 4/4 red Dragon creature token with flying.
    Target player mills four cards. You draw a card for each creature card put
    into their graveyard this way.

CR 608.2c: the instructions of a spell or ability are followed in order and
"later text on the card may modify the meaning of earlier text", so "this way"
is the earlier instruction's own outcome - what it actually did, not what it
was aimed at. CR 701.8a defines destroying as moving the permanent from the
battlefield to its owner's graveyard, so an indestructible, regenerated or
replaced permanent was not destroyed this way. CR 701.17a / CR 701.17c: a
milled card is found in the zone it moved to. CR 608.2h: what a
permanent was (its controller, its types, its toughness) is read as it last
existed on the battlefield (last known information).

The reader is the *ledger*: `snapshot` notes every card in the zones a
payoff's verb can start from (id, zone-change stamp, controller, owner, and a
permanent's characteristics), the first instruction runs, and `affected` lists
the cards whose stamp moved to the zone the verb names. A payoff is then a
count over that list (type/colour quality, "you controlled", destination
owner, distinct opponents), a per-object stat (its toughness, the power of the
card returned), a shortfall against a number ("fewer than two cards were
discarded this way") or the greatest per-player count - applied to a
recipient (you, "its controller" per object, a targeted player, each player).

Registered as one SPELL_TEXT and one ABILITY_TEXT rung; the cheap lowercase
gate (`" this way"`) and the memoised parsers keep it inside the classify
budget.
"""

import functools
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID

from ..models.card_state import CardState
from ..models.player import Player
from ..models.token import create_tokens
from ..models.zone import Zone
from ..numbers import parse_count
from .decisions import Decision, DecisionKind, source_id_of
from .effects._chains import ABILITY_TEXT, FORWARD, MIXED_CLAUSE, SPELL_TEXT
from .effects._common import (
    _TOKEN_CLAUSE_RE,
    _card_description_is_readable,
    _quality_matcher,
    _targets_understood,
)
from .effects.dispatch import _ability_effect_or_notice, _spell_effect_or_notice
from .effects.text import _plain_resolution_sentences, _strip_non_effect_preamble
from .effects.tokens import (
    PREDEFINED,
    _is_notice_only,
    _parse_generic_token_descriptor,
)

if TYPE_CHECKING:
    from ..models.game import Game

# --------------------------------------------------------------------------
# The ledger
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class _Verb:
    """What "destroyed", "exiled", "returned to ... hand", "milled" ... name:
    the zones a card starts from and the zone it must end in."""

    sources: frozenset[Zone]
    destination: Zone


_BF = Zone.BATTLEFIELD
_VERBS: dict[str, _Verb] = {
    "destroyed": _Verb(frozenset({_BF}), Zone.GRAVEYARD),  # CR 701.8a
    "sacrificed": _Verb(frozenset({_BF}), Zone.GRAVEYARD),  # CR 701.21a
    "put into a graveyard": _Verb(
        frozenset({_BF, Zone.LIBRARY, Zone.HAND, Zone.EXILE}), Zone.GRAVEYARD
    ),
    "exiled": _Verb(frozenset({_BF, Zone.GRAVEYARD, Zone.LIBRARY, Zone.HAND}), Zone.EXILE),
    "returned": _Verb(frozenset({_BF, Zone.GRAVEYARD, Zone.EXILE}), Zone.HAND),
    "milled": _Verb(frozenset({Zone.LIBRARY}), Zone.GRAVEYARD),  # CR 701.17a
    "discarded": _Verb(frozenset({Zone.HAND}), Zone.GRAVEYARD),  # CR 701.9a
}


@dataclass(frozen=True)
class _Mark:
    zone: Zone
    stamp: UUID | None
    controller: str
    owner: str | None
    characteristics: Any  # a permanent's, as it stood before it left


@dataclass(frozen=True)
class Affected:
    """A card an instruction moved: where it went, who controlled it and what
    it was while it was on the battlefield (CR 608.2h last known information)."""

    card: CardState
    source: Zone
    controller: str
    owner: str | None
    characteristics: Any


def snapshot(game: "Game", zones: frozenset[Zone]) -> dict[UUID, _Mark]:
    """Every card now in `zones`, by id - the "before" half of the ledger."""
    marks: dict[UUID, _Mark] = {}
    for state in game.battlefield if _BF in zones else ():
        marks[state.id] = _Mark(
            _BF,
            state.zone_change_stamp,
            game.controller_of(state).username,
            state.owner,
            game.characteristics_of(state),
        )
    for player in game.players:
        for zone in zones - {_BF, Zone.EXILE}:
            for state in player.zones.get(zone, ()):
                marks[state.id] = _Mark(
                    zone, state.zone_change_stamp, player.username, state.owner, None
                )
    if Zone.EXILE in zones:
        for state in game.exile:
            marks[state.id] = _Mark(
                Zone.EXILE, state.zone_change_stamp, state.owner or "", state.owner, None
            )
    return marks


def affected(game: "Game", marks: dict[UUID, _Mark], verb: _Verb) -> list[Affected]:
    """The cards in `marks` that `verb` moved since the snapshot: their stamp
    changed and they now sit in the verb's destination zone."""
    moved: list[Affected] = []
    for card_id, mark in marks.items():
        if mark.zone not in verb.sources:
            continue
        card = game.find_by_id(card_id)
        if (
            card is None
            or card.zone_change_stamp == mark.stamp
            or card.zone is not verb.destination
        ):
            continue
        moved.append(
            Affected(
                card,
                mark.zone,
                mark.controller,
                mark.owner,
                mark.characteristics or game.characteristics_of(card),
            )
        )
    return moved


# --------------------------------------------------------------------------
# Reading a payoff sentence
# --------------------------------------------------------------------------

_VERB_PHRASE = (
    r"(?P<verb>destroyed|exiled|sacrificed|milled|discarded"
    r"|returned(?: to (?P<rdest>your|its owner's|their owners'|a|their) hands?)?"
    r"|put into (?P<gy>a|your|their|its owner's|that player's|an opponent's) graveyard)"
)

#: "creature card put into their graveyard this way", "creatures you
#: controlled that were destroyed this way", "opponent who controlled a
#: creature returned this way".
_OBJECTS_RE = re.compile(
    r"^(?:the number of )?(?:(?P<opp>opponent) who controlled an? )?"
    r"(?P<noun>[a-z][a-z' ,-]*?)(?P<you> you controlled)?(?: that were)? "
    + _VERB_PHRASE
    + r" this way$",
    re.IGNORECASE,
)

#: "the power of the card returned this way", "its toughness".
_STAT_OF_RE = re.compile(
    r"^the (?P<stat>power|toughness|mana value) of the (?P<noun>[a-z' ,-]+?) "
    + _VERB_PHRASE
    + r" this way$",
    re.IGNORECASE,
)
_GREATEST_RE = re.compile(
    r"^the greatest number of cards a player (?P<verb>discarded|exiled|milled) this way$",
    re.IGNORECASE,
)
_ITS_STAT_RE = re.compile(r"^its (?P<stat>power|toughness|mana value)$", re.IGNORECASE)

_ALL_NOUNS = frozenset({"permanent", "card", "object", "thing"})


def _singular(noun: str) -> str:
    words = noun.strip().lower().split()
    if words and words[-1] == "cards":
        words[-1] = "card"
    elif words and words[-1].endswith("s") and not words[-1].endswith(("ss", "us")):
        words[-1] = words[-1][:-1]
    return " ".join(words)


def _verb_key(match: re.Match[str]) -> str:
    verb = match.group("verb").lower()
    return "put into a graveyard" if verb.startswith("put into") else verb.split()[0]


@dataclass(frozen=True)
class _Objects:
    """The objects a payoff counts: a verb and a quality, narrowed to what
    "you controlled" / "your graveyard" / "your hand" say."""

    verb: str
    quality: Callable[[Any], bool] | None
    yours_before: bool = False
    dest_yours: bool = False
    dest_not_yours: bool = False
    opponents: bool = False

    def matching(self, moved: list[Affected], controller: str) -> list[Affected]:
        out: list[Affected] = []
        for entry in moved:
            if self.quality is not None and not self.quality(entry.characteristics):
                continue
            if self.yours_before and entry.controller != controller:
                continue
            if self.dest_yours and entry.owner != controller:
                continue
            if self.dest_not_yours and entry.owner == controller:
                continue
            if self.opponents and entry.controller == controller:
                continue
            out.append(entry)
        return out


def _quality_of(noun: str) -> tuple[bool, Callable[[Any], bool] | None]:
    singular = _singular(noun)
    if singular in _ALL_NOUNS:
        return True, None
    quality = singular.removesuffix(" card")
    if not _card_description_is_readable(quality):
        return False, None
    return True, _quality_matcher(quality)


def _objects(phrase: str) -> _Objects | None:
    match = _OBJECTS_RE.fullmatch(phrase.strip())
    if match is None:
        return None
    ok, quality = _quality_of(match.group("noun"))
    if not ok:
        return None
    destination = (match.group("rdest") or match.group("gy") or "").lower()
    return _Objects(
        verb=_verb_key(match),
        quality=quality,
        yours_before=match.group("you") is not None,
        dest_yours=destination == "your",
        dest_not_yours=destination == "an opponent's",
        opponents=match.group("opp") is not None,
    )


# -- the action half -------------------------------------------------------

_RECIPIENT = r"(?P<who>you|its controller|that player|target player|each player|each opponent)"
_NUM = r"(?P<k>an?|one|two|three|four|five|six|seven|eight|nine|ten|\d+)"

_LIFE_RE = re.compile(rf"^{_RECIPIENT} (?P<what>gains?|loses?) {_NUM} life$", re.IGNORECASE)
_LIFE_EQUAL_RE = re.compile(
    rf"^{_RECIPIENT} (?P<what>gains?|loses?) life equal to (?P<expr>.+)$", re.IGNORECASE
)
_DRAW_RE = re.compile(rf"^(?:then )?{_RECIPIENT}? ?draws? {_NUM} cards?$", re.IGNORECASE)
_DRAW_EQUAL_RE = re.compile(
    rf"^(?:then )?{_RECIPIENT}? ?draws? cards equal to (?P<expr>.+)$", re.IGNORECASE
)
_CREATE_RE = re.compile(rf"^(?:{_RECIPIENT} )?creates? (?P<rest>.+)$", re.IGNORECASE)
_DAMAGE_RE = re.compile(
    rf"^(?P<source>.+?) deals {_NUM} damage to (?P<tgt>each opponent)$", re.IGNORECASE
)
_COUNTERS_RE = re.compile(
    rf"^put {_NUM} (?P<kind>[+\-\d/a-z]+) counters? on (?P<tgt>this creature|this permanent)$",
    re.IGNORECASE,
)
_DAMAGE_EQUAL_RE = re.compile(
    r"^(?P<source>.+?) deals damage to (?P<tgt>any target|target [a-z ]+?) equal to (?P<expr>.+)$",
    re.IGNORECASE,
)
_SEARCH_RE = re.compile(
    r"^(?:(?:its controller|you)(?: may)? )?search(?:es)? (?:their|your) library (?P<rest>.+)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class _Payoff:
    objects: _Objects | None
    who: str  # "you", "its controller", "target player", "that player", "each player"
    run: Callable[["Game", Any, str, int], None]  # (game, obj, player, amount)
    unit: int = 1
    stat: str | None = None  # amount = sum of that stat over the objects
    shortfall: int | None = None  # amount = max(0, shortfall - count)
    greatest: bool = False  # amount = the greatest per-owner count
    per_opponent: bool = False


def _as_player(game: "Game", obj: Any, username: str) -> Any:
    return obj.model_copy(update={"controller": username}) if hasattr(obj, "ability") else obj


def _gain_or_lose(gain: bool) -> Callable[["Game", Any, str, int], None]:
    def run(game: "Game", obj: Any, player: str, amount: int) -> None:
        if amount <= 0:
            return
        (game.gain_life if gain else game.lose_life)(player, amount)

    return run


def _damage_to_target(game: "Game", obj: Any, player: str, amount: int) -> None:
    """The damage half of "<source> deals damage to any target equal to ...":
    the first chosen target that can be dealt damage (a player or a permanent
    still on the battlefield - not the graveyard card the first sentence
    named), dealt by the resolving spell or the ability's source."""
    if amount <= 0:
        return
    source = obj if isinstance(obj, CardState) else obj.source(game)
    for target in game.resolve_targets(obj):
        if isinstance(target, Player) or (
            isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD
        ):
            game.deal_damage(target, amount, source=source)
            return


def _draw(game: "Game", obj: Any, player: str, amount: int) -> None:
    if amount > 0:
        game.draw_cards(player, amount)


@functools.lru_cache(maxsize=512)
def _parse_cached(text: str, for_spell: bool) -> Any:
    effect = _spell_effect_or_notice(text) if for_spell else _ability_effect_or_notice(text)
    return None if effect is None or _is_notice_only(effect) else effect


def _text_action(
    template: str, for_spell: bool, *, repeat: bool = False
) -> Callable[["Game", Any, str, int], None] | None:
    """An action read by the ordinary clause parsers once the number is written
    in: `template` holds `{n}`. Probed with 1 now so an unreadable clause
    refuses the whole text instead of failing when it resolves."""
    if _parse_cached(template.format(n=1), for_spell) is None:
        return None

    def run(game: "Game", obj: Any, player: str, amount: int) -> None:
        if amount <= 0:
            return
        effect = _parse_cached(template.format(n=1 if repeat else amount), for_spell)
        if effect is None:
            return
        for _ in range(amount if repeat else 1):
            effect(game, _as_player(game, obj, player))

    return run


def _token_action(rest: str) -> Callable[["Game", Any, str, int], None] | None:
    """ "a 4/4 red Dragon creature token with flying", "an X/X colorless
    Phyrexian Horror artifact creature token", "two 1/1 blue Faerie creature
    tokens with flying and \"...\"" as a creator for one player. An `X/X` is
    sized by the amount (CR 608.2h: counted once, when applied)."""
    sized = re.search(r"\bx/x\b", rest, re.IGNORECASE) is not None

    def definition(amount: int) -> tuple[Any, int, bool] | None:
        text = re.sub(r"\bx/x\b", f"{amount}/{amount}", rest, flags=re.IGNORECASE)
        match = _TOKEN_CLAUSE_RE.fullmatch(text)
        if match is None:
            return None
        count = parse_count(match.group("n"))
        words = match.group("desc").strip().split()
        tail = match.group("tail")
        tapped = bool(words) and words[0].lower() == "tapped"
        if tapped:
            words = words[1:]
        if count is None or not words:
            return None
        name = " ".join(words)
        token = (
            PREDEFINED[name]
            if tail is None and name in PREDEFINED
            else _parse_generic_token_descriptor(words, tail)
        )
        return None if token is None else (token, count, tapped)

    probe = definition(1)
    if probe is None:
        return None

    def run(game: "Game", obj: Any, player: str, amount: int) -> None:
        if amount <= 0:
            return
        if sized:
            built = definition(amount)
            if built is not None:
                create_tokens(game, built[0], player, built[1], tapped=built[2])
            return
        token, per_unit, tapped = probe
        create_tokens(game, token, player, per_unit * amount, tapped=tapped)

    return run


def _action(
    action: str, for_spell: bool, name_hint: str = ""
) -> tuple[str, int, Callable[..., None]] | None:
    """`(who, per-unit multiplier, run)` for one action clause, or `None`."""
    text = action.strip()
    if (m := _LIFE_RE.fullmatch(text)) is not None:
        k = parse_count(m.group("k"))
        if k is not None:
            return (
                m.group("who").lower(),
                k,
                _gain_or_lose(m.group("what").lower().startswith("gain")),
            )
    if (m := _DRAW_RE.fullmatch(text)) is not None:
        k = parse_count(m.group("k"))
        if k is not None:
            return (m.group("who") or "").lower() or "you", k, _draw
    if (m := _CREATE_RE.fullmatch(text)) is not None:
        run = _token_action(m.group("rest"))
        if run is not None:
            return (m.group("who") or "you").lower(), 1, run
    if (m := _DAMAGE_RE.fullmatch(text)) is not None:
        k = parse_count(m.group("k"))
        run = _text_action(f"{m.group('source')} deals {{n}} damage to each opponent", for_spell)
        if k is not None and run is not None:
            return "you", k, run
    if (m := _SEARCH_RE.fullmatch(text)) is not None:
        template = "you may search your library " + m.group("rest").replace("{", "{{").replace(
            "}", "}}"
        )
        run = _text_action(template, for_spell, repeat=True)
        if run is not None:
            return "its controller", 1, run
    if (m := _COUNTERS_RE.fullmatch(text)) is not None:
        k = parse_count(m.group("k"))
        template = f"put {{n}} {m.group('kind')} counters on {m.group('tgt')}"
        run = _text_action(template, for_spell)
        if k is not None and run is not None:
            return "you", k, run
    return None


def _amount_action(action: str) -> tuple[str, str, Callable[..., None]] | None:
    """ "<who> gain(s)/lose(s) life equal to <expr>" or "<who> draw(s) cards
    equal to <expr>": `(who, expr, run)`."""
    text = action.strip()
    if (m := _LIFE_EQUAL_RE.fullmatch(text)) is not None:
        return (
            m.group("who").lower(),
            m.group("expr"),
            _gain_or_lose(m.group("what").lower().startswith("gain")),
        )
    if (m := _DRAW_EQUAL_RE.fullmatch(text)) is not None:
        return (m.group("who") or "each player").lower(), m.group("expr"), _draw
    if (m := _DAMAGE_EQUAL_RE.fullmatch(text)) is not None:
        return "you", m.group("expr"), _damage_to_target
    return None


# -- whole sentences -------------------------------------------------------

_FOR_EACH_LEAD_RE = re.compile(r"^for each (?P<each>.+? this way), (?P<action>.+)$", re.IGNORECASE)
_FOR_EACH_TRAIL_RE = re.compile(r"^(?P<action>.+?) for each (?P<each>.+? this way)$", re.IGNORECASE)
_WHERE_X_RE = re.compile(
    r"^(?P<action>.+?), where x is (?P<expr>the number of .+? this way)(?P<rest>,.*)?$",
    re.IGNORECASE,
)
_EQUAL_RE = re.compile(r"^(?P<action>.+? equal to) (?P<expr>.+)$", re.IGNORECASE)
_FEWER_RE = re.compile(
    r"^if fewer than (?P<n>\w+) (?P<noun>[a-z' ,-]+?) were "
    r"(?P<vphrase>(?:discarded|exiled|milled)) this way, "
    r"(?P<who>you) draw cards equal to the difference$",
    re.IGNORECASE,
)
_IF_A_RE = re.compile(
    r"^if (?:an?|one or more) (?P<noun>[a-z' ,-]+?) (?:is|was|are|were) "
    + _VERB_PHRASE
    + r" this way, (?P<action>.+)$",
    re.IGNORECASE,
)


def _parse_payoff(sentence: str, for_spell: bool) -> list[_Payoff] | None:
    text = sentence.strip().rstrip(".").strip()
    if (m := _FEWER_RE.fullmatch(text)) is not None:
        count = parse_count(m.group("n"))
        ok, quality = _quality_of(m.group("noun"))
        if count is None or not ok:
            return None
        objects = _Objects(m.group("vphrase").lower(), quality)
        return [_Payoff(objects, "you", _draw, shortfall=count)]
    if (m := _IF_A_RE.fullmatch(text)) is not None:
        ok, quality = _quality_of(m.group("noun"))
        equal = _amount_action(m.group("action"))
        stat = _ITS_STAT_RE.fullmatch(equal[1].strip()) if equal else None
        if not ok or equal is None or stat is None:
            return None
        objects = _Objects(_verb_key(m), quality)
        return [_Payoff(objects, equal[0], equal[2], stat=stat.group("stat").lower())]
    if (m := _FOR_EACH_LEAD_RE.fullmatch(text)) or (m := _FOR_EACH_TRAIL_RE.fullmatch(text)):
        objects = _objects(m.group("each"))
        actions = [
            part.strip()
            for part in re.split(r"\s+and\s+(?=(?:you|that player)\s)", m.group("action"))
        ]
        found = [_action(action, for_spell) for action in actions]
        if objects is None or any(part is None for part in found):
            return None
        opponent = (
            re.match(r"^(?:the number of )?opponent who", m.group("each"), re.IGNORECASE)
            is not None
        )
        return [
            _Payoff(objects, part[0], part[2], unit=part[1], per_opponent=opponent)
            for part in found
            if part is not None
        ]
    if (m := _WHERE_X_RE.fullmatch(text)) is not None:
        objects = _objects(m.group("expr"))
        if objects is None:
            return None
        created = _CREATE_RE.fullmatch(m.group("action").strip())
        if created is not None and not m.group("rest"):
            run = _token_action(created.group("rest"))
            if run is None:
                return None
            return [_Payoff(objects, (created.group("who") or "you").lower(), run)]
        template = m.group("action") + (m.group("rest") or "")
        template = re.sub(
            r"\bx\b", "{n}", template.replace("{", "{{").replace("}", "}}"), flags=re.IGNORECASE
        )
        text_run = _text_action(template, for_spell)
        if text_run is None:
            return None
        return [_Payoff(objects, "you", text_run)]
    if _EQUAL_RE.fullmatch(text) is not None:
        equal = _amount_action(text)
        if equal is None:
            return None
        who, expr, run = equal
        if (g := _GREATEST_RE.fullmatch(expr.strip())) is not None:
            return [_Payoff(_Objects(g.group("verb").lower(), None), who, run, greatest=True)]
        if (s := _STAT_OF_RE.fullmatch(expr.strip())) is not None:
            ok, quality = _quality_of(s.group("noun"))
            if not ok:
                return None
            return [
                _Payoff(_Objects(_verb_key(s), quality), who, run, stat=s.group("stat").lower())
            ]
        objects = _objects(expr)
        if objects is None:
            return None
        return [_Payoff(objects, who, run)]
    return None


# --------------------------------------------------------------------------
# Applying a payoff to the ledger
# --------------------------------------------------------------------------

_STAT_ATTRS = {"power": "power", "toughness": "toughness", "mana value": "mana_value"}


def _stat_of(entry: Affected, stat: str) -> int:
    value = getattr(entry.characteristics, _STAT_ATTRS[stat], 0)
    return int(value or 0)


def _players_in_order(game: "Game") -> list[str]:
    return [player.username for player in game.players]


def _apply(
    game: "Game",
    obj: Any,
    controller: str,
    payoff: _Payoff,
    marks: dict[UUID, _Mark],
) -> None:
    assert payoff.objects is not None
    moved = payoff.objects.matching(affected(game, marks, _VERBS[payoff.objects.verb]), controller)
    if payoff.shortfall is not None:
        payoff.run(game, obj, controller, max(0, payoff.shortfall - len(moved)))
        return
    if payoff.who == "its controller":
        # A separate recipient per object: the player who controlled it (CR 608.2h).
        by_controller: Counter[str] = Counter()
        for entry in moved:
            by_controller[entry.controller] += (
                _stat_of(entry, payoff.stat) if payoff.stat else payoff.unit
            )
        for player, amount in by_controller.items():
            payoff.run(game, obj, player, amount)
        return
    if payoff.greatest:
        per_owner = Counter(entry.owner or entry.controller for entry in moved)
        amount = max(per_owner.values(), default=0)
    elif payoff.stat:
        amount = sum(_stat_of(entry, payoff.stat) for entry in moved)
    elif payoff.per_opponent:
        amount = payoff.unit * len({e.controller for e in moved if e.controller != controller})
    else:
        amount = payoff.unit * len(moved)
    for player in _recipients(game, obj, controller, payoff.who, moved):
        payoff.run(game, obj, player, amount)


def _recipients(
    game: "Game", obj: Any, controller: str, who: str, moved: list[Affected]
) -> list[str]:
    if who == "you":
        return [controller]
    if who == "each player":
        return _players_in_order(game)
    if who == "each opponent":
        return [name for name in _players_in_order(game) if name != controller]
    named = [t.username for t in game.resolve_targets(obj) if hasattr(t, "username")]
    if named:
        return named[:1]
    return list(dict.fromkeys(entry.owner or entry.controller for entry in moved))[:1]


# --------------------------------------------------------------------------
# The first instruction
# --------------------------------------------------------------------------

_FOR_EACH_PLAYER_DESTROY_RE = re.compile(
    r"^for each player, destroy up to one (?P<desc>[a-z ]+?) that player controls$",
    re.IGNORECASE,
)


def _for_each_player_destroys(text: str) -> Callable[["Game", Any], None] | None:
    """ "For each player, destroy up to one `<land>` that player controls." -
    the resolving ability's controller picks one (or none) of each player's
    permanents as the effect is applied (CR 608.2d), nothing is targeted."""
    match = _FOR_EACH_PLAYER_DESTROY_RE.fullmatch(text.strip().rstrip("."))
    if match is None:
        return None
    description = match.group("desc").strip()
    if description.startswith("nonbasic "):
        base = _quality_matcher(description.removeprefix("nonbasic "))
        from ..models.card import Supertype

        def matches(chars: Any) -> bool:
            return base(chars) and Supertype.BASIC not in chars.supertypes

    elif _card_description_is_readable(description):
        matches = _quality_matcher(description)
    else:
        return None

    def effect(game: "Game", obj: Any) -> None:
        controller = game.controller_of(obj).username
        source = getattr(obj, "source_name", None) or getattr(obj, "name", "")
        for player in game.players:
            candidates = [
                state
                for state in game.permanents_controlled_by(player.username)
                if matches(game.characteristics_of(state))
            ]
            if not candidates:
                continue
            chosen = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=controller,
                    prompt=f"destroy up to one {description} {player.username} controls",
                    source=source,
                    amount=1,
                    cards=tuple(state.id for state in candidates),
                    source_id=source_id_of(obj),
                    exact=False,
                )
            )
            by_id = {state.id: state for state in candidates}
            for card_id in chosen:
                target = by_id.get(card_id)
                if target is not None and target.zone is Zone.BATTLEFIELD:
                    game.destroy(target)

    return effect


_RETURN_FROM_YOUR_GRAVEYARD_RE = re.compile(
    r"^return (?P<phrase>.*target.+from your graveyard) to your hand$", re.IGNORECASE
)


def _return_from_graveyard(text: str) -> Callable[["Game", Any], None] | None:
    """ "Return target `<card>` from your graveyard to your hand." as the first
    instruction of a text that carries more targets of its own (Morgue Burst's
    "any target"): only the targets still in the graveyard are returned, where
    the generic clause returns every target the object has."""
    match = _RETURN_FROM_YOUR_GRAVEYARD_RE.fullmatch(text.strip().rstrip("."))
    if match is None or not _targets_understood(
        match.group("phrase"), count_agnostic=True, battlefield_only=False
    ):
        return None

    def effect(game: "Game", obj: Any) -> None:
        with game.returning_together():  # CR 603.2c: one instruction, one event
            for target in game.resolve_targets(obj):
                if isinstance(target, CardState) and target.zone is Zone.GRAVEYARD:
                    game.return_to_hand(target)

    return effect


_EXILE_ALL_FROM_GRAVEYARD_RE = re.compile(
    r"^exile all (?P<quality>[a-z' ,-]+?) cards? from target (?:player|opponent)'s graveyard$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s30", for_spell=FORWARD)
def _parse_exile_all_quality_from_graveyard_clause(
    clause: str, *, for_spell: bool
) -> Callable[["Game", Any], None] | None:
    """ "Exile all `<quality>` cards from target player's graveyard." (CR 406.2,
    CR 701.13a): only the cards of that quality leave - the generic "exile
    target player's graveyard" reader would take the whole pile."""
    match = _EXILE_ALL_FROM_GRAVEYARD_RE.fullmatch(clause.strip().rstrip("."))
    if match is None or not _card_description_is_readable(match.group("quality")):
        return None
    if not _targets_understood(
        "target player's graveyard", allow_player_targets=True, count_agnostic=True
    ):
        return None
    matches = _quality_matcher(match.group("quality"))

    def effect(game: "Game", obj: Any) -> None:
        for target in game.resolve_targets(obj):
            if isinstance(target, Player):
                for state in [c for c in target.graveyard if matches(c)]:
                    game.exile_permanent(state)

    return effect


def _first_instruction(text: str, for_spell: bool) -> Callable[["Game", Any], None] | None:
    returned = _return_from_graveyard(text)
    if returned is not None:
        return returned
    exiled = _parse_exile_all_quality_from_graveyard_clause(text, for_spell=for_spell)
    if exiled is not None:
        return exiled
    effect = _parse_cached(text, for_spell)
    if effect is not None:
        return effect  # type: ignore[no-any-return]
    return _for_each_player_destroys(text)


# --------------------------------------------------------------------------
# The whole text
# --------------------------------------------------------------------------

_THEN_SPLIT_RE = re.compile(r",\s+then\s+(?=[^.]*\bthis way\b)", re.IGNORECASE)


def _sentences(text: str) -> list[str]:
    out: list[str] = []
    for sentence in _plain_resolution_sentences(_strip_non_effect_preamble(text)):
        parts = _THEN_SPLIT_RE.split(sentence.strip().rstrip("."), maxsplit=1)
        out.extend(part.strip() for part in parts if part.strip())
    return out


@functools.lru_cache(maxsize=2048)
def _plan(text: str, for_spell: bool) -> tuple[Any, tuple[_Payoff, ...]] | None:
    sentences = _sentences(text)
    first = next((i for i, s in enumerate(sentences) if " this way" in s.lower()), None)
    if first is None or first == 0:
        return None
    payoffs: list[_Payoff] = []
    for sentence in sentences[first:]:
        parsed = _parse_payoff(sentence, for_spell)
        if parsed is None:
            return None
        payoffs.extend(parsed)
    instruction = _first_instruction(". ".join(sentences[:first]) + ".", for_spell)
    if instruction is None:
        return None
    return instruction, tuple(payoffs)


def _this_way_effect(text: str, for_spell: bool) -> Any:
    if " this way" not in text.lower():
        return None
    plan = _plan(text, for_spell)
    if plan is None:
        return None
    instruction, payoffs = plan
    zones = frozenset(z for payoff in payoffs for z in _VERBS[payoff.objects.verb].sources)  # type: ignore[union-attr]

    def effect(game: "Game", obj: Any) -> None:
        marks = snapshot(game, zones)
        instruction(game, obj)
        controller = game.controller_of(obj).username
        for payoff in payoffs:
            _apply(game, obj, controller, payoff, marks)

    return effect


@SPELL_TEXT.rung("s23", before=("parse_mixed_effect_for_spell",))
def _parse_affected_this_way_spell(text: str) -> Any:
    """A spell whose later sentence counts what its first instruction affected."""
    return _this_way_effect(text, True)


@ABILITY_TEXT.rung("s40", before=("parse_mixed_effect",))
def _parse_affected_this_way_ability(text: str) -> Any:
    """An ability whose later sentence counts what its first instruction affected."""
    return _this_way_effect(text, False)
