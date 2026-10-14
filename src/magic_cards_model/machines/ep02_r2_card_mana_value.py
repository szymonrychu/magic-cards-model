"""EP-02 R2 T3: the mana value of a spell or a card as an amount.

"Gain life equal to that spell's mana value" (the spell a cast trigger names),
"create X Thrull tokens, where X is that spell's mana value", "reveal the top
card of your library and put that card into your hand. You lose life equal to
its mana value", "mill a card, then draw cards equal to the milled card's mana
value", "discard a card at random. If you do, ~ deals damage equal to that
card's mana value to each creature".

`ep02_r1_moved_card_stat` reads a characteristic of something the same text
moved (a countered spell, a returned card). This module adds the objects whose
mana value a text spends that nothing was moved *away from*:

- the spell a cast trigger names (`cast_event_spell`), read as it was on the
  stack when it was cast - an {X} in its cost counts as the announced value
  (CR 202.3e) and the value is taken once, as the effect applies (CR 608.2h);
- the card a text reveals (the top card of a library, a card at random from a
  hand, cards until a nonland card), mills, discards at random or exiles
  (CR 701.20a, CR 701.17a, CR 701.9b), read as the card it is: a card that
  moved is a new object (CR 400.7), so its mana value comes off its mana cost
  (CR 202.3), 0 for a land (CR 202.3a);
- the whole shape those sentences share - openers that fix the card, a
  following sentence that spends its mana value, "if you do" / "otherwise" /
  "you may repeat this process any number of times" - compiled into one
  effect, with every amount sentence read by `ep02_r1_moved_card_stat` (which
  reads `amount_sentences`).

`parse_card_phrase` and `cast_event_spell` are the public entry points a task
that spends a spell's or a card's mana value as another kind of amount (look at
the top X, scry X) reuses.
"""

import functools
import re
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from random import Random
from typing import TYPE_CHECKING, Any

from magic_cards_model.text_norm import collapsed

from ..models.card_state import CardState
from ..models.player import Player
from ..models.zone import Zone
from ..numbers import parse_count
from .amount_sentences import parse_create, parse_life_clause, split_where_x, token_maker
from .ep02_r1_moved_card_stat import (
    _IF_YOU_DO_RE,
    Moved,
    Phrase,
    ResolutionStep,
    State,
    _amount_step,
    _clean,
    _opening_step,
    _step_delegate_to_target,
    card_snapshot,
    parse_moved_phrase,
)
from .ep02_r2_devotion_domain_party import CHOOSE_TARGET_RE

if TYPE_CHECKING:
    from ..models.game import Game

# --------------------------------------------------------------------------
# The run state
# --------------------------------------------------------------------------


@dataclass
class RunState(State):
    """`State` plus what the shapes of this module remember."""

    card: CardState | None = None
    """The card an opener revealed, milled, discarded or exiled."""
    revealed: list[CardState] = field(default_factory=list)
    branch: bool = False
    """The result of the last "if" / "if you do": what "otherwise" negates."""
    chooser: str | None = None
    """The player who made a choice another sentence refers to ("that player")."""
    coin: bool | None = None
    """The result of the coin flip this text made: True for a win (CR 705.1)."""


def parse_card_phrase(phrase: str) -> Phrase | None:
    """ "that spell's mana value", "the milled card's mana value", "the
    revealed card's mana value", "that card's mana value", "its mana value",
    "the card's mana value" as the `Phrase` the moved-card reader spends."""
    found = parse_moved_phrase(phrase)
    return found if found is not None and found.stat == "mana value" else None


def cast_event_spell(game: "Game", stack_object: Any) -> Moved | None:
    """The spell a cast trigger names, as it was when it was cast.

    Its mana value is the one the cast event recorded off the stack, an {X} in
    the cost counted as the value announced for it (CR 202.3e); once the spell
    has resolved or been countered an {X} would count as 0, but the trigger is
    about the spell as it was cast (CR 608.2h)."""
    event = getattr(stack_object, "event", None)
    if event is None or event.subject_id is None:
        return None
    spell = game.find_by_id(event.subject_id)
    if spell is None:
        return None
    base = card_snapshot(game, spell)
    mana_value = event.amount if event.amount is not None else base.mana_value
    controller = base.controller or event.player
    return replace(base, mana_value=int(mana_value), controller=controller)


def _name_and_id(stack_object: Any) -> tuple[str | None, str | None]:
    from .decisions import source_id_of

    name = getattr(stack_object, "source_name", None) or getattr(stack_object, "name", None)
    return name, source_id_of(stack_object)


def _random_pick(game: "Game", cards: list[CardState], label: str) -> CardState:
    """One of `cards` at random, seeded the way every random choice of the
    engine is so that a replay reproduces it."""
    rng = Random(f"{game.shuffle_seed}:{game.shuffles_performed}:{label}")  # noqa: S311
    game.shuffles_performed += 1
    return rng.choice(cards)


# --------------------------------------------------------------------------
# Openers: they fix the card the following sentences refer to
# --------------------------------------------------------------------------

_REVEAL_TOP_RE = re.compile(
    r"^(?P<may>you may )?reveal the top card of your library"
    r"(?P<hand>,? and put (?:that card|it) into your hand)?(?:,? then (?P<rest>.+))?$",
    re.IGNORECASE,
)
_SCRY_REVEAL_RE = re.compile(
    r"^scry (?P<n>\w+), then reveal the top card of your library$", re.IGNORECASE
)
_MILL_ONE_RE = re.compile(
    r"^(?:(?P<who>target player) )?mills? a card(?:,? then (?P<rest>.+))?$", re.IGNORECASE
)
_DISCARD_RANDOM_RE = re.compile(
    r"^discard a card at random(?:,? then (?P<rest>.+))?$", re.IGNORECASE
)
_REVEAL_RANDOM_HAND_RE = re.compile(
    r"^(?P<who>target player|target opponent) reveals a card at random from their hand"
    r"(?:,? then (?P<rest>.+))?$",
    re.IGNORECASE,
)
_REVEAL_UNTIL_NONLAND_RE = re.compile(
    r"^reveal cards from the top of your library until you reveal a nonland card$",
    re.IGNORECASE,
)
_COUNTER_THAT_SPELL_RE = re.compile(r"^counter that spell$", re.IGNORECASE)
_CHANGE_TARGET_RE = re.compile(
    r"^change the target of target spell with a single target$", re.IGNORECASE
)
_EACH_PLAYER_REVEAL_RE = re.compile(
    r"^each player reveals the top card of their library, loses life equal to that card's "
    r"mana value, then puts it into their hand$",
    re.IGNORECASE,
)


@functools.cache
def _shared_step(which: str, sentence: str) -> Any:
    """The step `ep02_r2_revealed_this_way` builds for `sentence`: the one
    interpreter of "reveal the top card", "reveal cards until ...", "discard a
    card at random" and "mill a card" (it is imported here, not the reverse)."""
    from . import ep02_r2_revealed_this_way as plan

    regex, build = {
        "top": (plan._REVEAL_TOP_RE, plan._reveal_top),
        "until": (plan._REVEAL_UNTIL_RE, plan._reveal_until),
        "discard": (plan._DISCARD_RANDOM_RE, plan._discard_random),
        "mill": (plan._MILL_RE, plan._mill_step),
    }[which]
    match = regex.fullmatch(sentence)
    assert match is not None
    step = build(match)
    assert step is not None
    return step


def _run_shared(which: str, sentence: str, game: "Game", stack_object: Any, player: Player) -> Any:
    """Run the shared step as `player` (the one who reveals, mills or discards) and return
    the plan context it filled in."""
    from .ep02_r2_revealed_this_way import _Ctx

    ctx = _Ctx(actor=player, controller=player)
    _shared_step(which, sentence)(game, stack_object, ctx)
    return ctx


def _step_reveal_top(*, hand: bool, may: bool) -> ResolutionStep:
    def step(game: "Game", stack_object: Any, state: State) -> bool:
        assert isinstance(state, RunState)
        player = game.controller_of(stack_object)
        if not player.library:
            return False  # CR 609.3: no card to reveal, move or measure
        name, source_id = _name_and_id(stack_object)
        if may and not game.may(
            player, "reveal the top card of your library", source=name, source_id=source_id
        ):
            return False
        ctx = _run_shared("top", "reveal the top card of your library", game, stack_object, player)
        top = ctx.revealed[0]
        state.referent = card_snapshot(game, top)  # CR 608.2h: before it moves
        state.card = top
        state.did = True
        if hand:
            player.add(top, Zone.HAND)
        return True

    return step


def _step_scry(count: int) -> ResolutionStep:
    def step(game: "Game", stack_object: Any, state: State) -> bool:
        name, source_id = _name_and_id(stack_object)
        game.scry(game.controller_of(stack_object), count, source=name, source_id=source_id)
        return True

    return step


def _chain(first: ResolutionStep, second: ResolutionStep) -> ResolutionStep:
    def step(game: "Game", stack_object: Any, state: State) -> bool:
        return first(game, stack_object, state) and second(game, stack_object, state)

    return step


def _step_mill_one(who: str | None) -> ResolutionStep:
    def step(game: "Game", stack_object: Any, state: State) -> bool:
        assert isinstance(state, RunState)
        if who:
            target = state.next_target(game, stack_object)
            if not isinstance(target, Player):
                return False
            player = target
        else:
            player = game.controller_of(stack_object)
        ctx = _run_shared("mill", "you mill a card", game, stack_object, player)
        state.player = player.username
        milled = ctx.moved.get("milled", [])
        if milled:
            state.card = milled[0]
            state.referent = card_snapshot(game, milled[0])
            state.did = True
        return True

    return step


def _step_discard_random(game: "Game", stack_object: Any, state: State) -> bool:
    assert isinstance(state, RunState)
    player = game.controller_of(stack_object)
    ctx = _run_shared("discard", "discard a card at random", game, stack_object, player)
    state.player = player.username
    discarded = ctx.moved.get("discarded", [])
    if discarded:
        state.referent = card_snapshot(game, discarded[0])
        state.card = discarded[0]
        state.did = discarded[0].zone is not Zone.HAND
    return True


def _step_reveal_random_from_hand(game: "Game", stack_object: Any, state: State) -> bool:
    assert isinstance(state, RunState)
    target = state.next_target(game, stack_object)
    if not isinstance(target, Player):
        return False
    state.player = target.username
    hand = list(target.hand)
    if not hand:
        return True
    name, _ = _name_and_id(stack_object)
    card = _random_pick(game, hand, "reveal-at-random")
    game.reveal(card, source=name)
    state.referent = card_snapshot(game, card)
    state.card = card
    state.did = True
    return True


def _step_reveal_until_nonland(game: "Game", stack_object: Any, state: State) -> bool:
    assert isinstance(state, RunState)
    player = game.controller_of(stack_object)
    ctx = _run_shared(
        "until",
        "reveal cards from the top of your library until you reveal a nonland card",
        game,
        stack_object,
        player,
    )
    state.revealed.extend(ctx.revealed)
    if ctx.stoppers:
        state.card = ctx.stoppers[0]
        state.referent = card_snapshot(game, ctx.stoppers[0])
        state.did = True
    return True


def _step_noop(game: "Game", stack_object: Any, state: State) -> bool:
    return True


def _step_counter_that_spell(game: "Game", stack_object: Any, state: State) -> bool:
    event = getattr(stack_object, "event", None)
    spell = None if event is None else game.find_by_id(event.subject_id)
    state.referent = cast_event_spell(game, stack_object)
    if isinstance(spell, CardState) and spell.zone is Zone.STACK:
        game.counter(spell)
        state.did = True
    return True


def _step_each_player_reveals_loses_life_takes(
    game: "Game", stack_object: Any, state: State
) -> bool:
    from .effects._common import _players_in_apnap_order

    name, _ = _name_and_id(stack_object)
    for player in _players_in_apnap_order(game):
        if not player.library:
            continue
        top = player.library[0]
        game.reveal(top, source=name)
        amount = int(game.last_known_mana_value(top))
        game.lose_life(player, amount) if amount > 0 else None
        player.add(top, Zone.HAND)
    return True


#: Openers that also spend the card's mana value in the same sentence.
_SPENDING_OPENERS = frozenset({_step_each_player_reveals_loses_life_takes})


def _opener(sentence: str, *, for_spell: bool) -> tuple[ResolutionStep, str | None, str] | None:
    """`(step, tail, subject)`: the step an opening sentence is, the ", then
    ..." tail it carries, and the subject a subject-less tail inherits."""
    if m := _SCRY_REVEAL_RE.fullmatch(sentence):
        count = parse_count(m.group("n"))
        if count is None:
            return None
        return _chain(_step_scry(count), _step_reveal_top(hand=False, may=False)), None, ""
    if m := _REVEAL_TOP_RE.fullmatch(sentence):
        step = _step_reveal_top(hand=bool(m.group("hand")), may=bool(m.group("may")))
        return step, m.group("rest"), "you"
    if m := _MILL_ONE_RE.fullmatch(sentence):
        return (
            _step_mill_one(m.group("who")),
            m.group("rest"),
            "that player" if m.group("who") else "you",
        )
    if m := _DISCARD_RANDOM_RE.fullmatch(sentence):
        return _step_discard_random, m.group("rest"), "you"
    if m := _REVEAL_RANDOM_HAND_RE.fullmatch(sentence):
        return _step_reveal_random_from_hand, m.group("rest"), "that player"
    if _REVEAL_UNTIL_NONLAND_RE.fullmatch(sentence):
        return _step_reveal_until_nonland, None, ""
    if CHOOSE_TARGET_RE.fullmatch(sentence):
        return _step_noop, None, ""
    if _COUNTER_THAT_SPELL_RE.fullmatch(sentence):
        return _step_counter_that_spell, None, ""
    if _CHANGE_TARGET_RE.fullmatch(sentence):
        step = _step_delegate_to_target(f"{sentence}.", for_spell=for_spell)
        return None if step is None else (step, None, "")
    if _EACH_PLAYER_REVEAL_RE.fullmatch(sentence):
        return _step_each_player_reveals_loses_life_takes, None, ""
    first = _opening_step(sentence, for_spell=for_spell)
    if first is not None:
        return first[0], first[1], "you"
    return None


# --------------------------------------------------------------------------
# Sentences that act on the card an opener fixed
# --------------------------------------------------------------------------

_PUT_IN_HAND_RE = re.compile(r"^put (?:that|the) (?:nonland )?card into your hand$", re.IGNORECASE)
_PUT_NONLAND_AND_REST_RE = re.compile(
    r"^put the nonland card into your hand and the rest on the bottom of your library "
    r"in any order$",
    re.IGNORECASE,
)
_PUT_REVEALED_BOTTOM_RE = re.compile(
    r"^put all cards revealed this way on the bottom of your library in any order$",
    re.IGNORECASE,
)
_CAST_FREE_RE = re.compile(
    r"^you may cast (?:it|that card) without paying its mana cost$", re.IGNORECASE
)  # the cast helper asks the "may" itself
_OPPONENT_PUTS_IN_GRAVEYARD_RE = re.compile(
    r"^any opponent may have you put that card into your graveyard$", re.IGNORECASE
)
_REPEAT_RE = re.compile(r"^you may repeat this process any number of times$", re.IGNORECASE)
_IF_PLAYER_DOES_RE = re.compile(r"^if a player does,? (?P<rest>.+)$", re.IGNORECASE)
_IF_KIND_RE = re.compile(
    r"^if it's an? (?P<kinds>[a-z]+(?: or [a-z]+)*) card,? (?P<rest>.+)$", re.IGNORECASE
)
_OTHERWISE_RE = re.compile(r"^otherwise,? (?P<rest>.+)$", re.IGNORECASE)
_IF_COND_RE = re.compile(r"^if (?P<cond>[^,]+), (?P<rest>.+)$", re.IGNORECASE)
_TRAILING_IF_RE = re.compile(r"^(?P<body>.+?) if (?P<cond>this creature (?:is|isn't) saddled)$")
_MAY_PREFIX_RE = re.compile(r"^you may (?:have )?(?P<rest>.+)$", re.IGNORECASE)
_LOOK_TOP_X_RE = re.compile(
    r"^(?P<verb>look at|reveal) the top x cards of your library, where x is "
    r"(?:that|the) spell's mana value$",
    re.IGNORECASE,
)
_CAST_AMONG_RE = re.compile(
    r"^you may cast a spell with mana value (?P<cmp>less than x|x or less) from among "
    r"(?:them|cards revealed this way) without paying its mana cost$",
    re.IGNORECASE,
)
_REST_BOTTOM_RANDOM_RE = re.compile(
    r"^put the rest on the bottom of your library in a random order$", re.IGNORECASE
)


def _bottom(
    game: "Game", player: Player, cards: list[CardState], *, name: str | None, source_id: str | None
) -> None:
    """ "...on the bottom of your library in any order": the owner arranges
    them (CR 401.4)."""
    if not cards:
        return
    for card in game.ask_library_bottom_order(player, cards, source=name, source_id=source_id):
        player.move(card, Zone.LIBRARY)


def _step_put_in_hand(game: "Game", stack_object: Any, state: State) -> bool:
    assert isinstance(state, RunState)
    if state.card is not None and state.card.zone is Zone.LIBRARY:
        game.controller_of(stack_object).add(state.card, Zone.HAND)
    return True


def _step_put_nonland_in_hand_rest_bottom(game: "Game", stack_object: Any, state: State) -> bool:
    assert isinstance(state, RunState)
    player = game.controller_of(stack_object)
    name, source_id = _name_and_id(stack_object)
    if state.card is not None:
        player.add(state.card, Zone.HAND)
    _bottom(
        game,
        player,
        [card for card in state.revealed if card is not state.card],
        name=name,
        source_id=source_id,
    )
    return True


def _step_put_revealed_bottom(game: "Game", stack_object: Any, state: State) -> bool:
    assert isinstance(state, RunState)
    name, source_id = _name_and_id(stack_object)
    _bottom(
        game, game.controller_of(stack_object), list(state.revealed), name=name, source_id=source_id
    )
    return True


def _card_of(game: "Game", state: RunState) -> CardState | None:
    """The card the text is about: the one an opener of this module fixed, else
    the one a moved-card opener of `ep02_r1_moved_card_stat` snapshotted."""
    if state.card is not None:
        return state.card
    if state.referent is None or state.referent.card_id is None:
        return None
    found = game.find_by_id(state.referent.card_id)
    return found if isinstance(found, CardState) else None


def _step_cast_free(game: "Game", stack_object: Any, state: State) -> bool:
    assert isinstance(state, RunState)
    card = _card_of(game, state)
    if card is None:
        return True
    name, source_id = _name_and_id(stack_object)
    game.may_cast_during_resolution(
        card,
        game.controller_of(stack_object).username,
        prompt=f"cast {card.name} without paying its mana cost",
        source=name,
        source_id=source_id,
        source_name=name or card.name,
        rule="CR 608.2g",
    )
    return True


def _step_opponent_puts_in_graveyard(game: "Game", stack_object: Any, state: State) -> bool:
    """ "Any opponent may have you put that card into your graveyard": each
    opponent in turn order is asked; the first to say yes decides (CR 101.4)."""
    assert isinstance(state, RunState)
    from .effects._common import _players_in_apnap_order

    card = state.card
    name, source_id = _name_and_id(stack_object)
    controller = game.controller_of(stack_object).username
    state.did = False
    if card is None or card.zone is not Zone.LIBRARY:
        return True
    for player in _players_in_apnap_order(game):
        if player.username == controller:
            continue
        if game.may(
            player,
            f"have {controller} put {card.name} into their graveyard",
            source=name,
            source_id=source_id,
            cards=(card,),
        ):
            game.put_into_graveyard(card)
            state.did = True
            state.chooser = player.username
            state.player = player.username
            break
    return True


def _step_look_top_x_cast_free(verb: str, *, strictly_less: bool) -> ResolutionStep:
    """ "Look at / reveal the top X cards of your library, where X is that
    spell's mana value. You may cast a spell with mana value less than X /
    X or less from among them without paying its mana cost. Put the rest on the
    bottom of your library in a random order." (CR 608.2g, CR 118.9)."""
    from .effects.library import _look_at_top_cast_free_bottom_rest

    def step(game: "Game", stack_object: Any, state: State) -> bool:
        assert isinstance(state, RunState)
        name, source_id = _name_and_id(stack_object)
        x = max(state.referent.mana_value, 0) if state.referent is not None else 0
        _look_at_top_cast_free_bottom_rest(
            game,
            game.controller_of(stack_object),
            x,
            ceiling=x if strictly_less else x + 1,
            prompt=(
                f"cast a spell with mana value {'less than' if strictly_less else 'at most'} "
                f"{x} from among them without paying its mana cost"
            ),
            source_name=name,
            source_id=source_id,
            reveal=verb == "reveal",
        )
        return True

    return step


def _guarded(step: ResolutionStep, test: Callable[["Game", Any, RunState], bool]) -> ResolutionStep:
    """Run `step` only when `test` holds, remembering the verdict for a
    following "otherwise"."""

    def guarded(game: "Game", stack_object: Any, state: State) -> bool:
        assert isinstance(state, RunState)
        state.branch = test(game, stack_object, state)
        return step(game, stack_object, state) if state.branch else True

    return guarded


def _maybe(step: ResolutionStep) -> ResolutionStep:
    """ "You may <do it>": the controller is asked first (CR 608.2d)."""

    def asked(game: "Game", stack_object: Any, state: State) -> bool:
        name, source_id = _name_and_id(stack_object)
        if not game.may(
            game.controller_of(stack_object), "do it", source=name, source_id=source_id
        ):
            return True
        return step(game, stack_object, state)

    return asked


def _step_repeat(previous: list[ResolutionStep]) -> ResolutionStep:
    """ "You may repeat this process any number of times": the whole text so
    far again, each time the controller agrees and the process still does
    something."""

    def step(game: "Game", stack_object: Any, state: State) -> bool:
        name, source_id = _name_and_id(stack_object)
        controller = game.controller_of(stack_object)
        while game.may(controller, "repeat this process", source=name, source_id=source_id):
            again = RunState()
            for earlier in previous:
                if not earlier(game, stack_object, again):
                    break
            if not again.did:
                break
        return True

    return step


def _condition_test(condition: str) -> Callable[["Game", Any, RunState], bool] | None:
    from .conditions import ConditionContext, claims, read_condition

    if not claims(condition):
        return None

    def test(game: "Game", stack_object: Any, state: RunState) -> bool:
        source = stack_object if isinstance(stack_object, CardState) else stack_object.source(game)
        context = ConditionContext(game, game.controller_of(stack_object).username, source)
        return bool(read_condition(context, condition))

    return test


# --------------------------------------------------------------------------
# The whole text
# --------------------------------------------------------------------------

#: A keyword ability's line left behind once its reminder text is stripped
#: ("Storm (When you cast this spell, ...)"): a separate ability, read elsewhere.
_KEYWORD_ONLY = frozenset({"storm", "cascade", "rebound", "cipher", "convoke", "delve"})


def _unwrap_then(sentence: str, rest: str | None, subject: str) -> list[str]:
    if not rest:
        return [sentence]
    tail = rest if rest.split()[0].lower() in {"you", "target", "each"} else f"{subject} {rest}"
    return [tail]


def _compile(sentences: list[str], *, for_spell: bool) -> list[ResolutionStep] | None:
    steps: list[ResolutionStep] = []
    event_spell_named = any("that spell" in sentence.lower() for sentence in sentences)
    opened = False
    uses_amount = False
    queue = list(sentences)
    position = 0
    last_expression: str | None = None
    event_spell = False
    while position < len(queue):
        sentence = queue[position]
        position += 1
        guard: Callable[[Game, Any, RunState], bool] | None = None

        # Look/reveal the top X cards (Kiora, Sunbird's Invocation): three sentences.
        if (look := _LOOK_TOP_X_RE.fullmatch(sentence)) and position + 1 < len(queue) + 0:
            cast = _CAST_AMONG_RE.fullmatch(queue[position]) if position < len(queue) else None
            rest = (
                _REST_BOTTOM_RANDOM_RE.fullmatch(queue[position + 1])
                if position + 1 < len(queue)
                else None
            )
            if cast is None or rest is None:
                return None
            steps.append(
                _step_look_top_x_cast_free(
                    look.group("verb").lower(), strictly_less=cast.group("cmp").startswith("less")
                )
            )
            position += 2
            uses_amount = True
            event_spell = event_spell or not opened
            continue

        if _REPEAT_RE.fullmatch(sentence):
            if not steps:
                return None
            steps.append(_step_repeat(list(steps)))
            continue

        did_match = _IF_YOU_DO_RE.fullmatch(sentence) or _IF_PLAYER_DOES_RE.fullmatch(sentence)
        if m := did_match:
            sentence, guard = m.group("rest"), lambda g, so, s: s.did  # noqa: E731
        elif m := _OTHERWISE_RE.fullmatch(sentence):
            sentence, guard = m.group("rest"), lambda g, so, s: not s.branch  # noqa: E731
        elif m := _IF_KIND_RE.fullmatch(sentence):
            kinds = [kind.lower() for kind in m.group("kinds").split(" or ")]
            sentence = m.group("rest")
            guard = lambda g, so, s, kinds=kinds: (  # noqa: E731
                s.referent is not None and any(s.referent.is_a(kind) for kind in kinds)
            )
        elif (m := _IF_COND_RE.fullmatch(sentence)) and (
            test := _condition_test(m.group("cond").lower())
        ):
            sentence, guard = m.group("rest"), test
        elif m := _TRAILING_IF_RE.fullmatch(sentence):
            test = _condition_test(m.group("cond").lower())
            if test is None:
                return None
            sentence, guard = m.group("body"), test
        if _FLIP_RE.fullmatch(sentence):
            steps.append(_guarded(_step_flip, guard) if guard is not None else _step_flip)
            continue
        if flip_result := _FLIP_RESULT_RE.fullmatch(sentence):
            consequence = flip_result.group("rest")
            if position < len(queue) and _NEW_TARGETS_RE.fullmatch(queue[position]):
                consequence = f"{consequence}, {queue[position].lower()}"
                position += 1
            if not _reflexive_consequence_reads(consequence):
                return None
            uses_amount = uses_amount or "mana value" in consequence.lower()
            event_spell = event_spell or not opened
            steps.append(_step_reflexive_on_flip(consequence, win=flip_result["result"] == "win"))
            continue
        may = False
        if (
            _opener(sentence, for_spell=for_spell) is None
            and (may_match := _MAY_PREFIX_RE.fullmatch(sentence))
            and not any(
                own.fullmatch(sentence) for own in (_REVEAL_TOP_RE, _REPEAT_RE, _CAST_FREE_RE)
            )
        ):
            sentence, may = may_match.group("rest"), True

        if re.match(r"^(?:gain|lose) ", sentence, re.IGNORECASE):
            sentence = f"you {sentence}"
        if "that much life" in sentence and last_expression:
            sentence = sentence.replace("that much life", f"life equal to {last_expression}")

        step: ResolutionStep | None = None
        if (first := _opener(sentence, for_spell=for_spell)) is not None:
            step, tail, subject = first
            opened = True
            uses_amount = uses_amount or step in _SPENDING_OPENERS
            if event_spell_named and sentence.lower().startswith(
                ("you may sacrifice", "sacrifice")
            ):
                step = _keep_referent(step)
            steps.append(_guarded(step, guard) if guard is not None else step)
            if tail:
                queue[position:position] = _unwrap_then(sentence, tail, subject)
            continue
        if _PUT_NONLAND_AND_REST_RE.fullmatch(sentence):
            step = _step_put_nonland_in_hand_rest_bottom
        elif _PUT_REVEALED_BOTTOM_RE.fullmatch(sentence):
            step = _step_put_revealed_bottom
        elif _PUT_IN_HAND_RE.fullmatch(sentence):
            step = _step_put_in_hand
        elif _CAST_FREE_RE.fullmatch(sentence):
            step = _step_cast_free
        elif _OPPONENT_PUTS_IN_GRAVEYARD_RE.fullmatch(sentence):
            step = _step_opponent_puts_in_graveyard
        elif (cycled := _x_tokens_of_the_trigger(sentence)) is not None:
            step = cycled
            uses_amount = True
        else:
            if not opened and not for_spell:
                event_spell = True
            step = _amount_step(sentence, for_spell=for_spell, opener=opened or event_spell)
            if step is None:
                return None
            uses_amount = True
            life = parse_life_clause(sentence)
            if life is not None and life.kind == "equal":
                last_expression = life.expr
        if may:
            step = _maybe(step)
        steps.append(_guarded(step, guard) if guard is not None else step)

    if not uses_amount:
        return None
    if event_spell:
        steps.insert(0, _step_event_spell)
    return steps


_CREATE_X_TOKENS_RE = re.compile(r"^create an? x/x .+ tokens?(?: with .+)?$", re.IGNORECASE)


def _x_tokens_of_the_trigger(sentence: str) -> ResolutionStep | None:
    """ "Create an X/X blue Shark creature token with flying" with no "where X
    is": the X the triggering ability's cost announced (Shark Typhoon's "When
    you cycle this card" - the X paid for `Cycling {X}{1}{U}`, carried on the
    cycle event), else the X of the ability itself."""
    if _CREATE_X_TOKENS_RE.fullmatch(sentence) is None or split_where_x(sentence) is not None:
        return None
    created = parse_create(sentence)
    make = None if created is None or created[0] not in ("", "you") else token_maker(created[1])
    if make is None:
        return None

    def step(game: "Game", stack_object: Any, state: State) -> bool:
        event = getattr(stack_object, "event", None)
        amount = getattr(event, "amount", None)
        if amount is None:
            amount = getattr(stack_object, "x_value", 0)
        make(game, game.controller_of(stack_object).username, max(int(amount), 0))
        return True

    return step


_FLIP_RE = re.compile(r"^flip a coin$", re.IGNORECASE)
_FLIP_RESULT_RE = re.compile(
    r"^when you (?P<result>win|lose) the flip,? (?P<rest>.+)$", re.IGNORECASE
)
_NEW_TARGETS_RE = re.compile(r"^you may choose new targets for the copy$", re.IGNORECASE)


def _step_flip(game: "Game", stack_object: Any, state: State) -> bool:
    assert isinstance(state, RunState)
    state.coin = game.flip_coin(game.controller_of(stack_object))
    return True


def _step_reflexive_on_flip(consequence: str, *, win: bool) -> ResolutionStep:
    """ "When you win/lose the flip, <consequence>": CR 603.12's reflexive
    triggered ability, put on the stack after the flip with its own targets,
    carrying the triggering event so "that spell" still names the spell cast."""
    from .delayed import ReflexiveConsequence

    def step(game: "Game", stack_object: Any, state: State) -> bool:
        assert isinstance(state, RunState)
        if state.coin is not win:
            return True
        game.create_reflexive_trigger(
            text=_as_sentence(consequence),
            controller=game.controller_of(stack_object).username,
            source_id=getattr(stack_object, "source_id", None),
            source_name=getattr(stack_object, "source_name", "") or "",
            callback=ReflexiveConsequence(),
            event=getattr(stack_object, "event", None),
        )
        return True

    return step


def _keep_referent(step: ResolutionStep) -> ResolutionStep:
    """Run `step` without letting it replace the card the text is about (a
    sacrifice that is only a cost of a later "that spell")."""

    def kept(game: "Game", stack_object: Any, state: State) -> bool:
        saved = state.referent
        result = step(game, stack_object, state)
        state.referent = saved
        return result

    return kept


def _reflexive_consequence_reads(consequence: str) -> bool:
    from .effects import reflexive_consequence_effect

    return reflexive_consequence_effect(_as_sentence(consequence)) is not None


#: A card's own name in front of "deals": the reflexive reader knows the source
#: as "this creature".
_NAMED_SOURCE_RE = re.compile(r"^[A-Z][\w',-]*(?: (?:of |the )?[A-Z][\w',-]*)* (?=deals )")


def _as_sentence(consequence: str) -> str:
    text = _NAMED_SOURCE_RE.sub("this creature ", consequence.strip().rstrip("."))
    return f"{text[:1].upper()}{text[1:]}."


def _step_event_spell(game: "Game", stack_object: Any, state: State) -> bool:
    """The spell a cast trigger names is what "that spell" means until a
    sentence of the text fixes another card."""
    state.referent = cast_event_spell(game, stack_object)
    return True


def _owned_by_the_reveal_hand_lose_life_merge(sentences: list[str]) -> bool:
    """Exactly "reveal the top card ... put that card into your hand. You lose
    life equal to its mana value" is `effects.merges`'s own three-clause
    reader (Dark Confidant); only a repeat or other rider is read here."""
    from .effects.merges import (
        _PUT_THAT_CARD_INTO_YOUR_HAND_BARE_RE,
        _REVEAL_TOP_CARD_OF_LIBRARY_BARE_RE,
        _YOU_LOSE_LIFE_EQUAL_TO_THAT_CARDS_MANA_VALUE_RE,
    )

    # The merge sees "reveal ... and put" cut at the "and" into two clauses.
    parts = [
        piece.strip(" .")
        for sentence in sentences
        for piece in sentence.replace(" and put ", "\0put ").split("\0")
    ]
    return (
        len(parts) == 3
        and bool(_REVEAL_TOP_CARD_OF_LIBRARY_BARE_RE.fullmatch(parts[0]))
        and bool(_PUT_THAT_CARD_INTO_YOUR_HAND_BARE_RE.fullmatch(parts[1]))
        and bool(_YOU_LOSE_LIFE_EQUAL_TO_THAT_CARDS_MANA_VALUE_RE.fullmatch(parts[2]))
    )


@functools.cache
def card_mana_value_effect(text: str, *, for_spell: bool) -> Callable[["Game", Any], None] | None:
    """The effect of `text` when it spends the mana value of the spell a cast
    trigger names or of a card the text itself reveals, mills, discards or
    exiles, or `None` for anything else."""
    lowered = text.lower()
    if "mana value" not in lowered and not lowered.startswith("create an x/x "):
        return None
    from .effects.text import _plain_resolution_sentences, _strip_non_effect_preamble

    sentences = [
        _clean(sentence)
        for sentence in _plain_resolution_sentences(_strip_non_effect_preamble(collapsed(text)))
    ]
    sentences = [s for s in sentences if s and s.lower() not in _KEYWORD_ONLY]
    if not sentences or _owned_by_the_reveal_hand_lose_life_merge(sentences):
        return None
    steps = _compile(sentences, for_spell=for_spell)
    if steps is None:
        return None

    def effect(game: "Game", stack_object: Any) -> None:
        state = RunState()
        for step in steps:
            if not step(game, stack_object, state):
                return

    return effect
