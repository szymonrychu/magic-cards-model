"""EP-02 R2 T8: chosen or paid amounts, and damage or life as X.

Two shared parts live here.

**choose-amount-then-payoff.** An instruction lets a player choose how many
things to act on or how much to pay, and a later instruction reads exactly
that number:

    Tap any number of untapped creatures you control. Create a 4/4 ... token
    for each creature tapped this way.
    Return any number of Mountains you control to their owner's hand. ...
    equal to twice the number of Mountains returned this way.
    Reveal any number of creature cards with power 5 or greater from your
    hand. Add {G} for each card revealed this way.
    Pay any amount of mana. Look at that many cards ...
    You may pay {1}{W} any number of times. When you pay this cost one or
    more times, put that many valor counters on this creature.

CR 107.1c: "any number" may be zero. The choice is the player's, asked as a
`Decision` while the effect is applied (CR 608.2d) with the limit in the
question, so an over-large answer is refused with a text naming that limit.
CR 608.2c: the later instruction reads what the earlier one really did - the
objects that really moved or tapped, the amount really paid - which the
choosing instruction records on the count channel (`Game.record_count`, read
by `effects.that_many` and `effects.counted_this_way`).

**damage-or-life-amount-as-x.** An amount that is the damage dealt or life
gained: "the damage dealt to target opponent this turn", "the damage dealt to
your opponents this turn", "that damage" / "the damage dealt" after a
combat-damage trigger, "each 1 life you gained" after a life-gain trigger, "X
can't be greater than the amount of life you gained this turn". CR 120.3a:
damage dealt to a player makes them lose that much life; CR 119.3 adjusts a
life total by what was gained or lost. The this-turn damage total is the
engine's own per-turn count (`DAMAGE_DEALT_TO_PLAYER`, written where damage is
dealt); a trigger's amount is the event's (`GameEvent.amount`, CR 603.2c).

A sentence whose amount is one of these is rewritten with the number and read
by the ordinary clause parsers as it resolves (`_rewritten`); it is probed with
a sample number when the text is read, so an unreadable sentence refuses the
whole text instead of failing on resolution.
"""

import functools
import re
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ..models.card_state import CardState
from ..models.player import Player
from ..models.zone import Zone
from .decisions import Decision, DecisionKind, source_id_of
from .effects._chains import ABILITY_TEXT, FORWARD, MIXED_CLAUSE, SPELL_TEXT

if TYPE_CHECKING:
    from ..models.game import Game

#: `Game.turn_counts` key: damage dealt to a player this turn (CR 120.3a).
DAMAGE_DEALT_TO_PLAYER = "damage_dealt_to_player"


def _source_name(stack_object: Any) -> str:
    return str(
        getattr(stack_object, "source_name", None) or getattr(stack_object, "name", "") or ""
    )


def _controller(game: "Game", stack_object: Any) -> Player:
    return game.controller_of(stack_object)


def _singular(noun: str) -> str:
    words = noun.strip().split()
    if not words:
        return noun
    last = words[-1]
    lowered = last.lower()
    if lowered in ("plains",):
        return noun.strip()
    if lowered.endswith("ies"):
        words[-1] = last[:-3] + "y"
    elif lowered.endswith(("ches", "shes", "sses", "xes")):
        words[-1] = last[:-2]
    elif lowered.endswith("s") and not lowered.endswith(("ss", "us")):
        words[-1] = last[:-1]
    return " ".join(words)


# --------------------------------------------------------------------------
# choose-amount-then-payoff: "<verb> any number of <things>"
# --------------------------------------------------------------------------

#: "with {X} in its/their mana cost" - a card description word the shared
#: grammar has no entry for (CR 107.3, CR 202.1).
_X_IN_COST_RE = re.compile(r"\s+with \{x\} in (?:its|their) mana costs?$", re.IGNORECASE)

_ANY_NUMBER_RE = re.compile(
    r"^(?:you may )?(?P<verb>tap|return|reveal|sacrifice) any number of (?P<desc>.+?)"
    r"(?P<where> you control(?: to (?:their|its) owners?'s? hands?)?"
    r"| from your hand| in your hand|)$",
    re.IGNORECASE,
)


def _hand_card_matcher(description: str) -> Callable[["Game", str, CardState], bool] | None:
    """A predicate over a hand card for "<desc> card(s)" - "cards", "creature
    cards with power 5 or greater", "cards with {X} in their mana cost"."""
    from .targeting import permanent_description

    text = description.strip()
    needs_x = False
    if (m := _X_IN_COST_RE.search(text)) is not None:
        needs_x = True
        text = text[: m.start()]
    m = re.fullmatch(r"(?P<head>.*?)\bcards?\b(?P<tail>(?: with .+)?)", text, re.IGNORECASE)
    if m is None:
        return None
    rest = m.group("head").strip()
    tail = m.group("tail").strip()
    phrase = (_singular(rest) if rest else "permanent") + (" " + tail if tail else "")
    requirement = None
    if rest or tail:
        requirement = permanent_description(phrase)
        if requirement is None:
            return None
    battlefield_only = requirement

    def matches(game: "Game", controller: str, state: CardState) -> bool:
        if needs_x and "{X}" not in (state.card.mana_cost or "").upper():
            return False
        if battlefield_only is None:
            return True
        return (
            battlefield_only.model_copy(update={"zones": frozenset({Zone.HAND})}).rejects(
                state, controller, game
            )
            is None
        )

    return matches


_LIST_SPLIT_RE = re.compile(r"\s*,\s*(?:and/or\s+|or\s+|and\s+)?|\s+and/or\s+|\s+or\s+")


def _permanent_matcher(description: str) -> tuple[bool, bool, Callable[..., bool]] | None:
    """`(untapped_only, other, predicate)` for "untapped creatures", "Mountains",
    "other permanents", "artifacts, enchantments, and/or tokens" - a list of
    descriptions names a permanent that fits any one of them."""
    from .targeting import permanent_description

    text = description.strip()
    untapped = text.lower().startswith("untapped ")
    if untapped:
        text = text[len("untapped ") :]
    other = text.lower().startswith("other ")
    if other:
        text = text[len("other ") :]
    requirements = []
    for part in _LIST_SPLIT_RE.split(text):
        requirement = permanent_description(_singular(part))
        if requirement is None:
            return None
        requirements.append(requirement)

    def matches(game: "Game", controller: str, state: CardState) -> bool:
        return any(r.rejects(state, controller, game) is None for r in requirements)

    return untapped, other, matches


@functools.cache
def _any_number_plan(clause: str) -> tuple[str, Callable[..., bool], bool, bool] | None:
    match = _ANY_NUMBER_RE.fullmatch(clause.strip().rstrip("."))
    if match is None:
        return None
    verb = match.group("verb").lower()
    where = match.group("where").strip().lower()
    description = match.group("desc")
    if verb == "sacrifice":
        # CR 701.21a: only a permanent its controller controls can be
        # sacrificed, so "you control" may go unprinted. "Sacrifice any
        # number of <card type>s." is `removal`'s Scapeshift reader.
        from .effects.removal import _SACRIFICE_N_GROUP_RE

        if where not in ("", "you control") or _SACRIFICE_N_GROUP_RE.fullmatch(clause.strip()):
            return None
        permanent = _permanent_matcher(description)
        return None if permanent is None else ("sacrifice", permanent[2], False, permanent[1])
    if not where:
        return None
    if verb == "reveal":
        if where == "you control":
            return None
        hand = _hand_card_matcher(description)
        return None if hand is None else ("reveal", hand, False, False)
    if not where.startswith("you control"):
        return None
    to_hand = " to " in where
    if (verb == "return") != to_hand:
        return None
    permanent = _permanent_matcher(description)
    if permanent is None:
        return None
    untapped, other, predicate = permanent
    if verb == "tap" and not untapped:
        return None
    return verb, predicate, untapped, other


def choose_any_number(
    game: "Game",
    stack_object: Any,
    player: Player,
    candidates: list[CardState],
    prompt: str,
) -> list[CardState]:
    """CR 107.1c / CR 608.2d: `player` chooses any number - zero up to all - of
    `candidates`; the answer is refused past the limit (`Game.ask`)."""
    if not candidates:
        return []
    chosen = game.ask(
        Decision(
            kind=DecisionKind.CHOOSE_CARDS,
            player=player.username,
            prompt=prompt,
            source=_source_name(stack_object),
            source_id=source_id_of(stack_object),
            amount=len(candidates),
            cards=tuple(state.id for state in candidates),
            exact=False,
        )
    )
    by_id = {state.id: state for state in candidates}
    return [by_id[card_id] for card_id in chosen if card_id in by_id]


def any_number_chosen(game: "Game", stack_object: Any, clause: str) -> list[CardState] | None:
    """Carry out "<verb> any number of <things>" and return what it really
    affected (CR 608.2c) - `None` when `clause` is not that shape."""
    plan = _any_number_plan(clause)
    if plan is None:
        return None
    verb, predicate, untapped, other = plan
    player = _controller(game, stack_object)
    source_id = source_id_of(stack_object)
    if verb == "reveal":
        candidates = [s for s in player.hand if predicate(game, player.username, s)]
    else:
        candidates = [
            s
            for s in game.permanents_controlled_by(player.username)
            if predicate(game, player.username, s)
            and not (untapped and s.tapped)
            and not (other and str(s.id) == str(source_id))
        ]
    chosen = choose_any_number(game, stack_object, player, candidates, clause.strip().rstrip("."))
    done: list[CardState] = []
    for state in chosen:
        if verb == "tap":
            if not state.tapped and state.zone is Zone.BATTLEFIELD and game.tap_permanent(state):
                done.append(state)
        elif verb == "sacrifice":
            if state.zone is Zone.BATTLEFIELD:
                game.sacrifice(state)
                done.append(state)
        elif verb == "return":
            if state.zone is Zone.BATTLEFIELD:
                moved = game.return_to_hand(state)
                if moved is not None and moved.zone is Zone.HAND:
                    done.append(moved)
        else:
            if state.zone is Zone.HAND:
                game.reveal(state, source=_source_name(stack_object))
                done.append(state)
    return done


@MIXED_CLAUSE.rung("s32", for_spell=FORWARD)
def _parse_any_number_of_clause(clause: str, *, for_spell: bool) -> Any:
    """ "[You may] tap any number of untapped <permanents> you control",
    "Return any number of <permanents> you control to their owner's hand",
    "Reveal any number of <cards> from your hand", "Sacrifice any number of
    <permanents> [you control]" (CR 107.1c, CR 701.26a, CR 701.20a,
    CR 701.21a): the controller chooses, the chosen objects are tapped,
    returned, revealed or sacrificed, and how many really were is recorded for a later
    "for each ... this way" / "that many" (CR 608.2c)."""
    lowered = clause.lower()
    if "any number of" not in lowered or _any_number_plan(clause) is None:
        return None

    def effect(game: "Game", stack_object: Any) -> None:
        done = any_number_chosen(game, stack_object, clause) or []
        game.record_count(len(done))

    return effect


def reveal_any_number_readable(clause: str) -> bool:
    """Whether a mana ability's "Reveal any number of <cards> from your hand"
    count is one `reveal_any_number_count` performs (`machines/abilities.py`)."""
    plan = _any_number_plan(clause)
    return plan is not None and plan[0] == "reveal"


def reveal_any_number_count(game: "Game", source: CardState, clause: str) -> int:
    """CR 605.3b: a mana ability's own reveal, chosen and performed as it
    resolves - how many cards were really revealed (CR 107.1c, CR 701.20a)."""
    return len(any_number_chosen(game, source, clause) or [])


# --------------------------------------------------------------------------
# damage-or-life-amount-as-x
# --------------------------------------------------------------------------

#: "the damage dealt to target opponent this turn" (Knollspine Dragon), "the
#: damage dealt to your opponents this turn" (Notorious Throng) - CR 120.3a.
_DAMAGE_THIS_TURN_RE = re.compile(
    r"^(?:the )?(?:total )?(?:amount of )?damage dealt to "
    r"(?P<who>target opponent|target player|your opponents|each opponent|you) this turn$",
    re.IGNORECASE,
)


def _damage_dealt_this_turn(game: "Game", username: str) -> int:
    return game.turn_count(DAMAGE_DEALT_TO_PLAYER, username)


@functools.cache
def damage_this_turn_count(phrase: str) -> Callable[["Game", str], int] | None:
    """`(game, controller) -> int` for the damage a player or players were
    dealt this turn (CR 120.3a), read once as the instruction is applied
    (CR 608.2h). A targeted player is the resolving object's chosen target."""
    match = _DAMAGE_THIS_TURN_RE.fullmatch(phrase.strip().rstrip("."))
    if match is None:
        return None
    who = match.group("who").lower()

    def count(game: "Game", controller: str) -> int:
        if who == "you":
            return _damage_dealt_this_turn(game, controller)
        if who.startswith("target"):
            resolving = game.resolving
            if resolving is None:
                return 0
            return sum(
                _damage_dealt_this_turn(game, target.username)
                for target in game.resolve_targets(resolving)
                if isinstance(target, Player)
            )
        return sum(
            _damage_dealt_this_turn(game, player.username)
            for player in game.players_in_game
            if player.username != controller
        )

    return count


# --------------------------------------------------------------------------
# choose-amount-then-payoff: paying an amount
# --------------------------------------------------------------------------


def _times(cost_text: str, n: int) -> "Any":
    from ..models.mana import ManaCost

    return ManaCost.parse(cost_text * n)


def most_payable_times(game: "Game", player: Player, cost_text: str, ceiling: int = 64) -> int:
    """How many times `player` could pay `cost_text` right now from floating
    mana and untapped mana sources (CR 118.3, CR 608.2g)."""
    from .cost.payment import plan_mana_payment

    sources = game._mana_sources_while_resolving(player)
    times = 0
    while times < ceiling:
        cost = _times(cost_text, times + 1)
        if plan_mana_payment(cost, sources, game=game, payer=player.username) is None:
            break
        times += 1
    return times


def pay_cost_chosen_times(
    game: "Game", stack_object: Any, player: Player, cost_text: str, prompt: str
) -> int:
    """CR 107.1c / CR 608.2d: `player` chooses how many times to pay
    `cost_text` - zero up to as many times as they can pay (CR 118.3), the
    limit named in the question - and pays it that many times."""
    limit = most_payable_times(game, player, cost_text)
    chosen = game.choose_an_amount(
        player,
        limit,
        source=_source_name(stack_object),
        source_id=source_id_of(stack_object),
        prompt=f"{prompt} (at most {limit}, CR 118.3)",
    )
    if chosen <= 0:
        return 0
    sources = game._mana_sources_while_resolving(player)
    game._pay_mana_while_resolving(player, _times(cost_text, chosen), sources, prompt=prompt)
    return chosen


_PAY_ANY_AMOUNT_RE = re.compile(
    r"^(?:then )?(?:you may )?pay any amount of (?P<what>\{e\}|mana|life)$", re.IGNORECASE
)


@MIXED_CLAUSE.rung("s32", for_spell=FORWARD)
def _parse_pay_any_amount_clause(clause: str, *, for_spell: bool) -> Any:
    """ "[You may] pay any amount of {E}" (CR 107.14) / "Pay any amount of
    mana" (CR 118.3) / "Pay any amount of life" (CR 119.4): the player
    chooses the amount, up to what they can pay, pays it, and the amount
    paid is recorded for a later "that many" / "for each {E} paid this way"
    (CR 608.2c)."""
    if "any amount of" not in clause.lower():
        return None
    match = _PAY_ANY_AMOUNT_RE.fullmatch(clause.strip().rstrip("."))
    if match is None:
        return None
    what = match.group("what").lower()

    def effect(game: "Game", stack_object: Any) -> None:
        player = _controller(game, stack_object)
        if what == "{e}":
            paid = game.pay_any_amount_of_energy(
                player, source=_source_name(stack_object), source_id=source_id_of(stack_object)
            )
        elif what == "life":
            # CR 119.4: from 0 up to the player's life total.
            paid = game.pay_any_amount_of_life(
                player, source=_source_name(stack_object), source_id=source_id_of(stack_object)
            )
        else:
            paid = pay_cost_chosen_times(
                game, stack_object, player, "{1}", "pay any amount of mana"
            )
        game.record_count(paid)

    return effect


_ANY_NUMBER_OF_TIMES_RE = re.compile(
    r"^you may pay (?P<cost>(?:\{[^}]+\})+) any number of times\.\s*"
    r"when you pay this cost one or more times, (?P<payoff>.+?)\.?$",
    re.IGNORECASE | re.DOTALL,
)


def _that_many_written(payoff: str, n: int) -> str:
    text = re.sub(r"\btwice that many\b", str(2 * n), payoff, flags=re.IGNORECASE)
    text = re.sub(r"\bthree times that many\b", str(3 * n), text, flags=re.IGNORECASE)
    return re.sub(r"\bthat many\b", str(n), text, flags=re.IGNORECASE)


@functools.cache
def _times_payoff_readable(payoff: str) -> bool:
    from .effects.dispatch import _ability_effect_or_notice
    from .effects.tokens import _is_notice_only

    for n in (1, 2):
        effect = _ability_effect_or_notice(_that_many_written(payoff, n) + ".")
        if effect is None or _is_notice_only(effect):
            return False
    return True


def any_number_of_times_effect(text: str) -> Any:
    """ "You may pay {1}{W} any number of times. When you pay this cost one or
    more times, <payoff with that many>." (the Adversary cycle) - the number
    of payments is chosen (CR 107.1c) and paid, then a reflexive trigger
    (CR 603.12) carries the payoff with "that many" read as that number."""
    if "any number of times" not in text.lower():
        return None
    match = _ANY_NUMBER_OF_TIMES_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    cost_text, payoff = match.group("cost"), match.group("payoff")
    if not _times_payoff_readable(payoff):
        return None

    def effect(game: "Game", ability: Any) -> None:
        from .delayed import ReflexiveConsequence

        player = _controller(game, ability)
        paid = pay_cost_chosen_times(
            game, ability, player, cost_text, f"pay {cost_text} any number of times"
        )
        if paid <= 0:
            return
        game.create_reflexive_trigger(
            text=_that_many_written(payoff, paid) + ".",
            controller=player.username,
            source_id=getattr(ability, "source_id", None),
            source_name=_source_name(ability),
            callback=ReflexiveConsequence(),
        )

    return effect


@ABILITY_TEXT.rung("s40", before=("parse_mixed_effect",))
def _parse_any_number_of_times_ability(text: str) -> Any:
    """`any_number_of_times_effect` as an ability's whole text."""
    return any_number_of_times_effect(text)


# --------------------------------------------------------------------------
# A chosen amount, then a payoff that reads "that many"
# --------------------------------------------------------------------------

_FIRST_SENTENCE_RE = re.compile(r"^(?P<first>[^.]+?)(?:\.\s+|,\s*then\s+)(?P<rest>.+)$", re.DOTALL)


def _chooser(clause: str, for_spell: bool) -> Any:
    return _parse_pay_any_amount_clause(clause, for_spell=for_spell) or _parse_any_number_of_clause(
        clause, for_spell=for_spell
    )


def _number_written(rest: str, n: int) -> str:
    text = re.sub(
        r"\blook at that many cards from the top of (?P<whose>your|their|its owner's) library",
        lambda m: f"look at the top {n} cards of {m.group('whose')} library",
        rest,
        flags=re.IGNORECASE,
    )
    return _that_many_written(text, n)


@functools.cache
def _then_that_many_plan(text: str, for_spell: bool) -> tuple[Any, str] | None:
    from .effects.dispatch import _ability_effect_or_notice, _spell_effect_or_notice
    from .effects.text import _strip_non_effect_preamble
    from .effects.tokens import _is_notice_only

    whole = " ".join(_strip_non_effect_preamble(text).strip().split())
    match = _FIRST_SENTENCE_RE.fullmatch(whole)
    if match is None or "that many" not in match.group("rest").lower():
        return None
    chooser = _chooser(match.group("first"), for_spell)
    if chooser is None:
        return None
    parse = _spell_effect_or_notice if for_spell else _ability_effect_or_notice
    rest = match.group("rest").strip()
    for n in (1, 2):
        effect = parse(_number_written(rest, n))
        if effect is None or _is_notice_only(effect):
            return None
    return chooser, rest


def then_that_many_effect(text: str, for_spell: bool) -> Any:
    """ "Pay any amount of mana. Look at that many cards from the top of your
    library, then ..." (Karn, Living Legacy's -1): the chosen amount is paid,
    then the rest is read with the number written in (CR 608.2c)."""
    if "that many" not in text.lower() or "any " not in text.lower():
        return None
    plan = _then_that_many_plan(text, for_spell)
    if plan is None:
        return None
    chooser, rest = plan

    def effect(game: "Game", stack_object: Any) -> None:
        from .effects.dispatch import _ability_effect_or_notice, _spell_effect_or_notice

        chooser(game, stack_object)
        n = game.recorded_count() or 0
        if n <= 0:
            return
        parse = _spell_effect_or_notice if for_spell else _ability_effect_or_notice
        payoff = parse(_number_written(rest, n))
        if payoff is not None:
            payoff(game, stack_object)

    return effect


@ABILITY_TEXT.rung("s40", before=("parse_mixed_effect",))
def _parse_then_that_many_ability(text: str) -> Any:
    """`then_that_many_effect` as an ability's whole text."""
    return then_that_many_effect(text, False)


# --------------------------------------------------------------------------
# damage-or-life-amount-as-x: the amount written into the text as it resolves
# --------------------------------------------------------------------------

#: The trigger event's own amount (CR 603.2c): "that damage", "the damage
#: dealt", "the amount of damage dealt" after a damage trigger (CR 120.3a).
_EVENT_AMOUNT = r"(?:that damage|the damage dealt|the damage|the amount of damage dealt)"
_EVENT_AMOUNT_RE = re.compile(rf"^{_EVENT_AMOUNT}$", re.IGNORECASE)

#: Each rewrite: a printed amount that names the trigger's own amount, and
#: the ordinary wording the clause readers already know with that number.
_EVENT_REWRITES: tuple[tuple[re.Pattern[str], Callable[[re.Match[str], int], str]], ...] = (
    # "with mana value less than or equal to that damage" (CR 202.3).
    (
        re.compile(rf"\bmana value less than or equal to {_EVENT_AMOUNT}\b", re.IGNORECASE),
        lambda m, n: f"mana value {n} or less",
    ),
    # "discards cards equal to the damage".
    (
        re.compile(rf"\b(?P<noun>cards|damage|life) equal to {_EVENT_AMOUNT}\b", re.IGNORECASE),
        lambda m, n: f"{n} {m.group('noun')}",
    ),
    # "put a +1/+1 counter on target creature for each 1 life you gained"
    # after a life-gain trigger (CR 119.3, CR 603.2c).
    (
        re.compile(
            r"\bput (?:a|an|one) (?P<kind>\S+) counter on (?P<obj>[^.]+?) "
            r"for each 1 life (?:you|they|that player) gained\b",
            re.IGNORECASE,
        ),
        lambda m, n: f"put {n} {m.group('kind')} counters on {m.group('obj')}",
    ),
)

#: "mana value less than or equal to <a counted amount>".
_AT_MOST_COUNT_RE = re.compile(
    r"\bmana value less than or equal to (?P<expr>the (?:number|amount) of [^.]+?)"
    r"(?= and |\.|,|$)",
    re.IGNORECASE,
)

#: ", where X is <expr>" ending its sentence, its X used anywhere in the text.
_WHERE_X_SENTENCE_RE = re.compile(r",\s*where x is (?P<expr>[^.]+)(?=\.|$)", re.IGNORECASE)

Measure = Callable[["Game", Any], int]


def _event_amount(game: "Game", stack_object: Any) -> int:
    from .effects.amounts import that_many

    return that_many(game, stack_object) or 0


def amount_measure(expr: str) -> Measure | None:
    """`(game, stack_object) -> int` for an amount phrase: the trigger's own
    amount (CR 603.2c) or anything `count_expression` reads ("the total
    amount of life your opponents lost this turn", "the amount of life you
    gained this turn"), read once as the instruction is applied (CR 608.2h)."""
    from .effects.amounts import count_expression

    phrase = expr.strip().rstrip(".")
    if _EVENT_AMOUNT_RE.fullmatch(phrase):
        return _event_amount
    count = count_expression(phrase)
    if count is None:
        return None

    def measure(game: "Game", stack_object: Any) -> int:
        return count(game, game.controller_of(stack_object).username)

    return measure


def _written_template(
    text: str, *, after_prefix: bool = False
) -> tuple[Measure, Callable[[int], str]] | None:
    """`(measure, template)`: the amount `text` names and `text` with that
    amount written as a number, or `None` when it names none of these.
    `after_prefix`: earlier instructions run first, so even a one-sentence
    "..., where X is ..." is read here, once they have."""
    from .amount_sentences import write_x

    where = _WHERE_X_SENTENCE_RE.search(text)
    if where is not None:
        # Otherwise only an X that reaches past its own sentence: a
        # one-sentence "..., where X is ..." is the ordinary readers' own.
        later = text[where.end() :]
        measure = amount_measure(where.group("expr"))
        if measure is None:
            return None
        body = text[: where.start()] + later
        return measure, lambda n: write_x(body, n)
    if after_prefix and (bound := _AT_MOST_COUNT_RE.search(text)) is not None:
        # "with mana value less than or equal to the number of creatures
        # sacrificed this way" (The Hunger Tide Rises), read once the
        # sacrifice before it has happened (CR 608.2c).
        bound_measure = amount_measure(bound.group("expr"))
        if bound_measure is not None:
            return (
                bound_measure,
                lambda n: text[: bound.start()] + f"mana value {n} or less" + text[bound.end() :],
            )
    if not any(pattern.search(text) for pattern, _ in _EVENT_REWRITES):
        return None

    def template(n: int) -> str:
        written = text
        for pattern, write in _EVENT_REWRITES:
            written = pattern.sub(lambda m, w=write: w(m, n), written)
        return written

    return _event_amount, template


def _parser(for_spell: bool) -> Callable[[str], Any]:
    from .effects.dispatch import _ability_effect_or_notice, _spell_effect_or_notice

    return _spell_effect_or_notice if for_spell else _ability_effect_or_notice


@functools.cache
def _readable_for_numbers(template_texts: tuple[str, ...], for_spell: bool) -> bool:
    from .effects.tokens import _is_notice_only

    parse = _parser(for_spell)
    for written in template_texts:
        effect = parse(written)
        if effect is None or _is_notice_only(effect):
            return False
    return True


def amount_written_effect(text: str, for_spell: bool) -> Any:
    """A text whose amount is the damage dealt, the life gained, or a
    ", where X is <expr>" read across its sentences: as it resolves the
    amount is measured once (CR 608.2h) and written into the text as a
    number, and that text is read by the ordinary readers (CR 608.2c). The
    text is probed with sample numbers when read, so a shape no reader takes
    refuses here instead of failing on resolution."""
    from .effects.text import _strip_non_effect_preamble

    lowered = text.lower()
    if "where x is" not in lowered and not any(
        word in lowered
        for word in ("damage", "life you gained", "life they gained", "less than or equal to the")
    ):
        return None
    whole = " ".join(_strip_non_effect_preamble(text).strip().split())
    prefix, body = "", whole
    sentences = re.split(r"(?<=\.)\s+", whole)
    where_at = next(
        (
            i
            for i, sentence in enumerate(sentences)
            if _WHERE_X_SENTENCE_RE.search(sentence) or _AT_MOST_COUNT_RE.search(sentence)
        ),
        0,
    )
    if where_at > 0:
        # "Sacrifice any number of lands. Reveal the top X cards ..., where X
        # is the number of lands sacrificed this way. ..." - the instructions
        # before X is defined are followed first (CR 608.2c), then X is read.
        prefix, body = " ".join(sentences[:where_at]), " ".join(sentences[where_at:])
    plan = _written_template(body, after_prefix=bool(prefix))
    if plan is None:
        return None
    measure, template = plan
    if template(1) == body or not _readable_for_numbers(
        tuple(template(n) for n in (1, 2, 3)) + ((prefix,) if prefix else ()), for_spell
    ):
        return None

    def effect(game: "Game", stack_object: Any) -> None:
        parse = _parser(for_spell)
        if prefix:
            first = parse(prefix)
            if first is not None:
                first(game, stack_object)
        n = measure(game, stack_object)
        payoff = parse(template(n))
        if payoff is not None:
            payoff(game, stack_object)

    return effect


@ABILITY_TEXT.rung("s40", after=("parse_mixed_effect", "_parse_counted_amount_ability_text"))
def _parse_amount_written_ability(text: str) -> Any:
    """`amount_written_effect` as an ability's whole text."""
    return amount_written_effect(text, False)


@SPELL_TEXT.rung(
    "s23",
    after=(
        "_parse_counted_amount_spell_text",
        "parse_mixed_effect_for_spell",
        "_parse_affected_this_way_spell",
    ),
)
def _parse_amount_written_spell(text: str) -> Any:
    """`amount_written_effect` as a spell's whole text."""
    return amount_written_effect(text, True)


# --------------------------------------------------------------------------
# "you may pay {X}. If you do, <X payoff>. X can't be greater than <amount>."
# --------------------------------------------------------------------------

_PAY_X_CAPPED_RE = re.compile(
    r"^you may pay \{x\}\. if you do, (?P<body>[^.]+)\. "
    r"x can't be greater than (?P<cap>[^.]+?)\.?$",
    re.IGNORECASE,
)


def pay_x_capped_effect(text: str, for_spell: bool) -> Any:
    """ "You may pay {X}. If you do, draw X cards. X can't be greater than
    the amount of life you gained this turn." (Shanna, Purifying Blade): X is
    chosen as the ability resolves (CR 107.3, CR 608.2d), from 0 up to the
    smaller of the cap and what can be paid (CR 118.3) - the limit is named
    in the question and an answer past it refused - then {X} is paid and the
    payoff read with X written in."""
    from .amount_sentences import write_x

    if "can't be greater than" not in text.lower():
        return None
    match = _PAY_X_CAPPED_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    cap = amount_measure(match.group("cap"))
    body = match.group("body") + "."
    if cap is None or not _readable_for_numbers(tuple(write_x(body, n) for n in (1, 2)), for_spell):
        return None

    def effect(game: "Game", stack_object: Any) -> None:
        player = _controller(game, stack_object)
        ceiling = min(cap(game, stack_object), most_payable_times(game, player, "{1}"))
        x = game.choose_an_amount(
            player,
            ceiling,
            source=_source_name(stack_object),
            source_id=source_id_of(stack_object),
            prompt=f"pay {{X}} (X at most {ceiling}: {match.group('cap')}, CR 118.3)",
        )
        if x <= 0:
            return
        sources = game._mana_sources_while_resolving(player)
        game._pay_mana_while_resolving(player, _times("{1}", x), sources, prompt="pay {X}")
        payoff = _parser(for_spell)(write_x(body, x))
        if payoff is not None:
            payoff(game, stack_object)

    return effect


@ABILITY_TEXT.rung("s40", before=("parse_mixed_effect",))
def _parse_pay_x_capped_ability(text: str) -> Any:
    """`pay_x_capped_effect` as an ability's whole text."""
    return pay_x_capped_effect(text, False)


# --------------------------------------------------------------------------
# Payoffs a written-in amount lands on
# --------------------------------------------------------------------------

#: "look at the top card of your library. You may play a land from the top
#: of your library or cast a spell with mana value N or less from the top of
#: your library without paying its mana cost. If you don't, put that card
#: into your hand." (Ziatora's Envoy, N read in from the damage dealt).
_LOOK_TOP_PLAY_OR_CAST_ELSE_HAND_RE = re.compile(
    r"^look at the top card of your library\. you may play a land from the top of your "
    r"library or cast a spell(?: with mana value (?P<most>\d+) or less)? from the top of "
    r"your library without paying its mana cost\. if you don't, put that card into your "
    r"hand\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s40", before=("parse_mixed_effect",))
def _parse_look_top_play_or_cast_else_hand(text: str) -> Any:
    """CR 701.20e looks at the top card; CR 608.2g lets it be played (a land,
    CR 305.9, within the land-play allowance CR 305.2) or cast without paying
    its mana cost (CR 118.9) as this resolves; CR 608.2d offers only what is
    legal; a card not played or cast goes to its owner's hand."""
    if "if you don't, put that card into your hand" not in text.lower():
        return None
    match = _LOOK_TOP_PLAY_OR_CAST_ELSE_HAND_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    most = int(match.group("most")) if match.group("most") else None

    def effect(game: "Game", stack_object: Any) -> None:
        player = _controller(game, stack_object)
        if not player.library:
            return
        top = player.library[0]
        name = _source_name(stack_object)
        game.look(top, player.username, source=name)
        taken = None
        if top.card.is_land or most is None or top.mana_value <= most:
            taken = game.may_cast_during_resolution(
                top,
                player.username,
                prompt=("play that land" if top.card.is_land else "cast that spell")
                + " from the top of your library without paying its mana cost",
                source=name,
                source_id=source_id_of(stack_object),
                source_name=name,
                rule="CR 608.2g",
                play=True,
            )
        if taken is None and top.zone is Zone.LIBRARY:
            player.move(top, Zone.HAND)

    return effect


#: "look at the top N cards of your library. Exile one of those cards and put
#: the rest on the bottom of your library in a random order. You may play the
#: exiled card this turn." (Florian, Voldaren Scion, N read in from the life
#: opponents lost this turn).
_LOOK_TOP_EXILE_ONE_PLAY_RE = re.compile(
    r"^look at the top (?P<n>\d+) cards? of your library\. exile one of (?:them|those cards) "
    r"and put the rest on the bottom of your library in a random order\. "
    r"you may play the exiled card this turn\.?$",
    re.IGNORECASE,
)


@ABILITY_TEXT.rung("s40", before=("parse_mixed_effect",))
def _parse_look_top_exile_one_play_this_turn(text: str) -> Any:
    """CR 701.20e looks at the top N; one is exiled (CR 406.1) and may be
    played this turn (CR 601.3), the rest go to the bottom in a random order.
    N of zero looks at nothing."""
    if "may play the exiled card this turn" not in text.lower():
        return None
    match = _LOOK_TOP_EXILE_ONE_PLAY_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    count = int(match.group("n"))

    def effect(game: "Game", stack_object: Any) -> None:
        from .casting.permissions import PlayAction
        from .effects.library import _bottom_in_random_order

        player = _controller(game, stack_object)
        name = _source_name(stack_object)
        looked = list(player.library[:count])
        if not looked:
            return
        for state in looked:
            game.look(state, player.username, source=name)
        chosen_ids = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=player.username,
                prompt="exile one of the cards looked at; you may play it this turn",
                source=name,
                source_id=source_id_of(stack_object),
                amount=1,
                cards=tuple(state.id for state in looked),
                default_cards=(looked[0].id,),
            )
        )
        by_id = {state.id: state for state in looked}
        chosen = [by_id[card_id] for card_id in chosen_ids if card_id in by_id][:1]
        for state in chosen:
            exiled = game.exile_permanent(state)
            game.grant_play_permission(
                exiled,
                player.username,
                action=PlayAction.PLAY,
                source_name=name,
                zone=Zone.EXILE,
                rule="CR 601.3",
            )
        _bottom_in_random_order(game, player, [s for s in looked if s not in chosen])

    return effect


# --------------------------------------------------------------------------
# Revealed cards' mana symbols as the amount
# --------------------------------------------------------------------------

_COLOR_SYMBOL = {"white": "W", "blue": "U", "black": "B", "red": "R", "green": "G"}

#: "for each green mana symbol in those cards' mana costs" (Phosphorescent
#: Feast's chroma) - CR 107.4 names the mana symbols, CR 202.1 puts them in a
#: card's mana cost; a hybrid symbol with that color in it is one of them.
_SYMBOLS_IN_THOSE_RE = re.compile(
    r"\bfor each (?P<color>white|blue|black|red|green) mana symbol in those cards' mana costs\b",
    re.IGNORECASE,
)


def colored_symbols_in_costs(cards: list[CardState], color: str) -> int:
    """How many of `cards`' mana symbols are `color` (W/U/B/R/G), a hybrid
    or Phyrexian symbol containing it included (CR 107.4)."""
    total = 0
    for state in cards:
        for symbol in re.findall(r"\{([^}]+)\}", state.card.mana_cost or ""):
            if color in symbol.upper().split("/"):
                total += 1
    return total


@functools.cache
def _reveal_then_symbols_plan(text: str, for_spell: bool) -> tuple[str, str, str] | None:
    from .effects.text import _strip_non_effect_preamble

    whole = " ".join(_strip_non_effect_preamble(text).strip().split())
    match = _FIRST_SENTENCE_RE.fullmatch(whole)
    if match is None:
        return None
    first, rest = match.group("first"), match.group("rest").strip()
    symbols = _SYMBOLS_IN_THOSE_RE.search(rest)
    plan = _any_number_plan(first)
    if symbols is None or plan is None or plan[0] != "reveal":
        return None
    payoff = _SYMBOLS_IN_THOSE_RE.sub("for each card revealed this way", rest)
    if not _readable_for_numbers((payoff,), for_spell):
        return None
    return first, payoff, _COLOR_SYMBOL[symbols.group("color").lower()]


def reveal_then_symbols_effect(text: str, for_spell: bool) -> Any:
    """ "Reveal any number of cards in your hand. You gain 2 life for each
    green mana symbol in those cards' mana costs.": the cards are chosen and
    revealed (CR 107.1c, CR 701.20a), their symbols of that color counted
    (CR 107.4, CR 202.1), and that count is what the payoff reads through
    the count channel (CR 608.2c)."""
    if "mana symbol in those cards" not in text.lower():
        return None
    plan = _reveal_then_symbols_plan(text, for_spell)
    if plan is None:
        return None
    first, payoff, color = plan

    def effect(game: "Game", stack_object: Any) -> None:
        revealed = any_number_chosen(game, stack_object, first) or []
        game.record_count(colored_symbols_in_costs(revealed, color))
        reader = _parser(for_spell)(payoff)
        if reader is not None:
            reader(game, stack_object)

    return effect


@SPELL_TEXT.rung("s23")
def _parse_reveal_then_symbols_spell(text: str) -> Any:
    """`reveal_then_symbols_effect` as a spell's whole text."""
    return reveal_then_symbols_effect(text, True)


@ABILITY_TEXT.rung("s40", before=("parse_mixed_effect",))
def _parse_reveal_then_symbols_ability(text: str) -> Any:
    """`reveal_then_symbols_effect` as an ability's whole text."""
    return reveal_then_symbols_effect(text, False)


# --------------------------------------------------------------------------
# "Starting with you, each player may pay any amount of life. Repeat this
# process until no one pays life."
# --------------------------------------------------------------------------

_REPEATED_PAY_LIFE_RE = re.compile(
    r"^starting with you, each player may pay any amount of life\. "
    r"repeat this process until no one pays life\. "
    r"each player creates (?P<rest>.+?) for each 1 life they paid this way\.?$",
    re.IGNORECASE,
)


def _starting_with(game: "Game", username: str) -> list[Player]:
    players = list(game.players_in_game)
    names = [player.username for player in players]
    start = names.index(username) if username in names else 0
    return players[start:] + players[:start]


def repeated_pay_life_effect(text: str) -> Any:
    """Plague of Vermin: starting with the controller and going in turn
    order, each player may pay any amount of life (CR 119.4,
    CR 107.1c); the round repeats until a whole round passes with no one
    paying; then each player creates a token per 1 life they paid in all."""
    from .amount_sentences import token_maker

    if "repeat this process until no one pays life" not in text.lower():
        return None
    match = _REPEATED_PAY_LIFE_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    make = token_maker(match.group("rest"))
    if make is None:
        return None

    def effect(game: "Game", stack_object: Any) -> None:
        order = _starting_with(game, _controller(game, stack_object).username)
        paid = {player.username: 0 for player in order}
        name, source_id = _source_name(stack_object), source_id_of(stack_object)
        while True:
            round_paid = 0
            for player in order:
                if player not in game.players_in_game:
                    continue
                amount = game.pay_any_amount_of_life(player, source=name, source_id=source_id)
                paid[player.username] += amount
                round_paid += amount
            if round_paid <= 0:
                break
        for player in order:
            make(game, player.username, paid[player.username])

    return effect


@SPELL_TEXT.rung("s23")
def _parse_repeated_pay_life_spell(text: str) -> Any:
    """`repeated_pay_life_effect` as a spell's whole text."""
    return repeated_pay_life_effect(text)


#: "look at the top N cards of your library. Put one of those cards into your
#: hand and exile the rest." (Plunge into Darkness, N read in from the life
#: paid).
_LOOK_TOP_ONE_TO_HAND_EXILE_REST_RE = re.compile(
    r"^look at the top (?P<n>\d+) cards? of your library\. put one of (?:them|those cards) "
    r"into your hand and exile the rest\.?$",
    re.IGNORECASE,
)


def look_top_one_to_hand_exile_rest(clause: str) -> Any:
    """CR 701.20e looks at the top N; one goes to the hand, the rest are
    exiled (CR 406.1). N of zero looks at nothing."""
    if "exile the rest" not in clause.lower():
        return None
    match = _LOOK_TOP_ONE_TO_HAND_EXILE_REST_RE.fullmatch(" ".join(clause.strip().split()))
    if match is None:
        return None
    count = int(match.group("n"))

    def effect(game: "Game", stack_object: Any) -> None:
        player = _controller(game, stack_object)
        name = _source_name(stack_object)
        looked = list(player.library[:count])
        if not looked:
            return
        for state in looked:
            game.look(state, player.username, source=name)
        chosen_ids = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=player.username,
                prompt="put one of the cards looked at into your hand; the rest are exiled",
                source=name,
                source_id=source_id_of(stack_object),
                amount=1,
                cards=tuple(state.id for state in looked),
                default_cards=(looked[0].id,),
            )
        )
        by_id = {state.id: state for state in looked}
        chosen = [by_id[card_id] for card_id in chosen_ids if card_id in by_id][:1]
        for state in chosen:
            player.move(state, Zone.HAND)
        for state in looked:
            if state not in chosen and state.zone is Zone.LIBRARY:
                game.exile_permanent(state)

    return effect


@SPELL_TEXT.rung("s23")
def _parse_look_top_one_to_hand_exile_rest_spell(text: str) -> Any:
    """`look_top_one_to_hand_exile_rest` as a spell's whole text."""
    return look_top_one_to_hand_exile_rest(text)


@ABILITY_TEXT.rung("s40", before=("parse_mixed_effect",))
def _parse_look_top_one_to_hand_exile_rest_ability(text: str) -> Any:
    """`look_top_one_to_hand_exile_rest` as an ability's whole text."""
    return look_top_one_to_hand_exile_rest(text)


@SPELL_TEXT.rung("s23")
def _parse_then_that_many_spell(text: str) -> Any:
    """`then_that_many_effect` as a spell's whole text."""
    return then_that_many_effect(text, True)


def chosen_amount_spell_effect(text: str) -> Any:
    """This module's whole-text spell readers, for a text that never reaches
    `SPELL_TEXT` (a modal spell's mode, CR 700.2a)."""
    for reader in (
        lambda t: then_that_many_effect(t, True),
        lambda t: amount_written_effect(t, True),
        lambda t: reveal_then_symbols_effect(t, True),
        look_top_one_to_hand_exile_rest,
        repeated_pay_life_effect,
    ):
        effect = reader(text)
        if effect is not None:
            return effect
    return None


# --------------------------------------------------------------------------
# "Lands you control enter tapped this turn." as one instruction of several
# --------------------------------------------------------------------------


@MIXED_CLAUSE.rung("s32", for_spell=FORWARD)
def _parse_enters_tapped_this_turn_clause(clause: str, *, for_spell: bool) -> Any:
    """ "<Permanents> you control enter tapped this turn." after other
    instructions (Nahiri's Lithoforming): a replacement effect created as the
    instruction resolves (CR 614.1a) lasting the turn (CR 611.2a), ended by
    the cleanup step (CR 514.2)."""
    from .replacement import CreatedReplacement, EntersTappedThisTurn
    from .replacement.parse import created_replacement_spec

    if "enter tapped" not in clause.lower():
        return None
    spec = created_replacement_spec(clause)
    if not isinstance(spec, EntersTappedThisTurn):
        return None
    label = " ".join(clause.split())

    def effect(game: "Game", stack_object: Any) -> None:
        source_id = getattr(stack_object, "source_id", None) or getattr(stack_object, "id", None)
        game.created_replacements.append(
            CreatedReplacement(
                spec=spec,
                label=label,
                controller=_controller(game, stack_object).username,
                source_id=source_id,
                source_name=_source_name(stack_object),
            )
        )

    return effect


#: "For each land sacrificed this way, draw a card." - the count fronted.
_LEADING_FOR_EACH_RE = re.compile(r"^for each (?P<each>[^,]+), (?P<body>.+?)\.?$", re.IGNORECASE)


@MIXED_CLAUSE.rung("s32", for_spell=FORWARD)
def _parse_leading_for_each_clause(clause: str, *, for_spell: bool) -> Any:
    """ "For each <counted thing>, <instruction>" is the same instruction as
    "<instruction> for each <counted thing>" (CR 608.2c), read that way."""
    from .effects.dispatch import _parse_mixed_clause

    if not clause.lower().startswith("for each "):
        return None
    match = _LEADING_FOR_EACH_RE.fullmatch(" ".join(clause.strip().split()))
    if match is None or "this way" not in match.group("each").lower():
        return None
    return _parse_mixed_clause(
        f"{match.group('body')} for each {match.group('each')}", for_spell=for_spell
    )


#: "Reveal the top N cards of your library. Choose any number of artifact
#: and/or land cards revealed this way. Put all nonland cards chosen this way
#: onto the battlefield, then put all land cards chosen this way onto the
#: battlefield tapped, then put the rest on the bottom of your library in a
#: random order." (Hew the Entwood, N read in from the lands sacrificed).
_REVEAL_CHOOSE_PUT_RE = re.compile(
    r"^reveal the top (?P<n>\d+) cards? of your library\. "
    r"choose any number of (?P<types>[a-z ,/]+?) cards revealed this way\. "
    r"put all nonland cards chosen this way onto the battlefield, "
    r"then put all land cards chosen this way onto the battlefield tapped, "
    r"then put the rest on the bottom of your library in a random order\.?$",
    re.IGNORECASE,
)
_TYPE_WORDS = {
    "artifact": "Artifact",
    "creature": "Creature",
    "enchantment": "Enchantment",
    "land": "Land",
    "planeswalker": "Planeswalker",
    "battle": "Battle",
}


def _type_list(words: str) -> tuple[str, ...] | None:
    parts = [p for p in re.split(r"\s*(?:,|and/or|\bor\b|\band\b)\s*", words.lower()) if p]
    if not parts or any(part not in _TYPE_WORDS for part in parts):
        return None
    return tuple(_TYPE_WORDS[part] for part in parts)


def reveal_choose_put_effect(text: str) -> Any:
    """CR 701.20a reveals the top N; any number (CR 107.1c) of the named
    types are chosen; the chosen nonland cards enter, then the chosen lands
    enter tapped (CR 608.2c's order), and the rest go to the bottom in a
    random order."""
    if "cards chosen this way onto the battlefield" not in text.lower():
        return None
    match = _REVEAL_CHOOSE_PUT_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    types = _type_list(match.group("types"))
    if types is None:
        return None
    count = int(match.group("n"))

    def effect(game: "Game", stack_object: Any) -> None:
        from .effects.library import _bottom_in_random_order

        player = _controller(game, stack_object)
        name = _source_name(stack_object)
        revealed = list(player.library[:count])
        for state in revealed:
            game.reveal(state, source=name)
        candidates = [
            state for state in revealed if any(t in str(state.card.type_line) for t in types)
        ]
        chosen = choose_any_number(
            game, stack_object, player, candidates, "choose cards revealed this way"
        )
        for state in [c for c in chosen if not c.card.is_land]:
            game.put_onto_battlefield(state, player.username)
        for state in [c for c in chosen if c.card.is_land]:
            game.put_onto_battlefield(state, player.username, tapped=True)
        _bottom_in_random_order(
            game, player, [s for s in revealed if s not in chosen and s.zone is Zone.LIBRARY]
        )

    return effect


@SPELL_TEXT.rung("s23")
def _parse_reveal_choose_put_spell(text: str) -> Any:
    """`reveal_choose_put_effect` as a spell's whole text."""
    return reveal_choose_put_effect(text)


@ABILITY_TEXT.rung("s40", before=("parse_mixed_effect",))
def _parse_reveal_choose_put_ability(text: str) -> Any:
    """`reveal_choose_put_effect` as an ability's whole text."""
    return reveal_choose_put_effect(text)


# --------------------------------------------------------------------------
# "... You may play those cards this turn." after an exile of a chosen number
# --------------------------------------------------------------------------

_PLAY_THOSE_THIS_TURN_RE = re.compile(
    r"^(?P<prefix>.+\.)\s+you may play (?:those cards|them|the exiled cards) this turn\.?$",
    re.IGNORECASE,
)


@functools.cache
def _play_exiled_plan(text: str, for_spell: bool) -> tuple[str, str] | None:
    from .effects.text import _strip_non_effect_preamble

    whole = " ".join(_strip_non_effect_preamble(text).strip().split())
    match = _PLAY_THOSE_THIS_TURN_RE.fullmatch(whole)
    if match is None:
        return None
    exile, _, middle = match.group("prefix").partition(". ")
    if not exile.lower().startswith("exile any number of "):
        return None
    exile += "."
    middle = middle.strip()
    if not _readable_for_numbers((exile, middle) if middle else (exile,), for_spell):
        return None
    return exile, middle


def play_exiled_this_turn_effect(text: str, for_spell: bool) -> Any:
    """ "Exile any number of target cards from your graveyard. Add {R} for
    each card exiled this way. You may play those cards this turn."
    (Quintorius Kand's -6): the earlier instructions are followed (CR
    608.2c), and each card they really exiled may be played this turn
    (CR 601.3, CR 305.2 for a land)."""
    if "may play" not in text.lower() or "this turn" not in text.lower():
        return None
    plan = _play_exiled_plan(text, for_spell)
    if plan is None:
        return None
    exile, middle = plan

    def effect(game: "Game", stack_object: Any) -> None:
        from .casting.permissions import PlayAction

        parse = _parser(for_spell)
        before = {state.id for state in game.exile}
        first = parse(exile)
        if first is not None:
            first(game, stack_object)
        exiled = [s for s in game.exile if s.id not in before]
        # "for each card exiled this way" reads what really moved (CR 608.2c).
        game.record_count(len(exiled))
        then = parse(middle) if middle else None
        if then is not None:
            then(game, stack_object)
        player = _controller(game, stack_object)
        for state in exiled:
            game.grant_play_permission(
                state,
                player.username,
                action=PlayAction.PLAY,
                source_name=_source_name(stack_object),
                zone=Zone.EXILE,
                rule="CR 601.3",
            )

    return effect


@ABILITY_TEXT.rung("s40", before=("parse_mixed_effect",))
def _parse_play_exiled_this_turn_ability(text: str) -> Any:
    """`play_exiled_this_turn_effect` as an ability's whole text."""
    return play_exiled_this_turn_effect(text, False)


@SPELL_TEXT.rung("s23")
def _parse_play_exiled_this_turn_spell(text: str) -> Any:
    """`play_exiled_this_turn_effect` as a spell's whole text."""
    return play_exiled_this_turn_effect(text, True)


# --------------------------------------------------------------------------
# "Target opponent reveals N cards from their hand. You choose one of them
# and exile it." (the payoff after "pay any amount of life")
# --------------------------------------------------------------------------

_REVEAL_N_CHOOSE_EXILE_RE = re.compile(
    r"^target (?:opponent|player) reveals (?P<n>\d+) cards? from their hand\.\s*"
    r"you choose (?:one|a card) of them and exile it\.?$",
    re.IGNORECASE,
)


def reveal_n_choose_exile_effect(text: str, for_spell: bool) -> Any:
    """ "Target opponent reveals N cards from their hand. You choose one of
    them and exile it." (Vizkopa Confessor, N written in from "that many"):
    the revealing player picks which N cards - every card when the hand is
    shorter (CR 609.3) - and reveals them (CR 701.20a); the effect's
    controller then chooses one of those cards and it is exiled (CR 701.13a),
    the choice made as the effect resolves (CR 608.2d)."""
    if " reveals " not in text.lower() or "of them and exile it" not in text.lower():
        return None
    match = _REVEAL_N_CHOOSE_EXILE_RE.fullmatch(" ".join(text.strip().split()))
    if match is None:
        return None
    wanted = int(match.group("n"))

    def effect(game: "Game", stack_object: Any) -> None:
        controller = _controller(game, stack_object)
        revealer = next(
            (t for t in game.resolve_targets(stack_object) if isinstance(t, Player)), None
        )
        if revealer is None or wanted <= 0:
            return
        hand = list(revealer.hand)
        revealed = hand
        if len(hand) > wanted:
            picked = game.ask(
                Decision(
                    kind=DecisionKind.CHOOSE_CARDS,
                    player=revealer.username,
                    prompt=f"reveal {wanted} cards from your hand",
                    source=_source_name(stack_object),
                    source_id=source_id_of(stack_object),
                    amount=wanted,
                    exact=True,
                    cards=tuple(state.id for state in hand),
                )
            )
            by_id = {state.id: state for state in hand}
            revealed = [by_id[card_id] for card_id in picked]
        for state in revealed:
            game.reveal(state, source=_source_name(stack_object))
        if not revealed:
            return
        chosen = game.ask(
            Decision(
                kind=DecisionKind.CHOOSE_CARDS,
                player=controller.username,
                prompt=f"choose one of the cards {revealer.username} revealed to exile",
                source=_source_name(stack_object),
                source_id=source_id_of(stack_object),
                amount=1,
                exact=True,
                cards=tuple(state.id for state in revealed),
            )
        )
        by_id = {state.id: state for state in revealed}
        for card_id in chosen:
            game.exile_permanent(by_id[card_id])

    return effect


@ABILITY_TEXT.rung("s40", before=("parse_mixed_effect",))
def _parse_reveal_n_choose_exile_ability(text: str) -> Any:
    """`reveal_n_choose_exile_effect` as an ability's whole text."""
    return reveal_n_choose_exile_effect(text, False)


@SPELL_TEXT.rung("s23")
def _parse_reveal_n_choose_exile_spell(text: str) -> Any:
    """`reveal_n_choose_exile_effect` as a spell's whole text."""
    return reveal_n_choose_exile_effect(text, True)


# --------------------------------------------------------------------------
# "Counter target spell unless its controller pays {1} for each {E} paid
# this way." (Aether Spike)
# --------------------------------------------------------------------------

_COUNTER_UNLESS_PAYS_PER_RE = re.compile(
    r"^counter (?P<phrase>target [^.]*?spell) unless its controller pays "
    r"\{(?P<n>\d+)\} for each \{e\} paid this way\.?$",
    re.IGNORECASE,
)


@MIXED_CLAUSE.rung("s32", for_spell=FORWARD)
def _parse_counter_unless_pays_per_energy_clause(clause: str, *, for_spell: bool) -> Any:
    """ "Counter target spell unless its controller pays {N} for each {E} paid
    this way." (CR 118.12a, CR 608.2c): the spell's controller is offered
    {N} times the energy the preceding "pay any amount of {E}" really took
    (the recorded count); nothing owed means nothing to decline, so the spell
    is not countered."""
    if "for each {e} paid this way" not in clause.lower():
        return None
    match = _COUNTER_UNLESS_PAYS_PER_RE.fullmatch(clause.strip())
    if match is None:
        return None
    from .effects._common import _targets_understood

    if not _targets_understood(match.group("phrase"), battlefield_only=False):
        return None
    unit = int(match.group("n"))

    def effect(game: "Game", stack_object: Any) -> None:
        owed = unit * (game.recorded_count() or 0)
        for reference in stack_object.targets:
            if not reference.is_card:
                continue
            target = next((item for item in game.stack if item.id == reference.card_id), None)
            if target is None:
                continue
            if owed > 0 and game.may_pay_mana(
                target.controller,
                owed,
                source=_source_name(stack_object),
                source_id=source_id_of(stack_object),
            ):
                continue
            if owed > 0:
                game.counter(target)

    return effect


# --------------------------------------------------------------------------
# "Each player may exile their hand and draw a number of cards equal to the
# amount of {E} paid this way." (Wheel of Potential)
# --------------------------------------------------------------------------

_EXILE_HAND_AND_DRAW_PAID_RE = re.compile(
    r"^(?P<lead>.+?)\s+each player may exile their hand and draw a number of cards equal to "
    r"the amount of \{e\} paid this way\.(?:\s+if (?P<k>\S+) or more \{e\} was paid this way, "
    r"you may play cards you own exiled this way until the end of your next turn\.)?$",
    re.IGNORECASE,
)


@functools.cache
def _exile_hand_plan(text: str) -> tuple[Any, int | None] | None:
    from ..numbers import parse_count
    from .effects.dispatch import _spell_effect_or_notice
    from .effects.text import _strip_non_effect_preamble
    from .effects.tokens import _is_notice_only

    whole = " ".join(_strip_non_effect_preamble(text).strip().split())
    match = _EXILE_HAND_AND_DRAW_PAID_RE.fullmatch(whole)
    if match is None:
        return None
    lead = _spell_effect_or_notice(match.group("lead"))
    if lead is None or _is_notice_only(lead):
        return None
    threshold = None
    if match.group("k") is not None:
        threshold = parse_count(match.group("k"))
        if threshold is None:
            return None
    return lead, threshold


def exile_hand_and_draw_paid_effect(text: str) -> Any:
    """ "<pay any amount of {E}>. Each player may exile their hand and draw a
    number of cards equal to the amount of {E} paid this way. If N or more {E}
    was paid this way, you may play cards you own exiled this way until the
    end of your next turn." (Wheel of Potential): starting with the
    controller, each player in turn order chooses (CR 608.2d) whether to
    exile their hand and, if so, draws the energy paid (CR 608.2c, CR 121.2);
    at the threshold, the controller may play the cards they own that were
    exiled this way (CR 601.3, CR 305.2)."""
    if "each player may exile their hand" not in text.lower():
        return None
    plan = _exile_hand_plan(text)
    if plan is None:
        return None
    lead, threshold = plan

    def effect(game: "Game", stack_object: Any) -> None:
        from .casting.permissions import PlayAction

        lead(game, stack_object)
        paid = game.recorded_count() or 0
        controller = _controller(game, stack_object)
        name, source_id = _source_name(stack_object), source_id_of(stack_object)
        mine: list[CardState] = []
        for player in _starting_with(game, controller.username):
            if not game.may(
                player,
                f"exile your hand and draw {paid} cards",
                source=name,
                source_id=source_id,
                cards=tuple(player.hand),
            ):
                continue
            exiled = [game.exile_permanent(state) for state in list(player.hand)]
            if player.username == controller.username:
                mine = [state for state in exiled if state.owner == controller.username]
            game.draw_cards(player, paid)
        if threshold is not None and paid >= threshold:
            for state in mine:
                game.grant_play_permission(
                    state,
                    controller.username,
                    action=PlayAction.PLAY,
                    source_name=name,
                    zone=Zone.EXILE,
                    rule="CR 601.3",
                    until_end_of_turn=False,
                    expires_end_of_next_turn=True,
                )

    return effect


@SPELL_TEXT.rung("s23")
def _parse_exile_hand_and_draw_paid_spell(text: str) -> Any:
    """`exile_hand_and_draw_paid_effect` as a spell's whole text."""
    return exile_hand_and_draw_paid_effect(text)
