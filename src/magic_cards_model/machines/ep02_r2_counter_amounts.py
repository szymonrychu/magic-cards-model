"""EP-02 R2 T5: counters as an amount, and counter bookkeeping.

The counters-counted shapes `ep02_r1_counter_amounts` does not reach: a count
of the counters on a group, kinds of counter, doubling a stack, counters
removed "this way", and a planeswalker's loyalty counters as its power and
toughness (CR 122.1, CR 306.5c). Every reader is registered into the family
ladders; each is a template, never a card.
"""

import functools
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..models.card_state import CardState
from ..models.zone import Zone
from ..numbers import COUNT, parse_count
from .amount_sentences import split_where_x, write_x
from .decisions import Decision, DecisionKind, source_id_of
from .effects._chains import ABILITY_TEXT, FORWARD, MIXED_CLAUSE
from .effects.amounts import amount_expression
from .effects.continuous import continuous_effects
from .effects.dispatch import parse_mixed_effect
from .effects.draw_discard import _source_characteristic
from .effects.mana import read_add_mana_instruction
from .effects.tokens import _token_creator_for_count
from .ep02_r1_counter_amounts import (
    PLACEHOLDER,
    choose_counters_to_remove,
    choose_removal_allocation,
)
from .layers import (
    ContinuousEffect,
    Duration,
    Layer,
    creatures_controlled_by_opponents_of_with_power_at_most,
    grant_ability,
)
from .targeting import permanent_description

if TYPE_CHECKING:
    from ..models.game import Game


_TOKENS_EQUAL_TO_SOURCE_STAT_RE = re.compile(
    r"^create a number of (?P<desc>.+?) tokens equal to this [a-z]+'s "
    r"(?P<stat>power|toughness)\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_create_tokens_equal_to_source_stat_clause(text: str, *, for_spell: bool):
    """ "Create a number of 1/1 red Goblin creature tokens equal to Krenko's
    power" (the name read as "this creature", CR 201.5): the source's own power
    or toughness as the clause applies (CR 608.2h), after any earlier
    instruction of the same ability has run (CR 608.2c) - so a "put a +1/+1
    counter on it, then create ..." counts the new counter. The source's last
    known information when it has left the battlefield (CR 603.10a)."""
    if for_spell or "tokens equal to this" not in text:
        return None
    match = _TOKENS_EQUAL_TO_SOURCE_STAT_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    create = _token_creator_for_count(match.group("desc"))
    if create is None:
        return None
    stat = match.group("stat").lower()

    def effect(game: "Game", ability) -> None:
        count = _source_characteristic(game, ability.source_or_last_known(game), stat)
        create(game, ability, count)

    return effect


# ---------------------------------------------------------------------------
# counters-removed-this-way-amount: "remove all <kind> counters from it. <Do
# something> for each counter removed this way", "you may remove any number of
# +1/+1 counters from among creatures you control. If you do, put twice that
# many counters on this creature".
#
# CR 608.2c: the instructions run in order and the later one reads what the
# earlier one did; CR 608.2h: the number is fixed once, when the removal
# happened. The removal runs first and reports how many counters came off; the
# rest of the text is then read with that number written in (`removed_text`)
# and run, so every ordinary clause reader sees a plain number. CR 122.1: a
# counter's kind is its name, and no kind named means every kind.
# ---------------------------------------------------------------------------

_KIND = r"(?:[a-z0-9+/-]+)"
_SELF_OBJECT = r"(?:it|them|this [a-z]+)"
_REMOVE_ALL_OF_THEM_RE = re.compile(r"^(?P<may>you may )?remove all of them$", re.IGNORECASE)
_REMOVE_RE = re.compile(
    rf"^(?P<may>you may )?remove (?P<amount>all|any number of|up to (?P<upto>{COUNT}|x)|"
    rf"(?P<n>{COUNT}|x)) (?:(?P<kind>{_KIND}) )?counters?"
    rf"(?: from (?:(?P<self>{_SELF_OBJECT})|among (?P<group>[^.,]+?)"
    rf"|(?P<target>target [^.,]+?)))?$",
    re.IGNORECASE,
)
#: What the rest of a "remove ..." text says about the number removed.
_REMOVED_THIS_WAY_RE = re.compile(
    rf"\bthe number of (?:{_KIND} )?counters removed this way\b", re.IGNORECASE
)
_FOR_EACH_REMOVED_RE = re.compile(
    rf"\s+for each (?:{_KIND} )?counter removed this way(?=[.,]|$)", re.IGNORECASE
)
_TWICE_THAT_MANY_RE = re.compile(r"\btwice that many\b", re.IGNORECASE)
_THAT_MANY_RE = re.compile(r"\bthat many\b", re.IGNORECASE)


@dataclass(frozen=True)
class RemoveCounters:
    """One "remove ... counters" instruction: how many (`amount` is a number,
    "all", "any" or "x"), of which kind (`None`: any kind), from what."""

    may: bool
    amount: int | str
    kind: str | None
    source: str  # "self" | "group" | "target"
    group: str | None = None
    up_to: bool = False


@functools.cache
def parse_remove_counters(text: str) -> RemoveCounters | None:
    """`RemoveCounters` for a "remove ... counters" instruction, or `None`."""
    body = text.strip().rstrip(".")
    if "remove " not in body.lower():
        return None
    if _REMOVE_ALL_OF_THEM_RE.fullmatch(body) is not None:
        may = body.lower().startswith("you may")
        return RemoveCounters(may, "all", None, "self")
    match = _REMOVE_RE.fullmatch(body)
    if match is None:
        return None
    kind = match.group("kind")
    kind = None if kind is None or kind.lower() in ("of",) else kind.lower()
    word = (match.group("amount") or "").lower()
    if word == "all":
        amount: int | str = "all"
    elif word == "any number of":
        amount = "any"
    else:
        number = (match.group("upto") or match.group("n")).lower()
        amount = "x" if number == "x" else (parse_count(number) or 0)
        if amount == 0:
            return None
    where = "self" if match.group("self") else "group" if match.group("group") else "target"
    if (
        match.group("self") is None
        and match.group("group") is None
        and match.group("target") is None
    ):
        where = "self"  # "remove a counter" with no "from": the source
    return RemoveCounters(
        match.group("may") is not None,
        amount,
        kind,
        where,
        match.group("group"),
        up_to=word.startswith("up to"),
    )


def _kinds_on(card, kind: str | None) -> list[str]:
    return [kind] if kind is not None else [str(k) for k, count in card.counters.items() if count]


def _count_on(card, kind: str | None) -> int:
    return sum(card.counter_count(k) for k in _kinds_on(card, kind))


def _take_all(card, kind: str | None) -> int:
    removed = 0
    for each in _kinds_on(card, kind):
        have = card.counter_count(each)
        if have:
            card.remove_counters(each, have)
            removed += have
    return removed


def perform_removal(game: "Game", ability, spec: RemoveCounters, x: int | None = None) -> int:
    """Take the counters `spec` names off, asking the controller whatever the
    instruction leaves to a choice (CR 608.2d: how many of "any number of",
    which kind, from which permanent), and return how many came off. Zero when
    a "you may" is declined or nothing was there to take (CR 122.1)."""
    controller = game.controller_of(ability).username
    if spec.may and not game.ask(
        Decision(
            kind=DecisionKind.MAY,
            player=controller,
            prompt=f"remove {spec.kind or ''} counters?".replace("  ", " "),
            source=ability.source_name,
            source_id=source_id_of(ability),
        )
    ):
        return 0
    if spec.source == "self":
        source = ability.source_or_last_known(game)
        return _remove_from_one(game, ability, spec, source, x)
    if spec.source == "target":
        total = 0
        for target in game.resolve_targets(ability):
            if isinstance(target, CardState) and target.zone is Zone.BATTLEFIELD:
                total += _remove_from_one(game, ability, spec, target, x)
        return total
    return _remove_among(game, ability, spec, controller, x)


def _limit(spec: RemoveCounters, x: int | None) -> int | None:
    if spec.amount == "x":
        return x or 0
    return spec.amount if isinstance(spec.amount, int) else None


def _remove_from_one(game: "Game", ability, spec: RemoveCounters, card, x: int | None) -> int:
    if card is None or card.zone is not Zone.BATTLEFIELD:
        return 0
    limit = _limit(spec, x)
    if spec.amount == "all":
        return _take_all(card, spec.kind)
    if spec.amount == "any":
        have = _count_on(card, spec.kind)
        limit = _ask_amount(game, ability, have)
    if spec.kind is not None:
        take = min(limit or 0, card.counter_count(spec.kind))
        if take:
            card.remove_counters(spec.kind, take)
        return take
    return choose_counters_to_remove(game, ability, card, limit or 0)


def _ask_amount(game: "Game", ability, ceiling: int) -> int:
    if ceiling <= 0:
        return 0
    answer = game.ask(
        Decision(
            kind=DecisionKind.CHOOSE_AN_AMOUNT,
            player=game.controller_of(ability).username,
            prompt="choose how many counters to remove",
            source=ability.source_name,
            source_id=source_id_of(ability),
            amount=ceiling,
        )
    )
    return max(0, min(int(answer), ceiling))


def _remove_among(game: "Game", ability, spec: RemoveCounters, controller: str, x) -> int:
    requirement = permanent_description(spec.group or "")
    if requirement is None:
        return 0
    candidates = [
        permanent
        for permanent in game.permanents_controlled_by(controller)
        if _count_on(permanent, spec.kind)
        and requirement.why_not(permanent, game, controller) is None
    ]
    have = sum(_count_on(permanent, spec.kind) for permanent in candidates)
    if spec.amount == "all":
        return sum(_take_all(permanent, spec.kind) for permanent in candidates)
    total = have if spec.amount == "any" else min(_limit(spec, x) or 0, have)
    if spec.amount == "any":
        total = _ask_amount(game, ability, have)
    picks = choose_removal_allocation(
        game,
        controller,
        candidates,
        lambda card: _count_on(card, spec.kind),
        total,
        source=ability.source_name,
        source_id=source_id_of(ability),
    )
    for permanent in picks:
        for each in _kinds_on(permanent, spec.kind):
            if permanent.counter_count(each):
                permanent.remove_counters(each, 1)
                break
    return len(picks)


def removed_text(text: str, n: int) -> tuple[str, bool]:
    """`text` with the number of counters removed written in, and whether the
    instruction is a per-counter one ("... for each counter removed this way")
    to run `n` times instead."""
    each = _FOR_EACH_REMOVED_RE.search(text)
    repeat = each is not None
    if repeat:
        text = text[: each.start()] + text[each.end() :]
    text = _TWICE_THAT_MANY_RE.sub(str(2 * n), text)
    text = _THAT_MANY_RE.sub(str(n), text)
    text = _REMOVED_THIS_WAY_RE.sub(str(n), text)
    where = split_where_x(text)
    if where is not None and _REMOVED_THIS_WAY_RE.sub("", where[1]).strip() == "":
        text = write_x(where[0], n)
    return text, repeat


def _clause_effect(text: str):
    """A single instruction as an effect `(game, ability)`: an "Add ..." mana
    instruction, or whatever the ordinary ability ladder reads."""
    adder = read_add_mana_instruction(text.strip().rstrip("."))
    if adder is not None:
        return lambda game, ability: adder(game, ability, None)
    return parse_mixed_effect(text)


@functools.cache
def _rest_effect(text: str, n: int):
    rewritten, repeat = removed_text(text, n)
    unit = _clause_effect(rewritten)
    if unit is None:
        return None
    if not repeat:
        return unit

    def each(game: "Game", ability) -> None:
        for _ in range(n):
            unit(game, ability)

    return each


_IF_YOU_DO_RE = re.compile(r"^(?P<first>[^.]+)\.\s*(?:if you do,\s*)?(?P<rest>.+)$", re.IGNORECASE)
_MENTIONS_REMOVED_RE = re.compile(r"removed this way|that many", re.IGNORECASE)


def removal_then_rest_effect(text: str):
    """ "Remove ... counters. <Instruction that reads the number removed>" as one
    effect (CR 608.2c), or `None`."""
    lowered = text.lower()
    if "remove" not in lowered or _MENTIONS_REMOVED_RE.search(text) is None:
        return None
    text = " ".join(text.strip().split())
    where_x = split_where_x(text)
    first_end = text.find(". ")
    if first_end < 0:
        return None
    first, rest = text[:first_end], text[first_end + 2 :]
    rest = re.sub(r"^if you do,\s*", "", rest, flags=re.IGNORECASE)
    x_reader = None
    if where_x is not None and ", where x is" in first.lower():
        first, expr = split_where_x(first) or (first, "")
        x_reader = amount_expression(expr)
        if x_reader is None:
            return None
    spec = parse_remove_counters(first)
    if spec is None or _rest_effect(rest, PLACEHOLDER) is None:
        return None

    def effect(game: "Game", ability) -> None:
        x = None
        if x_reader is not None:
            x = x_reader(
                game, game.controller_of(ability).username, ability.source_or_last_known(game), 0
            )
        removed = perform_removal(game, ability, spec, x)
        if removed <= 0:
            return
        follow = _rest_effect(rest, removed)
        if follow is not None:
            follow(game, ability)

    return effect


@ABILITY_TEXT.rung("s40", before=("parse_mixed_effect",))
def _parse_removal_then_rest(text: str):
    """An ability whose later instruction counts the counters its first one
    removed ("... for each counter removed this way", "put twice that many ...")."""
    return removal_then_rest_effect(text)


# ---------------------------------------------------------------------------
# A count of the cards you own in exile and in your graveyard "that are <type>
# or are named <N>" (CR 108.3: cards by owner, whichever zone; CR 205.3: a
# subtype). `ep02_r1_graveyard_counts.graveyard_count_expression` reads the
# shapes with a description before "cards"; this is the relative-clause one.
# ---------------------------------------------------------------------------

_OWNED_THAT_ARE_RE = re.compile(
    r"^(?:the )?(?:total )?(?:number of )?cards you own in exile and in your graveyard "
    r"that are (?P<desc>.+?)(?: or are named (?P<name>.+))?$",
    re.IGNORECASE,
)


def _singular_word(word: str) -> str | None:
    from .effects.text import _singular_card_type, _singular_subtype_for_count_expression

    card_type = _singular_card_type(word)
    if card_type is not None:
        return card_type.value
    return _singular_subtype_for_count_expression(word)


@functools.cache
def owned_cards_that_are(phrase: str):
    """The `(game, controller) -> int` reader of "cards you own in exile and in
    your graveyard that are Oozes or are named N", or `None`."""
    match = _OWNED_THAT_ARE_RE.fullmatch(" ".join(phrase.split()).rstrip("."))
    if match is None:
        return None
    from .ep02_r1_graveyard_counts import _quality

    words = [w for w in re.split(r",\s*(?:or\s+)?|\s+(?:and/or|or)\s+", match.group("desc")) if w]
    singular = [_singular_word(word) for word in words]
    if not singular or any(word is None for word in singular):
        return None
    matches = _quality(" or ".join(singular))  # type: ignore[arg-type]
    if matches is None:
        return None
    name = match.group("name")

    def count(game: "Game", controller: str) -> int:
        owned = [
            *(card for card in game.exile if card.owner == controller),
            *game.player(controller).graveyard,
        ]
        return sum(1 for card in owned if matches(card) or (name is not None and card.name == name))

    return count


# ---------------------------------------------------------------------------
# "Count the number of <expr>. <Sentence naming that number>" - an instruction
# that only fixes a number (CR 608.2h: taken once, as it resolves) for the next
# sentence to use. Rumbling Ruin: "count the number of +1/+1 counters on
# creatures you control. Creatures your opponents control with power less than
# or equal to that number can't block this turn."
# ---------------------------------------------------------------------------

_COUNT_THE_NUMBER_RE = re.compile(
    r"^count the number of (?P<expr>[^.]+)\.\s+(?P<rest>[^.]*\bthat number\b[^.]*)\.?$",
    re.IGNORECASE,
)
_POWER_BOUND_CANT_BLOCK_RE = re.compile(
    r"^creatures your opponents control with power (?:(?P<n>\d+) or less|"
    r"less than or equal to (?P<n2>\d+)) can(?:'|’)?t block this turn\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s26", for_spell=FORWARD)
def _parse_opponents_power_bound_cant_block_clause(clause: str, *, for_spell: bool):
    """ "Creatures your opponents control with power N or less can't block this
    turn." (CR 509.1b): the restriction is granted to a live selector - it
    modifies the rules, not a characteristic, so CR 611.2c does not fix the set
    of creatures it applies to."""
    if "with power" not in clause:
        return None
    match = _POWER_BOUND_CANT_BLOCK_RE.fullmatch(" ".join(clause.split()))
    if match is None:
        return None
    threshold = int(match.group("n") or match.group("n2"))

    def effect(game: "Game", stack_object) -> None:
        controller = game.controller_of(stack_object).username
        source_name = (
            stack_object.card.name
            if isinstance(stack_object, CardState)
            else stack_object.source_name
        )
        store = continuous_effects(game)
        store.add(
            ContinuousEffect(
                description=(
                    f"{source_name}: creatures {controller}'s opponents control with power "
                    f"{threshold} or less can't block this turn"
                ),
                layer=Layer.ABILITY,
                timestamp=store.tick(),
                duration=Duration.UNTIL_END_OF_TURN,
                selector=creatures_controlled_by_opponents_of_with_power_at_most(
                    controller, threshold
                ),
                modification=grant_ability("This creature can't block."),
            )
        )

    return effect


@functools.cache
def _counted_number_then(rest: str, n: int):
    return parse_mixed_effect(re.sub(r"\bthat number\b", str(n), rest, flags=re.IGNORECASE))


@ABILITY_TEXT.rung("s40", before=("parse_mixed_effect",))
def _parse_count_the_number_then_rest(text: str):
    """ "Count the number of <expr>. <Sentence using that number>" (CR 608.2c)."""
    if not text.lower().startswith("count the number of"):
        return None
    match = _COUNT_THE_NUMBER_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    reader = amount_expression("the number of " + match.group("expr"))
    rest = match.group("rest")
    if reader is None or _counted_number_then(rest, PLACEHOLDER) is None:
        return None

    def effect(game: "Game", ability) -> None:
        number = reader(
            game, game.controller_of(ability).username, ability.source_or_last_known(game), 0
        )
        follow = _counted_number_then(rest, number)
        if follow is not None:
            follow(game, ability)

    return effect
