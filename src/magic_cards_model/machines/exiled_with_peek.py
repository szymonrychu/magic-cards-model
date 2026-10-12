"""EP-01 round 3, task T6: reading back a pile of cards exiled with an object
(CR 607.2a).

- "You may look at cards exiled with this creature." (Bane Alley Broker,
  Grimoire Thief): a standing permission (CR 406.3) for the permanent's
  controller to examine the face-down cards in its pile. Read live off the
  permanent's computed ability lines, like every other look-at grant
  (`Game.known_to`), so it ends when the permanent leaves or loses the line.
- "Return a card exiled with this creature to its owner's hand." and "Put all
  cards exiled with this creature into their owners' hands." (below).
- "Turn all cards exiled with this creature face up. Counter all spells with
  those names." (below).
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import TYPE_CHECKING

from ..models.card_state import CardState
from ..models.zone import Zone

if TYPE_CHECKING:
    from ..models.game import Game

_LOOK_AT_EXILED_WITH_RE = re.compile(
    r"^you may look at (?:the )?cards exiled with this \w+\.?$", re.IGNORECASE
)


@lru_cache(maxsize=1024)
def reads_look_at_exiled_with_line(card_name: str, text: str, legendary: bool) -> bool:
    """Whether `text` is the standing "you may look at cards exiled with this
    `<noun>`" permission (the printed name read as CR 201.5's "this `<noun>`")."""
    if "look at" not in text.lower() or "exiled with" not in text.lower():
        return False
    from .abilities import self_normalized_effect_text

    line = " ".join(
        self_normalized_effect_text(card_name, text.strip(), legendary=legendary).split()
    )
    return _LOOK_AT_EXILED_WITH_RE.fullmatch(line) is not None


def may_look_at_exiled_with(game: Game, card: CardState, viewer: str) -> bool:
    """Whether a permanent `viewer` controls prints the standing look
    permission and `card` is in that permanent's own pile (CR 607.2a, the
    incarnation that exiled it, CR 400.7)."""
    from ..models.card import Supertype
    from .triggers.collect import _computed_ability_lines

    annotation = card.exile_annotation
    if card.zone is not Zone.EXILE or annotation is None or annotation.linked_permanent_id is None:
        return False
    for permanent in game.permanents_controlled_by(viewer):
        if permanent.id != annotation.linked_permanent_id:
            continue
        if not annotation.links_to(permanent.id, permanent.zone_change_stamp):
            continue
        legendary = Supertype.LEGENDARY in permanent.card.supertypes
        if any(
            reads_look_at_exiled_with_line(permanent.name, line, legendary)
            for line in _computed_ability_lines(game, permanent)
        ):
            return True
    return False


# --------------------------------------------------------------------------
# Instructions that read the pile back (CR 607.2a)
# --------------------------------------------------------------------------

_NOUN = r"this \w+"

_EXILE_FROM_HAND_FACE_DOWN_RE = re.compile(
    r"^(?P<draw>draw a card, then )?exile a card from your hand face down\.?"
    r"(?P<look>\s+you may look at that card for as long as it remains exiled\.?)?"
    r"(?:\s+(?P<rest>.+))?$",
    re.IGNORECASE,
)
_RETURN_A_CARD_RE = re.compile(
    rf"^return a card exiled with {_NOUN} to its owner'?s hand\.?$", re.IGNORECASE
)
_PUT_ALL_INTO_HANDS_RE = re.compile(
    rf"^put all cards exiled with {_NOUN} into their owners'? hands\.?$", re.IGNORECASE
)
_TURN_FACE_UP_RE = re.compile(
    rf"^turn all cards exiled with {_NOUN} face up\.?"
    r"(?P<counter>\s+counter all spells with those names\.?)?$",
    re.IGNORECASE,
)


def _pile(game: Game, ability) -> list[CardState]:
    from .linked_exile import _linked_cards

    return [card for card in _linked_cards(game, ability) if card.zone is Zone.EXILE]


def parse_exile_from_hand_face_down(text: str):
    """ "[Draw a card, then ]exile a card from your hand face down.[ You may
    look at that card for as long as it remains exiled.][ `<more>`]": the
    controller chooses a card from their hand (CR 608.2d), it is exiled face
    down (CR 406.3) and linked to the ability's source (CR 607.2a). `<more>` is
    read as an ordinary effect run afterwards (Jacob Hauken's "You may pay
    {4}{U}{U}. If you do, transform ...")."""
    if "from your hand face down" not in text.lower():
        return None
    match = _EXILE_FROM_HAND_FACE_DOWN_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None
    rest = None
    if match.group("rest"):
        from .effects.dispatch import _ability_effect_or_notice

        rest = _ability_effect_or_notice(match.group("rest"))
        if rest is None or getattr(rest, "__name__", "").endswith("notice_only"):
            return None
    draws = match.group("draw") is not None
    looks = match.group("look") is not None

    def effect(game: Game, ability) -> None:
        from .decisions import source_id_of
        from .effects.modal import _choose_one_card
        from .exile_top_marked import mark_exiled

        player = game.controller_of(ability)
        if draws:
            game.draw_cards(player.username, 1)
        if player.hand:
            chosen = _choose_one_card(
                game,
                player,
                list(player.hand),
                prompt="choose a card from your hand to exile face down",
                source=ability.source_name,
                source_id=source_id_of(ability),
            )
            (moved,) = game.exile_cards([chosen])
            mark_exiled(
                game,
                ability,
                moved,
                face_down=True,
                looker=player.username if looks else None,
            )
        if rest is not None:
            rest(game, ability)

    return effect


def parse_return_exiled_with_to_hand(text: str):
    """ "Return a card exiled with `<this>` to its owner's hand." (one of the
    pile, chosen on resolution, CR 608.2d) and "Put all cards exiled with
    `<this>` into their owners' hands." (the whole pile, one event, CR 603.2c)."""
    if "exiled with" not in text.lower():
        return None
    one = _RETURN_A_CARD_RE.fullmatch(" ".join(text.split())) is not None
    if not one and _PUT_ALL_INTO_HANDS_RE.fullmatch(" ".join(text.split())) is None:
        return None

    def effect(game: Game, ability) -> None:
        from .decisions import source_id_of
        from .effects.modal import _choose_one_card

        pile = _pile(game, ability)
        if not pile:
            return
        if one:
            card = _choose_one_card(
                game,
                game.controller_of(ability),
                pile,
                prompt="choose a card exiled with this permanent to return to its owner's hand",
                source=ability.source_name,
                source_id=source_id_of(ability),
            )
            game.return_to_hand(card)
            return
        with game.returning_together():  # CR 603.2c: one event, several cards
            for card in pile:
                game.return_to_hand(card)

    return effect


def parse_turn_exiled_with_face_up(text: str):
    """ "Turn all cards exiled with `<this>` face up.[ Counter all spells with
    those names.]": every card of the pile is turned face up (CR 406.3a lifts
    its blank), then each spell on the stack whose name is one of theirs is
    countered (CR 701.6a)."""
    if "face up" not in text.lower():
        return None
    match = _TURN_FACE_UP_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None
    counters = match.group("counter") is not None

    def effect(game: Game, ability) -> None:
        pile = _pile(game, ability)
        for card in pile:
            card.face_up = True
        if not counters:
            return
        names = {card.card.name for card in pile}
        for spell in list(game.stack):
            if isinstance(spell, CardState) and spell.card.name in names:
                game.counter(spell)

    return effect


# -- graveyard exile that is remembered (CR 607.2a) ---------------------------
#
# Cemetery Illuminator ("exile a card from a graveyard"), Azula ("target
# opponent exiles a nontoken creature they control, then they exile a nonland
# card from their graveyard"), Tinybones ("exile it from their graveyard with a
# stash counter on it"). Hedonist's Trove ("exile target opponent's graveyard")
# is the plain removal reader, linked to its source by `link_cards_exiled_during`.

_EXILE_A_CARD_FROM_A_GRAVEYARD_RE = re.compile(r"^exile a card from a graveyard\.?$", re.IGNORECASE)
_OPPONENT_EXILES_RE = re.compile(
    r"^target opponent exiles an? (?P<permanent>(?:non\w+ )?\w+) they control, "
    r"then they exile an? (?P<card>non\w+|\w+) card from their graveyard\.?$",
    re.IGNORECASE,
)
_EXILE_IT_FROM_GRAVEYARD_WITH_COUNTER_RE = re.compile(
    r"^exile it from their graveyard with an? (?P<counter>[a-z]+) counter on it\.?$",
    re.IGNORECASE,
)


def _quality(phrase: str):
    """A predicate for "`<type>`", "non`<type>`" or "nontoken `<type>`" (a
    creature, a card), or None when the word is not a card type."""
    from ..models.card import Type

    lowered = phrase.lower().strip()
    nontoken = lowered.startswith("nontoken ")
    word = lowered.removeprefix("nontoken ")
    negated = word.startswith("non")
    try:
        card_type = Type(word[3:] if negated else word)
    except ValueError:
        return None

    def matches(card: CardState) -> bool:
        if nontoken and card.token:
            return False
        return (card_type not in card.types) if negated else (card_type in card.types)

    return matches


def _choose_and_exile(game: Game, ability, chooser, candidates: list[CardState], prompt: str):
    from .decisions import source_id_of
    from .effects.modal import _choose_one_card

    if not candidates:
        return None
    chosen = _choose_one_card(
        game,
        chooser,
        candidates,
        prompt=prompt,
        source=ability.source_name,
        source_id=source_id_of(ability),
    )
    (moved,) = game.exile_cards([chosen])
    return moved


def parse_exile_a_card_from_a_graveyard(text: str):
    """ "Exile a card from a graveyard." - the controller picks one card out of
    every graveyard (CR 608.2d; none when all are empty) and it is exiled with
    the ability's source (CR 607.2a)."""
    if _EXILE_A_CARD_FROM_A_GRAVEYARD_RE.fullmatch(" ".join(text.split())) is None:
        return None

    def effect(game: Game, ability) -> None:
        from .exile_top_marked import mark_exiled

        controller = game.controller_of(ability)
        candidates = [card for player in game.players for card in player.graveyard]
        moved = _choose_and_exile(
            game, ability, controller, candidates, "choose a card from a graveyard to exile"
        )
        if moved is not None:
            mark_exiled(game, ability, moved)

    return effect


def parse_opponent_exiles_permanent_then_graveyard_card(text: str):
    """ "Target opponent exiles a `<permanent>` they control, then they exile a
    `<card>` from their graveyard." - the targeted opponent chooses both
    (CR 608.2d), each exile linked to the ability's source (CR 607.2a)."""
    match = _OPPONENT_EXILES_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None
    permanent_ok = _quality(match.group("permanent"))
    card_ok = _quality(match.group("card"))
    if permanent_ok is None or card_ok is None:
        return None

    def effect(game: Game, ability) -> None:
        from .exile_top_marked import mark_exiled

        from ..models.player import Player

        for target in game.resolve_targets(ability):
            if not isinstance(target, Player):
                continue
            battlefield = [
                c for c in game.permanents_controlled_by(target.username) if permanent_ok(c)
            ]
            first = _choose_and_exile(
                game, ability, target, battlefield, "choose a permanent you control to exile"
            )
            if first is not None:
                mark_exiled(game, ability, first)
            graveyard = [c for c in target.graveyard if card_ok(c)]
            second = _choose_and_exile(
                game, ability, target, graveyard, "choose a card from your graveyard to exile"
            )
            if second is not None:
                mark_exiled(game, ability, second)

    return effect


def parse_exile_discarded_card_with_counter(text: str):
    """ "Exile it from their graveyard with a `<kind>` counter on it." - the
    card a "whenever an opponent discards a card" trigger is about: the first
    card of the event's discard (`GameEvent.discarded_ids`; the trigger is put
    on the stack once per discarded card, CR 603.2c) still in that graveyard
    (CR 400.7: a card that moved is a new object, so one that left is skipped)."""
    match = _EXILE_IT_FROM_GRAVEYARD_WITH_COUNTER_RE.fullmatch(" ".join(text.split()))
    if match is None:
        return None
    counter = match.group("counter").lower()

    def effect(game: Game, ability) -> None:
        from .exile_top_marked import mark_exiled

        event = getattr(ability, "event", None)
        for card_id in getattr(event, "discarded_ids", ()):
            card = game.find_by_id(card_id)
            if card is None or card.zone is not Zone.GRAVEYARD:
                continue
            (moved,) = game.exile_cards([card])
            mark_exiled(game, ability, moved, counter=counter)
            return

    return effect
