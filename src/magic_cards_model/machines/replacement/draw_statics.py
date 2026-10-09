"""Draw replacement statics (CR 614.11, CR 121.6): "If you / a player would
draw a card [while <condition>], <replacement> instead."

The draw is raised as an `EventKind.DRAW` event by `Game.draw_cards`; a
replacement here sets `event.amount` (CR 121.2a) or zeroes it and performs the
substitute action itself.  Library-empty draws are replaced too (CR 614.11,
CR 121.6a): the event is raised before the library is consulted.

The substitute action is, wherever the engine's own effect reader already
performs the same words as an ordinary clause ("look at the top three cards ...
put one into your hand ..."), that reader - run on a synthetic ability the
replacement's source controls - so a rule is never written twice.
"""

import re
from collections.abc import Callable
from typing import TYPE_CHECKING

from ...models.card import Type
from ...models.card_state import CardState
from ...models.zone import Zone
from ..abilities import AbilityKind, TriggeredAbility, TriggerWord
from ..decisions import Decision, DecisionKind
from ..triggers.events import AbilityOnStack
from .model import (
    Apply,
    CardReplacement,
    EventKind,
    ReplaceableEvent,
    ReplacementEffect,
    ReplacementKind,
)
from .parse import strip_reminder_text

if TYPE_CHECKING:
    from ...models.game import Game

_DRAW_LINE_RE = re.compile(
    r"^(?:[^—]+— )?"
    r"(?:As long as this enchantment has (?P<n>\w+) or more (?P<kind>[a-z]+) counters on it, )?"
    r"if (?P<who>you|a player) would draw a card(?: while (?P<cond>[^,]+?))?, (?P<rest>.+)$",
    re.IGNORECASE | re.DOTALL,
)
_NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7}
_CONDITIONS: dict[str, Callable[["Game", CardState, ReplaceableEvent], bool]] = {
    "you have no cards in hand": lambda game, source, event: not event.player.hand,
    "your library has no cards in it": lambda game, source, event: not event.player.library,
}


def synthetic_ability(source: CardState, controller: str, text: str) -> AbilityOnStack:
    """An ability `source` is "resolving" for a replacement that performs a
    printed clause (the clause readers take a `(game, ability)` pair)."""
    return AbilityOnStack(
        kind=AbilityKind.TRIGGERED,
        ability=TriggeredAbility(
            raw=text, text=text, face=source.name, word=TriggerWord.WHEN, condition="", effect=text
        ),
        source_id=source.id,
        source_name=source.name,
        controller=controller,
    )


def _clause(rest: str) -> tuple[str, bool]:
    """The substitute clause of a draw replacement, and whether it is optional."""
    text = rest.strip()
    optional = text.lower().startswith("you may instead ")
    if optional:
        text = text[len("you may instead ") :]
    text = re.sub(r"^instead,? ", "", text, count=1, flags=re.IGNORECASE)
    text = re.sub(r" instead(?=[.,]|$)", "", text, count=1, flags=re.IGNORECASE)
    return text.strip().rstrip(".").strip(), optional


def _choose(game: "Game", username: str, prompt: str, options: tuple[str, ...], source: str) -> str:
    answer = game.ask(
        Decision(
            kind=DecisionKind.CHOOSE_A_QUALITY,
            player=username,
            prompt=prompt,
            source=source,
            options=options,
        )
    )
    assert isinstance(answer, str)
    return answer


def _other_players(game: "Game", name: str):
    return [p for p in game.players if p.username != name]


def _exile_top(game: "Game", owner, source: CardState, *, face_up: bool) -> CardState | None:
    if not owner.library:
        return None
    card = owner.library[0]
    game.exile_cards([card])
    card.face_up = face_up
    return card


def _custom_action(clause: str, source: CardState) -> Apply | None:  # noqa: C901
    text = clause.lower()
    if text in ("draw two cards", "you draw two cards"):

        def draw_two(game, src, event):
            event.amount += 1

        return draw_two
    if match := re.fullmatch(r"you draw two cards and you lose (\d+) life", text):
        life = int(match.group(1))

        def draw_two_lose(game, src, event):
            event.amount += 1
            game.lose_life(src.controller, life)

        return draw_two_lose
    if text == "you win the game":

        def win(game, src, event):
            event.amount = 0
            game.player_wins_the_game(src.controller)

        return win
    if text == "skip that draw":

        def skip(game, src, event):
            event.amount = 0

        return skip
    if text == "exile the top card of your library face down":

        def exile_own(game, src, event):
            event.amount = 0
            _exile_top(game, game.player(src.controller), src, face_up=False)

        return exile_own
    if text == "that player exiles the top card of one of their opponents' libraries face down":

        def exile_theirs(game, src, event):
            drawer = event.player
            event.amount = 0
            opponents = _other_players(game, drawer.username)
            if not opponents:
                return
            target = opponents[0]
            if len(opponents) > 1:
                names = tuple(p.username for p in opponents)
                pick = _choose(
                    game, drawer.username, "Exile the top card of whose library?", names, src.name
                )
                target = game.player(pick)
            _exile_top(game, target, src, face_up=False)

        return exile_theirs
    if text == "that player exiles that card face up":

        def exile_that(game, src, event):
            event.amount = 0
            _exile_top(game, event.player, src, face_up=True)

        return exile_that
    if text == (
        "reveal the top card of your library. if it's a creature card, put it into your "
        "graveyard. otherwise, draw a card"
    ):

        def reveal_creature_else_draw(game, src, event):
            player = game.player(src.controller)
            if not player.library:
                return  # nothing to reveal: the original draw (and its loss) stands
            top = player.library[0]
            game.reveal(top, src.name)
            if Type.CREATURE in top.types:
                event.amount = 0
                game.put_into_graveyard(top)
            # otherwise the draw this replaced simply happens (CR 614.5: this
            # effect gets no second opportunity at its own "draw a card").

        return reveal_creature_else_draw
    if text == (
        "they reveal it. then any other player may pay 2 life. if a player does, put that card "
        "into its owner's graveyard. otherwise, that player draws a card"
    ):

        def reveal_then_pay(game, src, event):
            drawer = event.player
            if not drawer.library:
                return
            top = drawer.library[0]
            game.reveal(top, src.name)
            for other in _other_players(game, drawer.username):
                if game.may_pay_life(other, 2, source=src.name):
                    event.amount = 0
                    game.put_into_graveyard(top)
                    return

        return reveal_then_pay
    if text.startswith("choose land or nonland and reveal cards from the top of your library"):

        def abundance(game, src, event):
            player = game.player(src.controller)
            event.amount = 0
            kind = _choose(game, player.username, "Land or nonland?", ("land", "nonland"), src.name)
            revealed, found = [], None
            for card in list(player.library):
                game.reveal(card, src.name)
                is_land = Type.LAND in card.types
                if is_land == (kind == "land"):
                    found = card
                    break
                revealed.append(card)
            if found is not None:
                player.move(found, Zone.HAND)
            for card in revealed:
                player.move(card, Zone.LIBRARY)  # below every other card (CR 401.2)
            if revealed:
                # "in a random order": shuffle just the revealed pile at the bottom.
                game.shuffle_library(player, keep=player.library[: -len(revealed)])

        return abundance
    return None


def _generic_action(clause: str, optional: bool) -> Apply | None:
    from ..effects import reflexive_consequence_effect

    effect_fn = reflexive_consequence_effect(clause)
    if effect_fn is None:
        return None

    def apply(game: "Game", source: CardState, event: ReplaceableEvent) -> None:
        # CR 121.6 / 614.6: the draw is replaced; "you" is whoever the effect's
        # source's controller is, "that player" the one who would have drawn.
        event.amount = 0
        controller = source.controller
        if optional and not game.may(controller, f"Instead: {clause}?", source=source.name):
            event.amount = 1
            return
        effect_fn(game, synthetic_ability(source, controller, clause))

    return apply


def _compile_draw_replacement(effect: ReplacementEffect) -> CardReplacement | None:
    if effect.kind is not ReplacementKind.IF_WOULD_INSTEAD or effect.from_trigger:
        return None
    rules = strip_reminder_text(effect.raw)[0].strip()
    match = _DRAW_LINE_RE.match(rules)
    if match is None:
        return None
    cond = match.group("cond")
    condition = _CONDITIONS.get(cond.lower()) if cond else None
    if cond and condition is None:
        return None
    clause, optional = _clause(match.group("rest"))
    custom = _custom_action(clause, None)
    action = custom or _generic_action(clause, optional)
    if action is None:
        return None
    if optional and custom is not None:
        inner = custom

        def action(game, source, event, _inner=inner, _clause=clause):  # noqa: F811
            if game.may(source.controller, f"Instead: {_clause}?", source=source.name):
                _inner(game, source, event)

    any_player = match.group("who").lower() == "a player"
    threshold = match.group("n")
    kind = match.group("kind")
    needed = _NUMBER_WORDS.get(threshold.lower()) if threshold else None
    if threshold and needed is None:
        return None

    def applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
        if event.kind is not EventKind.DRAW or event.player is None or event.amount <= 0:
            return False
        if not any_player and event.player.username != source.controller:
            return False
        if needed is not None and source.counter_count(kind) < needed:
            return False
        return condition is None or condition(game, source, event)

    return CardReplacement(label=effect.text, applies=applies, apply=action)


_CYCLING_DRAW_LINE = (
    "if a cycling ability of another nonland card would cause you to draw a card, instead "
    "exile cards from the top of your library until you exile a card that shares a "
    "card type with the cycled card. you may cast that card without paying its mana cost. "
    "then put the exiled cards that weren't cast this way on the bottom of your library "
    "in a random order."
)


def _compile_cycling_draw(effect: ReplacementEffect) -> CardReplacement | None:
    """Unpredictable Cyclone: "If a cycling ability of another nonland card would
    cause you to draw a card, instead exile cards from the top of your library
    until you exile a card that shares a card type with the cycled card. You may
    cast that card without paying its mana cost. Then put the exiled cards that
    weren't cast this way on the bottom of your library in a random order."
    (CR 702.29a, 614.11a) Cascade's own half-by-half process (CR 702.85a)."""
    if effect.kind is not ReplacementKind.IF_WOULD_INSTEAD or effect.from_trigger:
        return None
    if " ".join(strip_reminder_text(effect.raw)[0].lower().split()) != _CYCLING_DRAW_LINE:
        return None

    def applies(game: "Game", source: CardState, event: ReplaceableEvent) -> bool:
        cycled = event.cycled_card
        return (
            event.kind is EventKind.DRAW
            and event.amount > 0
            and cycled is not None
            and cycled.id != source.id
            and Type.LAND not in cycled.types
            and event.player is not None
            and event.player.username == source.controller
        )

    def apply(game: "Game", source: CardState, event: ReplaceableEvent) -> None:
        import random

        from ..keywords import exile_until

        event.amount = 0
        owner = event.player
        shared = set(event.cycled_card.types)
        exiled = exile_until(
            game, owner, lambda state, _: bool(shared & set(state.types)), source_name=source.name
        )
        hit = exiled[-1] if exiled and shared & set(exiled[-1].types) else None
        cast = False
        if hit is not None:
            decision = Decision(
                kind=DecisionKind.MAY,
                player=owner.username,
                prompt=f"cast {hit.name} without paying its mana cost",
                source=source.name,
                affirmative_is_legal=game.can_cast_during_resolution(hit, owner.username),
            )
            if game.ask(decision):
                cast = (
                    game.cast_during_resolution(
                        hit,
                        owner.username,
                        source_name=f"{source.name}'s replacement",
                        rule="CR 614.11a",
                    )
                    is not None
                )
        bottomed = [state for state in exiled if not (cast and state is hit)]
        seed = f"{game.shuffle_seed}:{game.shuffles_performed}:cyclone"
        random.Random(seed).shuffle(bottomed)  # noqa: S311
        if bottomed:
            game.shuffles_performed += 1
        for state in bottomed:
            game.exile.remove(state)
            owner.add(state, Zone.LIBRARY)  # the bottom of the library

    return CardReplacement(label=effect.text, applies=applies, apply=apply)


DRAW_COMPILERS = (_compile_draw_replacement, _compile_cycling_draw)
