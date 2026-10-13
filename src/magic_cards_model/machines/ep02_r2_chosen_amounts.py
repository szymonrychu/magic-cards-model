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
from .effects._chains import ABILITY_TEXT, FORWARD, MIXED_CLAUSE

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
    r"^(?:you may )?(?P<verb>tap|return|reveal) any number of (?P<desc>.+?)"
    r"(?P<where> you control(?: to (?:their|its) owners?'s? hands?)?"
    r"| from your hand| in your hand)$",
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


def _permanent_matcher(description: str) -> tuple[bool, Callable[..., bool]] | None:
    """`(untapped_only, predicate)` for "untapped creatures", "Mountains"."""
    from .targeting import permanent_description

    text = description.strip()
    untapped = text.lower().startswith("untapped ")
    if untapped:
        text = text[len("untapped ") :]
    requirement = permanent_description(_singular(text))
    if requirement is None:
        return None

    def matches(game: "Game", controller: str, state: CardState) -> bool:
        return requirement.rejects(state, controller, game) is None

    return untapped, matches


@functools.cache
def _any_number_plan(clause: str) -> tuple[str, Callable[..., bool], bool] | None:
    match = _ANY_NUMBER_RE.fullmatch(clause.strip().rstrip("."))
    if match is None:
        return None
    verb = match.group("verb").lower()
    where = match.group("where").strip().lower()
    description = match.group("desc")
    if verb == "reveal":
        if where == "you control":
            return None
        hand = _hand_card_matcher(description)
        return None if hand is None else ("reveal", hand, False)
    if not where.startswith("you control"):
        return None
    to_hand = " to " in where
    if (verb == "return") != to_hand:
        return None
    permanent = _permanent_matcher(description)
    if permanent is None:
        return None
    untapped, predicate = permanent
    if verb == "tap" and not untapped:
        return None
    return verb, predicate, untapped


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
    verb, predicate, untapped = plan
    player = _controller(game, stack_object)
    if verb == "reveal":
        candidates = [s for s in player.hand if predicate(game, player.username, s)]
    else:
        candidates = [
            s
            for s in game.permanents_controlled_by(player.username)
            if predicate(game, player.username, s) and not (untapped and s.tapped)
        ]
    chosen = choose_any_number(game, stack_object, player, candidates, clause.strip().rstrip("."))
    done: list[CardState] = []
    for state in chosen:
        if verb == "tap":
            if not state.tapped and state.zone is Zone.BATTLEFIELD and game.tap_permanent(state):
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
    "Reveal any number of <cards> from your hand" (CR 107.1c, CR 701.26a,
    CR 701.20a): the controller chooses, the chosen objects are tapped,
    returned or revealed, and how many really were is recorded for a later
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
    r"^(?:then )?(?:you may )?pay any amount of (?P<what>\{e\}|mana)$", re.IGNORECASE
)


@MIXED_CLAUSE.rung("s32", for_spell=FORWARD)
def _parse_pay_any_amount_clause(clause: str, *, for_spell: bool) -> Any:
    """ "[You may] pay any amount of {E}" (CR 107.14) / "Pay any amount of
    mana" (CR 118.3): the player chooses the amount, up to what they can pay,
    pays it, and the amount paid is recorded for a later "that many" / "for
    each {E} paid this way" (CR 608.2c)."""
    if "any amount of" not in clause.lower():
        return None
    match = _PAY_ANY_AMOUNT_RE.fullmatch(clause.strip().rstrip("."))
    if match is None:
        return None
    energy = match.group("what").lower() == "{e}"

    def effect(game: "Game", stack_object: Any) -> None:
        player = _controller(game, stack_object)
        if energy:
            paid = game.pay_any_amount_of_energy(
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
