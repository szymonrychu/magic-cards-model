"""EP-02 R3 T6: the count a create-token sentence asks for (token-count-amounts).

Extends the shared amount readers (`effects.amounts.amount_expression` through
`_amount_term`, and `_for_each_multiplier`) additively; nothing here replaces a
reader they own, and the token clause itself stays `effects.tokens`'s.

Board facts a token count reads, each taken once when the instruction is applied
(CR 608.2h):

- "the number of opponents you have" and "the number of opponents who control
  <permanent>" - the players still in the game (CR 104.5);
- "<creatures> that died this turn" - CR 700.4's dies, read from the turn ledger
  as the creature last existed (CR 603.10a), so a token or a subtype is judged
  by what it was when it died;
- "<permanents> that entered the battlefield under your control this turn";
- "<Auras and/or Equipment> attached to <this permanent>" (CR 301.5a);
- "differently named creature tokens you control" (CR 201.2: names differ);
- "unlocked doors among Rooms you control" (CR 709.5c's unlocked designations);
- "the amount of mana spent to cast that spell" - the spell a cast trigger names
  (CR 601.2h: the total cost paid);
- "time it was kicked" as a "for each" tail (CR 702.33d).
"""

import functools
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from uuid import UUID

from ..models.card_state import CardState
from ..models.token import PREDEFINED, create_tokens, token_copy_of
from ..models.zone import Zone
from ..numbers import parse_count
from .effects._chains import ABILITY_TEXT, SPELL_TEXT
from .effects._common import _quality_matcher, _targets_understood
from .effects.amounts import amount_expression
from .effects.continuous import _may_attach_equipment_to
from .effects.dispatch import _parse_mixed_clauses
from .effects.text import _strip_non_effect_preamble
from .effects.tokens import (
    _attack_target_of_source,
    _quote_aware_sentences,
    _read_token_rider,
    _token_definition_from_words,
    apply_token_riders,
)
from .targeting import permanent_description

if TYPE_CHECKING:
    from ..models.game import Game

#: `(game, controller, source object, announced X) -> int`, `effects.amounts`'s
#: `AmountReader`.
Reader = Callable[["Game", str, CardState | None, int], int]

_PREFIX = r"^(?:the )?(?:number|amount) of "


def _opponents_of(game: "Game", controller: str) -> list:
    return [player for player in game.players_in_game if player.username != controller]


# -- opponents ------------------------------------------------------------------

_OPPONENTS_YOU_HAVE_RE = re.compile(_PREFIX + r"opponents you have$", re.IGNORECASE)
_OPPONENTS_WHO_CONTROL_RE = re.compile(
    _PREFIX + r"opponents who control (?:an? |)(?P<what>.+)$", re.IGNORECASE
)


def _opponents_you_have(_text: str) -> Reader:
    return lambda game, controller, _obj, _x: len(_opponents_of(game, controller))


def _opponents_who_control(match: re.Match[str]) -> Reader | None:
    """CR 109.5: each opponent who controls at least one permanent matching the
    description counts once."""
    from .targeting import permanent_description

    requirement = permanent_description(match.group("what").strip())
    if requirement is None:
        return None

    def count(game: "Game", controller: str, _obj: CardState | None, _x: int) -> int:
        board = game.computed_board()
        total = 0
        for opponent in _opponents_of(game, controller):
            if any(
                board.of(permanent).controller == opponent.username
                and not requirement.rejects(permanent, controller, game)
                for permanent in game.battlefield
            ):
                total += 1
        return total

    return count


# -- the turn ledger -------------------------------------------------------------

_DIED_RE = re.compile(r"^(?:the )?(?:number of )?(?P<what>.+?) that died this turn$", re.IGNORECASE)
_ENTERED_RE = re.compile(
    r"^(?:the )?(?:number of )?(?P<what>.+?) that entered the battlefield under your "
    r"control this turn$",
    re.IGNORECASE,
)


def _ledger_count(kind: str, what: str, *, yours_only: bool) -> Reader | None:
    from .conditions.history import _quality

    # CR 111.1: a token is a permanent that is not represented by a card; the
    # ledger's characteristics carry that as they last existed (CR 603.10a).
    token_filter = None
    words = [word for word in what.split() if word]
    for index, word in enumerate(words):
        if word.lower() in ("nontoken", "non-token"):
            token_filter, words = False, words[:index] + words[index + 1 :]
            break
    quality = _quality(" ".join(words))
    if quality is None:
        return None

    def count(game: "Game", controller: str, _obj: CardState | None, _x: int) -> int:
        return sum(
            1
            for entry in game.turn_history
            if entry.kind == kind
            and (not yours_only or entry.player == controller)
            and quality(entry)
            and (
                token_filter is None
                or (entry.characteristics is not None)
                and entry.characteristics.is_token is token_filter
            )
        )

    return count


# -- tokens and rooms ------------------------------------------------------------

_DIFFERENTLY_NAMED_RE = re.compile(
    _PREFIX + r"differently named (?P<what>creature tokens?) you control$", re.IGNORECASE
)
_UNLOCKED_DOORS_RE = re.compile(_PREFIX + r"unlocked doors among Rooms you control$", re.IGNORECASE)


def _differently_named_tokens(_match: re.Match[str]) -> Reader:
    def count(game: "Game", controller: str, _obj: CardState | None, _x: int) -> int:
        board = game.computed_board()
        names = set()
        for permanent in game.battlefield:
            chars = board.of(permanent)
            if (
                chars.controller == controller
                and chars.is_token
                and "creature" in {str(kind).lower().rsplit(".", 1)[-1] for kind in chars.types}
            ):
                names.add(chars.name)
        return len(names)

    return count


def _unlocked_doors(_match: re.Match[str]) -> Reader:
    """CR 709.5c: each half of a Room permanent you control that is unlocked."""

    def count(game: "Game", controller: str, _obj: CardState | None, _x: int) -> int:
        board = game.computed_board()
        return sum(
            len(permanent.unlocked_doors)
            for permanent in game.battlefield
            if board.of(permanent).controller == controller
            and "room" in {subtype.lower() for subtype in board.of(permanent).subtypes}
        )

    return count


# -- attached ---------------------------------------------------------------------

_ATTACHED_RE = re.compile(
    r"^(?:the )?(?:number of )?(?P<kinds>[A-Za-z ,/]+?) attached to "
    r"(?P<ref>it|him|her|this [a-z]+|[A-Z][\w',-]*(?: [A-Z][\w',-]*)*)$"
)
_KIND_SPLIT_RE = re.compile(
    r"\s*(?:,\s*(?:and/or\s+|or\s+|and\s+)?|\s+and/or\s+|\s+or\s+|\s+and\s+)"
)


def _attached_count(match: re.Match[str]) -> Reader | None:
    """CR 301.5a, CR 303.4b: what is attached to the object the ability is on."""
    words = [word for word in _KIND_SPLIT_RE.split(match.group("kinds").strip()) if word]
    if not words:
        return None
    wanted = {word.lower() for word in words}
    if not wanted <= {"aura", "equipment", "fortification", "auras"}:
        return None
    wanted = {word.removesuffix("s") if word == "auras" else word for word in wanted}

    def count(game: "Game", _controller: str, obj: CardState | None, _x: int) -> int:
        if obj is None:
            return 0
        board = game.computed_board()
        return sum(
            1
            for permanent in game.battlefield
            if permanent.attached_to == obj.id
            and wanted & {subtype.lower() for subtype in board.of(permanent).subtypes}
        )

    return count


# -- mana spent, kicks ----------------------------------------------------------------

_MANA_SPENT_THAT_SPELL_RE = re.compile(
    _PREFIX + r"mana spent to cast (?:that|the) spell$", re.IGNORECASE
)
_TIME_KICKED_RE = re.compile(
    r"^(?:the )?(?:number of )?times? "
    r"(?:it|this (?:creature|permanent|artifact|enchantment|spell)) "
    r"was kicked$",
    re.IGNORECASE,
)


def _mana_spent_on_triggering_spell(_match: re.Match[str]) -> Reader:
    """CR 601.2h: the total mana spent to cast the spell a cast trigger names,
    read off that spell's cast record."""

    def count(game: "Game", _controller: str, _obj: CardState | None, _x: int) -> int:
        resolving = game.resolving
        event = getattr(resolving, "event", None)
        if event is None or event.subject_id is None:
            return 0
        spell = game.find_by_id(event.subject_id)
        if not isinstance(spell, CardState):
            return 0
        record = game.cast_record_of(spell)
        return 0 if record is None else record.total_mana_spent

    return count


def _times_kicked(_match: re.Match[str]) -> Reader:
    def count(game: "Game", _controller: str, obj: CardState | None, _x: int) -> int:
        record = None if obj is None else game.cast_record_of(obj)
        return 0 if record is None else record.kicked

    return count


# -- other attacking creatures -----------------------------------------------------

_OTHER_ATTACKERS_RE = re.compile(_PREFIX + r"other attacking creatures$", re.IGNORECASE)
_GREATEST_POWER_OTHER_ATTACKERS_RE = re.compile(
    r"^the greatest power among other attacking creatures$", re.IGNORECASE
)


def _other_attackers(game: "Game", obj: CardState | None) -> list[CardState]:
    """Every attacking creature but the source (CR 508.4: a creature put onto the
    battlefield attacking is one as well)."""
    found = (game.find_by_id(attack.attacker_id) for attack in game.combat.attacks)
    return [
        creature
        for creature in found
        if isinstance(creature, CardState)
        and creature.zone is Zone.BATTLEFIELD
        and (obj is None or creature.id != obj.id)
    ]


def _other_attackers_count(game: "Game", _controller: str, obj: CardState | None, _x: int) -> int:
    return len(_other_attackers(game, obj))


def _other_attackers_greatest_power(
    game: "Game", _controller: str, obj: CardState | None, _x: int
) -> int:
    """CR 107.1b: a negative greatest power counts as zero; no attackers is zero."""
    return max(
        (game.power_of(creature) or 0 for creature in _other_attackers(game, obj)), default=0
    )


@functools.cache
def amount_term(text: str) -> Reader | None:
    """One `amount_expression` term this module reads, or `None`."""
    phrase = " ".join(text.strip().rstrip(".").split())
    lowered = phrase.lower()
    if "opponents" in lowered:
        if _OPPONENTS_YOU_HAVE_RE.fullmatch(phrase):
            return _opponents_you_have(phrase)
        if (who := _OPPONENTS_WHO_CONTROL_RE.fullmatch(phrase)) is not None:
            return _opponents_who_control(who)
    if lowered.endswith("this turn"):
        if (entered := _ENTERED_RE.fullmatch(phrase)) is not None:
            return _ledger_count("entered", entered.group("what"), yours_only=True)
        if (died := _DIED_RE.fullmatch(phrase)) is not None:
            return _ledger_count("to_graveyard", died.group("what"), yours_only=False)
    if "differently named" in lowered and (named := _DIFFERENTLY_NAMED_RE.fullmatch(phrase)):
        return _differently_named_tokens(named)
    if "unlocked doors" in lowered and (doors := _UNLOCKED_DOORS_RE.fullmatch(phrase)):
        return _unlocked_doors(doors)
    if "attached to" in lowered and (attached := _ATTACHED_RE.fullmatch(phrase)):
        return _attached_count(attached)
    if "mana spent" in lowered and (spent := _MANA_SPENT_THAT_SPELL_RE.fullmatch(phrase)):
        return _mana_spent_on_triggering_spell(spent)
    if "kicked" in lowered and (kicked := _TIME_KICKED_RE.fullmatch(phrase)):
        return _times_kicked(kicked)
    if "other attacking creatures" in lowered:
        if _OTHER_ATTACKERS_RE.fullmatch(phrase):
            return _other_attackers_count
        if _GREATEST_POWER_OTHER_ATTACKERS_RE.fullmatch(phrase):
            return _other_attackers_greatest_power
    return None


@functools.cache
def for_each_count(phrase: str) -> Callable[["Game", str, str | None], int] | None:
    """The count of a "for each <phrase>" tail: the same readers as "the number
    of <phrase>", with the ability's source as the object (CR 608.2h)."""
    text = " ".join(phrase.strip().rstrip(".").split())
    reader = amount_term(f"the number of {text}") or amount_expression(f"the number of {text}")
    if reader is None:
        return None

    def count(game: "Game", controller: str, source_id: str | None) -> int:
        source = None
        if source_id is not None:
            found = game.find_by_id(UUID(str(source_id)))
            source = found if isinstance(found, CardState) else None
        return int(reader(game, controller, source, 0))

    return count


# ====================================================================================
# Token sentences read in order (CR 608.2c)
# ====================================================================================
#
# A token paragraph is a run of instructions whose later sentences talk about what
# the earlier ones made or did: "Its power is equal to ...", "Exile those tokens at
# the beginning of the next end step", "If that creature dies this way, create ...",
# "For each flip you win, create ...". Each sentence becomes one step over a shared
# per-resolution context (`_Ctx`); a sentence none of the readers below takes goes
# through the ordinary clause pipeline, so the sequence is only taken when at least
# one reader here matched (a text the older readers already read keeps its reader).


@dataclass
class _Ctx:
    """What the earlier instructions of the resolving object left behind."""

    created: list[CardState] = field(default_factory=list)
    """The permanents the latest token-making instruction put onto the battlefield."""

    wins: int = 0
    """Coin flips won by the latest "flip N coins" (CR 705.1)."""

    discarded: list[CardState] = field(default_factory=list)
    """The cards the latest ordinary instruction put into the controller's graveyard
    (a discard, for "the discarded card")."""

    exiled: list[CardState] = field(default_factory=list)
    """The cards the latest "exile it" instruction really exiled ("If you do")."""

    referents: list[tuple[CardState, int, int]] = field(default_factory=list)
    """The resolving object's targets as they were when it began (CR 608.2h's last
    known information): the permanent, its power and its toughness."""


Step = Callable[["Game", Any, _Ctx], None]
Amount = Callable[["Game", Any, _Ctx], int]


def _source_of(game: "Game", stack_object: Any) -> tuple[CardState | None, int]:
    if hasattr(stack_object, "source_or_last_known"):
        return stack_object.source_or_last_known(game), stack_object.x_value
    return stack_object, 0


_REFERENT_STAT_RE = re.compile(
    r"^(?:that|the (?:destroyed|exiled|sacrificed)) (?:creature|permanent)'s "
    r"(?P<stat>power|toughness)$",
    re.IGNORECASE,
)


def _amount_of(expression: str) -> Amount | None:
    """`expression` as an amount read when the instruction is applied (CR 608.2h):
    a referent's last known power or toughness, or any `amount_expression`."""
    text = " ".join(expression.strip().rstrip(".").split())
    if (referent := _REFERENT_STAT_RE.fullmatch(text)) is not None:
        index = 1 if referent.group("stat").lower() == "power" else 2

        def of_referent(_game: "Game", _so: Any, ctx: _Ctx) -> int:
            return max(ctx.referents[0][index], 0) if ctx.referents else 0

        return of_referent
    reader = amount_expression(text)
    if reader is None:
        return None

    def of_board(game: "Game", stack_object: Any, _ctx: _Ctx) -> int:
        source, x_value = _source_of(game, stack_object)
        return reader(game, game.controller_of(stack_object).username, source, x_value)

    return of_board


def _run_clauses(clauses: list, game: "Game", stack_object: Any, ctx: _Ctx) -> None:
    """Ordinary clauses as a step; the tokens they put onto the battlefield become
    `ctx.created` and the cards they put into the controller's graveyard become
    `ctx.discarded` (CR 400.7: a before/after diff on the zone-change stamp)."""
    controller = game.player(game.controller_of(stack_object).username)
    before = {(state.id, state.zone_change_stamp) for state in game.battlefield}
    buried = {(card.id, card.zone_change_stamp) for card in controller.graveyard}
    for clause in clauses:
        clause(game, stack_object)
        game.announce_batched_events()  # CR 603.2c: one event per instruction
    created = [
        state for state in game.battlefield if (state.id, state.zone_change_stamp) not in before
    ]
    if created:
        ctx.created = created
    ctx.discarded = [
        card for card in controller.graveyard if (card.id, card.zone_change_stamp) not in buried
    ]


# -- "create <tokens>" with an attack, a name, a size or a per-opponent loop -------------

_TOKEN_SENTENCE_RE = re.compile(
    r"^(?:(?P<each>for each opponent),\s*)?(?:you )?create (?P<n>an?|one|x|\d+|[a-z]+) "
    r"(?P<desc>.+?) \btokens?\b"
    r"(?:\s+named (?P<name>.+?))?"
    r"(?:\s+with\s+(?P<tail>.+?))?"
    r"(?:,?\s+that(?:'s|’s| is| are) (?P<tapped>tapped and )?(?P<attacking>attacking)"
    r"(?P<who> that player or a planeswalker they control)?)?"
    r"(?:,?\s*where x is (?P<expr>.+?))?\.?$",
    re.IGNORECASE | re.DOTALL,
)

_SIZE_SENTENCE_RE = re.compile(
    r"^its power is equal to (?P<power>.+?) and its toughness is equal to (?P<toughness>.+?)\.?$",
    re.IGNORECASE,
)

_GRANT_SENTENCE_RE = re.compile(
    r"^(?:the|those) tokens? (?:have|has) (?P<quote>[\"\u201c].+[\"\u201d])\.?$", re.IGNORECASE
)

_FLIPS_RE = re.compile(r"^flip (?P<n>\w+) coins?\.?$", re.IGNORECASE)
_EACH_WIN_RE = re.compile(r"^for each flip you win, (?P<inner>.+?)\.?$", re.IGNORECASE)
_IF_DIES_RE = re.compile(
    r"^if (?:that|the) (?:creature|permanent) dies this way, (?P<inner>.+?)\.?$", re.IGNORECASE
)


def _token_step(
    match: re.Match[str],
    size: tuple[Amount, Amount] | None,
    *,
    count: Amount | None = None,
    granted: str | None = None,
) -> Step | None:
    """The step for one parsed token sentence (`_TOKEN_SENTENCE_RE`); `granted` is
    the quoted ability a following "The tokens have ..." sentence gives them
    (CR 111.3: part of the token's definition)."""
    words = match.group("desc").strip().split()
    tail = match.group("tail")
    if granted is not None:
        tail = granted if tail is None else f"{tail} and {granted}"
    definition = _token_definition_from_words(" ".join(words), tail)
    if definition is None:
        return None
    if match.group("name"):
        definition = definition.model_copy(update={"name": match.group("name").strip()})
    if count is None:
        word = match.group("n").lower()
        if word == "x":
            count = _amount_of(match.group("expr") or "")
            if count is None:
                return None
        else:
            fixed = parse_count(word)
            if fixed is None:
                return None
            count = lambda _game, _so, _ctx, fixed=fixed: fixed  # noqa: E731
    tapped = bool(match.group("tapped"))
    attacking = match.group("attacking") is not None
    per_opponent = match.group("each") is not None

    def step(game: "Game", stack_object: Any, ctx: _Ctx) -> None:
        controller = game.controller_of(stack_object).username
        made = definition
        if size is not None:
            made = definition.model_copy(
                update={
                    "power": size[0](game, stack_object, ctx),
                    "toughness": size[1](game, stack_object, ctx),
                }
            )
        number = count(game, stack_object, ctx)
        created: list[CardState] = []
        if per_opponent:
            # CR 508.4: each token is put onto the battlefield attacking the
            # player (or a planeswalker they control) its creator names.
            for opponent in _opponents_of(game, controller):
                created += create_tokens(
                    game,
                    made,
                    controller,
                    number,
                    tapped=tapped,
                    attacking=opponent.username if attacking else None,
                )
        else:
            defender = (
                _attack_target_of_source(game, stack_object, controller) if attacking else None
            )
            created = create_tokens(
                game, made, controller, number, tapped=tapped, attacking=defender
            )
        ctx.created = list(created)

    return step


def _read_token(sentences: list[str], index: int, for_spell: bool) -> tuple[Step, int] | None:
    """A token sentence the ordinary token reader does not take: one repeated for
    each opponent, one whose size the next sentence states, or one whose tokens
    "have" a quoted ability the next sentence gives them."""
    if "create" not in sentences[index].lower():
        return None
    match = _TOKEN_SENTENCE_RE.fullmatch(sentences[index].strip())
    if match is None or "copy of" in sentences[index].lower():
        return None
    following = sentences[index + 1].strip() if index + 1 < len(sentences) else ""
    sized = _SIZE_SENTENCE_RE.fullmatch(following)
    granting = _GRANT_SENTENCE_RE.fullmatch(following)
    if not (match.group("each") or sized or granting):
        return None
    size = None
    if sized is not None:
        power, toughness = _amount_of(sized.group("power")), _amount_of(sized.group("toughness"))
        if power is None or toughness is None:
            return None
        size = (power, toughness)
    step = _token_step(
        match, size, granted=granting.group("quote") if granting is not None else None
    )
    return None if step is None else (step, 2 if (sized or granting) else 1)


def _read_flips(sentences: list[str], index: int, for_spell: bool) -> tuple[Step, int] | None:
    """ "Flip N coins. For each flip you win, <instruction>." (CR 705.1): the
    instruction is applied once per flip won."""
    flips = _FLIPS_RE.fullmatch(sentences[index].strip())
    if flips is None or index + 1 >= len(sentences):
        return None
    each_win = _EACH_WIN_RE.fullmatch(sentences[index + 1].strip())
    coins = parse_count(flips.group("n"))
    if each_win is None or coins is None:
        return None
    inner = each_win.group("inner")
    match = _TOKEN_SENTENCE_RE.fullmatch(inner)
    inner_step: Step | None = None
    if match is not None and match.group("n").lower() in ("a", "an", "one"):
        # All the tokens one flip result asks for are created together (CR 701.7a).
        inner_step = _token_step(match, None, count=lambda _game, _so, ctx: ctx.wins)
    else:
        clauses = _parse_mixed_clauses(inner, for_spell=for_spell)
        if clauses is not None:

            def inner_step(game: "Game", stack_object: Any, ctx: _Ctx) -> None:  # type: ignore[misc]
                for _ in range(ctx.wins):
                    _run_clauses(clauses, game, stack_object, ctx)

    if inner_step is None:
        return None
    run_inner = inner_step

    def step(game: "Game", stack_object: Any, ctx: _Ctx) -> None:
        controller = game.controller_of(stack_object).username
        ctx.wins = sum(1 for _ in range(coins) if game.flip_coin(controller))
        run_inner(game, stack_object, ctx)

    return step, 2


def _read_conditional_on_death(
    sentences: list[str], index: int, for_spell: bool
) -> tuple[Step, int] | None:
    """ "If that creature dies this way, <token sentence>" (CR 700.4: it dies when
    it is put into a graveyard from the battlefield - a creature that was
    regenerated or was indestructible did not die)."""
    match = _IF_DIES_RE.fullmatch(sentences[index].strip())
    if match is None:
        return None
    token = _TOKEN_SENTENCE_RE.fullmatch(match.group("inner"))
    if token is None:
        return None
    following = sentences[index + 1].strip() if index + 1 < len(sentences) else ""
    sized = _SIZE_SENTENCE_RE.fullmatch(following)
    size = None
    if sized is not None:
        power, toughness = _amount_of(sized.group("power")), _amount_of(sized.group("toughness"))
        if power is None or toughness is None:
            return None
        size = (power, toughness)
    inner = _token_step(token, size)
    if inner is None:
        return None

    def step(game: "Game", stack_object: Any, ctx: _Ctx) -> None:
        if any(permanent.zone is Zone.GRAVEYARD for permanent, _p, _t in ctx.referents[:1]):
            inner(game, stack_object, ctx)

    return step, 2 if sized else 1


# -- "for each <permanent>, create a <Role> Role token attached to it" ---------------------

_FOR_EACH_ROLE_RE = re.compile(
    r"^(?:then )?for each (?P<what>.+?), create an? (?P<role>[a-z][a-z ]*?) role token attached to "
    r"(?:that [a-z]+|it)\.?$",
    re.IGNORECASE,
)
_CONTROLLER_SUFFIX_RE = re.compile(
    r"^(?P<body>.+?)(?: (?P<who>you control|your opponents control|an opponent controls))?$",
    re.IGNORECASE,
)


def _permanent_matcher(phrase: str) -> Callable[["Game", str, CardState], bool] | None:
    """A "<permanent> [you control | your opponents control]" description, as a test
    of one permanent for a given controller."""
    parts = _CONTROLLER_SUFFIX_RE.fullmatch(phrase.strip())
    if parts is None:
        return None
    requirement = permanent_description(parts.group("body"))
    if requirement is None:
        return None
    who = (parts.group("who") or "").lower()

    def matches(game: "Game", controller: str, permanent: CardState) -> bool:
        owner = game.computed_board().of(permanent).controller
        if who == "you control" and owner != controller:
            return False
        if who in ("your opponents control", "an opponent controls") and owner == controller:
            return False
        return requirement.rejects(permanent, controller, game) is None

    return matches


def _read_role_for_each(
    sentences: list[str], index: int, for_spell: bool
) -> tuple[Step, int] | None:
    """CR 111.10 Roles, one per permanent: the Role token is created attached to
    each (CR 303.4h: put onto the battlefield attached; CR 303.7a and CR 704.5z
    leave only the newest Role of one controller on a permanent). "For each of those
    creatures" is the resolving object's own targets."""
    match = _FOR_EACH_ROLE_RE.fullmatch(sentences[index].strip())
    if match is None:
        return None
    definition = PREDEFINED.get(match.group("role").strip().title())
    if definition is None or definition.subtypes != ("Aura", "Role"):
        return None
    what = match.group("what").strip()
    matcher = None if what.lower().startswith("of those") else _permanent_matcher(what)
    if matcher is None and not what.lower().startswith("of those"):
        return None

    def step(game: "Game", stack_object: Any, ctx: _Ctx) -> None:
        controller = game.controller_of(stack_object).username
        if matcher is None:
            subjects = [t for t in game.resolve_targets(stack_object) if isinstance(t, CardState)]
        else:
            subjects = [p for p in list(game.battlefield) if matcher(game, controller, p)]
        for subject in subjects:
            if subject.zone is Zone.BATTLEFIELD:
                create_tokens(game, definition, controller, attached_to=subject)

    return step, 1


# -- "Choose any number of target creatures you control." ------------------------------

_CHOOSE_TARGETS_RE = re.compile(r"^choose (?P<phrase>.+?)\.?$", re.IGNORECASE)


def _read_choose_targets(
    sentences: list[str], index: int, for_spell: bool
) -> tuple[Step, int] | None:
    """The opening sentence that only names the targets (CR 115.1a: announced with
    the object, CR 601.2c); the instructions after it act on them."""
    match = _CHOOSE_TARGETS_RE.fullmatch(sentences[index].strip())
    if match is None or "target" not in match.group("phrase").lower():
        return None
    if not _targets_understood(match.group("phrase"), count_agnostic=True):
        return None
    return (lambda _game, _so, _ctx: None), 1


# -- "For each of them, create a token that's a copy of that creature, except ..." --------

_FOR_EACH_TARGET_COPY_RE = re.compile(
    r"^for each of (?:them|those (?:creatures|permanents)),\s*"
    r"(?P<copy>create a token that['\u2019]?s a copy of that (?:creature|permanent)"
    r"(?:, except .+)?)\.?$",
    re.IGNORECASE,
)


def _read_for_each_target_copy(
    sentences: list[str], index: int, for_spell: bool
) -> tuple[Step, int] | None:
    """One token copy per chosen target. The ordinary copy-of-target reader already
    makes one copy of each target it resolves (CR 707.2's copiable values, CR 707.9b's
    exceptions), so the "that creature" anaphor is read as the target it names."""
    match = _FOR_EACH_TARGET_COPY_RE.fullmatch(sentences[index].strip())
    if match is None:
        return None
    copy = re.sub(
        r"a copy of that (?:creature|permanent)",
        "a copy of target creature you control",
        match.group("copy"),
        count=1,
        flags=re.IGNORECASE,
    )
    clauses = _parse_mixed_clauses(copy, for_spell=for_spell)
    if clauses is None:
        return None
    return (lambda game, so, ctx: _run_clauses(clauses, game, so, ctx)), 1


# -- "For each of those tokens, you may attach an Equipment you control to it" ----------------

_MAY_ATTACH_EACH_RE = re.compile(
    r"^for each of (?:those|the) tokens, you may attach an equipment you control to it\.?$",
    re.IGNORECASE,
)


def _read_may_attach_each(
    sentences: list[str], index: int, for_spell: bool
) -> tuple[Step, int] | None:
    """CR 608.2d: each token in turn offers its controller an Equipment to attach
    (CR 701.3a); an Equipment moves from a token it was already on."""
    if _MAY_ATTACH_EACH_RE.fullmatch(sentences[index].strip()) is None:
        return None

    def step(game: "Game", stack_object: Any, ctx: _Ctx) -> None:
        for token in list(ctx.created):
            _may_attach_equipment_to(game, token, stack_object)

    return step, 1


# -- "If the discarded card was an artifact card, exile it ... If you do, ..." ----------------

_IF_DISCARDED_EXILE_RE = re.compile(
    r"^if the discarded card was an? (?P<quality>[a-z]+) card, exile it from your graveyard\.?$",
    re.IGNORECASE,
)
_IF_YOU_DO_COPY_RE = re.compile(
    r"^if you do, create a token that['\u2019]?s a copy of it, except (?P<exception>.+?)\.?$",
    re.IGNORECASE,
)
_EXCEPT_TYPED_SIZE_RE = re.compile(
    r"^it['\u2019]?s an? (?P<power>\d+)/(?P<toughness>\d+) (?P<subtype>[A-Z][a-z]+) "
    r"(?:(?P<card_type>artifact|enchantment) )?creature(?: with (?P<keywords>[a-z, ]+?))? "
    r"in addition to its other types$",
    re.IGNORECASE,
)


def _read_discarded_exile(
    sentences: list[str], index: int, for_spell: bool
) -> tuple[Step, int] | None:
    """CR 608.2c: the card an earlier "discard" put into the graveyard, exiled from
    there if it has the named quality; `ctx.exiled` is what "if you do" means."""
    match = _IF_DISCARDED_EXILE_RE.fullmatch(sentences[index].strip())
    if match is None:
        return None
    wanted = _quality_matcher(match.group("quality").lower())
    if wanted is None:
        return None

    def step(game: "Game", _so: Any, ctx: _Ctx) -> None:
        ctx.exiled = []
        card = ctx.discarded[0] if ctx.discarded else None
        if card is not None and card.zone is Zone.GRAVEYARD and wanted(card):
            ctx.exiled = [moved for moved in game.exile_cards([card]) if moved.zone is Zone.EXILE]

    return step, 1


def _read_if_you_do_copy(
    sentences: list[str], index: int, for_spell: bool
) -> tuple[Step, int] | None:
    """ "If you do, create a token that's a copy of it, except it's a P/T `<Subtype>`
    artifact creature with `<keywords>` in addition to its other types": CR 707.9b's
    exceptions, folded into the copy's copiable values (`token_copy_of`)."""
    from .layers.model import split_and_validate_keywords

    match = _IF_YOU_DO_COPY_RE.fullmatch(sentences[index].strip())
    if match is None:
        return None
    exception = _EXCEPT_TYPED_SIZE_RE.fullmatch(match.group("exception").strip())
    if exception is None:
        return None
    keywords = None
    if exception.group("keywords"):
        keywords = split_and_validate_keywords(exception.group("keywords"))
        if keywords is None:
            return None
    options: dict[str, Any] = {
        "power": int(exception.group("power")),
        "toughness": int(exception.group("toughness")),
        "added_creature_type": exception.group("subtype"),
        "added_abilities": tuple(keywords or ()),
    }
    if exception.group("card_type"):
        options["added_card_type"] = exception.group("card_type").title()

    def step(game: "Game", stack_object: Any, ctx: _Ctx) -> None:
        controller = game.controller_of(stack_object).username
        if ctx.exiled:
            ctx.created = list(token_copy_of(game, ctx.exiled[0], controller, **options))

    return step, 1


_READERS = (
    _read_choose_targets,
    _read_token,
    _read_flips,
    _read_conditional_on_death,
    _read_role_for_each,
    _read_for_each_target_copy,
    _read_may_attach_each,
    _read_discarded_exile,
    _read_if_you_do_copy,
)


#: A quoted ability's closing quote followed by the next instruction with no full
#: stop between them - what the support oracle's "redacted quote" probe leaves
#: behind, and never printed on a real card.
_AFTER_QUOTE_RE = re.compile(
    r"(?<=[\"\u201d])\s+(?=(?:Then|For|It|They|Its|Those|That|Exile|Sacrifice|If|Create|Draw)\b)"
)


def _sentences(text: str) -> list[str]:
    return [
        part.strip()
        for sentence in _quote_aware_sentences(_strip_non_effect_preamble(text))
        for part in _AFTER_QUOTE_RE.split(sentence)
        if part.strip()
    ]


@functools.lru_cache(maxsize=4096)
def _sequence(text: str, for_spell: bool) -> Callable[["Game", Any], None] | None:
    """The whole paragraph as ordered steps, or `None` when no sentence of it is one
    of the shapes above (or one cannot be read at all - never half a paragraph)."""
    lowered = text.lower()
    if "token" not in lowered and "role" not in lowered:
        return None
    sentences = _sentences(text)
    steps: list[Step] = []
    used = False
    index = 0
    while index < len(sentences):
        for reader in _READERS:
            found = reader(sentences, index, for_spell)
            if found is not None:
                steps.append(found[0])
                index += found[1]
                used = True
                break
        else:
            rider = _read_token_rider(sentences[index])
            if rider is not None and steps:
                kind, value = rider
                grants = [value] if kind == "grant" else []
                delayed = [value] if kind == "delayed" else []

                def rider_step(
                    game: "Game",
                    stack_object: Any,
                    ctx: _Ctx,
                    grants: list = grants,
                    delayed: list = delayed,
                ) -> None:
                    apply_token_riders(
                        game, stack_object, ctx.created, grants, delayed, for_spell=for_spell
                    )

                steps.append(rider_step)
            else:
                clauses = _parse_mixed_clauses(sentences[index], for_spell=for_spell)
                if clauses is None:
                    return None
                steps.append(
                    lambda game, so, ctx, clauses=clauses: _run_clauses(clauses, game, so, ctx)
                )
            index += 1
    if not used:
        return None
    needs_referents = "that creature" in lowered or "that permanent" in lowered

    def effect(game: "Game", stack_object: Any) -> None:
        ctx = _Ctx()
        if needs_referents:
            ctx.referents = [
                (target, game.power_of(target) or 0, game.toughness_of(target) or 0)
                for target in game.resolve_targets(stack_object)
                if isinstance(target, CardState)
            ]
        for step in steps:
            step(game, stack_object, ctx)
            game.announce_batched_events()

    return effect


@ABILITY_TEXT.rung("s40", before=("parse_mixed_effect",))
def _parse_token_sequence_ability(text: str) -> Any:
    """An ability whose token paragraph is one of this module's sequences."""
    return _sequence(text, False)


@SPELL_TEXT.rung("s23", before=("parse_mixed_effect_for_spell",))
def _parse_token_sequence_spell(text: str) -> Any:
    """A spell whose token paragraph is one of this module's sequences."""
    return _sequence(text, True)


# ====================================================================================
# "Look at the top card of <whose> library, then exile it face down. You may play it."
# ====================================================================================

_LOOK_EXILE_MAY_PLAY_RE = re.compile(
    r"^look at the top card of (?P<whose>your|target opponent'?s|target player'?s|that player'?s) "
    r"library, then exile it face down\.\s*"
    r"you may (?P<verb>play|cast) that card for as long as it remains exiled\.?$",
    re.IGNORECASE,
)


def _look_exile_may_play(text: str, *, for_spell: bool) -> Any:
    """The peek-exile-play template (CR 701.20e looks, CR 406.3 face down, CR 607.2a
    linked to the source). The grant (CR 601.3, CR 305.2a for a land) names this one
    object and ends when it leaves exile (CR 400.7); nobody else may play it."""
    lowered = text.lower()
    if "look at the top card" not in lowered or "face down" not in lowered:
        return None
    match = _LOOK_EXILE_MAY_PLAY_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None
    whose = match.group("whose").lower()
    verb = match.group("verb").lower()

    def effect(game: "Game", ability: Any) -> None:
        from .casting import PlayAction
        from .exile_top_marked import _owners, exiled_by_top_of_library, mark_exiled

        controller = game.controller_of(ability).username
        owners = _owners(game, ability, whose)
        if not owners or not owners[0].library:
            return
        game.look(owners[0].library[0], controller, source=ability.source_name)
        for card in exiled_by_top_of_library(game, ability, owners[:1], 1):
            mark_exiled(game, ability, card, face_down=True, looker=controller)
            if card.zone is Zone.EXILE:
                game.grant_play_permission(
                    card,
                    controller,
                    action=PlayAction.PLAY if verb == "play" else PlayAction.CAST,
                    source_name=ability.source_name,
                    rule="CR 601.3",
                    zone=Zone.EXILE,
                    until_end_of_turn=False,
                )

    return effect


@ABILITY_TEXT.rung("s40", before=("parse_mixed_effect",))
def _parse_look_exile_may_play_ability(text: str) -> Any:
    return _look_exile_may_play(text, for_spell=False)


# ====================================================================================
# "Target creature card in your graveyard gains embalm until end of turn."
# ====================================================================================

_GRANT_TOKEN_COPY_KEYWORD_RE = re.compile(
    r"^(?P<phrase>target creature card in your graveyard) gains (?P<keyword>embalm|eternalize) "
    r"until end of turn\.\s*the (?P=keyword) cost is equal to its mana cost\.?$",
    re.IGNORECASE,
)


def _grant_token_copy_keyword(text: str) -> Any:
    """CR 702.128a / CR 702.129a granted for a turn (CR 611.2, CR 613.1f): the card
    gains the keyword line with its own mana cost as the cost (CR 202.1), which the
    off-zone ability machinery then offers like a printed one - sorcery timing and
    exiling the card are part of the keyword's own activation."""
    if "gains" not in text.lower() or "mana cost" not in text.lower():
        return None
    match = _GRANT_TOKEN_COPY_KEYWORD_RE.fullmatch(" ".join(text.split()))
    if match is None or not _targets_understood(match.group("phrase"), battlefield_only=False):
        return None
    keyword = match.group("keyword").title()

    def effect(game: "Game", ability: Any) -> None:
        from .effects.continuous import continuous_effects
        from .layers import ContinuousEffect, Duration, Layer, grant_ability, only_this_incarnation

        store = continuous_effects(game)
        for target in game.resolve_targets(ability):
            if not isinstance(target, CardState) or target.zone is not Zone.GRAVEYARD:
                continue
            if not target.card.mana_cost:
                continue  # no mana cost, no cost to be equal to (CR 202.1)
            store.add(
                ContinuousEffect(
                    description=f"{ability.source_name}: {target.name} gains {keyword.lower()}",
                    layer=Layer.ABILITY,
                    timestamp=store.tick(),
                    selector=only_this_incarnation(target, target.zone_change_stamp),
                    modification=grant_ability(f"{keyword} {target.card.mana_cost}"),
                    duration=Duration.UNTIL_END_OF_TURN,
                ),
                game,
            )

    return effect


@ABILITY_TEXT.rung("s40", before=("parse_mixed_effect",))
def _parse_grant_token_copy_keyword_ability(text: str) -> Any:
    return _grant_token_copy_keyword(text)
